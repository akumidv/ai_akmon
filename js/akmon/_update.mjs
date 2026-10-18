/**
 * `akmon update` — move a Node project to another akmon release, then realign it (C107, ADR 0020
 * D07, ADR-0018/D03). The JavaScript twin of `src/akmon/_update.py` for **Node package mode only**:
 * the Python module is the spec for the plan (direction, rollback, the six notes), the banner, the
 * checks after `init`, the closing steps and the exit codes. The mounted modes and Python package
 * mode are served by the Python implementation.
 *
 * What differs from the Python, each a decision of C107:
 * - a record that is not a Node package attach is refused (exit 2, `node_refuses_record`, naming
 *   what `bin/sync.mjs::unsupportedFound` found); no record at all keeps the shared `missing_record`;
 * - the target without `--ref` is the newest final release the **npm registry** lists
 *   (`npm view akmon versions --json`, run in the project so its `.npmrc` applies), because the
 *   installed package comes from there, not from a git tag; `--repo` is accepted and changes
 *   nothing. A release is ordered with the PEP 440 reading of its SemVer spelling (`-dev.N`);
 * - the pin moves with the detected manager's exact dev-install command (`add_dev_exact` of
 *   `init.json`'s `node_managers`) at the bare version (`v0.5.0` pins `akmon@0.5.0`). A
 *   `packageManager` naming any other manager, or a manager binary not on PATH, gets the command
 *   printed (exit 2), never a guessed substitute;
 * - `init` and the checks run from the project's own installed CLI,
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
import { compareVersions, isFinal, orderKey } from "../common/versions.mjs";
import { shlexJoin, shlexSplit } from "../common/shlex.mjs";
import { packagePinStatus, readSyncData, unsupportedFound } from "../bin/sync.mjs";
import { InitError, declaredManager, detectManager, effectiveAitnaRoot, readInitData } from "./_init.mjs";
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
 * @param {string} root
 * @param {string} aitna
 * @param {Plan} thePlan
 * @param {string | null} lastRealign
 */
function _closing(data, root, aitna, thePlan, lastRealign) {
  const steps = [];
  if (thePlan.move) {
    steps.push(
      fill(data.closing_changelog, {
        last: lastRealign || thePlan.current || "the previous version",
        target: thePlan.target,
      }),
    );
  }
  steps.push(fill(data.closing_review, { staged: data.closing_staged_node }));
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
  --ref REF             Release to move to (default: the newest release on the
                        npm registry; an older one rolls back).
  --project-root PROJECT_ROOT
                        Project to update. Defaults to the current directory.
  --aitna-root AITNA_ROOT
                        Dev-layer root, project-root-relative (default:
                        AITNA_ROOT or _aitna).
  --repo REPO           Accepted; the release comes from the npm registry.
`;

/**
 * @typedef {{ref: string | undefined, projectRoot: string | undefined, aitnaRoot: string | undefined, help: boolean}} UpdateOptions
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
  const target = options.ref || _registryTarget(data.update, deps, root);
  const thePlan = plan(data.update, current, target, { explicit: options.ref !== undefined });
  _log(fill(data.update.banner, { root, mode: _PACKAGE_MODE, note: thePlan.note }));

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
  _closing(data.update, root, aitna, thePlan, lastRealign);
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
