#!/usr/bin/env bash
# jira-tempo-mcp uninstaller — thin wrapper around install.sh --uninstall.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/uninstall.sh | bash
#   curl -fsSL ... | bash -- --help
#
# This is a convenience entry point. The full uninstall logic lives in
# install.sh --uninstall, which delegates to `python install.py uninstall`
# (removes the VS Code mcp.json entry, optionally deletes .env and the pip
# package). See scripts/install.sh --help for all options.

set -euo pipefail

# Resolve the directory of this script so we can call install.sh directly
# when run from a local checkout. When piped from curl, fall back to
# fetching install.sh from the same raw GitHub path.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
INSTALL_SH_LOCAL="${SCRIPT_DIR:+${SCRIPT_DIR}/install.sh}"
REMOTE_INSTALL_URL="https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/install.sh"

run_install_sh() {
    if [ -n "$INSTALL_SH_LOCAL" ] && [ -f "$INSTALL_SH_LOCAL" ]; then
        exec bash "$INSTALL_SH_LOCAL" --uninstall "$@"
    fi
    # Piped-from-curl path: fetch install.sh and pipe into bash with --uninstall.
    if command -v curl >/dev/null 2>&1; then
        exec curl -fsSL "$REMOTE_INSTALL_URL" | bash -- --uninstall "$@"
    fi
    echo "jira-tempo-mcp uninstall: need curl to fetch the installer, or run scripts/install.sh --uninstall from a local clone." >&2
    exit 1
}

# --help short-circuit before delegating (so we don't fetch unnecessarily).
for arg in "$@"; do
    case "$arg" in
        --help|-h)
            cat <<EOF
jira-tempo-mcp uninstaller — wrapper around install.sh --uninstall.

Usage:
  bash scripts/uninstall.sh [OPTIONS]

Options (forwarded to install.sh):
  --install-dir <path>   Clone/install directory (default: ~/.local/share/jira-tempo-mcp).
  --branch <name>        Git branch to clone (default: main).
  --no-clone             Use an existing checkout in --install-dir.
  --yes                  Non-interactive.
  --help, -h             Show this help.

See: scripts/install.sh --help for the full option list.
EOF
            exit 0
            ;;
    esac
done

run_install_sh "$@"
