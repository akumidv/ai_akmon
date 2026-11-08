/**
 * node:test for `js/hooks/work-style.mjs` and the `work-style` route of `js/hooks/codex-hook.mjs`
 * (ADR 0031/D03), plus the SessionStart line — the hooks run as the harness runs them. The Python
 * twin is `meta/tests/test_work_style.py`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { readData, resolve, WorkStyle } from "../common/work_style.mjs";
import { sessionStartResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

const CLAUDE_HOOK = fileURLToPath(new URL("./work-style.mjs", import.meta.url));
const CODEX_HOOK = fileURLToPath(new URL("./codex-hook.mjs", import.meta.url));
const DATA = readData();

/** A scratch project with the default dev root. */
function project(record = 'mount = "package"\n') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-hook-")));
  fs.mkdirSync(path.join(root, "_aitna"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# a\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), record);
  return root;
}

/** @param {string} root @param {string} name */
const local = (root, name) => path.join(root, "_aitna", ".local", name);

/**
 * One payload through a hook script.
 * @param {string} script
 * @param {string[]} args
 * @param {string} root
 * @param {Record<string, unknown>} payload
 */
function run(script, args, root, payload) {
  const env = { ...process.env };
  delete env.CLAUDE_PROJECT_DIR;
  const done = spawnSync(process.execPath, [script, ...args], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    cwd: root,
    env,
  });
  return done;
}

test("the Claude hook records a typed switch and answers on both channels", () => {
  const root = project();
  const done = run(CLAUDE_HOOK, [], root, {
    hook_event_name: "UserPromptSubmit",
    session_id: "s1",
    prompt: "/style controlling",
    cwd: root,
  });
  assert.equal(done.status, 0, done.stderr);
  assert.equal(done.stderr, "");
  const document = JSON.parse(done.stdout);
  assert.equal(document.hookSpecificOutput.hookEventName, "UserPromptSubmit");
  assert.equal(document.hookSpecificOutput.additionalContext, document.systemMessage);
  assert.match(document.systemMessage, /Work style recorded for this session: controlling/);
  assert.deepEqual(resolve(root, "s1", DATA), new WorkStyle("controlling", "session"));
});

test("the Claude hook names the allowed values for an invalid one and records nothing", () => {
  const root = project();
  const done = run(CLAUDE_HOOK, [], root, { session_id: "s1", prompt: "/style fast", cwd: root });
  assert.match(JSON.parse(done.stdout).hookSpecificOutput.additionalContext, /delegating, controlling/);
  assert.equal(fs.existsSync(local(root, "work-sessions.json")), false);
});

for (const fields of [
  { session_id: "s1", prompt: "write the tests" },
  { session_id: "s1" },
  { session_id: "s1", prompt: 3 },
  {},
]) {
  test(`the Claude hook is silent and writes nothing for ${JSON.stringify(fields)}`, () => {
    const root = project();
    const done = run(CLAUDE_HOOK, [], root, { cwd: root, ...fields });
    assert.equal(done.status, 0, done.stderr);
    assert.equal(done.stdout, "");
    assert.equal(fs.existsSync(path.join(root, "_aitna", ".local")), false);
  });
}

test("the Claude hook with no project root is silent and writes no file", () => {
  const bare = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-bare-")));
  const done = run(CLAUDE_HOOK, [], bare, { session_id: "s1", prompt: "/style controlling", cwd: bare });
  assert.equal(done.stdout, "");
  assert.deepEqual(fs.readdirSync(bare), []);
});

test("the Claude hook is crash-open when the store cannot be written", () => {
  const root = project();
  fs.writeFileSync(path.join(root, "_aitna", ".local"), "a file where the local layer should be");
  const done = run(CLAUDE_HOOK, [], root, { session_id: "s1", prompt: "/style controlling", cwd: root });
  assert.equal(done.status, 0);
  assert.deepEqual(Object.keys(JSON.parse(done.stdout)), ["systemMessage"]);
  assert.match(done.stderr, /^akmon work-style hook: /);
});

