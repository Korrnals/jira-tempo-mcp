# Code Review Report — jira-tempo-mcp 0.1.0

**Review date:** 2026-06-19
**Reviewer:** @GCW: Code Reviewer (delegated by @GCW: Tech Lead)
**Mode:** `standard` (all 5 passes, no refactor — findings only)
**Scope:** full codebase, first review (no prior baseline)

---

## 1. Executive summary

The codebase is well-structured for a 0.1.0: clean layering, secrets masking in
`Config.__repr__`, redaction in `_redact`, and a working stdio MCP server.
However it is **not production-ready**. The single biggest risk is
**zero test coverage combined with a silent fallback in `find_worker_key`**:
if the Tempo `/workers` endpoint is unavailable, the code silently substitutes
the Jira username as the worker key, which can cause `list_worklogs` to return
an empty set and `generate_weekly_report` to emit a blank report — with no
error surfaced to the user. A close second is the `.history/` directory not
being gitignored: VS Code Local History persists old file versions on disk,
and if `.env` was ever edited while the extension was active, real PATs may be
sitting in `.history/` outside VCS but still on disk.

**Verdict:** block production use until BLOCKERs are resolved.

---

## 2. Findings by severity

### BLOCKER

| # | File | Line | Issue | Suggestion | Evidence |
|---|------|------|-------|------------|----------|
| B1 | `.gitignore` | — | `.history/` is not ignored. VS Code Local History persists old file revisions on disk; if `.env` was ever edited, real PATs may be stored in `.history/.env/…`. The directory is present in the workspace and contains source snapshots. | Add `.history/` to `.gitignore` and audit/purge any existing `.history/` entries that contain `.env` or PATs. | `list_dir` shows `.history/` at project root; `.gitignore` ignores `.vscode/` but not `.history/`. |
| B2 | `tests/` | — | No `tests/` directory exists despite `pyproject.toml` configuring `testpaths = ["tests"]` and pytest-asyncio. Running `pytest` collects nothing / errors on missing path. For a tool that writes production time-tracking data and deletes worklogs, zero tests is a blocker. | Add a `tests/` package with unit tests for the pure functions listed in §4 before any production use. | `file_search **/tests/**` returns no matches under `jira-tempo-mcp/`; `pyproject.toml` line 67 `testpaths = ["tests"]`. |

### MAJOR

