/**
 * node:test for `js/tools/model_routing/gate_pack.mjs` — the pack builders, the digest and the
 * arguments. The byte-level spec is the `tools/gate-pack-*` scenarios of `meta/conformance/scenarios`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildFullPack,
  buildPlanCheckPack,
  digest,
  main,
  planCheckQuestion,
  relativeTo,
  reportDir,
  reportPrefix,
  roleQuestion,
} from "./gate_pack.mjs";

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
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "gate-pack-test-"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "x");
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  return root;
}

test("the roles and the plan-check question come from gate.json", () => {
  assert.deepEqual(Object.keys(roleQuestion()).sort(), ["architect", "review"]);
  assert.match(planCheckQuestion(), /^Does the plan cover the stated goal/);
});

test("a full pack without extras carries the empty artifacts and coverage sentinels", () => {
  const pack = buildFullPack("g", "review", "goal", []);
  assert.match(pack, /^# Gate-pack — g\n\nrole: review\nkind: full\n/);
  assert.ok(pack.includes("## Artifacts\n\n_No artifacts supplied._\n\n## Coverage map\n\n_Coverage map not provided"));
  assert.ok(!pack.includes("## Decisions register"));
  assert.ok(pack.endsWith("diluted verdict.\n"));
});

test("a full pack renders every optional section in order", () => {
  const pack = buildFullPack("g", "architect", "goal", [["a.md", "text"]], {
    decisions: "D1",
    coverageMap: "map",
    depGraph: "a -> b",
  });
  const order = [
    "### a.md",
    "## Decisions register",
    "## Coverage map",
    "## Dependency-graph excerpt",
    "## What to return",
  ];
  let at = -1;
  for (const heading of order) {
    const next = pack.indexOf(heading);
    assert.ok(next > at, heading);
    at = next;
  }
});

test("an unknown role is refused", () => {
  assert.throws(() => buildFullPack("g", "nobody", "y", []), /unknown role 'nobody'; known roles: architect, review/);
  assert.throws(() => buildPlanCheckPack("g", "nobody", "y", "z"), /unknown role/);
});

test("a plan-check pack holds the yardstick and the zone plan, no coverage section", () => {
  const pack = buildPlanCheckPack("g", "review", "goal", "- a");
  assert.ok(pack.includes("kind: plan-check"));
  assert.ok(pack.includes("## Yardstick (goal)\n\ngoal\n\n## Zone plan\n\n- a\n\n## What to return"));
  assert.ok(!pack.includes("## Coverage map"));
});

test("the digest cuts at the limit on a character, not a code unit", () => {
  assert.equal(digest("  short  "), "short");
  assert.equal(digest("ab cd", 3), "ab\n...[truncated; see full pack]");
  assert.equal(digest("😀😀😀", 2), "😀😀\n...[truncated; see full pack]");
});

test("the default report directory and name prefix", () => {
  assert.equal(reportDir("/r"), "/r/_aitna/artifacts/gates");
  assert.equal(reportPrefix("a b/ü", "full"), "a-b-ü-full");
  assert.equal(reportPrefix("///", "full"), "gate-full");
  assert.equal(reportPrefix("design-align", "plan-check", "C7"), "C7-design-align-plan-check");
});

test("relativeTo keeps a path outside the root as written", () => {
  assert.equal(relativeTo("/r", "/r/a/b.md"), "a/b.md");
  assert.equal(relativeTo("/r", "x/./y.md"), "x/y.md");
  assert.equal(relativeTo("/r", "/other/y.md"), "/other/y.md");
});

test("main writes the pack and prints the summary", () => {
  const root = project({ "y.md": "goal\n", "a/f.md": "finding\n" });
  const result = run([
    "--project-root",
    root,
    "--gate",
    "g",
    "--role",
    "review",
    "--yardstick",
    path.join(root, "y.md"),
    "--artifact",
    path.join(root, "a/f.md"),
    "--out",
    path.join(root, "out/p.md"),
    "--stdout",
  ]);
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^gate-pack kind=full role=review\npack: out\/p\.md\n\n# Gate-pack — g\n/);
  const pack = fs.readFileSync(path.join(root, "out/p.md"), "utf8");
  assert.ok(pack.includes("### f.md\n\nfinding\n"));
  assert.ok(result.stdout.endsWith(`\n\n${pack}\n`));
});

test("usage errors are one line and exit 2", () => {
  assert.deepEqual(run(["--role", "review"]), {
    code: 2,
    stdout: "",
    stderr: "gate_pack.mjs: error: the following arguments are required: --gate, --yardstick\n",
  });
  assert.match(
    run(["--gate", "g", "--role", "x", "--yardstick", "y"]).stderr,
    /--role: invalid choice: 'x' \(choose from 'architect', 'review'\)/,
  );
  assert.match(
    run(["--gate", "g", "--role", "review", "--yardstick", "y", "--kind", "z"]).stderr,
    /--kind: invalid choice: 'z'/,
  );
  assert.equal(
    run(["--gate", "g", "--role", "review", "--yardstick", "y", "--kind", "plan-check"]).stderr,
    "gate_pack.mjs: error: --zone-plan is required for --kind plan-check\n",
  );
  assert.deepEqual(run(["--gate", "g", "--role", "review", "--yardstick", "/nonexistent/y.md", "--task", "///"]), {
    code: 2,
    stdout: "",
    stderr: "gate_pack.mjs: error: --task '///' has no usable characters (letters, digits, '_' or '-')\n",
  });
  assert.match(run(["--bogus"]).stderr, /^gate_pack\.mjs: error: Unknown option '--bogus'/);
});

test("-h prints the usage and exits 0", () => {
  const result = run(["-h"]);
  assert.equal(result.code, 0);
  assert.match(result.stdout, /^usage: gate_pack\.mjs/);
});
