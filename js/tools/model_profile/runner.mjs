/**
 * The probe runner: ask a model through a channel, grade the answer, and write the ledger — the
 * JavaScript twin of `tools/model_profile/runner.py` (ADR 0020 D01); the Python module is the
 * reference, and a ledger written by one twin is read by the other.
 *
 * One run covers a list of models over a case/family selection. The order of the stages is the
 * discipline:
 *
 * 1. **The gold-sanity gate runs first, over the whole selection.** A case the gate refuses is never
 *    scored: the run is refused and the refusal is reported.
 * 2. **Every model is asked the same items**, under one pinned envelope, and each answer is graded by
 *    a mechanical rule: a location hit for the hunt family, the hidden test for the two fix
 *    families. The scaffold is the one the channel carries.
 * 3. **A deferral is not a failure.** A transport failure, an empty answer, a cut-off answer and an
 *    attempt skipped for the token budget stay out of the pass rate.
 * 4. **A malformed hunt answer is not a wrong location.** It is counted as `malformed` on its own
 *    line and excluded from the localization rates.
 *
 * Three different gates live in the tool, and they judge three different things: the **oracle gate**
 * (`oracle.mjs`) judges an item's hidden test; the **model gates** (`gates` in `profile.json`) judge
 * a model's cell against a bar — provisional, no published absolute threshold exists; the
 * **item-selection band** (`item_band` in `profile.json`) judges an item across the pool of models
 * and reports `pool_too_small` below `min_scored` attempts. The `items_scored` bar is 30 because a
 * binary family at p ~ 0.5 has a standard error of about 9 points at 30 items.
 *
 * **Nothing is lost to a crash.** Each attempt is appended to its detail file the moment it
 * finishes. A cell's ledger row is appended when the cell is complete; an interrupted run appends the
 * rows of the cells it had begun with `complete: false` before the error propagates. A re-run into
 * the same output directory appends to what is there.
 *
 * **The token budget is per model.** A model that has spent that many prompt-plus-completion tokens
 * is not called again: its remaining attempts are recorded as deferrals with the reason `budget`.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`): a line is written with `JSON.stringify`, so a
 * float with no fraction reads `1` where the Python twin writes `1.0`; the run is interrupted by an
 * `AbortSignal` the entry point wires to Ctrl-C.
 */

import fs from "node:fs";
import { dirname, join } from "node:path";

import { askOf, selectCases } from "./cases.mjs";
import { requireUsable, runGate, sandboxRunner } from "./oracle.mjs";
import { SandboxError } from "./sandbox.mjs";
import { huntReason, scoreFix, scoreHunt } from "./scoring.mjs";
import * as settings from "./settings.mjs";
import { InterruptedError, variantRecord } from "./transport.mjs";

/** The run cannot be made — a broken selection, not a model's failure. */
export class RunnerError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "RunnerError";
  }
}

/**
 * What a run asks: which models, over which families and cases (`null` is all).
 * @typedef {object} Selection
 * @property {readonly string[]} models
 * @property {readonly string[] | null} [families]
 * @property {readonly string[] | null} [caseIds]
 */

/**
 * How a run is made: where it writes, how long the sandbox may take, the budget per model.
 * @typedef {object} RunOptions
 * @property {string} outDir
 * @property {number | null} [sandboxTimeoutS] `null` is the profile's default
 * @property {number | null} [tokenBudget]
 * @property {import("./sandbox.mjs").TestRunner | null} [runTest] grades a hidden test; `null` is the container sandbox
 * @property {Date | null} [now] the run's timestamp; `null` is the current time
 * @property {((source: string) => {compiled: boolean, detail: string}) | null} [compileCheck] asks whether a
 *   fix compiles; `null` is the container's interpreter (a stand-in for tests)
 * @property {AbortSignal | null} [signal] the owner's interrupt
 */

/**
 * What one question earned, before it is tied to the model and the case.
 * @typedef {object} Outcome
 * @property {string} verdict
 * @property {string} reason
 * @property {number} promptTokens
 * @property {number} completionTokens
 * @property {number} latencyS
 * @property {string} answer
 * @property {boolean | null} locationHit
 * @property {boolean | null} fileHit
 */

/**
 * One question asked of one model, and what it earned.
 * @typedef {object} Attempt
 * @property {string} model
 * @property {string} caseId
 * @property {string} family
 * @property {string} scaffold
 * @property {string} envelopeSha
 * @property {string} casesSha
 * @property {string} seed
 * @property {string} ts
 * @property {Outcome} outcome
 */

