/**
 * node:test for `js/common/check_runner.mjs` — the record's `[check]` table, the `{files}`
 * scope rule and the finding per command, data-driven against `common/check_runner.json` and
 * a synthetic git repository.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ScopeError, argvFor, changedFiles, configTarget, defaultFiles, filesPlaceholder, makeCheck,
  noChecks, readChecks, runChecks } from "./check_runner.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../../common/check_runner.json", import.meta.url), "utf-8"));

test("the config texts and the default patterns come from the shared data file", () => {
  assert.equal(configTarget(data), ".akmon.toml [check]");
  assert.equal(filesPlaceholder(data), "{files}");
  assert.deepEqual(defaultFiles(data), ["*.py"]);
  assert.deepEqual(noChecks(data), ["declares no checks, so nothing ran", "Name the project's checks under [check], or run akmon init to set them up"]);
});

test("read_checks accepts a plain command and a command+files table", () => {
  const { checks, problems } = readChecks(data, {
    lint: "ruff check {files}",
    types: { command: "mypy {files}", files: ["*.py"] },
  });
  assert.deepEqual(problems, []);
  assert.equal(checks.length, 2);
  assert.deepEqual(checks[0].argv, ["ruff", "check", "{files}"]);
  assert.deepEqual(checks[0].files, ["*.py"]);
  assert.deepEqual(checks[1].files, ["*.py"]);
});

test("a malformed entry is reported and skipped, never guessed at", () => {
  const { checks, problems } = readChecks(data, {
    good: "ruff check {files}",
    number: 42,
    unknown: { command: "ruff", extra: 1 },
    empty: { command: "   " },
    bad_files: { command: "ruff", files: "src/**/*.py" },
    unsplit: 'ruff check "*.py',
  });
  assert.equal(checks.length, 1);
  assert.match(problems[0], /\[check\]\.number must be a command string/);
  assert.match(problems[1], /\[check\]\.unknown has an unknown key 'extra'/);
  assert.match(problems[2], /\[check\]\.empty needs a non-empty `command`/);
  assert.match(problems[3], /\[check\]\.bad_files\.files must be a non-empty list/);
  assert.match(problems[4], /\[check\]\.unsplit command does not split into arguments: No closing quotation/);
});

test("a non-table [check] is one problem, no guess", () => {
  assert.deepEqual(readChecks(data, "ruff check"), { checks: [], problems: ["[check] must be a table of named commands"] });
  assert.deepEqual(readChecks(data, null), { checks: [], problems: [] });
});

test("argv_for keeps the command unchanged without the placeholder", () => {
  const check = makeCheck(data, "lint", ["ruff", "check", "."]);
  assert.deepEqual(argvFor(data, check, ["a.py"]), ["ruff", "check", "."]);
});

test("argv_for expands the placeholder: the whole project, or only the matching changed files", () => {
  const check = makeCheck(data, "lint", ["ruff", "check", "{files}"]);
  assert.deepEqual(argvFor(data, check, null), ["ruff", "check", "."]);
  assert.deepEqual(argvFor(data, check, ["a.py", "b.txt", "c.py"]), ["ruff", "check", "a.py", "c.py"]);
  assert.equal(argvFor(data, check, ["b.txt"]), null);
});

function git_repo() {
  const root = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-check-runner-"));
  const git = (/** @type {string[]} */ ...args) => execFileSync("git", ["-C", root, ...args], { stdio: "ignore" });
  git("init", "-b", "main");
  git("config", "user.name", "Test");
  git("config", "user.email", "test@example.com");
  fs.writeFileSync(posix.join(root, "a.py"), "x = 1\n");
  git("add", "a.py");
  git("commit", "-m", "base");
  return root;
}

test("changed_files lists the diff against HEAD plus the new files, never the dev layer", () => {
  const root = git_repo();
  fs.writeFileSync(posix.join(root, "a.py"), "x = 2\n");
  fs.writeFileSync(posix.join(root, "b.py"), "y = 1\n");
  fs.mkdirSync(posix.join(root, "_aitna"));
  fs.writeFileSync(posix.join(root, "_aitna", "note.md"), "dev layer\n");
  fs.writeFileSync(posix.join(root, "b.txt"), "not python\n");
  assert.deepEqual(changedFiles(data, root), ["a.py", "b.py", "b.txt"]);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a git that cannot list the changes is a ScopeError naming the command and its status", () => {
  // A -C target that no longer exists makes git exit non-zero: the message names the git
  // command and its outcome, never an interpreter exception repr (the C101 R5 neutralization).
  const root = git_repo();
  fs.rmSync(root, { recursive: true, force: true });
  assert.throws(() => changedFiles(data, root), (error) => {
    return error instanceof ScopeError && /exited with status/.test(error.message);
  });
});

