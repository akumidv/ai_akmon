/**
 * The Chrome side of the inspection and extension verbs: what each of `snapshot`, `screenshot`, `eval`, `logs`,
 * `net`, `selectors` and the `ext-*` operations asks of a target or of the browser and what it collects, as
 * JSON-safe data. `runRequest` is the one entry: it runs a
 * request (`protocol.mjs`) against a browser, either in `akmon tool browser`'s own process or in the CDP
 * runner on the Windows side, so a Chrome only Windows reaches is served by the same code. Formatting
 * for the person or the agent is the other side's (`render.mjs`). Secrets are redacted here, at
 * capture, before a value leaves this module. The module imports nothing outside Node.
 */

import fs from "node:fs";

import { attachToPage, CdpError, connect, detachFromPage, openTransport } from "./cdp.mjs";
import {
  EXTENSION_ID,
  extensionAmong,
  extensionIdOf,
  listExtensions,
  reloadExtensions,
  resolveSubject,
  samePath,
  triggerAction,
  turnDeveloperModeOn,
} from "./extension-cdp.mjs";
import { redactBody, redactFloor, redactHeaders, redactUrl, scrubbedText, textualMime } from "./redact.mjs";
import { selectorExpression, selectorFindings } from "./selectors.mjs";
import { fetchTargets } from "./targets.mjs";

/** How long one evaluation may run, and how long a page's answer to a plain call may take, in milliseconds. */
const _EVAL_MS = 30_000;
const _CALL_MS = 15_000;
/** How long one response body may take. */
const _BODY_MS = 5000;
/** How many console lines and requests one run keeps; the rest is counted. */
const _MAX_ENTRIES = 5000;
/** The longest a console line or an outline name is kept, in characters. */
const _MAX_TEXT = 2000;
const _MAX_NAME = 200;

/**
 * What a run needs from the machine it runs on, replaced by a test.
 * @typedef {object} Deps
 * @property {(url: string) => Promise<any>} fetchJson a DevTools JSON answer
 * @property {(url: string) => Promise<import("./cdp.mjs").Transport>} open opens the wire of a WebSocket
 * @property {() => number} now milliseconds since the epoch, on the Chrome's machine
 * @property {(path: string) => string} readText the text of a file on the Chrome's machine (an extension's manifest)
 */

/**
 * The machine this process runs on.
 * @returns {Deps}
 */
export function realDeps() {
  return {
    fetchJson: async (url) => {
      let response;
      try {
        response = await fetch(url, { signal: AbortSignal.timeout(5000) });
      } catch {
        throw new CdpError(`nothing answers on ${url}`);
      }
      if (!response.ok) {
        throw new CdpError(`${url} answered HTTP ${response.status}`);
      }
      return response.json();
    },
    open: (url) => openTransport(url),
    now: () => Date.now(),
    readText: (path) => fs.readFileSync(path, "utf8"),
  };
}

/**
 * One accessibility node as Chrome reports it, reduced to what the outline reads.
 * @typedef {object} AxNode
 * @property {string} nodeId
 * @property {string} [parentId]
 * @property {string[]} [childIds]
 * @property {boolean} [ignored]
 * @property {{value?: unknown}} [role]
 * @property {{value?: unknown}} [name]
 * @property {{value?: unknown}} [value]
 */

/**
 * One line of the outline.
 * @typedef {object} OutlineLine
 * @property {number} depth
 * @property {string} role
 * @property {string} name
 * @property {string} value
 */

/** Roles that say nothing about structure: dropped, their children keep the parent's depth. */
const _PLAIN_ROLES = new Set(["none", "presentation", "InlineTextBox"]);

/**
 * Text collapsed to one line and cut.
 * @param {unknown} value
 * @param {number} limit
 * @returns {string}
 */
