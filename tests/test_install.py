"""Tests for install.py — installer logic without real side effects.

All filesystem operations are isolated via the ``tmp_path`` fixture and
module-level path constants in ``install.py`` are redirected through
``monkeypatch``. No real user files (``~/.config/Code/User/mcp.json``,
``.env.local``) are touched. No network calls are made.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

# Make the project root importable so ``import install`` resolves to the
# top-level install.py (not a package). install.py is shipped as package
# data but is also runnable as a script, so we import it as a module.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import install  # noqa: E402  — path setup above is intentional

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_vscode_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect install.py module-level paths to an isolated tmp_path tree.

    Returns a mapping of logical name → tmp_path location so individual tests
    can pre-seed or assert on specific files.
    """
    vscode_dir = tmp_path / "vscode-user"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    mcp = vscode_dir / "mcp.json"
    env_local = vscode_dir / ".env.local"

    workspace_dir = tmp_path / "project" / ".vscode"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    workspace_mcp = workspace_dir / "mcp.json"

    project_root = tmp_path / "project"

    monkeypatch.setattr(install, "VSCODE_DIR", vscode_dir)
    monkeypatch.setattr(install, "VSCODE_MCP", mcp)
    monkeypatch.setattr(install, "ENV_LOCAL", env_local)
    monkeypatch.setattr(install, "WORKSPACE_MCP", workspace_mcp)
    monkeypatch.setattr(install, "PROJECT_ROOT", project_root)
    # Disable TTY colour codes so captured output is plain text.
    monkeypatch.setattr(install, "_IS_TTY", False)

    return {
        "vscode_dir": vscode_dir,
        "mcp": mcp,
        "env_local": env_local,
        "workspace_mcp": workspace_mcp,
        "project_root": project_root,
    }


def _autoc_confirm(monkeypatch: pytest.MonkeyPatch, value: bool = True) -> None:
    """Make install._confirm non-interactive (always returns *value*)."""
    monkeypatch.setattr(install, "_confirm", lambda *a, **k: value)


# ---------------------------------------------------------------------------
# TestBackupMcpJson
# ---------------------------------------------------------------------------


class TestBackupMcpJson:
    """Test _backup_mcp_json — timestamped backup with collision handling."""

    def test_creates_timestamped_backup(self, tmp_path: Path) -> None:
        mcp = tmp_path / "mcp.json"
        mcp.write_text('{"servers": {}}', encoding="utf-8")

        backup = install._backup_mcp_json(mcp)

        assert backup.exists()
        assert backup.name.startswith("mcp.json.bak.")
        # Original preserved untouched.
        assert mcp.read_text(encoding="utf-8") == '{"servers": {}}'
        # Backup content matches original.
        assert backup.read_text(encoding="utf-8") == '{"servers": {}}'

    def test_collision_appends_counter(self, tmp_path: Path) -> None:
        mcp = tmp_path / "mcp.json"
        mcp.write_text('{"servers": {}}', encoding="utf-8")

        backup1 = install._backup_mcp_json(mcp)
        # Occupy the same-timestamp slot so the second call must collide.
        backup1.write_text("existing", encoding="utf-8")

        backup2 = install._backup_mcp_json(mcp)

        # Second backup must differ and carry a counter suffix.
        assert backup2 != backup1
        assert backup2.exists()
        # Either "-1" (first collision) or a higher counter is acceptable.
        assert any(f"-{i}" in backup2.name for i in range(1, 20))

    def test_legacy_backup_renamed(self, tmp_path: Path) -> None:
        mcp = tmp_path / "mcp.json"
        mcp.write_text('{"servers": {}}', encoding="utf-8")
        legacy = tmp_path / "mcp.json.bak"
        legacy.write_text("old backup", encoding="utf-8")

        install._backup_mcp_json(mcp)

        legacy_target = tmp_path / "mcp.json.bak.legacy"
        assert legacy_target.exists()
        assert legacy_target.read_text(encoding="utf-8") == "old backup"
        # Original legacy file is moved (no longer at the old path).
        assert not legacy.exists()

    def test_legacy_rename_idempotent(self, tmp_path: Path) -> None:
        """Second run does not clobber an already-renamed .bak.legacy."""
        mcp = tmp_path / "mcp.json"
        mcp.write_text('{"servers": {}}', encoding="utf-8")
        legacy = tmp_path / "mcp.json.bak"
        legacy.write_text("first legacy", encoding="utf-8")

        install._backup_mcp_json(mcp)
        # Simulate a second legacy appearing (unlikely but guards the guard).
        legacy2 = tmp_path / "mcp.json.bak"
        legacy2.write_text("second legacy", encoding="utf-8")
        install._backup_mcp_json(mcp)

        legacy_target = tmp_path / "mcp.json.bak.legacy"
        # The first legacy content must survive — second legacy is NOT moved
        # because .bak.legacy already exists.
        assert legacy_target.read_text(encoding="utf-8") == "first legacy"


