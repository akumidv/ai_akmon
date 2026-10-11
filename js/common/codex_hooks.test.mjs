/**
 * node:test for `js/common/codex_hooks.mjs` — the named pins of the twin: the closed diagnostic
 * table, `queryHooksList` with an injected runner (no process), and `defaultRunner` against a fake
 * `codex` on a temporary PATH: a clean answer, an interleaved one, a hang (the bound), a hang that
 * ignores SIGTERM (the cleanup bound), an early exit, garbage, a binary that does not start. The
 * pure parsers are the spec of `meta/conformance/units/codex_hooks.toml`, run through `probe.mjs`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import {
  CodexProtocolError, CodexWiringError, DEFAULT_TIMEOUT_SECONDS, defaultRunner, expectedCodexHooks, hookTrustProblems, queryHooksList,
  readCodexHooksData } from "./codex_hooks.mjs";

const DATA_FILE = new URL("../../common/codex_hooks.json", import.meta.url);
const SOURCE = fs.readFileSync(new URL("./codex_hooks.mjs", import.meta.url), "utf-8");
const data = readCodexHooksData();

/** A value only a hostile or broken host would put on the wire; no diagnostic may contain it. */
const CANARY = "VENDOR_CANARY_7f3a";

/** @type {readonly string[]} */
const CODEX = ["codex", "app-server"];

const entry = (/** @type {Record<string, unknown>} */ over = {}) => ({
  handlerType: "command", enabled: true, trustStatus: "trusted", eventName: "preToolUse", matcher: "m", command: "c1", ...over,
});
const project = (/** @type {Record<string, unknown>} */ over = {}) => ({ cwd: "/proj", hooks: [], warnings: [], errors: [], ...over });
const answer = (/** @type {unknown[]} */ rows) => JSON.stringify({ id: 2, result: { data: rows } });
const query = (/** @type {unknown} */ raw) => queryHooksList(data, CODEX, "/proj", { runner: () => /** @type {string} */ (raw) });

// --------------------------------------------------------------------------------------
// the data file, the error classes
// --------------------------------------------------------------------------------------

test("the loader reads exactly codex_hooks.json, which carries the closed tables", () => {
  assert.deepEqual(data, JSON.parse(fs.readFileSync(DATA_FILE, "utf-8")));
  assert.deepEqual(Object.keys(data).toSorted(), ["event_names", "live_trust_statuses", "protocol_failures", "trust_statuses"]);
  assert.deepEqual(data.event_names, { PreToolUse: "preToolUse", SessionStart: "sessionStart" });
  assert.equal(DEFAULT_TIMEOUT_SECONDS, 5);
});

for (const kind of [CANARY, "no hooks/list response within 5.0s", null, 7, ["timeout"], undefined, { kind: "timeout" }, "constructor", "__proto__", "toString"]) {
  test(`a protocol error can only carry a fixed text: ${JSON.stringify(kind) ?? "undefined"}`, () => {
    const error = new CodexProtocolError(data, kind);
    assert.equal(error.kind, "unclassified");
    assert.equal(error.message, data.protocol_failures.unclassified);
    assert.equal(error.name, "CodexProtocolError");
    assert.ok(error instanceof Error);
  });
}

test("a known kind carries its table text and keeps the kind", () => {
  for (const [kind, text] of Object.entries(data.protocol_failures)) {
    const error = new CodexProtocolError(data, kind);
    assert.deepEqual([error.kind, error.message], [kind, text]);
  }
});

test("CodexWiringError is a named Error", () => {
  const error = new CodexWiringError("x");
  assert.equal(error.name, "CodexWiringError");
  assert.ok(error instanceof Error);
});

