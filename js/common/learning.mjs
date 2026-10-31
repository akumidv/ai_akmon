/**
 * The learning agent's run record and its reminder — the JavaScript twin of `common/learning.py`
 * (C177, ADR 0026 D07; ADR 0020 D01). The Python module is the spec: the same answers, the same
 * texts, the same state file byte for byte.
 *
 * The learning agent reads the sessions of the project it serves, recorded since its last run.
 * This module keeps that record — `<dev root>/local/learning.json` in the project's local layer
 * (ADR 0022), gitignored — and decides when a session-start hook should remind the owner to run it.
 *
 * State is three fields: `last_run` (UTC ISO seconds, `null` before the first run), `since` (when
 * counting began: the first session recorded while no run exists) and `sessions` (the distinct
 * session ids seen since the last run). A missing or unreadable file is empty state, not an error —
 * the next write replaces it. Writes are atomic (temp file in the same directory, then rename). A
 * write that follows a read ({@link recordSession}, {@link markRun}) holds an exclusive lock file
 * beside the state (`learning.json.lock`, created with `O_EXCL`): a short bounded retry, a stale
 * lock past its timeout is taken over, and a lock that cannot be taken throws
 * {@link StateLockedError} — the hook gives up silently on it, `akmon learn mark` reports it.
 *
 * Everything that reads the world — the clock, the file, the thresholds in
 * `<dev root>/.akmon.toml` — is read at the entry point and passed down; the decision functions
 * take values. The texts and the thresholds' defaults are `common/learning.json`'s, shared by both
 * twins: {@link readData} reads it, and the hook bundle (`hooks/hook_data.mjs`) hands it to the
 * hooks as `data.learning`.
 *
 * Twin notes:
 * - a moment is a `Date` (millisecond resolution; the state file records whole seconds);
 * - a threshold is a `number`, or a `bigint` when the configured integer is past what a `number`
 *   holds exactly, so the status line prints the digits the Python prints;
 * - the temp file is `.<name>.<random>.tmp` with mode 0600, as `tempfile.mkstemp` makes it.
 */

import { randomBytes } from "node:crypto";
import fs from "node:fs";
import { basename, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { wiringForm } from "./json_writer.mjs";
import { fill, read } from "./jsondata.mjs";
import { JSONDecodeError, jsonLoads } from "./pyjson.mjs";
import { aitnaRoot } from "./project_root.mjs";
import { recordedTable } from "./record.mjs";
import { decodeUtf8, dictGet, dictItem, isDict, isOSError, pyError, pyPath, pyStrip } from "./pyvalue.mjs";

const _TIME_SHAPE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/;
const _MS_PER_DAY = 24 * 60 * 60 * 1000;
const _INT_STR_DIGITS_LIMIT = 4300;

/**
 * The shape of `common/learning.json`.
 * @typedef {object} LearningData
 * @property {string} state_rel the state file, relative to `<dev root>`
 * @property {number} reminder_sessions default session threshold
 * @property {number} reminder_days default day threshold
 * @property {string} record_section the `.akmon.toml` section holding the overrides
 * @property {string[]} skip_sources the `source` values that stay silent
 * @property {string} second_opinion_variable the environment variable that marks a second-opinion run
 * @property {string} attended_variable the environment variable whose value `0` marks an unattended run
 * @property {{wait_seconds: number, poll_seconds: number, stale_seconds: number}} lock the state lock's timings
 * @property {Record<string, string>} reminder the reminder texts
 * @property {Record<string, string>} cli the `akmon learn` texts
 */

/**
 * What the project's local layer records of the learning run: the last run, the counting start,
 * the sessions since.
 */
export class LearningState {
  /**
   * @param {string | null} [lastRun]
   * @param {string | null} [since]
   * @param {readonly string[]} [sessions]
   */
  constructor(lastRun = null, since = null, sessions = []) {
    this.lastRun = lastRun;
    this.since = since;
    this.sessions = Object.freeze([...sessions]);
    Object.freeze(this);
  }
}

/** When the reminder fires: this many sessions, or this many days, since the last run. */
export class Thresholds {
  /**
   * @param {number | bigint} reminderSessions
   * @param {number | bigint} reminderDays
   */
  constructor(reminderSessions, reminderDays) {
    this.reminderSessions = reminderSessions;
    this.reminderDays = reminderDays;
    Object.freeze(this);
  }
}

/**
 * A session start as the hook payload names it: its id and how it began (`startup`, `resume`,
 * `compact` …), and whether a person is at the session — an unattended run (`claude -p`) is
 * recorded but never reminded, since nobody is there to act on the reminder.
 * @typedef {object} SessionEvent
 * @property {string | null} sessionId
 * @property {string | null} source
 * @property {boolean} attended
 */

/** The state file's lock could not be taken within the retry window. */
export class StateLockedError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "StateLockedError";
  }
}

