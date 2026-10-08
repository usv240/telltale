# Evaluation Design: E1 to E6

Sub-project: `evaluation/`. Every number in the report is produced by a script in this folder,
from a clean clone, with fixed seeds. Failure cases are first-class results, not footnotes;
Rules.md explicitly requires evaluation evidence "including failure cases or limitations".

## E1: Synthetic sub-pixel accuracy

- Method: the shift generator (pipeline `synthetic.py`) produces image pairs with exact known
  sub-pixel shifts (multiples of 0.125 px via 8x supersampling), across three texture classes
  (rock face crop, soil crop, low-texture grass crop) and perturbations: Gaussian noise (sigma
  0, 2, 5 gray levels), illumination gain 0.8 to 1.2 with bias, Gaussian blur to 1.5 px.
- Sweep: shifts 0.125 to 2.0 px, 30 trials per cell, both axes.
- Report: bias and sigma per condition with bootstrap confidence intervals; the headline is the
  95th percentile absolute error on textured classes at realistic noise.
- Gate G1: mean absolute error at 0.25 px shift below 0.05 px on textured classes.

## E2: Physical metrology (the rig does not lie)

- Rig: printed random-speckle target on a rigid board, mounted on a micrometer translation
  stage (or a printed vernier sled, accuracy 0.05 mm), photographed from 20, 50, and 100 m
  with a phone (1x and telephoto) on a tripod.
- Protocol: 5 known moves per distance (0.5, 1, 2, 5, 10 mm), bursts before and after each
  move, full pipeline including stabilization against surrounding scene.
- Report: measured vs true regression, slope and intercept with confidence intervals, per
  distance and lens; converts directly into the deployment guidance table (what precision to
  expect at what range with what lens).

## E3: Tabletop failures (end-to-end truth)

- Rig: see `demo-rig/DESIGN.md`. Sand-soil slope in a tank, drip-infiltration triggered, camera
  on tripod, LED lighting, continuous burst capture.
- Runs: at least 5 collapses. True failure time from the video record (first general movement
  frame, annotated independently by both team members).
- Report: forecast error vs lead time curve: at 30, 15, 10, 5, 2 minutes before collapse, what
  window did the system publish and did the true time fall inside it. Also: how early was OOA
  declared, and false-alarm count across the quiet phases of all runs.
- Honest framing: tabletop validates the pipeline and physics loop, not field-scale soil
  mechanics; field validity rests on E4 plus the literature (GeoPIV lineage, DIC landslide
  papers cited in RESEARCH.md).

## E4: Real-world data

- Mukilteo (USGS public-domain time-lapse of an active coastal bluff, 2015-2016): run the full
  pipeline; report displacement fields, coherent-motion regions, valid-subset coverage, and a
  qualitative comparison against the USGS event record for the season.
- Slumgullion (USGS 2024 imagery + published GPS rates): measure velocity over the active body
  from repeat imagery; compare magnitude and direction against published rates.
- Stretch: Brienz 2023 public webcam frames, pre-collapse acceleration extraction.
- Report: measured fields with uncertainty, agreement statistics where ground truth exists,
  and an explicit list of what did not work (decorrelated regions, weather gaps).

## E5: Agent ablation

- Scenario suite defined in `agent/scenarios/`: camera bump, lighting step, fog, vegetation
  flutter, true acceleration, true acceleration plus same-day camera bump.
- Each scenario run with (a) thresholds only, (b) agent enabled, same seeds.
- Report: false alarms per scenario, missed or late OOA, forecast quality at fixed leads,
  and complete decision traces for two representative events (one correctly suppressed false
  alarm, one correctly escalated true alarm). These traces are the Agentic award evidence.

## E6: COOL benchmark

- Same epoch workload (1080p and 4K grids) run on: COOL v3.1 on c8g, stock OpenCV 5 wheel on
  the same c8g, stock wheel on c7i at matched vCPUs.
- 20 warm repetitions per cell; report p50 and p95 epoch latency, epochs per hour, cost per
  1,000 epochs at on-demand pricing, nights of monitoring per dollar at daily cadence.
- Proof of execution: `cv2.__file__`, build info hash, instance metadata captured in the
  result rows. Publishing the harness makes the claim reproducible by judges.

## Outputs

`evaluation/results/` holds CSVs and generated figures; the landing site's Evidence section and
the report tables are generated from these files, never hand-typed.
