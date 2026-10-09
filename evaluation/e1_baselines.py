"""E1 with named baselines: the same known sub-pixel shifts measured by TellTale's DIC and by
the three things a reasonable engineer would reach for first in OpenCV.

    python evaluation/e1_baselines.py [--size 256] [--trials 3] [--out evaluation/results]

Baselines
  farneback   dense optical flow (cv2.calcOpticalFlowFarneback), median over the frame
  pyrlk       sparse pyramidal Lucas-Kanade on goodFeaturesToTrack corners, median flow
  phasecorr   global cv2.phaseCorrelate on the whole frame (Hanning window)
  telltale    this project: ZNCC subsets, Gaussian sub-pixel peak, one re-sampling pass

All methods see identical image pairs (8x-supersampled exact shifts, noise and illumination
perturbations) and are scored on the same median-over-frame estimate, so the comparison is
about the estimator, not about coverage.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.config import GridConfig  # noqa: E402
from telltale.dic import compute_field  # noqa: E402
from telltale.synthetic import make_texture, shift_image  # noqa: E402


def m_telltale(ref, cur, grid):
    f = compute_field(ref, cur, grid, crosscheck_frac=0.0)
    if f.n_valid == 0:
        return np.nan, np.nan
    return float(np.median(f.u[f.valid])), float(np.median(f.v[f.valid]))


def m_farneback(ref, cur, grid):
    a, b = (ref * 255).astype(np.uint8), (cur * 255).astype(np.uint8)
    flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 4, 21, 5, 7, 1.5, cv2.OPTFLOW_FARNEBACK_GAUSSIAN)
    m = 32
    return float(np.median(flow[m:-m, m:-m, 0])), float(np.median(flow[m:-m, m:-m, 1]))


def m_pyrlk(ref, cur, grid):
    a, b = (ref * 255).astype(np.uint8), (cur * 255).astype(np.uint8)
    pts = cv2.goodFeaturesToTrack(a, 400, 0.01, 8)
    if pts is None:
        return np.nan, np.nan
    nxt, st, err = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(41, 41), maxLevel=3,
                                            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 0.001))
    ok = st.ravel() == 1
    if ok.sum() < 5:
        return np.nan, np.nan
    d = (nxt - pts).reshape(-1, 2)[ok]
    return float(np.median(d[:, 0])), float(np.median(d[:, 1]))


def m_phasecorr(ref, cur, grid):
    win = cv2.createHanningWindow((ref.shape[1], ref.shape[0]), cv2.CV_32F)
    (dx, dy), _ = cv2.phaseCorrelate(ref, cur, win)
    return float(dx), float(dy)


METHODS = {"telltale": m_telltale, "farneback": m_farneback, "pyrlk": m_pyrlk, "phasecorr": m_phasecorr}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = p.parse_args(argv)
    rng = np.random.default_rng(a.seed)
    tex = make_texture(a.size, a.size, seed=a.seed)
    grid = GridConfig(template=41, stride=24, search=8)
    shifts = [0.125, 0.25, 0.5, 1.0, 2.0]
    conds = [("clean", 0.0, 1.0), ("noise 1%, gain 0.85", 0.01, 0.85), ("noise 2%, gain 0.85", 0.02, 0.85)]
    errs = {m: {c[0]: [] for c in conds} for m in METHODS}
    times = {m: [] for m in METHODS}
    for cname, noise, gain in conds:
        for sh in shifts:
            for _ in range(a.trials):
                ang = rng.uniform(0, 2 * np.pi)
                ref, cur, (ax, ay) = shift_image(tex, sh * np.cos(ang), sh * np.sin(ang), noise=noise, gain=gain,
                                                  seed=int(rng.integers(1 << 30)))
                ref = np.ascontiguousarray(ref, np.float32); cur = np.ascontiguousarray(cur, np.float32)
                for m, fn in METHODS.items():
                    t0 = time.perf_counter()
                    u, v = fn(ref, cur, grid)
                    times[m].append(time.perf_counter() - t0)
                    errs[m][cname].append(np.hypot(u - ax, v - ay) if np.isfinite(u) else np.nan)
    rows = []
    print(f"{'method':10} " + " ".join(f"{c[0]:>22}" for c in conds) + f" {'ms/pair':>8}")
    for m in METHODS:
        cells = []
        for cname, _, _ in conds:
            e = np.array(errs[m][cname])
            cells.append({"condition": cname, "median_err_px": float(np.nanmedian(e)), "p95_err_px": float(np.nanpercentile(e, 95)),
                          "fail_frac": float(np.mean(~np.isfinite(e)))})
        rows.append({"method": m, "cells": cells, "ms_per_pair": float(1000 * np.median(times[m]))})
        print(f"{m:10} " + " ".join(f"{c['median_err_px']:9.4f} / p95 {c['p95_err_px']:7.4f}" for c in cells) + f" {rows[-1]['ms_per_pair']:8.1f}")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "e1_baselines.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"wrote {out / 'e1_baselines.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
