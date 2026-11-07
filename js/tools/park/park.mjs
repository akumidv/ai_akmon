#!/usr/bin/env node
/**
 * The park helper: hold, write, resume, digest and list the kits of parked work — the JavaScript
 * twin of `tools/park/park.py` (ADR 0020 D01, ADR 0028 D02, D03, D06, D08–D12). The Python module is
 * the spec: the same files in the same bytes, the same stdout lines, the same `error:` lines, the
 * same exit codes; its docstring carries the full account of the kit, its units (the plan and its
 * jobs), the note's header format and the derived states.
 *
 * The read-only command `local-id` prints the next free local id (`_T<n>`), counted over the live
 * kits and the closed ones and never reused.
 *
 * A *kit* is the folder `<dev root>/.ergon/<id>-<name>/` of one piece of work. Its plan is `PLAN.md`;
 * its units are the plan itself (the kit root) and its jobs (`jobs/<n>-<name>/`). Parking a unit
 * writes `PARK.md` and `RESUME.md` into it atomically. A unit is held by a lease, the file `HOLDER`,
 * created exclusively and judged stale on read. There is no local index anymore: a kit is its own
 * record, and `park list` is the index (ADR 0028 D12).
 *
 * Data (the C102 convention): the tool's texts are `tools/park/park.json`, read once by `main` (and
 * by `digest` when it is called alone) and passed down as `texts`.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the dataclasses are frozen plain objects with camelCase keys (`nextAction`, `ownedPaths`,
 *   `sessionId`, `ageDays`, `staleHours`); `parkFields` and `parkBody` fill the defaults the
 *   dataclasses carry; a dataclass method is a function that takes the object first
 *   (`holderSameAs`, `holderLabel`, `leaseAgeSeconds`, `jobDocNextStep`);
 * - the arguments are parsed by a small `argparse`-shaped scanner (DV12): a usage error is the one
 *   line `park.mjs: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0.
 *   Options are accepted before and after the subcommand's positional, `--root` and `--project-root`
 *   are one option, and a value such as `-1` or `- two words` is a value, as `argparse` takes it;
 * - character counts (the digest cap, the 60-character cut of `next`) count code points, and kit ids
 *   and file paths sort by code point (a path by its components), as Python's `len` and `sorted` do;
 * - a path the helper prints follows the one rule of `_displayPath`, as in Python: from the session's
 *   project root when it lies inside, absolute when it does not (the kits of a linked worktree stay
 *   in the main checkout);
 * - an I/O failure (DV16) is the runtime's own error, never caught: Node's stack trace and exit 1.
 */

import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import { dirname, posix } from "node:path";
import { fileURLToPath } from "node:url";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { ergonRoot, gitCommonRoot, isRelativeTo, localRoot, resolveProjectRoot } from "../../common/project_root.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import {
  decodeUtf8,
  encodeUtf8,
  isDir,
  isFile,
  isOSError,
  pyInt,
  pyLen,
  pyPath,
  pyStat,
  pyStrip,
  readText,
  rstripChars,
  strRepr,
  unlinkMissingOk,
  writeText,
} from "../../common/pyvalue.mjs";

/**
 * The keys of `tools/park/park.json` the code reads.
 * @typedef {object} ParkData
 * @property {string} invocation
 * @property {number} default_cap
 * @property {number} next_width
 * @property {number} stale_after_hours
 * @property {string} unknown_holder
 * @property {string} none_marker
 * @property {string} empty_cell
 * @property {string} ellipsis
 * @property {{active: string, parked: string, not_started: string, done: string}} states
 * @property {Record<string, string>} headings
 * @property {{title: string, intro: string, steps: string[], next_heading: string, decisions_heading: string, decisions_none: string, retirement_heading: string, retirement: string[]}} resume
 * @property {{title: string}} note
 * @property {Record<string, string>} digest
 * @property {{line: string, unreadable: string, job_line: string, empty: string, no_match: string, warning_shared_paths: string}} list
 * @property {{none: string, line: string}} active
 * @property {{uncommitted: string, unreadable: string}} takeover
 * @property {{title: string, file_header: string, end: string}} export
 * @property {Record<string, string>} errors
 */

/**
 * Where the work was done: a reference for provenance, never a requirement (ADR 0028 D03).
 * @typedef {{readonly harness: string, readonly sessionId: string, readonly machine: string}} SessionRef
 */

/**
 * The holder of a lease: who holds a unit, and where (ADR 0028 D09).
 * @typedef {{readonly harness: string, readonly sessionId: string, readonly machine: string, readonly worktree: string}} Holder
 */

/**
 * The lease file `HOLDER` of a unit: its holder and the time of its last write (epoch seconds).
 * @typedef {{readonly holder: Holder, readonly written: number}} Lease
 */

/**
 * What a lease is judged against: the clock (epoch seconds), the stale threshold and this machine.
 * @typedef {{readonly now: number, readonly staleHours: number, readonly machine: string}} LeaseContext
 */

/**
 * The header of a park note: the one source of its keys, rendered and parsed from here.
 * @typedef {object} ParkFields
 * @property {string} id
 * @property {string} name
 * @property {string} nextAction
 * @property {string} plan
 * @property {string} job
 * @property {string} row
 * @property {string} branch
 * @property {readonly string[]} revisions
 * @property {readonly string[]} ownedPaths
 * @property {readonly string[]} tasks
 * @property {readonly SessionRef[]} sessions
 * @property {string} origin
 * @property {string} readiness
 * @property {string} written
 */

/**
 * The facts under the header. `purpose` is empty until a brief kind fills it.
 * @typedef {object} ParkBody
 * @property {string} goal
 * @property {readonly string[]} decisions
 * @property {readonly string[]} answers
 * @property {readonly string[]} checks
 * @property {readonly string[]} unverified
 * @property {readonly string[]} agents
 * @property {readonly (readonly [string, string])[]} purpose
 */

/**
 * One job line of `PLAN.md`: the structure of a job, never its state (ADR 0028 D08).
 * @typedef {object} JobLine
 * @property {string} id
 * @property {number} number
 * @property {string} label
 * @property {readonly string[]} tasks
 * @property {readonly string[]} after
 * @property {readonly string[]} paths
 * @property {string} harness
 * @property {string} result
 */

/**
 * The header of `PLAN.md`: the kit's id, name, title and the tasks it carries.
 * @typedef {{readonly id: string, readonly name: string, readonly title: string, readonly tasks: readonly string[]}} PlanHeader
 */

/**
 * A plan: its header and its job lines.
 * @typedef {{readonly header: PlanHeader, readonly jobs: readonly JobLine[]}} Plan
 */

/**
 * A job's own file `JOB.md`: its steps with their done marks, and whether it is done.
 * @typedef {{readonly header: ParkFields, readonly steps: readonly (readonly [string, boolean])[], readonly done: boolean}} JobDoc
 */

/**
 * One line of `list`: what a kit says of itself, read from its folder.
 * @typedef {object} KitSummary
 * @property {string} id
 * @property {string} name
 * @property {string} state
 * @property {string} plan
 * @property {string} nextAction
 * @property {number} decisions
 * @property {string} branch
 * @property {number | null} ageDays
 * @property {string} [unreadable] why the kit's files could not be read; the other fields are then empty
 */

/**
 * One job line of `list`: what a job says of itself, read from its folder.
 * @typedef {object} JobSummary
 * @property {string} id
 * @property {string} name
 * @property {string} state
 * @property {readonly string[]} tasks
 * @property {string} nextAction
 * @property {string} branch
 * @property {number | null} ageDays
 */

/**
 * The filters of `list`; an empty one matches every kit.
 * @typedef {{readonly plan: string, readonly task: string, readonly state: string, readonly closed: boolean}} ListQuery
 */

/**
 * The keys of one flat header: their order, which hold a list, and which are read and ignored.
 * @typedef {{readonly order: readonly string[], readonly listKeys: readonly string[], readonly legacy: readonly string[]}} HeaderSpec
 */

const PROG = "park.mjs";

const USAGE = `usage: ${PROG} [-h] {write,unpark,digest,list,hold,release,job,active,close,export,local-id} ...

Park work into a kit and resume it.

commands:
  write ID --name N --goal G --next X [--plan ID] [--row ID] [--owned-path P]... [--check C]...
        [--unverified U]... [--decision D]... [--answer A]... [--agent A]... [--readiness R]
        [--origin O] [--harness H] [--session-id S]
                        Park a piece of work.
  unpark ID [--harness H] [--session-id S]
                        Resume a parked kit.
  digest ID [--cap N]   Print the capped digest.
  list [--plan ID] [--task ID] [--state S] [--closed]
                        List the kits.
  hold ID [--number N] [--takeover] [--harness H] [--session-id S]
                        Take the lease of a unit.
  release ID [--number N]
                        Release the lease of a unit.
  job ID --number N [--step S]... [--done] [--harness H] [--session-id S]
                        Write a job's own file.
  active                Print the unit this session is in.
  close ID [--harness H] [--session-id S]
                        Close a kit and move it to the closed folder.
  export ID --out FILE  Write the kit to one bundle file.
  local-id              Print the next free local id, _T<n>.

Every command takes --root DIR (or --project-root DIR): the project root. Defaults to the nearest
parent holding AGENTS.md beside the dev layer. Every command also takes --machine M: the machine
this session acts as. Defaults to the host's name.

options:
  -h, --help            show this help message and exit
`;

const SECONDS_PER_DAY = 86400;
const SECONDS_PER_HOUR = 3600;
const PARK_FILE = "PARK.md";
const RESUME_FILE = "RESUME.md";
const PLAN_FILE = "PLAN.md";
const JOB_FILE = "JOB.md";
const HOLDER_FILE = "HOLDER";
const SESSIONS_FILE = "SESSIONS";
const HEADER_FENCE = "---";
const SESSION_PARTS = 3; // harness|session_id|machine
const SLUG_MAX = 40;
const GIT_TIMEOUT_MS = 10_000;
const GIT_REVISIONS = 5;
const STEPS_HEADING = "## Steps";
const DONE_MARKER = "done";
const STEP_UNDONE = "- [ ] ";
const STEP_DONE = "- [x] ";
const JOBS_DIR = "jobs";
const CLOSED_DIR = ".closed";
const WORKTREES_DIR = ".worktrees";
const TASK_SEPARATOR = "·";
const FIELD_SEPARATOR = ",";
const PATH_SEPARATOR = "/";
const JOBS_HEADING = "Jobs";
const LINE_BREAKS_RE = /[\r\n]+/g;
const JOB_SOURCE_PARTS = 4; // kit folder, `jobs`, job folder, `JOB.md`

// Python's `$` also matches before a final newline, so `\n?$` keeps the twin's answer for a value
// that ends in one; `\p{Nd}` is Python's `\d`; `.` is `[^\n]` because Python's `.` takes `\r`.
const ID_RE = /^(?:[A-Z]\p{Nd}+|_T\p{Nd}+)\n?$/u; // ADR 0002 typed id, and a local id's _T<n> (ADR 0028 D12)
const JOB_ID_RE = /^((?:[A-Z]\p{Nd}+|_T\p{Nd}+))\.(\p{Nd}+)\n?$/u;
const NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*\n?$/;
const KIT_RE = /^([A-Z]\p{Nd}+|_T\p{Nd}+)-([a-z0-9]+(?:-[a-z0-9]+)*)\n?$/u;
const KEY_RE = /^([a-z_]+):(?: ([^\n]*))?$/;
const PURPOSE_KEY_RE = /^[a-z][a-z0-9_]*\n?$/;
const SLUG_RE = /[^a-z0-9]+/g;
const LOCAL_ID_RE = /^_T(\p{Nd}+)\n?$/u;
// The retired local index, in `<dev root>/.local/`, and one of its rows: `- _T6 · ...`.
const LEGACY_INDEX_FILE = "TASKS.md";
const LEGACY_ROW_RE = /^- _T([0-9]+)(?:[ \t]|$)/;
const WORKTREE_TAIL_RE = /^\p{Nd}+$/u;
// `datetime.strptime("%Y-%m-%dT%H:%M:%SZ")`: the widths and ranges its directives accept.
const STAMP_RE =
  /^(\d{4})-(1[0-2]|0[1-9]|[1-9])-(3[01]|[12]\d|0[1-9]|[1-9]| [1-9])T(2[0-3]|[01]\d|\d):([0-5]\d|\d):(6[01]|[0-5]\d|\d)Z$/;

// Header keys in their written order, and which of them hold a list: the one table the renderer and
// the parser share. `nextAction` is written as `next`.
const SCALAR_KEYS = ["id", "name", "plan", "job", "row", "branch", "next", "origin", "readiness", "written"];
const LIST_KEYS = ["revisions", "owned_paths", "tasks", "sessions"];
const HEADER_ORDER = [
  "id",
  "name",
  "plan",
  "job",
  "row",
  "branch",
  "revisions",
  "owned_paths",
  "tasks",
  "next",
  "sessions",
  "origin",
  "readiness",
  "written",
];
// The keys of a note written before ADR 0028 D09: read and ignored, never written again.
const LEGACY_KEYS = ["state", "peers"];
// The keys of the lease file `HOLDER`, in their written order.
const LEASE_KEYS = ["harness", "session", "machine", "worktree", "written"];

/**
 * The header of a park note and the header of a lease: the two flat formats the helper reads.
 * @type {HeaderSpec}
 */
export const NOTE_HEADER = Object.freeze({ order: HEADER_ORDER, listKeys: LIST_KEYS, legacy: LEGACY_KEYS });
/** @type {HeaderSpec} */
export const LEASE_HEADER = Object.freeze({ order: LEASE_KEYS, listKeys: [], legacy: [] });

/** A failure the command line reports as one line on stderr with exit 1. */
export class ParkError extends Error {
  /**
   * @param {string} message
   */
  constructor(message) {
    super(message);
    this.name = "ParkError";
  }
}

/**
 * The header fields with the dataclass's defaults filled in.
 * @param {Pick<ParkFields, "id" | "name" | "nextAction"> & Partial<ParkFields>} init
 * @returns {ParkFields}
 */
export function parkFields(init) {
  return Object.freeze({
    plan: "",
    job: "",
    row: "",
    branch: "",
    revisions: Object.freeze([]),
    ownedPaths: Object.freeze([]),
    tasks: Object.freeze([]),
    sessions: Object.freeze([]),
    origin: "",
    readiness: "",
    written: "",
    ...init,
  });
}

/**
 * The body with the dataclass's defaults filled in.
 * @param {Pick<ParkBody, "goal"> & Partial<ParkBody>} init
 * @returns {ParkBody}
 */
