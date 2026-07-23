# StockPulse — Product Architecture & Phased Plan

Turning the single-user PnL Sentinel into a **public, multi-tenant, paid**
Telegram bot (@stockpulse_official_bot). BYO-broker: each subscriber connects
their own Zerodha/Dhan. Built standalone in this repo.

Status: **DESIGN — not yet built.** Decisions locked: BYO-broker multi-tenant,
phased delivery, hosting chosen at end of this doc.

---

## 1. What changes vs today

| Aspect | Today (v0.1) | Target |
|---|---|---|
| Users | 1 (owner) | many (public) |
| Broker tokens | owner's, in `.env`/SSM | each user's, **encrypted per-user** |
| State | SQLite, 1 row | **Postgres**, multi-tenant |
| Telegram | long-poll, single chat gate | webhook, per-user routing, inline buttons |
| Access | open to owner | **gated by subscription** (₹10/mo, ₹99/yr) |
| Payments | none | **Razorpay** UPI/subscriptions |
| Hosting | EC2 nano, outbound-only | needs **inbound HTTPS** (2 webhooks) + Postgres |

---

## 2. Security model (the "not visible to me" question — honestly)

**What we guarantee:**
- Broker tokens stored **only as ciphertext** — envelope encryption via AWS KMS
  (per-user data key). Plaintext exists only transiently in process memory when
  a broker call is made.
- Tokens/PII **never logged, never printed, never in error messages** to the
  operator or to Telegram.
- **Zero card/UPI data touches us** — Razorpay-hosted checkout; we store only a
  Razorpay customer/subscription id + status.
- DB access is least-privilege; secrets in KMS/SSM, never in the repo.

**The honest ceiling:** the bot must decrypt tokens in memory to act on the
user's behalf, so an operator with server root could *in principle* intercept
plaintext at runtime. True operator-zero-knowledge is infeasible for a bot that
trades/monitors for the user. We minimize exposure; we don't claim impossibility.

**Regulatory (must resolve before charging):** public *paid* stock alerts in
India may trigger SEBI Research Analyst / Investment Adviser rules. Mandatory:
clear disclaimer ("not investment advice", "informational only", "verify with
your broker") + a disclosure/T&C the user accepts at onboarding. **Not legal
advice — get a professional opinion before go-live.**

---

## 3. Data model (Postgres)

```
users            (telegram_user_id PK, created_at, tnc_accepted_at, state)
subscriptions    (user_id FK, plan {monthly,yearly}, status {active,grace,expired},
                  razorpay_sub_id, current_period_end, updated_at)
broker_conns     (id PK, user_id FK, broker {zerodha,dhan}, enc_token BYTEA,
                  enc_dek BYTEA, token_expiry, status, updated_at)   -- ciphertext only
alerts           (id PK, user_id FK, kind {profit,loss}, threshold, latched, updated_at)
payments_log     (id PK, user_id FK, razorpay_event, amount, status, ts)   -- no card data
```

All broker credentials live in `broker_conns.enc_token` (KMS-encrypted). No
plaintext token column exists anywhere.

---

## 4. Phases (ship + validate each)

### Phase 1 — Onboarding UX & brand (no payments, no multi-tenancy yet)
Buildable on the current bot immediately; de-risks UX + gets the brand live.
- `/start` → inline-keyboard welcome: **[🚀 Get Started] [💎 Plans] [❓ How it works] [📜 Disclaimer]**.
- Guided onboarding: what it does, connect-broker teaser, plan teaser, T&C accept.
- Disclaimer/disclosure screens (SEBI-safe copy).
- Brand: logo (in progress via agy), inline images/diagrams in onboarding.
- Menu-driven `/status`, `/plans`, `/help` with buttons instead of raw commands.
- **Still single-user under the hood** — subscribe/connect buttons show "coming soon" or route to Phase 2/3 stubs.
- Acceptance: a polished, button-driven onboarding a stranger can follow; disclaimer gate before any data.

### Phase 2 — Subscription & payments (Razorpay)
- Razorpay **Subscriptions** (UPI autopay mandate) for recurring, or Payment
  Links for one-shot — plans ₹10/mo, ₹99/yr, **amounts + plan set in config** (env/DB), easily changeable.
- Razorpay **webhook** (inbound HTTPS) → verify signature → update `subscriptions.status`.
- Access gate: only `active`/`grace` users get alerts; expired → renewal prompt.
- `/plans` → inline buttons → Razorpay checkout link → confirmation.
- Config: plan prices, grace-period days, free-trial length — all configurable.
- Acceptance: pay ₹10 in UPI test mode → status flips active → alerts unlock; expiry → locked.

### Phase 3 — Multi-tenant BYO-broker + encryption
- Per-user broker connect: Zerodha (Kite Connect login flow, request_token capture via redirect) + Dhan (headless TOTP or manual token).
- KMS envelope encryption on store; decrypt-in-memory on use; never log.
- Per-user monitor: one shared tick, fan out per subscribed user (no per-user API storm).
- Daily Zerodha token UX × N users (each user re-auths daily — inline-button flow).
- Migrate storage.py SQLite → Postgres, brokers.py → per-user token source.
- Acceptance: two different users connect different brokers, each sees only their own PnL; operator sees only ciphertext in DB.

---

## 5. Hosting recommendation (now that the surface is known)

Needs: **2 inbound HTTPS webhooks** (Telegram + Razorpay), a **Postgres** DB, an
always-on process, and access to **AWS KMS** (encryption).

**Recommended: a small FastAPI service + managed Postgres.**
- Telegram switches from long-polling to **webhook** (FastAPI route).
- Razorpay webhook = another FastAPI route (signature-verified).
- Host options (pick at Phase 2): **Fly.io / Railway / Render** (managed Postgres
  add-on, HTTPS out of the box, ~$5–12/mo) — simplest for webhooks. Or **AWS**
  (ECS Fargate/App Runner + RDS + native KMS) if you want everything in AWS and
  are willing to run more infra.
- The current EC2-nano/`deploy/` setup is retired for this product (outbound-only
  + SQLite no longer fit). Keep it only if you also want the old single-user bot.

**KMS note:** wherever it runs, it needs an AWS IAM principal with `kms:Encrypt/Decrypt`
on the StockPulse data key — clean on AWS (role), doable elsewhere via scoped keys.

---

## 6. Open items before Phase 2
- Razorpay account (business KYC) + test keys.
- Legal: disclaimer/T&C copy reviewed; SEBI applicability checked.
- Final host pick (Fly/Railway/Render vs AWS).
- Free trial? (config supports it; decide length or none.)

---

## 7. Immediate next step
Build **Phase 1** (onboarding UX + brand) on the current bot — no payments, no
DB migration, no regulatory blockers. Fastest visible progress, zero risk to the
working v0.1. Phases 2–3 begin once Razorpay + host + legal are settled.
