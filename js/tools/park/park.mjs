#!/usr/bin/env node
/**
 * The park helper: write, resume, digest and list the kits of parked work — the JavaScript twin of
 * `tools/park/park.py` (ADR 0020 D01, ADR 0028 D02, D03, D06). The Python module is the spec: the
 * same files in the same bytes, the same stdout lines, the same `error:` lines, the same exit codes;
 * its docstring carries the full account of the kit, the note's header format and the local index.
 *
 * A *kit* is the folder `<dev root>/.ergon/<id>-<name>/` of one piece of work. Parking it writes
 * `RESUME.md` and `PARK.md` into it atomically and keeps the kit's one row in the local index
 * (`<dev root>/.local/TASKS.md`) at the status `parked`; a project index is never touched.
 *
 * Data (the C102 convention): the tool's texts are `tools/park/park.json`, read once by `main` (and
 * by `digest` when it is called alone) and passed down as `texts`.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the dataclasses are frozen plain objects with camelCase keys (`nextAction`, `ownedPaths`,
 *   `sessionId`, `ageDays`); `parkFields` and `parkBody` fill the defaults the dataclasses carry;
 * - the arguments are parsed by a small `argparse`-shaped scanner (DV12): a usage error is the one
 *   line `park.mjs: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0.
 *   Options are accepted before and after the subcommand's positional, `--root` and `--project-root`
 *   are one option, and a value such as `-1` or `- two words` is a value, as `argparse` takes it;
 * - character counts (the digest cap, the 60-character cut of `next`) count code points, and kit ids
 *   sort by code point, as Python's `len` and `sorted` do;
 * - an I/O failure (DV16) is the runtime's own error, never caught: Node's stack trace and exit 1.
 */

import fs from "node:fs";
import { dirname, posix } from "node:path";
import { fileURLToPath } from "node:url";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { ERGON_DIR_NAME, ergonRoot, localRoot, resolveProjectRoot } from "../../common/project_root.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import {
  encodeUtf8,
  isDir,
  isFile,
  isOSError,
  pyInt,
  pyLen,
  pyLstrip,
  pyPath,
  pyStrip,
  readText,
  rstripChars,
  strRepr,
  unlinkMissingOk,
} from "../../common/pyvalue.mjs";

/**
 * The keys of `tools/park/park.json` the code reads.
 * @typedef {object} ParkData
 * @property {string} invocation
 * @property {number} default_cap
 * @property {number} next_width
 * @property {string} default_role
 * @property {string} index_header
 * @property {string} status_parked
 * @property {string} status_active
 * @property {string} state_parked
 * @property {string} state_resumed
 * @property {string} state_never_parked
 * @property {string} none_marker
 * @property {string} empty_cell
 * @property {string} ellipsis
 * @property {Record<string, string>} headings
 * @property {{title: string, intro: string, steps: string[], next_heading: string, decisions_heading: string, decisions_none: string, retirement_heading: string, retirement: string[]}} resume
 * @property {{title: string}} note
 * @property {{link: string}} row
 * @property {Record<string, string>} digest
 * @property {{line: string, empty: string, no_match: string}} list
 * @property {Record<string, string>} errors
 */

/**
 * Where the work was done: a reference for provenance, never a requirement (ADR 0028 D03).
 * @typedef {{readonly harness: string, readonly sessionId: string, readonly machine: string}} SessionRef
 */

/**
 * The header of a park note: the one source of its keys, rendered and parsed from here.
 * @typedef {object} ParkFields
 * @property {string} id
 * @property {string} name
 * @property {string} nextAction
 * @property {string} state
 * @property {string} plan
 * @property {string} row
 * @property {string} branch
 * @property {readonly string[]} revisions
 * @property {readonly string[]} ownedPaths
 * @property {readonly SessionRef[]} sessions
 * @property {readonly string[]} peers
 * @property {string} origin
 * @property {string} readiness
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
 * One line of `list`: what a kit says of itself, read from its folder and the local index.
 * @typedef {object} KitSummary
 * @property {string} id
 * @property {string} name
 * @property {string} state
 * @property {string} plan
 * @property {string} nextAction
 * @property {number} decisions
 * @property {string} branch
 * @property {number | null} ageDays
 * @property {string} status
 */

