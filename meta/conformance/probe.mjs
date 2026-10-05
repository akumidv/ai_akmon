#!/usr/bin/env node
/**
 * Unit-table probe for the JavaScript implementation (C103) — the exact twin of `probe.py`.
 *
 * The corpus's unit tables test the *functions* the two implementations share and JS cannot
 * inherit — the stdlib gaps and the shared data-driven answers alike, the list being owned by
 * `probe.py`'s docstring. This probe feeds every case to the tree-under-test's own function
 * (loaded from `--tree`, the corpus snapshot) and compares with the table's expected value. The
 * table is the spec — the
 * probe is only the mouth the JavaScript implementation answers through, the way `probe.py`
 * is the Python one. Output: the same `{"ok", "failed"}` document, byte for byte.
 *
 * Usage: node meta/conformance/probe.mjs <subcommand> <table.toml> [--tree REPO]
 * (the flag parses in any position, the way argparse reorders probe.py's).
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { TextDecoder } from "node:util";

const CORPUS_ROOT = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(CORPUS_ROOT, "..", "..");

// The mouth's own TOML reader: the repository's vendored smol-toml, the way probe.py reads
// its tables with the host's tomllib.
const smol = await import(pathToFileURL(path.join(CORPUS_ROOT, "..", "..", "js", "vendor", "smol-toml", "dist", "index.js")).href);

/**
 * Load one module of the tree under test. Its shape is that module's own contract, checked
 * by its own file and the table it answers, so the probe treats the handle as opaque.
 * @param {string} tree
 * @param {string} relative
 * @returns {Promise<any>}
 */
async function loadModule(tree, relative) {
  return import(pathToFileURL(path.join(tree, relative)).href);
}

