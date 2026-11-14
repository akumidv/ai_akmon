/**
 * What crosses between `akmon tool browser` and the CDP runner that does the Chrome side of a verb on
 * Windows: one JSON request on the runner's stdin, one JSON response on its stdout. The same request
 * shape drives the run in this process when Chrome answers here, so both paths take one code path.
 * Pure, with no import outside Node: the runner loads it from `\\wsl.localhost`.
 */

/**
 * @typedef {object} Viewport
 * @property {number} width CSS pixels
 * @property {number} height
 */

/**
 * One operation on a page, by `op`. Everything a verb decides (a preset's size, the default numbers) is
 * resolved before the request is made, so the runner holds no settings. `eval` runs in the page's own world
 * unless `world` is `isolated`, the extension's content-script world; `selectors` checks a registry of
 * `{name: [css selector, fallback, ...]}`; the `ext-*` operations work on the browser's extensions (developer
 * mode, the list, a reload, the action of an extension on the selected page) and need no attached target.
 * @typedef {{op: "snapshot", maxNodes: number, text: boolean}
 *   | {op: "screenshot", viewport: Viewport | null, scheme: "light" | "dark" | null, full: boolean}
 *   | {op: "eval", expression: string, world?: "page" | "isolated"}
 *   | {op: "logs", until: string | null, seconds: number}
 *   | {op: "net", seconds: number, until: string | null, failed: boolean, bodies: boolean, maxBody: number}
 *   | {op: "selectors", registry: Record<string, string[]>}
 *   | {op: "ext-devmode"}
 *   | {op: "ext-list"}
 *   | {op: "ext-reload"}
 *   | {op: "ext-action"}
 * } Operation
 */

/**
 * @typedef {object} Request
 * @property {string} browserURL `http://127.0.0.1:<port>`, read from the side Chrome is reached from
 * @property {string | null} page the `--page` selector, `null` for the default page
 * @property {string} [target] what the operations run on: `page` (default), `sw` (an extension's service worker), `popup` (an open extension page) or a target id
 * @property {string | null} [ext] the extension an `sw` or `popup` target, an `isolated` world or an `ext-*` operation means: an id or a name; `null` for the configured one
 * @property {string[]} [extensionPaths] the configured extensions' folders as Chrome sees them, which tell the configured ones apart
 * @property {string[]} redact the JSON keys and query parameters redacted at capture
 * @property {Operation[]} operations run in order, on one connection
 */

/**
 * The outcome of one operation: its value, or the one line that says why it failed.
 * @typedef {{ok: true, value: any} | {ok: false, error: string}} Outcome
 */

/**
 * @typedef {object} Response
 * @property {{id: string, title: string, url: string}} [page] the page the operations ran on
 * @property {Outcome[]} [results] one per operation, in order
 * @property {string} [error] the run failed as a whole (no browser, no such page)
 */

/** The operations a request may name. */
const _OPS = [
  "snapshot",
  "screenshot",
  "eval",
  "logs",
  "net",
  "selectors",
  "ext-devmode",
  "ext-list",
  "ext-reload",
  "ext-action",
];

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function _isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * @param {unknown} value
 * @returns {value is number}
 */
