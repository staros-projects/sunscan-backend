import os
import cv2
import numpy as np

from scipy.ndimage import median_filter
from Inti_recon import solex_proc 

import matplotlib.pyplot as plt

try : 
    from serfilesreader import Serfile
except: 
    from serfilesreader.serfilesreader import Serfile

def process_scan(serfile, callback, dopcont=False, autocrop=True, autocrop_size=1300):
    WorkDir = os.path.dirname(serfile)
      
    if not os.path.exists(serfile):
        return callback(serfile, 'failed')
    
    print(f"process_scan {serfile}")

    # Creation des trois sous-repertoires 
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
        frames, header, cercle, range_dec, geom, polynome= solex_proc(serfile,Shift,Flags,ratio_fixe,ang_tilt, poly, data_entete,ang_P, solar_dict, param)
        create_surface_image(WorkDir, frames)
        create_continuum_image(WorkDir, frames)
        create_protus_image(WorkDir, frames, cercle)
        if dopcont:
            create_doppler_image(WorkDir, frames)
        callback(serfile, 'completed')
    except:
        print("error solex proc")
        callback(serfile, 'failed')


def sharpenImage(image):
    gaussian_3 = cv2.GaussianBlur(image, (9,9), 10.0)
    image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)

    gaussian_3 = cv2.GaussianBlur(image, (9,9), 8.0)
    image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)

    gaussian_3 = cv2.GaussianBlur(image, (3,3), 8.0)
    image = cv2.addWeighted(image, 1.5, gaussian_3, -0.5, 0, image)
    return image


