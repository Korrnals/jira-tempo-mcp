# ⚙️ Configuration

All configuration is via environment variables. The server reads them at
startup through `config.py` (pydantic-validated, secrets masked in repr).

---

## ⚙️ Environment variables

### 🔌 Jira connection (required)

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `JIRA_BASE_URL` | yes | — | Jira base URL, no trailing slash (e.g. `https://jira.example.com`) |
| `JIRA_USER` | yes | — | Jira username (login) — used for worklog author filtering |
| `JIRA_PAT` | yes | — | Personal Access Token — **never commit this** |

### 🔌 Jira connection (optional)

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `JIRA_TIMEZONE` | no | `Europe/Moscow` | IANA timezone for date/time handling |
| `TEMPO_API_TOKEN` | no | falls back to `JIRA_PAT` | Separate Tempo API token |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `JIRA_HTTP_TIMEOUT` | no | `30.0` | HTTP timeout for Jira/Tempo calls (seconds) |

### 📝 Weekly report (optional)

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `REPORT_OUTPUT_DIR` | no | `~/.mcp/jira-tempo-mcp/reports/` | Base directory for report files; nested `year/month/weekly/` subdirectories are created silently |
| `REPORT_AUTHOR_NAME` | no | `JIRA_USER` | Author display name in the report header |
| `REPORT_SECTION_MAP` | no | empty | JSON dict mapping issue keys to section titles |
| `REPORT_SECTION_MAP_FILE` | no | empty | Path to a JSON file with the section mapping |
| `REPORT_FILENAME_PREFIX` | no | `JIRA_USER` | Prefix for weekly report filenames |
| `REPORT_STABLE_ORDER` | no | empty | JSON list of issue keys that always appear in this order |
| `REPORT_NON_ISSUE_SECTIONS` | no | empty | JSON list of section titles without issue keys |

See [reports.md](reports.md) for details on the report-related variables.

### 👥 Team report rate-limiting (optional)

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `TEMPO_MAX_CONCURRENT_REQUESTS` | no | `3` | Max concurrent Tempo requests in team reports |
| `TEMPO_REQUEST_DELAY_MS` | no | `100` | Delay (ms) between request batches |
| `TEMPO_MAX_RETRIES` | no | `3` | Retry attempts on HTTP 429 (exponential backoff) |
| `REPORT_TEAM_OUTPUT_DIR` | no | empty | Output dir for team reports (empty = `REPORT_OUTPUT_DIR`) |

### 🎨 Custom report templates (optional)

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `REPORT_TEMPLATE` | no | `default` | Template name for `generate_weekly_report` |
| `REPORT_TEMPLATE_PATH` | no | empty | Explicit path to a template file (overrides `REPORT_TEMPLATE`) |
| `REPORT_TEMPLATE_DIR` | no | `~/.config/jira-tempo-mcp/templates/` | Directory scanned for custom templates |
| `REPORT_TEMPLATE_ALLOW_PY` | no | `false` | Opt-in to load `.py` templates (code execution risk) |

See [reports.md#custom-templates](reports.md#-custom-templates) for details on
custom templates.

### 🛠️ Dotenv source (optional)

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MCP_ENV_FILE` | no | empty | Explicit absolute path to `.env.local`; overrides the standard VS Code locations |

---

## 🔗 Configuration source priority

The server assembles configuration from several sources. Priority (highest
to lowest) determines which value wins on conflict:

| # | Source | When it applies |
| --- | --- | --- |
| 1 | **Process environment variables** | Always win — set by MCP-host, systemd, CI/CD, or shell |
| 2 | **MCP-host `.env.local`** | First existing file: `MCP_ENV_FILE` → `~/.config/Code/User/.env.local` (Linux) → `~/Library/Application Support/Code/User/.env.local` (macOS) → `%APPDATA%/Code/User/.env.local` (Windows) |
| 3 | **`.env` in the repo root** | The `.env` file next to `pyproject.toml`; convenient for CLI development |
| 4 | **Hardcoded defaults** | Defined in `config.py` (e.g. `~/.mcp/jira-tempo-mcp/reports/`) |

> 💡 **How it works:** all dotenv files are loaded via
> `load_dotenv(override=False)` — process variables already set are **not**
> overwritten. Files are applied in the order `.env.local` → repo `.env`,
> so for keys absent from the process environment, the first file to load
> (`.env.local`) wins.

> ⚠️ **Scenario this solves:** when calling Python directly from a terminal
> (outside the MCP-host), variables from `.env.local` **were previously not
> picked up** — reports fell into the default directory, requiring manual
> copying. Now a terminal invocation reads the same `.env.local` as the
> MCP server.

---

## 🔑 `.env` for CLI usage

The server loads `.env` from the project root automatically (via
`python-dotenv`). Copy the template and fill in your PAT:

```bash
cp .env.example .env
# Edit .env — set JIRA_PAT
chmod 0600 .env
```

Example `.env`:

```bash
JIRA_BASE_URL=https://jira.example.com
JIRA_USER=your-username
JIRA_PAT=your_personal_access_token_here
JIRA_TIMEZONE=Europe/Moscow
LOG_LEVEL=INFO
```

> 🔒 `.env` is gitignored. The installer creates it with permissions `0600`.

---

## 🔑 `.env.local` for VS Code MCP

VS Code MCP-host reads secrets from a single `envFile` referenced in
`mcp.json`. The recommended pattern is one `.env.local` per user that holds
all MCP-server secrets:

```bash
# ~/.config/Code/User/.env.local
JIRA_PAT=your_personal_access_token_here
TEMPO_API_TOKEN=your_tempo_token_here
```

Then in `mcp.json` reference it by **absolute path** (see
[mcp-integration.md](mcp-integration.md) for why `~` does not work in
sandboxed environments):

```json
{
  "servers": {
    "jira-tempo": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "jira_tempo_mcp.server"],
      "envFile": "/home/your-username/.config/Code/User/.env.local",
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_USER": "your-username",
        "PYTHONPATH": "/path/to/jira-tempo-mcp/src"
      }
    }
  }
}
```

`JIRA_PAT` is injected from `.env.local`; the non-secret vars live in `env`.

---

## 📋 Configuration examples

### Minimal (Jira PAT doubles as Tempo token)

```bash
JIRA_BASE_URL=https://jira.example.com
JIRA_USER=your-username
JIRA_PAT=your_personal_access_token_here
```

### Separate Tempo token

```bash
JIRA_BASE_URL=https://jira.example.com
JIRA_USER=your-username
JIRA_PAT=your_jira_pat
TEMPO_API_TOKEN=your_tempo_api_token
```

### Custom report sections

```bash
REPORT_SECTION_MAP='{"PROJECT-100":"Development","PROJECT-101":"Code review"}'
REPORT_STABLE_ORDER='["PROJECT-100", "PROJECT-101"]'
REPORT_NON_ISSUE_SECTIONS='["Team meetings", "Jira triage"]'
REPORT_FILENAME_PREFIX=your-username
```

---

## 🔒 Secret handling

- `JIRA_PAT` and `TEMPO_API_TOKEN` are masked as `***` in `Config.__repr__`
  — accidental `print(config)` does not leak credentials.
- URLs with embedded credentials are stripped by `_redact()` before logging.
- API error bodies are truncated to 200 characters to reduce noise and
  potential token leakage.

See [architecture.md](architecture.md#-security) for the full security model.

---

## ➡️ Next steps

- 🔌 [mcp-integration.md](mcp-integration.md) — wire the server into VS Code
- 📝 [reports.md](reports.md) — weekly report customization
- 🐛 [troubleshooting.md](troubleshooting.md) — config-related errors
