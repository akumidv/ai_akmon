/**
 * Running the CDP runner on the Windows side. Under WSL a Windows Chrome's DevTools port answers only
 * to Windows processes, so the inspection verbs hand their Chrome-side work to `cdp-runner.mjs` run by
 * Windows `node` (`cmd.exe /c node <runner>`, in `/mnt/c` as the MCP launcher does): a JSON request on its
 * stdin, a JSON response on its stdout. A missing Windows `node` is one line naming it.
 */

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { wslPath } from "./host.mjs";
import { decodeResponse, encodeRequest } from "./protocol.mjs";
import { BrowserError } from "./settings.mjs";

/** The exit status `cmd.exe` gives a command it cannot find. */
const _NOT_FOUND_STATUS = 9009;
/** How long the runner is given beyond the time a request itself asks for, in milliseconds. */
const _RUNNER_MARGIN_MS = 60_000;
/** How long `node -v` is given. */
const _VERSION_MS = 15_000;

/**
 * What a process run ended with.
 * @typedef {object} RunResult
 * @property {number | null} status the exit status; `null` when it could not run or was killed
 * @property {string} stdout
 * @property {string} stderr
 * @property {string | null} error why it could not run or was killed
 */

/**
 * How the real machine runs a program and converts a path.
 * @typedef {object} Windows
 * @property {(command: string, args: string[], how: {cwd: string, input: string, timeoutMs: number}) => Promise<RunResult>} run
 * @property {(path: string) => string} toWindowsPath
 * @property {string} runnerPath the runner as a path on this side
 */

/**
 * The real machine: `spawn` for `cmd.exe`, `wslpath -w` for paths.
 * @returns {Windows}
 */
export function realWindows() {
  return {
    run: (command, args, how) =>
      new Promise((resolve) => {
        const child = spawn(command, args, { cwd: how.cwd, stdio: ["pipe", "pipe", "pipe"] });
        /** @type {Buffer[]} */
        const out = [];
        /** @type {Buffer[]} */
        const err = [];
        /** @type {string | null} */
        let error = null;
        const timer = setTimeout(() => {
          error = `no answer within ${Math.round(how.timeoutMs / 1000)} s`;
          child.kill();
        }, how.timeoutMs);
        child.stdout.on("data", (chunk) => out.push(chunk));
        child.stderr.on("data", (chunk) => err.push(chunk));
        child.on("error", (exc) => {
          error = exc.message;
        });
        child.on("close", (status) => {
          clearTimeout(timer);
          resolve({
            status,
            stdout: Buffer.concat(out).toString("utf8"),
            stderr: Buffer.concat(err).toString("utf8"),
            error,
          });
        });
        child.stdin.on("error", () => {
          // The program ended before it read its input: its exit says why.
        });
        child.stdin.end(how.input);
      }),
    toWindowsPath: (path) => wslPath(path, "windows"),
    runnerPath: fileURLToPath(new URL("./cdp-runner.mjs", import.meta.url)),
  };
}

/**
 * Whether a finished run says Windows `node` is not there.
 * @param {RunResult} result
 * @returns {boolean}
 */
export function nodeMissing(result) {
  return result.status === _NOT_FOUND_STATUS || /not recognized|cannot find the (file|path)/i.test(result.stderr);
}

/**
 * The one line for a Windows `node` that is missing.
 * @param {string} detail what `cmd.exe` said, or why it could not run
 * @returns {string}
 */
export function missingNodeLine(detail) {
  return (
    "Windows node.exe was not found (cmd.exe /c node: " +
    `${detail.trim().split("\n")[0] || "no answer"}); the inspection verbs reach a Windows Chrome through it, ` +
    "so install Node.js 22 or newer for Windows"
  );
}

/**
 * The version of Windows `node`, or `null` when there is none.
 * @param {Windows} windows
 * @returns {Promise<string | null>}
 */
export async function windowsNodeVersion(windows) {
  const result = await windows.run("cmd.exe", ["/c", "node", "-v"], {
    cwd: "/mnt/c",
    input: "",
    timeoutMs: _VERSION_MS,
  });
  const version = result.stdout.trim().split(/\s+/)[0];
  return result.status === 0 && /^v\d+/.test(version) ? version : null;
}

/**
 * The words `status` reports for Windows `node`: the version, or what is missing.
 * @param {string | null} version from `windowsNodeVersion`
 * @returns {string}
 */
export function windowsNodeLine(version) {
  if (version === null) {
    return "windows node: not found; the inspection verbs (pages, snapshot, screenshot, eval, logs, net) need Node.js 22 or newer for Windows to reach this Windows Chrome";
  }
  const major = Number(version.slice(1).split(".")[0]);
  return major >= 22
    ? `windows node: ${version}, which the inspection verbs use to reach this Windows Chrome`
    : `windows node: ${version} is older than 22; the inspection verbs need Node.js 22 or newer for Windows`;
}

/**
 * How long the runner may take for a request: what its operations wait for, and a margin.
 * @param {import("./protocol.mjs").Request} request
 * @returns {number} milliseconds
 */
export function runnerTimeoutMs(request) {
  const waits = request.operations.map((spec) => (spec.op === "logs" || spec.op === "net" ? spec.seconds * 1000 : 0));
  return waits.reduce((sum, wait) => sum + wait, 0) + _RUNNER_MARGIN_MS;
}

/**
 * Run a request in the CDP runner on the Windows side.
 * @param {import("./protocol.mjs").Request} request
 * @param {Windows} [windows] the machine; the real one by default
 * @returns {Promise<import("./protocol.mjs").Response>}
 * @throws {BrowserError} when Windows `node` is missing, the runner fails, or its answer is not valid
 */
export async function runOnWindows(request, windows = realWindows()) {
  const result = await windows.run("cmd.exe", ["/c", "node", windows.toWindowsPath(windows.runnerPath)], {
    cwd: "/mnt/c",
    input: encodeRequest(request),
    timeoutMs: runnerTimeoutMs(request),
  });
  if (result.stdout.trim() !== "") {
    try {
      return decodeResponse(result.stdout);
    } catch (exc) {
      throw new BrowserError(
        `the CDP runner on Windows answered badly: ${exc instanceof Error ? exc.message : String(exc)}`,
      );
    }
  }
  if (result.error !== null && result.status === null) {
    throw new BrowserError(`could not run the CDP runner through cmd.exe: ${result.error}`);
  }
  if (nodeMissing(result)) {
    throw new BrowserError(missingNodeLine(result.stderr));
  }
  const reason = result.stderr.trim().split("\n")[0] || `exit status ${result.status}`;
  throw new BrowserError(`the CDP runner on Windows failed: ${reason}`);
}