function _oneLine(value, limit) {
  const text = value === undefined || value === null ? "" : String(value).replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

/**
 * Whether an outline leaves a node out: one Chrome ignores, a plain role, a nameless `generic`, or a text
 * node that repeats its parent's name.
 * @param {AxNode} node
 * @param {{role: string, name: string, parentName: string}} read the node's role and name, and its parent's name
 * @returns {boolean}
 */
function _dropped(node, read) {
  return (
    node.ignored === true ||
    _PLAIN_ROLES.has(read.role) ||
    (read.role === "generic" && read.name === "") ||
    (read.role === "StaticText" && read.name === read.parentName)
  );
}

/**
 * The accessibility tree as a flat outline: ignored and `none` nodes are dropped (their children move up),
 * as is a nameless `generic` node and a text node that repeats its parent's name; at most `maxNodes` lines
 * are kept and the rest only counted.
 * @param {readonly AxNode[]} nodes
 * @param {number} maxNodes
 * @returns {{lines: OutlineLine[], total: number, truncated: boolean}}
 */
export function outlineOf(nodes, maxNodes) {
  const byId = new Map(nodes.map((node) => [node.nodeId, node]));
  /** @type {{node: AxNode, depth: number, parentName: string}[]} */
  const stack = nodes
    .filter((node) => node.parentId === undefined || !byId.has(node.parentId))
    .reverse()
    .map((node) => ({ node, depth: 0, parentName: "" }));
  /** @type {OutlineLine[]} */
  const lines = [];
  let total = 0;
  for (let item = stack.pop(); item !== undefined; item = stack.pop()) {
    const { node, depth, parentName } = item;
    const role = _oneLine(node.role?.value, _MAX_NAME);
    const name = _oneLine(node.name?.value, _MAX_NAME);
    const dropped = _dropped(node, { role, name, parentName });
    if (!dropped) {
      total += 1;
      if (lines.length < maxNodes) {
        lines.push({ depth, role, name, value: _oneLine(node.value?.value, _MAX_NAME) });
      }
    }
    const below = dropped ? { depth, parentName } : { depth: depth + 1, parentName: name };
    for (const child of (node.childIds ?? []).flatMap((id) => byId.get(id) ?? []).reverse()) {
      stack.push({ node: child, ...below });
    }
  }
  return { lines, total, truncated: total > lines.length };
}

/**
 * `snapshot`: the page's accessibility outline, or with `text` its visible text.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {{maxNodes: number, text: boolean}} spec
 * @returns {Promise<{lines: OutlineLine[], total: number, truncated: boolean} | {text: string}>}
 */
async function _snapshot(page, spec) {
  if (spec.text) {
    const answer = await page.send(
      "Runtime.evaluate",
      { expression: "document.body ? document.body.innerText : ''", returnByValue: true },
      _CALL_MS,
    );
    return { text: String(answer.result?.value ?? "") };
  }
  const { nodes } = await page.send("Accessibility.getFullAXTree", {}, _EVAL_MS);
  return outlineOf(Array.isArray(nodes) ? nodes : [], spec.maxNodes);
}

/**
 * Undo the emulation a capture set, one call each, and say which could not be undone. It never throws:
 * the window is the user's, so every undo is tried and a failure is reported, not hidden.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {{metrics: boolean, media: boolean}} applied what was attempted
 * @returns {Promise<string[]>} one warning per undo that failed
 */
async function _clearEmulation(page, applied) {
  /** @type {string[]} */
  const warnings = [];
  /** @type {[boolean, string, Record<string, unknown>][]} */
  const steps = [
    [applied.metrics, "Emulation.clearDeviceMetricsOverride", {}],
    [applied.media, "Emulation.setEmulatedMedia", { features: [] }],
  ];
  for (const [attempted, method, params] of steps) {
    if (attempted) {
      try {
        await page.send(method, params, 5000);
      } catch (exc) {
        warnings.push(
          `${method} failed (${exc instanceof Error ? exc.message : String(exc)}); reload the page to drop the emulation`,
        );
      }
    }
  }
  return warnings;
}

/**
 * The screenshot of a page: its viewport and scheme are emulated for the capture only.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {{viewport: import("./protocol.mjs").Viewport | null, scheme: "light" | "dark" | null, full: boolean}} spec
 * @param {string[]} warnings collects what could not be undone; read after this returns or throws
 * @returns {Promise<string>} the PNG, base64
 */
async function _capture(page, spec, warnings) {
  const applied = { metrics: false, media: false };
  try {
    if (spec.viewport !== null) {
      applied.metrics = true;
      await page.send("Emulation.setDeviceMetricsOverride", {
        width: spec.viewport.width,
        height: spec.viewport.height,
        deviceScaleFactor: 1,
        mobile: false,
      });
    }
    if (spec.scheme !== null) {
      applied.media = true;
      await page.send("Emulation.setEmulatedMedia", {
        features: [{ name: "prefers-color-scheme", value: spec.scheme }],
      });
    }
    /** @type {Record<string, unknown>} */
    const params = { format: "png" };
    if (spec.full) {
      const metrics = await page.send("Page.getLayoutMetrics");
      const size = metrics.cssContentSize ?? metrics.contentSize;
      if (size === undefined) {
        throw new CdpError("Page.getLayoutMetrics: no content size in the answer");
      }
      params["captureBeyondViewport"] = true;
      params["clip"] = { x: 0, y: 0, width: Math.ceil(size.width), height: Math.ceil(size.height), scale: 1 };
    }
    const shot = await page.send("Page.captureScreenshot", params, _EVAL_MS);
    return String(shot.data);
  } finally {
    warnings.push(...(await _clearEmulation(page, applied)));
  }
}

/**
 * `screenshot`: a PNG of the page as base64, with the emulation always cleared afterwards.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {{viewport: import("./protocol.mjs").Viewport | null, scheme: "light" | "dark" | null, full: boolean}} spec
 * @returns {Promise<{data: string, warnings: string[]}>}
 * @throws {CdpError} on a failure, which also names an emulation that could not be undone
 */
async function _screenshot(page, spec) {
  /** @type {string[]} */
  const warnings = [];
  try {
    return { data: await _capture(page, spec, warnings), warnings };
  } catch (exc) {
    if (warnings.length > 0) {
      throw new CdpError(`${exc instanceof Error ? exc.message : String(exc)}; ${warnings.join("; ")}`);
    }
    throw exc;
  }
}

/**
 * One execution context of a target, as `Runtime.executionContextCreated` reports it.
 * @typedef {object} ExecutionContext
 * @property {number} id
 * @property {string} origin
 * @property {string} name an extension's content-script world is named by the extension
 * @property {{type?: string, frameId?: string}} [auxData] `type` is `isolated` for a content-script world
 */

/**
 * The execution contexts of one target, followed from the first `start`: Chrome announces the existing
 * ones when `Runtime.enable` is sent, and every new one after.
 */
class _Contexts {
  /**
   * @param {import("./cdp.mjs").PageSession} page
   */
  constructor(page) {
    this.page = page;
    /** @type {Map<number, ExecutionContext>} */
    this.byId = new Map();
    this.started = false;
  }

  /**
   * Follow the contexts and enable the runtime, once; later calls change nothing.
   * @returns {Promise<void>}
   */
  async start() {
    if (this.started) {
      return;
    }
    this.started = true;
    this.page.on("Runtime.executionContextCreated", (params) => this.byId.set(params.context.id, params.context));
    this.page.on("Runtime.executionContextDestroyed", (params) => this.byId.delete(params.executionContextId));
    this.page.on("Runtime.executionContextsCleared", () => this.byId.clear());
    await this.page.send("Runtime.enable");
  }

  /**
   * Whether a context is an extension's content-script world.
   * @param {number | undefined} id
   * @returns {boolean}
   */
  isExtensionWorld(id) {
    const context = id === undefined ? undefined : this.byId.get(id);
    return context !== undefined && isExtensionWorld(context);
  }
}

/**
 * Whether a context is a content-script world of an extension: isolated, with an extension's origin.
 * @param {ExecutionContext} context
 * @returns {boolean}
 */
function isExtensionWorld(context) {
  return context.auxData?.type === "isolated" && extensionIdOf(String(context.origin)) !== null;
}

/**
 * What a run holds for the one target its target-bound operations work on.
 * @typedef {object} Subject
 * @property {import("./cdp.mjs").PageSession} page
 * @property {"page" | "sw" | "popup"} source what its log lines are tagged with
 * @property {_Contexts} contexts
 */

/**
 * What an operation can reach besides its subject.
 * @typedef {object} Run
 * @property {import("./cdp.mjs").CdpConnection} connection
 * @property {readonly import("./targets.mjs").Target[]} targets
 * @property {import("./protocol.mjs").Request} request
 * @property {string[]} keys the JSON keys and query parameters to redact: the defaults and the project's
 * @property {Deps} deps
 * @property {Subject | null} subject the target for the operations that work on one
 */

/**
 * Evaluate an expression in a target and return the answer's result, or fail with the exception's text.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {string} expression
 * @param {number | null} contextId a world other than the target's own, or `null`
 * @returns {Promise<{type?: string, value?: unknown, unserializableValue?: string, description?: string}>}
 * @throws {CdpError} with the exception's text when the expression throws
 */
async function _evaluateIn(page, expression, contextId) {
  const answer = await page.send(
    "Runtime.evaluate",
    {
      expression,
      returnByValue: true,
      awaitPromise: true,
      timeout: _EVAL_MS,
      userGesture: false,
      ...(contextId === null ? {} : { contextId }),
    },
    _EVAL_MS + 5000,
  );
  if (answer.exceptionDetails !== undefined) {
    throw new CdpError(`the expression threw: ${exceptionText(answer.exceptionDetails)}`);
  }
  return answer.result ?? {};
}

/**
 * The content-script worlds a selector means: the extension named by id or by name (a name as a whole, else
 * as part of one), or all of them with no selector.
 * @param {readonly ExecutionContext[]} worlds
 * @param {string | null} select
 * @returns {ExecutionContext[]}
 */
function _worldsOf(worlds, select) {
  if (select === null) {
    return [...worlds];
  }
  if (EXTENSION_ID.test(select)) {
    return worlds.filter((context) => extensionIdOf(context.origin) === select);
  }
  const wanted = select.toLowerCase();
  const named = (/** @type {(name: string) => boolean} */ test) =>
    worlds.filter((context) => test(String(context.name).toLowerCase()));
  const exact = named((name) => name === wanted);
  return exact.length > 0 ? exact : named((name) => name.includes(wanted));
}

/**
 * The failure for a page with no content-script world of the extension asked for.
 * @param {readonly ExecutionContext[]} worlds the content-script worlds the page does have
 * @param {string | null} select
 * @returns {CdpError}
 */
function _noWorld(worlds, select) {
  const known = worlds.map((context) => `${context.name} (${extensionIdOf(context.origin)})`).join(", ");
  return new CdpError(
    `${select === null ? "no extension has" : `the extension "${select}" has no`} content-script world on this ` +
      `page${known === "" ? "" : ` (the page has: ${known})`}; the page may match none of its content scripts, ` +
      "or was opened before the extension was reloaded and needs a reload",
  );
}

/**
 * The execution context to evaluate in for the extension's isolated world on a page: the content-script
 * world of the extension the request names or configures, in the main frame when it has one there.
 * @param {Subject} subject
 * @param {Run} run
 * @returns {Promise<number>}
 * @throws {CdpError} when the page has no such world, saying why that may be
 */
async function _isolatedWorld(subject, run) {
  await subject.contexts.start();
  const worlds = [...subject.contexts.byId.values()].filter(isExtensionWorld);
  const select = run.request.ext ?? null;
  const pool = _worldsOf(worlds, select);
  if (pool.length === 0) {
    throw _noWorld(worlds, select);
  }
  const ids = [...new Set(pool.map((context) => String(extensionIdOf(context.origin))))];
  const id =
    ids.length === 1
      ? ids[0]
      : await extensionAmong(run.connection, ids, { ...run.request, ext: null }, "a content-script world on this page");
  const own = pool.filter((context) => extensionIdOf(context.origin) === id);
  const tree = await subject.page.send("Page.getFrameTree").catch(() => ({}));
  return (own.find((context) => context.auxData?.frameId === tree.frameTree?.frame?.id) ?? own[0]).id;
}

/**
 * `eval`: one expression evaluated in the target, awaited, returned by value, in the page's own world or, with
 * `world: "isolated"`, in the extension's content-script world on the page.
 * @param {Subject} subject
 * @param {{expression: string, world?: "page" | "isolated"}} spec
 * @param {Run} run
 * @returns {Promise<{type: string, value?: unknown, unserializable?: string, description?: string}>}
 * @throws {CdpError} with the exception's text when the expression throws
 */
async function _eval(subject, spec, run) {
  const contextId = spec.world === "isolated" ? await _isolatedWorld(subject, run) : null;
  const { type, value, unserializableValue, description } = await _evaluateIn(subject.page, spec.expression, contextId);
  return {
    type: String(type ?? "undefined"),
    ...(value === undefined ? {} : { value }),
    ...(unserializableValue === undefined ? {} : { unserializable: String(unserializableValue) }),
    ...(description === undefined ? {} : { description: String(description) }),
  };
}

/**
 * `selectors`: each name of a registry counted in the page, shadow roots included, and read as matched,
 * matched by a fallback or missing. It reads: the page is only queried.
 * @param {Subject} subject
 * @param {{registry: Record<string, string[]>}} spec
 * @returns {Promise<{findings: import("./selectors.mjs").SelectorFinding[]}>}
 * @throws {CdpError} when the page-side script throws
 */
async function _selectors(subject, spec) {
  const { value } = await _evaluateIn(subject.page, selectorExpression(spec.registry), null);
  return { findings: selectorFindings(spec.registry, /** @type {any} */ (value) ?? {}) };
}

/**
 * The text of an exception: its description (which carries the stack), else its message and place.
 * @param {{text?: string, url?: string, lineNumber?: number, exception?: {description?: string, value?: unknown}}} details
 * @returns {string}
 */
export function exceptionText(details) {
  const description =
    details.exception?.description ??
    (details.exception?.value === undefined ? undefined : String(details.exception.value));
  if (description !== undefined) {
    return description;
  }
  const place = details.url ? ` (${redactUrl(details.url, [])}:${(details.lineNumber ?? 0) + 1})` : "";
  return `${details.text ?? "exception"}${place}`;
}

/**
 * A console argument as text: its value, else a short preview of the object, else its description.
 * @param {{type?: string, value?: unknown, unserializableValue?: string, description?: string, className?: string, preview?: {properties?: {name: string, value?: string}[], overflow?: boolean}}} remote
 * @returns {string}
 */
export function remoteText(remote) {
  if (remote.value !== undefined) {
    return typeof remote.value === "string" ? remote.value : JSON.stringify(remote.value);
  }
  if (remote.unserializableValue !== undefined) {
    return remote.unserializableValue;
  }
  return _preview(remote) ?? remote.description ?? String(remote.type ?? "");
}

/**
 * An object's preview as `Class{a: 1, b: 2}`, or `null` when there is none worth showing (an error's
 * description already spans lines).
 * @param {{description?: string, className?: string, preview?: {properties?: {name: string, value?: string}[], overflow?: boolean}}} remote
 * @returns {string | null}
 */
function _preview(remote) {
  const properties = remote.preview?.properties;
  if (properties === undefined || remote.description?.includes("\n")) {
    return null;
  }
  const shown = properties.map((property) => `${property.name}: ${property.value}`).join(", ");
  return `${remote.className ?? remote.description ?? "Object"}{${shown}${remote.preview?.overflow ? ", …" : ""}}`;
}

/**
 * Wait for a promise or for the time to pass, whichever is first, and leave no timer behind.
 * @template T
 * @param {Promise<T>} promise
 * @param {number} ms
 * @returns {Promise<T | "timeout">}
 */
function _orTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve("timeout"), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

/**
 * One console or log line.
 * @typedef {object} LogEntry
 * @property {number} t seconds from the start of the capture; negative for a message from before it
 * @property {"page" | "extension" | "sw" | "popup"} source where it came from: the page's own world, an extension's content-script world on it, an extension's service worker, an extension page
 * @property {string} tag `console.<level>`, `exception` or `log.<source>`
 * @property {string} text
 */

/**
 * `logs`: the messages the target's console and log already hold, then those that arrive until `until`
 * matches a new line or the time is up. The regex is tried only against lines that arrive after the
 * replay, so an old line cannot end the wait, and against the line as printed, `[source] tag: text`.
 * @param {Subject} subject
 * @param {{until: string | null, seconds: number}} spec
 * @param {{deps: Deps, keys: readonly string[]}} how the clock, and the keys the text is scrubbed with: a
 *   line is scrubbed before it is kept or tested against `until`, so nothing printed or matched held a secret
 * @returns {Promise<{entries: LogEntry[], dropped: number, status: "matched" | "timeout" | "closed"}>}
 */
async function _logs(subject, spec, how) {
  const { deps, keys } = how;
  const { page } = subject;
  const start = deps.now();
  const until = spec.until === null ? null : new RegExp(spec.until);
  /** @type {LogEntry[]} */
  const entries = [];
  let dropped = 0;
  let live = false;
  let ended = false;
  /** @type {(status: "matched" | "closed") => void} */
  let finish = () => {};
  const finished = new Promise((resolve) => {
    finish = resolve;
  });
  /**
   * @param {string} tag
   * @param {string} text
   * @param {{at: number | undefined, context: number | undefined}} when the time, and the execution context the line came from
   */
  const add = (tag, text, when) => {
    if (ended) {
      return;
    }
    const source = subject.contexts.isExtensionWorld(when.context) ? "extension" : subject.source;
    const clean = scrubbedText(text, keys);
    const shown = clean.length > _MAX_TEXT ? `${clean.slice(0, _MAX_TEXT)}…` : clean;
    if (entries.length < _MAX_ENTRIES) {
      entries.push({ t: ((when.at ?? deps.now()) - start) / 1000, source, tag, text: shown });
    } else {
      dropped += 1;
    }
    if (until !== null && live && until.test(`[${source}] ${tag}: ${clean}`)) {
      ended = true;
      finish("matched");
    }
  };
  const unsubscribe = [
    page.on("Runtime.consoleAPICalled", (params) =>
      add(`console.${params.type}`, (params.args ?? []).map(remoteText).join(" "), {
        at: params.timestamp,
        context: params.executionContextId,
      }),
    ),
    page.on("Runtime.exceptionThrown", (params) =>
      add("exception", exceptionText(params.exceptionDetails ?? {}), {
        at: params.timestamp,
        context: params.exceptionDetails?.executionContextId,
      }),
    ),
    page.on("Log.entryAdded", (params) => {
      const entry = params.entry ?? {};
      add(`log.${entry.source}`, `${entry.text ?? ""}${entry.url ? ` (${redactUrl(entry.url, keys)})` : ""}`, {
        at: entry.timestamp,
        context: undefined,
      });
    }),
    page.onClose(() => finish("closed")),
  ];
  try {
    await subject.contexts.start();
    await page.send("Log.enable");
    live = true;
    const status = await _orTimeout(finished, spec.seconds * 1000);
    unsubscribe.forEach((off) => off());
    return { entries: [...entries].sort((a, b) => a.t - b.t), dropped, status };
  } finally {
    unsubscribe.forEach((off) => off());
  }
}

/**
 * One request the page made.
 * @typedef {object} NetEntry
 * @property {string} id
 * @property {string} method
 * @property {string} url the URL with secret query values redacted
 * @property {number | null} status
 * @property {string} type the resource type (`Fetch`, `XHR`, `Document` ...)
 * @property {string} mime
 * @property {number | null} size bytes on the wire
 * @property {number | null} ms from the request to the end of the response
 * @property {string | null} failure why the request failed, or `null`
 * @property {Record<string, string>} requestHeaders secrets redacted
 * @property {Record<string, string>} responseHeaders secrets redacted
 * @property {string} [body] a text or JSON body, redacted and within the cap
 * @property {boolean} [bodyTruncated]
 * @property {string} [bodyNote] why there is no body
 */

/**
 * The requests of a page, collected from `Network` events. A recording (`record-ops.mjs`) uses it too, with
 * `retain: false`: each request is handed to `onDone` and forgotten, so a long recording keeps nothing here.
 */
export class NetLog {
  /**
   * @param {readonly string[]} keys the JSON keys and query parameters to redact
   * @param {(entry: NetEntry) => void} onDone called when a request ends, in either way
   * @param {{retain?: boolean}} [options] `retain: false` keeps no entries and no open record after `onDone`
   */
  constructor(keys, onDone, options = {}) {
    this.keys = keys;
    this.onDone = onDone;
    this.retain = options.retain !== false;
    /** @type {NetEntry[]} */
    this.entries = [];
    this.dropped = 0;
    /** @type {Map<string, {entry: NetEntry, started: number, ended: boolean}>} */
    this.open = new Map();
  }

  /**
   * The open record of a request, made when only its answer was seen (a request begun before capture).
   * @param {string} id
   * @param {string} url
   * @returns {{entry: NetEntry, started: number, ended: boolean}}
   */
  #record(id, url) {
    let record = this.open.get(id);
    if (record === undefined) {
      /** @type {NetEntry} */
      const entry = {
        id,
        method: "",
        url: redactUrl(url, this.keys),
        status: null,
        type: "",
        mime: "",
        size: null,
        ms: null,
        failure: null,
        requestHeaders: {},
        responseHeaders: {},
      };
      record = { entry, started: Number.NaN, ended: false };
      this.open.set(id, record);
      if (!this.retain) {
        return record;
      }
      if (this.entries.length < _MAX_ENTRIES) {
        this.entries.push(entry);
      } else {
        this.dropped += 1;
      }
    }
    return record;
  }

  /**
   * @param {{requestId: string, type?: string, timestamp?: number, request: {url: string, method: string, headers?: Record<string, string>}, redirectResponse?: {status: number, mimeType?: string, headers?: Record<string, string>}}} params
   */
  requestWillBeSent(params) {
    const earlier = this.open.get(params.requestId);
    if (earlier !== undefined && params.redirectResponse !== undefined) {
      this.#answer(earlier.entry, params.redirectResponse);
      this.#end(earlier, params.timestamp);
      this.open.delete(params.requestId);
    }
    const record = this.#record(params.requestId, params.request.url);
    record.started = params.timestamp ?? Number.NaN;
    Object.assign(record.entry, {
      method: params.request.method,
      type: params.type ?? "",
      requestHeaders: redactHeaders(params.request.headers, this.keys),
    });
  }

  /**
   * @param {{requestId: string, type?: string, response: {url?: string, status: number, mimeType?: string, headers?: Record<string, string>}}} params
   */
  responseReceived(params) {
    const { entry } = this.#record(params.requestId, params.response.url ?? "");
    this.#answer(entry, params.response);
    entry.type = params.type ?? entry.type;
  }

  /**
   * @param {{requestId: string, timestamp?: number, encodedDataLength?: number}} params
   */
  loadingFinished(params) {
    const record = this.open.get(params.requestId);
    if (record !== undefined) {
      record.entry.size = params.encodedDataLength ?? null;
      this.#end(record, params.timestamp);
    }
  }

  /**
   * @param {{requestId: string, timestamp?: number, errorText?: string, blockedReason?: string, corsErrorStatus?: {corsError?: string}}} params
   */
  loadingFailed(params) {
    const record = this.open.get(params.requestId);
    if (record !== undefined) {
      const why = params.blockedReason ?? params.corsErrorStatus?.corsError;
      record.entry.failure = `${params.errorText ?? "failed"}${why === undefined ? "" : ` (${why})`}`;
      this.#end(record, params.timestamp);
    }
  }

  /**
   * @param {NetEntry} entry
   * @param {{status: number, mimeType?: string, headers?: Record<string, string>}} response
   */
  #answer(entry, response) {
    entry.status = response.status;
    entry.mime = response.mimeType ?? "";
    entry.responseHeaders = redactHeaders(response.headers, this.keys);
  }

  /**
   * @param {{entry: NetEntry, started: number, ended: boolean}} record
   * @param {number | undefined} timestamp
   */
  #end(record, timestamp) {
    if (record.ended) {
      return;
    }
    record.ended = true;
    if (timestamp !== undefined && !Number.isNaN(record.started)) {
      record.entry.ms = Math.round((timestamp - record.started) * 1000);
    }
    this.onDone(record.entry);
    if (!this.retain) {
      this.open.delete(record.entry.id);
    }
  }
}

