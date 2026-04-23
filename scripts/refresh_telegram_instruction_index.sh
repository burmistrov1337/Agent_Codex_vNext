#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/telegram_adk_bot/app}"
ENV_FILE="${ENV_FILE:-/opt/telegram_adk_bot/.env}"
PYTHON_BIN="${PYTHON_BIN:-/opt/telegram_adk_bot/.venv/bin/python}"
DEFAULT_DB_PATH="$APP_ROOT/telegram_adk_bot/data/bot.db"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$APP_ROOT"

channel_input="${TELEGRAM_REQUIRED_CHAT:-@ustore_active}"
channel_input="${channel_input#https://t.me/}"
channel_input="${channel_input#http://t.me/}"
channel_input="${channel_input#@}"
channel_input="${channel_input%/}"

pages="${TELEGRAM_INSTRUCTION_REFRESH_PAGES:-4}"
db_path="${TELEGRAM_ADK_DB_PATH:-$DEFAULT_DB_PATH}"
date_tag="$(date -u +%F)"
output_dir="$APP_ROOT/generated/instruction_search/telegram_export_${date_tag}"
output_path="$output_dir/public_result.json"

mkdir -p "$output_dir"

"$PYTHON_BIN" scripts/fetch_telegram_channel_posts.py \
  --channel "$channel_input" \
  --pages "$pages" \
  --output "$output_path"

"$PYTHON_BIN" scripts/import_instruction_posts.py \
  --platform telegram \
  --input "$output_path"

"$PYTHON_BIN" scripts/reindex_instruction_search.py \
  --platform telegram \
  --db-path "$db_path"
