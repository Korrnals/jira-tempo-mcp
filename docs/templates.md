# 🎨 Report templates — reference

How to write, register, and select custom report templates for
`jira-tempo-mcp`. This is the **author reference** for people (and agents)
building their own templates. For a one-paragraph overview and the builtin
template list, see [reports.md](reports.md#-custom-templates).

Templates turn a list of Tempo worklogs into a report string. Rendering is
**pluggable since v0.2.0**: drop a file in a directory and it becomes
selectable by name — no code change, no restart needed beyond reloading the
MCP server config.

---

## 🧩 Two engines

| Engine | Extension | Safe by default? | When to use |
| --- | --- | --- | --- |
| **Jinja2** | `.j2` | ✅ Yes — runs in a `SandboxedEnvironment` | Text layout, loops, formatting (recommended for almost all cases) |
| **Python** | `.py` | ⚠️ No — runs arbitrary code, **opt-in only** | Logic too complex for a template: external libraries, heavy aggregation, side effects |

Jinja2 is the recommended path. Use a `.py` template only when you need real
Python — and only for files you trust.

---

## 📁 Where templates live

Custom templates are discovered from the **template directory**:

| OS | Default path |
| --- | --- |
| **Linux** | `~/.config/jira-tempo-mcp/templates/` |
| **macOS** | `~/Library/Application Support/jira-tempo-mcp/templates/` |
| **Windows** | `%APPDATA%\jira-tempo-mcp\templates\` |

> The default is `~/.config/jira-tempo-mcp/templates/` on every platform
> (it is built from `Path.home()`). Override it with the
> `REPORT_TEMPLATE_DIR` environment variable.

Anything in this directory is scanned at report-generation time:

- `.j2` files → loaded into the Jinja2 sandbox. The **template name is the file stem** (`standup.j2` → name `standup`).
- `.py` files → loaded only when `REPORT_TEMPLATE_ALLOW_PY=1` (see [§Python templates](#-python-templates-py)).
- Files starting with `_` and subdirectories are ignored.
- Files with any other extension are ignored.

### Discovery & resolution

The loader (`src/jira_tempo_mcp/templates/loader.py`) builds a registry of
**builtin + custom** templates. Resolution priority when a report is generated:

1. `REPORT_TEMPLATE_PATH` — an explicit path to a single template file (loaded ad-hoc, highest priority).
2. `REPORT_TEMPLATE` (or the `template` tool parameter) — a **name** looked up in the registry.
3. Fallback to the builtin **`default`** template if nothing matches.

```
REPORT_TEMPLATE_PATH  →  REPORT_TEMPLATE / template param  →  "default"
```

---

## 📜 Jinja2 templates (`.j2`)

A `.j2` file is plain text with Jinja2 syntax (`{{ ... }}` for output,
`{% ... %}` for statements). It is loaded into a
[`SandboxedEnvironment`](https://jinja.palletsprojects.com/en/stable/sandbox/)
with these settings:

| Setting | Value | Effect |
| --- | --- | --- |
| `autoescape` | `False` | Output is plain text, not HTML — no entity escaping |
| `trim_blocks` | `True` | A block tag on its own line does not leave a blank line |
| `lstrip_blocks` | `True` | Leading whitespace before a block tag is stripped |

Because `autoescape=False`, what you write is exactly what you get. Use
`trim_blocks`/`lstrip_blocks` to keep the rendered report free of stray blank
lines.

### 🧠 Jinja2 context reference

When the template is rendered, the following variables are available. These
are the only names guaranteed to be present; anything else comes from
implementation kwargs and is **not** part of the stable contract.

| Variable | Type | Description |
| --- | --- | --- |
| `worklogs` | `list[dict]` | The week's Tempo worklogs (see [§Worklog fields](#-worklog-fields)). Empty list if no time was tracked. |
| `config` | `Config` | The runtime [`Config`](configuration.md) object. Read fields like `config.jira_user`, `config.report_author_header`. |
| `monday` | `date \| None` | Monday of the target week (a `datetime.date`). |
| `friday` | `date \| None` | Friday of the target week. |
| `users` | `list` | Ordered user list — `(username, display_name)` tuples for team reports; empty for single-user reports. |
| `per_user_worklogs` | `dict[str, list[dict]]` | `username → worklogs` mapping (team reports). Empty for single-user reports. |
| `issue_titles` | `dict[str, str]` | `issue_key → human summary` (e.g. `{"PROJ-123": "Fix login bug"}`). |
| `summary` | `str` | Short aggregate summary string (team reports). May be empty. |
| `format_seconds(seconds)` | callable | Human-readable duration, e.g. `format_seconds(5400)` → `"1ч 30м"`. |
| `format_date(d)` | callable | Date formatted as `DD.MM.YYYY`, e.g. `format_date(monday)` → `"08.06.2026"`. |

> **Note:** Only `format_seconds` and `format_date` are injected as callables.
> The shared helpers `format_date_short`, `week_range`, `extract_issue_key`,
> `extract_seconds` are **not** available inside `.j2` templates — use Jinja
> filters or Python templates if you need them.

Any additional keyword arguments passed by the renderer are also exposed, but
they are implementation details and may change between versions. Stick to the
table above for portable templates.

### 📦 Worklog fields

`worklogs` is a list of raw Tempo Timesheets 4 worklog objects. The fields
the builtin templates rely on:

| Field | Type | Notes |
| --- | --- | --- |
| `timeSpentSeconds` | `int` | Time logged, in seconds. The primary aggregation key. |
| `issueKey` | `str` | Jira issue key, e.g. `"PROJ-123"`. Falls back to `issue["key"]` if absent. |
| `started` | `str` | When the work was done, e.g. `"2026-06-08 00:00:00.000"`. `startDate` is accepted as a fallback. |
| `comment` | `str \| dict` | The worklog comment. A `dict` with a `content` key is also handled. |
| `authorAccountId` | `str` | Worker's account id. Falls back to `workerKey`, then `author["key"]` / `author["accountId"]`. |

The dict is the unmodified Tempo response, so **additional fields may be
present** (`id`, `description`, `updated`, etc.). They are not relied upon by
the builtins — use them at your own discretion.

### 🔧 Available Jinja2 filters

The sandbox ships the standard Jinja2 filter set. The most useful for reports:

| Filter | Example | Result |
| --- | --- | --- |
| `length` | `{{ worklogs \| length }}` | Number of worklogs |
| `sum` | `{{ worklogs \| map(attribute='timeSpentSeconds') \| sum }}` | Total seconds |
| `groupby` | `{% for key, items in worklogs \| groupby('issueKey') %}` | Group by a field |
| `sort` | `{% for wl in worklogs \| sort(attribute='timeSpentSeconds', reverse=true) %}` | Sort |
| `default` | `{{ wl.comment \| default('—') }}` | Fallback value |

> ❌ Unsafe constructs are blocked by the sandbox: attribute access that
> escapes the object graph (`{{ config.__class__.__mro__ }}`) raises
> `SecurityError`. This is intentional.

### Minimal example

`~/.config/jira-tempo-mcp/templates/simple.j2`:

```jinja2
{# Minimal weekly summary — uses worklogs, monday, friday, format_seconds #}
Week {{ format_date(monday) }} – {{ format_date(friday) }}
Total: {{ format_seconds(worklogs | map(attribute='timeSpentSeconds') | sum) }}
Worklogs: {{ worklogs | length }}
```

Generate with:

```bash
generate_weekly_report(template="simple")
```

---

## 🐍 Python templates (`.py`)

A `.py` template is a Python module that exposes a **`TEMPLATE` attribute**
implementing the `ReportTemplate` protocol:

```python
class ReportTemplate(Protocol):
    name: str
    description: str
    def render(self, worklogs: list[dict], config: Config, **kwargs) -> str: ...
```

The module is imported with `importlib` and `TEMPLATE.render(...)` is called.
The same context as Jinja2 is passed as keyword arguments (`monday`,
`friday`, `issue_titles`, `users`, `per_user_worklogs`, `summary`, ...).

### Example

`~/.config/jira-tempo-mcp/templates/my_report.py`:

```python
from collections import defaultdict

from jira_tempo_mcp.templates._shared import (
    extract_issue_key,
    extract_seconds,
    format_date,
)


class MyReport:
    name = "my_report"
    description = "Per-issue breakdown with totals, sorted by time."

    def render(self, worklogs, config, **kwargs):
        monday = kwargs.get("monday")
        friday = kwargs.get("friday")
        per_issue: dict[str, int] = defaultdict(int)
        for wl in worklogs:
            key = extract_issue_key(wl)
            if key:
                per_issue[key] += extract_seconds(wl)

        lines = [f"Week {format_date(monday)} – {format_date(friday)}", ""]
        for key, secs in sorted(per_issue.items(), key=lambda kv: kv[1], reverse=True):
            hours = secs / 3600
            lines.append(f"{key}: {hours:.1f}h")
        return "\n".join(lines)


TEMPLATE = MyReport()
```

### ⚠️ Security: opt-in only

Python templates execute **arbitrary code**. They are loaded **only** when
`REPORT_TEMPLATE_ALLOW_PY=1`:

```bash
export REPORT_TEMPLATE_ALLOW_PY=1
```

Without this flag, every `.py` file in the template directory is **skipped**
with a warning. A warning is also logged on each load as a reminder to audit
the file. **Only load `.py` templates from a trusted source.**

> If a module fails to load (syntax error, missing `TEMPLATE`, protocol
> mismatch), it is skipped with a warning — the rest of the registry keeps
> working. One broken template never breaks report generation.

---

## ⚙️ Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `REPORT_TEMPLATE` | `default` | Template **name** selected by `generate_weekly_report` / `generate_team_report`. |
| `REPORT_TEMPLATE_PATH` | *(empty)* | Explicit **file path** to a template (overrides `REPORT_TEMPLATE`). |
| `REPORT_TEMPLATE_DIR` | `~/.config/jira-tempo-mcp/templates/` | Directory scanned for custom templates. |
| `REPORT_TEMPLATE_ALLOW_PY` | `0` | Set to `1` to enable `.py` templates (code execution risk). |

The `template` **tool parameter** overrides `REPORT_TEMPLATE` for a single
call. `REPORT_TEMPLATE_PATH` always wins if set.

---

## 🛠️ Workflow: write, preview, generate

1. **Write** a `.j2` file in the template directory.
2. **List** to confirm it was discovered:

   ```
   list_report_templates
   ```

3. **Preview** on sample data (no file written):

   ```
   preview_report_template(template_name="standup", sample_data="default")
   ```

   `sample_data` is `default`, `minimal`, or `empty`.

4. **Generate** a real report:

   ```
   generate_weekly_report(template="standup")
   ```

---

## 📚 Builtin templates

| Name | Description |
| --- | --- |
| `default` | Weekly report grouped by issue with stable sections (original layout). |
| `weekly_summary` | Compact summary: total hours, top 5 issues, no per-issue detail. |
| `team_report` | Team report: per-user sections + aggregate summary. |

These are always available; custom templates are added alongside them. See
[reports.md](reports.md#-custom-templates) for rendered examples.

---

## ➡️ Next steps

- 📝 [reports.md](reports.md) — report formats (txt/md/json), section mapping, examples.
- ⚙️ [configuration.md](configuration.md) — all environment variables.
- 🔌 [mcp-integration.md](mcp-integration.md) — template-related MCP tools.
