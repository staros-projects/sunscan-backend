import os
import cv2
import json
import datetime
import numpy as np
from astropy.io import fits
from Inti_recon import solex_proc 
from PIL import Image, ImageDraw, ImageFont, ImageChops
from datetime import datetime

def process_scan(serfile, callback, dopcont=False, autocrop=True, autocrop_size=1100, noisereduction=False, dopplerShift=5, contShift=16, contSharpLevel=2, surfaceSharpLevel=2, proSharpLevel=1, offset=0, observer=''):
    """
    Process a solar scan from a .ser file and generate various images.

    Args:
        serfile (str): Path to the .ser file.
        callback (function): Callback function to report processing status.
        dopcont (bool): Flag to enable Doppler processing.
        autocrop (bool): Flag to enable auto-cropping.
        autocrop_size (int): Size for auto-cropping.

    Returns:
        None
    """
    WorkDir = os.path.dirname(serfile)
      
    if not os.path.exists(serfile):
        return callback(serfile, 'failed')
    
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
            'DOPCONT': dopcont, 
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
    param=[0,0,autocrop_size,autocrop_size]

    try:
        # Process the SER file using solex_proc function
        frames, header, cercle, range_dec, geom, polynome = solex_proc(serfile, Shift, Flags, ratio_fixe, ang_tilt, poly, data_entete, ang_P, solar_dict, param)
        
        header = update_header(WorkDir, header, observer)
        # Create and save surface image
        create_surface_image(WorkDir, frames, surfaceSharpLevel, header, observer)
        # Create and save continuum image
        create_continuum_image(WorkDir, frames, contSharpLevel, header, observer)
        # Create and save prominence (protus) image
        create_protus_image(WorkDir, frames, cercle, proSharpLevel, header, observer)
        # If doppler contrast is enabled, create and save doppler image
        if dopcont:
            create_doppler_image(WorkDir, frames, header, observer)
        # Call the callback function to indicate successful completion
        callback(serfile, 'completed')
    except Exception as e:
        # If an error occurs during processing, print an error message
        print("error solex proc", e)
        # Call the callback function to indicate failure
        callback(serfile, 'failed')

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

def create_surface_image(wd, frames, level, header, observer):
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
        save_as_fits(os.path.join(wd,'sunscan_clahe.fits'), cc, header)
        # Create and save a smaller preview image
        ccsmall = cv2.resize(cc/256,  (0,0), fx=0.4, fy=0.4) 
        cv2.imwrite(os.path.join(wd, 'sunscan_preview.jpg'),ccsmall)
        print(os.path.join(wd, 'sunscan_preview.jpg'))
    except Exception as e:
        print(e)
    Colorise_Image('auto', cc, wd, header, observer)

def apply_watermark_if_enable(frame, header, observer):
    print('watermark', observer)
    if not observer:
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
            formatted_date = datetime_obj.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            print(e)

    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image) 
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Regular.ttf", 30)  # Use a specific font if available
    text_position = get_text_position(image)
    draw.text(text_position, formatted_date, fill="white", font=font)

    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Baumans-Regular.ttf", 40)  # Use a specific font if available
    draw.text(get_text_position(image, 126), 'SUNSCAN', fill="white", font=font)
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Thin.ttf", 30)  # Use a specific font if available
    draw.text(get_text_position(image, 84), observer, fill="white", font=font)
    return np.array(image)

def get_text_position(image, padding_from_bottom=50, padding_from_left=20):
     # Get the image dimensions to position the text in the bottom-left corner
    width, height = image.size
    # Position the text in the bottom-left corner with some padding
    return (padding_from_left, height - padding_from_bottom)  # Padding of Npx from the left and bottom


