import logging
import os
import io
import platform
import sys
import time
import shutil
import zipfile
from hashlib import md5
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse


import base64
from fastapi import FastAPI, WebSocket, Request, File, UploadFile, HTTPException, WebSocketDisconnect, Header, Response, Body, BackgroundTasks
import datetime as dt
from threading import Condition, Thread
from PIL import Image
import asyncio
import cv2
import numpy as np

import queue
from locate_lines import locateLines

from fastapi.middleware.cors import CORSMiddleware

from storage import *
from camera import *
from power import PowerHelper
from camera_controller import CameraController

from process import process_scan

from pydantic import BaseModel

class SetTimeProp(BaseModel):
    unixtime: str

class Scan(BaseModel):
    filename: str
    autocrop: bool
    dopcont: bool
    autocrop_size: int

class CameraControls(BaseModel):
    exp: float
    gain: float

# Set logger
# now = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
# logfile = f'logs/{now}.log'
# logging.basicConfig(filename=logfile, filemode='w', level=logging.DEBUG)



def sys_debug():
    logging.debug('-- System information --')
    logging.debug(f'OS   : {os.name}')
    logging.debug(f'Plateform   : {platform.system()}')
    logging.debug(f'Architecture   : {platform.architecture()}')
    logging.debug(f'Platform Release   : {platform.release()}')
    logging.debug(f'Python version   : {sys.version}')

sys_debug()
app = FastAPI()

origins = [
    "*",
]

app.q = queue.Queue()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")
templates = Jinja2Templates(directory="templates")
app.cameraController = None
app.normalize = False

current_dt_overlay=os.popen('grep dtoverlay=imx /boot/firmware/config.txt').read()
print((current_dt_overlay))
current_camera = "imx219" if "imx219" in current_dt_overlay else "imx477"

power = PowerHelper()

def getCameraControls():
    if app.cameraController:
        content = jsonable_encoder(app.cameraController.getCameraControls())
        return JSONResponse(content=content) 


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # dashboard config & stats
    return templates.TemplateResponse("index.html", {"request": request,
                                                     "os" : os.name,
                                                     "platform" : platform.system(),
                                                     "architecture" : platform.architecture(),
                                                     "platform_release" : platform.release(),
                                                     "python_version" : sys.version})

@app.get("/data/scans", response_class=HTMLResponse)
async def home(request: Request):
    # dashboard config & stats
    return get_data()

@app.get("/data/snapshots", response_class=HTMLResponse)
async def home(request: Request):
    # dashboard config & stats
    return get_data2()


@app.post("/update")
async def update(file: UploadFile = File(...)):
    try:
        zip_path = "./storage/tmp/sunscan_backend.zip"
        print('update', file)
        with open(zip_path, "wb") as buffer:
            buffer.write(await file.read())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
             zip_ref.extractall("/var/www/sunscan-backend/app/")

        os.system("sudo systemctl restart uvicorn")

        return JSONResponse(content={"message": "Update successful"}, status_code=200)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sunscan/stats", response_class=JSONResponse)
async def connect(request: Request):
    du = get_available_size()
    
    version = {'camera':current_camera, 'backend_api_version':'1.1.5', 'battery':power.get_battery(), 'battery_power_plugged':power.battery_power_plugged()}
    return JSONResponse(content=jsonable_encoder(du | version))

@app.get("/sunscan/scans", response_class=JSONResponse)
async def connect(request: Request):
    scans = get_scans()
    return JSONResponse(content=jsonable_encoder(scans))

@app.get("/camera/imx477/connect", response_class=JSONResponse)
async def connect(request: Request):
    app.cameraController = CameraController(IMX477Camera_CSI())
    if app.cameraController.getStatus() != "conneted":
        app.cameraController.start()
    return JSONResponse(content=jsonable_encoder({"camera_status":app.cameraController.getStatus()}))
    
@app.get("/camera/disconnect", response_class=JSONResponse)
async def disconnect(request: Request):
    if app.cameraController:
        app.cameraController.stop()
        return JSONResponse(content=jsonable_encoder({"camera_status":app.cameraController.getStatus()}))
    else:
        return JSONResponse(content=jsonable_encoder({"camera_status":"disconnected"}))
    
@app.get("/camera/status", response_class=JSONResponse)
async def disconnect(request: Request):
    if app.cameraController:
        return JSONResponse(content=jsonable_encoder({"camera_status":app.cameraController.getStatus()}))
    else:
        return JSONResponse(content=jsonable_encoder({"camera_status":"disconnected"}))
    
@app.get("/camera/crop/up/", response_class=JSONResponse)
async def increaseExpTime(request: Request):
    if app.cameraController:
        app.cameraController.setCropVerticalPosition('up')
        return getCameraControls()
    
@app.get("/camera/crop/down/", response_class=JSONResponse)
async def increaseExpTime(request: Request):
    if app.cameraController:
        app.cameraController.setCropVerticalPosition('down')
        return getCameraControls()
    
@app.post("/sunscan/set-time/", response_class=JSONResponse)
async def setTime(props:SetTimeProp, request: Request):
    os.system("sudo date -s '"+str(time.ctime(int(props.unixtime)))+"'")


@app.post("/camera/controls/", response_class=JSONResponse)
async def updateCameraControls(controls:CameraControls, request: Request):
    if app.cameraController:
        app.cameraController.setCameraControls(controls)
        return getCameraControls()
    
@app.get("/camera/toggle-crop/", response_class=JSONResponse)
async def toggleCrop(request: Request):
    if app.cameraController:
        app.cameraController.toggleCrop()
        return getCameraControls()

