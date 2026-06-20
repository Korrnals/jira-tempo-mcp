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