/**
 * Whether a request counts as failed: a failure, or an HTTP status of 400 or more.
 * @param {NetEntry} entry
 * @returns {boolean}
 */
export function isFailed(entry) {
  return entry.failure !== null || (entry.status !== null && entry.status >= 400);
}

/**
 * Add the body of every finished text response: JSON and forms redacted by name, any other text scrubbed
 * (`redactBody`), all cut; a binary body is withheld with a note.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {NetEntry[]} entries
 * @param {{keys: readonly string[], maxBytes: number}} how
 * @returns {Promise<void>}
 */
async function _addBodies(page, entries, how) {
  for (const entry of entries) {
    if (entry.failure !== null || entry.status === null) {
      continue;
    }
    if (!textualMime(entry.mime)) {
      entry.bodyNote = `binary body not read (${entry.mime.split(";")[0] || "no type"})`;
      continue;
    }
    await _addBody(page, entry, how);
  }
}

/**
 * Add the redacted body of one finished text response, or the note that says why there is none.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {NetEntry} entry
 * @param {{keys: readonly string[], maxBytes: number}} how
 * @returns {Promise<void>}
 */
async function _addBody(page, entry, how) {
  try {
    const answer = await page.send("Network.getResponseBody", { requestId: entry.id }, _BODY_MS);
    if (answer.base64Encoded === true) {
      entry.bodyNote = "binary body not read";
      return;
    }
    const shown = redactBody(String(answer.body ?? ""), entry.mime, how);
    if (shown.note === null) {
      entry.body = shown.text;
      entry.bodyTruncated = shown.truncated;
    } else {
      entry.bodyNote = shown.note;
    }
  } catch (exc) {
    entry.bodyNote = exc instanceof Error ? exc.message : String(exc);
  }
}

