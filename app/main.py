"""
Main FastAPI application for the SunScan backend.

This module sets up the FastAPI application for the SunScan device. It handles:
- API routes for device control and data retrieval
- Camera control and image processing
- WebSocket communication for real-time data streaming
- System updates and diagnostics
- Scan processing and management

The application integrates various components such as camera controllers,
power management, and storage utilities to provide a comprehensive
backend for the SunScan device.
"""

import logging
import os
import platform
import sys
import time
import shutil
import zipfile
import datetime
from hashlib import md5
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from astropy.io import fits

import base64
from fastapi import FastAPI, WebSocket, Request, File, UploadFile, HTTPException, WebSocketDisconnect, Header, Response, Body, BackgroundTasks


import asyncio
import cv2
import numpy as np

import queue
from locate_lines import locateLines

from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from storage import *
from camera import *
from power import factory_power_helper
from camera_controller import CameraController

from process import process_scan, get_fits_header
from animate import *
from dedistor import *
 
from pydantic import BaseModel

BACKEND_API_VERSION = '1.3.0'

class SetTimeProp(BaseModel):
    unixtime: str


class ScanBase(BaseModel):
    filename: str

class Scan(ScanBase):
    autocrop: bool
    autocrop_size: int
    dopcont: bool
    noisereduction: bool
    doppler_shift: int
    continuum_shift: int
    surface_sharpen_level: int
    pro_sharpen_level: int
    cont_sharpen_level: int
    offset: int
    observer: str = ''
    description: str = ''

class CameraControls(BaseModel):
    exp: float
    gain: float
    max_visu_threshold: int

def sys_debug():
    """
    Log detailed system information for debugging purposes.
    
    This function captures and logs various system details including OS,
    platform, architecture, and Python version. It's crucial for
    troubleshooting and ensuring compatibility across different setups.
    """
    logging.debug('-- System information --')
    logging.debug(f'OS   : {os.name}')
    logging.debug(f'Plateform   : {platform.system()}')
    logging.debug(f'Architecture   : {platform.architecture()}')
    logging.debug(f'Platform Release   : {platform.release()}')
    logging.debug(f'Python version   : {sys.version}')

sys_debug()
app = FastAPI()

# CORS configuration to allow all origins
origins = [
    "*",
]

# Initialize a queue for inter-thread communication
app.q = queue.Queue()

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static file directories
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# Initialize camera controller and normalization flag
app.cameraController = None
app.normalize = False

# Determine the current camera model from system configuration
current_dt_overlay=os.popen('grep dtoverlay=imx /boot/firmware/config.txt').read()
print((current_dt_overlay))
current_camera = "imx477"

# Initialize power management helper
power = factory_power_helper()

def getCameraControls():
    """
    Retrieve and return current camera control settings.
    
    This function interfaces with the camera controller to fetch
    the current settings such as exposure, gain, and other parameters.
    It returns these settings in a JSON format for API responses.
    
    Returns:
        JSONResponse: A JSON object containing current camera settings.
    """
    if app.cameraController:
        content = jsonable_encoder(app.cameraController.getCameraControls())
        return JSONResponse(content=content) 

@app.post("/update")
async def update(file: UploadFile = File(...)):
    """
    Handle system updates via uploaded zip file.
    
    This endpoint allows for updating the backend software. It receives
    a zip file, extracts it to the appropriate directory, and restarts
    the service to apply the update.
    
    Args:
        file (UploadFile): The uploaded zip file containing the update.
    
    Returns:
        JSONResponse: A response indicating the success or failure of the update.
    
    Raises:
        HTTPException: If there's an error during the update process.
    """
    try:
        zip_path = "./storage/tmp/sunscan_backend.zip"
        print('update', file)
        with open(zip_path, "wb") as buffer:
            buffer.write(await file.read())

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
             zip_ref.extractall("/var/www/sunscan-backend/")

        os.system("sudo shutdown -h now")

        return JSONResponse(content={"message": "Update successful"}, status_code=200)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sunscan/stats", response_class=JSONResponse)
