import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import { readEvents } from "./record-events.mjs";
import {
  appendMark,
  checkName,
  clearState,
  eventsPath,
  fileSink,
  nextName,
  readState,
  recordingDir,
  recordingNames,
  summaryOf,
  writeState,
} from "./record-store.mjs";
import { BrowserError } from "./settings.mjs";

/** @returns {{dir: string, dispose: () => void}} */
function scratch() {
  const dir = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-record-")));
  return { dir, dispose: () => fs.rmSync(dir, { recursive: true, force: true }) };
}

/** @type {import("./record-store.mjs").RecordingState} */
const STATE = {
  name: "rec-1",
  pid: 4242,
  startedAtMs: 1_000_000,
  options: { page: null, allPages: false, bodies: false, maxBody: 65_536 },
  side: "here",
  redact: ["password", "ssn"],
};

test("the default name is rec-<n>, one past the highest in use, and a name with a path in it is refused", () => {
  assert.equal(nextName([]), "rec-1");
  assert.equal(nextName(["rec-1", "rec-7", "login-bug"]), "rec-8");
  for (const bad of ["../x", "a/b", "", ".hidden", "x y", "a".repeat(65)]) {
    assert.throws(() => checkName(bad), BrowserError, bad);
  }
  checkName("checkout-bug_2.run");
  const { dir, dispose } = scratch();
  try {
    assert.throws(() => recordingDir(dir, ".."), BrowserError);
    assert.equal(recordingDir(dir, "rec-1"), `${dir}/recordings/rec-1`);
  } finally {
    dispose();
  }
});

test("the state file lifecycle: none, written, read back, cleared", () => {
  const { dir, dispose } = scratch();
  try {
    assert.equal(readState(dir), null);
    writeState(dir, STATE);
    assert.deepEqual(readState(dir), STATE);
    clearState(dir);
    assert.equal(readState(dir), null);
    clearState(dir);
    fs.writeFileSync(posix.join(dir, "recording.json"), "{broken");
    assert.equal(readState(dir), null);
  } finally {
    dispose();
  }
});

test("recordings are the folders under recordings/, by name", () => {
  const { dir, dispose } = scratch();
  try {
    assert.deepEqual(recordingNames(dir), []);
    for (const name of ["rec-2", "rec-1", "x"]) {
      fs.mkdirSync(recordingDir(dir, name), { recursive: true });
    }
    fs.writeFileSync(posix.join(dir, "recordings", "stray.txt"), "");
    assert.deepEqual(recordingNames(dir), ["rec-1", "rec-2", "x"]);
  } finally {
    dispose();
  }
});

test("the sink stamps t from one clock that never goes back, and an event that began earlier says how much", () => {
  const { dir, dispose } = scratch();
  try {
    const file = posix.join(dir, "events.jsonl");
    const clock = [1_000_100, 1_000_500, 1_000_300, 1_000_900];
    const sink = fileSink({ file, startedAtMs: 1_000_000, now: () => clock.shift() ?? 0 });
    sink.append({ kind: "navigation", page: "p1" });
    sink.append({ kind: "click", page: "p1" });
    sink.append({ kind: "console", page: "p1" });
    sink.append({ kind: "net", page: "p1" }, 250);
    const times = readEvents(fs.readFileSync(file, "utf8")).events.map((event) => event.t);
    assert.deepEqual(times, [100, 500, 500, 650]);
  } finally {
    dispose();
  }
});

test("a mark takes t from the recorder's start time in the state, the same clock as the sink, and is numbered", () => {
  const { dir, dispose } = scratch();
  try {
    fs.mkdirSync(recordingDir(dir, "rec-1"), { recursive: true });
    const folder = recordingDir(dir, "rec-1");
    const sink = fileSink({ file: eventsPath(folder), startedAtMs: STATE.startedAtMs, now: () => 1_002_000 });
    sink.append({ kind: "click", page: "p1" });
    const first = appendMark({ dir: folder, state: STATE, now: () => 1_004_250 }, "checkout fails now");
    const second = appendMark({ dir: folder, state: STATE, now: () => 1_009_000 }, "again, password=hunter2");
    assert.deepEqual(first, { t: 4250, number: 1 });
    assert.equal(second.number, 2);
    const marks = readEvents(fs.readFileSync(eventsPath(folder), "utf8")).events.filter(
      (event) => event.kind === "mark",
    );
    assert.deepEqual(
      marks.map((mark) => [mark.t, mark["note"]]),
      [
        [4250, "checkout fails now"],
        [9000, "again, password=[redacted]"],
      ],
    );
  } finally {
    dispose();
  }
});

test("the summary counts events by kind, marks, failed requests, exceptions and the duration", () => {
  const lines = [
    { t: 0, kind: "start" },
    { t: 10, kind: "click" },
    { t: 20, kind: "net", status: 200, failure: null },
    { t: 30, kind: "net", status: 502, failure: null },
    { t: 40, kind: "net", status: null, failure: "net::ERR_FAILED" },
    { t: 50, kind: "exception" },
    { t: 60, kind: "mark" },
  ];
  const summary = summaryOf(`${lines.map((line) => JSON.stringify(line)).join("\n")}\n{"t":`);
  assert.equal(summary.events, 7);
  assert.equal(summary.failedRequests, 2);
  assert.equal(summary.exceptions, 1);
  assert.equal(summary.marks, 1);
  assert.equal(summary.durationMs, 60);
  assert.equal(summary.skipped, 1);
  assert.equal(summary.byKind["net"], 3);
});
