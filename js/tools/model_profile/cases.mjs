/**
 * The probe item set: load it, validate it, and name the measurement it defines — the JavaScript
 * twin of `tools/model_profile/cases.py` (ADR 0020 D01); the Python module is the reference.
 *
 * The item set is the yardstick. A case is a small synthetic program with one planted defect, clean
 * decoy files beside it, a hidden test that must separate the buggy program from the fixed one, and
 * one ask per family. Two hashes identify the measurement, and they are IDENTICAL across the twins:
 *
 * - `casesSha` — the content of the item set: the items file itself plus every embedded file
 *   source, hashed by content and never by filename;
 * - `envelopeSha` — the request envelope: the pinned temperature, the output-token cap, the timeout,
 *   the response format and the system prompts used. The payload is written the way Python's
 *   `json.dumps(sort_keys=True, separators=(",", ":"))` writes it (`canonicalForm`, the temperature
 *   as a float), so it is the same bytes' hash.
 *
 * The set is validated at load time and a malformed set throws — it never half-loads.
 * `fixedFiles` is a patch over `files`, not a second full program.
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import { posix } from "node:path";

import { FloatValue, canonicalForm } from "../../common/json_writer.mjs";
import { codePointCompare, codePointSort } from "../../common/sort.mjs";
import * as settings from "./settings.mjs";

/** The item set is malformed — thrown at load time, never half-loaded. */
export class ItemSetError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "ItemSetError";
  }
}

/**
 * @typedef {object} Bug
 * @property {string} file
 * @property {string} function
 * @property {string} kind
 */

/**
 * @typedef {object} Ask
 * @property {string} system
 * @property {string} user
 */

/**
 * One probe item: a buggy program, its fixed twin, an oracle and one ask per family.
 * @typedef {object} Case
 * @property {string} id
 * @property {string[]} families
 * @property {Bug} bug
 * @property {Record<string, string>} files
 * @property {Record<string, string>} fixedFiles
 * @property {{path: string, content: string}} hiddenTest
 * @property {Record<string, Ask>} asks
 */

/**
 * The pinned request envelope — everything that makes two scores comparable.
 * @typedef {object} Envelope
 * @property {number} temperature
 * @property {number} maxOutputTokens
 * @property {number} timeoutS
 * @property {string} responseFormat
 */

/**
 * A validated item set and the two hashes that identify it.
 * @typedef {object} ItemSet
 * @property {string} version
 * @property {Case[]} cases
 * @property {string} casesSha
 * @property {string} envelopeSha
 * @property {string[]} families
 */

/**
 * The default envelope, from `profile.json`.
 * @param {Partial<Envelope>} [overrides]
 * @returns {Envelope}
 */
export function makeEnvelope(overrides = {}) {
  return { ...settings.load().envelope, ...overrides };
}

/**
 * The buggy program as the sandbox sees it.
 * @param {Case} item
 * @returns {Record<string, string>}
 */
export function program(item) {
  return { ...item.files };
}

/**
 * The fixed program: the case's files with `fixedFiles` patched over them.
 * @param {Case} item
 * @returns {Record<string, string>}
 */
export function fixedProgram(item) {
  return { ...item.files, ...item.fixedFiles };
}

/**
 * The prompt for `family` — throws when the case does not carry that family.
 * @param {Case} item
 * @param {string} family
 * @returns {Ask}
 */
export function askOf(item, family) {
  const ask = Object.hasOwn(item.asks, family) ? item.asks[family] : undefined;
  if (ask === undefined) {
    throw new ItemSetError(`case '${item.id}' has no ask for family '${family}'`);
  }
  return ask;
}

/**
 * The cases of a set, narrowed by id and by family.
 * @param {ItemSet} itemSet
 * @param {readonly string[] | null} [caseIds]
 * @param {readonly string[] | null} [families]
 * @returns {Case[]}
 */
export function selectCases(itemSet, caseIds = null, families = null) {
  const wantedIds = caseIds === null ? null : new Set(caseIds);
  const chosen = itemSet.cases.filter((item) => wantedIds === null || wantedIds.has(item.id));
  if (families === null) {
    return chosen;
  }
  const wanted = new Set(families);
  return chosen.filter((item) => item.families.some((family) => wanted.has(family)));
}

/**
 * @param {import("node:crypto").Hash} digest
 * @param {string} text
 */
function updateWithText(digest, text) {
  digest.update(Buffer.from(text, "utf8"));
  digest.update(Buffer.from([0]));
}

/**
 * The hash of the item set's content: the items file plus every embedded source. Content, never
 * filename: moving the items file does not change the hash, editing a fixture does.
 * @param {Uint8Array} raw
 * @param {readonly Case[]} cases
 * @returns {string}
 */
