"""Unit tests for report.py pure functions (date helpers, extraction)."""

from __future__ import annotations

from datetime import date

from jira_tempo_mcp.report import (
    _extract_comment,
    _extract_issue_key,
    _extract_seconds,
    _extract_worker,
    _format_date,
    _format_date_short,
    _month_ru,
    _parse_tempo_date,
    _week_range,
)

# --- _week_range ---


class TestWeekRange:
    """Tests for _week_range."""

    def test_monday(self) -> None:
        monday, friday = _week_range(date(2026, 6, 15))  # Mon
        assert monday == date(2026, 6, 15)
        assert friday == date(2026, 6, 19)

    def test_wednesday(self) -> None:
        monday, friday = _week_range(date(2026, 6, 17))  # Wed
        assert monday == date(2026, 6, 15)
        assert friday == date(2026, 6, 19)

    def test_friday(self) -> None:
        monday, friday = _week_range(date(2026, 6, 19))  # Fri
        assert monday == date(2026, 6, 15)
        assert friday == date(2026, 6, 19)

    def test_sunday(self) -> None:
        monday, friday = _week_range(date(2026, 6, 21))  # Sun
        assert monday == date(2026, 6, 15)
        assert friday == date(2026, 6, 19)

    def test_month_boundary(self) -> None:
        # June 30 2026 is a Tuesday; week spans Jun 29 - Jul 3
        monday, friday = _week_range(date(2026, 6, 30))
        assert monday == date(2026, 6, 29)
        assert friday == date(2026, 7, 3)

    def test_year_boundary(self) -> None:
        # Dec 31 2026 is a Thursday; week spans Dec 28 - Jan 1 2027
        monday, friday = _week_range(date(2026, 12, 31))
        assert monday == date(2026, 12, 28)
        assert friday == date(2027, 1, 1)


# --- _format_date / _format_date_short ---


class TestFormatDate:
    def test_format_date(self) -> None:
        assert _format_date(date(2026, 6, 15)) == "15.06.2026"

    def test_format_date_short(self) -> None:
        assert _format_date_short(date(2026, 6, 15)) == "150626"

    def test_format_date_short_single_digit(self) -> None:
        assert _format_date_short(date(2026, 1, 5)) == "050126"


# --- _month_ru ---


class TestMonthRu:
    def test_january(self) -> None:
        assert _month_ru(1) == "январь"

    def test_june(self) -> None:
        assert _month_ru(6) == "июнь"

    def test_december(self) -> None:
        assert _month_ru(12) == "декабрь"


# --- _parse_tempo_date ---


class TestParseTempoDate:
    def test_date_only(self) -> None:
        assert _parse_tempo_date("2026-06-19") == date(2026, 6, 19)

    def test_datetime_with_tz(self) -> None:
        assert _parse_tempo_date("2026-06-19T10:00:00.000+0300") == date(2026, 6, 19)

    def test_datetime_utc(self) -> None:
        assert _parse_tempo_date("2026-06-19T10:00:00Z") == date(2026, 6, 19)

    def test_none(self) -> None:
        assert _parse_tempo_date(None) is None

    def test_empty_string(self) -> None:
        assert _parse_tempo_date("") is None

    def test_invalid_string(self) -> None:
        assert _parse_tempo_date("not-a-date") is None

    def test_garbage(self) -> None:
        assert _parse_tempo_date("garbage123") is None


# --- _extract_* ---


class TestExtractFunctions:
    def test_extract_issue_key_top_level(self) -> None:
        assert _extract_issue_key({"issueKey": "PROJECT-100"}) == "PROJECT-100"

    def test_extract_issue_key_nested(self) -> None:
        wl = {"issue": {"key": "PROJECT-100"}}
        assert _extract_issue_key(wl) == "PROJECT-100"

    def test_extract_issue_key_missing(self) -> None:
        assert _extract_issue_key({"foo": "bar"}) is None

    def test_extract_seconds_int(self) -> None:
        assert _extract_seconds({"timeSpentSeconds": 3600}) == 3600

    def test_extract_seconds_missing(self) -> None:
        assert _extract_seconds({"foo": "bar"}) == 0

    def test_extract_seconds_non_int(self) -> None:
        assert _extract_seconds({"timeSpentSeconds": "3600"}) == 0

    def test_extract_comment_string(self) -> None:
        assert _extract_comment({"comment": "did stuff"}) == "did stuff"

    def test_extract_comment_dict(self) -> None:
        assert _extract_comment({"comment": {"content": "nested"}}) == "nested"

    def test_extract_comment_missing(self) -> None:
        assert _extract_comment({"foo": "bar"}) == ""

    def test_extract_worker_top_level(self) -> None:
        assert _extract_worker({"authorAccountId": "abc123"}) == "abc123"

    def test_extract_worker_nested(self) -> None:
        assert _extract_worker({"author": {"key": "user1"}}) == "user1"

    def test_extract_worker_missing(self) -> None:
        assert _extract_worker({"foo": "bar"}) is None
