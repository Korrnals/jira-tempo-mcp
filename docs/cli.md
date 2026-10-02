# 🖥️ CLI reference

The `jira-tempo-mcp` console script dispatches between the MCP server, the
interactive installer, the uninstaller, the self-update command, and the
specialist installer.

---

## 🖥️ Commands

```text
jira-tempo-mcp                  # start the MCP server (default = serve)
jira-tempo-mcp serve            # start the MCP server (stdio)
jira-tempo-mcp install          # interactive installer (venv + .env + VS Code)
jira-tempo-mcp uninstall        # reverse the installation
jira-tempo-mcp update           # self-update the installed package
jira-tempo-mcp install-specialist  # install the JTM agent into AI harnesses
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

## � `update`

Self-updates the installed package. Detects the install mode (from pip's
`direct_url.json`) and runs the matching procedure:

| Install mode | What runs |
| --- | --- |
| Wheel / package index (PyPI, a wheel file, local non-editable) | `pip install --upgrade jira-tempo-mcp` |
| Editable (`pip install -e .` from a git checkout) | `git pull --ff-only` in the checkout, then `pip install -e .` to refresh metadata |
| Not pip-installed (Docker image, bare `PYTHONPATH` run) | No guess — prints per-kind guidance (e.g. `docker pull ghcr.io/korrnals/jira-tempo-mcp:latest`) and exits `1` |

```bash
jira-tempo-mcp update
```

Example output (wheel install):

```text
Install mode: wheel — installed from a package index (no direct_url.json)
--> pip install --upgrade jira-tempo-mcp: /path/to/python -m pip install --upgrade jira-tempo-mcp
Update complete.
Version: 0.6.0 -> 0.7.0
If an MCP server (jira-tempo-mcp serve) is running, restart it to pick up the new code.
```

Notes:

- pip runs through the **current interpreter** (`sys.executable -m pip`) — the
  update lands in the same environment/venv `update` was invoked from.
- A failed step aborts the update — nothing else is changed; the exit code is
  `1`.
- Takes no flags; unknown flags exit with `2`.

---

## 🤖 `install-specialist`

Installs the **JTM: Jira Tempo Reports** specialist (agent file + skill +
knowledge doc) into AI harnesses. Idempotent: re-installing overwrites
JTM-owned files and creates a timestamped backup (`<name>.bak.YYYYMMDD-HHMMSS`)
first; other harness files are never touched. Reversible with `--remove`.

### 🔧 Flags

| Flag | Effect |
| --- | --- |
| `--harness NAME` | Install only the named harness(es); repeatable (`--harness copilot --harness claude`); default: all supported (unsupported ones are skipped with an explicit reason) |
| `--list` | List the support status of every registered harness and exit |
| `--remove` | Uninstall the specialist from the selected harnesses (default: all); deletes only JTM-owned files, prints "nothing to remove — already clean" when nothing is installed |

`--harness`, `--list` and `--remove` are mutually exclusive. Unknown harness
names are rejected before anything is written.

### 🧩 Harness support

| Harness | Status | Files installed |
| --- | --- | --- |
| `copilot` | ✅ supported | `~/.copilot/agents/jtm-jira-tempo-reports.agent.md`, `~/.copilot/skills/jira-tempo-reports/` (`SKILL.md` + `JTM_AGENT.md`) |
| `claude` | ✅ supported | `~/.claude/agents/jtm-jira-tempo-reports.md`, `~/.claude/skills/jira-tempo-reports/` (`SKILL.md` + `JTM_AGENT.md`) |
| `opencode` | ✅ supported | `~/.config/opencode/skills/jira-tempo-reports/` (`SKILL.md` + `JTM_AGENT.md`) — skills-only convention |
| `codex` | ⏭️ skipped | unsupported: no agent-file convention — `AGENTS.md` is machine-managed, safe manual placement is not defined |

Actual `--list` output:

```text
Supported harnesses:
  copilot    supported                                               VS Code Copilot Chat (agents + skills)
  claude     supported                                               Claude Code (agents + skills)
  opencode   supported                                               OpenCode (skills directory)
  codex      skipped — unsupported: no agent-file convention (AGENTS.md is machine-managed; safe manual placement is not defined) OpenAI Codex CLI
```

### 💡 Examples

```bash
# Install into all supported harnesses (default)
jira-tempo-mcp install-specialist

# Target specific harnesses only
jira-tempo-mcp install-specialist --harness copilot --harness claude

# Show support status
jira-tempo-mcp install-specialist --list

# Uninstall (from all, or selected with --harness)
jira-tempo-mcp install-specialist --remove
```

Unknown harness name (usage block omitted):

```text
jira-tempo-mcp install-specialist: error: unknown harness(es): nonexistent.
Known: claude, codex, copilot, opencode. Use --list to show support status.
```

Works from a **wheel install** — the specialist files ship inside the wheel
(`jira_tempo_mcp.integration` package data), no git clone needed. The legacy
interactive `jira-tempo-mcp install` (`.env` setup) still requires a git
clone; see [installation.md](installation.md).

---

## �🗑️ `uninstall`

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
# jira-tempo-mcp 0.6.0

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
python -m jira_tempo_mcp.cli --version # version via the dispatcher
python -m jira_tempo_mcp.cli update    # self-update
python -m jira_tempo_mcp.cli install-specialist --list
python install.py                      # install
python install.py uninstall            # uninstall
```

---

## 📊 Exit codes

| Code | Meaning |
| --- | --- |
| `0` | ✅ success |
| `1` | ❌ subcommand error (installer/uninstaller, `update`, `install-specialist`) |
| `2` | ❌ unknown subcommand, flag, or harness name |

---

## ➡️ Next steps

- 🌐 [api.md](api.md) — MCP tools exposed by `serve`
- 📦 [installation.md](installation.md) — installer walkthrough
- ⚙️ [configuration.md](configuration.md) — env vars read at startup
