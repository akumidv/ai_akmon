#!/usr/bin/env node
/**
 * Run an advisory second-opinion review through the registry-selected CLI — the JavaScript twin
 * of `tools/model_routing/second_opinion.py` (C108, ADR 0020 D01). The Python module is the
 * spec: the same files in the same bytes, the same stdout lines, the same `second-opinion:` lines,
 * the same exit codes.
 *
 * The runner is called explicitly at a verify/align gate, writes the full external review to a
 * configured report directory, and prints a short digest. It is not wired as a blocking hook;
 * owner verification remains the decision point.
 *
 * Data (the C102 convention): `main` reads `tools/model_routing/second_opinion.json`, `gate.json`,
 * `agents.json` and `common/runtime.json` once and passes them down.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `second_opinion.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with
 *   every error, names the program `second_opinion.py`, and abbreviates long options — `--dry`),
 *   `-h`/`--help` prints a short usage and exits 0;
 * - the provider CLI runs through `spawnSync`; a CLI that cannot be started (not on PATH) throws
 *   its error, where Python raises `FileNotFoundError` — an uncaught traceback either way.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { join, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import { JSONDecodeError, jsonLoads } from "../../common/pyjson.mjs";
import { aitnaRootName, isRelativeTo, resolvePath, resolveProjectRoot } from "../../common/project_root.mjs";
import { dictGet, isDict, isFile, pyPath, pyStr, pyStrip, readText, universalNewlines } from "../../common/pyvalue.mjs";
import { recordsPackageMode } from "../../common/record.mjs";
import {
  createReport,
  nextReportPath,
  reportPrefix as taskPrefix,
  safeName,
  taskError,
} from "../../common/report_path.mjs";
import {
  UnpinnableModelError,
  loadRegistry,
  localConfigRel,
  resolveSecondOpinion,
  secondOpinionCommand,
  secondOpinionSpec,
  secondOpinionUnavailability,
} from "./routing.mjs";

/** @typedef {import("./routing.mjs").AgentsData} AgentsData */
/** @typedef {import("../../common/runtime.mjs").RuntimeData} RuntimeData */
/** @typedef {import("../../common/pyvalue.mjs").Json} Json */

/**
 * The keys of `tools/model_routing/second_opinion.json`.
 * @typedef {object} SecondOpinionData
 * @property {string} prompt
 * @property {string[]} unavailable_notice
 * @property {string} report_dir_outside
 * @property {{report_line: string, provider_line: string, result_line: string}} summary
 */

/** The keys of `tools/model_routing/gate.json` this runner reads. */
/** @typedef {{truncation_suffix_report: string}} GateData */

/** The tree the running module belongs to (it holds `tools/model_routing/` and `common/runtime.json`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "second_opinion.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--provider PROVIDER]
                         [--orchestrator-vendor ORCHESTRATOR_VENDOR] --gate GATE
                         --gate-pack GATE_PACK [--task TASK] [--dry-run]

Run an advisory second-opinion review through the registry-selected CLI.

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --provider PROVIDER   External review provider. Defaults to configured opposite vendor.
  --orchestrator-vendor ORCHESTRATOR_VENDOR
                        Vendor running the main session.
  --gate GATE           Verify gate name, e.g. design-align or code-verify.
  --gate-pack GATE_PACK
                        Path to a built gate-pack markdown file (see gate_pack.py).
  --task TASK           Task id the review belongs to; the report is <report_dir>/[<task>-]<gate>-<n>.md, n the next ordinal.
  --dry-run             Print the command and target report path without running it.
`;

/**
 * The tree `registry.json` is read from: the mount for mounted modes, the running tree otherwise.
 *
 * The rule of `bin/sync.py::standard_tree_root`: in package mode there is no
 * `<AITNA_ROOT>/akmon` to read, and the recorded `mount` field decides, so a stale mount
 * directory from a prior mode does not shadow the installed tree.
 * @param {string} projectRoot
 * @returns {string}
 */
export function standardTreeRoot(projectRoot) {
  const mounted = pyPath(projectRoot, aitnaRootName(), "akmon");
  if (!recordsPackageMode(projectRoot) && fs.existsSync(mounted) && fs.statSync(mounted).isDirectory()) {
    return mounted;
  }
  return TREE_ROOT;
}

/**
 * A JSON object read from `path`: `{}` when the file is absent, unparsable or not an object.
 * @param {string} path
 * @returns {Record<string, Json>}
 */
