/**
 * The mount half of `src/akmon/cli.py` for the JavaScript CLI — the version-skew rule of ADR 0009
 * decision 5, as the C129 amendment of ADR 0020 D02 extends it to a Node repository attached in a
 * mounted mode.
 *
 * A project whose record names a mounted `mount` and `ecosystem = "node"` is governed by its
 * mount's own CLI, `<AITNA_ROOT>/akmon/js/akmon/cli.mjs`: the pin governs, whichever CLI started.
 * A JavaScript CLI that is not the mount's own (an `npx` copy, a global install) hands the command
 * over to it as a child process, and for the commands the Python dispatches (`cli.json`
 * `dispatched_commands`) prints the same one-line notice when its version differs from the pinned
 * one. The mount's own CLI, and any project that is not such a mount, runs in place.
 *
 * Twin notes: the Python hands over to a mount of any ecosystem, because its launchers are in
 * every mount; here only a Node record hands over — a Python-ecosystem mount has no promise of a
 * `cli.mjs`, and the running CLI refuses that record itself (`bin/sync.mjs::unsupportedFound`).
 *
 * Kept apart from `cli.mjs` so `_init.mjs` can import it statically: `cli.mjs` evaluates its
 * `main` under a top-level `await`, and a module it loads must not import it back.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { fill, read } from "../common/jsondata.mjs";
import { aitnaRootName, resolvePath } from "../common/project_root.mjs";
import { readAkmonToml, recordedEcosystem, recordsPackageMode } from "../common/record.mjs";
import { splitVersion } from "../common/versions.mjs";

/** The tree this module executes from: `<tree>/js/akmon/_mount.mjs` → `<tree>`. */
const TREE_ROOT = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Where a tree keeps its CLI, relative to the tree. */
export const CLI_PATH = "js/akmon/cli.mjs";

/**
 * Whether `path` exists (a link is followed).
 * @param {string} path
 * @returns {boolean}
 */
function _exists(path) {
  try {
    fs.statSync(path);
    return true;
  } catch {
    return false;
  }
}

/**
 * The mounted tree (`<AITNA_ROOT>/akmon`) that governs `start`'s project, or `null` — the Python
 * `_mounted_akmon_root`, walking up from `start` to the first `AGENTS.md` whose dev layer holds a
 * mount. A record that says `mount = "package"` has no mount, whatever lingers on disk; a mount
 * governs here only when the record names `ecosystem = "node"` and the mount carries a CLI.
 * @param {string} start
 * @returns {string | null}
 */
export function mountedAkmonRoot(start) {
  const aitna = aitnaRootName();
  let candidate = resolvePath(start);
  for (;;) {
    if (_isFile(posix.join(candidate, "AGENTS.md"))) {
      if (recordsPackageMode(candidate)) {
        return null;
      }
      const mount = posix.join(candidate, aitna, "akmon");
      if (_exists(mount)) {
        const governs = recordedEcosystem(candidate) === "node" && _isFile(posix.join(mount, CLI_PATH));
        return governs ? mount : null;
      }
    }
    const parent = posix.dirname(candidate);
    if (parent === candidate) {
      return null;
    }
    candidate = parent;
  }
}

/**
 * Whether `path` is a regular file (a link is followed).
 * @param {string} path
 * @returns {boolean}
 */
function _isFile(path) {
  try {
    return fs.statSync(path).isFile();
  } catch {
    return false;
  }
}

/**
 * Whether `mount` is the tree at `treeRoot` (both dereferenced): the mount's own CLI is running.
 * @param {string} mount
 * @param {string} [treeRoot] default: the tree this module runs from
 * @returns {boolean}
 */
export function isRunningTree(mount, treeRoot = TREE_ROOT) {
  try {
    return fs.realpathSync(mount) === fs.realpathSync(treeRoot);
  } catch {
    return false;
  }
}

/**
 * The version of the running CLI (`<tree>/package.json`), `null` when it cannot be read.
 * @returns {string | null}
 */
function _runningVersion() {
  try {
    const manifest = /** @type {{version?: unknown}} */ (read(posix.join(TREE_ROOT, "package.json")));
    return typeof manifest.version === "string" ? manifest.version : null;
  } catch {
    return null;
  }
}

/**
 * The one-line notice when the running CLI's version differs from the pin the record holds (the
 * Python `_skew_notice`, `cli.json`'s texts): the versions compared without a leading `v` or a
 * `git describe` distance, and a distance is its own notice. `null` when the record names no
 * version, or nothing differs.
 * @param {string} mount the mounted tree, `<AITNA_ROOT>/akmon`
 * @param {string | null} [cliVersion] default: the running CLI's
 * @returns {string | null}
 */
export function skewNotice(mount, cliVersion = _runningVersion()) {
  const pinned = readAkmonToml(posix.join(posix.dirname(mount), ".akmon.toml"))["akmon_version"];
  if (typeof pinned !== "string" || pinned === "" || cliVersion === null) {
    return null;
  }
  const data = /** @type {{skew_version: string, skew_commits: string}} */ (
    read(posix.join(TREE_ROOT, "src", "akmon", "cli.json"))
  );
  const recorded = splitVersion(pinned);
  if (recorded.base !== splitVersion(cliVersion).base) {
    return fill(data.skew_version, { cli_version: cliVersion, pinned });
  }
  if (recorded.ahead !== null) {
    const commits = recorded.ahead === "1" ? "commit" : "commits";
    return fill(data.skew_commits, { pinned, ahead: recorded.ahead, commits });
  }
  return null;
}

/**
 * Run `relative` (a script of the mounted tree) under the running node, its streams on this
 * terminal; its exit code (1 when it could not be started or was killed).
 * @param {string} mount
 * @param {string} relative e.g. `js/akmon/cli.mjs`
 * @param {string[]} argv
 * @param {string} [cwd]
 * @returns {number}
 */
export function runMountedScript(mount, relative, argv, cwd = process.cwd()) {
  const result = spawnSync(process.execPath, [posix.join(mount, relative), ...argv], { cwd, stdio: "inherit" });
  return result.error === undefined && typeof result.status === "number" ? result.status : 1;
}

/**
 * Hand `argv` over to the CLI of the mount that governs `cwd`'s project, when the running CLI is
 * not that mount's own: the notice first (when `notice`), then the mount's CLI with `argv`
 * verbatim. `null` when nothing is handed over and the running CLI does the work itself.
 * @param {string[]} argv the full command line after `akmon` (`["sync", "--check"]`)
 * @param {{cwd?: string, notice?: boolean}} [options]
 * @returns {number | null}
 */
export function handOver(argv, { cwd = process.cwd(), notice = false } = {}) {
  const mount = mountedAkmonRoot(cwd);
  if (mount === null || isRunningTree(mount)) {
    return null;
  }
  if (notice) {
    const text = skewNotice(mount);
    if (text !== null) {
      process.stderr.write(`${text}\n`);
    }
  }
  return runMountedScript(mount, CLI_PATH, argv, cwd);
}
