# TellTale: technical report (draft, October 9, 2026)

TellTale stacks bursts from any fixed camera, removes the camera's own motion, measures ground creep to a hundredth of a pixel, forecasts the failure window, re-measures to verify it, and pages a person.

Team Ground Truth: Ujwal Suresh Vanjare, Arpita Madhukar Kalburgi.
OpenCV AI Competition 2026, powered by AWS. Featured paths: Best Use of COOL (pending
subscription); Agentic Vision (claimed: supervising agent on Amazon Bedrock, section 6b).

Live endpoint: https://d30le2uwgaimao.cloudfront.net/ (how it works: /about.html)
Repository: https://github.com/usv240/telltale (CI on x86 and arm64)

> Status markers: **measured** means the number comes from a script in `evaluation/` or from
> the deployed system; **pending** means the method exists but the run has not happened.
> Every pending item is listed in section 9.

## 1. Problem

Fatal landslides kill more than 4,000 people in a typical year, concentrated where nobody can
afford monitoring. Creep-type slope failures give days to weeks of warning: the surface moves
millimetres per day and accelerates. The inverse-velocity method turns that acceleration into a
failure-time forecast, and mines have relied on it with 100k to 500k USD radar for decades
(Bingham Canyon 2013: evacuated the morning of a 165-million-tonne collapse, no casualties).
Communities without instruments do not get the warning (Wayanad 2024, about 400 deaths).

TellTale applies the radar's physics to a 30 to 50 USD camera, for creep-type failures in
daylight: measure sub-pixel surface displacement, reject everything that merely looks like
motion, forecast the failure window with uncertainty, and put a person in the loop before any
alert. Measured precision: about 0.01 px on synthetic imagery (E1) and 0.1 to 0.4 px of daily
scatter on a real vegetated bluff (E4); it is not a substitute for radar where radar exists.

## 2. Users

District disaster-management offices and hill-town municipalities; small mines and quarries
that cannot justify radar; construction sites with deep excavations and retaining walls; road
and rail authorities in mountain corridors. Operators mark stable regions and target zones once;
duty officers read one sentence on the dashboard; experts drill into the series and fit.

## 3. Architecture

See `docs/architecture.svg`. Field camera, burst upload to S3 (frames first, manifest last), S3
event to SQS with a dead-letter queue, one Graviton EC2 worker running the OpenCV 5 pipeline,
artifacts published to a `public/` prefix served by CloudFront, CloudWatch metrics and three
alarms (queue age, dead-letter queue, worker stopped) that publish to an SNS topic with an
optional e-mail subscriber. A Lambda function URL records human approve / dismiss decisions
from HMAC-signed links. The supervising agent runs on the worker and calls Claude on Amazon
Bedrock. One CloudFormation template; one deploy script; one code path for laptop and cloud
(`infra/worker/worker.py` has a local and an S3 storage backend); GitHub Actions runs the test
suite, the E1 gate and the offline worker path on x86 and arm64 on every push.

## 4. OpenCV 5 implementation

All vision is classical `core` and `imgproc`; there is no neural network in the system.

