# PnL Sentinel 📊🔔

A Telegram bot that monitors real-time trading PnL across **Zerodha (Kite Connect)** and **DhanHQ**, and alerts you when combined PnL crosses your profit target or loss limit.

> ⚠️ This bot is read-only monitoring — it never places or modifies orders. Verify all figures against your broker terminal before making trading decisions.

## Architecture & flow

```
.env ──▶ config.py (validated Settings, fail-fast)
                │
bot.py (python-telegram-bot v21, asyncio)
  ├── TypeHandler gatekeeper: drops any chat ≠ TELEGRAM_CHAT_ID
  ├── Commands: /start /status /positions /setalert /clearalerts /resetalerts
  └── JobQueue: monitor() every POLL_INTERVAL_SECONDS
        │
        ├── brokers.py  BrokerHub → [ZerodhaBroker, DhanBroker]
        │     • sync SDKs run via asyncio.to_thread (event loop never blocks)
        │     • both brokers fetched concurrently with asyncio.gather
        │     • each returns a PnLSnapshot {realized, unrealized, ok, error}
        │
        ├── alerts.py   AlertEngine (latch + hysteresis state machine)
        │
        └── storage.py  SQLite via aiosqlite (thresholds + latch state)
```

## How state is handled

**Persistence.** Thresholds and alert-latch flags live in a single SQLite row per chat (`pnl_sentinel.db`). Everything survives restarts: if you set `/setalert loss -5000`, kill the bot, and restart, the limit and its armed/fired state are exactly where you left them.

**Anti-spam latch with hysteresis.** Each threshold is a tiny state machine:

- `ARMED → TRIGGERED`: PnL crosses the line → exactly **one** Telegram alert is sent and the latch is set in SQLite *before* anything else can fire.
- `TRIGGERED → ARMED`: PnL retreats back inside the band by ≥ 5% of the threshold value (e.g. loss limit −5,000 re-arms only above −4,750). This prevents machine-gun alerts when PnL oscillates around the line.
- Manual re-arm: `/resetalerts`, or setting a new threshold with `/setalert` (which always re-arms that side).

**Broker failure state.** If a broker starts erroring (typical case: Kite token expires mid-day), you get **one** warning message; the broker is excluded from the combined PnL until it recovers, and recovery clears the warning flag. The healthy broker keeps being monitored.

**Idle optimization.** If no thresholds are set, the monitor loop returns immediately without calling any broker API.

## How rate limits are handled

| Broker | Relevant limit | Our usage |
|---|---|---|
| Kite Connect | ~3 req/s per app; positions/holdings are lightweight | 2 requests per poll |
| DhanHQ | order APIs 25/s; data/non-trading APIs are generous | 2 requests per poll |
| Telegram | ~30 msg/s per bot | messages only on command or breach |

- `POLL_INTERVAL_SECONDS` is floor-clamped to **5s** in `config.py`; the default 15s means ≈ 4 requests per broker per minute — far below every limit.
- Polls run sequentially on a timer (JobQueue), never in overlapping bursts; both brokers are hit concurrently *within* one poll but only once per interval.
- No polling happens at all when no alert is configured.
- If you later add more chats/users, keep one shared `BrokerHub` snapshot per tick and fan out evaluations — do not fetch per-user.

## PnL semantics

- **Zerodha:** `positions()["net"]` gives per-position `realised`/`unrealised`; fully-closed intraday positions count as realized. Holdings contribute their mark-to-market `pnl` to unrealized.
- **Dhan:** `get_positions()` supplies `realizedProfit`/`unrealizedProfit` per position. Dhan's holdings endpoint doesn't return live MTM, so holdings are counted but don't add to alert PnL (positions cover intraday/F&O, which is what day-trading alerts care about).
- **Combined PnL** (what alerts trigger on) = Σ(realized + unrealized) across all *healthy* brokers.

## Setup

```bash
# 1. Create the project environment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env
#    → fill in TELEGRAM_BOT_TOKEN (from @BotFather),
#      TELEGRAM_CHAT_ID (from @userinfobot),
#      KITE_API_KEY / KITE_API_SECRET, DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN

# 3. Every trading morning: generate the daily Zerodha token
python generate_kite_token.py        # opens login URL → paste request_token

# 4. Run the bot
python bot.py
```

## Test it

**Offline (no broker/Telegram creds needed):** the alert engine — latch, hysteresis, re-arm, dual-side breach, and restart persistence — is covered by a standalone suite that runs against real SQLite state:

```bash
pip install aiosqlite      # already in requirements.txt
python test_alerts.py      # -> ALL 5 TESTS PASSED
```

**Live (in Telegram):**

1. In Telegram, open your bot and send `/start` — you should get the command menu (any other chat is silently rejected).
2. `/status` — live realized/unrealized/total per broker + combined.
3. `/setalert profit 10000` and `/setalert loss -5000`.
4. `/positions` — per-instrument breakdown.
5. To force-test alerting without waiting for a real breach, set a threshold you've already crossed, e.g. if combined PnL is +1,200, run `/setalert profit 1000` — an alert fires within one poll cycle, then stays silent (latched).
6. Restart the bot (`Ctrl-C`, `python bot.py`) and run `/status` — thresholds persist.

## Deploying beyond your laptop

- **VPS/systemd:** run `python bot.py` under a systemd unit with `Restart=always`; long-polling needs no inbound ports.
- **AWS/webhooks:** swap `run_polling()` for `run_webhook()` behind an HTTPS endpoint (or mount PTB inside FastAPI). Move the monitor loop to EventBridge → Lambda if you go serverless, and move state from SQLite to DynamoDB — Lambda's filesystem is ephemeral.
- The daily Kite login is interactive by design (SEBI requirement); automate the morning token step semi-manually or via TOTP-based flows at your own risk and per Zerodha's terms.

## File map

| File | Purpose |
|---|---|
| `bot.py` | Entrypoint: Telegram handlers, auth gate, JobQueue monitor |
| `brokers.py` | Zerodha/Dhan adapters + `BrokerHub` aggregator |
| `alerts.py` | Latch + hysteresis alert state machine |
| `storage.py` | SQLite persistence (aiosqlite) |
| `config.py` | `.env` loading & validation |
| `generate_kite_token.py` | Daily Kite access-token helper |
