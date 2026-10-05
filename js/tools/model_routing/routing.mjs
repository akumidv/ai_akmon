/**
 * Model-routing core: registry loading, tier binding, generated-agent content — the JavaScript
 * twin of `tools/model_routing/routing.py` (ADR 0020 D01). The Python module is the spec: the
 * same answers, the same texts, byte for byte. Vocabulary and policy: MODEL.md § Capability
 * tiers; the registry (`registry.json`) is the single owner of semantic selection policy and
 * task-kind data.
 *
 * Data (the C102/C103 convention): this module never reads a shared data file itself. The
 * caller reads each file once at its entry point (`js/common/jsondata.mjs` `read`) and passes
 * the parsed document down — named `data` when a function needs one file, `<name>Data` when it
 * needs two:
 *
 *   tools/model_routing/agents.json → `data` / `agentsData` (texts, tables, the agent roster)
 *   tools/model_routing/gate.json   → `data` / `gateData`   (gateRules, gateRuleFor and the gate)
 *   common/runtime.json             → `runtimeData`         (secondOpinionCommand, via harnessCommand)
 *   common/markers.json             → `markersData`         (suppressedRebindWarning, gateAuditOnce)
 *
 * `second_opinion.json` is not read here (its reader is `second_opinion.py`). The registry and
 * its project overlay are not shared data but the run's own input: `loadRegistry` reads them,
 * as the Python does, and so do the transcript readers, the local-config reader and the
 * artifact writers — those file operations are this module's contract.
 *
 * Signatures: a Python positional parameter stays positional (camelCase), a keyword-only one
 * moves into a trailing options object (`{markerDir}`, `{turn}`, `{write}`, `{required}`); a
 * dataclass becomes a frozen class whose constructor takes the fields in declaration order; a
 * returned tuple is an array; a `Path` is a string spelled as `str(Path)` spells it.
 *
 * Twin notes — every place the stdlib answers differently from Node's:
 * - JavaScript has one number type, so a float the source spelled whole (`3.0`) would read as
 *   the int `3`. The documents a person may edit — the registry and its overlay (`loadRegistry`)
 *   and the local config (`readLocalConfig`) — are read with the spelling kept: such a number
 *   becomes a `FloatValue` (`js/common/json_writer.mjs`), which every numeric check here honours
 *   as a Python float, as it does for a caller that passes one. A transcript line is plain
 *   `JSON.parse` (a hot path whose token counts are never float-spelled): a whole float there
 *   reads as an int — the documented divergence. An integer beyond 2**53 is not exact here;
 *   Python's `json` also accepts the non-JSON literals `NaN`/`Infinity`, which `JSON.parse`
 *   refuses;
 * - Python truthiness (`[]` and `{}` are false), `str()`/`repr()` of a JSON value, `==` between
 *   numbers and booleans, `in` over a list, a string or a dict, and `.get` on a non-dict (which
 *   raises) are ported as the `_truthy`/`_pyStr`/`_pyRepr`/`_pyEq`/`_contains`/`_get` helpers;
 * - `str.split()`/`strip()` with no argument, `splitlines()`, `len()` and `int(str)` follow the
 *   Python whitespace, line-break, code-point and Unicode-digit rules, never JavaScript's `trim`,
 *   `\s` or UTF-16 length;
 * - the module's patterns are `re.ASCII` on the Python side and spelled with explicit ASCII
 *   classes here; `_HEADING_WORD_RE` stays Unicode on purpose (C98) and is
 *   `[\p{L}\p{Nl}\p{No}]` — Python's `[^\W\d_]` exactly, up to the Unicode version each
 *   runtime ships (a code point Python's database leaves unassigned may be a letter here);
 * - `str.lower()` is `toLowerCase()`, equal under the same Unicode-version caveat;
 * - a transcript line decodes as strict UTF-8 with a leading BOM kept (Python's `utf-8` codec,
 *   not `utf-8-sig`); a file read as text gets universal-newline translation, as `read_text`;
 * - `f"{x:.0%}"` rounds half to even on the exact binary value, `toFixed` would not;
 * - a lone surrogate cannot be encoded by `str.encode()` / `write_text`, so it raises here too;
 * - a Python `KeyError` / `ValueError` / `AttributeError` is an `Error` with that `name` and the
 *   exception's first argument as its message (Python's `str(KeyError(x))` is `repr(x)`).
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import { posix } from "node:path";
import { TextDecoder } from "node:util";

import { fill } from "../../common/jsondata.mjs";
import { FloatValue, canonicalForm, hookForm, wiringForm } from "../../common/json_writer.mjs";
import { claimDiagnosticMarker, gettempdir, releaseDiagnosticMarkers } from "../../common/markers.mjs";
import { aitnaRootName } from "../../common/project_root.mjs";
import { harnessCommand } from "../../common/runtime.mjs";
import { shlexSplit } from "../../common/shlex.mjs";
import { codePointCompare, codePointSort } from "../../common/sort.mjs";

/** @typedef {import("../../common/runtime.mjs").RuntimeData} RuntimeData */
/** @typedef {import("../../common/markers.mjs").MarkersData} MarkersData */

/**
 * The shape of `tools/model_routing/agents.json` — the data file is the owner of these keys.
 *
 * @typedef {object} AgentsData
 * @property {string} generated_banner
 * @property {string} zone_convention
 * @property {string} overlay_name
 * @property {string} local_config_rel
 * @property {string} delegation_log_rel
 * @property {string} agents_dir_rel
 * @property {string[]} settings_probe_names
 * @property {string[]} retired_second_opinion_keys
 * @property {{name: string, tier: string, description: string, tools: string | null, body: string,
 *   kinds: string[]}[]} agent_specs
 * @property {{binding: string, delegation: string, self_check: string}} status_lines
 * @property {string[]} init_instruction
 * @property {string} rebind_notice
 * @property {string} unlabelled_fanout_warning
 * @property {Record<string, string>} second_opinion_unavailability
 * @property {string} unpinnable_model
 * @property {{semantic: string, not_in_list: string, below_floor: string, reserved_top: string}} compute_binding_warnings
 * @property {string} role_matrix_warning
 * @property {string} floor_gap_line
 * @property {string} delegation_floor_warning
 * @property {{warn: string, info: string}} context_pressure
 * @property {{no_config: string, registry_changed: string, model_mismatch: string}} staleness
 * @property {{retired_keys: string, no_usable_spec: string}} second_opinion_spec_errors
 */

/**
 * The shape of `tools/model_routing/gate.json` this module reads (the rest is `gate_pack`'s).
 *
 * @typedef {object} GateData
 * @property {{role: string, trigger: string, noun: string, headings: string[], anchor: string}[]} gate_rules
 */

/** A parsed JSON document (registry, overlay, local config, payload): any JSON value. */
/** @typedef {any} Json */

// --------------------------------------------------------------------------------------
// Python semantics the module leans on (see the header's twin notes)
// --------------------------------------------------------------------------------------

/**
 * An `Error` named like the Python exception it stands for, carrying its first argument.
 * @param {string} name
 * @param {string} message
 * @returns {Error}
 */
function _pyError(name, message) {
  const error = new Error(message);
  error.name = name;
  return error;
}

/** Whether `value` is a JSON object — Python's `isinstance(value, dict)`. */
function _isDict(/** @type {unknown} */ value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) && !(value instanceof FloatValue);
}

/** Python's `type(value).__name__` for a JSON value. */
function _pyTypeName(/** @type {unknown} */ value) {
  if (value === null || value === undefined) {
    return "NoneType";
  }
  if (typeof value === "boolean") {
    return "bool";
  }
  if (typeof value === "string") {
    return "str";
  }
  if (value instanceof FloatValue) {
    return "float";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? "int" : "float";
  }
  return Array.isArray(value) ? "list" : "dict";
}

/**
 * `mapping.get(key, fallback)` — which raises on anything that is not a dict, as Python's does.
 * @param {Json} mapping
 * @param {string} key
 * @param {Json} [fallback]
 * @returns {Json}
 */
function _get(mapping, key, fallback = null) {
  if (!_isDict(mapping)) {
    throw _pyError("AttributeError", `'${_pyTypeName(mapping)}' object has no attribute 'get'`);
  }
  return Object.hasOwn(mapping, key) ? mapping[key] : fallback;
}

/**
 * `mapping[key]` — a miss raises `KeyError`, never answers `undefined`.
 * @param {Json} mapping
 * @param {string} key
 * @returns {Json}
 */
function _item(mapping, key) {
  if (!_isDict(mapping)) {
    throw _pyError("TypeError", `'${_pyTypeName(mapping)}' object is not subscriptable by '${key}'`);
  }
  if (!Object.hasOwn(mapping, key)) {
    throw _pyError("KeyError", key);
  }
  return mapping[key];
}

/**
 * `mapping[key] = value` as a dict stores it: an own data property even for `__proto__`.
 * @param {Record<string, Json>} mapping
 * @param {string} key
 * @param {Json} value
 */
function _set(mapping, key, value) {
  Object.defineProperty(mapping, key, { value, writable: true, enumerable: true, configurable: true });
}

/** Python truthiness for a JSON value: `[]`, `{}`, `""`, `0`, `0.0`, `False` and `None` are false. */
function _truthy(/** @type {unknown} */ value) {
  if (value === null || value === undefined || value === false || value === 0 || value === "") {
    return false;
  }
  if (value instanceof FloatValue) {
    return value.n !== 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value).length > 0;
  }
  return true;
}

/** The numeric value of a Python number (bool included, as Python's `==` sees it), else null. */
function _numeric(/** @type {unknown} */ value) {
  if (typeof value === "boolean") {
    return value ? 1 : 0;
  }
  if (typeof value === "number") {
    return value;
  }
  return value instanceof FloatValue ? value.n : null;
}

/**
 * Python's `==` between two JSON values.
 * @param {unknown} a
 * @param {unknown} b
 * @returns {boolean}
 */
function _pyEq(a, b) {
  const na = _numeric(a);
  const nb = _numeric(b);
  if (na !== null || nb !== null) {
    return na !== null && nb !== null && na === nb;
  }
  if (typeof a === "string" || typeof b === "string") {
    return a === b;
  }
  if ((a === null || a === undefined) && (b === null || b === undefined)) {
    return true;
  }
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => _pyEq(item, b[i]));
  }
  if (_isDict(a) && _isDict(b)) {
    const ka = Object.keys(/** @type {object} */ (a));
    const recordA = /** @type {Record<string, unknown>} */ (a);
    const recordB = /** @type {Record<string, unknown>} */ (b);
    return (
      ka.length === Object.keys(recordB).length &&
      ka.every((key) => Object.hasOwn(recordB, key) && _pyEq(recordA[key], recordB[key]))
    );
  }
  return false;
}

/**
 * The items Python's iteration yields: a list's elements, a string's code points, a dict's keys.
 * @param {Json} value
 * @returns {Json[]}
 */
function _iterate(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (typeof value === "string") {
    return Array.from(value);
  }
  if (_isDict(value)) {
    return Object.keys(value);
  }
  throw _pyError("TypeError", `'${_pyTypeName(value)}' object is not iterable`);
}

/**
 * Python's `item in container` over a list, a string (substring) or a dict (key).
 * @param {Json} container
 * @param {Json} item
 * @returns {boolean}
 */
function _contains(container, item) {
  if (typeof container === "string") {
    if (typeof item !== "string") {
      throw _pyError("TypeError", `'in <string>' requires string as left operand, not ${_pyTypeName(item)}`);
    }
    return container.includes(item);
  }
  if (_isDict(container)) {
    return typeof item === "string" && Object.hasOwn(container, item);
  }
  return _iterate(container).some((element) => _pyEq(element, item));
}

/**
 * Python's `seq.index(item)`; a miss raises `ValueError`.
 * @param {Json[]} seq
 * @param {Json} item
 * @returns {number}
 */
function _index(seq, item) {
  const at = seq.findIndex((element) => _pyEq(element, item));
  if (at < 0) {
    throw _pyError("ValueError", `${_pyRepr(item)} is not in list`);
  }
  return at;
}

/**
 * Python's `seq[-1]` over the sequences a ladder can be: a list or a string.
 * @param {Json} seq
 * @returns {Json}
 */
function _last(seq) {
  if (typeof seq === "string" || Array.isArray(seq)) {
    const items = _iterate(seq);
    if (items.length === 0) {
      throw _pyError("IndexError", "list index out of range");
    }
    return items[items.length - 1];
  }
  if (_isDict(seq)) {
    throw _pyError("KeyError", "-1");
  }
  throw _pyError("TypeError", `'${_pyTypeName(seq)}' object is not subscriptable`);
}

/** Python's `repr` of a float (`json_writer`'s shortest round-trip spelling, non-finite as Python). */
function _floatRepr(/** @type {number} */ n) {
  if (Number.isNaN(n)) {
    return "nan";
  }
  if (!Number.isFinite(n)) {
    return n > 0 ? "inf" : "-inf";
  }
  return hookForm(new FloatValue(n));
}

// Python's str.isprintable() is false for these categories, and for every space but U+0020.
const _NON_PRINTABLE = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\p{Zs}]/u;

/** Python's `repr` of a string: its quote choice, escapes, and kept printable non-ASCII. */
function _strRepr(/** @type {string} */ value) {
  const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of value) {
    const cp = ch.codePointAt(0) ?? 0; // `?? 0` only feeds the checker: an iterated character is never empty
    if (ch === quote || ch === "\\") {
      out += `\\${ch}`;
    } else if (ch === "\t") {
      out += "\\t";
    } else if (ch === "\n") {
      out += "\\n";
    } else if (ch === "\r") {
      out += "\\r";
    } else if (cp < 0x20 || cp === 0x7f) {
      out += `\\x${cp.toString(16).padStart(2, "0")}`;
    } else if (cp < 0x7f || (ch !== " " && !_NON_PRINTABLE.test(ch))) {
      out += ch;
    } else if (cp <= 0xff) {
      out += `\\x${cp.toString(16).padStart(2, "0")}`;
    } else if (cp <= 0xffff) {
      out += `\\u${cp.toString(16).padStart(4, "0")}`;
    } else {
      out += `\\U${cp.toString(16).padStart(8, "0")}`;
    }
  }
  return out + quote;
}

