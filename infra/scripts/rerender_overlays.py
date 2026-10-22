"""Re-render a site's overlay PNGs from its stored fields and stabilised epochs, without
re-running the pipeline or the agent (local store only).

    python infra/scripts/rerender_overlays.py --store <local store root> --site mukilteo-usgs [--vmax 1.0]

Used when the overlay style changes (for example the switch from a rainbow map to the
single-hue ramp) so published traces and verdicts stay exactly as they were measured.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

from telltale.dic import DisplacementField  # noqa: E402
from telltale.overlay import render_overlay  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", required=True)
    p.add_argument("--site", required=True)
    p.add_argument("--vmax", type=float, default=None, help="fixed magnitude for full hue (px); default per epoch")
    a = p.parse_args(argv)
    root = Path(a.store)
    pub = root / "public" / "sites" / a.site / "epochs"
    priv = root / "private" / "sites" / a.site / "stabilized"
    n = skipped = 0
    for ep in sorted(pub.iterdir(), key=lambda d: float(d.name)):
        fz, img = ep / "field.npz", priv / f"{ep.name}.npy"
        if not fz.exists() or not img.exists():
            skipped += 1
            continue
        fld = DisplacementField.load(fz)
        gray = np.load(img)
        out = render_overlay(gray, fld, vmax=a.vmax)
        ok, buf = cv2.imencode(".png", out)
        (ep / "overlay.png").write_bytes(buf.tobytes())
        n += 1
    print(f"re-rendered {n} overlays; {skipped} epochs had no field or image (unusable or reference)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
