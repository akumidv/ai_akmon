/**
 * The one owner of "where is the project root" and "what the dev layer is called".
 * The JavaScript twin of `common/project_root.py` (ADR 0020 D01): the walk, the fallback
 * and the notice are the same answers, and the conformance corpus compares them.
 *
 * Paths are project-root-relative or absolute POSIX strings, the way the corpus
 * normalizes them. Node builtins only, imported at the top of the file: `node:child_process`,
 * `node:fs`, `node:path`.
 *
 * `resolvePath` is the only path resolver on this side, and the only one a later port may use:
 * every Python call site that writes `.resolve()` (the hooks, `_init`, `_update`, the CLI) will
 * need it here, and `path.resolve`/`path.join` answer a different question — see M114.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { posix } from "node:path";

import {
  decodeUtf8,
  isFile,
  isOSError,
  pyError,
  pyPath,
  pyStat,
  pyStrip,
  pySplitlines,
  readText,
  strRepr,
} from "./pyvalue.mjs";

/** The default dev-layer (local) root; a project may relocate it by committing `.aitna-root`. */
export const AITNA_ROOT_DEFAULT = "_aitna";

/** The file at the project root that declares a dev-layer root other than the default (ADR 0022 D09). */
export const DEV_ROOT_FILE = ".aitna-root";

/**
 * The two dotted folders under the dev root (ADR 0028 D01): `.local` holds what only this machine
 * needs (learning state, model overlays), `.ergon` holds one ergon per piece of work. Both are
 * gitignored. The local index retired with ADR 0028 D12, so no row is written anywhere.
 */
export const LOCAL_DIR_NAME = ".local";
export const ERGON_DIR_NAME = ".ergon";

// The folder the local layer had before ADR 0028; named only so the legacy check can find it.
const _LEGACY_LOCAL_DIR_NAME = "local";

/** How a dev root was found (`DevRoot.origin`). */
export const ORIGIN_POINTER = "pointer";
export const ORIGIN_DEFAULT = "default";
export const ORIGIN_NO_PROJECT_ROOT = "no-project-root";

// How long the git probe that resolves a worktree's main checkout may take, in milliseconds.
const _GIT_TIMEOUT_MS = 10_000;

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
 * @typedef {{readonly path: string, readonly origin: string}} DevRoot
 * The dev-layer root of a project and how it was found. `path` is `<project root>/<name>`, except
 * for `no-project-root`, where it is the bare default name, usable for reading only: a writer of
 * the local layer stops there.
 */

/**
 * A dev-layer root as a project-root-relative POSIX path, or a `ValueError` naming `value`:
 * not empty, not absolute, not climbing out with `..`, and (links followed) inside the project.
 * `common/project_root.py::validated_dev_root_name`. `source` names the declaration in the message
 * (`--aitna-root` or `.aitna-root`).
 * @param {string} value
 * @param {string} projectRoot
 * @param {string} [source]
 * @returns {string}
 * @throws {Error} `ValueError` when the value is refused
 */
export function validatedDevRootName(value, projectRoot, source = "--aitna-root") {
  const raw = pyStrip(value);
  // Absoluteness is decided on the *raw* value: stripping the slashes first would turn
  // `/tmp/escaped` into the innocent-looking relative `tmp/escaped`.
  if (raw.startsWith("/")) {
    throw pyError("ValueError", `${source} must be relative to the project root and stay inside it: ${strRepr(value)}`);
  }
  const cleaned = raw.replace(/^\/+|\/+$/g, "");
  if (cleaned === "") {
    throw pyError("ValueError", `${source} cannot be empty`);
  }
  if (cleaned.split("/").includes("..")) {
    throw pyError("ValueError", `${source} must be relative to the project root and stay inside it: ${strRepr(value)}`);
  }
  const rootReal = resolvePath(projectRoot);
  const resolved = resolvePath(`${rootReal === "/" ? "" : rootReal}/${cleaned}`);
  if (resolved === rootReal || !isRelativeTo(resolved, rootReal)) {
    throw pyError("ValueError", `${source} resolves outside the project root: ${resolved}`);
  }
  return cleaned;
}

/**
 * The dev-layer root of `projectRoot`, and how it was found (ADR 0022 D09): `.aitna-root` at the
 * project root holds one line, a project-root-relative POSIX path (`pointer`); an absent file
 * means `_aitna` (`default`); `null` — no project root found — answers `_aitna` as
 * `no-project-root`, for reading only.
 * @param {string | null} projectRoot
 * @returns {DevRoot}
 * @throws {Error} `ValueError` when the declaration is refused
 */
