#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
BACKUP_ROOT="${BACKUP_ROOT:-${PROJECT_ROOT}/backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_PATH="${BACKUP_ROOT}/agent_codex_runtime_${STAMP}.tar.gz"

cd "${PROJECT_ROOT}"
mkdir -p "${BACKUP_ROOT}" .agent_codex .docker/n8n

tar -czf "${ARCHIVE_PATH}" .agent_codex .docker/n8n .env
echo "Backup created: ${ARCHIVE_PATH}"
