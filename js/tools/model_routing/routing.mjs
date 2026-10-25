/**
 * Model-routing core: registry loading, tier binding, generated-agent content — the JavaScript
 * twin of `tools/model_routing/routing.py` (ADR 0020 D01). The Python module is the spec: the
 * same answers, the same texts, byte for byte. Vocabulary and policy: MODEL.md § Capability
 * tiers; the registry (`registry.json`) is the single owner of semantic selection policy and
 * task-kind data.
 *
 * Data (the C102/C103 convention): this module never reads a shared data file itself. The
 * caller reads each file once at its entry point (`js/common/jsondata.mjs` `read`) and passes
 * the parsed document down — named `data` when a function needs one file, `<name>Data` when it
 * needs two:
 *
 *   tools/model_routing/agents.json → `data` / `agentsData` (texts, tables, the agent roster)
 *   tools/model_routing/gate.json   → `data` / `gateData`   (gateRules, gateRuleFor and the gate)
 *   common/runtime.json             → `runtimeData`         (opinionCommand, carrierPresent, via the harness table)
 *   common/markers.json             → `markersData`         (suppressedRebindWarning, gateAuditOnce)
 *
 * `second_opinion.json` is not read here (its reader is `second_opinion.py`). The registry and
 * its project overlay are not shared data but the run's own input: `loadRegistry` reads them,
 * as the Python does, and so do the transcript readers, the local-config reader and the
 * artifact writers — those file operations are this module's contract.
 *
 * Signatures: a Python positional parameter stays positional (camelCase), a keyword-only one
 * moves into a trailing options object (`{markerDir}`, `{turn}`, `{write}`, `{required}`); a
 * dataclass becomes a frozen class whose constructor takes the fields in declaration order; a
 * returned tuple is an array; a `Path` is a string spelled as `str(Path)` spells it.
 *
 * Twin notes — every place the stdlib answers differently from Node's:
 * - JavaScript has one number type, so a float the source spelled whole (`3.0`) would read as
 *   the int `3`. The documents a person may edit — the registry and its overlay (`loadRegistry`)
 *   and the local config (`readLocalConfig`) — are read with the spelling kept: such a number
 *   becomes a `FloatValue` (`js/common/json_writer.mjs`), which every numeric check here honours
 *   as a Python float, as it does for a caller that passes one. A transcript line is plain
 *   `JSON.parse` (a hot path whose token counts are never float-spelled): a whole float there
 *   reads as an int — the documented divergence. An integer beyond 2**53 is not exact here;
 *   Python's `json` also accepts the non-JSON literals `NaN`/`Infinity`, which `JSON.parse`
 *   refuses;
 * - Python truthiness (`[]` and `{}` are false), `str()`/`repr()` of a JSON value, `==` between
 *   numbers and booleans, `in` over a list, a string or a dict, and `.get` on a non-dict (which
 *   raises) are ported as the `_truthy`/`_pyStr`/`_pyRepr`/`_pyEq`/`_contains`/`_get` helpers;
 * - `str.split()`/`strip()` with no argument, `splitlines()`, `len()` and `int(str)` follow the
 *   Python whitespace, line-break, code-point and Unicode-digit rules, never JavaScript's `trim`,
 *   `\s` or UTF-16 length;
 * - the module's patterns are `re.ASCII` on the Python side and spelled with explicit ASCII
 *   classes here; `_HEADING_WORD_RE` stays Unicode on purpose (C98) and is
 *   `[\p{L}\p{Nl}\p{No}]` — Python's `[^\W\d_]` exactly, up to the Unicode version each
 *   runtime ships (a code point Python's database leaves unassigned may be a letter here);
 * - `str.lower()` is `toLowerCase()`, equal under the same Unicode-version caveat;
 * - a transcript line decodes as strict UTF-8 with a leading BOM kept (Python's `utf-8` codec,
 *   not `utf-8-sig`); a file read as text gets universal-newline translation, as `read_text`;
 * - `f"{x:.0%}"` rounds half to even on the exact binary value, `toFixed` would not;
 * - a lone surrogate cannot be encoded by `str.encode()` / `write_text`, so it raises here too;
 * - a Python `KeyError` / `ValueError` / `AttributeError` is an `Error` with that `name` and the
 *   exception's first argument as its message (Python's `str(KeyError(x))` is `repr(x)`).
 */

import fs from "node:fs";
import { posix } from "node:path";

import { fill } from "../../common/jsondata.mjs";
import { FloatValue, canonicalForm, wiringForm } from "../../common/json_writer.mjs";
import { claimDiagnosticMarker, gettempdir, releaseDiagnosticMarkers } from "../../common/markers.mjs";
import { aitnaRootName } from "../../common/project_root.mjs";
import { harnessCommand, harnessCommands } from "../../common/runtime.mjs";
import {
  pyError as _pyError,
  isDict as _isDict,
  pyTypeName as _pyTypeName,
  dictGet as _get,
  dictItem as _item,
  dictSet as _set,
  truthy as _truthy,
  pyNumeric as _numeric,
  pyEq as _pyEq,
  pyIterate as _iterate,
  pyContains as _contains,
  seqIndex as _index,
  seqLast as _last,
  strRepr as _strRepr,
  pyRepr as _pyRepr,
  pyStr as _pyStr,
  pyInt as _pyInt,
  pyJoin as _join,
  pySplit as _split,
  pyLstrip as _lstrip,
  pyStrip as _strip,
  rstripChars as _rstripChars,
  pySplitlines as _splitlines,
  pyLen as _len,
  pyLower as _lower,
  encodeUtf8 as _utf8,
  pyPath as _path,
  isOSError as _isOSError,
  isFile as _isFile,
  isDir as _isDir,
  decodeUtf8 as _decode,
  readText as _readText,
  writeText as _writeText,
  unlinkMissingOk as _unlinkMissingOk,
} from "../../common/pyvalue.mjs";
import { sha256Hex } from "../../common/sha256.mjs";
import { shlexSplit } from "../../common/shlex.mjs";
import { codePointCompare, codePointSort } from "../../common/sort.mjs";

/** @typedef {import("../../common/runtime.mjs").RuntimeData} RuntimeData */
/** @typedef {import("../../common/markers.mjs").MarkersData} MarkersData */

/**
 * The shape of `tools/model_routing/agents.json` — the data file is the owner of these keys.
 *
 * @typedef {object} AgentsData
 * @property {string} generated_banner
 * @property {string[]} generated_banners_earlier
 * @property {{mount: string, python: string, node: string}} tool_command
 * @property {string} zone_convention
 * @property {string} overlay_name
 * @property {string} local_overlay_rel
 * @property {string} local_aliases_rel
 * @property {string} default_model_token
 * @property {{unresolved: string, invalid: string}} alias_errors
 * @property {{unsupported: string, unknown: string}} effort_errors
 * @property {{format: string, json: string, shape: string}} catalog_errors
 * @property {{invalid: string}} overlay_errors
 * @property {string} local_config_rel
 * @property {string} delegation_log_rel
 * @property {string} agents_dir_rel
 * @property {string[]} settings_probe_names
 * @property {{policy: string[], vendor: string[], config: string[]}} retired_second_opinion_keys
 * @property {{overlay: string, config: string}} retired_key_errors
 * @property {{name: string, tier: string, description: string, tools: string | null, body: string,
 *   kinds: string[]}[]} agent_specs
 * @property {{binding: string, delegation: string, self_check: string}} status_lines
 * @property {string[]} init_instruction
 * @property {string} rebind_notice
 * @property {string} unlabelled_fanout_warning
 * @property {string} unlabelled_fanout_directive
 * @property {string} unpinnable_model
 * @property {Record<string, string>} opinion_skip_reasons
 * @property {{provider: string, provider_default: string, session: string, session_default: string}} opinion_asks
 * @property {{head: string, unavailable: string, unavailable_unknown: string, chain_empty: string}} opinion_status
 * @property {string} session_unknown
 * @property {string} opinion_ladder_unknown
 * @property {string} session_family_unknown
 * @property {string} vendor_unknown
 * @property {string} vendor_is_carrier
 * @property {{line: string, effects: Record<string, string>}} hook_overlay_error
 * @property {{semantic: string, not_in_list: string, below_floor: string, reserved_top: string}} compute_binding_warnings
 * @property {string} role_matrix_warning
 * @property {string} role_matrix_directive
 * @property {string} floor_gap_line
 * @property {string} delegation_floor_warning
 * @property {{text: string, override: string}} delegation_floor_directive
 * @property {{warn: string, info: string}} context_pressure
 * @property {{no_config: string, registry_changed: string, model_mismatch: string}} staleness
 * @property {{order: string, auditor_unknown: string, auditor_unlisted: string}} ladder_errors
 */

/**
 * The shape of `tools/model_routing/gate.json` this module reads (the rest is `gate_pack`'s).
 *
 * @typedef {object} GateData
 * @property {{role: string, trigger: string, noun: string, headings: string[], anchor: string}[]} gate_rules
 */

/** A parsed JSON document (registry, overlay, local config, payload): any JSON value. */
/** @typedef {any} Json */

/**
 * The first of `items` with the greatest code-point length — `max(items, key=len)`.
 * @param {string[]} items
 * @returns {string}
 */
function _longest(items) {
  let best = items[0];
  for (const item of items.slice(1)) {
    if (_len(item) > _len(best)) {
      best = item;
    }
  }
  return best;
}

/** `f"{ratio:.0%}"`: the share times 100, rounded half to even on the exact binary value. */
function _percent(/** @type {number} */ ratio) {
  const scaled = ratio * 100;
  const floor = Math.floor(scaled);
  const rest = scaled - floor; // exact: both are doubles of one binade or the fraction is zero
  const whole = rest > 0.5 || (rest === 0.5 && floor % 2 !== 0) ? floor + 1 : floor;
  return `${Number.isSafeInteger(whole) ? String(whole) : BigInt(whole).toString()}%`;
}

// --------------------------------------------------------------------------------------
// Data accessors and the registry
// --------------------------------------------------------------------------------------

/**
 * Committed, per-project overlay file name (project-root-relative).
 *
 * Same shape as the registry, deep-merged over it; may add a "briefs" map with per-agent
 * markdown appended to the generated subagent bodies — keyed by agent name, matched
 * notation-insensitively, unmatched key is an error: see `resolveBriefs`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function overlayName(data) {
  return data.overlay_name;
}

/**
 * The developer-local overlay's path under the aitna root (gitignored with `<aitna_root>/local/`).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function localOverlayRel(data) {
  return data.local_overlay_rel;
}

/**
 * The generated resolved-aliases file's path under the aitna root (gitignored with `<aitna_root>/local/`).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function localAliasesRel(data) {
  return data.local_aliases_rel;
}

/**
 * The reserved model token of the `carrier[:model]` grammar: `carrier:default` is the carrier's own model.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function defaultModelToken(data) {
  return data.default_model_token;
}

/**
 * Per-user resolved binding (gitignored, like .env) — written by init, read by the hook.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function localConfigRel(data) {
  return data.local_config_rel;
}

/**
 * The delegation log the PreToolUse hook appends to (project-root-relative).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function delegationLogRel(data) {
  return data.delegation_log_rel;
}

/**
 * The generated `k_*` subagent definitions' directory (project-root-relative).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function agentsDirRel(data) {
  return data.agents_dir_rel;
}

/**
 * The banner marking a generated agent file as machine-written — the obsolete sweep's gate.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function generatedBanner(data) {
  return data.generated_banner;
}

/**
 * Every banner a generated agent file may carry: the current one, then the ones earlier
 * releases wrote. The obsolete sweep recognises all of them, so rewording the banner never turns
 * an agent an earlier release generated into a hand-written one that nothing removes.
 * @param {AgentsData} data
 * @returns {string[]}
 */
export function generatedBanners(data) {
  return [data.generated_banner, ...data.generated_banners_earlier];
}

/**
 * How an agent runs `tool` (`model_routing/init`) from this implementation (ADR-0020/D06).
 * `runtimeRoot` is `runtimeRootDisplay`'s answer: from a mounted tree the tool is the mount's
 * script, as the Python spells it (a Node project is never mounted; the corpus runs both on one
 * fixture); from the installed package it is `npx akmon tool`.
 * @param {AgentsData} data
 * @param {string} runtimeRoot
 * @param {string} tool
 * @returns {string}
 */
export function toolCommand(data, runtimeRoot, tool) {
  if (runtimeRoot === "$(akmon path)") {
    return fill(data.tool_command.node, { tool });
  }
  return fill(data.tool_command.mount, { runtime_root: runtimeRoot, tool });
}

/**
 * The `.claude` settings files the default-model probe reads, local first (single owner).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string[]}
 */
export function settingsProbeNames(data) {
  return [...data.settings_probe_names];
}

/**
 * Path to the shipped `registry.json` under an akmon tree.
 * @param {string} akmonDir
 * @returns {string}
 */
export function registryPath(akmonDir) {
  return _path(akmonDir, "tools", "model_routing", "registry.json");
}

/**
 * Path to the project's committed model-routing overlay file, if any.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {string}
 */
export function overlayPath(data, projectRoot) {
  return _path(projectRoot, aitnaRootName(), overlayName(data));
}

/**
 * Path to the developer's own routing overlay (gitignored, hand-owned, never generated), if any.
 *
 * Same shape and file name as the project overlay, but under `<aitna_root>/local/` (ADR 0022):
 * the strongest layer (ADR-0024/D11) — a developer states which harnesses and models they run
 * without asking the team to share it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {string}
 */
export function localOverlayPath(data, projectRoot) {
  return _path(projectRoot, aitnaRootName(), localOverlayRel(data));
}

/**
 * Path to the generated resolved-aliases file (ADR-0024/D16), if any.
 *
 * Written only by `tools/model_routing/models.mjs` and never hand-owned: it maps each alias of an
 * `aliases: true` provider row to the concrete id the carrier accepts on this machine.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {string}
 */
export function localAliasesPath(data, projectRoot) {
  return _path(projectRoot, aitnaRootName(), localAliasesRel(data));
}

/** A routing overlay file is not a JSON object; the message names the file. */
export class OverlayError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "OverlayError";
  }
}

/**
 * The override deep-merged over the base: nested objects merge, everything else replaces.
 * @param {Record<string, Json>} base
 * @param {Record<string, Json>} override
 * @returns {Record<string, Json>}
 */
function _deepMerge(base, override) {
  const merged = { ...base };
  for (const [key, value] of Object.entries(override)) {
    const current = Object.hasOwn(merged, key) ? merged[key] : undefined;
    _set(merged, key, _isDict(value) && _isDict(current) ? _deepMerge(current, value) : value);
  }
  return merged;
}

const _WHOLE_FLOAT_SPELLING = /[0-9]\.0+(?![0-9])|[0-9][eE]/;

/**
 * `json.loads` for a document a person may edit (the registry, its overlay, the local config):
 * a whole number the text spells as a float (`3.0`, `1e3`) stays a `FloatValue`, so a check that
 * refuses a Python float refuses it here too. The reviver's third argument (the source text)
 * is Node >= 21; the transcript readers keep plain `JSON.parse` (see the header).
 * @param {string} text
 * @returns {Json}
 */
function _parseKeepingFloats(text) {
  // The reviver doubles the parse time; only a text that can spell a whole float (`.0` closing
  // a number, or an exponent) needs it — a string that merely looks like one costs the slow
  // path, never a wrong answer.
  if (!_WHOLE_FLOAT_SPELLING.test(text)) {
    return JSON.parse(text);
  }
  /** @type {(text: string, reviver: (key: string, value: any, context: any) => any) => any} */
  const parse = /** @type {any} */ (JSON.parse);
  return parse(text, (_key, value, context) =>
    typeof value === "number" && Number.isInteger(value) && /[.eE]/.test(context?.source ?? "")
      ? new FloatValue(value)
      : value,
  );
}

/**
 * One overlay file's JSON object; anything else raises `OverlayError` naming `file`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} path
 * @param {string} file the project-root-relative name the error quotes
 * @returns {Record<string, Json>}
 */
function _readOverlay(data, path, file) {
  const invalid = () => new OverlayError(fill(data.overlay_errors.invalid, { file }));
  /** @type {Json} */
  let parsed;
  try {
    parsed = _parseKeepingFloats(_readText(path));
  } catch (error) {
    // `json.loads` raises a `ValueError` for a text it cannot parse or decode; an unreadable file is not one.
    if (error instanceof SyntaxError || (error instanceof Error && error.name === "UnicodeDecodeError")) {
      throw Object.assign(invalid(), { cause: error });
    }
    throw error;
  }
  if (!_isDict(parsed)) {
    throw invalid();
  }
  return parsed;
}

/**
 * The overlay layers that exist, weakest first: the project overlay, then the developer's local one.
 *
 * Each is `[project-root-relative file, parsed object]`; a missing file is no layer.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {[string, Record<string, Json>][]}
 */
function _overlayLayers(data, projectRoot) {
  /** @type {[string, string][]} */
  const candidates = [
    [_overlayFile(data), overlayPath(data, projectRoot)],
    [_localOverlayFile(data), localOverlayPath(data, projectRoot)],
  ];
  return candidates.filter(([, path]) => _isFile(path)).map(([file, path]) => [file, _readOverlay(data, path, file)]);
}

