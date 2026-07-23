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
- **Dhan:** single-session — **never mint from Alert-Money** (minting evicts the
  live session, `DH-906`). READ the token from NxBagger's AWS SSM
  (`/nxbagger/DHAN_ACCESS_TOKEN`, region `ap-south-1`, needs `MSYS_NO_PATHCONV=1`
  in git-bash) into `pnl-sentinel/.env`. The AWS-deployed NxBagger is the sole
  minter/publisher. See memory note `dhan-token-read-from-ssm`.

## Guardrails
- This bot is read-only monitoring — never add order-placing code.
- Verify no secrets are staged before every commit (`git diff --cached`).
- Follow global CLAUDE.md rules (rtk prefixes, plan mode >3 files, /code-review low before push).
