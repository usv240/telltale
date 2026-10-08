# Pipeline Design: Vision Core and Physics

Sub-project: `pipeline/`. Python package `telltale` implementing everything from raw frames to a
failure-time forecast. This is the part of the system judges will weigh hardest (technical
execution, 30 percent), so every stage below states its method, its parameters, its failure
modes, and how it is tested.

Design rule: local first. The full pipeline runs on a laptop from the CLI with zero AWS
dependencies. The cloud worker (see `infra/DESIGN.md`) imports this same package unchanged.

## 1. Data model

- **Site**: one camera pointed at one scene. Configuration (JSON): camera intrinsics hint
  (focal length equivalent, sensor width), scene scale (millimeters per pixel at the target
  distance, entered by the operator or derived from two marked points of known separation),
  polygon masks for STABLE regions (bedrock, buildings off the landslide) and TARGET zones
  (areas whose motion matters), grid parameters, alert thresholds, contact channels.
- **Epoch**: one burst of N frames (default 7) captured within a few seconds, at time t.
  Bursts, not single frames, because atmospheric shimmer averages toward zero across a burst
  while real displacement does not.
- **Reference epoch**: the stacked image all later epochs are compared against. Rotated on a
  schedule (default 30 days) or when the agent decides decorrelation demands it; displacement
  chains across reference changes so the series stays continuous.
- **Displacement field**: per grid subset: (u, v) in pixels, peak correlation, peak sharpness,
  texture score, validity flag. Serialized as `.npz` plus a rendered overlay `.png`.
- **Zone series**: per target zone: time series of robust displacement (median over valid
  subsets), with spread (median absolute deviation) as the per-epoch uncertainty.

## 2. Stage A: burst stacking (atmosphere and noise suppression)

1. Convert frames to grayscale float32.
2. Register frames 2..N to frame 1 with `cv2.phaseCorrelate` on a Hanning-windowed, downscaled
   copy (global translation only; a burst spans seconds, so the scene is rigid).
3. Median-stack the registered burst into one epoch image.

Why median: robust to birds, rain streaks, and single-frame glints. Why phase correlation:
subpixel global shift estimation in one call, cheap and deterministic.

Failure modes handled: if inter-frame shifts exceed a bound (default 3 px), the burst is flagged
UNSTABLE (wind-shaken mount) and the epoch's uncertainty is inflated; if frame contrast is
degenerate (fog, night), the epoch is marked BLIND and skipped, and blindness is reported, never
hidden.

## 3. Stage B: stabilization (camera motion vs ground motion)

The most important honesty mechanism in the system.

1. Detect ORB keypoints only inside STABLE region masks, in the reference and current epoch.
2. Match with BFMatcher and Lowe ratio test (0.75).
3. Estimate homography with `cv2.findHomography(..., cv2.USAC_MAGSAC)`, the robust estimator
   framework that is the default family in OpenCV 5.
4. Warp the current epoch onto reference geometry with `cv2.warpPerspective`, Lanczos
   interpolation.
5. Record diagnostics: inlier count, reprojection RMS, and the homography's deviation from
   identity decomposed into translation, rotation, and scale.

Decision logic: if stable regions themselves show coherent apparent motion after warping, the
verdict is CAMERA EVENT (mount moved, thermal drift), not ground motion, and no displacement is
appended for that epoch; the agent is notified instead. This single rule removes the largest
false-alarm class in camera monitoring.

## 4. Stage C: digital image correlation (the measurement)

For each subset center on a regular grid (default: 41 x 41 px template, 24 px stride, search
radius 16 px, all configurable):

1. Texture pre-screen: minimum eigenvalue of the structure tensor (`cv2.cornerMinEigenVal`
   summarized over the subset). Subsets below threshold are marked LOW_TEXTURE and excluded,
   honestly reducing coverage rather than emitting noise.
2. ZNCC matching: `cv2.matchTemplate` with `TM_CCOEFF_NORMED` of the reference subset against
   the search window in the current epoch. ZNCC is invariant to affine illumination change,
   which is why sunlight variation does not read as motion.
3. Sub-pixel refinement: two-dimensional paraboloid fit over the 3 x 3 correlation neighborhood
   around the integer peak. Standard, fast, and accurate to a few hundredths of a pixel on
   textured scenes.
4. Quality control per subset: minimum peak correlation (default 0.5), peak sharpness (ratio of
   best to second-best local maximum, default 1.05), and displacement magnitude sanity bound.
5. Cross-check (sampled): `cv2.phaseCorrelate` on Hanning-windowed subsets for a random 10
   percent of the grid; median disagreement with ZNCC beyond 0.3 px flags the epoch REVIEW.

Output: DisplacementField. Zone displacement = median of valid subset displacements inside the
zone polygon; uncertainty = 1.4826 x MAD (a robust sigma estimate).

Compute note (COOL relevance): the per-epoch cost is dominated by thousands of `matchTemplate`
calls plus warps, blurs, and resizes. This is exactly the classical imgproc profile that COOL
accelerates on Graviton; the benchmark harness in `evaluation/` measures it directly.

