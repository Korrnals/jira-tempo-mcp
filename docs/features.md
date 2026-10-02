# ✨ Features — what jira-tempo-mcp can do

`jira-tempo-mcp` is one package with three faces: an **MCP server** exposing
19 tools over self-hosted Jira (Server / Data Center) + Tempo Timesheets 4, a
**CLI** (`jira-tempo-mcp`) for install / update / specialist management, and a
**standalone AI specialist agent** that drives the server's report generators
from Copilot Chat and other harnesses.

This page is the capability map. The full per-tool reference with parameters
and examples lives in [api.md](api.md).

---

## 🗺️ At a glance

| Capability group | Tools | Deep dive |
| --- | --- | --- |
| 🔍 [Read Jira & Tempo](#-read-jira--tempo) | 8 | [api.md](api.md) |
| ⏱️ [Time tracking](#-time-tracking) | 2 | [api.md](api.md) |
| 🧩 [Issue creation & template decomposition](#-issue-creation--template-decomposition) | 4 | [task-templates.md](task-templates.md) |
| 📊 [Reports](#-reports) | 5 | [reports.md](reports.md), [templates.md](templates.md) |
| 🖥️ [CLI & operations](#-cli--operations) | 5 commands | [cli.md](cli.md) |
| 🤖 [AI specialist agent](#-ai-specialist-agent) | — | [README §JTM Agent](../README.md#-jtm-agent-standalone-copilot-chat-agent) |

---

## 🔍 Read Jira & Tempo

Read-only lookups against Jira and Tempo — the foundation every report
builds on.

| Tool | What it does |
| --- | --- |
| [`get_issue`](api.md#-get_issue) | Issue metadata: summary, status, project |
| [`list_issues_by_jql`](api.md#-list_issues_by_jql) | Search issues by JQL (read-only, max 100 results) |
| [`list_worklogs`](api.md#-list_worklogs) | Tempo worklogs for a date range or a single day |
| [`get_worklog`](api.md#-get_worklog) | A single worklog by Tempo ID |
| [`list_favorite_issues`](api.md#-list_favorite_issues) | Favorite issues of the current user |
| [`list_user_tasks`](api.md#-list_user_tasks) | Tasks assigned to a user, with status, priority, comments |
| [`search_users`](api.md#-search_users) | Find Jira users by name, surname, or username |
| [`get_current_user`](api.md#-get_current_user) | Info about the authenticated user (the PAT owner) |

---

## ⏱️ Time tracking

| Tool | What it does |
| --- | --- |
| [`create_worklog`](api.md#-create_worklog) | Track time on a Jira issue, with a comment |
| [`delete_worklog`](api.md#-delete_worklog) | Delete a worklog (undo mis-tracked time) |

---

## 🧩 Issue creation & template decomposition

| Tool | What it does |
| --- | --- |
| [`create_issue`](api.md#-create_issue) | Create a Jira issue — optionally a subtask via a parent key |
| [`add_issue_comment`](api.md#-add_issue_comment) | Add a comment to an existing issue |
| [`list_issue_templates`](api.md#-list_issue_templates) | List available task templates (built-in + user overrides) |
| [`create_issue_from_template`](api.md#-create_issue_from_template) | Create one parent issue plus ordered child subtasks from a YAML template |

A **task template** expands into a parent issue and an ordered list of child
subtasks — a repeatable checklist in one call. The package ships a built-in
`stand-preparation` template (15 child tasks); your own YAML files override
built-ins or add new ones via the `JTM_TEMPLATES_DIR` environment variable.
Template fields render through a sandboxed Jinja2 context (`summary`,
`user_description`, `project_key`, `today`).

Full format, validation rules, and an example: [task-templates.md](task-templates.md).

---

## 📊 Reports

Three generators, each producing `txt`, `md`, or `json`:

| Tool | What it does |
| --- | --- |
| [`generate_weekly_report`](api.md#-generate_weekly_report) | Weekly report from Tempo worklogs |
| [`generate_team_report`](api.md#-generate_team_report) | Team report for several Jira users |
| [`generate_tasks_report`](api.md#-generate_tasks_report) | Tasks report grouped by status — per-user (individual mode) or multi-user (group mode, active tasks only, detected via the language-independent `statusCategory`) |

Templates and tooling around them:

| Tool | What it does |
| --- | --- |
| [`list_report_templates`](api.md#-list_report_templates) | List available report templates (built-in + custom) |
| [`preview_report_template`](api.md#-preview_report_template) | Render a template on sample data — no Jira call, no file written |

**Custom report templates**: drop a `.j2` or `.py` file into the template
directory and it becomes selectable by name. Jinja2 runs in a sandbox;
Python templates are opt-in (`REPORT_TEMPLATE_ALLOW_PY=1`).

Report formats and section mapping: [reports.md](reports.md).
Template authoring reference: [templates.md](templates.md).

---

## 🖥️ CLI & operations

The `jira-tempo-mcp` console script dispatches five subcommands (plus
`--version` / `--help`):

| Command | What it does |
| --- | --- |
| `serve` | Start the MCP server over stdio (default) |
| `install` | Interactive installer (venv + `.env` + VS Code) |
| `uninstall` | Reverse the installation |
| `update` | Self-update; detects the install mode (wheel / editable); auto-refreshes the installed specialist |
| `install-specialist` | Install the AI specialist into AI harnesses |

`install-specialist` knows a harness registry: `copilot`, `zcode`, `claude`,
`pi`, `hermes`, and `opencode` are supported, `codex` is skipped (no
agent-file convention). Skills-only harnesses (`claude`, `pi`, `hermes`,
`opencode`) install no agents file — VS Code cross-scans the claude agents
dir, so a JTM agent file there would show a duplicate picker entry. Every
install records the harness names in a state file; `update` re-installs the
specialist from the new package data after a successful upgrade.

Commands reference: [cli.md](cli.md). Installation paths: [installation.md](installation.md).

---

## 🤖 AI specialist agent

A standalone agent — **JTM: Jira Tempo Reports** — that produces Jira/Tempo
reports predictably by calling the server's generators. Works in Copilot Chat
(graphical picker, one-click weekly report), ZCode, Claude Code, pi, Hermes,
OpenCode, and other MCP-capable harnesses. Ships inside the wheel:
`(re)install` it any time with `install-specialist`, no git clone needed.

Details: [README §JTM Agent](../README.md#-jtm-agent-standalone-copilot-chat-agent),
harness table in [cli.md](cli.md#-install-specialist).

---

## ⚠️ Limitations

- **E2E against real Jira is read-only by policy.** The write tools
  (`create_worklog`, `delete_worklog`, `create_issue`, `add_issue_comment`,
  `create_issue_from_template`) exist and are unit-tested on a mock
  transport; live write validation against a real instance is deliberately
  not performed.
- **JQL search is capped at 100 results** per `list_issues_by_jql` call.

---

## ➡️ Next steps

- 🌐 [api.md](api.md) — the full per-tool reference; this page is the map,
  not the reference
- 📦 [installation.md](installation.md) — install modes and walkthrough
- ⚙️ [configuration.md](configuration.md) — environment variables
