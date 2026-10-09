"""E1 on a public benchmark: the Society for Experimental Mechanics 2D DIC Challenge 1.0
(Reu et al., Experimental Mechanics 58, 2018; images shared by iDICs).

    python evaluation/e1_dic_challenge.py --root <folder with Sample1/ Sample2/ Sample3/> [--out evaluation/results]

Sets used (from "2D Challenge 1.0 set descriptions.xlsx"):
  Sample1  TexGen speckle, rigid shift X = Y = 0.05 px per image, 20 images, noise 1.5 GL
  Sample2  TexGen speckle, same shifts, noise 8 GL, contrast 0 to 50
  Sample3  FFT-shifted speckle, shift encoded in the file name (X0.10 Y0.10 ...), noise 2 GL
Each image is measured against the set's first image with TellTale's DIC and with the two
OpenCV baselines that survived the synthetic sweep (Farneback dense flow, pyramidal LK), and
the error against the imposed shift is reported. Sign is resolved per set by correlation
with the imposed shift, since the challenge's shift direction convention is not stated in the
file names.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "evaluation"))

from e1_baselines import m_farneback, m_pyrlk, m_telltale  # noqa: E402
from telltale.config import GridConfig  # noqa: E402
from telltale.stack import to_gray32  # noqa: E402


def load(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit(f"cannot read {path}")
    if img.dtype == np.uint16:
        img = (img.astype(np.float32) / float(img.max() or 1)).astype(np.float32)
        return img
    return to_gray32(img)


def set_sample12(folder: Path, step: float = 0.05):
    files = sorted(folder.rglob("*.tif"))
    ref = files[0]
    return [(f, step * k, step * k) for k, f in enumerate(files)][1:], ref


def set_sample3(folder: Path):
    files = sorted(folder.rglob("*.tif"))
    ref = next((f for f in files if "Reference" in f.name or "X0.00" in f.name), files[0])
    out = []
    for f in files:
        m = re.search(r"X([\d.]+) Y([\d.]+)", f.name)
        if m and f != ref:
            out.append((f, float(m.group(1)), float(m.group(2))))
    return out, ref


METHODS = {"telltale": m_telltale, "farneback": m_farneback, "pyrlk": m_pyrlk}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True)
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    p.add_argument("--max-shift", type=float, default=1.0, help="skip images shifted beyond this (px)")
    a = p.parse_args(argv)
    root = Path(a.root)
    sets = {}
    if (root / "Sample1").exists():
        sets["Sample1 (0.05 px steps, noise 1.5 GL)"] = set_sample12(root / "Sample1")
    if (root / "Sample2").exists():
        sets["Sample2 (0.05 px steps, noise 8 GL)"] = set_sample12(root / "Sample2")
    if (root / "Sample3").exists():
        sets["Sample3 (FFT shifts, noise 2 GL)"] = set_sample3(root / "Sample3")
    results = {}
    for name, (items, ref_path) in sets.items():
        ref = load(ref_path)
        h, w = ref.shape
        grid = GridConfig(template=41, stride=24, search=8)
        rows = []
        for f, ex, ey in items:
            if max(abs(ex), abs(ey)) > a.max_shift:
                continue
            cur = load(f)
            if cur.shape != ref.shape:
                continue
            row = {"file": f.name, "expected_x": ex, "expected_y": ey}
            for m, fn in METHODS.items():
                u, v = fn(ref, cur, grid)
                row[m] = [u, v]
            rows.append(row)
        # resolve the sign convention per method from the correlation with the imposed shift
        summary = {"n_images": len(rows), "image_size": [w, h], "methods": {}}
        for m in METHODS:
            meas = np.array([r[m] for r in rows], dtype=float)
            exp = np.array([[r["expected_x"], r["expected_y"]] for r in rows], dtype=float)
            ok = np.isfinite(meas).all(axis=1)
            if ok.sum() < 2:
                summary["methods"][m] = {"error": "no valid measurements"}
                continue
            sx = 1.0 if np.corrcoef(meas[ok, 0], exp[ok, 0])[0, 1] >= 0 else -1.0
            sy = 1.0 if np.corrcoef(meas[ok, 1], exp[ok, 1])[0, 1] >= 0 else -1.0
            err = np.hypot(sx * meas[ok, 0] - exp[ok, 0], sy * meas[ok, 1] - exp[ok, 1])
            summary["methods"][m] = {"sign": [sx, sy], "mean_abs_err_px": float(err.mean()),
                                     "median_err_px": float(np.median(err)), "max_err_px": float(err.max()),
                                     "bias_x_px": float(np.mean(sx * meas[ok, 0] - exp[ok, 0])),
                                     "bias_y_px": float(np.mean(sy * meas[ok, 1] - exp[ok, 1])),
                                     "n": int(ok.sum())}
        results[name] = {"summary": summary, "rows": rows}
        print(f"== {name}: {len(rows)} images of {w}x{h}")
        for m, sm in summary["methods"].items():
            if "error" in sm:
                print(f"   {m:10} {sm['error']}")
            else:
                print(f"   {m:10} MAE {sm['mean_abs_err_px']:.4f} px  median {sm['median_err_px']:.4f}  max {sm['max_err_px']:.4f}  "
                      f"bias x {sm['bias_x_px']:+.4f} y {sm['bias_y_px']:+.4f}  (n={sm['n']})")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "e1_dic_challenge.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"wrote {out / 'e1_dic_challenge.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
