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

import { DataFileError } from "../common/jsondata.mjs";
import { pyError } from "../common/pyvalue.mjs";
import {
  HookResult,
  agentDefinitions,
  agentNames,
  agentRoles,
  analysisBeforeMutationMessage,
  analysisWriteResult,
  askIsAttended,
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
  GitInvocation,
  gitInvocations,
  hookFailureDiagnostic,
  hookFailureNotice,
  isCodePath,
  isPlanningDoc,
  neutralKind,
  normpath,
  privilegeEscalationGuardResult,
  readTool,
  repositoryFacts,
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
    const names = ["TMPDIR", "TEMP", "TMP", ...Object.keys(env)];
    const saved = names.map((name) => process.env[name]);
    try {
      for (const name of ["TEMP", "TMP"]) {
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
  withDir((start) => {
    // the recovery command names the dev root found from `start`: the default where no project is
    assert.equal(
      hookFailureNotice("gate-audit", pyError("ValueError", "x"), start),
      "⚠ akmon: the gate-audit hook failed (ValueError) and was skipped — this action went ahead without it. " +
        "Check the setup: `akmon verify` (a mounted tree: `python3 _aitna/akmon/bin/verify.py`).",
    );
    fs.writeFileSync(posix.join(start, "AGENTS.md"), "# A\n");
    fs.writeFileSync(posix.join(start, ".aitna-root"), "meta\n");
    assert.ok(
      hookFailureNotice("gate-audit", pyError("ValueError", "x"), start).endsWith(
        "(a mounted tree: `python3 meta/akmon/bin/verify.py`).",
      ),
    );
    // a declaration the lookup refuses is no reason for the crash report to crash
    fs.writeFileSync(posix.join(start, ".aitna-root"), "../out\n");
    assert.ok(hookFailureNotice("gate-audit", pyError("ValueError", "x"), start).includes("python3 _aitna/akmon"));
  });
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
  withDir((project) => {
    fs.writeFileSync(posix.join(project, ".aitna-root"), "Dev/\n");
    assert.equal(isPlanningDoc(data, "dev/design/a.md", project), true);
    assert.equal(isPlanningDoc(data, "_aitna/design/a.md", project), false);
    assert.equal(isCodePath(data, "dev/memory/a.py", project), false);
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

// The shared case table of the harness settings guard (also run by meta/tests/test_harness_settings.py): the
// shell route reads a command's words, and a command that writes a harness settings file is denied for every actor.
const HARNESS_CASES = JSON.parse(
  fs.readFileSync(posix.join(TREE_ROOT, "meta", "conformance", "units", "harness_settings_cases.json"), "utf8"),
);

test("the privilege guard decides the shell route as the shared harness-settings table says", () => {
  for (const item of HARNESS_CASES.bash) {
    const label = `${item.start}: ${JSON.stringify(item.command)}`;
    const result = privilegeEscalationGuardResult(data, item.command, item.start);
    assert.equal(result === null ? "pass" : result.permissionDecision, item.decision, label);
    assert.equal(result === null ? "PreToolUse" : result.eventName, "PreToolUse", label);
    for (const text of item.contains ?? []) {
      assert.ok(String(result?.permissionReason).includes(text), `${label}: ${result?.permissionReason}`);
    }
  }
});

test("the shell route reads the process directory when none is given", () => {
  withDir((dir) => {
    fs.mkdirSync(posix.join(dir, ".claude"));
    const saved = process.cwd();
    process.chdir(posix.join(dir, ".claude"));
    try {
      assert.notEqual(privilegeEscalationGuardResult(data, "echo x > settings.json"), null);
      assert.equal(privilegeEscalationGuardResult(data, "echo x > notes.md"), null);
    } finally {
      process.chdir(saved);
    }
  });
});

test("the settings reason is its own text, and the elevation deny comes first", () => {
  const elevated = privilegeEscalationGuardResult(data, "sudo tee .claude/settings.json", "/p");
  const settings = privilegeEscalationGuardResult(data, "echo x > .claude/settings.json", "/p");
  assert.equal(elevated?.permissionReason, data.core.privilege_escalation_reason);
  assert.notEqual(settings?.permissionReason, elevated?.permissionReason);
});

test("a redirection is read as a write only for an output operator, and the data owns the shell programs", () => {
  for (const [command, denied] of /** @type {[string, boolean][]} */ ([
    ["cat < .claude/settings.json", false],
    ["cat <> .claude/settings.json", true],
    ["cat <<< x > .claude/settings.json", true],
    ["tee .claude/settings.json", true],
  ])) {
    assert.equal(privilegeEscalationGuardResult(data, command, "/p") !== null, denied, command);
  }
  const changed = {
    ...data,
    harnessSettings: {
      ...data.harnessSettings,
      shell: { ...data.harnessSettings.shell, write_all_operands: [], write_last_operand: ["ln"] },
    },
  };
  assert.equal(privilegeEscalationGuardResult(changed, "tee .claude/settings.json", "/p"), null);
  assert.notEqual(privilegeEscalationGuardResult(changed, "ln -s x .claude/settings.json", "/p"), null);
  assert.equal(privilegeEscalationGuardResult(changed, "cp x .claude/settings.json", "/p"), null);
});

// The shared case table (also run by meta/tests/test_hook_core.py): the scanner's answers and the
// guard's decisions, with the repositories a lookup stands in for.
const COMMIT_CASES = JSON.parse(
  fs.readFileSync(posix.join(TREE_ROOT, "meta", "conformance", "units", "commit_guard_cases.json"), "utf8"),
);
/** @type {Record<string, {linked: boolean, branch: string}>} */
const REPOSITORIES = COMMIT_CASES.repositories;
/** @param {string} directory */
const lookup = (directory) => (Object.hasOwn(REPOSITORIES, directory) ? REPOSITORIES[directory] : null);

/**
 * The guard run as the session would at `start`, with the shared table's repositories.
 * @param {string} command
 * @param {string | null} start
 * @param {{permissionMode?: string | null, attended?: boolean | null, actor?: import("../common/access_matrix.mjs").Actor, runBranch?: string | null}} [options]
 */
const guard = (command, start = "/wt", options = {}) =>
  gitCommitGuardResult(data, command, { directory: start, repositoryAt: lookup, ...options });

test("the scanner finds the git commands the shared table lists", () => {
  for (const item of COMMIT_CASES.scanner) {
    const found = gitInvocations(item.command, item.start, { homeDirectory: item.home });
    assert.deepEqual(
      found.map((one) => [one.subcommand, one.directory]),
      item.expected,
      `${item.start}: ${JSON.stringify(item.command)}`,
    );
  }
});

test("the guard decides as the shared table says", () => {
  for (const item of COMMIT_CASES.guard) {
    const label = `${item.start}: ${JSON.stringify(item.command)}`;
    const result = guard(item.command, item.start, {
      permissionMode: item.mode,
      attended: item.attended,
      actor: item.actor ?? "developer",
      runBranch: item.run_branch ?? null,
    });
    assert.equal(result === null ? "pass" : result.permissionDecision, item.decision, label);
    const reason = String(result?.permissionReason ?? "");
    for (const text of item.contains) {
      assert.ok(reason.includes(text), `${label}: ${reason}`);
    }
    for (const text of item.absent) {
      assert.ok(!reason.includes(text), `${label}: ${reason}`);
    }
  }
});

test("the commit guard reads the outcomes from the matrix data, not from code", () => {
  // Flip one cell: the autonomous push of its own branch now asks; nothing else changed.
  const flipped = {
    ...data,
    accessMatrix: { ...data.accessMatrix, autonomous: { ...data.accessMatrix.autonomous, push_own_branch: "ask" } },
  };
  const result = gitCommitGuardResult(flipped, "git push origin feat", {
    directory: "/wt",
    repositoryAt: lookup,
    actor: "autonomous",
    runBranch: "feat",
    permissionMode: "default",
  });
  assert.equal(result?.permissionDecision, "ask");
  assert.ok(String(result?.permissionReason).includes("own branch 'feat'"));
});

test("the commit guard reads the run branch patterns from the matrix data, not from code", () => {
  const changed = {
    ...data,
    accessMatrix: {
      ...data.accessMatrix,
      run_branch_patterns: { developer: [], autonomous: ["^bot/"] },
    },
  };
  /** @type {Record<string, {linked: boolean, branch: string}>} */
  const repositories = {
    "/bot": { linked: false, branch: "bot/x" },
    "/agent": { linked: false, branch: "agent/C203-x" },
  };
  /** @param {string} command @param {string} start */
  const run = (command, start) =>
    gitCommitGuardResult(changed, command, {
      directory: start,
      repositoryAt: (directory) => repositories[directory] ?? null,
      actor: "autonomous",
      permissionMode: "default",
    });
  assert.equal(run("git commit -m x", "/bot"), null);
  assert.equal(run("git push origin bot/x", "/bot"), null);
  assert.equal(run("git commit -m x", "/agent")?.permissionDecision, "deny");
});

test("a developer never reaches the run branch class", () => {
  // Soften the class for the developer; its outcome on a checkout branch is the class it had before.
  const changed = {
    ...data,
    accessMatrix: {
      ...data.accessMatrix,
      developer: { ...data.accessMatrix.developer, history_not_run_branch: "deny" },
    },
  };
  const result = gitCommitGuardResult(changed, "git commit -m x", {
    directory: "/clone",
    repositoryAt: () => ({ linked: false, branch: "feat" }),
    actor: "developer",
    permissionMode: "default",
  });
  assert.equal(result?.permissionDecision, "ask");
  assert.ok(!String(result?.permissionReason).includes("not the run's own branch"));
});

test("a developer's push asks the repository nothing", () => {
  /** @type {string[]} */
  const asked = [];
  gitCommitGuardResult(data, "git push origin feat", {
    directory: "/wt",
    repositoryAt: (directory) => {
      asked.push(directory);
      return null;
    },
  });
  assert.deepEqual(asked, []);
});

test("an unknown actor string is refused where the guard is called directly", () => {
  assert.throws(
    () =>
      gitCommitGuardResult(data, "git push", {
        directory: "/wt",
        repositoryAt: lookup,
        actor: /** @type {any} */ ("guided"),
      }),
    /no entry for actor 'guided'/,
  );
});

test("gh invocations carry their program and group-action", () => {
  const found = gitInvocations("git push && cd /w && gh -R o/r pr create --fill", "/s");
  assert.deepEqual(
    found.map((one) => [one.program, one.subcommand, one.directory]),
    [
      ["git", "push", "/s"],
      ["gh", "pr create", "/w"],
    ],
  );
  assert.deepEqual([...found[1].arguments], ["--fill"]);
  assert.equal(new GitInvocation({ subcommand: "status", directory: "/s" }).program, "git");
});

test("glab invocations carry their program and group-action", () => {
  const found = gitInvocations("glab -R o/r mr create -b develop && /usr/bin/glab mr merge 3", "/s");
  assert.deepEqual(
    found.map((one) => [one.program, one.subcommand, [...one.arguments]]),
    [
      ["glab", "mr create", ["-b", "develop"]],
      ["glab", "mr merge", ["3"]],
    ],
  );
});

test("the commit guard reads the protected branches from the matrix data, not from code", () => {
  const changed = {
    ...data,
    accessMatrix: {
      ...data.accessMatrix,
      protected_branches: { developer: ["feat"], autonomous: ["release"] },
    },
  };
  /** @type {Record<string, {linked: boolean, branch: string}>} */
  const repositories = {
    "/wt": { linked: true, branch: "feat" },
    "/rel": { linked: true, branch: "release" },
    "/dev": { linked: true, branch: "develop" },
  };
  /** @param {string} command @param {string} start @param {"developer" | "autonomous"} actor */
  const run = (command, start, actor) =>
    gitCommitGuardResult(changed, command, {
      directory: start,
      repositoryAt: (directory) => repositories[directory] ?? null,
      actor,
      permissionMode: "default",
    });
  assert.equal(run("git commit -m x", "/rel", "autonomous")?.permissionDecision, "deny");
  assert.equal(run("git push origin release", "/wt", "autonomous")?.permissionDecision, "deny");
  assert.equal(run("git commit -m x", "/dev", "autonomous"), null); // develop is no longer protected
  assert.equal(run("git commit -m x", "/wt", "developer")?.permissionDecision, "ask");
});

test("the commit guard: the trailer is read in the whole text, a heredoc body included", () => {
  const command = "git commit -F - <<'EOF'\nsubject\n\nCo-Authored-By: Claude\nEOF";
  assert.deepEqual(
    gitInvocations(command, "/wt").map((one) => [one.subcommand, one.directory]),
    [["commit", "/wt"]],
  );
  assert.equal(guard(command)?.permissionDecision, "deny");
  assert.equal(guard("git co‑authored-by"), null); // a non-breaking hyphen is not a hyphen
});

test("the commit guard: a heredoc body or a quoted argument that names a git command is text", () => {
  assert.equal(guard("cat <<'EOF'\n`git merge --squash x`\nEOF", "/main", { permissionMode: "default" }), null);
  assert.equal(guard("grep 'git merge' f", "/main", { permissionMode: "default" }), null);
});

test("the commit guard: a worktree commit passes, a main-checkout commit asks, push asks in both", () => {
  const heredoc = "git commit -m \"$(cat <<'EOF'\nsubject\nEOF\n)\"";
  assert.equal(guard(heredoc, "/wt", { permissionMode: "default" }), null);
  assert.equal(guard(heredoc, "/main", { permissionMode: "default" })?.permissionDecision, "ask");
  assert.equal(guard("cd /wt && git commit -m x", "/main", { permissionMode: "default" }), null);
  assert.equal(guard("git -C /main commit -m x", "/wt", { permissionMode: "default" })?.permissionDecision, "ask");
  assert.equal(guard("bash -c 'git merge x'", "/main", { permissionMode: "default" })?.permissionDecision, "ask");
  assert.equal(guard("git push", "/wt", { permissionMode: "default" })?.permissionDecision, "ask");
  assert.equal(guard("git push", "/wt", { permissionMode: "auto" })?.permissionDecision, "deny");
  const landing = guard("git commit -m x", "/wt-detached", { permissionMode: "default" });
  assert.match(String(landing?.permissionReason), /git commit writes history in \/wt-detached \(a detached HEAD\)/);
});

test("the commit guard asks the repository only for a history-writing invocation, with its directory", () => {
  /** @type {string[]} */
  const asked = [];
  /** @param {string} directory */
  const spy = (directory) => {
    asked.push(directory);
    return lookup(directory);
  };
  gitCommitGuardResult(data, "git status && git push; cd /main && git commit -m y", {
    directory: "/s",
    repositoryAt: spy,
  });
  assert.deepEqual(asked, []);
  gitCommitGuardResult(data, "cd /wt && git commit -m x && git status; git log", {
    directory: "/s",
    repositoryAt: spy,
  });
  assert.deepEqual(asked, ["/wt"]);
  const unresolved = gitCommitGuardResult(data, 'cd "$HOME/w" && git commit -m x', {
    directory: "/wt",
    repositoryAt: spy,
    permissionMode: "default",
  });
  assert.deepEqual(asked, ["/wt"]);
  assert.match(String(unresolved?.permissionReason), /cannot resolve/);
});

test("the live lookup reads git: a linked worktree passes, the main checkout and a non-repository ask", () => {
  withDir((dir) => {
    /** @param {string[]} args @param {string} cwd */
    const git = (args, cwd) =>
      spawnSync("git", ["-C", cwd, "-c", "user.name=t", "-c", "user.email=t@example.invalid", ...args], {
        stdio: "ignore",
      });
    const main = posix.join(dir, "main");
    fs.mkdirSync(main);
    git(["init", "-q", "-b", "main"], main);
    git(["commit", "-q", "--allow-empty", "-m", "first"], main);
    git(["worktree", "add", "-q", "-b", "feat", posix.join(dir, "wt")], main);
    git(["worktree", "add", "-q", "--detach", posix.join(dir, "detached")], main);
    fs.mkdirSync(posix.join(dir, "plain"));
    assert.deepEqual({ ...repositoryFacts(main) }, { linked: false, branch: "main" });
    assert.deepEqual({ ...repositoryFacts(posix.join(dir, "wt")) }, { linked: true, branch: "feat" });
    assert.deepEqual({ ...repositoryFacts(posix.join(dir, "detached")) }, { linked: true, branch: "" });
    assert.equal(repositoryFacts(posix.join(dir, "plain")), null);
    assert.equal(repositoryFacts(posix.join(dir, "missing")), null);
    /** @param {string} directory */
    const run = (directory) => gitCommitGuardResult(data, "git commit -m x", { directory, permissionMode: "default" });
    assert.equal(run(posix.join(dir, "wt")), null);
    assert.equal(run(main)?.permissionDecision, "ask");
    assert.equal(run(posix.join(dir, "detached"))?.permissionDecision, "ask");
    assert.match(String(run(posix.join(dir, "plain"))?.permissionReason), /not a git repository/);
  });
});

test("a non-string command is the TypeError re.search raises", () => {
  assert.equal(thrown(() => gitCommitGuardResult(data, ["git"])).name, "TypeError");
  assert.equal(gitCommitGuardResult(data, ["x"]), null); // `"git" in ["x"]` is False
  assert.equal(thrown(() => gitCommitGuardResult(data, 5)).name, "TypeError");
});

test("the trailer floor is decided before and without the access matrix, for every actor", () => {
  // a bundle whose matrix cannot be read: the floor still denies, because it never reads the matrix
  const unreadable = /** @type {import("./hook_data.mjs").HookData} */ (
    /** @type {unknown} */ (
      Object.defineProperties(
        {},
        {
          core: { enumerable: true, get: () => data.core },
          accessMatrix: {
            enumerable: true,
            get() {
              throw new Error("the trailer floor must not read the access matrix");
            },
          },
        },
      )
    )
  );
  for (const actor of /** @type {const} */ (["developer", "autonomous"])) {
    for (const command of ["git commit -m 'Co-Authored-By: Claude'", "gh pr create --body 'Co-Authored-By: Claude'"]) {
      const result = gitCommitGuardResult(unreadable, command, {
        directory: "/main",
        repositoryAt: lookup,
        actor,
      });
      assert.ok(result !== null, `${actor}: ${command}`);
      assert.equal(result.permissionDecision, "deny");
      assert.ok(String(result.permissionReason).includes("Co-Authored-By"), String(result.permissionReason));
    }
  }
});

test("a hook data bundle refuses a matrix that softens the trailer floor, on every access", () => {
  const root = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-matrix-"));
  try {
    fs.mkdirSync(posix.join(root, "common"), { recursive: true });
    const softened = JSON.parse(fs.readFileSync(posix.join(TREE_ROOT, "common", "access_matrix.json"), "utf8"));
    softened.autonomous.ai_trailer = "ask";
    fs.writeFileSync(posix.join(root, "common", "access_matrix.json"), JSON.stringify(softened));
    const bundle = lazyHookData(root);
    assert.throws(() => bundle.accessMatrix, DataFileError);
    assert.throws(() => bundle.accessMatrix, DataFileError);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("an unattended ask is a deny that spells the permission mode with repr()", () => {
  const reasonTail = (/** @type {string | null} */ mode) => {
    const result = guard("git push", "/wt", { permissionMode: mode });
    return [
      result?.permissionDecision,
      String(result?.permissionReason).match(/permission_mode=(.*?), CLAUDE_CODE_SESSION_ATTENDED=/)?.[1],
    ];
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

// ADR-0025/D06: the host's attendance statement decides; the permission mode decides only where the host
// states nothing, and a mode that skips every question is never attended. [mode, attended, the ask passes]
/** @type {Array<[string | null, boolean | null, boolean]>} */
const ATTENDANCE_CELLS = [
  ["auto", true, true],
  ["default", false, false],
  ["default", null, true],
  ["auto", null, false],
  ["bypassPermissions", true, false],
  ["dontAsk", true, false],
  [null, true, true],
  [null, null, false],
];

test("an ask is attended by the host's statement, then by the mode (ADR-0025/D06)", () => {
  for (const [mode, attended, passes] of ATTENDANCE_CELLS) {
    assert.equal(askIsAttended(data, mode, { attended }), passes, `${mode} ${attended}`);
  }
});

test("the commit guard's ask follows attendance and names both values when it escalates", () => {
  for (const [mode, attended, passes] of ATTENDANCE_CELLS) {
    const result = guard("git push", "/wt", { permissionMode: mode, attended });
    assert.equal(result?.permissionDecision, passes ? "ask" : "deny", `${mode} ${attended}`);
    const reason = String(result?.permissionReason);
    assert.equal(reason.includes("escalated ask"), !passes);
    if (!passes) {
      const label = attended === null ? "unset" : attended ? "1" : "0";
      assert.ok(reason.includes(`CLAUDE_CODE_SESSION_ATTENDED=${label}`), reason);
      assert.ok(reason.includes("ADR-0025/D06"), reason);
    }
  }
});

test("the delegation ask follows attendance", () => {
  withState({}, (tmp) => {
    let n = 0;
    for (const [mode, attended, passes] of ATTENDANCE_CELLS) {
      const result = nudge(tmp, `att${n++}`, "shell", "130 125.0", { permissionMode: mode, attended })[1];
      assert.equal(result?.permissionDecision, passes ? "ask" : "deny", `${mode} ${attended}`);
    }
  });
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
  /** @type {{permissionMode?: string | null, isSubagent?: boolean, attended?: boolean | null}} */ options = {
    permissionMode: "default",
  },
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

/**
 * Write a README into each named charter directory under `base`.
 * @param {string} base
 * @param {string[]} names
 * @returns {void}
 */
function charters(base, names) {
  for (const name of names) {
    fs.mkdirSync(posix.join(base, name), { recursive: true });
    fs.writeFileSync(posix.join(base, name, "README.md"), "charter\n");
  }
}

test("agentNames: the shipped agents in chain order, then the rest by name", () => {
  withDir((dir) => {
    charters(dir, ["release", "analyst", "learning", "development", "zeta"]);
    assert.deepEqual(agentNames(dir, agentDefinitions(data)), [
      "development",
      "learning",
      "release",
      "analyst",
      "zeta",
    ]);
  });
});

test("agentNames: a legacy role directory is left out only beside its agent's own charter", () => {
  withDir((dir) => {
    charters(dir, ["development", "review", "architect", "engineer", "learn", "learning"]);
    assert.deepEqual(agentNames(dir, agentDefinitions(data)), ["development", "learning"]);
  });
  withDir((dir) => {
    charters(dir, ["development", "review", "learn"]);
    assert.deepEqual(agentNames(dir, agentDefinitions(data)), ["development", "learn"]);
  });
});

test("sessionStartResult: a project's own agents follow the shipped ones, and no legacy role is listed twice", () => {
  withDir((dir) => {
    project(dir, { mount: true, agents: false });
    charters(posix.join(dir, "_aitna/agents"), ["release", "analyst", "development", "engineer", "review"]);
    fs.writeFileSync(posix.join(dir, "_aitna/agents/analyst/README.md"), "runs `roles/analyst.md`\n");
    const context = String(sessionStartResult(data, dir)?.additionalContext);
    assert.match(
      context,
      /development — roles review, architect, engineer; release — role release; analyst — role analyst\n/,
    );
  });
});

test("sessionStartResult: a broken work-style file loses the work-style line and nothing else", () => {
  withDir((dir) => {
    project(dir, { mount: true });
    const whole = String(sessionStartResult(data, dir)?.additionalContext);
    assert.match(whole, /\nwork style: delegating \(default\)\n/);
    const expected = whole
      .split("\n")
      .filter((line) => !line.startsWith("work style:"))
      .join("\n");
    const breakages = [
      {
        get: () => {
          throw new DataFileError("akmon data file x is not valid JSON");
        },
      },
      { value: {} },
      { value: { styles: null } },
    ];
    for (const breakage of breakages) {
      const broken = Object.create(data, { workStyle: breakage });
      assert.equal(sessionStartResult(broken, dir)?.additionalContext, expected);
    }
    const other = Object.create(data, {
      workStyle: {
        get: () => {
          throw new RangeError("not a data-file error");
        },
      },
    });
    assert.throws(() => sessionStartResult(other, dir), RangeError);
  });
});

test("sessionStartResult: the roster on a mounted project, no stale notice", () => {
  withDir((dir) => {
    project(dir, { mount: true });
    const result = sessionStartResult(data, dir);
    assert.equal(result?.eventName, "SessionStart");
    assert.equal(result?.systemMessage, null);
    assert.deepEqual(String(result?.additionalContext).split("\n").slice(0, 5), [
      "[akmon] Role declaration",
      "Before doing project work, state which role you are operating in, and restate it whenever you switch. Format: `🧭 role: <name> — <focus>`.",
      "- DEVELOP (build the project), agents and the roles they work in: Alpha — role Alpha; engineer — role engineer; zeta — role zeta",
      "- OPERATE (run/use from outside), agents and the roles they work in: ops — role ops",
      "No role is declared yet.",
    ]);
    assert.match(
      String(result?.additionalContext),
      /\nAlso: read `_aitna\/memory\/` at session start \(project memory\)\.$/,
    );
  });
});

test("sessionStartResult: an agent reads as its roles, release as its own role, and the pick names a role", () => {
  withDir((dir) => {
    project(dir, { mount: true });
    fs.mkdirSync(posix.join(dir, "_aitna/agents/development"), { recursive: true });
    fs.writeFileSync(
      posix.join(dir, "_aitna/agents/development/README.md"),
      "## review\nRole of record: `roles/review.md`.\n## architect\n`_aitna/akmon/roles/architect.md`\n" +
        "## engineer\n`roles/engineer.md` and again `roles/review.md`\n",
    );
    const context = String(sessionStartResult(data, dir)?.additionalContext);
    assert.match(context, /: development — roles review, architect, engineer; Alpha — role Alpha; zeta — role zeta\n/);
    assert.match(context, /\nPick the role \(never an agent name\) by operation: decompose an existing thing → review/);
  });
  withDir((dir) => {
    project(dir, { mount: true, agents: false });
    fs.mkdirSync(posix.join(dir, "agents/ops"), { recursive: true });
    fs.writeFileSync(posix.join(dir, "agents/ops/README.md"), "x\n");
    const context = String(sessionStartResult(data, dir)?.additionalContext);
    assert.match(
      context,
      /\nPick the role the task calls for, one of the roles listed above, never an agent name; if unclear, ask\.\n/,
    );
  });
});

test("agentRoles: the definitions' roles, else the charter's role references in order, else the agent's own name", () => {
  withDir((dir) => {
    fs.mkdirSync(posix.join(dir, "development"));
    fs.writeFileSync(posix.join(dir, "development/README.md"), "see roles/README.md and roles/Review.md\n");
    fs.mkdirSync(posix.join(dir, "learn"));
    fs.writeFileSync(posix.join(dir, "learn/README.md"), "x\n");
    const known = { development: ["review", "architect", "engineer"], learning: ["learn"] };
    // a named agent takes its definition's roles, whatever its charter says
    assert.deepEqual(agentRoles(dir, "development", known), ["review", "architect", "engineer"]);
    assert.deepEqual(agentRoles(dir, "learning", known), ["learn"]);
    // an agent no definition names keeps the charter fallback: its references, else its own name
    assert.deepEqual(agentRoles(dir, "learn", known), ["learn"]);
    assert.deepEqual(agentRoles(dir, "development", {}), ["development"]);
    assert.deepEqual(agentRoles(dir, "missing", known), ["missing"]);
    assert.deepEqual(agentRoles(dir, "constructor", known), ["constructor"]);
    fs.writeFileSync(posix.join(dir, "learn/README.md"), "see `akmon/roles/review.md` and roles/learn.md\n");
    assert.deepEqual(agentRoles(dir, "learn", known), ["review", "learn"]);
  });
});

test("agentDefinitions: the shipped agents and their roles, read from agents/agents.json", () => {
  assert.deepEqual(agentDefinitions(data), {
    development: ["review", "architect", "engineer"],
    learning: ["learn"],
    release: ["release"],
  });
  assert.deepEqual(Object.keys(agentDefinitions(data)), ["development", "learning", "release"]);
});

test("sessionStartResult: the development, learning and release agents name their roles", () => {
  withDir((dir) => {
    project(dir, { mount: true, agents: false });
    for (const agent of ["release", "learning", "development"]) {
      fs.mkdirSync(posix.join(dir, "_aitna/agents", agent), { recursive: true });
      fs.writeFileSync(posix.join(dir, "_aitna/agents", agent, "README.md"), "x\n");
    }
    const context = String(sessionStartResult(data, dir)?.additionalContext);
    assert.match(
      context,
      /agents and the roles they work in: development — roles review, architect, engineer; learning — role learn; release — role release\n/,
    );
  });
});

test("sessionStartResult: a legacy learn charter keeps its fallback role", () => {
  withDir((dir) => {
    project(dir, { mount: true, agents: false });
    fs.mkdirSync(posix.join(dir, "_aitna/agents/learn"), { recursive: true });
    fs.writeFileSync(posix.join(dir, "_aitna/agents/learn/README.md"), "x\n");
    const context = String(sessionStartResult(data, dir)?.additionalContext);
    assert.match(context, /agents and the roles they work in: learn — role learn\n/);
  });
});

test("sessionStartResult: akmon's own root agents/ definition files are not OPERATE agents", () => {
  withDir((dir) => {
    project(dir, { mount: true, agents: false });
    fs.mkdirSync(posix.join(dir, "agents"));
    for (const name of ["README.md", "development.md", "release.md", "learning.md", "agents.json"]) {
      fs.writeFileSync(posix.join(dir, "agents", name), "definition\n");
    }
    assert.doesNotMatch(String(sessionStartResult(data, dir)?.additionalContext), /OPERATE/);
    // a project's own runtime agent is still listed; its role is its charter's, never a shipped agent's
    fs.mkdirSync(posix.join(dir, "agents/release"));
    fs.writeFileSync(posix.join(dir, "agents/release/README.md"), "runs `roles/analyst.md`\n");
    assert.match(
      String(sessionStartResult(data, dir)?.additionalContext),
      /OPERATE \(run\/use from outside\), agents and the roles they work in: release — role analyst\n/,
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

test("the scanner keeps the arguments after the subcommand", () => {
  const [found] = gitInvocations("git -C /x branch -D 'a b' -- c", "/s");
  assert.deepEqual(
    [found.subcommand, found.directory, [...found.arguments]],
    ["branch", "/x", ["-D", "a b", "--", "c"]],
  );
});

test("the scanner marks a git run under configuration overrides", () => {
  for (const command of [
    "git -c push.default=current push",
    "git --config-env push.default=V push",
    "git --config-env=a=B push",
  ]) {
    const [found] = gitInvocations(command, "/s");
    assert.deepEqual([found.subcommand, [...found.arguments], found.configOverride], ["push", [], true], command);
  }
  assert.equal(gitInvocations("git -C /x push origin x", "/s")[0].configOverride, false);
});

test("the scanner keeps every word after api, options included", () => {
  const [found] = gitInvocations("gh -R o/r api -X POST repos/o/r/issues -f a=b", "/s");
  assert.deepEqual(
    [found.program, found.subcommand, [...found.arguments]],
    ["gh", "api", ["-X", "POST", "repos/o/r/issues", "-f", "a=b"]],
  );
  const [action] = gitInvocations("gh repo sync o/r", "/s");
  assert.deepEqual([action.subcommand, [...action.arguments]], ["repo sync", ["o/r"]]);
});
