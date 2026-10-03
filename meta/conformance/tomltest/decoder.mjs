#!/usr/bin/env node
/**
 * toml-test v2.2.0 decoder adapter for the vendored smol-toml (ADR 0020 D04, C103).
 *
 * Contract (toml-test README, "JSON description" section): read the TOML document on
 * stdin; on success print the tagged JSON encoding to stdout and exit 0, on parse
 * failure print the error to stderr and exit 1. TOML values become objects of the form
 * `{"type": "<tag>", "value": "<string>"}` with tags string, integer, float, bool,
 * datetime, datetime-local, date-local and time-local; tables become plain objects and
 * arrays plain JSON arrays.
 *
 * The adapter pins the suite to the `files-toml-1.0.0` subset — the TOML version the
 * Python floor (`tomllib`) reads — so it applies the small set of 1.0.0 strictness the
 * 1.1.0-capable smol-toml parser tolerates by design (the upstream README footnotes):
 * stdin is UTF-8-decoded with `fatal: true`; the raw text is pre-scanned to reject
 * `\x` byte escapes, line breaks at an inline table's own level, a trailing comma
 * before an inline table's `}` (arrays keep their 1.0.0-allowed one), and date/time
 * literals whose parts are out of range, whose calendar date does not exist, or whose
 * time part omits its seconds (mandatory in 1.0.0); integers are parsed with
 * `integersAsBigInt` so the integer/float distinction and magnitudes beyond 53 bits
 * survive. Everything else semantic is smol-toml's.
 *
 * Value normalization against the suite's expected spelling is mechanical only:
 * - smol-toml's legacy `TomlDate` serializes a zero fractional second as `.000`
 *   (e.g. `1979-05-27T07:32:00.000Z`), while the suite spells zero fractions without
 *   them (`1979-05-27T07:32:00Z`); the `.000` is dropped. Non-zero milliseconds, which
 *   the suite requires, pass through untouched.
 * - with `integersAsBigInt` an integer arrives as a `BigInt` and is tagged `integer`;
 *   every remaining number is a float and tagged `float`, whatever its magnitude.
 */

import { TextDecoder } from "node:util";

import { parse, TomlDate } from "../../../js/vendor/smol-toml/dist/index.js";

/** Days per month, January to December (February of a non-leap year). */
const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/** A date-shaped value start: four digits, dash, two, dash, two. */
const DATE_VALUE_RE = /^\d{4}-\d{2}-\d{2}/;
/** A full 1.0.0 date or datetime value: the date, an optional `[Tt]` time (seconds and
 *  fraction optional in the match — their presence is asserted below), an optional offset. */