export function parkBody(init) {
  return Object.freeze({
    decisions: Object.freeze([]),
    answers: Object.freeze([]),
    checks: Object.freeze([]),
    unverified: Object.freeze([]),
    agents: Object.freeze([]),
    purpose: Object.freeze([]),
    ...init,
  });
}

/**
 * The tool's texts (`park.json`), read on the call that needs them.
 * @returns {ParkData}
 */
function _texts() {
  return /** @type {ParkData} */ (read(pyPath(embeddedTreeRoot(), "tools", "park", "park.json")));
}

/**
 * A `ParkError` from the stored message `errors.<code>`, with its placeholders filled.
 * @param {ParkData} texts
 * @param {string} code
 * @param {Record<string, unknown>} [values]
 * @returns {ParkError}
 */
function _error(texts, code, values = {}) {
  const strings = Object.fromEntries(Object.entries(values).map(([name, value]) => [name, String(value)]));
  return new ParkError(fill(texts.errors[code], strings));
}

/**
 * The four derived states, by their short names.
 * @param {ParkData} texts
 * @returns {ParkData["states"]}
 */
function _states(texts) {
  return texts.states;
}

/**
 * `path` as the helper prints it: from `root` when it lies inside, as it is when it does not.
 *
 * The kits of a linked worktree live in the main checkout (ADR 0028 D12), outside the session's
 * root, so a path there is printed absolute rather than refused.
 * @param {string} path
 * @param {string} root
 * @returns {string}
 */
function _displayPath(path, root) {
  if (!isRelativeTo(path, root)) {
    return path;
  }
  return path === root ? "." : posix.relative(root, path);
}

/**
 * `sorted` by code point: the order Python compares strings in, not UTF-16 units.
 * @param {string} left
 * @param {string} right
 * @returns {number}
 */
function _compareCodePoints(left, right) {
  const a = Array.from(left);
  const b = Array.from(right);
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    const difference = (a[index].codePointAt(0) ?? 0) - (b[index].codePointAt(0) ?? 0);
    if (difference !== 0) {
      return difference;
    }
  }
  return a.length - b.length;
}

/**
 * `sorted` of `Path` objects: component by component, each by code point, as `PurePath` compares.
 * @param {string} left a POSIX path relative to a common base
 * @param {string} right
 * @returns {number}
 */
function _comparePaths(left, right) {
  const a = left.split("/");
  const b = right.split("/");
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    const difference = _compareCodePoints(a[index], b[index]);
    if (difference !== 0) {
      return difference;
    }
  }
  return a.length - b.length;
}

// --------------------------------------------------------------------------------------
// validation: at the boundary, so the renderer and every reader can trust the types
// --------------------------------------------------------------------------------------

/**
 * A scalar holds one line with no surrounding whitespace, so it survives a round trip.
 * @param {string} value
 * @param {string} label
 * @param {ParkData} texts
 */
function _checkLine(value, label, texts) {
  if (value.includes("\n") || value.includes("\r") || value !== pyStrip(value)) {
    throw _error(texts, "bad_line", { label });
  }
}

/**
 * @param {string} value
 * @param {string} label
 * @param {ParkData} texts
 */
function _checkId(value, label, texts) {
  if (!ID_RE.test(value)) {
    throw _error(texts, "bad_id", { label, value });
  }
}

/**
 * @param {string} value
 * @param {string} label
 * @param {ParkData} texts
 */
function _checkJobId(value, label, texts) {
  if (!JOB_ID_RE.test(value)) {
    throw _error(texts, "bad_job_id", { label, value });
  }
}

/**
 * @param {readonly string[]} items
 * @param {string} label
 * @param {ParkData} texts
 */
function _checkItems(items, label, texts) {
  for (const item of items) {
    if (item === "") {
      throw _error(texts, "empty", { label });
    }
    _checkLine(item, label, texts);
  }
}

/**
 * @param {SessionRef} session
 * @param {ParkData} texts
 */
function _checkSession(session, texts) {
  const parts = [session.harness, session.sessionId, session.machine];
  if (parts.some((part) => part.includes("|")) || session.harness === "") {
    throw _error(texts, "bad_session", { value: parts.join("|") });
  }
  for (const part of parts) {
    _checkLine(part, "session", texts);
  }
}

/**
 * The scalar half of `checkFields`: ids and the one-line values.
 * @param {ParkFields} fields
 * @param {ParkData} texts
 */
function _checkScalars(fields, texts) {
  _checkId(fields.id, "id", texts);
  if (!NAME_RE.test(fields.name)) {
    throw _error(texts, "bad_name", { value: fields.name });
  }
  for (const [label, value] of [
    ["plan", fields.plan],
    ["row", fields.row],
  ]) {
    if (value !== "") {
      _checkId(value, label, texts);
    }
  }
  if (fields.job !== "") {
    _checkJobId(fields.job, "job", texts);
  }
  for (const [label, value] of [
    ["branch", fields.branch],
    ["next", fields.nextAction],
    ["origin", fields.origin],
    ["readiness", fields.readiness],
    ["written", fields.written],
  ]) {
    _checkLine(value, label, texts);
  }
  if (fields.nextAction === "") {
    throw _error(texts, "empty", { label: "next" });
  }
}

/**
 * Refuse a header that would not render or parse back: a bad id or name, a multi-line scalar.
 * @param {ParkFields} fields
 * @param {ParkData} texts
 * @throws {ParkError} a field breaks the header's contract; the message names the field
 */
export function checkFields(fields, texts) {
  _checkScalars(fields, texts);
  _checkItems(fields.revisions, "revision", texts);
  _checkItems(fields.ownedPaths, "owned path", texts);
  _checkItems(fields.tasks, "task", texts);
  for (const session of fields.sessions) {
    _checkSession(session, texts);
  }
}

/**
 * Refuse a body whose text would open a section or break an item line.
 * @param {ParkBody} body
 * @param {ParkData} texts
 * @throws {ParkError} the goal is empty or unstable under a round trip, or an item spans lines
 */
export function checkBody(body, texts) {
  if (body.goal === "") {
    throw _error(texts, "empty", { label: "goal" });
  }
  if (body.goal !== pyStrip(body.goal)) {
    throw _error(texts, "bad_text", { label: "goal" });
  }
  if (body.goal.split("\n").some((line) => line.startsWith("## "))) {
    throw _error(texts, "bad_heading", { label: "goal" });
  }
  for (const [label, items] of [
    ["decision", body.decisions],
    ["answer", body.answers],
    ["check", body.checks],
    ["unverified", body.unverified],
    ["agent", body.agents],
  ]) {
    _checkItems(/** @type {readonly string[]} */ (items), /** @type {string} */ (label), texts);
  }
  for (const [key, value] of body.purpose) {
    if (!PURPOSE_KEY_RE.test(key)) {
      throw _error(texts, "bad_key", { value: key });
    }
    if (value === "") {
      throw _error(texts, "empty", { label: `purpose ${key}` });
    }
    _checkLine(value, `purpose ${key}`, texts);
  }
}

// --------------------------------------------------------------------------------------
// the park note: header and body, rendered from the types and parsed back into them
// --------------------------------------------------------------------------------------

/**
 * @param {SessionRef} session
 * @returns {string}
 */
function _sessionText(session) {
  return `${session.harness}|${session.sessionId}|${session.machine}`;
}

/**
 * @param {string} key
 * @param {string} value
 * @returns {string}
 */
function _scalarLine(key, value) {
  return value === "" ? `${key}:` : `${key}: ${value}`;
}

/**
 * The header of `fields`: the fenced `key: value` block that opens `PARK.md`.
 *
 * The fields are trusted here; `checkFields` is the gate that precedes every caller.
 * @param {ParkFields} fields
 * @returns {string}
 */
export function renderHeader(fields) {
  /** @type {Record<string, string>} */
  const scalars = {
    id: fields.id,
    name: fields.name,
    plan: fields.plan,
    job: fields.job,
    row: fields.row,
    branch: fields.branch,
    next: fields.nextAction,
    origin: fields.origin,
    readiness: fields.readiness,
    written: fields.written,
  };
  /** @type {Record<string, readonly string[]>} */
  const lists = {
    revisions: fields.revisions,
    owned_paths: fields.ownedPaths,
    tasks: fields.tasks,
    sessions: fields.sessions.map(_sessionText),
  };
  const lines = [HEADER_FENCE];
  for (const key of HEADER_ORDER) {
    if (SCALAR_KEYS.includes(key)) {
      lines.push(_scalarLine(key, scalars[key]));
    } else {
      lines.push(`${key}:`, ...lists[key].map((item) => `  - ${item}`));
    }
  }
  lines.push(HEADER_FENCE);
  return `${lines.join("\n")}\n`;
}

/**
 * The header lines of a note and the text after its closing fence (the body, untouched).
 * @param {string} text
 * @param {string} source
 * @param {ParkData} texts
 * @returns {{header: string[], rest: string}}
 */
function _splitNote(text, source, texts) {
  const lines = text.split("\n");
  if (lines[0] !== HEADER_FENCE) {
    throw _error(texts, "header_missing", { path: source });
  }
  for (let index = 1; index < lines.length; index += 1) {
    if (lines[index] === HEADER_FENCE) {
      return { header: lines.slice(1, index), rest: lines.slice(index + 1).join("\n") };
    }
  }
  throw _error(texts, "header_missing", { path: source });
}

/**
 * @param {string} text
 * @param {ParkData} texts
 * @returns {SessionRef}
 */
function _parseSession(text, texts) {
  const parts = text.split("|");
  if (parts.length !== SESSION_PARTS) {
    throw _error(texts, "bad_session", { value: text });
  }
  return { harness: parts[0], sessionId: parts[1], machine: parts[2] };
}

/**
 * One `key: value` or `key:` line of the header, stored into `values`.
 * @param {Map<string, string | string[]>} values
 * @param {string} line
 * @param {number} number the 1-based line number in the header
 * @param {{source: string, texts: ParkData, spec: HeaderSpec}} site where the header is read, for the errors, and its keys
 * @returns {{opened: string | null, legacyList: boolean}} the list key the line opened (`null` for a
 *   scalar), and whether it was a retired list key, read and ignored with the items below it
 */
function _headerEntry(values, line, number, site) {
  const { source, texts, spec } = site;
  const match = KEY_RE.exec(line);
  if (match === null) {
    throw _error(texts, "header_line", { path: source, line: number });
  }
  const key = match[1];
  const value = match[2] ?? "";
  if (spec.legacy.includes(key)) {
    return { opened: null, legacyList: value === "" };
  }
  if (!spec.order.includes(key) || values.has(key)) {
    throw _error(texts, "header_key", { path: source, key });
  }
  if (spec.listKeys.includes(key)) {
    if (value !== "") {
      throw _error(texts, "header_scalar_list", { path: source, key });
    }
    values.set(key, []);
    return { opened: key, legacyList: false };
  }
  values.set(key, value);
  return { opened: null, legacyList: false };
}

/**
 * The header lines as `key -> scalar | list`, each key known and once, each line well-formed.
 *
 * A retired key is read and ignored, as the Python reference does; a retired list takes its items
 * with it.
 * @param {readonly string[]} lines
 * @param {string} source
 * @param {ParkData} texts
 * @param {HeaderSpec} [spec]
 * @returns {Map<string, string | string[]>}
 */
function _headerValues(lines, source, texts, spec = NOTE_HEADER) {
  /** @type {Map<string, string | string[]>} */
  const values = new Map();
  /** @type {string | null} */
  let current = null;
  let legacyList = false;
  for (const [offset, line] of lines.entries()) {
    if (line.startsWith("  - ")) {
      if (legacyList) {
        continue;
      }
      const open = current === null || !spec.listKeys.includes(current) ? undefined : values.get(current);
      if (!Array.isArray(open)) {
        throw _error(texts, "header_item", { path: source, line: offset + 1 });
      }
      open.push(line.slice(4));
    } else {
      const entry = _headerEntry(values, line, offset + 1, { source, texts, spec });
      current = entry.opened;
      legacyList = entry.legacyList;
    }
  }
  return values;
}

/**
 * @param {Map<string, string | string[]>} values
 * @param {string} key
 * @returns {string}
 */
function _scalar(values, key) {
  const value = values.get(key) ?? "";
  return /** @type {string} */ (value);
}

/**
 * @param {Map<string, string | string[]>} values
 * @param {string} key
 * @returns {string[]}
 */
function _listed(values, key) {
  return [.../** @type {string[]} */ (values.get(key) ?? [])];
}

/**
 * The `ParkFields` a note's header declares; `source` names the note in the error.
 * @param {string} text
 * @param {string} source
 * @param {ParkData} texts
 * @returns {ParkFields}
 * @throws {ParkError} no header, a malformed or unknown line, or a field that fails `checkFields`
 */
export function parseHeader(text, source, texts) {
  const { header } = _splitNote(text, source, texts);
  const values = _headerValues(header, source, texts);
  for (const key of ["id", "name", "next"]) {
    if (!values.get(key)) {
      throw _error(texts, "header_required", { path: source, key });
    }
  }
  const fields = parkFields({
    id: _scalar(values, "id"),
    name: _scalar(values, "name"),
    nextAction: _scalar(values, "next"),
    plan: _scalar(values, "plan"),
    job: _scalar(values, "job"),
    row: _scalar(values, "row"),
    branch: _scalar(values, "branch"),
    revisions: _listed(values, "revisions"),
    ownedPaths: _listed(values, "owned_paths"),
    tasks: _listed(values, "tasks"),
    sessions: _listed(values, "sessions").map((item) => _parseSession(item, texts)),
    origin: _scalar(values, "origin"),
    readiness: _scalar(values, "readiness"),
    written: _scalar(values, "written"),
  });
  try {
    checkFields(fields, texts);
  } catch (exc) {
    if (!(exc instanceof ParkError)) {
      throw exc;
    }
    throw _error(texts, "header_invalid", { path: source, reason: exc.message });
  }
  return fields;
}

/**
 * @param {string} heading
 * @param {readonly string[]} content
 * @returns {string[]}
 */
function _section(heading, content) {
  return [`## ${heading}`, "", ...content, ""];
}

/**
 * @param {readonly string[]} items
 * @param {ParkData} texts
 * @returns {string[]}
 */
function _bullets(items, texts) {
  return items.length > 0 ? items.map((item) => `- ${item}`) : [texts.none_marker];
}

/**
 * The Markdown body of a note: the sections of ADR 0021 D01 and 0028 D03, then the purpose block.
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {ParkData} texts
 * @returns {string}
 */