/**
 * The merged registry: akmon data, the project overlay, then the developer's local overlay (strongest).
 *
 * Dicts merge key by key and anything else — a list, hence a `ladder` — is replaced whole by the
 * stronger layer (ADR-0024/D05, D11).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} akmonDir
 * @param {string | null} [projectRoot]
 * @returns {Json}
 */
export function loadRegistry(data, akmonDir, projectRoot = null) {
  let registry = _parseKeepingFloats(_readText(registryPath(akmonDir)));
  if (projectRoot !== null && projectRoot !== undefined) {
    for (const [, layer] of _overlayLayers(data, projectRoot)) {
      registry = _deepMerge(registry, layer);
    }
  }
  return registry;
}

/**
 * Stable digest of the merged registry — staleness detection for the local config.
 * @param {Json} registry
 * @returns {string}
 */
export function registryHash(registry) {
  return sha256Hex(canonicalForm(registry)).slice(0, 16);
}

/** The tier→model binding — a pure function of (selection policy, orchestrator, available). */
export class Binding {
  /**
   * @param {string} vendor
   * @param {Json} orchestrator
   * @param {Json} reasoner
   * @param {Json} worker
   * @param {Json} mid
   * @param {Json} auditor
   * @param {Json[]} escalation
   * @param {boolean} [semanticFallback]
   * @param {string | null} [warning]
   * @param {string | null} [auditorOptIn]
   */
  constructor(
    vendor,
    orchestrator,
    reasoner,
    worker,
    mid,
    auditor,
    escalation,
    semanticFallback = false,
    warning = null,
    auditorOptIn = null,
  ) {
    this.vendor = vendor;
    this.orchestrator = orchestrator;
    this.reasoner = reasoner;
    this.worker = worker;
    this.mid = mid;
    this.auditor = auditor;
    this.escalation = Object.freeze([...escalation]);
    this.semanticFallback = semanticFallback;
    this.warning = warning;
    this.auditorOptIn = auditorOptIn;
    Object.freeze(this);
  }
}

/**
 * The semantic ladder: worker, mid, reasoner, then the auditor, each once.
 * @param {Json} vendorData
 * @returns {string[]}
 */
function _semanticRungs(vendorData) {
  const fallback = _get(vendorData, "semantic_fallback", {});
  const worker = _pyStr(_truthy(_get(fallback, "worker")) ? _get(fallback, "worker") : "worker");
  const mid = _pyStr(_truthy(_get(fallback, "mid")) ? _get(fallback, "mid") : "mid");
  const reasoner = _pyStr(_truthy(_get(fallback, "reasoner")) ? _get(fallback, "reasoner") : "strongest");
  const auditor = _pyStr(_truthy(_get(fallback, "auditor")) ? _get(fallback, "auditor") : "strongest");
  /** @type {string[]} */ const rungs = [];
  for (const rung of [worker, mid, reasoner]) {
    if (!rungs.includes(rung)) {
      rungs.push(rung);
    }
  }
  if (!rungs.includes(auditor)) {
    rungs.push(auditor);
  }
  return rungs;
}

/** `value or fallback`. */
function _or(/** @type {Json} */ value, /** @type {Json} */ fallback) {
  return _truthy(value) ? value : fallback;
}

/**
 * The ladder `vendor` binds on, weakest to strongest, and whether it is the semantic one.
 *
 * A non-empty `available` list is the ladder, minus the vendor's auditor-only rungs (their
 * order kept); otherwise the vendor's committed `harness_rungs`; otherwise the semantic labels,
 * flagged `true` (ADR-0004/D04). The single place that decides it — every caller that needs
 * rungs asks here.
 * @param {Json} registry
 * @param {string} vendor
 * @param {Json} available
 * @returns {[string[], boolean]}
 */
export function selectionLadder(registry, vendor, available) {
  const vendorData = _get(registry, vendor, {});
  if (Array.isArray(available) && available.length > 0) {
    const auditorOnly = _or(_get(vendorData, "auditor_only_rungs"), []);
    const rungs = available.filter((alias) => !_contains(auditorOnly, alias));
    if (rungs.length > 0) {
      return [rungs, false];
    }
  }
  const committed = _get(vendorData, "harness_rungs");
  if (_truthy(committed)) {
    return [[..._iterate(committed)], false];
  }
  return [_semanticRungs(vendorData), true];
}

/**
 * Raise `ValueError` when `available` inverts the order of `vendor`'s committed ladder.
 *
 * Only the aliases `available` shares with `harness_rungs` are ranked: an unknown alias or an
 * auditor-only one never decides it, and a vendor with no committed ladder accepts any order.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} vendor
 * @param {string[]} available
 */
export function checkLadderOrder(data, registry, vendor, available) {
  const committed = [..._iterate(_or(_get(_get(registry, vendor, {}), "harness_rungs"), []))];
  const shared = available.filter((alias) => committed.includes(alias));
  const ranked = [...shared].sort((a, b) => committed.indexOf(a) - committed.indexOf(b));
  if (shared.some((alias, position) => alias !== ranked[position])) {
    throw _pyError(
      "ValueError",
      fill(data.ladder_errors.order, { given: available.join(","), vendor, expected: committed.join(",") }),
    );
  }
}

/**
 * Raise `ValueError` unless `alias` may be the opted-in auditor of `vendor` (ADR-0004/D04).
 *
 * It must be an auditor-only rung or a rung of the ladder, and when an `available` list is given
 * it must be listed there.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} vendor
 * @param {string[] | null} available
 * @param {string} alias
 */
export function checkAuditorOptIn(data, registry, vendor, available, alias) {
  const [rungs, semantic] = selectionLadder(registry, vendor, available);
  const auditorOnly = [..._iterate(_or(_get(_get(registry, vendor, {}), "auditor_only_rungs"), []))];
  const ladder = semantic ? [] : rungs;
  if (!auditorOnly.includes(alias) && !ladder.includes(alias)) {
    throw _pyError(
      "ValueError",
      fill(data.ladder_errors.auditor_unknown, {
        alias,
        vendor,
        ladder: ladder.join(","),
        auditor_only: auditorOnly.join(","),
      }),
    );
  }
  if (Array.isArray(available) && available.length > 0 && !available.includes(alias)) {
    throw _pyError("ValueError", fill(data.ladder_errors.auditor_unlisted, { alias, given: available.join(",") }));
  }
}

/**
 * Bind tiers to model aliases from a semantic vendor policy (MODEL.md § Capability tiers).
 *
 * The ladder comes from `selectionLadder`: `available` (the local, discovery-derived list,
 * weakest → strongest, auditor-only rungs removed) or the vendor's committed `harness_rungs`.
 * A vendor with neither binds semantic labels with a warning; generated file-backed agents then
 * omit concrete model frontmatter instead of pretending those labels are valid vendor model ids.
 * The auditor is `auditorOptIn` when given, else the top of the ladder; an auditor-only rung is
 * never the worker, mid, reasoner or an escalation step (ADR-0004/D04).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} orchestrator
 * @param {Json} [available]
 * @param {string} [vendor]
 * @param {string | null} [auditorOptIn]
 * @returns {Binding}
 */
export function computeBinding(
  data,
  registry,
  orchestrator,
  available = null,
  vendor = "anthropic",
  auditorOptIn = null,
) {
  const vendorData = _item(registry, vendor);
  const [rungs, semantic] = selectionLadder(registry, vendor, available);

  const auditor = _or(auditorOptIn, rungs[rungs.length - 1]); // pinned max unless the owner opted in — unlike the now-dynamic reasoner
  const worker = rungs[0];
  const workerPos = _index(rungs, worker);
  const mid = rungs[Math.min(workerPos + 1, rungs.length - 1)];
  const escalation = rungs.slice(workerPos + 1, rungs.length - 1);

  const policy = _get(vendorData, "selection_policy", {});
  const reasonerPolicy = _get(policy, "reasoner", "highest");
  let reasoner;
  if (semantic) {
    const fallback = _get(vendorData, "semantic_fallback", {});
    reasoner = _pyStr(_or(_get(fallback, "reasoner"), "strongest"));
  } else if (_pyEq(reasonerPolicy, "orchestrator") && _contains(rungs, orchestrator)) {
    reasoner = orchestrator;
  } else {
    // Unknown orchestrator, or a non-"orchestrator" policy value (e.g. "highest") —
    // fall back to the top rung.
    reasoner = rungs[rungs.length - 1];
  }

  const warnings = data.compute_binding_warnings;
  /** @type {string | null} */ let warning = null;
  if (semantic) {
    warning = warnings.semantic;
  } else {
    const floorRung = _corridorFloor(policy, rungs);
    if (!_contains(rungs, orchestrator)) {
      warning = fill(warnings.not_in_list, { orchestrator: _pyStr(orchestrator) });
    } else if (_contains(rungs, floorRung)) {
      // Healthy corridor: floor ≤ orchestrator < top (design §3, ADR 0006). When the
      // ladder tops out at the floor, floor == top and both arms stay silent — the
      // accepted degraded mode. A floor alias absent from the ladder disables the
      // check (nothing to rank against); the relative "highest" floor resolves to the
      // top rung, reproducing the pre-corridor below-top warning.
      const orchRank = _index(rungs, orchestrator);
      const floorRank = _index(rungs, floorRung);
      if (orchRank < floorRank) {
        warning = fill(warnings.below_floor, { orchestrator: _pyStr(orchestrator), floor: _pyStr(floorRung) });
      } else if (orchRank === rungs.length - 1 && floorRank < rungs.length - 1) {
        warning = fill(warnings.reserved_top, { orchestrator: _pyStr(orchestrator), floor: _pyStr(floorRung) });
      }
    }
  }

  return new Binding(vendor, orchestrator, reasoner, worker, mid, auditor, escalation, semantic, warning, auditorOptIn);
}

/**
 * The corridor's lower bound on `rungs`: `orchestrator_floor`, `"highest"` the top rung.
 *
 * Not necessarily on the ladder — an alias the local ladder lacks disables the corridor.
 * @param {Json} policy
 * @param {Json} rungs
 * @returns {Json}
 */
function _corridorFloor(policy, rungs) {
  const floor = _get(policy, "orchestrator_floor", "highest");
  return _pyEq(floor, "highest") ? _last(rungs) : _pyStr(floor);
}

/**
 * Per-task-kind rung floors, resolved to concrete aliases from `rungs`.
 *
 * Only task kinds carrying a `"floor"` key are included. `"highest"` resolves to
 * `rungs[-1]`; `"orchestrator_floor"` resolves to `vendor`'s corridor floor
 * (`selection_policy.orchestrator_floor`, itself `"highest"` or an alias) — the lowest rung the
 * corridor accepts for the orchestrator, and so for the reasoner that follows it (C32: a healthy
 * binding opens no gap); a literal alias passes through only when present in `rungs`. A kind
 * whose floor cannot be resolved (empty `rungs`, or an alias absent from it) is skipped.
 * @param {Json} registry
 * @param {Json} rungs
 * @param {string} [vendor]
 * @returns {Record<string, Json>}
 */
export function taskKindFloors(registry, rungs, vendor = "anthropic") {
  /** @type {Record<string, Json>} */ const floors = {};
  if (!_truthy(rungs)) {
    return floors;
  }
  const kinds = _get(registry, "task_kinds", {});
  if (!_isDict(kinds)) {
    throw _pyError("AttributeError", `'${_pyTypeName(kinds)}' object has no attribute 'items'`);
  }
  for (const [kind, spec] of Object.entries(kinds)) {
    let floor = _get(spec, "floor");
    if (!_truthy(floor)) {
      continue;
    }
    if (_pyEq(floor, "orchestrator_floor")) {
      floor = _corridorFloor(_get(_get(registry, vendor, {}), "selection_policy", {}), rungs);
    }
    if (_pyEq(floor, "highest")) {
      _set(floors, kind, _last(rungs));
    } else if (_contains(rungs, floor)) {
      _set(floors, kind, _pyStr(floor));
    }
  }
  return floors;
}

/**
 * Vendors that can run a main/orchestrator session under the semantic routing policy.
 * @param {Json} registry
 * @returns {string[]}
 */
export function vendorsWithRoutingPolicy(registry) {
  if (!_isDict(registry)) {
    throw _pyError("AttributeError", `'${_pyTypeName(registry)}' object has no attribute 'items'`);
  }
  return Object.entries(registry)
    .filter(([, spec]) => _isDict(spec) && _isDict(_get(spec, "selection_policy")))
    .map(([name]) => name);
}

/** A configuration file still carries a key ADR 0024 retired; the message names the file and the keys. */
export class RetiredKeyError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "RetiredKeyError";
  }
}

/**
 * The keys the second-opinion rewrite retired, by where they live: `policy`, `vendor` and `config`.
 *
 * A project overlay written before the change deep-merges *over* the shipped registry, so a stale
 * key survives and rides along unread: the configuration looks usable and silently means something
 * else. That is why each one is refused by name (`refuseRetiredKeys`) instead of ignored.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {{policy: string[], vendor: string[], config: string[]}}
 */
export function retiredSecondOpinionKeys(data) {
  const keys = data.retired_second_opinion_keys;
  return { policy: [...keys.policy], vendor: [...keys.vendor], config: [...keys.config] };
}

/**
 * The retired keys one overlay-shaped object still carries, policy first, then each block in order.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} layer
 * @returns {string[]}
 */
function _retiredOverlayKeys(data, layer) {
  const retired = retiredSecondOpinionKeys(data);
  /** @type {string[]} */
  const found = [];
  const policy = _get(layer, "second_opinion_policy");
  if (_isDict(policy)) {
    found.push(
      ...retired.policy.filter((key) => Object.hasOwn(policy, key)).map((key) => `second_opinion_policy.${key}`),
    );
  }
  for (const [name, spec] of Object.entries(layer)) {
    if (_isDict(spec)) {
      found.push(...retired.vendor.filter((key) => Object.hasOwn(spec, key)).map((key) => `${name}.${key}`));
    }
  }
  return found;
}

/**
 * Raise `RetiredKeyError` naming the file when an overlay or the local config holds a retired key.
 *
 * The shipped registry carries none of them, so one found in the merged registry came from an
 * overlay. With `projectRoot` each overlay file is read in turn, strongest first, and the error
 * quotes the one that holds the key — the file to edit. Without it only the merged registry is
 * known, so the error names both candidate files. The local config is a generated file, so its
 * error says to regenerate it; an overlay is hand-owned, so its error says which keys to delete.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} config
 * @param {{projectRoot?: string | null}} [options]
 * @returns {void}
 */
export function refuseRetiredKeys(data, registry, config, { projectRoot = null } = {}) {
  const texts = data.retired_key_errors;
  /** @type {[string, string[]][]} */
  const holders =
    projectRoot === null
      ? [[`${_localOverlayFile(data)} or ${_overlayFile(data)}`, _retiredOverlayKeys(data, registry)]]
      : _overlayLayers(data, projectRoot)
          .reverse()
          .map(([file, layer]) => [file, _retiredOverlayKeys(data, layer)]);
  for (const [file, keys] of holders) {
    if (keys.length) {
      throw new RetiredKeyError(fill(texts.overlay, { file, keys: keys.join(", ") }));
    }
  }
  const inConfig = retiredSecondOpinionKeys(data).config.filter((key) => _contains(config, key));
  if (inConfig.length) {
    throw new RetiredKeyError(fill(texts.config, { file: localConfigRel(data), keys: inConfig.join(", ") }));
  }
}

/** A second opinion asked for a model its provider declares no `model_flag` to pin (C97). */
export class UnpinnableModelError extends Error {
  /**
   * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
   * @param {string} provider
   * @param {string} model
   */
  constructor(data, provider, model) {
    super(fill(data.unpinnable_model, { model: _pyRepr(model), provider }));
    this.name = "UnpinnableModelError";
  }
}

// --------------------------------------------------------------------------------------
// The provider ladder (ADR-0024/D05-D12): one order, diversity tested on priors
// --------------------------------------------------------------------------------------

/** Rank 2 is the second opinion; 3 a third; 4 an arbiter. One walk answers them all (ADR-0024/D06). */
export const OPINION_RANK_SECOND = 2;

/** A resolved second-opinion target: which provider, which model to pin (if any), and whose priors answer. */
export class SecondOpinionTarget {
  /**
   * @param {string} provider
   * @param {string | null} model `null` = the carrier's own default model
   * @param {string | null} [family] the priors that answer (ADR-0024/D01); `null` = unknown (D08)
   * @param {string | null} [effort] the reasoning level sent with it (ADR-0024/D17); `null` = the carrier's own
   */
  constructor(provider, model, family = null, effort = null) {
    this.provider = provider;
    this.model = model;
    this.family = family;
    this.effort = effort;
    Object.freeze(this);
  }
}

/** The working session as the ladder sees it: its carrier, the family that answers, its model. */
export class SecondOpinionSession {
  /**
   * @param {string} provider
   * @param {string | null} family
   * @param {string | null} [model]
   */
  constructor(provider, family, model = null) {
    this.provider = provider;
    this.family = family;
    this.model = model;
    Object.freeze(this);
  }
}

/** No source names the session's provider: an explicit argument, the `session` stanza or the bound vendor. */
export class SessionUnknownError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "SessionUnknownError";
  }
}

/**
 * The one flat ladder — team-committed, or replaced whole by the local overlay (ADR-0024/D05).
 * @param {Json} registry
 * @returns {string[]}
 */
export function opinionLadder(registry) {
  const policy = _get(registry, "second_opinion_policy");
  const ladder = _isDict(policy) ? _get(policy, "ladder") : null;
  return _iterate(_or(ladder, [])).map(_pyStr);
}

