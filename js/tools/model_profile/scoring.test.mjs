import { test } from "node:test";
import assert from "node:assert/strict";

import { parseLocation, scoreFix, scoreHunt } from "./scoring.mjs";
import { FIXED_SOURCE, FIX_ANSWER, makeFixtureCase, neverRun } from "./support.test.mjs";

const EXPECTED = { expectedFile: "pkg/mod.py", expectedFunction: "compute" };

/** @type {[string, [boolean, boolean, boolean, boolean]][]} hit, file hit, function hit, malformed */
const HUNT_TABLE = [
  ["pkg/mod.py:compute", [true, true, true, false]],
  ["pkg/mod.py:other", [false, true, false, false]],
  ["other/mod.py:compute", [false, false, true, false]],
  ["pkg/mod.py", [false, false, false, true]],
  ["pkg/mod.py:compute\nexplains itself", [false, false, false, true]],
  ["I think it is pkg/mod.py:compute", [false, false, false, true]],
  ["", [false, false, false, true]],
];

for (const [answer, expected] of HUNT_TABLE) {
  test(`the hunt scorer decides a hit against the expected location: ${JSON.stringify(answer)}`, () => {
    const graded = scoreHunt(answer, EXPECTED);

    assert.deepEqual([graded.hit, graded.fileHit, graded.functionHit, graded.malformed], expected);
  });
}

test("parseLocation reads one line of the agreed form", () => {
  assert.deepEqual(parseLocation("pkg/mod.py:compute"), ["pkg/mod.py", "compute"]);
  assert.deepEqual(parseLocation("  pkg/mod.py:compute\n"), ["pkg/mod.py", "compute"]);
  assert.equal(parseLocation("pkg/mod.py"), null);
  assert.equal(parseLocation("pkg/mod.py:compute and more"), null);
  assert.equal(parseLocation(""), null);
});

/** A compile check that accepts anything; the container's interpreter is not reached from a unit test. */
const compilesAlways = () => ({ compiled: true, detail: "" });

test("the fix grader runs the hidden test on the one replaced file and leaves the others alone", () => {
  const item = makeFixtureCase("fixture-case", "fix-traceback");
  /** @type {Record<string, string>[]} */
  const seen = [];
  const recording = (/** @type {Record<string, string>} */ files) => {
    seen.push({ ...files });
    return { passed: true, tests: { test_compute: "passed" } };
  };

  const verdict = scoreFix(FIX_ANSWER, item, recording, compilesAlways);

  assert.ok(verdict.passed);
  assert.equal(seen.length, 1);
  assert.equal(seen[0]["pkg/mod.py"], FIXED_SOURCE);
  const others = Object.entries(seen[0]).filter(([path]) => path !== "pkg/mod.py");
  assert.deepEqual(
    others,
    Object.entries(item.files).filter(([path]) => path !== "pkg/mod.py"),
  );
});

/** @type {[string, string, boolean][]} answer, reason, whether the compile check is told the block compiles */
const UNUSABLE = [
  ["no code at all", "no single fenced", true],
  [`${FIX_ANSWER}${FIX_ANSWER}`, "no single fenced", true],
  ["```python\ndef broken(:\n```\n", "does not compile", false],
];

for (const [answer, reason, compiles] of UNUSABLE) {
  test(`a fix answer without a usable block is a wrong answer, not a deferral: ${reason}`, () => {
    const check = () => ({ compiled: compiles, detail: "invalid syntax (<unknown>, line 1)" });

    const verdict = scoreFix(answer, makeFixtureCase("fixture-case", "fix-traceback"), neverRun, check);

    assert.ok(!verdict.passed);
    assert.ok(verdict.reason.includes(reason), verdict.reason);
  });
}

test("a failing hidden test names the tests that failed", () => {
  const failing = () => ({ passed: false, tests: { test_a: "failed", test_b: "passed" } });

  const verdict = scoreFix(FIX_ANSWER, makeFixtureCase("c", "fix-symptom"), failing, compilesAlways);

  assert.equal(verdict.reason, "the hidden test still fails (test_a)");
  assert.deepEqual(verdict.failedTests, ["test_a"]);
  assert.ok(verdict.compiled);
});
