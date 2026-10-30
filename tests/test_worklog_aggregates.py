"""P5 (backlog wave 2026-10-30): list_worklogs aggregation parameters.

Contract:
- new optional ``group_by`` ("none"|"issue"|"day", default "none") and
  ``include_totals`` (bool, default false);
- aggregation happens in the handler over the SAME rows — the client is
  not touched;
- default output stays BYTE-IDENTICAL to the pre-P5 response (guard);
- offline: fully mocked client, no HTTP, no .env reads.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import TOOLS, _handle_list_worklogs
from jira_tempo_mcp.utils import format_seconds_to_human
from jira_tempo_mcp.worklog_aggregates import (
    GROUP_BY_VALUES,
    WorklogEntry,
    aggregate_sections,
)


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "timezone": "Europe/Moscow",
    }
    defaults.update(overrides)
    return Config(**defaults)


def _wl(
    key: str,
    seconds: int,
    started: str = "2026-06-15T10:00:00.000+0300",
    wl_id: str = "1",
) -> dict[str, Any]:
    return {
        "tempoWorklogId": wl_id,
        "issueKey": key,
        "timeSpentSeconds": seconds,
        "started": started,
        "comment": "comment text",
    }


def _mock_client(worklogs: list[dict[str, Any]]) -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "wk-testuser"
    mock.search_worklogs.return_value = worklogs
    return mock


def _default_output(worklogs: list[dict[str, Any]]) -> str:
    """The pre-P5 response shape (guards byte-identity)."""
    rows = []
    for wl in worklogs:
        rows.append(
            f"- {wl['started']} | {wl['issueKey']} | "
            + format_seconds_to_human(wl["timeSpentSeconds"])
            + f" | id={wl['tempoWorklogId']} | comment text"
        )
    header = f"Worklogs 2026-06-15 .. 2026-06-16 ({len(worklogs)} entries):\n"
    return header + "\n".join(rows) if rows else header + "(none)"


WORKLOGS = [
    _wl("PROJECT-100", 2 * 3600, "2026-06-15T10:00:00.000+0300", "101"),
    _wl("PROJECT-102", 4 * 3600 + 1800, "2026-06-15T14:00:00.000+0300", "102"),
    _wl("PROJECT-100", 1 * 3600, "2026-06-16T09:00:00.000+0300", "103"),
]


class TestP5DefaultByteIdentity:
    async def test_default_output_unchanged(self) -> None:
        """No aggregation params → exactly the pre-P5 response."""
        config = _make_config()
        mock = _mock_client(WORKLOGS)
        result = await _handle_list_worklogs(
            {"date_from": "2026-06-15", "date_to": "2026-06-16"},
            config,
            cast(JiraTempoClient, mock),
        )
        assert result == _default_output(WORKLOGS)
        # Client touched only for the plain list — no extra calls.
        assert mock.find_worker_key.await_count == 1
        assert mock.search_worklogs.await_count == 1

    async def test_explicit_defaults_equal_no_params(self) -> None:
        config = _make_config()
        implicit = await _handle_list_worklogs(
            {"date_from": "2026-06-15", "date_to": "2026-06-16"},
            config,
            cast(JiraTempoClient, _mock_client(WORKLOGS)),
        )
        explicit = await _handle_list_worklogs(
            {
                "date_from": "2026-06-15",
                "date_to": "2026-06-16",
                "group_by": "none",
                "include_totals": False,
            },
            config,
            cast(JiraTempoClient, _mock_client(WORKLOGS)),
        )
        assert implicit == explicit == _default_output(WORKLOGS)


class TestP5GroupByIssue:
    async def test_hours_per_issue_descending(self) -> None:
        config = _make_config()
        mock = _mock_client(WORKLOGS)
        result = await _handle_list_worklogs(
            {"date_from": "2026-06-15", "date_to": "2026-06-16", "group_by": "issue"},
            config,
            cast(JiraTempoClient, mock),
        )
        # The plain rows are still present, then the aggregate section.
        assert result.startswith(_default_output(WORKLOGS))
        assert "By issue (hours, descending):" in result
        issue_block = result.split("By issue (hours, descending):")[1]
        pos_100 = issue_block.find("PROJECT-100")
        pos_102 = issue_block.find("PROJECT-102")
        assert pos_102 < pos_100, "PROJECT-102 (4h 30m) must sort above PROJECT-100 (3h)"
        assert "- PROJECT-102: 4h 30m" in issue_block
        assert "- PROJECT-100: 3h" in issue_block
        # Aggregation adds NO extra network calls.
        assert mock.search_worklogs.await_count == 1

    async def test_group_by_day_chronological(self) -> None:
        config = _make_config()
        result = await _handle_list_worklogs(
            {"date_from": "2026-06-15", "date_to": "2026-06-16", "group_by": "day"},
            config,
            cast(JiraTempoClient, _mock_client(WORKLOGS)),
        )
        assert "By day (hours):" in result
        assert "- 2026-06-15: 6h 30m" in result
        assert "- 2026-06-16: 1h" in result
        assert result.find("2026-06-15: 6h 30m") < result.find("2026-06-16: 1h")


class TestP5IncludeTotals:
    async def test_totals_only(self) -> None:
        config = _make_config()
        result = await _handle_list_worklogs(
            {"date_from": "2026-06-15", "date_to": "2026-06-16", "include_totals": True},
            config,
            cast(JiraTempoClient, _mock_client(WORKLOGS)),
        )
        assert "Total for period: 7h 30m" in result
        assert "By issue" not in result and "By day" not in result

    async def test_totals_with_grouping(self) -> None:
        config = _make_config()
        result = await _handle_list_worklogs(
            {
                "date_from": "2026-06-15",
                "date_to": "2026-06-16",
                "group_by": "issue",
                "include_totals": True,
            },
            config,
            cast(JiraTempoClient, _mock_client(WORKLOGS)),
        )
        assert "By issue (hours, descending):" in result
        assert "Total for period: 7h 30m" in result

    async def test_totals_on_empty_range(self) -> None:
        config = _make_config()
        result = await _handle_list_worklogs(
            {"date_from": "2026-06-15", "date_to": "2026-06-16", "include_totals": True},
            config,
            cast(JiraTempoClient, _mock_client([])),
        )
        assert "Total for period: 0h" in result


class TestP5Validation:
    async def test_invalid_group_by_raises(self) -> None:
        config = _make_config()
        mock = _mock_client(WORKLOGS)
        with pytest.raises(ValueError, match="'group_by' must be one of"):
            await _handle_list_worklogs(
                {"date_from": "2026-06-15", "group_by": "week"},
                config,
                cast(JiraTempoClient, mock),
            )
        # Invalid input fails BEFORE any network call.
        mock.find_worker_key.assert_not_awaited()

    async def test_non_bool_include_totals_raises(self) -> None:
        config = _make_config()
        mock = _mock_client(WORKLOGS)
        with pytest.raises(ValueError, match="'include_totals' must be a boolean"):
            await _handle_list_worklogs(
                {"date_from": "2026-06-15", "include_totals": "yes"},
                config,
                cast(JiraTempoClient, mock),
            )
        mock.find_worker_key.assert_not_awaited()


class TestP5PureFunctions:
    def test_aggregate_sections_empty_entries(self) -> None:
        out = aggregate_sections([], group_by="issue", include_totals=True)
        assert "By issue (hours, descending):" in out
        assert "Total for period: 0h" in out

    def test_unparseable_date_goes_to_unknown_bucket(self) -> None:
        entries = [WorklogEntry("PROJECT-100", None, 3600)]
        out = aggregate_sections(entries, group_by="day", include_totals=False)
        assert "- (unknown date): 1h" in out

    def test_group_by_values_contract(self) -> None:
        assert GROUP_BY_VALUES == ("none", "issue", "day")


class TestP5ToolSchema:
    def test_schema_declares_new_params(self) -> None:
        tool = next(t for t in TOOLS if t.name == "list_worklogs")
        props = tool.inputSchema["properties"]
        assert props["group_by"]["enum"] == ["none", "issue", "day"]
        assert props["group_by"]["default"] == "none"
        assert props["include_totals"]["type"] == "boolean"
        assert props["include_totals"]["default"] is False
