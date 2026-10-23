"""Stage C: digital image correlation, the measurement.

For each subset center on a regular grid, the reference subset (template) is matched against a
search window in the current epoch with zero-normalized cross-correlation
(``cv2.matchTemplate`` / ``TM_CCOEFF_NORMED``), which is invariant to affine illumination
change. The integer peak is refined with a 2D paraboloid fit over its 3x3 neighborhood. Each
subset carries its own quality metrics and a status code; only status 0 contributes to a zone
measurement. A random 10 percent of valid subsets is cross-checked with ``cv2.phaseCorrelate``;
if the two estimators disagree, the epoch is flagged for review.

Displacement convention: (u, v) is where the reference content now sits in the current epoch,
in pixels, +u right and +v down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .config import GridConfig, polygon_mask

STATUS_OK = 0
STATUS_LOW_TEXTURE = 1
STATUS_LOW_CORR = 2
STATUS_LOW_MARGIN = 3
STATUS_OUT_OF_BOUND = 4
STATUS_EDGE_PEAK = 5
STATUS_NAMES = {
    STATUS_OK: "OK",
    STATUS_LOW_TEXTURE: "LOW_TEXTURE",
    STATUS_LOW_CORR: "LOW_CORR",
    STATUS_LOW_MARGIN: "LOW_MARGIN",
    STATUS_OUT_OF_BOUND: "OUT_OF_BOUND",
    STATUS_EDGE_PEAK: "EDGE_PEAK",
}

# Least-squares paraboloid over the 3x3 neighborhood: f = a x^2 + b y^2 + c xy + d x + e y + f0.
_YY, _XX = np.mgrid[-1:2, -1:2]
_A = np.stack([_XX.ravel() ** 2, _YY.ravel() ** 2, (_XX * _YY).ravel(),
               _XX.ravel(), _YY.ravel(), np.ones(9)], axis=1).astype(np.float64)
_PINV = np.linalg.pinv(_A)


def _parabola_1d(cm: float, c0: float, cp: float) -> float:
    den = cm - 2.0 * c0 + cp
    if den >= 0.0:
        return 0.0
    return float(np.clip(0.5 * (cm - cp) / den, -1.0, 1.0))


def _gaussian_1d(cm: float, c0: float, cp: float) -> float:
    """Three-point Gaussian peak fit (parabola in log space); falls back to a parabola."""
    if min(cm, c0, cp) <= 0.0:
        return _parabola_1d(cm, c0, cp)
    lm, l0, lp = np.log(cm), np.log(c0), np.log(cp)
    den = lm - 2.0 * l0 + lp
    if den >= 0.0:
        return 0.0
    return float(np.clip(0.5 * (lm - lp) / den, -1.0, 1.0))


def subpixel_peak_paraboloid(nb: np.ndarray) -> tuple[float, float]:
    """Least-squares 2D paraboloid over the 3x3 neighborhood (kept for comparison in E1)."""
    a, b, c, d, e, _ = _PINV @ nb.astype(np.float64).ravel()
    det = 4.0 * a * b - c * c
    if a < 0.0 and det > 0.0:
        dx = (c * e - 2.0 * b * d) / det
        dy = (c * d - 2.0 * a * e) / det
        if abs(dx) <= 1.0 and abs(dy) <= 1.0:
            return float(dx), float(dy)
    return (_parabola_1d(nb[1, 0], nb[1, 1], nb[1, 2]),
            _parabola_1d(nb[0, 1], nb[1, 1], nb[2, 1]))


def subpixel_peak(nb: np.ndarray) -> tuple[float, float]:
    """Sub-pixel offset of the maximum of a 3x3 correlation neighborhood.

    Separable three-point Gaussian fits per axis. On the E1 synthetic sweep this shows about a
    third of the pixel-locking bias of a paraboloid fit (0.02 px versus 0.06 px median error).
    """
    return (_gaussian_1d(nb[1, 0], nb[1, 1], nb[1, 2]),
            _gaussian_1d(nb[0, 1], nb[1, 1], nb[2, 1]))


_RESAMPLE_MARGIN = 5  # Lanczos4 support plus one, so the cropped window has no border effects


def _resample_refine(cur: np.ndarray, tpl: np.ndarray, x: int, y: int, u: float, v: float,
                     half: int) -> tuple[float, float, bool]:
    """One pass of sub-pixel re-sampling refinement.

    The current-epoch window is shifted by the fractional part of the estimate (Lanczos), so
    the remaining offset is near zero where the three-point peak fit is least biased. Returns
    the updated (u, v) and whether the pass could be applied.
    """
    iu, iv = int(round(u)), int(round(v))
    fu, fv = u - iu, v - iv
    m = _RESAMPLE_MARGIN
    y0, y1 = y + iv - half - m, y + iv + half + m + 1
    x0, x1 = x + iu - half - m, x + iu + half + m + 1
    h, w = cur.shape
    if y0 < 0 or x0 < 0 or y1 > h or x1 > w:
        return u, v, False
    big = cur[y0:y1, x0:x1]
    mat = np.array([[1.0, 0.0, -fu], [0.0, 1.0, -fv]], dtype=np.float32)
    big = cv2.warpAffine(big, mat, (big.shape[1], big.shape[0]), flags=cv2.INTER_LANCZOS4,
                         borderMode=cv2.BORDER_REFLECT)
    win = big[m - 1:-(m - 1), m - 1:-(m - 1)]          # template + 2 on each axis
    r = cv2.matchTemplate(np.ascontiguousarray(win), tpl, cv2.TM_CCOEFF_NORMED)
    py, px = np.unravel_index(int(np.argmax(r)), r.shape)
    if px != 1 or py != 1:
        return u, v, False
    ddx, ddy = subpixel_peak(r)
    return float(u + ddx), float(v + ddy), True


def texture_map(ref: np.ndarray, template: int) -> np.ndarray:
    """Per-pixel mean minimum eigenvalue of the structure tensor over a template-sized box."""
    me = cv2.cornerMinEigenVal(ref, blockSize=3, ksize=3)
    return cv2.boxFilter(me, -1, (template, template), normalize=True)


def grid_centers(shape: tuple, grid: GridConfig,
                 mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Subset centers (xs, ys) on a regular grid that fit template plus search inside the image."""
    h, w = shape[:2]
    half = grid.template // 2
    margin = half + grid.search
    ys = np.arange(margin, h - margin, grid.stride)
    xs = np.arange(margin, w - margin, grid.stride)
    gx, gy = np.meshgrid(xs, ys)
    gx, gy = gx.ravel(), gy.ravel()
    if mask is not None:
        keep = mask[gy, gx] > 0
        gx, gy = gx[keep], gy[keep]
    return gx.astype(np.int32), gy.astype(np.int32)