export function casesSha(raw, cases) {
  const digest = createHash("sha256");
  digest.update(raw);
  for (const item of [...cases].sort((a, b) => codePointCompare(a.id, b.id))) {
    for (const path of codePointSort(Object.keys(item.files))) {
      updateWithText(digest, item.files[path]);
    }
    for (const path of codePointSort(Object.keys(item.fixedFiles))) {
      updateWithText(digest, item.fixedFiles[path]);
    }
    updateWithText(digest, item.hiddenTest.content);
  }
  return digest.digest("hex").slice(0, settings.load().hashLength);
}

/**
 * The hash of the request envelope: its knobs and the system prompts used.
 * @param {Envelope} envelope
 * @param {readonly string[]} systemPrompts
 * @returns {string}
 */
export function envelopeSha(envelope, systemPrompts) {
  const payload = {
    temperature: new FloatValue(envelope.temperature),
    max_output_tokens: envelope.maxOutputTokens,
    timeout_s: envelope.timeoutS,
    response_format: envelope.responseFormat,
    system_prompts: codePointSort([...new Set(systemPrompts)]),
  };
  return createHash("sha256").update(canonicalForm(payload), "utf8").digest("hex").slice(0, settings.load().hashLength);
}

/**
 * Python's name for a JSON value's type, for the message of a type error.
 * @param {unknown} value
 * @returns {string}
 */
function typeName(value) {
  if (value === null) {
    return "NoneType";
  }
  if (Array.isArray(value)) {
    return "list";
  }
  switch (typeof value) {
    case "string":
      return "str";
    case "boolean":
      return "bool";
    case "number":
      return Number.isInteger(value) ? "int" : "float";
    default:
      return "dict";
  }
}

/**
 * @param {unknown} value
 * @param {string} where
 * @returns {Record<string, unknown>}
 */
function requireMapping(value, where) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ItemSetError(`${where} must be an object, got ${typeName(value)}`);
  }
  return /** @type {Record<string, unknown>} */ (value);
}

/**
 * @param {unknown} value
 * @param {string} where
 * @returns {string}
 */
function requireText(value, where) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new ItemSetError(`${where} must be a non-empty string`);
  }
  return value;
}

/**
 * @param {unknown} value
 * @param {string} where
 * @returns {string}
 */
function requireRelativePath(value, where) {
  const text = requireText(value, where);
  if (posix.isAbsolute(text) || text.split("/").includes("..")) {
    throw new ItemSetError(`${where} must stay inside the case, got '${text}'`);
  }
  return text;
}

/**
 * @param {Record<string, unknown>} mapping
 * @param {readonly string[]} keys
 * @param {string} where
 */
function requireKeys(mapping, keys, where) {
  const missing = keys.filter((key) => !Object.hasOwn(mapping, key));
  if (missing.length > 0) {
    throw new ItemSetError(`${where} is missing ${missing.join(", ")}`);
  }
}

/**
 * @param {unknown} raw
 * @param {string} where
 * @returns {Bug}
 */
function parseBug(raw, where) {
  const mapping = requireMapping(raw, where);
  requireKeys(mapping, settings.load().caseKeys.bug, where);
  return {
    file: requireRelativePath(mapping.file, `${where}.file`),
    function: requireText(mapping.function, `${where}.function`),
    kind: requireText(mapping.kind, `${where}.kind`),
  };
}

/**
 * @param {unknown} raw
 * @param {string} where
 * @returns {Record<string, string>}
 */
function parseFiles(raw, where) {
  const mapping = requireMapping(raw, where);
  /** @type {Record<string, string>} */
  const files = {};
  for (const [path, source] of Object.entries(mapping)) {
    files[requireRelativePath(path, `${where} path`)] = requireText(source, `${where}['${path}']`);
  }
  if (Object.keys(files).length === 0) {
    throw new ItemSetError(`${where} is empty - a case needs a program to run`);
  }
  return files;
}

/**
 * @param {unknown} raw
 * @param {string} where
 * @param {Record<string, string>} files
 * @returns {{path: string, content: string}}
 */
function parseHiddenTest(raw, where, files) {
  const mapping = requireMapping(raw, where);
  requireKeys(mapping, settings.load().caseKeys.hiddenTest, where);
  const path = requireRelativePath(mapping.path, `${where}.path`);
  const content = requireText(mapping.content, `${where}.content`);
  if (Object.hasOwn(files, path)) {
    throw new ItemSetError(`${where}.path '${path}' collides with a program file of the case`);
  }
  return { path, content };
}

/**
 * @param {unknown} raw
 * @param {string} where
 * @param {readonly string[]} families
 * @returns {Record<string, Ask>}
 */