| # | File | Line | Issue | Suggestion | Evidence |
|---|------|------|-------|------------|----------|
| M1 | `src/jira_tempo_mcp/client.py` | 174-189 | `find_worker_key` silently falls back to returning the raw `username` as the worker key when the `/workers` endpoint fails or returns an unexpected shape. This can cause wrong attribution in `create_worklog` and empty results in `list_worklogs`/`generate_weekly_report` with no error surfaced. | Distinguish "endpoint unavailable" (raise / return `None` and let callers decide) from "worker not found" (raise). At minimum, log at ERROR and let `list_worklogs` return an explicit "could not resolve worker" message instead of an empty list. | `except JiraTempoError: logger.warning(...); return target` |
| M2 | `src/jira_tempo_mcp/report.py` | 185-189 | Report header hardcodes the author name with a typo: `"[Голихи Л.С.]"` (missing `н`). The name should come from `Config.jira_user` or a new `Config.author_display_name` field. | Externalize the author display name to `Config` and fix the typo. | `lines.append(f"[Голихи Л.С.] Отчет работы за неделю ...")` |
| M3 | `src/jira_tempo_mcp/report.py` | 244-247 | Absolute path `./work/example-org/reports` is baked into the default `output_dir`. Not portable, not configurable, breaks for any other user or machine. | Add `report_output_dir` to `Config` (env: `REPORT_OUTPUT_DIR`) with a sensible default; fall back to `./reports` if unset. | `output_dir = Path("./work/example-org/reports") / str(monday.year) / month_ru` |
| M4 | `src/jira_tempo_mcp/report.py` | 20-40 | `SECTION_MAP`, `STABLE_ORDER`, `NON_ISSUE_SECTIONS` are hardcoded module constants. Customizing the report requires editing source code (README even instructs users to "Edit `SECTION_MAP` in `report.py`"). | Externalize to a YAML/JSON config file (e.g. `report-sections.yaml`) loaded by `Config`; keep the constants as a fallback default. | `SECTION_MAP: dict[str, str] = {...}` |
| M5 | `install.py` | 28-29 | `VSCODE_DIR = Path.home() / ".config" / "Code" / "User"` is Linux-only. On macOS the path is `~/Library/Application Support/Code/User`, on Windows `%APPDATA%\Code\User`. The installer silently writes to a non-existent path on non-Linux. | Detect platform (`sys.platform`) and pick the correct VS Code user dir, or document the installer as Linux-only. | `VSCODE_DIR = Path.home() / ".config" / "Code" / "User"` |
| M6 | `install.py` | 218-229 | `JIRA_PAT: "${env:JIRA_PAT}"` is written into `mcp.json`'s `env` block. `${env:...}` is a VS Code variable-substitution syntax; whether the MCP extension resolves it inside `env` values is not verified. If unresolved, the server receives the literal string `${env:JIRA_PAT}` as the PAT and fails with 401, which is hard to debug. | Verify the substitution works in the target VS Code + MCP extension version; if not, document that the user must set `JIRA_PAT` in their shell and have the server read it directly (drop the `env` entry). Add a post-install smoke check. | `"JIRA_PAT": "${env:JIRA_PAT}"` |
| M7 | `install.py` | 196-199 | `os.chmod(ENV_FILE, 0o600)` is wrapped in `contextlib.suppress(OSError)` and the README claims `0600`. On Windows, `os.chmod` with `0o600` does not restrict access (Windows uses ACLs); the success message `".env written (permissions: 600)"` is misleading cross-platform. | Either document the installer as POSIX-only, or use platform-appropriate ACL setting on Windows and only print the `600` message when `os.name == "posix"`. | `with contextlib.suppress(OSError): os.chmod(ENV_FILE, 0o600)` then `_ok(f".env written (permissions: 600) ...")` |
| M8 | `src/jira_tempo_mcp/cli.py` | 24-29 | The `install` subcommand resolves `install.py` by relative path from `__file__` (`parent.parent.parent / "install.py"`). This only works for an editable install where `install.py` sits alongside `src/`. A wheel/installed package will not ship `install.py`, and the command will fail with a confusing `FileNotFoundError`. | Either ship `install.py` as package data (`include_package_data`) and resolve via `importlib.resources`, or document that `install` only works in editable/dev mode. | `install_script = Path(__file__).resolve().parent.parent.parent / "install.py"` |
| M9 | `README.md` | 113-137 | README states `.vscode/mcp.json` is "already included in this repo", but `.vscode/` is in `.gitignore` and the file does not exist in the workspace. Users following the manual setup will not find it. | Either commit a `.vscode/mcp.json` template (un-ignore it specifically) or remove the claim and inline the config block as "create this file". | `Add to .vscode/mcp.json (already included in this repo):` |
| M10 | `src/jira_tempo_mcp/server.py` | 196, 222, 261-263 | `format_seconds_to_seconds_human` is used at lines 196 and 222 but defined at line 261, after `_handle_tool_call`. It is a pure alias for `format_seconds_to_human` (imported at line 25). This works at runtime (module fully loads before `serve()` is called) but is confusing and the import is only used by the alias. | Delete the alias and call `format_seconds_to_human` directly at lines 196 and 222; remove the now-unused import if applicable. | `def format_seconds_to_seconds_human(seconds: int) -> str: ... return format_seconds_to_human(seconds)` |
| M11 | `src/jira_tempo_mcp/client.py` | 1-270 (whole module) | `JiraTempoClient` mixes Jira REST API and Tempo Timesheets API in one 270-line class. The two APIs have different auth headers (`_jira_headers` vs `_tempo_headers`), different base URLs, and different error shapes. | Split into `JiraClient` and `TempoClient` (or a thin `JiraTempoClient` composing both). Improves testability and lets callers depend on only the API they use. | single class with `_jira_headers`, `_tempo_headers`, `jira_api_base`, `tempo_api_base` |
| M12 | `src/jira_tempo_mcp/config.py` | 18-50 | `Config` is a plain `frozen=True` dataclass with manual validation in `load_config`. `pydantic>=2.7.0` is already a declared dependency but unused. Using pydantic would give timezone validation, URL normalization, and non-empty checks for free. | Migrate `Config` to `pydantic.BaseModel` (or `pydantic.dataclasses.dataclass(frozen=True)`), or drop `pydantic` from dependencies if intentionally unused. | `@dataclass(frozen=True)\nclass Config:` + `dependencies = [..., "pydantic>=2.7.0", ...]` |

### MINOR

