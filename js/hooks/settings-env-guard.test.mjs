/**
 * node:test for `js/hooks/settings-env-guard.mjs` — the twin of the hook-script half of
 * `meta/tests/test_harness_settings.py` (ADR 0031/D07, D-C203-ACTOR-WRITE), run as a process the way
 * the wiring runs it.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HOOK = posix.join(posix.dirname(fileURLToPath(import.meta.url)), "settings-env-guard.mjs");

/**
 * Run the hook on `input` (a payload, or raw text).
 * @param {unknown} input
 * @returns {{stdout: string, stderr: string, status: number | null}}
 */
function run(input) {
  const text = typeof input === "string" ? input : JSON.stringify(input);
  const result = spawnSync("node", [HOOK], { input: text, encoding: "utf8" });
  return { stdout: result.stdout, stderr: result.stderr, status: result.status };
}

/**
 * A `.claude/settings.json` holding `text` (none when `null`), in a fresh directory removed after.
 * @param {string | null} text
 * @param {(path: string) => void} body
 */
function withSettings(text, body) {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-settings-env-"));
  try {
    const path = posix.join(dir, ".claude", "settings.json");
    fs.mkdirSync(posix.dirname(path));
    if (text !== null) {
      fs.writeFileSync(path, text);
    }
    body(path);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test("the hook denies a write that changes the env of the file on disk", () => {
  withSettings('{"hooks": {}}', (path) => {
    const result = run({
      tool_name: "Write",
      tool_input: { file_path: path, content: '{"env": {"AKMON_ACTOR": "autonomous"}}' },
    });
    assert.equal(result.status, 0);
    assert.equal(result.stderr, "");
    const output = JSON.parse(result.stdout).hookSpecificOutput;
    assert.equal(output.hookEventName, "PreToolUse");
    assert.equal(output.permissionDecision, "deny");
    assert.ok(output.permissionDecisionReason.includes(path));
  });
});

test("the hook denies an edit and a multiedit the same way", () => {
  withSettings('{"env": {"A": "1"}, "x": 1}', (path) => {
    const change = { old_string: '"A": "1"', new_string: '"A": "2"' };
    const other = { old_string: '"x": 1', new_string: '"x": 2' };
    for (const payload of [
      { tool_name: "Edit", tool_input: { file_path: path, ...change } },
      { tool_name: "MultiEdit", tool_input: { file_path: path, edits: [other, change] } },
    ]) {
      const output = JSON.parse(run(payload).stdout).hookSpecificOutput;
      assert.equal(output.permissionDecision, "deny", payload.tool_name);
    }
  });
});

test("the hook passes an edit that leaves the env identical", () => {
  withSettings('{"env": {"A": "1"}, "x": 1}', (path) => {
    const toolInput = { file_path: path, old_string: '"x": 1', new_string: '"x": 2' };
    assert.equal(run({ tool_name: "Edit", tool_input: toolInput }).stdout, "");
  });
});

test("the hook creates a settings file without an env and denies one with", () => {
  withSettings(null, (path) => {
    const ok = { tool_name: "Write", tool_input: { file_path: path, content: '{"permissions": {}}' } };
    assert.equal(run(ok).stdout, "");
    const bad = { tool_name: "Write", tool_input: { file_path: path, content: '{"env": {"A": "1"}}' } };
    assert.equal(JSON.parse(run(bad).stdout).hookSpecificOutput.permissionDecision, "deny");
  });
});

test("the hook ignores what is no edit of a settings file", () => {
  for (const payload of [
    { tool_name: "Bash", tool_input: { command: "echo x > .claude/settings.json" } },
    { tool_name: "Read", tool_input: { file_path: ".claude/settings.json" } },
    { tool_name: "Write", tool_input: "not an object" },
    { tool_name: "Write", tool_input: { file_path: "/p/src/x.py", content: "x" } },
    { tool_name: "Write" },
    {},
  ]) {
    assert.equal(run(payload).stdout, "", JSON.stringify(payload));
  }
  assert.equal(run("not json").stdout, "");
});

test("the hook treats an unreadable file as absent", () => {
  withSettings(null, (path) => {
    fs.writeFileSync(path, Buffer.from([0xff, 0xfe, 0x00, 0x20, 0x6e]));
    const payload = { tool_name: "Write", tool_input: { file_path: path, content: '{"permissions": {}}' } };
    assert.equal(run(payload).stdout, "");
  });
});