def create_surface_image(wd, frames):
    # raw
    Seuil_bas=np.percentile(frames[0], 45)
    Seuil_haut=np.percentile(frames[0],99.9999)*1.20
    raw=(frames[0]-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
    raw[raw<0]=0
    raw=np.array(raw, dtype='uint16')
    raw=cv2.flip(raw,0)

    # sauvegarde en png 
    cv2.imwrite(os.path.join(wd,'sunscan_raw.png'),raw)
    cv2.imwrite(os.path.join(wd,'sunscan_raw.jpg'),raw/256)


    # clahe
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
    cl1 = clahe.apply(frames[0])
    
    Seuil_bas=np.percentile(cl1, 45)
    Seuil_haut=np.percentile(cl1,99.9999)*1.05

    cc=(cl1-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
    cc[cc<0]=0
    cc=np.array(cc, dtype='uint16')
    cc=cv2.flip(cc,0)

    cc = sharpenImage(cc)

    # sauvegarde en png 
    cv2.imwrite(os.path.join(wd,'sunscan_clahe.png'),cc)
    cv2.imwrite(os.path.join(wd,'sunscan_clahe.jpg'),cc/256)
    ccsmall = cv2.resize(cc/256,  (0,0), fx=0.4, fy=0.4) 
    cv2.imwrite(os.path.join(wd, 'sunscan_preview.jpg'),ccsmall)
    print(os.path.join(wd, 'sunscan_preview.jpg'))
    cc_ori = cc.copy()

    # h alpha
    gamma_weight = 0.8
    gamma = 1.0
    im = gamma_weight * np.power(cc, gamma) + (1.0 - gamma_weight) * (1.0 - np.power(1.0 - cc, 1.0 / gamma))
    im = im.astype(np.float32) / 65535.0
    rgb = (np.power(im, 3.8), np.power(im, 1.25), np.power(im, 0.4))
    im = cv2.merge(rgb)
    im = (im * 65535).astype(np.uint16)

    Seuil_bas=np.percentile(im, 50)
    Seuil_haut=np.percentile(im,99.9999)*1.30

    cc=(im-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
    cc[cc<0]=0
    cc=np.array(cc, dtype='uint16')
    cv2.imwrite(os.path.join(wd, 'sunscan_clahe_colour.png'),im)
    cv2.imwrite(os.path.join(wd, 'sunscan_clahe_colour.jpg'),im/256)
    ccsmall = cv2.resize(im/256,  (0,0), fx=0.4, fy=0.4) 
    cv2.imwrite(os.path.join(wd, 'sunscan_colour_preview.jpg'),ccsmall)

    # ca II K
    gamma_weight = 0.8
    gamma = 1.0
    im = gamma_weight * np.power(cc_ori, gamma) + (1.0 - gamma_weight) * (1.0 - np.power(1.0 - cc_ori, 1.0 / gamma))
    im = im.astype(np.float32) / 65535.0
    rgb = (np.power(im, 1.0), np.power(im, 2.0), np.power(im, 1.2))
    im = cv2.merge(rgb)
    im = (im * 65535).astype(np.uint16)

    Seuil_bas=np.percentile(im, 50)
    Seuil_haut=np.percentile(im,99.9999)*1.30

    cc=(im-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
    cc[cc<0]=0
    cc=np.array(cc, dtype='uint16')
    cv2.imwrite(os.path.join(wd, 'sunscan_clahe_colour_caII.png'),im)
    cv2.imwrite(os.path.join(wd, 'sunscan_clahe_colour_caII.jpg'),im/256)
    ccsmall = cv2.resize(im/256,  (0,0), fx=0.4, fy=0.4) 
    cv2.imwrite(os.path.join(wd, 'sunscan_colour_caII_preview.jpg'),ccsmall)

def create_continuum_image(wd, frames):
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

        # sauvegarde en png 
        cv2.imwrite(os.path.join(wd,'sunscan_cont.png'),cc)
        cv2.imwrite(os.path.join(wd,'sunscan_cont.jpg'),cc/256)
        # cv2.imshow('clahe',cc)
        # cv2.waitKey(10000)

def create_protus_image(wd, frames, cercle):

    # png image generation
    # image seuils moyen
    frame1=np.copy(frames[0])
    sub_frame=frame1[5:,:-5]
    Seuil_haut=np.percentile(sub_frame,99.999)
    Seuil_bas=(Seuil_haut*0.35)
    frame1[frame1>Seuil_haut]=Seuil_haut
    fc=(frame1-Seuil_bas)* (65500/(Seuil_haut-Seuil_bas))
    fc[fc<0]=0
    frame_contrasted=np.array(fc, dtype='uint16')
    frame_contrasted=cv2.flip(frame_contrasted,0)
        
    sub_frame=frame1[5:,:-5]
    Seuil_haut=np.percentile(sub_frame,99.999)
    Seuil_bas=(Seuil_haut*0.25)
    frame1[frame1>Seuil_haut]=Seuil_haut
    fc2=(frame1-Seuil_bas)* (65500/(Seuil_haut-Seuil_bas))
    fc2[fc2<0]=0

    frame2=np.copy(frames[0])
    disk_limit_percent=0.002 # black disk radius inferior by 2% to disk edge (was 1%)
    if cercle[0]!=0:
        x0=cercle[0]
        y0=cercle[1]

        wi=int(cercle[2])
        he=int(cercle[3])
        r=(min(wi,he))
        r=int(r- round(r*disk_limit_percent))-1 # retrait de 1 pixel modif de juin 2023

        fc3=cv2.circle(frame2, (x0,y0),r,80,-1,lineType=cv2.LINE_AA)
        frame1=np.copy(fc3)
        Threshold_Upper=np.percentile(frame1,99.9999)*0.5  #preference for high contrast
        Threshold_low=0
        img_seuil=seuil_image_force(frame1, Threshold_Upper, Threshold_low)
        
        frame_contrasted3=np.array(img_seuil, dtype='uint16')
        frame_contrasted3=cv2.flip(frame_contrasted3,0)
    else:   
        frame_contrasted3=frame_contrasted


    # clahe
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(2,2))
    cl1 = clahe.apply(frame_contrasted3)
    
    Seuil_bas=np.percentile(cl1, 45)
    Seuil_haut=np.percentile(cl1,99.9999)*1.05

    cc=(cl1-Seuil_bas)*(65000/(Seuil_haut-Seuil_bas))
    cc[cc<0]=0
    cc=np.array(cc, dtype='uint16')

    cc = sharpenImage(cc)

    # sauvegarde en png 
    cv2.imwrite(os.path.join(wd,'sunscan_protus.png'),cc)
    cv2.imwrite(os.path.join(wd,'sunscan_protus.jpg'),cc/256)

def create_doppler_image(wd, frames):
    if len(frames) >3:
        try :
            img_doppler=np.zeros([frames[1].shape[0], frames[1].shape[1], 3],dtype='uint16')

            f1=np.array(frames[1], dtype="float64")
            f2=np.array(frames[2], dtype="float64")
            moy=np.array(((f1+f2)/2), dtype='uint16')
             
            i2,Seuil_haut, Seuil_bas=seuil_image(moy)
            i1=seuil_image_force (frames[1],Seuil_haut, Seuil_bas)
            i3=seuil_image_force(frames[2],Seuil_haut, Seuil_bas)
            
            img_doppler[:,:,0] = i1 # blue
            img_doppler[:,:,1] = i2 # green
            img_doppler[:,:,2] = i3 # red
            img_doppler=cv2.flip(img_doppler,0)

            # sauvegarde en png 
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.png'),img_doppler)
            cv2.imwrite(os.path.join(wd,'sunscan_doppler.jpg'),img_doppler/256)
                
        except:
            pass
        


def seuil_image (img):
    Seuil_haut=np.percentile(img,99.999)
    Seuil_bas=(Seuil_haut*0.25)
    img[img>Seuil_haut]=Seuil_haut
    img_seuil=(img-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas)) # was 65500
    img_seuil[img_seuil<0]=0
    
    return img_seuil, Seuil_haut, Seuil_bas

def seuil_image_force (img, Seuil_haut, Seuil_bas):
    img[img>Seuil_haut]=Seuil_haut
    img_seuil=(img-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas)) # was 65500
    img_seuil[img_seuil<0]=0
    
    return img_seuil

def get_lum_moyenne(img) :
    # ajout calcul intensit� moyenne sur ROI centr�e
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


if __name__ == '__main__':
    process_scan("C:\\Users\\g-ber\\Documents\\ASTRO\\sunscan\\ser\\scan_gbertrand_good_20240706.ser", lambda x:x)
