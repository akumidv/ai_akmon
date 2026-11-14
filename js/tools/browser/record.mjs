/**
 * `akmon tool browser record <sub-command>`: record a session the user drives in the shared Chrome, so the agent
 * can read it afterwards or while it runs. `start` launches a detached recorder (`recorder.mjs`) that outlives the
 * command and appends events to `<dev root>/.local/.browser/recordings/<name>/events.jsonl`; `mark` adds the
 * moment the user says something went wrong; `stop` ends it and prints what it holds; `status`, `list` and
 * `delete` manage recordings; `export` prints a timeline (all of it, or the stretch around a mark) or writes a
 * draft end-to-end test. The agent stays passive: the recording only listens, a typed value is never kept, a
 * secret is redacted at capture, and a recording stays in the project's local layer until it is deleted.
 * One recording runs at a time per project.
 */

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { LOCAL_TIMEOUT_MS } from "./host.mjs";
import { BrowserError } from "./settings.mjs";
import { locateBrowser, outputPath } from "./inspect.mjs";
import { readEvents } from "./record-events.mjs";
import {
  DEFAULT_WINDOW_SECONDS,
  eventsAround,
  markAt,
  playwrightDraft,
  sortedEvents,
  summaryLines,
  timelineLines,
} from "./record-export.mjs";
import { readRecordSettings } from "./record-settings.mjs";
import {
  appendMark,
  clearState,
  eventsPath,
  nextName,
  readState,
  readTextOrEmpty,
  recordingDir,
  recordingNames,
  summaryOf,
  checkName,
  writeState,
} from "./record-store.mjs";

/** The recorder, started as a detached `node` process. */
const RECORDER_PATH = fileURLToPath(new URL("./recorder.mjs", import.meta.url));
/** The name of the CDP binding the injected listener reports through. */
const BINDING = "__akmonRecord";
/** How long `start` waits for the recorder to be recording, and `stop` for it to end, in milliseconds. */
const _START_MS = 30_000;
const _STOP_MS = 15_000;
const _POLL_MS = 100;

/**
 * @typedef {import("./context.mjs").Context} Context
 * @typedef {import("./arguments.mjs").Options} Options
 */

/**
 * What the verb asks of the machine, replaced by a test.
 * @typedef {object} RecordHow
 * @property {(ctx: Context) => Promise<import("./inspect.mjs").Browser>} locate which browser to record, checked
 * @property {(configPath: string, logPath: string) => number} launch start the recorder detached; its process id
 * @property {(pid: number) => boolean} alive whether the process is the recorder, still running, read from its command line
 * @property {(pid: number) => boolean} [unverifiable] whether the process exists but nothing says what it runs, so it is not signalled
 * @property {(pid: number, signal: "SIGTERM" | "SIGKILL") => void} signal
 * @property {() => number} now milliseconds since the epoch
 * @property {(ms: number) => Promise<void>} sleep
 */

/**
 * The real machine.
 * @returns {RecordHow}
 */
export function realRecordHow() {
  return {
    locate: locateBrowser,
    launch: (configPath, logPath) => {
      const log = fs.openSync(logPath, "a");
      try {
        const child = spawn(process.execPath, [RECORDER_PATH, configPath], {
          detached: true,
          stdio: ["ignore", log, log],
          windowsHide: true,
        });
        child.on("error", () => {
          // A recorder that could not start leaves no `start` event; `start` reports it.
        });
        child.unref();
        if (child.pid === undefined) {
          throw new BrowserError(`could not start the recorder: ${process.execPath} did not run`);
        }
        return child.pid;
      } finally {
        fs.closeSync(log);
      }
    },
    alive: (pid) => recorderState(pid, realProcessReaders()) === "recorder",
    unverifiable: (pid) => recorderState(pid, realProcessReaders()) === "unverifiable",
    signal: (pid, signal) => {
      try {
        process.kill(pid, signal);
      } catch {
        // It ended in the meantime: that is what was wanted.
      }
    },
    now: () => Date.now(),
    sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  };
}

/**
 * What `recorderState` asks of the machine.
 * @typedef {object} ProcessReaders
 * @property {string} platform `process.platform`
 * @property {(pid: number) => boolean} exists whether a process with the id runs
 * @property {(pid: number) => string | null} procCommand `/proc/<pid>/cmdline` as text, or `null` when it cannot be read
 * @property {(pid: number) => string | null} psCommand `ps -p <pid> -o command=`, or `null` when it did not answer
 */

