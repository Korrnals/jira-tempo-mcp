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


# ---------- color & TTY support ----------

_IS_TTY = sys.stdout.isatty()


def _color(code: str, text: str, *, bold: bool = False) -> str:
    """Wrap text in ANSI colour codes. Honours TTY — falls back to plain text when piped."""
    if not _IS_TTY:
        return text
    prefix = "\033[1;" if bold else "\033["
    return f"{prefix}{code}m{text}\033[0m"


# Semantic colours
C_OK = "32"      # green
C_WARN = "33"    # yellow
C_ERR = "31"     # red
C_INFO = "36"    # cyan
C_MUTED = "90"   # grey
C_ACCENT = "35"  # magenta
C_HEAD = "34"    # blue


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
            print(f"  {_color(C_OK, '●' * min(len(raw.strip()), 24))} {_color(C_MUTED, f'({len(raw.strip())} chars)')}")
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


def write_env() -> bool:
    if ENV_FILE.exists():
        _ok(f".env already exists at {ENV_FILE}")
        if not _confirm("Overwrite", default=False):
            return True

    defaults = _read_env_example()
    existing = _parse_existing_env()

    _muted("Enter configuration values — press Enter to accept the default.")
    print()

    base_url = _ask(
        "Jira base URL", existing.get("JIRA_BASE_URL") or defaults.get("JIRA_BASE_URL", "")
    )
    user = _ask(
        "Jira username", existing.get("JIRA_USER") or defaults.get("JIRA_USER", "")
    )
    pat = _ask(
        "Jira Personal Access Token (PAT)",
        existing.get("JIRA_PAT", ""),
        secret=True,
    )
    tz = _ask(
        "Timezone (IANA)",
        existing.get("JIRA_TIMEZONE") or defaults.get("JIRA_TIMEZONE", "Europe/Moscow"),
    )
    log_level = _ask(
        "Log level (DEBUG/INFO/WARNING/ERROR)",
        existing.get("LOG_LEVEL") or defaults.get("LOG_LEVEL", "INFO"),
    )

    content = (
        "# Generated by jira-tempo-mcp installer\n"
        f"JIRA_BASE_URL={base_url}\n"
        f"JIRA_USER={user}\n"
        f"JIRA_PAT={pat}\n"
        f"JIRA_TIMEZONE={tz}\n"
        f"LOG_LEVEL={log_level}\n"
    )

    ENV_FILE.write_text(content, encoding="utf-8")
    # M7: chmod 0600 only works on POSIX; on Windows it's a no-op.
    if os.name == "posix":
        with contextlib.suppress(OSError):
            os.chmod(ENV_FILE, 0o600)
        _ok(f".env written (permissions: 600) — {ENV_FILE}")
    else:
        _ok(f".env written — {ENV_FILE} (restrict access manually on Windows)")
    return True


def register_vscode() -> bool:
    _info("Register MCP server in VS Code so the agent can use it.")
    _muted("This adds the 'jira-tempo' entry to ~/.config/Code/User/mcp.json.")
    print()
    if not _confirm("Register in VS Code", default=True):
        return True

    # Load current .env to fill template
    env = _parse_existing_env()
    base_url = env.get("JIRA_BASE_URL", "https://jira.example.com")
    user = env.get("JIRA_USER", "your-username")
    tz = env.get("JIRA_TIMEZONE", "Europe/Moscow")
    log_level = env.get("LOG_LEVEL", "INFO")

    # Build jira-tempo-mcp entry
    venv_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
    # PYTHONPATH points at the src/ layout so the package is importable even
    # when the spawned process bypasses the venv's site-packages (e.g. a
    # PYTHONHOME override in the VS Code/distrobox environment that skips the
    # editable-install .pth). Harmless when the .pth is processed normally.
    src_dir = str(PROJECT_ROOT / "src")
    server_entry = {
        "command": venv_python,
        "args": ["-m", "jira_tempo_mcp.server"],
        "env": {
            "JIRA_BASE_URL": base_url,
            "JIRA_USER": user,
            # Inherit PAT from user shell env (not stored in mcp.json).
            "JIRA_PAT": "${env:JIRA_PAT}",
            "JIRA_TIMEZONE": tz,
            "LOG_LEVEL": log_level,
            "PYTHONPATH": src_dir,
        },
    }

    # Read or create mcp.json — MERGE, never overwrite existing servers
    mcp_data: dict[str, Any] = {"servers": {}}
    existing_servers: list[str] = []
    if VSCODE_MCP.exists():
        try:
            mcp_data = json.loads(VSCODE_MCP.read_text(encoding="utf-8"))
            if "servers" in mcp_data and isinstance(mcp_data["servers"], dict):
                existing_servers = [k for k in mcp_data["servers"] if k != SERVER_NAME]
        except json.JSONDecodeError:
            _warn(f"{VSCODE_MCP} exists but is not valid JSON.")
            _warn("Creating backup and starting fresh (existing content saved to .bak).")
            backup = VSCODE_MCP.with_suffix(".json.bak")
            shutil.copy2(VSCODE_MCP, backup)
            _ok(f"Backup of invalid mcp.json: {backup}")
            mcp_data = {"servers": {}}
    if "servers" not in mcp_data or not isinstance(mcp_data["servers"], dict):
        mcp_data["servers"] = {}

    # Report existing servers that will be preserved
    if existing_servers:
        _ok(f"Preserving {len(existing_servers)} existing MCP server(s): {', '.join(existing_servers)}")

    # Backup before write (only if file exists and is valid)
    if VSCODE_MCP.exists():
        backup = VSCODE_MCP.with_suffix(".json.bak")
        shutil.copy2(VSCODE_MCP, backup)
        _ok(f"Backup of mcp.json: {backup}")

    # MERGE: only update our entry, preserve all others
    mcp_data["servers"][SERVER_NAME] = server_entry
    VSCODE_DIR.mkdir(parents=True, exist_ok=True)
    VSCODE_MCP.write_text(json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _ok(f"VS Code MCP config written: {VSCODE_MCP}")
    _info("Next step in VS Code: open the MCP panel and approve the 'jira-tempo' server.")
    _muted("The server will read JIRA_PAT from your shell environment (not from mcp.json).")
    return True


def verify_jira() -> bool:
    _info("Verify connectivity to Jira? (tests auth and PAT validity)")
    if not _confirm("Verify now", default=False):
        return True

    env = _parse_existing_env()
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
    _info("Make sure JIRA_PAT is exported in your shell:")
    _muted("    export JIRA_PAT='<your-token>'")
    _muted("    (or add to your ~/.bashrc / ~/.zshrc)")
    print()
    _info("Restart VS Code and approve the 'jira-tempo' MCP server in the MCP panel.")
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
    if not register_vscode():
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
        _muted("Inspect the file manually or restore from a .json.bak.")
        return True

    servers = mcp_data.get("servers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        _info(f"No '{SERVER_NAME}' entry in {VSCODE_MCP} — already clean.")
        return True

    # Backup before write (same pattern as register_vscode()).
    backup = VSCODE_MCP.with_suffix(".json.bak")
    shutil.copy2(VSCODE_MCP, backup)
    _ok(f"Backup of mcp.json: {backup}")

    del servers[SERVER_NAME]
    VSCODE_MCP.write_text(
        json.dumps(mcp_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _ok(f"Removed '{SERVER_NAME}' from {VSCODE_MCP}")
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

    _step(1, total, "Remove 'jira-tempo' from VS Code mcp.json")
    if not _remove_vscode_entry():
        _warn("VS Code entry removal failed — continuing with remaining steps.")

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