function _renderBody(fields, body, texts) {
  const headings = texts.headings;
  const lines = [fill(texts.note.title, { kit: `${fields.id}-${fields.name}` }), ""];
  lines.push(..._section(headings.goal, body.goal.split("\n")));
  lines.push(..._section(headings.decisions, _bullets(body.decisions, texts)));
  lines.push(..._section(headings.answers, _bullets(body.answers, texts)));
  lines.push(..._section(headings.checks, _bullets(body.checks, texts)));
  lines.push(..._section(headings.unverified, _bullets(body.unverified, texts)));
  lines.push(..._section(headings.agents, _bullets(body.agents, texts)));
  lines.push(..._section(headings.next, [fields.nextAction]));
  if (body.purpose.length > 0) {
    lines.push(
      ..._section(
        headings.purpose,
        body.purpose.map(([key, value]) => `- ${key}: ${value}`),
      ),
    );
  }
  return `${rstripChars(lines.join("\n"), "\n")}\n`;
}

/**
 * The whole `PARK.md`: header, a blank line, body.
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} the fields or the body fail their checks
 */
export function renderNote(fields, body, texts) {
  checkFields(fields, texts);
  checkBody(body, texts);
  return `${renderHeader(fields)}\n${_renderBody(fields, body, texts)}`;
}

/**
 * The `## ` sections of a body by heading (the first of a repeated heading wins).
 * @param {string} text
 * @returns {Map<string, string[]>}
 */
function _sections(text) {
  /** @type {Map<string, string[]>} */
  const sections = new Map();
  /** @type {string[] | null} */
  let current = null;
  for (const line of text.split("\n")) {
    if (line.startsWith("## ")) {
      const heading = pyStrip(line.slice(3));
      current = null;
      if (!sections.has(heading)) {
        current = [];
        sections.set(heading, current);
      }
    } else if (current !== null) {
      current.push(line);
    }
  }
  return sections;
}

/**
 * @param {readonly string[]} lines
 * @returns {string[]}
 */
function _items(lines) {
  return lines.filter((line) => line.startsWith("- ")).map((line) => line.slice(2));
}

/**
 * The `ParkBody` of a note's text after its header; a section that is missing reads as empty.
 * @param {string} text
 * @param {ParkData} texts
 * @returns {ParkBody}
 */
function _parseBody(text, texts) {
  const headings = texts.headings;
  const sections = _sections(text);
  /** @param {string} heading */
  const items = (heading) => _items(sections.get(heading) ?? []);
  /** @type {[string, string][]} */
  const purpose = items(headings.purpose).map((item) => {
    const at = item.indexOf(": ");
    return at < 0 ? [item, ""] : [item.slice(0, at), item.slice(at + 2)];
  });
  return parkBody({
    goal: (sections.get(headings.goal) ?? []).join("\n").replace(/^\n+|\n+$/g, ""),
    decisions: items(headings.decisions),
    answers: items(headings.answers),
    checks: items(headings.checks),
    unverified: items(headings.unverified),
    agents: items(headings.agents),
    purpose,
  });
}

/**
 * The fields and the body of a whole `PARK.md`.
 * @param {string} text
 * @param {string} source
 * @param {ParkData} texts
 * @returns {{fields: ParkFields, body: ParkBody}}
 */
export function parseNote(text, source, texts) {
  const fields = parseHeader(text, source, texts);
  const { rest } = _splitNote(text, source, texts);
  return { fields, body: _parseBody(rest, texts) };
}

/**
 * `RESUME.md`: the harness-neutral prompt, generated from the note and nothing else.
 *
 * It names paths from the project root and the helper's own command, never an absolute path or a
 * slash command, and carries the retirement text of ADR 0021 D05.
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {string} parkPath
 * @param {ParkData} texts
 * @returns {string}
 */
export function renderResume(fields, body, parkPath, texts) {
  const resume = texts.resume;
  const values = {
    kit: `${fields.id}-${fields.name}`,
    id: fields.id,
    park_path: parkPath,
    command: texts.invocation,
  };
  /** @type {string[][]} */
  const blocks = [
    [fill(resume.title, values)],
    [resume.intro],
    resume.steps.map((step) => fill(step, values)),
    [resume.next_heading, "", fields.nextAction],
    [
      resume.decisions_heading,
      "",
      ...(body.decisions.length > 0 ? body.decisions.map((item) => `- ${item}`) : [resume.decisions_none]),
    ],
    [resume.retirement_heading, "", resume.retirement[0]],
    ...resume.retirement.slice(1).map((line) => [line]),
  ];
  return `${blocks.map((block) => block.join("\n")).join("\n\n")}\n`;
}

// --------------------------------------------------------------------------------------
// the digest: what SessionStart returns after a compaction (capped, cut at a whole line)
// --------------------------------------------------------------------------------------

/**
 * The digest before the cap: the summary, the goal, the next action, the decisions and the answers.
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {string} state
 * @param {ParkData} texts
 * @returns {string[]}
 */
export function digestLines(fields, body, state, texts) {
  const spec = texts.digest;
  const lines = [fill(spec.title, { kit: `${fields.id}-${fields.name}`, state })];
  for (const [key, value] of [
    ["plan", fields.plan],
    ["job", fields.job],
    ["row", fields.row],
    ["branch", fields.branch],
    ["readiness", fields.readiness],
  ]) {
    if (value !== "") {
      lines.push(fill(spec.field, { key, value }));
    }
  }
  const goal = body.goal.split("\n");
  lines.push(fill(spec.goal, { text: goal[0] }));
  lines.push(...goal.slice(1).map((line) => `  ${line}`));
  lines.push(fill(spec.next, { text: fields.nextAction }));
  for (const [items, head, none] of [
    [body.decisions, spec.decisions, spec.decisions_none],
    [body.answers, spec.answers, spec.answers_none],
  ]) {
    const listed = /** @type {readonly string[]} */ (items);
    if (listed.length > 0) {
      lines.push(/** @type {string} */ (head), ...listed.map((item) => `- ${item}`));
    } else {
      lines.push(/** @type {string} */ (none));
    }
  }
  return lines;
}

/**
 * The fields and the body of the kit's `PARK.md`; a kit without one was never parked.
 * @param {string} kit
 * @param {ParkData} texts
 * @returns {{fields: ParkFields, body: ParkBody}}
 * @throws {ParkError} the kit has no `PARK.md`, or its note does not parse
 */
export function readNote(kit, texts) {
  const note = pyPath(kit, PARK_FILE);
  const name = posix.basename(kit);
  if (!isFile(note)) {
    throw _error(texts, "never_parked", { kit: name });
  }
  return parseNote(readText(note), `${name}/${PARK_FILE}`, texts);
}

/**
 * The capped digest of a kit's note: whole lines up to `cap` characters, then the overflow line.
 *
 * `cap` counts the code points of the lines kept, newline included; the overflow line
 * (`… N more lines in <path>`) is appended after them and is not counted. With `root` the
 * path is the note's path from the project root, otherwise `<kit name>/PARK.md`.
 * @param {string} kit
 * @param {number} cap
 * @param {string | null} [root]
 * @param {ParkData | null} [data] the tool's texts; read from `park.json` when omitted
 * @returns {string}
 * @throws {ParkError} the kit was never parked or its note does not parse
 */
export function digest(kit, cap, root = null, data = null) {
  const texts = data ?? _texts();
  const { fields, body } = readNote(kit, texts);
  const context = { now: Date.now() / 1000, staleHours: texts.stale_after_hours, machine: "" };
  const lines = digestLines(fields, body, kitState(kit, texts, context), texts);
  /** @type {string[]} */
  const kept = [];
  let used = 0;
  for (const line of lines) {
    const size = pyLen(line) + 1;
    if (used + size > cap) {
      break;
    }
    kept.push(line);
    used += size;
  }
  if (kept.length < lines.length) {
    const where = root === null ? `${posix.basename(kit)}/${PARK_FILE}` : _displayPath(pyPath(kit, PARK_FILE), root);
    kept.push(fill(texts.digest.overflow, { count: String(lines.length - kept.length), path: where }));
  }
  return kept.join("\n");
}

// --------------------------------------------------------------------------------------
// git: the branch and the revisions of the note are read, never passed by the caller
// --------------------------------------------------------------------------------------

/**
 * The output of one git command in `cwd`, or `null` when git is absent or fails.
 *
 * The output is stripped unless `strip` is false, for a listing whose first line starts with a space.
 * @param {readonly string[]} args
 * @param {string} cwd
 * @param {boolean} [strip]
 * @returns {string | null}
 */
function _git(args, cwd, strip = true) {
  const done = spawnSync("git", [...args], {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    timeout: GIT_TIMEOUT_MS,
  });
  if (done.error !== undefined || done.status !== 0) {
    return null; // no git, a timeout, a missing cwd, or a failing command
  }
  return strip ? pyStrip(decodeUtf8(done.stdout)) : decodeUtf8(done.stdout);
}

/**
 * The branch checked out in `cwd`, or the empty string outside a repository.
 * @param {string} cwd
 * @returns {string}
 */
export function gitBranch(cwd) {
  return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) || "";
}

/**
 * The last `count` revisions of `cwd`, newest first; empty outside a repository.
 * @param {string} cwd
 * @param {number} [count]
 * @returns {string[]}
 */
export function gitRevisions(cwd, count = GIT_REVISIONS) {
  const out = _git(["log", `-${count}`, "--format=%h"], cwd);
  if (!out) {
    return [];
  }
  return out.split("\n").filter((line) => line !== "");
}

/**
 * The paths with uncommitted changes in `worktree`, tracked or not, or `null` when unreadable.
 *
 * `null` means the worktree is unnamed, is not a folder here (a lease from another machine), or git
 * cannot list it; an empty list means it is clean.
 * @param {string} worktree
 * @returns {string[] | null}
 */
export function gitUncommittedPaths(worktree) {
  if (worktree === "" || !isDir(worktree)) {
    return null;
  }
  const out = _git(["status", "--porcelain", "--untracked-files=all"], worktree, false);
  if (out === null) {
    return null;
  }
  return out
    .split("\n")
    .filter((line) => line !== "")
    .map((line) => line.slice(3));
}

/**
 * The epoch seconds as a stamp: UTC, to the second (`2026-01-02T03:04:05Z`).
 * @param {number} seconds
 * @returns {string}
 */
function _stampOf(seconds) {
  return `${new Date(Math.floor(seconds) * 1000).toISOString().slice(0, 19)}Z`;
}

/**
 * The current time as a stamp the note records: UTC, to the second.
 * @returns {string}
 */
export function nowStamp() {
  return _stampOf(Date.now() / 1000);
}

// --------------------------------------------------------------------------------------
// the lease: one holder per unit, created exclusively, judged stale on read
// --------------------------------------------------------------------------------------

/**
 * Whether the holder names a session: a harness and a session id, the pair a note can carry.
 * @param {Holder} holder
 * @returns {boolean}
 */
export function holderIdentified(holder) {
  return holder.harness !== "" && holder.sessionId !== "";
}

/**
 * Whether two holders are the same session on the same machine.
 *
 * An anonymous holder, one that names no harness or no session, is the same as nobody: two of them
 * cannot be told apart, so neither is taken for the other (ADR 0028 D09).
 * @param {Holder} holder
 * @param {Holder} other
 * @returns {boolean}
 */
export function holderSameAs(holder, other) {
  if (!holderIdentified(holder) || !holderIdentified(other)) {
    return false;
  }
  return holder.harness === other.harness && holder.sessionId === other.sessionId && holder.machine === other.machine;
}

/**
 * The holder as one line of text: harness, session, machine and worktree.
 * @param {Holder} holder
 * @returns {string}
 */
export function holderLabel(holder) {
  const parts = [holder.harness || "?", holder.sessionId || "?", holder.machine || "?"];
  if (holder.worktree) {
    parts.push(holder.worktree);
  }
  return parts.join(" ");
}

/**
 * How long ago a lease was last written, in seconds.
 * @param {Lease} lease
 * @param {number} now
 * @returns {number}
 */
export function leaseAgeSeconds(lease, now) {
  return Math.max(0, now - lease.written);
}

/**
 * @param {string} unit
 * @returns {string}
 */
function _leasePath(unit) {
  return pyPath(unit, HOLDER_FILE);
}

/**
 * The lease file `HOLDER`: its holder and the time of its last write.
 * @param {Lease} lease
 * @returns {string}
 */
export function renderLease(lease) {
  const holder = lease.holder;
  /** @type {Record<string, string>} */
  const values = {
    harness: holder.harness,
    session: holder.sessionId,
    machine: holder.machine,
    worktree: holder.worktree,
    written: _stampOf(lease.written),
  };
  const lines = [HEADER_FENCE, ...LEASE_KEYS.map((key) => _scalarLine(key, values[key])), HEADER_FENCE];
  return `${lines.join("\n")}\n`;
}

/**
 * The epoch seconds of an ISO stamp, or `0` when it is not one.
 * @param {string} value
 * @returns {number}
 */
function _parseStamp(value) {
  const match = STAMP_RE.exec(value);
  if (match === null) {
    return 0;
  }
  const [year, month, day, hour, minute, second] = [
    match[1],
    match[2],
    match[3].trim(),
    match[4],
    match[5],
    match[6],
  ].map(Number);
  const moment = new Date(0);
  moment.setUTCFullYear(year, month - 1, day);
  moment.setUTCHours(hour, minute, second, 0);
  const valid =
    year >= 1 &&
    second <= 59 &&
    moment.getUTCFullYear() === year &&
    moment.getUTCMonth() === month - 1 &&
    moment.getUTCDate() === day &&
    moment.getUTCHours() === hour &&
    moment.getUTCMinutes() === minute &&
    moment.getUTCSeconds() === second;
  return valid ? moment.getTime() / 1000 : 0;
}

/**
 * The lease a `HOLDER` file declares.
 * @param {string} text
 * @param {string} source
 * @param {ParkData} texts
 * @returns {Lease}
 * @throws {ParkError} the file has no header, or a line is malformed
 */
export function parseLease(text, source, texts) {
  const { header } = _splitNote(text, source, texts);
  const values = _headerValues(header, source, texts, LEASE_HEADER);
  const holder = {
    harness: String(values.get("harness") ?? ""),
    sessionId: String(values.get("session") ?? ""),
    machine: String(values.get("machine") ?? ""),
    worktree: String(values.get("worktree") ?? ""),
  };
  return { holder, written: _parseStamp(String(values.get("written") ?? "")) };
}

/**
 * The lease of a unit, or `null` when the unit is free.
 * @param {string} unit
 * @param {ParkData} texts
 * @returns {Lease | null}
 */
