/**
 * Claude PreToolUse wrapper for the akmon commit guard and the shell-route diagnostic — the
 * JavaScript twin of `hooks/git-commit-guard.py` (ADR 0020 D01).
 *
 * The guardrail logic lives in `hook_core.mjs` and returns a vendor-neutral `HookResult`. This
 * entry point only adapts Claude Code's JSON payload/output shape so existing
 * `.claude/settings.json` wiring can keep pointing here.
 *
 * It also carries the browser class of the access matrix (ADR 0032/D07): a `Bash` call that runs
 * `akmon tool browser` and an MCP call of the `akmon-browser` server are denied to a delegated agent (its
 * payload carries `agent_id`, M189) and to an autonomous run, for the matrix's `browser_*` rows.
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
  browserGuardResult,
  gitCommitGuardResult,
  guardCrashDenyDocument,
  privilegeEscalationGuardResult,
  reportUnclassifiedShellRoute,
  strictestResult,
} from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */

/**
 * Whether the call is a delegated agent's: a Claude subagent's every tool event carries `agent_id` (M189).
 * @param {unknown} payload
 * @returns {boolean}
 */
function isDelegated(payload) {
  const agentId = dictGet(payload, "agent_id");
  return typeof agentId === "string" && agentId !== "";
}

/**
 * @param {HookData} data
 * @param {import("../common/access_matrix.mjs").Actor} actor who drives the run (`AKMON_ACTOR`)
 * @param {unknown} payload the `Bash` call
 * @param {{permissionMode: string | null, attended: boolean | null, delegated: boolean}} facts
 * @returns {import("./hook_core.mjs").HookResult | null}
 */
function decideShell(data, actor, payload, { permissionMode, attended, delegated }) {
  const sessionId = dictGet(payload, "session_id");
  reportUnclassifiedShellRoute(data, typeof sessionId === "string" ? sessionId : null);
  const rawInput = dictGet(payload, "tool_input");
  const rawCommand = dictGet(truthy(rawInput) ? rawInput : {}, "command", "");
  const command = truthy(rawCommand) ? rawCommand : "";
  const cwd = dictGet(payload, "cwd");
  const directory = typeof cwd === "string" && cwd !== "" ? cwd : null;
  const escalation = privilegeEscalationGuardResult(data, command, directory);
  if (escalation !== null) {
    return escalation;
  }
  // Every guard reads the command and the strictest decision wins: a git ask must not hide a browser deny.
  return strictestResult([
    gitCommitGuardResult(data, command, {
      permissionMode,
      directory,
      attended,
      actor,
      runBranch: runBranchFromEnvironment(process.env),
    }),
    browserGuardResult(data, "Bash", command, { actor, delegated, permissionMode, attended, directory }),
  ]);
}

/**
 * @param {HookData} data
 * @param {import("../common/access_matrix.mjs").Actor} actor who drives the run (`AKMON_ACTOR`)
 * @returns {import("./hook_core.mjs").HookResult | null}
 */
function decide(data, actor) {
  const payload = loadPayload();
  const toolName = dictGet(payload, "tool_name");
  if (typeof toolName !== "string") {
    return null;
  }
  const rawMode = dictGet(payload, "permission_mode");
  const permissionMode = typeof rawMode === "string" ? rawMode : null;
  const attended = attendedFromEnvironment(process.env);
  const delegated = isDelegated(payload);
  if (toolName === "Bash") {
    return decideShell(data, actor, payload, { permissionMode, attended, delegated });
  }
  // An MCP call of the browser server: the only non-shell call this entry is wired for.
  const cwd = dictGet(payload, "cwd");
  const directory = typeof cwd === "string" && cwd !== "" ? cwd : null;
  return browserGuardResult(data, toolName, "", { actor, delegated, permissionMode, attended, directory });
}

/**
 * Entry point: guard privilege-escalation, commit-shaped and browser-driving calls.
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