| Stage | Method | OpenCV 5 calls |
|---|---|---|
| A Stack | Register burst frames to frame 1 (phase correlation for the coarse shift, ZNCC on a large central template for sub-pixel precision), median-stack. Contrast below 2 percent is BLIND; inter-frame shift above 3 px is UNSTABLE. | `phaseCorrelate`, `createHanningWindow`, `matchTemplate`, `warpAffine` |
| B Stabilize | ORB in operator-marked stable regions, Lowe ratio 0.75, homography with `USAC_MAGSAC`. The coarse warp is then correlated against the reference inside the stable regions with the same sub-pixel DIC as the measurement; those correspondences are mapped back to the current frame and the simplest camera model that explains them (translation, similarity, affine, homography) is selected by residual. A verification pass measures what is left: coherent residual above 0.3 px or scatter above 0.3 px is a CAMERA_EVENT and the epoch is rejected. | `ORB_create`, `BFMatcher`, `findHomography(USAC_MAGSAC)`, `estimateAffinePartial2D`, `estimateAffine2D`, `perspectiveTransform`, `warpPerspective` |
| C Measure | Optional coarse-to-fine pyramid (`pyrDown`, normalised-convolution infill of the coarse field, residual search at each finer level) so a fixed reference can follow motions of tens of pixels (E3b). Regular grid of 41 px subsets at 24 px stride (3,000 to 3,500 per 1080p frame). Texture pre-screen on the mean minimum eigenvalue of the structure tensor. ZNCC (`TM_CCOEFF_NORMED`) over a 16 px search radius; separable three-point Gaussian sub-pixel fit; one re-sampling pass (window shifted by the fractional estimate with Lanczos, re-matched) which halves the residual pixel-locking bias; per-subset codes OK, LOW_TEXTURE, LOW_CORR, LOW_MARGIN, OUT_OF_BOUND, EDGE_PEAK. A random 10 percent of valid subsets is cross-checked with phase correlation on 2x patches as a gross-error detector. Zone displacement is the median over valid subsets; uncertainty is 1.4826 x MAD. | `cornerMinEigenVal`, `boxFilter`, `matchTemplate`, `warpAffine`, `phaseCorrelate`, `fillPoly` |
| D Mask | Temporal-variance mask for vegetation and water, applied from a trailing window of epochs when `mask_window` is set. | `GaussianBlur`, `morphologyEx`, `findContours` |
| Scale | Metric conversion across an oblique slope: a homography from image to the ground plane (least squares or RANSAC on surveyed point pairs) whose local Jacobian converts each subset's pixel displacement to millimetres; a scalar `mm_per_px` remains the simple default. | `getPerspectiveTransform`, `findHomography`, `perspectiveTransform` |
| Magnify | Motion magnification for people: the reference is re-sampled by `gain` x the measured dense field (holes filled by normalised convolution), so 0.3 px of creep becomes visible motion. The measurement is the only input; nothing is synthesised. | `blur`, `resize`, `remap` |
| E Forecast | numpy. Velocity from the series; short (3) and long (7) trailing averages; onset of acceleration when the short average exceeds the long one for three epochs with positive acceleration, displacement above the noise floor, the smoothed difference above three robust sigmas of its own jitter, and a significant quadratic term (t above 4) over the trailing fourteen epochs (gates added after the real-data negative control, E4b); a causal jump detector raises single-epoch steps to the agent; weighted linear fit of 1/v against the window-centred time (Fukuzono alpha = 2); residual bootstrap (500 draws) for a 10 to 90 percent window; Theil-Sen and Voight (alpha free in 1.5 to 2.2) fits form the ensemble; the reported window is the union of bootstrap and ensemble spread. Alarm ladder QUIET, MOVING, ACCELERATING, CRITICAL (horizon below threshold with R squared above 0.5). | |

Why these choices. ZNCC is invariant to affine illumination change, which is why sunlight does
not read as motion (E5 lighting scenario: 0.024 px false displacement). The paraboloid peak fit
we started with showed 0.056 px bias at a 0.25 px shift; the Gaussian fit cut it to about
0.02 px and the re-sampling pass to about 0.01 px (E1). An 8-parameter homography fitted on a
narrow stable strip extrapolated badly across the slope (0.3 px errors in the jittered
end-to-end test); model selection on the total camera motion fixed that (0.007 px).

## 5. AWS deployment

Stack `telltale`, us-east-1, created from `infra/cloudformation.yaml` on October 8, 2026.
Worker: c8g.large (Graviton4, 2 vCPU), stock Ubuntu 24.04 arm64 AMI, pinned
`opencv-python-headless==5.0.0.93`, `numpy==2.5.2`, `boto3==1.40.0`, installed by
`infra/worker/bootstrap.sh` from a release tarball in the bucket, run as a systemd service.
No inbound ports; operator access through SSM Session Manager. Bucket blocks public access;
CloudFront reads `public/*` through an origin access control. Raw bursts expire after 30 days.
Worker IAM: this bucket, this queue, the `TellTale` metrics namespace, SSM core.

**Measured**: the demo site (30 epochs of 5-frame bursts, 320 px) went through the real ingest
path; the worker processed each epoch in 0.35 to 0.48 s and the dashboard shows the result with
the runtime proof fields (instance type, architecture, AMI id, cv2 path, build hash).

Cost: c8g.large on-demand is 0.07976 USD per hour (pricing API, October 8, 2026). From E6,
2,094 epochs per hour at 1080p gives 0.038 USD per 1,000 epochs, or about 26,000 nights of
daily monitoring per dollar of compute. The instance, not the epochs, dominates a small
deployment, so the table gives both views:

| Fleet | Epochs per day | Compute per site per month (processing time only) | One always-on c8g.large shared by the fleet, per site per month |
|---|---|---|---|
| 1 site | 1 | 0.001 USD | 58.2 USD |
| 1 site | 6 | 0.007 USD | 58.2 USD |
| 10 sites | 6 | 0.007 USD | 5.8 USD |
| 50 sites | 6 | 0.007 USD | 1.2 USD |
| 50 sites | 24 | 0.027 USD | 1.2 USD |

