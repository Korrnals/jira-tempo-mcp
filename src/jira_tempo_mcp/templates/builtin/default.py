"""Default weekly report template — mirrors the original report.py layout.

Renders worklogs grouped by issue with stable sections, non-issue sections,
and remaining issues sorted by total time descending. This is the backward-
compatible default selected when ``REPORT_TEMPLATE=default`` (or unset).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...config import Config
from ...utils import format_seconds_to_human
from .._shared import (
    extract_comment,
    extract_issue_key,
    extract_seconds,
    format_date,
    month_ru,
    week_range,
)


class DefaultTemplate:
    """Default weekly report template (issue-grouped, stable sections)."""

    name: str = "default"
    description: str = (
        "Weekly report grouped by issue with stable sections, non-issue "
        "sections, and remaining issues sorted by total time."
    )

    def render(
        self,
        worklogs: list[dict[str, Any]],
        config: Config,
        **kwargs: Any,
    ) -> str:
        """Render worklogs to the default weekly report text.

        kwargs:
            monday: optional date — the Monday of the target week. If absent,
                the week is derived from the first worklog date or today.
            friday: optional date — the Friday of the target week.
            issue_titles: optional dict[str, str] — pre-resolved issue titles.
        """
        from datetime import date

        monday = kwargs.get("monday")
        friday = kwargs.get("friday")
        if monday is None or friday is None:
            today = date.today()
            monday, friday = week_range(today)
        issue_titles: dict[str, str] = kwargs.get("issue_titles") or {}

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        total_seconds = 0
        for wl in worklogs:
            key = extract_issue_key(wl)
            if not key:
                continue
            grouped[key].append(wl)
            total_seconds += extract_seconds(wl)

        lines: list[str] = []
        author = config.report_author_header
        lines.append(
            f"[{author}] Отчет работы за неделю ({format_date(monday)} - {format_date(friday)}):"
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
                comment = extract_comment(wl)
                if comment:
                    lines.append(f"\t+ {comment}")
                else:
                    lines.append(f"\t+ {format_seconds_to_human(extract_seconds(wl))} отработано")
            lines.append("")
            used_keys.add(key)
            section_num += 1

        # 2. Non-issue sections (planerki, Jira work) — always present.
        for title in config.non_issue_sections:
            lines.append(f"{section_num}. {title}")
            lines.append("")
            section_num += 1

        # 3. Remaining project tasks, sorted by total time desc.
        remaining = [k for k in grouped if k not in used_keys]
        remaining.sort(key=lambda k: sum(extract_seconds(w) for w in grouped[k]), reverse=True)
        for key in remaining:
            title = issue_titles.get(key, key)
            lines.append(f'{section_num}. [{key}] {key} - "{title}"')
            for wl in grouped[key]:
                comment = extract_comment(wl)
                if comment:
                    lines.append(f"\t+ {comment}")
                else:
                    lines.append(f"\t+ {format_seconds_to_human(extract_seconds(wl))} отработано")
            lines.append("")
            section_num += 1

        return "\n".join(lines).rstrip() + "\n"


__all__ = ["DefaultTemplate", "month_ru"]
