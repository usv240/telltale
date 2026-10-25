"""Stage the slope collapses that the dashboard's "Run it live" button replays.

    python infra/scripts/stage_live_demo.py --s3 telltale-<account> [--variants 3]

Each variant is a simulated collapse (true failure at t = 50) with its own seed and camera
jitter, rendered as camera bursts and stored under samples/live-demo/v<n>/<epoch>/ in the same
layout the camera client uploads (frames plus manifest.json; the first manifest carries
site.json). The live-run Lambda copies one variant into ingest/live-demo/, so the real queue,
the COOL worker and the agent process it exactly as they would a camera's uploads.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

import seed_demo  # noqa: E402

SITE = "live-demo"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--s3", required=True, help="bucket of the deployed stack")
    p.add_argument("--variants", type=int, default=3)
    p.add_argument("--epochs", type=int, default=36)
    p.add_argument("--size", type=int, default=384)
    p.add_argument("--region", default=None)
    a = p.parse_args(argv)
    import boto3
    s3 = boto3.client("s3", region_name=a.region)
    for v in range(a.variants):
        jitter = (0.6, 0.9, 1.2)[v % 3]
        _, epochs, cfg = seed_demo.make_bursts(a.epochs, a.size, jitter, seed=100 + v)
        cfg["name"] = SITE
        cfg["notes"] = (f"Live run, variant {v}: simulated creep to failure at t = 50 (Voight alpha = 2), "
                        f"camera jitter {jitter} px; started from the dashboard's Run it live button.")
        for i, (t, frames) in enumerate(epochs):
            prefix = f"samples/{SITE}/v{v}/{i:03d}/"
            names = []
            for k, f in enumerate(frames):
                ok, buf = cv2.imencode(".png", f)
                name = f"frame_{k}.png"
                s3.put_object(Bucket=a.s3, Key=prefix + name, Body=buf.tobytes(), ContentType="image/png")
                names.append(name)
            man = {"site": SITE, "t": t, "frames": names}
            if i == 0:
                man["site_config"] = cfg
            s3.put_object(Bucket=a.s3, Key=prefix + "manifest.json", Body=json.dumps(man).encode(),
                          ContentType="application/json")
        print(f"staged variant v{v}: {len(epochs)} epochs, jitter {jitter} px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
