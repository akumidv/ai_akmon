/**
 * The Chrome side of a recording: attach to the page (or every page), inject the user-event listener, and turn
 * what the browser reports (navigations, the listener's events, console and exceptions, the network) into
 * recorded events handed to `emit` as they happen. It runs in `akmon tool browser`'s recorder process when
 * Chrome answers on this side, and in the CDP runner (`cdp-runner.mjs`) when only Windows reaches it, so
 * everything is redacted **here**, at capture, before an event leaves: the Linux side that follows only stamps
 * and appends. The module imports nothing outside Node and the runner's own modules.
 *
 * A page is never closed or navigated, and nothing is sent to a site: the recording only listens.
 */

import { attachToPage, CdpError, connect, detachFromPage } from "./cdp.mjs";
import { exceptionText, NetLog, remoteText } from "./ops.mjs";
import { userEventOf } from "./record-events.mjs";
import { disposeSource, listenerSource } from "./record-listener.mjs";
import { redactBody, redactFloor, redactUrl, scrubbedText } from "./redact.mjs";
import { fetchTargets, pageTargets, selectPage } from "./targets.mjs";

/** The window property the injected listener marks itself with. */
const FLAG = "__akmonRecorder";
/** How long typing must pause before the listener reports an `input` event, in milliseconds. */
const _DEBOUNCE_MS = 500;
/** How long a response body or a cleanup call may take, in milliseconds. */
const _BODY_MS = 5000;
const _CLEANUP_MS = 2000;
/** The longest a console line is kept, in characters. */
const _MAX_TEXT = 2000;

/**
 * What the recording asks of the machine it runs on, as `ops.mjs` does.
 * @typedef {Pick<import("./ops.mjs").Deps, "fetchJson" | "open" | "now">} Deps
 */

/**
 * Hand over one recorded event. `ago` is how long before now the thing began, when it is not now (a request is
 * handed over when it ends).
 * @typedef {(event: Record<string, unknown>, ago?: number) => void} Emit
 */

/**
 * A recording that is running.
 * @typedef {object} RecordingHandle
 * @property {string[]} pages the labels of the pages attached at the start
 * @property {Promise<{reason: "closed" | "stopped" | "error", error: string | null}>} ended resolves when the recording is over
 * @property {() => Promise<void>} stop end it: remove the injected listener where possible, detach, close
 */

/**
 * One page being recorded.
 * @typedef {object} Watch
 * @property {string} label `p1`, `p2` ... in the order the pages were attached
 * @property {import("./cdp.mjs").PageSession} page
 * @property {string | null} scriptId the injected script, for its removal
 * @property {string | null} mainFrame the id of the page's main frame
 * @property {(() => void)[]} off
 */

/**
 * @param {string} mime
 * @returns {"json" | "form" | null} the kind of body a recording keeps, which it can redact
 */
function _bodyKind(mime) {
  const type = mime.split(";")[0].trim().toLowerCase();
  if (type === "application/json" || type.endsWith("+json")) {
    return "json";
  }
  return type === "application/x-www-form-urlencoded" ? "form" : null;
}

/**
 * The value of a header, whatever the case of its name.
 * @param {Record<string, string> | undefined} headers
 * @param {string} name lower case
 * @returns {string}
 */
function _header(headers, name) {
  for (const [key, value] of Object.entries(headers ?? {})) {
    if (key.toLowerCase() === name) {
      return value;
    }
  }
  return "";
}

/**
 * @param {string} text
 * @returns {string}
 */
function _capped(text) {
  return text.length > _MAX_TEXT ? `${text.slice(0, _MAX_TEXT)}…` : text;
}

/**
 * Await a promise and drop its failure: for cleanup, where a page that is gone is not an error.
 * @param {Promise<unknown>} promise
 * @returns {Promise<void>}
 */
async function _quiet(promise) {
  try {
    await promise;
  } catch {
    // The page or the browser is already gone: there is nothing to undo.
  }
}

