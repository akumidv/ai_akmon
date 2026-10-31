#!/usr/bin/env node
/**
 * Claude SessionStart hook for the learning-run reminder — the JavaScript twin of
 * `hooks/learning-reminder.py` (C177, ADR 0026 D07; ADR 0020 D01). The Python module is the spec:
 * the same answers, the same texts, the same exit code and the same stdout and stderr.
 *
 * Records the session in the project's learning record (`<dev root>/local/learning.json`) and,
 * once enough sessions or days have passed since the learning agent's last run, tells the model (to
 * say so once, in its first reply) and the owner to run the `learning` skill. Silent when nothing
 * is due, and never blocking: a failure goes through the shared crash guard, which exits 0.
 *
 * The record, the thresholds and the texts live in `common/learning.mjs` and its data file; this
 * entry point reads the clock, the payload, the thresholds and the record once, and adapts the
 * result. The Codex route (`codex-hook.mjs learning-reminder`) calls the same functions.
 *
 * Data (the C104 convention): `main` reads nothing itself; the texts and the threshold defaults
 * are `data.learning` of `lazyHookData()`, read on first access, so a broken `learning.json` fails
 * this hook and the Codex route only — as the Python's `learning.read_data()` does.
 */

import { dictGet } from "../common/pyvalue.mjs";
import { readThresholds, recordAndRemind, sessionEvent, statePath } from "../common/learning.mjs";
import { loadPayload, locatedProjectRoot, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { HookResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("../common/learning.mjs").LearningData} LearningData */
/** @typedef {import("../common/learning.mjs").Thresholds} Thresholds */
/** @typedef {import("./claude_adapter.mjs").Payload} Payload */

/**
 * The session start this payload names, as the learning record sees it, or null for a second opinion.
 *
 * `environ` is the hook process's environment, read once at the entry point: a second-opinion run
 * is neither recorded nor reminded, an unattended session (`claude -p`) is recorded but not reminded.
 * @param {Payload} payload
 * @param {Record<string, string | undefined>} environ
 * @param {LearningData} data
 * @returns {import("../common/learning.mjs").SessionEvent | null}
 */
export function payloadEvent(payload, environ, data) {
  const sessionId = dictGet(payload, "session_id");
  const source = dictGet(payload, "source");
  return sessionEvent(
    typeof sessionId === "string" ? sessionId : null,
    typeof source === "string" ? source : null,
    environ,
    data,
  );
}

/**
 * The SessionStart result for this session: the learning reminder, or null when nothing is due.
 *
 * `event` is {@link payloadEvent}'s answer; null (a second-opinion run) records and says nothing.
 *
 * Runtime classification: operational
 * Rationale: it authors no guardrail rule. It records that a session happened and delivers a
 * reminder the learning agent's charter (ADR 0026/D07) already states, on the two channels an
 * owner-addressed notice uses: `additionalContext` for the model, `systemMessage` for the owner.
 * It is a public `*Result` outside `hook_core`, so ADR-0012/D07's join covers neither it nor the
 * thresholds it applies (same standing as `modelRoutingResult`).
 * @param {import("../common/learning.mjs").SessionEvent | null} event
 * @param {string} root
 * @param {LearningData} data
 * @param {Thresholds} thresholds
 * @param {Date} now
 * @returns {HookResult | null}
 */
export function learningReminderResult(event, root, data, thresholds, now) {
  if (event === null) {
    return null;
  }
  const reminder = recordAndRemind(statePath(root, data), event, thresholds, now, data);
  if (reminder === null) {
    return null;
  }
  const [forModel, forOwner] = reminder;
  return new HookResult({ eventName: "SessionStart", additionalContext: forModel, systemMessage: forOwner });
}

/**
 * @param {import("./hook_data.mjs").HookData} data
 * @returns {HookResult | null}
 */
function _decide(data) {
  const payload = loadPayload();
  const root = locatedProjectRoot(payload);
  if (root === null) {
    // No project root: the record has no local layer to live in, so nothing is written (ADR 0022 D09).
    return null;
  }
  const event = payloadEvent(payload, process.env, data.learning);
  return learningReminderResult(event, root, data.learning, readThresholds(root, data.learning), new Date());
}

/**
 * Entry point: record the session and emit the learning reminder when one is due.
 * @returns {number} The process exit code.
 */
export function main() {
  const data = lazyHookData();
  // Never block session start: a crash is reported (stderr + the owner's notice), exit 0.
  return runGuarded("learning-reminder", data, () => _decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
