# Submission audit against Rules.md (October 8, 2026)

Every line of the final-submission requirements and every rubric criterion, with the current
state, the gap, the risk if left, and the fix. Status: **open**, **in progress**, **closed**.

## A. Hard submission requirements (missing any one is disqualifying or near-disqualifying)

| # | Requirement (Rules.md) | State | Gap and risk | Fix | Status |
|---|---|---|---|---|---|
| A1 | Technical report: problem, users, architecture, OpenCV 5, AWS, evaluation, limitations, responsible use | `docs/REPORT.md`, every number measured, figures embedded, verified by `evaluation/verify_claims.py` | none | - | closed |
| A2 | Judge-accessible repository | Private GitHub repo | Judges cannot see it. Risk: everything | Make public on submission day, or add judge handles when Devpost provides them | open |
| A3 | Pinned dependencies plus build, deploy, test instructions | Pinned; READMEs | No CI proves a clean clone works. Risk: reproducibility 10 % | GitHub Actions: tests on x86 now, arm64 runner when public | closed |
| A4 | Architecture diagram with OpenCV 5, AWS, COOL/agent components | `docs/architecture.svg` | Not visually verified; agent box marked optional | Verify render; update when agent lands | closed (agent box updated; agent_workflow.svg added) |
| A5 | Working web endpoint or live screen-share | CloudFront dashboard live; scale-to-zero worker wakes on demand; judges can start a live run | worker must stay deployed through judging (stack left up until Nov 9) | keep the stack | closed |
| A6 | Video, 5 min max, shows team, app working, architecture, results | Script in `docs/VIDEO.md`, works without the rig | must be recorded by the team | record and upload | open (team) |
| A7 | Evaluation evidence incl. failure cases | E1 to E7: synthetic, public benchmark, real landslide record, confounders, agent ablation, COOL, real failures replayed | physical E2 and E3 not claimed (harness and rig shipped) | - | closed |
| A8 | Both members registered on the Devpost team; project submitted before Oct 26 11:59 PM PT | Unknown | Risk: ineligible | Confirm on Devpost | open |

## B. Things that can cost points or trigger rejection

| # | Issue | Why it matters | Fix | Status |
|---|---|---|---|---|
| B1 | "Millimetre-precision" and "does the radar's job" wording without E2 metrology | Rules reject entries that misrepresent capabilities; Bradski will probe | Reword to measured claims: sub-pixel (0.01 px synthetic, 0.1 to 0.4 px daily scatter on real imagery) | closed |
| B2 | CloudWatch alarms have no actions | "Observability" scored; an alarm nobody receives is decorative | SNS topic with e-mail subscription parameter; alarms publish to it | closed |
| B3 | No human-approval mechanism exists; CRITICAL only says "approval required" | "Appropriate human control" is scored in both the overall and agentic rubrics; the report promises it | Approval Lambda (function URL) writing decisions to the site; SNS message with approve/dismiss links on CRITICAL; dashboard shows decision history | closed |
| B4 | Vegetation mask (Stage D) implemented but not used by the worker | Judges will read the design and find dead code | Worker builds the mask from the trailing epochs and passes it to DIC; record coverage effect | closed |
| B5 | Reference rotation / chained mode exists only in the E4 script | Long series will decorrelate; design says rotation exists | Site option `reference_mode: fixed | chained`; worker chains and integrates | closed |
| B6 | DIC is single-threaded Python loop | Cost-per-epoch and COOL story both improve with parallel matchTemplate | ThreadPool over grid rows (matchTemplate releases the GIL); measure | closed |
| B7 | E6 lacks the COOL cell (x86 done) | COOL award is 30 % "verified COOL" + 20 % measured value; baseline alone is not a comparison | COOL v3 AMI (OpenCV 5.1.0-dev) on the production worker; same-host COOL vs stock, op-level probe, and a COOL-tuned 8-bit search measured. COOL is 5.7 % slower on this workload and reported as such | closed (measured value is honest, not favourable) |
| B8 | Dashboard has no explanations, tour, or landing page | UX 10 %: "usability, accessibility, quality of interaction" | Info popovers on every panel, "how to read this" drawer, landing page with the story and evidence, mobile and light-theme check, keyboard pass | closed except a formal accessibility audit (help disclosures, about page, replay scrubber, setup tool, keyboard-reachable controls) |
| B9 | No agent; agentic award not claimed | 1,000 USD award unaddressed; "when present, judges credit agentic methods within overall criteria" | Bedrock Claude agent with MCP-style tools over the pipeline; bounded loop; traces; E5 agent-on arm | closed |
| B10 | Worker runs as root-installed service with the instance role; no log shipping to CloudWatch Logs | Observability and security hygiene | Ship `/var/log/telltale-worker.log` via CloudWatch agent or structured logs to the `/telltale/worker` group | closed |
| B11 | Bucket has no versioning; a bad worker could overwrite series.json | Reproducibility and auditability | Enable versioning on `public/` prefix objects (bucket-level) | closed |
| B12 | Report cost model uses list price only | Impact and cloud criteria want evidence | Add measured per-epoch cost from E6 and a per-site monthly table at 1, 6, 24 epochs/day | closed |