/**
 * What a run would ask, and what it would cost.
 * @typedef {object} Plan
 * @property {[string, string][]} pairs
 * @property {readonly string[]} models
 * @property {number} calls
 * @property {number} estimatedMinutes
 * @property {number} estimatedInputTokens
 * @property {number} estimatedOutputTokens
 */

/**
 * Where one (case, family) item sits against the item band across the pool.
 * @typedef {object} ItemBandResult
 * @property {string} caseId
 * @property {string} family
 * @property {number} scored
 * @property {number | null} passRate
 * @property {"in_band" | "outside_band" | "pool_too_small"} status
 */

/**
 * What a run produced.
 * @typedef {object} RunReport
 * @property {Attempt[]} attempts
 * @property {Record<string, any>[]} rows
 * @property {import("./oracle.mjs").GateReport} gate
 * @property {ItemBandResult[]} itemBands
 * @property {string} ledger
 * @property {string[]} detailFiles
 */

/** @typedef {import("./cases.mjs").Case} Case */
/** @typedef {import("./cases.mjs").ItemSet} ItemSet */
/** @typedef {import("./transport.mjs").Channel} Channel */

/**
 * Python's `format(value, "g")`: six significant digits, trailing zeros dropped, an exponent below
 * -4 or from 6 up. A gate's number is written this way in the failure it names.
 * @param {number} value
 * @returns {string}
 */
export function formatG(value) {
  if (value === 0) {
    return "0";
  }
  const [mantissa, power] = value.toExponential(5).split("e");
  const exponent = Number(power);
  if (exponent < -4 || exponent >= 6) {
    const digits = mantissa.includes(".") ? mantissa.replace(/\.?0+$/, "") : mantissa;
    return `${digits}e${exponent < 0 ? "-" : "+"}${String(Math.abs(exponent)).padStart(2, "0")}`;
  }
  const fixed = value.toFixed(5 - exponent);
  return fixed.includes(".") ? fixed.replace(/\.?0+$/, "") : fixed;
}

/**
 * Round to a whole number, a tie going to the even neighbour — Python's `format(value, ".0f")`.
 * @param {number} value
 * @returns {number}
 */
export function roundHalfEven(value) {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff === 0.5) {
    return floor % 2 === 0 ? floor : floor + 1;
  }
  return Math.round(value);
}

/**
 * A prompt's length in code points, the way Python's `len` counts it.
 * @param {string} text
 * @returns {number}
 */
function codePointLength(text) {
  return [...text].length;
}

/**
 * The (case, family) pairs a run asks, in the item set's own order.
 * @param {ItemSet} itemSet
 * @param {Selection} selection
 * @returns {[Case, string][]}
 */
function selectedPairs(itemSet, selection) {
  const families = selection.families ?? null;
  const wanted = families === null ? null : new Set(families);
  /** @type {[Case, string][]} */
  const pairs = [];
  for (const item of selectCases(itemSet, selection.caseIds ?? null, families)) {
    for (const family of item.families) {
      if (wanted === null || wanted.has(family)) {
        pairs.push([item, family]);
      }
    }
  }
  return pairs;
}

/**
 * The prompt's size in tokens, estimated from its characters.
 * @param {Case} item
 * @param {string} family
 * @returns {number}
 */
function promptTokens(item, family) {
  const ask = askOf(item, family);
  const chars = codePointLength(ask.system) + codePointLength(ask.user);
  return Math.ceil(chars / settings.load().estimate.charsPerToken);
}

/**
 * The (case id, family) pairs a run would ask, with a rough time and token estimate. The estimate
 * stands on four constants (`estimate` in `profile.json`): seconds per call, seconds per sandboxed
 * run (the two fix families only), characters per token and tokens per answer.
 * @param {ItemSet} itemSet
 * @param {Selection} selection
 * @returns {Plan}
 */
