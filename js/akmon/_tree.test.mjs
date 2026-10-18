/**
 * node:test for `js/akmon/_tree.mjs` — the tree the running module belongs to, links dereferenced.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { embeddedTreeRoot } from "./_tree.mjs";

const HERE = posix.dirname(fileURLToPath(import.meta.url));
const TREE = fs.realpathSync(posix.resolve(HERE, "..", ".."));

test("the embedded tree is two levels above js/akmon, and holds the package.json and the shared data", () => {
  assert.equal(embeddedTreeRoot(), TREE);
  assert.ok(fs.existsSync(posix.join(embeddedTreeRoot(), "package.json")));
  assert.ok(fs.existsSync(posix.join(embeddedTreeRoot(), "src", "akmon", "init.json")));
});

test("loaded through a link (a manager's node_modules/akmon) it still answers the real tree", () => {
  const dir = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-tree-")));
  fs.mkdirSync(posix.join(dir, "node_modules"));
  fs.symlinkSync(TREE, posix.join(dir, "node_modules", "akmon"));
  const script = posix.join(dir, "probe.mjs");
  fs.writeFileSync(
    script,
    `import { embeddedTreeRoot } from ${JSON.stringify(posix.join(dir, "node_modules", "akmon", "js", "akmon", "_tree.mjs"))};\nprocess.stdout.write(embeddedTreeRoot());\n`,
  );
  const result = spawnSync(process.execPath, [script], { encoding: "utf8", cwd: os.tmpdir() });
  assert.deepEqual(
    { status: result.status, stdout: result.stdout, stderr: result.stderr },
    { status: 0, stdout: TREE, stderr: "" },
  );
  fs.rmSync(dir, { recursive: true, force: true });
});
