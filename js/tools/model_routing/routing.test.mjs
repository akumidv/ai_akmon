/**
 * node:test for `js/tools/model_routing/routing.mjs` — the places where a hook payload hands the
 * module a value the Python twin treats by truthiness. The full spec is
 * `meta/conformance/units/routing.toml`, run through `probe.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { posix } from "node:path";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { read } from "../../common/jsondata.mjs";
import { activeRole, detectOrchestrator, lastMainTurn, toolCommand } from "./routing.mjs";

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

test("the `$(akmon path)` sentinel names the installed package's carrier, `npx akmon tool` (C12, DV34)", () => {
  // The corpus folds `akmon tool` and `npx akmon tool` to one `{{tool}}`, so the spelling each twin
  // writes for the sentinel is pinned here and in `test_model_routing.py`, never by a scenario.
  const data = /** @type {any} */ (read(posix.join(embeddedTreeRoot(), "tools", "model_routing", "agents.json")));
  assert.equal(toolCommand(data, "$(akmon path)", "model_routing/gate_pack"), "npx akmon tool model_routing/gate_pack");
  assert.notEqual(toolCommand(data, "$(akmon path)", "x"), `akmon tool x`); // not the Python twin's spelling
  // Any other answer is a mounted tree, spelled the Python way — the sentinel is an exact match.
  assert.equal(
    toolCommand(data, "_aitna/akmon", "model_routing/init"),
    "python3 _aitna/akmon/tools/model_routing/init.py",
  );
  assert.equal(toolCommand(data, "$(akmon path) ", "x"), "python3 $(akmon path) /tools/x.py");
});
