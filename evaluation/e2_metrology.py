"""E2: physical metrology. Known millimetre moves of a speckle target, measured by the pipeline.

Folder layout (one folder per distance and lens; any names):

    evaluation/e2/captures/
      50m_1x/
        manifest.json      {"distance_m": 50, "lens": "1x", "focal_mm_equiv": 26,
                            "sensor_width_mm": 7.0, "moves_mm": [0, 0.5, 1, 2, 5, 10],
                            "target_poly": [[x, y], ...]  (pixel polygon around the target in burst 0),
                            "stable_poly": [[x, y], ...]  (surroundings that did not move)}
        b00/ frame_*.jpg   burst before any move (reference, position 0)
        b01/ frame_*.jpg   after move 1 (moves_mm[1]) ... one burst per entry of moves_mm

    python evaluation/e2_metrology.py --captures evaluation/e2/captures --out evaluation/results

For each folder: stack each burst, stabilise against burst 0 using stable_poly, measure the
target zone's displacement with dense DIC, convert px to mm with the scale from the 100 mm bar
(``bar_px`` in the manifest) or from the focal length, and regress measured against true. Report
slope, intercept, RMS error, and the worst-case error per distance and lens. That table is the
deployment guidance: expected precision for a given camera at a given range.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.config import GridConfig, polygon_mask  # noqa: E402
from telltale.dic import compute_field, zone_displacement  # noqa: E402
from telltale.stabilize import VERDICT_OK, stabilize  # noqa: E402
from telltale.stack import stack_burst  # noqa: E402

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff")


def load_burst(folder: Path):
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT)
    return [cv2.imread(str(f), cv2.IMREAD_COLOR) for f in files]


def mm_per_px(man: dict, ref_shape) -> float:
    if man.get("bar_px"):
        return 100.0 / float(man["bar_px"])
    f = float(man["focal_mm_equiv"])
    sensor_w = float(man.get("sensor_width_mm", 36.0 if "equiv" in str(man.get("focal_mm_equiv")) else 36.0))
    width_px = ref_shape[1]
    # ground sample distance for a 35 mm-equivalent focal length
    return (float(man["distance_m"]) * 1000.0 * 36.0 / f) / width_px


def run_folder(folder: Path, grid: GridConfig) -> dict:
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    bursts = sorted(p for p in folder.iterdir() if p.is_dir() and p.name.startswith("b"))
    moves = man["moves_mm"]
    if len(bursts) != len(moves):
        raise SystemExit(f"{folder}: {len(bursts)} bursts but {len(moves)} moves listed")
    ref_stack = stack_burst(load_burst(bursts[0]))
    ref = ref_stack.image
    scale = mm_per_px(man, ref.shape)
    # Search radius must cover the largest commanded move at this range (plus margin).
    largest_px = max(abs(float(m)) for m in moves) / scale
    grid = GridConfig(template=grid.template, stride=grid.stride,
                      search=int(min(64, max(8, np.ceil(largest_px) + 6))))
    print(f"  scale {scale:.3f} mm/px; largest move {largest_px:.1f} px; search radius {grid.search} px")
    stable = polygon_mask(ref.shape, [man["stable_poly"]]) if man.get("stable_poly") else None
    rows = []
    for b, true_mm in zip(bursts, moves):
        st = stack_burst(load_burst(b))
        row = {"burst": b.name, "true_mm": float(true_mm), "stack": st.status}
        sb = stabilize(ref, st.image, stable) if stable is not None else None
        cur = sb.image if sb is not None and sb.verdict == VERDICT_OK else st.image
        row["stabilize"] = sb.verdict if sb else "none"
        fld = compute_field(ref, cur, grid)
        zm = zone_displacement(fld, "target", man["target_poly"])
        row.update(u_px=zm.u, v_px=zm.v, sigma_px=zm.sigma, n_valid=zm.n_valid,
                   measured_mm=float(zm.u * scale) if np.isfinite(zm.u) else None,
                   sigma_mm=float(zm.sigma * scale) if np.isfinite(zm.sigma) else None,
                   coverage=fld.coverage)
        rows.append(row)
        print(f"  {b.name}: true {true_mm:6.2f} mm  measured {row['measured_mm'] if row['measured_mm'] is None else round(row['measured_mm'], 3)} mm "
              f"(sigma {row['sigma_mm'] if row['sigma_mm'] is None else round(row['sigma_mm'], 3)}), stab {row['stabilize']}")
    ok = [r for r in rows if r["measured_mm"] is not None]
    t = np.array([r["true_mm"] for r in ok]); m = np.array([r["measured_mm"] for r in ok])
    sign = 1.0 if np.corrcoef(t, m)[0, 1] >= 0 else -1.0   # image x may be opposite to the stage
    m = m * sign
    A = np.vstack([t, np.ones_like(t)]).T
    slope, intercept = np.linalg.lstsq(A, m, rcond=None)[0]
    resid = m - (slope * t + intercept)
    return {"folder": folder.name, "distance_m": man["distance_m"], "lens": man.get("lens"),
            "mm_per_px": scale, "n_moves": len(ok), "slope": float(slope), "intercept_mm": float(intercept),
            "rms_mm": float(np.sqrt(np.mean(resid ** 2))), "max_abs_err_mm": float(np.max(np.abs(resid))),
            "rms_px": float(np.sqrt(np.mean((resid / scale) ** 2))), "sign": sign, "rows": rows}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--captures", default=str(ROOT / "evaluation" / "e2" / "captures"))
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = p.parse_args(argv)
    grid = GridConfig(template=41, stride=16, search=16)
    results = []
    for folder in sorted(Path(a.captures).iterdir()):
        if folder.is_dir() and (folder / "manifest.json").exists():
            print(f"== {folder.name}")
            results.append(run_folder(folder, grid))
    if not results:
        print("no capture folders with manifest.json found")
        return 1
    print(f"\n{'folder':14} {'dist m':>6} {'lens':>5} {'mm/px':>7} {'slope':>6} {'icpt mm':>8} {'rms mm':>7} {'max mm':>7} {'rms px':>7}")
    for r in results:
        print(f"{r['folder']:14} {r['distance_m']:>6} {str(r['lens']):>5} {r['mm_per_px']:7.3f} {r['slope']:6.3f} "
              f"{r['intercept_mm']:8.3f} {r['rms_mm']:7.3f} {r['max_abs_err_mm']:7.3f} {r['rms_px']:7.3f}")
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "e2_metrology.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"wrote {out / 'e2_metrology.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
