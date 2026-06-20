# jira-tempo-mcp

[![CI](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/ci.yml)
[![Release](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/release.yml/badge.svg)](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/release.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)

MCP server for **self-hosted Jira (Server / Data Center) + Tempo Timesheets 4**.

Track time, list worklogs, and generate weekly reports — all from your AI agent
(Copilot, Claude, etc.) via the Model Context Protocol.

## Features

| Tool | What it does |
| --- | --- |
| `list_worklogs` | List Tempo worklogs for a date range or single day |
| `get_worklog` | Get a single worklog by Tempo ID |
| `create_worklog` | Track time on a Jira issue with a comment |
| `delete_worklog` | Delete a worklog (undo mis-tracked time) |
| `get_issue` | Get Jira issue metadata (summary, status, project) |
| `list_favorite_issues` | List favorite issues for the current user |
| `generate_weekly_report` | Generate a weekly `.txt` report from Tempo worklogs |

## Prerequisites

- Python **3.11+**
- Jira Server / Data Center with **Tempo Timesheets 4.x** installed
- Jira **Personal Access Token (PAT)** — create one in:
  Jira → Profile → Personal Access Tokens

## Installation

Choose one of four paths depending on how you want to run the server.

### One-liner (recommended)

The interactive installer creates a venv, writes `.env`, registers the MCP
server in VS Code, and optionally verifies Jira connectivity:

```bash
cd jira-tempo-mcp
python install.py
```

See [Quick start](#quick-start) below for a walkthrough. The installer
**merges** into your existing `mcp.json` — it never overwrites other MCP
servers.

### Install from pip

Once the package is published to PyPI:

```bash
pip install jira-tempo-mcp
jira-tempo-mcp serve
```

### Install from source

```bash
git clone https://github.com/Korrnals/jira-tempo-mcp.git
cd jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
jira-tempo-mcp serve
```

### Install via Docker

The image is published to GitHub Container Registry on every `v*` tag:

```bash
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

The container runs `jira-tempo-mcp serve` over stdio by default. Secrets are
**never** baked into the image — pass them at runtime via `--env-file` or a
Kubernetes Secret. See [Docker](#docker) below for build instructions.

## Quick start

### Fastest path — one command, interactive

```bash
cd jira-tempo-mcp
python install.py
```

The installer walks you through 5 steps:

1. **Check Python** (>= 3.11)
2. **Create venv + install package** (editable, with dev deps)
3. **Write `.env`** — prompts for Jira URL, username, and PAT (PAT input is hidden
   via `getpass`; file is created with permissions `0600`)
4. **Register MCP server in VS Code** — **merges** the `jira-tempo` entry into
   `~/.config/Code/User/mcp.json`. Existing MCP servers are preserved
   (the installer reports how many it found and keeps). A backup
   `mcp.json.bak` is written before any change. If the file is invalid JSON,
   it is backed up and a fresh config is started.
5. **Verify Jira connectivity** — optional, calls `/rest/api/2/myself` with the
   PAT to confirm auth works

Re-run `python install.py` any time to regenerate `.env` or re-register the
VS Code config.

### Manual setup

If you prefer to wire things up by hand:

#### 1. Clone and install

```bash
git clone https://github.com/Korrnals/jira-tempo-mcp.git
cd jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

#### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your JIRA_PAT
```

Environment variables (see `.env.example` for a template):

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `JIRA_BASE_URL` | yes | — | Jira base URL (no trailing slash) |
| `JIRA_USER` | yes | — | Your Jira username (login) |
| `JIRA_PAT` | yes | — | Personal Access Token — **never commit this** |
| `JIRA_TIMEZONE` | no | `Europe/Moscow` | IANA timezone for date/time handling |
| `TEMPO_API_TOKEN` | no | falls back to `JIRA_PAT` | Separate Tempo API token |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `JIRA_HTTP_TIMEOUT` | no | `30.0` | HTTP timeout for Jira/Tempo calls (seconds) |
| `REPORT_OUTPUT_DIR` | no | `./reports` | Base directory for weekly report files |
| `REPORT_AUTHOR_NAME` | no | `JIRA_USER` | Author display name in the report header |
| `REPORT_SECTION_MAP` | no | empty | JSON dict mapping issue keys to section titles |
| `REPORT_SECTION_MAP_FILE` | no | empty | Path to a JSON file with the section mapping |
| `REPORT_FILENAME_PREFIX` | no | `JIRA_USER` | Prefix for weekly report filenames |
| `REPORT_STABLE_ORDER` | no | empty | JSON list of issue keys that always appear in this order |
| `REPORT_NON_ISSUE_SECTIONS` | no | empty | JSON list of section titles without issue keys |

See [Weekly report](#weekly-report) for details on the report-related
variables.

### 3. Run the server

After installation (manual or via `python install.py`):

```bash
# from inside the venv
jira-tempo-mcp serve
# or
python -m jira_tempo_mcp.server
```

The server runs over **stdio** — it reads JSON-RPC from stdin and writes to stdout.
Logs go to stderr.

CLI reference:

```text
jira-tempo-mcp                  # start the MCP server (default)
jira-tempo-mcp serve            # start the MCP server
jira-tempo-mcp install          # interactive installer
jira-tempo-mcp uninstall        # reverse the installation
jira-tempo-mcp --version        # show version
jira-tempo-mcp --help           # show usage
```

### Uninstall

`jira-tempo-mcp uninstall` reverses the installation in 4 steps:

1. **Remove `jira-tempo` from VS Code `mcp.json`** — backs up the file to
   `mcp.json.bak` first (same pattern as `install`). Only the `jira-tempo`
   entry is removed; **all other MCP servers are preserved**. If the entry
   is already absent or the file is missing, the step is a no-op.
2. **Delete `.env`** — optional, **default: No**. The file contains your
   `JIRA_PAT`; deletion is irreversible and requires explicit confirmation.
   The PAT value is never printed.
3. **Uninstall the pip package from the venv** — optional, **default: No**.
   Runs `pip uninstall -y jira-tempo-mcp` inside the project `.venv`. The
   `.venv` directory itself is kept (remove it manually if desired).
4. **Summary** — prints next steps (restart VS Code, how to fully remove
   `.venv`, how to reinstall).

The uninstaller reuses the same coloured UI helpers as `install.py` and never
logs the `JIRA_PAT` value.

### 4. Connect from VS Code / Copilot

The installer (`python install.py`) automatically registers the MCP server in
your VS Code user-level `mcp.json`. If you prefer manual setup, create or edit
`~/.config/Code/User/mcp.json` (Linux) — or the equivalent on macOS/Windows:

```json
{
  "servers": {
    "jira-tempo": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "jira_tempo_mcp.server"],
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_USER": "your-username",
        "JIRA_PAT": "${env:JIRA_PAT}",
        "JIRA_TIMEZONE": "Europe/Moscow",
        "LOG_LEVEL": "INFO",
        "PYTHONPATH": "/path/to/jira-tempo-mcp/src"
      }
    }
  }
}
```

`PYTHONPATH` points at the `src/` layout so the package is importable even if
the spawned process bypasses the venv's site-packages (e.g. a `PYTHONHOME`
override in the VS Code environment that skips the editable-install `.pth`).
Make sure `JIRA_PAT` is set in your shell environment or `.env` file.

## Security

The server handles a Jira Personal Access Token, so every layer is hardened
against accidental leakage.

### Token handling

- **Tokens never leave the local process.** The MCP server reads `JIRA_PAT` from
  environment and sends it only to your Jira instance over HTTPS.
- **`.env` is gitignored** and created with permissions **`0600`** on POSIX
  (owner read/write only). On Windows the installer prints a reminder to
  restrict access manually.
- **Tokens are masked in logs** — `Config.__repr__` replaces `JIRA_PAT` with
  `***`.
- **Error messages are redacted** — URLs with embedded credentials are stripped
  via `_redact()` before any logging. API error bodies are truncated to 200
  characters to reduce noise and potential token leakage.
- The AI agent receives only the **result** of API calls (worklogs, report
  text), never the token itself.

### Transport hardening

- **TLS verification is always on** (`httpx.AsyncClient(verify=True)`). The
  client never connects to a Jira instance with an invalid certificate.
- **HTTP redirects are disabled** (`follow_redirects=False`). This prevents
  PAT leakage via a redirect from your Jira host to an attacker-controlled
  host.
- **Configurable HTTP timeout** (`JIRA_HTTP_TIMEOUT`, default 30 s) prevents
  hung connections from blocking the MCP server indefinitely.

### Input validation

- **Jira issue keys are validated** against `^[A-Z][A-Z0-9]+-\d+$` before any
  API call — rejects malformed keys that could be used for injection.
- **Dates are validated** as ISO `YYYY-MM-DD` before parsing.
- **Report `output_dir` is checked against path traversal** — the resolved
  path must be inside the allowed root (`REPORT_OUTPUT_DIR` or `./reports`).
  Paths like `../../etc` are rejected with an explicit error.

### Docker build safety

- **`.dockerignore` excludes secrets and artifacts** from the build context:
  `.env`, `.env.*.local`, `.history/` (VS Code Local History snapshots that
  may contain old `.env` content), `.venv/`, `__pycache__/`, `.git/`, and
  `tests/`.
- **Multi-stage build** — the runtime image contains only the installed
  wheel, no dev dependencies, no build tools, no source tree.
- **Runs as non-root user** `appuser` (UID 1001) with no shell.
- **Never bake `JIRA_PAT` into the image** — pass it at runtime via
  `--env-file` or a Kubernetes Secret.

## Weekly report

The `generate_weekly_report` tool implements a weekly report template:

1. Fetches all Tempo worklogs for the target week (Mon–Fri).
2. Groups worklogs by issue key.
3. Maps known issues to stable report sections (see `config.py` defaults or
   override via `REPORT_SECTION_MAP` env var).
4. Fetches Jira issue summaries for unknown issues.
5. Writes `<prefix>_<DDMMYY>-<DDMMYY>.txt` to the configured output directory.

### Customizing section mapping

Override the default section mapping via environment variables:

```bash
# Option 1: inline JSON
export REPORT_SECTION_MAP='{"PROJECT-100":"Section A","PROJECT-101":"Section B"}'

