/**
 * The gold-sanity gate: a hidden test must fail on the buggy program and pass on the fixed one —
 * the JavaScript twin of `tools/model_profile/oracle.py` (ADR 0020 D01); the Python module is the
 * reference and the reasons are spelled the same.
 *
 * A weak oracle accepts wrong patches, and it inflates the cheap models most. So no item is asked of
 * any model before the runner has proved, on that item itself, that its hidden test separates the
 * buggy program from the fixed one. A case that fails either leg is refused and reported, never
 * scored and never dropped quietly. The third leg of the rule (the test also passes on the
 * unmutated original) has no data in the item set, so the gate implements the two legs the set can
 * express.
 *
 * This is the oracle gate on items. It is not one of the model `gates` and not the `item_band` of
 * `profile.json`; the module comment of `runner.mjs` says which is which.
 */

import { fixedProgram, program, selectCases } from "./cases.mjs";
import { failedTests, runHiddenTest } from "./sandbox.mjs";

/** The item set did not survive the gold-sanity gate — the run is refused, not scored. */
export class GateRefusalError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = "GateRefusalError";
  }
}

/**
 * What the gate found for one case.
 * @typedef {object} GateOutcome
 * @property {string} caseId
 * @property {boolean} usable
 * @property {string} reason
 */

/**
 * The gate's verdict over a set of cases.
 * @typedef {object} GateReport
 * @property {GateOutcome[]} outcomes
 */

/**
 * The ids of the cases the gate accepted.
 * @param {GateReport} report
 * @returns {string[]}
 */
export function usableCaseIds(report) {
  return report.outcomes.filter((outcome) => outcome.usable).map((outcome) => outcome.caseId);
}

/**
 * The cases the gate refused, with the reason each was refused.
 * @param {GateReport} report
 * @returns {GateOutcome[]}
 */
export function refusedOutcomes(report) {
  return report.outcomes.filter((outcome) => !outcome.usable);
}

/**
 * Whether every case survived the gate.
 * @param {GateReport} report
 * @returns {boolean}
 */
export function gateOk(report) {
  return refusedOutcomes(report).length === 0;
}

/**
 * The gate's verdict for one case: the hidden test must fail on the bug and pass on the fix.
 * @param {import("./cases.mjs").Case} item
 * @param {import("./sandbox.mjs").TestRunner} runTest
 * @returns {GateOutcome}
 */
export function checkCase(item, runTest) {
  const buggy = runTest(program(item), item.hiddenTest.path, item.hiddenTest.content);
  if (buggy.passed) {
    return {
      caseId: item.id,
      usable: false,
      reason:
        "the hidden test passes on the buggy program - it does not separate the " +
        "defect, so it would accept a wrong patch",
    };
  }
  const fixed = runTest(fixedProgram(item), item.hiddenTest.path, item.hiddenTest.content);
  if (!fixed.passed) {
    const failed = failedTests(fixed).join(", ") || "the test file itself broke";
    return {
      caseId: item.id,
      usable: false,
      reason: `the hidden test does not pass on the fixed program (${failed})`,
    };
  }
  return {
    caseId: item.id,
    usable: true,
    reason: "the hidden test fails on the buggy program and passes on the fixed one",
  };
}

/**
 * The runner that grades in the container — the hidden test travels in as a file.
 * @param {number | null} [timeoutS]
 * @returns {import("./sandbox.mjs").TestRunner}
 */
export function sandboxRunner(timeoutS = null) {
  return (files, testPath, testSource) =>
    runHiddenTest(files, testPath, { timeoutS, extraFiles: { [testPath]: testSource } });
}

/**
 * Run the gate over the item set's cases with `runTest` and report each one.
 * @param {import("./cases.mjs").ItemSet} itemSet
 * @param {import("./sandbox.mjs").TestRunner} runTest
 * @param {{caseIds?: readonly string[] | null, families?: readonly string[] | null}} [selection]
 * @returns {GateReport}
 */
export function runGate(itemSet, runTest, { caseIds = null, families = null } = {}) {
  return { outcomes: selectCases(itemSet, caseIds, families).map((item) => checkCase(item, runTest)) };
}

/**
 * Throw when any case was refused — a refused case is never scored silently.
 * @param {GateReport} report
 * @throws {GateRefusalError} at least one case did not survive the gate
 */
export function requireUsable(report) {
  if (gateOk(report)) {
    return;
  }
  const refused = refusedOutcomes(report);
  const lines = refused.map((outcome) => `  ${outcome.caseId}: ${outcome.reason}`).join("\n");
  throw new GateRefusalError(
    `${refused.length} case(s) did not survive the gold-sanity gate, so no model is asked about them:\n${lines}`,
  );
}
