/**
 * node:test for `js/tools/model_routing/routing.mjs` — the places where a hook payload hands the
 * module a value the Python twin treats by truthiness. The full spec is
 * `meta/conformance/units/routing.toml`, run through `probe.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { activeRole, detectOrchestrator, lastMainTurn } from "./routing.mjs";

test("a falsy transcript_path of any JSON type is no transcript (Python: `if not transcript_path`)", () => {
  for (const empty of [null, undefined, "", 0, false, [], {}]) {
    assert.equal(activeRole(/** @type {any} */ (empty)), null);
    assert.deepEqual(lastMainTurn(/** @type {any} */ (empty)), [null, null]);
    assert.equal(detectOrchestrator(/** @type {any} */ (empty), ["opus"]), null);
  }
});

test("a truthy transcript_path that is not a string is the TypeError Path() raises", () => {
  for (const bad of [5, true, ["x"], { a: 1 }]) {
    assert.throws(() => activeRole(/** @type {any} */ (bad)), { name: "TypeError" });
    assert.throws(() => lastMainTurn(/** @type {any} */ (bad)), { name: "TypeError" });
  }
});
