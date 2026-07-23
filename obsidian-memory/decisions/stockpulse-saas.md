# Decision: StockPulse public paid SaaS (BYO-broker, phased)

**Date:** 2026-07-23. Full design: [`docs/architecture.md`](../../docs/architecture.md).

## Direction (user-locked)
Turn single-user PnL Sentinel into a **public, paid, multi-tenant** Telegram bot
@stockpulse_official_bot. **BYO-broker**: each subscriber connects their own
Zerodha/Dhan; tokens **KMS-encrypted per-user**, never logged. Standalone in
this repo (NOT reusing NxBagger). **Phased** delivery. Hosting decided at design
end: **FastAPI + managed Postgres + webhooks** (Fly/Railway/Render or AWS) —
retires the EC2-nano/SQLite/outbound-only design for this product.

## Phases
1. Onboarding UX + brand (inline buttons, /start flow, disclaimer, logo) — no payments/DB, build now.
2. Razorpay subscription (₹10/mo, ₹99/yr, configurable) + webhook + access gating.
3. Multi-tenant BYO-broker connect + KMS envelope encryption + per-user monitor; SQLite→Postgres.

## Hard constraints
- "No tokens visible to operator" has a ceiling: encrypted-at-rest + never-logged
  + Razorpay-hosted payments, but the process decrypts in memory to act — true
  operator-zero-knowledge infeasible. Ceiling stated to user.
- Regulatory: public paid stock alerts brush SEBI RA/IA rules — disclaimer + T&C
  mandatory, get legal opinion before go-live. Not resolved yet.
- Open before Phase 2: Razorpay KYC + keys, legal copy, host pick, trial length.

Logo generation in progress via agy (Imagen) → `brand/logo/`.
