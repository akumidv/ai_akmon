/**
 * Claude PreToolUse wrapper for the akmon delegation nudge — the JavaScript twin of
 * `hooks/delegation-nudge.py` (ADR 0020 D01).
 *
 * Scores orchestrator edit/shell/read calls since session start or the last subagent delegation
 * (`Task`/`Agent` resets the score and re-arms the reminder) — an edit or shell call counts 1, a
 * read ½, the first calls of a stretch nothing (C88, ADR-0006/D02) — and, past the threshold,
 * injects a soft reminder — once per drift episode — that the work may belong to a `k_*`
 * delegate (MODEL.md § Capability tiers). Below the ask threshold, advisory only — nothing is
 * blocked; past it, the next edit or shell call (never a read) carries a hard `ask`, which
 * escalates to `deny` outside the interactive default permission mode (C31, ADR-0006/D02 — an
 * unattended `ask` was observed to be a silent no-op). This fires only for main-chain calls: a
 * subagent call (detected via the payload's `agent_id`, present only inside a subagent) is
 * exempt, since Claude Code shares the `session_id` between the main chain and its subagents
 * and a k_* delegate has no `Task` tool to act on the nudge anyway. The decision logic lives
 * in `hook_core.mjs`; this entry point only adapts Claude Code's payload.
 */

import { dictGet, dictItem, pyStr, truthy } from "../common/pyvalue.mjs";
import { loadPayload, normalizeTool, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { delegationNudgeResult, neutralKind } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */

/**
 * Claude tool names → the neutral kinds hook_core expects (edit tools via normalizeTool, C102).
 * @param {HookData} data
 * @returns {Map<string, string>}
 */
function toolKinds(data) {
  const table = dictItem(dictItem(data.vocabulary, "claude"), "delegation_nudge_tool_kinds");
  return new Map(Object.entries(table).map(([name, stem]) => [name, neutralKind(data, /** @type {string} */ (stem))]));
}

/**
 * @param {HookData} data
 * @returns {import("./hook_core.mjs").HookResult | null}
 */
function decide(data) {
  const payload = loadPayload();
  const rawName = dictGet(payload, "tool_name");
  const name = pyStr(truthy(rawName) ? rawName : "");
  const kind = toolKinds(data).get(name) || normalizeTool(data, name);
  const sessionId = dictGet(payload, "session_id");
  const isSubagent = truthy(dictGet(payload, "agent_id"));
  const permissionMode = dictGet(payload, "permission_mode");
  return delegationNudgeResult(data, kind, typeof sessionId === "string" ? sessionId : null, {
    isSubagent,
    permissionMode: typeof permissionMode === "string" ? permissionMode : null,
  });
}

/**
 * Entry point: score delegation drift and nudge or ask, never blocking outright.
 * @returns {number} the process exit code
 */
export function main() {
  const data = lazyHookData();
  // Never block a tool call: a crash is reported (stderr + the owner's notice), exit 0.
  return runGuarded("delegation-nudge", data, () => decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