/** Deep equality on the JSON-shaped values the results carry. */
function deepEqual(/** @type {unknown} */ a, /** @type {unknown} */ b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** `path` with symlinks dereferenced; unchanged when there is nothing there to resolve. */
function _realpath(/** @type {string} */ path_) {
  try {
    return fs.realpathSync(path_);
  } catch {
    return path_;
  }
}

// --------------------------------------------------------------------------------------
// the json probe's ordered value walk: smol-toml hands tables back as plain objects, and a
// plain object reorders its integer-like keys — the table pins the DOCUMENT's insertion
// order, so the order is re-read from the raw text and the values taken from the parse.
// --------------------------------------------------------------------------------------

function _skipWs(/** @type {string} */ text, /** @type {number} */ i) {
  while (i < text.length && " \t".includes(text[i])) i++;
  return i;
}

/**
 * The value of one TOML basic string (the text between the quotes at `i`), with its escapes
 * decoded — `tomllib` hands back the decoded key, so a raw-text reader that only strips
 * backslashes would look the key up under `u043A` instead of `к` and find nothing.
 * @returns {[string, number]}
 */
function _readBasicString(/** @type {string} */ text, /** @type {number} */ i) {
  let out = "";
  let j = i;
  while (j < text.length) {
    const c = text[j];
    if (c === '"') {
      return [out, j + 1];
    }
    if (c !== "\\") {
      out += c;
      j += 1;
      continue;
    }
    const next = text[j + 1];
    const short = { b: "\b", f: "\f", n: "\n", r: "\r", t: "\t", '"': '"', "\\": "\\" }[next];
    if (short !== undefined) {
      out += short;
      j += 2;
      continue;
    }
    const digits = next === "u" ? 4 : next === "U" ? 8 : 0;
    if (digits === 0) {
      throw new Error(`probe: an unknown escape \\${next} in the units table`);
    }
    out += String.fromCodePoint(Number.parseInt(text.slice(j + 2, j + 2 + digits), 16));
    j += 2 + digits;
  }
  throw new Error("probe: unterminated key string in the units table");
}

/** @returns {[string, number]} */
function _readKey(/** @type {string} */ text, /** @type {number} */ i) {
  const bare = /^[A-Za-z0-9_-]+/.exec(text.slice(i));
  if (bare !== null) {
    return [bare[0], i + bare[0].length];
  }
  const quote = text[i];
  if (quote === '"') {
    return _readBasicString(text, i + 1);
  }
  if (quote !== "'") {
    throw new Error(`probe: cannot read a key at ${text.slice(i, i + 12)}`);
  }
  let j = i + 1;
  while (j < text.length) {
    if (text[j] === quote) {
      return [text.slice(i + 1, j), j + 1];
    }
    j++;
  }
  throw new Error("probe: unterminated key string in the units table");
}

/** @returns {number} */
function _skipScalar(/** @type {string} */ text, /** @type {number} */ i) {
  const quote = text[i];
  if (quote === '"' || quote === "'") {
    let j = i + 1;
    while (j < text.length) {
      if (quote === '"' && text[j] === "\\") {
        j += 2;
        continue;
      }
      if (text[j] === quote) {
        return j + 1;
      }
      j++;
    }
    throw new Error("probe: unterminated string in the units table");
  }
  // A number, boolean or date: walk to the value's end (delimiter, table end or whitespace).
  while (i < text.length && !",}] \t\n".includes(text[i])) {
    i++;
  }
  return i;
}

// A TOML scalar that parsed to a JS number is a *float* exactly when its written text can only
// spell a float: a fraction, an exponent, or one of the inf/nan words. The radix prefixes are
// checked first because `0xE` carries an `e` that belongs to the digits, not to an exponent —
// a `[.eE]` test alone marked it a float, and the writer then spelled 14 as `14.0`.
const TOML_SPECIAL_FLOAT_RE = /^[-+]?(?:inf|nan)$/;
const TOML_DECIMAL_RE = /^[-+]?[0-9](?:_?[0-9])*(?:\.[0-9](?:_?[0-9])*)?(?:[eE][-+]?[0-9](?:_?[0-9])*)?$/;
const TOML_PREFIXED_INT_RE = /^[-+]?0[xXoObB]/;

/** Whether one written TOML scalar is a float. @param {string} written @returns {boolean} */
function isTomlFloat(written) {
  if (TOML_SPECIAL_FLOAT_RE.test(written)) {
    return true;
  }
  if (TOML_PREFIXED_INT_RE.test(written)) {
    return false;
  }
  return TOML_DECIMAL_RE.test(written) && (written.includes(".") || /[eE]/.test(written));
}

/**
 * Walk one TOML value expression (from `text` at `i`) in document order, taking every
 * scalar's value from the parallel `smolValue`. Returns [orderedValue, nextIndex]; objects
 * come back as Maps so integer-like keys keep their written order. A `floatMark` class, when
 * given, wraps the scalars that are floats — JS numbers lose that distinction (`1.0 === 1`),
 * and the writer spells the two differently.
 *
 * @param {string} text
 * @param {any} smolValue
 * @param {number} i
 * @param {{new (n: number): any} | null} [floatMark]
 * @returns {[any, number]}
 */
function toOrderedValue(text, smolValue, i, floatMark = null) {
  i = _skipWs(text, i);
  const c = text[i];
  if (c === "{") {
    /** @type {Map<string, any>} */
    const map = new Map();
    i++;
    for (;;) {
      i = _skipWs(text, i);
      if (text[i] === "}") {
        return [map, i + 1];
      }
      const [key, afterKey] = _readKey(text, i);
      let j = _skipWs(text, afterKey);
      if (text[j] !== "=") {
        throw new Error(`probe: expected = after key ${key} in the units table`);
      }
      const child = smolValue[key];
      const [value, next] = toOrderedValue(text, child, j + 1, floatMark);
      map.set(key, value);
      i = _skipWs(text, next);
      if (text[i] === ",") {
        i++;
      } else if (text[i] !== "}") {
        throw new Error("probe: malformed inline table in the units table");
      }
    }
  }
  if (c === "[") {
    /** @type {any[]} */
    const array = [];
    i++;
    for (;;) {
      i = _skipWs(text, i);
      if (text[i] === "]") {
        return [array, i + 1];
      }
      const [value, next] = toOrderedValue(text, smolValue[array.length], i, floatMark);
      array.push(value);
      i = _skipWs(text, next);
      if (text[i] === ",") {
        i++;
      } else if (text[i] !== "]") {
        throw new Error("probe: malformed array in the units table");
      }
    }
  }
  // A scalar: the written text is walked past for its floatness, the value is the parsed one.
  const end = _skipScalar(text, i);
  const written = text.slice(i, end).trim();
  if (typeof smolValue === "number") {
    if (floatMark !== null && isTomlFloat(written)) {
      return [new floatMark(smolValue), end];
    }
    return [smolValue, end];
  }
  if (typeof smolValue === "string" || typeof smolValue === "boolean" || smolValue === null) {
    return [smolValue, end];
  }
  throw new Error(`probe: a json case carries a date scalar (${written}) — not supported`);
}

/** The `value = { … }` expression of one `[[case]]` block, as an ordered document. */
function orderedValue(
  /** @type {string} */ block,
  /** @type {any} */ smolCase,
  /** @type {{new (n: number): any} | null} */ floatMark,
) {
  const lines = block.split("\n");
  const line = lines.find((/** @type {string} */ l) => /^value\s*=/.test(l.trimStart()));
  if (line === undefined) {
    throw new Error("probe: a json case without a value line");
  }
  const start = line.indexOf("{");
  if (start === -1) {
    throw new Error("probe: a json case whose value is not an inline table");
  }
  const [value] = toOrderedValue(line, smolCase.value, start, floatMark);
  return value;
}

// --------------------------------------------------------------------------------------
// the probes — one per subcommand, mirroring probe.py's result shapes
// --------------------------------------------------------------------------------------

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeVersions(tree, table) {
  const module = await loadModule(tree, "js/common/versions.mjs");
  const results = [];
  for (const [index, case_] of (table.case ?? []).entries()) {
    const expected = case_.expected;
    const actual = {
      split_base: module.splitVersion(case_.input).base,
      split_ahead: module.splitVersion(case_.input).ahead,
      is_final: module.isFinal(case_.input),
      order: module.orderKey(case_.input),
    };
    results.push({
      index,
      expected: {
        split_base: expected.split_base ?? null,
        split_ahead: expected.split_ahead ?? null,
        is_final: expected.is_final ?? null,
        order: expected.order ?? null,
      },
      actual,
    });
  }
  for (const [index, case_] of (table.pair ?? []).entries()) {
    // The table asks the comparator, not the key: `<` on two JS arrays compares their string
    // forms, and the table spells a raise "error" (units/versions.toml) — as probe.py does.
    let actual;
    try {
      actual = module.compareVersions(case_.a, case_.b);
    } catch {
      actual = "error";
    }
    results.push({ index: 1000 + index, expected: case_.expected, actual });
  }
  for (const [index, case_] of (table.semver ?? []).entries()) {
    results.push({ index: 2000 + index, expected: case_.expected, actual: module.semverSpelling(case_.input) });
  }
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeRecord(tree, table) {
  const module = await loadModule(tree, "js/common/record.mjs");
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-probe-record-"));
  const results = [];
  try {
    for (const [index, case_] of (table.case ?? []).entries()) {
      let lenient;
      let strict;
      let strictOk;
      if (case_.absent === true) {
        lenient = {};
        strict = {};
        strictOk = true;
      } else {
        const file = path.join(scratch, `record-${index}.toml`);
        fs.writeFileSync(file, case_.text ?? "", "utf-8");
        lenient = module.readAkmonToml(file);
        try {
          strict = module.readAkmonTomlStrict(file);
          strictOk = true;
        } catch (error) {
          if (error instanceof module.RecordError) {
            strict = null;
            strictOk = false;
          } else {
            throw error;
          }
        }
      }
      const expected = case_.expected;
      results.push({
        index,
        expected: {
          lenient: expected.lenient ?? null,
          strict: expected.strict ?? null,
          strict_ok: expected.strict_ok ?? null,
        },
        actual: { lenient, strict, strict_ok: strictOk },
      });
    }
  } finally {
    fs.rmSync(scratch, { recursive: true, force: true });
  }
  const stripResults = (table.strip ?? []).map((/** @type {any} */ case_, /** @type {number} */ index) => ({
    index,
    expected: case_.expected,
    actual: module.stripInlineComment(case_.input),
  }));
  results.push(...stripResults);
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeShlex(tree, table) {
  const module = await loadModule(tree, "js/common/shlex.mjs");
  const results = [];
  for (const [index, case_] of (table.case ?? []).entries()) {
    if (case_.join !== undefined) {
      results.push({ index, expected: case_.expected, actual: module.shlexJoin(case_.join) });
      continue;
    }
    let argv;
    let error;
    try {
      argv = module.shlexSplit(case_.input);
      error = false;
    } catch {
      argv = null;
      error = true;
    }
    results.push({
      index,
      expected: { argv: case_.expected.argv ?? null, error: case_.expected.error ?? false },
      actual: { argv, error },
    });
  }
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeGlob(tree, table) {
  const module = await loadModule(tree, "js/common/glob.mjs");
  return (table.case ?? []).map((/** @type {any} */ case_, /** @type {number} */ index) => ({
    index,
    expected: case_.expected,
    actual: module.fnmatchCase(case_.name, case_.pattern),
  }));
}

/** @param {any} writer @param {any} value @param {string} form @returns {string} */
function _jsonForm(writer, value, form) {
  if (form === "hook") {
    return writer.hookForm(value);
  }
  if (form === "wiring") {
    return writer.wiringForm(value);
  }
  if (form === "canonical") {
    return writer.canonicalForm(value);
  }
  throw new Error(`probe: unknown json form ${JSON.stringify(form)}`);
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @param {string} tableText
 * @returns {Promise<any[]>}
 */
async function probeJson(tree, table, tableText) {
  const writer = await loadModule(tree, "js/common/json_writer.mjs");
  // Each `[[case]]` block's own text, found by its marker rather than by splitting: a split
  // numbers the cases from whatever precedes the first marker, so a table that opens with
  // `[[case]]` at line 1 would answer case n from case n+1's text — silently, and with the
  // values of one case against the expectations of another.
  const markers = [...tableText.matchAll(/^\s*\[\[case\]\]\s*$/gm)].map((match) => match.index);
  const results = [];
  for (const [index, case_] of (table.case ?? []).entries()) {
    const from = markers[index];
    const block = from === undefined ? "" : tableText.slice(from, markers[index + 1] ?? tableText.length);
    let value = orderedValue(block, case_, writer.FloatValue);
    const nullKeys = case_.null_keys;
    if (nullKeys) {
      for (const key of nullKeys) {
        value.set(key, null);
      }
    }
    results.push({ index, expected: case_.expected, actual: _jsonForm(writer, value, case_.form) });
  }
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeSort(tree, table) {
  const module = await loadModule(tree, "js/common/sort.mjs");
  return (table.case ?? []).map((/** @type {any} */ case_, /** @type {number} */ index) => ({
    index,
    expected: case_.expected,
    actual: module.codePointSort(case_.input),
  }));
}

// --------------------------------------------------------------------------------------
// The two mouths below are the first to answer from a *shared data file*. `common/runtime.py`
// and `common/check_runner.py` read their tables out of `common/*.json` on every call, so the
// Python side reaches them through the module — which resolves the file beside itself, i.e.
// inside the snapshot — while the JS side is fed the same file by its mouth, exactly the way
// the module's twin is handed its data at the entry point.
// --------------------------------------------------------------------------------------

/** One data file of the tree under test, as the module beside it reads it. */
function readData(/** @type {string} */ tree, /** @type {string} */ relative) {
  return JSON.parse(fs.readFileSync(path.join(tree, relative), "utf-8"));
}

/**
 * The text a table names by data-file path, flattened one level.
 *
 * A `text` row states *where* its answer lives (`check_config.no_checks`) instead of repeating
 * it: the data file is the one owner of that prose, and what the table has to pin is the
 * accessor's pairing with its key and the order of a two-part answer.
 *
 * @param {any} document
 * @param {string[]} dottedPaths
 * @returns {any[]}
 */
function dataParts(document, dottedPaths) {
  /** @type {any[]} */
  const parts = [];
  for (const dotted of dottedPaths) {
    let node = document;
    for (const step of dotted.split(".")) {
      const isTable = typeof node === "object" && node !== null && !Array.isArray(node);
      node = isTable ? node[step] : null;
    }
    if (Array.isArray(node)) {
      parts.push(...node);
    } else {
      parts.push(node);
    }
  }
  return parts;
}

/** One accessor's answer as the flat list of text parts the table compares against. */
function textParts(/** @type {any} */ answer) {
  return Array.isArray(answer) ? answer : [answer];
}

/**
 * One declared check in the only form a table can carry it: three fields, in this order, lists
 * not tuples — the JSON key order is part of the document both mouths must print identically.
 */
function renderCheck(/** @type {any} */ check) {
  return { name: check.name, argv: [...check.argv], files: [...check.files] };
}

/** One runtime declaration as {binary, population, modality}; an absent one stays null. */
function renderDeclaration(/** @type {any} */ declaration) {
  if (declaration === null) {
    return null;
  }
  return { binary: declaration.binary, population: declaration.population, modality: declaration.modality };
}

/**
 * The population, carrier and modality labels the module declares (index base 0).
 * @param {any} module
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function runtimeLabels(module, table) {
  /** @type {Record<string, string | undefined>} */
  const labels = {
    GENERATED_WIRING: module.GENERATED_WIRING,
    OWN_TOOLING: module.OWN_TOOLING,
    POSIX_SHELL: module.POSIX_SHELL,
    REQUIRED: module.REQUIRED,
    OPTIONAL: module.OPTIONAL,
    REQUIRED_ON: module.REQUIRED_ON,
  };
  const results = [];
  for (const [index, case_] of (table.label ?? []).entries()) {
    results.push({ index, expected: case_.expected ?? null, actual: labels[case_.name] ?? null });
  }
  return results;
}

/**
 * The ordered declaration list, answered by the position the row names (index base 1000).
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function runtimeDeclared(module, data, table) {
  const declarations = module.declaredRuntimes(data);
  const results = [];
  for (const [index, case_] of (table.declared ?? []).entries()) {
    const found = declarations[case_.index] ?? null;
    results.push({ index: 1000 + index, expected: case_.expected ?? null, actual: renderDeclaration(found) });
  }
  return results;
}

/** The argv a named constructor answers; a row naming no known builder answers null. */
function runtimeNamedArgv(/** @type {any} */ module, /** @type {any} */ data, /** @type {any} */ case_) {
  if (case_.named === "version_command") {
    return module.versionCommand(data, case_.harness);
  }
  if (case_.named === "codex_hooks_list_command") {
    return module.codexHooksListCommand(data);
  }
  return null;
}

/**
 * The command builders: the table's prefix plus a caller's tail (bases 2000 and 3000).
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function runtimeArgv(module, data, table) {
  const results = [];
  for (const [index, case_] of (table.command ?? []).entries()) {
    const extra = /** @type {string[]} */ (case_.extra ?? []);
    const argv = module.harnessCommand(data, case_.harness, case_.operation, ...extra);
    results.push({ index: 2000 + index, expected: case_.expected ?? null, actual: argv });
  }
  for (const [index, case_] of (table.named ?? []).entries()) {
    const argv = runtimeNamedArgv(module, data, case_);
    results.push({ index: 3000 + index, expected: case_.expected ?? null, actual: argv });
  }
  return results;
}

/**
 * The refusal for an undeclared harness or operation, by its whole text (index base 5000).
 *
 * The message is spec, not decoration: both sides quote the unknown name the same way and list
 * what is known in the same order, and it is all an owner gets when a caller asks a harness for
 * an operation nobody declared.
 *
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function runtimeErrors(module, data, table) {
  const results = [];
  for (const [index, case_] of (table.error ?? []).entries()) {
    let actual = null;
    try {
      module.harnessCommand(data, case_.harness, case_.operation);
    } catch (error) {
      actual = error instanceof Error ? error.message : null;
    }
    results.push({ index: 5000 + index, expected: case_.expected ?? null, actual });
  }
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeRuntime(tree, table) {
  const module = await loadModule(tree, "js/common/runtime.mjs");
  const data = readData(tree, "common/runtime.json");
  const binaries = [];
  for (const [index, case_] of (table.binaries ?? []).entries()) {
    binaries.push({ index: 4000 + index, expected: case_.expected ?? null, actual: module.harnessBinaries(data) });
  }
  return [
    ...runtimeLabels(module, table),
    ...runtimeDeclared(module, data, table),
    ...runtimeArgv(module, data, table),
    ...binaries,
    ...runtimeErrors(module, data, table),
  ];
}

/**
 * ``readChecks`` over a whole `[check]` table: the checks and every problem (index base 0).
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function checkEntries(module, data, table) {
  const results = [];
  for (const [index, case_] of (table.case ?? []).entries()) {
    const answer = module.readChecks(data, case_.table ?? null);
    const expected = case_.expected ?? {};
    results.push({
      index,
      expected: { checks: expected.checks ?? null, problems: expected.problems ?? null },
      actual: { checks: answer.checks.map(renderCheck), problems: answer.problems },
    });
  }
  return results;
}

/**
 * `argvFor`: the `{files}` expansion and the nothing-to-do refusal (index base 1000).
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function checkArgv(module, data, table) {
  const results = [];
  for (const [index, case_] of (table.argv ?? []).entries()) {
    const check = module.makeCheck(data, "case", case_.argv ?? [], case_.files ?? []);
    const answer = module.argvFor(data, check, case_.changed ?? null);
    const expected = case_.expected ?? {};
    results.push({ index: 1000 + index, expected: { argv: expected.argv ?? null }, actual: { argv: answer } });
  }
  return results;
}

/**
 * The `makeCheck` rule itself: its three fields and its empty-patterns answer (index base 2000).
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function checkMade(module, data, table) {
  const results = [];
  for (const [index, case_] of (table.make ?? []).entries()) {
    const check = module.makeCheck(data, case_.name ?? "", case_.argv ?? [], case_.files ?? []);
    results.push({ index: 2000 + index, expected: case_.expected ?? null, actual: renderCheck(check) });
  }
  return results;
}

/**
 * The text accessors against the data-file path each row names (index base 3000).
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function checkTexts(module, data, table) {
  /** @type {Record<string, ((d: any) => any) | undefined>} */
  const getters = {
    config_target: module.configTarget,
    files_placeholder: module.filesPlaceholder,
    default_files: module.defaultFiles,
    repair_record_fix: module.repairRecordFix,
    repair_record_verify_fix: module.repairRecordVerifyFix,
    correct_entry_fix: module.correctEntryFix,
    no_checks: module.noChecks,
    scope_fix: module.scopeFix,
    check_table_ok: module.checkTableOk,
  };
  const results = [];
  for (const [index, case_] of (table.text ?? []).entries()) {
    const getter = getters[case_.getter];
    // The `undefined` test is inline, not a saved boolean: the call below needs the narrowing it
    // gives, and a row naming no known accessor must answer null on both sides, not crash.
    results.push({
      index: 3000 + index,
      expected: getter === undefined ? null : dataParts(data, case_.keys ?? []),
      actual: getter === undefined ? null : textParts(getter(data)),
    });
  }
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeCheckRunner(tree, table) {
  const module = await loadModule(tree, "js/common/check_runner.mjs");
  const data = readData(tree, "common/check_runner.json");
  return [
    ...checkEntries(module, data, table),
    ...checkArgv(module, data, table),
    ...checkMade(module, data, table),
    ...checkTexts(module, data, table),
  ];
}

// --------------------------------------------------------------------------------------
// The two mouths below answer from *files and the environment*, not only from values: the
// marker module claims and releases files in a directory, the materialization module compares
// two trees. A row describes a world — a scratch directory the probe builds and removes, the
// environment variables a row sets — and the mouth reports what the module did to it. The same
// world-building is written in `probe.py`; the table is the only shared text. A call that
// raises answers `{"raises": true}` rather than a message: what each language raises is its
// own, and the table pins only that the twin refuses too. A row marked `nonroot` relies on file
// modes, which root ignores: it is left out of the answer when the probe runs as root, on both
// sides.
// --------------------------------------------------------------------------------------

/**
 * Run `call` with environment variables set (a `null` value: unset), then restore every one.
 * @template T
 * @param {Record<string, string | null>} changes
 * @param {() => T} call
 * @returns {T}
 */
function withEnvironment(changes, call) {
  /** @type {Record<string, string | undefined>} */
  const saved = {};
  for (const name of Object.keys(changes)) {
    saved[name] = process.env[name];
  }
  const apply = (/** @type {string} */ name, /** @type {string | null | undefined} */ value) => {
    if (value === null || value === undefined) {
      delete process.env[name];
    } else {
      process.env[name] = value;
    }
  };
  try {
    for (const [name, value] of Object.entries(changes)) {
      apply(name, value);
    }
    return call();
  } finally {
    for (const [name, value] of Object.entries(saved)) {
      apply(name, value);
    }
  }
}

/** What a call answers in table form: `{value}`, or `{raises: true}` when it raised. */
function answered(/** @type {() => unknown} */ call) {
  try {
    return { value: call() };
  } catch {
    return { raises: true };
  }
}

/** A `nonroot` row is not asked of a process that file modes do not bind. */
function skippedAsRoot(/** @type {any} */ case_) {
  return case_.nonroot === true && process.getuid?.() === 0;
}

/** The marker hash as the probe's own oracle computes it (node:crypto), not through the module. */
function markerDigest(/** @type {any} */ data, /** @type {string} */ identity) {
  return createHash("sha256").update(identity, "utf8").digest("hex").slice(0, data.name_sha256_tail);
}

/** Marker file names with each hash replaced by the identity that made it: `kind@identity`. */
function markerLabelled(
  /** @type {any} */ data,
  /** @type {string[]} */ names,
  /** @type {string[]} */ identities,
) {
  /** @type {Map<string, string>} */
  const labels = new Map(identities.map((identity) => [markerDigest(data, identity), identity]));
  const prefix = data.name_prefix;
  return names.map((name) => {
    const cut = name.lastIndexOf("-");
    const digest = name.slice(cut + 1);
    const identity = labels.get(digest);
    if (name.startsWith(prefix) && identity !== undefined) {
      return `${name.slice(prefix.length, cut)}@${identity}`;
    }
    return name;
  });
}

/** The folder's file names, sorted by code point; a folder that is not there lists nothing. */
function markerListing(/** @type {any} */ sort, /** @type {string} */ folder) {
  try {
    return sort.codePointSort(fs.readdirSync(folder));
  } catch {
    return [];
  }
}

/**
 * One step of a marker sequence; answers are the claim results and the listings, in order.
 * @param {any} module
 * @param {any} sort
 * @param {any} data
 * @param {any} world
 * @param {any} step
 * @returns {any[]}
 */
function markerStep(module, sort, data, world, step) {
  const { folder, directory, identities } = world;
  switch (step.op) {
    case "claim":
      return [module.claimDiagnosticMarker(data, step.kind, step.identity ?? null, { directory })];
    case "release":
      module.releaseDiagnosticMarkers(data, step.prefix, step.identity ?? null, {
        keepKind: step.keep_kind ?? null,
        directory,
      });
      return [];
    case "ls":
      return [sort.codePointSort(markerLabelled(data, markerListing(sort, folder), identities))];
    case "outside":
      return [markerListing(sort, world.scratch).filter((/** @type {string} */ name) => name !== "dir")];
    case "plant":
      fs.writeFileSync(path.join(folder, step.name), "");
      return [];
    case "plant_dir":
      fs.mkdirSync(path.join(folder, `${data.name_prefix}${step.kind}-${markerDigest(data, step.identity)}`));
      return [];
    case "age": {
      const names = markerListing(sort, folder);
      const labelled = markerLabelled(data, names, identities);
      const found = names.filter((/** @type {string} */ _name, /** @type {number} */ i) => labelled[i] === step.label);
      if (found.length !== 1) {
        throw new Error(`probe: age label ${step.label} names ${found.length} markers`);
      }
      const moment = Date.now() / 1000 - step.seconds;
      fs.utimesSync(path.join(folder, found[0]), moment, moment);
      return [];
    }
    default:
      throw new Error(`probe: unknown marker step ${JSON.stringify(step.op)}`);
  }
}

/**
 * Claim/release/age sequences over one scratch directory each (index base 4000).
 * @param {any} module
 * @param {any} sort
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function markerSequences(module, sort, data, table) {
  const results = [];
  for (const [index, case_] of (table.sequence ?? []).entries()) {
    const steps = case_.steps ?? [];
    const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-probe-markers-"));
    const folder = path.join(scratch, "dir");
    if (!case_.missing_dir) {
      fs.mkdirSync(folder);
    }
    const identities = [...new Set(steps.map((/** @type {any} */ step) => step.identity).filter(Boolean))];
    const world = { scratch, folder, directory: case_.default_dir ? null : folder, identities };
    /** @type {any[]} */
    const answers = [];
    try {
      withEnvironment(case_.default_dir ? { TMPDIR: folder } : {}, () => {
        for (const step of steps) {
          answers.push(...markerStep(module, sort, data, world, step));
        }
      });
    } finally {
      fs.rmSync(scratch, { recursive: true, force: true });
    }
    results.push({ index: 4000 + index, expected: case_.expected ?? null, actual: answers });
  }
  return results;
}

