#!/usr/bin/env node
/**
 * The CDP runner: the Chrome side of an inspection verb, run by Windows `node` when the project's Chrome
 * is a Windows program under WSL, because only a Windows process reaches its DevTools port. It reads one
 * JSON request (`protocol.mjs`) on stdin, runs it (`ops.mjs`) and writes one JSON response on stdout, and
 * writes nothing else there. `akmon tool browser` starts it as `cmd.exe /c node <this file>` and does the
 * rest on the Linux side: settings, formatting, files.
 *
 * A request whose first line is a streaming one (`stream-protocol.mjs`) is a recording instead: the runner keeps
 * stdin open, writes one JSON line per recorded event on stdout as it happens, and stops when stdin ends or a
 * `stop` line arrives (also while it is still starting, so a start that hangs ends with stdin) (`record.mjs` on the Linux side holds the other end). Nothing else is ever written to
 * stdout.
 *
 * It imports only `cdp.mjs`, `extension-cdp.mjs`, `ops.mjs`, `protocol.mjs`, `record-events.mjs`,
 * `record-listener.mjs`, `record-ops.mjs`, `redact.mjs`, `selectors.mjs`, `stream-protocol.mjs` and
 * `targets.mjs`, which import nothing but Node, so the Windows side loads it all from `\\wsl.localhost`.
 */

import { runRequest, realDeps } from "./ops.mjs";
import { decodeRequest, encodeResponse } from "./protocol.mjs";
import { startRecording } from "./record-ops.mjs";
import { decodeStreamRequest, encodeStreamMessage, isStreamRequest, LineBuffer } from "./stream-protocol.mjs";

/**
 * What the runner was asked: a request that ran to the end of stdin, or a streaming one that is still talking.
 * @typedef {{kind: "request", text: string} | {kind: "stream", line: string, lines: LineBuffer, ended: Promise<void>}} Asked
 */

/**
 * Read the first thing on stdin. A streaming request is one line that arrives while stdin stays open; any
 * other request is all of stdin up to its end.
 * @returns {Promise<Asked>}
 */
function readAsked() {
  return new Promise((resolve) => {
    let text = "";
    let settled = false;
    const lines = new LineBuffer();
    /** @type {() => void} */
    let closed = () => {};
    const ended = new Promise((done) => {
      closed = () => done(undefined);
    });
    process.stdin.setEncoding("utf8");
    /** @param {string[]} fresh lines that arrived on a stream that is open */
    const scan = (fresh) => {
      if (fresh.some((line) => line.includes('"stop"'))) {
        closed();
      }
    };
    process.stdin.on("data", (chunk) => {
      if (settled) {
        scan(lines.push(String(chunk)));
        return;
      }
      text += chunk;
      if (text.includes("\n")) {
        const first = text.slice(0, text.indexOf("\n")).replace(/\r$/, "");
        if (isStreamRequest(first)) {
          settled = true;
          resolve({ kind: "stream", line: first, lines, ended });
          scan(lines.push(text.slice(text.indexOf("\n") + 1)));
        }
      }
    });
    process.stdin.on("end", () => {
      closed();
      if (!settled) {
        settled = true;
        resolve({ kind: "request", text });
      }
    });
  });
}

/**
 * Run a one-shot request and answer on stdout.
 * @param {string} text the whole request
 * @returns {Promise<void>}
 */
async function answerRequest(text) {
  /** @type {import("./protocol.mjs").Response} */
  let response;
  try {
    response = await runRequest(decodeRequest(text), realDeps());
  } catch (exc) {
    response = { error: exc instanceof Error ? exc.message : String(exc) };
  }
  process.stdout.write(encodeResponse(response));
}

/**
 * Record: say `ready`, write each event as it happens, and stop when the other end says so.
 * @param {Extract<Asked, {kind: "stream"}>} asked
 * @returns {Promise<void>}
 */
async function answerStream(asked) {
  /** @type {import("./stream-protocol.mjs").StreamMessage} */
  let last;
  process.stdout.on("error", () => process.exit(1));
  try {
    const starting = startRecording(
      decodeStreamRequest(asked.line),
      realDeps(),
      (ev, ago = 0) => void process.stdout.write(encodeStreamMessage({ ev, ago })),
    );
    const handle = await Promise.race([starting, asked.ended.then(() => null)]);
    if (handle === null) {
      // The other end closed stdin while this was still starting: nobody reads an answer, and a start that
      // hangs would keep this process (and the `cmd.exe` above it) alive.
      process.exit(0);
    }
    process.stdout.write(encodeStreamMessage({ ready: { pages: handle.pages } }));
    const outcome = await Promise.race([handle.ended, asked.ended.then(() => null)]);
    await handle.stop();
    const reason = outcome === null ? "stopped" : outcome.reason;
    last = { end: { reason, error: outcome?.error ?? null } };
  } catch (exc) {
    last = { error: exc instanceof Error ? exc.message : String(exc) };
  }
  process.stdout.write(encodeStreamMessage(last));
}

/**
 * Run what stdin asks and answer on stdout.
 * @returns {Promise<void>}
 */
async function main() {
  const asked = await readAsked();
  if (asked.kind === "stream") {
    await answerStream(asked);
    process.stdin.destroy();
    return;
  }
  await answerRequest(asked.text);
}

await main();