/** A reminder that is due: how many sessions and whole days have passed. */
export class Due {
  /**
   * @param {number} sessions
   * @param {number} days
   * @param {boolean} sinceRun whether a learning run is recorded (else: since counting began)
   */
  constructor(sessions, days, sinceRun) {
    this.sessions = sessions;
    this.days = days;
    this.sinceRun = sinceRun;
    Object.freeze(this);
  }
}

/**
 * The learning data file beside this module: state path, threshold defaults, reminder and CLI texts.
 * @returns {LearningData}
 */
export function readData() {
  return /** @type {LearningData} */ (read(fileURLToPath(new URL("../../common/learning.json", import.meta.url))));
}

/**
 * `moment` as the UTC ISO-seconds text the state file records (`2026-10-28T09:30:00Z`).
 * @param {Date} moment
 * @returns {string}
 */
export function formatUtc(moment) {
  return `${moment.toISOString().slice(0, 19)}Z`;
}

/**
 * The moment a recorded UTC ISO-seconds `text` names.
 * @param {string} text
 * @returns {Date}
 * @throws {Error} named `ValueError` when `text` is not in the {@link formatUtc} shape, or names no
 *   real moment (month 13, Feb 30, hour 24, year 0)
 */
export function parseUtc(text) {
  if (!_TIME_SHAPE.test(text)) {
    throw pyError("ValueError", `not a UTC ISO-seconds time: '${text}'`);
  }
  const [year, month, day, hour, minute, second] = text.match(/[0-9]+/g)?.map(Number) ?? [];
  const moment = new Date(0);
  moment.setUTCFullYear(year, month - 1, day); // `Date.UTC` reads years 0-99 as 19xx
  moment.setUTCHours(hour, minute, second, 0);
  if (!_isCalendarMoment(moment, [year, month, day, hour, minute, second])) {
    throw pyError("ValueError", `time data '${text}' does not name a real moment`);
  }
  return moment;
}

/**
 * Whether `moment`, built from `fields` (year to second), kept them: a month 13, a Feb 30, an hour
 * 24 or a year 0 rolls over or falls out of the range `datetime` takes.
 * @param {Date} moment
 * @param {number[]} fields year, month, day, hour, minute, second
 * @returns {boolean}
 */
function _isCalendarMoment(moment, fields) {
  const [year, month, day, hour, minute, second] = fields;
  return (
    year >= 1 &&
    moment.getUTCFullYear() === year &&
    moment.getUTCMonth() === month - 1 &&
    moment.getUTCDate() === day &&
    moment.getUTCHours() === hour &&
    moment.getUTCMinutes() === minute &&
    moment.getUTCSeconds() === second
  );
}

/**
 * Where the project's learning record lives: under the local layer of `<dev root>` (ADR 0022).
 * @param {string} projectRoot
 * @param {LearningData} data
 * @returns {string}
 */
export function statePath(projectRoot, data) {
  return pyPath(aitnaRoot(projectRoot), dictItem(data, "state_rel"));
}

/**
 * Whether `value` is `null` or a recorded moment.
 * @param {unknown} value
 * @returns {boolean}
 */
function _isMomentOrNull(value) {
  if (value === null) {
    return true;
  }
  if (typeof value !== "string") {
    return false;
  }
  try {
    parseUtc(value);
  } catch (error) {
    if (/** @type {Error} */ (error).name === "ValueError") {
      return false;
    }
    throw error;
  }
  return true;
}

/**
 * The recorded state, or the empty state when `path` is missing, unreadable or not a valid record.
 * @param {string} path
 * @returns {LearningState}
 */