/**
 * Python's `repr` of a JSON value.
 * @param {unknown} value
 * @returns {string}
 */
function _pyRepr(value) {
  if (value === null || value === undefined) {
    return "None";
  }
  if (typeof value === "boolean") {
    return value ? "True" : "False";
  }
  if (typeof value === "string") {
    return _strRepr(value);
  }
  if (value instanceof FloatValue) {
    return _floatRepr(value.n);
  }
  if (typeof value === "number") {
    if (!Number.isInteger(value)) {
      return _floatRepr(value);
    }
    return Number.isSafeInteger(value) ? String(value) : BigInt(value).toString();
  }
  if (Array.isArray(value)) {
    return `[${value.map(_pyRepr).join(", ")}]`;
  }
  const entries = Object.entries(/** @type {object} */ (value));
  return `{${entries.map(([key, item]) => `${_strRepr(key)}: ${_pyRepr(item)}`).join(", ")}}`;
}

/** Python's `str()` of a JSON value: a string is itself, everything else its `repr`. */
function _pyStr(/** @type {unknown} */ value) {
  return typeof value === "string" ? value : _pyRepr(value);
}

/** `", ".join(items)` — every item must be a string, as Python's `join` requires. */
function _join(/** @type {string} */ separator, /** @type {Json[]} */ items) {
  items.forEach((item, i) => {
    if (typeof item !== "string") {
      throw _pyError("TypeError", `sequence item ${i}: expected str instance, ${_pyTypeName(item)} found`);
    }
  });
  return items.join(separator);
}

// str.isspace(): the characters Python's no-argument split()/strip() cut on. JavaScript's
// `\s`/`trim` add U+FEFF and miss U+001C–U+001F and U+0085.
const _PY_SPACE = "\\t\\n\\v\\f\\r\\x1c-\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const _PY_SPACE_RUN = new RegExp(`[${_PY_SPACE}]+`);
const _PY_LEADING_SPACE = new RegExp(`^[${_PY_SPACE}]+`);
const _PY_TRAILING_SPACE = new RegExp(`[${_PY_SPACE}]+$`);
// str.splitlines(): every line boundary Python knows, `\r\n` as one.
// `int(str)` strips the same set minus U+001C–U+001F, which it refuses as part of the literal.
const _INT_SPACE = "\\t\\n\\v\\f\\r\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const _INT_SURROUNDING_SPACE = new RegExp(`^[${_INT_SPACE}]+|[${_INT_SPACE}]+$`, "g");
const _PY_LINE_BREAKS = "\\n\\r\\v\\f\\x1c-\\x1e\\x85\\u2028\\u2029";
const _PY_LINE_BOUNDARY = new RegExp(`\\r\\n|[${_PY_LINE_BREAKS}]`);

/** `text.split()` with no argument. */
function _split(/** @type {string} */ text) {
  return text.split(_PY_SPACE_RUN).filter((word) => word !== "");
}

/** `text.lstrip()` with no argument. */
function _lstrip(/** @type {string} */ text) {
  return text.replace(_PY_LEADING_SPACE, "");
}

/** `text.strip()` with no argument. */
function _strip(/** @type {string} */ text) {
  return _lstrip(text).replace(_PY_TRAILING_SPACE, "");
}

/** `text.rstrip(chars)` for an explicit character set. */
function _rstripChars(/** @type {string} */ text, /** @type {string} */ chars) {
  let end = text.length;
  while (end > 0 && chars.includes(text[end - 1])) {
    end -= 1;
  }
  return text.slice(0, end);
}

/** `text.splitlines()`: no empty last line for a trailing break, `[]` for an empty text. */
function _splitlines(/** @type {string} */ text) {
  const lines = text.split(_PY_LINE_BOUNDARY);
  if (lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines;
}

/** `len(text)` — code points, not UTF-16 units. */
function _len(/** @type {string} */ text) {
  let count = 0;
  for (let i = 0; i < text.length; i++) {
    const unit = text.charCodeAt(i);
    const next = text.charCodeAt(i + 1);
    if (unit >= 0xd800 && unit <= 0xdbff && next >= 0xdc00 && next <= 0xdfff) {
      i += 1; // a surrogate pair is one code point; a lone surrogate is one too, as in Python
    }
    count += 1;
  }
  return count;
}

/** `text.lower()` — which raises on a non-string, as the attribute lookup does. */
function _lower(/** @type {unknown} */ text) {
  if (typeof text !== "string") {
    throw _pyError("AttributeError", `'${_pyTypeName(text)}' object has no attribute 'lower'`);
  }
  return text.toLowerCase();
}

/**
 * The first of `items` with the greatest code-point length — `max(items, key=len)`.
 * @param {string[]} items
 * @returns {string}
 */
function _longest(items) {
  let best = items[0];
  for (const item of items.slice(1)) {
    if (_len(item) > _len(best)) {
      best = item;
    }
  }
  return best;
}

/** The value of one Unicode decimal digit: Nd digits come in contiguous runs of 0–9. */
function _digitValue(/** @type {number} */ cp) {
  let start = cp;
  while (start > 0 && /^\p{Nd}$/u.test(String.fromCodePoint(start - 1))) {
    start -= 1;
  }
  return (cp - start) % 10;
}

/**
 * Python's `int(value)` for a JSON value: an int is itself, a float truncates, a bool is 0/1,
 * and a string parses as base 10 — surrounding whitespace (U+001C–U+001F excepted), a sign, any script's decimal
 * digits and single underscores between digits, as `int(str)` reads them.
 * @param {unknown} value
 * @returns {number}
 */
function _pyInt(value) {
  if (typeof value === "boolean") {
    return value ? 1 : 0;
  }
  const n = _numeric(value);
  if (n !== null) {
    if (Number.isNaN(n)) {
      throw _pyError("ValueError", "cannot convert float NaN to integer");
    }
    if (!Number.isFinite(n)) {
      throw _pyError("OverflowError", "cannot convert float infinity to integer");
    }
    return Math.trunc(n);
  }
  if (typeof value !== "string") {
    throw _pyError(
      "TypeError",
      `int() argument must be a string, a bytes-like object or a real number, not '${_pyTypeName(value)}'`,
    );
  }
  const invalid = () => _pyError("ValueError", `invalid literal for int() with base 10: ${_strRepr(value)}`);
  let body = value.replace(_INT_SURROUNDING_SPACE, "");
  let sign = 1;
  if (body.startsWith("+") || body.startsWith("-")) {
    sign = body.startsWith("-") ? -1 : 1;
    body = body.slice(1);
  }
  let digits = "";
  let previous = "";
  for (const ch of body) {
    if (ch === "_") {
      if (previous !== "digit") {
        throw invalid();
      }
      previous = "_";
      continue;
    }
    if (!/^\p{Nd}$/u.test(ch)) {
      throw invalid();
    }
    digits += String(_digitValue(ch.codePointAt(0) ?? 0));
    previous = "digit";
  }
  if (digits === "" || previous !== "digit") {
    throw invalid();
  }
  return sign * Number(digits);
}

/** `f"{ratio:.0%}"`: the share times 100, rounded half to even on the exact binary value. */
function _percent(/** @type {number} */ ratio) {
  const scaled = ratio * 100;
  const floor = Math.floor(scaled);
  const rest = scaled - floor; // exact: both are doubles of one binade or the fraction is zero
  const whole = rest > 0.5 || (rest === 0.5 && floor % 2 !== 0) ? floor + 1 : floor;
  return `${Number.isSafeInteger(whole) ? String(whole) : BigInt(whole).toString()}%`;
}

/**
 * `template.format(model=model)` — the replacement fields Python's `str.format` reads, for the
 * one keyword a `model_flag` is given. A field with a format spec or an attribute/index path is
 * refused rather than spelled differently: no registry declares one.
 * @param {string} template
 * @param {string} model
 * @returns {string}
 */
function _formatModel(template, model) {
  let out = "";
  let i = 0;
  while (i < template.length) {
    const ch = template[i];
    if (ch === "}") {
      if (template[i + 1] !== "}") {
        throw _pyError("ValueError", "Single '}' encountered in format string");
      }
      out += "}";
      i += 2;
      continue;
    }
    if (ch !== "{") {
      out += ch;
      i += 1;
      continue;
    }
    if (template[i + 1] === "{") {
      out += "{";
      i += 2;
      continue;
    }
    const close = template.indexOf("}", i + 1);
    if (close < 0) {
      throw _pyError("ValueError", "expected '}' before end of string");
    }
    const field = template.slice(i + 1, close);
    const match = /^([^!:]*)(?:!(.))?(?::(.*))?$/s.exec(field);
    if (match === null || field.includes("{")) {
      throw _pyError("ValueError", `format field {${field}} is not supported by the JavaScript twin`);
    }
    const name = match[1];
    if (name === "" || /^[0-9]+$/.test(name)) {
      throw _pyError(
        "IndexError",
        `Replacement index ${name === "" ? 0 : Number(name)} out of range for positional args tuple`,
      );
    }
    if (name.includes(".") || name.includes("[") || match[3]) {
      throw _pyError("ValueError", `format field {${field}} is not supported by the JavaScript twin`);
    }
    if (name !== "model") {
      throw _pyError("KeyError", name);
    }
    const conversion = match[2];
    if (conversion === undefined || conversion === "s") {
      out += model;
    } else if (conversion === "r") {
      out += _strRepr(model);
    } else {
      throw _pyError("ValueError", `Unknown conversion specifier ${conversion}`);
    }
    i = close + 1;
  }
  return out;
}

/** UTF-8 of `text`, refusing a lone surrogate the way `str.encode()` does. */
function _utf8(/** @type {string} */ text) {
  if (/\p{Surrogate}/u.test(text)) {
    throw _pyError("UnicodeEncodeError", "'utf-8' codec can't encode a surrogate: surrogates not allowed");
  }
  return Buffer.from(text, "utf8");
}

// --------------------------------------------------------------------------------------
// Paths and files — `pathlib` semantics
// --------------------------------------------------------------------------------------

/**
 * `str(PurePosixPath(*parts))`: segments joined, an absolute one restarting the path, empty
 * and `.` components dropped (`..` kept — that is the filesystem's to resolve), a leading `//`
 * kept as POSIX allows, and `.` for nothing at all.
 * @param {...string} parts
 * @returns {string}
 */
function _path(...parts) {
  let anchor = "";
  /** @type {string[]} */ let components = [];
  for (const part of parts) {
    if (part.startsWith("/")) {
      anchor = part.startsWith("//") && !part.startsWith("///") ? "//" : "/";
      components = [];
    }
    for (const component of part.split("/")) {
      if (component !== "" && component !== ".") {
        components.push(component);
      }
    }
  }
  const joined = anchor + components.join("/");
  return joined === "" ? "." : joined;
}

/** Whether `error` is a filesystem failure — Python's `OSError` (the markers twin's test). */
function _isOSError(/** @type {unknown} */ error) {
  return error instanceof Error && typeof (/** @type {{errno?: unknown}} */ (error).errno) === "number";
}

/**
 * The `stat` behind `Path.is_file()`/`is_dir()` (3.11–3.13): a missing path, a non-directory
 * parent, a bad descriptor, a link loop or an unencodable path (an embedded NUL) answer
 * "no"; any other failure — a permission error on the way — raises.
 * @param {string} path
 * @returns {fs.Stats | null}
 */
function _stat(path) {
  try {
    return fs.statSync(path);
  } catch (error) {
    const code = /** @type {{code?: string}} */ (error).code;
    if (["ENOENT", "ENOTDIR", "EBADF", "ELOOP", "ERR_INVALID_ARG_VALUE", "ERR_INVALID_ARG_TYPE"].includes(code ?? "")) {
      return null;
    }
    throw error;
  }
}

/** `Path.is_file()`. */
function _isFile(/** @type {string} */ path) {
  return _stat(path)?.isFile() ?? false;
}

/** `Path.is_dir()`. */
function _isDir(/** @type {string} */ path) {
  return _stat(path)?.isDirectory() ?? false;
}

/** Strict UTF-8 with a leading BOM kept: Python's `utf-8` codec, not `utf-8-sig`. */
const _UTF8 = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

/**
 * The bytes as Python's strict UTF-8 decode reads them; a malformed sequence raises
 * (`UnicodeDecodeError`, a `ValueError` — never swallowed as an `OSError`).
 * @param {Uint8Array} bytes
 * @returns {string}
 */
function _decode(bytes) {
  try {
    return _UTF8.decode(bytes);
  } catch {
    throw _pyError("UnicodeDecodeError", "'utf-8' codec can't decode the bytes: invalid UTF-8");
  }
}

/** `Path.read_text(encoding="utf-8")`: strict decoding, then universal-newline translation. */
function _readText(/** @type {string} */ path) {
  return _decode(fs.readFileSync(path)).replace(/\r\n?/g, "\n");
}

/** `Path.write_text(text, encoding="utf-8")` — a lone surrogate raises before the file opens. */
function _writeText(/** @type {string} */ path, /** @type {string} */ text) {
  fs.writeFileSync(path, _utf8(text));
}

/** `Path.unlink(missing_ok=True)`. */
function _unlinkMissingOk(/** @type {string} */ path) {
  try {
    fs.unlinkSync(path);
  } catch (error) {
    if (/** @type {{code?: string}} */ (error).code !== "ENOENT") {
      throw error;
    }
  }
}

// --------------------------------------------------------------------------------------
// Data accessors and the registry
// --------------------------------------------------------------------------------------

/**
 * Committed, per-project overlay file name (project-root-relative).
 *
 * Same shape as the registry, deep-merged over it; may add a "briefs" map with per-agent
 * markdown appended to the generated subagent bodies — keyed by agent name, matched
 * notation-insensitively, unmatched key is an error: see `resolveBriefs`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function overlayName(data) {
  return data.overlay_name;
}

/**
 * Per-user resolved binding (gitignored, like .env) — written by init, read by the hook.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function localConfigRel(data) {
  return data.local_config_rel;
}

/**
 * The delegation log the PreToolUse hook appends to (project-root-relative).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function delegationLogRel(data) {
  return data.delegation_log_rel;
}

/**
 * The generated `k_*` subagent definitions' directory (project-root-relative).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function agentsDirRel(data) {
  return data.agents_dir_rel;
}

/**
 * The banner marking a generated agent file as machine-written — the obsolete sweep's gate.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function generatedBanner(data) {
  return data.generated_banner;
}

/**
 * The `.claude` settings files the default-model probe reads, local first (single owner).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string[]}
 */
export function settingsProbeNames(data) {
  return [...data.settings_probe_names];
}

/**
 * Path to the shipped `registry.json` under an akmon tree.
 * @param {string} akmonDir
 * @returns {string}
 */
export function registryPath(akmonDir) {
  return _path(akmonDir, "tools", "model_routing", "registry.json");
}

/**
 * Path to the project's committed model-routing overlay file, if any.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {string}
 */
export function overlayPath(data, projectRoot) {
  return _path(projectRoot, aitnaRootName(), overlayName(data));
}

/**
 * The override deep-merged over the base: nested objects merge, everything else replaces.
 * @param {Record<string, Json>} base
 * @param {Record<string, Json>} override
 * @returns {Record<string, Json>}
 */
function _deepMerge(base, override) {
  const merged = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const current = Object.hasOwn(merged, key) ? merged[key] : undefined;
    _set(merged, key, _isDict(value) && _isDict(current) ? _deepMerge(current, value) : value);
  }
  return merged;
}

