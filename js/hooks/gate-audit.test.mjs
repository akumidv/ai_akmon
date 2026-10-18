/**
 * node:test for `js/hooks/gate-audit.mjs` (C25 review D4) — the hook run as the harness runs it:
 * one hold per gate, keyed by the counted material rather than its count, and crash-open when the
 * tree under it is broken. The markers land in a private `TMPDIR`, so a run never sees another's.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const _HOOK = fileURLToPath(new URL("./gate-audit.mjs", import.meta.url));

const _THREE = "## Findings\n\n- the sync path drops the marker\n- the verify gate passes\n- the record reseeds\n";
const _FOUR = `${_THREE}- the log loses a row\n`;
const _OTHER_THREE = "## Findings\n\n- one\n- two\n- three\n";

/**
 * A package-mode project whose transcript declares the review role, and a private tempdir.
 * @returns {{root: string, tmp: string}}
 */
function _project() {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-gate-audit-")));
  fs.mkdirSync(posix.join(root, "_aitna"));
  fs.mkdirSync(posix.join(root, "tmp"));
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.writeFileSync(posix.join(root, "_aitna", ".akmon.toml"), 'mount = "package"\n');
  const declaration = {
    type: "assistant",
    isSidechain: false,
    message: { content: [{ type: "text", text: "🧭 agent: review — gate" }] },
  };
  fs.writeFileSync(posix.join(root, "transcript.jsonl"), `${JSON.stringify(declaration)}\n`);
  return { root, tmp: posix.join(root, "tmp") };
}

/**
 * One Stop event through the hook.
 * @param {{root: string, tmp: string}} project
 * @param {string} message the turn's `last_assistant_message`
 * @param {{session?: string, active?: boolean}} [options]
 */
function _stop(project, message, { session = "sess-ga", active = false } = {}) {
  const payload = JSON.stringify({
    hook_event_name: "Stop",
    stop_hook_active: active,
    session_id: session,
    cwd: project.root,
    transcript_path: posix.join(project.root, "transcript.jsonl"),
    last_assistant_message: message,
  });
  /** @type {Record<string, string | undefined>} */
  const env = { ...process.env, TMPDIR: project.tmp };
  delete env.CLAUDE_PROJECT_DIR;
  const run = spawnSync(process.execPath, [_HOOK], { input: payload, encoding: "utf8", cwd: project.root, env });
  assert.equal(run.status, 0, run.stderr);
  return run;
}

/** Whether a run held the turn. */
function _held(/** @type {{stdout: string}} */ run) {
  return run.stdout !== "" && JSON.parse(run.stdout).decision === "block";
}

test("the same material is held once, however the count moved in between", () => {
  const project = _project();
  try {
    const first = _stop(project, _THREE);
    assert.ok(_held(first), first.stdout);
    assert.match(JSON.parse(first.stdout).reason, /carries 3 findings as the review role/);
    assert.equal(_stop(project, _THREE).stdout, "", "a second identical turn is let through");
    assert.ok(_held(_stop(project, _FOUR)), "new material is a new gate");
    assert.equal(_stop(project, _THREE).stdout, "", "3 → 4 → 3 does not hold the first material again");
  } finally {
    fs.rmSync(project.root, { recursive: true, force: true });
  }
});

test("the same count over different material is a new gate", () => {
  const project = _project();
  try {
    assert.ok(_held(_stop(project, _THREE)));
    assert.ok(_held(_stop(project, _OTHER_THREE)));
    assert.ok(_held(_stop(project, _THREE, { session: "sess-other" })), "markers are per session");
  } finally {
    fs.rmSync(project.root, { recursive: true, force: true });
  }
});

test("a turn that answers a held one is never held", () => {
  const project = _project();
  try {
    assert.equal(_stop(project, _THREE, { active: true }).stdout, "");
    assert.ok(_held(_stop(project, _THREE)), "the answer claimed no marker");
  } finally {
    fs.rmSync(project.root, { recursive: true, force: true });
  }
});

test("a broken tree crashes open: exit 0, a diagnostic, no hold", () => {
  const project = _project();
  try {
    fs.writeFileSync(posix.join(project.root, "_aitna", "model-routing.json"), "{not json");
    const run = _stop(project, _THREE);
    assert.notEqual(run.stderr, "", "the failure is reported");
    const answer = JSON.parse(run.stdout);
    assert.equal(answer.decision, undefined, "a crash never holds the turn");
    assert.match(answer.systemMessage, /gate-audit/);
  } finally {
    fs.rmSync(project.root, { recursive: true, force: true });
  }
});
