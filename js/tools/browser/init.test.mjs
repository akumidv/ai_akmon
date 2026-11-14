import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import { buildContext } from "./context.mjs";
import { initCommand } from "./init.mjs";
import { BrowserError } from "./settings.mjs";
import { fakeHost, tempProject } from "./support.test.mjs";

/** @param {string} root @param {string[]} said */
const contextOf = (root, said, host = fakeHost()) =>
  buildContext(root, { env: {}, host, say: (line) => said.push(line) });

test("init writes .mcp.json once, keeps other servers, and a second run changes nothing", () => {
  const { root, dispose } = tempProject();
  try {
    fs.writeFileSync(posix.join(root, ".mcp.json"), JSON.stringify({ mcpServers: { other: { command: "x" } } }));
    const tree = posix.join(root, "node_modules", "akmon");
    const said = /** @type {string[]} */ ([]);
    assert.equal(initCommand(contextOf(root, said), { treeRoot: tree }), 0);
    const written = JSON.parse(fs.readFileSync(posix.join(root, ".mcp.json"), "utf8"));
    assert.deepEqual(written.mcpServers["akmon-browser"], {
      command: "node",
      args: ["${CLAUDE_PROJECT_DIR:-.}/node_modules/akmon/js/tools/browser/mcp.mjs"],
    });
    assert.deepEqual(written.mcpServers.other, { command: "x" });
    assert.ok(said.some((line) => line.includes("added the akmon-browser server")));
    assert.ok(
      said.some((line) => line.includes("akmon tool browser install")),
      "no Chrome: the next step is install",
    );
    assert.ok(said.some((line) => line.includes("Codex reads its MCP servers from its own config.toml")));
    assert.ok(said.some((line) => line.includes("Bash verbs")));

    const before = fs.readFileSync(posix.join(root, ".mcp.json"), "utf8");
    const again = /** @type {string[]} */ ([]);
    initCommand(contextOf(root, again), { treeRoot: tree });
    assert.equal(fs.readFileSync(posix.join(root, ".mcp.json"), "utf8"), before);
    assert.ok(again.some((line) => line.includes("nothing changed")));
  } finally {
    dispose();
  }
});

test("init with a Chrome found names start, not install", () => {
  const { root, dispose } = tempProject();
  try {
    const said = /** @type {string[]} */ ([]);
    initCommand(contextOf(root, said, fakeHost({ files: ["/opt/google/chrome/chrome"] })), { treeRoot: root });
    assert.ok(said.some((line) => line.includes("Chrome found (system)")));
    assert.ok(!said.some((line) => line.includes("browser install")));
  } finally {
    dispose();
  }
});

test("init refuses a project named by AKMON_BROWSER_ROOT, which has no dev layer", () => {
  const { root, dispose } = tempProject();
  try {
    const context = buildContext("/", { env: { AKMON_BROWSER_ROOT: root }, host: fakeHost(), say: () => {} });
    assert.throws(
      () => initCommand(context, { treeRoot: root }),
      (error) => error instanceof BrowserError && error.message.includes("AKMON_BROWSER_ROOT"),
    );
    assert.equal(fs.existsSync(posix.join(root, ".mcp.json")), false);
  } finally {
    dispose();
  }
});
