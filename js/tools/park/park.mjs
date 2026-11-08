#!/usr/bin/env node
/**
 * The park helper: hold, write, resume, digest and list the ergons of parked work — the JavaScript
 * twin of `tools/park/park.py` (ADR 0020 D01, ADR 0028 D02, D03, D06, D08–D12). The Python module is
 * the spec: the same files in the same bytes, the same stdout lines, the same `error:` lines, the
 * same exit codes; its docstring carries the full account of the ergon, its units (the plan and its
 * athlos), the note's header format and the derived states.
 *
 * The read-only command `worktrees` lists the git worktrees and the `_aitna/` branches with none, and
 * prints the commands that remove the removable ones; it removes nothing itself.
 *
 * The read-only command `local-id` prints the next free local id (`_T<n>`), counted over the live
 * ergons and the closed ones and never reused.
 *
 * An *ergon* is the folder `<dev root>/.ergon/<id>-<name>/` of one piece of work. Its plan is
 * `PLAN.md`; its units are the plan itself (the ergon root) and its athlos, each in the folder of its
 * own number (`<dev root>/.ergon/<id>-<name>/<n>/ATHLOS.md`, ADR 0029 D11). Parking a unit writes
 * `PARK.md` and `RESUME.md` into it atomically. A unit is held by a lease, the file `HOLDER`,
 * created exclusively and judged stale on read. There is no local index anymore: an ergon is its own
 * record, and `park list` is the index (ADR 0028 D12).
 *
 * A record written before the rename of ADR 0029 is read and translated: the `job` word, the
 * `jobs/<n>-<label>/JOB.md` layout, the `job:` key of a note and the retired local index. An old form
 * is never written (ADR 0029 D12).
 *
 * Data (the C102 convention): the tool's texts are `tools/park/park.json`, read once by `main` (and
 * by `digest` when it is called alone) and passed down as `texts`.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the dataclasses are frozen plain objects with camelCase keys (`nextAction`, `ownedPaths`,
 *   `sessionId`, `ageDays`, `staleHours`); `parkFields` and `parkBody` fill the defaults the
 *   dataclasses carry; a dataclass method is a function that takes the object first
 *   (`holderSameAs`, `holderLabel`, `leaseAgeSeconds`, `athlosDocNextStep`);
 * - the arguments are parsed by a small `argparse`-shaped scanner (DV12): a usage error is the one
 *   line `park.mjs: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0.
 *   Options are accepted before and after the subcommand's positional, `--root` and `--project-root`
 *   are one option, and a value such as `-1` or `- two words` is a value, as `argparse` takes it;
 * - character counts (the digest cap, the 60-character cut of `next`) count code points, and ergon ids
 *   and file paths sort by code point (a path by its components), as Python's `len` and `sorted` do;
 * - a path the helper prints follows the one rule of `_displayPath`, as in Python: from the session's
 *   project root when it lies inside, absolute when it does not (the ergons of a linked worktree stay
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
 * @property {{line: string, unreadable: string, athlos_line: string, empty: string, no_match: string, warning_shared_paths: string}} list
 * @property {{none: string, line: string}} active
 * @property {{columns: string[], separator: string, yes: string, no: string, detached: string, kinds: {main: string, athlos: string, harness: string, branch_only: string}, states: {main: string, harness: string, working: string, ready: string, carried: string, backup: string, not_carried_backup: string}, command_worktree: string, command_branch: string, carry_cd: string, carry_squash: string, carry_commit: string, verdict_carried: string, verdict_not_carried: string, verdict_unreadable: string, verdict_missing: string, verdict_paths: number, verdict_more: string}} worktrees
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
 * @property {string} athlos
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
 * One athlos line of `PLAN.md`: the structure of an athlos, never its state (ADR 0028 D08).
 *
 * The line carries the zone beside the tasks (ADR 0029 D03): the pair (task id, zone) is the athlos's
 * content, its id is its place in the plan.
 * @typedef {object} AthlosLine
 * @property {string} id
 * @property {number} number
 * @property {string} label
 * @property {readonly string[]} tasks
 * @property {readonly string[]} after
 * @property {readonly string[]} paths
 * @property {string} harness
 * @property {string} result
 * @property {string} [zone]
 */

/**
 * The header of `PLAN.md`: the ergon's id, name, title and the tasks it carries.
 * @typedef {{readonly id: string, readonly name: string, readonly title: string, readonly tasks: readonly string[]}} PlanHeader
 */

/**
 * A plan: its header and its athlos lines.
 * @typedef {{readonly header: PlanHeader, readonly athlos: readonly AthlosLine[]}} Plan
 */

/**
 * An athlos's own file `ATHLOS.md`: its steps with their done marks, and whether it is done.
 * @typedef {{readonly header: ParkFields, readonly steps: readonly (readonly [string, boolean])[], readonly done: boolean}} AthlosDoc
 */

/**
 * One line of `list`: what an ergon says of itself, read from its folder.
 * @typedef {object} ErgonSummary
 * @property {string} id
 * @property {string} name
 * @property {string} state
 * @property {string} plan
 * @property {string} nextAction
 * @property {number} decisions
 * @property {string} branch
 * @property {number | null} ageDays
 * @property {string} [unreadable] why the ergon's files could not be read; the other fields are then empty
 */

/**
 * One athlos line of `list`: what an athlos says of itself, read from its folder.
 * @typedef {object} AthlosSummary
 * @property {string} id
 * @property {string} name
 * @property {string} state
 * @property {readonly string[]} tasks
 * @property {string} nextAction
 * @property {string} branch
 * @property {number | null} ageDays
 */

/**
 * The filters of `list`; an empty one matches every ergon.
 * @typedef {{readonly plan: string, readonly task: string, readonly state: string, readonly closed: boolean}} ListQuery
 */

/**
 * The keys of one flat header: their order, which hold a list, and which are read and ignored.
 * @typedef {{readonly order: readonly string[], readonly listKeys: readonly string[], readonly legacy: readonly string[], readonly renamed: readonly (readonly [string, string])[]}} HeaderSpec
 */

const PROG = "park.mjs";

