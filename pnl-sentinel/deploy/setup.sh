#!/usr/bin/env bash
# Idempotent provisioning script for the Ubuntu 24.04 ARM64 (t4g) box.
# Run as a user with sudo (e.g. `ubuntu`): sudo bash deploy/setup.sh
#
# Manual pre-reqs (do these BEFORE running this script):
#   1. IAM role with deploy/iam-policy.json attached to the instance
#      (so SSM GetParameter works with no keys on disk).
#   2. Set REPO_URL below (or export it) to this repo's git remote.
#   3. After this script finishes, create /opt/pnl-sentinel/pnl-sentinel/.env
#      by hand (see deploy/deploy.md) — it is never created by this script.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/rhishi99/Alert-Money.git}"
INSTALL_ROOT="/opt/pnl-sentinel"
APP_DIR="$INSTALL_ROOT/pnl-sentinel"   # repo's pnl-sentinel/ subfolder is the app root
VENV_DIR="$APP_DIR/.venv"
SERVICE_NAME="pnl-sentinel"

sudo apt-get update -y
sudo apt-get install -y python3.12 python3.12-venv git

if [ -d "$INSTALL_ROOT/.git" ]; then
    echo "Repo already present — pulling latest."
    git -C "$INSTALL_ROOT" pull
else
    echo "Cloning repo into $INSTALL_ROOT"
    sudo mkdir -p "$INSTALL_ROOT"
    sudo chown "$(whoami)" "$INSTALL_ROOT"
    git clone "$REPO_URL" "$INSTALL_ROOT"
fi

python3.12 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
    echo "NOTE: $APP_DIR/.env does not exist yet — create it before starting the service."
    echo "      See deploy/deploy.md for the required variables."
fi

sudo cp "$APP_DIR/deploy/pnl-sentinel.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "Done. Check status with: systemctl status $SERVICE_NAME"
