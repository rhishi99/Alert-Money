"""Razorpay webhook receiver — FastAPI, runs as its own process.

    .venv/Scripts/python.exe -m uvicorn webhook:app --port 8000

Shares the SAME SQLite DB as bot.py (settings.db_path). On a verified
`payment_link.paid`, it activates the payer's subscription. Signature is
HMAC-SHA256 over the RAW request body with RAZORPAY_WEBHOOK_SECRET.

# ponytail: one SQLite file shared by bot + webhook is fine at this volume;
# move to Postgres at Phase 3 if concurrency actually bites.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

import crypto
import zerodha_auth
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


async def _notify_user(uid: int, text: str) -> None:
    """Best-effort Telegram ping from the webhook process (no bot instance here)."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(
                f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                json={"chat_id": uid, "text": text, "parse_mode": "Markdown"},
            )
    except Exception:  # noqa: BLE001 — a failed ping must not fail the callback
        log.warning("Telegram notify failed for user %s", uid)


_DONE_HTML = ("<html><body style='font-family:sans-serif;text-align:center;margin-top:15%'>"
              "<h2>{icon} {msg}</h2><p>You can close this tab and return to Telegram.</p>"
              "</body></html>")


@app.get("/zerodha/callback")
async def zerodha_callback(request: Request) -> HTMLResponse:
    """Kite redirects here after login. Map state->uid, exchange request_token
    for an access_token, encrypt + store it. api_secret never leaves the server."""
    qp = request.query_params
    request_token = qp.get("request_token", "")
    status = qp.get("status", "")
    uid = await store.pop_pending_login(qp.get("state", ""))

    if status != "success" or not request_token:
        return HTMLResponse(_DONE_HTML.format(icon="⚠️", msg="Login cancelled or failed — retry from Telegram."))
    if not uid:
        return HTMLResponse(_DONE_HTML.format(icon="⏳", msg="This login link expired — start Connect again in Telegram."))
    try:
        access_token = await asyncio.to_thread(
            zerodha_auth.exchange, settings.kite_api_key, settings.kite_api_secret, request_token)
    except Exception:  # noqa: BLE001 — never leak Kite/SDK errors to the browser
        log.warning("Zerodha token exchange failed for user %s", uid, exc_info=True)
        return HTMLResponse(_DONE_HTML.format(icon="⚠️", msg="Could not complete Zerodha login — retry from Telegram."))

    await store.save_broker_conn(uid, "zerodha", crypto.encrypt(access_token))
    log.info("Zerodha connected for user %s", uid)
    await _notify_user(uid, "✅ *Zerodha connected!* Your PnL is now being monitored. "
                             "Set a target with /setalert, or check /mypnl.")
    return HTMLResponse(_DONE_HTML.format(icon="✅", msg="Zerodha connected!"))
