"""Camera-side client: upload one burst as an epoch.

    python infra/scripts/upload_epoch.py --bucket telltale-123 --site quarry-a --t 12.5 \
        --frames bursts/t012/*.jpg [--site-config site.json]

Frames are uploaded first, then manifest.json; the manifest is what triggers processing, so a
half-uploaded burst can never be processed. The site config is only needed with the first
epoch of a new site. Runs on anything with Python and boto3 (a Raspberry Pi, an old phone via
Termux, a laptop next to a CCTV recorder).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import boto3


def upload(bucket: str, site: str, t: float, frames: list[str],
           site_config: dict | None = None, region: str | None = None) -> str:
    s3 = boto3.client("s3", region_name=region)
    prefix = f"ingest/{site}/{t:g}/"
    names = []
    for i, path in enumerate(sorted(frames)):
        name = f"frame_{i:02d}{Path(path).suffix.lower()}"
        s3.upload_file(path, bucket, prefix + name)
        names.append(name)
    manifest = {"site": site, "t": t, "frames": names}
    if site_config is not None:
        manifest["site_config"] = site_config
    s3.put_object(Bucket=bucket, Key=prefix + "manifest.json", Body=json.dumps(manifest),
                  ContentType="application/json")
    return prefix + "manifest.json"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True)
    p.add_argument("--site", required=True)
    p.add_argument("--t", type=float, required=True, help="epoch time (hours since site start)")
    p.add_argument("--frames", nargs="+", required=True, help="frame paths or globs")
    p.add_argument("--site-config", default=None, help="site.json, first epoch only")
    p.add_argument("--region", default=None)
    a = p.parse_args(argv)
    paths = []
    for f in a.frames:
        paths += glob.glob(f) or [f]
    cfg = json.loads(Path(a.site_config).read_text()) if a.site_config else None
    key = upload(a.bucket, a.site, a.t, paths, cfg, a.region)
    print(f"uploaded {len(paths)} frames -> s3://{a.bucket}/{key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
