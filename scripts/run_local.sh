#!/usr/bin/env bash
# Run the digest locally with .env loaded.
#
# Usage:
#   scripts/run_local.sh             # default DRY_RUN=1 → console
#   DRY_RUN=0 DELIVERY=slack scripts/run_local.sh

set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PY="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then
  echo "Python not found at $PY — create .venv first (python3.12 -m venv .venv)" >&2
  exit 1
fi

exec "$PY" -m ai_news_digest "$@"