export function readJsonObject(path) {
  if (!isFile(path)) {
    return {};
  }
  let value;
  try {
    value = jsonLoads(readText(path));
  } catch (error) {
    if (error instanceof JSONDecodeError) {
      return {};
    }
    throw error;
  }
  return isDict(value) ? /** @type {Record<string, Json>} */ (value) : {};
}

/**
 * The review prompt for `gate` over the gate-pack `material`.
 * @param {SecondOpinionData} texts
 * @param {string} gate
 * @param {string} material
 * @returns {string}
 */
export function reviewPrompt(texts, gate, material) {
  return fill(texts.prompt, { gate, material });
}

/**
 * The skip, stated as a fact plus the one option that is left and what it costs.
 *
 * The gate is skipped rather than downgraded to a same-model reviewer: shared weights reproduce
 * the author's systematic errors and return a confident agreement, which reads exactly like a
 * review and is filed like one. That refusal is the machine's; the weaker check is still worth
 * running sometimes, so it is offered here — to a person, with its boundary attached — instead of
 * being taken automatically and labelled as diversity.
 * @param {SecondOpinionData} texts
 * @param {AgentsData} agents
 * @param {Json} registry
 * @param {Json} config
 * @param {string} orchestratorVendor
 * @param {string} gate
 * @returns {string}
 */
export function unavailableNotice(texts, agents, registry, config, orchestratorVendor, gate) {
  const reason = secondOpinionUnavailability(agents, registry, config, orchestratorVendor);
  const lines = texts.unavailable_notice;
  return [fill(lines[0], { gate }), fill(lines[1], { reason }), lines[2], lines[3], lines[4]].join("\n");
}

/**
 * `[<task>-]<gate>`: the review's name before its `-<n>.md` ordinal (C114).
 * @param {string} gate
 * @param {string | null} [task]
 * @returns {string}
 */
export function reportPrefix(gate, task = null) {
  return taskPrefix(safeName(gate) || "gate", task);
}

/**
 * The error line for a `report_dir` that resolves outside `root`, else `null`.
 *
 * Reports stay inside the project (C9): the check resolves symlinks and `..` first, so an
 * absolute path, a `../outside` and a link inside the project pointing out are all refused, and
 * it runs before the provider is started or any file is written.
 * @param {SecondOpinionData} texts
 * @param {string} root
 * @param {string} reportDir `root` joined with the configured value
 * @param {string} configured the configured `report_dir`, as written
 * @returns {string | null}
 */
export function reportDirError(texts, root, reportDir, configured) {
  if (isRelativeTo(resolvePath(reportDir), resolvePath(root))) {
    return null;
  }
  return fill(texts.report_dir_outside, { report_dir: configured });
}

/**
 * The leading `limit` characters of `text` (stripped), with the truncation suffix when cut.
 * @param {GateData} gate
 * @param {string} text
 * @param {number} [limit]
 * @returns {string}
 */
