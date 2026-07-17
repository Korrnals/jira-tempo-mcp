"""Team report generator — aggregates per-user worklogs with rate-limiting.

For each Jira username the generator resolves the Tempo worker key, fetches
worklogs for the target date range, and renders a combined team report via
the ``team_report`` template. HTTP traffic is bounded by an
``asyncio.Semaphore`` (``TEMPO_MAX_CONCURRENT_REQUESTS``) with a small delay
between batches (``TEMPO_REQUEST_DELAY_MS``) and exponential backoff on
HTTP 429 (``TEMPO_MAX_RETRIES``).

Since v0.3.0 the ``fmt`` parameter selects output format:
- ``txt`` (default): plain text via the template system.
- ``md``: Markdown with tables and bold formatting.
- ``json``: structured JSON with all data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytz

from .client import JiraTempoClient, JiraTempoError
from .config import Config
from .templates import ReportTemplate, TemplateRegistry
from .templates._shared import (
    extract_comment,
    extract_issue_key,
    group_worklogs_by_comment_raw,
    md_escape_cell,
    month_ru,
    render_comment_cell,
    truncate_text,
    week_range,
)
from .utils import format_seconds_to_human

logger = logging.getLogger(__name__)

_VALID_FORMATS = ("txt", "md", "json")


@dataclass
class TeamReportResult:
    """Result of :func:`generate_team_report`."""

    file_path: Path
    summary: str
    per_user_totals: dict[str, int]


class RateLimitError(JiraTempoError):
    """Raised when Tempo returns HTTP 429 and retries are exhausted."""


def _week_bounds(date_from: str | None, date_to: str | None, tz: str) -> tuple[date, date]:
    """Resolve (monday, friday) from explicit dates or the current week."""
    today = datetime.now(pytz.timezone(tz)).date()
    if date_from and date_to:
        return date.fromisoformat(date_from), date.fromisoformat(date_to)
    monday, friday = week_range(today)
    return monday, friday


async def _fetch_with_retry(
    client: JiraTempoClient,
    username: str,
    date_from: str,
    date_to: str,
    *,
    max_retries: int,
) -> list[dict[str, Any]]:
    """Resolve worker key + fetch worklogs for one user with 429 backoff.

    Raises :class:`RateLimitError` if 429 persists after ``max_retries``.
    """
    worker_key = await client.find_worker_key(username)
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            worklogs = await client.search_worklogs(date_from, date_to, worker_keys=[worker_key])
            return worklogs
        except JiraTempoError as exc:
            last_exc = exc
            msg = str(exc)
            if "429" in msg and attempt < max_retries:
                delay = 2**attempt  # 1s, 2s, 4s, ...
                logger.warning(
                    "Tempo 429 for user %s (attempt %d/%d) — retrying in %ds",
                    username,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            if "429" in msg:
                raise RateLimitError(
                    f"Tempo rate limit exhausted for user {username!r} after {max_retries} retries"
                ) from exc
            raise
    # Unreachable in practice — loop either returns or raises.
    raise RateLimitError(f"Tempo rate limit exhausted for user {username!r}") from last_exc


async def _fetch_all_users(
    client: JiraTempoClient,
    config: Config,
    users: list[str],
    date_from: str,
    date_to: str,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch worklogs for all users with semaphore-bounded concurrency.

    Users are processed in batches of ``tempo_max_concurrent_requests``;
    a ``tempo_request_delay_ms`` pause is inserted between batches.
    """
    semaphore = asyncio.Semaphore(config.tempo_max_concurrent_requests)
    delay_seconds = config.tempo_request_delay_ms / 1000.0
    results: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    async def _one(username: str) -> None:
        async with semaphore:
            try:
                worklogs = await _fetch_with_retry(
                    client,
                    username,
                    date_from,
                    date_to,
                    max_retries=config.tempo_max_retries,
                )
                results[username] = worklogs
                logger.info("Team report: user %s -> %d worklogs", username, len(worklogs))
            except (JiraTempoError, RateLimitError) as exc:
                logger.warning("Team report: user %s failed: %s", username, exc)
                errors[username] = str(exc)
                results[username] = []

    # Run all tasks; the semaphore bounds concurrency. We insert a delay
    # between waves by chunking the user list manually so the delay is
    # observable even when individual requests are fast.
    concurrency = config.tempo_max_concurrent_requests
    for i in range(0, len(users), concurrency):
        batch = users[i : i + concurrency]
        await asyncio.gather(*(_one(u) for u in batch))
        if i + concurrency < len(users) and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    if errors:
        logger.warning("Team report: %d/%d users had fetch errors", len(errors), len(users))
    return results


