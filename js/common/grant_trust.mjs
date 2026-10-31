/**
 * Trust in a project's own grant files by an owner-accepted digest — the JavaScript twin of
 * `common/grant_trust.py` (C172, ADR 0025 D04/D05; ADR 0020 D01). The Python module is the spec:
 * the same store, the same digest, the same log lines, the same diff text.
 *
 * A digest is the SHA-256 of the file's bytes, not bound to a project or a path. The store is
 * `$AKMON_TRUST_DIR`, else `$XDG_STATE_HOME/akmon/trust`, else `~/.local/state/akmon/trust`;
 * `accepted/<digest>` is a byte copy of every accepted file and its existence is the acceptance;
 * `trust.log` is the append-only TSV record `timestamp · event · digest · path · project ·
 * previous`, `-` for an absent field. The store is created by the first write, never by a read, and
 * it is never inside the project's checkout: a resolved path (links followed) inside the resolved
 * project root is refused, since a store the project's own files could reach would let the project
 * ship pre-accepted copies. The digest is content-keyed; the history is keyed by (project name,
 * relative path), so a new file in one project is never presented as a change of another's, and
 * another project's accepted version of the same path is found only to show a diff against it.
 *
 * Data (the C102/C103 convention): `common/grant_trust.json` holds the layout names; {@link
 * resolveStore} and {@link grantsDirectory} read it, and the environment is an argument of the one
 * function that needs it — nothing deeper reads it.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - the log is read as bytes and split on `\n` only, as the Python does, where `str.splitlines`
 *   would also break on `\r`, `\v`, `\f` and U+2028;
 * - the bytes of a grant file are decoded as UTF-8 with replacement and the BOM kept
 *   (`ignoreBOM`), as `bytes.decode("utf-8", errors="replace")` does;
 * - a relative path is the lexical `posix.relative`, as `Path.relative_to` is; callers pass
 *   resolved absolute paths;
 * - the line diff is the same hand-written longest-common-subsequence script on both sides, because
 *   `difflib` has no Node counterpart and a second algorithm would print different text.
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { read } from "./jsondata.mjs";
import { aitnaRoot, resolvePath } from "./project_root.mjs";
import { codePointCompare } from "./sort.mjs";

/** The three kinds of log line. */
export const EVENT_ACCEPT = "accept";
export const EVENT_REVOKE = "revoke";
export const EVENT_UNTRUSTED = "untrusted";

/** What stands in a log field with no value. */
export const NO_PREVIOUS = "-";

/** Hex characters of a digest a listing shows, and the shortest prefix a command resolves. */
export const SHORT_DIGEST_LENGTH = 12;

/** Where a grant file stands: accepted as it is, an accepted path with new content, or unseen. */
export const TrustState = Object.freeze({ TRUSTED: "trusted", NEW: "new", CHANGED: "changed" });

const _DIGEST = /^[0-9a-f]{64}$/;
const _HEX = /^[0-9a-f]+$/;
const _EVENTS = [EVENT_ACCEPT, EVENT_REVOKE, EVENT_UNTRUSTED];
const _CONTEXT_LINES = 3;
// Two files whose differing middle holds more line pairs than this are shown as a full
// replacement instead of a minimal diff: the table is quadratic and grant files are small.
const _MAX_DIFF_CELLS = 4_000_000;

/** A trust operation cannot proceed; the message names the file, digest or line. */
export class GrantTrustError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "GrantTrustError";
  }
}

/**
 * The resolved store: where accepted copies and the log live (nothing is created by resolving).
 * @typedef {object} TrustStore
 * @property {string} root
 * @property {string} acceptedDir
 * @property {string} logPath
 */

/**
 * One grant file as read once: what is shown, digested and accepted is these very bytes.
 * @typedef {object} GrantFile
 * @property {string} relative
 * @property {string} project
 * @property {Buffer} content
 * @property {string} digest
 */

/**
 * A grant file's state. `previous`: for `changed` the last accepted digest at its path, for
 * `trusted` its own digest, `null` for `new`.
 * @typedef {object} FileTrust
 * @property {GrantFile} grant
 * @property {string} state one of {@link TrustState}
 * @property {string | null} previous
 */

/**
 * One log line. `previous` is {@link NO_PREVIOUS} when the path had no accepted version.
 * @typedef {object} TrustEvent
 * @property {string} timestamp
 * @property {string} event
 * @property {string} digest
 * @property {string} path
 * @property {string} project
 * @property {string} previous
 */

