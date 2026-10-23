"""Add evidence images to agent traces written before remeasure saved them, and check that
re-running each published re-measurement reproduces its numbers.

    python infra/scripts/backfill_evidence.py --s3 telltale-<account> --site demo-slope
    python infra/scripts/backfill_evidence.py --local web/dashboard/demo-data --site demo-slope

For every ``remeasure`` call in ``public/sites/<site>/agent/<t>.json`` this re-runs the same
call on the stored images, renders the field, stores it beside the trace, and adds
``evidence_png`` to that call's result. A trace is only rewritten when every re-run matches the
published magnitude within ``--tol`` px, so the backfill can never change what a verdict rested on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "infra" / "worker"))
sys.path.insert(0, str(ROOT))

import worker as W  # noqa: E402
from agent.tools import Toolbox  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--s3", help="bucket of the deployed stack")
    g.add_argument("--local", help="local store root")
    p.add_argument("--site", required=True)
    p.add_argument("--region", default=None)
    p.add_argument("--tol", type=float, default=1e-3)
    a = p.parse_args(argv)
    store = W.S3Store(a.s3, a.region) if a.s3 else W.LocalStore(a.local)
    pub = f"public/sites/{a.site}"
    log = json.loads(store.get(f"{pub}/agentlog.json") or b'{"events": []}')
    worst, written, skipped, missing = 0.0, 0, 0, 0
    for ev in log["events"]:
        key = f"{pub}/agent/{ev['t']:g}.json"
        raw = store.get(key)
        if raw is None:
            continue
        tr = json.loads(raw)
        ok, changed = True, False
        for c in tr.get("calls", []):
            if c["tool"] != "remeasure" or "error" in c["result"] or c["result"].get("evidence_png"):
                continue
            tb = Toolbox(store, a.site, None, event_t=ev["t"])
            tb.calls = [None] * (c["n"] - 1)          # file the image under the original call number
            r = tb.remeasure(c["args"]["t"], c["args"].get("reference", "previous"))
            if "error" in r:
                print(f"t={ev['t']:g} call {c['n']}: cannot re-run ({r['error']}); left as published")
                missing += 1
                continue
            for z, v in c["result"].get("zones", {}).items():
                d = abs(r["zones"][z]["magnitude"] - v["magnitude"])
                worst = max(worst, d)
                ok &= d <= a.tol
            c["result"]["evidence_png"] = r.get("evidence_png")
            changed = True
        if changed and ok:
            store.put(key, json.dumps(tr, indent=1, default=str).encode(), "application/json")
            written += 1
        elif changed:
            skipped += 1
            print(f"t={ev['t']:g}: re-run did not reproduce the published numbers; trace left as it was")
    print(f"{written} traces given evidence images, {skipped} left unchanged, {missing} calls without "
          f"stored images; largest difference from the published magnitude {worst:.2e} px")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
