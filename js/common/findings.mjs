/**
 * The shared finding envelope every akmon check speaks — `severity · code · message · target ·
 * fix`. The JavaScript twin of `common/findings.py` (C105, ADR 0020 D01); its docstring owns the
 * five fields and why each is load-bearing, and `meta/conformance/units/findings.toml` is the
 * spec both must pass. Stdlib only: `node:fs`, `node:url` and the two sibling twins.
 *
 * Data (the C102/C103 convention): the severity vocabulary, the retired-code record and the
 * render skeleton are `common/findings.json`, which the Python module opens beside itself. A
 * carrier that builds many findings calls {@link readFindingsData} once and passes the result to
 * each; a call without it reads the file itself (`data` is the trailing, optional parameter, as in
 * the Python signatures).
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - `Finding` is built from ONE options object, not positionally (a JavaScript class has no
 *   keyword arguments); a field the object leaves out is the `TypeError` Python raises for a
 *   missing argument, spelled the way Python spells it;
 * - a `repr()` in a message goes through `pyRepr` (`'x'` quoting, `None`, `True`);
 * - Python's `\s` is `re.ASCII` there and `[ \t\n\r\f\v]` here, so the one-sentence rule sees the
 *   same whitespace on both sides;
 * - `str.strip()` has Unicode semantics, so the emptiness test is `pyStrip`.
 */

import { fileURLToPath } from "node:url";

import { fill, read } from "./jsondata.mjs";
import { pyError, pyRepr, pyStrip } from "./pyvalue.mjs";

/** A dotted slug: at least two lowercase ASCII segments, single hyphens only inside them. */
export const CODE_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$/;

/**
 * The shape of `common/findings.json` — the data file is the owner of these keys.
 * @typedef {object} FindingsData
 * @property {string[]} severities
 * @property {string[]} retired_codes
 * @property {{head: string, head_with_target: string, line: string}} render
 */

/**
 * The severity vocabulary, the retired-code record and the render skeleton (`findings.json`).
 *
 * Read once by whoever builds or prints a report and passed down; a function called without it
 * reads the file itself.
 *
 * @returns {FindingsData}
 */
export function readFindingsData() {
  return /** @type {FindingsData} */ (read(fileURLToPath(new URL("../../common/findings.json", import.meta.url))));
}

/** The data a caller passed, or the file's when it passed none. */
function _orRead(/** @type {FindingsData | null | undefined} */ data) {
  return data ?? readFindingsData();
}

/**
 * Codes spent by checks that no longer exist.
 *
 * A slug listed here may never be issued again, so a consumer who greps their history is never
 * shown two different rules under one name. Empty while no check has been removed; appending on
 * deletion is process-owned (F14).
 *
 * @param {FindingsData | null} [data]
 * @returns {ReadonlySet<string>}
 */
export function retiredCodes(data = null) {
  return new Set(_orRead(data).retired_codes);
}

/**
 * The closed severity vocabulary, ordered least to most severe (`findings.json`).
 *
 * @param {FindingsData | null} [data]
 * @returns {readonly string[]}
 */
export function severities(data = null) {
  return Object.freeze([..._orRead(data).severities]);
}

// A sentence terminator followed by more text — the mechanical half of "one sentence".
// The uppercase lookahead catches the compact but still multi-sentence `Do this.Then that.`
// form without rejecting dots inside ordinary paths such as `meta/CONCEPT.md`. `\s` and `\S` are
// spelled out: the Python twin's are `re.ASCII`, and a JavaScript `\s` also matches U+00A0 and
// every other Unicode space.
const _SECOND_SENTENCE_RE = /[.!?](?:[ \t\n\r\f\v]+[^ \t\n\r\f\v]|(?=[A-Z]))/;

