/**
 * Attach mode (ADR 0032/D05): a Chrome the project did not start (an end-to-end run's, the user's) is
 * used only through an explicit `attach` to an endpoint the user names or an endpoint file the run
 * wrote, never because a port happens to answer. `attach` records the endpoint in
 * `<browser dir>/attach.json`; while it stands, the verbs that would start, stop or restart a Chrome
 * refuse, `status` reports the attached one, and the MCP launcher attaches to it. The agent never
 * closes the window or the page of an attached browser and never signs in to it; `detach` only
 * forgets the endpoint, and `detach --release` also deletes the endpoint file, which is the signal a
 * test run that holds its page open for the agent waits on.
 */

import fs from "node:fs";
import { posix } from "node:path";

import { answersHere, devtoolsJson } from "./devtools.mjs";
import { BrowserError, extensionsProblemLine, readTextOrNull } from "./settings.mjs";
import { pageTabs } from "./targets.mjs";
import { wiringOf } from "./wiring.mjs";
import { realWindows, windowsNodeLine, windowsNodeVersion } from "./windows.mjs";

/** The record of the attach, beside `launch.json`. */
const _ATTACH_FILE = "attach.json";

/** The hosts an endpoint may name: DevTools is loopback only, and so is every attach. */
const _LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost"]);

/**
 * What an endpoint file holds: the JSON a test run writes once its browser listens.
 * @typedef {object} EndpointFile
 * @property {string} browserURL `http://127.0.0.1:<port>`
 * @property {string} by who wrote it, for the report (`playwright`)
 * @property {number} [pid] the writer's process, for the report
 * @property {string} [release] the path of the file itself, which `detach --release` deletes
 */

/**
 * An endpoint the user named, resolved.
 * @typedef {object} ResolvedEndpoint
 * @property {string} endpoint what the user named, as given
 * @property {string} browserURL the loopback URL that is probed and handed to the MCP server
 * @property {number} port
 * @property {string} by
 * @property {string | null} file the endpoint file it came from, as an absolute path
 */

/**
 * What `attach.json` records.
 * @typedef {object} Attachment
 * @property {string} endpoint what the user named, as given
 * @property {string} browserURL
 * @property {string} by who wrote the endpoint (`user` for one the user named directly)
 * @property {string} [file] the endpoint file it came from, absent for a URL or a port
 * @property {string} browser the Chrome's version string when it was attached
 * @property {string} attached ISO time
 */

/**
 * @typedef {import("./context.mjs").Context} Context
 */

/**
 * A DevTools answer for a path, from the machine side the Chrome is reached from.
 * @typedef {(port: number, path?: string) => Promise<any>} Probe
 */

/**
 * The loopback `http://127.0.0.1:<port>` of an `http://` or `ws://` DevTools URL (`localhost` is the same).
 * @param {string} text
 * @returns {{browserURL: string, port: number}}
 * @throws {BrowserError} for anything that is not a loopback `http://` or `ws://` URL with a port
 */
export function loopbackBrowserUrl(text) {
  let url;
  try {
    url = new URL(text);
  } catch {
    throw new BrowserError(`attach: ${JSON.stringify(text)} is not a URL`);
  }
  if (url.protocol !== "http:" && url.protocol !== "ws:") {
    throw new BrowserError(`attach: ${JSON.stringify(text)} is not an http:// or ws:// DevTools URL`);
  }
  if (!_LOOPBACK_HOSTS.has(url.hostname)) {
    throw new BrowserError(
      `attach: ${JSON.stringify(text)} is not on loopback; only 127.0.0.1 or localhost endpoints are attached`,
    );
  }
  if (url.port === "") {
    throw new BrowserError(`attach: ${JSON.stringify(text)} names no DevTools port`);
  }
  const port = Number(url.port);
  return { browserURL: `http://127.0.0.1:${port}`, port };
}

/**
 * The JSON object an endpoint file holds.
 * @param {string} text
 * @param {string} path the file, for the messages
 * @returns {Record<string, unknown>}
 * @throws {BrowserError} when the text is not a JSON object
 */
