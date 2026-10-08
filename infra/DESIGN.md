# Infrastructure Design: AWS, COOL, and the Cost Model

Sub-project: `infra/`. Everything needed to run TellTale as a service, reproducibly, from one
command, with the vision core on COOL/Graviton. Scored under "Cloud delivery, reproducibility,
responsible operation" (10 percent) and it carries the Best Use of COOL award (see Rules.md:
COOL must execute the claimed core workload on Graviton, with reproducible measurements against
an appropriate baseline).

## 1. Architecture

```
Field camera (phone / RPi / CCTV)
      |  burst upload (presigned URL or IoT Core)
      v
S3 ingest bucket  s3://telltale-ingest/<site>/<epochtime>/frame_*.jpg
      |  S3 event
      v
EventBridge rule -> SQS epoch queue (DLQ attached)
      |
      v
DIC worker: ECS service on EC2 c8g (Graviton4), COOL v3.1 AMI as host
  - container mounts /opt/cool; PYTHONPATH points at COOL site-packages
  - runs `telltale epoch` from the same pipeline package as the laptop
  - logs cv2.__file__ and COOL version into every job record (award proof)
      |
      +--> S3 artifacts bucket: stacked epoch, displacement .npz, overlay .png
      +--> DynamoDB table `telltale-series`: zone displacement points, quality metrics
      v
Forecast Lambda (arm64) triggered per processed epoch
  - recomputes ensemble forecast, writes alarm state
      |
      +--> EventBridge events for the agent (E_ANOMALY, E_CAMERA, E_QUALITY, E_FORECAST)
      v
Agent task (ECS, small) : MCP server + Bedrock (Claude) invocation
      |
      +--> SNS topic: SMS and email to duty contacts; approval link (API Gateway + Lambda)
      v
Dashboard and landing site: static site on S3 + CloudFront
  - reads a read-only JSON API (API Gateway + Lambda) for series, overlays, decision logs
```

Notes:
- One codebase: the worker container installs `pipeline/` unchanged. Local, CI, and cloud run
  identical code; only the entrypoint differs.
- Idempotency: epoch id is the S3 prefix; reprocessing overwrites the same artifacts, so
  retries are safe and the DLQ can be replayed.
- The COOL AMI is Arm-only; the build pipeline produces a multi-arch container, and CI runs the
  test suite on both x86 and arm64 runners to keep the benchmark honest.

## 2. COOL specifics (award evidence checklist)

- AMI: Cloud Optimized OpenCV For AWS Graviton4, COOL v3.1, based on OpenCV 5.0, Ubuntu 24.04.
- Instances: c8g.large for steady service, c8g.4xlarge for the benchmark sweep.
- Activation: `source /opt/cool/venvs/python_3.12/bin/activate`, or system Python with
  `LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib` and `PYTHONPATH=/opt/cool/python_3.12/site-packages`.
- Proof of execution: each job record stores `cv2.__file__`, `cv2.getBuildInformation()` hash,
  instance type, and AMI id.
- Baselines for E6: (a) stock OpenCV 5 pip wheel on the same c8g instance, (b) stock wheel on
  c7i (x86) at matched vCPU count. Metrics: epochs per hour, p50 and p95 epoch latency, cost
  per 1,000 epochs (instance price times duration), and nights of monitoring per dollar at
  daily cadence. Harness: `evaluation/e6_cool_benchmark.py`, emits CSV plus the report figure.

## 3. Reproducibility

- IaC: AWS CDK (Python) in `infra/cdk/`; `cdk deploy telltale-dev` brings up the full stack.
- Pinned dependencies everywhere (`requirements.txt` with exact versions; container base images
  pinned by digest).
- Seeded demo: a `make demo` target uploads a bundled sample epoch sequence (synthetic collapse
  plus a Mukilteo excerpt) so judges see the full path without a camera.
- Teardown documented; the stack fits inside the AWS credit envelope with wide margin.

## 4. Observability

- CloudWatch metrics per site: epochs processed, valid-subset fraction, stabilization inliers,
  queue depth, worker latency, forecast horizon, alarm state, agent tool calls per event.
- Structured JSON logs from the worker and agent; correlation id = epoch id.
- Alarms on the system itself: queue age, worker failures, blind-site duration. A monitoring
  system that silently stops monitoring is the worst failure mode it can have, so liveness is
  alarmed independently of slope activity.

## 5. Security and responsible operation

- Least-privilege IAM per component; ingest bucket accepts uploads only via presigned URLs
  scoped per site; no public write anywhere.
- No person-related processing exists in the codebase; cameras are aimed at ground and
  structures, and the responsible-use section of the report states operator guidance.
- Alert governance: external alerts require human approval through the signed approval link;
  every approval or dismissal is logged with who and when.
- Data retention: raw bursts age out after a configurable window; derived series and decision
  logs are retained (small, auditable).

## 6. Cost model (to be finalized with measured numbers in E6)

Per site at daily cadence, 1080p bursts: storage a few MB per day, one worker-minute per epoch,
Lambda and DynamoDB in free-tier territory at pilot scale. Target: under 15 USD per site per
month at daily cadence, under 40 USD at 6 epochs per day, dominated by EC2 time that COOL
directly reduces. The final report publishes the measured bill for the pilot fleet.

## 7. Files

```
infra/
  DESIGN.md          this file
  cdk/               CDK app (stacks: ingest, compute, data, web, observability)
  worker/            Dockerfile, entrypoint, COOL activation script
  scripts/           deploy, seed-demo, teardown, benchmark-runner
```
