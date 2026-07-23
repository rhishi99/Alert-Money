# Decision: borrow secrets + harness from NxBagger

**Date:** 2026-07-23

## Secrets
PnL Sentinel needs Telegram + Zerodha + Dhan credentials. Rather than mint new
ones, borrowed from `NxBagger/src/backend/.env` (same trading accounts):

| pnl-sentinel key | NxBagger source key |
|---|---|
| TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID | same |
| KITE_API_KEY / KITE_API_SECRET | ZERODHA_API_KEY / ZERODHA_API_SECRET |
| DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN | same |

Live values live only in `pnl-sentinel/.env` (gitignored, never committed).
KITE_ACCESS_TOKEN regenerated daily by the user via `generate_kite_token.py`.

## Harness
Copied dev harness from NxBagger, symlinks dereferenced to real files so nothing
points back at the source repo:
- `.claude/` (agents, commands, skills) — incl. senior-software-architect agent
- `.agents/skills/` — emil-design-eng, impeccable, supabase, ui-ux-pro-max, nxbagger-hold
- `.codex/`, `.github/`, `.mcp.json`, `.gitattributes`, `.gitleaks.toml`
- Dropped NxBagger-specific mutable state (agent-memory/, worktrees/).
- **Did NOT** copy NxBagger's CLAUDE.md / AGENTS.md — they are supabase/trading-dashboard
  specific; this repo gets its own scoped memory instead (this vault).
