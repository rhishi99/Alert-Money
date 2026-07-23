# /agy:ask — Delegate a prompt to Antigravity (agy)

Use the bash tool to run the following command and return its output:

```bash
python scripts/agy_pty_bridge.py "$ARGUMENTS"
```

Why the bridge: `agy -p` suppresses stdout when not attached to a real TTY
(upstream issue #76). `scripts/agy_pty_bridge.py` allocates a fresh Windows
ConPTY via pywinpty so agy sees a real tty and emits normally; the bridge
strips ANSI/TUI chrome and prints the clean response.

- Exit 0 = non-empty response captured. Exit 1 = empty/error (the bridge
  prints the reason to stderr).
- Timeout override: set `AGY_BRIDGE_TIMEOUT` (seconds, default 180).
- If pywinpty is missing: `python -m pip install pywinpty`.

Show the full response from Antigravity to the user.
