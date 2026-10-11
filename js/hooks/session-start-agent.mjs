/**
 * Claude SessionStart wrapper for the akmon active-agent reminder — the JavaScript twin of
 * `hooks/session-start-agent.py` (ADR 0020 D01).
 *
 * The reminder logic lives in `hook_core.mjs` and returns a vendor-neutral `HookResult`. This
 * entry point only adapts Claude Code's JSON payload/output shape so existing
 * `.claude/settings.json` wiring can keep pointing here.
 */

import { dictGet, pyError, pyPath, pyTypeName, truthy } from "../common/pyvalue.mjs";
import { loadPayload, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { sessionStartResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./claude_adapter.mjs").Payload} Payload */

/**
 * `Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd()))` — the
 * payload's `cwd` is whatever JSON value it is, and `Path` refuses anything but a string.
 * @param {Payload} payload
 * @returns {string}
 */
function sessionRoot(payload) {
  const declared = dictGet(payload, "cwd");
  const cwd = truthy(declared) ? declared : process.env.CLAUDE_PROJECT_DIR || process.cwd();
  if (typeof cwd !== "string") {
    throw pyError(
      "TypeError",
      `argument should be a str or an os.PathLike object where __fspath__ returns a str, not '${pyTypeName(cwd)}'`,
    );
  }
  return pyPath(cwd);
}

/**
 * Entry point: emit the active-agent reminder, never blocking session start.
 * @returns {number} the process exit code
 */
export function main() {
  const data = lazyHookData();
  // Never block session start: a crash is reported (stderr + the owner's notice), exit 0.
  return runGuarded("session-start-agent", data, () => sessionStartResult(data, sessionRoot(loadPayload())));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
