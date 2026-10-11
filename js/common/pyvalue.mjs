/**
 * The Python semantics the JavaScript twins lean on — value semantics for a parsed JSON document
 * (truthiness, `==`, `str()`/`repr()`, `.get` on a non-dict, `in`), the no-argument `str`
 * whitespace methods, and the `pathlib` file operations (strict UTF-8 text, `is_file`/`is_dir`).
 * Moved out of `tools/model_routing/routing.mjs` (C104 pass 2) so that `hooks/hook_core.mjs` can
 * share them without loading the 3000-line routing module on every hook launch.
 *
 * A Python exception is an `Error` carrying the Python class name in `name` (`pyError`): the
 * hook crash handler prints `type(exc).__name__`, so a class name is owner-visible text.
 * Stdlib only: `node:fs`, `node:util`.
 */

import fs from "node:fs";

import { FloatValue, hookForm } from "./json_writer.mjs";

/** A parsed JSON document: any JSON value. */
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

// `int(str)` strips the same set minus U+001C–U+001F, which it refuses as part of the literal.
const _INT_SPACE = "\\t\\n\\v\\f\\r\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const _INT_SURROUNDING_SPACE = new RegExp(`^[${_INT_SPACE}]+|[${_INT_SPACE}]+$`, "g");
// `sys.int_info.default_max_str_digits`: `int(str)` refuses a longer decimal literal (3.11+).
const _INT_MAX_STR_DIGITS = 4300;

/** The value of one Unicode decimal digit: Nd digits come in contiguous runs of 0–9. */
function _digitValue(/** @type {number} */ cp) {
  let start = cp;
  while (start > 0 && /^\p{Nd}$/u.test(String.fromCodePoint(start - 1))) {
    start -= 1;
  }
  return (cp - start) % 10;
}

/**
 * The sign and the ASCII digits of the base-10 literal `int(value)` reads from a string:
 * surrounding whitespace (U+001C–U+001F excepted), a sign, any script's decimal digits and
 * single underscores between digits.
 * @param {string} value
 * @returns {{sign: number, digits: string}}
 */
function _intLiteral(value) {
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
  if (digits.length > _INT_MAX_STR_DIGITS) {
    throw _pyError(
      "ValueError",
      `Exceeds the limit (${_INT_MAX_STR_DIGITS} digits) for integer string conversion: value has ${digits.length} digits`,
    );
  }
  return { sign, digits };
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
  const { sign, digits } = _intLiteral(value);
  return sign * Number(digits);
}

/**
 * `int(value)` without the double's limit — the same rules as {@link _pyInt}, the answer exact.
 * @param {unknown} value
 * @returns {bigint}
 */
function _pyIntBig(value) {
  if (typeof value === "string") {
    const { sign, digits } = _intLiteral(value);
    return BigInt(sign) * BigInt(digits);
  }
  return BigInt(_pyInt(value));
}

/**
 * Python's `float(text)` for a string: surrounding whitespace (`int`'s set, U+001C–U+001F excepted), a
 * sign, any script's decimal digits, `inf`/`infinity`/`nan` in any case, and single underscores
 * between digits. A literal beyond the double's range is `inf`, not an error.
 * @param {string} text
 * @returns {number}
 */
function _pyFloatFromString(text) {
  const invalid = () => _pyError("ValueError", `could not convert string to float: ${_strRepr(text)}`);
  const characters = Array.from(text.replace(_INT_SURROUNDING_SPACE, ""), (ch) =>
    /^\p{Nd}$/u.test(ch) ? String(_digitValue(ch.codePointAt(0) ?? 0)) : ch,
  );
  let body = "";
  characters.forEach((ch, i) => {
    if (ch !== "_") {
      body += ch;
    } else if (!/^[0-9]$/.test(characters[i - 1] ?? "") || !/^[0-9]$/.test(characters[i + 1] ?? "")) {
      throw invalid();
    }
  });
  const special = /^([+-]?)(inf|infinity|nan)$/i.exec(body);
  if (special !== null) {
    if (special[2].toLowerCase() === "nan") {
      return NaN;
    }
    return special[1] === "-" ? -Infinity : Infinity;
  }
  if (!/^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$/.test(body)) {
    throw invalid();
  }
  return Number(body);
}

/**
 * Python's `float(value)` for a JSON value: a number is itself (a bool is 0/1), a string parses
 * as {@link _pyFloatFromString} reads it.
 * @param {unknown} value
 * @returns {number}
 */
function _pyFloat(value) {
  if (typeof value === "boolean") {
    return value ? 1 : 0;
  }
  const n = _numeric(value);
  if (n !== null) {
    return n;
  }
  if (typeof value !== "string") {
    throw _pyError(
      "TypeError",
      `float() argument must be a string or a real number, not '${_pyTypeName(value)}'`,
    );
  }
  return _pyFloatFromString(value);
}

