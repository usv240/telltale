# Devpost submission text

Paste each section into the matching Devpost field. Numbers are checked by
`python evaluation/verify_claims.py`; sources for every outside fact are in
`docs/PUBLISHED-RECORD.md`.

## Tagline (Devpost, one line)

Stacks bursts from any fixed camera, removes the camera's own motion, measures ground creep to a hundredth of a pixel, forecasts the failure window, re-measures to verify it, and pages a person.

## About the project

### Inspiration

In April 2013 the Bingham Canyon copper mine knew from its monitoring when its pit wall would
fail. The area was evacuated beforehand, about 65 million cubic metres came down, and no one was
hurt. In July 2024 nobody was measuring the hillsides above Wayanad in Kerala, and about 290 to
400 people died. The difference was not the physics. Slopes that creep before they fail give
days to weeks of warning, and the mines read that warning with instruments most communities
cannot afford: half of the people who lived through a landslide in the last five years got no
warning at all (World Risk Poll 2023). The UN's Sendai Framework asks for "simple and low-cost
early warning equipment". We wanted the mine's warning on a camera a village can buy.

### What it does

On the public USGS time-lapse of an active coastal bluff, TellTale flagged 2 of 2 documented
movement periods the camera could see and raised 0 false acceleration alarms across 147 quiet
days in each of three zones; on the public SEM DIC Challenge images it measures displacement to
0.005 px, ahead of OpenCV's Farneback and pyramidal Lucas-Kanade.

A fixed camera photographs the slope in short bursts. TellTale stacks each burst, removes the
camera's own motion using ground the operator marked as stable, measures surface movement at
about 3,000 points with sub-pixel image correlation, and when the movement accelerates it
forecasts a failure window with the inverse-velocity method mines use. A supervising agent,
Claude on Amazon Bedrock, then re-runs OpenCV on the stored images to check the warning is real
before anyone is woken: it re-measures against a different reference, checks that the motion is
coherent, and checks the camera did not move. Only then does it page the duty officer, once per
episode, with
the evidence images and signed approve and dismiss links. Nothing reaches the public without a
person.

What that buys, in the units a district office pays in:

- **14 times earlier warning.** On a simulated collapse, the agent's verified page reached a
  person 41.9 time units before failure; thresholds alone paged 3.0 before. Zero false pages
  in five quiet scenarios, in every arm.
- **About 1.40 USD per slope per month** for a district of 50 slopes sharing one Graviton
  worker, or about 10.50 USD for a single slope with the worker sleeping between photos. A
  single chain inclinometer starts at about 5,000 EUR before drilling and watches one borehole.
- **A forecast window, not a date.** At Brienz in 2023 the evacuation letter gave "between May
  15 and June 1"; TellTale's demo, a simulated collapse on a real USGS photograph, publishes days
  49.2 to 51.0 for a failure on day 50.

### What is new

Camera image correlation for landslides and the inverse-velocity forecast are both published,
and both are sold as expert services. TellTale joins them into one unattended loop that an
office without a geotechnical team can run. It adds three things the prior work leaves open:

- **Onset gates.** They took real-data false alarms from 371 to 0.
- **Measured camera failures.** CAMERA_EVENT, BLIND and BLURRED are reported, never shown as
  "no movement".
- **An agent that must re-measure before it may page anyone,** at most once per episode.

Report section 1b has the comparison table.

### The forecast on real failures

We replayed the unchanged forecaster on six real slope failures with open monitoring records:
Preonzo 2012, Arvigo 2007, Vajont 1963, Hogarth 1975 and Veslemannen 2019.

- It reached CRITICAL before every one.
- At the four sites with a forecast at the end, the median landed within two days of the
  collapse at three.
- It also raised twelve early CRITICAL spells on accelerations that settled. That is why
  TellTale publishes a window, the agent re-measures, and a person decides.

### How we built it

OpenCV 5, classical vision only, no neural network:

- **Stack:** `phaseCorrelate` plus ZNCC `matchTemplate` register each burst; a median stack
  removes shimmer. Dark, foggy or blurred bursts are reported as BLIND or BLURRED, never as
  "no movement".
- **Stabilize:** ORB with `findHomography(USAC_MAGSAC)` on the stable ground gives a coarse camera
  model, dense correlation refines it, and the simplest model that explains the stable ground
  wins. If stable ground still appears to move, the epoch is a CAMERA_EVENT and no displacement
  is recorded.
