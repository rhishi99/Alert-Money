"""Self-check for DhanBroker token auto-recover — no network, no frameworks.

Run: python test_dhan_recover.py
"""
from __future__ import annotations

import asyncio

from brokers import DhanBroker, PnLSnapshot


def test_is_token_error():
    assert DhanBroker._is_token_error(RuntimeError("{'error_code': 'DH-906', 'error_message': 'Invalid Token'}"))
    assert DhanBroker._is_token_error(Exception("Invalid Token"))
    assert not DhanBroker._is_token_error(Exception("connection reset by peer"))


def test_refresh_and_retry():
    b = DhanBroker("cid", "old-token", token_provider=lambda: "new-token")
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        if b.token == "old-token":
            raise RuntimeError("DH-906 Invalid Token")
        return PnLSnapshot(broker="Dhan", realized=5.0)

    b._fetch = fake_fetch
    snap = asyncio.run(b.snapshot())
    assert snap.ok and snap.realized == 5.0, snap
    assert b.token == "new-token"
    assert calls["n"] == 2, f"expected fail+retry, got {calls['n']} calls"


def test_no_provider_no_retry():
    b = DhanBroker("cid", "old-token", token_provider=None)

    def fake_fetch():
        raise RuntimeError("DH-906 Invalid Token")

    b._fetch = fake_fetch
    snap = asyncio.run(b.snapshot())
    assert not snap.ok and "DH-906" in snap.error


def test_same_token_no_pointless_retry():
    # provider returns the SAME (still-stale) token -> don't retry, just fail.
    b = DhanBroker("cid", "stale", token_provider=lambda: "stale")
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        raise RuntimeError("DH-906 Invalid Token")

    b._fetch = fake_fetch
    snap = asyncio.run(b.snapshot())
    assert not snap.ok
    assert calls["n"] == 1, "must not retry when refreshed token is unchanged"


if __name__ == "__main__":
    test_is_token_error()
    test_refresh_and_retry()
    test_no_provider_no_retry()
    test_same_token_no_pointless_retry()
    print("PASS")
