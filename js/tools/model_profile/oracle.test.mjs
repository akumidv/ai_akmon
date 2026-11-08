import { test } from "node:test";
import assert from "node:assert/strict";

import { GateRefusalError, requireUsable, runGate, usableCaseIds } from "./oracle.mjs";
import { alwaysFails, makeFixtureCase, makeItemSet, separatingRunner } from "./support.test.mjs";

test("the gate refuses a case whose fixed program fails its hidden test", () => {
  const report = runGate(makeItemSet(makeFixtureCase("broken-gold")), alwaysFails);

  assert.deepEqual(usableCaseIds(report), []);
  assert.deepEqual(
    report.outcomes.map((outcome) => outcome.caseId),
    ["broken-gold"],
  );
  assert.match(report.outcomes[0].reason, /does not pass on the fixed program/);
  assert.throws(
    () => requireUsable(report),
    (exc) => exc instanceof GateRefusalError && /broken-gold/.test(exc.message),
  );
});

test("the gate accepts a case whose hidden test separates the two programs", () => {
  const report = runGate(makeItemSet(makeFixtureCase("good-gold")), separatingRunner);

  assert.deepEqual(usableCaseIds(report), ["good-gold"]);
  requireUsable(report);
});

test("the gate refuses a test that passes on the bug", () => {
  const passesEverywhere = () => ({ passed: true, tests: { test_compute: "passed" } });

  const report = runGate(makeItemSet(makeFixtureCase("weak-oracle")), passesEverywhere);

  assert.match(report.outcomes[0].reason, /passes on the buggy program/);
  assert.ok(!report.outcomes[0].usable);
});

test("the gate runs over the selection only", () => {
  const items = makeItemSet(makeFixtureCase("a", "hunt"), makeFixtureCase("b", "fix-symptom"));

  assert.deepEqual(usableCaseIds(runGate(items, separatingRunner, { caseIds: ["b"] })), ["b"]);
  assert.deepEqual(usableCaseIds(runGate(items, separatingRunner, { families: ["hunt"] })), ["a"]);
});
