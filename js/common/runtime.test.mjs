/**
 * node:test for `js/common/runtime.mjs` — the harness-command map and the runtime
 * declarations, data-driven against `common/runtime.json` (the twin reads the same table the
 * Python twin reads, so both stay on one owner).
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import {
  GENERATED_WIRING,
  OPTIONAL,
  OWN_TOOLING,
  REQUIRED_ON,
  codexHooksListCommand,
  declaredRuntimes,
  harnessBinaries,
  harnessCommand,
  versionCommand,
} from "./runtime.mjs";

const data = JSON.parse(fs.readFileSync(new URL("../../common/runtime.json", import.meta.url), "utf-8"));

test("the declared runtimes come from the shared data file, ordered", () => {
  const runtimes = declaredRuntimes(data, "python");
  assert.equal(runtimes.length, 8);
  assert.equal(runtimes[1].binary, "python3");
  assert.deepEqual(runtimes[0], { binary: "POSIX shell", population: GENERATED_WIRING, modality: "required" });
  assert.deepEqual(runtimes[2], { binary: "git", population: GENERATED_WIRING, modality: REQUIRED_ON + "codex" });
  assert.ok(runtimes[3].modality, OPTIONAL);
  assert.equal(runtimes[4].population, OWN_TOOLING);
  // The unmeasured carriers of ADR 0024/D09, D15 are optional own tooling too.
  assert.deepEqual(
    runtimes.slice(5).map((r) => [r.binary, r.population, r.modality]),
    ["qwen", "opencode", "pi"].map((binary) => [binary, OWN_TOOLING, OPTIONAL]),
  );
});

test("the node ecosystem declares node where python declares python3", () => {
  const runtimes = declaredRuntimes(data, "node");
  assert.deepEqual(
    runtimes.map((r) => r.binary),
    ["POSIX shell", "node", "git", "claude", "codex", "qwen", "opencode", "pi"],
  );
  assert.deepEqual(runtimes[1], { binary: "node", population: GENERATED_WIRING, modality: "required" });
});

test("an unknown ecosystem raises a ValueError naming it", () => {
  assert.throws(
    () => declaredRuntimes(data, "ruby"),
    (/** @type {Error} */ error) =>
      error.name === "ValueError" && error.message === "unknown ecosystem 'ruby'; known: node, python",
  );
  assert.throws(() => declaredRuntimes(data, "toString"), /unknown ecosystem 'toString'/);
});

test("the harness binaries are the executables the table names, sorted", () => {
  assert.deepEqual(harnessBinaries(data), ["claude", "codex", "opencode", "pi", "qwen"]);
});

test("a harness command is its executable plus the table's operation prefix", () => {
  assert.deepEqual(harnessCommand(data, "codex", "hooks-list"), ["codex", "app-server"]);
  assert.deepEqual(codexHooksListCommand(data), ["codex", "app-server"]);
  assert.deepEqual(versionCommand(data, "claude"), ["claude", "--version"]);
  assert.deepEqual(harnessCommand(data, "codex", "review"), ["codex", "exec"]);
});

test("the carriers of ADR 0024 reach a review through their own prefix", () => {
  assert.deepEqual(harnessCommand(data, "qwen", "review"), [
    "qwen",
    "--approval-mode",
    "default",
    "--exclude-tools",
    "write_file,edit,run_shell_command",
    "--max-wall-time",
    "140s",
  ]);
  assert.deepEqual(harnessCommand(data, "opencode", "review"), ["opencode", "run", "--agent", "plan"]);
  assert.deepEqual(harnessCommand(data, "pi", "review"), [
    "pi",
    "-p",
    "--no-session",
    "--tools",
    "read,grep,find,ls",
    "--no-extensions",
    "--no-mcp",
  ]);
  assert.deepEqual(versionCommand(data, "pi"), ["pi", "--version"]);
});

test("a caller-supplied policy tail appends after the table's prefix", () => {
  assert.deepEqual(harnessCommand(data, "codex", "review", "--model", "x"), ["codex", "exec", "--model", "x"]);
});

test("an unknown harness and an unknown operation both name what is known", () => {
  assert.throws(
    () => harnessCommand(data, "gemini", "version"),
    /unknown harness 'gemini'; known: claude, codex, opencode, pi, qwen/,
  );
  assert.throws(
    () => harnessCommand(data, "claude", "hooks-list"),
    /harness 'claude' declares no operation 'hooks-list'; known: review, version/,
  );
});