/**
 * The file one claim leaves: its whole name, its mode under umask 022, nothing beside it (base 3000).
 * @param {any} module
 * @param {any} sort
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function markerNames(module, sort, data, table) {
  const results = [];
  for (const [index, case_] of (table.name ?? []).entries()) {
    const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-probe-markers-"));
    const folder = path.join(scratch, "dir");
    fs.mkdirSync(folder);
    const previous = process.umask(0o022);
    let actual;
    try {
      module.claimDiagnosticMarker(data, case_.kind, case_.identity, { directory: folder });
      const names = markerListing(sort, folder);
      const mode = names.length > 0 ? (fs.statSync(path.join(folder, names[0])).mode & 0o777).toString(8) : "";
      actual = {
        names,
        mode,
        outside: markerListing(sort, scratch).filter((/** @type {string} */ name) => name !== "dir"),
      };
    } finally {
      process.umask(previous);
      fs.rmSync(scratch, { recursive: true, force: true });
    }
    results.push({ index: 3000 + index, expected: case_.expected ?? null, actual });
  }
  return results;
}

/**
 * The module's `gettempdir` under each row's environment — the stdlib's answer, which the row
 * pins (index base 5000).
 * @param {any} module
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function markerTempdirs(module, table) {
  const results = [];
  for (const [index, case_] of (table.tempdir ?? []).entries()) {
    if (skippedAsRoot(case_)) {
      continue;
    }
    const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-probe-markers-"));
    /** @type {Array<[string, string]>} */
    const modes = Object.entries(case_.chmod ?? {});
    let actual;
    try {
      for (const relative of case_.dirs ?? []) {
        fs.mkdirSync(path.join(scratch, relative), { recursive: true });
      }
      for (const relative of case_.files ?? []) {
        fs.writeFileSync(path.join(scratch, relative), "");
      }
      for (const [relative, mode] of modes) {
        fs.chmodSync(path.join(scratch, relative), Number.parseInt(mode, 8));
      }
      /** @type {Record<string, string | null>} */
      const changes = { TMPDIR: null, TEMP: null, TMP: null };
      for (const [name, value] of Object.entries(case_.env ?? {})) {
        changes[name] = String(value).replaceAll("{{scratch}}", scratch);
      }
      actual = withEnvironment(changes, () => module.gettempdir()).replaceAll(scratch, "{{scratch}}");
    } finally {
      for (const [relative] of modes) {
        fs.chmodSync(path.join(scratch, relative), 0o700);
      }
      fs.rmSync(scratch, { recursive: true, force: true });
    }
    results.push({ index: 5000 + index, expected: case_.expected ?? null, actual });
  }
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeMarkers(tree, table) {
  const module = await loadModule(tree, "js/common/markers.mjs");
  const sort = await loadModule(tree, "js/common/sort.mjs");
  const data = readData(tree, "common/markers.json");
  const results = [];
  for (const [index, case_] of (table.kind ?? []).entries()) {
    results.push({ index, expected: case_.expected ?? null, actual: answered(() => module.markerKind(data, case_.stem)) });
  }
  for (const [index, case_] of (table.unidentified ?? []).entries()) {
    results.push({ index: 1000 + index, expected: case_.expected ?? null, actual: module.unidentifiedIdentity(data) });
  }
  for (const [index, case_] of (table.state ?? []).entries()) {
    const actual = answered(() => module.delegationStateName(data, case_.which, case_.identity));
    results.push({ index: 2000 + index, expected: case_.expected ?? null, actual });
  }
  return [
    ...results,
    ...markerNames(module, sort, data, table),
    ...markerSequences(module, sort, data, table),
    ...markerTempdirs(module, table),
  ];
}

