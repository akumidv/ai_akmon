import { test } from "node:test";
import assert from "node:assert/strict";

import { encodeResponse } from "./protocol.mjs";
import { BrowserError } from "./settings.mjs";
import { runnerTimeoutMs, runOnWindows, windowsNodeLine, windowsNodeVersion } from "./windows.mjs";

/** @type {import("./protocol.mjs").Request} */
const REQUEST = {
  browserURL: "http://127.0.0.1:9582",
  page: null,
  redact: [],
  operations: [{ op: "eval", expression: "1" }],
};

/**
 * A fake Windows: records the program run and answers as given.
 * @param {Partial<import("./windows.mjs").RunResult>} result
 */
function fakeWindows(result) {
  /** @type {{command: string, args: string[], how: any}[]} */
  const runs = [];
  return {
    runs,
    windows: {
      run: async (/** @type {string} */ command, /** @type {string[]} */ args, /** @type {any} */ how) => {
        runs.push({ command, args, how });
        return { status: 0, stdout: "", stderr: "", error: null, ...result };
      },
      toWindowsPath: (/** @type {string} */ path) => `\\\\wsl.localhost\\Ubuntu${path.replaceAll("/", "\\")}`,
      runnerPath: "/home/u/akmon/js/tools/browser/cdp-runner.mjs",
    },
  };
}

test("the runner is run by Windows node through cmd.exe in /mnt/c with the request on stdin", async () => {
  /** @type {import("./protocol.mjs").Response} */
  const response = { results: [{ ok: true, value: { type: "number", value: 1 } }] };
  const { runs, windows } = fakeWindows({ stdout: encodeResponse(response) });
  assert.deepEqual(await runOnWindows(REQUEST, windows), response);
  assert.equal(runs[0].command, "cmd.exe");
  assert.deepEqual(runs[0].args, [
    "/c",
    "node",
    "\\\\wsl.localhost\\Ubuntu\\home\\u\\akmon\\js\\tools\\browser\\cdp-runner.mjs",
  ]);
  assert.equal(runs[0].how.cwd, "/mnt/c");
  assert.deepEqual(JSON.parse(runs[0].how.input), REQUEST);
});

test("the runner's time is what the operations wait for, and a margin", () => {
  assert.equal(runnerTimeoutMs(REQUEST), 60_000);
  assert.equal(
    runnerTimeoutMs({
      ...REQUEST,
      operations: [
        { op: "logs", until: null, seconds: 30 },
        { op: "net", seconds: 10, until: null, failed: false, bodies: false, maxBody: 1 },
      ],
    }),
    100_000,
  );
});

test("a Windows without node is one line naming it, however cmd.exe says so", async () => {
  for (const given of [
    { status: 9009, stderr: "'node' is not recognized as an internal or external command," },
    { status: 1, stderr: "'node' is not recognized as an internal or external command," },
    { status: 9009, stderr: "" },
  ]) {
    const { windows } = fakeWindows(given);
    await assert.rejects(
      runOnWindows(REQUEST, windows),
      (error) =>
        error instanceof BrowserError &&
        /^Windows node\.exe was not found .*install Node\.js 22/.test(error.message) &&
        !error.message.includes("\n"),
      JSON.stringify(given),
    );
  }
});

test("a runner that fails, an answer that is not one, and a cmd.exe that cannot run are one line each", async () => {
  await assert.rejects(
    runOnWindows(
      REQUEST,
      fakeWindows({ status: 1, stderr: "ReferenceError: WebSocket is not defined\n at x" }).windows,
    ),
    /the CDP runner on Windows failed: ReferenceError: WebSocket is not defined$/,
  );
  await assert.rejects(
    runOnWindows(REQUEST, fakeWindows({ stdout: "garbage" }).windows),
    /answered badly: the runner's answer is not JSON/,
  );
  await assert.rejects(
    runOnWindows(REQUEST, fakeWindows({ status: null, error: "spawn cmd.exe ENOENT" }).windows),
    /could not run the CDP runner through cmd\.exe: spawn cmd\.exe ENOENT/,
  );
});

test("the runner's own failure arrives as its response, not as an error here", async () => {
  const { windows } = fakeWindows({ stdout: encodeResponse({ error: 'no page matches --page "x"' }) });
  assert.deepEqual(await runOnWindows(REQUEST, windows), { error: 'no page matches --page "x"' });
});

test("the version of Windows node is read from `node -v`, and its words say what is missing or old", async () => {
  assert.equal(await windowsNodeVersion(fakeWindows({ stdout: "v24.18.1\r\n" }).windows), "v24.18.1");
  assert.equal(await windowsNodeVersion(fakeWindows({ status: 9009, stderr: "not recognized" }).windows), null);
  assert.match(windowsNodeLine("v24.18.1"), /^windows node: v24\.18\.1, which the inspection verbs use/);
  assert.match(windowsNodeLine("v20.1.0"), /older than 22/);
  assert.match(windowsNodeLine(null), /not found; .*Node\.js 22 or newer for Windows/);
});
