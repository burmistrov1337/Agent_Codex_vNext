#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

cd "${PROJECT_ROOT}"

echo "== Compose config =="
docker compose config >/dev/null

echo "== Runtime layout =="
mkdir -p .agent_codex .docker/n8n
test -d .agent_codex
test -d .docker/n8n

echo "== Doctor =="
docker compose run --rm agent_codex_bot python -m agent_codex.apps.cli.main doctor --project-root /app --json

echo "== Marketplace headless smoke =="
docker compose run --rm agent_codex_bot python -m agent_codex.apps.cli.main marketplace-watch --project-root /app --sample-data --headless
