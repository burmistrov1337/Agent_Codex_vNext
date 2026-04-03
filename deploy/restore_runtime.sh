#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ARCHIVE_PATH="${1:-}"

if [[ -z "${ARCHIVE_PATH}" ]]; then
  echo "Usage: $0 <backup-archive.tar.gz>" >&2
  exit 1
fi

cd "${PROJECT_ROOT}"
docker compose down || true
tar -xzf "${ARCHIVE_PATH}" -C "${PROJECT_ROOT}"
echo "Runtime restored from ${ARCHIVE_PATH}"