const _WHOLE_FLOAT_SPELLING = /[0-9]\.0+(?![0-9])|[0-9][eE]/;

/**
 * `json.loads` for a document a person may edit (the registry, its overlay, the local config):
 * a whole number the text spells as a float (`3.0`, `1e3`) stays a `FloatValue`, so a check that
 * refuses a Python float refuses it here too. The reviver's third argument (the source text)
 * is Node >= 21; the transcript readers keep plain `JSON.parse` (see the header).
 * @param {string} text
 * @returns {Json}
 */
function _parseKeepingFloats(text) {
  // The reviver doubles the parse time; only a text that can spell a whole float (`.0` closing
  // a number, or an exponent) needs it — a string that merely looks like one costs the slow
  // path, never a wrong answer.
  if (!_WHOLE_FLOAT_SPELLING.test(text)) {
    return JSON.parse(text);
  }
  /** @type {(text: string, reviver: (key: string, value: any, context: any) => any) => any} */
  const parse = /** @type {any} */ (JSON.parse);
  return parse(text, (_key, value, context) =>
    typeof value === "number" && Number.isInteger(value) && /[.eE]/.test(context?.source ?? "")
      ? new FloatValue(value)
      : value,
  );
}

/**
 * The merged registry: akmon data deep-merged with the project overlay (if any).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} akmonDir
 * @param {string | null} [projectRoot]
 * @returns {Json}
 */
export function loadRegistry(data, akmonDir, projectRoot = null) {
  let registry = _parseKeepingFloats(_readText(registryPath(akmonDir)));
  if (projectRoot !== null && projectRoot !== undefined) {
    const overlay = overlayPath(data, projectRoot);
    if (_isFile(overlay)) {
      const parsed = _parseKeepingFloats(_readText(overlay));
      if (!_isDict(registry) || !_isDict(parsed)) {
        // `_deep_merge` copies the registry with `dict()` and walks the overlay's `.items()`.
        throw _pyError("AttributeError", `'${_pyTypeName(parsed)}' object has no attribute 'items'`);
      }
      registry = _deepMerge(registry, parsed);
    }
  }
  return registry;
}

/**
 * Stable digest of the merged registry — staleness detection for the local config.
 * @param {Json} registry
 * @returns {string}
 */
export function registryHash(registry) {
  return createHash("sha256").update(canonicalForm(registry), "utf8").digest("hex").slice(0, 16);
}

/** The tier→model binding — a pure function of (selection policy, orchestrator, available). */
export class Binding {
  /**
   * @param {string} vendor
   * @param {Json} orchestrator
   * @param {Json} reasoner
   * @param {Json} worker
   * @param {Json} mid
   * @param {Json} auditor
   * @param {Json[]} escalation
   * @param {boolean} [semanticFallback]
   * @param {string | null} [warning]
   * @param {Json} [secondOpinionCli]
   */
  constructor(
    vendor,
    orchestrator,
    reasoner,
    worker,
    mid,
    auditor,
    escalation,
    semanticFallback = false,
    warning = null,
    secondOpinionCli = null,
  ) {
    this.vendor = vendor;
    this.orchestrator = orchestrator;
    this.reasoner = reasoner;
    this.worker = worker;
    this.mid = mid;
    this.auditor = auditor;
    this.escalation = Object.freeze([...escalation]);
    this.semanticFallback = semanticFallback;
    this.warning = warning;
    this.secondOpinionCli = secondOpinionCli;
    Object.freeze(this);
  }
}

/**
 * The semantic ladder: worker, mid, reasoner, then the auditor, each once.
 * @param {Json} vendorData
 * @returns {string[]}
 */
function _semanticRungs(vendorData) {
  const fallback = _get(vendorData, "semantic_fallback", {});
  const worker = _pyStr(_truthy(_get(fallback, "worker")) ? _get(fallback, "worker") : "worker");
  const mid = _pyStr(_truthy(_get(fallback, "mid")) ? _get(fallback, "mid") : "mid");
  const reasoner = _pyStr(_truthy(_get(fallback, "reasoner")) ? _get(fallback, "reasoner") : "strongest");
  const auditor = _pyStr(_truthy(_get(fallback, "auditor")) ? _get(fallback, "auditor") : "strongest");
  /** @type {string[]} */ const rungs = [];
  for (const rung of [worker, mid, reasoner]) {
    if (!rungs.includes(rung)) {
      rungs.push(rung);
    }
  }
  if (!rungs.includes(auditor)) {
    rungs.push(auditor);
  }
  return rungs;
}

/** `value or fallback`. */
function _or(/** @type {Json} */ value, /** @type {Json} */ fallback) {
  return _truthy(value) ? value : fallback;
}

/**
 * Bind tiers to model aliases from a semantic vendor policy (MODEL.md § Capability tiers).
 *
 * `available` is the concrete, local, discovery-derived ladder ordered weakest → strongest.
 * The shared registry stores only the selection policy. Without `available` the binding uses
 * semantic fallback labels and carries a warning; generated file-backed agents then omit concrete
 * model frontmatter instead of pretending those labels are valid vendor model ids.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} orchestrator
 * @param {Json} [available]
 * @param {string} [vendor]
 * @returns {Binding}
 */
export function computeBinding(data, registry, orchestrator, available = null, vendor = "anthropic") {
  const vendorData = _item(registry, vendor);
  const semantic = !_truthy(available);
  let rungs = _truthy(available) ? [..._iterate(available)] : _semanticRungs(vendorData);
  if (rungs.length === 0) {
    rungs = _semanticRungs(vendorData);
  }

  const auditor = rungs[rungs.length - 1]; // pinned max, always — unlike the now-dynamic reasoner
  const worker = rungs[0];
  const workerPos = _index(rungs, worker);
  const mid = rungs[Math.min(workerPos + 1, rungs.length - 1)];
  const escalation = rungs.slice(workerPos + 1, rungs.length - 1);

  const policy = _get(vendorData, "selection_policy", {});
  const reasonerPolicy = _get(policy, "reasoner", "highest");
  let reasoner;
  if (semantic) {
    const fallback = _get(vendorData, "semantic_fallback", {});
    reasoner = _pyStr(_or(_get(fallback, "reasoner"), "strongest"));
  } else if (_pyEq(reasonerPolicy, "orchestrator") && _contains(rungs, orchestrator)) {
    reasoner = orchestrator;
  } else {
    // Unknown orchestrator, or a non-"orchestrator" policy value (e.g. "highest") —
    // fall back to the top rung.
    reasoner = rungs[rungs.length - 1];
  }

  const warnings = data.compute_binding_warnings;
  /** @type {string | null} */ let warning = null;
  if (semantic) {
    warning = warnings.semantic;
  } else {
    const floor = _get(policy, "orchestrator_floor", "highest");
    const floorRung = _pyEq(floor, "highest") ? rungs[rungs.length - 1] : _pyStr(floor);
    if (!_contains(rungs, orchestrator)) {
      warning = fill(warnings.not_in_list, { orchestrator: _pyStr(orchestrator) });
    } else if (_contains(rungs, floorRung)) {
      // Healthy corridor: floor ≤ orchestrator < top (design §3, ADR 0006). When the
      // ladder tops out at the floor, floor == top and both arms stay silent — the
      // accepted degraded mode. A floor alias absent from the ladder disables the
      // check (nothing to rank against); the relative "highest" floor resolves to the
      // top rung, reproducing the pre-corridor below-top warning.
      const orchRank = _index(rungs, orchestrator);
      const floorRank = _index(rungs, floorRung);
      if (orchRank < floorRank) {
        warning = fill(warnings.below_floor, { orchestrator: _pyStr(orchestrator), floor: _pyStr(floorRung) });
      } else if (orchRank === rungs.length - 1 && floorRank < rungs.length - 1) {
        warning = fill(warnings.reserved_top, { orchestrator: _pyStr(orchestrator), floor: _pyStr(floorRung) });
      }
    }
  }

  const provider = oppositeVendor(data, registry, vendor);
  const secondOpinion = _get(_get(registry, provider, {}), "second_opinion", {});
  return new Binding(
    vendor,
    orchestrator,
    reasoner,
    worker,
    mid,
    auditor,
    escalation,
    semantic,
    warning,
    _get(secondOpinion, "harness"),
  );
}

/**
 * Per-task-kind rung floors, resolved to concrete aliases from `rungs`.
 *
 * Only task kinds carrying a `"floor"` key are included. `"highest"` resolves to
 * `rungs[-1]`; a literal alias passes through only when present in `rungs`. A kind
 * whose floor cannot be resolved (empty `rungs`, or an alias absent from it) is skipped.
 * @param {Json} registry
 * @param {Json} rungs
 * @returns {Record<string, Json>}
 */
export function taskKindFloors(registry, rungs) {
  /** @type {Record<string, Json>} */ const floors = {};
  if (!_truthy(rungs)) {
    return floors;
  }
  const kinds = _get(registry, "task_kinds", {});
  if (!_isDict(kinds)) {
    throw _pyError("AttributeError", `'${_pyTypeName(kinds)}' object has no attribute 'items'`);
  }
  for (const [kind, spec] of Object.entries(kinds)) {
    const floor = _get(spec, "floor");
    if (!_truthy(floor)) {
      continue;
    }
    if (_pyEq(floor, "highest")) {
      _set(floors, kind, _last(rungs));
    } else if (_contains(rungs, floor)) {
      _set(floors, kind, _pyStr(floor));
    }
  }
  return floors;
}

/**
 * Vendors that can run a main/orchestrator session under the semantic routing policy.
 * @param {Json} registry
 * @returns {string[]}
 */
export function vendorsWithRoutingPolicy(registry) {
  if (!_isDict(registry)) {
    throw _pyError("AttributeError", `'${_pyTypeName(registry)}' object has no attribute 'items'`);
  }
  return Object.entries(registry)
    .filter(([, spec]) => _isDict(spec) && _isDict(_get(spec, "selection_policy")))
    .map(([name]) => name);
}

/**
 * Default second-opinion provider: another configured vendor, preferring the recorded order.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} vendor
 * @returns {string}
 */
export function oppositeVendor(data, registry, vendor) {
  for (const candidate of vendorsWithRoutingPolicy(registry)) {
    if (candidate !== vendor && _truthy(secondOpinionSpec(data, registry, candidate, { required: false }))) {
      return candidate;
    }
  }
  return vendor;
}

/**
 * Keys C57 retired when the executable moved into `common/runtime.py`.
 *
 * A project overlay written before that change deep-merges *over* the shipped registry, so
 * the new keys survive and the stale ones ride along unread — the config looks usable and
 * silently means something else.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string[]}
 */
export function retiredSecondOpinionKeys(data) {
  return [...data.retired_second_opinion_keys];
}

/**
 * The second-opinion policy for one provider, or `{}` when it is absent and optional.
 *
 * A spec still carrying the retired keys always raises (`KeyError`), in both the required and
 * optional calls: it is a stale *configuration*, not an absent capability, and degrading it to
 * "no second opinion available" would hide the migration behind a silently weaker run.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} provider
 * @param {{required?: boolean}} [options]
 * @returns {Json}
 */
export function secondOpinionSpec(data, registry, provider, { required = true } = {}) {
  const errors = data.second_opinion_spec_errors;
  const spec = _get(_get(registry, provider, {}), "second_opinion", {});
  if (_isDict(spec)) {
    const retired = retiredSecondOpinionKeys(data).filter((key) => Object.hasOwn(spec, key));
    if (retired.length) {
      throw _pyError("KeyError", fill(errors.retired_keys, { provider: _pyStr(provider), retired: retired.join(", ") }));
    }
    if (_truthy(spec.harness) && _truthy(spec.operation) && _truthy(spec.report_dir)) {
      return spec;
    }
  }
  if (required) {
    throw _pyError("KeyError", fill(errors.no_usable_spec, { provider: _pyStr(provider) }));
  }
  return {};
}

