# jira-tempo-mcp — local CI / quality gate (GitHub Actions intentionally disabled; make ci is canonical)
#
# Targets work from a cold shell (no venv activation required):
# each recipe calls .venv/bin/<tool> directly, falling back to `python` on PATH
# if the venv is absent.

.PHONY: help ci lint format format-check typecheck test build clean install

PY      := .venv/bin/python
PY_FALLBACK := python
PIP     := .venv/bin/pip
RUFF    := .venv/bin/ruff
MYPY    := .venv/bin/mypy
PYTEST  := .venv/bin/pytest
PY_BUILD := .venv/bin/python

# Resolve python to venv if present, else PATH
ifeq ($(wildcard .venv/bin/python),)
PY      := $(PY_FALLBACK)
PIP     := pip
RUFF    := ruff
MYPY    := mypy
PYTEST  := pytest
PY_BUILD := python
endif

help:  ## Show this help (default target)
	@echo "jira-tempo-mcp — local CI / quality gate"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

ci:  ## Full gate: lint + typecheck + test + build
	@echo "==> [1/4] lint (ruff check .)"
	@$(RUFF) check .
	@echo "==> [2/4] typecheck (mypy src)"
	@$(MYPY) src
	@echo "==> [3/4] test (pytest -q)"
	@$(PYTEST) -q
	@echo "==> [4/4] build (python -m build)"
	@$(PY_BUILD) -m build
	@echo "==> ci: all stages green"

lint:  ## ruff check .
	@$(RUFF) check .

format:  ## ruff format . (apply formatting fixes)
	@$(RUFF) format .

format-check:  ## ruff format --check . (verify, no changes)
	@$(RUFF) format --check .

typecheck:  ## mypy src
	@$(MYPY) src

test:  ## pytest -q
	@$(PYTEST) -q

build:  ## python -m build (produces dist/)
	@$(PY_BUILD) -m build

clean:  ## Remove build artefacts (NOT .venv)
	rm -rf dist/ build/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache

install:  ## pip install -e . (editable dev install)
	@$(PIP) install -e .
