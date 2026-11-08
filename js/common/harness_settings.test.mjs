/**
 * node:test for `js/common/harness_settings.mjs` — the twin of the edit-route half of
 * `meta/tests/test_harness_settings.py` (ADR 0031/D07, D-C203-ACTOR-WRITE). The decisions are the shared table
 * `meta/conformance/units/harness_settings_cases.json`, which the Python suite runs too.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import { editReason, fileFormat, writeReason } from "./harness_settings.mjs";
import { TREE_ROOT } from "../hooks/hook_data.mjs";

const CASES = JSON.parse(
  fs.readFileSync(posix.join(TREE_ROOT, "meta", "conformance", "units", "harness_settings_cases.json"), "utf8"),
);
const DATA = JSON.parse(fs.readFileSync(posix.join(TREE_ROOT, "common", "harness_settings.json"), "utf8"));

test("the edit route decides as the shared table says", () => {
  for (const item of CASES.edit) {
    const reason = editReason(item.tool_input, () => item.current, DATA);
    if (item.decision === "pass") {
      assert.equal(reason, null, item.name);
      continue;
    }
    assert.notEqual(reason, null, item.name);
    assert.ok(String(reason).includes(item.file), item.name);
    assert.ok(String(reason).includes("harness settings file"), item.name);
    assert.ok(String(reason).includes("AKMON_ACTOR"), item.name);
  }
});

test("the edit route reads the file only for a settings file", () => {
  const reader = (/** @type {string} */ path) => {
    throw new Error(`read ${path}`);
  };
  assert.equal(editReason({ file_path: "/p/src/x.py", content: "x" }, reader, DATA), null);
});

test("a settings file is named by its last two segments", () => {
  /** @type {Array<[string, string | null]>} */
  const cells = [
    ["/p/.claude/settings.json", "json"],
    ["/p/.claude/settings.local.json", "json"],
    ["/p/.claude/settingsX.json", "json"],
    ["/p/.claude/settings.jsonl", null],
    ["/p/.codex/config.toml", "toml"],
    ["~/.codex/config.toml", "toml"],
    ["/p/.codex/config.toml.bak", null],
    ["/p/.claude/settings", null],
    ["settings.json", null],
    ["", null],
    ["/", null],
  ];
  for (const [path, expected] of cells) {
    assert.equal(fileFormat(path, DATA), expected, path);
  }
});

test("the shipped data lists the files and the texts", () => {
  assert.deepEqual(
    DATA.files.map((/** @type {any} */ entry) => [entry.directory, entry.pattern, entry.format]),
    [
      [".claude", "settings*.json", "json"],
      [".codex", "config.toml", "toml"],
    ],
  );
  assert.deepEqual(DATA.toml_env_names, ["env", "shell_environment_policy"]);
  assert.deepEqual(Object.keys(DATA.texts).sort(), ["bash", "edit"]);
  assert.equal(writeReason("x/.claude/settings.json", DATA).split("x/.claude/settings.json").length, 2);
});
