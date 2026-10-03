/**
 * The one reader of `<AITNA_ROOT>/.akmon.toml` — the project's integration record.
 * The JavaScript twin of `common/record.py` (C103): the lenient reader degrades to the
 * same narrow line parser the Python fallback carries, so the corpus
 * (`meta/conformance/units/record.toml`) pins both twins on one tolerance. Stdlib plus
 * the vendored parser: `node:fs`, `node:path`, `node:util`, `smol-toml`.
 */

import fs from "node:fs";
import { basename, posix } from "node:path";
import { TextDecoder } from "node:util";

import { TomlError, parse } from "../vendor/smol-toml/dist/index.js";
import { aitnaRoot } from "./project_root.mjs";

const _PACKAGE_MODE = "package";

/** Whether `filePath` is a regular file (a directory named like one does not count). */
function _isFile(/** @type {string} */ filePath) {
  try {
    return fs.statSync(filePath).isFile();
  } catch {
    return false;
  }
}

/**
 * The record's bytes as text, refusing an invalid UTF-8 sequence instead of replacing it.
 *
 * `fs.readFileSync(path, "utf8")` never throws on bad bytes — it maps every undecodable
 * sequence to U+FFFD — so both readers would hand back a record value no disk holds where the
 * Python twin degrades (lenient) or raises (strict). `ignoreBOM` keeps a leading BOM in the
 * text as U+FEFF rather than stripping it, because that is where both readers look to keep the
 * asymmetry `meta/conformance/units/record.toml` pins: strict refuses a BOM, lenient drops one.
 *
 * @param {Buffer} bytes
 * @returns {string}
 * @throws {TypeError} when `bytes` are not valid UTF-8
 */
function _decodeUtf8(bytes) {
  return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
}

/** An empty table: null-prototype, the shape `parse` returns, so strict and lenient agree. */
function _emptyTable() {
  return Object.create(null);
}

/**
 * A TOML value with any trailing `# comment` removed, honouring quotes.
 *
 * `parse` does this for free; the narrow fallback in {@link readAkmonToml} must agree, so
 * the very shape BOOTSTRAP §C documents — `runner = "poetry run pytest"  # optional` —
 * strict and lenient parsing cannot produce different values. A `#` inside a quoted value
 * is data, not a comment: a quoted value ends at its closing quote and only a bare value
 * is cut at the first `#`.
 *
 * @param {string} value
 * @returns {string}
 */
export function stripInlineComment(value) {
  value = value.trim();
  const quote = value[0];
  if (quote !== '"' && quote !== "'") {
    return value.split("#")[0].trim();
  }
  // Scan to the *closing* quote rather than the next one: in a basic string a `\"` is an
  // escaped quote, so `indexOf` would end the value in the middle of it and hand back a
  // broken fragment. Literal strings (`'...'`) have no escapes at all, by TOML's definition.
  let index = 1;
  while (index < value.length) {
    if (quote === '"' && value[index] === "\\") {
      index += 2;
      continue;
    }
    if (value[index] === quote) {
      return value.slice(0, index + 1);
    }
    index += 1;
  }
  return value;
}

/**
 * The narrow fallback parser, moved rather than rewritten from `common/record.py`:
 * blanks and `#` lines are skipped, a bare `[name]` line opens a section, and every other
 * line is a `key = value` partitioned on the first `=`. A malformed header line is not a
 * section — it is read as a key=value line and its key keeps the `[`. Values become
 * strings with outer quotes stripped. A leading UTF-8 BOM is dropped before any line is
 * parsed, the way the Python fallback reads utf-8-sig.
 *
 * @param {string} text
 * @returns {Record<string, unknown>}
 */
function _lineParse(text) {
  const data = _emptyTable();
  /** @type {Record<string, unknown>} */
  let section = data;
  // A byte-order mark an editor left in front of the first key must not become part of
  // that key's name — the record would silently declare nothing (a "\uFEFFmount" key).
  if (text.charCodeAt(0) === 0xfeff) {
    text = text.slice(1);
  }
  for (const line of text.split(/\r\n|\r|\n/)) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("#")) {
      continue;
    }
    if (stripped.startsWith("[") && stripped.endsWith("]")) {
      const name = stripped.slice(1, -1).trim();
      // `setdefault`: a name already taken keeps whatever value holds it.
      section = name in data ? /** @type {Record<string, unknown>} */ (data[name]) : (data[name] = _emptyTable());
      continue;
    }
    const eq = stripped.indexOf("=");
    if (eq === -1) {
      continue;
    }
    const key = stripped.slice(0, eq).trim();
    // Two passes, as the Python's `strip('"').strip("'")`: outer double quotes, then outer singles.
    const value = stripInlineComment(stripped.slice(eq + 1)).replace(/^"+|"+$/g, "").replace(/^'+|'+$/g, "");
    section[key] = value;
  }
  return data;
}

/** The integration record exists but cannot be read as TOML (the twin of `RecordError`). */
export class RecordError extends Error {
  /**
   * @param {string} message
   */
  constructor(message) {
    super(message);
    this.name = "RecordError";
  }
}

