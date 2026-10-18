/**
 * Python's `json.loads` and `sys.stdin.read()` for the hook payloads (C104) — the one copy both
 * vendor adapters read their input through. Stdlib only: `node:fs`, plus `pyvalue.mjs`.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - `json.loads` accepts `NaN`, `Infinity` and `-Infinity` and refuses an integer literal of more
 *   than 4300 digits with a plain `ValueError`; `JSON.parse` does neither, so `jsonLoads` falls
 *   back to a scanner of Python's grammar when the text could hold one of them. A number is a
 *   plain JS number (`1.0` is `1`, an integer beyond 2**53 is inexact): a payload field is only
 *   ever tested for type and truthiness, or spelled by `str()` into a marker name, never into
 *   the document;
 * - Python's C scanner raises `RecursionError` (not a `ValueError`: a crash, not `{}`) past 9997
 *   levels on 3.12, the floor (M143; 3.13 takes 9998, 3.14 is bounded by the stack, far deeper);
 *   `JSON.parse` has no limit, so a long text is measured first. The measure ignores syntax — a text broken before that depth is
 *   a `RecursionError` here and a `JSONDecodeError` there;
 * - `sys.stdin.read()` is a strict UTF-8 decode of every byte (a malformed one raises
 *   `UnicodeDecodeError`, a `ValueError`) and keeps a BOM (which `json` then refuses). Not
 *   reproduced: Python under the C locale reads stdin with `surrogateescape` instead, and a closed
 *   descriptor 0 is `sys.stdin is None` (`AttributeError`) there, while node reopens it on
 *   `/dev/null` before any script runs, so it reads as an empty payload here.
 */

import fs from "node:fs";

import { decodeUtf8, pyError } from "./pyvalue.mjs";

/** The cause of a text that is not JSON — Python's `json.JSONDecodeError`, a `ValueError`. */
export class JSONDecodeError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "JSONDecodeError";
  }
}

/** The deepest nesting Python's C scanner takes on 3.12, the floor (M143); one level more is `RecursionError`. */
const _MAX_NESTING = 9997;
// `sys.int_info.default_max_str_digits`: an integer literal with more digits than this is refused.
const _MAX_INT_DIGITS = 4300;
const _PYTHON_ONLY = /NaN|Infinity|[0-9]{4301}/;
const _LONG_DIGITS = /[0-9]{4301}/;
const _JSON_NUMBER = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/y;
// JSON forbids a raw control character inside a string; that is what the class excludes.
// eslint-disable-next-line no-control-regex
const _JSON_STRING = /"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/y;
const _JSON_SPACE = /[ \t\n\r]*/y;

/** A scanner of Python's JSON grammar: standard JSON plus `NaN`, `Infinity` and `-Infinity`. */
class _Scanner {
  /** @param {string} text */
  constructor(text) {
    this.text = text;
    this.at = 0;
  }

  /** @param {string} message @returns {JSONDecodeError} */
  fail(message) {
    return new JSONDecodeError(`${message}: char ${this.at}`);
  }

  skipSpace() {
    _JSON_SPACE.lastIndex = this.at;
    _JSON_SPACE.exec(this.text);
    this.at = _JSON_SPACE.lastIndex;
  }

  /**
   * @param {string} literal
   * @returns {boolean}
   */
  takes(literal) {
    if (this.text.startsWith(literal, this.at)) {
      this.at += literal.length;
      return true;
    }
    return false;
  }

  /** @returns {any} */
  document() {
    this.skipSpace();
    const value = this.value();
    this.skipSpace();
    if (this.at !== this.text.length) {
      throw this.fail("Extra data");
    }
    return value;
  }

  /** @returns {any} */
  value() {
    const char = this.text[this.at];
    if (char === '"') {
      return this.string();
    }
    if (char === "{") {
      return this.object();
    }
    if (char === "[") {
      return this.array();
    }
    const literals = /** @type {[string, any][]} */ ([
      ["null", null],
      ["true", true],
      ["false", false],
      ["NaN", NaN],
      ["Infinity", Infinity],
      ["-Infinity", -Infinity],
    ]);
    for (const [literal, value] of literals) {
      if (this.takes(literal)) {
        return value;
      }
    }
    return this.number();
  }

  /** @returns {number} */
  number() {
    _JSON_NUMBER.lastIndex = this.at;
    const match = _JSON_NUMBER.exec(this.text);
    if (match === null) {
      throw this.fail("Expecting value");
    }
    const [literal, fraction, exponent] = match;
    if (fraction === undefined && exponent === undefined) {
      const digits = literal.startsWith("-") ? literal.length - 1 : literal.length;
      if (digits > _MAX_INT_DIGITS) {
        throw pyError(
          "ValueError",
          `Exceeds the limit (${_MAX_INT_DIGITS} digits) for integer string conversion: value has ${digits} digits`,
        );
      }
    }
    this.at += literal.length;
    return Number(literal);
  }

