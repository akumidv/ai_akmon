/**
 * The shared data files the hooks read, as one lazily-read bundle (C104).
 *
 * The convention (design §4) is that a JS module never reads shared JSON itself: the entry
 * point reads each file and passes the parsed document down as a parameter. A hook reads
 * several (`hooks/hook_core.json`, `hooks/vocabulary.json`, `common/markers.json`, …) and the
 * Python reads each one **when the decision first needs it** — a broken or missing file fails
 * only the hooks that reach it, with `DataFileError` on the crash line. The bundle keeps
 * exactly that: each property is read on first access, once per process, so which hooks fail
 * on which broken file is the Python's answer, and a hook pays only for the files it uses.
 *
 * A pure module (`hook_core`, the adapters) takes this bundle as its first parameter, `data`.
 * A test or a probe passes a plain object holding the same properties. Paths follow the
 * Python readers: each file sits beside its `.py` reader, under the tree root.
 */

import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { read } from "../common/jsondata.mjs";

/** @typedef {import("../common/markers.mjs").MarkersData} MarkersData */
/** @typedef {import("../common/materialization.mjs").MaterializationData} MaterializationData */
/** @typedef {import("../common/runtime.mjs").RuntimeData} RuntimeData */
/** @typedef {import("../tools/model_routing/routing.mjs").AgentsData} AgentsData */
/** @typedef {import("../tools/model_routing/routing.mjs").GateData} GateData */

/**
 * The shape of `hooks/hook_core.json`, `hooks/vocabulary.json`, `hooks/codex_hook.json` and
 * `hooks/delegation_log.json` — each data file owns its keys; the modules that read a key type it.
 * @typedef {any} HookDocument
 */

/**
 * The bundle a hook decision reads its data from.
 * @typedef {object} HookData
 * @property {HookDocument} core `hooks/hook_core.json`
 * @property {HookDocument} vocabulary `hooks/vocabulary.json`
 * @property {MarkersData} markers `common/markers.json`
 * @property {MaterializationData} materialization `common/materialization.json`
 * @property {HookDocument} codex `hooks/codex_hook.json`
 * @property {HookDocument} delegationLog `hooks/delegation_log.json`
 * @property {AgentsData} agents `tools/model_routing/agents.json`
 * @property {GateData} gate `tools/model_routing/gate.json`
 * @property {RuntimeData} runtime `common/runtime.json`
 */

/** The tree this module executes from: `<tree>/js/hooks/hook_data.mjs` → `<tree>`. */
export const TREE_ROOT = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** The property of the bundle → the data file's tree-relative path. */
const FILES = {
  core: "hooks/hook_core.json",
  vocabulary: "hooks/vocabulary.json",
  markers: "common/markers.json",
  materialization: "common/materialization.json",
  codex: "hooks/codex_hook.json",
  delegationLog: "hooks/delegation_log.json",
  agents: "tools/model_routing/agents.json",
  gate: "tools/model_routing/gate.json",
  runtime: "common/runtime.json",
};

/**
 * A bundle whose files are read on first access.
 * @param {string} [treeRoot] the tree the data files sit in (default: the tree this module is in)
 * @returns {HookData}
 */
export function lazyHookData(treeRoot = TREE_ROOT) {
  /** @type {Record<string, unknown>} */
  const bundle = {};
  for (const [name, relative] of Object.entries(FILES)) {
    /** @type {{value: unknown} | null} */
    let loaded = null;
    Object.defineProperty(bundle, name, {
      enumerable: true,
      get() {
        loaded ??= { value: read(posix.join(treeRoot, relative)) };
        return loaded.value;
      },
    });
  }
  return /** @type {HookData} */ (bundle);
}