/**
 * The same-vendor fallback rung when no other vendor is reachable (design §9.7 #2).
 *
 * The diversity requirement is about *model* priors, not vendor branding: the strongest
 * rung that differs from both the orchestrator (the author) and the auditor. `null` when
 * no rung differs from the orchestrator at all (a single distinct rung) — the caller warns
 * or skips; it must never fall back to the same model.
 * @param {Json} rungs
 * @param {Json} orchestrator
 * @param {Json} auditor
 * @returns {Json}
 */
export function secondOpinionFallbackModel(rungs, orchestrator, auditor) {
  for (const rung of [..._iterate(rungs)].reverse()) {
    if (!_pyEq(rung, orchestrator) && !_pyEq(rung, auditor)) {
      return rung;
    }
  }
  return null;
}

/** A second opinion asked for a model its vendor declares no `model_flag` to pin (C97). */
export class UnpinnableModelError extends Error {
  /**
   * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
   * @param {string} harness
   * @param {Json} model
   */
  constructor(data, harness, model) {
    super(fill(data.unpinnable_model, { model: _pyRepr(model), harness }));
    this.name = "UnpinnableModelError";
  }
}

/**
 * Build the non-interactive CLI command; the prompt is passed as the final argv.
 *
 * The executable and the operation's argv come from the single owner in `common/runtime.json`;
 * the registry contributes only *policy* — which harness, which operation, and the optional
 * `model_flag` format string (e.g. `"--model {model}"`) inserted before the prompt so the
 * same-vendor branch of the diversity ladder can pin a *different* model.
 *
 * A requested `model` with no `model_flag` raises `UnpinnableModelError` (C97): the run
 * would otherwise go out on the harness's default model and still be filed as a model-diverse
 * second opinion — the one guarantee the ladder exists to give, lost without a signal.
 * @param {AgentsData} agentsData the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} spec
 * @param {string} prompt
 * @param {Json} [model]
 * @returns {string[]}
 */
export function secondOpinionCommand(agentsData, runtimeData, spec, prompt, model = null) {
  const argv = harnessCommand(runtimeData, _pyStr(_item(spec, "harness")), _pyStr(_item(spec, "operation")));
  if (_truthy(model)) {
    const modelFlag = _get(spec, "model_flag");
    if (!_truthy(modelFlag)) {
      throw new UnpinnableModelError(agentsData, _pyStr(_item(spec, "harness")), model);
    }
    argv.push(...shlexSplit(_formatModel(_pyStr(modelFlag), _pyStr(model))));
  }
  return [...argv, prompt];
}

/**
 * Why no model-diverse reviewer exists, walked step by step over the configured ladder.
 *
 * Deliberately not a second verdict: `resolveSecondOpinion` owns the answer. This states,
 * per ladder step, the population that step had — and it states a *conclusion* ("nothing
 * differs") only where it derives one from the same helper the ladder uses. A step that was
 * never attempted says so instead of being explained away, because an overlay can shorten
 * the ladder, and "no diverse reviewer" then means something entirely different.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} config
 * @param {string} orchestratorVendor
 * @returns {string}
 */
export function secondOpinionUnavailability(data, registry, config, orchestratorVendor) {
  const policy = _isDict(registry) ? _get(registry, "second_opinion_policy", {}) : {};
  const ladder = _or(_get(policy, "diversity_ladder"), ["other-vendor", "same-vendor-other-model"]);
  const others = vendorsWithRoutingPolicy(registry).filter(
    (vendor) =>
      vendor !== orchestratorVendor && _truthy(secondOpinionSpec(data, registry, vendor, { required: false })),
  );
  const configured = _get(config, "second_opinion_provider");
  const rungs = _or(_get(config, "available"), null) ?? _semanticRungs(_get(registry, orchestratorVendor, {}));
  const orchestrator = _pyStr(_or(_get(config, "orchestrator"), "?"));
  const auditor = _pyStr(_or(_get(_get(config, "binding", {}), "auditor"), "?"));
  const against = `the orchestrator '${orchestrator}' and the auditor '${auditor}'`;
  const texts = data.second_opinion_unavailability;

  let otherVendor;
  if (!_contains(ladder, "other-vendor")) {
    otherVendor = texts.other_vendor_absent;
  } else if (others.length === 0) {
    otherVendor = texts.other_vendor_none;
  } else if (typeof configured === "string" && configured === orchestratorVendor) {
    otherVendor = fill(texts.other_vendor_pinned, { configured, others: others.join(", ") });
  } else {
    otherVendor = fill(texts.other_vendor_usable, { others: others.join(", ") });
  }

  let sameVendor;
  if (!_contains(ladder, "same-vendor-other-model")) {
    sameVendor = texts.same_vendor_absent;
  } else if (secondOpinionFallbackModel(rungs, orchestrator, auditor) === null) {
    sameVendor = fill(texts.same_vendor_no_diverse_rung, {
      vendor: orchestratorVendor,
      rungs: _pyRepr(rungs),
      against,
    });
  } else {
    sameVendor = fill(texts.same_vendor_diverse_rung, { vendor: orchestratorVendor, rungs: _pyRepr(rungs), against });
  }
  return `${otherVendor}; ${sameVendor}`;
}

/** A resolved second-opinion target: which provider, and which model to pin (if any). */
export class SecondOpinionTarget {
  /**
   * @param {Json} provider
   * @param {string | null} model `null` = the provider CLI's default model (other-vendor case)
   */
  constructor(provider, model) {
    this.provider = provider;
    this.model = model;
    Object.freeze(this);
  }
}

/**
 * Walk `second_opinion_policy.diversity_ladder` to a (provider, model) target.
 *
 * Diversity is about *model priors* (design §9.3 item 3): the reviewer must differ
 * from the models it reviews. Ladder steps (registry data):
 *   - "other-vendor": another configured vendor with a usable spec — different priors
 *     by construction, so model=null (its CLI default is already a different model);
 *   - "same-vendor-other-model": the same vendor, pinned to the strongest rung that
 *     differs from BOTH orchestrator (author) and auditor, via
 *     `secondOpinionFallbackModel` (design §9.7 #2);
 *   - `never: same-model` — if no rung differs, return null (skip); the caller must
 *     never fall back to the same model.
 *
 * An explicit `config.second_opinion_provider` is honored: a configured *other*
 * vendor satisfies the other-vendor step; configured == orchestrator vendor routes to
 * the same-vendor branch.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} config
 * @param {string} orchestratorVendor
 * @returns {SecondOpinionTarget | null}
 */
export function resolveSecondOpinion(data, registry, config, orchestratorVendor) {
  const policy = _isDict(registry) ? _get(registry, "second_opinion_policy", {}) : {};
  const ladder = _or(_get(policy, "diversity_ladder"), ["other-vendor", "same-vendor-other-model"]);
  const orchestrator = _pyStr(_or(_get(config, "orchestrator"), ""));
  const auditor = _pyStr(_or(_get(_get(config, "binding", {}), "auditor"), ""));
  const configured = _get(config, "second_opinion_provider");
  for (const step of _iterate(ladder)) {
    if (_pyEq(step, "other-vendor")) {
      // An explicit same-vendor override is a deliberate "stay on my vendor, pin a
      // different model" choice — skip the other-vendor step so it falls through to
      // same-vendor-other-model rather than silently picking the opposite vendor.
      if (typeof configured === "string" && configured === orchestratorVendor) {
        continue;
      }
      const provider =
        typeof configured === "string" && configured && configured !== orchestratorVendor
          ? configured
          : oppositeVendor(data, registry, orchestratorVendor);
      if (provider !== orchestratorVendor && _truthy(secondOpinionSpec(data, registry, provider, { required: false }))) {
        return new SecondOpinionTarget(provider, null);
      }
    } else if (_pyEq(step, "same-vendor-other-model")) {
      const provider = orchestratorVendor;
      if (!_truthy(secondOpinionSpec(data, registry, provider, { required: false }))) {
        continue;
      }
      let model = _get(config, "second_opinion_fallback_model");
      if (!_truthy(model)) {
        const rungs = _or(_get(config, "available"), null) ?? _semanticRungs(_get(registry, provider, {}));
        model = secondOpinionFallbackModel(rungs, orchestrator, auditor);
      }
      if (_truthy(model)) {
        return new SecondOpinionTarget(provider, _pyStr(model));
      }
    }
  }
  return null;
}

// --------------------------------------------------------------------------------------
// Generated subagent definitions (the `k-` akmon namespace)
// --------------------------------------------------------------------------------------

// Each agent groups the task kinds whose briefs coincide; the tier picks its model from
// the binding. Bodies are project-neutral (this is SHARED); project specifics are appended
// via the overlay's "briefs" map.
/** One generated `k_*` subagent's definition: tier, description, tools, body, task kinds. */
export class AgentSpec {
  /**
   * @param {string} name
   * @param {string} tier "worker" | "mid" | "reasoner" | "auditor"
   * @param {string} description
   * @param {string | null} tools frontmatter `tools:`; null = all tools
   * @param {string} body
   * @param {string[]} [kinds]
   */
  constructor(name, tier, description, tools, body, kinds = []) {
    this.name = name;
    this.tier = tier;
    this.description = description;
    this.tools = tools;
    this.body = body;
    this.kinds = Object.freeze([...kinds]);
    Object.freeze(this);
  }
}

/**
 * The six generated `k_*` subagent definitions (`agents.json`), in roster order.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {AgentSpec[]}
 */
export function agentSpecs(data) {
  return data.agent_specs.map((raw) => new AgentSpec(raw.name, raw.tier, raw.description, raw.tools, raw.body, raw.kinds));
}

/**
 * The model one agent's frontmatter pins: its tier's alias, or null under semantic fallback.
 * @param {AgentSpec} spec
 * @param {Binding} binding
 * @returns {Json}
 */
function _agentModel(spec, binding) {
  if (binding.semanticFallback) {
    return null;
  }
  return _item({ worker: binding.worker, mid: binding.mid, reasoner: binding.reasoner, auditor: binding.auditor }, spec.tier);
}

/**
 * Render one generated `.claude/agents/<name>.md` file: frontmatter, banner, body, brief.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {AgentSpec} spec
 * @param {Binding} binding
 * @param {string} [briefExtra]
 * @returns {string}
 */
export function agentFileContent(data, spec, binding, briefExtra = "") {
  const lines = ["---", `name: ${spec.name}`, "description: >-"];
  // The auditor reads a fan-out rather than being a zone of it, so it carries no zone convention.
  const description = spec.name === "k_auditor" ? spec.description : `${spec.description} ${zoneConvention(data)}`;
  lines.push(..._wrap(description, 88).map((chunk) => `  ${chunk}`));
  if (spec.tools) {
    lines.push(`tools: ${spec.tools}`);
  }
  const model = _agentModel(spec, binding);
  if (_truthy(model)) {
    lines.push(`model: ${_pyStr(model)}`);
  }
  lines.push("---");
  lines.push("");
  lines.push(`<!-- ${generatedBanner(data)} -->`);
  lines.push("");
  lines.push(spec.body);
  if (_strip(briefExtra)) {
    lines.push("");
    lines.push("<!-- project overlay brief -->");
    lines.push("");
    lines.push(_strip(briefExtra));
  }
  return lines.join("\n") + "\n";
}

/**
 * Greedy word wrap at `width` code points; a word longer than the width stands alone.
 * @param {string} text
 * @param {number} width
 * @returns {string[]}
 */
function _wrap(text, width) {
  /** @type {string[]} */ const chunks = [];
  let current = "";
  for (const word of _split(text)) {
    const candidate = current ? `${current} ${word}` : word;
    if (_len(candidate) > width && current) {
      chunks.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) {
    chunks.push(current);
  }
  return chunks;
}

/**
 * A project overlay's `briefs` map cannot be applied to the current agent specs.
 *
 * Raised instead of defaulting to an empty brief: an overlay brief is hand-authored
 * project instruction, and a key that matches no agent means those instructions would
 * silently vanish from the generated definition — no diff to look at, no warning. That is
 * the tolerance-degrades-to-silence shape C48 argues against, and ADR 0011's `k-*` →
 * `k_*` rename made it live (C50).
 */
export class BriefError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "BriefError";
  }
}

/**
 * Normal form of an agent name for overlay lookups — folds case, `-`/`_` and surrounding whitespace.
 *
 * Overlay brief keys are a public contract written by hand in a consumer's repository, so
 * a change of *notation* (ADR 0011) must not orphan them. The tolerance line, owner-verified
 * at ADR-0011/D02: invisible and notational differences are forgiven — surrounding whitespace does
 * not survive a diff, so failing on it costs more to diagnose than the tolerance costs to hold
 * — while any difference in significant characters, an internal space included, still fails
 * (see `resolveBriefs`).
 * @param {string} name
 * @returns {string}
 */
export function agentKey(name) {
  return _strip(name).toLowerCase().replaceAll("-", "_");
}

/**
 * Overlay briefs re-keyed by the **current** spec names; raises `BriefError` otherwise.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @returns {Record<string, string>}
 */
export function resolveBriefs(data, registry) {
  const briefs = _get(registry, "briefs", {});
  if (!_isDict(briefs)) {
    throw new BriefError(`overlay 'briefs' must be an object, got ${_pyTypeName(briefs)}`);
  }
  /** @type {Map<string, string>} */ const byKey = new Map();
  for (const spec of agentSpecs(data)) {
    byKey.set(agentKey(spec.name), spec.name);
  }
  /** @type {Record<string, string>} */ const resolved = {};
  /** @type {Record<string, string>} */ const source = {};
  const keys = Object.keys(briefs).sort(codePointCompare);
  for (const key of keys) {
    const text = briefs[key];
    if (typeof text !== "string") {
      throw new BriefError(`overlay brief '${key}' must be a string, got ${_pyTypeName(text)}`);
    }
    const name = byKey.get(agentKey(key));
    if (name === undefined) {
      const known = codePointSort([...byKey.values()]).join(", ");
      throw new BriefError(`overlay brief key '${key}' matches no agent (known: ${known})`);
    }
    if (Object.hasOwn(resolved, name)) {
      throw new BriefError(`overlay brief keys '${source[name]}' and '${key}' both resolve to '${name}'`);
    }
    source[name] = key;
    resolved[name] = text;
  }
  return resolved;
}

