/**
 * `akmon learn` — the learning agent's run record and its session list: the JavaScript twin of
 * `src/akmon/_learn.py` (C177, ADR 0026 D07; ADR 0020 D01). The Python module is the spec: the
 * same subcommands, texts, output lines, tabs and exit codes.
 *
 * The record, the thresholds and the texts are `common/learning.mjs`'s and the session-file
 * discovery is `common/transcripts.mjs`'s; this module is the command line over them. Imported
 * lazily by `akmon/cli.mjs`, as `trust` is. It reads only the sessions of the project the cwd
 * belongs to — never another project's (ADR 0026 D07).
 */

import os from "node:os";

import { DataFileError, fill } from "../common/jsondata.mjs";
import {
  daysSince,
  formatUtc,
  markRun,
  parseUtc,
  readData,
  readState,
  readThresholds,
  StateLockedError,
  statePath,
} from "../common/learning.mjs";
import { isRelativeTo, resolveProjectRoot } from "../common/project_root.mjs";
import { JSONDecodeError } from "../common/pyjson.mjs";
import { pyError, pyPath, strRepr } from "../common/pyvalue.mjs";
import { bySessionOrder, claudeSessions, codexSessions } from "../common/transcripts.mjs";

const _SUBCOMMANDS = ["status", "sessions", "mark"];

/** @typedef {import("../common/learning.mjs").LearningData} LearningData */

/**
 * What the command touches of the process: environment, cwd, streams and the clock.
 * @typedef {object} LearnIO
 * @property {Record<string, string | undefined>} environ
 * @property {string} cwd
 * @property {{write: (text: string) => unknown}} out
 * @property {{write: (text: string) => unknown}} err
 * @property {() => Date} now
 */

/**
 * The real process: its environment, cwd and streams, and the wall clock.
 * @returns {LearnIO}
 */
export function processIo() {
  return {
    environ: process.env,
    cwd: process.cwd(),
    out: process.stdout,
    err: process.stderr,
    now: () => new Date(),
  };
}

/**
 * A harness home: the directory `variable` names, else `~/<fallback>`.
 * @param {Record<string, string | undefined>} environ
 * @param {string} variable
 * @param {string} fallback
 * @returns {string}
 */
function _home(environ, variable, fallback) {
  const named = environ[variable];
  return named ? pyPath(named) : pyPath(os.homedir(), fallback);
}

/**
 * `path.relative_to(root).as_posix()`: a path outside the root is the stdlib's `ValueError`.
 * @param {string} path
 * @param {string} root
 * @returns {string}
 */
function _relativeTo(path, root) {
  if (!isRelativeTo(path, root) || path === root) {
    throw pyError("ValueError", `${strRepr(path)} is not in the subpath of ${strRepr(root)}`);
  }
  return path.slice(root === "/" ? 1 : root.length + 1);
}

/** One run of `akmon learn` in the project the cwd belongs to. */
class Learn {
  /**
   * @param {LearnIO} io
   * @param {LearningData} data
   * @param {string | null} [explicitRoot] the `--project-root` value, relative to the cwd or absolute
   */
  constructor(io, data, explicitRoot = null) {
    this.io = io;
    const { root, notice } = resolveProjectRoot(explicitRoot === null ? null : pyPath(io.cwd, explicitRoot), io.cwd);
    this.rooted = notice === null;
    if (notice) {
      io.err.write(`${notice}\n`);
    }
    this.root = root;
    this.data = data;
    this.path = statePath(root, data);
    this.texts = data.cli;
  }

  /**
   * @param {string} key
   * @param {Record<string, unknown>} [values]
   */
  _say(key, values = {}) {
    const text = fill(
      this.texts[key],
      Object.fromEntries(Object.entries(values).map(([name, value]) => [name, String(value)])),
    );
    this.io.out.write(`${text}\n`);
  }

  /** @returns {number} */
  status() {
    const state = readState(this.path);
    const thresholds = readThresholds(this.root, this.data);
    const days = daysSince(state, this.io.now());
    if (state.lastRun === null) {
      this._say("status_never_run");
    } else {
      this._say("status_last_run", { last_run: state.lastRun });
    }
    if (state.since === null) {
      this._say("status_not_counting");
    } else {
      this._say("status_since", { since: state.since });
    }
    this._say("status_sessions", { count: state.sessions.length });
    if (days === null) {
      this._say("status_days_none");
    } else {
      this._say("status_days", { days });
    }
    this._say("status_thresholds", { sessions: thresholds.reminderSessions, days: thresholds.reminderDays });
    this._say("status_state", { path: _relativeTo(this.path, this.root) });
    return 0;
  }

  /**
   * List this project's sessions modified since the last run, or since counting began before a first
   * run. The first line is the listing time: `mark --at` stamps it, so activity after the listing is
   * not swallowed by the run. `listAll` ignores the record and lists every session.
   * @param {boolean} listAll
   * @returns {number}
   */
  sessions(listAll) {
    const listedAt = formatUtc(this.io.now());
    const state = readState(this.path);
    const bound = listAll ? null : state.lastRun || state.since;
    const since = bound ? parseUtc(bound) : null;
    this._say("sessions_listed_at", { listed_at: listedAt });
    const found = [
      ...claudeSessions(this.root, _home(this.io.environ, "CLAUDE_CONFIG_DIR", ".claude"), since),
      ...codexSessions(this.root, _home(this.io.environ, "CODEX_HOME", ".codex"), since),
    ].sort(bySessionOrder);
    if (found.length === 0) {
      this._say(bound ? "sessions_none" : "sessions_none_ever", { since: bound });
      return 0;
    }
    this._say("sessions_header");
    for (const item of found) {
      this.io.out.write(`${item.kind}\t${item.sessionId}\t${formatUtc(item.modified)}\t${item.size}\t${item.path}\n`);
    }
    return 0;
  }

