#!/usr/bin/env bash
# StockPulse — start bot (long-poll) + Razorpay webhook in one shot.
# Ctrl-C stops both. (Windows git-bash: venv python is under Scripts/.)
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY=".venv/bin/python"   # fall back to POSIX venv layout

echo "Starting StockPulse bot + webhook..."
"$PY" bot.py &
BOT=$!
"$PY" -m uvicorn webhook:app --port 8000 &
WEB=$!

trap 'kill "$BOT" "$WEB" 2>/dev/null' EXIT INT TERM
echo "Bot (pid $BOT) + webhook (pid $WEB) running. Webhook: http://localhost:8000"
echo "Live Razorpay test: cloudflared tunnel --url http://localhost:8000"
wait
