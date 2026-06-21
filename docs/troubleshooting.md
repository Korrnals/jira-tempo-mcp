# 🐛 Troubleshooting

Common errors and their fixes.

---

## 🐛 MCP server does not appear in the panel

**🩺 Symptom:** the `jira-tempo` server is not listed in the VS Code MCP panel.

**🔍 Cause:** VS Code has not re-read `mcp.json` after the change.

**✅ Fix:**

```text
Ctrl+Shift+P → Developer: Reload Window
```

---

## ❌ `Failed to read envFile '~/...'`

**🩺 Symptom:** MCP panel shows `Failed to read envFile '~/.config/Code/User/.env.local'`.

**🔍 Cause:** VS Code MCP-host resolves `~` against its own root namespace, not
the user's `$HOME`. This breaks in sandboxed environments (distrobox, snap,
flatpak, containers).

**✅ Fix:** use an **absolute path** for `envFile` in `mcp.json`:

```json
"envFile": "/home/your-username/.config/Code/User/.env.local"
```

For distrobox:

```json
"envFile": "/var/home/your-username/.distrobox/box/home/.config/Code/User/.env.local"
```

> 💡 **Tip:** See [mcp-integration.md](mcp-integration.md#absolute-paths-for-envfile-distrobox--containers).

---

## ❌ `ModuleNotFoundError: No module named 'pytz'`

**🩺 Symptom:** the server crashes on startup with `ModuleNotFoundError: No
module named 'pytz'` (or `mcp`, `httpx`, `pydantic`).

**🔍 Cause:** the `python` in `mcp.json` is not the venv python — it bypasses
the editable install and its site-packages.

**✅ Fix:** point `command` at the venv python explicitly:

```json
"command": "${workspaceFolder}/.venv/bin/python"
```

Or, in a user-level config:

```json
"command": "/home/your-username/projects/jira-tempo-mcp/.venv/bin/python"
```

> 💡 **Tip:** The `PYTHONPATH` env var pointing at `src/` is a belt-and-suspenders
> fallback for environments that override `PYTHONHOME`.

---

## ❌ `400 Authorization header badly formatted`

**🩺 Symptom:** an HTTP-type MCP server (e.g. GitHub MCP) returns
`400 Authorization header badly formatted`.

**🔍 Cause:** `${env:VAR}` substitution does not work inside `headers` for
HTTP-type servers.

**✅ Fix:** use `${input:...}` instead, which prompts once and caches the value
in VS Code secret storage. See
[mcp-integration.md](mcp-integration.md#input-for-http-type-servers).

---

## ❌ `JIRA_BASE_URL or JIRA_PAT missing`

**🩺 Symptom:** the server exits immediately with
`JIRA_BASE_URL or JIRA_PAT missing` (pydantic validation error).

**🔍 Cause:** the required env vars are not visible to the server process.

**✅ Fix:**

1. ✅ Check that `.env.local` exists and contains `JIRA_PAT=...`.
2. ✅ Check that `envFile` in `mcp.json` points to the correct absolute path.
3. ✅ For CLI usage, check that `.env` exists in the project root and has
   `JIRA_BASE_URL`, `JIRA_USER`, `JIRA_PAT` set.
4. ✅ Re-run `python install.py` to regenerate `.env` and re-register the
   VS Code config.

> 💡 **Tip:** See [configuration.md](configuration.md).

---

## ❌ `401 Unauthorized`

**🩺 Symptom:** tool calls return `Jira/Tempo API error: 401 ...`.

**🔍 Cause:** the PAT is invalid, expired, or revoked.

**✅ Fix:**

1. ✅ In Jira: Profile → Personal Access Tokens → create a new token.
2. ✅ Update `JIRA_PAT` in `.env.local` (or `.env` for CLI).
3. ✅ Reload the VS Code window.

> 💡 **Tip:** If using a separate `TEMPO_API_TOKEN`, rotate that too.

---

## ❌ `Could not identify your Tempo worker key`

**🩺 Symptom:** `list_worklogs` or `generate_weekly_report` returns
`Could not identify your Tempo worker key`.

**🔍 Cause:** the configured `JIRA_USER` does not match a Tempo worker, or
Tempo connectivity is broken.

**✅ Fix:**

1. ✅ Verify `JIRA_USER` matches your Jira login (case-sensitive).
2. ✅ Check Tempo Timesheets 4 is installed and licensed on the Jira instance.
3. ✅ Verify `TEMPO_API_TOKEN` (if set separately) is valid for Tempo.

---

## ❌ `output_dir '...' resolves outside the allowed root`

**🩺 Symptom:** `generate_weekly_report` returns
`output_dir '...' resolves outside the allowed root`.

**🔍 Cause:** the `output_dir` argument resolves to a path outside
`REPORT_OUTPUT_DIR` (or `./reports`). This is a path-traversal guard.

**✅ Fix:** pass an `output_dir` that is inside the allowed root, or set
`REPORT_OUTPUT_DIR` to the desired base directory.

> 💡 **Tip:** See [reports.md](reports.md#path-traversal-protection).

---

## ❌ `Could not parse duration: '...'`

**🩺 Symptom:** `create_worklog` returns `Could not parse duration: '...'`.

**🔍 Cause:** `time_spent` contains no valid duration tokens.

**✅ Fix:** use the supported units: `w` (week), `d` (day), `h` (hour), `m` (minute).

| ✅ Valid | ❌ Invalid |
| --- | --- |
| `1h 30m` | `1:30` |
| `2h` | `2 hours` |
| `45m` | `45 minutes` |
| `1d 2h` | `1.5d` |

---

## ❌ `Invalid issue key '...'`

**🩺 Symptom:** `create_worklog` or `get_issue` returns `Invalid issue key '...'`.

**🔍 Cause:** the key does not match `^[A-Z][A-Z0-9]+-\d+$`.

**✅ Fix:** use the full Jira key format: `PROJECT-100`, not `project-100` or
`PROJECT100`.

---

## ⏱️ Server starts but tools time out

**🩺 Symptom:** the server starts, but tool calls hang until
`JIRA_HTTP_TIMEOUT` (default 30 s) elapses.

**🔍 Cause:** the Jira instance is unreachable from the server process
(firewall, VPN, DNS).

**✅ Fix:**

1. ✅ Test connectivity: `curl -I https://jira.example.com`.
2. ✅ If behind a VPN, ensure the VPN is active.
3. ✅ Increase `JIRA_HTTP_TIMEOUT` if the Jira instance is slow.

---

## ➡️ Next steps

- 🔌 [mcp-integration.md](mcp-integration.md) — MCP config details
- ⚙️ [configuration.md](configuration.md) — all env vars
- 🌐 [api.md](api.md#error-handling) — error messages reference
