#!/usr/bin/env bash
set -euo pipefail

python -m agent_codex.apps.cli.main doctor --project-root /app --json
