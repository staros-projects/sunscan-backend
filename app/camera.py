import time
import cv2
import numpy as np
from pathlib import Path
from libcamera import controls
from picamera2 import Picamera2, Controls
from picamera2.platform import Platform
from numba import jit
from abc import ABC
from abc import abstractmethod
from image import AbstractImageRaw12BitColor, ImageRawCameraHQ

def getMaxAduValue(array):
    """
    Get the maximum ADU value from the given array.

    Args:
        array (numpy.ndarray): Input array of ADU values.

    Returns:
        float: Maximum ADU value in the array.
    """
    return np.max(array)

class BaseIMX477Camera_CSI(ABC):
    def __new__(cls):
        # prevent multiple instances of the camera
        if not hasattr(cls, 'instance'):
            cls.instance = super(BaseIMX477Camera_CSI, cls).__new__(cls)
        return cls.instance

    def __init__(self):
        """
        Initialize the IMX477 camera with default settings.

        Parameters:
            depth (int): The depth value for the camera data.

        Attributes:
            _picam2 (None): Placeholder for the Picamera2 object.
            _cameraControls (None): Placeholder for camera control settings.
            _name (str): The name of the camera model.
            _bin (bool): Flag indicating whether binning is enabled.
            _crop_height (int): The height of the crop area.
            _max_adu (tuple): Maximum Analog-to-Digital Units (ADU) values.
            _monobin_mode (int): Mode for monochrome binning.
            data_depth (int): The depth value for the camera data.
        """
        self._picam2 = None
        self._cameraControls = None
        self._name = "IMX477"
        self._bin = False
        self._crop_height = 260
        self._max_adu = (0,0,0)
        self._monobin_mode = 0
        self._profile_request = None  # (x, columns) of the 1D profile to compute in colour mode, None = off
        self._profile = None          # last colour profile (x0, n, 12-bit values)

        # pisp is used on Raspberry Pi 5 and later
        self.tuning_file_name = "imx477_scientific_pisp.json" if Picamera2.platform == Platform.PISP else "imx477_scientific.json"

        # The black level is 256 ADU (here we have voluntarily set the value to 200)
        # see more about camera black level https://www.strollswithmydog.com/pi-hq-cam-sensor-performance/
        self.black_level_camera = 200

    def init(self):
        """
        Initialize the camera with specific settings.

        Returns:
            tuple: Sensor size (width, height).
        """
        # load the default tuning file
        directory = Path(__file__).parent.absolute()
        
        print(f"Load tuning_file: { self.tuning_file_name} in {directory}")
        tuning = Picamera2.load_tuning_file( self.tuning_file_name, directory)
        contrast_algo = Picamera2.find_tuning_algo(tuning, "rpi.contrast")
        gamma_curve = contrast_algo["gamma_curve"]
        contrast_algo["ce_enable"] = 0
        contrast_algo["gamma_curve"] = [0, 0, 65535, 65535]
        self._picam2 = Picamera2(tuning=tuning)
        
        mode_index, mode = self._select_sensor_mode(self._picam2.sensor_modes)
        print("-----------------")
        print(f"Sensor mode [{mode_index}]: {mode}")
        print("-----------------")
  
        self._sensor_mode = mode_index
        self._sensor_size = (mode['size'][0],mode['size'][1])
        video_config = self._picam2.create_video_configuration(
            buffer_count=10,
            sensor={'output_size': mode['size'], 'bit_depth':mode['bit_depth']}, 
            raw={"format":"SRGGB12", 'size': mode['size']}
        )
        self._picam2.configure(video_config)
        self._picam2.set_controls({'HdrMode': controls.HdrModeEnum.Off})
        self._picam2.start()
        time.sleep(2)

        return self._sensor_size
    
    @staticmethod
    def _select_sensor_mode(sensor_modes, size=(4056, 3040), bit_depth=12):
        """
        Pick the full-resolution 12-bit sensor mode by its characteristics.

        The index of this mode is not stable: older libcamera/kernel versions expose
        4 modes (full-res 12-bit at index 3), newer ones expose more (10-bit and
        4056x2160 variants), so the mode must never be selected by index.

        Returns:
            tuple: (index, mode dict)
        """
        for i, m in enumerate(sensor_modes):
            if tuple(m['size']) == size and m.get('bit_depth') == bit_depth:
                return i, m
        # Fallback: largest area, then highest bit depth
        i, m = max(enumerate(sensor_modes),
                   key=lambda im: (im[1]['size'][0] * im[1]['size'][1], im[1].get('bit_depth', 0)))
        print(f"WARNING: sensor mode {size} {bit_depth}-bit not found, falling back to {m}")
        return i, m

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

    def process_monobin_mode(self, image: AbstractImageRaw12BitColor, monobin_mode):
        match monobin_mode: 
            case 0:  # rgb monobin
                array = (image.bin_2x2().astype(np.int32) - (self.black_level_camera * 4)) 
            case 1:  # red layer
                array = (image.channel_red().astype(np.int32) - self.black_level_camera)
            case 2:  # green layer
                array = (image.channel_green().astype(np.int32) - self.black_level_camera)
            case 3:  # blue layer
                array = (image.channel_blue().astype(np.int32) - self.black_level_camera)
        # signed arithmetic: a pixel below the black level must clamp to 0, not wrap around to white
        return np.clip(array.astype(np.int32), 0, None) * 4 # 16 bits conversion

    def setProfileRequest(self, x, columns):
        """
        Enable (columns >= 1) or disable (columns None) the 1D profile computed in colour mode.

        Args:
            x (int | None): Centre column in mono frame coordinates, None = centre of the frame.
            columns (int | None): Number of mono columns to average, None to disable.
        """
        self._profile_request = None if columns is None else (x, columns)
        self._profile = None

    def getProfile(self):
        """
        Get the last 1D profile computed in colour mode.

        Returns:
            tuple | None: (x0, n, values) with 12-bit values, one per mono frame row.
        """
        return self._profile

    def _color_profile(self, image: AbstractImageRaw12BitColor, x, columns):
        """
        1D profile from the raw Bayer data, before demosaicing and resizing, computed exactly
        like the mono profile in monobin mode 0 but on the requested band of columns only.
        x and columns are in mono frame coordinates (1 mono column = 2 Bayer columns).
        """
        width = image.array.shape[1] // 2
        n = min(columns, width)
        x0 = min(max((x if x is not None else width // 2) - n // 2, 0), width - n)
        band = image.crop(2 * x0, 0, 2 * n, image.array.shape[0])  # even width, aligned on the Bayer matrix
        mono = self.process_monobin_mode(band, monobin_mode=0)
        mono[mono > 65535] = 65535
        # same 16 -> 12 bits scaling and rounding as the mono profile in main.py
        values = (mono.sum(axis=1) + n * 8) // (n * 16)
        return x0, n, values

    def capture(self, isRecording):
        """
        Capture an image from the camera.

        Args:
            isRecording (bool): Whether the camera is currently recording.

        Returns:
            numpy.ndarray: Captured image as a 12-bit numpy array.
        """
        if not self._picam2:
            return  
        
        array = self.capture_raw_image()
        
        image = ImageRawCameraHQ(array)

        # Crop the image        
        if self._crop:
            image = image.crop(0, self._crop_y, self._sensor_size[0], self._crop_height)
        else:
            image = image.crop(0, self._preview_crop_y, self._sensor_size[0], self._preview_crop_height)

        if not isRecording:
            self._max_adu = image.calculate_max_adu()

        if self._monobin:
            # mono image output
            array_16bit = self.process_monobin_mode(image, monobin_mode=self._monobin_mode)
            array_16bit[array_16bit>65535]=65535  # clip values to 16-bit
            frame = np.uint16(array_16bit)  # cast to uint16

        else:
            # color image output
            request = self._profile_request
            if request is not None and not isRecording:
                self._profile = self._color_profile(image, *request)
            f = image.to_rgb_16bit()
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


class IMX477Camera_CSI_rpi4(BaseIMX477Camera_CSI):
    def __init__(self):
        super().__init__()

    def capture_raw_image(self):
        """
        Capture a raw image from the camera.

        Returns:
            numpy.ndarray: Captured raw image as a 12-bit numpy array.
        """
        return self._picam2.capture_array('raw').view(np.uint16)



class IMX477Camera_CSI_rpi5(BaseIMX477Camera_CSI):
    def __init__(self):
        super().__init__()

    def capture_raw_image(self):
        """
        Capture a raw image from the camera and extract the 12 most significant bits.

        Returns:
            numpy.ndarray: Captured raw image as a 12-bit numpy array.
        """
        raw_array = self._picam2.capture_array('raw').view(np.uint16)

        # Extract the 12 most significant bits (>> on uint16 already yields uint16)
        return raw_array >> 4



def factory_imx477_camera_csi() -> BaseIMX477Camera_CSI:
    """
    Factory function to create an IMX477 camera object based on the platform.

    Returns:
        BaseIMX477Camera_CSI: IMX477 camera object.
    """
    if Picamera2.platform == Platform.PISP:
        print("Create Camera object for Raspberry Pi 5 and later")
        return IMX477Camera_CSI_rpi5()
    else:
        print("Create Camera object for Raspberry Pi 4")
        return IMX477Camera_CSI_rpi4()
