/**
 * node:test for `js/common/learning.mjs` — the twin of the run-record behaviour of
 * `common/learning.py` (C177, ADR 0026 D07). The state text and the reminder literals are the
 * Python's: a drift in either twin shows as a failing literal.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  Due,
  LearningState,
  Thresholds,
  daysSince,
  formatUtc,
  markRun,
  parseUtc,
  readData,
  readState,
  readThresholds,
  recordAndRemind,
  StateLockedError,
  sessionEvent,
  recordSession,
  reminderDue,
  reminderTexts,
  sessionReminder,
  statePath,
  writeState,
} from "./learning.mjs";

const DATA = readData();
const DEFAULTS = new Thresholds(10, 7);
/** @param {string} text */
const at = (text) => parseUtc(text);

/** A scratch project: `AGENTS.md`, an `_aitna` layer and (optionally) its record file text. */
function project(record = "") {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-learning-")));
  fs.mkdirSync(path.join(root, "_aitna"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# a\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), record);
  return { root, state: path.join(root, "_aitna", "local", "learning.json") };
}

/** The names left beside the state file. */
function leftovers(/** @type {string} */ state) {
  return fs.readdirSync(path.dirname(state)).filter((name) => name !== path.basename(state));
}

test("the data file carries the defaults and the state location", () => {
  assert.equal(DATA.state_rel, "local/learning.json");
  assert.equal(DATA.reminder_sessions, 10);
  assert.equal(DATA.reminder_days, 7);
  assert.deepEqual(DATA.skip_sources, ["compact"]);
});

test("formatUtc and parseUtc round-trip whole seconds", () => {
  assert.equal(formatUtc(new Date(Date.UTC(2026, 9, 28, 9, 30, 0, 999))), "2026-10-28T09:30:00Z");
  assert.equal(parseUtc("2026-10-28T09:30:00Z").getTime(), Date.UTC(2026, 9, 28, 9, 30, 0));
  assert.equal(formatUtc(parseUtc("0001-01-01T00:00:00Z")), "0001-01-01T00:00:00Z");
  assert.equal(formatUtc(parseUtc("2024-02-29T23:59:59Z")), "2024-02-29T23:59:59Z");
});

test("parseUtc refuses another shape and every impossible calendar moment, as strptime does", () => {
  for (const text of [
    "2026-10-28 09:30:00Z",
    "2026-10-28T09:30:00",
    "2026-10-28T09:30:00Z\n",
    "٢٠٢٦-10-28T09:30:00Z",
    "2026-02-30T00:00:00Z",
    "2023-02-29T00:00:00Z",
    "0000-01-01T00:00:00Z",
    "2026-13-01T00:00:00Z",
    "2026-00-10T00:00:00Z",
    "2026-01-01T24:00:00Z",
    "2026-01-01T00:60:00Z",
    "2026-01-01T00:00:60Z",
  ]) {
    assert.throws(() => parseUtc(text), { name: "ValueError" }, text);
  }
});

test("the state file lives in the local layer of the dev-layer root", () => {
  assert.equal(statePath("/p", DATA), "/p/_aitna/local/learning.json");
});

test("a missing, corrupt or ill-typed state file is the empty state", () => {
  const { state } = project();
  assert.deepEqual(readState(state), new LearningState());
  fs.mkdirSync(path.dirname(state), { recursive: true });
  for (const text of [
    "",
    "not json",
    "[]",
    "null",
    '{"sessions": "a"}',
    '{"sessions": [1]}',
    '{"sessions": [""]}',
    '{"sessions": ["a"], "last_run": 5}',
    '{"sessions": ["a"], "last_run": "yesterday"}',
    '{"sessions": ["a"], "since": "2026-02-30T00:00:00Z"}',
    '{"last_run": null, "since": null}',
  ]) {
    fs.writeFileSync(state, text);
    assert.deepEqual(readState(state), new LearningState(), text);
  }
  fs.writeFileSync(state, Buffer.from([0xff, 0xfe]));
  assert.deepEqual(readState(state), new LearningState());
  fs.rmSync(state);
  fs.mkdirSync(state);
  assert.deepEqual(readState(state), new LearningState(), "a directory in its place is unreadable, not fatal");
});

test("a valid state is read back, duplicate session ids dropped in first-seen order", () => {
  const { state } = project();
  fs.mkdirSync(path.dirname(state), { recursive: true });
  fs.writeFileSync(state, '{"last_run": "2026-10-01T00:00:00Z", "since": null, "sessions": ["b", "a", "b", "c", "a"]}');
  const read = readState(state);
  assert.equal(read.lastRun, "2026-10-01T00:00:00Z");
  assert.equal(read.since, null);
  assert.deepEqual([...read.sessions], ["b", "a", "c"]);
});

test("writeState writes json.dumps(indent=2) text, atomically, leaving no temp file", () => {
  const { state } = project();
  writeState(new LearningState(null, "2026-10-28T09:30:00Z", ["s1", "é\u{1F600}"]), state);
  assert.equal(
    fs.readFileSync(state, "utf8"),
    '{\n  "last_run": null,\n  "since": "2026-10-28T09:30:00Z",\n  "sessions": [\n    "s1",\n    "\\u00e9\\ud83d\\ude00"\n  ]\n}\n',
  );
  assert.deepEqual(leftovers(state), []);
  writeState(new LearningState("2026-10-29T00:00:00Z", null, []), state);
  assert.equal(
    fs.readFileSync(state, "utf8"),
    '{\n  "last_run": "2026-10-29T00:00:00Z",\n  "since": null,\n  "sessions": []\n}\n',
  );
  assert.deepEqual(leftovers(state), [], "the second write replaced the file and left no temp file");
  assert.equal(fs.statSync(state).mode & 0o777, 0o600);
});

test("a failed write is raised and leaves no temp file behind", () => {
  const { state } = project();
  fs.mkdirSync(state, { recursive: true }); // a directory where the file belongs: the rename must fail
  assert.throws(
    () => writeState(new LearningState(null, null, ["new"]), state),
    (error) => typeof (/** @type {{errno?: unknown}} */ (error).errno) === "number",
  );
  assert.deepEqual(leftovers(state), []);
});

test("recordSession starts the count, appends ids and ignores a known one", () => {
  const { state } = project();
  const first = recordSession(state, "s1", at("2026-10-28T09:00:00Z"), DATA);
  assert.deepEqual([first.lastRun, first.since, [...first.sessions]], [null, "2026-10-28T09:00:00Z", ["s1"]]);
  const second = recordSession(state, "s2", at("2026-10-29T09:00:00Z"), DATA);
  assert.deepEqual([second.since, [...second.sessions]], ["2026-10-28T09:00:00Z", ["s1", "s2"]]);
  const before = fs.readFileSync(state, "utf8");
  const again = recordSession(state, "s1", at("2026-10-30T09:00:00Z"), DATA);
  assert.deepEqual([...again.sessions], ["s1", "s2"]);
  assert.equal(fs.readFileSync(state, "utf8"), before);
});

test(
  "a known session id writes nothing, even where the directory cannot be written",
  { skip: process.getuid?.() === 0 },
  () => {
    const { state } = project();
    recordSession(state, "s1", at("2026-10-28T09:00:00Z"), DATA);
    fs.chmodSync(path.dirname(state), 0o500);
    try {
      assert.deepEqual([...recordSession(state, "s1", at("2026-10-28T10:00:00Z"), DATA).sessions], ["s1"]);
    } finally {
      fs.chmodSync(path.dirname(state), 0o700);
    }
  },
);

test("markRun records the run, clears the count and the counting start", () => {
  const { state } = project();
  recordSession(state, "s1", at("2026-10-28T09:00:00Z"), DATA);
  const marked = markRun(state, at("2026-10-30T12:00:00Z"), DATA);
  assert.deepEqual([marked.lastRun, marked.since, [...marked.sessions]], ["2026-10-30T12:00:00Z", null, []]);
  assert.deepEqual(readState(state), marked);
  const next = recordSession(state, "s2", at("2026-10-31T00:00:00Z"), DATA);
  assert.deepEqual([next.lastRun, next.since, [...next.sessions]], ["2026-10-30T12:00:00Z", null, ["s2"]]);
});

test("daysSince counts whole days from the last run, else from the counting start", () => {
  const now = at("2026-10-28T12:00:00Z");
  assert.equal(daysSince(new LearningState(), now), null);
  assert.equal(daysSince(new LearningState("2026-10-21T12:00:00Z"), now), 7);
  assert.equal(daysSince(new LearningState("2026-10-21T12:00:01Z"), now), 6);
  assert.equal(daysSince(new LearningState(null, "2026-10-26T00:00:00Z"), now), 2);
  assert.equal(daysSince(new LearningState("2026-10-29T00:00:00Z"), now), 0, "a baseline in the future is zero days");
});

test("thresholds default to the shipped values", () => {
  const { root } = project();
  assert.deepEqual(readThresholds(root, DATA), DEFAULTS);
  fs.rmSync(path.join(root, "_aitna", ".akmon.toml"));
  assert.deepEqual(readThresholds(root, DATA), DEFAULTS);
});

test("the [learning] section of .akmon.toml overrides the defaults, as numbers or strings", () => {
  assert.deepEqual(
    readThresholds(project('[learning]\nreminder_sessions = 3\nreminder_days = "2"\n').root, DATA),
    new Thresholds(3, 2),
  );
  assert.deepEqual(readThresholds(project('[learning]\nreminder_days = " 30 "\n').root, DATA), new Thresholds(10, 30));
});

test("a value that is not a positive ASCII integer falls back to its default", () => {
  for (const value of ["0", "-3", "2.5", '"abc"', '""', "true", "[1]", '"٣"', '"+4"', '"1_0"']) {
    const { root } = project(`[learning]\nreminder_sessions = ${value}\nreminder_days = ${value}\n`);
    assert.deepEqual(readThresholds(root, DATA), DEFAULTS, value);
  }
  assert.deepEqual(readThresholds(project('learning = "x"\n').root, DATA), DEFAULTS, "a section that is not a table");
});

test("an integer past what a number holds keeps its digits", () => {
  const { root } = project("[learning]\nreminder_sessions = 123456789012345678901234567890\n");
  const thresholds = readThresholds(root, DATA);
  assert.equal(String(thresholds.reminderSessions), "123456789012345678901234567890");
  assert.equal(
    reminderDue(new LearningState(null, "2026-10-28T00:00:00Z", ["a", "b"]), thresholds, at("2026-10-28T00:00:00Z")),
    null,
  );
});

test("an integer text past Python's digit limit is its ValueError", () => {
  const { root } = project(`[learning]\nreminder_sessions = "${"9".repeat(4301)}"\n`);
  assert.throws(() => readThresholds(root, DATA), { name: "ValueError", message: /Exceeds the limit \(4300 digits\)/ });
});

test("no reminder is due before a session has passed, however many days have", () => {
  const now = at("2026-12-28T00:00:00Z");
  assert.equal(reminderDue(new LearningState("2026-01-01T00:00:00Z"), DEFAULTS, now), null);
  assert.equal(reminderDue(new LearningState(null, null, []), DEFAULTS, now), null);
});

test("a reminder is due at the session threshold or at the day threshold", () => {
  const now = at("2026-10-28T00:00:00Z");
  const ids = Array.from({ length: 10 }, (_, index) => `s${index}`);
  assert.deepEqual(
    reminderDue(new LearningState("2026-10-27T00:00:00Z", null, ids), DEFAULTS, now),
    new Due(10, 1, true),
  );
  assert.equal(reminderDue(new LearningState("2026-10-27T00:00:00Z", null, ids.slice(1)), DEFAULTS, now), null);
  assert.deepEqual(
    reminderDue(new LearningState("2026-10-21T00:00:00Z", null, ["a"]), DEFAULTS, now),
    new Due(1, 7, true),
  );
  assert.equal(reminderDue(new LearningState("2026-10-21T00:00:01Z", null, ["a"]), DEFAULTS, now), null);
  assert.deepEqual(
    reminderDue(new LearningState(null, "2026-10-14T00:00:00Z", ["a"]), DEFAULTS, now),
    new Due(1, 14, false),
  );
});

test("the reminder texts name the counts, singular for one", () => {
  const [forModel, forOwner] = reminderTexts(new Due(1, 1, true), DATA);
  assert.equal(
    forOwner,
    "[akmon] learning: 1 session and 1 day since the last learning run — run the `learning` skill to review them.",
  );
  assert.match(
    forModel,
    /^\[akmon\] Learning reminder: 1 session and 1 day have passed since the last learning run\. /,
  );
  const [, started] = reminderTexts(new Due(12, 0, false), DATA);
  assert.equal(
    started,
    "[akmon] learning: 12 sessions and 0 days since akmon began counting (no learning run is recorded yet) — run the `learning` skill to review them.",
  );
});

test("a compaction is silent; a due reminder on any other source speaks", () => {
  const state = new LearningState("2026-10-01T00:00:00Z", null, ["a"]);
  const now = at("2026-10-28T00:00:00Z");
  assert.equal(sessionReminder(state, "compact", DEFAULTS, now, DATA), null);
  assert.notEqual(sessionReminder(state, "startup", DEFAULTS, now, DATA), null);
  assert.notEqual(sessionReminder(state, null, DEFAULTS, now, DATA), null);
});

test("a session counts only once it has passed; an unidentified session is not recorded", () => {
  const { state } = project();
  const now = at("2026-10-28T00:00:00Z");
  const few = new Thresholds(2, 7);
  /** @param {string | null} sessionId @param {string} source @param {boolean} [attended] */
  const remind = (sessionId, source, attended = true) =>
    recordAndRemind(state, { sessionId, source, attended }, few, now, DATA);
  assert.equal(remind("s1", "startup"), null);
  assert.equal(remind("s2", "startup"), null, "only s1 has passed");
  const reminder = remind("s3", "startup");
  assert.match(reminder?.[1] ?? "", /^\[akmon\] learning: 2 sessions and 0 days since akmon began counting/);
  assert.equal(remind(null, "startup")?.length, 2, "reads, and still reminds");
  assert.equal(remind("", "startup")?.length, 2);
  assert.deepEqual([...readState(state).sessions], ["s1", "s2", "s3"]);
  assert.equal(remind("s4", "compact"), null, "recorded, but silent");
  assert.equal(remind("s5", "startup", false), null, "unattended: recorded, never reminded");
  assert.deepEqual([...readState(state).sessions], ["s1", "s2", "s3", "s4", "s5"]);
});

test("after a run the days threshold waits for a session that has passed", () => {
  const { state } = project();
  markRun(state, at("2026-10-28T09:30:00Z"), DATA);
  const later = at("2026-11-11T09:30:00Z");
  const thresholds = new Thresholds(10, 7);
  const event = (/** @type {string} */ sessionId) => ({ sessionId, source: "startup", attended: true });
  assert.equal(recordAndRemind(state, event("s1"), thresholds, later, DATA), null, "14 days, no session passed");
  const reminder = recordAndRemind(state, event("s2"), thresholds, later, DATA);
  assert.match(reminder?.[1] ?? "", /^\[akmon\] learning: 1 session and 14 days since the last learning run/);
});

test("sessionEvent reads the environment it is handed: a second opinion is no event, unattended is flagged", () => {
  const attended = DATA.attended_variable;
  const marker = DATA.second_opinion_variable;
  assert.deepEqual(sessionEvent("s", "startup", {}, DATA), { sessionId: "s", source: "startup", attended: true });
  assert.equal(sessionEvent("s", "startup", { [attended]: "1" }, DATA)?.attended, true);
  assert.equal(sessionEvent("s", "startup", { [attended]: "0" }, DATA)?.attended, false);
  assert.equal(sessionEvent("s", "startup", { [marker]: "1" }, DATA), null);
});

test("a held lock makes the hook step give up silently and mark fail; a stale lock is taken over", () => {
  const { state } = project();
  fs.mkdirSync(path.dirname(state), { recursive: true });
  const lock = `${state}.lock`;
  fs.writeFileSync(lock, "1\n");
  const event = { sessionId: "s1", source: "startup", attended: true };
  assert.equal(recordAndRemind(state, event, new Thresholds(1, 1), at("2026-10-28T00:00:00Z"), DATA), null);
  assert.equal(fs.existsSync(state), false);
  assert.throws(() => markRun(state, at("2026-10-28T00:00:00Z"), DATA), StateLockedError);
  assert.equal(fs.existsSync(lock), true, "a lock we did not take is never ours to remove");
  const old = new Date(Date.now() - 86_400_000);
  fs.utimesSync(lock, old, old);
  assert.deepEqual([...recordSession(state, "s1", at("2026-10-28T00:00:00Z"), DATA).sessions], ["s1"]);
  assert.equal(fs.existsSync(lock), false);
  assert.deepEqual(leftovers(state), []);
});
