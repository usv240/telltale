# Agent Design: The Skeptical Supervisor

Sub-project: `agent/`. The agent exists for one measurable purpose: reduce false alarms without
missing real acceleration. Its output is judged by the E5 ablation (false-alarm and
missed-detection rates with the agent on and off), not by how fluent its prose is.

This design satisfies the Agentic Vision award requirements in Rules.md: OpenCV 5 results must
change a later plan, tool call, action, or human-approval request, in a multi-step
perception-decision-action loop, with evidence of failure handling, observability, and human
control.

## 1. Where the agent sits

The pipeline is deterministic and always runs. The agent is invoked on events, not on every
epoch:

- E_ANOMALY: a zone's velocity crosses the MOVING or ACCELERATING threshold.
- E_CAMERA: stabilization reports a camera event or low inlier count.
- E_QUALITY: valid-subset fraction dropped, cross-check flagged REVIEW, or blindness persists.
- E_FORECAST: forecast horizon crossed the CRITICAL threshold.

On each event the agent runs an investigation loop with a hard budget (default 6 tool calls,
2 minutes), then either closes the event with a verdict or escalates to a human with an
evidence packet. Autonomy is deliberately bounded: the agent can re-measure and reconfigure
capture, but only a human can send a public alert, and nothing the agent does can suppress the
raw data feed.

## 2. Tools (MCP server)

The pipeline is exposed to the agent as an MCP tool server (`agent/mcp_server.py`), so any
MCP-capable model can drive it; we use Amazon Bedrock (Claude) in deployment and a scripted
deterministic policy in tests.

| Tool | What it does | Why the agent needs it |
|---|---|---|
| `get_site_state(site)` | Current alarm state, last N epochs of zone series, quality metrics | situational awareness |
| `run_dic(site, epoch, reference)` | Re-run Stage C against a chosen reference epoch | test whether motion persists against multiple baselines |
| `check_stability(site, epoch)` | Stage B diagnostics: inliers, RMS, homography decomposition | camera event vs ground motion |
| `render_overlay(site, epoch)` | Displacement heatmap and vector overlay image | visual evidence for the packet |
| `update_masks(site)` | Recompute vegetation and texture masks | rule out foliage decorrelation |
| `set_cadence(site, per_day)` | Raise or lower capture frequency within bounds | more data when it matters, cheaper when quiet |
| `fit_forecast(site, zone)` | Recompute the ensemble forecast with current series | fresh numbers after re-measurement |
| `compile_evidence(site, event)` | Bundle series plots, overlays, diagnostics, and the decision log into a packet | the thing a human approves against |
| `request_human_approval(site, packet)` | Notify the duty contact, block CRITICAL until approve or dismiss | human control |

Every tool call and its result summary is appended to a per-event decision log (JSON lines).
The dashboard renders this log verbatim; the same log is the award's required trace.

## 3. Investigation policy (the playbook)

Encoded in the system prompt and mirrored by the deterministic test policy, so behavior is
reviewable:

1. On E_ANOMALY: first suspect the measurement. Check stability diagnostics; re-run DIC against
   two alternate references (the previous epoch and an older one); confirm the motion is
   spatially coherent (a connected region moving the same direction beats scattered speckle).
2. If motion survives scrutiny: raise cadence, recompute the forecast, and move the alarm
   ladder one step, writing the reasoning to the log.
3. On E_CAMERA: verify with stable-region residuals; if the camera moved, re-baseline geometry,
   do not touch the displacement series, and note the gap.
4. On E_QUALITY: update masks; if coverage still poor, recommend reference refresh; if blind,
   mark the site blind and say so on the dashboard.
5. On E_FORECAST: compile evidence and request human approval. The packet must contain: the 1/v
   plot with the fit and window, the displacement overlay, stability diagnostics, the last
   decision log, and plain-language reasoning at a reading level a district officer can act on.
6. Never: send external alerts autonomously, delete data, or lower an alarm level without
   logging why.

## 4. Failure handling and security

- Tool budget and timeout per event; on budget exhaustion the event escalates to a human by
  default (fail toward human attention, never toward silence).
- The MCP server validates all inputs against the site registry; the agent has no shell, no
  network, and no write access outside site artifacts.
- Bedrock invocation uses least-privilege IAM; decision logs are append-only in S3.
- If the model endpoint is unavailable, the system degrades to threshold-only alarms with a
  visible "agent offline" badge; deterministic behavior is the floor, agent behavior is the
  improvement.

## 5. Evaluation (E5)

Scripted scenario suite, each run with agent on and agent off:

- camera bump (injected homography) during steady creep
- lighting step change and shadow sweep
- fog sequence (contrast collapse)
- vegetation flutter over part of the target zone
- true accelerating creep to failure (simulator)
- true creep plus camera bump on the same day (the hard one)

Metrics: false alarms per scenario-week, missed or late OOA declarations, median forecast error
at fixed lead times, human-approval requests raised with complete evidence packets. Results
table lands in `evaluation/results/` and on the landing site.

## 6. Files

```
agent/
  DESIGN.md            this file
  mcp_server.py        MCP server wrapping the pipeline package
  policy.md            the system prompt (versioned, reviewable)
  deterministic.py     scripted policy used in tests and as offline floor
  scenarios/           E5 scenario definitions
```
