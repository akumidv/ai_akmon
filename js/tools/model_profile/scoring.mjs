/**
 * Grade one answer per family — pure rules, so a score can be re-derived from the answer. The
 * JavaScript twin of `tools/model_profile/scoring.py` (ADR 0020 D01); the Python module is the
 * reference and the reasons are spelled the same.
 *
 * - **hunt** — the answer must be exactly one line, `file.py:function_name`. A hit needs both the
 *   file and the function; the file's own correctness is recorded beside it. An answer that is not
 *   one such line is malformed, counted apart from a wrong location.
 * - **fix-traceback / fix-symptom** — the answer must carry exactly one fenced ```python block, and
 *   that block must compile; it is the corrected content of the file that holds the defect. The fix
 *   passes when the hidden test passes on the program with that one file replaced. An answer with no
 *   block, or a block that does not compile, is a wrong answer — never a deferral.
 *
 * Twin note: whether a block compiles is asked of the container's interpreter (`checkCompiles`),
 * where the Python twin asks `ast.parse`; the verdict is the same, the quoted message is the
 * interpreter's own.
 */

import { program } from "./cases.mjs";
import { checkCompiles, extractPythonBlock, failedTests } from "./sandbox.mjs";

/** The one line a hunt answer must be: a Python file, a colon, a function name. */
const LOCATION = /^([^\s:]+\.py):([A-Za-z_][A-Za-z0-9_]*)$/;

/**
 * What a hunt answer named, and how much of it was right.
 * @typedef {object} LocationHit
 * @property {boolean} hit
 * @property {boolean} fileHit
 * @property {boolean} functionHit
 * @property {boolean} malformed
 * @property {string | null} file
 * @property {string | null} function
 */

/**
 * What a fix answer earned.
 * @typedef {object} FixVerdict
 * @property {boolean} passed
 * @property {string} reason
 * @property {boolean} compiled
 * @property {string[]} failedTests
 */

/**
 * The `[file, function]` a hunt answer names — `null` when it is not one clean line.
 * @param {string} answer
 * @returns {[string, string] | null}
 */
export function parseLocation(answer) {
  const text = answer.trim();
  if (text === "" || text.includes("\n")) {
    return null;
  }
  const match = LOCATION.exec(text);
  return match === null ? null : [match[1], match[2]];
}

/**
 * Grade a hunt answer against the case's defect — the file's correctness is kept apart.
 * @param {string} answer
 * @param {{expectedFile: string, expectedFunction: string}} expected
 * @returns {LocationHit}
 */
export function scoreHunt(answer, { expectedFile, expectedFunction }) {
  const parsed = parseLocation(answer);
  if (parsed === null) {
    return { hit: false, fileHit: false, functionHit: false, malformed: true, file: null, function: null };
  }
  const [file, name] = parsed;
  const fileHit = file === expectedFile;
  const functionHit = name === expectedFunction;
  return { hit: fileHit && functionHit, fileHit, functionHit, malformed: false, file, function: name };
}

/**
 * Why a hunt answer missed — a localization gap and a wrong file read differently.
 * @param {LocationHit} hit
 * @param {{expectedFile: string, expectedFunction: string}} expected
 * @returns {string}
 */
export function huntReason(hit, { expectedFile, expectedFunction }) {
  if (hit.malformed) {
    return "the answer is not one line of the form file.py:function_name";
  }
  if (hit.fileHit && !hit.functionHit) {
    return (
      `the right file, the wrong function (${hit.function} instead of ` +
      `${expectedFunction}) - a localization gap, not a repair one`
    );
  }
  return `named ${hit.file}:${hit.function}, the defect is in ${expectedFile}:${expectedFunction}`;
}

/**
 * Grade a fix answer: the one fenced block replaces the defective file, the hidden test must pass.
 * @param {string} answer
 * @param {import("./cases.mjs").Case} item
 * @param {import("./sandbox.mjs").TestRunner} runTest
 * @param {(source: string) => {compiled: boolean, detail: string}} [compileCheck] the compile check; the container's by default
 * @returns {FixVerdict}
 */
export function scoreFix(answer, item, runTest, compileCheck = checkCompiles) {
  const block = extractPythonBlock(answer);
  if (block === null) {
    return {
      passed: false,
      reason: "the answer carries no single fenced ```python block",
      compiled: false,
      failedTests: [],
    };
  }
  const compile = compileCheck(block);
  if (!compile.compiled) {
    return {
      passed: false,
      reason: `the fenced block does not compile: ${compile.detail}`,
      compiled: false,
      failedTests: [],
    };
  }
  const patched = program(item);
  patched[item.bug.file] = block;
  const result = runTest(patched, item.hiddenTest.path, item.hiddenTest.content);
  if (!result.passed) {
    const failed = failedTests(result);
    return {
      passed: false,
      reason: `the hidden test still fails (${failed.join(", ") || "the test file broke"})`,
      compiled: true,
      failedTests: failed,
    };
  }
  return { passed: true, reason: "the hidden test passes", compiled: true, failedTests: [] };
}