/**
 * Read `<AITNA_ROOT>/.akmon.toml` (the integration record) into a nested object.
 *
 * Lenient on purpose: `{}` when the file is absent or unreadable — a failed read, or bytes
 * that are not UTF-8, never a value guessed at them; a malformed file falls through to the
 * line parser instead of raising and can come back non-empty, so a caller that needs to
 * *report* a broken record takes {@link readAkmonTomlStrict}. Values from the real parser
 * keep their TOML types; the fallback flattens them to strings.
 *
 * @param {string} filePath
 * @returns {Record<string, unknown>}
 */
export function readAkmonToml(filePath) {
  if (!_isFile(filePath)) {
    return _emptyTable();
  }
  let text;
  try {
    text = _decodeUtf8(fs.readFileSync(filePath));
  } catch {
    // Degrading rather than raising is the contract both twins carry: a hook consulting the
    // record must not abort a session over a file it only reads (C69, ADR-0009/D02). Refusing
    // the bytes here also keeps them from reaching `_lineParse`, which would otherwise read a
    // U+FFFD-substituted value back out as if the file said that.
    return _emptyTable();
  }
  try {
    return parse(text);
  } catch (exc) {
    // A malformed record degrades rather than raises: a hook consulting the record must
    // not abort a session over a file it only reads (C69, ADR-0009/D02), and the fallback
    // must agree with the real parser on inline comments.
    if (exc instanceof TomlError) {
      return _lineParse(text);
    }
    throw exc;
  }
}

/**
 * Read `<AITNA_ROOT>/.akmon.toml` strictly: `{}` when the file is absent, the parsed
 * table otherwise, and a {@link RecordError} when it cannot be read, is not valid UTF-8, is
 * BOM-prefixed, or does not parse — no lenient fallback here, unlike {@link readAkmonToml}.
 *
 * A caller that *applies* the record (the Python rule configuration, ADR 0014 §4, read to
 * switch rules on and off) needs a loud answer: the lenient fallback flattens a nested
 * table into strings, so a broken record would silently leave a rule on, or off.
 *
 * @param {string} filePath
 * @returns {Record<string, unknown>}
 */
export function readAkmonTomlStrict(filePath) {
  const name = basename(filePath);
  if (!_isFile(filePath)) {
    return _emptyTable();
  }
  let text;
  try {
    text = _decodeUtf8(fs.readFileSync(filePath));
  } catch (exc) {
    // A file that cannot be read and a file that cannot be decoded are different failures and
    // the message has to say which: the decoder is the only one that names the encoding, and
    // it does so as a `TypeError`. The Python twin's detail is its codec's own sentence — what
    // the twins share is a named error that says why, not the same words.
    const refused = exc instanceof TypeError ? "invalid UTF-8: " : "";
    const detail = exc instanceof Error ? exc.message : String(exc);
    throw new RecordError(`${name} cannot be read as TOML: ${refused}${detail}`);
  }
  // Refuse a BOM before the parser decides: `parse` (unlike `tomllib`) folds one in
  // silently, and TOML is BOM-free UTF-8. The byte is still here because `_decodeUtf8` sets
  // `ignoreBOM`; drop that flag and this check goes blind without anything going red.
  if (text.charCodeAt(0) === 0xfeff) {
    throw new RecordError(`${name} cannot be read as TOML: leading UTF-8 BOM (TOML is BOM-free UTF-8)`);
  }
  try {
    return parse(text);
  } catch (exc) {
    const detail =
      exc instanceof TomlError
        ? `parse failed at line ${exc.line}, column ${exc.column}: ${String(exc.message)
            .split("\n")[0]
            .replace(/^Invalid TOML document: /, "")}`
        : `parse failed: ${exc instanceof Error ? exc.message : String(exc)}`;
    throw new RecordError(`${name} cannot be read as TOML: ${detail}`);
  }
}

/**
 * The `mount` value this project records, or `null` when it records nothing.
 *
 * `null` rather than a default on purpose: a caller deciding whether the record *vetoes*
 * something must be able to tell "records submodule" from "records nothing at all" — a
 * project that predates the field records nothing.
 *
 * @param {string} projectRoot
 * @returns {string | null}
 */
export function recordedMount(projectRoot) {
  const value = readAkmonToml(posix.join(aitnaRoot(projectRoot), ".akmon.toml"))["mount"];
  return typeof value === "string" && value !== "" ? value : null;
}

/**
 * Whether the record declares mount mode `package` (ADR 0009 §4).
 *
 * Fail-safe, not fail-empty: an absent or unreadable record reads as `{}` and answers
 * `false`; a malformed one is parsed leniently instead — the line parser can still
 * resolve a `mount = "package"` line out of an otherwise-broken file.
 *
 * @param {string} projectRoot
 * @returns {boolean}
 */
export function recordsPackageMode(projectRoot) {
  return recordedMount(projectRoot) === _PACKAGE_MODE;
}