/** One recording's Chrome side. */
class _Recording {
  /**
   * @param {import("./cdp.mjs").CdpConnection} connection
   * @param {import("./stream-protocol.mjs").RecordRequest} request
   * @param {{deps: Deps, emit: Emit}} how
   */
  constructor(connection, request, how) {
    this.connection = connection;
    this.request = request;
    this.deps = how.deps;
    this.keys = redactFloor(request.redact);
    this.source = listenerSource({
      binding: request.binding,
      keys: this.keys,
      flag: FLAG,
      debounceMs: _DEBOUNCE_MS,
    });
    this.sink = how.emit;
    /** @type {Map<string, Watch>} by target id */
    this.watches = new Map();
    this.count = 0;
    this.stopped = false;
    /** @type {Promise<void> | null} */
    this.stopping = null;
    /** @type {(outcome: {reason: "closed" | "stopped" | "error", error: string | null}) => void} */
    this.finish = () => {};
    this.ended = new Promise((resolve) => {
      this.finish = resolve;
    });
  }

  /**
   * Hand an event over; a sink that fails ends the recording, because events would be lost.
   * @param {Record<string, unknown>} event
   * @param {number} [ago]
   */
  emit(event, ago = 0) {
    if (this.stopped) {
      return;
    }
    try {
      this.sink(event, ago);
    } catch (exc) {
      this.finish({
        reason: "error",
        error: `could not write an event (${exc instanceof Error ? exc.message : String(exc)})`,
      });
    }
  }

  /**
   * Follow a page: listen first, then enable what is reported, then inject the listener.
   * @param {import("./targets.mjs").Target} target
   * @returns {Promise<void>}
   */
  async attach(target) {
    if (this.watches.has(target.id) || this.stopped) {
      return;
    }
    const page = await attachToPage(this.connection, target.id);
    /** @type {Watch} */
    const watch = { label: `p${++this.count}`, page, scriptId: null, mainFrame: null, off: [] };
    this.watches.set(target.id, watch);
    this.#listen(watch);
    for (const domain of ["Page", "Runtime", "Network", "Log"]) {
      await page.send(`${domain}.enable`);
    }
    try {
      const tree = await page.send("Page.getFrameTree");
      watch.mainFrame = tree.frameTree?.frame?.id ?? null;
    } catch {
      // Without the frame id, a same-document navigation of a frame is read as the page's: harmless.
    }
    this.emit({ kind: "page", page: watch.label, url: redactUrl(target.url, this.keys), title: target.title });
    await this.#inject(watch);
  }

