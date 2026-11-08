#!/usr/bin/env node
/**
 * Claude UserPromptSubmit hook for the work style — the JavaScript twin of `hooks/work-style.py`
 * (ADR 0031/D03; ADR 0020 D01). The Python module is the spec: the same answers, the same texts,
 * the same exit code and the same stdout and stderr.
 *
 * When the owner types `/style delegating` or `/style controlling` it records that style for the
 * session in `<dev root>/.local/work-sessions.json` and tells the model — and the owner — what was
 * recorded and that a switch inside an athlos takes effect at the next park boundary. A value that
 * names no style returns the allowed values and records nothing. Any other prompt: silent, no
 * write. The agent cannot produce a user prompt, so only the owner can switch (a style never
 * widens a permission, D01).
 *
 * The record, the styles and the texts live in `common/work_style.mjs` and its data file; this
 * entry point reads the payload and the data once and adapts the result. The Codex route
 * (`codex-hook.mjs work-style`) calls the same function. Never blocking: a failure goes through the
 * shared crash guard, which exits 0.
 *
 * Data (the C104 convention): `main` reads nothing itself; the texts are `data.workStyle` of
 * `lazyHookData()`, read on first access.
 */

import { dictGet } from "../common/pyvalue.mjs";
import { recordAndReply } from "../common/work_style.mjs";
import { loadPayload, locatedProjectRoot, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { HookResult } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("../common/work_style.mjs").WorkStyleData} WorkStyleData */

/**
 * The UserPromptSubmit result for a typed `prompt`, or null when it is not a `/style` command.
 *
 * Both channels carry the reply (requirement 11): the model acts on it and the owner who typed the
 * command sees what was recorded.
 *
 * Runtime classification: operational
 * Rationale: it authors no guardrail rule. It captures the owner's typed style switch (ADR
 * 0031/D03) and confirms it; a style never widens a permission (D01), so nothing a hook enforces
 * depends on it. It is a public `*Result` outside `hook_core`, so ADR-0012/D07's join covers
 * neither it nor the values it records (same standing as `modelRoutingResult`).
 * @param {string} root
 * @param {string | null} sessionId
 * @param {string} prompt
 * @param {WorkStyleData} data
 * @returns {HookResult | null}
 */
export function workStyleResult(root, sessionId, prompt, data) {
  const reply = recordAndReply(root, sessionId, prompt, data);
  if (reply === null) {
    return null;
  }
  return new HookResult({ eventName: "UserPromptSubmit", additionalContext: reply, systemMessage: reply });
}

/**
 * @param {import("./hook_data.mjs").HookData} data
 * @returns {HookResult | null}
 */
function _decide(data) {
  const payload = loadPayload();
  const prompt = dictGet(payload, "prompt");
  if (typeof prompt !== "string") {
    return null;
  }
  const root = locatedProjectRoot(payload);
  if (root === null) {
    // No project root: the record has no local layer to live in, so nothing is written (ADR 0022 D09).
    return null;
  }
  const sessionId = dictGet(payload, "session_id");
  return workStyleResult(
    root,
    typeof sessionId === "string" && sessionId !== "" ? sessionId : null,
    prompt,
    data.workStyle,
  );
}

/**
 * Entry point: record a typed `/style` switch for the session, silent on every other prompt.
 * @returns {number} The process exit code.
 */
export function main() {
  const data = lazyHookData();
  // Never block a turn: a crash is reported (stderr + the owner's notice), exit 0.
  return runGuarded("work-style", data, () => _decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
