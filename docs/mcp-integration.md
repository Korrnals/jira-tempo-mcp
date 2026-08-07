# 🔌 MCP integration

How `jira-tempo-mcp` plugs into VS Code Copilot Chat via the Model Context
Protocol.

---

## 🏗️ How it works

```mermaid
flowchart LR
    A[VS Code Copilot Chat] -->|JSON-RPC over stdio| B[jira-tempo-mcp server]
    B -->|HTTPS + PAT| C[Jira REST API]
    B -->|HTTPS + Tempo token| D[Tempo Timesheets 4 API]
    B -->|reads| E[.env.local / env vars]
```

The MCP server runs as a child process of VS Code. It speaks JSON-RPC over
stdio (stdin/stdout); logs go to stderr. VS Code discovers it through an
entry in `mcp.json`.

---

## 👤 User-level config — `~/.config/Code/User/mcp.json`

The installer (`python install.py`) registers the server here automatically.
Manual equivalent on Linux:

```json
{
  "servers": {
    "jira-tempo": {
      "command": "/home/your-username/projects/jira-tempo-mcp/.venv/bin/python",
      "args": ["-m", "jira_tempo_mcp.server"],
      "envFile": "/home/your-username/.config/Code/User/.env.local",
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_USER": "your-username",
        "JIRA_TIMEZONE": "Europe/Moscow",
        "LOG_LEVEL": "INFO",
        "PYTHONPATH": "/home/your-username/projects/jira-tempo-mcp/src"
      }
    }
  }
}
```

> 💡 **Tip:** On macOS the path is `~/Library/Application Support/Code/User/mcp.json`;
> on Windows `%APPDATA%\Code\User\mcp.json`.

---

## 📁 Workspace-level config — `.vscode/mcp.json`

The installer also writes a workspace-level `.vscode/mcp.json` that uses
`${workspaceFolder}` variables so the config is portable across machines:

```json
{
  "servers": {
    "jira-tempo": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "jira_tempo_mcp.server"],
      "envFile": "/home/your-username/.config/Code/User/.env.local",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/src"
      }
    }
  }
}
```

`${workspaceFolder}` resolves to the project root at runtime. Non-secret
env vars (`JIRA_BASE_URL`, `JIRA_USER`, …) are injected from the user-level
config or `.env.local`.

---

## 🔑 `envFile` — single `.env.local` for secrets

The recommended pattern: keep all MCP-server secrets in one
`~/.config/Code/User/.env.local` and reference it via `envFile`:

```bash
# ~/.config/Code/User/.env.local
JIRA_PAT=your_personal_access_token_here
TEMPO_API_TOKEN=your_tempo_token_here
```

VS Code MCP-host loads this file and injects the variables into the server
process environment. This keeps secrets out of `mcp.json` (which may be
committed) and out of shell history.

### ⚠️ Absolute paths for `envFile` (distrobox / containers)

**Always use absolute paths for `envFile`.** The `~` shortcut does not work
in sandboxed environments (distrobox, snap, flatpak, containers) because
VS Code MCP-host resolves `~` against its own root namespace, not the
user's `$HOME`.

| Environment | Wrong | Right |
| --- | --- | --- |
| Native Linux | `~/.config/Code/User/.env.local` | `/home/your-username/.config/Code/User/.env.local` |
| distrobox | `~/.config/Code/User/.env.local` | `/var/home/your-username/.distrobox/box/home/.config/Code/User/.env.local` |
| macOS | `~/.config/…` | `/Users/your-username/.config/…` |

> 🐛 **Symptom of the bug:** `Failed to read envFile '~/...'` in the MCP panel,
> and the server does not start.

---

## 🌐 `${input:...}` for HTTP-type servers

Some MCP servers (e.g. the GitHub MCP server) use the `http` type and
require secrets in HTTP headers. The `${env:VAR}` substitution does **not**
work inside `headers` for HTTP-type servers — VS Code returns
`400 Authorization header badly formatted`.

Use `${input:...}` instead, which prompts the user once and caches the
value in the VS Code secret storage:

```json
{
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer ${input:github_token}"
      },
      "inputs": [
        {
          "id": "github_token",
          "type": "promptString",
          "description": "GitHub PAT (classic) with repo scope",
          "password": true
        }
      ]
    }
  }
}
```

