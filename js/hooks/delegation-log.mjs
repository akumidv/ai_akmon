#!/usr/bin/env node
/**
 * Claude PreToolUse wrapper: log each subagent delegation outside model context — the
 * JavaScript twin of `hooks/delegation-log.py` (ADR 0020 D01). The Python module is the spec:
 * the same answers, the same texts, the same exit code and the same stdout and stderr.
 *
 * Appends one TSV line (timestamp, session_id, subagent, model, zone, description) to
 * `.claude/model-routing.log` whenever the session calls the subagent tool (`Agent`/`Task`).
 * Nothing is injected into context and nothing is blocked; a system message makes each
 * delegation — and its declared model — visible in the console, with an advisory line when the
 * agent has no kind in the active role's allowed set (C20), is bound below the rung floor of
 * one of its task kinds (C32), or is an unlabelled delegation in a zoned fan-out (C33).
 *
 * Data (the C104 convention): `hooks/delegation_log.json` is `data.delegationLog`, read when the
 * first message is formatted, as the Python reads it; the routing calls get `data.agents`.
 *
 * Twin notes:
 * - the timestamp is `time.strftime("%Y-%m-%dT%H:%M:%S%z")` in the process's local time. With `TZ`
 *   unset it comes from `Date` (both read the host zone); with `TZ` set from `date`, because ICU
 *   reads an IANA name but not a POSIX rule (`CET-1CEST`) or a quoted name (`<+03>-3`) and the
 *   zoneinfo lookup libc does (`posix/Asia/Kolkata`) is the host's, not ICU's. If `date` is
 *   missing or answers something else, `Date` answers;
 * - `log_path.read_text(...).splitlines()` is strict UTF-8, universal newlines, then Python's
 *   line-break set (`readText`, `pySplitlines`); the append opens the file before it encodes the
 *   line, so a lone surrogate leaves an empty file and raises `UnicodeEncodeError`, as `open("a")`
 *   then `write` do;
 * - the payload is arbitrary JSON: `str(x or "")` is `pyStr(truthy(x) ? x : "")` (a list is
 *   `"['a']"`), `isinstance` is a `typeof`/`isDict` test, and a payload read by plain `JSON.parse`
 *   spells `1.0` as `1`;
 * - an absent subagent fills the prefix template as Python's `str(None)`: `[akmon] → None`.
 */

import fs from "node:fs";
import { createRequire } from "node:module";
import { posix } from "node:path";