const DATE_TOKEN_RE = /^\d{4}-\d{2}-\d{2}(?:[Tt]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})?)?/;
/** A local time value: `HH:MM`, seconds and fraction optional in the match. */
const TIME_TOKEN_RE = /^\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?/;
/** The same datetime with its fields captured. */
const FULL_DATETIME_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[Tt](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(?:[Zz]|[+-](\d{2}):(\d{2}))?)?$/;
/** A bare local time with its fields captured. */
const FULL_TIME_RE = /^(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?$/;

/**
 * A Gregorian year is a leap year when divisible by 4, except centuries, which need
 * divisibility by 400.
 *
 * @param {number} year - A parsed year.
 * @returns {boolean}
 */
function isLeapYear(year) {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

/**
 * The number of days a month has.
 *
 * @param {number} year - The parsed year.
 * @param {number} month - The parsed month, 1–12.
 * @returns {number}
 */
function daysInMonth(year, month) {
  return month === 2 && isLeapYear(year) ? 29 : MONTH_DAYS[month - 1];
}

/**
 * Reject a clock whose hour, minute or second is out of range.
 *
 * @param {string} hours - Two parsed digits.
 * @param {string} minutes - Two parsed digits.
 * @param {string} seconds - Two parsed digits.
 * @param {string} token - The token the fields came from, for the error message.
 */
function assertClockField(hours, minutes, seconds, token) {
  if (Number(hours) > 23 || Number(minutes) > 59 || Number(seconds) > 59) {
    throw new Error(`out-of-range clock in "${token}" (TOML 1.0.0: hours 00–23, minutes/seconds 00–59)`);
  }
}

/**
 * Reject a calendar date that does not exist (month 00/13, a day past month end, a
 * February 29/30 in a year without that day).
 *
 * @param {string} year - Four parsed digits.
 * @param {string} month - Two parsed digits.
 * @param {string} day - Two parsed digits.
 * @param {string} token - The token the fields came from, for the error message.
 */
function assertCalendarDate(year, month, day, token) {
  const m = Number(month);
  const d = Number(day);
  if (m < 1 || m > 12) {
    throw new Error(`month ${month} out of range in "${token}"`);
  }
  if (d < 1 || d > daysInMonth(Number(year), m)) {
    throw new Error(`calendar date "${token.slice(0, 10)}" does not exist`);
  }
}

/**
 * Validate one date or time token against TOML 1.0.0: real calendar dates, in-range
 * clock fields, and seconds wherever a time part appears (1.0.0 mandates them; 1.1.0
 * made them optional).
 *
 * @param {string} token - A matched date, datetime or local-time value.
 */
function validateDateOrTimeToken(token) {
  if (DATE_VALUE_RE.test(token)) {
    const match = FULL_DATETIME_RE.exec(token);
    if (match === null) {
      throw new Error(`unparseable date token: "${token}"`);
    }
    const [, year, month, day, hours, minutes, seconds, offsetHours, offsetMinutes] = match;
    assertCalendarDate(year, month, day, token);
    if (hours !== undefined) {
      if (seconds === undefined) {
        throw new Error(`no seconds in time part of "${token}" (TOML 1.0.0 requires them)`);
      }
      assertClockField(hours, minutes, seconds, token);
      if (offsetHours !== undefined) {
        assertClockField(offsetHours, offsetMinutes, "00", token);
      }
    }
  } else {
    const match = FULL_TIME_RE.exec(token);
    if (match === null) {
      throw new Error(`unparseable time token: "${token}"`);
    }
    const [, hours, minutes, seconds] = match;
    if (seconds === undefined) {
      throw new Error(`no seconds in time "${token}" (TOML 1.0.0 requires them)`);
    }
    assertClockField(hours, minutes, seconds, token);
  }
}

/**
 * The value token starting at a digit position, if any: a date (optionally a
 * datetime) or a local time.
 *
 * @param {string} rest - The document from the digit position on.
 * @returns {string | null}
 */
function matchValueToken(rest) {
  if (DATE_VALUE_RE.test(rest)) {
    const token = DATE_TOKEN_RE.exec(rest);
    return token === null ? null : token[0];
  }
  const token = TIME_TOKEN_RE.exec(rest);
  return token === null ? null : token[0];
}

/**
 * Whether the token ended in a bare-key position — `key = value` on one line, a
 * dotted-key segment after `.`, or a table-name segment after `[` — where a date- or
 * time-shaped token is a key, not a value, and needs no date validation.
 *
 * @param {string} document - The whole document.
 * @param {number} tokenEnd - The offset just past the token.
 * @returns {boolean}
 */
function isBareKeyPosition(document, tokenEnd) {
  let i = tokenEnd;
  while (i < document.length && (document.charAt(i) === " " || document.charAt(i) === "\t")) {
    i += 1;
  }
  if (document.charAt(i) === "=") {
    return true;
  }
  return document.charAt(tokenEnd - 1) === "." || document.charAt(tokenEnd - 1) === "[";
}

/**
 * Scan the raw document for the constructs a 1.0.0 decoder must reject but the
 * 1.1.0-capable smol-toml parser accepts:
 * - `\x` byte escapes (a 1.1.0 feature; `\u`/`\U` are 1.0.0 and pass through);
 * - a line break at an inline table's own level (a 1.1.0 feature; breaks inside that
 *   table's array or string values are 1.0.0-legal and pass through);
 * - a trailing comma before an inline table's `}` (a 1.1.0 feature; array trailing
 *   commas stay smol-toml's to check);
 * - date/time literals failing {@link validateDateOrTimeToken}.
 *
 * Strings and comments are tracked so their contents never trip the checks.
 *
 * @param {string} document - The TOML document, valid UTF-8.
 * @throws {Error} - Named when a 1.0.0-forbidden construct is found.
 */
function enforceToml100(document) {
  /** Inline tables currently open. */
  let openBraces = 0;
  /** Arrays currently open, so a line break sits inside a value. */
  let openBrackets = 0;
  let i = 0;
  while (i < document.length) {
    const c = document.charAt(i);
    if (c === "#") {
      // Stop at the line break itself: it still has to clear the inline-table check.
      while (i < document.length && document.charAt(i) !== "\n" && document.charAt(i) !== "\r") {
        i += 1;
      }
      continue;
    }
    if (c === "\"") {
      if (document.startsWith('"""', i)) {
        i += 3;
        while (i < document.length && !document.startsWith('"""', i)) {
          if (document.charAt(i) === "\\") {
            if (document.charAt(i + 1) === "x") {
              throw new Error("\\x byte escapes are a TOML 1.1.0 feature");
            }
            i += 2;
            continue;
          }
          i += 1;
        }
        i += 3;
      } else {
        i += 1;
        while (i < document.length && document.charAt(i) !== "\"") {
          if (document.charAt(i) === "\\") {
            if (document.charAt(i + 1) === "x") {
              throw new Error("\\x byte escapes are a TOML 1.1.0 feature");
            }
            i += 2;
            continue;
          }
          i += 1;
        }
        i += 1;
      }
      continue;
    }
    if (c === "'") {
      if (document.startsWith("'''", i)) {
        i += 3;
        while (i < document.length && !document.startsWith("'''", i)) {
          i += 1;
        }
        i += 3;
      } else {
        i += 1;
        while (i < document.length && document.charAt(i) !== "'") {
          i += 1;
        }
        i += 1;
      }
      continue;
    }
    if (c === "{") {
      openBraces += 1;
      i += 1;
      continue;
    }
    if (c === "}") {
      let j = i - 1;
      while (j >= 0 && (document.charAt(j) === " " || document.charAt(j) === "\t")) {
        j -= 1;
      }
      if (document.charAt(j) === ",") {
        throw new Error("trailing comma in an inline table (TOML 1.0.0 permits none)");
      }
      openBraces -= 1;
      i += 1;
      continue;
    }
    if (c === "[") {
      openBrackets += 1;
      i += 1;
      continue;
    }
    if (c === "]") {
      openBrackets -= 1;
      i += 1;
      continue;
    }
    if (c === "\n" || c === "\r") {
      // The break is at the table's own level only when no value array is open; a
      // line ending right after a comment is one too.
      if (openBraces > 0 && openBrackets === 0) {
        throw new Error("line break inside an inline table (TOML 1.0.0 permits none outside a value)");
      }
      i += 1;
      continue;
    }
    if (c >= "0" && c <= "9") {
      const token = matchValueToken(document.slice(i));
      if (token !== null) {
        if (!isBareKeyPosition(document, i + token.length)) {
          validateDateOrTimeToken(token);
        }
        i += token.length;
        continue;
      }
    }
    i += 1;
  }
}

/**
 * A tagged toml-test value.
 *
 * @typedef {object} Tagged
 * @property {string} type
 * @property {string} value
 */

/**
 * Any tagged document node: a scalar tag, a table of them, or an array. The members of
 * tables and arrays are themselves TaggedValues — JSDoc cannot spell that recursion, so
 * the inner level is left `unknown` and the toml-test suite is what pins it.
 *
 * @typedef {Tagged | Record<string, unknown> | unknown[]} TaggedValue
 */

/**
 * Render a parsed smol-toml value as its tagged form (toml-test's JSON encoding).
 *
 * @param {unknown} value - A parsed TOML value (string, number, `BigInt`, boolean,
 *   `TomlDate`, array or plain table).
 * @returns {TaggedValue} - The tagged form for a scalar, the recursively tagged form for
 *   a table, and a bare array of tagged values for an array (v2 spells arrays as JSON arrays).
 */
function tag(value) {
  if (typeof value === "string") {
    return { type: "string", value: value };
  }
  if (typeof value === "boolean") {
    return { type: "bool", value: String(value) };
  }
  if (typeof value === "bigint") {
    return { type: "integer", value: value.toString() };
  }
  if (typeof value === "number") {
    return { type: "float", value: String(value) };
  }
  if (value instanceof TomlDate) {
    return { type: dateTag(value), value: dateValue(value) };
  }
  if (Array.isArray(value)) {
    // An explicit arrow, not the bare function: `map` hands each item an index, and
    // `tag` takes one argument.
    return value.map((item) => tag(item));
  }
  if (value !== null && typeof value === "object") {
    return tagTable(/** @type {Record<string, unknown>} */ (value));
  }
  throw new Error(`untagged TOML value: ${String(value)}`);
}

/**
 * Walk a parsed table into its tagged form.
 *
 * @param {Record<string, unknown>} table - A plain object of parsed TOML values.
 * @returns {Record<string, unknown>}
 */
function tagTable(table) {
  /** @type {Record<string, unknown>} */
  const out = {};
  for (const [key, item] of Object.entries(table)) {
    out[key] = tag(item);
  }
  return out;
}

/**
 * The toml-test tag for a legacy `TomlDate`, from the parser's own classification.
 *
 * @param {TomlDate} date - A parsed date, time or datetime.
 * @returns {"datetime" | "datetime-local" | "date-local" | "time-local"}
 */
function dateTag(date) {
  if (date.isDate()) {
    return "date-local";
  }
  if (date.isTime()) {
    return "time-local";
  }
  return date.isLocal() ? "datetime-local" : "datetime";
}

/**
 * The suite's spelling for a `TomlDate`: its legacy ISO string with the zero-fraction
 * `.000` dropped, non-zero fractions kept.
 *
 * @param {TomlDate} date
 * @returns {string}
 */
function dateValue(date) {
  return date.toISOString().replace(/\.000(?=[+-]|Z|$)/, "");
}

/**
 * Print a parse failure to stderr and set the exit code to 1.
 *
 * @param {unknown} err - The caught failure.
 */
function reportFailure(err) {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
}

async function main() {
  /** @type {Buffer[]} */
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const buffer = Buffer.concat(chunks);

  let document;
  try {
    document = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    reportFailure("stdin is not valid UTF-8");
    return;
  }

  let parsed;
  try {
    enforceToml100(document);
    parsed = parse(document, { integersAsBigInt: true });
  } catch (err) {
    reportFailure(err);
    return;
  }
  process.stdout.write(JSON.stringify(tag(parsed)) + "\n");
}

main();
