# jira-tempo-mcp

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

## Quick start

### Fastest path — one command, interactive

```bash
cd ./jira-tempo-mcp
python install.py
```

The installer walks you through 5 steps:

1. **Check Python** (>= 3.11)
2. **Create venv + install package** (editable, with dev deps)
3. **Write `.env`** — prompts for Jira URL, username, and PAT (PAT input is hidden
   via `getpass`; file is created with permissions `0600`)
4. **Register MCP server in VS Code** — adds the `jira-tempo` entry to
   `~/.config/Code/User/mcp.json` (with backup of any existing file)
5. **Verify Jira connectivity** — optional, calls `/rest/api/2/myself` with the
   PAT to confirm auth works

Re-run `python install.py` any time to regenerate `.env` or re-register the
VS Code config.

### Manual setup

If you prefer to wire things up by hand:

#### 1. Clone and install

```bash
cd ./jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

#### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your JIRA_PAT
```

Required variables:

| Variable | Description |
| --- | --- |
| `JIRA_BASE_URL` | Jira base URL (no trailing slash) |
| `JIRA_USER` | Your Jira username (login) |
| `JIRA_PAT` | Personal Access Token — **never commit this** |
| `JIRA_TIMEZONE` | IANA timezone (default: `Europe/Moscow`) |
| `TEMPO_API_TOKEN` | Optional separate Tempo token (falls back to `JIRA_PAT`) |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

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
   `mcp.json.bak` first (same pattern as `install`). If the entry is already
   absent or the file is missing, the step is a no-op.
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

- **Tokens never leave the local process.** The MCP server reads `JIRA_PAT` from
  environment and sends it only to your Jira instance over HTTPS.
- **`.env` is gitignored** — see `.gitignore`.
- **Tokens are masked in logs** — `Config.__repr__` replaces `JIRA_PAT` with `***`.
- **Error messages are redacted** — URLs with credentials are stripped before logging.
- The AI agent receives only the **result** of API calls (worklogs, report text),
  never the token itself.

## Weekly report

The `generate_weekly_report` tool implements the template from
`reports/2026/README.md`:

1. Fetches all Tempo worklogs for the target week (Mon–Fri).
2. Groups worklogs by issue key.
3. Maps known issues to stable report sections (see `config.py` defaults or
   override via `REPORT_SECTION_MAP` env var).
4. Fetches Jira issue summaries for unknown issues.
5. Writes `<username>_<DDMMYY>-<DDMMYY>.txt` to the configured output directory.

### Customizing section mapping

Override the default section mapping via environment variables:

```bash
# Option 1: inline JSON
export REPORT_SECTION_MAP='{"PROJECT-102":"Section A","PROJECT-101":"Section B"}'

# Option 2: JSON file
export REPORT_SECTION_MAP_FILE=/path/to/sections.json
```

Or set `REPORT_OUTPUT_DIR` to change where reports are written, and
`REPORT_AUTHOR_NAME` to change the author name in the report header.

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

```
jira-tempo-mcp/
├── .env.example          # environment template (copy to .env)
├── .gitignore            # .env is ignored
├── .vscode/mcp.json      # VS Code MCP config
├── pyproject.toml        # package metadata + dependencies
├── README.md
└── src/jira_tempo_mcp/
    ├── __init__.py
    ├── __main__.py       # python -m jira_tempo_mcp.server
    ├── config.py         # env loading, Config dataclass (secrets masked)
    ├── client.py         # Jira + Tempo HTTP client (PAT auth)
    ├── report.py         # weekly report generator
    └── server.py         # MCP server + 7 tools
```

## License

MIT