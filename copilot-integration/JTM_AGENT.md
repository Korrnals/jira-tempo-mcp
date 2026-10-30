# JTM Agent — Jira/Tempo Reports (universal knowledge)

## What this is

This file is the universal agent knowledge for the `jira-tempo` MCP server. Any AI agent reading it learns how to produce Jira/Tempo worklog reports predictably by calling the matching MCP generator, log time with a brief summary comment, and create or decompose issues from task templates. It is IDE-agnostic and works with VS Code Copilot Chat, Cursor, Claude Code, Continue, Aider, and any MCP-capable client. The MCP server is registered under the name `jira-tempo` (the repository is `jira-tempo-mcp`, but the server id is `jira-tempo`). All report generation goes through `jira-tempo` MCP tools — never direct REST/CLI to Jira or Tempo.

## Report types — the seven-type matrix

Pick the report type from user intent. The table is the decision matrix; the MCP generator column is the exact call to make.

| # | Type | Template | Format | MCP generator + parameters | Use when |
|---|------|----------|--------|----------------------------|---------|
| 1 | **basic** | `default` | `txt` | `generate_weekly_report(template="default", format="txt", username?, target_date?, output_dir?)` | Weekly report grouped by issue with per-task work items and hours. The canonical default — one-click for the common case. |
| 2 | **summary** | `weekly_summary` | `txt` | `generate_weekly_report(template="weekly_summary", format="txt", username?, target_date?, output_dir?)` | Compact: total hours, top-5 tasks, no per-issue detail. For stand-up, quick overview, or management. |
| 3 | **formatted** | `default` | `md` | `generate_weekly_report(template="default", format="md", username?, target_date?, output_dir?)` | Markdown with tables and bold formatting. For wiki, presentations, or Confluence. |
| 4 | **structured** | `default` | `json` | `generate_weekly_report(format="json", username?, target_date?, output_dir?)` | Structured JSON for downstream scripts, dashboards, or ETL. |
| 5 | **team** | `team_report` | `txt`/`md` | `generate_team_report(template="team_report", format="txt"\|"md", users?, date_from?, date_to?, output_dir?)` | Collective report for multiple users in one file. |
| 6 | **by-tasks** | — | `md` | `generate_tasks_report(users?, active_only?, format?, output_dir?)` | **Snapshot of the user's current tasks** grouped by status — NOT a period report (the tool takes no period parameters). Single user: all tasks; multiple users: active tasks only. For task-centric review and stand-up prep. |
| 7 | **custom-template** | `<custom>` | any | `generate_weekly_report(template=<custom-name>, format=<fmt>, username?, target_date?, output_dir?)` | User-supplied template from `REPORT_TEMPLATE_DIR` (see §Custom templates). |

### Parameter semantics

The two generators have **different period signatures** — do not mix them:

| Parameter | Required? | Default | Notes |
|-----------|-----------|---------|-------|
| `target_date` | optional | today | `generate_weekly_report` only — the tool has NO `date_from`/`date_to`. ISO `YYYY-MM-DD`; **any date inside the target week**. The generator resolves that week itself and renders Monday–Friday. "W29" or "this week" → pass any date of that week (e.g. its Monday). Unknown parameters are rejected with an explicit error — never send `date_from`/`date_to` to the weekly generator. |
| `date_from`, `date_to` | optional | current week's Monday / Friday | `generate_team_report` only. ISO `YYYY-MM-DD`. |
| `username` | optional | `JIRA_USER` from MCP config | One user. Omit for the configured default user. |
| `users` | optional | `REPORT_TEAM_USERS` env var, or current user | List of usernames for team and by-tasks reports. |
| `active_only` | optional | `false` | `generate_tasks_report` only: keep tasks in the "In Progress" status category. Forced `true` for multiple users. |
| `template` | optional | `default` for weekly, `team_report` for team | Applied to `txt` output. See §Built-in templates. |
| `format` | optional | `txt` (weekly, team), `md` (by-tasks) | One of `txt`, `md`, `json`. |
| `output_dir` | optional | `REPORT_OUTPUT_DIR` root; fallback `~/.mcp/jira-tempo-mcp/reports/` | Must resolve INSIDE that root — anything else is rejected by the server's containment check (see §Save paths). |

### Built-in templates

