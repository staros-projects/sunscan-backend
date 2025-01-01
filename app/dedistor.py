import numpy as np
from scipy.interpolate import griddata
from scipy.ndimage import map_coordinates
from scipy.fft import fft2, ifft2, fftshift
from astropy.io import fits
import imageio.v2
import os
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageChops
import cv2

from process import sharpenImage, get_text_position
from storage import get_scan_tag

# ------------------------------------
# CROSS_CORRELATE_SHIFT_FFT
# ------------------------------------
def cross_correlation_shift_fft(patch_ref, patch_def):
    """
    Calculate the shift (dx, dy) using FFT-based cross-correlation with sub-pixel accuracy.
    """
    fft_ref = fft2(patch_ref)
    fft_def = fft2(patch_def)
    cross_corr = fftshift(ifft2(fft_ref * np.conj(fft_def)).real)

    max_idx = np.unravel_index(np.argmax(cross_corr), cross_corr.shape)
    center = np.array(cross_corr.shape) // 2
    shifts = np.array(max_idx) - center

    def fit_parabola_1d(values):
        denom = 2 * (2 * values[1] - values[0] - values[2])
        if denom == 0:
            return 0
        return (values[0] - values[2]) / denom

    dy_offset = 0
    dx_offset = 0

    if 1 <= max_idx[0] < cross_corr.shape[0] - 1:
        dy_offset = fit_parabola_1d([
            cross_corr[max_idx[0] - 1, max_idx[1]],
            cross_corr[max_idx[0], max_idx[1]],
            cross_corr[max_idx[0] + 1, max_idx[1]]
        ])
    if 1 <= max_idx[1] < cross_corr.shape[1] - 1:
        dx_offset = fit_parabola_1d([
            cross_corr[max_idx[0], max_idx[1] - 1],
            cross_corr[max_idx[0], max_idx[1]],
            cross_corr[max_idx[0], max_idx[1] + 1]
        ])

    shifts = shifts[::-1]
    shifts = shifts + np.array([dy_offset, dx_offset])
    return shifts

# --------------------------------------------------------------
# INTERPOLATE_DISPLACEMENT
# --------------------------------------------------------------
def interpolate_displacement(x_values, y_values, displacement_values, image_shape):
    """
    Interpolate displacement values (dx or dy) over the entire image using griddata.
    """
    # Create a grid corresponding to the full image
    grid_y, grid_x = np.mgrid[0:image_shape[0], 0:image_shape[1]]

    # Interpolation with griddata (linear interpolation + extrapolation)
    displacement_map = griddata(
        points=(y_values, x_values),
        values=displacement_values,
        xi=(grid_y, grid_x),
        method='cubic',
        fill_value=0  # Extrapolate with zeros if needed
    )
    return displacement_map


