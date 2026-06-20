# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
