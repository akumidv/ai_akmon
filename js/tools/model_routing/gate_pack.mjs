#!/usr/bin/env node
/**
 * Build the gate-pack markdown consumed by both gate executors — the JavaScript twin of
 * `tools/model_routing/gate_pack.py` (C108, ADR 0020 D01). The Python module is the spec: the
 * same pack bytes, the same stdout lines, the same `error:` lines, the same exit codes.
 *
 * One structured input package per gate (design §9.4), replacing free-form `--prompt-file` text:
 * the auditor subagent (the orchestrator pastes the pack text into an `Agent` call) and the
 * second-opinion CLI both read the same document. Provider-neutral markdown, deterministic given
 * its inputs.
 *
 * Two pack kinds:
 *
 * - `full` — post-fan-out audit pack: artifacts + yardstick + coverage map (+ optional decisions
 *   register / dependency-graph excerpt), ending in the k_auditor output contract (§9.3 item 4);
 * - `plan-check` — the pre-fan-out anchor (§9.3 item 5): yardstick + zone plan only, no
 *   artifacts, checking the plan against the goal rather than against its own coverage map.
 *
 * Data (the C102 convention): the texts live in `tools/model_routing/gate.json`, shared with the
 * Python twin and read on the call that needs them.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `gate_pack.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with
 *   every error, names the program `gate_pack.py`, and abbreviates long options), `-h`/`--help`
 *   prints a short usage and exits 0;
 * - an input file that cannot be read stops the run with the thrown error, not a Python traceback.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import { aitnaRoot, resolveProjectRoot } from "../../common/project_root.mjs";
import { pyPath, pyStrip, readText, writeText } from "../../common/pyvalue.mjs";
import { createReport, reportPrefix as taskPrefix, safeName, taskError } from "../../common/report_path.mjs";
import { codePointSort } from "../../common/sort.mjs";

/**
 * @typedef {object} GatePackData the `gate_pack` section of `gate.json`
 * @property {Record<string, string>} role_question
 * @property {string} plan_check_question
 * @property {string} title
 * @property {string} role_line
 * @property {string} kind_full
 * @property {string} kind_plan_check
 * @property {string} question_line
 * @property {string} yardstick_full_heading
 * @property {string} yardstick_plan_heading
 * @property {string} artifacts_heading
 * @property {string} artifact_heading
 * @property {string} artifacts_empty_sentinel
 * @property {string} decisions_heading
 * @property {string} coverage_heading
 * @property {string} coverage_empty_sentinel
 * @property {string} dep_graph_heading
 * @property {string} zone_plan_heading
 * @property {string} what_to_return_heading
 * @property {string[]} full_contract_bullets
 * @property {string[]} plan_contract_bullets
 */
/**
 * @typedef {object} GateData the parsed `gate.json` (the part this module reads)
 * @property {GatePackData} gate_pack
 * @property {string} truncation_suffix_pack
 */

/** The tree the running module belongs to (it holds `tools/model_routing/gate.json`). */
const TREE_ROOT = embeddedTreeRoot();

