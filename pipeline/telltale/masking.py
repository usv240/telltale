"""Stage D: masking over time. Vegetation and water decorrelate; exclude them honestly."""

from __future__ import annotations

import cv2
import numpy as np


def variance_mask(epochs: list[np.ndarray], blur_sigma: float = 3.0,
                  quantile: float = 0.90, kernel: int = 7) -> np.ndarray:
    """uint8 mask (255 = usable) excluding pixels whose temporal variance is in the top quantile.

    Call this on stabilized epochs over a trailing window; high-variance regions are foliage,
    water, or shadow edges and would otherwise emit noise displacement.
    """
    if len(epochs) < 2:
        return np.full(epochs[0].shape[:2], 255, np.uint8)
    stack = np.stack([e.astype(np.float32) for e in epochs], axis=0)
    var = stack.var(axis=0)
    var = cv2.GaussianBlur(var, (0, 0), blur_sigma)
    thr = float(np.quantile(var, quantile))
    bad = (var > thr).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel))
    bad = cv2.morphologyEx(bad, cv2.MORPH_CLOSE, k)
    bad = cv2.morphologyEx(bad, cv2.MORPH_OPEN, k)
    contours, _ = cv2.findContours(bad, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    good = np.full(var.shape, 255, np.uint8)
    cv2.drawContours(good, contours, -1, 0, thickness=-1)
    return good
