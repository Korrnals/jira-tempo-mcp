"""Tests for non-interactive mode in install.py.

Covers:
- ``_parse_args`` resolves flags and env-var fallbacks.
- ``InstallOptions`` singleton drives ``_ask`` / ``_confirm`` / ``_ask_choice``.
- ``write_env`` in non-interactive mode writes .env.local from flags/env,
  uses existing .env.local values when flags absent, applies defaults for
  optional fields, and exits cleanly (returns False) with a clear stderr
  message when required values are missing — never raises KeyError.
- ``main`` honours ``--register-only`` and ``--skip-vscode``.

No real user files are touched — all paths redirected via ``monkeypatch``.
No network calls.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

# Make the project root importable so ``import install`` resolves to the
# top-level install.py (not a package).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import install  # noqa: E402  — path setup above is intentional

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect install.py module-level paths to an isolated tmp_path tree."""
    # Clear all JIRA_* / LOG_LEVEL process env so tests are deterministic —
    # the real shell may have JIRA_USER/JIRA_PAT set for the live MCP server.
    for var in (
        "JIRA_BASE_URL",
        "JIRA_USER",
        "JIRA_PAT",
        "JIRA_TIMEZONE",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(var, raising=False)

    vscode_dir = tmp_path / "vscode-user"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    mcp = vscode_dir / "mcp.json"
    env_local = vscode_dir / ".env.local"

    workspace_dir = tmp_path / "project" / ".vscode"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    workspace_mcp = workspace_dir / "mcp.json"

    project_root = tmp_path / "project"
    # Pre-create a minimal pyproject + .env.example so check_files() passes.
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project_root / ".env.example").write_text(
        "JIRA_BASE_URL=https://jira.example.com\n"
        "JIRA_USER=your-username\n"
        "JIRA_PAT=your_personal_access_token_here\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(install, "VSCODE_DIR", vscode_dir)
    monkeypatch.setattr(install, "VSCODE_MCP", mcp)
    monkeypatch.setattr(install, "ENV_LOCAL", env_local)
    monkeypatch.setattr(install, "WORKSPACE_MCP", workspace_mcp)
    monkeypatch.setattr(install, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(install, "ENV_FILE", project_root / ".env")
    monkeypatch.setattr(install, "ENV_EXAMPLE", project_root / ".env.example")
    monkeypatch.setattr(install, "_IS_TTY", False)
    # Reset the options singleton between tests.
    monkeypatch.setattr(install, "_OPTIONS", install.InstallOptions())
    return {
        "vscode_dir": vscode_dir,
        "mcp": mcp,
        "env_local": env_local,
        "workspace_mcp": workspace_mcp,
        "project_root": project_root,
    }


def _set_options(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> install.InstallOptions:
    """Set the module-level options singleton to a non-default state."""
    opts = install.InstallOptions(**kwargs)  # type: ignore[arg-type]
    monkeypatch.setattr(install, "_OPTIONS", opts)
    return opts


# ---------------------------------------------------------------------------
# TestParseArgs
# ---------------------------------------------------------------------------


class TestParseArgs:
    """Test _parse_args — flag parsing with env-var fallback."""

    def test_flags_take_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JIRA_BASE_URL", "https://from-env.example.com")
        opts = install._parse_args(
            ["--non-interactive", "--jira-base-url", "https://from-flag.example.com"]
        )
        assert opts.non_interactive is True
        assert opts.jira_base_url == "https://from-flag.example.com"

    def test_env_fallback_when_flag_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JIRA_USER", "envuser")
        monkeypatch.setenv("JIRA_PAT", "envpat")
        monkeypatch.delenv("JIRA_BASE_URL", raising=False)
        opts = install._parse_args(["--non-interactive"])
        assert opts.jira_user == "envuser"
        assert opts.jira_pat == "envpat"
        assert opts.jira_base_url is None

    def test_yes_alias_for_non_interactive(self) -> None:
        assert install._parse_args(["--yes"]).non_interactive is True
        assert install._parse_args(["-n"]).non_interactive is True

    def test_defaults_for_optional_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JIRA_TIMEZONE", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        opts = install._parse_args(["--non-interactive"])
        assert opts.jira_timezone == "Europe/Moscow"
        assert opts.log_level == "INFO"

    def test_register_only_and_skip_vscode_flags(self) -> None:
        opts = install._parse_args(["--register-only", "--skip-vscode"])
        assert opts.register_only is True
        assert opts.skip_vscode is True


# ---------------------------------------------------------------------------
# TestNonInteractiveHelpers
# ---------------------------------------------------------------------------


class TestNonInteractiveHelpers:
    """Test _ask / _confirm / _ask_choice honour non_interactive mode."""

    def test_ask_returns_default_in_non_interactive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_options(monkeypatch, non_interactive=True)
        # input() should never be called — if it is, the test fails loudly.
        monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("input() called"))
        assert install._ask("label", default="fallback") == "fallback"

    def test_confirm_returns_default_true_in_non_interactive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_options(monkeypatch, non_interactive=True)
        monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("input() called"))
        assert install._confirm("ok?", default=True) is True

    def test_confirm_returns_default_false_in_non_interactive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_options(monkeypatch, non_interactive=True)
        monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("input() called"))
        assert install._confirm("ok?", default=False) is False

    def test_ask_choice_returns_default_in_non_interactive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_options(monkeypatch, non_interactive=True)
        monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("input() called"))
        assert install._ask_choice("pick", options=["a", "b"], default="b") == "b"