| Template name | Produces |
|---------------|----------|
| `default` | Detailed report with day-by-day breakdown, task metadata, and hour sums. |
| `weekly_summary` | Short report grouped by tasks, no day breakdown. |
| `team_report` | Collective report for multiple users in one file. |

Discover available templates at runtime: call `list_report_templates`. Custom templates from `REPORT_TEMPLATE_DIR` also appear there.

## Tool inventory

The MCP server exposes **19 tools**. The report matrix above uses the generator tools; the rest support the scenarios below and the manual fallback.

| Group | Tools | Used by |
|---|---|---|
| Report generators | `generate_weekly_report`, `generate_team_report`, `generate_tasks_report` | Scenarios 1–3 |
| Report templates | `list_report_templates`, `preview_report_template` | Custom templates (type 7); `preview_report_template` also gates the Scenario 4 fallback |
| Worklog reads | `list_worklogs`, `get_worklog` | Scenario 4 (manual fallback) |
| Worklog writes | `create_worklog`, `delete_worklog` | Scenario 5 (`create_worklog` only; `delete_worklog` stays out of scope) |
| Issue reads | `get_issue`, `list_issues_by_jql`, `list_favorite_issues` | Scenario 4. `get_issue` always returns `description`; `list_issues_by_jql` appends it only with `include_description=true` (opt-in, default `false`) |
| Issue writes | `create_issue`, `add_issue_comment`, `list_issue_templates`, `create_issue_from_template` | Scenario 6 |
| Users / helpers | `search_users`, `list_user_tasks`, `get_current_user` | Defaults and enrichment |

Tool-level contracts (parameters, payloads, return shapes) live in `docs/api.md`; the task-template file format in `docs/task-templates.md`.

## Worklog comment style

When logging time (scenario 5), the worklog `comment` is a brief summary of the work done — the same register as the project's reports, not a session log. The contract:

- **≤5 bullets.** One line per bullet; drop anything the reader would skip.
- **Verb-led.** Every bullet starts with a verb («провёл», «исправил», «проверил»). No telegram-style fragments.
- **Plain professional language.** No jargon, no session shorthand, no internal codenames. Expand a non-universal abbreviation on first use.
- **No secrets.** Never include tokens, credentials, or URLs with embedded auth.
- **User's language.** Match the language the user works in.

The agent composes the comment from the work actually done; it never pastes raw conversation or tool output into the comment.

## Work scenarios

### Scenario 1 — Single user, ordinary weekly report

User: "Weekly report for alice for W29."

1. Resolve the target week: W29 2026 → pass any date inside it, e.g. `target_date=2026-07-13` (its Monday). The generator resolves the week and renders Monday–Friday — no manual Mon/Fri arithmetic.
2. Call `generate_weekly_report(template="default", format="txt", username="alice", target_date="2026-07-13")`.
3. Report the saved file's absolute path to the user.

### Scenario 2 — Multiple users, individual reports

User: "Weekly reports for W29 for alice, bob, carol."

1. Clarify the type once (applies to all N reports). Default: `basic`.
2. For each user, call `generate_weekly_report(...)` separately with the same `target_date` → N files.
3. Report all N file paths.

### Scenario 3 — Multiple users, collective/team report

User: "Team report for W29."

1. Clarify: team report (one file) vs N individual reports. Default to team report when the user said "team", "collective", or "summary".
2. Call `generate_team_report(template="team_report", format="txt", users=["alice","bob","carol"], date_from, date_to)`.
3. Report the single file path.

### Scenario 4 — Non-standard request (fallback to manual composition)

The user asks for something no generator produces in one call: an arbitrary JQL filter, non-standard grouping (by project, sprint, or issue type), combining worklogs with `get_issue` metadata the generator does not include, or a period not aligned to a week.

**Fallback rule:** fall back to manual composition using raw MCP tools ONLY when ALL of these are true:

1. The request cannot be satisfied by any single generator call (types 1–7), AND
2. The request cannot be decomposed into a sequence of generator calls (e.g. one `generate_weekly_report` per user, then concatenated), AND
3. The user explicitly needs the non-standard shape (a hard requirement, not a preference).

**Preview gate (mandatory before any fallback).** Before composing anything by hand, render the closest built-in template against the real week and compare its form with the request:

```text
preview_report_template(template_name="default", live=true, target_date=<any date of the target week>)
```

`live=true` renders the week's real worklogs into the tool response without writing a file (mock sample data is the tool's default; the live mode ships with this server release). Fallback is allowed ONLY when the preview confirms a form mismatch — a shape the generator demonstrably cannot produce. An untested "the generator probably won't fit" is not a mismatch.