## C. Rubric-by-rubric: what "exceeding" looks like and what is missing

| Criterion | Weight | Have | Missing for a top score |
|---|---|---|---|
| Technical execution | 30 | Sub-pixel DIC with QC, model-selecting stabilizer, physics forecast, 22 tests, real-data E4 | Vegetation mask in use, reference rotation, parallel DIC, physical E2/E3, CI on arm64 |
| Innovation | 20 | Camera as instrument; physics-informed prediction; honesty mechanisms | Agent that changes its own perception strategy; "nights per dollar" framing in report |
| Real-world impact | 20 | Case narrative; E4 on a real slide; cost per epoch | Deployment guidance from E4 lessons (camera off the slide, lens protection); per-site cost table; a named pilot contact (stretch) |
| User experience | 10 | Clean dashboard, two themes, offline demo | Explanations, tour, landing page, mobile pass, accessibility audit, approval buttons |
| Documentation and presentation | 10 | README, REPORT draft, infra README, diagram | Video; figures in report; PDF export; judge quickstart verified from clean clone |
| Cloud delivery, reproducibility, responsible operation | 10 | CloudFormation, least privilege, no inbound, alarms, pinned deps, offline demo | Alarm actions, approval flow, CI, log shipping, versioning, cost table |
| Best Use of COOL | special | Core workload is classical imgproc; proof fields in every record; stock baseline measured | Subscription, COOL cell, x86 cell, comparison table and figure |
| Agentic Vision | special | Design doc only | Working bounded agent, traces, workflow diagram, agent-on/off evaluation |

## D. Order of work

1. B1 wording, B2 alerting, B3 approval flow, A3 CI (today).
2. B7 x86 cell; B6 parallel DIC; B4 and B5 in the worker.
3. B8 dashboard UX and landing page.
4. B9 agent and E5 agent arm; A4 diagram update.
5. COOL cell when subscribed; rig runs; video; report final; A2 and A8 on submission day.

## E. Added after the audit (beyond the rubric floor)

| Item | Why it scores | Status |
|---|---|---|
| Replay scrubber with per-epoch forecast snapshots | judges see the acceleration and the window appear in 30 seconds | closed |
| Site setup tool (`setup.html`) | real operators can configure a site without JSON; usability | closed |
| Metric scale across an oblique slope (`scale.py`) | correct millimetres anywhere in the frame; geometry depth | closed |
| Motion magnification (`telltale magnify`) | "seeing the invisible" clip for the video; innovation | closed |
| E2 kit: printable target, harness, synthetic self-test | physical metrology becomes a half-day task for an operator | closed; physical photos not claimed |
| CloudWatch ops dashboard, teardown script | cloud delivery and responsible operation | closed |
| Worker and agent tests (32 total) | reliability | closed |
| `docs/JUDGES.md`, `docs/DEPLOYMENT.md`, `docs/PUBLISHED-RECORD.md`, social drafts | documentation, impact | closed |

## F. Winner-pattern audit (October 9, 2026)

