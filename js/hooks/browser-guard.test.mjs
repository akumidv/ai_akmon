/**
 * node:test for the browser class of the access matrix in `js/hooks/hook_core.mjs` (ADR 0032/D07) — the
 * twin of `meta/tests/test_browser_guard.py`; the hook corpus runs both implementations end to end.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ACTORS } from "../common/access_matrix.mjs";
import {
  browserCommandDrives,
  browserGuardResult,
  gitCommitGuardResult,
  HookResult,
  strictestResult,
} from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

const data = lazyHookData();

const DRIVES = [
  "akmon tool browser status",
  "akmon tool browser start --url https://example.org",
  ".venv/bin/akmon tool browser status",
  "npx akmon tool browser status",
  "npx --no-install akmon tool browser status",
  "pnpm exec akmon tool browser status",
  "node node_modules/akmon/js/tools/browser.mjs status",
  "node js/tools/browser.mjs status",
  "python3 tools/browser.py status",
  "python3 /opt/akmon/tools/browser.py status",
  "uv run akmon tool browser status",
  "uv run python tools/browser.py status",
  "node --no-warnings js/tools/browser.mjs status",
  "node _aitna/akmon/js/akmon/cli.mjs tool browser status",
  "cd sub && akmon tool browser status",
  "FOO=1 env akmon tool browser status",
  "true; akmon tool browser status | cat",
  "bash -c 'akmon tool browser status'",
  "echo $(akmon tool browser status)",
];

const TEXT = [
  "ls -la",
  "akmon tool model-routing show",
  "akmon tool browser-notes",
  'echo "akmon tool browser status"',
  "echo 'akmon tool browser status' > note.txt",
  "echo akmon tool browser status",
  "grep -r 'tool browser' docs",
  "cat <<'EOF'\nakmon tool browser status\nEOF",
  "node scripts/browser.mjs",
  "npx --no-install oxfmt js/tools/browser.mjs",
  "npx --no-install oxlint js/tools/browser.mjs js/tools/browser.py",
  "node --test js/tools/browser/attach.test.mjs",
  "grep -n x js/tools/browser.mjs",
  "cat tools/browser.py",
  "npx --no-install tsc --checkJs js/tools/browser.mjs",
  "git diff js/tools/browser.mjs",
  "sed -n 1,5p tools/browser.py",
  "python3 other/browser.py",
  "git commit -m 'akmon tool browser'",
];

test("command words that run the browser tool drive it", () => {
  for (const command of DRIVES) {
    assert.equal(browserCommandDrives(data, command), true, command);
  }
});

test("text and other programs do not drive it", () => {
  for (const command of TEXT) {
    assert.equal(browserCommandDrives(data, command), false, command);
  }
});

const CALLS = [
  ["Bash", "akmon tool browser status"],
  ["mcp__akmon-browser__take_snapshot", ""],
];

test("a developer's own session drives the browser", () => {
  for (const [toolName, command] of CALLS) {
    assert.equal(browserGuardResult(data, toolName, command, { actor: ACTORS.DEVELOPER }), null, toolName);
    assert.equal(browserGuardResult(data, toolName, command), null, toolName);
  }
});

test("a delegated agent is denied with the hand-back reason", () => {
  for (const [toolName, command] of CALLS) {
    const result = browserGuardResult(data, toolName, command, { actor: ACTORS.DEVELOPER, delegated: true });
    assert.equal(result?.permissionDecision, "deny", toolName);
    assert.match(result?.permissionReason ?? "", /delegated agent/);
    assert.match(result?.permissionReason ?? "", /hand it back to the main session/);
  }
});

test("an autonomous run is denied, delegated or not", () => {
  for (const delegated of [false, true]) {
    for (const [toolName, command] of CALLS) {
      const result = browserGuardResult(data, toolName, command, { actor: ACTORS.AUTONOMOUS, delegated });
      assert.equal(result?.permissionDecision, "deny", toolName);
      assert.match(result?.permissionReason ?? "", /autonomous run/);
    }
  }
});

test("anything else is not this guard's", () => {
  for (const [toolName, command] of [
    ["Bash", "ls"],
    ["Bash", 'echo "akmon tool browser status"'],
    ["mcp__other-server__click", ""],
    ["Read", "akmon tool browser status"],
    ["WebFetch", ""],
  ]) {
    assert.equal(
      browserGuardResult(data, toolName, command, { actor: ACTORS.AUTONOMOUS, delegated: true }),
      null,
      toolName,
    );
  }
});

test("an ask nobody attends becomes a deny", () => {
  const flipped = {
    ...data,
    accessMatrix: { ...data.accessMatrix, developer: { ...data.accessMatrix.developer, browser_session: "ask" } },
  };
  const options = { actor: ACTORS.DEVELOPER, permissionMode: "default" };
  assert.equal(
    browserGuardResult(flipped, "mcp__akmon-browser__click", "", { ...options, attended: true })?.permissionDecision,
    "ask",
  );
  assert.equal(
    browserGuardResult(flipped, "mcp__akmon-browser__click", "", { ...options, attended: false })?.permissionDecision,
    "deny",
  );
});

const WRAPPED_DRIVES = [
  "npx -y -p akmon akmon tool browser open",
  "uv run --frozen --no-sync akmon tool browser open",
  "uv run python -m akmon tool browser open",
  "npm exec akmon tool browser status",
  "npm exec -- akmon tool browser status",
  "uvx akmon tool browser status",
  "pipx run akmon tool browser status",
  "bun js/tools/browser.mjs status",
  "bun run js/tools/browser.mjs status",
  "deno run --allow-all js/tools/browser.mjs status",
  "timeout 30 akmon tool browser open",
  "timeout -s KILL 30 node js/tools/browser.mjs status",
  "xargs akmon tool browser status",
  "xargs -n 1 akmon tool browser status",
  "nice -n 5 akmon tool browser status",
  "setsid akmon tool browser status",
  "stdbuf -oL akmon tool browser status",
  "/usr/bin/env node js/tools/browser.mjs status",
  "env -i akmon tool browser status",
  "env -u FOO akmon tool browser status",
  "command akmon tool browser status",
  "exec akmon tool browser status",
  "/usr/bin/node js/tools/browser.mjs status",
  "node.exe js/tools/browser.mjs status",
  "node22 js/tools/browser.mjs status",
  "python3.12 tools/browser.py status",
  "py tools/browser.py status",
  "node --import ./setup.mjs js/tools/browser.mjs status",
  "node --require ./setup.cjs js/tools/browser.mjs status",
  "node -r ./setup.cjs js/tools/browser.mjs status",
  "node --loader ./hooks.mjs js/tools/browser.mjs status",
  "timeout 30 bash -c 'akmon tool browser status'",
];

const WRAPPED_TEXT = [
  "node -e 'run()' js/tools/browser.mjs",
  "python3 -c 'run()' tools/browser.py",
  "python3 -m other tools/browser.py",
  "node --import ./setup.mjs js/other.mjs",
  "timeout 30 grep -n x js/tools/browser.mjs",
  "xargs echo akmon tool browser",
  "nice -n 5 echo akmon tool browser status",
  "env -i echo akmon tool browser status",
  "env -u FOO cat tools/browser.py",
  "node --test js/tools/browser/*.test.mjs",
  "npx --no-install oxfmt --check js/tools/browser.mjs",
  "tsc --noEmit js/tools/browser.mjs",
  "oxlint js/tools/browser.mjs",
  "git log -- js/tools/browser.mjs",
];

test("launchers, wrappers and interpreter spellings drive it", () => {
  for (const command of WRAPPED_DRIVES) {
    assert.equal(browserCommandDrives(data, command), true, command);
    assert.equal(
      browserGuardResult(data, "Bash", command, { actor: ACTORS.DEVELOPER, delegated: true })?.permissionDecision,
      "deny",
      command,
    );
  }
});

test("wrapped text and inline code do not drive it", () => {
  for (const command of WRAPPED_TEXT) {
    assert.equal(browserCommandDrives(data, command), false, command);
  }
});

const SPELLING_DRIVES = [
  "akmon tool 'brow'ser status",
  'akmon tool "brows"er status',
  "akmon tool brow\\ser status",
  "npm exec akmon -- tool browser status",
  "npx akmon -- tool browser status",
  "python3 -m akmon.cli tool browser status",
  "python3 -m akmon tool browser status",
  "python3 -m akmon.anything tool browser status",
  "node js/tools/./browser.mjs status",
  "node ./js/tools/browser.mjs status",
  "node ../akmon/js/tools/browser.mjs status",
  "python3 ./tools/../tools/browser.py status",
  "cd js/tools && node browser.mjs status",
  "cd tools && python3 browser.py status",
  "cd /opt/akmon/js/tools; node ./browser.mjs status",
  "bash -c 'cd js/tools && node browser.mjs status'",
];

const SPELLING_TEXT = [
  'echo "akmon tool browser"',
  "echo akmon tool browser",
  "echo 'brow'ser",
  "node --test js/tools/browser/*.test.mjs",
  "cd js/tools && node --test browser.test.mjs",
  "cd js/tools && grep -n x browser.mjs",
  "cd js/tools && cat browser.mjs",
  "cd js/tools && npx --no-install oxfmt browser.mjs",
  "git diff js/tools/browser.mjs",
  "cat <<'EOF'\nakmon tool browser\nEOF",
  "python3 -m pytest tools/browser.py",
  "npx --no-install oxlint -- js/tools/browser.mjs",
];

test("quoting, separators and path spellings still drive it", () => {
  for (const command of SPELLING_DRIVES) {
    assert.equal(browserCommandDrives(data, command), true, command);
    assert.equal(
      browserGuardResult(data, "Bash", command, { actor: ACTORS.DEVELOPER, delegated: true })?.permissionDecision,
      "deny",
      command,
    );
  }
});

test("a bare script name is the tool only where the command runs in the tools directory", () => {
  assert.equal(browserCommandDrives(data, "node browser.mjs status", "/repo/js/tools"), true);
  assert.equal(browserCommandDrives(data, "python3 browser.py status", "/repo/tools"), true);
  assert.equal(browserCommandDrives(data, "cd .. && node browser.mjs", "/repo/js/tools/sub"), true);
  assert.equal(browserCommandDrives(data, "node browser.mjs status", "/repo"), false);
  assert.equal(browserCommandDrives(data, "node browser.mjs status"), false);
  assert.equal(browserCommandDrives(data, "cd /repo && node browser.mjs status", "/repo/js/tools"), false);
  const result = browserGuardResult(data, "Bash", "node browser.mjs status", {
    actor: ACTORS.DEVELOPER,
    delegated: true,
    directory: "/repo/js/tools",
  });
  assert.equal(result?.permissionDecision, "deny");
});

test("the new spellings leave text and other programs silent", () => {
  for (const command of SPELLING_TEXT) {
    assert.equal(browserCommandDrives(data, command, "/repo/js/tools"), false, command);
  }
});

test("the strictest decision wins, and the first of equals", () => {
  const result = (/** @type {string} */ decision, /** @type {string} */ reason) =>
    new HookResult({ eventName: "PreToolUse", permissionDecision: decision, permissionReason: reason });
  const ask = result("ask", "a");
  const deny = result("deny", "d");
  assert.equal(strictestResult([null, null]), null);
  assert.equal(strictestResult([ask, null]), ask);
  assert.equal(strictestResult([ask, deny]), deny);
  assert.equal(strictestResult([deny, ask]), deny);
  assert.equal(strictestResult([deny, result("deny", "e")]), deny);
});