/**
 * The filters of `list`; an empty one matches every kit.
 * @typedef {{readonly plan: string, readonly state: string, readonly status: string}} ListQuery
 */

/**
 * What `write` needs beyond the note: the index row's title and role.
 * @typedef {{readonly title: string, readonly role: string}} WriteOptions
 */

const PROG = "park.mjs";

const USAGE = `usage: ${PROG} [-h] {write,unpark,digest,list} ...

Park work into a kit and resume it.

commands:
  write ID --name N --goal G --next X [--title T] [--plan ID] [--row ID] [--branch B]
        [--revision R]... [--owned-path P]... [--check C]... [--unverified U]...
        [--decision D]... [--answer A]... [--agent A]... [--readiness R] [--harness H]
        [--session-id S] [--machine M] [--peer P]... [--origin O] [--role R]
                        Park a piece of work.
  unpark ID             Resume a parked kit.
  digest ID [--cap N]   Print the capped digest.
  list [--plan ID] [--state S] [--status TOKEN]
                        List the kits.

Every command takes --root DIR (or --project-root DIR): the project root. Defaults to the nearest
parent holding AGENTS.md beside the dev layer.

options:
  -h, --help            show this help message and exit
`;

const SECONDS_PER_DAY = 86400;
const PARK_FILE = "PARK.md";
const RESUME_FILE = "RESUME.md";
const INDEX_FILE = "TASKS.md";
const HEADER_FENCE = "---";
const STATUS_FIELD = 2; // the third `·`-separated field of an index row (pipelines/tasks.md)
const ROW_FIELDS_MIN = 3;
const SESSION_PARTS = 3; // harness|session_id|machine

// Python's `$` also matches before a final newline, so `\n?$` keeps the twin's answer for a value
// that ends in one; `\p{Nd}` is Python's `\d`; `.` is `[^\n]` because Python's `.` takes `\r`.
const ID_RE = /^(?:[A-Z]\p{Nd}+|_T\p{Nd}+)\n?$/u; // ADR 0002 typed id, and a local row's _T<n> (ADR 0022 D03)
const NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*\n?$/;
const KIT_RE = /^([A-Z]\p{Nd}+|_T\p{Nd}+)-([a-z0-9]+(?:-[a-z0-9]+)*)\n?$/u;
const KEY_RE = /^([a-z_]+):(?: ([^\n]*))?$/;
const PURPOSE_KEY_RE = /^[a-z][a-z0-9_]*\n?$/;
const ROW_ID_TAIL = /\[[^\]]*\]$/; // a row id may carry a tracker tag: C2[#134]
const LINK_RE = /\]\([^)]*\)/;

// Header keys in their written order, and which of them hold a list: the one table the renderer and
// the parser share. `nextAction` is written as `next`.
const LIST_KEYS = ["revisions", "owned_paths", "sessions", "peers"];
const HEADER_ORDER = [
  "state",
  "id",
  "name",
  "plan",
  "row",
  "branch",
  "revisions",
  "owned_paths",
  "next",
  "sessions",
  "peers",
  "origin",
  "readiness",
];

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
    state: "parked",
    plan: "",
    row: "",
    branch: "",
    revisions: Object.freeze([]),
    ownedPaths: Object.freeze([]),
    sessions: Object.freeze([]),
    peers: Object.freeze([]),
    origin: "",
    readiness: "",
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
 * `str.rstrip()` with no argument (the shared module carries `strip` and `lstrip` only).
 * @param {string} text
 * @returns {string}
 */