@app.get("/camera/infos/", response_class=JSONResponse)
async def infos(request: Request):
    if app.cameraController:
        return getCameraControls()
    
@app.get("/camera/toggle-color-mode/", response_class=JSONResponse)
async def toggleColorMode(request: Request):
    app.cameraController.toggleColorMode()
    return getCameraControls()

@app.get("/camera/toggle-normalize/", response_class=JSONResponse)
async def toggleNormalize(request: Request):
    app.cameraController.toggleNormalize()
    return getCameraControls()

@app.get("/camera/toggle-bin/", response_class=JSONResponse)
async def toggleBin(request: Request):
    app.cameraController.toggleBin()
    return getCameraControls()

@app.get("/camera/toggle-monobin-mode/", response_class=JSONResponse)
async def toggleMonoBinMode(request: Request):
    app.cameraController.toggleMonoBinMode()
    return getCameraControls()

@app.get("/camera/toggle-bin/", response_class=JSONResponse)
async def toggleFlat(request: Request):
    app.cameraController.toggleFlat()
    return getCameraControls()

@app.get("/camera/record/start/", response_class=JSONResponse)
async def decreaseGain(request: Request):
    if app.cameraController:
        app.cameraController.startRecord()
        return getCameraControls()
    
@app.get("/camera/record/stop/", response_class=JSONResponse)
async def decreaseGain(request: Request):
    if app.cameraController:
        app.cameraController.stopRecord()
        return getCameraControls()

@app.get("/camera/reset-controls/", response_class=JSONResponse)
async def resetControls(request: Request):
    if app.cameraController:
        app.cameraController.resetControls()
        return getCameraControls()
        
app.snapShotCount = 1
app.takeSnapShot = False
app.snapshot_filename = ''
@app.get("/camera/take-snapshot/", response_class=JSONResponse)
async def takeSnapShot(request: Request):
    if app.cameraController:
        app.takeSnapShot = True
        d = time.strftime("%Y_%m_%d-%H_%M_%S")
        cc = app.cameraController.getCameraControls()
        app.snapshot_filename= f"storage/snapshots/frame_{d}_{app.snapShotCount}_{int(cc['exposure_time']/1000)}ms_{cc['gain']}db.png"
        return JSONResponse(content=jsonable_encoder({"filename":app.snapshot_filename}))

def notifyScanProcessCompleted(filename, status):
    print('add event to queue', filename, 'scan_process_'+md5(filename.encode()).hexdigest())
    app.q.put('scan_process_'+md5(filename.encode()).hexdigest()+';#;'+status) 

@app.post("/sunscan/scan/delete/", response_class=JSONResponse)
async def deleteScan(scan:Scan, background_tasks: BackgroundTasks):
    if os.path.exists(scan.filename):
        shutil.rmtree(scan.filename)
        print(f"The directory {scan.filename} has been deleted.")
    else:
        print(f"The directory {scan.filename} does not exist.")

@app.post("/sunscan/scan/process/", response_class=JSONResponse)
async def processScan(scan:Scan, background_tasks: BackgroundTasks):
    if (os.path.exists(scan.filename)):
        background_tasks.add_task(process_scan,serfile=scan.filename,callback=notifyScanProcessCompleted, autocrop=scan.autocrop, dopcont=scan.dopcont, autocrop_size=scan.autocrop_size)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    
    await websocket.accept()

    print("Socket is running...")
    try:
        # while open socket
        while True:

            if not app.q.empty(): 
                print('q')
                await websocket.send_text(app.q.get()) 
                
            if app.cameraController and app.cameraController.getStatus() == 'connected':
                frame = app.cameraController.getLastFrame() 
    
                if len(frame):
                    r = frame / 256
                    if not app.cameraController.isRecording():

                        # resize image
                        scale_percent = 90 if app.cameraController.isInColorMode() else 70
                        width = int(frame.shape[1] * scale_percent / 100)
                        height = int(frame.shape[0] * scale_percent / 100)
     
                        if app.takeSnapShot and app.snapshot_filename:
                            d = time.strftime("%Y_%m_%d")
                            cv2.imwrite(app.snapshot_filename,frame) 
                            app.snapShotCount += 1
                            app.takeSnapShot = False
                    
                        max_adu = app.cameraController.getMaxADU()

                        #if not app.cameraController.isInBinMode():
                        r = cv2.resize(r, (width, height))

                        await websocket.send_text('adu;#;'+str(max_adu[0])+';#;'+str(max_adu[1])+';#;'+str(max_adu[2])) 

                        if app.cameraController.cameraIsCropped() and not app.cameraController.isInColorMode():
                            await websocket.send_text('intensity;#;'+','.join([str(int(p)) for p in frame[0,500:1500]]))  
                            await websocket.send_text('spectrum;#;'+','.join([str(int(p)) for p in frame[:,1014]])) 
                    
                    if app.cameraController.cameraIsNormalize():
                        r = cv2.normalize(r, dst=None, alpha=0, beta=256, norm_type=cv2.NORM_MINMAX)

                    if False and not  app.cameraController.isRecording():
                        r = locateLines(r)
                    byte_im = cv2.imencode('.jpg', r)[1].tobytes()
                    file_64encoded = str(base64.b64encode(byte_im)  ).split('b\'')
                    bytes_to_sent = (file_64encoded[1])[:-1]
                    
                    await websocket.send_text('camera;#;0;#;0;#;data:image/jpg;base64,'+bytes_to_sent )
                   
                    
            
            if app.cameraController and app.cameraController.isRecording():
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.25)

    except WebSocketDisconnect:
        print('Socket close.')