const PROG = "gate_pack.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] --gate GATE --role {architect,review}
               [--kind {full,plan-check}] --yardstick YARDSTICK
               [--artifact ARTIFACT] [--decisions DECISIONS]
               [--coverage-map COVERAGE_MAP] [--zone-plan ZONE_PLAN]
               [--dep-graph DEP_GRAPH] [--task TASK] [--out OUT] [--stdout]

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --gate GATE           Verify gate name, e.g. design-align or code-verify.
  --role {architect,review}
                        Gate role — determines the pack's question (tier only determines the model).
  --kind {full,plan-check}
                        Pack kind.
  --yardstick YARDSTICK
                        File with the acceptance condition / goal.
  --artifact ARTIFACT   Artifact file (repeatable; full only) — named by its filename.
  --decisions DECISIONS
                        Decisions register file (architect full).
  --coverage-map COVERAGE_MAP
                        Coverage map file (full).
  --zone-plan ZONE_PLAN
                        Zone plan file (required for --kind plan-check).
  --dep-graph DEP_GRAPH
                        Dependency-graph excerpt file (opt-in, §9.7 #3).
  --task TASK           Task id the pack belongs to; prefixes the default name: <task>-<gate>-<kind>-<n>.md.
  --out OUT             Output path. Defaults to <AITNA_ROOT>/artifacts/gates/[<task>-]<gate>-<kind>-<n>.md, n the next ordinal.
  --stdout              Also print the full pack, so the orchestrator can paste it into the k_auditor Agent call.
`;

/**
 * The shared gate-pack texts and pack skeleton (`gate.json`), read on the call that needs it.
 * @returns {GateData}
 */
function _gateData() {
  return /** @type {GateData} */ (read(posix.join(TREE_ROOT, "tools", "model_routing", "gate.json")));
}

/**
 * Role -> the question the pack asks its executor.
 *
 * Design §9.4: "roles and tiers stay orthogonal" — the role determines the pack's contract
 * and question, the tier only the model.
 * @returns {Record<string, string>}
 */
export function roleQuestion() {
  return { ..._gateData().gate_pack.role_question };
}

/**
 * The question the plan-check pack asks its executor (design §9.3 item 5).
 * @returns {string}
 */
export function planCheckQuestion() {
  return _gateData().gate_pack.plan_check_question;
}

/**
 * @param {string} role
 * @returns {void}
 */
function _requireKnownRole(role) {
  const roles = roleQuestion();
  if (!Object.hasOwn(roles, role)) {
    const known = codePointSort(Object.keys(roles)).join(", ");
    throw new RangeError(`unknown role '${role}'; known roles: ${known}`);
  }
}

/**
 * The full pack's optional sections, each rendered only when given (`null` omits it).
 *
 * `decisions` (architect's decisions register), `coverageMap` (assembled from the delegation
 * log by code — this builder only embeds it; C17), and `depGraph` (opt-in per gate, §9.7 #3)
 * travel together as the pack's non-mandatory extras.
 * @typedef {object} OptionalSections
 * @property {string | null} [decisions]
 * @property {string | null} [coverageMap]
 * @property {string | null} [depGraph]
 */

/**
 * Assemble the post-fan-out audit pack (design §9.4).
 *
 * `artifacts` is a list of `[name, text]` pairs — findings-with-evidence (review) or
 * options-with-trade-offs (architect). `extras` carries the pack's optional sections (see
 * {@link OptionalSections}); omit it when none apply.
 * @param {string} gate
 * @param {string} role
 * @param {string} yardstick
 * @param {Array<[string, string]>} artifacts
 * @param {OptionalSections} [extras]
 * @returns {string}
 */
export function buildFullPack(gate, role, yardstick, artifacts, extras = {}) {
  _requireKnownRole(role);
  const data = _gateData().gate_pack;
  const lines = [
    fill(data.title, { gate }),
    "",
    fill(data.role_line, { role }),
    data.kind_full,
    fill(data.question_line, { question: roleQuestion()[role] }),
    "",
    data.yardstick_full_heading,
    "",
    yardstick,
    "",
    data.artifacts_heading,
    "",
  ];
  if (artifacts.length > 0) {
    for (const [name, text] of artifacts) {
      lines.push(fill(data.artifact_heading, { name }));
      lines.push("");
      lines.push(text);
      lines.push("");
    }
  } else {
    lines.push(data.artifacts_empty_sentinel);
    lines.push("");
  }

  if (extras.decisions !== undefined && extras.decisions !== null) {
    lines.push(data.decisions_heading);
    lines.push("");
    lines.push(extras.decisions);
    lines.push("");
  }

  lines.push(data.coverage_heading);
  lines.push("");
  lines.push(extras.coverageMap ?? data.coverage_empty_sentinel);
  lines.push("");

  if (extras.depGraph !== undefined && extras.depGraph !== null) {
    lines.push(data.dep_graph_heading);
    lines.push("");
    lines.push(extras.depGraph);
    lines.push("");
  }

  lines.push(data.what_to_return_heading);
  lines.push("");
  lines.push(...data.full_contract_bullets);
  return `${pyStrip(lines.join("\n"))}\n`;
}

/**
 * Assemble the minimal pre-fan-out pack (design §9.3 item 5).
 *
 * Yardstick + zone plan only, no artifacts and no coverage map: the plan is checked against the
 * stated goal, not against its own coverage map.
 * @param {string} gate
 * @param {string} role
 * @param {string} yardstick
 * @param {string} zonePlan
 * @returns {string}
 */
export function buildPlanCheckPack(gate, role, yardstick, zonePlan) {
  _requireKnownRole(role);
  const data = _gateData().gate_pack;
  const lines = [
    fill(data.title, { gate }),
    "",
    fill(data.role_line, { role }),
    data.kind_plan_check,
    fill(data.question_line, { question: planCheckQuestion() }),
    "",
    data.yardstick_plan_heading,
    "",
    yardstick,
    "",
    data.zone_plan_heading,
    "",
    zonePlan,
    "",
    data.what_to_return_heading,
    "",
    ...data.plan_contract_bullets,
  ];
  return `${pyStrip(lines.join("\n"))}\n`;
}

// --------------------------------------------------------------------------------------
// CLI
// --------------------------------------------------------------------------------------

/**
 * The directory a pack lands in by default: `<aitna-root>/artifacts/gates`.
 * @param {string} root
 * @returns {string}
 */
export function reportDir(root) {
  return pyPath(aitnaRoot(root), "artifacts", "gates");
}

/**
 * `[<task>-]<gate>-<kind>`: the default pack's name before its `-<n>.md` ordinal (C114).
 * @param {string} gate
 * @param {string} kind
 * @param {string | null} [task]
 * @returns {string}
 */
export function reportPrefix(gate, kind, task = null) {
  return taskPrefix(`${safeName(gate) || "gate"}-${kind}`, task);
}

/**
 * The head of `text` for the stdout summary: stripped, cut at `limit` characters.
 * @param {string} text
 * @param {number} [limit]
 * @returns {string}
 */
export function digest(text, limit = 1200) {
  const stripped = pyStrip(text);
  const chars = Array.from(stripped);
  if (chars.length <= limit) {
    return stripped;
  }
  // The kept head starts on a non-space, so stripping both ends is the Python `rstrip()`.
  return pyStrip(chars.slice(0, limit).join("")) + _gateData().truncation_suffix_pack;
}

/**
 * `out` as `Path.relative_to(root)` spells it, else as written (the Python prints it as given).
 * @param {string} root
 * @param {string} out
 * @returns {string}
 */
export function relativeTo(root, out) {
  const path = pyPath(out);
  return path.startsWith(`${root}/`) ? path.slice(root.length + 1) : path;
}

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, gate: string, role: string, kind: string, yardstick: string,
 *   artifacts: string[], decisions: string | null, coverageMap: string | null, zonePlan: string | null,
 *   depGraph: string | null, task: string | null, out: string | null, stdout: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        gate: { type: "string" },
        role: { type: "string" },
        kind: { type: "string" },
        yardstick: { type: "string" },
        artifact: { type: "string", multiple: true },
        decisions: { type: "string" },
        "coverage-map": { type: "string" },
        "zone-plan": { type: "string" },
        "dep-graph": { type: "string" },
        task: { type: "string" },
        out: { type: "string" },
        stdout: { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    const str = (/** @type {string} */ key) =>
      /** @type {string | undefined} */ (/** @type {Record<string, unknown>} */ (values)[key]) ?? null;
    if (values.help === true) {
      return {
        projectRoot: null,
        gate: "",
        role: "",
        kind: "full",
        yardstick: "",
        artifacts: [],
        decisions: null,
        coverageMap: null,
        zonePlan: null,
        depGraph: null,
        task: null,
        out: null,
        stdout: false,
        help: true,
      };
    }
    const missing = ["gate", "role", "yardstick"].filter((key) => str(key) === null);
    if (missing.length > 0) {
      return `the following arguments are required: ${missing.map((key) => `--${key}`).join(", ")}`;
    }
    const role = /** @type {string} */ (str("role"));
    const roles = codePointSort(Object.keys(roleQuestion()));
    if (!roles.includes(role)) {
      return `argument --role: invalid choice: '${role}' (choose from ${roles.map((r) => `'${r}'`).join(", ")})`;
    }
    const kind = str("kind") ?? "full";
    if (kind !== "full" && kind !== "plan-check") {
      return `argument --kind: invalid choice: '${kind}' (choose from 'full', 'plan-check')`;
    }
    const zonePlan = str("zone-plan");
    if (kind === "plan-check" && zonePlan === null) {
      return "--zone-plan is required for --kind plan-check";
    }
    const taskProblem = taskError(str("task"));
    if (taskProblem !== null) {
      return taskProblem;
    }
    return {
      projectRoot: str("project-root"),
      gate: /** @type {string} */ (str("gate")),
      role,
      kind,
      yardstick: /** @type {string} */ (str("yardstick")),
      artifacts: /** @type {string[] | undefined} */ (values.artifact) ?? [],
      decisions: str("decisions"),
      coverageMap: str("coverage-map"),
      zonePlan,
      depGraph: str("dep-graph"),
      task: str("task"),
      out: str("out"),
      stdout: values.stdout === true,
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
 * CLI entry point: build a gate pack from its inputs and write it under `artifacts/gates/`.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: 0, or 2 on a usage error.
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

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  const yardstickText = readText(options.yardstick);

  /** @type {string} */ let pack;
  if (options.kind === "plan-check") {
    const zonePlanText = readText(/** @type {string} */ (options.zonePlan));
    pack = buildPlanCheckPack(options.gate, options.role, yardstickText, zonePlanText);
  } else {
    /** @type {Array<[string, string]>} */
    const artifacts = options.artifacts.map((path) => [posix.basename(pyPath(path)), readText(path)]);
    const optional = (/** @type {string | null} */ path) => (path === null ? null : readText(path));
    pack = buildFullPack(options.gate, options.role, yardstickText, artifacts, {
      decisions: optional(options.decisions),
      coverageMap: optional(options.coverageMap),
      depGraph: optional(options.depGraph),
    });
  }

  /** @type {string} */ let out;
  if (options.out !== null) {
    out = options.out;
    fs.mkdirSync(posix.dirname(out), { recursive: true });
    writeText(out, pack);
  } else {
    out = createReport(reportDir(root), reportPrefix(options.gate, options.kind, options.task), pack);
  }

  process.stdout.write(`gate-pack kind=${options.kind} role=${options.role}\n`);
  process.stdout.write(`pack: ${relativeTo(root, out)}\n`);
  process.stdout.write("\n");
  process.stdout.write(`${digest(pack)}\n`);
  if (options.stdout) {
    process.stdout.write("\n");
    process.stdout.write(`${pack}\n`);
  }
  return 0;
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