export function readState(path) {
  /** @type {any} */
  let loaded;
  try {
    loaded = jsonLoads(decodeUtf8(fs.readFileSync(path)));
  } catch (error) {
    const name = /** @type {Error} */ (error).name;
    if (isOSError(error) || error instanceof JSONDecodeError || name === "UnicodeDecodeError") {
      return new LearningState();
    }
    throw error;
  }
  if (!isDict(loaded)) {
    return new LearningState();
  }
  const lastRun = dictGet(loaded, "last_run");
  const since = dictGet(loaded, "since");
  const sessions = dictGet(loaded, "sessions");
  if (!(_isMomentOrNull(lastRun) && _isMomentOrNull(since))) {
    return new LearningState();
  }
  if (!Array.isArray(sessions) || !sessions.every((item) => typeof item === "string" && item !== "")) {
    return new LearningState();
  }
  return new LearningState(lastRun, since, [...new Set(sessions)]);
}

/**
 * Persist `state` at `path` atomically: a temp file in the same directory, then a rename.
 * @param {LearningState} state
 * @param {string} path
 * @returns {void}
 */
export function writeState(state, path) {
  const directory = dirname(path);
  fs.mkdirSync(directory, { recursive: true });
  /** @type {Map<string, string | string[] | null>} */
  const document = new Map();
  document.set("last_run", state.lastRun);
  document.set("since", state.since);
  document.set("sessions", [...state.sessions]);
  const temp = pyPath(directory, `.${basename(path)}.${randomBytes(6).toString("hex")}.tmp`);
  try {
    const descriptor = fs.openSync(temp, "wx", 0o600);
    try {
      fs.writeFileSync(descriptor, wiringForm(document), "utf8");
    } finally {
      fs.closeSync(descriptor);
    }
    fs.renameSync(temp, path);
  } catch (error) {
    fs.rmSync(temp, { force: true });
    throw error;
  }
}

/**
 * Sleep `seconds`, blocking the thread (the hook has nothing else to do while it waits).
 * @param {number} seconds
 * @returns {void}
 */
function _sleep(seconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, Math.ceil(seconds * 1000));
}

/**
 * Remove `lock` when it is older than `staleSeconds`; a lock that vanished meanwhile is fine.
 * @param {string} lock
 * @param {number} staleSeconds
 * @returns {void}
 */
function _dropStale(lock, staleSeconds) {
  try {
    if ((Date.now() - fs.statSync(lock).mtimeMs) / 1000 > staleSeconds) {
      fs.unlinkSync(lock);
    }
  } catch {
    // gone, or not ours to remove: the next attempt says
  }
}

/**
 * Run `action` holding the exclusive lock file beside `path`.
 *
 * Created with `O_EXCL`; a contended lock is retried every `poll_seconds` for `wait_seconds`
 * (`learning.json`'s `lock`), and one older than `stale_seconds` is a crashed holder's, taken over.
 * @template T
 * @param {string} path
 * @param {LearningData} data
 * @param {() => T} action
 * @returns {T}
 * @throws {StateLockedError} the lock stayed held for the whole window
 */
function _locked(path, data, action) {
  const settings = dictItem(data, "lock");
  const lock = pyPath(dirname(path), `${basename(path)}.lock`);
  fs.mkdirSync(dirname(path), { recursive: true });
  const deadline = Date.now() + settings.wait_seconds * 1000;
  for (;;) {
    try {
      fs.writeFileSync(lock, `${process.pid}\n`, { flag: "wx", mode: 0o600 });
      break;
    } catch (error) {
      if (/** @type {{code?: string}} */ (error).code !== "EEXIST") {
        throw error;
      }
    }
    _dropStale(lock, settings.stale_seconds);
    if (Date.now() >= deadline) {
      throw new StateLockedError(`${lock} is held by another process`);
    }
    _sleep(settings.poll_seconds);
  }
  try {
    return action();
  } finally {
    fs.rmSync(lock, { force: true });
  }
}

/**
 * Record `sessionId` as seen at `now` and return the new state; a known id changes nothing.
 *
 * The first session recorded while no run exists starts the count (`since`). A resumed or
 * compacted session keeps its id, so it is not counted twice; an already-known id writes nothing.
 * @param {string} path
 * @param {string} sessionId
 * @param {Date} now
 * @param {LearningData} data
 * @returns {LearningState}
 * @throws {StateLockedError} another process holds the state's lock for the whole retry window
 */
