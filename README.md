# TellTale

[![tests and claims](https://github.com/usv240/telltale/actions/workflows/tests.yml/badge.svg)](https://github.com/usv240/telltale/actions/workflows/tests.yml)

**TellTale stacks bursts from any fixed camera, removes the camera's own motion, measures ground creep to a hundredth of a pixel, forecasts the failure window, re-measures to verify it, and pages a person.**

On the public USGS time-lapse of an active coastal bluff, TellTale flagged 2 of 2 documented movement periods the camera could see and raised 0 false acceleration alarms across 147 quiet days in each of three zones; on the controlled sweep it measures displacement to 0.008 px, and on the public SEM DIC Challenge images to 0.005 px.

Classical OpenCV 5 computer vision, established geotechnical physics, and AWS. No neural
network anywhere; a person approves every public alert. Watching a slope costs about 1.40 USD
a month in a 50-slope district, or about 10.50 USD for one slope alone (report section 5).

Check every number on this page yourself, in about 20 seconds and without AWS:

```bash
python evaluation/verify_claims.py      # 11 claims against the result files, plus a live re-run of the accuracy sweep
```

Team Ground Truth, OpenCV AI Competition 2026, powered by AWS.
Live dashboard: https://d30le2uwgaimao.cloudfront.net/

## Why

Creep-type slope failures give warning: for days or weeks the surface moves a few millimetres
per day and keeps accelerating. Mines watch for this with ground-based radar, which costs enough that most sites run a single unit
(CSIRO), and evacuate in time (Bingham Canyon 2013, Brienz 2023). Communities that cannot afford
monitoring do not get the warning: half the people hit by landslides in the last five years had
none (World Risk Poll 2023), and in Wayanad in 2024 about 290 to 400 people died. TellTale applies the same
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
python -m pytest -q                                          # 33 tests, ~15 s
python -m telltale e1                                        # sub-pixel accuracy sweep
python -m telltale simulate --jitter 1.0 --out ../out/sim    # synthetic collapse, forecast
cd ..
python infra/scripts/seed_demo.py --local web/dashboard/demo-data   # full worker path, offline
python -m http.server 8765 -d web/dashboard                          # then open
#   http://127.0.0.1:8765/?root=demo-data/public/sites  (use the Replay slider)
python evaluation/e2_target.py                 # printable speckle target for the metrology test
python evaluation/e2_metrology.py --captures evaluation/e2/captures   # your photos -> mm table
```

Deploy to AWS with `infra/scripts/deploy.sh` (see `infra/README.md`), then
`python infra/scripts/seed_demo.py --s3 <bucket> --wait`. Judges: start with `docs/JUDGES.md`.
Operators: `docs/DEPLOYMENT.md` and the setup page on the dashboard.
Motion-magnified video of the demo creep: `python -m telltale magnify --site-dir ... --video`.

The agent's OpenCV tools are also an MCP server, so any MCP client can investigate a site:

```bash
pip install -r agent/requirements-mcp.txt
python -m agent.mcp_smoke                       # lists 9 tools, investigates the demo site over stdio
claude mcp add telltale -- python -m agent.mcp_server   # or use the repo's .mcp.json
```

## How this was built

The team used Claude Code as a coding assistant. The Agentic Vision claim rests on the agent
inside the product, Claude on Amazon Bedrock re-running OpenCV before it may page anyone
(`agent/`), not on the coding assistant. Every number is produced by a script in `evaluation/`
and checked by `evaluation/verify_claims.py`.

## Repository map

| Folder | What | Doc |
|---|---|---|
| `pipeline/` | OpenCV 5 pipeline and physics, CLI, tests | `pipeline/README.md`, `pipeline/DESIGN.md` |
| `infra/` | CloudFormation stack, Graviton worker, deploy and camera scripts | `infra/README.md`, `infra/DESIGN.md` |
| `web/dashboard/` | Static dashboard, about page, site setup tool, bundled demo data | `web/DESIGN.md` |
| `docs/` | Report, audit, judges' path, deployment guide, video shot list, published evidence of need, diagrams, figures | `docs/JUDGES.md` first |
| `evaluation/` | E1 to E6 harnesses and results | `evaluation/DESIGN.md` |
| `demo-rig/` | Tabletop collapse rig: build, capture script, run log | `demo-rig/DESIGN.md` |
| `agent/` | Supervising agent: OpenCV tools, Claude-on-Bedrock loop, rule policy, MCP server | `agent/DESIGN.md`, `docs/agent_workflow.svg` |

## Evidence status

| Test | Status | Headline |
|---|---|---|
| E1 synthetic sub-pixel accuracy | done | MAE 0.006 to 0.010 px, bias under 0.003 px, p95 under 0.025 px |
| E3 synthetic collapse through the full cloud path | done | forecast 50.26, window [48.9, 61.9], truth 50.0, R² 0.98 |
| E3b large motion (28 px collapse, 16 px search) | done | fixed reference + coarse-to-fine DIC: MAE 0.007 px, forecast t = 49.78; chaining 0.079 px; single-level fixed loses the slope |
| E3 tabletop physical collapse | not claimed | rig design and capture script shipped in `demo-rig/` |
| E2 physical metrology | not claimed (harness shipped) | synthetic self-test at 20, 50, 100 m: slope 1.00, RMS 0.01 to 0.05 mm; printable target in `evaluation/e2/` |
| E4 real landslide imagery (USGS Mukilteo) | done | documented Dec 9 2015 movement measured at 4 to 7x the quiet baseline with coherent downslope vectors; wet-lens period from Feb 10 correctly rejected |
| E4c real landslide in the product | done | the whole USGS record through the unmodified worker with the Claude agent; December 9 2015 verdict CONFIRMED; live as site `mukilteo-usgs` on the dashboard |
| E7 forecast on real slope failures (open collection, 6 sites) | done | CRITICAL before all 6 failures (Preonzo, Arvigo, Vajont, Hogarth, Veslemannen); last window contained the failure at 3 of 4 sites, median within 2 days at 3; 12 early false CRITICAL spells reported, which is why a person approves |
| E4b negative control on real data | done | 0 false acceleration alarms on 147 quiet days x 3 zones (was 371 before the onset gates); 2 of 2 observable movement periods flagged by the jump detector |
| E1 public benchmark (SEM 2D DIC Challenge 1.0) | done | MAE 0.0047 px on Sample 1, best of TellTale, Farneback and pyramidal LK; within 0.01 px of the best on the noisier sets |
| E1 named baselines | done | TellTale 0.004 px median vs Farneback 0.010, pyramidal LK 0.034, phase correlation 0.67 on the synthetic sweep |
| E5 confounders (thresholds only) | done | zero false alarms under camera bump, lighting step, fog; non-rigid lens distortion partially caught |
| E5 agent ablation (off / rules / Claude on Bedrock) | done | zero false pages in every arm; agent closes all seven camera-distortion events as false alarms and pages a person at confirmed acceleration, 42 time units before failure against 3 for thresholds alone |
| E6 Graviton vs x86, COOL vs stock | done | c8g.large 1.72 s per epoch vs c7i.large 2.73 s, 44 percent cheaper per 1,000 epochs; COOL (OpenCV 5.1.0-dev, Marketplace AMI) verified in production, passes all tests with identical fields, 5.7 to 6.6 percent slower per epoch on this workload, faster on ORB (1.45x) and corner response (1.52x) |

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
18:2161 (2018) global fatal landslides. Who needs this, with 30 opened sources (UN Sendai
Framework, India's NDMA strategy, field camera studies, Brienz and Preonzo forecasts):
`docs/PUBLISHED-RECORD.md`.
