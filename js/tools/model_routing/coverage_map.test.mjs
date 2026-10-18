/**
 * node:test for `js/tools/model_routing/coverage_map.mjs` — the zone-plan parser, the map
 * builder, the ISO bounds and the arguments. The byte-level spec is the `tools/coverage-map-*`
 * scenarios of `meta/conformance/scenarios`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildCoverageMap,
  describeScope,
  inScope,
  main,
  parseBound,
  parseInstant,
  parseZonePlan,
  unlabelledMarker,
} from "./coverage_map.mjs";
import { DelegationEntry } from "./routing.mjs";

/**
 * Run `main` with the process streams captured.
 * @param {string[]} argv
 * @returns {{code: number, stdout: string, stderr: string}}
 */
function run(argv) {
  let stdout = "";
  let stderr = "";
  const out = process.stdout.write;
  const err = process.stderr.write;
  process.stdout.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stdout += text), true)
  );
  process.stderr.write = /** @type {any} */ (
    (/** @type {string} */ text) =>
      ((stderr += text), true)
  );
  try {
    return { code: main(argv), stdout, stderr };
  } finally {
    process.stdout.write = out;
    process.stderr.write = err;
  }
}

/**
 * A scratch project root holding `files`.
 * @param {Record<string, string>} files
 * @returns {string}
 */
function project(files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "coverage-map-test-"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "x");
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  return root;
}

/**
 * @param {string | null} zone
 * @param {string} [subagent]
 * @param {string | null} [model]
 * @param {string} [timestamp]
 * @param {string | null} [session]
 * @returns {DelegationEntry}
 */
function entry(zone, subagent = "k_explorer", model = null, timestamp = "2026-05-01T10:00:00", session = "s1") {
  return new DelegationEntry(timestamp, session, subagent, model, zone, "d");
}

test("the zone plan drops blanks and comments, strips bullets, collapses duplicates", () => {
  assert.deepEqual(parseZonePlan("- auth\n* api\n\n# note\n  billing  \nauth\n-x\n- \n"), [
    "auth",
    "api",
    "billing",
    "-x",
    "-",
  ]);
});

test("no entries is the empty sentinel, with or without a plan", () => {
  assert.equal(buildCoverageMap([]), "_No delegations in scope._");
  assert.equal(buildCoverageMap([], ["a"]), "_No delegations in scope._");
});

test("zones group in first-seen order with distinct workers and a count", () => {
  const map = buildCoverageMap([entry("a", "w", "m"), entry("b"), entry("a", "w", "m"), entry("a", "x")]);
  assert.equal(
    map,
    "| zone | workers | count |\n|------|---------|-------|\n| a | w/m, x | 3 |\n| b | k_explorer | 1 |",
  );
});

test("a plan surfaces uncovered, off-plan and unlabelled zones", () => {
  const map = buildCoverageMap([entry("a"), entry("z"), entry(null)], ["a", "b"]);
  assert.ok(map.includes(`| ${unlabelledMarker()} | k_explorer | 1 |`));
  assert.ok(map.includes("### Uncovered zones (planned, no worker)\n- b"));
  assert.ok(map.includes("### Off-plan zones (worked, not in the zone plan)\n- z"));
  assert.ok(map.endsWith("_1 delegation(s) carried no `[zone:…]` marker — unattributable._"));
  assert.ok(buildCoverageMap([entry("a")], ["a"]).endsWith("_All planned zones have at least one worker._"));
});

test("bounds: a bare date is the whole day, an offset is honoured, fractions truncate to microseconds", () => {
  assert.equal(parseInstant("2026-05-01T10:00:00Z"), 1777629600000000n);
  assert.equal(parseInstant("2026-05-01T12:00:00+02:00"), 1777629600000000n);
  assert.equal(parseInstant("2026-05-01 10:00:00.1234567Z"), 1777629600123456n);
  assert.equal(parseInstant("2026-05-01T10Z"), 1777629600000000n);
  assert.equal(parseBound(" 2026-05-01 ", true) - parseBound("2026-05-01", false), 86399999999n);
});