/**
 * A scratch directory with the project (its `.akmon` copies) and the standard tree a row describes.
 * @param {Record<string, any>} case_
 * @returns {{scratch: string, project: string, tree: string, copies: string}}
 */
function materializationWorld(case_) {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-probe-materialization-"));
  const project = path.join(scratch, "project");
  const tree = path.join(scratch, "tree");
  const copies = path.join(project, case_.aitna_dir ?? "_aitna", ".akmon");
  fs.mkdirSync(project);
  fs.mkdirSync(tree);
  for (const [base, prefix] of /** @type {Array<[string, string]>} */ ([[copies, "project"], [tree, "tree"]])) {
    /** @type {Array<[string, Buffer]>} */
    const files = [
      ...Object.entries(case_[prefix] ?? {}).map(([relative, text]) => /** @type {[string, Buffer]} */ ([relative, Buffer.from(String(text), "utf-8")])),
      ...Object.entries(case_[`${prefix}_hex`] ?? {}).map(([relative, hexed]) => /** @type {[string, Buffer]} */ ([relative, Buffer.from(String(hexed), "hex")])),
    ];
    for (const [relative, content] of files) {
      fs.mkdirSync(path.dirname(path.join(base, relative)), { recursive: true });
      fs.writeFileSync(path.join(base, relative), content);
    }
    for (const relative of case_[`${prefix}_dirs`] ?? []) {
      fs.mkdirSync(path.join(base, relative), { recursive: true });
    }
    for (const [relative, mode] of Object.entries(case_[`${prefix}_chmod`] ?? {})) {
      fs.chmodSync(path.join(base, relative), Number.parseInt(String(mode), 8));
    }
  }
  return { scratch, project, tree, copies };
}

