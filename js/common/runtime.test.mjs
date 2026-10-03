/**
 * node:test for `js/common/runtime.mjs` — the harness-command map and the runtime
 * declarations, data-driven against `common/runtime.json` (the twin reads the same table the
 * Python twin reads, so both stay on one owner).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import {
  GENERATED_WIRING, OPTIONAL, OWN_TOOLING, REQUIRED_ON,
  codexHooksListCommand, declaredRuntimes, harnessBinaries, harnessCommand, versionCommand } from "./runtime.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../../common/runtime.json", import.meta.url), "utf-8"));

test("the declared runtimes come from the shared data file, ordered", () => {
  const runtimes = declaredRuntimes(data);
  assert.equal(runtimes.length, 5);
  assert.deepEqual(runtimes[0], { binary: "POSIX shell", population: GENERATED_WIRING, modality: "required" });
  assert.deepEqual(runtimes[2], { binary: "git", population: GENERATED_WIRING, modality: REQUIRED_ON + "codex" });
  assert.ok(runtimes[3].modality, OPTIONAL);
  assert.equal(runtimes[4].population, OWN_TOOLING);
});

test("the harness binaries are the executables the table names, sorted", () => {
  assert.deepEqual(harnessBinaries(data), ["claude", "codex"]);
});

test("a harness command is its executable plus the table's operation prefix", () => {
  assert.deepEqual(harnessCommand(data, "codex", "hooks-list"), ["codex", "app-server"]);
  assert.deepEqual(codexHooksListCommand(data), ["codex", "app-server"]);
  assert.deepEqual(versionCommand(data, "claude"), ["claude", "--version"]);
  assert.deepEqual(harnessCommand(data, "codex", "review"), ["codex", "exec"]);
});

test("a caller-supplied policy tail appends after the table's prefix", () => {
  assert.deepEqual(harnessCommand(data, "codex", "review", "--model", "x"), ["codex", "exec", "--model", "x"]);
});

test("an unknown harness and an unknown operation both name what is known", () => {
  assert.throws(() => harnessCommand(data, "gemini", "version"), /unknown harness 'gemini'; known: claude, codex/);
  assert.throws(
    () => harnessCommand(data, "claude", "hooks-list"),
    /harness 'claude' declares no operation 'hooks-list'; known: review, version/,
  );
});
