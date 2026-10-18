/**
 * The one owner of "where is the project root" and "what the dev layer is called".
 * The JavaScript twin of `common/project_root.py` (ADR 0020 D01): the walk, the fallback
 * and the notice are the same answers, and the conformance corpus compares them.
 *
 * Paths are project-root-relative or absolute POSIX strings, the way the corpus
 * normalizes them. Stdlib only: `node:fs` and `node:path`.
 *
 * `resolvePath` is the only path resolver on this side, and the only one a later port may use:
 * every Python call site that writes `.resolve()` (the hooks, `_init`, `_update`, the CLI) will
 * need it here, and `path.resolve`/`path.join` answer a different question — see M114.
 */

import fs from "node:fs";
import { posix } from "node:path";

import { isFile, pyError, pyPath, pyStat } from "./pyvalue.mjs";

/** The default dev-layer (local) root; a project may relocate it via the `AITNA_ROOT` env var. */
export const AITNA_ROOT_DEFAULT = "_aitna";

// Dangling links followed by hand before the walk calls it a loop: Linux's own MAXSYMLINKS.
const _MAX_HOPS = 40;

// The longest start path the walk accepts, in UTF-8 bytes: Linux's PATH_MAX. No longer path
// names anything the kernel can look up, and resolving one costs time quadratic in its depth.
const _START_PATH_MAX_BYTES = 4096;

// How much of a refused start path its error message quotes, in code points.
const _REFUSED_PREFIX_CHARS = 40;

/**
 * `path.is_relative_to(root)` for two resolved absolute POSIX paths: a component prefix, so
 * `/a/bc` is not inside `/a/b`. Resolve both with `resolvePath` first.
 * @param {string} path
 * @param {string} root
 * @returns {boolean}
 */