export function readLease(unit, texts) {
  const path = _leasePath(unit);
  if (!isFile(path)) {
    return null;
  }
  return parseLease(readText(path), `${posix.basename(unit)}/${HOLDER_FILE}`, texts);
}

/**
 * Whether a lease is stale: written on another machine, or older than the threshold.
 *
 * A lease that came with a copied kit names another machine, and is stale at once.
 * @param {Lease} lease
 * @param {LeaseContext} context
 * @returns {boolean}
 */
export function leaseIsStale(lease, context) {
  if (context.machine && lease.holder.machine && lease.holder.machine !== context.machine) {
    return true;
  }
  return leaseAgeSeconds(lease, context.now) > context.staleHours * SECONDS_PER_HOUR;
}

/**
 * Create `path` with `text`, exclusively: an existing file is never overwritten.
 * @param {string} path
 * @param {string} text
 */
function _writeExclusive(path, text) {
  const descriptor = fs.openSync(path, "wx", 0o644);
  try {
    fs.writeSync(descriptor, encodeUtf8(text));
  } finally {
    fs.closeSync(descriptor);
  }
}

/**
 * Put `text` in `path`, replacing what was there, so a reader sees the old file or the new one.
 *
 * The temporary file has a name of its own and sits beside `path`, so two writers never share it
 * and the rename is atomic.
 * @param {string} path
 * @param {string} text
 */
function _writeAtomically(path, text) {
  const temporary = pyPath(
    dirname(path),
    `.${posix.basename(path)}.${process.pid}.${randomUUID().replaceAll("-", "")}.tmp`,
  );
  try {
    const handle = fs.openSync(temporary, "wx");
    try {
      fs.writeSync(handle, encodeUtf8(text));
      fs.fsyncSync(handle);
    } finally {
      fs.closeSync(handle);
    }
    fs.renameSync(temporary, path);
  } finally {
    unlinkMissingOk(temporary);
  }
}

/**
 * Renew the time of a lease the caller already holds.
 * @param {string} unit
 * @param {Lease} lease
 * @param {number} now
 */
export function renewLease(unit, lease, now) {
  _writeAtomically(_leasePath(unit), renderLease({ holder: lease.holder, written: now }));
}

/**
 * Release the lease of a unit; the note stays.
 * @param {string} unit
 */
export function releaseLease(unit) {
  unlinkMissingOk(_leasePath(unit));
}

/**
 * Release every lease of a kit: the plan's and its jobs'.
 * @param {string} kit
 */
export function releaseLeases(kit) {
  releaseLease(kit);
  for (const folder of _jobFolders(kit)) {
    releaseLease(folder);
  }
}

/**
 * Take the lease of a unit, or refuse with the holder named.
 *
 * The file is created exclusively, so two sessions racing for it cannot both win. A lease held by
 * this same session is renewed. A lease held by another session is refused; a stale one is refused
 * too, and taken over only on the owner's word (`takeover`) — the holder it replaces is kept in the
 * note's sessions, so the takeover leaves a trace.
 * @param {string} unit
 * @param {Holder} holder
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @param {{takeover?: boolean}} [options]
 * @returns {Lease}
 * @throws {ParkError} the unit is held by another session, and the caller did not ask for a takeover
 */
export function acquireLease(unit, holder, texts, context, { takeover = false } = {}) {
  const existing = readLease(unit, texts);
  /** @type {Lease} */
  const lease = { holder, written: context.now };
  const path = _leasePath(unit);
  fs.mkdirSync(dirname(path), { recursive: true });
  if (existing === null) {
    try {
      _writeExclusive(path, renderLease(lease));
    } catch (error) {
      if (/** @type {NodeJS.ErrnoException} */ (error).code !== "EEXIST") {
        throw error;
      }
      // another session created it between the read and the create
      const winner = readLease(unit, texts);
      const label = winner !== null ? holderLabel(winner.holder) : texts.unknown_holder;
      throw _error(texts, "held", { unit: posix.basename(unit), holder: label });
    }
    return lease;
  }
  if (holderSameAs(existing.holder, holder)) {
    renewLease(unit, lease, context.now);
    return lease;
  }
  if (!takeover) {
    const code = leaseIsStale(existing, context) ? "held_stale" : "held";
    throw _error(texts, code, { unit: posix.basename(unit), holder: holderLabel(existing.holder) });
  }
  rememberHolder(unit, existing.holder, texts); // the note is read, and keeps the trace, before the lease changes
  _writeAtomically(path, renderLease(lease));
  return lease;
}

/**
 * The file that carries a unit's sessions: `PARK.md` for a kit, `JOB.md` for a job, or `null`.
 * @param {string} unit
 * @returns {string | null}
 */
function _unitNote(unit) {
  for (const name of [PARK_FILE, JOB_FILE]) {
    if (isFile(pyPath(unit, name))) {
      return pyPath(unit, name);
    }
  }
  return null;
}

/**
 * The sessions a takeover kept for a unit that had no note yet: one `harness|session|machine` per line.
 * @param {string} unit
 * @param {ParkData} texts
 * @returns {SessionRef[]}
 * @throws {ParkError} a line is not a session
 */
export function readPendingSessions(unit, texts) {
  const path = pyPath(unit, SESSIONS_FILE);
  if (!isFile(path)) {
    return [];
  }
  return readText(path)
    .split("\n")
    .filter((line) => line !== "")
    .map((line) => _parseSession(line, texts));
}

/**
 * Whether two session references are the same.
 * @param {SessionRef} one
 * @param {SessionRef} other
 * @returns {boolean}
 */
function _sameSession(one, other) {
  return one.harness === other.harness && one.sessionId === other.sessionId && one.machine === other.machine;
}

/**
 * The sessions of every group in order, each once: the earlier ones are kept, never rebuilt.
 * @param {...readonly SessionRef[]} groups
 * @returns {SessionRef[]}
 */
export function mergeSessions(...groups) {
  /** @type {SessionRef[]} */
  const merged = [];
  for (const group of groups) {
    for (const session of group) {
      if (!merged.some((known) => _sameSession(known, session))) {
        merged.push(session);
      }
    }
  }
  return merged;
}

/**
 * Keep a replaced holder in the unit's record, among the sessions.
 *
 * The header of a unit's note carries the sessions the work was done in (`PARK.md` for a kit,
 * `JOB.md` for a job); a holder that is taken over stays among them, so the note says who held the
 * unit before. A unit with no note yet keeps it in `SESSIONS` beside the lease, and the next `write`
 * merges that file into the note and removes it. The note is read first, so a note that does not
 * parse stops the takeover before anything changes, and the file is replaced atomically. A holder
 * that names no harness or no session is no session a note can carry, so it is not recorded.
 * @param {string} unit
 * @param {Holder} holder
 * @param {ParkData} texts
 * @throws {ParkError} the unit's note, or its pending sessions, do not parse
 */
export function rememberHolder(unit, holder, texts) {
  const note = _unitNote(unit);
  const pending = readPendingSessions(unit, texts);
  const record = note !== null ? _readRecord(note, unit, texts) : null;
  if (!holderIdentified(holder)) {
    return;
  }
  const session = { harness: holder.harness, sessionId: holder.sessionId, machine: holder.machine };
  const known = record !== null ? record.sessions : pending;
  if (known.some((item) => _sameSession(item, session))) {
    return;
  }
  if (note !== null && record !== null) {
    _writeAtomically(note, record.render([...known, session]));
  } else {
    _writeAtomically(
      pyPath(unit, SESSIONS_FILE),
      [...pending, session].map((item) => `${_sessionText(item)}\n`).join(""),
    );
  }
}

/**
 * A unit's note read for its sessions: the sessions it carries, and the note's text with others in
 * their place (the body or the steps untouched).
 * @param {string} note the `PARK.md` or `JOB.md` path
 * @param {string} unit
 * @param {ParkData} texts
 * @returns {{sessions: readonly SessionRef[], render: (sessions: readonly SessionRef[]) => string}}
 * @throws {ParkError} the note does not parse
 */
function _readRecord(note, unit, texts) {
  const name = posix.basename(note);
  const source = `${posix.basename(unit)}/${name}`;
  const text = readText(note);
  if (name === PARK_FILE) {
    const { fields } = parseNote(text, source, texts);
    const { rest } = _splitNote(text, source, texts);
    return { sessions: fields.sessions, render: (sessions) => `${renderHeader({ ...fields, sessions })}${rest}` };
  }
  const doc = parseJobDoc(text, source, texts);
  return {
    sessions: doc.header.sessions,
    render: (sessions) => renderJobDoc({ ...doc, header: { ...doc.header, sessions } }, texts),
  };
}

// --------------------------------------------------------------------------------------
// the plan: its header and its job lines, read from `PLAN.md`
// --------------------------------------------------------------------------------------

/**
 * The header of a plan file as `key -> value`; a file without one is empty.
 * @param {string} text
 * @returns {Map<string, string>}
 */
function _planValues(text) {
  /** @type {Map<string, string>} */
  const values = new Map();
  const lines = text.split("\n");
  if (lines[0] !== HEADER_FENCE) {
    return values;
  }
  for (let index = 1; index < lines.length; index += 1) {
    if (lines[index] === HEADER_FENCE) {
      for (const line of lines.slice(1, index)) {
        const match = KEY_RE.exec(line);
        if (match !== null) {
          values.set(match[1], match[2] ?? "");
        }
      }
      return values;
    }
  }
  return new Map();
}

/**
 * A comma-separated field as its items, trimmed.
 * @param {string} value
 * @returns {string[]}
 */
function _splitValues(value) {
  return value
    .split(FIELD_SEPARATOR)
    .map((part) => pyStrip(part))
    .filter((part) => part !== "");
}

/**
 * One job line cell as `[key, value]`: `tasks C186` and `result: text` both parse.
 * @param {string} cell
 * @returns {[string, string]}
 */
function _jobField(cell) {
  const colon = cell.indexOf(": ");
  if (colon >= 0) {
    return [pyStrip(cell.slice(0, colon)), pyStrip(cell.slice(colon + 2))];
  }
  const space = cell.indexOf(" ");
  return space < 0 ? [pyStrip(cell), ""] : [pyStrip(cell.slice(0, space)), pyStrip(cell.slice(space + 1))];
}

/**
 * One job line of a plan as a `JobLine`; a line that is not a job line is skipped (`null`).
 * @param {string} line
 * @returns {JobLine | null}
 */
export function parseJobLine(line) {
  if (!line.startsWith("- ")) {
    return null;
  }
  const cells = line
    .slice(2)
    .split(TASK_SEPARATOR)
    .map((cell) => pyStrip(cell));
  if (cells.length < 2) {
    return null;
  }
  const match = JOB_ID_RE.exec(cells[0]);
  if (match === null) {
    return null;
  }
  let tasks = /** @type {string[]} */ ([]);
  let after = /** @type {string[]} */ ([]);
  let paths = /** @type {string[]} */ ([]);
  let harness = "";
  let result = "";
  for (const cell of cells.slice(2)) {
    const [key, value] = _jobField(cell);
    if (key === "tasks") {
      tasks = _splitValues(value);
    } else if (key === "after") {
      after = _splitValues(value);
    } else if (key === "paths") {
      paths = _splitValues(value);
    } else if (key === "harness") {
      harness = value;
    } else if (key === "result") {
      result = value;
    }
  }
  return { id: cells[0], number: pyInt(match[2]), label: cells[1], tasks, after, paths, harness, result };
}

/**
 * A plan file as its header and its job lines.
 * @param {string} text
 * @returns {Plan}
 */
export function parsePlan(text) {
  const values = _planValues(text);
  const header = {
    id: values.get("id") ?? "",
    name: values.get("name") ?? "",
    title: values.get("title") ?? "",
    tasks: _splitValues(values.get("tasks") ?? ""),
  };
  const jobLines = (_sections(text).get(JOBS_HEADING) ?? []).filter((line) => pyStrip(line) !== "");
  const jobs = jobLines.map(parseJobLine).filter((job) => job !== null);
  return { header, jobs };
}

/**
 * The plan of a kit, or `null` when it has none.
 * @param {string} kit
 * @returns {Plan | null}
 */
export function readPlan(kit) {
  const path = pyPath(kit, PLAN_FILE);
  return isFile(path) ? parsePlan(readText(path)) : null;
}

/**
 * A kebab-case name for a job, taken from its label.
 * @param {string} label
 * @returns {string}
 */
export function jobSlug(label) {
  const slug = label
    .toLowerCase()
    .replace(SLUG_RE, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, SLUG_MAX).replace(/^-+|-+$/g, "");
}

/**
 * Whether two forecast paths of two jobs may touch the same file.
 * @param {string} one
 * @param {string} other
 * @returns {boolean}
 */
function _pathsOverlap(one, other) {
  const left = rstripChars(one, PATH_SEPARATOR);
  const right = rstripChars(other, PATH_SEPARATOR);
  return left === right || left.startsWith(right + PATH_SEPARATOR) || right.startsWith(left + PATH_SEPARATOR);
}

/**
 * The job ids that wait, directly or through a chain of jobs, for `jobId`.
 * @param {ReadonlyMap<string, JobLine>} jobs
 * @param {string} jobId
 * @returns {Set<string>}
 */
function _jobsWaitingFor(jobs, jobId) {
  /** @type {Set<string>} */
  const reached = new Set();
  const pending = [jobId];
  while (pending.length > 0) {
    const current = /** @type {string} */ (pending.pop());
    for (const other of jobs.values()) {
      if (other.after.includes(current) && !reached.has(other.id)) {
        reached.add(other.id);
        pending.push(other.id);
      }
    }
  }
  return reached;
}

/**
 * Whether one of the two jobs waits for the other, directly or through a chain of them.
 *
 * The chain matters: a job that waits for a job that waits for another cannot run at once with it,
 * so the pair shares no warning. Only job ids of this plan order jobs; an `after` that names a task id orders nothing here.
 * @param {JobLine} one
 * @param {JobLine} other
 * @param {Plan} plan
 * @returns {boolean}
 */
function _jobOrders(one, other, plan) {
  const jobs = new Map(plan.jobs.map((job) => [job.id, job]));
  return _jobsWaitingFor(jobs, one.id).has(other.id) || _jobsWaitingFor(jobs, other.id).has(one.id);
}

/**
 * The warnings of a plan: two jobs that may run at once and forecast the same path.
 *
 * The forecast is advice, not a fact; the owned uncommitted paths of each note are the fact.
 * @param {Plan} plan
 * @param {ParkData} texts
 * @returns {string[]}
 */
