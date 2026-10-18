/**
 * `akmon update` — move a Node project to another akmon release, then realign it (C107, ADR 0020
 * D07, ADR-0018/D03). The JavaScript twin of `src/akmon/_update.py` for a record that names
 * `ecosystem = "node"`, in every mount mode (the mounted ones since C129, the amendment of ADR
 * 0020 D02): the Python module is the spec for the plan (direction, rollback, the six notes), the
 * banner, the per-mode moves, the checks after `init`, the closing steps and the exit codes.
 *
 * What differs from the Python, each a decision of C107 or C129:
 * - a record that is not a Node attach is refused (exit 2, `node_refuses_record`, naming what
 *   `bin/sync.mjs::unsupportedFound` found); no record at all keeps the shared `missing_record`;
 * - in package mode the target without `--ref` is the newest final release the **npm registry**
 *   lists (`npm view akmon versions --json`, run in the project so its `.npmrc` applies), because
 *   the installed package comes from there, not from a git tag, and `--repo` changes nothing. A
 *   mounted mode reads the tags of `--repo` with `git ls-remote`, as the Python does. A release is
 *   ordered with the PEP 440 reading of its SemVer spelling (`-dev.N`);
 * - the mounted modes: `submodule` fetches the release tags into the mount, then this CLI's `init
 *   --ref` moves the pin; `subtree` prints the `git subtree pull` that commits; `vendored` runs
 *   `init` from this CLI when it is the target release and otherwise prints the `npx` command that
 *   fetches that release's CLI — running it would be a download the owner did not ask for (the
 *   Python runs `uvx` instead). The checks then run on the mount's own CLI, the tree that governs;
 * - the pin moves with the detected manager's exact dev-install command (`add_dev_exact` of
 *   `init.json`'s `node_managers`) at the bare version (`v0.5.0` pins `akmon@0.5.0`). A
 *   `packageManager` naming any other manager, or a manager binary not on PATH, gets the command
 *   printed (exit 2), never a guessed substitute;
 * - in package mode `init` and the checks run from the project's own installed CLI,
 *   `node_modules/akmon/js/akmon/cli.mjs`, under the running node — the release the project now
 *   pins, whichever CLI started the update;
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08, DV12).
 *
 * Data (the C102 convention): `main` reads `src/akmon/update.json` and `src/akmon/init.json` once
 * and passes them down.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { delimiter, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { fill, read } from "../common/jsondata.mjs";
import { resolvePath } from "../common/project_root.mjs";
import { isFile } from "../common/pyvalue.mjs";
import { readAkmonToml, recordedMount } from "../common/record.mjs";
import { compareVersions, isFinal, orderKey, splitVersion } from "../common/versions.mjs";
import { shlexJoin, shlexSplit } from "../common/shlex.mjs";
import { installedAkmonVersion, packagePinStatus, readSyncData, unsupportedFound } from "../bin/sync.mjs";
import {
  InitError,
  declaredManager,
  defaultRef,
  detectManager,
  effectiveAitnaRoot,
  mountedCli,
  npxSpec,
  readInitData,
  shellWord,
} from "./_init.mjs";
import { CLI_PATH } from "./_mount.mjs";
import { embeddedTreeRoot } from "./_tree.mjs";

/**
 * The keys of `src/akmon/update.json` the JavaScript update reads.
 * @typedef {object} UpdateData
 * @property {Record<string, string>} plan_notes
 * @property {string} banner
 * @property {string} missing_record
 * @property {string} init_failed
 * @property {[string, string][]} checks
 * @property {string} checks_running
 * @property {string} checks_failed
 * @property {string} closing_left_to_you
 * @property {string} closing_step
 * @property {string} closing_changelog
 * @property {string} closing_review
 * @property {string} closing_bump
 * @property {string} closing_codex
 * @property {string} closing_staged_node
 * @property {string} subtree_refusal
 * @property {string} subtree_pull_command
 * @property {string} subtree_realign_command
 * @property {string} vendored_not_fetchable
 * @property {string} node_vendored_command
 * @property {string} node_refuses_record
 * @property {string} node_pin_not_dev
 * @property {string} node_registry_unreachable
 * @property {string} node_registry_no_release
 * @property {string} node_manager_unknown
 * @property {string} node_manager_missing
 * @property {string} node_move_failed
 * @property {string} node_launcher_missing
 */

