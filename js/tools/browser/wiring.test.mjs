import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import { BrowserError } from "./settings.mjs";
import { tempProject } from "./support.test.mjs";
import { LAUNCHER, launcherPath, mergeServer, serverEntry, SERVER_NAME, wiringOf } from "./wiring.mjs";

const ENTRY = serverEntry("${CLAUDE_PROJECT_DIR:-.}/node_modules/akmon/js/tools/browser/mcp.mjs");

test("the launcher path is under CLAUDE_PROJECT_DIR inside the project and absolute outside it", () => {
  assert.equal(
    launcherPath("/p", "/p/node_modules/akmon"),
    "${CLAUDE_PROJECT_DIR:-.}/node_modules/akmon/js/tools/browser/mcp.mjs",
  );
  assert.equal(launcherPath("/p", "/p/_aitna/akmon"), "${CLAUDE_PROJECT_DIR:-.}/_aitna/akmon/js/tools/browser/mcp.mjs");
  assert.equal(launcherPath("/p", "/usr/lib/akmon"), "/usr/lib/akmon/js/tools/browser/mcp.mjs");
  assert.deepEqual(ENTRY, {
    command: "node",
    args: ["${CLAUDE_PROJECT_DIR:-.}/node_modules/akmon/js/tools/browser/mcp.mjs"],
  });
});

test("no file: the server is added to a new one", () => {
  const merged = mergeServer(null, ENTRY);
  assert.equal(merged.change, "added");
  assert.deepEqual(JSON.parse(merged.text), { mcpServers: { [SERVER_NAME]: ENTRY } });
  assert.ok(merged.text.endsWith("\n"));
});

test("other servers and other keys are kept as they are", () => {
  const existing = JSON.stringify({ note: 1, mcpServers: { other: { command: "x", args: ["--a"], env: { K: "v" } } } });
  const merged = mergeServer(existing, ENTRY);
  assert.equal(merged.change, "added");
  assert.deepEqual(JSON.parse(merged.text), {
    note: 1,
    mcpServers: { other: { command: "x", args: ["--a"], env: { K: "v" } }, [SERVER_NAME]: ENTRY },
  });
});

test("merging twice changes nothing, byte for byte", () => {
  const first = mergeServer(null, ENTRY);
  const second = mergeServer(first.text, ENTRY);
  assert.equal(second.change, "unchanged");
  assert.equal(second.text, first.text);
  const hand = `{"mcpServers":{"${SERVER_NAME}":${JSON.stringify(ENTRY)}}}`;
  assert.equal(mergeServer(hand, ENTRY).text, hand, "a hand-formatted file is not rewritten");
});

test("an entry with the old bare relative spelling is updated in place to the new one", () => {
  const old = serverEntry("node_modules/akmon/js/tools/browser/mcp.mjs");
  const existing = JSON.stringify({ mcpServers: { other: { command: "x" }, [SERVER_NAME]: old } });
  const merged = mergeServer(existing, ENTRY);
  assert.equal(merged.change, "updated");
  const servers = JSON.parse(merged.text).mcpServers;
  assert.deepEqual(servers[SERVER_NAME], ENTRY);
  assert.deepEqual(servers.other, { command: "x" });
  assert.equal(mergeServer(merged.text, ENTRY).change, "unchanged", "the new spelling is the same entry");
});

test("a changed launcher updates the entry", () => {
  const first = mergeServer(null, ENTRY);
  const moved = mergeServer(first.text, serverEntry("_aitna/akmon/js/tools/browser/mcp.mjs"));
  assert.equal(moved.change, "updated");
  assert.deepEqual(JSON.parse(moved.text).mcpServers[SERVER_NAME].args, ["_aitna/akmon/js/tools/browser/mcp.mjs"]);
});

test("a file that does not parse or has the wrong shape is refused, never overwritten", () => {
  assert.throws(() => mergeServer("{nope", ENTRY), BrowserError);
  assert.throws(() => mergeServer("[]", ENTRY), BrowserError);
  assert.throws(() => mergeServer('{"mcpServers": []}', ENTRY), BrowserError);
});

test("status reads the wiring back: no file, no server, launcher missing, wired", () => {
  const { root, dispose } = tempProject();
  try {
    assert.equal(wiringOf(root).state, "not wired");
    fs.writeFileSync(posix.join(root, ".mcp.json"), JSON.stringify({ mcpServers: { other: {} } }));
    assert.match(wiringOf(root).why, /no akmon-browser server/);
    fs.writeFileSync(posix.join(root, ".mcp.json"), mergeServer(null, serverEntry(LAUNCHER)).text);
    assert.equal(wiringOf(root).state, "launcher missing");
    fs.mkdirSync(posix.dirname(posix.join(root, LAUNCHER)), { recursive: true });
    fs.writeFileSync(posix.join(root, LAUNCHER), "");
    assert.equal(wiringOf(root).state, "wired");
    fs.writeFileSync(posix.join(root, ".mcp.json"), mergeServer(null, serverEntry(launcherPath(root, root))).text);
    assert.equal(wiringOf(root).state, "wired", "the CLAUDE_PROJECT_DIR spelling resolves against the project root");
    fs.rmSync(posix.join(root, LAUNCHER));
    assert.equal(wiringOf(root).state, "launcher missing");
    fs.writeFileSync(posix.join(root, ".mcp.json"), "{nope");
    assert.equal(wiringOf(root).state, "not wired");
  } finally {
    dispose();
  }
});
