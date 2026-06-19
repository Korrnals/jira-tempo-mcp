"""MCP server entrypoint — exposes Jira + Tempo tools to MCP clients.

Run as a stdio MCP server:
    python -m jira_tempo_mcp.server
or via the console script:
    jira-tempo-mcp
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytz
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .client import JiraTempoClient, JiraTempoError, WorkerKeyResolutionError
from .config import Config, load_config
from .report import generate_weekly_report
from .utils import format_seconds_to_human, iso_now, parse_duration_to_seconds

logger = logging.getLogger("jira-tempo-mcp")

# Regex for validating Jira issue keys (m10).
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")

# --- Tool definitions ---

TOOLS: list[Tool] = [
    Tool(
        name="list_worklogs",
        description=(
            "List Tempo worklogs for a date range (or a single day). "
            "Returns worklogs with issue key, time spent, comment, and date. "
            "Only actually tracked time is returned — planned time is excluded."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date (ISO YYYY-MM-DD). Defaults to today.",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date (ISO YYYY-MM-DD). Defaults to date_from.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="get_worklog",
        description="Get a single Tempo worklog by its Tempo internal ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "worklog_id": {"type": "string", "description": "Tempo worklog ID"},
            },
            "required": ["worklog_id"],
        },
    ),
    Tool(
        name="create_worklog",
        description=(
            "Track (log) time on a Jira issue via Tempo. "
            "Provide issue key, duration (e.g. '1h 30m', '2h', '45m'), and optional comment. "
            "The worklog is attributed to the token owner unless author_account_id is given."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g. PROJECT-102)",
                },
                "time_spent": {
                    "type": "string",
                    "description": "Human duration: '1h 30m', '2h', '45m', '1d 2h'",
                },
                "comment": {"type": "string", "description": "Optional worklog comment"},
                "date_started": {
                    "type": "string",
                    "description": "ISO 8601 datetime with tz (e.g. 2026-06-19T10:00:00+03:00). Defaults to now.",
                },
                "author_account_id": {
                    "type": "string",
                    "description": "Optional Tempo worker key. Defaults to token owner.",
                },
            },
            "required": ["issue_key", "time_spent"],
        },
    ),
    Tool(
        name="delete_worklog",
        description="Delete a Tempo worklog by its ID. Use for undo/correction of mis-tracked time.",
        inputSchema={
            "type": "object",
            "properties": {
                "worklog_id": {"type": "string", "description": "Tempo worklog ID to delete"},
            },
            "required": ["worklog_id"],
        },
    ),
    Tool(
        name="get_issue",
        description="Get Jira issue metadata: summary, status, project, issue type.",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {
                    "type": "string",
                    "description": "Jira issue key (e.g. PROJECT-102)",
                },
            },
            "required": ["issue_key"],
        },
    ),
    Tool(
        name="list_favorite_issues",
        description="List favorite issues for the current Jira user. Returns keys and summaries.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    Tool(
        name="generate_weekly_report",
        description=(
            "Generate a weekly work report from Tempo worklogs and save it as a .txt file. "
            "Follows the template in reports/2026/README.md: groups worklogs by "
            "issue, maps known issues to stable sections, writes to "
            "reports/<year>/<month>/your-username_<DDMMYY>-<DDMMYY>.txt. "
            "Returns the path to the generated file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "target_date": {
                    "type": "string",
                    "description": "Any date within the target week (ISO YYYY-MM-DD). Defaults to today.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory. Defaults to REPORT_OUTPUT_DIR env or ./reports.",
                },
            },
            "required": [],
        },
    ),
]


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def _json_safe(obj: Any) -> Any:
    """Make any object JSON-serializable for MCP output."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return str(obj)


def _validate_issue_key(key: str) -> str:
    """Validate Jira issue key format. Raises ValueError if invalid."""
    if not _ISSUE_KEY_RE.match(key):
        raise ValueError(
            f"Invalid issue key {key!r}. Expected format: PROJECT-NUMBER (e.g. PROJECT-102)."
        )
    return key


def _validate_date(date_str: str, field_name: str) -> date:
    """Parse and validate an ISO date string. Raises ValueError if invalid."""
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        raise ValueError(
            f"Invalid date for {field_name}: {date_str!r}. Expected ISO format YYYY-MM-DD."
        ) from None


def _user_friendly_error(exc: Exception) -> str:
    """Map known exception types to user-friendly messages (m11)."""
    if isinstance(exc, WorkerKeyResolutionError):
        return f"Could not identify your Tempo worker key: {exc}. Check JIRA_USER or Tempo connectivity."
    if isinstance(exc, JiraTempoError):
        return f"Jira/Tempo API error: {exc}"
    if isinstance(exc, ValueError):
        return f"Invalid input: {exc}"
    if isinstance(exc, KeyError):
        return f"Missing required argument: {exc}"
    # For unexpected errors, show class name only in DEBUG, generic message otherwise.
    return f"Unexpected error: {exc.__class__.__name__}"


# --- Tool handlers (m3: dispatch table) ---