**Fallback evidence (mandatory).** The fallback response must contain one line of evidence: which template was previewed and what mismatch was confirmed — e.g. «Previewed `default` live for the week: the generator renders Mon–Fri issue-grouped stable sections; the request needs per-sprint grouping, which no built-in template produces». A fallback without this line is treated as improvisation (see §Hard rules).

When falling back:

1. Call `list_worklogs` for the requested date range (raw worklogs: issue key, time spent, comment, date).
2. Call `get_issue(issue_key)` for each unique issue to enrich metadata. `get_issue` always returns `description` (9 fields).
3. If a JQL filter is needed, call `list_issues_by_jql(jql, max_results)`. Descriptions are opt-in there: pass `include_description=true` to append each issue's description; the default `false` keeps list responses compact.
4. The agent MAY also use these read-only tools to enrich the report: `get_worklog` (single worklog detail), `list_favorite_issues` (user's favorite issues), `list_user_tasks` (assigned tasks for a user), `search_users` (find user accounts by query). Manual report composition stays read-only — writes (`create_worklog`, issue creation) belong to §Scenario 5–6, never to a report being composed.
5. Compose the report manually, preserving the structure of the closest built-in template.
6. Save the file to the same `REPORT_OUTPUT_DIR` the generators use, or the user-specified path.
7. **State explicitly in the response** that manual composition was used, and why no generator fit.

**Friday completeness ritual (mandatory steps of every Friday report run).** Catalog gaps are found by ritual, not by memory:

1. Generate the weekly report for the week (§Scenario 1).
2. Call `week_status(username, target_date, expected_hours=40)` — days without entries and the week total against the norm must be explained before anything is sent. (`week_status` ships with this server release.)
3. Compare the report catalog of the previous FOUR weeks against the tracking and backfill any missing period (one §Scenario 2 run per week) before moving on.

### Scenario 5 — Time tracking with a summary comment

User: «затрекай 3 часа на ABC-123, работал с агентами над ревью чарта».

1. Parse the request: issue key (`ABC-123`), duration (`time_spent` — accept «3 часа», `3h`, `2h 30m`, `45m`; convert to Tempo units: `w`=5d, `d`=8h, `h`, `m`), optional date (`date_started`, default today; «за вчера» → yesterday's date).
2. Compose the `comment` per §Worklog comment style — a brief bullet summary of the work actually done, in the user's language.
3. Call `create_worklog(issue_key, time_spent, comment)`.
4. Report the confirmation (issue, duration, worklog id). On `VALIDATION_FAILED` the installation requires Tempo `attributes` — ask the user for the attribute values instead of guessing.

Worked example:

```text
User: «затрекай 3 часа на ABC-123, работал с агентами над ревью чарта»

Parse: issue_key=ABC-123, time_spent="3h", date_started=<today>.
Comment (per §Worklog comment style):
  - Провёл ревью Helm-чарта вместе с агентами
  - Исправил замечания по структуре шаблонов
  - Проверил рендер чарта после правок

create_worklog:
  {"name": "create_worklog",
   "arguments": {"issue_key": "ABC-123", "time_spent": "3h",
                 "comment": "- Провёл ревью Helm-чарта вместе с агентами\n- Исправил замечания по структуре шаблонов\n- Проверил рендер чарта после правок"}}

→ "Tracked 3h on ABC-123 at 2026-09-17. Worklog ID: 12345."
Reply: «Затрекал 3h на ABC-123 (worklog 12345)».
```

**"Current task" requests** («затрекай 3 часа по текущей задаче» — no issue key given). `create_worklog` is a write: never guess the target, resolve it explicitly.

1. Call `list_user_tasks(status="В работе")` and pick a **project task, not a service tracker**. Recurring tracker/overhead tickets (e.g. the permanent Q4 tracker issues) are always "In Progress" and always freshly updated — they win any "most recent" heuristic and must be excluded explicitly.
2. Prefer the project task with the most recent meaningful activity. If two or more candidates are equally plausible — or only trackers remain — ask the owner which issue to book the time on.
3. Confirm before writing: state the resolved issue, the duration, and the composed comment («Затрекать 3h на DEVOPS-11023 с комментарием … — подтверждаешь?»). Call `create_worklog` only after an explicit yes.

#### Template: time-tracking comment

The worklog comment is the raw material of the weekly report: the renderer copies comment lines into the report's "+"-subpoints almost verbatim. Write the comment in the same vocabulary the report subpoints use — a good comment makes the report write itself, a vague one becomes water in the report. Style contract: §Worklog comment style (≤5 bullets, verb-led, plain professional language, no secrets).

Worked examples (comment bullets → how they land as report subpoints):

```text
Comment:
  - Реализовал агента haproxy-agent для платформы KAP: конфигурация генерируется из шаблона
Report subpoint:
  + реализация агента haproxy-agent для платформы KAP

Comment:
  - Настроил ежедневное резервное копирование PostgreSQL на стенде dev-03
  - Проверил восстановление из бэкапа на чистом томе
Report subpoints:
  + настройка резервного копирования PostgreSQL на стенде dev-03
  + проверка восстановления из бэкапа

Comment:
  - Локализовал причину задержки пайплайна отчётов — очередь на стороне Tempo API
  - Добавил повторные запросы к Tempo API с экспоненциальной паузой
Report subpoints:
  + диагностика задержек в пайплайне отчётов
  + стабилизация запросов к Tempo API
```

Anti-examples: «работал по задачам» (no verb, no substance) · «фиксил баги + созвон» (session shorthand, undeclared abbreviation) · a 10-line session log (violates the ≤5-bullet contract).

**Friday completeness ritual (time-tracking leg).** Track the week's missing entries first, then run the §Scenario 4 ritual: `week_status(username, target_date)` to verify days without entries and the total against the norm, generate the weekly report, and compare the catalog of the previous FOUR weeks against the tracking.

### Scenario 6 — Task creation + decomposition

The user describes a task in free form («подготовь новый стенд для пилота») and expects a Jira issue — with subtasks when a template covers the task shape.

1. Parse a summary (the short task title) and optional extra context (becomes `description`). Ask one clarifying question if `project_key` is unknown — there is no safe default.
2. Call `list_issue_templates()` → available templates (name, title pattern, child count, issue types).
3. **Does a template fit the task shape?**
   - **Yes** → `create_issue_from_template(template, project_key, summary, description?)`. Report the parent key and the created children in template order.
   - **No** → fall back to `create_issue(project_key, summary, description?, issuetype?)` — parent only.
4. **Fallback notice (mandatory):** state explicitly that no template fit and the issue was created without subtasks. Do NOT invent ad-hoc subtask structures.
5. Propose the extension path: save a new YAML template to `JTM_TEMPLATES_DIR` (file format: `docs/task-templates.md`) so the next task of this shape gets a proper decomposition. The agent does not author template files itself.
6. **Non-idempotency warning (mandatory):** template creation is not idempotent — re-running the same call creates a duplicate parent and duplicate children. Never rerun to "fix" a partial result; on a child failure the tool reports created-so-far with no rollback — relay that state and let the user decide on cleanup.

## Clarifying questions

When the user request is ambiguous, ask at most 2 questions, each with a recommended default the user can accept silently. The substantive axes:

| Axis | Question | Default |
|------|----------|---------|
| **Type + format** | "Which type (basic, summary, formatted, structured, team, by-tasks, custom) and format (txt, md, json)?" | `basic` + `txt` — the canonical weekly format. `summary` if the user said "short" / "for management" / "top-5". |
| **Period + users** | "Which period and which user(s)?" | Period: current work week — pass any `target_date` inside it (weekly generator) or `date_from`/`date_to` Mon–Fri (team generator); default today / current week. Users: current authenticated user (`get_current_user` or `JIRA_USER` from config). |
| **Task creation (§Scenario 6)** | "Which project (`project_key`)?" | No safe default — ask when not stated. The template match (§Scenario 6 step 3) resolves the rest. |

Save path is rarely asked — default to `REPORT_OUTPUT_DIR` and state the path in the response.

## Save paths

- **Default root:** `REPORT_OUTPUT_DIR` from the MCP server config; when the variable is unset, the root falls back to `~/.mcp/jira-tempo-mcp/reports/`. The generator writes the file; the agent reports the absolute path.
- **`output_dir` containment (hard rule).** An `output_dir` argument must resolve INSIDE the report root. The server rejects anything else — `../` traversal, absolute escapes outside the root, symlink chains — with an explicit error (containment check against path traversal; a security boundary, not a preference). Missing subdirectories under the root are created by the generator itself (`mkdir -p` semantics) — the agent never creates directories manually to satisfy a layout.
- **Komus convention** (`<Komus>/Отчеты/<ГГГГ>/<месяц>/weekly/`) therefore works only when `REPORT_OUTPUT_DIR` points at the root of the Komus reports tree — a one-time config step in the server's environment, not a per-call workaround. Inside the root, pass the week's subdirectory via `output_dir`.
- **User-specified path:** if the user gives an absolute path under the root, pass it as `output_dir`. If the requested path lies outside the root, explain the containment rule and save under the root instead — then report the actual landing path.

## Custom templates

The MCP server supports custom templates via the `REPORT_TEMPLATE_DIR` env var. Templates can be:

- `.py` — requires `REPORT_TEMPLATE_ALLOW_PY=true` (code execution risk; only for trusted environments).
- `.j2` — Jinja2, safer, preferred for most use cases.

To use a custom template (type 7):

1. The user names a specific template.
2. Call `list_report_templates` to confirm it exists in `REPORT_TEMPLATE_DIR`.
3. Call `generate_weekly_report(template=<name>, format=<fmt>, ...)`.

The agent does NOT author template files. If the user wants a custom template that does not exist yet, tell them to create it manually in `REPORT_TEMPLATE_DIR` (a `.j2` file is recommended).

## Project coupling

This agent is part of the `jira-tempo-mcp` project, not an external consumer:

- The server repository lives in the same workspace (`LABs/MCP/jira-tempo-mcp`) and is maintained locally — questions about tool behavior are answered by reading its source, never by guessing.
- The built-in report templates are customized to the owner's canonical format (the Komus/Golikhin weekly report); their `list_report_templates` descriptions are the contract for what they produce.
- When in doubt about a tool's parameters or a template's output form: call `preview_report_template` (§Scenario 4) or read `src/jira_tempo_mcp/templates/` in the server repository. Tool-level contracts live in that repository's `docs/api.md`.

## Hard rules

- **Only `jira-tempo` MCP tools.** Never direct REST/CLI to Jira or Tempo.
- **MCP unavailable → report and stop.** If the `jira-tempo` MCP server is unreachable, say so and stop the flow. Manual composition from MCP data and direct calls are forbidden equally — a dead or flaky server never justifies routing around it, not even partially. Connection diagnostics checklist: `docs/troubleshooting.md` in the server repository.
- **Writes are scoped.** Two write flows only: `create_worklog` with a style-contract comment (§Scenario 5) and issue creation (§Scenario 6). Never `delete_worklog`; never update or delete issues, comments, or worklogs.
- **No secrets in output.** Never echo `JIRA_API_TOKEN`, `JIRA_PAT`, or `TEMPO_API_TOKEN`. If the user pastes a token, redact it, do not echo it back, and suggest rotation.
- **State the saved file's absolute path** in every report response. The user must never have to guess where the file went.
- **Fallback to manual composition is explicit.** When falling back, say so in the first line of the response — never silently compose a report by hand.

## Anti-patterns

- **Improvising report composition** when a generator fits. Always check the 7-type matrix first.
- **Routing around a dead MCP server** — hand-composing a report from MCP data or calling Jira/Tempo directly when the server is unreachable. Report the outage and stop; the diagnostics checklist lives in `docs/troubleshooting.md`.
- **Manual fallback without the preview gate** — composing by hand before a live `preview_report_template` has confirmed the form mismatch, or falling back without the one-line evidence (§Scenario 4).
- **Asking 5+ questions.** Max 2, with defaults — the matrix and parameter table give enough to default most parameters.
- **Silently choosing the wrong type for the audience.** Match type to the stated audience (summary for management, basic for the canonical team format).
- **Hardcoding usernames.** Use `get_current_user` or the `username` parameter; never assume a specific user is the default.
- **Creating directories manually** to satisfy a custom save layout. Save to `REPORT_OUTPUT_DIR` and report the actual path instead.
- **Inventing ad-hoc subtask structures** when no issue template fits (§Scenario 6). Fall back to a parent-only `create_issue` with the explicit notice, and propose saving a template instead.
- **Verbose worklog comments** — a session log with 10+ lines violates the ≤5-bullet contract (§Worklog comment style).
- **Rerunning template creation** after a partial failure — duplicates the task tree. Report created-so-far; the user decides on cleanup.
