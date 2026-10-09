"""Stage B: stabilization, separating camera motion from ground motion.

Coarse: ORB keypoints inside the operator-marked STABLE regions, Lowe ratio matching, and a
homography from USAC/MAGSAC (OpenCV 5's robust estimator family). ORB correspondences are only
accurate to a few tenths of a pixel, which is not good enough for millimetre metrology, so:

Fine: the coarsely warped epoch is correlated against the reference inside the stable regions
with the same sub-pixel DIC used for measurement; those dense sub-pixel correspondences refine
the homography (again with MAGSAC, tight threshold). The current epoch is then warped once with
the composed homography.

Verify: a sparse DIC pass on the stable regions after the final warp measures what is left.
A coherent residual (the stable ground "moved") or a large scatter (motion the camera model
cannot explain: non-rigid distortion, wrong mask, lens change) is a CAMERA_EVENT, and no ground
displacement may be appended for the epoch.

Verdicts:
    OK            stable regions align after warping; measurement may proceed
    CAMERA_EVENT  residual or scatter in stable regions beyond tolerance
    LOW_INLIERS   not enough matches to estimate camera motion (fog, night, bad mask)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import GridConfig
from .dic import compute_field, robust_sigma

VERDICT_OK = "OK"
VERDICT_CAMERA_EVENT = "CAMERA_EVENT"
VERDICT_LOW_INLIERS = "LOW_INLIERS"


def to_u8(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img
    return np.clip(img * 255.0, 0, 255).astype(np.uint8)


@dataclass
class StabilizeResult:
    image: np.ndarray            # current epoch warped onto reference geometry
    H: np.ndarray                # 3x3 homography mapping current -> reference
    verdict: str
    n_matches: int               # ORB ratio-test matches
    n_inliers: int               # MAGSAC inliers of the coarse fit
    rms: float                   # coarse reprojection RMS over inliers, px
    translation: tuple[float, float]
    rotation_deg: float
    scale: float
    residual: tuple[float, float]  # median stable-region displacement after final warp, px
    scatter: float               # robust sigma of stable-region displacement after warp, px
    n_refine: int                # DIC correspondences used to refine H
    n_verify: int                # DIC subsets in the verification pass
    mount_moved: bool            # homography deviates from identity beyond mount threshold
    diag: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict, "n_matches": self.n_matches, "n_inliers": self.n_inliers,
            "rms": self.rms, "translation": list(self.translation),
            "rotation_deg": self.rotation_deg, "scale": self.scale,
            "residual": list(self.residual), "scatter": self.scatter,
            "n_refine": self.n_refine, "n_verify": self.n_verify,
            "mount_moved": self.mount_moved, **self.diag,
        }


def decompose_homography(H: np.ndarray) -> tuple[tuple[float, float], float, float]:
    """Translation, rotation (deg) and isotropic scale implied by H near identity."""
    tx, ty = float(H[0, 2]), float(H[1, 2])
    rot = math.degrees(math.atan2(H[1, 0], H[0, 0]))
    scale = math.sqrt(abs(float(np.linalg.det(H[:2, :2]))))
    return (tx, ty), rot, scale


def _warp(cur: np.ndarray, H: np.ndarray, shape: tuple) -> np.ndarray:
    h, w = shape[:2]
    return cv2.warpPerspective(cur, H, (w, h), flags=cv2.INTER_LANCZOS4,
                               borderMode=cv2.BORDER_REFLECT)


def coarse_homography(ref: np.ndarray, cur: np.ndarray, mask8: np.ndarray | None,
                      n_features: int, ratio: float, reproj_px: float, min_inliers: int):
    """ORB + ratio test + USAC_MAGSAC. Returns (H, n_matches, n_inliers, rms) or None."""
    orb = cv2.ORB_create(nfeatures=n_features)
    k1, d1 = orb.detectAndCompute(to_u8(ref), mask8)
    k2, d2 = orb.detectAndCompute(to_u8(cur), mask8)
    if d1 is None or d2 is None or len(k1) < min_inliers or len(k2) < min_inliers:
        return None
    knn = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d2, k=2)
    good = [p[0] for p in knn if len(p) == 2 and p[0].distance < ratio * p[1].distance]
    if len(good) < min_inliers:
        return None
    p_ref = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    p_cur = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inl = cv2.findHomography(p_cur, p_ref, cv2.USAC_MAGSAC, reproj_px)
    if H is None or inl is None:
        return None
    inl = inl.ravel().astype(bool)
    if inl.sum() < min_inliers:
        return None
    proj = cv2.perspectiveTransform(p_cur, H).reshape(-1, 2)
    err = np.linalg.norm(proj[inl] - p_ref.reshape(-1, 2)[inl], axis=1)
    return H, len(good), int(inl.sum()), float(np.sqrt(np.mean(err ** 2)))


def _fit_rms(M: np.ndarray, src: np.ndarray, dst: np.ndarray, inl: np.ndarray) -> float:
    proj = cv2.perspectiveTransform(src.reshape(-1, 1, 2), M).reshape(-1, 2)
    err = np.linalg.norm(proj[inl] - dst[inl], axis=1)
    return float(np.sqrt(np.mean(err ** 2))) if inl.any() else float("inf")


def select_camera_model(src: np.ndarray, dst: np.ndarray, min_inliers: int,
                        thresh_px: float = 0.5, slack_px: float = 0.02):
    """Simplest camera model (translation, similarity, affine, homography) that explains
    the sub-pixel correspondences ``src -> dst``.

    Stable regions are often a narrow strip of the frame; an 8-parameter homography fitted
    there extrapolates badly across the slope. A model is accepted when its RMS is within
    ``slack_px`` of the best model's RMS. Returns (3x3 matrix, name, rms, inlier_frac) or None.
    """
    n = len(src)
    if n < min_inliers:
        return None
    cands = []
    t = np.median(dst - src, axis=0)
    Mt = np.array([[1, 0, t[0]], [0, 1, t[1]], [0, 0, 1]], dtype=np.float64)
    inl_t = np.linalg.norm((src + t) - dst, axis=1) < thresh_px
    cands.append(("translation", Mt, inl_t))
    for name, fn in (("similarity", cv2.estimateAffinePartial2D), ("affine", cv2.estimateAffine2D)):
        A, inl = fn(src.reshape(-1, 1, 2), dst.reshape(-1, 1, 2), method=cv2.RANSAC,
                    ransacReprojThreshold=thresh_px)
        if A is not None and inl is not None:
            M = np.vstack([A, [0, 0, 1]]).astype(np.float64)
            cands.append((name, M, inl.ravel().astype(bool)))
    Hh, inl_h = cv2.findHomography(src.reshape(-1, 1, 2), dst.reshape(-1, 1, 2),
                                   cv2.USAC_MAGSAC, thresh_px)
    if Hh is not None and inl_h is not None:
        cands.append(("homography", Hh.astype(np.float64), inl_h.ravel().astype(bool)))
    scored = [(name, M, _fit_rms(M, src, dst, inl), float(inl.mean()))
              for name, M, inl in cands if inl.sum() >= min_inliers]
    if not scored:
        return None
    best = min(s[2] for s in scored)
    for name, M, rms, frac in scored:          # in order of increasing complexity
        if rms <= best + slack_px:
            return M, name, rms, frac
    return None


def phase_translation(ref: np.ndarray, cur: np.ndarray, mask8: np.ndarray | None,
                      min_response: float = 0.05) -> tuple[float, float] | None:
    """Global shift of the masked stable regions via phase correlation (coarse fallback)."""
    from .stack import shift_of
    if mask8 is None:
        a, b = ref, cur
    else:
        m = (mask8 > 0).astype(np.float32)
        ys, xs = np.nonzero(m)
        if len(ys) < 1024:
            return None
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        mm = m[y0:y1, x0:x1]
        a = (ref[y0:y1, x0:x1] - ref[y0:y1, x0:x1][mm > 0].mean()) * mm
        b = (cur[y0:y1, x0:x1] - cur[y0:y1, x0:x1][mm > 0].mean()) * mm
    if a.shape[0] < 32 or a.shape[1] < 32:
        return None
    dx, dy, resp = shift_of(np.ascontiguousarray(a, np.float32), np.ascontiguousarray(b, np.float32),
                            downscale=1, refine=False)
    if resp < min_response:
        return None
    return (float(dx), float(dy))


def stabilize(ref: np.ndarray, cur: np.ndarray, stable_mask: np.ndarray | None = None,
              n_features: int = 4000, ratio: float = 0.75, reproj_px: float = 2.0,
              min_inliers: int = 12, residual_px: float = 0.3, max_scatter: float = 0.3,
              mount_px: float = 1.0, refine: bool = True,
              refine_grid: GridConfig | None = None,
              verify_grid: GridConfig | None = None) -> StabilizeResult:
    """Warp ``cur`` onto ``ref`` geometry using the content of ``stable_mask``."""
    eye = np.eye(3, dtype=np.float64)
    mask8 = None if stable_mask is None else (stable_mask > 0).astype(np.uint8) * 255
    nan2 = (float("nan"), float("nan"))

    def failed(n_matches: int, stage: str) -> StabilizeResult:
        return StabilizeResult(cur, eye, VERDICT_LOW_INLIERS, n_matches, 0, float("nan"),
                               (0.0, 0.0), 0.0, 1.0, nan2, float("nan"), 0, 0, False,
                               {"failed_stage": stage})

    coarse = coarse_homography(ref, cur, mask8, n_features, ratio, reproj_px, min_inliers)
    diag = {}
    if coarse is None:
        # Low-texture or dark stable regions starve ORB (winter vegetation, fog). Fall back to a
        # global translation from phase correlation on the stable regions; the DIC refinement
        # below then recovers rotation and scale if the data support them.
        t = phase_translation(ref, cur, mask8)
        if t is None:
            return failed(0, "coarse")
        H = np.array([[1, 0, t[0]], [0, 1, t[1]], [0, 0, 1]], dtype=np.float64)
        n_matches, n_inl, rms = 0, 0, float("nan")
        diag["coarse"] = "phase"
    else:
        H, n_matches, n_inl, rms = coarse
        diag["coarse"] = "orb"
    warped = _warp(cur, H, ref.shape)

    n_refine = 0
    if refine:
        rg = refine_grid or GridConfig(template=41, stride=16, search=4)
        fld = compute_field(ref, warped, rg, mask=mask8, crosscheck_frac=0.0)
        n_refine = fld.n_valid
        if n_refine >= min_inliers:
            v = fld.valid
            # Sub-pixel correspondences in the coarsely warped frame, mapped back into the
            # original current frame so the model is selected for the TOTAL camera motion
            # (a coarse homography with spurious perspective terms must not survive).
            src_w = np.float32(np.stack([fld.xs[v] + fld.u[v], fld.ys[v] + fld.v[v]], 1))
            src = cv2.perspectiveTransform(src_w.reshape(-1, 1, 2),
                                           np.linalg.inv(H)).reshape(-1, 2)
            dst = np.float32(np.stack([fld.xs[v], fld.ys[v]], 1))
            chosen = select_camera_model(src, dst, min_inliers)
            if chosen is not None:
                Hr, model, rms_r, frac = chosen
                H = Hr
                warped = _warp(cur, H, ref.shape)
                diag["refine_model"] = model
                diag["refine_rms"] = rms_r
                diag["refine_inlier_frac"] = frac
                diag["coarse_residual"] = [float(np.median(fld.u[v])), float(np.median(fld.v[v]))]

    vg = verify_grid or GridConfig(template=41, stride=24, search=3)
    ver = compute_field(ref, warped, vg, mask=mask8, crosscheck_frac=0.0)
    n_verify = ver.n_valid
    if n_verify >= min_inliers:
        vu, vv = ver.u[ver.valid], ver.v[ver.valid]
        residual = (float(np.median(vu)), float(np.median(vv)))
        scatter = float(np.hypot(robust_sigma(vu), robust_sigma(vv)))
    else:
        residual, scatter = nan2, float("nan")

    translation, rot, scale = decompose_homography(H)
    verdict = VERDICT_OK
    if n_verify < min_inliers:
        verdict = VERDICT_LOW_INLIERS
    elif math.hypot(*residual) > residual_px or scatter > max_scatter:
        verdict = VERDICT_CAMERA_EVENT
    mount_moved = (math.hypot(*translation) > mount_px or abs(rot) > 0.1
                   or abs(scale - 1.0) > 0.002)
    return StabilizeResult(warped, H, verdict, n_matches, n_inl, rms, translation, rot, scale,
                           residual, scatter, n_refine, n_verify, mount_moved, diag)
