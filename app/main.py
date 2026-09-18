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
import subprocess
from typing import List
from hashlib import md5
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from astropy.io import fits

import base64
from fastapi import FastAPI, WebSocket, Request, File, UploadFile, HTTPException, WebSocketDisconnect, Header, Response, Body, BackgroundTasks, Query


import asyncio
import cv2
import numpy as np

import queue
from locate_lines import locateLines

from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from storage import *
from camera import *
from power import factory_power_helper
from camera_controller import CameraController

from focus_analyzer import FocusAnalyzer

from process import process_scan, get_fits_header
from scan_progress import ScanProgress, scan_key
import gallery
from system_tuning import apply_system_tuning
from animate import *
from dedistor import *
 
from pydantic import BaseModel

BACKEND_API_VERSION = '2.0.0'

class SetTimeProp(BaseModel):
    unixtime: str
    timezone: str

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
    advanced: str = ''
    doppler_color: int 
    process_doppler: bool

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
# Before any thread is started, so they all inherit the raised priority
apply_system_tuning()
app = FastAPI()

# CORS configuration to allow all origins
origins = [
    "*",
]

# Initialize a queue for inter-thread communication
app.q = queue.Queue()

# Processing progress of the scans, written by the processing threads and sent by the WebSocket
app.scanProgress = ScanProgress()

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

@app.options("/{full_path:path}")
async def preflight_handler(full_path: str, response: Response):
    """
    Handles CORS preflight requests.

    When a browser makes a cross-origin request, it may first send an OPTIONS 
    request (a "preflight" request) to check which HTTP methods and headers are 
    allowed. This function responds to such requests by setting appropriate CORS 
    headers, allowing the client to proceed with the actual request.

    Parameters:
    - full_path (str): The requested path (not used directly in this function).
    - response (Response): The HTTP response object.

    Returns:
    - Response: A response with CORS headers allowing cross-origin requests.
    """
    response.headers["Access-Control-Allow-Origin"] = "*"  # Allows requests from any origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"  # Permits specified HTTP methods
    response.headers["Access-Control-Allow-Headers"] = "*"  # Allows all headers
    return response


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
    app.cameraController.setProfile(app.profile)
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
async def setTime(props: SetTimeProp, request: Request):
    """
    Set the system time and timezone.
    
    This endpoint allows for setting the system time and updating the timezone on the Raspberry Pi 4.
    
    Args:
        props (SetTimeProp): A model containing the new time as a Unix timestamp and timezone.
        request (Request): The incoming request object.
    
    Returns:
        dict: Confirmation message with the set time and timezone.
    """

    
    # Log current timezone and time
    current_timezone = subprocess.getoutput("timedatectl show --property=Timezone --value")
    current_time = subprocess.getoutput("date")
    print(f"Current Timezone: {current_timezone}, Current Time: {current_time}")
    
    # Update time and timezone
    os.system("sudo date -s '"+str(time.ctime(int(props.unixtime)))+"'")
    os.system(f"sudo timedatectl set-timezone {props.timezone}")  # Update the system timezone
    
    # Log updated timezone and time
    updated_timezone = subprocess.getoutput("timedatectl show --property=Timezone --value")
    updated_time = subprocess.getoutput("date")
    print(f"Updated Timezone: {updated_timezone}, Updated Time: {updated_time}")
    
    return {"message": "Time and timezone set successfully", "unixtime": props.unixtime, "timezone": props.timezone}

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

@app.get("/camera/toggle-focus-assistant/", response_class=JSONResponse)
async def toggleFocusAssistant(request: Request):
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
        app.cameraController.toggleFocusAssistant()
        return getCameraControls()

# 1D spectral profile streamed on the WebSocket on demand (message 'profile;#;x0;#;n;#;v1,v2,...')
# 12-bit values, one per frame row, averaged over n columns starting at x0
app.profile = {'enabled': False, 'columns': 16, 'x': None}

class ProfileRequest(BaseModel):
    enabled: bool
    columns: int = 16
    x: int | None = None  # centre column, None = centre of the frame

