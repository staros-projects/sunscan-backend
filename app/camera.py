import time
import cv2
import numpy as np
from pathlib import Path
from libcamera import controls
from picamera2 import Picamera2, Controls
from picamera2.platform import Platform
from numba import jit

def getMaxAduValue(array):
    """
    Get the maximum ADU value from the given array.

    Args:
        array (numpy.ndarray): Input array of ADU values.

    Returns:
        float: Maximum ADU value in the array.
    """
    return np.max(array)

class IMX477Camera_CSI():
    def __init__(self):
        """Initialize the IMX477 camera with default settings."""
        self._picam2 = None
        self._cameraControls = None
        self._name = "IMX477"
        self._bin = False
        self._crop_height = 220
        self._max_adu = (0,0,0)
        self._monobin_mode = 0

    def init(self):
        """
        Initialize the camera with specific settings.

        Returns:
            tuple: Sensor size (width, height).
        """
        # load the default tuning file
        directory = Path(__file__).parent.absolute()
        # pisp is used on Raspberry Pi 5 and later
        is_pisp = Picamera2.platform == Platform.PISP
        tuning_file = "imx477_scientific_pisp.json" if is_pisp else "imx477_scientific.json"
        print(f"Load tuning_file: {tuning_file} in {directory}")
        tuning = Picamera2.load_tuning_file(tuning_file, directory)
        contrast_algo = Picamera2.find_tuning_algo(tuning, "rpi.contrast")
        gamma_curve = contrast_algo["gamma_curve"]
        contrast_algo["ce_enable"] = 0
        contrast_algo["gamma_curve"] = [0, 0, 65535, 65535]
        self._picam2 = Picamera2(tuning=tuning)

        
        mode = self._picam2.sensor_modes[3]
  
        self._sensor_mode = 3
        self._sensor_size = (mode['size'][0],mode['size'][1])
        video_config = self._picam2.create_video_configuration(buffer_count=10,sensor={'output_size': mode['size'], 'bit_depth':mode['bit_depth']}, raw={"format":"SRGGB12", 'size': mode['size']})
        self._picam2.configure(video_config)
        self._picam2.set_controls({'HdrMode': controls.HdrModeEnum.Off})
        self._picam2.start()
        time.sleep(2)

        return self._sensor_size
    
    def getName(self):
        """
        Get the name of the camera.

        Returns:
            str: Camera name.
        """
        return self._name
    
    def getMaxADU(self):
        """
        Get the maximum ADU values for each color channel.

        Returns:
            tuple: Maximum ADU values (red, green, blue).
        """
        return self._max_adu 
       
    def isColorCam(self):
        """
        Check if the camera is a color camera.

        Returns:
            bool: True if it's a color camera, False otherwise.
        """
        return True
    
    def capture(self, isRecording, withFlat=False):
        """
        Capture an image from the camera.

        Args:
            isRecording (bool): Whether the camera is currently recording.
            withFlat (bool, optional): Whether to apply flat field correction. Defaults to False.

        Returns:
            numpy.ndarray: Captured image as a 16-bit numpy array.
        """
        if not self._picam2:
            return  
        
        array = self._picam2.capture_array('raw').view(np.uint16)

        # Crop the image
        crop_x = 0
        if self._crop:
            array = array[self._crop_y:self._crop_y+self._crop_height,crop_x:crop_x+self._sensor_size[0]]
        else:
            array = array[self._preview_crop_y:self._preview_crop_y+self._preview_crop_height,crop_x:crop_x+self._sensor_size[0]] 

        offset = 3200
        bin = 2
        depth_conv = 4   

        if not isRecording:
            b = getMaxAduValue(array[:, 0::2][::2])-(offset/depth_conv/4)
            g = getMaxAduValue(array[:, 0::2][1::2])-(offset/depth_conv/4)
            r = getMaxAduValue(array[:, 1::2][1::2])-(offset/depth_conv/4)
            self._max_adu = (r,g,b)
        
        if self._monobin:
            match self._monobin_mode: # for each case : convert 12-bit values to 16 bit
                case 0:  # rgb monobin
                    array_16bit = (bin2dBayer(np.array(array), bin) * depth_conv) - offset 
                case 1:  # red layer
                    array_16bit = (array[:, 1::2][1::2] * depth_conv) - offset/4
                case 2:  # green layer
                    array_16bit = (array[:, 0::2][1::2]+array[:, 1::2][::2] * depth_conv) - offset/4
                case 3:  # blue layer
                    array_16bit = (array[:, 0::2][::2] * depth_conv) - offset/4
  
            array_16bit[array_16bit>65535]=65535
            frame = np.uint16(array_16bit)
        else:
            f = cv2.cvtColor(array * 16 , cv2.COLOR_BayerRGGB2RGB)
            height = f.shape[0]//4
            width = f.shape[1]//4
            r = cv2.resize(f, (width, height))
            frame = np.uint16(r)
        return frame
           
    def stop(self):
        """Stop the camera and release resources."""
        if not self._picam2:
            return
        self._picam2.stop()
        self._picam2.stop_encoder()
        self._picam2.close()

    def updateCameraControls(self, options):
        """
        Update camera controls based on the provided options.

        Args:
            options (dict): Dictionary containing camera control options.
        """
        if not self._picam2:
            return
        
        restart = False

        if self._cameraControls and self._cameraControls.ExposureTime >= 1000000.0:
            self._picam2.stop()
            restart = True
        
        self._cameraControls = Controls(self._picam2)
        self._cameraControls.AeEnable = 0 
        self._cameraControls.AwbEnable = False
        self._cameraControls.FrameDurationLimits = (int(150*1e3),60000000)
        self._cameraControls.ExposureTime = int(options['exposure_time'])
        self._cameraControls.AnalogueGain = options['gain']
        self._cameraControls.Contrast = 0.0
        self._cameraControls.Brightness = 0.0
        self._cameraControls.NoiseReductionMode = controls.draft.NoiseReductionModeEnum.Off

        self._picam2.set_controls(self._cameraControls)

        if restart:
            self._picam2.start()
            time.sleep(1)

        self._crop = options['crop']
        self._crop_y = options['crop_y']
        
        self._preview_crop_y = options['preview_crop_y']
        self._preview_crop_height = options['preview_crop_height']

        self._monobin = options['monobin']
        self._monobin_mode = options['monobin_mode']
        self._bin = options['bin']

@jit(nopython=True)
def bin2dBayer(a, K):
    """
    Perform 2D binning on a Bayer pattern array.

    Args:
        a (numpy.ndarray): Input Bayer pattern array.
        K (int): Binning factor.

    Returns:
        numpy.ndarray: Binned array.
    """
    m_bins = a.shape[0]//K
    n_bins = a.shape[1]//K
    return a.reshape(m_bins, K, n_bins, K).sum(3).sum(1)

@jit(nopython=True)
def clip_and_cast(arr):
    """
    Clip values to the range [0, 65535] and cast to uint16.

    Args:
        arr (numpy.ndarray): Input array.

    Returns:
        numpy.ndarray: Clipped and casted array as uint16.
    """
    arr = np.minimum(np.maximum(arr, 0), 65535)
    return arr.astype(np.uint16)




