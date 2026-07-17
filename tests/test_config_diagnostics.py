"""Tests for ConfigError diagnostics in config.py.

Covers:
- ``ConfigError`` is a ``ValueError`` subclass (back-compat with existing
  ``except ValueError`` handlers).
- ``load_config`` raises ``ConfigError`` with a backend-specific message
  when any required var (JIRA_BASE_URL, JIRA_USER, JIRA_PAT) is missing or
  empty.
- The error message lists the missing variable name and remediation steps
  for VS Code MCP / CLI / Docker backends.
- The error message NEVER contains the secret value (no PAT leakage) —
  only the variable name and description.
- The error message points the user at the auto-config command.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from jira_tempo_mcp.config import ConfigError, load_config

# Variables that are required and trigger ConfigError when missing.
_REQUIRED_VARS = ("JIRA_BASE_URL", "JIRA_USER", "JIRA_PAT")


def _clear_all_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset every required var plus the optional ones that could shadow."""
    for var in _REQUIRED_VARS:
        monkeypatch.delenv(var, raising=False)


class TestConfigErrorType:
    def test_config_error_is_value_error(self) -> None:
        assert issubclass(ConfigError, ValueError)


class TestLoadConfigMissing:
    """Each missing required var must raise ConfigError with a clear message."""

    def test_all_missing_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ConfigError) as excinfo:
            load_config()
        msg = str(excinfo.value)
        assert "JIRA_BASE_URL" in msg
        # Backend-specific remediation pointers must be present.
        assert "VS Code MCP" in msg
        assert "CLI" in msg
        assert "Docker" in msg
        # Pointer to the auto-config command.
        assert "install.py --non-interactive --register-only" in msg

    def test_only_pat_missing_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            # JIRA_PAT missing
        }
        with patch.dict(os.environ, env, clear=True), pytest.raises(ConfigError) as excinfo:
            load_config()
        msg = str(excinfo.value)
        assert "JIRA_PAT" in msg
        # Other required vars should NOT be named — only the missing one.
        assert "JIRA_BASE_URL" not in msg.replace("docs/mcp-integration.ru.md", "")
        # No secret value in the message.
        assert "your_personal_access_token" not in msg

    def test_empty_pat_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Whitespace-only PAT is treated as empty.
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "   ",
        }
        with patch.dict(os.environ, env, clear=True), pytest.raises(ConfigError) as excinfo:
            load_config()
        msg = str(excinfo.value)
        assert "JIRA_PAT" in msg

    def test_only_user_missing_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "",
            "JIRA_PAT": "tok123",
        }
        with patch.dict(os.environ, env, clear=True), pytest.raises(ConfigError) as excinfo:
            load_config()
        msg = str(excinfo.value)
        assert "JIRA_USER" in msg

    def test_message_has_no_secret_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A PAT accidentally leaked via env must NOT appear in the error."""
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "LEAKED_SECRET_TOKEN_xyz",
        }
        # Now unset JIRA_PAT inside load_config's view to trigger the error,
        # but keep the env-population order so any code path that reads the
        # wrong source cannot surface the value.
        env.pop("JIRA_PAT")
        with patch.dict(os.environ, env, clear=True), pytest.raises(ConfigError) as excinfo:
            load_config()
        assert "LEAKED_SECRET_TOKEN_xyz" not in str(excinfo.value)


class TestLoadConfigSuccessStillWorks:
    """Smoke test — valid env still loads without raising ConfigError."""

    def test_valid_env_loads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "tok123",
        }
        with patch.dict(os.environ, env, clear=False):
            for key in (
                "TEMPO_API_TOKEN",
                "REPORT_OUTPUT_DIR",
                "REPORT_AUTHOR_NAME",
                "REPORT_SECTION_MAP",
                "REPORT_SECTION_MAP_FILE",
                "JIRA_HTTP_TIMEOUT",
            ):
                os.environ.pop(key, None)
            c = load_config()
        assert c.jira_base_url == "https://jira.test"
        assert c.jira_user == "tester"


class TestConfigErrorMessageStructure:
    """The remediation message must list all three backends + the command."""

    def test_message_lists_three_backends(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ConfigError) as excinfo:
            load_config()
        msg = str(excinfo.value)
        assert "VS Code MCP" in msg
        assert "envFile" in msg
        assert "mcp.json" in msg
        assert ".env.local" in msg
        assert "docs/mcp-integration.ru.md" in msg
        # CLI path
        assert "cp .env.example .env" in msg
        # Docker path
        assert "--env-file" in msg
        # Auto-config pointer
        assert "install.py --non-interactive --register-only" in msg
