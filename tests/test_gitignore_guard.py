"""Guard test: virtualenv must never be tracked by git (incident abc55c8).

The .gitignore pattern ``.venv/`` (trailing slash) matches directories only
and silently ignores a *symlink* named ``.venv`` — which is how the
worktree workflow accidentally tracked one. The pattern is now ``.venv``
(no slash). This test fails the CI gate if ``git ls-files`` ever reports a
virtualenv path again.

Skipped outside a git repo (e.g. building from an sdist tarball).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _in_git_repo() -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    try:
        subprocess.run(
            [git, "-C", str(_REPO_ROOT), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return False
    return True


pytestmark = pytest.mark.skipif(not _in_git_repo(), reason="not a git repository")


def test_gitignore_covers_venv_symlinks() -> None:
    """``git check-ignore`` must ignore .venv whether it is a dir or a symlink."""
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(
        [git, "-C", str(_REPO_ROOT), "check-ignore", "-v", ".venv", "venv"],
        capture_output=True,
        text=True,
        check=False,
    )
    # check-ignore -v lines: "<source>:<line>:<pattern>\t<path>".
    ignored_patterns = {
        line.split("\t")[0].rsplit(":", 1)[-1] for line in result.stdout.splitlines()
    }
    assert ".venv" in ignored_patterns, (
        ".gitignore does not ignore '.venv' — a trailing-slash pattern only "
        "matches directories, not symlinks (incident abc55c8). Use '.venv' "
        "without the trailing slash."
    )
    assert "venv" in ignored_patterns, ".gitignore does not ignore 'venv'."


def test_no_venv_tracked_in_index() -> None:
    """``git ls-files`` must not report any virtualenv path as tracked."""
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(
        [git, "-C", str(_REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = result.stdout.splitlines()
    offenders = [
        path
        for path in tracked
        if path == ".venv"
        or path.startswith(".venv/")
        or path == "venv"
        or path.startswith("venv/")
    ]
    assert not offenders, f"Virtualenv tracked by git: {offenders}"