/**
 * What the update runs outside this process — injected so a test can stand in for the manager.
 * @typedef {object} UpdateDeps
 * @property {(argv: string[], cwd: string) => number} run a command with its output on this
 *   terminal; its exit code (-1 when it could not be started)
 * @property {(argv: string[], cwd: string) => string | null} capture a command's stdout, `null`
 *   when it could not be started, timed out or exited non-zero
 * @property {(name: string) => boolean} onPath whether a command of that name is on PATH
 */

/** The mount modes a record may name; any other value is no attach at all (the Python's `_UPDATERS`). */
const MODES = ["submodule", "package", "vendored", "subtree"];
const _PACKAGE_MODE = "package";
/** `npm view` waits on the network; the Python's `git ls-remote` gets the same bound. */
const _REGISTRY_TIMEOUT_MS = 20_000;

/** A refusal, or a step that failed before `init` ran; printed, exit 2. */
class UpdateError extends Error {}

/**
 * The shared update text and tables (`update.json`, beside the Python module), read on the call.
 * @returns {UpdateData}
 */
export function readUpdateData() {
  return /** @type {UpdateData} */ (read(posix.join(embeddedTreeRoot(), "src", "akmon", "update.json")));
}

/**
 * @param {string} message
 */
function _log(message) {
  process.stdout.write(`akmon update: ${message}\n`);
}

// --------------------------------------------------------------------------------------
// the plan
// --------------------------------------------------------------------------------------

/**
 * The version as the ordering rule reads it: the SemVer carrier spelling of a development version
 * (`0.4.0-dev.0`, `versions.mjs::semverSpelling`) back in its PEP 440 form (`0.4.0.dev0`), so it
 * sorts where the Python side sorts it rather than with the release candidates.
 * @param {string} version
 * @returns {string}
 */
function _orderable(version) {
  return version.replace(/^(v?[0-9]+\.[0-9]+\.[0-9]+)-dev\.([0-9]+)$/, "$1.dev$2");
}

/**
 * Where the pin goes: the target, the version the record holds, whether the pin moves, and why.
 * @typedef {{target: string, current: string | null, move: boolean, note: string}} Plan
 */

/**
 * Compare the recorded version with the target; the pin moves back only when `--ref` says so.
 * @param {UpdateData} data
 * @param {string | null} current
 * @param {string} target
 * @param {{explicit: boolean}} options
 * @returns {Plan}
 */
export function plan(data, current, target, { explicit }) {
  const notes = data.plan_notes;
  const then = orderKey(_orderable(target));
  const now = current ? orderKey(_orderable(current)) : null;
  let move;
  let note;
  if (then === null) {
    [move, note] = [true, fill(notes.not_a_release, { target })];
  } else if (now === null) {
    [move, note] = [true, fill(notes.record_no_version, { target, current: current || "none" })];
  } else {
    const recorded = /** @type {string} */ (current);
    const order = compareVersions(_orderable(target), _orderable(recorded));
    if (order > 0) {
      [move, note] = [true, fill(notes.forward, { current: recorded, target })];
    } else if (order === 0) {
      [move, note] = [false, fill(notes.already, { target })];
    } else if (explicit) {
      [move, note] = [true, fill(notes.rollback, { current: recorded, target })];
    } else {
      [move, note] = [false, fill(notes.past_newest, { current: recorded, target })];
    }
  }
  return { target, current, move, note };
}

/**
 * The newest final release among `versions` (registry spellings), or `null` when there is none.
 * A pre-release is never the newest.
 * @param {unknown[]} versions
 * @returns {string | null}
 */
export function newestRelease(versions) {
  /** @type {string | null} */
  let newest = null;
  for (const version of versions) {
    if (typeof version === "string" && isFinal(version) && (newest === null || compareVersions(version, newest) > 0)) {
      newest = version;
    }
  }
  return newest;
}

/**
 * The newest final release of akmon the npm registry lists, asked in the project so its `.npmrc`
 * (a mirror, a scope registry) applies.
 * @param {UpdateData} data
 * @param {UpdateDeps} deps
 * @param {string} root
 * @returns {string}
 */
