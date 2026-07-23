"""Self-check for Phase 1 onboarding: owner-auth logic + Store onboarding
methods. No network, no Telegram Update objects, no framework.

Run: python test_onboarding.py
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from bot import is_owner
from storage import Store

OWNER = 111
STRANGER = 999


def test_is_owner():
    assert is_owner(OWNER, OWNER) is True
    assert is_owner(STRANGER, OWNER) is False
    print("PASS is_owner: owner chat allowed, stranger chat rejected")


async def fresh_store():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.remove(path)
    s = Store(path); await s.init()
    return s, path


async def test_onboarding_persistence():
    s, path = await fresh_store()
    try:
        # fresh user has not accepted
        assert await s.has_accepted(OWNER) is False

        await s.mark_started(OWNER)
        assert await s.has_accepted(OWNER) is False, "mark_started must not imply acceptance"

        await s.accept_tnc(OWNER)
        assert await s.has_accepted(OWNER) is True

        # a different, untouched uid is unaffected
        assert await s.has_accepted(STRANGER) is False

        # idempotent: calling mark_started/accept_tnc again does not error
        await s.mark_started(OWNER)
        await s.accept_tnc(OWNER)
        assert await s.has_accepted(OWNER) is True
    finally:
        os.remove(path)
    print("PASS onboarding: mark_started/accept_tnc/has_accepted round-trip")


async def main():
    test_is_owner()
    await test_onboarding_persistence()
    print("\nALL 2 TESTS PASSED")


asyncio.run(main())
