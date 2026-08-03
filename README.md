# jira-tempo-mcp

![banner](docs/assets/banner.svg)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue.svg)](https://github.com/Korrnals/jira-tempo-mcp/pkgs/container/jira-tempo-mcp)

MCP server for **self-hosted Jira (Server / Data Center) + Tempo Timesheets 4**.
Track time, list worklogs, and generate weekly reports — all from your AI agent
(Copilot, Claude, etc.) via the Model Context Protocol.

> 📖 **Русская версия:** [README.ru.md](README.ru.md)

## 📚 Documentation

| Document | Description |
|----------|---------|
| [API Reference](docs/api.md) | Full MCP tool reference with parameters and examples |
| [Installation](docs/installation.md) | Setup and installation guide |
| [Configuration](docs/configuration.md) | Environment variables reference |
| [Reports](docs/reports.md) | Report formats (txt, md, json) and templates |
| [Architecture](docs/architecture.md) | Project architecture and design decisions |
| [CLI](docs/cli.md) | Command-line interface reference |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [MCP Integration](docs/mcp-integration.md) | Integration with MCP clients (VS Code, etc.) |
| [Deployment](docs/deployment.md) | Docker and deployment options |

---

## 📋 Features

| Tool | What it does |
| --- | --- |
| `list_worklogs` | List Tempo worklogs for a date range or single day |
| `get_worklog` | Get a single worklog by Tempo ID |
| `create_worklog` | Track time on a Jira issue with a comment |
| `delete_worklog` | Delete a worklog (undo mis-tracked time) |
| `get_issue` | Get Jira issue metadata (summary, status, project) |
| `list_favorite_issues` | List favorite issues for the current user |
| `search_users` | Search Jira users by name, surname, or username |
| `list_user_tasks` | Get tasks assigned to a Jira user with status, priority, comments |
| `generate_weekly_report` | Generate a weekly report (txt/md/json) from Tempo worklogs |
| `generate_team_report` | Generate a team report (txt/md/json) for multiple Jira users |
| `generate_tasks_report` | Generate a tasks report (md/txt/json) grouped by status |
| `list_report_templates` | List available report templates (builtin + custom) |

Since v0.2.0 the server supports **team reports** (per-user aggregation with
rate-limiting) and **custom report templates** (Jinja2 sandbox + opt-in Python).
Since v0.3.0 all report generators support **three output formats**: `txt`
(plain text), `md` (Markdown with tables and emojis), and `json` (structured
JSON). See [docs/reports.md](docs/reports.md) for details.

See [docs/api.md](docs/api.md) for the full tool reference with parameters and
examples.

---

## 🚀 Quick start

Get up and running in under a minute:

**Install (one command):**

```bash
curl -fsSL https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/install.sh | bash
```

This downloads and runs the interactive installer, which:

- ✅ Checks Python 3.11+ and pip
- ✅ Clones the repo and creates a venv
- ✅ Installs the package
- ✅ Guides you through Jira credentials setup
- ✅ Registers the MCP server in VS Code (user + workspace)

> 💡 **Tip:** The installer never requires `sudo` — everything lives in user space.
> It's idempotent: re-running updates without clobbering existing config.

**Uninstall:**

```bash
curl -fsSL https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/install.sh | bash -- --uninstall
```

**Docker:**

```bash
docker run -i --rm -e JIRA_PAT="$JIRA_PAT" ghcr.io/korrnals/jira-tempo-mcp:latest
```

> ⚠️ **Warning:** The install script URL works once the repository is public.
> Until then, clone manually and run `python install.py`.

---

### 🔧 From source (development)

The interactive installer creates a venv, writes `.env`, registers the MCP
server in VS Code, and optionally verifies Jira connectivity:

```bash
cd jira-tempo-mcp
python install.py
```

Or install from source:

```bash
git clone https://github.com/Korrnals/jira-tempo-mcp.git
cd jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
jira-tempo-mcp serve
```

Or run via Docker:

```bash
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

Full installation paths: [docs/installation.md](docs/installation.md).

---

## ⚙️ Configuration

All configuration is via environment variables. Required:

| Variable | Description |
| --- | --- |
| `JIRA_BASE_URL` | Jira base URL (no trailing slash) |
| `JIRA_USER` | Jira username (login) |
| `JIRA_PAT` | Personal Access Token — 🔑 **never commit this** |

Optional: `JIRA_TIMEZONE`, `TEMPO_API_TOKEN`, `LOG_LEVEL`, `JIRA_HTTP_TIMEOUT`,
and report-related vars (`REPORT_*`).

Full reference: [docs/configuration.md](docs/configuration.md).

---

## 🔌 MCP integration

The server runs over **stdio** and is registered in VS Code `mcp.json`:

```json
{
  "servers": {
    "jira-tempo": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "jira_tempo_mcp.server"],
      "envFile": "/home/your-username/.config/Code/User/.env.local",
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_USER": "your-username",
        "PYTHONPATH": "${workspaceFolder}/src"
      }
    }
  }
}
```

> 💡 **Tip:** Always use **absolute paths** for `envFile` — `~` does not work in
> sandboxed environments (distrobox, snap, containers).

Full guide: [docs/mcp-integration.md](docs/mcp-integration.md).

---

## 🖥️ CLI

```text
jira-tempo-mcp                  # start the MCP server (default)
jira-tempo-mcp serve            # start the MCP server
jira-tempo-mcp install          # interactive installer
jira-tempo-mcp uninstall        # reverse the installation
jira-tempo-mcp --version        # show version
```

Full reference: [docs/cli.md](docs/cli.md).

---

## 🔒 Security

- **🔑 Tokens never leave the local process** — `JIRA_PAT` is sent only to your
  Jira instance over HTTPS.
- **🛡️ TLS verification always on**, **HTTP redirects disabled**
  (`follow_redirects=False`) — prevents PAT leakage via redirect.
- **👁️ Tokens masked in logs** — `Config.__repr__` replaces `JIRA_PAT` with `***`.
- **✅ Input validation** — issue keys, dates, and `output_dir` (path traversal
  guard) are validated before any API call.
- **🐳 Docker** — multi-stage build, non-root user, secrets never baked in.

Full model: [docs/architecture.md#security](docs/architecture.md#security).

## 🛠️ Development

The canonical quality gate for this repo is the local `make` suite — GitHub
Actions are intentionally disabled here, so `make ci` is what every change
must pass before merge. It runs linting, type-checking, tests, and the build in
one command.

```sh
make ci         # full quality gate — lint + typecheck + test + build
make lint       # ruff
make typecheck  # mypy
make test       # pytest
make build      # python -m build (sdist + wheel)
```

---

##  License

MIT
