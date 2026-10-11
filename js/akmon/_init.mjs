/**
 * `akmon init` — attach the standard to a Node project (C105 pass 3, ADR 0020). The JavaScript
 * twin of `src/akmon/_init.py`, for **Node package mode only**: the Python module is the spec for
 * the local layout, the AGENTS.md block, `.gitignore`, the CI workflow, the closing steps, the
 * report and the exit codes; the mounted modes are served by the Python implementation.
 *
 * What differs from the Python, each a decision of the pass-3 spec:
 * - `--mode` accepts the Python's choices and refuses everything but `package` (exit 2,
 *   `node_refuses_mode`); with no `--mode` the mode is `package` — no probing, no git, no network;
 * - a present record that is not Node package mode (a mounted `mount`, or `mount = "package"`
 *   without `ecosystem = "node"`) is refused the same way (`node_refuses_record`, naming what
 *   `bin/sync.mjs::unsupportedFound` found). There is no mode migration, so `--switch-mode` is
 *   accepted and has nothing to do (package → package);
 * - `--repo` is accepted and, as in the Python's package mode, changes nothing: the AGENTS.md links
 *   name `akmon_repo` of `init.json`; nothing is cloned;
 * - the record also says `ecosystem = "node"`; the pin is `package.json`'s `devDependencies`
 *   (`packagePinStatus`), and the version is the running tree's `package.json` version;
 * - the ref of the AGENTS.md links is `--ref`, else the tag of the installed version
 *   (`tagForVersion`) — never a network lookup;
 * - the package manager (`node_managers` of `init.json`) is detected from `package.json`
 *   `packageManager`, else the lockfile, else npm; it picks the CI workflow, the existing-workflow
 *   commands and the pin command;
 * - `--checks none` or no flag records nothing (JS/TS linter detection is C109); `own` and `akmon`
 *   are refused (`node_checks_pending`);
 * - the generated surface runs **in process**: the JS `sync`, then the routing initializer;
 * - `_confirm` is the Python's: a stdin that is not a terminal confirms, a terminal is asked and
 *   one line is read synchronously (end of input is "not confirmed");
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `akmon init: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0.
 *
 * Data (the C102 convention): `main` reads `src/akmon/init.json` once and passes it down as `data`
 * — the first parameter of every function that needs a text or a table.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { isatty } from "node:tty";
import { parseArgs } from "node:util";

import { blockHeading, readAlwaysLoadedData } from "../common/always_loaded.mjs";
import { fill, read } from "../common/jsondata.mjs";
import { AITNA_ROOT_DEFAULT, resolvePath } from "../common/project_root.mjs";
import { isDir, isFile, pySplitlines, pyStrip, readText, strRepr, truthy, writeText } from "../common/pyvalue.mjs";
import { readAkmonToml } from "../common/record.mjs";
import { isFinal, splitVersion } from "../common/versions.mjs";
import {
  installedAkmonVersion,
  main as syncMain,
  packagePinStatus,
  readSyncData,
  unsupportedFound,
  upsertTomlKey,
} from "../bin/sync.mjs";
import { embeddedTreeRoot } from "./_tree.mjs";

/**
 * One package manager of `init.json`'s `node_managers` table.
 * @typedef {object} NodeManager
 * @property {string} install the CI install command over a committed lockfile
 * @property {string} install_unlocked the CI install command when no lockfile of this manager is committed
 * @property {string} [install_berry] Yarn 2+ (`.yarnrc.yml`, or `packageManager` `yarn@2`+): `--immutable`
 * @property {string} exec the prefix that runs a local bin (`npx `, `pnpm exec `, …)
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
 * @property {string} agents_shared_layer_node
 * @property {string} tasks_skeleton
 * @property {string} memory_index
 * @property {Record<string, string>} charters
 * @property {string} charter
 * @property {string} charter_locate_package
 * @property {string[]} gitignore_lines_node
 * @property {string} ci_workflow
 * @property {string} ci_workflow_steps_node
 * @property {string} record_fresh_node
 * @property {string} record_version_line
 * @property {Record<string, NodeManager>} node_managers
 * @property {Record<string, string[]>} write_ci_commands
 * @property {Record<string, string>} pin_step_node
 * @property {{complete: string, incomplete: string, step: string, exit: string, remedy: Record<string, string>}} report
 * @property {Record<string, string>} report_missing_node
 * @property {Record<string, string>} closing_steps
 * @property {string} node_refuses_mode
 * @property {string} node_refuses_record
 * @property {string} node_checks_pending
 * @property {string} node_mode_reason
 */

