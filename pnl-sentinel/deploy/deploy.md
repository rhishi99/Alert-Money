# Deploying PnL Sentinel to EC2 (ap-south-1)

Runbook for hosting the bot on a small always-on EC2 box. Long-polling
Telegram needs no inbound ports, so the instance can be fully outbound-only.

## 1. Launch the instance

- Instance type: **t4g.nano** (ARM64, Graviton — cheapest that runs the bot fine).
- AMI: **Ubuntu Server 24.04 LTS (ARM64)**.
- Region: **ap-south-1**.
- Security group: **no inbound rules**; allow all outbound (default). The bot
  only makes outbound HTTPS calls to Telegram/Kite/Dhan/SSM.
- Key pair: any you can SSH in with.

## 2. Create the IAM role

1. Create a policy from `deploy/iam-policy.json` (scoped to the two
   `/nxbagger/*` SSM params in this region).
2. Create an IAM role for EC2, attach that policy.
3. Attach the role to the instance (Actions → Security → Modify IAM role).
   No AWS access keys are ever stored on the box — the role provides
   credentials automatically via the instance metadata service.

## 3. Provision the box

SSH in, then:

```bash
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/rhishi99/Alert-Money.git /tmp/bootstrap
sudo bash /tmp/bootstrap/pnl-sentinel/deploy/setup.sh
```

`setup.sh` installs python3.12 + venv, clones/pulls the repo into
`/opt/pnl-sentinel`, creates the venv, installs `requirements.txt`, and
installs+enables the systemd unit. It does **not** create `.env` — do that
next.

## 4. Create `.env`

`/opt/pnl-sentinel/pnl-sentinel/.env` — same shape as `.env.example`, with
one difference: **no `DHAN_ACCESS_TOKEN` line**; instead set
`DHAN_TOKEN_SSM_PARAM` so the token comes from SSM via the instance role:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

KITE_API_KEY=...
KITE_API_SECRET=...
KITE_ACCESS_TOKEN=

DHAN_CLIENT_ID=...
DHAN_TOKEN_SSM_PARAM=/nxbagger/DHAN_ACCESS_TOKEN
DHAN_SSM_REGION=ap-south-1

POLL_INTERVAL_SECONDS=15
ENABLE_ZERODHA=true
ENABLE_DHAN=true
DB_PATH=pnl_sentinel.db
```

Make sure the two SSM params (`/nxbagger/DHAN_ACCESS_TOKEN`,
`/nxbagger/DHAN_TOKEN_EXPIRY`) already exist as SecureString in ap-south-1.

Then start/restart the service so it picks up the new `.env`:

```bash
sudo systemctl restart pnl-sentinel
```

## 5. Daily Zerodha token (SEBI requires interactive login)

Kite access tokens expire every day at ~6 AM IST. Do this over SSH each
trading morning, same flow as local dev but run on the box:

```bash
ssh ubuntu@<instance-ip>
cd /opt/pnl-sentinel/pnl-sentinel
source .venv/bin/activate
python generate_kite_token.py   # prints a login URL
```

Open the printed URL **on your laptop**, log in to Zerodha, copy the
`request_token` query param from the redirect URL, paste it back into the
SSH session. `generate_kite_token.py` writes `KITE_ACCESS_TOKEN` into the
box's `.env` for you. The service auto-restarts on failures (`Restart=always`)
but won't reload `.env` mid-run — restart it if you want the fresh token
picked up immediately:

```bash
sudo systemctl restart pnl-sentinel
```

## 6. Verify

```bash
systemctl status pnl-sentinel      # should show "active (running)"
journalctl -u pnl-sentinel -f      # tail live logs
```

In Telegram, `/status` should return live PnL from both brokers.