test("run_checks gives one finding per command, in declaration order", () => {
  const checks = [
    makeCheck(data, "lint", ["ruff", "check", "{files}"]),
    makeCheck(data, "noargs", ["true"]),
  ];
  /** @type {{argv: string[], options: {cwd: string}} | undefined} */
  let seen;
  const runner = (/** @type {string[]} */ argv, /** @type {{cwd: string}} */ options) => {
    seen = { argv, options };
    return { returncode: 0, error: undefined };
  };
  const findings = runChecks(data, "/proj", checks, ["a.py"], runner);
  assert.deepEqual(findings.map((f) => [f.severity, f.code, f.message]), [
    ["ok", "check.run", "`ruff check a.py` passed"],
    ["ok", "check.run", "`true` passed"],
  ]);
  assert.equal(findings[0].target, "[check].lint");
  assert.ok(seen !== undefined, "the runner was never called");
  assert.equal(seen.options.cwd, "/proj");
});

test("run_checks reports the exit status and the nothing-to-do and not-installed sides", () => {
  const checks = [makeCheck(data, "lint", ["ruff", "check", "{files}"])];
  const failing = runChecks(data, "/proj", checks, ["a.py"], () => ({ returncode: 1, error: undefined }));
  assert.deepEqual(failing[0], {
    severity: "error",
    code: "check.run",
    message: "`ruff check a.py` exited 1",
    target: "[check].lint",
    fix: "Fix what the command reported above, or change its configuration in the project",
  });
  const nothing = runChecks(data, "/proj", checks, [], () => ({ returncode: 0, error: undefined }));
  assert.deepEqual(nothing[0].message, "no changed file it checks");
  const notInstalled = runChecks(data, "/proj", checks, ["a.py"], () => ({
    returncode: null,
    error: { code: "ENOENT" },
  }));
  assert.equal(notInstalled[0].severity, "error");
  assert.equal(notInstalled[0].message, "`ruff` is not installed or not on PATH, so the check did not run");
});

test("a spawn failure that is not a missing command is not reported as one", () => {
  // ENOBUFS from an over-full capture, EACCES on a non-executable file: `subprocess.run` raises
  // these and the run dies naming them. Answering "not installed" sends the owner off looking
  // for a binary that is there.
  const checks = [makeCheck(data, "lint", ["ruff", "check", "{files}"])];
  for (const code of ["ENOBUFS", "EACCES"]) {
    assert.throws(
      () => runChecks(data, "/proj", checks, ["a.py"], () => ({ returncode: null, error: { code } })),
      (error) => (/** @type {{code?: string}} */ (error)).code === code,
    );
  }
  assert.throws(
    () => runChecks(data, "/proj", checks, ["a.py"], () => { throw Object.assign(new Error("boom"), { code: "EMISC" }); }),
    /boom/,
  );
});

test("a check killed by a signal reports the negative signal, not a null status", () => {
  // Python's `returncode` for a signalled child is `-N`; `spawnSync` splits the answer across
  // `status` (null) and `signal`, and a finding reading "exited null" says nothing about why.
  const checks = [makeCheck(data, "die", ["node", "-e", "process.kill(process.pid, 'SIGKILL')"])];
  const findings = runChecks(data, process.cwd(), checks, null);
  assert.equal(findings[0].severity, "error");
  assert.match(findings[0].message, /exited -9$/);
});

test("the check's own output reaches the terminal instead of being swallowed", () => {
  // The runner's contract is that the command reports and the finding only summarises, so the
  // output must pass the process through. A child process is the only place that can be observed:
  // written here, it would land in the test reporter's own stream.
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-check-io-"));
  const driver = posix.join(dir, "driver.mjs");
  fs.writeFileSync(
    driver,
    `import fs from "node:fs";
     import { makeCheck, runChecks } from ${JSON.stringify(new URL("./check_runner.mjs", import.meta.url).href)};
     const data = JSON.parse(fs.readFileSync(${JSON.stringify(fileURLToPath(new URL("../../common/check_runner.json", import.meta.url)))}, "utf-8"));
     const findings = runChecks(data, process.cwd(), [makeCheck(data, "noise", ["echo", "the-linter-spoke"])], null);
     process.stderr.write(findings[0].message + "\\n");`,
  );
  const result = spawnSync(process.execPath, [driver], { encoding: "utf-8" });
  assert.equal(result.stdout, "the-linter-spoke\n", "the command's stdout did not reach the terminal");
  assert.equal(result.stderr, "`echo the-linter-spoke` passed\n");
  fs.rmSync(dir, { recursive: true, force: true });
});

test("a date in the [check] table is a bad entry, not an empty spec", () => {
  // `TomlDate` is an object, and enumerating it yields nothing: read as a table it would report
  // a check with no command — a different problem, and one whose fix does not apply. Python's
  // twin says a non-mapping entry is a bad entry, and the message is the shared spec.
  const date = new Date(Date.UTC(1979, 4, 27));
  const { checks, problems } = readChecks(data, { when: date });
  assert.deepEqual(checks, []);
  assert.deepEqual(problems, ["[check].when must be a command string or a table with `command`"]);
});
