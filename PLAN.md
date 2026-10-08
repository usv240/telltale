# TellTale: Master Plan
Team Ground Truth. OpenCV AI Competition 2026, powered by AWS.
Plan date: September 2, 2026. Submission deadline: October 26, 2026, 11:59 PM PT.

TellTale turns any fixed camera into a millimeter-precision instrument that measures slope creep
and forecasts the time of ground failure, using classical OpenCV 5 computer vision, established
geotechnical physics, and AWS. This document is the master plan. Each component folder contains
its own DESIGN.md with full technical detail.

---

## 1. What we are building (one paragraph)

A camera photographs a slope in short bursts, several times a day. The pipeline stacks each burst
to suppress atmospheric shimmer, removes camera motion using stable-region homography, and
measures sub-pixel surface displacement with digital image correlation. Displacement becomes
velocity; when velocity accelerates, the inverse-velocity method produces a failure-time window
with uncertainty bounds. A supervising agent investigates every anomaly before an alarm is
allowed out, and a human approves or dismisses the final alert. Everything runs on AWS with the
core vision workload on COOL (Cloud Optimized OpenCV) on Graviton. A public dashboard and an
educational landing site make the whole system understandable to a first-time visitor in minutes.

## 2. Repository map

| Folder | Sub-project | Design doc |
|---|---|---|
| `pipeline/` | Core CV and physics: stacking, stabilization, DIC, masking, forecasting, synthetic evaluation | `pipeline/DESIGN.md` |
| `agent/` | Supervising agent: MCP tool server, investigation policy, evidence packets, approval gate | `agent/DESIGN.md` |
| `infra/` | AWS deployment: IaC, ingest, queueing, workers on COOL/Graviton, storage, alerting, observability | `infra/DESIGN.md` |
| `web/` | Landing site (education) and dashboard (live instrument view) | `web/DESIGN.md` |
| `evaluation/` | E1-E6 evaluation harness, datasets, results, figures | `evaluation/DESIGN.md` |
| `demo-rig/` | Tabletop slope-failure rig: build instructions, capture scripts, run protocol | `demo-rig/DESIGN.md` |

Root files: `PLAN.md` (this file), `README.md` (judge-facing quickstart), `RESEARCH.md` at the
repository parent (full research dossier and bibliography).

## 3. How this plan wins each judging criterion

Rubric weights from Rules.md, with the concrete artifact that earns each score.

### Technical execution (30 percent)
- Depth: sub-pixel DIC with quality control, USAC/MAGSAC stabilization, burst stacking,
  texture and vegetation masking, and a published forecasting protocol (Carla et al. 2017)
  implemented faithfully, with an ensemble and bootstrap uncertainty.
- Correctness: unit tests for every module; E1 synthetic accuracy with bias and sigma curves;
  E2 physical metrology with a known-displacement rig; error bars propagated end to end.
- Reliability: deterministic pipeline, pinned dependencies, idempotent epoch processing,
  graceful degradation when frames are unusable (the system says "blind", never silence).

### Innovation (20 percent)
- The reframe: cameras as measuring instruments, not classifiers. Physics-informed video
  prediction, which is on the organizers' suggested-areas list and which almost nobody attempts.
- The agent as a skeptic whose measurable output is a lower false-alarm rate, not a chatbot.

### Real-world impact (20 percent)
- The Bingham/Brienz/Wayanad narrative with citations; cost comparison against radar and InSAR;
  a deployment cost model per site; honest statement of who benefits and what is out of scope.

### User experience (10 percent)
- Landing site a first-time visitor understands end to end: plain language, light and dark mode,
  mobile and desktop layouts, info buttons on every non-obvious term or control, a glossary,
  references, and a guided tour of the dashboard.
- Dashboard: one screen answers "is this slope okay", with drill-down for experts.

### Documentation and presentation (10 percent)
- Technical report generated from the design docs plus measured results; architecture diagrams;
  reproducible build and test instructions; a 5-minute video with a live predicted collapse.

### Cloud delivery, reproducibility, responsible operation (10 percent)
- One-command IaC deploy; CloudWatch metrics, logs, and alarms; least-privilege IAM; cost model;
  privacy by design (cameras point at ground, no person detection anywhere); responsible-use
  section covering alert governance and failure modes.

### Best Use of COOL award
- The DIC core runs on the COOL v3.1 AMI on Graviton4 c8g. Benchmark harness compares stock
  OpenCV 5 wheel vs COOL on the same instance and against x86 c7i: epochs per hour, cost per
  1,000 epochs, nights of monitoring per dollar. `cv2.__file__` logged in every job as proof.