export function buildPlan(itemSet, selection) {
  const { estimate, families: familyNames } = settings.load();
  const pairs = selectedPairs(itemSet, selection);
  const models = selection.models.length;
  const calls = pairs.length * models;
  const inputTokens = pairs.reduce((sum, [item, family]) => sum + promptTokens(item, family), 0) * models;
  const sandboxRuns = pairs.filter(([, family]) => familyNames.fix.includes(family)).length * models;
  const seconds = calls * estimate.callSeconds + sandboxRuns * estimate.sandboxSeconds;
  return {
    pairs: pairs.map(([item, family]) => [item.id, family]),
    models: selection.models,
    calls,
    estimatedMinutes: Number((seconds / 60).toFixed(1)),
    estimatedInputTokens: inputTokens,
    estimatedOutputTokens: calls * estimate.outputTokens,
  };
}

/**
 * @param {string} reason
 * @param {import("./transport.mjs").Usage} usage
 * @param {number} latencyS
 * @param {string} [answer]
 * @returns {Outcome}
 */
function deferred(reason, usage, latencyS, answer = "") {
  return {
    verdict: "deferred",
    reason,
    promptTokens: usage.promptTokens,
    completionTokens: usage.completionTokens,
    latencyS,
    answer,
    locationHit: null,
    fileHit: null,
  };
}

/**
 * Grade a hunt answer: the file and the function, kept apart; a format miss is `malformed`.
 * @param {Case} item
 * @param {import("./transport.mjs").Answer} answer
 * @returns {Outcome}
 */
function gradeHunt(item, answer) {
  const expected = { expectedFile: item.bug.file, expectedFunction: item.bug.function };
  const hit = scoreHunt(answer.text, expected);
  let reason = huntReason(hit, expected);
  let verdict = "fail";
  if (hit.malformed) {
    verdict = "malformed";
  } else if (hit.hit) {
    verdict = "pass";
    reason = "the answer names the file and the function that hold the defect";
  }
  return {
    verdict,
    reason,
    promptTokens: answer.usage.promptTokens,
    completionTokens: answer.usage.completionTokens,
    latencyS: answer.latencyS,
    answer: answer.text,
    locationHit: hit.malformed ? null : hit.hit,
    fileHit: hit.malformed ? null : hit.fileHit,
  };
}

/**
 * Grade a fix answer: the one block replaces the defective file and the hidden test must pass.
 * @param {Case} item
 * @param {import("./transport.mjs").Answer} answer
 * @param {import("./sandbox.mjs").TestRunner} runTest
 * @param {((source: string) => {compiled: boolean, detail: string})} [compileCheck]
 * @returns {Outcome}
 */
function gradeFix(item, answer, runTest, compileCheck) {
  const verdict = scoreFix(answer.text, item, runTest, compileCheck);
  return {
    verdict: verdict.passed ? "pass" : "fail",
    reason: verdict.reason,
    promptTokens: answer.usage.promptTokens,
    completionTokens: answer.usage.completionTokens,
    latencyS: answer.latencyS,
    answer: answer.text,
    locationHit: null,
    fileHit: null,
  };
}

/**
 * A rate over the scored attempts — `null` when nothing was scored.
 * @param {number} passed
 * @param {number} scored
 * @returns {number | null}
 */
function rate(passed, scored) {
  return scored === 0 ? null : passed / scored;
}

/**
 * The median of a set of values — `null` when the set is empty.
 * @param {readonly number[]} values
 * @returns {number | null}
 */
