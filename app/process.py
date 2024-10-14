import os
import cv2
import numpy as np
from scipy.ndimage import median_filter # ToDo : delete?
from Inti_recon import solex_proc 
import matplotlib.pyplot as plt # ToDo : delete ?
try : 
    from serfilesreader import Serfile # Todo : delete ?
except: 
    from serfilesreader.serfilesreader import Serfile # ToDo : delete?

def process_scan(serfile, callback, dopcont=False, autocrop=True, autocrop_size=1300):
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

    Shift = [0, 5, 16, 0.0, 0.0, 0.0]
    Flags =  {'DOPFLIP': False, 
            'SAVEPOLY': False, 
            'FLIPRA': True, 
            'FLIPNS': True, 
            'FORCE_FREE_MAGN': False, 
            'Autocrop': autocrop, 
            'FREE_AUTOPOLY': False, 
            'ZEE_AUTOPOLY': False, 
            'NOISEREDUC': False, 
            'DOPCONT': dopcont, 
            'VOL': False, 
            'POL': False, 
            'WEAK': False, 
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
        # Create and save surface image
        create_surface_image(WorkDir, frames)
        # Create and save continuum image
        create_continuum_image(WorkDir, frames)
        # Create and save prominence (protus) image
        create_protus_image(WorkDir, frames, cercle)
        # If doppler contrast is enabled, create and save doppler image
        if dopcont:
            create_doppler_image(WorkDir, frames)
        # Call the callback function to indicate successful completion
        callback(serfile, 'completed')
    except:
        # If an error occurs during processing, print an error message
        print("error solex proc")
        # Call the callback function to indicate failure
        callback(serfile, 'failed')


def sharpenImage(image):
    """
    Apply multiple sharpening operations to an image.

    Args:
        image (numpy.ndarray): Input image.

    Returns:
        numpy.ndarray: Sharpened image.
    """
    # Apply Gaussian blur with a 9x9 kernel and sigma of 10.0
    gaussian_3 = cv2.GaussianBlur(image, (9,9), 10.0)
    # Sharpen the image by subtracting the blurred image
    image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)

    # Apply Gaussian blur with a 9x9 kernel and sigma of 8.0
    gaussian_3 = cv2.GaussianBlur(image, (9,9), 8.0)
    # Sharpen the image again
    image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)

    # Apply Gaussian blur with a 3x3 kernel and sigma of 8.0
    gaussian_3 = cv2.GaussianBlur(image, (3,3), 8.0)
    # Sharpen the image one more time
    image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)
    return image

def create_surface_image(wd, frames):
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
    Seuil_bas=np.percentile(frames[0], 45)
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


    # -- CLAHE --
    # Create CLAHE object (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
    # Apply CLAHE to the first frame
    cl1 = clahe.apply(frames[0])
    
    # Calculate new thresholds for CLAHE image
    Seuil_bas=np.percentile(cl1, 50)
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
    cc = sharpenImage(cc)
   
    # Save CLAHE image as PNG and JPG
    cv2.imwrite(os.path.join(wd,'sunscan_clahe.png'),cc)
    cv2.imwrite(os.path.join(wd,'sunscan_clahe.jpg'),cc/256)
    # Create and save a smaller preview image
    ccsmall = cv2.resize(cc/256,  (0,0), fx=0.4, fy=0.4) 
    cv2.imwrite(os.path.join(wd, 'sunscan_preview.jpg'),ccsmall)
    print(os.path.join(wd, 'sunscan_preview.jpg'))

    Colorise_Image('auto', cc, wd)


def create_continuum_image(wd, frames):
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

        cc = sharpenImage(cc)

        # save as png
        cv2.imwrite(os.path.join(wd,'sunscan_cont.png'),cc)
        cv2.imwrite(os.path.join(wd,'sunscan_cont.jpg'),cc/256)
        # cv2.imshow('clahe',cc)
        # cv2.waitKey(10000)

def create_protus_image(wd, frames, cercle):
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
    
    Seuil_bas = np.percentile(cl1, 45)  # Lower threshold
    Seuil_haut = np.percentile(cl1, 99.9999) * 1.05  # Upper threshold

    cc = (cl1 - Seuil_bas) * (65000 / (Seuil_haut - Seuil_bas))  # Apply contrast
    cc[cc < 0] = 0  # Remove negative values
    cc = np.array(cc, dtype='uint16')

    cc = sharpenImage(cc)  # Sharpen the image

    # Save as PNG and JPG
    cv2.imwrite(os.path.join(wd, 'sunscan_protus.png'), cc)
    cv2.imwrite(os.path.join(wd, 'sunscan_protus.jpg'), cc / 256)

def create_doppler_image(wd, frames):
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
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.png'),img_doppler)
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.jpg'),img_doppler/256)
                
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