/** The `UserPromptSubmit` payload codex-cli 0.153.4 sends (M65): the exact key set, nothing more. */
function codexPayload(/** @type {string} */ root, /** @type {string} */ prompt) {
  return {
    hook_event_name: "UserPromptSubmit",
    session_id: "019e0000-aaaa-7000-8000-000000000001",
    turn_id: "019e0000-bbbb-7000-8000-000000000002",
    prompt,
    cwd: root,
    transcript_path: path.join(root, "rollout.jsonl"),
    model: "gpt-5.5",
    permission_mode: "default",
  };
}

test("the Codex route records the style from the M65 payload and prints the model half only", () => {
  const root = project();
  const payload = codexPayload(root, "/style controlling");
  const done = run(CODEX_HOOK, ["work-style"], root, payload);
  assert.equal(done.status, 0, done.stderr);
  const document = JSON.parse(done.stdout);
  assert.deepEqual(Object.keys(document), ["hookSpecificOutput"], "Codex has no owner channel");
  assert.equal(document.hookSpecificOutput.hookEventName, "UserPromptSubmit");
  assert.match(document.hookSpecificOutput.additionalContext, /controlling/);
  assert.deepEqual(JSON.parse(fs.readFileSync(local(root, "work-sessions.json"), "utf8")), {
    sessions: { [payload.session_id]: "controlling" },
  });
  assert.deepEqual(resolve(root, payload.session_id, DATA), new WorkStyle("controlling", "session"));
});

test("the Codex route is silent on any other prompt", () => {
  const root = project();
  const done = run(CODEX_HOOK, ["work-style"], root, codexPayload(root, "fix the failing test"));
  assert.equal(done.status, 0, done.stderr);
  assert.equal(done.stdout, "");
  assert.equal(fs.existsSync(path.join(root, "_aitna", ".local")), false);
});

test("the Codex route skips an unidentified session and says so", () => {
  const root = project();
  const { session_id: _omitted, ...payload } = codexPayload(root, "/style controlling");
  const done = run(CODEX_HOOK, ["work-style"], root, payload);
  assert.match(JSON.parse(done.stdout).hookSpecificOutput.additionalContext, /no session id/);
  assert.equal(fs.existsSync(local(root, "work-sessions.json")), false);
});

/** A project with one dev agent charter, so `sessionStartResult` builds its full context. */
function withAgent(/** @type {string} */ record) {
  const root = project(record);
  fs.mkdirSync(path.join(root, "_aitna", "agents", "development"), { recursive: true });
  fs.writeFileSync(path.join(root, "_aitna", "agents", "development", "README.md"), "# development\n");
  return root;
}

/** @param {import("./hook_core.mjs").HookResult | null} result */
function styleLine(result) {
  const lines = String(result?.additionalContext)
    .split("\n")
    .filter((line) => line.startsWith("work style: "));
  assert.equal(lines.length, 1);
  return lines[0];
}

test("SessionStart states the default, then names the level that decided", () => {
  const data = lazyHookData();
  const root = withAgent('mount = "package"\n');
  assert.equal(styleLine(sessionStartResult(data, root, "s1")), "work style: delegating (default)");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), 'mount = "package"\n[work]\nstyle = "controlling"\n');
  assert.equal(styleLine(sessionStartResult(data, root)), "work style: controlling (from _aitna/.akmon.toml [work])");
  fs.mkdirSync(path.join(root, "_aitna", ".local"), { recursive: true });
  fs.writeFileSync(local(root, "work.json"), '{"style": "delegating"}');
  assert.equal(styleLine(sessionStartResult(data, root)), "work style: delegating (from _aitna/.local/work.json)");
  fs.writeFileSync(local(root, "work-sessions.json"), '{"sessions": {"s1": "controlling"}}');
  assert.equal(
    styleLine(sessionStartResult(data, root, "s1")),
    "work style: controlling (set in this session with /style)",
  );
  assert.equal(
    styleLine(sessionStartResult(data, root, "s2")),
    "work style: delegating (from _aitna/.local/work.json)",
  );
});
