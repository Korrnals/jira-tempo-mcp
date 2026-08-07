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


def iso_now(timezone: str) -> str:
    """Return current ISO 8601 datetime string with timezone offset."""
    tz = pytz.timezone(timezone)
    return datetime.now(tz).isoformat(timespec="seconds")