  /**
   * Record the end of a run at `at` (a UTC ISO-seconds time, normally the listing time) or now.
   * @param {string | null} at
   * @returns {number}
   * With no project root there is no local layer to record in: the notice was already printed, and
   * nothing is written (ADR 0022 D09).
   * @throws {Error} named `ValueError` when `at` is not a UTC ISO-seconds time, or lies after the current time
   */
  mark(at) {
    if (!this.rooted) {
      return 2;
    }
    const now = this.io.now();
    const moment = at === null ? now : parseUtc(at);
    if (moment.getTime() > now.getTime()) {
      throw pyError("ValueError", fill(this.texts.mark_future, { at: String(at), now: formatUtc(now) }));
    }
    const state = markRun(this.path, moment, this.data);
    this._say("marked", { last_run: state.lastRun });
    return 0;
  }
}

/**
 * Whether `error` is a failure this command reports in one line (the Python's `OSError`,
 * `RuntimeError` and `ValueError`) rather than a defect it must not hide.
 * @param {unknown} error
 * @returns {boolean}
 */
function _isReportable(error) {
  if (!(error instanceof Error)) {
    return false;
  }
  if (error instanceof DataFileError || error instanceof JSONDecodeError || error instanceof StateLockedError) {
    return true;
  }
  return (
    typeof (/** @type {{errno?: unknown}} */ (error).errno) === "number" ||
    ["ValueError", "RuntimeError", "UnicodeEncodeError", "UnicodeDecodeError"].includes(error.name)
  );
}

/**
 * @param {LearnIO} io
 * @param {string} usage
 * @param {string} message
 * @returns {number}
 */
function _usageError(io, usage, message) {
  io.err.write(`akmon learn: ${message}\n${usage}`);
  return 2;
}

/**
 * The flags of `sessions` (`--all`) and `mark` (`--at`).
 * @typedef {object} Options
 * @property {boolean} listAll
 * @property {string | null} at
 * @property {string | null} projectRoot
 */

const _PROJECT_ROOT_FLAG = "--project-root";

/**
 * `--project-root PATH` taken out of `rest`, and what is left.
 * @param {string[]} rest
 * @returns {[string | null, string[]]}
 * @throws {Error} named `ValueError` when the flag is repeated or has no path
 */
function _takeProjectRoot(rest) {
  const remaining = [...rest];
  const index = remaining.indexOf(_PROJECT_ROOT_FLAG);
  if (index === -1) {
    return [null, remaining];
  }
  if (index + 1 >= remaining.length || remaining[index + 1].startsWith("--")) {
    throw pyError("ValueError", `${_PROJECT_ROOT_FLAG} takes a path`);
  }
  const given = remaining[index + 1];
  remaining.splice(index, 2);
  if (remaining.includes(_PROJECT_ROOT_FLAG)) {
    throw pyError("ValueError", `${_PROJECT_ROOT_FLAG} given twice`);
  }
  return [given, remaining];
}

/**
 * The flags `command` takes out of `rest`; `--project-root PATH` is taken by every command.
 * @param {string} command
 * @param {string[]} restArguments
 * @returns {Options}
 * @throws {Error} named `ValueError` for a flag the command does not take, a repeated one, or `--at` without a time
 */
function _options(command, restArguments) {
  const [projectRoot, rest] = _takeProjectRoot(restArguments);
  if (rest.length === 0) {
    return { listAll: false, at: null, projectRoot };
  }
  if (command === "sessions" && rest.length === 1 && rest[0] === "--all") {
    return { listAll: true, at: null, projectRoot };
  }
  if (command === "mark" && rest[0] === "--at") {
    if (rest.length !== 2) {
      throw pyError("ValueError", "mark --at takes one time, e.g. 2026-10-28T09:30:00Z");
    }
    return { listAll: false, at: rest[1], projectRoot };
  }
  const takes = /** @type {Record<string, string>} */ ({ sessions: "only --all", mark: "only --at TIME" });
  throw pyError("ValueError", `${command} takes ${takes[command] ?? "no arguments"}; got ${strRepr(rest[0])}`);
}

/**
 * @param {Learn} session
 * @param {string} command one of the subcommands
 * @param {Options} options
 * @returns {number}
 */
function _run(session, command, options) {
  if (command === "status") {
    return session.status();
  }
  return command === "sessions" ? session.sessions(options.listAll) : session.mark(options.at);
}

/**
 * Run `akmon learn <subcommand>`; `io` is the process unless a test hands in a fake.
 * @param {string[]} argv the arguments after `learn`
 * @param {LearnIO} [io]
 * @returns {number} The process exit code.
 */
export function main(argv, io = processIo()) {
  const data = readData();
  const usage = data.cli.usage;
  if (argv.length === 0) {
    io.err.write(usage);
    return 2;
  }
  if (argv[0] === "-h" || argv[0] === "--help") {
    io.out.write(usage);
    return 0;
  }
  const [command, ...rest] = argv;
  if (!_SUBCOMMANDS.includes(command)) {
    return _usageError(io, usage, `unknown command ${strRepr(command)}`);
  }
  /** @type {Options} */
  let options;
  try {
    options = _options(command, rest);
  } catch (error) {
    return _usageError(io, usage, /** @type {Error} */ (error).message);
  }
  try {
    return _run(new Learn(io, data, options.projectRoot), command, options);
  } catch (error) {
    if (!_isReportable(error)) {
      throw error;
    }
    io.err.write(`akmon learn: ${/** @type {Error} */ (error).message}\n`);
    return 2;
  }
}
