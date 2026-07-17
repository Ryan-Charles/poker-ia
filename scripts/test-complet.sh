#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
"$ROOT/.venv/bin/python" -m alembic upgrade head
"$ROOT/.venv/bin/python" -m pytest -q
"$ROOT/.venv/bin/python" -m ruff check app tests ../scripts/Mesurer-Performances.py ../desktop/launcher.py
"$ROOT/.venv/bin/python" -m ruff format --check app tests ../scripts/Mesurer-Performances.py ../desktop/launcher.py
"$ROOT/.venv/bin/python" -m mypy app
cd "$ROOT/frontend"
pnpm typecheck
pnpm lint
pnpm format:check
pnpm test
pnpm build
pnpm test:e2e