| # | File | Line | Issue | Suggestion | Evidence |
|---|------|------|-------|------------|----------|
| m1 | `src/jira_tempo_mcp/server.py` | 194 | `wl.get("issue", {}) or {}` — if `issue` is a non-dict truthy value (e.g. a string), `.get("key")` raises `AttributeError`. Use `isinstance` guard or `(wl.get("issue") or {}).get("key")` only after type check. | `key = wl.get("issueKey") or (wl.get("issue") if isinstance(wl.get("issue"), dict) else {}).get("key", "?")` | `key = wl.get("issueKey") or (wl.get("issue", {}) or {}).get("key", "?")` |
| m2 | `src/jira_tempo_mcp/server.py` | 199 | `wl.get("tempoWorklogId") or wl.get("id") or wl.get("worklogId", "?")` — if `worklogId` key exists with value `""`, the `or` chain returns `""` (falsy) but the final `.get(..., "?")` already evaluated to `""`, so result is `""` not `"?"`. | Use explicit `wl.get("worklogId") or "?"` as the final term, or a helper. | `wl_id = wl.get("tempoWorklogId") or wl.get("id") or wl.get("worklogId", "?")` |
| m3 | `src/jira_tempo_mcp/server.py` | 252-258 | `_handle_tool_call` is a 7-branch if/elif chain. A dispatch table (`dict[str, Callable]`) would be cleaner, individually testable, and avoid the `raise ValueError` fallthrough. | Map tool names to handler coroutines in a dict; look up and `await`. | `if name == "list_worklogs": ... if name == "get_worklog": ...` |
| m4 | `src/jira_tempo_mcp/client.py` | 233-247 | `parse_duration_to_seconds`, `format_seconds_to_human`, `iso_now` are module-level functions unrelated to the HTTP client. `iso_now` imports `pytz` locally. These belong in a `utils.py` / `formatting.py`. | Move pure helpers to a separate module; `client.py` should only contain the client class. | `def parse_duration_to_seconds(...)` in `client.py` |
| m5 | `src/jira_tempo_mcp/client.py` | 44 | `timeout=30.0` is a magic default with no env override. `install.py` uses a separate `timeout=10` for `urllib`. Both should be configurable via `Config`. | Add `http_timeout` to `Config` (env `JIRA_HTTP_TIMEOUT`, default 30.0). | `def __init__(self, config: Config, timeout: float = 30.0)` |
| m6 | `src/jira_tempo_mcp/client.py` | 80-84 | `_request` logs `body = resp.text[:500]` on error. The response body from Jira/Tempo could echo request context (rare, but possible). 500 chars is a lot to log at ERROR. | Truncate to 200 chars and/or scrub known token patterns from the body before logging. | `body = resp.text[:500] if resp.text else ""` |
| m7 | `src/jira_tempo_mcp/report.py` | 167-172 | `except Exception` around `client.get_issue(key)` is too broad; catches `KeyboardInterrupt`? No (BaseException), but catches `asyncio.CancelledError`? No. Still, it swallows programming errors (e.g. `AttributeError` from a shape change). | Catch `JiraTempoError` specifically; let other exceptions propagate. | `except Exception: logger.warning("Could not fetch issue %s ...", key)` |
| m8 | `src/jira_tempo_mcp/server.py` | 252-258 | `generate_weekly_report` tool: `date.fromisoformat(td)` has no try/except; `ValueError` propagates to the broad handler and the user sees `ValueError: Invalid isoformat string`. | Validate `target_date` format before calling and return a helpful message. | `target = date.fromisoformat(td)` |
| m9 | `src/jira_tempo_mcp/server.py` | 210-213 | `get_worklog` returns `str(_json_safe(wl))` — a raw `repr`-style dump, while `list_worklogs` returns a formatted table. Inconsistent output style across tools. | Format `get_worklog` output as key/value lines like `get_issue` does. | `return f"Worklog {wl_id}:\n" + str(_json_safe(wl))` |
| m10 | `src/jira_tempo_mcp/server.py` | 234-238 | `create_worklog` does not validate `issue_key` format (e.g. `^[A-Z]+-\d+$`). Invalid keys go to the API and return a generic error. | Validate issue key format at the boundary and return a clear message. | `issue_key = arguments["issue_key"]` passed straight to client |
| m11 | `src/jira_tempo_mcp/server.py` | 226-228 | Broad `except Exception as exc` returns `f"ERROR: {exc.__class__.__name__}: {exc}"`. For a non-developer user, `JiraTempoError` is jargon. | Map known exception types to user-friendly messages; keep the class name only in DEBUG logs. | `result = f"ERROR: {exc.__class__.__name__}: {exc}"` |
| m12 | `src/jira_tempo_mcp/__main__.py` | 8 | `raise SystemExit(main())` — `cli.main()` returns `int`, but `server.main()` returns `None`. If someone runs `python -m jira_tempo_mcp.server` directly, `if __name__ == "__main__": main()` does not use `SystemExit`. Inconsistent exit-code handling. | Pick one pattern: `raise SystemExit(main())` everywhere, or `sys.exit(main())`. | `__main__.py`: `raise SystemExit(main())`; `server.py`: `main()` |
| m13 | `install.py` | 100-130 | Installer is interactive (`input()`, `getpass.getpass`). When run non-TTY (piped), `input()` reads from stdin and `getpass` may raise `GetPassWarning`/echo. No TTY guard at entry. | Detect `not sys.stdin.isatty()` at the top of `main()` and abort with a message pointing to manual setup. | `_IS_TTY = sys.stdout.isatty()` is used for colour but not for gating interactivity. |
| m14 | `src/jira_tempo_mcp/client.py` | 156-164 | `create_worklog` docstring says `date_started` is "ISO 8601 with timezone", but `server.py` passes `iso_now(config.timezone)` which returns `datetime.isoformat()` — correct. However there is no validation that the string actually contains a tz offset; Tempo may silently interpret naive times as UTC. | Validate `date_started` contains a tz offset before sending. | `date_started: str  # ISO 8601 with timezone` |
| m15 | `src/jira_tempo_mcp/report.py` | 252-258 | `remaining.sort(key=lambda k: sum(_extract_seconds(w) for w in grouped[k]), reverse=True)` — the `key` is recomputed; fine (called once per element), but the total is not stored, so downstream code cannot reuse it. | Precompute totals into a dict if reused. | `remaining.sort(key=lambda k: sum(...), reverse=True)` |

