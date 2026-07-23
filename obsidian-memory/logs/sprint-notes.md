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

## 2026-07-23 — Phase 2 (Razorpay) scaffolded
Payment → subscription pipeline built + tested (TEST mode). Decisions: **Payment
Links** (one-shot, not Subscriptions/autopay) + **host deploy deferred** (tunnel test).
See [`docs/razorpay-phase2.md`] and [[razorpay-payment-links-phase2]].

**Built:**
- `config.py`: Razorpay keys + `RAZORPAY_WEBHOOK_SECRET` + plan-period/grace days.
- `storage.py`: `subscriptions` + `payments_log` tables; `activate_subscription`,
  `subscription_status`, idempotent `record_payment_event`, pure `compute_status`.
- `razorpay_client.py` (NEW): `create_payment_link(uid, plan)` via httpx (no SDK); `notes` carry uid+plan.
- `webhook.py` (NEW): FastAPI `POST /razorpay/webhook`, HMAC-SHA256 sig-verify over raw body,
  idempotent activation. Separate process, shares SQLite. Lifespan (not deprecated on_event).
- `bot.py`: `plan:*` buttons → payment link + Pay URL button; `/subscription` status cmd;
  `requires_subscription` gate (wired, NOT on broker cmds — Phase 3, owner-only stays).
- `requirements.txt`: fastapi 0.115.6 + uvicorn 0.32.1 (installed in venv).
- Self-check `e2e/test_webhook.py` — **3 pass** (sig-verify, activation, idempotency, expiry).

**Open before go-live:** register webhook + paste `RAZORPAY_WEBHOOK_SECRET`, live UPI test,
pick host, fill policy pages/legal. **Side task ≤24h:** update NxBagger with new Razorpay
test key (old `rzp_test_T2Wm...` dies on grace).

### Next session starts here
- Phase 2 code done + green. Do the live tunnel smoke (docs/razorpay-phase2.md) when ready.
- Phase 3: multi-tenant BYO-broker + KMS encryption + Postgres; apply `requires_subscription`
  to real per-user data.
- Bot runs locally as a long-poll daemon during dev (daemon still on OLD code — restart to pick up Phase 2).