One c8g.large processes about 50,000 epochs a day, so a district fleet of 50 sites at
24 epochs a day uses under 3 percent of it. S3 (a few MB per site per day, raw bursts expiring
after 30 days), SQS, CloudFront, Lambda and CloudWatch stay in free-tier territory at this
scale. Each agent investigation on Bedrock (Claude Sonnet 4.5, about 25k input and 1.3k output
tokens) costs a few cents and happens only on events, not on every epoch.

## 6. Evaluation

**Headline.** On the public USGS time-lapse of an active coastal bluff, TellTale flagged 2 of 2 documented movement periods the camera could see and raised 0 false acceleration alarms across 147 quiet days in each of three zones; on the controlled sweep it measures displacement to 0.008 px, and on the public SEM DIC Challenge images to 0.005 px.

### E4b negative control on real data (measured)

`python evaluation/e4_forecast_eval.py`. The chained daily series from E4 (three zones,
August 20 2015 to February 9 2016, 147 quiet days each) replayed causally through the same
forecaster the worker runs, scored against the USGS-documented movement windows.

| Onset rule | False acceleration epochs, 3 zones | False CRITICAL epochs | Observable periods flagged (jump detector) |
|---|---|---|---|
| original (SMA above LMA for 3 epochs) | 371 | 10 | 2 of 2 |
| with onset gates (default) | 0 | 0 | 2 of 2 |

The original rule sat in ACCELERATING on most quiet days of a real slope: a chained series is a
random walk whose short average crosses its long average constantly. Two gates fixed it without
touching the synthetic results: the smoothed difference must exceed three robust sigmas of its
own jitter, and the quadratic coefficient of displacement over the trailing fourteen epochs must
be significant (t above 4). Both documented periods the camera could see are two-day steps, not
multi-week accelerations, so the alarm ladder (built for creep) does not fire on them; a causal
jump detector (today's increment against the median plus four robust sigmas of the last twenty)
flags both, at the cost of 10, 12 and 11 quiet-day
jumps per zone out of 147, each of which the supervising agent now investigates (E_JUMP)
rather than paging anyone. The three periods lost to the wet lens are reported as not
observable, not as misses.

### E1 named baselines (measured)

`python evaluation/e1_baselines.py`. Same synthetic pairs, same median-over-frame estimate.

| Method | clean (median / p95 px) | noise 1 %, gain 0.85 | noise 2 %, gain 0.85 | ms per pair |
|---|---|---|---|---|
| telltale | 0.0040 / 0.0077 | 0.0033 / 0.0070 | 0.0032 / 0.0066 | 22.0 |
| farneback | 0.0096 / 0.0129 | 0.0096 / 0.0161 | 0.0088 / 0.0142 | 24.4 |
| pyrlk | 0.0342 / 0.0479 | 0.0393 / 0.0487 | 0.0373 / 0.0467 | 4.6 |
| phasecorr | 0.6687 / 0.8703 | 0.7167 / 0.9169 | 0.6521 / 0.8156 | 2.2 |

### E1 on a public benchmark: SEM 2D DIC Challenge 1.0 (measured)

`python evaluation/e1_dic_challenge.py`. Image sets published by the Society for Experimental
Mechanics DIC Challenge (Reu et al., Experimental Mechanics 58, 2018), 512 x 512 px, rigid
shifts of 0.05 px per image (Samples 1 and 2 at 1.5 and 8 grey levels of noise) and
file-named shifts (Sample 3). Mean absolute error in pixels, each method's sign convention
resolved per set:

| Set | TellTale | Farneback | Pyramidal LK |
|---|---|---|---|
| Sample1 (0.05 px steps, noise 1.5 GL) | 0.0047 | 0.0064 | 0.0112 |
| Sample2 (0.05 px steps, noise 8 GL) | 0.0154 | 0.0206 | 0.0121 |
| Sample3 (FFT shifts, noise 2 GL) | 0.0102 | 0.0031 | 0.0045 |

Read it straight: on the low-noise set TellTale's estimator is the best of the three; on the
noisy set pyramidal LK is 0.003 px better and on the FFT-shifted set Farneback is 0.007 px
better. At this noise level the three estimators are within hundredths of a pixel of each other
and of the imposed shifts. The project's advantage is not a magic estimator; it is the
per-subset quality control, the stabilizer, the forecasting physics and the human control
built around a sound one, measured on real imagery.

### E1 sub-pixel accuracy (measured)

`python -m telltale e1`. 256 px synthetic speckle, exact shifts of 0.125 to 2.0 px via 8x
supersampling, Gaussian noise 0 to 2 percent, illumination gain 1.0 and 0.85, 3 trials per
cell, 294 subsets per cell.

| Condition | Bias (px) | Sigma (px) | MAE (px) | p95 abs (px) |
|---|---|---|---|---|
| noise 0, gain 1.0, all shifts | -0.0010 to 0.0021 | 0.0078 to 0.0101 | 0.0062 to 0.0088 | 0.015 to 0.018 |
| noise 1 %, gain 0.85 | -0.0012 to 0.0006 | 0.0094 to 0.0109 | 0.0078 to 0.0092 | 0.018 to 0.020 |
| noise 2 %, gain 0.85 | -0.0018 to 0.0018 | 0.0111 to 0.0129 | 0.0092 to 0.0104 | 0.022 to 0.025 |

Gate G1 (MAE at 0.25 px below 0.05 px): pass, 0.0084 px. At a typical phone-camera scale of
1 to 2 mm per pixel at 100 m, this is 0.01 to 0.02 mm of measurement noise per subset; the
practical floor in the field will be set by atmosphere and texture, not by the estimator.

### E3 synthetic collapse, end to end (measured)

Voight creep (alpha = 2, true failure at t = 50) rendered as frames, with 1 px random camera
jitter per epoch, run through stack, stabilize, DIC and forecast. 36 epochs to t = 47.

| Quantity | Value |
|---|---|
| Measurement MAE against rendered truth | 0.007 px (max 0.014 px) |
| Onset of acceleration declared | t = 4.9 |
| Final forecast | 50.33, window [49.92, 52.36], R squared 0.992, state CRITICAL |
| Same scene through the cloud path (5-frame bursts, 320 px) | 50.26, window [48.9, 61.9], R squared 0.98 |

### E4c the real landslide inside the product (measured)

`python evaluation/e4_product_run.py`. The 278 noon frames of the USGS Mukilteo record were fed
to the unmodified worker (`process_epoch`) as a chained-reference site with the Claude agent
on Amazon Bedrock enabled, one frame per epoch as a field camera would feed it. The run used
the worker's local storage backend on a laptop (the instrument-health panel says so: the
OpenCV build path and host are recorded for this site too) and the artifacts were published to
the live dashboard as site `mukilteo-usgs`: daily overlays, the replay slider, and every agent
trace. Unusable epochs: BLURRED 105 (the wet-lens period, as designed),
CAMERA_EVENT 13, LOW_INLIERS 1.

