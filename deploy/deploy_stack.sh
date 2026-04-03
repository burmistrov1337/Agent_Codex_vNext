#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

cd "${PROJECT_ROOT}"

mkdir -p .agent_codex .docker/n8n skills

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill secrets before starting the stack."
fi

docker compose build agent_codex_bot
docker compose pull n8n
docker compose up -d
docker compose ps
