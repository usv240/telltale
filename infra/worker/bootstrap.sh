#!/bin/bash
# Installs the TellTale worker on an arm64 Ubuntu host (stock or COOL AMI) and starts it as a
# systemd service. Idempotent: re-run after re-uploading release/pipeline.tar.gz to update.
# Expects to run from /opt/telltale with the release tarball already extracted there, and the
# environment variables TELLTALE_BUCKET, TELLTALE_QUEUE_URL, TELLTALE_REGION set.
set -euo pipefail
cd /opt/telltale

if [ -x /opt/cool/venvs/python_3.12/bin/python ]; then
  # COOL AMI: use the COOL-built OpenCV 5 environment as-is (this is the award's core claim).
  PY=/opt/cool/venvs/python_3.12/bin/python
  MODE=cool
  "$PY" -m pip install --quiet boto3==1.40.0
else
  # Stock AMI: pinned pip OpenCV 5 wheel (the E6 baseline).
  MODE=stock
  if [ ! -x /opt/telltale/venv/bin/python ]; then python3 -m venv /opt/telltale/venv; fi
  PY=/opt/telltale/venv/bin/python
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r infra/worker/requirements.txt
fi
"$PY" -m pip install --quiet --no-deps ./pipeline
"$PY" -c "import cv2, sys; print('cv2', cv2.__version__, cv2.__file__)"

cat > /etc/default/telltale <<EOF
TELLTALE_BUCKET=${TELLTALE_BUCKET}
TELLTALE_QUEUE_URL=${TELLTALE_QUEUE_URL}
TELLTALE_REGION=${TELLTALE_REGION:-us-east-1}
TELLTALE_MODE=${MODE}
TELLTALE_ALERT_TOPIC=${TELLTALE_ALERT_TOPIC:-}
TELLTALE_APPROVAL_URL=${TELLTALE_APPROVAL_URL:-}
TELLTALE_SECRET_PARAM=${TELLTALE_SECRET_PARAM:-}
EOF

cat > /etc/systemd/system/telltale-worker.service <<EOF
[Unit]
Description=TellTale epoch worker (OpenCV 5 pipeline, ${MODE})
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=/etc/default/telltale
WorkingDirectory=/opt/telltale
ExecStart=${PY} /opt/telltale/infra/worker/worker.py
Restart=always
RestartSec=5
StandardOutput=append:/var/log/telltale-worker.log
StandardError=append:/var/log/telltale-worker.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable telltale-worker.service
systemctl restart telltale-worker.service
echo "telltale worker started in ${MODE} mode with ${PY}"
