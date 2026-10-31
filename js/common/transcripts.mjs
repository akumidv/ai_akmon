/**
 * Where a project's agent sessions are recorded, and which of them a learning run may read — the
 * JavaScript twin of `common/transcripts.py` (C177, ADR 0026 D07; ADR 0020 D01). The Python module
 * is the spec: the same answers, the same names, the same ordering.
 *
 * Claude Code writes `~/.claude/projects/<munged-root>/<session-id>.jsonl`; Codex writes
 * `~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*.jsonl` whose first line is a `session_meta` record
 * carrying the session's `id` and `cwd`. A learning run reads this project's sessions only: a
 * Claude directory is the one named by the project root, or one named by a path inside it (the
 * munged name followed by `-`) whose transcripts record a `cwd` inside the root; a Codex file
 * counts only when its recorded `cwd` is the root or inside it. `tools/model_routing/stats.mjs`
 * imports the first three helpers from here.
 *
 * Twin notes:
 * - a session's `modified` is a `Date` (millisecond resolution); the Python's microsecond
 *   `datetime` order is kept in `modifiedMicros`, the key the sort and the `since` filter use, so
 *   two files written within one millisecond order as the Python orders them;
 * - Python's `Path.rglob("*.jsonl")` is a walk that does not follow directory links, and matches
 *   a dot-name like `.jsonl`; {@link _walkJsonl} is that walk.
 */

import fs from "node:fs";
import os from "node:os";
import { basename } from "node:path";

import { jsonLoads, JSONDecodeError } from "./pyjson.mjs";
import { isRelativeTo, resolvePath } from "./project_root.mjs";
import { decodeUtf8, dictGet, isDict, isDir, isFile, isOSError, pyError, pyPath } from "./pyvalue.mjs";
import { codePointCompare } from "./sort.mjs";

/** The kinds a session file can be: `claude` and `codex` name the harness that wrote it. */
export const CLAUDE = "claude";
export const CODEX = "codex";

const _ASTRAL = 0xffff;
const _ALNUM = /^[A-Za-z0-9]$/;
const _FIRST_LINE_CHUNK = 65536;
const _CWD_SCAN_BYTES = 1 << 20;

/** One recorded session of a project: which harness wrote it, its id, when it last changed, its size. */
export class SessionFile {
  /**
   * @param {string} kind `claude` or `codex`
   * @param {string} sessionId
   * @param {number} size bytes
   * @param {string} path
   * @param {bigint} modifiedMicros the modification time in whole microseconds since the epoch
   */
  constructor(kind, sessionId, size, path, modifiedMicros) {
    this.kind = kind;
    this.sessionId = sessionId;
    this.size = size;
    this.path = path;
    this.modifiedMicros = modifiedMicros;
    /** The modification time, to the millisecond. */
    this.modified = new Date(Number(modifiedMicros / 1000n));
    Object.freeze(this);
  }
}

/**
 * The `~/.claude/projects/` directory name for a project root: every non-alphanumeric character
 * becomes `-`.
 *
 * Claude Code replaces each UTF-16 code unit outside `[A-Za-z0-9]` with `-`, so `_` and `.` in a
 * path become dashes as `/` does (`/home/a/_cto` → `-home-a--cto`, read off the directories on
 * disk; M203 says which cases were observed and which are inferred); an astral character is two
 * code units, hence two dashes. The very long path Claude Code truncates and hashes is not
 * reproduced.
 * @param {string} projectRoot
 * @returns {string}
 */
export function mungedProjectDir(projectRoot) {
  let munged = "";
  for (const character of resolvePath(projectRoot)) {
    const codePoint = character.codePointAt(0) ?? 0;
    munged += _ALNUM.test(character) ? character : codePoint > _ASTRAL ? "--" : "-";
  }
  return munged;
}

/**
 * The project's transcript directory under `<claudeHome>/projects/`.
 * @param {string} projectRoot
 * @param {string | null} [claudeHome] default: `~/.claude`
 * @returns {string}
 */
export function transcriptsDir(projectRoot, claudeHome = null) {
  const home = claudeHome || pyPath(os.homedir(), ".claude");
  return pyPath(home, "projects", mungedProjectDir(projectRoot));
}

/**
 * `Path.suffix`: the last dot-suffix of the name, `""` for a dotfile or a trailing dot.
 * @param {string} name
 * @returns {string}
 */
