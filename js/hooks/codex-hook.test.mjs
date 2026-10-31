/**
 * node:test for the `learning-reminder` route of `js/hooks/codex-hook.mjs` (C177): Codex prints
 * only `additionalContext` (no owner channel), and a payload without a session id is not recorded.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { readData, readState } from "../common/learning.mjs";

const DATA = readData();
const _HOOK = fileURLToPath(new URL("./codex-hook.mjs", import.meta.url));

/** A scratch project whose record asks for a reminder at two sessions. */
function project() {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-codex-learning-")));
  fs.mkdirSync(path.join(root, "_aitna"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# a\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), '[learning]\nreminder_sessions = "2"\n');
  return { root, state: path.join(root, "_aitna", "local", "learning.json") };
}

/**
 * One `learning-reminder` event through the hook.
 * @param {{root: string}} scratch
 * @param {Record<string, unknown>} fields
 * @param {Record<string, string>} [extraEnv]
 */
function route(scratch, fields, extraEnv = {}) {
  const payload = JSON.stringify({ hook_event_name: "SessionStart", cwd: scratch.root, ...fields });
  const run = spawnSync(process.execPath, [_HOOK, "learning-reminder"], {
    input: payload,
    encoding: "utf8",
    cwd: scratch.root,
    env: { ...process.env, ...extraEnv },
  });
  assert.equal(run.status, 0, run.stderr);
  return run;
}

test("the route is silent below the threshold, then prints the model half only", () => {
  const scratch = project();
  assert.equal(route(scratch, { session_id: "s1", source: "startup" }).stdout, "");
  assert.equal(route(scratch, { session_id: "s2", source: "startup" }).stdout, "", "only s1 has passed");
  const run = route(scratch, { session_id: "s3", source: "startup" });
  assert.equal(run.stderr, "");
  const document = JSON.parse(run.stdout);
  assert.deepEqual(Object.keys(document), ["hookSpecificOutput"], "no systemMessage: Codex has no owner channel");
  assert.equal(document.hookSpecificOutput.hookEventName, "SessionStart");
  assert.match(
    document.hookSpecificOutput.additionalContext,
    /^\[akmon\] Learning reminder: 2 sessions and 0 days have passed since akmon began counting/,
  );
});

test("a second-opinion run is neither recorded nor reminded on the Codex route", () => {
  const scratch = project();
  route(scratch, { session_id: "s1", source: "startup" });
  route(scratch, { session_id: "s2", source: "startup" });
  const opinion = route(scratch, { session_id: "so", source: "startup" }, { [DATA.second_opinion_variable]: "1" });
  assert.equal(opinion.stdout, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s1", "s2"]);
});

test("a compaction is silent, and a payload without a session id is not recorded", () => {
  const scratch = project();
  route(scratch, { session_id: "s1", source: "startup" });
  assert.equal(route(scratch, { session_id: "s2", source: "compact" }).stdout, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s1", "s2"]);
  assert.notEqual(route(scratch, { source: "startup" }).stdout, "", "due, and read from the record");
  assert.deepEqual([...readState(scratch.state).sessions], ["s1", "s2"], "the unidentified session was not recorded");
});

test("a broken record is rewritten, not a crash", () => {
  const scratch = project();
  fs.mkdirSync(path.dirname(scratch.state), { recursive: true });
  fs.writeFileSync(scratch.state, "[[[");
  const run = route(scratch, { session_id: "s1", source: "startup" });
  assert.equal(run.stderr, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s1"]);
});