/**
 * The provider table — the single owner of every provider row (ADR-0024/D02).
 * @param {Json} registry
 * @returns {Record<string, Json>}
 */
export function providers(registry) {
  const rows = _get(registry, "providers");
  return _isDict(rows) ? rows : {};
}

/**
 * One row by id. A ladder id the table does not declare is a named error, never a silent skip.
 *
 * The error names the two overlay files that can hold the ladder (the developer's and the team's),
 * the same placeholders an ask names, because the entry came from one of them (ADR-0024/D05).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @returns {Record<string, Json>}
 */
export function providerRow(data, registry, provider) {
  const rows = providers(registry);
  const row = Object.hasOwn(rows, provider) ? rows[provider] : null;
  if (_isDict(row)) {
    return row;
  }
  const values = { provider, local_overlay: _localOverlayFile(data), overlay: _overlayFile(data) };
  throw _pyError("KeyError", fill(data.opinion_ladder_unknown, values));
}

/**
 * The closed set of family names, in declared order: `second_opinion_policy.families`' keys (ADR-0024/D01).
 *
 * An object, not a list, so an overlay adds a family by key without restating the shipped ones (a
 * list would be replaced whole by the stronger layer).
 * @param {Json} registry
 * @returns {string[]}
 */
export function familyVocabulary(registry) {
  const policy = _get(registry, "second_opinion_policy");
  const families = _isDict(policy) ? _get(policy, "families") : null;
  return _isDict(families) ? Object.keys(families) : [];
}

/**
 * Raise `ValueError` naming the files that extend the vocabulary when `family` is not in it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} family
 */
export function checkSessionFamily(data, registry, family) {
  const known = familyVocabulary(registry);
  if (known.includes(family)) {
    return;
  }
  const values = {
    family,
    known: known.join(", "),
    local_overlay: _localOverlayFile(data),
    overlay: _overlayFile(data),
  };
  throw _pyError("ValueError", fill(data.session_family_unknown, values));
}

/**
 * The usage error for a `--vendor` with no tier-binding block.
 *
 * A name the providers table declares is a carrier: it has no vendor block, so it cannot bind
 * tiers, and the message says how to start from that harness instead (`--session-provider`, with
 * `--vendor` still choosing the binding it borrows). Tier binding stays owned by a vendor block
 * (ADR-0024/D15).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} vendor
 * @param {string[]} vendors
 * @returns {string}
 */
export function vendorRefusal(data, registry, vendor, vendors) {
  const text = Object.hasOwn(providers(registry), vendor) ? data.vendor_is_carrier : data.vendor_unknown;
  return fill(text, { vendor, vendors: vendors.join(", ") });
}

/**
 * The one stderr line a hook prints for a bad hand-owned overlay: the hook, the file, what it costs.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} hook
 * @param {Error} error an `OverlayError`
 * @returns {string}
 */
export function hookOverlayLine(data, hook, error) {
  const texts = data.hook_overlay_error;
  return fill(texts.line, { hook, error: error.message, effect: texts.effects[hook] });
}

/**
 * A `carrier[:model]` entry as `[provider, model]`, split on the FIRST colon only.
 *
 * A model id may itself hold `/` and `:` (`anthropic/claude-sonnet-4`, `qwen3:8b`), so the
 * carrier is whatever precedes the first colon and everything after it is the model.
 * @param {string} entry
 * @returns {[string, string | null]}
 */
export function splitOpinionEntry(entry) {
  const colon = entry.indexOf(":");
  if (colon < 0) {
    return [entry, null];
  }
  return [entry.slice(0, colon), entry.slice(colon + 1) || null];
}

/**
 * Whether a ladder entry names `provider:default` — the carrier's own model, no pin (ADR-0024/D16).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @returns {boolean}
 */
export function ladderPinsDefault(data, registry, provider) {
  const token = defaultModelToken(data);
  return opinionLadder(registry).some((entry) => {
    const [entryProvider, pinned] = splitOpinionEntry(entry);
    return entryProvider === provider && splitModelEffort(pinned)[0] === token;
  });
}

/**
 * A `model[@effort]` text as `[model, effort]`, split at its LAST `@` (ADR-0024/D17).
 *
 * A model id that itself encodes the level (`acme/qwen3.8-27b-max`) stays one id, because akmon
 * never parses a model name; no `@` means no effort. An empty side is `null` for the model and kept
 * as `""` for the effort, which no row lists, so `m@` is refused rather than ignored.
 * @param {string | null} text
 * @returns {[string | null, string | null]}
 */
export function splitModelEffort(text) {
  if (text === null) {
    return [null, null];
  }
  const at = text.lastIndexOf("@");
  if (at < 0) {
    return [text || null, null];
  }
  return [text.slice(0, at) || null, text.slice(at + 1)];
}

/**
 * The priors that answer when `provider` runs `model`: the model's own entry, else the row's, else unknown.
 *
 * A carrier that fronts several families (a gateway, a multi-provider harness) states each model's
 * family in `model_families`; a single-family carrier states `family` once. A model neither names
 * resolves to `null`, which the walk treats as unknown and fails closed (ADR-0024/D08) — guessing
 * a family from the model id would be the silent weakness this record removes.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @param {string | null} [model]
 * @returns {string | null}
 */
export function providerFamily(data, registry, provider, model = null) {
  const row = providerRow(data, registry, provider);
  const families = _get(row, "model_families");
  if (_truthy(model) && _isDict(families) && _truthy(_get(families, /** @type {string} */ (model)))) {
    return _pyStr(families[/** @type {string} */ (model)]);
  }
  const family = _get(row, "family");
  return _truthy(family) ? _pyStr(family) : null;
}

/**
 * `shutil.which(command)`: the path of an executable, resolved on the current `PATH`, or `null`.
 *
 * A name holding a directory part is tested as given; a bare name is searched in each `PATH`
 * entry (an empty entry is the working directory), and a directory never counts.
 * @param {string} command
 * @returns {string | null}
 */
function _which(command) {
  /** @param {string} file */
  const executable = (file) => {
    try {
      if (fs.statSync(file).isDirectory()) {
        return false;
      }
      fs.accessSync(file, fs.constants.X_OK);
      return true;
    } catch {
      return false;
    }
  };
  if (command.includes("/")) {
    return executable(command) ? command : null;
  }
  const searched = process.env.PATH ?? "/bin:/usr/bin";
  if (searched === "") {
    return null;
  }
  for (const directory of new Set(searched.split(":"))) {
    const candidate = posix.join(directory, command);
    if (executable(candidate)) {
      return candidate;
    }
  }
  return null;
}

/**
 * Whether the carrier's executable resolves on `PATH` — a yes-or-no about a binary, nothing more.
 *
 * This is the one host fact the resolver takes (ADR-0024/D11): it reads no carrier settings file,
 * no developer dot-directory and no environment value, and never invokes the carrier to ask what
 * it is, so the same code answers the same way on the owner's host and on a consumer's. The
 * executable is the row's `requires_command`, a declared `argv`'s first element, or — for a
 * shipped carrier — the command map's own name for it, so the map stays the only place that spells one.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {string} provider
 * @returns {boolean}
 */
export function carrierPresent(data, runtimeData, registry, provider) {
  const row = providerRow(data, registry, provider);
  const argv = _get(row, "argv");
  const table = harnessCommands(runtimeData);
  const mapped = Object.hasOwn(table, provider) ? table[provider].binary : "";
  const binary = _pyStr(
    _or(_get(row, "requires_command"), _or(Array.isArray(argv) && argv.length > 0 ? argv[0] : "", mapped)),
  );
  return binary !== "" && _which(binary) !== null;
}

/**
 * The model the second opinion takes inside `provider`: its strongest declared one.
 *
 * This rule belongs to the second opinion alone (ADR-0024/D14) and reads the provider table's
 * `models` and nothing else — never the tier binding's rungs, which answer a different consumer's
 * question and would let a reviewer inherit a `worker`'s list. No declared list means the answer is
 * `null`: the carrier's own default, the one honest value left. A rule nobody implemented raises,
 * because silently picking by some other order would be an unstated policy.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @returns {string | null}
 */
export function opinionModel(data, registry, provider) {
  const policy = _get(registry, "second_opinion_policy");
  const rule = _isDict(policy) ? _pyStr(_get(policy, "model_rule", "max")) : "max";
  if (rule !== "max") {
    throw _pyError(
      "ValueError",
      `second opinion: unknown model_rule ${_strRepr(rule)}; the only rule implemented is 'max'`,
    );
  }
  const models = _get(providerRow(data, registry, provider), "models");
  if (!Array.isArray(models) || models.length === 0) {
    return null;
  }
  return _pyStr(models[models.length - 1]);
}

/** An effort a row cannot take: it declares no `efforts`, or the level is not one of its `levels`. */
export class EffortError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "EffortError";
  }
}

/**
 * Raise `EffortError` unless `effort` is `null` or a level the provider's `efforts` lists (ADR-0024/D17).
 *
 * akmon never guesses a level and never forwards one the row does not list: a carrier with no
 * `efforts` is refused naming it, and an unlisted level is refused naming the accepted ones.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @param {string | null} effort
 */
export function checkEffort(data, registry, provider, effort) {
  if (effort === null) {
    return;
  }
  const declared = _get(providerRow(data, registry, provider), "efforts");
  const levels = _isDict(declared) ? _get(declared, "levels") : null;
  if (!Array.isArray(levels)) {
    const values = { provider, effort, local_overlay: _localOverlayFile(data), overlay: _overlayFile(data) };
    throw new EffortError(fill(data.effort_errors.unsupported, values));
  }
  if (!levels.includes(effort)) {
    throw new EffortError(
      fill(data.effort_errors.unknown, { provider, effort, levels: levels.map((level) => _pyStr(level)).join(", ") }),
    );
  }
}

/**
 * The `[model, effort]` a `carrier[:model[@effort]]` entry runs (ADR-0024/D16, D17).
 *
 * `default` is a token, not a model id: it drops the pin altogether, so the carrier uses the model it
 * is configured with and no alias is resolved, and `default@high` sends only the level. An effort-only
 * pin (`@high`) keeps the rule's model. No pin at all still means the strongest declared entry
 * (`opinionModel`, D14), with the effort that entry carries. A level the row does not list raises
 * `EffortError`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @param {string | null} pinned
 * @returns {[string | null, string | null]}
 */
export function opinionPick(data, registry, provider, pinned) {
  const [model, effort] = splitModelEffort(pinned);
  checkEffort(data, registry, provider, effort);
  if (model === defaultModelToken(data)) {
    return [null, effort];
  }
  if (model !== null) {
    return [model, effort];
  }
  const [strongest, strongestEffort] = splitModelEffort(opinionModel(data, registry, provider));
  return [strongest, pinned !== null ? effort : strongestEffort];
}

/**
 * The session's carrier, model and priors: explicit arguments, else the `session` stanza, else the bound vendor.
 *
 * The session may start from any harness on any model, so nothing here assumes a vendor: the
 * `session` stanza of the local config (written by `init --session-provider`) names it outright,
 * and only when neither it nor an argument does the bound vendor's `carrier` and the recorded
 * orchestrator alias stand in. Each field comes from the first layer that states it for the chosen
 * provider — a layer that names another provider never lends it a model or a family. A family none
 * of them states is read from the provider table (`providerFamily`), and stays `null` when that
 * says nothing (ADR-0024/D08). No provider anywhere raises `SessionUnknownError`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} config
 * @param {{provider?: string | null, model?: string | null, family?: string | null}} [options]
 * @returns {SecondOpinionSession}
 */
export function resolveSession(data, registry, config, { provider = null, model = null, family = null } = {}) {
  const stanza = _get(config, "session");
  const vendorBlock = _get(registry, _pyStr(_or(_get(config, "vendor"), "")));
  /** @type {Json[]} */
  const layers = [
    { provider, model, family },
    _isDict(stanza) ? stanza : {},
    { provider: _isDict(vendorBlock) ? _get(vendorBlock, "carrier") : null, model: _get(config, "orchestrator") },
  ];
  const named = layers.find((layer) => _truthy(_get(layer, "provider")));
  if (named === undefined) {
    throw new SessionUnknownError(data.session_unknown);
  }
  const chosen = _pyStr(_get(named, "provider"));
  /**
   * @param {string} field
   * @returns {string | null}
   */
  const stated = (field) => {
    for (const layer of layers) {
      const owner = _get(layer, "provider");
      if (_truthy(_get(layer, field)) && (owner === null || owner === "" || _pyEq(owner, chosen))) {
        return _pyStr(_get(layer, field));
      }
    }
    return null;
  };
  const resolvedModel = stated("model");
  let resolvedFamily = stated("family");
  if (resolvedFamily === null && Object.hasOwn(providers(registry), chosen)) {
    resolvedFamily = providerFamily(data, registry, chosen, resolvedModel);
  }
  return new SecondOpinionSession(chosen, resolvedFamily, resolvedModel);
}

/**
 * The project routing overlay's path, project-root-relative — where an owner declares a missing prior.
 * @param {AgentsData} data
 * @returns {string}
 */
function _overlayFile(data) {
  return `${aitnaRootName()}/${overlayName(data)}`;
}

/**
 * The developer-local routing overlay's path, project-root-relative — the strongest place to declare a prior.
 * @param {AgentsData} data
 * @returns {string}
 */
function _localOverlayFile(data) {
  return `${aitnaRootName()}/${localOverlayRel(data)}`;
}

/**
 * The named key that would settle an unknown family, and the file to write it in (ADR-0024/D08, D11).
 * @param {AgentsData} data
 * @param {string} provider
 * @param {string | null} model
 * @returns {string}
 */
function _priorsAsk(data, provider, model) {
  const values = {
    provider,
    model: _pyStr(model),
    local_overlay: _localOverlayFile(data),
    overlay: _overlayFile(data),
  };
  return fill(data.opinion_asks[_truthy(model) ? "provider" : "provider_default"], values);
}

/**
 * The ask for a session whose own family cannot be resolved: nothing is counted as diverse until it is.
 * @param {AgentsData} data
 * @param {SecondOpinionSession} session
 * @returns {string}
 */
function _sessionAsk(data, session) {
  const values = {
    provider: session.provider,
    model: _pyStr(session.model),
    local_overlay: _localOverlayFile(data),
    overlay: _overlayFile(data),
    local: localConfigRel(data),
  };
  return fill(data.opinion_asks[_truthy(session.model) ? "session" : "session_default"], values);
}

/**
 * The one top-down walk: the admissible chain, every provider passed over with its reason, and the asks.
 *
 * Two skips carry the design (ADR-0024/D06): the session's own carrier, and any provider whose
 * family or concrete model is already spoken for — a different harness answering with the same
 * mind, or the same model under another name, buys no diversity. The compared model is the one the
 * consumer's rule resolves (D14), not only a ladder pin, or two providers answering with the same
 * weights would both pass; the family is read for that chosen model (`providerFamily`), because a
 * carrier that fronts several families has no single answer. `families`/`models` record which
 * provider holds each, so a reason names the owner rather than only refusing. Rank is a position in
 * the *resulting* chain, so a skip never leaves a hole the report must explain.
 *
 * A session whose own family is unknown yields an empty chain (D08): nothing can be said to differ
 * from priors nobody knows. A provider whose family is unknown is skipped and asked about.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @returns {[[string, string | null, string | null][], [string, string][], string[]]}
 */
function _walkOpinionLadder(data, runtimeData, registry, session) {
  const reasons = data.opinion_skip_reasons;
  if (!_truthy(session.family)) {
    return [[], [[session.provider, reasons.session_priors_unknown]], [_sessionAsk(data, session)]];
  }
  /** @type {[string, string | null, string | null][]} */
  const chain = [];
  /** @type {[string, string][]} */
  const skips = [];
  /** @type {string[]} */
  const asks = [];
  /** @type {Map<string, string>} */
  const families = new Map([[_pyStr(session.family), session.provider]]);
  /** @type {Map<string, string>} */
  const models = new Map(_truthy(session.model) ? [[_pyStr(session.model), session.provider]] : []);
  for (const entry of opinionLadder(registry)) {
    const [provider, pinned] = splitOpinionEntry(entry);
    providerRow(data, registry, provider); // an id the table does not declare is a named error, even for the self-skip
    checkEffort(data, registry, provider, splitModelEffort(pinned)[1]); // so is an effort the row cannot take (D17)
    if (provider === session.provider) {
      skips.push([provider, reasons.self]);
      continue;
    }
    if (!carrierPresent(data, runtimeData, registry, provider)) {
      skips.push([provider, reasons.absent]);
      continue;
    }
    const [chosen, effort] = opinionPick(data, registry, provider, pinned);
    const family = providerFamily(data, registry, provider, chosen);
    if (!family) {
      skips.push([provider, reasons.priors_unknown]);
      asks.push(_priorsAsk(data, provider, chosen));
      continue;
    }
    const familyOwner = families.get(family);
    if (familyOwner !== undefined) {
      skips.push([provider, fill(reasons.same_priors, { owner: familyOwner })]);
      continue;
    }
    const modelOwner = chosen ? models.get(chosen) : undefined;
    if (modelOwner !== undefined) {
      skips.push([provider, fill(reasons.same_model, { owner: modelOwner })]);
      continue;
    }
    families.set(family, provider);
    if (chosen) {
      models.set(chosen, provider);
    }
    chain.push([provider, chosen, effort]);
  }
  return [chain, skips, asks];
}

