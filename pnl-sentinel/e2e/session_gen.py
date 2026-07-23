"""One-time helper: mint a Telethon session string for the DEDICATED test account.

Run interactively ONCE (it asks for a phone code / QR):

    python e2e/session_gen.py

Use a THROWAWAY test Telegram account, NOT your main — the session string grants
full read/write to whatever account logs in here. Paste the printed string into
your .env as TG_TEST_SESSION (gitignored, never commit).

Needs TG_TEST_API_ID / TG_TEST_API_HASH from https://my.telegram.org/apps.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

api_id = os.getenv("TG_TEST_API_ID") or input("TG_TEST_API_ID: ").strip()
api_hash = os.getenv("TG_TEST_API_HASH") or input("TG_TEST_API_HASH: ").strip()

with TelegramClient(StringSession(), int(api_id), api_hash) as client:
    session = client.session.save()
    me = client.get_me()
    print("\nLogged in as:", me.username or me.first_name, f"(id {me.id})")
    print("\nAdd this to your .env (keep it secret):\n")
    print(f"TG_TEST_SESSION={session}\n")