/** The mount modes the Python offers; only the last is served here. */
const MODES = ["submodule", "vendored", "subtree", "package"];
const CHECK_CHOICES = ["own", "akmon", "none"];
const _PACKAGE_MODE = "package";

/** A precondition the caller has to fix; reported as one line. */
class InitError extends Error {}

/**
 * One `init` run: the project, its dev layer, the manager, and the steps left to a person.
 * @typedef {object} Attach
 * @property {string} root
 * @property {string} aitna
 * @property {NodeManager} manager
 * @property {string[]} nextSteps
 */

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
  const berry = isFile(posix.join(root, ".yarnrc.yml")) || (declared !== null && /^yarn@(?:[2-9]|[1-9][0-9])/.test(declared));
  let install = manager.install;
  if (!locked) {
    install = manager.install_unlocked;
  } else if (manager.install_berry !== undefined && berry) {
    install = manager.install_berry;
  }
  const setup = manager.ci_setup_unpinned !== undefined && declared === null ? manager.ci_setup_unpinned : manager.ci_setup;
  return { setup, install };
}

// --------------------------------------------------------------------------------------
// local layout + hand-owned documents
// --------------------------------------------------------------------------------------

/**
 * One agent charter (`init.json`), the locate line of package mode.
 * @param {InitData} data
 * @param {string} role
 * @param {string} focus
 * @param {string} aitna
 * @returns {string}
 */