/**
 * The whole admissible chain, in rank order from rank 2: every provider the walk kept, resolved.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @returns {SecondOpinionTarget[]}
 */
export function opinionChain(data, runtimeData, registry, session) {
  const [chain] = _walkOpinionLadder(data, runtimeData, registry, session);
  return chain.map(
    ([provider, model, effort]) =>
      new SecondOpinionTarget(provider, model, providerFamily(data, registry, provider, model), effort),
  );
}

/**
 * The provider at `rank` of the chain the walk produced, or `null` past its end.
 *
 * `null` says the chain is empty or shorter than asked; the caller then takes the disclosed last
 * resort (ADR-0024/D07) rather than arriving at the same model without saying so.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @param {{rank?: number}} [options]
 * @returns {SecondOpinionTarget | null}
 */
export function resolveOpinionChain(data, runtimeData, registry, session, { rank = OPINION_RANK_SECOND } = {}) {
  const chain = opinionChain(data, runtimeData, registry, session);
  const index = rank - OPINION_RANK_SECOND;
  return index >= 0 && index < chain.length ? chain[index] : null;
}

/**
 * Every provider passed over and why — the ledger that travels with the report (ADR-0024/D08).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @returns {[string, string][]}
 */
export function opinionSkips(data, runtimeData, registry, session) {
  return _walkOpinionLadder(data, runtimeData, registry, session)[1];
}

/**
 * One line per unknown prior the walk met, each naming the key and the file that would settle it (D08, D11).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @returns {string[]}
 */
export function opinionAsks(data, runtimeData, registry, session) {
  return _walkOpinionLadder(data, runtimeData, registry, session)[2];
}

/**
 * The disclosed last resort for an empty chain: the session's own provider, on a different model if declared.
 *
 * The strongest entry of the provider's declared `models` that differs from the session's model —
 * read from the provider table and not from the tier binding's rungs (ADR-0024/D14) — and only
 * when none differs the carrier's own default in a clean context (D07). The caller files the run
 * as `kind=last-resort`: same priors are never bought, only disclosed.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {SecondOpinionSession} session
 * @returns {SecondOpinionTarget}
 */
export function opinionLastResort(data, registry, session) {
  const row = providerRow(data, registry, session.provider);
  const declared = _iterate(_or(_get(row, "models"), []))
    .map(_pyStr)
    .filter((entry) => splitModelEffort(entry)[0] !== session.model);
  const [model, effort] = splitModelEffort(declared.length ? declared[declared.length - 1] : null);
  const family = providerFamily(data, registry, session.provider, model) ?? session.family;
  return new SecondOpinionTarget(session.provider, model, family, effort);
}

/**
 * What the reviewer could see: derived for a carrier akmon ships, stated or unknown for the rest.
 *
 * A knob would let a report claim repository access a bare completion cannot have, so a harness
 * carrier is `worktree`, a tool carrier is `none`, and a carrier its owner declared with nothing
 * said reports `unknown` instead of the optimistic reading (ADR-0024/D10, D12).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @returns {string}
 */
export function opinionRepo(data, registry, provider) {
  const row = providerRow(data, registry, provider);
  const stated = _get(row, "repo");
  if (_truthy(stated)) {
    return _pyStr(stated);
  }
  if (_truthy(_get(row, "argv"))) {
    return "unknown";
  }
  return _pyEq(_get(row, "carrier"), "tool") || _truthy(_get(row, "raw_model")) ? "none" : "worktree";
}

/**
 * The carrier kind the report names: `declared` for an owner's own argv, else the row's kind or `harness`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @returns {string}
 */
export function opinionCarrier(data, registry, provider) {
  const row = providerRow(data, registry, provider);
  return _truthy(_get(row, "argv")) ? "declared" : _pyStr(_or(_get(row, "carrier"), "harness"));
}

/**
 * `parts` with every `{model}` element gone, and the bare flag that pointed at a lone one.
 * @param {string[]} parts
 * @returns {string[]}
 */
function _withoutModelPlaceholder(parts) {
  /** @type {string[]} */
  const kept = [];
  for (const part of parts) {
    if (!part.includes("{model}")) {
      kept.push(part);
    } else if (
      part === "{model}" &&
      kept.length &&
      kept[kept.length - 1].startsWith("-") &&
      !kept[kept.length - 1].includes("=")
    ) {
      kept.pop();
    }
  }
  return kept;
}

/**
 * The argv for one provider: the command map for a shipped carrier, the owner's own list for a declared one.
 *
 * The executable and the operation's prefix come from `common/runtime.json` — the sole owner — and
 * the row adds only policy: its `model_flag` and the prompt as the last argument. A declared `argv`
 * is a list and is never split or handed to a shell (ADR-0024/D12) — the config the owner wrote is
 * the trust boundary, and a command string would make every value in it a candidate command.
 * `{model}` is the one placeholder, and a pin with nowhere to go raises `UnpinnableModelError`
 * rather than shipping an unpinned run filed as a diverse one (C97). Unpinned, an element holding
 * `{model}` is dropped whole; when that element is exactly `{model}` and the one before it is a bare
 * flag (leading `-`, no `=`), the flag goes with it, so `["qwen", "-m", "{model}"]` runs as
 * `["qwen"]` rather than with a flag that now eats the next argument (`_withoutModelPlaceholder`).
 * A row with `prompt: "stdin"` gets no prompt argument; the caller feeds the pack on stdin.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {string} provider
 * @param {{model?: Json, effort?: string | null, prompt?: Json}} [options]
 * @returns {string[]}
 */
export function opinionCommand(
  data,
  runtimeData,
  registry,
  provider,
  { model = null, effort = null, prompt = null } = {},
) {
  checkEffort(data, registry, provider, effort);
  const row = providerRow(data, registry, provider);
  const argv = _get(row, "argv");
  /** @type {string[]} */
  let parts;
  if (Array.isArray(argv)) {
    parts = argv.map(_pyStr);
    if (_truthy(model)) {
      if (!parts.some((part) => part.includes("{model}"))) {
        throw new UnpinnableModelError(data, provider, _pyStr(model));
      }
      parts = parts.map((part) => part.replaceAll("{model}", () => _pyStr(model)));
    } else {
      parts = _withoutModelPlaceholder(parts);
    }
  } else {
    parts = harnessCommand(runtimeData, provider, _pyStr(_get(row, "operation", "review")));
    if (_truthy(model)) {
      const modelFlag = _get(row, "model_flag");
      if (!_truthy(modelFlag)) {
        throw new UnpinnableModelError(data, provider, _pyStr(model));
      }
      parts.push(...shlexSplit(_pyStr(modelFlag)).map((part) => part.replaceAll("{model}", () => _pyStr(model))));
    }
  }
  if (effort !== null) {
    const flag = _pyStr(_get(_get(row, "efforts"), "flag"));
    parts.push(...shlexSplit(flag).map((part) => part.replaceAll("{effort}", () => effort)));
  }
  if (_truthy(prompt) && _pyStr(_get(row, "prompt", "argv")) !== "stdin") {
    parts.push(_pyStr(prompt));
  }
  return parts;
}

// --------------------------------------------------------------------------------------
// Model aliases (ADR-0024/D16): shipped aliases, concrete ids only in a local file
// --------------------------------------------------------------------------------------

/** The catalog formats `parseCatalog` reads; `bin/verify.json` keeps the same closed list for the verifier. */
export const CATALOG_FORMATS = Object.freeze(["codex-models-cache"]);

const _CODEX_SLUG = /^([a-z][a-z0-9]*)-(\d+(?:\.\d+)*)-([a-z]+)$/;

/** A provider row declares `aliases: true` and the alias asked for has no concrete id in the local file. */
export class UnresolvedAliasError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "UnresolvedAliasError";
  }
}

/** One provider's entry of the resolved-aliases file: what produced it, the client version, alias → concrete id. */
export class ProviderAliases {
  /**
   * @param {string} source
   * @param {string | null} client
   * @param {Record<string, string>} aliases
   */
  constructor(source, client, aliases) {
    this.source = source;
    this.client = client;
    this.aliases = aliases;
    Object.freeze(this);
  }
}

/** A catalog slug that names a versioned alias: `gpt-6.1-sol` is alias `sol` at version `[6, 1]`. */
export class CatalogModel {
  /**
   * @param {string} slug
   * @param {string} alias
   * @param {number[]} version
   * @param {number | null} priority
   */
  constructor(slug, alias, version, priority) {
    this.slug = slug;
    this.alias = alias;
    this.version = version;
    this.priority = priority;
    Object.freeze(this);
  }
}

/** What a provider's catalog lists: the carrier version it states, if any, and its listed versioned models. */
export class Catalog {
  /**
   * @param {string | null} client
   * @param {CatalogModel[]} models
   */
  constructor(client, models) {
    this.client = client;
    this.models = models;
    Object.freeze(this);
  }
}

/**
 * The resolved-aliases file's path, project-root-relative — what an unresolved alias asks to have refreshed.
 * @param {AgentsData} data
 * @returns {string}
 */
function _aliasFile(data) {
  return `${aitnaRootName()}/${localAliasesRel(data)}`;
}

/**
 * `value` as a `ProviderAliases`, or `null` when it does not have the file's shape.
 * @param {Json} value
 * @returns {ProviderAliases | null}
 */
function _validProviderAliases(value) {
  if (!_isDict(value)) {
    return null;
  }
  const source = _get(value, "source");
  const client = _get(value, "client");
  const aliases = _get(value, "aliases");
  if (typeof source !== "string" || !(client === null || typeof client === "string") || !_isDict(aliases)) {
    return null;
  }
  if (!Object.values(aliases).every((item) => typeof item === "string")) {
    return null;
  }
  return new ProviderAliases(source, client, /** @type {Record<string, string>} */ ({ ...aliases }));
}

/**
 * The resolved-aliases file as typed entries by provider; `{}` when it does not exist.
 *
 * A file that is not the shape `models.mjs` writes raises `ValueError` naming it: the file is
 * generated, so the cure is deleting it and refreshing, never a hand edit.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {Record<string, ProviderAliases>}
 */
export function readModelAliases(data, projectRoot) {
  const path = localAliasesPath(data, projectRoot);
  if (!_isFile(path)) {
    return {};
  }
  const invalid = () => _pyError("ValueError", fill(data.alias_errors.invalid, { file: _aliasFile(data) }));
  let parsed;
  try {
    parsed = _parseKeepingFloats(_readText(path));
  } catch (error) {
    if (error instanceof SyntaxError) {
      throw Object.assign(invalid(), { cause: error });
    }
    throw error;
  }
  if (!_isDict(parsed)) {
    throw invalid();
  }
  /** @type {Record<string, ProviderAliases>} */
  const entries = {};
  for (const [provider, value] of Object.entries(parsed)) {
    const entry = _validProviderAliases(value);
    if (entry === null) {
      throw invalid();
    }
    entries[provider] = entry;
  }
  return entries;
}

/**
 * The file's text for `stored`: indent 2, insertion order, a trailing newline (no dates, nothing host-wide).
 * @param {Record<string, ProviderAliases>} stored
 * @returns {string}
 */
export function modelAliasesDocument(stored) {
  /** @type {Record<string, Json>} */
  const document = {};
  for (const [provider, entry] of Object.entries(stored)) {
    document[provider] = { source: entry.source, client: entry.client, aliases: { ...entry.aliases } };
  }
  return wiringForm(document);
}

/**
 * Whether `model` is an alias the carrier does not accept: the row says `aliases: true` and lists it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string} provider
 * @param {string} model
 * @returns {boolean}
 */
export function isModelAlias(data, registry, provider, model) {
  const row = providerRow(data, registry, provider);
  const models = _get(row, "models");
  // An entry may carry an @effort (ADR-0024/D17); the alias is the model before it.
  return (
    _get(row, "aliases") === true &&
    Array.isArray(models) &&
    models.map((entry) => splitModelEffort(_pyStr(entry))[0]).includes(model)
  );
}

/**
 * The model a carrier is sent: an alias replaced by its concrete id, anything else passed through.
 *
 * Only a model that is an alias of an `aliases: true` row is replaced; a concrete id (not in the
 * row's `models`) and the carrier's own default (`null`) pass through. An alias with no mapping
 * raises `UnresolvedAliasError` naming the refresh command — fail closed, never an unresolved alias
 * sent to the carrier (ADR-0024/D16, D08).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Record<string, ProviderAliases>} stored
 * @param {string} provider
 * @param {string | null} model
 * @returns {string | null}
 */
export function resolveOpinionModel(data, registry, stored, provider, model) {
  if (model === null || !isModelAlias(data, registry, provider, model)) {
    return model;
  }
  const entry = Object.hasOwn(stored, provider) ? stored[provider] : undefined;
  const concrete = entry !== undefined && Object.hasOwn(entry.aliases, model) ? entry.aliases[model] : "";
  if (!concrete) {
    throw new UnresolvedAliasError(fill(data.alias_errors.unresolved, { provider, model, file: _aliasFile(data) }));
  }
  return concrete;
}

/**
 * `pathText` with a leading `~` or `~/` replaced by `home` — the only expansion a catalog path takes.
 * @param {string} pathText
 * @param {string} home
 * @returns {string}
 */
export function expandHome(pathText, home) {
  if (pathText === "~" || pathText.startsWith("~/")) {
    return home.replace(/\/+$/, "") + pathText.slice(1) || "/";
  }
  return pathText;
}

/**
 * A catalog file's text read as `catalogFormat`; `ValueError` says what is wrong with it, not where.
 *
 * `codex-models-cache`: `{"models": [{"slug", "visibility", "priority", ...}]}`. Only `visibility ==
 * "list"` entries count, and a slug counts when it reads `<family>-<version>-<alias>` (`gpt-6.1-sol`):
 * `gpt-reserve` and `codex-auto-review` are ignored, never guessed at.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} text
 * @param {string} catalogFormat
 * @returns {Catalog}
 */
export function parseCatalog(data, text, catalogFormat) {
  const texts = data.catalog_errors;
  if (!CATALOG_FORMATS.includes(catalogFormat)) {
    throw _pyError("ValueError", fill(texts.format, { format: catalogFormat, known: CATALOG_FORMATS.join(", ") }));
  }
  let parsed;
  try {
    parsed = _parseKeepingFloats(text);
  } catch (error) {
    if (error instanceof SyntaxError) {
      throw Object.assign(_pyError("ValueError", texts.json), { cause: error });
    }
    throw error;
  }
  const listed = _isDict(parsed) ? _get(parsed, "models") : null;
  if (!Array.isArray(listed)) {
    throw _pyError("ValueError", texts.shape);
  }
  const client = _get(parsed, "client_version");
  /** @type {CatalogModel[]} */
  const models = [];
  for (const entry of listed) {
    const slug = _isDict(entry) ? _get(entry, "slug") : null;
    const match = typeof slug === "string" ? _CODEX_SLUG.exec(slug) : null;
    if (match === null || typeof slug !== "string" || _get(entry, "visibility") !== "list") {
      continue;
    }
    const priority = _get(entry, "priority");
    models.push(
      new CatalogModel(
        slug,
        match[3],
        match[2].split(".").map(Number),
        typeof priority === "number" && Number.isInteger(priority) ? priority : null,
      ),
    );
  }
  return new Catalog(typeof client === "string" ? client : null, models);
}

/**
 * Whether version `left` is above `right`, compared part by part, a shorter prefix lower.
 * @param {number[]} left
 * @param {number[]} right
 * @returns {number} negative, zero or positive as `left` is below, equal to or above `right`
 */
function _compareVersions(left, right) {
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    if (left[index] !== right[index]) {
      return left[index] - right[index];
    }
  }
  return left.length - right.length;
}

/**
 * A model's catalog priority as a number where lower is better; a model stating none ranks last.
 * @param {CatalogModel} model
 * @returns {number}
 */
function _rankOf(model) {
  return model.priority === null ? Number.POSITIVE_INFINITY : model.priority;
}

/**
 * Each of `aliases` mapped to its highest-versioned slug, ties by lowest priority; an unmatched one is absent.
 *
 * Absent means unmapped: nothing here guesses an id for an alias the catalog does not list
 * (ADR-0024/D16). The result follows `aliases`' order.
 * @param {Catalog} catalog
 * @param {string[]} aliases
 * @returns {Record<string, string>}
 */
export function catalogAliases(catalog, aliases) {
  /** @type {Record<string, string>} */
  const resolved = {};
  for (const alias of aliases) {
    /** @type {CatalogModel | null} */
    let best = null;
    for (const model of catalog.models) {
      if (model.alias !== alias) {
        continue;
      }
      const order = best === null ? 1 : _compareVersions(model.version, best.version);
      if (best === null || order > 0 || (order === 0 && _rankOf(model) < _rankOf(best))) {
        best = model;
      }
    }
    if (best !== null) {
      resolved[alias] = best.slug;
    }
  }
  return resolved;
}

/**
 * What the second opinion would run first, as a display and any warning (the status line and the init summary).
 *
 * Resolved through the same walk the runner takes rather than through any stored provider: a
 * display that can disagree with the policy is a second owner of one fact, the drift class C46
 * exists to remove. `priors=unknown` stands for a session nobody could name the family of, and the
 * warning carries the ask beside it (ADR-0024/D08); a stale key raises out of here
 * (`refuseRetiredKeys`) and costs the whole status block, deliberately.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} registry
 * @param {Json} config
 * @returns {[string, string | null]}
 */
