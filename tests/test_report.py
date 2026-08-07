"""Unit tests for report.py pure functions (date helpers, extraction)."""

from __future__ import annotations

from datetime import date

from jira_tempo_mcp.report import (
    _extract_comment,
    _extract_issue_key,
    _extract_seconds,
    _extract_worker,
    _format_date,
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


# --- _format_date ---


class TestFormatDate:
    def test_format_date(self) -> None:
        assert _format_date(date(2026, 6, 15)) == "15.06.2026"


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


# --- Weekly MD / JSON comment rendering (hotfix regression) ---


class TestWeeklyMdJsonComments:
    """Weekly MD cells stay table-safe; JSON preserves raw comment structure."""

    @staticmethod
    def _config() -> object:
        from jira_tempo_mcp.config import Config

        return Config(
            jira_base_url="https://jira.test.example",
            jira_user="testuser",
            jira_pat="fake-pat",
            section_map={"PROJECT-100": "Section A"},
            stable_order=["PROJECT-100"],
            non_issue_sections=[],
        )

    def test_md_multiline_comment_cell_is_table_safe(self) -> None:
        from jira_tempo_mcp.report import _render_weekly_md

        config = self._config()
        worklogs = [
            {
                "issueKey": "PROJECT-100",
                "timeSpentSeconds": 7200,
                "comment": "+ разработка\n+ корректировка",
            }
        ]
        md = _render_weekly_md(
            worklogs, config, date(2026, 6, 15), date(2026, 6, 19), {"PROJECT-100": "Section A"}
        )
        # Locate the worklog row (the line that has the issue key + a bullet).
        rows = [ln for ln in md.splitlines() if ln.startswith("| PROJECT-100 |")]
        assert rows, "expected a worklog row"
        row = rows[0]
        # Every table row has exactly the right number of pipe-delimited cells.
        assert row.count("|") == 5
        # No raw newline leaked into the cell, multi-action uses <br>.
        assert "<br>" in row
        # No double marker.
        assert "+ +" not in row

    def test_json_preserves_raw_multiline_comment(self) -> None:
        import json as _json

        from jira_tempo_mcp.report import _render_weekly_json

        config = self._config()
        multiline = "+ разработка\n+ корректировка"
        worklogs = [
            {"issueKey": "PROJECT-100", "timeSpentSeconds": 3600, "comment": multiline},
            {"issueKey": "PROJECT-100", "timeSpentSeconds": 7200, "comment": multiline},
        ]
        out = _render_weekly_json(
            worklogs, config, date(2026, 6, 15), date(2026, 6, 19), {"PROJECT-100": "Section A"}
        )
        data = _json.loads(out)
        issue = data["issues"][0]
        # Grouping + summation intact.
        assert len(issue["worklogs"]) == 1
        entry = issue["worklogs"][0]
        assert entry["seconds"] == 10800
        # Raw comment round-trips faithfully (newline structure preserved).
        assert entry["comment"] == multiline
        assert "\n" in entry["comment"]
