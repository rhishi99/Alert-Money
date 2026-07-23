"""One-shot helper to generate the daily Zerodha Kite access token.

Kite Connect requires an interactive login once per trading day:
  1. This script prints a login URL — open it in a browser and log in.
  2. Zerodha redirects to your app's Redirect URL with ?request_token=XXX.
  3. Paste that request_token here; the script exchanges it for an
     access_token and writes it back into your .env automatically.

Run every morning before starting the bot:  python generate_kite_token.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("KITE_API_KEY", "")
API_SECRET = os.getenv("KITE_API_SECRET", "")
ENV_PATH = Path(".env")

if not API_KEY or not API_SECRET:
    sys.exit("Set KITE_API_KEY and KITE_API_SECRET in .env first.")

from kiteconnect import KiteConnect  # noqa: E402

kite = KiteConnect(api_key=API_KEY)
print("\n1) Open this URL, log in to Zerodha, complete 2FA:\n")
print("   " + kite.login_url())
print("\n2) After redirect, copy the `request_token` query param from the URL.\n")

request_token = input("Paste request_token: ").strip()
data = kite.generate_session(request_token, api_secret=API_SECRET)
access_token = data["access_token"]

# Write back into .env (replace existing line or append).
text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
if re.search(r"^KITE_ACCESS_TOKEN=.*$", text, flags=re.M):
    text = re.sub(r"^KITE_ACCESS_TOKEN=.*$", f"KITE_ACCESS_TOKEN={access_token}",
                  text, flags=re.M)
else:
    text += f"\nKITE_ACCESS_TOKEN={access_token}\n"
ENV_PATH.write_text(text)

print(f"\n✅ access_token saved to .env for user {data.get('user_id')}.")
print("   Valid until ~6:00 AM IST tomorrow. Start the bot:  python bot.py")
