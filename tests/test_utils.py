"""Unit tests for pure utility functions in jira_tempo_mcp.utils."""

from __future__ import annotations

import pytest

from jira_tempo_mcp.utils import format_seconds_to_human, parse_duration_to_seconds

# --- parse_duration_to_seconds ---

class TestParseDuration:
    """Tests for parse_duration_to_seconds."""

    def test_hours_only(self) -> None:
        assert parse_duration_to_seconds("2h") == 7200

    def test_minutes_only(self) -> None:
        assert parse_duration_to_seconds("45m") == 2700

    def test_hours_and_minutes(self) -> None:
        assert parse_duration_to_seconds("1h 30m") == 5400

    def test_days(self) -> None:
        # 1d = 8h = 28800s
        assert parse_duration_to_seconds("1d") == 28800

    def test_weeks(self) -> None:
        # 1w = 5d = 40h = 144000s
        assert parse_duration_to_seconds("1w") == 144000

    def test_complex(self) -> None:
        # 1d 2h 30m = 28800 + 7200 + 1800 = 37800
        assert parse_duration_to_seconds("1d 2h 30m") == 37800

    def test_case_insensitive(self) -> None:
        assert parse_duration_to_seconds("2H 30M") == 9000

    def test_whitespace_tolerant(self) -> None:
        assert parse_duration_to_seconds("  2h   30m  ") == 9000

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not parse duration"):
            parse_duration_to_seconds("")

    def test_no_units_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not parse duration"):
            parse_duration_to_seconds("just some text")

    def test_invalid_unit_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not parse duration"):
            parse_duration_to_seconds("5x")

    def test_zero(self) -> None:
        assert parse_duration_to_seconds("0h") == 0

    def test_zero_minutes(self) -> None:
        assert parse_duration_to_seconds("0m") == 0


# --- format_seconds_to_human ---

class TestFormatSeconds:
    """Tests for format_seconds_to_human."""

    def test_zero(self) -> None:
        assert format_seconds_to_human(0) == "0h"

    def test_negative(self) -> None:
        assert format_seconds_to_human(-100) == "0h"

    def test_one_hour(self) -> None:
        assert format_seconds_to_human(3600) == "1h"

    def test_one_hour_thirty_min(self) -> None:
        assert format_seconds_to_human(5400) == "1h 30m"

    def test_minutes_only(self) -> None:
        assert format_seconds_to_human(1800) == "30m"

    def test_two_hours(self) -> None:
        assert format_seconds_to_human(7200) == "2h"

    def test_seconds_truncated(self) -> None:
        # 3661s = 1h 1m 1s -> "1h 1m" (seconds dropped)
        assert format_seconds_to_human(3661) == "1h 1m"

    def test_large_value(self) -> None:
        # 40h = 144000s
        assert format_seconds_to_human(144000) == "40h"
