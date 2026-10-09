"""Run the USGS Mukilteo record through the real worker as a dashboard site.

    python evaluation/e4_product_run.py --photos <dir> --out <local store> [--agent rules|llm|off]

Each noon frame (dates from the OCR-read stamps) becomes a one-frame epoch; the site is
configured in chained reference mode with the top strip as stable ground and the timestamp
strip cropped away; epoch time is days since the first frame. The output folder has the same
layout as the cloud bucket, so `public/sites/mukilteo-usgs` can be uploaded as a second site:
daily overlays, replay, forecast state, jump events and the supervising agent's traces, on a
real landslide. Imagery: USGS, public domain, ScienceBase 5ef2388382ced62aaae3bbbe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "infra" / "worker"))
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT))

from e4_mukilteo import STABLE, ZONES, frame_date  # noqa: E402
from telltale.config import ForecastConfig, GridConfig, SiteConfig  # noqa: E402

SITE = "mukilteo-usgs"
CROP_ROWS = 630   # drop the burned-in timestamp strip (rows 630..677 at half resolution)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--photos", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--stamps", default=str(ROOT / "evaluation" / "results" / "mukilteo_stamps.json"))
    p.add_argument("--agent", default="llm", choices=["llm", "rules", "off"])
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args(argv)
    os.environ["TELLTALE_AGENT"] = a.agent
    import worker as W

    stamps = {}
    raw = json.loads(Path(a.stamps).read_text(encoding="utf-8"))
    for k, v in raw.items():
        if v.get("valid"):
            s = v["stamp"]
            stamps[int(k)] = (dt.date(int(s[6:10]), int(s[0:2]), int(s[3:5])), int(s[11:13]))
    files = sorted(Path(a.photos).glob("mukilteo-*.jpg"))
    seq, seen = [], set()
    for f in files:
        k = int(f.stem.split("-")[1])
        d, h = stamps.get(k, frame_date(k))
        if abs(h - 11) <= 1 and d not in seen:
            seq.append((d, f)); seen.add(d)
    if a.limit:
        seq = seq[:a.limit]
    start = seq[0][0]
    zones = {name: [[x, min(y, CROP_ROWS - 1)] for x, y in poly] for name, poly in ZONES.items()}
    cfg = SiteConfig(name=SITE, mm_per_px=1.0, stable_polys=[[[x, min(y, CROP_ROWS - 1)] for x, y in STABLE]],
                     target_zones=zones, grid=GridConfig(template=41, stride=20, search=16),
                     forecast=ForecastConfig(), burst_size=1, reference_mode="chained", mask_window=0,
                     notes="USGS Mukilteo coastal-bluff time-lapse (public domain, ScienceBase "
                           "5ef2388382ced62aaae3bbbe), noon frames at half resolution, chained reference; "
                           "t is days since 2015-08-20; scale unknown (1 px = 2 px of the original image).")
    store = W.LocalStore(a.out)
    t0 = time.perf_counter()
    for i, (d, f) in enumerate(seq):
        img = cv2.imread(str(f), cv2.IMREAD_COLOR)
        half = cv2.resize(img, (1024, 678), interpolation=cv2.INTER_AREA)[:CROP_ROWS]
        t = float((d - start).days)
        rec = W.process_epoch(store, SITE, t, [half], asdict(cfg) if i == 0 else None)
        if i % 20 == 0 or not rec["usable"]:
            z = rec.get("zones", {}).get("left_face", {})
            print(f"{i:4d}/{len(seq)} {d} t={t:5.0f} {rec['reason']:12} state={rec.get('state')} "
                  f"left|d|={z.get('magnitude') if z else None} jump={rec.get('jump')} ({time.perf_counter() - t0:.0f}s)")
    fc = json.loads(store.get(f"public/sites/{SITE}/forecast.json"))
    log_raw = store.get(f"public/sites/{SITE}/agentlog.json")
    events = json.loads(log_raw)["events"] if log_raw else []
    print(json.dumps({"state": fc["state"], "n_epochs": fc["n_epochs"], "n_unusable": fc["n_unusable"],
                      "events": [(e["t"], e["event"], e["verdict"], e["n_tool_calls"]) for e in events]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
