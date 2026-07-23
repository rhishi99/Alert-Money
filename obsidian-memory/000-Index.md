# Alert-Money — Memory Index

Central hub. Read this first before touching an area of code.

## What this repo is
**PnL Sentinel** — a read-only Telegram bot that watches combined trading PnL
across Zerodha (Kite Connect) and DhanHQ and alerts when PnL crosses a
profit/loss threshold. Lives in [`pnl-sentinel/`](../pnl-sentinel/). Never
places orders.

## Map
- `pnl-sentinel/bot.py` — Telegram entrypoint, auth gate, JobQueue monitor loop
- `pnl-sentinel/brokers.py` — Zerodha + Dhan adapters, `BrokerHub` aggregator
- `pnl-sentinel/alerts.py` — latch + hysteresis alert state machine
- `pnl-sentinel/storage.py` — SQLite persistence (aiosqlite)
- `pnl-sentinel/config.py` — `.env` load + validation
- `pnl-sentinel/generate_kite_token.py` — daily Zerodha token helper (interactive)

## Vault structure
- `architecture/` — API maps, DB schema, component flow
- `decisions/` — ADRs, why-X-not-Y
- `logs/` — sprint notes, known errors, debug sessions
- `MEMORY.md` — flat one-line index of every vault file

## Rules (from global CLAUDE.md)
1. Before touching an area → check for a vault file covering it; read that, not the source.
2. After a sprint → update `logs/sprint-notes.md`.
3. After fixing a recurring bug → append to `logs/known-errors.md`.
