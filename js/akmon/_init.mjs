/**
 * `akmon init` — attach the standard to a Node project (C105 pass 3, ADR 0020). The JavaScript
 * twin of `src/akmon/_init.py`: the Python module is the spec for the local layout, the AGENTS.md
 * block, `.gitignore`, the CI workflow, the mount modes, the mode migration, the closing steps,
 * the report and the exit codes. Since C129 (the amendment of ADR 0020 D02) it serves the mounted
 * modes too, for a record that names `ecosystem = "node"`.
 *
 * What differs from the Python, each a decision of the pass-3 spec or of C129:
 * - with no `--mode` and no record the mode is `package` — no probing, no git, no network;
 * - the ecosystem: a present record that does not name `ecosystem = "node"` is refused
 *   (`node_refuses_record`, naming what `bin/sync.mjs::unsupportedFound` found, and the switch
 *   command in a repository with no Python files), and a Node record with `--ecosystem python`
 *   is refused (`node_refuses_reverse`, no way back). A mounted record of the Python implementation
 *   moves to `ecosystem = "node"` by an explicit `--ecosystem node` (the migration of the C129
 *   amendment): the record and the wiring are rewritten, a `[check]` that is exactly the Python's
 *   ruff default is decided again (any other is kept), a `ruff.toml` byte-identical to akmon's
 *   template is named for removal and never deleted, and the closing steps say the Codex `/hooks`
 *   approval is voided. A first attach is
 *   Node in mode `package` (the npm package is the carrier) and, in a mounted mode, when the
 *   repository has `package.json` and no Python files (`bin/sync.mjs::hasPython`) or
 *   `--ecosystem node` says so; any other first attach is the Python implementation's, refused
 *   with its command (`node_refuses_python_ecosystem`);
 * - the mounted modes are the Python's (`mount_text` of `init.json` holds both implementations'
 *   messages): `submodule` adds the repository at the newest release tag, `subtree` prints the
 *   command that commits, `vendored` copies the running tree's `tree_members` plus
 *   `tree_members_node` (the CLI data and the `package.json` the CLI reads its version from). The
 *   generated surface is then run by the mount's own CLI, the version-skew rule (`_mount.mjs`);
 * - in package mode `--repo` is accepted and, as in the Python's package mode, changes nothing:
 *   the AGENTS.md links name `akmon_repo` of `init.json`; nothing is cloned;
 * - the record also says `ecosystem = "node"`; in package mode the pin is `package.json`'s
 *   `devDependencies` (`packagePinStatus`), and the version is the running tree's `package.json`
 *   version;
 * - the ref of the package-mode AGENTS.md links is `--ref`, else the tag of the installed version
 *   (`tagForVersion`) — never a network lookup;
 * - the package manager (`node_managers` of `init.json`) is detected from `package.json`
 *   `packageManager`, else the lockfile, else npm; it picks the CI workflow, the existing-workflow
 *   commands and the pin command;
 * - `[check]` records the JS/TS linters and analyzers the project is configured for (`_NODE_TOOLS`,
 *   run through the manager's `check_run`); a project with a linter (ESLint, Biome, oxlint) defaults to
 *   `own`, any other to `akmon` (ADR 0020 D07/D09): oxlint with akmon's rules, recorded first and
 *   followed by the detected Prettier / `tsc`, the rules attached as a standard `extends` of the
 *   project's `.oxlintrc.json` (written when absent, never edited when present). The project's
 *   `lint` / `typecheck` scripts are named in a next step, never recorded;
 * - the generated surface runs **in process** in package mode: the JS `sync`, then the routing
 *   initializer. In a mounted mode it is always the mount's own, run as child processes
 *   (`_mount.mjs`) — even when the mount is the running tree, since a moved pin has replaced the
 *   files this process already loaded — as the Python dispatches its sync to the mount's launcher;
 * - `_confirm` is the Python's: a stdin that is not a terminal confirms, a terminal is asked and
 *   one line is read synchronously (end of input is "not confirmed");
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `akmon init: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0.
 *
 * Data (the C102 convention): `main` reads `src/akmon/init.json` once and passes it down as `data`
 * — the first parameter of every function that needs a text or a table.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { isatty } from "node:tty";
import { parseArgs } from "node:util";

import { blockHeading, readAlwaysLoadedData } from "../common/always_loaded.mjs";
import { fnmatchCase } from "../common/glob.mjs";
import { fill, read } from "../common/jsondata.mjs";
import { AITNA_ROOT_DEFAULT, resolvePath } from "../common/project_root.mjs";
import { isDir, isFile, pySplitlines, pyStrip, readText, strRepr, truthy, writeText } from "../common/pyvalue.mjs";
import { readAkmonToml, recordedEcosystem, recordedMount } from "../common/record.mjs";
import { shlexJoin } from "../common/shlex.mjs";
import { compareVersions, isFinal, splitVersion, switchTag } from "../common/versions.mjs";
import {
  hasPython,
  installedAkmonVersion,
  main as syncMain,
  packagePinStatus,
  languageProfiles,
  readSyncData,
  ruffTomlTemplates,
  unsupportedFound,
  upsertTomlKey,
} from "../bin/sync.mjs";
import { CLI_PATH, isRunningTree, runMountedScript, skewNotice } from "./_mount.mjs";
import { embeddedTreeRoot } from "./_tree.mjs";

/**
 * One package manager of `init.json`'s `node_managers` table.
 * @typedef {object} NodeManager
 * @property {string} install the CI install command over a committed lockfile
 * @property {string} install_unlocked the CI install command when no lockfile of this manager is committed
 * @property {string} [install_berry] Yarn 2+ (`.yarnrc.yml`, or `packageManager` `yarn@2`+): `--immutable`
 * @property {string} exec the prefix that runs a local bin (`npx `, `pnpm exec `, …)
 * @property {string} check_run the prefix that runs a project tool for `[check]` (`npx --no-install `, …)
 * @property {string} run_script how the manager runs a `package.json` script (`npm run`, …)
 * @property {string} add_dev_exact the command that adds a dev dependency at an exact version
 * @property {string} test the project's test command
 * @property {string} ci_setup the CI steps between checkout and install
 * @property {string} [ci_setup_unpinned] the same when `package.json` names no `packageManager` (pnpm's
 *   setup action then needs an explicit version)
 * @property {string[]} lockfiles
 */

/**
 * The keys of `src/akmon/init.json` the JavaScript init reads.
 * @typedef {object} InitData
 * @property {string} akmon_repo
 * @property {string} agents_header
 * @property {string} agents_block
 * @property {string} agents_roles_hint_package
 * @property {string} agents_roles_hint_mounted
 * @property {string} agents_shared_layer_node
 * @property {string} agents_shared_layer_mounted
 * @property {string} tasks_skeleton
 * @property {string} memory_index
 * @property {Record<string, string>} charters
 * @property {string} charter
 * @property {string} charter_locate_package
 * @property {string} charter_locate_mounted
 * @property {string[]} gitignore_lines_node
 * @property {string} ci_workflow
 * @property {string} ci_workflow_steps_node
 * @property {string} ci_workflow_steps_node_mounted the mounted workflow (`{{cli}}`, `node_mounted_cli`)
 * @property {string} record_fresh_node
 * @property {string} record_version_line
 * @property {Record<string, NodeManager>} node_managers
 * @property {Record<string, string[]>} write_ci_commands
 * @property {Record<string, string>} pin_step_node
 * @property {{complete: string, incomplete: string, step: string, exit: string, remedy: Record<string, string>}} report
 * @property {Record<string, string>} report_missing_node
 * @property {Record<string, string>} closing_steps
 * @property {string} node_refuses_record
 * @property {string} node_refuses_python_ecosystem
 * @property {Record<string, string>} node_refuses_python_why
 * @property {string} node_refuses_reverse
 * @property {string} node_refuses_record_switch the switch command a refusal of a Python mount adds
 * @property {string} node_switch_mounted_only
 * @property {string} node_switch_log
 * @property {string} node_switch_checks_redecided
 * @property {string} node_switch_codex_step
 * @property {string} node_switch_ruff_step
 * @property {string} checks_redecided_empty
 * @property {Record<string, string>} node_switch_requires a data file of the mount, and the key the switch needs in it
 * @property {string} node_switch_mount_predates
 * @property {Record<string, string>} node_switch_mount_update the command that updates a mount, per mode
 * @property {Record<string, string>} run_prefix the Python `init`'s run prefixes by lockfile, which
 *   its ruff default for `[check]` is spelled with
 * @property {string} node_mounted_cli the spelling of the mount's CLI (`{{aitna}}`)
 * @property {string} node_oxlint_rules the path a project's `.oxlintrc.json` extends to run akmon's rules
 * @property {string} node_oxlint_rules_mounted the same in a mounted mode (`{{aitna}}`)
 * @property {string} node_oxlintrc_text the `.oxlintrc.json` init writes (`{{rules}}`)
 * @property {string} node_oxlintrc_wrote
 * @property {string} node_oxlintrc_env_step
 * @property {string} node_oxlintrc_own_step
 * @property {string} node_oxlint_step
 * @property {string} node_scripts_step
 * @property {string} node_mode_reason
 * @property {string[]} tree_members the standard tree's top-level members, a vendored copy's content
 * @property {string[]} tree_members_node what a Node vendored copy carries beside them
 * @property {string[]} tree_markers
 * @property {string[]} copy_ignore the names a vendored copy leaves out, at every depth
 * @property {string} mount_gitignore
 * @property {Record<string, string>} mount_text the mount modes' messages, shared with the Python
 * @property {Record<string, string>} old_mount_removal
 * @property {string} mode_switch_step
 * @property {string} mode_switch_link_resolution_package
 * @property {string} mode_switch_link_resolution_mounted
 * @property {string} mode_switch_remove_mount
 */

/** The mount modes, in the Python's order. */
const MODES = ["submodule", "vendored", "subtree", "package"];
const CHECK_CHOICES = ["own", "akmon", "none"];
const ECOSYSTEMS = ["python", "node"];
const _PACKAGE_MODE = "package";
const _NODE = "node";

/** A precondition the caller has to fix; reported as one line. */
export class InitError extends Error {}