/** `text.lower()` — which raises on a non-string, as the attribute lookup does. */
function _lower(/** @type {unknown} */ text) {
  if (typeof text !== "string") {
    throw _pyError("AttributeError", `'${_pyTypeName(text)}' object has no attribute 'lower'`);
  }
  return text.toLowerCase();
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
 * @param {string | Buffer} path a path, or the bytes of one that no string spells (`os.fsencode`)
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
const _UTF8 = new globalThis.TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

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
function _readText(/** @type {string | Buffer} */ path) {
  return _decode(fs.readFileSync(path)).replace(/\r\n?/g, "\n");
}

/** `Path.write_text(text, encoding="utf-8")` — a lone surrogate raises before the file opens. */
function _writeText(/** @type {string | Buffer} */ path, /** @type {string} */ text) {
  fs.writeFileSync(path, _utf8(text));
}

/** `Path.unlink(missing_ok=True)`. */
function _unlinkMissingOk(/** @type {string | Buffer} */ path) {
  try {
    fs.unlinkSync(path);
  } catch (error) {
    if (/** @type {{code?: string}} */ (error).code !== "ENOENT") {
      throw error;
    }
  }
}

// The Python `OSError` subclass a failed system call raises, by errno name; any other errno is
// the base class. Only the ones a hook's file, process and pipe operations can hit.
const _OS_ERROR_CLASSES = {
  ENOENT: "FileNotFoundError",
  EEXIST: "FileExistsError",
  EACCES: "PermissionError",
  EPERM: "PermissionError",
  EISDIR: "IsADirectoryError",
  ENOTDIR: "NotADirectoryError",
  EPIPE: "BrokenPipeError",
  ESRCH: "ProcessLookupError",
  ECHILD: "ChildProcessError",
  EINTR: "InterruptedError",
  ETIMEDOUT: "TimeoutError",
  EAGAIN: "BlockingIOError",
  EWOULDBLOCK: "BlockingIOError",
};

/**
 * `type(exc).__name__` for whatever was thrown: the crash handlers print it, so it is owner-visible
 * text. A Node system error (`code: "ENOENT"` with a numeric `errno`) is the `OSError` subclass
 * Python raises for that errno; any other `Error` carries its Python class in `name` (`pyError`,
 * or a class that sets `name`), which is also what JavaScript's own `TypeError` etc. already say.
 * Two Node errors are named for their Python twin: `JSON.parse`'s `SyntaxError` is
 * `JSONDecodeError`, and the argument error for a NUL in a path is `ValueError`.
 * @param {unknown} error
 * @returns {string}
 */
export function exceptionClassName(error) {
  if (!(error instanceof Error)) {
    return "Exception";
  }
  const { code, errno } = /** @type {{code?: unknown, errno?: unknown}} */ (error);
  if (typeof code === "string" && typeof errno === "number") {
    return Object.hasOwn(_OS_ERROR_CLASSES, code) ? _OS_ERROR_CLASSES[/** @type {keyof typeof _OS_ERROR_CLASSES} */ (code)] : "OSError";
  }
  // A `SyntaxError` in this tree is `JSON.parse` refusing a text: Python's `json.JSONDecodeError`.
  if (error instanceof SyntaxError) {
    return "JSONDecodeError";
  }
  // A NUL in a path is `ValueError("embedded null byte")` in Python; Node refuses the argument.
  if (code === "ERR_INVALID_ARG_VALUE" && error.message.includes("null bytes")) {
    return "ValueError";
  }
  return error.name;
}

export {
  _pyError as pyError,
  _isDict as isDict,
  _pyTypeName as pyTypeName,
  _get as dictGet,
  _item as dictItem,
  _set as dictSet,
  _truthy as truthy,
  _numeric as pyNumeric,
  _pyEq as pyEq,
  _iterate as pyIterate,
  _contains as pyContains,
  _index as seqIndex,
  _last as seqLast,
  _floatRepr as floatRepr,
  _strRepr as strRepr,
  _pyRepr as pyRepr,
  _pyStr as pyStr,
  _pyInt as pyInt,
  _pyIntBig as pyIntBig,
  _pyFloat as pyFloat,
  _join as pyJoin,
  _split as pySplit,
  _lstrip as pyLstrip,
  _strip as pyStrip,
  _rstripChars as rstripChars,
  _splitlines as pySplitlines,
  _len as pyLen,
  _lower as pyLower,
  _utf8 as encodeUtf8,
  _path as pyPath,
  _isOSError as isOSError,
  _stat as pyStat,
  _isFile as isFile,
  _isDir as isDir,
  _decode as decodeUtf8,
  _readText as readText,
  _writeText as writeText,
  _unlinkMissingOk as unlinkMissingOk,
};
