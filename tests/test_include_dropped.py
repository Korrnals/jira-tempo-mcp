"""B4 (ArchComm 2026-10-30): include_dropped on the report generators.

Contract §2 item 4: txt — a 'Dropped lines (N)' section (with content) in
the TOOL RESPONSE, file unchanged; json — a 'dropped' field; md — always
'(0)' by construction; log — counter only, NEVER the dropped content;
default render byte-identical (golden gate stays green).
"""

from __future__ import annotations

import json as _json
import logging
from datetime import date
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.report import generate_weekly_report
from jira_tempo_mcp.server import (
    TOOLS,
    _handle_generate_report,
    _handle_generate_team_report,
)
from jira_tempo_mcp.team_report import generate_team_report
from jira_tempo_mcp.templates._shared import (
    drop_lines_matching_title,
    drop_lines_matching_title_counted,
)

TARGET_DATE = date(2026, 6, 17)


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "author_display_name": "Тестовый Пользователь",
        "section_map": {"PROJECT-100": "Section A", "PROJECT-102": "Section C"},
        "stable_order": ["PROJECT-100", "PROJECT-102"],
        "non_issue_sections": ["Jira work."],
    }
    defaults.update(overrides)
    return Config(**defaults)


def _wl(key: str | None, seconds: int, day: int, comment: str = "", author: str = "wk-a") -> dict[str, Any]:
    wl: dict[str, Any] = {
        "issueKey": key,
        "timeSpentSeconds": seconds,
        "startDate": f"2026-06-{day:02d}",
        "authorAccountId": author,
    }
    if comment:
        wl["comment"] = comment
    return wl


_WEEKLY = [
    _wl("PROJECT-100", 7200, 15, "Подготовка стенда"),
    # Multi-line comments with the title echo INSIDE — a single-line
    # all-echo comment hits the never-orphan-hours fallback (the line stays
    # in the render, nothing hidden) and is therefore never counted.
    _wl("PROJECT-102", 5400, 16, "Section C\n- уточнил требования"),
    _wl("PROJECT-200", 3600, 17, "Task Alpha\n- код-ревью"),
]

_TEAM: dict[str, list[dict[str, Any]]] = {
    "alice": [_wl("PROJECT-100", 7200, 15, "Section A\n- настройка стенда", author="wk-alice")],
    "bob": [_wl("PROJECT-200", 3600, 16, "Task Alpha\n- отладка", author="wk-bob")],
}

_SUMMARIES = {"PROJECT-200": "Task Alpha"}


def _weekly_client() -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "wk-a"
    mock.search_worklogs.return_value = _WEEKLY

    async def _get_issue(key: str) -> dict[str, Any]:
        return {"key": key, "fields": {"summary": _SUMMARIES.get(key, f"Summary for {key}")}}

    mock.get_issue.side_effect = _get_issue
    return mock


def _team_client() -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.side_effect = lambda u: f"wk-{u}"

    async def _search(
        date_from: str, date_to: str, worker_keys: list[str] | None = None
    ) -> list[dict[str, Any]]:
        return _TEAM.get((worker_keys or [""])[0].removeprefix("wk-"), [])

    mock.search_worklogs.side_effect = _search

    async def _get_issue(key: str) -> dict[str, Any]:
        return {"key": key, "fields": {"summary": _SUMMARIES.get(key, f"Summary for {key}")}}

    mock.get_issue.side_effect = _get_issue
    return mock


class TestSharedCountedVariant:
    """drop_lines_matching_title_counted vs the plain helper (drift guard)."""

    def test_counted_collects_removed_lines(self) -> None:
        dropped: list[str] = []
        result = drop_lines_matching_title_counted("Task Alpha\n- деталь", "Task Alpha", dropped)
        assert result == "- деталь"
        assert dropped == ["Task Alpha"]

    def test_all_echo_fallback_records_nothing(self) -> None:
        dropped: list[str] = []
        result = drop_lines_matching_title_counted("Task Alpha", "Task Alpha", dropped)
        assert result == "Task Alpha"  # hours never orphaned
        assert dropped == []

    def test_plain_matches_counted_with_discard(self) -> None:
        """The plain helper must stay behaviour-identical to the counted one."""
        cases = [
            ("Task Alpha\n- x", "Task Alpha"),
            ("Task Alpha", "Task Alpha"),
            ("   ", "Task Alpha"),
            ("без заголовка", None),
            ("", "Task Alpha"),
        ]
        for comment, title in cases:
            dropped: list[str] = []
            counted = drop_lines_matching_title_counted(comment, title, dropped)
            assert drop_lines_matching_title(comment, title) == counted

    def test_counted_in_all(self) -> None:
        from jira_tempo_mcp.templates import _shared

        assert "drop_lines_matching_title_counted" in _shared.__all__


