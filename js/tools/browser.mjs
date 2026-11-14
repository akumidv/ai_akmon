#!/usr/bin/env node
/**
 * `akmon tool browser`: a Chrome the user and the agent share, one per project (ADR 0032). The tool is
 * implemented once, here, in Node, under the ADR 0020 amendment to D01 for a tool that drives an
 * external application; the Python package's `tools/browser.py` only calls `node` on this file. It has
 * no npm runtime dependency.
 *
 * Verbs: `status`, `start`, `stop`, `restart`, `attach`, `detach`, `install`, `init`, the inspection verbs
 * `pages`, `snapshot`, `screenshot`, `eval`, `logs`, `net`, `selectors` (`browser/inspect.mjs`), the extension
 * bench `ext` (`browser/ext.mjs`) and `record` (`browser/record.mjs`, with the detached recorder `browser/recorder.mjs`). The MCP launcher the `init` verb
 * wires is `browser/mcp.mjs`, which is not a tool of its own, and `browser/cdp-runner.mjs` is the helper
 * the inspection verbs run on the Windows side for a Windows Chrome under WSL.
 *
 * Each verb acts on the project at or above the working directory, with its profile in
 * `<dev root>/.local/.browser/`; `AKMON_BROWSER_ROOT` names the project instead (a folder that is not an akmon
 * project: state in `<root>/.local/.browser/`, no `[browser]` table). Settings come from `[browser]` of `<dev root>/.akmon.toml`, each
 * overridden by `AKMON_BROWSER_CHROME`, `AKMON_BROWSER_PORT`, `AKMON_BROWSER_PROFILE` and
 * `AKMON_BROWSER_PROXY`; `[browser].extensions` (unpacked extensions to load, for which Chrome for Testing is
 * required) by `AKMON_BROWSER_EXTENSIONS`.
 */

import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { helpText, parseInvocation, UsageError } from "./browser/arguments.mjs";
import { attachCommand, detachCommand } from "./browser/attach.mjs";
import { buildContext } from "./browser/context.mjs";
import { realHost } from "./browser/host.mjs";
import { developerModeCommand, extCommand } from "./browser/ext.mjs";
import { initCommand } from "./browser/init.mjs";
import {
  evalCommand,
  logsCommand,
  netCommand,
  pagesCommand,
  screenshotCommand,
  selectorsCommand,
  snapshotCommand,
} from "./browser/inspect.mjs";
import { installCommand } from "./browser/install.mjs";
import { restartCommand, startCommand, statusCommand, stopCommand } from "./browser/lifecycle.mjs";
import { recordCommand } from "./browser/record.mjs";
import { BrowserError } from "./browser/settings.mjs";

/**
 * What follows a successful `start` for a project that configures extensions: developer mode on, and what the
 * Chrome loaded.
 * @param {import("./browser/context.mjs").Context} ctx
 * @param {number} code the exit code of the start
 * @returns {Promise<number>}
 */
async function _afterStart(ctx, code) {
  if (code !== 0 || ctx.settings.extensions.length === 0) {
    return code;
  }
  return developerModeCommand(ctx);
}

/**
 * Run the verb of a parsed invocation.
 * @param {import("./browser/context.mjs").Context} ctx
 * @param {import("./browser/arguments.mjs").Invocation} invocation
 * @returns {Promise<number>}
 */
async function _run(ctx, invocation) {
  const { options } = invocation;
  switch (invocation.verb) {
    case "status":
      return statusCommand(ctx, { json: options.json });
    case "start":
      return _afterStart(ctx, await startCommand(ctx, { url: options.url, headless: options.headless }));
    case "stop":
      return stopCommand(ctx);
    case "restart":
      return _afterStart(ctx, await restartCommand(ctx, { url: options.url, headless: options.headless }));
    case "attach":
      return attachCommand(ctx, { endpoint: String(options.endpoint) });
    case "detach":
      return detachCommand(ctx, { release: options.release });
    case "install":
      return installCommand(ctx, { yes: options.yes, forExtensions: options.forExtensions });
    case "init": {
      const { standardTreeRoot } = await import("../bin/sync.mjs");
      return initCommand(ctx, { treeRoot: standardTreeRoot(ctx.project.root) });
    }
    default:
      return _runInspection(ctx, invocation);
  }
}

/**
 * Run an inspection verb of a parsed invocation (`browser/inspect.mjs`).
 * @param {import("./browser/context.mjs").Context} ctx
 * @param {import("./browser/arguments.mjs").Invocation} invocation
 * @returns {Promise<number>}
 */
async function _runInspection(ctx, invocation) {
  const { options } = invocation;
  switch (invocation.verb) {
    case "pages":
      return pagesCommand(ctx, options);
    case "snapshot":
      return snapshotCommand(ctx, options);
    case "screenshot":
      return screenshotCommand(ctx, options);
    case "eval":
      return evalCommand(ctx, options);
    case "logs":
      return logsCommand(ctx, options);
    case "net":
      return netCommand(ctx, options);
    case "selectors":
      return selectorsCommand(ctx, options);
    case "ext":
      return extCommand(ctx, options);
    case "record":
      return recordCommand(ctx, options);
    default:
      process.stdout.write(helpText());
      return 0;
  }
}

/**
 * `akmon tool browser <verb> [options]`.
 * @param {string[]} [argv] the arguments after `browser` (default: the process's)
 * @returns {Promise<number>} The process exit code: 2 for a usage error, 1 for a refusal.
 */
export async function main(argv = process.argv.slice(2)) {
  try {
    const invocation = parseInvocation(argv);
    if (invocation.verb === "help") {
      process.stdout.write(helpText());
      return 0;
    }
    const env = process.env;
    const ctx = buildContext(process.cwd(), {
      env,
      host: realHost(env),
      say: (line) => process.stdout.write(`${line}\n`),
    });
    return await _run(ctx, invocation);
  } catch (exc) {
    if (exc instanceof UsageError) {
      process.stderr.write(`browser.mjs: error: ${exc.message}\n`);
      return 2;
    }
    if (exc instanceof BrowserError) {
      process.stderr.write(`akmon tool browser: ${exc.message}\n`);
      return 1;
    }
    throw exc;
  }
}

/**
 * Whether node was told to execute `invoked` as this very module (see `akmon/cli.mjs`).
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
  process.exitCode = await main();
}