/**
 * `net`: the requests the page makes while the capture runs. It reloads nothing: the traffic comes from
 * the page itself or from what the user does in the window.
 * @param {import("./cdp.mjs").PageSession} page
 * @param {{seconds: number, until: string | null, failed: boolean, bodies: boolean, maxBody: number}} spec
 * @param {string[]} keys
 * @returns {Promise<{entries: NetEntry[], dropped: number, status: "matched" | "timeout" | "closed"}>}
 */
async function _net(page, spec, keys) {
  const until = spec.until === null ? null : new RegExp(spec.until);
  /** @type {(status: "matched" | "closed") => void} */
  let finish = () => {};
  const finished = new Promise((resolve) => {
    finish = resolve;
  });
  /** @type {(() => void)[]} */
  let unsubscribe = [];
  const log = new NetLog(keys, (entry) => {
    if (until !== null && until.test(`${entry.method} ${entry.url} ${entry.failure ?? entry.status}`)) {
      // The capture ends at the match: what ends after it is not part of it.
      unsubscribe.forEach((off) => off());
      finish("matched");
    }
  });
  unsubscribe = [
    page.on("Network.requestWillBeSent", (params) => log.requestWillBeSent(params)),
    page.on("Network.responseReceived", (params) => log.responseReceived(params)),
    page.on("Network.loadingFinished", (params) => log.loadingFinished(params)),
    page.on("Network.loadingFailed", (params) => log.loadingFailed(params)),
    page.onClose(() => finish("closed")),
  ];
  try {
    await page.send("Network.enable");
    const status = await _orTimeout(finished, spec.seconds * 1000);
    // The capture ends here: a request that ends while the bodies are read is not part of it.
    unsubscribe.forEach((off) => off());
    const entries = spec.failed ? log.entries.filter(isFailed) : [...log.entries];
    if (spec.bodies && status !== "closed") {
      await _addBodies(page, entries, { keys, maxBytes: spec.maxBody });
    }
    return { entries, dropped: log.dropped, status };
  } finally {
    unsubscribe.forEach((off) => off());
  }
}