/**
 * The real machine's process readers.
 * @returns {ProcessReaders}
 */
export function realProcessReaders() {
  return {
    platform: process.platform,
    exists: (pid) => {
      try {
        process.kill(pid, 0);
        return true;
      } catch {
        return false;
      }
    },
    procCommand: (pid) => {
      try {
        return fs.readFileSync(`/proc/${pid}/cmdline`, "utf8");
      } catch {
        return null;
      }
    },
    psCommand: (pid) => {
      const run = spawnSync("ps", ["-p", String(pid), "-o", "command="], {
        encoding: "utf8",
        timeout: LOCAL_TIMEOUT_MS,
      });
      return run.error === undefined && run.status === 0 ? run.stdout : null;
    },
  };
}

/**
 * What a process id is, by its command line: the recorder, another program (an id that was reused), nothing
 * (it ended), or unverifiable, when the platform gives no command line to read (Windows, or `/proc` and
 * `ps` that did not answer). An unverifiable process is never signalled: it could be anything.
 * @param {number} pid
 * @param {ProcessReaders} readers
 * @returns {"recorder" | "other" | "gone" | "unverifiable"}
 */
export function recorderState(pid, readers) {
  if (!readers.exists(pid)) {
    return "gone";
  }
  /** @type {string | null} */
  let command = null;
  if (readers.platform === "linux") {
    command = readers.procCommand(pid);
  } else if (readers.platform === "darwin") {
    command = readers.psCommand(pid);
  }
  if (command === null) {
    return "unverifiable";
  }
  return command.includes("recorder.mjs") ? "recorder" : "other";
}

/**
 * `record <sub-command> ...`.
 * @param {Context} ctx
 * @param {Options} options
 * @param {RecordHow} [how]
 * @returns {Promise<number>}
 */
export async function recordCommand(ctx, options, how = realRecordHow()) {
  switch (options.sub) {
    case "start":
      return _start(ctx, options, how);
    case "mark":
      return _mark(ctx, String(options.note ?? ""), how);
    case "stop":
      return _stop(ctx, how);
    case "status":
      return _status(ctx, options, how);
    case "list":
      return _list(ctx, options, how);
    case "delete":
      return _delete(ctx, String(options.name), how);
    default:
      return _export(ctx, options, how);
  }
}

/**
 * The state of the recording that is running, or a refusal.
 * @param {Context} ctx
 * @param {RecordHow} how
 * @returns {import("./record-store.mjs").RecordingState}
 * @throws {BrowserError} when none is running
 */
function _running(ctx, how) {
  const state = readState(ctx.project.browserDir);
  if (state === null || !how.alive(state.pid)) {
    throw new BrowserError("no recording is running; start one: akmon tool browser record start [--name NAME]");
  }
  return state;
}

/**
 * The text `start` prints: the name and what to do next.
 * @param {string} name
 * @param {string} file
 * @param {number} pid
 * @returns {string[]}
 */
function _startedLines(name, file, pid) {
  return [
    `recording ${name} started (recorder pid ${pid}); it runs until it is stopped`,
    `  events: ${file}`,
    '  mark the moment something goes wrong: akmon tool browser record mark "what happened"',
    "  read the stretch around it:           akmon tool browser record export --around last",
    "  stop:                                 akmon tool browser record stop",
  ];
}

/**
 * `record start`: launch the recorder and return once it records.
 * @param {Context} ctx
 * @param {Options} options
 * @param {RecordHow} how
 * @returns {Promise<number>}
 * @throws {BrowserError} when one is already running, no Chrome answers, or the recorder cannot begin
 */