// `str.splitlines` recognizes more separators than LF/CR. Any one of them would turn the
// canonical one-record-per-line rendering into multiple apparent findings.
// eslint-disable-next-line no-control-regex
const _LINE_SEPARATOR_RE = /[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/;
// The same class for `replace`: a global pattern keeps `lastIndex`, which would make `test` stateful.
const _LINE_SEPARATORS_RE = new RegExp(_LINE_SEPARATOR_RE.source, "g");
const _LINE_SEPARATOR_ESCAPES = /** @type {Record<string, string>} */ ({
  "\n": "\\n",
  "\r": "\\r",
  "\v": "\\v",
  "\f": "\\f",
  "\x1c": "\\u001c",
  "\x1d": "\\u001d",
  "\x1e": "\\u001e",
  "\x85": "\\u0085",
  "\u2028": "\\u2028",
  "\u2029": "\\u2029",
});

/**
 * Escape logical line separators while preserving every other Unicode character.
 *
 * @param {string} value
 * @returns {string}
 */
export function lineSafe(value) {
  return value.replace(_LINE_SEPARATORS_RE, (separator) => _LINE_SEPARATOR_ESCAPES[separator]);
}

/**
 * The five fields of a {@link Finding}, as the options object its constructor takes; `data` is
 * the parsed `findings.json` the validation checks against.
 * @typedef {object} FindingFields
 * @property {string} severity
 * @property {string} code
 * @property {string} message
 * @property {string} target
 * @property {string} fix
 * @property {FindingsData | null} [data]
 */

const _FIELDS = ["severity", "code", "message", "target", "fix"];

/** `'a'`, `'a' and 'b'`, `'a', 'b', and 'c'` — the list Python's `TypeError` for missing arguments prints. */
function _quotedList(/** @type {string[]} */ names) {
  const quoted = names.map((name) => `'${name}'`);
  if (quoted.length <= 2) {
    return quoted.join(" and ");
  }
  return `${quoted.slice(0, -1).join(", ")}, and ${quoted[quoted.length - 1]}`;
}

/** One observation from one check. Invalid combinations never construct. */
export class Finding {
  /**
   * `data` is not a field: a carrier that builds many findings reads it once and passes it to
   * each; without it the construction reads the file itself.
   *
   * @param {FindingFields} fields
   * @throws {Error} `ValueError` for a field that breaks the envelope, `TypeError` for an
   *   argument the options object leaves out or adds
   */
  constructor(fields) {
    const unexpected = Object.keys(fields).filter((key) => key !== "data" && !_FIELDS.includes(key));
    if (unexpected.length > 0) {
      throw pyError("TypeError", `Finding.__init__() got an unexpected keyword argument '${unexpected[0]}'`);
    }
    const missing = _FIELDS.filter((key) => fields[/** @type {keyof FindingFields} */ (key)] === undefined);
    if (missing.length > 0) {
      const noun = missing.length === 1 ? "argument" : "arguments";
      throw pyError(
        "TypeError",
        `Finding.__init__() missing ${missing.length} required positional ${noun}: ${_quotedList(missing)}`,
      );
    }
    const { severity, code, message, target, fix } = fields;
    const data = _orRead(fields.data);
    /** @readonly */ this.severity = severity;
    /** @readonly */ this.code = code;
    /** @readonly */ this.message = message;
    /** @readonly */ this.target = target;
    /** @readonly */ this.fix = fix;
    this._validateSeverity(data);
    this._validateCode(data);
    this._validateMessage();
    this._validateTarget();
    this._validateFix();
    Object.freeze(this);
  }

  /** @param {FindingsData} data */
  _validateSeverity(data) {
    if (!severities(data).includes(this.severity)) {
      throw pyError(
        "ValueError",
        `severity must be one of ${severities(data).join(" | ")}, got ${pyRepr(this.severity)}`,
      );
    }
  }

  /** @param {FindingsData} data */
  _validateCode(data) {
    if (typeof this.code !== "string" || !CODE_RE.test(this.code)) {
      throw pyError("ValueError", `code must be a dotted slug like 'area.rule', got ${pyRepr(this.code)}`);
    }
    if (retiredCodes(data).has(this.code)) {
      throw pyError("ValueError", `code ${pyRepr(this.code)} is retired and must not be reused by a live check`);
    }
  }

  _validateMessage() {
    if (typeof this.message !== "string" || pyStrip(this.message) === "") {
      throw pyError("ValueError", `message must be non-empty, got ${pyRepr(this.message)}`);
    }
    if (_LINE_SEPARATOR_RE.test(this.message)) {
      throw pyError("ValueError", `message must be one line, got ${pyRepr(this.message)}`);
    }
  }

  _validateTarget() {
    if (typeof this.target !== "string") {
      throw pyError("ValueError", `target must be a string (possibly empty), got ${pyRepr(this.target)}`);
    }
    if (_LINE_SEPARATOR_RE.test(this.target)) {
      throw pyError("ValueError", `target must be one line, got ${pyRepr(this.target)}`);
    }
  }

  _validateFix() {
    if (typeof this.fix !== "string" || pyStrip(this.fix) === "") {
      throw pyError("ValueError", `fix is required and must be non-empty, got ${pyRepr(this.fix)}`);
    }
    if (_LINE_SEPARATOR_RE.test(this.fix)) {
      throw pyError("ValueError", `fix must be one line, got ${pyRepr(this.fix)}`);
    }
    if (_SECOND_SENTENCE_RE.test(this.fix)) {
      throw pyError("ValueError", `fix must be one sentence, got ${pyRepr(this.fix)}`);
    }
  }

  /**
   * The sole canonical serialization: a JSON-safe mapping of exactly the five fields.
   *
   * Deterministic and non-mutating. There is no `level` key and no alias for one.
   *
   * @returns {{severity: string, code: string, message: string, target: string, fix: string}}
   */
  toDict() {
    return { severity: this.severity, code: this.code, message: this.message, target: this.target, fix: this.fix };
  }
}

/**
 * `SEVERITY code target: message → fix`; the `target` slot collapses when empty.
 *
 * The slot order and the arrow come from the data file's `render` skeleton; the upper-cased
 * severity and the conditional target are code-side choices.
 *
 * @param {Finding} finding
 * @param {FindingsData | null} [data]
 * @returns {string}
 */
export function render(finding, data = null) {
  const skeleton = _orRead(data).render;
  let head = fill(skeleton.head, { severity: finding.severity.toUpperCase(), code: finding.code });
  if (finding.target) {
    head = fill(skeleton.head_with_target, { head, target: finding.target });
  }
  return fill(skeleton.line, { head, message: finding.message, fix: finding.fix });
}

/**
 * Print each finding in canonical form; `quiet` drops the `ok` ones.
 *
 * One report, one read of `findings.json`: the skeleton is read here and passed to every line.
 *
 * @param {Iterable<Finding>} findings
 * @param {{quiet?: boolean}} [options]
 */
export function printFindings(findings, { quiet = false } = {}) {
  const data = readFindingsData();
  for (const finding of findings) {
    if (quiet && finding.severity === "ok") {
      continue;
    }
    process.stdout.write(`${render(finding, data)}\n`);
  }
}

/**
 * The shared exit contract: errors fail; warnings fail only under `--strict`.
 *
 * @param {readonly Finding[]} findings
 * @param {{strict?: boolean}} [options]
 * @returns {number}
 */
export function exitCode(findings, { strict = false } = {}) {
  const present = new Set(findings.map((finding) => finding.severity));
  return present.has("error") || (strict && present.has("warn")) ? 1 : 0;
}
