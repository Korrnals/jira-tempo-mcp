"""B6 (ArchComm 2026-10-30): health_check tool.

Output contract (§2 item 2): versions, configuration paths, statuses, and
credential PRESENCE flags ("JIRA_PAT: set"). Secret values must never
appear in the response NOR in any log line at any log level; API probe
failures report the exception class name only.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient, JiraTempoError
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import TOOLS, _handle_health_check

# A distinctive fake secret: if any code path echoed the PAT value, this
# exact string would surface in the response or logs and the test would fail.
_FAKE_PAT = "super-secret-pat-value-DO-NOT-LEAK-42"


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": _FAKE_PAT,
        "report_output_dir": "/tmp/jtm-test-reports",
        "log_level": "INFO",
    }
    defaults.update(overrides)
    return Config(**defaults)


def _make_mock_client() -> AsyncMock:
    return AsyncMock(spec=JiraTempoClient)


class TestHealthCheckSchema:
    def test_tool_registered_and_strict(self) -> None:
        schema = {t.name: t.inputSchema for t in TOOLS}
        assert "health_check" in schema
        assert schema["health_check"].get("additionalProperties") is False
        assert schema["health_check"].get("required") == []


class TestHealthCheckOffline:
    async def test_versions_paths_and_presence_flags(self) -> None:
        config = _make_config()
        result = await _handle_health_check(
            {}, config, cast(JiraTempoClient, _make_mock_client())
        )
        assert "Health check — jira-tempo-mcp" in result
        assert "Python:" in result
        assert "MCP SDK:" in result
        assert "Config: loaded" in result
        assert "JIRA_BASE_URL: set" in result
        assert "JIRA_USER: set" in result
        assert "JIRA_PAT: set" in result
        assert "TEMPO_API_TOKEN: not set (falls back to JIRA_PAT)" in result
        assert "report_output_dir: /tmp/jtm-test-reports" in result
        assert "template_dir:" in result

    async def test_probe_apis_absent_never_touches_client(self) -> None:
        client = _make_mock_client()
        await _handle_health_check({}, _make_config(), cast(JiraTempoClient, client))
        client.get_myself.assert_not_called()
        client.find_worker_key.assert_not_called()

    async def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown parameter"):
            await _handle_health_check(
                {"verbose": True}, _make_config(), cast(JiraTempoClient, _make_mock_client())
            )

    async def test_no_secret_value_in_response(self) -> None:
        result = await _handle_health_check(
            {}, _make_config(), cast(JiraTempoClient, _make_mock_client())
        )
        assert _FAKE_PAT not in result

    async def test_repr_of_config_stays_masked(self) -> None:
        """Defense in depth: Config.__repr__ keeps masking the PAT (B6 tie-in)."""
        config = _make_config()
        assert _FAKE_PAT not in repr(config)


class TestHealthCheckProbes:
    async def test_probe_apis_ok(self) -> None:
        client = _make_mock_client()
        result = await _handle_health_check(
            {"probe_apis": True}, _make_config(), cast(JiraTempoClient, client)
        )
        assert "Jira (get_myself): ok" in result
        assert "Tempo (find_worker_key): ok" in result
        client.get_myself.assert_awaited_once()
        client.find_worker_key.assert_awaited_once()

    async def test_probe_failure_reports_class_name_only(self, caplog: pytest.LogCaptureFixture) -> None:
        client = _make_mock_client()
        client.get_myself.side_effect = JiraTempoError("HTTP 500 with <response body>")
        client.find_worker_key.side_effect = JiraTempoError("HTTP 401 unauthorized")
        config = _make_config()
        with caplog.at_level(logging.DEBUG):
            result = await _handle_health_check(
                {"probe_apis": True}, config, cast(JiraTempoClient, client)
            )
        assert "Jira (get_myself): FAILED (JiraTempoError)" in result
        assert "Tempo (find_worker_key): FAILED (JiraTempoError)" in result
        # Neither the exception message body nor the secret may leak into
        # the response or any log record.
        assert "response body" not in result
        assert "401" not in result
        assert _FAKE_PAT not in result
        assert _FAKE_PAT not in caplog.text
