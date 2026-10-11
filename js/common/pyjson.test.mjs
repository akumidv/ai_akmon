/**
 * node:test for `js/common/pyjson.mjs` — `json.loads`'s grammar where `JSON.parse` differs, and
 * the stdin reader. The vendor adapters' tests (`claude_adapter.test.mjs`, `codex_adapter.test.mjs`)
 * pin what each makes of an error; these pin the loader itself.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { JSONDecodeError, jsonLoads } from "./pyjson.mjs";

const MODULE = fileURLToPath(new URL("./pyjson.mjs", import.meta.url));

test("jsonLoads is JSON.parse for a document JSON.parse reads", () => {
  assert.deepEqual(jsonLoads('{"a":[1,2.5,"x",null,true],"b":{"c":-0}}'), { a: [1, 2.5, "x", null, true], b: { c: -0 } });
  assert.deepEqual(jsonLoads(' \t\r\n[] '), []);
  assert.equal(jsonLoads('"s"'), "s");
});

test("jsonLoads accepts NaN, Infinity and -Infinity as Python's json does, and nothing near them", () => {
  assert.ok(Number.isNaN(jsonLoads("NaN")));
  assert.deepEqual(jsonLoads('[Infinity,-Infinity,{"k":NaN}]').slice(0, 2), [Infinity, -Infinity]);
  assert.deepEqual(jsonLoads('{"s":"NaN Infinity"}'), { s: "NaN Infinity" });
  for (const text of ["-NaN", "nan", "Infinit", "-Inf", "+Infinity", "{NaN:1}", "[NaN,]", "NaN NaN"]) {
    assert.throws(() => jsonLoads(text), JSONDecodeError, text);
  }
});

test("jsonLoads refuses an integer of more than 4300 digits with ValueError, not a float or a string", () => {
  const digits = (/** @type {number} */ n) => "1".repeat(n);
  assert.doesNotThrow(() => jsonLoads(`[${digits(4300)}]`));
  for (const text of [`[${digits(4301)}]`, `[-${digits(4301)}]`, `{"a":${digits(5000)}}`]) {
    assert.throws(() => jsonLoads(text), { name: "ValueError" }, text.slice(0, 8));
  }
  for (const text of [`[${digits(4301)}.0]`, `[${digits(4301)}e0]`, `["${digits(4301)}"]`]) {
    assert.doesNotThrow(() => jsonLoads(text), text.slice(0, 8));
  }
  assert.throws(() => jsonLoads(`[, ${digits(4301)}]`), JSONDecodeError); // a syntax error comes first
});

test("jsonLoads raises RecursionError past 9997 levels of nesting, brackets in a string excepted", () => {
  assert.doesNotThrow(() => jsonLoads("[".repeat(9997) + "]".repeat(9997)));
  assert.throws(() => jsonLoads("[".repeat(9998) + "]".repeat(9998)), { name: "RecursionError" });
  assert.throws(() => jsonLoads(`${'{"a":'.repeat(9998)}1${"}".repeat(9998)}`), { name: "RecursionError" });
  assert.doesNotThrow(() => jsonLoads(`["${"[".repeat(20000)}"]`));
});

test("jsonLoads keeps a __proto__ key as an own entry and the last of a repeated key", () => {
  const value = jsonLoads('{"__proto__":{"x":1},"a":1,"a":2,"n":NaN}');
  assert.equal(Object.hasOwn(value, "__proto__"), true);
  assert.equal(value.a, 2);
  assert.equal(Object.getPrototypeOf(value), Object.prototype);
});

/** The module's stdin readers run on `input` in a child; what they answered, as JSON. */
function readIn(/** @type {string} */ reader, /** @type {string | Buffer} */ input) {
  const script =
    `import(${JSON.stringify(MODULE)}).then((m) => { try { const v = m.${reader}(); ` +
    "console.log(JSON.stringify(typeof v === 'string' ? v : [...v])); } catch (e) { console.log('ERR ' + e.name); } });";
  return spawnSync("node", ["-e", script], { input, encoding: "utf8" }).stdout.trim();
}

test("the stdin readers: every byte, a BOM kept, a malformed sequence is UnicodeDecodeError", () => {
  assert.equal(readIn("readStdinText", "héllo\r\n"), JSON.stringify("héllo\r\n"));
  assert.equal(readIn("readStdinText", "﻿{}"), JSON.stringify("﻿{}"));
  assert.equal(readIn("readStdinText", ""), '""');
  assert.equal(readIn("readStdinText", Buffer.from([0x7b, 0xff])), "ERR UnicodeDecodeError");
  assert.equal(readIn("readStdinBytes", Buffer.from([0x7b, 0xff])), "[123,255]");
  const big = "x".repeat(200_000);
  assert.equal(readIn("readStdinText", big).length, big.length + 2);
});
