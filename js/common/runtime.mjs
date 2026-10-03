/**
 * What akmon needs on a host, and the one owner of every optional-harness command — the
 * JavaScript twin of `common/runtime.py` (ADR 0020 D01). The declarations and the harness
 * table come from `common/runtime.json`, read once at the entry point and passed down: this
 * module never reads a file itself (the C102/C103 data convention), so the table has exactly
 * one reader per process.
 */

import { codePointSort } from "./sort.mjs";

/** The two populations. A runtime belongs to exactly one. */
export const GENERATED_WIRING = "generated-wiring";
export const OWN_TOOLING = "akmon-own-tooling";
/** The shell that runs every generated command string; it has no executable name of its own. */
export const POSIX_SHELL = "POSIX shell";
/** Modalities. `required-on:<route>` names the vendor route that needs the runtime. */
export const REQUIRED = "required";
export const OPTIONAL = "optional";
export const REQUIRED_ON = "required-on:";

/** @typedef {{binary: string, population: string, modality: string}} RuntimeDeclaration */
/** @typedef {{binary: string, operations: Record<string, string[]>}} HarnessCommands */
/** The shape of `common/runtime.json`: the ordered declarations and the harness table. */
/** @typedef {{declared_runtimes: [string, string, string][], harness_commands: Record<string, HarnessCommands>}} RuntimeData */

/**
 * The ordered runtime declarations, as `common/runtime.json` carries them.
 * @param {RuntimeData} data the parsed `common/runtime.json`
 * @returns {RuntimeDeclaration[]}
 */
export function declaredRuntimes(data) {
  return data.declared_runtimes.map(([binary, population, modality]) => ({ binary, population, modality }));
}

/**
 * The harness table: each executable name and its operation prefixes. The answer is a fresh
 * copy — a caller mutating it cannot corrupt the data document the next read would give.
 * @param {RuntimeData} data the parsed `common/runtime.json`
 * @returns {Record<string, HarnessCommands>}
 */
export function harnessCommands(data) {
  /** @type {Record<string, HarnessCommands>} */
  const table = {};
  for (const [name, spec] of Object.entries(data.harness_commands)) {
    /** @type {Record<string, string[]>} */
    const operations = {};
    for (const [operation, argv] of Object.entries(spec.operations)) {
      operations[operation] = [...argv];
    }
    table[name] = { binary: spec.binary, operations };
  }
  return table;
}

/**
 * Every optional-harness executable name akmon knows how to invoke (sorted, duplicates kept,
 * the Python twin's answer).
 * @param {RuntimeData} data the parsed `common/runtime.json`
 * @returns {string[]}
 */
export function harnessBinaries(data) {
  return codePointSort(Object.values(harnessCommands(data)).map((spec) => spec.binary));
}

/**
 * The argv for `operation` on `harness`, plus any caller-supplied policy tail. The single
 * constructor of the executable-plus-operation prefix: a caller needing a different
 * operation adds it to the `common/runtime.json` table rather than assembling a prefix.
 * @param {RuntimeData} data the parsed `common/runtime.json`
 * @param {string} harness
 * @param {string} operation
 * @param {...string} extra
 * @returns {string[]}
 */
export function harnessCommand(data, harness, operation, ...extra) {
  const table = harnessCommands(data);
  const spec = table[harness];
  if (spec === undefined) {
    throw new Error(`unknown harness '${harness}'; known: ${codePointSort(Object.keys(table)).join(", ")}`);
  }
  const tail = spec.operations[operation];
  if (tail === undefined) {
    throw new Error(
      `harness '${harness}' declares no operation '${operation}'; known: ` +
        codePointSort(Object.keys(spec.operations)).join(", "),
    );
  }
  return [spec.binary, ...tail, ...extra];
}

/**
 * The harness-version query. `sync` reads it to pick a generated inventory.
 * @param {RuntimeData} data the parsed `common/runtime.json`
 * @param {string} harness
 * @returns {string[]}
 */
export function versionCommand(data, harness) {
  return harnessCommand(data, harness, "version");
}

/**
 * The bounded `codex app-server` invocation the host-trust check speaks JSON-RPC over.
 * @param {RuntimeData} data the parsed `common/runtime.json`
 * @returns {string[]}
 */
export function codexHooksListCommand(data) {
  return harnessCommand(data, "codex", "hooks-list");
}
