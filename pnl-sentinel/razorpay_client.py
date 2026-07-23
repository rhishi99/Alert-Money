"""Razorpay Payment Links — thin httpx wrapper (no SDK).

Phase 2 uses one-shot Payment Links (not Subscriptions): create a hosted
checkout link per billing cycle; the `notes` carry the Telegram user id + plan
so the webhook can map the payment back to the user. TEST mode throughout —
keys come from config (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET).
"""
from __future__ import annotations

import time

import httpx

from config import settings

_API = "https://api.razorpay.com/v1/payment_links"

# plan slug -> (amount in INR, human label, validity days)
PLANS = {
    "monthly": (settings.plan_monthly_inr, "StockPulse Monthly", settings.plan_monthly_days),
    "yearly": (settings.plan_yearly_inr, "StockPulse Yearly", settings.plan_yearly_days),
}


async def create_payment_link(uid: int, plan: str) -> str:
    """Create a Razorpay Payment Link, return its short_url. Raises on failure."""
    if plan not in PLANS:
        raise ValueError(f"unknown plan {plan!r}")
    amount_inr, label, _days = PLANS[plan]
    payload = {
        "amount": amount_inr * 100,  # Razorpay works in paise
        "currency": "INR",
        "accept_partial": False,
        "description": label,
        "reference_id": f"sp_{uid}_{plan}_{int(time.time())}",  # unique per attempt
        "notes": {"telegram_user_id": str(uid), "plan": plan},
        "reminder_enable": True,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _API, json=payload,
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
        )
    resp.raise_for_status()
    return resp.json()["short_url"]