export function digest(gate, text, limit = 1200) {
  const stripped = pyStrip(text);
  const chars = Array.from(stripped);
  if (chars.length <= limit) {
    return stripped;
  }
  return pyStrip(chars.slice(0, limit).join("")) + gate.truncation_suffix_report;
}

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, provider: string | null, orchestratorVendor: string, gate: string,
 *   gatePack: string, task: string | null, dryRun: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        provider: { type: "string" },
        "orchestrator-vendor": { type: "string" },
        gate: { type: "string" },
        "gate-pack": { type: "string" },
        task: { type: "string" },
        "dry-run": { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    if (values.help === true) {
      return {
        projectRoot: null,
        provider: null,
        orchestratorVendor: "",
        gate: "",
        gatePack: "",
        task: null,
        dryRun: false,
        help: true,
      };
    }
    const missing = [
      values.gate === undefined ? "--gate" : null,
      values["gate-pack"] === undefined ? "--gate-pack" : null,
    ].filter((name) => name !== null);
    if (missing.length > 0) {
      return `the following arguments are required: ${missing.join(", ")}`;
    }
    const taskProblem = taskError(/** @type {string | undefined} */ (values.task));
    if (taskProblem !== null) {
      return taskProblem;
    }
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      provider: /** @type {string | undefined} */ (values.provider) ?? null,
      orchestratorVendor: /** @type {string | undefined} */ (values["orchestrator-vendor"]) ?? "openai",
      gate: /** @type {string} */ (values.gate),
      gatePack: /** @type {string} */ (values["gate-pack"]),
      task: /** @type {string | undefined} */ (values.task) ?? null,
      dryRun: values["dry-run"] === true,
      help: false,
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
 * CLI entry point: run the second-opinion CLI against a gate pack and write its report.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: the provider CLI's, 0 for a skip or a dry run, 2 on a
 *   usage error, an unpinnable model or a `report_dir` outside the project.
 */
export function main(argv = process.argv.slice(2)) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`${PROG}: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  const modelRouting = join(TREE_ROOT, "tools", "model_routing");
  const texts = /** @type {SecondOpinionData} */ (read(join(modelRouting, "second_opinion.json")));
  const gateData = /** @type {GateData} */ (read(join(modelRouting, "gate.json")));
  const agents = /** @type {AgentsData} */ (read(join(modelRouting, "agents.json")));
  const runtime = /** @type {RuntimeData} */ (read(join(TREE_ROOT, "common", "runtime.json")));

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  const registry = loadRegistry(agents, standardTreeRoot(root), root);
  const config = readJsonObject(pyPath(root, localConfigRel(agents)));

  /** @type {string} */ let provider;
  /** @type {string | null} */ let model;
  if (options.provider) {
    provider = options.provider;
    model = null;
  } else {
    const target = resolveSecondOpinion(agents, registry, config, options.orchestratorVendor);
    if (target === null) {
      process.stdout.write(
        `${unavailableNotice(texts, agents, registry, config, options.orchestratorVendor, options.gate)}\n`,
      );
      return 0;
    }
    provider = pyStr(target.provider);
    model = target.model;
  }

  const spec = secondOpinionSpec(agents, registry, provider);
  const configuredDir = pyStr(dictGet(spec, "report_dir"));
  const outside = reportDirError(texts, root, pyPath(root, configuredDir), configuredDir);
  if (outside !== null) {
    process.stderr.write(`${outside}\n`);
    return 2;
  }
  // The resolved form, so the report line is always a path under the (resolved) root.
  const reportDir = resolvePath(pyPath(root, configuredDir));
  const material = readText(options.gatePack);
  /** @type {string[]} */ let command;
  try {
    command = secondOpinionCommand(agents, runtime, spec, reviewPrompt(texts, options.gate, material), model);
  } catch (exc) {
    if (!(exc instanceof UnpinnableModelError)) {
      throw exc;
    }
    process.stderr.write(`second-opinion: ${exc.message}\n`);
    return 2;
  }
  const prefix = reportPrefix(options.gate, options.task);

  const summary = texts.summary;
  if (options.dryRun) {
    process.stdout.write(`${command.join(" ")}\n`);
    process.stdout.write(
      `${fill(summary.report_line, { path: posix.relative(root, nextReportPath(reportDir, prefix)) })}\n`,
    );
    process.stdout.write(`${fill(summary.provider_line, { provider, model: model || "(default)" })}\n`);
    return 0;
  }

  const completed = spawnSync(command[0], command.slice(1), {
    cwd: root,
    encoding: "utf8",
    maxBuffer: Infinity,
    stdio: ["inherit", "pipe", "pipe"],
  });
  if (completed.error) {
    throw completed.error;
  }
  // A signal-killed child is a negative return code in Python.
  const returncode =
    completed.status ?? -(/** @type {Record<string, number>} */ (os.constants.signals)[completed.signal ?? ""] ?? 0);
  // Both twins read the pipes as UTF-8 with an undecodable byte as U+FFFD (`encoding: "utf8"`,
  // C120), then with universal newlines: `\r\n` and a lone `\r` arrive as `\n`, so the report
  // holds the same bytes on both twins (C115).
  const stdout = universalNewlines(completed.stdout);
  const stderr = universalNewlines(completed.stderr);
  let output = pyStrip(stdout);
  if (pyStrip(stderr) !== "") {
    output = pyStrip(`${output}\n\n[stderr]\n${pyStrip(stderr)}`);
  }
  const relReport = posix.relative(root, createReport(reportDir, prefix, `${output}\n`));
  process.stdout.write(
    `${fill(summary.result_line, { provider, model: model || "(default)", gate: options.gate, exit: String(returncode) })}\n`,
  );
  process.stdout.write(`${fill(summary.report_line, { path: relReport })}\n`);
  if (output) {
    process.stdout.write("\n");
    process.stdout.write(`${digest(gateData, output)}\n`);
  }
  return returncode;
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