function median(values) {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

/**
 * @param {readonly Attempt[]} attempts
 * @param {string} verdict
 * @returns {number}
 */
function count(attempts, verdict) {
  return attempts.filter((attempt) => attempt.outcome.verdict === verdict).length;
}

/**
 * The metrics of one (model, family) cell. The pass rate is computed over the scored attempts only
 * (`pass` and `fail`): a deferral and a malformed answer are each counted on their own line and never
 * as a miss. The latency median covers every attempt that called the model.
 * @param {readonly Attempt[]} cell
 * @returns {Record<string, number | null>}
 */
export function cellMetrics(cell) {
  const scored = cell.filter((attempt) => attempt.outcome.verdict === "pass" || attempt.outcome.verdict === "fail");
  const passed = count(scored, "pass");
  const called = cell.filter((attempt) => attempt.outcome.reason !== settings.load().run.budgetReason);
  /** @type {Record<string, number | null>} */
  const metrics = {
    n: cell.length,
    scored: scored.length,
    passed,
    failed: scored.length - passed,
    deferred: count(cell, "deferred"),
    malformed: count(cell, "malformed"),
    pass_rate: rate(passed, scored.length),
    median_output_tokens: median(scored.map((attempt) => attempt.outcome.completionTokens)),
    median_input_tokens: median(scored.map((attempt) => attempt.outcome.promptTokens)),
    median_latency_s: median(called.map((attempt) => attempt.outcome.latencyS)),
  };
  const hunt = scored.filter((attempt) => attempt.family === settings.load().families.hunt);
  if (hunt.length > 0) {
    metrics.location_hit_rate = rate(hunt.filter((attempt) => attempt.outcome.locationHit).length, hunt.length);
    metrics.file_localization_rate = rate(hunt.filter((attempt) => attempt.outcome.fileHit).length, hunt.length);
  }
  return metrics;
}

/**
 * Whether a value meets a gate's bar — an undefined value meets nothing.
 * @param {settings.Gate} gate
 * @param {number | null} value
 * @returns {boolean}
 */
function meets(gate, value) {
  if (value === null) {
    return false;
  }
  return gate.operator === ">=" ? value >= gate.threshold : value <= gate.threshold;
}

/**
 * A number as it is written in a failed gate.
 * @param {number | null} value
 * @returns {string}
 */
function gateNumber(value) {
  return value === null ? "n/a" : formatG(value);
}

/**
 * The model gates this cell fails, each naming the gate, its number and what it means.
 * @param {Record<string, number | null>} metrics
 * @param {string} family
 * @returns {string[]}
 */
export function evaluateGates(metrics, family) {
  /** @type {string[]} */
  const failed = [];
  for (const gate of settings.load().gates) {
    if (gate.family !== null && gate.family !== family) {
      continue;
    }
    const value = metrics[gate.metric] ?? null;
    if (!meets(gate, value)) {
      failed.push(`${gate.name} ${gateNumber(value)} ${gate.operator} ${gateNumber(gate.threshold)} - ${gate.meaning}`);
    }
  }
  return failed;
}

/**
 * Where each (case, family) item sits against the item band, over the scored attempts of every model.
 * @param {readonly Attempt[]} attempts
 * @returns {ItemBandResult[]}
 */
export function itemBands(attempts) {
  const band = settings.load().itemBand;
  /** @type {Map<string, Attempt[]>} */
  const pools = new Map();
  for (const attempt of attempts) {
    if (attempt.outcome.verdict === "pass" || attempt.outcome.verdict === "fail") {
      const key = JSON.stringify([attempt.caseId, attempt.family]);
      pools.set(key, [...(pools.get(key) ?? []), attempt]);
    }
  }
  return [...pools.values()].map((pool) => {
    const passRate = rate(count(pool, "pass"), pool.length);
    /** @type {ItemBandResult["status"]} */
    let status = "outside_band";
    if (pool.length < band.minScored || passRate === null) {
      status = "pool_too_small";
    } else if (band.low <= passRate && passRate <= band.high) {
      status = "in_band";
    }
    return { caseId: pool[0].caseId, family: pool[0].family, scored: pool.length, passRate, status };
  });
}

/**
 * A name safe for a filename — a model id may carry a slash.
 * @param {string} name
 * @returns {string}
 */
function safeName(name) {
  return name.replace(/[^A-Za-z0-9._-]/gu, "_");
}

/**
 * One (model, family) cell's detail file, relative to the run's output directory.
 * @param {string} model
 * @param {string} family
 * @returns {string}
 */
export function detailRef(model, family) {
  return `${settings.load().run.detailDir}/${safeName(model)}__${safeName(family)}.jsonl`;
}

/**
 * Append one JSON object to a file as a line, and push it to disk before returning.
 * @param {string} path
 * @param {unknown} row
 */
function appendJsonl(path, row) {
  fs.mkdirSync(dirname(path), { recursive: true });
  const handle = fs.openSync(path, "a");
  try {
    fs.writeSync(handle, `${JSON.stringify(row)}\n`);
    fs.fsyncSync(handle);
  } finally {
    fs.closeSync(handle);
  }
}

/**
 * A moment as Python's `datetime.isoformat()` writes a UTC one: microseconds only when they are
 * not zero, and `+00:00` for the offset.
 * @param {Date} moment
 * @returns {string}
 */
export function isoformat(moment) {
  const iso = moment.toISOString();
  const [stamp, fraction] = iso.slice(0, -1).split(".");
  const micro = fraction === "000" ? "" : `.${fraction}000`;
  return `${stamp}${micro}+00:00`;
}

/**
 * Round to three decimals — the detail file's latency.
 * @param {number} value
 * @returns {number}
 */
function round3(value) {
  return Number(value.toFixed(3));
}

/**
 * The attempt as one JSON object — a line of the detail file.
 * @param {Attempt} attempt
 * @returns {Record<string, unknown>}
 */
export function attemptRecord(attempt) {
  const outcome = attempt.outcome;
  return {
    ts: attempt.ts,
    model: attempt.model,
    case_id: attempt.caseId,
    family: attempt.family,
    scaffold: attempt.scaffold,
    envelope_sha: attempt.envelopeSha,
    cases_sha: attempt.casesSha,
    seed: attempt.seed,
    verdict: outcome.verdict,
    reason: outcome.reason,
    answer: outcome.answer,
    prompt_tokens: outcome.promptTokens,
    completion_tokens: outcome.completionTokens,
    latency_s: round3(outcome.latencyS),
    location_hit: outcome.locationHit,
    file_hit: outcome.fileHit,
  };
}

/** The state of one run: what was asked, what it cost, and what has been written down. */
class ProbeRun {
  /**
   * @param {ItemSet} itemSet
   * @param {Channel} channel
   * @param {RunOptions} options
   * @param {{stamp: Date, runTest: import("./sandbox.mjs").TestRunner}} context
   */
  constructor(itemSet, channel, options, { stamp, runTest }) {
    this._itemSet = itemSet;
    this._channel = channel;
    this._options = options;
    this._stamp = stamp;
    this._runTest = runTest;
    /** @type {Attempt[]} */
    this.attempts = [];
    /** @type {Record<string, any>[]} */
    this.rows = [];
    /** @type {string[]} */
    this.detailFiles = [];
    /** @type {Map<string, number>} */
    this._spent = new Map();
    /** @type {Set<string>} */
    this._flushed = new Set();
  }

  /** Where the ledger rows go. */
  get ledger() {
    return join(this._options.outDir, settings.load().run.ledgerFile);
  }

  /**
   * Ask one model one question, grade it, and write the attempt down before returning.
   * @param {string} model
   * @param {Case} item
   * @param {string} family
   */
  async step(model, item, family) {
    if (this._options.signal?.aborted) {
      throw new InterruptedError();
    }
    const budget = this._options.tokenBudget ?? null;
    if (budget !== null && (this._spent.get(model) ?? 0) >= budget) {
      const outcome = deferred(settings.load().run.budgetReason, { promptTokens: 0, completionTokens: 0 }, 0);
      this._record(model, item, family, this._channel.variant(model).scaffold, outcome);
      return;
    }
    const ask = askOf(item, family);
    const completion = await this._channel.complete(model, ask.system, ask.user);
    const scaffold = completion.variant.scaffold;
    if (completion.kind === "deferral") {
      this._record(model, item, family, scaffold, deferred(completion.reason, completion.usage, completion.latencyS));
      return;
    }
    this._record(model, item, family, scaffold, this._grade(model, item, family, completion));
  }

  /**
   * Grade an answer; when the sandbox cannot grade, keep the answer and its cost, then stop the run.
   * @param {string} model
   * @param {Case} item
   * @param {string} family
   * @param {import("./transport.mjs").Answer} completion
   * @returns {Outcome}
   */
  _grade(model, item, family, completion) {
    try {
      return family === settings.load().families.hunt
        ? gradeHunt(item, completion)
        : gradeFix(item, completion, this._runTest, this._options.compileCheck ?? undefined);
    } catch (exc) {
      if (exc instanceof SandboxError) {
        const outcome = deferred(
          `sandbox error: ${exc.message}`,
          completion.usage,
          completion.latencyS,
          completion.text,
        );
        this._record(model, item, family, completion.variant.scaffold, outcome);
      }
      throw exc;
    }
  }

  /**
   * @param {string} model
   * @param {Case} item
   * @param {string} family
   * @param {string} scaffold
   * @param {Outcome} outcome
   */
  _record(model, item, family, scaffold, outcome) {
    /** @type {Attempt} */
    const attempt = {
      model,
      caseId: item.id,
      family,
      scaffold,
      envelopeSha: this._itemSet.envelopeSha,
      casesSha: this._itemSet.casesSha,
      seed: this._itemSet.version,
      ts: isoformat(this._stamp),
      outcome,
    };
    this.attempts.push(attempt);
    this._spent.set(model, (this._spent.get(model) ?? 0) + outcome.promptTokens + outcome.completionTokens);
    appendJsonl(join(this._options.outDir, detailRef(model, family)), attemptRecord(attempt));
  }

  /**
   * Append the ledger row of every not-yet-written cell (of `models`, when given).
   * @param {{complete: boolean, models?: readonly string[] | null}} flush
   */
  flushCells({ complete, models = null }) {
    /** @type {Map<string, {key: [string, string], cell: Attempt[]}>} */
    const cells = new Map();
    for (const attempt of this.attempts) {
      if (models === null || models.includes(attempt.model)) {
        const id = JSON.stringify([attempt.model, attempt.family]);
        const entry = cells.get(id) ?? { key: [attempt.model, attempt.family], cell: [] };
        entry.cell.push(attempt);
        cells.set(id, entry);
      }
    }
    for (const [id, { key, cell }] of cells) {
      if (this._flushed.has(id)) {
        continue;
      }
      this._flushed.add(id);
      const metrics = cellMetrics(cell);
      const row = this._ledgerRow(key, metrics, evaluateGates(metrics, key[1]), complete);
      this.rows.push(row);
      this.detailFiles.push(join(this._options.outDir, detailRef(key[0], key[1])));
      appendJsonl(this.ledger, row);
    }
  }

  /**
   * One ledger row, keyed by (model, family) the way a score is looked up later. `target` is the
   * harness the run was made under and `stage` is the probe family.
   * @param {[string, string]} key
   * @param {Record<string, number | null>} metrics
   * @param {readonly string[]} failed
   * @param {boolean} complete
   * @returns {Record<string, any>}
   */
  _ledgerRow([model, family], metrics, failed, complete) {
    const variant = this._channel.variant(model);
    return {
      date: this._stamp.toISOString().slice(0, 10),
      ts: isoformat(this._stamp),
      target: variant.scaffold,
      model,
      endpoint: this._channel.endpoint,
      request: variantRecord(variant),
      stage: family,
      cases_sha: this._itemSet.casesSha,
      system_sha: this._itemSet.envelopeSha,
      sufficient: complete && failed.length === 0,
      complete,
      failed: [...failed],
      metrics: { ...metrics },
      detail: detailRef(model, family),
    };
  }
}

/**
 * Ask every model every selected item, grade the answers and write the ledger. The gold-sanity gate
 * runs first over the whole selection: a case it refuses is never scored, and the run is refused with
 * the refusal reported. The ledger rows go to `<outDir>/ledger.jsonl` and each cell's attempts to
 * `<outDir>/detail/<model>__<family>.jsonl`; both are appended as the run goes.
 * @param {ItemSet} itemSet
 * @param {Channel} channel
 * @param {Selection} selection
 * @param {RunOptions} options
 * @returns {Promise<RunReport>}
 * @throws {RunnerError} the selection holds nothing to ask
 * @throws {import("./oracle.mjs").GateRefusalError} an item did not survive the gold-sanity gate
 * @throws {SandboxError} the sandbox failed while grading; the rows so far are kept
 * @throws {InterruptedError} the owner interrupted the run; the rows so far are kept
 */
export async function runProbe(itemSet, channel, selection, options) {
  const pairs = selectedPairs(itemSet, selection);
  if (pairs.length === 0) {
    throw new RunnerError("nothing to ask: the selection holds no (case, family) pair");
  }
  if (selection.models.length === 0) {
    throw new RunnerError("nothing to ask: no model was named");
  }
  const grader = options.runTest ?? sandboxRunner(options.sandboxTimeoutS ?? null);
  const selected = [...new Set(pairs.map(([item]) => item.id))];
  const gate = runGate(itemSet, grader, { caseIds: selected, families: selection.families ?? null });
  requireUsable(gate);
  const run = new ProbeRun(itemSet, channel, options, { stamp: options.now ?? new Date(), runTest: grader });
  try {
    for (const model of selection.models) {
      for (const [item, family] of pairs) {
        await run.step(model, item, family);
      }
      run.flushCells({ complete: true, models: [model] });
    }
  } finally {
    run.flushCells({ complete: false });
  }
  return {
    attempts: run.attempts,
    rows: run.rows,
    gate,
    itemBands: itemBands(run.attempts),
    ledger: run.ledger,
    detailFiles: run.detailFiles,
  };
}
