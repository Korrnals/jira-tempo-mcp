# jira-tempo-mcp (npm wrapper)

**MCP server for self-hosted Jira (Server / Data Center) + Tempo Timesheets 4.**
This npm package is a thin wrapper around the real thing: the Python
[`jira-tempo-mcp`](https://pypi.org/project/jira-tempo-mcp/) package
([GitHub](https://github.com/Korrnals/jira-tempo-mcp)) — a stdio MCP server
with 19 tools (worklogs, reports, issue creation from templates) and one-command
AI-harness integration.

## Install

```bash
npm install -g jira-tempo-mcp
```

The postinstall step installs the Python package (pipx when available, pip
otherwise) when Python ≥ 3.11 is present, then you pick what to run:

```bash
jira-tempo-mcp                     # run the MCP server over stdio
jira-tempo-mcp install             # interactive installer (venv + .env + VS Code)
jira-tempo-mcp install-specialist  # install the JTM agent into AI harnesses
jira-tempo-mcp install-specialist --list
jira-tempo-mcp update              # self-update the Python package
jira-tempo-mcp --version
```

No Python? Install Python ≥ 3.11, then `pip install jira-tempo-mcp`.

## What you get

- **19 MCP tools**: worklog tracking, weekly/team/tasks reports (txt/md/json),
  issue search by JQL, templates-driven issue creation, and more
- **`install-specialist`** — installs the `JTM: Jira Tempo Reports` agent
  (agent md + skill + knowledge doc) into AI harnesses: Copilot Chat, Claude
  Code, OpenCode; `--harness` to pick, `--remove` to uninstall — idempotent
- **`update`** — self-update: `pip install --upgrade` for package installs,
  `git pull --ff-only` + reinstall for editable installs

All commands pass through to the Python CLI; arguments are forwarded verbatim.

## How it works

`bin/cli.js` locates a runner for the Python package — the `jira-tempo-mcp`
console script on `PATH`, else any Python ≥ 3.11 with `jira_tempo_mcp`
importable. If the Python package is missing, commands that make sense
(`--help`, `install`, `update`, bare server start) trigger a one-time
auto-install via pipx → pip fallback, then re-dispatch.

Full documentation: [github.com/Korrnals/jira-tempo-mcp](https://github.com/Korrnals/jira-tempo-mcp)

## License

MIT — same as the Python package.