function _isPositive(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
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
 * @returns {value is string | null}
 */
function _isStringOrNull(value) {
  return value === null || typeof value === "string";
}

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function _isViewportOrNull(value) {
  return value === null || (_isObject(value) && _isPositive(value["width"]) && _isPositive(value["height"]));
}

/**
 * @param {unknown} value
 * @returns {boolean}
 */
function _isRegistry(value) {
  return (
    _isObject(value) &&
    Object.values(value).every(
      (list) => Array.isArray(list) && list.length > 0 && list.every((css) => typeof css === "string" && css !== ""),
    )
  );
}

/**
 * Each operation's check of its own fields.
 * @type {Record<string, (spec: Record<string, unknown>) => boolean>}
 */
const _VALID = {
  snapshot: (spec) => _isPositive(spec["maxNodes"]) && typeof spec["text"] === "boolean",
  screenshot: (spec) =>
    _isViewportOrNull(spec["viewport"]) &&
    [null, "light", "dark"].includes(/** @type {string | null} */ (spec["scheme"])) &&
    typeof spec["full"] === "boolean",
  eval: (spec) =>
    typeof spec["expression"] === "string" &&
    (spec["world"] === undefined || spec["world"] === "page" || spec["world"] === "isolated"),
  logs: (spec) => _isStringOrNull(spec["until"]) && _isPositive(spec["seconds"]),
  net: (spec) =>
    _isPositive(spec["seconds"]) &&
    _isStringOrNull(spec["until"]) &&
    typeof spec["failed"] === "boolean" &&
    typeof spec["bodies"] === "boolean" &&
    _isPositive(spec["maxBody"]),
  selectors: (spec) => _isRegistry(spec["registry"]),
  "ext-devmode": () => true,
  "ext-list": () => true,
  "ext-reload": () => true,
  "ext-action": () => true,
};

/**
 * Whether an operation record names an operation and has the fields it needs, of the kinds it needs.
 * @param {unknown} spec
 * @returns {boolean}
 */
function _validOperation(spec) {
  return _isObject(spec) && _OPS.includes(String(spec["op"])) && _VALID[String(spec["op"])](spec);
}

/**
 * A request as text.
 * @param {Request} request
 * @returns {string}
 */
export function encodeRequest(request) {
  return JSON.stringify(request);
}

/**
 * The JSON of a text, or the failure naming what is wrong.
 * @param {string} text
 * @param {string} what what the text should be, for the message
 * @returns {unknown}
 * @throws {Error}
 */
function _parseJson(text, what) {
  try {
    return JSON.parse(text);
  } catch (exc) {
    throw new Error(`${what} is not JSON (${exc instanceof Error ? exc.message : String(exc)})`, { cause: exc });
  }
}

/**
 * Check the fields that say what the operations run on: `target`, `ext` and `extensionPaths`, each optional.
 * @param {Record<string, unknown>} data
 * @throws {Error} naming the field that is wrong
 */
function _checkTargeting(data) {
  const { target, ext, extensionPaths } = data;
  if (target !== undefined && typeof target !== "string") {
    throw new Error('the request\'s "target" is not a string');
  }
  if (ext !== undefined && !_isStringOrNull(ext)) {
    throw new Error('the request\'s "ext" is not a string or null');
  }
  if (extensionPaths !== undefined && !(Array.isArray(extensionPaths) && extensionPaths.every(_isString))) {
    throw new Error('the request\'s "extensionPaths" is not a list of strings');
  }
}

/**
 * A request read from text, validated: the boundary where the runner's stdin enters.
 * @param {string} text
 * @returns {Request}
 * @throws {Error} when the text is not a request, naming what is wrong
 */
export function decodeRequest(text) {
  const data = _parseJson(text, "the request");
  if (!_isObject(data) || typeof data["browserURL"] !== "string" || !_isStringOrNull(data["page"])) {
    throw new Error('the request needs a "browserURL" string and a "page" string or null');
  }
  _checkTargeting(data);
  const { redact, operations } = data;
  if (!Array.isArray(redact) || !redact.every((key) => typeof key === "string")) {
    throw new Error('the request\'s "redact" is not a list of strings');
  }
  if (!Array.isArray(operations) || operations.length === 0) {
    throw new Error('the request\'s "operations" is not a non-empty list');
  }
  const invalid = operations.find((spec) => !_validOperation(spec));
  if (operations.some((spec) => !_validOperation(spec))) {
    throw new Error(`the request names an operation that is not valid: ${JSON.stringify(invalid)}`);
  }
  return /** @type {Request} */ (data);
}

/**
 * A response as text.
 * @param {Response} response
 * @returns {string}
 */
export function encodeResponse(response) {
  return JSON.stringify(response);
}

/**
 * A response read from text.
 * @param {string} text
 * @returns {Response}
 * @throws {Error} when the text is not a response
 */
export function decodeResponse(text) {
  const data = _parseJson(text, "the runner's answer");
  if (!_isObject(data) || (!Array.isArray(data["results"]) && typeof data["error"] !== "string")) {
    throw new Error('the runner\'s answer has neither "results" nor "error"');
  }
  return /** @type {Response} */ (data);
}
