"""Zerodha connect flow (Phase 3b), offline — no Kite, no Telegram, no network.

Covers the security-critical bits: pending-login state is one-time + TTL'd, the
login URL carries state, and the callback maps state->uid, exchanges (mocked),
and stores an ENCRYPTED token (never plaintext).
"""
from __future__ import annotations

import asyncio
import base64

from fastapi.testclient import TestClient

import crypto
import webhook
import zerodha_auth
from storage import Store


def _fresh_key():
    crypto._key_cache = base64.b64decode(crypto.generate_key_b64())


def test_login_url_carries_state():
    url = zerodha_auth.login_url("apikey123", "STATE_XYZ")
    assert "api_key=apikey123" in url
    assert "redirect_params=" in url and "STATE_XYZ" in url


def test_pending_login_one_time_and_ttl(tmp_path):
    store = Store(str(tmp_path / "p.db"))
    asyncio.run(store.init())
    asyncio.run(store.save_pending_login("s1", 4242))
    assert asyncio.run(store.pop_pending_login("s1")) == 4242      # consumed
    assert asyncio.run(store.pop_pending_login("s1")) is None      # one-time only
    # expired: ttl_sec=0 means anything older than "now" is gone
    asyncio.run(store.save_pending_login("s2", 7))
    assert asyncio.run(store.pop_pending_login("s2", ttl_sec=0)) is None


def _setup(tmp_db, monkey_exchange="zerodha_access_TOKEN_secret"):
    _fresh_key()
    webhook.store = Store(tmp_db)
    asyncio.run(webhook.store.init())
    # mock the blocking Kite exchange + the Telegram ping (no network in tests)
    zerodha_auth.exchange = lambda api_key, api_secret, request_token: monkey_exchange
    async def _noop(uid, text): pass
    webhook._notify_user = _noop
    return TestClient(webhook.app)


def test_callback_stores_encrypted_token(tmp_path):
    client = _setup(str(tmp_path / "w.db"))
    uid = 55501
    asyncio.run(webhook.store.save_pending_login("goodstate", uid))

    r = client.get("/zerodha/callback",
                   params={"request_token": "rt1", "status": "success", "state": "goodstate"})
    assert r.status_code == 200 and "connected" in r.text.lower()

    conns = asyncio.run(webhook.store.get_broker_conns(uid))
    assert len(conns) == 1 and conns[0]["broker"] == "zerodha"
    blob = conns[0]["enc_token"]
    assert b"zerodha_access_TOKEN_secret" not in blob, "PLAINTEXT token stored!"
    assert crypto.decrypt(blob) == "zerodha_access_TOKEN_secret"


def test_callback_rejects_unknown_state(tmp_path):
    client = _setup(str(tmp_path / "w.db"))
    r = client.get("/zerodha/callback",
                   params={"request_token": "rt", "status": "success", "state": "nope"})
    assert r.status_code == 200 and "expired" in r.text.lower()
    assert asyncio.run(webhook.store.get_broker_conns(99)) == []


def test_callback_rejects_failed_login(tmp_path):
    client = _setup(str(tmp_path / "w.db"))
    asyncio.run(webhook.store.save_pending_login("st", 1))
    r = client.get("/zerodha/callback", params={"status": "cancelled", "state": "st"})
    assert r.status_code == 200 and ("cancelled" in r.text.lower() or "failed" in r.text.lower())


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
