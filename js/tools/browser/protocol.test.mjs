import { test } from "node:test";
import assert from "node:assert/strict";

import { decodeRequest, decodeResponse, encodeRequest, encodeResponse } from "./protocol.mjs";

/** @type {import("./protocol.mjs").Request} */
const REQUEST = {
  browserURL: "http://127.0.0.1:9582",
  page: null,
  redact: ["password"],
  operations: [
    { op: "snapshot", maxNodes: 10, text: false },
    { op: "screenshot", viewport: { width: 390, height: 844 }, scheme: "dark", full: false },
    { op: "eval", expression: "document.title" },
    { op: "logs", until: null, seconds: 3 },
    { op: "net", seconds: 2, until: "api", failed: true, bodies: true, maxBody: 100 },
  ],
};

test("a request survives the trip through the runner's stdin", () => {
  assert.deepEqual(decodeRequest(encodeRequest(REQUEST)), REQUEST);
  assert.deepEqual(decodeRequest(encodeRequest({ ...REQUEST, page: "2" })).page, "2");
});

test("a request that is not valid is refused naming what is wrong", () => {
  const bad = [
    ["not json", /not JSON/],
    [JSON.stringify([]), /browserURL/],
    [JSON.stringify({ ...REQUEST, page: 3 }), /"page"/],
    [JSON.stringify({ ...REQUEST, redact: "x" }), /redact/],
    [JSON.stringify({ ...REQUEST, operations: [] }), /operations/],
    [JSON.stringify({ ...REQUEST, operations: [{ op: "reload" }] }), /not valid: {"op":"reload"}/],
    [JSON.stringify({ ...REQUEST, operations: [{ op: "eval" }] }), /not valid/],
    [JSON.stringify({ ...REQUEST, operations: [{ op: "logs", until: null, seconds: 0 }] }), /not valid/],
    [
      JSON.stringify({
        ...REQUEST,
        operations: [{ op: "screenshot", viewport: { width: 1 }, scheme: null, full: false }],
      }),
      /not valid/,
    ],
  ];
  for (const [text, pattern] of bad) {
    assert.throws(() => decodeRequest(String(text)), /** @type {RegExp} */ (pattern), String(text).slice(0, 60));
  }
});

test("a response is a list of outcomes or one error, and nothing else", () => {
  /** @type {import("./protocol.mjs").Response} */
  const ok = {
    page: { id: "T1", title: "t", url: "u" },
    results: [
      { ok: true, value: 1 },
      { ok: false, error: "x" },
    ],
  };
  assert.deepEqual(decodeResponse(encodeResponse(ok)), ok);
  assert.deepEqual(decodeResponse(encodeResponse({ error: "no page" })), { error: "no page" });
  assert.throws(() => decodeResponse("{}"), /neither/);
  assert.throws(() => decodeResponse("nope"), /not JSON/);
});

test("a request for the extension bench survives the trip, and its new fields are checked", () => {
  /** @type {import("./protocol.mjs").Request} */
  const bench = {
    ...REQUEST,
    target: "sw",
    ext: "Bench",
    extensionPaths: ["C:\\work\\ext"],
    operations: [
      { op: "eval", expression: "1", world: "isolated" },
      { op: "selectors", registry: { buy: [".buy", ".buy-v2"] } },
      { op: "ext-devmode" },
      { op: "ext-list" },
      { op: "ext-reload" },
      { op: "ext-action" },
    ],
  };
  assert.deepEqual(decodeRequest(encodeRequest(bench)), bench);
  assert.equal(decodeRequest(encodeRequest({ ...bench, ext: null })).ext, null);
  const bad = [
    [{ ...REQUEST, target: 3 }, /"target"/],
    [{ ...REQUEST, ext: 3 }, /"ext"/],
    [{ ...REQUEST, extensionPaths: "x" }, /"extensionPaths"/],
    [{ ...REQUEST, operations: [{ op: "eval", expression: "1", world: "main" }] }, /not valid/],
    [{ ...REQUEST, operations: [{ op: "selectors", registry: { a: [] } }] }, /not valid/],
    [{ ...REQUEST, operations: [{ op: "selectors", registry: { a: [""] } }] }, /not valid/],
    [{ ...REQUEST, operations: [{ op: "selectors" }] }, /not valid/],
  ];
  for (const [request, pattern] of bad) {
    assert.throws(
      () => decodeRequest(JSON.stringify(request)),
      /** @type {RegExp} */ (pattern),
      JSON.stringify(request).slice(0, 80),
    );
  }
});