  /**
   * Add the binding and the listener to a page: on every document to come, and on the one that is open.
   * @param {Watch} watch
   * @returns {Promise<void>}
   */
  async #inject(watch) {
    try {
      await watch.page.send("Runtime.addBinding", { name: this.request.binding });
      const added = await watch.page.send("Page.addScriptToEvaluateOnNewDocument", { source: this.source });
      watch.scriptId = typeof added.identifier === "string" ? added.identifier : null;
      const now = await watch.page.send("Runtime.evaluate", { expression: this.source });
      if (now.exceptionDetails !== undefined) {
        throw new CdpError(exceptionText(now.exceptionDetails));
      }
    } catch (exc) {
      this.emit({
        kind: "warning",
        page: watch.label,
        text: `the user-event listener could not be installed (${exc instanceof Error ? exc.message : String(exc)}); navigations, console and network are still recorded`,
      });
    }
  }

  /**
   * Subscribe to everything a page reports.
   * @param {Watch} watch
   */
  #listen(watch) {
    const { page, label } = watch;
    const keys = this.keys;
    watch.off.push(
      page.on("Page.frameNavigated", (params) => {
        if (params.frame?.parentId === undefined) {
          watch.mainFrame = params.frame?.id ?? watch.mainFrame;
          this.emit({ kind: "navigation", page: label, url: redactUrl(String(params.frame?.url ?? ""), keys) });
        }
      }),
      page.on("Page.navigatedWithinDocument", (params) => {
        if (watch.mainFrame === null || params.frameId === watch.mainFrame) {
          this.emit({ kind: "navigation", page: label, url: redactUrl(String(params.url ?? ""), keys), within: true });
        }
      }),
      page.on("Runtime.bindingCalled", (params) => {
        const event = params.name === this.request.binding ? userEventOf(String(params.payload ?? ""), keys) : null;
        if (event !== null) {
          const { kind, ...rest } = event;
          this.emit({ kind, page: label, ...rest });
        }
      }),
      page.on("Runtime.consoleAPICalled", (params) =>
        this.emit({
          kind: "console",
          page: label,
          level: String(params.type ?? "log"),
          text: _capped(scrubbedText((params.args ?? []).map(remoteText).join(" "), keys)),
        }),
      ),
      page.on("Runtime.exceptionThrown", (params) =>
        this.emit({
          kind: "exception",
          page: label,
          text: _capped(scrubbedText(exceptionText(params.exceptionDetails ?? {}), keys)),
        }),
      ),
      page.on("Log.entryAdded", (params) => {
        const entry = params.entry ?? {};
        this.emit({
          kind: "log",
          page: label,
          source: String(entry.source ?? ""),
          level: String(entry.level ?? ""),
          text: _capped(
            scrubbedText(`${entry.text ?? ""}${entry.url ? ` (${redactUrl(entry.url, keys)})` : ""}`, keys),
          ),
        });
      }),
      ...this.#listenNetwork(watch),
    );
  }

  /**
   * Subscribe to the page's requests: each is emitted when it ends, with the time it began.
   * @param {Watch} watch
   * @returns {(() => void)[]}
   */
  #listenNetwork(watch) {
    const { page, label } = watch;
    /** @type {Map<string, number>} when each open request began, on this machine's clock */
    const started = new Map();
    /** @type {Map<string, {body?: string, truncated?: boolean, note?: string}>} */
    const requestBodies = new Map();
    const log = new NetLog(
      this.keys,
      (entry) => {
        const began = started.get(entry.id) ?? this.deps.now();
        const sent = requestBodies.get(entry.id);
        started.delete(entry.id);
        requestBodies.delete(entry.id);
        this.#finishRequest(watch, entry, { began, sent }).catch((exc) =>
          this.emit({ kind: "warning", page: label, text: exc instanceof Error ? exc.message : String(exc) }),
        );
      },
      { retain: false },
    );
    return [
      page.on("Network.requestWillBeSent", (params) => {
        log.requestWillBeSent(params);
        started.set(params.requestId, this.deps.now());
        if (this.request.bodies) {
          requestBodies.set(params.requestId, this.#requestBody(params.request ?? {}));
        }
      }),
      page.on("Network.responseReceived", (params) => log.responseReceived(params)),
      page.on("Network.loadingFinished", (params) => log.loadingFinished(params)),
      page.on("Network.loadingFailed", (params) => log.loadingFailed(params)),
    ];
  }

  /**
   * The body a request sent, redacted and capped, or the note that says why there is none.
   * @param {{postData?: string, hasPostData?: boolean, headers?: Record<string, string>}} request
   * @returns {{body?: string, truncated?: boolean, note?: string}}
   */
  #requestBody(request) {
    if (request.postData === undefined) {
      return request.hasPostData === true ? { note: "request body not read" } : {};
    }
    const mime = _header(request.headers, "content-type");
    if (_bodyKind(mime) === null) {
      return {
        note: `request body not kept (${mime.split(";")[0] || "no content type"}): only JSON and forms can be redacted`,
      };
    }
    const shown = redactBody(request.postData, mime, { keys: this.keys, maxBytes: this.request.maxBody });
    return shown.note === null ? { body: shown.text, truncated: shown.truncated } : { note: shown.note };
  }

  /**
   * Emit a request that has ended, with its response body when bodies are kept.
   * @param {Watch} watch
   * @param {import("./ops.mjs").NetEntry} entry
   * @param {{began: number, sent: {body?: string, truncated?: boolean, note?: string} | undefined}} when
   * @returns {Promise<void>}
   */
  async #finishRequest(watch, entry, when) {
    /** @type {Record<string, unknown>} */
    const event = { kind: "net", page: watch.label, ...entry };
    if (when.sent !== undefined && Object.keys(when.sent).length > 0) {
      event["requestBody"] = when.sent.body;
      event["requestBodyTruncated"] = when.sent.truncated;
      event["requestBodyNote"] = when.sent.note;
    }
    if (this.request.bodies && entry.failure === null && entry.status !== null) {
      Object.assign(event, await this.#responseBody(watch, entry));
    }
    this.emit(event, this.deps.now() - when.began);
  }

  /**
   * The response body of a finished request, redacted and capped, or the note that says why there is none.
   * @param {Watch} watch
   * @param {import("./ops.mjs").NetEntry} entry
   * @returns {Promise<Record<string, unknown>>}
   */
  async #responseBody(watch, entry) {
    if (_bodyKind(entry.mime) === null) {
      return { bodyNote: `not kept (${entry.mime.split(";")[0] || "no type"}): only JSON and forms can be redacted` };
    }
    try {
      const answer = await watch.page.send("Network.getResponseBody", { requestId: entry.id }, _BODY_MS);
      if (answer.base64Encoded === true) {
        return { bodyNote: "binary body not read" };
      }
      const shown = redactBody(String(answer.body ?? ""), entry.mime, {
        keys: this.keys,
        maxBytes: this.request.maxBody,
      });
      return shown.note === null ? { body: shown.text, bodyTruncated: shown.truncated } : { bodyNote: shown.note };
    } catch (exc) {
      return { bodyNote: exc instanceof Error ? exc.message : String(exc) };
    }
  }

  /**
   * A page target went away: stop following it; with nothing left to follow, the recording is over.
   * @param {string} targetId
   */
  forget(targetId) {
    const watch = this.watches.get(targetId);
    if (watch === undefined) {
      return;
    }
    watch.off.forEach((off) => off());
    this.watches.delete(targetId);
    this.emit({ kind: "warning", page: watch.label, text: "the page was closed" });
    if (this.watches.size === 0 && !this.request.allPages) {
      this.finish({ reason: "closed", error: null });
    }
  }

  /**
   * End the recording: take the listener out of every page where that is possible, detach, close.
   * @returns {Promise<void>}
   */
  stop() {
    this.stopping ??= this.#end();
    return this.stopping;
  }

  /**
   * @returns {Promise<void>}
   */
  async #end() {
    for (const watch of this.watches.values()) {
      const { page } = watch;
      if (watch.scriptId !== null) {
        await _quiet(
          page.send("Page.removeScriptToEvaluateOnNewDocument", { identifier: watch.scriptId }, _CLEANUP_MS),
        );
      }
      await _quiet(page.send("Runtime.evaluate", { expression: disposeSource(FLAG) }, _CLEANUP_MS));
      await _quiet(page.send("Runtime.removeBinding", { name: this.request.binding }, _CLEANUP_MS));
      watch.off.forEach((off) => off());
      await detachFromPage(this.connection, page);
    }
    this.stopped = true;
    this.finish({ reason: "stopped", error: null });
    this.connection.close();
  }
}