/**
 * What the log says; `medianSeconds` is `null` when no sighted digest was later accepted.
 * @typedef {object} TrustReport
 * @property {number} accepts
 * @property {number} reaccepts
 * @property {number} revokes
 * @property {number} untrustedDigests
 * @property {number} acceptedAfterSighting
 * @property {number | null} medianSeconds
 */

/**
 * The shape of `common/grant_trust.json`.
 * @typedef {object} GrantTrustData
 * @property {string} grants_dir
 * @property {string} store_env
 * @property {string} state_home_env
 * @property {string} state_home_subdir
 * @property {string} store_subdir
 * @property {string} accepted_dir
 * @property {string} log_file
 */

/** @returns {GrantTrustData} */
function _data() {
  return /** @type {GrantTrustData} */ (read(fileURLToPath(new URL("../../common/grant_trust.json", import.meta.url))));
}

/**
 * The store `environment` names: `AKMON_TRUST_DIR`, else the XDG state home, else `~/.local/state`.
 * An empty variable is unset. The directory is not created: only a write does that. The store is the
 * resolved path, links followed, so what was checked is what is written to.
 * @param {Record<string, string | undefined>} environment
 * @param {string} projectRoot the project's root
 * @returns {TrustStore}
 * @throws {GrantTrustError} the store lies inside the project at `projectRoot` (resolved the same way).
 */
export function resolveStore(environment, projectRoot) {
  const data = _data();
  const explicit = environment[data.store_env];
  const stateHome = environment[data.state_home_env];
  let given;
  if (explicit) {
    given = explicit;
  } else if (stateHome) {
    given = posix.join(stateHome, data.store_subdir);
  } else {
    given = posix.join(environment["HOME"] || os.homedir(), data.state_home_subdir, data.store_subdir);
  }
  const root = resolvePath(given);
  const project = resolvePath(projectRoot);
  const outside = posix.relative(project, root);
  if (outside === "" || !(outside === ".." || outside.startsWith("../") || posix.isAbsolute(outside))) {
    throw new GrantTrustError(
      `the trust store ${root} is inside the project ${project}; ` +
        `set ${data.store_env} to a directory outside the checkout (ADR 0025/D05)`,
    );
  }
  return { root, acceptedDir: posix.join(root, data.accepted_dir), logPath: posix.join(root, data.log_file) };
}

/**
 * The default grant location of the project at `root`: `<dev root>/grants` (ADR 0025 D05, provisional).
 * @param {string} root
 * @returns {string}
 */
export function grantsDirectory(root) {
  return posix.join(aitnaRoot(root), _data().grants_dir);
}

/**
 * Every regular file under `directory`, recursively, sorted by relative path; none when it is
 * absent. A symbolic link is not a regular file here, whatever it points at, and a link to a
 * directory is not entered.
 * @param {string} directory
 * @returns {string[]}
 */
export function listGrantFiles(directory) {
  /** @type {string[]} */
  const found = [];
  const pending = [directory];
  while (pending.length > 0) {
    const current = /** @type {string} */ (pending.pop());
    /** @type {fs.Dirent[]} */
    let entries;
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch (error) {
      if (["ENOENT", "ENOTDIR"].includes(/** @type {{code?: string}} */ (error).code ?? "")) {
        continue;
      }
      throw error;
    }
    for (const entry of entries) {
      const path = posix.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(path);
      } else if (entry.isFile()) {
        found.push(path);
      }
    }
  }
  return found.sort((a, b) => codePointCompare(posix.relative(directory, a), posix.relative(directory, b)));
}

/**
 * @param {Uint8Array} content
 * @returns {string}
 */
function _sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

/**
 * The SHA-256 hex digest of the bytes of `path`.
 * @param {string} path
 * @returns {string}
 */
export function fileDigest(path) {
  return _sha256(fs.readFileSync(path));
}

/**
 * @param {string} value
 * @param {string} what
 */
function _requireLineSafe(value, what) {
  if (/[\t\n\r]/.test(value)) {
    throw new GrantTrustError(`the ${what} ${JSON.stringify(value)} holds a tab or a line break and cannot be logged`);
  }
}

/**
 * Read `path` once as a grant file of the project at `root`.
 * @param {string} path
 * @param {string} root
 * @returns {GrantFile}
 * @throws {GrantTrustError} `path` is outside `root`, or its relative path or the project's name
 *   holds a tab or a newline, which would break the log's lines.
 */
