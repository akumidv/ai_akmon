/**
 * Claude PreToolUse wrapper for the akmon commit guard and the shell-route diagnostic — the
 * JavaScript twin of `hooks/git-commit-guard.py` (ADR 0020 D01).
 *
 * The guardrail logic lives in `hook_core.mjs` and returns a vendor-neutral `HookResult`. This
 * entry point only adapts Claude Code's JSON payload/output shape so existing
 * `.claude/settings.json` wiring can keep pointing here.
 *
 * It also carries the unclassified-shell-route diagnostic (C49, ADR-0012/D02). The blind spot it
 * reports is not Codex-specific — Claude's advisories sit on the edit tools, so a write that
 * reaches the filesystem through `Bash` was unreported here while Codex at least said the route
 * may mutate files unseen. This is the hook Claude already runs on every `Bash` call, so the
 * diagnostic costs no additional process on the hottest tool.
 */

import { ACTORS, actorFromEnvironment, runBranchFromEnvironment } from "../common/access_matrix.mjs";
import { dictGet, truthy } from "../common/pyvalue.mjs";
import { attendedFromEnvironment, loadPayload, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import {
  gitCommitGuardResult,
  guardCrashDenyDocument,
  privilegeEscalationGuardResult,
  reportUnclassifiedShellRoute,
} from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */

/**
 * @param {HookData} data
 * @param {import("../common/access_matrix.mjs").Actor} actor who drives the run (`AKMON_ACTOR`)
 * @returns {import("./hook_core.mjs").HookResult | null}
 */
function decide(data, actor) {
  const payload = loadPayload();
  if (dictGet(payload, "tool_name") !== "Bash") {
    return null;
  }
  const sessionId = dictGet(payload, "session_id");
  reportUnclassifiedShellRoute(data, typeof sessionId === "string" ? sessionId : null);
  const rawInput = dictGet(payload, "tool_input");
  const rawCommand = dictGet(truthy(rawInput) ? rawInput : {}, "command", "");
  const command = truthy(rawCommand) ? rawCommand : "";
  const permissionMode = dictGet(payload, "permission_mode");
  const cwd = dictGet(payload, "cwd");
  const directory = typeof cwd === "string" && cwd !== "" ? cwd : null;
  return (
    privilegeEscalationGuardResult(data, command, directory) ??
    gitCommitGuardResult(data, command, {
      permissionMode: typeof permissionMode === "string" ? permissionMode : null,
      directory,
      attended: attendedFromEnvironment(process.env),
      actor,
      runBranch: runBranchFromEnvironment(process.env),
    })
  );
}

/**
 * Entry point: guard privilege-escalation and commit-shaped `Bash` calls.
 * @returns {number} the process exit code
 */
export function main() {
  const data = lazyHookData();
  // Deny-class, and crash-open for a developer (ADR 0013 F3): a crash lets the command through and says so. An
  // autonomous run is denied instead (ADR 0031/D07, D-C203-GUARD-CRASH); the actor is read here, before the
  // matrix or anything else that can crash.
  const actor = actorFromEnvironment(process.env);
  return runGuarded(
    "git-commit-guard",
    data,
    () => decide(data, actor),
    actor === ACTORS.AUTONOMOUS ? () => guardCrashDenyDocument(data) : null,
  );
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
