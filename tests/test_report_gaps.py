"""P8 (backlog wave 2026-10-30): report_gaps — read-only report gap finder.

Contract:
- weeks (ISO, Mon–Fri render window / Mon–Sun data window) since ``since``
  (default: Jan 1st of the current year; look-back capped at 26 weeks,
  older values clamped and disclosed) in which the user tracked hours > 0
  are checked against report files (recursive ``*_<monday>_<friday>.*``
  glob under the report output root);
- response: per-week covered/missing + hours, then a summary line;
- strictly read-only: only the two Tempo reads (worker key + one search)
  and Path.rglob inside the root; no writes anywhere.

Offline: fully mocked client + tmp_path fixtures, no HTTP, no .env reads.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.report_gaps import (
    GAP_WINDOW_WEEKS,
    build_week_gaps,
    find_report_file,
    group_hours_by_week,
    render_week_gaps,
    resolve_since,
)
from jira_tempo_mcp.server import TOOLS, _handle_report_gaps

TODAY = date(2026, 10, 28)  # Wednesday


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "timezone": "Europe/Moscow",
    }
    defaults.update(overrides)
    return Config(**defaults)


def _wl(started: str, seconds: int, key: str = "PROJECT-100") -> dict[str, Any]:
    return {
        "issueKey": key,
        "timeSpentSeconds": seconds,
        "started": started,
        "authorAccountId": "wk-testuser",
    }


def _mock_client(worklogs: list[dict[str, Any]]) -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "wk-testuser"
    mock.search_worklogs.return_value = worklogs
    return mock


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _write_report(root: Any, monday: date, friday: date, prefix: str = "testuser") -> None:
    sub = root / str(monday.year) / "06-June" / "weekly"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / f"{prefix}_{monday.isoformat()}_{friday.isoformat()}.txt").write_text(
        "report", encoding="utf-8"
    )


# --- resolve_since -------------------------------------------------------------


class TestResolveSince:
    def test_default_is_jan_first(self) -> None:
        # Mid-June: Jan 1st is ~24 weeks back — inside the 26-week cap.
        mid_june = date(2026, 6, 17)
        since, clamped = resolve_since(None, today=mid_june)
        assert since == date(2026, 1, 1)
        assert clamped is False

    def test_default_clamped_late_in_year(self) -> None:
        # In late October Jan 1st is ~43 weeks back — the default itself
        # must be clamped to the 26-week boundary.
        late = date(2026, 10, 28)
        since, clamped = resolve_since(None, today=late)
        assert since == late - timedelta(weeks=GAP_WINDOW_WEEKS)
        assert clamped is True

    def test_explicit_since(self) -> None:
        since, clamped = resolve_since("2026-06-01", today=TODAY)
        assert since == date(2026, 6, 1)
        assert clamped is False

    def test_old_since_clamped_to_26_weeks(self) -> None:
        floor = TODAY - timedelta(weeks=GAP_WINDOW_WEEKS)
        since, clamped = resolve_since("2020-01-01", today=TODAY)
        assert since == floor
        assert clamped is True

    def test_future_since_raises(self) -> None:
        with pytest.raises(ValueError, match="in the future"):
            resolve_since("2027-01-01", today=TODAY)

    def test_bad_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid since"):
            resolve_since("01.06.2026", today=TODAY)

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="must be an ISO date string"):
            resolve_since(20260101, today=TODAY)


# --- group_hours_by_week --------------------------------------------------------


class TestGroupHoursByWeek:
    def test_weekend_entries_count_toward_their_week(self) -> None:
        # Week Mon 2026-06-15 .. Sun 2026-06-21.
        worklogs = [
            _wl("2026-06-15", 4 * 3600),
            _wl("2026-06-20", 2 * 3600),  # Saturday — same Mon–Sun window
        ]
        per_week = group_hours_by_week(
            worklogs, window_start=date(2026, 6, 15), window_end=date(2026, 6, 21)
        )
        assert per_week == {date(2026, 6, 15): 6 * 3600}

    def test_zero_and_unparseable_excluded(self) -> None:
        # Week of 2026-06-22 (Mon): zero-hour and garbage entries dropped,
        # the valid entry grouped under ITS week's Monday.
        worklogs = [
            _wl("2026-06-23", 0),
            _wl("garbage", 3600),
            _wl("2026-06-24", 3600),
        ]
        per_week = group_hours_by_week(
            worklogs, window_start=date(2026, 6, 22), window_end=date(2026, 6, 28)
        )
        assert per_week == {date(2026, 6, 22): 3600}

    def test_outside_window_excluded(self) -> None:
        worklogs = [_wl("2026-01-05", 3600)]
        per_week = group_hours_by_week(
            worklogs, window_start=date(2026, 6, 15), window_end=date(2026, 6, 21)
        )
        assert per_week == {}


# --- find_report_file ------------------------------------------------------------


class TestFindReportFile:
    def test_finds_recursive_match(self, tmp_path: Any) -> None:
        monday, friday = date(2026, 6, 15), date(2026, 6, 19)
        _write_report(tmp_path, monday, friday)
        assert find_report_file(tmp_path, monday, friday) is not None

    def test_any_prefix_matches(self, tmp_path: Any) -> None:
        monday, friday = date(2026, 6, 15), date(2026, 6, 19)
        _write_report(tmp_path, monday, friday, prefix="other.user")
        assert find_report_file(tmp_path, monday, friday) is not None

    def test_no_match_returns_none(self, tmp_path: Any) -> None:
        assert find_report_file(tmp_path, date(2026, 6, 15), date(2026, 6, 19)) is None

    def test_missing_root_returns_none(self, tmp_path: Any) -> None:
        assert find_report_file(tmp_path / "nope", date(2026, 6, 15), date(2026, 6, 19)) is None


# --- handler (mocked client + tmp report dir) -------------------------------------


class TestHandleReportGaps:
    async def test_covered_and_missing_weeks(self, tmp_path: Any) -> None:
        # Two weeks with tracked time relative to real "today" (handler uses
        # now()); week0 = current week, week1 = previous, week2 = before that.
        today = date.today()
        this_monday = _monday_of(today)
        week1_monday = this_monday - timedelta(days=7)
        week2_monday = this_monday - timedelta(days=14)

        worklogs = [
            _wl(week1_monday.isoformat(), 8 * 3600),
            _wl((week1_monday + timedelta(days=6)).isoformat(), 2 * 3600),  # Sunday
            _wl(week2_monday.isoformat(), 4 * 3600),
        ]
        _write_report(tmp_path, week1_monday, week1_monday + timedelta(days=4))

        config = _make_config(report_output_dir=str(tmp_path))
        mock = _mock_client(worklogs)
        result = await _handle_report_gaps(
            {"username": "testuser"}, config, cast(JiraTempoClient, mock)
        )

        assert "Report gaps for testuser" in result
        week1_line = next(
            line for line in result.splitlines() if week1_monday.isoformat() in line
        )
        assert "covered" in week1_line
        assert "10h tracked" in week1_line  # 8h Mon + 2h Sun (Mon–Sun data window)
        week2_line = next(
            line for line in result.splitlines() if week2_monday.isoformat() in line
        )
        assert "MISSING" in week2_line
        assert "Summary:" in result
        # Strictly read-only: no mutating client surface touched.
        for name in ("create_worklog", "delete_worklog"):
            getattr(mock, name).assert_not_awaited()
        # Exactly the two read-only network calls.
        assert mock.find_worker_key.await_count == 1
        assert mock.search_worklogs.await_count == 1

    async def test_no_tracked_time_weeks(self, tmp_path: Any) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        mock = _mock_client([])
        result = await _handle_report_gaps(
            {"since": "2026-06-01"}, config, cast(JiraTempoClient, mock)
        )
        assert "No weeks with tracked time found" in result

    async def test_clamped_since_disclosed(self, tmp_path: Any) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        mock = _mock_client([])
        result = await _handle_report_gaps(
            {"since": "2020-01-01"}, config, cast(JiraTempoClient, mock)
        )
        assert "clamped" in result
        # The fetch window starts at the clamped boundary, not 2020-01-01.
        floor = (date.today() - timedelta(weeks=GAP_WINDOW_WEEKS)).isoformat()
        assert mock.search_worklogs.await_args.args[0] == floor

    async def test_bad_since_no_network(self, tmp_path: Any) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        mock = _mock_client([])
        with pytest.raises(ValueError, match="Invalid since"):
            await _handle_report_gaps({"since": "not-a-date"}, config, cast(JiraTempoClient, mock))
        mock.find_worker_key.assert_not_awaited()
        mock.search_worklogs.assert_not_awaited()

    async def test_unknown_param_rejected(self, tmp_path: Any) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        mock = _mock_client([])
        with pytest.raises(ValueError, match="Unknown parameter"):
            await _handle_report_gaps(
                {"target_date": "2026-06-17"}, config, cast(JiraTempoClient, mock)
            )
        mock.find_worker_key.assert_not_awaited()


# --- render + schema ---------------------------------------------------------------


class TestRenderAndSchema:
    def test_render_summary_counts(self, tmp_path: Any) -> None:
        worklogs = [
            _wl("2026-06-15", 8 * 3600),
            _wl("2026-06-22", 4 * 3600),
        ]
        _write_report(tmp_path, date(2026, 6, 15), date(2026, 6, 19))
        gaps = build_week_gaps(
            worklogs, root=tmp_path, window_start=date(2026, 6, 15), window_end=date(2026, 6, 28)
        )
        text = render_week_gaps(
            gaps,
            username="testuser",
            since=date(2026, 6, 15),
            today=date(2026, 6, 28),
            clamped=False,
            root=tmp_path,
        )
        assert "Summary: 2 weeks with tracked time — 1 covered, 1 missing report file(s)" in text
        assert "total tracked 12h" in text

    def test_schema_registered(self) -> None:
        tool = next(t for t in TOOLS if t.name == "report_gaps")
        assert tool.inputSchema["required"] == []
        assert tool.inputSchema["additionalProperties"] is False
        assert set(tool.inputSchema["properties"]) == {"username", "since"}
