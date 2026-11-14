/**
 * The inspection verbs of `akmon tool browser`: `pages`, `snapshot`, `screenshot`, `eval`, `logs`, `net` and
 * `selectors`, which read the page the user and the agent share, from Bash. `eval`, `logs` and `net` also
 * read an extension's service worker or page (`--target`) and `eval` its content-script world (`--world`). This side does the project's part
 * (which Chrome, the settings, the files and the words); the Chrome side is `ops.mjs`, run in this
 * process when Chrome answers here and in the CDP runner on the Windows side when only Windows reaches it
 * (`windows.mjs`). A verb never starts a Chrome. `eval` reads: the page is not changed, and no request is
 * made to a site's API from inside it.
 */

import fs from "node:fs";
import { posix } from "node:path";

import { UsageError } from "./arguments.mjs";
import { loopbackBrowserUrl, readAttach } from "./attach.mjs";
import { answersHere, devtoolsJson } from "./devtools.mjs";
import { portState } from "./lifecycle.mjs";
import { realDeps, runRequest } from "./ops.mjs";
import { evalText, logLines, netLines, outlineLines, pageLines, pageRows, selectorLines } from "./render.mjs";
import { BrowserError } from "./settings.mjs";
import { fetchTargets, redactedTargets } from "./targets.mjs";
import { realWindows, runOnWindows } from "./windows.mjs";

/** The seconds `logs` and `net` listen for, and the largest body `net --bodies` keeps, without an option. */
const _LOGS_SECONDS = 30;
const _NET_SECONDS = 10;
const _MAX_BODY_BYTES = 65_536;
/** The outline's size without `--max-nodes`. */
const _MAX_NODES = 1500;

/**
 * @typedef {import("./context.mjs").Context} Context
 * @typedef {import("./protocol.mjs").Operation} Operation
 */

/**
 * The browser a verb works on, and the side it is reached from.
 * @typedef {object} Browser
 * @property {string} browserURL `http://127.0.0.1:<port>`
 * @property {number} port
 * @property {"own" | "attached"} mode
 * @property {"here" | "windows"} side `windows`: under WSL, a Chrome only Windows reaches
 */

/**
 * What the verbs ask of the machine, replaced by a test.
 * @typedef {object} Inspector
 * @property {(ctx: Context) => Promise<Browser>} locate which browser to read, checked
 * @property {(ctx: Context, browser: Browser) => Promise<import("./targets.mjs").Target[]>} targets its targets
 * @property {(browser: Browser, request: import("./protocol.mjs").Request) => Promise<import("./protocol.mjs").Response>} execute run a request on the right side
 * @property {(path: string) => string} [toChromePath] a path as a Chrome on the Windows side spells it (`wslpath -w`); none: the path as it is
 */

/**
 * The side a Chrome on `port` is reached from: here when it answers here, else, under WSL, Windows (a
 * Windows Chrome's port answers only to Windows processes).
 * @param {{isWsl: boolean, answersHere: boolean, port: number}} state
 * @returns {"here" | "windows"}
 * @throws {BrowserError} when it answers on neither side
 */
export function chooseSide(state) {
  if (state.answersHere) {
    return "here";
  }
  if (state.isWsl) {
    return "windows";
  }
  throw new BrowserError(`Chrome DevTools on 127.0.0.1:${state.port} does not answer from here`);
}

/**
 * The side the Chrome on `port` is reached from, asked of the real machine.
 * @param {Context} ctx
 * @param {number} port
 * @returns {Promise<"here" | "windows">}
 */
async function _sideOf(ctx, port) {
  return chooseSide({ isWsl: ctx.host.isWsl, answersHere: await answersHere(port), port });
}

/**
 * The browser to read: the attached one in attach mode, else the project's own Chrome once its ownership
 * is checked. Nothing is started.
 * @param {Context} ctx
 * @returns {Promise<Browser>}
 * @throws {BrowserError} when none answers, or the Chrome on the port is not this project's
 */
