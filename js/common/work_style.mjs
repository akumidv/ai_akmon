/**
 * The work style in force — the JavaScript twin of `common/work_style.py` (ADR 0031/D03; ADR 0020
 * D01). The Python module is the spec: the same answers, the same texts, the same session store
 * byte for byte.
 *
 * A work style says how a `developer` run splits the work with the developer: `delegating` (the
 * default) or `controlling` (ADR 0031/D02). It never widens a permission (D01). The first of these
 * that holds a valid value decides:
 *
 * 1. **session** — the owner typed `/style delegating` or `/style controlling`; the
 *    `UserPromptSubmit` hook {@link recordAndReply} records it for that `session_id` in
 *    `<dev root>/.local/work-sessions.json` (the most recent `sessions_keep` entries stay);
 * 2. **developer** — `<dev root>/.local/work.json`, key `style`, untracked;
 * 3. **project** — `[work] style` in `<dev root>/.akmon.toml`, through the lenient record reader;
 * 4. **default** — `delegating`.
 *
 * A value that is not a style is skipped at its level and the next level decides. Every reader
 * here is lenient (a missing or unreadable file is no value); the one write, the session store, is
 * atomic (a temp file in the same directory, then a rename).
 *
 * Everything that reads the world — the payload, the data file — is read at the entry point and
 * passed down; the hook bundle (`hooks/hook_data.mjs`) hands the data file over as
 * `data.workStyle`.
 *
 * Twin notes:
 * - the session store is read into an object, so an integer-like session id (`"7"`) sorts before
 *   the others when the order of the entries is read back; a real session id is a UUID, and the
 *   Python keeps recorded order for every key;
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
import { decodeUtf8, dictGet, dictItem, isDict, isOSError, pyLower, pyLstrip, pyPath, pyStrip } from "./pyvalue.mjs";

/**
 * The shape of `common/work_style.json`.
 * @typedef {object} WorkStyleData
 * @property {string[]} styles the allowed values
 * @property {string} default the style when no level holds a valid one
 * @property {string} developer_rel the developer's setting, relative to `<dev root>`
 * @property {string} sessions_rel the per-session store, relative to `<dev root>`
 * @property {number} sessions_keep how many recent sessions the store keeps
 * @property {string} record_section the `.akmon.toml` section holding the project's style
 * @property {string} record_key the key of that section
 * @property {string} command the prompt word that sets a style
 * @property {string} recorded the reply to a recorded style
 * @property {string} invalid the reply to a value that names no style
 * @property {string} no_session the reply when the payload carried no session id
 */

/** @typedef {"session" | "developer" | "project" | "default"} StyleSource */

/** The style in force and the level that decided it. */
export class WorkStyle {
  /**
   * @param {string} style
   * @param {StyleSource} source
   */
  constructor(style, source) {
    this.style = style;
    this.source = source;
    Object.freeze(this);
  }
}

/**
 * The work-style data file beside this module: the styles, the file locations, the hook texts.
 * @returns {WorkStyleData}
 */
export function readData() {
  return /** @type {WorkStyleData} */ (read(fileURLToPath(new URL("../../common/work_style.json", import.meta.url))));
}

/**
 * Where the developer's own setting lives: under the local layer of `<dev root>` (ADR 0022).
 * @param {string} projectRoot
 * @param {WorkStyleData} data
 * @returns {string}
 */
export function developerPath(projectRoot, data) {
  return pyPath(aitnaRoot(projectRoot), dictItem(data, "developer_rel"));
}

/**
 * Where the per-session styles live: beside the developer's setting, in the local layer.
 * @param {string} projectRoot
 * @param {WorkStyleData} data
 * @returns {string}
 */
export function sessionsPath(projectRoot, data) {
  return pyPath(aitnaRoot(projectRoot), dictItem(data, "sessions_rel"));
}

/**
 * The JSON object in `path`, or `{}` when it is missing, unreadable or not an object.
 * @param {string} path
 * @returns {Record<string, any>}
 */
function _loadObject(path) {
  /** @type {any} */
  let loaded;
  try {
    loaded = jsonLoads(decodeUtf8(fs.readFileSync(path)));
  } catch (error) {
    const name = /** @type {Error} */ (error).name;
    if (isOSError(error) || error instanceof JSONDecodeError || name === "UnicodeDecodeError") {
      return {};
    }
    throw error;
  }
  return isDict(loaded) ? loaded : {};
}

/**
 * `value` when it is one of the styles, else null (the level is skipped).
 * @param {unknown} value
 * @param {WorkStyleData} data
 * @returns {string | null}
 */
function _valid(value, data) {
  return typeof value === "string" && dictItem(data, "styles").includes(value) ? value : null;
}

/**
 * The recorded per-session styles in recorded order, oldest first; an entry that is not a style is dropped.
 * @param {string} path
 * @param {WorkStyleData} data
 * @returns {Map<string, string>}
 */
