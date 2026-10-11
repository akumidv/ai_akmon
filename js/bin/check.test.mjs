/**
 * node:test for `js/bin/check.mjs` — `akmon check` end to end: the record, the table, the
 * findings it prints and the exit code, through a spawned `node js/bin/check.mjs` (the real
 * stdout, stderr and the children's own output) and through `main(argv)` (the exit code, with
 * the output captured). The engine's own cases are `common/check_runner.test.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { main } from "./check.mjs";

const CHECK = fileURLToPath(new URL("./check.mjs", import.meta.url));

/** A project with `AGENTS.md` and a record holding `record` (no record file when `null`). */
function project(/** @type {string | null} */ record) {
  const root = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-check-"));
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# project\n");
  if (record !== null) {
    fs.mkdirSync(posix.join(root, "_aitna"));
    fs.writeFileSync(posix.join(root, "_aitna", ".akmon.toml"), record);
  }
  return root;
}

/** The record of a project that declares `table` under `[check]`. */
function recordWith(/** @type {string} */ table) {
  return `mount = "package"\nakmon_version = "0.4.0"\n\n[check]\n${table}`;
}

/** Run `node check.mjs` with `args` in `cwd`, `AITNA_ROOT` unset. */
function run(/** @type {string[]} */ args, /** @type {string} */ cwd) {
  const env = { ...process.env };
  delete env.AITNA_ROOT;
  const result = spawnSync(process.execPath, [CHECK, ...args], { cwd, env, encoding: "utf8" });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

/** Run `main(args)` with `process.cwd()` untouched and the two streams captured. */
function inProcess(/** @type {string[]} */ args) {
  const out = /** @type {string[]} */ ([]);
  const err = /** @type {string[]} */ ([]);
  const write = { out: process.stdout.write, err: process.stderr.write };
  process.stdout.write = /** @type {typeof process.stdout.write} */ ((/** @type {string} */ text) => (out.push(text), true));
  process.stderr.write = /** @type {typeof process.stderr.write} */ ((/** @type {string} */ text) => (err.push(text), true));
  try {
    return { status: main(args), stdout: out.join(""), stderr: err.join("") };
  } finally {
    process.stdout.write = write.out;
    process.stderr.write = write.err;
  }
}

function git(/** @type {string} */ root, /** @type {string[]} */ ...args) {
  execFileSync("git", ["-C", root, ...args], { stdio: "ignore" });
}

test("a passing check prints its OK line and exits 0; the command's own output comes first", () => {
  const root = project(recordWith('lint = "echo checked {files}"\n'));
  const result = run(["--project-root", root], root);
  assert.deepEqual(result, {
    status: 0,
    stdout: "checked .\nOK check.run [check].lint: `echo checked .` passed → Keep it passing\n",
    stderr: "",
  });
  fs.rmSync(root, { recursive: true, force: true });
});

test("a failing check is an error finding naming the exit status, and exit 1", () => {
  const root = project(recordWith('lint = "false"\n'));
  const result = run([`--project-root=${root}`], root);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /^ERROR check\.run \[check\]\.lint: `false` exited 1 → /);
  assert.equal(result.stderr, "");
  fs.rmSync(root, { recursive: true, force: true });
});