export function opinionHead(data, runtimeData, registry, config) {
  refuseRetiredKeys(data, registry, config);
  const texts = data.opinion_status;
  /** @type {SecondOpinionSession} */
  let session;
  try {
    session = resolveSession(data, registry, config);
  } catch (error) {
    if (error instanceof SessionUnknownError) {
      return [texts.unavailable_unknown, error.message];
    }
    throw error;
  }
  if (!_truthy(session.family)) {
    return [texts.unavailable_unknown, _sessionAsk(data, session)];
  }
  const chain = opinionChain(data, runtimeData, registry, session);
  if (chain.length === 0) {
    return [texts.unavailable, fill(texts.chain_empty, { provider: session.provider })];
  }
  const head = chain[0];
  let pin = head.model || (head.effort !== null ? defaultModelToken(data) : "");
  pin = head.effort !== null ? `${pin}@${head.effort}` : pin;
  const target = pin ? `${head.provider}:${pin}` : head.provider;
  return [fill(texts.head, { target, family: head.family || "unknown" }), null];
}

// --------------------------------------------------------------------------------------
// Generated subagent definitions (the `k-` akmon namespace)
// --------------------------------------------------------------------------------------

// Each agent groups the task kinds whose briefs coincide; the tier picks its model from
// the binding. Bodies are project-neutral (this is SHARED); project specifics are appended
// via the overlay's "briefs" map.
/** One generated `k_*` subagent's definition: tier, description, tools, body, task kinds. */
export class AgentSpec {
  /**
   * @param {string} name
   * @param {string} tier "worker" | "mid" | "reasoner" | "auditor"
   * @param {string} description
   * @param {string | null} tools frontmatter `tools:`; null = all tools
   * @param {string} body
   * @param {string[]} [kinds]
   */
  constructor(name, tier, description, tools, body, kinds = []) {
    this.name = name;
    this.tier = tier;
    this.description = description;
    this.tools = tools;
    this.body = body;
    this.kinds = Object.freeze([...kinds]);
    Object.freeze(this);
  }
}

/**
 * The six generated `k_*` subagent definitions (`agents.json`), in roster order.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {AgentSpec[]}
 */
export function agentSpecs(data) {
  return data.agent_specs.map(
    (raw) => new AgentSpec(raw.name, raw.tier, raw.description, raw.tools, raw.body, raw.kinds),
  );
}

/**
 * The model one agent's frontmatter pins: its tier's alias, or null under semantic fallback.
 * @param {AgentSpec} spec
 * @param {Binding} binding
 * @returns {Json}
 */
function _agentModel(spec, binding) {
  if (binding.semanticFallback) {
    return null;
  }
  return _item(
    { worker: binding.worker, mid: binding.mid, reasoner: binding.reasoner, auditor: binding.auditor },
    spec.tier,
  );
}

/**
 * Render one generated `.claude/agents/<name>.md` file: frontmatter, banner, body, brief.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {AgentSpec} spec
 * @param {Binding} binding
 * @param {string} [briefExtra]
 * @returns {string}
 */
export function agentFileContent(data, spec, binding, briefExtra = "") {
  const lines = ["---", `name: ${spec.name}`, "description: >-"];
  // The auditor reads a fan-out rather than being a zone of it, so it carries no zone convention.
  const description = spec.name === "k_auditor" ? spec.description : `${spec.description} ${zoneConvention(data)}`;
  lines.push(..._wrap(description, 88).map((chunk) => `  ${chunk}`));
  if (spec.tools) {
    lines.push(`tools: ${spec.tools}`);
  }
  const model = _agentModel(spec, binding);
  if (_truthy(model)) {
    lines.push(`model: ${_pyStr(model)}`);
  }
  lines.push("---");
  lines.push("");
  lines.push(`<!-- ${generatedBanner(data)} -->`);
  lines.push("");
  lines.push(spec.body);
  if (_strip(briefExtra)) {
    lines.push("");
    lines.push("<!-- project overlay brief -->");
    lines.push("");
    lines.push(_strip(briefExtra));
  }
  return lines.join("\n") + "\n";
}

/**
 * Greedy word wrap at `width` code points; a word longer than the width stands alone.
 * @param {string} text
 * @param {number} width
 * @returns {string[]}
 */
function _wrap(text, width) {
  /** @type {string[]} */ const chunks = [];
  let current = "";
  for (const word of _split(text)) {
    const candidate = current ? `${current} ${word}` : word;
    if (_len(candidate) > width && current) {
      chunks.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) {
    chunks.push(current);
  }
  return chunks;
}

/**
 * A project overlay's `briefs` map cannot be applied to the current agent specs.
 *
 * Raised instead of defaulting to an empty brief: an overlay brief is hand-authored
 * project instruction, and a key that matches no agent means those instructions would
 * silently vanish from the generated definition — no diff to look at, no warning. That is
 * the tolerance-degrades-to-silence shape C48 argues against, and ADR 0011's `k-*` →
 * `k_*` rename made it live (C50).
 */
export class BriefError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "BriefError";
  }
}

/**
 * Normal form of an agent name for overlay lookups — folds case, `-`/`_` and surrounding whitespace.
 *
 * Overlay brief keys are a public contract written by hand in a consumer's repository, so
 * a change of *notation* (ADR 0011) must not orphan them. The tolerance line, owner-verified
 * at ADR-0011/D02: invisible and notational differences are forgiven — surrounding whitespace does
 * not survive a diff, so failing on it costs more to diagnose than the tolerance costs to hold
 * — while any difference in significant characters, an internal space included, still fails
 * (see `resolveBriefs`).
 * @param {string} name
 * @returns {string}
 */
export function agentKey(name) {
  return _strip(name).toLowerCase().replaceAll("-", "_");
}

/**
 * Overlay briefs re-keyed by the **current** spec names; raises `BriefError` otherwise.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @returns {Record<string, string>}
 */
export function resolveBriefs(data, registry) {
  const briefs = _get(registry, "briefs", {});
  if (!_isDict(briefs)) {
    throw new BriefError(`overlay 'briefs' must be an object, got ${_pyTypeName(briefs)}`);
  }
  /** @type {Map<string, string>} */ const byKey = new Map();
  for (const spec of agentSpecs(data)) {
    byKey.set(agentKey(spec.name), spec.name);
  }
  /** @type {Record<string, string>} */ const resolved = {};
  /** @type {Record<string, string>} */ const source = {};
  const keys = Object.keys(briefs).sort(codePointCompare);
  for (const key of keys) {
    const text = briefs[key];
    if (typeof text !== "string") {
      throw new BriefError(`overlay brief '${key}' must be a string, got ${_pyTypeName(text)}`);
    }
    const name = byKey.get(agentKey(key));
    if (name === undefined) {
      const known = codePointSort([...byKey.values()]).join(", ");
      throw new BriefError(`overlay brief key '${key}' matches no agent (known: ${known})`);
    }
    if (Object.hasOwn(resolved, name)) {
      throw new BriefError(`overlay brief keys '${source[name]}' and '${key}' both resolve to '${name}'`);
    }
    source[name] = key;
    resolved[name] = text;
  }
  return resolved;
}

/**
 * Owner-addressed line naming an unusable overlay `briefs` map, or null when it is fine.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string | null} [aitna]
 * @returns {string | null}
 */
export function briefWarning(data, registry, aitna = null) {
  try {
    resolveBriefs(data, registry);
  } catch (error) {
    if (!(error instanceof BriefError)) {
      throw error;
    }
    const root = aitna || aitnaRootName();
    return `⚠ ${error.message} — fix ${root}/${overlayName(data)}; k_* definitions are not regenerated until it resolves`;
  }
  return null;
}

const _REBIND_MARKER = "suppressed-rebind";

/**
 * Emit one warning per session/model/error episode; reset when the condition clears.
 *
 * A refused rebind leaves the recorded orchestrator unchanged, so comparing the next
 * transcript against that config reports the same switch on every prompt. The marker is
 * deliberately temporary rather than project state: it remembers only which warning the
 * current session already saw. A changed model or error produces a new digest and re-arms
 * the notice; a cleared condition removes the marker so a later recurrence speaks again.
 *
 * Since C36(a) the marker is claimed through `common/markers` — atomic, hashed, `0600`,
 * aged out after a day — so exactly-once per episode is the contract. The condition is folded
 * into the marker's kind, and moving to another condition or clearing it releases the
 * session's other markers, which is what re-arms a later recurrence.
 * @param {MarkersData} markersData the parsed `common/markers.json`
 * @param {string | null} warning
 * @param {Json} detectedModel
 * @param {Json} sessionId
 * @param {{markerDir?: string | null}} [options]
 * @returns {string[]}
 */
export function suppressedRebindWarning(markersData, warning, detectedModel, sessionId, { markerDir = null } = {}) {
  // Without a reliable session identity, never let one anonymous invocation silence
  // another session. Repeating the warning is safer than a process-global `nosession`
  // marker that hides an unresolved lossy-rebind condition from an unrelated owner.
  if (!_truthy(sessionId)) {
    return warning !== null && warning !== undefined && detectedModel !== null && detectedModel !== undefined
      ? [warning]
      : [];
  }
  const session = _pyStr(sessionId);
  if (warning === null || warning === undefined || detectedModel === null || detectedModel === undefined) {
    releaseDiagnosticMarkers(markersData, _REBIND_MARKER, session, { directory: markerDir });
    return [];
  }
  const fingerprint = `${_pyStr(detectedModel)}\0${warning}`;
  _utf8(fingerprint); // refuses a lone surrogate, as str.encode() does
  const condition = sha256Hex(fingerprint).slice(0, 16);
  const kind = `${_REBIND_MARKER}-${condition}`;
  if (!claimDiagnosticMarker(markersData, kind, session, { directory: markerDir })) {
    return [];
  }
  releaseDiagnosticMarkers(markersData, _REBIND_MARKER, session, { keepKind: kind, directory: markerDir });
  return [warning];
}

/**
 * Map of `.claude/agents/<name>.md` relative paths → generated content.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Binding} binding
 * @returns {Record<string, string>}
 */
export function generatedAgentFiles(data, registry, binding) {
  const briefs = resolveBriefs(data, registry);
  /** @type {Record<string, string>} */ const files = {};
  for (const spec of agentSpecs(data)) {
    files[`${agentsDirRel(data)}/${spec.name}.md`] = agentFileContent(
      data,
      spec,
      binding,
      Object.hasOwn(briefs, spec.name) ? briefs[spec.name] : "",
    );
  }
  return files;
}

/**
 * The roster keyed by name (a Map: a name is never confused with an object property).
 * @param {AgentsData} data
 * @returns {Map<string, AgentSpec>}
 */
function _agentByName(data) {
  return new Map(agentSpecs(data).map((spec) => [spec.name, spec]));
}

/**
 * Task kinds a generated subagent covers; empty for a host built-in / unknown name.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} name
 * @returns {readonly string[]}
 */
export function subagentKinds(data, name) {
  const spec = typeof name === "string" ? _agentByName(data).get(name) : undefined;
  return spec ? spec.kinds : [];
}

/**
 * Model a generated `k_*` agent is pinned to — its tier's binding alias, or null.
 *
 * The generated agent frontmatter carries `model: <alias>`, but an `Agent` call rarely echoes
 * it — so the delegation record shows `-` and the console line omits the model. Deriving it
 * from the recorded binding restores it. Null for an unknown agent (a host built-in) or for a
 * semantic-fallback binding, whose tier values are labels (`worker`/`strongest`), not vendor
 * aliases.
 *
 * The config does not persist `Binding.semanticFallback`, so the mode is re-derived the
 * same way `computeBinding` decides it: **no recorded `available` ladder is exactly
 * semantic fallback**. That is the mirror of the agent file emitting no `model:` line — an
 * agent file without a pin is inherited by the host from the session, so there is no pin to
 * report and the record honestly says `-`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} subagentType
 * @returns {string | null}
 */
export function boundModelFor(data, config, subagentType) {
  const spec = typeof subagentType === "string" ? _agentByName(data).get(subagentType) : undefined;
  if (spec === undefined || !_isDict(config)) {
    return null;
  }
  const binding = config.binding;
  if (!_isDict(binding)) {
    return null;
  }
  const model = Object.hasOwn(binding, spec.tier) ? binding[spec.tier] : null;
  if (typeof model !== "string" || !model) {
    return null;
  }
  const available = config.available;
  if (!Array.isArray(available) || available.length === 0 || !available.every((alias) => typeof alias === "string")) {
    return null;
  }
  // The opted-in auditor is an auditor-only rung: pinned although the ladder never lists it.
  if (!available.includes(model) && !(spec.tier === "auditor" && model === config.auditor_opt_in)) {
    return null;
  }
  return model;
}

// A declaration: `🧭 agent: <name>` as the first non-whitespace text of a turn (`re.ASCII`).
const _ROLE_DECL_RE = /^[ \t\n\r\f\v]*🧭[ \t\n\r\f\v]*agent:[ \t\n\r\f\v]*([A-Za-z][A-Za-z0-9_-]*)/u;

/**
 * The text of an assistant turn: its string content, or its text blocks joined by a space.
 * @param {Record<string, Json>} entry
 * @returns {string}
 */
function _assistantText(entry) {
  const message = entry.message;
  if (!_isDict(message)) {
    return "";
  }
  const content = message.content;
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return _join(
      " ",
      content.filter((block) => _isDict(block) && block.type === "text").map((block) => _get(block, "text", "")),
    );
  }
  return "";
}

/** Block size of the tail read. A line longer than one block is assembled across blocks. */
const _TAIL_BLOCK_BYTES = 1 << 16;
const _CR = 0x0d;
const _LF = 0x0a;

/**
 * The transcript path when it names a regular file, else null. The hook payload hands over any
 * JSON value: a falsy one (`[]`, `{}`, `0`) is no path, a truthy non-string is `Path()`'s `TypeError`.
 * @param {Json} transcriptPath
 * @returns {string | null}
 */
function _transcriptFile(transcriptPath) {
  if (!_truthy(transcriptPath)) {
    return null;
  }
  if (typeof transcriptPath !== "string") {
    throw _pyError(
      "TypeError",
      `argument should be a str or an os.PathLike object where __fspath__ returns a str, not '${_pyTypeName(transcriptPath)}'`,
    );
  }
  const path = _path(transcriptPath);
  return _isFile(path) ? path : null;
}

/**
 * `block` split on `\r\n`, `\r` and `\n` (the exact split), or on `\n` alone.
 * @param {Buffer} block
 * @param {boolean} exact
 * @returns {Buffer[]}
 */
function _splitBlock(block, exact) {
  /** @type {Buffer[]} */ const pieces = [];
  let start = 0;
  for (let i = 0; i < block.length; i++) {
    const byte = block[i];
    if (byte === _LF || (exact && byte === _CR)) {
      pieces.push(block.subarray(start, i));
      if (exact && byte === _CR && block[i + 1] === _LF) {
        i += 1;
      }
      start = i + 1;
    }
  }
  pieces.push(block.subarray(start));
  return pieces;
}

/**
 * Up to `size` bytes at `position`, short only at the end of the file — a buffered `read(size)`.
 * @param {number} fd
 * @param {number} position
 * @param {number} size
 * @returns {Buffer}
 */
function _readAt(fd, position, size) {
  const buffer = Buffer.alloc(size);
  let filled = 0;
  while (filled < size) {
    const read = fs.readSync(fd, buffer, filled, size - filled, position + filled);
    if (read === 0) {
      break;
    }
    filled += read;
  }
  return buffer.subarray(0, filled);
}

/**
 * The lines of the open file `fd` that contain `needle`, last line first (A19).
 *
 * Both transcript scanners want the *last* record that qualifies, so reading from the end and
 * stopping at the first qualifying record returns what a full forward scan returns, at a cost
 * set by the distance from the end rather than by the file's size. Lines split on `\r\n`,
 * `\r` and `\n`, as a forward text-mode read splits them, and each line decodes as strict
 * UTF-8. A line that does not decode is skipped. Memory stays at one block plus the longest
 * line.
 * @param {number} fd
 * @param {Buffer} needle
 * @returns {Generator<string>}
 */
function* _linesFromEnd(fd, needle) {
  let position = fs.fstatSync(fd).size;
  /** @type {Buffer[]} */ let carry = []; // the start of the line that runs past the current block, in file order
  while (position > 0) {
    const size = Math.min(_TAIL_BLOCK_BYTES, position);
    position -= size;
    const block = _readAt(fd, position, size);
    // JSON escapes a carriage return, so a real transcript carries none, and the `\n` split is
    // the fast one. A block holding one takes the exact split — the Python's choice, kept
    // because it decides where a `\r\n` straddling two blocks splits.
    const pieces = _splitBlock(block, block.includes(_CR));
    if (pieces.length === 1) {
      carry.unshift(pieces[0]);
      continue;
    }
    const complete = [Buffer.concat([pieces[pieces.length - 1], ...carry]), ...pieces.slice(1, -1).reverse()];
    carry = [pieces[0]];
    yield* _decoded(complete, needle);
  }
  yield* _decoded([Buffer.concat(carry)], needle);
}

/**
 * The lines holding `needle`, decoded; a line that is not strict UTF-8 is skipped.
 * @param {Buffer[]} lines
 * @param {Buffer} needle
 * @returns {Generator<string>}
 */
