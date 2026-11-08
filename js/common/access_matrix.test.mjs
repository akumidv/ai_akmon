/**
 * node:test for `js/common/access_matrix.mjs` — the twin of `meta/tests/test_access_matrix.py`
 * (ADR 0031/D07): the data file's shape, the actor carrier and the outcome reader. The decisions
 * the matrix gives the commit guard are the shared table `meta/conformance/units/commit_guard_cases.json`,
 * run by `js/hooks/hook_core.test.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import {
  ACTORS,
  AI_TRAILER_CLASS,
  OUTCOMES,
  PROTECTED_BRANCHES_KEY,
  RUN_BRANCH_PATTERNS_KEY,
  actorFromEnvironment,
  checkData,
  checkProtectedBranches,
  checkRunBranchPatterns,
  checkTrailerFloor,
  isOwnBranch,
  isProtectedBranch,
  outcome,
  protectedBranches,
  runBranchFromEnvironment,
} from "./access_matrix.mjs";
import { DataFileError } from "./jsondata.mjs";
import { TREE_ROOT } from "../hooks/hook_data.mjs";

/** @type {Record<string, any>} */
const DATA = JSON.parse(fs.readFileSync(posix.join(TREE_ROOT, "common", "access_matrix.json"), "utf8"));
/** @type {Record<string, any>} */
const TEXTS = JSON.parse(fs.readFileSync(posix.join(TREE_ROOT, "hooks", "hook_core.json"), "utf8"));
const ROWS = Object.fromEntries(
  Object.entries(DATA).filter(([name]) => name !== PROTECTED_BRANCHES_KEY && name !== RUN_BRANCH_PATTERNS_KEY),
);
const HISTORY = Object.keys(DATA.developer).filter((name) => name.startsWith("history_"));

test("the matrix has one row per actor and every row the same classes", () => {
  assert.deepEqual(
    Object.keys(DATA).sort(),
    [...Object.values(ACTORS), PROTECTED_BRANCHES_KEY, RUN_BRANCH_PATTERNS_KEY].sort(),
  );
  assert.deepEqual(Object.keys(ROWS).sort(), Object.values(ACTORS).sort());
  const classes = Object.keys(DATA.developer).sort();
  for (const [actor, row] of Object.entries(ROWS)) {
    assert.deepEqual(Object.keys(row).sort(), classes, actor);
    for (const value of Object.values(row)) {
      assert.ok(OUTCOMES.includes(value), `${actor}: ${value}`);
    }
  }
});

test("every class has a reason text and every history class a where text, for each actor", () => {
  for (const [actor, row] of Object.entries(ROWS)) {
    assert.deepEqual(Object.keys(TEXTS.access_reasons[actor]).sort(), Object.keys(row).sort(), actor);
    assert.deepEqual(Object.keys(TEXTS.access_where[actor]).sort(), [...HISTORY].sort(), actor);
    for (const key of [...Object.values(TEXTS.access_reasons[actor]), ...Object.values(TEXTS.access_where[actor])]) {
      assert.equal(typeof TEXTS[/** @type {string} */ (key)], "string", String(key));
    }
  }
});

test("the developer row is the guard before the matrix; the autonomous row is the run-branch column", () => {
  const developer = DATA.developer;
  assert.deepEqual(
    HISTORY.filter((name) => developer[name] === "allow"),
    ["history_worktree_branch"],
  );
  for (const name of ["push_own_branch", "push_own_branch_forced", "push_default_branch", "push_other_branch", "tag"]) {
    assert.equal(developer[name], "ask", name);
  }
  assert.equal(developer.ref_write, "ask");
  assert.deepEqual([developer.pr_create, developer.pr_create_other_base], ["ask", "ask"]);
  // git config and `gh api` passed before the matrix, and still do for the developer
  assert.deepEqual([developer.config_push_write, developer.forge_write_other], ["allow", "allow"]);
  assert.equal(developer.ai_trailer, "deny");
  const autonomous = DATA.autonomous;
  assert.deepEqual(
    HISTORY.filter((name) => autonomous[name] === "allow"),
    ["history_checkout_branch", "history_worktree_branch"],
  );
  assert.equal(autonomous.push_own_branch, "allow");
  assert.equal(autonomous.push_own_branch_forced, "ask");
  assert.equal(autonomous.push_default_branch, "deny");
  assert.equal(autonomous.push_other_branch, "deny");
  assert.deepEqual([autonomous.tag, autonomous.ref_write], ["ask", "ask"]);
  assert.deepEqual([autonomous.pr_create, autonomous.pr_merge, autonomous.release_create], ["allow", "ask", "ask"]);
  assert.equal(autonomous.pr_create_other_base, "deny");
  assert.deepEqual([autonomous.config_push_write, autonomous.forge_write_other], ["deny", "ask"]);
  assert.equal(autonomous.ai_trailer, "deny");
});

