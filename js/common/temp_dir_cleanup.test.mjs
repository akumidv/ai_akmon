import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";
import { tempDir } from "./temp_dir.test.mjs";

test("tempDir makes a fresh real folder with the prefix", () => {
  const first = tempDir("akmon-temp-dir-");
  const second = tempDir("akmon-temp-dir-");
  assert.notEqual(first, second);
  assert.ok(fs.statSync(first).isDirectory());
  assert.equal(fs.realpathSync(first), first);
  assert.ok(path.basename(first).startsWith("akmon-temp-dir-"));
});

test("tempDir's folders are gone when the process exits, files inside included", () => {
  // The child imports the helper module only: it carries no test, so nothing recurses.
  const helper = new URL("./temp_dir.test.mjs", import.meta.url).href;
  const script =
    `const { tempDir } = await import(${JSON.stringify(helper)});` +
    `const fs = await import("node:fs");` +
    `const dir = tempDir("akmon-temp-dir-child-");` +
    `fs.writeFileSync(dir + "/file.txt", "x");` +
    `fs.mkdirSync(dir + "/nested");` +
    `process.stdout.write(dir);`;
  const run = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
    encoding: "utf8",
    timeout: 30_000,
  });
  assert.equal(run.status, 0, run.stderr);
  const dir = run.stdout.trim();
  assert.ok(dir.length > 0, "the child printed no folder");
  assert.equal(fs.existsSync(dir), false, `${dir} survived the process`);
});
