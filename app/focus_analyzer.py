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
        - Compute average horizontal profile
        - Find gradient (slope of intensity)
        - Left edge = strongest positive gradient
        - Right edge = strongest negative gradient
        Returns:
            sharpness: average of absolute gradients at both edges
            edges: (left_x, right_x) positions
            profile: 1D brightness profile
            grad: gradient of profile
        """
        profile = frame_gray.mean(axis=0)
        grad = np.gradient(profile)

        # Left edge = strongest rising slope
        left_idx = np.argmax(grad)
        left_val = grad[left_idx]

        # Right edge = strongest falling slope
        right_idx = np.argmin(grad)
        right_val = grad[right_idx]

        # Sharpness = mean of absolute slopes
        sharpness = (abs(left_val) + abs(right_val)) / 2.0
        return sharpness, (left_idx, right_idx), profile, grad

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
            sharpness, edges, profile, grad = self.measure_focus_two_edges(gray)
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
        Draw vertical green lines at the detected left and right edges.
        """
        if edges[0] is not None:
            cv2.line(frame, (edges[0], 0), (edges[0], frame.shape[0]), (0, 255, 0), 2)
        if edges[1] is not None:
            cv2.line(frame, (edges[1], 0), (edges[1], frame.shape[0]), (0, 255, 0), 2)
        return frame
