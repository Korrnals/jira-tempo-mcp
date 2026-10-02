#!/usr/bin/env node
/**
 * Lightweight tests for the jira-tempo-mcp npm shim (bin/cli.js).
 *
 * Run from this dir:  npm test  (no deps — plain node:test + assert)
 * Covered (light, per the task contract):
 * - arg passthrough: subcommands + args reach the Python CLI verbatim
 * - runner discovery: console script on PATH preferred; python module fallback
 * - auto-install flow on first run when the Python package is absent
 * - no python + no package → exit 1 with guidance
 *
 * The Python side is stubbed via child_process.spawnSync monkeypatching.
 * cli.js destructures spawnSync at module load, so every test MUST evict
 * the require cache before re-requiring the shim — otherwise a stale stub
 * binding from the first load wins (proven root cause of a first-draft bug).
 */

const { test } = require("node:test");
const assert = require("node:assert");

const cp = require("child_process");
const SHIM = require.resolve("../bin/cli.js");

/** Evict shim from require cache + fresh process.argv + spawnSync stub. */
function loadShim(argvTail, spawnStub) {
  delete require.cache[SHIM];
  const origArgv = process.argv;
  const origSpawn = cp.spawnSync;
  const origExit = process.exit;
  const calls = [];
  process.argv = [process.argv[0], SHIM, ...argvTail];
  cp.spawnSync = (bin, args, opts) => spawnStub(calls, bin, args, opts);
  // process.exit must TERMINATE like the real one — the shim has guard
  // paths that rely on exit never returning. Throwing a sentinel emulates
  // termination inside require() and lets us capture the exit code.
  let exitCode = null;
  const sentinel = { __exitSentinel: true };
  process.exit = (code) => {
    exitCode = code;
    throw sentinel;
  };
  try {
    require(SHIM);
  } catch (err) {
    if (err !== sentinel) {
      throw err;
    }
  } finally {
    process.exit = origExit;
    cp.spawnSync = origSpawn;
    process.argv = origArgv;
  }
  return { calls, exitCode };
}

/** python3 --version probe succeeds; everything else is recorded. */
const versionOk = (calls, bin, args) => {
  if (bin === "python3" && args[0] === "--version") {
    return { status: 0, stdout: "Python 3.14.7\n", stderr: "" };
  }
  calls.push({ bin, args });
  return { status: 0, stdout: "", stderr: "" };
};

test("passthrough: bare run spawns module server with no extra args", () => {
  const { calls, exitCode } = loadShim([], (calls2, bin, args) => {
    if (bin === "which" && args[0] === "jira-tempo-mcp") {
      return { status: 1, stdout: "", stderr: "" }; // no console script
    }
    return versionOk(calls2, bin, args);
  });

  assert.strictEqual(exitCode, 0);
  const final = calls[calls.length - 1];
  assert.strictEqual(final.bin, "python3");
  assert.deepStrictEqual(final.args, ["-m", "jira_tempo_mcp.cli"]);
});

test("passthrough: install-specialist flags forwarded verbatim via script", () => {
  const { calls, exitCode } = loadShim(
    ["install-specialist", "--harness", "claude", "--list"],
    (calls2, bin, args) => {
      if (bin === "which" && args[0] === "jira-tempo-mcp") {
        // A console script that DOES exist on disk: this very test file.
        return { status: 0, stdout: `${__filename}\n`, stderr: "" };
      }
      calls2.push({ bin, args });
      return { status: 0, stdout: "", stderr: "" };
    }
  );

  assert.strictEqual(exitCode, 0);
  assert.deepStrictEqual(calls[0].args, [
    "install-specialist",
    "--harness",
    "claude",
    "--list",
  ]);
});

test("passthrough: update subcommand forwarded", () => {
  const { calls, exitCode } = loadShim(["update", "--quiet"], (calls2, bin, args) => {
    if (bin === "which" && args[0] === "jira-tempo-mcp") {
      return { status: 0, stdout: `${__filename}\n`, stderr: "" };
    }
    calls2.push({ bin, args });
    return { status: 0, stdout: "", stderr: "" };
  });

  assert.strictEqual(exitCode, 0);
  assert.deepStrictEqual(calls[0].args, ["update", "--quiet"]);
});

test("runner discovery: python module fallback when script missing", () => {
  const { calls, exitCode } = loadShim(["--version"], (calls2, bin, args) => {
    if (bin === "which") {
      return { status: 1, stdout: "", stderr: "" };
    }
    return versionOk(calls2, bin, args);
  });

  assert.strictEqual(exitCode, 0);
  const final = calls[calls.length - 1];
  assert.deepStrictEqual(final.args, ["-m", "jira_tempo_mcp.cli", "--version"]);
});

test("auto-install: server start with package missing runs pip, then dispatches", () => {
  const { calls, exitCode } = loadShim([], (calls2, bin, args) => {
    if (bin === "which") {
      return { status: 1, stdout: "", stderr: "" };
    }
    if (bin === "python3" && args[0] === "--version") {
      return { status: 0, stdout: "Python 3.14.7\n", stderr: "" };
    }
    calls2.push({ bin, args });
    // module probes fail; pip "succeeds" (status 0) to reach re-probe.
    if (args[0] === "-m" && args[1] === "pip") {
      return { status: 0, stdout: "", stderr: "" };
    }
    return { status: 1, stdout: "", stderr: "" };
  });

  assert.strictEqual(exitCode, 1); // re-probe failed → guidance
  const pipCall = calls.find(
    (c) => c.args[0] === "-m" && c.args[1] === "pip" && c.args[2] === "install"
  );
  assert.ok(pipCall, "pip install must be attempted");
  assert.deepStrictEqual(pipCall.args.slice(3), ["--upgrade", "jira-tempo-mcp"]);
});

test("no python at all: exit 1 with guidance", () => {
  // python3/py probes fail (status 1), which fails → no runner, no auto-install
  const { exitCode } = loadShim([], () => ({ status: 1, stdout: "", stderr: "" }));

  assert.strictEqual(exitCode, 1);
});

test("unknown subcommand with package missing: no silent auto-install", () => {
  const { calls, exitCode } = loadShim(["uninstall"], (calls2, bin, args) => {
    if (bin === "which") {
      return { status: 1, stdout: "", stderr: "" };
    }
    if (bin === "python3" && args[0] === "--version") {
      return { status: 0, stdout: "Python 3.14.7\n", stderr: "" };
    }
    calls2.push({ bin, args });
    return { status: 1, stdout: "", stderr: "" };
  });

  assert.strictEqual(exitCode, 1);
  const pipCall = calls.find(
    (c) => c.args[0] === "-m" && c.args[1] === "pip" && c.args[2] === "install"
  );
  assert.strictEqual(pipCall, undefined); // no surprise install for 'uninstall'
});