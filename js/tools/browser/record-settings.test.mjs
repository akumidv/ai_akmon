import { test } from "node:test";
import assert from "node:assert/strict";

import { DEFAULT_RECORD_SETTINGS, readRecordSettings } from "./record-settings.mjs";
import { BrowserError, projectAt, readSettings } from "./settings.mjs";
import { DEFAULT_REDACT } from "./redact.mjs";
import { tempProject } from "./support.test.mjs";

/**
 * @param {string} record the text of the project's record
 * @returns {{project: import("./settings.mjs").Project, dispose: () => void}}
 */
function projectWith(record) {
  const { root, dispose } = tempProject(record);
  return { project: projectAt(root, {}), dispose };
}

test("without a [browser.record] table the defaults hold: no bodies, 64 KiB, the one page", () => {
  const { project, dispose } = projectWith("[browser]\nport = 9400\n");
  try {
    assert.deepEqual(readRecordSettings(project), DEFAULT_RECORD_SETTINGS);
    assert.deepEqual(DEFAULT_RECORD_SETTINGS, { bodies: false, maxBody: 65_536, allPages: false });
  } finally {
    dispose();
  }
});

test("[browser.record] sets what a recording keeps by default", () => {
  const { project, dispose } = projectWith("[browser.record]\nbodies = true\nmax_body = 4096\nall_pages = true\n");
  try {
    assert.deepEqual(readRecordSettings(project), { bodies: true, maxBody: 4096, allPages: true });
  } finally {
    dispose();
  }
});

test("a value of the wrong kind, and a key that is not a setting, are refused in one line", () => {
  for (const [text, pattern] of /** @type {[string, RegExp][]} */ ([
    ['[browser.record]\nbodies = "yes"\n', /bodies must be true or false/],
    ["[browser.record]\nmax_body = 0\n", /max_body must be a positive whole number/],
    ["[browser.record]\nmax_body = 1.5\n", /max_body must be a positive whole number/],
    ["[browser.record]\nall_pages = 1\n", /all_pages must be true or false/],
    ["[browser.record]\nredact = []\n", /redact is not a setting/],
    ["[browser]\nrecord = 3\n", /must be a table/],
  ])) {
    const { project, dispose } = projectWith(text);
    try {
      assert.throws(
        () => readRecordSettings(project),
        (error) => error instanceof BrowserError && pattern.test(error.message),
      );
    } finally {
      dispose();
    }
  }
});

test("[browser.record] cannot lower the redaction floor: the keys a capture redacts are still the defaults plus [browser] redact", () => {
  const { project, dispose } = projectWith('[browser]\nredact = ["ssn"]\n[browser.record]\nbodies = true\n');
  try {
    const keys = readSettings(project, {}).redact;
    for (const key of DEFAULT_REDACT) {
      assert.ok(keys.includes(key), key);
    }
    assert.ok(keys.includes("ssn"));
  } finally {
    dispose();
  }
});