/** The operations that work on an attached target; the others work on the browser. */
const _TARGET_OPS = new Set(["snapshot", "screenshot", "eval", "logs", "net", "selectors"]);

/**
 * Run one operation.
 * @param {import("./protocol.mjs").Operation} spec
 * @param {Run} run
 * @returns {Promise<any>}
 */
async function _operate(spec, run) {
  const { subject } = run;
  if (_TARGET_OPS.has(spec.op) && subject === null) {
    throw new CdpError(`${spec.op}: no target is attached`);
  }
  switch (spec.op) {
    case "snapshot":
      return _snapshot(/** @type {Subject} */ (subject).page, spec);
    case "screenshot":
      return _screenshot(/** @type {Subject} */ (subject).page, spec);
    case "eval":
      return _eval(/** @type {Subject} */ (subject), spec, run);
    case "logs":
      return _logs(/** @type {Subject} */ (subject), spec, { deps: run.deps, keys: run.keys });
    case "net":
      return _net(/** @type {Subject} */ (subject).page, spec, run.keys);
    case "selectors":
      return _selectors(/** @type {Subject} */ (subject), spec);
    default:
      return _operateOnBrowser(spec, run);
  }
}

/**
 * Run an operation on the browser's extensions.
 * @param {import("./protocol.mjs").Operation} spec
 * @param {Run} run
 * @returns {Promise<any>}
 */
