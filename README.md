# jira-tempo-mcp

![banner](docs/assets/banner.svg)

[![CI](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/ci.yml)
[![Release](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/release.yml/badge.svg)](https://github.com/Korrnals/jira-tempo-mcp/actions/workflows/release.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue.svg)](https://github.com/Korrnals/jira-tempo-mcp/pkgs/container/jira-tempo-mcp)

MCP server for **self-hosted Jira (Server / Data Center) + Tempo Timesheets 4**.
Track time, list worklogs, and generate weekly reports — all from your AI agent
(Copilot, Claude, etc.) via the Model Context Protocol.

> **Русская версия:** [README.ru.md](README.ru.md)
> **Full documentation:** [docs/README.md](docs/README.md)

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

See [docs/api.md](docs/api.md) for the full tool reference with parameters and
examples.

## Quick start

**One-liner (pip, once published on PyPI):**

```bash
pip install jira-tempo-mcp && jira-tempo-mcp install
```

**One-liner (from GitHub, before PyPI or for dev):**

```bash
pip install git+https://github.com/Korrnals/jira-tempo-mcp.git && jira-tempo-mcp install
```

**Docker:**

```bash
docker run -i --rm -e JIRA_PAT=$JIRA_PAT ghcr.io/korrnals/jira-tempo-mcp:latest
```

> The interactive installer (`jira-tempo-mcp install`) guides you through
> Jira credentials setup and VS Code MCP registration.

---

### From source (development)

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

## Configuration

All configuration is via environment variables. Required:

| Variable | Description |
| --- | --- |
| `JIRA_BASE_URL` | Jira base URL (no trailing slash) |
| `JIRA_USER` | Jira username (login) |
| `JIRA_PAT` | Personal Access Token — **never commit this** |

Optional: `JIRA_TIMEZONE`, `TEMPO_API_TOKEN`, `LOG_LEVEL`, `JIRA_HTTP_TIMEOUT`,
and report-related vars (`REPORT_*`).

Full reference: [docs/configuration.md](docs/configuration.md).

## MCP integration

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

> **Tip:** always use **absolute paths** for `envFile` — `~` does not work in
> sandboxed environments (distrobox, snap, containers).

Full guide: [docs/mcp-integration.md](docs/mcp-integration.md).

## CLI

```text
jira-tempo-mcp                  # start the MCP server (default)
jira-tempo-mcp serve            # start the MCP server
jira-tempo-mcp install          # interactive installer
jira-tempo-mcp uninstall        # reverse the installation
jira-tempo-mcp --version        # show version
```

Full reference: [docs/cli.md](docs/cli.md).

## Security

- **Tokens never leave the local process** — `JIRA_PAT` is sent only to your
  Jira instance over HTTPS.
- **TLS verification always on**, **HTTP redirects disabled**
  (`follow_redirects=False`) — prevents PAT leakage via redirect.
- **Tokens masked in logs** — `Config.__repr__` replaces `JIRA_PAT` with `***`.
- **Input validation** — issue keys, dates, and `output_dir` (path traversal
  guard) are validated before any API call.
- **Docker** — multi-stage build, non-root user, secrets never baked in.

Full model: [docs/architecture.md#security](docs/architecture.md#security).

## Documentation

| Topic | Document |
| --- | --- |
| Installation | [docs/installation.md](docs/installation.md) |
| Configuration | [docs/configuration.md](docs/configuration.md) |
| MCP integration | [docs/mcp-integration.md](docs/mcp-integration.md) |
| CLI | [docs/cli.md](docs/cli.md) |
| API (MCP tools) | [docs/api.md](docs/api.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) |
| Reports | [docs/reports.md](docs/reports.md) |
| Deployment | [docs/deployment.md](docs/deployment.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |

## License

MIT