import { fill } from "../common/jsondata.mjs";
import { findProjectRoot } from "../common/project_root.mjs";
import {
  dictGet,
  dictItem,
  encodeUtf8,
  isDict,
  isFile,
  pyError,
  pyPath,
  pySplitlines,
  pyStr,
  pyStrip,
  readText,
  truthy,
} from "../common/pyvalue.mjs";
import {
  activeRole,
  boundModelFor,
  delegationFloorWarning,
  delegationLogLine,
  delegationLogRel,
  loadRegistry,
  parseDelegationEntries,
  readLocalConfig,
  roleMatrixWarning,
  unlabelledFanoutWarning,
} from "../tools/model_routing/routing.mjs";
import { loadPayload, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { HookResult, akmonRuntimeRoot, assertEncodablePath } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */
/** @typedef {any} Json */

/**
 * Format a delegation-log TSV line as a user-facing system message.
 * @param {HookData} data
 * @param {string} line
 * @returns {string}
 */
function _formatSystemMessage(data, line) {
  const parts = line.split("\t").map((field) => (pyStrip(field) !== "-" ? pyStrip(field) : null));
  // `(parts + [None] * 6)[:6]`
  const padded = [...parts, null, null, null, null, null, null].slice(0, 6);
  const [, , subagent, model, zone, description] = padded;

  // The fragment texts are owned by hooks/delegation_log.json (C102); the assembly order and
  // the empty-part rules stay here.
  const texts = data.delegationLog;
  let msg = fill(dictItem(texts, "subagent_prefix"), { subagent: pyStr(subagent) });
  if (model) {
    msg += fill(dictItem(texts, "model_suffix"), { model });
  }
  if (zone) {
    msg += fill(dictItem(texts, "zone_suffix"), { zone });
  }
  if (description) {
    msg += fill(dictItem(texts, "description_suffix"), { description });
  }
  return msg;
}

/** @param {number} n */
function _two(n) {
  return String(n).padStart(2, "0");
}

/**
 * `time.strftime("%Y-%m-%dT%H:%M:%S%z")`: local time, the offset as `+HHMM`/`-HHMM`.
 *
 * With `TZ` unset Node and libc both read the host zone. With `TZ` set the zone is libc's to
 * name: ICU reads an IANA name but not a POSIX rule or a quoted name, so the clock is asked of
 * `date`, which is libc. That branch is the only one that pays for `node:child_process`.
 * @returns {string}
 */
function _timestamp() {
  if (process.env.TZ) {
    const { spawnSync } = /** @type {typeof import("node:child_process")} */ (
      createRequire(import.meta.url)("node:child_process")
    );
    const done = spawnSync("date", ["+%Y-%m-%dT%H:%M:%S%z"], { encoding: "utf8", timeout: 5000 });
    if (
      done.status === 0 &&
      /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{4}\n$/.test(done.stdout)
    ) {
      return done.stdout.slice(0, -1);
    }
  }
  const now = new Date();
  const east = -now.getTimezoneOffset(); // minutes east of UTC
  const zone = `${east < 0 ? "-" : "+"}${_two(Math.floor(Math.abs(east) / 60))}${_two(Math.abs(east) % 60)}`;
  const date = `${now.getFullYear()}-${_two(now.getMonth() + 1)}-${_two(now.getDate())}`;
  return `${date}T${_two(now.getHours())}:${_two(now.getMinutes())}:${_two(now.getSeconds())}${zone}`;
}

/**
 * `with path.open("a", encoding="utf-8") as handle: handle.write(text)` — opened before encoded.
 * @param {string} path
 * @param {string} text
 */
function _append(path, text) {
  const fd = fs.openSync(path, "a");
  try {
    fs.writeFileSync(fd, encodeUtf8(text));
  } finally {
    fs.closeSync(fd);
  }
}

/**
 * The project root the payload's `cwd` (else `$CLAUDE_PROJECT_DIR`, else the process's) is in.
 * @param {Json} payload
 * @returns {string}
 */
function _projectRoot(payload) {
  let cwd = dictGet(payload, "cwd");
  if (!truthy(cwd)) {
    cwd = process.env.CLAUDE_PROJECT_DIR;
  }
  if (!truthy(cwd)) {
    cwd = process.cwd();
  }
  if (typeof cwd !== "string") {
    throw pyError("TypeError", "argument should be a str or an os.PathLike object where __fspath__ returns a str");
  }
  assertEncodablePath(cwd); // `Path(cwd).resolve()` refuses a NUL or a lone surrogate
  return findProjectRoot(pyPath(cwd));
}

/**
 * @param {HookData} data
 * @returns {HookResult | null}
 */
function _decide(data) {
  const payload = loadPayload();
  const rawInput = dictGet(payload, "tool_input");
  const toolInput = isDict(rawInput) ? rawInput : {};
  const timestamp = _timestamp();
  const sessionId = dictGet(payload, "session_id");
  const root = _projectRoot(payload);

  // Derive the recorded generated-agent pin (its frontmatter `model:` is not echoed in
  // the call). An explicit call override still wins in `delegationLogLine`; neither
  // value is an independent observation of the model the harness actually launched.
  const config = readLocalConfig(data.agents, root);
  const subagentType = pyStr(truthy(dictGet(toolInput, "subagent_type")) ? dictGet(toolInput, "subagent_type") : "");
  const boundModel = boundModelFor(data.agents, config, subagentType);

  const toolName = dictGet(payload, "tool_name");
  const line = delegationLogLine(
    pyStr(truthy(toolName) ? toolName : ""),
    toolInput,
    timestamp,
    typeof sessionId === "string" ? sessionId : null,
    boundModel,
  );
  if (line === null) {
    return null;
  }
  const logPath = pyPath(root, delegationLogRel(data.agents));
  // C33 — read this session's earlier delegations before the new line joins them.
  const earlier = isFile(logPath) ? parseDelegationEntries(pySplitlines(readText(logPath))) : [];
  // The line always carries the six columns, so it parses to exactly one entry.
  const [thisCall] = parseDelegationEntries([line]);
  const zoneWarning = unlabelledFanoutWarning(data.agents, earlier, thisCall.sessionId, subagentType, thisCall.zone);
  fs.mkdirSync(posix.dirname(logPath), { recursive: true });
  _append(logPath, `${line}\n`);
  // Emit a UI-visible system message without injecting it into model context.
  const messages = [_formatSystemMessage(data, line)];
  // C20 — advise when the agent has no overlap with the role's effective allowed set.
  const registry = loadRegistry(data.agents, akmonRuntimeRoot(root), root);
  const role = activeRole(dictGet(payload, "transcript_path"));
  const warning = roleMatrixWarning(data.agents, registry, subagentType, role);
  const warnPrefix = dictItem(data.delegationLog, "warning_prefix");
  if (warning) {
    messages.push(fill(warnPrefix, { warning }));
  }
  // C32 — the recorded task-kind floors are otherwise read by nothing at delegation time.
  const floorWarning = delegationFloorWarning(data.agents, config, subagentType, dictGet(toolInput, "model"));
  if (floorWarning) {
    messages.push(fill(warnPrefix, { warning: floorWarning }));
  }
  if (zoneWarning) {
    messages.push(fill(warnPrefix, { warning: zoneWarning }));
  }
  return new HookResult({ eventName: "PreToolUse", systemMessage: messages.join("\n") });
}

/**
 * Entry point: log the delegation, advisory only.
 * @returns {number} The process exit code.
 */
export function main() {
  const data = lazyHookData();
  // Advisory only: a crash is reported (stderr + the owner's notice) and never blocks the call.
  return runGuarded("delegation-log", data, () => _decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
