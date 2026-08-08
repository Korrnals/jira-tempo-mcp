"""Tests for the CLI dispatcher (``jira_tempo_mcp.cli``).

Covers ``_run_install_script``'s error path: when invoked outside a git clone
(wheel / Docker install), neither the package-data ``install.py`` nor the
editable-fallback ``install.py`` is present. The CLI must then print actionable
guidance (``git clone`` + ``pip install -e .``) instead of a terse
"install.py not found" message.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jira_tempo_mcp import cli


class TestRunInstallScriptGuidance:
    """Error message when ``install.py`` is absent (wheel/Docker scenario)."""

    def test_guidance_message_when_no_install_py(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Outside a git clone, the CLI returns 1 and prints actionable guidance.

        Simulates a wheel/Docker install where ``install.py`` is unreachable:
        - package-data lookup raises (no ``install.py`` shipped in the wheel);
        - the editable-fallback path points at a nonexistent location.
        """
        import importlib.resources

        def _no_package_data(*_args: object, **_kwargs: object) -> Path:
            raise ModuleNotFoundError("simulated wheel: no package-data install.py")

        monkeypatch.setattr(importlib.resources, "files", _no_package_data)
        monkeypatch.setattr(cli, "__file__", str(Path("/nonexistent/cli.py")))

        rc = cli._run_install_script("install")

        assert rc == 1
        captured = capsys.readouterr()
        # The guidance must name the precondition and the recovery recipe.
        assert "git clone" in captured.err
        assert "pip install -e ." in captured.err
        assert "jira-tempo-mcp install" in captured.err
        # The Docker alternative for users who do not need the dev setup.
        assert "ghcr.io/korrnals/jira-tempo-mcp" in captured.err

    def test_guidance_message_for_uninstall_subcommand(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The same guidance fires for 'uninstall' (shares the fallback)."""
        import importlib.resources

        def _no_package_data(*_args: object, **_kwargs: object) -> Path:
            raise ModuleNotFoundError("simulated wheel: no package-data install.py")

        monkeypatch.setattr(importlib.resources, "files", _no_package_data)
        monkeypatch.setattr(cli, "__file__", str(Path("/nonexistent/cli.py")))

        rc = cli._run_install_script("uninstall")

        assert rc == 1
        captured = capsys.readouterr()
        assert "git clone" in captured.err