function _endpointObject(text, path) {
  let data;
  try {
    data = JSON.parse(text);
  } catch (exc) {
    const detail = exc instanceof Error ? exc.message.split("\n")[0] : String(exc);
    throw new BrowserError(`attach: endpoint file ${path} is not valid JSON (${detail})`);
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new BrowserError(`attach: endpoint file ${path} is not a JSON object`);
  }
  return /** @type {Record<string, unknown>} */ (data);
}

/**
 * @param {unknown} value
 * @returns {value is string}
 */
function _isString(value) {
  return typeof value === "string";
}

/**
 * @param {unknown} value
 * @returns {value is string}
 */
function _isNonEmptyString(value) {
  return typeof value === "string" && value !== "";
}

/**
 * @param {unknown} value
 * @returns {value is number}
 */
function _isPositiveInteger(value) {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

/**
 * An optional field of an endpoint file: `undefined` when absent, else the value, which must pass `valid`.
 * @template T
 * @param {Record<string, unknown>} record
 * @param {string} name
 * @param {{path: string, kind: string, valid: (value: unknown) => value is T}} how `kind` says what the field must be
 * @returns {T | undefined}
 * @throws {BrowserError} when the field is there and is not valid
 */
function _optionalField(record, name, how) {
  const value = record[name];
  if (value === undefined) {
    return undefined;
  }
  if (!how.valid(value)) {
    throw new BrowserError(`attach: endpoint file ${how.path}: "${name}" is not ${how.kind}`);
  }
  return value;
}

/**
 * An endpoint file's text, validated: the boundary where its JSON enters the tool.
 * @param {string} text
 * @param {string} path the file, for the messages
 * @returns {EndpointFile}
 * @throws {BrowserError} when the text is not JSON or a field is missing or of another kind
 */
export function parseEndpointFile(text, path) {
  const record = _endpointObject(text, path);
  const browserURL = record["browserURL"];
  if (typeof browserURL !== "string") {
    throw new BrowserError(`attach: endpoint file ${path} has no "browserURL" string`);
  }
  loopbackBrowserUrl(browserURL);
  const by = _optionalField(record, "by", { path, kind: "a non-empty string", valid: _isNonEmptyString });
  const pid = _optionalField(record, "pid", { path, kind: "a positive integer", valid: _isPositiveInteger });
  const release = _optionalField(record, "release", { path, kind: "a string", valid: _isString });
  return {
    browserURL,
    by: by ?? "unknown",
    ...(pid === undefined ? {} : { pid }),
    ...(release === undefined ? {} : { release }),
  };
}

/**
 * What the user named as an endpoint: a bare port, a loopback `http://` or `ws://` URL, or the path of
 * an endpoint file (relative to the project root).
 * @param {string} spec
 * @param {{root: string, readText: (path: string) => string | null}} how `root` resolves a relative
 *   path; `readText` reads a file, `null` when there is none
 * @returns {ResolvedEndpoint}
 * @throws {BrowserError} for a host that is not loopback, a port that is not a port, an unreadable
 *   file or one that is not an endpoint file
 */
export function resolveEndpoint(spec, how) {
  if (/^\d+$/.test(spec)) {
    const port = Number(spec);
    if (port < 1 || port > 65535) {
      throw new BrowserError(`attach: the port ${spec} is not a number from 1 to 65535`);
    }
    return { endpoint: spec, browserURL: `http://127.0.0.1:${port}`, port, by: "user", file: null };
  }
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(spec)) {
    return { endpoint: spec, ...loopbackBrowserUrl(spec), by: "user", file: null };
  }
  const file = posix.resolve(how.root, spec);
  const text = how.readText(file);
  if (text === null) {
    throw new BrowserError(
      `attach: ${JSON.stringify(spec)} is not a loopback URL, a port or an endpoint file that exists (looked for ${file})`,
    );
  }
  const parsed = parseEndpointFile(text, file);
  return { endpoint: spec, ...loopbackBrowserUrl(parsed.browserURL), by: parsed.by, file };
}

/**
 * The path of the attach record.
 * @param {string} browserDir
 * @returns {string}
 */
function _attachPath(browserDir) {
  return posix.join(browserDir, _ATTACH_FILE);
}