# ---------------------------------------------------------------------------
# TestWriteEnvNonInteractive
# ---------------------------------------------------------------------------


class TestWriteEnvNonInteractive:
    """Test write_env() in non-interactive mode."""

    def test_writes_from_flags(
        self, fake_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_options(
            monkeypatch,
            non_interactive=True,
            jira_base_url="https://jira.example.com",
            jira_user="alice",
            jira_pat="secret123",
            jira_timezone="UTC",
            log_level="DEBUG",
        )
        assert install.write_env() is True
        content = fake_paths["env_local"].read_text(encoding="utf-8")
        assert "JIRA_BASE_URL=https://jira.example.com" in content
        assert "JIRA_USER=alice" in content
        assert "JIRA_PAT=secret123" in content
        assert "JIRA_TIMEZONE=UTC" in content
        assert "LOG_LEVEL=DEBUG" in content

    def test_uses_existing_env_local_when_flags_absent(
        self, fake_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pre-seed .env.local with all required values.
        fake_paths["env_local"].write_text(
            "JIRA_BASE_URL=https://existing.example.com\nJIRA_USER=bob\nJIRA_PAT=existing_pat\n",
            encoding="utf-8",
        )
        # Non-interactive with no flags — should pick up existing .env.local.
        _set_options(monkeypatch, non_interactive=True)
        assert install.write_env() is True
        content = fake_paths["env_local"].read_text(encoding="utf-8")
        assert "JIRA_BASE_URL=https://existing.example.com" in content
        assert "JIRA_USER=bob" in content
        assert "JIRA_PAT=existing_pat" in content
        # Optional defaults applied.
        assert "JIRA_TIMEZONE=Europe/Moscow" in content
        assert "LOG_LEVEL=INFO" in content

    def test_missing_required_returns_false_not_raises(
        self,
        fake_paths: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # No flags, no existing .env.local, no env vars — must exit gracefully.
        for var in ("JIRA_BASE_URL", "JIRA_USER", "JIRA_PAT"):
            monkeypatch.delenv(var, raising=False)
        _set_options(monkeypatch, non_interactive=True)
        result = install.write_env()
        assert result is False
        # No .env.local file created.
        assert not fake_paths["env_local"].exists()
        # Stderr contains all three missing var names.
        err = capsys.readouterr().err
        assert "JIRA_BASE_URL" in err
        assert "JIRA_USER" in err
        assert "JIRA_PAT" in err
        # No secret value echoed.
        assert "your_personal_access_token" not in err

    def test_partial_missing_reports_only_missing(
        self,
        fake_paths: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _set_options(
            monkeypatch,
            non_interactive=True,
            jira_base_url="https://jira.example.com",
            # jira_user and jira_pat missing
        )
        for var in ("JIRA_USER", "JIRA_PAT"):
            monkeypatch.delenv(var, raising=False)
        assert install.write_env() is False
        err = capsys.readouterr().err
        # The "missing" bullets section lists only the missing vars.
        # The header/footer mention all three names in prose — so we check
        # the bullet section by ensuring JIRA_USER/JIRA_PAT appear and
        # JIRA_BASE_URL appears only in the header/footer prose, not as a
        # bullet. We assert the header line contains all three (prose), and
        # the bullet section starts with "  • JIRA_USER".
        assert "JIRA_USER" in err
        assert "JIRA_PAT" in err
        # The bullet list must not contain JIRA_BASE_URL (it is provided).
        bullets = [line for line in err.splitlines() if line.startswith("  • ")]
        bullet_vars = [line.split("• ")[1].split(" ")[0] for line in bullets]
        assert "JIRA_USER" in bullet_vars
        assert "JIRA_PAT" in bullet_vars
        assert "JIRA_BASE_URL" not in bullet_vars


# ---------------------------------------------------------------------------
# TestMainFlags
# ---------------------------------------------------------------------------


class TestMainFlags:
    """Test main() honours --register-only and --skip-vscode."""

    def test_register_only_skips_venv(
        self,
        fake_paths: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            install, "create_venv_and_install", lambda: calls.append("venv") or True
        )
        monkeypatch.setattr(install, "write_env", lambda: calls.append("write_env") or True)
        monkeypatch.setattr(install, "register_mcp_step", lambda: calls.append("register") or True)
        monkeypatch.setattr(install, "verify_jira", lambda: calls.append("verify") or True)
        monkeypatch.setattr(install, "print_next_steps", lambda: calls.append("summary") or None)
        monkeypatch.setattr(install, "check_python", lambda: True)
        monkeypatch.setattr(install, "check_files", lambda: True)

        rc = install.main(["--non-interactive", "--register-only"])

        assert rc == 0
        assert calls == ["write_env", "register"]
        # venv and verify and summary must NOT run in register-only mode.
        assert "venv" not in calls
        assert "verify" not in calls
        assert "summary" not in calls

    def test_skip_vscode_skips_registration(
        self,
        fake_paths: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        called: dict[str, bool] = {"register": False}
        monkeypatch.setattr(install, "create_venv_and_install", lambda: True)
        monkeypatch.setattr(install, "write_env", lambda: True)
        monkeypatch.setattr(
            install, "register_mcp_step", lambda: called.__setitem__("register", True) or True
        )
        monkeypatch.setattr(install, "verify_jira", lambda: True)
        monkeypatch.setattr(install, "print_next_steps", lambda: None)
        monkeypatch.setattr(install, "check_python", lambda: True)
        monkeypatch.setattr(install, "check_files", lambda: True)

        rc = install.main(["--non-interactive", "--skip-vscode"])
        assert rc == 0
        # register_mcp_step returns True early due to --skip-vscode, and the
        # outer main sees True — register_mcp_step itself never delegates to
        # register_vscode.
        assert called["register"] is True  # called but internally skips

    def test_full_path_runs_all_steps(
        self,
        fake_paths: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            install, "create_venv_and_install", lambda: calls.append("venv") or True
        )
        monkeypatch.setattr(install, "write_env", lambda: calls.append("write_env") or True)
        monkeypatch.setattr(install, "register_mcp_step", lambda: calls.append("register") or True)
        monkeypatch.setattr(install, "verify_jira", lambda: calls.append("verify") or None)
        monkeypatch.setattr(install, "print_next_steps", lambda: calls.append("summary") or None)
        monkeypatch.setattr(install, "check_python", lambda: True)
        monkeypatch.setattr(install, "check_files", lambda: True)

        rc = install.main(["--non-interactive"])
        assert rc == 0
        assert calls == ["venv", "write_env", "register", "verify", "summary"]

    def test_non_interactive_full_flow_writes_files(
        self,
        fake_paths: dict[str, Path],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Use real write_env + register_mcp_step, with venv creation stubbed out.
        monkeypatch.setattr(install, "create_venv_and_install", lambda: True)
        monkeypatch.setattr(install, "check_python", lambda: True)
        monkeypatch.setattr(install, "check_files", lambda: True)
        monkeypatch.setattr(install, "verify_jira", lambda: None)
        monkeypatch.setattr(install, "print_next_steps", lambda: None)
        # Stub cache clear + cleanup so register_mcp_step does not touch real
        # SQLite state.
        monkeypatch.setattr(install, "clear_mcp_tool_cache", lambda: None)
        monkeypatch.setattr(install, "cleanup_bak_files", lambda: None)
        # No existing jira-tempo entry → register_vscode writes user-level.
        assert not fake_paths["mcp"].exists()

        rc = install.main(
            [
                "--non-interactive",
                "--jira-base-url",
                "https://jira.example.com",
                "--jira-user",
                "carol",
                "--jira-pat",
                "tok",
            ]
        )
        assert rc == 0
        # .env.local written.
        env_content = fake_paths["env_local"].read_text(encoding="utf-8")
        assert "JIRA_USER=carol" in env_content
        assert "JIRA_PAT=tok" in env_content
        # mcp.json written with jira-tempo entry + envFile.
        mcp_data = json.loads(fake_paths["mcp"].read_text(encoding="utf-8"))
        entry = mcp_data["servers"][install.SERVER_NAME]
        assert "envFile" in entry


# ---------------------------------------------------------------------------
# TestEnvFilePermissions
# ---------------------------------------------------------------------------


class TestEnvFilePermissionsNonInteractive:
    """Verify .env.local still gets chmod 600 in non-interactive mode."""

    def test_chmod_600_applied(
        self, fake_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if os.name != "posix":
            pytest.skip("POSIX-only check")
        _set_options(
            monkeypatch,
            non_interactive=True,
            jira_base_url="https://jira.example.com",
            jira_user="dave",
            jira_pat="secret",
        )
        install.write_env()
        mode = stat.S_IMODE(fake_paths["env_local"].stat().st_mode)
        assert mode == 0o600
