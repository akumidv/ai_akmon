/**
 * node:test for the crash-handler naming in `js/common/pyvalue.mjs`: `exceptionClassName` prints
 * the class the Python twin would raise, because the hooks' crash line and notice carry it; and
 * for the universal-newline translation every text-mode read shares.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { exceptionClassName, pyError, pyRepr, pyStr, readText, universalNewlines } from "./pyvalue.mjs";

/** What `body` throws. */
function thrown(/** @type {() => unknown} */ body) {
  try {
    body();
  } catch (error) {
    return error;
  }
  throw new assert.AssertionError({ message: "nothing was thrown" });
}

test("a JSON.parse refusal is named JSONDecodeError, as json.loads raises it", () => {
  assert.equal(exceptionClassName(thrown(() => JSON.parse("{"))), "JSONDecodeError");
  assert.equal(exceptionClassName(thrown(() => JSON.parse("﻿{}"))), "JSONDecodeError");
});

test("a NUL in a path is ValueError, not Node's TypeError", () => {
  const error = thrown(() => fs.statSync("a\0b"));
  assert.equal(/** @type {Error} */ (error).name, "TypeError");
  assert.equal(exceptionClassName(error), "ValueError");
});

test("system errors map to their OSError subclass; pyError and other errors keep their name", () => {
  assert.equal(exceptionClassName(thrown(() => fs.readFileSync("/nonexistent/x"))), "FileNotFoundError");
  assert.equal(exceptionClassName(pyError("KeyError", "k")), "KeyError");
  assert.equal(exceptionClassName(new TypeError("x")), "TypeError");
  assert.equal(exceptionClassName("not an error"), "Exception");
});

test("universalNewlines turns CRLF and a lone CR into LF and leaves LF alone", () => {
  assert.equal(universalNewlines("a\r\nb\rc\n\r\r\nd\r"), "a\nb\nc\n\n\nd\n");
  assert.equal(universalNewlines("\n\n"), "\n\n");
});

test("readText decodes strictly, keeps a BOM and translates newlines", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pyvalue-test-"));
  try {
    fs.writeFileSync(path.join(dir, "ok"), Buffer.from("\ufeffa\r\nb\r", "utf8"));
    assert.equal(readText(path.join(dir, "ok")), "\ufeffa\nb\n");
    fs.writeFileSync(path.join(dir, "bad"), Buffer.from([0x61, 0xff]));
    assert.equal(/** @type {Error} */ (thrown(() => readText(path.join(dir, "bad")))).name, "UnicodeDecodeError");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("pyRepr spells nested lists and dicts as Python's repr does", () => {
  assert.equal(pyRepr([1, "a", null, true, [], {}]), "[1, 'a', None, True, [], {}]");
  assert.equal(pyRepr({ a: [1, { "b'": false }], c: 2.5 }), `{'a': [1, {"b'": False}], 'c': 2.5}`);
  assert.equal(pyStr("plain"), "plain");
  assert.equal(pyStr([["x"]]), "[['x']]");
});

test("pyStr of a member nested as deep as json.loads takes does not exhaust the stack", () => {
  // 9996 levels inside the payload object: the deepest the Python twin's json.loads accepts.
  const depth = 9996;
  const dict = JSON.parse(`${'{"a": '.repeat(depth)}1${"}".repeat(depth)}`);
  assert.equal(pyStr(dict), `${"{'a': ".repeat(depth)}1${"}".repeat(depth)}`);
  const list = JSON.parse(`${"[".repeat(depth)}${"]".repeat(depth)}`);
  assert.equal(pyStr(list), `${"[".repeat(depth)}${"]".repeat(depth)}`);
});