The agent investigated 34 events (10 camera events, 24 single-day jumps) with 300 OpenCV
tool calls in about 20 minutes. All 10 camera events were closed as false alarms. Of the 24
jumps, 12 were confirmed as ground motion on identical increments against two references,
direction coherence above 0.8 and clean stabilization; 10 were closed as artefacts; 2 were
inconclusive. On December 9, 2015, the USGS-documented movement day, the verdict was
CONFIRMED after 8 tool calls, with the agent noting that the camera mount had shifted, that
stabilization had corrected it with a 0.02 px residual, and that re-measurement against both
references matched the recorded 0.44 to 0.98 px increments. January 23, 2016 was closed as an
artefact because the chain crosses a camera event on January 22 and re-measurement against the
previous usable day fails stabilization: the right call on the evidence, and a stated limit of
chaining across camera events.

Two findings from this run changed the code. First, the chained reference must advance on every
non-blind epoch, usable or not; the first pass stranded the chain on a stale image after the
first camera event and lost the rest of the record to LOW_INLIERS. Second, the agent's
re-measurement tool must stabilize before correlating on a chained site, as the worker does;
without that it saw camera motion as inflated, reference-dependent displacement and correctly
distrusted it, which turned December 9 into a false alarm. With both fixed, the agent's
judgement on the documented day matched the record.

Eleven confirmed jumps fall on days the USGS record does not list (late August to early
January, 0.1 to 0.6 px). They are confirmed on the same evidence as December 9, so they are
either small undocumented motions of an active slide or a residual limitation of day-to-day
chaining; the record cannot settle it and we do not claim either. What the run did expose is
that confirming motion and paging a person must be separate decisions: the first pass paged
14 times. A materiality rule now applies in both policies (page only in ACCELERATING or
CRITICAL, or for a confirmed step above five times the zone's recent median increment and at
least 0.5 px); small confirmed steps are logged, not paged.

### E5 confounders, thresholds-only arm (measured)

`python evaluation/e5_confounders.py`. 30 epochs each, 5-frame bursts with sub-pixel jitter and
1.5 percent noise, through the full pipeline.

