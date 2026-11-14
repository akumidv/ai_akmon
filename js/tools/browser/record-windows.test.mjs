import { test } from "node:test";
import assert from "node:assert/strict";

import { streamFromWindows } from "./record-windows.mjs";
import { decodeStreamRequest, encodeStreamMessage } from "./stream-protocol.mjs";

/** @type {import("./stream-protocol.mjs").RecordRequest} */
const REQUEST = {
  browserURL: "http://127.0.0.1:9582",
  page: null,
  allPages: false,
  bodies: false,
  maxBody: 4096,
  redact: [],
  binding: "__akmonRecord",
};

/**
 * A fake runner process the test drives, and the host that starts it.
 */
function fakeHost() {
  /** @type {string[]} */
  const written = [];
  const state = { ended: false, killed: false, command: /** @type {string[]} */ ([]), cwd: "" };
  /** @type {(text: string) => void} */
  let stdout = () => {};
  /** @type {(text: string) => void} */
  let stderr = () => {};
  /** @type {(status: number | null, error: string | null) => void} */
  let exit = () => {};
  /** @type {import("./record-windows.mjs").StreamHost} */
  const host = {
    spawn: (command, args, how) => {
      state.command = [command, ...args];
      state.cwd = how.cwd;
      return {
        write: (text) => void written.push(text),
        end: () => {
          state.ended = true;
        },
        kill: () => {
          state.killed = true;
        },
        onStdout: (handler) => {
          stdout = handler;
        },
        onStderr: (handler) => {
          stderr = handler;
        },
        onExit: (handler) => {
          exit = handler;
        },
      };
    },
    toWindowsPath: (path) => `\\\\wsl.localhost\\Ubuntu${path.replaceAll("/", "\\")}`,
    runnerPath: "/repo/js/tools/browser/cdp-runner.mjs",
  };
  return {
    host,
    written,
    state,
    out: (/** @type {import("./stream-protocol.mjs").StreamMessage} */ message) => stdout(encodeStreamMessage(message)),
    outText: (/** @type {string} */ text) => stdout(text),
    err: (/** @type {string} */ text) => stderr(text),
    exit: (/** @type {number | null} */ status, /** @type {string | null} */ error = null) => exit(status, error),
  };
}

test("it starts the runner through cmd.exe in /mnt/c, writes the request as the first line and keeps stdin open", async () => {
  const fake = fakeHost();
  const events = [];
  const started = streamFromWindows(REQUEST, fake.host, (event, ago) => events.push({ event, ago }));
  assert.deepEqual(fake.state.command.slice(0, 3), ["cmd.exe", "/c", "node"]);
  assert.match(fake.state.command[3], /^\\\\wsl\.localhost\\Ubuntu\\repo\\js\\tools\\browser\\cdp-runner\.mjs$/);
  assert.equal(fake.state.cwd, "/mnt/c");
  assert.deepEqual(decodeStreamRequest(fake.written[0].trim()), REQUEST);
  assert.equal(fake.state.ended, false);
  fake.out({ ready: { pages: ["p1"] } });
  const handle = await started;
  assert.deepEqual(handle.pages, ["p1"]);
});

test("events arrive as lines in any chunking and are handed over as they are, with how long ago they began", async () => {
  const fake = fakeHost();
  /** @type {{event: Record<string, unknown>, ago: number}[]} */
  const events = [];
  const started = streamFromWindows(REQUEST, fake.host, (event, ago = 0) => events.push({ event, ago }));
  fake.out({ ready: { pages: ["p1"] } });
  await started;
  const line = encodeStreamMessage({ ev: { kind: "net", page: "p1", url: "https://api.example/x" }, ago: 40 });
  fake.outText(line.slice(0, 10));
  fake.outText(`${line.slice(10)}${encodeStreamMessage({ ev: { kind: "click", page: "p1" }, ago: 0 })}`);
  fake.outText("noise that is not a message\n");
  assert.deepEqual(events, [
    { event: { kind: "net", page: "p1", url: "https://api.example/x" }, ago: 40 },
    { event: { kind: "click", page: "p1" }, ago: 0 },
  ]);
});