test("develop and the release branches are protected for the autonomous actor only", () => {
  assert.deepEqual(DATA[PROTECTED_BRANCHES_KEY], { developer: [], autonomous: ["develop", "release/*"] });
  assert.deepEqual(protectedBranches(DATA, "autonomous"), ["develop", "release/*"]);
  assert.deepEqual(protectedBranches(DATA, "developer"), []);
  assert.throws(() => protectedBranches({}, "developer"), DataFileError);
});

test("the actor is autonomous only for that exact value", () => {
  assert.equal(actorFromEnvironment({}), "developer");
  assert.equal(actorFromEnvironment({ AKMON_ACTOR: "developer" }), "developer");
  assert.equal(actorFromEnvironment({ AKMON_ACTOR: "autonomous" }), "autonomous");
  for (const value of ["", "guided", "Autonomous", " autonomous", undefined]) {
    assert.equal(actorFromEnvironment({ AKMON_ACTOR: value }), "developer", String(value));
  }
  assert.equal(actorFromEnvironment({ OTHER: "autonomous" }), "developer");
});

test("outcome reads the row and the class; a hole in the matrix raises instead of reading as permission", () => {
  assert.equal(outcome(DATA, "autonomous", "pr_create"), "allow");
  assert.equal(outcome(DATA, "developer", "pr_create"), "ask");
  assert.throws(() => outcome(DATA, "autonomous", "nope"), DataFileError);
  assert.throws(() => outcome({}, "developer", "tag"), DataFileError);
  assert.throws(() => outcome({ developer: { tag: "maybe" } }, "developer", "tag"), /is 'maybe'/);
});

test("the shipped matrix passes the trailer floor, and a matrix that softens it for any actor is refused", () => {
  assert.equal(checkTrailerFloor(DATA), DATA);
  for (const actor of ["developer", "autonomous"]) {
    for (const cell of ["allow", "ask", undefined]) {
      const softened = structuredClone(DATA);
      if (cell === undefined) {
        delete softened[actor][AI_TRAILER_CLASS];
      } else {
        softened[actor][AI_TRAILER_CLASS] = cell;
      }
      assert.throws(() => checkTrailerFloor(softened), DataFileError, `${actor} ${cell}`);
    }
  }
});

test("a protected_branches of the wrong shape is refused", () => {
  assert.equal(checkProtectedBranches(DATA), DATA);
  assert.equal(checkData(DATA), DATA);
  /** @type {unknown[]} */
  const broken = [
    undefined,
    [],
    { developer: [] },
    { developer: [], autonomous: "develop" },
    { developer: [], autonomous: [1] },
    { developer: [], autonomous: [""] },
    { developer: null, autonomous: ["develop"] },
  ];
  for (const value of broken) {
    const mangled = structuredClone(DATA);
    if (value === undefined) {
      delete mangled[PROTECTED_BRANCHES_KEY];
    } else {
      mangled[PROTECTED_BRANCHES_KEY] = value;
    }
    assert.throws(() => checkProtectedBranches(mangled), DataFileError, JSON.stringify(value));
    assert.throws(() => checkData(mangled), /protected_branches/, JSON.stringify(value));
  }
});

// --- D-C203-RUN-BRANCH: the autonomous actor's own branch ---------------------------------------------------------

test("the autonomous row has a class for a history write off the run branch; a developer never reaches it", () => {
  assert.equal(DATA.autonomous.history_not_run_branch, "deny");
  assert.equal(DATA.developer.history_not_run_branch, DATA.developer.history_checkout_branch);
  assert.equal(DATA.developer.history_not_run_branch, "ask");
});

test("the run branch patterns are per-actor regexes and the developer has none", () => {
  assert.deepEqual(DATA[RUN_BRANCH_PATTERNS_KEY].developer, []);
  assert.equal(DATA[RUN_BRANCH_PATTERNS_KEY].autonomous.length, 1);
});