| Scenario | Usable epochs | Rejected (reason) | False alarms | Max false displacement | Outcome |
|---|---|---|---|---|---|
| quiet | 30/30 | none | 0 | 0.026 px | QUIET |
| quiet + camera bump (3 px, 0.4 deg, 0.2 % zoom) | 30/30 | none | 0 | 0.020 px | QUIET; bump fully removed |
| quiet + lighting step to 70 % | 30/30 | none | 0 | 0.024 px | QUIET |
| quiet + fog for 5 epochs | 25/30 | BLIND: 5 | 0 | 0.024 px | QUIET; blindness reported |
| quiet + non-rigid lens distortion | 12/30 | CAMERA_EVENT: 18 | 2 (MOVING) | 0.632 px | partial failure, see section 8 |
| creep + camera bump at epoch 20 | 30/30 | none | 0 | | CRITICAL, 50.29, window [48.8, 70.9] contains truth |

### E5 agent ablation (measured, re-run after the onset gates)

`python evaluation/e5_agent.py --arms off rules llm`. The same six scenarios through the full
worker (`process_epoch`, local store) with the supervising agent off (thresholds only), the
deterministic rule policy, and Claude Sonnet 4.5 on Amazon Bedrock. Pages are counted through a
stand-in for SNS.

| Arm | False pages (5 quiet scenarios) | Events investigated | OpenCV tool calls | Lens-distortion events | First human page in the creep scenario | Lead time before true failure (t = 50) |
|---|---|---|---|---|---|---|
| off (thresholds) | 0 | 0 | 0 | 0 events, all - | t = 47.0 | 3.0 |
| rules | 0 | 10 | 55 | 7 events, all {'FALSE_ALARM'} | t = 8.1 | 41.9 |
| Claude on Bedrock | 0 | 10 | 66 | 7 events, all {'FALSE_ALARM'} | t = 8.1 | 41.9 |

What the agent changed. In the non-rigid lens scenario the stabilizer raised four camera events;
both agent arms re-ran stabilization and DIC and closed all four as FALSE_ALARM without paging
anyone, with the named measurement in the verdict ("1.20 px stabilization scatter, 0.64 px
residual, affine model required"). In the creep scenario both arms confirmed the acceleration at
its onset by re-measuring against two independent references and checking direction coherence,
and paged a person 42 time units before failure, against 3 for the thresholds-only system. The thresholds-only
arm also had zero false pages here, because the synthetic confounders are the ones the stabilizer
and the BLIND / BLURRED logic already catch; the agent's measurable value in this suite is earlier,
evidence-backed escalation and a verdict log for every event. Each Claude investigation used 8 to 9
tool calls, 21k to 31k input tokens, and 30 to 42 seconds.

## 6b. Supervising agent (Agentic Vision path)

Workflow diagram: `docs/agent_workflow.svg`. Code: `agent/tools.py`, `agent/supervisor.py`.

The worker raises an event when a zone's state rises to ACCELERATING or CRITICAL (E_ANOMALY),
when the stabilizer returns CAMERA_EVENT (E_CAMERA), or when the cross-check flags REVIEW or
coverage collapses (E_QUALITY); runs of identical failures raise one event. The agent then runs
a bounded perception-decision-action loop:

- **Perception tools re-run OpenCV 5 on stored images.** `remeasure(t, reference)` runs dense
  DIC again against the previous epoch, the site reference, or any earlier epoch (real creep is
  reference-independent). `check_stabilization(t)` re-estimates the camera model from the
  stacked image and reports stable-ground residual and scatter. `inspect_quality(t)` returns
  sharpness, contrast and subset status counts. `motion_coherence(t)` measures the share of
  subsets moving within 45 degrees of the zone's median direction.
- **Decision.** Claude (Anthropic SDK tool runner over Amazon Bedrock, model
  `us.anthropic.claude-sonnet-4-5`) is prompted as a skeptic with explicit rules for what real
  creep looks like and a budget of ten tool calls. Every tool result determines the next call;
  the trace of calls, arguments and results is written to `public/sites/<site>/agent/<t>.json`.
  A deterministic rule policy drives the same tools as the control arm and the fallback when
  Bedrock is unreachable.
- **Actions.** `set_capture_cadence` writes the camera's control file; `request_human_approval`
  pages the duty contact with an evidence summary and signed approve / dismiss links;
  `close_event` records CONFIRMED, FALSE_ALARM or INCONCLUSIVE. The agent cannot send a public
  alert. If it is inconclusive, errors, or is disabled, the worker's own CRITICAL page still
  fires: a missed page is treated as worse than an extra one.

Operations: a CloudWatch dashboard (`<stack>-ops`) created by the template shows epochs
processed and usable, alarm level, seconds per epoch, coverage and stabilization inliers, queue
depth and age, worker CPU, and the worker log stream; `infra/scripts/teardown.sh` removes
everything including bucket versions. Observability and human control: the dashboard's agent panel lists every event with its verdict,
policy, tool-call count and duration, and expands to the full trace; decisions by the human are
logged with time and source in `decisions.json`. On the live demo site the agent confirmed the
acceleration at t = 8.1 and again at the CRITICAL transition at t = 47, each with nine tool calls,
and the human page carried its evidence summary.

**Second transport: MCP.** `agent/mcp_server.py` exposes the same nine tools (plus `list_sites`)
as a Model Context Protocol server (stdio, `mcp` 2.3), backed by the bucket or by a local
store. The worker's tool runner is the production path and the MCP server is the open one;
each is the other's backup, and neither can send a public alert. `agent/mcp_smoke.py` starts
the server, lists its tools and re-measures the demo's CRITICAL epoch (0.835 px against the
previous epoch, 5.600 px against the reference, coherence 1.0, stabilization OK); `.mcp.json`
registers it for Claude Code in the repository.

