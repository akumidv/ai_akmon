/**
 * The text akmon's SessionStart hooks put in the model's context, as the always-loaded counter reads
 * it — the JavaScript twin of `hooks/session_start_text.py` (A49, ADR 0012 F18, ADR 0020 D01). The
 * Python module is the spec.
 *
 * Owner decision D-A49-HOOKCOUNT (a) adds the hooks `bin/sync.json` wires on SessionStart —
 * `session-start-agent`, `model-routing` and `learning-reminder` — to the ratchet, so that moving a
 * rule from an imported file into a hook is not a false saving. This module builds each hook's text
 * in-process, from the functions the hook itself calls, and returns it as `Member` rows.
 *
 * A **ceiling**, not the text of one session: every optional line is present. Nothing is read from
 * the host, a transcript or a developer's local config, and nothing is written — the learning
 * reminder is built without touching the record, so counting the hook never counts a session.
 *
 * Data (the C104 convention): `data` is the hook bundle (`lazyHookData()`), passed down as the first
 * parameter.
 */

import { Member } from "../common/always_loaded.mjs";
import { readThresholds, reminderCeiling } from "../common/learning.mjs";
import { aitnaRootName } from "../common/project_root.mjs";
import { exceptionClassName, isFile } from "../common/pyvalue.mjs";
import {
  loadRegistry,
  OverlayError,
  registryPath,
  sessionStartCeiling,
  toolCommandCeiling,
} from "../tools/model_routing/routing.mjs";
import {
  akmonRuntimeRoot,
  sessionLayer,
  sessionStartContext,
  staleGuardrailCeiling,
  subagentStartResult,
} from "./hook_core.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */

/** The Python classes a registry that does not parse, or lacks what the ceiling reads, raises. */
const _UNREADABLE_REGISTRY = new Set([
  "JSONDecodeError",
  "ValueError",
  "KeyError",
  "IndexError",
  "TypeError",
  "AttributeError",
]);

/**
 * The model-routing hook's ceiling for `root`, or null where the hook is silent or cannot be read.
 *
 * Silent without a registry. A registry that does not parse, or lacks what the ceiling reads, is
 * `verify`'s `routing.*` finding to report: the counter says nothing for the hook rather than take
 * the whole verification down with it.
 * @param {HookData} data
 * @param {string} root
 * @returns {string | null}
 */
function _routingText(data, root) {
  const akmon = akmonRuntimeRoot(root);
  if (!isFile(registryPath(akmon))) {
    return null;
  }
  try {
    let registry;
    try {
      registry = loadRegistry(data.agents, akmon, root);
    } catch (error) {
      if (!(error instanceof OverlayError)) {
        throw error;
      }
      // The hook reports a broken overlay in one line and routes nothing; the counter measures the shipped registry.
      registry = loadRegistry(data.agents, akmon);
    }
    const command = toolCommandCeiling(data.agents, `${aitnaRootName(root)}/akmon`, "model_routing/init");
    return sessionStartCeiling(data.agents, registry, command);
  } catch (error) {
    if (!_UNREADABLE_REGISTRY.has(exceptionClassName(error))) {
      throw error;
    }
    return null;
  }
}

/**
 * The SessionStart hook texts for the project at `root`, one member per hook that has something to say.
 *
 * `attended` picks the layer the session-start hook appends: the head layer (the default, the largest
 * audience the cap is checked against) or the unattended one.
 * @param {HookData} data
 * @param {string} root
 * @param {boolean} [attended]
 * @returns {Member[]}
 */
export function sessionStartMembers(data, root, attended = true) {
  const layer = sessionLayer(data, root, attended);
  /** @type {Array<[string, string | null]>} */
  const texts = [
    ["session-start-agent", sessionStartContext(data, root, null, staleGuardrailCeiling(data, root), layer)],
    ["model-routing", _routingText(data, root)],
    ["learning-reminder", reminderCeiling(readThresholds(root, data.learning), data.learning)],
  ];
  return texts.flatMap(([name, text]) => (text === null ? [] : [new Member(`hook: ${name}`, text)]));
}

/**
 * The SubagentStart hook text a delegate carries for the project at `root`: its one member.
 * @param {HookData} data
 * @param {string} root
 * @returns {Member[]}
 */
export function subagentStartMembers(data, root) {
  const text = subagentStartResult(data, root).additionalContext;
  return text === null || text === undefined ? [] : [new Member("hook: subagent-start", text)];
}
