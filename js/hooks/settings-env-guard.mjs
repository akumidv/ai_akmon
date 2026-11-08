/**
 * Claude PreToolUse hook: an agent never writes the `env` of a harness settings file — the
 * JavaScript twin of `hooks/settings-env-guard.py` (ADR 0031/D07, ADR 0020 D01).
 *
 * A harness settings file's `env` block reaches the hook process (M239), and the launcher sets the
 * run's actor there (`AKMON_ACTOR`), so the guard denies an `Edit`, `Write` or `MultiEdit` that
 * changes the parsed `env` of `.claude/settings.json` or `.claude/settings.local.json` (the
 * project's at any depth and the user's) or any `env`/`shell_environment_policy` text of a Codex
 * `.codex/config.toml` — for every actor, D-C203-ACTOR-WRITE. It computes the content after the
 * edit from the file as it is now; an edit that leaves `env` identical passes. The shell half of
 * the rule is in `privilegeEscalationGuardResult` (`hook_core.mjs`), on the `Bash` hook.
 *
 * Both halves are `privilege.no-escalation`. The file list, the texts and the comparison are
 * `common/harness_settings.mjs`'s; this entry point reads the payload and the file and adapts the
 * result. Deny-class, and crash-open like every other Claude entry point (ADR 0013 F3).
 */

import fs from "node:fs";

import { editReason } from "../common/harness_settings.mjs";
import { dictGet, isDict } from "../common/pyvalue.mjs";
import { loadPayload, normalizeTool, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { editTool, HookResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */

/**
 * The file's text now, `null` where there is no file to read (the edit tool fails on one that cannot be read).
 * @param {string} path
 * @returns {string | null}
 */
function _readCurrent(path) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(fs.readFileSync(path));
  } catch {
    return null;
  }
}

/**
 * @param {HookData} data
 * @returns {HookResult | null}
 */
function _decide(data) {
  const payload = loadPayload();
  const toolName = dictGet(payload, "tool_name");
  if (normalizeTool(data, typeof toolName === "string" ? toolName : "") !== editTool(data)) {
    return null;
  }
  const toolInput = dictGet(payload, "tool_input");
  if (!isDict(toolInput)) {
    return null;
  }
  const reason = editReason(toolInput, _readCurrent, data.harnessSettings);
  if (reason === null) {
    return null;
  }
  return new HookResult({ eventName: "PreToolUse", permissionDecision: "deny", permissionReason: reason });
}

/**
 * Entry point: deny an edit that changes the `env` of a harness settings file.
 * @returns {number} the process exit code
 */
export function main() {
  const data = lazyHookData();
  return runGuarded("settings-env-guard", data, () => _decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
