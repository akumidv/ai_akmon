/**
 * node:test for `js/hooks/session_start_text.mjs` (A49, ADR 0012 F18, D-A49-HOOKCOUNT): the hook text
 * the always-loaded counter adds is built from the functions the hooks call, writes nothing, and is
 * the same text the hook injects. The Python twin is `meta/tests/test_session_start_text.py`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import { readData, readThresholds, reminderCeiling, reminderTexts, Due, Thresholds } from "../common/learning.mjs";
import {
  initInstruction,
  loadRegistry,
  localConfig,
  computeBinding,
  sessionStartCeiling,
  staleness,
  statusBlock,
  statusLines,
  toolCommandCeiling,
} from "../tools/model_routing/routing.mjs";
import {
  akmonRuntimeRoot,
  sessionStartContext,
  sessionStartResult,
  staleGuardrailCeiling,
  staleGuardrailNotice,
} from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";
import { sessionStartMembers } from "./session_start_text.mjs";

const data = lazyHookData();

/** A scratch project with one dev-layer agent charter and one materialized guardrail. */
function withProject(/** @type {(root: string) => void} */ body) {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-session-start-text-")));
  try {
    fs.mkdirSync(posix.join(root, "_aitna", "agents", "development"), { recursive: true });
    fs.writeFileSync(posix.join(root, "_aitna", "agents", "development", "README.md"), "# development\n");
    fs.mkdirSync(posix.join(root, "_aitna", ".akmon", "guardrails"), { recursive: true });
    fs.writeFileSync(posix.join(root, "_aitna", ".akmon", "guardrails", "_common.md"), "old text\n");
    body(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

/** @param {string} root */
function snapshot(root) {
  /** @type {Record<string, string>} */
  const files = {};
  /** @param {string} dir */
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const path = posix.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(path);
      } else {
        files[path] = fs.readFileSync(path, "utf8");
      }
    }
  };
  walk(root);
  return files;
}

test("the three session-start hooks are members", () => {
  withProject((root) => {
    assert.deepEqual(
      sessionStartMembers(data, root).map((member) => member.name),
      ["hook: session-start-agent", "hook: model-routing", "hook: learning-reminder"],
    );
  });
});

test("counting the hooks writes nothing", () => {
  withProject((root) => {
    const before = snapshot(root);
    sessionStartMembers(data, root);
    assert.deepEqual(snapshot(root), before);
  });
});

test("the text a hook injects is the text counted", () => {
  withProject((root) => {
    const members = sessionStartMembers(data, root);
    const text = (/** @type {string} */ name) => members.find((member) => member.name === `hook: ${name}`)?.text;
    const ceiling = staleGuardrailCeiling(data, root);
    assert.notEqual(ceiling, null);
    assert.equal(text("session-start-agent"), sessionStartContext(data, root, null, ceiling));
    assert.ok(ceiling?.includes("guardrails/_common.md"));
    assert.equal(
      sessionStartResult(data, root)?.additionalContext,
      sessionStartContext(data, root, null, staleGuardrailNotice(data, root)),
    );
    const thresholds = readThresholds(root, data.learning);
    const wordings = [true, false].map(
      (sinceRun) =>
        reminderTexts(
          new Due(Number(thresholds.reminderSessions), Number(thresholds.reminderDays), sinceRun),
          data.learning,
        )[0],
    );
    assert.ok(wordings.includes(/** @type {string} */ (text("learning-reminder"))));
  });
});

test("the status lines are the status block with the second-opinion pair resolved", () => {
  const registry = loadRegistry(data.agents, akmonRuntimeRoot("/nonexistent"));
  const binding = computeBinding(data.agents, registry, "opus", null, "anthropic", null);
  const config = localConfig(data.agents, binding, registry, { secondOpinion: false, available: null });
  const lines = statusLines(data.agents, data.runtime, config, registry, "cmd", null);
  const fixed = /** @type {[string, string | null]} */ (["second-opinion=x (off)", null]);
  const block = statusBlock(data.agents, config, registry, "cmd", fixed);
  assert.equal(lines.length, block.length);
  assert.deepEqual(lines.slice(1), block.slice(1)); // only the first line carries the second-opinion display
});

test("the learning ceiling is the longer wording and reads no record", () => {
  const learning = readData();
  const thresholds = new Thresholds(10, 7);
  const wordings = [true, false].map((sinceRun) => reminderTexts(new Due(10, 7, sinceRun), learning)[0]);
  const longest = wordings.reduce((a, b) => (Buffer.byteLength(b) > Buffer.byteLength(a) ? b : a));
  assert.equal(reminderCeiling(thresholds, learning), longest);
});

test("the routing ceiling is deterministic and at least as long as every setup instruction", () => {
  const registry = loadRegistry(data.agents, akmonRuntimeRoot("/nonexistent"));
  const text = sessionStartCeiling(data.agents, registry, "akmon tool model_routing/init");
  assert.equal(text, sessionStartCeiling(data.agents, registry, "akmon tool model_routing/init"));
  assert.ok(text.includes("model routing:"));
  const init = initInstruction(
    data.agents,
    staleness(data.agents, {}, registry, null) ?? "",
    "akmon tool model_routing/init",
  );
  assert.ok(Buffer.byteLength(text) >= Buffer.byteLength(init.join("\n")));
});

test("routing data the ceiling cannot read costs the routing member, not the count", () => {
  const broken = /** @type {any} */ ({ ...data, agents: { ...data.agents, opinion_status: undefined } });
  withProject((root) => {
    assert.deepEqual(
      sessionStartMembers(broken, root).map((member) => member.name),
      ["hook: session-start-agent", "hook: learning-reminder"],
    );
  });
});

test("the tool command ceiling is the longest launcher spelling", () => {
  assert.equal(
    toolCommandCeiling(data.agents, "_aitna/akmon", "model_routing/init"),
    "python3 _aitna/akmon/tools/model_routing/init.py",
  );
  assert.equal(toolCommandCeiling(data.agents, "a", "t"), "python3 a/tools/t.py");
});
