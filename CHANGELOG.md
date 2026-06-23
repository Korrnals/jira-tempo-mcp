# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-06-23

### Added

- **New MCP tools:**
  - `list_issues_by_jql` — arbitrary JQL search (read-only, max 100 results).
  - `get_current_user` — authenticated user info (username, displayName, email, key, active).
- **`REPORT_TEAM_USERS` env var** — default list of Jira usernames for team/tasks reports. When set, `generate_team_report` and `generate_tasks_report` can be called without the `users` parameter.
- **`username` parameter on `generate_weekly_report`** — generate weekly reports for any user, not just the configured `JIRA_USER`. Affects filename prefix, report header, and worker key resolution.
- **Dynamic Tempo work attributes** — `create_worklog` proactively queries Tempo for required work attributes on validation failure and returns an actionable hint with attribute names and types.
- **`get_work_attributes()` client method** — queries Tempo `/work-attributes` endpoint (graceful degradation on 404).
- **Report directory structure** — reports organized into subdirectories: `weekly/`, `team/`, `tasks/`, `tasks-team/` under the month directory.
- **`Reports directory:` line** in all report tool results — shows the output directory path.
- **Default report directory** — changed from `Path.cwd()/"reports"` to `~/.mcp/jira-tempo-mcp/reports` (stable across CWD changes).
- 34 new tests (185 → 219): bug/UX coverage, username override, REPORT_TEAM_USERS.

### Changed

- **Markdown report redesign** — all 3 MD report types (weekly, team, tasks) now use professional table-based layout: summary table at top, top-5 issues, per-user tables with total rows. Task summaries truncated to 50 chars, comments to 80 chars with `…`.
- **`get_issue` expanded** — now returns 8 fields (was 3): added priority, assignee, duedate, issuetype, components.
- **`get_worklog` formatted output** — structured key/value display instead of raw Python dict repr. Nested attributes expanded.
- **`list_user_tasks` shows comments** — last 2 comments displayed inline with 💬 marker (was only comment count).
- **`create_worklog` returns full details** — after successful creation, returns complete worklog info (no need for separate `get_worklog` call).
- **ISO dates in filenames** — all report filenames use `2026-06-15_2026-06-19` format (was `150626-190626`).
- **`.env.example` rewrite** — clean sections (Required / Optional / Report config / Advanced), all env vars documented.
- **`search_users` description** — updated to mention email fragment search.

### Fixed

- **`list_user_tasks` status_filter with Russian statuses** (BUG-1) — JQL now uses `statusCategory` mapping instead of localized `status` names. Russian status names ("В работе", "Ожидание", etc.) mapped to category keys.
- **`create_worklog` without required attributes** (BUG-2) — returns actionable error message listing required Tempo work attributes instead of raw API error.
- **`list_worklogs` invalid date** (BUG-3) — local date validation via `_validate_date` before API call (was 500 from server with Java stack trace).
- **`list_worklogs` reversed date range** (BUG-4) — validation error when `date_from > date_to` (was silent 0 results).
- **`generate_team_report` file overwrite** (BUG-5) — filename includes hash of sorted usernames, so different user sets produce different files.
- **`list_favorite_issues` 404 handling** (BUG-6) — distinguishes "endpoint unavailable" from "empty favorites list" with appropriate messages.
- **`parse_tempo_date` critical fix** (BUG-7) — Tempo API returns dates with space separator (`"2026-06-15 00:00:00.000"`) instead of ISO `T`. Now normalized before parsing. This was causing all weekly reports to show 0h.
- **404 noise from `/workers` endpoint** (UX-1) — class-level cache suppresses repeated 404 logs after first failure.

## [0.2.0] — 2026-06-20

### Added

- **Team reports** — new `generate_team_report` MCP tool aggregates worklogs
  for multiple Jira users into a single `.txt` report with per-user sections
  and an aggregate summary (per-user totals, grand total, top 5 issues).
- **Rate-limiting for team reports** — concurrent Tempo requests are bounded
  by `asyncio.Semaphore` (`TEMPO_MAX_CONCURRENT_REQUESTS`, default 3), with a
  configurable delay between batches (`TEMPO_REQUEST_DELAY_MS`, default 100 ms)
  and exponential backoff on HTTP 429 (`TEMPO_MAX_RETRIES`, default 3).
- **Custom report templates** — new template system with a `ReportTemplate`
  protocol and a `TemplateRegistry`. Builtin templates: `default`,
  `weekly_summary`, `team_report`.
- **Jinja2 templates** — `.j2` files discovered from `REPORT_TEMPLATE_DIR`
  are loaded into a `SandboxedEnvironment` (safe by default).
- **Python templates (opt-in)** — `.py` templates loaded only when
  `REPORT_TEMPLATE_ALLOW_PY=1` (code execution risk, explicit opt-in).
- **`list_report_templates` MCP tool** — lists builtin + custom templates.
- **`template` parameter** on `generate_weekly_report` and
  `generate_team_report` to select a template by name.
- New env vars: `TEMPO_MAX_CONCURRENT_REQUESTS`, `TEMPO_REQUEST_DELAY_MS`,
  `TEMPO_MAX_RETRIES`, `REPORT_TEAM_OUTPUT_DIR`, `REPORT_TEMPLATE`,
  `REPORT_TEMPLATE_PATH`, `REPORT_TEMPLATE_DIR`, `REPORT_TEMPLATE_ALLOW_PY`.
- `jinja2>=3.1` added to dependencies.

### Changed

- `generate_weekly_report` now resolves templates through the registry;
  without a `template` argument it falls back to the `default` builtin,
  preserving the exact previous output (backward compatible).
- Report rendering logic extracted into `src/jira_tempo_mcp/templates/`
  package; `report.py` delegates to the selected template.
- Architecture diagram updated to include the templates and team_report
  modules.

### Fixed

- Worklogs returned by Tempo with dates slightly outside the target week
  are now filtered out before rendering (defensive date-range check).

### Security

- Jinja2 templates run in `SandboxedEnvironment` — unsafe constructs
  (e.g. `{{ config.__class__ }}`) are blocked.
- Python templates require explicit opt-in via `REPORT_TEMPLATE_ALLOW_PY=1`
  and log a warning on load.
- `output_dir` for team reports is validated against path traversal, same
  as the weekly report.

### Documentation

- Bilingual docs (EN/RU) updated: `api.md`, `reports.md`,
  `configuration.md`, `architecture.md`, `README.md`.
- New sections: "Team reports", "Custom templates".
- New env vars documented in `configuration.md`.

## [0.1.0] — 2026-06-19

### Added

- Initial release — MCP server for self-hosted Jira (Server / Data Center)
  + Tempo Timesheets 4.
- MCP tools: `list_worklogs`, `get_worklog`, `create_worklog`,
  `delete_worklog`, `get_issue`, `list_favorite_issues`,
  `generate_weekly_report`.
- Async `httpx` client with PAT auth, TLS verification, no redirects.
- Pydantic-validated `Config` with secrets masked in `__repr__`.
- Interactive installer (`jira-tempo-mcp install`) for venv, `.env`, and
  VS Code MCP registration.
- Docker image (multi-stage, non-root, `.dockerignore` for secrets).
- CI/CD pipeline (ruff + mypy + pytest) and release workflow (PyPI + GHCR).
- Bilingual documentation (EN/RU).

### Security

- Tokens never logged; URLs redacted; API error bodies truncated to 200
  chars.
- `output_dir` validated against path traversal.
- `.env` gitignored and created with `0600` permissions.