const USAGE = `usage: ${PROG} [-h] {write,unpark,digest,list,hold,release,athlos,active,worktrees,close,export,local-id} ...

Park work into an ergon and resume it.

commands:
  write ID --name N --goal G --next X [--plan ID] [--row ID] [--owned-path P]... [--check C]...
        [--unverified U]... [--decision D]... [--answer A]... [--agent A]... [--readiness R]
        [--origin O] [--harness H] [--session-id S]
                        Park a piece of work.
  unpark ID [--harness H] [--session-id S]
                        Resume a parked ergon.
  digest ID [--cap N]   Print the capped digest.
  list [--plan ID] [--task ID] [--state S] [--closed]
                        List the ergons.
  hold ID [--number N] [--takeover] [--harness H] [--session-id S]
                        Take the lease of a unit.
  release ID [--number N]
                        Release the lease of a unit.
  athlos ID --number N [--step S]... [--done] [--harness H] [--session-id S]
                        Write an athlos's own file.
  active                Print the unit this session is in.
  worktrees [TARGET]    List the worktrees and backup branches by state; with a branch or athlos key, say if it is carried.
  close ID [--harness H] [--session-id S]
                        Close an ergon and move it to the closed folder.
  export ID --out FILE  Write the ergon to one bundle file.
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
const ATHLOS_FILE = "ATHLOS.md";
const HOLDER_FILE = "HOLDER";
const SESSIONS_FILE = "SESSIONS";
const HEADER_FENCE = "---";
const SESSION_PARTS = 3; // harness|session_id|machine
const GIT_TIMEOUT_MS = 10_000;
const GIT_REVISIONS = 5;
const STEPS_HEADING = "## Steps";
const DONE_MARKER = "done";
const STEP_UNDONE = "- [ ] ";
const STEP_DONE = "- [x] ";
const CLOSED_DIR = ".closed";
const WORKTREES_DIR = ".worktrees";
const BRANCH_NAMESPACE = "_aitna/"; // ADR 0028 D04: an athlos's branch is `_aitna/<id>-<name>.<n>`
const HEADS = "refs/heads/";
const TASK_SEPARATOR = "·";
const FIELD_SEPARATOR = ",";
const PATH_SEPARATOR = "/";
const ATHLOS_HEADING = "Athlos";
const LINE_BREAKS_RE = /[\r\n]+/g;
const ATHLOS_SOURCE_PARTS = 3; // ergon folder, athlos folder, `ATHLOS.md`

// Python's `$` also matches before a final newline, so `\n?$` keeps the twin's answer for a value
// that ends in one; `\p{Nd}` is Python's `\d`; `.` is `[^\n]` because Python's `.` takes `\r`.
const ID_RE = /^(?:[A-Z]\p{Nd}+|_T\p{Nd}+)\n?$/u; // ADR 0002 typed id, and a local id's _T<n> (ADR 0028 D12)
const ATHLOS_ID_RE = /^((?:[A-Z]\p{Nd}+|_T\p{Nd}+))\.(\p{Nd}+)\n?$/u;
const NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*\n?$/;
const ERGON_RE = /^([A-Z]\p{Nd}+|_T\p{Nd}+)-([a-z0-9]+(?:-[a-z0-9]+)*)\n?$/u;
const KEY_RE = /^([a-z_]+):(?: ([^\n]*))?$/;
const PURPOSE_KEY_RE = /^[a-z][a-z0-9_]*\n?$/;
const LOCAL_ID_RE = /^_T(\p{Nd}+)\n?$/u;
// The retired local index, in `<dev root>/.local/`, and one of its rows: `- _T6 · ...`.
const LEGACY_INDEX_FILE = "TASKS.md";
const LEGACY_ROW_RE = /^- _T([0-9]+)(?:[ \t]|$)/;
// The athlos layout a record written before ADR 0029 D11 carries: `jobs/<n>-<label>/JOB.md`, and the
// plan's section heading before ADR 0029 D02. Read and translated, never written.
const LEGACY_ATHLOS_DIR = "jobs";
const LEGACY_ATHLOS_FILE = "JOB.md";
const LEGACY_ATHLOS_HEADING = "Jobs";
// Python's `str.isdecimal()`: a run of Unicode decimal digits, which `int()` then reads.
const DIGITS_RE = /^\p{Nd}+$/u;
// `datetime.strptime("%Y-%m-%dT%H:%M:%SZ")`: the widths and ranges its directives accept.
const STAMP_RE =
  /^(\d{4})-(1[0-2]|0[1-9]|[1-9])-(3[01]|[12]\d|0[1-9]|[1-9]| [1-9])T(2[0-3]|[01]\d|\d):([0-5]\d|\d):(6[01]|[0-5]\d|\d)Z$/;

// Header keys in their written order, and which of them hold a list: the one table the renderer and
// the parser share. `nextAction` is written as `next`.
const SCALAR_KEYS = ["id", "name", "plan", "athlos", "row", "branch", "next", "origin", "readiness", "written"];
const LIST_KEYS = ["revisions", "owned_paths", "tasks", "sessions"];
const HEADER_ORDER = [
  "id",
  "name",
  "plan",
  "athlos",
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
// A key renamed by ADR 0029 D02, as `[old, new]`: read under the new spelling, never written again.
/** @type {readonly (readonly [string, string])[]} */
const RENAMED_KEYS = [["job", "athlos"]];
// The keys of the lease file `HOLDER`, in their written order.
const LEASE_KEYS = ["harness", "session", "machine", "worktree", "written"];

/**
 * The header of a park note and the header of a lease: the two flat formats the helper reads.
 * @type {HeaderSpec}
 */
export const NOTE_HEADER = Object.freeze({
  order: HEADER_ORDER,
  listKeys: LIST_KEYS,
  legacy: LEGACY_KEYS,
  renamed: RENAMED_KEYS,
});
/** @type {HeaderSpec} */
export const LEASE_HEADER = Object.freeze({ order: LEASE_KEYS, listKeys: [], legacy: [], renamed: [] });

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
    athlos: "",
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
 * The ergons of a linked worktree live in the main checkout (ADR 0028 D12), outside the session's
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
function _checkAthlosId(value, label, texts) {
  if (!ATHLOS_ID_RE.test(value)) {
    throw _error(texts, "bad_athlos_id", { label, value });
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
  if (fields.athlos !== "") {
    _checkAthlosId(fields.athlos, "athlos", texts);
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
    athlos: fields.athlos,
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
  // A key the release renamed is read under its new spelling, never written in the old one.
  const named = spec.renamed.find(([previous]) => previous === key)?.[1] ?? key;
  if (!spec.order.includes(named) || values.has(named)) {
    throw _error(texts, "header_key", { path: source, key });
  }
  if (spec.listKeys.includes(named)) {
    if (value !== "") {
      throw _error(texts, "header_scalar_list", { path: source, key });
    }
    values.set(named, []);
    return { opened: named, legacyList: false };
  }
  values.set(named, value);
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
    athlos: _scalar(values, "athlos"),
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
  const lines = [fill(texts.note.title, { ergon: `${fields.id}-${fields.name}` }), ""];
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
    ergon: `${fields.id}-${fields.name}`,
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
  const lines = [fill(spec.title, { ergon: `${fields.id}-${fields.name}`, state })];
  for (const [key, value] of [
    ["plan", fields.plan],
    ["athlos", fields.athlos],
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
 * The fields and the body of the ergon's `PARK.md`; an ergon without one was never parked.
 * @param {string} ergon
 * @param {ParkData} texts
 * @returns {{fields: ParkFields, body: ParkBody}}
 * @throws {ParkError} the ergon has no `PARK.md`, or its note does not parse
 */
export function readNote(ergon, texts) {
  const note = pyPath(ergon, PARK_FILE);
  const name = posix.basename(ergon);
  if (!isFile(note)) {
    throw _error(texts, "never_parked", { ergon: name });
  }
  return parseNote(readText(note), `${name}/${PARK_FILE}`, texts);
}

/**
 * The capped digest of an ergon's note: whole lines up to `cap` characters, then the overflow line.
 *
 * `cap` counts the code points of the lines kept, newline included; the overflow line
 * (`… N more lines in <path>`) is appended after them and is not counted. With `root` the
 * path is the note's path from the project root, otherwise `<ergon name>/PARK.md`. `machine` is
 * the one the caller judges a lease against, so the digest reads a copied lease stale exactly as
 * `list` does.
 * @param {string} ergon
 * @param {number} cap
 * @param {string | null} [root]
 * @param {ParkData | null} [data] the tool's texts; read from `park.json` when omitted
 * @param {string} [machine]
 * @returns {string}
 * @throws {ParkError} the ergon was never parked or its note does not parse
 */
export function digest(ergon, cap, root = null, data = null, machine = "") {
  const texts = data ?? _texts();
  const { fields, body } = readNote(ergon, texts);
  const context = { now: Date.now() / 1000, staleHours: texts.stale_after_hours, machine };
  const lines = digestLines(fields, body, ergonState(ergon, texts, context), texts);
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
    const where =
      root === null ? `${posix.basename(ergon)}/${PARK_FILE}` : _displayPath(pyPath(ergon, PARK_FILE), root);
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
 * The epoch seconds of an ISO stamp.
 *
 * A stamp that is not one is refused, never read as the epoch: `0` would make a corrupt lease older
 * than any threshold, so a live holder's unit would read as free.
 * @param {string} value
 * @param {string} source the file the stamp was read from, named in the error
 * @param {ParkData} texts
 * @returns {number}
 * @throws {ParkError} the value is not a UTC stamp
 */
function _parseStamp(value, source, texts) {
  const match = STAMP_RE.exec(value);
  if (match === null) {
    throw _error(texts, "bad_stamp", { path: source, key: "written", value });
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
  if (!valid) {
    throw _error(texts, "bad_stamp", { path: source, key: "written", value });
  }
  return moment.getTime() / 1000;
}

/**
 * The lease a `HOLDER` file declares.
 * @param {string} text
 * @param {string} source
 * @param {ParkData} texts
 * @returns {Lease}
 * @throws {ParkError} the file has no header, a line is malformed, or its stamp is not one
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
  return { holder, written: _parseStamp(String(values.get("written") ?? ""), source, texts) };
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
 * A lease that came with a copied ergon names another machine, and is stale at once.
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
 * Release every lease of an ergon: the plan's and its athlos'.
 * @param {string} ergon
 */
export function releaseLeases(ergon) {
  releaseLease(ergon);
  for (const folder of _athlosFolders(ergon)) {
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
 * The file that carries a unit's sessions: `PARK.md` for an ergon, an athlos's file, or `null`.
 * @param {string} unit
 * @returns {string | null}
 */
function _unitNote(unit) {
  for (const name of [PARK_FILE, ATHLOS_FILE, LEGACY_ATHLOS_FILE]) {
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
 * The header of a unit's note carries the sessions the work was done in (`PARK.md` for an ergon,
 * `ATHLOS.md` for an athlos); a holder that is taken over stays among them, so the note says who held the
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
 * @param {string} note the `PARK.md` or `ATHLOS.md` path
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
  const doc = parseAthlosDoc(text, source, texts);
  return {
    sessions: doc.header.sessions,
    render: (sessions) => renderAthlosDoc({ ...doc, header: { ...doc.header, sessions } }, texts),
  };
}

// --------------------------------------------------------------------------------------
// the plan: its header and its athlos lines, read from `PLAN.md`
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
 * One athlos line cell as `[key, value]`: `tasks C186` and `result: text` both parse.
 *
 * A cell that carries its colon and no value (`result:`) is the key with an empty value, not a key
 * named `result:` — the empty value is what the caller refuses (ADR 0029 D03).
 * @param {string} cell
 * @returns {[string, string]}
 */
function _athlosField(cell) {
  const colon = cell.indexOf(": ");
  if (colon >= 0) {
    return [pyStrip(cell.slice(0, colon)), pyStrip(cell.slice(colon + 2))];
  }
  const space = cell.indexOf(" ");
  const key = pyStrip(space < 0 ? cell : cell.slice(0, space)).replace(/:+$/, "");
  const value = space < 0 ? "" : pyStrip(cell.slice(space + 1));
  return [key, value];
}

/**
 * One athlos line of a plan as an `AthlosLine`; a line that is not one is skipped (`null`).
 *
 * A cell whose key the format does not carry is refused, not dropped: a plan line is structure, and
 * a field the reader cannot see is a field the plan silently loses (ADR 0029 D03).
 * @param {string} line
 * @param {ParkData} texts
 * @returns {AthlosLine | null}
 * @throws {ParkError} a cell names an unknown field
 */
export function parseAthlosLine(line, texts) {
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
  const match = ATHLOS_ID_RE.exec(cells[0]);
  if (match === null) {
    return null;
  }
  const listedFields = ["tasks", "after", "paths"];
  /** @type {Record<string, string | string[]>} */
  const fields = { tasks: [], after: [], paths: [], harness: "", result: "", zone: "" };
  for (const cell of cells.slice(2)) {
    const [key, value] = _athlosField(cell);
    if (!Object.hasOwn(fields, key)) {
      throw _error(texts, "unknown_field", { id: cells[0], key });
    }
    fields[key] = listedFields.includes(key) ? _splitValues(value) : value;
  }
  return {
    id: cells[0],
    number: pyInt(match[2]),
    label: cells[1],
    tasks: /** @type {string[]} */ (fields.tasks),
    after: /** @type {string[]} */ (fields.after),
    paths: /** @type {string[]} */ (fields.paths),
    harness: /** @type {string} */ (fields.harness),
    result: /** @type {string} */ (fields.result),
    zone: /** @type {string} */ (fields.zone),
  };
}

/**
 * A plan file as its header and its athlos lines.
 *
 * The section heading of the lines is read under its new name and the one a plan written before
 * ADR 0029 D02 carries; only the new one is ever written.
 * @param {string} text
 * @param {ParkData} texts
 * @returns {Plan}
 * @throws {ParkError} an athlos line carries a field the format does not know
 */
export function parsePlan(text, texts) {
  const values = _planValues(text);
  const header = {
    id: values.get("id") ?? "",
    name: values.get("name") ?? "",
    title: values.get("title") ?? "",
    tasks: _splitValues(values.get("tasks") ?? ""),
  };
  const sections = _sections(text);
  const lines = sections.get(ATHLOS_HEADING) ?? sections.get(LEGACY_ATHLOS_HEADING) ?? [];
  const athlosLines = lines.filter((line) => pyStrip(line) !== "");
  const athlos = athlosLines.map((line) => parseAthlosLine(line, texts)).filter((line) => line !== null);
  return { header, athlos };
}

/**
 * The plan of an ergon, or `null` when it has none.
 * @param {string} ergon
 * @param {ParkData} texts
 * @returns {Plan | null}
 * @throws {ParkError} an athlos line of the plan carries an unknown field
 */
export function readPlan(ergon, texts) {
  const path = pyPath(ergon, PLAN_FILE);
  return isFile(path) ? parsePlan(readText(path), texts) : null;
}

/**
 * Whether two forecast paths of two athlos may touch the same file.
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
 * The athlos ids that wait, directly or through a chain of athlos, for `athlosId`.
 * @param {ReadonlyMap<string, AthlosLine>} athlos
 * @param {string} athlosId
 * @returns {Set<string>}
 */
function _athlosWaitingFor(athlos, athlosId) {
  /** @type {Set<string>} */
  const reached = new Set();
  const pending = [athlosId];
  while (pending.length > 0) {
    const current = /** @type {string} */ (pending.pop());
    for (const other of athlos.values()) {
      if (other.after.includes(current) && !reached.has(other.id)) {
        reached.add(other.id);
        pending.push(other.id);
      }
    }
  }
  return reached;
}

/**
 * Whether one of the two athlos waits for the other, directly or through a chain of them.
 *
 * The chain matters: an athlos that waits for an athlos that waits for another cannot run at once with it,
 * so the pair shares no warning. Only athlos ids of this plan order athlos; an `after` that names a task id orders nothing here.
 * @param {AthlosLine} one
 * @param {AthlosLine} other
 * @param {Plan} plan
 * @returns {boolean}
 */
function _athlosOrders(one, other, plan) {
  const athlos = new Map(plan.athlos.map((athlos) => [athlos.id, athlos]));
  return _athlosWaitingFor(athlos, one.id).has(other.id) || _athlosWaitingFor(athlos, other.id).has(one.id);
}

/**
 * The warnings of a plan: two athlos that may run at once and forecast the same path.
 *
 * The forecast is advice, not a fact; the owned uncommitted paths of each note are the fact.
 * @param {Plan} plan
 * @param {ParkData} texts
 * @returns {string[]}
 */
export function sharedPathWarnings(plan, texts) {
  /** @type {string[]} */
  const warnings = [];
  for (const [index, one] of plan.athlos.entries()) {
    for (const other of plan.athlos.slice(index + 1)) {
      if (_athlosOrders(one, other, plan)) {
        continue;
      }
      const shared = new Set(
        one.paths.flatMap((path) => other.paths.filter((otherPath) => _pathsOverlap(path, otherPath)).map(() => path)),
      );
      for (const path of [...shared].sort(_compareCodePoints)) {
        warnings.push(fill(texts.list.warning_shared_paths, { athlos: `${one.id} ${other.id}`, path }));
      }
    }
  }
  return warnings;
}

// --------------------------------------------------------------------------------------
// an athlos's own file: its steps with their done marks, and whether it is done
// --------------------------------------------------------------------------------------

/**
 * The first step of an athlos that is not done, or the empty string when every step is done.
 * @param {AthlosDoc} doc
 * @returns {string}
 */
export function athlosDocNextStep(doc) {
  for (const [text, isDone] of doc.steps) {
    if (!isDone) {
      return text;
    }
  }
  return "";
}

/**
 * The whole `ATHLOS.md`: its header, its steps and, once the result is met, the done mark.
 * @param {AthlosDoc} doc
 * @param {ParkData} texts
 * @returns {string}
 */
export function renderAthlosDoc(doc, texts) {
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
 * The `AthlosDoc` a `ATHLOS.md` declares: its header, its steps and its done mark.
 * @param {string} text
 * @param {string} source
 * @param {ParkData} texts
 * @returns {AthlosDoc}
 * @throws {ParkError} the file has no header, or a line is malformed
 */
export function parseAthlosDoc(text, source, texts) {
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
 * The athlos file of an athlos folder, or `null` when it has none.
 * @param {string} path the `ATHLOS.md` path
 * @param {ParkData} texts
 * @returns {AthlosDoc | null}
 */
export function readAthlosDoc(path, texts) {
  if (!isFile(path)) {
    return null;
  }
  const source = path.split("/").slice(-ATHLOS_SOURCE_PARTS).join("/"); // <ergon>/<n>/ATHLOS.md: the ergon is named
  return parseAthlosDoc(readText(path), source, texts);
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
// the ergons of a project
// --------------------------------------------------------------------------------------

/**
 * The names of the ergon folders under `.ergon/` (`<id>-<name>` only), sorted.
 * @param {string} root
 * @param {{closed?: boolean}} [options] `closed` reads `.ergon/.closed/` instead
 * @returns {string[]}
 */
function _ergonNames(root, { closed = false } = {}) {
  let ergon = ergonRoot(root);
  if (closed) {
    ergon = pyPath(ergon, CLOSED_DIR);
  }
  if (!isDir(ergon)) {
    return [];
  }
  return fs
    .readdirSync(ergon)
    .filter((name) => isDir(pyPath(ergon, name)) && ERGON_RE.test(name))
    .sort(_compareCodePoints);
}

/**
 * @param {string} ergonName
 * @returns {string}
 */
function _ergonId(ergonName) {
  const match = ERGON_RE.exec(ergonName);
  if (match === null) {
    throw new Error(`not an ergon name: ${ergonName}`);
  }
  return match[1];
}

/**
 * @param {string} root
 * @param {string} ergonId
 * @param {ParkData} texts
 * @param {boolean} closed
 * @returns {string}
 */
function _findErgonIn(root, ergonId, texts, closed) {
  const names = _ergonNames(root, { closed });
  const found = names.filter((name) => _ergonId(name) === ergonId);
  const ergon = _displayPath(ergonRoot(root), root);
  if (found.length === 0) {
    throw _error(texts, "no_ergon", { id: ergonId, ergon, ergons: names.join(", ") || "none" });
  }
  if (found.length > 1) {
    throw _error(texts, "several_ergons", { id: ergonId, ergon, ergons: found.join(", ") });
  }
  const base = closed ? pyPath(ergonRoot(root), CLOSED_DIR) : ergonRoot(root);
  return pyPath(base, found[0]);
}

/**
 * The ergon folder whose name leads with `ergonId`.
 * @param {string} root
 * @param {string} ergonId
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} no ergon or several ergons carry the id; the message names the candidates
 */
export function findErgon(root, ergonId, texts) {
  return _findErgonIn(root, ergonId, texts, false);
}

/**
 * The closed ergon folder whose name leads with `ergonId`, or `null`.
 * @param {string} root
 * @param {string} ergonId
 * @param {ParkData} texts
 * @returns {string | null}
 */
export function findClosedErgon(root, ergonId, texts) {
  try {
    return _findErgonIn(root, ergonId, texts, true);
  } catch (exc) {
    if (!(exc instanceof ParkError)) {
      throw exc;
    }
    return null;
  }
}

/**
 * The athlos file of a folder: `ATHLOS.md`, or the `JOB.md` a record written before ADR 0029 D11
 * carries. The answer is a path whether or not either exists, so a writer gets the new name and a
 * reader still finds the old one.
 * @param {string} folder
 * @returns {string}
 */
export function athlosFileOf(folder) {
  const fresh = pyPath(folder, ATHLOS_FILE);
  if (isFile(fresh)) {
    return fresh;
  }
  const legacy = pyPath(folder, LEGACY_ATHLOS_FILE);
  return isFile(legacy) ? legacy : fresh;
}

/**
 * The number an athlos folder carries: its whole name, or the lead of a legacy `<n>-<label>`.
 * @param {string} folder
 * @returns {number | null}
 */
function _athlosNumber(folder) {
  const name = posix.basename(folder);
  if (DIGITS_RE.test(name)) {
    return pyInt(name);
  }
  const head = name.split("-")[0];
  return DIGITS_RE.test(head) ? pyInt(head) : null;
}

/**
 * The folder of the athlos of this number, in either layout, or `null` when the ergon has none.
 *
 * The new layout names the folder by the number alone (ADR 0029 D11); the `jobs/<n>-<label>/` of a
 * record written before it is read and translated (ADR 0029 D12).
 * @param {string} ergon
 * @param {number} number
 * @returns {string | null}
 */
export function athlosFolder(ergon, number) {
  const fresh = pyPath(ergon, String(number));
  if (isDir(fresh)) {
    return fresh;
  }
  const legacy = pyPath(ergon, LEGACY_ATHLOS_DIR);
  if (!isDir(legacy)) {
    return null;
  }
  for (const name of fs.readdirSync(legacy).sort(_compareCodePoints)) {
    const folder = pyPath(legacy, name);
    if (isDir(folder) && _athlosNumber(folder) === number) {
      return folder;
    }
  }
  return null;
}

/**
 * The athlos folders of an ergon, by number: the new layout, plus the `jobs/` of an old record.
 *
 * One number has one folder in the listing: where both layouts hold it, the new one is the record.
 * @param {string} ergon
 * @returns {string[]}
 */
function _athlosFolders(ergon) {
  /** @type {Map<number, string>} */
  const found = new Map();
  if (isDir(ergon)) {
    for (const name of fs.readdirSync(ergon).sort(_compareCodePoints)) {
      if (DIGITS_RE.test(name) && isDir(pyPath(ergon, name))) {
        found.set(pyInt(name), pyPath(ergon, name));
      }
    }
  }
  const legacy = pyPath(ergon, LEGACY_ATHLOS_DIR);
  if (isDir(legacy)) {
    for (const name of fs.readdirSync(legacy).sort(_compareCodePoints)) {
      const folder = pyPath(legacy, name);
      const number = isDir(folder) ? _athlosNumber(folder) : null;
      if (number !== null && !found.has(number)) {
        found.set(number, folder);
      }
    }
  }
  const numbers = [...found.keys()].sort((one, other) => one - other);
  return numbers.map((number) => /** @type {string} */ (found.get(number)));
}

/**
 * The folder of the athlos named by `athlosId` (`<ergon-id>.<n>`), in either layout.
 *
 * The number of the id is the folder's name; a folder a hand made under another name is still found
 * by the id its athlos file carries.
 * @param {string} ergon
 * @param {string} athlosId
 * @param {ParkData} texts
 * @returns {string | null}
 */
export function findAthlosFolder(ergon, athlosId, texts) {
  const match = ATHLOS_ID_RE.exec(athlosId);
  if (match !== null) {
    const byNumber = athlosFolder(ergon, pyInt(match[2]));
    if (byNumber !== null) {
      return byNumber;
    }
  }
  for (const folder of _athlosFolders(ergon)) {
    const doc = readAthlosDoc(athlosFileOf(folder), texts);
    if (doc !== null && doc.header.athlos === athlosId) {
      return folder;
    }
  }
  return null;
}

/**
 * The folder an athlos's file is written into: `<ergon>/<n>/`, the old record moved there when it
 * sits in `jobs/`.
 *
 * An old form is never written (ADR 0029 D12), so the write that meets a record in the retired layout
 * carries the whole folder — its file, its lease and its notes — to the folder of the athlos's number,
 * once. Where the new folder already stands the old one is left for the owner's one rewrite of the
 * records this release did not touch.
 * @param {string} ergon
 * @param {number} number
 * @param {string | null} current the folder the record lives in now, or `null` for a new athlos
 * @returns {string}
 */
export function moveAthlosFolder(ergon, number, current) {
  const fresh = pyPath(ergon, String(number));
  if (current === null || current === fresh || fs.existsSync(fresh)) {
    return fresh;
  }
  fs.renameSync(current, fresh);
  const legacyFile = pyPath(fresh, LEGACY_ATHLOS_FILE);
  if (isFile(legacyFile) && !isFile(pyPath(fresh, ATHLOS_FILE))) {
    fs.renameSync(legacyFile, pyPath(fresh, ATHLOS_FILE));
  }
  _removeIfEmpty(pyPath(ergon, LEGACY_ATHLOS_DIR));
  return fresh;
}

/**
 * The id of an athlos of an ergon: the ergon's id and the athlos's number.
 * @param {string} ergonId
 * @param {number} number
 * @returns {string}
 */
export function athlosIdOf(ergonId, number) {
  return `${ergonId}.${number}`;
}

/**
 * The derived state of a unit (ADR 0028 D09): active, parked, not started or done.
 *
 * A stale lease holds nothing: the unit is free, and the lease is offered to the owner.
 * @param {string} unit
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @param {{athlosDone?: boolean}} [options]
 * @returns {string}
 */
export function unitState(unit, texts, context, { athlosDone = false } = {}) {
  const states = _states(texts);
  if (athlosDone) {
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
 * The state of an ergon, joined from its athlos and its own lease and note (ADR 0028 D08, D09).
 *
 * An ergon is **active** when it or any of its athlos is held, else **done** when every athlos is done, else
 * **parked** when it or any of its athlos is parked, else **not started**. With a plan that lists
 * athlos, "every athlos" is every listed athlos: it has a folder whose `ATHLOS.md` is done, and an athlos with no
 * folder has not started. With no plan, or a plan that lists no athlos, the athlos folders that exist
 * decide. An ergon whose athlos are all done is done even when its own note is still there; only a live
 * lease on the ergon itself outranks that.
 * @param {string} ergon
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {string}
 */
export function ergonState(ergon, texts, context) {
  const states = _states(texts);
  const docs = _athlosFolders(ergon).map((folder) => ({ folder, doc: readAthlosDoc(athlosFileOf(folder), texts) }));
  const athlosStates = docs.flatMap(({ folder, doc }) =>
    doc === null ? [] : [unitState(folder, texts, context, { athlosDone: doc.done })],
  );
  const own = unitState(ergon, texts, context);
  if ([own, ...athlosStates].includes(states.active)) {
    return states.active;
  }
  const plan = readPlan(ergon, texts);
  if (plan !== null && plan.athlos.length > 0) {
    const doneIds = new Set(docs.filter(({ doc }) => doc !== null && doc.done).map(({ doc }) => doc?.header.athlos));
    if (plan.athlos.every((line) => doneIds.has(line.id))) {
      return states.done;
    }
  } else if (docs.length > 0 && docs.every(({ doc }) => doc !== null && doc.done)) {
    return states.done;
  }
  return [own, ...athlosStates].includes(states.parked) ? states.parked : states.not_started;
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
// writing an ergon and an athlos
// --------------------------------------------------------------------------------------

/**
 * Park the work: write `RESUME.md` and `PARK.md` into the ergon folder.
 *
 * The ergon folder is created when missing. Everything that can be refused is checked before any
 * file is touched; the files then land together (`writeFiles`), `PARK.md` last among the ergon's, and
 * a failure removes the folder it created when that folder is still empty.
 *
 * The sessions of the note are kept, not rebuilt: the sessions an earlier write recorded, the holder a
 * takeover kept (`SESSIONS` when the ergon had no note yet), and then the ones on this command line.
 *
 * The branch and the revisions come from git, and the note records the time it was written.
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {string} root
 * @param {ParkData} texts
 * @param {string} cwd where git is asked for the branch and the revisions
 * @returns {string} the ergon folder
 * @throws {ParkError} a field fails its check, an ergon with this id has another name, a closed ergon has
 *   this id and name, or the note already there does not parse
 */
export function writeErgon(fields, body, root, texts, cwd) {
  checkFields(fields, texts);
  checkBody(body, texts);
  refuseErgonConflict(fields, root, texts);
  const ergon = pyPath(ergonRoot(root), `${fields.id}-${fields.name}`);
  const parkPath = _displayPath(pyPath(ergon, PARK_FILE), root);
  const sessions = mergeSessions(_noteSessions(ergon, texts), readPendingSessions(ergon, texts), fields.sessions);
  const stamped = { ...fields, sessions, branch: gitBranch(cwd), revisions: gitRevisions(cwd), written: nowStamp() };
  /** @type {[string, string][]} */
  const files = [
    [pyPath(ergon, RESUME_FILE), renderResume(stamped, body, parkPath, texts)],
    [pyPath(ergon, PARK_FILE), renderNote(stamped, body, texts)],
  ];
  const created = !isDir(ergon);
  try {
    fs.mkdirSync(ergon, { recursive: true });
    writeFiles(files);
  } catch (error) {
    if (created) {
      _removeIfEmpty(ergon);
    }
    throw error;
  }
  unlinkMissingOk(pyPath(ergon, SESSIONS_FILE)); // merged into the note just written
  return ergon;
}

/**
 * The sessions the ergon's note already carries; none when the ergon has no note yet.
 * @param {string} ergon
 * @param {ParkData} texts
 * @returns {readonly SessionRef[]}
 */
function _noteSessions(ergon, texts) {
  if (!isFile(pyPath(ergon, PARK_FILE))) {
    return [];
  }
  return readNote(ergon, texts).fields.sessions;
}

/**
 * Refuse an ergon whose id is taken by another name, or whose id and name belong to a closed ergon.
 *
 * A closed ergon keeps its id and name for good, so a write never reuses them; `local-id` counts the
 * closed ergons for the same reason.
 * @param {ParkFields} fields
 * @param {string} root
 * @param {ParkData} texts
 * @throws {ParkError} a live or closed ergon carries the id under another name, or a closed ergon has both
 */
export function refuseErgonConflict(fields, root, texts) {
  const ergonName = `${fields.id}-${fields.name}`;
  const closedNames = _ergonNames(root, { closed: true });
  const other = [..._ergonNames(root), ...closedNames].filter(
    (name) => _ergonId(name) === fields.id && name !== ergonName,
  );
  if (other.length > 0) {
    throw _error(texts, "ergon_other_name", { existing: other[0], id: fields.id, name: fields.name });
  }
  if (closedNames.includes(ergonName)) {
    throw _error(texts, "ergon_closed", { ergon: ergonName });
  }
}

/**
 * Write an athlos's own file, creating its folder when missing; a reader sees the old file or the new one.
 * @param {string} folder
 * @param {AthlosDoc} doc
 * @param {ParkData} texts
 */
export function writeAthlosDoc(folder, doc, texts) {
  fs.mkdirSync(folder, { recursive: true });
  _writeAtomically(pyPath(folder, ATHLOS_FILE), renderAthlosDoc(doc, texts));
}

/**
 * Refuse an athlos file whose header would not read back, naming the ergon and the offending value.
 *
 * The header is built from the plan's header and athlos line, so the plan is what is at fault: a plan
 * `id` that is no task id, say, would make a `ATHLOS.md` that `park list` cannot parse.
 * @param {AthlosDoc} doc
 * @param {string} ergonName
 * @param {ParkData} texts
 * @throws {ParkError} the plan's header or athlos line breaks the header's contract
 */
function _checkAthlosDoc(doc, ergonName, texts) {
  try {
    checkFields(doc.header, texts);
  } catch (error) {
    if (error instanceof ParkError) {
      throw _error(texts, "bad_plan", { ergon: ergonName, reason: error.message });
    }
    throw error;
  }
}

/**
 * The athlos file an athlos starts with: its header from the plan's athlos line, no steps yet.
 * @param {AthlosLine} athlos
 * @param {string} ergonId
 * @param {string} ergonName
 * @param {Plan | null} plan
 * @param {string} cwd where git is asked for the branch
 * @returns {AthlosDoc}
 */
export function athlosDocFor(athlos, ergonId, ergonName, plan, cwd) {
  const header = parkFields({
    id: ergonId,
    name: ergonName,
    nextAction: athlos.result,
    plan: plan !== null ? plan.header.id : "",
    athlos: athlos.id,
    tasks: athlos.tasks,
    branch: gitBranch(cwd),
  });
  return { header, steps: [], done: false };
}

// --------------------------------------------------------------------------------------
// the listing: the ergons, their athlos, and the states derived from the folders
// --------------------------------------------------------------------------------------

/**
 * What `list` says of one ergon; an ergon with no `PARK.md` has no age and no next action.
 * @param {string} ergon
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {ErgonSummary}
 */
export function summarizeErgon(ergon, texts, context) {
  const ergonName = posix.basename(ergon);
  const id = _ergonId(ergonName);
  const name = Array.from(ergonName)
    .slice(Array.from(id).length + 1)
    .join("");
  const note = pyPath(ergon, PARK_FILE);
  if (!isFile(note)) {
    return {
      id,
      name,
      state: ergonState(ergon, texts, context),
      plan: "",
      nextAction: "",
      decisions: 0,
      branch: "",
      ageDays: null,
    };
  }
  const { fields, body } = readNote(ergon, texts);
  return {
    id,
    name,
    state: ergonState(ergon, texts, context),
    plan: fields.plan,
    nextAction: fields.nextAction,
    decisions: body.decisions.length,
    branch: fields.branch,
    ageDays: _ageDays(note, context.now),
  };
}

/**
 * What `list` says of one athlos, or `null` when the folder carries no athlos file.
 * @param {string} folder
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {AthlosSummary | null}
 */
export function summarizeAthlos(folder, texts, context) {
  const doc = readAthlosDoc(athlosFileOf(folder), texts);
  if (doc === null) {
    return null;
  }
  const state = unitState(folder, texts, context, { athlosDone: doc.done });
  return {
    id: doc.header.athlos || posix.basename(folder),
    name: posix.basename(folder),
    state,
    tasks: doc.header.tasks,
    nextAction: athlosDocNextStep(doc),
    branch: doc.header.branch,
    ageDays: _ageDays(athlosFileOf(folder), context.now),
  };
}

/**
 * The task ids an ergon carries: from its plan header, its athlos lines and its athlos files.
 * @param {string} ergon
 * @param {readonly AthlosSummary[]} summaries
 * @param {ParkData} texts
 * @returns {string[]}
 * @throws {ParkError} an athlos line of the plan carries an unknown field
 */
function _ergonTasks(ergon, summaries, texts) {
  /** @type {string[]} */
  const tasks = [];
  const plan = readPlan(ergon, texts);
  if (plan !== null) {
    tasks.push(...plan.header.tasks);
    for (const line of plan.athlos) {
      tasks.push(...line.tasks);
    }
  }
  for (const summary of summaries) {
    tasks.push(...summary.tasks);
  }
  return tasks;
}

/**
 * Whether an ergon passes the filters of `list`.
 * @param {ErgonSummary} summary
 * @param {readonly AthlosSummary[]} athlos
 * @param {string} ergon
 * @param {ListQuery} query
 * @param {ParkData} texts
 * @returns {boolean}
 */
function _matches(summary, athlos, ergon, query, texts) {
  if (query.plan && summary.plan !== query.plan) {
    return false;
  }
  if (query.state && summary.state !== query.state) {
    return false;
  }
  return !query.task || _ergonTasks(ergon, athlos, texts).includes(query.task);
}

/**
 * The ergons under `.ergon/` that match `query`, and the athlos of those ergons.
 *
 * Reads only: the local index is retired, so the folders are the whole record. An ergon whose files do
 * not parse is listed with its `unreadable` reason, whatever the filters, and the other ergons are
 * listed as usual.
 * @param {string} root
 * @param {ListQuery} query
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {{ergons: ErgonSummary[], athlos: AthlosSummary[]}}
 */
export function listErgons(root, query, texts, context) {
  /** @type {ErgonSummary[]} */
  const summaries = [];
  /** @type {AthlosSummary[]} */
  const units = [];
  const layer = ergonRoot(root);
  const entries = _ergonNames(root).map((name) => pyPath(layer, name));
  if (query.closed) {
    entries.push(..._ergonNames(root, { closed: true }).map((name) => pyPath(layer, CLOSED_DIR, name)));
  }
  for (const ergon of entries) {
    /** @type {ErgonSummary} */
    let summary;
    /** @type {(AthlosSummary | null)[]} */
    let summarized;
    try {
      summary = summarizeErgon(ergon, texts, context);
      summarized = _athlosFolders(ergon).map((folder) => summarizeAthlos(folder, texts, context));
    } catch (error) {
      if (!(error instanceof ParkError)) {
        throw error;
      }
      // one bad ergon is reported on its own line, never stops the others
      const ergonName = posix.basename(ergon);
      const id = _ergonId(ergonName);
      const name = Array.from(ergonName)
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
    const ergonAthlos = summarized.filter((item) => item !== null);
    if (!_matches(summary, ergonAthlos, ergon, query, texts)) {
      continue;
    }
    summaries.push(summary);
    units.push(...ergonAthlos);
  }
  return { ergons: summaries.sort((a, b) => _compareCodePoints(a.id, b.id)), athlos: units };
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
 * @param {ErgonSummary} item
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
 * One athlos line of `list`.
 * @param {AthlosSummary} item
 * @param {ParkData} texts
 * @returns {string}
 */
export function formatAthlos(item, texts) {
  const empty = texts.empty_cell;
  return fill(texts.list.athlos_line, {
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
 * The ergon id and the athlos number a worktree's folder names, or `null`.
 *
 * The folder is `<id>-<name>.<n>`: the ergon's own folder name and the athlos's number.
 * @param {string} folder
 * @returns {{ergonId: string, number: number} | null}
 */
export function worktreeUnit(folder) {
  const name = posix.basename(folder);
  const dot = name.lastIndexOf(".");
  const base = name.slice(0, Math.max(dot, 0));
  const tail = dot < 0 ? "" : name.slice(dot + 1);
  if (base === "" || !DIGITS_RE.test(tail)) {
    return null;
  }
  const match = ERGON_RE.exec(base);
  if (match === null) {
    return null;
  }
  return { ergonId: match[1], number: pyInt(tail) };
}

/**
 * The ergon and the athlos this session is in, read from the folder it works in.
 *
 * A session in the main checkout has no active unit until it picks one; a session in an athlos's
 * worktree is in that athlos, named by the worktree's own folder.
 * @param {string} root
 * @param {ParkData} texts
 * @returns {{ergon: string, ergonId: string, number: number} | null}
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
    return { ergon: findErgon(root, unit.ergonId, texts), ergonId: unit.ergonId, number: unit.number };
  } catch (exc) {
    if (!(exc instanceof ParkError)) {
      throw exc;
    }
    return null;
  }
}

// --------------------------------------------------------------------------------------
// the worktree list: every worktree git knows, what carries it, and which one may go (ADR 0029 D06, D09)
// --------------------------------------------------------------------------------------

/**
 * One entry of `git worktree list --porcelain`: the folder, its commit and its branch (the short
 * name; empty when HEAD is detached).
 * @typedef {{readonly path: string, readonly head: string, readonly branch: string, readonly bare: boolean}} GitWorktree
 */

/**
 * What a unit says of the branch and the folder it works in: read from its lease and its note.
 * `athlos` is empty for the ergon's own unit; `worktree` is the folder its live lease names, empty
 * when the lease is absent, stale or unnamed; `live` says a live lease holds the unit; `written` is
 * when its note was last written (epoch seconds).
 * @typedef {{readonly ergon: string, readonly athlos: string, readonly branch: string, readonly worktree: string, readonly live: boolean, readonly written: number}} UnitRecord
 */

/**
 * One row of `worktrees`: a worktree, or a branch whose worktree is gone, and what state its work is in. `path` is absolute (empty for a branch-only row), `shown` is the path as printed: from the
 * `.worktrees/` folder when inside it. `clean`, `ahead` and `ageSeconds` are `null` when git cannot
 * say; `differing` lists the paths the branch changed that the owner's branch does not hold alike
 * (`null` when git cannot compare); `state` is working, ready, carried, backup, not-carried backup,
 * harness or main; `removable` is a carried worktree or a carried backup branch; `subject` is the
 * subject of the branch's last commit, read for a ready row only.
 * @typedef {object} WorktreeRow
 * @property {string} path
 * @property {string} shown
 * @property {string} branch
 * @property {string} kind
 * @property {string} ergon
 * @property {string} athlos
 * @property {boolean | null} clean
 * @property {number | null} ahead
 * @property {number | null} ageSeconds
 * @property {boolean} carried
 * @property {readonly string[] | null} differing
 * @property {string} state
 * @property {boolean} removable
 * @property {string} subject
 */

/**
 * What every row of one `worktrees` call is judged against: where git runs, the owner's checkout, the
 * commit its branch stands at, the units to match, the texts and the clock.
 * @typedef {{readonly root: string, readonly main: string, readonly ownerTip: string, readonly units: readonly UnitRecord[], readonly texts: ParkData, readonly now: number}} Listing
 */

/**
 * The entries of `git worktree list --porcelain`, in git's order; blocks are split by a blank line.
 * @param {string} text
 * @returns {GitWorktree[]}
 */
export function parseWorktreeList(text) {
  return text
    .split("\n\n")
    .map(_worktreeBlock)
    .filter((entry) => entry.path !== "");
}

/**
 * One block of the porcelain listing: its `key value` lines, and the bare marker.
 * @param {string} block
 * @returns {GitWorktree}
 */
function _worktreeBlock(block) {
  const lines = block.split("\n");
  /** @param {string} key */
  const value = (key) => {
    const line = lines.find((entry) => entry.startsWith(`${key} `));
    return line === undefined ? "" : line.slice(key.length + 1);
  };
  const ref = value("branch");
  return {
    path: value("worktree"),
    head: value("HEAD"),
    branch: ref.startsWith(HEADS) ? ref.slice(HEADS.length) : ref,
    bare: lines.includes("bare"),
  };
}

/**
 * The ergon id and the athlos number an athlos's branch `_aitna/<id>-<name>.<n>` names, or `null`.
 * @param {string} branch
 * @returns {{ergonId: string, number: number} | null}
 */
export function branchUnit(branch) {
  if (!branch.startsWith(BRANCH_NAMESPACE)) {
    return null;
  }
  const rest = branch.slice(BRANCH_NAMESPACE.length);
  const dot = rest.lastIndexOf(".");
  const base = rest.slice(0, Math.max(dot, 0));
  const tail = dot < 0 ? "" : rest.slice(dot + 1);
  const match = ERGON_RE.exec(base);
  if (match === null || !DIGITS_RE.test(tail)) {
    return null;
  }
  return { ergonId: match[1], number: pyInt(tail) };
}

/**
 * `path` with its links resolved, or as it is when it does not exist.
 * @param {string} path
 * @returns {string}
 */
function _realPath(path) {
  try {
    return fs.realpathSync(path);
  } catch {
    return path;
  }
}

/**
 * @param {string} one
 * @param {string} other
 * @returns {boolean}
 */
function _samePath(one, other) {
  return one !== "" && other !== "" && _realPath(one) === _realPath(other);
}

/**
 * The lease of a unit when it is live; a stale one holds nothing.
 * @param {string} unit
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {Lease | null}
 */
function _liveLease(unit, texts, context) {
  const lease = readLease(unit, texts);
  return lease !== null && !leaseIsStale(lease, context) ? lease : null;
}

/**
 * What one unit says: its note's branch, and the folder its live lease names.
 * @param {string} unit
 * @param {string} ergonId
 * @param {string} athlos
 * @param {string} branch
 * @param {Lease | null} lease
 * @returns {UnitRecord}
 */
function _unitRecord(unit, ergonId, athlos, branch, lease) {
  const note = athlos !== "" ? athlosFileOf(unit) : pyPath(unit, PARK_FILE);
  const stat = pyStat(note);
  return {
    ergon: ergonId,
    athlos,
    branch,
    worktree: lease !== null ? lease.holder.worktree : "",
    live: lease !== null,
    written: stat !== null && stat.isFile() ? stat.mtimeMs / 1000 : 0,
  };
}

/**
 * The ergon's own unit and each athlos of every ergon, the closed ones too, as the list matches against.
 *
 * An ergon whose files do not parse is left out: one bad ergon never stops the list.
 * @param {string} root
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {UnitRecord[]}
 */
function _unitRecords(root, texts, context) {
  /** @type {UnitRecord[]} */
  const records = [];
  const layer = ergonRoot(root);
  const folders = [
    ..._ergonNames(root).map((name) => pyPath(layer, name)),
    ..._ergonNames(root, { closed: true }).map((name) => pyPath(layer, CLOSED_DIR, name)),
  ];
  for (const ergon of folders) {
    const ergonId = _ergonId(posix.basename(ergon));
    /** @type {UnitRecord[]} */
    const found = [];
    try {
      const noteBranch = isFile(pyPath(ergon, PARK_FILE)) ? readNote(ergon, texts).fields.branch : "";
      found.push(_unitRecord(ergon, ergonId, "", noteBranch, _liveLease(ergon, texts, context)));
      for (const folder of _athlosFolders(ergon)) {
        const doc = readAthlosDoc(athlosFileOf(folder), texts);
        if (doc !== null) {
          const athlos = doc.header.athlos || posix.basename(folder);
          found.push(_unitRecord(folder, ergonId, athlos, doc.header.branch, _liveLease(folder, texts, context)));
        }
      }
    } catch (exc) {
      if (!(exc instanceof ParkError)) {
        throw exc;
      }
      continue;
    }
    records.push(...found);
  }
  return records;
}

/**
 * The paths that differ between two revisions, both sides of a rename apart, or `null` when git fails.
 * @param {string} cwd
 * @param {...string} revisions
 * @returns {Set<string> | null}
 */
function _changedPaths(cwd, ...revisions) {
  const out = _git(["diff", "--name-only", "--no-renames", "-z", ...revisions], cwd, false);
  if (out === null) {
    return null;
  }
  return new Set(out.split("\0").filter((path) => path !== ""));
}

/**
 * The paths of the branch at `tip` that the owner's branch does not hold alike; empty when it is carried.
 *
 * `git branch --merged` cannot say it: a squash leaves the branch unmerged. So it is read from content:
 * every path the branch changed since its merge-base must hold the same blob at `tip` and at
 * `ownerTip` (absent on both sides is equal); a branch that changed no path, or whose tip the owner's
 * branch contains, has no such path. `null` is what git cannot answer (no merge-base, a failing
 * command), and counts as not carried.
 * @param {string} root
 * @param {string} ownerTip
 * @param {string} tip
 * @returns {string[] | null}
 */
export function uncarriedPaths(root, ownerTip, tip) {
  const base = _git(["merge-base", ownerTip, tip], root);
  if (!base) {
    return null;
  }
  if (base === tip) {
    return [];
  }
  const changed = _changedPaths(root, base, tip);
  const differing = _changedPaths(root, tip, ownerTip);
  if (changed === null || differing === null) {
    return null;
  }
  return [...changed].filter((path) => differing.has(path)).sort(_compareCodePoints);
}

/**
 * An age in the short relative form: minutes under an hour, hours under a day, days after.
 * @param {number} seconds
 * @returns {string}
 */
function _relativeAge(seconds) {
  if (seconds < SECONDS_PER_HOUR) {
    return `${Math.floor(seconds / 60)}m`;
  }
  if (seconds < SECONDS_PER_DAY) {
    return `${Math.floor(seconds / SECONDS_PER_HOUR)}h`;
  }
  return `${Math.floor(seconds / SECONDS_PER_DAY)}d`;
}

/**
 * The unit a row belongs to, and whether a live lease holds it.
 *
 * The live lease whose folder is `path` wins; else the unit whose latest note names `branch`. A live
 * lease on any unit that names the branch holds the row too.
 * @param {readonly UnitRecord[]} units
 * @param {string} path
 * @param {string} branch
 * @returns {{unit: UnitRecord | null, held: boolean}}
 */
function _unitFor(units, path, branch) {
  const byPath = units.filter((unit) => unit.live && _samePath(unit.worktree, path));
  const byBranch = units.filter((unit) => branch !== "" && unit.branch === branch);
  const held = byPath.length > 0 || byBranch.some((unit) => unit.live);
  // the first of the best: Python's `max` keeps the first of equals
  if (byPath.length > 0) {
    const best = byPath.reduce((one, other) =>
      Number(other.athlos !== "") - Number(one.athlos !== "") || other.written - one.written > 0 ? other : one,
    );
    return { unit: best, held };
  }
  if (byBranch.length > 0) {
    const best = byBranch.reduce((one, other) =>
      other.written - one.written || Number(other.athlos !== "") - Number(one.athlos !== "") > 0 ? other : one,
    );
    return { unit: best, held };
  }
  return { unit: null, held };
}

/**
 * What decides a row's state: a live lease, the content check, the folder's cleanliness, the commits ahead.
 * @typedef {{readonly held: boolean, readonly carried: boolean, readonly clean: boolean | null, readonly ahead: number | null}} RowFacts
 */

/**
 * The state of a row: what the owner may do with it, or why nothing yet.
 *
 * An athlos worktree is *working* while it is dirty (or cannot be read) or a live lease holds it,
 * *ready* when it is clean, beyond the owner's branch and not carried, and *carried* when its work is
 * in the owner's branch. A branch without a worktree is a *backup*, carried or not; a held one is
 * still *working*.
 * @param {string} kind
 * @param {ParkData} texts
 * @param {RowFacts} facts
 * @returns {string}
 */
function _rowState(kind, texts, facts) {
  const { kinds, states } = texts.worktrees;
  if (kind === kinds.main || kind === kinds.harness) {
    return kind === kinds.main ? states.main : states.harness;
  }
  if (facts.held) {
    return states.working;
  }
  if (kind === kinds.branch_only) {
    return facts.carried ? states.backup : states.not_carried_backup;
  }
  if (facts.clean !== true) {
    return states.working;
  }
  if (facts.carried) {
    return states.carried;
  }
  return facts.ahead ? states.ready : states.working;
}

/**
 * The whole number one git command prints, or `null` when it fails or prints something else.
 * @param {readonly string[]} args
 * @param {string} cwd
 * @returns {number | null}
 */
function _gitNumber(args, cwd) {
  const out = _git(args, cwd);
  return out && DIGITS_RE.test(out) ? pyInt(out) : null;
}

/**
 * The commits of `tip` beyond the owner's branch, and the age of its last commit in seconds.
 * @param {Listing} listing
 * @param {string} tip
 * @returns {{ahead: number | null, ageSeconds: number | null}}
 */
function _commitFacts(listing, tip) {
  const ahead = _gitNumber(["rev-list", "--count", `${listing.ownerTip}..${tip}`], listing.root);
  const stamp = _gitNumber(["log", "-1", "--format=%ct", tip], listing.root);
  return { ahead, ageSeconds: stamp === null ? null : Math.max(0, Math.floor(listing.now - stamp)) };
}

/**
 * The subject of the last commit of `tip`, for a ready row only: the message the carry proposes.
 * @param {Listing} listing
 * @param {string} tip
 * @param {string} state
 * @returns {string}
 */
function _readySubject(listing, tip, state) {
  if (state !== listing.texts.worktrees.states.ready) {
    return "";
  }
  return _git(["log", "-1", "--format=%s", tip], listing.root) ?? "";
}

/**
 * Whether a worktree's folder has nothing uncommitted; `null` when there is no folder or git cannot say.
 * @param {string} path
 * @returns {boolean | null}
 */
function _folderClean(path) {
  const uncommitted = path !== "" ? gitUncommittedPaths(path) : null;
  return uncommitted === null ? null : uncommitted.length === 0;
}

/**
 * One row: the facts git gives of `tip`, the unit that owns it, and its state.
 * @param {Listing} listing
 * @param {string} path
 * @param {string} branch
 * @param {string} tip
 * @param {string} kind
 * @returns {WorktreeRow}
 */
function _worktreeRow(listing, path, branch, tip, kind) {
  const { texts } = listing;
  const { states } = texts.worktrees;
  const { unit, held } = _unitFor(listing.units, path, branch);
  const differing = uncarriedPaths(listing.root, listing.ownerTip, tip);
  const carried = differing !== null && differing.length === 0;
  const clean = _folderClean(path);
  const { ahead, ageSeconds } = _commitFacts(listing, tip);
  const state = _rowState(kind, texts, { held, carried, clean, ahead });
  return {
    path,
    shown: path !== "" ? _displayPath(path, pyPath(listing.main, WORKTREES_DIR)) : "",
    branch: branch || texts.worktrees.detached,
    kind,
    ergon: unit?.ergon ?? "",
    athlos: unit?.athlos ?? "",
    clean,
    ahead,
    ageSeconds,
    carried,
    differing,
    state,
    removable: state === states.carried || state === states.backup,
    subject: _readySubject(listing, tip, state),
  };
}

/**
 * The `_aitna/` branches with no worktree, as `{branch, tip}`, by branch name.
 * @param {string} root
 * @param {ReadonlySet<string>} sheltered the branches a worktree has checked out
 * @returns {{branch: string, tip: string}[]}
 */
function _branchOnly(root, sheltered) {
  const out = _git(["for-each-ref", "--format=%(objectname) %(refname)", HEADS + BRANCH_NAMESPACE], root) ?? "";
  /** @type {{branch: string, tip: string}[]} */
  const found = [];
  for (const line of out.split("\n")) {
    const space = line.indexOf(" ");
    const tip = space < 0 ? line : line.slice(0, space);
    const ref = space < 0 ? "" : line.slice(space + 1);
    const branch = ref.startsWith(HEADS) ? ref.slice(HEADS.length) : ref;
    if (tip !== "" && branch !== "" && !sheltered.has(branch)) {
      found.push({ branch, tip });
    }
  }
  return found.sort((one, other) => _compareCodePoints(one.branch, other.branch));
}

/**
 * Every worktree of the repository and every `_aitna/` branch that has none, as rows; reads only.
 *
 * The owner's checkout is git's first entry and comes first; a linked worktree is an *athlos* when its
 * branch is in the `_aitna/<id>-<name>.<n>` namespace and a *harness* one otherwise; a branch whose
 * worktree is gone is a backup. Each row carries a state; one is removable only when it is a carried
 * athlos worktree or a carried backup branch (never one a live lease holds).
 * @param {string} root
 * @param {ParkData} texts
 * @param {LeaseContext} context
 * @returns {WorktreeRow[]}
 * @throws {ParkError} `root` is not in a git repository, or the repository has no checkout of its own
 */
export function listWorktrees(root, texts, context) {
  const out = _git(["worktree", "list", "--porcelain"], root, false);
  const entries = out ? parseWorktreeList(out) : [];
  if (entries.length === 0) {
    throw _error(texts, "no_repository", { path: root });
  }
  const main = entries[0];
  if (main.bare) {
    throw _error(texts, "no_main_checkout", { path: main.path });
  }
  const { kinds } = texts.worktrees;
  /** @type {Listing} */
  const listing = {
    root,
    main: main.path,
    ownerTip: main.head,
    units: _unitRecords(root, texts, context),
    texts,
    now: context.now,
  };
  const linked = entries.slice(1).filter((entry) => !entry.bare);
  const rows = linked
    .map((entry) =>
      _worktreeRow(
        listing,
        entry.path,
        entry.branch,
        entry.head,
        branchUnit(entry.branch) ? kinds.athlos : kinds.harness,
      ),
    )
    .sort((one, other) => _compareCodePoints(one.shown, other.shown));
  rows.unshift(_worktreeRow(listing, main.path, main.branch, main.head, kinds.main));
  const sheltered = new Set(entries.map((entry) => entry.branch).filter((branch) => branch !== ""));
  for (const { branch, tip } of _branchOnly(root, sheltered)) {
    rows.push(_worktreeRow(listing, "", branch, tip, kinds.branch_only));
  }
  return rows;
}

/**
 * @param {ParkData} texts
 * @param {boolean | null} value
 * @returns {string}
 */
function _yesNo(texts, value) {
  if (value === null) {
    return texts.empty_cell;
  }
  return value ? texts.worktrees.yes : texts.worktrees.no;
}

/**
 * @param {WorktreeRow} row
 * @param {ParkData} texts
 * @returns {string[]}
 */
function _tableCells(row, texts) {
  const empty = texts.empty_cell;
  return [
    row.shown || empty,
    row.branch,
    row.kind,
    row.ergon || empty,
    row.athlos || empty,
    _yesNo(texts, row.clean),
    row.ahead === null ? empty : String(row.ahead),
    row.ageSeconds === null ? empty : _relativeAge(row.ageSeconds),
    row.state,
  ];
}

/**
 * The table of `worktrees` as aligned lines, the header first; an absent value is the empty cell.
 * @param {readonly WorktreeRow[]} rows
 * @param {ParkData} texts
 * @returns {string[]}
 */
export function formatWorktrees(rows, texts) {
  const spec = texts.worktrees;
  const table = [[...spec.columns], ...rows.map((row) => _tableCells(row, texts))];
  const widths = table[0].map((_cell, column) => Math.max(...table.map((line) => Array.from(line[column]).length)));
  return table.map((line) => {
    const padded = line.slice(0, -1).map((cell, column) => cell + " ".repeat(widths[column] - Array.from(cell).length));
    return [...padded, line[line.length - 1]].join(spec.separator);
  });
}

/**
 * A word as the shell takes it literally: the word itself when it is plain, else in single quotes.
 * @param {string} word
 * @returns {string}
 */
function _shellQuote(word) {
  if (word === "") {
    return "''";
  }
  if (!/[^A-Za-z0-9_@%+=:,./-]/.test(word)) {
    return word;
  }
  return `'${word.replaceAll("'", `'"'"'`)}'`;
}

