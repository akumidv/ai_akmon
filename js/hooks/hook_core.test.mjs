/**
 * node:test for `js/hooks/hook_core.mjs` — the named pins of the twin. Every expected value was
 * produced by running the Python module (`hooks/hook_core.py`) on the same input: the path
 * classification edge cases, the command guards' ASCII boundaries, the permission-mode `repr`,
 * the `:g` spelling of a score, and the drift counter file. The five Claude entry points are
 * compared with the Python hooks end to end by the hook corpus (`runner.py --impl node`).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { spawnSync } from "node:child_process";

import { pyError } from "../common/pyvalue.mjs";
import {
  HookResult,
  agentNames,
  analysisBeforeMutationMessage,
  analysisWriteResult,
  classifyTarget,
  currentGitBranch,
  delegationAskThreshold,
  delegationGrace,
  delegationNudgeMessage,
  delegationNudgeResult,
  delegationNudgeThreshold,
  editTool,
  formatG,
  gitCommitGuardResult,
  hookFailureDiagnostic,
  hookFailureNotice,
  isCodePath,
  isPlanningDoc,
  neutralKind,
  normpath,
  privilegeEscalationGuardResult,
  readTool,
  reportUnclassifiedShellRoute,
  roleOnCodeResult,
  runtimeRootDisplay,
  sessionStartResult,
  shellTool,
  staleGuardrailNotice,
  subagentTool,
} from "./hook_core.mjs";
import { TREE_ROOT, lazyHookData } from "./hook_data.mjs";

const data = lazyHookData();

/** Run `body` with a fresh directory, removed after. */
function withDir(/** @type {(dir: string) => void} */ body) {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-hook-core-test-"));
  try {
    body(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** Run `body` with `TMPDIR` a fresh directory (the markers and counters land there) and `env` set. */
function withState(/** @type {Record<string, string | null>} */ env, /** @type {(tmp: string) => void} */ body) {
  withDir((tmp) => {
    const names = ["TMPDIR", "TEMP", "TMP", "AITNA_ROOT", ...Object.keys(env)];
    const saved = names.map((name) => process.env[name]);
    try {
      for (const name of ["TEMP", "TMP", "AITNA_ROOT"]) {
        delete process.env[name];
      }
      process.env.TMPDIR = tmp;
      for (const [name, value] of Object.entries(env)) {
        if (value === null) {
          delete process.env[name];
        } else {
          process.env[name] = value;
        }
      }
      body(tmp);
    } finally {
      names.forEach((name, i) => {
        if (saved[i] === undefined) {
          delete process.env[name];
        } else {
          process.env[name] = saved[i];
        }
      });
    }
  });
}

/** `body`'s thrown error, for a test that pins its class. */
function thrown(/** @type {() => unknown} */ body) {
  try {
    body();
  } catch (error) {
    return /** @type {Error} */ (error);
  }
  throw new Error("expected a throw");
}

test("HookResult: one options object, null defaults, frozen", () => {
  const result = new HookResult({ eventName: "PreToolUse", permissionDecision: "deny" });
  assert.deepEqual(
    { ...result },
    {
      eventName: "PreToolUse",
      additionalContext: null,
      permissionDecision: "deny",
      permissionReason: null,
      systemMessage: null,
      decision: null,
      reason: null,
    },
  );
  assert.ok(Object.isFrozen(result));
});

test("the crash report is the class name, never the message", () => {
  assert.equal(
    hookFailureDiagnostic("role-on-code", pyError("KeyError", "secret/path")),
    "akmon role-on-code hook: KeyError",
  );
  const missing = thrown(() => fs.readFileSync("/nonexistent/x"));
  assert.equal(hookFailureDiagnostic("h", missing), "akmon h hook: FileNotFoundError");
  assert.equal(hookFailureDiagnostic("h", "not an error"), "akmon h hook: Exception");
  assert.equal(
    hookFailureNotice("gate-audit", pyError("ValueError", "x")),
    "⚠ akmon: the gate-audit hook failed (ValueError) and was skipped — this action went ahead without it. " +
      "Check the setup: `akmon verify` (a mounted tree: `python3 _aitna/akmon/bin/verify.py`).",
  );
});

test("the neutral kinds come from vocabulary.json; an unknown stem is a KeyError", () => {
  assert.deepEqual(
    [editTool(data), shellTool(data), readTool(data), subagentTool(data)],
    ["edit", "shell", "read", "subagent"],
  );
  assert.equal(thrown(() => neutralKind(data, "nope-not-a-stem")).name, "KeyError");
});

test("normpath: os.path.normpath on every shape of separator and dot", () => {
  for (const [given, expected] of [
    ["", "."],
    [".", "."],
    ["..", ".."],
    ["//x", "//x"],
    ["///x", "/x"],
    ["////x", "/x"],
    ["a/", "a"],
    ["a//b", "a/b"],
    ["a/./b", "a/b"],
    ["/..", "/"],
    ["/../a", "/a"],
    ["//..", "//"],
    ["//a/../..", "//"],
    ["a/..", "."],
    ["../a", "../a"],
    ["a/../..", ".."],
    ["./", "."],
    ["/./a", "/a"],
    ["//./a", "//a"],
    ["a/b/../../..", ".."],
    ["/a/b/../../..", "/"],
  ]) {
    assert.equal(normpath(given), expected, JSON.stringify(given));
  }
});

test("classifyTarget with a root: project-relative, lowercased, leading slash, outside is a marker", () => {
  for (const [given, expected] of [
    ["src/a.py", "/src/a.py"],
    ["SRC/A.PY", "/src/a.py"],
    ["./a.py", "/a.py"],
    ["a/../b.py", "/b.py"],
    ["../a.py", "/__outside_project__"],
    ["a//b.py", "/a/b.py"],
    ["a/./b.py", "/a/b.py"],
    ["/proj/a.py", "/a.py"],
    ["/proj//a.py", "/a.py"],
    ["//proj/a.py", "/a.py"],
    ["///proj/a.py", "/a.py"],
    ["/proj", "/."],
    ["/proj/", "/."],
    ["/proj/..", "/__outside_project__"],
    ["/other/a.py", "/__outside_project__"],
    ["a\\b.py", "/a/b.py"],
    ["C:\\x\\a.py", "/c:/x/a.py"],
    ["", "/."],
    [".", "/."],
    [" ", "/ "],
    ["..", "/__outside_project__"],
    ["src/", "/src"],
    ["/", "/__outside_project__"],
    ["//", "/__outside_project__"],
    ["///", "/__outside_project__"],
    ["a.PY", "/a.py"],
    ["/proj/docs/a.py", "/docs/a.py"],
    ["_AITNA/TASKS.md", "/_aitna/tasks.md"],
    ["/proj/./x/../y.py", "/y.py"],
    ["/proj/x/../../y.py", "/__outside_project__"],
    ["é/İ.PY", "/é/i̇.py"],
    ["a\nb.py", "/a\nb.py"],
  ]) {
    assert.equal(classifyTarget(given, "/proj"), expected, JSON.stringify(given));
  }
});

test("classifyTarget without a root: an absolute path keeps its own spelling (a leading // too)", () => {
  for (const [given, expected] of [
    ["/a/b.py", "/a/b.py"],
    ["//a/b.py", "//a/b.py"],
    ["///a/b.py", "/a/b.py"],
    ["/a//b/./c.py", "/a/b/c.py"],
    ["/a/../b.py", "/a/../b.py"],
    ["/", "/"],
    ["//", "//"],
    ["/a/", "/a"],
    ["\\\\x\\y.py", "//x/y.py"],
    ["C:/x/A.PY", "/c:/x/a.py"],
  ]) {
    assert.equal(classifyTarget(given), expected, JSON.stringify(given));
  }
});

test("classifyTarget: a root reached through a symlink alias takes the resolved fallback; a link out stays inside", () => {
  withDir((dir) => {
    const real = posix.join(fs.realpathSync(dir), "real");
    fs.mkdirSync(posix.join(real, "src"), { recursive: true });
    fs.symlinkSync(real, posix.join(dir, "alias"));
    fs.mkdirSync(posix.join(dir, "outside"));
    fs.symlinkSync(posix.join(dir, "outside"), posix.join(real, "linkout"));
    assert.equal(classifyTarget(`${dir}/alias/src/a.py`, real), "/src/a.py");
    assert.equal(classifyTarget(`${real}/src/a.py`, `${dir}/alias`), "/src/a.py");
    assert.equal(classifyTarget(`${real}/linkout/x.py`, real), "/linkout/x.py");
    assert.equal(classifyTarget(`${dir}/outside/x.py`, real), "/__outside_project__");
  });
});

test("classifyTarget: a path no filesystem call can take raises as Python does", () => {
  assert.equal(thrown(() => classifyTarget("/elsewhere/a\0b.py", "/proj")).name, "ValueError");
  assert.equal(thrown(() => classifyTarget("/elsewhere/\ud800.py", "/proj")).name, "UnicodeEncodeError");
  assert.equal(thrown(() => classifyTarget(/** @type {any} */ (5), "/proj")).name, "AttributeError");
  assert.equal(classifyTarget("a\0b.py", "/proj"), "/a\0b.py"); // lexically inside: no filesystem call
});

test("isCodePath: the suffix rule and the non-code segments", () => {
  withState({}, () => {
    for (const [given, expected] of /** @type {[string, boolean][]} */ ([
      ["src/a.py", true],
      ["a.PY", true],
      [".py", false],
      ["a.", false],
      ["x.tar.gz", false],
      ["x.mjs", true],
      ["Makefile", false],
      ["x.R", true],
      ["x.mm", true],
      ["docs/a.py", false],
      ["src/docs/a.py", false],
      ["_aitna/design/a.py", false],
      ["_aitna/akmon/js/x.mjs", false],
      [".claude/x.py", false],
      ["../a.py", false],
      ["a/b.py/", true],
      ["a.py//", true],
      ["/proj/src/a.py", true],
    ])) {
      assert.equal(isCodePath(data, given, "/proj"), expected, JSON.stringify(given));
    }
  });
});

test("isPlanningDoc: the backlog files, and a .md under a planning segment", () => {
  withState({}, () => {
    for (const [given, expected] of /** @type {[string, boolean][]} */ ([
      ["_aitna/TASKS.md", true],
      ["_aitna/tasks_archive.md", true],
      ["_AITNA/Design/a.md", true],
      ["_aitna/design/a.py", false],
      ["docs/dev/a.md", true],
      ["docs/b.md", false],
      ["_aitna/akmon/a.md", true],
      ["_aitna/.akmon/a.md", true],
      ["src/_aitna/design/a.md", true],
      ["_aitna/design", false],
    ])) {
      assert.equal(isPlanningDoc(data, given, "/proj"), expected, JSON.stringify(given));
    }
  });
  // a substring, not a prefix: the segment matches anywhere in the project-relative path
  withState({ AITNA_ROOT: "Dev/" }, () => {
    assert.equal(isPlanningDoc(data, "dev/design/a.md", "/proj"), true);
    assert.equal(isPlanningDoc(data, "_aitna/design/a.md", "/proj"), false);
    assert.equal(isCodePath(data, "dev/memory/a.py", "/proj"), false);
  });
});

test("the privilege guard is ASCII-word-bounded: another script's letter is a boundary", () => {
  for (const [command, denied] of /** @type {[string, boolean][]} */ ([
    ["sudo ls", true],
    ["echo sudo", true],
    ["SUDO ls", false],
    ["pseudo ls", false],
    ["sudoku", false],
    ["sudo-x", true],
    ["a;sudo b", true],
    ["ésudo ls", true],
    ["sudoé ls", true],
    ["sudo_x", false],
  ])) {
    assert.equal(privilegeEscalationGuardResult(data, command) !== null, denied, command);
  }
  assert.equal(thrown(() => privilegeEscalationGuardResult(data, 5)).name, "TypeError");
});

test("the commit guard: trailer deny, push/tag/merge ask, a commit on main/master/detached asks", () => {
  /** @param {string} command @param {string | null} branch @param {string | null} [permissionMode] */
  const decide = (command, branch, permissionMode = "default") => {
    const result = gitCommitGuardResult(data, command, branch, { permissionMode });
    return result === null ? null : result.permissionDecision;
  };
  assert.equal(decide("git push", "feat"), "ask");
  assert.equal(decide("git tag v1", "feat"), "ask");
  assert.equal(decide("git merge x", "feat"), "ask");
  assert.equal(decide("git commit -m x", "main"), "ask");
  assert.equal(decide("git commit -m x", "master"), "ask");
  assert.equal(decide("git commit -m x", ""), "ask");
  assert.equal(decide("git commit -m x", "feat"), null);
  assert.equal(decide("git commit -m x", "Main"), null);
  assert.equal(decide("git status", "main"), null);
  assert.equal(decide("ls", "main"), null);
  assert.equal(decide("git commit -m 'Co-Authored-By: x'", "feat"), "deny");
  assert.equal(decide("git CO-AUTHORED-BY", "feat"), "deny");
  assert.equal(decide("git co\u2011authored-by", "feat"), null); // a non-breaking hyphen is not a hyphen
  // `\b` is ASCII: another script's letter next to git/push is a boundary, as `git; push` is not one
  assert.equal(decide("βgit push", "feat"), "ask");
  assert.equal(decide("git pushé", "feat"), "ask");
  assert.equal(decide("git\u00a0push", "feat"), "ask");
  assert.equal(decide("git; push", "feat"), null);
  assert.equal(decide("git a | push", "feat"), null);
  assert.equal(decide("echo git\npush", "feat"), "ask"); // [^|&;] crosses a newline
  assert.equal(decide("git x &&\npush", "feat"), null);
  assert.equal(decide("git\u2028push", "feat"), "ask"); // and U+2028
  assert.equal(decide("gitpush", "feat"), null);
  const landing = gitCommitGuardResult(data, "git commit -m x", "", { permissionMode: "default" });
  assert.match(String(landing?.permissionReason), /A commit on 'detached HEAD' is a landing commit/);
});

test("a non-string command is the TypeError re.search raises", () => {
  assert.equal(thrown(() => gitCommitGuardResult(data, ["git"], "main")).name, "TypeError");
  assert.equal(gitCommitGuardResult(data, ["x"], "main"), null); // `"git" in ["x"]` is False
  assert.equal(thrown(() => gitCommitGuardResult(data, 5, "main")).name, "TypeError");
});

test("an unattended ask is a deny that spells the permission mode with repr()", () => {
  const reasonTail = (/** @type {string | null} */ mode) => {
    const result = gitCommitGuardResult(data, "git push", "feat", { permissionMode: mode });
    return [result?.permissionDecision, String(result?.permissionReason).match(/permission_mode=(.*?) is not/)?.[1]];
  };
  assert.deepEqual(reasonTail("default"), ["ask", undefined]);
  assert.deepEqual(reasonTail(null), ["deny", "None"]);
  assert.deepEqual(reasonTail("auto"), ["deny", "'auto'"]);
  assert.deepEqual(reasonTail("it's"), ["deny", '"it\'s"']);
  assert.deepEqual(reasonTail('a"b'), ["deny", "'a\"b'"]);
  assert.deepEqual(reasonTail("é"), ["deny", "'é'"]);
  assert.deepEqual(reasonTail("a\nb"), ["deny", "'a\\nb'"]);
  assert.deepEqual(reasonTail(""), ["deny", "''"]);
  assert.deepEqual(reasonTail("Default"), ["deny", "'Default'"]);
});

test("role-on-code and analysis-guard fire once per session on a matching edit", () => {
  withState({}, () => {
    assert.equal(roleOnCodeResult(data, "edit", "/proj/src/a.py", "s-a", "/proj")?.eventName, "PreToolUse");
    assert.equal(roleOnCodeResult(data, "edit", "/proj/src/a.py", "s-a", "/proj"), null);
    assert.equal(
      roleOnCodeResult(data, "edit", "/proj/src/b.py", "s-b", "/proj")?.additionalContext?.startsWith(
        "[akmon] Role check",
      ),
      true,
    );
    assert.equal(roleOnCodeResult(data, "read", "/proj/src/c.py", "s-c", "/proj"), null);
    assert.equal(roleOnCodeResult(data, "edit", 5, "s-c", "/proj"), null);
    assert.equal(roleOnCodeResult(data, "edit", "/proj/docs/c.py", "s-c", "/proj"), null);
    assert.equal(
      analysisWriteResult(data, "edit", "/proj/_aitna/TASKS.md", "s-a", "/proj")?.additionalContext,
      analysisBeforeMutationMessage(data),
    );
    assert.equal(analysisWriteResult(data, "edit", "/proj/_aitna/TASKS.md", "s-a", "/proj"), null);
    assert.equal(analysisWriteResult(data, "edit", "/proj/src/a.py", "s-d", "/proj"), null);
  });
});

test("the shell-route notice is claimed once per session, on stderr", () => {
  withState({}, () => {
    /** @type {string[]} */
    const written = [];
    const original = process.stderr.write;
    process.stderr.write = /** @type {any} */ (
      (/** @type {string} */ text) =>
        (written.push(text), true)
    );
    try {
      reportUnclassifiedShellRoute(data, "s-shell");
      reportUnclassifiedShellRoute(data, "s-shell");
      reportUnclassifiedShellRoute(data, null);
    } finally {
      process.stderr.write = original;
    }
    assert.equal(written.length, 2);
    assert.match(written[0], /^akmon hook: a shell call may mutate the filesystem.*\n$/);
  });
});

test("formatG: six significant digits, half to even on the exact value, Python's exponent spelling", () => {
  for (const [value, expected] of /** @type {[number, string][]} */ ([
    [1, "1"],
    [0.5, "0.5"],
    [2.5, "2.5"],
    [31, "31"],
    [29.5, "29.5"],
    [100, "100"],
    [1234565, "1.23456e+06"],
    [1234575, "1.23458e+06"],
    [999999.5, "1e+06"],
    [1e16, "1e+16"],
    [0.0001234565, "0.000123457"],
    [0.00001234565, "1.23456e-05"],
    [123456, "123456"],
    [1234567, "1.23457e+06"],
    [1e-5, "1e-05"],
    [0, "0"],
    [-0, "-0"],
    [1e300, "1e+300"],
    [Infinity, "inf"],
    [NaN, "nan"],
    [33.5, "33.5"],
    [0.1, "0.1"],
    [100000, "100000"],
    [99999.95, "99999.9"],
    [5e-324, "4.94066e-324"],
    [1500000, "1.5e+06"],
  ])) {
    assert.equal(formatG(value), expected, String(value));
  }
});

/**
 * Call the nudge for `kind` with the counter seeded to `seed` (`null`: as it is).
 * @returns {[string | null, HookResult | null]} the counter text after the call, and the result
 */
function nudge(
  /** @type {string} */ tmp,
  /** @type {string} */ sid,
  /** @type {string} */ kind,
  /** @type {string | null} */ seed,
  /** @type {{permissionMode?: string | null, isSubagent?: boolean}} */ options = { permissionMode: "default" },
) {
  const counter = posix.join(tmp, `akmon-delegation-nudge-${sid}.count`);
  if (seed !== null) {
    fs.writeFileSync(counter, seed);
  }
  const result = delegationNudgeResult(data, kind, sid, options);
  return [fs.existsSync(counter) ? fs.readFileSync(counter, "utf8") : null, result];
}

test("the drift counter: the grace is calls, a read is half, the file spells the score as a Python float", () => {
  withState({}, (tmp) => {
    assert.deepEqual(nudge(tmp, "c1", "edit", null)[0], "1 0.0");
    assert.deepEqual(nudge(tmp, "c1", "edit", null)[0], "2 0.0");
    assert.equal(nudge(tmp, "c2", "read", "8 0.0")[0], "9 0.5");
    assert.equal(nudge(tmp, "c2", "read", null)[0], "10 1.0");
    assert.equal(nudge(tmp, "c9", "edit", "1_0 1.5")[0], "11 2.5");
    assert.equal(nudge(tmp, "c11", "edit", "8 -0.0")[0], "9 1.0");
    assert.equal(nudge(tmp, "c10", "edit", "8 nan")[0], "9 nan");
    assert.equal(nudge(tmp, "c12", "edit", "5")[0], "6 0.0"); // the old one-number counter: calls, no score
    assert.equal(nudge(tmp, "c13", "edit", "x")[0], "1 0.0"); // unreadable: start over
    assert.equal(nudge(tmp, "c14", "edit", " 7 2.0")[0], "1 0.0"); // the first space splits: "" is not an int
    assert.equal(nudge(tmp, "c15", "edit", "7 ٢.5")[0], "8 2.5"); // another script's digits read as digits
    fs.writeFileSync(posix.join(tmp, "akmon-delegation-nudge-c16.count"), Buffer.from([0x37, 0x20, 0xff]));
    assert.equal(nudge(tmp, "c16", "edit", null)[0], "1 0.0"); // not UTF-8: a ValueError, start over
    assert.equal(nudge(tmp, "c17", "bash", "9 29.5")[0], "9 29.5"); // not a counted kind: untouched
    assert.equal(nudge(tmp, "c18", "shell", "9 1e16")[0], "10 1e+16");
  });
});

test("the advisory fires once per episode; the ask fires once, never on a read; a delegation re-arms both", () => {
  withState({}, (tmp) => {
    const [, first] = nudge(tmp, "d1", "edit", "29 29.5");
    assert.match(String(first?.additionalContext), /^\[akmon\] Delegation check — a drift score of 30\.5 /);
    assert.equal(nudge(tmp, "d1", "edit", null)[1], null);
    const [, ask] = nudge(tmp, "d2", "shell", "130 125.0");
    assert.equal(ask?.permissionDecision, "ask");
    assert.match(String(ask?.permissionReason), /^\[akmon\] Sustained delegation drift — a drift score of 126 /);
    assert.equal(nudge(tmp, "d2", "shell", null)[1], null);
    assert.equal(nudge(tmp, "d3", "read", "130 125.0")[1], null); // a read never carries the ask
    assert.equal(fs.existsSync(posix.join(tmp, "akmon-delegation-nudge-d3.ask-marker")), false);
    assert.equal(nudge(tmp, "d3", "shell", null)[1]?.permissionDecision, "ask");
    assert.equal(nudge(tmp, "d4", "edit", "130 125.0", { permissionMode: "auto" })[1]?.permissionDecision, "deny");
    assert.equal(nudge(tmp, "d2", "subagent", null)[0], "0");
    assert.equal(fs.existsSync(posix.join(tmp, "akmon-delegation-nudge-d2.ask-marker")), false);
    assert.equal(nudge(tmp, "d2", "edit", null)[0], "1 0.0");
    assert.equal(nudge(tmp, "d5", "edit", "130 125.0", { isSubagent: true })[0], "130 125.0"); // exempt entirely
  });
});

test("the drift thresholds and grace read the environment as int() does", () => {
  withState(
    { AKMON_DELEGATION_GRACE: " 1_0 ", AKMON_DELEGATION_NUDGE_THRESHOLD: "٥", AKMON_DELEGATION_ASK_THRESHOLD: "3" },
    () => {
      assert.equal(delegationGrace(data), 10);
      assert.equal(delegationNudgeThreshold(data), 5);
      assert.equal(delegationAskThreshold(data), 5); // clamped up to the advisory
    },
  );
  withState(
    { AKMON_DELEGATION_GRACE: "-1", AKMON_DELEGATION_NUDGE_THRESHOLD: "0", AKMON_DELEGATION_ASK_THRESHOLD: "x" },
    () => {
      assert.deepEqual(
        [delegationGrace(data), delegationNudgeThreshold(data), delegationAskThreshold(data)],
        [8, 30, 120],
      );
    },
  );
  withState({ AKMON_DELEGATION_GRACE: "99999999999999999999" }, () => {
    assert.match(delegationNudgeMessage(data, 31), /the first 99999999999999999999 calls of a stretch nothing/);
  });
  withState({ AKMON_DELEGATION_GRACE: "\x1c3" }, () => {
    assert.equal(delegationGrace(data), 8); // U+001C is not whitespace to int()
  });
});

test("a session id no filename can carry is the exception open() raises", () => {
  withState({}, () => {
    assert.equal(thrown(() => delegationNudgeResult(data, "edit", "a\0b")).name, "ValueError");
    assert.equal(thrown(() => delegationNudgeResult(data, "edit", "\ud800")).name, "UnicodeEncodeError");
    assert.equal(thrown(() => delegationNudgeResult(data, "subagent", "a\0b")).name, "ValueError");
    assert.equal(delegationNudgeResult(data, "bash", "a\0b"), null); // not a counted kind: no file is touched
  });
});

test("a state file that cannot be written is silent (OSError), a directory in its place included", () => {
  withState({}, (tmp) => {
    fs.mkdirSync(posix.join(tmp, "akmon-delegation-nudge-e1.count"));
    assert.equal(delegationNudgeResult(data, "edit", "e1"), null);
    fs.writeFileSync(posix.join(tmp, "akmon-delegation-nudge-e2.count"), "40 39.0");
    fs.mkdirSync(posix.join(tmp, "akmon-delegation-nudge-e2.marker"));
    assert.equal(delegationNudgeResult(data, "edit", "e2"), null);
    assert.equal(delegationNudgeResult(data, "subagent", "e1"), null);
  });
});

/** A project directory: `AGENTS.md`, agents, and either the mounted tree or a package record. */
function project(
  /** @type {string} */ dir,
  /** @type {{mount: boolean, stale?: boolean, agents?: boolean}} */ options,
) {
  fs.mkdirSync(posix.join(dir, "_aitna"), { recursive: true });
  fs.writeFileSync(posix.join(dir, "AGENTS.md"), "# a\n");
  if (options.mount) {
    fs.symlinkSync(TREE_ROOT, posix.join(dir, "_aitna/akmon"));
  } else {
    fs.writeFileSync(posix.join(dir, "_aitna/.akmon.toml"), 'mount = "package"\n');
  }
  if (options.stale) {
    fs.mkdirSync(posix.join(dir, "_aitna/.akmon/guardrails"), { recursive: true });
    fs.writeFileSync(posix.join(dir, "_aitna/.akmon/guardrails/_common.md"), "old\n");
  }
  if (options.agents ?? true) {
    for (const name of ["zeta", "engineer", "Alpha", ".hidden"]) {
      fs.mkdirSync(posix.join(dir, "_aitna/agents", name), { recursive: true });
      fs.writeFileSync(posix.join(dir, "_aitna/agents", name, "README.md"), "x\n");
    }
    fs.mkdirSync(posix.join(dir, "_aitna/agents/no-readme"));
    fs.writeFileSync(posix.join(dir, "_aitna/agents/file.md"), "x\n");
    fs.mkdirSync(posix.join(dir, "agents/ops"), { recursive: true });
    fs.writeFileSync(posix.join(dir, "agents/ops/README.md"), "x\n");
  }
}

test("agentNames: sorted by code point, directories with a README, no dotted names", () => {
  withDir((dir) => {
    project(dir, { mount: true });
    assert.deepEqual(agentNames(`${dir}/_aitna/agents`), ["Alpha", "engineer", "zeta"]);
    assert.deepEqual(agentNames(`${dir}/agents`), ["ops"]);
    assert.deepEqual(agentNames(`${dir}/_aitna/agents/file.md`), []);
    assert.deepEqual(agentNames(`${dir}/missing`), []);
  });
});

test("sessionStartResult: the roster on a mounted project, no stale notice", () => {
  withDir((dir) => {
    project(dir, { mount: true });
    const result = sessionStartResult(data, dir);
    assert.equal(result?.eventName, "SessionStart");
    assert.equal(result?.systemMessage, null);
    assert.deepEqual(String(result?.additionalContext).split("\n").slice(0, 5), [
      "[akmon] Active-agent declaration",
      "Before doing project work, state which agent you are operating as, and restate it whenever you switch. Format: `🧭 agent: <name> — <focus>`.",
      "- DEVELOP (build the project): Alpha, engineer, zeta",
      "- OPERATE (run/use from outside): ops",
      "No agent is active yet.",
    ]);
    assert.match(
      String(result?.additionalContext),
      /\nAlso: read `_aitna\/memory\/` at session start \(project memory\)\.$/,
    );
  });
});

test("sessionStartResult: a package project with a stale copy says so on both channels", () => {
  withDir((dir) => {
    project(dir, { mount: false, stale: true });
    const result = sessionStartResult(data, dir);
    const notice = staleGuardrailNotice(data, dir);
    assert.match(
      String(notice),
      /^⚠ akmon: the rules in _aitna\/\.akmon\/ are not the ones this session's akmon ships \(guardrails\/_common\.md\)\./,
    );
    assert.equal(result?.systemMessage, notice);
    assert.ok(String(result?.additionalContext).endsWith(String(notice)));
  });
  withDir((dir) => {
    project(dir, { mount: false, stale: true, agents: false });
    const result = sessionStartResult(data, dir);
    assert.equal(result?.additionalContext, result?.systemMessage); // no roster: the notice alone
  });
  withDir((dir) => {
    project(dir, { mount: false, agents: false });
    assert.equal(sessionStartResult(data, dir), null);
  });
});

test("runtimeRootDisplay: project-relative when the executing tree is the mount, else akmon path", () => {
  withDir((dir) => {
    project(dir, { mount: true });
    assert.equal(runtimeRootDisplay(dir), "_aitna/akmon");
  });
  withDir((dir) => {
    project(dir, { mount: false });
    assert.equal(runtimeRootDisplay(dir), "$(akmon path)");
  });
});

test("currentGitBranch: the branch in a repository, empty outside one", () => {
  const probe = spawnSync("git", ["--version"]);
  if (probe.error !== undefined) {
    return; // no git on this host: the twin answers "" the same way
  }
  withDir((dir) => {
    const here = process.cwd();
    try {
      process.chdir(dir);
      assert.equal(currentGitBranch(), "");
      spawnSync("git", ["init", "-q", "-b", "feat"], { cwd: dir });
      spawnSync("git", ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], {
        cwd: dir,
      });
      assert.equal(currentGitBranch(), "feat");
    } finally {
      process.chdir(here);
    }
  });
});
