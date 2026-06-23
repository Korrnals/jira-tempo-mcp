"""Interactive installer for jira-tempo-mcp.

One-command setup:
    python install.py

Steps:
1. Verify Python >= 3.11 and project layout
2. Create .venv and install package
3. Interactively create .env from .env.example (with secret input hidden)
4. Optionally register MCP server in VS Code mcp.json
5. Optionally verify connectivity to Jira
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
SERVER_NAME = "jira-tempo"
PY_MIN = (3, 11)


def _vscode_user_dir() -> Path:
    """Detect VS Code user settings directory per platform (M5)."""
    plat = sys.platform
    if plat == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User"
    if plat == "win32":
        appdata = os.getenv("APPDATA", "")
        if appdata:
            return Path(appdata) / "Code" / "User"
        return Path.home() / "AppData" / "Roaming" / "Code" / "User"
    # Linux and other POSIX — default.
    return Path.home() / ".config" / "Code" / "User"


VSCODE_DIR = _vscode_user_dir()
VSCODE_MCP = VSCODE_DIR / "mcp.json"
ENV_LOCAL = VSCODE_DIR / ".env.local"
WORKSPACE_MCP = PROJECT_ROOT / ".vscode" / "mcp.json"


def _backup_mcp_json(path: Path) -> Path:
    """Create a timestamped backup of *path*.

    Produces ``<path>.bak.YYYYMMDD-HHMMSS``. If a backup for the same
    second already exists, appends ``-1``, ``-2``, … to avoid collisions.

    A legacy ``<path>.bak`` (without timestamp, from older script versions)
    is renamed once to ``<path>.bak.legacy`` so it is not silently overwritten.
    """
    legacy = path.with_suffix(".json.bak")
    if legacy.exists():
        renamed = path.with_suffix(".json.bak.legacy")
        if not renamed.exists():
            shutil.move(str(legacy), str(renamed))
            _muted(f"Renamed legacy backup {legacy.name} → {renamed.name}")

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f".json.bak.{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_suffix(f".json.bak.{stamp}-{counter}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


# ---------- color & TTY support ----------

_IS_TTY = sys.stdout.isatty()


def _color(code: str, text: str, *, bold: bool = False) -> str:
    """Wrap text in ANSI colour codes. Honours TTY — falls back to plain text when piped."""
    if not _IS_TTY:
        return text
    prefix = "\033[1;" if bold else "\033["
    return f"{prefix}{code}m{text}\033[0m"


# Semantic colours
C_OK = "32"  # green
C_WARN = "33"  # yellow
C_ERR = "31"  # red
C_INFO = "36"  # cyan
C_MUTED = "90"  # grey
C_ACCENT = "35"  # magenta
C_HEAD = "34"  # blue


# ---------- helpers ----------


def _ok(msg: str) -> None:
    print(f"  {_color(C_OK, '✓', bold=True)} {msg}")


def _warn(msg: str) -> None:
    print(f"  {_color(C_WARN, '!', bold=True)} {msg}")


def _err(msg: str) -> None:
    print(f"  {_color(C_ERR, '✗', bold=True)} {msg}")


def _info(msg: str) -> None:
    print(f"  {_color(C_INFO, '·')} {msg}")


def _muted(msg: str) -> None:
    print(f"  {_color(C_MUTED, msg)}")


def _step(n: int, total: int, msg: str) -> None:
    """Render a step header with a coloured box and progress."""
    bar_full = "━" * 28
    head = _color(C_HEAD, f" Step {n}/{total} ", bold=True)
    bar_left = _color(C_MUTED, bar_full)
    print()
    print(f"  {bar_left}{head}{bar_left}")
    print(f"  {_color('1', msg, bold=True)}")
    print()


def _title(text: str) -> None:
    """Print a fancy box title for the whole installer."""
    width = max(60, len(text) + 8)
    border = _color(C_ACCENT, "╔" + "═" * (width - 2) + "╗")
    bottom = _color(C_ACCENT, "╚" + "═" * (width - 2) + "╝")
    # Centre the label inside the box.
    pad_total = width - 2 - len(text)
    pad_left = pad_total // 2
    pad_right = pad_total - pad_left
    label = (
        _color(C_ACCENT, "║", bold=True)
        + " " * pad_left
        + _color("1", text, bold=True)
        + " " * pad_right
        + _color(C_ACCENT, "║", bold=True)
    )
    print()
    print(border)
    print(label)
    print(bottom)
    print()


def _ask(label: str, default: str = "", *, secret: bool = False, required: bool = True) -> str:
    """Prompt user for input with coloured label and highlighted user input echo.

    The user input is captured via input() in raw mode so we can echo it back
    in colour. Secret prompts (e.g. PAT) use getpass with no echo.
    """
    label_styled = _color(C_INFO, "?", bold=True) + " " + _color("1", label, bold=True)
    suffix = " " + _color(C_MUTED, f"[{default}]") if default else ""
    shown = f"  {label_styled}{suffix}: "

    if secret:
        import getpass

        raw = getpass.getpass(shown)
        if raw.strip():
            # Echo a masked length indicator so the user knows something was entered.
            print(
                f"  {_color(C_OK, '●' * min(len(raw.strip()), 24))} {_color(C_MUTED, f'({len(raw.strip())} chars)')}"
            )
        value = raw
    else:
        # We want to colour the user's input echo. Capture without ANSI, then re-print.
        raw = input(shown)
        if raw:
            print(f"    {_color(C_OK, '→')} {_color(C_ACCENT, raw)}")
        value = raw

    value = value.strip() or default
    if required and not value:
        _warn("(required, please enter a value)")
        return _ask(label, default, secret=secret, required=required)
    return value


def _confirm(msg: str, default: bool = True) -> bool:
    label = _color(C_INFO, "?", bold=True) + " " + msg
    suffix = " " + _color(C_MUTED, "[Y/n]" if default else "[y/N]")
    ans = input(f"  {label}{suffix}: ").strip().lower()
    if ans:
        marker = _color(C_OK, "✓ yes") if ans in ("y", "yes", "д", "да") else _color(C_WARN, "✗ no")
        print(f"    {_color(C_OK, '→')} {marker}")
    return ans in ("y", "yes", "д", "да") if ans else default


def _ask_choice(prompt: str, *, options: list[str], default: str) -> str:
    """Ask user to choose from *options*. Returns the selected option.

    Accepts the full option word or a unique prefix. Empty input returns
    *default*. Loops until a valid choice is made.
    """
    options_str = "/".join(options)
    default_idx = options.index(default)
    hint = "/".join(o.upper() if i == default_idx else o for i, o in enumerate(options))
    while True:
        resp = input(f"  {_color(C_INFO, '?', bold=True)} {prompt} [{hint}]: ").strip().lower()
        if not resp:
            return default
        if resp in options:
            return resp
        # Try unique prefix match.
        matches = [o for o in options if o.startswith(resp)]
        if len(matches) == 1:
            return matches[0]
        print(f"  Please choose one of: {options_str}")


# ---------- MCP conflict detection & cleanup ----------


def _server_in_config(path: Path) -> bool:
    """Return True if *path* exists, is valid JSON, and has a ``jira-tempo`` server."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    servers = data.get("servers")
    if not isinstance(servers, dict):
        # Some configs put servers at the top level (older format).
        return SERVER_NAME in data if isinstance(data, dict) else False
    return SERVER_NAME in servers


