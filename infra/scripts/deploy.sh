#!/bin/bash
# One-command deploy. Usage:
#   infra/scripts/deploy.sh                       # stock Ubuntu arm64 on c8g.large
#   infra/scripts/deploy.sh --cool ami-xxxxxxxx   # COOL Marketplace AMI (subscribe first)
#   infra/scripts/deploy.sh --type c8g.xlarge
# Packages pipeline/ and infra/worker/ into release/pipeline.tar.gz, deploys the CloudFormation
# stack, uploads the dashboard, and restarts the worker through SSM.
set -euo pipefail
cd "$(dirname "$0")/../.."
STACK=${TELLTALE_STACK:-telltale}
REGION=${AWS_REGION:-$(aws configure get region)}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="telltale-${ACCOUNT}"
COOL_AMI=""
TYPE="c8g.large"
EMAIL="${TELLTALE_ALERT_EMAIL:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --cool) COOL_AMI="$2"; shift 2 ;;
    --type) TYPE="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    *) echo "unknown arg $1"; exit 2 ;;
  esac
done

# Approval-link signing secret: keep the existing one across redeploys, create on first deploy.
SECRET=$(aws ssm get-parameter --region "$REGION" --name "/${STACK}/approval-secret"   --query Parameter.Value --output text 2>/dev/null || true)
if [ -z "$SECRET" ] || [ "$SECRET" = "None" ]; then SECRET=$(openssl rand -hex 24); fi

echo "== packaging release"
rm -f /tmp/pipeline.tar.gz
tar czf /tmp/pipeline.tar.gz \
  --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.egg-info' \
  pipeline infra/worker agent evaluation/e6_cool_benchmark.py

echo "== ensuring bucket exists for the release artifact (stack creates it on first deploy)"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "   bucket missing; deploying stack without worker first"
  aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
    --template-file infra/cloudformation.yaml --capabilities CAPABILITY_IAM \
    --parameter-overrides InstanceType="$TYPE" CoolAmiId="$COOL_AMI" AlertEmail="$EMAIL" ApprovalSecret="$SECRET" \
    --no-fail-on-empty-changeset || true
fi
aws s3 cp /tmp/pipeline.tar.gz "s3://${BUCKET}/release/pipeline.tar.gz"

echo "== deploying stack ${STACK} (${TYPE}${COOL_AMI:+, COOL ${COOL_AMI}})"
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file infra/cloudformation.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides InstanceType="$TYPE" CoolAmiId="$COOL_AMI" \
  --no-fail-on-empty-changeset

echo "== uploading dashboard"
aws s3 sync web/dashboard "s3://${BUCKET}/public/" --exclude 'demo-data/*' --delete \
  --exclude 'sites/*'

INSTANCE=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='WorkerInstanceId'].OutputValue" --output text)
TOPIC=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='AlertTopicArn'].OutputValue" --output text)
APPROVAL=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ApprovalUrl'].OutputValue" --output text)
URL=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" --output text)
QUEUE=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='QueueUrl'].OutputValue" --output text)

echo "== refreshing worker code on ${INSTANCE} via SSM (no-op on first boot; user-data does it)"
aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript --comment "telltale update" \
  --parameters "commands=[\"set -e\",\"export TELLTALE_BUCKET=${BUCKET} TELLTALE_QUEUE_URL=${QUEUE} TELLTALE_REGION=${REGION} TELLTALE_ALERT_TOPIC=${TOPIC} TELLTALE_APPROVAL_URL=${APPROVAL} TELLTALE_SECRET_PARAM=/${STACK}/approval-secret TELLTALE_AGENT=llm\",\"cd /opt/telltale && aws s3 cp s3://${BUCKET}/release/pipeline.tar.gz . && tar xzf pipeline.tar.gz && bash infra/worker/bootstrap.sh\"]" \
  --query "Command.CommandId" --output text 2>/dev/null || echo "   (SSM not ready yet; worker installs itself on first boot)"

echo
echo "dashboard: ${URL}"
echo "bucket:    s3://${BUCKET}"
echo "worker:    ${INSTANCE}"
echo "seed demo: python infra/scripts/seed_demo.py --s3 ${BUCKET}"
