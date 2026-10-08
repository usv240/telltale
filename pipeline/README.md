# TellTale pipeline

Camera-based slope deformation measurement and failure-time forecasting. Pure OpenCV 5 classical
vision (no neural networks) plus established geotechnical physics. Runs on a laptop with no cloud
dependency; the cloud worker imports this same package unchanged.

## Install and test

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt   # pinned: opencv-python 5.0.0.93, numpy 2.5.2, pytest 9.1.1
python -m pytest -q               # 21 tests, about 7 seconds
```

## What the stages do

| Stage | Module | OpenCV 5 calls | Purpose |
|---|---|---|---|
| A | `stack.py` | `phaseCorrelate`, `matchTemplate`, `warpAffine` | Register a burst to its first frame and median-stack it; flags UNSTABLE and BLIND epochs |
| B | `stabilize.py` | `ORB`, `BFMatcher`, `findHomography(USAC_MAGSAC)`, `estimateAffinePartial2D`, `warpPerspective` | Remove camera motion using operator-marked stable regions; coarse ORB fit refined by sub-pixel DIC; simplest camera model that explains the data; CAMERA_EVENT verdict when it cannot |
| C | `dic.py` | `cornerMinEigenVal`, `matchTemplate(TM_CCOEFF_NORMED)`, `warpAffine`, `phaseCorrelate` | Dense sub-pixel displacement: texture pre-screen, ZNCC peak, Gaussian sub-pixel fit, one re-sampling refinement pass, per-subset quality codes, phase-correlation cross-check |
| D | `masking.py` | `GaussianBlur`, `morphologyEx`, `findContours` | Exclude vegetation and water from temporal variance |
| E | `forecast.py` | numpy only | Carla et al. 2017 protocol: SMA/LMA velocities, onset of acceleration, inverse-velocity fit, bootstrap window, Theil-Sen and Voight ensemble, alarm ladder |
| - | `synthetic.py` | `resize(LANCZOS4 / AREA)`, `warpAffine` | Exact sub-pixel shift generator (E1) and Voight collapse simulator (E3 rehearsal) |

## Commands

```bash
python -m telltale e1                       # synthetic accuracy sweep; prints the G1 gate
python -m telltale simulate --jitter 1.0 --out out/sim   # collapse through the full pipeline
python -m telltale epoch --site site.json --ref bursts/ref --cur bursts/t0012 --t 12 --out out/site
python -m telltale forecast --series out/site/series.jsonl --zone slope --rolling
```

## Measured on this machine (Oct 8, 2026)

- E1 sweep, 256 px speckle, shifts 0.125 to 2.0 px, noise up to 2 percent, gain down to 0.85:
  mean absolute error 0.006 to 0.010 px, bias under 0.003 px, 95th percentile under 0.025 px.
  G1 gate (MAE under 0.05 px at 0.25 px) passes.
- Simulated collapse, 36 epochs, 1 px random camera jitter per epoch, true failure at t = 50:
  measurement MAE 0.007 px, forecast 50.33 with window [49.92, 52.36], r2 0.99, state CRITICAL.
- 1080p epoch with the default grid (3,116 subsets): 2.05 s single-threaded on a laptop.

## Conventions

- Images inside the pipeline are float32 grayscale in [0, 1].
- Displacement (u, v) is where reference content now sits in the current epoch, +u right, +v down.
- Nothing is interpolated over gaps. Unusable epochs are recorded with a reason (BLIND, UNSTABLE,
  CAMERA_EVENT, LOW_INLIERS, REVIEW), never silently dropped.