export async function locateBrowser(ctx) {
  const attachment = readAttach(ctx.project.browserDir);
  if (attachment !== null) {
    const { port, browserURL } = loopbackBrowserUrl(attachment.browserURL);
    if ((await devtoolsJson(ctx.host, port)) === null) {
      throw new BrowserError(
        `the attached Chrome at ${browserURL} (written by ${attachment.by}) no longer answers; ` +
          "run: akmon tool browser detach",
      );
    }
    return { browserURL, port, mode: "attached", side: await _sideOf(ctx, port) };
  }
  const found = await portState(ctx);
  if (found === null) {
    throw new BrowserError(
      `no Chrome of project ${ctx.project.name} answers on 127.0.0.1:${ctx.port}; start it: ` +
        "akmon tool browser start (or use a Chrome the project did not start: akmon tool browser attach <endpoint>)",
    );
  }
  if (found.refusal !== null) {
    throw new BrowserError(found.refusal);
  }
  return {
    browserURL: `http://127.0.0.1:${ctx.port}`,
    port: ctx.port,
    mode: "own",
    side: await _sideOf(ctx, ctx.port),
  };
}

/**
 * The real machine's inspector.
 * @returns {Inspector}
 */
export function realInspector() {
  return {
    locate: locateBrowser,
    targets: (ctx, browser) =>
      fetchTargets(browser.browserURL, (url) => devtoolsJson(ctx.host, browser.port, new URL(url).pathname)),
    execute: (browser, request) => (browser.side === "here" ? runRequest(request, realDeps()) : runOnWindows(request)),
    toChromePath: (path) => realWindows().toWindowsPath(path),
  };
}

/**
 * The folders of the configured extensions as the Chrome on `browser` spells them.
 * @param {Context} ctx
 * @param {Inspector} how
 * @param {Browser} browser
 * @returns {string[]}
 */
function _extensionPaths(ctx, how, browser) {
  const convert = how.toChromePath;
  return ctx.settings.extensions.map((path) =>
    browser.side === "windows" && convert !== undefined ? convert(path) : path,
  );
}

/**
 * What a run asks of the browser.
 * @typedef {object} Work
 * @property {string | null} page the `--page` selector
 * @property {Operation[]} operations
 * @property {string | null} [target] `--target`: `page` (the default), `sw`, `popup` or a target id
 * @property {string | null} [ext] `--ext`: the extension an `sw` or `popup` target, an isolated world or an `ext-*` operation means
 */

/**
 * Run operations on the browser the verb works on, and return the answer as a whole.
 * @param {Context} ctx
 * @param {Inspector} how
 * @param {Work} what
 * @returns {Promise<import("./protocol.mjs").Response & {results: import("./protocol.mjs").Outcome[], extensionPaths: string[]}>}
 * @throws {BrowserError} when the run fails as a whole
 */
export async function runOperations(ctx, how, what) {
  const browser = await how.locate(ctx);
  const extensionPaths = _extensionPaths(ctx, how, browser);
  const response = await how.execute(browser, {
    browserURL: browser.browserURL,
    page: what.page,
    redact: [...ctx.settings.redact],
    operations: what.operations,
    target: what.target ?? "page",
    ext: what.ext ?? null,
    extensionPaths,
  });
  if (response.error !== undefined) {
    throw new BrowserError(response.error);
  }
  if (response.results === undefined) {
    throw new BrowserError("the browser run returned no result");
  }
  return { ...response, results: response.results, extensionPaths };
}

/**
 * Run one operation on the page and return its value.
 * @param {Context} ctx
 * @param {Inspector} how
 * @param {Omit<Work, "operations"> & {operation: Operation}} what
 * @returns {Promise<{value: any, page: {id: string, title: string, url: string}}>}
 * @throws {BrowserError} when the run fails as a whole or the operation fails
 */
async function _run(ctx, how, what) {
  const response = await runOperations(ctx, how, { ...what, operations: [what.operation] });
  const outcome = response.results[0];
  if (outcome === undefined || response.page === undefined) {
    throw new BrowserError("the browser run returned no result");
  }
  if (!outcome.ok) {
    throw new BrowserError(outcome.error);
  }
  return { value: outcome.value, page: response.page };
}

/**
 * `pages [--all] [--json]`: the page targets, and with `--all` the others.
 * @param {Context} ctx
 * @param {{all: boolean, json: boolean}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 */
export async function pagesCommand(ctx, options, how = realInspector()) {
  const browser = await how.locate(ctx);
  const rows = pageRows(redactedTargets(await how.targets(ctx, browser), ctx.settings.redact), options.all);
  if (options.json) {
    ctx.say(JSON.stringify(rows, null, 2));
  } else {
    pageLines(rows).forEach(ctx.say);
  }
  return 0;
}