export function loadGrant(path, root) {
  const relative = posix.relative(root, path);
  if (relative === "" || relative === ".." || relative.startsWith("../") || posix.isAbsolute(relative)) {
    throw new GrantTrustError(`${path} is outside the project root ${root}`);
  }
  const project = posix.basename(root);
  _requireLineSafe(relative, "path");
  _requireLineSafe(project, "project name");
  const content = fs.readFileSync(path);
  return { relative, project, content, digest: _sha256(content) };
}

/**
 * The log line of `event`, without its newline.
 * @param {TrustEvent} event
 * @returns {string}
 */
export function formatEvent(event) {
  return [event.timestamp, event.event, event.digest, event.path, event.project, event.previous].join("\t");
}

/**
 * The event a log `line` records.
 * @param {string} line
 * @returns {TrustEvent}
 * @throws {GrantTrustError} the line does not hold six fields or names an unknown event.
 */
export function parseEvent(line) {
  const fields = line.split("\t");
  if (fields.length !== 6 || !_EVENTS.includes(fields[1])) {
    throw new GrantTrustError(`malformed trust log line: ${JSON.stringify(line)}`);
  }
  const [timestamp, event, digest, path, project, previous] = fields;
  return { timestamp, event, digest, path, project, previous };
}

/**
 * Every event of the log in order; empty when the store has none. Never creates anything.
 * @param {TrustStore} store
 * @returns {TrustEvent[]}
 * @throws {GrantTrustError} a line is malformed (the line number is named).
 */
export function readLog(store) {
  /** @type {string} */
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(fs.readFileSync(store.logPath));
  } catch (error) {
    if (/** @type {{code?: string}} */ (error).code === "ENOENT") {
      return [];
    }
    throw error;
  }
  const lines = text.split("\n");
  if (lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines.map((line, index) => {
    try {
      return parseEvent(line);
    } catch (error) {
      throw new GrantTrustError(`${store.logPath}:${index + 1}: ${/** @type {Error} */ (error).message}`);
    }
  });
}

/**
 * @param {string} text
 * @returns {boolean}
 */
function _isDigest(text) {
  return _DIGEST.test(text);
}

/**
 * Whether `digest` is accepted: its copy is in the store.
 * @param {string} digest
 * @param {TrustStore} store
 * @returns {boolean}
 */
export function isAccepted(digest, store) {
  if (!_isDigest(digest)) {
    return false;
  }
  try {
    return fs.statSync(posix.join(store.acceptedDir, digest)).isFile();
  } catch {
    return false;
  }
}

/**
 * The accepted copy of `digest`.
 * @param {string} digest
 * @param {TrustStore} store
 * @returns {Buffer}
 * @throws {GrantTrustError} `digest` is not accepted.
 */
export function acceptedContent(digest, store) {
  if (!isAccepted(digest, store)) {
    throw new GrantTrustError(`digest ${digest} is not accepted`);
  }
  return fs.readFileSync(posix.join(store.acceptedDir, digest));
}

/**
 * The newest accepted digest the log records for `relative` in `project` that is still accepted. A
 * revoked digest has lost its copy and is skipped, so an earlier surviving version answers.
 * @param {string} relative
 * @param {string} project
 * @param {TrustStore} store
 * @returns {string | null}
 */
export function lastAccepted(relative, project, store) {
  for (const event of readLog(store).reverse()) {
    if (
      event.event === EVENT_ACCEPT &&
      event.path === relative &&
      event.project === project &&
      isAccepted(event.digest, store)
    ) {
      return event.digest;
    }
  }
  return null;
}

/**
 * The newest still-accepted acceptance of `relative` in a project other than `project`. Only for
 * showing the owner a diff: it never decides a state, and it names the project the version was
 * accepted in.
 * @param {string} relative
 * @param {string} project
 * @param {TrustStore} store
 * @returns {TrustEvent | null}
 */
export function lastAcceptedElsewhere(relative, project, store) {
  for (const event of readLog(store).reverse()) {
    if (
      event.event === EVENT_ACCEPT &&
      event.path === relative &&
      event.project !== project &&
      isAccepted(event.digest, store)
    ) {
      return event;
    }
  }
  return null;
}

/**
 * The state of `grant` against `store`. Reads only.
 * @param {GrantFile} grant
 * @param {TrustStore} store
 * @returns {FileTrust}
 */
export function fileTrust(grant, store) {
  if (isAccepted(grant.digest, store)) {
    return { grant, state: TrustState.TRUSTED, previous: grant.digest };
  }
  const previous = lastAccepted(grant.relative, grant.project, store);
  return { grant, state: previous === null ? TrustState.NEW : TrustState.CHANGED, previous };
}

