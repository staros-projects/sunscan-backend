
import time
import os
import json
from datetime import datetime, timezone
from pprint import *
from threading import Condition, Thread



try : 
    from serfilesreader import Serfile
except: 
    from serfilesreader.serfilesreader import Serfile



class CameraController:
    def __init__(self, camera, path = 'storage/scans/', filename_prefix = 'sunscan', stream= 'main'):
        self._gain = 1.0
        self._exposure_time = 110 * 1e3 # 160ms default
        self._crop = False
        self._monobin = True
        self._monobin_mode = 0 # 0 : RGB, 1 : R, 2: G, 3: B
        self._camera_status = "disonnected"
        self._camera = camera
        self._bin = False

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
        self._normalize = True
        self._flat_enabled = False

    def _init(self):
        self._sensor_size = self._camera.init()
        self._crop_height = 280
        self._crop_y = int((self._sensor_size[1] / 2) - (self._crop_height / 2))
        self._preview_crop_height = 1600
        self._preview_crop_y = int((self._sensor_size[1] / 2) - (self._preview_crop_height / 2))
        
    def _thread_func(self):  
        print('thread cam ok')  
        while(self._running):
            self._frame = self._camera.capture(self._record, self._flat_enabled)
            if not self.isInColorMode():
                if self._record:
                    if not self._serfile_object: 
                        self._initSerFile()
                        self._t0 = time.time()
                    self._time_in_progress = time.time()
                    self._serfile_object.addFrame(self._frame)
                    self._fc+=1

       
    def isRecording(self):
        return self._record
                
    def start(self):
        self._running = True
        self._thread = Thread(target=self._thread_func, daemon=True)
        self._init()
        self._camera.updateCameraControls(self.getCameraControls())
        self._thread.start()
        self._camera_status = "connected" 
    
    def isInColorMode(self):
        return not self._monobin

    def toggleColorMode(self):
        self._monobin = not self._monobin
        self._camera.updateCameraControls(self.getCameraControls())

    def toggleFlat(self):
        self._flat_enabled = not self._flat_enabled
        self._camera.updateCameraControls(self.getCameraControls())

    def toggleBin(self):
        self._bin = not self._bin
        self._camera.updateCameraControls(self.getCameraControls())

    def toggleMonoBinMode(self):
        self._monobin_mode = (self._monobin_mode + 1) % 4
        self._camera.updateCameraControls(self.getCameraControls())

    def isInBinMode(self):
        return self._bin

    def isFlatEnable(self):
        return self._flat_enabled

    def getStatus(self):
        return self._camera_status

    def getMaxADU(self):
        return self._camera.getMaxADU()

    def stop(self):
        self._running = False
        self._frame = None
        self._thread.join()
        self._camera_status = 'disconnected'
        self._camera.stop()
        self._cropped_flat = []

    def getLastFrame(self):
        return self._frame

    def getCameraControls(self):
        c = { 'exposure_time': self._exposure_time, 
                'normalize': self._normalize,
                'gain': self._gain, 
                'crop': self._crop, 
                'record': self._record,
                'crop_y': self._crop_y,
                'crop_height': self._crop_height,
                'preview_crop_y': self._preview_crop_y,
                'preview_crop_height': self._preview_crop_height,
                'monobin_mode': self._monobin_mode,
                'bin': self._bin,
                'monobin':self._monobin, 
                'camera':self._camera.getName()}
        print(c)
        return c

    def setCameraControls(self, controls):
        self._exposure_time = controls.exp * 1e3
        self._gain = controls.gain
        self._camera.updateCameraControls(self.getCameraControls())

    def resetControls(self):
        self._exposure_time = 100 * 1e3
        self._gain = 3.0
        self._camera.updateCameraControls(self.getCameraControls())
        
    def toggleCrop(self):
        self._crop = not self._crop
        self._camera.updateCameraControls(self.getCameraControls())

    def toggleNormalize(self):
        self._normalize = not self._normalize
        self._camera.updateCameraControls(self.getCameraControls())

    def cameraIsNormalize(self):
        return self._normalize

    def cameraIsCropped(self):
        return self.cameraIsCropped

    def setCropVerticalPosition(self, direction):
        if direction =='up':
            self._crop_y -= 16
        else:
            self._crop_y += 16
        self._camera.updateCameraControls(self.getCameraControls())
        

    def startRecord(self):
        self._serfile_object = None
        self._fc = 1
        self._time_in_progress =0
        self._t0 =0  
        self._record = True

    def stopRecord(self):
        self._record = False
        print(self._fc,self._time_in_progress,self._t0)
        print(f"frame count : {self._fc} time:{self._time_in_progress-self._t0} fps:{self._fc/(self._time_in_progress-self._t0)}")

    def _initSerFile(self):
        timestr = time.strftime("%Y_%m_%d-%H_%M_%S")
        date = time.strftime("%Y_%m_%d")
        filename = f"{self._filename_prefix}_{timestr}"
        full_path = os.path.join(self._path, date)
        if not os.path.exists(full_path):
            os.mkdir(full_path)
        full_path = os.path.join(full_path, filename)
        self._final_ser_filename = os.path.join(full_path, f"scan.ser")
        if not os.path.exists(full_path):
            os.mkdir(full_path)
        serfile_object = Serfile(self._final_ser_filename, NEW=True)
        fileid="SUNSCAN+IMX219"
        serfile_object.setFileID(fileid)
        #Largeur, hauteur, nb de bits, nb de frame
        Width=self._sensor_size[0]
        serfile_object.setImageWidth(Width)
        Height=self._sensor_size[1]
        serfile_object.setImageHeight(Height)
        serfile_object.setPixelDepthPerPlane(16)
        #observateur, Intrument, telescope
        serfile_object.setObserver('')
        serfile_object.setInstrument('sunscan')
        serfile_object.setTelescope('sunscan')
        # date et date UTC
        ts =  datetime.now(timezone.utc).timestamp()
        serfile_object.setDateTimeUTC(int(ts))
        self._serfile_object = serfile_object
        with  open(os.path.join(full_path, 'sunscan_conf.txt'), "w") as logfile:
            logfile.writelines(json.dumps(self.getCameraControls()))