/**
 * `snapshot [--page P] [--json] [--max-nodes N] [--text]`: the accessibility outline, or the visible text.
 * @param {Context} ctx
 * @param {{page: string | null, json: boolean, maxNodes: number | null, text: boolean}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 */
export async function snapshotCommand(ctx, options, how = realInspector()) {
  const { value } = await _run(ctx, how, {
    page: options.page,
    operation: { op: "snapshot", maxNodes: options.maxNodes ?? _MAX_NODES, text: options.text },
  });
  if (options.json) {
    ctx.say(JSON.stringify(value, null, 2));
  } else if (options.text) {
    ctx.say(value.text);
  } else {
    outlineLines(value).forEach(ctx.say);
  }
  return 0;
}

/**
 * The size `--viewport` names: `WxH`, or a name from the settings' table (the presets and `[browser].viewports`).
 * @param {string | null} spec
 * @param {import("./settings.mjs").BrowserSettings["viewports"]} named
 * @returns {{viewport: import("./protocol.mjs").Viewport | null, label: string}} the size, and the word that names it in a file
 * @throws {UsageError} for a name that is not in the table
 */
export function resolveViewport(spec, named) {
  if (spec === null) {
    return { viewport: null, label: "native" };
  }
  const found = Object.hasOwn(named, spec) ? named[spec] : undefined;
  if (found !== undefined) {
    return { viewport: found, label: spec };
  }
  const match = spec.trim().match(/^(\d{2,5})\s*[xX]\s*(\d{2,5})$/);
  if (match !== null) {
    return { viewport: { width: Number(match[1]), height: Number(match[2]) }, label: `${match[1]}x${match[2]}` };
  }
  throw new UsageError(
    `screenshot: --viewport ${JSON.stringify(spec)} is neither WxH nor one of ${Object.keys(named).join(", ")}`,
  );
}

/**
 * The host of a page's URL, as a word safe in a file name (`page` for a URL with none, such as `data:`).
 * @param {string} url
 * @returns {string}
 */
export function hostWord(url) {
  let host = "";
  try {
    host = new URL(url).hostname;
  } catch {
    // A URL that does not parse names no host.
  }
  const word = host.toLowerCase().replace(/[^a-z0-9.-]+/g, "_");
  return word === "" ? "page" : word;
}

/**
 * Where a verb writes: nothing when `out` is not given and there is no default; a bare file name goes into
 * the verb's own folder; a path is relative to the project root; a folder (an existing one, or one written
 * with a trailing slash) gets the default file name.
 * @param {string | null} out `--out`
 * @param {{root: string, folder: string, name: string, always: boolean}} where `folder` and `name` are
 *   the default place and file; `always` writes there when `out` is not given
 * @returns {string | null}
 */
export function outputPath(out, where) {
  if (out === null) {
    return where.always ? posix.join(where.folder, where.name) : null;
  }
  const absolute = posix.resolve(where.root, out);
  if (out.endsWith("/") || (fs.existsSync(absolute) && fs.statSync(absolute).isDirectory())) {
    return posix.join(absolute, where.name);
  }
  return out.includes("/") ? absolute : posix.join(where.folder, out);
}

/**
 * Write a file, making its folder.
 * @param {string} path
 * @param {string | Uint8Array} data
 */
function _write(path, data) {
  fs.mkdirSync(posix.dirname(path), { recursive: true });
  fs.writeFileSync(path, data);
}

/**
 * `screenshot [--page P] [--viewport V] [--scheme S] [--full] [--out PATH]`: a PNG, the emulation cleared after.
 * @param {Context} ctx
 * @param {{page: string | null, viewport: string | null, scheme: "light" | "dark" | null, full: boolean, out: string | null}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>} 1 when the emulation could not be cleared, the shot being written all the same
 * @throws {UsageError} for a viewport that is not known
 */
