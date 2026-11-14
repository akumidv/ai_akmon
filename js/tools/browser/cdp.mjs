/**
 * A minimal Chrome DevTools protocol client over Node's global `WebSocket` (no npm dependency): one
 * connection to a browser's `webSocketDebuggerUrl`, calls with ids and a timeout each, event
 * subscription, and a flattened session on a page. The transport is a small interface, so the verbs are
 * tested against a fake one. The module imports nothing outside Node: the CDP runner loads it on the
 * Windows side too (`cdp-runner.mjs`).
 */

/** How long a call may take when the caller names no timeout, in milliseconds. */
export const DEFAULT_TIMEOUT_MS = 10_000;

/** A failure of the protocol or of the connection, stated in one line. */
export class CdpError extends Error {
  /**
   * @param {string} message
   */
  constructor(message) {
    super(message);
    this.name = "CdpError";
  }
}

/**
 * The wire under a connection: text frames both ways. The connection sets `onmessage` and `onclose`.
 * @typedef {object} Transport
 * @property {(text: string) => void} send
 * @property {() => void} close
 * @property {((text: string) => void) | null} onmessage
 * @property {((reason: string) => void) | null} onclose
 */

/**
 * Open a WebSocket as a transport.
 * @param {string} url a `ws://` DevTools URL
 * @param {number} [timeoutMs] how long the connection may take to open
 * @returns {Promise<Transport>}
 * @throws {CdpError} when it does not open in time or is refused
 */
export function openTransport(url, timeoutMs = DEFAULT_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    /** @type {Transport} */
    const transport = {
      send: (text) => socket.send(text),
      close: () => socket.close(),
      onmessage: null,
      onclose: null,
    };
    const timer = setTimeout(() => {
      reject(new CdpError(`${url} did not open within ${timeoutMs} ms`));
      socket.close();
    }, timeoutMs);
    socket.onopen = () => {
      clearTimeout(timer);
      resolve(transport);
    };
    socket.onerror = () => {
      clearTimeout(timer);
      reject(new CdpError(`could not connect to ${url}`));
    };
    socket.onmessage = (event) => transport.onmessage?.(String(event.data));
    socket.onclose = () => transport.onclose?.("the browser closed the connection");
  });
}

/**
 * One call waiting for its answer.
 * @typedef {object} Pending
 * @property {string} method
 * @property {(result: any) => void} resolve
 * @property {(error: Error) => void} reject
 * @property {ReturnType<typeof setTimeout>} timer
 */

/** One browser connection and everything flattened onto it: the browser's own calls and its sessions. */
export class CdpConnection {
  /** @type {Transport} */
  #transport;
  #nextId = 1;
  /** @type {Map<number, Pending>} */
  #pending = new Map();
  /** @type {Map<string, Set<(params: any) => void>>} handlers by `<session>|<method>` */
  #handlers = new Map();
  /** @type {Set<() => void>} */
  #closeHandlers = new Set();
  #closed = false;

  /**
   * @param {Transport} transport
   */
  constructor(transport) {
    this.#transport = transport;
    transport.onmessage = (text) => this.#receive(text);
    transport.onclose = (reason) => this.#lost(reason);
  }

  /** Whether the connection has ended. */
  get closed() {
    return this.#closed;
  }

