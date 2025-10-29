import cv2
import numpy as np
import os

import cv2
import numpy as np
import os
import matplotlib.pyplot as plt

def create_solar_planisphere(filename, debug=False):
    """
    Create a full solar planisphere from a single solar image.
    Invisible parts of the Sun are filled with black.
    Saves the output as <original_name>_proj.<ext>.
    If debug=True, shows the detected Sun circle on the original image.
    """
    # Load image
    img = cv2.imread(filename, cv2.IMREAD_COLOR)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detect Sun using Hough Circle
    gray_blur = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        gray_blur, cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=100,
        param1=50, param2=30,
        minRadius=350, maxRadius=450
    )

    if circles is None:
        raise ValueError("Sun could not be detected automatically.")

    cx, cy, r = np.round(circles[0, 0]).astype(int)

    # Debug: show detected circle
    if debug:
        debug_img = img_rgb.copy()
        cv2.circle(debug_img, (cx, cy), r, (255, 0, 0), 3)
        cv2.circle(debug_img, (cx, cy), 3, (0, 255, 0), -1)
        plt.figure(figsize=(6,6))
        plt.imshow(debug_img)
        plt.title("Debug: Detected Sun Circle")
        plt.axis('off')
        plt.show()

    # Output planisphere size
    width_out = 2 * r
    height_out = r

    # Create latitude-longitude grid for full 360° longitude
    lon = np.linspace(-np.pi, np.pi, width_out)
    lat = np.linspace(-np.pi/2, np.pi/2, height_out)
    lon, lat = np.meshgrid(lon, lat)

    # Convert spherical coordinates to image coordinates
    x = cx + r * np.cos(lat) * np.sin(lon)
    y = cy + r * np.sin(lat)

    # Mask visible hemisphere
    mask = (np.cos(lat) * np.cos(lon) >= 0) & ((x - cx)**2 + (y - cy)**2 <= r**2)

    # Clip coordinates
    x = np.clip(x, 0, img.shape[1]-1).astype(np.float32)
    y = np.clip(y, 0, img.shape[0]-1).astype(np.float32)

    # Remap and apply mask
    planisphere = np.zeros((height_out, width_out, 3), dtype=np.uint8)
    planisphere[mask] = cv2.remap(img_rgb, x, y, interpolation=cv2.INTER_LINEAR)[mask]

    # Save output
    base, ext = os.path.splitext(filename)
    outname = f"{base}_proj.jpg"
    cv2.imwrite(outname, cv2.cvtColor(planisphere, cv2.COLOR_RGB2BGR))
    print(f"Planisphere saved as: {outname}")

