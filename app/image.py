from abc import ABC

import cv2
import numpy as np
from numba import jit
from picamera2 import Picamera2, Platform

class AbstractImageRaw12BitColor(ABC):
    def __init__(self, array: np.ndarray):
        self.array = array
        self._red_channel = None
        self._green_channel = None
        self._blue_channel = None

    def _get_channel(self, channel_name: str, extract_method: callable) -> np.ndarray:
        if getattr(self, channel_name) is None:
            setattr(self, channel_name, extract_method())
        return getattr(self, channel_name)

    def channel_red(self):
        return self._get_channel('_red_channel', self.extract_red_channel)

    def channel_green(self):
        return self._get_channel('_green_channel', self.extract_green_channel)

    def channel_blue(self):
        return self._get_channel('_blue_channel', self.extract_blue_channel)

    def bin_2x2(self) -> np.ndarray:
        """
        Convert the image to a grayscale image using precomputed channels.

        Returns:
            numpy.ndarray: Converted grayscale image.
        """
        return bin2dBayer(np.array(self.array),2)

    def to_rgb_16bit(self):
        """
        Convert the Bayer pattern image to an RGB image.

        Returns:
            numpy.ndarray: Converted RGB image.
        """
        return cv2.cvtColor(self.array * 16, cv2.COLOR_BayerRGGB2RGB)
 
    def calculate_max_adu(self) -> tuple[int, int, int]:
        """
        Calculate the maximum ADU values for the red, green, and blue channels.
        each channel is a 12-bit integer value.

        Returns:
            tuple[int, int, int]: Maximum ADU values (red, green, blue).
        """
        red_max = np.max(self.channel_red())
        green_max = np.max(self.channel_green()/2)
        blue_max = np.max(self.channel_blue())
        return (red_max, green_max, blue_max)

    def crop(self, crop_x: int, crop_y: int, crop_width: int, crop_height: int) -> 'AbstractImageRaw12BitColor':
        """
        Crop the image to the specified width and height.

        Args:
            crop_x (int): The x-coordinate of the crop area.
            crop_y (int): The y-coordinate of the crop area.
            crop_width (int): The width of the crop area.
            crop_height (int): The height of the crop area.

        Returns:
            AbstractImageRaw12BitColor: Cropped image.
        """
        return self.__class__(self.array[crop_y:crop_y+crop_height, crop_x:crop_x+crop_width])
    

class ImageRawCameraHQ(AbstractImageRaw12BitColor):
    def __init__(self, array: np.ndarray):
        super().__init__(array)
    def extract_red_channel(self) -> np.ndarray:
        """
        Extract the red channel from the Bayer pattern array.

        Returns:
            numpy.ndarray: Extracted red channel.
        """
        return self.array[1::2, 1::2]
    def extract_green_channel(self) -> np.ndarray:
        """
        Extract the green channel from the Bayer pattern array.

        Returns:
            numpy.ndarray: Extracted green channel.
        """
        return self.array[0::2, 1::2] + self.array[1::2, 0::2]

    def extract_blue_channel(self) -> np.ndarray:
        """
        Extract the blue channel from the Bayer pattern array.

        Returns:
            numpy.ndarray: Extracted blue channel.
        """
        return self.array[0::2, 0::2]

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



