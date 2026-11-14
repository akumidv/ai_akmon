import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { posix } from "node:path";

import { spawn } from "node:child_process";
import http from "node:http";
import { fileURLToPath } from "node:url";

import { encodeStreamRequest } from "./stream-protocol.mjs";

const HERE = posix.dirname(fileURLToPath(import.meta.url));

/**
 * The modules a module imports, as the text of its static imports names them.
 * @param {string} file
 * @returns {string[]}
 */
function importsOf(file) {
  const source = fs.readFileSync(posix.join(HERE, file), "utf8");
  return [...source.matchAll(/^import\s[^;]*?from\s+"([^"]+)";/gms)].map((match) => match[1]);
}

test("everything the CDP runner loads on the Windows side imports only Node and the runner's own modules", () => {
  const allowed = new Set([
    "cdp-runner.mjs",
    "cdp.mjs",
    "extension-cdp.mjs",
    "ops.mjs",
    "protocol.mjs",
    "record-events.mjs",
    "record-listener.mjs",
    "record-ops.mjs",
    "redact.mjs",
    "selectors.mjs",
    "stream-protocol.mjs",
    "targets.mjs",
  ]);
  /** @type {string[]} */
  const queue = ["cdp-runner.mjs"];
  const seen = new Set(queue);
  for (const file of queue) {
    for (const name of importsOf(file)) {
      if (name.startsWith("node:")) {
        continue;
      }
      const module = name.replace(/^\.\//, "");
      assert.ok(name.startsWith("./") && allowed.has(module), `${file} imports ${name}, which the runner may not load`);
      if (!seen.has(module)) {
        seen.add(module);
        queue.push(module);
      }
    }
  }
  assert.deepEqual([...seen].sort(), [...allowed].sort());
});

/**
 * Run the real runner as Windows `node` would, feeding it `input` on stdin, and collect what it prints.
 * @param {string} input what to write to stdin
 * @param {{keepOpen: boolean}} how `keepOpen`: leave stdin open, as a recorder does, until the runner exits on its own
 * @returns {Promise<{stdout: string, status: number | null}>}
 */
function runRunner(input, how) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [posix.join(HERE, "cdp-runner.mjs")], { stdio: ["pipe", "pipe", "ignore"] });
    let stdout = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`the runner did not end; it printed ${JSON.stringify(stdout)}`));
    }, 15_000);
    child.on("close", (status) => {
      clearTimeout(timer);
      resolve({ stdout, status });
    });
    if (how.keepOpen) {
      child.stdin.write(input);
    } else {
      child.stdin.end(input);
    }
  });
}

test("a streaming request keeps stdin open and answers with lines; when it cannot begin the last line says why", async () => {
  const request = encodeStreamRequest({
    browserURL: "http://127.0.0.1:1",
    page: null,
    allPages: false,
    bodies: false,
    maxBody: 1000,
    redact: [],
    binding: "__akmonRecord",
  });
  const { stdout, status } = await runRunner(request, { keepOpen: true });
  const lines = stdout.trim().split("\n");
  assert.equal(lines.length, 1);
  assert.match(JSON.parse(lines[0]).error, /nothing answers on http:\/\/127\.0\.0\.1:1/);
  assert.equal(status, 0);
});

test("a one-shot request still reads all of stdin and answers with one JSON response", async () => {
  const { stdout } = await runRunner(
    JSON.stringify({
      browserURL: "http://127.0.0.1:1",
      page: null,
      redact: [],
      operations: [{ op: "eval", expression: "1" }],
    }),
    { keepOpen: false },
  );
  assert.match(JSON.parse(stdout).error, /nothing answers/);
  const bad = await runRunner("not a request", { keepOpen: false });
  assert.match(JSON.parse(bad.stdout).error, /not JSON/);
});

test("a streaming runner that hangs while starting exits when stdin ends, before its own fetch gives up", async () => {
  // A DevTools port that accepts a request and never answers it.
  const silent = http.createServer(() => {});
  await new Promise((resolve) => silent.listen(0, "127.0.0.1", () => resolve(undefined)));
  const { port } = /** @type {import("node:net").AddressInfo} */ (silent.address());
  const request = encodeStreamRequest({
    browserURL: `http://127.0.0.1:${port}`,
    page: null,
    allPages: false,
    bodies: false,
    maxBody: 1000,
    redact: [],
    binding: "__akmonRecord",
  });
  try {
    const child = spawn(process.execPath, [posix.join(HERE, "cdp-runner.mjs")], { stdio: ["pipe", "pipe", "ignore"] });
    const exited = new Promise((resolve) => child.on("close", (status) => resolve(status)));
    child.stdin.write(request);
    await new Promise((resolve) => setTimeout(resolve, 500));
    const began = Date.now();
    child.stdin.end();
    const status = await Promise.race([
      exited,
      new Promise((resolve) => setTimeout(() => resolve("still running"), 3000)),
    ]);
    if (status === "still running") {
      child.kill();
    }
    assert.equal(status, 0);
    assert.ok(Date.now() - began < 3000);
  } finally {
    silent.closeAllConnections();
    silent.close();
  }
});
