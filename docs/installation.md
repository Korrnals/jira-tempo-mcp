# 📦 Installation

How to install `jira-tempo-mcp` — four paths: interactive installer, pip,
source, Docker.

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

---

## 📥 Path 2 — pip (published package)

> ⚠️ **Not yet available.** The package is **not published to PyPI** while
> GitHub Actions are disabled and the `pypi-publish` job is guarded by
> `if: false` (see [deployment.md](deployment.md)). `pip install
> jira-tempo-mcp` will fail with a 404. Until PyPI publishing is enabled, use
> the **interactive installer** (Path 1), an **editable install from source**
> (Path 3), or **Docker** (Path 4).

The command below is the intended flow once the package is published:

```bash
pip install jira-tempo-mcp
jira-tempo-mcp serve
```

Configuration is read from environment variables or a `.env` file in the
working directory. See [configuration.md](configuration.md).

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
