import { test } from "node:test";
import assert from "node:assert/strict";

import {
  decodeStreamMessage,
  decodeStreamRequest,
  encodeStreamMessage,
  encodeStreamRequest,
  isStreamRequest,
  LineBuffer,
  stopLine,
} from "./stream-protocol.mjs";

/** @type {import("./stream-protocol.mjs").RecordRequest} */
const REQUEST = {
  browserURL: "http://127.0.0.1:9582",
  page: null,
  allPages: false,
  bodies: true,
  maxBody: 4096,
  redact: ["ssn"],
  binding: "__akmonRecord",
};

test("a streaming request is one line, told apart from a one-shot request, and round-trips", () => {
  const line = encodeStreamRequest(REQUEST);
  assert.ok(line.endsWith("\n"));
  assert.equal(line.trim().includes("\n"), false);
  assert.ok(isStreamRequest(line.trim()));
  assert.deepEqual(decodeStreamRequest(line.trim()), REQUEST);
  assert.equal(isStreamRequest(JSON.stringify({ browserURL: "x", operations: [] })), false);
  assert.equal(isStreamRequest("not json"), false);
});

test("a streaming request that is wrong is refused naming the field", () => {
  const bad = (/** @type {object} */ change) => JSON.stringify({ stream: "record", ...REQUEST, ...change });
  for (const [change, pattern] of /** @type {[object, RegExp][]} */ ([
    [{ browserURL: 3 }, /browserURL/],
    [{ bodies: "yes" }, /booleans/],
    [{ maxBody: 0 }, /maxBody/],
    [{ redact: [1] }, /redact/],
    [{ binding: "a b" }, /binding/],
  ])) {
    assert.throws(() => decodeStreamRequest(bad(change)), pattern);
  }
  assert.throws(() => decodeStreamRequest("{"), /not JSON/);
});

test("the messages round-trip and the codec refuses a line that is none of them", () => {
  const messages = /** @type {import("./stream-protocol.mjs").StreamMessage[]} */ ([
    { ready: { pages: ["p1"] } },
    { ev: { kind: "click", page: "p1" }, ago: 12 },
    { error: "no page" },
    { end: { reason: "stopped", error: null } },
  ]);
  for (const message of messages) {
    assert.deepEqual(decodeStreamMessage(encodeStreamMessage(message).trim()), message);
  }
  assert.throws(() => decodeStreamMessage('{"hello": 1}'), /none of/);
  assert.throws(() => decodeStreamMessage("x"), /not JSON/);
  assert.deepEqual(JSON.parse(stopLine()), { stop: true });
});

test("lines are whole only once their newline has arrived, whatever the chunks", () => {
  const buffer = new LineBuffer();
  assert.deepEqual(buffer.push('{"a":'), []);
  assert.deepEqual(buffer.push('1}\n{"b":2}\r\n\n{"c"'), ['{"a":1}', '{"b":2}']);
  assert.equal(buffer.rest(), '{"c"');
  assert.deepEqual(buffer.push(":3}\n"), ['{"c":3}']);
});