function _registryTarget(data, deps, root) {
  const listing = deps.capture(["npm", "view", "akmon", "versions", "--json"], root);
  /** @type {unknown} */
  let parsed;
  try {
    parsed = listing === null ? null : JSON.parse(listing);
  } catch (error) {
    if (!(error instanceof SyntaxError)) {
      throw error;
    }
    parsed = null;
  }
  // npm prints a lone version as a string, several as an array.
  const versions = typeof parsed === "string" ? [parsed] : Array.isArray(parsed) ? parsed : null;
  if (versions === null) {
    throw new UpdateError(data.node_registry_unreachable);
  }
  const newest = newestRelease(versions);
  if (newest === null) {
    throw new UpdateError(data.node_registry_no_release);
  }
  return newest;
}

/**
 * The package spec a target pins: a release tag's leading `v` is a spelling, not part of the version.
 * @param {string} target
 * @returns {string}
 */
export function pinSpec(target) {
  return `akmon@${/^v[0-9]/.test(target) ? target.slice(1) : target}`;
}

/**
 * The command that moves the pin, as argv: the manager's exact dev install of `spec`.
 * @param {import("./_init.mjs").NodeManager} manager
 * @param {string} spec
 * @returns {string[]}
 */
export function moveCommand(manager, spec) {
  return [...shlexSplit(manager.add_dev_exact), spec];
}

// --------------------------------------------------------------------------------------
// the move, init, the checks
// --------------------------------------------------------------------------------------

/**
 * Move the pin with the project's manager, refusing — with the command printed — where akmon does
 * not drive it or cannot run it.
 * @param {{update: UpdateData, init: import("./_init.mjs").InitData}} data
 * @param {UpdateDeps} deps
 * @param {string} root
 * @param {Plan} thePlan
 */
function _movePin(data, deps, root, thePlan) {
  const status = packagePinStatus(root);
  if (status !== "dev") {
    throw new UpdateError(fill(data.update.node_pin_not_dev, { status }));
  }
  const spec = pinSpec(thePlan.target);
  const managers = data.init.node_managers;
  const declared = declaredManager(root);
  if (declared !== null && !Object.hasOwn(managers, declared.split("@", 1)[0])) {
    throw new UpdateError(
      fill(data.update.node_manager_unknown, { declared, spec, command: shlexJoin(moveCommand(managers.npm, spec)) }),
    );
  }
  const name = detectManager(data.init, root);
  const command = moveCommand(managers[name], spec);
  if (!deps.onPath(command[0])) {
    throw new UpdateError(
      fill(data.update.node_manager_missing, { manager: name, binary: command[0], command: shlexJoin(command) }),
    );
  }
  _log(`moving the pin: ${shlexJoin(command)}`);
  const code = deps.run(command, root);
  if (code !== 0) {
    throw new UpdateError(fill(data.update.node_move_failed, { command: shlexJoin(command), code: String(code) }));
  }
}

// --------------------------------------------------------------------------------------
// per mounted mode: move the pin, run init — the init exit code (the Python's `_update_*`)
// --------------------------------------------------------------------------------------

/**
 * The argv that runs this CLI's own `init` on `root` (the Python calls its `_init.main` in process).
 * @param {string} root
 * @param {string[]} [extra]
 * @returns {string[]}
 */
function _ownInit(root, extra = []) {
  return [
    process.execPath,
    posix.join(embeddedTreeRoot(), CLI_PATH),
    "init",
    "--project-root",
    root,
    "--yes",
    ...extra,
  ];
}

/**
 * Mode `submodule`: fetch the release tags from `repo`, where the target was read, into the mount;
 * then `init --ref` moves the pin (left unstaged, D5).
 * @param {UpdateDeps} deps
 * @param {{root: string, aitna: string, thePlan: Plan, repo: string}} run
 * @returns {number}
 */