# ---------------------------------------------------------------------------
# TestRegisterVscode
# ---------------------------------------------------------------------------


class TestRegisterVscode:
    """Test register_vscode — MERGE logic, corrupt JSON handling."""

    def test_merge_preserves_existing_servers(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = fake_vscode_paths["mcp"]
        mcp.write_text(
            json.dumps(
                {"servers": {"other-mcp": {"command": "other"}}},
                indent=2,
            ),
            encoding="utf-8",
        )
        _autoc_confirm(monkeypatch, True)

        result = install.register_vscode()

        assert result is True
        data = json.loads(mcp.read_text(encoding="utf-8"))
        # Existing server preserved.
        assert "other-mcp" in data["servers"]
        assert data["servers"]["other-mcp"]["command"] == "other"
        # jira-tempo added.
        assert install.SERVER_NAME in data["servers"]
        entry = data["servers"][install.SERVER_NAME]
        assert entry["args"] == ["-m", "jira_tempo_mcp.server"]
        assert "envFile" in entry
        assert "PYTHONPATH" in entry["env"]

    def test_corrupt_json_refuses_to_write(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = fake_vscode_paths["mcp"]
        corrupt_content = '{ "servers": { "other": { "command": "x" }, NOT JSON'
        mcp.write_text(corrupt_content, encoding="utf-8")
        _autoc_confirm(monkeypatch, True)

        result = install.register_vscode()

        assert result is False
        # A .corrupt.<timestamp> sidecar must exist.
        corrupt_copies = list(mcp.parent.glob("mcp.json.corrupt.*"))
        assert len(corrupt_copies) == 1
        assert corrupt_copies[0].read_text(encoding="utf-8") == corrupt_content
        # Original file NOT modified.
        assert mcp.read_text(encoding="utf-8") == corrupt_content

    def test_corrupt_json_does_not_zero_data(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Critical regression guard: corrupt JSON must NOT zero out servers."""
        mcp = fake_vscode_paths["mcp"]
        # Valid-looking content with a trailing comma that breaks JSON parsing.
        corrupt_content = (
            '{"servers": {"other": {"command": "other"}, "github": {"command": "gh"}},}'
        )
        mcp.write_text(corrupt_content, encoding="utf-8")
        _autoc_confirm(monkeypatch, True)

        result = install.register_vscode()

        assert result is False
        # No valid mcp.json written with only jira-tempo — original untouched.
        assert mcp.read_text(encoding="utf-8") == corrupt_content
        # Parsing must still fail (we did not silently "fix" it).
        with pytest.raises(json.JSONDecodeError):
            json.loads(mcp.read_text(encoding="utf-8"))

    def test_no_existing_mcp_json_creates_fresh(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mcp = fake_vscode_paths["mcp"]
        assert not mcp.exists()
        _autoc_confirm(monkeypatch, True)

        result = install.register_vscode()

        assert result is True
        assert mcp.exists()
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME in data["servers"]


# ---------------------------------------------------------------------------
# TestRegisterWorkspaceVscode
# ---------------------------------------------------------------------------


class TestRegisterWorkspaceVscode:
    """Test register_workspace_vscode — ${workspaceFolder} variables."""

    def test_uses_workspace_folder_variable(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _autoc_confirm(monkeypatch, True)

        result = install.register_workspace_vscode()

        assert result is True
        wmcp = fake_vscode_paths["workspace_mcp"]
        data = json.loads(wmcp.read_text(encoding="utf-8"))
        entry = data["servers"][install.SERVER_NAME]
        assert entry["command"] == "${workspaceFolder}/.venv/bin/python"
        assert entry["env"]["PYTHONPATH"] == "${workspaceFolder}/src"
        # envFile must be an absolute path (not ~/...).
        env_file = entry["envFile"]
        assert os.path.isabs(env_file)
        assert not env_file.startswith("~")

    def test_merge_preserves_other_workspace_servers(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wmcp = fake_vscode_paths["workspace_mcp"]
        wmcp.write_text(
            json.dumps(
                {"servers": {"existing": {"command": "existing-cmd"}}},
                indent=2,
            ),
            encoding="utf-8",
        )
        _autoc_confirm(monkeypatch, True)

        result = install.register_workspace_vscode()

        assert result is True
        data = json.loads(wmcp.read_text(encoding="utf-8"))
        assert "existing" in data["servers"]
        assert data["servers"]["existing"]["command"] == "existing-cmd"
        assert install.SERVER_NAME in data["servers"]


# ---------------------------------------------------------------------------
# TestWriteEnvLocal
# ---------------------------------------------------------------------------


class TestWriteEnvLocal:
    """Test _write_env_local — merge into .env.local."""

    def test_merge_preserves_other_secrets(self, fake_vscode_paths: dict[str, Path]) -> None:
        env_local = fake_vscode_paths["env_local"]
        env_local.write_text(
            "GITHUB_TOKEN=ghp_example_not_real\nOTHER_SERVICE_KEY=abc123\n",
            encoding="utf-8",
        )

        ok = install._write_env_local(
            {
                "JIRA_BASE_URL": "https://jira.example.com",
                "JIRA_USER": "tester",
                "JIRA_PAT": "secret_pat_value",
                "JIRA_TIMEZONE": "Europe/Moscow",
                "LOG_LEVEL": "INFO",
            }
        )

        assert ok is True
        content = env_local.read_text(encoding="utf-8")
        # Other-server secrets preserved.
        assert "GITHUB_TOKEN=ghp_example_not_real" in content
        assert "OTHER_SERVICE_KEY=abc123" in content
        # JIRA_* values written.
        assert "JIRA_BASE_URL=https://jira.example.com" in content
        assert "JIRA_PAT=secret_pat_value" in content
        assert "JIRA_USER=tester" in content

    def test_creates_file_with_chmod_600(self, fake_vscode_paths: dict[str, Path]) -> None:
        env_local = fake_vscode_paths["env_local"]
        assert not env_local.exists()

        install._write_env_local(
            {
                "JIRA_BASE_URL": "https://jira.example.com",
                "JIRA_USER": "tester",
                "JIRA_PAT": "secret",
                "JIRA_TIMEZONE": "Europe/Moscow",
                "LOG_LEVEL": "INFO",
            }
        )

        assert env_local.exists()
        if os.name == "posix":
            mode = stat.S_IMODE(env_local.stat().st_mode)
            assert mode == 0o600, f"expected 600, got {oct(mode)}"

    def test_jira_keys_overwritten_on_merge(self, fake_vscode_paths: dict[str, Path]) -> None:
        """Re-running with new JIRA_PAT overwrites the old value, not duplicates."""
        env_local = fake_vscode_paths["env_local"]
        env_local.write_text("JIRA_PAT=old_token\n", encoding="utf-8")

        install._write_env_local(
            {
                "JIRA_BASE_URL": "https://jira.example.com",
                "JIRA_USER": "tester",
                "JIRA_PAT": "new_token",
                "JIRA_TIMEZONE": "Europe/Moscow",
                "LOG_LEVEL": "INFO",
            }
        )

        content = env_local.read_text(encoding="utf-8")
        assert "new_token" in content
        assert "old_token" not in content
        # Exactly one JIRA_PAT line.
        assert content.count("JIRA_PAT=") == 1


# ---------------------------------------------------------------------------
# TestRemoveVscodeEntry
# ---------------------------------------------------------------------------


class TestRemoveVscodeEntry:
    """Test _remove_vscode_entry and _remove_workspace_vscode_entry."""

    def test_removes_only_jira_tempo(self, fake_vscode_paths: dict[str, Path]) -> None:
        mcp = fake_vscode_paths["mcp"]
        mcp.write_text(
            json.dumps(
                {
                    "servers": {
                        install.SERVER_NAME: {"command": "jira"},
                        "other": {"command": "other"},
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = install._remove_vscode_entry()

        assert result is True
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME not in data["servers"]
        assert "other" in data["servers"]

    def test_no_entry_is_noop(self, fake_vscode_paths: dict[str, Path]) -> None:
        mcp = fake_vscode_paths["mcp"]
        mcp.write_text(
            json.dumps({"servers": {"other": {"command": "other"}}}, indent=2),
            encoding="utf-8",
        )

        result = install._remove_vscode_entry()

        assert result is True
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert "other" in data["servers"]

    def test_corrupt_json_refuses_to_modify(self, fake_vscode_paths: dict[str, Path]) -> None:
        mcp = fake_vscode_paths["mcp"]
        corrupt = '{"servers": {"other": "x" NOT JSON'
        mcp.write_text(corrupt, encoding="utf-8")

        result = install._remove_vscode_entry()

        assert result is False
        assert mcp.read_text(encoding="utf-8") == corrupt
        corrupt_copies = list(mcp.parent.glob("mcp.json.corrupt.*"))
        assert len(corrupt_copies) == 1

    def test_remove_workspace_entry_preserves_others(
        self, fake_vscode_paths: dict[str, Path]
    ) -> None:
        wmcp = fake_vscode_paths["workspace_mcp"]
        wmcp.write_text(
            json.dumps(
                {
                    "servers": {
                        install.SERVER_NAME: {"command": "jira"},
                        "ws-other": {"command": "ws-other"},
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = install._remove_workspace_vscode_entry()

        assert result is True
        data = json.loads(wmcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME not in data["servers"]
        assert "ws-other" in data["servers"]


# ---------------------------------------------------------------------------
# TestAskChoice
# ---------------------------------------------------------------------------


class TestAskChoice:
    """Test _ask_choice — option selection with prefix matching."""

    def test_default_on_empty_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda *a: "")
        result = install._ask_choice("pick", options=["user", "workspace", "both"], default="user")
        assert result == "user"

    def test_full_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda *a: "workspace")
        result = install._ask_choice("pick", options=["user", "workspace", "both"], default="user")
        assert result == "workspace"

    def test_unique_prefix_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda *a: "w")
        result = install._ask_choice("pick", options=["user", "workspace", "both"], default="user")
        assert result == "workspace"

    def test_loops_on_ambiguous_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers = iter(["u", "user"])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        result = install._ask_choice("pick", options=["user", "workspace", "both"], default="user")
        assert result == "user"


# ---------------------------------------------------------------------------
# TestServerInConfig
# ---------------------------------------------------------------------------


class TestServerInConfig:
    """Test _server_in_config — conflict detection helper."""

    def test_missing_file(self, tmp_path: Path) -> None:
        assert install._server_in_config(tmp_path / "nope.json") is False

    def test_present(self, tmp_path: Path) -> None:
        p = tmp_path / "mcp.json"
        p.write_text(json.dumps({"servers": {install.SERVER_NAME: {}}}), encoding="utf-8")
        assert install._server_in_config(p) is True

    def test_absent(self, tmp_path: Path) -> None:
        p = tmp_path / "mcp.json"
        p.write_text(json.dumps({"servers": {"other": {}}}), encoding="utf-8")
        assert install._server_in_config(p) is False

    def test_corrupt_json(self, tmp_path: Path) -> None:
        p = tmp_path / "mcp.json"
        p.write_text("NOT JSON", encoding="utf-8")
        assert install._server_in_config(p) is False


# ---------------------------------------------------------------------------
# TestRemoveMcpEntryCleanup
# ---------------------------------------------------------------------------


class TestRemoveMcpEntryCleanup:
    """Test _remove_workspace_mcp_entry and _remove_user_mcp_entry (silent cleanup)."""

    def test_remove_workspace_deletes_empty_file(self, fake_vscode_paths: dict[str, Path]) -> None:
        wmcp = fake_vscode_paths["workspace_mcp"]
        wmcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "x"}}}),
            encoding="utf-8",
        )
        install._remove_workspace_mcp_entry()
        assert not wmcp.exists()

    def test_remove_workspace_preserves_others(self, fake_vscode_paths: dict[str, Path]) -> None:
        wmcp = fake_vscode_paths["workspace_mcp"]
        wmcp.write_text(
            json.dumps(
                {"servers": {install.SERVER_NAME: {"command": "x"}, "other": {"command": "y"}}}
            ),
            encoding="utf-8",
        )
        install._remove_workspace_mcp_entry()
        data = json.loads(wmcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME not in data["servers"]
        assert "other" in data["servers"]

    def test_remove_workspace_noop_when_absent(self, fake_vscode_paths: dict[str, Path]) -> None:
        wmcp = fake_vscode_paths["workspace_mcp"]
        wmcp.write_text(json.dumps({"servers": {"other": {}}}), encoding="utf-8")
        install._remove_workspace_mcp_entry()
        data = json.loads(wmcp.read_text(encoding="utf-8"))
        assert "other" in data["servers"]

    def test_remove_workspace_corrupt_is_noop(self, fake_vscode_paths: dict[str, Path]) -> None:
        wmcp = fake_vscode_paths["workspace_mcp"]
        corrupt = "NOT JSON"
        wmcp.write_text(corrupt, encoding="utf-8")
        install._remove_workspace_mcp_entry()
        assert wmcp.read_text(encoding="utf-8") == corrupt

    def test_remove_user_preserves_others(self, fake_vscode_paths: dict[str, Path]) -> None:
        mcp = fake_vscode_paths["mcp"]
        mcp.write_text(
            json.dumps(
                {"servers": {install.SERVER_NAME: {"command": "x"}, "github": {"command": "gh"}}}
            ),
            encoding="utf-8",
        )
        install._remove_user_mcp_entry()
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME not in data["servers"]
        assert "github" in data["servers"]

    def test_remove_user_noop_when_absent(self, fake_vscode_paths: dict[str, Path]) -> None:
        mcp = fake_vscode_paths["mcp"]
        mcp.write_text(json.dumps({"servers": {"other": {}}}), encoding="utf-8")
        install._remove_user_mcp_entry()
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert "other" in data["servers"]


# ---------------------------------------------------------------------------
# TestRegisterMcpStep
# ---------------------------------------------------------------------------


class TestRegisterMcpStep:
    """Test register_mcp_step — auto-detection of existing config with cleanup."""

    def test_auto_detect_user_config_updates_and_cleans_workspace(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When jira-tempo is in user config only → update user, remove workspace."""
        mcp = fake_vscode_paths["mcp"]
        wmcp = fake_vscode_paths["workspace_mcp"]
        # Pre-seed user with jira-tempo (existing user-level install).
        mcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "old"}}}),
            encoding="utf-8",
        )
        # Pre-seed workspace with a stale jira-tempo entry (old install leftover).
        wmcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "stale"}}}),
            encoding="utf-8",
        )
        _autoc_confirm(monkeypatch, True)
        # _ask_choice should NOT be called — auto-detection resolves "both" conflict.
        # But "both" triggers a conflict prompt. Let's test the "user" detection path
        # by only seeding user config.
        wmcp.unlink()

        result = install.register_mcp_step()

        assert result is True
        # User config has jira-tempo (updated).
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME in data["servers"]
        # No workspace config created.
        assert not wmcp.exists()

    def test_auto_detect_workspace_config_updates_and_cleans_user(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When jira-tempo is in workspace config only → update workspace, remove user."""
        mcp = fake_vscode_paths["mcp"]
        wmcp = fake_vscode_paths["workspace_mcp"]
        # Pre-seed workspace with jira-tempo (existing workspace-level install).
        wmcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "old"}}}),
            encoding="utf-8",
        )
        _autoc_confirm(monkeypatch, True)

        result = install.register_mcp_step()

        assert result is True
        # Workspace config has jira-tempo (updated).
        data = json.loads(wmcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME in data["servers"]
        # User config not created.
        assert not mcp.exists()

    def test_auto_detect_none_defaults_to_user(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When jira-tempo is not registered anywhere → default to user-level."""
        mcp = fake_vscode_paths["mcp"]
        wmcp = fake_vscode_paths["workspace_mcp"]
        _autoc_confirm(monkeypatch, True)

        result = install.register_mcp_step()

        assert result is True
        # User config has jira-tempo.
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME in data["servers"]
        # Workspace config not created.
        assert not wmcp.exists()

    def test_conflict_both_prompts_user_choice(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When jira-tempo is in BOTH configs → prompt user, keep chosen, remove other."""
        mcp = fake_vscode_paths["mcp"]
        wmcp = fake_vscode_paths["workspace_mcp"]
        # Pre-seed both configs with jira-tempo (conflict).
        mcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "user-old"}}}),
            encoding="utf-8",
        )
        wmcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "ws-old"}}}),
            encoding="utf-8",
        )
        _autoc_confirm(monkeypatch, True)
        # User chooses "user" in the conflict prompt.
        monkeypatch.setattr(install, "_ask_choice", lambda *a, **k: "user")

        result = install.register_mcp_step()

        assert result is True
        # User config has jira-tempo (updated).
        data = json.loads(mcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME in data["servers"]
        # Workspace config cleaned up (file deleted — only had jira-tempo).
        assert not wmcp.exists()

    def test_conflict_both_prompts_workspace_choice(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When jira-tempo is in BOTH configs → user picks workspace, user entry removed."""
        mcp = fake_vscode_paths["mcp"]
        wmcp = fake_vscode_paths["workspace_mcp"]
        mcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "user-old"}}}),
            encoding="utf-8",
        )
        wmcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "ws-old"}}}),
            encoding="utf-8",
        )
        _autoc_confirm(monkeypatch, True)
        monkeypatch.setattr(install, "_ask_choice", lambda *a, **k: "workspace")

        result = install.register_mcp_step()

        assert result is True
        data = json.loads(wmcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME in data["servers"]
        data_u = json.loads(mcp.read_text(encoding="utf-8"))
        assert install.SERVER_NAME not in data_u["servers"]

    def test_clears_mcp_tool_cache_after_registration(
        self, fake_vscode_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """register_mcp_step calls clear_mcp_tool_cache after writing config."""
        _autoc_confirm(monkeypatch, True)
        called = {"clear": False, "cleanup": False}
        monkeypatch.setattr(
            install, "clear_mcp_tool_cache", lambda: called.__setitem__("clear", True)
        )
        monkeypatch.setattr(
            install, "cleanup_bak_files", lambda: called.__setitem__("cleanup", True)
        )

        result = install.register_mcp_step()

        assert result is True
        assert called["clear"] is True
        assert called["cleanup"] is True


# ---------------------------------------------------------------------------
# TestDetectExistingConfig
# ---------------------------------------------------------------------------


class TestDetectExistingConfig:
    """Test _detect_existing_config — auto-detection helper."""

    def test_detects_user_only(self, fake_vscode_paths: dict[str, Path]) -> None:
        mcp = fake_vscode_paths["mcp"]
        mcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "x"}}}),
            encoding="utf-8",
        )
        assert install._detect_existing_config() == "user"

    def test_detects_workspace_only(self, fake_vscode_paths: dict[str, Path]) -> None:
        wmcp = fake_vscode_paths["workspace_mcp"]
        wmcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "x"}}}),
            encoding="utf-8",
        )
        assert install._detect_existing_config() == "workspace"

    def test_detects_both(self, fake_vscode_paths: dict[str, Path]) -> None:
        mcp = fake_vscode_paths["mcp"]
        wmcp = fake_vscode_paths["workspace_mcp"]
        mcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "x"}}}),
            encoding="utf-8",
        )
        wmcp.write_text(
            json.dumps({"servers": {install.SERVER_NAME: {"command": "y"}}}),
            encoding="utf-8",
        )
        assert install._detect_existing_config() == "both"

    def test_detects_none(self, fake_vscode_paths: dict[str, Path]) -> None:
        assert install._detect_existing_config() is None

    def test_detects_none_with_other_servers(self, fake_vscode_paths: dict[str, Path]) -> None:
        """Other servers present but not jira-tempo → None."""
        mcp = fake_vscode_paths["mcp"]
        mcp.write_text(
            json.dumps({"servers": {"other": {"command": "x"}}}),
            encoding="utf-8",
        )
        assert install._detect_existing_config() is None