/**
 * A record read back, validated.
 * @param {string} text
 * @param {string} path
 * @returns {Attachment}
 * @throws {BrowserError} when the record is not an attach record
 */
function _parseAttachment(text, path) {
  /** @type {unknown} */
  let data = null;
  try {
    data = JSON.parse(text);
  } catch {
    // Reported below with the rest.
  }
  const record = /** @type {Record<string, unknown>} */ (typeof data === "object" && data !== null ? data : {});
  const fields = ["endpoint", "browserURL", "by", "browser", "attached"];
  const missing = fields.find((name) => typeof record[name] !== "string");
  const badFile = record["file"] !== undefined && typeof record["file"] !== "string";
  if (missing !== undefined || badFile) {
    throw new BrowserError(
      `${path} is not a valid attach record (${missing === undefined ? '"file"' : `"${missing}"`} is missing or not a string); ` +
        "run: akmon tool browser detach",
    );
  }
  loopbackBrowserUrl(String(record["browserURL"]));
  return /** @type {Attachment} */ (record);
}

/**
 * The attach record of the project, or `null` when it is not in attach mode.
 * @param {string} browserDir
 * @returns {Attachment | null}
 * @throws {BrowserError} when a record exists and is not valid
 */
export function readAttach(browserDir) {
  const path = _attachPath(browserDir);
  const text = readTextOrNull(path);
  return text === null ? null : _parseAttachment(text, path);
}

/**
 * Record an attach.
 * @param {Attachment} attachment
 * @param {string} browserDir
 */
export function writeAttach(attachment, browserDir) {
  fs.mkdirSync(browserDir, { recursive: true });
  fs.writeFileSync(_attachPath(browserDir), `${JSON.stringify(attachment, null, 2)}\n`);
}

/**
 * Forget the attach; nothing else is touched.
 * @param {string} browserDir
 */
export function clearAttach(browserDir) {
  fs.rmSync(_attachPath(browserDir), { force: true });
}

/**
 * The refusal of a verb that would start, stop or restart a Chrome while the project is attached to
 * one it did not start; nothing happens when it is not attached.
 * @param {string} browserDir
 * @param {"start" | "stop" | "restart"} verb
 * @throws {BrowserError} in attach mode
 */
export function refuseInAttachMode(browserDir, verb) {
  const attachment = readAttach(browserDir);
  if (attachment === null) {
    return;
  }
  const why =
    verb === "start"
      ? "the project's own Chrome is started outside attach mode"
      : "akmon never closes a browser it did not start";
  throw new BrowserError(
    `${verb} is refused in attach mode (attached to ${attachment.browserURL}, written by ${attachment.by}): ${why}; run: akmon tool browser detach`,
  );
}

/**
 * The rules of attach mode, as the lines the agent reads after an attach and in `status`.
 * @returns {string[]}
 */
export function attachRules() {
  return [
    "attach mode: never close the window or a page (a run guard may stop the run), never sign in (a test account may have a session cap);",
    "start, stop and restart are refused; read and inspect, then run `akmon tool browser detach`",
    "(`detach --release` also deletes the endpoint file, which lets a held test run finish).",
  ];
}

/**
 * The probe of the real machine for a context.
 * @param {Context} ctx
 * @returns {Probe}
 */
function _realProbe(ctx) {
  return (port, path) => devtoolsJson(ctx.host, port, path);
}

/**
 * The record of an attach to a resolved endpoint.
 * @param {ResolvedEndpoint} resolved
 * @param {string} browser the Chrome's version string
 * @returns {Attachment}
 */
function _attachmentOf(resolved, browser) {
  return {
    endpoint: resolved.endpoint,
    browserURL: resolved.browserURL,
    by: resolved.by,
    ...(resolved.file === null ? {} : { file: resolved.file }),
    browser,
    attached: new Date().toISOString(),
  };
}

