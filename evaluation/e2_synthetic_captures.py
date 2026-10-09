"""Self-test for the E2 harness: render the printed target into a scene and shift it by known
millimetres, producing the same folder layout the real captures use.

    python evaluation/e2_synthetic_captures.py --out evaluation/e2/captures_synthetic
    python evaluation/e2_metrology.py --captures evaluation/e2/captures_synthetic --out evaluation/results

Proves the analysis path (bursts -> stack -> stabilise -> DIC -> mm) before any photo is taken.
Not a substitute for the physical test: the report labels it as synthetic.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.stack import translate  # noqa: E402
from telltale.synthetic import downsample, integer_shift, make_texture, perturb, supersample  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=str(ROOT / "evaluation" / "e2" / "captures_synthetic"))
    p.add_argument("--target", default=str(ROOT / "evaluation" / "e2" / "target_a4.png"))
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    rng = np.random.default_rng(a.seed)
    target = cv2.imread(a.target, cv2.IMREAD_GRAYSCALE)
    if target is None:
        raise SystemExit("run e2_target.py first")
    moves = [0, 0.5, 1, 2, 5, 10]
    # three "distances": the target occupies fewer pixels as the range grows
    for dist, target_px in [(20, 480), (50, 200), (100, 100)]:
        h, w = 720, 1280
        bg = make_texture(h, w, seed=dist)
        tgt = cv2.resize(target, (target_px, target_px), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        bar_px = 100.0 / 190.0 * target_px * (target.shape[1] / (target.shape[1]))  # bar is 100 of 190 mm of the speckle square
        # the printed sheet is wider than the speckle square; approximate bar length from print geometry
        px_per_mm = target_px / (target.shape[1] / (300 / 25.4))
        bar_px = 100.0 * px_per_mm
        x0, y0 = w // 2 - target_px // 2, h // 2 - target_px // 2
        ss = 8
        folder = out / f"{dist}m_1x"
        folder.mkdir(parents=True)
        for i, mm in enumerate(moves):
            dx_px = mm * px_per_mm
            scene = bg.copy()
            big = supersample(tgt, ss)
            shifted = downsample(integer_shift(big, int(round(dx_px * ss)), 0), ss)
            scene[y0:y0 + target_px, x0:x0 + target_px] = shifted
            bdir = folder / f"b{i:02d}"
            bdir.mkdir()
            for k in range(5):
                f = translate(scene, rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3))
                f = perturb(f, noise=0.01, gain=1.0 + rng.uniform(-0.05, 0.05), rng=rng)
                cv2.imwrite(str(bdir / f"frame_{k:02d}.png"), (f * 255).astype(np.uint8))
        man = {"distance_m": dist, "lens": "1x", "focal_mm_equiv": 26, "moves_mm": moves,
               "bar_px": bar_px,
               "target_poly": [[x0 + 10, y0 + 10], [x0 + target_px - 10, y0 + 10],
                               [x0 + target_px - 10, y0 + target_px - 10], [x0 + 10, y0 + target_px - 10]],
               "stable_poly": [[0, 0], [w - 1, 0], [w - 1, y0 - 20], [0, y0 - 20]],
               "synthetic": True}
        (folder / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
        print(f"{folder.name}: target {target_px}px, {px_per_mm:.3f} px/mm, moves {moves} mm "
              f"= {[round(m * px_per_mm, 2) for m in moves]} px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