export async function screenshotCommand(ctx, options, how = realInspector()) {
  const { viewport, label } = resolveViewport(options.viewport, ctx.settings.viewports);
  const { value, page } = await _run(ctx, how, {
    page: options.page,
    operation: { op: "screenshot", viewport, scheme: options.scheme, full: options.full },
  });
  const name = `${hostWord(page.url)}-${label}${options.scheme === null ? "" : `-${options.scheme}`}${options.full ? "-full" : ""}.png`;
  const path = outputPath(options.out, {
    root: ctx.project.root,
    folder: posix.join(ctx.project.browserDir, "shots"),
    name,
    always: true,
  });
  _write(String(path), Buffer.from(String(value.data), "base64"));
  ctx.say(String(path));
  /** @type {string[]} */
  const warnings = value.warnings;
  warnings.forEach((warning) => ctx.say(`warning: ${warning}`));
  return warnings.length === 0 ? 0 : 1;
}

/**
 * `eval <expression> [--page P] [--target T] [--world W] [--ext E] [--json]`: the value of one expression,
 * evaluated in the page (its own world, or the extension's isolated one), an extension's service worker or an
 * extension page, which it reads.
 * @param {Context} ctx
 * @param {{page: string | null, json: boolean, expression: string | null, target?: string | null, world?: "page" | "isolated" | null, ext?: string | null}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 * @throws {BrowserError} with the exception's text when the expression throws
 */
export async function evalCommand(ctx, options, how = realInspector()) {
  const { value } = await _run(ctx, how, {
    page: options.page,
    target: options.target,
    ext: options.ext,
    operation: { op: "eval", expression: String(options.expression), world: options.world ?? "page" },
  });
  ctx.say(evalText(value, options.json));
  return 0;
}

/**
 * What a listening verb says when it ends, and its exit status: a matched `--until` is 0, a timeout is 0
 * unless an `--until` was asked for and never met, and a browser that went away is a refusal.
 * @param {"matched" | "timeout" | "closed"} status
 * @param {{until: string | null, seconds: number}} listened
 * @returns {{line: string | null, code: number}}
 * @throws {BrowserError} when the browser closed the connection
 */
function _ending(status, listened) {
  if (status === "closed") {
    throw new BrowserError("the browser closed the connection before the capture ended");
  }
  if (status === "matched") {
    return { line: null, code: 0 };
  }
  const unmet = listened.until === null ? "" : `; /${listened.until}/ did not match`;
  return { line: `timeout after ${listened.seconds} s${unmet}`, code: listened.until === null ? 0 : 1 };
}

/**
 * `logs [--page P] [--target T] [--ext E] [--until REGEX] [--timeout SECONDS] [--json]`: console messages,
 * exceptions and log entries, tagged by source, those already held first, then those that follow.
 * @param {Context} ctx
 * @param {{page: string | null, until: string | null, timeout: number | null, json: boolean, target?: string | null, ext?: string | null}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 */
export async function logsCommand(ctx, options, how = realInspector()) {
  const seconds = options.timeout ?? _LOGS_SECONDS;
  const { value } = await _run(ctx, how, {
    page: options.page,
    target: options.target,
    ext: options.ext,
    operation: { op: "logs", until: options.until, seconds },
  });
  const ending = _ending(value.status, { until: options.until, seconds });
  if (options.json) {
    ctx.say(JSON.stringify(value, null, 2));
    return ending.code;
  }
  logLines(value.entries).forEach(ctx.say);
  if (value.dropped > 0) {
    ctx.say(`… ${value.dropped} more lines not kept`);
  }
  if (ending.line !== null) {
    ctx.say(ending.line);
  }
  return ending.code;
}

/**
 * `net [--page P] [--target T] [--ext E] [--for SECONDS] [--until REGEX] [--failed] [--bodies] [--max-body BYTES]
 * [--out PATH] [--json]`: the requests the page (or an extension's service worker) makes while it listens. It
 * reloads nothing; secrets are redacted at capture.
 * @param {Context} ctx
 * @param {{page: string | null, forSeconds: number | null, until: string | null, failed: boolean, bodies: boolean, maxBody: number | null, out: string | null, json: boolean, target?: string | null, ext?: string | null}} options
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 */
export async function netCommand(ctx, options, how = realInspector()) {
  const seconds = options.forSeconds ?? _NET_SECONDS;
  const { value, page } = await _run(ctx, how, {
    page: options.page,
    target: options.target,
    ext: options.ext,
    operation: {
      op: "net",
      seconds,
      until: options.until,
      failed: options.failed,
      bodies: options.bodies,
      maxBody: options.maxBody ?? _MAX_BODY_BYTES,
    },
  });
  const ending = _ending(value.status, { until: options.until, seconds });
  const path = outputPath(options.out, {
    root: ctx.project.root,
    folder: posix.join(ctx.project.browserDir, "net"),
    name: `${hostWord(page.url)}.json`,
    always: false,
  });
  if (path !== null) {
    _write(
      path,
      `${JSON.stringify({ page, status: value.status, dropped: value.dropped, entries: value.entries }, null, 2)}\n`,
    );
  }
  if (options.json) {
    ctx.say(JSON.stringify(value, null, 2));
  } else {
    _netSummary(ctx, value, { failed: options.failed, bodies: options.bodies && path === null, path });
    if (ending.line !== null) {
      ctx.say(ending.line);
    }
  }
  return ending.code;
}