def create_continuum_image(wd, frames, level, header, observer):
    """
    Create and save a continuum image of the sun.

    Args:
        wd (str): Working directory to save images.
        frames (list): List of image frames.

    Returns:
        None
    """
    if len(frames) >3:
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
        cv2.imwrite(os.path.join(wd,'sunscan_cont.jpg'),apply_watermark_if_enable(cc//256,header,observer))
        cv2.imwrite(os.path.join(wd,'sunscan_cont.png'),cc)
        # cv2.imshow('clahe',cc)
        # cv2.waitKey(10000)

def create_protus_image(wd, frames, cercle, level, header, observer):
    """
    Create and save a prominence (protus) image of the sun.

    Args:
        wd (str): Working directory to save images.
        frames (list): List of image frames.
        cercle (tuple): Parameters defining the solar disk circle.

    Returns:
        None
    """

    # Generate PNG image
    # Image with average thresholds
    frame1 = np.copy(frames[0])
    sub_frame = frame1[5:,:-5]
    Seuil_haut = np.percentile(sub_frame, 99.999)  # Upper threshold
    Seuil_bas = (Seuil_haut * 0.35)  # Lower threshold
    frame1[frame1 > Seuil_haut] = Seuil_haut  # Cap values at upper threshold
    fc = (frame1 - Seuil_bas) * (65500 / (Seuil_haut - Seuil_bas))  # Apply contrast
    fc[fc < 0] = 0  # Remove negative values
    frame_contrasted = np.array(fc, dtype='uint16')
    frame_contrasted = cv2.flip(frame_contrasted, 0)  # Flip image vertically
        
    sub_frame = frame1[5:,:-5]
    Seuil_haut = np.percentile(sub_frame, 99.999)  # Recalculate upper threshold
    Seuil_bas = (Seuil_haut * 0.25)  # Recalculate lower threshold
    frame1[frame1 > Seuil_haut] = Seuil_haut  # Cap values at new upper threshold
    fc2 = (frame1 - Seuil_bas) * (65500 / (Seuil_haut - Seuil_bas))  # Apply contrast
    fc2[fc2 < 0] = 0  # Remove negative values

    frame2 = np.copy(frames[0])
    disk_limit_percent = 0.002  # Black disk radius inferior by 2% to disk edge (was 1%)
    if cercle[0] != 0:
        x0 = cercle[0]  # Center x-coordinate
        y0 = cercle[1]  # Center y-coordinate

        wi = int(cercle[2])  # Width
        he = int(cercle[3])  # Height
        r = (min(wi, he))  # Radius
        r = int(r - round(r * disk_limit_percent)) - 1  # Adjust radius (modified June 2023) - 1 pixel removed

        fc3 = cv2.circle(frame2, (x0, y0), r, 80, -1, lineType=cv2.LINE_AA)  # Draw circle
        frame1 = np.copy(fc3)
        Threshold_Upper = np.percentile(frame1, 99.9999) * 0.5  # Preference for high contrast
        Threshold_low = 0
        img_seuil = seuil_image_force(frame1, Threshold_Upper, Threshold_low)
        
        frame_contrasted3 = np.array(img_seuil, dtype='uint16')
        frame_contrasted3 = cv2.flip(frame_contrasted3, 0)  # Flip image vertically
    else:   
        frame_contrasted3 = frame_contrasted

    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
    cl1 = clahe.apply(frame_contrasted3)
    
    Seuil_bas = np.percentile(cl1, 50)  # Lower threshold
    Seuil_haut = np.percentile(cl1, 99.9999) * 1.05  # Upper threshold

    cc = (cl1 - Seuil_bas) * (65000 / (Seuil_haut - Seuil_bas))  # Apply contrast
    cc[cc < 0] = 0  # Remove negative values
    cc = np.array(cc, dtype='uint16')

    cc = sharpenImage(cc, level)  # Sharpen the image

    # Save as PNG and JPG
    cv2.imwrite(os.path.join(wd, 'sunscan_protus.jpg'), apply_watermark_if_enable(cc//256,header,observer))
    cv2.imwrite(os.path.join(wd, 'sunscan_protus.png'), cc)

def create_doppler_image(wd, frames, header, observer):
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
            img_doppler=np.zeros([frames[1].shape[0], frames[1].shape[1], 3],dtype='uint16')

            f1=np.array(frames[1], dtype="float64")
            f2=np.array(frames[2], dtype="float64")
            moy=np.array(((f1+f2)/2), dtype='uint16')
             
            i2,Seuil_haut, Seuil_bas=seuil_image(moy)
            i1=seuil_image_force (frames[1],Seuil_haut, Seuil_bas)
            i3=seuil_image_force(frames[2],Seuil_haut, Seuil_bas)
            
            img_doppler[:,:,0] = i3 # blue
            img_doppler[:,:,1] = i2 # green
            img_doppler[:,:,2] = i1 # red
            img_doppler=cv2.flip(img_doppler,0)

            # sauvegarde en png 
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.jpg'),apply_watermark_if_enable(img_doppler//256, header, observer))
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.png'),img_doppler)
                
        except:
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

def Colorise_Image (couleur_lbl, frame_contrasted, wd, header, observer):
    # gestion couleur auto ou sur dropdown database compatibility
    # 'Manual','Ha','Ha2cb','Cah','Cah1v','Cak','Cak1v','HeID3'
    if couleur_lbl == 'auto' :
        couleur = 'on' # mode detection auto basé sur histogramme simple
    else :
        if couleur_lbl[:2] == 'Ha' :
            couleur='H-alpha'
        if couleur_lbl[:3] == 'Ha2' :
            couleur='Pale'
        if couleur_lbl[:2] == 'Ca' :
            couleur='Calcium'
        if couleur_lbl[:2] == 'He' :
            couleur='Pale'
    
    f=frame_contrasted/256
    f_8=f.astype('uint8')
    
    #hist = cv2.calcHist([f_8],[0],None,[256],[10,256])
    # separe les 2 pics fond et soleil
    th_otsu,img_binarized=cv2.threshold(f_8, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    hist = cv2.calcHist([f_8],[0],None,[256],[0,256])
    hist[0:int(th_otsu)]=0
    pos_max=np.argmax(hist)

    if couleur =='on' :  
        if pos_max<200 and pos_max>=70 :
            couleur="H-alpha"
        if pos_max<70 :
            couleur="Calcium"
    
    if couleur != '' :
        # image couleur en h-alpha
        if couleur == 'H-alpha' :
            # Apply gamma correction
            im = im = adjust_gamma(f_8,1.2)
            im = im.astype(np.float32) / 256
            # Create RGB channels with different gamma values
            rgb = (np.power(im, 3.87), np.power(im, 1.35), np.power(im, 0.6))
            im = cv2.merge(rgb)
            im = (im * 256).astype(np.uint16)

            # Apply thresholds to H-alpha image
            Seuil_bas=np.percentile(im,68)
            Seuil_haut=np.percentile(im,99.9999)*1.05
            cc=(im-Seuil_bas)*(256/(Seuil_haut-Seuil_bas))
            cc[cc<0]=0
            img_color=cc
            
        # image couleur en calcium
        if couleur == 'Calcium' :
            # Apply gamma correction
            im = adjust_gamma(f_8,1.8)
            im = im.astype(np.float32) / 256
            # Create RGB channels with different gamma values
            rgb = (np.power(im, 0.8), np.power(im, 1.5), np.power(im, 1.5))
            im = cv2.merge(rgb)
            im = (im * 256).astype(np.uint8)

            # Apply thresholds to image
            Seuil_bas=np.percentile(im,50)
            Seuil_haut=np.percentile(im,99.99999)*1.1
            cc=(im-Seuil_bas)*(256/(Seuil_haut-Seuil_bas))
            cc[cc<0]=0
            img_color=cc

        cv2.imwrite(os.path.join(wd,'sunscan_clahe_colour.jpg'),apply_watermark_if_enable(img_color, header, observer))
        return img_color

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
    hdr['DATE-OBS']=datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f7%z')
    hdr['OBSERVER']='SUNSCAN'
    hdr['INSTRUME']='SUNSCAN'
    hdr['TELESCOP']='SUNSCAN'
    hdr['OBJNAME']='Sun'
    hdr['PHYSPARA']= 'Intensity'
    hdr['WAVEUNIT']= -10  
    return hdr

def mock_callback(serfile, status):
    print(f"mock_callback {serfile} {status}")
if __name__ == '__main__':
    process_scan("/var/www/sunscan-backend/app/storage/scans/2024_11_22/sunscan_2024_11_22-12_59_03/scan.ser", mock_callback, False, True, 1100)
