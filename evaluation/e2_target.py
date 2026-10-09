"""Printable random-speckle target for the E2 metrology test.

    python evaluation/e2_target.py --out evaluation/e2/target_a4.png [--size-mm 190] [--dpi 300]

Prints a square speckle pattern with a 100 mm scale bar and four corner fiducials. Mount it on a
rigid board on a sliding caliper, micrometer stage, or a printed vernier sled, with the board's
motion along the camera's image x axis. Photograph from 20, 50 and 100 m with the phone on a
tripod (exposure and focus locked), a burst of 7 frames before and after each known move of
0.5, 1, 2, 5 and 10 mm. Keep the surroundings in frame: they are the stable region.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="evaluation/e2/target_a4.png")
    p.add_argument("--size-mm", type=float, default=190.0, help="printed side length")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--speckle-mm", type=float, default=2.5, help="typical speckle diameter")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)
    px_per_mm = a.dpi / 25.4
    n = int(round(a.size_mm * px_per_mm))
    rng = np.random.default_rng(a.seed)
    img = np.full((n, n), 255, np.uint8)
    r = a.speckle_mm * px_per_mm / 2
    count = int((n * n) / (np.pi * r * r) * 0.45)           # about 45 percent coverage
    for _ in range(count):
        x, y = rng.integers(0, n, 2)
        rad = int(max(1, rng.normal(r, r * 0.3)))
        cv2.circle(img, (int(x), int(y)), rad, 0, -1, cv2.LINE_AA)
    # white border so the edge is unambiguous, then fiducials and a 100 mm scale bar
    b = int(8 * px_per_mm)
    canvas = np.full((n + 2 * b + int(20 * px_per_mm), n + 2 * b), 255, np.uint8)
    canvas[b:b + n, b:b + n] = img
    f = int(4 * px_per_mm)
    for cx, cy in [(b // 2, b // 2), (n + b + b // 2, b // 2), (b // 2, n + b + b // 2), (n + b + b // 2, n + b + b // 2)]:
        cv2.circle(canvas, (cx, cy), f, 0, -1)
        cv2.circle(canvas, (cx, cy), f // 2, 255, -1)
    y0 = n + 2 * b + int(6 * px_per_mm)
    x0 = b
    cv2.rectangle(canvas, (x0, y0), (x0 + int(100 * px_per_mm), y0 + int(3 * px_per_mm)), 0, -1)
    cv2.putText(canvas, "100 mm", (x0, y0 + int(12 * px_per_mm)), cv2.FONT_HERSHEY_SIMPLEX,
                px_per_mm / 12, 0, max(1, int(px_per_mm / 6)), cv2.LINE_AA)
    cv2.putText(canvas, "TellTale E2 speckle target  print at 100 %  check the bar with a ruler",
                (x0 + int(110 * px_per_mm), y0 + int(12 * px_per_mm)), cv2.FONT_HERSHEY_SIMPLEX,
                px_per_mm / 18, 0, max(1, int(px_per_mm / 8)), cv2.LINE_AA)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), canvas)
    print(f"wrote {out}: {canvas.shape[1]}x{canvas.shape[0]} px at {a.dpi} dpi "
          f"({canvas.shape[1] / px_per_mm:.0f} x {canvas.shape[0] / px_per_mm:.0f} mm)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
