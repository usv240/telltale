"""E6b: which OpenCV operations a build accelerates, by interpolation mode and size.

    python evaluation/e6_interp_probe.py --label cool --out evaluation/results

Times the warps, resamplers and matchers TellTale uses at 1080p, at each interpolation it
could use, so a build's strengths can be matched to pipeline choices. Same seeded pixels on
every build; p50 of 15 runs after 3 warm-ups.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np


def bench(fn, reps=15, warm=3):
    for _ in range(warm):
        fn()
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter(); fn(); ts.append(time.perf_counter() - t0)
    return round(statistics.median(ts) * 1000, 3)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--out", default="evaluation/results")
    a = p.parse_args()
    rng = np.random.default_rng(0)
    img = cv2.GaussianBlur(rng.integers(0, 255, (1080, 1920), dtype=np.uint8), (0, 0), 2)
    imgf = img.astype(np.float32)
    A = np.array([[1, 0.002, 0.7], [-0.002, 1, -0.4]], np.float64)
    H = np.array([[1, 0.002, 0.7], [-0.002, 1, -0.4], [1e-7, 0, 1]], np.float64)
    yy, xx = np.mgrid[0:1080, 0:1920].astype(np.float32)
    mx, my = xx + 0.37, yy - 0.21
    interps = {"nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR,
               "cubic": cv2.INTER_CUBIC, "lanczos": cv2.INTER_LANCZOS4}
    r = {}
    for name, f in interps.items():
        r[f"warpAffine_{name}_u8"] = bench(lambda f=f: cv2.warpAffine(img, A, (1920, 1080), flags=f))
        r[f"warpPerspective_{name}_u8"] = bench(lambda f=f: cv2.warpPerspective(img, H, (1920, 1080), flags=f))
        r[f"warpAffine_{name}_f32"] = bench(lambda f=f: cv2.warpAffine(imgf, A, (1920, 1080), flags=f))
        r[f"remap_{name}_u8"] = bench(lambda f=f: cv2.remap(img, mx, my, f))
        r[f"resize_half_{name}_u8"] = bench(lambda f=f: cv2.resize(img, (960, 540), interpolation=f))
    r["resize_half_area_u8"] = bench(lambda: cv2.resize(img, (960, 540), interpolation=cv2.INTER_AREA))
    r["pyrDown_u8"] = bench(lambda: cv2.pyrDown(img))
    r["GaussianBlur_s2_u8"] = bench(lambda: cv2.GaussianBlur(img, (0, 0), 2))
    r["GaussianBlur_s2_f32"] = bench(lambda: cv2.GaussianBlur(imgf, (0, 0), 2))
    tpl, win = img[500:541, 900:941].copy(), img[480:561, 880:961].copy()
    tplf, winf = tpl.astype(np.float32), win.astype(np.float32)
    r["matchTemplate_x1000_u8"] = bench(lambda: [cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED) for _ in range(1000)], reps=5)
    r["matchTemplate_x1000_f32"] = bench(lambda: [cv2.matchTemplate(winf, tplf, cv2.TM_CCOEFF_NORMED) for _ in range(1000)], reps=5)
    r["matchTemplate_big_u8"] = bench(lambda: cv2.matchTemplate(img[:540, :960], img[200:300, 300:400], cv2.TM_CCOEFF_NORMED), reps=5)
    r["Sobel_u8"] = bench(lambda: cv2.Sobel(img, cv2.CV_16S, 1, 0))
    r["threshold_u8"] = bench(lambda: cv2.threshold(img, 128, 255, cv2.THRESH_BINARY))
    out = {"label": a.label, "opencv": cv2.__version__, "cv2_file": cv2.__file__,
           "threads": cv2.getNumThreads(), "p50_ms": r}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / f"e6b_interp_{a.label}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
