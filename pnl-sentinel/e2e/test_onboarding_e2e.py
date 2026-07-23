"""End-to-end onboarding test — drives @stockpulse_official_bot as a real Telegram
user (the dedicated NON-OWNER test account) and asserts the flow + owner-gating.

Run (after session_gen.py + .env setup, and with the bot running):

    python e2e/test_onboarding_e2e.py

Skips cleanly (exit 0) if TG_TEST_* creds are not configured, so it never breaks
an unconfigured checkout. Reads all creds from env — never hardcode/commit them.
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = os.getenv("TG_TEST_API_ID", "")
API_HASH = os.getenv("TG_TEST_API_HASH", "")
SESSION = os.getenv("TG_TEST_SESSION", "")
BOT = os.getenv("BOT_USERNAME", "stockpulse_official_bot")

if not (API_ID and API_HASH and SESSION):
    print("SKIP: set TG_TEST_API_ID / TG_TEST_API_HASH / TG_TEST_SESSION in .env "
          "(run e2e/session_gen.py first). See docs/testing-telegram.md.")
    sys.exit(0)


async def _newest(client, *, with_buttons=False):
    """Return the newest message from the bot (optionally one that has buttons)."""
    async for m in client.iter_messages(BOT, limit=8):
        if with_buttons and not m.buttons:
            continue
        return m
    return None


async def _refetch(client, msg_id):
    return (await client.get_messages(BOT, ids=msg_id))


def _assert_in(needle: str, msg, label: str):
    text = (getattr(msg, "message", None) or getattr(msg, "text", "") or "")
    assert needle.lower() in text.lower(), f"{label}: expected '{needle}' in:\n{text!r}"
    print(f"PASS {label}")


async def main() -> None:
    client = TelegramClient(StringSession(SESSION), int(API_ID), API_HASH)
    await client.start()
    try:
        # 1. /start → welcome menu (+ hero banner photo above it)
        await client.send_message(BOT, "/start")
        await asyncio.sleep(3)
        menu = await _newest(client, with_buttons=True)
        assert menu is not None, "no message with buttons after /start"
        _assert_in("Welcome to StockPulse", menu, "start: welcome menu")

        # 2. Press Get Started → getting-started screen (edited in place)
        await menu.click(data=b"nav:getstarted")
        await asyncio.sleep(2)
        gs = await _refetch(client, menu.id)
        _assert_in("Getting Started", gs, "button: get started")

        # 3. Press I Understand → T&C accepted screen
        await gs.click(data=b"nav:accept")
        await asyncio.sleep(2)
        acc = await _refetch(client, menu.id)
        _assert_in("Got it", acc, "button: accept T&C")

        # 4. Owner-gating: non-owner /status must be refused, never data
        await client.send_message(BOT, "/status")
        await asyncio.sleep(3)
        refusal = await _newest(client)
        _assert_in("personal command", refusal, "gating: /status refused for non-owner")

        print("\nALL E2E CHECKS PASSED")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
