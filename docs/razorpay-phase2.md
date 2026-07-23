# Razorpay Phase 2 — subscription payments (TEST mode)

One-shot **Payment Links** (not Subscriptions/autopay). A user taps a plan in
`/plans` → the bot creates a Razorpay hosted checkout link → on payment,
Razorpay fires a `payment_link.paid` webhook → a **separate FastAPI process**
verifies the signature and activates the subscription in the shared SQLite DB.

## Pieces
| File | Role |
|---|---|
| `razorpay_client.py` | `create_payment_link(uid, plan)` — POST to Razorpay, returns checkout URL. `notes` carry the Telegram uid + plan. |
| `webhook.py` | FastAPI app. `POST /razorpay/webhook` — HMAC-SHA256 sig-verify over the raw body, idempotent activation. |
| `storage.py` | `subscriptions` + `payments_log` tables; `subscription_status()`, `activate_subscription()`, `record_payment_event()` (idempotency), pure `compute_status()`. |
| `bot.py` | `plan:*` buttons → payment link; `/subscription` status; `requires_subscription` gate (wired, applied to real data in Phase 3). |

## Config (`.env`, gitignored)
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` — TEST keys (already set).
- `RAZORPAY_WEBHOOK_SECRET` — paste after registering the webhook (below). Empty ⇒ every event rejected.
- Optional: `PLAN_MONTHLY_DAYS` (30), `PLAN_YEARLY_DAYS` (365), `SUBSCRIPTION_GRACE_DAYS` (3), `PLAN_MONTHLY_INR` (10), `PLAN_YEARLY_INR` (99).

## Test (offline, no network)
```
cd pnl-sentinel && .venv/Scripts/python.exe -m pytest e2e/test_webhook.py -q
```
Covers: sig-verify, activation, idempotency (no double-extend on retry),
forged-signature rejection, status/expiry rule.

## Live TEST-mode smoke (optional)
1. Run the webhook process:
   ```
   .venv/Scripts/python.exe -m uvicorn webhook:app --port 8000
   ```
2. Tunnel it (public HTTPS Razorpay can reach):
   ```
   cloudflared tunnel --url http://localhost:8000
   ```
3. Razorpay dashboard → **Settings → Webhooks → Add** →
   URL `https://<tunnel>/razorpay/webhook`, active event **`payment_link.paid`**,
   copy the **signing secret** → `.env` `RAZORPAY_WEBHOOK_SECRET` → restart the webhook process.
4. In the bot: `/plans` → tap a plan → **Pay** → complete the Razorpay **test**
   checkout (test UPI / card) → webhook fires → `/subscription` shows `Active`.

## Notes
- Bot (long-poll) and webhook are **two processes** sharing `pnl_sentinel.db`.
  Fine at this volume; Postgres at Phase 3 (`# ponytail:` in `webhook.py`).
- Host deploy deferred to go-live (Fly/Railway/Render).
- Broker/PnL commands stay `@owner_only` — subscription gating goes live on
  per-user data in Phase 3.
