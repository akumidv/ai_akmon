/**
 * Where a recording lives and what is kept of it: one folder per recording under
 * `<dev root>/.local/.browser/recordings/<name>/` with its `events.jsonl`, and the state of the recording
 * that is running in `<dev root>/.local/.browser/recording.json`. The recordings stay in the project's local
 * layer (git-ignored), are named by the session, and are deleted only on request.
 *
 * **The clock.** Every `t` is milliseconds from `startedAtMs`, the wall-clock time the `start` verb took
 * before it launched the recorder and wrote into the state file. The recorder reads the same value from its
 * configuration, and `record mark` computes `t` as `Date.now() - startedAtMs` from the state file: one clock
 * (this machine's), one base. The recorder keeps its own stamps from going backwards if the clock is set
 * back, and stamps an event when it reaches the file, not when the browser made it, so a Windows Chrome's
 * clock under WSL never enters it (an event that began earlier, such as a request, says how much earlier).
 */

import fs from "node:fs";
import { posix } from "node:path";

import { isFailed } from "./ops.mjs";
import { eventLine, readEvents } from "./record-events.mjs";
import { scrubbedText } from "./redact.mjs";
import { BrowserError } from "./settings.mjs";

/** The folder of all recordings, in the browser's state folder. */
const _RECORDINGS = "recordings";
const _STATE = "recording.json";
const _EVENTS = "events.jsonl";
/** What a recording's name may be: a folder name, and nothing that climbs out of the recordings folder. */
const _NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const _DEFAULT_NAME = /^rec-(\d+)$/;

/**
 * What a recording was started with.
 * @typedef {object} RecordOptions
 * @property {string | null} page the `--page` selector; `null` for the default page
 * @property {boolean} allPages every page, and the ones that open later
 * @property {boolean} bodies keep request and response bodies (redacted, capped)
 * @property {number} maxBody the cap of a body in bytes
 */

/**
 * The state of the recording that is running, in `<browser dir>/recording.json`.
 * @typedef {object} RecordingState
 * @property {string} name
 * @property {number} pid the recorder's process id
 * @property {number} startedAtMs the clock base of every `t`, milliseconds since the epoch
 * @property {RecordOptions} options
 * @property {"here" | "windows"} side where the Chrome side runs
 * @property {string[]} redact the project's own redact keys, which `record mark` scrubs a note with
 */

/**
 * The folder of the recordings.
 * @param {string} browserDir
 * @returns {string}
 */
export function recordingsDir(browserDir) {
  return posix.join(browserDir, _RECORDINGS);
}

/**
 * The folder of one recording.
 * @param {string} browserDir
 * @param {string} name
 * @returns {string}
 * @throws {BrowserError} when the name is not a plain folder name
 */
export function recordingDir(browserDir, name) {
  checkName(name);
  return posix.join(recordingsDir(browserDir), name);
}

/**
 * The file a recording's events go to.
 * @param {string} dir the recording's folder
 * @returns {string}
 */
export function eventsPath(dir) {
  return posix.join(dir, _EVENTS);
}

/**
 * A name a recording may have.
 * @param {string} name
 * @throws {BrowserError} when it is not one: it must start with a letter or digit and hold only letters, digits, `.`, `_` and `-`
 */
export function checkName(name) {
  if (!_NAME.test(name)) {
    throw new BrowserError(
      `${JSON.stringify(name)} is not a recording name: use letters, digits, '.', '_' and '-', starting with a letter or digit, up to 64 characters`,
    );
  }
}

/**
 * The names of the recordings that exist, sorted.
 * @param {string} browserDir
 * @returns {string[]}
 */
