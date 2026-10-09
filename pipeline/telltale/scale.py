"""Metric scale: pixels to millimetres across a sloping scene.

A single ``mm_per_px`` is only right for a plane facing the camera. A slope seen obliquely has
a scale that changes across the frame. Given four or more image points with known ground
coordinates (a tape measure between stakes, a surveyed baseline, or an E2 target placed at a
few spots), a homography from image to the ground plane is estimated (least squares for a
handful of points, RANSAC with a scale-relative threshold for more), and the local Jacobian of that homography converts a pixel displacement at any
location into millimetres on the ground. Zones report mm from this when the site has a
``plane`` entry; otherwise the scalar scale applies.
"""

from __future__ import annotations

import cv2
import numpy as np


class PlaneScale:
    def __init__(self, image_pts, world_pts_mm):
        src = np.asarray(image_pts, dtype=np.float64).reshape(-1, 1, 2)
        dst = np.asarray(world_pts_mm, dtype=np.float64).reshape(-1, 1, 2)
        if len(src) < 4:
            raise ValueError("a plane scale needs at least four point pairs")
        if len(src) == 4:
            H, inl = cv2.getPerspectiveTransform(src.astype(np.float32), dst.astype(np.float32)), None
        elif len(src) < 8:
            H, inl = cv2.findHomography(src, dst, 0), None          # least squares on all points
        else:
            extent = float(np.ptp(dst.reshape(-1, 2), axis=0).max())
            H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 0.01 * extent)
            if H is None:
                H, inl = cv2.findHomography(src, dst, 0), None
        if H is None:
            raise ValueError("homography estimation failed")
        self.H = H.astype(np.float64)
        self.n_inliers = int(inl.sum()) if inl is not None else len(src)
        proj = cv2.perspectiveTransform(src, self.H).reshape(-1, 2)
        self.rms_mm = float(np.sqrt(np.mean(np.sum((proj - dst.reshape(-1, 2)) ** 2, axis=1))))

    def jacobian(self, x: float, y: float) -> np.ndarray:
        """2x2 d(world)/d(image) at (x, y), in mm per px."""
        h = self.H
        d = h[2, 0] * x + h[2, 1] * y + h[2, 2]
        X = h[0, 0] * x + h[0, 1] * y + h[0, 2]
        Y = h[1, 0] * x + h[1, 1] * y + h[1, 2]
        return np.array([[(h[0, 0] * d - X * h[2, 0]) / d ** 2, (h[0, 1] * d - X * h[2, 1]) / d ** 2],
                         [(h[1, 0] * d - Y * h[2, 0]) / d ** 2, (h[1, 1] * d - Y * h[2, 1]) / d ** 2]])

    def displacement_mm(self, x, y, u, v) -> np.ndarray:
        """Vectorised: (n, 2) ground displacement in mm for pixel displacements (u, v) at (x, y)."""
        x, y, u, v = (np.asarray(a, dtype=np.float64) for a in (x, y, u, v))
        out = np.zeros((len(x), 2))
        for i in range(len(x)):
            out[i] = self.jacobian(x[i], y[i]) @ np.array([u[i], v[i]])
        return out

    def mm_per_px_at(self, x: float, y: float) -> float:
        """Isotropic scale estimate at a point (geometric mean of the Jacobian's singular values)."""
        s = np.linalg.svd(self.jacobian(x, y), compute_uv=False)
        return float(np.sqrt(s[0] * s[1]))

    @classmethod
    def from_dict(cls, d: dict | None):
        if not d or "image_pts" not in d or "world_pts_mm" not in d:
            return None
        return cls(d["image_pts"], d["world_pts_mm"])
