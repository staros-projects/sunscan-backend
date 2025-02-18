
import os 
import time
from astropy.io import fits
import imageio

from dedistor import write_images

def jstack(paths, required_files, observer):
    os.system("./jsolex/jsolex-scripting -s ./jsolex/stack.math -o ./jsolex/tmp/ -f fits")
    # Read FITS data
    with fits.open('./jsolex/tmp/stacked.fits') as hdul:
        data = hdul[0].data  # Assuming the image data is in the first HDU
    write_images('./jsolex/tmp', data, 'clahe', 3, '', observer)
    with fits.open('./jsolex/tmp/stacked_cont.fits') as hdul:
        data = hdul[0].data  # Assuming the image data is in the first HDU
    write_images('./jsolex/tmp', data, 'cont', 3, '', observer)
    pass

if __name__ == '__main__':
    jstack([], [], '')