test("a command that is not installed is its own finding, not a crash", () => {
  const root = project(recordWith('lint = "akmon-no-such-linter {files}"\n'));
  const result = run([], root);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /^ERROR check\.run \[check\]\.lint: `akmon-no-such-linter` is not installed or not on PATH, so the check did not run → /);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a project that declares no checks gets the warning and exit 0", () => {
  for (const record of [null, 'mount = "package"\n']) {
    const root = project(record);
    const result = run([], root);
    assert.equal(result.status, 0);
    assert.equal(
      result.stdout,
      "WARN check.config .akmon.toml [check]: declares no checks, so nothing ran → " +
        "Name the project's checks under [check], or run akmon init to set them up\n",
    );
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("an unreadable record is the one check.config finding and exit 1", () => {
  const root = project("mount = \n[check\n");
  const result = run([], root);
  assert.equal(result.status, 1);
  const lines = result.stdout.split("\n");
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^ERROR check\.config \.akmon\.toml \[check\]: \.akmon\.toml cannot be read as TOML: parse failed at line \d+, column \d+: /);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a malformed entry is reported and skipped; the good one still runs", () => {
  const root = project(recordWith('good = "true"\nnumber = 42\nunknown = { command = "true", extra = 1 }\n'));
  const result = run([], root);
  assert.equal(result.status, 1);
  const lines = result.stdout.trimEnd().split("\n");
  assert.equal(lines.length, 3);
  assert.match(lines[0], /^ERROR check\.config \.akmon\.toml \[check\]: \[check\]\.number must be a command string/);
  assert.match(lines[1], /^ERROR check\.config \.akmon\.toml \[check\]: \[check\]\.unknown has an unknown key 'extra'/);
  assert.match(lines[2], /^OK check\.run \[check\]\.good: `true` passed/);
  fs.rmSync(root, { recursive: true, force: true });
});

test("a date where a command belongs is a malformed entry, not a quiet no-op", () => {
  const root = project(recordWith("when = 2026-10-11\n"));
  const result = run([], root);
  assert.equal(result.status, 1);
  assert.match(result.stdout, /^ERROR check\.config \.akmon\.toml \[check\]: \[check\]\.when must be a command string/);
  fs.rmSync(root, { recursive: true, force: true });
});

test("--changed checks only what differs from HEAD, and skips a check with nothing to look at", () => {
  const root = project(recordWith('lint = { command = "echo {files}", files = ["*.py"] }\n'));
  git(root, "init", "-b", "main");
  git(root, "config", "user.name", "Test");
  git(root, "config", "user.email", "test@example.com");
  fs.writeFileSync(posix.join(root, "a.py"), "x = 1\n");
  git(root, "add", "-A");
  git(root, "commit", "-m", "base");
  const skipped = run(["--changed"], root);
  assert.equal(skipped.status, 0);
  assert.match(skipped.stdout, /^OK check\.run \[check\]\.lint: /);
  assert.doesNotMatch(skipped.stdout, /^a\.py/m);
  fs.writeFileSync(posix.join(root, "a.py"), "x = 2\n");
  const ran = run(["--changed"], root);
  assert.equal(ran.status, 0);
  assert.equal(ran.stdout, "a.py\nOK check.run [check].lint: `echo a.py` passed → Keep it passing\n");
  fs.rmSync(root, { recursive: true, force: true });
});

test("--changed outside a git repository is a check.scope finding and exit 1", () => {
  const root = project(recordWith('lint = "true"\n'));
  const result = run(["--changed"], root);
  assert.equal(result.status, 1);
  assert.match(
    result.stdout,
    /^ERROR check\.scope: cannot list the files changed against HEAD: `git diff --name-only HEAD --` exited with status \d+ → Run it inside a git work tree\n$/,
  );
  fs.rmSync(root, { recursive: true, force: true });
});

test("without --project-root, the root is found by walking up from the cwd", () => {
  const root = project(recordWith('lint = "true"\n'));
  const nested = posix.join(root, "src", "deep");
  fs.mkdirSync(nested, { recursive: true });
  const result = run([], nested);
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
  assert.match(result.stdout, /^OK check\.run \[check\]\.lint: `true` passed/);
  fs.rmSync(root, { recursive: true, force: true });
});

test("outside any project the fallback root comes with the notice on stderr", () => {
  const dir = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-check-bare-"));
  const result = run([], fs.realpathSync(dir));
  assert.equal(result.status, 0);
  assert.match(result.stderr, new RegExp(`^\\[akmon\\] no project root at or above ${fs.realpathSync(dir)}: expected AGENTS\\.md `));
  assert.ok(result.stderr.endsWith("pass --project-root to name the root instead.\n"));
  assert.match(result.stdout, /^WARN check\.config /);
  fs.rmSync(dir, { recursive: true, force: true });
});

test("a usage error is one line on stderr and exit 2; nothing runs", () => {
  const root = project(recordWith('lint = "echo ran"\n'));
  for (const [args, message] of [
    [["--bogus"], "Unknown option '--bogus'"],
    [["extra"], "Unexpected argument 'extra'. This command does not take positional arguments"],
    [["--project-root"], "Option '--project-root <value>' argument missing"],
    [["--changed=yes"], "Option '--changed' does not take an argument"],
  ]) {
    const result = run(/** @type {string[]} */ (args), root);
    assert.deepEqual(result, { status: 2, stdout: "", stderr: `akmon check: error: ${message}\n` }, String(args));
  }
  fs.rmSync(root, { recursive: true, force: true });
});

test("-h and --help print the usage and exit 0 without reading any project", () => {
  for (const flag of ["-h", "--help"]) {
    const result = run([flag], os.tmpdir());
    assert.equal(result.status, 0);
    assert.match(result.stdout, /^usage: akmon check \[-h\] \[--project-root PROJECT_ROOT\] \[--changed\]\n/);
    assert.equal(result.stderr, "");
  }
});

test("main returns the exit code and writes through process.stdout, process.stderr", () => {
  const root = project(recordWith('lint = "true"\nbroken = 1\n'));
  const failing = inProcess(["--project-root", root]);
  assert.equal(failing.status, 1);
  assert.match(failing.stdout, /^ERROR check\.config /);
  assert.match(failing.stdout, /OK check\.run \[check\]\.lint: `true` passed/);
  assert.equal(failing.stderr, "");
  assert.deepEqual(inProcess(["--nope"]), { status: 2, stdout: "", stderr: "akmon check: error: Unknown option '--nope'\n" });
  fs.rmSync(root, { recursive: true, force: true });
});
