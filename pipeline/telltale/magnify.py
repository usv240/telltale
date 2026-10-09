"""Motion magnification: make sub-pixel creep visible.

The measured displacement field is dense but tiny (tenths of a pixel). To show a person what
the instrument sees, the reference image is warped by ``gain`` times the measured field, so a
0.3 px creep becomes a 15 px motion at gain 50. Interpolating the sparse subset grid to a dense
flow field and re-sampling with ``cv2.remap`` is all classical imgproc; nothing is invented, the
motion is the measurement, amplified.

Used by the CLI (``telltale magnify``) to render an animated sequence for the video and by the
dashboard's overlay generation when requested.
"""

from __future__ import annotations

import cv2
import numpy as np

from .dic import DisplacementField


def dense_flow(fld: DisplacementField, shape: tuple, smooth_sigma: float = 0.0) -> np.ndarray:
    """Dense (H, W, 2) flow in px from the subset grid; invalid subsets are filled from
    neighbours by normalised convolution so holes do not tear the warp."""
    h, w = shape[:2]
    xs_u, ys_u = np.unique(fld.xs), np.unique(fld.ys)
    gi = np.searchsorted(xs_u, fld.xs)
    gj = np.searchsorted(ys_u, fld.ys)
    gu = np.zeros((len(ys_u), len(xs_u)), np.float32)
    gv = np.zeros_like(gu)
    wt = np.zeros_like(gu)
    v = fld.valid
    gu[gj[v], gi[v]] = fld.u[v]
    gv[gj[v], gi[v]] = fld.v[v]
    wt[gj[v], gi[v]] = 1.0
    k = (5, 5)
    num_u = cv2.blur(gu, k)
    num_v = cv2.blur(gv, k)
    den = cv2.blur(wt, k)
    fill = den > 1e-3
    gu = np.where(wt > 0, gu, np.where(fill, num_u / np.maximum(den, 1e-6), 0.0)).astype(np.float32)
    gv = np.where(wt > 0, gv, np.where(fill, num_v / np.maximum(den, 1e-6), 0.0)).astype(np.float32)
    # place the coarse grid at the subset centres and interpolate to full resolution
    fu = cv2.resize(gu, (w, h), interpolation=cv2.INTER_CUBIC)
    fv = cv2.resize(gv, (w, h), interpolation=cv2.INTER_CUBIC)
    if smooth_sigma > 0:
        fu = cv2.GaussianBlur(fu, (0, 0), smooth_sigma)
        fv = cv2.GaussianBlur(fv, (0, 0), smooth_sigma)
    return np.dstack([fu, fv])


def magnify(ref: np.ndarray, fld: DisplacementField, gain: float = 30.0,
            smooth_sigma: float = 8.0) -> np.ndarray:
    """Warp ``ref`` by ``gain`` x the measured displacement (forward motion rendered via
    backward sampling with ``cv2.remap``)."""
    h, w = ref.shape[:2]
    flow = dense_flow(fld, ref.shape, smooth_sigma) * float(gain)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = xx - flow[..., 0]
    map_y = yy - flow[..., 1]
    return cv2.remap(ref, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def magnified_sequence(ref: np.ndarray, fields: list[DisplacementField], gain: float = 30.0,
                       smooth_sigma: float = 8.0) -> list[np.ndarray]:
    """One magnified frame per epoch; play them back to see the creep as motion."""
    return [magnify(ref, f, gain, smooth_sigma) for f in fields]