function _updateSubmodule(deps, { root, aitna, thePlan, repo }) {
  const extra = [];
  if (thePlan.move) {
    _log(`fetching release tags into ${aitna}/akmon`);
    if (deps.run(["git", "fetch", "--quiet", "--tags", repo], posix.join(root, aitna, "akmon")) !== 0) {
      throw new UpdateError(
        `\`git fetch --tags\` failed in ${aitna}/akmon — it needs git and network access to ${repo}`,
      );
    }
    extra.push("--ref", thePlan.target);
  }
  return deps.run(_ownInit(root, extra), root);
}

/**
 * Whether `ref` names a release and it is the release this CLI is.
 * @param {string | null} ref
 * @returns {boolean}
 */
function _isRunningRelease(ref) {
  const running = installedAkmonVersion();
  if (!ref || !isFinal(ref) || running === null) {
    return false;
  }
  return splitVersion(ref).base === splitVersion(running).base;
}

/**
 * Mode `vendored`: the mount is a copy of the tree of the CLI that runs `init`, so `init` runs from
 * exactly the pinned release — this CLI when it is that release; otherwise the `npx` command that
 * fetches it is printed, never run.
 * @param {{update: UpdateData, init: import("./_init.mjs").InitData}} data
 * @param {UpdateDeps} deps
 * @param {{root: string, aitna: string, thePlan: Plan, repo: string}} run
 * @returns {number}
 */
function _updateVendored(data, deps, { root, thePlan, repo }) {
  const ref = thePlan.move ? thePlan.target : thePlan.current;
  if (_isRunningRelease(ref)) {
    return deps.run(_ownInit(root), root);
  }
  if (!thePlan.move && !(ref && isFinal(ref))) {
    throw new UpdateError(fill(data.update.vendored_not_fetchable, { recorded: ref || "version" }));
  }
  const tag = thePlan.move ? /** @type {string} */ (ref) : `v${splitVersion(/** @type {string} */ (ref)).base}`;
  const command = ["npx", npxSpec(repo, tag), "init", "--mode", "vendored", "--project-root", root, "--yes"];
  throw new UpdateError(fill(data.update.node_vendored_command, { tag, command: command.map(shellWord).join(" ") }));
}

/**
 * Mode `subtree`: realign in place; a move is `git subtree pull`, which commits, so it is printed.
 * @param {{update: UpdateData, init: import("./_init.mjs").InitData}} data
 * @param {UpdateDeps} deps
 * @param {{root: string, aitna: string, thePlan: Plan, repo: string}} run
 * @returns {number}
 */
function _updateSubtree(data, deps, { root, aitna, thePlan, repo }) {
  if (!thePlan.move) {
    return deps.run(_ownInit(root, ["--ref", String(thePlan.current)]), root);
  }
  const commands = [
    fill(data.update.subtree_pull_command, { aitna, repo, target: thePlan.target }),
    fill(data.update.subtree_realign_command, { target: thePlan.target, cli: mountedCli(data.init, aitna) }),
  ];
  throw new UpdateError(`${data.update.subtree_refusal}\n${commands.join("\n")}`);
}

/**
 * `sync --check`, then `verify --strict`, run by the CLI the project now pins; the first failure.
 * @param {UpdateData} data
 * @param {UpdateDeps} deps
 * @param {string} root
 * @param {string} launcher
 * @returns {number}
 */
function _checks(data, deps, root, launcher) {
  for (const [script, flag] of data.checks) {
    _log(fill(data.checks_running, { script, flag }));
    const code = deps.run([process.execPath, launcher, script, flag, "--project-root", root], root);
    if (code !== 0) {
      process.stderr.write(`${fill(data.checks_failed, { script, flag, code: String(code) })}\n`);
      return code;
    }
  }
  return 0;
}

/**
 * What the update leaves to the owner (`update.json`, `closing_*`), one numbered line each.
 * @param {UpdateData} data
 * @param {{root: string, aitna: string, mode: string}} project
 * @param {Plan} thePlan
 * @param {string | null} lastRealign
 */
