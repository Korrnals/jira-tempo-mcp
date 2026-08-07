"""Unit tests for config.py — validation, defaults, section map loading."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from jira_tempo_mcp.config import (
    DEFAULT_SECTION_MAP,
    Config,
    _apply_dotenv_files,
    _env_local_candidates,
    load_config,
)


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


class TestResilientConfigLoading:
    """Tests for the dotenv priority chain (problem 1 — resilient config-loading).

    Priority (highest first): process env → MCP-host ``.env.local`` → repo
    ``.env`` → defaults. These tests exercise :func:`_apply_dotenv_files`
    against temp dotenv files so the real machine's ``.env.local`` never
    leaks into test outcomes.
    """

    def _write_env_file(self, path: Path, values: dict[str, str]) -> Path:
        """Write a KEY=value dotenv file (content is test fixture only)."""
        path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
        return path

    def test_env_local_read_when_process_env_missing(self, tmp_path: Path) -> None:
        """Problem 1: ``.env.local`` is read so direct terminal Python calls work.

        When ``MCP_ENV_FILE`` points to a ``.env.local`` and the process env
        lacks a key, that key must be loaded from the file. This is the exact
        scenario that broke weekly-report generation on 2026-08-07.
        """
        env_local = self._write_env_file(
            tmp_path / ".env.local",
            {
                "JIRA_BASE_URL": "https://from-env-local.test",
                "JIRA_USER": "localuser",
                "JIRA_PAT": "tok-from-local",
                "REPORT_OUTPUT_DIR": str(tmp_path / "reports"),
            },
        )
        with patch.dict(os.environ, {}, clear=True):
            os.environ["MCP_ENV_FILE"] = str(env_local)
            _apply_dotenv_files()
            c = load_config()
        assert c.jira_base_url == "https://from-env-local.test"
        assert c.report_output_dir == str(tmp_path / "reports")

    def test_process_env_wins_over_env_local(self, tmp_path: Path) -> None:
        """Process env has highest priority (load_dotenv override=False)."""
        env_local = self._write_env_file(
            tmp_path / ".env.local",
            {
                "JIRA_BASE_URL": "https://from-env-local.test",
                "REPORT_OUTPUT_DIR": str(tmp_path / "local"),
            },
        )
        process_env = {
            "JIRA_BASE_URL": "https://from-process.test",
            "JIRA_USER": "procuser",
            "JIRA_PAT": "proc-tok",
            "REPORT_OUTPUT_DIR": str(tmp_path / "process"),
            "MCP_ENV_FILE": str(env_local),
        }
        with patch.dict(os.environ, process_env, clear=True):
            _apply_dotenv_files()
            c = load_config()
        assert c.jira_base_url == "https://from-process.test"
        assert c.report_output_dir == str(tmp_path / "process")

    def test_env_local_wins_over_repo_env(self, tmp_path: Path) -> None:
        """``.env.local`` takes priority over the repo ``.env`` for unset keys.

        Keys absent from the process env resolve from ``.env.local`` first,
        then the repo ``.env``. We patch ``_ENV_PATH`` to a temp repo env so
        no real repo file interferes.
        """
        env_local = self._write_env_file(
            tmp_path / ".env.local",
            {
                "JIRA_BASE_URL": "https://local-wins.test",
                "JIRA_USER": "localuser",
                "JIRA_PAT": "local-tok",
                "REPORT_OUTPUT_DIR": str(tmp_path / "from-local"),
            },
        )
        repo_env = self._write_env_file(
            tmp_path / ".env",
            {
                "JIRA_BASE_URL": "https://repo-loses.test",
                "REPORT_OUTPUT_DIR": str(tmp_path / "from-repo"),
            },
        )
        with (
            patch("jira_tempo_mcp.config._ENV_PATH", repo_env),
            patch.dict(os.environ, {}, clear=True),
        ):
            os.environ["MCP_ENV_FILE"] = str(env_local)
            _apply_dotenv_files()
            c = load_config()
        assert c.jira_base_url == "https://local-wins.test"
        assert c.report_output_dir == str(tmp_path / "from-local")

    def test_repo_env_used_when_no_env_local(self, tmp_path: Path) -> None:
        """Repo ``.env`` is the fallback when no ``.env.local`` exists.

        We patch ``_env_local_candidates`` to return an empty list so the
        real machine's VS Code ``.env.local`` does not interfere with this
        test — modelling the scenario where no MCP-host env file is present.
        """
        repo_env = self._write_env_file(
            tmp_path / ".env",
            {
                "JIRA_BASE_URL": "https://from-repo.test",
                "JIRA_USER": "repouser",
                "JIRA_PAT": "repo-tok",
                "REPORT_OUTPUT_DIR": str(tmp_path / "repo-reports"),
            },
        )
        with (
            patch("jira_tempo_mcp.config._ENV_PATH", repo_env),
            patch("jira_tempo_mcp.config._env_local_candidates", return_value=[]),
            patch.dict(os.environ, {}, clear=True),
        ):
            _apply_dotenv_files()
            c = load_config()
        assert c.jira_base_url == "https://from-repo.test"
        assert c.report_output_dir == str(tmp_path / "repo-reports")

    def test_apply_dotenv_files_is_idempotent(self, tmp_path: Path) -> None:
        """Re-applying dotenv sources does not duplicate or error."""
        env_local = self._write_env_file(
            tmp_path / ".env.local",
            {"JIRA_BASE_URL": "https://idempotent.test", "JIRA_USER": "u", "JIRA_PAT": "t"},
        )
        with patch.dict(os.environ, {}, clear=True):
            os.environ["MCP_ENV_FILE"] = str(env_local)
            _apply_dotenv_files()
            _apply_dotenv_files()
            assert os.getenv("JIRA_BASE_URL") == "https://idempotent.test"

    def test_env_local_candidates_explicit_override(self, tmp_path: Path) -> None:
        """``MCP_ENV_FILE`` override is listed first in candidates."""
        explicit = tmp_path / "custom.env"
        explicit.write_text("KEY=val\n")
        with patch.dict(os.environ, {"MCP_ENV_FILE": str(explicit)}, clear=True):
            candidates = _env_local_candidates()
        assert candidates[0] == explicit