export function readSessions(path, data) {
  /** @type {Map<string, string>} */
  const sessions = new Map();
  const table = dictGet(_loadObject(path), "sessions");
  if (!isDict(table)) {
    return sessions;
  }
  for (const [key, value] of Object.entries(table)) {
    const style = _valid(value, data);
    if (key !== "" && style !== null) {
      sessions.set(key, style);
    }
  }
  return sessions;
}

/**
 * The developer's `style`, or null when the file, the key or the value is missing or invalid.
 * @param {string} path
 * @param {WorkStyleData} data
 * @returns {string | null}
 */
export function readDeveloper(path, data) {
  return _valid(dictGet(_loadObject(path), "style"), data);
}

/**
 * The project's `[work] style`, or null when the record, the table, the key or the value is missing or invalid.
 * @param {string} projectRoot
 * @param {WorkStyleData} data
 * @returns {string | null}
 */
export function readProject(projectRoot, data) {
  const table = recordedTable(projectRoot, dictItem(data, "record_section"));
  return _valid(dictGet(table, dictItem(data, "record_key")), data);
}

/**
 * The style in force for `sessionId` and where it came from, first valid level wins (ADR 0031/D03).
 * @param {string} projectRoot
 * @param {string | null} sessionId
 * @param {WorkStyleData} data
 * @returns {WorkStyle}
 */
export function resolve(projectRoot, sessionId, data) {
  if (sessionId) {
    const recorded = readSessions(sessionsPath(projectRoot, data), data).get(sessionId);
    if (recorded !== undefined) {
      return new WorkStyle(recorded, "session");
    }
  }
  const developer = readDeveloper(developerPath(projectRoot, data), data);
  if (developer !== null) {
    return new WorkStyle(developer, "developer");
  }
  const project = readProject(projectRoot, data);
  if (project !== null) {
    return new WorkStyle(project, "project");
  }
  return new WorkStyle(dictItem(data, "default"), "default");
}

/**
 * The text after `/style` when the whole `prompt` is that command, else null.
 *
 * The prompt is trimmed; the command is the first word, so `/styles x` is not it. The text is
 * returned as typed (`""` for a bare `/style`) — whether it names a style is {@link knownStyle}'s.
 * @param {string} prompt
 * @param {WorkStyleData} data
 * @returns {string | null}
 */
export function typedStyle(prompt, data) {
  const command = dictItem(data, "command");
  const text = pyStrip(prompt);
  if (!text.startsWith(command)) {
    return null;
  }
  const rest = text.slice(command.length);
  if (rest !== "" && rest === pyLstrip(rest)) {
    return null;
  }
  return pyStrip(rest);
}

/**
 * The style `typed` names, case-insensitive, or null.
 * @param {string} typed
 * @param {WorkStyleData} data
 * @returns {string | null}
 */
export function knownStyle(typed, data) {
  return _valid(pyLower(typed), data);
}

/**
 * Persist `sessions` at `path` atomically: a temp file in the same directory, then a rename.
 * @param {Map<string, string>} sessions
 * @param {string} path
 * @returns {void}
 */
export function writeSessions(sessions, path) {
  const directory = dirname(path);
  fs.mkdirSync(directory, { recursive: true });
  const temp = pyPath(directory, `.${basename(path)}.${randomBytes(6).toString("hex")}.tmp`);
  try {
    const descriptor = fs.openSync(temp, "wx", 0o600);
    try {
      fs.writeFileSync(descriptor, wiringForm(new Map([["sessions", sessions]])), "utf8");
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
 * Record `style` for `sessionId` as the most recent entry and keep the newest `sessions_keep`.
 *
 * A later write for the same session moves it to the newest place. No lock is taken: two sessions
 * typing `/style` in the same instant can lose one entry, which reads as the next level's style.
 * @param {string} path
 * @param {string} sessionId
 * @param {string} style
 * @param {WorkStyleData} data
 * @returns {void}
 */
export function recordSessionStyle(path, sessionId, style, data) {
  const sessions = readSessions(path, data);
  sessions.delete(sessionId);
  sessions.set(sessionId, style);
  const keep = dictItem(data, "sessions_keep");
  writeSessions(new Map([...sessions].slice(-keep)), path);
}

/**
 * Handle a typed prompt: record a valid `/style` for the session and return the reply, else null.
 *
 * Null means the prompt is not a `/style` command, and nothing is written. A value that names no
 * style, or a payload with no session id, writes nothing and returns the text saying so.
 * @param {string} projectRoot
 * @param {string | null} sessionId
 * @param {string} prompt
 * @param {WorkStyleData} data
 * @returns {string | null}
 */
export function recordAndReply(projectRoot, sessionId, prompt, data) {
  const typed = typedStyle(prompt, data);
  if (typed === null) {
    return null;
  }
  const style = knownStyle(typed, data);
  if (style === null) {
    return fill(dictItem(data, "invalid"), { value: typed, allowed: dictItem(data, "styles").join(", ") });
  }
  if (!sessionId) {
    return fill(dictItem(data, "no_session"), { style, developer_file: dictItem(data, "developer_rel") });
  }
  recordSessionStyle(sessionsPath(projectRoot, data), sessionId, style, data);
  return fill(dictItem(data, "recorded"), { style });
}
