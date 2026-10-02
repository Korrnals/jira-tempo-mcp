"""Tests for the ``update`` self-update subcommand (``jira_tempo_mcp.selfupdate``).

Covers install-mode detection (editable / wheel / not-installed) with
``monkeypatch`` over ``importlib.metadata.distribution`` — no real
environment state is touched. Command execution paths are exercised with
monkeypatched ``subprocess.run``, verifying argument shaping
(``sys.executable -m pip``, ``git -C <root> pull --ff-only``) and failure
semantics (first failing command aborts the plan).
"""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import Distribution, PackageNotFoundError
from pathlib import Path

import pytest

from jira_tempo_mcp import selfupdate


class _FakeDist:
    """Minimal stand-in for ``importlib.metadata.Distribution``."""

    def __init__(self, direct_url: str | None) -> None:
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        if filename == "direct_url.json":
            return self._direct_url
        return None


def _patch_dist(
    monkeypatch: pytest.MonkeyPatch,
    direct_url: str | None,
    version: str = "0.5.0",
) -> None:
    """Patch ``_distribution`` and ``_version`` to a fake distribution."""

    def fake_distribution(name: str) -> _FakeDist:
        if name != selfupdate.DIST_NAME:
            raise PackageNotFoundError(name)
        return _FakeDist(direct_url)

    def fake_version(name: str) -> str:
        if name != selfupdate.DIST_NAME:
            raise PackageNotFoundError(name)
        return version

    monkeypatch.setattr(selfupdate, "_distribution", fake_distribution)
    monkeypatch.setattr(selfupdate, "_version", fake_version)


# ---------------------------------------------------------------------------
# detect_install_mode
# ---------------------------------------------------------------------------