function parseAsks(raw, where, families) {
  const mapping = requireMapping(raw, where);
  /** @type {Record<string, Ask>} */
  const asks = {};
  for (const [family, value] of Object.entries(mapping)) {
    if (!settings.load().families.known.includes(family)) {
      throw new ItemSetError(`${where} carries an unknown family '${family}'`);
    }
    const askMapping = requireMapping(value, `${where}['${family}']`);
    requireKeys(askMapping, settings.load().caseKeys.ask, `${where}['${family}']`);
    asks[family] = {
      system: requireText(askMapping.system, `${where}['${family}'].system`),
      user: requireText(askMapping.user, `${where}['${family}'].user`),
    };
  }
  const absent = families.filter((family) => !Object.hasOwn(asks, family));
  if (absent.length > 0) {
    throw new ItemSetError(`${where} has no ask for ${codePointSort(absent).join(", ")}`);
  }
  return asks;
}

/**
 * @param {unknown} raw
 * @param {string} where
 * @returns {string[]}
 */
function parseFamilies(raw, where) {
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new ItemSetError(`${where} must be a non-empty list`);
  }
  /** @type {string[]} */
  const families = [];
  for (const family of raw) {
    const name = requireText(family, `${where} entry`);
    if (!settings.load().families.known.includes(name)) {
      throw new ItemSetError(`${where} names an unknown family '${name}'`);
    }
    if (families.includes(name)) {
      throw new ItemSetError(`${where} names '${name}' twice`);
    }
    families.push(name);
  }
  return families;
}

/**
 * @param {unknown} raw
 * @param {number} index
 * @returns {Case}
 */
function parseCase(raw, index) {
  const where = `cases[${index}]`;
  const mapping = requireMapping(raw, where);
  requireKeys(mapping, settings.load().caseKeys.case, where);
  const families = parseFamilies(mapping.families, `${where}.families`);
  const files = parseFiles(mapping.files, `${where}.files`);
  const fixedFiles = parseFiles(mapping.fixed_files, `${where}.fixed_files`);
  for (const path of Object.keys(fixedFiles)) {
    if (!Object.hasOwn(files, path)) {
      throw new ItemSetError(`${where}.fixed_files patches '${path}', which the case does not carry`);
    }
  }
  const bug = parseBug(mapping.bug, `${where}.bug`);
  if (!Object.hasOwn(files, bug.file)) {
    throw new ItemSetError(`${where}.bug.file '${bug.file}' is not one of the case's files`);
  }
  return {
    id: requireText(mapping.id, `${where}.id`),
    families,
    bug,
    files,
    fixedFiles,
    hiddenTest: parseHiddenTest(mapping.hidden_test, `${where}.hidden_test`, files),
    asks: parseAsks(mapping.asks, `${where}.asks`, families),
  };
}

/**
 * The document of an items file, decoded strictly (a BOM is kept, so JSON refuses it as Python does).
 * @param {string} path
 * @param {Uint8Array} raw
 * @returns {unknown}
 */
function decodeDocument(path, raw) {
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(raw));
  } catch (exc) {
    throw new ItemSetError(`the item set at ${path} is not valid JSON: ${/** @type {Error} */ (exc).message}`);
  }
}

/**
 * Load, validate and hash the item set at `path`.
 * @param {string} path
 * @param {Envelope | null} [envelope]
 * @returns {ItemSet}
 * @throws {ItemSetError} anything is malformed — a half-loaded set is never returned
 */
export function loadItemSet(path, envelope = null) {
  /** @type {Uint8Array} */
  let raw;
  try {
    raw = fs.readFileSync(path);
  } catch (exc) {
    throw new ItemSetError(`cannot read the item set at ${path}: ${/** @type {Error} */ (exc).message}`);
  }
  const mapping = requireMapping(decodeDocument(path, raw), `item set ${path}`);
  const casesRaw = mapping.cases;
  if (!Array.isArray(casesRaw) || casesRaw.length === 0) {
    throw new ItemSetError(`the item set at ${path} carries no cases`);
  }
  const cases = casesRaw.map((rawCase, index) => parseCase(rawCase, index));
  if (new Set(cases.map((item) => item.id)).size !== cases.length) {
    throw new ItemSetError(`the item set at ${path} carries a case id twice`);
  }
  const prompts = cases.flatMap((item) => Object.values(item.asks).map((ask) => ask.system));
  return {
    version: requireText(mapping.version, `item set ${path}.version`),
    cases,
    casesSha: casesSha(raw, cases),
    envelopeSha: envelopeSha(envelope ?? makeEnvelope(), prompts),
    families: codePointSort([...new Set(cases.flatMap((item) => item.families))]),
  };
}
