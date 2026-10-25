"""E5 agent ablation: the same confounder scenarios through the worker, with the supervising
agent off (thresholds only), rule-based, and LLM-driven (Claude on Amazon Bedrock).

    python evaluation/e5_agent.py --arms off rules llm --out evaluation/results

Scoring per scenario:
  false page      a human was paged (or, with the agent off, a CRITICAL transition fired the
                  worker's page) in a scenario where nothing real happened
  correct page    a human was paged in the creep scenario
  verdicts        agent verdicts per event and the number of OpenCV tool calls it made
Traces are written by the agent to <out>/e5_agent/<arm>/<scenario>/public/sites/.../agent/.
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
sys.path.insert(0, str(ROOT / "evaluation"))
sys.path.insert(0, str(ROOT))

from e5_confounders import build  # noqa: E402
from telltale.config import ForecastConfig, GridConfig, SiteConfig  # noqa: E402
from telltale.stack import translate  # noqa: E402
from telltale.synthetic import perturb  # noqa: E402

SCENARIOS = ["quiet", "quiet+bump", "quiet+lighting", "quiet+fog", "quiet+lens", "creep+bump"]


class CountingAlerting:
    """Stands in for SNS: counts pages instead of sending them."""
    topic = "counter"

    def __init__(self):
        self.pages = []

    def links(self, site, t):
        return {"approve": f"approve://{site}/{t}", "dismiss": f"dismiss://{site}/{t}"}

    def publish(self, subject, message):
        self.pages.append({"subject": subject, "message": message[:400]})


def run_arm(arm: str, out: Path, size: int, seed: int) -> dict:
    import worker as W
    os.environ["TELLTALE_AGENT"] = arm
    rng = np.random.default_rng(seed + 7)
    results = {}
    for name in SCENARIOS:
        epochs, times, zone, stable, true_tf = build(name, size, seed)
        site_dir = out / "e5_agent" / arm / name
        shutil.rmtree(site_dir, ignore_errors=True)
        store = W.LocalStore(site_dir)
        counter = CountingAlerting()
        W._ALERTING = counter
        cfg = SiteConfig(name=name, mm_per_px=1.0, stable_polys=[stable], target_zones={"slope": zone},
                         grid=GridConfig(template=41, stride=16, search=16), forecast=ForecastConfig())
        for k, ((frame, gain), t) in enumerate(zip(epochs, times)):
            fr = [np.clip(perturb(translate(frame, rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4)),
                                  noise=0.015, gain=gain, rng=rng) * 255, 0, 255).astype(np.uint8)
                  for _ in range(5)]
            W.process_epoch(store, name, float(t), fr, asdict(cfg) if k == 0 else None)
        fc = json.loads(store.get(f"public/sites/{name}/forecast.json"))
        raw = store.get(f"public/sites/{name}/agentlog.json")
        events = json.loads(raw)["events"] if raw else []
        pages = [p for p in counter.pages if "left CRITICAL" not in p["subject"]]   # every page to a person
        results[name] = {
            "final_state": fc["state"], "true_tf": true_tf,
            "pages": len(pages), "false_page": bool(pages) and true_tf is None,
            "correct_page": bool(pages) and true_tf is not None,
            "events": [{k: e[k] for k in ("t", "event", "verdict", "n_tool_calls", "paged_human", "seconds")} for e in events],
            "verdicts": [e["verdict"] for e in events],
            "tool_calls": sum(e["n_tool_calls"] for e in events),
            "forecast": {k: fc["zones"].get("slope", {}).get(k) for k in ("tf", "t_lo", "t_hi", "r2")},
        }
        print(f"[{arm:5}] {name:16} state={fc['state']:12} pages={len(pages)} events={len(events)} "
              f"verdicts={results[name]['verdicts']} tool_calls={results[name]['tool_calls']}")
    return results


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arms", nargs="+", default=["off", "rules", "llm"])
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    allres = {}
    for arm in a.arms:
        allres[arm] = run_arm(arm, out, a.size, a.seed)
    summary = {arm: {"false_pages": sum(r["false_page"] for r in res.values()),
                     "correct_pages": sum(r["correct_page"] for r in res.values()),
                     "events": sum(len(r["events"]) for r in res.values()),
                     "tool_calls": sum(r["tool_calls"] for r in res.values())}
               for arm, res in allres.items()}
    print(json.dumps(summary, indent=1))
    (out / "e5_agent.json").write_text(json.dumps({"summary": summary, "arms": allres}, indent=1, default=str),
                                       encoding="utf-8")
    print(f"wrote {out / 'e5_agent.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
