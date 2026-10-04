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

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

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
