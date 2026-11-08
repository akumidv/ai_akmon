/**
 * The model-profile tool's data: every constant, bar and name that is not code, read from
 * `tools/model_profile/profile.json` — the JavaScript twin of `tools/model_profile/settings.py`
 * (ADR 0020 D01). Both implementations read the same file, so a bar, a family name, a path or a
 * limit is written once and a score made by one twin is comparable with a score made by the other.
 * Code — the rules, the grading, the sandbox's argv — stays separate in each language.
 *
 * Nothing is read at import time: `load` reads and validates the file on the first call and hands
 * the same object back afterwards. The in-container runner's source is a Python program that both
 * twins ship to the container; `runnerSource` reads it the same way.
 */

import fs from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { read } from "../../common/jsondata.mjs";

/** The shared data directory: `tools/model_profile/`, two levels above `js/tools/model_profile/`. */
const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tools", "model_profile");

/** The data file's name. */
export const PROFILE_FILE = "profile.json";

/** `profile.json` or the in-container runner's source is missing or malformed. */
export class SettingsError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "SettingsError";
  }
}

/**
 * A bar one (model, family) cell is measured against; a `null` family means every family.
 * @typedef {object} Gate
 * @property {string} name
 * @property {string | null} family
 * @property {string} metric
 * @property {">=" | "<="} operator
 * @property {number} threshold
 * @property {string} meaning
 */

/**
 * The pass-rate band an item must sit in across the pool of models to separate them.
 * @typedef {object} Band
 * @property {string} name
 * @property {number} low
 * @property {number} high
 * @property {number} minScored
 * @property {string} meaning
 */

/**
 * @typedef {object} Settings
 * @property {number} hashLength
 * @property {{known: string[], hunt: string, fix: string[]}} families
 * @property {{case: string[], bug: string[], ask: string[], hiddenTest: string[]}} caseKeys
 * @property {{temperature: number, maxOutputTokens: number, timeoutS: number, responseFormat: string}} envelope
 * @property {{verdicts: string[], budgetReason: string, ledgerFile: string, detailDir: string}} run
 * @property {{callSeconds: number, sandboxSeconds: number, charsPerToken: number, outputTokens: number}} estimate
 * @property {Gate[]} gates
 * @property {Band} itemBand
 * @property {{completionsPath: string, modelsPath: string, doneSentinel: string, directScaffold: string,
 *   modelsTimeoutS: number, errorDetailChars: number}} transport
 * @property {{image: string, defaultTimeoutS: number, memoryLimit: string, pidsLimit: string,
 *   workspaceSize: string, containerUser: string, workDir: string, resultPrefix: string, runnerFile: string,
 *   nonceFile: string, runnerSourceFile: string, dockerFailureCodes: number[], dockerCommandTimeoutS: number,
 *   detailChars: number}} sandbox
 * @property {{defaultTokenEnv: string, outSubdir: string, defaultItems: string}} cli
 */

/**
 * One object section of the document.
 * @param {Record<string, any>} document
 * @param {string} name
 * @returns {Record<string, any>}
 */
function section(document, name) {
  const value = document[name];
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new SettingsError(`${PROFILE_FILE} has no '${name}' object`);
  }
  return value;
}

/**
 * Turn the document into the typed settings.
 * @param {Record<string, any>} document
 * @returns {Settings}
 */
function parse(document) {
  const families = section(document, "families");
  const keys = section(document, "case_keys");
  const envelope = section(document, "envelope");
  const run = section(document, "run");
  const estimate = section(document, "estimate");
  const band = section(document, "item_band");
  const transport = section(document, "transport");
  const sandbox = section(document, "sandbox");
  const cli = section(document, "cli");
  return {
    hashLength: document.hash_length,
    families: { known: [...families.known], hunt: families.hunt, fix: [...families.fix] },
    caseKeys: { case: [...keys.case], bug: [...keys.bug], ask: [...keys.ask], hiddenTest: [...keys.hidden_test] },
    envelope: {
      temperature: envelope.temperature,
      maxOutputTokens: envelope.max_output_tokens,
      timeoutS: envelope.timeout_s,
      responseFormat: envelope.response_format,
    },
    run: {
      verdicts: [...run.verdicts],
      budgetReason: run.budget_reason,
      ledgerFile: run.ledger_file,
      detailDir: run.detail_dir,
    },
    estimate: {
      callSeconds: estimate.call_seconds,
      sandboxSeconds: estimate.sandbox_seconds,
      charsPerToken: estimate.chars_per_token,
      outputTokens: estimate.output_tokens,
    },
    gates: document.gates.map((/** @type {Record<string, any>} */ gate) => ({ ...gate })),
    itemBand: {
      name: band.name,
      low: band.low,
      high: band.high,
      minScored: band.min_scored,
      meaning: band.meaning,
    },
    transport: {
      completionsPath: transport.completions_path,
      modelsPath: transport.models_path,
      doneSentinel: transport.done_sentinel,
      directScaffold: transport.direct_scaffold,
      modelsTimeoutS: transport.models_timeout_s,
      errorDetailChars: transport.error_detail_chars,
    },
    sandbox: {
      image: sandbox.image,
      defaultTimeoutS: sandbox.default_timeout_s,
      memoryLimit: sandbox.memory_limit,
      pidsLimit: sandbox.pids_limit,
      workspaceSize: sandbox.workspace_size,
      containerUser: sandbox.container_user,
      workDir: sandbox.work_dir,
      resultPrefix: sandbox.result_prefix,
      runnerFile: sandbox.runner_file,
      nonceFile: sandbox.nonce_file,
      runnerSourceFile: sandbox.runner_source_file,
      dockerFailureCodes: [...sandbox.docker_failure_codes],
      dockerCommandTimeoutS: sandbox.docker_command_timeout_s,
      detailChars: sandbox.detail_chars,
    },
    cli: { defaultTokenEnv: cli.default_token_env, outSubdir: cli.out_subdir, defaultItems: cli.default_items },
  };
}

/** @type {Settings | null} */
let cached = null;

/**
 * Read `profile.json` once and hand back its typed contents.
 * @returns {Settings}
 * @throws {SettingsError} the file is missing, is not JSON, or lacks a section or a key
 */
export function load() {
  if (cached === null) {
    const path = join(DATA_DIR, PROFILE_FILE);
    let document;
    try {
      document = /** @type {Record<string, any>} */ (read(path));
    } catch (exc) {
      throw new SettingsError(`the model-profile data file cannot be read: ${/** @type {Error} */ (exc).message}`);
    }
    try {
      cached = parse(document);
    } catch (exc) {
      if (exc instanceof SettingsError) {
        throw exc;
      }
      throw new SettingsError(
        `the model-profile data file ${path} is malformed: ${/** @type {Error} */ (exc).message}`,
      );
    }
  }
  return cached;
}

/** @type {string | null} */
let cachedRunner = null;

/**
 * The source of the program that runs the hidden test inside the container.
 * @returns {string}
 * @throws {SettingsError} the file is missing
 */
export function runnerSource() {
  if (cachedRunner === null) {
    const path = join(DATA_DIR, load().sandbox.runnerSourceFile);
    try {
      cachedRunner = fs.readFileSync(path, "utf8");
    } catch (exc) {
      throw new SettingsError(
        `the in-container runner's source cannot be read: ${path}: ${/** @type {Error} */ (exc).message}`,
      );
    }
  }
  return cachedRunner;
}

/**
 * The shared data directory — where `profile.json`, the runner's source and the shipped item set live.
 * @returns {string}
 */
export function dataDir() {
  return DATA_DIR;
}
