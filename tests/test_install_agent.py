"""Tests for Copilot Chat agent install/uninstall in install.py.

Covers:
- ``install_copilot_agent`` skips cleanly on ``--no-agent`` / ``--skip-vscode``.
- ``install_copilot_agent`` copies the agent file, skill, and knowledge doc
  to the VS Code Copilot Chat directories when sources exist.
- ``install_copilot_agent`` warns and skips (non-blocking) when source files
  are missing — the MCP server install still proceeds.
- ``uninstall_copilot_agent`` removes only the JTM-owned files and never
  touches other agents or skills in ``~/.copilot/``.
- ``uninstall_copilot_agent`` is idempotent when nothing is installed.

No real user files are touched — ``COPILOT_AGENTS_DIR`` and
``COPILOT_SKILLS_DIR`` are redirected via ``monkeypatch`` to ``tmp_path``.
No network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the project root importable so ``import install`` resolves to the
# top-level install.py (not a package).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import install  # noqa: E402,I001  — path setup above is intentional


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_agent_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect install.py agent/skill dirs to an isolated tmp_path tree.

    Returns a mapping so tests can pre-seed or assert on specific files.
    Never touches the real ``~/.copilot/`` directories.
    """
    agents_dir = tmp_path / "agents"
    skills_dir = tmp_path / "skills"
    agents_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(install, "COPILOT_AGENTS_DIR", agents_dir)
    monkeypatch.setattr(install, "COPILOT_SKILLS_DIR", skills_dir)
    return {"agents": agents_dir, "skills": skills_dir}


def _reset_options(**overrides: object) -> None:
    """Replace the module-level ``_OPTIONS`` singleton with a fresh instance."""
    install._OPTIONS = install.InstallOptions(**overrides)


# ---------------------------------------------------------------------------
# install_copilot_agent — skip paths
# ---------------------------------------------------------------------------


def test_no_agent_flag_skips_install(
    fake_agent_paths: dict[str, Path],
) -> None:
    """``--no-agent`` short-circuits before any filesystem work."""
    _reset_options(no_agent=True)

    result = install.install_copilot_agent()

    assert result is True
    # No agent files created in the redirected agents dir.
    assert not list(fake_agent_paths["agents"].iterdir())


def test_skip_vscode_skips_agent_install(
    fake_agent_paths: dict[str, Path],
) -> None:
    """``--skip-vscode`` skips the agent (it is VS Code-specific)."""
    _reset_options(skip_vscode=True)

    result = install.install_copilot_agent()

    assert result is True
    assert not list(fake_agent_paths["agents"].iterdir())


# ---------------------------------------------------------------------------
# install_copilot_agent — copy path
# ---------------------------------------------------------------------------