async function _start(ctx, options, how) {
  const dir = ctx.project.browserDir;
  _refuseSecond(ctx, how);
  const settings = readRecordSettings(ctx.project);
  const browser = await how.locate(ctx);
  const name = options.name ?? nextName(recordingNames(dir));
  const folder = recordingDir(dir, name);
  if (fs.existsSync(folder)) {
    throw new BrowserError(
      `a recording named ${name} exists; choose another name, or delete it: akmon tool browser record delete ${name}`,
    );
  }
  const chosen = {
    page: options.page,
    allPages: options.page === null && (options.allPages || settings.allPages),
    bodies: options.bodies || settings.bodies,
    maxBody: options.maxBody ?? settings.maxBody,
  };
  /** @type {import("./recorder.mjs").RecorderConfig} */
  const config = {
    name,
    dir: folder,
    startedAtMs: how.now(),
    side: browser.side,
    request: { browserURL: browser.browserURL, ...chosen, redact: [...ctx.settings.redact], binding: BINDING },
  };
  fs.mkdirSync(folder, { recursive: true });
  const configPath = posix.join(folder, "recorder.json");
  fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`);
  const pid = how.launch(configPath, posix.join(folder, "recorder.log"));
  writeState(dir, {
    name,
    pid,
    startedAtMs: config.startedAtMs,
    options: chosen,
    side: browser.side,
    redact: [...ctx.settings.redact],
  });
  try {
    await _awaitRecording(folder, { pid, how });
  } catch (exc) {
    // Only a process verified to be the recorder is signalled: an id nothing can verify (Windows) may be any program.
    if (how.alive(pid)) {
      how.signal(pid, "SIGKILL");
    }
    clearState(dir);
    fs.rmSync(folder, { recursive: true, force: true });
    throw exc;
  }
  _startedLines(name, eventsPath(folder), pid).forEach(ctx.say);
  return 0;
}

/**
 * Refuse a second recording; clear the state of one whose recorder is gone.
 * @param {Context} ctx
 * @param {RecordHow} how
 * @throws {BrowserError} when a recording is running
 */
function _refuseSecond(ctx, how) {
  const state = readState(ctx.project.browserDir);
  if (state === null) {
    return;
  }
  if (how.alive(state.pid)) {
    throw new BrowserError(
      `recording ${state.name} is running (recorder pid ${state.pid}); one at a time per project: akmon tool browser record stop`,
    );
  }
  ctx.say(`recording ${state.name} had ended without being stopped; its events are kept, and its state is cleared`);
  clearState(ctx.project.browserDir);
}

/**
 * The line for a recorder that ended before it recorded: its own last log line.
 * @param {string} folder
 * @returns {string}
 */
function _exitedLine(folder) {
  const logged = readTextOrEmpty(posix.join(folder, "recorder.log")).trim().split("\n").at(-1);
  return `the recorder exited before it began recording${logged ? `: ${logged}` : ""}`;
}

/**
 * The line for a recorder that did not record in time.
 * @param {number | null} unverifiedPid the process, when nothing can show it is the recorder (so it was not signalled)
 * @returns {string}
 */
function _timeoutLine(unverifiedPid) {
  const base = `the recorder did not begin recording within ${_START_MS / 1000} s`;
  return unverifiedPid === null
    ? base
    : `${base}; process ${unverifiedPid} could not be verified as the recorder on this platform, so it was not signalled: end it by hand if it still runs`;
}

/**
 * Wait until the recorder says it records (`start`) or why it cannot (`error`). A process that cannot be
 * verified (no command line to read, as on Windows) counts as still starting: only the events file or the
 * start timeout ends the wait, and it is never signalled.
 * @param {string} folder
 * @param {{pid: number, how: RecordHow}} where
 * @returns {Promise<void>}
 * @throws {BrowserError} with the recorder's own words when it could not begin
 */
async function _awaitRecording(folder, where) {
  const { how } = where;
  const deadline = how.now() + _START_MS;
  for (;;) {
    const events = readEvents(readTextOrEmpty(eventsPath(folder))).events;
    const failed = events.find((event) => event.kind === "error");
    if (failed !== undefined) {
      throw new BrowserError(String(failed["text"]));
    }
    if (events.some((event) => event.kind === "start")) {
      return;
    }
    const unverifiable = !how.alive(where.pid) && how.unverifiable?.(where.pid) === true;
    if (!unverifiable && !how.alive(where.pid)) {
      throw new BrowserError(_exitedLine(folder));
    }
    if (how.now() > deadline) {
      throw new BrowserError(_timeoutLine(unverifiable ? where.pid : null));
    }
    await how.sleep(_POLL_MS);
  }
}

/**
 * `record mark [NOTE]`: add a mark at the time now.
 * @param {Context} ctx
 * @param {string} note
 * @param {RecordHow} how
 * @returns {Promise<number>}
 */
async function _mark(ctx, note, how) {
  const state = _running(ctx, how);
  const dir = recordingDir(ctx.project.browserDir, state.name);
  const { t, number } = appendMark({ dir, state, now: how.now }, note);
  ctx.say(`mark #${number} in ${state.name} at +${(t / 1000).toFixed(3)}s${note === "" ? "" : `: ${note}`}`);
  return 0;
}