export function sharedPathWarnings(plan, texts) {
  /** @type {string[]} */
  const warnings = [];
  for (const [index, one] of plan.jobs.entries()) {
    for (const other of plan.jobs.slice(index + 1)) {
      if (_jobOrders(one, other, plan)) {
        continue;
      }
      const shared = new Set(
        one.paths.flatMap((path) => other.paths.filter((otherPath) => _pathsOverlap(path, otherPath)).map(() => path)),
      );
      for (const path of [...shared].sort(_compareCodePoints)) {
        warnings.push(fill(texts.list.warning_shared_paths, { jobs: `${one.id} ${other.id}`, path }));
      }
    }
  }
  return warnings;
}

// --------------------------------------------------------------------------------------
// a job's own file: its steps with their done marks, and whether it is done
// --------------------------------------------------------------------------------------

/**
 * The first step of a job that is not done, or the empty string when every step is done.
 * @param {JobDoc} doc
 * @returns {string}
 */
export function jobDocNextStep(doc) {
  for (const [text, isDone] of doc.steps) {
    if (!isDone) {
      return text;
    }
  }
  return "";
}

/**
 * The whole `JOB.md`: its header, its steps and, once the result is met, the done mark.
 * @param {JobDoc} doc
 * @param {ParkData} texts
 * @returns {string}
 */
export function renderJobDoc(doc, texts) {
  const lines = [rstripChars(renderHeader(doc.header), "\n"), "", STEPS_HEADING, ""];
  for (const [text, isDone] of doc.steps) {
    lines.push((isDone ? STEP_DONE : STEP_UNDONE) + text);
  }
  if (doc.steps.length === 0) {
    lines.push(texts.none_marker);
  }
  lines.push("");
  if (doc.done) {
    lines.push(DONE_MARKER, "");
  }
  return `${rstripChars(lines.join("\n"), "\n")}\n`;
}

/**
 * The `JobDoc` a `JOB.md` declares: its header, its steps and its done mark.
 * @param {string} text
 * @param {string} source
 * @param {ParkData} texts
 * @returns {JobDoc}
 * @throws {ParkError} the file has no header, or a line is malformed
 */
export function parseJobDoc(text, source, texts) {
  const header = parseHeader(text, source, texts);
  const { rest } = _splitNote(text, source, texts);
  /** @type {[string, boolean][]} */
  const steps = [];
  let done = false;
  for (const line of rest.split("\n")) {
    const stripped = pyStrip(line);
    if (stripped.startsWith(STEP_DONE)) {
      steps.push([stripped.slice(STEP_DONE.length), true]);
    } else if (stripped.startsWith(STEP_UNDONE)) {
      steps.push([stripped.slice(STEP_UNDONE.length), false]);
    } else if (stripped === DONE_MARKER) {
      done = true;
    }
  }
  return { header, steps, done };
}

/**
 * The job file of a job folder, or `null` when it has none.
 * @param {string} path the `JOB.md` path
 * @param {ParkData} texts
 * @returns {JobDoc | null}
 */
export function readJobDoc(path, texts) {
  if (!isFile(path)) {
    return null;
  }
  const source = path.split("/").slice(-JOB_SOURCE_PARTS).join("/"); // <kit>/jobs/<job>/JOB.md: the kit is named
  return parseJobDoc(readText(path), source, texts);
}

// --------------------------------------------------------------------------------------
// files: written atomically, as a set
// --------------------------------------------------------------------------------------

/**
 * @param {string} path
 * @returns {string}
 */
function _tempPath(path) {
  return pyPath(dirname(path), `.${posix.basename(path)}.${process.pid}.tmp`);
}

/**
 * Write `files` so none is left half-written: every one to a temp file first, then replaced in order.
 *
 * Each temp file sits beside its target (a rename is atomic within a directory) and is removed if
 * anything fails before or during the replacing. The caller orders `files` so the file that marks
 * the work as done lands last.
 * @param {readonly (readonly [string, string])[]} files `[path, text]` pairs
 */
export function writeFiles(files) {
  /** @type {[string, string][]} */
  const temps = [];
  try {
    for (const [path, text] of files) {
      const temp = _tempPath(path);
      temps.push([temp, path]);
      const handle = fs.openSync(temp, "wx");
      try {
        fs.writeSync(handle, encodeUtf8(text));
        fs.fsyncSync(handle);
      } finally {
        fs.closeSync(handle);
      }
    }
    for (const [temp, path] of temps) {
      fs.renameSync(temp, path);
    }
  } finally {
    for (const [temp] of temps) {
      unlinkMissingOk(temp);
    }
  }
}

/**
 * @param {string} folder
 */
function _removeIfEmpty(folder) {
  try {
    fs.rmdirSync(folder);
  } catch (error) {
    if (!isOSError(error)) {
      throw error; // an OSError (not empty, already gone) leaves nothing of ours to remove
    }
  }
}

// --------------------------------------------------------------------------------------
// the kits of a project
// --------------------------------------------------------------------------------------

/**
 * The names of the kit folders under `.ergon/` (`<id>-<name>` only), sorted.
 * @param {string} root
 * @param {{closed?: boolean}} [options] `closed` reads `.ergon/.closed/` instead
 * @returns {string[]}
 */
function _kitNames(root, { closed = false } = {}) {
  let ergon = ergonRoot(root);
  if (closed) {
    ergon = pyPath(ergon, CLOSED_DIR);
  }
  if (!isDir(ergon)) {
    return [];
  }
  return fs
    .readdirSync(ergon)
    .filter((name) => isDir(pyPath(ergon, name)) && KIT_RE.test(name))
    .sort(_compareCodePoints);
}

/**
 * @param {string} kitName
 * @returns {string}
 */
function _kitId(kitName) {
  const match = KIT_RE.exec(kitName);
  if (match === null) {
    throw new Error(`not a kit name: ${kitName}`);
  }
  return match[1];
}

/**
 * @param {string} root
 * @param {string} kitId
 * @param {ParkData} texts
 * @param {boolean} closed
 * @returns {string}
 */
function _findKitIn(root, kitId, texts, closed) {
  const names = _kitNames(root, { closed });
  const found = names.filter((name) => _kitId(name) === kitId);
  const ergon = _displayPath(ergonRoot(root), root);
  if (found.length === 0) {
    throw _error(texts, "no_kit", { id: kitId, ergon, kits: names.join(", ") || "none" });
  }
  if (found.length > 1) {
    throw _error(texts, "several_kits", { id: kitId, ergon, kits: found.join(", ") });
  }
  const base = closed ? pyPath(ergonRoot(root), CLOSED_DIR) : ergonRoot(root);
  return pyPath(base, found[0]);
}

/**
 * The kit folder whose name leads with `kitId`.
 * @param {string} root
 * @param {string} kitId
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} no kit or several kits carry the id; the message names the candidates
 */
export function findKit(root, kitId, texts) {
  return _findKitIn(root, kitId, texts, false);
}

/**
 * The closed kit folder whose name leads with `kitId`, or `null`.
 * @param {string} root
 * @param {string} kitId
 * @param {ParkData} texts
 * @returns {string | null}
 */
export function findClosedKit(root, kitId, texts) {
  try {
    return _findKitIn(root, kitId, texts, true);
  } catch (exc) {
    if (!(exc instanceof ParkError)) {
      throw exc;
    }
    return null;
  }
}

/**
 * @param {string} kit
 * @returns {string}
 */
function _jobsDir(kit) {
  return pyPath(kit, JOBS_DIR);
}

/**
 * The job folders of a kit, sorted by name.
 * @param {string} kit
 * @returns {string[]}
 */
function _jobFolders(kit) {
  const folder = _jobsDir(kit);
  if (!isDir(folder)) {
    return [];
  }
  return fs
    .readdirSync(folder)
    .filter((name) => isDir(pyPath(folder, name)))
    .sort(_compareCodePoints)
    .map((name) => pyPath(folder, name));
}

/**
 * The folder of the job whose `JOB.md` names `jobId`, or `null`.
 * @param {string} kit
 * @param {string} jobId
 * @param {ParkData} texts
 * @returns {string | null}
 */
export function findJobFolder(kit, jobId, texts) {
  for (const folder of _jobFolders(kit)) {
    const doc = readJobDoc(pyPath(folder, JOB_FILE), texts);
    if (doc !== null && doc.header.job === jobId) {
      return folder;
    }
  }
  return null;
}

/**
 * The id of a job of a kit: the kit's id and the job's number.
 * @param {string} kitId
 * @param {number} number
 * @returns {string}
 */
export function jobIdOf(kitId, number) {
  return `${kitId}.${number}`;
}

/**
 * The derived state of a unit (ADR 0028 D09): active, parked, not started or done.
 *
 * A stale lease holds nothing: the unit is free, and the lease is offered to the owner.
 * @param {string} unit
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @param {{jobDone?: boolean}} [options]
 * @returns {string}
 */
export function unitState(unit, texts, context, { jobDone = false } = {}) {
  const states = _states(texts);
  if (jobDone) {
    return states.done;
  }
  const lease = readLease(unit, texts);
  if (lease !== null && !leaseIsStale(lease, context)) {
    return states.active;
  }
  if (isFile(pyPath(unit, PARK_FILE))) {
    return states.parked;
  }
  return states.not_started;
}

/**
 * The state of a kit, joined from its jobs and its own lease and note (ADR 0028 D08, D09).
 *
 * A kit is **active** when it or any of its jobs is held, else **done** when every job is done, else
 * **parked** when it or any of its jobs is parked, else **not started**. With a plan that lists
 * jobs, "every job" is every listed job: it has a folder whose `JOB.md` is done, and a job with no
 * folder has not started. With no plan, or a plan that lists no jobs, the job folders that exist
 * decide. A kit whose jobs are all done is done even when its own note is still there; only a live
 * lease on the kit itself outranks that.
 * @param {string} kit
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {string}
 */
export function kitState(kit, texts, context) {
  const states = _states(texts);
  const docs = _jobFolders(kit).map((folder) => ({ folder, doc: readJobDoc(pyPath(folder, JOB_FILE), texts) }));
  const jobStates = docs.flatMap(({ folder, doc }) =>
    doc === null ? [] : [unitState(folder, texts, context, { jobDone: doc.done })],
  );
  const own = unitState(kit, texts, context);
  if ([own, ...jobStates].includes(states.active)) {
    return states.active;
  }
  const plan = readPlan(kit);
  if (plan !== null && plan.jobs.length > 0) {
    const doneIds = new Set(docs.filter(({ doc }) => doc !== null && doc.done).map(({ doc }) => doc?.header.job));
    if (plan.jobs.every((job) => doneIds.has(job.id))) {
      return states.done;
    }
  } else if (docs.length > 0 && docs.every(({ doc }) => doc !== null && doc.done)) {
    return states.done;
  }
  return [own, ...jobStates].includes(states.parked) ? states.parked : states.not_started;
}

/**
 * The age of a file in whole days, or `null` when there is no file.
 * @param {string} path
 * @param {number} now seconds since the epoch
 * @returns {number | null}
 */
function _ageDays(path, now) {
  const stat = pyStat(path);
  if (stat === null || !stat.isFile()) {
    return null;
  }
  return Math.max(0, Math.floor((now - stat.mtimeMs / 1000) / SECONDS_PER_DAY));
}

// --------------------------------------------------------------------------------------
// writing a kit and a job
// --------------------------------------------------------------------------------------

/**
 * Park the work: write `RESUME.md` and `PARK.md` into the kit folder.
 *
 * The kit folder is created when missing. Everything that can be refused is checked before any
 * file is touched; the files then land together (`writeFiles`), `PARK.md` last among the kit's, and
 * a failure removes the folder it created when that folder is still empty.
 *
 * The sessions of the note are kept, not rebuilt: the sessions an earlier write recorded, the holder a
 * takeover kept (`SESSIONS` when the kit had no note yet), and then the ones on this command line.
 *
 * The branch and the revisions come from git, and the note records the time it was written.
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {string} root
 * @param {ParkData} texts
 * @param {string} cwd where git is asked for the branch and the revisions
 * @returns {string} the kit folder
 * @throws {ParkError} a field fails its check, a kit with this id has another name, a closed kit has
 *   this id and name, or the note already there does not parse
 */
export function writeKit(fields, body, root, texts, cwd) {
  checkFields(fields, texts);
  checkBody(body, texts);
  refuseKitConflict(fields, root, texts);
  const kit = pyPath(ergonRoot(root), `${fields.id}-${fields.name}`);
  const parkPath = _displayPath(pyPath(kit, PARK_FILE), root);
  const sessions = mergeSessions(_noteSessions(kit, texts), readPendingSessions(kit, texts), fields.sessions);
  const stamped = { ...fields, sessions, branch: gitBranch(cwd), revisions: gitRevisions(cwd), written: nowStamp() };
  /** @type {[string, string][]} */
  const files = [
    [pyPath(kit, RESUME_FILE), renderResume(stamped, body, parkPath, texts)],
    [pyPath(kit, PARK_FILE), renderNote(stamped, body, texts)],
  ];
  const created = !isDir(kit);
  try {
    fs.mkdirSync(kit, { recursive: true });
    writeFiles(files);
  } catch (error) {
    if (created) {
      _removeIfEmpty(kit);
    }
    throw error;
  }
  unlinkMissingOk(pyPath(kit, SESSIONS_FILE)); // merged into the note just written
  return kit;
}

/**
 * The sessions the kit's note already carries; none when the kit has no note yet.
 * @param {string} kit
 * @param {ParkData} texts
 * @returns {readonly SessionRef[]}
 */
function _noteSessions(kit, texts) {
  if (!isFile(pyPath(kit, PARK_FILE))) {
    return [];
  }
  return readNote(kit, texts).fields.sessions;
}

/**
 * Refuse a kit whose id is taken by another name, or whose id and name belong to a closed kit.
 *
 * A closed kit keeps its id and name for good, so a write never reuses them; `local-id` counts the
 * closed kits for the same reason.
 * @param {ParkFields} fields
 * @param {string} root
 * @param {ParkData} texts
 * @throws {ParkError} a live or closed kit carries the id under another name, or a closed kit has both
 */
export function refuseKitConflict(fields, root, texts) {
  const kitName = `${fields.id}-${fields.name}`;
  const closedNames = _kitNames(root, { closed: true });
  const other = [..._kitNames(root), ...closedNames].filter((name) => _kitId(name) === fields.id && name !== kitName);
  if (other.length > 0) {
    throw _error(texts, "kit_other_name", { existing: other[0], id: fields.id, name: fields.name });
  }
  if (closedNames.includes(kitName)) {
    throw _error(texts, "kit_closed", { kit: kitName });
  }
}

/**
 * Write a job's own file, creating its folder when missing; a reader sees the old file or the new one.
 * @param {string} folder
 * @param {JobDoc} doc
 * @param {ParkData} texts
 */
