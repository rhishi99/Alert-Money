"""Self-check for config.resolve_dhan_token — no network, no frameworks.

Run: python test_config_ssm.py
"""
from __future__ import annotations

from config import resolve_dhan_token

# 1. No SSM param configured -> plain env var wins, unchanged from today's behavior.
env = {"DHAN_ACCESS_TOKEN": "dummy-env-token"}
assert resolve_dhan_token(env) == "dummy-env-token", "expected env-based token when SSM param unset"

# 2. Empty-string SSM param behaves the same as unset.
env = {"DHAN_TOKEN_SSM_PARAM": "", "DHAN_ACCESS_TOKEN": "dummy-env-token"}
assert resolve_dhan_token(env) == "dummy-env-token", "empty DHAN_TOKEN_SSM_PARAM must fall back to env"

# 3. Neither var set -> empty string, no crash.
assert resolve_dhan_token({}) == "", "expected empty string when nothing is set"

print("PASS")
