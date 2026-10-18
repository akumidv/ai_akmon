/**
 * node:test for `js/tools/tasks/archive.mjs` — the entry parsing, the status flip, the sweep and
 * the exit codes. The byte-level spec is the `tools/archive-*` scenarios of
 * `meta/conformance/scenarios`, run by `runner.py --impl node --area tools`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { insertIntoArchive, main, malformedEntries, markDone, parseEntries, splitDone } from "./archive.mjs";

const DATA = {
  done_status: "done",
  done_header: "## Done",
  archive_no_section: "archive has no '{{header}}' section",
  error_no_archive_file: "error: no archive file: {{path}}",
  error_generic: "error: {{exc}}",
  archived: "archived {{count}}: {{ids}}",
  warning_missing_status: "warning: task entry missing a status field: {{bullet}}",
  error_no_such_entry: "error: no such entry: {{ids}}",
  no_done_entries: "no done entries to archive",
  would_archive_entry: "would archive {{count}} done entry: {{ids}}",
  would_archive_entries: "would archive {{count}} done entries: {{ids}}",
  reapply_hint: "re-run with --apply to move them",
};

const TASKS = "# Tasks\n\n- C1 · one · done · e\n  continued\n- C2 · two · active · e\n\n- C3 · three · done · e\n";

/**
 * Run `main` with the process streams captured.
 * @param {string[]} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function run(argv) {
  let stdout = "";
  let stderr = "";
  const out = process.stdout.write;
  const err = process.stderr.write;
  process.stdout.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stdout += text), true)
  );
  process.stderr.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stderr += text), true)
  );
  try {
    return { code: main(argv), stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
  }
}

/**
 * A scratch directory holding TASKS.md and TASKS_ARCHIVE.md.
 * @param {string} tasks
 * @param {string | null} [archive]
 * @returns {string} the TASKS.md path
 */
function backlog(tasks, archive = "# Archive\n\n## Done\n\n- T1 · old · done · e\n") {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "archive-test-"));
  fs.writeFileSync(path.join(dir, "TASKS.md"), tasks);
  if (archive !== null) {
    fs.writeFileSync(path.join(dir, "TASKS_ARCHIVE.md"), archive);
  }
  return path.join(dir, "TASKS.md");
}

test("parseEntries groups a bullet with its indented continuation", () => {
  assert.deepEqual(parseEntries(TASKS.split("\n")), [
    [2, 4],
    [4, 5],
    [6, 7],
  ]);
});

test("markDone flips only the status cell and reports unknown ids", () => {
  const { text, missing } = markDone(DATA, "- C2 · two ·  active  · e\n", ["C2", "C2", "C9"]);
  assert.equal(text, "- C2 · two ·  done  · e\n");
  assert.deepEqual(missing, ["C9"]);
});

test("splitDone removes done blocks and collapses the blank line left behind", () => {
  const { remaining, blocks, ids } = splitDone(DATA, TASKS);
  assert.deepEqual(ids, ["C1", "C3"]);
  assert.deepEqual(blocks[0], ["- C1 · one · done · e", "  continued"]);
  assert.equal(remaining, "# Tasks\n\n- C2 · two · active · e\n");
});

test("insertIntoArchive puts blocks at the top of the Done section, or fails without it", () => {
  assert.equal(
    insertIntoArchive(DATA, "# A\n\n## Done\n\n- T1 · x · done · e\n", [["- C1 · a · done · e"]]),
    "# A\n\n## Done\n\n- C1 · a · done · e\n- T1 · x · done · e\n",
  );
  assert.throws(() => insertIntoArchive(DATA, "# A\n", []), {
    name: "ValueError",
    message: "archive has no '## Done' section",
  });
});

test("malformedEntries flags an id-like bullet with no status field only", () => {
  assert.deepEqual(malformedEntries(["- C5 · no status", "- prose bullet", "- C6 · t · done · e"]), [
    "- C5 · no status",
  ]);
});

test("main: dry-run lists the entries and exits 1 without writing", () => {
  const tasks = backlog(TASKS);
  const result = run(["--tasks", tasks]);
  assert.equal(result.code, 1);
  assert.equal(result.stdout, "would archive 2 done entries: C1, C3\nre-run with --apply to move them\n");
  assert.equal(fs.readFileSync(tasks, "utf8"), TASKS);
});

test("main: --apply moves the entries, newest first", () => {
  const tasks = backlog(TASKS);
  const result = run(["--tasks", tasks, "--apply"]);
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "archived 2: C1, C3\n");
  assert.equal(fs.readFileSync(tasks, "utf8"), "# Tasks\n\n- C2 · two · active · e\n");
  assert.equal(
    fs.readFileSync(path.join(path.dirname(tasks), "TASKS_ARCHIVE.md"), "utf8"),
    "# Archive\n\n## Done\n\n- C1 · one · done · e\n  continued\n- C3 · three · done · e\n- T1 · old · done · e\n",
  );
});

test("main: --done takes several ids, in both the nargs and the repeated form", () => {
  for (const done of [
    ["--done", "C2", "C4"],
    ["--done", "C2", "--done", "C4"],
  ]) {
    const tasks = backlog("- C2 · two · active · e\n- C4 · four · active · e\n");
    const result = run(["--tasks", tasks, ...done, "--apply"]);
    assert.equal(result.stdout, "archived 2: C2, C4\n");
    assert.equal(result.code, 0);
  }
});

test("main: an unknown --done id fails closed", () => {
  const tasks = backlog(TASKS);
  const result = run(["--tasks", tasks, "--done", "C999", "--apply"]);
  assert.equal(result.code, 2);
  assert.equal(result.stderr, "error: no such entry: C999\n");
  assert.equal(fs.readFileSync(tasks, "utf8"), TASKS);
});

test("main: nothing done is exit 0; a missing file or archive is exit 2", () => {
  assert.deepEqual(run(["--tasks", backlog("- C2 · two · active · e\n")]), {
    code: 0,
    stdout: "no done entries to archive\n",
    stderr: "",
  });
  assert.equal(run(["--tasks", "/nonexistent/TASKS.md"]).stderr, "error: no such file: /nonexistent/TASKS.md\n");
  const tasks = backlog(TASKS, null);
  const result = run(["--tasks", tasks, "--apply"]);
  assert.equal(result.code, 2);
  assert.equal(result.stderr, `error: no archive file: ${path.join(path.dirname(tasks), "TASKS_ARCHIVE.md")}\n`);
});

test("main: a bullet missing its status is warned about on stderr", () => {
  const result = run(["--tasks", backlog("- C5 · no status\n")]);
  assert.equal(result.stderr, "warning: task entry missing a status field: - C5 · no status\n");
  assert.equal(result.code, 0);
});

test("main: usage errors are one line and exit 2; -h prints the usage", () => {
  assert.deepEqual(run([]), {
    code: 2,
    stdout: "",
    stderr: "archive.mjs: error: the following arguments are required: --tasks\n",
  });
  assert.equal(run(["--tasks", "x", "stray"]).stderr, "archive.mjs: error: unrecognized arguments: stray\n");
  assert.match(run(["--bogus"]).stderr, /^archive\.mjs: error: Unknown option '--bogus'/);
  const help = run(["-h"]);
  assert.equal(help.code, 0);
  assert.match(help.stdout, /^usage: archive\.mjs /);
});