/**
 * One `init` run: the project, its dev layer, the mount mode (and the one the record held before
 * this run, `null` for a first attach), whether the run moves a Python record to `ecosystem =
 * "node"`, the manager, and the steps left to a person.
 * @typedef {object} Attach
 * @property {string} root
 * @property {string} aitna
 * @property {string} mode
 * @property {string | null} previous
 * @property {boolean} ecosystemSwitch
 * @property {NodeManager} manager
 * @property {string[]} nextSteps
 */

/**
 * Whether the attach mounts a tree (every mode but `package`).
 * @param {Attach} attach
 * @returns {boolean}
 */
function _mounted(attach) {
  return attach.mode !== _PACKAGE_MODE;
}

/**
 * Whether the run changes a recorded mount mode — a migration, not a realign.
 * @param {Attach} attach
 * @returns {boolean}
 */
function _switching(attach) {
  return attach.previous !== null && attach.previous !== attach.mode;
}

/**
 * Where a mounted mode puts the standard tree.
 * @param {Attach} attach
 * @returns {string}
 */
function _mount(attach) {
  return posix.join(attach.root, attach.aitna, "akmon");
}

/**
 * The spelling of the mount's CLI in printed commands (`node <AITNA_ROOT>/akmon/js/akmon/cli.mjs`).
 * @param {InitData} data
 * @param {string} aitna
 * @returns {string}
 */
export function mountedCli(data, aitna) {
  return fill(data.node_mounted_cli, { aitna });
}

/**
 * The shared init text and tables (`init.json`, beside the Python module), read on the call.
 * @returns {InitData}
 */
export function readInitData() {
  return /** @type {InitData} */ (read(posix.join(embeddedTreeRoot(), "src", "akmon", "init.json")));
}

// --------------------------------------------------------------------------------------
// output and input
// --------------------------------------------------------------------------------------

/**
 * @param {string} message
 */
function _log(message) {
  process.stdout.write(`akmon init: ${message}\n`);
}

/**
 * One line from stdin, read synchronously a byte at a time so nothing past it is consumed;
 * `null` at end of input with nothing read.
 * @returns {string | null}
 */
function _readLine() {
  /** @type {number[]} */
  const bytes = [];
  const one = Buffer.alloc(1);
  for (;;) {
    let count;
    try {
      count = fs.readSync(0, one, 0, 1, null);
    } catch (error) {
      const code = /** @type {{code?: string}} */ (error).code;
      if (code === "EAGAIN") {
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 20);
        continue;
      }
      if (code === "EOF") {
        count = 0;
      } else {
        throw error;
      }
    }
    if (count === 0) {
      return bytes.length === 0 ? null : Buffer.from(bytes).toString("utf8");
    }
    if (one[0] === 0x0a) {
      return Buffer.from(bytes).toString("utf8");
    }
    bytes.push(one[0]);
  }
}

/**
 * Ask `question`; a stdin that is not a terminal confirms (as the Python does), otherwise an empty
 * answer or `y`/`yes` does and end of input does not.
 * @param {string} question
 * @returns {boolean}
 */
function _confirm(question) {
  if (!isatty(0)) {
    return true; // non-interactive by design: agents and CI are first-class callers
  }
  process.stdout.write(`${question} [Y/n] `);
  const line = _readLine();
  if (line === null) {
    process.stdout.write("\n");
    return false;
  }
  const answer = pyStrip(line).toLowerCase();
  return answer === "" || answer === "y" || answer === "yes";
}

// --------------------------------------------------------------------------------------
// paths, versions and the package manager
// --------------------------------------------------------------------------------------

/**
 * The dev-layer root this run will use — from `--aitna-root` or from `AITNA_ROOT`, validated
 * whichever way it arrived (the two are one contract).
 * @param {string | undefined} flag
 * @param {string} root
 * @returns {string}
 */
export function effectiveAitnaRoot(flag, root) {
  const source = flag !== undefined ? "--aitna-root" : "AITNA_ROOT";
  const raw = flag !== undefined ? flag : process.env.AITNA_ROOT;
  if (raw === undefined || pyStrip(raw) === "") {
    return AITNA_ROOT_DEFAULT;
  }
  return validatedAitnaRoot(raw, root, source);
}

/**
 * A dev-layer root as a project-root-relative path, or a hard error: not absolute, not climbing
 * out with `..`, and (links followed) inside the project.
 * @param {string} value
 * @param {string} root
 * @param {string} [source]
 * @returns {string}
 */
export function validatedAitnaRoot(value, root, source = "--aitna-root") {
  const raw = pyStrip(value);
  // Absoluteness is decided on the *raw* value: stripping the slashes first would turn
  // `/tmp/escaped` into the innocent-looking relative `tmp/escaped`.
  if (raw.startsWith("/")) {
    throw new InitError(`${source} must be relative to the project root and stay inside it: ${strRepr(value)}`);
  }
  const cleaned = raw.replace(/^\/+|\/+$/g, "");
  if (cleaned === "") {
    throw new InitError(`${source} cannot be empty`);
  }
  if (cleaned.split("/").includes("..")) {
    throw new InitError(`${source} must be relative to the project root and stay inside it: ${strRepr(value)}`);
  }
  const rootReal = resolvePath(root);
  const resolved = resolvePath(`${rootReal === "/" ? "" : rootReal}/${cleaned}`);
  const inside = resolved !== rootReal && resolved.startsWith(rootReal === "/" ? "/" : `${rootReal}/`);
  if (!inside) {
    throw new InitError(`${source} resolves outside the project root: ${resolved}`);
  }
  return cleaned;
}

/**
 * The ref the AGENTS.md links point at: the release tag for a released version, `main` for a
 * development one (no tag exists for it yet) or an unknown one.
 * @param {string | null} version
 * @returns {string}
 */
export function tagForVersion(version) {
  if (version === null || !isFinal(version)) {
    return "main";
  }
  return `v${splitVersion(version).base}`;
}

/**
 * The package manager of the project: `package.json` `packageManager` (`pnpm@9.1.0`, …), else the
 * first manager of the table whose lockfile is present (table order), else npm.
 * @param {InitData} data
 * @param {string} root
 * @returns {string} a key of `node_managers`
 */
export function detectManager(data, root) {
  const managers = data.node_managers;
  const declared = declaredManager(root);
  if (declared !== null) {
    const name = declared.split("@", 1)[0];
    if (Object.hasOwn(managers, name)) {
      return name;
    }
  }
  for (const [name, manager] of Object.entries(managers)) {
    if (manager.lockfiles.some((lockfile) => isFile(posix.join(root, lockfile)))) {
      return name;
    }
  }
  return "npm";
}

/**
 * The `packageManager` field of `package.json` (`pnpm@9.1.0`), or `null` when there is none or the
 * manifest cannot be read.
 * @param {string} root
 * @returns {string | null}
 */
export function declaredManager(root) {
  const manifest = posix.join(root, "package.json");
  if (!isFile(manifest)) {
    return null;
  }
  try {
    const document = JSON.parse(readText(manifest));
    const declared = document !== null && typeof document === "object" ? document.packageManager : undefined;
    return typeof declared === "string" ? declared : null;
  } catch (error) {
    if (!(error instanceof SyntaxError) && /** @type {{name?: string}} */ (error).name !== "UnicodeDecodeError") {
      throw error;
    }
    return null;
  }
}

/**
 * The CI setup steps and install command for this project, so the workflow `init` writes runs on its
 * first push: a frozen install only over a committed lockfile (`npm ci` refuses without one), Yarn 2+'s
 * `--immutable` (its `--frozen-lockfile` is the classic flag), and pnpm's setup action given a version
 * when `package.json` names no `packageManager` (the action fails without one).
 * @param {NodeManager} manager
 * @param {string} root
 * @returns {{setup: string, install: string}}
 */
export function ciInstall(manager, root) {
  const declared = declaredManager(root);
  const locked = manager.lockfiles.some((lockfile) => isFile(posix.join(root, lockfile)));
  const berry =
    isFile(posix.join(root, ".yarnrc.yml")) || (declared !== null && /^yarn@(?:[2-9]|[1-9][0-9])/.test(declared));
  let install = manager.install;
  if (!locked) {
    install = manager.install_unlocked;
  } else if (manager.install_berry !== undefined && berry) {
    install = manager.install_berry;
  }
  const setup =
    manager.ci_setup_unpinned !== undefined && declared === null ? manager.ci_setup_unpinned : manager.ci_setup;
  return { setup, install };
}

// --------------------------------------------------------------------------------------
// git, and the mount modes (the Python's, for a Node record — C129)
// --------------------------------------------------------------------------------------

/**
 * One mount-mode message (`init.json` `mount_text`), filled — the Python reads the same.
 * @param {InitData} data
 * @param {string} key
 * @param {Record<string, string>} [values]
 * @returns {string}
 */
function _mountText(data, key, values = {}) {
  return fill(data.mount_text[key], values);
}

/**
 * Run `argv` (the Python's `_run`): never with a credential prompt (an attach must not hang on
 * one); its output on this terminal unless `capture`.
 * @param {string[]} argv
 * @param {{cwd: string, capture?: boolean, timeout?: number}} options
 * @returns {{status: number, stdout: string}} `status` -1 when the command could not be started
 */
function _spawn(argv, { cwd, capture = false, timeout }) {
  const result = spawnSync(argv[0], argv.slice(1), {
    cwd,
    env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
    encoding: "utf-8",
    stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
    timeout,
  });
  if (result.error !== undefined) {
    return { status: -1, stdout: "" };
  }
  return { status: result.status ?? -1, stdout: result.stdout ?? "" };
}

/**
 * `git <args>` stdout, stripped — `null` when git fails, is absent, or prints nothing.
 * @param {string[]} args
 * @param {string} cwd
 * @returns {string | null}
 */
function _gitOutput(args, cwd) {
  const { status, stdout } = _spawn(["git", ...args], { cwd, capture: true });
  return status === 0 ? pyStrip(stdout) || null : null;
}

/**
 * Whether **git** records `relative` as a submodule of `root`: the staged or committed gitlink
 * (mode `160000`) or a `.gitmodules` entry, since a fresh `git submodule add` writes both and a
 * half-removed one may leave either. The file system cannot answer it: a vendored copy and a
 * subtree carry the same files.
 * @param {string} root
 * @param {string} relative
 * @returns {boolean}
 */