# Option 2: JSON file
export REPORT_SECTION_MAP_FILE=/path/to/sections.json
```

Or set `REPORT_OUTPUT_DIR` to change where reports are written,
`REPORT_AUTHOR_NAME` to change the author name in the report header, and
`REPORT_FILENAME_PREFIX` to change the filename prefix (defaults to `JIRA_USER`).

Control section ordering and non-issue sections via JSON lists:

```bash
# Stable sections — issue keys that always appear in this order
export REPORT_STABLE_ORDER='["PROJECT-100", "PROJECT-101"]'

# Non-issue sections — titles without issue keys (e.g. meetings, admin)
export REPORT_NON_ISSUE_SECTIONS='["Team meetings", "Jira triage"]'
```

## CI/CD

The repo has two GitHub Actions workflows:

| Workflow | Trigger | What it does |
| --- | --- | --- |
| [`ci.yml`](.github/workflows/ci.yml) | push / PR to `main` | `ruff check` + `ruff format --check` + `mypy src/` + `pytest tests/ -v` on Python 3.12 |
| [`release.yml`](.github/workflows/release.yml) | git tag `v*` | Build wheel (`python -m build`), build & push Docker image to `ghcr.io/korrnals/jira-tempo-mcp:<tag>`, create GitHub Release with the wheel attached |

CI uses the ruff / mypy / pytest configuration already declared in
`pyproject.toml` — no duplicated config. Pip dependencies are cached via
`actions/setup-python` keyed on `pyproject.toml`.

### Releasing a new version

```bash
# 1. Bump version in pyproject.toml
# 2. Commit + push to main (CI must be green)
# 3. Tag and push
git tag v0.2.0
git push origin v0.2.0
```

The release workflow then:

1. Builds the wheel and sdist.
2. Builds the Docker image and pushes it to `ghcr.io/korrnals/jira-tempo-mcp:v0.2.0`
   (and `:latest` for non-pre-release tags).
3. Creates a GitHub Release with auto-generated release notes and the wheel
   attached as a download asset.

## Docker

### Build the image locally

```bash
docker build -t jira-tempo-mcp .
```

The Dockerfile is a **multi-stage build**:

- **builder** — `python:3.12-slim`, builds a wheel and installs it into a
  clean venv (no dev deps leak into runtime).
- **runtime** — `python:3.12-slim`, copies only the venv, runs as non-root
  user `appuser` (UID 1001), with `PYTHONDONTWRITEBYTECODE=1` and
  `PYTHONUNBUFFERED=1`.

A `HEALTHCHECK` verifies the package is importable (`python -c "import jira_tempo_mcp"`).
There is no HTTP port to probe — the server speaks stdio.

### Run the container

```bash
# stdio mode — pipe JSON-RPC in/out
docker run -i --rm \
  --env-file .env \
  jira-tempo-mcp