def test_install_copilot_agent_copies_files(
    fake_agent_paths: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three artefacts land in the right places with the right names."""
    _reset_options()

    # Author fake source artefacts in tmp_path (never touch the real repo files).
    src_agent = tmp_path / "src_agent.md"
    src_skill = tmp_path / "src_skill.md"
    src_jtm = tmp_path / "src_jtm.md"
    src_agent.write_text("# agent body\n", encoding="utf-8")
    src_skill.write_text("# skill body\n", encoding="utf-8")
    src_jtm.write_text("# jtm knowledge\n", encoding="utf-8")
    monkeypatch.setattr(install, "REPO_AGENT_SRC", src_agent)
    monkeypatch.setattr(install, "REPO_SKILL_SRC", src_skill)
    monkeypatch.setattr(install, "REPO_JTM_AGENT_MD", src_jtm)

    result = install.install_copilot_agent()

    assert result is True

    agents_dir = fake_agent_paths["agents"]
    skills_dir = fake_agent_paths["skills"]

    # Agent file uses the canonical AGENT_FILE_NAME in the agents dir.
    agent_target = agents_dir / install.AGENT_FILE_NAME
    assert agent_target.exists()
    assert agent_target.read_text(encoding="utf-8") == "# agent body\n"

    # Skill dir holds SKILL.md (INSTALLED_SKILL_FILE_NAME) and JTM_AGENT.md
    # (JTM_AGENT_MD_NAME) — VS Code expects these names in the skills dir.
    skill_dir_target = skills_dir / install.SKILL_DIR_NAME
    skill_file_target = skill_dir_target / install.INSTALLED_SKILL_FILE_NAME
    jtm_target = skill_dir_target / install.JTM_AGENT_MD_NAME
    assert skill_file_target.exists()
    assert skill_file_target.read_text(encoding="utf-8") == "# skill body\n"
    assert jtm_target.exists()
    assert jtm_target.read_text(encoding="utf-8") == "# jtm knowledge\n"


def test_install_copilot_agent_missing_source_warns_and_skips(
    fake_agent_paths: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing source files are a warning, not a failure — install is non-blocking."""
    _reset_options()

    # Point all three sources at non-existent paths.
    missing_agent = tmp_path / "missing_agent.md"
    missing_skill = tmp_path / "missing_skill.md"
    missing_jtm = tmp_path / "missing_jtm.md"
    monkeypatch.setattr(install, "REPO_AGENT_SRC", missing_agent)
    monkeypatch.setattr(install, "REPO_SKILL_SRC", missing_skill)
    monkeypatch.setattr(install, "REPO_JTM_AGENT_MD", missing_jtm)

    result = install.install_copilot_agent()

    # Non-blocking: returns True, no files created.
    assert result is True
    assert not list(fake_agent_paths["agents"].iterdir())
    assert not list(fake_agent_paths["skills"].iterdir())


# ---------------------------------------------------------------------------
# uninstall_copilot_agent
# ---------------------------------------------------------------------------


def test_uninstall_copilot_agent_removes_only_jtm_files(
    fake_agent_paths: dict[str, Path],
) -> None:
    """Uninstall removes JTM artefacts but leaves other agents/skills intact."""
    agents_dir = fake_agent_paths["agents"]
    skills_dir = fake_agent_paths["skills"]

    # Pre-seed the agents dir with our agent AND a foreign one.
    jtm_agent_file = agents_dir / install.AGENT_FILE_NAME
    other_agent_file = agents_dir / "other-agent.agent.md"
    jtm_agent_file.write_text("# jtm agent\n", encoding="utf-8")
    other_agent_file.write_text("# other agent\n", encoding="utf-8")

    # Pre-seed the skills dir with our skill dir AND a foreign skill dir.
    jtm_skill_dir = skills_dir / install.SKILL_DIR_NAME
    jtm_skill_dir.mkdir(parents=True)
    (jtm_skill_dir / install.JTM_AGENT_MD_NAME).write_text("# jtm knowledge\n", encoding="utf-8")
    (jtm_skill_dir / install.INSTALLED_SKILL_FILE_NAME).write_text(
        "# jtm skill\n", encoding="utf-8"
    )

    other_skill_dir = skills_dir / "other-skill"
    other_skill_dir.mkdir(parents=True)
    other_skill_file = other_skill_dir / install.INSTALLED_SKILL_FILE_NAME
    other_skill_file.write_text("# other skill\n", encoding="utf-8")

    result = install.uninstall_copilot_agent()

    assert result is True

    # JTM agent removed; the foreign agent is untouched.
    assert not jtm_agent_file.exists()
    assert other_agent_file.exists(), "foreign agent must survive uninstall"

    # JTM skill dir removed entirely; foreign skill dir is untouched.
    assert not jtm_skill_dir.exists()
    assert other_skill_dir.exists(), "foreign skill dir must survive uninstall"
    assert other_skill_file.exists(), "foreign skill file must survive uninstall"


def test_uninstall_copilot_agent_idempotent_when_not_installed(
    fake_agent_paths: dict[str, Path],
) -> None:
    """Uninstall on an empty tree returns True and raises nothing."""
    result = install.uninstall_copilot_agent()

    assert result is True
    assert fake_agent_paths["agents"].exists()
    assert fake_agent_paths["skills"].exists()
