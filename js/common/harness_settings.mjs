/**
 * Harness settings files whose `env` an agent never writes — the JavaScript twin of
 * `common/harness_settings.py` (ADR 0031/D07, D-C203-ACTOR-WRITE; ADR 0020 D01). The Python module
 * is the spec: the same files, the same comparison, the same texts.
 *
 * A harness settings file's `env` block reaches the hook process (M239), so an agent that could
 * write it could set the actor of the next session. The guard (policy `privilege.no-escalation`,
 * every actor) denies that write on two routes, and this module owns what they both need:
 *
 * - **the files** — `.claude/settings*.json` and `.codex/config.toml`, matched on the last two
 *   segments of a path, so the project's file at any depth and the user's are one rule;
 * - **the edit route** (Claude's `Edit`/`Write`/`MultiEdit`): {@link editReason} computes the file's
 *   content after the edit and answers a reason when the parsed `env` of a JSON file differs from
 *   the current one — a Codex `config.toml` when any `env` or `shell_environment_policy` text
 *   changes; an edit that leaves `env` identical passes;
 * - **the shell route**: {@link writeReason} is the text for a command the guard found writing one
 *   of the files (the command-word parsing lives in `hooks/hook_core.mjs`).
 *
 * The data (`common/harness_settings.json`) is read at the entry point and passed down; the hook
 * bundle hands it over as `data.harnessSettings`. Nothing here reads the environment or a file.
 */

import { fill } from "./jsondata.mjs";
import { JSONDecodeError, jsonLoads } from "./pyjson.mjs";
import { pySplitlines } from "./pyvalue.mjs";

/**
 * The shape of `common/harness_settings.json`.
 * @typedef {object} HarnessSettingsData
 * @property {Array<{directory: string, pattern: string, format: string}>} files
 * @property {string[]} toml_env_names
 * @property {{write_all_operands: string[], in_place: Record<string, string>, in_place_long_option: string, write_last_operand: string[], target_directory_options: string[], operand_assignments: Record<string, string>}} shell
 * @property {{edit: string, bash: string}} texts
 */