async def connect(request: Request):
    """
    Retrieve comprehensive system statistics.
    
    This endpoint provides a wealth of information about the system's
    current state, including storage capacity, camera details, API version,
    and battery status. It's crucial for monitoring the device's health
    and capabilities.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: A JSON object containing various system statistics.
    """
    du = get_available_size()
    
    version = {'camera':current_camera, 'backend_api_version':BACKEND_API_VERSION, 'battery':power.get_battery(), 'battery_power_plugged':power.battery_power_plugged()}
    return JSONResponse(content=jsonable_encoder(du | version))

@app.get("/sunscan/scans", response_class=JSONResponse)
async def paginated_scans(page: int = 1, size: int = 10):
    """
    Retrieve a list of all available scans.
    
    This endpoint returns information about all scans stored in the system.
    It's used to provide an overview of available scan data to the user
    or other parts of the application.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: A JSON array containing information about each scan.
    """
    scans = get_paginated_scans(page, size)
    return JSONResponse(content=jsonable_encoder(scans))

@app.get("/sunscan/stacked", response_class=JSONResponse)
async def paginated_stacked_scans(page: int = 1, size: int = 10):
    """
    Retrieve a list of all available stacked scans.
    
    This endpoint returns information about all scans stored in the system.
    It's used to provide an overview of available scan data to the user
    or other parts of the application.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: A JSON array containing information about each scan.
    """
    scans = get_paginated_scans(page, size, get_stacked_scans)
    return JSONResponse(content=jsonable_encoder(scans))

@app.get("/sunscan/animated", response_class=JSONResponse)
async def paginated_animated_scans(page: int = 1, size: int = 10):
    """
    Retrieve a list of all available animated scans.
    
    This endpoint returns information about all scans stored in the system.
    It's used to provide an overview of available scan data to the user
    or other parts of the application.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: A JSON array containing information about each scan.
    """
    scans = get_paginated_scans(page, size, get_animated_scans)
    return JSONResponse(content=jsonable_encoder(scans))

@app.get("/camera/imx477/connect", response_class=JSONResponse)
async def connect(request: Request):
    """
    Establish a connection to the IMX477 camera.
    
    This endpoint initializes and connects to the IMX477 camera. It sets up
    the camera controller and starts the camera if it's not already connected.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: A JSON object indicating the camera's connection status.
    """
    camera = factory_imx477_camera_csi()
    app.cameraController = CameraController(camera)
    if app.cameraController.getStatus() != "connected":
        app.cameraController.start()
    return JSONResponse(content=jsonable_encoder({"camera_status":app.cameraController.getStatus()}))

@app.get("/camera/disconnect", response_class=JSONResponse)
async def disconnect(request: Request):
    """
    Disconnect the currently connected camera.
    
    This endpoint safely disconnects the camera if one is currently connected.
    It's important for properly shutting down the camera connection when needed.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: A JSON object indicating the updated camera connection status.
    """
    if app.cameraController:
        app.cameraController.stop()
        return JSONResponse(content=jsonable_encoder({"camera_status":app.cameraController.getStatus()}))
    else:
        return JSONResponse(content=jsonable_encoder({"camera_status":"disconnected"}))
    
@app.get("/camera/status", response_class=JSONResponse)
async def disconnect(request: Request):
    """
    Retrieve the current status of the camera.
    
    This endpoint checks and returns the current connection status of the camera.
    It's useful for monitoring the camera's state in the application.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: A JSON object indicating the current camera status.
    """
    if app.cameraController:
        return JSONResponse(content=jsonable_encoder({"camera_status":app.cameraController.getStatus()}))
    else:
        return JSONResponse(content=jsonable_encoder({"camera_status":"disconnected"}))
    
@app.get("/camera/crop/up/", response_class=JSONResponse)
async def increaseExpTime(request: Request):
    """
    Adjust the camera's crop position upwards.
    
    This endpoint moves the camera's crop area upwards. It's used for
    fine-tuning the area of interest in the camera's field of view.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera control settings after the adjustment.
    """
    if app.cameraController:
        app.cameraController.setCropVerticalPosition('up')
        return getCameraControls()
    
