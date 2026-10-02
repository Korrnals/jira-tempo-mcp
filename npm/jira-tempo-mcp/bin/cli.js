#!/usr/bin/env node
/**
 * jira-tempo-mcp — thin wrapper around the Python `jira-tempo-mcp` package.
 *
 * The real server is a Python stdio MCP server distributed on PyPI. This npm
 * package exists so Node-first users can `npm install -g jira-tempo-mcp` and
 * get the same end-to-end result: Python package installed, MCP server and
 * specialist commands available.
 *
 * Commands (all subcommands pass through to the Python CLI):
 *   jira-tempo-mcp                    start the MCP server over stdio (default)
 *   jira-tempo-mcp serve              same
 *   jira-tempo-mcp install            run the interactive installer (install.py)
 *   jira-tempo-mcp uninstall          reverse the installation
 *   jira-tempo-mcp update             self-update the Python package
 *   jira-tempo-mcp install-specialist install the JTM agent into AI harnesses
 *   jira-tempo-mcp --version / --help
 */

const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PROJECT = "jira-tempo-mcp";
const PY_MIN = [3, 11];

function pythonBin() {
  const bins = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];
  for (const bin of bins) {
    const res = spawnSync(bin, ["--version"], { encoding: "utf8" });
    if (res.status === 0 && res.stdout) {
      const match = res.stdout.trim().match(/(\d+)\.(\d+)/);
      if (match && +match[1] >= PY_MIN[0] && +match[2] >= PY_MIN[1]) {
        return bin;
      }
      // Version below the floor — keep scanning (a `py` launcher may hold 3.11+).
    } else if (res.status === 0) {
      return bin;
    }
  }
  return null;
}

function pipxAvailable() {
  const res = spawnSync("pipx", ["--version"], { encoding: "utf8" });
  return res.status === 0;
}

function moduleInstalled(py) {
  const res = spawnSync(py, ["-m", "jira_tempo_mcp.cli", "--version"], {
    encoding: "utf8",
  });
  return res.status === 0;
}

/**
 * Locate a Python interpreter that can run the jira_tempo_mcp module.
 * Order: console script on PATH (`jira-tempo-mcp`) → any python with the
 * module importable. Returns { kind, value } or null.
 */
function findRunner() {
  const which = process.platform === "win32" ? "where" : "which";
  for (const cmd of ["jira-tempo-mcp"]) {
    const res = spawnSync(which, [cmd], { encoding: "utf8" });
    if (res.status === 0 && res.stdout) {
      const script = res.stdout.trim().split("\n")[0];
      if (script && fs.existsSync(script)) {
        return { kind: "script", value: script };
      }
    }
  }
  const py = pythonBin();
  if (py && moduleInstalled(py)) {
    return { kind: "module", value: py };
  }
  return null;
}

function autoInstall(py) {
  // pipx first (isolated, no venv pollution); pip --user fallback via pip -m.
  if (pipxAvailable()) {
    console.log(`[jira-tempo-mcp] Installing Python package via pipx…`);
    const res = spawnSync("pipx", ["install", PROJECT], { stdio: "inherit" });
    if (res.status === 0) return true;
    console.log(`[jira-tempo-mcp] pipx install failed — falling back to pip.`);
  }
  console.log(`[jira-tempo-mcp] Installing Python package via pip (${py})…`);
  const res = spawnSync(py, ["-m", "pip", "install", "--upgrade", PROJECT], {
    stdio: "inherit",
  });
  return res.status === 0;
}

function main() {
  const cmd = process.argv[2] || "";
  const helpRequested = cmd === "help" || cmd === "--help" || cmd === "-h";
  const passthrough = ["--version", "-v"].includes(cmd)
    ? ["--version"]
    : process.argv.slice(2);

  const runner = findRunner();
  if (!runner) {
    const py = pythonBin();
    if (!py) {
      console.error(
        `Python >= 3.11 not found. Install Python, then: pip install ${PROJECT}`
      );
      process.exit(1);
    }
    if (helpRequested || ["install", "update"].includes(cmd) || !cmd) {
      console.error(`[jira-tempo-mcp] Python package not installed — installing it now…`);
      if (!autoInstall(py)) {
        console.error(
          `[jira-tempo-mcp] Auto-install failed. Install manually:\n` +
            `  pip install ${PROJECT}\n` +
            `then re-run this command.`
        );
        process.exit(1);
      }
      const after = findRunner();
      if (!after) {
        console.error(
          `[jira-tempo-mcp] Installed, but the CLI is still not reachable.\n` +
            `If pipx was used, run: pipx ensurepath  (then reopen the terminal).`
        );
        process.exit(1);
      }
      const res =
        after.kind === "script"
          ? spawnSync(after.value, passthrough, { stdio: "inherit" })
          : spawnSync(after.value, ["-m", "jira_tempo_mcp.cli", ...passthrough], {
              stdio: "inherit",
            });
      process.exit(res.status || 0);
    }
    console.error(
      `${PROJECT} (Python) is not installed and no auto-install was requested\n` +
        `for command '${cmd}'. Run:\n` +
        `  jira-tempo-mcp --help        # triggers one-time auto-install\n` +
        `or:\n` +
        `  pip install ${PROJECT}`
    );
    process.exit(1);
  }

  const args =
    runner.kind === "script" ? passthrough : ["-m", "jira_tempo_mcp.cli", ...passthrough];
  const res =
    runner.kind === "script"
      ? spawnSync(runner.value, args, { stdio: "inherit" })
      : spawnSync(runner.value, args, { stdio: "inherit" });
  process.exit(res.status || 0);
}

// pipx on PATH check needs os/path only in some layouts; keep import visible
// for future use (npm shim conventions).
void os;
void path;

main();