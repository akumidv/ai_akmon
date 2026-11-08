// The tests that run a real container: the local full suite's, skipped with the cause when docker
// cannot be used (no client, no permission on the socket, no daemon) and always in CI, which has
// no docker daemon by design.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

import { loadItemSet } from "./cases.mjs";
import { gateOk, runGate, sandboxRunner } from "./oracle.mjs";
import { checkCompiles } from "./sandbox.mjs";
import * as settings from "./settings.mjs";

/**
 * Why a real container cannot be run here, or false when one can.
 * @returns {string | false}
 */
function dockerUnavailableReason() {
  if (process.env.CI) {
    return "CI has no docker daemon by design; run the full suite locally";
  }
  const done = spawnSync("docker", ["version"], { encoding: "utf8", timeout: 60000 });
  if (done.error) {
    return "docker is not on the PATH (install the docker client)";
  }
  if (done.status === 0) {
    return false;
  }
  if (/permission denied/i.test(done.stderr)) {
    return "this user may not reach the docker socket (add the user to group docker, then log in again)";
  }
  return "docker version failed: no daemon is answering";
}

const SKIP = dockerUnavailableReason();

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
