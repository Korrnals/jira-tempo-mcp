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
    """Parse a human duration string like '1h 30m', '2h', '45m', '1d 2h' to seconds.

    Supports: w (weeks=5d), d (days=8h), h (hours), m (minutes).
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