/**
 * @param {Date | undefined} at
 * @returns {string}
 */
function _stamp(at) {
  const moment = at ?? new Date();
  if (Number.isNaN(moment.getTime())) {
    throw new RangeError(`a trust event time must be a valid date, got ${moment}`);
  }
  return `${moment.toISOString().slice(0, 19)}Z`;
}

/**
 * @param {string} stamp
 * @returns {number} milliseconds since the epoch
 */
function _parseStamp(stamp) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(stamp) || Number.isNaN(Date.parse(stamp))) {
    throw new GrantTrustError(`malformed trust log timestamp ${JSON.stringify(stamp)}`);
  }
  return Date.parse(stamp);
}

/**
 * Write the accepted copy whole or not at all: a temporary file in the store, then a rename.
 * @param {GrantFile} grant
 * @param {TrustStore} store
 */
function _storeCopy(grant, store) {
  fs.mkdirSync(store.acceptedDir, { recursive: true });
  const temporary = posix.join(store.acceptedDir, `.${grant.digest}.${process.pid}.tmp`);
  try {
    fs.writeFileSync(temporary, grant.content);
    fs.renameSync(temporary, posix.join(store.acceptedDir, grant.digest));
  } catch (error) {
    fs.rmSync(temporary, { force: true });
    throw error;
  }
}

/**
 * Append the event's line in one `write` on an append descriptor, creating the store on first use.
 * @param {TrustEvent} event
 * @param {TrustStore} store
 */
function _append(event, store) {
  fs.mkdirSync(store.root, { recursive: true });
  const line = Buffer.from(`${formatEvent(event)}\n`, "utf8");
  const descriptor = fs.openSync(store.logPath, "a", 0o644);
  try {
    if (fs.writeSync(descriptor, line) !== line.length) {
      throw new GrantTrustError(`short write to ${store.logPath}`);
    }
  } finally {
    fs.closeSync(descriptor);
  }
}

/**
 * Accept `grant`: keep a copy of exactly these bytes, then log it; returns the logged event.
 * @param {GrantFile} grant
 * @param {TrustStore} store
 * @param {Date} [at] the event time (default: now)
 * @returns {TrustEvent}
 * @throws {GrantTrustError} the digest is already accepted (nothing is logged).
 */
export function accept(grant, store, at) {
  if (isAccepted(grant.digest, store)) {
    throw new GrantTrustError(`${grant.relative} is already accepted as ${grant.digest}`);
  }
  const timestamp = _stamp(at); // before anything is written, so a refused time leaves the store untouched
  const previous = lastAccepted(grant.relative, grant.project, store) || NO_PREVIOUS;
  _storeCopy(grant, store);
  /** @type {TrustEvent} */
  const event = {
    timestamp,
    event: EVENT_ACCEPT,
    digest: grant.digest,
    path: grant.relative,
    project: grant.project,
    previous,
  };
  _append(event, store);
  return event;
}

/**
 * Revoke the full `digest`: remove its copy, then log it with the path and project it was
 * accepted for.
 * @param {string} digest
 * @param {TrustStore} store
 * @param {Date} [at] the event time (default: now)
 * @returns {TrustEvent}
 * @throws {GrantTrustError} `digest` is not accepted.
 */
export function revoke(digest, store, at) {
  if (!isAccepted(digest, store)) {
    throw new GrantTrustError(`digest ${digest} is not accepted`);
  }
  const timestamp = _stamp(at);
  let path = NO_PREVIOUS;
  let project = NO_PREVIOUS;
  for (const event of readLog(store).reverse()) {
    if (event.event === EVENT_ACCEPT && event.digest === digest) {
      ({ path, project } = event);
      break;
    }
  }
  fs.unlinkSync(posix.join(store.acceptedDir, digest));
  /** @type {TrustEvent} */
  const revoked = { timestamp, event: EVENT_REVOKE, digest, path, project, previous: NO_PREVIOUS };
  _append(revoked, store);
  return revoked;
}

/**
 * Log a sighting of `grant` as untrusted, once per digest; `null` when nothing was logged.
 * Nothing is logged for a digest that is accepted or was sighted before: the log counts distinct
 * untrusted contents, not how often a run met them.
 * @param {GrantFile} grant
 * @param {TrustStore} store
 * @param {Date} [at] the event time (default: now)
 * @returns {TrustEvent | null}
 */
