import { test } from "node:test";
import assert from "node:assert/strict";

import { descriptorOf, readEvents, userEventOf } from "./record-events.mjs";
import { redactFloor } from "./redact.mjs";

const KEYS = redactFloor(["ssn"]);

test("a descriptor cuts every text to its limit and decides sensitivity again, whatever the page said", () => {
  const given = { tag: "input", type: "PASSWORD", sensitive: false, text: "x".repeat(500), css: "y".repeat(500) };
  const out = descriptorOf(given, KEYS);
  assert.equal(out.sensitive, true);
  assert.equal(out.text, "");
  assert.equal(out.css.length, 300);
  assert.equal(out.type, "password");
  assert.equal(descriptorOf({ tag: "input", nameAttr: "ssn", text: "t" }, KEYS).sensitive, true);
  assert.equal(descriptorOf("not an object", KEYS).tag, "");
});

test("a user event from the page: a known kind only, a length but never a value, none for a secret", () => {
  const typed = userEventOf(
    JSON.stringify({ kind: "input", target: { tag: "input", nameAttr: "city" }, length: 6, value: "Berlin" }),
    KEYS,
  );
  assert.deepEqual(
    { kind: typed?.kind, length: typed?.length, hasValue: JSON.stringify(typed).includes("Berlin") },
    { kind: "input", length: 6, hasValue: false },
  );
  const secret = userEventOf(
    JSON.stringify({ kind: "input", target: { tag: "input", type: "password" }, length: 8 }),
    KEYS,
  );
  assert.equal(secret?.length, null);
  assert.equal(secret?.target.sensitive, true);
  assert.equal(userEventOf(JSON.stringify({ kind: "eval", target: {} }), KEYS), null);
  assert.equal(userEventOf("{not json", KEYS), null);
  assert.equal(userEventOf(JSON.stringify({ kind: "keydown", key: "a", target: {} }), KEYS), null);
  assert.equal(userEventOf(JSON.stringify({ kind: "keydown", key: "Enter", target: {} }), KEYS)?.key, "Enter");
});

test("a page that sends a sensitive field's text through a field the listener should not fill gets nothing kept", () => {
  const event = userEventOf(
    JSON.stringify({ kind: "click", target: { tag: "input", type: "password", text: "hunter2", name: "Password" } }),
    KEYS,
  );
  assert.equal(event?.target.text, "");
});

test("a file's events are read line by line and an unreadable tail is counted, not fatal", () => {
  const text = `${JSON.stringify({ t: 0, kind: "start" })}\n${JSON.stringify({ t: 5, kind: "click" })}\n{"t": 9, "kind": "net", "ur`;
  const { events, skipped } = readEvents(text);
  assert.deepEqual(
    events.map((event) => event.kind),
    ["start", "click"],
  );
  assert.equal(skipped, 1);
});