class TestDetectInstallMode:
    def test_not_installed_reports_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No distribution → MODE_UNKNOWN with a clear note."""

        def missing(name: str) -> Distribution:
            raise PackageNotFoundError(name)

        monkeypatch.setattr(selfupdate, "_distribution", missing)

        mode = selfupdate.detect_install_mode()

        assert mode.kind == selfupdate.MODE_UNKNOWN
        assert "not installed via pip" in mode.note

    def test_index_install_reports_wheel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No direct_url.json → package-index install → wheel upgrade path."""
        _patch_dist(monkeypatch, direct_url=None)

        mode = selfupdate.detect_install_mode()

        assert mode.kind == selfupdate.MODE_WHEEL
        assert mode.project_root is None

    def test_editable_install_reports_editable_with_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """editable dir_info + existing local dir → MODE_EDITABLE with root."""
        url = tmp_path.resolve().as_uri()
        _patch_dist(
            monkeypatch,
            direct_url=json.dumps({"dir_info": {"editable": True}, "url": url}),
        )

        mode = selfupdate.detect_install_mode()

        assert mode.kind == selfupdate.MODE_EDITABLE
        assert mode.project_root == tmp_path.resolve()

    def test_local_non_editable_install_reports_wheel(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Local dir without editable flag → wheel upgrade from the index."""
        url = tmp_path.resolve().as_uri()
        _patch_dist(
            monkeypatch,
            direct_url=json.dumps({"dir_info": {"editable": False}, "url": url}),
        )

        mode = selfupdate.detect_install_mode()

        assert mode.kind == selfupdate.MODE_WHEEL

    def test_wheel_file_url_reports_wheel(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """file URL pointing at a *file* (not a dir) → wheel mode."""
        wheel = tmp_path / "jira_tempo_mcp-0.5.0-py3-none-any.whl"
        wheel.write_bytes(b"")
        _patch_dist(
            monkeypatch,
            direct_url=json.dumps({"url": wheel.resolve().as_uri()}),
        )

        mode = selfupdate.detect_install_mode()

        assert mode.kind == selfupdate.MODE_WHEEL

    def test_unreadable_direct_url_falls_back_to_wheel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Corrupt direct_url.json must not crash — treat as index install."""
        _patch_dist(monkeypatch, direct_url="{not json")

        mode = selfupdate.detect_install_mode()

        assert mode.kind == selfupdate.MODE_WHEEL

    def test_missing_root_fallback_uses_pyproject_parent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nonexistent direct URL root → the code-path fallback keeps the
        module's own ``parents[2]`` when ``pyproject.toml`` exists there."""
        _patch_dist(
            monkeypatch,
            direct_url=json.dumps(
                {"dir_info": {"editable": True}, "url": "file:///nonexistent/repo"}
            ),
        )
        # The real editable install lives 3 levels up from selfupdate.py.
        expected = Path(selfupdate.__file__).resolve().parents[2]

        mode = selfupdate.detect_install_mode()

        assert mode.kind == selfupdate.MODE_EDITABLE
        assert mode.project_root == expected


# ---------------------------------------------------------------------------
# build_update_plan
# ---------------------------------------------------------------------------


class TestBuildUpdatePlan:
    def test_wheel_plan_upgrades_from_index(self) -> None:
        mode = selfupdate.Mode(selfupdate.MODE_WHEEL, None, "note")

        plan = selfupdate.build_update_plan(mode)

        assert plan is not None
        assert len(plan) == 1
        assert plan[0].argv == [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            selfupdate.PROJECT_NAME,
        ]

    def test_editable_plan_pulls_then_reinstalls(self, tmp_path: Path) -> None:
        mode = selfupdate.Mode(selfupdate.MODE_EDITABLE, tmp_path, "note")

        plan = selfupdate.build_update_plan(mode)

        assert plan is not None
        assert [c.argv for c in plan] == [
            ["git", "-C", str(tmp_path), "pull", "--ff-only"],
            [sys.executable, "-m", "pip", "install", "-e", str(tmp_path)],
        ]

    def test_unknown_plan_is_none(self) -> None:
        mode = selfupdate.Mode(selfupdate.MODE_UNKNOWN, None, "note")

        assert selfupdate.build_update_plan(mode) is None


# ---------------------------------------------------------------------------
# run_update — argument shaping + failure semantics
# ---------------------------------------------------------------------------


class TestRunUpdate:
    def test_wheel_run_executes_pip_upgrade(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_dist(monkeypatch, direct_url=None)
        calls: list[list[str]] = []

        def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(selfupdate.subprocess, "run", fake_run)

        rc = selfupdate.run_update([])

        assert rc == 0
        assert calls == [[sys.executable, "-m", "pip", "install", "--upgrade", "jira-tempo-mcp"]]
        captured = capsys.readouterr()
        assert "Update complete." in captured.out

    def test_editable_run_executes_git_pull_then_pip_editable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_dist(
            monkeypatch,
            direct_url=json.dumps(
                {"dir_info": {"editable": True}, "url": tmp_path.resolve().as_uri()}
            ),
        )
        calls: list[list[str]] = []

        def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0)

        monkeypatch.setattr(selfupdate.subprocess, "run", fake_run)

        rc = selfupdate.run_update([])

        assert rc == 0
        assert len(calls) == 2
        assert calls[0][:4] == ["git", "-C", str(tmp_path.resolve()), "pull"]
        assert calls[0][4] == "--ff-only"
        assert calls[1] == [sys.executable, "-m", "pip", "install", "-e", str(tmp_path.resolve())]
        assert "Update complete." in capsys.readouterr().out

    def test_first_failed_command_aborts_remaining_plan(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """git pull fails → pip install -e . must NOT run; exit 1."""
        _patch_dist(
            monkeypatch,
            direct_url=json.dumps(
                {"dir_info": {"editable": True}, "url": tmp_path.resolve().as_uri()}
            ),
        )
        calls: list[list[str]] = []

        def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append(argv)
            code = 1 if argv[0] == "git" else 0
            return subprocess.CompletedProcess(argv, code)

        monkeypatch.setattr(selfupdate.subprocess, "run", fake_run)

        rc = selfupdate.run_update([])

        assert rc == 1
        assert len(calls) == 1  # pip step never reached
        captured = capsys.readouterr()
        assert "Update aborted" in captured.err

    def test_oserror_reports_blocked_not_crash(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_dist(monkeypatch, direct_url=None)

        def exploding_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            raise FileNotFoundError("no such executable")

        monkeypatch.setattr(selfupdate.subprocess, "run", exploding_run)

        rc = selfupdate.run_update([])

        assert rc == 1
        assert "Could not execute" in capsys.readouterr().err

    def test_unknown_mode_prints_guidance_and_exits_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def missing(name: str) -> Distribution:
            raise PackageNotFoundError(name)

        monkeypatch.setattr(selfupdate, "_distribution", missing)

        rc = selfupdate.run_update([])

        assert rc == 1
        captured = capsys.readouterr()
        assert "cannot proceed" in captured.err
        assert "pip install --upgrade jira-tempo-mcp" in captured.err
        assert "ghcr.io/korrnals/jira-tempo-mcp:latest" in captured.err

    def test_version_change_is_reported(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Post-update version bump is printed (restart hint included)."""
        _patch_dist(monkeypatch, direct_url=None, version="0.5.0")
        versions = iter(["0.5.0", "0.6.0"])
        monkeypatch.setattr(
            selfupdate,
            "_version",
            lambda name: next(versions),  # noqa: ARG005
        )
        monkeypatch.setattr(
            selfupdate.subprocess,
            "run",
            lambda argv, **_kw: subprocess.CompletedProcess(argv, 0),
        )

        rc = selfupdate.run_update([])

        assert rc == 0
        captured = capsys.readouterr()
        assert "0.5.0 -> 0.6.0" in captured.out
        assert "restart" in captured.out
