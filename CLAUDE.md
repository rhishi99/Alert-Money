# Alert-Money — project instructions

## What this is
**PnL Sentinel** (`pnl-sentinel/`) — a read-only Telegram bot that monitors
combined trading PnL across **Zerodha (Kite Connect)** and **DhanHQ** and alerts
when PnL crosses a profit target or loss limit. It never places orders.

## Before touching code
Read `obsidian-memory/000-Index.md` first. For any area with a vault file
(`obsidian-memory/architecture/pnl-sentinel.md` etc.), read that instead of the
source — token discipline.

## Running it
- venv: `pnl-sentinel/.venv` (gitignored). Run everything from `pnl-sentinel/`.
- Start bot: `.venv/Scripts/python.exe bot.py` (long-polling daemon).
- Live smoke check: `.venv/Scripts/python.exe verify_live.py`.

## Secrets — `pnl-sentinel/.env` (gitignored, never commit)
- Borrowed from `NxBagger/src/backend/.env`. See `obsidian-memory/decisions/secrets-from-nxbagger.md`.
- **Zerodha:** daily interactive token — `python generate_kite_token.py` each morning.
- **Dhan:** single-session. Do NOT reinvent a minter. Reuse NxBagger's expert
  `dhan_auth` (`src/backend/api/brokers/dhan_auth.py`): mint once via NxBagger's
  venv, then copy the exact `DHAN_ACCESS_TOKEN` into `pnl-sentinel/.env` so both
  apps share ONE token (same string = one Dhan session, no eviction war).

## Guardrails
- This bot is read-only monitoring — never add order-placing code.
- Verify no secrets are staged before every commit (`git diff --cached`).
- Follow global CLAUDE.md rules (rtk prefixes, plan mode >3 files, /code-review low before push).