export function isSubmodule(root, relative) {
  const entry = _gitOutput(["ls-files", "--stage", "--", relative], root);
  if (entry !== null && entry.split(/\s+/, 1)[0] === "160000") {
    return true;
  }
  const listing = _gitOutput(["config", "-f", ".gitmodules", "--get-regexp", "^submodule\\..*\\.path$"], root);
  return pySplitlines(listing ?? "")
    .filter((line) => pyStrip(line) !== "")
    .some((line) => {
      const fields = pyStrip(line).match(/^\S+\s+([\s\S]*)$/);
      return pyStrip(fields === null ? line : fields[1]) === relative;
    });
}

/**
 * @param {string} root
 * @returns {boolean}
 */
function _isGitRepo(root) {
  return _gitOutput(["rev-parse", "--is-inside-work-tree"], root) === "true";
}

/**
 * The newest final release tag (`vX.Y.Z`) among `tags`; `null` when there is none. A pre-release
 * never counts: it is not the reviewed state a release tag stands for.
 * @param {Iterable<string>} tags
 * @returns {string | null}
 */
export function newestReleaseTag(tags) {
  /** @type {string | null} */
  let newest = null;
  for (const tag of tags) {
    if (tag.startsWith("v") && isFinal(tag) && (newest === null || compareVersions(tag, newest) > 0)) {
      newest = tag;
    }
  }
  return newest;
}

/**
 * The newest release tag `repo` advertises (`git ls-remote`), never one synthesized from a
 * version; the failure names `--ref` as the way around it.
 * @param {InitData} data
 * @param {string} repo
 * @param {string} root
 * @param {(argv: string[], cwd: string) => string | null} capture a command's stdout, `null` on failure
 * @returns {string}
 */
export function defaultRef(data, repo, root, capture) {
  const listing = capture(["git", "ls-remote", "--tags", "--refs", repo, "refs/tags/v*"], root);
  if (listing === null) {
    throw new InitError(_mountText(data, "ref_unreachable", { repo: strRepr(repo) }));
  }
  const tags = pySplitlines(listing)
    .map((line) => pyStrip(line).split(/\s+/))
    .filter((fields) => fields.length === 2 && fields[1].startsWith("refs/tags/v"))
    .map((fields) => fields[1].slice("refs/tags/".length));
  const newest = newestReleaseTag(tags);
  if (newest === null) {
    throw new InitError(_mountText(data, "ref_no_release", { repo: strRepr(repo) }));
  }
  return newest;
}

/**
 * Whether `path` carries every marker of this standard's tree (`init.json` `tree_markers`): one
 * file is no identity, and a vendored realign deletes and re-copies whole members.
 * @param {InitData} data
 * @param {string} path
 * @returns {boolean}
 */
function _isAkmonTree(data, path) {
  return data.tree_markers.every((marker) => isFile(posix.join(path, marker)));
}

/**
 * Whether `path` is a directory with something in it.
 * @param {string} path
 * @returns {boolean}
 */
function _nonEmptyDir(path) {
  try {
    return fs.readdirSync(path).length > 0;
  } catch {
    return false;
  }
}

/**
 * The commands that retire a `previous`-mode mount — printed, never run (`init.json`).
 * @param {InitData} data
 * @param {string} previous
 * @param {string} relative
 * @returns {string}
 */
function _oldMountRemoval(data, previous, relative) {
  const removals = data.old_mount_removal;
  return fill(Object.hasOwn(removals, previous) ? removals[previous] : removals.vendored, { relative });
}

/**
 * Mode `submodule`: `git submodule add` and the checkout of the pin; the version to record. "Already
 * mounted" is git's answer (`isSubmodule`). A re-run realigns and does not bump: the checkout
 * happens on a fresh mount (the newest release tag) or when `--ref` names one; a moved existing
 * pin is left unstaged for the owner (D5), a fresh one restaged so the index names what is checked out.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {string} repo
 * @param {string | undefined} ref
 * @returns {string | null}
 */
function _mountSubmodule(data, attach, repo, ref) {
  const { root } = attach;
  const mount = _mount(attach);
  const relative = posix.relative(root, mount);
  if (!_isGitRepo(root)) {
    throw new InitError(_mountText(data, "submodule_not_git", { root }));
  }
  const fresh = !isSubmodule(root, relative);
  if (fresh) {
    if (_nonEmptyDir(mount)) {
      const what = _mountText(data, _isAkmonTree(data, mount) ? "submodule_what_mounted" : "submodule_what_foreign");
      throw new InitError(
        _mountText(data, "submodule_not_recorded", {
          relative,
          what,
          removal: _oldMountRemoval(data, "vendored", relative),
        }),
      );
    }
    _log(_mountText(data, "submodule_add", { repo, relative }));
    const added = _spawn(["git", "submodule", "add", "--name", relative, repo, relative], { cwd: root });
    if (added.status !== 0) {
      throw new InitError(_mountText(data, "submodule_add_failed", { code: String(added.status) }));
    }
    _spawn(["git", "submodule", "update", "--init", "--recursive", relative], { cwd: root });
  } else {
    _log(_mountText(data, "submodule_realigning", { relative }));
  }
  const pin = ref
    ? ref
    : fresh
      ? newestReleaseTag(pySplitlines(_gitOutput(["tag", "--list", "v*"], mount) ?? "").map(pyStrip))
      : null;
  if (pin) {
    if (_spawn(["git", "checkout", "--quiet", pin], { cwd: mount }).status !== 0) {
      throw new InitError(_mountText(data, "submodule_checkout_failed", { pin: strRepr(pin), relative }));
    }
    if (fresh) {
      _spawn(["git", "add", "--", relative], { cwd: root });
      _log(_mountText(data, "submodule_pinned", { relative, pin }));
    } else {
      _log(_mountText(data, "submodule_moved", { relative, pin }));
      attach.nextSteps.push(_mountText(data, "submodule_bump_step", { relative }));
    }
  } else if (fresh) {
    _log(_mountText(data, "submodule_no_release", { relative }));
  } else {
    _log(_mountText(data, "submodule_left", { relative }));
  }
  return _gitOutput(["describe", "--tags"], mount) ?? (pin || null);
}

/**
 * Mode `subtree`: attach onto a subtree the **owner** added, never one `init` adds — `git subtree
 * add` commits, and commits are the owner's (D5), so the command is printed (exit 2) and a re-run
 * finds the subtree in place. `--ref` is required on the realign: a subtree keeps no git metadata
 * of its own, so the recorded pin can only come from the owner.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {string} repo
 * @param {string | undefined} ref
 * @returns {string}
 */
function _mountSubtree(data, attach, repo, ref) {
  const { root, aitna } = attach;
  const mount = _mount(attach);
  const relative = posix.relative(root, mount);
  if (!_isGitRepo(root)) {
    throw new InitError(_mountText(data, "subtree_not_git", { root }));
  }
  if (isSubmodule(root, relative)) {
    throw new InitError(
      _mountText(data, "subtree_is_submodule", { relative, removal: _oldMountRemoval(data, "submodule", relative) }),
    );
  }
  if (_isAkmonTree(data, mount)) {
    if (!ref) {
      throw new InitError(_mountText(data, "subtree_needs_ref", { relative }));
    }
    _log(_mountText(data, "subtree_realigning", { relative, ref }));
    return ref;
  }
  let pin = ref;
  if (!pin) {
    const listing = _gitOutput(["ls-remote", "--tags", "--refs", repo], root);
    const tags = pySplitlines(listing ?? "")
      .filter((line) => line.includes("refs/tags/v"))
      .map((line) => line.split("refs/tags/").pop() ?? "");
    pin = newestReleaseTag(tags) ?? "main";
  }
  throw new InitError(_mountText(data, "subtree_refusal", { relative, repo, pin, cli: mountedCli(data, aitna) }));
}

/**
 * Copy `origin` into `target` recursively, leaving out every entry whose name matches one of
 * `ignore` at any depth (`shutil.copytree` with `ignore_patterns`, links followed).
 * @param {string} origin
 * @param {string} target
 * @param {readonly string[]} ignore
 */
function _copyTree(origin, target, ignore) {
  fs.mkdirSync(target, { recursive: true });
  for (const name of fs.readdirSync(origin)) {
    if (ignore.some((pattern) => fnmatchCase(name, pattern))) {
      continue;
    }
    const from = posix.join(origin, name);
    const to = posix.join(target, name);
    if (fs.statSync(from).isDirectory()) {
      _copyTree(from, to, ignore);
    } else {
      fs.copyFileSync(from, to);
    }
  }
}

/**
 * Mode `vendored`: copy the running tree into the mount, member by member — `tree_members`, the
 * members mode `package` ships, plus `tree_members_node`, what the mount's own CLI reads (its
 * data and its `package.json`). The pin is the running tree's version by construction, so `--ref`
 * is refused rather than ignored. Each member is replaced, not merged, so a file a later version
 * dropped does not linger; anything else under the mount is left alone.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {string | undefined} ref
 * @param {string | null} version the running tree's
 * @returns {string | null}
 */
function _mountVendored(data, attach, ref, version) {
  if (ref) {
    throw new InitError(_mountText(data, "vendored_ref", { version: String(version), ref }));
  }
  const { root } = attach;
  const mount = _mount(attach);
  const source = embeddedTreeRoot();
  const relative = posix.relative(root, mount);
  if (_isGitRepo(root) && isSubmodule(root, relative)) {
    throw new InitError(
      _mountText(data, "vendored_into_submodule", { relative, removal: _oldMountRemoval(data, "submodule", relative) }),
    );
  }
  if (_nonEmptyDir(mount) && !_isAkmonTree(data, mount)) {
    throw new InitError(_mountText(data, "vendored_foreign", { relative }));
  }
  if (isRunningTree(mount, source)) {
    // The mount's own CLI realigns it: the copy would delete the very tree it reads from. The
    // pin is that tree's version already (the Python CLI is never its own mount's tree).
    _log(_mountText(data, "vendored_in_place", { relative, version: String(version) }));
    return version;
  }
  fs.mkdirSync(mount, { recursive: true });
  let copied = 0;
  for (const name of [...data.tree_members, ...data.tree_members_node]) {
    const origin = posix.join(source, name);
    const target = posix.join(mount, name);
    if (!fs.existsSync(origin)) {
      continue;
    }
    if (isDir(origin)) {
      if (isDir(target)) {
        fs.rmSync(target, { recursive: true, force: true });
      }
      _copyTree(origin, target, data.copy_ignore);
    } else {
      fs.mkdirSync(posix.dirname(target), { recursive: true });
      fs.copyFileSync(origin, target);
    }
    copied += 1;
  }
  const gitignore = posix.join(mount, ".gitignore");
  if (!isFile(gitignore)) {
    writeText(gitignore, data.mount_gitignore);
  }
  _log(_mountText(data, "vendored", { count: String(copied), relative, version: String(version) }));
  return version;
}