export function writeJobDoc(folder, doc, texts) {
  fs.mkdirSync(folder, { recursive: true });
  _writeAtomically(pyPath(folder, JOB_FILE), renderJobDoc(doc, texts));
}

/**
 * Refuse a job file whose header would not read back, naming the kit and the offending value.
 *
 * The header is built from the plan's header and job line, so the plan is what is at fault: a plan
 * `id` that is no task id, say, would make a `JOB.md` that `park list` cannot parse.
 * @param {JobDoc} doc
 * @param {string} kitName
 * @param {ParkData} texts
 * @throws {ParkError} the plan's header or job line breaks the header's contract
 */
function _checkJobDoc(doc, kitName, texts) {
  try {
    checkFields(doc.header, texts);
  } catch (error) {
    if (error instanceof ParkError) {
      throw _error(texts, "bad_plan", { kit: kitName, reason: error.message });
    }
    throw error;
  }
}

/**
 * The job file a job starts with: its header from the plan's job line, no steps yet.
 * @param {JobLine} job
 * @param {string} kitId
 * @param {string} kitName
 * @param {Plan | null} plan
 * @returns {JobDoc}
 */
export function jobDocFor(job, kitId, kitName, plan) {
  const header = parkFields({
    id: kitId,
    name: kitName,
    nextAction: job.result,
    plan: plan !== null ? plan.header.id : "",
    job: job.id,
    tasks: job.tasks,
    branch: gitBranch(process.cwd()),
  });
  return { header, steps: [], done: false };
}

// --------------------------------------------------------------------------------------
// the listing: the kits, their jobs, and the states derived from the folders
// --------------------------------------------------------------------------------------

/**
 * What `list` says of one kit; a kit with no `PARK.md` has no age and no next action.
 * @param {string} kit
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {KitSummary}
 */
export function summarizeKit(kit, texts, context) {
  const kitName = posix.basename(kit);
  const id = _kitId(kitName);
  const name = Array.from(kitName)
    .slice(Array.from(id).length + 1)
    .join("");
  const note = pyPath(kit, PARK_FILE);
  if (!isFile(note)) {
    return {
      id,
      name,
      state: kitState(kit, texts, context),
      plan: "",
      nextAction: "",
      decisions: 0,
      branch: "",
      ageDays: null,
    };
  }
  const { fields, body } = readNote(kit, texts);
  return {
    id,
    name,
    state: kitState(kit, texts, context),
    plan: fields.plan,
    nextAction: fields.nextAction,
    decisions: body.decisions.length,
    branch: fields.branch,
    ageDays: _ageDays(note, context.now),
  };
}

/**
 * What `list` says of one job, or `null` when the folder carries no job file.
 * @param {string} folder
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {JobSummary | null}
 */
export function summarizeJob(folder, texts, context) {
  const doc = readJobDoc(pyPath(folder, JOB_FILE), texts);
  if (doc === null) {
    return null;
  }
  const state = unitState(folder, texts, context, { jobDone: doc.done });
  return {
    id: doc.header.job || posix.basename(folder),
    name: posix.basename(folder),
    state,
    tasks: doc.header.tasks,
    nextAction: jobDocNextStep(doc),
    branch: doc.header.branch,
    ageDays: _ageDays(pyPath(folder, JOB_FILE), context.now),
  };
}

/**
 * The task ids a kit carries: from its plan header, its job lines and its jobs' files.
 * @param {string} kit
 * @param {readonly JobSummary[]} jobs
 * @returns {string[]}
 */
function _kitTasks(kit, jobs) {
  /** @type {string[]} */
  const tasks = [];
  const plan = readPlan(kit);
  if (plan !== null) {
    tasks.push(...plan.header.tasks);
    for (const job of plan.jobs) {
      tasks.push(...job.tasks);
    }
  }
  for (const job of jobs) {
    tasks.push(...job.tasks);
  }
  return tasks;
}

/**
 * Whether a kit passes the filters of `list`.
 * @param {KitSummary} summary
 * @param {readonly JobSummary[]} jobs
 * @param {string} kit
 * @param {ListQuery} query
 * @returns {boolean}
 */
function _matches(summary, jobs, kit, query) {
  if (query.plan && summary.plan !== query.plan) {
    return false;
  }
  if (query.state && summary.state !== query.state) {
    return false;
  }
  return !query.task || _kitTasks(kit, jobs).includes(query.task);
}

/**
 * The kits under `.ergon/` that match `query`, and the jobs of those kits.
 *
 * Reads only: the local index is retired, so the folders are the whole record. A kit whose files do
 * not parse is listed with its `unreadable` reason, whatever the filters, and the other kits are
 * listed as usual.
 * @param {string} root
 * @param {ListQuery} query
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {{kits: KitSummary[], jobs: JobSummary[]}}
 */
export function listKits(root, query, texts, context) {
  /** @type {KitSummary[]} */
  const summaries = [];
  /** @type {JobSummary[]} */
  const jobs = [];
  const ergon = ergonRoot(root);
  const entries = _kitNames(root).map((name) => pyPath(ergon, name));
  if (query.closed) {
    entries.push(..._kitNames(root, { closed: true }).map((name) => pyPath(ergon, CLOSED_DIR, name)));
  }
  for (const kit of entries) {
    /** @type {KitSummary} */
    let summary;
    /** @type {(JobSummary | null)[]} */
    let summarized;
    try {
      summary = summarizeKit(kit, texts, context);
      summarized = _jobFolders(kit).map((folder) => summarizeJob(folder, texts, context));
    } catch (error) {
      if (!(error instanceof ParkError)) {
        throw error;
      }
      // one bad kit is reported on its own line, never stops the others
      const kitName = posix.basename(kit);
      const id = _kitId(kitName);
      const name = Array.from(kitName)
        .slice(Array.from(id).length + 1)
        .join("");
      const reason = error.message.replace(LINE_BREAKS_RE, " ");
      summaries.push({
        id,
        name,
        state: "",
        plan: "",
        nextAction: "",
        decisions: 0,
        branch: "",
        ageDays: null,
        unreadable: reason,
      });
      continue;
    }
    const kitJobs = summarized.filter((job) => job !== null);
    if (!_matches(summary, kitJobs, kit, query)) {
      continue;
    }
    summaries.push(summary);
    jobs.push(...kitJobs);
  }
  return { kits: summaries.sort((a, b) => _compareCodePoints(a.id, b.id)), jobs };
}

/**
 * `text` cut to `width` characters, the last one the ellipsis when it was cut.
 * @param {string} text
 * @param {number} width
 * @param {ParkData} texts
 * @returns {string}
 */
function _truncate(text, width, texts) {
  const points = Array.from(text);
  return points.length <= width ? text : points.slice(0, width - 1).join("") + texts.ellipsis;
}

/**
 * @param {number | null} ageDays
 * @param {string} empty
 * @returns {string}
 */
function _ageCell(ageDays, empty) {
  return ageDays === null ? empty : `${ageDays}d`;
}

/**
 * One `list` line; an absent value is the empty cell and the age is whole days (`3d`).
 * @param {KitSummary} item
 * @param {ParkData} texts
 * @returns {string}
 */
export function formatSummary(item, texts) {
  const empty = texts.empty_cell;
  if (item.unreadable) {
    return fill(texts.list.unreadable, { id: item.id, name: item.name, reason: item.unreadable });
  }
  return fill(texts.list.line, {
    id: item.id,
    name: item.name,
    state: item.state,
    plan: item.plan || empty,
    next: item.nextAction ? _truncate(item.nextAction, texts.next_width, texts) : empty,
    decisions: String(item.decisions),
    branch: item.branch || empty,
    age: _ageCell(item.ageDays, empty),
  });
}

/**
 * One job line of `list`.
 * @param {JobSummary} item
 * @param {ParkData} texts
 * @returns {string}
 */
export function formatJob(item, texts) {
  const empty = texts.empty_cell;
  return fill(texts.list.job_line, {
    id: item.id,
    name: item.name,
    state: item.state,
    tasks: item.tasks.join(", ") || empty,
    next: item.nextAction ? _truncate(item.nextAction, texts.next_width, texts) : empty,
    branch: item.branch || empty,
    age: _ageCell(item.ageDays, empty),
  });
}

// --------------------------------------------------------------------------------------
// the active unit: read from the worktree's folder, never kept in git (ADR 0028 D10)
// --------------------------------------------------------------------------------------

/**
 * The kit id and the job number a worktree's folder names, or `null`.
 *
 * The folder is `<id>-<name>.<n>`: the kit's own folder name and the job's number.
 * @param {string} folder
 * @returns {{kitId: string, number: number} | null}
 */
export function worktreeUnit(folder) {
  const name = posix.basename(folder);
  const dot = name.lastIndexOf(".");
  const base = name.slice(0, Math.max(dot, 0));
  const tail = dot < 0 ? "" : name.slice(dot + 1);
  if (base === "" || !WORKTREE_TAIL_RE.test(tail)) {
    return null;
  }
  const match = KIT_RE.exec(base);
  if (match === null) {
    return null;
  }
  return { kitId: match[1], number: pyInt(tail) };
}

/**
 * The kit and the job this session is in, read from the folder it works in.
 *
 * A session in the main checkout has no active unit until it picks one; a session in a job's
 * worktree is in that job, named by the worktree's own folder.
 * @param {string} root
 * @param {ParkData} texts
 * @returns {{kit: string, kitId: string, number: number} | null}
 */
export function activeUnit(root, texts) {
  if (posix.basename(dirname(root)) !== WORKTREES_DIR) {
    return null;
  }
  const unit = worktreeUnit(root);
  if (unit === null) {
    return null;
  }
  try {
    return { kit: findKit(root, unit.kitId, texts), kitId: unit.kitId, number: unit.number };
  } catch (exc) {
    if (!(exc instanceof ParkError)) {
      throw exc;
    }
    return null;
  }
}

// --------------------------------------------------------------------------------------
// the export: the kit's files, its leases left out (ADR 0028 D07, branch B10)
// --------------------------------------------------------------------------------------

/**
 * Every file under `folder` as a path relative to `base`, in `Path.rglob("*")`'s reach.
 * @param {string} folder
 * @param {string} base
 * @returns {string[]}
 */
function _filesUnder(folder, base) {
  /** @type {string[]} */
  const found = [];
  for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
    const full = pyPath(folder, entry.name);
    if (entry.isDirectory()) {
      found.push(..._filesUnder(full, base));
    } else if (isFile(full)) {
      found.push(posix.relative(base, full));
    }
  }
  return found;
}

/**
 * Write the kit's files to one bundle file, its leases left out.
 *
 * The bundle is plain text: the file's path, then its content, so any language reads it.
 * @param {string} kit
 * @param {string} out
 * @param {ParkData} texts
 * @returns {string} the bundle path
 */
export function exportKit(kit, out, texts) {
  const spec = texts.export;
  const lines = [fill(spec.title, { kit: posix.basename(kit) }), ""];
  for (const relative of _filesUnder(kit, kit).sort(_comparePaths)) {
    if (posix.basename(relative) === HOLDER_FILE) {
      continue;
    }
    lines.push(fill(spec.file_header, { path: relative }));
    lines.push(rstripChars(readText(pyPath(kit, relative)), "\n"));
    lines.push(spec.end);
    lines.push("");
  }
  fs.mkdirSync(dirname(out), { recursive: true });
  writeText(out, `${rstripChars(lines.join("\n"), "\n")}\n`);
  return out;
}

// --------------------------------------------------------------------------------------
// the local ids: `_T<n>` counted over the kits, live and closed, never reused
// --------------------------------------------------------------------------------------

/**
 * The `_T<n>` numbers the retired local index `<DEV>/.local/TASKS.md` still holds.
 *
 * Read as legacy input and never written (ADR 0028 D12). The index sits with the kits in the main
 * checkout, so a linked worktree reads that one. No such file holds no number.
 * @param {string} root
 * @returns {number[]}
 */
function _legacyLocalIds(root) {
  const index = pyPath(localRoot(gitCommonRoot(root)), LEGACY_INDEX_FILE);
  if (!isFile(index)) {
    return [];
  }
  /** @type {number[]} */
  const numbers = [];
  for (const line of readText(index).split("\n")) {
    const match = LEGACY_ROW_RE.exec(line);
    if (match !== null) {
      numbers.push(pyInt(match[1]));
    }
  }
  return numbers;
}

/**
 * The next free local id: `_T<n>` counted over every kit, live and closed, and the legacy index.
 * @param {string} root
 * @returns {string}
 */
export function nextLocalId(root) {
  const numbers = [0, ..._legacyLocalIds(root)];
  for (const name of [..._kitNames(root), ..._kitNames(root, { closed: true })]) {
    const match = LOCAL_ID_RE.exec(_kitId(name));
    if (match !== null) {
      numbers.push(pyInt(match[1]));
    }
  }
  return `_T${Math.max(...numbers) + 1}`;
}

// --------------------------------------------------------------------------------------
// command line
// --------------------------------------------------------------------------------------

/**
 * One option of a command.
 * @typedef {object} OptionSpec
 * @property {string[]} flags the spellings, the first one names it in a message
 * @property {string} dest the key its value is stored under
 * @property {"one" | "many" | "int" | "switch"} kind
 * @property {boolean} required
 */

/**
 * What the scanner holds while it walks the arguments of one command.
 * @typedef {object} Scan
 * @property {Map<string, OptionSpec | "help">} flags
 * @property {Map<string, string | string[] | number | boolean>} values
 * @property {string[]} positionals
 * @property {number[]} positionalAt the place of each positional on the command line
 * @property {{at: number, token: string}[]} extras the unknown options, each with its place
 */

/**
 * The arguments of one command, as the scanner leaves them.
 * @typedef {object} ParsedArgs
 * @property {string} command
 * @property {string} id the positional, empty for a command that takes none
 * @property {Map<string, string | string[] | number | boolean>} values
 */

/** A usage error: the one line the scanner reports with exit 2. */
class UsageError extends Error {}

/**
 * @param {string} flag
 * @returns {string} `--owned-path` as `ownedPath`
 */
function _camel(flag) {
  return flag.slice(2).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
}

/**
 * @param {string[]} flags
 * @param {string} dest
 * @param {Partial<OptionSpec>} [extra]
 * @returns {OptionSpec}
 */
function _option(flags, dest, extra = {}) {
  return { flags, dest, kind: "one", required: false, ...extra };
}

/**
 * @param {string} flag
 * @param {Partial<OptionSpec>} [extra]
 * @returns {OptionSpec}
 */
function _flag(flag, extra = {}) {
  return _option([flag], flag === "--next" ? "nextAction" : _camel(flag), extra);
}

