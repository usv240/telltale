"""E4: USGS Mukilteo coastal-bluff time-lapse (public domain, ScienceBase 5ef2388382ced62aaae3bbbe).

843 frames, three per day (9 am, 12 pm, 4 pm PST), August 20, 2015 to May 25, 2016. USGS
documented five movement periods: Dec 8-9 2015, Jan 21-30 2016, Mar 9-14 2016, and two
night-time events on Mar 23 and Mar 26 2016.

Method. The scene decorrelates over months (vegetation, erosion, metres of movement), so the
pipeline runs in chained mode: each noon frame is stabilised and correlated against the previous
noon frame, and the daily increments are integrated per zone. The stable region is the top strip
(solar panels and the ground above the scarp); the burned-in timestamp strip is masked out so
that static text cannot masquerade as stable ground. Frames are processed at half resolution
(1024 x 678), so 1 px here is 2 px in the original.

Date mapping uses the nominal three-per-day sequence; gaps in the camera record make it
uncertain by about a day, which is stated in the report.

    python evaluation/e4_mukilteo.py --photos <dir with mukilteo-NNN.jpg> --out evaluation/results
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.config import ForecastConfig, GridConfig, polygon_mask  # noqa: E402
from telltale.dic import compute_field, zone_displacement  # noqa: E402
from telltale.forecast import forecast  # noqa: E402
from telltale.overlay import render_overlay  # noqa: E402
from telltale.stabilize import VERDICT_OK, stabilize  # noqa: E402
from telltale.stack import to_gray32  # noqa: E402

START = dt.date(2015, 8, 20)  # verified from burned-in stamps: frame 1 = 08/20/2015 08:59, frame 332 = 12/08/2015
SLOTS = (9, 12, 16)
MOVEMENT_PERIODS = [
    ("Dec 8-9 2015", dt.date(2015, 12, 8), dt.date(2015, 12, 9)),
    ("Jan 21-30 2016", dt.date(2016, 1, 21), dt.date(2016, 1, 30)),
    ("Mar 9-14 2016", dt.date(2016, 3, 9), dt.date(2016, 3, 14)),
    ("Mar 23 2016 (night)", dt.date(2016, 3, 23), dt.date(2016, 3, 23)),
    ("Mar 26 2016 (night)", dt.date(2016, 3, 26), dt.date(2016, 3, 26)),
]

# Half-resolution geometry (1024 x 678). Polygons in that frame.
STABLE = [(0, 0), (1023, 0), (1023, 120), (0, 120)]              # panels and ground above scarp
ZONES = {
    "left_face": [(60, 180), (360, 180), (360, 470), (60, 470)],
    "right_face": [(560, 80), (1010, 80), (1010, 560), (560, 560)],
    "lower_body": [(300, 470), (900, 470), (900, 620), (300, 620)],
}
TIMESTAMP_STRIP = [(700, 630), (1023, 630), (1023, 677), (700, 677)]


def frame_date(k: int) -> tuple[dt.date, int]:
    """Nominal (date, hour) for 1-based frame index k."""
    return START + dt.timedelta(days=(k - 1) // 3), SLOTS[(k - 1) % 3]


def in_period(d: dt.date) -> str | None:
    for name, a, b in MOVEMENT_PERIODS:
        if a <= d <= b:
            return name
    return None


def load_half(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    g = to_gray32(img)
    return cv2.resize(g, (1024, 678), interpolation=cv2.INTER_AREA)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--photos", required=True)
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    p.add_argument("--slot", type=int, default=11, help="hour of day to chain (stamps read 11:5x for the noon frame)")
    p.add_argument("--stamps", default=str(ROOT / "evaluation" / "results" / "mukilteo_stamps.json"),
                   help="OCR-read stamps from mukilteo_stamps.py; nominal mapping if missing")
    p.add_argument("--overlays", type=int, default=6, help="save this many overlay PNGs")
    a = p.parse_args(argv)
    photos = Path(a.photos)
    out = Path(a.out)
    (out / "e4_overlays").mkdir(parents=True, exist_ok=True)

    files = sorted(photos.glob("mukilteo-*.jpg"))
    stamps = {}
    if a.stamps and Path(a.stamps).exists():
        raw = json.loads(Path(a.stamps).read_text(encoding="utf-8"))
        for k, v in raw.items():
            if v.get("valid"):
                s = v["stamp"]  # MM/DD/YYYY HH:MM
                stamps[int(k)] = (dt.date(int(s[6:10]), int(s[0:2]), int(s[3:5])), int(s[11:13]))
        print(f"using {len(stamps)} OCR-read timestamps from {a.stamps}")
    seq, seen_dates = [], set()
    for f in files:
        k = int(f.stem.split("-")[1])
        d, h = stamps.get(k, frame_date(k))
        if abs(h - a.slot) <= 1 and d not in seen_dates:   # 11:5x read stamps, 12:00 nominal
            seq.append((k, d, f))
            seen_dates.add(d)
    print(f"{len(files)} frames; {len(seq)} at {a.slot}:00; {seq[0][1]} to {seq[-1][1]}")

    grid = GridConfig(template=41, stride=20, search=16)
    stable_mask = polygon_mask((678, 1024), [STABLE])
    grid_mask = np.full((678, 1024), 255, np.uint8)
    cv2.fillPoly(grid_mask, [np.int32(TIMESTAMP_STRIP)], 0)
    cv2.fillPoly(grid_mask, [np.int32(STABLE)], 0)

    prev = load_half(seq[0][2])
    cum = {z: np.zeros(2) for z in ZONES}
    rows = []
    t0 = time.perf_counter()
    overlay_every = max(1, len(seq) // a.overlays)
    for i in range(1, len(seq)):
        k, d, f = seq[i]
        cur = load_half(f)
        row = {"k": k, "date": d.isoformat(), "period": in_period(d), "usable": False, "reason": None,
               "sharpness": float(cv2.Laplacian(cur, cv2.CV_32F).var()),
               "contrast": float(cur.std())}
        st = stabilize(prev, cur, stable_mask)
        row["stabilize"] = {"verdict": st.verdict, "n_inliers": st.n_inliers,
                            "model": st.diag.get("refine_model"), "scatter": st.scatter,
                            "translation": list(st.translation)}
        if st.verdict != VERDICT_OK:
            row["reason"] = st.verdict
        else:
            fld = compute_field(prev, st.image, grid, mask=grid_mask, seed=i)
            row["coverage"] = fld.coverage
            row["status_counts"] = fld.status_counts()
            row["review"] = fld.review
            row["usable"] = not fld.review
            row["reason"] = "REVIEW" if fld.review else "OK"
            row["zones"] = {}
            for z, poly in ZONES.items():
                zm = zone_displacement(fld, z, poly, min_valid=5)
                if np.isfinite(zm.u):
                    cum[z] = cum[z] + np.array([zm.u, zm.v])
                row["zones"][z] = {"du": zm.u, "dv": zm.v, "sigma": zm.sigma, "n_valid": zm.n_valid,
                                   "n_total": zm.n_total, "cum_u": float(cum[z][0]),
                                   "cum_v": float(cum[z][1]),
                                   "cum_mag": float(np.hypot(*cum[z]))}
            if i % overlay_every == 0 or row["period"]:
                lab = f"{d.isoformat()} daily increment" + (f" [{row['period']}]" if row["period"] else "")
                cv2.imwrite(str(out / "e4_overlays" / f"{d.isoformat()}.png"),
                            render_overlay(st.image, fld, vmax=3.0, label=lab, arrow_every=3))
        rows.append(row)
        if i % 20 == 0:
            z = rows[-1].get("zones", {}).get("right_face", {})
            print(f"{i:4d}/{len(seq)} {d} {row['reason']:12} cov={row.get('coverage', float('nan')):.2f} "
                  f"right_face cum={z.get('cum_mag', float('nan')):.2f}px  ({time.perf_counter() - t0:.0f}s)")
        prev = cur

    # Summary: daily increment magnitude inside vs outside documented movement periods
    summary = {"n_pairs": len(rows), "usable": sum(r["usable"] for r in rows),
               "unusable": {}, "zones": {},
               "sharpness_median_usable": float(np.median([r["sharpness"] for r in rows if r["usable"]] or [np.nan])),
               "sharpness_median_unusable": float(np.median([r["sharpness"] for r in rows if not r["usable"]] or [np.nan])),
               "first_unusable_run_start": next((r["date"] for i, r in enumerate(rows)
                                                  if i + 10 <= len(rows) and all(not q["usable"] for q in rows[i:i + 10])), None)}
    for r in rows:
        if not r["usable"]:
            summary["unusable"][r["reason"]] = summary["unusable"].get(r["reason"], 0) + 1
    for z in ZONES:
        inc_in, inc_out, per_period = [], [], {}
        for r in rows:
            if not r["usable"] or z not in r.get("zones", {}):
                continue
            zz = r["zones"][z]
            if not np.isfinite(zz["du"]):
                continue
            m = float(np.hypot(zz["du"], zz["dv"]))
            if r["period"]:
                inc_in.append(m)
                per_period.setdefault(r["period"], []).append(m)
            else:
                inc_out.append(m)
        summary["zones"][z] = {
            "median_daily_px_in_movement_periods": float(np.median(inc_in)) if inc_in else None,
            "median_daily_px_outside": float(np.median(inc_out)) if inc_out else None,
            "p90_daily_px_outside": float(np.percentile(inc_out, 90)) if inc_out else None,
            "n_in": len(inc_in), "n_out": len(inc_out),
            "per_period_median_px": {k: float(np.median(v)) for k, v in per_period.items()},
            "days_outside_exceeding_p90": None,
            "final_cum_px": float(np.hypot(*cum[z])),
        }
        # forecast on the cumulative series (expect MOVING / ACCELERATING episodes, not CRITICAL)
        t = [i for i, r in enumerate(rows) if r["usable"] and z in r.get("zones", {})]
        dmag = [rows[i]["zones"][z]["cum_mag"] for i in t]
        if len(t) > 10:
            fc = forecast(np.array(t, float), np.array(dmag), ForecastConfig())
            summary["zones"][z]["forecast_state_at_end"] = fc.state
    (out / "e4_mukilteo.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1,
                                                      default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else float(o)),
                                          encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))
    print(f"wrote {out / 'e4_mukilteo.json'} and {out / 'e4_overlays'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
