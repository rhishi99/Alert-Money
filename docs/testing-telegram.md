# Telegram E2E testing harness

Drive @stockpulse_official_bot as a real Telegram **user** to test the onboarding
flow automatically (send `/start`, press inline buttons, assert each screen, and
confirm owner-gating). A bot can't talk to another bot, so this uses an MTProto
**user** client (Telethon) on a **dedicated test account**.

## One-time setup

1. **Dedicated test account** — use a throwaway Telegram number, NOT your main.
   The session grants full access to whatever account logs in. Being a non-owner,
   it also validates that strangers are blocked from `/status`.
2. **API creds** — https://my.telegram.org/apps → create an app → copy `api_id`
   and `api_hash`.
3. **Install dev deps:** `pnl-sentinel/.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`
4. **Mint a session string** (interactive login on the test account):
   ```
   python e2e/session_gen.py
   ```
5. **Put creds in `pnl-sentinel/.env`** (gitignored — never commit):
   ```
   TG_TEST_API_ID=...
   TG_TEST_API_HASH=...
   TG_TEST_SESSION=...        # from session_gen.py
   BOT_USERNAME=stockpulse_official_bot
   ```

## Run the harness

With the bot running:
```
python e2e/test_onboarding_e2e.py
```
Prints `ALL E2E CHECKS PASSED`, or a `SKIP` line if creds aren't set. It asserts:
welcome menu → Get Started → I Understand (T&C) → `/status` refused for non-owner.

## Optional: register the Telegram MCP (conversational testing)

To let the AI drive the bot ad-hoc during dev sessions, add
[chigwell/telegram-mcp](https://github.com/chigwell/telegram-mcp) (Telethon,
`press_inline_callback`). **Review the repo before trusting it with a session —
even a test account.** Clone it, then add to `.mcp.json`:

```json
{
  "mcpServers": {
    "telegram-test": {
      "command": "uv",
      "args": ["--directory", "/path/to/telegram-mcp", "run", "main.py"],
      "env": {
        "TELEGRAM_API_ID": "...",
        "TELEGRAM_API_HASH": "...",
        "TELEGRAM_SESSION_STRING": "..."
      }
    }
  }
}
```
> Not added to the live `.mcp.json` yet — a server with a missing command/creds
> errors on every session load. Wire it once the clone + creds exist.

## Security
- `TG_TEST_*` and the session string are **secrets** → `.env`/SSM only, gitignored, never logged.
- Use a dedicated account so a leaked session can't touch your real Telegram.
