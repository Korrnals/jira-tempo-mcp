"""Setuptools build hook — ships ``install.py`` inside the wheel package.

``install.py`` lives at the project root: it is used directly by editable
installs (``python install.py``) and resolved from there by
:func:`jira_tempo_mcp.cli._run_install_script`. For **wheel** installs the
project root is not on disk, so ``cli.py`` falls back to
``importlib.resources.files(__package__) / "install.py"`` — which only
resolves if ``install.py`` is shipped as package data.

This hook copies ``install.py`` from the project root into the package
directory (``jira_tempo_mcp/``) at build time so the wheel includes it.
The file remains authoritative at the project root; this is a build-time
copy, not a second source of truth.

The module is named ``build_helpers`` (not ``build``) to avoid shadowing
the ``pypa/build`` package used by ``python -m build``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools.command.build_py import build_py as _build_py


class build_py(_build_py):
    """Copy ``install.py`` from the project root into the package build dir."""

    def run(self) -> None:
        super().run()
        src = Path(__file__).resolve().parent / "install.py"
        if not src.exists():
            return
        pkg = Path(self.build_lib) / "jira_tempo_mcp"
        pkg.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, pkg / "install.py")
