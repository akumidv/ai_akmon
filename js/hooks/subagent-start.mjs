/**
 * Claude SubagentStart wrapper: the unattended layer for the delegate that is starting — the
 * JavaScript twin of `hooks/subagent-start.py` (A49, ADR 0020 D01).
 *
 * A delegate is read only by the head session that launched it, so it needs the rules for working
 * without an owner (`rules/unattended.md`), not the owner-dialogue rules the head gets at
 * SessionStart. The `additionalContext` of a `SubagentStart` hook reaches the subagent (M247). The
 * text comes from `hook_core.mjs`; this entry point only adapts Claude Code's JSON payload/output
 * shape.
 */

import { loadPayload, projectRoot, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { subagentStartResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/**
 * Entry point: emit the unattended layer, never blocking the subagent's start.
 * @returns {number} the process exit code
 */
export function main() {
  const data = lazyHookData();
  return runGuarded("subagent-start", data, () => subagentStartResult(data, projectRoot(loadPayload())));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
