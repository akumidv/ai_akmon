/**
 * Claude Code adapter for neutral akmon hook results — the JavaScript twin of
 * `hooks/claude_adapter.py` (ADR 0020 D01). The Python module is the spec: the same documents,
 * byte for byte, the same stderr line and exit code. It reads the payload off stdin, normalizes
 * Claude's tool names to the neutral kinds `hook_core` expects, renders a `HookResult` as the one
 * JSON document Claude Code reads, and carries the crash guard every spawned entry point runs
 * under.
 *
 * Data (the C102/C104 convention): functions whose Python twin reads `hooks/vocabulary.json` take
 * the bundle of `hook_data.mjs` as their first parameter, `data`. The crash path of `runGuarded`
 * touches no data file.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - `json.load(sys.stdin)` is `readStdinBytes` and `jsonLoads` of `common/pyjson.mjs` (strict
 *   UTF-8, `NaN`/`Infinity`, the 4300-digit limit, the recursion limit — see its header). A text
 *   that is not JSON, a malformed byte sequence (`UnicodeDecodeError`) and an over-long integer
 *   (`ValueError`) are all `ValueError`s in Python, so the payload is `{}`; `RecursionError` is
 *   not one, and crashes;
 * - `Path(cwd).resolve()` of a `cwd` holding NUL raises `ValueError` and one with a lone surrogate
 *   `UnicodeEncodeError`, where Node reports an argument error or a different name — raised as
 *   Python does, before the walk starts.
 */

import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { hookForm } from "../common/json_writer.mjs";
import { JSONDecodeError, jsonLoads, readStdinBytes } from "../common/pyjson.mjs";
import {
  decodeUtf8,
  dictGet,
  dictItem,
  isDict,
  pyPath,
} from "../common/pyvalue.mjs";
import {
  assertEncodablePath,
  editTool,
  findProjectRoot,
  hookFailureDiagnostic,
  hookFailureNotice,
  readTool,
} from "./hook_core.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */
/** @typedef {import("./hook_core.mjs").HookResult} HookResult */
/** A hook payload: whatever JSON object the harness sent. */
/** @typedef {Record<string, any>} Payload */

/**
 * Claude Code's file-editing or read/sweep tool names (hooks/vocabulary.json, C102).
 * @param {HookData} data
 * @param {string} key `edit_tools` or `read_tools`
 * @returns {string[]}
 */
function _claudeTools(data, key) {
  return dictItem(dictItem(data.vocabulary, "claude"), key);
}

/**
 * Map a Claude tool name to the neutral kind hook_core expects; pass others through.
 * @param {HookData} data
 * @param {string} name
 * @returns {string}
 */
export function normalizeTool(data, name) {
  if (_claudeTools(data, "edit_tools").includes(name)) {
    return editTool(data);
  }
  if (_claudeTools(data, "read_tools").includes(name)) {
    return readTool(data);
  }
  return name;
}

// --------------------------------------------------------------------------------------
// The payload
// --------------------------------------------------------------------------------------

/**
 * The payload of a text: a JSON object, else `{}` — any parse failure, a malformed byte sequence
 * (`ValueError` in Python) or a document that is not an object.
 * @param {string | Uint8Array} input the stdin text, or its raw bytes
 * @returns {Payload}
 */
export function parsePayload(input) {
  /** @type {any} */
  let payload;
  try {
    payload = jsonLoads(typeof input === "string" ? input : decodeUtf8(input));
  } catch (error) {
    // `json.JSONDecodeError` and `UnicodeDecodeError` are `ValueError`s; `RecursionError` is not.
    const name = /** @type {Error} */ (error).name;
    if (error instanceof JSONDecodeError || name === "ValueError" || name === "UnicodeDecodeError") {
      return {};
    }
    throw error;
  }
  return isDict(payload) ? payload : {};
}

/**
 * Parse the hook payload from stdin as a JSON object; `{}` on any parse failure.
 * @returns {Payload}
 */
export function loadPayload() {
  return parsePayload(readStdinBytes());
}

/**
 * The project root the payload's paths belong to — from its `cwd`, not the process's.
 *
 * Mirrors `codex-hook`'s `_payload_root`. The path predicates normalize against this root (C47),
 * so it has to describe the session's project rather than wherever the hook process happens to
 * have been started.
 * @param {Payload} payload
 * @returns {string}
 */
