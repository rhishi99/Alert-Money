"""Razorpay webhook receiver — FastAPI, runs as its own process.

    .venv/Scripts/python.exe -m uvicorn webhook:app --port 8000

Shares the SAME SQLite DB as bot.py (settings.db_path). On a verified
`payment_link.paid`, it activates the payer's subscription. Signature is
HMAC-SHA256 over the RAW request body with RAZORPAY_WEBHOOK_SECRET.

# ponytail: one SQLite file shared by bot + webhook is fine at this volume;
# move to Postgres at Phase 3 if concurrency actually bites.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from config import settings
from razorpay_client import PLANS
from storage import Store

log = logging.getLogger("stockpulse-webhook")

store = Store(settings.db_path)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await store.init()  # idempotent CREATE TABLE IF NOT EXISTS
    yield


app = FastAPI(title="StockPulse Razorpay webhook", lifespan=_lifespan)


def _valid_signature(body: bytes, sig: str) -> bool:
    """Constant-time compare of HMAC-SHA256(body, secret) against the header."""
    secret = settings.razorpay_webhook_secret
    if not secret or not sig:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@app.post("/razorpay/webhook")
async def razorpay_webhook(request: Request) -> Response:
    body = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    if not _valid_signature(body, sig):
        log.warning("Rejected webhook: bad/missing signature")  # never log the body
        return Response(status_code=400, content='{"error":"bad signature"}',
                        media_type="application/json")

    event = json.loads(body)
    if event.get("event") != "payment_link.paid":
        return {"ok": True, "ignored": event.get("event")}  # ack other events, do nothing

    # Idempotency key: Razorpay's event id is stable across retries.
    event_id = request.headers.get("X-Razorpay-Event-Id") or event.get("id") or ""
    entity = event["payload"]["payment_link"]["entity"]
    notes = entity.get("notes") or {}
    uid = int(notes.get("telegram_user_id", 0))
    plan = notes.get("plan", "")
    amount_inr = int(entity.get("amount", 0)) // 100

    if uid <= 0 or plan not in PLANS:
        log.warning("Paid webhook missing/invalid notes (uid=%s plan=%s)", uid, plan)
        return {"ok": True, "ignored": "bad notes"}  # ack — retrying won't fix it

    fresh = await store.record_payment_event(event_id, uid, "payment_link.paid", amount_inr)
    if not fresh:
        return {"ok": True, "duplicate": event_id}  # already processed

    _amt, _label, days = PLANS[plan]
    period_end = time.time() + days * 86400
    await store.activate_subscription(uid, plan, period_end, entity.get("id", ""))
    log.info("Activated %s subscription for user %s (%d days)", plan, uid, days)
    return {"ok": True}
