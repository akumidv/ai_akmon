/**
 * node:test for `js/common/report_path.mjs` — the task-and-ordinal report names (C114), twin of
 * `meta/tests/test_report_path.py`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { createReport, nextReportPath, reportPrefix, safeName, taskError } from "./report_path.mjs";

const scratch = () => fs.mkdtempSync(path.join(os.tmpdir(), "report-path-test-"));

test("safeName and reportPrefix sanitise like a gate name and keep the task's case", () => {
  assert.equal(safeName("a b/ü"), "a-b-ü");
  assert.equal(safeName("///"), "");
  assert.equal(reportPrefix("stats", null), "stats");
  assert.equal(reportPrefix("stats", "C7"), "C7-stats");
  assert.equal(reportPrefix("stats", "c7/x"), "c7-x-stats");
});

test("a task with no usable characters is an error, not no task (owner decision, C114)", () => {
  for (const task of ["///", "", "..."]) {
    const message = `--task '${task}' has no usable characters (letters, digits, '_' or '-')`;
    assert.equal(taskError(task), message);
    assert.throws(() => reportPrefix("stats", task), { message });
  }
  assert.equal(taskError(null), null);
  assert.equal(taskError(undefined), null);
  assert.equal(taskError("C7"), null);
});

test("no task and an empty or missing directory: <base>-1.md", () => {
  const dir = scratch();
  assert.equal(nextReportPath(path.join(dir, "absent"), "coverage"), path.join(dir, "absent", "coverage-1.md"));
  const made = createReport(path.join(dir, "absent"), "coverage", "x\n");
  assert.equal(made, path.join(dir, "absent", "coverage-1.md"));
  assert.equal(fs.readFileSync(made, "utf8"), "x\n");
});

test("with a task: one past the largest ordinal of exactly that prefix", () => {
  const dir = scratch();
  for (const name of ["C7-stats-1.md", "C7-stats-x.md", "stats-9.md", "C7-stats-full-5.md", "C7-stats-3.md.bak"]) {
    fs.writeFileSync(path.join(dir, name), "");
  }
  const prefix = reportPrefix("stats", "C7");
  assert.equal(nextReportPath(dir, prefix), path.join(dir, "C7-stats-2.md"));
  assert.equal(createReport(dir, prefix, "y"), path.join(dir, "C7-stats-2.md"));
});

test("non-matching neighbours are ignored: design-align does not see design-align-full-3.md", () => {
  const dir = scratch();
  fs.writeFileSync(path.join(dir, "design-align-full-3.md"), "");
  assert.equal(nextReportPath(dir, "design-align"), path.join(dir, "design-align-1.md"));
  assert.equal(nextReportPath(dir, "design-align-full"), path.join(dir, "design-align-full-4.md"));
});

test("a name taken between the scan and the create moves to the next ordinal, never overwrites", () => {
  const dir = scratch();
  fs.writeFileSync(path.join(dir, "stats-1.md"), "kept");
  fs.writeFileSync(path.join(dir, "stats-2.md"), "kept");
  assert.equal(createReport(dir, "stats", "new", 1), path.join(dir, "stats-3.md"));
  assert.equal(fs.readFileSync(path.join(dir, "stats-1.md"), "utf8"), "kept");
  assert.equal(fs.readFileSync(path.join(dir, "stats-3.md"), "utf8"), "new");
});