@dataclass
class DisplacementField:
    xs: np.ndarray
    ys: np.ndarray
    u: np.ndarray
    v: np.ndarray
    corr: np.ndarray
    margin: np.ndarray
    texture: np.ndarray
    status: np.ndarray
    shape: tuple
    template: int
    stride: int
    search: int
    crosscheck_px: float = float("nan")
    review: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def valid(self) -> np.ndarray:
        return self.status == STATUS_OK

    @property
    def n_valid(self) -> int:
        return int(self.valid.sum())

    @property
    def coverage(self) -> float:
        return float(self.n_valid / max(1, len(self.status)))

    def status_counts(self) -> dict:
        return {name: int((self.status == code).sum()) for code, name in STATUS_NAMES.items()}

    def save(self, path: str | Path) -> None:
        np.savez_compressed(
            path, xs=self.xs, ys=self.ys, u=self.u, v=self.v, corr=self.corr,
            margin=self.margin, texture=self.texture, status=self.status,
            shape=np.asarray(self.shape), template=self.template, stride=self.stride,
            search=self.search, crosscheck_px=self.crosscheck_px, review=self.review)

    @classmethod
    def load(cls, path: str | Path) -> "DisplacementField":
        z = np.load(path)
        return cls(z["xs"], z["ys"], z["u"], z["v"], z["corr"], z["margin"], z["texture"],
                   z["status"], tuple(int(s) for s in z["shape"]), int(z["template"]),
                   int(z["stride"]), int(z["search"]), float(z["crosscheck_px"]),
                   bool(z["review"]))


