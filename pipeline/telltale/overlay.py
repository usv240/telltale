"""Displacement overlays rendered with OpenCV only: a single-hue magnitude ramp plus vectors."""

from __future__ import annotations

import cv2
import numpy as np

from .dic import DisplacementField
from .stabilize import to_u8


# The one data hue of the dashboard (#1d5fbf), in BGR.
DATA_HUE_BGR = (191, 95, 29)


def render_overlay(gray: np.ndarray, fld: DisplacementField, vmax: float | None = None,
                   alpha: float = 0.72, arrow_every: int = 2, arrow_scale: float = 8.0,
                   label: str | None = None, burn_label: bool = False,
                   hue_bgr: tuple = DATA_HUE_BGR) -> np.ndarray:
    """BGR uint8 image: the epoch in grey, displacement magnitude as a single-hue ramp from the
    photograph (no motion) to the data hue (the largest motion), arrows for direction.

    A single hue keeps the picture readable as a photograph and carries magnitude in one
    ordered dimension; a rainbow map (JET) invents boundaries where the colour bands change.
    Labels are not burned into the pixels by default; the dashboard captions the image."""
    base = cv2.cvtColor(to_u8(gray), cv2.COLOR_GRAY2BGR).astype(np.float32)
    if len(fld.xs) == 0:
        return base.astype(np.uint8)
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
    strength = np.clip(mag_full / vmax, 0.0, 1.0) * np.clip(wgt_full, 0.0, 1.0) * alpha
    # lift the photograph slightly so the ramp reads against it
    base = base * 0.82 + 255 * 0.18
    hue = np.array(hue_bgr, np.float32)[None, None, :]
    out = (base * (1 - strength[..., None]) + hue * strength[..., None]).astype(np.uint8)

    for k in np.nonzero(valid)[0][::arrow_every]:
        if mag[k] < 0.15 * vmax or mag[k] * arrow_scale < 3:
            continue        # still ground: no arrow, or it renders as a dot
        x, y = int(fld.xs[k]), int(fld.ys[k])
        x2 = int(round(x + fld.u[k] * arrow_scale))
        y2 = int(round(y + fld.v[k] * arrow_scale))
        cv2.arrowedLine(out, (x, y), (x2, y2), (20, 20, 20), 3, cv2.LINE_AA, tipLength=0.3)
        cv2.arrowedLine(out, (x, y), (x2, y2), (255, 255, 255), 1, cv2.LINE_AA, tipLength=0.3)
    if label and burn_label:
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
