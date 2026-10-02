"""Wheel-mode installer/uninstaller for jira-tempo-mcp.

Driven by ``jira-tempo-mcp install`` / ``jira-tempo-mcp uninstall`` when the
package is NOT running from a git clone (the repo-root ``install.py`` is not
reachable — the typical ``pip install jira-tempo-mcp`` case). The editable /
git-clone flow keeps using ``install.py`` unchanged (see
:mod:`jira_tempo_mcp.cli` dispatch).

What this module does (wheel flow):

1. Collect settings (JIRA_BASE_URL, JIRA_USER, JIRA_PAT, JIRA_TIMEZONE,
   LOG_LEVEL) with the priority CLI flag → env var → existing VS Code
   ``.env.local`` value → interactive prompt with default. In
   ``--non-interactive`` mode prompts are skipped and missing REQUIRED
   variables exit 1 with a clear message.
2. Write/merge the VS Code user-level ``.env.local`` (managed keys
   overwritten, foreign keys preserved, chmod 600 on POSIX). Key names
   added/updated are printed — never values.
3. Register the ``jira-tempo`` server in the user-level ``mcp.json``
   (timestamped backup first; other entries preserved). The entry points at
   the running interpreter (``sys.executable -m jira_tempo_mcp.server``) with
   ``envFile`` pointing at the absolute ``.env.local`` path. If the VS Code
   user directory does not exist, registration is skipped with a note —
   not an error.
4. Install the JTM specialist into AI harnesses (delegated to
   :func:`jira_tempo_mcp.specialist.run_specialist`) unless ``--no-agent``.
5. Optional read-only connectivity check (``get_myself`` through the normal
   client config path) unless ``--skip-check`` — failures warn and never
   fail the install (Jira may be unreachable at install time).

``uninstall`` reverses 2-3 (mcp.json backup first), delegates cleanup to the
specialist, asks (default: yes) whether to drop the managed JIRA_* keys from
``.env.local``, and prints a hint that the pip package itself is removed via
``pip uninstall`` (never done automatically).

Secrets policy: PAT input via ``getpass`` (no echo); no secret value is ever
printed, logged, or embedded in the mcp.json entry.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

SERVER_NAME = "jira-tempo"

# Keys this installer owns inside .env.local. Everything else found in the
# file belongs to other MCP servers (github, tavily, ...) and is preserved.
MANAGED_ENV_KEYS: tuple[str, ...] = (
    "JIRA_BASE_URL",
    "JIRA_USER",
    "JIRA_PAT",
    "JIRA_TIMEZONE",
    "LOG_LEVEL",
)
REQUIRED_ENV_KEYS: tuple[str, ...] = ("JIRA_BASE_URL", "JIRA_USER", "JIRA_PAT")
OPTIONAL_ENV_DEFAULTS: dict[str, str] = {
    "JIRA_TIMEZONE": "Europe/Moscow",
    "LOG_LEVEL": "INFO",
}

# CLI flag (install option attribute) backing each managed key.
_FLAG_BY_KEY: dict[str, str] = {
    "JIRA_BASE_URL": "jira_base_url",
    "JIRA_USER": "jira_user",
    "JIRA_PAT": "jira_pat",
    "JIRA_TIMEZONE": "jira_timezone",
    "LOG_LEVEL": "log_level",
}

ENV_LOCAL_NAME = ".env.local"
MCP_JSON_NAME = "mcp.json"


# --------------------------------------------------------------------------
# Options & argument parsing (flag naming mirrors install.py where shared)
# --------------------------------------------------------------------------


@dataclass
class InstallOptions:
    """Parsed wheel-installer options (interactive + non-interactive)."""

    non_interactive: bool = False
    skip_vscode: bool = False
    no_agent: bool = False
    skip_check: bool = False
    jira_base_url: str | None = None
    jira_user: str | None = None
    jira_pat: str | None = None
    jira_timezone: str | None = None
    log_level: str | None = None


def _parse_args(argv: list[str] | None) -> InstallOptions:
    """Parse wheel-installer CLI args into :class:`InstallOptions`.

    Flags fall back to the matching env var (e.g. ``--jira-pat`` →
    ``JIRA_PAT``) so the installer can be driven entirely by environment
    variables in CI — same contract as install.py.
    """
    parser = argparse.ArgumentParser(
        prog="jira-tempo-mcp install",
        description=(
            "Configure jira-tempo-mcp for a wheel/pip install: write VS Code "
            ".env.local, register the MCP server in user mcp.json, install "
            "the specialist, optionally verify Jira connectivity."
        ),
    )
    parser.add_argument(
        "-n",
        "--non-interactive",
        "--yes",
        dest="non_interactive",
        action="store_true",
        help="Run without prompts; take values from flags / env vars / defaults.",
    )
    parser.add_argument(
        "--skip-vscode",
        action="store_true",
        help="Skip VS Code registration (only write .env.local).",
    )
    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="Skip the JTM specialist installation into AI harnesses.",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip the read-only Jira connectivity check (on by default, failure-tolerant).",
    )
    parser.add_argument("--jira-base-url", default=os.getenv("JIRA_BASE_URL"))
    parser.add_argument("--jira-user", default=os.getenv("JIRA_USER"))
    parser.add_argument("--jira-pat", default=os.getenv("JIRA_PAT"))
    parser.add_argument(
        "--jira-timezone",
        default=os.getenv("JIRA_TIMEZONE"),
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL"),
    )
    args = parser.parse_args(argv)
    return InstallOptions(
        non_interactive=args.non_interactive,
        skip_vscode=args.skip_vscode,
        no_agent=args.no_agent,
        skip_check=args.skip_check,
        jira_base_url=args.jira_base_url,
        jira_user=args.jira_user,
        jira_pat=args.jira_pat,
        jira_timezone=args.jira_timezone,
        log_level=args.log_level,
    )


# --------------------------------------------------------------------------
# Prompt provider (factored out so interactive paths are testable)
# --------------------------------------------------------------------------


class Prompter(Protocol):
    """Input provider used by the installer (interactive or not)."""

    def ask(self, label: str, default: str = "", *, secret: bool = False) -> str:
        """Ask for a value; ``secret`` inputs use getpass (no echo)."""
        ...  # pragma: no cover

    def confirm(self, msg: str, default: bool = True) -> bool:
        """Ask a yes/no question."""
        ...  # pragma: no cover


class InteractivePrompter:
    """Stdin prompter — plain ``input()`` and ``getpass`` for secrets."""

    def ask(self, label: str, default: str = "", *, secret: bool = False) -> str:
        suffix = f" [{default}]" if default else ""
        shown = f"? {label}{suffix}: "
        if secret:
            import getpass

            raw = getpass.getpass(shown)
        else:
            raw = input(shown)
        return raw.strip() or default

    def confirm(self, msg: str, default: bool = True) -> bool:
        hint = "[Y/n]" if default else "[y/N]"
        ans = input(f"? {msg} {hint}: ").strip().lower()
        if not ans:
            return default
        return ans in ("y", "yes", "д", "да")


class NonInteractivePrompter:
    """No-stdin prompter — every prompt resolves to its default."""

    def ask(self, label: str, default: str = "", *, secret: bool = False) -> str:
        return default

    def confirm(self, msg: str, default: bool = True) -> bool:
        return default


def _prompter_for(options: InstallOptions) -> Prompter:
    return NonInteractivePrompter() if options.non_interactive else InteractivePrompter()


# --------------------------------------------------------------------------
# Path resolution (same idea as install.py._vscode_user_dir, kept local)
# --------------------------------------------------------------------------


def vscode_user_dir() -> Path:
    """VS Code user settings directory per platform.

    Computed per call (not at import) and via ``Path.home()`` so tests can
    redirect the whole tree by monkeypatching ``Path.home``.
    """
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


def env_local_path() -> Path:
    """Absolute path of the VS Code user-level ``.env.local``."""
    return vscode_user_dir() / ENV_LOCAL_NAME


def mcp_json_path() -> Path:
    """Absolute path of the VS Code user-level ``mcp.json``."""
    return vscode_user_dir() / MCP_JSON_NAME


# --------------------------------------------------------------------------
# Small file helpers
# --------------------------------------------------------------------------


def _backup_file(path: Path) -> Path:
    """Create a timestamped backup ``<path>.bak.<YYYYMMDD-HHMMSS>``.

    Appends ``-1``, ``-2``, ... on same-second collisions.
    """
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{stamp}-{counter}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv-style file into ``{key: value}`` (comments ignored)."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


# --------------------------------------------------------------------------
# Settings collection
# --------------------------------------------------------------------------


def collect_settings(
    options: InstallOptions,
    existing_env: dict[str, str],
    prompter: Prompter,
) -> tuple[dict[str, str], list[str]]:
    """Resolve the managed settings dict and the list of missing REQUIRED keys.

    Priority per key: CLI flag → env var → existing ``.env.local`` value →
    prompt (with the resolved-so-far value, or the built-in default, as the
    Enter-only answer). In non-interactive mode the prompt step is skipped —
    a REQUIRED key with no source lands in the returned missing list and the
    caller exits 1; OPTIONAL keys fall back to their built-in default.
    """
    resolved: dict[str, str] = {}
    missing: list[str] = []

    for key in MANAGED_ENV_KEYS:
        # 1. CLI flag (argparse already folded the env var in as the default).
        value = getattr(options, _FLAG_BY_KEY[key], None)
        # 2. Env var (also covers env set after argument parsing).
        if not value:
            value = os.getenv(key)
        # 3. Existing .env.local value.
        if not value:
            value = existing_env.get(key)
        value = (value or "").strip()

        # 4. Interactive prompt with default. Skipped in non-interactive mode:
        # a built-in placeholder (e.g. "https://jira.example.com") must never
        # backfill a REQUIRED key there — install.py's contract is that a
        # missing required value is reported, not masked by a default.
        if not value and not options.non_interactive:
            if key in OPTIONAL_ENV_DEFAULTS:
                default = OPTIONAL_ENV_DEFAULTS[key]
            elif key == "JIRA_BASE_URL":
                default = "https://jira.example.com"
            else:
                default = ""
            prompted = prompter.ask(
                _label_for(key), default, secret=(key == "JIRA_PAT")
            ).strip()
            value = prompted or default

        if not value:
            if key in REQUIRED_ENV_KEYS:
                missing.append(key)
            elif key in OPTIONAL_ENV_DEFAULTS:
                value = OPTIONAL_ENV_DEFAULTS[key]
            else:  # pragma: no cover — defensive: MANAGED keys are covered above
                missing.append(key)

        resolved[key] = value

    return resolved, missing


def _label_for(key: str) -> str:
    labels = {
        "JIRA_BASE_URL": "Jira base URL",
        "JIRA_USER": "Jira username",
        "JIRA_PAT": "Jira Personal Access Token (PAT)",
        "JIRA_TIMEZONE": "Timezone (IANA)",
        "LOG_LEVEL": "Log level (DEBUG/INFO/WARNING/ERROR)",
    }
    return labels.get(key, key)


def _missing_required_message(missing: list[str]) -> str:
    """Clear remediation message for non-interactive missing vars (no values)."""
    bullets = "\n".join(f"  - {var}" for var in missing)
    return (
        "Non-interactive mode requires the following variables but they are "
        "missing (not set via CLI flag, env var, or an existing .env.local):\n"
        f"{bullets}\n"
        "Provide them via flags (--jira-base-url, --jira-user, --jira-pat) or "
        "env vars (JIRA_BASE_URL, JIRA_USER, JIRA_PAT), or re-run without "
        "--non-interactive for interactive setup."
    )


# --------------------------------------------------------------------------
# .env.local merge
# --------------------------------------------------------------------------


def write_env_local(
    path: Path, updates: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Merge *updates* into the user-level ``.env.local``.

    Existing keys NOT managed by this installer are preserved verbatim;
    managed keys are overwritten. The file is created with chmod 600 on
    POSIX. Prints which keys were added/updated — never their values.

    Returns ``(added_keys, updated_keys)``.
    """
    existing = parse_env_file(path)
    added = [k for k in updates if k not in existing]
    updated = [k for k in updates if k in existing and existing[k] != updates[k]]

    merged = dict(existing)
    merged.update(updates)

    lines: list[str] = [
        "# VS Code user-level env for MCP servers (NOT in VCS)",
        "# Managed by jira-tempo-mcp installer (jira-tempo section)",
        "",
        "# jira-tempo-mcp",
    ]
    for key in MANAGED_ENV_KEYS:
        if key in merged:
            lines.append(f"{key}={merged[key]}")
    lines.append("")

    other_keys = sorted(k for k in merged if k not in MANAGED_ENV_KEYS)
    if other_keys:
        lines.append("# other MCP servers")
        for key in other_keys:
            lines.append(f"{key}={merged[key]}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name == "posix":
        try:
            path.chmod(0o600)
        except OSError as exc:  # pragma: no cover — platform-specific edge
            print(f"  ! could not chmod 600 {path}: {exc}")

    for key in added:
        print(f"  + {key} added")
    for key in updated:
        print(f"  ~ {key} updated")
    print(f"  .env.local written: {path}")
    return added, updated


def remove_managed_env_keys(path: Path) -> bool:
    """Remove the managed JIRA_* keys from ``.env.local`` (foreign keys kept).

    If no content lines remain afterwards, the file is deleted. Never prints
    values. Returns True when any change was made.
    """
    existing = parse_env_file(path)
    remaining = {k: v for k, v in existing.items() if k not in MANAGED_ENV_KEYS}
    removed = [k for k in MANAGED_ENV_KEYS if k in existing]
    if not removed:
        print("  no managed JIRA_* keys found in .env.local")
        return False

    if remaining:
        lines = [f"{key}={value}" for key, value in sorted(remaining.items())]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  removed {len(removed)} managed key(s) from {path}")
    else:
        path.unlink()
        print(f"  removed {path} (no other keys remained)")
    return True


# --------------------------------------------------------------------------
# mcp.json registration / removal
# --------------------------------------------------------------------------


def _read_mcp_json(path: Path) -> dict[str, Any] | None:
    """Read and parse mcp.json; None when absent or corrupt."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def register_vscode_entry(env_local: Path, *, skip_vscode: bool = False) -> bool:
    """Register the ``jira-tempo`` server in the user-level ``mcp.json``.

    Other servers are preserved (json round-trip, indent=2). A timestamped
    backup is written next to the file first. When the VS Code user directory
    does not exist, prints a note and skips registration — that is not an
    error. Corrupt files are refused (never overwritten).
    """
    if skip_vscode:
        print("--skip-vscode: skipping VS Code registration.")
        return True

    mcp_path = mcp_json_path()
    if not vscode_user_dir().exists():
        print(f"  ! VS Code user directory not found ({vscode_user_dir()}).")
        print("    Skipping mcp.json registration — create the directory (or start")
        print("    VS Code) and re-run 'jira-tempo-mcp install' to register later.")
        return True

    entry: dict[str, Any] = {
        "command": sys.executable,
        "args": ["-m", "jira_tempo_mcp.server"],
        "envFile": str(env_local.resolve()),
    }

    data: dict[str, Any] = {"servers": {}}
    if mcp_path.exists():
        parsed = _read_mcp_json(mcp_path)
        if parsed is None:
            print(f"  ! {mcp_path} is not valid JSON — refusing to modify it.")
            print("    Fix the file manually (or restore from a backup) and re-run.")
            return False
        data = parsed
    if not isinstance(data.get("servers"), dict):
        data["servers"] = {}

    if mcp_path.exists():
        backup = _backup_file(mcp_path)
        print(f"  backup: {backup.name}")

    data["servers"][SERVER_NAME] = entry
    mcp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"  registered '{SERVER_NAME}' in {mcp_path}")
    return True


def remove_vscode_entry() -> bool:
    """Remove the ``jira-tempo`` entry from the user-level ``mcp.json``.

    A timestamped backup is written before the rewrite; other servers are
    preserved. Corrupt files are left untouched. Returns True when no error
    occurred (an absent file is a no-op, not an error).
    """
    mcp_path = mcp_json_path()
    if not mcp_path.exists():
        print(f"  no {mcp_path} — nothing to remove.")
        return True

    parsed = _read_mcp_json(mcp_path)
    if parsed is None:
        print(f"  ! {mcp_path} is not valid JSON — leaving it untouched.")
        return False
    servers = parsed.get("servers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        print(f"  no '{SERVER_NAME}' entry in {mcp_path} — already clean.")
        return True

    backup = _backup_file(mcp_path)
    del servers[SERVER_NAME]
    mcp_path.write_text(
        json.dumps(parsed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"  removed '{SERVER_NAME}' from {mcp_path} (backup: {backup.name})")
    return True


# --------------------------------------------------------------------------
# Connectivity check (read-only, failure-tolerant)
# --------------------------------------------------------------------------


def check_connectivity(settings: dict[str, str]) -> str | None:
    """Best-effort ``get_myself`` through the normal client config path.

    Builds a :class:`~jira_tempo_mcp.config.Config` from the just-collected
    settings (the same model ``load_config()`` produces from env) and performs
    a read-only Jira ``/myself`` call. Returns the display name on success,
    ``None`` on any failure — the install itself never fails because Jira was
    unreachable at install time.
    """
    try:
        from .client import JiraTempoClient
        from .config import Config

        config = Config(
            jira_base_url=settings["JIRA_BASE_URL"],
            jira_user=settings["JIRA_USER"],
            jira_pat=settings["JIRA_PAT"],
            timezone=settings["JIRA_TIMEZONE"],
            log_level=settings["LOG_LEVEL"],
        )

        async def _whoami() -> str:
            async with JiraTempoClient(config) as client:
                data = await client.get_myself()
            if isinstance(data, dict):
                name = data.get("displayName") or data.get("name") or data.get("key")
                return str(name) if name else "unknown user"
            return "unknown user"

        return asyncio.run(_whoami())
    except Exception as exc:  # noqa: BLE001 — deliberate: install must not fail
        print(f"  ! connectivity check failed (not an error): {exc}")
        return None


# --------------------------------------------------------------------------
# Entry points (called from cli.py when install.py is not available)
# --------------------------------------------------------------------------


def install_wheel(argv: list[str] | None = None) -> int:
    """Wheel-mode ``jira-tempo-mcp install`` — configure without a git clone."""
    options = _parse_args(argv)
    prompter = _prompter_for(options)

    print("jira-tempo-mcp installer (wheel mode)")
    print()

    existing_env = parse_env_file(env_local_path())
    settings, missing = collect_settings(options, existing_env, prompter)
    if missing:
        print(_missing_required_message(missing), file=sys.stderr)
        return 1

    print("Step 1/3 — write .env.local (credentials)")
    env_local = env_local_path()
    write_env_local(env_local, settings)

    print("Step 2/3 — register MCP server in VS Code")
    if not register_vscode_entry(env_local, skip_vscode=options.skip_vscode):
        return 1

    print("Step 3/3 — install JTM specialist into AI harnesses")
    if options.no_agent:
        print("  --no-agent: skipping specialist installation.")
    else:
        from .specialist import run_specialist

        rc_specialist = run_specialist([])
        if rc_specialist != 0:
            print(
                "  ! specialist installation failed — continuing (it is optional;"
                " re-run 'jira-tempo-mcp install-specialist' later)."
            )

    if options.skip_check:
        print("Connectivity check skipped (--skip-check).")
    else:
        print("Connectivity check (read-only /myself)")
        whoami = check_connectivity(settings)
        if whoami is not None:
            print(f"  authenticated as: {whoami}")

    print()
    print("Done. Restart VS Code (not just reload window) to pick up the MCP server,")
    print("then approve the 'jira-tempo' server in the MCP panel.")
    print("To update the token later, edit the .env.local above or re-run this install.")
    return 0


def uninstall_wheel(argv: list[str] | None = None) -> int:
    """Wheel-mode ``jira-tempo-mcp uninstall`` — reverse the configuration."""
    options = _parse_args(argv)
    prompter = _prompter_for(options)

    print("jira-tempo-mcp uninstaller (wheel mode)")
    print()

    print("Step 1/3 — remove 'jira-tempo' from user mcp.json")
    remove_vscode_entry()

    print("Step 2/3 — remove the JTM specialist from AI harnesses")
    from .specialist import run_specialist

    run_specialist(["--remove"])

    print("Step 3/3 — remove managed JIRA_* keys from .env.local")
    env_local = env_local_path()
    if env_local.exists():
        if prompter.confirm("Remove managed JIRA_* keys from .env.local?", default=True):
            remove_managed_env_keys(env_local)
        else:
            print("  keeping .env.local as is.")
    else:
        print(f"  no {env_local} — nothing to remove.")

    print()
    print("Done. Restart VS Code so it picks up the removed MCP server entry.")
    print("The pip package itself is NOT removed automatically — to fully uninstall:")
    print("  pip uninstall jira-tempo-mcp")
    return 0
