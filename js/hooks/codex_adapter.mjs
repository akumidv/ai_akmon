/**
 * Codex adapter helpers for neutral akmon hook results — the JavaScript twin of
 * `hooks/codex_adapter.py` (C104, ADR 0020 D01). The Python module is the spec: the same
 * answers, the same texts, byte for byte, the same stdout and stderr.
 *
 * Codex command-hook payload details may evolve, so this adapter accepts several common field
 * spellings and degrades to plain-text reminders. Hard decisions are wired only after the exact
 * route, payload, and runtime behavior are live-verified for the target version.
 *
 * Data (the C102 convention): this module never reads a data file itself. The functions that
 * read `hooks/vocabulary.json`, `hooks/codex_hook.json` or a marker take the lazily-read bundle
 * `data` (`hook_data.mjs`) as their first parameter; `isApplyPatchCommand`, `loadPayload` and
 * `reportFailure` read none and take none.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - the patch patterns are `re.ASCII` on the Python side and spelled with explicit ASCII classes
 *   here (`\s` is `[ \t\n\r\f\v]`); the Python `re.MULTILINE` anchors and `.` see only `\n`, while
 *   a JavaScript `m`-flag `^`/`$` also see `\r`, U+2028 and U+2029, so the line anchors are
 *   lookarounds on `\n` and `.` is `[^\n]` — a CRLF patch body keeps its `\r` in the captured
 *   path until `strip()` takes it, as in Python;
 * - `pattern.match(text, pos)` is a sticky regex; `finditer` is `matchAll`;
 * - `sys.stdin.read()` is a strict UTF-8 decode of every byte (a malformed one raises
 *   `UnicodeDecodeError`, which `json.loads` is never reached for) with no newline translation
 *   (POSIX: `\r\n` stays). Not reproduced: Python under the C locale reads stdin with
 *   `surrogateescape`; a closed descriptor 0 is `sys.stdin is None` (`AttributeError`) there, while
 *   node reopens it on `/dev/null` before any script runs, so it reads as an empty payload here;
 * - `json.loads` is `jsonLoads` of `common/pyjson.mjs`, as `sys.stdin.read()` is its
 *   `readStdinText`: `NaN`, `Infinity`, the 4300-digit limit and the recursion limit are
 *   explained in its header;
 * - `sorted(str)` orders by code point (`codePointSort`), `strip()` cuts Python's whitespace set
 *   (`pyStrip`), and a lone surrogate written to stderr is `\udXXX` (`backslashreplace`), not U+FFFD.
 */

import { fill } from "../common/jsondata.mjs";
import { hookForm } from "../common/json_writer.mjs";
import { unidentifiedIdentity } from "../common/markers.mjs";
import { JSONDecodeError, jsonLoads, readStdinText } from "../common/pyjson.mjs";
import { dictGet, dictItem, isDict, pyIterate, pyStrip, truthy } from "../common/pyvalue.mjs";
import { codePointSort } from "../common/sort.mjs";
import { editTool, hookFailureDiagnostic, shellTool } from "./hook_core.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */
/** @typedef {import("./hook_core.mjs").HookResult} HookResult */
/** A hook payload: whatever JSON object the harness sent (or the `raw`/`payload` off-shapes). */
/** @typedef {Record<string, any>} Payload */

// --------------------------------------------------------------------------------------
// The patch patterns
// --------------------------------------------------------------------------------------

// All four measured patch forms, one owner. A rename is spelled `*** Update File: <source>`
// followed by `*** Move to: <destination>`, so the destination has its own literal and is
// invisible to a pattern that reads the `File:` lines alone (C67). Kept as one alternation
// because these lines are the single measured source of patch paths, and a second extractor is a
// second place for the next form to be missing from. `^` is the start of a line, `(.+)$` the rest
// of it — both on `\n` only, as Python's `re.MULTILINE` sees them.
const _PATCH_PATH_SOURCE = String.raw`(?<![^\n])\*\*\* (?:(?:Add|Update|Delete) File|Move to): ([^\n]+)(?![^\n])`;
const _PATCH_PATH_RE = new RegExp(_PATCH_PATH_SOURCE, "g");
const _PATCH_PATH_PRESENT_RE = new RegExp(_PATCH_PATH_SOURCE);

