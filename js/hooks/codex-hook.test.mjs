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
import { TREE_ROOT } from "./hook_data.mjs";

const DATA = readData();
const _HOOK = fileURLToPath(new URL("./codex-hook.mjs", import.meta.url));

/** A scratch project whose record asks for a reminder at two sessions. */
function project() {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-codex-learning-")));
  fs.mkdirSync(path.join(root, "_aitna"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# a\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), '[learning]\nreminder_sessions = "2"\n');
  return { root, state: path.join(root, "_aitna", ".local", "learning.json") };
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

test("the git-commit-guard route reads the actor from the environment (ADR-0031/D07)", () => {
  const scratch = project();
  // `gh pr create` needs no repository, so the actor alone decides it. The route states no attendance and
  // no permission mode, so a developer's ask reaches it as a deny.
  /** @type {Array<[string | undefined, string | null]>} */
  const cells = [
    [undefined, "deny"],
    ["developer", "deny"],
    ["autonomous", null],
    ["bogus", "deny"],
    ["Autonomous", "deny"],
    ["", "deny"],
  ];
  for (const [value, decision] of cells) {
    const run = spawnSync(process.execPath, [_HOOK, "git-commit-guard"], {
      input: JSON.stringify({ tool_name: "shell", tool_input: { command: "gh pr create --fill" }, cwd: scratch.root }),
      encoding: "utf8",
      cwd: scratch.root,
      env: { ...process.env, AKMON_ACTOR: value ?? "" },
    });
    assert.equal(run.status, 0, run.stderr);
    if (decision === null) {
      assert.equal(run.stdout, "", String(value));
    } else {
      assert.equal(JSON.parse(run.stdout).hookSpecificOutput.permissionDecision, decision, String(value));
    }
  }
});

/**
 * A copy of the tree's hook code and data under a temporary directory, with an access matrix that cannot be
 * read — the guard's own data failing, end to end (D-C203-GUARD-CRASH). `body` gets the copy's root.
 * @param {(root: string) => void} body
 */
function withBrokenMatrixTree(body) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-broken-matrix-"));
  try {
    for (const directory of ["js", "hooks", "common", "tools/model_routing", "agents"]) {
      fs.cpSync(path.join(TREE_ROOT, directory), path.join(root, directory), {
        recursive: true,
        filter: (source) => !source.includes("__pycache__") && !source.endsWith(".test.mjs"),
      });
    }
    fs.writeFileSync(path.join(root, "common", "access_matrix.json"), "{ not json");
    body(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test("the git-commit-guard route denies an autonomous run when the access matrix cannot be read, not a developer's", () => {
  const scratch = project();
  withBrokenMatrixTree((tree) => {
    const call = (/** @type {Record<string, string>} */ env) =>
      spawnSync(process.execPath, [path.join(tree, "js", "hooks", "codex-hook.mjs"), "git-commit-guard"], {
        input: JSON.stringify({
          tool_name: "shell",
          tool_input: { command: "gh pr create --fill" },
          cwd: scratch.root,
        }),
        encoding: "utf8",
        cwd: scratch.root,
        env: { ...process.env, AKMON_ACTOR: "", ...env },
      });
    const closed = call({ AKMON_ACTOR: "autonomous" });
    assert.equal(closed.status, 0, closed.stderr);
    assert.equal(closed.stderr, "akmon codex-hook git-commit-guard hook: DataFileError\n");
    const output = JSON.parse(closed.stdout).hookSpecificOutput;
    assert.equal(output.permissionDecision, "deny");
    assert.match(output.permissionDecisionReason, /access matrix could not be read/);
    for (const actor of [undefined, "developer", "bogus"]) {
      const open = call(actor === undefined ? {} : { AKMON_ACTOR: actor });
      assert.equal(open.status, 1, String(actor)); // ADR 0013: Codex shows the hook Failed, the action goes ahead
      assert.equal(open.stdout, "");
    }
  });
});

test("the git-commit-guard route reads the run branch from the environment (ADR-0031/D07)", () => {
  const scratch = project();
  const repository = path.join(scratch.root, "clone");
  fs.mkdirSync(repository);
  spawnSync("git", ["-C", repository, "init", "-q", "-b", "feat"], { encoding: "utf8" });
  /** @type {Array<[string | undefined, string | null]>} */
  const cells = [
    [undefined, "deny"], // `feat` is no task-id branch under agent/
    ["feat", null],
    ["agent/C203-x", "deny"], // the exact name wins over the pattern
    ["", "deny"], // an empty value names nothing
  ];
  for (const [value, decision] of cells) {
    const run = spawnSync(process.execPath, [_HOOK, "git-commit-guard"], {
      input: JSON.stringify({ tool_name: "shell", tool_input: { command: "git commit -m x" }, cwd: repository }),
      encoding: "utf8",
      cwd: repository,
      env: { ...process.env, AKMON_ACTOR: "autonomous", AKMON_RUN_BRANCH: value ?? "" },
    });
    assert.equal(run.status, 0, run.stderr);
    if (decision === null) {
      assert.equal(run.stdout, "", String(value));
    } else {
      assert.equal(JSON.parse(run.stdout).hookSpecificOutput.permissionDecision, decision, String(value));
    }
  }
  // a developer run ignores the variable: its commit in a checkout asks, which this route (no attendance) denies
  const developer = spawnSync(process.execPath, [_HOOK, "git-commit-guard"], {
    input: JSON.stringify({ tool_name: "shell", tool_input: { command: "git commit -m x" }, cwd: repository }),
    encoding: "utf8",
    cwd: repository,
    env: { ...process.env, AKMON_ACTOR: "", AKMON_RUN_BRANCH: "feat" },
  });
  assert.equal(JSON.parse(developer.stdout).hookSpecificOutput.permissionDecision, "deny");
});