/**
 * Owner-addressed line naming an unusable overlay `briefs` map, or null when it is fine.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string | null} [aitna]
 * @returns {string | null}
 */
export function briefWarning(data, registry, aitna = null) {
  try {
    resolveBriefs(data, registry);
  } catch (error) {
    if (!(error instanceof BriefError)) {
      throw error;
    }
    const root = aitna || aitnaRootName();
    return `⚠ ${error.message} — fix ${root}/${overlayName(data)}; k_* definitions are not regenerated until it resolves`;
  }
  return null;
}

const _REBIND_MARKER = "suppressed-rebind";

/**
 * Emit one warning per session/model/error episode; reset when the condition clears.
 *
 * A refused rebind leaves the recorded orchestrator unchanged, so comparing the next
 * transcript against that config reports the same switch on every prompt. The marker is
 * deliberately temporary rather than project state: it remembers only which warning the
 * current session already saw. A changed model or error produces a new digest and re-arms
 * the notice; a cleared condition removes the marker so a later recurrence speaks again.
 *
 * Since C36(a) the marker is claimed through `common/markers` — atomic, hashed, `0600`,
 * aged out after a day — so exactly-once per episode is the contract. The condition is folded
 * into the marker's kind, and moving to another condition or clearing it releases the
 * session's other markers, which is what re-arms a later recurrence.
 * @param {MarkersData} markersData the parsed `common/markers.json`
 * @param {string | null} warning
 * @param {Json} detectedModel
 * @param {Json} sessionId
 * @param {{markerDir?: string | null}} [options]
 * @returns {string[]}
 */
export function suppressedRebindWarning(markersData, warning, detectedModel, sessionId, { markerDir = null } = {}) {
  // Without a reliable session identity, never let one anonymous invocation silence
  // another session. Repeating the warning is safer than a process-global `nosession`
  // marker that hides an unresolved lossy-rebind condition from an unrelated owner.
  if (!_truthy(sessionId)) {
    return warning !== null && warning !== undefined && detectedModel !== null && detectedModel !== undefined
      ? [warning]
      : [];
  }
  const session = _pyStr(sessionId);
  if (warning === null || warning === undefined || detectedModel === null || detectedModel === undefined) {
    releaseDiagnosticMarkers(markersData, _REBIND_MARKER, session, { directory: markerDir });
    return [];
  }
  const condition = createHash("sha256")
    .update(_utf8(`${_pyStr(detectedModel)}\0${warning}`))
    .digest("hex")
    .slice(0, 16);
  const kind = `${_REBIND_MARKER}-${condition}`;
  if (!claimDiagnosticMarker(markersData, kind, session, { directory: markerDir })) {
    return [];
  }
  releaseDiagnosticMarkers(markersData, _REBIND_MARKER, session, { keepKind: kind, directory: markerDir });
  return [warning];
}

/**
 * Map of `.claude/agents/<name>.md` relative paths → generated content.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Binding} binding
 * @returns {Record<string, string>}
 */
export function generatedAgentFiles(data, registry, binding) {
  const briefs = resolveBriefs(data, registry);
  /** @type {Record<string, string>} */ const files = {};
  for (const spec of agentSpecs(data)) {
    files[`${agentsDirRel(data)}/${spec.name}.md`] = agentFileContent(
      data,
      spec,
      binding,
      Object.hasOwn(briefs, spec.name) ? briefs[spec.name] : "",
    );
  }
  return files;
}

/**
 * The roster keyed by name (a Map: a name is never confused with an object property).
 * @param {AgentsData} data
 * @returns {Map<string, AgentSpec>}
 */
function _agentByName(data) {
  return new Map(agentSpecs(data).map((spec) => [spec.name, spec]));
}

/**
 * Task kinds a generated subagent covers; empty for a host built-in / unknown name.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} name
 * @returns {readonly string[]}
 */
export function subagentKinds(data, name) {
  const spec = typeof name === "string" ? _agentByName(data).get(name) : undefined;
  return spec ? spec.kinds : [];
}

/**
 * Model a generated `k_*` agent is pinned to — its tier's binding alias, or null.
 *
 * The generated agent frontmatter carries `model: <alias>`, but an `Agent` call rarely echoes
 * it — so the delegation record shows `-` and the console line omits the model. Deriving it
 * from the recorded binding restores it. Null for an unknown agent (a host built-in) or for a
 * semantic-fallback binding, whose tier values are labels (`worker`/`strongest`), not vendor
 * aliases.
 *
 * The config does not persist `Binding.semanticFallback`, so the mode is re-derived the
 * same way `computeBinding` decides it: **no recorded `available` ladder is exactly
 * semantic fallback**. That is the mirror of the agent file emitting no `model:` line — an
 * agent file without a pin is inherited by the host from the session, so there is no pin to
 * report and the record honestly says `-`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} subagentType
 * @returns {string | null}
 */
export function boundModelFor(data, config, subagentType) {
  const spec = typeof subagentType === "string" ? _agentByName(data).get(subagentType) : undefined;
  if (spec === undefined || !_isDict(config)) {
    return null;
  }
  const binding = config.binding;
  if (!_isDict(binding)) {
    return null;
  }
  const model = Object.hasOwn(binding, spec.tier) ? binding[spec.tier] : null;
  if (typeof model !== "string" || !model) {
    return null;
  }
  const available = config.available;
  if (
    !Array.isArray(available) ||
    available.length === 0 ||
    !available.every((alias) => typeof alias === "string") ||
    !available.includes(model)
  ) {
    return null;
  }
  return model;
}

// A declaration: `🧭 agent: <name>` as the first non-whitespace text of a turn (`re.ASCII`).
const _ROLE_DECL_RE = /^[ \t\n\r\f\v]*🧭[ \t\n\r\f\v]*agent:[ \t\n\r\f\v]*([A-Za-z][A-Za-z0-9_-]*)/u;

/**
 * The text of an assistant turn: its string content, or its text blocks joined by a space.
 * @param {Record<string, Json>} entry
 * @returns {string}
 */
function _assistantText(entry) {
  const message = entry.message;
  if (!_isDict(message)) {
    return "";
  }
  const content = message.content;
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return _join(
      " ",
      content.filter((block) => _isDict(block) && block.type === "text").map((block) => _get(block, "text", "")),
    );
  }
  return "";
}

/** Block size of the tail read. A line longer than one block is assembled across blocks. */
const _TAIL_BLOCK_BYTES = 1 << 16;
const _CR = 0x0d;
const _LF = 0x0a;

/**
 * The transcript path when it names a regular file, else null.
 * @param {string | null | undefined} transcriptPath
 * @returns {string | null}
 */
function _transcriptFile(transcriptPath) {
  if (!transcriptPath) {
    return null;
  }
  const path = _path(transcriptPath);
  return _isFile(path) ? path : null;
}

/**
 * `block` split on `\r\n`, `\r` and `\n` (the exact split), or on `\n` alone.
 * @param {Buffer} block
 * @param {boolean} exact
 * @returns {Buffer[]}
 */
function _splitBlock(block, exact) {
  /** @type {Buffer[]} */ const pieces = [];
  let start = 0;
  for (let i = 0; i < block.length; i++) {
    const byte = block[i];
    if (byte === _LF || (exact && byte === _CR)) {
      pieces.push(block.subarray(start, i));
      if (exact && byte === _CR && block[i + 1] === _LF) {
        i += 1;
      }
      start = i + 1;
    }
  }
  pieces.push(block.subarray(start));
  return pieces;
}

/**
 * Up to `size` bytes at `position`, short only at the end of the file — a buffered `read(size)`.
 * @param {number} fd
 * @param {number} position
 * @param {number} size
 * @returns {Buffer}
 */
function _readAt(fd, position, size) {
  const buffer = Buffer.alloc(size);
  let filled = 0;
  while (filled < size) {
    const read = fs.readSync(fd, buffer, filled, size - filled, position + filled);
    if (read === 0) {
      break;
    }
    filled += read;
  }
  return buffer.subarray(0, filled);
}

/**
 * The lines of the open file `fd` that contain `needle`, last line first (A19).
 *
 * Both transcript scanners want the *last* record that qualifies, so reading from the end and
 * stopping at the first qualifying record returns what a full forward scan returns, at a cost
 * set by the distance from the end rather than by the file's size. Lines split on `\r\n`,
 * `\r` and `\n`, as a forward text-mode read splits them, and each line decodes as strict
 * UTF-8. A line that does not decode is skipped. Memory stays at one block plus the longest
 * line.
 * @param {number} fd
 * @param {Buffer} needle
 * @returns {Generator<string>}
 */
function* _linesFromEnd(fd, needle) {
  let position = fs.fstatSync(fd).size;
  /** @type {Buffer[]} */ let carry = []; // the start of the line that runs past the current block, in file order
  while (position > 0) {
    const size = Math.min(_TAIL_BLOCK_BYTES, position);
    position -= size;
    const block = _readAt(fd, position, size);
    // JSON escapes a carriage return, so a real transcript carries none, and the `\n` split is
    // the fast one. A block holding one takes the exact split — the Python's choice, kept
    // because it decides where a `\r\n` straddling two blocks splits.
    const pieces = _splitBlock(block, block.includes(_CR));
    if (pieces.length === 1) {
      carry.unshift(pieces[0]);
      continue;
    }
    const complete = [Buffer.concat([pieces[pieces.length - 1], ...carry]), ...pieces.slice(1, -1).reverse()];
    carry = [pieces[0]];
    yield* _decoded(complete, needle);
  }
  yield* _decoded([Buffer.concat(carry)], needle);
}

/**
 * The lines holding `needle`, decoded; a line that is not strict UTF-8 is skipped.
 * @param {Buffer[]} lines
 * @param {Buffer} needle
 * @returns {Generator<string>}
 */
function* _decoded(lines, needle) {
  for (const raw of lines) {
    if (raw.includes(needle)) {
      let text;
      try {
        text = _decode(raw);
      } catch {
        continue;
      }
      yield text;
    }
  }
}

/**
 * The record on `line` when it is a main-chain assistant turn, else null.
 *
 * Sidechain (subagent) turns are skipped, and so is a line that is not JSON — a torn last line
 * included, since the harness may be writing it while a hook reads.
 * @param {string} line
 * @returns {Record<string, Json> | null}
 */
function _mainChainAssistant(line) {
  let entry;
  try {
    entry = JSON.parse(line);
  } catch (error) {
    if (error instanceof SyntaxError) {
      return null;
    }
    throw error;
  }
  if (!_isDict(entry) || entry.type !== "assistant" || _truthy(entry.isSidechain)) {
    return null;
  }
  return entry;
}

/**
 * Scan a transcript's matching lines from the end with `visit` until it answers non-undefined;
 * a filesystem failure (`OSError`) ends the scan with `fallback`, anything else propagates.
 * @template T
 * @param {string} path
 * @param {Buffer} needle
 * @param {(line: string) => T | undefined} visit
 * @param {T} fallback
 * @returns {T}
 */
function _scanFromEnd(path, needle, visit, fallback) {
  let fd;
  try {
    fd = fs.openSync(path, "r");
  } catch (error) {
    if (_isOSError(error)) {
      return fallback;
    }
    throw error;
  }
  try {
    for (const line of _linesFromEnd(fd, needle)) {
      const answer = visit(line);
      if (answer !== undefined) {
        return answer;
      }
    }
  } catch (error) {
    if (_isOSError(error)) {
      return fallback;
    }
    throw error;
  } finally {
    try {
      fs.closeSync(fd);
    } catch {
      // the scan's answer stands; a failed close of a read-only descriptor changes nothing
    }
  }
  return fallback;
}

/**
 * The role from the last qualifying `🧭 agent: <name>` transcript declaration.
 *
 * Only main-chain assistant turns are read, so the SessionStart reminder / a subagent echo
 * never masquerades as the declaration. A declaration qualifies only as the first
 * non-whitespace text of its turn. Returns the case-normalized role name, else null.
 *
 * Read from the end (A19), stopping at the first qualifying declaration, which is the last one.
 * A session that never declared a role still reads the whole file.
 * @param {string | null | undefined} transcriptPath
 * @returns {string | null}
 */
export function activeRole(transcriptPath) {
  const path = _transcriptFile(transcriptPath);
  if (path === null) {
    return null;
  }
  // Cheap ascii pre-filter: the emoji may be \u-escaped in the JSONL, but "agent:" is
  // always literal. JSON.parse then decodes the real marker.
  return _scanFromEnd(
    path,
    Buffer.from("agent:"),
    (line) => {
      const entry = _mainChainAssistant(line);
      const match = entry !== null ? _ROLE_DECL_RE.exec(_assistantText(entry)) : null;
      return match ? match[1].toLowerCase() : undefined;
    },
    /** @type {string | null} */ (null),
  );
}

/**
 * Conservative advisory (§10.2): the agent has no effectively allowed task kind.
 *
 * The call carries the agent, not an authoritative invocation kind, so warn only when *none*
 * of the agent's kinds intersect the role's effective allowed set. Null when the role is
 * unknown/undeclared or the agent is a host built-in (no kinds).
 *
 * **Cross-cutting verification kinds** (`cross_cutting_kinds`) are *not* role-gated (A7 (b),
 * §10.2): they join every role's allowed set, so an agent whose only kinds are cross-cutting
 * (e.g. `k_auditor`) never warns under any role.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} subagentType
 * @param {string | null} role
 * @returns {string | null}
 */
