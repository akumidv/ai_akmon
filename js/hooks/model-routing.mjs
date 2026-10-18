#!/usr/bin/env node
/**
 * Claude wrapper for akmon model routing — orchestrator detection + status line — the
 * JavaScript twin of `hooks/model-routing.py` (ADR 0020 D01). The Python module is the spec:
 * the same answers, the same texts, the same exit code and the same stdout and stderr.
 *
 * Runs on **SessionStart** and **UserPromptSubmit**. Both read the session transcript
 * (`transcript_path` in the payload) to detect the model the main chain is actually running
 * on, map it to an alias, and — when it differs from the recorded orchestrator — recompute the
 * binding and regenerate the `k_*` subagent definitions so delegates follow the live model.
 * The orchestrator itself is only *detected* here, never overridden.
 *
 * - **SessionStart:** fresh config → status line (binding + self-check, plus the corridor
 *   warning); missing or stale config → the init instruction.
 * - **UserPromptSubmit:** silent unless the orchestrator changed (a one-line notice) or the
 *   context fill reached a new pressure level (design §12).
 *
 * Owner-addressed output goes out on two channels (requirement 11): `additionalContext` and
 * `systemMessage`; the context-pressure reminder is `systemMessage` only. Logic lives in
 * `tools/model_routing/routing.mjs`; this entry point only adapts the payload.
 *
 * Data (the C104 convention): `main` reads nothing itself; `lazyHookData()` hands each shared
 * file over on first access. `common/markers.json` is reached only for an identified session,
 * as the Python reaches `claim_diagnostic_marker` only then.
 *
 * Twin notes:
 * - `hook_event_name` is arbitrary JSON, echoed as `hookEventName` when it is not
 *   `SessionStart`: `5` and `["x"]` are echoed, `[]` and `{}` are falsy and mean `SessionStart`;
 * - the settings files are read as strict UTF-8 text and parsed by `jsonLoads` — Python's
 *   `json.loads`, the `NaN`/`Infinity`/`-Infinity` literals included (C115): a `JSONDecodeError`
 *   skips the file, any other failure (a `RecursionError` on a very deep document) is a crash;
 *   only `model` is read.
 */

import { aitnaRootName, findProjectRoot } from "../common/project_root.mjs";
import { JSONDecodeError, jsonLoads } from "../common/pyjson.mjs";
import { dictGet, isDict, isDir, isFile, pyEq, pyError, pyPath, readText, truthy } from "../common/pyvalue.mjs";
import {
  briefWarning,
  contextPressureNotice,
  detectOrchestrator,
  initInstruction,
  lastMainTurn,
  loadRegistry,
  rebindNotice,
  rebindTo,
  readLocalConfig,
  registryPath,
  settingsProbeNames,
  staleness,
  statusLines,
  suppressedRebindWarning,
  toolCommand,
} from "../tools/model_routing/routing.mjs";
import { loadPayload, runAsEntryPoint, runGuarded } from "./claude_adapter.mjs";
import { HookResult, akmonRuntimeRoot, assertEncodablePath, runtimeRootDisplay } from "./hook_core.mjs";
import { lazyHookData } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */
/** @typedef {any} Json */

/**
 * The `model` a project's Claude settings file names, or null.
 * @param {HookData} data
 * @param {string} projectRoot
 * @returns {string | null}
 */
function _settingsModel(data, projectRoot) {
  for (const name of settingsProbeNames(data.agents)) {
    const path = pyPath(projectRoot, ".claude", name);
    if (!isFile(path)) {
      continue;
    }
    let settings;
    try {
      // `json.loads`, not `JSON.parse`: a `NaN` or `Infinity` is JSON to the twin (C115).
      settings = jsonLoads(readText(path));
    } catch (error) {
      if (error instanceof JSONDecodeError) {
        continue;
      }
      throw error;
    }
    const model = isDict(settings) ? dictGet(settings, "model") : null;
    if (typeof model === "string" && model) {
      return model;
    }
  }
  return null;
}

/**
 * Orchestrator-detection + status-line result for this hook event, or null when silent.
 *
 * Runtime classification: operational
 * Rationale: it authors no guardrail rule. It detects the model the session runs on, rebinds the
 * delegates and delivers the status line, the init instruction and the corridor warning; the tier
 * floor those warnings restate is owned by `delegation.tier-floor`, and delivery is not
 * ownership. It is a public `*Result` outside `hook_core`, so the join's scope excludes it
 * while ADR-0012/D07's obligation on owner-visible callables does not.
 * @param {HookData} data
 * @param {string} root
 * @param {Json} payload
 * @returns {HookResult | null}
 */
