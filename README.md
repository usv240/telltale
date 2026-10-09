# TellTale

**See the ground move before it fails.** TellTale turns any fixed camera into a sub-pixel
displacement instrument that measures slope creep and forecasts the time of failure, using
classical OpenCV 5 computer vision, established geotechnical physics, and AWS.

Team Ground Truth, OpenCV AI Competition 2026, powered by AWS.
Live dashboard: https://d30le2uwgaimao.cloudfront.net/

## Why

Creep-type slope failures give warning: for days or weeks the surface moves a few millimetres
per day and keeps accelerating. Mines watch for this with radar that costs 100k to 500k USD per
site, and evacuate in time (Bingham Canyon 2013, Brienz 2023). Communities that cannot afford
monitoring do not get the warning (Wayanad 2024, about 400 deaths). TellTale applies the same
physics to a 30 to 50 USD camera and cents of cloud compute per day. It is not a radar: it
measures what a camera can see, in daylight, on creep-type failures, and it says so when it
cannot see.

## How it works

1. **Capture.** A camera photographs the slope in short bursts, several times a day.
2. **Stack.** Each burst is registered and median-stacked; atmospheric shimmer averages out,
   real displacement does not.
3. **Stabilise.** ORB features in operator-marked stable regions plus USAC/MAGSAC give a coarse
   camera model; dense sub-pixel correlation refines it; the simplest model that explains the
   stable ground is chosen. If the stable ground still appears to move, the epoch is a
   CAMERA_EVENT and no ground displacement is recorded.
4. **Measure.** Zero-normalised cross-correlation on thousands of subsets, a Gaussian sub-pixel
   peak fit, one re-sampling refinement pass, per-subset quality control. Accuracy on the
   synthetic sweep: about 0.01 px mean absolute error.
5. **Forecast.** Velocity, onset of acceleration, and the inverse-velocity method
   (Fukuzono 1985; Carlà et al. 2017) with a bootstrap window and a three-method ensemble.
   The alarm ladder is QUIET, MOVING, ACCELERATING, CRITICAL. A public alert always needs a
   human.

Everything the cloud worker does, the laptop does too, from the same package.

## Quickstart

```bash
cd pipeline
python -m venv ../.venv && ../.venv/Scripts/activate        # or source ../.venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                                          # 21 tests, ~7 s
python -m telltale e1                                        # sub-pixel accuracy sweep
python -m telltale simulate --jitter 1.0 --out ../out/sim    # synthetic collapse, forecast
cd ..
python infra/scripts/seed_demo.py --local web/dashboard/demo-data   # full worker path, offline
python -m http.server 8765 -d web/dashboard                          # then open
#   http://127.0.0.1:8765/?root=demo-data/public/sites
```

Deploy to AWS with `infra/scripts/deploy.sh` (see `infra/README.md`), then
`python infra/scripts/seed_demo.py --s3 <bucket> --wait`.

## Repository map

| Folder | What | Doc |
|---|---|---|
| `pipeline/` | OpenCV 5 pipeline and physics, CLI, tests | `pipeline/README.md`, `pipeline/DESIGN.md` |
| `infra/` | CloudFormation stack, Graviton worker, deploy and camera scripts | `infra/README.md`, `infra/DESIGN.md` |
| `web/dashboard/` | Static dashboard (no framework) with bundled demo data | `web/DESIGN.md` |
| `evaluation/` | E1 to E6 harnesses and results | `evaluation/DESIGN.md` |
| `demo-rig/` | Tabletop collapse rig: build, capture script, run log | `demo-rig/DESIGN.md` |
| `agent/` | Supervising agent: OpenCV tools, Claude-on-Bedrock loop, rule policy | `agent/DESIGN.md`, `docs/agent_workflow.svg` |

## Evidence status

| Test | Status | Headline |
|---|---|---|
| E1 synthetic sub-pixel accuracy | done | MAE 0.006 to 0.010 px, bias under 0.003 px, p95 under 0.025 px |
| E3 synthetic collapse through the full cloud path | done | forecast 50.26, window [48.9, 61.9], truth 50.0, R² 0.98 |
| E3 tabletop physical collapses | pending | rig and capture script ready |
| E2 physical metrology | pending | |
| E4 real landslide imagery (USGS Mukilteo) | done | documented Dec 9 2015 movement measured at 4 to 7x the quiet baseline with coherent downslope vectors; wet-lens period from Feb 10 correctly rejected |
| E5 confounders (thresholds only) | done | zero false alarms under camera bump, lighting step, fog; non-rigid lens distortion partially caught |
| E5 agent ablation (off / rules / Claude on Bedrock) | done | zero false pages in every arm; agent closes all four camera-distortion events as false alarms and pages a person at confirmed acceleration, 39 time units earlier than thresholds alone |
| E6 Graviton vs x86 | done | c8g.large 1.72 s per epoch vs c7i.large 2.73 s; 44 percent cheaper per 1,000 epochs; COOL cell pending subscription |

## Scope and responsible use

- Creep-type failures only. Brittle and liquefaction collapses can fail with little surface
  precursor (Brumadinho 2019); this is stated, not hidden.
- Night, fog and heavy rain create measurement gaps. Gaps widen the forecast uncertainty and are
  shown as unusable epochs, never silence.
- Cameras point at ground and structures. There is no person detection or face processing
  anywhere in the code.
- The system never sends a public alert on its own; CRITICAL requests human approval.

## References

Fukuzono (1985) inverse-velocity method; Carlà, Intrieri et al., Landslides 14:517 (2017)
alarm-threshold guidelines; Geosciences 13:371 (2023) DIC for landslide monitoring;
Remote Sensing 13:893 (2021) low-cost time-lapse slope monitoring; Froude and Petley, NHESS
18:2161 (2018) global fatal landslides. Full bibliography in `RESEARCH.md`.