// A deliberately narrow recognition rule for the one shell effect we can classify exactly: an
// apply_patch invocation in *command position* (the string start, after a `;`/`&&`/`||`/`|`
// separator, a subshell `(`, a group `{ `, or a `sh -c` / `bash -lc` wrapper's script), with the
// patch body carried inline. See the Python module for the reasoning; the width is safe to spend
// because `_hasApplyPatchInvocation` also requires the first line, no shell quoting and a
// directly opened patch heredoc.
const _APPLY_PATCH_INVOCATION_RE =
  /(?:^|[;&|(]|\{(?=[ \t\n\r\f\v])|-\w*c[ \t\n\r\f\v]*["'])[ \t\n\r\f\v]*(?:command[ \t\n\r\f\v]+)?(?:[^ \t\n\r\f\v]*\/)?apply_patch(?=[ \t\n\r\f\v<]|$)/g;
// `pattern.match(text, pos)`: sticky, so it matches at `lastIndex` and nowhere else.
const _PATCH_HEREDOC_RE = /[ \t]*<<-?[ \t]*(?<quote>['"]?)(?<delimiter>[A-Za-z_][A-Za-z0-9_]*)\k<quote>[ \t]*\r?\n/y;
const _ENVELOPE_SOURCE = String.raw`(?<![^\n])\*\*\* Begin Patch[ \t\n\r\f\v]*(?![^\n])`;
const _PATCH_ENVELOPE_RE = new RegExp(_ENVELOPE_SOURCE);
const _PATCH_ENVELOPE_AT_RE = new RegExp(_ENVELOPE_SOURCE, "y");
const _PATCH_END_RE = /(?<![^\n])\*\*\* End Patch[ \t\n\r\f\v]*(?![^\n])/;

/**
 * The match of the sticky `pattern` at exactly `position`, else null (`pattern.match(text, pos)`).
 * @param {RegExp} pattern
 * @param {string} text
 * @param {number} position
 * @returns {RegExpExecArray | null}
 */
function _matchAt(pattern, text, position) {
  pattern.lastIndex = position;
  return pattern.exec(text);
}

/**
 * Whether `position` starts outside simple shell single/double quoting.
 * @param {string} text
 * @param {number} position
 * @returns {boolean}
 */
function _outsideShellQuotes(text, position) {
  let quote = "";
  let escaped = false;
  for (const char of text.slice(0, position)) {
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === "\\" && quote !== "'") {
      escaped = true;
      continue;
    }
    if (quote) {
      if (char === quote) {
        quote = "";
      }
    } else if (char === "'" || char === '"') {
      quote = char;
    }
  }
  return !quote;
}

/**
 * Find an invocation that directly opens the inline patch heredoc.
 * @param {string} commandText
 * @returns {boolean}
 */
function _hasApplyPatchInvocation(commandText) {
  const firstNewline = commandText.indexOf("\n");
  const lineEnd = firstNewline < 0 ? commandText.length : firstNewline;
  for (const match of commandText.matchAll(_APPLY_PATCH_INVOCATION_RE)) {
    const start = match.index ?? 0; // `?? 0` only feeds the checker: a match always has an index
    if (start >= lineEnd || !_outsideShellQuotes(commandText, start)) {
      continue;
    }
    const opener = _matchAt(_PATCH_HEREDOC_RE, commandText, start + match[0].length);
    if (opener !== null && _matchAt(_PATCH_ENVELOPE_AT_RE, commandText, opener.index + opener[0].length) !== null) {
      return true;
    }
  }
  return false;
}

/**
 * Whether Bash carries the one effect akmon can path-classify conservatively.
 *
 * Require a command-position `apply_patch` invocation and a complete inline envelope;
 * patch-looking text that is merely printed, searched, stored, or truncated stays shell.
 * @param {string} commandText
 * @returns {boolean}
 */
export function isApplyPatchCommand(commandText) {
  return (
    _hasApplyPatchInvocation(commandText) &&
    _PATCH_ENVELOPE_RE.test(commandText) &&
    _PATCH_END_RE.test(commandText) &&
    _PATCH_PATH_PRESENT_RE.test(commandText)
  );
}

// --------------------------------------------------------------------------------------
// The data tables
// --------------------------------------------------------------------------------------

/** `_vocabulary()["codex"]` — a missing key is the `KeyError` Python raises. */
function _vocabularyCodex(/** @type {HookData} */ data) {
  return dictItem(data.vocabulary, "codex");
}

/**
 * One measured field's key spellings in priority order (hooks/vocabulary.json, C102).
 * @param {HookData} data
 * @param {string} stem
 * @returns {string[]}
 */
function _payloadKeySpellings(data, stem) {
  return pyIterate(dictItem(dictItem(_vocabularyCodex(data), "payload_key_spellings"), stem));
}

/** Codex's file-editing tool name(s) (hooks/vocabulary.json, C102). */
function _editTools(/** @type {HookData} */ data) {
  return new Set(pyIterate(dictItem(_vocabularyCodex(data), "edit_tools")));
}

/**
 * The shell route (hooks/vocabulary.json, C102).
 *
 * `Bash` is the `tool_name` codex 0.146.0 puts in the payload for a shell call — measured, not
 * assumed: its model-facing names (`exec_command`, `shell`) appear neither as payload tool names
 * nor as working matchers (C49).
 */
function _shellTools(/** @type {HookData} */ data) {
  return new Set(pyIterate(dictItem(_vocabularyCodex(data), "shell_tools")));
}

/** The hook document-shape key table (hooks/vocabulary.json, C102). */
function _documentKeys(/** @type {HookData} */ data) {
  return dictItem(data.vocabulary, "document_keys");
}

/**
 * Map a Codex tool name to the neutral kind hook_core expects; pass others through.
 * @param {HookData} data
 * @param {string} name
 * @returns {string}
 */
export function normalizeTool(data, name) {
  if (_editTools(data).has(name)) {
    return editTool(data);
  }
  return _shellTools(data).has(name) ? shellTool(data) : name;
}

/**
 * The neutral kind this call *acts as*, which is not always the route it took.
 *
 * A shell call whose command carries a patch body is an edit. Codex's model demonstrated exactly
 * this in the N2 deny probe: a denied `apply_patch` was re-issued through the shell in the same
 * turn, unprompted, and went through. Classifying by route would let one effect be seen or unseen
 * depending on its spelling, so the payload decides (C49).
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
export function toolKind(data, payload) {
  const name = normalizeTool(data, toolName(data, payload) || "apply_patch");
  if (name === shellTool(data) && isApplyPatchCommand(command(data, payload))) {
    return editTool(data);
  }
  return name;
}

// --------------------------------------------------------------------------------------
// The payload
// --------------------------------------------------------------------------------------

/**
 * Parse the hook payload from stdin; `{"raw": ...}`/`{"payload": ...}` on the off-shapes.
 * @returns {Payload}
 */
export function loadPayload() {
  const raw = readStdinText();
  if (!pyStrip(raw)) {
    return {};
  }
  let value;
  try {
    value = jsonLoads(raw);
  } catch (error) {
    if (error instanceof JSONDecodeError) {
      return { raw };
    }
    throw error;
  }
  return isDict(value) ? value : { payload: value };
}

/**
 * The payload's tool name, tried across every measured field spelling; `""` if none match.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
export function toolName(data, payload) {
  for (const key of _payloadKeySpellings(data, "tool_name")) {
    const value = dictGet(payload, key);
    if (typeof value === "string") {
      return value;
    }
    if (isDict(value) && typeof dictGet(value, "name") === "string") {
      return dictGet(value, "name");
    }
  }
  return "";
}

/**
 * The payload's session identity, tried across every measured field spelling; `"nosession"` if
 * none match.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
export function sessionId(data, payload) {
  for (const key of _payloadKeySpellings(data, "session_id")) {
    const value = dictGet(payload, key);
    if (typeof value === "string" && value !== "") {
      return value;
    }
  }
  return unidentifiedIdentity(data.markers);
}

/**
 * Return the per-event identity Codex supplies, or an empty string if absent.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
export function toolUseId(data, payload) {
  for (const key of _payloadKeySpellings(data, "tool_use_id")) {
    const value = dictGet(payload, key);
    if (typeof value === "string" && value !== "") {
      return value;
    }
  }
  return "";
}

/**
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {Payload}
 */
function _toolInput(data, payload) {
  for (const key of _payloadKeySpellings(data, "tool_input")) {
    const value = dictGet(payload, key);
    if (isDict(value)) {
      return value;
    }
  }
  return {};
}

/**
 * The shell command or patch body, tried across every measured field spelling; `""` if none match.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
export function command(data, payload) {
  const toolInput = _toolInput(data, payload);
  for (const key of _payloadKeySpellings(data, "command")) {
    // `tool_input.get(key) or payload.get(key)`: the first only when it is truthy, so an empty
    // string (or any other falsy value) in `tool_input` falls through to the payload's own.
    const inner = dictGet(toolInput, key);
    const value = truthy(inner) ? inner : dictGet(payload, key);
    if (typeof value === "string") {
      return value;
    }
  }
  return "";
}

/**
 * `(unmeasured, measured)` — paths read from guessed keys, and from the patch body.
 *
 * Kept apart so a caller can say *how* it learned a path. No measured Codex version sends any of
 * the guessed keys; they are tolerated in case a future shape uses one, but a path that only they
 * produced is a claim no measurement backs (ADR-0012/D01). Ranking them below the patch body is
 * not enough on its own — a speculative key that matches something *other* than an edited file
 * would classify it silently, which is worse than the empty list C48 started from, so the wrapper
 * reports the provenance instead of trusting it.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {[string[], string[]]}
 */
function _pathsBySource(data, payload) {
  /** @type {string[]} */
  const unmeasured = [];
  for (const source of [_toolInput(data, payload), payload]) {
    for (const key of _payloadKeySpellings(data, "unmeasured_string_keys")) {
      const value = dictGet(source, key);
      if (typeof value === "string" && value !== "") {
        unmeasured.push(value);
      }
    }
    for (const key of _payloadKeySpellings(data, "unmeasured_list_keys")) {
      const value = dictGet(source, key);
      if (Array.isArray(value)) {
        unmeasured.push(...value.filter((item) => typeof item === "string" && item !== ""));
      }
    }
  }
  const body = command(data, payload);
  const patch = body !== "" ? body : dictGet(payload, "raw");
  const measured =
    typeof patch === "string" ? [...patch.matchAll(_PATCH_PATH_RE)].map((match) => pyStrip(match[1])) : [];
  return [unmeasured, measured];
}

/**
 * True when the payload named files, but only through keys no measured Codex sends.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {boolean}
 */
export function unmeasuredPathSource(data, payload) {
  const [unmeasured, measured] = _pathsBySource(data, payload);
  return unmeasured.length > 0 && measured.length === 0;
}

/**
 * Every file path the payload names, including those parsed out of a patch body.
 *
 * A rename names two: the source on its `*** Update File:` line and the destination on the
 * `*** Move to:` line that follows it, both returned in patch order (C67). The advisories run
 * over the whole list, so a move *into* a sensitive path is now seen from the destination even
 * though the source is ordinary.
 *
 * The patch body is read through {@link command} because on `apply_patch` it *is* the command:
 * codex 0.146.0 sends the whole patch as `tool_input.command` (captured live). `raw` stays — it
 * is this module's own malformed-JSON fallback (see {@link loadPayload}), not a guess.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string[]}
 */
export function filePaths(data, payload) {
  const [unmeasured, measured] = _pathsBySource(data, payload);
  // Stable de-duplication.
  const seen = new Set();
  /** @type {string[]} */
  const unique = [];
  for (const path of [...unmeasured, ...measured]) {
    const normalized = path.replaceAll("\\", "/");
    if (!seen.has(normalized)) {
      seen.add(normalized);
      unique.push(path);
    }
  }
  return unique;
}

/**
 * The payload's key names, for a diagnostic that must not print the payload itself.
 *
 * Used when a matcher fired but no path could be read (C48): the useful evidence is *which keys
 * arrived*, and the values may carry file contents from a patch body.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
export function payloadShape(data, payload) {
  const top = codePointSort(Object.keys(payload)).join(", ") || "<none>";
  const inner = codePointSort(Object.keys(_toolInput(data, payload))).join(", ") || "<none>";
  return fill(dictItem(data.codex, "payload_shape"), { inner, top });
}

/**
 * The payload's working directory, tried across every measured field spelling; `""` if none match.
 * @param {HookData} data
 * @param {Payload} payload
 * @returns {string}
 */
export function cwd(data, payload) {
  for (const key of _payloadKeySpellings(data, "cwd")) {
    const value = dictGet(payload, key);
    if (typeof value === "string" && value !== "") {
      return value;
    }
  }
  return "";
}

// --------------------------------------------------------------------------------------
// Output
// --------------------------------------------------------------------------------------

/**
 * Print the rendered `result` document, or nothing when there is none.
 * @param {HookData} data
 * @param {HookResult | null} result
 * @returns {void}
 */
export function printResult(data, result) {
  if (result === null) {
    return;
  }
  const keys = _documentKeys(data);
  /** @type {Map<string, string>} */
  const output = new Map([[dictItem(keys, "event_name"), result.eventName]]);
  if (result.additionalContext !== null) {
    output.set(dictItem(keys, "additional_context"), result.additionalContext);
  }
  if (result.permissionDecision !== null) {
    output.set(dictItem(keys, "permission_decision"), result.permissionDecision);
  }
  if (result.permissionReason !== null) {
    output.set(dictItem(keys, "permission_reason"), result.permissionReason);
  }
  const topLevel = new Map([[dictItem(keys, "hook_specific_output"), output]]);
  // `result.systemMessage` is dropped: Codex hooks have no documented user-facing channel.
  process.stdout.write(`${hookForm(topLevel)}\n`);
}

/**
 * `print(text, file=sys.stderr)`: stderr's error handler is `backslashreplace`, so a lone
 * surrogate (a payload string can hold one) reads `\udXXX` where Node would write U+FFFD.
 * @param {string} text
 * @returns {void}
 */
export function writeStderr(text) {
  const escaped = text.replace(
    /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g,
    (unit) => `\\u${unit.charCodeAt(0).toString(16)}`,
  );
  process.stderr.write(`${escaped}\n`);
}

/**
 * The crash half of the Codex entry point (ADR-0013/D01): exit 1.
 *
 * One stderr line naming the route and the exception class — never its message — and nothing on
 * stdout. Codex has no measured text channel to the owner, but it does show each hook's outcome: a
 * hook that exits 1 on `SessionStart`, on `PreToolUse` (shell and patch routes) or on
 * `UserPromptSubmit` is reported `Failed` while the action goes ahead (M68, M71). An exit 0 would
 * read `Completed` and hide the crash, so the exit code is the channel here.
 * @param {string} hookName
 * @param {unknown} exc
 * @returns {number}
 */
export function reportFailure(hookName, exc) {
  writeStderr(hookFailureDiagnostic(hookName, exc));
  return 1;
}