function _rstrip(text) {
  const stripped = pyStrip(text);
  if (stripped === "") {
    return "";
  }
  return text.slice(0, text.length - pyLstrip(text).length + stripped.length);
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
 * The scalar half of `checkFields`: ids, state and the one-line values.
 * @param {ParkFields} fields
 * @param {ParkData} texts
 */
function _checkScalars(fields, texts) {
  _checkId(fields.id, "id", texts);
  if (!NAME_RE.test(fields.name)) {
    throw _error(texts, "bad_name", { value: fields.name });
  }
  if (fields.state !== texts.state_parked && fields.state !== texts.state_resumed) {
    throw _error(texts, "bad_state", { value: fields.state });
  }
  for (const [label, value] of [
    ["plan", fields.plan],
    ["row", fields.row],
  ]) {
    if (value !== "") {
      _checkId(value, label, texts);
    }
  }
  for (const [label, value] of [
    ["branch", fields.branch],
    ["next", fields.nextAction],
    ["origin", fields.origin],
    ["readiness", fields.readiness],
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
  _checkItems(fields.peers, "peer", texts);
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
    state: fields.state,
    id: fields.id,
    name: fields.name,
    plan: fields.plan,
    row: fields.row,
    branch: fields.branch,
    next: fields.nextAction,
    origin: fields.origin,
    readiness: fields.readiness,
  };
  /** @type {Record<string, readonly string[]>} */
  const lists = {
    revisions: fields.revisions,
    owned_paths: fields.ownedPaths,
    sessions: fields.sessions.map(_sessionText),
    peers: fields.peers,
  };
  const lines = [HEADER_FENCE];
  for (const key of HEADER_ORDER) {
    if (Object.hasOwn(scalars, key)) {
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
 * @param {string} source
 * @param {ParkData} texts
 * @returns {string | null} the list key the line opened, or `null` for a scalar
 */
function _headerEntry(values, line, number, source, texts) {
  const match = KEY_RE.exec(line);
  if (match === null) {
    throw _error(texts, "header_line", { path: source, line: number });
  }
  const key = match[1];
  const value = match[2] ?? "";
  if (!HEADER_ORDER.includes(key) || values.has(key)) {
    throw _error(texts, "header_key", { path: source, key });
  }
  if (LIST_KEYS.includes(key)) {
    if (value !== "") {
      throw _error(texts, "header_scalar_list", { path: source, key });
    }
    values.set(key, []);
    return key;
  }
  values.set(key, value);
  return null;
}

/**
 * The header lines as `key -> scalar | list`, each key known and once, each line well-formed.
 * @param {readonly string[]} lines
 * @param {string} source
 * @param {ParkData} texts
 * @returns {Map<string, string | string[]>}
 */
function _headerValues(lines, source, texts) {
  /** @type {Map<string, string | string[]>} */
  const values = new Map();
  /** @type {string | null} */
  let current = null;
  for (const [offset, line] of lines.entries()) {
    if (line.startsWith("  - ")) {
      const open = current === null ? undefined : values.get(current);
      if (!Array.isArray(open)) {
        throw _error(texts, "header_item", { path: source, line: offset + 1 });
      }
      open.push(line.slice(4));
    } else {
      current = _headerEntry(values, line, offset + 1, source, texts);
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
  for (const key of ["id", "name", "next", "state"]) {
    if (!values.get(key)) {
      throw _error(texts, "header_required", { path: source, key });
    }
  }
  const fields = parkFields({
    id: _scalar(values, "id"),
    name: _scalar(values, "name"),
    nextAction: _scalar(values, "next"),
    state: _scalar(values, "state"),
    plan: _scalar(values, "plan"),
    row: _scalar(values, "row"),
    branch: _scalar(values, "branch"),
    revisions: _listed(values, "revisions"),
    ownedPaths: _listed(values, "owned_paths"),
    sessions: _listed(values, "sessions").map((item) => _parseSession(item, texts)),
    peers: _listed(values, "peers"),
    origin: _scalar(values, "origin"),
    readiness: _scalar(values, "readiness"),
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
 * `text` with its header's state replaced and everything after the header kept byte for byte.
 * @param {string} text
 * @param {string} state
 * @param {string} source
 * @param {ParkData} texts
 * @returns {string}
 */
export function withState(text, state, source, texts) {
  const fields = parseHeader(text, source, texts);
  const { rest } = _splitNote(text, source, texts);
  return renderHeader({ ...fields, state }) + rest;
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
 * @param {ParkData} texts
 * @returns {string[]}
 */
function _digestLines(fields, body, texts) {
  const spec = texts.digest;
  const lines = [fill(spec.title, { kit: `${fields.id}-${fields.name}`, state: fields.state })];
  for (const [key, value] of [
    ["plan", fields.plan],
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
  const lines = _digestLines(fields, body, texts);
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
    const where = root === null ? `${posix.basename(kit)}/${PARK_FILE}` : posix.relative(root, pyPath(kit, PARK_FILE));
    kept.push(fill(texts.digest.overflow, { count: String(lines.length - kept.length), path: where }));
  }
  return kept.join("\n");
}

// --------------------------------------------------------------------------------------
// the local index: one row per kit, status parked only here
// --------------------------------------------------------------------------------------

/**
 * @param {string} row
 * @returns {string}
 */
function _rowId(row) {
  return pyStrip(row.slice(2).split("·")[0]).replace(ROW_ID_TAIL, "");
}

/**
 * @param {string} row
 * @returns {string | null}
 */
function _rowStatus(row) {
  const cells = row.slice(2).split("·");
  return cells.length >= ROW_FIELDS_MIN ? pyStrip(cells[STATUS_FIELD]) : null;
}

/**
 * `row` with only its status cell replaced, keeping the spacing around it.
 * @param {string} row
 * @param {string} status
 * @returns {string}
 */
function _withStatus(row, status) {
  const cells = row.split("·");
  const cell = cells[STATUS_FIELD];
  const lead = cell.slice(0, cell.length - pyLstrip(cell).length);
  const trail = cell.slice(_rstrip(cell).length);
  cells[STATUS_FIELD] = `${lead}${status}${trail}`;
  return cells.join("·");
}

/**
 * @param {readonly string[]} lines
 * @param {string} rowId
 * @returns {number | null}
 */
function _findRow(lines, rowId) {
  const at = lines.findIndex((line) => line.startsWith("- ") && _rowId(line) === rowId);
  return at < 0 ? null : at;
}

/**
 * The status of every row of an index text by id (the first row of a repeated id wins).
 * @param {string} text
 * @returns {Map<string, string>}
 */
function _indexStatuses(text) {
  /** @type {Map<string, string>} */
  const statuses = new Map();
  for (const line of text.split("\n")) {
    const status = line.startsWith("- ") ? _rowStatus(line) : null;
    if (status !== null && !statuses.has(_rowId(line))) {
      statuses.set(_rowId(line), status);
    }
  }
  return statuses;
}

/**
 * @param {string} value
 * @param {string} label
 * @param {ParkData} texts
 */
function _checkCell(value, label, texts) {
  if (value.includes("·")) {
    throw _error(texts, "bad_cell", { label });
  }
}

/**
 * The local index text with the kit's row parked: its status set, or the row appended.
 *
 * `text` is `null` when the index does not exist, which starts it with the one-line header.
 * An existing row keeps its prose and gains a `[park]` detail link only when it has no link.
 * @param {string | null} text
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {WriteOptions} options
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} the existing row has too few fields, or a new row's cell holds the separator
 */
function _parkIndex(text, fields, body, options, texts) {
  const link = fill(texts.row.link, { link: `../${ERGON_DIR_NAME}/${fields.id}-${fields.name}/${PARK_FILE}` });
  const parked = texts.status_parked;
  const start = text ?? `${texts.index_header}\n\n`;
  const lines = start.split("\n");
  const at = _findRow(lines, fields.id);
  if (at !== null) {
    if (_rowStatus(lines[at]) === null) {
      throw _error(texts, "bad_row", { id: fields.id, row: lines[at] });
    }
    const row = _rstrip(_withStatus(lines[at], parked));
    lines[at] = LINK_RE.test(row) ? row : `${row} · ${link}`;
    return lines.join("\n");
  }
  const goal = body.goal.split("\n")[0];
  const title = options.title || goal;
  const role = options.role || texts.default_role;
  for (const [label, value] of [
    ["title", title],
    ["role", role],
    ["goal", goal],
  ]) {
    _checkCell(value, label, texts);
  }
  const row = `- ${fields.id} · ${title} · ${parked} · ${role} · ${goal} · ${link}`;
  return start.endsWith("\n") ? `${start}${row}\n` : `${start}\n${row}\n`;
}

/**
 * The index text with the kit's row set back to `active`, or `null` when it is not `parked`.
 * @param {string} text
 * @param {string} kitId
 * @param {ParkData} texts
 * @returns {string | null}
 */
function _resumeIndex(text, kitId, texts) {
  const lines = text.split("\n");
  const at = _findRow(lines, kitId);
  if (at === null || _rowStatus(lines[at]) !== texts.status_parked) {
    return null;
  }
  lines[at] = _withStatus(lines[at], texts.status_active);
  return lines.join("\n");
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
function _writeFiles(files) {
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

// --------------------------------------------------------------------------------------
// the kits of a project
// --------------------------------------------------------------------------------------

/**
 * The names of the kit folders under `.ergon/` (`<id>-<name>` only), sorted.
 * @param {string} root
 * @returns {string[]}
 */
function _kitNames(root) {
  const ergon = ergonRoot(root);
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
 * The kit folder whose name leads with `kitId`.
 * @param {string} root
 * @param {string} kitId
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} no kit or several kits carry the id; the message names the candidates
 */
export function findKit(root, kitId, texts) {
  const names = _kitNames(root);
  const found = names.filter((name) => _kitId(name) === kitId);
  const ergon = posix.relative(root, ergonRoot(root));
  if (found.length === 0) {
    throw _error(texts, "no_kit", { id: kitId, ergon, kits: names.join(", ") || "none" });
  }
  if (found.length > 1) {
    throw _error(texts, "several_kits", { id: kitId, ergon, kits: found.join(", ") });
  }
  return pyPath(ergonRoot(root), found[0]);
}

/**
 * @param {string} root
 * @returns {string}
 */
function _indexPath(root) {
  return pyPath(localRoot(root), INDEX_FILE);
}

/**
 * @param {string} root
 * @returns {string | null}
 */
function _readIndex(root) {
  const path = _indexPath(root);
  return isFile(path) ? readText(path) : null;
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

/**
 * Park the work: write `RESUME.md` and `PARK.md` into the kit and park its row in the local index.
 *
 * The kit folder is created when missing. Everything that can be refused is checked before
 * any file is touched; the files then land together (`_writeFiles`), `PARK.md` last among
 * the kit's, and a failure removes the folder it created when that folder is still empty.
 * @param {ParkFields} fields
 * @param {ParkBody} body
 * @param {string} root
 * @param {WriteOptions} options
 * @param {ParkData} texts
 * @returns {string} the kit folder
 * @throws {ParkError} a field fails its check, or a kit with this id has another name
 */
export function writeKit(fields, body, root, options, texts) {
  checkFields(fields, texts);
  checkBody(body, texts);
  const kitName = `${fields.id}-${fields.name}`;
  const other = _kitNames(root).filter((name) => _kitId(name) === fields.id && name !== kitName);
  if (other.length > 0) {
    throw _error(texts, "kit_other_name", { existing: other[0], id: fields.id, name: fields.name });
  }
  const kit = pyPath(ergonRoot(root), kitName);
  const parkPath = posix.relative(root, pyPath(kit, PARK_FILE));
  const index = _indexPath(root);
  /** @type {[string, string][]} */
  const files = [
    [pyPath(kit, RESUME_FILE), renderResume(fields, body, parkPath, texts)],
    [pyPath(kit, PARK_FILE), renderNote(fields, body, texts)],
    [index, _parkIndex(_readIndex(root), fields, body, options, texts)],
  ];
  const created = !isDir(kit);
  try {
    fs.mkdirSync(kit, { recursive: true });
    fs.mkdirSync(dirname(index), { recursive: true });
    _writeFiles(files);
  } catch (error) {
    if (created) {
      _removeIfEmpty(kit);
    }
    throw error;
  }
  return kit;
}

/**
 * Resume the work: the note's state becomes `resumed`, its row `active`; returns what to print.
 *
 * The text is `RESUME.md` followed by a blank line and the capped digest.
 * @param {string} kit
 * @param {string} root
 * @param {ParkData} texts
 * @returns {string}
 * @throws {ParkError} the kit was never parked or has no `RESUME.md`
 */
export function unparkKit(kit, root, texts) {
  const name = posix.basename(kit);
  const note = pyPath(kit, PARK_FILE);
  if (!isFile(note)) {
    throw _error(texts, "never_parked", { kit: name });
  }
  const resume = pyPath(kit, RESUME_FILE);
  if (!isFile(resume)) {
    throw _error(texts, "no_resume", { kit: name });
  }
  const updated = withState(readText(note), texts.state_resumed, `${name}/${PARK_FILE}`, texts);
  /** @type {[string, string][]} */
  const files = [[note, updated]];
  const indexText = _readIndex(root);
  const resumed = indexText === null ? null : _resumeIndex(indexText, _kitId(name), texts);
  if (resumed !== null) {
    files.push([_indexPath(root), resumed]);
  }
  _writeFiles(files);
  return `${rstripChars(readText(resume), "\n")}\n\n${digest(kit, texts.default_cap, root, texts)}`;
}

/**
 * What `list` says of one kit; a kit with no `PARK.md` is `never-parked` and has no age.
 * @param {string} kit
 * @param {string} status
 * @param {number} now seconds since the epoch
 * @param {ParkData} texts
 * @returns {KitSummary}
 */
function _summarizeKit(kit, status, now, texts) {
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
      state: texts.state_never_parked,
      plan: "",
      nextAction: "",
      decisions: 0,
      branch: "",
      ageDays: null,
      status,
    };
  }
  const { fields, body } = readNote(kit, texts);
  const modified = fs.statSync(note).mtimeMs / 1000;
  const ageDays = Math.max(0, Math.floor((now - modified) / SECONDS_PER_DAY));
  return {
    id,
    name,
    state: fields.state,
    plan: fields.plan,
    nextAction: fields.nextAction,
    decisions: body.decisions.length,
    branch: fields.branch,
    ageDays,
    status,
  };
}

/**
 * The kits under `.ergon/` that match `query`, stably sorted by id. Reads only.
 * @param {string} root
 * @param {ListQuery} query
 * @param {number} now seconds since the epoch
 * @param {ParkData} texts
 * @returns {KitSummary[]}
 */
export function listKits(root, query, now, texts) {
  const indexText = _readIndex(root);
  const statuses = indexText === null ? new Map() : _indexStatuses(indexText);
  const ergon = ergonRoot(root);
  const summaries = _kitNames(root).map((name) =>
    _summarizeKit(pyPath(ergon, name), statuses.get(_kitId(name)) ?? texts.empty_cell, now, texts),
  );
  return summaries
    .filter(
      (item) =>
        (query.plan === "" || item.plan === query.plan) &&
        (query.state === "" || item.state === query.state) &&
        (query.status === "" || item.status === query.status),
    )
    .sort((a, b) => _compareCodePoints(a.id, b.id));
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
 * One `list` line; an absent value is the empty cell and the age is whole days (`3d`).
 * @param {KitSummary} item
 * @param {ParkData} texts
 * @returns {string}
 */
export function formatSummary(item, texts) {
  const empty = texts.empty_cell;
  return fill(texts.list.line, {
    id: item.id,
    name: item.name,
    state: item.state,
    plan: item.plan || empty,
    next: item.nextAction ? _truncate(item.nextAction, texts.next_width, texts) : empty,
    decisions: String(item.decisions),
    branch: item.branch || empty,
    age: item.ageDays === null ? empty : `${item.ageDays}d`,
  });
}

// --------------------------------------------------------------------------------------
// command line
// --------------------------------------------------------------------------------------

/**
 * One option of a command.
 * @typedef {object} OptionSpec
 * @property {string[]} flags the spellings, the first one names it in a message
 * @property {string} dest the key its value is stored under
 * @property {"one" | "many" | "int"} kind
 * @property {boolean} required
 */

/**
 * What the scanner holds while it walks the arguments of one command.
 * @typedef {object} Scan
 * @property {Map<string, OptionSpec | "help">} flags
 * @property {Map<string, string | string[] | number>} values
 * @property {string[]} positionals
 * @property {string[]} extras
 */

/**
 * The arguments of one command, as the scanner leaves them.
 * @typedef {object} ParsedArgs
 * @property {string} command
 * @property {string} id the positional, empty for `list`
 * @property {Map<string, string | string[] | number>} values
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

/** The commands: whether each takes the kit id positional, and its options. */
const COMMANDS = {
  write: {
    id: true,
    options: [
      _flag("--name", { required: true }),
      _flag("--goal", { required: true }),
      _flag("--next", { required: true }),
      ...["--title", "--plan", "--row", "--branch"].map((flag) => _flag(flag)),
      ...["--revision", "--owned-path", "--check", "--unverified", "--decision", "--answer", "--agent"].map((flag) =>
        _flag(flag, { kind: "many" }),
      ),
      ...["--readiness", "--harness", "--session-id", "--machine"].map((flag) => _flag(flag)),
      _flag("--peer", { kind: "many" }),
      ...["--origin", "--role"].map((flag) => _flag(flag)),
      ROOT_OPTION,
    ],
  },
  unpark: { id: true, options: [ROOT_OPTION] },
  digest: { id: true, options: [_flag("--cap", { kind: "int" }), ROOT_OPTION] },
  list: { id: false, options: [_flag("--plan"), _flag("--state"), _flag("--status"), ROOT_OPTION] },
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
  if (found.spec !== "help") {
    return _store(scan, found.spec, found.explicit, tokens, index);
  }
  if (found.explicit !== null) {
    throw new UsageError(`argument -h/--help: ignored explicit argument ${strRepr(found.explicit)}`);
  }
  return "help";
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
  const scan = { flags, values: new Map(), positionals: [], extras: [] };
  let bare = false;
  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index];
    index += 1;
    const found = bare ? { kind: "positional" } : _classify(token, flags);
    if (!bare && token === "--") {
      bare = true;
    } else if (found.kind === "positional") {
      scan.positionals.push(token);
    } else if (found.kind === "unknown") {
      scan.extras.push(token);
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
  const surplus = [...scan.extras, ...scan.positionals.slice(spec.id ? 1 : 0)];
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
    branch: _text(args, "branch"),
    revisions: _listOf(args, "revision"),
    ownedPaths: _listOf(args, "ownedPath"),
    sessions: _sessionRefs(args, texts),
    peers: _listOf(args, "peer"),
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
 * @param {string} text
 */
function _print(text) {
  process.stdout.write(`${text}\n`);
}

/**
 * @param {ParsedArgs} args
 * @param {string} root
 * @param {ParkData} texts
 */
function _runList(args, root, texts) {
  const query = { plan: _text(args, "plan"), state: _text(args, "state"), status: _text(args, "status") };
  const items = listKits(root, query, Date.now() / 1000, texts);
  if (items.length > 0) {
    _print(items.map((item) => formatSummary(item, texts)).join("\n"));
  } else if (_kitNames(root).length === 0) {
    _print(fill(texts.list.empty, { path: posix.relative(root, ergonRoot(root)) }));
  } else {
    _print(texts.list.no_match);
  }
}

/**
 * @param {ParsedArgs} args
 * @param {string} root
 * @param {ParkData} texts
 */
function _runDigest(args, root, texts) {
  const given = args.values.get("cap");
  const cap = given === undefined ? texts.default_cap : /** @type {number} */ (given);
  if (cap < 0) {
    throw _error(texts, "bad_cap", { value: cap });
  }
  _print(digest(findKit(root, pyStrip(args.id), texts), cap, root, texts));
}

/**
 * @param {ParsedArgs} args
 * @param {string} root
 * @param {ParkData} texts
 */
function _run(args, root, texts) {
  if (args.command === "write") {
    const options = { title: _text(args, "title"), role: _text(args, "role") };
    const kit = writeKit(_fieldsFrom(args, texts), _bodyFrom(args), root, options, texts);
    _print(posix.relative(root, kit));
  } else if (args.command === "unpark") {
    _print(unparkKit(findKit(root, pyStrip(args.id), texts), root, texts));
  } else if (args.command === "digest") {
    _runDigest(args, root, texts);
  } else {
    _runList(args, root, texts);
  }
}

/**
 * CLI entry point: `write`, `unpark`, `digest` or `list`; a failure is one stderr line and exit 1.
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
    const rootValue = parsed.values.get("root");
    const explicit = typeof rootValue === "string" ? pyPath(rootValue) : null;
    _run(parsed, _projectRoot(explicit, texts), texts);
    return 0;
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
