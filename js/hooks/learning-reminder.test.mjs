/**
 * node:test for `js/hooks/learning-reminder.mjs` (C177) — the hook run as the harness runs it:
 * records the session, speaks once a run is due, stays silent on a compaction, and is crash-open on
 * a broken record or an unwritable layer.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { readData, readThresholds, readState, Thresholds } from "../common/learning.mjs";
import { learningReminderResult, payloadEvent } from "./learning-reminder.mjs";

const _HOOK = fileURLToPath(new URL("./learning-reminder.mjs", import.meta.url));
const DATA = readData();

/** A scratch project whose record asks for a reminder at two sessions. */
function project(record = '[learning]\nreminder_sessions = "2"\n') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-learning-hook-")));
  fs.mkdirSync(path.join(root, "_aitna"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# a\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), record);
  return { root, state: path.join(root, "_aitna", ".local", "learning.json") };
}

/**
 * One SessionStart event through the hook.
 * @param {{root: string}} scratch
 * @param {Record<string, unknown>} fields
 * @param {Record<string, string>} [extraEnv]
 */
function start(scratch, fields, extraEnv = {}) {
  const payload = JSON.stringify({ hook_event_name: "SessionStart", cwd: scratch.root, ...fields });
  /** @type {Record<string, string | undefined>} */
  const env = { ...process.env };
  delete env.CLAUDE_PROJECT_DIR;
  delete env[DATA.second_opinion_variable];
  delete env[DATA.attended_variable];
  Object.assign(env, extraEnv);
  const run = spawnSync(process.execPath, [_HOOK], { input: payload, encoding: "utf8", cwd: scratch.root, env });
  assert.equal(run.status, 0, run.stderr);
  return run;
}

test("silent below the threshold, then one reminder on both channels", () => {
  const scratch = project();
  assert.equal(start(scratch, { session_id: "s1", source: "startup" }).stdout, "");
  assert.equal(start(scratch, { session_id: "s2", source: "startup" }).stdout, "", "only s1 has passed");
  const run = start(scratch, { session_id: "s3", source: "startup" });
  assert.equal(run.stderr, "");
  const document = JSON.parse(run.stdout);
  assert.equal(document.hookSpecificOutput.hookEventName, "SessionStart");
  assert.match(
    document.hookSpecificOutput.additionalContext,
    /^\[akmon\] Learning reminder: 2 sessions and 0 days have passed since akmon began counting/,
  );
  assert.equal(
    document.systemMessage,
    "[akmon] learning: 2 sessions and 0 days since akmon began counting (no learning run is recorded yet) — run the `learning` skill to review them.",
  );
  assert.deepEqual([...readState(scratch.state).sessions], ["s1", "s2", "s3"]);
});

test("a second-opinion run is neither recorded nor reminded; an unattended run is recorded, not reminded", () => {
  const scratch = project('[learning]\nreminder_sessions = "1"\n');
  start(scratch, { session_id: "s0", source: "startup" });
  const opinion = start(scratch, { session_id: "so1", source: "startup" }, { [DATA.second_opinion_variable]: "1" });
  assert.equal(opinion.stdout, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s0"]);
  const unattended = start(scratch, { session_id: "p1", source: "startup" }, { [DATA.attended_variable]: "0" });
  assert.equal(unattended.stdout, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s0", "p1"]);
  assert.notEqual(
    start(scratch, { session_id: "s1", source: "startup" }, { [DATA.attended_variable]: "1" }).stdout,
    "",
  );
});

test("a resumed session keeps its id and is not counted twice", () => {
  const scratch = project();
  start(scratch, { session_id: "s1", source: "startup" });
  assert.equal(start(scratch, { session_id: "s1", source: "resume" }).stdout, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s1"]);
});

test("a compaction is silent even when a run is due, and an unidentified session is not recorded", () => {
  const scratch = project();
  start(scratch, { session_id: "s1", source: "startup" });
  assert.equal(start(scratch, { session_id: "s2", source: "compact" }).stdout, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s1", "s2"]);
  assert.notEqual(start(scratch, { session_id: "s3", source: "startup" }).stdout, "");
  const before = fs.readFileSync(scratch.state, "utf8");
  assert.notEqual(start(scratch, { source: "startup" }).stdout, "", "still due: it reads the record");
  assert.equal(fs.readFileSync(scratch.state, "utf8"), before);
});

test("a corrupt record is treated as empty and rewritten, never a crash", () => {
  const scratch = project();
  fs.mkdirSync(path.dirname(scratch.state), { recursive: true });
  fs.writeFileSync(scratch.state, "{ not json");
  const run = start(scratch, { session_id: "s1", source: "startup" });
  assert.equal(run.stdout, "");
  assert.equal(run.stderr, "");
  assert.deepEqual([...readState(scratch.state).sessions], ["s1"]);
  assert.equal(JSON.parse(fs.readFileSync(scratch.state, "utf8")).last_run, null);
});

test("an unwritable layer is the crash notice and exit 0", { skip: process.getuid?.() === 0 }, () => {
  const scratch = project();
  fs.mkdirSync(path.dirname(scratch.state), { recursive: true });
  fs.chmodSync(path.dirname(scratch.state), 0o500);
  try {
    const run = start(scratch, { session_id: "s1", source: "startup" });
    assert.equal(run.stderr, "akmon learning-reminder hook: PermissionError\n");
    assert.match(JSON.parse(run.stdout).systemMessage, /the learning-reminder hook failed \(PermissionError\)/);
  } finally {
    fs.chmodSync(path.dirname(scratch.state), 0o700);
  }
});

test("with no project root the hook is silent and writes nothing: there is no local layer to record in", () => {
  const lone = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-learning-lone-")));
  try {
    for (const fields of [
      { session_id: "s1", source: "startup" },
      { session_id: "s2", source: "startup" },
      { session_id: "s3", source: "startup" },
    ]) {
      const run = start({ root: lone }, fields);
      assert.equal(run.stdout, "");
      assert.equal(run.stderr, "");
    }
    assert.deepEqual(fs.readdirSync(lone), []);
  } finally {
    fs.rmSync(lone, { recursive: true, force: true });
  }
});

test("learningReminderResult is the SessionStart result, or null when nothing is due", () => {
  const scratch = project("");
  const now = new Date(Date.UTC(2026, 9, 28));
  const few = new Thresholds(1, 7);
  const result = (/** @type {Record<string, unknown>} */ payload, /** @type {Record<string, string>} */ environ = {}) =>
    learningReminderResult(payloadEvent(payload, environ, DATA), scratch.root, DATA, few, now);
  assert.equal(result({ session_id: 5 }), null, "a non-string id is unidentified");
  assert.equal(result({ session_id: "s0", source: "startup" }), null);
  assert.equal(result({ session_id: "so", source: "startup" }, { [DATA.second_opinion_variable]: "1" }), null);
  const reminder = result({ session_id: "s1", source: "startup" });
  assert.equal(reminder?.eventName, "SessionStart");
  assert.match(reminder?.additionalContext ?? "", /^\[akmon\] Learning reminder: 1 session and 0 days have passed/);
  assert.match(reminder?.systemMessage ?? "", /^\[akmon\] learning: 1 session and 0 days since akmon began counting/);
  assert.deepEqual(readThresholds(scratch.root, DATA), new Thresholds(10, 7));
});
