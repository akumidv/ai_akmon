/**
 * The project's `.mcp.json` and the `akmon-browser` server in it (ADR 0032/D03, D04). Nothing writes
 * it by default: `akmon tool browser init` merges the one server in, keeps every other server as it
 * is, and says what changed; `status` reads the same file back.
 */

import fs from "node:fs";
import { posix } from "node:path";

import { BrowserError } from "./settings.mjs";

/** The key of the server in `mcpServers`. */
export const SERVER_NAME = "akmon-browser";

/**
 * How a project-relative launcher path is spelled in `.mcp.json`: the host sets `CLAUDE_PROJECT_DIR` in
 * a project MCP server's environment, but the server's working directory is not documented, so a bare
 * relative path may not resolve.
 */
const _PROJECT_DIR = "${CLAUDE_PROJECT_DIR:-.}";

/** Where the launcher sits under the standard tree. */
export const LAUNCHER = "js/tools/browser/mcp.mjs";

/**
 * One server of `.mcp.json`.
 * @typedef {object} McpServer
 * @property {string} command
 * @property {string[]} args
 */

/**
 * The server entry that runs the launcher with `node`. `launcher` is the launcher's path as the host
 * will resolve it: project-root-relative when the standard tree is inside the project, absolute otherwise.
 * @param {string} launcher
 * @returns {McpServer}
 */
export function serverEntry(launcher) {
  return { command: "node", args: [launcher] };
}

/**
 * The launcher's path for a project: the standard tree's launcher as `${CLAUDE_PROJECT_DIR:-.}/<path
 * relative to the project root>` when it is inside it (so the committed file holds no machine-specific
 * path), absolute otherwise.
 * @param {string} projectRoot
 * @param {string} treeRoot the standard tree the project runs from
 * @returns {string}
 */
export function launcherPath(projectRoot, treeRoot) {
  const relative = posix.relative(projectRoot, posix.join(treeRoot, LAUNCHER));
  return relative.startsWith("..") ? posix.join(treeRoot, LAUNCHER) : `${_PROJECT_DIR}/${relative}`;
}

/**
 * The parsed `.mcp.json` text: an object, or a refusal naming what is wrong, because a file this tool
 * could not read is a file it must not overwrite.
 * @param {string} text
 * @returns {Record<string, unknown>}
 * @throws {BrowserError}
 */
function _parseMcp(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch (exc) {
    const detail = exc instanceof Error ? exc.message.split("\n")[0] : String(exc);
    throw new BrowserError(`.mcp.json does not parse (${detail}); fix it, then run init again`);
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new BrowserError(".mcp.json is not a JSON object; fix it, then run init again");
  }
  return data;
}

/**
 * The `mcpServers` table of a parsed `.mcp.json`, or a refusal when it is something else.
 * @param {Record<string, unknown>} data
 * @returns {Record<string, unknown>}
 * @throws {BrowserError}
 */
function _servers(data) {
  const servers = data["mcpServers"];
  if (servers === undefined) {
    return {};
  }
  if (typeof servers !== "object" || servers === null || Array.isArray(servers)) {
    throw new BrowserError(".mcp.json: mcpServers is not an object; fix it, then run init again");
  }
  return /** @type {Record<string, unknown>} */ (servers);
}

/**
 * `.mcp.json` text with the `akmon-browser` server merged in.
 * @typedef {object} Merged
 * @property {string} text the file's new content
 * @property {"added" | "updated" | "unchanged"} change
 */

/**
 * Merge the `akmon-browser` server into the text of a `.mcp.json` (`null` when there is no file):
 * every other server and every other key stays as it is, and merging twice changes nothing.
 * @param {string | null} text
 * @param {McpServer} entry
 * @returns {Merged}
 * @throws {BrowserError} when the file does not parse or has no object where one belongs
 */
export function mergeServer(text, entry) {
  const data = text === null ? {} : _parseMcp(text);
  const servers = _servers(data);
  const before = servers[SERVER_NAME];
  const same = JSON.stringify(before) === JSON.stringify(entry);
  const merged = { ...data, mcpServers: { ...servers, [SERVER_NAME]: entry } };
  const rendered = `${JSON.stringify(merged, null, 2)}\n`;
  if (same) {
    return { text: text ?? rendered, change: "unchanged" };
  }
  return { text: rendered, change: before === undefined ? "added" : "updated" };
}

/**
 * What `.mcp.json` says about the browser, for `status`.
 * @typedef {object} Wiring
 * @property {"wired" | "launcher missing" | "not wired"} state
 * @property {string} why
 */

/**
 * The state of the project's `.mcp.json` as far as the browser goes: the file, the server and the
 * launcher it names. The tool cannot see the host's live tool list, so it says what is wired, never
 * what the host attached.
 * @param {string} projectRoot
 * @returns {Wiring}
 */
export function wiringOf(projectRoot) {
  const file = posix.join(projectRoot, ".mcp.json");
  if (!fs.existsSync(file)) {
    return { state: "not wired", why: "no .mcp.json in the project" };
  }
  let servers;
  try {
    servers = _servers(_parseMcp(fs.readFileSync(file, "utf8")));
  } catch (exc) {
    return { state: "not wired", why: exc instanceof Error ? exc.message : String(exc) };
  }
  const server = /** @type {Partial<McpServer> | undefined} */ (servers[SERVER_NAME]);
  if (server === undefined) {
    return { state: "not wired", why: `no ${SERVER_NAME} server in .mcp.json` };
  }
  const launcher = (server.args ?? []).find((arg) => typeof arg === "string" && arg.endsWith(LAUNCHER));
  if (launcher === undefined) {
    return { state: "not wired", why: `the ${SERVER_NAME} server names no launcher (${LAUNCHER})` };
  }
  const bare = launcher.startsWith(`${_PROJECT_DIR}/`) ? launcher.slice(_PROJECT_DIR.length + 1) : launcher;
  if (!fs.existsSync(posix.resolve(projectRoot, bare))) {
    return { state: "launcher missing", why: `the launcher ${launcher} does not exist` };
  }
  return { state: "wired", why: `the launcher ${launcher} is there` };
}
