# jira-tempo-mcp — Documentation

![banner](assets/banner.svg)

MCP server for **self-hosted Jira (Server / Data Center) + Tempo Timesheets 4**.
Track time, list worklogs, and generate weekly reports from your AI agent
(Copilot, Claude, etc.) via the Model Context Protocol.

## Quick links

| Topic | Document | What you will learn |
| --- | --- | --- |
| Install | [installation.md](installation.md) | `python install.py`, pip, Docker, venv |
| Configure | [configuration.md](configuration.md) | env vars, `.env.local`, `.env`, examples |
| MCP integration | [mcp-integration.md](mcp-integration.md) | VS Code `mcp.json`, `envFile`, workspace config |
| CLI | [cli.md](cli.md) | `serve`, `install`, `uninstall`, `--version` |
| API (MCP tools) | [api.md](api.md) | `list_worklogs`, `create_worklog`, `generate_weekly_report`, … |
| Architecture | [architecture.md](architecture.md) | layers, data flow, security model |
| Reports | [reports.md](reports.md) | weekly report, section mapping, stable order |
| Deployment | [deployment.md](deployment.md) | Docker, CI/CD, release workflow |
| Troubleshooting | [troubleshooting.md](troubleshooting.md) | common errors and fixes |

## Where to start

- **First time?** → [installation.md](installation.md) → [configuration.md](configuration.md) → [mcp-integration.md](mcp-integration.md)
- **Already installed?** → [api.md](api.md) for the full tool reference
- **Something broken?** → [troubleshooting.md](troubleshooting.md)

## Language

English is the primary language. A mirrored Russian version is available at
[README.ru.md](README.ru.md).

## License

MIT — see the root [README.md](../README.md#license).
