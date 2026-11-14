#!/usr/bin/env node
/**
 * The launcher of the `chrome-devtools-mcp` server (ADR 0032/D03), the command `.mcp.json` names after
 * `akmon tool browser init`. It is not a registered tool: the host runs it with `node`.
 *
 * The server attaches to the project's Chrome, so it has to run on the same side as Chrome: with a
 * Windows Chrome under WSL only a Windows process reaches its loopback DevTools port, so the server is
 * started through `cmd.exe`; everywhere else it runs here. Before it starts, the Chrome answering on the
 * port is checked the way `start` checks it: a Chrome that is another project's, or that akmon did not
 * start, is refused and the server never starts. The refusal goes to stderr and, as a JSON-RPC error,
 * answers the host's first request (`initialize`), so the host shows why the server is missing; then the
 * process exits 1. With no Chrome on the port it refuses the same way: a Chrome taking the port after the
 * server started would be driven without the check, so the user runs `start` first and then reconnects (/mcp).
 *
 * In attach mode (`attach.json`, ADR 0032/D05) the server attaches to the endpoint the user named
 * instead, with no ownership check: naming it was the explicit route. Either way one line on stderr
 * says which mode the launcher started in.
 */

import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { readAttach } from "./attach.mjs";
import { windowsSide } from "./chrome.mjs";
import { buildContext } from "./context.mjs";
import { answersHere } from "./devtools.mjs";
import { realHost } from "./host.mjs";
import { chromeOf, portState } from "./lifecycle.mjs";

/**
 * The pinned server, from npx's cache: `@latest` asks the registry on every start, which through
 * `cmd.exe` and a proxy outran the host's start timeout.
 */
export const SERVER_PACKAGE = "chrome-devtools-mcp@1.10.1";

/** How long a refusal waits for the host's first request before it exits without answering it. */
const _REFUSAL_WAIT_MS = 10_000;

/**
 * How to run the server attached to `port`.
 * @param {number} port
 * @param {boolean} windowsChrome the Chrome is a Windows program under WSL
 * @returns {{command: string, args: string[], cwd: string | undefined}}
 */
export function serverCommand(port, windowsChrome) {
  const server = [
    "--prefer-offline",
    "-y",
    SERVER_PACKAGE,
    `--browser-url=http://127.0.0.1:${port}`,
    "--no-usage-statistics",
  ];
  return windowsChrome
    ? { command: "cmd.exe", args: ["/c", "npx", ...server], cwd: "/mnt/c" }
    : { command: "npx", args: server, cwd: undefined };
}

/**
 * The JSON-RPC error that answers the host's first request with the refusal, or `null` when the
 * line is not a request with an id.
 * @param {string} line the first line the host sent
 * @param {string} message the refusal
 * @returns {string | null}
 */
export function refusalAnswer(line, message) {
  let id = null;
  try {
    id = JSON.parse(line).id ?? null;
  } catch {
    // Not JSON-RPC: nothing to answer.
  }
  return id === null ? null : `${JSON.stringify({ jsonrpc: "2.0", id, error: { code: -32000, message } })}\n`;
}

/**
 * Refuse over stdio, before any tool is announced: the message to stderr, then as the error answering
 * the host's first request, then exit 1.
 * @param {string} message
 */
export function refuseOverStdio(message) {
  process.stderr.write(`${message}\n`);
  const done = () => process.exit(1);
  if (process.stdin.isTTY) {
    done();
    return;
  }
  let received = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    received += chunk;
    const end = received.indexOf("\n");
    if (end < 0) {
      return;
    }
    const answer = refusalAnswer(received.slice(0, end), message);
    if (answer === null) {
      done();
      return;
    }
    process.stdout.write(answer, done);
  });
  process.stdin.on("end", done);
  setTimeout(done, _REFUSAL_WAIT_MS);
}

/**
 * Start the server attached to `port`; stdio passes straight through.
 * @param {number} port
 * @param {boolean} windowsChrome
 */
export function startServer(port, windowsChrome) {
  const { command, args, cwd } = serverCommand(port, windowsChrome);
  const child = spawn(command, args, { stdio: "inherit", cwd });
  child.on("error", (error) => {
    process.stderr.write(`chrome-devtools MCP server not started: ${error.message}\n`);
    process.exit(1);
  });
  child.on("exit", (code) => process.exit(code ?? 1));
  for (const signal of /** @type {const} */ (["SIGINT", "SIGTERM"])) {
    process.on(signal, () => child.kill(signal));
  }
}

