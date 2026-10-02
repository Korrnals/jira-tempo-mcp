#!/usr/bin/env node
/**
 * postinstall: make `npm i -g jira-tempo-mcp` a complete one-command setup.
 * Installs the Python package (pipx when available, pip otherwise) when
 * Python ≥3.11 exists, then prints the next steps. Never fails the npm
 * install: absence of Python is reported, not thrown.
 */

const { spawnSync } = require("child_process");

const PROJECT = "jira-tempo-mcp";

function pythonBin() {
  const bins = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];
  for (const bin of bins) {
    const res = spawnSync(bin, ["--version"], { encoding: "utf8" });
    if (res.status === 0 && res.stdout) {
      const match = res.stdout.trim().match(/(\d+)\.(\d+)/);
      if (match && (+match[1] > 3 || +match[2] >= 11)) return bin;
    }
  }
  return null;
}

const py = pythonBin();
if (!py) {
  console.log(
    `[${PROJECT}] Python >= 3.11 not found — install Python, then:\n` +
      `             pip install ${PROJECT}\n` +
      `             jira-tempo-mcp                # MCP server (stdio)\n` +
      `             jira-tempo-mcp install-specialist  # AI harness integration`
  );
  return;
}

if (spawnSync("pipx", ["--version"], { encoding: "utf8" }).status === 0) {
  console.log(`[${PROJECT}] Installing Python package via pipx…`);
  const res = spawnSync("pipx", ["install", PROJECT], { stdio: "inherit" });
  if (res.status !== 0) {
    console.log(`[${PROJECT}] pipx install failed — try: pip install ${PROJECT}`);
    return;
  }
} else {
  console.log(`[${PROJECT}] Installing Python package via pip (${py})…`);
  const res = spawnSync(py, ["-m", "pip", "install", "--upgrade", PROJECT], {
    stdio: "inherit",
  });
  if (res.status !== 0) {
    console.log(
      `[${PROJECT}] pip install failed — run manually, then:\n` +
        `  jira-tempo-mcp install`
    );
    return;
  }
}

console.log(
  `[${PROJECT}] Done. Next steps:\n` +
    `  jira-tempo-mcp                    # MCP server (stdio)\n` +
    `  jira-tempo-mcp install            # interactive setup (venv/.env/VS Code)\n` +
    `  jira-tempo-mcp install-specialist # install the JTM agent into AI harnesses\n` +
    `  jira-tempo-mcp update             # self-update later`
);