export function isRelativeTo(path, root) {
  return path === root || path.startsWith(root === "/" ? "/" : `${root}/`);
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
 * path no other answer agrees with, which is the failure this function exists to avoid. Any other
 * filesystem error on the way (a name too long, a directory that cannot be searched) only means
 * that component is not a link the stdlib could follow, and it is kept as written. A dangling
 * link is the exception `realpath` cannot answer and the stdlib can: it is followed to its target.
 * @param {string} path
 * @returns {string}
 */
export function resolvePath(path) {
  // The cwd prefix is concatenated, never `path.join`ed: join normalizes, which collapses `..`
  // against the *written* path — the exact mistake the walk below exists to avoid. A relative
  // start of `link/..` has to reach the resolver as `link` then `..`, so that `..` applies to
  // what the link expanded into, which is what `Path.resolve()` does.
  const given = posix.isAbsolute(path) ? path : `${process.cwd()}/${path}`;
  /** @type {string[]} */ const beyond = [];
  let cursor = given;
  let hops = 0;
  for (;;) {
    try {
      return _reattach(fs.realpathSync.native(cursor), beyond);
    } catch (error) {
      const code = /** @type {{code?: string}} */ (error).code;
      if (code === "ELOOP") {
        // The same refusal the stdlib raises (`RuntimeError: Symlink loop from '<path>'`), with
        // the filesystem's own error kept underneath it.
        const refusal = new Error(`Symlink loop from '${cursor}'`, { cause: error });
        refusal.name = "RuntimeError";
        throw refusal;
      }
      // Python 3.12's `realpath(strict=False)` takes any `OSError` from the `lstat` of a component
      // (ENOENT, ENOTDIR, EACCES, ENAMETOOLONG, …) as "not a link" and goes on; only an error
      // that is no system call's — an argument Node refuses — is not its to swallow.
      if (typeof (/** @type {{errno?: unknown}} */ (error).errno) !== "number") {
        throw error;
      }
      const target = _danglingTarget(cursor);
      if (target !== null) {
        hops += 1;
        if (hops > _MAX_HOPS) {
          const refusal = new Error(`Symlink loop from '${given}'`, { cause: error });
          refusal.name = "RuntimeError";
          throw refusal;
        }
        cursor = target;
        continue;
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
 * Where a link that `realpath` could not finish points, or `null` when `cursor` is no link.
 *
 * `realpath` fails on a dangling link, but `Path.resolve()` still follows it: `<dir>/dangling`
 * pointing at `nonexistent` resolves to `<dir>/nonexistent`, the components past the link
 * re-attached to the target (C115). A relative target is concatenated onto the link's directory
 * unnormalized, for the reason the cwd is: a `..` in it applies to what that directory resolves
 * to. A failed `lstat` or `readlink` means "not a link", as everywhere else in the walk.
 * @param {string} cursor
 * @returns {string | null}
 */
function _danglingTarget(cursor) {
  const link = cursor.length > 1 ? cursor.replace(/\/+$/, "") || "/" : cursor;
  try {
    if (!fs.lstatSync(link).isSymbolicLink()) {
      return null;
    }
    const target = fs.readlinkSync(link);
    return posix.isAbsolute(target) ? target : `${posix.dirname(link)}/${target}`;
  } catch {
    return null;
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
  return pyPath(projectRoot, aitnaRootName());
}

/**
 * Absolute akmon mount for `projectRoot` (`<aitna-root>/akmon`) — the mounted tree's path,
 * computed, not a claim that it exists.
 * @param {string} projectRoot
 * @returns {string}
 */
export function akmonMount(projectRoot) {
  return pyPath(aitnaRoot(projectRoot), "akmon");
}

/**
 * A project `AGENTS.md` beside either a mounted tree or an integration record. The record
 * (`<AITNA_ROOT>/.akmon.toml`) is the only marker a package-mode project carries.
 * @param {string} candidate
 * @returns {boolean}
 */
export function isProjectRoot(candidate) {
  if (!isFile(pyPath(candidate, "AGENTS.md"))) {
    return false;
  }
  const aitna = aitnaRoot(candidate);
  // `Path.exists()`, not `existsSync`: a failure other than "not there" (a name too long, a
  // directory that cannot be searched) raises in both twins rather than in one only (C121).
  return pyStat(pyPath(aitna, "akmon")) !== null || isFile(pyPath(aitna, ".akmon.toml"));
}

/**
 * `start` (default: the cwd) as `Path(start)` spells it, refused when it is longer than the walk
 * accepts — `common/project_root.py::_bounded_start`.
 *
 * The bound is checked on the string before any filesystem call, `resolvePath` included, because
 * the cost it guards is in those calls: a start of 32,769 `a/` components kept a hook resolving it
 * for close to a minute (C121). The length is counted in UTF-8 on the `Path`-normalized spelling,
 * a lone surrogate as three bytes, the way the Python twin counts it.
 * @param {string | null} start
 * @returns {string}
 * @throws {Error} `ValueError` when the start path is longer than the bound
 */
function _boundedStart(start) {
  const text = pyPath(start ?? process.cwd());
  const size = Buffer.byteLength(text, "utf8");
  if (size > _START_PATH_MAX_BYTES) {
    let prefix = "";
    let taken = 0;
    for (const point of text) {
      if (taken === _REFUSED_PREFIX_CHARS) {
        break;
      }
      prefix += point;
      taken += 1;
    }
    throw pyError(
      "ValueError",
      `project-root start path is ${size} bytes, over the ${_START_PATH_MAX_BYTES}-byte bound: ${prefix}...`,
    );
  }
  return text;
}

/**
 * Walk up from `start` (default: the cwd) to the nearest project root, else `start`. The
 * fallback is deliberate and stays: a hook must not abort a session invoked outside a project.
 * A start path longer than 4096 UTF-8 bytes (Linux's PATH_MAX) is not a fallback: it is refused
 * with a `ValueError` before it is resolved, and a hook takes that as its ordinary failure exit
 * (C121). The walk is linear: each step is the candidate's parent, until it stops changing.
 * @param {string | null} [start]
 * @returns {string}
 * @throws {Error} `ValueError` when the start path is longer than the bound
 */
export function findProjectRoot(start = null) {
  const origin = resolvePath(_boundedStart(start));
  let candidate = origin;
  while (!isProjectRoot(candidate)) {
    const parent = posix.dirname(candidate);
    if (parent === candidate) {
      return origin;
    }
    candidate = parent;
  }
  return candidate;
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
    return { root: resolvePath(explicit), notice: null };
  }
  const origin = resolvePath(_boundedStart(start));
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
