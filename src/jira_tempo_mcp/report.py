"""Weekly report generator — maps Tempo worklogs to the report template.

Implements the logic described in
./work/example-org/reports/2026/README.md

Section mapping, stable order, and non-issue sections are loaded from Config
(overridable via env vars — see config.py).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytz

from .client import JiraTempoClient, JiraTempoError
from .config import Config
from .utils import format_seconds_to_human

logger = logging.getLogger(__name__)


def _week_range(target: date) -> tuple[date, date]:
    """Return (monday, friday) of the ISO week containing target."""
    monday = target - timedelta(days=target.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def _format_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _format_date_short(d: date) -> str:
    """DDMMYY for filename."""
    return d.strftime("%d%m%y")


def _parse_tempo_date(raw: str | None) -> date | None:
    """Parse Tempo startDate (ISO 8601) to a date object."""
    if not raw:
        return None
    try:
        # Tempo returns e.g. "2026-06-19" or "2026-06-19T10:00:00.000+0300"
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _extract_comment(worklog: dict[str, Any]) -> str:
    """Extract the comment text from a Tempo worklog object."""
    comment = worklog.get("comment")
    if isinstance(comment, str):
        return comment.strip()
    if isinstance(comment, dict):
        # Tempo sometimes nests comment as {content: "..."}
        return str(comment.get("content", "")).strip()
    return ""


def _extract_issue_key(worklog: dict[str, Any]) -> str | None:
    """Extract issue key from a Tempo worklog object."""
    # Tempo 4 API uses issueKey at top level, or issue.key
    key = worklog.get("issueKey")
    if key:
        return str(key)
    issue = worklog.get("issue")
    if isinstance(issue, dict):
        k = issue.get("key")
        if k:
            return str(k)
    return None


def _extract_seconds(worklog: dict[str, Any]) -> int:
    """Extract time spent in seconds from a Tempo worklog object."""
    seconds = worklog.get("timeSpentSeconds")
    if isinstance(seconds, int):
        return seconds
    return 0


def _extract_worker(worklog: dict[str, Any]) -> str | None:
    """Extract worker/author key from a Tempo worklog object."""
    worker = worklog.get("authorAccountId") or worklog.get("workerKey")
    if worker:
        return str(worker)
    author = worklog.get("author")
    if isinstance(author, dict):
        key = author.get("key") or author.get("accountId")
        if key:
            return str(key)
    return None


async def generate_weekly_report(
    client: JiraTempoClient,
    config: Config,
    *,
    target_date: date | None = None,
    output_dir: Path | None = None,
    author_filter: str | None = None,
) -> str:
    """Generate a weekly report file and return its path.

    target_date: any date within the target week (default: today).
    output_dir: directory to write the report file. If None, uses
                config.report_output_dir or falls back to ./reports.
    author_filter: if set, only include worklogs from this worker key.
    """
    tz = pytz.timezone(config.timezone)
    today = datetime.now(tz).date()
    target = target_date or today
    monday, friday = _week_range(target)

    date_from = monday.isoformat()
    date_to = friday.isoformat()

    logger.info("Fetching worklogs %s .. %s", date_from, date_to)

    # Determine worker key for filtering.
    worker_keys: list[str] | None = None
    if author_filter:
        worker_keys = [author_filter]
    else:
        wk = await client.find_worker_key(config.jira_user)
        worker_keys = [wk]

    worklogs = await client.search_worklogs(date_from, date_to, worker_keys=worker_keys)
    logger.info("Got %d worklogs", len(worklogs))

    # Group worklogs by issue key, collect comments.
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_seconds = 0
    for wl in worklogs:
        key = _extract_issue_key(wl)
        if not key:
            continue
        wl_date = _parse_tempo_date(wl.get("startDate"))
        if wl_date is None or not (monday <= wl_date <= friday):
            continue
        grouped[key].append(wl)
        total_seconds += _extract_seconds(wl)

    # Build issue summaries cache (fetch from Jira for unknown titles).
    issue_titles: dict[str, str] = {}
    for key in grouped:
        if key in config.section_map:
            issue_titles[key] = config.section_map[key]
        else:
            try:
                issue = await client.get_issue(key)
                fields = issue.get("fields", {})
                issue_titles[key] = (
                    str(fields.get("summary", key)) if isinstance(fields, dict) else key
                )
            except JiraTempoError:
                logger.warning("Could not fetch issue %s, using key as title", key)
                issue_titles[key] = key

    # --- Compose report lines ---
    lines: list[str] = []
    author = config.report_author_header
    lines.append(
        f"[{author}] Отчет работы за неделю ({_format_date(monday)} - {_format_date(friday)}):"
    )
    lines.append("")

    section_num = 1
    used_keys: set[str] = set()

    # 1. Stable sections in defined order.
    for key in config.stable_order:
        if key not in grouped:
            continue
        title = issue_titles.get(key, config.section_map.get(key, key))
        lines.append(f"{section_num}. {title} [{key}]")
        for wl in grouped[key]:
            comment = _extract_comment(wl)
            if comment:
                lines.append(f"\t+ {comment}")
            else:
                lines.append(f"\t+ {format_seconds_to_human(_extract_seconds(wl))} отработано")
        lines.append("")
        used_keys.add(key)
        section_num += 1

    # 2. Non-issue sections (planerki, Jira work) — always present.
    for title in config.non_issue_sections:
        lines.append(f"{section_num}. {title}")
        lines.append("")
        section_num += 1

    # 3. Remaining project tasks (not in stable sections), sorted by total time desc.
    remaining = [k for k in grouped if k not in used_keys]
    # Sort by total seconds descending.
    remaining.sort(key=lambda k: sum(_extract_seconds(w) for w in grouped[k]), reverse=True)

    for key in remaining:
        title = issue_titles.get(key, key)
        lines.append(f'{section_num}. [{key}] {key} - "{title}"')
        for wl in grouped[key]:
            comment = _extract_comment(wl)
            if comment:
                lines.append(f"\t+ {comment}")
            else:
                lines.append(f"\t+ {format_seconds_to_human(_extract_seconds(wl))} отработано")
        lines.append("")
        section_num += 1

    report_text = "\n".join(lines).rstrip() + "\n"

    # --- Determine output path ---
    if output_dir is None:
        # M3: use config.report_output_dir, fall back to ./reports
        base = config.report_output_dir or str(Path.cwd() / "reports")
        month_ru = _month_ru(monday.month)
        output_dir = Path(base) / str(monday.year) / month_ru
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"your-username_{_format_date_short(monday)}-{_format_date_short(friday)}.txt"
    out_path = output_dir / filename
    out_path.write_text(report_text, encoding="utf-8")
    logger.info("Report written to %s (%d seconds total)", out_path, total_seconds)
    return str(out_path)


def _month_ru(month: int) -> str:
    """Map month number to Russian lowercase month name (for folder name)."""
    names = [
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    ]
    return names[month - 1]
