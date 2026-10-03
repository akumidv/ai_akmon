/**
 * node:test for `js/akmon/cli.mjs` — the `bin` stub run as an entry point and imported as a
 * module. Both sides run in a child process because the entry-point guard only happens while
 * the module loads: importing it from this file would settle the question before an assertion
 * could be made about it.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { NOT_PORTED } from "./cli.mjs";

const cliModule = new URL("./cli.mjs", import.meta.url);

function tmpdir() {
  return fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-cli-"));
}

test("run through the symlink npm installs for a bin entry, the stub still reports", () => {
  // npm does not copy the `bin` target into `node_modules/.bin/`, it links it, so the path
  // node was given and the path the module was loaded from differ by one hop.
  const dir = tmpdir();
  const linkPath = posix.join(dir, "akmon");
  fs.symlinkSync(fileURLToPath(cliModule), linkPath);
  const result = spawnSync(process.execPath, [linkPath], { encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.equal(result.stderr, `${NOT_PORTED}\n`);
  assert.equal(result.stdout, "");
  fs.rmSync(dir, { recursive: true, force: true });
});

test("run by its own path, the stub reports the same way", () => {
  const result = spawnSync(process.execPath, [fileURLToPath(cliModule)], { encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.equal(result.stderr, `${NOT_PORTED}\n`);
});

test("imported rather than run, the stub writes nothing and leaves the exit code alone", () => {
  const dir = tmpdir();
  const importer = posix.join(dir, "importer.mjs");
  fs.writeFileSync(importer, `await import("${cliModule.href}");\nprocess.stdout.write("imported\\n");\n`);
  const result = spawnSync(process.execPath, [importer], { encoding: "utf8" });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, "");
  assert.equal(result.stdout, "imported\n");
  fs.rmSync(dir, { recursive: true, force: true });
});
