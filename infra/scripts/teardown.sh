#!/bin/bash
# Remove the TellTale stack and its data. Empties the bucket (all versions) first because
# CloudFormation will not delete a non-empty bucket.
set -euo pipefail
STACK=${TELLTALE_STACK:-telltale}
REGION=${AWS_REGION:-$(aws configure get region)}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="telltale-${ACCOUNT}"
echo "This deletes stack ${STACK} and bucket ${BUCKET} in ${REGION}. Type the bucket name to confirm:"
read -r CONFIRM
[ "$CONFIRM" = "$BUCKET" ] || { echo "aborted"; exit 1; }
python - "$BUCKET" "$REGION" <<'EOF'
import sys, boto3
bucket, region = sys.argv[1], sys.argv[2]
s3 = boto3.resource("s3", region_name=region).Bucket(bucket)
s3.object_versions.delete()
print("bucket emptied")
EOF
aws cloudformation delete-stack --region "$REGION" --stack-name "$STACK"
aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$STACK"
echo "stack ${STACK} deleted"
