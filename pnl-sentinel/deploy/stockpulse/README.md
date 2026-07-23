# StockPulse — AWS provisioning runbook

Amazon Linux 2023, systemd. Two long-running processes (bot + webhook) plus
Caddy for HTTPS termination.

## a) Launch the instance

- t3.micro (free-tier) or t4g.nano, region **ap-south-1**.
- Attach an IAM role granting:
  - `ssm:GetParameter`, `ssm:GetParameters`, `ssm:GetParametersByPath`
  - scoped to resource `arn:aws:ssm:ap-south-1:<account-id>:parameter/stockpulse/*`
- Allocate + associate an Elastic IP (needed for the DNS A-record in step f).
- Security group: allow inbound 80/443 from anywhere, 22 from your IP.

## b) Install base packages

```bash
sudo dnf install -y python3.12 git caddy jq
```

(`aws` CLI v2 ships pre-installed on AL2023 AMIs; install it manually if not.)

## c) Create the app user and checkout

```bash
sudo useradd -r -m -d /opt/stockpulse -s /sbin/nologin stockpulse
sudo -u stockpulse git clone <this-repo-url> /tmp/alert-money
sudo -u stockpulse cp -r /tmp/alert-money/pnl-sentinel/. /opt/stockpulse/
cd /opt/stockpulse
sudo -u stockpulse python3.12 -m venv .venv
sudo -u stockpulse .venv/bin/pip install -r requirements.txt
```

## d) Put secrets in SSM

Under path prefix `/stockpulse/` (SecureString, region ap-south-1):

| Parameter | Notes |
|---|---|
| `/stockpulse/TELEGRAM_BOT_TOKEN` | |
| `/stockpulse/TELEGRAM_CHAT_ID` | |
| `/stockpulse/KITE_API_KEY` | |
| `/stockpulse/KITE_API_SECRET` | |
| `/stockpulse/DHAN_CLIENT_ID` | |
| `/stockpulse/RAZORPAY_KEY_ID` | |
| `/stockpulse/RAZORPAY_KEY_SECRET` | |
| `/stockpulse/RAZORPAY_WEBHOOK_SECRET` | |
| `/stockpulse/STOCKPULSE_MASTER_KEY` | encryption master key |
| `/stockpulse/DHAN_TOKEN_SSM_PARAM` | pointer to NxBagger's SSM param, e.g. `/nxbagger/DHAN_ACCESS_TOKEN` — StockPulse never mints its own Dhan token |

`fetch_secrets.sh` (this dir) pulls everything under `/stockpulse/` and writes
`/opt/stockpulse/.env` as `KEY=value` (basename of the param path → env var
name), `chmod 600`. It runs as `ExecStartPre` on both units, so it re-syncs
on every start/restart.

```bash
sudo cp fetch_secrets.sh /opt/stockpulse/deploy/stockpulse/fetch_secrets.sh
sudo chmod +x /opt/stockpulse/deploy/stockpulse/fetch_secrets.sh
```

## e) Install and start the systemd units

```bash
sudo cp stockpulse-bot.service stockpulse-webhook.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stockpulse-bot stockpulse-webhook
sudo systemctl status stockpulse-bot stockpulse-webhook
```

## f) Caddy + DNS

1. Point the domain's DNS A-record at the instance's Elastic IP.
2. Edit `Caddyfile`, replace `stockpulse.example.com` with the real domain.
3. `sudo cp Caddyfile /etc/caddy/Caddyfile`
4. `sudo systemctl enable --now caddy` (or `sudo systemctl reload caddy` if already running).

## g) Register webhook URLs

Once `https://<domain>` resolves and serves TLS:

- **Telegram**: set the bot webhook / confirm long-poll mode is intended (this
  deployment runs `bot.py` as long-poll, not a Telegram webhook — no
  registration needed for Telegram itself).
- **Razorpay**: set the webhook URL to `https://<domain>/razorpay/webhook`
  with the same secret as `/stockpulse/RAZORPAY_WEBHOOK_SECRET`.
- **Zerodha** (Phase 3b): set the app redirect/callback URL to
  `https://<domain>/zerodha/callback`.
