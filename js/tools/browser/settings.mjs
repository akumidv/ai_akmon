/**
 * What `akmon tool browser` knows about one project before it touches Chrome: the project, the
 * folder it keeps its browser state in, and the settings of the `[browser]` table of
 * `<dev root>/.akmon.toml` (`chrome`, `port`, `profile`, `proxy`, `viewports`, `redact`, `extensions`), each
 * overridden by an `AKMON_BROWSER_*` environment variable where it has one (ADR 0032/D05). Both are read
 * once, at the entry point, and passed down.
 */

import { createHash } from "node:crypto";
import fs from "node:fs";
import { delimiter, isAbsolute, posix } from "node:path";

import { aitnaRoot, localRoot, locateProjectRoot } from "../../common/project_root.mjs";
import { readAkmonToml } from "../../common/record.mjs";
import { DEFAULT_REDACT, redactFloor } from "./redact.mjs";

export { DEFAULT_REDACT };

/** A failure the tool states in one line (a refusal, a missing prerequisite): exit 1, no stack. */
export class BrowserError extends Error {
  /**
   * @param {string} message
   * @param {{cause?: unknown}} [options]
   */
  constructor(message, options) {
    super(message, options);
    this.name = "BrowserError";
  }
}

/**
 * The `[browser]` settings after the environment has overridden the table; a value not set is `null`,
 * except the two the inspection verbs read, which carry their defaults.
 * @typedef {object} BrowserSettings
 * @property {string | null} chrome the Chrome executable to use
 * @property {number | null} port the DevTools port
 * @property {string | null} profile the Chrome profile folder
 * @property {string | null} proxy `system`, `direct` or a proxy URL
 * @property {Readonly<Record<string, import("./protocol.mjs").Viewport>>} viewports the named screenshot sizes: the presets, overridden by `[browser].viewports`
 * @property {readonly string[]} redact the JSON keys (and query parameters) a capture redacts: the defaults, then `[browser].redact` added to them
 * @property {readonly string[]} extensions the unpacked extensions to load, absolute, each holding a `manifest.json`: `[browser].extensions`, or `AKMON_BROWSER_EXTENSIONS` (paths joined by the OS path delimiter); a path that is not one is left out and named by `extensionsProblem`
 * @property {ExtensionsProblem | null} extensionsProblem the first path that is not an unpacked extension, or `null`; the verbs that load or act on extensions refuse on it (`requireExtensions`), the others do not
 */

/**
 * A configured extension path that cannot be loaded.
 * @typedef {object} ExtensionsProblem
 * @property {string} path the path as written
 * @property {string} defect what is wrong with it, a phrase that follows the path
 */

/** The screenshot sizes `--viewport` names without a setting, in CSS pixels. */
export const DEFAULT_VIEWPORTS = Object.freeze({
  desktop: Object.freeze({ width: 1440, height: 900 }),
  tablet: Object.freeze({ width: 834, height: 1112 }),
  phone: Object.freeze({ width: 390, height: 844 }),
});

/**
 * One project's browser identity.
 * @typedef {object} Project
 * @property {string} root the project root, symlinks resolved
 * @property {string} name the project root's folder name, which names the project in messages
 * @property {string | null} devRoot the dev-layer root (`<root>/_aitna`, `<root>/meta`, ...), or `null` for a project named by `AKMON_BROWSER_ROOT`, which has no dev layer and so no `[browser]` table
 * @property {string} browserDir `<dev root>/.local/.browser`, the browser's state; `<root>/.local/.browser` when `devRoot` is `null`
 */

/** The environment variable that names the project outright, for a consumer that is not an akmon project. */
export const ROOT_ENV = "AKMON_BROWSER_ROOT";

/** The names of the environment overrides, by `[browser]` key. */
const _ENV_NAMES = Object.freeze({
  chrome: "AKMON_BROWSER_CHROME",
  port: "AKMON_BROWSER_PORT",
  profile: "AKMON_BROWSER_PROFILE",
  proxy: "AKMON_BROWSER_PROXY",
});

/** The port range a derived port falls in: `9300 + hash % 600`. */
const _PORT_BASE = 9300;
const _PORT_SPAN = 600;

/**
 * The text of a file, or `null` when it cannot be read (absent, not ours to read): for the records
 * other projects and other tools leave, where "not there" is an ordinary answer.
 * @param {string} path
 * @returns {string | null}
 */
export function readTextOrNull(path) {
  try {
    return fs.readFileSync(path, "utf8");
  } catch {
    return null;
  }
}

/**
 * The project the run acts on: the folder `AKMON_BROWSER_ROOT` names when it is set and non-empty
 * (explicit beats implicit: no discovery, no `[browser]` table, the state under `<root>/.local/.browser`),
 * else the one that holds `start`. The browser's profile lives in a local layer, so without the
 * variable there is nothing to attach it to outside an akmon project.
 * @param {string} start where discovery starts (the cwd of the run)
 * @param {Record<string, string | undefined>} env
 * @returns {Project}
 * @throws {BrowserError} when `AKMON_BROWSER_ROOT` is relative or not an existing directory, or when it is unset and no project root is at or above `start`
 */
