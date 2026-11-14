import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import { createServer } from "node:net";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";

import { writeAttach } from "./attach.mjs";
import { refusalAnswer, serve, SERVER_PACKAGE, serverCommand, targetOf } from "./mcp.mjs";
import { tempProject } from "./support.test.mjs";

const MCP = fileURLToPath(new URL("./mcp.mjs", import.meta.url));

test("the server is the pinned package attached to the project's loopback port", () => {
  assert.match(SERVER_PACKAGE, /^chrome-devtools-mcp@\d+\.\d+\.\d+$/);
  assert.deepEqual(serverCommand(9312, false), {
    command: "npx",
    args: ["--prefer-offline", "-y", SERVER_PACKAGE, "--browser-url=http://127.0.0.1:9312", "--no-usage-statistics"],
    cwd: undefined,
  });
});

test("a Windows Chrome under WSL gets the server through cmd.exe, from /mnt/c", () => {
  const { command, args, cwd } = serverCommand(9312, true);
  assert.equal(command, "cmd.exe");
  assert.deepEqual(args.slice(0, 3), ["/c", "npx", "--prefer-offline"]);
  assert.equal(cwd, "/mnt/c");
});

test("the refusal answers the host's request by its id, and nothing that has none", () => {
  const answer = refusalAnswer('{"jsonrpc":"2.0","id":7,"method":"initialize"}', "why");
  assert.deepEqual(JSON.parse(answer ?? ""), { jsonrpc: "2.0", id: 7, error: { code: -32000, message: "why" } });
  assert.ok((answer ?? "").endsWith("\n"));
  assert.equal(refusalAnswer('{"jsonrpc":"2.0","method":"notifications/initialized"}', "why"), null);
  assert.equal(refusalAnswer("not json", "why"), null);
});

test("the server starts only for this project's Chrome, and nothing on the port is a refusal", async () => {
  /** @param {{refusal: string | null} | null} found */
  const run = async (found) => {
    /** @type {unknown[][]} */
    const calls = [];
    await serve(
      { mode: "own", port: 9312 },
      {
        check: async () => found,
        start: (port) => calls.push(["start", port]),
        refuse: (message) => calls.push(["refuse", message]),
        say: (line) => calls.push(["say", line]),
      },
    );
    return calls.filter(([kind]) => kind !== "say");
  };
  const none = await run(null);
  assert.equal(none.length, 1, "no Chrome: the server does not start");
  assert.equal(none[0][0], "refuse");
  assert.equal(
    none[0][1],
    "chrome-devtools MCP server not started: no Chrome on 127.0.0.1:9312 for this project: run `akmon tool browser start`, then reconnect the server (/mcp)",
  );
  assert.deepEqual(await run({ refusal: null }), [["start", 9312]]);
  const refused = await run({ refusal: "the Chrome on 127.0.0.1:9312 is another" });
  assert.equal(refused.length, 1);
  assert.equal(refused[0][0], "refuse");
  assert.match(
    String(refused[0][1]),
    /^chrome-devtools MCP server not started: the Chrome on 127\.0\.0\.1:9312 is another; then reconnect/,
  );
});

test("in attach mode the server starts on the attached endpoint and the ownership check is skipped", async () => {
  /** @type {string[][]} */
  const calls = [];
  await serve(
    { mode: "attached", port: 9333, browserURL: "http://127.0.0.1:9333", by: "playwright" },
    {
      check: async () => assert.fail("the ownership check is not made in attach mode"),
      start: (port) => calls.push(["start", String(port)]),
      refuse: () => assert.fail("nothing is refused in attach mode"),
      say: (line) => calls.push(["say", line]),
    },
  );
  assert.deepEqual(calls[1], ["start", "9333"]);
  assert.equal(calls[0][0], "say");
  assert.match(
    calls[0][1],
    /attach mode, http:\/\/127\.0\.0\.1:9333 \(written by playwright\); ownership check skipped$/,
  );
  assert.ok(serverCommand(9333, false).args.includes("--browser-url=http://127.0.0.1:9333"));
});

