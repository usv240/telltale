## Inspiration

In April 2013 the Bingham Canyon copper mine in Utah knew its pit wall was about to fail. Its monitoring saw the slope creep and speed up, the pit was cleared, about 65 million cubic metres came down, and **no one was hurt** ([Pankow et al. 2014](https://doi.org/10.1130/GSATG191A.1)).

In July 2024 nobody was measuring the hills above Wayanad in Kerala, India. **About 290 to 400 people died** ([Petley 2024, Eos](https://eos.org/thelandslideblog/wayanad-landslides)).

The physics was the same. Many slopes creep for days or weeks before they fail, and that warning can be read. Mines read it with radar and survey instruments that cost far more than a village can pay. Worldwide, **half of the people hit by a landslide in the last five years got no warning at all** ([World Risk Poll 2023, in UNDRR and WMO 2024](https://www.mhewc.org/wp-content/uploads/2025/12/Global-Status-of-EWS-2024-_opt.pdf)). The UN's Sendai Framework asks for exactly the missing piece: *"simple and low-cost early warning equipment"* ([UN 2015](https://documents.un.org/doc/undoc/gen/n15/167/16/pdf/n1516716.pdf)).

So we asked: **can an ordinary camera give a village the warning a mine gets?**

## What it does

TellTale turns any fixed camera pointed at a slope into a landslide early-warning instrument. It works in four steps:

1. **Watch.** The camera takes a short burst of photos a few times a day. The photos go to Amazon S3.
2. **Measure.** OpenCV 5 measures how far the ground moved at about 3,000 points, to a hundredth of a pixel. It first removes the camera's own shake using ground the operator marked as stable.
3. **Forecast.** When the movement speeds up, TellTale uses the inverse-velocity method that mines use (Fukuzono 1985; Carlà et al. 2017) to give a **failure window**, such as "between day 49.2 and day 51.0", not a single date.
4. **Check, then ask a person.** Before anyone is woken, an AI agent (Claude on Amazon Bedrock) re-runs OpenCV on the stored photos to make sure the warning is real. Only then does it page the duty officer, once, with the evidence images. **Nothing reaches the public unless a person presses Approve.**

**Features**

- **Live dashboard:** one sentence tells the duty officer what is happening, with the forecast window, a displacement chart, the camera view with the moving ground in blue, and the Approve and Dismiss buttons.
- **An agent that has to show its evidence:** every investigation shows the displacement fields it re-measured, its verdict, and the full trace of tool calls.
- **Honest about what it can't see:** a moved camera, darkness, fog or a wet lens is reported as CAMERA_EVENT, BLIND or BLURRED, never as "no movement".
- **One-photo setup:** an operator marks the stable ground and the slope to watch on a single photo.
- **Run it yourself:** one button on the live site starts a real collapse on AWS. You can watch it travel through the queue, the Graviton worker and the agent in about four minutes.
- **MCP server:** the agent's nine OpenCV tools are also published as an MCP server, so any MCP client can investigate a site.

## Results

We tested on data we did not make wherever we could.

| Test | Data | Result |
|---|---|---|
| Real landslide, quiet days | USGS time-lapse of the Mukilteo bluff, Washington ([Smith et al. 2020](https://doi.org/10.5066/P99QOYL2)) | **0 false alarms in 147 quiet days**, and both movement periods the camera could see were flagged |
| Real slopes that failed | Six published monitoring records: Preonzo 2012 (two instrument sets), Arvigo 2007, Vajont 1963, Hogarth 1975, Veslemannen 2019 ([Leinauer et al. 2023](https://doi.org/10.14459/2023mp1688868), CC BY) | **Reached CRITICAL before all 6.** It also raised 12 early alarms that settled, which is why a person always decides |
| Measurement accuracy | Public SEM DIC Challenge images | **0.005 px error**, better than OpenCV's Farneback and Lucas-Kanade |
| Agent against thresholds alone | Simulated collapse with camera problems mixed in | The agent paged a person **41.9 time units before failure** (thresholds alone: 3.0), with **0 false pages** |
| Cost | AWS, 50 slopes sharing one worker | **About $1.40 per slope per month**. A single borehole sensor starts at about €5,000 and watches one point ([Gamperl et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8068166/)) |

## How we built it

**OpenCV 5, classical vision, no neural network:**

- **Stacking:** `phaseCorrelate` and `matchTemplate` line up each burst, and a median stack removes heat shimmer.
- **Removing camera shake:** ORB features with `findHomography` (USAC_MAGSAC), refined by dense correlation. If the "stable" ground still appears to move, the camera itself moved and no movement is recorded.
- **Measuring movement:** sub-pixel image correlation (ZNCC `matchTemplate`, a Gaussian peak fit and a Lanczos re-sampling pass), with a coarse-to-fine pyramid for large motion.
- **Forecasting:** inverse velocity with a bootstrap window and onset gates.

**On AWS, from one CloudFormation template:**

- S3 for photos.
- An SQS queue, with a dead-letter queue.
- A Graviton4 (c8g.large) worker running **COOL**, the Cloud Optimized OpenCV from AWS Marketplace.
- Claude on Amazon Bedrock as the agent.
- SNS and a Lambda approval link, with the link secret in Secrets Manager.
- CloudFront for the dashboard, and CloudWatch alarms with an ops dashboard.
- The worker **switches itself off** after 20 idle minutes, and a small scheduled Lambda wakes it when photos arrive.

![Architecture](https://raw.githubusercontent.com/usv240/telltale/master/docs/gallery/06-architecture.png)

## Challenges we ran into

- **Our own false alarms.** On the real USGS record, our first forecast raised 371 false alarms on quiet days. Two statistical "onset gates" brought that to 0 without missing either real movement period.
- **A real bug that the agent's trace exposed.** The agent once closed a real acceleration as a false alarm: it rounded a time, so "the previous photo" became the same photo. We found it because every agent decision is logged with its evidence, and we fixed it.
- **COOL did not speed up our workload.** On the same Graviton machine, COOL was 1.45× faster at feature detection but about 6% slower per photo overall, because our heaviest step is an image warp it doesn't speed up. We report that as measured. Moving from x86 to Graviton did pay off: about 1.6× faster and over 40% cheaper.

## Accomplishments that we're proud of

- A judge can press one button and watch a slope collapse go through the real cloud system live.
- Our headline results come from data we didn't make: a real USGS landslide, six real failures and a public benchmark.
- The agent doesn't just explain: what it sees in the images decides whether a person is paged at all.
- Every number above can be re-checked with one command in the repository.

## What we learned

**What TellTale refuses to claim matters as much as what it measures.** It reports a window instead of a date, says "the camera moved" instead of "no movement", and won't page anyone until it has measured again. A duty officer needs that more than another decimal of accuracy.

## Limits and responsible use

- It can't warn of **sudden, brittle collapses** that don't creep first.
- It can't see at night, in fog or through a wet lens, and it says so.
- It is an aid to a trained person, **not an automatic public alarm**. Only a person can send an alert.
- It hasn't been calibrated in the field yet. Results are in pixels and on the public records above.
- The cameras point at ground, not people. All data we use is public or openly licensed.

## What's next for TellTale

- A field pilot with a district disaster-management office.
- Physical calibration at range with the printed target we ship.
- Stereo cameras for 3D motion.
- Handling vegetation that changes with the seasons.
