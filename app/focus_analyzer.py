import numpy as np
import cv2

class FocusAnalyzer:
    def __init__(self, measure_every=5):
        """
        Initialize the FocusAnalyzer.
        :param measure_every: number of frames to skip before recomputing sharpness
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

    @staticmethod
    def measure_focus_two_edges(frame_gray):
        """
        Detect the two main edges of the solar disk by analyzing the intensity profile.

        Steps:
        - Extract top and bottom strips of the image to reduce noise
        - Compute average horizontal profile
        - Find gradient (slope of intensity)
        - Left edge = strongest positive gradient
        - Right edge = strongest negative gradient
        - Sharpness = average of absolute gradients at both edges
        - Sharpness is also normalized by the dynamic range of the profile

        Returns:
            sharpness_raw: average of absolute gradients (not normalized)
            sharpness_norm: normalized sharpness in [0..1]
            edges: (left_x, right_x) positions
            profile: 1D brightness profile
            grad: gradient of profile
        """
        # Take only the top 10 and bottom 10 vertical pixels to reduce noise
        strip_top = frame_gray[:10, :]        # Top 10 rows
        strip_bottom = frame_gray[-10:, :]    # Bottom 10 rows
        strip = np.vstack((strip_top, strip_bottom))  # Combine top and bottom strips

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

    def update_sharpness_range(self, sharpness):
        """
        Update min and max sharpness values for percentage normalization.
        """
        if self.sharp_min is None or sharpness < self.sharp_min:
            self.sharp_min = sharpness
        if self.sharp_max is None or sharpness > self.sharp_max:
            self.sharp_max = sharpness

    def get_sharpness_pct(self, sharpness):
        """
        Convert sharpness value into a normalized percentage [0..100].
        """
        if self.sharp_min is None or self.sharp_max is None or self.sharp_max == self.sharp_min:
            return 0.0
        pct = (sharpness - self.sharp_min) / (self.sharp_max - self.sharp_min)
        return max(0.0, min(1.0, pct)) * 100

    def update(self, frame):
        """
        Process one frame:
        - Convert to grayscale
        - Every N frames, recompute sharpness and edges
        - Otherwise reuse previous values
        Returns:
            sharpness: raw sharpness metric
            pct: normalized percentage [0..100]
            edges: (left, right) edge positions
        """
        gray = frame

        if self.frame_idx % self.measure_every == 0:
            sharpness, sharpness_norm, edges, profile, grad = self.measure_focus_two_edges(gray)
            self.sharpness_prev = sharpness
            self.profile_prev = profile
            self.edges_prev = edges
            self.update_sharpness_range(sharpness)
        else:
            # Reuse last computed values
            sharpness = self.sharpness_prev
            edges = self.edges_prev
            profile = self.profile_prev

        self.frame_idx += 1
        pct = self.get_sharpness_pct(sharpness)
        return sharpness, pct, edges

    @staticmethod
    def overlay_edges(frame, edges):
        """
        Draw vertical edges on a grayscale 16-bit image.
        Convert to 8-bit BGR before drawing so we can use color.
        """
        # Ensure frame is uint8
        frame_u8 = frame.astype(np.uint8)

        # If already grayscale, just copy
        if len(frame_u8.shape) == 2:
            frame_bgr = cv2.cvtColor(frame_u8, cv2.COLOR_GRAY2BGR)
        else:
            frame_bgr = frame_u8


        # Draw green lines at detected edges
        if edges[0] is not None:
            cv2.line(frame_bgr, (edges[0], 0), (edges[0], frame_bgr.shape[0]), (0, 255, 0), 2)
        if edges[1] is not None:
            cv2.line(frame_bgr, (edges[1], 0), (edges[1], frame_bgr.shape[0]), (0, 255, 0), 2)

        return frame_bgr
