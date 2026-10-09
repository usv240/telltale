# For judges: the ten-minute path

Everything below works without contacting us. Times are what it took us on a laptop.

## 1. See it working (2 minutes)

Open https://d30le2uwgaimao.cloudfront.net/ . Press **Play** on the replay slider: the demo slope
creeps, accelerates, the forecast window appears and narrows, the state climbs to CRITICAL, and
the supervising agent's investigations appear in the agent panel with every OpenCV tool call.
The instrument-health panel shows which OpenCV build ran on which instance.
"How it works" (top right) explains every panel in plain language.

## 2. Run it yourself, offline (3 minutes)

```bash
git clone https://github.com/usv240/telltale && cd telltale/pipeline
python -m venv ../.venv && ../.venv/Scripts/activate      # or source ../.venv/bin/activate
pip install -r requirements.txt                           # pinned
python -m pytest -q                                       # 24 tests, ~8 s
python -m telltale e1                                     # sub-pixel accuracy sweep, prints the gate
python -m telltale simulate --jitter 1.0 --out ../out/sim # collapse through the full pipeline
cd .. && python infra/scripts/seed_demo.py --local web/dashboard/demo-data   # the worker path, no AWS
python -m http.server 8765 -d web/dashboard               # open http://127.0.0.1:8765/?root=demo-data/public/sites
```

The offline run exercises the same `process_epoch` the cloud worker runs, with the rule-based
supervisor instead of Claude.

## 3. The evidence (3 minutes)

| Claim | Where to look |
|---|---|
| Sub-pixel accuracy 0.01 px | `evaluation/results/e1-*` from CI artifacts, or run `telltale e1` |
| Forecast recovers a known failure time | `pipeline/tests/test_end_to_end.py`, `telltale simulate` |
| Real landslide: documented movement days stand out 4 to 7x | `evaluation/results/e4_mukilteo.json`, `docs/figures/e4_*` |
| 0 false acceleration alarms on 147 real quiet days x 3 zones; 2 of 2 observable periods flagged | `evaluation/results/e4_forecast_snr3_t4.json` (and `_snr0_t0` for the rule before the fix) |
| Public benchmark and named baselines | `evaluation/results/e1_dic_challenge.json`, `evaluation/results/e1_baselines.json` |
| Zero false alarms under bump, lighting, fog; lens distortion partly caught | `evaluation/results/e5_confounders.json` |
| Agent closes all camera-artefact events as false alarms, pages a person 42 time units before failure (thresholds alone: 3) | `evaluation/results/e5_agent.json`, agent panel traces |
| Graviton vs x86 cost and speed | `evaluation/results/e6_*.json` |
| COOL executes the core workload | `runtime.cv2_file` in every record, instrument-health panel |
| Human control works | approval links in `forecast.json`, `decisions.json`, section 9 of the report |

Full report: `docs/REPORT.md`. Diagrams: `docs/architecture.svg`, `docs/agent_workflow.svg`.
Audit of our own gaps: `docs/AUDIT.md`.

## 4. Deploy it (10 minutes, optional)

`infra/scripts/deploy.sh` with AWS credentials creates the whole stack from one CloudFormation
template and prints the dashboard URL; `--cool <ami>` switches the worker to the COOL AMI.
`infra/scripts/teardown.sh` removes it. Details in `infra/README.md`.

## 5. What we do not claim

Creep-type failures only; daylight; a camera on stable ground. Night, fog, wet lens and a
camera inside the slide are detected and reported, not solved. Every number in the report comes
from a script in `evaluation/`, and synthetic numbers are labelled synthetic.
