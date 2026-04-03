#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SERVICE="${1:-}"

cd "${PROJECT_ROOT}"

if [[ -n "${SERVICE}" ]]; then
  docker compose logs --tail=200 -f "${SERVICE}"
else
  docker compose logs --tail=200 -f
fi
