"""Stage A: burst stacking.

A burst is N frames captured within a few seconds. Atmospheric shimmer averages toward zero
across a burst while real displacement does not, so each burst is registered to its first frame
(global translation via phase correlation) and median-stacked into one epoch image.

Status codes:
    OK        burst registered and stacked
    UNSTABLE  inter-frame shift exceeded ``max_shift`` (wind-shaken mount); stacked anyway,
              caller should inflate the epoch's uncertainty
    BLIND     frame contrast below ``min_contrast`` (fog, night); image returned unchanged,
              caller must skip the epoch and report blindness
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

STATUS_OK = "OK"
STATUS_UNSTABLE = "UNSTABLE"
STATUS_BLIND = "BLIND"


def to_gray32(img: np.ndarray) -> np.ndarray:
    """Any image (uint8/uint16/float, gray or BGR) to float32 grayscale in [0, 1]."""
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.dtype == np.uint8:
        return img.astype(np.float32) / 255.0
    if img.dtype == np.uint16:
        return img.astype(np.float32) / 65535.0
    return np.ascontiguousarray(img, dtype=np.float32)


def translate(img: np.ndarray, dx: float, dy: float,
              interpolation: int = cv2.INTER_LANCZOS4) -> np.ndarray:
    """Move image content by (+dx, +dy) pixels (sub-pixel), reflecting borders."""
    m = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)
    return cv2.warpAffine(img, m, (img.shape[1], img.shape[0]),
                          flags=interpolation, borderMode=cv2.BORDER_REFLECT)


def _gauss_peak_1d(cm: float, c0: float, cp: float) -> float:
    if min(cm, c0, cp) <= 0.0:
        den = cm - 2.0 * c0 + cp
        return float(np.clip(0.5 * (cm - cp) / den, -1.0, 1.0)) if den < 0 else 0.0
    lm, l0, lp = np.log(cm), np.log(c0), np.log(cp)
    den = lm - 2.0 * l0 + lp
    return float(np.clip(0.5 * (lm - lp) / den, -1.0, 1.0)) if den < 0 else 0.0


def refine_shift(ref: np.ndarray, img: np.ndarray, dx: float, dy: float,
                 search: int = 3, frac: float = 0.5) -> tuple[float, float, float]:
    """Refine a coarse global shift with ZNCC on a large central template.

    Returns (dx, dy, peak_corr). Phase correlation gives a robust coarse estimate; the ZNCC
    peak with a Gaussian sub-pixel fit gives the precision (a few hundredths of a pixel).
    """
    h, w = ref.shape[:2]
    th, tw = int(h * frac) | 1, int(w * frac) | 1
    cy, cx = h // 2, w // 2
    hh, hw = th // 2, tw // 2
    ix, iy = int(round(dx)), int(round(dy))
    y0, y1 = cy - hh + iy - search, cy + hh + iy + search + 1
    x0, x1 = cx - hw + ix - search, cx + hw + ix + search + 1
    if y0 < 0 or x0 < 0 or y1 > h or x1 > w:
        return float(dx), float(dy), float("nan")
    tpl = ref[cy - hh:cy + hh + 1, cx - hw:cx + hw + 1]
    win = img[y0:y1, x0:x1]
    r = cv2.matchTemplate(np.ascontiguousarray(win), np.ascontiguousarray(tpl),
                          cv2.TM_CCOEFF_NORMED)
    py, px = np.unravel_index(int(np.argmax(r)), r.shape)
    side = 2 * search + 1
    if px in (0, side - 1) or py in (0, side - 1):
        return float(dx), float(dy), float(r[py, px])
    ddx = _gauss_peak_1d(r[py, px - 1], r[py, px], r[py, px + 1])
    ddy = _gauss_peak_1d(r[py - 1, px], r[py, px], r[py + 1, px])
    return float(ix + px - search + ddx), float(iy + py - search + ddy), float(r[py, px])


def shift_of(ref: np.ndarray, img: np.ndarray, downscale: int = 2,
             refine: bool = True) -> tuple[float, float, float]:
    """Global displacement of content in ``img`` relative to ``ref``.

    Returns (dx, dy, response) in full-resolution pixels: content in ``img`` sits at
    (+dx, +dy) from where it sits in ``ref``. ``cv2.phaseCorrelate`` on Hanning-windowed,
    downscaled copies gives the coarse shift; a ZNCC match of a large central template
    refines it to sub-pixel precision.
    """
    if downscale > 1:
        r = cv2.resize(ref, None, fx=1.0 / downscale, fy=1.0 / downscale,
                       interpolation=cv2.INTER_AREA)
        i = cv2.resize(img, None, fx=1.0 / downscale, fy=1.0 / downscale,
                       interpolation=cv2.INTER_AREA)
    else:
        r, i = ref, img
    win = cv2.createHanningWindow((r.shape[1], r.shape[0]), cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(r, i, win)
    dx, dy = float(dx * downscale), float(dy * downscale)
    if refine:
        rdx, rdy, _ = refine_shift(ref, img, dx, dy)
        dx, dy = rdx, rdy
    return dx, dy, float(resp)


@dataclass
class StackResult:
    image: np.ndarray          # float32 gray, epoch image
    status: str                # OK | UNSTABLE | BLIND
    shifts: np.ndarray         # (N, 2) per-frame (dx, dy) relative to frame 0
    contrast: float            # std of frame 0 intensities
    n_frames: int

    @property
    def max_shift(self) -> float:
        if len(self.shifts) == 0:
            return 0.0
        return float(np.max(np.hypot(self.shifts[:, 0], self.shifts[:, 1])))


def stack_burst(frames: list[np.ndarray], max_shift: float = 3.0,
                min_contrast: float = 0.02, downscale: int = 2) -> StackResult:
    """Register frames 2..N to frame 1 and median-stack them."""
    if len(frames) == 0:
        raise ValueError("stack_burst needs at least one frame")
    grays = [to_gray32(f) for f in frames]
    ref = grays[0]
    contrast = float(ref.std())
    if contrast < min_contrast:
        return StackResult(ref, STATUS_BLIND, np.zeros((len(grays), 2), np.float32),
                           contrast, len(grays))
    aligned = [ref]
    shifts = [(0.0, 0.0)]
    for g in grays[1:]:
        dx, dy, _ = shift_of(ref, g, downscale)
        shifts.append((dx, dy))
        aligned.append(translate(g, -dx, -dy))
    stacked = np.median(np.stack(aligned, axis=0), axis=0).astype(np.float32)
    shifts_arr = np.asarray(shifts, dtype=np.float32)
    status = STATUS_OK
    if np.max(np.hypot(shifts_arr[:, 0], shifts_arr[:, 1])) > max_shift:
        status = STATUS_UNSTABLE
    return StackResult(stacked, status, shifts_arr, contrast, len(grays))