/**
 * Start recording: connect to the browser, attach to the page the request names (every page with
 * `allPages`, and those that open later), inject the listener and begin handing events to `emit`.
 * @param {import("./stream-protocol.mjs").RecordRequest} request
 * @param {Deps} deps
 * @param {Emit} emit
 * @returns {Promise<RecordingHandle>}
 * @throws {CdpError} when there is no browser, no such page, or a page cannot be attached; nothing is left attached
 */
export async function startRecording(request, deps, emit) {
  const targets = await fetchTargets(request.browserURL, deps.fetchJson);
  const initial = request.allPages ? pageTargets(targets) : [selectPage(targets, request.page)];
  if (initial.length === 0) {
    selectPage(targets, null);
  }
  const version = await deps.fetchJson(`${request.browserURL}/json/version`);
  const connection = await connect(String(version.webSocketDebuggerUrl), deps.open);
  const recording = new _Recording(connection, request, { deps, emit });
  try {
    connection.onClose(() => recording.finish({ reason: "closed", error: null }));
    connection.on("Target.targetDestroyed", (params) => recording.forget(String(params.targetId)));
    if (request.allPages) {
      connection.on("Target.targetCreated", (params) => {
        const info = params.targetInfo ?? {};
        if (info.type === "page") {
          recording
            .attach({
              id: String(info.targetId),
              type: "page",
              title: String(info.title ?? ""),
              url: String(info.url ?? ""),
            })
            .catch(() => {
              // A page that closed before it could be attached is not one to record.
            });
        }
      });
    }
    await connection.send("Target.setDiscoverTargets", { discover: true });
    for (const target of initial) {
      await recording.attach(target);
    }
  } catch (exc) {
    await recording.stop();
    throw exc;
  }
  return {
    pages: [...recording.watches.values()].map((watch) => watch.label),
    ended: recording.ended,
    stop: () => recording.stop(),
  };
}