def _resolve_issue_titles(
    worklogs_by_user: dict[str, list[dict[str, Any]]],
    config: Config,
    client: JiraTempoClient,
) -> dict[str, str]:
    """Synchronously collect issue titles — caller should await get_issue instead.

    This helper is kept for completeness but the async version below is used
    in practice. Returns only titles already present in ``config.section_map``.
    """
    titles: dict[str, str] = {}
    for worklogs in worklogs_by_user.values():
        for wl in worklogs:
            key = extract_issue_key(wl)
            if key and key not in titles and key in config.section_map:
                titles[key] = config.section_map[key]
    return titles


async def _resolve_issue_titles_async(
    worklogs_by_user: dict[str, list[dict[str, Any]]],
    config: Config,
    client: JiraTempoClient,
) -> dict[str, str]:
    """Fetch Jira summaries for every issue key not in ``section_map``."""
    titles: dict[str, str] = {}
    keys: set[str] = set()
    for worklogs in worklogs_by_user.values():
        for wl in worklogs:
            key = extract_issue_key(wl)
            if key:
                keys.add(key)
    for key in config.section_map:
        titles[key] = config.section_map[key]
    for key in keys:
        if key in titles:
            continue
        try:
            issue = await client.get_issue(key)
            fields = issue.get("fields", {})
            titles[key] = str(fields.get("summary", key)) if isinstance(fields, dict) else key
        except JiraTempoError:
            logger.warning("Team report: could not fetch issue %s", key)
            titles[key] = key
    return titles