/**
 * `attach <endpoint>`: record the endpoint, once its DevTools answers. The ownership check of the
 * project's own Chrome does not apply: naming the endpoint is the explicit route.
 * @param {Context} ctx
 * @param {{endpoint: string}} options
 * @param {{probe?: Probe, readText?: (path: string) => string | null}} [how] the machine, replaced by a test
 * @returns {Promise<number>}
 * @throws {BrowserError} for an endpoint that is not valid or not loopback, or that does not answer
 */
export async function attachCommand(ctx, options, how = {}) {
  const probe = how.probe ?? _realProbe(ctx);
  const resolved = resolveEndpoint(options.endpoint, {
    root: ctx.project.root,
    readText: how.readText ?? readTextOrNull,
  });
  const version = await probe(resolved.port);
  if (version === null || typeof version !== "object") {
    throw new BrowserError(
      `attach: nothing answers on ${resolved.browserURL}; the browser is not listening yet or has gone` +
        (resolved.file === null ? "" : ` (endpoint file ${resolved.file} may be stale)`),
    );
  }
  const before = readAttach(ctx.project.browserDir);
  const attachment = _attachmentOf(resolved, String(version["Browser"] ?? ""));
  writeAttach(attachment, ctx.project.browserDir);
  if (before !== null) {
    ctx.say(`replaced the earlier attach (${before.browserURL}, written by ${before.by})`);
  }
  ctx.say(
    `Attached to Chrome ${attachment.browser} at ${attachment.browserURL} (written by ${attachment.by}` +
      `${resolved.file === null ? "" : `, endpoint file ${resolved.file}`}).`,
  );
  attachRules().forEach((line) => ctx.say(`  ${line}`));
  return 0;
}

/**
 * The endpoint file an attach came from, checked before it is deleted: it must still be an endpoint
 * file, so a record that points elsewhere cannot make `--release` delete some other file.
 * @param {string} file
 * @returns {boolean} whether the file exists
 * @throws {BrowserError} when the file is there and is not an endpoint file
 */
function _isReleasable(file) {
  const text = readTextOrNull(file);
  if (text === null) {
    return false;
  }
  parseEndpointFile(text, file);
  return true;
}

/**
 * The attach record, or the refusal that says it is not valid: `detach` clears an invalid one.
 * @param {string} browserDir
 * @returns {{attachment: Attachment | null, invalid: BrowserError | null}}
 */
function _readForDetach(browserDir) {
  try {
    return { attachment: readAttach(browserDir), invalid: null };
  } catch (exc) {
    if (exc instanceof BrowserError) {
      return { attachment: null, invalid: exc };
    }
    throw exc;
  }
}

/**
 * `detach [--release]`: leave attach mode; the browser is never closed. `--release` also deletes the
 * endpoint file the attach came from, the signal a held test run waits on.
 * @param {Context} ctx
 * @param {{release: boolean}} options
 * @returns {number}
 * @throws {BrowserError} for `--release` when the attach came from no endpoint file
 */
export function detachCommand(ctx, options) {
  const dir = ctx.project.browserDir;
  const { attachment, invalid } = _readForDetach(dir);
  if (invalid !== null) {
    if (options.release) {
      throw invalid;
    }
    clearAttach(dir);
    ctx.say("cleared an attach record that was not valid; no browser was touched");
    return 0;
  }
  if (attachment === null) {
    ctx.say("not attached; nothing to detach");
    return 0;
  }
  const file = attachment.file;
  let existed = false;
  if (options.release) {
    if (file === undefined) {
      throw new BrowserError(
        `detach --release: the attach to ${attachment.browserURL} came from no endpoint file, so there is nothing to release; run detach without --release`,
      );
    }
    existed = _isReleasable(file);
    if (existed) {
      fs.rmSync(file);
    }
  }
  clearAttach(dir);
  ctx.say(`detached from ${attachment.browserURL}; the browser was left running and untouched`);
  if (options.release) {
    ctx.say(
      existed
        ? `released: deleted the endpoint file ${file}; a test run holding its page for the agent may continue`
        : `the endpoint file ${file} was already gone`,
    );
  }
  return 0;
}