/**
 * The lines `net` prints for a capture.
 * @param {Context} ctx
 * @param {{entries: import("./ops.mjs").NetEntry[], dropped: number}} capture
 * @param {{failed: boolean, bodies: boolean, path: string | null}} how `bodies`: print the bodies; `path`: where the entries were written
 */
function _netSummary(ctx, capture, how) {
  netLines(capture.entries, how.bodies).forEach(ctx.say);
  if (capture.dropped > 0) {
    ctx.say(`… ${capture.dropped} more requests not kept`);
  }
  ctx.say(`${capture.entries.length} request(s)${how.failed ? " failed" : ""} in the capture`);
  if (how.path !== null) {
    ctx.say(`wrote ${how.path}`);
  }
}

/**
 * A selector registry from the text of its file: `{ "<name>": ["<css selector>", "<fallback>", ...] }`, each name
 * with at least one selector, the first the primary and the others fallbacks tried in order.
 * @param {string} text
 * @param {string} label the file, for the message
 * @returns {Record<string, string[]>}
 * @throws {BrowserError} naming the file and what is wrong with it
 */
export function parseRegistry(text, label) {
  /** @type {unknown} */
  let data;
  try {
    data = JSON.parse(text);
  } catch (exc) {
    throw new BrowserError(`${label} is not JSON (${exc instanceof Error ? exc.message : String(exc)})`);
  }
  if (typeof data !== "object" || data === null || Array.isArray(data) || Object.keys(data).length === 0) {
    throw new BrowserError(`${label} must be a JSON object of name -> list of CSS selectors, with at least one name`);
  }
  /** @type {Record<string, string[]>} */
  const registry = {};
  for (const [name, list] of Object.entries(data)) {
    if (!_isSelectorList(list)) {
      throw new BrowserError(`${label}: "${name}" must be a non-empty list of CSS selector strings`);
    }
    registry[name] = list;
  }
  return registry;
}

/**
 * @param {unknown} list
 * @returns {list is string[]}
 */
function _isSelectorList(list) {
  return Array.isArray(list) && list.length > 0 && list.every((css) => typeof css === "string" && css !== "");
}

/**
 * `selectors <file> [--page P] [--json]`: each name of the project's selector registry counted on the page,
 * shadow roots included, as matched, matched by a fallback or missing. It reads; it exits 1 when any is missing.
 * @param {Context} ctx
 * @param {{file: string | null, page: string | null, json: boolean}} options `file` is relative to the project root
 * @param {Inspector} [how]
 * @returns {Promise<number>}
 * @throws {BrowserError} when the registry cannot be read or is not valid
 */
export async function selectorsCommand(ctx, options, how = realInspector()) {
  const path = posix.resolve(ctx.project.root, String(options.file));
  let text;
  try {
    text = fs.readFileSync(path, "utf8");
  } catch (exc) {
    throw new BrowserError(
      `cannot read the selector registry ${path} (${exc instanceof Error ? exc.message : String(exc)})`,
    );
  }
  const registry = parseRegistry(text, String(options.file));
  const { value, page } = await _run(ctx, how, {
    page: options.page,
    operation: { op: "selectors", registry },
  });
  /** @type {import("./selectors.mjs").SelectorFinding[]} */
  const findings = value.findings;
  const missing = findings.filter((finding) => finding.status === "missing").length;
  if (options.json) {
    ctx.say(JSON.stringify({ page, findings }, null, 2));
  } else {
    selectorLines(findings).forEach(ctx.say);
    ctx.say(`${findings.length} selector name(s) on ${page.url}: ${missing} missing`);
  }
  return missing === 0 ? 0 : 1;
}
