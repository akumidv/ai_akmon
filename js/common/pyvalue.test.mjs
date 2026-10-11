/**
 * node:test for the crash-handler naming in `js/common/pyvalue.mjs`: `exceptionClassName` prints
 * the class the Python twin would raise, because the hooks' crash line and notice carry it.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

import { exceptionClassName, pyError } from "./pyvalue.mjs";

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