def _crosscheck(ref: np.ndarray, cur: np.ndarray, xs, ys, u, v, valid, half: int,
                frac: float, rng: np.random.Generator, max_samples: int = 200) -> float:
    """Median disagreement (px) between ZNCC and phase correlation on a random subset sample.

    Phase correlation on small patches is only accurate to a few tenths of a pixel, so this is
    a gross-error detector (wrong peak, decorrelated scene), not a precision check. Patches are
    twice the template size to give the spectral estimator enough support.
    """
    idx = np.nonzero(valid)[0]
    if len(idx) == 0 or frac <= 0:
        return float("nan")
    n = int(min(max_samples, max(1, round(frac * len(idx)))))
    pick = rng.choice(idx, size=n, replace=False)
    ph = 2 * half
    size = 2 * ph + 1
    win = cv2.createHanningWindow((size, size), cv2.CV_32F)
    h, w = ref.shape
    dis = []
    for i in pick:
        x, y = int(xs[i]), int(ys[i])
        iu, iv = int(round(u[i])), int(round(v[i]))
        x2, y2 = x + iu, y + iv
        if (y - ph < 0 or x - ph < 0 or y + ph + 1 > h or x + ph + 1 > w
                or y2 - ph < 0 or x2 - ph < 0 or y2 + ph + 1 > h or x2 + ph + 1 > w):
            continue
        a = ref[y - ph:y + ph + 1, x - ph:x + ph + 1]
        b = cur[y2 - ph:y2 + ph + 1, x2 - ph:x2 + ph + 1]
        (sx, sy), _ = cv2.phaseCorrelate(np.ascontiguousarray(a), np.ascontiguousarray(b), win)
        dis.append(np.hypot(iu + sx - u[i], iv + sy - v[i]))
    return float(np.median(dis)) if dis else float("nan")


