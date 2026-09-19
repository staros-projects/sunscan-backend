import numpy as np
from scipy.signal import find_peaks, savgol_filter

# H epsilon (3970.07 Å) sits in the red wing of Ca II H, 1.606 Å from its core. Around Ca II H the SunScan
# spectrum is 0.125 Å per column and the wavelength decreases when the column increases (a positive shift
# goes to the blue), so the line is 13 columns under the core. Measured on real scans against the solar
# atlas: the contrast of the plages drops and the prominences emit again at that shift, 5 columns wide.
HEPSILON_SHIFT = -13
# Same distance on the other side of the core: same level in the Ca II H wing, without the H epsilon line
MIRROR_SHIFT = 13

# Photospheric lines seen in the mean spectrum around Ca II H and Ca II K, in columns from the core.
# The line tag of a scan can't be trusted alone (Ca II K scans tagged Ca II H do exist), and at the same
# shift from Ca II K there is no line at all: these lines tell which one of the two was scanned.
CA2H_LINES = (-41, -30, -22, 14, 19, 32, 38, 43, 56)
CA2K_LINES = (-37, -29, -17, 27, 35, 45)
MIN_LINES = 5


def mean_profile(mean_image, poly, y1, y2):
    """
    Mean spectrum of the solar disk, once the line is straightened with its polynomial.

    Args:
        mean_image (numpy.ndarray): Mean of the frames of the scan, one spectrum per row.
        poly (list): a, b, c of the column of the line: a*y**2 + b*y + c.
        y1, y2 (int): First and last row of the spectrum in the mean image.

    Returns:
        numpy.ndarray: Profile with the core of the line at column c, 1 at its maximum.
    """
    a, b, c = poly
    iw = mean_image.shape[1]
    margin = min(100, (y2 - y1) // 4)
    ys = np.arange(y1 + margin, y2 - margin)
    rows = mean_image[ys].astype(np.float64)
    # linear interpolation of each row at the columns that follow the line
    src = np.arange(iw)[None, :] + (a * ys**2 + b * ys)[:, None]
    left = np.clip(np.floor(src).astype(int), 0, iw - 2)
    weight = np.clip(src - left, 0, 1)
    straight = np.take_along_axis(rows, left, axis=1) * (1 - weight) + np.take_along_axis(rows, left + 1, axis=1) * weight
    profile = straight.mean(axis=0)
    return profile / profile.max()


def count_lines(dips, core, lines, iw):
    """Number of expected lines found among the dips, out of those that fall inside the spectrum."""
    inside = [l for l in lines if 3 <= core + l <= iw - 4]
    return sum(1 for l in inside if np.any(np.abs(dips - (core + l)) <= 1))


def is_ca2h(profile, c):
    """
    Tell if the line of a mean spectrum is Ca II H, from the photospheric lines around it.

    Args:
        profile (numpy.ndarray): Mean spectrum, see mean_profile.
        c (float): Column of the core of the line.

    Returns:
        bool: True when the lines around Ca II H are there, and not the ones around Ca II K.
    """
    smooth = savgol_filter(profile, 5, 2)
    dips, _ = find_peaks(-smooth, prominence=0.008)
    lo = max(int(round(c)) - 4, 0)
    core = lo + int(np.argmin(smooth[lo:lo + 9]))
    found_h = count_lines(dips, core, CA2H_LINES, len(profile))
    found_k = count_lines(dips, core, CA2K_LINES, len(profile))
    print(f'hepsilon: {found_h} Ca II H lines, {found_k} Ca II K lines around the core')
    return found_h >= MIN_LINES and found_h > found_k


class HEpsilonPlanes:
    """
    Extra planes to rebuild out of a Ca II H scan to get H epsilon, given to solex_proc as extra_shifts.
    solex_proc calls it once the line is located; shifts holds what was asked for, empty when the scan
    can't give H epsilon, and the planes then come last in the frames of solex_proc, in the same order.
    """
    def __init__(self):
        self.shifts = []

    def __call__(self, mean_image, poly, y1, y2):
        a, b, c = poly
        ys = np.arange(y1, y2)
        center = a * ys**2 + b * ys + c
        # both planes, and the column on their right used by the interpolation, must stay inside the spectrum
        if center.min() + HEPSILON_SHIFT < 1 or center.max() + MIRROR_SHIFT + 1 > mean_image.shape[1] - 2:
            print('hepsilon: line too close to the edge of the spectrum')
        elif is_ca2h(mean_profile(mean_image, poly, y1, y2), c):
            self.shifts = [HEPSILON_SHIFT, MIRROR_SHIFT]
        return self.shifts
