"""Zerodha Kite Connect login helpers (Phase 3b).

Per-user connect flow:
  1. bot builds `login_url(api_key, state)` -> user logs in on kite.zerodha.com.
  2. Kite redirects to our registered app URL with `request_token`, `status`,
     and our `state` echoed back via `redirect_params`.
  3. webhook `/zerodha/callback` maps state->uid, then `exchange()` swaps the
     request_token (+ api_secret) for a per-user `access_token`, which is
     encrypted (crypto.py) and stored. api_secret NEVER leaves the server.
"""
from __future__ import annotations

from urllib.parse import urlencode


def login_url(api_key: str, state: str) -> str:
    """Kite login URL carrying our opaque `state` through redirect_params.

    Kite appends redirect_params to the app's registered Redirect URL on
    success, so the callback receives `state` alongside `request_token`.
    """
    base = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
    return base + "&" + urlencode({"redirect_params": urlencode({"state": state})})


def exchange(api_key: str, api_secret: str, request_token: str) -> str:
    """Swap a one-time request_token for a durable access_token. Blocking HTTP
    (kiteconnect SDK) — call via asyncio.to_thread. Returns the access_token."""
    from kiteconnect import KiteConnect  # lazy import
    kite = KiteConnect(api_key=api_key)
    data = kite.generate_session(request_token, api_secret=api_secret)
    return data["access_token"]
