# 📝 Weekly reports

The `generate_weekly_report` tool produces a `.txt` weekly work report from
Tempo worklogs.

---

## 📝 How it works

1. Fetches all Tempo worklogs for the target week (Mon–Fri).
2. Groups worklogs by issue key.
3. Maps known issues to stable report sections (via `REPORT_SECTION_MAP`).
4. Fetches Jira issue summaries for unknown issues.
5. Writes `<prefix>_<YYYY-MM-DD>_<YYYY-MM-DD>.txt` to the configured output directory.

---

## 📄 Filename format

```text
<prefix>_<YYYY-MM-DD>_<YYYY-MM-DD>.txt
```

- `<prefix>` — `REPORT_FILENAME_PREFIX` (default: `JIRA_USER`)
- `<YYYY-MM-DD>_<YYYY-MM-DD>` — Monday–Friday dates of the target week (ISO 8601, separated by `_`)

> 💡 **Tip:** Example: `your-username_2026-06-16_2026-06-20.txt`

---

## 🗺️ Section mapping

Map issue keys to report section titles via env vars:

```bash
# Option 1: inline JSON
export REPORT_SECTION_MAP='{"PROJECT-100":"Development","PROJECT-101":"Code review"}'

# Option 2: JSON file
export REPORT_SECTION_MAP_FILE=/path/to/sections.json
```

`sections.json` format:

```json
{
  "PROJECT-100": "Development",
  "PROJECT-101": "Code review",
  "PROJECT-102": "Infrastructure"
}
```

> 💡 **Tip:** Issues not in the map are grouped under their Jira summary.

---

## 📊 Stable order

Force specific issue keys to always appear in a fixed order (if they have
worklogs):

```bash
export REPORT_STABLE_ORDER='["PROJECT-100", "PROJECT-101", "PROJECT-102"]'
```

Issues in `REPORT_STABLE_ORDER` appear first, in the given order. Remaining
issues follow in insertion order.

---

## 📋 Non-issue sections

Add section titles that have no issue key (e.g. meetings, admin work):

```bash
export REPORT_NON_ISSUE_SECTIONS='["Team meetings", "Jira triage"]'
```

These sections appear in the report with their title only — no issue key
prefix. They are placeholders for work that is not tied to a specific
Jira issue.

---

## ⚙️ Other report variables

| Variable | Default | Effect |
| --- | --- | --- |
| `REPORT_OUTPUT_DIR` | `~/.mcp/jira-tempo-mcp/reports/` | Base directory for report files |
| `REPORT_AUTHOR_NAME` | `JIRA_USER` | Author display name in the report header |
| `REPORT_FILENAME_PREFIX` | `JIRA_USER` | Prefix for report filenames |

---

## 📝 Example report

```text
Weekly report: 16.06.2026 – 20.06.2026
Author: your-username

Development
- PROJECT-100: Implement login flow — 3h 30m
- PROJECT-100: Fix login redirect bug — 1h

Code review
- PROJECT-101: Review PR #42 — 2h

Infrastructure
- PROJECT-102: Rotate CI secrets — 1h 15m

Team meetings
- (no issue key)

Jira triage
- (no issue key)
```

---

## 👥 Team reports

The `generate_team_report` tool produces a `.txt` team report from Tempo
worklogs for multiple Jira users. Each user gets a section with their issue
breakdown; an aggregate summary shows per-user totals, the grand total, and
the top 5 issues across the team.

### 📄 Filename format

```text
team_<YYYY-MM-DD>_<YYYY-MM-DD>.txt
```

> 💡 **Tip:** Example: `team_2026-06-15_2026-06-19.txt`

### 🛡️ Rate-limiting

Team reports issue one Tempo request per user. To avoid hitting the Tempo
rate limit, concurrent requests are bounded by a semaphore:

