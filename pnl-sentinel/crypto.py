"""App-managed encryption for per-user broker tokens (Phase 3).

AES-256-GCM (authenticated) with a single master key. Master key source, in
priority order:
  1. SSM SecureString param named by env STOCKPULSE_MASTER_KEY_SSM_PARAM
     (production — same boto3 pattern as config.resolve_dhan_token).
  2. env STOCKPULSE_MASTER_KEY  (local dev) — base64 of exactly 32 bytes.

Ciphertext blob layout:  nonce(12 bytes) || AES-256-GCM(ciphertext + 16-byte tag)

Honest ceiling (see architecture.md §2): the bot must decrypt tokens in memory
to call brokers, so an operator with server root can read runtime plaintext
regardless of where the key lives. This module keeps tokens as ciphertext AT
REST and never logs plaintext or the key — that is the guarantee it provides.

    python crypto.py            # run self-test (round-trip + tamper detection)
    python crypto.py --genkey   # print a fresh base64 master key for SSM/.env
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12
_KEY_LEN = 32  # AES-256
_key_cache: bytes | None = None


def _load_master_key() -> bytes:
    """Resolve + cache the 32-byte master key. Raises if unavailable/malformed."""
    global _key_cache
    if _key_cache is not None:
        return _key_cache

    raw_b64 = ""
    param = os.getenv("STOCKPULSE_MASTER_KEY_SSM_PARAM", "").strip()
    if param:
        region = (os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
                  or "ap-south-1")
        import boto3  # lazy — only when SSM is actually used
        client = boto3.client("ssm", region_name=region)
        raw_b64 = client.get_parameter(Name=param, WithDecryption=True)["Parameter"]["Value"]
    else:
        raw_b64 = os.getenv("STOCKPULSE_MASTER_KEY", "").strip()

    if not raw_b64:
        raise RuntimeError(
            "No master key: set STOCKPULSE_MASTER_KEY (base64 32 bytes) for local "
            "dev, or STOCKPULSE_MASTER_KEY_SSM_PARAM for production. "
            "Generate one with: python crypto.py --genkey")
    try:
        key = base64.b64decode(raw_b64, validate=True)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Master key is not valid base64") from e
    if len(key) != _KEY_LEN:
        raise RuntimeError(f"Master key must be {_KEY_LEN} bytes (got {len(key)})")
    _key_cache = key
    return key


def encrypt(plaintext: str) -> bytes:
    """Return nonce||ciphertext+tag for a UTF-8 string. Fresh random nonce each call."""
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_load_master_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ct


def decrypt(blob: bytes) -> str:
    """Inverse of encrypt. Raises cryptography.exceptions.InvalidTag if tampered."""
    if len(blob) <= _NONCE_LEN:
        raise ValueError("ciphertext blob too short")
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    return AESGCM(_load_master_key()).decrypt(nonce, ct, None).decode("utf-8")


def generate_key_b64() -> str:
    """Fresh base64-encoded 32-byte key for STOCKPULSE_MASTER_KEY / SSM."""
    return base64.b64encode(os.urandom(_KEY_LEN)).decode("ascii")


def _selftest() -> None:
    # Use an ephemeral key so the test needs no env/SSM configured.
    global _key_cache
    _key_cache = base64.b64decode(generate_key_b64())

    secret = "kite_access_token_abc123::live"
    blob = encrypt(secret)
    assert blob[:_NONCE_LEN] != blob[_NONCE_LEN:_NONCE_LEN * 2], "nonce not prepended?"
    assert decrypt(blob) == secret, "round-trip failed"
    assert encrypt(secret) != encrypt(secret), "nonce must randomize ciphertext"

    from cryptography.exceptions import InvalidTag
    tampered = bytearray(blob)
    tampered[-1] ^= 0x01  # flip one bit of the tag/ciphertext
    try:
        decrypt(bytes(tampered))
        raise AssertionError("tampered blob decrypted — GCM auth NOT enforced!")
    except InvalidTag:
        pass
    print("crypto self-test OK: round-trip + random-nonce + tamper-detection")


if __name__ == "__main__":
    import sys
    if "--genkey" in sys.argv:
        print(generate_key_b64())
    else:
        _selftest()