/**
 * Refuse a mount-mode change without `--switch-mode`, or with the old mount still on disk between
 * two mounted modes: retiring it deletes tracked files and is the owner's commit (D5).
 * @param {InitData} data
 * @param {Attach} attach
 * @param {boolean} switchMode
 */
function _refuseUnreadySwitch(data, attach, switchMode) {
  if (!_switching(attach)) {
    return;
  }
  const previous = /** @type {string} */ (attach.previous);
  const mount = _mount(attach);
  const cli = mountedCli(data, attach.aitna);
  if (switchMode && _mounted(attach) && _nonEmptyDir(mount)) {
    const relative = posix.relative(attach.root, mount);
    throw new InitError(
      _mountText(data, "switch_old_mount", {
        previous: strRepr(previous),
        mode: strRepr(attach.mode),
        relative,
        removal: _oldMountRemoval(data, previous, relative),
        cli,
        target: attach.mode,
      }),
    );
  }
  if (!switchMode) {
    throw new InitError(
      _mountText(data, "switch_needs_flag", { previous: strRepr(previous), mode: strRepr(attach.mode), cli }),
    );
  }
}

/**
 * What a human must do after a mount-mode migration: re-point the hand-owned AGENTS.md block, and
 * in package mode remove the now-unused mount (`init.json`).
 * @param {InitData} data
 * @param {Attach} attach
 * @returns {string[]}
 */
function _modeSwitchSteps(data, { previous, mode, aitna }) {
  const base = mode === _PACKAGE_MODE ? `${aitna}/.akmon` : `${aitna}/akmon`;
  const resolution =
    mode === _PACKAGE_MODE
      ? data.mode_switch_link_resolution_package
      : fill(data.mode_switch_link_resolution_mounted, { aitna });
  const steps = [fill(data.mode_switch_step, { previous: String(previous), mode, base, link_resolution: resolution })];
  if (mode === _PACKAGE_MODE) {
    steps.push(fill(data.mode_switch_remove_mount, { aitna }));
  }
  return steps;
}

/**
 * `text` as one shell word: as written when it holds only safe characters, else quoted as
 * `shlex.quote` does — the Python `shell_word` (a `#` in mid-word is no comment, so
 * `npx github:<owner>/<name>#<ref>` prints as npm documents it).
 * @param {string} text
 * @returns {string}
 */
export function shellWord(text) {
  return /^[A-Za-z0-9_@%+=:,./#-]+$/.test(text) ? text : shlexJoin([text]);
}

/**
 * How `npx` names the akmon repository at `ref` (the Python `npx_spec`): `github:<owner>/<name>#<ref>`
 * for a GitHub URL, else the git URL npm resolves as written; a local path becomes a `file://` one.
 * @param {string} repo
 * @param {string} ref
 * @returns {string}
 */
export function npxSpec(repo, ref) {
  const match = repo.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+?)(?:\.git)?\/?$/);
  if (match !== null) {
    return `github:${match[1]}/${match[2]}#${ref}`;
  }
  return `git+${repo.startsWith("/") ? `file://${repo}` : repo}#${ref}`;
}

// --------------------------------------------------------------------------------------
// local layout + hand-owned documents
// --------------------------------------------------------------------------------------

/**
 * One agent charter (`init.json`), with the locate line picked by mount mode.
 * @param {InitData} data
 * @param {string} role
 * @param {string} focus
 * @param {string} aitna
 * @param {boolean} mounted
 * @returns {string}
 */
function _charter(data, role, focus, aitna, mounted) {
  const locate = fill(mounted ? data.charter_locate_mounted : data.charter_locate_package, { aitna, role });
  return fill(data.charter, { role, focus, locate });
}

/**
 * `existing` plus every wanted line it does not already carry, appended verbatim; never reorders
 * or rewrites what is there.
 * @param {string} existing
 * @param {string[]} wanted
 * @returns {string}
 */
export function mergeGitignore(existing, wanted) {
  const present = new Set(
    pySplitlines(existing)
      .map(pyStrip)
      .filter((line) => line !== ""),
  );
  const missing = wanted.filter((line) => pyStrip(line) === "" || !present.has(pyStrip(line)));
  // Drop leading/trailing blanks and collapse a run of them left by already-present lines.
  /** @type {string[]} */
  const trimmed = [];
  for (const line of missing) {
    if (pyStrip(line) === "" && (trimmed.length === 0 || pyStrip(trimmed[trimmed.length - 1]) === "")) {
      continue;
    }
    trimmed.push(line);
  }
  while (trimmed.length > 0 && pyStrip(trimmed[trimmed.length - 1]) === "") {
    trimmed.pop();
  }
  if (!trimmed.some((line) => pyStrip(line) !== "")) {
    return existing;
  }
  const prefix = existing.endsWith("\n") || existing === "" ? existing : `${existing}\n`;
  const separator = prefix !== "" && !prefix.endsWith("\n\n") ? "\n" : "";
  return `${prefix}${separator}${trimmed.join("\n")}\n`;
}

/**
 * The AGENTS.md akmon block (`init.json`); links and fragments computed here. In package mode links
 * name the GitHub repository at the pinned ref (there is no tree in the project to point at), in a
 * mounted mode the mount. `profiles` are the language profiles to import (`js.md`), one line each
 * right after the common guardrail, under the attach's prefix.
 * @param {InitData} data
 * @param {{aitna: string, repo: string, ref: string, archetype: string, language: string, profiles: readonly string[], mounted: boolean}} fields
 * @returns {string}
 */
function _agentsBlock(data, { aitna, repo, ref, archetype, language, profiles, mounted }) {
  /** @param {string} name */
  const link = (name) => (mounted ? `${aitna}/akmon/${name}` : `${repo}/blob/${ref}/${name}`);
  const rolesHint = fill(mounted ? data.agents_roles_hint_mounted : data.agents_roles_hint_package, {
    roles_link: link("roles/README.md"),
    aitna,
  });
  const sharedLayer = fill(mounted ? data.agents_shared_layer_mounted : data.agents_shared_layer_node, { aitna });
  const base = mounted ? `${aitna}/akmon` : `${aitna}/.akmon`;
  return fill(data.agents_block, {
    heading: blockHeading(readAlwaysLoadedData()),
    model: link("MODEL.md"),
    bootstrap: link("BOOTSTRAP.md"),
    readme: link("README.md"),
    archetypes: link("ARCHETYPES.md"),
    archetype,
    language,
    aitna,
    shared_layer: sharedLayer,
    roles_hint: rolesHint,
    guardrails_dir: `${base}/guardrails`,
    profiles_dir: `${base}/profiles`,
    profile_imports: profiles.map((profile) => `\n@${base}/profiles/${profile}`).join(""),
    pre_commit: link("pipelines/pre-commit.md"),
    review_flow: link("pipelines/review-flow.md"),
    design_flow: link("pipelines/design-flow.md"),
    code_flow: link("pipelines/code-flow.md"),
    tasks_link: link("pipelines/tasks.md"),
    memory_distill: link("pipelines/memory-distill.md"),
    learning: link("pipelines/learning.md"),
  });
}

/**
 * The language profiles a fresh block imports: the ones the flags and manifests call for. The
 * mapping is the standard tree's (`bin/sync.json`), so `init` writes exactly the imports `verify`
 * later expects.
 * @param {string} root
 * @param {string | undefined} archetype
 * @param {string | undefined} language
 * @returns {string[]}
 */
export function detectedProfiles(root, archetype, language) {
  const named = [archetype, language].filter((value) => value !== undefined && value !== "");
  return languageProfiles(readSyncData(), root, /** @type {string[]} */ (named)).map((found) => found.profile);
}

/**
 * Write `text` at `path` unless something is there.
 * @param {string} path
 * @param {string} text
 * @param {string} label
 * @returns {boolean} whether it wrote
 */
function _writeIfAbsent(path, text, label) {
  if (fs.existsSync(path)) {
    return false;
  }
  fs.mkdirSync(posix.dirname(path), { recursive: true });
  writeText(path, text);
  _log(`wrote ${label}`);
  return true;
}

/**
 * The dev layer's directories, task list, memory index and agent charters, each when absent.
 * @param {InitData} data
 * @param {Attach} attach
 */
function _writeLocalLayout(data, attach) {
  const { root, aitna } = attach;
  for (const name of ["agents", "skills", "tools", "memory"]) {
    fs.mkdirSync(posix.join(root, aitna, name), { recursive: true });
  }
  _writeIfAbsent(posix.join(root, aitna, "TASKS.md"), fill(data.tasks_skeleton, { aitna }), `${aitna}/TASKS.md`);
  _writeIfAbsent(posix.join(root, aitna, "memory", "README.md"), data.memory_index, `${aitna}/memory/README.md`);
  for (const [role, focus] of Object.entries(data.charters)) {
    _writeIfAbsent(
      posix.join(root, aitna, "agents", role, "README.md"),
      _charter(data, role, focus, aitna, _mounted(attach)),
      `${aitna}/agents/${role}/README.md`,
    );
  }
}

/**
 * Write AGENTS.md with the akmon block, or append the block; one already there stays untouched.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {string} block
 */
function _writeAgentsBlock(data, attach, block) {
  const agentsMd = posix.join(attach.root, "AGENTS.md");
  if (!isFile(agentsMd)) {
    writeText(agentsMd, data.agents_header + block);
    _log("wrote AGENTS.md with the akmon block");
    return;
  }
  const text = readText(agentsMd);
  if (text.includes(blockHeading(readAlwaysLoadedData()))) {
    _log("AGENTS.md already carries an akmon block — left untouched");
    if (!_switching(attach)) {
      const verify = _mounted(attach) ? `${mountedCli(data, attach.aitna)} verify --strict` : "akmon verify --strict";
      attach.nextSteps.push(`\`${verify}\` checks the existing AGENTS.md block against the contract`);
    }
    return;
  }
  const separator = text.endsWith("\n\n") ? "" : text.endsWith("\n") ? "\n" : "\n\n";
  writeText(agentsMd, text + separator + block);
  _log("appended the akmon block to AGENTS.md (existing content preserved)");
}

