# TellTale on AWS

One CloudFormation stack, one command. The vision core runs on a Graviton (arm64) EC2 worker;
everything else is S3, SQS, CloudFront and CloudWatch.

```
camera / upload_epoch.py
   └─ s3://telltale-<acct>/ingest/<site>/<t>/frame_*.png + manifest.json
        └─ S3 event ──> SQS telltale-epochs (DLQ after 3 failures)
              └─ EC2 c8g.large worker (infra/worker/worker.py, systemd)
                    stack ─> stabilize ─> DIC ─> zones ─> forecast      (OpenCV 5, pipeline/)
                    └─ s3://.../public/sites/<site>/{series,forecast}.json, epochs/<t>/overlay.png
                          └─ CloudFront ──> dashboard (web/dashboard, static, no framework)
CloudWatch: TellTale/* metrics per site, queue-age and DLQ alarms (liveness of the monitor itself)
```

## Deploy

Prerequisites: AWS CLI v2 with credentials, a default region, `bash`, `tar`.

```bash
infra/scripts/deploy.sh                     # stock Ubuntu 24.04 arm64 on c8g.large (E6 baseline)
infra/scripts/deploy.sh --cool ami-xxxxxxxx # COOL AMI once subscribed (see below)
infra/scripts/deploy.sh --type c8g.xlarge   # bigger worker for 4K sites
```

The script packages `pipeline/` and `infra/worker/` into `release/pipeline.tar.gz`, deploys
`infra/cloudformation.yaml`, uploads `web/dashboard/`, and refreshes the worker through SSM.
First boot takes about three minutes (apt, pip, pinned OpenCV 5 wheel). Outputs: dashboard URL,
bucket, worker instance id.

Then seed the demo site so the dashboard has data without a camera:

```bash
python infra/scripts/seed_demo.py --s3 telltale-<account-id> --wait
```

After a change to the overlay style, `python infra/scripts/rerender_overlays.py --store <local
store> --site <site>` redraws each epoch's `overlay.png` from its stored field without re-running
the pipeline or the agent, so published traces and verdicts stay as measured.

Real cameras use `infra/scripts/upload_epoch.py` (frames first, manifest last, so a partial
upload never triggers processing). The first epoch of a site must include `--site-config`.

## COOL path (Best Use of COOL award)

1. Subscribe to "Cloud Optimized OpenCV for AWS Graviton" on AWS Marketplace
   (https://aws.amazon.com/marketplace/pp/prodview-fdvbfiewzuehs). Subscription is a terms
   acceptance on the account; it is not automated here on purpose.
2. Find the arm64 AMI id for your region, for example:
   `aws ec2 describe-images --owners aws-marketplace --filters "Name=name,Values=*COOL*Graviton4*" --query "Images[].[ImageId,Name]"`
3. `infra/scripts/deploy.sh --cool <ami-id>`.

`infra/worker/bootstrap.sh` detects `/opt/cool/venvs/python_3.12` and uses that interpreter, so
the pipeline imports COOL's OpenCV 5 build. Every epoch record then carries
`runtime.cv2_file = /opt/cool/...`, `runtime.build_hash`, `runtime.instance_type` and
`runtime.ami_id`; `forecast.json` exposes `runtime.cool = true` and the dashboard shows the
"COOL on Graviton" badge. That is the proof-of-execution evidence the award asks for.
Benchmark against the stock path with `evaluation/e6_cool_benchmark.py` (same tarball, two
AMIs, same instance type).

## Operating

- Worker log: `/var/log/telltale-worker.log` on the instance; shell access with
  `aws ssm start-session --target <instance-id>` (no inbound ports, no SSH keys).
- Update code: re-run `deploy.sh`; it re-uploads the tarball and restarts the service.
- Replay a failed epoch: move the message from `telltale-epochs-dlq` back to `telltale-epochs`
  (idempotent: artifacts are keyed by site and epoch time).
- Tear down: empty the bucket, then `aws cloudformation delete-stack --stack-name telltale`.

## Cost (on-demand, us-east-1, October 2026 list prices)

c8g.large is about 0.08 USD per hour (roughly 58 USD per month if left running continuously;
stop the instance between captures for a pilot). S3, SQS, CloudFront and CloudWatch are in
free-tier territory at pilot scale. Measured epoch cost comes from E6.

## Security and responsible operation

- Bucket blocks all public access; CloudFront reads `public/*` through an Origin Access Control.
- Worker role: read and write on this bucket only, consume this queue only, metrics in the
  `TellTale` namespace only, SSM core. No inbound security-group rules.
- Raw bursts expire after 30 days; derived series and records are small and retained.
- No person detection or face processing exists anywhere in the code; cameras look at ground.
- The system never silences itself: unusable epochs are recorded with a reason, and the queue
  age and DLQ alarms fire when the monitor itself stops working.
