/**
 * node:test for `js/common/work_style.mjs` — the twin of `meta/tests/test_work_style.py`'s resolver,
 * typed-command and session-store cases (ADR 0031/D03). The store text and the reply literals are the
 * Python's: a drift in either twin shows as a failing literal.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  WorkStyle,
  knownStyle,
  readData,
  readSessions,
  recordAndReply,
  recordSessionStyle,
  resolve,
  typedStyle,
} from "./work_style.mjs";

const DATA = readData();

/** A scratch project: `AGENTS.md`, an `_aitna` layer and its record file text. */
function project(record = 'mount = "package"\n') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-style-")));
  fs.mkdirSync(path.join(root, "_aitna"));
  fs.writeFileSync(path.join(root, "AGENTS.md"), "# a\n");
  fs.writeFileSync(path.join(root, "_aitna", ".akmon.toml"), record);
  return root;
}

/** @param {string} root @param {string} name */
const local = (root, name) => path.join(root, "_aitna", ".local", name);

/** @param {string} file @param {string} text */
function put(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
}

test("the data file names the two styles and their locations", () => {
  assert.deepEqual(DATA.styles, ["delegating", "controlling"]);
  assert.equal(DATA.default, "delegating");
  assert.equal(DATA.developer_rel, ".local/work.json");
  assert.equal(DATA.sessions_rel, ".local/work-sessions.json");
  assert.equal(DATA.sessions_keep, 50);
  assert.equal(DATA.record_section, "work");
  assert.equal(DATA.record_key, "style");
});

test("precedence: session, developer, project, default — the first valid level wins", () => {
  const root = project('mount = "package"\n[work]\nstyle = "controlling"\n');
  assert.deepEqual(resolve(root, "s1", DATA), new WorkStyle("controlling", "project"));
  put(local(root, "work.json"), '{"style": "delegating"}');
  assert.deepEqual(resolve(root, "s1", DATA), new WorkStyle("delegating", "developer"));
  put(local(root, "work-sessions.json"), '{"sessions": {"s1": "controlling"}}');
  assert.deepEqual(resolve(root, "s1", DATA), new WorkStyle("controlling", "session"));
  assert.equal(resolve(root, "other", DATA).source, "developer");
  assert.equal(resolve(root, null, DATA).source, "developer");
  assert.deepEqual(resolve(project(), "s1", DATA), new WorkStyle("delegating", "default"));
});

for (const bad of [
  '{"style": "chaotic"}',
  '{"style": 3}',
  '{"style": null}',
  "{broken",
  "[]",
  '{"other": "controlling"}',
  "",
]) {
  test(`an invalid developer file (${JSON.stringify(bad)}) falls through to the project`, () => {
    const root = project('mount = "package"\n[work]\nstyle = "controlling"\n');
    put(local(root, "work.json"), bad);
    assert.deepEqual(resolve(root, null, DATA), new WorkStyle("controlling", "project"));
  });
}

for (const record of ['[work]\nstyle = "chaotic"\n', "[work]\nstyle = 3\n", "work = 1\n", "[work]\n"]) {
  test(`an invalid project value (${JSON.stringify(record)}) falls through to the default`, () => {
    assert.deepEqual(resolve(project(record), null, DATA), new WorkStyle("delegating", "default"));
  });
}

for (const bad of [
  '{"sessions": {"s1": "chaotic"}}',
  '{"sessions": {"s1": 1}}',
  '{"sessions": []}',
  "{broken",
  '{"sessions": {"": "controlling"}}',
]) {
  test(`an invalid session entry (${JSON.stringify(bad)}) falls through to the developer`, () => {
    const root = project();
    put(local(root, "work.json"), '{"style": "controlling"}');
    put(local(root, "work-sessions.json"), bad);
    assert.deepEqual(resolve(root, "s1", DATA), new WorkStyle("controlling", "developer"));
  });
}

test("a valid entry survives beside an invalid one", () => {
  const root = project();
  put(local(root, "work-sessions.json"), '{"sessions": {"a": "chaotic", "b": "controlling"}}');
  assert.equal(resolve(root, "a", DATA).source, "default");
  assert.deepEqual(resolve(root, "b", DATA), new WorkStyle("controlling", "session"));
});

test("the dev root is the one the project declares", () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-style-")));
  put(path.join(root, "AGENTS.md"), "# a\n");
  put(path.join(root, ".aitna-root"), "meta\n");
  put(path.join(root, "meta", ".akmon.toml"), '[work]\nstyle = "controlling"\n');
  assert.deepEqual(resolve(root, null, DATA), new WorkStyle("controlling", "project"));
  put(path.join(root, "meta", ".local", "work.json"), '{"style": "delegating"}');
  assert.deepEqual(resolve(root, null, DATA), new WorkStyle("delegating", "developer"));
});

