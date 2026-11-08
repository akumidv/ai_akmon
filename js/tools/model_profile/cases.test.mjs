import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { join } from "node:path";

import { ItemSetError, casesSha, envelopeSha, fixedProgram, loadItemSet, makeEnvelope, selectCases } from "./cases.mjs";
import * as settings from "./settings.mjs";
import { fixtureDocument, tempDir, writeItems } from "./support.test.mjs";

const SEED = join(settings.dataDir(), "items", "seed_cases.json");

/** The hashes of `fixtureDocument()` as the Python twin computes them — pinned in both test suites. */
const FIXTURE_CASES_SHA = "e6b39adb5ad5";
const FIXTURE_ENVELOPE_SHA = "be247f97a6c7";

test("the shipped seed set loads", () => {
  const itemSet = loadItemSet(SEED);

  assert.deepEqual(
    itemSet.cases.map((item) => item.id),
    ["invoice-coupon", "inventory-available"],
  );
  assert.deepEqual(itemSet.families, ["fix-symptom", "fix-traceback", "hunt"]);
  assert.equal(itemSet.casesSha.length, settings.load().hashLength);
  assert.equal(itemSet.envelopeSha.length, settings.load().hashLength);
  assert.equal(selectCases(itemSet, null, ["hunt"])[0].id, "inventory-available");
  const fixed = fixedProgram(itemSet.cases[0]);
  assert.equal(fixed["report.py"], itemSet.cases[0].files["report.py"]);
  assert.notEqual(fixed["invoice.py"], itemSet.cases[0].files["invoice.py"]);
});

test("the cases hash follows the content, not the filename", () => {
  const directory = tempDir();
  const document = JSON.parse(fs.readFileSync(SEED, "utf8"));
  const first = loadItemSet(writeItems(directory, document, "one.json"));
  const moved = loadItemSet(writeItems(directory, document, "two.json"));
  document.cases[0].files["helpers.py"] += "# edited\n";
  const edited = loadItemSet(writeItems(directory, document, "three.json"));

  assert.equal(first.casesSha, moved.casesSha);
  assert.notEqual(edited.casesSha, first.casesSha);
});

test("the envelope hash follows the knobs", () => {
  assert.notEqual(
    loadItemSet(SEED).envelopeSha,
    loadItemSet(SEED, makeEnvelope({ maxOutputTokens: 2048 })).envelopeSha,
  );
});

test("the hashes of a fixed document are pinned: the Python twin computes the same ones", () => {
  const itemSet = loadItemSet(writeItems(tempDir(), fixtureDocument()));

  assert.equal(itemSet.casesSha, FIXTURE_CASES_SHA);
  assert.equal(itemSet.envelopeSha, FIXTURE_ENVELOPE_SHA);
  assert.equal(casesSha(Buffer.from("x"), []).length, 12);
  assert.equal(envelopeSha(makeEnvelope(), ["b", "a", "a"]), envelopeSha(makeEnvelope(), ["a", "b"]));
});

/** @type {[string, (document: Record<string, any>) => void, RegExp][]} */
const MALFORMED = [
  ["no hidden test", (d) => delete d.cases[0].hidden_test, /missing hidden_test/],
  ["no oracle content", (d) => delete d.cases[0].hidden_test.content, /missing content/],
  ["oracle collides", (d) => (d.cases[0].hidden_test.path = "invoice.py"), /collides/],
  ["path escapes", (d) => (d.cases[0].hidden_test.path = "../escape.py"), /stay inside/],
  ["patch of an absent file", (d) => (d.cases[0].fixed_files["nope.py"] = "x = 1\n"), /does not carry/],
  ["bug in an absent file", (d) => (d.cases[0].bug.file = "nope.py"), /not one of the case's files/],
  ["missing ask", (d) => delete d.cases[0].asks["fix-symptom"], /no ask for fix-symptom/],
  ["unknown family", (d) => (d.cases[0].families = ["telepathy"]), /unknown family/],
  ["family twice", (d) => (d.cases[0].families = ["hunt", "hunt"]), /twice/],
  ["case id twice", (d) => d.cases.push(d.cases[0]), /case id twice/],
  ["no cases", (d) => (d.cases = []), /no cases/],
  ["no version", (d) => delete d.version, /version/],
];

for (const [name, mutate, message] of MALFORMED) {
  test(`a malformed item set throws and never half-loads: ${name}`, () => {
    const document = JSON.parse(fs.readFileSync(SEED, "utf8"));
    mutate(document);

    assert.throws(
      () => loadItemSet(writeItems(tempDir(), document)),
      (exc) => {
        assert.ok(exc instanceof ItemSetError);
        assert.match(exc.message, message);
        return true;
      },
    );
  });
}

test("an unreadable or non-JSON item set throws", () => {
  const directory = tempDir();
  assert.throws(() => loadItemSet(join(directory, "missing.json")), /cannot read/);
  const broken = join(directory, "broken.json");
  fs.writeFileSync(broken, "{nope");
  assert.throws(() => loadItemSet(broken), /not valid JSON/);
  const bom = join(directory, "bom.json");
  fs.writeFileSync(bom, Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from("{}")]));
  assert.throws(() => loadItemSet(bom), /not valid JSON/);
});

test("selectCases narrows by id and by family", () => {
  const itemSet = loadItemSet(writeItems(tempDir(), fixtureDocument()));

  assert.deepEqual(
    selectCases(itemSet, ["a-hunt"]).map((item) => item.id),
    ["a-hunt"],
  );
  assert.deepEqual(
    selectCases(itemSet, null, ["fix-symptom"]).map((item) => item.id),
    ["b-fix"],
  );
  assert.equal(selectCases(itemSet).length, 2);
});
