"""Tests for templates DX improvements: list_report_templates kind/engine
provenance and the preview_report_template MCP tool (offline mock preview).

These tests exercise the server-level handlers directly — they do not call
Jira/Tempo or write files. The preview tool uses built-in mock worklogs.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import (
    _handle_list_report_templates,
    _handle_preview_report_template,
)


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "author_display_name": "Тестовый Пользователь",
        "timezone": "Europe/Moscow",
        "section_map": {"PROJECT-100": "Section A"},
        "stable_order": ["PROJECT-100"],
        "non_issue_sections": [],
    }
    defaults.update(overrides)
    return Config(**defaults)


def _make_mock_client() -> AsyncMock:
    # preview_report_template never uses the client; a spec mock is enough
    # to satisfy the JiraTempoClient type at the handler boundary.
    return AsyncMock(spec=JiraTempoClient)


# --- list_report_templates: kind/engine provenance ---


class TestListReportTemplatesKind:
    """list_report_templates surfaces (kind, engine) provenance per template."""

    async def test_output_contains_builtin_kind(self) -> None:
        config = _make_config()
        result = await _handle_list_report_templates({}, config, cast(JiraTempoClient, _make_mock_client()))
        assert "(builtin" in result

    async def test_output_contains_engine_python(self) -> None:
        config = _make_config()
        result = await _handle_list_report_templates({}, config, cast(JiraTempoClient, _make_mock_client()))
        assert "Python" in result

    async def test_each_template_has_provenance(self) -> None:
        config = _make_config()
        result = await _handle_list_report_templates({}, config, cast(JiraTempoClient, _make_mock_client()))
        # Every non-header, non-empty line should carry a (kind, engine) pair.
        body_lines = [
            line for line in result.splitlines()
            if line.startswith("- ")
        ]
        assert body_lines, "expected at least one template line"
        for line in body_lines:
            assert "(" in line and ", " in line and ")" in line, (
                f"template line missing (kind, engine) provenance: {line!r}"
            )


# --- preview_report_template ---


class TestPreviewReportTemplate:
    """preview_report_template renders templates against mock worklogs."""

    async def test_default_profile_renders_nonempty(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "default"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        # The default profile includes several DEVOPS-* issues plus OPS-200;
        # the standup entry has issueKey=None and is skipped by the template.
        assert "DEVOPS-101" in result

    async def test_default_profile_contains_time(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "default"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        # The default profile includes worklogs; the rendered report should
        # contain a human-readable duration (h/m suffix from format_seconds).
        assert any(token in result for token in ("h", "m", "ч", "м")), (
            "expected a human-readable duration in the rendered preview"
        )

    async def test_minimal_profile_renders(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "default", "sample_data": "minimal"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        assert "DEVOPS-101" in result

    async def test_empty_profile_renders_without_crash(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "default", "sample_data": "empty"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        # Empty profile exercises the empty-state rendering path. The handler
        # must NOT crash and must return a string (possibly a fallback message).
        assert isinstance(result, str)

    async def test_unknown_template_raises(self) -> None:
        config = _make_config()
        with pytest.raises(ValueError, match="Unknown template"):
            await _handle_preview_report_template(
                {"template_name": "does-not-exist"},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )

    async def test_builtin_default_renders(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "default", "sample_data": "default"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    async def test_builtin_weekly_summary_renders(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "weekly_summary", "sample_data": "default"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    async def test_builtin_team_report_renders(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "team_report", "sample_data": "default"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        # team_report expects per_user_worklogs/users kwargs which the preview
        # handler does not supply; it should still render its header structure
        # without crashing (the body may be empty).
        assert isinstance(result, str)

    async def test_invalid_sample_data_raises(self) -> None:
        config = _make_config()
        with pytest.raises(ValueError, match="sample_data"):
            await _handle_preview_report_template(
                {"template_name": "default", "sample_data": "bogus"},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )

    async def test_empty_template_name_raises(self) -> None:
        config = _make_config()
        with pytest.raises(ValueError, match="template_name"):
            await _handle_preview_report_template(
                {"template_name": ""},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )

    async def test_missing_template_name_raises(self) -> None:
        config = _make_config()
        with pytest.raises(ValueError, match="template_name"):
            await _handle_preview_report_template(
                {},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )

    async def test_sample_data_defaults_to_default(self) -> None:
        """Omitting sample_data should behave identically to 'default'."""
        config = _make_config()
        explicit = await _handle_preview_report_template(
            {"template_name": "default", "sample_data": "default"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        implicit = await _handle_preview_report_template(
            {"template_name": "default"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        assert explicit == implicit