test("bounds: what is not ISO raises, with Python's wording", () => {
  assert.throws(() => parseInstant("yesterday"), /Invalid isoformat string: 'yesterday'/);
  assert.throws(() => parseInstant("2026-13-01"), /month must be in 1\.\.12/);
  assert.throws(() => parseInstant("2026-02-30"), /day is out of range for month/);
  assert.throws(() => parseInstant("2026-05-01T24:00:00"), /hour must be in 0\.\.23/);
  assert.throws(() => parseInstant("2026-05-01T10:00:00+24:00"), /strictly between/);
  assert.throws(() => parseInstant("20260501"), /Invalid isoformat string/);
});

test("scope: session and time bounds compose; an unplaceable row raises under a time bound only", () => {
  const e = entry("a", "k", null, "2026-05-01T10:00:00Z", "s1");
  const lo = parseInstant("2026-05-01T09:00:00Z");
  const hi = parseInstant("2026-05-01T11:00:00Z");
  assert.equal(inScope(e, "s2", null, null), false);
  assert.equal(inScope(e, "s1", lo, hi), true);
  assert.equal(inScope(e, null, hi, null), false);
  assert.equal(inScope(e, null, null, lo), false);
  const bad = entry("a", "k", null, "garbage");
  assert.equal(inScope(bad, null, null, null), true);
  assert.throws(() => inScope(bad, null, lo, null), /Invalid isoformat string: 'garbage'/);
});

test("the scope line names the session set", () => {
  assert.equal(describeScope("s1", []), "session s1");
  assert.equal(describeScope(null, []), "all sessions (none in scope)");
  assert.equal(
    describeScope(null, [entry("a", "k", null, "t", "b"), entry("a", "k", null, "t", null), entry("a")]),
    "all sessions (3: -, b, s1)",
  );
});

test("main assembles a scoped map and reports it", () => {
  const log = "2026-05-01T10:00:00\ts1\tk_explorer\thaiku\tauth\tx\n2026-05-01T11:00:00\ts2\tk_mechanic\t-\tapi\ty\n";
  const root = project({ ".claude/model-routing.log": log });
  const result = run(["--project-root", root, "--session", "s1", "--out", path.join(root, "m.md"), "--stdout"]);
  assert.equal(result.code, 0);
  assert.equal(
    result.stdout,
    "coverage-map entries=1 zones=1\nscope: session s1\nmap: m.md\n\n| zone | workers | count |\n|------|---------|-------|\n| auth | k_explorer/haiku | 1 |\n",
  );
  assert.equal(
    fs.readFileSync(path.join(root, "m.md"), "utf8"),
    "| zone | workers | count |\n|------|---------|-------|\n| auth | k_explorer/haiku | 1 |\n",
  );
});

test("main refuses a bad bound, a missing log and an unplaceable row", () => {
  const root = project({ ".claude/model-routing.log": "garbage\ts1\tk\t-\tz\td\n" });
  const base = ["--project-root", root, "--all-sessions"];
  assert.equal(
    run([...base, "--since", "soon"]).stderr,
    "coverage_map.mjs: error: --since 'soon' is not an ISO date or date-time\n",
  );
  assert.match(
    run([...base, "--since", "2026-05-01"]).stderr,
    /a delegation-log row cannot be placed inside --since\/--until \(Invalid isoformat string: 'garbage'\); no map written\n$/,
  );
  const missing = run([...base, "--log", "nope.log"]);
  assert.equal(missing.code, 2);
  assert.equal(missing.stderr, "coverage_map.mjs: error: delegation log not found: nope.log\n");
});

test("scope flags: one is required and the two exclude each other", () => {
  assert.equal(run([]).stderr, "coverage_map.mjs: error: one of the arguments --session --all-sessions is required\n");
  assert.equal(
    run(["--session", "a", "--all-sessions"]).stderr,
    "coverage_map.mjs: error: argument --all-sessions: not allowed with argument --session\n",
  );
  assert.equal(
    run(["--all-sessions", "--session", "a"]).stderr,
    "coverage_map.mjs: error: argument --session: not allowed with argument --all-sessions\n",
  );
});

test("-h prints the usage and exits 0", () => {
  const result = run(["-h"]);
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^usage: coverage_map\.mjs/);
});