/**
 * `staleMaterialized` over each row's project and tree (index base 6000).
 * @param {any} module
 * @param {any} data
 * @param {Record<string, any>} table
 * @returns {any[]}
 */
function materializationStale(module, data, table) {
  const results = [];
  for (const [index, case_] of (table.stale ?? []).entries()) {
    if (skippedAsRoot(case_)) {
      continue;
    }
    const { scratch, project, tree, copies } = materializationWorld(case_);
    let actual;
    try {
      actual = withEnvironment({ AITNA_ROOT: case_.aitna_root ?? null }, () =>
        answered(() => module.staleMaterialized(data, project, tree)),
      );
    } finally {
      for (const [prefix, base] of /** @type {Array<[string, string]>} */ ([["project", copies], ["tree", tree]])) {
        for (const relative of Object.keys(case_[`${prefix}_chmod`] ?? {})) {
          fs.chmodSync(path.join(base, relative), 0o700);
        }
      }
      fs.rmSync(scratch, { recursive: true, force: true });
    }
    results.push({ index: 6000 + index, expected: case_.expected ?? null, actual });
  }
  return results;
}

/**
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeMaterialization(tree, table) {
  const module = await loadModule(tree, "js/common/materialization.mjs");
  const data = readData(tree, "common/materialization.json");
  /** @type {any[]} */
  const results = [];
  /**
   * One family of rows, each answered under the AITNA_ROOT the row sets.
   * @param {(case_: any) => unknown} answer
   * @param {number} base
   * @param {string} name
   */
  const family = (answer, base, name) => {
    for (const [index, case_] of (table[name] ?? []).entries()) {
      const actual = withEnvironment({ AITNA_ROOT: case_.aitna_root ?? null }, () => answer(case_));
      results.push({ index: base + index, expected: case_.expected ?? null, actual });
    }
  };
  family(() => module.generatedMarker(data), 0, "marker");
  family(() => module.generatedBanner(data), 1000, "banner");
  family((/** @type {any} */ c) => module.materializedMarkdown(data, c.input), 2000, "markdown");
  family((/** @type {any} */ c) => module.materializedText(data, c.name, c.input), 3000, "text");
  family(() => module.importedDirs(data), 4000, "dirs");
  family((/** @type {any} */ c) => module.materializedDir(c.project_root), 5000, "dir");
  return [...results, ...materializationStale(module, data, table)];
}

