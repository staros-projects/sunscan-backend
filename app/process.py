import os
import cv2
import json
import datetime
import numpy as np
from astropy.io import fits
from Inti_recon import solex_proc 
from Inti_recon2 import solex_proc2
from PIL import Image, ImageDraw, ImageFont, ImageChops
from datetime import datetime
from helium import process_helium, create_circular_mask, blend_images
from hepsilon import HEpsilonPlanes
from mapping import create_solar_planisphere
import config as cfg

# Steps reported to the frontend while a scan is processed: (key, weight).
# The weight is the rough share of the total processing time, it sets how much
# of the 0-100 % range the step covers. The keys are translated by the frontend.
PROGRESS_STEPS_RECON = [('reading_scan', 30), ('building_disk', 15), ('correcting_geometry', 30)]
PROGRESS_STEPS_IMAGES = [('image_surface', 12), ('image_continuum', 3), ('image_prominences', 3)]
PROGRESS_STEP_DOPPLER = ('image_doppler', 12)
PROGRESS_STEP_HEPSILON = ('image_hepsilon', 6)
PROGRESS_STEPS_HELIUM = [('image_helium', 25)]


class ProgressReporter:
    """
    Turn "fraction done of a step" into a global percentage and hand it to a notify function.

    Args:
        notify (function): notify(step, percent), or None to report nothing.
        steps (list): Ordered (key, weight) list of the steps the processing goes through.
    """
    def __init__(self, notify, steps):
        self.notify = notify
        self.ranges = {}
        self.last = None
        total = sum(weight for key, weight in steps)
        start = 0
        for key, weight in steps:
            self.ranges[key] = (100 * start / total, 100 * (start + weight) / total)
            start += weight

    def __call__(self, step, fraction=0.0):
        if self.notify is None or step not in self.ranges:
            return
        start, end = self.ranges[step]
        # 100 % is only reached with the 'completed' status
        percent = min(int(start + (end - start) * min(max(fraction, 0.0), 1.0)), 99)
        if (step, percent) != self.last:
            self.last = (step, percent)
            try:
                self.notify(step, percent)
            except Exception as e:
                # Reporting the progress must never break the processing
                print("error progress", e)