| Variable | Default | Effect |
| --- | --- | --- |
| `TEMPO_MAX_CONCURRENT_REQUESTS` | `3` | Max concurrent Tempo requests |
| `TEMPO_REQUEST_DELAY_MS` | `100` | Delay (ms) between request batches |
| `TEMPO_MAX_RETRIES` | `3` | Retry attempts on HTTP 429 (exponential backoff: 1s, 2s, 4s) |
| `REPORT_TEAM_OUTPUT_DIR` | empty | Output dir for team reports (empty = use `REPORT_OUTPUT_DIR`) |

> 💡 **Tip:** Users without worklogs are listed in the summary under "Without tracked time".

### 📝 Example team report

```text
Командный отчёт за неделю (15.06.2026 - 19.06.2026):

== alice (10h) ==
  - PROJECT-100 (Section A):
      + Stand support
  - PROJECT-200 (Task B):
      + 2h отработано

== bob (8h) ==
  - PROJECT-100 (Section A):
      + Review PR

== Сводка по команде ==
Всего отработано: 18h

По сотрудникам:
  - alice: 10h
  - bob: 8h

Топ-5 задач команды:
  - PROJECT-100 (Section A): 12h
  - PROJECT-200 (Task B): 6h
```

---

## 🎨 Custom templates

Since v0.2.0 the report rendering is pluggable. Builtin templates:

| Template | Description |
| --- | --- |
| `default` | Weekly report grouped by issue with stable sections (original layout) |
| `weekly_summary` | Compact summary: total hours, top 5 issues, no per-issue detail |
| `team_report` | Team report: per-user sections + aggregate summary |

### 📌 Selecting a template

Pass the `template` parameter to `generate_weekly_report` or
`generate_team_report`, or set the `REPORT_TEMPLATE` env var.

### ➕ Adding custom templates

Place template files in `REPORT_TEMPLATE_DIR` (default:
`~/.config/jira-tempo-mcp/templates/`). Two formats are supported:

> 📖 For the full author reference (complete context table, worklog fields,
> Python protocol, security model), see [templates.md](templates.md).

#### 📜 Jinja2 templates (`.j2`) — safe by default

Loaded into a `SandboxedEnvironment`. The template context includes:
`worklogs`, `config`, `format_seconds`, `format_date`, `users`,
`per_user_worklogs`, `issue_titles`, `monday`, `friday`.

Example `simple.j2`:

```jinja
Total worklogs: {{ worklogs | length }}
Grand total: {{ format_seconds(worklogs | map(attribute='timeSpentSeconds') | sum) }}
```

> ✅ Unsafe constructs (e.g. `{{ config.__class__ }}`) are blocked by the sandbox.

#### 🐍 Python templates (`.py`) — opt-in, code execution risk

Loaded only when `REPORT_TEMPLATE_ALLOW_PY=1`. The module must expose a
`TEMPLATE` attribute implementing the `ReportTemplate` protocol:

```python
class MyTemplate:
    name = "my_template"
    description = "My custom template"

    def render(self, worklogs, config, **kwargs):
        return f"Got {len(worklogs)} worklogs"

TEMPLATE = MyTemplate()
```

> ⚠️ **Warning:** Python templates execute arbitrary code. Only load `.py`
> files from a trusted source. A warning is logged on every load.

### 📋 Listing available templates

Use the `list_report_templates` tool to see all builtin + custom templates.

---

## 🛡️ Path traversal protection

The `output_dir` parameter of `generate_weekly_report` is validated against
path traversal. The resolved path must be inside the allowed root
(`REPORT_OUTPUT_DIR` or `~/.mcp/jira-tempo-mcp/reports/`). Paths like `../../etc` are rejected
with an explicit error.

---

## ➡️ Next steps

- 🌐 [api.md#generate_weekly_report](api.md#generate_weekly_report) — tool parameters
- ⚙️ [configuration.md](configuration.md#weekly-report-optional) — all report env vars
- 🐛 [troubleshooting.md](troubleshooting.md) — report-related errors
