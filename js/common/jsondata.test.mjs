/**
 * node:test for `js/common/jsondata.mjs` — the loud failure that names the file and the
 * `{{name}}` fill the Python twin pins: single braces stay literal, an unfilled
 * placeholder raises naming the key, and values are inserted verbatim.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import { read, fill, DataFileError } from "./jsondata.mjs";

function tmpdir() {
  return fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-jsondata-"));
}

test("a missing data file raises a DataFileError naming the file", () => {
  const dir = tmpdir();
  try {
    const path = posix.join(dir, "absent.json");
    assert.throws(
      () => read(path),
      (/** @type {unknown} */ err) => {
        assert.ok(err instanceof DataFileError, "the error is a DataFileError");
        assert.ok(/** @type {Error} */ (err).message.includes(`akmon data file missing: ${path}`));
        return true;
      },
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("a broken data file raises a DataFileError naming the file", () => {
  const dir = tmpdir();
  try {
    const path = posix.join(dir, "broken.json");
    fs.writeFileSync(path, "{ oops");
    assert.throws(
      () => read(path),
      (/** @type {unknown} */ err) => {
        assert.ok(err instanceof DataFileError, "the error is a DataFileError");
        const message = /** @type {Error} */ (err).message;
        assert.ok(message.includes(path), "the file is named");
        assert.match(message, /is not valid JSON/);
        return true;
      },
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("a data file is read and parsed as its own data", () => {
  const dir = tmpdir();
  try {
    const path = posix.join(dir, "policy.json");
    fs.writeFileSync(path, '{"fixes": ["akmon sync"], "count": 2}\n');
    assert.deepStrictEqual(/** @type {{fixes: string[], count: number}} */ (read(path)), { fixes: ["akmon sync"], count: 2 });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("fill leaves single braces literal: a {files} check command passes through", () => {
  assert.equal(fill("uv run ruff check {files}", {}), "uv run ruff check {files}");
});

test("fill leaves non-placeholder braces literal: uppercase is not a name", () => {
  assert.equal(fill("keep {{Name}} and {name} as is", {}), "keep {{Name}} and {name} as is");
});

test("an unfilled placeholder raises a DataFileError naming the key", () => {
  assert.throws(
    () => fill("lint with {{runner}}", {}),
    (/** @type {unknown} */ err) => {
      assert.ok(err instanceof DataFileError, "the error is a DataFileError");
      assert.equal(/** @type {Error} */ (err).message, "placeholder {{runner}} in a data template has no value");
      return true;
    },
  );
});

test("values are inserted verbatim, in order, every occurrence", () => {
  assert.equal(fill("{{runner}} on {{scope}}", { runner: "uv run pytest", scope: "common/" }), "uv run pytest on common/");
  assert.equal(fill("{{n}}-{{n}}", { n: "1" }), "1-1");
  // The Python's `str(value)`: a non-string value is rendered, not rejected.
  assert.equal(fill("{{count}} fixes", { count: "2" }), "2 fixes");
});