export function pySuffix(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot) : "";
}

/**
 * `Path.stem`: the name without its last suffix.
 * @param {string} path
 * @returns {string}
 */
export function pyStem(path) {
  const name = basename(path);
  return name.slice(0, name.length - pySuffix(name).length);
}

/**
 * The most recently modified `*.jsonl` file in `directory` — the current session; null when none.
 * @param {string} directory
 * @returns {string | null}
 */
export function newestJsonl(directory) {
  if (!isDir(directory)) {
    return null;
  }
  /** @type {string | null} */ let best = null;
  /** @type {bigint} */ let bestTime = 0n;
  for (const name of fs.readdirSync(directory)) {
    const path = pyPath(directory, name);
    if (!isFile(path) || pySuffix(name) !== ".jsonl") {
      continue;
    }
    const mtime = fs.statSync(path, { bigint: true }).mtimeNs;
    if (best === null || mtime > bestTime) {
      best = path;
      bestTime = mtime;
    }
  }
  return best;
}

/**
 * A modification time in whole microseconds, rounded half to even as `datetime.fromtimestamp` does.
 * @param {bigint} nanoseconds
 * @returns {bigint}
 */
function _micros(nanoseconds) {
  const whole = nanoseconds / 1000n;
  const rest = nanoseconds % 1000n;
  return rest > 500n || (rest === 500n && whole % 2n === 1n) ? whole + 1n : whole;
}

/**
 * `path` as a session file stamped with its mtime (UTC), or null when it is not newer than `since`
 * and when the file is gone — a session file can vanish between the listing of its directory and
 * the `stat`.
 * @param {string} path
 * @param {Date | null} since
 * @param {string} kind
 * @param {string} sessionId
 * @returns {SessionFile | null}
 */
function _modifiedAfter(path, since, kind, sessionId) {
  /** @type {fs.BigIntStats} */
  let info;
  try {
    info = fs.statSync(path, { bigint: true });
  } catch (error) {
    if (isOSError(error)) {
      return null;
    }
    throw error;
  }
  const micros = _micros(info.mtimeNs);
  if (since !== null && micros <= BigInt(since.getTime()) * 1000n) {
    return null;
  }
  return new SessionFile(kind, sessionId, Number(info.size), path, micros);
}

/**
 * Two session files in the order the Python sorts them: by modification time, then by file name.
 * @param {SessionFile} a
 * @param {SessionFile} b
 * @returns {number}
 */
export function bySessionOrder(a, b) {
  if (a.modifiedMicros !== b.modifiedMicros) {
    return a.modifiedMicros < b.modifiedMicros ? -1 : 1;
  }
  return codePointCompare(basename(a.path), basename(b.path));
}

/**
 * Whether the resolved `path` is `root` or lies inside it.
 * @param {string} path
 * @param {string} root
 * @returns {boolean}
 */
function _isInside(path, root) {
  return isRelativeTo(path, root);
}

/**
 * The first `_CWD_SCAN_BYTES` of `path`; null when it cannot be read.
 * @param {string} path
 * @returns {Buffer | null}
 */
function _readHead(path) {
  try {
    const descriptor = fs.openSync(path, "r");
    try {
      const block = Buffer.allocUnsafe(_CWD_SCAN_BYTES);
      let filled = 0;
      while (filled < _CWD_SCAN_BYTES) {
        const count = fs.readSync(descriptor, block, filled, _CWD_SCAN_BYTES - filled, null);
        if (count === 0) {
          break;
        }
        filled += count;
      }
      return Buffer.from(block.subarray(0, filled));
    } finally {
      fs.closeSync(descriptor);
    }
  } catch (error) {
    if (isOSError(error)) {
      return null;
    }
    throw error;
  }
}

/**
 * The `cwd` a transcript line records, or null: a line that is not a JSON object or is not UTF-8
 * records none.
 * @param {Buffer} line
 * @returns {string | null}
 */
function _lineCwd(line) {
  /** @type {any} */
  let record;
  try {
    record = jsonLoads(decodeUtf8(line));
  } catch (error) {
    const name = /** @type {Error} */ (error).name;
    if (error instanceof JSONDecodeError || name === "UnicodeDecodeError") {
      return null;
    }
    throw error;
  }
  const recorded = isDict(record) ? dictGet(record, "cwd") : null;
  return _isText(recorded) && !recorded.includes("\0") ? recorded : null;
}