async def _handle_list_worklogs(
    arguments: dict[str, Any], config: Config, client: JiraTempoClient
) -> str:
    tz = pytz.timezone(config.timezone)
    today = datetime.now(tz).date()
    date_from = arguments.get("date_from") or today.isoformat()
    date_to = arguments.get("date_to") or date_from

    wk = await client.find_worker_key(config.jira_user)
    worker_keys = [wk]
    worklogs = await client.search_worklogs(date_from, date_to, worker_keys=worker_keys)

    rows = []
    for wl in worklogs:
        # m1: safe extraction with isinstance guard.
        key = wl.get("issueKey")
        if not key:
            issue = wl.get("issue")
            key = issue.get("key", "?") if isinstance(issue, dict) else "?"
        seconds = wl.get("timeSpentSeconds", 0)
        comment = wl.get("comment", "") or ""
        if isinstance(comment, dict):
            comment = comment.get("content", "")
        started = wl.get("startDate", "")
        # m2: explicit fallback to "?" if all lookups return falsy.
        wl_id = wl.get("tempoWorklogId") or wl.get("id") or wl.get("worklogId") or "?"
        rows.append(
            f"- {started} | {key} | {format_seconds_to_human(seconds)} | id={wl_id}"
            + (f" | {comment}" if comment else "")
        )
    header = f"Worklogs {date_from} .. {date_to} ({len(worklogs)} entries):\n"
    return header + "\n".join(rows) if rows else header + "(none)"


async def _handle_get_worklog(
    arguments: dict[str, Any], config: Config, client: JiraTempoClient
) -> str:
    wl_id = arguments["worklog_id"]
    wl = await client.get_worklog(wl_id)
    # m9: format as key/value lines, not raw repr.
    lines = [f"Worklog {wl_id}:"]
    for k, v in wl.items():
        lines.append(f"  {k}: {_json_safe(v)}")
    return "\n".join(lines)


async def _handle_create_worklog(
    arguments: dict[str, Any], config: Config, client: JiraTempoClient
) -> str:
    issue_key = _validate_issue_key(arguments["issue_key"])
    time_spent = arguments["time_spent"]
    seconds = parse_duration_to_seconds(time_spent)
    date_started = arguments.get("date_started") or iso_now(config.timezone)
    comment = arguments.get("comment", "")
    author = arguments.get("author_account_id")
    result = await client.create_worklog(
        issue_key=issue_key,
        time_spent_seconds=seconds,
        date_started=date_started,
        comment=comment,
        author_account_id=author,
    )
    wl_id = result.get("tempoWorklogId") or result.get("id", "?")
    msg = f"Tracked {format_seconds_to_human(seconds)} on {issue_key} at {date_started}. Worklog ID: {wl_id}"
    if comment:
        msg += f". Comment: {comment}"
    return msg


async def _handle_delete_worklog(
    arguments: dict[str, Any], config: Config, client: JiraTempoClient
) -> str:
    wl_id = arguments["worklog_id"]
    await client.delete_worklog(wl_id)
    return f"Deleted worklog {wl_id}."


async def _handle_get_issue(
    arguments: dict[str, Any], config: Config, client: JiraTempoClient
) -> str:
    key = _validate_issue_key(arguments["issue_key"])
    issue = await client.get_issue(key)
    fields = issue.get("fields", {})
    summary = fields.get("summary", "") if isinstance(fields, dict) else ""
    status = fields.get("status", {}).get("name", "") if isinstance(fields, dict) else ""
    project = fields.get("project", {}).get("name", "") if isinstance(fields, dict) else ""
    return f"{key}: {summary}\nStatus: {status}\nProject: {project}"


async def _handle_list_favorites(
    arguments: dict[str, Any], config: Config, client: JiraTempoClient
) -> str:
    favs = await client.list_favorite_issues()
    if not favs:
        return "No favorite issues found."
    lines = [f"- {f['key']}: {f['summary']}" for f in favs]
    return f"Favorite issues ({len(favs)}):\n" + "\n".join(lines)


async def _handle_generate_report(
    arguments: dict[str, Any], config: Config, client: JiraTempoClient
) -> str:
    target = None
    if td := arguments.get("target_date"):
        # m8: validate date format with helpful error.
        target = _validate_date(td, "target_date")
    out_dir = None
    if raw_dir := arguments.get("output_dir"):
        # M2: validate output_dir against path traversal.
        # Reject paths that resolve outside the allowed root directory.
        resolved = Path(raw_dir).resolve()
        allowed_root = Path(config.report_output_dir or str(Path.cwd() / "reports")).resolve()
        try:
            resolved.relative_to(allowed_root)
        except ValueError:
            raise ValueError(
                f"output_dir {raw_dir!r} resolves outside the allowed root {allowed_root}. "
                f"Path traversal is not permitted."
            ) from None
        out_dir = resolved
    path = await generate_weekly_report(client, config, target_date=target, output_dir=out_dir)
    return f"Weekly report generated: {path}"


# Dispatch table (m3).
_TOOL_HANDLERS: dict[str, Any] = {
    "list_worklogs": _handle_list_worklogs,
    "get_worklog": _handle_get_worklog,
    "create_worklog": _handle_create_worklog,
    "delete_worklog": _handle_delete_worklog,
    "get_issue": _handle_get_issue,
    "list_favorite_issues": _handle_list_favorites,
    "generate_weekly_report": _handle_generate_report,
}


async def serve(config: Config) -> None:
    """Run the MCP server over stdio."""
    server = Server("jira-tempo-mcp")

    # mypy: MCP SDK decorators are untyped — suppress until upstream adds hints.
    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        async with JiraTempoClient(config) as client:
            try:
                result = await handler(arguments, config, client)
            except Exception as exc:
                logger.exception("Tool %s failed", name)
                result = _user_friendly_error(exc)
            return [TextContent(type="text", text=result)]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Console script entrypoint."""
    config = load_config()
    _setup_logging(config.log_level)
    logger.info("Starting jira-tempo-mcp for %s", config.jira_base_url)
    asyncio.run(serve(config))


if __name__ == "__main__":
    main()