test("every raise site names a fixed kind and every kind is raised", () => {
  const named = [...SOURCE.matchAll(/(?:new CodexProtocolError\(data, |fail\()"([a-z-]+)"\)/g)].map((match) => match[1]);
  assert.ok(named.every((kind) => kind in data.protocol_failures), "a raise site names a kind outside the table");
  assert.deepEqual(new Set(named), new Set(Object.keys(data.protocol_failures).filter((kind) => kind !== "unclassified")));
  // the non-literal arguments: `fail`'s own parameter, and the rebuild of a runner's error (its `kind` alone)
  const dynamic = [...SOURCE.matchAll(/new CodexProtocolError\(data, ([^"][^)]*)\)/g)].map((match) => match[1]);
  assert.deepEqual(dynamic, ["kind", "error.kind"]);
});

// --------------------------------------------------------------------------------------
// the pure functions: a few end-to-end pins (the table has the rest)
// --------------------------------------------------------------------------------------

test("expectedCodexHooks and hookTrustProblems compose", () => {
  const wiring = { hooks: { PreToolUse: [{ matcher: "m", hooks: [{ type: "command", command: "c1" }, { type: "command", command: "c2" }] }] } };
  const expected = expectedCodexHooks(data, wiring);
  assert.deepEqual(expected, [["preToolUse", "m", "c1"], ["preToolUse", "m", "c2"]]);
  assert.deepEqual(hookTrustProblems(data, expected, [entry(), entry({ command: "c2", trustStatus: "untrusted" })]), { untrusted: ["c2"] });
  assert.throws(() => expectedCodexHooks(data, []), { name: "CodexWiringError", message: "Codex wiring is not a JSON object" });
});

test("an inherited key is not an event, a problem or a kind", () => {
  assert.throws(() => expectedCodexHooks(data, { hooks: { constructor: [] } }), CodexWiringError);
  assert.deepEqual(hookTrustProblems(data, [["preToolUse", "m", "c1"]], [entry({ trustStatus: "constructor" })]), { unrecognized: ["c1"] });
});

// --------------------------------------------------------------------------------------
// queryHooksList — the wire-protocol parsing, with an injected runner (no process)
// --------------------------------------------------------------------------------------

test("queryHooksList returns the matching cwd's hooks", async () => {
  const hooks = [entry(), entry({ command: "c2" })];
  assert.deepEqual(await query(answer([project({ hooks })])), hooks);
  assert.deepEqual(await query(answer([project({ cwd: "/other", hooks: [entry({ enabled: "no" })] }), project({ hooks })])), hooks);
});

test("queryHooksList accepts a synchronous or an asynchronous runner", async () => {
  const raw = answer([project()]);
  assert.deepEqual(await queryHooksList(data, CODEX, "/proj", { runner: () => raw }), []);
  assert.deepEqual(await queryHooksList(data, CODEX, "/proj", { runner: async () => raw }), []);
});

test("queryHooksList hands the runner the command, the cwd and the timeout", async () => {
  /** @type {unknown[]} */
  const seen = [];
  await queryHooksList(data, CODEX, "/proj", { runner: (...args) => (seen.push(args), answer([project()])), timeout: 1.5 });
  assert.deepEqual(seen, [[CODEX, "/proj", 1.5]]);
  await queryHooksList(data, CODEX, "/proj", { runner: (...args) => (seen.push(args), answer([project()])) });
  assert.deepEqual(seen[1], [CODEX, "/proj", 5]);
});

test("queryHooksList accepts a non-command handler without a command", async () => {
  assert.deepEqual(await query(answer([project({ hooks: [{ handlerType: "prompt", enabled: true, trustStatus: "trusted" }] })])).then((hooks) => hooks.length), 1);
});

/** @type {Array<[string, unknown, string]>} */
const REFUSED = [
  ["not json", "{", "not-json"],
  ["a bare string", JSON.stringify(CANARY), "not-object"],
  ["a JSON-RPC error", JSON.stringify({ id: 2, error: { code: -1, message: CANARY } }), "jsonrpc-error"],
  ["an id that does not echo", JSON.stringify({ id: CANARY, result: {} }), "id-mismatch"],
  ["no result.data", JSON.stringify({ id: 2, result: {} }), "no-data"],
  ["no entry for the cwd", answer([project({ cwd: "/other" })]), "no-project"],
  ["two entries for the cwd", answer([project(), project()]), "duplicate-project"],
  ["a misshapen entry", answer([{ cwd: "/proj" }]), "project-shape"],
  ["discovery errors", answer([project({ errors: [CANARY] })]), "discovery-errors"],
  ["a scalar hook element", answer([project({ hooks: [CANARY] })]), "hook-not-object"],
  ["a hook without handlerType", answer([project({ hooks: [{ enabled: true, trustStatus: "trusted" }] })]), "hook-handler"],
  ["a hook with a vendor trust word", answer([project({ hooks: [entry({ trustStatus: CANARY })] })]), "hook-trust"],
  ["a command hook with a non-string matcher", answer([project({ hooks: [entry({ matcher: 3 })] })]), "hook-matcher"],
  ["a non-string response", 7, "not-json"],
];
for (const [label, raw, kind] of REFUSED) {
  test(`queryHooksList refuses ${label} with a fixed text`, async () => {
    await assert.rejects(query(raw), (/** @type {unknown} */ error) => {
      assert.ok(error instanceof CodexProtocolError);
      assert.equal(error.kind, kind);
      assert.equal(error.message, data.protocol_failures[kind]);
      assert.ok(!error.message.includes(CANARY));
      return true;
    });
  });
}

test("queryHooksList turns any runner failure into runner-failed without its text", async () => {
  for (const thrown of [new Error(CANARY), Object.assign(new Error(CANARY), { code: "EPIPE" }), new TypeError(CANARY)]) {
    await assert.rejects(queryHooksList(data, CODEX, "/proj", { runner: () => { throw thrown; } }), (error) => {
      assert.ok(error instanceof CodexProtocolError);
      assert.equal(error.kind, "runner-failed");
      assert.ok(!error.message.includes(CANARY));
      assert.equal(error.cause, undefined);
      return true;
    });
  }
  await assert.rejects(queryHooksList(data, CODEX, "/proj", { runner: async () => { throw new Error(CANARY); } }), { message: data.protocol_failures["runner-failed"] });
});

test("queryHooksList propagates a runner's protocol kind, rebuilt from the kind alone", async () => {
  class Chatty extends CodexProtocolError {
    constructor() {
      super(data, "timeout");
      this.message = CANARY;
    }
  }
  /** @type {Array<[Error, string]>} */
  const cases = [
    [new CodexProtocolError(data, "timeout"), "timeout"],
    [new CodexProtocolError(data, CANARY), "unclassified"],
    [new Chatty(), "timeout"],
  ];
  for (const [raised, kind] of cases) {
    await assert.rejects(queryHooksList(data, CODEX, "/proj", { runner: () => { throw raised; } }), (/** @type {any} */ error) => {
      assert.equal(Object.getPrototypeOf(error), CodexProtocolError.prototype);
      assert.equal(/** @type {CodexProtocolError} */ (error).kind, kind);
      assert.equal(error.message, data.protocol_failures[kind]);
      assert.equal(error.cause, undefined);
      return true;
    });
  }
});

// --------------------------------------------------------------------------------------
// defaultRunner — the real subprocess / JSON-RPC implementation, against a fake `codex`
// --------------------------------------------------------------------------------------

/**
 * Run `body` with a `codex` executable (a node script of `source`) first on PATH, in a fresh
 * directory that is also the cwd handed to the runner.
 * @param {string} source
 * @param {(dir: string) => Promise<void>} body
 */
async function withFakeCodex(source, body) {
  const dir = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-codex-test-")));
  const bin = posix.join(dir, "bin");
  fs.mkdirSync(bin);
  fs.writeFileSync(posix.join(bin, "codex"), `#!${process.execPath}\n${source}`, { mode: 0o755 });
  const savedPath = process.env.PATH;
  process.env.PATH = `${bin}:${savedPath}`;
  try {
    await body(dir);
  } finally {
    process.env.PATH = savedPath;
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** The script prelude: collect stdin lines, call `onLine(line, index)` for each, exit on end. */
const READER = `
const fs = require("fs");
const lines = [];
let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let at;
  while ((at = buffer.indexOf("\\n")) >= 0) {
    const line = buffer.slice(0, at);
    buffer = buffer.slice(at + 1);
    lines.push(line);
    onLine(line, lines.length - 1);
  }
});
process.stdin.on("end", () => process.exit(0));
`;

test("defaultRunner: a clean answer, both responses in one flush, and the handshake it sent", async () => {
  const source = `
const received = process.argv[2];
function onLine(line, index) {
  if (index === 1) {
    fs.writeFileSync(received, lines.join("\\n") + "\\n");
    process.stdout.write(JSON.stringify({ id: 1, result: {} }) + "\\n" + JSON.stringify({ id: 2, result: { data: [] } }) + "\\n");
  }
}
${READER}`;
  await withFakeCodex(source, async (dir) => {
    const received = posix.join(dir, "received.txt");
    const raw = await defaultRunner(["codex", received], dir, 5);
    assert.deepEqual(JSON.parse(raw), { id: 2, result: { data: [] } });
    assert.equal(raw, JSON.stringify({ id: 2, result: { data: [] } }) + "\n");
    // the bytes of Python's `json.dumps` with its default separators
    assert.equal(
      fs.readFileSync(received, "utf-8"),
      `{"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "akmon", "title": "akmon verify", "version": "1"}}}\n` +
        `{"id": 2, "method": "hooks/list", "params": {"cwds": ["${dir}"]}}\n`,
    );
  });
});

test("defaultRunner: a notification, a garbage line and a blank line before the answer are skipped", async () => {
  const source = `
function onLine(line, index) {
  if (index === 1) {
    process.stdout.write(JSON.stringify({ method: "remoteControl/status/changed", params: {} }) + "\\n");
    process.stdout.write("not json at all\\n\\n");
    process.stdout.write(JSON.stringify({ id: 1, result: {} }) + "\\n");
    process.stdout.write(JSON.stringify([2]) + "\\n");
    process.stdout.write(JSON.stringify({ id: 2, result: { data: [{ cwd: process.cwd(), hooks: [], warnings: [], errors: [] }] } }) + "\\n");
  }
}
${READER}`;
  await withFakeCodex(source, async (dir) => {
    assert.deepEqual(await queryHooksList(data, ["codex", "app-server"], dir, { timeout: 5 }), []);
  });
});

test("defaultRunner: an answer split across chunks, with CRLF and with no final newline", async () => {
  const source = `
const line = JSON.stringify({ id: 2, result: { data: [] } });
function onLine(_line, index) {
  if (index === 1) {
    process.stdout.write(line.slice(0, 10));
    setTimeout(() => {
      process.stdout.write(line.slice(10) + process.env.TAIL);
      if (process.env.TAIL === "") process.exit(0); // EOF is what ends an unterminated line
    }, 100);
  }
}
${READER}`;
  for (const tail of ["\n", "\r\n", ""]) {
    await withFakeCodex(source, async (dir) => {
      process.env.TAIL = tail;
      try {
        const raw = await defaultRunner(["codex"], dir, 5);
        assert.deepEqual(JSON.parse(raw), { id: 2, result: { data: [] } });
        assert.equal(raw, JSON.stringify({ id: 2, result: { data: [] } }) + (tail === "" ? "" : "\n"));
      } finally {
        delete process.env.TAIL;
      }
    });
  }
});

test("defaultRunner: a chatty stderr never blocks the child (it is not a pipe nobody reads)", async () => {
  const source = `
function onLine(_line, index) {
  if (index === 1) {
    process.stderr.write("e".repeat(1 << 20));
    process.stdout.write(JSON.stringify({ id: 2, result: { data: [] } }) + "\\n");
  }
}
${READER}`;
  await withFakeCodex(source, async (dir) => {
    assert.deepEqual(JSON.parse(await defaultRunner(["codex"], dir, 5)), { id: 2, result: { data: [] } });
  });
});

test("defaultRunner: a multi-byte character split across two chunks is decoded whole", async () => {
  const source = `
const bytes = Buffer.from(JSON.stringify({ id: 2, result: { data: [], note: "é€😀" } }) + "\\n", "utf8");
function onLine(_line, index) {
  if (index === 1) {
    const cut = bytes.indexOf(0xc3) + 1; // between the two bytes of "é"
    process.stdout.write(bytes.subarray(0, cut));
    setTimeout(() => process.stdout.write(bytes.subarray(cut)), 100);
  }
}
${READER}`;
  await withFakeCodex(source, async (dir) => {
    assert.deepEqual(JSON.parse(await defaultRunner(["codex"], dir, 5)), { id: 2, result: { data: [], note: "é€😀" } });
  });
});

test("defaultRunner: a line the JSON reader refuses for a reason other than syntax is a runner failure", async () => {
  const source = `
function onLine(_line, index) {
  if (index === 1) {
    process.stdout.write('{"id": 1, "n": ' + "1".repeat(4301) + '}\\n');
    process.stdout.write(JSON.stringify({ id: 2, result: { data: [] } }) + "\\n");
  }
}
${READER}`;
  await withFakeCodex(source, async (dir) => {
    await assert.rejects(defaultRunner(["codex"], dir, 5), { name: "ValueError" });
    await assert.rejects(queryHooksList(data, ["codex"], dir, { timeout: 5 }), { name: "CodexProtocolError", message: data.protocol_failures["runner-failed"] });
  });
});

test("defaultRunner: the child's stdin is closed before it is signalled", async () => {
  const source = `
process.on("SIGTERM", () => {});
function onLine(_line, index) {
  if (index === 1) process.stdout.write(JSON.stringify({ id: 2, result: { data: [] } }) + "\\n");
}
${READER}`;
  await withFakeCodex(source, async (dir) => {
    const started = Date.now();
    assert.deepEqual(JSON.parse(await defaultRunner(["codex"], dir, 5)), { id: 2, result: { data: [] } });
    assert.ok(Date.now() - started < 1500, "a child that exits on EOF was waited on for its grace");
  });
});

test("defaultRunner: a hang returns within the bound, and the child is gone", async () => {
  const source = `
const fs = require("fs");
fs.writeFileSync(process.argv[2], String(process.pid));
setTimeout(() => {}, 30000);
process.stdin.resume();
`;
  await withFakeCodex(source, async (dir) => {
    const pidFile = posix.join(dir, "pid");
    const started = Date.now();
    await assert.rejects(defaultRunner(["codex", pidFile], dir, 0.3), (error) => {
      assert.ok(error instanceof CodexProtocolError);
      assert.equal(error.kind, "timeout");
      return true;
    });
    const elapsed = Date.now() - started;
    console.log(`defaultRunner hang: returned in ${elapsed} ms for a 300 ms bound`);
    assert.ok(elapsed >= 280, `returned before the bound: ${elapsed} ms`);
    assert.ok(elapsed < 1500, `a hang took ${elapsed} ms for a 300 ms bound`);
    const pid = Number(fs.readFileSync(pidFile, "utf-8"));
    assert.throws(() => process.kill(pid, 0), { code: "ESRCH" });
  });
});

test("defaultRunner: a child that ignores SIGTERM is killed after the grace, not waited on", async () => {
  const source = `
const fs = require("fs");
process.on("SIGTERM", () => {});
fs.writeFileSync(process.argv[2], String(process.pid));
setInterval(() => {}, 1000);
process.stdin.resume();
`;
  await withFakeCodex(source, async (dir) => {
    const pidFile = posix.join(dir, "pid");
    const started = Date.now();
    await assert.rejects(defaultRunner(["codex", pidFile], dir, 0.3), { name: "CodexProtocolError", message: data.protocol_failures.timeout });
    const elapsed = Date.now() - started;
    console.log(`defaultRunner SIGTERM-proof hang: returned in ${elapsed} ms (bound 300 ms + 2000 ms grace)`);
    assert.ok(elapsed >= 2200 && elapsed < 3500, `cleanup took ${elapsed} ms`);
    assert.throws(() => process.kill(Number(fs.readFileSync(pidFile, "utf-8")), 0), { code: "ESRCH" });
  });
});

test("defaultRunner: a timeout of zero or less fails at once", async () => {
  await withFakeCodex(`setTimeout(() => {}, 30000); process.stdin.resume();\n`, async (dir) => {
    for (const bound of [0, -1]) {
      const started = Date.now();
      await assert.rejects(defaultRunner(["codex"], dir, bound), { message: data.protocol_failures.timeout });
      assert.ok(Date.now() - started < 1500);
    }
  });
});

test("defaultRunner: a process that exits at once is a protocol error, never a raw error", async () => {
  await withFakeCodex(`process.exit(1);\n`, async (dir) => {
    for (let round = 0; round < 5; round++) {
      await assert.rejects(defaultRunner(["codex"], dir, 2), (error) => {
        assert.ok(error instanceof CodexProtocolError);
        assert.ok(["stdout-closed", "stdin-closed"].includes(error.kind), error.kind);
        return true;
      });
    }
  });
});

test("defaultRunner: output that never answers ends as stdout-closed or a timeout", async () => {
  await withFakeCodex(`process.stdout.write("garbage\\n{\\"id\\": 1}\\n"); process.exit(0);\n`, async (dir) => {
    await assert.rejects(defaultRunner(["codex"], dir, 2), (error) => {
      assert.ok(["stdout-closed", "stdin-closed"].includes(/** @type {CodexProtocolError} */ (error).kind));
      return true;
    });
  });
  await withFakeCodex(`process.stdout.write("garbage\\n"); setTimeout(() => {}, 30000); process.stdin.resume();\n`, async (dir) => {
    await assert.rejects(defaultRunner(["codex"], dir, 0.3), { message: data.protocol_failures.timeout });
  });
});

test("defaultRunner: bytes that are not UTF-8 end the stream", async () => {
  await withFakeCodex(`process.stdout.write(Buffer.from([0xff, 0xfe, 0x0a])); setTimeout(() => {}, 30000); process.stdin.resume();\n`, async (dir) => {
    await assert.rejects(defaultRunner(["codex"], dir, 2), { message: data.protocol_failures["stdout-closed"] });
  });
});

test("defaultRunner: an answer whose id is 2 is returned as given, even when it is not a valid response", async () => {
  await withFakeCodex(`function onLine(_l, i) { if (i === 1) process.stdout.write('{"id": 2}\\n'); }\n${READER}`, async (dir) => {
    assert.equal(await defaultRunner(["codex"], dir, 2), '{"id": 2}\n');
    await assert.rejects(queryHooksList(data, ["codex"], dir), { message: data.protocol_failures["no-data"] });
  });
});

test("defaultRunner: an unstartable binary or cwd is reported by kind, not by the OS text", async () => {
  const dir = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-codex-test-")));
  try {
    for (const [command, cwd] of /** @type {Array<[string[], string]>} */ ([
      [[posix.join(dir, "no-such-codex")], dir],
      [["no-such-codex-akmon-xyz"], dir],
      [[process.execPath, "-e", "0"], posix.join(dir, "no-such-cwd")],
      [[""], dir],
    ])) {
      await assert.rejects(defaultRunner(command, cwd, 1), (error) => {
        assert.ok(error instanceof CodexProtocolError);
        assert.equal(error.kind, "unstartable");
        assert.ok(!error.message.includes("ENOENT") && !error.message.includes("No such file"));
        return true;
      });
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("defaultRunner: a non-executable file is unstartable", async () => {
  const dir = fs.realpathSync(fs.mkdtempSync(posix.join(os.tmpdir(), "akmon-codex-test-")));
  try {
    fs.writeFileSync(posix.join(dir, "codex"), "#!/bin/sh\n", { mode: 0o644 });
    await assert.rejects(defaultRunner([posix.join(dir, "codex")], dir, 1), { message: data.protocol_failures.unstartable });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("queryHooksList uses defaultRunner by default, end to end", async () => {
  const source = `
function onLine(_line, index) {
  if (index === 1) {
    const hook = { handlerType: "command", enabled: true, trustStatus: "untrusted", eventName: "preToolUse", matcher: "m", command: "c1" };
    process.stdout.write(JSON.stringify({ id: 2, result: { data: [{ cwd: process.cwd(), hooks: [hook], warnings: [], errors: [] }] } }) + "\\n");
  }
}
${READER}`;
  await withFakeCodex(source, async (dir) => {
    const hooks = await queryHooksList(data, ["codex", "app-server"], dir, { timeout: 5 });
    assert.deepEqual(hookTrustProblems(data, [["preToolUse", "m", "c1"]], hooks), { untrusted: ["c1"] });
  });
});