test("stop writes the stop line, closes stdin and waits for the runner's end message; a runner that hangs is killed", async () => {
  const fake = fakeHost();
  const started = streamFromWindows(REQUEST, fake.host, () => {}, { stopMs: 20 });
  fake.out({ ready: { pages: ["p1"] } });
  const handle = await started;
  const stopping = handle.stop();
  assert.deepEqual(JSON.parse(fake.written.at(-1) ?? ""), { stop: true });
  assert.equal(fake.state.ended, true);
  assert.equal(fake.state.killed, false);
  fake.out({ end: { reason: "stopped", error: null } });
  await stopping;
  assert.deepEqual(await handle.ended, { reason: "stopped", error: null });

  const hung = fakeHost();
  const second = streamFromWindows(REQUEST, hung.host, () => {}, { stopMs: 10 });
  hung.out({ ready: { pages: ["p1"] } });
  const stuck = await second;
  const waiting = stuck.stop();
  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.equal(hung.state.killed, true);
  hung.exit(null);
  await waiting;
});

test("the runner closing on its own (Chrome went away) ends the recording", async () => {
  const fake = fakeHost();
  const started = streamFromWindows(REQUEST, fake.host, () => {});
  fake.out({ ready: { pages: ["p1"] } });
  const handle = await started;
  fake.out({ end: { reason: "closed", error: null } });
  fake.exit(0);
  assert.deepEqual(await handle.ended, { reason: "closed", error: null });
});

test("a runner that cannot attach says why in one line", async () => {
  const fake = fakeHost();
  const started = streamFromWindows(REQUEST, fake.host, () => {});
  fake.out({ error: "the browser has no open page; open one in the window, then run the verb again" });
  await assert.rejects(started, /no open page/);
});

test("a Windows node that is missing is one line naming it, not a bare exit status", async () => {
  const fake = fakeHost();
  const started = streamFromWindows(REQUEST, fake.host, () => {});
  fake.err("'node' is not recognized as an internal or external command");
  fake.exit(9009);
  await assert.rejects(started, /Windows node\.exe was not found/);
  const failing = fakeHost();
  const other = streamFromWindows(REQUEST, failing.host, () => {});
  failing.err("boom\nmore");
  failing.exit(1);
  await assert.rejects(other, /the CDP runner on Windows failed: boom/);
  const missing = fakeHost();
  const none = streamFromWindows(REQUEST, missing.host, () => {});
  missing.exit(null, "spawn cmd.exe ENOENT");
  await assert.rejects(none, /could not run the CDP runner through cmd\.exe: spawn cmd\.exe ENOENT/);
});

test("an event the sink cannot write ends the recording as an error and tells the runner to stop", async () => {
  const fake = fakeHost();
  const started = streamFromWindows(REQUEST, fake.host, () => {
    throw new Error("disk full");
  });
  fake.out({ ready: { pages: ["p1"] } });
  const handle = await started;
  fake.out({ ev: { kind: "click" }, ago: 0 });
  const outcome = await handle.ended;
  assert.equal(outcome.reason, "error");
  assert.match(String(outcome.error), /disk full/);
  assert.deepEqual(JSON.parse(fake.written.at(-1) ?? ""), { stop: true });
});

test("a runner that never says it is recording is stopped at the start timeout, and the failure is one line", async () => {
  const fake = fakeHost();
  const started = streamFromWindows(REQUEST, fake.host, () => {}, { startMs: 20 });
  await assert.rejects(
    started,
    /^BrowserError: the CDP runner on Windows did not begin recording within 0\.02 s$|did not begin recording within/,
  );
  assert.equal(fake.state.ended, true, "stdin is closed, which makes the runner exit");
  assert.equal(fake.state.killed, true, "and the cmd.exe held on this side is killed");
});

test("a runner that is recording in time is neither stopped nor killed by the start timer", async () => {
  const fake = fakeHost();
  const started = streamFromWindows(REQUEST, fake.host, () => {}, { startMs: 30 });
  fake.out({ ready: { pages: ["p1"] } });
  await started;
  await new Promise((resolve) => setTimeout(resolve, 60));
  assert.deepEqual([fake.state.ended, fake.state.killed], [false, false]);
});