def Colorise_Image (couleur_lbl, frame_contrasted, wd):
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
    """
    plt.plot(hist)
    plt.show()
    print('couleur : ',pos_max)
    """
    
    # test ombres >> provoque des applats 
    ombres=False
    if ombres :
        
        i_low=[]
        i_hi=[]
        fr=np.copy(frame_contrasted)
        i_low=np.array((fr<(pos_max*256))*fr*1.01, dtype='uint16')
        i_hi=(fr>=pos_max)*fr
        fr=i_low+i_hi
        f=fr/256
        f_8=f.astype('uint8')
    
    
    if couleur =='on' :  
        if pos_max<200 and pos_max>=70 :
            couleur="H-alpha"
        if pos_max<70 :
            couleur="Calcium"
        if pos_max>=200 :
            couleur="Pale"

    
    # test ombres >> provoque des applats 
    ombres=False
    if ombres :
        f8_low=[]
        f8_hi=[]
        f8_low=np.array((f_8<pos_max)*f_8*1.05, dtype='uint8')
        f8_hi=(f_8>=pos_max)*f_8
        f_8=f8_low+f8_hi
    
    if couleur != '' :
        # image couleur en h-alpha
        if couleur == 'H-alpha' :
            # build a lookup table mapping the pixel values [0, 255] to
            # their adjusted gamma values
            gamma=0.05   # was gam 1.3 > 0.3 ok un peu plus clair et 0.1 plus sombre sombre
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f1_gam= cv2.LUT(f_8, table)
            
            gamma=0.45 # was gam 0.5 - 0.3 trop rouge, 0.6 un peu jaune - 0.55 ok
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f2_gam= cv2.LUT(f_8, table)
            
            gamma=1 # gam is 1.0
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
            # apply gamma correction using the lookup table
            f3_gam= cv2.LUT(f_8, table)
            
            i1=(f1_gam*1).astype('uint8')     # was 0.05 - 1 trop pale - 0.1 ok
            i2=(f2_gam*1).astype('uint8')       # is 1
            i3=(f3_gam*1).astype('uint8')       # is 1
            
            gamma=1.5 # gam total image 2 est trop fade, 1.2 pas assez, 1.5 pas mal
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            i1= cv2.LUT(i1, table)
            i2= cv2.LUT(i2, table)
            i3= cv2.LUT(i3, table)
            
            img_color=np.zeros([frame_contrasted.shape[0], frame_contrasted.shape[1], 3],dtype='uint8')
            img_color[:,:,0] = np.array(i1, dtype='uint8') # blue
            img_color[:,:,1] = np.array(i2, dtype='uint8') # blue
            img_color[:,:,2] = np.array(i3, dtype='uint8') # blue
            

            
        # image couleur en calcium
        if couleur == 'Calcium' :
            # build a lookup table mapping the pixel values [0, 255] to
            # their adjusted gamma values
            gamma=1.2  # was 1
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f1_gam= cv2.LUT(f_8, table)
            
            gamma=1 # was 0.8
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f2_gam= cv2.LUT(f_8, table)
            
            gamma=1 # was 0.8
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f3_gam= cv2.LUT(f_8, table)
            
            # i1: bleu, i2: vert, i3:rouge
            i1=(f1_gam*1).astype('uint8')     # was 0.05 - 1 trop pale - 0.1 ok
            i2=(f2_gam*0.7).astype('uint8')       # is 1
            i3=(f3_gam*0.7).astype('uint8')       # was 0.8 un peu trop violet
            
            img_color=np.zeros([frame_contrasted.shape[0], frame_contrasted.shape[1], 3],dtype='uint8')
            img_color[:,:,0] = np.array(i1, dtype='uint8') # blue
            img_color[:,:,1] = np.array(i2, dtype='uint8') # green
            img_color[:,:,2] = np.array(i3, dtype='uint8') # red
            
            vp=np.percentile(f_8, 99.7)
            alpha=(255//2)/(vp*0.5)
      
            img_color=cv2.convertScaleAbs(img_color, alpha=alpha) # was 1.5 ok
            

        # image couleur en jaune-orange (helium, sodium, continuum)
        if couleur == 'Pale' :
            # build a lookup table mapping the pixel values [0, 255] to
            # their adjusted gamma values
            gamma=1  # 
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f1_gam= cv2.LUT(f_8, table)
            
            gamma=1 # was 0.7
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f2_gam= cv2.LUT(f_8, table)
            
            gamma=1 # 
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            f3_gam= cv2.LUT(f_8, table)
            
            # i1: bleu, i2: vert, i3:rouge
            i1=(f1_gam*0.92).astype('uint8')     # was 0.5 
            i2=(f2_gam*0.98).astype('uint8')       # was 0.9
            i3=(f3_gam*1).astype('uint8')       # is 1
            
            gamma=0.5 # gam total image 1 trop fade, 0.7 pas mal
            invGamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
                # apply gamma correction using the lookup table
            i1= cv2.LUT(i1, table)
            i2= cv2.LUT(i2, table)
            i3= cv2.LUT(i3, table)
            
                
            img_color=np.zeros([frame_contrasted.shape[0], frame_contrasted.shape[1], 3],dtype='uint8')
            img_color[:,:,0] = np.array(i1, dtype='uint8') # blue
            img_color[:,:,1] = np.array(i2, dtype='uint8') # green
            img_color[:,:,2] = np.array(i3, dtype='uint8') # red
            
        #img_color = cv2.normalize(img_color, dst=None, alpha=0, beta=256, norm_type=cv2.NORM_MINMAX)
        cv2.imwrite(os.path.join(wd,'sunscan_clahe_colour.png'),img_color)
        cv2.imwrite(os.path.join(wd,'sunscan_clahe_colour.jpg'),img_color)
        return img_color
    

def mock_callback(serfile, status):
    print(f"mock_callback {serfile} {status}")
if __name__ == '__main__':
    process_scan("C:\\Users\\g-ber\\Downloads\\scan(6).ser", mock_callback, False, True, 1300)
