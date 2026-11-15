#!/usr/bin/env node
/**
 * Session-statistics digest (design: `docs/design/model-routing.md` §4.4, task C13) — the
 * JavaScript twin of `tools/model_routing/stats.py` (C108, ADR 0020 D01). The Python module is the
 * spec: the same report file bytes, the same stdout lines, the same exit code.
 *
 * Parses the delegation log, the session transcript(s), and (optionally) the Claude API usage
 * endpoint to produce an on-demand digest of a session's routing activity: how much was
 * delegated, where the tokens went, how much budget remains, and (task A49) what share of the
 * project's sessions needed code at all.
 *
 * Pure aggregation lives in plain functions that take already-read data (lines, objects); I/O —
 * filesystem walks, reading files, the HTTP call — sits in thin wrappers around them, so the
 * aggregation logic is testable without a real home directory or network access. Never fails for
 * a missing/unavailable data source: each section of the digest degrades to an explanatory line
 * instead, and the tool always exits 0.
 *
 * Data (the C102 convention): `main` reads `tools/model_routing/stats.json` and `agents.json`
 * once and passes them down.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `stats.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with every
 *   error, names the program `stats.py`, and abbreviates long options), `-h`/`--help` prints a
 *   short usage and exits 0;
 * - the budget call is the global `fetch` with a 10 s `AbortSignal.timeout`, so `main` is async
 *   (`akmon tool` awaits it); the text of an `unavailable` reason for a network failure or a
 *   timeout is Node's (`TypeError: fetch failed`, `TimeoutError: …`), where `urllib` words
 *   `URLError: <urlopen error …>`; an HTTP error is `HTTPError: HTTP Error 401: Unauthorized` in
 *   both;
 * - a JSON number is a plain JS number (`pyjson`), so a token count written `1.0` reads as the
 *   integer `1` here and as the float it is (counted `0`) in Python.
 */

