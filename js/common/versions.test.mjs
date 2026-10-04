/**
 * node:test for `js/common/versions.mjs` — the npm carrier's spelling, which is the one part of
 * this module the shared units table cannot pin whole.
 *
 * `meta/conformance/units/versions.toml` drives the carriable spellings (its `[[semver]]` block,
 * read here from the same file `probe.mjs` answers), and the ordering rows of that table are the
 * corpus's job, not this file's. What the table cannot say is a *refusal*: both probes call
 * `semverSpelling` bare, so a row for a refused shape would crash the mouth instead of failing it
 * (the table's pair block has an "error" spelling for a raise; the semver block has none). The
 * ban therefore lives here on the JS side, beside the Python carrier of the same contract in
 * `meta/tests/test_release_check.py`, over the same inputs.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import { parse as parseToml } from "../vendor/smol-toml/dist/index.js";
import { semverSpelling } from "./versions.mjs";

const _UNITS = new URL("../../meta/conformance/units/versions.toml", import.meta.url);

/**
 * @returns {{semver: Array<{input: string, expected: string}>}}
 */
function _units() {
  // The cast only admits the read; the shape is asserted case by case. The unknown bridge
  // is needed because the parser's own return type is the generic table.
  const parsed = /** @type {unknown} */ (parseToml(fs.readFileSync(_UNITS, "utf8")));
  return /** @type {{semver: Array<{input: string, expected: string}>}} */ (parsed);
}

/**
 * Every spelling the carrier refuses (owner decision 2026-10-03). The three pre-release steps are
 * in here because SemVer §11 orders the identifiers the derivation would form —
 * `alpha < beta < dev < rc` — against PEP 440's `dev < a < b < rc`: the derived npm side would
 * claim an order its PEP 440 side denies, so it is refused rather than guessed.
 */
const _UNCARRIABLE = [
  "1.2.3.post1",
  "1.2.3+local.1",
  "1.2.3a1",
  "1.2.3b2",
  "1.2.3rc1",
  "1.2.3a1.dev0",
  "1.2.3rc1.dev4",
  "v1.2.3-3-g1234abcd",
  // Arabic-Indic digits: a Python `\d` once matched them, a JavaScript `\d` never did.
  "١.٢.٣",
  "1.2.3.dev٣",
];

test("every semver case of the units table spells as pinned, and only the carriable ones are there", () => {
  const units = _units();
  assert.ok(units.semver.length > 0, "the units table carries semver cases");
  for (const [i, unitCase] of units.semver.entries()) {
    assert.equal(semverSpelling(unitCase.input), unitCase.expected, `semver ${i}: ${unitCase.input}`);
  }
  // The block is the carriable set: a refused shape added to it would crash probe.mjs rather
  // than fail it, so its absence here is part of what this test guards.
  for (const refused of _UNCARRIABLE) {
    assert.equal(
      units.semver.some((unitCase) => unitCase.input === refused),
      false,
      `${refused} is refused and has no place in the table's [[semver]] block`,
    );
  }
});

test("the npm carrier refuses every shape that would invert the pre-release order", () => {
  for (const refused of _UNCARRIABLE) {
    assert.throws(
      () => semverSpelling(refused),
      /npm-carriable|distance past its tag/,
      `${refused} must raise, not return a near miss`,
    );
  }
});

test("the npm carrier spells a final release and its own development version", () => {
  // The two carriable shapes, named beside the ban so the pair of them reads as one contract.
  assert.equal(semverSpelling("1.2.3"), "1.2.3");
  assert.equal(semverSpelling("v1.2.3"), "1.2.3");
  assert.equal(semverSpelling("1.2.3.dev0"), "1.2.3-dev.0");
});