const ROOT_OPTION = _option(["--root", "--project-root"], "root");
const MACHINE_OPTION = _flag("--machine");
const HOLDER_OPTIONS = [_flag("--harness"), _flag("--session-id")];

/**
 * The options of a command with the two every command takes (`--root`, `--machine`) appended.
 * @param {OptionSpec[]} options
 * @returns {OptionSpec[]}
 */
function _withCommon(options) {
  return [...options, ROOT_OPTION, MACHINE_OPTION];
}

/** The commands, in the order the Python parser adds them: whether each takes the kit id, and its options. */
const COMMANDS = {
  write: {
    id: true,
    options: _withCommon([
      _flag("--name", { required: true }),
      _flag("--goal", { required: true }),
      _flag("--next", { required: true }),
      ...["--plan", "--row"].map((flag) => _flag(flag)),
      ...["--owned-path", "--check", "--unverified", "--decision", "--answer", "--agent"].map((flag) =>
        _flag(flag, { kind: "many" }),
      ),
      ...["--readiness", "--origin"].map((flag) => _flag(flag)),
      ...HOLDER_OPTIONS,
    ]),
  },
  unpark: { id: true, options: _withCommon(HOLDER_OPTIONS) },
  digest: { id: true, options: _withCommon([_flag("--cap", { kind: "int" })]) },
  list: {
    id: false,
    options: _withCommon([_flag("--plan"), _flag("--task"), _flag("--state"), _flag("--closed", { kind: "switch" })]),
  },
  hold: {
    id: true,
    options: _withCommon([
      _flag("--number", { kind: "int" }),
      _flag("--takeover", { kind: "switch" }),
      ...HOLDER_OPTIONS,
    ]),
  },
  release: { id: true, options: _withCommon([_flag("--number", { kind: "int" })]) },
  job: {
    id: true,
    options: _withCommon([
      _flag("--number", { kind: "int", required: true }),
      _flag("--step", { kind: "many" }),
      _flag("--done", { kind: "switch" }),
      ...HOLDER_OPTIONS,
    ]),
  },
  active: { id: false, options: _withCommon([]) },
  close: { id: true, options: _withCommon(HOLDER_OPTIONS) },
  export: { id: true, options: _withCommon([_flag("--out", { required: true })]) },
  "local-id": { id: false, options: _withCommon([]) },
};

// What `argparse` takes for a number, hence for a value rather than an option (no option here looks like one).
const NEGATIVE_NUMBER = /^-\d+$|^-\d*\.\d+$/;

/**
 * How `argparse` reads one argument string: a value (`positional`), a known option, or an
 * unknown one. `--flag=value` splits at the first `=`; a lone `-`, a negative number and a string
 * with a space are values.
 * @param {string} token
 * @param {Map<string, OptionSpec | "help">} flags
 * @returns {{kind: "positional"} | {kind: "unknown"} | {kind: "option", spec: OptionSpec | "help", explicit: string | null}}
 */
function _classify(token, flags) {
  if (!token.startsWith("-") || token === "-") {
    return { kind: "positional" };
  }
  const exact = flags.get(token);
  if (exact !== undefined) {
    return { kind: "option", spec: exact, explicit: null };
  }
  const equals = token.indexOf("=");
  const named = equals < 0 ? undefined : flags.get(token.slice(0, equals));
  if (named !== undefined) {
    return { kind: "option", spec: named, explicit: token.slice(equals + 1) };
  }
  return NEGATIVE_NUMBER.test(token) || token.includes(" ") ? { kind: "positional" } : { kind: "unknown" };
}

/**
 * The value an option holds for the text it was given: the text, the list it joins, or the integer.
 * @param {Scan} scan
 * @param {OptionSpec} spec
 * @param {string} raw
 * @returns {string | string[] | number}
 */
function _valueOf(scan, spec, raw) {
  if (spec.kind === "many") {
    return [...(/** @type {string[] | undefined} */ (scan.values.get(spec.dest)) ?? []), raw];
  }
  if (spec.kind === "int") {
    try {
      return pyInt(raw);
    } catch {
      throw new UsageError(`argument ${spec.flags.join("/")}: invalid int value: ${strRepr(raw)}`);
    }
  }
  return raw;
}

/**
 * Store one option's value, taking it from the next argument when `--flag=value` did not give it.
 * @param {Scan} scan
 * @param {OptionSpec} spec
 * @param {string | null} explicit
 * @param {readonly string[]} tokens
 * @param {number} index the position after the option
 * @returns {number} the position after the value
 */
function _store(scan, spec, explicit, tokens, index) {
  const next = tokens[index];
  if (explicit !== null) {
    scan.values.set(spec.dest, _valueOf(scan, spec, explicit));
    return index;
  }
  if (next === undefined || next === "--" || _classify(next, scan.flags).kind !== "positional") {
    throw new UsageError(`argument ${spec.flags.join("/")}: expected one argument`);
  }
  scan.values.set(spec.dest, _valueOf(scan, spec, next));
  return index + 1;
}

/**
 * @param {Scan} scan
 * @param {{spec: OptionSpec | "help", explicit: string | null}} found
 * @param {readonly string[]} tokens
 * @param {number} index
 * @returns {number | "help"} the position after the option, or `"help"` when it asked for the usage
 */
function _applyOption(scan, found, tokens, index) {
  const { spec, explicit } = found;
  if (spec !== "help" && spec.kind !== "switch") {
    return _store(scan, spec, explicit, tokens, index);
  }
  const names = spec === "help" ? "-h/--help" : spec.flags.join("/");
  if (explicit !== null) {
    throw new UsageError(`argument ${names}: ignored explicit argument ${strRepr(explicit)}`);
  }
  if (spec === "help") {
    return "help";
  }
  scan.values.set(spec.dest, true);
  return index;
}

/**
 * Walk the arguments after the command: values, options and `--` as `argparse` reads them.
 * @param {string} command
 * @param {readonly string[]} tokens
 * @returns {Scan | "help"}
 */
function _scan(command, tokens) {
  /** @type {Map<string, OptionSpec | "help">} */
  const flags = new Map([
    ["-h", "help"],
    ["--help", "help"],
  ]);
  for (const option of COMMANDS[/** @type {keyof typeof COMMANDS} */ (command)].options) {
    for (const flag of option.flags) {
      flags.set(flag, option);
    }
  }
  /** @type {Scan} */
  const scan = { flags, values: new Map(), positionals: [], positionalAt: [], extras: [] };
  let bare = false;
  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index];
    const at = index;
    index += 1;
    const found = bare ? { kind: "positional" } : _classify(token, flags);
    if (!bare && token === "--") {
      bare = true;
    } else if (found.kind === "positional") {
      scan.positionals.push(token);
      scan.positionalAt.push(at);
    } else if (found.kind === "unknown") {
      scan.extras.push({ at, token });
    } else {
      const next = _applyOption(
        scan,
        /** @type {{spec: OptionSpec | "help", explicit: string | null}} */ (found),
        tokens,
        index,
      );
      if (next === "help") {
        return "help";
      }
      index = next;
    }
  }
  return scan;
}

/**
 * The scan checked against the command: the id present, the required options given, nothing left over.
 * @param {string} command
 * @param {Scan} scan
 * @returns {ParsedArgs}
 */
function _finish(command, scan) {
  const spec = COMMANDS[/** @type {keyof typeof COMMANDS} */ (command)];
  const missing = [
    ...(spec.id && scan.positionals.length === 0 ? ["id"] : []),
    ...spec.options
      .filter((option) => option.required && !scan.values.has(option.dest))
      .map((option) => option.flags[0]),
  ];
  if (missing.length > 0) {
    throw new UsageError(`the following arguments are required: ${missing.join(", ")}`);
  }
  const skipped = spec.id ? 1 : 0;
  const surplus = [
    ...scan.extras,
    ...scan.positionals.slice(skipped).map((token, offset) => ({ at: scan.positionalAt[skipped + offset], token })),
  ]
    .sort((left, right) => left.at - right.at)
    .map((entry) => entry.token);
  if (surplus.length > 0) {
    throw new UsageError(`unrecognized arguments: ${surplus.join(" ")}`);
  }
  return { command, id: spec.id ? scan.positionals[0] : "", values: scan.values };
}

/**
 * Parse the arguments: the command, then its options and the id in any order.
 * @param {readonly string[]} argv
 * @returns {ParsedArgs | "help" | string} the arguments, `"help"`, or the one-line usage error
 */
function _parse(argv) {
  const command = argv[0];
  if (command === undefined) {
    return "the following arguments are required: command";
  }
  if (command === "-h" || command === "--help") {
    return "help";
  }
  if (!Object.hasOwn(COMMANDS, command)) {
    const choices = Object.keys(COMMANDS)
      .map((name) => `'${name}'`)
      .join(", ");
    return `argument command: invalid choice: ${strRepr(command)} (choose from ${choices})`;
  }
  try {
    const scan = _scan(command, argv.slice(1));
    return scan === "help" ? "help" : _finish(command, scan);
  } catch (exc) {
    if (!(exc instanceof UsageError)) {
      throw exc;
    }
    return exc.message;
  }
}

/**
 * @param {ParsedArgs} args
 * @param {string} dest
 * @returns {string} the value, stripped; empty when the option was not given
 */
function _text(args, dest) {
  const value = args.values.get(dest);
  return typeof value === "string" ? pyStrip(value) : "";
}

/**
 * @param {ParsedArgs} args
 * @param {string} dest
 * @returns {string[]} every given value, stripped
 */
function _listOf(args, dest) {
  return /** @type {string[]} */ (args.values.get(dest) ?? []).map((value) => pyStrip(value));
}

/**
 * @param {ParsedArgs} args
 * @param {string} dest
 * @returns {boolean} whether a `store_true` option was given
 */
function _switchOf(args, dest) {
  return args.values.get(dest) === true;
}

/**
 * @param {ParsedArgs} args
 * @param {string} dest
 * @returns {number | null} the integer an option was given, or `null`
 */
function _numberOf(args, dest) {
  const value = args.values.get(dest);
  return typeof value === "number" ? value : null;
}

/**
 * @param {ParsedArgs} args
 * @param {ParkData} texts
 * @returns {readonly SessionRef[]}
 */
function _sessionRefs(args, texts) {
  const harness = _text(args, "harness");
  if (harness === "") {
    if (_text(args, "sessionId") !== "" || _text(args, "machine") !== "") {
      throw _error(texts, "session_needs_harness");
    }
    return [];
  }
  return [{ harness, sessionId: _text(args, "sessionId"), machine: _text(args, "machine") }];
}

/**
 * @param {ParsedArgs} args
 * @param {ParkData} texts
 * @returns {ParkFields}
 */
function _fieldsFrom(args, texts) {
  return parkFields({
    id: pyStrip(args.id),
    name: _text(args, "name"),
    nextAction: _text(args, "nextAction"),
    plan: _text(args, "plan"),
    row: _text(args, "row"),
    ownedPaths: _listOf(args, "ownedPath"),
    sessions: _sessionRefs(args, texts),
    origin: _text(args, "origin"),
    readiness: _text(args, "readiness"),
  });
}

/**
 * @param {ParsedArgs} args
 * @returns {ParkBody}
 */
function _bodyFrom(args) {
  return parkBody({
    goal: _text(args, "goal"),
    decisions: _listOf(args, "decision"),
    answers: _listOf(args, "answer"),
    checks: _listOf(args, "check"),
    unverified: _listOf(args, "unverified"),
    agents: _listOf(args, "agent"),
  });
}

/**
 * The root the command works in; a missing project root is refused, as every command reads or writes under it.
 * @param {string | null} explicit
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} no project root, or `--root` names something that is not a directory
 */
function _projectRoot(explicit, texts) {
  const { root, notice } = resolveProjectRoot(explicit);
  if (notice !== null) {
    throw new ParkError(notice);
  }
  if (explicit !== null && !isDir(root)) {
    throw _error(texts, "no_project_root_dir", { path: root });
  }
  return root;
}

/**
 * The holder a command acts as: the flags, or the machine it runs on.
 * @param {ParsedArgs} args
 * @param {string} machine
 * @returns {Holder}
 */
function _holderOf(args, machine) {
  return {
    harness: _text(args, "harness"),
    sessionId: _text(args, "sessionId"),
    machine: _text(args, "machine") || machine,
    worktree: process.cwd(),
  };
}

/**
 * The folder of the unit a command acts on: the kit root, or one of its jobs.
 * @param {string} kit
 * @param {number | null} number
 * @param {ParkData} texts
 * @returns {string}
 */
function _unitOf(kit, number, texts) {
  if (number === null) {
    return kit;
  }
  const jobId = jobIdOf(_kitId(posix.basename(kit)), number);
  const folder = findJobFolder(kit, jobId, texts);
  if (folder === null) {
    throw _error(texts, "no_job", { kit: posix.basename(kit), job: jobId });
  }
  return folder;
}

/**
 * The label of the machine this session runs on.
 * @returns {string}
 */
function _machineLabel() {
  try {
    return os.hostname();
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
    return "";
  }
}

/**
 * The resume prompt of a kit, and the proof that its note reads: nothing is held yet.
 * @param {string} kit
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} the kit has no `RESUME.md`, was never parked, or its note does not parse
 */
function _readResume(kit, texts) {
  const resume = pyPath(kit, RESUME_FILE);
  if (!isFile(resume)) {
    throw _error(texts, "no_resume", { kit: posix.basename(kit) });
  }
  readNote(kit, texts);
  return rstripChars(readText(resume), "\n");
}

/**
 * The resume prompt of a kit, followed by a blank line and its capped digest.
 * @param {string} prompt
 * @param {string} kit
 * @param {string} root
 * @param {ParkData} texts
 * @returns {string}
 */
function _resumeText(prompt, kit, root, texts) {
  return `${prompt}\n\n${digest(kit, texts.default_cap, root, texts)}`;
}

/**
 * @param {string} text
 */
function _print(text) {
  process.stdout.write(`${text}\n`);
}

/**
 * The usable job line of a plan for `jobId`: it names a folder and a result for `JOB.md`.
 * @param {string} kit
 * @param {Plan} plan
 * @param {string} jobId
 * @param {ParkData} texts
 * @returns {JobLine}
 * @throws {ParkError} the plan has no such job, or the line has no label or no result
 */
function _plannedJob(kit, plan, jobId, texts) {
  const line = plan.jobs.find((job) => job.id === jobId);
  if (line === undefined) {
    throw _error(texts, "no_job", { kit: posix.basename(kit), job: jobId });
  }
  if (line.label === "") {
    throw _error(texts, "job_label", { id: jobId });
  }
  if (line.result === "") {
    throw _error(texts, "bad_plan", { kit: posix.basename(kit), reason: `job ${jobId} has no result` });
  }
  return line;
}

