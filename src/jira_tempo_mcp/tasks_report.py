"""Tasks report generator — user task lists grouped by status.

Two modes:
- **Individual** (single user): all tasks, grouped by status, with full
  details (summary, due date, priority, comments).
- **Group** (multiple users): only active tasks (status category
  ``In Progress``), grouped by user then by status.

Active-status detection uses the Jira ``statusCategory.name`` field which
is language-independent (``In Progress``, ``To Do``, ``Done``) — this
works on installations with Russian status names.

Output formats (``fmt`` parameter):
- ``md`` (default): Markdown with tables, emojis, collapsible comments.
- ``txt``: plain text (legacy format).
- ``json``: structured JSON with all data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz

from .client import JiraTempoClient, JiraTempoError
from .config import Config
from .templates._shared import format_date, md_escape_cell, month_ru, truncate_text

logger = logging.getLogger(__name__)

# Status category keys that count as "active" (language-independent).
# Jira's statusCategory.key is always one of: "indeterminate" (In Progress),
# "new" (To Do), "done" (Done). The .name field is localized (Russian on
# this installation), so we match on .key for reliability.
_ACTIVE_CATEGORY_KEY = "indeterminate"

# Emoji map for status categories (language-independent key → emoji).
_STATUS_EMOJI: dict[str, str] = {
    "indeterminate": "🔄",  # In Progress
    "new": "📋",  # To Do / Open
    "done": "✅",  # Done
}

# Fallback emoji map for localized status names (when category key is empty).
_STATUS_EMOJI_FALLBACK: dict[str, str] = {
    "In Progress": "🔄",
    "В работе": "🔄",
    "To Do": "📋",
    "Открыта": "📋",
    "Open": "📋",
    "Done": "✅",
    "Готово": "✅",
    "In Review": "👀",
    "На рассмотрении": "👀",
    "Blocked": "⏸️",
    "Заблокирована": "⏸️",
}

_VALID_FORMATS = ("md", "txt", "json")


@dataclass
class TasksReportResult:
    """Result of :func:`generate_tasks_report`."""

    file_path: Path
    summary: str
    total_tasks: int


def _format_jira_date(raw: str) -> str:
    """Format a Jira datetime/date string as DD.MM.YYYY.

    Jira returns dates in two formats:
    - ``2026-06-30`` (duedate field)
    - ``2026-06-20T11:43:12.000+0300`` (created/updated fields)
    Returns empty string if parsing fails.
    """
    if not raw:
        return ""
    try:
        # Try full ISO datetime first.
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%d.%m.%Y")
        # Plain date.
        return format_date(datetime.fromisoformat(raw).date())
    except (ValueError, TypeError):
        return raw


def _is_active_task(task: dict[str, Any]) -> bool:
    """Check if a task is in an active status category.

    Uses ``statusCategoryKey`` (language-independent: ``indeterminate``)
    with fallback to ``statusCategory`` name matching for installations
    that return English category names.
    """
    cat_key = str(task.get("statusCategoryKey", ""))
    if cat_key:
        return cat_key == _ACTIVE_CATEGORY_KEY
    # Fallback: match on localized name (English installations).
    category = str(task.get("statusCategory", ""))
    return category in ("In Progress", "В работе")


def _status_emoji(task: dict[str, Any]) -> str:
    """Get emoji for a task based on its status category."""
    cat_key = task.get("statusCategoryKey", "")
    if cat_key and cat_key in _STATUS_EMOJI:
        return _STATUS_EMOJI[cat_key]
    status_name = task.get("statusCategory", "") or task.get("status", "")
    return _STATUS_EMOJI_FALLBACK.get(status_name, "📌")


def _group_tasks_by_status(tasks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group tasks by their status name, preserving insertion order."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        status = task.get("status", "Без статуса") or "Без статуса"
        groups[status].append(task)
    return groups


# --- Markdown rendering ---


def _render_individual_md(
    username: str,
    display_name: str,
    tasks: list[dict[str, Any]],
    tz: str,
) -> str:
    """Render a single-user report in Markdown: tables, emojis, collapsible comments.

    Uses the shared truncate_text (50 chars for summaries) and md_escape_cell
    helpers for consistent styling across all report types.
    """
    now = datetime.now(pytz.timezone(tz))
    lines: list[str] = [
        f"# \u041e\u0442\u0447\u0451\u0442 \u043f\u043e \u0437\u0430\u0434\u0430\u0447\u0430\u043c: {display_name} ({username})",
        "",
        f"\U0001f4c5 \u0414\u0430\u0442\u0430 \u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f: {now.strftime('%d.%m.%Y')}",
        "",
    ]

    groups = _group_tasks_by_status(tasks)

    # --- Summary table at the top ---
    lines.append("## \U0001f4ca \u0420\u0435\u0437\u044e\u043c\u0435")
    lines.append("")
    lines.append(
        "| \u0421\u0442\u0430\u0442\u0443\u0441 | \u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e |"
    )
    lines.append("|--------|-----------:|")
    for status, group_tasks in groups.items():
        emoji = _status_emoji(group_tasks[0]) if group_tasks else "\U0001f4cc"
        lines.append(f"| {emoji} {status} | {len(group_tasks)} |")
    lines.append(f"| **\u0412\u0441\u0435\u0433\u043e** | **{len(tasks)}** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Per-status sections with task tables ---
    task_num = 0
    for status, group_tasks in groups.items():
        emoji = _status_emoji(group_tasks[0]) if group_tasks else "\U0001f4cc"
        lines.append(f"## {emoji} {status} ({len(group_tasks)})")
        lines.append("")

        has_comments = any(t.get("comment_count", 0) > 0 for t in group_tasks)

        if has_comments:
            lines.append(
                "| # | \u041a\u043b\u044e\u0447 | \u0417\u0430\u0434\u0430\u0447\u0430 | \u041f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442 | \u0421\u0440\u043e\u043a | \u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e | \u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438 |"
            )
            lines.append("|---:|------|--------|-----------|------|-----------|-------------:|")
        else:
            lines.append(
                "| # | \u041a\u043b\u044e\u0447 | \u0417\u0430\u0434\u0430\u0447\u0430 | \u041f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442 | \u0421\u0440\u043e\u043a | \u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u043e |"
            )
            lines.append("|---:|------|--------|-----------|------|-----------|")

        for task in group_tasks:
            task_num += 1
            key = task.get("key", "")
            summary = task.get("summary", "")
            priority = task.get("priority", "") or ""
            duedate = _format_jira_date(task.get("duedate", "")) or "\u2014"
            updated = _format_jira_date(task.get("updated", "")) or "\u2014"
            comment_count = task.get("comment_count", 0)

            if has_comments:
                lines.append(
                    f"| {task_num} | {key} | {md_escape_cell(truncate_text(summary, 50))} | "
                    f"{md_escape_cell(priority)} | {duedate} | {updated} | {comment_count} |"
                )
            else:
                lines.append(
                    f"| {task_num} | {key} | {md_escape_cell(truncate_text(summary, 50))} | "
                    f"{md_escape_cell(priority)} | {duedate} | {updated} |"
                )

        lines.append("")

        # Collapsible comments for tasks in this status group.
        for task in group_tasks:
            if task.get("comment_count", 0) > 0:
                key = task.get("key", "")
                comments = task.get("comments", [])
                lines.append("<details>")
                lines.append(
                    f"<summary>\U0001f4ac \u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438 \u043a {key}</summary>"
                )
                lines.append("")
                for c in comments:
                    author = c.get("author", "?")
                    body = c.get("body", "")
                    created = _format_jira_date(c.get("created", "")) or "\u2014"
                    lines.append(f"- **{author}** ({created}): {body}")
                lines.append("")
                lines.append("</details>")
                lines.append("")

    return "\n".join(lines)


def _render_group_md(
    users: list[str],
    user_display_names: dict[str, str],
    tasks_by_user: dict[str, list[dict[str, Any]]],
    tz: str,
) -> str:
    """Render a multi-user report in Markdown: only active tasks, per-user sections.

    Layout:
    1. Title + metadata.
    2. Summary table at the top: per-user active task counts + total.
    3. Per-user sections (H2) with status-grouped task tables.
    """
    now = datetime.now(pytz.timezone(tz))

    # --- Compute per-user active counts ---
    per_user_active: dict[str, list[dict[str, Any]]] = {}
    total_active = 0
    for username in users:
        all_tasks = tasks_by_user.get(username, [])
        active_tasks = [t for t in all_tasks if _is_active_task(t)]
        per_user_active[username] = active_tasks
        total_active += len(active_tasks)

    lines: list[str] = [
        "# \u041e\u0442\u0447\u0451\u0442 \u043f\u043e \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u043c \u0437\u0430\u0434\u0430\u0447\u0430\u043c \u043a\u043e\u043c\u0430\u043d\u0434\u044b",
        "",
        f"\U0001f4c5 \u0414\u0430\u0442\u0430 \u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f: {now.strftime('%d.%m.%Y')}",
        f"\U0001f465 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0438: {', '.join(users)}",
        "",
    ]

    # --- Summary table at the top ---
    lines.append("## \U0001f4ca \u0421\u0432\u043e\u0434\u043a\u0430")
    lines.append("")
    lines.append(
        "| \u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a | \u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0437\u0430\u0434\u0430\u0447 |"
    )
    lines.append("|-----------|---------------:|")
    for username in users:
        display = user_display_names.get(username, username)
        lines.append(f"| {display} | {len(per_user_active[username])} |")
    lines.append(f"| **\u0412\u0441\u0435\u0433\u043e** | **{total_active}** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Per-user sections ---
    for username in users:
        active_tasks = per_user_active[username]
        display = user_display_names.get(username, username)
        lines.append(
            f"## {display} ({len(active_tasks)} \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445)"
        )
        lines.append("")

        if not active_tasks:
            lines.append(
                "*(\u043d\u0435\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0437\u0430\u0434\u0430\u0447)*"
            )
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        groups = _group_tasks_by_status(active_tasks)
        for status, group_tasks in groups.items():
            emoji = _status_emoji(group_tasks[0]) if group_tasks else "\U0001f4cc"
            lines.append(f"### {emoji} {status}")
            lines.append("")
            lines.append("| \u041a\u043b\u044e\u0447 | \u0417\u0430\u0434\u0430\u0447\u0430 |")
            lines.append("|------|--------|")
            for task in group_tasks:
                key = task.get("key", "")
                summary = task.get("summary", "")
                lines.append(f"| {key} | {md_escape_cell(truncate_text(summary, 50))} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Clean trailing separators.
    while lines and (lines[-1] == "" or lines[-1] == "---"):
        lines.pop()
    lines.append("")
    return "\n".join(lines)


# --- Plain text rendering (legacy) ---


def _render_individual_txt(
    username: str,
    display_name: str,
    tasks: list[dict[str, Any]],
    tz: str,
) -> str:
    """Render a single-user report in plain text (legacy format)."""
    now = datetime.now(pytz.timezone(tz))
    lines: list[str] = [
        f"Отчёт по задачам: {display_name} ({username})",
        f"Дата формирования: {now.strftime('%d.%m.%Y')}",
        "",
    ]

    groups = _group_tasks_by_status(tasks)
    task_num = 0
    for status, group_tasks in groups.items():
        lines.append(f"=== {status} ({len(group_tasks)}) ===")
        for task in group_tasks:
            task_num += 1
            key = task.get("key", "")
            summary = task.get("summary", "")
            priority = task.get("priority", "")
            duedate = _format_jira_date(task.get("duedate", ""))
            updated = _format_jira_date(task.get("updated", ""))
            comments = task.get("comments", [])
            comment_count = task.get("comment_count", 0)

            lines.append(f"  {task_num}. [{key}] {summary}")
            meta_parts = [f"Приоритет: {priority or '—'}"]
            if duedate:
                meta_parts.append(f"Срок: {duedate}")
            if updated:
                meta_parts.append(f"Обновлено: {updated}")
            lines.append(f"     {' | '.join(meta_parts)}")

            if comment_count > 0:
                lines.append(f"     Комментарии ({comment_count}):")
                for c in comments:
                    author = c.get("author", "?")
                    body = c.get("body", "")
                    lines.append(f'       - {author}: "{body}"')
            lines.append("")

    # Summary section.
    lines.append("=== Резюме ===")
    lines.append(f"Всего задач: {len(tasks)}")
    for status, group_tasks in groups.items():
        lines.append(f"  - {status}: {len(group_tasks)}")
    lines.append("")
    return "\n".join(lines)


def _render_group_txt(
    users: list[str],
    user_display_names: dict[str, str],
    tasks_by_user: dict[str, list[dict[str, Any]]],
    tz: str,
) -> str:
    """Render a multi-user report in plain text (legacy format)."""
    now = datetime.now(pytz.timezone(tz))
    lines: list[str] = [
        "Отчёт по активным задачам команды",
        f"Дата формирования: {now.strftime('%d.%m.%Y')}",
        f"Пользователи: {', '.join(users)}",
        "",
    ]

    total_active = 0
    per_user_counts: dict[str, int] = {}

    for username in users:
        all_tasks = tasks_by_user.get(username, [])
        active_tasks = [t for t in all_tasks if _is_active_task(t)]
        per_user_counts[username] = len(active_tasks)
        total_active += len(active_tasks)

        display = user_display_names.get(username, username)
        lines.append(f"== {display} ({len(active_tasks)} активных) ==")

        if not active_tasks:
            lines.append("  (нет активных задач)")
            lines.append("")
            continue

        groups = _group_tasks_by_status(active_tasks)
        for status, group_tasks in groups.items():
            lines.append(f"  {status}:")
            for task in group_tasks:
                key = task.get("key", "")
                summary = task.get("summary", "")
                lines.append(f"    - [{key}] {summary}")
        lines.append("")

    # Summary section.
    lines.append("== Сводка ==")
    lines.append(f"Всего активных задач: {total_active}")
    for username in users:
        lines.append(
            f"  - {user_display_names.get(username, username)}: {per_user_counts[username]}"
        )
    lines.append("")
    return "\n".join(lines)


# --- JSON rendering ---


def _render_individual_json(
    username: str,
    display_name: str,
    tasks: list[dict[str, Any]],
    tz: str,
) -> str:
    """Render a single-user report as structured JSON."""
    now = datetime.now(pytz.timezone(tz))
    groups = _group_tasks_by_status(tasks)

    status_groups: list[dict[str, Any]] = []
    for status, group_tasks in groups.items():
        emoji = _status_emoji(group_tasks[0]) if group_tasks else "📌"
        status_groups.append(
            {
                "status": status,
                "emoji": emoji,
                "count": len(group_tasks),
                "tasks": [
                    {
                        "key": t.get("key", ""),
                        "summary": t.get("summary", ""),
                        "priority": t.get("priority", ""),
                        "duedate": _format_jira_date(t.get("duedate", "")),
                        "updated": _format_jira_date(t.get("updated", "")),
                        "comment_count": t.get("comment_count", 0),
                        "comments": t.get("comments", []),
                    }
                    for t in group_tasks
                ],
            }
        )

    data = {
        "username": username,
        "display_name": display_name,
        "generated_at": now.strftime("%d.%m.%Y"),
        "total_tasks": len(tasks),
        "status_groups": status_groups,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _render_group_json(
    users: list[str],
    user_display_names: dict[str, str],
    tasks_by_user: dict[str, list[dict[str, Any]]],
    tz: str,
) -> str:
    """Render a multi-user report as structured JSON (active tasks only)."""
    now = datetime.now(pytz.timezone(tz))

    per_user: list[dict[str, Any]] = []
    total_active = 0
    for username in users:
        all_tasks = tasks_by_user.get(username, [])
        active_tasks = [t for t in all_tasks if _is_active_task(t)]
        display = user_display_names.get(username, username)
        total_active += len(active_tasks)

        groups = _group_tasks_by_status(active_tasks)
        status_groups: list[dict[str, Any]] = []
        for status, group_tasks in groups.items():
            emoji = _status_emoji(group_tasks[0]) if group_tasks else "📌"
            status_groups.append(
                {
                    "status": status,
                    "emoji": emoji,
                    "count": len(group_tasks),
                    "tasks": [
                        {
                            "key": t.get("key", ""),
                            "summary": t.get("summary", ""),
                        }
                        for t in group_tasks
                    ],
                }
            )

        per_user.append(
            {
                "username": username,
                "display_name": display,
                "active_count": len(active_tasks),
                "status_groups": status_groups,
            }
        )

    data = {
        "generated_at": now.strftime("%d.%m.%Y"),
        "users": users,
        "total_active": total_active,
        "per_user": per_user,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


async def _resolve_display_names(
    client: JiraTempoClient,
    users: list[str],
) -> dict[str, str]:
    """Resolve display names for a list of usernames via user search.

    Falls back to the username itself if resolution fails.
    """
    display_names: dict[str, str] = {}
    for username in users:
        try:
            results = await client.search_users(username, max_results=5)
            for u in results:
                if u.get("name") == username:
                    display_names[username] = u.get("displayName", username)
                    break
            if username not in display_names and results:
                display_names[username] = results[0].get("displayName", username)
        except JiraTempoError:
            display_names[username] = username
        if username not in display_names:
            display_names[username] = username
    return display_names


async def generate_tasks_report(
    client: JiraTempoClient,
    config: Config,
    users: list[str],
    *,
    active_only: bool = False,
    output_dir: Path | None = None,
    fmt: str = "md",
) -> TasksReportResult:
    """Generate a tasks report file and return its path + summary.

    Args:
        users: list of Jira usernames.
        active_only: if True, only include active tasks (status category
            ``In Progress``). Automatically forced True for multiple users.
        output_dir: directory to write the report. Defaults to
            ``config.report_output_dir`` or ``./reports``.
        fmt: output format — ``md`` (Markdown, default), ``txt`` (plain text),
            ``json`` (structured JSON).

    For a single user: all tasks grouped by status with full details.
    For multiple users: only active tasks, grouped by user then status.
    """
    if not users:
        raise ValueError("users must be a non-empty list of Jira usernames.")

    if fmt not in _VALID_FORMATS:
        raise ValueError(f"Invalid format {fmt!r}. Supported: {', '.join(_VALID_FORMATS)}.")

    is_group = len(users) > 1
    # Group mode is always active-only per spec.
    effective_active_only = active_only or is_group

    tz = config.timezone
    now = datetime.now(pytz.timezone(tz))

    # Fetch tasks for all users concurrently.
    logger.info(
        "Tasks report: fetching tasks for %d user(s) (active_only=%s, fmt=%s)",
        len(users),
        effective_active_only,
        fmt,
    )

    async def _fetch_one(username: str) -> list[dict[str, Any]]:
        try:
            return await client.list_user_tasks(username)
        except JiraTempoError as exc:
            logger.warning("Failed to fetch tasks for %s: %s", username, exc)
            return []

    tasks_by_user: dict[str, list[dict[str, Any]]] = {}
    results = await asyncio.gather(*[_fetch_one(u) for u in users])
    for username, user_tasks in zip(users, results, strict=True):
        tasks_by_user[username] = user_tasks

    # Resolve display names.
    display_names = await _resolve_display_names(client, users)

    # Render report.
    if is_group:
        if fmt == "md":
            report_text = _render_group_md(users, display_names, tasks_by_user, tz)
        elif fmt == "json":
            report_text = _render_group_json(users, display_names, tasks_by_user, tz)
        else:
            report_text = _render_group_txt(users, display_names, tasks_by_user, tz)
        total_tasks = sum(
            len([t for t in tasks_by_user.get(u, []) if _is_active_task(t)]) for u in users
        )
    else:
        username = users[0]
        all_tasks = tasks_by_user.get(username, [])
        if effective_active_only:
            all_tasks = [t for t in all_tasks if _is_active_task(t)]
        display = display_names.get(username, username)
        if fmt == "md":
            report_text = _render_individual_md(username, display, all_tasks, tz)
        elif fmt == "json":
            report_text = _render_individual_json(username, display, all_tasks, tz)
        else:
            report_text = _render_individual_txt(username, display, all_tasks, tz)
        total_tasks = len(all_tasks)

    # --- Output path ---
    if output_dir is None:
        base = config.report_output_dir or str(Path.home() / ".mcp" / "jira-tempo-mcp" / "reports")
        subdir = "tasks" if len(users) == 1 else "tasks-team"
        output_dir = Path(base) / str(now.year) / month_ru(now.month) / subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = fmt
    # UX-8: ISO dates in filename for clarity across years.
    if is_group:
        filename = f"tasks_active_{now.strftime('%Y-%m-%d')}.{ext}"
    else:
        prefix = users[0]
        filename = f"tasks_{prefix}_{now.strftime('%Y-%m-%d')}.{ext}"
    out_path = output_dir / filename
    out_path.write_text(report_text, encoding="utf-8")

    logger.info("Tasks report written: %s (%d tasks, fmt=%s)", out_path, total_tasks, fmt)

    summary = f"Tasks report generated: {out_path} ({total_tasks} tasks, fmt={fmt})"
    return TasksReportResult(file_path=out_path, summary=summary, total_tasks=total_tasks)