export function modelRoutingResult(data, root, payload) {
  const akmon = akmonRuntimeRoot(root);
  if (!isFile(registryPath(akmon))) {
    // Silence is the right answer for a pin that predates model routing: such a tree has no
    // routing tools at all, and there is nothing to report. It is the wrong answer for a
    // registry that has gone *missing* from a tree that does carry them — a broken carrier
    // takes the status line and the delegation log out of every session, at exit 0 with an
    // empty stderr. So the two states are separated rather than swallowed together (C77).
    if (isDir(pyPath(akmon, "tools", "model_routing"))) {
      process.stderr.write(
        `akmon model-routing hook: ${akmon}/tools/model_routing exists but registry.json ` +
          "is missing — model routing is silent for this session\n",
      );
    }
    return null;
  }

  const registry = loadRegistry(data.agents, akmon, root);
  let config = readLocalConfig(data.agents, root);
  const hookEvent = dictGet(payload, "hook_event_name");
  const event = truthy(hookEvent) ? hookEvent : "SessionStart";

  const aitna = aitnaRootName();
  // Recovery instructions must name a command that works in the tree this project actually has:
  // the mount's script when one exists, `akmon tool` from the installed package, whose literal
  // path would carry the install layout (C77, ADR-0020/D06). Naming the mount unconditionally
  // used to hand a package-mode session a path that is not there.
  const initCommand = toolCommand(data.agents, runtimeRootDisplay(root), "model_routing/init");
  // An overlay `briefs` key matching no agent makes every regeneration lossy, so the
  // rebind is refused rather than run — and the reason is stated instead of swallowed (C50).
  const briefWarn = briefWarning(data.agents, registry, aitna);

  // Detect the model the main chain actually runs on (authoritative over settings) and
  // rebind the subagents when it moved. Needs an existing config for the `available`
  // ladder + opt-ins; first-time setup stays explicit (the init instruction below).
  // One transcript read per run (A19): detection and the pressure notice below share it.
  const transcript = dictGet(payload, "transcript_path");
  const turn = lastMainTurn(transcript);
  const detected = detectOrchestrator(transcript, dictGet(config, "available"), { turn });
  const switched = truthy(detected) && truthy(config) && !pyEq(detected, dictGet(config, "orchestrator"));
  const rebound = switched && briefWarn === null;
  if (rebound) {
    rebindTo(data.agents, root, registry, config, detected);
    config = readLocalConfig(data.agents, root); // reload the freshly-written binding
  }

  const sessionId = dictGet(payload, "session_id");
  const pressure = contextPressureNotice(data.agents, registry, transcript, sessionId, { turn });
  // `common/markers.json` is read only for an identified session (see the header).
  const suppressed = suppressedRebindWarning(
    truthy(sessionId) ? data.markers : /** @type {any} */ (null),
    switched ? briefWarn : null,
    detected,
    sessionId,
  );

  if (event !== "SessionStart") {
    // Per-turn: silent unless a switch or a new context-pressure level just landed — zero
    // token cost otherwise. A rebind is owner-addressed → dual-channel (requirement 11);
    // the pressure reminder goes to the owner only. A suppressed rebind speaks up here too:
    // the delegates stay pinned to the old model until the overlay is fixed, which the owner
    // has to know at the moment it happens.
    const dual = [...(rebound ? rebindNotice(data.agents, config, registry) : []), ...suppressed];
    if (dual.length === 0 && pressure.length === 0) {
      return null;
    }
    return new HookResult({
      eventName: event,
      additionalContext: dual.join("\n") || null,
      systemMessage: [...dual, ...pressure].join("\n"),
    });
  }

  // SessionStart: the transcript (when it named a model) is ground truth, so suppress the
  // weaker settings-model staleness signal once we have detected + bound to it.
  const settingsModel = truthy(detected) ? null : _settingsModel(data, root);
  const reason = staleness(data.agents, config, registry, settingsModel);
  const overlay = briefWarn ? [briefWarn] : [];
  if (reason !== null) {
    const lines = [...initInstruction(data.agents, reason, initCommand), ...overlay];
    return new HookResult({
      eventName: "SessionStart",
      additionalContext: lines.join("\n"),
      systemMessage: [lines[0], ...overlay, ...pressure].join("\n"),
    });
  }
  const lines = [...statusLines(data.agents, config, registry, initCommand), ...overlay];
  // Owner-addressed subset: the corridor warning, the fact of a rebind and — for the owner
  // alone — the context-pressure reminder at either level (its info line carries ℹ, not ⚠);
  // the steady-state status line itself stays context-only so the UI is quiet when healthy.
  const owner = [...lines.filter((line) => line.startsWith("⚠")), ...pressure];
  if (rebound) {
    owner.unshift(rebindNotice(data.agents, config, registry)[0]);
  }
  return new HookResult({
    eventName: "SessionStart",
    additionalContext: lines.join("\n"),
    systemMessage: owner.length > 0 ? owner.join("\n") : null,
  });
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
  return modelRoutingResult(data, _projectRoot(payload), payload);
}

/**
 * Entry point: detect orchestrator drift and emit the status line, never blocking.
 * @returns {number} The process exit code.
 */
export function main() {
  const data = lazyHookData();
  // Never block a turn: a crash is reported (stderr + the owner's notice), exit 0.
  return runGuarded("model-routing", data, () => _decide(data));
}

if (runAsEntryPoint(import.meta.url)) {
  process.exitCode = main();
}
