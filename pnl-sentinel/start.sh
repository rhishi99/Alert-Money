#!/usr/bin/env bash
# Sweep strays + start bot + webhook.
# On Windows/git-bash delegate to stockpulse.ps1 (reliable process-tree kill);
# on Linux fall back to pkill + backgrounded processes.
set -euo pipefail
cd "$(dirname "$0")"

if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "./stockpulse.ps1" start both
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "./stockpulse.ps1" status
  exit 0
fi

# --- Linux path ---
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
mkdir -p .logs
pkill -f 'bot\.py' 2>/dev/null || true
pkill -f 'uvicorn webhook:app' 2>/dev/null || true
sleep 1
nohup "$PY" bot.py > .logs/bot.log 2>&1 &
nohup "$PY" -m uvicorn webhook:app --port 8000 > .logs/webhook.log 2>&1 &
echo "bot + webhook started (logs in .logs/)."