# or use the published image
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

### Required environment variables

The container reads the same env vars as the local install. Pass them via
`--env-file` (a gitignored `.env`) or a Kubernetes Secret:

| Variable | Required | Description |
| --- | --- | --- |
| `JIRA_BASE_URL` | yes | Jira base URL (no trailing slash) |
| `JIRA_USER` | yes | Jira username |
| `JIRA_PAT` | yes | Personal Access Token |
| `JIRA_TIMEZONE` | no | IANA timezone (default `Europe/Moscow`) |
| `TEMPO_API_TOKEN` | no | Separate Tempo token (falls back to `JIRA_PAT`) |
| `LOG_LEVEL` | no | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `JIRA_HTTP_TIMEOUT` | no | HTTP timeout in seconds (default `30.0`) |
| `REPORT_OUTPUT_DIR` | no | Base directory for reports (default `./reports`) |
| `REPORT_AUTHOR_NAME` | no | Author name in report header (default `JIRA_USER`) |
| `REPORT_SECTION_MAP` | no | JSON dict: issue key → section title |
| `REPORT_SECTION_MAP_FILE` | no | Path to a JSON file with the section mapping |
| `REPORT_FILENAME_PREFIX` | no | Prefix for report filenames (default `JIRA_USER`) |
| `REPORT_STABLE_ORDER` | no | JSON list: issue keys in stable order |
| `REPORT_NON_ISSUE_SECTIONS` | no | JSON list: non-issue section titles |

