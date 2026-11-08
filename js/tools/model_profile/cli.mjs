#!/usr/bin/env node
/**
 * The model-profile probe: ask an endpoint's models the same items, grade the answers, write the
 * ledger — the JavaScript twin of `tools/model_profile/cli.py` (ADR 0020 D01). The Python module is
 * the reference: the same three commands, the same flags, the same output directory, the same
 * lines on stdout and the same exit codes.
 *
 * - `gate` — run the gold-sanity gate over the item set and report each case: the hidden test must
 *   fail on the buggy program and pass on the fixed one. It needs docker, not an endpoint.
 * - `plan` — print what a run would ask and what it would cost. Nothing is sent; the endpoint is asked
 *   only for the list of models when `--models` is not given.
 * - `probe` — run it. The spend is gated: it prints the plan and sends nothing without `--yes`.
 *   `--token-budget N` caps what each model may spend.
 *
 * The endpoint is an OpenAI-compatible server given by `--endpoint URL`. The bearer token is read
 * from the environment variable named by `--token-env` (default in `profile.json`) and is never
 * printed or written anywhere. A run writes under `<dev root>/.local/model_profile/<run>/` unless
 * `--out` names a directory.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`): the arguments are parsed by hand, because
 * `node:util` `parseArgs` has no `nargs="*"`; a usage error is the one line
 * `model_profile: error: …` on stderr and exit 2 (`argparse` prints its usage block and abbreviates
 * long options), `-h`/`--help` prints a short usage and exits 0; Ctrl-C ends the run between two
 * questions and exits 130, keeping what was written.
 */

import fs from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { FloatValue, hookForm } from "../../common/json_writer.mjs";
import { localRoot, resolveProjectRoot } from "../../common/project_root.mjs";
import { ItemSetError, loadItemSet, makeEnvelope } from "./cases.mjs";
import { GateRefusalError, gateOk, runGate, sandboxRunner, usableCaseIds } from "./oracle.mjs";
import { RunnerError, buildPlan, roundHalfEven, runProbe } from "./runner.mjs";
import { SandboxError, SandboxUnavailableError, ensureAvailable } from "./sandbox.mjs";
import * as settings from "./settings.mjs";
import { EndpointChannel, InterruptedError, TransportError, makeEndpointConfig, servedModels } from "./transport.mjs";

/** The command cannot be made — a broken request, not a model's failure. */
export class CliError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "CliError";
  }
}

/** The command line is not one the tool takes. */
class UsageError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "UsageError";
  }
}

/**
 * The parsed command line.
 * @typedef {object} Args
 * @property {string} command
 * @property {string} items
 * @property {string[] | null} families
 * @property {string[] | null} cases
 * @property {string | null} endpoint
 * @property {string} tokenEnv
 * @property {string[] | null} models
 * @property {string | null} out
 * @property {boolean} yes
 * @property {number | null} tokenBudget
 */

/**
 * @typedef {{key: keyof Args, kind: "value" | "list" | "flag" | "positive"}} OptionSpec
 */

/** @type {Record<string, OptionSpec>} */
const SELECTION_OPTIONS = {
  "--items": { key: "items", kind: "value" },
  "--families": { key: "families", kind: "list" },
  "--cases": { key: "cases", kind: "list" },
};

/** @type {Record<string, OptionSpec>} */
const ENDPOINT_OPTIONS = {
  "--endpoint": { key: "endpoint", kind: "value" },
  "--token-env": { key: "tokenEnv", kind: "value" },
  "--models": { key: "models", kind: "list" },
};

/** @type {Record<string, OptionSpec>} */
const PROBE_OPTIONS = {
  "--out": { key: "out", kind: "value" },
  "--yes": { key: "yes", kind: "flag" },
  "--token-budget": { key: "tokenBudget", kind: "positive" },
};

