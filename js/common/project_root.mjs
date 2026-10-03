/**
 * The one owner of "where is the project root" and "what the dev layer is called".
 * The JavaScript twin of `common/project_root.py` (ADR 0020 D01): the walk, the fallback
 * and the notice are the same answers, and the conformance corpus compares them.
 *
 * Paths are project-root-relative or absolute POSIX strings, the way the corpus
 * normalizes them. Stdlib only: `node:fs` and `node:path`.
 *
 * `_absolute` is the only path resolver on this side, and the only one a later port may use:
 * every Python call site that writes `.resolve()` (the hooks, `_init`, `_update`, the CLI) will
 * need it here, and `path.resolve`/`path.join` answer a different question — see M114.
 */

import fs from "node:fs";
import { posix } from "node:path";

/** The default dev-layer (local) root; a project may relocate it via the `AITNA_ROOT` env var. */
export const AITNA_ROOT_DEFAULT = "_aitna";

/** Whether `path` is a regular file (a directory named like one does not count). */
function _isFile(/** @type {string} */ path) {
  try {
    return fs.statSync(path).isFile();
  } catch {
    return false;
  }
}

/**
 * The absolute form of `path` with symlinks dereferenced — `Path.resolve(strict=False)` ported,
 * component by component rather than in one call.
 *
 * Neither Node primitive is that function on its own. `posix.resolve` collapses `..` *lexically*,
 * before any link is read, so `<base>/link/../../target` becomes `<base>` where the stdlib walks
 * through the link and answers `<base>/target`; `realpathSync` does dereference, but it answers
 * only for a path that exists, while the twin resolves the existing prefix and re-attaches the
 * rest. Hence the walk: hand the longest existing prefix to `realpathSync.native` — the OS
 * `realpath`, which resolves links and applies `..` to what the link expanded into, the way
 * `pathlib` does — and finish the components past it by hand, where a `..` can only mean the
 * component before it.
 *
 * A loop raises, as the stdlib's `RuntimeError` does: an answer built on the alias would be a
 * path no other answer agrees with, which is the failure this function exists to avoid.
 * @param {string} path
 * @returns {string}
 */
function _absolute(path) {
  // The cwd prefix is concatenated, never `path.join`ed: join normalizes, which collapses `..`
  // against the *written* path — the exact mistake the walk below exists to avoid. A relative
  // start of `link/..` has to reach the resolver as `link` then `..`, so that `..` applies to
  // what the link expanded into, which is what `Path.resolve()` does.
  const given = posix.isAbsolute(path) ? path : `${process.cwd()}/${path}`;
  /** @type {string[]} */ const beyond = [];
  let cursor = given;
  for (;;) {
    try {
      return _reattach(fs.realpathSync.native(cursor), beyond);
    } catch (error) {
      const code = /** @type {{code?: string}} */ (error).code;
      if (code === "ELOOP") {
        // The same refusal the stdlib raises (`RuntimeError: Symlink loop from '<path>'`), with
        // the filesystem's own error kept underneath it.
        throw new Error(`Symlink loop from '${cursor}'`, { cause: error });
      }
      if (code !== "ENOENT" && code !== "ENOTDIR") {
        throw error;
      }
      const parent = posix.dirname(cursor);
      if (parent === cursor) {
        throw error; // no shorter prefix exists: nothing can be resolved
      }
      beyond.push(posix.basename(cursor));
      cursor = parent;
    }
  }
}

/**
 * Re-attach the components that were not on disk, in order, against the resolved prefix.
 * @param {string} resolved
 * @param {string[]} beyond
 * @returns {string}
 */
function _reattach(resolved, beyond) {
  let out = resolved;
  for (const part of beyond.toReversed()) {
    if (part === "." || part === "") {
      continue;
    }
    out = part === ".." ? posix.dirname(out) : posix.join(out, part);
  }
  return out;
}

/**
 * The configured dev-layer root, as a project-root-relative POSIX path (default `_aitna`).
 * Mirrors `common/project_root.py::aitna_root_name`: the env var is the configuration, read
 * at the point the name is asked for, never cached at module level.
 */
export function aitnaRootName() {
  const declared = (process.env.AITNA_ROOT || "").replace(/^\/+|\/+$/g, "");
  return declared || AITNA_ROOT_DEFAULT;
}

/**
 * Absolute dev-layer root for `projectRoot` (`<projectRoot>/<AITNA_ROOT>`).
 * @param {string} projectRoot
 * @returns {string}
 */
export function aitnaRoot(projectRoot) {
  return posix.join(projectRoot, aitnaRootName());
}

/**
 * Absolute akmon mount for `projectRoot` (`<aitna-root>/akmon`) — the mounted tree's path,
 * computed, not a claim that it exists.
 * @param {string} projectRoot
 * @returns {string}
 */
export function akmonMount(projectRoot) {
  return posix.join(aitnaRoot(projectRoot), "akmon");
}

/**
 * A project `AGENTS.md` beside either a mounted tree or an integration record. The record
 * (`<AITNA_ROOT>/.akmon.toml`) is the only marker a package-mode project carries.
 * @param {string} candidate
 * @returns {boolean}
 */
export function isProjectRoot(candidate) {
  if (!_isFile(posix.join(candidate, "AGENTS.md"))) {
    return false;
  }
  const aitna = aitnaRoot(candidate);
  return fs.existsSync(posix.join(aitna, "akmon")) || _isFile(posix.join(aitna, ".akmon.toml"));
}

/**
 * Walk up from `start` (default: the cwd) to the nearest project root, else `start`. The
 * fallback is deliberate and stays: a hook must not abort a session invoked outside a project.
 * @param {string | null} [start]
 * @returns {string}
 */
export function findProjectRoot(start = null) {
  const origin = _absolute(start ?? process.cwd());
  let candidate = origin;
  for (;;) {
    if (isProjectRoot(candidate)) {
      return candidate;
    }
    const parent = posix.dirname(candidate);
    if (parent === candidate) {
      break;
    }
    candidate = parent;
  }
  return origin;
}

/** @typedef {{root: string, notice: string | null}} ResolvedRoot */

/**
 * The root a command-line entry point works in, plus the notice to print if it guessed.
 * `{root, null}` when the root was named or found; `{cwd, notice}` when it was not — the
 * notice exists because the fallback root is where the tool then reads and writes.
 * @param {string | null} explicit the `--project-root` value, when the caller was given one
 * @param {string | null} [start]
 * @returns {ResolvedRoot}
 */
export function resolveProjectRoot(explicit, start = null) {
  if (explicit !== null && explicit !== undefined) {
    return { root: _absolute(explicit), notice: null };
  }
  const origin = _absolute(start ?? process.cwd());
  const found = findProjectRoot(origin);
  if (isProjectRoot(found)) {
    return { root: found, notice: null };
  }
  const aitna = aitnaRootName();
  const notice =
    `[akmon] no project root at or above ${origin}: expected AGENTS.md beside ${aitna}/akmon ` +
    `or ${aitna}/.akmon.toml. Falling back to that directory, so anything this command reads ` +
    `or writes is relative to it; pass --project-root to name the root instead.`;
  return { root: origin, notice };
}
