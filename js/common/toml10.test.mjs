/**
 * node:test for `js/common/toml10.mjs` — the TOML 1.0.0 fence in front of smol-toml (C115). Each
 * refused text is one `tomllib` (Python 3.11) refuses and smol-toml 1.9.0 parses; each accepted
 * one is TOML 1.0.0 that must reach the parser. The record reader's answers on the same boundary
 * are the shared units table (`meta/conformance/units/record.toml`), run against both twins.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { parse } from "../vendor/smol-toml/dist/index.js";
import { toml10Refusal } from "./toml10.mjs";

const _REFUSED = [
  "\uFEFFmount = 1\n",
  'a = "x\\x62c"\n',
  'a = "x\\ec"\n',
  'a = """x\\x62"""\n',
  "t = {a = 1,}\n",
  "t = {a = 1, }\n",
  "t = {a = 1,\n b = 2}\n",
  "a = [{b = 1,\n c = 2}]\n",
  "t = 07:32\n",
  "t = 1979-05-27T07:32Z\n",
  "t = 1979-05-27 07:32\n",
  "a = 1979-02-29\n",
  "a = [1979-02-29]\n",
];

const _ACCEPTED = [
  'a = "x\\\\x"\n',
  "a = '\\x'\n",
  "a = '''\\e'''\n",
  "# \\x {a = 1,} 07:32\na = 1\n",
  'a = "{a = 1,}"\n',
  "t = {a = [1,\n2]}\n",
  "a = [\n1,\n2,\n]\n",
  'a = """q""""\nb = "x"\n',
  "a = 2000-02-29\n",
  "a = 1979-05-27 07:32:00\n",
  "1979-02-29 = 1\n",
  "[1979-02-29]\nk = 1\n",
  "[ a . 1979-13-01 ]\nk = 1\n",
  "k1979-02-29 = 1\n",
  "a = 1\r\nb = 2\r\n",
];

test("every 1.1.0-only text is refused, and smol-toml alone would have taken it", () => {
  for (const text of _REFUSED) {
    assert.notEqual(toml10Refusal(text), null, JSON.stringify(text));
    assert.doesNotThrow(() => parse(text), JSON.stringify(text));
  }
});

test("TOML 1.0.0 passes the fence untouched: strings, comments and keys never trip it", () => {
  for (const text of _ACCEPTED) {
    assert.equal(toml10Refusal(text), null, JSON.stringify(text));
  }
});

test("a refusal names the line and column of the construct", () => {
  assert.deepEqual(toml10Refusal('mount = "package"\nlint = "a\\x62"\n'), {
    line: 2,
    column: 10,
    reason: "the \\x escape is a TOML 1.1.0 feature",
  });
  assert.deepEqual(toml10Refusal("\uFEFFa = 1\n"), {
    line: 1,
    column: 1,
    reason: "leading UTF-8 BOM (TOML is BOM-free UTF-8)",
  });
});