export function projectRoot(payload) {
  const cwd = dictGet(payload, "cwd");
  if (typeof cwd === "string" && cwd !== "") {
    assertEncodablePath(cwd); // `Path(cwd).resolve()` refuses a NUL or a lone surrogate
    return findProjectRoot(pyPath(cwd));
  }
  return findProjectRoot(null);
}

// --------------------------------------------------------------------------------------
// The document and the crash guard
// --------------------------------------------------------------------------------------

/**
 * The one JSON document Claude Code reads for `result`, or `null` when there is none.
 * @param {HookData} data
 * @param {HookResult | null} result
 * @returns {string | null}
 */
export function renderResult(data, result) {
  if (result === null) {
    return null;
  }

  /** @type {Record<string, string>} */
  const keys = dictItem(data.vocabulary, "document_keys");
  const key = (/** @type {string} */ name) => dictItem(keys, name);
  /** @type {Map<string, string>} */
  const output = new Map([[key("event_name"), result.eventName]]);
  if (result.additionalContext !== null) {
    output.set(key("additional_context"), result.additionalContext);
  }
  if (result.permissionDecision !== null) {
    output.set(key("permission_decision"), result.permissionDecision);
  }
  if (result.permissionReason !== null) {
    output.set(key("permission_reason"), result.permissionReason);
  }

  /** @type {Map<string, unknown>} */
  const topLevel = new Map([[key("hook_specific_output"), output]]);
  if (result.decision !== null) {
    // Stop's own shape: `decision` and `reason` are read at the top level, not inside
    // `hookSpecificOutput`, and Claude Code refuses a block without a non-empty reason.
    topLevel.set(key("decision"), result.decision);
    topLevel.set(key("reason"), result.reason || "");
  }
  if (result.systemMessage !== null) {
    topLevel.set(key("system_message"), result.systemMessage);
  }

  return hookForm(topLevel);
}

/**
 * Print the rendered `result` document, or nothing when there is none.
 * @param {HookData} data
 * @param {HookResult | null} result
 * @returns {void}
 */
export function printResult(data, result) {
  const document = renderResult(data, result);
  if (document !== null) {
    process.stdout.write(`${document}\n`);
  }
}

/**
 * Run one Claude entry point under the crash guard every spawned entry carries.
 *
 * ADR-0013/D01. `decide` computes the entry's whole result and writes nothing to stdout; the one
 * document is rendered first and written after, so a crash can only land before the write — the
 * single-write property the guard rests on, and the reason a render failure is caught here too.
 * A crash is reported to two readers: one stderr line naming the hook and the exception class,
 * never its message, which routinely carries a path, a key or a payload fragment; and one
 * `systemMessage` for the owner. On 2.1.270 Claude Code shows that message as a notice on
 * `PreToolUse` and `UserPromptSubmit` and never passes it to the model (M69); on `SessionStart`
 * it is recorded with the hook's response, and whether the terminal shows it there is unmeasured.
 * The exit stays 0 — Claude Code shows nothing at all for a hook that exits 1 on `PreToolUse` or
 * `UserPromptSubmit` (M70), so a non-zero exit would only hide the failure. The action goes ahead
 * either way: crash-open, including the deny-class commit guard.
 * @param {string} hookName
 * @param {HookData} data
 * @param {() => HookResult | null} decide
 * @returns {number} the process exit code (always 0)
 */
export function runGuarded(hookName, data, decide) {
  /** @type {string | null} */
  let document;
  try {
    document = renderResult(data, decide());
  } catch (exc) {
    process.stderr.write(`${hookFailureDiagnostic(hookName, exc)}\n`);
    // A literal key, not the vocabulary.json table: the crash path reads no data file, since a
    // missing or broken one may be the very failure it reports (C102 review F1).
    document = hookForm(new Map([["systemMessage", hookFailureNotice(hookName, exc)]]));
  }
  if (document !== null) {
    process.stdout.write(`${document}\n`);
  }
  return 0;
}

/**
 * Whether node was told to execute `moduleUrl` as the entry point. Both sides are dereferenced
 * because npm installs a `bin` entry as a symlink: the path node was given is the link,
 * `import.meta.url` is the target, and the two agree only once resolved. An unresolvable path
 * falls back to the unresolved comparison: the check answers whether to run, it never crashes the
 * thing it is guarding.
 * @param {string} moduleUrl the calling module's `import.meta.url`
 * @returns {boolean}
 */
export function runAsEntryPoint(moduleUrl) {
  const invoked = process.argv[1];
  if (invoked === undefined) {
    return false;
  }
  const self = fileURLToPath(moduleUrl);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}