export function roleMatrixWarning(data, registry, subagentType, role) {
  if (!role) {
    return null;
  }
  const roleRows = _get(registry, "role_task_kinds", {});
  if (!_isDict(roleRows) || !Object.hasOwn(roleRows, role)) {
    return null;
  }
  const allowed = roleRows[role];
  if (!Array.isArray(allowed)) {
    return null;
  }
  /** @type {Json[]} */ const effectiveAllowed = [];
  for (const kind of [...allowed, ..._iterate(_get(registry, "cross_cutting_kinds", []))]) {
    if (kind !== null && typeof kind === "object" && !(kind instanceof FloatValue)) {
      throw _pyError("TypeError", `unhashable type: '${_pyTypeName(kind)}'`);
    }
    if (!effectiveAllowed.some((seen) => _pyEq(seen, kind))) {
      effectiveAllowed.push(kind);
    }
  }
  const kinds = subagentKinds(data, subagentType);
  if (kinds.length === 0 || kinds.some((kind) => effectiveAllowed.some((allowedKind) => _pyEq(allowedKind, kind)))) {
    return null;
  }
  const allowedText = _join(", ", effectiveAllowed) || "no task kinds";
  return fill(data.role_matrix_warning, {
    subagent: _pyStr(subagentType),
    kinds: kinds.join(", "),
    role,
    allowed: allowedText,
  });
}

// --------------------------------------------------------------------------------------
// Local config + status line (the SessionStart hook contract)
// --------------------------------------------------------------------------------------

/**
 * Map a concrete vendor model id (e.g. `claude-opus-4-8`) to a known local alias.
 *
 * The alias is matched as a case-insensitive substring of the id, preferring the longest
 * match so overlapping aliases disambiguate (`opus` over a bare `o`). Null when no alias in
 * `available` matches — the caller keeps the recorded binding rather than guess.
 * @param {Json} modelId
 * @param {Json} available
 * @returns {Json}
 */
export function resolveAlias(modelId, available) {
  if (!_truthy(modelId) || !_truthy(available)) {
    return null;
  }
  const lowered = _lower(modelId);
  const matches = _iterate(available).filter((alias) => _truthy(alias) && lowered.includes(_lower(alias)));
  return matches.length ? _longest(matches) : null;
}

/** `(model id, usage)` of the last main-chain assistant turn — what `lastMainTurn` returns. */
/** @typedef {[string | null, Record<string, Json> | null]} MainTurn */

/**
 * (model id, usage) of the last *main-chain* assistant turn in the session transcript.
 *
 * The transcript (a JSONL the harness records; its path arrives in the hook payload) carries
 * `message.model` and `message.usage` per assistant turn. Sidechain (subagent) turns and
 * synthetic entries are skipped, so a delegate's model or usage never masquerades as the
 * orchestrator's. Read from the end (A19) and stopped at the first qualifying turn.
 * `[null, null]` when the transcript is missing/empty/unreadable or names no model yet.
 * @param {string | null | undefined} transcriptPath
 * @returns {MainTurn}
 */
export function lastMainTurn(transcriptPath) {
  const path = _transcriptFile(transcriptPath);
  if (path === null) {
    return [null, null];
  }
  return _scanFromEnd(
    path,
    Buffer.from('"model"'),
    (line) => {
      const entry = _mainChainAssistant(line);
      const message = entry !== null ? entry.message : null;
      const model = _isDict(message) ? message.model : null;
      if (typeof model === "string" && model && !model.startsWith("<")) {
        const usage = message.usage;
        return /** @type {MainTurn} */ ([model, _isDict(usage) ? usage : null]);
      }
      return undefined;
    },
    /** @type {MainTurn} */ ([null, null]),
  );
}

/**
 * Alias of the model the *main chain* last ran on, read from the session transcript.
 *
 * Null when the transcript names no model yet or the model maps to no known alias: the caller
 * then keeps the recorded orchestrator instead of guessing. `turn` is a `lastMainTurn` result
 * the caller already read; the transcript is read only without one.
 * @param {string | null | undefined} transcriptPath
 * @param {Json} available
 * @param {{turn?: MainTurn | null}} [options]
 * @returns {Json}
 */
export function detectOrchestrator(transcriptPath, available, { turn = null } = {}) {
  const [modelId] = turn !== null && turn !== undefined ? turn : lastMainTurn(transcriptPath);
  return resolveAlias(modelId, available);
}

// --------------------------------------------------------------------------------------
// Context-pressure detection (design §12, ADR 0006) — the tokens axis of runtime weakness
// --------------------------------------------------------------------------------------

/**
 * Context fill at a turn: the three input components partition the prompt.
 *
 * `output_tokens` is not context carried forward, so it is excluded. Null unless all three
 * input components are non-negative integers (a bool is not a count, a float is not either).
 * @param {Json} usage
 * @returns {number | null}
 */
export function contextFill(usage) {
  if (!_isDict(usage)) {
    return null;
  }
  const components = ["input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"].map((key) =>
    Object.hasOwn(usage, key) ? usage[key] : null,
  );
  if (!components.every((value) => typeof value === "number" && Number.isInteger(value) && value >= 0)) {
    return null;
  }
  return components.reduce((total, value) => total + value, 0);
}

/**
 * Overrides the recommended maximum for every model when it holds a positive integer — per user
 * (the shell, or `env` in `~/.claude/settings.json`) or per project (`env` in
 * `.claude/settings.json`). Any other value is ignored and the registry decides.
 */
export const RECOMMENDED_MAX_ENV = "AKMON_CONTEXT_RECOMMENDED_MAX";

/**
 * The recommended context budget, in tokens — what pressure percentages are a share of.
 *
 * Resolution: `AKMON_CONTEXT_RECOMMENDED_MAX` when it holds a positive integer, else the
 * longest alias-substring key of `recommended_max_by_alias` found in the model id, else
 * `recommended_max` (design §12.2, C80).
 * @param {Json} registry
 * @param {Json} modelId
 * @returns {number}
 */
export function recommendedMaxContext(registry, modelId) {
  let override;
  try {
    override = _pyInt(process.env[RECOMMENDED_MAX_ENV] ?? "");
  } catch (error) {
    if (/** @type {Error} */ (error).name !== "ValueError") {
      throw error;
    }
    override = 0;
  }
  if (override > 0) {
    return override;
  }
  const policy = _get(registry, "context_pressure", {});
  const fallback = _pyInt(_or(_get(policy, "recommended_max"), 200000));
  const byAlias = _get(policy, "recommended_max_by_alias", {});
  if (_truthy(modelId) && _isDict(byAlias)) {
    const lowered = _lower(modelId);
    const matches = Object.keys(byAlias).filter((key) => key && lowered.includes(key.toLowerCase()));
    if (matches.length) {
      return _pyInt(byAlias[_longest(matches)]);
    }
  }
  return fallback;
}

/**
 * `[fill, recommendedMax, ratio]` for the last main-chain turn; null if unavailable.
 * @param {Json} registry
 * @param {string | null | undefined} transcriptPath
 * @param {MainTurn | null} [turn]
 * @returns {[number, number, number] | null}
 */
function _contextFillMetrics(registry, transcriptPath, turn = null) {
  const [modelId, usage] = turn !== null && turn !== undefined ? turn : lastMainTurn(transcriptPath);
  const filled = contextFill(usage);
  if (filled === null) {
    return null;
  }
  const recommended = recommendedMaxContext(registry, modelId);
  if (recommended <= 0) {
    return null;
  }
  return [filled, recommended, filled / recommended];
}

/**
 * Fill as a share of the recommended maximum for the last main-chain turn (can pass 1.0); null
 * if unavailable. Reused by the C29 output-weight nudge.
 * @param {Json} registry
 * @param {string | null | undefined} transcriptPath
 * @returns {number | null}
 */
export function contextFillRatio(registry, transcriptPath) {
  const metrics = _contextFillMetrics(registry, transcriptPath);
  return metrics ? metrics[2] : null;
}

/**
 * One reminder line when the context fill reached a *new* pressure level; `[]` otherwise.
 *
 * Two levels of the recommended budget (design §12.2): **info** at `info_ratio` and **warn**
 * at the budget itself, 1.0. Throttled by a per-session temp-dir marker recording the last
 * announced level, so only a rise speaks; a fill below the lowest level ends the pressure
 * episode and clears the marker. Missing/malformed usage → silent; never raises past I/O.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string | null | undefined} transcriptPath
 * @param {Json} sessionId
 * @param {{markerDir?: string | null, turn?: MainTurn | null}} [options]
 * @returns {string[]}
 */
export function contextPressureNotice(data, registry, transcriptPath, sessionId, { markerDir = null, turn = null } = {}) {
  const policy = _get(registry, "context_pressure", {});
  // Only a share strictly between 0 and 1 is a level below the budget; anything else (absent,
  // a bool, 0, 1 or more, a string) leaves the budget's own warning alone.
  const rawInfo = _get(policy, "info_ratio");
  let infoRatio = typeof rawInfo === "boolean" ? null : _numeric(rawInfo);
  if (infoRatio !== null && !(infoRatio > 0 && infoRatio < 1)) {
    infoRatio = null;
  }
  const metrics = _contextFillMetrics(registry, transcriptPath, turn);
  if (metrics === null) {
    return [];
  }
  const [, recommended, ratio] = metrics;
  /** @type {number | null} */ let level = null; // 0 = info, 1 = warn — the value the marker records
  if (ratio >= 1.0) {
    level = 1;
  } else if (infoRatio !== null && ratio >= infoRatio) {
    level = 0;
  }

  const marker = _path(markerDir ?? gettempdir(), `akmon-context-pressure-${_pyStr(_or(sessionId, "nosession"))}`);
  /** @type {number | null} */ let lastLevel;
  try {
    lastLevel = _pyInt(_readText(marker));
  } catch (error) {
    // Python catches OSError and ValueError (a decode failure is one); a NUL in the path is a
    // ValueError there and an argument error here.
    const name = /** @type {Error} */ (error).name;
    if (!_isOSError(error) && !["ValueError", "UnicodeDecodeError", "TypeError"].includes(name)) {
      throw error;
    }
    lastLevel = null;
  }

  if (level === null) {
    // Below every level — the pressure episode is over and the throttle resets. The cause is
    // not visible here: a compact, a fresh session and anything else that lowered the fill
    // look alike.
    try {
      _unlinkMissingOk(marker);
    } catch (error) {
      if (!_isOSError(error)) {
        throw error;
      }
    }
    return [];
  }
  if (lastLevel !== null && level <= lastLevel) {
    return [];
  }
  try {
    _writeText(marker, String(level));
  } catch (error) {
    if (!_isOSError(error)) {
      throw error;
    }
  }

  const shown = recommended % 1000 === 0 ? `${Math.floor(recommended / 1000)}k` : String(recommended);
  const share = `~${_percent(ratio)} of the recommended ${shown} budget`;
  // A reminder to the owner and nothing more: the share and the command to type. The marks are
  // the hook's own: ⚠ for a warning, as the corridor's, ℹ for information.
  const pressure = data.context_pressure;
  if (level === 1) {
    return [fill(pressure.warn, { share })];
  }
  return [fill(pressure.info, { share })];
}

/**
 * Every generated routing artifact as `project-root-relative path → content`.
 *
 * The generated `k_*` subagent definitions plus the local config — the single set the init
 * tool and the SessionStart/UserPromptSubmit hook both write, so a rebind from either path
 * produces byte-identical files.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Binding} binding
 * @param {{secondOpinion: boolean, available: Json}} options
 * @returns {Record<string, string>}
 */
export function bindingArtifacts(data, registry, binding, { secondOpinion, available }) {
  const files = { ...generatedAgentFiles(data, registry, binding) };
  const config = localConfig(data, binding, registry, { secondOpinion, available });
  files[localConfigRel(data)] = wiringForm(config);
  return files;
}

/**
 * Generated subagent definitions on disk that the current `agentSpecs()` no longer plan.
 *
 * Only files carrying `generatedBanner()` are candidates, so a hand-written agent living in
 * the same directory is never a deletion target. Without this, renaming an agent leaves its
 * old definition behind as a live duplicate (ADR 0011).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} root
 * @param {Iterable<string>} plannedPaths
 * @returns {string[]}
 */
export function obsoleteAgentFiles(data, root, plannedPaths) {
  const agentsDir = _path(root, agentsDirRel(data));
  if (!_isDir(agentsDir)) {
    return [];
  }
  const planned = new Set([...plannedPaths].map((path) => _path(path)));
  let names;
  try {
    names = fs.readdirSync(agentsDir);
  } catch (error) {
    // `Path.glob` yields nothing from a directory it cannot list.
    if (!_isOSError(error)) {
      throw error;
    }
    return [];
  }
  /** @type {string[]} */ const obsolete = [];
  for (const name of codePointSort(names.filter((entry) => entry.endsWith(".md")))) {
    const path = _path(agentsDir, name);
    if (planned.has(path)) {
      continue;
    }
    let text;
    try {
      text = _readText(path);
    } catch (error) {
      if (_isOSError(error)) {
        continue;
      }
      throw error;
    }
    if (text.includes(generatedBanner(data))) {
      obsolete.push(path);
    }
  }
  return obsolete;
}

/**
 * Delete the generated agent definitions no longer planned; return their paths.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} root
 * @param {Iterable<string>} plannedPaths
 * @param {{write?: boolean}} [options]
 * @returns {string[]}
 */
export function removeObsoleteAgents(data, root, plannedPaths, { write = true } = {}) {
  const removed = obsoleteAgentFiles(data, root, plannedPaths);
  if (write) {
    for (const path of removed) {
      _unlinkMissingOk(path);
    }
  }
  return removed;
}

/**
 * Write each artifact whose content changed; return the changed paths (idempotent).
 * @param {string} root
 * @param {Record<string, string>} files
 * @param {{write?: boolean}} [options]
 * @returns {string[]}
 */
