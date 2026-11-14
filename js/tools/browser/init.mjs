/**
 * `init`: the opt-in setup of the browser's MCP hands (ADR 0032/D04). Nothing else does it: `sync` never
 * touches `.mcp.json`. It merges one `akmon-browser` server into the project's `.mcp.json`, whose
 * command runs the launcher with `node` from the standard tree the project runs from, then looks for a
 * Chrome and names the next step.
 */

import fs from "node:fs";
import { posix } from "node:path";

import { chromeOf } from "./lifecycle.mjs";
import { BrowserError, ROOT_ENV } from "./settings.mjs";
import { launcherPath, mergeServer, serverEntry, SERVER_NAME } from "./wiring.mjs";

/**
 * @typedef {import("./context.mjs").Context} Context
 */

/**
 * The lines that say what the merge did.
 * @param {"added" | "updated" | "unchanged"} change
 * @param {string} launcher
 * @returns {string}
 */
function _changeLine(change, launcher) {
  if (change === "unchanged") {
    return `.mcp.json already carries the ${SERVER_NAME} server (node ${launcher}); nothing changed`;
  }
  return `.mcp.json: ${change} the ${SERVER_NAME} server (node ${launcher}); every other server is untouched`;
}

/**
 * `init`: register the MCP server, look for Chrome, say what comes next.
 * @param {Context} ctx
 * @param {{treeRoot: string}} where the standard tree the project runs from (`standardTreeRoot` of `sync`)
 * @returns {number} the exit code
 * @throws {BrowserError} when the project is named by `AKMON_BROWSER_ROOT`: it has no dev layer, and the
 *   registered server would not carry the variable, so the host would not find the same project
 */
export function initCommand(ctx, where) {
  if (ctx.project.devRoot === null) {
    throw new BrowserError(
      `init needs an akmon project: ${ROOT_ENV} names ${ctx.project.root}, which has no dev layer, and the MCP server the host starts would not carry ${ROOT_ENV}; unset it, or register the server by hand`,
    );
  }
  const launcher = launcherPath(ctx.project.root, where.treeRoot);
  const file = posix.join(ctx.project.root, ".mcp.json");
  const before = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
  const merged = mergeServer(before, serverEntry(launcher));
  if (merged.change !== "unchanged") {
    fs.writeFileSync(file, merged.text);
  }
  ctx.say(_changeLine(merged.change, launcher));
  const chrome = chromeOf(ctx);
  if (chrome === null) {
    ctx.say("no Chrome found: the next step is `akmon tool browser install` (it prints a plan first)");
  } else {
    ctx.say(`Chrome found (${chrome.source}): ${chrome.path}; start it with: akmon tool browser start`);
  }
  ctx.say(
    "Claude Code reads .mcp.json and attaches the server only when this project's Chrome runs: start it, then reconnect the server (/mcp).",
  );
  ctx.say(
    "Codex reads its MCP servers from its own config.toml, which init does not write: on Codex use the Bash verbs of `akmon tool browser`, which work everywhere, with or without the MCP server.",
  );
  return 0;
}