/**
 * Wait until a process is gone, or the time is up.
 * @param {number} pid
 * @param {RecordHow} how
 * @returns {Promise<boolean>} whether it is gone
 */
async function _waitGone(pid, how) {
  const deadline = how.now() + _STOP_MS;
  while (how.alive(pid)) {
    if (how.now() > deadline) {
      return false;
    }
    await how.sleep(_POLL_MS);
  }
  return true;
}

/**
 * `record stop`: end the recording and print what it holds.
 * @param {Context} ctx
 * @param {RecordHow} how
 * @returns {Promise<number>}
 * @throws {BrowserError} when no recording is running or was left
 */
async function _stop(ctx, how) {
  const dir = ctx.project.browserDir;
  const state = readState(dir);
  if (state === null) {
    throw new BrowserError("no recording is running; `record list` shows the ones that were kept");
  }
  if (!how.alive(state.pid)) {
    ctx.say(
      how.unverifiable?.(state.pid) === true
        ? `process ${state.pid} is not shown to be the recorder of ${state.name} on this platform, so it was not signalled; the recording state is cleared. If a recorder still runs, end it by hand`
        : `the recorder of ${state.name} had already ended (Chrome closed, or it was killed)`,
    );
  } else {
    how.signal(state.pid, "SIGTERM");
    if (!(await _waitGone(state.pid, how))) {
      how.signal(state.pid, "SIGKILL");
      ctx.say(
        `the recorder did not end within ${_STOP_MS / 1000} s and was killed: the tail of the recording may be missing, and the listener stays in the open page until it reloads`,
      );
    }
  }
  clearState(dir);
  summaryLines(state.name, summaryOf(readTextOrEmpty(eventsPath(recordingDir(dir, state.name))))).forEach(ctx.say);
  ctx.say(
    `kept in ${recordingDir(dir, state.name)}; delete it when done: akmon tool browser record delete ${state.name}`,
  );
  return 0;
}

/**
 * `record status [--json]`.
 * @param {Context} ctx
 * @param {Options} options
 * @param {RecordHow} how
 * @returns {Promise<number>}
 */
async function _status(ctx, options, how) {
  const dir = ctx.project.browserDir;
  const state = readState(dir);
  const live = state !== null && how.alive(state.pid);
  const summary = state === null ? null : summaryOf(readTextOrEmpty(eventsPath(recordingDir(dir, state.name))));
  if (options.json) {
    ctx.say(JSON.stringify({ running: live, state, summary, recordings: recordingNames(dir) }, null, 2));
    return 0;
  }
  if (state === null || summary === null) {
    ctx.say(`no recording is running; ${recordingNames(dir).length} kept (record list)`);
    return 0;
  }
  const since = ((how.now() - state.startedAtMs) / 1000).toFixed(0);
  ctx.say(
    live
      ? `recording ${state.name} is running (recorder pid ${state.pid}, ${since} s, ${state.side === "windows" ? "Chrome side on Windows" : "Chrome side here"})`
      : `recording ${state.name}: the recorder has ended; run record stop for its summary`,
  );
  summaryLines(state.name, summary).slice(1).forEach(ctx.say);
  return 0;
}

/**
 * `record list [--json]`: the recordings that exist.
 * @param {Context} ctx
 * @param {Options} options
 * @param {RecordHow} how
 * @returns {Promise<number>}
 */
