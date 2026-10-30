"""B5 (ArchComm 2026-10-30): strict parameter validation for generator tools.

Generator handlers must reject unknown parameter names with an explicit
error that lists the valid parameters (contract §2 item 6), and their
inputSchemas must declare ``additionalProperties: false``. Handlers outside
the generator set are intentionally NOT strict in this wave.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import (
    TOOLS,
    _handle_generate_report,
    _handle_generate_tasks_report,
    _handle_generate_team_report,
    _handle_preview_report_template,
)

# Tools covered by the B5 strict contract.
_STRICT_TOOLS = (
    "generate_weekly_report",
    "generate_team_report",
    "generate_tasks_report",
    "preview_report_template",
)

# Tools born in this wave (B6 health_check, B2 week_status) that are strict
# BY CONSTRUCTION — the B5 guard only protects the pre-wave non-generator
# surface.
_NEW_IN_WAVE = ("health_check", "week_status")


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "author_display_name": "Тестовый Пользователь",
        "section_map": {"PROJECT-100": "Section A"},
        "stable_order": ["PROJECT-100"],
        "non_issue_sections": [],
    }
    defaults.update(overrides)
    return Config(**defaults)


def _make_mock_client(worklogs: list[dict[str, Any]] | None = None) -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "worker123"
    mock.search_worklogs.return_value = worklogs or []

    async def _get_issue(key: str) -> dict[str, Any]:
        return {"key": key, "fields": {"summary": f"Summary for {key}"}}

    mock.get_issue.side_effect = _get_issue
    return mock


class TestStrictSchemas:
    """Generator inputSchemas declare additionalProperties: false."""

    def test_generator_schemas_are_strict(self) -> None:
        schemas = {t.name: t.inputSchema for t in TOOLS}
        for name in _STRICT_TOOLS:
            assert schemas[name].get("additionalProperties") is False, (
                f"{name} inputSchema must set additionalProperties=false (B5)"
            )

    def test_non_generator_schemas_untouched(self) -> None:
        """Handlers outside the generator set stay non-strict in this wave."""
        schemas = {t.name: t.inputSchema for t in TOOLS}
        for name, schema in schemas.items():
            if name in _STRICT_TOOLS or name in _NEW_IN_WAVE:
                continue
            # Not asserted False — the wave contract leaves them as-is.
            assert schema.get("additionalProperties") is not False, (
                f"{name} was non-generator: B5 must not touch it, but its "
                "schema now declares additionalProperties=false"
            )


class TestStrictHandlersRejectUnknownKeys:
    """V5 acceptance: unknown parameter → explicit error listing valid ones."""

    async def test_weekly_report_rejects_date_from(self) -> None:
        """The historical JTM bug: date_from silently ignored — now an error."""
        config = _make_config()
        with pytest.raises(ValueError) as excinfo:
            await _handle_generate_report(
                {"date_from": "2026-06-15", "date_to": "2026-06-19"},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )
        msg = str(excinfo.value)
        assert "'date_from'" in msg and "'date_to'" in msg
        for valid in ("target_date", "output_dir", "template", "format", "username"):
            assert valid in msg

    async def test_team_report_rejects_unknown(self) -> None:
        config = _make_config()
        with pytest.raises(ValueError) as excinfo:
            await _handle_generate_team_report(
                {"users": ["alice"], "target_date": "2026-06-17"},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )
        msg = str(excinfo.value)
        assert "'target_date'" in msg
        assert "date_from" in msg and "date_to" in msg

    async def test_tasks_report_rejects_unknown(self) -> None:
        config = _make_config()
        with pytest.raises(ValueError) as excinfo:
            await _handle_generate_tasks_report(
                {"users": ["alice"], "target_date": "2026-06-17"},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )
        msg = str(excinfo.value)
        assert "'target_date'" in msg
        for valid in ("users", "active_only", "output_dir", "format"):
            assert valid in msg

    async def test_preview_rejects_unknown(self) -> None:
        config = _make_config()
        with pytest.raises(ValueError) as excinfo:
            await _handle_preview_report_template(
                {"template_name": "default", "date_from": "2026-06-15"},
                config,
                cast(JiraTempoClient, _make_mock_client()),
            )
        msg = str(excinfo.value)
        assert "'date_from'" in msg
        assert "template_name" in msg and "sample_data" in msg


class TestStrictDoesNotBreakValidCalls:
    """Existing valid calls keep working (contract §2 item 6)."""

    async def test_weekly_report_valid_params_pass(self, tmp_path: Any) -> None:
        config = _make_config(report_output_dir=str(tmp_path))
        client = _make_mock_client()
        result = await _handle_generate_report(
            {"target_date": "2026-06-17", "format": "txt"},
            config,
            cast(JiraTempoClient, client),
        )
        assert "Weekly report generated" in result
        client.find_worker_key.assert_called_once()

    async def test_preview_valid_params_pass(self) -> None:
        config = _make_config()
        result = await _handle_preview_report_template(
            {"template_name": "default", "sample_data": "minimal"},
            config,
            cast(JiraTempoClient, _make_mock_client()),
        )
        assert "DEVOPS-101" in result

    async def test_unknown_key_never_reaches_client(self) -> None:
        """Rejection happens before any Jira/Tempo traffic."""
        client = _make_mock_client()
        with pytest.raises(ValueError, match="Unknown parameter"):
            await _handle_generate_report(
                {"bogus": 1}, _make_config(), cast(JiraTempoClient, client)
            )
        client.find_worker_key.assert_not_called()
        client.search_worklogs.assert_not_called()