function* _decoded(lines, needle) {
  for (const raw of lines) {
    if (raw.includes(needle)) {
      let text;
      try {
        text = _decode(raw);
      } catch {
        continue;
      }
      yield text;
    }
  }
}

/**
 * The record on `line` when it is a main-chain assistant turn, else null.
 *
 * Sidechain (subagent) turns are skipped, and so is a line that is not JSON — a torn last line
 * included, since the harness may be writing it while a hook reads.
 * @param {string} line
 * @returns {Record<string, Json> | null}
 */
function _mainChainAssistant(line) {
  let entry;
  try {
    entry = JSON.parse(line);
  } catch (error) {
    if (error instanceof SyntaxError) {
      return null;
    }
    throw error;
  }
  if (!_isDict(entry) || entry.type !== "assistant" || _truthy(entry.isSidechain)) {
    return null;
  }
  return entry;
}

/**
 * Scan a transcript's matching lines from the end with `visit` until it answers non-undefined;
 * a filesystem failure (`OSError`) ends the scan with `fallback`, anything else propagates.
 * @template T
 * @param {string} path
 * @param {Buffer} needle
 * @param {(line: string) => T | undefined} visit
 * @param {T} fallback
 * @returns {T}
 */
function _scanFromEnd(path, needle, visit, fallback) {
  let fd;
  try {
    fd = fs.openSync(path, "r");
  } catch (error) {
    if (_isOSError(error)) {
      return fallback;
    }
    throw error;
  }
  try {
    for (const line of _linesFromEnd(fd, needle)) {
      const answer = visit(line);
      if (answer !== undefined) {
        return answer;
      }
    }
  } catch (error) {
    if (_isOSError(error)) {
      return fallback;
    }
    throw error;
  } finally {
    try {
      fs.closeSync(fd);
    } catch {
      // the scan's answer stands; a failed close of a read-only descriptor changes nothing
    }
  }
  return fallback;
}

/**
 * The role from the last qualifying `🧭 agent: <name>` transcript declaration.
 *
 * Only main-chain assistant turns are read, so the SessionStart reminder / a subagent echo
 * never masquerades as the declaration. A declaration qualifies only as the first
 * non-whitespace text of its turn. Returns the case-normalized role name, else null.
 *
 * Read from the end (A19), stopping at the first qualifying declaration, which is the last one.
 * A session that never declared a role still reads the whole file.
 * @param {string | null | undefined} transcriptPath
 * @returns {string | null}
 */
export function activeRole(transcriptPath) {
  const path = _transcriptFile(transcriptPath);
  if (path === null) {
    return null;
  }
  // Cheap ascii pre-filter: the emoji may be \u-escaped in the JSONL, but "agent:" is
  // always literal. JSON.parse then decodes the real marker.
  return _scanFromEnd(
    path,
    Buffer.from("agent:"),
    (line) => {
      const entry = _mainChainAssistant(line);
      const match = entry !== null ? _ROLE_DECL_RE.exec(_assistantText(entry)) : null;
      return match ? match[1].toLowerCase() : undefined;
    },
    /** @type {string | null} */ (null),
  );
}

/**
 * Conservative advisory (§10.2): the agent has no effectively allowed task kind.
 *
 * The call carries the agent, not an authoritative invocation kind, so warn only when *none*
 * of the agent's kinds intersect the role's effective allowed set. Null when the role is
 * unknown/undeclared or the agent is a host built-in (no kinds).
 *
 * **Cross-cutting verification kinds** (`cross_cutting_kinds`) are *not* role-gated (A7 (b),
 * §10.2): they join every role's allowed set, so an agent whose only kinds are cross-cutting
 * (e.g. `k_auditor`) never warns under any role.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} subagentType
 * @param {string | null} role
 * @returns {string | null}
 */
export function roleMatrixWarning(data, registry, subagentType, role) {
  const fields = _roleMatrixFields(data, registry, subagentType, role);
  return fields === null ? null : fill(data.role_matrix_warning, fields);
}

/**
 * The model-addressed form of `roleMatrixWarning`: re-route or switch role.
 *
 * Same predicate, same silence; the delegation log sends it as `additionalContext` beside the
 * owner's `systemMessage` (ADR 0006 item 4, M149).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} subagentType
 * @param {string | null} role
 * @returns {string | null}
 */
export function roleMatrixDirective(data, registry, subagentType, role) {
  const fields = _roleMatrixFields(data, registry, subagentType, role);
  return fields === null ? null : fill(data.role_matrix_directive, fields);
}

/**
 * The role-matrix advisory's template fields, or null when it stays silent (§10.2).
 * @param {AgentsData} data
 * @param {Json} registry
 * @param {Json} subagentType
 * @param {string | null} role
 * @returns {Record<string, string> | null}
 */
function _roleMatrixFields(data, registry, subagentType, role) {
  if (!role) {
    return null;
  }
  const roleRows = _get(registry, "role_task_kinds", {});
  if (!_isDict(roleRows) || !Object.hasOwn(roleRows, role)) {
    return null;
  }
  const allowed = roleRows[role];
  if (!Array.isArray(allowed)) {
    return null;
  }
  /** @type {Json[]} */ const effectiveAllowed = [];
  for (const kind of [...allowed, ..._iterate(_get(registry, "cross_cutting_kinds", []))]) {
    if (kind !== null && typeof kind === "object" && !(kind instanceof FloatValue)) {
      throw _pyError("TypeError", `unhashable type: '${_pyTypeName(kind)}'`);
    }
    if (!effectiveAllowed.some((seen) => _pyEq(seen, kind))) {
      effectiveAllowed.push(kind);
    }
  }
  const kinds = subagentKinds(data, subagentType);
  if (kinds.length === 0 || kinds.some((kind) => effectiveAllowed.some((allowedKind) => _pyEq(allowedKind, kind)))) {
    return null;
  }
  const allowedText = _join(", ", effectiveAllowed) || "no task kinds";
  return {
    subagent: _pyStr(subagentType),
    kinds: kinds.join(", "),
    role,
    allowed: allowedText,
  };
}

// --------------------------------------------------------------------------------------
// Local config + status line (the SessionStart hook contract)
// --------------------------------------------------------------------------------------

/**
 * Map a concrete vendor model id (e.g. `claude-opus-4-8`) to a known local alias.
 *
 * The alias is matched as a case-insensitive substring of the id, preferring the longest
 * match so overlapping aliases disambiguate (`opus` over a bare `o`). Null when no alias in
 * `available` matches — the caller keeps the recorded binding rather than guess.
 * @param {Json} modelId
 * @param {Json} available
 * @returns {Json}
 */
export function resolveAlias(modelId, available) {
  if (!_truthy(modelId) || !_truthy(available)) {
    return null;
  }
  const lowered = _lower(modelId);
  const matches = _iterate(available).filter((alias) => _truthy(alias) && lowered.includes(_lower(alias)));
  return matches.length ? _longest(matches) : null;
}

/** `(model id, usage)` of the last main-chain assistant turn — what `lastMainTurn` returns. */
/** @typedef {[string | null, Record<string, Json> | null]} MainTurn */

/**
 * (model id, usage) of the last *main-chain* assistant turn in the session transcript.
 *
 * The transcript (a JSONL the harness records; its path arrives in the hook payload) carries
 * `message.model` and `message.usage` per assistant turn. Sidechain (subagent) turns and
 * synthetic entries are skipped, so a delegate's model or usage never masquerades as the
 * orchestrator's. Read from the end (A19) and stopped at the first qualifying turn.
 * `[null, null]` when the transcript is missing/empty/unreadable or names no model yet.
 * @param {string | null | undefined} transcriptPath
 * @returns {MainTurn}
 */
export function lastMainTurn(transcriptPath) {
  const path = _transcriptFile(transcriptPath);
  if (path === null) {
    return [null, null];
  }
  return _scanFromEnd(
    path,
    Buffer.from('"model"'),
    (line) => {
      const entry = _mainChainAssistant(line);
      const message = entry !== null ? entry.message : null;
      const model = _isDict(message) ? message.model : null;
      if (typeof model === "string" && model && !model.startsWith("<")) {
        const usage = message.usage;
        return /** @type {MainTurn} */ ([model, _isDict(usage) ? usage : null]);
      }
      return undefined;
    },
    /** @type {MainTurn} */ ([null, null]),
  );
}

/**
 * Alias of the model the *main chain* last ran on, read from the session transcript.
 *
 * Null when the transcript names no model yet or the model maps to no known alias: the caller
 * then keeps the recorded orchestrator instead of guessing. `turn` is a `lastMainTurn` result
 * the caller already read; the transcript is read only without one.
 * @param {string | null | undefined} transcriptPath
 * @param {Json} available
 * @param {{turn?: MainTurn | null}} [options]
 * @returns {Json}
 */
export function detectOrchestrator(transcriptPath, available, { turn = null } = {}) {
  const [modelId] = turn !== null && turn !== undefined ? turn : lastMainTurn(transcriptPath);
  return resolveAlias(modelId, available);
}

/**
 * The aliases orchestrator detection recognises: the recorded ladder plus the vendor's
 * auditor-only rungs. Empty without a recorded ladder (the semantic case), so detection stays
 * silent there as before.
 * @param {Json} registry
 * @param {Json} config
 * @returns {string[]}
 */
export function detectionAliases(registry, config) {
  const ladder = _isDict(config) ? _get(config, "available") : null;
  if (!Array.isArray(ladder) || ladder.length === 0) {
    return [];
  }
  const vendor = _pyStr(_or(_get(config, "vendor"), "anthropic"));
  const auditorOnly = _or(_get(_get(registry, vendor, {}), "auditor_only_rungs"), []);
  return [...ladder, ...[..._iterate(auditorOnly)].filter((alias) => !ladder.includes(alias))];
}

// --------------------------------------------------------------------------------------
// Context-pressure detection (design §12, ADR 0006) — the tokens axis of runtime weakness
// --------------------------------------------------------------------------------------

/**
 * Context fill at a turn: the three input components partition the prompt.
 *
 * `output_tokens` is not context carried forward, so it is excluded. Null unless all three
 * input components are non-negative integers (a bool is not a count, a float is not either).
 * @param {Json} usage
 * @returns {number | null}
 */
export function contextFill(usage) {
  if (!_isDict(usage)) {
    return null;
  }
  const components = ["input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"].map((key) =>
    Object.hasOwn(usage, key) ? usage[key] : null,
  );
  if (!components.every((value) => typeof value === "number" && Number.isInteger(value) && value >= 0)) {
    return null;
  }
  return components.reduce((total, value) => total + value, 0);
}

/**
 * Overrides the recommended maximum for every model when it holds a positive integer — per user
 * (the shell, or `env` in `~/.claude/settings.json`) or per project (`env` in
 * `.claude/settings.json`). Any other value is ignored and the registry decides.
 */
export const RECOMMENDED_MAX_ENV = "AKMON_CONTEXT_RECOMMENDED_MAX";

/**
 * The recommended context budget, in tokens — what pressure percentages are a share of.
 *
 * Resolution: `AKMON_CONTEXT_RECOMMENDED_MAX` when it holds a positive integer, else the
 * longest alias-substring key of `recommended_max_by_alias` found in the model id, else
 * `recommended_max` (design §12.2, C80).
 * @param {Json} registry
 * @param {Json} modelId
 * @returns {number}
 */
export function recommendedMaxContext(registry, modelId) {
  let override;
  try {
    override = _pyInt(process.env[RECOMMENDED_MAX_ENV] ?? "");
  } catch (error) {
    if (/** @type {Error} */ (error).name !== "ValueError") {
      throw error;
    }
    override = 0;
  }
  if (override > 0) {
    return override;
  }
  const policy = _get(registry, "context_pressure", {});
  const fallback = _pyInt(_or(_get(policy, "recommended_max"), 200000));
  const byAlias = _get(policy, "recommended_max_by_alias", {});
  if (_truthy(modelId) && _isDict(byAlias)) {
    const lowered = _lower(modelId);
    const matches = Object.keys(byAlias).filter((key) => key && lowered.includes(key.toLowerCase()));
    if (matches.length) {
      return _pyInt(byAlias[_longest(matches)]);
    }
  }
  return fallback;
}

/**
 * `[fill, recommendedMax, ratio]` for the last main-chain turn; null if unavailable.
 * @param {Json} registry
 * @param {string | null | undefined} transcriptPath
 * @param {MainTurn | null} [turn]
 * @returns {[number, number, number] | null}
 */
function _contextFillMetrics(registry, transcriptPath, turn = null) {
  const [modelId, usage] = turn !== null && turn !== undefined ? turn : lastMainTurn(transcriptPath);
  const filled = contextFill(usage);
  if (filled === null) {
    return null;
  }
  const recommended = recommendedMaxContext(registry, modelId);
  if (recommended <= 0) {
    return null;
  }
  return [filled, recommended, filled / recommended];
}

/**
 * Fill as a share of the recommended maximum for the last main-chain turn (can pass 1.0); null
 * if unavailable. Reused by the C29 output-weight nudge.
 * @param {Json} registry
 * @param {string | null | undefined} transcriptPath
 * @returns {number | null}
 */
export function contextFillRatio(registry, transcriptPath) {
  const metrics = _contextFillMetrics(registry, transcriptPath);
  return metrics ? metrics[2] : null;
}

/**
 * One reminder line when the context fill reached a *new* pressure level; `[]` otherwise.
 *
 * Two levels of the recommended budget (design §12.2): **info** at `info_ratio` and **warn**
 * at the budget itself, 1.0. Throttled by a per-session temp-dir marker recording the last
 * announced level, so only a rise speaks; a fill below the lowest level ends the pressure
 * episode and clears the marker. Missing/malformed usage → silent; never raises past I/O.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {string | null | undefined} transcriptPath
 * @param {Json} sessionId
 * @param {{markerDir?: string | null, turn?: MainTurn | null}} [options]
 * @returns {string[]}
 */
export function contextPressureNotice(
  data,
  registry,
  transcriptPath,
  sessionId,
  { markerDir = null, turn = null } = {},
) {
  const policy = _get(registry, "context_pressure", {});
  // Only a share strictly between 0 and 1 is a level below the budget; anything else (absent,
  // a bool, 0, 1 or more, a string) leaves the budget's own warning alone.
  const rawInfo = _get(policy, "info_ratio");
  let infoRatio = typeof rawInfo === "boolean" ? null : _numeric(rawInfo);
  if (infoRatio !== null && !(infoRatio > 0 && infoRatio < 1)) {
    infoRatio = null;
  }
  const metrics = _contextFillMetrics(registry, transcriptPath, turn);
  if (metrics === null) {
    return [];
  }
  const [, recommended, ratio] = metrics;
  /** @type {number | null} */ let level = null; // 0 = info, 1 = warn — the value the marker records
  if (ratio >= 1.0) {
    level = 1;
  } else if (infoRatio !== null && ratio >= infoRatio) {
    level = 0;
  }

  const marker = _path(markerDir ?? gettempdir(), `akmon-context-pressure-${_pyStr(_or(sessionId, "nosession"))}`);
  /** @type {number | null} */ let lastLevel;
  try {
    lastLevel = _pyInt(_readText(marker));
  } catch (error) {
    // Python catches OSError and ValueError (a decode failure is one); a NUL in the path is a
    // ValueError there and an argument error here.
    const name = /** @type {Error} */ (error).name;
    if (!_isOSError(error) && !["ValueError", "UnicodeDecodeError", "TypeError"].includes(name)) {
      throw error;
    }
    lastLevel = null;
  }

  if (level === null) {
    // Below every level — the pressure episode is over and the throttle resets. The cause is
    // not visible here: a compact, a fresh session and anything else that lowered the fill
    // look alike.
    try {
      _unlinkMissingOk(marker);
    } catch (error) {
      if (!_isOSError(error)) {
        throw error;
      }
    }
    return [];
  }
  if (lastLevel !== null && level <= lastLevel) {
    return [];
  }
  try {
    _writeText(marker, String(level));
  } catch (error) {
    if (!_isOSError(error)) {
      throw error;
    }
  }

  const shown = recommended % 1000 === 0 ? `${Math.floor(recommended / 1000)}k` : String(recommended);
  const share = `~${_percent(ratio)} of the recommended ${shown} budget`;
  // A reminder to the owner and nothing more: the share and the command to type. The marks are
  // the hook's own: ⚠ for a warning, as the corridor's, ℹ for information.
  const pressure = data.context_pressure;
  if (level === 1) {
    return [fill(pressure.warn, { share })];
  }
  return [fill(pressure.info, { share })];
}

/**
 * Every generated routing artifact as `project-root-relative path → content`.
 *
 * The generated `k_*` subagent definitions plus the local config — the single set the init
 * tool and the SessionStart/UserPromptSubmit hook both write, so a rebind from either path
 * produces byte-identical files.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Binding} binding
 * @param {{secondOpinion: boolean, available: Json, session?: Json}} options
 * @returns {Record<string, string>}
 */
export function bindingArtifacts(data, registry, binding, { secondOpinion, available, session = null }) {
  const files = { ...generatedAgentFiles(data, registry, binding) };
  const config = localConfig(data, binding, registry, { secondOpinion, available, session });
  files[localConfigRel(data)] = wiringForm(config);
  return files;
}

/**
 * Generated subagent definitions on disk that the current `agentSpecs()` no longer plan.
 *
 * Only files carrying one of `generatedBanners()` are candidates, so a hand-written agent living in
 * the same directory is never a deletion target. Without this, renaming an agent leaves its
 * old definition behind as a live duplicate (ADR 0011).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} root
 * @param {Iterable<string>} plannedPaths
 * @returns {string[]}
 */
