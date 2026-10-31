/**
 * node:test for the dev-root accessor of ADR 0022 D09 in `js/common/project_root.mjs`:
 * `<root>/.aitna-root` names the root, its absence means `_aitna`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { dirname, posix } from "node:path";
import { fileURLToPath } from "node:url";

import { aitnaRootName, devRoot, findProjectRoot, isProjectRoot } from "./project_root.mjs";

const REPO = posix.resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/**
 * @param {string | null} pointer
 * @returns {string}
 */
function project(pointer = null) {
  const root = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-dev-root-")));
  fs.writeFileSync(posix.join(root, "AGENTS.md"), "# A\n");
  if (pointer !== null) {
    fs.writeFileSync(posix.join(root, ".aitna-root"), pointer);
  }
  return root;
}

test("the pointer names the dev root", () => {
  const root = project("tools/ai\n");
  assert.deepEqual({ ...devRoot(root) }, { path: posix.join(root, "tools/ai"), origin: "pointer" });
  assert.equal(aitnaRootName(root), "tools/ai");
  assert.ok(Object.isFrozen(devRoot(root)));
});

test("an absent file means the default; no project root answers the default for reading", () => {
  const root = project();
  assert.deepEqual({ ...devRoot(root) }, { path: posix.join(root, "_aitna"), origin: "default" });
  assert.deepEqual({ ...devRoot(null) }, { path: "_aitna", origin: "no-project-root" });
});

for (const line of ["/abs/place", "../escaped", "a/../../escaped", "", "one\ntwo\n"]) {
  test(`a refused declaration raises naming the file: ${JSON.stringify(line)}`, () => {
    const root = project(line);
    assert.throws(
      () => devRoot(root),
      (error) => error instanceof Error && error.name === "ValueError" && /\.aitna-root/.test(error.message),
    );
  });
}

test("a symlink leaving the project is refused", () => {
  const root = project("leak");
  const outside = fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-dev-root-out-"));
  fs.symlinkSync(outside, posix.join(root, "leak"));
  assert.throws(() => devRoot(root), /resolves outside the project root/);
});

test("the declaration alone marks a project root", () => {
  assert.equal(isProjectRoot(project("meta\n")), true);
});

test("akmon's own repository resolves to meta; a consumer with its own meta/ does not", () => {
  assert.equal(aitnaRootName(REPO), "meta");
  assert.equal(findProjectRoot(posix.join(REPO, "common")), REPO);
  const consumer = project();
  fs.mkdirSync(posix.join(consumer, "meta"));
  assert.equal(aitnaRootName(consumer), "_aitna");
});