import fs from "node:fs";
import os from "node:os";
import { basename, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import { JSONDecodeError, jsonLoads } from "../../common/pyjson.mjs";
import { resolvePath } from "../../common/project_root.mjs";
import {
  decodeUtf8,
  dictGet,
  exceptionClassName,
  floatRepr,
  isDict,
  isDir,
  isFile,
  pyIterate,
  pyLower,
  pyPath,
  pySplitlines,
  pyStr,
  pyStrip,
  readText,
  truthy,
} from "../../common/pyvalue.mjs";
import { createReport, reportPrefix, taskError } from "../../common/report_path.mjs";
import { codePointCompare } from "../../common/sort.mjs";
import { mungedProjectDir, newestJsonl, pyStem, pySuffix, transcriptsDir } from "../../common/transcripts.mjs";
import { agentSpecs, delegationLogRel, parseDelegationEntries } from "./routing.mjs";

// The three transcript-location helpers moved to `common/transcripts.mjs` (C177); they stay part of
// this module's public surface (tools/README.md), so the one copy is re-exported, not duplicated.
export { mungedProjectDir, newestJsonl, transcriptsDir };

/** @typedef {import("./routing.mjs").AgentsData} AgentsData */
/** @typedef {import("../../common/pyvalue.mjs").Json} Json */

/**
 * The `code_touch` block of `stats.json`.
 * @typedef {object} CodeTouchData
 * @property {string[]} code_extensions
 * @property {string[]} edit_tools
 * @property {string[]} read_tools
 * @property {string[]} shell_tools
 * @property {string[]} path_fields
 * @property {string[]} test_command_patterns
 * @property {string} system_reminder_prefix
 * @property {string} group_main
 * @property {string} group_subagents
 */

/**
 * The keys of `tools/model_routing/stats.json`.
 * @typedef {object} StatsData
 * @property {string} usage_url the usage endpoint the budget summary fetches
 * @property {string} credentials_rel the OAuth credentials file (home-relative)
 * @property {string} report_dir_rel the full-report output directory (project-root-relative)
 * @property {{session: string, week_all_models: string, week_scoped: string}} budget_labels
 * @property {CodeTouchData} code_touch what counts as touching code, and the group names
 * @property {Record<string, string>} digest the compact stdout digest texts
 * @property {Record<string, any>} report the full-report texts (strings and string lists)
 */

/** The tree the running module belongs to (it holds `tools/model_routing/`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "stats.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--transcript TRANSCRIPT]
                [--no-budget] [--report-dir REPORT_DIR] [--task TASK]

Session-statistics digest: delegations, per-role tokens and remaining budget.

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root (default: cwd).
  --transcript TRANSCRIPT
                        Override the main session transcript path.
  --no-budget           Skip the Claude API budget call.
  --report-dir REPORT_DIR
                        Override the report output directory.
  --task TASK           Task id the report belongs to; the report is <report-dir>/[<task>-]stats-<n>.md, n the next ordinal.
`;

// --------------------------------------------------------------------------------------
// Token usage — shared shape across the orchestrator and every subagent
// --------------------------------------------------------------------------------------

/** Token usage for one turn or one aggregate — the shape shared across every role. */
export class TokenUsage {
  /**
   * @param {number} [inputTokens]
   * @param {number} [outputTokens]
   * @param {number} [cacheReadTokens]
   * @param {number} [cacheCreationTokens]
   */
  constructor(inputTokens = 0, outputTokens = 0, cacheReadTokens = 0, cacheCreationTokens = 0) {
    this.inputTokens = inputTokens;
    this.outputTokens = outputTokens;
    this.cacheReadTokens = cacheReadTokens;
    this.cacheCreationTokens = cacheCreationTokens;
    Object.freeze(this);
  }

  /**
   * Elementwise sum with `other`.
   * @param {TokenUsage} other
   * @returns {TokenUsage}
   */
  add(other) {
    return new TokenUsage(
      this.inputTokens + other.inputTokens,
      this.outputTokens + other.outputTokens,
      this.cacheReadTokens + other.cacheReadTokens,
      this.cacheCreationTokens + other.cacheCreationTokens,
    );
  }
}

/**
 * Extract a `TokenUsage` from an assistant record's `message`; null when absent.
 * @param {Json} message
 * @returns {TokenUsage | null}
 */
export function usageFromMessage(message) {
  const usage = dictGet(message, "usage");
  if (!isDict(usage)) {
    return null;
  }
  const count = (/** @type {string} */ key) => {
    const value = dictGet(usage, key, 0);
    // Python's `isinstance(value, int)`: a bool is an int, a float is not.
    if (typeof value === "boolean") {
      return value ? 1 : 0;
    }
    return typeof value === "number" && Number.isInteger(value) ? value : 0;
  };
  return new TokenUsage(
    count("input_tokens"),
    count("output_tokens"),
    count("cache_read_input_tokens"),
    count("cache_creation_input_tokens"),
  );
}

/**
 * @param {Iterable<TokenUsage>} usages
 * @returns {TokenUsage}
 */
function _sumUsage(usages) {
  let total = new TokenUsage();
  for (const usage of usages) {
    total = total.add(usage);
  }
  return total;
}

// --------------------------------------------------------------------------------------
// Delegation log — `.claude/model-routing.log`
// --------------------------------------------------------------------------------------

/** Aggregated delegation-log counts: total, and per (subagent, model) pair. */
export class DelegationStats {
  constructor() {
    this.total = 0;
    /** @type {Map<string, {subagent: string, model: string, count: number}>} keyed by the JSON pair */
    this.perPair = new Map();
  }

  /**
   * Count one delegation.
   * @param {string} subagent
   * @param {string} model
   */
  count(subagent, model) {
    this.total += 1;
    const key = JSON.stringify([subagent, model]);
    const slot = this.perPair.get(key);
    if (slot === undefined) {
      this.perPair.set(key, { subagent, model, count: 1 });
    } else {
      slot.count += 1;
    }
  }

  /**
   * Delegation counts collapsed to subagent, ignoring model.
   * @returns {Map<string, number>}
   */
  get perSubagent() {
    /** @type {Map<string, number>} */ const counts = new Map();
    for (const { subagent, count } of this.perPair.values()) {
      counts.set(subagent, (counts.get(subagent) ?? 0) + count);
    }
    return counts;
  }

  /**
   * Delegation counts collapsed to model, ignoring subagent.
   * @returns {Map<string, number>}
   */
  get perModel() {
    /** @type {Map<string, number>} */ const counts = new Map();
    for (const { model, count } of this.perPair.values()) {
      counts.set(model, (counts.get(model) ?? 0) + count);
    }
    return counts;
  }
}

/**
 * Aggregate delegation-log lines, counting exactly the rows `parseDelegationEntries` yields.
 *
 * The current 6-field schema and the legacy 4-field one; a shorter line is skipped. An absent
 * model counts as `-`, as the log writes it.
 * @param {Iterable<string>} lines
 * @returns {DelegationStats}
 */
export function aggregateDelegationLines(lines) {
  const stats = new DelegationStats();
  for (const entry of parseDelegationEntries(lines)) {
    stats.count(entry.subagent, entry.model || "-");
  }
  return stats;
}

/**
 * Read and aggregate the delegation log; null when the file is missing.
 * @param {string} path
 * @returns {DelegationStats | null}
 */
export function parseDelegationLog(path) {
  if (!isFile(path)) {
    return null;
  }
  return aggregateDelegationLines(pySplitlines(readText(path)));
}

// --------------------------------------------------------------------------------------
// Main session transcript — `~/.claude/projects/<munged-root>/*.jsonl`
// --------------------------------------------------------------------------------------

/**
 * Aggregated main-session transcript stats: per-model token usage + a user-message count, and the
 * code-touch scan of the directory the transcript sits in once `main` has made it.
 */
export class TranscriptStats {
  constructor() {
    /** @type {Map<string, TokenUsage>} */
    this.perModel = new Map();
    this.userMessageCount = 0;
    /**
     * The scan of the directory the transcript sits in (A49), set by `main`; null until then.
     * @type {CodeTouchStats | null}
     */
    this.codeTouch = null;
  }
}

/**
 * One transcript line as a JSON object; null for a blank, unparseable or non-object line.
 * @param {string} raw
 * @returns {Record<string, Json> | null}
 */
function _record(raw) {
  const line = pyStrip(raw);
  if (!line) {
    return null;
  }
  let record;
  try {
    record = jsonLoads(line);
  } catch (error) {
    if (error instanceof JSONDecodeError) {
      return null;
    }
    throw error;
  }
  return isDict(record) ? record : null;
}

/**
 * Aggregate a main-session transcript: per-model token usage + a user-message count.
 *
 * Tolerates unparseable lines and ignores record types other than `assistant` (with
 * `message.usage`) and `user` (counted only).
 * @param {Iterable<string>} lines
 * @returns {TranscriptStats}
 */
export function aggregateTranscriptLines(lines) {
  const stats = new TranscriptStats();
  for (const raw of lines) {
    const record = _record(raw);
    if (record === null) {
      continue;
    }
    const recordType = dictGet(record, "type");
    if (recordType === "user") {
      stats.userMessageCount += 1;
      continue;
    }
    if (recordType !== "assistant") {
      continue;
    }
    const message = dictGet(record, "message");
    if (!isDict(message)) {
      continue;
    }
    const usage = usageFromMessage(message);
    if (usage === null) {
      continue;
    }
    const modelValue = dictGet(message, "model");
    const model = truthy(modelValue) ? pyStr(modelValue) : "-";
    stats.perModel.set(model, (stats.perModel.get(model) ?? new TokenUsage()).add(usage));
  }
  return stats;
}

/**
 * Read and aggregate the main-session transcript; null when `path` is absent.
 * @param {string | null} path
 * @returns {TranscriptStats | null}
 */
export function parseMainTranscript(path) {
  if (path === null || !isFile(path)) {
    return null;
  }
  return aggregateTranscriptLines(pySplitlines(readText(path)));
}

// --------------------------------------------------------------------------------------
// Subagent transcripts — `<session-stem>/subagents/agent-<id>.jsonl` + `.meta.json`
// --------------------------------------------------------------------------------------

/** One subagent transcript's identity, label/tier, and total token usage. */
export class SubagentRecord {
  /**
   * @param {string} agentId
   * @param {string} label
   * @param {string} tier
   * @param {TokenUsage} usage
   */
  constructor(agentId, label, tier, usage) {
    this.agentId = agentId;
    this.label = label;
    this.tier = tier;
    this.usage = usage;
  }
}

/**
 * Map `k_*` agent name to tier, from the routing registry's generated-agent specs.
 * @param {AgentsData} agents
 * @returns {Map<string, string>}
 */
export function agentTierMap(agents) {
  return new Map(agentSpecs(agents).map((spec) => [spec.name, spec.tier]));
}

/**
 * A JSON object read from `path`: `{}` when the file is absent, unparsable or not an object.
 * @param {string} path
 * @returns {Record<string, Json>}
 */
function _readJsonDict(path) {
  if (!isFile(path)) {
    return {};
  }
  let data;
  try {
    data = jsonLoads(readText(path));
  } catch (error) {
    if (error instanceof JSONDecodeError) {
      return {};
    }
    throw error;
  }
  return isDict(data) ? data : {};
}

/**
 * Display label and tier for a subagent transcript, from its `.meta.json` and the tier map.
 * @param {Record<string, Json>} meta
 * @param {string} fallbackLabel
 * @param {Map<string, string>} tierMap
 * @returns {[string, string]}
 */
export function labelAndTier(meta, fallbackLabel, tierMap) {
  const agentType = dictGet(meta, "agentType");
  const label = truthy(agentType) ? pyStr(agentType) : fallbackLabel || "-";
  return [label, tierMap.get(label) ?? "-"];
}

/**
 * One subagent transcript's total usage, plus its `attributionAgent` as a label fallback.
 * @param {Iterable<string>} lines
 * @returns {[TokenUsage, string | null]}
 */
export function aggregateSubagentLines(lines) {
  let total = new TokenUsage();
  /** @type {string | null} */ let fallbackLabel = null;
  for (const raw of lines) {
    const record = _record(raw);
    if (record === null) {
      continue;
    }
    if (fallbackLabel === null) {
      const attribution = dictGet(record, "attributionAgent");
      if (typeof attribution === "string" && attribution) {
        fallbackLabel = attribution;
      }
    }
    if (dictGet(record, "type") !== "assistant") {
      continue;
    }
    const message = dictGet(record, "message");
    if (!isDict(message)) {
      continue;
    }
    const usage = usageFromMessage(message);
    if (usage !== null) {
      total = total.add(usage);
    }
  }
  return [total, fallbackLabel];
}

/**
 * Every `agent-*.jsonl` transcript of a subagents directory; `[]` when the directory is missing.
 * @param {string} subagentsDir
 * @param {Map<string, string>} tierMap
 * @returns {SubagentRecord[]}
 */
export function collectSubagentStats(subagentsDir, tierMap) {
  if (!isDir(subagentsDir)) {
    return [];
  }
  const names = fs
    .readdirSync(subagentsDir)
    .filter((name) => name.startsWith("agent-") && pySuffix(name) === ".jsonl")
    .sort(codePointCompare);
  /** @type {SubagentRecord[]} */ const records = [];
  for (const name of names) {
    const agentId = pyStem(name);
    const meta = _readJsonDict(pyPath(subagentsDir, `${agentId}.meta.json`));
    const [usage, fallbackLabel] = aggregateSubagentLines(pySplitlines(readText(pyPath(subagentsDir, name))));
    const [label, tier] = labelAndTier(meta, fallbackLabel || "-", tierMap);
    records.push(new SubagentRecord(agentId, label, tier, usage));
  }
  return records;
}

// --------------------------------------------------------------------------------------
// Code touch — which sessions needed code at all (task A49)
// --------------------------------------------------------------------------------------

/** The three classes a session falls into, from the strongest touch of code to none. */
export const CODE_EDIT = "code-edit";
export const CODE_READ = "code-read";
export const NO_CODE = "no-code";

/** What counts as touching code: the tools, the code-file extensions, the test-command pattern. */
export class TouchRules {
  /**
   * @param {object} fields
   * @param {Set<string>} fields.codeExtensions
   * @param {Set<string>} fields.editTools
   * @param {Set<string>} fields.readTools
   * @param {Set<string>} fields.shellTools
   * @param {string[]} fields.pathFields
   * @param {RegExp} fields.commandPattern
   * @param {string} fields.systemReminderPrefix
   */
  constructor({ codeExtensions, editTools, readTools, shellTools, pathFields, commandPattern, systemReminderPrefix }) {
    this.codeExtensions = codeExtensions;
    this.editTools = editTools;
    this.readTools = readTools;
    this.shellTools = shellTools;
    this.pathFields = pathFields;
    this.commandPattern = commandPattern;
    this.systemReminderPrefix = systemReminderPrefix;
    Object.freeze(this);
  }
}

/**
 * The rules from the `code_touch` block of `stats.json`.
 * @param {StatsData} data the whole file
 * @returns {TouchRules}
 */
export function touchRules(data) {
  const block = data.code_touch;
  return new TouchRules({
    codeExtensions: new Set(block.code_extensions),
    editTools: new Set(block.edit_tools),
    readTools: new Set(block.read_tools),
    shellTools: new Set(block.shell_tools),
    pathFields: [...block.path_fields],
    commandPattern: new RegExp(String.raw`\b(?:${block.test_command_patterns.join("|")})\b`),
    systemReminderPrefix: block.system_reminder_prefix,
  });
}

/**
 * One transcript classified: its class, the user turn of its first code touch, its label.
 * `label` is the subagent type for a subagent transcript and `-` for a main session.
 */
export class SessionTouch {
  /**
   * @param {string} kind
   * @param {number | null} firstTouchTurn
   * @param {string} [label]
   */
  constructor(kind, firstTouchTurn, label = "-") {
    this.kind = kind;
    this.firstTouchTurn = firstTouchTurn;
    this.label = label;
    Object.freeze(this);
  }
}

/** Every classified main session and subagent transcript found beside the located transcript. */
export class CodeTouchStats {
  /**
   * @param {string} scanned
   * @param {SessionTouch[]} main
   * @param {SessionTouch[]} subagents
   */
  constructor(scanned, main, subagents) {
    this.scanned = scanned;
    this.main = main;
    this.subagents = subagents;
    Object.freeze(this);
  }
}

/**
 * A prompt typed by the user: not a tool result, not a meta or system-reminder record.
 * @param {Record<string, Json>} record
 * @param {TouchRules} rules
 * @returns {boolean}
 */
function _isUserTurn(record, rules) {
  if (dictGet(record, "type") !== "user" || truthy(dictGet(record, "isMeta"))) {
    return false;
  }
  const message = dictGet(record, "message");
  const content = isDict(message) ? dictGet(message, "content") : null;
  if (typeof content === "string") {
    return !content.startsWith(rules.systemReminderPrefix);
  }
  if (Array.isArray(content)) {
    const kinds = new Set(content.filter((item) => isDict(item)).map((item) => dictGet(item, "type")));
    return !kinds.has("tool_result") && kinds.has("text");
  }
  return false;
}

/**
 * CODE_EDIT or CODE_READ when one tool call touches code, else null.
 * @param {Record<string, Json>} toolUse
 * @param {TouchRules} rules
 * @returns {string | null}
 */
function _touchesCode(toolUse, rules) {
  const name = dictGet(toolUse, "name");
  const toolInput = dictGet(toolUse, "input");
  if (typeof name !== "string" || !isDict(toolInput)) {
    return null;
  }
  if (rules.shellTools.has(name)) {
    const command = dictGet(toolInput, "command");
    return typeof command === "string" && rules.commandPattern.test(command) ? CODE_READ : null;
  }
  if (!rules.editTools.has(name) && !rules.readTools.has(name)) {
    return null;
  }
  const field = rules.pathFields.find((candidate) => truthy(dictGet(toolInput, candidate)));
  const target = field === undefined ? "" : dictGet(toolInput, field);
  if (typeof target !== "string" || !rules.codeExtensions.has(pyLower(pySuffix(basename(target))))) {
    return null;
  }
  return rules.editTools.has(name) ? CODE_EDIT : CODE_READ;
}

/**
 * The lines that are JSON objects; blank, unparseable and non-object lines are passed over.
 * @param {Iterable<string>} lines
 * @returns {Generator<Record<string, Json>>}
 */
function* _jsonRecords(lines) {
  for (const raw of lines) {
    const record = _record(raw);
    if (record !== null) {
      yield record;
    }
  }
}

/**
 * The `tool_use` items of an assistant record.
 * @param {Record<string, Json>} record
 * @returns {Record<string, Json>[]}
 */
function _toolUses(record) {
  const message = dictGet(record, "message");
  const content = isDict(message) ? dictGet(message, "content") : null;
  if (dictGet(record, "type") !== "assistant" || !Array.isArray(content)) {
    return [];
  }
  return content.filter(
    /** @returns {item is Record<string, Json>} */ (item) => isDict(item) && dictGet(item, "type") === "tool_use",
  );
}

/**
 * Classify one transcript; null when it holds no user turn (nothing asked, nothing to measure).
 *
 * A code *edit* is an edit tool on a code file; a code *read* is a read tool on a code file or a
 * shell command running the project's tests, linters or tools. A shell write (heredoc, `sed -i`)
 * and `Grep`/`Glob` are not counted, so NO_CODE is an upper bound on the sessions that never
 * touched code. `firstTouchTurn` is how many user turns had been seen at the first edit or read,
 * whichever came first. The label is the transcript's `attributionAgent`, else `-`.
 * @param {Iterable<string>} lines
 * @param {TouchRules} rules
 * @returns {SessionTouch | null}
 */
export function classifySessionLines(lines, rules) {
  let turns = 0;
  let edited = false;
  /** @type {number | null} */ let firstTouchTurn = null;
  let label = "-";
  for (const record of _jsonRecords(lines)) {
    const attribution = dictGet(record, "attributionAgent");
    if (label === "-" && typeof attribution === "string" && attribution) {
      label = attribution;
    }
    if (_isUserTurn(record, rules)) {
      turns += 1;
      continue;
    }
    for (const toolUse of _toolUses(record)) {
      const kind = _touchesCode(toolUse, rules);
      if (kind === null) {
        continue;
      }
      edited = edited || kind === CODE_EDIT;
      firstTouchTurn ??= turns;
    }
  }
  if (turns === 0) {
    return null;
  }
  if (edited) {
    return new SessionTouch(CODE_EDIT, firstTouchTurn, label);
  }
  return new SessionTouch(firstTouchTurn === null ? NO_CODE : CODE_READ, firstTouchTurn, label);
}

/**
 * Classify one transcript file, decoding what is not UTF-8 leniently.
 * @param {string} path
 * @param {TouchRules} rules
 * @returns {SessionTouch | null}
 */
function _classifyFile(path, rules) {
  return classifySessionLines(pySplitlines(readText(path)), rules);
}

/**
 * Classify every session of a transcript directory and every subagent transcript under it.
 *
 * Main sessions are the `*.jsonl` files of the directory; subagents are
 * `<directory>/<session>/subagents/agent-*.jsonl`, labelled by their `.meta.json` `agentType`
 * (else their `attributionAgent`). Null when the directory is missing.
 * @param {string} transcriptsDirectory
 * @param {TouchRules} rules
 * @returns {CodeTouchStats | null}
 */
export function collectCodeTouch(transcriptsDirectory, rules) {
  if (!isDir(transcriptsDirectory)) {
    return null;
  }
  const entries = fs.readdirSync(transcriptsDirectory).sort(codePointCompare);
  /** @type {SessionTouch[]} */ const main = [];
  for (const name of entries.filter((entry) => pySuffix(entry) === ".jsonl")) {
    const path = pyPath(transcriptsDirectory, name);
    const touch = isFile(path) ? _classifyFile(path, rules) : null;
    if (touch !== null) {
      main.push(touch);
    }
  }
  /** @type {SessionTouch[]} */ const subagents = [];
  for (const session of entries) {
    const subagentsDir = pyPath(transcriptsDirectory, session, "subagents");
    if (!isDir(subagentsDir)) {
      continue;
    }
    const names = fs
      .readdirSync(subagentsDir)
      .filter((name) => name.startsWith("agent-") && pySuffix(name) === ".jsonl")
      .sort(codePointCompare);
    for (const name of names) {
      const touch = _classifyFile(pyPath(subagentsDir, name), rules);
      if (touch === null) {
        continue;
      }
      const meta = _readJsonDict(pyPath(subagentsDir, `${pyStem(name)}.meta.json`));
      const [label] = labelAndTier(meta, touch.label, new Map());
      subagents.push(new SessionTouch(touch.kind, touch.firstTouchTurn, label));
    }
  }
  return new CodeTouchStats(transcriptsDirectory, main, subagents);
}

// --------------------------------------------------------------------------------------
// Budget — Claude API usage endpoint (opt out with --no-budget)
// --------------------------------------------------------------------------------------

/** One usage-endpoint limit: its label, remaining percent, and reset time. */
export class LimitSummary {
  /**
   * @param {string} label
   * @param {number | null} remainingPct
   * @param {Json} resetsAt
   */
  constructor(label, remainingPct, resetsAt) {
    this.label = label;
    this.remainingPct = remainingPct;
    this.resetsAt = resetsAt;
  }
}

/** Parsed `/api/oauth/usage` response: session/week/scoped limits, or an unavailable reason. */
export class BudgetSummary {
  /**
   * @param {{session?: LimitSummary | null, week?: LimitSummary | null, scoped?: LimitSummary[],
   *   unavailable?: string | null}} [fields]
   */
  constructor({ session = null, week = null, scoped = [], unavailable = null } = {}) {
    this.session = session;
    this.week = week;
    this.scoped = scoped;
    this.unavailable = unavailable;
  }
}

/**
 * Python's `round(x, 1)` of a float: correctly rounded, an exact tie to the even digit.
 * @param {number} x
 * @returns {number}
 */
function _round1(x) {
  const quad = x * 4;
  // An exact tie at one decimal is `odd / 4` (`toFixed` would send it away from zero).
  if (Number.isFinite(x) && Number.isInteger(quad) && Math.abs(quad) % 2 === 1) {
    const lower = Math.trunc(Math.abs(x) * 10);
    const even = lower % 2 === 0 ? lower : lower + 1;
    return (x < 0 ? -even : even) / 10;
  }
  return Number(x.toFixed(1));
}

/**
 * @param {Json} percent
 * @returns {number | null}
 */
function _remainingPct(percent) {
  // Python's `isinstance(percent, (int, float))`: a bool counts.
  if (typeof percent === "boolean") {
    return _round1(100 - (percent ? 1 : 0));
  }
  if (typeof percent !== "number") {
    return null;
  }
  return _round1(100 - percent);
}

/**
 * `value or {}`.
 * @param {Json} value
 * @returns {Json}
 */
function _orEmpty(value) {
  return truthy(value) ? value : {};
}

/**
 * Pure parse of the `/api/oauth/usage` response shape into remaining-budget summaries.
 * @param {StatsData} data
 * @param {Json} response
 * @returns {BudgetSummary}
 */
export function parseUsageResponse(data, response) {
  try {
    const labels = data.budget_labels;
    const fiveHour = _orEmpty(dictGet(response, "five_hour"));
    const sevenDay = _orEmpty(dictGet(response, "seven_day"));
    const session = new LimitSummary(
      labels.session,
      _remainingPct(dictGet(fiveHour, "utilization")),
      dictGet(fiveHour, "resets_at"),
    );
    const week = new LimitSummary(
      labels.week_all_models,
      _remainingPct(dictGet(sevenDay, "utilization")),
      dictGet(sevenDay, "resets_at"),
    );
    /** @type {LimitSummary[]} */ const scoped = [];
    const limits = dictGet(response, "limits");
    for (const limit of pyIterate(truthy(limits) ? limits : [])) {
      if (!isDict(limit) || dictGet(limit, "kind") !== "weekly_scoped") {
        continue;
      }
      const scope = _orEmpty(dictGet(_orEmpty(dictGet(limit, "scope")), "model"));
      const modelName = dictGet(scope, "display_name", "?");
      scoped.push(
        new LimitSummary(
          fill(labels.week_scoped, { model: pyStr(modelName) }),
          _remainingPct(dictGet(limit, "percent")),
          dictGet(limit, "resets_at"),
        ),
      );
    }
    return new BudgetSummary({ session, week, scoped });
  } catch (exc) {
    // Any unexpected shape degrades, never crashes the digest.
    return new BudgetSummary({ unavailable: `${exceptionClassName(exc)}: ${/** @type {Error} */ (exc).message}` });
  }
}

/**
 * The OAuth access token from a `.credentials.json` file, or null when absent/malformed.
 * @param {string} credentialsPath
 * @returns {string | null}
 */
export function readAccessToken(credentialsPath) {
  const data = _readJsonDict(credentialsPath);
  const oauth = dictGet(data, "claudeAiOauth");
  const token = isDict(oauth) ? dictGet(oauth, "accessToken") : null;
  return typeof token === "string" && token ? token : null;
}

/** The seconds the usage call may take before it is abandoned. */
const FETCH_TIMEOUT_MS = 10_000;

/**
 * The one network call in this module — kept tiny so tests inject a canned response instead.
 * @param {string} url
 * @param {string} token
 * @returns {Promise<Json>}
 */
export async function fetchUsage(url, token) {
  const response = await globalThis.fetch(url, {
    headers: { Authorization: `Bearer ${token}`, "anthropic-beta": "oauth-2025-04-20" },
    signal: globalThis.AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });
  if (!response.ok) {
    // `urllib.error.HTTPError`, worded as Python words it.
    const error = new Error(`HTTP Error ${response.status}: ${response.statusText}`);
    error.name = "HTTPError";
    throw error;
  }
  return jsonLoads(decodeUtf8(new Uint8Array(await response.arrayBuffer())));
}

/**
 * Never throws: any failure (no creds, HTTP error, timeout, bad shape) becomes `unavailable`.
 * @param {StatsData} data
 * @param {{credentialsPath?: string | null, fetch?: (url: string, token: string) => Promise<Json>}} [options]
 *   `credentialsPath` (default `~/<credentials_rel>`) and `fetch` (default {@link fetchUsage})
 * @returns {Promise<BudgetSummary>}
 */
export async function budgetSummary(data, { credentialsPath = null, fetch: fetchFn = fetchUsage } = {}) {
  const credsPath = credentialsPath || pyPath(os.homedir(), data.credentials_rel);
  try {
    const token = readAccessToken(credsPath);
    if (!token) {
      return new BudgetSummary({ unavailable: "no credentials found" });
    }
    const response = await fetchFn(data.usage_url, token);
    return parseUsageResponse(data, response);
  } catch (exc) {
    return new BudgetSummary({ unavailable: `${exceptionClassName(exc)}: ${/** @type {Error} */ (exc).message}` });
  }
}

// --------------------------------------------------------------------------------------
// Rendering — full report (file) + compact digest (stdout)
// --------------------------------------------------------------------------------------

/**
 * @param {number | null} value
 * @returns {string}
 */
function _fmtPct(value) {
  return value !== null ? `${floatRepr(value)}%` : "-";
}

/**
 * @param {Json} value
 * @returns {string}
 */
function _fmtResets(value) {
  return truthy(value) ? pyStr(value) : "-";
}

/**
 * `count` of `total` as a whole percent, halves rounded up — integer arithmetic, so both twins agree.
 * @param {number} count
 * @param {number} total
 * @returns {number}
 */
function _percent(count, total) {
  return Math.floor((200 * count + total) / (2 * total));
}

/**
 * @param {number} count
 * @param {number} total
 * @returns {string}
 */
function _share(count, total) {
  return total ? `${_percent(count, total)}%` : "-";
}

/**
 * The median of whole numbers, `-` for none; an even count between two odd values ends in `.5`.
 * @param {number[]} values
 * @returns {string}
 */
function _medianText(values) {
  const ordered = [...values].sort((a, b) => a - b);
  if (ordered.length === 0) {
    return "-";
  }
  const middle = Math.floor(ordered.length / 2);
  if (ordered.length % 2) {
    return String(ordered[middle]);
  }
  const pair = ordered[middle - 1] + ordered[middle];
  return pair % 2 === 0 ? String(pair / 2) : `${Math.floor(pair / 2)}.5`;
}

/**
 * The class counts of one group of transcripts, as the texts the digest and the report print.
 * @param {SessionTouch[]} touches
 * @returns {{n: string, edit: string, read: string, none: string, median: string}}
 */
function _group(touches) {
  const total = touches.length;
  /** @param {string} kind @returns {string} */
  const counted = (kind) => {
    const count = touches.filter((touch) => touch.kind === kind).length;
    return `${count} (${_share(count, total)})`;
  };
  const turns = touches.map((touch) => touch.firstTouchTurn).filter((turn) => turn !== null);
  return {
    n: String(total),
    edit: counted(CODE_EDIT),
    read: counted(CODE_READ),
    none: counted(NO_CODE),
    median: _medianText(/** @type {number[]} */ (turns)),
  };
}

/**
 * `[type, transcripts, no-code transcripts]` per subagent type, the largest no-code share first.
 * @param {SessionTouch[]} subagents
 * @returns {[string, number, number][]}
 */
function _noCodeByType(subagents) {
  /** @type {Map<string, [number, number]>} */ const counts = new Map();
  for (const touch of subagents) {
    const entry = counts.get(touch.label) ?? [0, 0];
    entry[0] += 1;
    entry[1] += touch.kind === NO_CODE ? 1 : 0;
    counts.set(touch.label, entry);
  }
  return [...counts.entries()]
    .map(/** @returns {[string, number, number]} */ ([label, [total, empty]]) => [label, total, empty])
    .sort((a, b) => _percent(b[2], b[1]) - _percent(a[2], a[1]) || codePointCompare(a[0], b[0]));
}

/**
 * The digest's code-touch lines: both groups, the no-code share per subagent type, the limit.
 * @param {StatsData} data
 * @param {CodeTouchStats | null} codeTouch
 * @returns {string[]}
 */
function _renderCodeTouchDigest(data, codeTouch) {
  const texts = data.digest;
  if (codeTouch === null || (codeTouch.main.length === 0 && codeTouch.subagents.length === 0)) {
    return [texts.code_touch_none];
  }
  /** @type {string[]} */ const lines = [];
  for (const [name, touches] of [
    [data.code_touch.group_main, codeTouch.main],
    [data.code_touch.group_subagents, codeTouch.subagents],
  ]) {
    const touched = /** @type {SessionTouch[]} */ (touches);
    if (touched.length === 0) {
      lines.push(fill(texts.code_touch_group_empty, { group: String(name) }));
      continue;
    }
    lines.push(fill(texts.code_touch_group, { group: String(name), ..._group(touched) }));
  }
  if (codeTouch.subagents.length > 0) {
    const types = _noCodeByType(codeTouch.subagents)
      .map(([label, total, empty]) => `${label} ${_share(empty, total)} (n=${total})`)
      .join(", ");
    lines.push(fill(texts.code_touch_no_code_by_type, { types }));
  }
  lines.push(texts.code_touch_limit);
  return lines;
}

/**
 * The '## Code touch' body: a table per group, a table per subagent type, the definitions.
 * @param {StatsData} data
 * @param {CodeTouchStats | null} codeTouch
 * @returns {string[]}
 */
function _renderCodeTouchSection(data, codeTouch) {
  const texts = data.report;
  if (codeTouch === null || (codeTouch.main.length === 0 && codeTouch.subagents.length === 0)) {
    return [texts.code_touch_none];
  }
  const lines = [fill(texts.code_touch_scanned, { dir: codeTouch.scanned }), "", ...texts.code_touch_group_header];
  for (const [name, touches] of [
    [data.code_touch.group_main, codeTouch.main],
    [data.code_touch.group_subagents, codeTouch.subagents],
  ]) {
    lines.push(
      fill(texts.code_touch_group_row, { group: String(name), ..._group(/** @type {SessionTouch[]} */ (touches)) }),
    );
  }
  if (codeTouch.subagents.length > 0) {
    lines.push("", ...texts.code_touch_type_header);
    for (const [label, total, empty] of _noCodeByType(codeTouch.subagents)) {
      lines.push(
        fill(texts.code_touch_type_row, {
          type: label,
          n: String(total),
          none: String(empty),
          share: _share(empty, total),
        }),
      );
    }
  }
  lines.push("", texts.code_touch_note);
  return lines;
}

/**
 * Which session a report is about — its stem and the transcript path it was parsed from.
 *
 * The two travel together everywhere a report is rendered: `stem` is only ever derived from
 * `transcriptPath` (or stands in for a missing one), never chosen independently.
 */
export class SessionRef {
  /**
   * @param {string} stem
   * @param {string | null} transcriptPath
   */
  constructor(stem, transcriptPath) {
    this.stem = stem;
    this.transcriptPath = transcriptPath;
    Object.freeze(this);
  }
}

/**
 * The '## Delegations' body: total plus the per-subagent/model breakdown table.
 * @param {StatsData} data
 * @param {DelegationStats | null} delegation
 * @returns {string[]}
 */
function _renderDelegationsSection(data, delegation) {
  const texts = data.report;
  if (delegation === null) {
    return [texts.delegations_none];
  }
  if (delegation.total === 0) {
    return [texts.delegations_zero];
  }
  const rows = [...delegation.perPair.values()].sort(
    (a, b) => codePointCompare(a.subagent, b.subagent) || codePointCompare(a.model, b.model),
  );
  return [
    fill(texts.delegations_total, { total: String(delegation.total) }),
    "",
    ...texts.delegations_table_header,
    ...rows.map((row) =>
      fill(texts.delegations_table_row, { subagent: row.subagent, model: row.model, count: String(row.count) }),
    ),
  ];
}

/**
 * The '## Tokens' body: per-role/tier token table plus the totals row.
 * @param {StatsData} data
 * @param {TranscriptStats | null} transcriptStats
 * @param {SubagentRecord[]} subagents
 * @returns {string[]}
 */
function _renderTokensSection(data, transcriptStats, subagents) {
  const texts = data.report;
  const lines = [...texts.tokens_table_header];
  let total = new TokenUsage();
  if (transcriptStats === null) {
    lines.push(texts.tokens_orchestrator_missing_row);
  } else {
    const models = [...transcriptStats.perModel.keys()].sort(codePointCompare);
    for (const model of models) {
      const usage = /** @type {TokenUsage} */ (transcriptStats.perModel.get(model));
      lines.push(
        fill(texts.tokens_orchestrator_row, {
          model,
          input: String(usage.inputTokens),
          output: String(usage.outputTokens),
          cache_read: String(usage.cacheReadTokens),
          cache_created: String(usage.cacheCreationTokens),
        }),
      );
      total = total.add(usage);
    }
  }
  for (const record of subagents) {
    lines.push(
      fill(texts.tokens_subagent_row, {
        label: record.label,
        tier: record.tier,
        input: String(record.usage.inputTokens),
        output: String(record.usage.outputTokens),
        cache_read: String(record.usage.cacheReadTokens),
        cache_created: String(record.usage.cacheCreationTokens),
      }),
    );
    total = total.add(record.usage);
  }
  lines.push(
    fill(texts.tokens_total_row, {
      input: String(total.inputTokens),
      output: String(total.outputTokens),
      cache_read: String(total.cacheReadTokens),
      cache_created: String(total.cacheCreationTokens),
    }),
  );
  if (subagents.length === 0) {
    lines.push("");
    lines.push(texts.tokens_no_subagents);
  }
  return lines;
}

/**
 * The '## Budget' body: unavailable notice, or the session/week/scoped remaining lines.
 * @param {StatsData} data
 * @param {BudgetSummary} budget
 * @returns {string[]}
 */
function _renderBudgetSection(data, budget) {
  const texts = data.report;
  if (budget.unavailable) {
    return [fill(texts.budget_unavailable, { reason: budget.unavailable })];
  }
  /** @type {string[]} */ const lines = [];
  if (budget.session) {
    lines.push(
      fill(texts.budget_session_line, {
        remaining: _fmtPct(budget.session.remainingPct),
        resets: _fmtResets(budget.session.resetsAt),
      }),
    );
  }
  if (budget.week) {
    lines.push(
      fill(texts.budget_week_line, {
        remaining: _fmtPct(budget.week.remainingPct),
        resets: _fmtResets(budget.week.resetsAt),
      }),
    );
  }
  for (const scoped of budget.scoped) {
    lines.push(
      fill(texts.budget_scoped_line, {
        label: scoped.label,
        remaining: _fmtPct(scoped.remainingPct),
        resets: _fmtResets(scoped.resetsAt),
      }),
    );
  }
  return lines;
}

/**
 * Full markdown report (file) — delegations, per-role tokens, code touch, budget.
 * @param {StatsData} data
 * @param {string} delegationLog the delegation log's project-root-relative path (named under "Sources")
 * @param {SessionRef} session
 * @param {DelegationStats | null} delegation
 * @param {TranscriptStats | null} transcriptStats
 * @param {SubagentRecord[]} subagents
 * @param {BudgetSummary} budget
 * @returns {string}
 */
export function renderReport(data, delegationLog, session, delegation, transcriptStats, subagents, budget) {
  const texts = data.report;
  const transcriptPath = session.transcriptPath;
  const lines = [fill(texts.title, { stem: session.stem }), ""];
  lines.push(transcriptPath ? fill(texts.transcript_found, { path: transcriptPath }) : texts.transcript_not_found);
  lines.push("");

  lines.push(texts.delegations_heading);
  lines.push("");
  lines.push(..._renderDelegationsSection(data, delegation));
  lines.push("");

  lines.push(texts.tokens_heading);
  lines.push("");
  lines.push(..._renderTokensSection(data, transcriptStats, subagents));
  lines.push("");

  lines.push(texts.code_touch_heading);
  lines.push("");
  lines.push(..._renderCodeTouchSection(data, transcriptStats?.codeTouch ?? null));
  lines.push("");

  lines.push(texts.budget_heading);
  lines.push("");
  lines.push(..._renderBudgetSection(data, budget));
  lines.push("");

  lines.push(texts.separator);
  const sources = transcriptPath ? texts.sources_found : texts.sources_not_found;
  lines.push(fill(sources, { path: transcriptPath ?? "None", delegation_log: delegationLog }));
  return `${lines.join("\n")}\n`;
}

/**
 * Compact stdout digest (~12-16 lines) — relayed to chat verbatim by the calling skill.
 * @param {StatsData} data
 * @param {DelegationStats | null} delegation
 * @param {TranscriptStats | null} transcriptStats
 * @param {SubagentRecord[]} subagents
 * @param {BudgetSummary} budget
 * @param {string} reportPath
 * @returns {string}
 */
export function renderDigest(data, delegation, transcriptStats, subagents, budget, reportPath) {
  const texts = data.digest;
  /** @type {string[]} */ const lines = [];

  if (delegation === null) {
    lines.push(texts.no_delegations_logged);
  } else if (delegation.total === 0) {
    lines.push(texts.no_delegations_recorded);
  } else {
    const perSubagent = [...delegation.perSubagent.entries()]
      .sort((a, b) => codePointCompare(a[0], b[0]))
      .map(([name, count]) => `${name}=${count}`)
      .join(", ");
    lines.push(fill(texts.delegations_total, { total: String(delegation.total), per_subagent: perSubagent }));
  }

  if (transcriptStats === null) {
    lines.push(texts.orchestrator_transcript_unavailable);
  } else {
    const orch = _sumUsage(transcriptStats.perModel.values());
    lines.push(
      fill(texts.orchestrator_tokens, {
        input: String(orch.inputTokens),
        output: String(orch.outputTokens),
        cache_read: String(orch.cacheReadTokens),
      }),
    );
  }

  if (subagents.length > 0) {
    const sub = _sumUsage(subagents.map((record) => record.usage));
    lines.push(
      fill(texts.subagent_tokens, {
        n: String(subagents.length),
        input: String(sub.inputTokens),
        output: String(sub.outputTokens),
        cache_read: String(sub.cacheReadTokens),
      }),
    );
  } else {
    lines.push(texts.no_subagent_transcripts);
  }

  lines.push(..._renderCodeTouchDigest(data, transcriptStats?.codeTouch ?? null));

  if (budget.unavailable) {
    lines.push(fill(texts.budget_unavailable, { reason: budget.unavailable }));
  } else {
    const { session, week } = budget;
    lines.push(
      fill(texts.budget_session_week, {
        session_remaining: session ? _fmtPct(session.remainingPct) : "-",
        session_resets: session ? _fmtResets(session.resetsAt) : "-",
        week_remaining: week ? _fmtPct(week.remainingPct) : "-",
        week_resets: week ? _fmtResets(week.resetsAt) : "-",
      }),
    );
    for (const scoped of budget.scoped) {
      lines.push(
        fill(texts.budget_scoped, {
          label: scoped.label,
          remaining: _fmtPct(scoped.remainingPct),
          resets: _fmtResets(scoped.resetsAt),
        }),
      );
    }
  }

  lines.push(fill(texts.report, { path: reportPath }));
  return lines.join("\n");
}

// --------------------------------------------------------------------------------------
// CLI
// --------------------------------------------------------------------------------------

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, transcript: string | null, noBudget: boolean,
 *   reportDir: string | null, task: string | null, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        transcript: { type: "string" },
        "no-budget": { type: "boolean" },
        "report-dir": { type: "string" },
        task: { type: "string" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    const taskProblem = values.help === true ? null : taskError(/** @type {string | undefined} */ (values.task));
    if (taskProblem !== null) {
      return taskProblem;
    }
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      transcript: /** @type {string | undefined} */ (values.transcript) ?? null,
      noBudget: values["no-budget"] === true,
      reportDir: /** @type {string | undefined} */ (values["report-dir"]) ?? null,
      task: /** @type {string | undefined} */ (values.task) ?? null,
      help: values.help === true,
    };
  } catch (exc) {
    const code = /** @type {{code?: string}} */ (exc).code;
    if (typeof code !== "string" || !code.startsWith("ERR_PARSE_ARGS_")) {
      throw exc;
    }
    // parseArgs words some errors over several lines (the hint for the fix); the first is the fact.
    return /** @type {Error} */ (exc).message.split("\n")[0];
  }
}

