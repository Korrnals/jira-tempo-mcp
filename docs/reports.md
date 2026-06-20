# Weekly reports

The `generate_weekly_report` tool produces a `.txt` weekly work report from
Tempo worklogs.

## How it works

1. Fetches all Tempo worklogs for the target week (Mon–Fri).
2. Groups worklogs by issue key.
3. Maps known issues to stable report sections (via `REPORT_SECTION_MAP`).
4. Fetches Jira issue summaries for unknown issues.
5. Writes `<prefix>_<DDMMYY>-<DDMMYY>.txt` to the configured output directory.

## Filename format

```text
<prefix>_<DDMMYY>-<DDMMYY>.txt
```

- `<prefix>` — `REPORT_FILENAME_PREFIX` (default: `JIRA_USER`)
- `<DDMMYY>-<DDMMYY>` — Monday–Friday dates of the target week

Example: `your-username_160620-200620.txt`

## Section mapping

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

Issues not in the map are grouped under their Jira summary.

## Stable order

Force specific issue keys to always appear in a fixed order (if they have
worklogs):

```bash
export REPORT_STABLE_ORDER='["PROJECT-100", "PROJECT-101", "PROJECT-102"]'
```

Issues in `REPORT_STABLE_ORDER` appear first, in the given order. Remaining
issues follow in insertion order.

## Non-issue sections

Add section titles that have no issue key (e.g. meetings, admin work):

```bash
export REPORT_NON_ISSUE_SECTIONS='["Team meetings", "Jira triage"]'
```

These sections appear in the report with their title only — no issue key
prefix. They are placeholders for work that is not tied to a specific
Jira issue.

## Other report variables

| Variable | Default | Effect |
| --- | --- | --- |
| `REPORT_OUTPUT_DIR` | `./reports` | Base directory for report files |
| `REPORT_AUTHOR_NAME` | `JIRA_USER` | Author display name in the report header |
| `REPORT_FILENAME_PREFIX` | `JIRA_USER` | Prefix for report filenames |

## Example report

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

## Path traversal protection

The `output_dir` parameter of `generate_weekly_report` is validated against
path traversal. The resolved path must be inside the allowed root
(`REPORT_OUTPUT_DIR` or `./reports`). Paths like `../../etc` are rejected
with an explicit error.

## Next steps

- [api.md#generate_weekly_report](api.md#generate_weekly_report) — tool parameters
- [configuration.md](configuration.md#weekly-report-optional) — all report env vars
- [troubleshooting.md](troubleshooting.md) — report-related errors