# -------------------------------
# FIND_DISTORSION 
# -------------------------------
def find_distorsion(reference_name, deformed_name, patch_size, step_size, intensity_threshold):
    """
    Parameters
    ----------
    path : TYPE
        Chemin des images
    reference_name : TYPE
        Nom de l'image ma�tre de r�f�rence'
    deformed_name : TYPE
        Nom  de l'image d�form�e � rectivier'
    patch_size : TYPE
        Taille du patch corr�lation
    step_size : TYPE
        Pas du cadrillage du patch de corr�lation (en X et Y)
    intensity_threshold : TYPE
        Seuil d'intensit� au dessus duquel la corr�laton est calcul�

    Returns
    -------
    dx_map : TYPE
        Carte des d�calages en X
    dy_map : TYPE
        Carte des d�calages en Y
    amplitude_map : TYPE
        Carte de l'amplitude des d�calages '
    """

    # Le traitement est fait par paire d'imagees, on charge la paire au format PNG
    full_reference_path =  reference_name 
    full_deformed_path =  deformed_name 
    
    ref_image = imageio.v2.imread(full_reference_path)
    def_image = imageio.v2.imread(full_deformed_path)
    
    # Conversion sur ne base 16 bits N&B (imp�ratif avec images SUNSCAN)
    ref_image = np.array(ref_image, np.uint16)
    def_image = np.array(def_image, np.uint16)
   
    # Passe-haut pour am�liorre la registration (accroissement des contrastes) (NA)
    #ref_image = sharpen_image(ref_image, 3)
    #def_image = sharpen_image(def_image, 3)
    
    rows, cols = ref_image.shape
    grid_y, grid_x = np.mgrid[0:rows:step_size, 0:cols:step_size]
    dx_values, dy_values, x_values, y_values = [], [], [], []

    for y, x in zip(grid_y.ravel(), grid_x.ravel()):
        
        if y + patch_size > rows or x + patch_size > cols:
            continue

        patch_ref = ref_image[y:y + patch_size, x:x + patch_size]
        patch_def = def_image[y:y + patch_size, x:x + patch_size]
        
        if patch_ref.min() < intensity_threshold:
            continue

        if patch_ref.shape == (patch_size, patch_size) and patch_def.shape == (patch_size, patch_size):
            dx, dy = cross_correlation_shift_fft(patch_ref, patch_def)
            dx_values.append(dx)
            dy_values.append(dy)
            x_values.append(x + patch_size // 2)
            y_values.append(y + patch_size // 2)
            
    # Interpolation des images point de mesures en des cartes dx, dy
    # (images au m�me format que les images d'entr�e)
    dx_map = interpolate_displacement(np.array(x_values), np.array(y_values), np.array(dx_values), ref_image.shape)
    dy_map = interpolate_displacement(np.array(x_values), np.array(y_values), np.array(dy_values), ref_image.shape)
    amplitude_map = np.sqrt(dx_map ** 2 + dy_map ** 2)
        
    return dx_map, dy_map, amplitude_map

# -----------------------------------------------------------------
# CORRECT_IMAGE_PNG
# Corrige une image d�form�e avec l'information des cartes dx, dy
# -----------------------------------------------------------------
def correct_image_png(input_name, dx_map, dy_map):
    """
    Parameters
    ----------
    path : TYPE
        Chemin de l'image'
    input_name : TYPE
        Nom de l'image (au format JPG)
    dx_map : TYPE
        Carte des d�formations en X
    dy_map : TYPE
        Carte des d�formations en Y 

    Returns
    -------
    corrected_image : TYPE
        L'image corrig�e de la distorsion

    """
    
    # Charge l'image d�form�e (version FITS)
    #input_path = path + input_name + '.fits'
    #def_image = fits.getdata(input_path)
    
    # Charge l'image d�forl�e (version PNG)
    input_path = input_name 
    def_image = imageio.v2.imread(input_path)
    
    # Convertie en 16 bits N&B
    def_image = np.array(def_image, np.uint16)
    
    # Correction de la distorsion (pixel au plus proche voisin)
    coords_y, coords_x = np.meshgrid(np.arange(def_image.shape[0]), np.arange(def_image.shape[1]), indexing='ij')
    corrected_coords_y = coords_y - dy_map
    corrected_coords_x = coords_x - dx_map
    corrected_image = map_coordinates(def_image, [corrected_coords_y, corrected_coords_x], order=1, mode='nearest')
    return corrected_image


def stack(paths, status, observer):
    if not status['clahe']:
        return 

    clahe_basefilename =  'sunscan_clahe.png'
    cont_basefilename =  'sunscan_cont.png'

    deformed_root = os.path.join(os.path.dirname(paths[0]) ,clahe_basefilename)
    sum_image = imageio.v2.imread(deformed_root )
    sum_image = sum_image.astype(np.uint32) 

    if status['cont']:
        cont_deformed_root = os.path.join(os.path.dirname(paths[0]) ,cont_basefilename)
        cont_sum_image = imageio.v2.imread(cont_deformed_root )
        cont_sum_image = cont_sum_image.astype(np.uint32) 
    i = 1
    tag = ''
    acquisition_dates = []
    for p in paths:
        print('Stack #'+str(i))
        dirname = os.path.dirname(p)
        # Check for tag_ file and set tag accordingly
        if not tag:
            tag = get_scan_tag(dirname)
        
        date_str = dirname.split('/')[-1].split('-')[-2].replace('sunscan_', '') 
        time_str = dirname.split('/')[-1].split('-')[-1] 
        print(date_str, time_str)
        full_datetime_str = f"{date_str} {time_str.replace('_', ':')}"
        dt = datetime.strptime(full_datetime_str, "%Y_%m_%d %H:%M:%S")
        acquisition_dates.append(dt)

        # Calcul des cartes de d�calage
        # patch_size : taille du patch de cross-corr�lation
        # step_size : pas de cross-corr�lation (en X et Y)
        # intensity_threshold : seuil d'intensit� en dessous duquel la corr�lation n'est pas calcul�
        deformed_name = os.path.join(os.path.dirname(p) ,clahe_basefilename)
        dx_map, dy_map, amplitude_map = find_distorsion(deformed_root,deformed_name, patch_size=32, step_size=10, intensity_threshold=0)
            
        # Correction des distorsions dans la s�quence principale (format PNG en entr�e)
        corrected_image = correct_image_png(deformed_name, dx_map, dy_map)

        if status['cont']:
            cont_deformed_name = os.path.join(os.path.dirname(p) ,cont_basefilename)
            corrected_cont_image = correct_image_png(cont_deformed_name, dx_map, dy_map)
        
        # Sommation (stacking)
        if i>1:
            sum_image = sum_image + corrected_image.astype(np.uint32)
            if status['cont']:
                cont_sum_image = cont_sum_image + corrected_cont_image.astype(np.uint32)

        print('Scan #' + p)
        i+=1

    stacking_dir = './storage/stacking'
    
    if not os.path.exists(stacking_dir):
        os.mkdir(stacking_dir)

    formatted_avg_datetime = None
    if acquisition_dates:
        avg_timestamp = sum([dt.timestamp() for dt in acquisition_dates]) / len(acquisition_dates)
        avg_datetime = datetime.fromtimestamp(avg_timestamp)
        formatted_avg_datetime = avg_datetime.strftime("%Y/%m/%d %H:%M:%S")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") 
    work_dir = os.path.join(stacking_dir, timestamp)
    if not os.path.exists(work_dir):
        os.mkdir(work_dir)

    watermark_txt = str(i-1)+' stacked images - '+formatted_avg_datetime
    if tag:
        watermark_txt += ' - '+ tag

    write_images(work_dir, sum_image, 'clahe', i-1, watermark_txt, observer)
    if status['cont']: 
        write_images(work_dir, cont_sum_image, 'cont', i-1, watermark_txt, observer)


def apply_watermark_if_enable(frame, text, observer):
    print('watermark', observer)
    if not observer:
        return frame
    # Ensure the frame is in uint8 format
    if frame.dtype != np.uint8:
        frame = frame.astype(np.uint8)  # Normalize if in float

    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image) 
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Regular.ttf", 30)  # Use a specific font if available
    text_position = get_text_position(image)
    draw.text(text_position, text, fill="white", font=font)

    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Baumans-Regular.ttf", 40)  # Use a specific font if available
    draw.text(get_text_position(image, 126), 'SUNSCAN', fill="white", font=font)
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Thin.ttf", 30)  # Use a specific font if available
    draw.text(get_text_position(image, 84), observer, fill="white", font=font)
    return np.array(image)


def write_images(work_dir, sum_image, type, scan_count, text, observer):
    sum_image = sum_image / scan_count
    sum_image = sum_image.astype(np.uint16)

    max_value = np.max(sum_image)
    if max_value != 0:
        sum_image = (sum_image / max_value) * 65535.0
    sum_image = sum_image.astype(np.uint16)

    imageio.v2.imwrite(os.path.join(work_dir,'stacked_'+type+'_'+str(scan_count)+'_raw.png'), sum_image, format="png")
    cv2.imwrite(os.path.join(work_dir,'stacked_'+type+'_'+str(scan_count)+'_raw.jpg'), apply_watermark_if_enable(sum_image//256,text,observer))
    sum_image = sharpenImage(sum_image, 1 if scan_count<8 else 2)
    imageio.v2.imwrite(os.path.join(work_dir,'stacked_'+type+'_'+str(scan_count)+'_sharpen.png'), sum_image, format="png")
    cv2.imwrite(os.path.join(work_dir,'stacked_'+type+'_'+str(scan_count)+'_sharpen.jpg'), apply_watermark_if_enable(sum_image//256,text,observer))


    ccsmall = cv2.resize(sum_image/256,  (0,0), fx=0.4, fy=0.4)    
    cv2.imwrite(os.path.join(work_dir, 'stacked_'+type+'_preview.jpg'),ccsmall)