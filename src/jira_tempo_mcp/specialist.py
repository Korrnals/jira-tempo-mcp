"""``install-specialist`` subcommand: install the JTM agent into AI harnesses.

Ships the specialist artefacts inside the wheel
(``jira_tempo_mcp.integration`` package data) and installs them into AI
harnesses through a small registry of per-harness installers:

===================  ====================================================
Harness              Layout (discovered on this host, 2026-10-02)
===================  ====================================================
``copilot``          ``~/.copilot/agents/jtm-jira-tempo-reports.agent.md`` +
                     ``~/.copilot/skills/jira-tempo-reports/SKILL.md`` +
                     ``~/.copilot/skills/jira-tempo-reports/JTM_AGENT.md``
                     (mirrors ``install.py`` exactly: the knowledge doc
                     goes to the *skills* dir — ``~/.copilot/agents/`` is
                     scanned by VS Code and a stray md there would appear
                     as a second fake agent in the picker).
``zcode``            ``~/.zcode/agents/jtm-jira-tempo-reports.md`` (markdown
                     agent with frontmatter — the ``.agent.md`` artefact
                     already carries the required ``name``/``description``/
                     ``tools`` fields, so it is reused as-is, renamed to
                     ``.md``) + ``~/.zcode/skills/jira-tempo-reports/``
                     (``SKILL.md`` + ``JTM_AGENT.md``).
``claude``           ``~/.claude/skills/jira-tempo-reports/`` (``SKILL.md`` +
                     ``JTM_AGENT.md``) — skills-only, mirroring
                     ``opencode_plan()`` shape: VS Code cross-scans the
                     Claude agents dir, an extra agent file there would
                     show a duplicate picker entry.
``pi``               ``~/.pi/agent/skills/jira-tempo-reports/`` (``SKILL.md``
                     + ``JTM_AGENT.md``) — skills-only: pi has no agent-file
                     convention (it skips subagents).
``hermes``           ``~/.hermes/skills/jira-tempo-reports/`` (``SKILL.md`` +
                     ``JTM_AGENT.md``) — skills-only: hermes agents are
                     runtime delegation profiles, not markdown files.
``opencode``         ``~/.config/opencode/skills/jira-tempo-reports/``
                     (``SKILL.md`` — opencode only has a skills convention).
``codex``            UNSUPPORTED — ``~/.codex`` has no agent/skill file
                     convention readable on this host (only ``skills/.system``
                     with a system marker). Registered as skipped so the
                     message is explicit instead of a silent ``AGENTS.md``
                     append.
===================  ====================================================

Semantics:
- **Idempotent** — re-install overwrites JTM-owned files (timestamped
  backups are created first), never touches other harness files.
- **Reversible** — ``--remove`` deletes only the JTM-owned paths and
  purges legacy leftovers (JTM-named files in ``~/.claude/agents/``,
  stray ``.bak.*`` backups next to JTM files in harness dirs).
- **Refreshable** — the install path records the installed harness names
  in a state file (``$XDG_STATE_HOME`` or ``~/.local/state/`` — see
  :func:`state_path`); ``jira-tempo-mcp update`` reads it to auto-refresh
  the specialist after a package upgrade, and a successful ``--remove``
  deletes it.
- **Wheel + editable** — artefacts are read via ``importlib.resources``
  from ``jira_tempo_mcp.integration``, working in both install modes.

The existing ``install`` subcommand (``install.py``) is untouched.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

PACKAGE = "jira_tempo_mcp"
INTEGRATION_SUBPACKAGE = "integration"

AGENT_FILE_NAME = "jtm-jira-tempo-reports.agent.md"
ZCODE_AGENT_FILE_NAME = "jtm-jira-tempo-reports.md"  # zcode agent convention: plain .md
SKILL_SOURCE_NAME = "jira-tempo-reports.skill.md"  # repo consolidated name
SKILL_INSTALLED_NAME = "SKILL.md"  # harnesses expect this name
KNOWLEDGE_DOC_NAME = "JTM_AGENT.md"
SKILL_DIR_NAME = "jira-tempo-reports"


# ---------------------------------------------------------------------------
# Artefact sources (package data via importlib.resources)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artefact:
    """One integration file: its name in package data + content bytes."""

    source_name: str
    content: bytes


def load_artefacts() -> dict[str, Artefact]:
    """Read the three specialist files from package data.

    Raises ``FileNotFoundError`` if any is missing (broken install), which
    callers report as a blocked error.
    """
    artefacts: dict[str, Artefact] = {}
    names = (AGENT_FILE_NAME, SKILL_SOURCE_NAME, KNOWLEDGE_DOC_NAME)
    for name in names:
        try:
            content = (resources.files(PACKAGE) / INTEGRATION_SUBPACKAGE / name).read_bytes()
        except FileNotFoundError:
            msg = (
                f"integration file {name!r} not found in package data "
                f"({PACKAGE}.{INTEGRATION_SUBPACKAGE}) — install appears broken"
            )
            raise FileNotFoundError(msg) from None
        artefacts[name] = Artefact(source_name=name, content=content)
    return artefacts


def _write_file(target: Path, content: bytes) -> None:
    """Atomically create/overwrite target with parent dirs."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _backup(path: Path) -> Path:
    """Timestamped backup into ``~/.copilot/.backups/<name>.bak.YYYYMMDD-HHMMSS``.

    Keeps the ``.bak.<ts>`` scheme of ``install.py`` but writes into a
    dedicated out-of-tree directory: harness scan dirs (``~/.copilot/agents``,
    the skills dirs) stay clean — a stray ``.bak`` sibling there would appear
    as junk next to live files (and in the VS Code picker).
    """
    import datetime

    backup_dir = Path.home() / ".copilot" / ".backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{path.name}.bak.{stamp}"
    counter = 1
    while backup.exists():
        backup = backup_dir / f"{path.name}.bak.{stamp}-{counter}"
        counter += 1
    shutil.copy2(path, backup)
    return backup


