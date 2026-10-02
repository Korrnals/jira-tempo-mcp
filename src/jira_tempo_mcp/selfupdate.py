"""Self-update subcommand: ``jira-tempo-mcp update``.

Detects how the running package was installed (``importlib.metadata``
``direct_url.json``) and applies the matching update procedure:

- editable install (``pip install -e .`` from a git checkout):
  ``git pull --ff-only`` in the checkout, then ``pip install -e .`` to
  refresh package metadata;
- wheel / package-index install (PyPI, a wheel file, or a local
  non-editable dir): ``pip install --upgrade jira-tempo-mcp``;
- package not pip-installed (Docker image, bare ``PYTHONPATH`` run):
  report and exit with guidance instead of guessing.

All pip invocations go through the current interpreter
(``sys.executable -m pip``) so the update lands in the environment/venv
the user invoked ``update`` from.

Exit codes:
    0 — update applied (or nothing applicable but reported cleanly);
    1 — detection failed / a command failed.

After a successful upgrade the specialist is refreshed best-effort: the
harnesses recorded by ``install-specialist`` in its state file are
re-installed from the new package data (per-harness failures print
warnings and never change the exit code). See ``_refresh_specialist``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import distribution as _distribution
from importlib.metadata import version as _version
from pathlib import Path
from urllib.parse import unquote, urlparse

DIST_NAME = "jira_tempo_mcp"
PROJECT_NAME = "jira-tempo-mcp"

MODE_EDITABLE = "editable"
MODE_WHEEL = "wheel"
MODE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Mode:
    """Result of install-mode detection."""

    kind: str
    project_root: Path | None
    note: str


@dataclass(frozen=True)
class Command:
    """One update step: a human-readable label + the argv to execute."""

    label: str
    argv: list[str]


def _read_direct_url() -> tuple[bool, str]:
    """Return ``(installed_via_pip, direct_url_json_text)``.

    ``direct_url.json`` exists only for direct-URL installs (local path,
    VCS, wheel file); a plain package-index install has none.
    """
    try:
        dist = _distribution(DIST_NAME)
    except PackageNotFoundError:
        return False, ""
    try:
        return True, dist.read_text("direct_url.json") or ""
    except OSError:
        return True, ""


def _fallback_root() -> Path | None:
    """Best-effort editable project root: ``<root>/src/<pkg>/selfupdate.py``."""
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "pyproject.toml").is_file() else None


def _local_root_from_url(url: str) -> Path | None:
    """Extract an existing local directory from a ``file://`` direct URL."""
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    # Windows URLs look like file:///C:/Users/... — leading slash is not
    # part of the filesystem path for drive-letter forms.
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    candidate = Path(path)
    return candidate if candidate.is_dir() else None


