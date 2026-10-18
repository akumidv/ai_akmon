#!/usr/bin/env node
/**
 * Run the checks a project declares — `akmon check` (ADR 0014 §4, as amended). The JavaScript
 * twin of `bin/check.py` (C105, ADR 0020 D01): the Python module is the spec, the same findings,
 * the same texts, the same exit code and the same stdout and stderr.
 *
 * The checks are the project's own: its linter, its type checker, or ruff with akmon's rules,
 * named in `[check]` of `<AITNA_ROOT>/.akmon.toml`. akmon runs them and reports the result; it
 * checks no code itself. The engine is `common/check_runner.mjs`.
 *
 *     akmon check              every declared check over the whole project
 *     akmon check --changed    the same checks over the files that differ from HEAD
 *
 * Exit 1 when a check fails or cannot run, or the table is malformed; 0 otherwise.
 *
 * Data (the C102 convention): `main` reads `common/check_runner.json` and `common/findings.json`
 * once, after the arguments are parsed, and passes them down.
 *
 * Twin notes (ADR 0020 D08, `meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs`: a usage error is the one line
 *   `akmon check: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0.
 *   `argparse` prints its usage block with every error and abbreviates long options
 *   (`--chan`); `parseArgs` does neither;
 * - a finding the runner could not build (a command whose report carries a line separator) is a
 *   `ValueError` in both implementations, but the Python raises it at the command that produced
 *   it and the checks after it never run, where here `runChecks` has run them all by then.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import {
  ScopeError,
  changedFiles,
  configTarget,
  correctEntryFix,
  noChecks,
  readChecks,
  repairRecordFix,
  runChecks,
  scopeFix,
} from "../common/check_runner.mjs";
import { Finding, exitCode, printFindings, readFindingsData } from "../common/findings.mjs";
import { read } from "../common/jsondata.mjs";
import { aitnaRoot, resolveProjectRoot } from "../common/project_root.mjs";
import { RecordError, readAkmonTomlStrict } from "../common/record.mjs";
import { pyPath } from "../common/pyvalue.mjs";

/** @typedef {import("../common/check_runner.mjs").CheckRunnerData} CheckRunnerData */

/** The tree this module executes from: `<tree>/js/bin/check.mjs` → `<tree>`. */
const TREE_ROOT = posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", "..");

/** What `-h` / `--help` prints (the Python has `argparse`'s own block; see the header). */
const USAGE = `usage: akmon check [-h] [--project-root PROJECT_ROOT] [--changed]

Run the checks the project declares in [check] of <AITNA_ROOT>/.akmon.toml.

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --changed             Check only the files that differ from HEAD.
`;

/**
 * Parse the arguments after `check`.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, changed: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        changed: { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      changed: values.changed === true,
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
 * Parse arguments, run the project's declared checks, and print findings.
 * @param {string[]} [argv] the arguments after `check` (default: the process's)
 * @returns {number} The process exit code.
 */
export function main(argv = process.argv.slice(2)) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`akmon check: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  const data = /** @type {CheckRunnerData} */ (read(posix.join(TREE_ROOT, "common", "check_runner.json")));
  const findingsData = readFindingsData();
  /** @param {string} severity @param {string} code @param {string} message @param {string} target @param {string} fix */
  const finding = (severity, code, message, target, fix) =>
    new Finding({ severity, code, message, target, fix, data: findingsData });

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  let table;
  try {
    table = readAkmonTomlStrict(pyPath(aitnaRoot(root), ".akmon.toml"))["check"];
  } catch (exc) {
    if (!(exc instanceof RecordError)) {
      throw exc;
    }
    printFindings([finding("error", "check.config", exc.message, configTarget(data), repairRecordFix(data))]);
    return 1;
  }
  const { checks, problems } = readChecks(data, table);
  const findings = problems.map((problem) =>
    finding("error", "check.config", problem, configTarget(data), correctEntryFix(data)),
  );
  if (checks.length === 0 && problems.length === 0) {
    const [message, fix] = noChecks(data);
    findings.push(finding("warn", "check.config", message, configTarget(data), fix));
  }
  let changed;
  try {
    changed = options.changed ? changedFiles(data, root) : null;
  } catch (exc) {
    if (!(exc instanceof ScopeError)) {
      throw exc;
    }
    findings.push(finding("error", "check.scope", exc.message, "", scopeFix(data)));
    printFindings(findings);
    return 1;
  }
  for (const run of runChecks(data, root, checks, changed)) {
    findings.push(finding(run.severity, run.code, run.message, run.target, run.fix));
  }
  printFindings(findings);
  return exitCode(findings);
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
