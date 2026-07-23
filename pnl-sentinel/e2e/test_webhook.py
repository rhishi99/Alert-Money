"""Offline self-check for the Razorpay webhook — no network, no real Razorpay.

Run:  cd pnl-sentinel && .venv/Scripts/python.exe -m pytest e2e/test_webhook.py -q

Proves the money path: signature verification, activation, idempotency (no
double-extend on retry), rejection of forged payloads, and the pure
status/expiry rule.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

import webhook
from config import settings
from storage import Store, compute_status

TEST_SECRET = "whsec_test_12345"
UID = 468500661


def _setup(tmp_db: str) -> TestClient:
    # frozen dataclass — bypass to inject a known webhook secret for signing.
    object.__setattr__(settings, "razorpay_webhook_secret", TEST_SECRET)
    webhook.store = Store(tmp_db)  # isolate from the real bot DB
    asyncio.run(webhook.store.init())  # create tables (lifespan doesn't run w/o context mgr)
    return TestClient(webhook.app)


def _paid_body(event_id: str, plan: str = "monthly", amount_inr: int = 10) -> bytes:
    payload = {
        "id": event_id,
        "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {
            "id": "plink_xyz",
            "amount": amount_inr * 100,
            "notes": {"telegram_user_id": str(UID), "plan": plan},
        }}},
    }
    return json.dumps(payload).encode()


def _sign(body: bytes, secret: str = TEST_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _post(client: TestClient, body: bytes, sig: str, event_id: str):
    return client.post("/razorpay/webhook", content=body, headers={
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": event_id,
        "Content-Type": "application/json",
    })


def test_paid_activates_and_is_idempotent(tmp_path):
    db = str(tmp_path / "t.db")
    client = _setup(db)
    store = webhook.store

    body = _paid_body("evt_1")
    r = _post(client, body, _sign(body), "evt_1")
    assert r.status_code == 200 and r.json()["ok"] is True

    sub = asyncio.run(store.get_subscription(UID))
    assert sub is not None and sub["plan"] == "monthly"
    first_end = sub["current_period_end"]
    assert abs(first_end - (time.time() + 30 * 86400)) < 120  # ~30 days out

    # Retry the SAME event id → duplicate, period_end must NOT extend.
    r2 = _post(client, body, _sign(body), "evt_1")
    assert r2.status_code == 200 and r2.json().get("duplicate") == "evt_1"
    assert asyncio.run(store.get_subscription(UID))["current_period_end"] == first_end


def test_bad_signature_rejected(tmp_path):
    db = str(tmp_path / "t.db")
    client = _setup(db)
    body = _paid_body("evt_forged")
    r = _post(client, body, _sign(body, "wrong_secret"), "evt_forged")
    assert r.status_code == 400
    assert asyncio.run(webhook.store.get_subscription(UID)) is None  # nothing written


def test_status_and_expiry_rule():
    now = 1_000_000.0
    end = now + 30 * 86400
    assert compute_status(end, 3, now) == "active"
    assert compute_status(end, 3, end + 86400) == "grace"          # 1 day past, within grace
    assert compute_status(end, 3, end + 4 * 86400) == "expired"    # past period + 3d grace


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