def _render_team_md(
    worklogs_by_user: dict[str, list[dict[str, Any]]],
    config: Config,
    monday: date,
    friday: date,
    issue_titles: dict[str, str],
    user_order: list[tuple[str, str]],
) -> str:
    """Render team report in Markdown format — professional table-based layout.

    Layout:
    1. Title with date range (em dash).
    2. Summary table: per-user totals + grand total, sorted by hours desc.
    3. Top-5 cross-team issues table.
    4. Per-user sections (H2): one table per user with all worklogs as rows.
    """
    from .templates._shared import format_date

    # --- Compute per-user totals and cross-issue totals ---
    per_user_totals: dict[str, int] = {}
    cross_issue_totals: dict[str, int] = defaultdict(int)
    user_worklogs_flat: dict[str, list[dict[str, Any]]] = {}

    for username, display_name in user_order:
        header = display_name or username
        user_worklogs = worklogs_by_user.get(username, [])
        user_total = 0
        flat: list[dict[str, Any]] = []
        for wl in user_worklogs:
            key = extract_issue_key(wl)
            if not key:
                continue
            secs = wl.get("timeSpentSeconds")
            if not isinstance(secs, int):
                secs = 0
            user_total += secs
            cross_issue_totals[key] += secs
            flat.append(wl)
        per_user_totals[header] = user_total
        user_worklogs_flat[header] = flat

    grand_total = sum(per_user_totals.values())

    # --- Header ---
    lines: list[str] = [
        f"# Командный отчёт за неделю ({format_date(monday)} \u2014 {format_date(friday)})",
        "",
    ]

    # --- Summary table (sorted by hours desc) ---
    lines.append("## \U0001f4ca \u0421\u0432\u043e\u0434\u043a\u0430")
    lines.append("")
    lines.append(
        "| \u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a | \u0427\u0430\u0441\u044b |"
    )
    lines.append("|-----------|------:|")
    sorted_users = sorted(per_user_totals.items(), key=lambda kv: kv[1], reverse=True)
    for header, total in sorted_users:
        lines.append(f"| {header} | {format_seconds_to_human(total)} |")
    lines.append(
        f"| **\u0418\u0442\u043e\u0433\u043e** | **{format_seconds_to_human(grand_total)}** |"
    )
    lines.append("")

    # --- Top-5 issues table ---
    top_issues = sorted(cross_issue_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    if top_issues:
        lines.append("### \U0001f3c6 \u0422\u043e\u043f-5 \u0437\u0430\u0434\u0430\u0447")
        lines.append("")
        lines.append(
            "| # | \u041a\u043b\u044e\u0447 | \u0417\u0430\u0434\u0430\u0447\u0430 | \u0427\u0430\u0441\u044b |"
        )
        lines.append("|---:|------|--------|------:|")
        for rank, (key, secs) in enumerate(top_issues, start=1):
            title = issue_titles.get(key, key)
            lines.append(
                f"| {rank} | {key} | {md_escape_cell(truncate_text(title, 50))} | "
                f"{format_seconds_to_human(secs)} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")

    # --- Per-user sections ---
    for username, display_name in user_order:
        header = display_name or username
        user_total = per_user_totals[header]
        flat = user_worklogs_flat[header]
        lines.append(f"## {header} ({format_seconds_to_human(user_total)})")
        lines.append("")

        if not flat:
            lines.append(
                "*(\u043d\u0435\u0442 \u043e\u0442\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u043d\u043e\u0433\u043e \u0432\u0440\u0435\u043c\u0435\u043d\u0438)*"
            )
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        # Sort worklogs: by issue key asc, then by seconds desc within issue.
        def _sort_key(wl: dict[str, Any]) -> tuple[str, int]:
            k = extract_issue_key(wl) or ""
            s = wl.get("timeSpentSeconds", 0)
            if not isinstance(s, int):
                s = 0
            return (k, -s)

        sorted_worklogs = sorted(flat, key=_sort_key)

        lines.append(
            "| \u041a\u043b\u044e\u0447 | \u0417\u0430\u0434\u0430\u0447\u0430 | \u0427\u0430\u0441\u044b | \u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439 |"
        )
        lines.append("|------|--------|------:|-------------|")
        for wl in sorted_worklogs:
            key = extract_issue_key(wl) or ""
            title = issue_titles.get(key, config.section_map.get(key, key))
            secs = wl.get("timeSpentSeconds", 0)
            if not isinstance(secs, int):
                secs = 0
            comment = extract_comment(wl)
            lines.append(
                f"| {key} | {md_escape_cell(truncate_text(title, 50))} | "
                f"{format_seconds_to_human(secs)} | "
                f"{render_comment_cell(comment)} |"
            )
        lines.append(f"| | | **{format_seconds_to_human(user_total)}** | |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Remove trailing separator + blank lines for clean ending.
    while lines and (lines[-1] == "" or lines[-1] == "---"):
        lines.pop()
    lines.append("")
    return "\n".join(lines)


def _render_team_json(
    worklogs_by_user: dict[str, list[dict[str, Any]]],
    config: Config,
    monday: date,
    friday: date,
    issue_titles: dict[str, str],
    user_order: list[tuple[str, str]],
) -> str:
    """Render team report as structured JSON."""
    per_user: list[dict[str, Any]] = []
    cross_issue_totals: dict[str, int] = defaultdict(int)
    grand_total = 0

    for username, display_name in user_order:
        user_worklogs = worklogs_by_user.get(username, [])
        header = display_name or username
        user_total = 0
        issues: list[dict[str, Any]] = []

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for wl in user_worklogs:
            key = extract_issue_key(wl)
            if not key:
                continue
            grouped[key].append(wl)
            secs = wl.get("timeSpentSeconds")
            if isinstance(secs, int):
                user_total += secs
                cross_issue_totals[key] += secs

        used: set[str] = set()
        for key in config.stable_order:
            if key not in grouped:
                continue
            title = issue_titles.get(key, config.section_map.get(key, key))
            task_total = sum(w.get("timeSpentSeconds", 0) for w in grouped[key])
            worklog_entries = []
            for comment, secs in group_worklogs_by_comment_raw(grouped[key]):
                worklog_entries.append(
                    {
                        "comment": comment,
                        "seconds": secs,
                        "human": format_seconds_to_human(secs),
                    }
                )
            issues.append(
                {
                    "key": key,
                    "title": title,
                    "total_seconds": task_total,
                    "total_human": format_seconds_to_human(task_total),
                    "worklogs": worklog_entries,
                }
            )
            used.add(key)

        remaining = sorted(
            (k for k in grouped if k not in used),
            key=lambda k: sum(w.get("timeSpentSeconds", 0) for w in grouped[k]),
            reverse=True,
        )
        for key in remaining:
            title = issue_titles.get(key, key)
            task_total = sum(w.get("timeSpentSeconds", 0) for w in grouped[key])
            worklog_entries = []
            for comment, secs in group_worklogs_by_comment_raw(grouped[key]):
                worklog_entries.append(
                    {
                        "comment": comment,
                        "seconds": secs,
                        "human": format_seconds_to_human(secs),
                    }
                )
            issues.append(
                {
                    "key": key,
                    "title": title,
                    "total_seconds": task_total,
                    "total_human": format_seconds_to_human(task_total),
                    "worklogs": worklog_entries,
                }
            )

        grand_total += user_total
        per_user.append(
            {
                "username": username,
                "display_name": header,
                "total_seconds": user_total,
                "total_human": format_seconds_to_human(user_total),
                "issues": issues,
            }
        )

    top_issues = sorted(cross_issue_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_issues_data = [
        {
            "key": key,
            "title": issue_titles.get(key, key),
            "seconds": secs,
            "human": format_seconds_to_human(secs),
        }
        for key, secs in top_issues
    ]

    data = {
        "date_from": monday.isoformat(),
        "date_to": friday.isoformat(),
        "grand_total_seconds": grand_total,
        "grand_total_human": format_seconds_to_human(grand_total),
        "per_user": per_user,
        "top_issues": top_issues_data,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


async def generate_team_report(
    client: JiraTempoClient,
    config: Config,
    users: list[str],
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    section_map: dict[str, str] | None = None,
    template: ReportTemplate | None = None,
    registry: TemplateRegistry | None = None,
    output_dir: Path | None = None,
    fmt: str = "txt",
) -> TeamReportResult:
    """Generate a team report file and return its path + summary.

    users: non-empty list of Jira usernames.
    date_from/date_to: ISO YYYY-MM-DD. Default to the current Mon–Fri.
    section_map: optional override for ``config.section_map`` (applied to a
        copy — the original config is frozen).
    template: optional explicit template instance. If None, the
        ``team_report`` builtin (or ``registry.get("team_report")``) is used.
        Only used when ``fmt="txt"``.
    registry: optional template registry to look up the template by name.
        Only used when ``fmt="txt"``.
    output_dir: directory to write the report. Defaults to
        ``config.team_output_dir`` or ``./reports``.
    fmt: output format — ``txt`` (default, uses template system),
         ``md`` (Markdown), ``json`` (structured JSON).
    """
    if not users:
        raise ValueError("users must be a non-empty list of Jira usernames.")

    if fmt not in _VALID_FORMATS:
        raise ValueError(f"Invalid format {fmt!r}. Supported: {', '.join(_VALID_FORMATS)}.")

    monday, friday = _week_bounds(date_from, date_to, config.timezone)
    iso_from = monday.isoformat()
    iso_to = friday.isoformat()

    logger.info(
        "Team report: fetching worklogs for %d users (%s..%s)", len(users), iso_from, iso_to
    )

    worklogs_by_user = await _fetch_all_users(client, config, users, iso_from, iso_to)

    # Resolve issue titles (Jira summaries for unknown keys).
    issue_titles = await _resolve_issue_titles_async(worklogs_by_user, config, client)

    # Apply section_map override by cloning config (frozen model).
    effective_config = config
    if section_map:
        effective_config = config.model_copy(update={"section_map": section_map})

    # Build ordered (username, display_name) list — display name = username
    # for now; a future enhancement can resolve real display names via Jira.
    user_order: list[tuple[str, str]] = [(u, u) for u in users]

    all_worklogs: list[dict[str, Any]] = []
    for u in users:
        all_worklogs.extend(worklogs_by_user.get(u, []))

    # Render based on format.
    if fmt == "md":
        report_text = _render_team_md(
            worklogs_by_user, effective_config, monday, friday, issue_titles, user_order
        )
    elif fmt == "json":
        report_text = _render_team_json(
            worklogs_by_user, effective_config, monday, friday, issue_titles, user_order
        )
    else:
        # txt: use the template system (backward compatible).
        if template is None:
            if registry is not None:
                template = registry.get("team_report")
            if template is None:
                from .templates.builtin.team_report import TeamReportTemplate

                template = TeamReportTemplate()

        report_text = template.render(
            all_worklogs,
            effective_config,
            monday=monday,
            friday=friday,
            issue_titles=issue_titles,
            users=user_order,
            per_user_worklogs=worklogs_by_user,
        )

    # --- Output path ---
    if output_dir is None:
        base = config.team_output_dir or str(Path.home() / ".mcp" / "jira-tempo-mcp" / "reports")
        output_dir = Path(base) / str(monday.year) / month_ru(monday.month) / "team"
    output_dir.mkdir(parents=True, exist_ok=True)
    # BUG-5: include users hash to prevent silent overwrite with different user sets.
    # UX-8: ISO dates in filename for clarity across years.
    users_hash = hashlib.md5(",".join(sorted(users)).encode()).hexdigest()[:6]
    filename = f"team_{monday.isoformat()}_{friday.isoformat()}_{users_hash}.{fmt}"
    out_path = output_dir / filename
    out_path.write_text(report_text, encoding="utf-8")

    # --- Summary ---
    per_user_totals: dict[str, int] = {}
    cross_issue: dict[str, int] = defaultdict(int)
    for username in users:
        total = 0
        for wl in worklogs_by_user.get(username, []):
            secs = wl.get("timeSpentSeconds")
            if isinstance(secs, int):
                total += secs
                key = extract_issue_key(wl)
                if key:
                    cross_issue[key] += secs
        per_user_totals[username] = total
    grand_total = sum(per_user_totals.values())
    top_issues = sorted(cross_issue.items(), key=lambda kv: kv[1], reverse=True)[:5]
    empty_users = [u for u in users if per_user_totals[u] == 0]

    summary_lines = [
        f"Team report written: {out_path}",
        f"Grand total: {format_seconds_to_human(grand_total)} across {len(users)} users.",
        "Per-user totals:",
    ]
    for u in users:
        summary_lines.append(f"  - {u}: {format_seconds_to_human(per_user_totals[u])}")
    if empty_users:
        summary_lines.append(f"Users without worklogs: {', '.join(empty_users)}")
    if top_issues:
        summary_lines.append("Top issues:")
        for key, secs in top_issues:
            title = issue_titles.get(key, key)
            summary_lines.append(f"  - {key} ({title}): {format_seconds_to_human(secs)}")

    logger.info("Team report written to %s", out_path)
    return TeamReportResult(
        file_path=out_path,
        summary="\n".join(summary_lines),
        per_user_totals=per_user_totals,
    )


__all__ = [
    "RateLimitError",
    "TeamReportResult",
    "generate_team_report",
]
