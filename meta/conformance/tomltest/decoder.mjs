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
 * Python floor (`tomllib`) reads — so it puts the same TOML 1.0.0 fence in front of the
 * 1.1.0-capable smol-toml parser that akmon's record reader does:
 * `js/common/toml10.mjs::toml10Refusal` (C117; one fence, so the suite measures the
 * one akmon runs). Stdin is UTF-8-decoded with `fatal: true` (the decoder drops a
 * leading BOM, as before); integers are parsed with `integersAsBigInt` so the
 * integer/float distinction and magnitudes beyond 53 bits survive. Everything else
 * semantic is smol-toml's.
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

import { toml10Refusal } from "../../../js/common/toml10.mjs";
import { parse, TomlDate } from "../../../js/vendor/smol-toml/dist/index.js";

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
    const refusal = toml10Refusal(document);
    if (refusal !== null) {
      throw new Error(`line ${refusal.line}, column ${refusal.column}: ${refusal.reason}`);
    }
    parsed = parse(document, { integersAsBigInt: true });
  } catch (err) {
    reportFailure(err);
    return;
  }
  process.stdout.write(JSON.stringify(tag(parsed)) + "\n");
}

main();
