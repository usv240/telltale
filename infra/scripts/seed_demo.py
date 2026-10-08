"""Seed a demo site: render a synthetic slope collapse as camera bursts and feed it through
the pipeline, either locally (no AWS needed) or through the deployed stack.

    python infra/scripts/seed_demo.py --local web/dashboard/demo-data      # offline judges
    python infra/scripts/seed_demo.py --s3 telltale-123456789012 [--wait]    # cloud path

Local mode calls the same ``process_epoch`` the cloud worker runs, so the dashboard shows an
identical artifact set either way. Cloud mode uploads bursts in order and (with --wait) polls
forecast.json until the last epoch has been processed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "infra" / "worker"))

from telltale.config import ForecastConfig, GridConfig, SiteConfig  # noqa: E402
from telltale.stack import translate  # noqa: E402
from telltale.synthetic import perturb, simulate_collapse  # noqa: E402

SITE = "demo-slope"


def make_bursts(n_epochs: int, size: int, jitter: float, seed: int, burst: int = 5):
    scene = simulate_collapse(h=size, w=size, n_epochs=n_epochs, tf=50.0, t_end=47.0,
                              amp=2.0, noise=0.0, jitter_px=jitter, seed=seed)
    rng = np.random.default_rng(seed + 1)
    epochs = []
    for t, frame in zip(scene.times, scene.frames):
        frames = []
        for _ in range(burst):
            f = translate(frame, rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4))
            f = perturb(f, noise=0.015, rng=rng)
            frames.append(np.clip(f * 255, 0, 255).astype(np.uint8))
        epochs.append((float(t), frames))
    site = SiteConfig(name=SITE, mm_per_px=0.8, stable_polys=[scene.stable_poly],
                      target_zones={"slope": scene.zone_poly},
                      grid=GridConfig(template=41, stride=16, search=16),
                      forecast=ForecastConfig(),
                      notes="Synthetic collapse: Voight alpha=2 creep, true failure at t=50; "
                            "0.8 mm per pixel; left strip stable, right block moves.")
    return scene, epochs, asdict(site)


def run_local(out: Path, epochs, site_cfg):
    from worker import LocalStore, process_epoch
    store = LocalStore(out)
    for t, frames in epochs:
        rec = process_epoch(store, SITE, t, frames, site_cfg)
        z = rec.get("zones", {}).get("slope", {})
        print(f"t={t:6.2f} usable={rec['usable']!s:5} reason={rec['reason']:10} "
              f"|d|={z.get('magnitude', float('nan')):.3f}px total={rec['timing']['total_s']:.2f}s")
    fc = json.loads((out / f"public/sites/{SITE}/forecast.json").read_text())
    print(json.dumps({k: fc["zones"]["slope"].get(k) for k in ("state", "tf", "t_lo", "t_hi", "r2")}))


def run_s3(bucket: str, epochs, site_cfg, wait: bool, region: str | None, delay: float):
    import boto3
    from upload_epoch import upload
    import tempfile
    s3 = boto3.client("s3", region_name=region)
    last_t = epochs[-1][0]
    with tempfile.TemporaryDirectory() as td:
        for i, (t, frames) in enumerate(epochs):
            paths = []
            for k, f in enumerate(frames):
                p = Path(td) / f"e{i:03d}_f{k}.png"
                cv2.imwrite(str(p), f)
                paths.append(str(p))
            key = upload(bucket, SITE, t, paths, site_cfg if i == 0 else None, region)
            print(f"uploaded t={t:6.2f} -> {key}")
            time.sleep(delay)
    if wait:
        print("waiting for the worker to process the final epoch ...")
        for _ in range(120):
            try:
                body = s3.get_object(Bucket=bucket, Key=f"public/sites/{SITE}/forecast.json")["Body"].read()
                fc = json.loads(body)
                if fc.get("updated_t") == last_t:
                    z = fc["zones"]["slope"]
                    print(json.dumps({"state": fc["state"], "tf": z.get("tf"), "t_lo": z.get("t_lo"),
                                      "t_hi": z.get("t_hi"), "r2": z.get("r2"),
                                      "runtime": fc["runtime"]}, indent=1))
                    return
                print(f"  processed up to t={fc.get('updated_t')}")
            except Exception:
                print("  no forecast yet")
            time.sleep(5)
        print("timed out waiting; check the worker log")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--local", help="output folder for a local artifact set")
    g.add_argument("--s3", help="bucket name of the deployed stack")
    p.add_argument("--epochs", type=int, default=36)
    p.add_argument("--size", type=int, default=384)
    p.add_argument("--jitter", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--wait", action="store_true")
    p.add_argument("--delay", type=float, default=0.5, help="seconds between uploads")
    p.add_argument("--region", default=None)
    a = p.parse_args(argv)
    scene, epochs, site_cfg = make_bursts(a.epochs, a.size, a.jitter, a.seed)
    print(f"rendered {len(epochs)} epochs of {a.size}px, true failure t={scene.tf}")
    if a.local:
        run_local(Path(a.local), epochs, site_cfg)
    else:
        run_s3(a.s3, epochs, site_cfg, a.wait, a.region, a.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