> **Never** bake `JIRA_PAT` into the image. The `.dockerignore` excludes
> `.env`, `.venv/`, `.history/`, and build artifacts from the build context.

## Development

### Pre-commit hooks

The project ships a `.pre-commit-config.yaml` that runs lint and type checks
automatically before every commit. Install once after cloning:

```bash
pip install -e ".[dev]"
pre-commit install
```

On each commit the hooks run:

| Hook | What it does |
| --- | --- |
| `ruff check --fix` | Lint + autofix (rules from `pyproject.toml`) |
| `ruff format --check` | Verify formatting (no in-place rewrite on commit) |
| `mypy src/` | Strict type check on `src/` only |
| `trailing-whitespace` / `end-of-file-fixer` / `check-yaml` / `check-added-large-files` | Standard hygiene |

To bypass the hooks in an emergency (e.g. WIP commit on a branch you will
rebase later):

```bash
git commit --no-verify
```

Use sparingly — the hooks exist to keep `main` green.

### Manual checks

```bash
# Lint
ruff check src/

# Type check
mypy src/

# Run tests (when added)
pytest
```

## Project structure

```text
jira-tempo-mcp/
├── .dockerignore          # excludes secrets + artifacts from image build
├── .env.example           # environment template (copy to .env)
├── .github/workflows/     # CI + release pipelines
│   ├── ci.yml
│   └── release.yml
├── .gitignore             # .env, .history/, venvs are ignored
├── .pre-commit-config.yaml
├── .vscode/mcp.json       # workspace MCP config (example)
├── Dockerfile             # multi-stage build, non-root runtime
├── install.py             # interactive installer + uninstaller
├── pyproject.toml         # package metadata + dependencies + tool config
├── README.md
├── src/jira_tempo_mcp/
│   ├── __init__.py
│   ├── __main__.py        # python -m jira_tempo_mcp
│   ├── cli.py             # console entrypoint dispatcher
│   ├── config.py          # env loading, Config dataclass (secrets masked)
│   ├── client.py          # Jira + Tempo HTTP client (PAT auth, TLS, no redirects)
│   ├── report.py          # weekly report generator
│   ├── server.py          # MCP server + 7 tools, input validation
│   └── utils.py           # duration parsing, formatting, timezone helpers
└── tests/
    ├── test_config.py
    ├── test_report.py
    ├── test_report_integration.py
    └── test_utils.py
```

## License

MIT