/**
 * Add the akmon entries the project's `.gitignore` lacks.
 * @param {InitData} data
 * @param {Attach} attach
 */
function _writeGitignore(data, { root, aitna }) {
  const gitignore = posix.join(root, ".gitignore");
  const existing = isFile(gitignore) ? readText(gitignore) : "";
  const merged = mergeGitignore(
    existing,
    data.gitignore_lines_node.map((line) => fill(line, { aitna })),
  );
  if (merged !== existing) {
    writeText(gitignore, merged);
    _log(".gitignore: added the akmon entries (secrets, Node dependencies, routing artifacts)");
  }
}

/**
 * Whether `directory` holds a workflow file (`*.yml` or `*.yaml`, hidden names and directories
 * included, as `Path.glob` lists them).
 * @param {string} directory
 * @returns {boolean}
 */
function _hasWorkflows(directory) {
  try {
    return fs.readdirSync(directory).some((name) => name.endsWith(".yml") || name.endsWith(".yaml"));
  } catch {
    return false;
  }
}

/**
 * Write the contract-check workflow, or name the step when the project's CI is its own.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {{noCi: boolean}} options
 */
function _writeCi(data, attach, { noCi }) {
  const { manager } = attach;
  const workflows = posix.join(attach.root, ".github", "workflows");
  const cli = mountedCli(data, attach.aitna);
  const [syncCmd, verifyCmd] = _mounted(attach)
    ? data.write_ci_commands.mounted_node.map((command) => fill(command, { cli }))
    : data.write_ci_commands.package.map((command) => manager.exec + command);
  if (noCi) {
    attach.nextSteps.push(`add the contract checks to CI: \`${syncCmd}\` and \`${verifyCmd}\``);
  } else if (_hasWorkflows(workflows)) {
    const verb =
      _switching(attach) || attach.ecosystemSwitch ? "update the akmon commands in" : "add the contract checks to";
    attach.nextSteps.push(`${verb} your existing workflow(s): \`${syncCmd}\` and \`${verifyCmd}\``);
  } else {
    const { setup, install } = ciInstall(manager, attach.root);
    const steps = _mounted(attach)
      ? fill(data.ci_workflow_steps_node_mounted, { cli })
      : fill(data.ci_workflow_steps_node, { setup, install, exec: manager.exec });
    _writeIfAbsent(
      posix.join(workflows, "akmon.yml"),
      fill(data.ci_workflow, { steps }),
      ".github/workflows/akmon.yml",
    );
  }
}

/**
 * Create or prepare `<AITNA_ROOT>/.akmon.toml`: a fresh record is written whole; an existing one is
 * upserted key by key, so a hand-written `[test].runner`, comments and every field this command
 * does not own survive. `last_realign` is left to {@link _markRealignComplete}.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {{version: string | null, archetype: string}} fields
 * @returns {string} the record's path
 */
function _writeAkmonToml(data, { root, aitna, mode, manager }, { version, archetype }) {
  const path = posix.join(root, aitna, ".akmon.toml");
  if (!isFile(path)) {
    const recorded = version ? fill(data.record_version_line, { version }) : "";
    fs.mkdirSync(posix.dirname(path), { recursive: true });
    writeText(path, fill(data.record_fresh_node, { mode, recorded, archetype, runner: manager.test }));
    return path;
  }
  let text = readText(path);
  const fields = readAkmonToml(path);
  text = upsertTomlKey(text, "mount", mode);
  text = upsertTomlKey(text, "ecosystem", "node");
  if (version) {
    text = upsertTomlKey(text, "akmon_version", version);
  }
  if (!truthy(fields["attached_archetype"])) {
    text = upsertTomlKey(text, "attached_archetype", archetype);
  }
  fs.mkdirSync(posix.dirname(path), { recursive: true });
  writeText(path, text);
  return path;
}

/**
 * Advance the completion marker after every generated stage has succeeded.
 * @param {string} path
 * @param {string | null} version
 */
function _markRealignComplete(path, version) {
  if (!version) {
    return;
  }
  writeText(path, upsertTomlKey(readText(path), "last_realign", version));
}

// --------------------------------------------------------------------------------------
// what `akmon check` runs
// --------------------------------------------------------------------------------------

const _JS_TS = ["*.js", "*.mjs", "*.cjs", "*.jsx", "*.ts", "*.mts", "*.cts", "*.tsx"];

/**
 * The JS/TS linters and analyzers a project can be configured for, in record order: how each
 * announces its configuration (`files` exact names, `prefixes` for `<prefix>` or `<prefix>.*`,
 * `manifestKey` a top-level `package.json` key), the command after the manager's run prefix, and
 * the file patterns a run covers (`null`: the command takes no `{files}`).
 * @type {{name: string, files: string[], prefixes: string[], manifestKey: string | null, command: string, patterns: string[] | null}[]}
 */
const _NODE_TOOLS = [
  {
    name: "eslint",
    files: [
      "eslint.config.js",
      "eslint.config.mjs",
      "eslint.config.cjs",
      "eslint.config.ts",
      "eslint.config.mts",
      "eslint.config.cts",
    ],
    prefixes: [".eslintrc"],
    manifestKey: "eslintConfig",
    command: "eslint {files}",
    patterns: _JS_TS,
  },
  {
    name: "biome",
    files: ["biome.json", "biome.jsonc"],
    prefixes: [],
    manifestKey: null,
    command: "biome check {files}",
    patterns: [..._JS_TS, "*.json"],
  },
  {
    name: "oxlint",
    files: [".oxlintrc.json"],
    prefixes: [],
    manifestKey: null,
    command: "oxlint {files}",
    patterns: _JS_TS,
  },
  {
    name: "prettier",
    files: [],
    prefixes: [".prettierrc", "prettier.config"],
    manifestKey: "prettier",
    command: "prettier --check {files}",
    patterns: [..._JS_TS, "*.json", "*.css", "*.md"],
  },
  // tsc given files ignores tsconfig.json, so it takes none and is recorded as a plain string
  {
    name: "tsc",
    files: ["tsconfig.json"],
    prefixes: [],
    manifestKey: null,
    command: "tsc --noEmit -p .",
    patterns: null,
  },
];

/**
 * The parsed `package.json` of the project; `{}` when there is none or it is not a JSON object.
 * @param {string} root
 * @returns {Record<string, unknown>}
 */
function _manifest(root) {
  const path = posix.join(root, "package.json");
  if (!isFile(path)) {
    return {};
  }
  try {
    const document = JSON.parse(readText(path));
    return document !== null && typeof document === "object" && !Array.isArray(document) ? document : {};
  } catch (error) {
    if (!(error instanceof SyntaxError) && /** @type {{name?: string}} */ (error).name !== "UnicodeDecodeError") {
      throw error;
    }
    return {};
  }
}

/**
 * The tools the project is configured for, in table order — files only, nothing is run.
 * @param {string} root
 * @returns {{name: string, command: string, patterns: string[] | null}[]}
 */
export function detectNodeTools(root) {
  /** @type {string[]} */
  let names;
  try {
    names = fs.readdirSync(root);
  } catch {
    names = [];
  }
  const manifest = _manifest(root);
  return _NODE_TOOLS.filter(
    (tool) =>
      tool.files.some((file) => isFile(posix.join(root, file))) ||
      names.some((name) =>
        tool.prefixes.some(
          (prefix) => (name === prefix || name.startsWith(`${prefix}.`)) && isFile(posix.join(root, name)),
        ),
      ) ||
      (tool.manifestKey !== null && Object.hasOwn(manifest, tool.manifestKey)),
  );
}

/**
 * One `[check]` entry: an inline table with `files` when the command takes `{files}`, else a plain string.
 * @param {string} name
 * @param {string} command
 * @param {string[] | null} patterns
 * @returns {string}
 */
function _checkLine(name, command, patterns) {
  if (patterns === null) {
    return `${name} = ${JSON.stringify(command)}`;
  }
  return `${name} = { command = ${JSON.stringify(command)}, files = [${patterns.map((p) => JSON.stringify(p)).join(", ")}] }`;
}

const _LINTERS = ["eslint", "biome", "oxlint"];

/**
 * The owner's answer when `--checks` is absent: the project's own tools when it has a linter, else
 * akmon's rules; the defaults when nobody is asked.
 * @param {{name: string}[]} tools
 * @param {boolean} ask
 * @returns {string}
 */
function _chooseChecks(tools, ask) {
  const names = tools.map((tool) => tool.name).join(", ");
  if (tools.some((tool) => _LINTERS.includes(tool.name))) {
    if (!ask || _confirm(`akmon init: \`akmon check\` runs the project's own ${names}?`)) {
      return "own";
    }
    return _confirm("akmon init: set up oxlint with akmon's JavaScript/TypeScript rules instead?") ? "akmon" : "none";
  }
  if (
    !ask ||
    _confirm(
      "akmon init: no JavaScript/TypeScript linter configured — set up oxlint with akmon's JavaScript/TypeScript rules?",
    )
  ) {
    return "akmon";
  }
  return tools.length > 0 ? "own" : "none";
}

/**
 * Point the project's oxlint configuration at akmon's rules — the standard `extends`. Absent
 * `.oxlintrc.json` is written; a present one is never edited: it either extends the rules already or
 * gets a next step.
 * @param {InitData} data
 * @param {Attach} attach
 */
function _extendWithAkmonRules(data, attach) {
  const { root, nextSteps } = attach;
  const path = posix.join(root, ".oxlintrc.json");
  const rules = _mounted(attach)
    ? fill(data.node_oxlint_rules_mounted, { aitna: attach.aitna })
    : data.node_oxlint_rules;
  if (isFile(path)) {
    if (!readText(path).includes(rules)) {
      nextSteps.push(fill(data.node_oxlintrc_own_step, { rules }));
    }
    return;
  }
  writeText(path, fill(data.node_oxlintrc_text, { rules }));
  _log(fill(data.node_oxlintrc_wrote, { rules }));
  nextSteps.push(data.node_oxlintrc_env_step);
}

/**
 * The next step that makes oxlint runnable, when package.json does not declare it yet.
 * @param {InitData} data
 * @param {Attach} attach
 * @returns {string | null}
 */
function _oxlintStep(data, { root, manager }) {
  const manifest = _manifest(root);
  const declared = ["devDependencies", "dependencies"].some((key) => {
    const table = manifest[key];
    return table !== null && typeof table === "object" && Object.hasOwn(table, "oxlint");
  });
  return declared ? null : fill(data.node_oxlint_step, { command: `${manager.add_dev_exact} oxlint` });
}