@app.get("/camera/crop/down/", response_class=JSONResponse)
async def increaseExpTime(request: Request):
    """
    Adjust the camera's crop position downwards.
    
    Similar to the 'up' endpoint, this moves the camera's crop area downwards.
    It allows for precise control over the captured image area.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera control settings after the adjustment.
    """
    if app.cameraController:
        app.cameraController.setCropVerticalPosition('down')
        return getCameraControls()
    
@app.post("/sunscan/set-time/", response_class=JSONResponse)
async def setTime(props:SetTimeProp, request: Request):
    """
    Set the system time.
    
    This endpoint allows for setting the system time. It's crucial for
    ensuring accurate timestamps on scans and other time-sensitive operations.
    
    Args:
        props (SetTimeProp): A model containing the new time as a Unix timestamp.
        request (Request): The incoming request object.
    
    Returns:
        None: This endpoint doesn't return a response directly.
    """
    os.system("sudo date -s '"+str(time.ctime(int(props.unixtime)))+"'")

@app.post("/camera/controls/", response_class=JSONResponse)
async def updateCameraControls(controls:CameraControls, request: Request):
    """
    Update camera control settings.
    
    This endpoint allows for adjusting various camera settings such as
    exposure time and gain. It's essential for optimizing image capture
    based on current conditions.
    
    Args:
        controls (CameraControls): A model containing the new camera settings.
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: The updated camera control settings after the changes.
    """
    if app.cameraController:
        app.cameraController.setCameraControls(controls)
        return getCameraControls()
    
@app.get("/camera/toggle-crop/", response_class=JSONResponse)
async def toggleCrop(request: Request):
    """
    Toggle the camera's crop mode.
    
    This endpoint switches the camera's crop mode on or off. Cropping can be
    useful for focusing on specific areas of interest in the image.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: The updated camera control settings after toggling crop mode.
    """
    if app.cameraController:
        app.cameraController.toggleCrop()
        return getCameraControls()

@app.get("/camera/infos/", response_class=JSONResponse)
async def infos(request: Request):
    """
    Retrieve detailed camera information.
    
    This endpoint provides comprehensive information about the camera's
    current settings and capabilities. It's useful for diagnostics and
    for informing users about the camera's current state.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Detailed camera information and settings.
    """
    if app.cameraController:
        return getCameraControls()
    
@app.get("/camera/toggle-color-mode/", response_class=JSONResponse)
async def toggleColorMode(request: Request):
    """
    Toggle the camera's color mode.
    
    This endpoint switches between color and monochrome imaging modes.
    It's important for different types of scientific observations.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera settings after toggling the color mode.
    """
    app.cameraController.toggleColorMode()
    return getCameraControls()

@app.get("/camera/toggle-normalize/0", response_class=JSONResponse)
async def switchOffNormalize(request: Request):
    return await toggleNormalize(0)
@app.get("/camera/toggle-normalize/1", response_class=JSONResponse)
async def switchOffNormalize(request: Request):
    return await toggleNormalize(1)
@app.get("/camera/toggle-normalize/2", response_class=JSONResponse)
async def switchOffNormalize(request: Request):
    return await toggleNormalize(2)

async def toggleNormalize(mode):
    app.cameraController.toggleNormalize(mode)
    return getCameraControls()

@app.get("/camera/toggle-bin/", response_class=JSONResponse)
async def toggleBin(request: Request):
    """
    Toggle camera binning mode.
    
    This endpoint switches the camera's binning mode on or off. Binning can
    improve signal-to-noise ratio at the cost of resolution.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera settings after toggling binning mode.
    """
    app.cameraController.toggleBin()
    return getCameraControls()

@app.get("/camera/toggle-monobin-mode/", response_class=JSONResponse)
async def toggleMonoBinMode(request: Request):
    """
    Toggle monochrome binning mode.
    
    This endpoint switches between different monochrome binning modes,
    which can be useful for specific types of astronomical observations.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera settings after toggling mono binning mode.
    """
    app.cameraController.toggleMonoBinMode()
    return getCameraControls()

@app.get("/camera/toggle-bin/", response_class=JSONResponse)
async def toggleFlat(request: Request):
    """
    Toggle flat field correction.
    
    This endpoint enables or disables flat field correction, which is used
    to improve image uniformity by compensating for variations in pixel sensitivity.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera settings after toggling flat field correction.
    """
    app.cameraController.toggleFlat()
    return getCameraControls()

