
import time
import os
import json
from datetime import datetime, timezone
from pprint import *
from threading import Condition, Thread

try:
    from serfilesreader import Serfile
except:
    from serfilesreader.serfilesreader import Serfile

from ser_writer import SerWriter

class CameraController:
    """
    A class to control camera operations, including recording and image processing.
    """

    def __init__(self, camera, path='storage/scans/', filename_prefix='sunscan', stream='main'):
        """
        Initialize the CameraController with given parameters.

        :param camera: The camera object to control
        :param path: Path to store recorded scans
        :param filename_prefix: Prefix for recorded filenames
        :param stream: Stream identifier
        """
        self._gain = 1.0
        self._exposure_time = 110 * 1e3 # 160ms default
        self._crop = False
        self._monobin = True
        self._monobin_mode = 0 # 0 : RGB, 1 : R, 2: G, 3: B
        self._camera_status = "disonnected"
        self._camera = camera
        self._bin = False
        self._focus_assistant = False

        self._record = False

        self._ser_file = None
        self._path = path
        self._filename_prefix = filename_prefix
        self._stream = stream
        self._frame = []
        self._condition = Condition()
        self._running = True
        self._count = 0
        self._fc = 0
        
        self._serfile_object = None
        self._time_in_progress = 0
        self._t0 = 0
        self._final_ser_filename = None
        self._writer = None          # SerWriter of the recording in progress (owned by the capture thread)
        self._last_writer = None     # SerWriter of the last recording, may still be draining its queue
        self._normalize = 1
        self._max_visu_threshold = 256

    def _init(self):
        """
        Initialize camera settings and calculate crop parameters.
        """
        self._sensor_size = self._camera.init()
        self._crop_height = 260
        self._crop_y = int((self._sensor_size[1] / 2) - (self._crop_height / 2))
        self._preview_crop_height = 2000 
        self._preview_crop_y = int((self._sensor_size[1] / 2) - (self._preview_crop_height / 2))
        
    def _thread_func(self):  
        """
        Main thread function for continuous camera capture.
        """
        print('Thread camera is running...')
        while(self._running):
            self._frame = self._camera.capture(self._record)  # Capture a frame from the camera
            if self._record and not self.isInColorMode():  # Recording active and camera in mono mode
                if not self._writer:  # first frame of this recording
                    self._initSerFile()  # Initialize a new SER file
                    self._writer = SerWriter(self._serfile_object)  # dedicated writer thread + queue
                    self._t0 = time.time()  # Set the start time for recording
                self._time_in_progress = time.time()  # Update the current time
                # never write to the SD card from this thread: just enqueue the frame
                if self._writer.put(self._frame):
                    self._fc+=1  # Increment the frame count
            elif self._writer:
                # recording just stopped: hand the writer over, it drains its queue
                # and closes the file on its own thread (stopRecord waits for it)
                self._hand_over_writer()

       
    def _hand_over_writer(self):
        writer = self._writer
        if writer:
            writer.finish()
            self._last_writer = writer
            self._writer = None
            self._serfile_object = None

    def isRecording(self):
        """
        Check if the camera is currently recording.

        :return: Boolean indicating recording status
        """
        return self._record
                
    def start(self):
        """
        Start the camera controller thread and initialize camera.
        """
        self._running = True
        self._thread = Thread(target=self._thread_func, daemon=True)
        self._init()
        self._camera.updateCameraControls(self.getCameraControls())
        self._thread.start()
        self._camera_status = "connected" 
    
    def isInColorMode(self):
        """
        Check if the camera is in color mode.

        :return: Boolean indicating color mode status
        """
        return not self._monobin

    def toggleColorMode(self):
        """
        Toggle between color and monochrome modes.
        """
        self._monobin = not self._monobin
        self._camera.updateCameraControls(self.getCameraControls())

    def toggleBin(self):
        """
        Toggle binning mode.
        """
        self._bin = not self._bin
        self._camera.updateCameraControls(self.getCameraControls())

    def toggleMonoBinMode(self):
        """
        Cycle through monochrome binning modes (RGB, R, G, B).
        """
        self._monobin_mode = (self._monobin_mode + 1) % 4
        self._camera.updateCameraControls(self.getCameraControls())

    def isInBinMode(self):
        """
        Check if binning mode is active.

        :return: Boolean indicating binning mode status
        """
        return self._bin

    def getStatus(self):
        """
        Get the current camera status.

        :return: String representing camera status
        """
        return self._camera_status

    def getMaxADU(self):
        """
        Get the maximum ADU (Analog-to-Digital Unit) value of the camera.

        :return: Maximum ADU value
        """
        return self._camera.getMaxADU()

    def stop(self):
        """
        Stop the camera controller thread and release resources.
        """
        self._running = False
        self._record = False
        self._frame = None
        self._thread.join()
        # camera stopped while recording: still flush and close the SER file properly
        self._hand_over_writer()
        if self._last_writer:
            self._last_writer.wait(60)
        self._camera_status = 'disconnected'
        self._camera.stop()

    def setProfile(self, profile):
        """
        Configure the 1D profile computed by the camera in colour mode.

        :param profile: dict with 'enabled', 'columns' and 'x' (see POST /camera/profile/)
        """
        if profile['enabled']:
            self._camera.setProfileRequest(profile['x'], profile['columns'])
        else:
            self._camera.setProfileRequest(None, None)

    def getColorProfile(self):
        """
        Get the last 1D profile computed from the raw Bayer data in colour mode.

        :return: (x0, n, values) or None
        """
        return self._camera.getProfile()

    def getLastFrame(self):
        """
        Get the most recent captured frame.

        :return: The last captured frame
        """
        return self._frame

    def getCameraControls(self):
        """
        Get current camera control settings.

        :return: Dictionary of camera control parameters
        """
        c = { 'exposure_time': self._exposure_time, 
                'normalize': self._normalize,
                'gain': self._gain, 
                'crop': self._crop, 
                'record': self._record,
                'crop_y': self._crop_y,
                'max_visu_threshold': self._max_visu_threshold,
                'crop_height': self._crop_height,
                'preview_crop_y': self._preview_crop_y,
                'preview_crop_height': self._preview_crop_height,
                'monobin_mode': self._monobin_mode,
                'focus_assistant': self._focus_assistant,
                'bin': self._bin,
                'monobin':self._monobin, 
                'camera':self._camera.getName()}
        print(c)
        return c

    def setCameraControls(self, controls):
        """
        Set camera control parameters.

        :param controls: Object containing new control settings
        """
        self._exposure_time = controls.exp * 1e3
        self._gain = controls.gain
        self._max_visu_threshold = controls.max_visu_threshold
        self._camera.updateCameraControls(self.getCameraControls())

    def resetControls(self):
        """
        Reset camera controls to default values.
        """
        self._exposure_time = 100 * 1e3
        self._gain = 3.0
        self._camera.updateCameraControls(self.getCameraControls())
        
    def toggleCrop(self):
        """
        Toggle image cropping.
        """
        self._crop = not self._crop
        self._camera.updateCameraControls(self.getCameraControls())

    def toggleFocusAssistant(self):
            """
            Toggle focus assistant.
            """
            self._focus_assistant = not self._focus_assistant
            self._camera.updateCameraControls(self.getCameraControls())

    def toggleNormalize(self, mode):
        """
        Toggle image normalization.
        """
        self._normalize = mode
        #self._camera.updateCameraControls(self.getCameraControls())

    def normalizeMode(self):
        """
        Check if image normalization is active.

        :return: Boolean indicating normalization status
        """
        return self._normalize

    def focusAssistantIsOn(self):
        return self._focus_assistant

    def cameraIsCropped(self):
        """
        Check if image cropping is active.

        :return: Boolean indicating cropping status
        """
        return self._crop

    def getMaxVisuThreshold(self):
        return self._max_visu_threshold

    def setCropVerticalPosition(self, direction):
        """
        Adjust the vertical position of the crop area.

        :param direction: String indicating 'up' or 'down' movement
        """
        if direction =='up':
            self._crop_y -= 16
        else:
            self._crop_y += 16
        self._camera.updateCameraControls(self.getCameraControls())
        

    def startRecord(self):
        """
        Start recording frames.
        """
        self._serfile_object = None
        self._final_ser_filename = None
        self._last_writer = None
        self._fc = 0
        self._time_in_progress =0
        self._t0 =0  
        self._record = True

    def stopRecord(self):
        """
        Stop recording frames and print recording statistics.

        Blocks (with a timeout) until the capture thread has flushed and
        closed the SER file, so callers can safely read it afterwards.
        """
        self._record = False
        # 1. wait for the capture thread to hand the writer over (at most one frame period)
        deadline = time.time() + 10
        while self._writer is not None and time.time() < deadline:
            time.sleep(0.02)
        # 2. wait for the writer to drain its queue and close the file. The queue holds
        #    up to 30 s of frames, so allow more than that if the SD card is stalling.
        writer = self._last_writer
        if writer:
            if not writer.wait(90):
                print("WARNING: SER writer still busy after 90 s, scan file may be incomplete")
            print(f"ser writer : written={writer.written} dropped={writer.dropped} "
                  f"max_queue={writer.max_depth} max_write={writer.max_write_s*1000:.0f}ms error={writer.error}")
        print(self._fc,self._time_in_progress,self._t0)
        if self._time_in_progress > self._t0:
            print(f"frame count : {self._fc} time:{self._time_in_progress-self._t0} fps:{self._fc/(self._time_in_progress-self._t0)}")
        return self._final_ser_filename

    def _initSerFile(self):
        """
        Initialize a new SER file for recording frames.
        """
        # Generate timestamp and date strings for file naming in UTC
        now = datetime.now(timezone.utc)
        timestr = now.strftime("%Y_%m_%d-%H_%M_%S")
        date = now.strftime("%Y_%m_%d")
        
        # Create filename with prefix and timestamp
        filename = f"{self._filename_prefix}_{timestr}"
        
        # Create full path for the date directory
        full_path = os.path.join(self._path, date)
        if not os.path.exists(full_path):
            os.mkdir(full_path)
        
        # Add filename to the full path
        full_path = os.path.join(full_path, filename)
        
        # Set the final SER filename
        self._final_ser_filename = os.path.join(full_path, f"scan.ser")
        
        # Create the directory if it doesn't exist
        if not os.path.exists(full_path):
            os.mkdir(full_path)
        
        # Create a new Serfile object
        serfile_object = Serfile(self._final_ser_filename, NEW=True)
        fileid="SUNSCAN+IMX477"
        serfile_object.setFileID(fileid)
        
        # Set image width and height
        Width=self._sensor_size[0]
        serfile_object.setImageWidth(Width)
        Height=self._sensor_size[1]
        serfile_object.setImageHeight(Height)
        
        # Set pixel depth per plane (16-bit)
        serfile_object.setPixelDepthPerPlane(16)
        
        # Set observer, instrument, and telescope information
        serfile_object.setObserver('')
        serfile_object.setInstrument('sunscan')
        serfile_object.setTelescope('sunscan')
       
        # date et date UTC
        custom_ser_ts = get_custom_ts(now)
        serfile_object.setDateTime(custom_ser_ts)
        serfile_object.setDateTimeUTC(custom_ser_ts)
        
        # Store the Serfile object
        self._serfile_object = serfile_object
        
        # Write camera controls to a configuration file
        with  open(os.path.join(full_path, 'sunscan_conf.txt'), "w") as logfile:
            logfile.writelines(json.dumps(self.getCameraControls()))


def get_custom_ts(datetime):
    # Number of 100-nanoseconds between 0001-01-01T00:00:00 and 1970-01-01T00:00:00
    # This accounts for leap years and the Gregorian calendar reform
    epoch_offset_100ns = 621355968000000000

    # Convert the current timestamp to 100-nanoseconds since Unix epoch
    current_time_100ns = int(datetime.timestamp() * 1e7)

    # Adjust to custom epoch by adding the offset
    custom_epoch_time = epoch_offset_100ns + current_time_100ns 
    return int(custom_epoch_time  )  