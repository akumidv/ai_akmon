/**
 * The access matrix: what an actor may do, by action class — the JavaScript twin of
 * `common/access_matrix.py` (ADR 0031/D07; ADR 0020 D01). The Python module is the spec.
 *
 * Whether an action passes, asks or is denied is read from the actor (ADR 0025/D01) and the action
 * class; `common/access_matrix.json` holds the answers, keyed by actor and then by action class,
 * each `allow`, `ask` or `deny`. Two other top-level keys are not actor rows: `protected_branches`
 * lists per actor the branches the guard treats like the default branch for that actor (a trailing
 * `*` is a prefix match: `release/*`), and `run_branch_patterns` lists per actor the regular
 * expressions a branch name matches to be that actor's own run branch (ADR 0031/D07,
 * D-C203-RUN-BRANCH). The commit guard (`hooks/hook_core.mjs`) reads it, and so does C173's
 * repertoire. The *parsing* — which command is which action class, which repository and
 * branch it acts on — stays in the guard's code; a style is not a key (D07).
 *
 * The actor is carried by `AKMON_ACTOR`, and an autonomous run's own branch by `AKMON_RUN_BRANCH`,
 * both set by whatever launches the run. A hook's entry point reads them (like attendance, ADR
 * 0025/D06) and passes them down: a pure function never reads the environment. A run with no actor
 * value, or one this module does not know, is a `developer` run.
 * The hook bundle (`hooks/hook_data.mjs`) hands the data file over as `data.accessMatrix`.
 */

import { DataFileError } from "./jsondata.mjs";

/**
 * The shape of `common/access_matrix.json`: actor, then action class, then the outcome; and the
 * `protected_branches` and `run_branch_patterns` keys, actor then branch names or regular expressions.
 * @typedef {Record<string, any>} AccessMatrix
 */

/** The top-level key of the data file that is not an actor row: `{actor: [branch, ...]}`. */
export const PROTECTED_BRANCHES_KEY = "protected_branches";

/** The other top-level key that is not an actor row: `{actor: [regular expression, ...]}`. */
export const RUN_BRANCH_PATTERNS_KEY = "run_branch_patterns";

/** The environment value that names an autonomous run's own branch, set by the launcher (D-C203-RUN-BRANCH). */
export const RUN_BRANCH_ENV = "AKMON_RUN_BRANCH";

/** The environment value that carries the actor, set by the launcher. */
export const ACTOR_ENV = "AKMON_ACTOR";

/** What an action class may be mapped to, from the most permissive to the most restrictive. */
export const OUTCOMES = Object.freeze(["allow", "ask", "deny"]);

/**
 * The action classes of driving the shared browser (ADR 0032/D07): from the developer's own session, and from a
 * delegated agent (a subagent's tool event carries `agent_id`, M189); the actor picks the row.
 */
export const BROWSER_SESSION_CLASS = "browser_session";
export const BROWSER_DELEGATED_CLASS = "browser_delegated";

/** The action class of an AI trailer (`Co-Authored-By`): a floor of the commit guard, denied for every actor. */
export const AI_TRAILER_CLASS = "ai_trailer";

/**
 * The matrix, checked: every actor's `ai_trailer` cell must be `deny`. Returns the data, or throws.
 *
 * The Python twin is `read_data` (`common/access_matrix.py`); a matrix that softens the trailer floor
 * is broken, not a choice, so it raises {@link DataFileError} rather than being read.
 * @param {AccessMatrix} data the parsed `common/access_matrix.json`
 * @returns {AccessMatrix}
 */
export function checkTrailerFloor(data) {
  for (const [actor, row] of Object.entries(data)) {
    if (actor === PROTECTED_BRANCHES_KEY || actor === RUN_BRANCH_PATTERNS_KEY) {
      continue;
    }
    const cell = row !== null && typeof row === "object" ? row[AI_TRAILER_CLASS] : undefined;
    if (cell !== "deny") {
      throw new DataFileError(
        `access matrix entry '${actor}'/'${AI_TRAILER_CLASS}' is '${cell}'; an AI trailer is denied for every actor`,
      );
    }
  }
  return data;
}

/**
 * The matrix, checked: `protected_branches` maps every actor to a list of branch names. Returns the
 * data, or throws {@link DataFileError} (the twin of `check_protected_branches`).
 * @param {AccessMatrix} data the parsed `common/access_matrix.json`
 * @returns {AccessMatrix}
 */
export function checkProtectedBranches(data) {
  const protectedBranches = data[PROTECTED_BRANCHES_KEY];
  if (protectedBranches === null || typeof protectedBranches !== "object" || Array.isArray(protectedBranches)) {
    throw new DataFileError(
      `access matrix '${PROTECTED_BRANCHES_KEY}' is ${JSON.stringify(protectedBranches)}; expected a mapping`,
    );
  }
  for (const actor of ["developer", "autonomous"]) {
    const names = Object.hasOwn(protectedBranches, actor) ? protectedBranches[actor] : undefined;
    if (!Array.isArray(names) || !names.every((name) => typeof name === "string" && name !== "")) {
      throw new DataFileError(
        `access matrix '${PROTECTED_BRANCHES_KEY}'/'${actor}' is ${JSON.stringify(names)}; expected a list of branch names`,
      );
    }
  }
  return data;
}

/**
 * The matrix, checked: `run_branch_patterns` maps every actor to a list of regular expressions. Returns
 * the data, or throws {@link DataFileError} (the twin of `check_run_branch_patterns`).
 * @param {AccessMatrix} data the parsed `common/access_matrix.json`
 * @returns {AccessMatrix}
 */
