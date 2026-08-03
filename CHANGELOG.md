# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No unreleased changes._

## [0.3.3] — 2026-08-03

### Added

- **`docker-compose.yml`** — single-service compose for running the MCP server in a container, image pinned to the release tag (e.g. `:0.3.3`), secrets via `.env` file (gitignored). Use `docker compose up -d` to run as a managed service or `docker compose run --rm -T jira-tempo-mcp` to drive the server via stdio.
- **README Quick start Docker block expanded** — two options: `docker run --env-file .env ghcr.io/korrnals/jira-tempo-mcp:<version>` (one-liner) and `docker compose up -d` (managed). Image is published to ghcr for every release with version-pinned + `:latest` tags.
- **Tests for installer agent code paths** (`tests/test_install_agent.py`, 6 cases) — cover `install_copilot_agent` / `uninstall_copilot_agent`, `--no-agent` / `--skip-vscode` skip logic, file copy to correct install destinations, missing-source non-blocking skip, uninstall removes only JTM files (foreign agents/skills untouched), idempotent uninstall. Total suite: 280 → 286.

### Changed

- **`JTM_AGENT.md` fallback scenario** — added mention of read-only tools (`get_worklog`, `list_favorite_issues`, `list_user_tasks`, `search_users`) available in manual composition fallback. Write operations (`create_worklog`, `delete_worklog`) explicitly out of scope (agent is read-only on Jira).

### Fixed

- **README Quick start Docker block** previously used `:latest` tag — now pins to the versioned release tag for reproducibility, with `:latest` documented as the tracking option.

## [0.3.2] — 2026-08-03

### Added

- **Standalone JTM Copilot Chat agent** — a ready-to-use AI agent (`JTM: Jira Tempo Reports`) that produces Jira/Tempo worklog reports predictably via the `jira-tempo` MCP generators. Installs by default with `python install.py` into `~/.copilot/agents/` (agent) and `~/.copilot/skills/jira-tempo-reports/` (skill + universal knowledge doc). Escape hatches: `--no-agent` (skip agent on install), `--uninstall-agent` (remove only the agent, keep the MCP server). See README §"JTM Agent" for the full integration matrix.
- **Universal knowledge doc `JTM_AGENT.md`** — IDE-agnostic 7-type report matrix, MCP-tool mapping, work scenarios, and fallback rules. Works with any MCP-capable agent (Cursor, Claude Code, Continue, Aider) that reads it as context. The VS Code wrapper (`copilot-integration/jtm-jira-tempo-reports.agent.md` + `copilot-integration/jira-tempo-reports.skill.md`) adds the interactive `vscode_askQuestions` picker and VS Code-specific behavior on top of this universal layer.
- **Installer agent integration** — `install.py` extended with `install_copilot_agent()` / `uninstall_copilot_agent()`, `--no-agent` and `--uninstall-agent` flags, and a loud announcement block at the end of install confirming the agent location and one-click usage. Full uninstall (`python install.py uninstall`) now also removes the agent + skill + knowledge doc.
- **README §"JTM Agent"** — new section documenting the agent install locations, VS Code one-click usage, and a harness integration table (VS Code, Cursor, Claude Code, Continue, Aider) with the MCP server JSON entry for non-VS Code harnesses.
- **README Quick start uninstall one-liners** — two copy-pasteable one-liners: full uninstall (`python install.py uninstall` / `curl ... | bash -- --uninstall`) and agent-only uninstall (`python install.py --uninstall-agent`).

### Fixed

- **`JTM_AGENT.md` install location** — the universal knowledge doc was initially copied into `~/.copilot/agents/`, which VS Code Copilot Chat scans for agents — it appeared as a second fake agent in the picker. Fixed: `JTM_AGENT.md` now installs into `~/.copilot/skills/jira-tempo-reports/` (next to `SKILL.md`), which VS Code does not scan for agents.

## [0.3.1] — 2026-08-03

### Added

- **Non-interactive installer mode** (`install.py --non-interactive`).
  Enables setup from CI, scripts, and agents without a TTY. CLI flags
  (`--jira-base-url`, `--jira-user`, `--jira-pat`, `--jira-timezone`,
  `--log-level`) and env-var fallbacks replace interactive prompts.
  `--register-only` skips venv/pip and only writes `~/.config/Code/User/.env.local`
  + registers the MCP server in VS Code `mcp.json`. `--skip-vscode` skips
  VS Code registration. Missing required values exit 1 with a clear stderr
  message instead of raising `KeyError`.
- **`ConfigError` diagnostics for missing required env vars** (`config.py`).
  When `JIRA_BASE_URL`, `JIRA_USER`, or `JIRA_PAT` is empty after
  `load_dotenv()`, `load_config()` raises `ConfigError(ValueError)` with
  backend-specific remediation instructions (VS Code `envFile`, CLI `.env`,
  Docker `--env-file`). The message never contains the secret value —
  only the variable name. Replaces pydantic's generic "field required".
- **26 new tests** (19 for `install.py` non-interactive mode, 7 for
  `ConfigError` diagnostics). 245 → 271 total.

### Fixed

- **Broken bullet rendering in worklog reports (all types, all formats).**
  Multi-line worklog comments were collapsed into a single line and templates
  prepended their own marker, producing duplicated markers (`+ + …`) and merged
  actions. Fixed across TXT, Markdown, and JSON for weekly, team, weekly-summary
  and tasks reports:
  - New pure helpers in `templates/_shared.py`: `strip_bullet_marker`,
    `split_comment_lines`, `render_comment_lines` (TXT), `render_comment_cell`
    (MD `<br>`-joined cells), and `group_worklogs_by_comment_raw` (separates the
    normalized grouping key from the raw render payload so newlines survive).
  - Each action now renders as its own bullet with a single unified marker; the
    human-readable time suffix is attached to the last sub-item only.
  - Markdown cells stay table-safe (escaped pipes, `<br>` line breaks); JSON now
    round-trips the raw multi-line comment faithfully.
  - Grouping and time summation are unchanged.
  - 26 new regression tests (219 → 245).

- **Pagination in `client.py`** for `search_worklogs` / `list_user_tasks` / `search_issues` / `list_users` via a new `_paginated_get` helper. Jira REST responses with >100 items were silently truncated (single-page `maxResults`); now pages through `startAt` / `total`. Covered by new `tests/test_client_pagination.py`.
- **`JiraTempoError` attributes** `status_code` / `response_body` declared on the class — removed 3 unjustified `# type: ignore[attr-defined]`; mypy tracks them natively.
- **Bare `except` narrowed to `except ValueError`** in `_request` JSON-parse fallback (catches `json.JSONDecodeError`; no longer swallows `KeyboardInterrupt` / `SystemExit`).
- **Stale tool descriptions corrected** — `generate_weekly_report` / `generate_team_report` referenced a `<DDMMYY>` filename format, but the actual output uses ISO `<YYYY-MM-DD>`.
- **Version sync** — `__init__.py` `__version__` was `0.3.0` while pyproject was `0.3.1`; `cli --version` printed the wrong number.
- **`test_all_tools.py` internal refs removed** (internal hostname, real username) — parameterized, safe for public visibility.
- **LICENSE file added (MIT)** + MIT classifier in pyproject.
- **Local CI scaffold** — `Makefile` + `scripts/local-ci.sh` provide `make ci` / `test` / `lint` / `typecheck` / `build` (GitHub Actions intentionally disabled; local CI is the canonical gate).
- **README badges + Development section** — removed GitHub Actions status badges (Actions disabled); added a Development section documenting `make` targets.

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