async function _operateOnBrowser(spec, run) {
  switch (spec.op) {
    case "ext-devmode":
      return turnDeveloperModeOn(run.connection);
    case "ext-list": {
      const paths = run.request.extensionPaths ?? [];
      const listed = await listExtensions(run.connection);
      return {
        extensions: listed.map((item) => ({
          ...item,
          configured: item.path !== null && paths.some((path) => samePath(path, String(item.path))),
        })),
      };
    }
    case "ext-reload":
      return reloadExtensions(run.connection, run.request);
    case "ext-action":
      return triggerAction(run.connection, run.targets, { request: run.request, readText: run.deps.readText });
    default:
      throw new CdpError(`unknown operation ${JSON.stringify(spec)}`);
  }
}

/**
 * Attach to the target the request's operations work on, when any of them does.
 * @param {import("./cdp.mjs").CdpConnection} connection
 * @param {readonly import("./targets.mjs").Target[]} targets
 * @param {import("./protocol.mjs").Request} request
 * @returns {Promise<{subject: Subject, target: import("./targets.mjs").Target} | null>} `null` when every operation works on the browser
 */
async function _attach(connection, targets, request) {
  if (!request.operations.some((spec) => _TARGET_OPS.has(spec.op))) {
    return null;
  }
  const { target, source } = await resolveSubject(connection, targets, request);
  const page = await attachToPage(connection, target.id);
  return { subject: { page, source, contexts: new _Contexts(page) }, target };
}