| Pattern | Status | Evidence |
|---|---|---|
| 1 Two numbers | closed | controlled 0.008 px; real data 0 false alarms / 2 of 2 periods |
| 2 Cases from outside | closed | USGS Mukilteo (public domain), SEM DIC Challenge 1.0 images |
| 3 Named baseline beaten | closed with caveat | Farneback, pyramidal LK, phase correlation measured on the same pairs and on the public set; TellTale best on two of four tables, within 0.01 px elsewhere, stated plainly |
| 4 Negative control as headline | closed | first sentence of README, report and submission |
| 5 Loop closes into the user's system | closed | capture script polls control.json; decisions log; SNS |
| 6 Depth on one surface | pass | one measurement, built deep |
| 7 Tagline is verbs | closed | README, about page, submission |
| 8 Demo cannot break | pass | static replay, rule-policy fallback, offline clone |
| 9 Practitioner or adoption | closed by published record | `docs/PUBLISHED-RECORD.md`: 30 opened sources mapping each stated need (Sendai 33(b) low-cost equipment, NDMA slope-scale timing gap, ISO 22327 district users, Brienz window plus political decision) to a TellTale feature; states plainly that no practitioner has evaluated TellTale |
| 10 Shipped surface | pass | live URL, setup tool, offline demo |
| 11 Limits as measured properties | closed except E2 photos | every limit has a number; COOL measured; E2 photos still await the user |
| 12 Inspectable and rerunnable | pass | `evaluation/verify_claims.py` checks 10 headline claims and re-runs E1 live; 32 tests, CI, result JSON, traces with evidence images, MCP smoke test |

| Coarse-to-fine DIC (`compute_field_pyramid`) | fixed reference follows 28 px of motion at 0.007 px MAE; removes the random-walk cost of chaining on textured scenes | closed |
| Real landslide inside the product (`mukilteo-usgs` live site, Claude traces) | judges scrub a real slide and read the agent on a documented day | closed |
| MCP server for the agent's OpenCV tools (`agent/mcp_server.py`, `.mcp.json`) | any MCP client can investigate a site; second transport and backup to the worker's tool runner | closed |
| Interface redesign, measured (dashboard, setup, about) | browser inspector at three widths: 2 FAIL / 4 WARN before, 0 / 0 after; single-hue overlay; daily-motion fallback | closed |
| COOL on the live demo site | all 36 demo epochs processed by the COOL worker (OpenCV 5.1.0-dev, /opt/cool), dashboard shows the COOL on Graviton badge and the build in Instrument health | closed |
| Scale to zero, measured | worker stops itself after 20 idle minutes and the wake function restarts it; backlog drained and processed in time order (bug found and fixed on the live stack) | closed |
| Second public landslide record (USGS Barry Arm) | no public time-lapse data release exists (InSAR and maps only); not pursued | closed as not available |

## G. Patterns 13 to 18 (October 23, 2026)

| Pattern | Status | Evidence |
|---|---|---|
| 13 The model's work is visible | pass | each agent investigation shows the displacement fields it re-measured (`evidence_png`, 6 demo and 24 Mukilteo traces backfilled, numbers reproduced to 1.6e-7 px); the overlay and the forecast window are the visible OpenCV work |
| 14 Results in money or time | pass | about 1.40 USD per slope per month (50-slope district) or 10.50 USD (one slope); a page 41.9 time units before failure against 3.0 for thresholds; a window, not a date |
| 15 The partner triggers the system | pass | S3 events queue epochs, an EventBridge schedule wakes the worker, SNS pages a person, a Lambda URL writes the human decision back into the dashboard, the agent writes the camera's capture cadence |
| 16 Read the rubric weighting | pass | technical execution 30, innovation 20, impact 20, UX 10, documentation 10; rigour scores here, so the submission leads with the measured numbers and the verifier |
| 17 Gallery shows the product | pass | `docs/gallery/` 01 to 04 are the product: forecast and approve button, the real landslide, the agent's evidence, the real record in the dashboard; architecture is last |
| 18 Open with a known failure | pass | submission and video open on Bingham Canyon 2013 against Wayanad 2024, both sourced in `docs/PUBLISHED-RECORD.md` |
| 8 Demo cannot break, and runs live (re-checked) | pass | judges can start a real run from the dashboard (rate-limited Lambda, three staged variants); the static demo sites stay as they were |
| 9 Practitioner (re-checked) | partial, cannot close | the team cannot contact practitioners; `docs/PUBLISHED-RECORD.md` maps each published need to a feature and says plainly that no practitioner has evaluated TellTale |