### Agentic Vision award
- A perception-decision-action loop in which DIC output changes the agent's next tool call.
  Full decision traces, injected-confounder evaluation with agent on and off, and a human
  approval gate. Workflow diagram plus trace exports for judges.

## 4. Milestones and calendar

Week numbering starts Tuesday, September 2, 2026.

| Week | Dates | Milestone | Definition of done |
|---|---|---|---|
| 1 | Sep 2 - Sep 8 | Core pipeline works end to end on synthetic data | E1 accuracy table produced; simulated collapse forecast within 15 percent of true failure time; unit tests green |
| 2 | Sep 9 - Sep 15 | Real data and spikes | Mukilteo time-lapse processed (Spike A); backyard metrology first pass (Spike B); COOL instance boot and microbenchmark (Spike C); landing site v1 live locally |
| 3 | Sep 16 - Sep 22 | Cloud path | Ingest to S3, queue, containerized worker on Graviton, series store, forecast Lambda; dashboard v1 reading real artifacts |
| 4 | Sep 23 - Sep 29 | Agent and rig | MCP tool server plus Bedrock agent with investigation policy; tabletop rig built; first instrumented collapse (E3 run 1); grant check-in prep (check-ins run Sep 21 - Oct 2) |
| 5 | Sep 30 - Oct 6 | Evidence | E3 runs 2-5; E2 rig finalized with error budget; E5 agent ablation; E6 COOL benchmark complete |
| 6 | Oct 7 - Oct 13 | Hardening | Observability, security review, cost report, failure-case documentation, Slumgullion or Brienz stretch analysis |
| 7 | Oct 14 - Oct 20 | Story | Technical report, architecture diagrams, landing site final content with measured results, video shot and edited |
| 8 | Oct 21 - Oct 26 | Buffer and ship | Endpoint live, repo cleaned, pinned deps verified from clean clone, submission package uploaded |

Standing rule: every week ends with the demo path re-run from scratch. If the demo breaks, fixing
it outranks new features.

## 5. Risk gates (from RESEARCH.md, operationalized)

| Gate | Test | If it fails |
|---|---|---|
| G1 (Wk 1) | E1 synthetic: mean absolute error at 0.25 px shift below 0.05 px | Switch subset size and refinement method; escalate to phase-correlation-primary design |
| G2 (Wk 2) | Mukilteo: coherent displacement on at least half of slope-face subsets | Fall back to corner-feature tracking on strong-texture patches; reduce claimed coverage honestly |
| G3 (Wk 2) | Backyard: 1 mm move at 50 m measured within 30 percent | Increase focal length guidance; revise precision claims on landing site |
| G4 (Wk 2) | COOL AMI boots, `/opt/cool` env imports, speedup measured | Use COOL container path; if unavailable, document and pivot COOL claim to hybrid |
| G5 (Wk 4) | Tabletop collapse: inverse-velocity trend visible before failure | Adjust soil mix and wetting rate; slow the failure; consult E3 protocol alternatives in demo-rig/DESIGN.md |

## 6. Division of work

- Ujwal: pipeline, agent, infra, dashboard integration, COOL benchmark.
- Arpita: evaluation harness and runs (E1-E6), demo rig builds and captures, landing site
  content and UX review, report figures.
- Shared: weekly demo run, video, report writing.

## 7. Out of scope (stated to protect the schedule)

- No person detection, face processing, or people analytics of any kind.
- No mobile app; the dashboard is a responsive web app.
- No multi-camera stereo in the core deliverable (documented as future work; the geometry
  design leaves room for it).
- No claim of predicting brittle liquefaction failures; documented as a limitation with the
  Brumadinho citation.

## 8. Submission checklist (from Rules.md, tracked to the end)

- [ ] Technical report: problem, users, architecture, OpenCV 5 implementation, AWS deployment,
      evaluation, limitations, responsible use.
- [ ] Judge-accessible repository with pinned dependencies and build, deploy, test instructions.
- [ ] Architecture diagram showing OpenCV 5, AWS, COOL, and agent components.
- [ ] Working web endpoint (dashboard plus landing site) or arranged live screen share.
- [ ] Video, 5 minutes or less: team, working application, architecture, principal results.
- [ ] Evaluation evidence including failure cases and limitations.
- [ ] COOL award evidence: COOL version, instance config, reproducible benchmark, proof of
      execution on the Arm path.
- [ ] Agentic award evidence: workflow diagram, decision-changing trace, evaluation of task
      success, failure handling, observability, human control.