def compute_field(ref: np.ndarray, cur: np.ndarray, grid: GridConfig | None = None,
                  mask: np.ndarray | None = None, seed: int = 0,
                  crosscheck_frac: float = 0.1, crosscheck_tol: float = 1.0,
                  prior_flow: np.ndarray | None = None) -> DisplacementField:
    """Dense sub-pixel displacement of ``cur`` relative to ``ref`` (float32 gray, same shape).

    ``prior_flow`` (H, W, 2), optional: a predicted displacement field. Each subset's search
    window is centred on its rounded prediction, so the search radius only has to cover the
    residual. Used by ``compute_field_pyramid`` to follow motions far larger than the search.
    """
    grid = grid or GridConfig()
    if ref.shape != cur.shape:
        raise ValueError("reference and current epoch must have the same shape")
    ref = np.ascontiguousarray(ref, dtype=np.float32)
    cur = np.ascontiguousarray(cur, dtype=np.float32)
    if grid.search_dtype == "uint8":
        # The integer search and first peak fit run on 8-bit copies (the build's fastest
        # matchTemplate path); the re-sampling refinement below still runs on float32, so the
        # quantisation only perturbs the starting estimate it corrects.
        ref_s = np.clip(np.rint(ref * 255.0), 0, 255).astype(np.uint8)
        cur_s = np.clip(np.rint(cur * 255.0), 0, 255).astype(np.uint8)
    else:
        ref_s, cur_s = ref, cur
    half, s = grid.template // 2, grid.search
    xs, ys = grid_centers(ref.shape, grid, mask)
    n = len(xs)
    u = np.zeros(n, np.float32)
    v = np.zeros(n, np.float32)
    corr = np.zeros(n, np.float32)
    margin = np.zeros(n, np.float32)
    status = np.zeros(n, np.int8)
    tex = texture_map(ref, grid.template)[ys, xs].astype(np.float32) if n else np.zeros(0, np.float32)
    side = 2 * s + 1
    if prior_flow is not None and n:
        ox_all = np.rint(prior_flow[ys, xs, 0]).astype(np.int32)
        oy_all = np.rint(prior_flow[ys, xs, 1]).astype(np.int32)
    else:
        ox_all = np.zeros(n, np.int32)
        oy_all = np.zeros(n, np.int32)
    H, W = ref.shape

    def one(i: int) -> None:
        if tex[i] < grid.min_texture:
            status[i] = STATUS_LOW_TEXTURE
            return
        x, y = int(xs[i]), int(ys[i])
        ox, oy = int(ox_all[i]), int(oy_all[i])
        tpl = ref[y - half:y + half + 1, x - half:x + half + 1]
        y0, y1 = y + oy - half - s, y + oy + half + s + 1
        x0, x1 = x + ox - half - s, x + ox + half + s + 1
        if y0 < 0 or x0 < 0 or y1 > H or x1 > W:
            status[i] = STATUS_OUT_OF_BOUND
            return
        r = cv2.matchTemplate(cur_s[y0:y1, x0:x1], ref_s[y - half:y + half + 1, x - half:x + half + 1],
                              cv2.TM_CCOEFF_NORMED)
        py, px = np.unravel_index(int(np.argmax(r)), r.shape)
        peak = float(r[py, px])
        corr[i] = peak
        if not np.isfinite(peak) or peak < grid.min_corr:
            status[i] = STATUS_LOW_CORR
            return
        if px == 0 or py == 0 or px == side - 1 or py == side - 1:
            status[i] = STATUS_EDGE_PEAK
            return
        r2 = r.copy()
        r2[max(0, py - 3):py + 4, max(0, px - 3):px + 4] = -np.inf
        second = float(r2.max()) if np.isfinite(r2).any() else -1.0
        margin[i] = peak - second
        if margin[i] < grid.min_margin:
            status[i] = STATUS_LOW_MARGIN
            return
        ddx, ddy = subpixel_peak(r[py - 1:py + 2, px - 1:px + 2])
        ui, vi = ox + px - s + ddx, oy + py - s + ddy
        for _ in range(grid.refine_iters):
            ui, vi, ok = _resample_refine(cur, tpl, x, y, ui, vi, half)
            if not ok:
                break
        u[i], v[i] = ui, vi
        if np.hypot(u[i] - ox, v[i] - oy) > grid.max_disp:
            status[i] = STATUS_OUT_OF_BOUND

    # matchTemplate and warpAffine release the GIL, so a thread pool over subsets scales with
    # cores; each subset writes only its own index, so no locking is needed.
    n_threads = grid.threads if grid.threads > 0 else max(1, cv2.getNumberOfCPUs())
    if n_threads > 1 and n >= 64:
        from concurrent.futures import ThreadPoolExecutor
        chunk = max(16, n // (n_threads * 4))
        with ThreadPoolExecutor(max_workers=n_threads) as ex:
            list(ex.map(lambda rng_: [one(i) for i in rng_],
                        [range(a, min(n, a + chunk)) for a in range(0, n, chunk)]))
    else:
        for i in range(n):
            one(i)

    fld = DisplacementField(xs, ys, u, v, corr, margin, tex, status, ref.shape,
                            grid.template, grid.stride, grid.search)
    rng = np.random.default_rng(seed)
    fld.crosscheck_px = _crosscheck(ref, cur, xs, ys, u, v, fld.valid, half,
                                    crosscheck_frac, rng)
    fld.review = bool(np.isfinite(fld.crosscheck_px) and fld.crosscheck_px > crosscheck_tol)
    return fld


def compute_field_pyramid(ref: np.ndarray, cur: np.ndarray, grid: GridConfig | None = None,
                          mask: np.ndarray | None = None, seed: int = 0, levels: int | None = None,
                          crosscheck_frac: float = 0.1, crosscheck_tol: float = 1.0) -> DisplacementField:
    """Coarse-to-fine DIC. The images are reduced ``levels`` times with ``cv2.pyrDown``; the
    coarse field (same search radius, so 2^levels times the reach) becomes a dense prediction
    by normalised-convolution infill; each finer level searches only the residual around the
    upsampled prediction. A fixed-reference site can then follow motions of tens of pixels
    without chaining, so measurement error does not accumulate as a random walk."""
    from .magnify import dense_flow
    grid = grid or GridConfig()
    L = grid.pyramid_levels if levels is None else levels
    if L <= 0:
        return compute_field(ref, cur, grid, mask, seed, crosscheck_frac, crosscheck_tol)
    refs = [np.ascontiguousarray(ref, np.float32)]
    curs = [np.ascontiguousarray(cur, np.float32)]
    masks = [mask]
    for _ in range(L):
        refs.append(cv2.pyrDown(refs[-1]))
        curs.append(cv2.pyrDown(curs[-1]))
        m = masks[-1]
        masks.append(None if m is None else cv2.resize(m, (refs[-1].shape[1], refs[-1].shape[0]),
                                                     interpolation=cv2.INTER_NEAREST))
    flow = None
    for lvl in range(L, 0, -1):
        f = 2 ** lvl
        g = GridConfig(template=max(15, (grid.template // f) | 1), stride=max(6, grid.stride // f),
                       search=grid.search, min_corr=grid.min_corr, min_margin=grid.min_margin,
                       min_texture=grid.min_texture / f, refine_iters=0, threads=grid.threads)
        fld = compute_field(refs[lvl], curs[lvl], g, masks[lvl], seed, crosscheck_frac=0.0, prior_flow=flow)
        if fld.n_valid:
            dense = dense_flow(fld, refs[lvl].shape, smooth_sigma=2.0)
        else:
            dense = np.zeros(refs[lvl].shape + (2,), np.float32)
        h, w = refs[lvl - 1].shape
        flow = cv2.resize(dense, (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
    out = compute_field(refs[0], curs[0], grid, mask, seed, crosscheck_frac, crosscheck_tol, prior_flow=flow)
    out.meta["pyramid_levels"] = L
    return out


@dataclass
class ZoneMeasure:
    zone: str
    u: float
    v: float
    sigma_u: float
    sigma_v: float
    n_valid: int
    n_total: int

    @property
    def magnitude(self) -> float:
        return float(np.hypot(self.u, self.v))

    @property
    def sigma(self) -> float:
        return float(np.hypot(self.sigma_u, self.sigma_v))

    @property
    def coverage(self) -> float:
        return self.n_valid / max(1, self.n_total)

    def to_dict(self) -> dict:
        return {"zone": self.zone, "u": self.u, "v": self.v, "sigma_u": self.sigma_u,
                "sigma_v": self.sigma_v, "n_valid": self.n_valid, "n_total": self.n_total,
                "magnitude": self.magnitude, "sigma": self.sigma}


def robust_sigma(x: np.ndarray) -> float:
    """1.4826 x median absolute deviation."""
    if len(x) == 0:
        return float("nan")
    med = np.median(x)
    return float(1.4826 * np.median(np.abs(x - med)))


def zone_displacement(fld: DisplacementField, name: str, poly: list,
                      min_valid: int = 3) -> ZoneMeasure:
    """Median displacement of valid subsets inside a polygon, with robust sigma."""
    m = polygon_mask(fld.shape, [poly])
    inside = m[fld.ys, fld.xs] > 0
    sel = inside & fld.valid
    n_total = int(inside.sum())
    n_valid = int(sel.sum())
    if n_valid < min_valid:
        return ZoneMeasure(name, float("nan"), float("nan"), float("nan"), float("nan"),
                           n_valid, n_total)
    uu, vv = fld.u[sel], fld.v[sel]
    return ZoneMeasure(name, float(np.median(uu)), float(np.median(vv)),
                       robust_sigma(uu), robust_sigma(vv), n_valid, n_total)
