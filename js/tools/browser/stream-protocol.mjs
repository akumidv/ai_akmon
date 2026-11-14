/**
 * What crosses between the recorder and the CDP runner when a recording's Chrome side runs on Windows
 * (a Windows Chrome under WSL, which only a Windows process reaches): the recorder writes one request line
 * on the runner's stdin and keeps stdin open, the runner answers with one message per line on stdout, and
 * the end of stdin (or a `stop` line) is the order to stop. Every line is one JSON object. The events in the
 * lines were redacted on the Windows side already; the Linux side only stamps and appends them. Pure, with no
 * import outside Node: the runner loads it from `\\wsl.localhost`.
 */

/**
 * What a recording's Chrome side is asked to do.
 * @typedef {object} RecordRequest
 * @property {string} browserURL `http://127.0.0.1:<port>`, read from the side Chrome is reached from
 * @property {string | null} page the `--page` selector; `null` for the first page
 * @property {boolean} allPages record every page, and the ones that open later
 * @property {boolean} bodies keep request and response bodies, redacted and capped
 * @property {number} maxBody the cap of a body, in bytes
 * @property {string[]} redact the project's own redact keys; the floor is added on the Chrome side
 * @property {string} binding the name of the CDP binding the listener reports through
 */

/**
 * What the runner says, one per line.
 * @typedef {{ready: {pages: string[]}}
 *   | {ev: Record<string, unknown>, ago: number}
 *   | {error: string}
 *   | {end: {reason: "closed" | "stopped" | "error", error: string | null}}
 * } StreamMessage
 */

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function _isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * A request as the first line of the runner's stdin.
 * @param {RecordRequest} request
 * @returns {string} one line, with its newline
 */
export function encodeStreamRequest(request) {
  return `${JSON.stringify({ stream: "record", ...request })}\n`;
}

/**
 * Whether a line is a streaming request, so the runner knows which of its two modes it is in.
 * @param {string} line
 * @returns {boolean}
 */
export function isStreamRequest(line) {
  try {
    const data = JSON.parse(line);
    return _isObject(data) && data["stream"] === "record";
  } catch {
    return false;
  }
}

/**
 * @param {unknown} data
 * @returns {data is Record<string, unknown>} whether the fields that name the browser and the page are right
 */
function _namesBrowser(data) {
  return (
    _isObject(data) &&
    typeof data["browserURL"] === "string" &&
    (data["page"] === null || typeof data["page"] === "string")
  );
}

/**
 * @param {Record<string, unknown>} data
 * @throws {Error} naming the field that is wrong
 */
function _checkOptions(data) {
  if (typeof data["allPages"] !== "boolean" || typeof data["bodies"] !== "boolean") {
    throw new Error('the stream request needs "allPages" and "bodies" as booleans');
  }
  const { maxBody, redact, binding } = data;
  if (typeof maxBody !== "number" || !Number.isFinite(maxBody) || maxBody <= 0) {
    throw new Error('the stream request needs a positive "maxBody"');
  }
  if (!Array.isArray(redact) || !redact.every((key) => typeof key === "string")) {
    throw new Error('the stream request\'s "redact" is not a list of strings');
  }
  if (typeof binding !== "string" || !/^[A-Za-z_$][\w$]*$/.test(binding)) {
    throw new Error('the stream request needs a "binding" that is a plain name');
  }
}

/**
 * A request read from its line, validated: the boundary where the runner's stdin enters.
 * @param {string} line
 * @returns {RecordRequest}
 * @throws {Error} naming what is wrong
 */
export function decodeStreamRequest(line) {
  /** @type {unknown} */
  let data;
  try {
    data = JSON.parse(line);
  } catch (exc) {
    throw new Error(`the stream request is not JSON (${exc instanceof Error ? exc.message : String(exc)})`, {
      cause: exc,
    });
  }
  if (!_isObject(data) || data["stream"] !== "record") {
    throw new Error('the stream request needs "stream": "record"');
  }
  if (!_namesBrowser(data)) {
    throw new Error('the stream request needs a "browserURL" string and a "page" string or null');
  }
  _checkOptions(data);
  return /** @type {RecordRequest} */ ({
    browserURL: data["browserURL"],
    page: data["page"],
    allPages: data["allPages"],
    bodies: data["bodies"],
    maxBody: data["maxBody"],
    redact: data["redact"],
    binding: data["binding"],
  });
}

/**
 * A message as one line.
 * @param {StreamMessage} message
 * @returns {string} one line, with its newline
 */
export function encodeStreamMessage(message) {
  return `${JSON.stringify(message)}\n`;
}

/**
 * The order to stop, as a line the runner reads from stdin (the end of stdin means the same).
 * @returns {string}
 */
export function stopLine() {
  return `${JSON.stringify({ stop: true })}\n`;
}

/**
 * A message read from its line.
 * @param {string} line
 * @returns {StreamMessage}
 * @throws {Error} when the line is not a message
 */
export function decodeStreamMessage(line) {
  /** @type {unknown} */
  let data;
  try {
    data = JSON.parse(line);
  } catch (exc) {
    throw new Error(`the runner's line is not JSON (${exc instanceof Error ? exc.message : String(exc)})`, {
      cause: exc,
    });
  }
  if (
    !_isObject(data) ||
    !(
      _isObject(data["ready"]) ||
      (_isObject(data["ev"]) && typeof data["ago"] === "number") ||
      typeof data["error"] === "string" ||
      _isObject(data["end"])
    )
  ) {
    throw new Error("the runner's line is none of ready, ev, error and end");
  }
  return /** @type {StreamMessage} */ (data);
}

/**
 * Splits a stream of text chunks into lines: a line is whole only once its newline has arrived.
 */
export class LineBuffer {
  #rest = "";

  /**
   * Take a chunk.
   * @param {string} chunk
   * @returns {string[]} the lines it completed, without newlines, blank ones left out
   */
  push(chunk) {
    this.#rest += chunk;
    const parts = this.#rest.split("\n");
    this.#rest = parts.pop() ?? "";
    return parts.map((line) => line.replace(/\r$/, "")).filter((line) => line.trim() !== "");
  }

  /**
   * The text of a last line that never got its newline.
   * @returns {string}
   */
  rest() {
    return this.#rest;
  }
}