### E6 COOL benchmark (baseline measured, COOL pending)

`evaluation/e6_cool_benchmark.py`, 1080p synthetic workload, 7-frame burst, 3,234 subsets,
10 warm repetitions.

| Cell | cv2 path | Threads | Epoch p50 | Stack | Stabilize | DIC | Epochs/hour | USD per 1,000 epochs |
|---|---|---|---|---|---|---|---|---|
| stock OpenCV 5 wheel, c8g.large (Graviton4, 0.07976 USD/h) | /opt/telltale/venv/... | 2 | 1.719 s | 0.474 | 0.687 | 0.560 | 2,094 | 0.038 |
| stock OpenCV 5 wheel, c7i.large (x86, 0.08925 USD/h) | /opt/telltale/venv/... | 2 | 2.732 s | 0.688 | 1.147 | 0.902 | 1,318 | 0.068 |
| COOL, c8g.large | /opt/cool/... | 2 | pending subscription | | | | | |

Same release tarball, same pinned wheel, same synthetic pixels, both with the threaded DIC loop.
Graviton4 is 1.6x faster per epoch than the matched-vCPU x86 instance and 44 percent cheaper per
1,000 epochs at on-demand list prices before COOL is applied. An earlier single-threaded run on
c8g.large measured 2.504 s per epoch; the thread pool over subsets brought the DIC stage from
1.02 s to 0.56 s on two vCPUs.

Op-level microbenchmark on c8g.large (p50, ms): 1,000 x matchTemplate 41-in-81: 152.5;
warpPerspective Lanczos 1080p: 24.1; cornerMinEigenVal: 10.3; GaussianBlur sigma 3: 4.3;
ORB 4,000 features: 64.0; median stack of 7: 72.4. The DIC stage is dominated by
`matchTemplate` and the stabilizer by Lanczos warps and ORB, which are the operation classes
COOL advertises as accelerated.

### E3b large motion: coarse-to-fine DIC against chaining (measured)

`python evaluation/e3_large_motion.py`. A Voight collapse whose final displacement is
28.1 px, beyond a 16 px search radius, rendered with 0.8 px camera jitter and run
through the unmodified worker three times.

| Arm | Epochs measured | Epochs beyond the 16 px search measured | MAE vs truth (px) | Final-epoch error (px) | Forecast failure time (truth 50) | State |
|---|---|---|---|---|---|---|
| fixed, single level | 27/30 | 3/5 | 2.689 | 28.071 | 63.02 | ACCELERATING |
| chained, single level | 30/30 | 5/5 | 0.079 | 0.167 | 49.65 | CRITICAL |
| fixed, coarse-to-fine (3 levels) | 30/30 | 5/5 | 0.007 | 0.002 | 49.78 | CRITICAL |

A single-level fixed search loses the slope once it moves more than its radius (the final
epoch is wrong by the whole displacement and the forecast drifts late). Chaining follows it but
sums daily errors into a random walk. Fixed reference with three pyramid levels
(`cv2.pyrDown`, coarse field infilled by normalised convolution, each finer level searching only
the residual around the upsampled prediction) follows it with 0.08
times the error of chaining, about 12 times better, and forecasts
failure at t = 49.78. Sites whose texture survives weeks should run fixed reference with
`pyramid_levels: 3`; chaining remains the mode for scenes that decorrelate, such as the
vegetated Mukilteo bluff.

### E4 real landslide imagery: USGS Mukilteo bluff (measured)