class TestWeeklyIncludeDropped:
    async def test_txt_file_identical_default_vs_include(self, tmp_path: Path) -> None:
        """The report FILE must not change when include_dropped=true."""
        config = _make_config()
        plain = await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path / "plain",
        )
        dropped: list[str] = []
        with_include = await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path / "with",
            include_dropped=True,
            dropped_out=dropped,
        )
        assert Path(plain).read_text(encoding="utf-8") == Path(with_include).read_text(
            encoding="utf-8"
        )
        assert sorted(dropped) == ["Section C", "Task Alpha"]

    async def test_default_run_collects_nothing(self, tmp_path: Path) -> None:
        """include_dropped absent → no collector wired, no log counter."""
        dropped: list[str] = []
        await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            _make_config(),
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            dropped_out=dropped,
        )
        assert dropped == []

    async def test_handler_txt_response_section(self, tmp_path: Path) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        result = await _handle_generate_report(
            {"target_date": "2026-06-17", "include_dropped": True},
            config,
            cast(JiraTempoClient, _weekly_client()),
        )
        assert "Dropped lines (2)" in result
        assert "  - Section C" in result
        assert "  - Task Alpha" in result

    async def test_handler_md_response_always_zero(self, tmp_path: Path) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        result = await _handle_generate_report(
            {"target_date": "2026-06-17", "format": "md", "include_dropped": True},
            config,
            cast(JiraTempoClient, _weekly_client()),
        )
        # Committee decision: md always reports (0) — construction, documented.
        assert "Dropped lines (0)" in result
        assert "Dropped lines (2)" not in result

    async def test_json_gains_dropped_field(self, tmp_path: Path) -> None:
        config = _make_config()
        with_dropped = await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path / "j1",
            fmt="json",
            include_dropped=True,
        )
        data = _json.loads(Path(with_dropped).read_text(encoding="utf-8"))
        assert data["dropped"] == []

        plain = await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path / "j2",
            fmt="json",
        )
        plain_data = _json.loads(Path(plain).read_text(encoding="utf-8"))
        assert "dropped" not in plain_data

    async def test_log_carries_counter_never_content(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = _make_config()
        with caplog.at_level(logging.DEBUG):
            await generate_weekly_report(
                cast(JiraTempoClient, _weekly_client()),
                config,
                target_date=TARGET_DATE,
                output_dir=tmp_path,
                include_dropped=True,
            )
        assert "Dropped 2 lines" in caplog.text
        # Red line §2 item 9: dropped CONTENT never reaches any log record.
        assert "Section C" not in caplog.text
        assert "Task Alpha" not in caplog.text

    async def test_off_switch_matches_previous_behaviour(self, tmp_path: Path) -> None:
        """include_dropped=false → response identical to the pre-B4 shape."""
        config = _make_config(report_output_dir=str(tmp_path))
        result = await _handle_generate_report(
            {"target_date": "2026-06-17", "include_dropped": False},
            config,
            cast(JiraTempoClient, _weekly_client()),
        )
        assert result.count("\n") == 1  # path + reports directory only
        assert "Dropped" not in result


class TestTeamIncludeDropped:
    async def test_txt_result_carries_dropped_and_file_unchanged(self, tmp_path: Path) -> None:
        config = _make_config()
        plain = await generate_team_report(
            cast(JiraTempoClient, _team_client()),
            config,
            ["alice", "bob"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path / "plain",
        )
        with_include = await generate_team_report(
            cast(JiraTempoClient, _team_client()),
            config,
            ["alice", "bob"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path / "with",
            include_dropped=True,
        )
        assert plain.file_path.read_text(encoding="utf-8") == with_include.file_path.read_text(
            encoding="utf-8"
        )
        assert sorted(with_include.dropped_lines) == ["Section A", "Task Alpha"]

    async def test_handler_txt_response_section(self, tmp_path: Path) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        result = await _handle_generate_team_report(
            {
                "users": ["alice", "bob"],
                "date_from": "2026-06-15",
                "date_to": "2026-06-19",
                "include_dropped": True,
            },
            config,
            cast(JiraTempoClient, _team_client()),
        )
        assert "Dropped lines (2)" in result
        assert "  - Section A" in result

    async def test_json_gains_dropped_field(self, tmp_path: Path) -> None:
        config = _make_config()
        result = await generate_team_report(
            cast(JiraTempoClient, _team_client()),
            config,
            ["alice", "bob"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
            fmt="json",
            include_dropped=True,
        )
        data = _json.loads(result.file_path.read_text(encoding="utf-8"))
        assert data["dropped"] == []


class TestIncludeDroppedSchema:
    def test_property_declared_on_both_generators(self) -> None:
        schemas = {t.name: t.inputSchema for t in TOOLS}
        for name in ("generate_weekly_report", "generate_team_report"):
            props = schemas[name]["properties"]
            assert "include_dropped" in props, f"{name} schema lacks include_dropped"
            assert props["include_dropped"]["type"] == "boolean"
            assert "md" in props["include_dropped"]["description"]