### NIT

| # | File | Line | Issue | Suggestion | Evidence |
|---|------|------|-------|------------|----------|
| n1 | `src/jira_tempo_mcp/config.py` | 30 | `# pragma: no cover` on `__repr__` — there are no tests, so coverage pragmas are premature. | Remove until tests exist. | `def __repr__(self) -> str:  # pragma: no cover - safety guard` |
| n2 | `src/jira_tempo_mcp/report.py` | 189 | Typo: `Голихи` should be `Korrnals`. | Fix spelling. | `f"[Голихи Л.С.] Отчет работы за неделю ..."` |
| n3 | `pyproject.toml` | 67 | `testpaths = ["tests"]` points to a non-existent directory. | Add `tests/` (even empty with a placeholder) or remove the setting until tests exist. | `testpaths = ["tests"]` |
| n4 | `README.md` | 180-190 | "Project structure" lists `.vscode/mcp.json` but it is gitignored and absent. | Remove from the tree or un-ignore and commit it. | `├── .vscode/mcp.json      # VS Code MCP config` |
| n5 | `src/jira_tempo_mcp/server.py` | 1-10 | Module docstring says "Run as a stdio MCP server: `python -m jira_tempo_mcp.server`" — but `__main__.py` dispatches `serve` to `server.main`, and `python -m jira_tempo_mcp.server` also works. The two entrypoints are redundant and not cross-documented. | Pick one canonical entrypoint and document it; note the other as an alias. | two entrypoints: `__main__.py` and `server.py:if __name__` |
| n6 | `src/jira_tempo_mcp/client.py` | 249-257 | `iso_now` does a local `import pytz` inside the function. `pytz` is already a top-level dependency; import at module top for consistency. | Move `import pytz` to module top. | `def iso_now(timezone: str) -> str: ... import pytz` |
| n7 | `install.py` | 1-16 | `from __future__ import annotations` is present (good), but `typing.Any` is imported and used only once in `mcp_data: dict[str, Any]`. Fine, but `Any` usage defeats type safety in the JSON handling. | Use `json.JSONDecoder` types or `object` with narrowing. | `mcp_data: dict[str, Any]` |

---

## 3. Top 5 must-fix items

