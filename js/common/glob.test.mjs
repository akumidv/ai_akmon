/**
 * node:test for `js/common/glob.mjs` — every case of the shared units table
 * (`meta/conformance/units/glob.toml`) iterated on the host, the astral range repair (C115)
 * among them; the corpus runs the same table against the Python stdlib.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import { parse as parseToml } from "../vendor/smol-toml/dist/index.js";
import { fnmatchCase } from "./glob.mjs";

const _UNITS = new URL("../../meta/conformance/units/glob.toml", import.meta.url);

/** The table's cases. */
function _cases() {
  const parsed = /** @type {unknown} */ (parseToml(fs.readFileSync(_UNITS, "utf8")));
  return /** @type {{case: Array<{pattern: string, name: string, expected: boolean}>}} */ (parsed).case;
}

test("every case of the units table answers as fnmatch.fnmatchcase does", () => {
  const cases = _cases();
  assert.ok(cases.length > 0, "the units table carries cases");
  for (const [i, unitCase] of cases.entries()) {
    assert.equal(fnmatchCase(unitCase.name, unitCase.pattern), unitCase.expected, `case ${i}: ${unitCase.pattern}`);
  }
});

test("a range with an astral end is ordered and skipped by code point, never by UTF-16 unit (C115)", () => {
  // U+10000 is above U+FFFF by code point and below it by unit: the range is valid one way only.
  assert.equal(fnmatchCase("￿", "[-\u{1F600}]"), true);
  assert.equal(fnmatchCase("￿", "[\u{10000}-￿]"), false);
  assert.equal(fnmatchCase("b", "[!\u{10000}-￿]"), true);
  // After `a-😀` the next scan starts three code points on, so the second `-` is a member.
  assert.equal(fnmatchCase("-", "[a-\u{1F600}-z]"), true);
  assert.equal(fnmatchCase("z", "[a-\u{1F600}-z]"), true);
});

test("a negated class ending at U+10FFFE misses U+10FFFF: a V8 defect, DIVERGENCES.md DV37", () => {
  // `fnmatch` answers true (pinned in `test_check_runner.py`); the class is the same, V8's answer
  // is not, and `[^\u{10FFFD}]` behaves. A V8 that fixes the defect fails here: drop DV37 then.
  assert.equal(fnmatchCase("\u{10FFFF}", "[!-\u{10FFFE}]"), false);
  assert.equal(/^[^\u{10FFFE}]$/u.test("\u{10FFFF}"), false);
  assert.equal(/^[^\u{10FFFD}]$/u.test("\u{10FFFF}"), true);
});