@app.post("/camera/profile/", response_class=JSONResponse)
async def setProfile(request: ProfileRequest):
    """
    Enable/disable the 1D profile (12 bits, averaged over `columns` columns centred on `x`)
    sent on the WebSocket with each preview frame (not during a recording). In colour mode it is
    computed by the camera from the raw Bayer data, like the mono profile in monobin mode 0.
    """
    if request.columns < 1 or (request.x is not None and request.x < 0):
        raise HTTPException(status_code=422, detail="columns must be >= 1 and x >= 0")
    app.profile = request.model_dump()
    if app.cameraController:
        app.cameraController.setProfile(app.profile)
    return app.profile

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
        # stopRecord blocks until the SER file is fully written: keep the event loop (WebSocket) alive meanwhile
        scan_path = await run_in_threadpool(app.cameraController.stopRecord)
        if not scan_path:
            # stop received before any frame was recorded (or without a start)
            return JSONResponse(content={"error": "no frame recorded"}, status_code=409)
        return JSONResponse(content={"scan": os.path.dirname(scan_path)}, status_code=200)

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

def notifyScanProcessProgress(filename, step, percent):
    """
    Notify the progress of a scan process.

    This function is called by the scan processing task each time it moves
    forward. The WebSocket sends the new state to the clients on the
    'scan_progress_<key>' channel.

    Args:
        filename (str): The filename of the scan being processed.
        step (str): Key of the current processing step.
        percent (int): Global progress of the processing, 0 to 99.
    """
    app.scanProgress.update(scan_key(filename), step, percent)

def notifyScanProcessCompleted(filename, status, error='', detail=''):
    """
    Notify that a scan process has completed.

    This function is called when a scan processing task finishes. It sets
    the final state on the 'scan_progress_<key>' channel and adds
    a notification to the queue, which can be picked up by the WebSocket
    to inform the client about the completion of the scan process.

    Args:
        filename (str): The filename of the completed scan.
        status (str): The status of the completed scan process.
        error (str): Error key when the status is 'failed'.
        detail (str): Raw error message when the status is 'failed'.
    """
    app.scanProgress.finish(scan_key(filename), status, error, detail)
    # Message listened to by the app versions that do not know the progress channel
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
    path = gallery.resolve_storage_path(scan.filename)
    if os.path.exists(path):
        await gallery.run_low(shutil.rmtree, path)
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
    # check them all before deleting anything
    paths = [gallery.resolve_storage_path(p) for p in data.paths]
    for p, path in zip(data.paths, paths):
        if os.path.exists(path):
            await gallery.run_low(shutil.rmtree, path)
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


@app.post("/sunscan/shutdown/", response_class=JSONResponse)
async def shutdownSUNSCAN():
    os.system("sudo shutdown -h now")
    return JSONResponse(content={"message": "Shutdown ok"}, status_code=200)