@app.get("/camera/record/start/", response_class=JSONResponse)
async def decreaseGain(request: Request):
    """
    Start camera recording.
    
    This endpoint initiates the camera recording process. It's used for
    capturing video or a series of images over time.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera settings after starting the recording.
    """
    if app.cameraController:
        app.cameraController.startRecord()
        return getCameraControls()
    
@app.get("/camera/record/stop/", response_class=JSONResponse)
async def decreaseGain(request: Request):
    """
    Stop camera recording.
    
    This endpoint stops the ongoing camera recording process. It's important
    for properly ending a recording session and saving the captured data.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera settings after stopping the recording.
    """
    if app.cameraController:
        app.cameraController.stopRecord()
        return getCameraControls()

@app.get("/camera/reset-controls/", response_class=JSONResponse)
async def resetControls(request: Request):
    """
    Reset camera controls to default values.
    
    This endpoint resets all camera settings to their default values. It's useful
    for quickly returning to a known, standard configuration.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Updated camera settings after resetting to defaults.
    """
    if app.cameraController:
        app.cameraController.resetControls()
        return getCameraControls()
        
app.snapShotCount = 1
app.takeSnapShot = False
app.snapshot_filename = ''
app.snapshot_header = None

@app.get("/camera/take-snapshot/", response_class=JSONResponse)
async def takeSnapShot(request: Request):
    """
    Capture a snapshot with the camera.
    
    This endpoint triggers the camera to take a single snapshot. It generates
    a unique filename for the snapshot based on current time and camera settings.
    
    Args:
        request (Request): The incoming request object.
    
    Returns:
        JSONResponse: Information about the captured snapshot, including its filename.
    """
    if app.cameraController:
        app.takeSnapShot = True
        d = time.strftime("%Y_%m_%d-%H_%M_%S")
        cc = app.cameraController.getCameraControls()
        app.snapshot_filename= f"storage/snapshots/frame_{d}_{app.snapShotCount}"

        app.snapshot_header = get_fits_header(cc['exposure_time'], cc['gain'])

        return JSONResponse(content=jsonable_encoder({"filename":app.snapshot_filename}))

def notifyScanProcessCompleted(filename, status):
    """
    Notify that a scan process has completed.
    
    This function is called when a scan processing task finishes. It adds
    a notification to the queue, which can be picked up by the WebSocket
    to inform the client about the completion of the scan process.
    
    Args:
        filename (str): The filename of the completed scan.
        status (str): The status of the completed scan process.
    """
    print('add event to queue', filename, 'scan_process_'+md5(filename.encode()).hexdigest())
    app.q.put('scan_process_'+md5(filename.encode()).hexdigest()+';#;'+status) 

@app.post("/sunscan/scan/delete/", response_class=JSONResponse)
async def deleteScan(scan:ScanBase, background_tasks: BackgroundTasks):
    """
    Delete a scan directory.
    
    This endpoint removes a specified scan directory and all its contents.
    It's used for managing storage and removing unwanted scan data.
    
    Args:
        scan (Scan): A model containing the filename of the scan to be deleted.
        background_tasks (BackgroundTasks): FastAPI's background tasks handler.
    
    Returns:
        None: This endpoint doesn't return a response directly.
    """
    if os.path.exists(scan.filename):
        shutil.rmtree(scan.filename)
        print(f"The directory {scan.filename} has been deleted.")
    else:
        print(f"The directory {scan.filename} does not exist.")

@app.post("/sunscan/scans/delete/", response_class=JSONResponse)
async def deleteScans(data: PostProcessRequest):
    """
    Delete multiple scan directories.
    
    This endpoint removes a specified scan directory and all its contents.
    It's used for managing storage and removing unwanted scan data.
    
    Args:
        scan (Scan): A model containing the filename of the scan to be deleted.
        background_tasks (BackgroundTasks): FastAPI's background tasks handler.
    
    Returns:
        None: This endpoint doesn't return a response directly.
    """
    for p in data.paths:
        if os.path.exists(p):
            shutil.rmtree(p)
            print(f"The directory {p} has been deleted.")
        else:
            print(f"The directory {p} does not exist.")

