"""Unit tests for config.py — validation, defaults, section map loading."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from jira_tempo_mcp.config import DEFAULT_SECTION_MAP, Config, load_config


class TestConfigValidation:
    """Tests for pydantic validation in Config."""

    def test_valid_config(self) -> None:
        c = Config(
            jira_base_url="https://jira.example.com",
            jira_user="testuser",
            jira_pat="secret",
        )
        assert c.jira_base_url == "https://jira.example.com"
        assert c.timezone == "Europe/Moscow"
        assert c.log_level == "INFO"

    def test_empty_base_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            Config(jira_base_url="", jira_user="u", jira_pat="p")

    def test_empty_user_rejected(self) -> None:
        with pytest.raises(ValueError):
            Config(jira_base_url="https://x", jira_user="", jira_pat="p")

    def test_empty_pat_rejected(self) -> None:
        with pytest.raises(ValueError):
            Config(jira_base_url="https://x", jira_user="u", jira_pat="")

    def test_invalid_log_level_rejected(self) -> None:
        with pytest.raises(ValueError):
            Config(jira_base_url="https://x", jira_user="u", jira_pat="p", log_level="VERBOSE")

    def test_tempo_token_fallback(self) -> None:
        c = Config(jira_base_url="https://x", jira_user="u", jira_pat="p")
        assert c.tempo_token == "p"  # falls back to jira_pat

    def test_tempo_token_separate(self) -> None:
        c = Config(
            jira_base_url="https://x", jira_user="u", jira_pat="p", tempo_api_token="tempo_tok"
        )
        assert c.tempo_token == "tempo_tok"

    def test_repr_masks_pat(self) -> None:
        c = Config(jira_base_url="https://x", jira_user="u", jira_pat="secret123")
        repr_str = repr(c)
        assert "secret123" not in repr_str
        assert "***" in repr_str

    def test_repr_masks_tempo_token(self) -> None:
        c = Config(
            jira_base_url="https://x",
            jira_user="u",
            jira_pat="p",
            tempo_api_token="tempo_secret",
        )
        assert "tempo_secret" not in repr(c)

    def test_report_author_header_default(self) -> None:
        c = Config(jira_base_url="https://x", jira_user="testuser", jira_pat="p")
        assert c.report_author_header == "testuser"

    def test_report_author_header_override(self) -> None:
        c = Config(
            jira_base_url="https://x",
            jira_user="testuser",
            jira_pat="p",
            author_display_name="Test User",
        )
        assert c.report_author_header == "Test User"

    def test_default_section_map(self) -> None:
        c = Config(jira_base_url="https://x", jira_user="u", jira_pat="p")
        assert c.section_map == DEFAULT_SECTION_MAP

    def test_frozen(self) -> None:
        c = Config(jira_base_url="https://x", jira_user="u", jira_pat="p")
        with pytest.raises(ValidationError):
            c.jira_user = "other"


class TestLoadConfig:
    """Tests for load_config with mocked env."""

    def test_load_full_config(self) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "tok123",
            "JIRA_TIMEZONE": "UTC",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env, clear=False):
            # Clear env vars not in our test set.
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
        assert c.timezone == "UTC"
        assert c.log_level == "DEBUG"

    def test_load_missing_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True), pytest.raises((RuntimeError, ValueError)):
            load_config()

    def test_load_custom_section_map(self, tmp_path: Path) -> None:
        section_file = tmp_path / "sections.json"
        section_file.write_text(json.dumps({"PROJECT-1": "Custom Title"}))
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "tok123",
            "REPORT_SECTION_MAP_FILE": str(section_file),
        }
        with patch.dict(os.environ, env, clear=False):
            for key in (
                "TEMPO_API_TOKEN",
                "REPORT_OUTPUT_DIR",
                "REPORT_AUTHOR_NAME",
                "REPORT_SECTION_MAP",
                "JIRA_HTTP_TIMEOUT",
            ):
                os.environ.pop(key, None)
            c = load_config()
        assert c.section_map == {"PROJECT-1": "Custom Title"}

    def test_load_inline_section_map(self) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "tok123",
            "REPORT_SECTION_MAP": '{"PROJECT-2": "Inline"}',
        }
        with patch.dict(os.environ, env, clear=False):
            for key in (
                "TEMPO_API_TOKEN",
                "REPORT_OUTPUT_DIR",
                "REPORT_AUTHOR_NAME",
                "REPORT_SECTION_MAP_FILE",
                "JIRA_HTTP_TIMEOUT",
            ):
                os.environ.pop(key, None)
            c = load_config()
        assert c.section_map == {"PROJECT-2": "Inline"}

    def test_load_invalid_http_timeout_falls_back(self) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "tok123",
            "JIRA_HTTP_TIMEOUT": "not_a_number",
        }
        with patch.dict(os.environ, env, clear=False):
            for key in (
                "TEMPO_API_TOKEN",
                "REPORT_OUTPUT_DIR",
                "REPORT_AUTHOR_NAME",
                "REPORT_SECTION_MAP",
                "REPORT_SECTION_MAP_FILE",
            ):
                os.environ.pop(key, None)
            c = load_config()
        assert c.http_timeout == 30.0


class TestReportTeamUsers:
    """Tests for REPORT_TEAM_USERS env var and team_users_resolved property."""

    def test_report_team_users_from_env(self) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "tok123",
            "REPORT_TEAM_USERS": '["pikalov", "tarasenk", "dmz", "gritsel"]',
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
        assert c.report_team_users == ["pikalov", "tarasenk", "dmz", "gritsel"]
        assert c.team_users_resolved == ["pikalov", "tarasenk", "dmz", "gritsel"]

    def test_team_users_resolved_fallback_to_jira_user(self) -> None:
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
                "REPORT_TEAM_USERS",
            ):
                os.environ.pop(key, None)
            c = load_config()
        assert c.report_team_users == []
        assert c.team_users_resolved == ["tester"]

    def test_report_team_users_invalid_json_empty(self) -> None:
        env = {
            "JIRA_BASE_URL": "https://jira.test",
            "JIRA_USER": "tester",
            "JIRA_PAT": "tok123",
            "REPORT_TEAM_USERS": "not-json",
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
        assert c.report_team_users == []
        assert c.team_users_resolved == ["tester"]
