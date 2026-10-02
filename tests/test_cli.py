"""Tests for the CLI dispatcher (``jira_tempo_mcp.cli``).

Covers the ``install`` / ``uninstall`` routing (JTM-004):

- a repo checkout (editable flow) keeps driving the repo-root ``install.py``
  via runpy — unchanged behaviour;
- a wheel / pip install (install.py unreachable) routes to the built-in
  wheel-mode configurator (``jira_tempo_mcp.installer``) instead of failing
  with the old "requires a git clone" error.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from jira_tempo_mcp import cli


@pytest.fixture
def saved_argv(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Pin sys.argv and restore it after the test (dispatch mutates it)."""
    argv = ["jira-tempo-mcp", "install"]
    monkeypatch.setattr(sys, "argv", list(argv))
    return argv


class TestEditableDispatch:
    """When install.py is found, the runpy path is used — unchanged."""

    def test_found_script_runs_via_runpy(
        self,
        monkeypatch: pytest.MonkeyPatch,
        saved_argv: list[str],  # noqa: ARG002
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_script = Path("/fake/repo/install.py")
        monkeypatch.setattr(cli, "_find_install_script", lambda: fake_script)
        run_calls: list[tuple[str, str]] = []

        def fake_run_path(path: str, **_kwargs: Any) -> None:
            run_calls.append((path, sys.argv[1]))

        monkeypatch.setattr("runpy.run_path", fake_run_path)

        rc = cli._run_install_script("install")

        assert rc == 0
        assert run_calls == [(str(fake_script), "install")]

    def test_find_install_script_finds_repo_root(self) -> None:
        """In this repo checkout, the editable probe finds the real install.py."""
        found = cli._find_install_script()
        assert found is not None
        assert found.name == "install.py"
        assert found.is_file()


class TestWheelDispatch:
    """When install.py is unreachable (wheel/pip install), wheel mode runs."""

    def test_install_routes_to_wheel_installer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        saved_argv: list[str],
    ) -> None:
        monkeypatch.setattr(cli, "_find_install_script", lambda: None)
        monkeypatch.setattr(sys, "argv", ["jira-tempo-mcp", "install", "--no-agent"])
        calls: list[list[str]] = []
        monkeypatch.setattr(
            "jira_tempo_mcp.installer.install_wheel",
            lambda argv: calls.append(argv) or 0,
        )

        rc = cli._run_install_script("install")

        assert rc == 0
        assert calls == [["--no-agent"]]

    def test_uninstall_routes_to_wheel_uninstaller(
        self,
        monkeypatch: pytest.MonkeyPatch,
        saved_argv: list[str],
    ) -> None:
        monkeypatch.setattr(cli, "_find_install_script", lambda: None)
        monkeypatch.setattr(sys, "argv", ["jira-tempo-mcp", "uninstall"])
        calls: list[list[str]] = []
        monkeypatch.setattr(
            "jira_tempo_mcp.installer.uninstall_wheel",
            lambda argv: calls.append(argv) or 7,
        )

        rc = cli._run_install_script("uninstall")

        assert rc == 7
        assert calls == [[]]
