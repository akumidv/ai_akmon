/**
 * node:test for `js/hooks/model-routing.mjs` — what the corpus scenarios cannot hold cheaply:
 * the settings file the hook compares the recorded orchestrator against is parsed as Python's
 * `json.loads` parses it (C115). The config is written by the model-routing init tool against
 * the live registry, so the binding is fresh and only the settings model can make it stale.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const _HOOK = fileURLToPath(new URL("./model-routing.mjs", import.meta.url));
const _INIT = fileURLToPath(new URL("../tools/model_routing/init.mjs", import.meta.url));

/** A package-mode project with a fresh binding for `opus`. */
function _project() {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-model-routing-")));
  fs.mkdirSync(posix.join(root, "_aitna"));
  fs.mkdirSync(posix.join(root, ".claude"));
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  fs.writeFileSync(posix.join(root, "_aitna", ".akmon.toml"), 'mount = "package"\n');
  const init = spawnSync(process.execPath, [_INIT, "--project-root", root, "--orchestrator", "opus"], {
    encoding: "utf8",
  });
  assert.equal(init.status, 0, init.stderr);
  return root;
}

/** The SessionStart answer for `root`, as the harness reads it. */
function _sessionStart(/** @type {string} */ root) {
  const payload = JSON.stringify({ hook_event_name: "SessionStart", session_id: "sess-c115", cwd: root });
  const run = spawnSync(process.execPath, [_HOOK], { input: payload, encoding: "utf8", cwd: root });
  assert.equal(run.status, 0, run.stderr);
  return JSON.parse(run.stdout).hookSpecificOutput.additionalContext;
}

test("a settings model beside a NaN or Infinity literal is read, as json.loads reads it (C115)", () => {
  const root = _project();
  const settings = posix.join(root, ".claude", "settings.json");
  try {
    for (const literal of ["NaN", "Infinity", "-Infinity"]) {
      fs.writeFileSync(settings, `{"model": "sonnet", "x": ${literal}}`);
      assert.match(_sessionStart(root), /settings default model 'sonnet' differs/, literal);
    }
    // Text that is no JSON to either parser is still skipped: the status line, no mismatch.
    fs.writeFileSync(settings, '{"model": "sonnet", "x": nan}');
    assert.match(_sessionStart(root), /^\[akmon\] model routing: /);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

const _BAD_OVERLAY =
  "akmon model-routing hook: the routing overlay _aitna/model-routing.json is not a valid JSON object; " +
  "repair or delete it (it is hand-owned, so akmon never rewrites it) — model routing is silent for this session";

/** One event through the hook on a project whose routing overlay does not parse. */
function _withBadOverlay(/** @type {string} */ event) {
  const root = _project();
  try {
    fs.writeFileSync(posix.join(root, "_aitna", "model-routing.json"), "{ not json");
    const payload = JSON.stringify({ hook_event_name: event, session_id: "sess-overlay", cwd: root });
    const run = spawnSync(process.execPath, [_HOOK], { input: payload, encoding: "utf8", cwd: root });
    assert.equal(run.status, 0, run.stderr);
    return run;
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("a bad routing overlay at SessionStart tells the owner on both channels which file to repair", () => {
  const run = _withBadOverlay("SessionStart");
  const document = JSON.parse(run.stdout);
  assert.equal(document.systemMessage, _BAD_OVERLAY);
  assert.deepEqual(document.hookSpecificOutput, { hookEventName: "SessionStart", additionalContext: _BAD_OVERLAY });
  assert.equal(run.stderr, `${_BAD_OVERLAY}\n`);
});

test("a bad routing overlay at a later prompt is silent beyond one stderr line", () => {
  const run = _withBadOverlay("UserPromptSubmit");
  assert.equal(run.stdout, "");
  assert.equal(run.stderr, `${_BAD_OVERLAY}\n`);
});