function _charter(data, role, focus, aitna) {
  const locate = fill(data.charter_locate_package, { aitna, role });
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
  const present = new Set(pySplitlines(existing).map(pyStrip).filter((line) => line !== ""));
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
 * The AGENTS.md akmon block (`init.json`); links and fragments computed here. Links name the
 * GitHub repository at the pinned ref (there is no tree in the project to point at).
 * @param {InitData} data
 * @param {{aitna: string, repo: string, ref: string, archetype: string, language: string}} fields
 * @returns {string}
 */
function _agentsBlock(data, { aitna, repo, ref, archetype, language }) {
  /** @param {string} name */
  const link = (name) => `${repo}/blob/${ref}/${name}`;
  const rolesHint = fill(data.agents_roles_hint_package, { roles_link: link("roles/README.md"), aitna });
  const sharedLayer = fill(data.agents_shared_layer_node, { aitna });
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
    guardrails_dir: `${aitna}/.akmon/guardrails`,
    profiles_dir: `${aitna}/.akmon/profiles`,
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
function _writeLocalLayout(data, { root, aitna }) {
  for (const name of ["agents", "skills", "tools", "memory"]) {
    fs.mkdirSync(posix.join(root, aitna, name), { recursive: true });
  }
  _writeIfAbsent(posix.join(root, aitna, "TASKS.md"), fill(data.tasks_skeleton, { aitna }), `${aitna}/TASKS.md`);
  _writeIfAbsent(posix.join(root, aitna, "memory", "README.md"), data.memory_index, `${aitna}/memory/README.md`);
  for (const [role, focus] of Object.entries(data.charters)) {
    _writeIfAbsent(
      posix.join(root, aitna, "agents", role, "README.md"),
      _charter(data, role, focus, aitna),
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
    attach.nextSteps.push("`akmon verify --strict` checks the existing AGENTS.md block against the contract");
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
  const [syncCmd, verifyCmd] = data.write_ci_commands.package.map((command) => manager.exec + command);
  if (noCi) {
    attach.nextSteps.push(`add the contract checks to CI: \`${syncCmd}\` and \`${verifyCmd}\``);
  } else if (_hasWorkflows(workflows)) {
    attach.nextSteps.push(`add the contract checks to your existing workflow(s): \`${syncCmd}\` and \`${verifyCmd}\``);
  } else {
    const { setup, install } = ciInstall(manager, attach.root);
    const steps = fill(data.ci_workflow_steps_node, { setup, install, exec: manager.exec });
    _writeIfAbsent(posix.join(workflows, "akmon.yml"), fill(data.ci_workflow, { steps }), ".github/workflows/akmon.yml");
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
function _writeAkmonToml(data, { root, aitna, manager }, { version, archetype }) {
  const path = posix.join(root, aitna, ".akmon.toml");
  if (!isFile(path)) {
    const recorded = version ? fill(data.record_version_line, { version }) : "";
    fs.mkdirSync(posix.dirname(path), { recursive: true });
    writeText(path, fill(data.record_fresh_node, { recorded, archetype, runner: manager.test }));
    return path;
  }
  let text = readText(path);
  const fields = readAkmonToml(path);
  text = upsertTomlKey(text, "mount", _PACKAGE_MODE);
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
// the generated surface, the closing steps, the report
// --------------------------------------------------------------------------------------

/**
 * Run sync, then the model-routing initializer, both in this process; the first failing exit code, else 0.
 * @param {string} root
 * @returns {Promise<number>}
 */
async function _generate(root) {
  _log("running sync (generated pointers, hook wiring, imported guardrails)");
  let code = syncMain(["--project-root", root]);
  if (code !== 0) {
    process.stderr.write(`akmon init: sync failed (${code}); the attach is incomplete\n`);
    return code;
  }
  _log("running model-routing init (subagent definitions + local routing config)");
  const routing = await import("../tools/model_routing/init.mjs");
  code = await routing.main(["--project-root", root]);
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
 * The judgment steps `init` deliberately did not take, a missing pin first.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {{archetype: string, pinStatus: string, version: string | null}} state
 */
function _addClosingSteps(data, attach, { archetype, pinStatus, version }) {
  const { aitna, nextSteps, manager } = attach;
  const steps = data.closing_steps;
  if (archetype === "unclassified") {
    nextSteps.unshift(fill(steps["classify"], { aitna }));
  }
  nextSteps.push(fill(steps["pin_test_node"], { aitna, test: manager.test }));
  const pinStep = _pinStep(data, attach, pinStatus, version);
  if (pinStep) {
    nextSteps.unshift(pinStep);
  }
  if (aitna !== AITNA_ROOT_DEFAULT) {
    nextSteps.push(fill(steps["export_aitna"], { aitna }));
  }
  nextSteps.push(fill(steps["verify_node"], { exec: manager.exec }));
}

/**
 * Print the steps left; exit 1 while the attach has no `devDependencies` pin it can run from.
 * @param {InitData} data
 * @param {Attach} attach
 * @param {{pinStatus: string, record: string, version: string | null}} state
 * @returns {number}
 */
function _report(data, attach, { pinStatus, record, version }) {
  // The manifest pin *is* the mount: an attach that ends without one looks attached and cannot
  // run a single akmon command, so the exit code says so rather than reporting success.
  const incomplete = pinStatus !== "dev";
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
                  [--language LANGUAGE] [--no-ci] [--checks {own,akmon,none}]
                  [--switch-mode] [--yes]

Attach the akmon standard to a Node project (package mode).

options:
  -h, --help            show this help message and exit
  --mode {submodule,vendored,subtree,package}
                        Mount mode. Only 'package' is served by the
                        JavaScript implementation (default).
  --aitna-root AITNA_ROOT
                        Dev-layer root, project-root-relative (default: _aitna).
  --project-root PROJECT_ROOT
                        Project to attach to. Defaults to the current directory.
  --repo REPO           akmon repository URL (accepted; the AGENTS.md links name the standard one).
  --ref REF             Ref the AGENTS.md links name (default: the tag of the installed version).
  --archetype ARCHETYPE
                        Archetype id per ARCHETYPES.md (default: left unclassified).
  --language LANGUAGE   Primary language per ARCHETYPES.md (default: left unclassified).
  --no-ci               Do not write a CI workflow running sync/verify.
  --checks {own,akmon,none}
                        Not available for Node projects yet (only 'none').
  --switch-mode         Accepted; there is no mode migration to allow.
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
 * @property {string | undefined} checks
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
      checks,
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
 * The refusals of a run that cannot be a Node package attach, raised before anything is touched.
 * @param {InitData} data
 * @param {InitOptions} options
 * @param {string} root
 * @param {string} aitna
 */
function _refuseUnservedRun(data, options, root, aitna) {
  if (options.mode !== undefined && options.mode !== _PACKAGE_MODE) {
    throw new InitError(fill(data.node_refuses_mode, { mode: options.mode }));
  }
  const found = isFile(posix.join(root, aitna, ".akmon.toml"))
    ? unsupportedFound(readSyncData(), root)
    : null;
  if (found !== null) {
    throw new InitError(fill(data.node_refuses_record, { found }));
  }
  if (options.checks === "own" || options.checks === "akmon") {
    throw new InitError(fill(data.node_checks_pending, { choice: options.checks }));
  }
}

/**
 * Attach the standard to the Node project named by `argv` (package mode).
 * @param {string[]} [argv] the arguments after `init` (default: the process's)
 * @returns {Promise<number>} The process exit code: 0 when complete, 1 while the attach has no
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
 * The run proper: plan and refuse, confirm, write the layout and documents, generate, report.
 * @param {InitData} data
 * @param {InitOptions} options
 * @param {string} root
 * @returns {Promise<number>}
 */
async function _run(data, options, root) {
  const aitna = effectiveAitnaRoot(options.aitnaRoot, root);
  process.env.AITNA_ROOT = aitna;
  _refuseUnservedRun(data, options, root, aitna);
  const recordPath = posix.join(root, aitna, ".akmon.toml");
  const recorded = isFile(recordPath);
  const reason = options.mode !== undefined ? "requested" : recorded ? "recorded" : data.node_mode_reason;
  /** @type {Attach} */
  const attach = { root, aitna, manager: data.node_managers[detectManager(data, root)], nextSteps: [] };

  _log(`attaching to ${root}`);
  _log(`mount mode: ${_PACKAGE_MODE} (${reason}) · dev layer: ${aitna}/`);
  if (!options.yes && !_confirm(`akmon init: attach akmon to ${root}?`)) {
    process.stderr.write("akmon init: aborted\n");
    return 1;
  }
  const version = installedAkmonVersion();
  const pinStatus = packagePinStatus(root);
  const ref = options.ref ? options.ref : tagForVersion(version);

  const archetype = [options.archetype, options.language].filter((part) => part !== undefined && part !== "").join("/") || "unclassified";
  // --- local layout (LOCAL layer) ----------------------------------------------------
  _writeLocalLayout(data, attach);

  // --- hand-owned documents: written when absent, never rewritten --------------------
  const block = _agentsBlock(data, {
    aitna,
    repo: data.akmon_repo,
    ref,
    archetype: options.archetype || "<archetype>",
    language: options.language || "<language>",
  });
  _writeAgentsBlock(data, attach, block);
  _writeGitignore(data, attach);
  _writeCi(data, attach, { noCi: options.noCi });

  const record = _writeAkmonToml(data, attach, { version, archetype });
  _log(`recorded ${aitna}/.akmon.toml (mount=${_PACKAGE_MODE}, akmon_version=${version || "unknown"})`);

  // --- generated surface: sync, then model routing -----------------------------------
  const code = await _generate(root);
  if (code !== 0) {
    return code;
  }

  // --- the judgment steps init deliberately did not do -------------------------------
  _addClosingSteps(data, attach, { archetype, pinStatus, version });
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