async function _list(ctx, options, how) {
  const dir = ctx.project.browserDir;
  const active = readState(dir);
  const rows = recordingNames(dir).map((name) => {
    const summary = summaryOf(readTextOrEmpty(eventsPath(recordingDir(dir, name))));
    return { name, running: active?.name === name && how.alive(active.pid), ...summary };
  });
  if (options.json) {
    ctx.say(JSON.stringify(rows, null, 2));
    return 0;
  }
  if (rows.length === 0) {
    ctx.say("no recording is kept");
  }
  for (const row of rows) {
    ctx.say(
      `${row.name.padEnd(16)} ${String(row.events).padStart(6)} events  ${(row.durationMs / 1000).toFixed(1).padStart(7)} s  ${row.marks} mark(s)${row.running ? "  (running)" : ""}`,
    );
  }
  return 0;
}

/**
 * `record delete <name>`: delete one recording's folder, and nothing else.
 * @param {Context} ctx
 * @param {string} name
 * @param {RecordHow} how
 * @returns {Promise<number>}
 * @throws {BrowserError} for a name that is not a recording, or a recording that is running
 */
async function _delete(ctx, name, how) {
  const dir = ctx.project.browserDir;
  checkName(name);
  if (!recordingNames(dir).includes(name)) {
    throw new BrowserError(`no recording named ${name}; \`record list\` shows the ones that are kept`);
  }
  const active = readState(dir);
  if (active?.name === name && how.alive(active.pid)) {
    throw new BrowserError(`recording ${name} is running; stop it first: akmon tool browser record stop`);
  }
  fs.rmSync(recordingDir(dir, name), { recursive: true, force: true });
  if (active?.name === name) {
    clearState(dir);
  }
  ctx.say(`deleted recording ${name}`);
  return 0;
}

/**
 * The recording `export` reads: the one named, else the one that runs, else the newest kept.
 * @param {Context} ctx
 * @param {string | null} given
 * @param {RecordHow} how
 * @returns {string}
 * @throws {BrowserError} when there is none
 */
function _chosen(ctx, given, how) {
  const dir = ctx.project.browserDir;
  const names = recordingNames(dir);
  if (given !== null) {
    checkName(given);
    if (!names.includes(given)) {
      throw new BrowserError(`no recording named ${given}; \`record list\` shows the ones that are kept`);
    }
    return given;
  }
  const active = readState(dir);
  if (active !== null && how.alive(active.pid) && names.includes(active.name)) {
    return active.name;
  }
  const newest = names
    .map((name) => ({ name, at: _modified(eventsPath(recordingDir(dir, name))) }))
    .sort((a, b) => b.at - a.at)[0];
  if (newest === undefined) {
    throw new BrowserError("no recording to export; start one: akmon tool browser record start");
  }
  return newest.name;
}

/**
 * @param {string} path
 * @returns {number} the file's modification time, or 0 when it is not there
 */
function _modified(path) {
  try {
    return fs.statSync(path).mtimeMs;
  } catch {
    return 0;
  }
}

/**
 * `record export [NAME] [--around N|last] [--window SECONDS] [--json]` or `... --test playwright [--out PATH]`.
 * @param {Context} ctx
 * @param {Options} options
 * @param {RecordHow} how
 * @returns {Promise<number>}
 */
async function _export(ctx, options, how) {
  const dir = ctx.project.browserDir;
  const name = _chosen(ctx, options.name, how);
  const folder = recordingDir(dir, name);
  const { events, skipped } = readEvents(readTextOrEmpty(eventsPath(folder)));
  if (options.testRunner !== null) {
    const path = outputPath(options.out, { root: ctx.project.root, folder, name: `${name}.spec.ts`, always: true });
    fs.mkdirSync(posix.dirname(String(path)), { recursive: true });
    fs.writeFileSync(String(path), playwrightDraft(events, name));
    ctx.say(
      `wrote ${path}: a draft for the project's own runner; check the locators and write the assertions its TODO lines ask for`,
    );
    return 0;
  }
  const windowSeconds = options.window ?? DEFAULT_WINDOW_SECONDS;
  const around = options.around === null ? null : { ...markAt(events, options.around), windowSeconds };
  if (options.json) {
    ctx.say(
      JSON.stringify(
        around === null ? sortedEvents(events) : eventsAround(events, { t: around.mark.t, windowSeconds }),
        null,
        2,
      ),
    );
    return 0;
  }
  timelineLines(events, { name, around }).forEach(ctx.say);
  if (skipped > 0) {
    ctx.say(`${skipped} unreadable line(s) left out`);
  }
  return 0;
}
