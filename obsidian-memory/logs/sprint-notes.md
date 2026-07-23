# Sprint notes

## 2026-07-23 — bootstrap
- Merged `claude/telegram-pnl-alert-bot-rwcx8n` → `main` (pnl-sentinel/, 923 lines).
- Borrowed secrets + harness from NxBagger — see [[secrets-from-nxbagger]].
- Built `pnl-sentinel/.venv`, installed requirements.
- Verified real Dhan data via live `BrokerHub.snapshots()` (no dummy data).
- Zerodha auth is user-driven daily: `generate_kite_token.py` (interactive).
- Bot launched (long-polling) — see [[pnl-sentinel]] for flow.
- Tagged main after first working run.

### Known constraints
- Zerodha data only appears after the daily `generate_kite_token.py` login.
- Dhan access token is static (~30 days) — will need refresh; watch expiry.