def _check_mcp_conflict() -> None:
    """Warn if ``jira-tempo`` is registered in BOTH user and workspace configs.

    VS Code loads both configs and overwrites one with the other repeatedly,
    so the MCP server may never start. This is a read-only warning — cleanup
    happens via ``_remove_workspace_mcp_entry`` / ``_remove_user_mcp_entry``
    once the user picks a config.
    """
    in_user = _server_in_config(VSCODE_MCP)
    in_workspace = _server_in_config(WORKSPACE_MCP)
    if in_user and in_workspace:
        _warn(f"'{SERVER_NAME}' is registered in BOTH user and workspace configs.")
        _warn(
            "VS Code will overwrite one config with the other repeatedly — the server may not start."
        )
        _muted(f"    • User:      {VSCODE_MCP}")
        _muted(f"    • Workspace: {WORKSPACE_MCP}")


def _remove_workspace_mcp_entry() -> None:
    """Silently remove ``jira-tempo`` from workspace ``.vscode/mcp.json``.

    If no other servers remain, the file is deleted entirely. Corrupt files
    are left untouched. No backup is created (this is a cleanup, not a
    destructive edit of user-authored content — the entry was auto-written
    by this installer).
    """
    if not WORKSPACE_MCP.exists():
        return
    try:
        data = json.loads(WORKSPACE_MCP.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return  # Don't touch corrupt files.
    servers = data.get("servers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        return
    del servers[SERVER_NAME]
    if not servers:
        WORKSPACE_MCP.unlink()
        _ok(f"Removed empty workspace config: {WORKSPACE_MCP}")
    else:
        data["servers"] = servers
        WORKSPACE_MCP.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _ok(f"Removed '{SERVER_NAME}' from workspace config: {WORKSPACE_MCP}")


def _remove_user_mcp_entry() -> None:
    """Silently remove ``jira-tempo`` from user-level ``mcp.json``.

    Creates a timestamped backup before writing (user-level config may contain
    entries from other MCP servers that the user authored manually). Corrupt
    files are left untouched.
    """
    if not VSCODE_MCP.exists():
        return
    try:
        data = json.loads(VSCODE_MCP.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    servers = data.get("servers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        return
    backup = _backup_mcp_json(VSCODE_MCP)
    del servers[SERVER_NAME]
    data["servers"] = servers
    VSCODE_MCP.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ok(f"Removed '{SERVER_NAME}' from user config: {VSCODE_MCP} (backup: {backup})")


def clear_mcp_tool_cache() -> None:
    """Clear mcpToolCache from VS Code state.vscdb so tools are re-discovered.

    VS Code caches MCP tool lists in state.vscdb (SQLite). When the server
    code changes but mcp.json doesn't, VS Code uses the stale cache and
    doesn't restart the server. This function clears the cache to force
    re-discovery on next VS Code start.

    Safe to call while VS Code is running — SQLite handles concurrent access.
    The change takes effect on next VS Code restart.
    """
    import sqlite3

    # Global state.vscdb
    global_db = VSCODE_DIR / "globalStorage" / "state.vscdb"

    # Find workspace state.vscdb files
    ws_storage = VSCODE_DIR / "workspaceStorage"

    cleared = 0

    # Clear global cache
    if global_db.exists():
        try:
            conn = sqlite3.connect(str(global_db))
            cursor = conn.execute("DELETE FROM ItemTable WHERE key = 'mcpToolCache'")
            if cursor.rowcount > 0:
                _ok(f"Cleared MCP tool cache from global state.vscdb ({cursor.rowcount} entries)")
                cleared += cursor.rowcount
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            _warn(f"Could not clear global MCP cache: {e}")

    # Clear workspace caches
    if ws_storage.exists():
        for ws_dir in ws_storage.iterdir():
            if not ws_dir.is_dir():
                continue
            ws_db = ws_dir / "state.vscdb"
            if not ws_db.exists():
                continue
            try:
                conn = sqlite3.connect(str(ws_db))
                cursor = conn.execute("DELETE FROM ItemTable WHERE key = 'mcpToolCache'")
                if cursor.rowcount > 0:
                    _ok(
                        f"Cleared MCP tool cache from {ws_dir.name}/state.vscdb ({cursor.rowcount} entries)"
                    )
                    cleared += cursor.rowcount
                conn.commit()
                conn.close()
            except sqlite3.Error:
                pass  # Workspace DB might be locked

    if cleared == 0:
        _muted("No stale MCP tool cache found (already clean).")
    else:
        _ok(f"Cleared {cleared} stale MCP tool cache entries total.")
        _info("VS Code will re-discover tools on next restart.")


def cleanup_bak_files() -> None:
    """Remove old mcp.json.bak.* files from .vscode/ directory."""
    vscode_dir = PROJECT_ROOT / ".vscode"
    if not vscode_dir.exists():
        return
    bak_files = list(vscode_dir.glob("mcp.json.bak.*"))
    if not bak_files:
        return
    for bak in bak_files:
        with contextlib.suppress(OSError):
            bak.unlink()
    _ok(f"Cleaned up {len(bak_files)} backup file(s) from .vscode/")


def _detect_existing_config() -> str | None:
    """Detect which config already has jira-tempo registered.

    Returns 'user', 'workspace', 'both', or None.
    """
    in_user = _server_in_config(VSCODE_MCP)
    in_workspace = _server_in_config(WORKSPACE_MCP)
    if in_user and in_workspace:
        return "both"
    if in_user:
        return "user"
    if in_workspace:
        return "workspace"
    return None


# ---------- steps ----------


def check_python() -> bool:
    v = sys.version_info
    if (v.major, v.minor) < PY_MIN:
        _err(f"Python {v.major}.{v.minor} is too old (need >= {PY_MIN[0]}.{PY_MIN[1]})")
        return False
    _ok(f"Python {v.major}.{v.minor}.{v.micro} OK")
    return True


def check_files() -> bool:
    if not (PROJECT_ROOT / "pyproject.toml").exists():
        _err("pyproject.toml not found — are you in the project root?")
        return False
    if not ENV_EXAMPLE.exists():
        _err(".env.example not found")
        return False
    _ok("Project files OK")
    return True


def create_venv_and_install() -> bool:
    venv_dir = PROJECT_ROOT / ".venv"
    if not venv_dir.exists():
        _info(f"Creating venv in {_color(C_ACCENT, str(venv_dir))}...")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True,
            )
            _ok("venv created")
        except subprocess.CalledProcessError as exc:
            _err(f"venv creation failed: {exc}")
            return False
    else:
        _ok(f"venv already exists at {_color(C_ACCENT, str(venv_dir))}")

    pip = venv_dir / "bin" / "pip"
    if not pip.exists():
        _err("pip not found in venv")
        return False

    _info("Installing package (editable, with dev deps)...")
    try:
        # Use -q for quieter output but still show progress on errors.
        result = subprocess.run(
            [str(pip), "install", "-e", ".[dev]", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Show full output on failure.
            print(result.stdout)
            print(result.stderr)
            _err(f"pip install failed (exit {result.returncode})")
            return False
        _ok("Package installed")
    except subprocess.CalledProcessError as exc:
        _err(f"pip install failed: {exc}")
        return False
    return True


def _read_env_example() -> dict[str, str]:
    """Parse .env.example into {key: default_value}."""
    out: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _parse_existing_env() -> dict[str, str]:
    """Parse existing .env if present."""
    if not ENV_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _parse_env_local() -> dict[str, str]:
    """Parse existing ~/.config/Code/User/.env.local if present."""
    if not ENV_LOCAL.exists():
        return {}
    out: dict[str, str] = {}
    for raw in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _write_env_local(updates: dict[str, str]) -> bool:
    """Merge *updates* into ~/.config/Code/User/.env.local.

    Preserves existing keys that are not in *updates* (secrets from other
    MCP servers like github, tavily, context7). Creates the file with
    chmod 0600 if it does not exist.
    """
    existing = _parse_env_local()
    existing.update(updates)

    # Rebuild file: header + sorted sections (jira-tempo first, then others)
    jira_keys = {"JIRA_BASE_URL", "JIRA_USER", "JIRA_PAT", "JIRA_TIMEZONE", "LOG_LEVEL"}
    lines: list[str] = [
        "# ~/.config/Code/User/.env.local",
        "# MCP server secrets — chmod 600, NOT in VCS",
        "# Managed by jira-tempo-mcp installer (jira-tempo section)",
        "",
        "# jira-tempo-mcp",
    ]
    for key in ["JIRA_BASE_URL", "JIRA_USER", "JIRA_PAT", "JIRA_TIMEZONE", "LOG_LEVEL"]:
        if key in existing:
            lines.append(f"{key}={existing[key]}")
    lines.append("")

    # Other keys (github, tavily, context7, etc.) — preserve as-is
    other_keys = sorted(k for k in existing if k not in jira_keys)
    if other_keys:
        lines.append("# other MCP servers")
        for key in other_keys:
            lines.append(f"{key}={existing[key]}")
        lines.append("")

    ENV_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    ENV_LOCAL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name == "posix":
        with contextlib.suppress(OSError):
            os.chmod(ENV_LOCAL, 0o600)
        _ok(f".env.local written (permissions: 600) — {ENV_LOCAL}")
    else:
        _ok(f".env.local written — {ENV_LOCAL} (restrict access manually on Windows)")
    return True


def write_env() -> bool:
    """Write Jira credentials to ~/.config/Code/User/.env.local (merged).

    If .env.local already exists, JIRA_* keys are merged in — other servers'
    secrets (github, tavily, context7) are preserved untouched.
    """
    defaults = _read_env_example()
    existing_local = _parse_env_local()
    existing_project = _parse_existing_env()

    # Prefer values from project .env (if user ran installer before),
    # then from .env.local, then from .env.example defaults.
    def _resolve(key: str, fallback_default: str = "") -> str:
        return (
            existing_project.get(key)
            or existing_local.get(key)
            or defaults.get(key, fallback_default)
        )

    has_existing_jira = any(k in existing_local for k in ("JIRA_BASE_URL", "JIRA_PAT"))
    if has_existing_jira:
        _ok(f".env.local already exists at {ENV_LOCAL}")
        _info("Existing JIRA_* values will be shown as defaults — press Enter to keep.")
        if not _confirm("Update JIRA credentials in .env.local", default=False):
            return True

    _muted("Enter configuration values — press Enter to accept the default.")
    print()

    base_url = _ask("Jira base URL", _resolve("JIRA_BASE_URL", "https://jira.example.com"))
    user = _ask("Jira username", _resolve("JIRA_USER", "your-username"))
    pat = _ask(
        "Jira Personal Access Token (PAT)",
        existing_project.get("JIRA_PAT", existing_local.get("JIRA_PAT", "")),
        secret=True,
    )
    tz = _ask("Timezone (IANA)", _resolve("JIRA_TIMEZONE", "Europe/Moscow"))
    log_level = _ask(
        "Log level (DEBUG/INFO/WARNING/ERROR)",
        _resolve("LOG_LEVEL", "INFO"),
    )

    updates = {
        "JIRA_BASE_URL": base_url,
        "JIRA_USER": user,
        "JIRA_PAT": pat,
        "JIRA_TIMEZONE": tz,
        "LOG_LEVEL": log_level,
    }
    return _write_env_local(updates)


def register_vscode() -> bool:
    _info("Register MCP server in VS Code so the agent can use it.")
    _muted(f"This adds the 'jira-tempo' entry to {VSCODE_MCP}.")
    print()
    if not _confirm("Register in VS Code", default=True):
        return True

    # Build jira-tempo-mcp entry — secrets via envFile, not inline
    venv_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
    # PYTHONPATH points at the src/ layout so the package is importable even
    # when the spawned process bypasses the venv's site-packages (e.g. a
    # PYTHONHOME override in the VS Code/distrobox environment that skips the
    # editable-install .pth). Harmless when the .pth is processed normally.
    src_dir = str(PROJECT_ROOT / "src")
    # Note: envFile uses absolute path, not `~/...`, because in sandboxed
    # environments (distrobox, containers, snap) VS Code MCP-host resolves `~/`
    # against its own root namespace, not the user's actual $HOME. An absolute
    # path is portable across host/container boundaries.
    server_entry = {
        "command": venv_python,
        "args": ["-m", "jira_tempo_mcp.server"],
        "envFile": str(ENV_LOCAL),
        "env": {
            "PYTHONPATH": src_dir,
        },
    }

    # Read or create mcp.json — MERGE on valid JSON; refuse to touch corrupt file
    mcp_data: dict[str, Any] = {"servers": {}}
    existing_servers: list[str] = []
    if VSCODE_MCP.exists():
        try:
            mcp_data = json.loads(VSCODE_MCP.read_text(encoding="utf-8"))
            if "servers" in mcp_data and isinstance(mcp_data["servers"], dict):
                existing_servers = [k for k in mcp_data["servers"] if k != SERVER_NAME]
        except json.JSONDecodeError:
            _warn(f"{VSCODE_MCP} exists but is not valid JSON.")
            corrupt = VSCODE_MCP.with_suffix(
                f".json.corrupt.{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            shutil.copy2(VSCODE_MCP, corrupt)
            _ok(f"Saved corrupt file as: {corrupt}")
            _err("Refusing to modify a corrupt mcp.json — fix it manually or restore from backup.")
            return False
    if "servers" not in mcp_data or not isinstance(mcp_data["servers"], dict):
        mcp_data["servers"] = {}

    # Report existing servers that will be preserved
    if existing_servers:
        _ok(
            f"Preserving {len(existing_servers)} existing MCP server(s): {', '.join(existing_servers)}"
        )

    # Backup before write (only if file exists and is valid)
    if VSCODE_MCP.exists():
        backup = _backup_mcp_json(VSCODE_MCP)
        _ok(f"Backup of mcp.json: {backup}")

    # MERGE: only update our entry, preserve all others
    mcp_data["servers"][SERVER_NAME] = server_entry
    VSCODE_DIR.mkdir(parents=True, exist_ok=True)
    VSCODE_MCP.write_text(
        json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ok(f"VS Code MCP config written: {VSCODE_MCP}")
    _info("Next step in VS Code: open the MCP panel and approve the 'jira-tempo' server.")
    _muted(f"The server will read JIRA_PAT from {ENV_LOCAL} (not from mcp.json).")
    return True


def register_workspace_vscode() -> bool:
    """Register the MCP server in the workspace-level .vscode/mcp.json.

    Uses VS Code ``${workspaceFolder}`` variables so the config is portable
    across machines (the venv python and src/ path resolve at project-open
    time). ``envFile`` stays an absolute path because VS Code MCP-host in
    sandboxed environments (distrobox, containers, snap) resolves ``~/``
    against its own root namespace, not the user's actual $HOME.

    Merges into the existing workspace mcp.json — other servers are preserved.
    """
    _info("Register MCP server in workspace .vscode/mcp.json (portable config).")
    _muted(f"This adds/updates the 'jira-tempo' entry in {WORKSPACE_MCP}.")
    _muted(
        "Uses ${workspaceFolder} variables — resolves automatically when VS Code opens the project."
    )
    print()
    if not _confirm("Register in workspace .vscode/mcp.json", default=True):
        return True

    # Build jira-tempo-mcp entry — ${workspaceFolder} variables for portability
    server_entry = {
        "command": "${workspaceFolder}/.venv/bin/python",
        "args": ["-m", "jira_tempo_mcp.server"],
        "envFile": str(ENV_LOCAL),
        "env": {
            "PYTHONPATH": "${workspaceFolder}/src",
        },
    }

    # Read or create workspace mcp.json — MERGE on valid JSON
    mcp_data: dict[str, Any] = {"servers": {}}
    existing_servers: list[str] = []
    if WORKSPACE_MCP.exists():
        try:
            mcp_data = json.loads(WORKSPACE_MCP.read_text(encoding="utf-8"))
            if "servers" in mcp_data and isinstance(mcp_data["servers"], dict):
                existing_servers = [k for k in mcp_data["servers"] if k != SERVER_NAME]
        except json.JSONDecodeError:
            _warn(f"{WORKSPACE_MCP} exists but is not valid JSON.")
            corrupt = WORKSPACE_MCP.with_suffix(
                f".json.corrupt.{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            shutil.copy2(WORKSPACE_MCP, corrupt)
            _ok(f"Saved corrupt file as: {corrupt}")
            _err(
                "Refusing to modify a corrupt workspace mcp.json — fix it manually or restore from backup."
            )
            return False
    if "servers" not in mcp_data or not isinstance(mcp_data["servers"], dict):
        mcp_data["servers"] = {}

    if existing_servers:
        _ok(
            f"Preserving {len(existing_servers)} existing workspace MCP server(s): "
            f"{', '.join(existing_servers)}"
        )

    if WORKSPACE_MCP.exists():
        backup = _backup_mcp_json(WORKSPACE_MCP)
        _ok(f"Backup of workspace mcp.json: {backup}")

    mcp_data["servers"][SERVER_NAME] = server_entry
    WORKSPACE_MCP.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACE_MCP.write_text(
        json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ok(f"Workspace MCP config written: {WORKSPACE_MCP}")
    _info("When you open this project in VS Code, the server uses the project venv automatically.")
    _muted(f"The server will read JIRA_PAT from {ENV_LOCAL} (absolute path, envFile).")
    return True


def verify_jira() -> bool:
    _info("Verify connectivity to Jira? (tests auth and PAT validity)")
    if not _confirm("Verify now", default=False):
        return True

    env = _parse_env_local()
    base_url = env.get("JIRA_BASE_URL", "").rstrip("/")
    pat = env.get("JIRA_PAT", "")
    if not base_url or not pat:
        _err("JIRA_BASE_URL or JIRA_PAT missing — cannot verify")
        return True

    _info(f"Calling {_color(C_ACCENT, f'{base_url}/rest/api/2/myself')} ...")
    req = urllib.request.Request(
        f"{base_url}/rest/api/2/myself",
        headers={"Authorization": f"Bearer {pat}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if isinstance(data, dict):
                username = data.get("name") or data.get("displayName") or "?"
                _ok(f"Authenticated as: {username}")
                return True
            _err("Unexpected response shape from /myself")
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            _err("401 Unauthorized — PAT is invalid or expired")
        else:
            _err(f"HTTP {exc.code}: {exc.reason}")
    except urllib.error.URLError as exc:
        _err(f"Network error: {exc.reason}")
    return True


def print_next_steps() -> None:
    print()
    print(f"  {_color(C_OK, '✓', bold=True)} {_color('1', 'Done.', bold=True)}")
    print()
    print(f"  {_color(C_HEAD, 'Next steps', bold=True)}")
    print()
    _info(f"JIRA_PAT is stored in {ENV_LOCAL} (chmod 600).")
    _muted("    Edit that file to update the token if it expires.")
    print()
    _info("MCP config written to ONE of:")
    _muted(f"    • User-level:    {VSCODE_MCP} (works across all workspaces)")
    _muted(f"    • Workspace:     {WORKSPACE_MCP} (portable with this project)")
    _info("If you need to switch, re-run: python install.py")
    print()
    _info("Restart VS Code (not just reload window) to pick up the new MCP tools.")
    _muted("    Then approve the 'jira-tempo' MCP server in the MCP panel.")
    print()
    _info("Quick check — from the project dir:")
    _muted(f"    cd {PROJECT_ROOT}")
    _muted("    source .venv/bin/activate")
    _muted("    python -m jira_tempo_mcp.server")
    _muted("    (server should start and wait for stdio input; Ctrl+C to stop)")
    print()
    _info("To regenerate the .env later, run: python install.py")
    print()


# ---------- main ----------


def register_mcp_step() -> bool:
    """Register MCP server with auto-detection of existing config.

    VS Code loads both user-level and workspace-level ``mcp.json``. If the
    same server name appears in both, VS Code overwrites one with the other
    on every reload and the server may never start.

    Auto-detection logic:
    - If jira-tempo is already in user-level config → update user-level,
      remove workspace entry.
    - If jira-tempo is already in workspace-level config → update workspace,
      remove user entry.
    - If in BOTH → conflict, ask user which to keep.
    - If not registered anywhere → default to user-level (recommended).

    Only prompts when there's a conflict (both configs) or the user
    explicitly wants to change. After writing the config, clears the MCP
    tool cache so VS Code re-discovers tools on next restart.
    """
    _info("Register MCP server in VS Code.")

    existing = _detect_existing_config()

    if existing == "user":
        # Auto-proceed with user-level, just update it.
        _muted("Found existing user-level config — updating.")
        if not register_vscode():
            return False
        _remove_workspace_mcp_entry()
    elif existing == "workspace":
        _muted("Found existing workspace-level config — updating.")
        if not register_workspace_vscode():
            return False
        _remove_user_mcp_entry()
    elif existing == "both":
        # Conflict — need user decision.
        _warn(f"'{SERVER_NAME}' is in BOTH configs — this causes VS Code conflicts.")
        _muted(f"    • User:      {VSCODE_MCP}")
        _muted(f"    • Workspace: {WORKSPACE_MCP}")
        print()
        choice = _ask_choice(
            "Which config to keep?",
            options=["user", "workspace"],
            default="user",
        )
        if choice == "user":
            if not register_vscode():
                return False
            _remove_workspace_mcp_entry()
        else:
            if not register_workspace_vscode():
                return False
            _remove_user_mcp_entry()
    else:
        # New installation — auto-use user-level (recommended).
        _muted("No existing config found — using user-level (recommended).")
        _muted("User-level config works across all workspaces.")
        if not register_vscode():
            return False
        _remove_workspace_mcp_entry()

    # Clear MCP tool cache so VS Code re-discovers tools on next restart.
    clear_mcp_tool_cache()

    # Clean up old backup files from .vscode/.
    cleanup_bak_files()

    return True


def main() -> int:
    _title("jira-tempo-mcp installer")
    if not check_python() or not check_files():
        return 1

    total = 5

    _step(1, total, "Create venv and install package")
    if not create_venv_and_install():
        return 1

    _step(2, total, "Write .env with Jira credentials")
    if not write_env():
        return 1

    _step(3, total, "Register MCP server in VS Code")
    if not register_mcp_step():
        return 1

    _step(4, total, "Verify Jira connectivity (optional)")
    verify_jira()

    _step(5, total, "Summary")
    print_next_steps()
    return 0


# ---------- uninstall ----------


def _remove_vscode_entry() -> bool:
    """Remove the 'jira-tempo' entry from VS Code mcp.json (with backup)."""
    if not VSCODE_MCP.exists():
        _info(f"No {VSCODE_MCP} found — nothing to remove.")
        return True

    try:
        mcp_data = json.loads(VSCODE_MCP.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _warn(f"{VSCODE_MCP} is not valid JSON — leaving it untouched.")
        corrupt = VSCODE_MCP.with_suffix(
            f".json.corrupt.{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(VSCODE_MCP, corrupt)
        _ok(f"Saved corrupt file as: {corrupt}")
        _err("Refusing to modify a corrupt mcp.json — fix it manually or restore from backup.")
        return False

    servers = mcp_data.get("servers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        _info(f"No '{SERVER_NAME}' entry in {VSCODE_MCP} — already clean.")
        return True

    # Backup before write (same pattern as register_vscode()).
    backup = _backup_mcp_json(VSCODE_MCP)
    _ok(f"Backup of mcp.json: {backup}")

    del servers[SERVER_NAME]
    VSCODE_MCP.write_text(
        json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ok(f"Removed '{SERVER_NAME}' from {VSCODE_MCP}")
    return True


def _remove_workspace_vscode_entry() -> bool:
    """Remove the 'jira-tempo' entry from workspace .vscode/mcp.json (with backup)."""
    if not WORKSPACE_MCP.exists():
        _info(f"No {WORKSPACE_MCP} found — nothing to remove.")
        return True

    try:
        mcp_data = json.loads(WORKSPACE_MCP.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _warn(f"{WORKSPACE_MCP} is not valid JSON — leaving it untouched.")
        corrupt = WORKSPACE_MCP.with_suffix(
            f".json.corrupt.{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(WORKSPACE_MCP, corrupt)
        _ok(f"Saved corrupt file as: {corrupt}")
        _err(
            "Refusing to modify a corrupt workspace mcp.json — fix it manually or restore from backup."
        )
        return False

    servers = mcp_data.get("servers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        _info(f"No '{SERVER_NAME}' entry in {WORKSPACE_MCP} — already clean.")
        return True

    backup = _backup_mcp_json(WORKSPACE_MCP)
    _ok(f"Backup of workspace mcp.json: {backup}")

    del servers[SERVER_NAME]
    WORKSPACE_MCP.write_text(
        json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ok(f"Removed '{SERVER_NAME}' from {WORKSPACE_MCP}")
    return True


def _delete_env() -> bool:
    """Delete .env after explicit confirmation. Never logs the PAT value."""
    if not ENV_FILE.exists():
        _info(f"No {ENV_FILE} found — nothing to delete.")
        return True

    _warn(f"{ENV_FILE} contains your JIRA_PAT (Personal Access Token).")
    _muted("Deletion is irreversible. You will need to re-run 'install' to regenerate it.")
    if not _confirm("Delete .env", default=False):
        _info("Keeping .env — no changes made.")
        return True

    try:
        ENV_FILE.unlink()
    except OSError as exc:
        _err(f"Failed to delete {ENV_FILE}: {exc}")
        return False
    _ok(f"Deleted {ENV_FILE}")
    return True


def _uninstall_pip_package() -> bool:
    """Uninstall the pip package from the project venv."""
    venv_dir = PROJECT_ROOT / ".venv"
    pip = venv_dir / "bin" / "pip"
    if not pip.exists():
        _info(f"No venv pip found at {pip} — skipping package uninstall.")
        return True

    _info("Running pip uninstall jira-tempo-mcp ...")
    try:
        result = subprocess.run(
            [str(pip), "uninstall", "-y", "jira-tempo-mcp", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        _err(f"Failed to run pip uninstall: {exc}")
        return False
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        _err(f"pip uninstall failed (exit {result.returncode})")
        return False
    _ok("pip package uninstalled from venv")
    return True


def uninstall() -> int:
    """Reverse the installation: remove VS Code entry, optionally delete .env and pip package."""
    _title("jira-tempo-mcp uninstaller")

    total = 4

    _step(1, total, "Remove 'jira-tempo' from VS Code mcp.json (user + workspace)")
    if not _remove_vscode_entry():
        _warn("User mcp.json entry removal failed — continuing with remaining steps.")
    if not _remove_workspace_vscode_entry():
        _warn("Workspace mcp.json entry removal failed — continuing with remaining steps.")

    _step(2, total, "Delete .env (optional, destructive)")
    _delete_env()

    _step(3, total, "Uninstall pip package from venv (optional)")
    _info("This removes the editable install from the project venv.")
    _info("The .venv directory itself is kept — remove it manually if desired.")
    if _confirm("Uninstall pip package", default=False):
        _uninstall_pip_package()
    else:
        _info("Keeping pip package — no changes made.")

    _step(4, total, "Summary")
    print()
    print(f"  {_color(C_OK, '✓', bold=True)} {_color('1', 'Uninstall complete.', bold=True)}")
    print()
    print(f"  {_color(C_HEAD, 'Next steps', bold=True)}")
    print()
    _info("Restart VS Code so it picks up the removed MCP server entry.")
    print()
    _info("To fully remove the project venv directory:")
    _muted(f"    rm -rf {PROJECT_ROOT / '.venv'}")
    print()
    _info("To reinstall later:")
    _muted("    jira-tempo-mcp install   (or: python install.py)")
    print()
    return 0


if __name__ == "__main__":
    # Allow `python install.py [install|uninstall]` as a convenience entrypoint.
    # When invoked via the CLI dispatcher (cli.py), sys.argv is set to
    # [install.py_path, subcommand] so this guard dispatches correctly.
    if len(sys.argv) >= 2 and sys.argv[1] == "uninstall":
        sys.exit(uninstall())
    sys.exit(main())