1. **B1 — `.history/` not gitignored.** Add `.history/` to `.gitignore` immediately and audit the existing `.history/` directory for any `.env` snapshots containing real PATs. Rotate the PAT if any are found.
2. **B2 — No tests.** Add a `tests/` package with unit tests for the pure functions (see §4) before any production use. A tool that deletes worklogs (`delete_worklog`) and writes reports to disk cannot ship untested.
3. **M1 — `find_worker_key` silent fallback.** Stop returning the username as a worker key on failure; surface a clear error so `list_worklogs` and `generate_weekly_report` do not silently return empty results.
4. **M3 / M4 — Hardcoded paths and section map in `report.py`.** The absolute `./...` path and the hardcoded `SECTION_MAP` make the tool unusable outside one machine and one user. Externalize both to `Config` / a config file.
5. **M6 — `${env:JIRA_PAT}` substitution in `mcp.json`.** Verify the substitution actually resolves in the target VS Code + MCP extension; if not, the server will receive a literal `${env:JIRA_PAT}` string and fail with 401, which is very hard to debug.

---

## 4. Top 5 recommended tests

Priority order (highest first):

1. **`parse_duration_to_seconds`** — pure function, high blast radius (drives `create_worklog` seconds). Test: valid forms (`"1h 30m"`, `"2h"`, `"45m"`, `"1d 2h"`, `"1w"`), invalid (`""`, `"abc"`, `"1x"`), edge (`"0h"` → 0, `"999h"`), whitespace, case insensitivity. Verify unit conversions (week=5d, day=8h).
2. **`format_seconds_to_human`** — pure function used in report and tool output. Test: 0 → `"0h"`, 3600 → `"1h"`, 5400 → `"1h 30m"`, 60 → `"1m"`, negative → `"0h"`.
3. **`_week_range`** — pure date logic, drives the report window. Test: a Monday, a Friday, a Sunday (boundary), a Wednesday, cross-month boundary, leap-year Feb 29.
4. **`_parse_tempo_date`** — pure parser for Tempo's inconsistent date formats. Test: `"2026-06-19"`, `"2026-06-19T10:00:00.000+0300"`, `"2026-06-19T10:00:00Z"`, `None`, `""`, garbage string → `None`.
5. **`generate_weekly_report` (integration, mocked client)** — end-to-end with a fake `JiraTempoClient` returning canned worklogs. Assert: output file path, section ordering (stable first, then non-issue, then remaining sorted by time desc), total seconds, filename format `your-username_<DDMMYY>-<DDMMYY>.txt`, handling of unknown issues (fetches summary), handling of missing comment (uses `format_seconds_to_human`).

Bonus: `Config.__repr__` masking (assert `jira_pat` never appears in `repr(config)`), `load_config` missing-var error, `_redact` URL sanitisation.

---

## 5. Positive observations

- **Secrets hygiene is mostly sound:** `Config.__repr__` masks `jira_pat` and `tempo_api_token`; `_redact` strips credentials from URLs before logging; `.env` is gitignored; PAT is read from env, not stored in `mcp.json` (only a reference).
- **Layering is clean for 0.1.0:** `config` → `client` → `report`/`server` dependency direction is correct; no circular imports; `report.py` reaches into `client` via the public `JiraTempoClient` API, not internals.
- **`from __future__ import annotations`** is consistently present across all `src/` modules.
- **ruff + mypy strict** are configured and reportedly passing — the type annotations are full coverage (verified: all public functions annotated).
- **`JiraTempoClient` is a proper async context manager** (`__aenter__`/`__aexit__`/`aclose`), and `server.py` uses `async with` per tool call — no leaked connections.
- **Error boundary is correct:** `JiraTempoError` is raised in the client and caught at the MCP tool boundary (`_call_tool`), not leaked to the user as a stack trace.
- **`install.py` TTY-aware colour** (`_color` falls back to plain text when piped) is a nice touch — no raw ANSI leaks in non-TTY mode for the colour helpers.
- **`pyproject.toml` is well-organised** — ruff/mypy/pytest config in one place, `src/` layout, optional `dev` extras.

---

## 6. Deferred items

- Splitting `JiraTempoClient` into `JiraClient` + `TempoClient` (M11) — defer to a refactor slice; not blocking.
- Migrating `Config` to pydantic (M12) — defer; current manual validation works, but `pydantic` is a dead dependency until then.
- Dispatch table for `_handle_tool_call` (m3) — defer with the test-writing slice (tests will drive the refactor).
- Externalizing `SECTION_MAP` to YAML (M4) — defer until a second user needs it; for now document as "edit `report.py`".

---

*End of report. No files were modified. Findings only, per task constraints.*