/**
 * What the server attaches to: the project's own Chrome on its port, or the endpoint of an attach.
 * @typedef {{mode: "own", port: number} | {mode: "attached", port: number, browserURL: string, by: string}} Target
 */

/**
 * The target of a launch: the attached endpoint when the project is attached, else its own port.
 * @param {import("./context.mjs").Context} ctx
 * @returns {Target}
 * @throws {import("./settings.mjs").BrowserError} when `attach.json` is not valid
 */
export function targetOf(ctx) {
  const attachment = readAttach(ctx.project.browserDir);
  if (attachment === null) {
    return { mode: "own", port: ctx.port };
  }
  const port = Number(new URL(attachment.browserURL).port);
  return { mode: "attached", port, browserURL: attachment.browserURL, by: attachment.by };
}

/**
 * Serve the MCP server for a target. In attach mode it starts at once, on the attached endpoint, with no
 * ownership check. For the project's own Chrome on `port` it starts only when the Chrome answering there
 * is the project's: with nothing on the port, or another Chrome, it refuses, because a Chrome that takes
 * the port later would be driven without the ownership check.
 * @param {Target} target
 * @param {{check: (port: number) => Promise<{refusal: string | null} | null>, start: (port: number) => void, refuse: (message: string) => void, say: (line: string) => void}} how
 *   `check` asks who answers, `start` runs the server, `refuse` refuses over stdio, `say` writes a line to stderr
 * @returns {Promise<void>}
 */
export async function serve(target, how) {
  const { port } = target;
  if (target.mode === "attached") {
    how.say(
      `akmon-browser MCP launcher: attach mode, ${target.browserURL} (written by ${target.by}); ownership check skipped`,
    );
    how.start(port);
    return;
  }
  how.say(`akmon-browser MCP launcher: own mode, the project's Chrome on 127.0.0.1:${port}`);
  const found = await how.check(port);
  if (found === null) {
    how.refuse(
      `chrome-devtools MCP server not started: no Chrome on 127.0.0.1:${port} for this project: run \`akmon tool browser start\`, then reconnect the server (/mcp)`,
    );
    return;
  }
  if (found.refusal !== null) {
    how.refuse(
      `chrome-devtools MCP server not started: ${found.refusal}; then reconnect the server (/mcp) or restart the session`,
    );
    return;
  }
  how.start(port);
}

/**
 * Whether the server must run on the Windows side to reach its Chrome: the project's own Chrome is
 * a Windows program; an attached one is, under WSL, when only Windows reaches its port.
 * @param {import("./context.mjs").Context} ctx
 * @param {Target} target
 * @returns {Promise<boolean>}
 */
async function _windowsChrome(ctx, target) {
  if (target.mode === "attached") {
    return ctx.host.isWsl && !(await answersHere(target.port));
  }
  try {
    const chrome = chromeOf(ctx);
    return chrome !== null && windowsSide(ctx.host, chrome.path);
  } catch {
    // No usable Chrome: the server starts here and reports it when a tool is used.
    return false;
  }
}

/**
 * Run the launcher for the project the host started it in.
 * @param {Record<string, string | undefined>} env
 * @returns {Promise<void>}
 */
export async function main(env = process.env) {
  const ctx = buildContext(env["CLAUDE_PROJECT_DIR"] ?? process.cwd(), {
    env,
    host: realHost(env),
    say: (line) => process.stderr.write(`${line}\n`),
  });
  const target = targetOf(ctx);
  const windowsChrome = await _windowsChrome(ctx, target);
  await serve(target, {
    check: () => portState(ctx),
    start: (port) => startServer(port, windowsChrome),
    refuse: refuseOverStdio,
    say: ctx.say,
  });
}

/**
 * Whether node was told to execute `invoked` as this very module.
 * @param {string} invoked `process.argv[1]`, the path node was given
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
  main().catch((error) => {
    process.stderr.write(`chrome-devtools MCP server not started: ${error.message}\n`);
    process.exit(1);
  });
}