export function recordSession(path, sessionId, now, data) {
  const known = readState(path);
  if (known.sessions.includes(sessionId)) {
    return known; // the common resume: no lock, no write
  }
  return _locked(path, data, () => {
    const state = readState(path);
    if (state.sessions.includes(sessionId)) {
      return state;
    }
    const since = state.since !== null || state.lastRun !== null ? state.since : formatUtc(now);
    const updated = new LearningState(state.lastRun, since, [...state.sessions, sessionId]);
    writeState(updated, path);
    return updated;
  });
}

/**
 * Record the end of a learning run at `now`: `lastRun` set, the counted sessions and `since` cleared.
 * @param {string} path
 * @param {Date} now
 * @param {LearningData} data
 * @returns {LearningState}
 * @throws {StateLockedError} another process holds the state's lock for the whole retry window
 */
export function markRun(path, now, data) {
  return _locked(path, data, () => {
    const updated = new LearningState(formatUtc(now), null, []);
    writeState(updated, path);
    return updated;
  });
}

/**
 * Whole days from the last run (or, before any run, from the counting start) to `now`; null with
 * neither.
 * @param {LearningState} state
 * @param {Date} now
 * @returns {number | null}
 */
export function daysSince(state, now) {
  const baseline = state.lastRun || state.since;
  if (baseline === null) {
    return null;
  }
  return Math.max(0, Math.floor((now.getTime() - parseUtc(baseline).getTime()) / _MS_PER_DAY));
}

/**
 * `value` as a positive integer, else `fallback` — the lenient record reader hands back strings.
 * @param {unknown} value
 * @param {number} fallback
 * @returns {number | bigint}
 */
function _positiveInt(value, fallback) {
  let candidate = value;
  if (typeof candidate === "string") {
    candidate = _decimalOrNull(pyStrip(candidate));
  }
  if (typeof candidate === "number" && Number.isInteger(candidate) && candidate > 0) {
    return candidate;
  }
  if (typeof candidate === "bigint" && candidate > 0n) {
    return candidate;
  }
  return fallback;
}

/**
 * The integer an ASCII decimal text names (a `number` while it is exact, else a `bigint`), or null
 * for any other text; more digits than Python's `int()` takes is its `ValueError`.
 * @param {string} text
 * @returns {number | bigint | null}
 */
function _decimalOrNull(text) {
  if (!/^[0-9]+$/.test(text)) {
    return null;
  }
  if (text.length > _INT_STR_DIGITS_LIMIT) {
    throw pyError(
      "ValueError",
      `Exceeds the limit (${_INT_STR_DIGITS_LIMIT} digits) for integer string conversion: ` +
        `value has ${text.length} digits; use sys.set_int_max_str_digits() to increase the limit`,
    );
  }
  const exact = BigInt(text);
  return exact <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(exact) : exact;
}

/**
 * The reminder thresholds: `[learning]` of `<dev root>/.akmon.toml` over the shipped defaults.
 *
 * A missing section, a missing key and a value that is not a positive integer each fall back to
 * the default — a hook consulting the record never aborts a session over it.
 * @param {string} projectRoot
 * @param {LearningData} data
 * @returns {Thresholds}
 */
export function readThresholds(projectRoot, data) {
  const table = recordedTable(projectRoot, dictItem(data, "record_section"));
  return new Thresholds(
    _positiveInt(dictGet(table, "reminder_sessions"), dictItem(data, "reminder_sessions")),
    _positiveInt(dictGet(table, "reminder_days"), dictItem(data, "reminder_days")),
  );
}

/**
 * The reminder to give, or null.
 *
 * Due when at least one session has passed since the last run **and** either the session count
 * reached `reminderSessions` or the days since the last run (before any run: since counting began)
 * reached `reminderDays`.
 * @param {LearningState} state
 * @param {Thresholds} thresholds
 * @param {Date} now
 * @returns {Due | null}
 */
export function reminderDue(state, thresholds, now) {
  const count = state.sessions.length;
  if (count < 1) {
    return null;
  }
  const days = daysSince(state, now);
  if (count >= thresholds.reminderSessions || (days !== null && days >= thresholds.reminderDays)) {
    return new Due(count, days ?? 0, state.lastRun !== null);
  }
  return null;
}

