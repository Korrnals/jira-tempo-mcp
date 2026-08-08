# 🖥️ CLI reference

The `jira-tempo-mcp` console script dispatches between the MCP server, the
interactive installer, and the uninstaller.

---

## 🖥️ Commands

```text
jira-tempo-mcp                  # start the MCP server (default = serve)
jira-tempo-mcp serve            # start the MCP server (stdio)
jira-tempo-mcp install          # interactive installer (venv + .env + VS Code)
jira-tempo-mcp uninstall        # reverse the installation
jira-tempo-mcp --version        # show version
jira-tempo-mcp --help           # show usage
```

---

## 🚀 `serve`

Starts the MCP server over stdio. Reads JSON-RPC from stdin, writes to
stdout, logs to stderr. This is the default when no subcommand is given.

```bash
# from inside the venv
jira-tempo-mcp serve

# or via the package module
python -m jira_tempo_mcp.server
```

The server reads configuration from environment variables / `.env` at
startup. See [configuration.md](configuration.md).

---

## 📦 `install`

Runs the interactive installer (`install.py`). Creates a venv, writes
`.env`, registers the MCP server in VS Code `mcp.json`, and optionally
verifies Jira connectivity.

```bash
jira-tempo-mcp install
# equivalent to:
python install.py
```

See [installation.md](installation.md) for the full walkthrough.

### 🔧 Installer flags

The installer (`install.py`) accepts these flags — useful in CI, headless
setups, or when re-running only part of the setup:

| Flag | Effect |
| --- | --- |
| `-n` / `--non-interactive` / `--yes` | Run without prompts; take values from flags / env vars / defaults |
| `--register-only` | Skip venv/pip — only write `.env.local` and register in `mcp.json` |
| `--no-agent` | Skip the Copilot Chat agent installation (agent installs by default) |
| `--uninstall-agent` | Remove only the Copilot Chat agent + skill + `JTM_AGENT.md`, then exit |
| `--skip-vscode` | Skip VS Code `mcp.json` registration (only write `.env.local`) |
| `--jira-base-url` | Override `JIRA_BASE_URL` (default: env var) |
| `--jira-user` | Override `JIRA_USER` (default: env var) |
| `--jira-pat` | Override `JIRA_PAT` (default: env var) |
| `--jira-timezone` | Override `JIRA_TIMEZONE` (default: `Europe/Moscow`) |
| `--log-level` | Override `LOG_LEVEL` (default: `INFO`) |

Example — register only, non-interactive:

```bash
python install.py --non-interactive --register-only
```

---

## 🗑️ `uninstall`

Reverses the installation in 4 steps:

1. ✅ Remove `jira-tempo` from VS Code `mcp.json` (backup `mcp.json.bak` first;
   other servers preserved).
2. ⚠️ Delete `.env` — optional, **default: No**. Irreversible; requires
   explicit confirmation. The PAT value is never printed.
3. ⚠️ Uninstall the pip package from the venv — optional, **default: No**.
   The `.venv` directory itself is kept.
4. ✅ Print a summary with next steps.

```bash
jira-tempo-mcp uninstall
```

---

## ℹ️ `--version` / `--help`

```bash
jira-tempo-mcp --version
# jira-tempo-mcp 0.4.1

jira-tempo-mcp --help
# prints the usage block shown above
```

---

## 🔧 Direct module invocation

If the console script is not on `PATH` (e.g. running outside the venv),
invoke the module directly:

```bash
python -m jira_tempo_mcp.server        # serve
python -m jira_tempo_mcp               # __main__ dispatches to serve
python install.py                      # install
python install.py uninstall            # uninstall
```

---

## 📊 Exit codes

| Code | Meaning |
| --- | --- |
| `0` | ✅ success |
| `1` | ❌ installer/uninstaller error (e.g. `install.py` not found) |
| `2` | ❌ unknown subcommand |

---

## ➡️ Next steps

- 🌐 [api.md](api.md) — MCP tools exposed by `serve`
- 📦 [installation.md](installation.md) — installer walkthrough
- ⚙️ [configuration.md](configuration.md) — env vars read at startup