def process_scan(callback, scan, progress=None):
    """
    Process a solar scan from a .ser file and generate various images.

    Args:
        callback (function): Called at the end with (serfile, 'completed') or
            (serfile, 'failed', error key, error message).
        scan (Scan): Scan to process and processing options.
        progress (function): Optional, called with (step key, global percent) while processing.

    Returns:
        None
    """
    serfile=scan.filename
    WorkDir = os.path.dirname(serfile)
    dopcont=scan.dopcont
    autocrop=scan.autocrop
    autocrop_size=scan.autocrop_size
    noisereduction=scan.noisereduction 
    dopplerShift=scan.doppler_shift
    contShift=scan.continuum_shift
    contSharpLevel=scan.cont_sharpen_level
    surfaceSharpLevel=scan.surface_sharpen_level
    proSharpLevel=scan.pro_sharpen_level
    offset=scan.offset
    observer=scan.observer
    advanced=scan.advanced
    doppler_color=scan.doppler_color
    process_doppler=scan.process_doppler
      
    if not os.path.exists(serfile):
        return callback(serfile, 'failed', 'file_not_found', serfile)

    print(f"process_scan {serfile}")

    # Create the three subdirectories
    subrep=os.path.join(WorkDir,'BASS2000')
    if not os.path.isdir(subrep):
        os.makedirs(subrep)
    subrep=os.path.join(WorkDir,'Clahe')
    if not os.path.isdir(subrep):
        os.makedirs(subrep)
    subrep=os.path.join(WorkDir,'Complements')
    if not os.path.isdir(subrep):
        os.makedirs(subrep)

    #Les param�tres sont les suivants, que je sugg�re d�adopter : d�calage par rapport � la raie Fe I = +74 pixiels
    #Decalages pour le continuum par rapport � la raie He I : -11 pixels et +6 pixels.
    helium = True if advanced == 'heI' else False

    if helium:
        offset = 74
        noisereduction = True
        contShift = 11
        dopplerShift = -6

    Shift = [0, dopplerShift, contShift, offset, 0.0, 0.0]
    Flags =  {'DOPFLIP': False, 
            'SAVEPOLY': False, 
            'FLIPRA': True, 
            'FLIPNS': True, 
            'FORCE_FREE_MAGN': False, 
            'Autocrop': autocrop, 
            'FREE_AUTOPOLY': offset != 0, 
            'ZEE_AUTOPOLY': False, 
            'NOISEREDUC': noisereduction, 
            'DOPCONT': process_doppler, 
            'VOL': False, 
            'POL': False, 
            'WEAK': offset != 0, 
            'RTDISP': False, 
            'ALLFITS': False, 
            'sortie': False,
            'FITS3D': False, 
            'FORCE': False}

    ratio_fixe=0
    ang_tilt=0
    poly=[0.0,0.0,0.0]
    data_entete= ['', '', 0.0, 0.0, '', 0, 'Manual']
    ang_P=0.0
    solar_dict={}
    param=[0,0,autocrop_size,autocrop_size, 0,0]

    color = None
    tag_files = [f for f in os.listdir(WorkDir) if f.startswith('tag_')]
    if tag_files:
        tag_value = tag_files[0].split('_', 1)[-1]  # Extract tag value after 'tag_'
        color = tag_value
        print('auto extracted line tag :'+color)

    # A Ca II H scan also holds the H epsilon line in its red wing: two more planes are rebuilt for it,
    # only if the spectrum confirms the line since the tag alone can't be trusted
    hepsilon = HEpsilonPlanes() if color == 'caIIH' and not helium else None

    # Steps this processing goes through, to report its progress
    steps = list(PROGRESS_STEPS_RECON)
    if helium:
        steps += PROGRESS_STEPS_HELIUM
    else:
        steps += PROGRESS_STEPS_IMAGES
        if dopcont and process_doppler:
            steps.append(PROGRESS_STEP_DOPPLER)
        if hepsilon is not None:
            steps.append(PROGRESS_STEP_HEPSILON)
    report = ProgressReporter(progress, steps)

    # Error key sent to the frontend if the processing fails, depends on how far it went
    error = 'reconstruction_failed'
    try:
        # Process the SER file using solex_proc function
        frames, header, cercle, range_dec, geom, polynome = solex_proc(serfile, Shift, Flags, ratio_fixe, ang_tilt, poly, data_entete, ang_P, solar_dict, param, progress=report, extra_shifts=hepsilon)
        error = 'image_generation_failed'

        # The H epsilon planes come last: the images below expect the usual frames only
        hepsilon_frames = []
        if hepsilon is not None and hepsilon.shifts:
            hepsilon_frames = frames[-len(hepsilon.shifts):]
            frames = frames[:-len(hepsilon.shifts)]

        header = update_header(WorkDir, header, observer)

        if helium:
            report('image_helium')
            result_image = process_helium(WorkDir, frames, cercle, header, observer, apply_watermark_if_enable, Colorise_Image)


        else:
            # Create and save surface image
            report('image_surface')
            raw = create_surface_image(WorkDir, frames, helium, surfaceSharpLevel, header, observer, color, cercle)
            # Create and save continuum image
            report('image_continuum')
            create_continuum_image(WorkDir, frames, contSharpLevel, header, observer)
            # Create and save prominence (protus) image
            report('image_prominences')
            create_protus_image(WorkDir, cv2.flip(raw,0), cercle,proSharpLevel, header, observer, 'sunscan_protus')
            # If doppler contrast is enabled, create and save doppler image
            print('doppler:', dopcont)
            if dopcont and process_doppler:
                report('image_doppler')
                create_doppler_image(WorkDir, frames, cercle, header, observer, doppler_color)
            if hepsilon_frames:
                report('image_hepsilon')
                try:
                    create_hepsilon_images(WorkDir, hepsilon_frames, cercle, surfaceSharpLevel, header, observer)
                except Exception as e:
                    # H epsilon comes on top of the Ca II H images, it must never fail the scan
                    print("error hepsilon", e)
        # Call the callback function to indicate successful completion
        callback(serfile, 'completed')
    except Exception as e:
        # If an error occurs during processing, print an error message
        print("error solex proc", e)
        # Call the callback function to indicate failure
        callback(serfile, 'failed', error, str(e))

def update_header(path, header, observer):
    if os.path.exists(os.path.join(path, 'sunscan_conf.txt')):
        d = open(os.path.join(path, 'sunscan_conf.txt'))
        try:
            c = json.load(d)
            header['EXPTIME']=int(c['exposure_time']/1000)
            header['GAIN']=c['gain']
            header['OBSERVER']=observer
            header['INSTRUME']='SUNSCAN'
            header['TELESCOP']='SUNSCAN'
            header['OBJNAME']='Sun'
        except Exception as e:
            print("error update header", e)
    return header


