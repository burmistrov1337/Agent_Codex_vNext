#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/max_bot/app}"
ENV_FILE="${ENV_FILE:-/opt/max_bot/.env}"
PYTHON_BIN="${PYTHON_BIN:-/opt/max_bot/venv/bin/python}"
DEFAULT_DB_PATH="$APP_ROOT/max_bot/data/bot.db"

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

chat_id="${MAX_REQUIRED_CHAT_ID:-}"
if [[ -z "$chat_id" ]]; then
  echo "MAX_REQUIRED_CHAT_ID is missing in $ENV_FILE" >&2
  exit 1
fi

count="${MAX_INSTRUCTION_REFRESH_COUNT:-100}"
batches="${MAX_INSTRUCTION_REFRESH_BATCHES:-10}"
db_path="${MAX_BOT_DB_PATH:-$DEFAULT_DB_PATH}"
sheet_channel_id="${MAX_INSTRUCTION_SHEET_CHANNEL_ID:-max-browser-channel}"
sheet_channel_name="${MAX_INSTRUCTION_SHEET_CHANNEL_NAME:-Активы для косметики}"
date_tag="$(date -u +%F)"
output_dir="$APP_ROOT/generated/instruction_search/max_export_${date_tag}"
output_path="$output_dir/result.json"

mkdir -p "$output_dir"

"$PYTHON_BIN" scripts/fetch_max_channel_posts.py \
  --app-env server \
  --chat-id "$chat_id" \
  --count "$count" \
  --batches "$batches" \
  --output "$output_path"

"$PYTHON_BIN" scripts/import_instruction_posts.py \
  --platform max \
  --input "$output_path" \
  --channel-name "$sheet_channel_name" \
  --channel-id "$sheet_channel_id"

"$PYTHON_BIN" scripts/reindex_instruction_search.py \
  --platform max \
  --db-path "$db_path"
