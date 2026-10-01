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

from process import Colorise_Image, sharpenImage, get_text_position, create_protus_image, create_negative_surface_image
from storage import get_scan_tag, save_sources
from config import LineDict

from Inti_functions import detect_edge, fit_ellipse

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
def find_distorsion(ref_image, def_image, patch_size, step_size, intensity_threshold):
    """
    Parameters
    ----------
    ref_image : TYPE
        Image ma�tre de r�f�rence
    def_image : TYPE
        Image d�form�e � rectifier, de la taille de la r�f�rence
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
def correct_image_png(def_image, dx_map, dy_map):
    """
    Parameters
    ----------
    def_image : TYPE
        Image d�form�e, de la taille des cartes
    dx_map : TYPE
        Carte des d�formations en X
    dy_map : TYPE
        Carte des d�formations en Y 

    Returns
    -------
    corrected_image : TYPE
        L'image corrig�e de la distorsion

    """
    
    # Convertie en 16 bits N&B
    def_image = np.array(def_image, np.uint16)
    
    # Correction de la distorsion (pixel au plus proche voisin)
    coords_y, coords_x = np.meshgrid(np.arange(def_image.shape[0]), np.arange(def_image.shape[1]), indexing='ij')
    corrected_coords_y = coords_y - dy_map
    corrected_coords_x = coords_x - dx_map
    corrected_image = map_coordinates(def_image, [corrected_coords_y, corrected_coords_x], order=1, mode='nearest')
    return corrected_image


class StackError(Exception):
    """Stacking refused for a reason the frontend can show : error key and detail."""
    def __init__(self, error, detail):
        super().__init__(detail)
        self.error = error
        self.detail = detail


# Side of the stacked images when the scans differ in size, in disk diameters : as the autocrop of 1100 px
# for a disk of about 800, it keeps the prominences
DISK_FRAME_RATIO = 1.4

def find_disk(image):
    """(xc, yc, radius) of the solar disk of an image, None when it is not found."""
    try:
        X = detect_edge(image, zexcl=0.1, crop=0, disp_log=False)
        fit, _ = fit_ellipse(image, X, disp_log=False)
        xc, yc = (float(np.real(v)) for v in fit[0])
        radius = float(np.real(max(fit[1], fit[2])))
    except Exception as e:
        print('disk not found', e)
        return None
    h, w = image.shape[:2]
    if not (0 <= xc < w and 0 <= yc < h and 0 < radius < max(h, w)):
        return None
    return xc, yc, radius

def crop_on_disk(image, xc, yc, side):
    """Square of side pixels centred on the disk, black where the image does not cover it."""
    square = np.zeros((side, side) + image.shape[2:], image.dtype)
    x0 = int(round(xc)) - side // 2
    y0 = int(round(yc)) - side // 2
    sx0, sy0 = max(x0, 0), max(y0, 0)
    sx1, sy1 = min(x0 + side, image.shape[1]), min(y0 + side, image.shape[0])
    if sx1 > sx0 and sy1 > sy0:
        square[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = image[sy0:sy1, sx0:sx1]
    return square


def stack(paths, status, observer, patch_size, step_size, intensity_threshold, progress=None):
    """
    progress (function): Optional, progress(step key, fraction of the step, scan number, number of scans).
    Returns the directory of the new stack, None when the scans do not all have the images to stack.
    Raises StackError when the scans can not be stacked together.
    """
    if not status['clahe'] and not status['helium']:
        return

    clahe_basefilename =  'sunscan_clahe.png' if not status['helium'] else 'sunscan_helium.png'
    cont_basefilename =  'sunscan_cont.png' if not status['helium'] else 'sunscan_helium_cont.png'

    def load(p, basefilename):
        return imageio.v2.imread(os.path.join(os.path.dirname(p), basefilename))

    surfaces = [load(p, clahe_basefilename) for p in paths]

    # Scans processed without the autocrop (their size depends on the length of the scan), or with different
    # autocrop sizes : each one is cropped around its disk to a common square, the alignment does the rest
    disks = None
    if len({s.shape for s in surfaces}) > 1:
        disks = []
        for n, (p, s) in enumerate(zip(paths, surfaces), 1):
            disk = find_disk(s)
            if disk is None:
                raise StackError('disk_not_found', f'Scan #{n} ({os.path.dirname(p)}) : solar disk not found')
            disks.append(disk)
        side = 2 * int(round(max(d[2] for d in disks) * DISK_FRAME_RATIO))
        print('stack: scans of different sizes', [s.shape for s in surfaces], 'cropped on their disk to', side)

    def prepare(n, image):
        """Image of the scan n (from 0) at the size of the stack."""
        if disks is None:
            return image
        xc, yc, _ = disks[n]
        return crop_on_disk(image, xc, yc, side)

    reference = prepare(0, surfaces[0])
    sum_image = reference.astype(np.uint32)

    # Other images of the scans summed with the surface, aligned with its distortion maps :
    # type of the stacked image -> file of the scans. A Ca II H scan also has the H epsilon images : they are
    # stacked when every scan has them (not a Ca II K scan tagged Ca II H, nor a scan processed before 2.1.0)
    extra = {}
    if status['cont'] or status['helium_cont']:
        extra['cont'] = cont_basefilename
    if not status['helium']:
        for name in ('hepsilon', 'hepsilon_protus'):
            if status.get(name):
                extra[name] = 'sunscan_' + name + '.png'
    extra_sum_images = {name: prepare(0, load(paths[0], basefilename)).astype(np.uint32)
                        for name, basefilename in extra.items()}
    i = 1
    tag = ''
    acquisition_dates = []
    print('conf:',patch_size, step_size, intensity_threshold)
    for p in paths:
        print('Stack #'+str(i))
        if progress:
            progress('aligning', (i - 1) / len(paths), i, len(paths))
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
        deformed = prepare(i - 1, surfaces[i - 1])
        dx_map, dy_map, amplitude_map = find_distorsion(reference, deformed, patch_size, step_size, intensity_threshold)

        # Correction des distorsions dans la s�quence principale (format PNG en entr�e)
        corrected_image = correct_image_png(deformed, dx_map, dy_map)

        # Sommation (stacking)
        if i>1:
            sum_image = sum_image + corrected_image.astype(np.uint32)
            for name, basefilename in extra.items():
                corrected_extra_image = correct_image_png(prepare(i - 1, load(p, basefilename)), dx_map, dy_map)
                extra_sum_images[name] = extra_sum_images[name] + corrected_extra_image.astype(np.uint32)

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
    # The directory is named after now : keep the scans, their line and their dates (upload to SpectroSolHub)
    save_sources(work_dir, 'stack', paths, observer)

    watermark_txt = str(i-1)+' stacked images - '+formatted_avg_datetime+' UT'
    watermark_txt_t = watermark_txt
    if tag:
        watermark_txt_t += ' - '+ tag

    if progress:
        progress('writing_images', 0.0, len(paths), len(paths))
    write_images(work_dir, sum_image, 'clahe', i-1, watermark_txt_t, observer, tag)
 
    if progress:
        progress('writing_images', 0.8, len(paths), len(paths))
    if 'cont' in extra_sum_images:
        # the helium continuum carries the line, the continuum of the other lines does not
        write_images(work_dir, extra_sum_images['cont'], 'cont', i-1, watermark_txt_t if status['helium_cont'] else watermark_txt, observer, tag)
    # The H epsilon images carry their own line, not the tag of the scans (Ca II H)
    hepsilon_txt = watermark_txt + ' - ' + LineDict['hepsilon']
    if 'hepsilon' in extra_sum_images:
        if progress:
            progress('writing_images', 0.9, len(paths), len(paths))
        write_images(work_dir, extra_sum_images['hepsilon'], 'hepsilon', i-1, hepsilon_txt, observer, tag)
    if 'hepsilon_protus' in extra_sum_images:
        # the prominences are not sharpened, as on a single scan
        write_images(work_dir, extra_sum_images['hepsilon_protus'], 'hepsilon_protus', i-1, hepsilon_txt, observer, tag, sharpen=False)
    return work_dir

        
def apply_watermark_if_enable(frame, text, observer):
    print('watermark', observer)
    if observer == ' ':
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
    draw.text(get_text_position(image, 115), 'SUNSCAN', fill="white", font=font)
    font = ImageFont.truetype("/var/www/sunscan-backend/app/fonts/Roboto-Regular.ttf", 20)  # Use a specific font if available
    draw.text(get_text_position(image, 73), observer, fill="white", font=font)
    return np.array(image)


def write_images(work_dir, sum_image, im_type, scan_count, text, observer, tag, sharpen=True):
    """sharpen : also write the sharpened version, the one the preview is made of. False for the prominences."""
    sum_image = sum_image / scan_count
    sum_image = sum_image.astype(np.uint16)

    max_value = np.max(sum_image)
    if max_value != 0:
        sum_image = (sum_image / max_value) * 65535.0
    sum_image = sum_image.astype(np.uint16)

    imageio.v2.imwrite(os.path.join(work_dir,'stacked_'+im_type+'_'+str(scan_count)+'_raw.png'), sum_image, format="png")
    cv2.imwrite(os.path.join(work_dir,'stacked_'+im_type+'_'+str(scan_count)+'_raw.jpg'), apply_watermark_if_enable(sum_image//256,text,observer))
    sum_image2 = sum_image
    if sharpen:
        sum_image2 = sharpenImage(sum_image, 1 if scan_count<8 else 2)
        imageio.v2.imwrite(os.path.join(work_dir,'stacked_'+im_type+'_'+str(scan_count)+'_sharpen.png'), sum_image2, format="png")
        cv2.imwrite(os.path.join(work_dir,'stacked_'+im_type+'_'+str(scan_count)+'_sharpen.jpg'), apply_watermark_if_enable(sum_image2//256,text,observer))
    


    #     cc = create_protus_image(work_dir, cv2.flip(raw,0), 0, None, observer, None)
    #     imageio.v2.imwrite(os.path.join(work_dir, 'stacked_protus'+'_'+str(scan_count)+'_raw.png'), cc, format="png")
    #     cv2.imwrite(os.path.join(work_dir, 'stacked_protus'+'_'+str(scan_count)+'_raw.jpg'), apply_watermark_if_enable(cc//256,text,observer))

    ccsmall = cv2.resize(sum_image2/256,  (0,0), fx=0.4, fy=0.4)    
    cv2.imwrite(os.path.join(work_dir, 'stacked_'+im_type+'_preview.jpg'),ccsmall)

    tag_enabled_for_negative = ['halpha', 'hbeta', 'hgamma', 'hdelta', 'hepsilon']
    label_enabled_for_negative = []
    for t in tag_enabled_for_negative:
        l = LineDict[t]
        label_enabled_for_negative.append(l)

    if im_type == 'hepsilon':
        # coloured like the H epsilon image of a scan, raw and sharpened as the colour image of the surface
        Colorise_Image('hepsilon', sum_image, work_dir, text, observer, False, 'stacked_hepsilon_color_'+str(scan_count)+'_raw')
        Colorise_Image('hepsilon', sum_image2, work_dir, text, observer, False, 'stacked_hepsilon_color_'+str(scan_count)+'_sharpen')

    if im_type == 'clahe':
        for (k,v) in LineDict.items():
            if v == tag:
                color = k
                print('stack color image generation ', text, observer)
                Colorise_Image(color, sum_image, work_dir, text, observer, False, 'stacked_color_'+str(scan_count)+'_raw')
                Colorise_Image(color, sum_image2, work_dir, text, observer, False, 'stacked_color_'+str(scan_count)+'_sharpen')
                break

        if tag in label_enabled_for_negative:
            X = detect_edge(sum_image, zexcl=0.1, crop=0, disp_log=False)
            EllipseFit,XE=fit_ellipse(sum_image, X, disp_log=False)
            xc=round(EllipseFit[0][0])
            yc=round(EllipseFit[0][1])
            wi=round(EllipseFit[1]) # diametre
            he=round(EllipseFit[2])
            cercle=[xc,yc,wi,he]  
            im_type = 'negative'
            text = text.replace('stacked images', 'stacked negative images')
            # Built on the sharpened image, as the negative of a single scan (the file keeps its '_raw' name,
            # the one the gallery, the animations and SpectroSolHub look for)
            n = create_negative_surface_image(work_dir, sum_image2, cercle, text, observer, return_image=True)
            imageio.v2.imwrite(os.path.join(work_dir,'stacked_'+im_type+'_'+str(scan_count)+'_raw.png'), n, format="png")
            cv2.imwrite(os.path.join(work_dir,'stacked_'+im_type+'_'+str(scan_count)+'_raw.jpg'), apply_watermark_if_enable(n//256,text,observer))



    