test("a git ask does not hide the browser deny", () => {
  const command = "git commit -m x && akmon tool browser status";
  const directory = mkdtempSync(join(tmpdir(), "akmon-browser-guard-"));
  try {
    const git = gitCommitGuardResult(data, command, { directory, attended: true });
    assert.equal(git?.permissionDecision, "ask");
    const browser = browserGuardResult(data, "Bash", command, { actor: ACTORS.DEVELOPER, delegated: true });
    const chosen = strictestResult([git, browser]);
    assert.equal(chosen?.permissionDecision, "deny");
    assert.match(chosen?.permissionReason ?? "", /delegated agent/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

/**
 * A scratch project, with an attach record or without.
 * @param {boolean} attached
 * @returns {string}
 */
function project(attached) {
  const directory = mkdtempSync(join(tmpdir(), "akmon-browser-guard-"));
  writeFileSync(join(directory, "AGENTS.md"), "# project\n");
  writeFileSync(join(directory, ".aitna-root"), "_aitna\n");
  if (attached) {
    mkdirSync(join(directory, "_aitna", ".local", ".browser"), { recursive: true });
    writeFileSync(join(directory, "_aitna", ".local", ".browser", "attach.json"), "{}");
  }
  return directory;
}

test("in attach mode the agent never closes the page, whoever it is", () => {
  const directory = project(true);
  try {
    for (const toolName of ["mcp__akmon-browser__close_page", "mcp__akmon-browser__close_window"]) {
      for (const options of [{}, { delegated: true }, { actor: ACTORS.AUTONOMOUS }]) {
        const result = browserGuardResult(data, toolName, "", { ...options, directory });
        assert.equal(result?.permissionDecision, "deny", toolName);
      }
    }
    const developer = browserGuardResult(data, "mcp__akmon-browser__close_page", "", { directory });
    assert.match(developer?.permissionReason ?? "", /attach mode/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("without an attach a developer closes pages, and other tools are not held", () => {
  const detached = project(false);
  const attached = project(true);
  try {
    assert.equal(browserGuardResult(data, "mcp__akmon-browser__close_page", "", { directory: detached }), null);
    assert.equal(browserGuardResult(data, "mcp__akmon-browser__take_snapshot", "", { directory: attached }), null);
    assert.equal(browserGuardResult(data, "mcp__other-server__close_page", "", { directory: attached }), null);
  } finally {
    rmSync(detached, { recursive: true, force: true });
    rmSync(attached, { recursive: true, force: true });
  }
});

test("an unresolvable project skips the attach check", () => {
  const directory = mkdtempSync(join(tmpdir(), "akmon-browser-guard-"));
  try {
    assert.equal(browserGuardResult(data, "mcp__akmon-browser__close_page", "", { directory }), null);
    assert.equal(browserGuardResult(data, "mcp__akmon-browser__close_page"), null);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