/**
 * CLI entry point: assemble the digest, write the full report, print the compact digest.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @param {{fetch?: (url: string, token: string) => Promise<Json>}} [deps] the budget call (default:
 *   {@link fetchUsage}); tests inject a canned one
 * @returns {Promise<number>} The process exit code: 0, or 2 on a usage error.
 */
export async function main(argv = process.argv.slice(2), deps = {}) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`${PROG}: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  const modelRouting = pyPath(TREE_ROOT, "tools", "model_routing");
  const data = /** @type {StatsData} */ (read(pyPath(modelRouting, "stats.json")));
  const agents = /** @type {AgentsData} */ (read(pyPath(modelRouting, "agents.json")));

  const root = resolvePath(options.projectRoot ?? process.cwd());
  const logRel = delegationLogRel(agents);

  const delegation = parseDelegationLog(pyPath(root, logRel));

  const transcriptPath = options.transcript !== null ? pyPath(options.transcript) : newestJsonl(transcriptsDir(root));
  const transcriptStats = parseMainTranscript(transcriptPath);

  const sessionStem = transcriptPath !== null ? pyStem(transcriptPath) : "-";
  /** @type {SubagentRecord[]} */ let subagentRecords = [];
  if (transcriptPath !== null) {
    subagentRecords = collectSubagentStats(
      pyPath(dirname(transcriptPath), sessionStem, "subagents"),
      agentTierMap(agents),
    );
  }

  if (transcriptStats !== null && transcriptPath !== null) {
    transcriptStats.codeTouch = collectCodeTouch(dirname(transcriptPath), touchRules(data));
  }

  const budget = options.noBudget
    ? new BudgetSummary({ unavailable: "skipped (--no-budget)" })
    : await budgetSummary(data, deps.fetch === undefined ? {} : { fetch: deps.fetch });

  const reportDir = options.reportDir !== null ? pyPath(options.reportDir) : pyPath(root, data.report_dir_rel);
  const reportFile = createReport(
    reportDir,
    reportPrefix("stats", options.task),
    renderReport(
      data,
      logRel,
      new SessionRef(sessionStem, transcriptPath),
      delegation,
      transcriptStats,
      subagentRecords,
      budget,
    ),
  );

  process.stdout.write(`${renderDigest(data, delegation, transcriptStats, subagentRecords, budget, reportFile)}\n`);
  return 0;
}

/**
 * Whether node was told to execute `invoked` as this very module (see `akmon/cli.mjs`).
 * @param {string} invoked `process.argv[1]`, the path node was given
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = await main();
}