/**
 * What `status` reports in attach mode, as data: the same object `--json` prints.
 * @typedef {object} AttachedStatusReport
 * @property {"attached"} mode
 * @property {string} project
 * @property {string} browserURL
 * @property {string} endpoint
 * @property {string} by
 * @property {string | null} file
 * @property {boolean} running the attached Chrome still answers
 * @property {string | null} browser the Chrome's version string now; `null` when it does not answer
 * @property {{title: string, url: string}[]} tabs
 * @property {import("./wiring.mjs").Wiring} mcp
 * @property {string} node
 * @property {string | null} extensionsProblem the configured extension path that cannot be loaded and why, or `null`
 * @property {{version: string | null} | null} [windowsNode] Windows `node`, which the inspection verbs use when only Windows reaches the attached Chrome; `null` when this side reaches it
 */

/**
 * Whether Windows `node` is what the inspection verbs reach the attached Chrome through, and which version.
 * @param {Context} ctx
 * @param {number} port
 * @returns {Promise<{version: string | null} | null>}
 */
async function _windowsNode(ctx, port) {
  if (!ctx.host.isWsl || (await answersHere(port))) {
    return null;
  }
  return { version: await windowsNodeVersion(realWindows()) };
}

/**
 * Collect the status of an attached browser.
 * @param {Attachment} attachment
 * @param {Context} ctx
 * @param {Probe} [probe] how DevTools is asked; the real machine's by default
 * @returns {Promise<AttachedStatusReport>}
 */
export async function collectAttachedStatus(attachment, ctx, probe = _realProbe(ctx)) {
  const port = loopbackBrowserUrl(attachment.browserURL).port;
  const version = await probe(port);
  const answering = version !== null && typeof version === "object";
  const list = answering ? ((await probe(port, "/json/list")) ?? []) : [];
  return {
    mode: "attached",
    project: ctx.project.name,
    browserURL: attachment.browserURL,
    endpoint: attachment.endpoint,
    by: attachment.by,
    file: attachment.file ?? null,
    running: answering,
    browser: answering ? String(version["Browser"] ?? "") : null,
    tabs: pageTabs(list, ctx.settings.redact),
    mcp: wiringOf(ctx.project.root),
    node: process.version,
    extensionsProblem: extensionsProblemLine(ctx.settings),
    windowsNode: answering ? await _windowsNode(ctx, port) : null,
  };
}

/**
 * The lines `status` prints for an attached report.
 * @param {AttachedStatusReport} report
 * @returns {string[]}
 */
export function attachedStatusLines(report) {
  const source = report.file === null ? "" : `, endpoint file ${report.file}`;
  const lines = [];
  if (report.running) {
    lines.push(
      `mode: attached to Chrome ${report.browser} at ${report.browserURL} (written by ${report.by}${source}), ${report.tabs.length} tab(s)`,
    );
    lines.push(...report.tabs.map((tab) => `  ${tab.title.slice(0, 60).padEnd(60)} ${tab.url}`));
    lines.push(...attachRules().map((line) => `  ${line}`));
  } else {
    lines.push(
      `mode: attached to ${report.browserURL} (written by ${report.by}${source}), but it no longer answers: ` +
        "the run may have finished or the browser closed; run: akmon tool browser detach",
    );
  }
  lines.push(`  mcp: ${report.mcp.state}, ${report.mcp.why}`);
  lines.push(`  node: ${report.node}`);
  if (report.windowsNode) {
    lines.push(`  ${windowsNodeLine(report.windowsNode.version)}`);
  }
  if (report.extensionsProblem !== null) {
    lines.push(`  extensions: ${report.extensionsProblem}`);
  }
  return lines;
}

/**
 * `status` in attach mode: exit 0 when the attached Chrome still answers, 1 when the attach is stale.
 * @param {Context} ctx
 * @param {Attachment} attachment
 * @param {{json: boolean}} options
 * @param {Probe} [probe]
 * @returns {Promise<number>}
 */
export async function attachedStatusCommand(ctx, attachment, options, probe) {
  const report = await collectAttachedStatus(attachment, ctx, probe);
  if (options.json) {
    ctx.say(JSON.stringify(report, null, 2));
  } else {
    attachedStatusLines(report).forEach(ctx.say);
  }
  return report.running && report.extensionsProblem === null ? 0 : 1;
}
