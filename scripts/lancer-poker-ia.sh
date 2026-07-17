#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export POKER_IA_PROJECT_ROOT="$ROOT"
export POKER_IA_DATA_DIR="$ROOT/data"
export POKER_IA_FRONTEND_DIST="$ROOT/frontend/dist"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8765

