"""Weekly report generator — maps Tempo worklogs to the report template.

Implements the weekly report template logic. Since v0.2.0 the rendering is
delegated to the template system (see :mod:`jira_tempo_mcp.templates`).
The default template reproduces the original layout exactly, so callers
without a ``template`` argument keep the same output.
"""

from __future__ import annotations

import logging
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
    month_ru as _month_ru,  # noqa: F401
)
from .templates._shared import (
    parse_tempo_date,
    week_range,
)

logger = logging.getLogger(__name__)

# Backward-compatible aliases (tests import these private names).
_week_range = week_range
_format_date = _format_date
_format_date_short = _format_date_short
_month_ru = _month_ru
_parse_tempo_date = parse_tempo_date


async def generate_weekly_report(
    client: JiraTempoClient,
    config: Config,
    *,
    target_date: date | None = None,
    output_dir: Path | None = None,
    author_filter: str | None = None,
    template: ReportTemplate | None = None,
    registry: TemplateRegistry | None = None,
) -> str:
    """Generate a weekly report file and return its path.

    target_date: any date within the target week (default: today).
    output_dir: directory to write the report file. If None, uses
                config.report_output_dir or falls back to ./reports.
    author_filter: if set, only include worklogs from this worker key.
    template: explicit template instance. If None, the template named in
              ``config.report_template`` is resolved via ``registry`` (or
              the ``default`` builtin if the registry lacks it).
    registry: optional template registry for template name resolution.
    """
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
        wk = await client.find_worker_key(config.jira_user)
        worker_keys = [wk]

    worklogs = await client.search_worklogs(date_from, date_to, worker_keys=worker_keys)
    logger.info("Got %d worklogs", len(worklogs))

    # Filter worklogs to the target week (Tempo may return slightly out-of-range).
    filtered: list[dict[str, Any]] = []
    for wl in worklogs:
        wl_date = parse_tempo_date(wl.get("startDate"))
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

    # Select template.
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
    )

    # --- Determine output path ---
    if output_dir is None:
        base = config.report_output_dir or str(Path.cwd() / "reports")
        output_dir = Path(base) / str(monday.year) / _month_ru(monday.month)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = (
        f"{config.report_filename_header}_"
        f"{_format_date_short(monday)}-{_format_date_short(friday)}.txt"
    )
    out_path = output_dir / filename
    out_path.write_text(report_text, encoding="utf-8")
    total_seconds = sum(_extract_seconds(w) for w in filtered)
    logger.info("Report written to %s (%d seconds total)", out_path, total_seconds)
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