function _closing(data, { root, aitna, mode }, thePlan, lastRealign) {
  const steps = [];
  if (thePlan.move) {
    steps.push(
      fill(data.closing_changelog, {
        last: lastRealign || thePlan.current || "the previous version",
        target: thePlan.target,
      }),
    );
  }
  const staged = mode === _PACKAGE_MODE ? data.closing_staged_node : `\`${aitna}/akmon\``;
  steps.push(fill(data.closing_review, { staged }));
  if (thePlan.move) {
    steps.push(fill(data.closing_bump, { aitna }));
  }
  if (isFile(posix.join(root, ".codex", "hooks.json"))) {
    steps.push(data.closing_codex);
  }
  process.stdout.write("\n");
  _log(data.closing_left_to_you);
  steps.forEach((step, index) => {
    process.stdout.write(`${fill(data.closing_step, { index: String(index + 1), step })}\n`);
  });
}

// --------------------------------------------------------------------------------------
// the command
// --------------------------------------------------------------------------------------

/** What `-h` / `--help` prints (the Python has `argparse`'s own block). */
const USAGE = `usage: akmon update [-h] [--ref REF] [--project-root PROJECT_ROOT]
                    [--aitna-root AITNA_ROOT] [--repo REPO]

Move this Node project to another akmon release, then realign it: init, sync
--check, verify --strict. Never commits.

options:
  -h, --help            show this help message and exit
  --ref REF             Release to move to (default: the newest release — on the
                        npm registry in package mode, the newest release tag of
                        --repo in a mounted one; an older one rolls back).
  --project-root PROJECT_ROOT
                        Project to update. Defaults to the current directory.
  --aitna-root AITNA_ROOT
                        Dev-layer root, project-root-relative (default:
                        AITNA_ROOT or _aitna).
  --repo REPO           akmon repository URL of a mounted mode (package mode:
                        accepted; the release comes from the npm registry).
`;

/**
 * @typedef {{ref: string | undefined, projectRoot: string | undefined, aitnaRoot: string | undefined, repo: string | undefined, help: boolean}} UpdateOptions
 */

/**
 * Parse the arguments after `update`.
 * @param {string[]} argv
 * @returns {UpdateOptions | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        ref: { type: "string" },
        "project-root": { type: "string" },
        "aitna-root": { type: "string" },
        repo: { type: "string" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    return {
      ref: /** @type {string | undefined} */ (values.ref),
      projectRoot: /** @type {string | undefined} */ (values["project-root"]),
      aitnaRoot: /** @type {string | undefined} */ (values["aitna-root"]),
      repo: /** @type {string | undefined} */ (values.repo),
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
 * Whether `name` is an executable file in a PATH directory (Windows: with a PATHEXT suffix).
 * @param {string} name
 * @returns {boolean}
 */
function _onPath(name) {
  const suffixes = process.platform === "win32" ? ["", ...(process.env.PATHEXT ?? ".EXE;.CMD").split(";")] : [""];
  for (const directory of (process.env.PATH ?? "").split(delimiter)) {
    for (const suffix of suffixes) {
      try {
        fs.accessSync(posix.join(directory || ".", `${name}${suffix}`), fs.constants.X_OK);
        return true;
      } catch {
        // not here
      }
    }
  }
  return false;
}

/** @type {UpdateDeps} */
const DEFAULT_DEPS = {
  run(argv, cwd) {
    const result = spawnSync(argv[0], argv.slice(1), { cwd, stdio: "inherit" });
    return result.error !== undefined ? -1 : (result.status ?? 1);
  },
  capture(argv, cwd) {
    const result = spawnSync(argv[0], argv.slice(1), {
      cwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: _REGISTRY_TIMEOUT_MS,
    });
    return result.error !== undefined || result.status !== 0 ? null : result.stdout;
  },
  onPath: _onPath,
};

/**
 * Update the project to `--ref` or the newest release; the first failing exit code, else 0.
 * @param {string[]} [argv] the arguments after `update` (default: the process's)
 * @param {UpdateDeps} [deps]
 * @returns {number}
 */
