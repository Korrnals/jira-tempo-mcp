"""Tests for the wheel-mode installer/uninstaller (``jira_tempo_mcp.installer``).

Covers JTM-004: ``pip install jira-tempo-mcp`` users get a real
``jira-tempo-mcp install`` instead of the old "requires a git clone" error.

All filesystem effects are redirected to a tmp tree by monkeypatching
``Path.home`` (same pattern as ``tests/test_specialist.py``) — the real
``~/.config/Code/User`` is never touched. The specialist delegate and the
connectivity check are monkeypatched, so no harness dirs or network are hit.
Process env is scrubbed of the managed JIRA_*/LOG_LEVEL keys per test.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from jira_tempo_mcp import installer
from jira_tempo_mcp.installer import (
    InstallOptions,
    NonInteractivePrompter,
    collect_settings,
    env_local_path,
    install_wheel,
    mcp_json_path,
    parse_env_file,
    register_vscode_entry,
    remove_vscode_entry,
    uninstall_wheel,
    write_env_local,
)

MANAGED = ("JIRA_BASE_URL", "JIRA_USER", "JIRA_PAT", "JIRA_TIMEZONE", "LOG_LEVEL")


@pytest.fixture(autouse=True)
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() to a tmp tree; scrub managed env vars."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(installer.Path, "home", lambda: home)
    for var in (*MANAGED, "MCP_ENV_FILE"):
        monkeypatch.delenv(var, raising=False)
    return home


class FakePrompter:
    """Scripted Prompter — answers by label substring, confirms in order."""

    def __init__(self, answers: dict[str, str] | None = None, confirms: list[bool] | None = None):
        self.answers = answers or {}
        self.confirms = list(confirms or [])
        self.asked: list[tuple[str, str, bool]] = []
        self.confirmed: list[str] = []

    def ask(self, label: str, default: str = "", *, secret: bool = False) -> str:
        self.asked.append((label, default, secret))
        for fragment, answer in self.answers.items():
            if fragment in label:
                return answer
        return default

    def confirm(self, msg: str, default: bool = True) -> bool:
        self.confirmed.append(msg)
        return self.confirms.pop(0) if self.confirms else default


def _vscode_dir(home: Path) -> Path:
    return home / ".config" / "Code" / "User"


def _non_interactive(**overrides: Any) -> InstallOptions:
    return InstallOptions(non_interactive=True, **overrides)


# ---------------------------------------------------------------------------
# Settings collection priority: flag > env > .env.local > prompt
# ---------------------------------------------------------------------------


class TestCollectSettingsPriority:
    def test_flag_beats_env_and_existing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JIRA_BASE_URL", "https://from-env.example.com")
        existing = {"JIRA_BASE_URL": "https://from-file.example.com"}
        options = _non_interactive(jira_base_url="https://from-flag.example.com")
        settings, missing = collect_settings(options, existing, NonInteractivePrompter())
        assert settings["JIRA_BASE_URL"] == "https://from-flag.example.com"
        # USER/PAT were not provided by any source — still reported as missing.
        assert missing == ["JIRA_USER", "JIRA_PAT"]

    def test_env_beats_existing_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JIRA_USER", "env-user")
        options = _non_interactive(jira_base_url="https://b.example.com", jira_pat="p")
        settings, _ = collect_settings(options, {"JIRA_USER": "file-user"}, NonInteractivePrompter())
        assert settings["JIRA_USER"] == "env-user"

    def test_existing_env_local_used_without_flag_or_env(self) -> None:
        options = _non_interactive()
        existing = {
            "JIRA_BASE_URL": "https://kept.example.com",
            "JIRA_USER": "kept-user",
            "JIRA_PAT": "kept-pat",
        }
        settings, missing = collect_settings(options, existing, NonInteractivePrompter())
        assert settings["JIRA_BASE_URL"] == "https://kept.example.com"
        assert settings["JIRA_USER"] == "kept-user"
        assert settings["JIRA_PAT"] == "kept-pat"
        assert missing == []

    def test_non_interactive_missing_required_listed(self) -> None:
        settings, missing = collect_settings(
            _non_interactive(), {}, NonInteractivePrompter()
        )
        assert missing == ["JIRA_BASE_URL", "JIRA_USER", "JIRA_PAT"]
        assert settings["JIRA_TIMEZONE"] == "Europe/Moscow"
        assert settings["LOG_LEVEL"] == "INFO"

    def test_optional_defaults_applied(self) -> None:
        settings, _ = collect_settings(
            _non_interactive(
                jira_base_url="https://b.example.com", jira_user="u", jira_pat="p"
            ),
            {},
            NonInteractivePrompter(),
        )
        assert settings["JIRA_TIMEZONE"] == "Europe/Moscow"
        assert settings["LOG_LEVEL"] == "INFO"

    def test_interactive_prompt_used_when_nothing_set(self) -> None:
        prompter = FakePrompter(
            {
                "base URL": "https://prompted.example.com",
                "username": "prompted-user",
                "Token": "prompted-pat",
            }
        )
        settings, _ = collect_settings(InstallOptions(), {}, prompter)
        assert settings["JIRA_BASE_URL"] == "https://prompted.example.com"
        assert settings["JIRA_USER"] == "prompted-user"
        assert settings["JIRA_PAT"] == "prompted-pat"
        # PAT prompt must be marked secret (getpass path in the real prompter).
        pat_asks = [a for a in prompter.asked if "PAT" in a[0]]
        assert pat_asks and pat_asks[0][2] is True

    def test_interactive_prompt_default_is_built_in_url(self) -> None:
        prompter = FakePrompter()  # answers with defaults
        settings, missing = collect_settings(InstallOptions(), {}, prompter)
        base_ask_default = next(d for label, d, _ in prompter.asked if "base URL" in label)
        assert base_ask_default == "https://jira.example.com"
        assert settings["JIRA_BASE_URL"] == "https://jira.example.com"
        assert missing == ["JIRA_USER", "JIRA_PAT"]


# ---------------------------------------------------------------------------
# .env.local merge
# ---------------------------------------------------------------------------


class TestWriteEnvLocal:
    def test_creates_file_chmod_600_and_reports_keys(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "sub" / ".env.local"
        added, updated = write_env_local(
            path,
            {
                "JIRA_BASE_URL": "https://b.example.com",
                "JIRA_USER": "u",
                "JIRA_PAT": "s3cret",
                "JIRA_TIMEZONE": "Europe/Moscow",
                "LOG_LEVEL": "INFO",
            },
        )
        assert len(added) == 5 and updated == []
        assert path.exists()
        if os.name == "posix":
            assert (path.stat().st_mode & 0o777) == 0o600
        out = capsys.readouterr().out
        assert "JIRA_PAT added" in out
        assert "s3cret" not in out  # never print values

    def test_foreign_keys_preserved_and_managed_overwritten(self, tmp_path: Path) -> None:
        path = tmp_path / ".env.local"
        path.write_text(
            "GITHUB_TOKEN=foreign-secret\n"
            "JIRA_USER=old-user\n"
            "JIRA_PAT=old-pat\n",
            encoding="utf-8",
        )
        added, updated = write_env_local(
            path,
            {
                "JIRA_BASE_URL": "https://new.example.com",
                "JIRA_USER": "new-user",
                "JIRA_PAT": "new-pat",
                "JIRA_TIMEZONE": "UTC",
                "LOG_LEVEL": "DEBUG",
            },
        )
        assert added == ["JIRA_BASE_URL", "JIRA_TIMEZONE", "LOG_LEVEL"]
        assert sorted(updated) == ["JIRA_PAT", "JIRA_USER"]
        data = parse_env_file(path)
        assert data["GITHUB_TOKEN"] == "foreign-secret"
        assert data["JIRA_USER"] == "new-user"
        assert data["JIRA_PAT"] == "new-pat"


# ---------------------------------------------------------------------------
# mcp.json registration
# ---------------------------------------------------------------------------


class TestRegisterVscodeEntry:
    def test_creates_entry_with_backup_and_preserves_foreign_servers(self) -> None:
        vsc = _vscode_dir(Path.home())
        vsc.mkdir(parents=True)
        mcp = vsc / "mcp.json"
        mcp.write_text(
            json.dumps(
                {"servers": {"github": {"command": "gh-mcp", "args": []}}},
                indent=2,
            ),
            encoding="utf-8",
        )
        env_local = vsc / ".env.local"

        assert register_vscode_entry(env_local) is True

        backups = list(vsc.glob("mcp.json.bak.*"))
        assert len(backups) == 1
        assert json.loads(backups[0].read_text(encoding="utf-8"))["servers"]["github"]

        data = json.loads(mcp.read_text(encoding="utf-8"))
        entry = data["servers"]["jira-tempo"]
        assert data["servers"]["github"] == {"command": "gh-mcp", "args": []}
        assert entry["command"] == sys.executable
        assert entry["args"] == ["-m", "jira_tempo_mcp.server"]
        assert entry["envFile"] == str(env_local.resolve())

    def test_missing_vscode_dir_skips_without_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert register_vscode_entry(Path("/nonexistent/.env.local")) is True
        out = capsys.readouterr().out
        assert "Skipping mcp.json registration" in out
        assert not mcp_json_path().exists()

    def test_skip_vscode_flag_skips(self, fake_home: Path) -> None:  # noqa: ARG002
        _vscode_dir(fake_home).mkdir(parents=True)
        assert register_vscode_entry(
            env_local_path(), skip_vscode=True
        ) is True
        assert not mcp_json_path().exists()

    def test_corrupt_mcp_json_refused(self, fake_home: Path) -> None:
        vsc = _vscode_dir(fake_home)
        vsc.mkdir(parents=True)
        mcp = vsc / "mcp.json"
        mcp.write_text("{not valid json", encoding="utf-8")
        assert register_vscode_entry(vsc / ".env.local") is False
        assert mcp.read_text(encoding="utf-8") == "{not valid json"  # untouched


# ---------------------------------------------------------------------------
# Wheel install flow (non-interactive)
# ---------------------------------------------------------------------------


class TestInstallWheelFlow:
    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_home: Path,
        argv: list[str],
        *,
        vscode_dir_exists: bool = True,
    ) -> tuple[int, dict[str, list[Any]]]:
        calls: dict[str, list[Any]] = {"specialist": [], "check": []}

        def fake_specialist(argv_: list[str]) -> int:
            calls["specialist"].append(argv_)
            return 0

        def fake_check(settings: dict[str, str]) -> str | None:
            calls["check"].append(dict(settings))
            return "Test User"

        monkeypatch.setattr("jira_tempo_mcp.specialist.run_specialist", fake_specialist)
        monkeypatch.setattr(installer, "check_connectivity", fake_check)
        if vscode_dir_exists:
            _vscode_dir(fake_home).mkdir(parents=True)
        rc = install_wheel(argv)
        return rc, calls

    def test_full_flow_writes_env_registers_and_installs_specialist(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path
    ) -> None:
        rc, calls = self._run(
            monkeypatch,
            fake_home,
            [
                "--non-interactive",
                "--jira-base-url",
                "https://b.example.com",
                "--jira-user",
                "u",
                "--jira-pat",
                "p",
            ],
        )
        assert rc == 0
        env = parse_env_file(env_local_path())
        assert env["JIRA_BASE_URL"] == "https://b.example.com"
        assert env["JIRA_PAT"] == "p"
        assert env["JIRA_TIMEZONE"] == "Europe/Moscow"
        entry = json.loads(mcp_json_path().read_text(encoding="utf-8"))["servers"][
            "jira-tempo"
        ]
        assert entry["command"] == sys.executable
        assert calls["specialist"] == [[]]
        assert calls["check"] and calls["check"][0]["JIRA_PAT"] == "p"

    def test_missing_required_in_non_interactive_exits_1(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc, calls = self._run(
            monkeypatch, fake_home, ["--non-interactive", "--jira-base-url", "https://b"]
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "JIRA_USER" in err and "JIRA_PAT" in err
        assert "non-interactive" in err.lower()
        assert calls["specialist"] == []
        assert not env_local_path().exists()

    def test_no_agent_and_skip_check_flags(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path
    ) -> None:
        rc, calls = self._run(
            monkeypatch,
            fake_home,
            [
                "--non-interactive",
                "--no-agent",
                "--skip-check",
                "--jira-base-url",
                "https://b",
                "--jira-user",
                "u",
                "--jira-pat",
                "p",
            ],
        )
        assert rc == 0
        assert calls["specialist"] == []
        assert calls["check"] == []

    def test_env_vars_drive_non_interactive(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path
    ) -> None:
        monkeypatch.setenv("JIRA_BASE_URL", "https://env.example.com")
        monkeypatch.setenv("JIRA_USER", "env-user")
        monkeypatch.setenv("JIRA_PAT", "env-pat")
        rc, _ = self._run(monkeypatch, fake_home, ["--non-interactive"])
        assert rc == 0
        env = parse_env_file(env_local_path())
        assert env["JIRA_BASE_URL"] == "https://env.example.com"
        assert env["JIRA_USER"] == "env-user"

    def test_specialist_failure_does_not_fail_install(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path
    ) -> None:
        monkeypatch.setattr(
            "jira_tempo_mcp.specialist.run_specialist", lambda _argv: 1
        )
        monkeypatch.setattr(installer, "check_connectivity", lambda _s: None)
        _vscode_dir(fake_home).mkdir(parents=True)
        rc = install_wheel(
            [
                "--non-interactive",
                "--jira-base-url",
                "https://b",
                "--jira-user",
                "u",
                "--jira-pat",
                "p",
            ]
        )
        assert rc == 0


# ---------------------------------------------------------------------------
# Wheel uninstall flow
# ---------------------------------------------------------------------------


class TestUninstallWheelFlow:
    def _seed(self, fake_home: Path) -> Path:
        vsc = _vscode_dir(fake_home)
        vsc.mkdir(parents=True)
        (vsc / "mcp.json").write_text(
            json.dumps(
                {
                    "servers": {
                        "github": {"command": "gh-mcp"},
                        "jira-tempo": {"command": "python", "args": []},
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (vsc / ".env.local").write_text(
            "JIRA_BASE_URL=https://b.example.com\n"
            "JIRA_PAT=secret\n"
            "GITHUB_TOKEN=foreign\n",
            encoding="utf-8",
        )
        return vsc

    def test_removes_entry_specialist_and_env_keys_on_confirm(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        vsc = self._seed(fake_home)
        removed: list[list[str]] = []
        monkeypatch.setattr(
            "jira_tempo_mcp.specialist.run_specialist",
            lambda argv_: removed.append(argv_) or 0,
        )
        rc = uninstall_wheel(["--non-interactive"])  # non-interactive confirm → default yes

        assert rc == 0
        assert removed == [["--remove"]]
        servers = json.loads((vsc / "mcp.json").read_text(encoding="utf-8"))["servers"]
        assert "jira-tempo" not in servers
        assert servers["github"] == {"command": "gh-mcp"}
        assert list(vsc.glob("mcp.json.bak.*"))
        env = parse_env_file(vsc / ".env.local")
        assert "JIRA_BASE_URL" not in env and "JIRA_PAT" not in env
        assert env["GITHUB_TOKEN"] == "foreign"
        # The package itself is never auto-uninstalled — the hint names pip.
        assert "pip uninstall jira-tempo-mcp" in capsys.readouterr().out

    def test_declining_keeps_env_keys(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path
    ) -> None:
        vsc = self._seed(fake_home)
        monkeypatch.setattr(
            "jira_tempo_mcp.specialist.run_specialist", lambda _argv: 0
        )
        prompter = FakePrompter(confirms=[False])

        # Drive the flow with a scripted confirm via the interactive prompter path.
        monkeypatch.setattr(installer, "_prompter_for", lambda _options: prompter)
        rc = uninstall_wheel([])
        assert rc == 0
        env = parse_env_file(vsc / ".env.local")
        assert env["JIRA_PAT"] == "secret"
        assert prompter.confirmed

    def test_removes_empty_env_file_when_no_foreign_keys(
        self, monkeypatch: pytest.MonkeyPatch, fake_home: Path
    ) -> None:
        vsc = _vscode_dir(fake_home)
        vsc.mkdir(parents=True)
        (vsc / ".env.local").write_text("JIRA_PAT=only-key\n", encoding="utf-8")
        monkeypatch.setattr(
            "jira_tempo_mcp.specialist.run_specialist", lambda _argv: 0
        )
        rc = uninstall_wheel(["--non-interactive"])
        assert rc == 0
        assert not (vsc / ".env.local").exists()


# ---------------------------------------------------------------------------
# remove_vscode_entry specifics
# ---------------------------------------------------------------------------


class TestRemoveVscodeEntry:
    def test_absent_file_is_noop(self, fake_home: Path) -> None:  # noqa: ARG002
        assert remove_vscode_entry() is True

    def test_absent_entry_is_noop(self, fake_home: Path) -> None:
        vsc = _vscode_dir(fake_home)
        vsc.mkdir(parents=True)
        (vsc / "mcp.json").write_text('{"servers": {}}', encoding="utf-8")
        assert remove_vscode_entry() is True
        assert json.loads((vsc / "mcp.json").read_text(encoding="utf-8")) == {"servers": {}}