/**
 * The `[check]` entries and the closing next steps of the chosen mode: `own` records every
 * detected tool; `akmon` sets up the extends and records oxlint first, then the detected non-linters.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {string} choice
 * @param {ReturnType<typeof detectNodeTools>} tools
 * @returns {ReturnType<typeof detectNodeTools>}
 */
function _checkEntries(data, attach, choice, tools) {
  if (choice === "own") {
    return tools;
  }
  _extendWithAkmonRules(data, attach);
  const step = _oxlintStep(data, attach);
  if (step !== null) {
    attach.nextSteps.push(step);
  }
  const oxlint = /** @type {(typeof _NODE_TOOLS)[number]} */ (_NODE_TOOLS.find((tool) => tool.name === "oxlint"));
  return [oxlint, ...tools.filter((tool) => !_LINTERS.includes(tool.name))];
}

/** The comment line every `[check]` table `init` writes opens with, in both implementations. */
const _CHECK_COMMENT =
  "# What `akmon check` runs: the project's own commands, `{files}` becoming the files a run covers.";

/**
 * `text`, the record, with its `[check]` table cut out when that table is exactly the ruff default
 * the Python `init` records for `--checks akmon` — the comment line and `ruff = "<prefix>ruff check
 * {files}"`, the prefix one of `run_prefix` or none, blank lines aside — else `null`: any other
 * content, a sub-table or a second table included, is the owner's (C123) and stays.
 * @param {InitData} data
 * @param {string} text
 * @returns {string | null}
 */
export function withoutRuffDefault(data, text) {
  const defaults = ["", ...Object.values(data.run_prefix)].map((prefix) => [
    _CHECK_COMMENT,
    `ruff = ${JSON.stringify(`${prefix}ruff check {files}`)}`,
  ]);
  return _withoutCheckTable(text, (body) =>
    defaults.some((expected) => expected.length === body.length && expected.every((line, i) => line === body[i])),
  );
}

/**
 * `text`, the record, with its `[check]` table cut out when the table records nothing — comment
 * lines only, blank lines aside, as `--checks none` or `own` with nothing found writes it — else
 * `null`. An explicit `--checks` decides such a table again (F4 of the C129 audit).
 * @param {string} text
 * @returns {string | null}
 */
export function withoutEmptyChecks(text) {
  return _withoutCheckTable(text, (body) => body.every((line) => line.startsWith("#")));
}

/**
 * `text` with its one `[check]` table cut out when `matches` accepts the table's lines (trimmed,
 * blank ones dropped), else `null`: a sub-table or a second table is the owner's (C123) and stays.
 * @param {string} text
 * @param {(body: string[]) => boolean} matches
 * @returns {string | null}
 */
function _withoutCheckTable(text, matches) {
  const lines = text.split("\n");
  const headers = lines.filter((line) => /^\s*\[\[?\s*check\s*[.\]]/.test(line));
  const start = lines.findIndex((line) => line.trimEnd() === "[check]");
  if (start === -1 || headers.length !== 1) {
    return null;
  }
  let end = lines.findIndex((line, index) => index > start && /^\s*\[/.test(line));
  if (end === -1) {
    end = lines.length;
  }
  const body = lines
    .slice(start + 1, end)
    .map((line) => line.trimEnd())
    .filter((line) => line !== "");
  if (!matches(body)) {
    return null;
  }
  return [...lines.slice(0, start), ...lines.slice(end)].join("\n");
}

/**
 * Append the `[check]` table holding `lines` to the record — empty when there are none (the Python
 * `_record_checks`).
 * @param {string[]} lines the table's entries
 * @param {string} record the record's path
 */
function _recordChecks(lines, record) {
  const table = ["", "[check]", _CHECK_COMMENT, ...lines];
  writeText(record, `${readText(record).replace(/\s+$/, "")}\n${table.join("\n")}\n`);
}

/**
 * Decide once what `akmon check` runs and record it as `[check]` (the Python `_setup_checks`, Node
 * variant): the project's own tools, or oxlint with akmon's rules, or nothing — `none`, or `own`
 * when no tool is found — recorded as an empty `[check]` table, so it is a choice like the others. A
 * record that already has a `[check]` table is left alone: a realign never changes that choice; a
 * record written before an empty table meant nothing has no table and is decided again. The move of
 * a Python record to Node decides again a table that is exactly the Python's ruff default
 * ({@link withoutRuffDefault}), and keeps any other; an explicit `--checks` decides again a table
 * that records nothing ({@link withoutEmptyChecks}). The project's `lint` / `typecheck` scripts
 * become a next step.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {string} record the record's path
 * @param {string | undefined} choice `--checks`
 * @param {{ask: boolean}} options
 */
function _setupChecks(data, attach, record, choice, { ask }) {
  const { root, nextSteps, manager } = attach;
  if (attach.ecosystemSwitch) {
    const cleared = withoutRuffDefault(data, readText(record));
    if (cleared !== null) {
      writeText(record, cleared);
      _log(data.node_switch_checks_redecided);
    }
  }
  if (choice !== undefined) {
    // the owner asks again: an explicit --checks decides a table that records nothing once more
    const cleared = withoutEmptyChecks(readText(record));
    if (cleared !== null) {
      writeText(record, cleared);
      _log(data.checks_redecided_empty);
    }
  }
  if (/^\[check\]/m.test(readText(record))) {
    _log("[check] already names this project's checks — left untouched");
    return;
  }
  const tools = detectNodeTools(root);
  const chosen = choice ?? _chooseChecks(tools, ask);
  const recordName = posix.basename(record);
  if (chosen === "none") {
    _recordChecks([], record);
    _log("akmon check: no checks recorded");
    nextSteps.push(`name the project's checks under \`[check]\` in ${recordName} when it has any`);
  } else if (chosen === "own" && tools.length === 0) {
    _recordChecks([], record);
    nextSteps.push(`no linter configuration was found: name the project's checks under \`[check]\` in ${recordName}`);
  } else {
    const entries = _checkEntries(data, attach, chosen, tools);
    _recordChecks(
      entries.map((tool) => _checkLine(tool.name, manager.check_run + tool.command, tool.patterns)),
      record,
    );
    _log(`akmon check will run: ${entries.map((tool) => tool.name).join(", ")} (recorded as [check])`);
  }
  const scripts = _manifest(root).scripts;
  const present = ["lint", "typecheck"].filter(
    (script) => scripts !== null && typeof scripts === "object" && Object.hasOwn(scripts, script),
  );
  if (present.length > 0) {
    nextSteps.push(
      fill(data.node_scripts_step, {
        names: present.map((script) => `\`${script}\``).join(", "),
        record: recordName,
        example: `${manager.run_script} ${present[0]}`,
      }),
    );
  }
}

// --------------------------------------------------------------------------------------
// the generated surface, the closing steps, the report
// --------------------------------------------------------------------------------------

/**
 * Run sync, then the model-routing initializer; the first failing exit code, else 0. Both run in
 * this process in package mode. In a mounted mode the mount's own CLI and initializer run them as
 * child processes, after the version-skew notice — the pin governs from here on, as the Python
 * dispatches its sync to the mount's launcher (ADR 0009 decision 5). That holds when the mount is
 * the running tree too: a `--ref` checkout has just replaced the files this process loaded, and only
 * a fresh process runs the code the pin names.
 * @param {Attach} attach
 * @returns {Promise<number>}
 */
async function _generate(attach) {
  const { root } = attach;
  const mount = _mounted(attach) ? _mount(attach) : null;
  _log("running sync (generated pointers, hook wiring, imported guardrails)");
  let code;
  if (mount === null) {
    code = syncMain(["--project-root", root]);
  } else {
    const notice = skewNotice(mount);
    if (notice !== null) {
      process.stderr.write(`${notice}\n`);
    }
    code = runMountedScript(mount, CLI_PATH, ["sync", "--project-root", root], root);
  }
  if (code !== 0) {
    process.stderr.write(`akmon init: sync failed (${code}); the attach is incomplete\n`);
    return code;
  }
  _log("running model-routing init (subagent definitions + local routing config)");
  if (mount === null) {
    const routing = await import("../tools/model_routing/init.mjs");
    code = await routing.main(["--project-root", root]);
  } else {
    code = runMountedScript(mount, "js/tools/model_routing/init.mjs", ["--project-root", root], root);
  }
  if (code !== 0) {
    process.stderr.write(`akmon init: model-routing init failed (${code})\n`);
    return code;
  }
  return 0;
}

/**
 * The step a Node attach needs for its manifest pin status; `null` when the status (`dev`) names none.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {string} pinStatus
 * @param {string | null} version
 * @returns {string | null}
 */
function _pinStep(data, { manager }, pinStatus, version) {
  const template = Object.hasOwn(data.pin_step_node, pinStatus) ? data.pin_step_node[pinStatus] : undefined;
  if (template === undefined) {
    return null;
  }
  return fill(template, { command: `${manager.add_dev_exact} akmon${version ? `@${version}` : ""}` });
}

/**
 * Whether the project's `ruff.toml` is byte for byte the one the Python `init` writes, for either
 * mode's rules path (`ruffTomlTemplates`): the file the move to Node names for removal.
 * @param {Attach} attach
 * @returns {boolean}
 */
function _isRuffTemplate({ root, aitna }) {
  const path = posix.join(root, "ruff.toml");
  if (!isFile(path)) {
    return false;
  }
  const content = fs.readFileSync(path);
  return ruffTomlTemplates(readSyncData(), aitna).some((template) => template.equals(content));
}

/**
 * The judgment steps `init` deliberately did not take, a missing pin first. Classifying stays a step
 * while the archetype is unclassified or no language profile was detected — the block then imports
 * none, and only a person can say which one it needs. With a profile already imported the step asks
 * for the archetype alone (C127).
 * @param {InitData} data
 * @param {Attach} attach
 * @param {{archetype: string, profiles: readonly string[], pinStatus: string, version: string | null}} state
 */
function _addClosingSteps(data, attach, { archetype, profiles, pinStatus, version }) {
  const { aitna, nextSteps, manager } = attach;
  const steps = data.closing_steps;
  if (archetype === "unclassified" || profiles.length === 0) {
    const classify = profiles.length > 0 ? steps["classify_archetype"] : steps["classify"];
    nextSteps.unshift(fill(classify, { aitna }));
  }
  nextSteps.push(fill(steps["pin_test_node"], { aitna, test: manager.test }));
  const pinStep = _mounted(attach) ? null : _pinStep(data, attach, pinStatus, version);
  if (pinStep) {
    nextSteps.unshift(pinStep);
  }
  if (aitna !== AITNA_ROOT_DEFAULT) {
    nextSteps.push(fill(steps["export_aitna"], { aitna }));
  }
  if (attach.ecosystemSwitch) {
    nextSteps.push(data.node_switch_codex_step);
    if (_isRuffTemplate(attach)) {
      nextSteps.push(data.node_switch_ruff_step);
    }
  }
  if (_mounted(attach)) {
    // akmon does not edit the project's package.json: a script entry is offered, never written.
    const cli = mountedCli(data, aitna);
    nextSteps.push(fill(steps["node_mounted_script"], { cli, run_script: manager.run_script }));
    nextSteps.push(fill(steps["verify_node_mounted"], { cli }));
  } else {
    nextSteps.push(fill(steps["verify_node"], { exec: manager.exec }));
  }
}

/**
 * Print the steps left; exit 1 while a package attach has no `devDependencies` pin it can run from.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {{pinStatus: string, record: string, version: string | null}} state
 * @returns {number}
 */
function _report(data, attach, { pinStatus, record, version }) {
  // The manifest pin *is* the mount: an attach that ends without one looks attached and cannot
  // run a single akmon command, so the exit code says so rather than reporting success.
  const incomplete = !_mounted(attach) && pinStatus !== "dev";
  const report = data.report;
  process.stdout.write("\n");
  _log(incomplete ? report.incomplete : report.complete);
  attach.nextSteps.forEach((step, index) => {
    process.stdout.write(`${fill(report.step, { index: String(index + 1), step })}\n`);
  });
  if (incomplete) {
    const key = pinStatus === "unreadable" ? "unreadable" : "absent";
    process.stdout.write("\n");
    _log(fill(report.exit, { missing: data.report_missing_node[key], remedy: report.remedy[key] }));
    return 1;
  }
  _markRealignComplete(record, version);
  return 0;
}

// --------------------------------------------------------------------------------------
// the command
// --------------------------------------------------------------------------------------

/** What `-h` / `--help` prints (the Python has `argparse`'s own block). */
const USAGE = `usage: akmon init [-h] [--mode {submodule,vendored,subtree,package}]
                  [--aitna-root AITNA_ROOT] [--project-root PROJECT_ROOT]
                  [--repo REPO] [--ref REF] [--archetype ARCHETYPE]
                  [--language LANGUAGE] [--no-ci] [--ecosystem {python,node}]
                  [--checks {own,akmon,none}] [--switch-mode] [--yes]

Attach the akmon standard to a Node project.

options:
  -h, --help            show this help message and exit
  --mode {submodule,vendored,subtree,package}
                        Mount mode. Default: the recorded one, else package.
  --aitna-root AITNA_ROOT
                        Dev-layer root, project-root-relative (default: _aitna).
  --project-root PROJECT_ROOT
                        Project to attach to. Defaults to the current directory.
  --repo REPO           akmon repository URL a submodule or subtree is taken from
                        (package mode: accepted; the AGENTS.md links name the standard one).
  --ref REF             Ref to pin in a mounted mode (default: the latest release tag);
                        in package mode the ref the AGENTS.md links name (default: the
                        tag of the installed version).
  --archetype ARCHETYPE
                        Archetype id per ARCHETYPES.md (default: left unclassified).
  --language LANGUAGE   Primary language per ARCHETYPES.md (default: left unclassified).
  --no-ci               Do not write a CI workflow running sync/verify.
  --ecosystem {python,node}
                        The implementation that serves the project. Default on a
                        first attach: node in package mode, and in a mounted mode
                        for a repository with package.json and no Python files;
                        a recorded attach keeps its own. python is served by the
                        Python implementation, which this command names.
  --checks {own,akmon,none}
                        What \`akmon check\` runs: the project's own linters
                        (default when it has any), oxlint with akmon's
                        JavaScript/TypeScript rules (default when it has
                        none), or nothing.
  --switch-mode         Allow changing the recorded mount mode (a migration: it
                        needs manual AGENTS.md edits).
  --yes                 Do not ask for confirmation.
`;

/**
 * @typedef {object} InitOptions
 * @property {string | undefined} mode
 * @property {string | undefined} aitnaRoot
 * @property {string | undefined} projectRoot
 * @property {string | undefined} repo
 * @property {string | undefined} ref
 * @property {string | undefined} archetype
 * @property {string | undefined} language
 * @property {boolean} noCi
 * @property {string | undefined} ecosystem
 * @property {string | undefined} checks
 * @property {boolean} switchMode
 * @property {boolean} yes
 * @property {boolean} help
 */

/**
 * `argparse`'s sentence for a value outside a flag's choices.
 * @param {string} flag
 * @param {string} value
 * @param {string[]} choices
 * @returns {string}
 */
function _invalidChoice(flag, value, choices) {
  return `argument ${flag}: invalid choice: ${strRepr(value)} (choose from ${choices.map(strRepr).join(", ")})`;
}

/**
 * Parse the arguments after `init`.
 * @param {string[]} argv
 * @returns {InitOptions | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        mode: { type: "string" },
        "aitna-root": { type: "string" },
        "project-root": { type: "string" },
        repo: { type: "string" },
        ref: { type: "string" },
        archetype: { type: "string" },
        language: { type: "string" },
        "no-ci": { type: "boolean" },
        ecosystem: { type: "string" },
        checks: { type: "string" },
        "switch-mode": { type: "boolean" },
        yes: { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    const mode = /** @type {string | undefined} */ (values.mode);
    if (mode !== undefined && !MODES.includes(mode)) {
      return _invalidChoice("--mode", mode, MODES);
    }
    const ecosystem = /** @type {string | undefined} */ (values.ecosystem);
    if (ecosystem !== undefined && !ECOSYSTEMS.includes(ecosystem)) {
      return _invalidChoice("--ecosystem", ecosystem, ECOSYSTEMS);
    }
    const checks = /** @type {string | undefined} */ (values.checks);
    if (checks !== undefined && !CHECK_CHOICES.includes(checks)) {
      return _invalidChoice("--checks", checks, CHECK_CHOICES);
    }
    return {
      mode,
      aitnaRoot: /** @type {string | undefined} */ (values["aitna-root"]),
      projectRoot: /** @type {string | undefined} */ (values["project-root"]),
      repo: /** @type {string | undefined} */ (values.repo),
      ref: /** @type {string | undefined} */ (values.ref),
      archetype: /** @type {string | undefined} */ (values.archetype),
      language: /** @type {string | undefined} */ (values.language),
      noCi: values["no-ci"] === true,
      ecosystem,
      checks,
      switchMode: values["switch-mode"] === true,
      yes: values.yes === true,
      help: values.help === true,
    };
  } catch (exc) {
    const code = /** @type {{code?: string}} */ (exc).code;
    if (typeof code !== "string" || !code.startsWith("ERR_PARSE_ARGS_")) {
      throw exc;
    }
    // parseArgs words some errors over several lines (the hint for the fix); the first is the fact.
    return /** @type {Error} */ (exc).message.split("\n")[0];
  }
}

