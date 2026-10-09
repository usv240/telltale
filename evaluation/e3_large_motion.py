"""E3b: large-motion collapse. Fixed reference with coarse-to-fine DIC against the two
single-level alternatives (fixed reference, and day-to-day chaining).

    python evaluation/e3_large_motion.py [--amp 10] [--out evaluation/results]

A Voight collapse (true failure at t = 50) whose final displacement is about 28 px, far beyond
a 16 px search radius, is rendered with camera jitter and run through the unmodified worker
three times. Scored on measurement error against the rendered truth, epochs measured, and the
final forecast. This is the reason to prefer fixed reference plus pyramid on scenes that keep
their texture: chaining sums daily errors into a random walk, a single-level fixed search loses
the slope once it moves more than the radius.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "infra" / "worker"))
sys.path.insert(0, str(ROOT))

from telltale.config import ForecastConfig, GridConfig, SiteConfig  # noqa: E402
from telltale.stack import translate  # noqa: E402
from telltale.synthetic import perturb, simulate_collapse  # noqa: E402

ARMS = {
    "fixed, single level": dict(reference_mode="fixed", pyramid_levels=0),
    "chained, single level": dict(reference_mode="chained", pyramid_levels=0),
    "fixed, coarse-to-fine (3 levels)": dict(reference_mode="fixed", pyramid_levels=3),
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--amp", type=float, default=10.0)
    p.add_argument("--size", type=int, default=384)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = p.parse_args(argv)
    os.environ["TELLTALE_AGENT"] = "off"
    import worker as W

    scene = simulate_collapse(h=a.size, w=a.size, n_epochs=a.epochs, tf=50.0, t_end=47.0, amp=a.amp,
                              noise=0.0, jitter_px=0.8, seed=a.seed)
    print(f"true final displacement {scene.true_disp[-1]:.2f} px; search radius 16 px")
    results = {}
    for name, opts in ARMS.items():
        store_dir = Path(a.out) / "e3_large_motion" / name.split(",")[0].replace(" ", "_") / str(opts["pyramid_levels"])
        shutil.rmtree(store_dir, ignore_errors=True)
        store = W.LocalStore(store_dir)
        cfg = SiteConfig(name="large", mm_per_px=1.0, stable_polys=[scene.stable_poly],
                         target_zones={"slope": scene.zone_poly},
                         grid=GridConfig(template=41, stride=16, search=16, pyramid_levels=opts["pyramid_levels"]),
                         forecast=ForecastConfig(), reference_mode=opts["reference_mode"])
        rng = np.random.default_rng(a.seed + 1)
        meas = []
        for k, (t, frame) in enumerate(zip(scene.times, scene.frames)):
            burst = [np.clip(perturb(translate(frame, rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3)),
                                     noise=0.01, rng=rng) * 255, 0, 255).astype(np.uint8) for _ in range(3)]
            rec = W.process_epoch(store, "large", float(t), burst, asdict(cfg) if k == 0 else None)
            z = (rec.get("zones") or {}).get("slope") or {}
            m = z.get("magnitude")
            meas.append(np.nan if (m is None or not rec["usable"]) else float(m))
        meas = np.array(meas)
        truth = scene.true_disp
        ok = np.isfinite(meas)
        err = np.abs(meas[ok] - truth[ok])
        fc = json.loads(store.get("public/sites/large/forecast.json"))["zones"]["slope"]
        late = truth > 16
        results[name] = {
            "epochs_measured": int(ok.sum()), "epochs": int(len(meas)),
            "mae_px": float(err.mean()) if len(err) else None, "max_err_px": float(err.max()) if len(err) else None,
            "final_err_px": float(abs(meas[-1] - truth[-1])) if ok[-1] else None,
            "epochs_beyond_search_measured": int((ok & late).sum()), "epochs_beyond_search": int(late.sum()),
            "forecast_tf": fc.get("tf"), "window": [fc.get("t_lo"), fc.get("t_hi")], "state": fc.get("state"),
        }
        r = results[name]
        print(f"{name:34} measured {r['epochs_measured']:2d}/{r['epochs']}  beyond-search {r['epochs_beyond_search_measured']}/{r['epochs_beyond_search']}  "
              f"MAE {r['mae_px'] if r['mae_px'] is None else round(r['mae_px'], 3)} px  final err {r['final_err_px'] if r['final_err_px'] is None else round(r['final_err_px'], 3)}  "
              f"tf {r['forecast_tf'] if r['forecast_tf'] is None else round(r['forecast_tf'], 2)} {r['state']}")
    out = Path(a.out)
    (out / "e3_large_motion.json").write_text(json.dumps({"true_final_px": float(scene.true_disp[-1]), "arms": results},
                                                         indent=1), encoding="utf-8")
    print(f"wrote {out / 'e3_large_motion.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
