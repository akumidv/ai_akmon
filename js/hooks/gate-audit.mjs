#!/usr/bin/env node
/**
 * Claude Stop wrapper for the akmon gate-audit forcing function (C25) — the JavaScript twin of
 * `hooks/gate-audit.py` (ADR 0020 D01). The Python module is the spec: the same answers, the
 * same texts, the same exit code and the same stdout and stderr.
 *
 * It runs on **Stop**, where the turn's own text is already in the payload
 * (`last_assistant_message`, M87), counts the structural items under the role's
 * Findings/Options sections, and — at or above the registry's count floor — holds the turn once
 * with the one request the flows make there: run the `audit` pass, or say the skip out loud.
 * It holds a turn once per gate (the C36 marker is keyed by role and a digest of the counted
 * section text) and never a turn
 * that already is the answer to a held one (`stop_hook_active`). The counting and the request
 * live in `tools/model_routing/routing.mjs`.
 *
 * Data (the C104 convention): `main` reads nothing itself; `lazyHookData()` hands each shared
 * file over on first access, so a broken `gate.json` fails this hook only when a registry exists
 * and a role is declared, as the Python's does. The decision takes the bundle as `data`.
 *
 * Twin notes:
 * - the payload is arbitrary JSON: a field is read with `dictGet`, tested with `truthy` and
 *   `isinstance` (`typeof`) as the Python does, and `payload["cwd"]` that is truthy but not a
 *   string is the `TypeError` `Path()` raises;
 * - the three reads that feed the request (registry, role, local config) keep the Python's
 *   order, so the exception a broken tree raises is the same one.
 */

import { findProjectRoot } from "../common/project_root.mjs";
import { dictGet, isFile, pyError, pyPath, pyStrip, truthy } from "../common/pyvalue.mjs";
import {
  activeRole,
  gateAuditOnce,
  gateAuditRequest,
  loadRegistry,
  readLocalConfig,
  registryPath,
  toolCommand,
} from "../tools/model_routing/routing.mjs";
import { loadPayload, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { HookResult, akmonRuntimeRoot, assertEncodablePath, runtimeRootDisplay } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */
/** @typedef {any} Json */

/**
 * The Stop decision for this turn: hold it for the gate audit, or null to let it end.
 *
 * Runtime classification: operational
 * Rationale: it authors no guardrail rule of its own. The count floors are registry data and
 * the gate is written in review-flow and design-flow; this delivers them at the moment the
 * role hands off. It is a public `*Result` outside `hook_core`, so ADR-0012/D07's join
 * covers neither it nor the floors it restates (same standing as `modelRoutingResult`).
 * @param {HookData} data
 * @param {string} root
 * @param {Json} payload
 * @returns {HookResult | null}
 */
export function gateAuditResult(data, root, payload) {
  if (truthy(dictGet(payload, "stop_hook_active"))) {
    return null; // this turn is already the answer to a held turn — never hold it again
  }
  const message = dictGet(payload, "last_assistant_message");
  if (typeof message !== "string" || pyStrip(message) === "") {
    return null;
  }
  const akmon = akmonRuntimeRoot(root);
  if (!isFile(registryPath(akmon))) {
    return null; // a tree from before model routing has no floors to enforce
  }
  const registry = loadRegistry(data.agents, akmon, root);
  const role = activeRole(dictGet(payload, "transcript_path"));
  const config = readLocalConfig(data.agents, root);
  const gatePack = toolCommand(data.agents, runtimeRootDisplay(root), "model_routing/gate_pack");
  const request = gateAuditRequest(data.gate, data.agents, registry, config, role, message, gatePack);
  if (request === null) {
    return null;
  }
  if (!gateAuditOnce(data.gate, data.markers, role, message, dictGet(payload, "session_id"))) {
    return null; // this gate was already asked about; a second hold would be a loop
  }
  return new HookResult({ eventName: "Stop", decision: "block", reason: request });
}

/**
 * The project root the payload's `cwd` (else `$CLAUDE_PROJECT_DIR`, else the process's) is in.
 * @param {Json} payload
 * @returns {string}
 */
function _projectRoot(payload) {
  let cwd = dictGet(payload, "cwd");
  if (!truthy(cwd)) {
    cwd = process.env.CLAUDE_PROJECT_DIR;
  }
  if (!truthy(cwd)) {
    cwd = process.cwd();
  }
  if (typeof cwd !== "string") {
    throw pyError("TypeError", "argument should be a str or an os.PathLike object where __fspath__ returns a str");
  }
  assertEncodablePath(cwd); // `Path(cwd).resolve()` refuses a NUL or a lone surrogate
  return findProjectRoot(pyPath(cwd));
}

/**
 * @param {HookData} data
 * @returns {HookResult | null}
 */
function _decide(data) {
  const payload = loadPayload();
  return gateAuditResult(data, _projectRoot(payload), payload);
}

/**
 * Entry point: hold the turn once when a role passed its gate's count floor.
 * @returns {number} The process exit code.
 */
export function main() {
  const data = lazyHookData();
  // Crash-open through the shared guard: a failure here must never wedge a session's turn.
  return runGuarded("gate-audit", data, () => _decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
