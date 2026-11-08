// The one test that needs a running docker daemon: it skips itself when `docker version` fails.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

import { loadItemSet } from "./cases.mjs";
import { gateOk, runGate, sandboxRunner } from "./oracle.mjs";
import { checkCompiles } from "./sandbox.mjs";
import * as settings from "./settings.mjs";

const done = spawnSync("docker", ["version"], { encoding: "utf8", timeout: 60000 });
const SKIP = done.status === 0 ? false : "docker version failed: no usable daemon";

test("the seed item set survives the gold-sanity gate in a real container", { skip: SKIP }, () => {
  const itemSet = loadItemSet(join(settings.dataDir(), "items", "seed_cases.json"));

  const report = runGate(itemSet, sandboxRunner());

  assert.ok(
    gateOk(report),
    JSON.stringify(report.outcomes.filter((outcome) => !outcome.usable).map((outcome) => outcome.reason)),
  );
});

test("the compile check works in a real container", { skip: SKIP }, () => {
  assert.equal(checkCompiles("x = 1\n").compiled, true);
  assert.equal(checkCompiles("def broken(:\n").compiled, false);
});
