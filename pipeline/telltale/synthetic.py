"""Synthetic truth machine: exact sub-pixel shifts (E1) and a collapse simulator (E3 rehearsal).

Shift generator: an image is supersampled 8x with Lanczos, shifted by an integer number of
supersampled pixels, and downsampled back with area averaging. The shift is therefore exactly
known (multiples of 1/8 px) and the resampling is realistic. Both the reference and the shifted
image go through the same resampling path so that resampling itself is not mistaken for motion.

Collapse simulator: a target region moves with Voight kinematics for alpha = 2,
d(t) = A ln(tf / (tf - t)), i.e. velocity accelerating as A / (tf - t), against a static
background, with illumination drift, noise, and optional camera jitter. The pipeline runs on the
rendered epochs and its forecast is compared with the true failure time tf.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


def make_texture(h: int, w: int, seed: int = 0, scales=(1, 2, 4, 8, 16)) -> np.ndarray:
    """Multi-scale random speckle in [0, 1] (float32); stands in for rock or soil texture."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((h, w), np.float32)
    for s in scales:
        noise = rng.standard_normal((h // s + 2, w // s + 2)).astype(np.float32)
        up = cv2.resize(noise, (w, h), interpolation=cv2.INTER_CUBIC)
        acc += up / np.sqrt(s)
    acc = (acc - acc.mean()) / (acc.std() + 1e-9)
    # +-3 sigma maps to [0.2, 0.8] so illumination gains up to 1.2 do not clip the texture
    return np.clip(0.5 + acc / 10.0, 0.0, 1.0).astype(np.float32)


def supersample(img: np.ndarray, ss: int) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (w * ss, h * ss), interpolation=cv2.INTER_LANCZOS4)


def downsample(big: np.ndarray, ss: int) -> np.ndarray:
    h, w = big.shape[0] // ss, big.shape[1] // ss
    return cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA)


def integer_shift(big: np.ndarray, ix: int, iy: int) -> np.ndarray:
    m = np.array([[1.0, 0.0, ix], [0.0, 1.0, iy]], dtype=np.float32)
    return cv2.warpAffine(big, m, (big.shape[1], big.shape[0]), flags=cv2.INTER_NEAREST,
                          borderMode=cv2.BORDER_REFLECT)


def perturb(img: np.ndarray, noise: float = 0.0, gain: float = 1.0, bias: float = 0.0,
            blur: float = 0.0, rng: np.random.Generator | None = None) -> np.ndarray:
    out = img * gain + bias
    if blur > 0:
        out = cv2.GaussianBlur(out, (0, 0), blur)
    if noise > 0:
        rng = rng or np.random.default_rng(0)
        out = out + rng.standard_normal(out.shape).astype(np.float32) * noise
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def shift_image(img: np.ndarray, dx: float, dy: float, ss: int = 8, noise: float = 0.0,
                gain: float = 1.0, bias: float = 0.0, blur: float = 0.0, seed: int = 0,
                crop: int = 16) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    """Return (reference, shifted, (dx_actual, dy_actual)); content moves by (+dx, +dy)."""
    ix, iy = int(round(dx * ss)), int(round(dy * ss))
    big = supersample(img, ss)
    ref = downsample(big, ss)
    shifted = downsample(integer_shift(big, ix, iy), ss)
    shifted = perturb(shifted, noise, gain, bias, blur, np.random.default_rng(seed))
    if crop > 0:
        ref = ref[crop:-crop, crop:-crop]
        shifted = shifted[crop:-crop, crop:-crop]
    return np.ascontiguousarray(ref), np.ascontiguousarray(shifted), (ix / ss, iy / ss)


def voight_displacement(t: np.ndarray, tf: float, amp: float) -> np.ndarray:
    """d(t) = A ln(tf / (tf - t)); velocity A / (tf - t); alpha = 2 creep to failure at tf."""
    t = np.asarray(t, dtype=np.float64)
    return amp * np.log(tf / (tf - t))


@dataclass
class CollapseScene:
    frames: list                 # one float32 gray image per epoch (already "stacked")
    times: np.ndarray            # epoch times
    true_disp: np.ndarray        # true target displacement magnitude per epoch, px
    true_u: np.ndarray
    true_v: np.ndarray
    tf: float                    # true failure time
    zone_poly: list              # target zone polygon [(x, y), ...]
    stable_poly: list            # stable region polygon
    jitter: np.ndarray           # (N, 2) camera jitter applied per epoch
    meta: dict = field(default_factory=dict)


def simulate_collapse(h: int = 256, w: int = 256, n_epochs: int = 40, tf: float = 50.0,
                      t_end: float = 47.0, amp: float = 2.0, direction=(1.0, 0.5),
                      ss: int = 8, noise: float = 0.01, illum_drift: float = 0.1,
                      jitter_px: float = 0.0, seed: int = 0) -> CollapseScene:
    """Render an epoch sequence in which the lower-right target zone creeps to failure."""
    rng = np.random.default_rng(seed)
    tex = make_texture(h, w, seed)
    big = supersample(tex, ss)
    bh, bw = big.shape

    x0, y0 = int(w * 0.45), int(h * 0.30)
    zone_poly = [(x0, y0), (w - 1, y0), (w - 1, h - 1), (x0, h - 1)]
    stable_poly = [(0, 0), (x0 - 8, 0), (x0 - 8, h - 1), (0, h - 1)]
    zone_mask = np.zeros((bh, bw), np.uint8)
    cv2.fillPoly(zone_mask, [np.int32([(x * ss, y * ss) for x, y in zone_poly])], 255)
    zone_big = zone_mask > 0

    times = np.linspace(0.0, t_end, n_epochs)
    d = voight_displacement(times, tf, amp)
    dvec = np.asarray(direction, dtype=np.float64)
    dvec /= np.linalg.norm(dvec)
    ix = np.round(d * dvec[0] * ss).astype(int)
    iy = np.round(d * dvec[1] * ss).astype(int)
    true_u, true_v = ix / ss, iy / ss

    frames, jit = [], []
    for k in range(n_epochs):
        moved = integer_shift(big, int(ix[k]), int(iy[k]))
        comp = np.where(zone_big, moved, big)
        frame = downsample(comp, ss)
        gain = 1.0 + illum_drift * np.sin(2 * np.pi * k / max(1, n_epochs) * 1.7)
        frame = perturb(frame, noise=noise, gain=gain, bias=0.0, rng=rng)
        jx = jy = 0.0
        if jitter_px > 0 and k > 0:
            jx, jy = rng.uniform(-jitter_px, jitter_px, size=2)
            m = np.array([[1.0, 0.0, jx], [0.0, 1.0, jy]], dtype=np.float32)
            frame = cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LANCZOS4,
                                   borderMode=cv2.BORDER_REFLECT)
        frames.append(frame)
        jit.append((jx, jy))

    return CollapseScene(frames, times, np.hypot(true_u, true_v), true_u, true_v, tf,
                         zone_poly, stable_poly, np.asarray(jit, dtype=np.float64),
                         {"amp": amp, "noise": noise, "illum_drift": illum_drift,
                          "jitter_px": jitter_px, "seed": seed})
