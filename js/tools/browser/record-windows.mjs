/**
 * The Linux side of a recording whose Chrome is a Windows program under WSL: it starts the CDP runner through
 * `cmd.exe /c node` in streaming mode (`stream-protocol.mjs`), writes the request, and hands each event line
 * the runner prints to `emit` as it arrives; the recorder stamps and appends it, nothing more, because the
 * runner redacted it on the Windows side already. It returns the same handle a recording on this side does
 * (`record-ops.mjs`), so the recorder treats both alike. A missing Windows `node` is one line naming it.
 */

import { spawn } from "node:child_process";

import { BrowserError } from "./settings.mjs";
import { decodeStreamMessage, encodeStreamRequest, LineBuffer, stopLine } from "./stream-protocol.mjs";
import { missingNodeLine, nodeMissing, realWindows } from "./windows.mjs";

/** How long the runner is given to finish after it is told to stop, in milliseconds. */
const _STOP_MS = 10_000;
/** How long the runner is given to say it is recording, in milliseconds: less than `record start` waits for the recorder. */
const _START_MS = 20_000;

/**
 * A program started with pipes on all three streams.
 * @typedef {object} RunnerProcess
 * @property {(text: string) => void} write
 * @property {() => void} end close its stdin
 * @property {() => void} kill
 * @property {(handler: (text: string) => void) => void} onStdout
 * @property {(handler: (text: string) => void) => void} onStderr
 * @property {(handler: (status: number | null, error: string | null) => void) => void} onExit
 */

/**
 * What a recording on Windows asks of the machine, replaced by a test.
 * @typedef {object} StreamHost
 * @property {(command: string, args: string[], how: {cwd: string}) => RunnerProcess} spawn
 * @property {(path: string) => string} toWindowsPath
 * @property {string} runnerPath the runner as a path on this side
 */

/**
 * The real machine: `spawn` for `cmd.exe`, `wslpath -w` for paths.
 * @returns {StreamHost}
 */
export function realStreamHost() {
  const windows = realWindows();
  return {
    spawn: (command, args, how) => {
      const child = spawn(command, args, { cwd: how.cwd, stdio: ["pipe", "pipe", "pipe"] });
      child.stdin.on("error", () => {
        // The runner ended before it read what was written: its exit says why.
      });
      return {
        write: (text) => void child.stdin.write(text),
        end: () => void child.stdin.end(),
        kill: () => void child.kill(),
        onStdout: (handler) => child.stdout.on("data", (chunk) => handler(chunk.toString("utf8"))),
        onStderr: (handler) => child.stderr.on("data", (chunk) => handler(chunk.toString("utf8"))),
        onExit: (handler) => {
          /** @type {string | null} */
          let error = null;
          child.on("error", (exc) => {
            error = exc.message;
          });
          child.on("close", (status) => handler(status, error));
        },
      };
    },
    toWindowsPath: windows.toWindowsPath,
    runnerPath: windows.runnerPath,
  };
}

/**
 * Start a recording in the CDP runner on Windows.
 * @param {import("./stream-protocol.mjs").RecordRequest} request
 * @param {StreamHost} host
 * @param {import("./record-ops.mjs").Emit} emit
 * @param {{stopMs?: number, startMs?: number}} [options] how long the runner may take to stop, and to say it is recording
 * @returns {Promise<import("./record-ops.mjs").RecordingHandle>} once the runner says it is recording
 * @throws {BrowserError} when Windows `node` is missing, the runner fails to start, cannot attach, or does not say it records in time
 */
export function streamFromWindows(request, host, emit, options = {}) {
  const child = host.spawn("cmd.exe", ["/c", "node", host.toWindowsPath(host.runnerPath)], { cwd: "/mnt/c" });
  const lines = new LineBuffer();
  let stderr = "";
  let ready = false;
  let finished = false;
  /** @type {(handle: import("./record-ops.mjs").RecordingHandle) => void} */
  let becameReady = () => {};
  /** @type {(error: BrowserError) => void} */
  let failedToStart = () => {};
  /** @type {(outcome: {reason: "closed" | "stopped" | "error", error: string | null}) => void} */
  let finish = () => {};
  const ended = new Promise((resolve) => {
    finish = (outcome) => {
      if (!finished) {
        finished = true;
        resolve(outcome);
      }
    };
  });
  const handle = {
    pages: /** @type {string[]} */ ([]),
    ended,
    stop: () => {
      child.write(stopLine());
      child.end();
      const timer = setTimeout(() => child.kill(), options.stopMs ?? _STOP_MS);
      return ended.then(() => clearTimeout(timer));
    },
  };
  const started = new Promise((resolve, reject) => {
    becameReady = resolve;
    failedToStart = reject;
  });
  // A runner that hangs before it is recording would leave `cmd.exe` and Windows `node` behind: closing its
  // stdin makes the runner exit (it reads end of input as "stop", also while it is still starting), and the
  // `cmd.exe` the Linux side holds is killed besides.
  const startMs = options.startMs ?? _START_MS;
  const startTimer = setTimeout(() => {
    if (!ready) {
      child.end();
      child.kill();
      failedToStart(new BrowserError(`the CDP runner on Windows did not begin recording within ${startMs / 1000} s`));
      finish({ reason: "error", error: "the CDP runner on Windows did not begin recording" });
    }
  }, startMs);
  /**
   * @param {string} line one line the runner printed
   */
  const onLine = (line) => {
    /** @type {import("./stream-protocol.mjs").StreamMessage} */
    let message;
    try {
      message = decodeStreamMessage(line);
    } catch {
      return;
    }
    if ("ready" in message) {
      ready = true;
      clearTimeout(startTimer);
      handle.pages = message.ready.pages;
      becameReady(handle);
    } else if ("ev" in message) {
      try {
        emit(message.ev, message.ago);
      } catch (exc) {
        finish({
          reason: "error",
          error: `could not write an event (${exc instanceof Error ? exc.message : String(exc)})`,
        });
        void handle.stop();
      }
    } else if ("error" in message) {
      if (ready) {
        finish({ reason: "error", error: message.error });
      } else {
        clearTimeout(startTimer);
        failedToStart(new BrowserError(message.error));
      }
    } else {
      finish(message.end);
    }
  };
  child.onStdout((text) => lines.push(text).forEach(onLine));
  child.onStderr((text) => {
    stderr += text;
  });
  child.onExit((status, error) => {
    clearTimeout(startTimer);
    if (!ready) {
      failedToStart(new BrowserError(_startFailure({ status, error, stderr })));
    }
    finish({ reason: "error", error: `the CDP runner on Windows exited (status ${status})` });
  });
  child.write(encodeStreamRequest(request));
  return /** @type {Promise<import("./record-ops.mjs").RecordingHandle>} */ (started);
}

/**
 * The one line for a runner that ended before it was recording.
 * @param {{status: number | null, error: string | null, stderr: string}} run
 * @returns {string}
 */
function _startFailure(run) {
  const result = { status: run.status, stdout: "", stderr: run.stderr, error: run.error };
  if (run.error !== null && run.status === null) {
    return `could not run the CDP runner through cmd.exe: ${run.error}`;
  }
  if (nodeMissing(result)) {
    return missingNodeLine(run.stderr);
  }
  return `the CDP runner on Windows failed: ${run.stderr.trim().split("\n")[0] || `exit status ${run.status}`}`;
}