> 💡 **Tip:** `jira-tempo-mcp` is a **stdio** server, so it uses `envFile` + `env`,
> not `${input:...}`. The `${input:...}` pattern is documented here for users
> who run multiple MCP servers side by side.

---

## 📁 `${workspaceFolder}` variables

| Variable | Resolves to |
| --- | --- |
| `${workspaceFolder}` | Project root (where `.vscode/` lives) |
| `${workspaceFolderBasename}` | Project folder name only |

Use these in workspace-level `.vscode/mcp.json` so the config is portable.
Avoid them in user-level `mcp.json` — there is no workspace context at
that scope.

---

## 🐛 Troubleshooting MCP startup

| Symptom | Cause | Fix |
| --- | --- | --- |
| Server not in MCP panel | VS Code did not reload | Ctrl+Shift+P → Developer: Reload Window |
| `Failed to read envFile '~/...'` | `~` not resolved in sandbox | use absolute path |
| `ModuleNotFoundError: No module named 'pytz'` | venv not activated / wrong python | use `${workspaceFolder}/.venv/bin/python` |
| `JIRA_BASE_URL or JIRA_PAT missing` | `.env.local` not loaded | check `envFile` path and contents |
| `401 Unauthorized` | invalid or expired PAT | rotate the PAT in Jira |
| `400 Authorization header badly formatted` | `${env:...}` in HTTP headers | use `${input:...}` |

See [troubleshooting.md](troubleshooting.md) for the full list.

---

## 🤝 Agent ↔ MCP contract

This section fixes how AI agents (Copilot, GCW agents, etc.) should interact
with `jira-tempo-mcp`. The contract is mandatory: violating either side leads
to reports landing in the wrong directory, duplicated work, and delegating to
the user tasks the agent could have solved itself.

### ✅ The only sanctioned channel — MCP tools

The agent interacts with the server **only** through MCP tools
(`generate_weekly_report`, `get_tempo_worklogs`, `get_jira_issue`, etc.),
invoked from Copilot / MCP-client chat. In this mode the VS Code MCP-host
injects variables from `.env.local` into the server's process environment,
and reports are written to the canonical directory automatically.

### 🚫 Direct Python/CLI calls from a terminal — anti-pattern

Running the module directly (e.g. `python -m jira_tempo_mcp.cli ...` or
scripts from `src/`) **from an agent's chat** is an anti-pattern. Reasons:

- the agent duplicates logic already encapsulated in MCP tools;
- outside the MCP-host, variables from `.env.local` were historically not
  picked up (see [configuration.md § Configuration source priority](configuration.md) —
  a terminal call now reads `.env.local` too, but the MCP channel remains
  preferred);
- terminal output may contain secrets — higher PAT-leak risk.

A direct call is justified **only** when a human debugs the server itself,
not when an agent does routine work.

### 🔁 Retry strategy when MCP is unavailable

If an MCP tool is unavailable or returned a network error (`ConnectError`,
timeout, 5xx), the agent **does not** fall back to the terminal and **does
not** ask the user to run a script by hand. Strategy:

| Attempt | Action | Delay |
| --- | --- | --- |
| 1 | Retry the same MCP tool | — |
| 2 | Retry after a pause | ~5 s (backoff) |
| 3 | Retry after a pause | ~15 s (backoff) |
| 4+ | Escalate to the user with a diagnosis, not a command | — |

Escalating to the user is a **diagnosis** ("the `jira-tempo` MCP server has
not responded after 3 attempts; check whether the server is running in the
MCP panel"), not an **instruction** to run a command ("run `python ...` in
the terminal"). Delegating command execution to the user violates scope
discipline.

> 💡 **For HTTP 429** (Tempo rate-limit) a retry is already built into the
> server (`TEMPO_MAX_RETRIES`, exponential backoff) — the agent does not need
> to retry; it is enough to wait for the tool's response.

---

## ➡️ Next steps

- 🌐 [api.md](api.md) — MCP tools reference
- ⚙️ [configuration.md](configuration.md) — all environment variables
- 🐛 [troubleshooting.md](troubleshooting.md) — common errors
