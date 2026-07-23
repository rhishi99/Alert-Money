"""Central configuration — loads and validates the .env file once."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # reads .env from the working directory


def _bool(key: str, default: str = "true") -> bool:
    return os.getenv(key, default).strip().lower() in {"1", "true", "yes", "on"}


def resolve_dhan_token(env: dict) -> str:
    """Pure resolution: SSM (if configured) wins, else plain env var.

    `env` is a mapping like os.environ — takes a dict so this is testable
    without touching real env vars or the network.
    """
    param = env.get("DHAN_TOKEN_SSM_PARAM", "").strip()
    if not param:
        return env.get("DHAN_ACCESS_TOKEN", "")

    region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "ap-south-1"
    region = env.get("DHAN_SSM_REGION", "").strip() or region
    try:
        import boto3  # lazy import — only needed when SSM is actually used
        client = boto3.client("ssm", region_name=region)
        resp = client.get_parameter(Name=param, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception as e:  # noqa: BLE001 — never let SSM take the bot down
        print(f"WARN: failed to fetch Dhan token from SSM param {param!r} "
              f"({e}); falling back to DHAN_ACCESS_TOKEN env var.")
        return env.get("DHAN_ACCESS_TOKEN", "")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    telegram_chat_id: int

    kite_api_key: str
    kite_api_secret: str
    kite_access_token: str

    dhan_client_id: str
    dhan_access_token: str

    poll_interval: int
    enable_zerodha: bool
    enable_dhan: bool
    db_path: str

    plan_monthly_inr: int
    plan_yearly_inr: int
    onboarding_img_dir: str


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        sys.exit("FATAL: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")

    s = Settings(
        telegram_token=token,
        telegram_chat_id=int(chat_id),
        kite_api_key=os.getenv("KITE_API_KEY", ""),
        kite_api_secret=os.getenv("KITE_API_SECRET", ""),
        kite_access_token=os.getenv("KITE_ACCESS_TOKEN", ""),
        dhan_client_id=os.getenv("DHAN_CLIENT_ID", ""),
        dhan_access_token=resolve_dhan_token(os.environ),
        poll_interval=max(5, int(os.getenv("POLL_INTERVAL_SECONDS", "15"))),
        enable_zerodha=_bool("ENABLE_ZERODHA"),
        enable_dhan=_bool("ENABLE_DHAN"),
        db_path=os.getenv("DB_PATH", "pnl_sentinel.db"),
        plan_monthly_inr=int(os.getenv("PLAN_MONTHLY_INR", "10")),
        plan_yearly_inr=int(os.getenv("PLAN_YEARLY_INR", "99")),
        onboarding_img_dir=os.getenv("ONBOARDING_IMG_DIR", "../brand/onboarding"),
    )

    if s.enable_zerodha and not (s.kite_api_key and s.kite_access_token):
        print("WARN: Zerodha enabled but KITE_API_KEY / KITE_ACCESS_TOKEN missing "
              "— run `python generate_kite_token.py` first. Zerodha will be skipped.")
    if s.enable_dhan and not (s.dhan_client_id and s.dhan_access_token):
        print("WARN: Dhan enabled but DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN missing "
              "— Dhan will be skipped.")
    return s


settings = load_settings()