const _TOML_HEADER = /^\[\[?\s*(.+?)\s*\]\]?\s*(?:#.*)?$/;
const _TOML_KEY = /^([A-Za-z0-9_.\-"' ]+?)\s*=/;

/**
 * The regular expression of a file-name pattern: `*` is any run of characters, the rest is literal.
 * @param {string} pattern
 * @returns {RegExp}
 */
function _glob(pattern) {
  const escaped = pattern.split("*").map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`^(?:${escaped.join(".*")})$`, "s");
}

/**
 * `json` or `toml` when `path` names a harness settings file, else `null`. Only the last two
 * segments count (`.claude/settings.local.json`): the directory a project sits in, or the home
 * directory, does not.
 * @param {string} path
 * @param {HarnessSettingsData} data
 * @returns {string | null}
 */
export function fileFormat(path, data) {
  const parts = path.split("/").filter((part) => part !== "" && part !== ".");
  if (parts.length < 2) {
    return null;
  }
  const directory = parts[parts.length - 2];
  const name = parts[parts.length - 1];
  for (const entry of data.files) {
    if (directory === entry.directory && _glob(entry.pattern).test(name)) {
      return entry.format;
    }
  }
  return null;
}

/**
 * The reason for a shell command that writes the harness settings file `path`.
 * @param {string} path
 * @param {HarnessSettingsData} data
 * @returns {string}
 */
export function writeReason(path, data) {
  return fill(data.texts.bash, { path });
}

/**
 * Whether two parsed JSON values are the same: by type (`true` is not `1`) and, for numbers, by value.
 * @param {any} first
 * @param {any} second
 * @returns {boolean}
 */
function _same(first, second) {
  if (Array.isArray(first) || Array.isArray(second)) {
    return _sameList(first, second);
  }
  if (_isObject(first) && _isObject(second)) {
    const keys = Object.keys(first);
    return (
      keys.length === Object.keys(second).length &&
      keys.every((key) => Object.hasOwn(second, key) && _same(first[key], second[key]))
    );
  }
  return first === second;
}

/**
 * @param {any} first
 * @param {any} second
 * @returns {boolean}
 */
function _sameList(first, second) {
  return (
    Array.isArray(first) &&
    Array.isArray(second) &&
    first.length === second.length &&
    first.every((/** @type {any} */ item, /** @type {number} */ index) => _same(item, second[index]))
  );
}

/**
 * @param {any} value
 * @returns {boolean}
 */
function _isObject(value) {
  return value !== null && typeof value === "object";
}

/**
 * The `env` of a JSON settings file's text; `{}` for no file, no `env`, an empty one or no object.
 * A file that does not parse delivers no `env` to anything, so it holds none.
 * @param {string | null} text
 * @returns {any}
 */
export function jsonEnv(text) {
  if (text === null) {
    return {};
  }
  /** @type {any} */
  let document;
  try {
    document = jsonLoads(text);
  } catch (error) {
    // `json.JSONDecodeError` and the over-long integer are `ValueError`s; `RecursionError` is not
    if (error instanceof JSONDecodeError || /** @type {Error} */ (error).name === "ValueError") {
      return {};
    }
    throw error;
  }
  const env = document !== null && typeof document === "object" && !Array.isArray(document) ? document.env : undefined;
  return _truthy(env) ? env : {};
}

/**
 * Python's truthiness of a parsed JSON value.
 * @param {any} value
 * @returns {boolean}
 */
function _truthy(value) {
  if (value === undefined || value === null || value === false || value === 0 || value === "") {
    return false;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value).length > 0;
  }
  return true;
}

/**
 * @param {string} key
 * @returns {string[]}
 */
function _keySegments(key) {
  return key.split(".").map((segment) => segment.trim().replace(/^["']+|["']+$/g, ""));
}

/**
 * The lines of a Codex `config.toml` text that belong to an `env` or `shell_environment_policy` table.
 *
 * A table whose dotted name has a segment in `names` (`[env]`, `[mcp_servers.x.env]`,
 * `[shell_environment_policy.set]`), and a key at any level whose first segment is one
 * (`env = { ... }`, `shell_environment_policy.inherit = "none"`), with the lines that continue a
 * value. Blank lines and comment-only lines are not text that changes anything, and are left out.
 * @param {string | null} text
 * @param {readonly string[]} names
 * @returns {string[]}
 */
export function tomlEnvLines(text, names) {
  /** @type {string[]} */
  const kept = [];
  let inTable = false;
  let belongs = false;
  for (const raw of pySplitlines(text ?? "")) {
    const line = raw.trim();
    if (line === "" || line.startsWith("#")) {
      continue;
    }
    const header = _TOML_HEADER.exec(line);
    const key = header === null ? _TOML_KEY.exec(line) : null;
    if (header !== null) {
      inTable = _keySegments(header[1]).some((segment) => names.includes(segment));
      belongs = inTable;
    } else if (key !== null) {
      belongs = inTable || names.includes(_keySegments(key[1])[0]);
    }
    if (belongs) {
      kept.push(line);
    }
  }
  return kept;
}

/**
 * Whether the `env` of a settings file of `fileKind` (`json` or `toml`) differs between two texts.
 * @param {string} fileKind
 * @param {string | null} before
 * @param {string | null} after
 * @param {HarnessSettingsData} data
 * @returns {boolean}
 */
export function envChanged(fileKind, before, after, data) {
  if (fileKind === "toml") {
    const names = data.toml_env_names;
    return tomlEnvLines(before, names).join("\n") !== tomlEnvLines(after, names).join("\n");
  }
  return !_same(jsonEnv(before), jsonEnv(after));
}

/**
 * `text` after one `old_string`/`new_string` edit, or `null` when the edit cannot apply.
 * @param {string} text
 * @param {any} edit
 * @returns {string | null}
 */
function _applyEdit(text, edit) {
  if (edit === null || typeof edit !== "object" || Array.isArray(edit)) {
    return null;
  }
  const old = edit.old_string;
  const replacement = edit.new_string;
  if (typeof old !== "string" || typeof replacement !== "string") {
    return null;
  }
  if (old === "") {
    // only a file that has no text yet is written by an edit with nothing to replace
    return text === "" ? replacement : null;
  }
  const at = text.indexOf(old);
  if (at < 0) {
    return null;
  }
  if (edit.replace_all === true) {
    return text.split(old).join(replacement);
  }
  return text.slice(0, at) + replacement + text.slice(at + old.length);
}

/**
 * The file's text after the edit `toolInput` asks for, or `null` when the edit cannot apply.
 *
 * `Write` carries `content`; `MultiEdit` an ordered list `edits`; `Edit` one `old_string` and
 * `new_string` (every occurrence with `replace_all`, else the first). An edit whose `old_string` is
 * not in the text (or is empty and the text is not) fails in the harness, so it changes nothing here.
 * @param {Record<string, any>} toolInput
 * @param {string | null} current
 * @returns {string | null}
 */
export function editedText(toolInput, current) {
  if (Object.hasOwn(toolInput, "content")) {
    return typeof toolInput.content === "string" ? toolInput.content : null;
  }
  const edits = Object.hasOwn(toolInput, "edits") ? toolInput.edits : [toolInput];
  if (!Array.isArray(edits)) {
    return null;
  }
  /** @type {string | null} */
  let text = current ?? "";
  for (const edit of edits) {
    text = _applyEdit(text, edit);
    if (text === null) {
      return null;
    }
  }
  return text;
}

/**
 * The reason to deny an `Edit`/`Write`/`MultiEdit` of a harness settings file's `env`, else `null`.
 *
 * `readCurrent` answers a path's present text, `null` when there is no file: the entry point reads
 * the file, this function reads nothing. A file that is not a harness settings file, an edit that
 * cannot apply and an edit that leaves `env` identical all pass.
 * @param {Record<string, any>} toolInput
 * @param {(path: string) => string | null} readCurrent
 * @param {HarnessSettingsData} data
 * @returns {string | null}
 */
export function editReason(toolInput, readCurrent, data) {
  const path = toolInput.file_path;
  const fileKind = typeof path === "string" ? fileFormat(path, data) : null;
  if (fileKind === null) {
    return null;
  }
  const current = readCurrent(path);
  const after = editedText(toolInput, current);
  if (after === null || !envChanged(fileKind, current, after, data)) {
    return null;
  }
  return fill(data.texts.edit, { path });
}