  /** @returns {string} */
  string() {
    _JSON_STRING.lastIndex = this.at;
    const match = _JSON_STRING.exec(this.text);
    if (match === null) {
      throw this.fail("Unterminated string or bad escape");
    }
    this.at += match[0].length;
    return JSON.parse(match[0]);
  }

  /** @returns {Record<string, any>} */
  object() {
    /** @type {Record<string, any>} */
    const table = {};
    this.at += 1;
    this.skipSpace();
    if (this.takes("}")) {
      return table;
    }
    for (;;) {
      if (this.text[this.at] !== '"') {
        throw this.fail("Expecting property name enclosed in double quotes");
      }
      const key = this.string();
      this.skipSpace();
      if (!this.takes(":")) {
        throw this.fail("Expecting ':' delimiter");
      }
      this.skipSpace();
      // An own data property even for `__proto__`, as a dict stores it.
      Object.defineProperty(table, key, {
        value: this.value(),
        writable: true,
        enumerable: true,
        configurable: true,
      });
      this.skipSpace();
      if (this.takes("}")) {
        return table;
      }
      if (!this.takes(",")) {
        throw this.fail("Expecting ',' delimiter");
      }
      this.skipSpace();
    }
  }

  /** @returns {any[]} */
  array() {
    /** @type {any[]} */
    const items = [];
    this.at += 1;
    this.skipSpace();
    if (this.takes("]")) {
      return items;
    }
    for (;;) {
      items.push(this.value());
      this.skipSpace();
      if (this.takes("]")) {
        return items;
      }
      if (!this.takes(",")) {
        throw this.fail("Expecting ',' delimiter");
      }
      this.skipSpace();
    }
  }
}

/**
 * The deepest bracket nesting of `text`, strings skipped; counting stops once past the limit.
 * @param {string} text
 * @returns {number}
 */
function _nesting(text) {
  let depth = 0;
  let deepest = 0;
  for (let i = 0; i < text.length && deepest <= _MAX_NESTING; i++) {
    const char = text[i];
    if (char === '"') {
      for (i += 1; i < text.length && text[i] !== '"'; i++) {
        if (text[i] === "\\") {
          i += 1;
        }
      }
    } else if (char === "[" || char === "{") {
      depth += 1;
      deepest = Math.max(deepest, depth);
    } else if (char === "]" || char === "}") {
      depth -= 1;
    }
  }
  return deepest;
}

/**
 * Python's `json.loads(text)`: the parsed value, or `JSONDecodeError`. The common case is
 * `JSON.parse`; the scanner above runs only for a text that fails it while holding a literal
 * Python accepts, or that holds a digit run long enough to hit the integer limit.
 * @param {string} text
 * @returns {any}
 * @throws {JSONDecodeError} for text that is not JSON; `ValueError` for an integer over the digit
 *   limit; `RecursionError` for nesting past what the interpreter allows
 */
export function jsonLoads(text) {
  if (text.length > _MAX_NESTING && _nesting(text) > _MAX_NESTING) {
    throw pyError("RecursionError", "maximum recursion depth exceeded while decoding a JSON document");
  }
  /** @type {any} */
  let value;
  try {
    value = JSON.parse(text);
  } catch (error) {
    if (!_PYTHON_ONLY.test(text)) {
      throw new JSONDecodeError(error instanceof Error ? error.message : String(error));
    }
    return new _Scanner(text).document();
  }
  return _LONG_DIGITS.test(text) ? new _Scanner(text).document() : value;
}

/**
 * Every byte of stdin: `sys.stdin.read()` before the decode. A pipe the parent has not written
 * yet is `EAGAIN` on a non-blocking descriptor — wait a millisecond and ask again.
 * @returns {Buffer}
 */
export function readStdinBytes() {
  /** @type {Buffer[]} */
  const chunks = [];
  const block = Buffer.allocUnsafe(65536);
  for (;;) {
    let count;
    try {
      count = fs.readSync(0, block, 0, block.length, null);
    } catch (error) {
      const code = /** @type {{code?: string}} */ (error).code;
      if (code === "EAGAIN") {
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 1);
        continue;
      }
      if (code === "EOF") {
        break;
      }
      throw error;
    }
    if (count === 0) {
      break;
    }
    chunks.push(Buffer.from(block.subarray(0, count)));
  }
  return Buffer.concat(chunks);
}

/**
 * Every byte of stdin as strict UTF-8: `sys.stdin.read()`.
 * @returns {string}
 * @throws {Error} named `UnicodeDecodeError` for a malformed byte sequence
 */
export function readStdinText() {
  return decodeUtf8(readStdinBytes());
}