export function writeArtifacts(root, files, { write = true } = {}) {
  /** @type {string[]} */ const changed = [];
  for (const [rel, content] of Object.entries(files)) {
    const path = _path(root, rel);
    const current = _isFile(path) ? _readText(path) : null;
    if (current === content) {
      continue;
    }
    changed.push(path);
    if (write) {
      fs.mkdirSync(posix.dirname(path), { recursive: true });
      _writeText(path, content);
    }
  }
  return changed;
}

/**
 * Recompute the binding for `orchestrator` and (re)write the artifacts under `root`.
 *
 * Reuses the recorded `available` list and opt-ins from `config` — only the orchestrator
 * moves. Idempotent: unchanged files are left untouched. This is how the hook makes subagent
 * models follow the session's actual orchestrating model.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} root
 * @param {Json} registry
 * @param {Json} config
 * @param {Json} orchestrator
 * @param {{write?: boolean}} [options]
 * @returns {[Binding, string[]]}
 */
export function rebindTo(data, root, registry, config, orchestrator, { write = true } = {}) {
  const available = _get(config, "available");
  const secondOpinion = _truthy(_get(config, "second_opinion"));
  const vendor = _pyStr(_or(_get(config, "vendor"), "anthropic"));
  const binding = computeBinding(data, registry, orchestrator, available, vendor);
  const files = bindingArtifacts(data, registry, binding, { secondOpinion, available });
  const changed = writeArtifacts(root, files, { write });
  removeObsoleteAgents(
    data,
    root,
    Object.keys(files).map((rel) => _path(root, rel)),
    { write },
  );
  return [binding, changed];
}

/**
 * The per-user resolved config written to `localConfigRel()` (binding, opt-ins, staleness hash).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Binding} binding
 * @param {Json} registry
 * @param {{secondOpinion: boolean, available: Json}} options
 * @returns {Record<string, Json>}
 */
export function localConfig(data, binding, registry, { secondOpinion, available }) {
  /** @type {Record<string, Json>} */
  const config = {
    vendor: binding.vendor,
    orchestrator: binding.orchestrator,
    binding: {
      reasoner: binding.reasoner,
      worker: binding.worker,
      mid: binding.mid,
      auditor: binding.auditor,
      escalation: [...binding.escalation],
    },
    second_opinion: secondOpinion,
    second_opinion_provider: oppositeVendor(data, registry, binding.vendor),
    available: available ?? null,
    registry_hash: registryHash(registry),
    task_kind_floors: taskKindFloors(registry, _or(available, [])),
  };
  if (config.second_opinion_provider === binding.vendor) {
    const rungs = _truthy(available) ? [..._iterate(available)] : _semanticRungs(_get(registry, binding.vendor, {}));
    config.second_opinion_fallback_model = secondOpinionFallbackModel(rungs, binding.orchestrator, binding.auditor);
  }
  return config;
}

/**
 * Why the local config is stale — or null when it is fresh.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} registry
 * @param {Json} settingsModel
 * @returns {string | null}
 */
export function staleness(data, config, registry, settingsModel) {
  const texts = data.staleness;
  if (!_truthy(config)) {
    return texts.no_config;
  }
  if (!_pyEq(_get(config, "registry_hash"), registryHash(registry))) {
    return texts.registry_changed;
  }
  if (_truthy(settingsModel) && !_pyEq(settingsModel, _get(config, "orchestrator"))) {
    return fill(texts.model_mismatch, { model: _pyStr(settingsModel) });
  }
  return null;
}

/**
 * What the second-opinion gate will actually do, as one status field plus any warning.
 *
 * Resolved through the same ladder the runner walks (`resolveSecondOpinion`), so the display
 * cannot disagree with the policy. A retired-key overlay (C57) raises out of here, deliberately.
 * @param {AgentsData} data
 * @param {Json} registry
 * @param {Json} config
 * @param {string} orchestratorVendor
 * @returns {[string, string | null]}
 */
function _secondOpinionStatus(data, registry, config, orchestratorVendor) {
  const enabled = _truthy(_get(config, "second_opinion"));
  const state = enabled ? "on" : "off";
  const target = resolveSecondOpinion(data, registry, config, orchestratorVendor);
  if (target === null) {
    const warning =
      "second-opinion is on but the diversity ladder is exhausted: no reachable " +
      "provider differs from the reviewed model, so every gate will skip it — " +
      "second_opinion.py states the reason at the gate and names the one thing that " +
      "can still be run by hand, with its limits";
    return [`second-opinion=unavailable(${state})`, enabled ? warning : null];
  }
  const harness = _pyStr(_or(_get(secondOpinionSpec(data, registry, target.provider, { required: false }), "harness"), "-"));
  const pin = target.model ? `, model=${target.model}` : "";
  return [`second-opinion=${harness}(${state}${pin})`, null];
}

/** A task kind whose rung floor sits above the rung its routed agent is bound to (C32). */
export class FloorGap {
  /**
   * @param {string} kind
   * @param {string} agent
   * @param {Json} floor
   * @param {string} bound
   */
  constructor(kind, agent, floor, bound) {
    this.kind = kind;
    this.agent = agent;
    this.floor = floor;
    this.bound = bound;
    Object.freeze(this);
  }
}

/**
 * The position of `alias` on the ladder, or null for a non-string or an absent alias.
 * @param {Json[]} ladder
 * @param {Json} alias
 * @returns {number | null}
 */
function _rank(ladder, alias) {
  return typeof alias === "string" && _contains(ladder, alias) ? _index(ladder, alias) : null;
}

/**
 * Kinds whose recorded `task_kind_floors` entry exceeds their agent's bound model.
 *
 * The floors are resolved at init against the local ladder; the agent's model is the one
 * `boundModelFor` reports, so a semantic-fallback binding (no pin) yields no gap.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @returns {FloorGap[]}
 */
export function floorGaps(data, config) {
  const floors = _isDict(config) ? _get(config, "task_kind_floors") : null;
  const ladder = _isDict(config) ? _get(config, "available") : null;
  if (!_isDict(floors) || !Array.isArray(ladder)) {
    return [];
  }
  /** @type {FloorGap[]} */ const gaps = [];
  for (const spec of agentSpecs(data)) {
    const bound = boundModelFor(data, config, spec.name);
    const boundRank = _rank(ladder, bound);
    if (bound === null || boundRank === null) {
      continue;
    }
    for (const kind of spec.kinds) {
      const floor = Object.hasOwn(floors, kind) ? floors[kind] : null;
      const floorRank = _rank(ladder, floor);
      if (floorRank !== null && floorRank > boundRank) {
        gaps.push(new FloorGap(kind, spec.name, floor, bound));
      }
    }
  }
  return gaps;
}

/**
 * One context line per floor gap: which kind, which agent, and the override that meets it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @returns {string[]}
 */
export function floorGapLines(data, config) {
  const template = data.floor_gap_line;
  return floorGaps(data, config).map((gap) =>
    fill(template, { kind: gap.kind, floor: _pyStr(gap.floor), agent: gap.agent, bound: gap.bound }),
  );
}

/**
 * Per-call form of the floor check for the delegation log (C32).
 *
 * The call does not say which task kind it carries, so the warning is conditional on the
 * kind; an explicit `model` override at or above every gapped floor silences it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} subagentType
 * @param {Json} callModel
 * @returns {string | null}
 */
export function delegationFloorWarning(data, config, subagentType, callModel) {
  const ladder = _isDict(config) ? _get(config, "available") : null;
  const gaps = floorGaps(data, config).filter((gap) => gap.agent === subagentType);
  if (gaps.length === 0 || !Array.isArray(ladder)) {
    return null;
  }
  const callRank = _rank(ladder, callModel);
  const openGaps = gaps.filter((gap) => callRank === null || callRank < _index(ladder, gap.floor));
  if (openGaps.length === 0) {
    return null;
  }
  const kinds = openGaps.map((gap) => `${gap.kind} (floor ${_pyStr(gap.floor)})`).join(", ");
  return fill(data.delegation_floor_warning, { subagent: _pyStr(subagentType), bound: openGaps[0].bound, kinds });
}

/**
 * The recorded escalation path, named only when the binding pins concrete aliases.
 * @param {Json} config
 * @returns {string}
 */
function _escalationHint(config) {
  const binding = _get(config, "binding", {});
  const path = _isDict(binding) ? _get(binding, "escalation") : null;
  const ladder = _get(config, "available");
  if (!Array.isArray(path) || path.length === 0 || !Array.isArray(ladder) || ladder.length === 0) {
    return "";
  }
  return ` (escalation path: ${path.map((rung) => _pyStr(rung)).join(" → ")})`;
}

/**
 * The steady-state status injection: one binding line + self-check, plus any warning.
 *
 * `runtimeRoot` is the project-root-relative directory the routing tools actually live in —
 * `<AITNA_ROOT>/akmon` when the standard is mounted, `<AITNA_ROOT>/.akmon` in mount mode
 * `package` (ADR 0009 §4). It is passed in because only the caller knows the project root.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} registry
 * @param {string} runtimeRoot
 * @returns {string[]}
 */
export function statusLines(data, config, registry, runtimeRoot) {
  const binding = _get(config, "binding", {});
  const orchestratorVendor = _pyStr(_or(_get(config, "vendor"), "anthropic"));
  const [secondDisplay, secondWarning] = _secondOpinionStatus(data, registry, config, orchestratorVendor);
  const orchestrator = _get(config, "orchestrator", "?");
  const texts = data.status_lines;
  const lines = [
    fill(texts.binding, {
      vendor: orchestratorVendor,
      orchestrator: _pyStr(orchestrator),
      reasoner: _pyStr(_get(binding, "reasoner", "?")),
      auditor: _pyStr(_get(binding, "auditor", "?")),
      worker: _pyStr(_get(binding, "worker", "?")),
      mid: _pyStr(_get(binding, "mid", "?")),
      second_opinion: secondDisplay,
    }),
    fill(texts.delegation, { escalation_hint: _escalationHint(config), zone_convention: zoneConvention(data) }),
    fill(texts.self_check, { orchestrator: _pyStr(orchestrator), runtime_root: runtimeRoot }),
  ];
  const warning = computeBinding(data, registry, orchestrator, _get(config, "available"), orchestratorVendor).warning;
  if (warning) {
    lines.push(`⚠ ${warning}`);
  }
  if (secondWarning) {
    lines.push(`⚠ ${secondWarning}`);
  }
  lines.push(...floorGapLines(data, config));
  return lines;
}

/**
 * The concise mid-session note after the orchestrator model changed (UserPromptSubmit).
 *
 * One line naming the new orchestrator and the recomputed subagent binding, plus the
 * weak-orchestrator warning when it applies.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} registry
 * @returns {string[]}
 */
export function rebindNotice(data, config, registry) {
  const binding = _get(config, "binding", {});
  const orchestrator = _get(config, "orchestrator", "?");
  const vendor = _pyStr(_or(_get(config, "vendor"), "anthropic"));
  const lines = [
    fill(data.rebind_notice, {
      orchestrator: _pyStr(orchestrator),
      reasoner: _pyStr(_get(binding, "reasoner", "?")),
      auditor: _pyStr(_get(binding, "auditor", "?")),
      worker: _pyStr(_get(binding, "worker", "?")),
      mid: _pyStr(_get(binding, "mid", "?")),
    }),
  ];
  const warning = computeBinding(data, registry, orchestrator, _get(config, "available"), vendor).warning;
  if (warning) {
    lines.push(`⚠ ${warning}`);
  }
  lines.push(...floorGapLines(data, config));
  return lines;
}

/**
 * The one-time setup instruction. `runtimeRoot`: see `statusLines`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} reason
 * @param {string} runtimeRoot
 * @returns {string[]}
 */
export function initInstruction(data, reason, runtimeRoot) {
  const values = { reason, runtime_root: runtimeRoot };
  return data.init_instruction.map((line) => fill(line, values));
}

// --------------------------------------------------------------------------------------
// Delegation log (the PreToolUse hook contract)
// --------------------------------------------------------------------------------------

const _SUBAGENT_TOOLS = new Set(["Task", "Agent"]);

// `re.ASCII | re.IGNORECASE | re.DOTALL`; the `i` flag without `u` folds only ASCII, as the
// Python's ASCII flag does.
const _ZONE_BRACKETED = /^\[[ \t\n\r\f\v]*zone[ \t\n\r\f\v]*:[ \t\n\r\f\v]*([^\]]*)\][ \t\n\r\f\v]*(.*)/is;
// Unbracketed only as one token (`zone:auth`): with a space after the colon, prose such as
// "zone: the auth module" would otherwise yield the label "the".
const _ZONE_BARE = /^zone:([^ \t\n\r\f\v]+)[ \t\n\r\f\v]*(.*)/is;

/**
 * The zone-label convention as the orchestrator reads it — on the generated fan-out agents
 * and in the status line's delegation guidance (C33).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function zoneConvention(data) {
  return data.zone_convention;
}

// Column counts for `parseDelegationEntries`: the current schema (timestamp, session_id,
// subagent, model, zone, description) and the legacy one (timestamp, subagent, model,
// description — no session/zone).
const _CURRENT_SCHEMA_COLUMNS = 6;
const _LEGACY_SCHEMA_COLUMNS = 4;

/**
 * Split a leading `[zone:LABEL]` marker off a delegation description.
 *
 * A marker only counts at the very start: `[zone:auth] check tokens` -> `["auth", "check
 * tokens"]`; tolerated alike (C33): any case, spaces inside the brackets, and the bare
 * one-token `zone:auth check tokens`. No marker -> `[null, <description stripped>]`.
 * @param {string} description
 * @returns {[string | null, string]}
 */
export function parseZone(description) {
  const text = _strip(description);
  const bracketed = _ZONE_BRACKETED.exec(text);
  if (bracketed) {
    return [_strip(bracketed[1]) || null, _strip(bracketed[2])];
  }
  const bare = _ZONE_BARE.exec(text);
  if (bare) {
    // C33: the unbracketed `zone:X …` spelling was observed live and used to leave the
    // whole fan-out unlabelled — an all-uncovered coverage map.
    return [_rstripChars(bare[1], ",;:") || null, _strip(bare[2])];
  }
  return [null, text];
}