/** The options each command takes. */
const COMMAND_OPTIONS = {
  gate: SELECTION_OPTIONS,
  plan: { ...SELECTION_OPTIONS, ...ENDPOINT_OPTIONS },
  probe: { ...SELECTION_OPTIONS, ...ENDPOINT_OPTIONS, ...PROBE_OPTIONS },
};

const USAGE = [
  "usage: model_profile {gate,plan,probe} [options]",
  "",
  "  gate   run the gold-sanity gate over the item set (needs docker)",
  "  plan   print what a run would ask and cost",
  "  probe  run the probe and write the ledger",
  "",
  "options: --items FILE  --families F...  --cases ID...  --endpoint URL  --token-env NAME",
  "         --models M...  --out DIR  --yes  --token-budget N",
].join("\n");

/**
 * The shipped item set the pilot runs on.
 * @returns {string}
 */
export function defaultItemSet() {
  return join(settings.dataDir(), settings.load().cli.defaultItems);
}

/**
 * Whether a token begins an option (a negative number does not).
 * @param {string} token
 * @returns {boolean}
 */
function isOption(token) {
  return token.startsWith("-") && token.length > 1 && !/^-\d/.test(token);
}

/**
 * The value of an option that takes one, or a usage error.
 * @param {string} name
 * @param {string | null} inline the value after `=`, when given
 * @param {string[]} rest the tokens after the option
 * @returns {string}
 */
function takeValue(name, inline, rest) {
  if (inline !== null) {
    return inline;
  }
  if (rest.length === 0 || isOption(rest[0])) {
    throw new UsageError(`argument ${name}: expected one argument`);
  }
  return /** @type {string} */ (rest.shift());
}

/**
 * Set one option on `args`, taking its values off `rest`.
 * @param {Args} args
 * @param {string} name
 * @param {OptionSpec} spec
 * @param {{inline: string | null, rest: string[]}} source
 */
function setOption(args, name, spec, { inline, rest }) {
  const target = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (args));
  if (spec.kind === "flag") {
    target[spec.key] = true;
  } else if (spec.kind === "list") {
    const values = inline === null ? [] : [inline];
    while (rest.length > 0 && !isOption(rest[0])) {
      values.push(/** @type {string} */ (rest.shift()));
    }
    target[spec.key] = values;
  } else if (spec.kind === "positive") {
    const text = takeValue(name, inline, rest);
    const value = Number(text);
    if (!/^[+-]?\d+$/.test(text.trim()) || value < 1) {
      throw new UsageError(`argument ${name}: must be a positive integer, got ${text}`);
    }
    target[spec.key] = value;
  } else {
    target[spec.key] = takeValue(name, inline, rest);
  }
}

/**
 * The options of the command a command line names.
 * @param {string | undefined} command
 * @returns {Record<string, OptionSpec>}
 * @throws {UsageError} no command, or one the tool does not have
 */
function optionsOf(command) {
  if (command === undefined) {
    throw new UsageError("the following arguments are required: command");
  }
  if (!Object.hasOwn(COMMAND_OPTIONS, command)) {
    throw new UsageError(`argument command: invalid choice: '${command}' (choose from 'gate', 'plan', 'probe')`);
  }
  return COMMAND_OPTIONS[/** @type {keyof typeof COMMAND_OPTIONS} */ (command)];
}

/**
 * The arguments of a command, before any option is read.
 * @param {string} command
 * @returns {Args}
 */
function defaultArgs(command) {
  return {
    command,
    items: defaultItemSet(),
    families: null,
    cases: null,
    endpoint: null,
    tokenEnv: settings.load().cli.defaultTokenEnv,
    models: null,
    out: null,
    yes: false,
    tokenBudget: null,
  };
}

/**
 * The command line as arguments.
 * @param {readonly string[]} argv
 * @returns {Args | "help"}
 * @throws {UsageError} the command line is not one the tool takes
 */
