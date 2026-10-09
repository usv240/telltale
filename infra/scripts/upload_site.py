"""Publish a locally produced site (output of the worker's local store) to the deployed bucket
as a read-only dashboard site, and merge it into public/sites/index.json.

    python infra/scripts/upload_site.py --store <local store root> --site mukilteo-usgs --bucket telltale-123

Only what the dashboard reads is uploaded (JSON, overlays, agent traces); field.npz and
status.png stay local. Existing sites in the index are kept.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path

import boto3


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", required=True)
    p.add_argument("--site", required=True)
    p.add_argument("--bucket", required=True)
    p.add_argument("--region", default=None)
    a = p.parse_args(argv)
    s3 = boto3.client("s3", region_name=a.region)
    root = Path(a.store) / "public" / "sites" / a.site
    n = 0
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix == ".npz" or f.name == "status.png":
            continue
        key = f"public/sites/{a.site}/{f.relative_to(root).as_posix()}"
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        s3.upload_file(str(f), a.bucket, key, ExtraArgs={"ContentType": ctype})
        n += 1
    local_index = json.loads((Path(a.store) / "public" / "sites" / "index.json").read_text(encoding="utf-8"))
    mine = next(e for e in local_index if e["site"] == a.site)
    try:
        remote = json.loads(s3.get_object(Bucket=a.bucket, Key="public/sites/index.json")["Body"].read())
    except Exception:
        remote = []
    merged = [e for e in remote if e["site"] != a.site] + [mine]
    merged.sort(key=lambda e: e["site"])
    s3.put_object(Bucket=a.bucket, Key="public/sites/index.json", Body=json.dumps(merged, indent=1),
                  ContentType="application/json")
    print(f"uploaded {n} files for {a.site}; index now lists {[e['site'] for e in merged]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
