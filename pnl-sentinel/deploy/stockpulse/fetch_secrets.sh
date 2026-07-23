#!/usr/bin/env bash
# Fetches StockPulse secrets from AWS SSM Parameter Store and materialises
# them into /opt/stockpulse/.env. Run as ExecStartPre before bot/webhook
# start (idempotent — safe to run from both units, overwrites .env each time).
set -euo pipefail

REGION="ap-south-1"
SSM_PATH="/stockpulse/"
ENV_FILE="/opt/stockpulse/.env"

command -v aws >/dev/null 2>&1 || { echo "aws CLI not found" >&2; exit 1; }
command -v jq  >/dev/null 2>&1 || { echo "jq not found" >&2; exit 1; }

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

next_token=""
: > "$tmp_file"
while :; do
  if [ -n "$next_token" ]; then
    resp="$(aws ssm get-parameters-by-path \
      --region "$REGION" \
      --path "$SSM_PATH" \
      --with-decryption \
      --recursive \
      --starting-token "$next_token")"
  else
    resp="$(aws ssm get-parameters-by-path \
      --region "$REGION" \
      --path "$SSM_PATH" \
      --with-decryption \
      --recursive)"
  fi

  echo "$resp" | jq -r '.Parameters[] | (.Name | split("/") | last) + "=" + .Value' >> "$tmp_file"

  next_token="$(echo "$resp" | jq -r '.NextToken // empty')"
  [ -n "$next_token" ] || break
done

mv "$tmp_file" "$ENV_FILE"
chmod 600 "$ENV_FILE"
trap - EXIT
