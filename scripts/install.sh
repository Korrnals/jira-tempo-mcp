#!/usr/bin/env bash
# jira-tempo-mcp installer — one-command setup.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/install.sh | bash
#   curl -fsSL ... | bash -- --uninstall
#   curl -fsSL ... | bash -- --help
#   curl -fsSL ... | bash -- --install-dir /custom/path
#   curl -fsSL ... | bash -- --branch develop
#
# Clones the repo, creates a venv, installs the package, and runs the
# interactive installer (python install.py) which guides the user through
# Jira credentials setup and VS Code MCP registration.
#
# Idempotent: re-running updates the repo and re-runs the installer without
# clobbering existing .env.local or mcp.json entries (the installer merges).

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_URL="https://github.com/Korrnals/jira-tempo-mcp.git"
INSTALL_DIR_DEFAULT="${HOME}/.local/share/jira-tempo-mcp"
PY_MIN_MAJOR=3
PY_MIN_MINOR=11
SCRIPT_NAME="jira-tempo-mcp install.sh"

# ---------------------------------------------------------------------------
# Colors (honour TTY — no ANSI when piped)
# ---------------------------------------------------------------------------

if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
    BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; NC=''
fi

info()  { printf "${BLUE}·${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}!${NC} %s\n" "$*"; }
err()   { printf "${RED}✗${NC} %s\n" "$*" >&2; }
die()   { err "$*"; exit 1; }
step()  { printf "\n${BOLD}${BLUE}▸ %s${NC}\n" "$*"; }

# ---------------------------------------------------------------------------
# Cleanup trap
# ---------------------------------------------------------------------------

TMP_CLONE=""
cleanup() {
    local rc=$?
    if [ -n "${TMP_CLONE}" ] && [ -d "${TMP_CLONE}" ]; then
        info "Cleaning up temporary clone: ${TMP_CLONE}"
        rm -rf "${TMP_CLONE}" || warn "Failed to remove ${TMP_CLONE} (remove manually)"
    fi
    exit $rc
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
${SCRIPT_NAME} — one-command installer for jira-tempo-mcp.

Usage:
  curl -fsSL https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/install.sh | bash
  curl -fsSL ... | bash -- [OPTIONS]

Options:
  --uninstall              Run the uninstaller instead of the installer.
  --install-dir <path>     Clone/install directory (default: ${INSTALL_DIR_DEFAULT}).
  --branch <name>          Git branch to clone (default: main).
  --no-clone               Use an existing checkout in --install-dir (skip clone).
  --yes                    Non-interactive: accept installer defaults where possible.
  --help, -h               Show this help and exit.

Environment overrides:
  JIRA_TEMPO_MCP_INSTALL_DIR   Same as --install-dir.
  JIRA_TEMPO_MCP_BRANCH        Same as --branch.

The installer never requires sudo — everything lives in user space.
EOF
}

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------

UNINSTALL=false
INSTALL_DIR="${JIRA_TEMPO_MCP_INSTALL_DIR:-${INSTALL_DIR_DEFAULT}}"
BRANCH="${JIRA_TEMPO_MCP_BRANCH:-main}"
NO_CLONE=false
ASSUME_YES=false

while [ $# -gt 0 ]; do
    case "$1" in
        --uninstall)    UNINSTALL=true; shift ;;
        --install-dir)  INSTALL_DIR="${2:-}"; shift 2 || die "--install-dir requires a value" ;;
        --branch)       BRANCH="${2:-}"; shift 2 || die "--branch requires a value" ;;
        --no-clone)     NO_CLONE=true; shift ;;
        --yes|-y)       ASSUME_YES=true; shift ;;
        --help|-h)      usage; exit 0 ;;
        --)             shift; break ;;
        *)              die "Unknown option: $1 (try --help)" ;;
    esac
done

# ---------------------------------------------------------------------------
# OS detection
# ---------------------------------------------------------------------------

detect_os() {
    local os
    os="$(uname -s 2>/dev/null || echo unknown)"
    case "$os" in
        Linux*)  printf "linux" ;;
        Darwin*) printf "macos" ;;
        MINGW*|MSYS*|CYGWIN*) printf "windows-git-bash" ;;
        *)       printf "unknown:%s" "$os" ;;
    esac
}

OS="$(detect_os)"
case "$OS" in
    linux|macos)
        info "Detected OS: ${OS}"
        ;;
    windows-git-bash)
        warn "Windows detected via Git Bash. This script works best on Linux/macOS."
        warn "On native Windows, use WSL (Windows Subsystem for Linux) for full support."
        warn "Continuing anyway — proceed at your own risk."
        ;;
    *)
        warn "Unrecognised OS: ${OS#unknown:}. Proceeding on a best-effort basis."
        ;;
esac

# ---------------------------------------------------------------------------
# Prerequisites: python3, pip, git
# ---------------------------------------------------------------------------

step "Checking prerequisites"

command -v git >/dev/null 2>&1 || die "git not found in PATH. Install git first."

# Locate a suitable python3.
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        ver="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
        major="${ver%%.*}"
        minor="${ver#*.}"
        if [ "$major" -gt "$PY_MIN_MAJOR" ] 2>/dev/null \
           || { [ "$major" -eq "$PY_MIN_MAJOR" ] 2>/dev/null && [ "$minor" -ge "$PY_MIN_MINOR" ] 2>/dev/null; }; then
            PYTHON_BIN="$candidate"
            ok "Found ${candidate} ${ver} (>= ${PY_MIN_MAJOR}.${PY_MIN_MINOR})"
            break
        fi
    fi