@app.post("/sunscan/reboot/", response_class=JSONResponse)
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
        JSONResponse: {"status": "started", "key": ...}, the processing itself is done in
        the background and followed on the 'scan_progress_<key>' WebSocket channel.
        404 with {"status": "failed", "error": "file_not_found", "key": ...} if the scan does not exist.
    """
    key = scan_key(scan.filename)
    if (os.path.exists(scan.filename)):
        print(scan)
        app.scanProgress.start(key)
        background_tasks.add_task(process_scan, callback=notifyScanProcessCompleted, scan=scan,
                                  progress=lambda step, percent: notifyScanProcessProgress(scan.filename, step, percent))
        return JSONResponse(content={"status": "started", "key": key})

    notifyScanProcessCompleted(scan.filename, 'failed', 'file_not_found', scan.filename)
    return JSONResponse(content={"status": "failed", "error": "file_not_found", "key": key}, status_code=404)

@app.post("/sunscan/scan/process/status/", response_class=JSONResponse)
async def getScanProcessStatus(scan:ScanBase):
    """
    Get the current processing state of a scan.

    Same information as the last message of the 'scan_progress_<key>' WebSocket
    channel. Useful when the client missed messages, after the app was in the
    background for instance.

    Args:
        scan (ScanBase): A model containing the filename of the scan.

    Returns:
        JSONResponse: key, status ('processing', 'completed', 'failed', or 'unknown' if no
        processing of this scan is known), percent, step, error and detail.
    """
    key = scan_key(scan.filename)
    state = app.scanProgress.get(key)
    if state is None:
        state = {"key": key, "status": "unknown", "percent": 0, "step": "", "error": "", "detail": ""}
    return JSONResponse(content={name: state[name] for name in ("key", "status", "percent", "step", "error", "detail")})


@app.post("/sunscan/process/stack/")
def process_stack(request: PostProcessRequest):
    required_files = {"clahe": False, "protus": False, "cont": False, "color":False, "helium":False, "helium_cont":False}
    for required_file, status in required_files.items():
        matching_paths = []
        for path_str in request.paths:
            path = Path(os.path.join(os.path.dirname(path_str) , "sunscan_"+required_file+".png"))
            if path.exists():
                matching_paths.append(path)
        if len(matching_paths) == len(request.paths):
            required_files[required_file] = True
    start_time = time.perf_counter()
    stack(request.paths, required_files, request.observer, request.patch_size, request.step_size, request.intensity_threshold)
    end_time = time.perf_counter()
    print(f" {end_time - start_time:.6f} secondes") 

@app.post("/sunscan/process/animate/")
def process_animate(request: PostProcessRequest):
    # Supported filenames and output GIF names
    gif_names = {
        "sunscan_clahe.png": "animated_clahe.gif",
        "sunscan_negative.png": "animated_negative.gif",
        "sunscan_helium.png": "animated_helium.gif",
        "sunscan_helium_cont.png": "animated_helium_cont.gif",
        "sunscan_protus.png": "animated_protus.gif",
        "sunscan_cont.png": "animated_cont.gif",
    }

    gif_names_stacking = {
        "stacked_clahe_*_raw.png": "stacked_clahe_raw.gif",
        "stacked_clahe_*_sharpen.png": "stacked_clahe_sharpen.gif",
        "stacked_negative_*_raw.png": "stacked_negative.gif",
        "stacked_negative_*_sharpen.png": "stacked_negative_sharpen.gif",
        "stacked_helium_*_raw.png": "stacked_helium.gif",
        "stacked_helium_*_sharpen.png": "stacked_helium_sharpen.gif",
        "stacked_helium_cont_*_raw.png": "stacked_helium_cont.gif",
        "stacked_helium_cont_*_sharpen.png": "stacked_helium_cont_sharpen.gif",
        "stacked_protus_*_raw.png": "stacked_protus.gif",
        "stacked_protus_*_sharpen.png": "stacked_protus_sharpen.gif",
        "stacked_cont_*_raw.png": "stacked_cont.gif",
        "stacked_cont_*_sharpen.png": "stacked_cont_sharpen.gif",
        # "stacked_color_*_raw.jpg": "stacked_cont.gif",
        # "stacked_color_*_sharpen.jpg": "stacked_cont_sharpen.gif",
    }

    gifs_created = []

    stacking_dir = './storage/animations'
    os.makedirs(stacking_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    work_dir = os.path.join(stacking_dir, timestamp)
    os.makedirs(work_dir, exist_ok=True)

    # Vérifier si on est en mode stacking
    is_stacking_mode = any("stacking" in p for p in request.paths)

    if is_stacking_mode:
        # MODE STACKING
        for pattern, gif_name in gif_names_stacking.items():
            regex_pattern = pattern.replace("*", r"(\d+)")  # transformer * en regex pour chiffres
            regex = re.compile(regex_pattern)

            matching_paths = []

            # scanner tous les répertoires donnés
            for path_str in request.paths:
                directory = Path(path_str)
                if not directory.exists():
                    continue

                for file in directory.glob("*.png"):
                    if regex.fullmatch(file.name):
                        matching_paths.append(file)

            # si on a trouvé des fichiers correspondants → créer le GIF
            if matching_paths:
                output_gif_path = os.path.join(work_dir, gif_name)
                create_gif(
                    matching_paths,
                    request.watermark,
                    request.observer,
                    output_gif_path,
                    request.frame_duration,
                    request.display_datetime,
                    request.resize_gif,
                    request.bidirectional,
                    request.add_average_frame,
                )
                gifs_created.append(str(output_gif_path))

    else:
        # MODE CLASSIQUE
        for required_file, gif_name in gif_names.items():
            matching_paths = []

            for path_str in request.paths:
                path = Path(os.path.dirname(path_str)) / required_file

                if path.exists():
                    matching_paths.append(path)
     
            # Create GIF if all paths contain the required file
            if len(matching_paths) == len(request.paths):
                output_gif_path = os.path.join(work_dir, gif_name)
                create_gif(
                    matching_paths,
                    request.watermark,
                    request.observer,
                    output_gif_path,
                    request.frame_duration,
                    request.display_datetime,
                    request.resize_gif,
                    request.bidirectional,
                    request.add_average_frame,
                )
                gifs_created.append(str(output_gif_path))

    if not gifs_created:
        raise HTTPException(status_code=400, detail="No GIFs were created. Ensure the required files exist.")

    return {"message": "GIFs created successfully", "gifs": gifs_created}

class FileTagRequest(BaseModel):
    filename: str
    tag: str

@app.post("/sunscan/scan/tag/")
async def create_tag_file(request: FileTagRequest):
    directory = gallery.resolve_storage_path(request.filename)
    tag = request.tag
    if not tag or '/' in tag or '\\' in tag or tag in ('.', '..'):
        raise HTTPException(status_code=400, detail="Invalid tag")

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


def calculate_fwhm(y):
    x = np.arange(len(y))
    max_value = np.max(y)
    half_max = max_value / 2.0
    indices = np.where(y >= half_max)[0]
    if len(indices) < 2:
        return None
    left_idx = indices[0]
    right_idx = indices[-1]
    fwhm = x[right_idx] - x[left_idx]
    return fwhm

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
        focus_analyzer = FocusAnalyzer(measure_every=5)
        # Last scan processing state sent to this client, 0 so that a client which
        # (re)connects gets the current state of the scans being processed
        progress_seq = 0
        # Infinite loop to handle continuous data streaming
        while True:
            # Check for notifications in the queue
            if not app.q.empty():
                print('q')
                await websocket.send_text(app.q.get())

            # Send the scan processing states that changed since the last loop
            for state in app.scanProgress.changes_since(progress_seq):
                await websocket.send_text(ScanProgress.to_message(state))
                progress_seq = state['seq']

            # Handle camera frame streaming if camera is connected
            if app.cameraController and app.cameraController.getStatus() == 'connected':
                frame = app.cameraController.getLastFrame() 
    
                if len(frame):
                    # Live disk preview : core of the darkest line along the whole slit
                    # (the disk can extend beyond the central 1000 columns)
                    if (app.cameraController.isRecording() and len(frame.shape) == 2
                            and app.cameraController.cameraIsCropped()):
                        w = frame.shape[1] // 125 * 125
                        band = cv2.blur(frame[:, :w].astype(np.float32), (1, 3))
                        core = band.min(axis=0)                      # darkest pixel of each column
                        core = core.reshape(125, -1).mean(axis=1)
                        await websocket.send_text('scanline;#;' + ','.join(str(int(v)) for v in core))

                    r = frame / 256
                    edges = None
                    if not app.cameraController.isRecording():
                        #if not app.cameraController.cameraIsCropped() :
                        #    r = locateLines(r)
                        
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

                        # Send intensity and spectrum data for cropped imagess
                        if len(frame.shape) == 2 and app.cameraController.cameraIsCropped() :
                            await websocket.send_text('intensity;#;'+','.join([str(int(p)) for p in frame[0,500:1500]]))  
                            await websocket.send_text('spectrum;#;'+str(calculate_fwhm(frame[:,1014]))+';#;'+','.join([str(int(p)) for p in frame[:,1014]]))

                        # 1D profile on demand: 16-bit frame -> 12 bits, averaged over n columns (rounded integer division)
                        if app.profile['enabled'] and len(frame.shape) == 2:
                            n = min(app.profile['columns'], frame.shape[1])
                            x0 = min(max((app.profile['x'] if app.profile['x'] is not None else frame.shape[1] // 2) - n // 2, 0), frame.shape[1] - n)
                            p = (frame[:, x0:x0+n].sum(axis=1, dtype=np.uint32) + n * 8) // (n * 16)
                            await websocket.send_text(f'profile;#;{x0};#;{n};#;' + ','.join(map(str, p.tolist())))
                        elif app.profile['enabled']:
                            color_profile = app.cameraController.getColorProfile()
                            if color_profile is not None:
                                x0, n, p = color_profile
                                await websocket.send_text(f'profile;#;{x0};#;{n};#;' + ','.join(map(str, p.tolist())))

                        # Send focus analyzer data
                        edges = None
                        if app.cameraController.focusAssistantIsOn() and not app.cameraController.isInColorMode():
                            # Update focus measurement
                            sharpness, edges = focus_analyzer.update(frame)
                            await websocket.send_text('focus;#;'+str(sharpness)+';#;'+str(0)+';#;'+str(edges[0])+';#;'+str(edges[1]))
                    
                    # Apply normalization if enabled
                    if app.cameraController.normalizeMode()==1:    
                        r = cv2.normalize(r, dst=None, alpha=0, beta=256, norm_type=cv2.NORM_MINMAX)
                    else:
                        max_threshold = app.cameraController.getMaxVisuThreshold()
                        r = (r * 256) / max_threshold

                    # Rescale edges if they exist
                    if edges:

                        # Compute resize ratios
                        scale_x = r.shape[1] / frame.shape[1]   # width ratio
                        scale_y = r.shape[0] / frame.shape[0]   # height ratio, usually 1D profile so can ignore

                        edges_scaled = (
                            int(edges[0] * scale_x - 10) if edges[0] is not None else None,
                            int(edges[1] * scale_x + 10) if edges[1] is not None else None
                        )
                        r = FocusAnalyzer.overlay_edges(r.copy(), edges_scaled)
                    
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
# Legacy gallery routes, kept with the same URLs and responses for the clients built on them.
# The web app now uses the /gallery API (gallery.py). Every path goes through gallery.resolve,
# the zips are streamed (never written on the SD card) and the disk work runs at low priority.
SCANS_DIR = "storage/scans"
SNAPSHOTS_DIR = "storage/snapshots"
STACKING_DIR = "storage/stacking"
ANIMATIONS_DIR = "storage/animations"


def _existing(section, *parts):
    return gallery.resolve_existing(section, os.path.join(*parts))


def _zip_name(prefix):
    return f'{prefix}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'


async def _delete(fulls):
    await gallery.run_low(gallery.delete_paths, fulls)


def _list_files(section, *parts):
    folder = _existing(section, *parts)
    return [f for f in os.listdir(folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.fits', '.ser', '.txt'))]


def _list_dirs(section, *parts):
    folder = _existing(section, *parts)
    return [f for f in os.listdir(folder) if os.path.isdir(os.path.join(folder, f))]


# ---------- SNAPSHOTS ----------- #
@app.get("/snapshots")
def get_snapshots():
    """
    List the snapshot images: [{name, thumbnail}].
    """
    if not os.path.exists(SNAPSHOTS_DIR):
        raise HTTPException(status_code=404, detail="Scan folder not found")
    images = [f for f in os.listdir(SNAPSHOTS_DIR) if f.lower().endswith(('.fits', '.png'))]
    return [{"name": image, "thumbnail": f"/snapshots/{image}"} for image in images]

@app.get("/download/snapshot/{image_name}")
def download_snapshot(image_name: str):
    return FileResponse(_existing('snapshots', image_name), filename=image_name)


# ----------- STACKING -------------#

@app.get("/stacking")
def get_stacking_folders():
    return [{"name": folder, "thumbnail": None} for folder in _list_dirs('stacking', '')]

@app.get("/stacking/{stacking_folder}")
def get_images_in_stacking(stacking_folder: str):
    return [{"name": image, "thumbnail": f"/stacking/{stacking_folder}/{image}"} for image in _list_files('stacking', stacking_folder)]

@app.get("/stacking/{stacking_folder}/{image_name}")
def get_image_in_stacking(stacking_folder: str, image_name: str):
    return FileResponse(_existing('stacking', stacking_folder, image_name))

@app.get("/download/stacking/{stacking_folder}/{image_name}")
def download_image_in_stacking(stacking_folder: str, image_name: str):
    return FileResponse(_existing('stacking', stacking_folder, image_name), filename=image_name)

@app.get("/download/stacking/multiple/{stacking_folder}/")
async def download_multiple_images_in_stacking(stacking_folder: str, files: List[str] = Query(...)):
    folder = _existing('stacking', stacking_folder)
    fulls = [_existing('stacking', stacking_folder, f) for f in files]
    return await gallery.download_response(fulls, _zip_name('stacking'), base=folder)

@app.get("/download/stacking/folders")
async def download_folders_in_stacking(folders: List[str] = Query(...)):
    # one zip with a folder per stacking (it used to be a zip of zips)
    fulls = [_existing('stacking', f) for f in folders]
    return await gallery.download_response(fulls, _zip_name('stacking'))

@app.delete("/stacking/selection")
async def delete_images_in_stacking(folders: List[str] = Query(...)):
    fulls = [_existing('stacking', f) for f in folders]
    await _delete(fulls)
    return {"message": "Folders deleted successfully"}


# --------------- ANIMATIONS ------------- #
@app.get("/animations")
def get_animations_folders():
    return [{"name": folder, "thumbnail": None} for folder in _list_dirs('animations', '')]

@app.get("/animations/{animation_folder}")
def get_images_in_animations(animation_folder: str):
    return [{"name": image, "thumbnail": f"/animations/{animation_folder}/{image}"} for image in _list_files('animations', animation_folder)]

@app.get("/animations/{animation_folder}/{image_name}")
def get_image_in_animations(animation_folder: str, image_name: str):
    return FileResponse(_existing('animations', animation_folder, image_name))

@app.get("/download/animations/{animation_folder}/{image_name}")
def download_image_in_animations(animation_folder: str, image_name: str):
    return FileResponse(_existing('animations', animation_folder, image_name), filename=image_name)

@app.get("/download/animations/multiple/{animation_folder}/")
async def download_multiple_images_in_animations(animation_folder: str, files: List[str] = Query(...)):
    folder = _existing('animations', animation_folder)
    fulls = [_existing('animations', animation_folder, f) for f in files]
    return await gallery.download_response(fulls, _zip_name('animations'), base=folder)

@app.delete("/animations/selection")
async def delete_images_in_animations(folders: List[str] = Query(...)):
    fulls = [_existing('animations', f) for f in folders]
    await _delete(fulls)
    return {"message": "Folders deleted successfully"}

@app.get("/download/animations/folders")
async def download_folders_in_animations(folders: List[str] = Query(...)):
    fulls = [_existing('animations', f) for f in folders]
    return await gallery.download_response(fulls, _zip_name('animations'))


# ------------ SCANS -------------#
@app.get("/dates")
def get_date_folders():
    return [{"name": date, "thumbnail": get_first_image_thumbnail(date)} for date in _list_dirs('scans', '')]

@app.get("/dates/{date_folder}")
def get_scan_folders(date_folder: str):
    return [{"name": scan, "thumbnail": get_first_image_thumbnail(date_folder, scan)} for scan in _list_dirs('scans', date_folder)]

@app.get("/dates/{date_folder}/scans/{scan_folder}")
def get_images_in_scan(date_folder: str, scan_folder: str):
    return [{"name": image, "thumbnail": f"/images/{date_folder}/{scan_folder}/{image}"} for image in _list_files('scans', date_folder, scan_folder)]

@app.get("/images/{date_folder}/{scan_folder}/{image_name}")
def get_image(date_folder: str, scan_folder: str, image_name: str):
    return FileResponse(_existing('scans', date_folder, scan_folder, image_name))

@app.get("/download/image/{date_folder}/{scan_folder}/{image_name}")
def download_image(date_folder: str, scan_folder: str, image_name: str):
    return FileResponse(_existing('scans', date_folder, scan_folder, image_name),
                        filename=scan_folder.replace('sunscan_', '')+'-'+image_name)

def get_first_image_thumbnail(date_folder, scan_folder=None):
    """Preview image of a date or scan folder, as a legacy /images/... URL."""
    preview = gallery._folder_preview(_existing('scans', date_folder, scan_folder or ''))
    if not preview:
        return None
    return f"/images/{os.path.relpath(preview, gallery.SECTIONS['scans'])}"

@app.get("/download/scans/multiple")
async def download_multiple_scans(folders: List[str] = Query(...)):
    fulls = [_existing('scans', f) for f in folders]
    return await gallery.download_response(fulls, _zip_name('scans'), base=gallery.SECTIONS['scans'])

@app.get("/download/scan/{date_folder}")
async def download_date(date_folder: str):
    folder = _existing('scans', date_folder)
    return await gallery.download_response([folder], f"{date_folder}.zip", base=folder)

@app.get("/download/date/{date_folder}/scan/{scan_folder}")
async def download_scan(date_folder: str, scan_folder: str):
    folder = _existing('scans', date_folder, scan_folder)
    return await gallery.download_response([folder], f"{scan_folder}.zip", base=folder)

@app.get("/download/date/{date_folder}/scans/multiple")
async def download_multiple_date_scans(date_folder: str, folders: List[str] = Query(...)):
    fulls = [_existing('scans', date_folder, f) for f in folders]
    return await gallery.download_response(fulls, _zip_name('scans'), base=gallery.SECTIONS['scans'])

@app.get("/download/date/{date_folder}/scan/{scan_folder}/images/multiple")
async def download_multiple_images(date_folder: str, scan_folder: str, images: List[str] = Query(...)):
    fulls = [_existing('scans', date_folder, scan_folder, i) for i in images]
    return await gallery.download_response(fulls, _zip_name('images'), base=gallery.SECTIONS['scans'])

@app.delete("/scans")
async def delete_date_folders(folders: List[str] = Query(...)):
    fulls = [_existing('scans', f) for f in folders]
    await _delete(fulls)
    return {"message": "Folders deleted successfully"}

@app.delete("/dates/{date_folder}/scans")
async def delete_scans(date_folder: str, folders: List[str] = Query(...)):
    fulls = [_existing('scans', date_folder, f) for f in folders]
    await _delete(fulls)
    return {"message": "Folders deleted successfully"}

@app.delete("/dates/{date_folder}/scans/{scan_folder}/images")
async def delete_images(date_folder: str, scan_folder: str, images: List[str] = Query(...)):
    fulls = [_existing('scans', date_folder, scan_folder, i) for i in images]
    await _delete(fulls)
    return {"message": "Images deleted successfully"}

@app.get("/dates/{date_folder}/scans/{scan_folder}/log")
def get_scan_log(date_folder: str, scan_folder: str):
    return FileResponse(_existing('scans', date_folder, scan_folder, "_scan_log.txt"), filename="_scan_log.txt")


def cleanup_zip_files(*directories):
    """
    Remove the zip files left in the storage directories by the former downloads,
    which were built on the SD card before being sent.
    """
    for directory in directories:
        if not os.path.isdir(directory):
            continue
        for file in os.listdir(directory):
            if file.endswith(".zip"):
                os.remove(os.path.join(directory, file))

cleanup_zip_files(STACKING_DIR, SCANS_DIR, ANIMATIONS_DIR)
# in the low priority pool: does not delay the startup
gallery.run_in_background(gallery.remove_empty_folders)

app.include_router(gallery.router)
