"""Offline self-check for multi-tenant broker connections in storage.py — no
network, temp sqlite db per test.

Run:  cd pnl-sentinel && .venv/Scripts/python.exe -m pytest e2e/test_storage_multitenant.py -q
"""
from __future__ import annotations

import asyncio
import time

from storage import Store

UID_A = 111
UID_B = 222
UID_C = 333


def _store(tmp_path) -> Store:
    db = str(tmp_path / "t.db")
    store = Store(db)
    asyncio.run(store.init())
    return store


def test_save_and_get_broker_conn_roundtrips(tmp_path):
    store = _store(tmp_path)
    token = b"\x00\x01ciphertext"
    asyncio.run(store.save_broker_conn(UID_A, "zerodha", token, extra='{"client_id":"abc"}'))

    conns = asyncio.run(store.get_broker_conns(UID_A))
    assert len(conns) == 1
    assert conns[0]["enc_token"] == token
    assert conns[0]["extra"] == '{"client_id":"abc"}'
    assert conns[0]["broker"] == "zerodha"


def test_save_broker_conn_upserts_not_duplicates(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.save_broker_conn(UID_A, "dhan", b"first"))
    asyncio.run(store.save_broker_conn(UID_A, "dhan", b"second"))

    conns = asyncio.run(store.get_broker_conns(UID_A))
    assert len(conns) == 1
    assert conns[0]["enc_token"] == b"second"


def test_delete_broker_conn(tmp_path):
    store = _store(tmp_path)
    asyncio.run(store.save_broker_conn(UID_A, "zerodha", b"tok"))
    asyncio.run(store.delete_broker_conn(UID_A, "zerodha"))

    assert asyncio.run(store.get_broker_conns(UID_A)) == []


def test_users_with_active_sub_and_brokers(tmp_path):
    store = _store(tmp_path)
    now = time.time()

    # A: active subscription + broker conn -> included
    asyncio.run(store.activate_subscription(UID_A, "monthly", now + 30 * 86400, "ref_a"))
    asyncio.run(store.save_broker_conn(UID_A, "zerodha", b"tok_a"))

    # B: broker conn but no subscription -> excluded
    asyncio.run(store.save_broker_conn(UID_B, "dhan", b"tok_b"))

    # C: active subscription but no broker conn -> excluded
    asyncio.run(store.activate_subscription(UID_C, "monthly", now + 30 * 86400, "ref_c"))

    uids = asyncio.run(store.users_with_active_sub_and_brokers(grace_days=3))
    assert uids == [UID_A]


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
