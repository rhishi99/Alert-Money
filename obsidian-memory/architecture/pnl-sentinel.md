# PnL Sentinel — architecture

## Flow
```
.env ─▶ config.py (validated Settings, fail-fast on Telegram creds)
          │
bot.py (python-telegram-bot v21, asyncio, long-polling)
  ├── TypeHandler gatekeeper (group=-1): drops any chat ≠ TELEGRAM_CHAT_ID
  ├── Commands: /start /status /positions /setalert /clearalerts /resetalerts
  └── JobQueue.run_repeating(monitor, POLL_INTERVAL_SECONDS, first=5)
        ├── brokers.py  BrokerHub → [ZerodhaBroker, DhanBroker]
        │     sync SDKs via asyncio.to_thread; both fetched with asyncio.gather
        ├── alerts.py   AlertEngine (latch + hysteresis)
        └── storage.py  SQLite (thresholds + latch state)
```

## PnL semantics
- **Zerodha:** `positions()["net"]` realised/unrealised; closed intraday = realized. Holdings `pnl` → unrealized.
- **Dhan:** `get_positions()` realizedProfit/unrealizedProfit. Holdings have no live MTM → count only, no PnL.
- **Combined** (alert trigger) = Σ(realized+unrealized) across healthy brokers.

## Broker enable logic (brokers.py BrokerHub.__init__)
- Zerodha added only if `enable_zerodha AND kite_api_key AND kite_access_token`.
- Dhan added only if `enable_dhan AND dhan_client_id AND dhan_access_token`.
- KITE_ACCESS_TOKEN is blank until the daily interactive `generate_kite_token.py` run → **Zerodha silently skipped** until then. Dhan (static ~30-day token) runs immediately.

## Alert state machine (per threshold)
- ARMED→TRIGGERED: cross line → one alert, latch in SQLite first.
- TRIGGERED→ARMED: PnL retreats ≥5% of threshold (hysteresis, anti machine-gun).
- Manual re-arm: `/resetalerts` or new `/setalert`.
- Broker failure: one warning, broker excluded until recovery clears flag.
- Idle: no thresholds set → monitor returns before any API call.

## Rate limits — safe by design
Poll floor-clamped to 5s (config.py). Default 15s ≈ 4 req/broker/min, far below Kite ~3/s and Dhan limits.