export function main(argv = process.argv.slice(2), deps = DEFAULT_DEPS) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`akmon update: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }
  const root = resolvePath(options.projectRoot ?? process.cwd());
  const previousEnv = process.env.AITNA_ROOT;
  try {
    return _run(options, deps, root);
  } catch (error) {
    if (error instanceof UpdateError || error instanceof InitError) {
      process.stderr.write(`akmon update: ${error.message}\n`);
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
 * The run proper: refuse, plan, move, init, the checks, the closing steps.
 * @param {UpdateOptions} options
 * @param {UpdateDeps} deps
 * @param {string} root
 * @returns {number}
 */
function _run(options, deps, root) {
  const data = { update: readUpdateData(), init: readInitData() };
  const aitna = effectiveAitnaRoot(options.aitnaRoot, root);
  process.env.AITNA_ROOT = aitna;
  const mode = recordedMount(root);
  if (mode === null || !MODES.includes(mode)) {
    throw new UpdateError(fill(data.update.missing_record, { root, aitna }));
  }
  const found = unsupportedFound(readSyncData(), root);
  if (found !== null) {
    throw new UpdateError(fill(data.update.node_refuses_record, { found }));
  }
  const record = readAkmonToml(posix.join(root, aitna, ".akmon.toml"));
  const text = (/** @type {unknown} */ value) => (typeof value === "string" && value !== "" ? value : null);
  const current = text(record["akmon_version"]);
  const lastRealign = text(record["last_realign"]);
  const repo = options.repo ?? data.init.akmon_repo;
  const target =
    options.ref ||
    (mode === _PACKAGE_MODE
      ? _registryTarget(data.update, deps, root)
      : defaultRef(data.init, repo, root, deps.capture));
  const thePlan = plan(data.update, current, target, { explicit: options.ref !== undefined });
  _log(fill(data.update.banner, { root, mode, note: thePlan.note }));
  const run = { root, aitna, mode, thePlan, repo, lastRealign };
  return mode === _PACKAGE_MODE ? _finishPackage(data, deps, run) : _finishMounted(data, deps, run);
}

/**
 * Package mode after the plan: move the pin with the project's manager, then `init` and the checks
 * on the project's own installed CLI, and the closing steps.
 * @param {{update: UpdateData, init: import("./_init.mjs").InitData}} data
 * @param {UpdateDeps} deps
 * @param {{root: string, aitna: string, mode: string, thePlan: Plan, repo: string, lastRealign: string | null}} run
 * @returns {number}
 */
function _finishPackage(data, deps, { root, aitna, mode, thePlan, lastRealign }) {
  if (thePlan.move) {
    _movePin(data, deps, root, thePlan);
  }
  const launcher = posix.join(root, "node_modules", "akmon", "js", "akmon", "cli.mjs");
  if (!isFile(launcher)) {
    const manager = data.init.node_managers[detectManager(data.init, root)];
    throw new UpdateError(
      fill(data.update.node_launcher_missing, {
        launcher: posix.relative(root, launcher),
        install: manager.install_unlocked,
      }),
    );
  }
  let code = deps.run([process.execPath, launcher, "init", "--project-root", root, "--yes"], root);
  if (code !== 0) {
    process.stderr.write(`${fill(data.update.init_failed, { code: String(code) })}\n`);
    return code;
  }
  code = _checks(data.update, deps, root, launcher);
  _closing(data.update, { root, aitna, mode }, thePlan, lastRealign);
  return code;
}

/**
 * A mounted mode after the plan: move the pin the mode's way, then the checks on the mount's own
 * CLI — the tree that governs once `init` has realigned it — and the closing steps.
 * @param {{update: UpdateData, init: import("./_init.mjs").InitData}} data
 * @param {UpdateDeps} deps
 * @param {{root: string, aitna: string, mode: string, thePlan: Plan, repo: string, lastRealign: string | null}} run
 * @returns {number}
 */
function _finishMounted(data, deps, run) {
  const { root, aitna, mode, thePlan, lastRealign } = run;
  let code;
  if (mode === "submodule") {
    code = _updateSubmodule(deps, run);
  } else if (mode === "vendored") {
    code = _updateVendored(data, deps, run);
  } else {
    code = _updateSubtree(data, deps, run);
  }
  if (code !== 0) {
    process.stderr.write(`${fill(data.update.init_failed, { code: String(code) })}\n`);
    return code;
  }
  code = _checks(data.update, deps, root, posix.join(root, aitna, "akmon", CLI_PATH));
  _closing(data.update, { root, aitna, mode }, thePlan, lastRealign);
  return code;
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
  process.exitCode = main();
}