/**
 * Whether the project has `package.json` and no Python (`hasPython`, the one answer; the Python
 * `_node_without_python`).
 * @param {string} root
 * @param {string} aitna the dev layer, which holds no project code
 * @returns {boolean}
 */
export function nodeWithoutPython(root, aitna) {
  return isFile(posix.join(root, "package.json")) && !hasPython(readSyncData(), root, aitna);
}

/**
 * The ecosystem a first attach serves, and the `node_refuses_python_why` key that says why it is
 * Python: `--ecosystem` when given; mode `package` is the npm carrier's own, so Node; a mounted
 * mode follows the files, Node only for `package.json` with no Python files (the C129 amendment of
 * ADR 0020 D02 — the Python `_first_attach_ecosystem`).
 * @param {string} root
 * @param {string | undefined} flag
 * @param {string} mode
 * @param {string} aitna
 * @returns {{ecosystem: string, why: string}}
 */
export function firstAttachEcosystem(root, flag, mode, aitna) {
  if (flag !== undefined) {
    return { ecosystem: flag, why: "flag" };
  }
  if (mode === _PACKAGE_MODE || nodeWithoutPython(root, aitna)) {
    return { ecosystem: _NODE, why: "inferred" };
  }
  return { ecosystem: "python", why: "inferred" };
}

/**
 * The Python init command a Python attach is the implementation of, with the flags this run was
 * given that it needs: `uvx` from the repository at the run's ref (the Python's own first attach).
 * @param {InitData} data
 * @param {InitOptions} options
 * @param {string} mode
 * @returns {string}
 */
function _pythonCommand(data, options, mode) {
  const repo = options.repo ?? data.akmon_repo;
  const ref = options.ref || tagForVersion(installedAkmonVersion());
  const command = ["uvx", "--from", `git+${repo}@${ref}`, "akmon", "init", "--mode", mode];
  if (options.aitnaRoot) {
    command.push("--aitna-root", options.aitnaRoot);
  }
  return command.map(shellWord).join(" ");
}

/**
 * The ref a printed vendored switch names (the Python `_switch_ref`): `switchTag`, the one rule —
 * the newer of the release the record names and this implementation's (C129).
 * @param {string} root
 * @param {string} aitna
 * @returns {string}
 */
function _switchRef(root, aitna) {
  const recorded = readAkmonToml(posix.join(root, aitna, ".akmon.toml"))["akmon_version"];
  return switchTag(typeof recorded === "string" ? recorded : null, installedAkmonVersion());
}

/**
 * The command that moves a Python-mounted record to `ecosystem = "node"` (the Python
 * `node_switch_command`): the mount's own CLI for a submodule or a subtree, which are whole
 * checkouts; `npx` from the repository at `ref` (`_switchRef`) for a vendored copy, which a Python
 * attach made without the data this CLI reads (`tree_members_node`) — that init re-vendors it whole.
 * @param {InitData} data
 * @param {string} aitna
 * @param {string} mode
 * @param {string} ref
 * @returns {string}
 */
export function nodeSwitchCommand(data, aitna, mode, ref) {
  const base = mode === "vendored" ? ["npx", npxSpec(data.akmon_repo, ref)] : mountedCli(data, aitna).split(" ");
  return [...base, "init", "--ecosystem", _NODE].map(shellWord).join(" ");
}

