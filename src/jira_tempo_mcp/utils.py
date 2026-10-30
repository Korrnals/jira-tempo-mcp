"""Pure utility functions — duration parsing, formatting, timezone helpers.

Separated from client.py so they can be unit-tested without HTTP mocks.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytz

_UNITS: dict[str, int] = {"w": 5 * 8 * 3600, "d": 8 * 3600, "h": 3600, "m": 60}
_DURATION_RE = re.compile(r"(\d+)\s*([wdhm])")


def parse_duration_to_seconds(time_spent: str) -> int:
    """Parse a human duration string to whole seconds.

    Supported units (work-time semantics, not calendar time):

    ===========  ===========  =========================
    Unit         Meaning      Example
    ===========  ===========  =========================
    ``w``        week (5d)    ``1w``  = 5 × 8h
    ``d``        day (8h)     ``1d``  = 8h
    ``h``        hour         ``1h``  = 3600s
    ``m``        minute       ``45m`` = 2700s
    ===========  ===========  =========================

    Accepted formats (tokens may be space- or glue-separated, any order):

    - ``1h``              → 3600
    - ``1h 30m``          → 5400
    - ``1h30m``           → 5400
    - ``1d 2h``           → 36000
    - ``2w``              → 288000
    - ``45m``             → 2700

    Constraints:

    - Only **integers** are parsed. ``1.5h`` is *not* accepted (the regex
      matches ``\\d+`` before each unit, so ``1.5`` parses as ``1`` and ``.5``
      is left unmatched, yielding ``3600`` — pass integers only).
    - No negative durations.
    - Case-insensitive.
    - A string with no valid token (e.g. ``"foo"``) raises ``ValueError``.

    Raises ValueError if the string contains no valid duration tokens.
    """
    total = 0
    matched = False
    for match in _DURATION_RE.finditer(time_spent.lower().strip()):
        matched = True
        value, unit = int(match.group(1)), match.group(2)
        total += value * _UNITS[unit]
    if not matched:
        raise ValueError(f"Could not parse duration: {time_spent!r}")
    return total


def format_seconds_to_human(seconds: int) -> str:
    """Format seconds as '1h 30m' style string."""
    if seconds <= 0:
        return "0h"
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0h"


# Regex for validating Jira issue keys (m10). Shared by the single
# create_worklog and the batch create_worklogs (P7) — one source of truth.
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def validate_issue_key(key: str) -> str:
    """Validate Jira issue key format. Raises ValueError if invalid."""
    if not ISSUE_KEY_RE.match(key):
        raise ValueError(
            f"Invalid issue key {key!r}. Expected format: PROJECT-NUMBER (e.g. PROJECT-100)."
        )
    return key


# Matches a numeric timezone offset WITHOUT a colon at end of string,
# e.g. "...+0300" or "...-0500". Used to normalise such offsets so that
# datetime.fromisoformat accepts them (it requires "+03:00").
_TZ_OFFSET_NO_COLON_RE = re.compile(r"([+-]\d{2})(\d{2})$")


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime tolerantly.

    Handles variants that ``datetime.fromisoformat`` rejects on Python 3.11:
    a numeric offset without a colon (``+0300``) and a trailing ``Z``.
    Microseconds (``.000``) are already accepted on 3.11+.

    Raises :class:`ValueError` with an actionable message if the value
    cannot be parsed by any known shape.
    """
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    # Insert the colon a numeric offset lacks: "+0300" -> "+03:00".
    normalized = _TZ_OFFSET_NO_COLON_RE.sub(r"\1:\2", normalized)
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Could not parse date_started {value!r}: expected ISO-8601 "
            f"(e.g. '2026-06-19T10:00:00+03:00'). Details: {exc}"
        ) from exc


def iso_now(timezone: str) -> str:
    """Return current ISO 8601 datetime string with timezone offset."""
    tz = pytz.timezone(timezone)
    return datetime.now(tz).isoformat(timespec="seconds")
