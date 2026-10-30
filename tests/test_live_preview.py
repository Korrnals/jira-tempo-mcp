"""B3 (ArchComm 2026-10-30): live mode for preview_report_template.

live=true renders the REAL worklogs of the target week through the same
fetch context as generate_weekly_report, returns the render in the tool
response, and never writes a file. Mock mode stays the default and never
touches the client. The log carries template name / worklog count /
duration — never the render body.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import _handle_preview_report_template

TARGET_DATE = date(2026, 6, 17)


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "author_display_name": "Тестовый Пользователь",
        "section_map": {"PROJECT-100": "Section A"},
        "stable_order": ["PROJECT-100"],
        "non_issue_sections": ["Jira work."],
    }
    defaults.update(overrides)
    return Config(**defaults)


def _make_mock_client(worklogs: list[dict[str, Any]] | None = None) -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "worker123"
    mock.search_worklogs.return_value = worklogs or [
        {
            "issueKey": "PROJECT-100",
            "timeSpentSeconds": 7200,
            "startDate": "2026-06-16",
            "comment": "Реальная работа недели",
            "authorAccountId": "worker123",
        }
    ]

    async def _get_issue(key: str) -> dict[str, Any]:
        return {"key": key, "fields": {"summary": f"Summary for {key}"}}

    mock.get_issue.side_effect = _get_issue
    return mock


class TestLivePreviewMockDefault:
    async def test_default_is_mock_no_client_calls(self) -> None:
        client = _make_mock_client()
        result = await _handle_preview_report_template(
            {"template_name": "default"},
            _make_config(),
            cast(JiraTempoClient, client),
        )
        assert "DEVOPS-101" in result  # mock profile marker
        client.find_worker_key.assert_not_called()
        client.search_worklogs.assert_not_called()

    async def test_live_false_is_mock(self) -> None:
        client = _make_mock_client()
        result = await _handle_preview_report_template(
            {"template_name": "default", "live": False},
            _make_config(),
            cast(JiraTempoClient, client),
        )
        assert "DEVOPS-101" in result
        client.search_worklogs.assert_not_called()

    async def test_sample_data_ignored_in_live(self) -> None:
        """live=true renders real data even if a sample_data profile is sent."""
        client = _make_mock_client()
        result = await _handle_preview_report_template(
            {
                "template_name": "default",
                "live": True,
                "sample_data": "empty",
                "target_date": "2026-06-17",
            },
            _make_config(),
            cast(JiraTempoClient, client),
        )
        client.search_worklogs.assert_awaited_once()
        assert "DEVOPS-101" not in result  # mock profile NOT used
        assert "Реальная работа недели" in result
        assert "Section A" in result  # title from section_map


class TestLivePreviewLive:
    async def test_live_renders_real_week_without_file(self, tmp_path: Path) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        client = _make_mock_client()
        result = await _handle_preview_report_template(
            {"template_name": "default", "live": True, "target_date": "2026-06-17"},
            config,
            cast(JiraTempoClient, client),
        )
        # Real worklog content rendered; title resolved via section_map.
        assert "Реальная работа недели" in result
        assert "Section A" in result
        # Week bounds come from target_date (15–19 June 2026, Mon–Fri).
        assert "15.06.2026" in result and "19.06.2026" in result
        # V2 acceptance: NO new file appears in the reports directory.
        assert list(tmp_path.rglob("*")) == []
        # Read-only traffic: worker key + worklog search + issue title.
        client.find_worker_key.assert_awaited_once_with("testuser")
        client.search_worklogs.assert_awaited_once_with(
            "2026-06-15", "2026-06-19", worker_keys=["worker123"]
        )

    async def test_live_filters_out_of_week_worklogs(self, tmp_path: Path) -> None:
        worklogs = [
            {
                "issueKey": "PROJECT-100",
                "timeSpentSeconds": 3600,
                "startDate": "2026-06-10",  # previous week's Wednesday
                "comment": "Прошлая неделя",
                "authorAccountId": "worker123",
            },
            {
                "issueKey": "PROJECT-100",
                "timeSpentSeconds": 3600,
                "startDate": "2026-06-17",
                "comment": "Эта неделя",
                "authorAccountId": "worker123",
            },
        ]
        client = _make_mock_client(worklogs)
        result = await _handle_preview_report_template(
            {"template_name": "default", "live": True, "target_date": "2026-06-17"},
            _make_config(report_output_dir=str(tmp_path)),
            cast(JiraTempoClient, client),
        )
        assert "Эта неделя" in result
        assert "Прошлая неделя" not in result

    async def test_live_team_template_per_user_section(self, tmp_path: Path) -> None:
        client = _make_mock_client()
        result = await _handle_preview_report_template(
            {"template_name": "team_report", "live": True, "target_date": "2026-06-17"},
            _make_config(report_output_dir=str(tmp_path)),
            cast(JiraTempoClient, client),
        )
        # Per-user section keyed by the resolved worker key, displayed
        # under the configured author label.
        assert "Тестовый Пользователь" in result
        assert "Сводка по команде" in result

    async def test_live_unknown_template_still_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown template"):
            await _handle_preview_report_template(
                {"template_name": "no-such-template", "live": True},
                _make_config(),
                cast(JiraTempoClient, _make_mock_client()),
            )

    async def test_live_invalid_target_date_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid date"):
            await _handle_preview_report_template(
                {"template_name": "default", "live": True, "target_date": "17-06-2026"},
                _make_config(),
                cast(JiraTempoClient, _make_mock_client()),
            )

    async def test_live_logs_metadata_never_render_body(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            await _handle_preview_report_template(
                {"template_name": "default", "live": True, "target_date": "2026-06-17"},
                _make_config(report_output_dir=str(tmp_path)),
                cast(JiraTempoClient, _make_mock_client()),
            )
        assert "Preview live render: template=default worklogs=1 duration_ms=" in caplog.text
        # Red line §2 item 9: the render body never reaches the log.
        assert "Реальная работа недели" not in caplog.text
        assert "Summary for PROJECT-100" not in caplog.text

    async def test_live_empty_week_renders_header(self, tmp_path: Path) -> None:
        client = _make_mock_client(worklogs=[])
        result = await _handle_preview_report_template(
            {"template_name": "default", "live": True, "target_date": "2026-06-17"},
            _make_config(report_output_dir=str(tmp_path)),
            cast(JiraTempoClient, client),
        )
        assert "[Тестовый Пользователь]" in result