@app.get("/sunscan/snapshots/delete/all/", response_class=JSONResponse)
async def deleteAllSnapshots(background_tasks: BackgroundTasks):
    """
    Delete all snapshots.

    Args:
        background_tasks (BackgroundTasks): FastAPI's background tasks handler.
    
    Returns:
        None: This endpoint doesn't return a response directly.
    """
    dirToClean = './storage/snapshots/'
    for item in os.listdir(dirToClean):
        item_path = os.path.join(dirToClean, item)
        if os.path.isfile(item_path):
            os.remove(item_path)  
        print(f"The directory {dirToClean} ws cleared.")
    else:
        print(f"The directory {dirToClean} does not exist.")


@app.post("/sunscan/shutdown", response_class=JSONResponse)
async def shutdownSUNSCAN():
    os.system("sudo shutdown -h now")
    return JSONResponse(content={"message": "Shutdown ok"}, status_code=200)

@app.post("/sunscan/reboot", response_class=JSONResponse)
async def rebootSUNSCAN():
    os.system("sudo shutdown -r now")
    return JSONResponse(content={"message": "Reboot ok"}, status_code=200)


@app.post("/sunscan/scan", response_class=JSONResponse)
async def getScanDetails(scan:ScanBase, request: Request):
    scans = get_single_scan(scan.filename)
    return JSONResponse(content=jsonable_encoder(scans))

@app.post("/sunscan/scan/process/", response_class=JSONResponse)
async def processScan(scan:Scan, background_tasks: BackgroundTasks):
    """
    Process a scan in the background.
    
    This endpoint initiates the processing of a scan. The actual processing
    is done in a background task to avoid blocking the API. It handles
    various processing options like autocropping and contrast adjustment.
    
    Args:
        scan (Scan): A model containing scan processing parameters.
        background_tasks (BackgroundTasks): FastAPI's background tasks handler.
    
    Returns:
        None: The processing is done in the background, so no immediate return.
    """
    if (os.path.exists(scan.filename)):
        print(scan)
        background_tasks.add_task(process_scan,serfile=scan.filename,callback=notifyScanProcessCompleted, autocrop=scan.autocrop, dopcont=scan.dopcont, autocrop_size=scan.autocrop_size, noisereduction=scan.noisereduction, dopplerShift=scan.doppler_shift, contShift=scan.continuum_shift, contSharpLevel=scan.cont_sharpen_level, surfaceSharpLevel=scan.surface_sharpen_level, proSharpLevel=scan.pro_sharpen_level, offset=scan.offset, observer=scan.observer)


@app.post("/sunscan/process/stack/")
def process_stack(request: PostProcessRequest):
    required_files = {"clahe": False, "protus": False, "cont": False}
    for required_file, status in required_files.items():
        matching_paths = []
        for path_str in request.paths:
            path = Path(os.path.join(os.path.dirname(path_str) , "sunscan_"+required_file+".png"))
            if path.exists():
                matching_paths.append(path)
        if len(matching_paths) == len(request.paths):
            required_files[required_file] = True
    stack(request.paths, required_files, request.observer)
     
@app.post("/sunscan/process/animate/")
def process_animate(request: PostProcessRequest):
    # Supported filenames and output GIF names
    required_files = ["sunscan_clahe.png", "sunscan_protus.png", "sunscan_cont.png"]
    gif_names = {
        "sunscan_clahe.png": "animated_clahe.gif",
        "sunscan_protus.png": "animated_protus.gif",
        "sunscan_cont.png": "animated_cont.gif",
    }

    gifs_created = []

    stacking_dir = './storage/animations'
    if not os.path.exists(stacking_dir):
        os.mkdir(stacking_dir)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    work_dir = os.path.join(stacking_dir, timestamp)
    if not os.path.exists(work_dir):
        os.mkdir(work_dir)

    # Check for each required file type and generate GIFs if possible
    for required_file in required_files:
        matching_paths = []

        for path_str in request.paths:
            path = Path(os.path.dirname(path_str)) / required_file
            print(path)

            if path.exists() or os.path.exists(path):
                matching_paths.append(path)

        print(matching_paths)
        # Create GIF if all paths contain the required file
        if len(matching_paths) == len(request.paths):
            output_gif_path = os.path.join(work_dir, gif_names[required_file])
            create_gif(matching_paths, request.watermark, request.observer, output_gif_path, request.frame_duration, request.display_datetime, request.resize_gif, request.bidirectional, request.add_average_frame)
            gifs_created.append(str(output_gif_path))

    if not gifs_created:
        raise HTTPException(status_code=400, detail="No GIFs were created. Ensure the required files exist.")

    return {"message": "GIFs created successfully", "gifs": gifs_created}

