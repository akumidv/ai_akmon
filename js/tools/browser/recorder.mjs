#!/usr/bin/env node
/**
 * The recorder: the detached process `akmon tool browser record start` launches, which outlives the Bash call
 * that started it. It holds the connection to Chrome (here, or through the CDP runner on Windows when Chrome is
 * a Windows program under WSL) and appends every event to the recording's `events.jsonl` as it happens, until it
 * is told to stop (`SIGTERM` from `record stop`) or Chrome goes away. It is not a verb of its own: it is started
 * with the path of its configuration file and writes nothing to stdout.
 *
 * The first event it writes is `start` once it records, or `error` when it could not begin, which is how
 * `record start` knows which; the last is `stop`.
 */

import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { realDeps } from "./ops.mjs";
import { eventsPath, fileSink } from "./record-store.mjs";
import { startRecording } from "./record-ops.mjs";
import { realStreamHost, streamFromWindows } from "./record-windows.mjs";

/**
 * What the `start` verb hands the recorder, as JSON in the recording's folder.
 * @typedef {object} RecorderConfig
 * @property {string} name the recording's name
 * @property {string} dir the recording's folder
 * @property {number} startedAtMs the clock base of every `t` (`record-store.mjs`)
 * @property {"here" | "windows"} side where the Chrome side runs
 * @property {import("./stream-protocol.mjs").RecordRequest} request what to record
 */

/**
 * What the recorder asks of the machine, replaced by a test.
 * @typedef {object} RecorderDeps
 * @property {() => number} now milliseconds since the epoch
 * @property {(request: import("./stream-protocol.mjs").RecordRequest, emit: import("./record-ops.mjs").Emit) => Promise<import("./record-ops.mjs").RecordingHandle>} start begin the Chrome side
 * @property {(handler: () => void) => void} onStop call `handler` when the recorder is told to stop
 */

/**
 * A configuration read from its text, validated: the boundary where the recorder's file enters.
 * @param {string} text
 * @returns {RecorderConfig}
 * @throws {Error} naming what is wrong
 */
export function decodeRecorderConfig(text) {
  /** @type {any} */
  const data = JSON.parse(text);
  if (
    typeof data !== "object" ||
    data === null ||
    typeof data.name !== "string" ||
    typeof data.dir !== "string" ||
    typeof data.startedAtMs !== "number" ||
    (data.side !== "here" && data.side !== "windows") ||
    typeof data.request !== "object" ||
    data.request === null
  ) {
    throw new Error("the recorder's configuration needs name, dir, startedAtMs, side and request");
  }
  return /** @type {RecorderConfig} */ (data);
}

/**
 * Record until told to stop or until Chrome goes away.
 * @param {RecorderConfig} config
 * @param {RecorderDeps} deps
 * @returns {Promise<number>} 0 when the recording ended as asked or because Chrome closed, 1 when it could not begin or failed
 */
export async function runRecorder(config, deps) {
  const sink = fileSink({ file: eventsPath(config.dir), startedAtMs: config.startedAtMs, now: deps.now });
  /** @type {import("./record-ops.mjs").RecordingHandle} */
  let handle;
  try {
    handle = await deps.start(config.request, (event, ago) => sink.append(event, ago));
  } catch (exc) {
    sink.append({ kind: "error", text: exc instanceof Error ? exc.message : String(exc) });
    return 1;
  }
  const { request } = config;
  sink.append({
    kind: "start",
    name: config.name,
    pages: handle.pages,
    page: request.page,
    allPages: request.allPages,
    bodies: request.bodies,
    maxBody: request.maxBody,
    side: config.side,
  });
  const told = new Promise((resolve) => deps.onStop(() => resolve(null)));
  const outcome = await Promise.race([handle.ended, told]);
  await handle.stop();
  const reason = outcome === null ? "stopped" : outcome.reason;
  sink.append({ kind: "stop", reason, ...(outcome?.error ? { text: outcome.error } : {}) });
  return reason === "error" ? 1 : 0;
}

/**
 * The real machine's dependencies for a configuration.
 * @param {RecorderConfig} config
 * @returns {RecorderDeps}
 */
export function realRecorderDeps(config) {
  return {
    now: () => Date.now(),
    start: (request, emit) =>
      config.side === "windows"
        ? streamFromWindows(request, realStreamHost(), emit)
        : startRecording(request, realDeps(), emit),
    onStop: (handler) => {
      process.once("SIGTERM", handler);
      process.once("SIGINT", handler);
    },
  };
}

/**
 * Run the recorder of the configuration file named in `argv`.
 * @param {string[]} argv the arguments after the script
 * @returns {Promise<number>}
 */
async function main(argv) {
  try {
    const config = decodeRecorderConfig(fs.readFileSync(String(argv[0]), "utf8"));
    return await runRecorder(config, realRecorderDeps(config));
  } catch (exc) {
    process.stderr.write(`recorder.mjs: ${exc instanceof Error ? exc.message : String(exc)}\n`);
    return 2;
  }
}

/**
 * Whether node was told to execute `invoked` as this very module.
 * @param {string} invoked `process.argv[1]`
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  // Every event is written with a synchronous call, so leaving at once loses nothing.
  process.exit(await main(process.argv.slice(2)));
}