/**
 * `text` made literal inside double quotes: the four characters the shell still reads there are escaped.
 * @param {string} text
 * @returns {string}
 */
function _doubleQuoted(text) {
  return text.replace(/([\\"$`])/g, "\\$1");
}

/**
 * The squash that carries each ready row into the owner's branch, one block of commands per row.
 *
 * The tool prints them and never runs them (ADR 0029 D09): the owner starts every carry. The message
 * is the subject of the branch's last commit, which the agent may rewrite before the owner commits.
 * @param {readonly WorktreeRow[]} rows
 * @param {string} main the owner's checkout
 * @param {ParkData} texts
 * @returns {string[][]}
 */
export function carryCommands(rows, main, texts) {
  const spec = texts.worktrees;
  return rows
    .filter((row) => row.state === spec.states.ready)
    .map((row) => [
      fill(spec.carry_cd, { path: _shellQuote(main) }),
      fill(spec.carry_squash, { branch: _shellQuote(row.branch) }),
      fill(spec.carry_commit, { message: _doubleQuoted(row.subject) }),
    ]);
}

/**
 * The commands that remove each removable row: the tool prints them and never runs them.
 *
 * A worktree goes with `git worktree remove`, which refuses while anything in it is uncommitted; a
 * backup branch goes with `-D`, because a squash leaves it unmerged in git's eyes.
 * @param {readonly WorktreeRow[]} rows
 * @param {ParkData} texts
 * @returns {string[]}
 */
export function removalCommands(rows, texts) {
  const spec = texts.worktrees;
  return rows
    .filter((row) => row.removable)
    .map((row) =>
      row.path !== ""
        ? fill(spec.command_worktree, { path: _shellQuote(row.path) })
        : fill(spec.command_branch, { branch: _shellQuote(row.branch) }),
    );
}

/**
 * The rows a target names: a branch (with or without `_aitna/`) or an athlos key such as `C190.1`.
 * @param {readonly WorktreeRow[]} rows
 * @param {string} target
 * @returns {WorktreeRow[]}
 */
export function selectWorktrees(rows, target) {
  return rows.filter(
    (row) => row.branch === target || row.athlos === target || row.branch === BRANCH_NAMESPACE + target,
  );
}

/**
 * The one line that says whether the branch of `row` is carried and, if not, what differs.
 * @param {WorktreeRow} row
 * @param {ParkData} texts
 * @returns {string}
 */
export function worktreeVerdict(row, texts) {
  const spec = texts.worktrees;
  if (row.carried) {
    return fill(spec.verdict_carried, { branch: row.branch });
  }
  let paths = spec.verdict_unreadable;
  if (row.differing !== null) {
    const shown = row.differing.slice(0, spec.verdict_paths);
    paths = shown.join(", ") + (row.differing.length > shown.length ? spec.verdict_more : "");
  }
  return fill(spec.verdict_not_carried, { branch: row.branch, paths });
}

// --------------------------------------------------------------------------------------
// the export: the ergon's files, its leases left out (ADR 0028 D07, branch B10)
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
 * Write the ergon's files to one bundle file, its leases left out.
 *
 * The bundle is plain text: the file's path, then its content, so any language reads it.
 * @param {string} ergon
 * @param {string} out
 * @param {ParkData} texts
 * @returns {string} the bundle path
 */
export function exportErgon(ergon, out, texts) {
  const spec = texts.export;
  const lines = [fill(spec.title, { ergon: posix.basename(ergon) }), ""];
  for (const relative of _filesUnder(ergon, ergon).sort(_comparePaths)) {
    if (posix.basename(relative) === HOLDER_FILE) {
      continue;
    }
    lines.push(fill(spec.file_header, { path: relative }));
    lines.push(rstripChars(readText(pyPath(ergon, relative)), "\n"));
    lines.push(spec.end);
    lines.push("");
  }
  fs.mkdirSync(dirname(out), { recursive: true });
  writeText(out, `${rstripChars(lines.join("\n"), "\n")}\n`);
  return out;
}

// --------------------------------------------------------------------------------------
// the local ids: `_T<n>` counted over the ergons, live and closed, never reused
// --------------------------------------------------------------------------------------

/**
 * The `_T<n>` numbers the retired local index `<DEV>/.local/TASKS.md` still holds.
 *
 * Read as legacy input and never written (ADR 0028 D12). The index sits with the ergons in the main
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
 * The next free local id: `_T<n>` counted over every ergon, live and closed, and the legacy index.
 * @param {string} root
 * @returns {string}
 */
export function nextLocalId(root) {
  const numbers = [0, ..._legacyLocalIds(root)];
  for (const name of [..._ergonNames(root), ..._ergonNames(root, { closed: true })]) {
    const match = LOCAL_ID_RE.exec(_ergonId(name));
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

/** The commands, in the order the Python parser adds them: whether each takes the ergon id, and its options. */
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
  athlos: {
    id: true,
    options: _withCommon([
      _flag("--number", { kind: "int", required: true }),
      _flag("--step", { kind: "many" }),
      _flag("--done", { kind: "switch" }),
      ...HOLDER_OPTIONS,
    ]),
  },
  active: { id: false, options: _withCommon([]) },
  worktrees: { id: "optional", options: _withCommon([]) },
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
    ...(spec.id === true && scan.positionals.length === 0 ? ["id"] : []),
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
  return { command, id: spec.id ? (scan.positionals[0] ?? "") : "", values: scan.values };
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
 * The holder a command acts as: the flags, or the machine it runs on, and the folder it works in.
 *
 * The worktree is the folder the process started in, read once at the entry (`_run`) and carried on
 * the run — a command never asks the file system where it is from inside the logic.
 * @param {ParsedArgs} args
 * @param {{machine: string, cwd: string}} run
 * @returns {Holder}
 */
function _holderOf(args, run) {
  return {
    harness: _text(args, "harness"),
    sessionId: _text(args, "sessionId"),
    machine: _text(args, "machine") || run.machine,
    worktree: run.cwd,
  };
}

/**
 * The folder of the unit a command acts on: the ergon root, or one of its athlos.
 * @param {string} ergon
 * @param {number | null} number
 * @param {ParkData} texts
 * @returns {string}
 */
function _unitOf(ergon, number, texts) {
  if (number === null) {
    return ergon;
  }
  const athlosId = athlosIdOf(_ergonId(posix.basename(ergon)), number);
  const folder = athlosFolder(ergon, number);
  if (folder === null) {
    throw _error(texts, "no_athlos", { ergon: posix.basename(ergon), athlos: athlosId });
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
 * The resume prompt of an ergon, and the proof that its note reads: nothing is held yet.
 * @param {string} ergon
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} the ergon has no `RESUME.md`, was never parked, or its note does not parse
 */
function _readResume(ergon, texts) {
  const resume = pyPath(ergon, RESUME_FILE);
  if (!isFile(resume)) {
    throw _error(texts, "no_resume", { ergon: posix.basename(ergon) });
  }
  readNote(ergon, texts);
  return rstripChars(readText(resume), "\n");
}

/**
 * The resume prompt of an ergon, followed by a blank line and its capped digest.
 * @param {string} prompt
 * @param {string} ergon
 * @param {string} root
 * @param {ParkData} texts
 * @param {string} machine
 * @returns {string}
 */
function _resumeText(prompt, ergon, root, texts, machine) {
  return `${prompt}\n\n${digest(ergon, texts.default_cap, root, texts, machine)}`;
}

/**
 * @param {string} text
 */
function _print(text) {
  process.stdout.write(`${text}\n`);
}

/**
 * The usable athlos line of a plan for `athlosId`: it names a folder and a result for `ATHLOS.md`.
 * @param {string} ergon
 * @param {Plan} plan
 * @param {string} athlosId
 * @param {ParkData} texts
 * @returns {AthlosLine}
 * @throws {ParkError} the plan has no such athlos, or the line has no label or no result
 */
function _plannedAthlos(ergon, plan, athlosId, texts) {
  const line = plan.athlos.find((athlos) => athlos.id === athlosId);
  if (line === undefined) {
    throw _error(texts, "no_athlos", { ergon: posix.basename(ergon), athlos: athlosId });
  }
  if (line.label === "") {
    throw _error(texts, "athlos_label", { id: athlosId });
  }
  if (line.result === "") {
    throw _error(texts, "bad_plan", { ergon: posix.basename(ergon), reason: `athlos ${athlosId} has no result` });
  }
  return line;
}

/**
 * The folder and the file an athlos write starts from: the athlos's own when it exists, else the ones the
 * plan's athlos line gives it.
 *
 * The file lands in the folder of the athlos's number; a record written in the retired `jobs/` layout is
 * carried there by this write, once (ADR 0029 D11, D12).
 * @param {string} ergon
 * @param {Plan} plan
 * @param {number} number
 * @param {ParkData} texts
 * @param {string} cwd where git is asked for the branch
 * @returns {{folder: string, doc: AthlosDoc}}
 * @throws {ParkError} the athlos has no folder yet and the plan has no usable line for it
 */
function _athlosToWrite(ergon, plan, number, texts, cwd) {
  const athlosId = athlosIdOf(_ergonId(posix.basename(ergon)), number);
  const existing = athlosFolder(ergon, number);
  const doc = existing !== null ? readAthlosDoc(athlosFileOf(existing), texts) : null;
  if (doc !== null) {
    return { folder: moveAthlosFolder(ergon, number, existing), doc };
  }
  const line = _plannedAthlos(ergon, plan, athlosId, texts);
  const ergonId = _ergonId(posix.basename(ergon));
  const ergonName = Array.from(posix.basename(ergon))
    .slice(Array.from(ergonId).length + 1)
    .join("");
  const fresh = athlosDocFor(line, ergonId, ergonName, plan, cwd);
  _checkAthlosDoc(fresh, posix.basename(ergon), texts);
  return { folder: moveAthlosFolder(ergon, number, existing), doc: fresh };
}

/**
 * Write an athlos's own file: create it from the plan's athlos line, then add its steps.
 *
 * Everything that can be refused is checked before the lease is taken or a file is touched. The
 * first write into an athlos's folder takes its lease, so two sessions never write one file. The plan's
 * shared-path warnings go to stderr.
 * @param {ParsedArgs} args
 * @param {Run} run
 * @throws {ParkError} the ergon has no plan, the plan has no usable line for the athlos, or the athlos is held
 */
function _writeAthlos(args, run) {
  const { root, texts } = run;
  const ergon = findErgon(root, pyStrip(args.id), texts);
  const number = /** @type {number} */ (_numberOf(args, "number"));
  const plan = readPlan(ergon, texts);
  if (plan === null) {
    throw _error(texts, "no_plan", { ergon: posix.basename(ergon) });
  }
  const { folder, doc } = _athlosToWrite(ergon, plan, number, texts, run.cwd);
  acquireLease(folder, _holderOf(args, run), texts, run.lease);
  /** @type {(readonly [string, boolean])[]} */
  const steps = [
    ...doc.steps,
    ..._listOf(args, "step").map((text) => /** @type {[string, boolean]} */ ([text, false])),
  ];
  writeAthlosDoc(folder, { header: doc.header, steps, done: doc.done || _switchOf(args, "done") }, texts);
  _print(_displayPath(folder, root));
  for (const warning of sharedPathWarnings(plan, texts)) {
    process.stderr.write(`${warning}\n`);
  }
}

/**
 * Print the unit this session is in: the athlos of the worktree it works in.
 * @param {Run} run
 */
function _printActive(run) {
  const { root, texts } = run;
  const found = activeUnit(root, texts);
  if (found === null) {
    _print(texts.active.none);
    return;
  }
  const athlosId = athlosIdOf(found.ergonId, found.number);
  const folder = findAthlosFolder(found.ergon, athlosId, texts);
  const unit = folder !== null ? folder : found.ergon;
  const lease = readLease(unit, texts);
  const state = unitState(unit, texts, run.lease);
  const path = _displayPath(unit, root);
  _print(
    fill(texts.active.line, {
      kind: folder !== null ? "athlos" : "ergon",
      id: folder !== null ? athlosId : found.ergonId,
      name: posix.basename(unit),
      state,
      holder: lease !== null ? holderLabel(lease.holder) : texts.empty_cell,
      path,
    }),
  );
}

/**
 * What every command of one invocation shares: the root, the texts, the lease clock, the machine, the folder.
 * @typedef {object} Run
 * @property {string} root
 * @property {ParkData} texts
 * @property {LeaseContext} lease
 * @property {string} machine
 * @property {string} cwd the folder the process started in, read once at the entry
 */

/**
 * The folder an ergon has, or the one it would have; the name conflict is the writer's to refuse.
 * @param {string} root
 * @param {ParkFields} fields
 * @returns {string}
 */
function _ergonFolder(root, fields) {
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
  const ergon = _ergonFolder(run.root, fields);
  const holder = _holderOf(args, run);
  checkFields(fields, run.texts);
  checkBody(body, run.texts);
  refuseErgonConflict(fields, run.root, run.texts);
  _refuseForeignLease(ergon, holder, run);
  const free = readLease(ergon, run.texts) === null;
  // The write holds the ergon while it writes: a lease taken since the check is refused, not overwritten.
  const lease = acquireLease(ergon, holder, run.texts, run.lease);
  try {
    writeErgon(fields, body, run.root, run.texts, run.cwd);
  } catch (error) {
    if (free) {
      _releaseOwnLease(ergon, lease, run.texts);
      _removeIfEmpty(ergon);
    }
    throw error;
  }
  _releaseOwnLease(ergon, lease, run.texts);
  _print(_displayPath(ergon, run.root));
  return 0;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdUnpark(args, run) {
  const ergon = findErgon(run.root, pyStrip(args.id), run.texts);
  const prompt = _readResume(ergon, run.texts); // everything that can be refused, before a lease is taken
  acquireLease(ergon, _holderOf(args, run), run.texts, run.lease);
  _print(_resumeText(prompt, ergon, run.root, run.texts, run.machine));
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
  _print(digest(findErgon(run.root, pyStrip(args.id), run.texts), cap, run.root, run.texts, run.machine));
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
  const { ergons, athlos } = listErgons(run.root, query, run.texts, run.lease);
  if (ergons.length > 0) {
    /** @type {string[]} */
    const lines = [];
    for (const summary of ergons) {
      lines.push(formatSummary(summary, run.texts));
      const units = athlos.filter((item) => item.id.startsWith(`${summary.id}.`));
      lines.push(...units.map((item) => formatAthlos(item, run.texts)));
    }
    _print(lines.join("\n"));
  } else if (_ergonNames(run.root).length === 0) {
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
  const ergon = findErgon(run.root, pyStrip(args.id), run.texts);
  const unit = _unitOf(ergon, _numberOf(args, "number"), run.texts);
  const holder = _holderOf(args, run);
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
  const ergon = findErgon(run.root, pyStrip(args.id), run.texts);
  const unit = _unitOf(ergon, _numberOf(args, "number"), run.texts);
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
function _cmdAthlos(args, run) {
  _writeAthlos(args, run);
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
function _cmdWorktrees(args, run) {
  const rows = listWorktrees(run.root, run.texts, run.lease);
  const target = pyStrip(args.id);
  if (target !== "") {
    return _printWorktreeVerdict(selectWorktrees(rows, target), target, run);
  }
  const sections = [formatWorktrees(rows, run.texts), ...carryCommands(rows, rows[0].path, run.texts)];
  const removals = removalCommands(rows, run.texts);
  if (removals.length > 0) {
    sections.push(removals);
  }
  _print(sections.map((section) => section.join("\n")).join("\n\n"));
  return 0;
}

/**
 * Print the rows a target names and one verdict line each; the exit code is 0 only when all are carried.
 * @param {readonly WorktreeRow[]} rows
 * @param {string} target
 * @param {Run} run
 * @returns {number}
 */
function _printWorktreeVerdict(rows, target, run) {
  if (rows.length === 0) {
    _print(fill(run.texts.worktrees.verdict_missing, { target }));
    return 1;
  }
  const lines = [...formatWorktrees(rows, run.texts), ...rows.map((row) => worktreeVerdict(row, run.texts))];
  _print(lines.join("\n"));
  return rows.every((row) => row.carried) ? 0 : 1;
}

/**
 * @param {ParsedArgs} args
 * @param {Run} run
 * @returns {number}
 */
function _cmdClose(args, run) {
  const ergon = findErgon(run.root, pyStrip(args.id), run.texts);
  _refuseLiveForeignLease(ergon, _holderOf(args, run), run);
  const closed = pyPath(ergonRoot(run.root), CLOSED_DIR);
  const target = pyPath(closed, posix.basename(ergon));
  if (pyStat(target) !== null) {
    throw _error(run.texts, "close_exists", {
      ergon: posix.basename(ergon),
      target: _displayPath(target, run.root),
    });
  }
  fs.mkdirSync(closed, { recursive: true });
  try {
    fs.renameSync(ergon, target);
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
    const reason = /** @type {NodeJS.ErrnoException} */ (error).code ?? "OSError";
    throw _error(run.texts, "close_failed", { ergon: posix.basename(ergon), reason });
  }
  releaseLeases(target); // after the move, so a close that is refused or fails changes nothing
  _print(_displayPath(target, run.root));
  return 0;
}

/**
 * Refuse to close an ergon while a live lease of another session is in it, the plan's or an athlos's.
 *
 * A stale lease holds nothing, and the closing session's own leases are its to release.
 * @param {string} ergon
 * @param {Holder} holder
 * @param {Run} run
 * @throws {ParkError} another session holds a unit of the ergon; the message names the unit and the holder
 */
function _refuseLiveForeignLease(ergon, holder, run) {
  for (const unit of [ergon, ..._athlosFolders(ergon)]) {
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
  const ergon = findErgon(run.root, pyStrip(args.id), run.texts);
  const out = pyPath(/** @type {string} */ (args.values.get("out")));
  exportErgon(ergon, out, run.texts);
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
    athlos: _cmdAthlos,
    active: _cmdActive,
    worktrees: _cmdWorktrees,
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
  const run = {
    root,
    texts,
    lease: { now: Date.now() / 1000, staleHours: texts.stale_after_hours, machine },
    machine,
    cwd: process.cwd(), // read once here; a command below never asks the process where it is
  };
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