class FileTagRequest(BaseModel):
    filename: str
    tag: str

@app.post("/sunscan/scan/tag/")
async def create_tag_file(request: FileTagRequest):
    directory = request.filename
    tag = request.tag


    # Check if the directory exists
    if not os.path.exists(directory):
        raise HTTPException(status_code=400, detail="The specified directory does not exist.")

    # Remove all files starting with tag_ in the directory
    for file in os.listdir(directory):
        if file.startswith("tag_"):
            try:
                os.remove(os.path.join(directory, file))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error removing file {file}: {str(e)}")

    # Construct the full path for the tag_<tag> file
    tag_filename = os.path.join(directory, f"tag_{tag}")

    try:
        # Write an empty file with the name tag_<tag>
        with open(tag_filename, "w") as f:
            f.write("")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating the file: {str(e)}")

    return {"message": f"File '{tag_filename}' created successfully."}



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication.
    
    This endpoint handles WebSocket connections for real-time data streaming.
    It continuously sends camera frames, ADU values, and other real-time data
    to connected clients. It also handles notifications from the queue.
    
    Args:
        websocket (WebSocket): The WebSocket connection object.
    
    The function runs in an infinite loop, continuously sending data until
    the WebSocket connection is closed.
    """
    await websocket.accept()

    print("Socket is running...")
    try:
        # Infinite loop to handle continuous data streaming
        while True:
            # Check for notifications in the queue
            if not app.q.empty(): 
                print('q')
                await websocket.send_text(app.q.get()) 
                
            # Handle camera frame streaming if camera is connected
            if app.cameraController and app.cameraController.getStatus() == 'connected':
                frame = app.cameraController.getLastFrame() 
    
                if len(frame):
                    r = frame / 256
                    if not app.cameraController.isRecording():
                        # Handle snapshot capture if requested
                        if app.takeSnapShot and app.snapshot_filename and app.snapshot_header:
                            d = time.strftime("%Y_%m_%d")
                            cv2.imwrite(app.snapshot_filename+'.png',frame) 

                            app.snapshot_header['WIDTH']=frame.shape[1]
                            app.snapshot_header['HEIGHT']=frame.shape[0]

                            DiskHDU=fits.PrimaryHDU(frame,app.snapshot_header)
                            DiskHDU.writeto(app.snapshot_filename+'.fits', overwrite='True')

                            app.snapShotCount += 1
                            app.takeSnapShot = False
                            app.snapshot_header = None

                        # Resize image for streaming
                        scale_percent = 90 if app.cameraController.isInColorMode() else 70
                        width = int(frame.shape[1] * scale_percent / 100)
                        height = int(frame.shape[0] * scale_percent / 100)
                        r = cv2.resize(r, (width, height))
                    
                        # Get and send ADU values
                        max_adu = app.cameraController.getMaxADU()
                        await websocket.send_text('adu;#;'+str(max_adu[0])+';#;'+str(max_adu[1])+';#;'+str(max_adu[2])) 

                        # Send intensity and spectrum data for cropped images
                        if app.cameraController.cameraIsCropped() and not app.cameraController.isInColorMode():
                            await websocket.send_text('intensity;#;'+','.join([str(int(p)) for p in frame[0,500:1500]]))  
                            await websocket.send_text('spectrum;#;'+','.join([str(int(p)) for p in frame[:,1014]])) 
                    
                    # Apply normalization if enabled
                    if app.cameraController.normalizeMode()==1:    
                        r = cv2.normalize(r, dst=None, alpha=0, beta=256, norm_type=cv2.NORM_MINMAX)
                    else:
                        max_threshold = app.cameraController.getMaxVisuThreshold()
                        r = (r * 256) / max_threshold
                    
                    # Encode and send the frame
                    byte_im = cv2.imencode('.jpg', r)[1].tobytes()
                    file_64encoded = str(base64.b64encode(byte_im)  ).split('b\'')
                    bytes_to_sent = (file_64encoded[1])[:-1]

                    await websocket.send_text('camera;#;0;#;0;#;data:image/jpg;base64,'+bytes_to_sent )
                   
            # Adjust sleep time based on recording status
            if app.cameraController and app.cameraController.isRecording():
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.25)

    except WebSocketDisconnect:
        print('Socket close.')



## ------------ Webapp Routes here-------- #
# Todo : draft for now - clear and clean stuff
# Chemin vers le dossier contenant les scans
# Se base sur la structure des dossiers de stockage
SCANS_DIR = "storage/scans"
SNAPSHOTS_DIR = "storage/snapshots"

@app.get("/snapshots")
async def get_snapshots():
    if not os.path.exists(SNAPSHOTS_DIR):
        raise HTTPException(status_code=404, detail="Scan folder not found")
    images = [f for f in os.listdir(SNAPSHOTS_DIR) if f.lower().endswith(('.fits', '.png'))] #todo : extract to a main list?
    return [{"name": image, "thumbnail": f"/snapshots/{image}"} for image in images]

@app.get("/download/snapshot/{image_name}")
async def download_image(image_name: str):
    image_path = os.path.join(SNAPSHOTS_DIR,image_name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path, filename=image_name)

@app.get("/dates")
async def get_date_folders():
    dates = [f for f in os.listdir(SCANS_DIR) if os.path.isdir(os.path.join(SCANS_DIR, f))]
    return [{"name": date, "thumbnail": get_first_image_thumbnail(date)} for date in dates]

@app.get("/dates/{date_folder}")
async def get_scan_folders(date_folder: str):
    date_path = os.path.join(SCANS_DIR, date_folder)
    if not os.path.exists(date_path):
        raise HTTPException(status_code=404, detail="Date folder not found")
    scans = [f for f in os.listdir(date_path) if os.path.isdir(os.path.join(date_path, f))]
    return [{"name": scan, "thumbnail": get_first_image_thumbnail(date_folder, scan)} for scan in scans]

@app.get("/dates/{date_folder}/scans/{scan_folder}")
async def get_images_in_scan(date_folder: str, scan_folder: str):
    scan_path = os.path.join(SCANS_DIR, date_folder, scan_folder)
    if not os.path.exists(scan_path):
        raise HTTPException(status_code=404, detail="Scan folder not found")
    images = [f for f in os.listdir(scan_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.fits', '.ser', '.txt'))] #todo : extract to a main list?
    return [{"name": image, "thumbnail": f"/images/{date_folder}/{scan_folder}/{image}"} for image in images]

@app.get("/images/{date_folder}/{scan_folder}/{image_name}")
async def get_image(date_folder: str, scan_folder: str, image_name: str):
    image_path = os.path.join(SCANS_DIR, date_folder, scan_folder, image_name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)

@app.get("/download/scan/{date_folder}/{scan_folder}")
async def download_scan(date_folder: str, scan_folder: str):
    scan_path = os.path.join(SCANS_DIR, date_folder, scan_folder,'scan.ser')
    if not os.path.exists(scan_path):
        raise HTTPException(status_code=404, detail="Scan folder not found")
    # return FileResponse
    return FileResponse(scan_path, filename=scan_folder+'.ser')



@app.get("/download/image/{date_folder}/{scan_folder}/{image_name}")
async def download_image(date_folder: str, scan_folder: str, image_name: str):
    image_path = os.path.join(SCANS_DIR, date_folder, scan_folder, image_name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path, filename=scan_folder.replace('sunscan_', '')+'-'+image_name)

def get_first_image_thumbnail(date_folder, scan_folder=None):
    path = os.path.join(SCANS_DIR, date_folder)
    if scan_folder:
        path = os.path.join(path, scan_folder)
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.ser', '.txt')): # todo : extract to a main list?
                return f"/images/{os.path.relpath(os.path.join(root, file), SCANS_DIR)}"
    return None