/**
 * Warn on an unlabelled fan-out delegation in a session that is running a zone plan (C33).
 *
 * The observable sign that a zone plan is active is that earlier delegations of this session
 * carried zone labels. The auditor is exempt: an audit reads the fan-out, it is not a zone of it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Iterable<DelegationEntry>} entries
 * @param {string | null} sessionId
 * @param {string} subagent
 * @param {string | null} zone
 * @returns {string | null}
 */
export function unlabelledFanoutWarning(data, entries, sessionId, subagent, zone) {
  if (zone || !sessionId || !_agentByName(data).has(subagent) || subagent === "k_auditor") {
    return null;
  }
  /** @type {Set<string>} */ const zones = new Set();
  for (const entry of entries) {
    if (entry.sessionId === sessionId && entry.zone) {
      zones.add(entry.zone);
    }
  }
  const labelled = codePointSort([...zones]);
  if (labelled.length === 0) {
    return null;
  }
  return fill(data.unlabelled_fanout_warning, { subagent, labelled: labelled.join(", ") });
}

/**
 * One TSV line per subagent delegation; null for any other tool.
 *
 * Columns: `timestamp · session_id · subagent · model · zone · description`. The zone is
 * parsed off a leading `[zone:LABEL]` marker in the description (removed from the stored
 * description); `-` marks an absent session / model / zone. The model is the call's explicit
 * override if given, else `boundModel`. `sessionId` scopes a fan-out round for the
 * coverage-map assembler (C17).
 * @param {Json} toolName
 * @param {Json} toolInput
 * @param {string} timestamp
 * @param {Json} [sessionId]
 * @param {Json} [boundModel]
 * @returns {string | null}
 */
export function delegationLogLine(toolName, toolInput, timestamp, sessionId = null, boundModel = null) {
  if (toolName !== null && typeof toolName === "object" && !(toolName instanceof FloatValue)) {
    throw _pyError("TypeError", `unhashable type: '${_pyTypeName(toolName)}'`);
  }
  if (typeof toolName !== "string" || !_SUBAGENT_TOOLS.has(toolName)) {
    return null;
  }
  const subagent = _pyStr(_or(_get(toolInput, "subagent_type"), "-"));
  const model = _pyStr(_or(_or(_get(toolInput, "model"), boundModel), "-"));
  const rawDescription = _split(_pyStr(_or(_get(toolInput, "description"), ""))).join(" ");
  const [zone, description] = parseZone(rawDescription);
  return `${_pyStr(timestamp)}\t${_pyStr(_or(sessionId, "-"))}\t${subagent}\t${model}\t${zone || "-"}\t${description}`;
}

/** One parsed delegation-log row (schema: see `delegationLogLine`). */
export class DelegationEntry {
  /**
   * @param {string} timestamp
   * @param {string | null} sessionId
   * @param {string} subagent
   * @param {string | null} model
   * @param {string | null} zone
   * @param {string} description
   */
  constructor(timestamp, sessionId, subagent, model, zone, description) {
    this.timestamp = timestamp;
    this.sessionId = sessionId;
    this.subagent = subagent;
    this.model = model;
    this.zone = zone;
    this.description = description;
    Object.freeze(this);
  }
}

/** A stripped column, or null for an absent (`""`/`-`) one. */
function _dashToNone(/** @type {string} */ value) {
  const stripped = _strip(value);
  return stripped === "" || stripped === "-" ? null : stripped;
}

/**
 * Parse delegation-log lines into entries.
 *
 * Handles the current 6-column schema and the legacy 4-column one (no session/zone) so
 * a mixed local log still parses; lines with fewer than 4 fields are skipped.
 * @param {Iterable<string>} lines
 * @returns {DelegationEntry[]}
 */
export function parseDelegationEntries(lines) {
  /** @type {DelegationEntry[]} */ const entries = [];
  for (const raw of lines) {
    const line = _rstripChars(raw, "\n");
    if (!line) {
      continue;
    }
    const parts = line.split("\t");
    let ts, sid, subagent, model, zone, description;
    if (parts.length >= _CURRENT_SCHEMA_COLUMNS) {
      [ts, sid, subagent, model, zone] = parts;
      description = parts.slice(5).join("\t");
    } else if (parts.length >= _LEGACY_SCHEMA_COLUMNS) {
      // Legacy: timestamp · subagent · model · description (no session / zone).
      [ts, sid, subagent, model, zone] = [parts[0], "-", parts[1], parts[2], "-"];
      description = parts.slice(3).join("\t");
    } else {
      continue;
    }
    entries.push(
      new DelegationEntry(
        ts,
        _dashToNone(sid),
        _strip(subagent),
        _dashToNone(model),
        _dashToNone(zone),
        _strip(description),
      ),
    );
  }
  return entries;
}

// --------------------------------------------------------------------------------------
// C25 — the missed-gate forcing function: count a role's findings/options at the gate
// --------------------------------------------------------------------------------------

/**
 * The project's recorded binding, or `{}` when it is absent or unreadable.
 *
 * The hooks that need the live binding all read the same file the same way; the one
 * tolerated failure is a missing or malformed config, which means "not set up yet".
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {Record<string, Json>}
 */
export function readLocalConfig(data, projectRoot) {
  const path = _path(projectRoot, localConfigRel(data));
  if (!_isFile(path)) {
    return {};
  }
  let loaded;
  try {
    loaded = _parseKeepingFloats(_readText(path));
  } catch (error) {
    if (_isOSError(error) || error instanceof SyntaxError) {
      return {};
    }
    throw error;
  }
  return _isDict(loaded) ? loaded : {};
}

/** One role's count floor: which registry trigger it reads and what it counts. */
export class GateRule {
  /**
   * @param {string} role
   * @param {string} trigger
   * @param {string} noun
   * @param {string[]} headings section headings that open the counted material, lowercased prefixes
   * @param {string} anchor where the flow puts this gate, for the reason the hook hands back
   */
  constructor(role, trigger, noun, headings, anchor) {
    this.role = role;
    this.trigger = trigger;
    this.noun = noun;
    this.headings = Object.freeze([...headings]);
    this.anchor = anchor;
    Object.freeze(this);
  }
}

/**
 * The two floors `gate_triggers` carries. A role outside this list has no count gate.
 * @param {GateData} data the parsed `tools/model_routing/gate.json`
 * @returns {GateRule[]}
 */
export function gateRules(data) {
  return data.gate_rules.map((raw) => new GateRule(raw.role, raw.trigger, raw.noun, raw.headings, raw.anchor));
}

// A markdown heading (`## Findings`) or a whole line in bold (`**Findings**`) — both are how
// a role's output actually labels its sections; a bold line counts as the deepest level, so
// the next heading of any level closes it. Every pattern but the word one is `re.ASCII`.
const _MD_HEADING_RE = /^(#{1,6})[ \t\n\r\f\v]+(.*[^ \t\n\r\f\v])[ \t\n\r\f\v]*$/;
const _BOLD_HEADING_RE = /^\*\*(.+?)\*\*:?[ \t\n\r\f\v]*$/;
// A heading's words, letters only — Python's Unicode `[^\W\d_]`: letters and the non-decimal
// numbers (C98: a non-latin script yields its words like any other).
const _HEADING_WORD_RE = /[\p{L}\p{Nl}\p{No}]+/gu;
// A structural item: a bullet or a numbered item, at whatever depth it sits.
const _LIST_ITEM_RE = /^([ \t\n\r\f\v]*)(?:[-*+]|[0-9]+[.)])[ \t\n\r\f\v]+[^ \t\n\r\f\v]/;
// A table row that carries content — not the header separator `|---|---|`.
const _TABLE_SEPARATOR_RE = /^[ \t\n\r\f\v]*\|[ \t\n\r\f\v:|-]+\|[ \t\n\r\f\v]*$/;
const _GATE_MARKER_PREFIX = "gate-audit";

/**
 * `[level, text]` when `line` opens a section, else null. A bold line is level 7.
 * @param {string} line
 * @returns {[number, string] | null}
 */
function _heading(line) {
  const match = _MD_HEADING_RE.exec(line);
  if (match) {
    return [match[1].length, match[2]];
  }
  const bold = _BOLD_HEADING_RE.exec(line);
  return bold ? [7, bold[1]] : null;
}

/**
 * Whether a heading's text names the counted material (`Findings`, `3 findings`, `Options`).
 * @param {string} text
 * @param {readonly string[]} headings
 * @returns {boolean}
 */
function _opensSection(text, headings) {
  const words = text.toLowerCase().match(_HEADING_WORD_RE) ?? [];
  return words.slice(0, 3).some((word) => headings.some((heading) => word.startsWith(heading)));
}

/**
 * Structural items under every `rule` section of `message` (C25's counting rule).
 *
 * Counted: the section's outermost bullets and numbered items, and table rows with content.
 * An item indented deeper than the section's first one belongs to that item and is detail, a
 * table's header and separator are not rows, and prose is not an item. Sections close at the
 * next heading of the same or a higher level. The base indent is per section.
 * @param {string} message
 * @param {GateRule} rule
 * @returns {number}
 */
export function countGateItems(message, rule) {
  let total = 0;
  /** @type {number | null} */ let level = null;
  let inTable = false;
  /** @type {number | null} */ let base = null;
  for (const line of _splitlines(message)) {
    const heading = _heading(line);
    if (heading !== null) {
      const [opened, text] = heading;
      if (level !== null && opened <= level) {
        [level, inTable, base] = [null, false, null];
      }
      if (level === null && _opensSection(text, rule.headings)) {
        [level, base] = [opened, null];
      }
      continue;
    }
    if (level === null) {
      continue;
    }
    if (_lstrip(line).startsWith("|")) {
      if (_TABLE_SEPARATOR_RE.test(line)) {
        inTable = true; // the row above it was the header, not an item
        continue;
      }
      total += inTable ? 1 : 0;
      continue;
    }
    inTable = false;
    const item = _LIST_ITEM_RE.exec(line);
    if (item === null) {
      continue;
    }
    const indent = item[1].length;
    base = base === null ? indent : Math.min(base, indent);
    if (indent <= base) {
      total += 1;
    }
  }
  return total;
}

/**
 * `rule`'s count floor from the registry, or null when it is absent or not a count.
 * @param {Json} registry
 * @param {GateRule} rule
 * @returns {number | null}
 */
export function gateThreshold(registry, rule) {
  const triggers = _isDict(registry) ? _get(registry, "gate_triggers") : null;
  const value = _isDict(triggers) ? _get(triggers, rule.trigger) : null;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

/**
 * The count gate for a declared role, or null for a role that has none.
 * @param {GateData} data the parsed `tools/model_routing/gate.json`
 * @param {string | null} role
 * @returns {GateRule | null}
 */
export function gateRuleFor(data, role) {
  return gateRules(data).find((rule) => rule.role === role) ?? null;
}

/**
 * The one thing the gate asks for when a role's count reached its floor, else null.
 *
 * The floor is advisory in the flows — the orchestrator may skip it — so the request names
 * both live moves: run the audit, or say the skip out loud. What it does not allow is the
 * gate passing unmentioned, which is the whole of C25.
 * @param {GateData} gateData the parsed `tools/model_routing/gate.json`
 * @param {AgentsData} agentsData the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} config
 * @param {string | null} role
 * @param {string} message
 * @returns {string | null}
 */
export function gateAuditRequest(gateData, agentsData, registry, config, role, message) {
  const rule = gateRuleFor(gateData, role);
  const threshold = rule !== null ? gateThreshold(registry, rule) : null;
  if (rule === null || threshold === null) {
    return null;
  }
  const count = countGateItems(message, rule);
  if (count < threshold) {
    return null;
  }
  const auditor = boundModelFor(agentsData, config, "k_auditor");
  const model = auditor ? ` (model=${auditor})` : "";
  return (
    `[akmon gate] This turn carries ${count} ${rule.noun} as the ${rule.role} role, at or above the ` +
    `\`${rule.trigger}\` floor of ${threshold} — ${rule.anchor} routes an \`audit\` pass here. ` +
    `Before handing off: either delegate \`k_auditor\`${model} over the gate-pack ` +
    "(`tools/model_routing/gate_pack.py`) and fold its verdict in, or state in one line that you " +
    "are skipping the audit and why. The floor is advisory; passing it in silence is not."
  );
}

/**
 * The marker kind for one gate episode: role and count, so a changed count asks again.
 * @param {GateRule} rule
 * @param {number} count
 * @returns {string}
 */
export function gateAuditMarkerKind(rule, count) {
  return `${_GATE_MARKER_PREFIX}-${rule.role}-${count}`;
}

/**
 * Claim this gate episode for `sessionId`; false when it was already asked for.
 *
 * Keyed by role and count (C36 markers): the same material never blocks twice, while a later
 * turn that carries a different count is a new gate and is asked about again.
 * @param {GateData} gateData the parsed `tools/model_routing/gate.json`
 * @param {MarkersData} markersData the parsed `common/markers.json`
 * @param {string | null} role
 * @param {string} message
 * @param {string | null | undefined} sessionId
 * @param {{markerDir?: string | null}} [options]
 * @returns {boolean}
 */
export function gateAuditOnce(gateData, markersData, role, message, sessionId, { markerDir = null } = {}) {
  const rule = gateRuleFor(gateData, role);
  if (rule === null) {
    return false;
  }
  const kind = gateAuditMarkerKind(rule, countGateItems(message, rule));
  const claimed = claimDiagnosticMarker(markersData, kind, sessionId, { directory: markerDir });
  releaseDiagnosticMarkers(markersData, _GATE_MARKER_PREFIX, sessionId, { keepKind: kind, directory: markerDir });
  return claimed;
}