test("a branch under agent/ starting with a task id is the autonomous run branch", () => {
  /** @type {Array<[string, boolean]>} */
  const cells = [
    ["agent/C203-run", true],
    ["agent/C203", true],
    ["agent/C203/sub", true],
    ["agent/C203.1", true],
    ["agent/C203_x", true],
    ["agent/A76-x", true],
    ["agent/B15-y", true],
    ["agent/_T3-local", true],
    ["agent/_T3", true],
    ["agent/C1-x", true],
    ["agent/c203-x", false],
    ["agent/C203x", false],
    ["agent/CC203-x", false],
    ["agent/_T-x", false],
    ["agent/T3-x", true], // `T3` is a task id (a letter and digits), like `C203`
    ["agent/fix-thing", false],
    ["agent/", false],
    ["agent", false],
    ["feat", false],
    ["x/agent/C203-run", false],
    ["agent/C203-run\nx", true], // only the start of the name is read
    ["main", false],
    ["", false],
  ];
  for (const [branch, own] of cells) {
    assert.equal(isOwnBranch(DATA, "autonomous", branch, null), own, JSON.stringify(branch));
  }
});

test("a named run branch is the only own branch for an autonomous run, and every branch is a developer's", () => {
  for (const branch of ["agent/C203-run", "feat", "anything", "agent/fix"]) {
    assert.equal(isOwnBranch(DATA, "autonomous", branch, branch), true, branch);
  }
  assert.equal(isOwnBranch(DATA, "autonomous", "agent/C203-run", "feat"), false); // exact, not a pattern
  assert.equal(isOwnBranch(DATA, "autonomous", "feat/sub", "feat"), false);
  for (const runBranch of [null, "feat", "agent/C203-run"]) {
    assert.equal(isOwnBranch(DATA, "developer", "whatever", runBranch), true, String(runBranch));
  }
});

test("the run branch is the environment value when set", () => {
  assert.equal(runBranchFromEnvironment({}), null);
  assert.equal(runBranchFromEnvironment({ AKMON_RUN_BRANCH: "" }), null);
  assert.equal(runBranchFromEnvironment({ AKMON_RUN_BRANCH: "agent/C203-run" }), "agent/C203-run");
  assert.equal(runBranchFromEnvironment({ AKMON_RUN_BRANCH: " agent/x" }), " agent/x"); // nothing is trimmed
  assert.equal(runBranchFromEnvironment({ OTHER: "agent/C203-run" }), null);
});

test("a protected name is exact, or a prefix when it ends in a star", () => {
  /** @type {Array<[string[], string, boolean]>} */
  const cells = [
    [["develop"], "develop", true],
    [["develop"], "develop2", false],
    [["develop"], "develop/x", false],
    [["release/*"], "release/1.0", true],
    [["release/*"], "release/", true],
    [["release/*"], "release", false],
    [["release/*"], "releases/1", false],
    [["release/*"], "x/release/1", false],
    [["*"], "anything", true],
    [["a*b"], "axb", false], // a glob is a trailing `*` only
    [[], "develop", false],
  ];
  for (const [names, branch, expected] of cells) {
    assert.equal(isProtectedBranch(names, branch), expected, `${names} ${branch}`);
  }
});

test("run_branch_patterns of the wrong shape, or that is no regex, is refused", () => {
  assert.equal(checkRunBranchPatterns(DATA), DATA);
  /** @type {unknown[]} */
  const broken = [
    undefined,
    [],
    { developer: [] },
    { developer: [], autonomous: "^agent/" },
    { developer: [], autonomous: [1] },
    { developer: [], autonomous: [""] },
    { developer: null, autonomous: ["^agent/"] },
    { developer: [], autonomous: ["(unclosed"] },
  ];
  for (const value of broken) {
    const mangled = structuredClone(DATA);
    if (value === undefined) {
      delete mangled[RUN_BRANCH_PATTERNS_KEY];
    } else {
      mangled[RUN_BRANCH_PATTERNS_KEY] = value;
    }
    assert.throws(() => checkRunBranchPatterns(mangled), DataFileError, JSON.stringify(value));
    assert.throws(() => checkData(mangled), /run_branch_patterns/, JSON.stringify(value));
  }
});
