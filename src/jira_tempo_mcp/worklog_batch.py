"""Batch worklog creation (P7, backlog wave 2026-10-30).

Contract (ArchComm backlog conditions + owner directive 2026-10-31):

1. ALL entries are validated BEFORE the first write — an invalid input
   raises one aggregated ValueError and NOTHING is written (not even a
   worker-key lookup happens before validation passes);
2. valid entries are written SEQUENTIALLY with NO auto-retries —
   ``POST /worklogs`` is not idempotent, a retry could duplicate hours;
3. one entry's failure does NOT stop the batch — each entry gets a
   per-entry ok(id) / error(reason) result and the response ends with a
   written/failed summary, rendered human-readable.

Pure validation/rendering lives here; the network loop stays in the
server handler (same split as week_status / worklog_aggregates).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pytz

from .utils import (
    format_seconds_to_human,
    parse_duration_to_seconds,
    parse_iso_datetime,
    validate_issue_key,
)

MAX_BATCH_ENTRIES = 20


@dataclass(frozen=True)
class ValidatedEntry:
    """One batch entry after full local validation (ready to POST)."""

    issue_key: str
    seconds: int
    comment: str
    date_started: str  # normalized YYYY-MM-DD (Tempo date field)


@dataclass(frozen=True)
class BatchEntryResult:
    """Per-entry outcome for the batch response."""

    index: int  # 1-based position in the request
    issue_key: str
    hours: str
    date_started: str
    ok: bool
    worklog_id: str | None = None
    error: str | None = None


def _normalize_date_started(raw: Any, timezone: str) -> str:
    """Normalize date_started to the YYYY-MM-DD Tempo wants.

    Same tolerance as the single create_worklog: full ISO datetimes
    (``+0300`` without colon, trailing ``Z``, microseconds) are accepted
    and reduced to their date part. Empty/None → today in ``timezone``.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return datetime.now(pytz.timezone(timezone)).date().isoformat()
    if not isinstance(raw, str):
        raise ValueError(
            f"date_started must be an ISO string (YYYY-MM-DD or full ISO datetime); "
            f"got {type(raw).__name__}."
        )
    if "T" in raw:
        return parse_iso_datetime(raw).strftime("%Y-%m-%d")
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValueError(
            f"Invalid date_started: {raw!r}. Expected ISO format YYYY-MM-DD or a full ISO datetime."
        ) from None


def validate_batch_entries(entries: Any, *, timezone: str) -> list[ValidatedEntry]:
    """Validate the whole batch BEFORE any write. All problems are reported.

    Raises :class:`ValueError` listing EVERY offending entry (index,
    field, reason) if: ``entries`` is not a non-empty list, exceeds
    ``MAX_BATCH_ENTRIES``, or any entry fails key/duration/date/comment
    validation. The caller must not touch the network on failure.
    """
    if not isinstance(entries, list) or isinstance(entries, str):
        raise ValueError(
            "'entries' must be an array of worklog objects "
            "{issue_key, time_spent, comment?, date_started?}."
        )
    if not entries:
        raise ValueError("'entries' must contain at least one worklog entry.")
    if len(entries) > MAX_BATCH_ENTRIES:
        raise ValueError(
            f"Too many entries: {len(entries)} > {MAX_BATCH_ENTRIES}. "
            "Nothing was written — split the batch into several calls."
        )

    problems: list[str] = []
    validated: list[ValidatedEntry] = []
    for idx, entry in enumerate(entries, start=1):
        label = f"entries[{idx}]"
        if not isinstance(entry, dict):
            problems.append(f"{label}: expected an object, got {type(entry).__name__}.")
            continue

        issue_key = entry.get("issue_key")
        if not isinstance(issue_key, str) or not issue_key.strip():
            problems.append(f"{label}: 'issue_key' is required (non-empty string).")
        else:
            try:
                issue_key = validate_issue_key(issue_key)
            except ValueError as exc:
                problems.append(f"{label}: {exc}")
                issue_key = None

        time_spent = entry.get("time_spent")
        seconds = 0
        if not isinstance(time_spent, str) or not time_spent.strip():
            problems.append(f"{label}: 'time_spent' is required (Tempo format, e.g. '1h 30m').")
        else:
            try:
                seconds = parse_duration_to_seconds(time_spent)
                if seconds <= 0:
                    raise ValueError("'time_spent' must be greater than zero.")
            except ValueError as exc:
                problems.append(f"{label}: invalid time_spent {time_spent!r}: {exc}")
                seconds = 0

        comment = entry.get("comment", "")
        if comment is None:
            comment = ""
        if not isinstance(comment, str):
            problems.append(f"{label}: 'comment' must be a string.")
            comment = ""

        try:
            date_started = _normalize_date_started(entry.get("date_started"), timezone)
        except ValueError as exc:
            problems.append(f"{label}: {exc}")
            date_started = ""

        if issue_key is not None and seconds > 0 and date_started:
            validated.append(
                ValidatedEntry(
                    issue_key=issue_key,
                    seconds=seconds,
                    comment=comment,
                    date_started=date_started,
                )
            )

    if problems:
        raise ValueError(
            f"Batch rejected — {len(problems)} invalid entrie(s), nothing was written:\n- "
            + "\n- ".join(problems)
        )
    return validated


def render_batch_results(results: list[BatchEntryResult]) -> str:
    """Render the human-readable per-entry batch response with a summary."""
    recorded = sum(1 for r in results if r.ok)
    failed = len(results) - recorded
    lines = [f"Batch result: {recorded} recorded, {failed} failed (of {len(results)} entries)."]
    for r in results:
        entry = f"{r.issue_key} — {r.hours} on {r.date_started}"
        if r.ok:
            lines.append(f"- [{r.index}] OK {entry} — Worklog ID: {r.worklog_id}")
        else:
            lines.append(f"- [{r.index}] FAILED {entry} — {r.error}")
    return "\n".join(lines)


__all__ = [
    "MAX_BATCH_ENTRIES",
    "BatchEntryResult",
    "ValidatedEntry",
    "render_batch_results",
    "validate_batch_entries",
    # re-exported for the handler's convenience
    "format_seconds_to_human",
]