/**
 * Whether the project's record is a mounted attach of the Python implementation — the one record
 * `--ecosystem node` moves to this implementation.
 * @param {string} root
 * @param {string | null} previous the recorded mount mode
 * @returns {boolean}
 */
function _pythonMount(root, previous) {
  return previous !== null && previous !== _PACKAGE_MODE && recordedEcosystem(root) === "python";
}

/**
 * A data file of the mount as the switch will find it: at `ref` when the run moves a submodule
 * there (`git show`), else on disk; `null` when it is absent or no JSON object.
 * @param {string} mount
 * @param {string} relative
 * @param {string | null} ref
 * @returns {Record<string, unknown> | null}
 */
function _mountDataFile(mount, relative, ref) {
  let text;
  if (ref === null) {
    try {
      text = fs.readFileSync(posix.join(mount, relative), "utf8");
    } catch {
      return null;
    }
  } else {
    const shown = _spawn(["git", "show", `${ref}:${relative}`], { cwd: mount, capture: true });
    if (shown.status !== 0) {
      return null;
    }
    text = shown.stdout;
  }
  try {
    const parsed = JSON.parse(text);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Refuse the move of a Python record to Node when the submodule or subtree mount predates the
 * release that has the move (C129): the switch rewrites the record and the wiring, then runs the
 * mount's own sync and routing initializer, so a mount without the data they read would stop it
 * half done. Asked of the data, not a version: the mount lacks a key of `node_switch_requires` —
 * at `--ref` when the run moves a submodule to a ref the mount has. A vendored copy is replaced by
 * this tree, so it is never too old. Raised before anything is written.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {InitOptions} options
 */
function _refuseMountPredatingSwitch(data, attach, options) {
  const { root, aitna, mode } = attach;
  const mount = _mount(attach);
  if (!attach.ecosystemSwitch || mode === "vendored" || !_nonEmptyDir(mount)) {
    return;
  }
  const moving = mode === "submodule" && options.ref ? options.ref : null;
  const ref =
    moving !== null && _gitOutput(["rev-parse", "--verify", "--quiet", `${moving}^{commit}`], mount) !== null
      ? moving
      : null;
  for (const [file, key] of Object.entries(data.node_switch_requires)) {
    const found = _mountDataFile(mount, file, ref);
    if (found !== null && Object.hasOwn(found, key)) {
      continue;
    }
    const relative = posix.relative(root, mount);
    const target = _switchRef(root, aitna);
    const repo = options.repo ?? data.akmon_repo;
    const update = fill(data.node_switch_mount_update[mode], { relative, ref: target, repo });
    const command =
      nodeSwitchCommand(data, aitna, mode, target) + (mode === "subtree" ? ` --ref ${shellWord(target)}` : "");
    throw new InitError(fill(data.node_switch_mount_predates, { relative, file, key, ref: target, update, command }));
  }
}

/**
 * The refusals of a run this implementation does not serve, raised before anything is touched: a
 * record that is not Node (`unsupportedFound`) — unless it is a Python mount `--ecosystem node`
 * moves here, between two mounted modes — a Node record asked to go back to Python, a first attach
 * that is the Python implementation's, a mount-mode migration not asked for, a submodule or subtree
 * mount that predates the move to Node.
 * @param {InitData} data
 * @param {InitOptions} options
 * @param {Attach} attach
 */
function _refuseUnservedRun(data, options, attach) {
  const { root, aitna, mode, previous } = attach;
  if (isFile(posix.join(root, aitna, ".akmon.toml"))) {
    const found = unsupportedFound(readSyncData(), root);
    if (found !== null && options.ecosystem === _NODE && recordedEcosystem(root) === "python") {
      if (!_pythonMount(root, previous) || !_mounted(attach)) {
        throw new InitError(fill(data.node_switch_mounted_only, { previous: String(previous), mode }));
      }
    } else if (found !== null) {
      let refusal = fill(data.node_refuses_record, { found });
      if (_pythonMount(root, previous) && nodeWithoutPython(root, aitna)) {
        const command = nodeSwitchCommand(data, aitna, String(previous), _switchRef(root, aitna));
        refusal += fill(data.node_refuses_record_switch, { command });
      }
      throw new InitError(refusal);
    }
    if (options.ecosystem === "python") {
      throw new InitError(fill(data.node_refuses_reverse, { aitna }));
    }
  } else {
    const { ecosystem, why } = firstAttachEcosystem(root, options.ecosystem, mode, aitna);
    if (ecosystem !== _NODE) {
      throw new InitError(
        fill(data.node_refuses_python_ecosystem, {
          why: data.node_refuses_python_why[why],
          command: _pythonCommand(data, options, mode),
        }),
      );
    }
  }
  _refuseUnreadySwitch(data, attach, options.switchMode);
  _refuseMountPredatingSwitch(data, attach, options);
}

/**
 * Attach the standard to the Node project named by `argv`.
 * @param {string[]} [argv] the arguments after `init` (default: the process's)
 * @returns {Promise<number>} The process exit code: 0 when complete, 1 while a package attach has no
 *   `devDependencies` pin (or the owner declined), 2 for a usage error or a refusal.
 */
export async function main(argv = process.argv.slice(2)) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`akmon init: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }
  const root = resolvePath(options.projectRoot ?? process.cwd());
  if (!isDir(root)) {
    process.stderr.write(`akmon init: ${root} is not a directory\n`);
    return 2;
  }
  const data = readInitData();
  // Every path in the tooling derives from this variable (sync, the routing initializer and the
  // hooks read it at call time), so it is set once, validated, for the whole in-process run and
  // given back afterwards.
  const previousEnv = process.env.AITNA_ROOT;
  try {
    return await _run(data, options, root);
  } catch (error) {
    if (error instanceof InitError) {
      process.stderr.write(`akmon init: ${error.message}\n`);
      return 2;
    }
    throw error;
  } finally {
    if (previousEnv === undefined) {
      delete process.env.AITNA_ROOT;
    } else {
      process.env.AITNA_ROOT = previousEnv;
    }
  }
}

/**
 * Mount the standard in `attach.mode`: the version to record, and the manifest pin's status. Only
 * mode `package` pins akmon in the project's manifest; a mounted tree reports `dev`.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {InitOptions} options
 * @returns {{version: string | null, pinStatus: string}}
 */
function _mountStandard(data, attach, options) {
  const repo = options.repo ?? data.akmon_repo;
  if (attach.mode === "submodule") {
    return { version: _mountSubmodule(data, attach, repo, options.ref), pinStatus: "dev" };
  }
  if (attach.mode === "subtree") {
    return { version: _mountSubtree(data, attach, repo, options.ref), pinStatus: "dev" };
  }
  if (attach.mode === "vendored") {
    return { version: _mountVendored(data, attach, options.ref, installedAkmonVersion()), pinStatus: "dev" };
  }
  return { version: installedAkmonVersion(), pinStatus: packagePinStatus(attach.root) };
}

/**
 * The run proper: plan and refuse, confirm, mount, write the layout and documents, generate, report.
 * @param {InitData} data
 * @param {InitOptions} options
 * @param {string} root
 * @returns {Promise<number>}
 */
async function _run(data, options, root) {
  const aitna = effectiveAitnaRoot(options.aitnaRoot, root);
  process.env.AITNA_ROOT = aitna;
  const previous = isFile(posix.join(root, aitna, ".akmon.toml")) ? recordedMount(root) : null;
  /** @type {[string, string]} */
  const [mode, reason] =
    options.mode !== undefined
      ? [options.mode, "requested"]
      : previous !== null && MODES.includes(previous)
        ? [previous, "recorded"]
        : [_PACKAGE_MODE, data.node_mode_reason];
  /** @type {Attach} */
  const attach = {
    root,
    aitna,
    mode,
    previous,
    ecosystemSwitch: options.ecosystem === _NODE && _pythonMount(root, previous),
    manager: data.node_managers[detectManager(data, root)],
    nextSteps: [],
  };
  _refuseUnservedRun(data, options, attach);

  _log(`attaching to ${root}`);
  _log(`mount mode: ${mode} (${reason}) · dev layer: ${aitna}/`);
  if (attach.ecosystemSwitch) {
    _log(fill(data.node_switch_log, { aitna }));
  }
  if (_switching(attach)) {
    _log(`migrating the mount mode: ${previous} → ${mode}`);
  }
  if (!options.yes && !_confirm(`akmon init: attach akmon to ${root}?`)) {
    process.stderr.write("akmon init: aborted\n");
    return 1;
  }
  const { version, pinStatus } = _mountStandard(data, attach, options);
  const ref = options.ref ? options.ref : tagForVersion(version);

  const archetype =
    [options.archetype, options.language].filter((part) => part !== undefined && part !== "").join("/") ||
    "unclassified";
  const profiles = detectedProfiles(root, options.archetype, options.language);
  // --- local layout (LOCAL layer) ----------------------------------------------------
  _writeLocalLayout(data, attach);

  // --- hand-owned documents: written when absent, never rewritten --------------------
  const block = _agentsBlock(data, {
    aitna,
    repo: data.akmon_repo,
    ref,
    archetype: options.archetype || "<archetype>",
    language: options.language || "<language>",
    profiles,
    mounted: _mounted(attach),
  });
  _writeAgentsBlock(data, attach, block);
  if (_switching(attach)) {
    attach.nextSteps.push(..._modeSwitchSteps(data, attach));
  }
  _writeGitignore(data, attach);
  _writeCi(data, attach, { noCi: options.noCi });

  const record = _writeAkmonToml(data, attach, { version, archetype });
  _log(`recorded ${aitna}/.akmon.toml (mount=${mode}, akmon_version=${version || "unknown"})`);
  _setupChecks(data, attach, record, options.checks, { ask: !options.yes });

  // --- generated surface: sync, then model routing -----------------------------------
  const code = await _generate(attach);
  if (code !== 0) {
    return code;
  }

  // --- the judgment steps init deliberately did not do -------------------------------
  _addClosingSteps(data, attach, { archetype, profiles, pinStatus, version });
  return _report(data, attach, { pinStatus, record, version });
}

/**
 * Whether node was told to execute `invoked` as this very module (see `akmon/cli.mjs`).
 * @param {string} invoked `process.argv[1]`, the path node was given
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = await main();
}
