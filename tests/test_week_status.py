"""B2 (ArchComm 2026-10-30): week_status tool — read-only weekly status.

Contract §2 item 1: data window Mon–Sun; Sat/Sun entries marked «вне окна
рендера»; working days Mon–Fri; days without entries listed; totals vs the
expected_hours norm (default 40); per-day overtime flag (>8h); read-only.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import TOOLS, _handle_week_status
from jira_tempo_mcp.week_status import week_status_text

TARGET_DATE = date(2026, 6, 17)  # Wednesday of the fixture week


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
    }
    defaults.update(overrides)
    return Config(**defaults)


def _wl(day: int, seconds: int, key: str = "PROJECT-100") -> dict[str, Any]:
    return {
        "issueKey": key,
        "timeSpentSeconds": seconds,
        "startDate": f"2026-06-{day:02d}",
        "comment": "комментарий не должен утечь в week_status",
        "authorAccountId": "wk-testuser",
    }


def _mock_client(worklogs: list[dict[str, Any]]) -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "wk-testuser"
    mock.search_worklogs.return_value = worklogs
    return mock


class TestWeekStatusText:
    def test_full_week_with_weekend_and_overtime(self) -> None:
        worklogs = [
            _wl(15, 8 * 3600),  # Mon — exactly 8h, no flag
            _wl(16, 9 * 3600),  # Tue — overtime
            # Wed 17.06 — no entries
            _wl(18, 4 * 3600 + 1800),  # Thu 4h 30m
            _wl(19, 7 * 3600 + 1800),  # Fri 7h 30m
            _wl(20, 2 * 3600),  # Sat — outside render window
        ]
        text = week_status_text(worklogs, target=TARGET_DATE, username="golikhin")
        assert "Week status for golikhin — 2026-06-15 .. 2026-06-21" in text
        assert "Norm: 40h (expected_hours)" in text
        assert "- Mon 15.06: 8h\n" in text  # exactly 8h — no overtime flag
        assert "- Tue 16.06: 9h [overtime >8h]" in text
        assert "- Wed 17.06: no entries" in text
        assert "- Fri 19.06: 7h 30m" in text
        assert "- Sat 20.06: 2h (вне окна рендера)" in text
        assert "- Sun 21.06: no entries" in text
        assert "Days without entries (render window): Wed 17.06" in text
        assert "Total Mon–Fri (render window): 29h" in text
        assert "Total Mon–Sun: 31h" in text
        assert "Weekend tracked: 2h (вне окна рендера)" in text
        assert "Norm check: 29h of 40h — 11h remaining" in text

    def test_norm_parameter_changes_the_check(self) -> None:
        worklogs = [_wl(15, 25 * 3600)]  # Mon 25h (also overtime)
        text = week_status_text(
            worklogs, target=TARGET_DATE, username="u", expected_hours=20
        )
        assert "Norm: 20h (expected_hours)" in text
        assert "Norm check: 25h of 20h — 5h over norm" in text
        assert "- Mon 15.06: 25h [overtime >8h]" in text

    def test_norm_met_boundary(self) -> None:
        worklogs = [_wl(15, 10 * 3600), _wl(16, 10 * 3600), _wl(17, 10 * 3600), _wl(18, 10 * 3600)]
        text = week_status_text(worklogs, target=TARGET_DATE, username="u", expected_hours=40)
        assert "Norm check: 40h of 40h — norm met" in text

    def test_empty_week(self) -> None:
        text = week_status_text([], target=TARGET_DATE, username="u")
        assert text.count("no entries") == 7
        assert "Days without entries (render window): Mon 15.06, Tue 16.06, Wed 17.06, Thu 18.06, Fri 19.06" in text
        assert "Norm check: 0h of 40h — 40h remaining" in text

    def test_out_of_window_worklogs_ignored(self) -> None:
        worklogs = [
            _wl(15, 3600),
            _wl(10, 8 * 3600),  # previous week's Wednesday
            _wl(22, 8 * 3600),  # next week's Monday
        ]
        text = week_status_text(worklogs, target=TARGET_DATE, username="u")
        assert "Total Mon–Sun: 1h" in text

    def test_no_worklog_content_leaks(self) -> None:
        """The status is time-only: comments/keys never appear (read-only)."""
        text = week_status_text([_wl(15, 3600)], target=TARGET_DATE, username="u")
        assert "комментарий" not in text
        assert "PROJECT-100" not in text


class TestWeekStatusHandler:
    async def test_fetches_mon_sun_window_read_only(self) -> None:
        client = _mock_client([])
        result = await _handle_week_status(
            {"target_date": "2026-06-17"}, _make_config(), cast(JiraTempoClient, client)
        )
        # Data window is Mon–SUN (not Mon–Fri).
        client.search_worklogs.assert_awaited_once_with(
            "2026-06-15", "2026-06-21", worker_keys=["wk-testuser"]
        )
        # Strictly read-only: exactly two client calls, no writes.
        client.find_worker_key.assert_awaited_once_with("testuser")
        assert "Week status for testuser" in result

    async def test_username_override(self) -> None:
        client = _mock_client([])
        await _handle_week_status(
            {"username": "golikhin", "target_date": "2026-06-17"},
            _make_config(),
            cast(JiraTempoClient, client),
        )
        client.find_worker_key.assert_awaited_once_with("golikhin")

    async def test_expected_hours_forwarded(self) -> None:
        client = _mock_client([])
        result = await _handle_week_status(
            {"target_date": "2026-06-17", "expected_hours": 20},
            _make_config(),
            cast(JiraTempoClient, client),
        )
        assert "Norm: 20h (expected_hours)" in result

    async def test_invalid_expected_hours_raises(self) -> None:
        for bad in (-1, 0, "40", True):
            with pytest.raises(ValueError, match="expected_hours"):
                await _handle_week_status(
                    {"target_date": "2026-06-17", "expected_hours": bad},
                    _make_config(),
                    cast(JiraTempoClient, _mock_client([])),
                )

    async def test_invalid_target_date_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid date"):
            await _handle_week_status(
                {"target_date": "not-a-date"},
                _make_config(),
                cast(JiraTempoClient, _mock_client([])),
            )

    async def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown parameter"):
            await _handle_week_status(
                {"date_from": "2026-06-15"},
                _make_config(),
                cast(JiraTempoClient, _mock_client([])),
            )


class TestWeekStatusSchema:
    def test_registered_strict_readonly(self) -> None:
        schema = {t.name: t.inputSchema for t in TOOLS}
        assert "week_status" in schema
        assert schema["week_status"].get("additionalProperties") is False
        assert schema["week_status"].get("required") == []