export function parseArgs(argv) {
  const rest = [...argv];
  const command = rest.shift();
  if (command === "-h" || command === "--help") {
    return "help";
  }
  const options = optionsOf(command);
  const args = defaultArgs(/** @type {string} */ (command));
  while (rest.length > 0) {
    const token = /** @type {string} */ (rest.shift());
    if (token === "-h" || token === "--help") {
      return "help";
    }
    const [name, ...tail] = token.split("=");
    const spec = Object.hasOwn(options, name) ? options[name] : undefined;
    if (spec === undefined) {
      throw new UsageError(`unrecognized arguments: ${token}`);
    }
    setOption(args, name, spec, { inline: tail.length > 0 ? tail.join("=") : null, rest });
  }
  return args;
}

/**
 * The item set, loaded and validated.
 * @param {string} path
 * @param {import("./cases.mjs").Envelope} envelope
 * @returns {import("./cases.mjs").ItemSet}
 */
function loadItems(path, envelope) {
  try {
    return loadItemSet(path, envelope);
  } catch (exc) {
    if (exc instanceof ItemSetError) {
      throw new CliError(exc.message);
    }
    throw exc;
  }
}

/**
 * The endpoint configuration, read once here from the command line and the environment.
 * @param {Args} args
 * @param {Record<string, string | undefined>} environ
 * @returns {import("./transport.mjs").EndpointConfig}
 */
function endpointConfig(args, environ) {
  if (!args.endpoint) {
    throw new CliError("--endpoint URL is required: the base URL of an OpenAI-compatible endpoint");
  }
  const token = environ[args.tokenEnv] ?? "";
  if (token === "") {
    throw new CliError(
      `the environment variable ${args.tokenEnv} is not set: it must hold the endpoint's bearer token`,
    );
  }
  const trimmed = args.endpoint.replace(/\/+$/, "");
  const baseUrl = trimmed.endsWith("/v1") ? trimmed.slice(0, -3) : trimmed;
  try {
    return makeEndpointConfig(baseUrl, token);
  } catch (exc) {
    throw new CliError(/** @type {Error} */ (exc).message);
  }
}

/**
 * The envelope the request will carry, as the item set's hash sees it.
 * @param {import("./transport.mjs").EndpointConfig | null} config
 * @returns {import("./cases.mjs").Envelope}
 */
function envelopeOf(config) {
  if (config === null) {
    return makeEnvelope();
  }
  return makeEnvelope({
    temperature: config.temperature,
    maxOutputTokens: config.maxOutputTokens,
    timeoutS: config.timeoutS,
  });
}

/**
 * The models a run asks: the named ones, checked against what the endpoint serves, else all it serves.
 * @param {Args} args
 * @param {import("./transport.mjs").EndpointConfig} config
 * @returns {Promise<string[]>}
 */
async function modelsOf(args, config) {
  let served;
  try {
    served = await servedModels(config);
  } catch (exc) {
    if (exc instanceof TransportError) {
      throw new CliError(exc.message);
    }
    throw exc;
  }
  if (!args.models || args.models.length === 0) {
    return served;
  }
  const unknown = args.models.filter((name) => !served.includes(name));
  if (unknown.length > 0) {
    throw new CliError(
      `the endpoint does not serve ${unknown.join(", ")}; it serves ${served.join(", ") || "(nothing)"}`,
    );
  }
  return args.models;
}

/**
 * @param {Args} args
 * @param {readonly string[]} models
 * @returns {import("./runner.mjs").Selection}
 */
function selectionOf(args, models) {
  return {
    models: [...models],
    families: args.families && args.families.length > 0 ? args.families : null,
    caseIds: args.cases && args.cases.length > 0 ? args.cases : null,
  };
}

/**
 * A run's folder name: the moment as `strftime("%Y%m%dT%H%M%SZ")`.
 * @param {Date} now
 * @returns {string}
 */
function runFolder(now) {
  return `${now.toISOString().slice(0, 19).replace(/[-:]/g, "")}Z`;
}

