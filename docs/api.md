# API — MCP tools

The server exposes 9 tools over the Model Context Protocol. Each tool is
defined in `src/jira_tempo_mcp/server.py` and dispatched through a table
(`_TOOL_HANDLERS`).

## Tool index

| Tool | Purpose |
| --- | --- |
| [`list_worklogs`](#list_worklogs) | List Tempo worklogs for a date range or single day |
| [`get_worklog`](#get_worklog) | Get a single worklog by Tempo ID |
| [`create_worklog`](#create_worklog) | Track time on a Jira issue |
| [`delete_worklog`](#delete_worklog) | Delete a worklog by ID |
| [`get_issue`](#get_issue) | Get Jira issue metadata |
| [`list_favorite_issues`](#list_favorite_issues) | List favorite issues for the current user |
| [`generate_weekly_report`](#generate_weekly_report) | Generate a weekly `.txt` report |
| [`generate_team_report`](#generate_team_report) | Generate a team report for multiple users |
| [`list_report_templates`](#list_report_templates) | List available report templates |

---

## `list_worklogs`

List Tempo worklogs for a date range (or a single day). Only actually
tracked time is returned — planned time is excluded.

**Parameters:**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `date_from` | string | no | Start date (ISO `YYYY-MM-DD`). Defaults to today. |
| `date_to` | string | no | End date (ISO `YYYY-MM-DD`). Defaults to `date_from`. |

**Example call:**

```json
{
  "name": "list_worklogs",
  "arguments": {
    "date_from": "2026-06-16",
    "date_to": "2026-06-20"
  }
}
```

**Returns:** one line per worklog:

```text
Worklogs 2026-06-16 .. 2026-06-20 (5 entries):
- 2026-06-16 | PROJECT-100 | 1h 30m | id=12345 | Implemented login flow
- 2026-06-17 | PROJECT-101 | 2h | id=12346 | Code review
```

---

## `get_worklog`

Get a single Tempo worklog by its Tempo internal ID.

**Parameters:**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `worklog_id` | string | yes | Tempo worklog ID |

**Example call:**

```json
{
  "name": "get_worklog",
  "arguments": { "worklog_id": "12345" }
}
```

**Returns:** key/value lines with all worklog fields:

```text
Worklog 12345:
  tempoWorklogId: 12345
  issueKey: PROJECT-100
  timeSpentSeconds: 5400
  startDate: 2026-06-16
  comment: Implemented login flow
```

---

## `create_worklog`

Track (log) time on a Jira issue via Tempo. The worklog is attributed to
the token owner unless `author_account_id` is given.

**Parameters:**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `issue_key` | string | yes | Jira issue key (e.g. `PROJECT-100`) |
| `time_spent` | string | yes | Human duration: `1h 30m`, `2h`, `45m`, `1d 2h` |
| `comment` | string | no | Optional worklog comment |
| `date_started` | string | no | ISO 8601 datetime with tz. Defaults to now. |
| `author_account_id` | string | no | Optional Tempo worker key. Defaults to token owner. |

**Duration units:** `w` (week = 5d), `d` (day = 8h), `h` (hour), `m` (minute).

**Example call:**

```json
{
  "name": "create_worklog",
  "arguments": {
    "issue_key": "PROJECT-100",
    "time_spent": "1h 30m",
    "comment": "Implemented login flow",
    "date_started": "2026-06-19T10:00:00+03:00"
  }
}
```

**Returns:**

```text
Tracked 1h 30m on PROJECT-100 at 2026-06-19T10:00:00+03:00. Worklog ID: 12345. Comment: Implemented login flow
```

---

## `delete_worklog`

Delete a Tempo worklog by its ID. Use for undo/correction of mis-tracked
time.

**Parameters:**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `worklog_id` | string | yes | Tempo worklog ID to delete |

**Example call:**

```json
{
  "name": "delete_worklog",
  "arguments": { "worklog_id": "12345" }
}
```

**Returns:**

```text
Deleted worklog 12345.
```

---

## `get_issue`

Get Jira issue metadata: summary, status, project.

**Parameters:**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `issue_key` | string | yes | Jira issue key (e.g. `PROJECT-100`) |

**Example call:**

```json
{
  "name": "get_issue",
  "arguments": { "issue_key": "PROJECT-100" }
}
```

**Returns:**

```text
PROJECT-100: Implement login flow
Status: In Progress
Project: Web Platform
```

---

## `list_favorite_issues`

List favorite issues for the current Jira user. Returns keys and summaries.

**Parameters:** none.

**Example call:**

```json
{
  "name": "list_favorite_issues",
  "arguments": {}
}
```

**Returns:**

```text
Favorite issues (3):
- PROJECT-100: Implement login flow
- PROJECT-101: Code review process
- PROJECT-102: Fix CI pipeline
```

---

## `generate_weekly_report`

Generate a weekly work report from Tempo worklogs and save it as a `.txt`
file. Groups worklogs by issue, maps known issues to stable sections, and
writes `<prefix>_<DDMMYY>-<DDMMYY>.txt` to the configured output directory.

**Parameters:**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `target_date` | string | no | Any date within the target week (ISO `YYYY-MM-DD`). Defaults to today. |
| `output_dir` | string | no | Output directory. Defaults to `REPORT_OUTPUT_DIR` env or `./reports`. Must be inside the allowed root. |
| `template` | string | no | Template name (e.g. `default`, `weekly_summary`). Defaults to `REPORT_TEMPLATE` env or `default`. Use `list_report_templates` to see available templates. |

**Example call:**

```json
{
  "name": "generate_weekly_report",
  "arguments": { "target_date": "2026-06-19" }
}
```

**Returns:**

```text
Weekly report generated: /path/to/reports/your-username_160620-200620.txt
```

See [reports.md](reports.md) for report customization (section mapping,
stable order, non-issue sections).

---

## `generate_team_report`

Generate a team work report from Tempo worklogs for multiple Jira users.
Fetches worklogs per user with bounded concurrency (rate-limit safe), renders
per-user sections plus an aggregate summary, and writes
`team_<DDMMYY>-<DDMMYY>.txt` to the configured output directory.

**Parameters:**

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `users` | array<string> | yes | Jira usernames to include (non-empty) |
| `date_from` | string | no | Start date (ISO `YYYY-MM-DD`). Defaults to Monday of the current week. |
| `date_to` | string | no | End date (ISO `YYYY-MM-DD`). Defaults to Friday of the current week. |
| `section_map` | object | no | Optional override for `REPORT_SECTION_MAP` (issue key → section title) |
| `template` | string | no | Template name. Defaults to `team_report`. |
| `output_dir` | string | no | Output directory. Defaults to `REPORT_TEAM_OUTPUT_DIR` or `REPORT_OUTPUT_DIR`. Must be inside the allowed root. |

**Rate-limiting:** concurrent Tempo requests are bounded by
`TEMPO_MAX_CONCURRENT_REQUESTS` (default 3). A configurable delay
(`TEMPO_REQUEST_DELAY_MS`, default 100 ms) is inserted between batches.
On HTTP 429 the client retries with exponential backoff up to
`TEMPO_MAX_RETRIES` (default 3) times.

**Example call:**

```json
{
  "name": "generate_team_report",
  "arguments": {
    "users": ["alice", "bob", "carol"],
    "date_from": "2026-06-15",
    "date_to": "2026-06-19"
  }
}
```

**Returns:**

```text
Team report written: /path/to/reports/team_150626-190626.txt
Grand total: 24h across 3 users.
Per-user totals:
  - alice: 10h
  - bob: 8h
  - carol: 6h
Top issues:
  - PROJECT-100 (Implement login flow): 12h
  - PROJECT-101 (Code review process): 5h
```

---

## `list_report_templates`

List available report templates (builtin + custom). Returns each template's
name and description. Custom templates are discovered from
`REPORT_TEMPLATE_DIR`.

**Parameters:** none.

**Example call:**

```json
{
  "name": "list_report_templates",
  "arguments": {}
}
```

**Returns:**

```text
Report templates (4):
- default: Weekly report grouped by issue with stable sections...
- team_report: Team report: per-user sections with issue breakdown...
- weekly_summary: Compact weekly summary: total hours, top 5 issues...
- custom: My custom Jinja2 template
```

See [reports.md#custom-templates](reports.md#custom-templates) for how to
add custom templates.

---

## Error handling

All tools return a user-friendly error string on failure (never a raw
exception trace). Common error patterns:

| Error | Cause |
| --- | --- |
| `Invalid issue key '...'` | key does not match `^[A-Z][A-Z0-9]+-\d+$` |
| `Invalid date for ...` | date is not ISO `YYYY-MM-DD` |
| `Could not parse duration: '...'` | `time_spent` has no valid `w/d/h/m` tokens |
| `Jira/Tempo API error: 401 ...` | invalid or expired PAT |
| `output_dir '...' resolves outside the allowed root` | path traversal attempt |
| `Could not identify your Tempo worker key` | `JIRA_USER` mismatch or Tempo connectivity |

## Next steps

- [reports.md](reports.md) — weekly report customization
- [configuration.md](configuration.md) — env vars that affect tool behavior
- [architecture.md](architecture.md) — how tools are dispatched
