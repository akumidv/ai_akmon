import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { join } from "node:path";

import * as settings from "./settings.mjs";

test("the settings are the data file's, typed", () => {
  const loaded = settings.load();

  assert.equal(loaded.hashLength, 12);
  assert.deepEqual(loaded.families.known, ["hunt", "fix-traceback", "fix-symptom"]);
  assert.equal(loaded.sandbox.image, "python:3.13-slim");
  assert.deepEqual(loaded.sandbox.dockerFailureCodes, [125, 126, 127]);
  assert.equal(loaded.itemBand.minScored, 3);
  assert.equal(loaded.gates.length, 5);
  assert.equal(settings.load(), loaded, "the file is read once");
});

test("every key of the data file is read: nothing in it is dead", () => {
  const document = JSON.parse(fs.readFileSync(join(settings.dataDir(), settings.PROFILE_FILE), "utf8"));
  const snake = (/** @type {string} */ key) => key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
  const loaded = /** @type {Record<string, any>} */ (/** @type {unknown} */ (settings.load()));
  for (const [section, value] of Object.entries(document)) {
    assert.ok(snake(section) in loaded, section);
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      for (const key of Object.keys(value)) {
        assert.ok(snake(key) in loaded[snake(section)], `${section}.${key}`);
      }
    }
  }
});

test("the in-container runner's source is the shared program", () => {
  const source = settings.runnerSource();

  assert.match(source, /def main\(\) -> int:/);
  assert.match(source, /raise SystemExit\(main\(\)\)/);
  assert.equal(source, fs.readFileSync(join(settings.dataDir(), "container_runner.py.txt"), "utf8"));
});