- **Measure:** ZNCC `matchTemplate` on 41 px subsets, a Gaussian sub-pixel peak fit, one Lanczos
  re-sampling pass, per-subset quality codes, a phase-correlation cross-check, and a
  coarse-to-fine pyramid that follows 28 px of motion at 0.007 px.
- **Forecast:** inverse velocity (Fukuzono 1985; Carlà et al. 2017) with a bootstrap window and a
  three-method ensemble, behind onset gates added after the real-data negative control.

On AWS, from one CloudFormation template: S3 ingest, an SQS queue with a dead-letter queue, a
Graviton4 c8g.large worker running COOL (Cloud Optimized OpenCV, OpenCV 5.1.0) from the AWS
Marketplace, CloudFront for the dashboard, SNS plus a Lambda approval link, CloudWatch alarms and
an ops dashboard. The worker stops itself after 20 idle minutes and a scheduled Lambda wakes it
when photos arrive. The agent's nine OpenCV tools are also an MCP server, so any MCP client can
investigate a site.

### Challenges we ran into

- **Our own false alarms on real data.** The first forecast raised 371 false acceleration
  alarms on the quiet days of the USGS record. Two statistical onset gates brought that to 0
  without losing either documented movement period.
- **Pixel locking.** The first sub-pixel estimator had a 0.06 px bias. A Gaussian peak fit plus
  one re-sampling pass brought it to 0.01 px.
- **Bugs found on the live stack.** The agent once closed a real acceleration as a false alarm,
  because the model rounded an epoch time and "the previous epoch" became the epoch itself.
  Separately, a backlog of photos came off the queue in random order. Both are fixed and have
  regression tests, and the write-ups are in the report.
- **COOL did not speed this workload up.** On the same instance COOL is 5.7 to 6.6 percent
  slower per epoch: it is 1.45x faster on ORB and 1.52x on corner response, but slower on the
  float32 Lanczos warps that dominate our time. We report it as measured.

### Accomplishments that we're proud of

A judge can press one button and watch a slope collapse go through the real system: the queue,
the self-waking COOL worker on Graviton and the Claude agent, live, in about four minutes.
Two numbers from data we did not make (the USGS record and the SEM DIC Challenge). A negative
control as the headline. A named baseline beaten (Farneback, pyramidal LK, phase correlation). An
agent whose visual evidence is on screen: each investigation shows the displacement fields it
re-measured. And `python evaluation/verify_claims.py`, which checks every number on this page
and re-runs the accuracy sweep in about 20 seconds.

### What we learned

The refusals are the product. The CAMERA_EVENT verdict, the BLIND flag, the window instead of a
date, and an agent that must re-measure before it may page anyone matter more to a duty officer
than another decimal of accuracy.

### What's next

Reference rotation across seasons for vegetated slopes, a physical calibration at range with the
printed target we ship, stereo cameras for 3D motion, and a field pilot through a district
disaster-management office.

## Built with

OpenCV 5, COOL (Cloud Optimized OpenCV for AWS Graviton), Python, NumPy, Amazon EC2 Graviton4,
Amazon S3, Amazon SQS, Amazon CloudFront, AWS Lambda, Amazon SNS, Amazon CloudWatch, AWS Systems
Manager, AWS CloudFormation, Amazon Bedrock, Claude, Anthropic SDK, Model Context Protocol.

## Try it out

- **Run it live:** https://d30le2uwgaimao.cloudfront.net/?site=live-demo, then press "Start a new
  collapse on AWS" and watch S3, the COOL worker and the Claude agent process it in about four minutes
- Live dashboard: https://d30le2uwgaimao.cloudfront.net/
- How it works: https://d30le2uwgaimao.cloudfront.net/about.html
- Code, report and one-command verification: https://github.com/usv240/telltale

## Gallery (upload in this order; the first four show the product)

The images are in `docs/gallery/`, 1600 x 1000 px.

1. `01-forecast.png`: the live dashboard at CRITICAL. One sentence says when the slope will
   fail and that a person decides, with the approve button.
2. `02-real-landslide.png`: the USGS Mukilteo bluff on 9 December 2015, with the ground
   TellTale measured moving shown in blue.
3. `03-agent-evidence.png`: an agent investigation, with the two displacement fields it
   re-measured and its verdict.
4. `04-mukilteo-dashboard.png`: the real landslide record in the product, showing daily
   motion and the steps the agent confirmed.
5. `05-setup.png`: site setup, where an operator marks the stable ground and the zones.
6. `06-architecture.png`: the architecture diagram.