export function devRoot(projectRoot) {
  if (projectRoot === null) {
    return Object.freeze({ path: AITNA_ROOT_DEFAULT, origin: ORIGIN_NO_PROJECT_ROOT });
  }
  const declaration = pyPath(projectRoot, DEV_ROOT_FILE);
  if (!isFile(declaration)) {
    return Object.freeze({ path: pyPath(projectRoot, AITNA_ROOT_DEFAULT), origin: ORIGIN_DEFAULT });
  }
  const text = pyStrip(readText(declaration));
  if (pySplitlines(text).length > 1) {
    throw pyError("ValueError", `${DEV_ROOT_FILE} must hold one line, a project-root-relative path: ${strRepr(text)}`);
  }
  const name = validatedDevRootName(text, projectRoot, DEV_ROOT_FILE);
  return Object.freeze({ path: pyPath(projectRoot, name), origin: ORIGIN_POINTER });
}

/**
 * The dev-layer root of `projectRoot` as a project-root-relative POSIX path (default `_aitna`).
 * @param {string | null} projectRoot
 * @returns {string}
 */
export function aitnaRootName(projectRoot) {
  const found = devRoot(projectRoot);
  if (projectRoot === null) {
    return found.path;
  }
  return posix.relative(pyPath(projectRoot), found.path);
}

/**
 * Absolute dev-layer root for `projectRoot` (see `devRoot`).
 * @param {string | null} projectRoot
 * @returns {string}
 */
export function aitnaRoot(projectRoot) {
  return devRoot(projectRoot).path;
}

/**
 * The local layer `<dev root>/.local` of `projectRoot` (ADR 0028 D01): the path, computed, not a
 * claim that it exists. With no project root it is the default-name relative path
 * (`_aitna/.local`), for reading only, as `aitnaRoot` is.
 * @param {string | null} projectRoot
 * @returns {string}
 */
export function localRoot(projectRoot) {
  return pyPath(aitnaRoot(projectRoot), LOCAL_DIR_NAME);
}

/**
 * The main checkout of the repository that holds `projectRoot`, or `projectRoot` itself.
 *
 * A linked worktree keeps its own working tree but shares the repository, so
 * `git rev-parse --git-common-dir` answers where the repository really is. The ergons live in the
 * main checkout (ADR 0028 D11), so the accessor resolves them through it: a session in a worktree
 * writes into the main checkout's ergons, and one ergon is one folder for the project.
 *
 * The probe runs on every call and its answer is not kept: a cached root is module state a later
 * call cannot see the end of — a worktree added or removed while a process lives would keep
 * answering the old one. A caller that asks repeatedly passes the resolved root down.
 *
 * Outside a repository, or when git is absent, the answer is the project root unchanged. With no
 * project root at all, the answer is `null`, as everywhere else in this module.
 * @param {string | null} projectRoot
 * @returns {string | null}
 */
export function gitCommonRoot(projectRoot) {
  if (projectRoot === null) {
    return null;
  }
  return _resolveGitCommonRoot(projectRoot);
}

/**
 * What git says of `projectRoot`: the repository's resolved common directory and the project
 * root's prefix inside its working tree (`mono/proj/`, or empty at the top); `null` when git cannot
 * say.
 * @param {string} projectRoot
 * @returns {{common: string, prefix: string} | null}
 */
function _gitAnswer(projectRoot) {
  const done = spawnSync("git", ["rev-parse", "--git-common-dir", "--show-prefix"], {
    cwd: projectRoot,
    stdio: ["ignore", "pipe", "pipe"],
    timeout: _GIT_TIMEOUT_MS,
  });
  if (done.error !== undefined || done.status !== 0) {
    return null; // no git, a timeout, a missing cwd, or not a repository
  }
  const answer = decodeUtf8(done.stdout);
  const newline = answer.indexOf("\n");
  const common = pyStrip(newline < 0 ? answer : answer.slice(0, newline));
  if (common === "") {
    return null;
  }
  const absolute = posix.isAbsolute(common) ? pyPath(common) : pyPath(projectRoot, common);
  try {
    return { common: resolvePath(absolute), prefix: newline < 0 ? "" : pyStrip(answer.slice(newline + 1)) };
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
    return null;
  }
}

/**
 * The main checkout's copy of `projectRoot`, read from git; the project root when there is none.
 *
 * One git call answers two things: the repository's common directory (its parent is the main
 * checkout) and the project root's own prefix inside its working tree. A project in a repository
 * subfolder (`mono/proj`) keeps that subfolder in the main checkout, so its ergons stay its own and
 * do not land in the repository top's dev root (ADR 0028 D11).
 * @param {string} projectRoot
 * @returns {string}
 */
function _resolveGitCommonRoot(projectRoot) {
  const answer = _gitAnswer(projectRoot);
  if (answer === null) {
    return projectRoot;
  }
  // The common directory is the repository's `.git`; its parent is the main checkout.
  const top = posix.basename(answer.common) === ".git" ? posix.dirname(answer.common) : answer.common;
  const root = pyPath(top, answer.prefix);
  return isFile(pyPath(root, DEV_ROOT_FILE)) || isFile(pyPath(root, "AGENTS.md")) ? root : projectRoot;
}