export function obsoleteAgentFiles(data, root, plannedPaths) {
  const agentsDir = _path(root, agentsDirRel(data));
  if (!_isDir(agentsDir)) {
    return [];
  }
  const planned = new Set([...plannedPaths].map((path) => _path(path)));
  let names;
  try {
    names = fs.readdirSync(agentsDir);
  } catch (error) {
    // `Path.glob` yields nothing from a directory it cannot list.
    if (!_isOSError(error)) {
      throw error;
    }
    return [];
  }
  /** @type {string[]} */ const obsolete = [];
  for (const name of codePointSort(names.filter((entry) => entry.endsWith(".md")))) {
    const path = _path(agentsDir, name);
    if (planned.has(path)) {
      continue;
    }
    let text;
    try {
      text = _readText(path);
    } catch (error) {
      if (_isOSError(error)) {
        continue;
      }
      throw error;
    }
    if (generatedBanners(data).some((banner) => text.includes(banner))) {
      obsolete.push(path);
    }
  }
  return obsolete;
}

/**
 * Delete the generated agent definitions no longer planned; return their paths.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} root
 * @param {Iterable<string>} plannedPaths
 * @param {{write?: boolean}} [options]
 * @returns {string[]}
 */
export function removeObsoleteAgents(data, root, plannedPaths, { write = true } = {}) {
  const removed = obsoleteAgentFiles(data, root, plannedPaths);
  if (write) {
    for (const path of removed) {
      _unlinkMissingOk(path);
    }
  }
  return removed;
}

/**
 * Write each artifact whose content changed; return the changed paths (idempotent).
 * @param {string} root
 * @param {Record<string, string>} files
 * @param {{write?: boolean}} [options]
 * @returns {string[]}
 */
export function writeArtifacts(root, files, { write = true } = {}) {
  /** @type {string[]} */ const changed = [];
  for (const [rel, content] of Object.entries(files)) {
    const path = _path(root, rel);
    const current = _isFile(path) ? _readText(path) : null;
    if (current === content) {
      continue;
    }
    changed.push(path);
    if (write) {
      fs.mkdirSync(posix.dirname(path), { recursive: true });
      _writeText(path, content);
    }
  }
  return changed;
}

/**
 * Recompute the binding for `orchestrator` and (re)write the artifacts under `root`.
 *
 * Reuses the recorded `available` list, opt-ins and `session` stanza from `config` — only the
 * orchestrator moves. Idempotent: unchanged files are left untouched. This is how the hook makes subagent
 * models follow the session's actual orchestrating model.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} root
 * @param {Json} registry
 * @param {Json} config
 * @param {Json} orchestrator
 * @param {{write?: boolean}} [options]
 * @returns {[Binding, string[]]}
 */
export function rebindTo(data, root, registry, config, orchestrator, { write = true } = {}) {
  const available = _get(config, "available");
  const secondOpinion = _truthy(_get(config, "second_opinion"));
  const vendor = _pyStr(_or(_get(config, "vendor"), "anthropic"));
  const auditorOptIn = _or(_get(config, "auditor_opt_in"), null);
  const binding = computeBinding(data, registry, orchestrator, available, vendor, auditorOptIn);
  const files = bindingArtifacts(data, registry, binding, {
    secondOpinion,
    available,
    session: _get(config, "session"),
  });
  const changed = writeArtifacts(root, files, { write });
  removeObsoleteAgents(
    data,
    root,
    Object.keys(files).map((rel) => _path(root, rel)),
    { write },
  );
  return [binding, changed];
}

/**
 * The per-user resolved config written to `localConfigRel()` (binding, opt-ins, staleness hash).
 *
 * `available` records the ladder the binding resolved (`selectionLadder`) — none in the semantic
 * case — so the runtime readers need no `--available` of their own. `session` is the optional
 * `{provider, model, family?}` stanza naming the harness the session runs on when it is not the
 * bound vendor's own (ADR-0024); it is written only when given, so a project that never states one
 * derives its session from the vendor as before.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Binding} binding
 * @param {Json} registry
 * @param {{secondOpinion: boolean, available: Json, session?: Json}} options
 * @returns {Record<string, Json>}
 */
export function localConfig(data, binding, registry, { secondOpinion, available, session = null }) {
  const [rungs, semantic] = selectionLadder(registry, binding.vendor, available);
  /** @type {Record<string, Json>} */
  const config = {
    vendor: binding.vendor,
    orchestrator: binding.orchestrator,
    binding: {
      reasoner: binding.reasoner,
      worker: binding.worker,
      mid: binding.mid,
      auditor: binding.auditor,
      escalation: [...binding.escalation],
    },
    second_opinion: secondOpinion,
    available: semantic ? null : rungs,
    auditor_opt_in: binding.auditorOptIn,
    registry_hash: registryHash(registry),
    task_kind_floors: taskKindFloors(registry, semantic ? [] : rungs, binding.vendor),
  };
  if (_truthy(session)) {
    config.session = { ...session };
  }
  return config;
}

/**
 * Why the local config is stale — or null when it is fresh.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} registry
 * @param {Json} settingsModel
 * @returns {string | null}
 */
export function staleness(data, config, registry, settingsModel) {
  const texts = data.staleness;
  if (!_truthy(config)) {
    return texts.no_config;
  }
  if (!_pyEq(_get(config, "registry_hash"), registryHash(registry))) {
    return texts.registry_changed;
  }
  if (_truthy(settingsModel) && !_pyEq(settingsModel, _get(config, "orchestrator"))) {
    return fill(texts.model_mismatch, { model: _pyStr(settingsModel) });
  }
  return null;
}

/**
 * What the second-opinion gate will actually do, as one status field plus any warning.
 *
 * The head of the chain the runner would walk (`opinionHead`), with the on/off state. The status
 * shows the vendor the hook already resolved, so a config that predates the `vendor` key reads as
 * the hook reads it.
 * @param {AgentsData} data
 * @param {RuntimeData} runtimeData
 * @param {Json} registry
 * @param {Json} config
 * @param {string} orchestratorVendor
 * @returns {[string, string | null]}
 */
function _secondOpinionStatus(data, runtimeData, registry, config, orchestratorVendor) {
  const enabled = _truthy(_get(config, "second_opinion"));
  const [display, warning] = opinionHead(data, runtimeData, registry, {
    ...config,
    vendor: _or(_get(config, "vendor"), orchestratorVendor),
  });
  const state = enabled ? "on" : "off";
  return [`second-opinion=${display} (${state})`, enabled ? warning : null];
}

/** A task kind whose rung floor sits above the rung its routed agent is bound to (C32). */
export class FloorGap {
  /**
   * @param {string} kind
   * @param {string} agent
   * @param {Json} floor
   * @param {string} bound
   */
  constructor(kind, agent, floor, bound) {
    this.kind = kind;
    this.agent = agent;
    this.floor = floor;
    this.bound = bound;
    Object.freeze(this);
  }
}

/**
 * The position of `alias` on the ladder, or null for a non-string or an absent alias.
 * @param {Json[]} ladder
 * @param {Json} alias
 * @returns {number | null}
 */
function _rank(ladder, alias) {
  return typeof alias === "string" && _contains(ladder, alias) ? _index(ladder, alias) : null;
}

/**
 * Kinds whose recorded `task_kind_floors` entry exceeds their agent's bound model.
 *
 * The floors are resolved at init against the local ladder; the agent's model is the one
 * `boundModelFor` reports, so a semantic-fallback binding (no pin) yields no gap.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @returns {FloorGap[]}
 */
export function floorGaps(data, config) {
  const floors = _isDict(config) ? _get(config, "task_kind_floors") : null;
  const ladder = _isDict(config) ? _get(config, "available") : null;
  if (!_isDict(floors) || !Array.isArray(ladder)) {
    return [];
  }
  /** @type {FloorGap[]} */ const gaps = [];
  for (const spec of agentSpecs(data)) {
    const bound = boundModelFor(data, config, spec.name);
    const boundRank = _rank(ladder, bound);
    if (bound === null || boundRank === null) {
      continue;
    }
    for (const kind of spec.kinds) {
      const floor = Object.hasOwn(floors, kind) ? floors[kind] : null;
      const floorRank = _rank(ladder, floor);
      if (floorRank !== null && floorRank > boundRank) {
        gaps.push(new FloorGap(kind, spec.name, floor, bound));
      }
    }
  }
  return gaps;
}

/**
 * One context line per floor gap: which kind, which agent, and the override that meets it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @returns {string[]}
 */
export function floorGapLines(data, config) {
  const template = data.floor_gap_line;
  return floorGaps(data, config).map((gap) =>
    fill(template, { kind: gap.kind, floor: _pyStr(gap.floor), agent: gap.agent, bound: gap.bound }),
  );
}

/**
 * Per-call form of the floor check for the delegation log (C32).
 *
 * The call does not say which task kind it carries, so the warning is conditional on the
 * kind; an explicit `model` override at or above every gapped floor silences it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} subagentType
 * @param {Json} callModel
 * @returns {string | null}
 */
export function delegationFloorWarning(data, config, subagentType, callModel) {
  const openGaps = _openFloorGaps(data, config, subagentType, callModel);
  if (openGaps.length === 0) {
    return null;
  }
  const kinds = openGaps.map((gap) => `${gap.kind} (floor ${_pyStr(gap.floor)})`).join(", ");
  return fill(data.delegation_floor_warning, { subagent: _pyStr(subagentType), bound: openGaps[0].bound, kinds });
}

/**
 * The model-addressed form of `delegationFloorWarning`: from the next call on, the floor's model.
 *
 * Same predicate, same silence; the delegation log sends it as `additionalContext` beside the
 * owner's `systemMessage` (ADR 0006 item 4, M149).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} subagentType
 * @param {Json} callModel
 * @returns {string | null}
 */
export function delegationFloorDirective(data, config, subagentType, callModel) {
  const openGaps = _openFloorGaps(data, config, subagentType, callModel);
  if (openGaps.length === 0) {
    return null;
  }
  const texts = data.delegation_floor_directive;
  const overrides = openGaps
    .map((gap) => fill(texts.override, { kind: gap.kind, floor: _pyStr(gap.floor) }))
    .join("; ");
  return fill(texts.text, { subagent: _pyStr(subagentType), bound: openGaps[0].bound, overrides });
}

/**
 * The agent's floor gaps the call's `model` override leaves open (C32).
 * @param {AgentsData} data
 * @param {Json} config
 * @param {Json} subagentType
 * @param {Json} callModel
 */
function _openFloorGaps(data, config, subagentType, callModel) {
  const ladder = _isDict(config) ? _get(config, "available") : null;
  const gaps = floorGaps(data, config).filter((gap) => gap.agent === subagentType);
  if (gaps.length === 0 || !Array.isArray(ladder)) {
    return [];
  }
  const callRank = _rank(ladder, callModel);
  return gaps.filter((gap) => callRank === null || callRank < _index(ladder, gap.floor));
}

/**
 * The recorded escalation path, named only when the binding pins concrete aliases.
 * @param {Json} config
 * @returns {string}
 */
function _escalationHint(config) {
  const binding = _get(config, "binding", {});
  const path = _isDict(binding) ? _get(binding, "escalation") : null;
  const ladder = _get(config, "available");
  if (!Array.isArray(path) || path.length === 0 || !Array.isArray(ladder) || ladder.length === 0) {
    return "";
  }
  return ` (escalation path: ${path.map((rung) => _pyStr(rung)).join(" → ")})`;
}

/**
 * The steady-state status injection: one binding line + self-check, plus any warning.
 *
 * `initCommand` is how this project runs the routing initializer (`toolCommand`). It is passed
 * in because only the caller knows the project root.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {RuntimeData} runtimeData the parsed `common/runtime.json`
 * @param {Json} config
 * @param {Json} registry
 * @param {string} initCommand
 * @returns {string[]}
 */
export function statusLines(data, runtimeData, config, registry, initCommand) {
  const binding = _get(config, "binding", {});
  const orchestratorVendor = _pyStr(_or(_get(config, "vendor"), "anthropic"));
  const [secondDisplay, secondWarning] = _secondOpinionStatus(data, runtimeData, registry, config, orchestratorVendor);
  const orchestrator = _get(config, "orchestrator", "?");
  const texts = data.status_lines;
  const lines = [
    fill(texts.binding, {
      vendor: orchestratorVendor,
      orchestrator: _pyStr(orchestrator),
      reasoner: _pyStr(_get(binding, "reasoner", "?")),
      auditor: _pyStr(_get(binding, "auditor", "?")),
      worker: _pyStr(_get(binding, "worker", "?")),
      mid: _pyStr(_get(binding, "mid", "?")),
      second_opinion: secondDisplay,
    }),
    fill(texts.delegation, { escalation_hint: _escalationHint(config), zone_convention: zoneConvention(data) }),
    fill(texts.self_check, { orchestrator: _pyStr(orchestrator), init_command: initCommand }),
  ];
  const warning = computeBinding(
    data,
    registry,
    orchestrator,
    _get(config, "available"),
    orchestratorVendor,
    _or(_get(config, "auditor_opt_in"), null),
  ).warning;
  if (warning) {
    lines.push(`⚠ ${warning}`);
  }
  if (secondWarning) {
    lines.push(`⚠ ${secondWarning}`);
  }
  lines.push(...floorGapLines(data, config));
  return lines;
}

/**
 * The concise mid-session note after the orchestrator model changed (UserPromptSubmit).
 *
 * One line naming the new orchestrator and the recomputed subagent binding, plus the
 * weak-orchestrator warning when it applies.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Json} config
 * @param {Json} registry
 * @returns {string[]}
 */
export function rebindNotice(data, config, registry) {
  const binding = _get(config, "binding", {});
  const orchestrator = _get(config, "orchestrator", "?");
  const vendor = _pyStr(_or(_get(config, "vendor"), "anthropic"));
  const lines = [
    fill(data.rebind_notice, {
      orchestrator: _pyStr(orchestrator),
      reasoner: _pyStr(_get(binding, "reasoner", "?")),
      auditor: _pyStr(_get(binding, "auditor", "?")),
      worker: _pyStr(_get(binding, "worker", "?")),
      mid: _pyStr(_get(binding, "mid", "?")),
    }),
  ];
  const warning = computeBinding(
    data,
    registry,
    orchestrator,
    _get(config, "available"),
    vendor,
    _or(_get(config, "auditor_opt_in"), null),
  ).warning;
  if (warning) {
    lines.push(`⚠ ${warning}`);
  }
  lines.push(...floorGapLines(data, config));
  return lines;
}

/**
 * The one-time setup instruction. `initCommand`: see `statusLines`.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} reason
 * @param {string} initCommand
 * @returns {string[]}
 */
export function initInstruction(data, reason, initCommand) {
  const values = { reason, init_command: initCommand };
  return data.init_instruction.map((line) => fill(line, values));
}

// --------------------------------------------------------------------------------------
// Delegation log (the PreToolUse hook contract)
// --------------------------------------------------------------------------------------

const _SUBAGENT_TOOLS = new Set(["Task", "Agent"]);

// `re.ASCII | re.IGNORECASE | re.DOTALL`; the `i` flag without `u` folds only ASCII, as the
// Python's ASCII flag does.
const _ZONE_BRACKETED = /^\[[ \t\n\r\f\v]*zone[ \t\n\r\f\v]*:[ \t\n\r\f\v]*([^\]]*)\][ \t\n\r\f\v]*(.*)/is;
// Unbracketed only as one token (`zone:auth`): with a space after the colon, prose such as
// "zone: the auth module" would otherwise yield the label "the".
const _ZONE_BARE = /^zone:([^ \t\n\r\f\v]+)[ \t\n\r\f\v]*(.*)/is;
// A zone label (C33 review): a letter or digit first, then letters, digits, `-`, `_` or `.`.
// Python's Unicode `[^\W_][\w.-]*`: `\w` is `str.isalnum()` plus `_`, read here as the letter and
// number categories.
const _ZONE_LABEL = /^[\p{L}\p{N}][\p{L}\p{N}_.-]*$/u;

/**
 * The zone-label convention as the orchestrator reads it — on the generated fan-out agents
 * and in the status line's delegation guidance (C33).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @returns {string}
 */
export function zoneConvention(data) {
  return data.zone_convention;
}

// Column counts for `parseDelegationEntries`: the current schema (timestamp, session_id,
// subagent, model, zone, description) and the legacy one (timestamp, subagent, model,
// description — no session/zone).
const _CURRENT_SCHEMA_COLUMNS = 6;
const _LEGACY_SCHEMA_COLUMNS = 4;

/**
 * Split a leading `[zone:LABEL]` marker off a delegation description.
 *
 * A marker only counts at the very start: `[zone:auth] check tokens` -> `["auth", "check
 * tokens"]`; tolerated alike (C33): any case, spaces inside the brackets, and the bare
 * one-token `zone:auth check tokens`. No marker -> `[null, <description stripped>]`. A marker
 * whose label is not a label — empty, or breaking `_ZONE_LABEL` (`[zone:-]`, `zone:[auth]`,
 * `zone:auth]x`) — is still taken off the description but yields no label. The label keeps its
 * case as written; the coverage map matches it case-insensitively.
 * @param {string} description
 * @returns {[string | null, string]}
 */