`python evaluation/e4_mukilteo.py`. Public-domain USGS time-lapse of an active coastal-bluff
landslide at Mukilteo, Washington (ScienceBase 5ef2388382ced62aaae3bbbe, DOI 10.5066/P99QOYL2):
843 frames, three per day, August 20, 2015 to May 25, 2016, camera installed in the landslide
crown looking down the body. USGS documented movement on Dec 8-9 2015, Jan 21-30 2016, Mar 9-14
2016 and two night-time events on Mar 23 and Mar 26 2016.

Method. Burned-in timestamps were read with a small template OCR (`mukilteo_stamps.py`,
796 of 843 frames, the rest filled from neighbours where the frame count matched the capture
slots). The scene decorrelates over months (vegetation, erosion, metres of movement), so the
pipeline ran in chained mode: each noon frame stabilised against the previous noon frame using
the top strip (solar panels and ground above the scarp) as the stable region, then dense DIC
at half resolution (1024 x 678; 1 px here is 2 px in the original), with the timestamp strip
masked out. Daily increments were taken per zone: `left_face` (the landslide body), `right_face`
(bare slope on the right) and `lower_body`.

| Quantity | left_face | right_face | lower_body |
|---|---|---|---|
| Usable daily pairs, Aug 20 to Feb 9 | 159 of 170 | | |
| Median daily increment on quiet days (px) | 0.128 | 0.096 | 0.130 |
| 90th percentile on quiet days (px) | 0.385 | 0.253 | 0.398 |
| Dec 9 2015 (documented movement) | **0.924** | **0.818** | **0.485** |
| Jan 21 and Jan 23 2016 (documented movement) | 0.440, **1.215** | 0.135, 0.096 | 0.164, 0.071 |
| Jan 22, 28, 29, 30 2016 | CAMERA_EVENT | CAMERA_EVENT | CAMERA_EVENT |

On December 9 the landslide body moved at seven times its quiet-day median, above the 90th
percentile of every quiet day in all three zones, and the displacement field shows coherent
downslope vectors across the body (figure `docs/figures/e4_mukilteo_2015-12-09_movement.jpg`;
compare `..._2015-11-20_quiet.jpg`). The January period shows the body moving on Jan 21, 23,
25 and 26 while the stabilizer rejected Jan 22 and 28 to 30 as CAMERA_EVENT: the camera is
mounted in the landslide crown, so when the slide moves the camera's own ground moves, which is
precisely the condition the verdict exists for.

From February 10, 2016 every pair is unusable. The frames' Laplacian-variance sharpness drops
from a median of 0.025 (usable) to 0.0017: the lens is wet or defocused for the rest of the
record, and the camera view has shifted enough that the solar panels leave the frame. The
March movement periods are therefore not measured. This failure is now detected by the
pipeline itself as a BLURRED epoch (added to `stack_burst` as a result of this experiment)
rather than surfacing as a stabilization failure.

Honest reading of the statistics: the daily-increment series is noisy at the 0.1 to 0.4 px
level (shadows, wet and dry soil, wind in vegetation), 15 of 151 quiet days in each zone also
exceed the 90th percentile by construction, and no sub-pixel ground truth exists for this site.
What the data support is that the documented movement days stand out from the quiet baseline
by a factor of four to seven with coherent direction, and that the two failure modes seen
(camera on moving ground, wet lens) are reported as such and never as ground motion.

### E2 physical metrology (harness verified, photographs pending)

`evaluation/e2_target.py` prints a 190 mm random-speckle target with a 100 mm scale bar;
`evaluation/e2_metrology.py` turns bursts before and after known moves into a measured-versus-
true regression per distance and lens. The harness was verified on synthetic captures rendered
from the printed target at 20, 50 and 100 m equivalents (`e2_synthetic_captures.py`): slope
0.997 to 1.002, intercept under 0.02 mm, RMS 0.009 to 0.048 mm (0.02 px). These are synthetic
numbers and are labelled as such; the physical run is scheduled before the rig runs.

### Pending

E2 photographs, E3 tabletop physical collapses (rig design and capture script are ready),
E6 COOL cell.

## 7. User experience

One static page, no framework, light and dark themes, keyboard-reachable controls, a "How it
works" page, a "How to read this" disclosure on every panel, and a site-setup page
(`setup.html`) where an operator loads one reference photo, draws the stable regions and target
zones, sets the scale from two points of known separation, and exports `site.json` without
editing JSON by hand. A replay slider rewinds the
whole instrument to any earlier epoch (overlay, facts, charts and the forecast as it stood then)
and a Play button animates the record; judges can watch the acceleration and the forecast
window appear without waiting for a slope to fail. The first
sentence answers "is this slope okay", then the overlay image, then the series and the
inverse-velocity chart with the forecast intercept and window, then the instrument health
panel (coverage, stabilization inliers and model, epoch time, OpenCV build and worker identity)
and the full epoch log with unusable epochs in red and their reasons. The same page runs
offline from bundled demo data.