// --------------------------------------------------------------------------------------
// The routing mouth (C104) — the twin of probe.py's `probe_routing`, whose block comment is the
// row format. What this side adds is the mapping onto the JS module's API: the Python public name
// becomes its camelCase export; the shared data files the module is handed go first, by the table
// below (the Python module opens them itself); keyword-only parameters ride in a trailing options
// object with camelCase keys; a dataclass is a frozen class built from its fields in declaration
// order, and its instance fields map back to snake_case in the answer. JSON is read with the float
// spelling kept: a number the text spells with a fraction or an exponent and whose value is whole
// (`1.0`, `3.0`) becomes a `FloatValue`, which is what the module honours as a Python float — a
// non-whole number is a float in either language already. Expected and actual compare as the
// canonical form (`json_writer.mjs`, the twin of `json.dumps(sort_keys=True)`), so `1.0` is not
// `1` and `true` is not `1`, as on the Python side.
// --------------------------------------------------------------------------------------

const ROUTING_DATA_FILES = {
  agents: "tools/model_routing/agents.json",
  gate: "tools/model_routing/gate.json",
  runtime: "common/runtime.json",
  markers: "common/markers.json",
};

/**
 * The data documents each export takes before its Python arguments, in parameter order
 * (routing.mjs's header). A name absent here takes none.
 * @type {Record<string, Array<keyof typeof ROUTING_DATA_FILES>>}
 */
const ROUTING_DATA_PARAMS = {
  secondOpinionCommand: ["agents", "runtime"],
  suppressedRebindWarning: ["markers"],
  gateRules: ["gate"],
  gateRuleFor: ["gate"],
  gateAuditRequest: ["gate", "agents"],
  gateAuditOnce: ["gate", "markers"],
  ...Object.fromEntries(
    [
      "overlayName", "localConfigRel", "delegationLogRel", "agentsDirRel", "generatedBanner", "settingsProbeNames",
      "overlayPath", "loadRegistry", "computeBinding", "oppositeVendor", "retiredSecondOpinionKeys",
      "secondOpinionSpec", "secondOpinionUnavailability", "resolveSecondOpinion", "agentSpecs", "agentFileContent",
      "resolveBriefs", "briefWarning", "generatedAgentFiles", "subagentKinds", "boundModelFor", "roleMatrixWarning",
      "contextPressureNotice", "bindingArtifacts", "obsoleteAgentFiles", "removeObsoleteAgents", "rebindTo",
      "localConfig", "staleness", "floorGaps", "floorGapLines", "delegationFloorWarning", "statusLines",
      "rebindNotice", "initInstruction", "zoneConvention", "unlabelledFanoutWarning", "readLocalConfig",
    ].map((name) => [name, /** @type {Array<keyof typeof ROUTING_DATA_FILES>} */ (["agents"])]),
  ),
};

/** The dataclasses' fields in declaration order (snake_case), for `$new` and class rows. */
const ROUTING_CLASS_FIELDS = /** @type {Record<string, string[]>} */ ({
  Binding: ["vendor", "orchestrator", "reasoner", "worker", "mid", "auditor", "escalation", "semantic_fallback", "warning", "second_opinion_cli"],
  SecondOpinionTarget: ["provider", "model"],
  AgentSpec: ["name", "tier", "description", "tools", "body", "kinds"],
  FloorGap: ["kind", "agent", "floor", "bound"],
  DelegationEntry: ["timestamp", "session_id", "subagent", "model", "zone", "description"],
  GateRule: ["role", "trigger", "noun", "headings", "anchor"],
});

const ROUTING_BASE_ENV = ["AKMON_CONTEXT_RECOMMENDED_MAX", "AITNA_ROOT"];
const ROUTING_CONSTRUCTORS = ["$path", "$registry", "$call", "$new"];

/** `snake_case` → `camelCase`; a CamelCase class or SCREAMING constant keeps its name. */
function routingCamel(/** @type {string} */ name) {
  return /^[a-z]/.test(name) ? name.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase()) : name;
}

/** `camelCase` → `snake_case` (an instance field back to its Python name). */
function routingSnake(/** @type {string} */ name) {
  return name.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
}

/**
 * JSON with the float spelling kept: a whole value spelled `1.0` / `1e3` is a `FloatValue`.
 * @param {any} floatValue the json_writer `FloatValue` class of the tree under test
 * @param {string} text
 * @returns {any}
 */
function routingParse(floatValue, text) {
  // The reviver's third argument (the source text, Node >= 21) is not in the lib typing yet.
  /** @type {(text: string, reviver: (key: string, value: any, context: any) => any) => any} */
  const parse = /** @type {any} */ (JSON.parse);
  return parse(text, (_key, value, context) => {
    if (typeof value === "number" && Number.isInteger(value) && /[.eE]/.test(context?.source ?? "")) {
      return new floatValue(value);
    }
    return value;
  });
}

/**
 * One argument with its constructors resolved and `{{dir}}` filled, recursively.
 * @param {any} ctx
 * @param {any} value
 * @returns {any}
 */