/**
 * The `cwd` of the first line of the Claude transcript `path` that records one (resolved), else null.
 *
 * Only the first `_CWD_SCAN_BYTES` are read (a final line cut by that limit is dropped): the first
 * lines of a transcript are bookkeeping records with no `cwd`.
 * @param {string} path
 * @returns {string | null}
 */
function _recordedCwd(path) {
  const head = _readHead(path);
  if (head === null) {
    return null;
  }
  const lines = _splitLines(head);
  if (head.length === _CWD_SCAN_BYTES) {
    lines.pop();
  }
  for (const line of lines) {
    const recorded = _lineCwd(line);
    if (recorded !== null) {
      return _resolveRecorded(recorded);
    }
  }
  return null;
}

/**
 * `head` split on `\n` bytes, as `bytes.split(b"\n")`.
 * @param {Buffer} head
 * @returns {Buffer[]}
 */
function _splitLines(head) {
  /** @type {Buffer[]} */
  const lines = [];
  let start = 0;
  for (;;) {
    const newline = head.indexOf(0x0a, start);
    if (newline < 0) {
      lines.push(head.subarray(start));
      return lines;
    }
    lines.push(head.subarray(start, newline));
    start = newline + 1;
  }
}

/**
 * This project's Claude transcripts modified after `since` (all when null), oldest first.
 *
 * Two kinds of directory under `<claudeHome>/projects/` count. The one named by the project root
 * ({@link mungedProjectDir}) is the project's own. One whose name is that name followed by `-` is
 * a session started in a path *inside* the root (`<root>/sub` → `<munged>-sub`) — but `<root>-x`
 * munges the same way, so each of its transcripts must record a `cwd` that is the root or inside
 * it; a sibling's, or a transcript recording none, is left out. Only top-level `*.jsonl` files are
 * read — the subagent transcripts under `<session-id>/subagents/` belong to the session that
 * spawned them. A file that vanishes during the listing is skipped.
 * @param {string} projectRoot
 * @param {string | null} [claudeHome] default: `~/.claude`
 * @param {Date | null} [since]
 * @returns {SessionFile[]}
 */
export function claudeSessions(projectRoot, claudeHome = null, since = null) {
  const base = pyPath(claudeHome || pyPath(os.homedir(), ".claude"), "projects");
  if (!isDir(base)) {
    return [];
  }
  const name = mungedProjectDir(projectRoot);
  const root = resolvePath(projectRoot);
  /** @type {SessionFile[]} */
  const found = [];
  for (const entry of fs.readdirSync(base)) {
    const directory = pyPath(base, entry);
    if ((entry === name || entry.startsWith(`${name}-`)) && isDir(directory)) {
      found.push(..._directorySessions(directory, entry === name, root, since));
    }
  }
  return found.sort(bySessionOrder);
}

/**
 * The sessions of one project directory: all of them when it is the project's `own`, else those
 * whose transcript records a `cwd` inside `root`.
 * @param {string} directory
 * @param {boolean} own
 * @param {string} root the resolved project root
 * @param {Date | null} since
 * @returns {SessionFile[]}
 */
function _directorySessions(directory, own, root, since) {
  /** @type {SessionFile[]} */
  const found = [];
  for (const file of fs.readdirSync(directory)) {
    const path = pyPath(directory, file);
    if (pySuffix(file) !== ".jsonl" || !isFile(path)) {
      continue;
    }
    const item = _modifiedAfter(path, since, CLAUDE, pyStem(path));
    const recorded = item === null || own ? null : _recordedCwd(path);
    if (item !== null && (own || (recorded !== null && _isInside(recorded, root)))) {
      found.push(item);
    }
  }
  return found;
}

/**
 * The `payload` of a rollout's first line when it is a `session_meta` record, else null.
 *
 * Only the first line is read, as the Python's `readline` does; an unreadable file, bytes that are
 * not UTF-8 and a first line that is not JSON are each "not a rollout" (null).
 * @param {string} path
 * @returns {Record<string, any> | null}
 */
function _codexMeta(path) {
  /** @type {any} */
  let record;
  try {
    record = jsonLoads(decodeUtf8(_firstLine(path)));
  } catch (error) {
    const name = /** @type {Error} */ (error).name;
    if (isOSError(error) || error instanceof JSONDecodeError || name === "UnicodeDecodeError") {
      return null;
    }
    throw error;
  }
  const payload = isDict(record) && dictGet(record, "type") === "session_meta" ? dictGet(record, "payload") : null;
  return isDict(payload) ? payload : null;
}