The interface was redesigned in October against three published design disciplines and
measured in a real browser at 1440, 768 and 390 px with a layout inspector (font-size count,
text contrast, focal point, empty screens, lopsided sections, small text): 2 failures and 4
warnings before, 0 and 0 after, on the dashboard, the setup page and the about page, live.
Colour is spent only on data and state: a neutral stone ground, one data blue, and status
colours on pills. The failure window is the largest figure on the screen. The camera overlay
uses that single blue, with a lightness ramp for magnitude (a rainbow map invents boundaries
that are not in the ground), and drops arrows below 15% of the peak so noise does not read as
motion. Where a site never builds an inverse-velocity trend (the Mukilteo bluff moves in steps),
the forecast panel shows daily motion with the agent-confirmed steps highlighted instead of an
empty chart. Buttons respond on press, hover effects only run on devices that hover, motion
respects reduced-motion settings, and on phones the navigation becomes a bottom bar.

## 8. Limitations and failure cases

- **Creep-type failures only.** Brittle and liquefaction collapses can fail with little
  surface precursor (Brumadinho 2019). TellTale will not warn of those and says so.
- **Non-rigid camera distortion is only partly caught.** In E5, 18 of 30 distorted epochs were
  rejected as CAMERA_EVENT, but 12 passed the 0.3 px residual and scatter gates with up to
  0.63 px of false displacement and two epochs reached MOVING (not ACCELERATING). A thermal lens
  drift that is smooth across the frame is the realistic version of this. Mitigations we have
  not yet built: tighter scatter gate at the cost of coverage, and the supervising agent's
  re-measurement against alternate references.
- **Night, fog, heavy rain.** Contrast collapse is reported as BLIND and the epoch is skipped;
  the forecast carries the gap as widened uncertainty. Rain often triggers failure, so this is
  a real coverage gap, not a corner case.
- **Vegetation and seasonal decorrelation.** On Mukilteo the scene decorrelated over months,
  which forced chained (day-to-day) measurement; chained integration accumulates random-walk
  error, so long-baseline displacement from this mode is less trustworthy than the daily
  increments. Reference rotation with cross-reference chaining is the designed fix.
- **Wet or defocused lens.** Mukilteo lost its last three and a half months to a wet lens. The
  pipeline now reports BLURRED epochs; a lens hood, heater, or wiper is a field requirement.
- **Camera on moving ground.** A camera mounted inside the landslide (as at Mukilteo) produces
  CAMERA_EVENT verdicts on the days that matter most. The verdict is correct, but the lesson
  for deployment is that the camera must stand on ground that is not part of the slide.
- **Scale.** The estimator's floor (0.01 px on synthetic data) is not the field floor: on real
  imagery the quiet-day daily scatter was 0.1 to 0.4 px at half resolution.
- **Single camera, single reference.** Reference rotation across seasons is designed but not
  implemented; long series will drift as the scene changes.

## 9. Responsible use

Cameras point at ground and structures; there is no person detection or face processing in the
code. The system never sends a public alert on its own: CRITICAL pages the duty contact with
signed approve / dismiss links (tested: a tampered link is rejected with HTTP 403, a valid one
is logged with time and source), and the dashboard shows the decision state. Unusable epochs are always recorded with a reason; the monitor's own liveness is
alarmed (queue age, dead-letter queue) so that a silent monitor cannot pass for a quiet slope.
Raw imagery expires after 30 days; derived series are small and auditable. The report states
every limitation above on the dashboard footer and in the README.

## 10. Reproducibility

Pinned dependencies (`pipeline/requirements.txt`, `infra/worker/requirements.txt`), fixed seeds
in every generator, 21 unit and end-to-end tests, one-command deploy, a bundled offline demo,
and result JSON files in `evaluation/results/` produced by the scripts named in this report.

## References

Fukuzono T. (1985) A new method for predicting the failure time of a slope. Carlà T., Intrieri
E. et al. (2017) Guidelines on the use of the inverse velocity method, Landslides 14:517. Froude
M.J., Petley D.N. (2018) Global fatal landslide occurrence 2004 to 2016, NHESS 18:2161.
Geosciences 13:371 (2023) DIC performance for landslide monitoring. Remote Sensing 13:893 (2021)
Low-cost slope monitoring from time-lapse imagery. Zhu, Zhang, Puzrin (2023) Brumadinho delayed
failure, Commun. Earth Environ. 4. Full bibliography in `RESEARCH.md`.
