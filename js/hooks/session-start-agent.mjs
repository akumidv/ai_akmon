/**
 * Claude SessionStart wrapper for the akmon active-agent reminder and the audience's layer — the JavaScript twin of
 * `hooks/session-start-agent.py` (ADR 0020 D01).
 *
 * The reminder logic lives in `hook_core.mjs` and returns a vendor-neutral `HookResult`. This
 * entry point only adapts Claude Code's JSON payload/output shape so existing
 * `.claude/settings.json` wiring can keep pointing here.
 */

import { isAttended } from "../common/audience.mjs";
import { dictGet, pyError, pyPath, pyTypeName, truthy } from "../common/pyvalue.mjs";
import { loadPayload, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { sessionLayer, sessionStartResult } from "./hook_core.mjs";
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
  return runGuarded("session-start-agent", data, () => {
    const payload = loadPayload();
    const sessionId = dictGet(payload, "session_id");
    const root = sessionRoot(payload);
    // The environment is read here, once, and passed down. The audience's layer rides on every `source`:
    // compaction drops what was given only at startup (M246).
    const layer = sessionLayer(data, root, isAttended(data.learning, process.env));
    return sessionStartResult(data, root, typeof sessionId === "string" ? sessionId : null, layer);
  });
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