/**
 * `count` with its noun: `1 session`, `12 sessions`.
 * @param {number} count
 * @param {string} one
 * @param {string} many
 * @returns {string}
 */
function _counted(count, one, many) {
  return `${count} ${count === 1 ? one : many}`;
}

/**
 * The reminder as `[for the model, for the owner]`.
 * @param {Due} due
 * @param {LearningData} data
 * @returns {[string, string]}
 */
export function reminderTexts(due, data) {
  const texts = dictItem(data, "reminder");
  const values = {
    sessions: _counted(due.sessions, dictItem(texts, "session_one"), dictItem(texts, "session_many")),
    days: _counted(due.days, dictItem(texts, "day_one"), dictItem(texts, "day_many")),
  };
  const suffix = due.sinceRun ? "since_run" : "since_start";
  return [fill(dictItem(texts, `model_${suffix}`), values), fill(dictItem(texts, `owner_${suffix}`), values)];
}

/**
 * What a session start says about the learning run — `[for the model, for the owner]` — or null.
 *
 * Silent on a `source` the data lists in `skip_sources` (a compaction: the same session, whose
 * model was already told) and whenever {@link reminderDue} finds nothing due. `state` is what was
 * recorded *before* this session: a session counts only once it has passed.
 * @param {LearningState} state
 * @param {string | null} source
 * @param {Thresholds} thresholds
 * @param {Date} now
 * @param {LearningData} data
 * @returns {[string, string] | null}
 */
export function sessionReminder(state, source, thresholds, now, data) {
  if (source !== null && dictItem(data, "skip_sources").includes(source)) {
    return null;
  }
  const due = reminderDue(state, thresholds, now);
  return due === null ? null : reminderTexts(due, data);
}

/**
 * The one SessionStart step both harnesses take: decide what is due, then record the session.
 *
 * Changes state *and* returns, by design — the hook has one step to run and both halves belong to
 * it; the two parts are {@link sessionReminder} and {@link recordSession}. The decision is taken on
 * the state *before* this session: the session just starting has not "passed" (ADR 0026 D07), so
 * ten sessions are counted when the eleventh starts. No reminder for an unattended run
 * (`event.attended` false), which is still recorded. An unidentified session (`event.sessionId` is
 * null or empty) cannot be deduplicated, so it is not recorded. A record that cannot be locked is
 * given up on silently: no reminder, no write, no wait.
 * @param {string} path
 * @param {SessionEvent} event
 * @param {Thresholds} thresholds
 * @param {Date} now
 * @param {LearningData} data
 * @returns {[string, string] | null}
 */
export function recordAndRemind(path, event, thresholds, now, data) {
  const before = readState(path);
  const reminder = event.attended ? sessionReminder(before, event.source, thresholds, now, data) : null;
  if (event.sessionId) {
    try {
      recordSession(path, event.sessionId, now, data);
    } catch (error) {
      if (error instanceof StateLockedError) {
        return null;
      }
      throw error;
    }
  }
  return reminder;
}

/**
 * Whether this process is a second-opinion run (`tools/model_routing/second_opinion`): not a
 * session of the owner's.
 * @param {Record<string, string | undefined>} environ
 * @param {LearningData} data
 * @returns {boolean}
 */
export function isSecondOpinion(environ, data) {
  return Boolean(environ[dictItem(data, "second_opinion_variable")]);
}

/**
 * Whether a person is at the session: false only when the harness says `0` (M199, M200); absent
 * means attended.
 * @param {Record<string, string | undefined>} environ
 * @param {LearningData} data
 * @returns {boolean}
 */
export function isAttended(environ, data) {
  return environ[dictItem(data, "attended_variable")] !== "0";
}

/**
 * The session start a hook records and reminds on, or null when it is not one of the owner's.
 *
 * A second-opinion run ({@link isSecondOpinion}) is neither recorded nor reminded; an unattended
 * session is recorded, never reminded. The hook reads `environ` once at its entry point and passes
 * it here — nothing below reads the process environment.
 * @param {string | null} sessionId
 * @param {string | null} source
 * @param {Record<string, string | undefined>} environ
 * @param {LearningData} data
 * @returns {SessionEvent | null}
 */
export function sessionEvent(sessionId, source, environ, data) {
  if (isSecondOpinion(environ, data)) {
    return null;
  }
  return { sessionId, source, attended: isAttended(environ, data) };
}