/**
 * Where the run writes: `--out`, else a fresh folder in the local layer of the project.
 * @param {Args} args
 * @param {Date} now
 * @returns {string}
 */
function outDir(args, now) {
  if (args.out) {
    return args.out;
  }
  const { root, notice } = resolveProjectRoot(null);
  if (notice) {
    throw new CliError(`${notice}\nOr pass --out DIR to say where the run writes.`);
  }
  return join(localRoot(root), settings.load().cli.outSubdir, runFolder(now));
}

/**
 * The plan as it is printed: what is asked, against which yardstick, at what cost.
 * @param {import("./runner.mjs").Plan} plan
 * @param {import("./cases.mjs").ItemSet} itemSet
 * @returns {string}
 */
export function planText(plan, itemSet) {
  const grouped = (/** @type {number} */ n) => n.toLocaleString("en-US");
  return [
    `item set     ${itemSet.version}  cases_sha ${itemSet.casesSha}  envelope_sha ${itemSet.envelopeSha}`,
    `models       ${plan.models.join(", ")}`,
    `items        ${plan.pairs.length} (case, family) pairs x ${plan.models.length} models = ${plan.calls} calls`,
    `estimate     ~${roundHalfEven(plan.estimatedMinutes)} min wall-clock, ` +
      `~${grouped(plan.estimatedInputTokens)} input tokens, ~${grouped(plan.estimatedOutputTokens)} output tokens`,
  ].join("\n");
}

/**
 * @param {string} text
 */
function print(text) {
  process.stdout.write(`${text}\n`);
}

/**
 * Run the gold-sanity gate over the item set and report each case.
 * @param {Args} args
 * @returns {number}
 */
function cmdGate(args) {
  const itemSet = loadItems(args.items, makeEnvelope());
  ensureAvailable();
  const report = runGate(itemSet, sandboxRunner(), {
    caseIds: args.cases && args.cases.length > 0 ? args.cases : null,
    families: args.families && args.families.length > 0 ? args.families : null,
  });
  for (const outcome of report.outcomes) {
    print(`${outcome.usable ? "ok     " : "REFUSED"} ${outcome.caseId}: ${outcome.reason}`);
  }
  print(`\n${usableCaseIds(report).length} of ${report.outcomes.length} case(s) usable`);
  return gateOk(report) ? 0 : 1;
}

/**
 * Print what a run would ask and what it would cost — nothing is sent.
 * @param {Args} args
 * @param {Record<string, string | undefined>} environ
 * @returns {Promise<number>}
 */
async function cmdPlan(args, environ) {
  const named = args.models && args.models.length > 0;
  const config = named ? null : endpointConfig(args, environ);
  const models = named
    ? /** @type {string[]} */ (args.models)
    : await modelsOf(args, /** @type {NonNullable<typeof config>} */ (config));
  const itemSet = loadItems(args.items, envelopeOf(config));
  print(planText(buildPlan(itemSet, selectionOf(args, models)), itemSet));
  return 0;
}

/**
 * A float the way Python's `repr` writes it, `None` for a missing one.
 * @param {number | null | undefined} value
 * @returns {string}
 */
function floatText(value) {
  return value === null || value === undefined ? "None" : hookForm(new FloatValue(value));
}

/**
 * A count the way Python's `repr` writes it, `None` for a missing one.
 * @param {number | null | undefined} value
 * @returns {string}
 */
function countText(value) {
  if (value === null || value === undefined) {
    return "None";
  }
  return Number.isInteger(value) ? String(value) : floatText(value);
}

/**
 * @param {import("./runner.mjs").RunReport} report
 */