for (const [prompt, typed] of /** @type {[string, string][]} */ ([
  ["/style controlling", "controlling"],
  ["  /style   Delegating \n", "Delegating"],
  ["/style\tCONTROLLING", "CONTROLLING"],
  ["/style", ""],
  ["/style nonsense", "nonsense"],
  ["/style controlling now", "controlling now"],
  ["/style\ncontrolling", "controlling"],
])) {
  test(`a style prompt yields the text after the command: ${JSON.stringify(prompt)}`, () => {
    assert.equal(typedStyle(prompt, DATA), typed);
  });
}

for (const prompt of [
  "",
  "hello",
  "/styles controlling",
  "please /style controlling",
  "/Style controlling",
  "/ style x",
]) {
  test(`any other prompt is not the command: ${JSON.stringify(prompt)}`, () => {
    assert.equal(typedStyle(prompt, DATA), null);
  });
}

test("the value is case-insensitive and exact otherwise", () => {
  assert.equal(knownStyle("CONTROLLING", DATA), "controlling");
  assert.equal(knownStyle("Delegating", DATA), "delegating");
  assert.equal(knownStyle("control", DATA), null);
  assert.equal(knownStyle("", DATA), null);
});

test("recording writes the documented shape atomically", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-store-"));
  const file = path.join(dir, ".local", "work-sessions.json");
  recordSessionStyle(file, "s1", "controlling", DATA);
  assert.equal(fs.readFileSync(file, "utf8"), '{\n  "sessions": {\n    "s1": "controlling"\n  }\n}\n');
  assert.deepEqual(fs.readdirSync(path.dirname(file)), ["work-sessions.json"]);
});

test("the store keeps only the fifty most recent sessions", () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-store-")), "work-sessions.json");
  for (let number = 0; number < 60; number += 1) {
    recordSessionStyle(file, `s${number}`, "controlling", DATA);
  }
  const expected = Array.from({ length: 50 }, (_, index) => `s${index + 10}`);
  assert.deepEqual([...readSessions(file, DATA).keys()], expected);
});

test("a repeated switch moves the session to the newest place and replaces its style", () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-store-")), "work-sessions.json");
  recordSessionStyle(file, "a", "controlling", DATA);
  recordSessionStyle(file, "b", "controlling", DATA);
  recordSessionStyle(file, "a", "delegating", DATA);
  assert.deepEqual(
    [...readSessions(file, DATA)],
    [
      ["b", "controlling"],
      ["a", "delegating"],
    ],
  );
});

test("recording over a corrupt store replaces it", () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-store-")), "work-sessions.json");
  fs.writeFileSync(file, "{broken");
  recordSessionStyle(file, "s1", "delegating", DATA);
  assert.deepEqual([...readSessions(file, DATA)], [["s1", "delegating"]]);
});

test("a failed write leaves no temp file", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "akmon-work-store-"));
  const file = path.join(dir, "work-sessions.json");
  fs.mkdirSync(file); // a directory where the store should be: the rename is refused
  assert.throws(() => recordSessionStyle(file, "s1", "controlling", DATA));
  assert.deepEqual(fs.readdirSync(dir), ["work-sessions.json"]);
});

test("recordAndReply: a valid command records and confirms", () => {
  const root = project();
  const reply = recordAndReply(root, "s1", "/style Controlling", DATA);
  assert.match(String(reply), /controlling/);
  assert.match(String(reply), /next park boundary/);
  assert.deepEqual(resolve(root, "s1", DATA), new WorkStyle("controlling", "session"));
});

test("recordAndReply: an invalid value names the allowed values and records nothing", () => {
  const root = project();
  const reply = recordAndReply(root, "s1", "/style chaotic", DATA);
  assert.equal(
    reply,
    "[akmon] 'chaotic' is not a work style; the allowed values are delegating, controlling. The style in force is unchanged.",
  );
  assert.equal(fs.existsSync(local(root, "work-sessions.json")), false);
  assert.match(String(recordAndReply(root, "s1", "/style", DATA)), /delegating, controlling/);
});

test("recordAndReply: no session id records nothing and says so", () => {
  const root = project();
  const reply = recordAndReply(root, null, "/style controlling", DATA);
  assert.match(String(reply), /no session id/);
  assert.match(String(reply), /\.local\/work\.json/);
  assert.equal(fs.existsSync(local(root, "work-sessions.json")), false);
});

test("recordAndReply: any other prompt is silent and writes nothing", () => {
  const root = project();
  assert.equal(recordAndReply(root, "s1", "refactor the parser", DATA), null);
  assert.equal(fs.existsSync(path.join(root, "_aitna", ".local")), false);
});
