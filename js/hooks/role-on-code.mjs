/**
 * Claude PreToolUse wrapper for the akmon design-to-code role reminder — the JavaScript
 * twin of `hooks/role-on-code.py` (ADR 0020 D01).
 *
 * The logic lives in `hook_core.mjs` and returns a vendor-neutral `HookResult`. This entry point
 * only adapts Claude Code's JSON payload/output shape so existing `.claude/settings.json` wiring
 * can keep pointing here.
 */

import { unidentifiedIdentity } from "../common/markers.mjs";
import { dictGet, pyStr, truthy } from "../common/pyvalue.mjs";
import { loadPayload, normalizeTool, projectRoot, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { roleOnCodeResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */

/**
 * @param {HookData} data
 * @returns {import("./hook_core.mjs").HookResult | null}
 */
function decide(data) {
  const payload = loadPayload();
  const rawInput = dictGet(payload, "tool_input");
  const toolInput = truthy(rawInput) ? rawInput : {};
  const rawName = dictGet(payload, "tool_name");
  const toolName = normalizeTool(data, pyStr(truthy(rawName) ? rawName : ""));
  const filePath = dictGet(toolInput, "file_path");
  const rawSession = dictGet(payload, "session_id");
  const sessionId = pyStr(truthy(rawSession) ? rawSession : unidentifiedIdentity(data.markers));
  return roleOnCodeResult(data, toolName, filePath, sessionId, projectRoot(payload));
}

/**
 * Entry point: emit the design-to-code role reminder.
 * @returns {number} the process exit code
 */
export function main() {
  const data = lazyHookData();
  return runGuarded("role-on-code", data, () => decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