export function recordingNames(browserDir) {
  try {
    return fs
      .readdirSync(recordingsDir(browserDir), { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && _NAME.test(entry.name))
      .map((entry) => entry.name)
      .sort();
  } catch {
    return [];
  }
}

/**
 * The name a recording gets when none is given: `rec-<n>`, one past the highest `n` in use.
 * @param {readonly string[]} existing the names in use
 * @returns {string}
 */
export function nextName(existing) {
  const used = existing.map((name) => Number(_DEFAULT_NAME.exec(name)?.[1] ?? 0));
  return `rec-${Math.max(0, ...used) + 1}`;
}

/**
 * The state of the running recording, or `null` when there is none.
 * @param {string} browserDir
 * @returns {RecordingState | null}
 */
export function readState(browserDir) {
  try {
    return JSON.parse(fs.readFileSync(posix.join(browserDir, _STATE), "utf8"));
  } catch {
    return null;
  }
}

/**
 * Write the state of the running recording.
 * @param {string} browserDir
 * @param {RecordingState} state
 */
export function writeState(browserDir, state) {
  fs.mkdirSync(browserDir, { recursive: true });
  fs.writeFileSync(posix.join(browserDir, _STATE), `${JSON.stringify(state, null, 2)}\n`);
}

/**
 * Forget the state of the running recording.
 * @param {string} browserDir
 */
export function clearState(browserDir) {
  fs.rmSync(posix.join(browserDir, _STATE), { force: true });
}

/**
 * The writer of a recording's events. It stamps `t` itself, when the event reaches it, from one clock
 * that never goes back.
 * @typedef {object} Sink
 * @property {(event: Record<string, unknown>, ago?: number) => void} append write one event; `ago` is how long before now it began
 */

/**
 * A sink that appends events to a file, each a line, written at once so that a stopped recorder loses nothing.
 * @param {{file: string, startedAtMs: number, now: () => number}} where
 * @returns {Sink}
 */
export function fileSink(where) {
  let last = 0;
  return {
    append: (event, ago = 0) => {
      last = Math.max(last, where.now() - where.startedAtMs);
      const t = Math.max(0, last - Math.round(ago));
      fs.appendFileSync(where.file, eventLine({ t, ...event }));
    },
  };
}

/**
 * Add a mark to a recording that runs: `{t, kind: "mark", note}`, with `t` on the recorder's clock.
 * @param {{dir: string, state: RecordingState, now: () => number}} where
 * @param {string} note what the user says went wrong
 * @returns {{t: number, number: number}} the time, and the mark's number among the recording's marks (from 1)
 */
export function appendMark(where, note) {
  const file = eventsPath(where.dir);
  const before = readEvents(readTextOrEmpty(file)).events.filter((event) => event.kind === "mark").length;
  const t = Math.max(0, where.now() - where.state.startedAtMs);
  fs.appendFileSync(file, eventLine({ t, kind: "mark", note: scrubbedText(note, where.state.redact) }));
  return { t, number: before + 1 };
}

/**
 * The text of a file, or an empty text when it is not there.
 * @param {string} path
 * @returns {string}
 */
export function readTextOrEmpty(path) {
  try {
    return fs.readFileSync(path, "utf8");
  } catch {
    return "";
  }
}

/**
 * What a finished or running recording holds, counted.
 * @typedef {object} Summary
 * @property {Record<string, number>} byKind events by kind
 * @property {number} events
 * @property {number} marks
 * @property {number} failedRequests requests that failed or answered 400 or more
 * @property {number} exceptions
 * @property {number} durationMs `t` of the last event
 * @property {number} skipped lines of the file that could not be read
 */

/**
 * The summary of a recording's events.
 * @param {string} text the text of `events.jsonl`
 * @returns {Summary}
 */
export function summaryOf(text) {
  const { events, skipped } = readEvents(text);
  /** @type {Record<string, number>} */
  const byKind = {};
  let failedRequests = 0;
  let durationMs = 0;
  for (const event of events) {
    byKind[event.kind] = (byKind[event.kind] ?? 0) + 1;
    durationMs = Math.max(durationMs, event.t);
    if (event.kind === "net" && isFailed(/** @type {any} */ (event))) {
      failedRequests += 1;
    }
  }
  return {
    byKind,
    events: events.length,
    marks: byKind["mark"] ?? 0,
    failedRequests,
    exceptions: byKind["exception"] ?? 0,
    durationMs,
    skipped,
  };
}
