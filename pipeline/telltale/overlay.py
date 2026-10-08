"""Displacement overlays rendered with OpenCV only: magnitude heatmap plus vectors."""

from __future__ import annotations

import cv2
import numpy as np

from .dic import DisplacementField
from .stabilize import to_u8


def render_overlay(gray: np.ndarray, fld: DisplacementField, vmax: float | None = None,
                   alpha: float = 0.55, arrow_every: int = 2, arrow_scale: float = 8.0,
                   label: str | None = None) -> np.ndarray:
    """BGR uint8 image: epoch in gray, valid displacement magnitude as a heatmap, arrows on top."""
    base = cv2.cvtColor(to_u8(gray), cv2.COLOR_GRAY2BGR)
    if len(fld.xs) == 0:
        return base
    xs_u, ys_u = np.unique(fld.xs), np.unique(fld.ys)
    gi = np.searchsorted(xs_u, fld.xs)
    gj = np.searchsorted(ys_u, fld.ys)
    mag_grid = np.zeros((len(ys_u), len(xs_u)), np.float32)
    wgt_grid = np.zeros_like(mag_grid)
    valid = fld.valid
    mag = np.hypot(fld.u, fld.v)
    mag_grid[gj[valid], gi[valid]] = mag[valid]
    wgt_grid[gj[valid], gi[valid]] = 1.0
    if vmax is None:
        vmax = float(np.percentile(mag[valid], 98)) if valid.any() else 1.0
    vmax = max(vmax, 1e-6)

    h, w = gray.shape[:2]
    mag_full = cv2.resize(mag_grid, (w, h), interpolation=cv2.INTER_CUBIC)
    wgt_full = cv2.resize(wgt_grid, (w, h), interpolation=cv2.INTER_LINEAR)
    heat = cv2.applyColorMap(np.clip(mag_full / vmax * 255, 0, 255).astype(np.uint8),
                             cv2.COLORMAP_JET)
    a = (np.clip(wgt_full, 0, 1) * alpha)[..., None]
    out = (base * (1 - a) + heat * a).astype(np.uint8)

    for k in np.nonzero(valid)[0][::arrow_every]:
        x, y = int(fld.xs[k]), int(fld.ys[k])
        x2 = int(round(x + fld.u[k] * arrow_scale))
        y2 = int(round(y + fld.v[k] * arrow_scale))
        cv2.arrowedLine(out, (x, y), (x2, y2), (255, 255, 255), 1, cv2.LINE_AA, tipLength=0.3)
    if label:
        cv2.putText(out, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1,
                    cv2.LINE_AA)
    return out


def render_status_map(gray: np.ndarray, fld: DisplacementField) -> np.ndarray:
    """Each subset drawn as a dot colored by status (green OK, gray low texture, red rejected)."""
    out = cv2.cvtColor(to_u8(gray), cv2.COLOR_GRAY2BGR)
    colors = {0: (0, 200, 0), 1: (128, 128, 128), 2: (0, 0, 220), 3: (0, 140, 255),
              4: (255, 0, 200), 5: (200, 0, 0)}
    for x, y, s in zip(fld.xs, fld.ys, fld.status):
        cv2.circle(out, (int(x), int(y)), 3, colors.get(int(s), (255, 255, 255)), -1, cv2.LINE_AA)
    return out