## 5. Stage D: masking over time

- Vegetation mask: per-pixel temporal variance over a trailing window of epochs, blurred
  (`cv2.GaussianBlur`), thresholded, cleaned with morphology, contoured. High-variance regions
  (foliage, water) are excluded from the grid.
- Seasonal decorrelation: when the fraction of valid subsets in a zone decays below a floor,
  the agent is asked to consider a reference refresh (see `agent/DESIGN.md`).

## 6. Stage E: physics and forecasting

Implements the operational protocol of Carla, Intrieri et al., Landslides 14:517-534 (2017),
plus an ensemble, per the four-method reliability evaluation in Landslides (2024).

1. Series conditioning: zone displacement series resampled to a uniform grid; gaps carried as
   widened uncertainty, not interpolation fantasy.
2. Velocity: derivative of displacement after two moving averages, short (SMA, default 3
   epochs) and long (LMA, default 7 epochs), following the guidelines paper.
3. Onset of acceleration (OOA): declared when SMA velocity exceeds LMA velocity for k
   consecutive epochs (default 3) with positive acceleration and displacement above the noise
   floor. Before OOA the site is in state QUIET or MOVING (steady creep).
4. Inverse-velocity fit: from OOA onward, weighted linear regression of 1 / v(SMA) against
   time (Fukuzono, alpha = 2 case). Predicted failure time is the time-axis intercept.
5. Uncertainty: residual bootstrap (default 500 draws) around the regression, combined with
   per-epoch velocity uncertainty, yielding a failure window [t10, t90] and a trend quality
   score (R squared of the 1/v fit).
6. Ensemble: linear inverse velocity, a Voight-style nonlinear fit with alpha free in
   [1.5, 2.2], and a robust Theil-Sen variant of the linear fit. Reported forecast is the
   ensemble median; disagreement widens the reported window. Never a bare timestamp.
7. Alarm ladder: QUIET, MOVING, ACCELERATING (OOA confirmed), CRITICAL (forecast horizon below
   the site threshold with fit quality above floor). Transitions up the ladder require the
   agent's investigation to pass; the external alert at CRITICAL requires human approval.

Stated limits (also on the landing site): the method addresses creep-type failures; brittle
liquefaction collapses can fail without surface precursor (Brumadinho analysis, Zhu, Zhang and
Puzrin 2023). Night, fog, and heavy rain create measurement gaps; gaps widen uncertainty and are
displayed as blindness, never silence.

## 7. Synthetic truth machine (E1 and the collapse simulator)

Two generators, both in the package so tests and CI can run them anywhere:

- **Shift generator (E1)**: takes any texture image, supersamples 8x with Lanczos, shifts by an
  integer number of supersampled pixels, downsamples back, giving an exact known sub-pixel
  shift (multiples of 0.125 px) with realistic resampling. Adds configurable Gaussian noise,
  illumination gain and bias, and blur. The E1 harness sweeps shift magnitudes and perturbations
  and reports bias and sigma with confidence intervals.
- **Collapse simulator (E3 rehearsal)**: renders an epoch sequence where a target region moves
  with Voight kinematics d(t) = c - a * ln(tf - t) (alpha = 2), i.e. velocity accelerating as
  1 / (tf - t), against a static background, with noise and illumination drift. The full
  pipeline runs on the rendered frames and the forecast is compared to the true tf. This is the
  end-to-end correctness test: measurement plus physics recovering a known failure time.

## 8. Package layout

```
pipeline/
  DESIGN.md              this file
  requirements.txt       pinned
  telltale/
    __init__.py
    config.py            Site/Grid dataclasses, JSON load/save
    stack.py             Stage A
    stabilize.py         Stage B
    dic.py               Stage C
    masking.py           Stage D
    forecast.py          Stage E
    synthetic.py         Section 7 generators
    overlay.py           heatmap and vector overlays (cv2 only)
    series.py            zone time-series store (JSON lines)
    cli.py               `python -m telltale <command>`
  tests/
    test_dic.py          known shifts recovered within tolerance
    test_stabilize.py    injected homography removed; camera-event verdict fires
    test_forecast.py     synthetic creep recovers true failure time
    test_stack.py        burst registration and median stack behavior
```

CLI commands: `e1` (accuracy sweep), `simulate` (collapse simulator end to end),
`epoch` (process one burst directory against a site config), `forecast` (recompute forecast
from a stored series).

## 9. Performance budget

Per epoch at 1080p with default grid (about 3,300 subsets): under 2 seconds on a laptop core,
under 1 second on c8g with COOL (to be measured in E6). At 4K with a dense grid (about 30,000
subsets): the cloud worker's job, parallel across cores; budget under 20 seconds per epoch.
Daily cadence per site is therefore pennies; the cost model lives in `infra/DESIGN.md`.

## 10. Testing policy

Every numerical claim in the report must be produced by a script in `evaluation/`, from a clean
clone, with a fixed seed. Unit tests run in CI on every commit. The E1 table and the simulate
command's forecast error are the pipeline's regression tests: if accuracy degrades, the build
fails loudly.