done
[ -n "$PYTHON_BIN" ] || die "Python >= ${PY_MIN_MAJOR}.${PY_MIN_MINOR} not found. Install it first."

# pip availability.
if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
    die "pip not available for ${PYTHON_BIN}. Install pip (e.g. 'python3 -m ensurepip' or your package manager)."
fi
ok "pip available"

# ---------------------------------------------------------------------------
# Existing install detection (idempotency / update prompt)
# ---------------------------------------------------------------------------

if command -v jira-tempo-mcp >/dev/null 2>&1; then
    existing_ver="$(jira-tempo-mcp --version 2>/dev/null || echo 'unknown')"
    warn "An existing 'jira-tempo-mcp' was found in PATH (version: ${existing_ver})."
    if [ "$ASSUME_YES" = "true" ]; then
        info "Proceeding with update (--yes set)."
    else
        printf "  Update existing installation? [Y/n]: "
        read -r reply
        reply="${reply:-y}"
        case "$reply" in
            y|Y|yes) info "Updating existing installation." ;;
            *)       info "Keeping existing installation. Exiting."; exit 0 ;;
        esac
    fi
fi

# ---------------------------------------------------------------------------
# Uninstall path
# ---------------------------------------------------------------------------

if [ "$UNINSTALL" = "true" ]; then
    step "Uninstalling jira-tempo-mcp"
    if [ "$NO_CLONE" = "true" ] || [ -d "${INSTALL_DIR}/.git" ]; then
        info "Using existing checkout at: ${INSTALL_DIR}"
    else
        info "Cloning repo (shallow) for uninstaller..."
        TMP_CLONE="$(mktemp -d -t jira-tempo-mcp-uninstall-XXXXXX)"
        git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP_CLONE" \
            || die "git clone failed (branch: ${BRANCH}). Check the URL and network."
        INSTALL_DIR="$TMP_CLONE"
    fi

    if [ ! -f "${INSTALL_DIR}/install.py" ]; then
        die "install.py not found in ${INSTALL_DIR} — cannot run uninstaller."
    fi

    info "Running: ${PYTHON_BIN} ${INSTALL_DIR}/install.py uninstall"
    ( cd "$INSTALL_DIR" && "$PYTHON_BIN" install.py uninstall ) || die "Uninstaller failed."
    ok "Uninstall complete."
    exit 0
fi

# ---------------------------------------------------------------------------
# Install path: clone (or reuse), venv, pip install, run installer
# ---------------------------------------------------------------------------

step "Preparing project directory: ${INSTALL_DIR}"

if [ "$NO_CLONE" = "true" ]; then
    [ -d "${INSTALL_DIR}" ] || die "--no-clone set but ${INSTALL_DIR} does not exist."
    [ -f "${INSTALL_DIR}/install.py" ] || die "--no-clone set but install.py missing in ${INSTALL_DIR}."
    info "Using existing checkout (--no-clone): ${INSTALL_DIR}"
elif [ -d "${INSTALL_DIR}/.git" ]; then
    info "Existing checkout found — updating (git pull)."
    ( cd "$INSTALL_DIR" \
        && git fetch --quiet origin \
        && git checkout --quiet "$BRANCH" \
        && git reset --hard --quiet "origin/${BRANCH}" ) \
        || die "Failed to update existing checkout in ${INSTALL_DIR}."
    ok "Checkout updated to origin/${BRANCH}"
else
    info "Cloning ${REPO_URL} (branch: ${BRANCH}) → ${INSTALL_DIR}"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR" \
        || die "git clone failed. Check the URL, branch, and network."
    ok "Repository cloned"
fi

step "Creating venv and installing package"

VENV_DIR="${INSTALL_DIR}/.venv"
if [ ! -d "$VENV_DIR" ]; then
    info "Creating venv at ${VENV_DIR}"
    "$PYTHON_BIN" -m venv "$VENV_DIR" || die "venv creation failed."
    ok "venv created"
else
    ok "venv already exists at ${VENV_DIR}"
fi

# shellcheck disable=SC1091
# venv activate sets up PATH for the venv python/pip.
set +u
# shellcheck source=/dev/null
. "${VENV_DIR}/bin/activate"
set -u

info "Upgrading pip..."
python -m pip install --quiet --upgrade pip || warn "pip upgrade skipped (non-fatal)."

info "Installing package (editable, with dev deps)..."
pip install --quiet -e ".[dev]" || die "pip install failed. See output above for details."
ok "Package installed"

step "Running interactive installer"
info "This will guide you through Jira credentials and VS Code MCP registration."
info "Press Enter to accept defaults where shown."
echo

# Deactivate before handing off so install.py uses its own venv python cleanly.
deactivate 2>/dev/null || true

( cd "$INSTALL_DIR" && "$PYTHON_BIN" install.py ) || die "Interactive installer failed."

echo
ok "All done!"
echo
info "Next steps:"
printf "  • Restart VS Code and approve the 'jira-tempo' MCP server in the MCP panel.\n"
printf "  • Edit ~/.config/Code/User/.env.local to update JIRA_PAT if it expires.\n"
printf "  • Re-run this script anytime to update (idempotent).\n"
printf "  • Uninstall: curl -fsSL ... | bash -- --uninstall\n"