/**
 * The ergon layer `<dev root>/.ergon` of `projectRoot` (ADR 0028 D01, D11; ADR 0029 D02): the path,
 * computed, not a claim that it exists. With no project root it is the default-name relative path
 * (`_aitna/.ergon`), for reading only, as `aitnaRoot` is. In a linked worktree it is the main
 * checkout's folder: the ergons are shared, the working tree is not.
 * @param {string | null} projectRoot
 * @returns {string}
 */
export function ergonRoot(projectRoot) {
  return pyPath(aitnaRoot(gitCommonRoot(projectRoot)), ERGON_DIR_NAME);
}

/**
 * The pre-0028 local layer `<dev root>/.local` of `projectRoot`. Used only to detect the old
 * folder and warn that it moves by hand to `.local` and `.ergon` (ADR 0028 D01); akmon never
 * reads state from it and never moves it. The path, computed, not a claim that it exists.
 * @param {string | null} projectRoot
 * @returns {string}
 */
export function legacyLocalRoot(projectRoot) {
  return pyPath(aitnaRoot(projectRoot), _LEGACY_LOCAL_DIR_NAME);
}

/**
 * Absolute akmon mount for `projectRoot` (`<aitna-root>/akmon`) — the mounted tree's path,
 * computed, not a claim that it exists.
 * @param {string | null} projectRoot
 * @returns {string}
 */
export function akmonMount(projectRoot) {
  return pyPath(aitnaRoot(projectRoot), "akmon");
}

/**
 * A project `AGENTS.md` beside a mounted tree, an integration record or `.aitna-root`. The record
 * (`<dev root>/.akmon.toml`) is the only marker a package-mode project carries; the declaration
 * file is a marker of its own (ADR 0022 D09), and without it the dev root is the default, so the
 * question never reads the declaration.
 * @param {string} candidate
 * @returns {boolean}
 */
export function isProjectRoot(candidate) {
  if (!isFile(pyPath(candidate, "AGENTS.md"))) {
    return false;
  }
  if (isFile(pyPath(candidate, DEV_ROOT_FILE))) {
    return true;
  }
  const aitna = pyPath(candidate, AITNA_ROOT_DEFAULT);
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
 * Walk up from `start` (default: the cwd) to the nearest project root, or `null`. The answer a
 * writer of the local layer needs: `null` is "no project root", so it writes nothing, where
 * `findProjectRoot` hands back a guess. The walk is linear: each step is the candidate's parent.
 * @param {string | null} [start]
 * @returns {string | null}
 * @throws {Error} `ValueError` when the start path is longer than the bound
 */
export function locateProjectRoot(start = null) {
  let candidate = resolvePath(_boundedStart(start));
  while (!isProjectRoot(candidate)) {
    const parent = posix.dirname(candidate);
    if (parent === candidate) {
      return null;
    }
    candidate = parent;
  }
  return candidate;
}

/**
 * Walk up from `start` (default: the cwd) to the nearest project root, else `start`. The
 * fallback is deliberate and stays: a hook must not abort a session invoked outside a project.
 * A start path longer than 4096 UTF-8 bytes (Linux's PATH_MAX) is not a fallback: it is refused
 * with a `ValueError` before it is resolved, and a hook takes that as its ordinary failure exit
 * (C121).
 * @param {string | null} [start]
 * @returns {string}
 * @throws {Error} `ValueError` when the start path is longer than the bound
 */
export function findProjectRoot(start = null) {
  return locateProjectRoot(start) ?? resolvePath(_boundedStart(start));
}

/** @typedef {{root: string, notice: string | null}} ResolvedRoot */

/**
 * The root a command-line entry point works in, plus the notice to print if it guessed.
 * `{root, null}` when the root was named or found; `{cwd, notice}` when it was not — the
 * notice exists because the fallback root is where the tool then reads and writes. A command
 * that writes the local layer prints the notice and stops (ADR 0022 D09).
 * @param {string | null} explicit the `--project-root` value, when the caller was given one
 * @param {string | null} [start]
 * @returns {ResolvedRoot}
 */
export function resolveProjectRoot(explicit, start = null) {
  if (explicit !== null && explicit !== undefined) {
    return { root: resolvePath(explicit), notice: null };
  }
  const origin = resolvePath(_boundedStart(start));
  const found = locateProjectRoot(origin);
  if (found !== null) {
    return { root: found, notice: null };
  }
  const notice =
    `[akmon] no project root at or above ${origin}: expected AGENTS.md beside ${DEV_ROOT_FILE}, ` +
    `${AITNA_ROOT_DEFAULT}/akmon or ${AITNA_ROOT_DEFAULT}/.akmon.toml. Falling back to that directory, ` +
    `so anything this command reads or writes is relative to it; pass --project-root to name the root instead.`;
  return { root: origin, notice };
}
