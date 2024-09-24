import numpy as np
import cv2 as cv2


def synth_spectrum(template, ratio_pix):
    """
    Synthesize a spectrum from a template image.

    Args:
        template (numpy.ndarray): The input template image.
        ratio_pix (float): The pixel ratio for resizing.

    Returns:
        numpy.ndarray: The synthesized spectrum.
    """
    h, w = template.shape[0], template.shape[1]
    if ratio_pix != 1:
        template = cv2.resize(template, dsize=(w, int(h*0.5)), interpolation=cv2.INTER_LANCZOS4)
        template = cv2.GaussianBlur(template, (5, 1), cv2.BORDER_DEFAULT)
    template = template[:, w//2-10:(w//2)+10]
    moy = 1 * np.mean(template, 1)
    moy = np.array(moy, dtype='uint8')
    vector_t = np.array([moy]).T
    temp_r = np.tile(vector_t, (1, 100))

    return temp_r


def template_locate(img_r, temp_r):
    """
    Locate the best match position of a template in an image.

    Args:
        img_r (numpy.ndarray): The input image.
        temp_r (numpy.ndarray): The template to match.

    Returns:
        int: The y-coordinate of the best match.
    """
    matched = cv2.matchTemplate(img_r, temp_r, cv2.TM_CCOEFF_NORMED)
    (minVal, maxVal, minLoc, maxLoc) = cv2.minMaxLoc(matched)
    return maxLoc[1]

atlas = {
    20491-694:"Ca II K - 3933.68 A",
    20491-932:"Ca II H - 3968.49 A",
    20491-6935:"H beta - 4861.35 A",
    20491-9018:"Mg I",
    20491-9054:"Mg I",
    20491-9129:"Mg I",
    20491-9953:"Fe XIV - 5302.86 A",
    20491-14015:"He I D3",
    20491-14120:"Na D2",
    20491-14162:"Na D1",
    20491-16235:"Fe I - 6173 A",
    20491-17229:"Fe I - 6302 A",
    20491-17792:"Fe X - 6374.56 A",
    20491-19310:"H alpha  - 6562.82 A"}

pixel_ref = 2.4 *2
ratio_pix= 1.0
        
img_r=cv2.imread('sun_spectre.png',cv2.IMREAD_GRAYSCALE)
img_r=cv2.flip(img_r, 0)
ih,iw = img_r.shape[0], img_r.shape[1]
img_r=img_r[:,iw//2-100:(iw//2)+100]

font                   = cv2.FONT_HERSHEY_COMPLEX
fontScale              = 1
fontColor              = (255,255,255)
thickness              = 1
lineType               = cv2.LINE_AA

def locateLines(frame):
    """
    Locate and annotate spectral lines in the given frame.

    Args:
        frame (numpy.ndarray): The input frame to process.

    Returns:
        numpy.ndarray: The processed frame with annotated spectral lines.
    """
    temp_r = synth_spectrum(frame, ratio_pix)
    y_top = template_locate(img_r, temp_r)
    y_bottom = y_top + frame.shape[0]

    lines = {k: v for k, v in atlas.items() if k in range(y_top, y_bottom)}
    for line, name in lines.items():
        print(line, name)
        cv2.line(frame, (0,line-y_top), (frame.shape[1],line-y_top), (255,255,255), thickness) 
        cv2.putText(frame,
                        name,
                        (500,line-y_top+20),
                        font, 
                        fontScale,
                        fontColor,
                        thickness,
                        lineType)
    return frame


                          