def _overwrite(path: Path, content: bytes, label: str) -> None:
    """Overwrite with backup if exists; print the resulting path."""
    if path.exists():
        backup = _backup(path)
        print(f"  backed up existing {label} -> {backup}")
    _write_file(path, content)
    print(f"  installed {label}: {path}")


def _try_unlink(path: Path) -> bool:
    """Unlink, printing a warning on OSError. True when removed."""
    try:
        path.unlink()
        return True
    except OSError as exc:
        print(f"  warned: could not remove {path}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Installed-harness state file (drives `update` specialist auto-refresh)
# ---------------------------------------------------------------------------


def state_path() -> Path:
    """Path of the specialist state file.

    ``$XDG_STATE_HOME/jira-tempo-mcp/specialist-state.json`` when
    ``XDG_STATE_HOME`` is set, else ``~/.local/state/jira-tempo-mcp/
    specialist-state.json``.
    """
    xdg = os.getenv("XDG_STATE_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "jira-tempo-mcp" / "specialist-state.json"


def read_state() -> dict[str, Any] | None:
    """Read the state file. None when absent, unreadable or malformed.

    A malformed file is reported as a warning and treated as absent — the
    next successful install rewrites it from scratch.
    """
    path = state_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warned: specialist state file unreadable ({path}): {exc}")
        return None
    if not isinstance(data, dict):
        print(f"warned: specialist state file malformed ({path}) — ignoring")
        return None
    return data


def record_state(harnesses: list[str], version: str | None = None) -> None:
    """Write the state file for the given installed harness names.

    Idempotent: the file is overwritten (never appended to), names are
    deduplicated preserving order. ``version`` defaults to the running
    package ``__version__``; ``selfupdate`` passes the post-upgrade
    version explicitly because the running process was started under the
    OLD code and its in-memory ``__version__`` is stale.
    """
    if version is None:
        from jira_tempo_mcp import __version__  # lazy: avoid import cost at module load

        version = __version__
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "harnesses": list(dict.fromkeys(harnesses)),
        "specialist_version": version,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def delete_state() -> bool:
    """Delete the state file. True when it existed and was removed."""
    try:
        state_path().unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        print(f"warned: could not remove specialist state file {state_path()}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Harness plan (data-driven): every supported harness describes its targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """Where an artefact lands for a harness: ``artefact name -> dest path``."""

    artefact: str
    dest: Path | None  # None only for skipped harnesses


@dataclass(frozen=True)
class HarnessPlan:
    """Install layout for one harness."""

    name: str
    description: str
    targets: tuple[Target, ...]
    note: str = ""  # non-empty => not supported / install is skipped


def copilot_plan() -> HarnessPlan:
    """VS Code Copilot Chat layout — mirrors install.py exactly.

    The knowledge doc goes to the *skills* dir: ``~/.copilot/agents/`` is
    scanned by VS Code and an extra md there would surface as a second
    fake agent in the picker.
    """
    home = Path.home()
    agents = home / ".copilot" / "agents"
    skills = home / ".copilot" / "skills" / SKILL_DIR_NAME
    return HarnessPlan(
        name="copilot",
        description="VS Code Copilot Chat (agents + skills)",
        targets=(
            Target(AGENT_FILE_NAME, agents / AGENT_FILE_NAME),
            Target(SKILL_SOURCE_NAME, skills / SKILL_INSTALLED_NAME),
            Target(KNOWLEDGE_DOC_NAME, skills / KNOWLEDGE_DOC_NAME),
        ),
    )


def zcode_plan() -> HarnessPlan:
    """ZCode layout: agent file + skills directory.

    The agent lands as ``~/.zcode/agents/jtm-jira-tempo-reports.md`` —
    zcode reads plain markdown with frontmatter and the ``.agent.md``
    artefact already carries the required ``name``/``description``/
    ``tools`` fields (copilot-only extras such as ``argument-hint`` are
    ignored), so the artefact is reused unchanged. Skills follow the
    standard skills-dir convention under ``~/.zcode/skills/``.
    """
    home = Path.home()
    agents = home / ".zcode" / "agents"
    skills = home / ".zcode" / "skills" / SKILL_DIR_NAME
    return HarnessPlan(
        name="zcode",
        description="ZCode (agents + skills)",
        targets=(
            Target(AGENT_FILE_NAME, agents / ZCODE_AGENT_FILE_NAME),
            Target(SKILL_SOURCE_NAME, skills / SKILL_INSTALLED_NAME),
            Target(KNOWLEDGE_DOC_NAME, skills / KNOWLEDGE_DOC_NAME),
        ),
    )


def claude_plan() -> HarnessPlan:
    """Claude Code layout: skills-only under ``~/.claude/skills/``.

    Mirrors ``opencode_plan()`` shape: no agent file. VS Code cross-scans
    the Claude agents dir along with its own, so a JTM agent file there
    would surface as a duplicate picker entry on this host.
    """
    home = Path.home()
    skills = home / ".claude" / "skills" / SKILL_DIR_NAME
    return HarnessPlan(
        name="claude",
        description="Claude Code (skills directory)",
        targets=(
            Target(SKILL_SOURCE_NAME, skills / SKILL_INSTALLED_NAME),
            Target(KNOWLEDGE_DOC_NAME, skills / KNOWLEDGE_DOC_NAME),
        ),
    )


def pi_plan() -> HarnessPlan:
    """pi (badlogic/pi-mono) layout: skills-only under ``~/.pi/agent/skills``.

    pi has no agent-file convention — it skips subagents entirely — so the
    knowledge doc rides along inside the skill dir (``SKILL.md`` already
    references it). Mirrors ``opencode_plan()`` shape.
    """
    home = Path.home()
    skills = home / ".pi" / "agent" / "skills" / SKILL_DIR_NAME
    return HarnessPlan(
        name="pi",
        description="pi coding agent (skills directory)",
        targets=(
            Target(SKILL_SOURCE_NAME, skills / SKILL_INSTALLED_NAME),
            Target(KNOWLEDGE_DOC_NAME, skills / KNOWLEDGE_DOC_NAME),
        ),
    )


def hermes_plan() -> HarnessPlan:
    """Hermes (NousResearch/hermes-agent) layout: skills-only under ``~/.hermes/skills``.

    Hermes agents are runtime delegation profiles, not markdown files, so
    there is no agent file to install. Mirrors ``opencode_plan()`` shape.
    """
    home = Path.home()
    skills = home / ".hermes" / "skills" / SKILL_DIR_NAME
    return HarnessPlan(
        name="hermes",
        description="Hermes agent (skills directory)",
        targets=(
            Target(SKILL_SOURCE_NAME, skills / SKILL_INSTALLED_NAME),
            Target(KNOWLEDGE_DOC_NAME, skills / KNOWLEDGE_DOC_NAME),
        ),
    )


def opencode_plan() -> HarnessPlan:
    """OpenCode layout: skills-only convention under ``~/.config/opencode/skills``."""
    home = Path.home()
    skills = home / ".config" / "opencode" / "skills" / SKILL_DIR_NAME
    return HarnessPlan(
        name="opencode",
        description="OpenCode (skills directory)",
        targets=(
            Target(SKILL_SOURCE_NAME, skills / SKILL_INSTALLED_NAME),
            Target(KNOWLEDGE_DOC_NAME, skills / KNOWLEDGE_DOC_NAME),
        ),
    )


def codex_plan() -> HarnessPlan:
    """Codex: no safe agent-file convention — registered as unsupported.

    ``~/.codex`` holds auth/state databases and an AGENTS.md that is a
    system-generated config document; silently appending to it could
    corrupt the user's config. We do NOT invent a layout.
    """
    return HarnessPlan(
        name="codex",
        description="OpenAI Codex CLI",
        targets=(),
        note="unsupported: no agent-file convention (AGENTS.md is machine-managed; "
        "safe manual placement is not defined)",
    )


def registry() -> list[HarnessPlan]:
    """All harnesses in canonical order (copilot first, then discovery order)."""
    return [
        copilot_plan(),
        zcode_plan(),
        claude_plan(),
        pi_plan(),
        hermes_plan(),
        opencode_plan(),
        codex_plan(),
    ]


# ---------------------------------------------------------------------------
# Install / remove per harness
# ---------------------------------------------------------------------------


def install_into(harness: HarnessPlan, artefacts: dict[str, Artefact]) -> bool:
    """Install artefacts into one harness. Returns True on success.

    Harnesses with a ``note`` are skipped with the note printed (not an
    error). Per-file failures warn and continue — partial installs are
    reported in the exit summary by the caller.
    """
    print(f"[{harness.name}] {harness.description}")
    if harness.note:
        print(f"  skipped: {harness.note}")
        return True
    ok = True
    for target in harness.targets:
        artefact = artefacts.get(target.artefact)
        if artefact is None or target.dest is None:
            print(f"  warned: missing artefact {target.artefact!r}")
            ok = False
            continue
        try:
            _overwrite(target.dest, artefact.content, target.dest.name)
        except OSError as exc:
            print(f"  warned: could not write {target.dest}: {exc}")
            ok = False
    return ok


def remove_from(harness: HarnessPlan) -> bool:
    """Remove JTM-owned files from one harness. Returns True on success.

    Idempotent: missing paths are reported as 'already clean'. Directories
    created for JTM are removed when empty; never rmtree a dir that holds
    foreign files.
    """
    print(f"[{harness.name}] removing specialist files")
    if harness.note:
        print(f"  skipped: {harness.note}")
        return True
    removed = 0
    dirs: set[Path] = set()
    for target in harness.targets:
        if target.dest is None:
            continue
        dirs.add(target.dest.parent)
        if not target.dest.exists():
            continue
        try:
            target.dest.unlink()
            print(f"  removed: {target.dest}")
            removed += 1
        except OSError as exc:
            print(f"  warned: could not remove {target.dest}: {exc}")
    # Clean up now-empty JTM skill dirs.
    for directory in {d for d in dirs if d.name == SKILL_DIR_NAME}:
        with contextlib.suppress(OSError):
            directory.rmdir()  # fails silently when non-empty
    if removed == 0:
        print("  nothing to remove — already clean")
    return True


def purge_legacy_noise() -> int:
    """Purge leftovers of pre-skills-only installs. Idempotent; returns count.

    Removes, counting each file:
    - every ``jtm-jira-tempo-reports*`` file in ``~/.claude/agents/`` — the
      legacy claude agent write that VS Code's cross-scan surfaces as a
      duplicate picker entry, plus its ``.bak.*`` backups (the shared name
      prefix covers both). The prefix is deliberately exact: a user's own
      ``jtm-<other>`` file there is foreign and survives;
    - ``<JTM-name>.bak.*`` backups sitting next to current JTM targets in
      every supported harness dir (backups used to be written in-tree).

    Foreign files are never touched.
    """
    purged: list[Path] = []

    claude_agents = Path.home() / ".claude" / "agents"
    if claude_agents.is_dir():
        for leftover in sorted(claude_agents.glob("jtm-jira-tempo-reports*")):
            if leftover.is_file() and _try_unlink(leftover):
                purged.append(leftover)

    for plan in registry():
        if plan.note:
            continue
        for target in plan.targets:
            if target.dest is None:
                continue
            parent = target.dest.parent
            if not parent.is_dir():
                continue
            for leftover in sorted(parent.glob(f"{target.dest.name}.bak.*")):
                if leftover.is_file() and _try_unlink(leftover):
                    purged.append(leftover)

    if purged:
        for leftover in purged:
            print(f"  purged legacy: {leftover}")
    print(f"purged {len(purged)} legacy file(s)")
    return len(purged)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jira-tempo-mcp install-specialist",
        description=(
            "Install the JTM: Jira Tempo Reports specialist (skill + knowledge "
            "doc, plus the agent file for harnesses that support one) into AI "
            "harnesses. Idempotent and reversible."
        ),
        epilog=(
            "Supported harnesses: copilot, zcode, claude, pi, hermes, opencode. "
            "codex is registered but unsupported (no agent-file convention)."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--harness",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "install only the named harness(es); repeatable "
            "(default: all supported, unsupported ones are skipped)"
        ),
    )
    group.add_argument("--list", action="store_true", help="list supported harnesses and exit")
    group.add_argument(
        "--remove",
        action="store_true",
        help=(
            "uninstall the specialist from the selected harnesses (default: all); "
            "also purges legacy JTM leftovers (claude agents dir, .bak backups)"
        ),
    )
    args = parser.parse_args(argv)
    known = {h.name for h in registry()}
    unknown = set(args.harness) - known
    if unknown:
        parser.error(
            f"unknown harness(es): {', '.join(sorted(unknown))}. "
            f"Known: {', '.join(sorted(known))}. Use --list to show support status."
        )
    return args


def run_specialist(argv: list[str] | None = None) -> int:
    """Entry point for the ``install-specialist`` subcommand."""
    args = _parse_args(argv)
    all_plans = registry()

    if args.list:
        print("Supported harnesses:")
        for plan in all_plans:
            status = f"skipped — {plan.note}" if plan.note else "supported"
            print(f"  {plan.name:<10} {status:<55} {plan.description}")
        return 0

    selected = [p for p in all_plans if p.name in set(args.harness)] if args.harness else all_plans

    try:
        artefacts = load_artefacts()
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.remove:
        results = {plan.name: remove_from(plan) for plan in selected}
        purge_legacy_noise()
        if all(results.values()) and delete_state():
            # Successful removal — drop the auto-refresh state. A selective
            # removal also drops it (conservative: the next install recreates
            # the file with the full set).
            print(f"removed specialist state file: {state_path()}")
    else:
        results = {plan.name: install_into(plan, artefacts) for plan in selected}
        # Record the harnesses actually installed (supported ones that
        # succeeded) so `update` can auto-refresh the specialist. Merge with
        # the existing state so a selective install never shrinks it.
        supported = {p.name for p in selected if not p.note}
        installed = [name for name, ok in results.items() if ok and name in supported]
        state = read_state()
        previous = [str(h) for h in (state or {}).get("harnesses", []) if isinstance(h, str)]
        record_state(list(dict.fromkeys(previous + installed)))
        print(f"specialist state recorded: {state_path()}")
    failed = [name for name, ok in results.items() if not ok]
    verb = "removed from" if args.remove else "installed into"
    summary = ", ".join(results) if results else "no harnesses selected"
    print(f"Specialist {verb} harnesses: {summary}")
    if failed:
        print(f"Failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0
