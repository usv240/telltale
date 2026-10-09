# Devpost submission text (draft)

## Tagline

TellTale stacks bursts from any fixed camera, removes the camera's own motion, measures ground creep to a hundredth of a pixel, forecasts the failure window, re-measures to verify it, and pages a person.

## First line

On the public USGS time-lapse of an active coastal bluff, TellTale flagged 2 of 2 documented movement periods the camera could see and raised 0 false acceleration alarms across 147 quiet days in each of three zones; on the controlled sweep it measures displacement to 0.008 px, and on the public SEM DIC Challenge images to 0.005 px.

## Inspiration

Creep-type landslides give warning for days or weeks: the surface moves millimetres a day and
accelerates. Mines read that warning with radar costing 100k to 500k USD per site and evacuate
in time. The communities where most landslide deaths happen cannot afford an instrument. We
wanted the physics the mines use, on a camera a village can buy.

## What it does

TellTale turns a fixed camera into a slope-stability instrument. It stacks bursts of photos to
suppress atmospheric shimmer, removes camera motion using stable ground, measures sub-pixel
surface displacement with digital image correlation, and when the motion accelerates it
forecasts a failure window with the inverse-velocity method. A duty officer sees one sentence
on a dashboard. Nothing alerts the public without a person approving.

## How we built it

Pure OpenCV 5 classical vision, no neural network: phaseCorrelate and ZNCC for burst
registration, ORB plus USAC_MAGSAC refined by dense DIC for stabilization with camera-model
selection, matchTemplate ZNCC with a Gaussian sub-pixel fit and a re-sampling refinement pass
for measurement, and numpy for the Carlà et al. 2017 forecasting protocol with bootstrap and
ensemble uncertainty. On AWS: S3 ingest, SQS with a dead-letter queue, one Graviton c8g worker
running the same package as the laptop, CloudFront serving a static dashboard, CloudWatch
metrics and liveness alarms, all from one CloudFormation template.

## Challenges

The first sub-pixel estimator had a 0.06 px pixel-locking bias; a Gaussian fit plus one
re-sampling pass brought it to 0.01 px. A homography fitted on a narrow stable strip
extrapolated 0.3 px errors across the slope; selecting the simplest camera model that explains
the stable ground fixed it. Phase correlation on small patches was too imprecise to act as a
cross-check, so it became a gross-error detector instead.

## Accomplishments

Mean absolute error of 0.008 px on the synthetic sweep. A simulated collapse forecast to within
0.3 time units of truth under 1 px camera jitter, through the real cloud path. Zero false
alarms under camera bumps, lighting steps and fog. 1,438 epochs per hour on a c8g.large, which
is about 18,000 nights of monitoring per dollar.

## What we learned

Honesty mechanisms are the product. The stabilizer's CAMERA_EVENT verdict, the BLIND flag, and
the always-a-window-never-a-timestamp forecast matter more to a duty officer than another
decimal of accuracy.

## What's next

Reference rotation across seasons, the supervising agent that investigates anomalies before a
human sees them, multi-camera stereo for 3D displacement, and a field pilot with a district
disaster-management office.

## Built with

OpenCV 5, Python, NumPy, AWS CloudFormation, EC2 Graviton (c8g), S3, SQS, CloudFront,
CloudWatch, Systems Manager, COOL (Cloud Optimized OpenCV Library).