def sharpenImage(image, level):
    """
    Apply multiple sharpening operations to an image.

    Args:
        image (numpy.ndarray): Input image.

    Returns:
        numpy.ndarray: Sharpened image.
    """
    for i in range(0,level):
        # Apply Gaussian blur with a 9x9 kernel and sigma of 10.0
        gaussian_3 = cv2.GaussianBlur(image, (9,9), 10.0)
        # Sharpen the image by subtracting the blurred image
        image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)

        if (i <2):
            # Apply Gaussian blur with a 3x3 kernel and sigma of 8.0
            gaussian_3 = cv2.GaussianBlur(image, (3,3), 8.0)
            # Sharpen the image one more time
            image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)
    return image

def create_surface_image(wd, frames, helium, level, header, observer, color, cercle):
    """
    Create and save various surface images of the sun.

    Args:
        wd (str): Working directory to save images.
        frames (list): List of image frames.

    Returns:
        None
    """
    # -- RAW --
    # Calculate lower threshold (45th percentile)
    Seuil_bas=0
    # Calculate upper threshold (99.9999th percentile * 1.20)
    Seuil_haut=np.percentile(frames[0],99.9999)*1.20
    # Apply thresholds and scale to 16-bit range
    raw=(frames[0]-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
    # Set negative values to 0
    raw[raw<0]=0
    # Convert to 16-bit unsigned integer
    raw=np.array(raw, dtype='uint16')
    # Flip the image vertically
    raw=cv2.flip(raw,0)

    # Save raw image as PNG and JPG
    cv2.imwrite(os.path.join(wd,'sunscan_raw.png'),raw)
    cv2.imwrite(os.path.join(wd,'sunscan_raw.jpg'),raw/256)
    save_as_fits(os.path.join(wd,'sunscan_raw.fits'), raw, header)


    # -- CLAHE --
    # Create CLAHE object (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
    # Apply CLAHE to the first frame
    cl1 = clahe.apply(frames[0])
    
    # Calculate new thresholds for CLAHE image
    Seuil_bas=0
    Seuil_haut=np.percentile(cl1,99.9999)*1.05

    # Apply thresholds and scale to 16-bit range
    cc=(cl1-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
    # Set negative values to 0
    cc[cc<0]=0
    # Convert to 16-bit unsigned integer
    cc=np.array(cc, dtype='uint16')
    # Flip the image vertically
    cc=cv2.flip(cc,0)

    # Apply sharpening to the image
    cc = sharpenImage(cc, level)
   
    # Save CLAHE image as PNG and JPG
    try:
        cv2.imwrite(os.path.join(wd,'sunscan_clahe.jpg'), apply_watermark_if_enable(cc//256,header,observer))
        cv2.imwrite(os.path.join(wd,'sunscan_clahe.png'),cc)
        create_solar_planisphere(os.path.join(wd,'sunscan_clahe.png'))
        save_as_fits(os.path.join(wd,'sunscan_clahe.fits'), cc, header)
        # Create and save a smaller preview image
        ccsmall = cv2.resize(cc/256,  (0,0), fx=0.4, fy=0.4) 
        cv2.imwrite(os.path.join(wd, 'sunscan_preview.jpg'),ccsmall)
        print(os.path.join(wd, 'sunscan_preview.jpg'))
    except Exception as e:
        print(e)

    Colorise_Image(color, cc, wd, header, observer)

    tag_enabled_for_negative = ['halpha', 'hbeta', 'hgamma', 'hdelta', 'hepsilon']
    
    if color in tag_enabled_for_negative:
        create_negative_surface_image(wd, cc, cercle, header, observer)
    return raw

def apply_watermark_if_enable(frame, header, observer, desc=''):
    print('- watermark : ', observer, desc)
    if observer == ' ':
        return frame
    # Ensure the frame is in uint8 format
    if frame.dtype != np.uint8:
        frame = frame.astype(np.uint8)  # Normalize if in float

    formatted_date = ''
    if header and 'DATE-OBS' in header and header['DATE-OBS']:
        try:
            # Convert to datetime object using strptime
            datetime_obj = datetime.strptime(header['DATE-OBS'][:23], '%Y-%m-%dT%H:%M:%S.%f')
            # Convert to desired format (YYYY-MM-DD HH:MM:SS)
            formatted_date = datetime_obj.strftime('%Y-%m-%d %H:%M:%S')+' UT'
        except Exception as e:
            print(e)

    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image) 
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Regular.ttf", 30)  # Use a specific font if available
    text_position = get_text_position(image)
    desc = ' - ' + desc if desc else ''
    if desc == '' and isinstance(header, str) and header != '':
        desc = header
    draw.text(text_position, formatted_date+desc, fill="white", font=font)

    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Baumans-Regular.ttf", 40)  # Use a specific font if available
    draw.text(get_text_position(image, 115), 'SUNSCAN', fill="white", font=font)
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Regular.ttf", 20)  # Use a specific font if available
    draw.text(get_text_position(image, 73), observer, fill="white", font=font)
    return np.array(image)

def get_text_position(image, padding_from_bottom=50, padding_from_left=20):
     # Get the image dimensions to position the text in the bottom-left corner
    width, height = image.size
    # Position the text in the bottom-left corner with some padding
    return (padding_from_left, height - padding_from_bottom)  # Padding of Npx from the left and bottom

def create_negative_surface_image(wd, cc, cercle, header, observer, return_image=False):
    """
    Negative surface with bright prominences and clean black sky.
    - Surface: stretched + inverted
    - Prominences: stretched separately
    - Outside sky: forced to black
    """
    height, width = cc.shape
    feather_width = 5

    # Disk geometry
    x0, y0 = cercle[0], cercle[1]
    center = (x0, y0)
    disk_limit_percent = 0.002
    wi, he = int(cercle[2]), int(cercle[3])
    r = min(wi, he)
    r = int(r - round(r * disk_limit_percent))-5 

    # --- Masks ---
    mask_disk_smooth = create_circular_mask((height, width), center, r-5, feather_width).astype(np.float32)
    mask_disk_smooth = np.clip(mask_disk_smooth, 0, 1)

    y, x = np.ogrid[:height, :width]
    dist = np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2)
    mask_disk_hard = (dist <= r).astype(np.uint8)
    mask_prom_hard = 1 -  (dist <= r-10).astype(np.uint8)

    # --- Stretch prominences ---
    protu = cc.astype(np.float64) * mask_prom_hard
    valid_p = protu[protu > 0]
    protu_stretched = np.zeros_like(protu)
    if valid_p.size > 0:
        low_p = np.percentile(valid_p, 20)
        high_p = np.percentile(valid_p, 97)
        if high_p > low_p:
            scaled = (protu[protu > 0] - low_p) * (65535 / (high_p - low_p))
            protu_stretched[protu > 0] = np.clip(scaled, 0, 65535)
        gamma_p = 1.3
        protu_norm = np.clip(protu_stretched / 65535.0, 0, 1)
        protu_stretched = np.power(protu_norm, gamma_p) * 65535

    # --- Stretch surface ---
    surface = cc.astype(np.float64) * mask_disk_hard
    valid_s = surface[surface > 0]
    surface_stretched = np.zeros_like(surface)
    if valid_s.size > 0:
        low_s = np.percentile(valid_s, 0.085)
        high_s = np.percentile(valid_s, 99.9)
        if high_s > low_s:
            scaled = (surface[surface > 0] - low_s) * (65535 / (high_s - low_s))
            surface_stretched[surface > 0] = np.clip(scaled, 0, 65535)

    # --- Negative surface ---
    surface_negative = 65535 - surface_stretched

    # --- Blend inline ---
    surface_f = surface_negative.astype(np.float32)
    protu_f = protu_stretched.astype(np.float32)
    mask_f = mask_disk_smooth.astype(np.float32)

    blended_image = surface_f * mask_f + protu_f * (1.0 - mask_f)

    # Convert to uint16
    final_image = np.clip(blended_image, 0, 65535).astype(np.uint16)

    # --- Save or return ---
    if return_image:
        return final_image

    filename = 'sunscan_negative'
    cv2.imwrite(os.path.join(wd, filename + '.jpg'),
                apply_watermark_if_enable(final_image // 256, header, observer))
    cv2.imwrite(os.path.join(wd, filename + '.png'), final_image)
    save_as_fits(os.path.join(wd, filename + '.fits'), final_image, header)


def create_continuum_image(wd, frames, level, header, observer):
    """
    Create and save a continuum image of the sun.

    Args:
        wd (str): Working directory to save images.
        frames (list): List of image frames.

    Returns:
        None
    """
    if len(frames) >3 or len(frames) == 2:
        clahe = cv2.createCLAHE(clipLimit=0.8, tileGridSize=(2,2))
        cl1 = clahe.apply(frames[len(frames)-1])

        Seuil_bas=np.percentile(cl1, 30)
        Seuil_haut=np.percentile(cl1,99.9999)*1.05

        cc=(cl1-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
        cc[cc<0]=0
        cc=np.array(cc, dtype='uint16')

        cc=cv2.flip(cc,0)

        # clahe
        clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
        cl1 = clahe.apply(cc)

        cc = sharpenImage(cc, level)

        # save as png
        cv2.imwrite(os.path.join(wd,'sunscan_cont.jpg'),apply_watermark_if_enable(cc//256,header,observer, 'Continuum'))
        cv2.imwrite(os.path.join(wd,'sunscan_cont.png'),cc)
        create_solar_planisphere(os.path.join(wd,'sunscan_cont.png'))
        # cv2.imshow('clahe',cc)
        # cv2.waitKey(10000)

def create_protus_image(wd, raw, cercle, level, header, observer, name=None):
    """
    Create and save a prominence (protus) image of the sun.
    """
    height, width = raw.shape
    

    print(name)
    x0=cercle[0]
    y0=cercle[1]
    center = (x0, y0)
    # Create the circular mask
    disk_limit_percent=0.002
    wi=int(cercle[2])
    he=int(cercle[3])
    r=(min(wi,he))
    r=int(r- round(r*disk_limit_percent))-4
    
    mask = create_circular_mask((height, width), center, r, 3)

    # Blend the images
    blended_image = blend_images(raw, np.zeros(raw.shape), mask)
    
    Threshold_Upper = np.percentile(blended_image, 99.9999) * 0.5  # Preference for high contrast
    Threshold_low = 0
    img_seuil = seuil_image_force(blended_image, Threshold_Upper, Threshold_low)
    
    frame_contrasted3 = np.array(img_seuil, dtype='uint16')
    frame_contrasted3 = cv2.flip(frame_contrasted3, 0)  # Flip image vertically

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
    cl1 = clahe.apply(frame_contrasted3)
    
    Seuil_bas = np.percentile(cl1, 60)  # Lower threshold
    Seuil_haut = np.percentile(cl1, 99.9999) * 1.05  # Upper threshold

    cc = (cl1 - Seuil_bas) * (65000 / (Seuil_haut - Seuil_bas))  # Apply contrast
    cc[cc < 0] = 0  # Remove negative values
    cc = np.array(cc, dtype='uint16')

    # Save as PNG and JPG
    if name:
        cv2.imwrite(os.path.join(wd, name+'.jpg'), apply_watermark_if_enable(cc//256,header,observer))
        cv2.imwrite(os.path.join(wd, name+'.png'), cc)
    else:
        return cc

def create_hepsilon_images(wd, frames, cercle, level, header, observer):
    """
    Create and save the H epsilon images out of the two extra planes of a Ca II H scan.

    Args:
        wd (str): Working directory to save images.
        frames (list): H epsilon plane, then the plane at the same distance on the other side of the Ca II H core.
        cercle (list): Centre and radii of the solar disk.
        level (int): Sharpening level of the surface image.

    Returns:
        None
    """
    desc = cfg.LineDict['hepsilon']

    # -- SURFACE --
    # Same processing as the CLAHE surface image
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
    cl1 = clahe.apply(frames[0])
    Seuil_haut=np.percentile(cl1,99.9999)*1.05
    cc=np.clip(cl1*(65000/Seuil_haut), 0, 65535)
    cc=np.array(cc, dtype='uint16')
    cc=cv2.flip(cc,0)
    cc = sharpenImage(cc, level)

    cv2.imwrite(os.path.join(wd,'sunscan_hepsilon.jpg'), apply_watermark_if_enable(cc//256,header,observer, desc))
    cv2.imwrite(os.path.join(wd,'sunscan_hepsilon.png'),cc)
    save_as_fits(os.path.join(wd,'sunscan_hepsilon.fits'), cc, header)
    Colorise_Image('hepsilon', cc, wd, header, observer, planisphere=False, filename='sunscan_hepsilon_color')

    # -- PROMINENCES --
    wi=int(cercle[2])
    he=int(cercle[3])
    r=min(wi,he)
    if r <= 0:
        # no disk found, as for a partial scan
        return
    # The stray light halo is the same in both planes, and so is the light of the limb since they are at the
    # same level in the Ca II H wing, but only the first one holds the emission of the prominences:
    # their difference removes the halo, which hides them in the H epsilon plane alone
    diff = frames[0].astype(np.float64) - frames[1].astype(np.float64)
    diff = cv2.GaussianBlur(diff, (0,0), 1.5)

    height, width = diff.shape
    y, x = np.ogrid[:height, :width]
    dist = np.sqrt((x - cercle[0])**2 + (y - cercle[1])**2)
    # Noise of the sky around the disk, not further: the corners of the image are filled with a constant.
    # The median deviation ignores the prominences
    sky = diff[(dist > r*1.05) & (dist < r*1.3)]
    noise = 1.4826 * np.median(np.abs(sky - np.median(sky)))
    Seuil_bas = np.median(sky) + 4*noise
    # The chromosphere makes a thin bright ring at the limb: the upper threshold is taken further out
    around = diff[(dist > r*1.02) & (dist < r*1.3)]
    Seuil_haut = max(np.percentile(around, 99.99), Seuil_bas + 10*noise)

    protus = np.clip((diff-Seuil_bas)/(Seuil_haut-Seuil_bas), 0, 1)
    protus = np.power(protus, 0.7)*65535
    # Same mask of the disk as the prominence image
    r=int(r- round(r*0.002))-4
    mask = create_circular_mask((height, width), (cercle[0], cercle[1]), r, 3)
    protus = blend_images(protus, np.zeros(protus.shape), mask)
    protus = cv2.flip(protus, 0)

    cv2.imwrite(os.path.join(wd,'sunscan_hepsilon_protus.jpg'), apply_watermark_if_enable(protus//256,header,observer, desc))
    cv2.imwrite(os.path.join(wd,'sunscan_hepsilon_protus.png'), protus)

def create_doppler_image(wd, frames, cercle, header, observer, doppler_color):
    """
    Create and save a Doppler image of the sun.

    Args:
        wd (str): Working directory to save images.
        frames (list): List of image frames.

    Returns:
        None
    """
    if len(frames) >3:
        try :
            img_doppler=np.zeros([frames[1].shape[0], frames[1].shape[1], 3],dtype='uint8')

            f1=np.array(frames[1], dtype="float64")
            f2=np.array(frames[2], dtype="float64")
            moy=np.array(((f1+f2)/2), dtype='float64') 
            # on equilibre les plans
            lum_roi1 = get_lum_moyenne(f1) # calcul moyenne au centre sur zone de 200x200
            lum_roi2 = get_lum_moyenne(f2)
            lum_roimoy = get_lum_moyenne(moy)
            ratio_l1 = lum_roimoy/lum_roi1
            ratio_l2 = lum_roimoy/lum_roi2
            frames[2] = np.clip(f2*ratio_l2, 0, 65535).astype( np.uint16)
            frames[1] = np.clip(f1*ratio_l1, 0, 65535).astype( np.uint16) 
            moy=np.array(moy, dtype='uint16')

            
            #i2,Seuil_haut, Seuil_bas=seuil_image(moy) # seuil bas = 0
            Seuil_haut = np.percentile(moy, 99.99) # was 99.999
            Seuil_bas=np.percentile(moy,5) # was zéra
            i2= seuil_image_force (moy,Seuil_haut, Seuil_bas)
            i1=seuil_image_force (frames[1],Seuil_haut, Seuil_bas)
            i3=seuil_image_force(frames[2],Seuil_haut, Seuil_bas)
             
            i2,Seuil_haut, Seuil_bas=seuil_image(moy)
            i1=seuil_image_force (frames[1],Seuil_haut, Seuil_bas)
            i3=seuil_image_force(frames[2],Seuil_haut, Seuil_bas)

            i1=np.clip(i1/256,0,255).astype(np.uint8)
            i2=np.clip(i2/256,0,255).astype(np.uint8)
            i3=np.clip(i3/256,0,255).astype(np.uint8)
            
            img_doppler[:,:,0] = i1 # blue
            img_doppler[:,:,1] = i2 # green
            img_doppler[:,:,2] = i3 # red
            img_doppler=cv2.flip(img_doppler,0)

            if doppler_color:
                # BGR → HSV
                hsv = cv2.cvtColor(img_doppler, cv2.COLOR_RGB2HSV).astype(np.float32)
                H, S, V = cv2.split(hsv)
                
                # Correction orange → plus rouge
                mask_orange = (H > 5) & (H < 25)   # plage d'orange en degrés OpenCV (0-179) was 25
                H[mask_orange] -= 20             # décale la teinte vers le rouge
                                
                # Correction bleu → plus bleu
                mask_blue = (H > 90) & (H < 150)    # plage de bleu was 90
                H[mask_blue] += 20 

                H = np.clip(H, 0, 180)
                S = np.clip(S, 0, 255) 
                V = np.clip(V, 0, 255) 
                
                # Reconstruction
                hsv_mod = cv2.merge([H, S, V]).astype(np.uint8)
                img_doppler = cv2.cvtColor(hsv_mod, cv2.COLOR_HSV2RGB)

            # sauvegarde en png 
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.jpg'),apply_watermark_if_enable(img_doppler, header, observer))
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.png'),img_doppler)
            create_solar_planisphere(os.path.join(wd,'sunscan_doppler.png'))

            print('create_protus_image eclipse doppler')
            i1 = create_protus_image(wd, f2, cercle, 0, header, observer)
            i2 = create_protus_image(wd, moy, cercle,0, header, observer)
            i3 = create_protus_image(wd, f1, cercle, 0, header, observer)
            
            i1=np.clip(i1/256,0,255).astype(np.uint8)
            i2=np.clip(i2/256,0,255).astype(np.uint8)
            i3=np.clip(i3/256,0,255).astype(np.uint8)
            
            img_doppler[:,:,0] = i1 # blue
            img_doppler[:,:,1] = i2 # green
            img_doppler[:,:,2] = i3 # red
         

            if doppler_color:

                # BGR → HSV
                hsv = cv2.cvtColor(img_doppler, cv2.COLOR_RGB2HSV).astype(np.float32)
                H, S, V = cv2.split(hsv)
                
                # Correction orange → plus rouge
                mask_orange = (H > 5) & (H < 25)   # plage d'orange en degrés OpenCV (0-179) was 25
                H[mask_orange] -= 20             # décale la teinte vers le rouge
                                
                # Correction bleu → plus bleu
                mask_blue = (H > 90) & (H < 150)    # plage de bleu was 90
                H[mask_blue] += 20 

                H = np.clip(H, 0, 180)
                S = np.clip(S, 0, 255) 
                V = np.clip(V, 0, 255) 
                
                # Reconstruction
                hsv_mod = cv2.merge([H, S, V]).astype(np.uint8)
                img_doppler = cv2.cvtColor(hsv_mod, cv2.COLOR_HSV2RGB)
                

            cv2.imwrite(os.path.join(wd,'sunscan_protus_doppler.jpg'),apply_watermark_if_enable(img_doppler, header, observer))
            cv2.imwrite(os.path.join(wd,'sunscan_protus_doppler.png'),img_doppler)
            
                
        except Exception as e:
            print(e)
            pass
        


def seuil_image(img):
    """
    Apply thresholding to an image.

    Args:
        img (numpy.ndarray): Input image.

    Returns:
        tuple: Thresholded image, upper threshold, lower threshold.
    """
    Seuil_haut=np.percentile(img,99.999)
    Seuil_bas=(Seuil_haut*0.25)
    img[img>Seuil_haut]=Seuil_haut
    img_seuil=(img-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas)) # was 65500
    img_seuil[img_seuil<0]=0
    
    return img_seuil, Seuil_haut, Seuil_bas

def seuil_image_force(img, Seuil_haut, Seuil_bas):
    """
    Apply forced thresholding to an image with given thresholds.

    Args:
        img (numpy.ndarray): Input image.
        Seuil_haut (float): Upper threshold.
        Seuil_bas (float): Lower threshold.

    Returns:
        numpy.ndarray: Thresholded image.
    """
    img[img>Seuil_haut]=Seuil_haut
    img_seuil=(img-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas)) # was 65500
    img_seuil[img_seuil<0]=0
    
    return img_seuil

def get_lum_moyenne(img):
    """
    Calculate the average luminosity of a central region of interest (ROI) in the image.

    Args:
        img (numpy.ndarray): Input image.

    Returns:
        float: Average luminosity of the ROI.
    """
    # add calculation of average intensity on center ROI
    ih, iw =img.shape
    dim_roi = 100
    rox1 = iw//2 - dim_roi
    rox2 = iw//2 + dim_roi
    roy1 = ih//2 - dim_roi
    roy2 = ih//2 + dim_roi
    #print('roi ', rox1,rox2,roy1,roy2)
    try :
        lum_roi=np.mean(img[roy1:roy2,rox1:rox2])
    except:
        lum_roi=0
    return lum_roi


def adjust_gamma(image, gamma=1.0):
	# build a lookup table mapping the pixel values [0, 255] to
	# their adjusted gamma values
	invGamma = 1.0 / gamma
	table = np.array([((i / 255.0) ** invGamma) * 255
		for i in np.arange(0, 256)]).astype("uint8")
	# apply gamma correction using the lookup table
	return cv2.LUT(image, table)

def Colorise_Image(color, frame_contrasted, wd, header, observer, planisphere=True, filename='sunscan_color'):
    if not color:
        return
    
    print(color)
    
    rules = {
        # orange/red
        'halpha':       { 'b':3.87, 'g':1.35, 'r':0.60, 'thresholds':55, 'gamma':1.2 }, 

        # purple
        'caIIH':     { 'b':0.80, 'g':1.50, 'r':1.50, 'thresholds':35, 'gamma':1.8   }, 
        'caIIK':     { 'b':0.80, 'g':1.50, 'r':1.50, 'thresholds':35, 'gamma':1.8  }, 
        'hepsilon':   { 'b':0.80, 'g':1.50, 'r':1.50, 'thresholds':40, 'gamma':1.8  }, 
        'hgamma':    { 'b':0.80, 'g':1.50, 'r':1.50, 'thresholds':45, 'gamma':1.8  },
        'hdelta':    { 'b':0.80, 'g':1.50, 'r':1.50, 'thresholds':50, 'gamma':1.8  },

        # blue
        'hbeta':    { 'b':0.90, 'g':1.30, 'r':1.80, 'thresholds':50, 'gamma':1.8  },
       
        # green
        'mgI1':      { 'b':1.3, 'g':.5, 'r':1.3, 'thresholds':55, 'gamma':1.0  },
        'mgI2':      { 'b':1.3, 'g':.5, 'r':1.3, 'thresholds':55, 'gamma':1.0  },
        'mgI3':      { 'b':1.3, 'g':.5, 'r':1.3, 'thresholds':55, 'gamma':1.0  },

        # yellow
        'heI':      { 'b':0.0, 'g':2.8, 'r':2.2, 'thresholds':10, 'gamma':1.8  }, 
        'sodium':   { 'b':0.0, 'g':2.8, 'r':2.2, 'thresholds':10, 'gamma':1.8  }, 
    }

    img_color = None
    f=frame_contrasted/256
    f_8=f.astype('uint8')

    if color in rules.keys():
        r = rules[color]
        # Apply gamma correction
        im = adjust_gamma(f_8,r['gamma'])
        im = im.astype(np.float32) / 256
        # Create BGR channels with different gamma values
        bgr = (np.power(im, r['b']), np.power(im, r['g']), np.power(im, r['r']))
        im = cv2.merge(bgr)
        im = (im * 256).astype(np.uint8)
        if r['thresholds'] > 0 :
            # Apply thresholds to image
            Seuil_bas=np.percentile(im,r['thresholds'])
            Seuil_haut=np.percentile(im,99.99999)*1.10
            cc=(im-Seuil_bas)*(256/(Seuil_haut-Seuil_bas))
            cc[cc<0]=0
            img_color=cc
        else:
            img_color=im
        
        cv2.imwrite(os.path.join(wd,filename+'.jpg'),apply_watermark_if_enable(img_color, header, observer))
        if planisphere:
            create_solar_planisphere(os.path.join(wd,filename+'.jpg'))

def save_as_fits(path, image, header):
    DiskHDU=fits.PrimaryHDU(image,header)
    DiskHDU.writeto(path, overwrite='True')

def get_fits_header(exp, gain):
    hdr= fits.Header()
    hdr['SIMPLE']='T'
    hdr['BITPIX']=32
    hdr['NAXIS']=2
    hdr['NAXIS1']=0
    hdr['NAXIS2']=0
    hdr['BZERO']=0
    hdr['BSCALE']=1
    hdr['BIN1']=1
    hdr['BIN2']=1
    hdr['EXPTIME']=int(exp/1000)
    hdr['GAIN']=gain
    hdr['DATE-OBS']=datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f7%z')
    hdr['OBSERVER']='SUNSCAN'
    hdr['INSTRUME']='SUNSCAN'
    hdr['TELESCOP']='SUNSCAN'
    hdr['OBJNAME']='Sun'
    hdr['PHYSPARA']= 'Intensity'
    hdr['WAVEUNIT']= -10  
    return hdr

def mock_callback(serfile, status, error='', detail=''):
    print(f"mock_callback {serfile} {status} {error} {detail}")
if __name__ == '__main__':
    process_scan("C:\\Users\\g-ber\\Downloads\\2025_09_21-07_50_05-scan.ser", mock_callback, True, True, 1100, False, advanced='halpha',observer=' ')