export function projectAt(start, env) {
  const named = env[ROOT_ENV];
  if (named !== undefined && named !== "") {
    return _namedProject(named);
  }
  const found = locateProjectRoot(start);
  if (found === null) {
    throw new BrowserError(
      `no akmon project at or above ${start}: the browser keeps its profile in the project's local layer (or set ${ROOT_ENV} to a folder)`,
    );
  }
  const root = fs.realpathSync(found);
  const devRoot = aitnaRoot(found);
  return Object.freeze({
    root,
    name: posix.basename(root),
    devRoot,
    browserDir: posix.join(localRoot(found), ".browser"),
  });
}

/**
 * The project `AKMON_BROWSER_ROOT` names: the folder itself, with no dev layer.
 * @param {string} named the variable's value
 * @returns {Project}
 * @throws {BrowserError} when the value is relative or not an existing directory
 */
function _namedProject(named) {
  if (!isAbsolute(named)) {
    throw new BrowserError(`${ROOT_ENV} ${JSON.stringify(named)} is not an absolute path`);
  }
  let root;
  try {
    root = fs.realpathSync(named);
    if (!fs.statSync(root).isDirectory()) {
      throw new Error("not a directory");
    }
  } catch (cause) {
    throw new BrowserError(`${ROOT_ENV} ${JSON.stringify(named)} is not an existing directory`, { cause });
  }
  return Object.freeze({
    root,
    name: posix.basename(root),
    devRoot: null,
    browserDir: posix.join(root, ".local", ".browser"),
  });
}

/**
 * The port a project's browser uses when nothing sets one: derived from the project root, so two
 * projects on a machine do not meet on Chrome's usual 9222.
 * @param {string} root the project root, symlinks resolved
 * @returns {number}
 */
export function defaultPort(root) {
  return _PORT_BASE + (createHash("sha1").update(root).digest().readUInt16BE(0) % _PORT_SPAN);
}

/**
 * The `[browser]` table of the project's record, or an empty one (always empty for a project with no dev
 * layer, which has no record).
 * @param {Project} project
 * @returns {Record<string, unknown>}
 */
export function browserTable(project) {
  if (project.devRoot === null) {
    return {};
  }
  const record = readAkmonToml(posix.join(project.devRoot, ".akmon.toml"));
  const table = record["browser"];
  return typeof table === "object" && table !== null && !Array.isArray(table)
    ? /** @type {Record<string, unknown>} */ (table)
    : {};
}

/**
 * One setting: the environment's value, else the table's, else `null`.
 * @param {Record<string, unknown>} table the `[browser]` table
 * @param {Record<string, string | undefined>} env
 * @param {keyof typeof _ENV_NAMES} key
 * @returns {string | number | null}
 */
function _setting(table, env, key) {
  const fromEnv = env[_ENV_NAMES[key]];
  if (fromEnv !== undefined && fromEnv !== "") {
    return fromEnv;
  }
  const fromTable = table[key];
  return typeof fromTable === "string" || typeof fromTable === "number" ? fromTable : null;
}

/**
 * A port value as a number, or a refusal naming the value.
 * @param {string | number} value
 * @returns {number}
 * @throws {BrowserError}
 */
function _validPort(value) {
  const port = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new BrowserError(
      `the DevTools port ${JSON.stringify(value)} is not a number from 1 to 65535 (AKMON_BROWSER_PORT or [browser] port)`,
    );
  }
  return port;
}

/**
 * A size written `WxH` (`1280x720`) as a viewport, or `null` when the text is not one.
 * @param {string} text
 * @returns {import("./protocol.mjs").Viewport | null}
 */
export function parseViewportSize(text) {
  const match = text.trim().match(/^(\d{2,5})\s*[xX]\s*(\d{2,5})$/);
  return match === null ? null : { width: Number(match[1]), height: Number(match[2]) };
}

/**
 * The named screenshot sizes: the presets, each replaced or joined by `[browser].viewports`.
 * @param {Record<string, unknown>} table the `[browser]` table
 * @returns {Record<string, import("./protocol.mjs").Viewport>}
 * @throws {BrowserError} when `viewports` is not a table of `name = "WxH"`
 */
function _viewports(table) {
  const given = table["viewports"];
  if (given === undefined) {
    return { ...DEFAULT_VIEWPORTS };
  }
  if (typeof given !== "object" || given === null || Array.isArray(given)) {
    throw new BrowserError('[browser] viewports must be a table of name = "WxH", such as phone = "390x844"');
  }
  /** @type {Record<string, import("./protocol.mjs").Viewport>} */
  const named = { ...DEFAULT_VIEWPORTS };
  for (const [name, size] of Object.entries(given)) {
    const parsed = typeof size === "string" ? parseViewportSize(size) : null;
    if (parsed === null) {
      throw new BrowserError(`[browser] viewports ${name} = ${JSON.stringify(size)} is not a size written "WxH"`);
    }
    named[name] = parsed;
  }
  return named;
}