def detect_install_mode() -> Mode:
    """Classify the installation for the update procedure."""
    installed, raw = _read_direct_url()
    if not installed:
        return Mode(
            MODE_UNKNOWN,
            None,
            f"{PROJECT_NAME} is not installed via pip in this environment",
        )
    if not raw:
        return Mode(
            MODE_WHEEL,
            None,
            "installed from a package index (no direct_url.json)",
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return Mode(
            MODE_WHEEL,
            None,
            "unreadable direct_url.json — treating as package-index install",
        )
    dir_info = data.get("dir_info") or {}
    url = str(data.get("url", ""))
    if dir_info.get("editable"):
        root = _local_root_from_url(url) or _fallback_root()
        if root is None:
            return Mode(
                MODE_UNKNOWN,
                None,
                "editable install, but the project root is not resolvable",
            )
        return Mode(MODE_EDITABLE, root, f"editable install; project root: {root}")
    if _local_root_from_url(url) is not None:
        return Mode(
            MODE_WHEEL,
            None,
            "local non-editable install — upgrading from the package index",
        )
    return Mode(MODE_WHEEL, None, "installed from a package index / wheel file")


def build_update_plan(mode: Mode) -> list[Command] | None:
    """Build the ordered update commands for the detected mode.

    Returns None when update is not applicable (``MODE_UNKNOWN``).
    """
    if mode.kind == MODE_WHEEL:
        return [
            Command(
                "pip install --upgrade jira-tempo-mcp",
                [sys.executable, "-m", "pip", "install", "--upgrade", PROJECT_NAME],
            )
        ]
    if mode.kind == MODE_EDITABLE and mode.project_root is not None:
        root = str(mode.project_root)
        return [
            Command(
                "git pull --ff-only (project checkout)",
                ["git", "-C", root, "pull", "--ff-only"],
            ),
            Command(
                "pip install -e . (refresh editable install)",
                [sys.executable, "-m", "pip", "install", "-e", root],
            ),
        ]
    return None


def _installed_version() -> str:
    """Read the currently installed version (best-effort)."""
    try:
        return _version(DIST_NAME)
    except PackageNotFoundError:
        return "unknown"


def _refresh_specialist(new_version: str) -> None:
    """Re-install the specialist into the harnesses recorded in the state file.

    Best-effort: never raises, never affects the update exit code (the
    package itself did update). The state file is written by
    ``install-specialist``; when it is absent the user gets a one-line hint
    instead.

    Version bookkeeping edge: this process runs while pip has already
    replaced the on-disk package, so the artefacts re-installed below come
    from the NEW code, but the state file's recorded ``specialist_version``
    is still the OLD one — it is read BEFORE the state is overwritten, and
    the state rewrite receives ``new_version`` explicitly (the in-memory
    ``__version__`` of this long-running process is stale).
    """
    from jira_tempo_mcp import specialist  # lazy import: keep selfupdate import-light

    state = specialist.read_state()
    if state is None:
        print(
            "Hint: run 'jira-tempo-mcp install-specialist' to enable "
            "specialist auto-refresh on update."
        )
        return

    recorded_version = str(state.get("specialist_version", "unknown"))
    names = [str(h) for h in state.get("harnesses", []) if isinstance(h, str)]
    plans = {p.name: p for p in specialist.registry()}
    refreshable = [plans[name] for name in names if name in plans and not plans[name].note]

    if not refreshable:
        return

    artefacts: dict[str, specialist.Artefact] | None = None
    refreshed: list[str] = []
    for plan in refreshable:
        if artefacts is None:
            try:
                artefacts = specialist.load_artefacts()
            except (FileNotFoundError, OSError) as exc:
                print(f"warned: specialist artefacts unavailable, refresh skipped: {exc}")
                return
        try:
            # install_into prints the per-harness "[name] ..." line plus the
            # installed-file lines, and warns per file on failure.
            if specialist.install_into(plan, artefacts):
                refreshed.append(plan.name)
        except OSError as exc:
            print(f"warned: could not refresh specialist harness {plan.name!r}: {exc}")

    if not refreshed:
        return

    # Keep the full recorded set (unknown names ignored), refresh the stamp.
    # A post-upgrade metadata read should never be "unknown"; if it somehow
    # is, keep the recorded stamp rather than corrupting the state.
    stamp = new_version if new_version != "unknown" else recorded_version
    specialist.record_state(names, version=stamp)
    if recorded_version not in ("", "unknown") and recorded_version != stamp:
        print(f"specialist refreshed: {recorded_version} -> {stamp}")


def _unknown_mode_message(mode: Mode) -> str:  # pragma: no cover - trivial formatter
    """Guidance printed when update cannot proceed."""
    return (
        f"jira-tempo-mcp update cannot proceed: {mode.note}.\n\n"
        "Update guidance by install kind:\n"
        "- pip (venv / user):      pip install --upgrade jira-tempo-mcp\n"
        "- editable (git clone):   git pull --ff-only && pip install -e .\n"
        "- Docker image:           docker pull "
        "ghcr.io/korrnals/jira-tempo-mcp:latest\n"
    )


def run_update(argv: list[str] | None = None) -> int:
    """Entry point for the ``update`` subcommand. Returns the exit code."""
    parser = argparse.ArgumentParser(
        prog="jira-tempo-mcp update",
        description="Self-update the jira-tempo-mcp installation.",
    )
    parser.parse_args(argv)  # no flags today; unknown flags exit 2

    mode = detect_install_mode()
    print(f"Install mode: {mode.kind}" + (f" — {mode.note}" if mode.note else ""))
    plan = build_update_plan(mode)
    if plan is None:
        print(_unknown_mode_message(mode), file=sys.stderr)
        return 1

    old_version = _installed_version()
    for command in plan:
        print(f"--> {command.label}: {' '.join(command.argv)}")
        try:
            proc = subprocess.run(command.argv)  # noqa: S603 — fixed argv list
        except OSError as exc:
            print(f"Could not execute {command.argv[0]!r}: {exc}", file=sys.stderr)
            print("Update aborted.", file=sys.stderr)
            return 1
        if proc.returncode != 0:
            print(
                f"Step failed (exit {proc.returncode}): {command.label}\n"
                "Update aborted — nothing else was changed.",
                file=sys.stderr,
            )
            return 1

    new_version = _installed_version()
    print("Update complete.")
    if old_version != new_version and old_version != "unknown":
        print(f"Version: {old_version} -> {new_version}")
        print(
            "If an MCP server (jira-tempo-mcp serve) is running, restart it "
            "to pick up the new code."
        )
    # Best-effort specialist refresh — never turns a successful update into
    # a failure (the package itself did update).
    try:
        _refresh_specialist(new_version)
    except OSError as exc:
        print(f"warned: specialist refresh failed: {exc}", file=sys.stderr)
    return 0