test("the own mode says so on stderr before it starts", async () => {
  /** @type {string[]} */
  const said = [];
  await serve(
    { mode: "own", port: 9312 },
    { check: async () => ({ refusal: null }), start: () => {}, refuse: () => {}, say: (line) => said.push(line) },
  );
  assert.equal(said.length, 1);
  assert.match(said[0], /own mode, the project's Chrome on 127\.0\.0\.1:9312/);
});

test("the launcher's target is the attached endpoint when attach.json stands, else the project's port", () => {
  const { root, dispose } = tempProject();
  try {
    const browserDir = posix.join(root, "_aitna", ".local", ".browser");
    const ctx = /** @type {any} */ ({ port: 9312, project: { browserDir } });
    assert.deepEqual(targetOf(ctx), { mode: "own", port: 9312 });
    writeAttach(
      {
        endpoint: "9333",
        browserURL: "http://127.0.0.1:9333",
        by: "user",
        browser: "Chrome/140",
        attached: new Date(0).toISOString(),
      },
      browserDir,
    );
    assert.deepEqual(targetOf(ctx), {
      mode: "attached",
      port: 9333,
      browserURL: "http://127.0.0.1:9333",
      by: "user",
    });
  } finally {
    dispose();
  }
});

/** @returns {Promise<number>} a free loopback port */
function freePort() {
  return new Promise((resolve) => {
    const server = createServer().listen(0, "127.0.0.1", () => {
      const address = /** @type {import("node:net").AddressInfo} */ (server.address());
      server.close(() => resolve(address.port));
    });
  });
}

/**
 * A stand-in Chrome: Chrome's flags on its command line, DevTools' version answer on `port`.
 * @param {number} port
 * @param {string} profile
 */
async function fakeChrome(port, profile) {
  const answer = `require('http').createServer((q, r) => r.end(JSON.stringify({ Browser: 'FakeChrome/1' }))).listen(${port}, '127.0.0.1')`;
  const child = spawn(
    process.execPath,
    ["-e", answer, "--", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`],
    { stdio: "ignore" },
  );
  for (let poll = 0; poll < 50; poll += 1) {
    try {
      if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) {
        return child;
      }
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  child.kill();
  throw new Error(`the stand-in Chrome did not answer on ${port}`);
}

test(
  "the launcher refuses another project's Chrome and one akmon did not start, as the answer to initialize",
  { skip: process.platform !== "linux" && "the process table is read from /proc" },
  async () => {
    const { root, dispose } = tempProject();
    try {
      for (const [profile, whose] of [
        [
          posix.join(root, "..", "globex", "_aitna", ".local", ".browser", "chrome-profile"),
          "the Chrome of project globex",
        ],
        [posix.join(root, "chrome-debug"), "a Chrome not started by akmon"],
      ]) {
        const port = await freePort();
        const chrome = await fakeChrome(port, posix.normalize(profile));
        try {
          /** @type {Record<string, string | undefined>} */
          const env = {
            ...process.env,
            CLAUDE_PROJECT_DIR: root,
            AKMON_BROWSER_PORT: String(port),
            AKMON_BROWSER_CHROME: process.execPath,
          };
          for (const name of ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"]) {
            delete env[name];
          }
          const initialize = { jsonrpc: "2.0", id: 0, method: "initialize", params: {} };
          const run = spawnSync(process.execPath, [MCP], {
            cwd: root,
            env,
            encoding: "utf8",
            input: `${JSON.stringify(initialize)}\n`,
            timeout: 60_000,
          });
          assert.equal(run.status, 1, run.stderr);
          const expected = `the Chrome on 127.0.0.1:${port} is ${whose}`;
          assert.ok(run.stderr.includes(expected), run.stderr);
          assert.ok(run.stderr.includes("akmon tool browser start"), run.stderr);
          const answer = JSON.parse(run.stdout.trim());
          assert.equal(answer.id, 0);
          assert.ok(answer.error.message.includes(expected));
        } finally {
          chrome.kill();
        }
      }
    } finally {
      dispose();
      fs.rmSync(posix.join(root, "..", "globex"), { recursive: true, force: true });
    }
  },
);
