# 📦 Installation

How to install `jira-tempo-mcp` — four paths: interactive installer, pip (PyPI)
/ npm, source, Docker.

---

## 📦 Requirements

| Requirement | Version | Notes |
| --- | --- | --- |
| Python | 3.11+ | 3.12 recommended |
| pip | latest | bundled with Python |
| Jira | Server / Data Center | Tempo Timesheets 4.x installed |
| Jira PAT | — | Personal Access Token (Profile → Personal Access Tokens) |

---

## 🚀 Path 1 — Interactive installer (recommended)

The installer creates a venv, writes `.env`, registers the MCP server in
VS Code, and optionally verifies Jira connectivity:

```bash
cd jira-tempo-mcp
python install.py
```

Steps performed:

1. ✅ Check Python ≥ 3.11
2. ✅ Create `.venv` and install the package (editable, with dev deps)
3. ✅ Write `.env` — prompts for Jira URL, username, PAT (hidden via `getpass`,
   file permissions `0600`)
4. ✅ Register the MCP server in VS Code `mcp.json` — **merges** into the
   existing file, never overwrites other servers. A `mcp.json.bak` backup is
   written first.
5. ✅ Optional Jira connectivity check (`/rest/api/2/myself`)

> 💡 **Tip:** Re-run `python install.py` any time to regenerate `.env` or
> re-register the VS Code config. The installer is idempotent.

### CLI dispatcher compatibility

The installer is also reachable through the package's CLI dispatcher:

```bash
jira-tempo-mcp install --non-interactive --register-only   # equivalent to python install.py
```

> ⚠️ **Note:** `jira-tempo-mcp install` requires a git clone (editable install).
> `install.py` is a dev-setup script: it creates a venv, writes `.env`, registers the
> MCP server, and copies the agent from `copilot-integration/`. It needs access to the
> repository tree (`.env.example`, `copilot-integration/`, `pyproject.toml`). Under a
> wheel or Docker install these files are absent — the command prints a clear error
> with recovery instructions. For Docker-only usage, no install is needed: run the
> server directly via `docker run` (see [Path 4](#-path-4--docker)).

---

## 📥 Path 2 — pip (PyPI) and npm

Install from the package index — either the Python package from PyPI or the
npm wrapper (it installs the Python package under the hood and proxies every
subcommand to the same CLI):

```bash
pip install jira-tempo-mcp
# or the npm wrapper (installs the Python package via pipx → pip)
npm i -g jira-tempo-mcp
```

> 💡 **Tip:** the PyPI and npm listings go live with the next release cut.
> Until publishing is enabled, `pip install` may 404 — fall back to the
> interactive installer (Path 1), source (Path 3), or Docker (Path 4).

Then run whatever you need:

```bash
jira-tempo-mcp serve              # start the MCP server (stdio)
jira-tempo-mcp update             # self-update (pip upgrade)
jira-tempo-mcp install-specialist # install the JTM specialist skill into AI harnesses
```

Configuration is read from environment variables or a `.env` file in the
working directory. See [configuration.md](configuration.md).

> 💡 **Tip:** self-update of a wheel install is one command —
> `jira-tempo-mcp update` (runs `pip install --upgrade jira-tempo-mcp` for
> you). Editable installs get `git pull --ff-only` + reinstall instead; see
> [`update`](cli.md#-update).

### 🤖 Installing the specialist agent (harnesses)

The specialist artefacts ship **inside the wheel** (`jira_tempo_mcp.integration`
package data), so `install-specialist` works from any pip/npm install — a git
clone is **not** required for it. The legacy interactive `jira-tempo-mcp
install` (`.env` setup) still requires a git clone (see Path 1 above).

```bash
jira-tempo-mcp install-specialist                  # all supported harnesses
jira-tempo-mcp install-specialist --harness copilot
jira-tempo-mcp install-specialist --list
jira-tempo-mcp install-specialist --remove
```

Support status per harness — full flags and behavior in
[cli.md](cli.md#-install-specialist):

| Harness | Status | Install locations |
| --- | --- | --- |
| `copilot` | ✅ supported | `~/.copilot/agents/jtm-jira-tempo-reports.agent.md` + `~/.copilot/skills/jira-tempo-reports/` (`SKILL.md` + `JTM_AGENT.md`) |
| `claude` | ✅ supported | `~/.claude/skills/jira-tempo-reports/` — skills-only, no agents file (VS Code cross-scans the claude agents dir and shows a duplicate picker entry) |
| `opencode` | ✅ supported | `~/.config/opencode/skills/jira-tempo-reports/` (skills-only convention) |
| `codex` | ⏭️ skipped | no agent-file convention — `AGENTS.md` is machine-managed |

---

## 🔧 Path 3 — from source

```bash
git clone https://github.com/Korrnals/jira-tempo-mcp.git
cd jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
jira-tempo-mcp serve
```

> 💡 **Tip:** On Windows PowerShell replace `source .venv/bin/activate` with
> `.venv\Scripts\Activate.ps1`.

---

## 🐳 Path 4 — Docker

The image is published to GitHub Container Registry on every `v*` tag:

```bash
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

The container runs `jira-tempo-mcp serve` over stdio. Secrets are **never**
baked into the image — pass them at runtime via `--env-file` or a
Kubernetes Secret. See [deployment.md](deployment.md) for build details.

---

## 🔁 Install modes

Paths 2–4 put the same package on disk in three different ways — the
difference matters when you update:

| Mode | How you got it | Update to the latest |
| --- | --- | --- |
| **Wheel** (package index) | `pip install jira-tempo-mcp` / `pipx`, or the npm wrapper (it installs the same Python package) | `jira-tempo-mcp update` (runs `pip install --upgrade jira-tempo-mcp`), or the pip command directly |
| **Editable** (git checkout) | `pip install -e .` from a cloned repo | `jira-tempo-mcp update` detects the mode and runs `git pull --ff-only` in the checkout, then `pip install -e .` to refresh metadata — or run both steps by hand |
| **Docker image** | `ghcr.io/korrnals/jira-tempo-mcp`, tags `:X.Y.Z` and `:latest` | `docker pull` a newer tag and restart the container |

`update` classifies the installation via pip's `direct_url.json` into modes
`wheel` and `editable` and prints the detected mode as its first line. When
the package is not pip-installed at all (Docker image, bare `PYTHONPATH`
run), it does not guess — it prints per-kind guidance and exits without
changing anything. See [`update`](cli.md#-update) for the full behavior.

> 💡 **Tip: how to tell which mode you have.** `pip show jira-tempo-mcp`
> prints an `Editable project location` line for an editable install and no
> such line for a wheel install (the underlying marker is pip's
> `direct_url.json`). If you run `jira-tempo-mcp` straight from a repo
> checkout, you are almost certainly in editable mode.

---

## 🛠️ Creating a venv manually

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The `[dev]` extra installs `ruff`, `mypy`, `pytest`, `pytest-asyncio`,
`types-pytz`, and `pre-commit`.

---

## 🔍 Verifying the installation

```bash
# Version
jira-tempo-mcp --version

# Start the server (stdio)
jira-tempo-mcp serve
```

If the server starts and logs `Starting jira-tempo-mcp for <your-jira-url>`
on stderr, the installation is correct. The server speaks stdio — it reads
JSON-RPC from stdin and writes to stdout.

---

## ➡️ Next steps

- ⚙️ [configuration.md](configuration.md) — all environment variables
- 🔌 [mcp-integration.md](mcp-integration.md) — wire the server into VS Code
- 🖥️ [cli.md](cli.md) — CLI commands reference
