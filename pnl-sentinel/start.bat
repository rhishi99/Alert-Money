@echo off
REM StockPulse — start bot (long-poll) + Razorpay webhook in one shot (Windows).
REM Each runs in its own window; close a window to stop that process.
cd /d "%~dp0"
echo Starting StockPulse bot + webhook...
start "StockPulse Bot"     .venv\Scripts\python.exe bot.py
start "StockPulse Webhook" .venv\Scripts\python.exe -m uvicorn webhook:app --port 8000
echo Bot + webhook launched. Webhook on http://localhost:8000
echo For live Razorpay testing, expose it:  cloudflared tunnel --url http://localhost:8000
