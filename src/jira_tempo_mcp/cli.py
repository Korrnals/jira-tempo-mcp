"""Console entrypoint dispatcher.

Usage:
    jira-tempo-mcp                  # same as 'serve' — start the MCP server
    jira-tempo-mcp serve            # start the MCP server (stdio)
    jira-tempo-mcp install          # interactive installer (repo checkout drives
                                    #   install.py; wheel installs use the built-in
                                    #   configurator — see installer.py)
    jira-tempo-mcp uninstall        # reverse the installation (remove VS Code entry, optional .env + pip)
    jira-tempo-mcp update           # self-update (pip upgrade, or git pull for editable installs)
    jira-tempo-mcp install-specialist  # install the JTM agent into AI harnesses
    jira-tempo-mcp --version
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import __version__


def _find_install_script() -> Path | None:
    """Locate the repo-root ``install.py`` (editable flow), or None.

    Probes, in order:
    1. Package data (works in wheel installs only if install.py is shipped —
       it is not, but keep the probe for sdist/custom builds).
    2. Editable install — install.py at the project root (3 levels up from
       cli.py).

    Shared by the runpy dispatch and the wheel-mode fallback decision.
    """
    from importlib.resources import files

    # Try package data first (works in wheel installs if install.py is shipped).
    try:
        install_path = Path(str(files(__package__) / "install.py"))
        if install_path.exists():
            return install_path
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    # Fallback: editable install — install.py is at project root.
    editable_path = Path(__file__).resolve().parent.parent.parent / "install.py"
    if editable_path.exists():
        return editable_path
    return None


def _run_install_script(subcommand: str) -> int:
    """Route ``install`` / ``uninstall`` to the right implementation.

    When a repo checkout is detected (editable flow) the repo-root
    ``install.py`` is executed with runpy — unchanged behaviour. Otherwise
    (wheel / Docker / bare pip install) the built-in wheel-mode configurator
    in :mod:`jira_tempo_mcp.installer` runs, so pip users no longer need to
    hand-edit ``mcp.json``.

    install.py's ``if __name__ == "__main__"`` guard inspects ``sys.argv[1]``
    to dispatch, so we set ``sys.argv`` accordingly and run under
    ``run_name="__main__"`` so the guard fires.
    """
    import runpy

    script = _find_install_script()
    if script is not None:
        sys.argv = [str(script), subcommand]
        runpy.run_path(str(script), run_name="__main__")
        return 0

    if subcommand == "install":
        from .installer import install_wheel

        return install_wheel(sys.argv[2:])

    from .installer import uninstall_wheel

    return uninstall_wheel(sys.argv[2:])


def main() -> int:
    if len(sys.argv) >= 2:
        cmd = sys.argv[1]
        if cmd in ("-v", "--version"):
            print(f"jira-tempo-mcp {__version__}")
            return 0
        if cmd == "serve":
            from .server import main as serve_main

            serve_main()
            return 0
        if cmd == "install":
            return _run_install_script("install")
        if cmd == "uninstall":
            return _run_install_script("uninstall")
        if cmd == "update":
            from .selfupdate import run_update

            rc_update: int = run_update(sys.argv[2:])
            return rc_update
        if cmd == "install-specialist":
            from .specialist import run_specialist

            rc_specialist: int = run_specialist(sys.argv[2:])
            return rc_specialist
        if cmd in ("-h", "--help"):
            print(__doc__)
            return 0
        print(f"Unknown command: {cmd!r}\n", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2

    # No args: default to serve
    from .server import main as serve_main

    serve_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