/**
 * The folder and the file a job write starts from: the job's own when it exists, else the ones the
 * plan's job line gives it.
 * @param {string} kit
 * @param {Plan} plan
 * @param {string} jobId
 * @param {ParkData} texts
 * @returns {{folder: string, doc: JobDoc}}
 * @throws {ParkError} the job has no folder yet and the plan has no usable line for it
 */
function _jobToWrite(kit, plan, jobId, texts) {
  const existing = findJobFolder(kit, jobId, texts);
  const doc = existing !== null ? readJobDoc(pyPath(existing, JOB_FILE), texts) : null;
  if (existing !== null && doc !== null) {
    return { folder: existing, doc };
  }
  const line = _plannedJob(kit, plan, jobId, texts);
  const kitId = _kitId(posix.basename(kit));
  const kitName = Array.from(posix.basename(kit))
    .slice(Array.from(kitId).length + 1)
    .join("");
  const fresh = jobDocFor(line, kitId, kitName, plan);
  _checkJobDoc(fresh, posix.basename(kit), texts);
  const folder = existing ?? pyPath(_jobsDir(kit), `${line.number}-${jobSlug(line.label)}`);
  return { folder, doc: fresh };
}

/**
 * Write a job's own file: create it from the plan's job line, then add its steps.
 *
 * Everything that can be refused is checked before the lease is taken or a file is touched. The
 * first write into a job's folder takes its lease, so two sessions never write one file. The plan's
 * shared-path warnings go to stderr.
 * @param {ParsedArgs} args
 * @param {Run} run
 * @throws {ParkError} the kit has no plan, the plan has no usable line for the job, or the job is held
 */
function _writeJob(args, run) {
  const { root, texts } = run;
  const kit = findKit(root, pyStrip(args.id), texts);
  const kitId = _kitId(posix.basename(kit));
  const number = /** @type {number} */ (_numberOf(args, "number"));
  const jobId = jobIdOf(kitId, number);
  const plan = readPlan(kit);
  if (plan === null) {
    throw _error(texts, "no_plan", { kit: posix.basename(kit) });
  }
  const { folder, doc } = _jobToWrite(kit, plan, jobId, texts);
  acquireLease(folder, _holderOf(args, run.lease.machine), texts, run.lease);
  /** @type {(readonly [string, boolean])[]} */
  const steps = [
    ...doc.steps,
    ..._listOf(args, "step").map((text) => /** @type {[string, boolean]} */ ([text, false])),
  ];
  writeJobDoc(folder, { header: doc.header, steps, done: doc.done || _switchOf(args, "done") }, texts);
  _print(_displayPath(folder, root));
  for (const warning of sharedPathWarnings(plan, texts)) {
    process.stderr.write(`${warning}\n`);
  }
}

/**
 * Print the unit this session is in: the job of the worktree it works in.
 * @param {Run} run
 */
function _printActive(run) {
  const { root, texts } = run;
  const found = activeUnit(root, texts);
  if (found === null) {
    _print(texts.active.none);
    return;
  }
  const jobId = jobIdOf(found.kitId, found.number);
  const folder = findJobFolder(found.kit, jobId, texts);
  const unit = folder !== null ? folder : found.kit;
  const lease = readLease(unit, texts);
  const state = unitState(unit, texts, run.lease);
  const path = _displayPath(unit, root);
  _print(
    fill(texts.active.line, {
      kind: folder !== null ? "job" : "kit",
      id: folder !== null ? jobId : found.kitId,
      name: posix.basename(unit),
      state,
      holder: lease !== null ? holderLabel(lease.holder) : texts.empty_cell,
      path,
    }),
  );
}

/**
 * What every command of one invocation shares: the root, the texts, the lease clock, the machine.
 * @typedef {object} Run
 * @property {string} root
 * @property {ParkData} texts
 * @property {LeaseContext} lease
 */

/**
 * The folder a kit has, or the one it would have; the name conflict is the writer's to refuse.
 * @param {string} root
 * @param {ParkFields} fields
 * @returns {string}
 */
function _kitFolder(root, fields) {
  return pyPath(ergonRoot(root), `${fields.id}-${fields.name}`);
}

/**
 * Refuse to write a unit another session holds, live or stale.
 *
 * The lease is what keeps one file out of two writers' hands, so a write into a held unit is refused
 * with the holder named. A stale lease is refused too: it is offered to the owner for a takeover
 * (`hold --takeover`), which keeps the replaced holder in the note, and a write never takes it
 * silently (ADR 0028 D09).
 * @param {string} unit
 * @param {Holder} holder
 * @param {Run} run
 * @throws {ParkError} another session holds the unit
 */
function _refuseForeignLease(unit, holder, run) {
  const lease = readLease(unit, run.texts);
  if (lease === null || holderSameAs(lease.holder, holder)) {
    return;
  }
  const code = leaseIsStale(lease, run.lease) ? "held_write_stale" : "held_write";
  throw _error(run.texts, code, { unit: posix.basename(unit), holder: holderLabel(lease.holder) });
}

/**
 * Release the lease of a unit when it is still the one this session took; another's is never removed.
 * @param {string} unit
 * @param {Lease} lease
 * @param {ParkData} texts
 */
function _releaseOwnLease(unit, lease, texts) {
  const current = readLease(unit, texts);
  if (
    current !== null &&
    current.holder.harness === lease.holder.harness &&
    current.holder.sessionId === lease.holder.sessionId &&
    current.holder.machine === lease.holder.machine &&
    current.holder.worktree === lease.holder.worktree
  ) {
    releaseLease(unit);
  }
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdWrite(args, run) {
  const fields = _fieldsFrom(args, run.texts);
  const body = _bodyFrom(args);
  const kit = _kitFolder(run.root, fields);
  const holder = _holderOf(args, run.lease.machine);
  checkFields(fields, run.texts);
  checkBody(body, run.texts);
  refuseKitConflict(fields, run.root, run.texts);
  _refuseForeignLease(kit, holder, run);
  const free = readLease(kit, run.texts) === null;
  // The write holds the kit while it writes: a lease taken since the check is refused, not overwritten.
  const lease = acquireLease(kit, holder, run.texts, run.lease);
  try {
    writeKit(fields, body, run.root, run.texts, process.cwd());
  } catch (error) {
    if (free) {
      _releaseOwnLease(kit, lease, run.texts);
      _removeIfEmpty(kit);
    }
    throw error;
  }
  _releaseOwnLease(kit, lease, run.texts);
  _print(_displayPath(kit, run.root));
  return 0;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdUnpark(args, run) {
  const kit = findKit(run.root, pyStrip(args.id), run.texts);
  const prompt = _readResume(kit, run.texts); // everything that can be refused, before a lease is taken
  acquireLease(kit, _holderOf(args, run.lease.machine), run.texts, run.lease);
  _print(_resumeText(prompt, kit, run.root, run.texts));
  return 0;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdDigest(args, run) {
  const given = _numberOf(args, "cap");
  const cap = given === null ? run.texts.default_cap : given;
  if (cap < 0) {
    throw _error(run.texts, "bad_cap", { value: cap });
  }
  _print(digest(findKit(run.root, pyStrip(args.id), run.texts), cap, run.root, run.texts));
  return 0;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdList(args, run) {
  const query = {
    plan: _text(args, "plan"),
    task: _text(args, "task"),
    state: _text(args, "state"),
    closed: _switchOf(args, "closed"),
  };
  const { kits, jobs } = listKits(run.root, query, run.texts, run.lease);
  if (kits.length > 0) {
    /** @type {string[]} */
    const lines = [];
    for (const summary of kits) {
      lines.push(formatSummary(summary, run.texts));
      lines.push(...jobs.filter((job) => job.id.startsWith(`${summary.id}.`)).map((job) => formatJob(job, run.texts)));
    }
    _print(lines.join("\n"));
  } else if (_kitNames(run.root).length === 0) {
    _print(fill(run.texts.list.empty, { path: _displayPath(ergonRoot(run.root), run.root) }));
  } else {
    _print(run.texts.list.no_match);
  }
  return 0;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdHold(args, run) {
  const kit = findKit(run.root, pyStrip(args.id), run.texts);
  const unit = _unitOf(kit, _numberOf(args, "number"), run.texts);
  const holder = _holderOf(args, run.lease.machine);
  const takeover = _switchOf(args, "takeover");
  if (takeover) {
    _printReplacedPaths(unit, holder, run);
  }
  const lease = acquireLease(unit, holder, run.texts, run.lease, { takeover });
  _print(`${posix.basename(unit)}: ${holderLabel(lease.holder)}`);
  return 0;
}

/**
 * Name the uncommitted paths of the holder a takeover would replace, before anything else is done.
 *
 * Nothing is printed when the unit is free, is this session's own, or the replaced worktree is clean;
 * a worktree that cannot be read is said so, so a silent line means a clean one.
 * @param {string} unit
 * @param {Holder} holder
 * @param {Run} run
 */
function _printReplacedPaths(unit, holder, run) {
  const existing = readLease(unit, run.texts);
  if (existing === null || holderSameAs(existing.holder, holder)) {
    return;
  }
  const paths = gitUncommittedPaths(existing.holder.worktree);
  const spec = run.texts.takeover;
  const label = holderLabel(existing.holder);
  if (paths === null) {
    _print(fill(spec.unreadable, { holder: label }));
  } else if (paths.length > 0) {
    _print(fill(spec.uncommitted, { holder: label, paths: paths.join(", ") }));
  }
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdRelease(args, run) {
  const kit = findKit(run.root, pyStrip(args.id), run.texts);
  const unit = _unitOf(kit, _numberOf(args, "number"), run.texts);
  if (readLease(unit, run.texts) === null) {
    throw _error(run.texts, "no_holder", { unit: posix.basename(unit) });
  }
  releaseLease(unit);
  _print(posix.basename(unit));
  return 0;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdJob(args, run) {
  _writeJob(args, run);
  return 0;
}

/**
 * @param {ParsedArgs} _args
 * @param {Run} run
 * @returns {number}
 */
function _cmdActive(_args, run) {
  _printActive(run);
  return 0;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdClose(args, run) {
  const kit = findKit(run.root, pyStrip(args.id), run.texts);
  _refuseLiveForeignLease(kit, _holderOf(args, run.lease.machine), run);
  const closed = pyPath(ergonRoot(run.root), CLOSED_DIR);
  const target = pyPath(closed, posix.basename(kit));
  if (pyStat(target) !== null) {
    throw _error(run.texts, "close_exists", {
      kit: posix.basename(kit),
      target: _displayPath(target, run.root),
    });
  }
  fs.mkdirSync(closed, { recursive: true });
  try {
    fs.renameSync(kit, target);
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
    const reason = /** @type {NodeJS.ErrnoException} */ (error).code ?? "OSError";
    throw _error(run.texts, "close_failed", { kit: posix.basename(kit), reason });
  }
  releaseLeases(target); // after the move, so a close that is refused or fails changes nothing
  _print(_displayPath(target, run.root));
  return 0;
}

/**
 * Refuse to close a kit while a live lease of another session is in it, the plan's or a job's.
 *
 * A stale lease holds nothing, and the closing session's own leases are its to release.
 * @param {string} kit
 * @param {Holder} holder
 * @param {Run} run
 * @throws {ParkError} another session holds a unit of the kit; the message names the unit and the holder
 */
function _refuseLiveForeignLease(kit, holder, run) {
  for (const unit of [kit, ..._jobFolders(kit)]) {
    const lease = readLease(unit, run.texts);
    if (lease === null || leaseIsStale(lease, run.lease) || holderSameAs(lease.holder, holder)) {
      continue;
    }
    throw _error(run.texts, "close_held", { unit: posix.basename(unit), holder: holderLabel(lease.holder) });
  }
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdExport(args, run) {
  const kit = findKit(run.root, pyStrip(args.id), run.texts);
  const out = pyPath(/** @type {string} */ (args.values.get("out")));
  exportKit(kit, out, run.texts);
  _print(out);
  return 0;
}

/**
 * @param {ParsedArgs} _args
 * @param {Run} run
 * @returns {number}
 */
function _cmdLocalId(_args, run) {
  _print(nextLocalId(run.root));
  return 0;
}

/**
 * The command name to its handler; one place, so a new command is one line and one function.
 * @returns {Record<string, (args: ParsedArgs, run: Run) => number>}
 */
function _commandHandlers() {
  return {
    write: _cmdWrite,
    unpark: _cmdUnpark,
    digest: _cmdDigest,
    list: _cmdList,
    hold: _cmdHold,
    release: _cmdRelease,
    job: _cmdJob,
    active: _cmdActive,
    close: _cmdClose,
    export: _cmdExport,
    "local-id": _cmdLocalId,
  };
}

/**
 * The machine this session acts as: the flag when given, the host's label otherwise.
 *
 * One value serves both the holder it records and the staleness comparison, so a session that names
 * its machine is never told its own lease came from another machine.
 * @param {ParsedArgs} args
 * @returns {string}
 */
function _effectiveMachine(args) {
  return _text(args, "machine") || _machineLabel();
}

/**
 * @param {ParsedArgs} args
 * @param {ParkData} texts
 * @returns {number}
 */
function _run(args, texts) {
  const rootValue = args.values.get("root");
  const root = _projectRoot(typeof rootValue === "string" ? pyPath(rootValue) : null, texts);
  const machine = _effectiveMachine(args);
  /** @type {Run} */
  const run = { root, texts, lease: { now: Date.now() / 1000, staleHours: texts.stale_after_hours, machine } };
  return _commandHandlers()[args.command](args, run);
}

/**
 * CLI entry point; a failure is one stderr line and exit 1.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} the process exit code: 0 on success, 1 on a refusal, 2 on a usage error
 */
export function main(argv = process.argv.slice(2)) {
  const parsed = _parse(argv);
  if (parsed === "help") {
    process.stdout.write(USAGE);
    return 0;
  }
  if (typeof parsed === "string") {
    process.stderr.write(`${PROG}: error: ${parsed}\n`);
    return 2;
  }
  const texts = _texts();
  try {
    return _run(parsed, texts);
  } catch (exc) {
    if (!(exc instanceof ParkError)) {
      throw exc;
    }
    process.stderr.write(`error: ${exc.message}\n`);
    return 1;
  }
}

/**
 * Whether node was told to execute `invoked` as this very module (see `akmon/cli.mjs`).
 * @param {string} invoked `process.argv[1]`, the path node was given
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = main();
}