function routingArg(ctx, value) {
  if (typeof value === "string") {
    return value.split("{{dir}}").join(ctx.dir);
  }
  if (Array.isArray(value)) {
    return value.map((item) => routingArg(ctx, item));
  }
  if (value === null || typeof value !== "object" || value instanceof ctx.FloatValue) {
    return value;
  }
  if (ROUTING_CONSTRUCTORS.some((key) => key in value)) {
    return routingConstructed(ctx, value);
  }
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, routingArg(ctx, item)]));
}

/** The probe's own deep merge for `$registry.merge` (not the module's). */
function routingDeepMerge(/** @type {any} */ base, /** @type {any} */ override) {
  const merged = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const both = [value, merged[key]].every((v) => v !== null && typeof v === "object" && !Array.isArray(v));
    merged[key] = both ? routingDeepMerge(merged[key], value) : value;
  }
  return merged;
}

/**
 * The value one constructor object stands for.
 * @param {any} ctx
 * @param {any} value
 * @returns {any}
 */
function routingConstructed(ctx, value) {
  if ("$path" in value) {
    return routingArg(ctx, value.$path);
  }
  if ("$registry" in value) {
    const change = value.$registry;
    let registry = routingParse(ctx.FloatValue, ctx.registryText);
    Object.assign(registry, routingArg(ctx, change.set ?? {}));
    registry = routingDeepMerge(registry, routingArg(ctx, change.merge ?? {}));
    for (const key of change.drop ?? []) {
      delete registry[key];
    }
    ctx.hashes.add(createHash("sha256").update(ctx.canonicalForm(registry), "utf8").digest("hex").slice(0, 16));
    return registry;
  }
  if ("$call" in value) {
    const answer = routingCall(ctx, { fn: value.$call, args: value.args ?? [], kwargs: value.kwargs ?? {} });
    return "pick" in value ? answer[value.pick] : answer;
  }
  return routingNew(ctx, value.$new, routingArg(ctx, value.fields ?? {}));
}

/** A dataclass from its snake_case fields, in the declaration order of `ROUTING_CLASS_FIELDS`. */
function routingNew(/** @type {any} */ ctx, /** @type {string} */ name, /** @type {Record<string, any>} */ fields) {
  const order = ROUTING_CLASS_FIELDS[name] ?? [];
  return new ctx.module[name](...order.map((field) => fields[field]));
}

/**
 * Call one public name: data documents first, then the arguments, then the options object.
 * @param {any} ctx
 * @param {{fn: string, args?: any[], kwargs?: Record<string, any>}} call
 * @returns {any}
 */
function routingCall(ctx, call) {
  const name = routingCamel(call.fn);
  const target = ctx.module[name];
  if (target === undefined) {
    throw new Error(`probe: routing.mjs exports no ${name} (for ${call.fn})`);
  }
  const args = routingArg(ctx, call.args ?? []);
  const kwargs = routingArg(ctx, call.kwargs ?? {});
  if (name in ROUTING_CLASS_FIELDS) {
    return routingNew(ctx, name, { ...Object.fromEntries(args.map((/** @type {any} */ a, /** @type {number} */ i) => [ROUTING_CLASS_FIELDS[name][i], a])), ...kwargs });
  }
  if (typeof target !== "function") {
    return target;
  }
  const data = (ROUTING_DATA_PARAMS[name] ?? []).map((file) => ctx.data[file]);
  const options = Object.fromEntries(Object.entries(kwargs).map(([key, value]) => [routingCamel(key), value]));
  return target(...data, ...args, ...(Object.keys(options).length > 0 ? [options] : []));
}

/**
 * An answer in table form: class instances keyed by snake_case fields, Maps in order.
 * @param {any} ctx
 * @param {any} value
 * @returns {any}
 */
function routingJson(ctx, value) {
  if (value === undefined) {
    return null;
  }
  if (value === null || typeof value !== "object" || value instanceof ctx.FloatValue) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => routingJson(ctx, item));
  }
  const entries = value instanceof Map ? [...value.entries()] : Object.entries(value);
  const isClass = !(value instanceof Map) && Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null;
  return Object.fromEntries(entries.map(([key, item]) => [isClass ? routingSnake(key) : key, routingJson(ctx, item)]));
}

/** An object answer as its ordered [key, value] pairs (from the Map or instance it came as). */
function routingPairs(/** @type {any} */ ctx, /** @type {any} */ raw) {
  const entries = raw instanceof Map ? [...raw.entries()] : Object.entries(raw);
  return entries.map(([key, item]) => [key, routingJson(ctx, item)]);
}

/**
 * Every string of an answer with the scratch path, agent bodies and registry hashes tokenized.
 * @param {any} ctx
 * @param {any} value
 * @returns {any}
 */
function routingText(ctx, value) {
  if (typeof value === "string") {
    let text = value.split(ctx.dir).join("{{dir}}");
    for (const [name, body] of ctx.bodies) {
      text = text.split(body).join(`{{body:${name}}}`);
    }
    for (const digest of ctx.hashes) {
      text = text.split(digest).join("{{registry_hash}}");
    }
    return text;
  }
  if (Array.isArray(value)) {
    return value.map((item) => routingText(ctx, item));
  }
  if (value !== null && typeof value === "object" && !(value instanceof ctx.FloatValue)) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [routingText(ctx, key), routingText(ctx, item)]));
  }
  return value;
}

/** The files under `base`: relpath → text (or `{hex}` when not UTF-8), with modes on request. */
function routingTree(/** @type {string} */ base, /** @type {boolean} */ withModes) {
  /** @type {Record<string, any>} */
  const tree = {};
  if (!fs.existsSync(base) || !fs.statSync(base).isDirectory()) {
    return tree;
  }
  const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
  const walk = (/** @type {string} */ folder) => {
    for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
      const full = path.join(folder, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile()) {
        const raw = fs.readFileSync(full);
        /** @type {any} */
        let content;
        try {
          content = decoder.decode(raw);
        } catch {
          content = { hex: raw.toString("hex") };
        }
        if (withModes) {
          content = { text: content, mode: (fs.statSync(full).mode & 0o7777).toString(8) };
        }
        tree[path.relative(base, full).split(path.sep).join("/")] = content;
      }
    }
  };
  walk(base);
  return tree;
}

/** Write the row's files, then set the mtimes and modes it names. */
function routingWorld(/** @type {string} */ scratch, /** @type {any} */ case_) {
  /** @type {Array<[string, Buffer]>} */
  const contents = Object.entries(case_.files ?? {}).map(([relative, text]) => [relative, Buffer.from(String(text), "utf-8")]);
  for (const [relative, parts] of Object.entries(case_.files_parts ?? {})) {
    const chunks = /** @type {any[]} */ (parts).map((part) => {
      if (typeof part === "string") {
        return Buffer.from(part, "utf-8");
      }
      if ("hex" in part) {
        return Buffer.from(part.hex, "hex");
      }
      return Buffer.from(String(part.repeat).repeat(part.times), "utf-8");
    });
    contents.push([relative, Buffer.concat(chunks)]);
  }
  for (const [relative, data] of contents) {
    fs.mkdirSync(path.dirname(path.join(scratch, relative)), { recursive: true });
    fs.writeFileSync(path.join(scratch, relative), data);
  }
  for (const [relative, seconds] of Object.entries(case_.mtimes ?? {})) {
    const moment = Date.now() / 1000 - Number(seconds);
    fs.utimesSync(path.join(scratch, relative), moment, moment);
  }
  for (const [relative, mode] of Object.entries(case_.modes ?? {})) {
    fs.chmodSync(path.join(scratch, relative), Number.parseInt(String(mode), 8));
  }
}

