"""Tests for the ``update`` self-update subcommand (``jira_tempo_mcp.selfupdate``).

Covers install-mode detection (editable / wheel / not-installed) with
``monkeypatch`` over ``importlib.metadata.distribution`` — no real
environment state is touched. Command execution paths are exercised with
monkeypatched ``subprocess.run``, verifying argument shaping
(``sys.executable -m pip``, ``git -C <root> pull --ff-only``) and failure
semantics (first failing command aborts the plan).

The post-upgrade specialist auto-refresh is tested with a fake state file
inside a monkeypatched home and faked ``load_artefacts`` — no real
harness directory is ever written.
"""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import Distribution, PackageNotFoundError
from pathlib import Path

import pytest

from jira_tempo_mcp import selfupdate, specialist


@pytest.fixture(autouse=True)
def fake_specialist_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the specialist state file + installs into a tmp home.

    Autouse for this module: every ``run_update`` test would otherwise read
    the real user state file (and, with one present, install into the real
    harness dirs).
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(specialist.Path, "home", lambda: home)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    return home


@pytest.fixture
def fake_specialist_artefacts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake specialist package-data payloads."""
    payload = {
        specialist.AGENT_FILE_NAME: specialist.Artefact(
            source_name=specialist.AGENT_FILE_NAME, content=b"# agent body\n"
        ),
        specialist.SKILL_SOURCE_NAME: specialist.Artefact(
            source_name=specialist.SKILL_SOURCE_NAME, content=b"# skill body\n"
        ),
        specialist.KNOWLEDGE_DOC_NAME: specialist.Artefact(
            source_name=specialist.KNOWLEDGE_DOC_NAME, content=b"# knowledge\n"
        ),
    }
    monkeypatch.setattr(specialist, "load_artefacts", lambda: payload)


def _write_state(home: Path, harnesses: list[str], version: str) -> Path:
    """Pre-seed a specialist state file in the fake home."""
    path = home / ".local" / "state" / "jira-tempo-mcp" / "specialist-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "harnesses": harnesses,
                "specialist_version": version,
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return path


def _read_state(home: Path) -> dict:
    path = home / ".local" / "state" / "jira-tempo-mcp" / "specialist-state.json"
    return json.loads(path.read_text(encoding="utf-8"))


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


# ---------------------------------------------------------------------------
# specialist auto-refresh after a successful upgrade
# ---------------------------------------------------------------------------


@pytest.fixture
def successful_wheel_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wheel-mode update whose pip step succeeds."""
    _patch_dist(monkeypatch, direct_url=None, version="0.6.0")
    monkeypatch.setattr(
        selfupdate.subprocess,
        "run",
        lambda argv, **_kw: subprocess.CompletedProcess(argv, 0),
    )


class TestSpecialistRefresh:
    def test_refresh_installs_recorded_harnesses_with_new_artefacts(
        self,
        fake_specialist_home: Path,
        fake_specialist_artefacts: None,
        successful_wheel_update: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_state(fake_specialist_home, ["copilot", "claude", "ghost"], "0.5.0")

        rc = selfupdate.run_update([])

        assert rc == 0
        # Known harnesses re-installed from the (new) artefact payloads...
        assert (
            fake_specialist_home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME
        ).read_bytes() == b"# agent body\n"
        assert (
            fake_specialist_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        ).read_bytes() == b"# skill body\n"
        # ...the unknown name is ignored (no such dir is invented)...
        assert not (fake_specialist_home / ".ghost").exists()
        # ...and the state file records the post-update version.
        state = _read_state(fake_specialist_home)
        assert state["specialist_version"] == "0.6.0"
        assert state["harnesses"] == ["copilot", "claude", "ghost"]
        out = capsys.readouterr().out
        assert "[copilot]" in out and "[claude]" in out
        assert "specialist refreshed: 0.5.0 -> 0.6.0" in out

    def test_missing_state_prints_single_hint_and_no_error(
        self,
        fake_specialist_home: Path,
        successful_wheel_update: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = selfupdate.run_update([])

        assert rc == 0
        out = capsys.readouterr().out
        assert "install-specialist" in out and "auto-refresh" in out
        assert "[copilot]" not in out  # nothing was installed
        assert "specialist refreshed" not in out

    def test_per_harness_failure_warns_and_update_still_succeeds(
        self,
        fake_specialist_home: Path,
        fake_specialist_artefacts: None,
        successful_wheel_update: None,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_state(fake_specialist_home, ["copilot", "claude"], "0.5.0")

        real_write = specialist._write_file

        def failing_write(target: Path, content: bytes) -> None:
            if ".claude" in str(target):
                msg = "read-only filesystem"
                raise OSError(msg)
            real_write(target, content)

        monkeypatch.setattr(specialist, "_write_file", failing_write)

        rc = selfupdate.run_update([])

        assert rc == 0  # the package did update — refresh stays best-effort
        captured = capsys.readouterr()
        assert "warned: could not write" in captured.out
        assert "[copilot]" in captured.out  # the healthy harness still refreshed
        assert "specialist refreshed: 0.5.0 -> 0.6.0" in captured.out
        assert (fake_specialist_home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME).exists()

    def test_no_version_line_when_specialist_version_unchanged(
        self,
        fake_specialist_home: Path,
        fake_specialist_artefacts: None,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _patch_dist(monkeypatch, direct_url=None, version="0.6.2")
        monkeypatch.setattr(
            selfupdate.subprocess,
            "run",
            lambda argv, **_kw: subprocess.CompletedProcess(argv, 0),
        )
        _write_state(fake_specialist_home, ["claude"], "0.6.2")

        rc = selfupdate.run_update([])

        assert rc == 0
        assert (
            fake_specialist_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        ).exists()  # artefacts re-installed even without a version bump
        assert "specialist refreshed" not in capsys.readouterr().out

    def test_state_with_only_unknown_names_is_untouched(
        self,
        fake_specialist_home: Path,
        successful_wheel_update: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_state(fake_specialist_home, ["ghost", "codex"], "0.5.0")

        rc = selfupdate.run_update([])

        assert rc == 0
        out = capsys.readouterr().out
        assert "specialist refreshed" not in out
        assert _read_state(fake_specialist_home)["specialist_version"] == "0.5.0"

    def test_refresh_never_runs_when_update_aborts(
        self,
        fake_specialist_home: Path,
        fake_specialist_artefacts: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A failing update step must not touch the specialist files."""
        _write_state(fake_specialist_home, ["claude"], "0.5.0")
        _patch_dist(
            monkeypatch,
            direct_url=json.dumps(
                {"dir_info": {"editable": True}, "url": tmp_path.resolve().as_uri()}
            ),
            version="0.5.0",
        )
        monkeypatch.setattr(
            selfupdate.subprocess,
            "run",
            lambda argv, **_kw: subprocess.CompletedProcess(argv, 1),
        )

        rc = selfupdate.run_update([])

        assert rc == 1
        assert not (
            fake_specialist_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        ).exists()
