/**
 * The JSON writer — the JavaScript answers to the forms of `json.dumps` akmon emits
 * (units/json.toml is the spec, Python's `json.dumps` the reference):
 *
 *   hook      — a hook's stdout document: one line, default separators
 *   wiring    — generated wiring files: indent 2 + trailing newline
 *   canonical — the registry content hash: sorted keys, compact separators
 *
 * `JSON.stringify` diverges from `ensure_ascii=True` in three ways this module closes: it
 * never escapes non-ASCII (or DEL / U+2028 / U+2029), it reorders integer-like keys, and it
 * spells a float by value (`1.0` and `1` are one number) — the mirror builds the string itself,
 * keeps a document's key order from its own source (a Map, never a plain object), and writes a
 * float with Python's `repr` algorithm: the shortest digits that read back exactly, laid out
 * fixed or exponential the way `float_repr` chooses.
 */

import { codePointSort } from "./sort.mjs";

/** An ordered table: a Map, so integer-like keys keep the order the source document had. */
/** @typedef {Map<string, JsonValue>} JsonTable */
/** One node of a JSON document, in the writer's own model. */
/** @typedef {string | number | boolean | null | FloatValue | JsonValue[] | JsonTable} JsonValue */

// JSON's own short escapes, then \uXXXX for every non-printable (code point < 0x20) and
// non-ASCII character — Python's ensure_ascii rule, with DEL and U+2028/U+2029 escaped too.
/** @type {Record<string, string>} */
const _ESCAPE = { '"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t" };

/**
 * Stringify one string value with the ensure_ascii rule: everything outside printable ASCII
 * (0x20–0x7e) takes a `\u` escape — control characters, DEL, U+2028/U+2029 and every
 * non-ASCII character alike, astral ones as a lowercase surrogate pair, the way Python does.
 * @param {string} value
 * @returns {string}
 */
function _string(value) {
  let out = '"';
  for (const ch of value) {
    const short = _ESCAPE[ch];
    if (short !== undefined) {
      out += short;
      continue;
    }
    // `?? 0` only feeds the checker: an iterated character is never empty.
    const cp = ch.codePointAt(0) ?? 0;
    if (cp > 0xffff) {
      const lo = cp - 0x10000;
      out +=
        `\\u${(0xd800 + (lo >> 10)).toString(16)}` +
        `\\u${(0xdc00 + (lo & 0x3ff)).toString(16)}`;
    } else if (cp < 0x20 || cp > 0x7e) {
      out += `\\u${cp.toString(16).padStart(4, "0")}`;
    } else {
      out += ch;
    }
  }
  return out + '"';
}

/**
 * The explicit float marker — the JS twin of Python's `float` type, which plain numbers
 * cannot express (JS has one number type, and `1.0 === 1`). A caller whose source document
 * distinguished the two (the unit probe, reading the written TOML) wraps its floats; the
 * real call sites carry only ints and strings today, so they never need it.
 */
export class FloatValue {
  /** @param {number} n */
  constructor(n) {
    this.n = n;
  }
}

/**
 * Spell one number the way `json.dumps` does: an integer spells itself; a float takes
 * Python's `repr` — the shortest digits that read back exactly, then the fixed-or-exponential
 * choice and the trailing `.0` that `float_repr` adds. The two engines agree on the shortest
 * digits (`String(n)` is the same round-trip algorithm Python's `repr` uses), so only the
 * *layout* has to be ported; `toFixed` would not, because it spells the binary value's exact
 * decimal expansion (`0.1` through 20 places is `0.10000000000000000555`, not `0.1`), and
 * `String(n)` alone loses the `.0` and spells exponents the JSON reader never sees in a
 * Python document.
 * @param {number | FloatValue} value
 * @returns {string}
 */
function _number(value) {
  if (value instanceof FloatValue) {
    return _floatRepr(value.n);
  }
  const n = value;
  if (Number.isSafeInteger(n)) {
    return String(n);
  }
  if (!Number.isInteger(n)) {
    return _floatRepr(n); // unmarked and not whole: only a float can be that
  }
  // A whole number beyond the safe range: `String` would switch to exponent notation, which
  // json.dumps never writes for an int, and it is already a value the reader held exactly.
  return BigInt(n).toString();
}

/**
 * Python's `float_repr` for one float (the `repr` `json.dumps` prints).
 *
 * The shortest digits that read back exactly are the same in both engines: `toExponential()`
 * with no precision is that algorithm, and it trims what `String()` would pad out (`String`
 * writes `15000000000000000` for 1.5e16, the digits are `15`). `decpt` is where the decimal
 * point sits relative to those digits — the value is `0.<digits> * 10 ** decpt`. The stdlib
 * prints exponentially below `1e-4` and above `1e16`, padding the exponent to two digits;
 * otherwise it writes the fixed form and adds the `.0` that marks the number a float rather
 * than an int.
 * @param {number} n
 * @returns {string}
 */
function _floatRepr(n) {
  if (Number.isNaN(n)) {
    return "NaN"; // json.dumps emits the JS literals for non-finite values, invalid JSON and all
  }
  if (!Number.isFinite(n)) {
    return n > 0 ? "Infinity" : "-Infinity";
  }
  if (n === 0) {
    return Object.is(n, -0) ? "-0.0" : "0.0";
  }
  const sign = n < 0 ? "-" : "";
  const [mantissa, power] = Math.abs(n).toExponential().split("e");
  const digits = mantissa.replace(".", "");
  const decpt = Number.parseInt(power, 10) + 1;
  if (decpt <= -4 || decpt > 16) {
    const exponent = decpt - 1;
    const fraction = digits.length > 1 ? `.${digits.slice(1)}` : "";
    const padded = String(Math.abs(exponent)).padStart(2, "0");
    return `${sign}${digits.charAt(0)}${fraction}e${exponent < 0 ? "-" : "+"}${padded}`;
  }
  if (decpt <= 0) {
    return `${sign}0.${"0".repeat(-decpt)}${digits}`;
  }
  if (decpt >= digits.length) {
    return `${sign}${digits}${"0".repeat(decpt - digits.length)}.0`;
  }
  return `${sign}${digits.slice(0, decpt)}.${digits.slice(decpt)}`;
}

/**
 * @param {JsonValue} value
 * @param {number} level the current indentation level (only for the wiring form)
 * @param {"hook" | "wiring" | "canonical"} form
 * @returns {string}
 */
function _value(value, level, form) {
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return _string(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (value instanceof FloatValue) {
    return _number(value);
  }
  if (typeof value === "number") {
    return _number(value);
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "[]";
    }
    if (form === "wiring") {
      const pad = "  ".repeat(level + 1);
      return (
        "[\n" + value.map((item) => pad + _value(item, level + 1, "wiring")).join(",\n") + "\n" + "  ".repeat(level) + "]"
      );
    }
    const sep = form === "canonical" ? "," : ", ";
    return "[" + value.map((item) => _value(item, 0, form)).join(sep) + "]";
  }
  // A Map, in its own key order: plain objects would reorder integer-like keys.
  /** @type {Map<string, JsonValue>} */ const obj = /** @type {Map<string, JsonValue>} */ (value);
  const child = (/** @type {string} */ key) => /** @type {JsonValue} */ (obj.get(key)); // a listed key is present
  let keys = [...obj.keys()];
  if (keys.length === 0) {
    return "{}";
  }
  if (form === "wiring") {
    const pad = "  ".repeat(level + 1);
    const body = keys.map((key) => `${pad}${_string(key)}: ${_value(child(key), level + 1, "wiring")}`);
    return "{\n" + body.join(",\n") + "\n" + "  ".repeat(level) + "}";
  }
  if (form === "canonical") {
    // sort_keys sorts keys as strings, character by character (code points, not numbers):
    // "10" < "2" < "b".
    keys = codePointSort(keys);
    return "{" + keys.map((key) => `${_string(key)}:${_value(child(key), 0, "canonical")}`).join(",") + "}";
  }
  return "{" + keys.map((key) => `${_string(key)}: ${_value(child(key), 0, "hook")}`).join(", ") + "}";
}

/**
 * Build the document from a plain object or array in its insertion order (the caller's
 * source order — a Map keeps it, and this is the only hop the corpus payload crosses).
 * @param {unknown} value
 * @returns {JsonValue}
 */
export function toDocument(value) {
  /** @param {unknown} v @returns {JsonValue} */
  const build = (v) => {
    if (v === null || typeof v !== "object") {
      return /** @type {JsonValue} */ (v);
    }
    if (v instanceof FloatValue) {
      return v;
    }
    if (v instanceof Map) {
      // A Map is the ordered document already: rebuild it (never Object.entries it — that
      // sees no own properties) with its children built the same way.
      /** @type {JsonTable} */
      const map = new Map();
      for (const [key, item] of v) {
        map.set(/** @type {string} */ (key), build(item));
      }
      return map;
    }
    if (Array.isArray(v)) {
      return v.map(build);
    }
    /** @type {JsonTable} */
    const map = new Map();
    for (const [key, item] of Object.entries(v)) {
      map.set(key, build(item));
    }
    return map;
  };
  return build(value);
}

/**
 * The hook's stdout document: one line, default separators.
 * @param {unknown} value
 * @returns {string}
 */
export function hookForm(value) {
  return _value(toDocument(value), 0, "hook");
}

/**
 * The generated wiring files: indent 2 + a trailing newline.
 * @param {unknown} value
 * @returns {string}
 */
export function wiringForm(value) {
  return _value(toDocument(value), 0, "wiring") + "\n";
}

/**
 * The registry content hash: sorted keys, compact separators.
 * @param {unknown} value
 * @returns {string}
 */
export function canonicalForm(value) {
  return _value(toDocument(value), 0, "canonical");
}
