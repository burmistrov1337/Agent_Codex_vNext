#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

cd "${PROJECT_ROOT}"

echo "== Docker Compose =="
docker compose ps

echo
echo "== Health =="
docker compose exec -T agent_codex_bot python -m agent_codex.apps.cli.main doctor --project-root /app --json || true

echo
echo "== Host resources =="
free -h
df -h