export function parseZone(description) {
  const text = _strip(description);
  const bracketed = _ZONE_BRACKETED.exec(text);
  if (bracketed) {
    return [_zoneLabel(_strip(bracketed[1])), _strip(bracketed[2])];
  }
  const bare = _ZONE_BARE.exec(text);
  if (bare) {
    // C33: the unbracketed `zone:X …` spelling was observed live and used to leave the
    // whole fan-out unlabelled — an all-uncovered coverage map.
    return [_zoneLabel(_rstripChars(bare[1], ",;:")), _strip(bare[2])];
  }
  return [null, text];
}

/**
 * `candidate` when it is a well-formed zone label, else null.
 * @param {string} candidate
 * @returns {string | null}
 */
function _zoneLabel(candidate) {
  return _ZONE_LABEL.test(candidate) ? candidate : null;
}

/**
 * Warn on an unlabelled fan-out delegation in a session that is running a zone plan (C33).
 *
 * The observable sign that a zone plan is active is that earlier delegations of this session
 * carried zone labels. The auditor is exempt: an audit reads the fan-out, it is not a zone of it.
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Iterable<DelegationEntry>} entries
 * @param {string | null} sessionId
 * @param {string} subagent
 * @param {string | null} zone
 * @returns {string | null}
 */
export function unlabelledFanoutWarning(data, entries, sessionId, subagent, zone) {
  const labelled = _zonedLabels(data, entries, sessionId, subagent, zone);
  if (labelled.length === 0) {
    return null;
  }
  return fill(data.unlabelled_fanout_warning, { subagent, labelled: labelled.join(", ") });
}

/**
 * The model-addressed form of `unlabelledFanoutWarning`: label the fan-out calls.
 *
 * Same predicate, same silence; the delegation log sends it as `additionalContext` beside the
 * owner's `systemMessage` (ADR 0006 item 4, M149).
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {Iterable<DelegationEntry>} entries
 * @param {string | null} sessionId
 * @param {string} subagent
 * @param {string | null} zone
 * @returns {string | null}
 */
export function unlabelledFanoutDirective(data, entries, sessionId, subagent, zone) {
  const labelled = _zonedLabels(data, entries, sessionId, subagent, zone);
  if (labelled.length === 0) {
    return null;
  }
  return fill(data.unlabelled_fanout_directive, { subagent, labelled: labelled.join(", ") });
}

/**
 * The session's earlier zone labels when this call should carry one too, else `[]` (C33).
 * @param {AgentsData} data
 * @param {Iterable<DelegationEntry>} entries
 * @param {string | null} sessionId
 * @param {string} subagent
 * @param {string | null} zone
 * @returns {string[]}
 */
function _zonedLabels(data, entries, sessionId, subagent, zone) {
  if (zone || !sessionId || !_agentByName(data).has(subagent) || subagent === "k_auditor") {
    return [];
  }
  /** @type {Set<string>} */ const zones = new Set();
  for (const entry of entries) {
    if (entry.sessionId === sessionId && entry.zone) {
      zones.add(entry.zone);
    }
  }
  return codePointSort([...zones]);
}

/**
 * One TSV line per subagent delegation; null for any other tool.
 *
 * Columns: `timestamp · session_id · subagent · model · zone · description`. The zone is
 * parsed off a leading `[zone:LABEL]` marker in the description (removed from the stored
 * description); `-` marks an absent session / model / zone. The model is the call's explicit
 * override if given, else `boundModel`. `sessionId` scopes a fan-out round for the
 * coverage-map assembler (C17).
 * @param {Json} toolName
 * @param {Json} toolInput
 * @param {string} timestamp
 * @param {Json} [sessionId]
 * @param {Json} [boundModel]
 * @returns {string | null}
 */
export function delegationLogLine(toolName, toolInput, timestamp, sessionId = null, boundModel = null) {
  if (toolName !== null && typeof toolName === "object" && !(toolName instanceof FloatValue)) {
    throw _pyError("TypeError", `unhashable type: '${_pyTypeName(toolName)}'`);
  }
  if (typeof toolName !== "string" || !_SUBAGENT_TOOLS.has(toolName)) {
    return null;
  }
  const subagent = _pyStr(_or(_get(toolInput, "subagent_type"), "-"));
  const model = _pyStr(_or(_or(_get(toolInput, "model"), boundModel), "-"));
  const rawDescription = _split(_pyStr(_or(_get(toolInput, "description"), ""))).join(" ");
  const [zone, description] = parseZone(rawDescription);
  return `${_pyStr(timestamp)}\t${_pyStr(_or(sessionId, "-"))}\t${subagent}\t${model}\t${zone || "-"}\t${description}`;
}

/** One parsed delegation-log row (schema: see `delegationLogLine`). */
export class DelegationEntry {
  /**
   * @param {string} timestamp
   * @param {string | null} sessionId
   * @param {string} subagent
   * @param {string | null} model
   * @param {string | null} zone
   * @param {string} description
   */
  constructor(timestamp, sessionId, subagent, model, zone, description) {
    this.timestamp = timestamp;
    this.sessionId = sessionId;
    this.subagent = subagent;
    this.model = model;
    this.zone = zone;
    this.description = description;
    Object.freeze(this);
  }
}

/** A stripped column, or null for an absent (`""`/`-`) one. */
function _dashToNone(/** @type {string} */ value) {
  const stripped = _strip(value);
  return stripped === "" || stripped === "-" ? null : stripped;
}

/**
 * Parse delegation-log lines into entries.
 *
 * Handles the current 6-column schema and the legacy 4-column one (no session/zone) so
 * a mixed local log still parses; lines with fewer than 4 fields are skipped.
 * @param {Iterable<string>} lines
 * @returns {DelegationEntry[]}
 */
export function parseDelegationEntries(lines) {
  /** @type {DelegationEntry[]} */ const entries = [];
  for (const raw of lines) {
    const line = _rstripChars(raw, "\n");
    if (!line) {
      continue;
    }
    const parts = line.split("\t");
    let ts;
    let sid;
    let subagent;
    let model;
    let zone;
    let description;
    if (parts.length >= _CURRENT_SCHEMA_COLUMNS) {
      [ts, sid, subagent, model, zone] = parts;
      description = parts.slice(5).join("\t");
    } else if (parts.length >= _LEGACY_SCHEMA_COLUMNS) {
      // Legacy: timestamp · subagent · model · description (no session / zone).
      [ts, sid, subagent, model, zone] = [parts[0], "-", parts[1], parts[2], "-"];
      description = parts.slice(3).join("\t");
    } else {
      continue;
    }
    entries.push(
      new DelegationEntry(
        ts,
        _dashToNone(sid),
        _strip(subagent),
        _dashToNone(model),
        _dashToNone(zone),
        _strip(description),
      ),
    );
  }
  return entries;
}

// --------------------------------------------------------------------------------------
// C25 — the missed-gate forcing function: count a role's findings/options at the gate
// --------------------------------------------------------------------------------------

/**
 * The project's recorded binding, or `{}` when it is absent or unreadable.
 *
 * The hooks that need the live binding all read the same file the same way; the one
 * tolerated failure is a missing or malformed config, which means "not set up yet".
 * @param {AgentsData} data the parsed `tools/model_routing/agents.json`
 * @param {string} projectRoot
 * @returns {Record<string, Json>}
 */
export function readLocalConfig(data, projectRoot) {
  const path = _path(projectRoot, localConfigRel(data));
  if (!_isFile(path)) {
    return {};
  }
  let loaded;
  try {
    loaded = _parseKeepingFloats(_readText(path));
  } catch (error) {
    if (_isOSError(error) || error instanceof SyntaxError) {
      return {};
    }
    throw error;
  }
  return _isDict(loaded) ? loaded : {};
}

/** One role's count floor: which registry trigger it reads and what it counts. */
export class GateRule {
  /**
   * @param {string} role
   * @param {string} trigger
   * @param {string} noun
   * @param {string[]} headings section headings that open the counted material, lowercased prefixes
   * @param {string} anchor where the flow puts this gate, for the reason the hook hands back
   */
  constructor(role, trigger, noun, headings, anchor) {
    this.role = role;
    this.trigger = trigger;
    this.noun = noun;
    this.headings = Object.freeze([...headings]);
    this.anchor = anchor;
    Object.freeze(this);
  }
}

/**
 * The two floors `gate_triggers` carries. A role outside this list has no count gate.
 * @param {GateData} data the parsed `tools/model_routing/gate.json`
 * @returns {GateRule[]}
 */
export function gateRules(data) {
  return data.gate_rules.map((raw) => new GateRule(raw.role, raw.trigger, raw.noun, raw.headings, raw.anchor));
}

// A markdown heading (`## Findings`) or a whole line in bold (`**Findings**`) — both are how
// a role's output actually labels its sections; a bold line counts as the deepest level, so
// the next heading of any level closes it. Every pattern but the word one is `re.ASCII`.
const _MD_HEADING_RE = /^(#{1,6})[ \t\n\r\f\v]+(.*[^ \t\n\r\f\v])[ \t\n\r\f\v]*$/;
const _BOLD_HEADING_RE = /^\*\*(.+?)\*\*:?[ \t\n\r\f\v]*$/;
// A heading's words, letters only — Python's Unicode `[^\W\d_]`: letters and the non-decimal
// numbers (C98: a non-latin script yields its words like any other).
const _HEADING_WORD_RE = /[\p{L}\p{Nl}\p{No}]+/gu;
// A structural item: a bullet or a numbered item, at whatever depth it sits.
const _LIST_ITEM_RE = /^([ \t\n\r\f\v]*)(?:[-*+]|[0-9]+[.)])[ \t\n\r\f\v]+[^ \t\n\r\f\v]/;
// A table row that carries content — not the header separator `|---|---|`.
const _TABLE_SEPARATOR_RE = /^[ \t\n\r\f\v]*\|[ \t\n\r\f\v:|-]+\|[ \t\n\r\f\v]*$/;
const _GATE_MARKER_PREFIX = "gate-audit";

/**
 * `[level, text]` when `line` opens a section, else null. A bold line is level 7.
 * @param {string} line
 * @returns {[number, string] | null}
 */
function _heading(line) {
  const match = _MD_HEADING_RE.exec(line);
  if (match) {
    return [match[1].length, match[2]];
  }
  const bold = _BOLD_HEADING_RE.exec(line);
  return bold ? [7, bold[1]] : null;
}

/**
 * Whether a heading's text names the counted material (`Findings`, `3 findings`, `Options`).
 * @param {string} text
 * @param {readonly string[]} headings
 * @returns {boolean}
 */
function _opensSection(text, headings) {
  const words = text.toLowerCase().match(_HEADING_WORD_RE) ?? [];
  return words.slice(0, 3).some((word) => headings.some((heading) => word.startsWith(heading)));
}

/**
 * `[section ordinal, line]` for every body line under a `rule` section of `message`.
 *
 * A section opens at a heading that names the counted material and closes at the next heading
 * of the same or a higher level; a deeper heading inside it is neither yielded nor a closer.
 * The ordinal tells a caller where one section's body ends and the next one's begins.
 * @param {string} message
 * @param {GateRule} rule
 * @returns {Array<[number, string]>}
 */
function _gateSectionLines(message, rule) {
  /** @type {Array<[number, string]>} */ const lines = [];
  /** @type {number | null} */ let level = null;
  let ordinal = 0;
  for (const line of _splitlines(message)) {
    const heading = _heading(line);
    if (heading !== null) {
      const [opened, text] = heading;
      if (level !== null && opened <= level) {
        level = null;
      }
      if (level === null && _opensSection(text, rule.headings)) {
        [level, ordinal] = [opened, ordinal + 1];
      }
      continue;
    }
    if (level !== null) {
      lines.push([ordinal, line]);
    }
  }
  return lines;
}

/**
 * Structural items under every `rule` section of `message` (C25's counting rule).
 *
 * Counted: the section's outermost bullets and numbered items, and table rows with content.
 * An item indented deeper than the section's first one belongs to that item and is detail, a
 * table's header and separator are not rows, and prose is not an item. Sections close at the
 * next heading of the same or a higher level. The base indent is per section.
 * @param {string} message
 * @param {GateRule} rule
 * @returns {number}
 */
export function countGateItems(message, rule) {
  let total = 0;
  let section = 0;
  let inTable = false;
  /** @type {number | null} */ let base = null;
  for (const [ordinal, line] of _gateSectionLines(message, rule)) {
    if (ordinal !== section) {
      [section, inTable, base] = [ordinal, false, null];
    }
    if (_lstrip(line).startsWith("|")) {
      if (_TABLE_SEPARATOR_RE.test(line)) {
        inTable = true; // the row above it was the header, not an item
        continue;
      }
      total += inTable ? 1 : 0;
      continue;
    }
    inTable = false;
    const item = _LIST_ITEM_RE.exec(line);
    if (item === null) {
      continue;
    }
    const indent = item[1].length;
    base = base === null ? indent : Math.min(base, indent);
    if (indent <= base) {
      total += 1;
    }
  }
  return total;
}

/**
 * The body of every `rule` section of `message`, one line each — the material a gate counts.
 *
 * The headings are left out (a renamed heading over the same items is the same gate), and so are
 * blank lines and every line outside the sections (the summary around them moves from turn to
 * turn).
 * @param {string} message
 * @param {GateRule} rule
 * @returns {string}
 */
export function gateSectionText(message, rule) {
  return _gateSectionLines(message, rule)
    .map(([, line]) => line)
    .filter((line) => _strip(line) !== "")
    .join("\n");
}

/**
 * `rule`'s count floor from the registry, or null when it is absent or not a count.
 * @param {Json} registry
 * @param {GateRule} rule
 * @returns {number | null}
 */
export function gateThreshold(registry, rule) {
  const triggers = _isDict(registry) ? _get(registry, "gate_triggers") : null;
  const value = _isDict(triggers) ? _get(triggers, rule.trigger) : null;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

/**
 * The count gate for a declared role, or null for a role that has none.
 * @param {GateData} data the parsed `tools/model_routing/gate.json`
 * @param {string | null} role
 * @returns {GateRule | null}
 */
export function gateRuleFor(data, role) {
  return gateRules(data).find((rule) => rule.role === role) ?? null;
}

/**
 * The one thing the gate asks for when a role's count reached its floor, else null.
 *
 * The floor is advisory in the flows — the orchestrator may skip it — so the request names
 * both live moves: run the audit, or say the skip out loud. What it does not allow is the
 * gate passing unmentioned, which is the whole of C25. `gatePackCommand` is how this project
 * runs the gate-pack tool (`toolCommand`).
 * @param {GateData} gateData the parsed `tools/model_routing/gate.json`
 * @param {AgentsData} agentsData the parsed `tools/model_routing/agents.json`
 * @param {Json} registry
 * @param {Json} config
 * @param {string | null} role
 * @param {string} message
 * @param {string} gatePackCommand
 * @returns {string | null}
 */
export function gateAuditRequest(gateData, agentsData, registry, config, role, message, gatePackCommand) {
  const rule = gateRuleFor(gateData, role);
  const threshold = rule !== null ? gateThreshold(registry, rule) : null;
  if (rule === null || threshold === null) {
    return null;
  }
  const count = countGateItems(message, rule);
  if (count < threshold) {
    return null;
  }
  const auditor = boundModelFor(agentsData, config, "k_auditor");
  const model = auditor ? ` (model=${auditor})` : "";
  return (
    `[akmon gate] This turn carries ${count} ${rule.noun} as the ${rule.role} role, at or above the ` +
    `\`${rule.trigger}\` floor of ${threshold} — ${rule.anchor} routes an \`audit\` pass here. ` +
    `Before handing off: either delegate \`k_auditor\`${model} over the gate-pack ` +
    `(\`${gatePackCommand}\`) and fold its verdict in, or state in one line that you ` +
    "are skipping the audit and why. The floor is advisory; passing it in silence is not."
  );
}

/**
 * The marker kind for one gate episode: the role and a digest of the counted material.
 *
 * Keyed by content, not count (C25 review): two different gates with the same count are two
 * gates, and the same material is one gate however the count moved in between.
 * @param {string} message
 * @param {GateRule} rule
 * @returns {string}
 */
export function gateAuditMarkerKind(message, rule) {
  const material = gateSectionText(message, rule);
  _utf8(material); // refuses a lone surrogate, as str.encode() does
  return `${_GATE_MARKER_PREFIX}-${rule.role}-${sha256Hex(material).slice(0, 16)}`;
}

/**
 * Claim this gate episode for `sessionId`; false when it was already asked for.
 *
 * Keyed by role and the counted material (C36 markers): the same Findings/Options never block
 * twice in a session, while different material — even with the same count — is a new gate and
 * is asked about again. Markers are not released on a new gate, so returning to material
 * already held (3 → 4 → 3) does not hold it a second time; they age out with the C36 throttle.
 * @param {GateData} gateData the parsed `tools/model_routing/gate.json`
 * @param {MarkersData} markersData the parsed `common/markers.json`
 * @param {string | null} role
 * @param {string} message
 * @param {string | null | undefined} sessionId
 * @param {{markerDir?: string | null}} [options]
 * @returns {boolean}
 */
export function gateAuditOnce(gateData, markersData, role, message, sessionId, { markerDir = null } = {}) {
  const rule = gateRuleFor(gateData, role);
  if (rule === null) {
    return false;
  }
  return claimDiagnosticMarker(markersData, gateAuditMarkerKind(message, rule), sessionId, { directory: markerDir });
}
