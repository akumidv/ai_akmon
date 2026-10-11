import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { test } from "node:test";

import { sha256Hex } from "./sha256.mjs";

const reference = (/** @type {string} */ text) => createHash("sha256").update(text, "utf8").digest("hex");

test("sha256Hex matches the standard vectors", () => {
  assert.equal(sha256Hex(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  assert.equal(sha256Hex("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});

test("sha256Hex matches node:crypto around every padding boundary and on non-ASCII text", () => {
  for (let length = 0; length <= 200; length++) {
    const text = "x".repeat(length);
    assert.equal(sha256Hex(text), reference(text), `length ${length}`);
  }
  for (const text of ["é", "🧭 agent", "\u0000\u0001", "a\0b", "日本語".repeat(40)]) {
    assert.equal(sha256Hex(text), reference(text));
  }
});

test("sha256Hex matches node:crypto on random strings", () => {
  for (let i = 0; i < 300; i++) {
    const text = randomBytes(1 + (i % 150)).toString("latin1");
    assert.equal(sha256Hex(text), reference(text));
  }
});
