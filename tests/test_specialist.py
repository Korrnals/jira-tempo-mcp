"""Tests for the ``install-specialist`` subcommand (``jira_tempo_mcp.specialist``).

All filesystem effects are redirected to ``tmp_path`` by monkeypatching
``Path.home`` — the real ``~/.copilot``, ``~/.claude``, ``~/.config/opencode``
directories are never touched. Package-data artefact loads are faked with
tiny byte payloads to keep the tests independent of the real integration
files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jira_tempo_mcp import specialist


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() to a tmp tree; returns the fake home."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(specialist.Path, "home", lambda: home)
    return home


@pytest.fixture
def fake_artefacts(monkeypatch: pytest.MonkeyPatch) -> dict[str, specialist.Artefact]:
    """Replace load_artefacts with tiny deterministic payloads."""
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
    return payload


# ---------------------------------------------------------------------------
# Registry / plan shaping
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_registry_contains_all_four_harnesses(self) -> None:
        names = [h.name for h in specialist.registry()]
        assert names == ["copilot", "claude", "opencode", "codex"]

    def test_codex_is_unsupported_with_note(self) -> None:
        codex = next(h for h in specialist.registry() if h.name == "codex")
        assert codex.note != ""
        assert codex.targets == ()

    def test_copilot_matches_install_py_layout(self) -> None:
        """copilot targets replicate install.py: agent -> agents/, skill +
        knowledge doc -> skills/jira-tempo-reports/ (skill renamed SKILL.md)."""
        plan = specialist.copilot_plan()
        dests = {t.artefact: t.dest for t in plan.targets}
        home = Path.home()  # not redirected here — paths are only inspected
        assert dests[specialist.AGENT_FILE_NAME] == (
            home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME
        )
        assert dests[specialist.SKILL_SOURCE_NAME] == (
            home / ".copilot" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        )
        assert dests[specialist.KNOWLEDGE_DOC_NAME] == (
            home / ".copilot" / "skills" / specialist.SKILL_DIR_NAME / specialist.KNOWLEDGE_DOC_NAME
        )

    def test_claude_is_skills_only(self) -> None:
        """No agent target at all: VS Code cross-scans the claude agents dir."""
        plan = specialist.claude_plan()
        dests = {t.artefact: t.dest for t in plan.targets}
        home = Path.home()
        assert specialist.AGENT_FILE_NAME not in dests
        assert dests[specialist.SKILL_SOURCE_NAME] == (
            home / ".claude" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        )
        assert dests[specialist.KNOWLEDGE_DOC_NAME] == (
            home
            / ".claude"
            / "skills"
            / specialist.SKILL_DIR_NAME
            / specialist.KNOWLEDGE_DOC_NAME
        )

    def test_opencode_is_skills_only(self) -> None:
        plan = specialist.opencode_plan()
        assert len(plan.targets) == 2  # skill + knowledge doc, no agent file
        for target in plan.targets:
            assert target.dest is not None
            assert target.dest.parent == (
                Path.home() / ".config" / "opencode" / "skills" / specialist.SKILL_DIR_NAME
            )


# ---------------------------------------------------------------------------
# install / remove idempotency + isolation
# ---------------------------------------------------------------------------


class TestInstallInto:
    def test_install_copilot_writes_all_three_files(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact], capsys
    ) -> None:
        plan = specialist.copilot_plan()

        assert specialist.install_into(plan, fake_artefacts) is True

        agent = fake_home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME
        skill = (
            fake_home
            / ".copilot"
            / "skills"
            / specialist.SKILL_DIR_NAME
            / specialist.SKILL_INSTALLED_NAME
        )
        knowledge = (
            fake_home / ".copilot" / "skills" / specialist.SKILL_DIR_NAME / specialist.KNOWLEDGE_DOC_NAME
        )
        assert agent.read_bytes() == b"# agent body\n"
        assert skill.read_bytes() == b"# skill body\n"
        assert knowledge.read_bytes() == b"# knowledge\n"
        out = capsys.readouterr().out
        assert "installed" in out

    def test_reinstall_is_idempotent_with_backup(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        plan = specialist.copilot_plan()
        specialist.install_into(plan, fake_artefacts)

        assert specialist.install_into(plan, fake_artefacts) is True

        backup_dir = fake_home / ".copilot" / ".backups"
        backups = list(backup_dir.glob("SKILL.md.bak.*"))
        assert len(backups) == 1  # one backup per reinstall, content preserved
        assert backups[0].read_bytes() == b"# skill body\n"
        # The harness skill dir itself stays clean — no in-tree .bak siblings.
        skill_dir = fake_home / ".copilot" / "skills" / specialist.SKILL_DIR_NAME
        assert {p.name for p in skill_dir.iterdir()} == {
            specialist.SKILL_INSTALLED_NAME,
            specialist.KNOWLEDGE_DOC_NAME,
        }

    def test_never_touches_foreign_files(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        """Other agents/skills in the harness dirs survive an install."""
        foreign_agent = fake_home / ".copilot" / "agents" / "other.agent.md"
        foreign_skill = fake_home / ".copilot" / "skills" / "other-skill" / "SKILL.md"
        foreign_agent.parent.mkdir(parents=True)
        foreign_skill.parent.mkdir(parents=True)
        foreign_agent.write_bytes(b"foreign\n")
        foreign_skill.write_bytes(b"foreign\n")

        specialist.install_into(specialist.copilot_plan(), fake_artefacts)

        assert foreign_agent.read_bytes() == b"foreign\n"
        assert foreign_skill.read_bytes() == b"foreign\n"


class TestRemoveFrom:
    def test_remove_deletes_only_jtm_files(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        specialist.install_into(specialist.copilot_plan(), fake_artefacts)
        foreign_skill = fake_home / ".copilot" / "skills" / "other-skill" / "SKILL.md"
        foreign_skill.parent.mkdir(parents=True)
        foreign_skill.write_bytes(b"foreign\n")

        assert specialist.remove_from(specialist.copilot_plan()) is True

        assert not (fake_home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME).exists()
        assert not (
            fake_home / ".copilot" / "skills" / specialist.SKILL_DIR_NAME
        ).exists() or not any(
            (fake_home / ".copilot" / "skills" / specialist.SKILL_DIR_NAME).iterdir()
        )
        assert foreign_skill.read_bytes() == b"foreign\n"

    def test_remove_is_idempotent(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact], capsys
    ) -> None:
        specialist.install_into(specialist.copilot_plan(), fake_artefacts)
        specialist.remove_from(specialist.copilot_plan())

        assert specialist.remove_from(specialist.copilot_plan()) is True

        assert "already clean" in capsys.readouterr().out

    def test_remove_skips_unsupported_harness(self, capsys) -> None:
        assert specialist.remove_from(specialist.codex_plan()) is True
        assert "skipped" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run_specialist — flags + exit codes
# ---------------------------------------------------------------------------


class TestRunSpecialist:
    def test_list_shows_support_status(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = specialist.run_specialist(["--list"])

        assert rc == 0
        out = capsys.readouterr().out
        for name in ("copilot", "claude", "opencode", "codex"):
            assert name in out
        assert "unsupported" in out  # codex must be explicit, not silent

    def test_default_installs_all_supported_and_skips_codex(
        self,
        fake_home: Path,
        fake_artefacts: dict[str, specialist.Artefact],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = specialist.run_specialist([])

        assert rc == 0
        assert (fake_home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME).exists()
        assert (
            fake_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        ).exists()
        assert (
            fake_home
            / ".config"
            / "opencode"
            / "skills"
            / specialist.SKILL_DIR_NAME
            / "SKILL.md"
        ).exists()
        out = capsys.readouterr().out
        assert "[codex]" in out and "skipped" in out

    def test_harness_flag_installs_only_selected(
        self,
        fake_home: Path,
        fake_artefacts: dict[str, specialist.Artefact],
    ) -> None:
        rc = specialist.run_specialist(["--harness", "claude"])

        assert rc == 0
        assert not (fake_home / ".claude" / "agents").exists()
        assert (
            fake_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        ).exists()

        # copilot untouched
        assert not (fake_home / ".copilot" / "agents").exists()

    def test_harness_flag_is_repeatable(
        self,
        fake_home: Path,
        fake_artefacts: dict[str, specialist.Artefact],
    ) -> None:
        rc = specialist.run_specialist(["--harness", "copilot", "--harness", "opencode"])

        assert rc == 0
        assert (fake_home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME).exists()
        assert (
            fake_home
            / ".config"
            / "opencode"
            / "skills"
            / specialist.SKILL_DIR_NAME
            / "SKILL.md"
        ).exists()
        assert not (fake_home / ".claude" / "agents").exists()

    def test_remove_uninstalls_everything(
        self,
        fake_home: Path,
        fake_artefacts: dict[str, specialist.Artefact],
    ) -> None:
        specialist.run_specialist([])

        rc = specialist.run_specialist(["--remove"])

        assert rc == 0
        assert not (fake_home / ".copilot" / "agents" / specialist.AGENT_FILE_NAME).exists()
        assert not (
            fake_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME / "SKILL.md"
        ).exists()
        skill_dir = (
            fake_home
            / ".config"
            / "opencode"
            / "skills"
            / specialist.SKILL_DIR_NAME
        )
        assert not skill_dir.exists() or not any(skill_dir.iterdir())

    def test_unknown_harness_name_exits_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            specialist.run_specialist(["--harness", "unknown-ai"])
        assert exc.value.code == 2

    def test_mutually_exclusive_flags_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            specialist.run_specialist(["--list", "--remove"])

    def test_missing_artefacts_is_blocked_error(
        self,
        fake_home: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def missing() -> dict[str, specialist.Artefact]:
            raise FileNotFoundError("integration file missing — install broken")

        monkeypatch.setattr(specialist, "load_artefacts", missing)

        rc = specialist.run_specialist([])

        assert rc == 1
        assert "error:" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# claude skills-only plan (end-to-end)
# ---------------------------------------------------------------------------


class TestClaudeSkillsOnly:
    def test_claude_plan_writes_skills_but_no_agent_file(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        plan = specialist.claude_plan()

        assert specialist.install_into(plan, fake_artefacts) is True

        skills_dir = fake_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME
        assert len(list(skills_dir.iterdir())) == 2  # SKILL.md + JTM_AGENT.md
        assert not (fake_home / ".claude" / "agents").exists()

    def test_remove_claude_purges_legacy_agent_file(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact], capsys
    ) -> None:
        """A pre-skills-only claude install left an agent file — remove purges it."""
        legacy_agent = fake_home / ".claude" / "agents" / "jtm-jira-tempo-reports.md"
        legacy_agent.parent.mkdir(parents=True)
        legacy_agent.write_bytes(b"# legacy agent\n")

        assert specialist.remove_from(specialist.claude_plan()) is True
        purged = specialist.purge_legacy_noise()

        assert purged == 1
        assert not legacy_agent.exists()
        assert "purged 1 legacy" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# backup relocation (~/.copilot/.backups/)
# ---------------------------------------------------------------------------


class TestBackupRelocation:
    def test_backup_goes_to_copilot_backups_dir(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        """Reinstall over an existing file: backup lands out-of-tree."""
        plan = specialist.claude_plan()
        specialist.install_into(plan, fake_artefacts)

        assert specialist.install_into(plan, fake_artefacts) is True

        backups = list((fake_home / ".copilot" / ".backups").glob("SKILL.md.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == b"# skill body\n"
        skills_dir = fake_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME
        assert {p.name for p in skills_dir.iterdir()} == {
            specialist.SKILL_INSTALLED_NAME,
            specialist.KNOWLEDGE_DOC_NAME,
        }

    def test_backup_preserves_original_dir(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        """Foreign files in the same dir are untouched by backup creation."""
        plan = specialist.copilot_plan()
        specialist.install_into(plan, fake_artefacts)
        foreign = fake_home / ".copilot" / "agents" / "other.agent.md"
        foreign.write_bytes(b"foreign\n")

        specialist.install_into(plan, fake_artefacts)

        assert foreign.read_bytes() == b"foreign\n"
        assert not list((fake_home / ".copilot" / "agents").glob("*.bak.*"))


# ---------------------------------------------------------------------------
# legacy purge (--remove noise cleanup)
# ---------------------------------------------------------------------------


class TestPurgeLegacyNoise:
    def test_purges_jtm_files_in_claude_agents_dir(
        self, fake_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        agents_dir = fake_home / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        jtm_agent = agents_dir / "jtm-jira-tempo-reports.md"
        jtm_agent.write_bytes(b"legacy\n")
        jtm_bak = agents_dir / "jtm-jira-tempo-reports.md.bak.20260101-000000"
        jtm_bak.write_bytes(b"legacy bak\n")
        foreign = agents_dir / "other-agent.md"
        foreign.write_bytes(b"foreign\n")

        purged = specialist.purge_legacy_noise()

        assert purged == 2
        assert not jtm_agent.exists()
        assert not jtm_bak.exists()
        assert foreign.read_bytes() == b"foreign\n"
        out = capsys.readouterr().out
        assert "purged 2 legacy file(s)" in out

    def test_purges_bak_next_to_jtm_targets(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        """In-tree .bak siblings next to current JTM targets are purged."""
        skills_dir = (
            fake_home
            / ".config"
            / "opencode"
            / "skills"
            / specialist.SKILL_DIR_NAME
        )
        skills_dir.mkdir(parents=True)
        old_bak = skills_dir / "SKILL.md.bak.20250101-000000"
        old_bak.write_bytes(b"old in-tree backup\n")
        foreign = skills_dir / "other.md.bak.20250101-000000"
        foreign.write_bytes(b"foreign backup\n")

        purged = specialist.purge_legacy_noise()

        assert purged == 1
        assert not old_bak.exists()
        assert foreign.read_bytes() == b"foreign backup\n"

    def test_purge_is_idempotent(
        self, fake_home: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        agents_dir = fake_home / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "jtm-jira-tempo-reports.md").write_bytes(b"legacy\n")

        assert specialist.purge_legacy_noise() == 1
        assert specialist.purge_legacy_noise() == 0
        assert "purged 0 legacy file(s)" in capsys.readouterr().out

    def test_double_run_no_new_files_beyond_expected(
        self, fake_home: Path, fake_artefacts: dict[str, specialist.Artefact]
    ) -> None:
        """Install + remove + remove again: no stray files, stable state."""
        specialist.run_specialist([])
        specialist.run_specialist(["--remove"])

        rc = specialist.run_specialist(["--remove"])

        assert rc == 0
        claude_skills = fake_home / ".claude" / "skills" / specialist.SKILL_DIR_NAME
        assert not claude_skills.exists() or not any(claude_skills.iterdir())
        assert len(list((fake_home / ".copilot" / ".backups").glob("*"))) == 0
        agents_dir = fake_home / ".claude" / "agents"
        assert not agents_dir.exists() or not any(
            p.name.startswith("jtm-") for p in agents_dir.iterdir()
        )
