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

def create_circular_mask(image_shape, center, radius, feather_width):
    """
    Create a circular mask with progressive edges (feathering).

    Parameters:
        image_shape (tuple): Shape of the target image (height, width).
        center (tuple): Center of the circular mask (x, y).
        radius (int): Radius of the circular mask.
        feather_width (int): Width of the feathering at the edges.

    Returns:
        mask (numpy.ndarray): A 2D mask with values ranging from 0 to 1.
    """
    height, width = image_shape
    y, x = np.ogrid[:height, :width]
    dist_from_center = np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2)

    # Create a mask with feathering
    mask = np.clip((radius + feather_width - dist_from_center) / feather_width, 0, 1)
    return mask

def blend_images(cc, result_image, mask):
    """
    Blend two images using a circular mask.

    Parameters:
        cc (numpy.ndarray): The background image.
        result_image (numpy.ndarray): The foreground image to be masked in the center.
        mask (numpy.ndarray): The blending mask with values between 0 and 1.

    Returns:
        blended_image (numpy.ndarray): The final blended image.
    """
    # Ensure both images are float64 for blending
    cc = cc.astype(np.float64)
    result_image = result_image.astype(np.float64)

    # Blend the images using the mask
    blended_image = mask * result_image + (1 - mask) * cc

    # Clip values to 16-bit range and convert back to uint16
    blended_image = np.clip(blended_image, 0, 65535).astype(np.uint16)

    return blended_image

def process_and_save_images(cc, result_image, output_dir, name, watermark_fct, header, observer, desc):
    """
    Process and save the blended image with a circular mask.

    Parameters:
        cc (numpy.ndarray): The background image (16-bit).
        result_image (numpy.ndarray): The foreground image (16-bit).
        output_dir (str): Directory where the output image will be saved.
        radius (int): Radius of the circular mask.
        feather_width (int): Width of the feathering at the edges.

    Returns:
        blended_image (numpy.ndarray): The blended image (16-bit).
    """
    height, width = cc.shape
    center = (width // 2, height // 2)
    radius=390
    feather_width=15

    # Create the circular mask
    mask = create_circular_mask((height, width), center, radius, feather_width)

    # Blend the images
    blended_image = blend_images(cc, result_image, mask)



    # Save the final blended image
    cv2.imwrite(os.path.join(output_dir,name+'.jpg'), watermark_fct(blended_image//256,header,observer, desc))
    cv2.imwrite(os.path.join(output_dir,name+'.png'),blended_image)
    return blended_image

def adjust_histogram(image):
    """
    Adjust the histogram of the image to tighten intensity thresholds.

    Parameters:
        image (numpy.ndarray): Input image (16-bit).

    Returns:
        adjusted_image (numpy.ndarray): Image with adjusted histogram.
    """
    # Calculate the 2nd and 98th percentiles for intensity stretching
    lower_bound = np.percentile(image, 1)
    upper_bound = np.percentile(image, 99.9)

    # Stretch the intensities to the full 16-bit range
    adjusted_image = np.clip((image - lower_bound) * (65535 / (upper_bound - lower_bound)), 0, 65535)

    return adjusted_image.astype(np.uint16)

def process_helium(WorkDir, frames, header, observer, watermark_fct, Colorise_Image):

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
    Seuil_haut=int(np.percentile(img_weak_uint,99.99))
    if (Seuil_haut-Seuil_bas) != 0 :
        cc=seuil_image_force(img_weak_uint, Seuil_haut, Seuil_bas).astype(np.uint16)
    else:
        cc=np.array((img_weak_array), dtype='uint16')

    cc = cv2.flip(cc,0)
    moy = cv2.flip(moy,0)

    R = 406
    
    median_projection = calculate_median_projection(cc, R)
    corrected_image = apply_transversalium_correction(cc, R, median_projection)

    image1 = np.array(corrected_image, dtype=np.int32) 
    image2 = np.array(moy, dtype=np.int32)


    constant = 32767


    coef = 0.0
    image2_transformed = np.where(image2 > 0, image2 - constant, 0)
    result_image = image1 + coef * image2_transformed
    result_image = np.clip(result_image, 0, 65535).astype(np.uint16)
    max_value = np.max(result_image)
    result_image = (result_image / max_value) * 65535.0
    result_image = result_image.astype(np.uint16)

    res = process_and_save_images(cc, result_image, WorkDir, 'sunscan_helium', watermark_fct, header, observer, 'He I line (D3) - 5875.65 Å')

    coef = 0.6
    result_image = image1 + coef * image2_transformed
    result_image = np.clip(result_image, 0, 65535).astype(np.uint16)
    max_value = np.max(result_image)
    result_image = (result_image / max_value) * 65535.0
    result_image = result_image.astype(np.uint16)

    res = process_and_save_images(cc, result_image, WorkDir, 'sunscan_helium_cont', watermark_fct, header, observer, 'He I line (D3) - 5875.65 Å')
    Colorise_Image('heI', res, WorkDir, header, observer)
    
    coef = 0.6
    result_image = image1 + coef * image2_transformed
    result_image = np.clip(result_image, 0, 65535).astype(np.uint16)
    max_value = np.max(result_image)
    result_image = (result_image / max_value) * 65535.0
    result_image = result_image.astype(np.uint16)

    moy = np.clip(moy, 0, 65535).astype(np.uint16)
    max_value = np.max(moy)
    moy = (moy / max_value) * 65535.0
    moy = moy.astype(np.uint16)

    cont_image = watermark_fct(moy//256, header, observer, 'Continuum')
    cv2.imwrite(os.path.join(WorkDir, 'sunscan_cont.png'),moy)
    cv2.imwrite(os.path.join(WorkDir, 'sunscan_cont.jpg'),cont_image)
    
    # Create and save a smaller preview image
    ccsmall = cv2.resize(res/256,  (0,0), fx=0.4, fy=0.4) 
    cv2.imwrite(os.path.join(WorkDir, 'sunscan_preview.jpg'),ccsmall)

