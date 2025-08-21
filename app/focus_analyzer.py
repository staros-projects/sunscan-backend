import numpy as np
import cv2
from collections import deque

class FocusAnalyzer:
    def __init__(self, measure_every=1, smooth_window=5):
        """
        Initialize the FocusAnalyzer.
        :param measure_every: number of frames to skip before recomputing sharpness
        :param smooth_window: number of values for moving average smoothing (default=3)
        """
        self.measure_every = measure_every
        self.frame_idx = 0

        # Previous measurements (kept for skipped frames)
        self.sharpness_prev = 0.0
        self.profile_prev = None
        self.edges_prev = (None, None)

        # Dynamic sharpness range for percentage normalization
        self.sharp_min = None
        self.sharp_max = None

        # History for moving average
        self.sharpness_history = deque(maxlen=smooth_window)

    @staticmethod
    def measure_focus_two_edges(frame_gray):
        """
        Detect the two main edges of the solar disk by analyzing the intensity profile.
        Returns:
            sharpness_raw: average of absolute gradients (not normalized)
            sharpness_norm: normalized sharpness in [0..1]
            edges: (left_x, right_x) positions
            profile: 1D brightness profile
            grad: gradient of profile
        """
        # Take only the top 20 and bottom 10 vertical pixels to reduce noise
        strip_top = frame_gray[:20, :]
        strip_bottom = frame_gray[-20:, :]
        strip = np.vstack((strip_top, strip_bottom))

        # Compute horizontal profile by averaging the selected rows
        profile = strip.mean(axis=0)

        # Compute the gradient of the profile to detect edges
        grad = np.gradient(profile.astype(float))

        # Left edge = maximum positive gradient
        left_idx = np.argmax(grad)
        left_val = grad[left_idx]

        # Right edge = minimum (most negative) gradient
        right_idx = np.argmin(grad)
        right_val = grad[right_idx]

        # Sharpness raw = average of absolute values of both edges
        sharpness_raw = (abs(left_val) + abs(right_val)) / 2.0

        # Normalize sharpness by dynamic range of profile
        Imin, Imax = np.min(profile), np.max(profile)
        dynamic = max(1.0, Imax - Imin)  # avoid division by zero
        sharpness_norm = sharpness_raw / dynamic

        return sharpness_raw, sharpness_norm, (left_idx, right_idx), profile, grad

    def update(self, frame):
        """
        Process one frame:
        - Convert to grayscale
        - Every N frames, recompute sharpness and edges
        - Otherwise reuse previous values
        Returns:
            sharpness_raw: raw sharpness
            sharpness_pct: normalized percentage [0..100]
            sharpness_smooth: smoothed sharpness (moving average)
            edges: (left, right) edge positions
        """
        gray = frame
        sharpness, sharpness_norm, edges, profile, grad = self.measure_focus_two_edges(gray)
      
        # Store in history and compute moving average
        self.sharpness_history.append(sharpness)
        sharpness_smooth = np.mean(self.sharpness_history)

        return sharpness_smooth, edges

    @staticmethod
    def overlay_edges(frame, edges):
        """
        Draw vertical dashed edges on a grayscale 16-bit image.
        Convert to 8-bit BGR before drawing so we can use color.
        """
        frame_u8 = frame.astype(np.uint8)

        if len(frame_u8.shape) == 2:
            frame_bgr = cv2.cvtColor(frame_u8, cv2.COLOR_GRAY2BGR)
        else:
            frame_bgr = frame_u8

        # Draw dashed green lines
        if edges[0] is not None:
            for y in range(0, frame_bgr.shape[0], 20):
                cv2.line(frame_bgr, (edges[0], y), (edges[0], y+10), (0, 255, 0), 2)
        if edges[1] is not None:
            for y in range(0, frame_bgr.shape[0], 20):
                cv2.line(frame_bgr, (edges[1], y), (edges[1], y+10), (0, 255, 0), 2)

        return frame_bgr
