import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
import os
import cv2

def seuil_image_force (img, Seuil_haut, Seuil_bas):
    img[img>Seuil_haut]=Seuil_haut
    img_seuil=(img-Seuil_bas)* (65535/(Seuil_haut-Seuil_bas)) # was 65500
    img_seuil[img_seuil<0]=0
    
    return img_seuil

# Calcul de la projection m�diane suivant l'axe X (coordonn�e horizontale)
def calculate_median_projection(image, R):
    # Dans mon r�f�renciel, imax est la dimension horizontale de l'image (axe x)
    # C'est aussi la direction du scan
    jmax, imax = image.shape
    xc, yc = imax // 2, jmax // 2  # Calcul automatique du centre
    x_coords, y_coords = np.ogrid[:imax, :jmax]
    mask = (x_coords - xc)**2 + (y_coords - yc)**2 <= R**2
    median_projection = np.zeros(jmax)
    
    # Pour chaque ligne Y, calculer la m�diane des intensit�s le long de X
    for y in range(jmax):
        line_pixels = image[y, mask[y, :]]  # Pixels sur cette ligne, dans le disque
        if line_pixels.size > 0:
            median_projection[y] = np.median(line_pixels)
        else:
            median_projection[y] = 1  # Evite la division par z�ro
             
    return median_projection

# Appliquer la correction
def apply_transversalium_correction(image, R, median_projection):
    # Dans mon r�f�renciel, imax est la dimension horizontale de l'image (axe x)
    # C'est aussi la direction du scan
    corrected_image = image.astype(np.float64)  # Convertir en r�els pour les calculs
    jmax, imax = image.shape
    xc, yc = imax // 2, jmax // 2  # Calcul automatique du centre
    x_coords, y_coords = np.ogrid[:imax, :jmax]
    mask = (x_coords - xc)**2 + (y_coords - yc)**2 <= R**2

    # Appliquer la correction pour chaque ligne Y en divisant par la projection m�diane
    for y in range(jmax):
        correction_value = median_projection[y]  # Projection m�diane suivant l'axe Y pour chaque ligne X
        if correction_value > 0:  # Evite la division par z�ro
            corrected_image[y, mask[y, :]] = corrected_image[y, mask[y, :]] / correction_value

    # Normaliser l'intensit� � 32767 (intensit� mouenne dans l'image de d�part h�lium)
    normalization_factor = 32767.0
    corrected_image *= normalization_factor
        
    # Mettre � z�ro les pixels en dehors du disque solaire
    corrected_image[~mask] = 0    

    # Convertir l'image corrig�e en entier 16 bits
    corrected_image = np.clip(corrected_image, 0, 65535).astype(np.uint16)
        
    return corrected_image

def process_helium(WorkDir, frames, header, observer, watermark_fct):

    fr1=np.copy(frames[1])
    fr2=np.copy(frames[2])
    fr0=np.copy(frames[0])
    s=np.array(np.array(fr1, dtype='float64')+np.array(fr2, dtype='float64'),dtype='float64')
    moy=s*0.5
    
    d=(np.array(fr0, dtype='float64')-moy)

    
    offset=-np.min(d)

    img_weak_array=d+float(offset+100)
    img_weak_uint=np.array((img_weak_array), dtype='uint16')
    #Seuil_bas=int(offset/2)
    Seuil_bas=0
    Seuil_haut=int(np.percentile(img_weak_uint,99.96))
    if (Seuil_haut-Seuil_bas) != 0 :
        cc=seuil_image_force(img_weak_uint, Seuil_haut, Seuil_bas).astype(np.uint16)
    else:
        cc=np.array((img_weak_array), dtype='uint16')

    cc = cv2.flip(cc,0)

    R = 408
    
    median_projection = calculate_median_projection(cc, R)
    corrected_image = apply_transversalium_correction(cc, R, median_projection)

    image1 = np.array(corrected_image, dtype=np.int32) 
    image2 = np.array(cv2.flip(moy,0), dtype=np.int32)


    constant = 32767

    # Coefficient d'accentuation de l'image h�lium
    coef = 0.8

    # Transformer la deuxi�me image
    image2_transformed = np.where(image2 > 0, image2 - constant, 0)

    # Additionner la premi�re image avec la deuxi�me image transform�e
    result_image = image1 + coef * image2_transformed

    # S'assurer que les valeurs sont dans l'intervalle [0, 65535] pour les PNG 16 bits
    result_image = np.clip(result_image, 0, 65535).astype(np.uint16)
    ci = np.clip(corrected_image, 0, 65535).astype(np.uint16)
    
    cv2.imwrite(os.path.join(WorkDir,'sunscan_clahe.jpg'), watermark_fct(cc//256,header,observer))
    cv2.imwrite(os.path.join(WorkDir,'sunscan_clahe.png'),cc)

    cv2.imwrite(os.path.join(WorkDir,'sunscan_cont.jpg'), watermark_fct(result_image//256,header,observer))
    cv2.imwrite(os.path.join(WorkDir,'sunscan_cont.png'),result_image)
    # Create and save a smaller preview image
    ccsmall = cv2.resize(result_image/256,  (0,0), fx=0.4, fy=0.4) 
    cv2.imwrite(os.path.join(WorkDir, 'sunscan_preview.jpg'),ccsmall)

  
  