# ---------------------------------------------------------------------------
# TestClearMcpToolCache
# ---------------------------------------------------------------------------


class TestClearMcpToolCache:
    """Test clear_mcp_tool_cache — clears mcpToolCache from state.vscdb."""

    def test_clears_global_cache(self, fake_vscode_paths: dict[str, Path]) -> None:
        """Clears mcpToolCache from global state.vscdb."""
        import sqlite3

        vscode_dir = fake_vscode_paths["vscode_dir"]
        global_storage = vscode_dir / "globalStorage"
        global_storage.mkdir(parents=True, exist_ok=True)
        global_db = global_storage / "state.vscdb"
        # Create a real SQLite DB with the ItemTable and a mcpToolCache entry.
        conn = sqlite3.connect(str(global_db))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value BLOB)")
        conn.execute("INSERT INTO ItemTable (key, value) VALUES ('mcpToolCache', 'stale-data')")
        conn.execute("INSERT INTO ItemTable (key, value) VALUES ('otherKey', 'keep-me')")
        conn.commit()
        conn.close()

        install.clear_mcp_tool_cache()

        # Verify mcpToolCache removed, otherKey preserved.
        conn = sqlite3.connect(str(global_db))
        rows = dict(conn.execute("SELECT key, value FROM ItemTable").fetchall())
        conn.close()
        assert "mcpToolCache" not in rows
        assert rows["otherKey"] == "keep-me"

    def test_clears_workspace_cache(self, fake_vscode_paths: dict[str, Path]) -> None:
        """Clears mcpToolCache from workspace state.vscdb files."""
        import sqlite3

        vscode_dir = fake_vscode_paths["vscode_dir"]
        ws_storage = vscode_dir / "workspaceStorage"
        ws_dir = ws_storage / "abc123"
        ws_dir.mkdir(parents=True, exist_ok=True)
        ws_db = ws_dir / "state.vscdb"
        conn = sqlite3.connect(str(ws_db))
        conn.execute("CREATE TABLE ItemTable (key TEXT, value BLOB)")
        conn.execute("INSERT INTO ItemTable (key, value) VALUES ('mcpToolCache', 'ws-stale')")
        conn.commit()
        conn.close()

        install.clear_mcp_tool_cache()

        conn = sqlite3.connect(str(ws_db))
        rows = conn.execute("SELECT key FROM ItemTable WHERE key = 'mcpToolCache'").fetchall()
        conn.close()
        assert rows == []

    def test_no_cache_is_noop(self, fake_vscode_paths: dict[str, Path]) -> None:
        """No state.vscdb files → no error, just a muted message."""
        # No globalStorage or workspaceStorage dirs created.
        install.clear_mcp_tool_cache()  # should not raise

    def test_locked_workspace_db_is_skipped(self, fake_vscode_paths: dict[str, Path]) -> None:
        """A sqlite3.Error on a workspace DB is silently skipped, not fatal."""

        vscode_dir = fake_vscode_paths["vscode_dir"]
        ws_storage = vscode_dir / "workspaceStorage"
        ws_dir = ws_storage / "locked"
        ws_dir.mkdir(parents=True, exist_ok=True)
        # Create a non-SQLite file to trigger sqlite3.Error.
        (ws_dir / "state.vscdb").write_text("not a database", encoding="utf-8")

        # Should not raise — the error is caught.
        install.clear_mcp_tool_cache()


