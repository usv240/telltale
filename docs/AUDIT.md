# Submission audit against Rules.md (October 8, 2026)

Every line of the final-submission requirements and every rubric criterion, with the current
state, the gap, the risk if left, and the fix. Status: **open**, **in progress**, **closed**.

## A. Hard submission requirements (missing any one is disqualifying or near-disqualifying)

| # | Requirement (Rules.md) | State | Gap and risk | Fix | Status |
|---|---|---|---|---|---|
| A1 | Technical report: problem, users, architecture, OpenCV 5, AWS, evaluation, limitations, responsible use | `docs/REPORT.md` draft with measured numbers | Draft; no figures embedded; E2/E3-physical/E6-COOL pending. Risk: documentation 10 % | Finish after E6 and rig; embed figures; export PDF | in progress |
| A2 | Judge-accessible repository | Private GitHub repo | Judges cannot see it. Risk: everything | Make public on submission day, or add judge handles when Devpost provides them | open |
| A3 | Pinned dependencies plus build, deploy, test instructions | Pinned; READMEs | No CI proves a clean clone works. Risk: reproducibility 10 % | GitHub Actions: tests on x86 now, arm64 runner when public | closed |
| A4 | Architecture diagram with OpenCV 5, AWS, COOL/agent components | `docs/architecture.svg` | Not visually verified; agent box marked optional | Verify render; update when agent lands | closed (agent box updated; agent_workflow.svg added) |
| A5 | Working web endpoint or live screen-share | CloudFront dashboard live | Worker stopped between sessions; must run Oct 27 to Nov 9. Risk: judges see stale data | Start worker before submission; schedule nothing that stops it | open |
| A6 | Video, 5 min max, shows team, app working, architecture, results | Shot list only | Needs rig footage and both members on camera. Risk: documentation 10 % and overall impression | Film after rig run | open |
| A7 | Evaluation evidence incl. failure cases | E1, E3-synthetic, E4, E5, E6-baseline | E2 and physical E3 pending. Failure cases documented | Rig runs; E2 if time | in progress |
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
| B7 | E6 lacks the COOL cell (x86 done) | COOL award is 30 % "verified COOL" + 20 % measured value; baseline alone is not a comparison | c7i.large one-off run now; COOL after subscription | in progress |
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
| E2 kit: printable target, harness, synthetic self-test | physical metrology becomes a half-day task | closed, photos pending |
| CloudWatch ops dashboard, teardown script | cloud delivery and responsible operation | closed |
| Worker and agent tests (29 total) | reliability | closed |
| `docs/JUDGES.md`, `docs/DEPLOYMENT.md`, outreach and social drafts | documentation, impact | closed |
