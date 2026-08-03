#!/usr/bin/env bash
# jira-tempo-mcp — standalone local CI gate (mirror of `make ci`)
# Usage: bash scripts/local-ci.sh  (or make ci)
set -euo pipefail

cd "$(dirname "$0")/.."

# Activate venv if present, else fall back to python on PATH
if [ -x .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  echo "WARN: .venv/bin/activate not found — using python on PATH"
fi

echo "[1/4] lint (ruff check .)"
ruff check .

echo "[2/4] typecheck (mypy src)"
mypy src

echo "[3/4] test (pytest -q)"
pytest -q

echo "[4/4] build (python -m build)"
python -m build

echo "local-ci: all stages green"