  /**
   * Call a protocol method and wait for its result.
   * @param {string} method
   * @param {Record<string, unknown>} [params]
   * @param {{sessionId?: string, timeoutMs?: number}} [options] `sessionId` addresses a page session
   * @returns {Promise<any>}
   * @throws {CdpError} on an error answer, a timeout, or a connection that has ended
   */
  send(method, params = {}, options = {}) {
    if (this.#closed) {
      return Promise.reject(new CdpError(`${method}: the browser connection is closed`));
    }
    const id = this.#nextId++;
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pending.delete(id);
        reject(new CdpError(`${method}: no answer within ${timeoutMs} ms`));
      }, timeoutMs);
      this.#pending.set(id, { method, resolve, reject, timer });
      const message = {
        id,
        method,
        params,
        ...(options.sessionId === undefined ? {} : { sessionId: options.sessionId }),
      };
      try {
        this.#transport.send(JSON.stringify(message));
      } catch (exc) {
        clearTimeout(timer);
        this.#pending.delete(id);
        reject(new CdpError(`${method}: could not be sent (${exc instanceof Error ? exc.message : String(exc)})`));
      }
    });
  }

  /**
   * Subscribe to an event of the browser, or of one session.
   * @param {string} method the event, such as `Runtime.consoleAPICalled`
   * @param {(params: any) => void} handler
   * @param {string} [sessionId] a session's events; the browser's own when absent
   * @returns {() => void} unsubscribes
   */
  on(method, handler, sessionId = "") {
    const key = `${sessionId}|${method}`;
    const set = this.#handlers.get(key) ?? new Set();
    set.add(handler);
    this.#handlers.set(key, set);
    return () => {
      set.delete(handler);
    };
  }

  /**
   * Call a function when the connection ends, whoever ended it.
   * @param {() => void} handler
   * @returns {() => void} unsubscribes
   */
  onClose(handler) {
    this.#closeHandlers.add(handler);
    return () => {
      this.#closeHandlers.delete(handler);
    };
  }

  /** Close the connection; calls still waiting fail. */
  close() {
    if (!this.#closed) {
      this.#transport.close();
      this.#lost("the connection was closed");
    }
  }

  /**
   * @param {string} text one frame
   */
  #receive(text) {
    /** @type {any} */
    let message;
    try {
      message = JSON.parse(text);
    } catch {
      return;
    }
    if (typeof message.id === "number") {
      this.#answer(message);
    } else if (typeof message.method === "string") {
      for (const handler of [...(this.#handlers.get(`${message.sessionId ?? ""}|${message.method}`) ?? [])]) {
        handler(message.params ?? {});
      }
    }
  }

  /**
   * @param {{id: number, result?: any, error?: {message?: string, code?: number}}} message
   */
  #answer(message) {
    const pending = this.#pending.get(message.id);
    if (pending === undefined) {
      return;
    }
    this.#pending.delete(message.id);
    clearTimeout(pending.timer);
    if (message.error === undefined) {
      pending.resolve(message.result ?? {});
    } else {
      pending.reject(new CdpError(`${pending.method}: ${message.error.message ?? JSON.stringify(message.error)}`));
    }
  }

  /**
   * @param {string} reason
   */
  #lost(reason) {
    if (this.#closed) {
      return;
    }
    this.#closed = true;
    for (const pending of this.#pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(new CdpError(`${pending.method}: ${reason}`));
    }
    this.#pending.clear();
    for (const handler of [...this.#closeHandlers]) {
      handler();
    }
  }
}

/** A flattened session on one page: calls and events addressed to it. */
export class PageSession {
  /** @type {CdpConnection} */
  #connection;

  /**
   * @param {CdpConnection} connection
   * @param {string} sessionId
   * @param {string} targetId
   */
  constructor(connection, sessionId, targetId) {
    this.#connection = connection;
    this.sessionId = sessionId;
    this.targetId = targetId;
  }

  /**
   * Call a method on the page.
   * @param {string} method
   * @param {Record<string, unknown>} [params]
   * @param {number} [timeoutMs]
   * @returns {Promise<any>}
   */
  send(method, params = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
    return this.#connection.send(method, params, { sessionId: this.sessionId, timeoutMs });
  }

  /**
   * Subscribe to an event of the page.
   * @param {string} method
   * @param {(params: any) => void} handler
   * @returns {() => void} unsubscribes
   */
  on(method, handler) {
    return this.#connection.on(method, handler, this.sessionId);
  }

  /**
   * Call a function when the connection under the page ends.
   * @param {() => void} handler
   * @returns {() => void} unsubscribes
   */
  onClose(handler) {
    return this.#connection.onClose(handler);
  }
}

/**
 * Attach to a page target with a flattened session; the page is never closed, only detached from.
 * @param {CdpConnection} connection
 * @param {string} targetId
 * @param {number} [timeoutMs]
 * @returns {Promise<PageSession>}
 */
export async function attachToPage(connection, targetId, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const { sessionId } = await connection.send("Target.attachToTarget", { targetId, flatten: true }, { timeoutMs });
  if (typeof sessionId !== "string") {
    throw new CdpError(`Target.attachToTarget: no session for target ${targetId}`);
  }
  return new PageSession(connection, sessionId, targetId);
}

/**
 * Detach from a page, ignoring a failure: the page may be gone.
 * @param {CdpConnection} connection
 * @param {PageSession} page
 * @returns {Promise<void>}
 */
export async function detachFromPage(connection, page) {
  try {
    await connection.send("Target.detachFromTarget", { sessionId: page.sessionId }, { timeoutMs: 2000 });
  } catch {
    // The page or the browser is already gone: nothing is left attached.
  }
}

/**
 * Connect to a browser's DevTools WebSocket.
 * @param {string} webSocketUrl
 * @param {(url: string) => Promise<Transport>} [open] how the wire opens; the real WebSocket by default
 * @returns {Promise<CdpConnection>}
 */
export async function connect(webSocketUrl, open = openTransport) {
  return new CdpConnection(await open(webSocketUrl));
}