/**
 * The keys a capture redacts: the defaults, with `[browser].redact` added to them. The project's list
 * can add a key and can never remove a default.
 * @param {Record<string, unknown>} table the `[browser]` table
 * @returns {string[]}
 * @throws {BrowserError} when `redact` is not a list of strings
 */
function _redactKeys(table) {
  const given = table["redact"];
  if (given === undefined) {
    return redactFloor([]);
  }
  if (!Array.isArray(given) || !given.every((key) => typeof key === "string")) {
    throw new BrowserError('[browser] redact must be a list of key names, such as ["ssn"]');
  }
  return redactFloor(given);
}

/** The environment variable that replaces `[browser].extensions`. */
export const EXTENSIONS_ENV = "AKMON_BROWSER_EXTENSIONS";

/**
 * The extension paths as written: the environment's (joined by the OS path delimiter), else the table's list.
 * @param {Record<string, unknown>} table the `[browser]` table
 * @param {Record<string, string | undefined>} env
 * @returns {string[]}
 * @throws {BrowserError} when `extensions` is not a list of strings
 */
function _extensionPaths(table, env) {
  const fromEnv = env[EXTENSIONS_ENV];
  if (fromEnv !== undefined && fromEnv !== "") {
    return fromEnv.split(delimiter).filter((path) => path !== "");
  }
  const given = table["extensions"];
  if (given === undefined) {
    return [];
  }
  if (!Array.isArray(given) || !given.every((path) => typeof path === "string")) {
    throw new BrowserError('[browser] extensions must be a list of paths, such as ["extension"]');
  }
  return given;
}

/**
 * The unpacked extensions to load: each path made absolute against the project root and checked to hold a
 * `manifest.json`; a comma in a path is classified as a problem because Chrome's flag joins the paths with
 * commas. This is where the settings are classified; the verbs decide whether a problem blocks them.
 * @param {Project} project
 * @param {Record<string, unknown>} table the `[browser]` table
 * @param {Record<string, string | undefined>} env
 * @returns {{paths: string[], problem: ExtensionsProblem | null}} the usable paths, and the first path that is not one
 */
function _extensions(project, table, env) {
  /** @type {string[]} */
  const paths = [];
  /** @type {ExtensionsProblem | null} */
  let problem = null;
  for (const written of _extensionPaths(table, env)) {
    const path = posix.resolve(project.root, written);
    if (path.includes(",")) {
      problem ??= { path: written, defect: "holds a comma, which Chrome's flag cannot carry" };
    } else if (!fs.existsSync(posix.join(path, "manifest.json"))) {
      problem ??= { path: written, defect: "has no manifest.json" };
    } else if (!paths.includes(path)) {
      paths.push(path);
    }
  }
  return { paths, problem };
}

/**
 * The line that names the extensions problem of the settings, or `null` when there is none.
 * @param {BrowserSettings} settings
 * @returns {string | null}
 */
export function extensionsProblemLine(settings) {
  const { extensionsProblem } = settings;
  return extensionsProblem === null ? null : `${extensionsProblem.path} ${extensionsProblem.defect}`;
}

/**
 * Refuse when a configured extension path is not an unpacked extension: for the verbs that load or act on the
 * extensions.
 * @param {BrowserSettings} settings
 * @returns {void}
 * @throws {BrowserError} in one line naming the path
 */
export function requireExtensions(settings) {
  const { extensionsProblem } = settings;
  if (extensionsProblem !== null) {
    throw new BrowserError(
      `the extension path ${JSON.stringify(extensionsProblem.path)} ${extensionsProblem.defect} (${EXTENSIONS_ENV} or [browser] extensions)`,
    );
  }
}

/**
 * The settings of a project: `[browser]` of its record, each key overridden by its environment variable.
 * A relative `chrome` or `profile` is relative to the project root.
 * @param {Project} project
 * @param {Record<string, string | undefined>} env
 * @returns {BrowserSettings}
 * @throws {BrowserError} when the port is not a port, or `viewports`, `redact` or `extensions` is not what it must be; an extension path that is not an unpacked extension is not thrown but classified (`extensionsProblem`)
 */
export function readSettings(project, env) {
  const table = browserTable(project);
  const path = (/** @type {string | number | null} */ value) =>
    value === null ? null : posix.resolve(project.root, String(value));
  const port = _setting(table, env, "port");
  const proxy = _setting(table, env, "proxy");
  const extensions = _extensions(project, table, env);
  return Object.freeze({
    chrome: path(_setting(table, env, "chrome")),
    port: port === null ? null : _validPort(port),
    profile: path(_setting(table, env, "profile")),
    proxy: proxy === null ? null : String(proxy),
    viewports: Object.freeze(_viewports(table)),
    redact: Object.freeze(_redactKeys(table)),
    extensions: Object.freeze(extensions.paths),
    extensionsProblem: extensions.problem,
  });
}

/**
 * The DevTools port of the project: the setting, else the derived one.
 * @param {Project} project
 * @param {BrowserSettings} settings
 * @returns {number}
 */
export function portOf(project, settings) {
  return settings.port ?? defaultPort(project.root);
}
