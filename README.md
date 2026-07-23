# Alert-Money

**PnL Sentinel** — a Telegram bot that monitors real-time trading PnL across
**Zerodha (Kite Connect)** and **DhanHQ**, and alerts you when combined PnL
crosses your profit target or loss limit.

The application lives in [`pnl-sentinel/`](./pnl-sentinel). See its
[README](./pnl-sentinel/README.md) for architecture, state/rate-limit handling,
setup, and run instructions.

## Quick start

```bash
cd pnl-sentinel
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in tokens
python generate_kite_token.py   # each trading morning (Zerodha only)
python bot.py
```

Then in Telegram: `/start` → `/status` → `/setalert profit 10000` → `/setalert loss -5000`.

Offline test of the alert engine (no credentials needed):

```bash
cd pnl-sentinel && python test_alerts.py   # -> ALL 5 TESTS PASSED
```
