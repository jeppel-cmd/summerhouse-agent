#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export SUMMERHOUSE_HOST="${SUMMERHOUSE_HOST:-127.0.0.1}"
export SUMMERHOUSE_PORT="${SUMMERHOUSE_PORT:-8080}"
exec .venv/bin/python app.py
