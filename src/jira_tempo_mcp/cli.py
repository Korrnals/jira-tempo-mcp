"""Console entrypoint dispatcher.

Usage:
    jira-tempo-mcp                  # same as 'serve' — start the MCP server
    jira-tempo-mcp serve            # start the MCP server (stdio)
    jira-tempo-mcp install          # interactive installer (vibe-style setup)
    jira-tempo-mcp uninstall        # reverse the installation (remove VS Code entry, optional .env + pip)
    jira-tempo-mcp --version
"""

from __future__ import annotations

import sys

from . import __version__


def _run_install_script(subcommand: str) -> int:
    """Resolve install.py robustly (editable or wheel) and run it with the given subcommand.

    subcommand="install"   → executes main() (installer).
    subcommand="uninstall" → executes uninstall() (uninstaller).

    install.py's ``if __name__ == "__main__"`` guard inspects ``sys.argv[1]``
    to dispatch, so we set ``sys.argv`` accordingly and run under
    ``run_name="__main__"`` so the guard fires.
    """
    import runpy
    from importlib.resources import files
    from pathlib import Path

    # Try package data first (works in wheel installs if install.py is shipped).
    try:
        install_path = Path(str(files(__package__) / "install.py"))
        if install_path.exists():
            sys.argv = [str(install_path), subcommand]
            runpy.run_path(str(install_path), run_name="__main__")
            return 0
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    # Fallback: editable install — install.py is at project root (3 levels up from cli.py).
    editable_path = Path(__file__).resolve().parent.parent.parent / "install.py"
    if editable_path.exists():
        sys.argv = [str(editable_path), subcommand]
        runpy.run_path(str(editable_path), run_name="__main__")
        return 0

    print(
        "\n'jira-tempo-mcp install' requires a git clone (not a wheel/Docker install).\n"
        "install.py is a dev-setup script that needs the repository tree "
        "(.env.example, copilot-integration/, pyproject.toml).\n\n"
        "To install:\n"
        "  git clone https://github.com/Korrnals/jira-tempo-mcp.git\n"
        "  cd jira-tempo-mcp\n"
        "  pip install -e .\n"
        "  jira-tempo-mcp install\n\n"
        "For Docker-only usage (no install needed):\n"
        "  docker run -i --rm --env-file .env ghcr.io/korrnals/jira-tempo-mcp:latest\n",
        file=sys.stderr,
    )
    return 1


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