export function recordUntrusted(grant, store, at) {
  const timestamp = _stamp(at);
  if (isAccepted(grant.digest, store)) {
    return null;
  }
  if (readLog(store).some((event) => event.event === EVENT_UNTRUSTED && event.digest === grant.digest)) {
    return null;
  }
  const previous = lastAccepted(grant.relative, grant.project, store) || NO_PREVIOUS;
  /** @type {TrustEvent} */
  const event = {
    timestamp,
    event: EVENT_UNTRUSTED,
    digest: grant.digest,
    path: grant.relative,
    project: grant.project,
    previous,
  };
  _append(event, store);
  return event;
}

/**
 * The one accepted digest that `reference` — a full digest or a prefix of at least 12 hex — names.
 * @param {string} reference
 * @param {TrustStore} store
 * @returns {string}
 * @throws {GrantTrustError} no accepted digest, or more than one, starts with `reference`.
 */
export function resolveDigest(reference, store) {
  if (reference.length < SHORT_DIGEST_LENGTH || !_HEX.test(reference)) {
    throw new GrantTrustError(
      `${JSON.stringify(reference)} is not a digest: give at least ${SHORT_DIGEST_LENGTH} hex characters`,
    );
  }
  /** @type {string[]} */
  let names = [];
  try {
    names = fs.readdirSync(store.acceptedDir);
  } catch (error) {
    if (/** @type {{code?: string}} */ (error).code !== "ENOENT") {
      throw error;
    }
  }
  const matches = names.filter((name) => _isDigest(name) && name.startsWith(reference)).sort();
  if (matches.length !== 1) {
    throw new GrantTrustError(
      `digest ${reference} ${matches.length === 0 ? "names no accepted digest" : "is ambiguous"}`,
    );
  }
  return matches[0];
}

/**
 * @param {number[]} values a non-empty list
 * @returns {number}
 */
function _median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = sorted.length >> 1;
  return sorted.length % 2 === 1 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

/**
 * How many acceptances follow an earlier acceptance of the same file: the same project and relative path.
 * @param {TrustEvent[]} accepts
 * @returns {number}
 */
function _reaccepts(accepts) {
  /** @type {Set<string>} */
  const seen = new Set();
  let count = 0;
  for (const event of accepts) {
    const key = JSON.stringify([event.project, event.path]);
    if (seen.has(key)) {
      count += 1;
    }
    seen.add(key);
  }
  return count;
}

/**
 * The summary of the log: acceptances, re-acceptances, revocations and the sighting-to-acceptance time.
 * @param {TrustStore} store
 * @returns {TrustReport}
 */
export function trustReport(store) {
  const events = readLog(store);
  /** @type {Map<string, number>} */
  const firstSighting = new Map();
  events.forEach((event, index) => {
    if (event.event === EVENT_UNTRUSTED && !firstSighting.has(event.digest)) {
      firstSighting.set(event.digest, index);
    }
  });
  /** @type {number[]} */
  const seconds = [];
  for (const [digest, sighted] of firstSighting) {
    const accepted = events.slice(sighted + 1).find((event) => event.event === EVENT_ACCEPT && event.digest === digest);
    if (accepted !== undefined) {
      seconds.push((_parseStamp(accepted.timestamp) - _parseStamp(events[sighted].timestamp)) / 1000);
    }
  }
  const accepts = events.filter((event) => event.event === EVENT_ACCEPT);
  return {
    accepts: accepts.length,
    reaccepts: _reaccepts(accepts),
    revokes: events.filter((event) => event.event === EVENT_REVOKE).length,
    untrustedDigests: firstSighting.size,
    acceptedAfterSighting: seconds.length,
    medianSeconds: seconds.length > 0 ? _median(seconds) : null,
  };
}

/**
 * @param {Uint8Array} content
 * @returns {string[]}
 */
function _lines(content) {
  const parts = new TextDecoder("utf-8", { fatal: false, ignoreBOM: true }).decode(content).split("\n");
  return parts[parts.length - 1] === "" ? parts.slice(0, -1) : parts;
}

/**
 * A hunk range as `difflib` spells it: the 1-based start, and the length unless it is one.
 * @param {number} before
 * @param {number} length
 * @returns {string}
 */
function _span(before, length) {
  if (length === 1) {
    return String(before + 1);
  }
  return `${length === 0 ? before : before + 1},${length}`;
}

/** @typedef {[" " | "-" | "+", string]} EditStep */

/**
 * @param {string[]} oldLines
 * @param {string[]} newLines
 * @returns {EditStep[]}
 */
