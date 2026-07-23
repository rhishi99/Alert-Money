# Decision: host on AWS EC2 t4g.nano (ap-south-1)

**Date:** 2026-07-23. Researched via two subagents (hosting pricing + alert delivery).

## Choice
Host PnL Sentinel on **AWS EC2 `t4g.nano`, ap-south-1**, under systemd
(`Restart=always`), **IAM instance role** for SSM. ~$3/mo (~₹255). **Zero rewrite.**

## Why (not the alternatives)
- **Zero rewrite** — bot already long-polling + SQLite + 15s scheduler; EC2 runs `bot.py` as-is.
- **SSM without keys on disk** — EC2 instance role reads `/nxbagger/DHAN_ACCESS_TOKEN` (see [[dhan-token-read-from-ssm]]). Non-AWS hosts would need AWS access keys stored on the box — the deciding factor.
- **Same region** as SSM + brokers (Mumbai).

## Rejected
- **Oracle Always-Free** — idle-reclaim risk (near-zero CPU bot flagged/killed after ~7d); bad for a financial watchdog.
- **Fly / Railway / Render** — no real free tier in 2026; AWS-keys-on-disk problem.
- **Serverless (Lambda + EventBridge + DynamoDB)** — needs webhook + SQLite→DynamoDB rewrite. NOT blocked by EventBridge's 1-min floor (a human alert bot is fine at 60s), just not worth the rewrite to save $3. Revisit only if idle cost matters.

## Alert delivery
Keep **Telegram** (already push-notifies Android+iOS, free). A Flutter+FCM app is
strictly more work ($99/yr Apple, APNs, FCM-send integration, iOS distribution
treadmill) for the same outcome — build only for a branded dashboard, not alerts.
Pushover ($4.99 once) is the only justified upgrade if Telegram noise bugs the user.

## Open operational wart
Zerodha daily interactive token — on headless VM: SSH in, run login-url step,
open URL on laptop, paste request_token back. ~30s each morning. Dhan needs
nothing (SSM auto-refreshed by deployed NxBagger). Automate this only if it annoys.

## Build
Handed to executor on branch `deploy/ec2-hosting`: config.py SSM dual-path
(`DHAN_TOKEN_SSM_PARAM`), boto3 dep, `deploy/` (systemd unit, IAM policy,
setup.sh, deploy.md runbook). Deploy artifacts only — no live provisioning.