/**
 * The bytes of the file's first line (universal newlines: `\n`, `\r` or `\r\n` ends it), the
 * terminator left off; the whole file when it has none.
 * @param {string} path
 * @returns {Buffer}
 */
function _firstLine(path) {
  const descriptor = fs.openSync(path, "r");
  try {
    /** @type {Buffer[]} */
    const chunks = [];
    const block = Buffer.allocUnsafe(_FIRST_LINE_CHUNK);
    for (;;) {
      const count = fs.readSync(descriptor, block, 0, block.length, null);
      if (count === 0) {
        break;
      }
      const chunk = Buffer.from(block.subarray(0, count));
      const newline = chunk.findIndex((byte) => byte === 0x0a || byte === 0x0d);
      if (newline >= 0) {
        chunks.push(chunk.subarray(0, newline));
        break;
      }
      chunks.push(chunk);
    }
    return Buffer.concat(chunks);
  } finally {
    fs.closeSync(descriptor);
  }
}

/**
 * Every `*.jsonl` name under `base`, directories not followed through links, unreadable
 * directories skipped: the walk behind `Path.rglob("*.jsonl")`.
 * @param {string} base
 * @returns {string[]}
 */
function _walkJsonl(base) {
  /** @type {string[]} */
  const found = [];
  /** @type {string[]} */
  const pending = [base];
  while (pending.length > 0) {
    const directory = /** @type {string} */ (pending.pop());
    /** @type {fs.Dirent[]} */
    let entries;
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const path = pyPath(directory, entry.name);
      if (entry.name.endsWith(".jsonl")) {
        found.push(path);
      }
      if (entry.isDirectory()) {
        pending.push(path);
      }
    }
  }
  return found;
}

/**
 * The Codex sessions of this project modified after `since`, oldest first; `[]` when Codex left none.
 *
 * A rollout counts when its recorded `cwd` resolves to the project root or inside it. A subagent rollout
 * (`source` is an object, M8) belongs to its parent session and is left out. An absent `sessions`
 * directory and an unreadable or unrecognised file are skipped silently.
 * @param {string} projectRoot
 * @param {string | null} [codexHome] default: `~/.codex`
 * @param {Date | null} [since]
 * @returns {SessionFile[]}
 */
export function codexSessions(projectRoot, codexHome = null, since = null) {
  const home = codexHome || pyPath(os.homedir(), ".codex");
  const base = pyPath(home, "sessions");
  if (!isDir(base)) {
    return [];
  }
  const root = resolvePath(projectRoot);
  /** @type {SessionFile[]} */
  const found = [];
  for (const path of _walkJsonl(base)) {
    const item = _codexSession(path, root, since);
    if (item !== null) {
      found.push(item);
    }
  }
  return found.sort(bySessionOrder);
}

/**
 * `path` as a Codex session of the project at `root` modified after `since`, or null.
 * @param {string} path
 * @param {string} root the resolved project root
 * @param {Date | null} since
 * @returns {SessionFile | null}
 */
function _codexSession(path, root, since) {
  if (!isFile(path)) {
    return null;
  }
  const item = _modifiedAfter(path, since, CODEX, "");
  const meta = item === null ? null : _codexMeta(path);
  if (item === null || meta === null || isDict(dictGet(meta, "source"))) {
    return null;
  }
  const recorded = dictGet(meta, "cwd");
  const sessionId = dictGet(meta, "id");
  if (!_isText(recorded) || !_isText(sessionId)) {
    return null;
  }
  return _isInside(_resolveRecorded(recorded), root)
    ? new SessionFile(CODEX, sessionId, item.size, path, item.modifiedMicros)
    : null;
}

/**
 * Whether `value` is a non-empty string.
 * @param {unknown} value
 * @returns {value is string}
 */
function _isText(value) {
  return typeof value === "string" && value !== "";
}

/**
 * `resolve_path(Path(recorded))`: a `cwd` holding NUL is refused as `Path.resolve()` refuses it.
 * @param {string} recorded
 * @returns {string}
 */
function _resolveRecorded(recorded) {
  if (recorded.includes("\0")) {
    throw pyError("ValueError", "embedded null byte");
  }
  return resolvePath(pyPath(recorded));
}
