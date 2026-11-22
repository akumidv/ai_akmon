/**
 * The audience a session's starting context is delivered to, and the layer each one reads — the
 * JavaScript twin of `common/audience.py` (A49, ADR 0020 D01). The Python module is the spec.
 *
 * akmon's rules reach three readers. The floor — the guardrail, the code rules, the profiles — goes
 * to everyone through the entry file. Two layers go through hooks instead, so each reaches only its
 * audience (`docs/design/context-audiences.md`):
 *
 * - the **head layer** (`rules/collaboration.md` and `rules/templates.md`): the session an owner
 *   attends — how it talks with the owner;
 * - the **unattended layer** (`rules/unattended.md`): a delegate, and a session no owner attends —
 *   how it finishes without stopping to ask.
 *
 * The SessionStart hook delivers one of the two to a session, on every `source` (compaction drops
 * text given only at startup, M246); the SubagentStart hook delivers the unattended layer to a
 * delegate. {@link isAttended} decides which one a session gets (D-A49-SELECTOR (a)); {@link layerText}
 * reads it.
 *
 * Nothing here reads the process environment: a hook entry point passes `process.env` once. The file
 * lists are `common/audience.json`'s, shared by both twins; the hook bundle hands them over as
 * `data.audience`.
 */

import { ACTORS, actorFromEnvironment } from "./access_matrix.mjs";
import { isAttended as sessionAttended, isSecondOpinion } from "./learning.mjs";
import { dictItem, pyPath, readText } from "./pyvalue.mjs";

/** @typedef {import("./learning.mjs").LearningData} LearningData */

/**
 * The shape of `common/audience.json`.
 * @typedef {object} AudienceData
 * @property {string[]} attended_files the head layer's standard files, tree-relative
 * @property {string[]} unattended_files the unattended layer's standard files, tree-relative
 * @property {string} separator what joins the files of a layer
 */

/**
 * Whether the session is one an owner attends, so it gets the head layer (D-A49-SELECTOR (a)).
 *
 * All three must hold: the actor is `developer` (an absent or unknown value reads as developer); the
 * harness has not said the session is unattended (`CLAUDE_CODE_SESSION_ATTENDED` is not `0`, M199); and
 * the run is not a second opinion (`AKMON_SECOND_OPINION` unset). Any other session gets the
 * unattended layer.
 * @param {LearningData} learning the learning data, which names the two variables
 * @param {Record<string, string | undefined>} environ a hook entry point passes `process.env`
 * @returns {boolean}
 */
export function isAttended(learning, environ) {
  return (
    actorFromEnvironment(environ) === ACTORS.DEVELOPER &&
    sessionAttended(environ, learning) &&
    !isSecondOpinion(environ, learning)
  );
}

/**
 * The standard files of the layer an `attended` session gets, as tree-relative paths.
 * @param {AudienceData} data
 * @param {boolean} attended
 * @returns {string[]}
 */
export function layerFiles(data, attended) {
  return [...dictItem(data, attended ? "attended_files" : "unattended_files")];
}

/**
 * The text of the layer an `attended` session gets, read from the standard tree at `treeRoot`.
 *
 * `treeRoot` is the tree the hook executes from: the mount, the package's embedded tree, or akmon's
 * own checkout — each ships the rule files beside its hooks, so the layer does not depend on a
 * materialized copy. Throws an `OSError` when a file of the layer is missing from the tree.
 * @param {AudienceData} data
 * @param {string} treeRoot
 * @param {boolean} attended
 * @returns {string}
 */
export function layerText(data, treeRoot, attended) {
  const texts = layerFiles(data, attended).map((relative) => readText(pyPath(treeRoot, relative)).replace(/\n+$/, ""));
  return texts.join(dictItem(data, "separator"));
}