/** The row's answer in table form, a raise included. */
function routingAnswer(/** @type {any} */ ctx, /** @type {any} */ case_) {
  for (const setup of routingParse(ctx.FloatValue, case_.setup_json ?? "[]")) {
    routingCall(ctx, setup);
  }
  const call = {
    fn: case_.fn,
    args: routingParse(ctx.FloatValue, case_.args_json ?? "[]"),
    kwargs: routingParse(ctx.FloatValue, case_.kwargs_json ?? "{}"),
  };
  /** @type {any} */
  let raw;
  try {
    raw = routingCall(ctx, call);
  } catch (error) {
    const caught = /** @type {Error} */ (error);
    return { error: caught.name, message: routingText(ctx, caught.message) };
  }
  const isObject = raw !== null && typeof raw === "object" && !Array.isArray(raw) && !(raw instanceof ctx.FloatValue);
  const value = routingText(ctx, case_.ordered === true && isObject ? routingPairs(ctx, raw) : routingJson(ctx, raw));
  if (!("tree" in case_)) {
    return value;
  }
  const tree = routingTree(path.join(ctx.dir, case_.tree), case_.tree_modes === true);
  return { value, tree: routingText(ctx, tree) };
}

/** One row in its own scratch directory and environment, both restored afterwards. */
function routingCase(/** @type {any} */ base, /** @type {any} */ case_) {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-probe-routing-"));
  const ctx = { ...base, dir: scratch, hashes: new Set() };
  /** @type {Record<string, string | null>} */
  const changes = Object.fromEntries(ROUTING_BASE_ENV.map((name) => [name, null]));
  changes.TMPDIR = scratch;
  for (const [name, value] of Object.entries(case_.env ?? {})) {
    changes[name] = value === "" ? null : String(value).split("{{dir}}").join(scratch);
  }
  const previous = process.umask(0o022);
  try {
    routingWorld(scratch, case_);
    return withEnvironment(changes, () => routingAnswer(ctx, case_));
  } finally {
    process.umask(previous);
    for (const relative of Object.keys(case_.modes ?? {})) {
      try {
        fs.chmodSync(path.join(scratch, relative), 0o700);
      } catch {
        // gone already: nothing to restore
      }
    }
    fs.rmSync(scratch, { recursive: true, force: true });
  }
}

/**
 * A value the main document can print: a `FloatValue` as its number.
 * @param {any} ctx
 * @param {any} value
 * @returns {any}
 */
function routingPrintable(ctx, value) {
  if (value instanceof ctx.FloatValue) {
    return value.n;
  }
  if (Array.isArray(value)) {
    return value.map((item) => routingPrintable(ctx, item));
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, routingPrintable(ctx, item)]));
  }
  return value;
}

/**
 * The model-routing core, one public call per row, against the tree's routing.mjs.
 * @param {string} tree
 * @param {Record<string, any>} table
 * @returns {Promise<any[]>}
 */
async function probeRouting(tree, table) {
  const module = await loadModule(tree, "js/tools/model_routing/routing.mjs");
  const writer = await loadModule(tree, "js/common/json_writer.mjs");
  const data = Object.fromEntries(Object.entries(ROUTING_DATA_FILES).map(([key, relative]) => [key, readData(tree, relative)]));
  const base = {
    module,
    FloatValue: writer.FloatValue,
    canonicalForm: writer.canonicalForm,
    data,
    registryText: fs.readFileSync(path.join(tree, "tools/model_routing/registry.json"), "utf-8"),
    bodies: data.agents.agent_specs.map((/** @type {any} */ spec) => [spec.name, spec.body]),
  };
  const results = [];
  for (const [index, case_] of (table.case ?? []).entries()) {
    if (skippedAsRoot(case_)) {
      continue;
    }
    const expected = routingParse(writer.FloatValue, case_.expected_json);
    let actual = routingCase(base, case_);
    if (writer.canonicalForm(expected) === writer.canonicalForm(actual)) {
      actual = expected;
    } else if (deepEqual(routingPrintable(base, expected), routingPrintable(base, actual))) {
      actual = { strictly: writer.canonicalForm(actual) }; // `1.0` against `1`: the print would hide it
    }
    results.push({ index, id: case_.id, expected: routingPrintable(base, expected), actual: actual === expected ? routingPrintable(base, expected) : routingPrintable(base, actual) });
  }
  return results;
}

/** @type {Record<string, (tree: string, table: any, text: string) => Promise<any[]>>} */
const PROBES = {
  versions: probeVersions,
  record: probeRecord,
  shlex: probeShlex,
  glob: probeGlob,
  json: probeJson,
  sort: probeSort,
  runtime: probeRuntime,
  check_runner: probeCheckRunner,
  markers: probeMarkers,
  materialization: probeMaterialization,
  routing: probeRouting,
};

/**
 * @param {string[]} [argv]
 * @returns {Promise<number>}
 */
async function main(argv) {
  const args = argv ?? process.argv.slice(2);
  const positionals = [];
  let tree = REPO_ROOT;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--tree") {
      tree = path.resolve(args[++i] ?? "");
    } else {
      positionals.push(args[i]);
    }
  }
  if (positionals.length !== 2) {
    process.stderr.write("usage: probe.mjs <probe> <table.toml> [--tree REPO]\n");
    return 2;
  }
  const [probeName, tablePath] = positionals;
  if (!(probeName in PROBES)) {
    process.stderr.write(`probe.mjs: unknown probe ${JSON.stringify(probeName)}; known: ${[...Object.keys(PROBES)].sort().join(", ")}\n`);
    return 2;
  }
  const text = fs.readFileSync(tablePath, "utf-8");
  const table = smol.parse(text);
  const results = await PROBES[probeName](tree, table, text);
  const failed = results.filter((/** @type {any} */ r) => !deepEqual(r.expected, r.actual));
  process.stdout.write(JSON.stringify({ ok: failed.length === 0, failed }, null, 2) + "\n");
  return failed.length === 0 ? 0 : 1;
}

// The entry guard dereferences both sides: node hands the main module's URL in its physical
// form while `argv[1]` keeps the path it was given, so a snapshot reached through a symlink
// (a `/tmp` that is a link) leaves this file loaded and silent — measured as exit 0 with an
// empty stdout, which the runner reports as a units scenario whose document does not match the
// pinned one: red, but naming nothing about the cause.
if (process.argv[1] !== undefined && _realpath(path.resolve(process.argv[1])) === _realpath(fileURLToPath(import.meta.url))) {
  const code = await main();
  process.exit(code);
}

export { main };