/**
 * Run every operation of a request in order, each an outcome of its own.
 * @param {Run} run
 * @returns {Promise<import("./protocol.mjs").Outcome[]>}
 */
async function _runAll(run) {
  /** @type {import("./protocol.mjs").Outcome[]} */
  const results = [];
  for (const spec of run.request.operations) {
    try {
      results.push({ ok: true, value: await _operate(spec, run) });
    } catch (exc) {
      results.push({ ok: false, error: exc instanceof Error ? exc.message : String(exc) });
    }
  }
  return results;
}

/**
 * Run a request: connect to the browser, attach to the target its target-bound operations work on (the
 * selected page by default; an extension's service worker or page, or a target id, when the request says),
 * run every operation in order, detach. A page is never closed or navigated. A failed operation is its own
 * outcome and the rest still run.
 * @param {import("./protocol.mjs").Request} request
 * @param {Deps} deps
 * @returns {Promise<import("./protocol.mjs").Response>}
 */
export async function runRequest(request, deps) {
  try {
    const targets = await fetchTargets(request.browserURL, deps.fetchJson);
    const version = await deps.fetchJson(`${request.browserURL}/json/version`);
    const connection = await connect(String(version.webSocketDebuggerUrl), deps.open);
    try {
      const attached = await _attach(connection, targets, request);
      const keys = redactFloor(request.redact);
      const results = await _runAll({ connection, targets, request, keys, deps, subject: attached?.subject ?? null });
      if (attached === null) {
        return { results };
      }
      await detachFromPage(connection, attached.subject.page);
      const { id, title, url } = attached.target;
      return { page: { id, title, url: redactUrl(url, keys) }, results };
    } finally {
      connection.close();
    }
  } catch (exc) {
    return { error: exc instanceof Error ? exc.message : String(exc) };
  }
}