function printReport(report) {
  print(`\nledger      ${report.ledger}`);
  for (const row of report.rows) {
    const metrics = row.metrics;
    print(
      `${String(row.model).padEnd(24)} ${String(row.stage).padEnd(14)} ` +
        `scored ${metrics.scored}/${metrics.n}  ` +
        `pass_rate ${floatText(metrics.pass_rate)}  ` +
        `deferred ${metrics.deferred}  ` +
        `malformed ${metrics.malformed}  ` +
        `tokens ${countText(metrics.median_input_tokens)}+${countText(metrics.median_output_tokens)}  ` +
        `latency ${floatText(metrics.median_latency_s)}s  ` +
        `sufficient ${row.sufficient ? "True" : "False"}`,
    );
  }
  for (const band of report.itemBands) {
    print(
      `${settings.load().itemBand.name}  ${band.caseId}/${band.family}: ${band.status} ` +
        `(pass rate ${floatText(band.passRate)}, scored ${band.scored})`,
    );
  }
}

/**
 * Run the probe: ask, grade, and write the ledger as the run goes.
 * @param {Args} args
 * @param {Record<string, string | undefined>} environ
 * @returns {Promise<number>}
 */
async function cmdProbe(args, environ) {
  const config = endpointConfig(args, environ);
  const itemSet = loadItems(args.items, envelopeOf(config));
  const models = await modelsOf(args, config);
  const selection = selectionOf(args, models);
  print(planText(buildPlan(itemSet, selection), itemSet));
  if (args.tokenBudget !== null) {
    print(`budget       ${args.tokenBudget.toLocaleString("en-US")} tokens per model`);
  }
  if (!args.yes) {
    print("\nnothing was sent: pass --yes to run the plan above");
    return 2;
  }
  const now = new Date();
  const directory = outDir(args, now);
  print(`writing      ${directory}`);
  const controller = new AbortController();
  const interrupt = () => controller.abort();
  process.once("SIGINT", interrupt);
  try {
    const channel = new EndpointChannel(config, { interrupt: controller.signal });
    const report = await runProbe(itemSet, channel, selection, {
      outDir: directory,
      tokenBudget: args.tokenBudget,
      signal: controller.signal,
      now,
    });
    printReport(report);
    return 0;
  } catch (exc) {
    if (!(exc instanceof InterruptedError)) {
      throw exc;
    }
    process.stderr.write(`\ninterrupted: what was finished is kept in ${directory}\n`);
    return 130;
  } finally {
    process.removeListener("SIGINT", interrupt);
  }
}

/**
 * Whether an error is one a command reports as a line and an exit code 1.
 * @param {unknown} exc
 * @returns {exc is Error}
 */
function isReportable(exc) {
  return (
    exc instanceof CliError ||
    exc instanceof RunnerError ||
    exc instanceof GateRefusalError ||
    exc instanceof SandboxError ||
    exc instanceof SandboxUnavailableError
  );
}

/**
 * Run the parsed command.
 * @param {Args} args
 * @param {Record<string, string | undefined>} environ
 * @returns {Promise<number>}
 */
async function runCommand(args, environ) {
  if (args.command === "gate") {
    return cmdGate(args);
  }
  return args.command === "plan" ? cmdPlan(args, environ) : cmdProbe(args, environ);
}

/**
 * Run one command; the environment is read here, once, and passed down.
 * @param {readonly string[]} [argv]
 * @param {Record<string, string | undefined>} [environ]
 * @returns {Promise<number>} the exit code
 */
export async function main(argv = process.argv.slice(2), environ = process.env) {
  let args;
  try {
    args = parseArgs(argv);
  } catch (exc) {
    if (!(exc instanceof UsageError)) {
      throw exc;
    }
    process.stderr.write(`model_profile: error: ${exc.message}\n`);
    return 2;
  }
  if (args === "help") {
    print(USAGE);
    return 0;
  }
  try {
    return await runCommand(args, environ);
  } catch (exc) {
    if (!isReportable(exc)) {
      throw exc;
    }
    process.stderr.write(`${exc.message}\n`);
    return 1;
  }
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
