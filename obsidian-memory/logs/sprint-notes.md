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

## 2026-07-23 — SaaS pivot + Phase 1 (StockPulse)
Big direction change: PnL Sentinel → **StockPulse**, a public paid multi-tenant
bot. Full plan in [`docs/architecture.md`]; decision in [[stockpulse-saas]].

**Infra/creds done:**
- Dhan token now READ from AWS SSM `/nxbagger/DHAN_ACCESS_TOKEN` (never mint) — [[dhan-token-read-from-ssm]]. Auto-recover on DH-906 in `brokers.py`.
- Config SSM dual-path (`DHAN_TOKEN_SSM_PARAM`) + `deploy/` (EC2 nano) — [[hosting-ec2-nano]]. Note: EC2-nano design RETIRED for the SaaS (needs webhooks+Postgres).
- **Dedicated bot** @stockpulse_official_bot (token 8658796977) — replaced shared @nxbagger_bot to end the 409 poller collision. Chat id 468500661.
- Avatar = `brand/logo/stockpulse_avatar_512.png` (minimal line-mark). User sets via @BotFather.

**Phase 1 shipped (live on the bot):**
- Inline-button onboarding: /start (hero banner) → Get Started → Disclaimer → I Understand (T&C stored in SQLite `onboarding` table). Owner-gated data commands (`@owner_only`) — strangers get onboarding, never PnL.
- `/plans` shows priced `brand/onboarding/plans.jpg` (₹10/mo, ₹99/yr); `/howitworks` shows flow image. `render_screen()` handles text↔photo transitions. Persistent command menu (setMyCommands).
- Brand assets in `brand/` (4 logos, 4 onboarding images via agy/Imagen; grok is OUT OF QUOTA). Landing page + 4 DRAFT policy pages (Terms/Privacy/Refund/Contact) in `brand/onboarding-page/`.

**Test harness:** `pnl-sentinel/e2e/` Telethon E2E (dedicated NON-owner test account) — `test_onboarding_e2e.py` PASSES (flow + owner-gating). Creds in `.env` as `API_ID`/`API_HASH`/`TG_TEST_SESSION`. Setup + optional MCP (chigwell/telegram-mcp, uv installed, NOT wired) in `docs/testing-telegram.md`.

**Razorpay (Phase 2, not built):** reuse test key — user generated new test keys (24h grace kills nxbagger's old `rzp_test_T2Wm...`; update nxbagger too). Prereqs still open: policy pages filled + legal, webhook host pick, subscription model (Payment Links first vs UPI autopay).

### Next session starts here
- Phase 2: scaffold FastAPI Razorpay webhook (sig-verify) + plan config + subscription gating, testable in Razorpay TEST mode. Needs: test keys (in .env now?), host pick.
- Bot runs locally as a long-poll daemon during dev; NOT yet deployed.