function _lcsScript(oldLines, newLines) {
  const rows = oldLines.length;
  const columns = newLines.length;
  /** @type {number[][]} */
  const table = Array.from({ length: rows + 1 }, () => new Array(columns + 1).fill(0));
  for (let row = rows - 1; row >= 0; row--) {
    for (let column = columns - 1; column >= 0; column--) {
      table[row][column] =
        oldLines[row] === newLines[column]
          ? table[row + 1][column + 1] + 1
          : Math.max(table[row + 1][column], table[row][column + 1]);
    }
  }
  /** @type {EditStep[]} */
  const script = [];
  let row = 0;
  let column = 0;
  while (row < rows && column < columns) {
    if (oldLines[row] === newLines[column]) {
      script.push([" ", oldLines[row]]);
      row++;
      column++;
    } else if (table[row + 1][column] >= table[row][column + 1]) {
      script.push(["-", oldLines[row]]);
      row++;
    } else {
      script.push(["+", newLines[column]]);
      column++;
    }
  }
  for (; row < rows; row++) {
    script.push(["-", oldLines[row]]);
  }
  for (; column < columns; column++) {
    script.push(["+", newLines[column]]);
  }
  return script;
}

/**
 * The line-level edit script: a longest common subsequence, deletions first on ties.
 * @param {string[]} oldLines
 * @param {string[]} newLines
 * @returns {EditStep[]}
 */
function _editScript(oldLines, newLines) {
  let start = 0;
  while (start < oldLines.length && start < newLines.length && oldLines[start] === newLines[start]) {
    start++;
  }
  let endOld = oldLines.length;
  let endNew = newLines.length;
  while (endOld > start && endNew > start && oldLines[endOld - 1] === newLines[endNew - 1]) {
    endOld--;
    endNew--;
  }
  const middleOld = oldLines.slice(start, endOld);
  const middleNew = newLines.slice(start, endNew);
  /** @type {EditStep[]} */
  const script = oldLines.slice(0, start).map((line) => [" ", line]);
  if (middleOld.length * middleNew.length > _MAX_DIFF_CELLS) {
    script.push(...middleOld.map((/** @type {string} */ line) => /** @type {EditStep} */ (["-", line])));
    script.push(...middleNew.map((/** @type {string} */ line) => /** @type {EditStep} */ (["+", line])));
  } else {
    script.push(..._lcsScript(middleOld, middleNew));
  }
  script.push(...oldLines.slice(endOld).map((/** @type {string} */ line) => /** @type {EditStep} */ ([" ", line])));
  return script;
}

/**
 * A unified diff (three lines of context) of two files' text; empty when the text is the same.
 * Bytes are read as UTF-8 with replacement. The text is split on `\n` only, so a changed `\r`
 * shows as a changed line; a difference in the final newline alone is not shown, and the caller
 * says so when the bytes differ and this is empty.
 * @param {Uint8Array} oldContent
 * @param {Uint8Array} newContent
 * @param {string} oldLabel
 * @param {string} newLabel
 * @returns {string}
 */
export function unifiedDiff(oldContent, newContent, oldLabel, newLabel) {
  const operations = _editScript(_lines(oldContent), _lines(newContent));
  /** @type {number[]} */
  const changed = [];
  operations.forEach(([tag], index) => {
    if (tag !== " ") {
      changed.push(index);
    }
  });
  if (changed.length === 0) {
    return "";
  }
  /** @type {[number, number][]} */
  const ranges = [];
  for (const index of changed) {
    const low = Math.max(0, index - _CONTEXT_LINES);
    const high = Math.min(operations.length - 1, index + _CONTEXT_LINES);
    const last = ranges[ranges.length - 1];
    if (last !== undefined && low <= last[1] + 1) {
      last[1] = high;
    } else {
      ranges.push([low, high]);
    }
  }
  const out = [`--- ${oldLabel}\n`, `+++ ${newLabel}\n`];
  for (const [low, high] of ranges) {
    const before = operations.slice(0, low);
    const hunk = operations.slice(low, high + 1);
    const oldStart = before.filter(([tag]) => tag !== "+").length;
    const newStart = before.filter(([tag]) => tag !== "-").length;
    const oldLength = hunk.filter(([tag]) => tag !== "+").length;
    const newLength = hunk.filter(([tag]) => tag !== "-").length;
    out.push(`@@ -${_span(oldStart, oldLength)} +${_span(newStart, newLength)} @@\n`);
    for (const [tag, line] of hunk) {
      out.push(`${tag}${line}\n`);
    }
  }
  return out.join("");
}