export function checkRunBranchPatterns(data) {
  const patterns = data[RUN_BRANCH_PATTERNS_KEY];
  if (patterns === null || typeof patterns !== "object" || Array.isArray(patterns)) {
    throw new DataFileError(
      `access matrix '${RUN_BRANCH_PATTERNS_KEY}' is ${JSON.stringify(patterns)}; expected a mapping`,
    );
  }
  for (const actor of ["developer", "autonomous"]) {
    const expressions = Object.hasOwn(patterns, actor) ? patterns[actor] : undefined;
    if (!Array.isArray(expressions) || !expressions.every((item) => typeof item === "string" && item !== "")) {
      throw new DataFileError(
        `access matrix '${RUN_BRANCH_PATTERNS_KEY}'/'${actor}' is ${JSON.stringify(expressions)}; expected a list of regular expressions`,
      );
    }
    for (const expression of expressions) {
      try {
        new RegExp(expression);
      } catch (error) {
        throw new DataFileError(
          `access matrix '${RUN_BRANCH_PATTERNS_KEY}'/'${actor}' holds '${expression}', which is not a regular expression (${/** @type {Error} */ (error).message})`,
        );
      }
    }
  }
  return data;
}

/**
 * The matrix, checked whole: the trailer floor, the protected branches and the run-branch patterns.
 * Returns the data, or throws.
 * @param {AccessMatrix} data the parsed `common/access_matrix.json`
 * @returns {AccessMatrix}
 */
export function checkData(data) {
  return checkRunBranchPatterns(checkProtectedBranches(checkTrailerFloor(data)));
}

/**
 * Who drives a run, fixed for the run (ADR 0025/D01). The `guided` actor is A76's, not yet here.
 * @typedef {"developer" | "autonomous"} Actor
 */

/** The actors this module knows. */
export const ACTORS = Object.freeze({ DEVELOPER: "developer", AUTONOMOUS: "autonomous" });

/**
 * The actor `environ` carries; `developer` where the value is absent or unknown.
 * @param {Record<string, string | undefined>} environ a hook entry point passes `process.env`
 * @returns {Actor}
 */
export function actorFromEnvironment(environ) {
  const value = environ[ACTOR_ENV];
  return value === ACTORS.AUTONOMOUS ? ACTORS.AUTONOMOUS : ACTORS.DEVELOPER;
}

/**
 * The run branch `environ` names, or `null` where the value is absent or empty.
 * @param {Record<string, string | undefined>} environ a hook entry point passes `process.env`
 * @returns {string | null}
 */
export function runBranchFromEnvironment(environ) {
  const value = environ[RUN_BRANCH_ENV];
  return value === undefined || value === "" ? null : value;
}

/**
 * What `actor` may do for `actionClass`: `allow`, `ask` or `deny`.
 *
 * A row, a class or a value the matrix lacks raises {@link DataFileError}: the matrix is a
 * dependency of the guard, and a hole in it must not read as permission.
 * @param {AccessMatrix} data the parsed `common/access_matrix.json`
 * @param {Actor} actor
 * @param {string} actionClass
 * @returns {string}
 */
export function outcome(data, actor, actionClass) {
  const row = Object.hasOwn(data, actor) ? data[actor] : null;
  if (row === null || typeof row !== "object" || !Object.hasOwn(row, actionClass)) {
    throw new DataFileError(`access matrix has no entry for actor '${actor}', action '${actionClass}'`);
  }
  const value = row[actionClass];
  if (!OUTCOMES.includes(value)) {
    throw new DataFileError(
      `access matrix entry '${actor}'/'${actionClass}' is '${value}'; the outcomes are ${OUTCOMES.join(", ")}`,
    );
  }
  return value;
}

/**
 * The branches `actor` is kept off like the default branch (`develop` for an autonomous run).
 * @param {AccessMatrix} data the parsed `common/access_matrix.json`
 * @param {Actor} actor
 * @returns {string[]}
 */
export function protectedBranches(data, actor) {
  const protectedBranches = Object.hasOwn(data, PROTECTED_BRANCHES_KEY) ? data[PROTECTED_BRANCHES_KEY] : null;
  const names =
    protectedBranches !== null && typeof protectedBranches === "object" && Object.hasOwn(protectedBranches, actor)
      ? protectedBranches[actor]
      : null;
  if (!Array.isArray(names)) {
    throw new DataFileError(`access matrix has no entry for actor '${actor}' in '${PROTECTED_BRANCHES_KEY}'`);
  }
  return names;
}

/**
 * Whether `branch` is one of `names`: an exact name, or a prefix for a name ending in `*`.
 * @param {readonly string[]} names
 * @param {string} branch
 * @returns {boolean}
 */
export function isProtectedBranch(names, branch) {
  return names.some((name) => (name.endsWith("*") ? branch.startsWith(name.slice(0, -1)) : branch === name));
}

/**
 * Whether `branch` is one `actor` may write: a developer's every branch, an autonomous run's own.
 *
 * An autonomous run's own branch is the `runBranch` the launcher named (`AKMON_RUN_BRANCH`), exactly;
 * with none named, a branch the actor's `run_branch_patterns` match (`agent/C203-...`). A developer has
 * no run branch, so the question does not narrow what a developer may write.
 * @param {AccessMatrix} data the parsed `common/access_matrix.json`
 * @param {Actor} actor
 * @param {string} branch
 * @param {string | null} runBranch
 * @returns {boolean}
 */
export function isOwnBranch(data, actor, branch, runBranch) {
  if (actor !== ACTORS.AUTONOMOUS) {
    return true;
  }
  if (runBranch !== null) {
    return branch === runBranch;
  }
  return data[RUN_BRANCH_PATTERNS_KEY][actor].some((/** @type {string} */ pattern) => new RegExp(pattern).test(branch));
}