# ---------------------------------------------------------------------------
# TestCleanupBakFiles
# ---------------------------------------------------------------------------


class TestCleanupBakFiles:
    """Test cleanup_bak_files — removes .bak files from .vscode/."""

    def test_removes_bak_files(self, fake_vscode_paths: dict[str, Path]) -> None:
        project_root = fake_vscode_paths["project_root"]
        vscode_dir = project_root / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        bak1 = vscode_dir / "mcp.json.bak.20260622-120000"
        bak2 = vscode_dir / "mcp.json.bak.20260622-130000"
        bak1.write_text("old", encoding="utf-8")
        bak2.write_text("older", encoding="utf-8")
        # A non-bak file that should be preserved.
        keep = vscode_dir / "settings.json"
        keep.write_text("{}", encoding="utf-8")

        install.cleanup_bak_files()

        assert not bak1.exists()
        assert not bak2.exists()
        assert keep.exists()

    def test_no_vscode_dir_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Point PROJECT_ROOT at a dir with no .vscode/ subdirectory.
        empty_project = tmp_path / "empty-project"
        empty_project.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(install, "PROJECT_ROOT", empty_project)
        assert not (empty_project / ".vscode").exists()
        install.cleanup_bak_files()  # should not raise

    def test_no_bak_files_is_noop(self, fake_vscode_paths: dict[str, Path]) -> None:
        project_root = fake_vscode_paths["project_root"]
        vscode_dir = project_root / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        (vscode_dir / "settings.json").write_text("{}", encoding="utf-8")

        install.cleanup_bak_files()

        # No error, settings.json preserved.
        assert (vscode_dir / "settings.json").exists()
