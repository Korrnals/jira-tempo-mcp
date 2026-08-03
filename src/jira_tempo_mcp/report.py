"""Weekly report generator — maps Tempo worklogs to the report template.

Implements the weekly report template logic. Since v0.2.0 the rendering is
delegated to the template system (see :mod:`jira_tempo_mcp.templates`).
The default template reproduces the original layout exactly, so callers
without a ``template`` argument keep the same output.

Since v0.3.0 the ``format`` parameter selects output format:
- ``txt`` (default): plain text via the template system.
- ``md``: Markdown with tables and bold formatting.
- ``json``: structured JSON with all worklog data.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytz

from .client import JiraTempoClient, JiraTempoError
from .config import Config
from .templates import ReportTemplate, TemplateRegistry
from .templates._shared import (
    extract_comment as _extract_comment,  # noqa: F401 — re-exported for tests
)
from .templates._shared import (
    extract_issue_key as _extract_issue_key,  # noqa: F401
)
from .templates._shared import (
    extract_seconds as _extract_seconds,  # noqa: F401
)
from .templates._shared import (
    extract_worker as _extract_worker,  # noqa: F401
)
from .templates._shared import (
    format_date as _format_date,  # noqa: F401
)
from .templates._shared import (
    format_date_short as _format_date_short,  # noqa: F401
)
from .templates._shared import (
    group_worklogs_by_comment_raw,
    parse_tempo_date,
    week_range,
)
from .templates._shared import (
    md_escape_cell as _md_escape_cell,
)
from .templates._shared import (
    month_ru as _month_ru,  # noqa: F401
)
from .templates._shared import (
    render_comment_cell as _render_comment_cell,
)
from .templates._shared import (
    truncate_text as _truncate_text,
)
from .utils import format_seconds_to_human

logger = logging.getLogger(__name__)

# Backward-compatible aliases (tests import these private names).
_week_range = week_range
_format_date = _format_date
_format_date_short = _format_date_short
_month_ru = _month_ru
_parse_tempo_date = parse_tempo_date

_VALID_FORMATS = ("txt", "md", "json")


def _render_weekly_md(
    worklogs: list[dict[str, Any]],
    config: Config,
    monday: date,
    friday: date,
    issue_titles: dict[str, str],
    author: str | None = None,
) -> str:
    """Render weekly report in Markdown format — professional table-based layout.

    Single-user report: one table with all worklogs as rows, sorted by issue
    key then by seconds desc within each issue. A total row at the bottom.

    author: optional override for the report header label (e.g. when
        generating a report for a different user via ``username``).
    """
    # Collect flat worklog list with issue keys.
    flat: list[dict[str, Any]] = []
    total_seconds = 0
    for wl in worklogs:
        key = _extract_issue_key(wl)
        if not key:
            continue
        secs = _extract_seconds(wl)
        total_seconds += secs
        flat.append(wl)

    author_label = author if author else config.report_author_header

    # --- Header ---
    lines: list[str] = [
        f"# \u041e\u0442\u0447\u0451\u0442 \u0437\u0430 \u043d\u0435\u0434\u0435\u043b\u044e ({_format_date(monday)} \u2014 {_format_date(friday)})",
        "",
        f"**\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a:** {author_label}",
        f"**\u0412\u0441\u0435\u0433\u043e:** {format_seconds_to_human(total_seconds)}",
        "",
    ]

    if not flat:
        lines.append(
            "*(\u043d\u0435\u0442 \u043e\u0442\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u043d\u043e\u0433\u043e \u0432\u0440\u0435\u043c\u0435\u043d\u0438)*"
        )
        lines.append("")
        return "\n".join(lines)

    # Sort worklogs: by issue key asc, then by seconds desc within issue.
    def _sort_key(wl: dict[str, Any]) -> tuple[str, int]:
        k = _extract_issue_key(wl) or ""
        s = _extract_seconds(wl)
        return (k, -s)

    sorted_worklogs = sorted(flat, key=_sort_key)

    # --- Worklogs table ---
    lines.append(
        "| \u041a\u043b\u044e\u0447 | \u0417\u0430\u0434\u0430\u0447\u0430 | \u0427\u0430\u0441\u044b | \u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439 |"
    )
    lines.append("|------|--------|------:|-------------|")
    for wl in sorted_worklogs:
        key = _extract_issue_key(wl) or ""
        title = issue_titles.get(key, config.section_map.get(key, key))
        secs = _extract_seconds(wl)
        comment = _extract_comment(wl)
        lines.append(
            f"| {key} | {_md_escape_cell(_truncate_text(title, 50))} | "
            f"{format_seconds_to_human(secs)} | "
            f"{_render_comment_cell(comment)} |"
        )
    lines.append(f"| | | **{format_seconds_to_human(total_seconds)}** | |")
    lines.append("")
    return "\n".join(lines)


def _render_weekly_json(
    worklogs: list[dict[str, Any]],
    config: Config,
    monday: date,
    friday: date,
    issue_titles: dict[str, str],
    author: str | None = None,
) -> str:
    """Render weekly report as structured JSON.

    author: optional override for the report ``author`` field (e.g. when
        generating a report for a different user via ``username``).
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_seconds = 0
    for wl in worklogs:
        key = _extract_issue_key(wl)
        if not key:
            continue
        grouped[key].append(wl)
        total_seconds += _extract_seconds(wl)

    issues: list[dict[str, Any]] = []
    used_keys: set[str] = set()

    # 1. Stable sections in defined order.
    for key in config.stable_order:
        if key not in grouped:
            continue
        title = issue_titles.get(key, config.section_map.get(key, key))
        task_total = sum(_extract_seconds(w) for w in grouped[key])
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
        used_keys.add(key)

    # 2. Remaining issues sorted by total time desc.
    remaining = [k for k in grouped if k not in used_keys]
    remaining.sort(key=lambda k: sum(_extract_seconds(w) for w in grouped[k]), reverse=True)
    for key in remaining:
        title = issue_titles.get(key, key)
        task_total = sum(_extract_seconds(w) for w in grouped[key])
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

    data = {
        "author": author if author else config.report_author_header,
        "date_from": monday.isoformat(),
        "date_to": friday.isoformat(),
        "total_seconds": total_seconds,
        "total_human": format_seconds_to_human(total_seconds),
        "issues": issues,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


async def generate_weekly_report(
    client: JiraTempoClient,
    config: Config,
    *,
    target_date: date | None = None,
    output_dir: Path | None = None,
    author_filter: str | None = None,
    template: ReportTemplate | None = None,
    registry: TemplateRegistry | None = None,
    fmt: str = "txt",
    username: str | None = None,
) -> str:
    """Generate a weekly report file and return its path.

    target_date: any date within the target week (default: today).
    output_dir: directory to write the report file. If None, uses
                config.report_output_dir or falls back to ./reports.
    author_filter: if set, only include worklogs from this worker key.
    template: explicit template instance. If None, the template named in
              ``config.report_template`` is resolved via ``registry`` (or
              the ``default`` builtin if the registry lacks it).
              Only used when ``fmt="txt"``.
    registry: optional template registry for template name resolution.
              Only used when ``fmt="txt"``.
    fmt: output format — ``txt`` (default, uses template system),
         ``md`` (Markdown), ``json`` (structured JSON).
    username: optional Jira username to generate the report for (instead of
              ``config.jira_user``). If provided, worklogs are filtered to
              this user's worker key.
    """
    if fmt not in _VALID_FORMATS:
        raise ValueError(f"Invalid format {fmt!r}. Supported: {', '.join(_VALID_FORMATS)}.")

    tz = pytz.timezone(config.timezone)
    today = datetime.now(tz).date()
    target = target_date or today
    monday, friday = week_range(target)

    date_from = monday.isoformat()
    date_to = friday.isoformat()

    logger.info("Fetching worklogs %s .. %s", date_from, date_to)

    worker_keys: list[str] | None = None
    if author_filter:
        worker_keys = [author_filter]
    else:
        # UX-7: use username override if provided, else config.jira_user.
        target_user = username if username else config.jira_user
        wk = await client.find_worker_key(target_user)
        worker_keys = [wk]

    worklogs = await client.search_worklogs(date_from, date_to, worker_keys=worker_keys)
    logger.info("Got %d worklogs", len(worklogs))

    # Filter worklogs to the target week (Tempo may return slightly out-of-range).
    # Tempo API returns "started" field (e.g. "2026-06-08 00:00:00.000"),
    # not "startDate" — handle both for compatibility.
    filtered: list[dict[str, Any]] = []
    for wl in worklogs:
        raw_date = wl.get("started") or wl.get("startDate")
        wl_date = parse_tempo_date(raw_date)
        if wl_date is None or not (monday <= wl_date <= friday):
            continue
        filtered.append(wl)

    # Build issue summaries cache (fetch from Jira for unknown titles).
    issue_titles: dict[str, str] = {}
    seen_keys: set[str] = set()
    for wl in filtered:
        key = _extract_issue_key(wl)
        if key and key not in seen_keys:
            seen_keys.add(key)
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

    # UX-7: when a username override is provided, use it as the report
    # header author label too, so the header matches the report subject.
    # Fall back to report_author_header (not report_filename_header) to
    # preserve the existing default behaviour where the header shows the
    # configured author_display_name when no username override is given.
    header_author = username if username else config.report_author_header

    # Select rendering based on format.
    if fmt == "md":
        report_text = _render_weekly_md(
            filtered, config, monday, friday, issue_titles, author=header_author
        )
    elif fmt == "json":
        report_text = _render_weekly_json(
            filtered, config, monday, friday, issue_titles, author=header_author
        )
    else:
        # txt: use the template system (backward compatible).
        if template is None:
            if registry is not None:
                template = registry.get(config.report_template)
            if template is None:
                from .templates.builtin.default import DefaultTemplate

                template = DefaultTemplate()

        report_text = template.render(
            filtered,
            config,
            monday=monday,
            friday=friday,
            issue_titles=issue_titles,
            author=header_author,
        )

    # --- Determine output path ---
    if output_dir is None:
        base = config.report_output_dir or str(Path.home() / ".mcp" / "jira-tempo-mcp" / "reports")
        output_dir = Path(base) / str(monday.year) / _month_ru(monday.month) / "weekly"
    output_dir.mkdir(parents=True, exist_ok=True)

    # UX-8: ISO dates in filename for clarity across years.
    # UX-7: when a username override is provided, use it as the filename
    # prefix instead of config.jira_user so the file is named after the
    # report subject, not the PAT owner.
    filename_prefix = username if username else config.report_filename_header
    filename = f"{filename_prefix}_{monday.isoformat()}_{friday.isoformat()}.{fmt}"
    out_path = output_dir / filename
    out_path.write_text(report_text, encoding="utf-8")
    total_seconds = sum(_extract_seconds(w) for w in filtered)
    logger.info("Report written to %s (%d seconds total, fmt=%s)", out_path, total_seconds, fmt)
    return str(out_path)


__all__ = [
    "generate_weekly_report",
    # Backward-compatible private helpers re-exported for tests.
    "_extract_comment",
    "_extract_issue_key",
    "_extract_seconds",
    "_extract_worker",
    "_format_date",
    "_format_date_short",
    "_month_ru",
    "_parse_tempo_date",
    "_week_range",
]
