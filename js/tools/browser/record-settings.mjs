/**
 * The `[browser.record]` table of `<dev root>/.akmon.toml`: what a recording keeps by default, which is the
 * user's to decide for their scenario (`bodies`, `max_body`, `all_pages`). It cannot lower the redaction
 * floor: nothing in it names a key to keep, and the floor (`redact.mjs`) is applied at capture whatever it
 * says. A flag of `record start` overrides a setting for one recording. Read once, at the verb's entry, and
 * passed down.
 */

import { browserTable, BrowserError } from "./settings.mjs";

/**
 * What a recording keeps when neither a setting nor a flag says otherwise.
 * @typedef {object} RecordSettings
 * @property {boolean} bodies keep request and response bodies (JSON and forms, redacted, capped)
 * @property {number} maxBody the cap of a body in bytes
 * @property {boolean} allPages record every page, and the ones that open later
 */

/** The defaults: no bodies, 64 KiB when they are kept, the one page. */
export const DEFAULT_RECORD_SETTINGS = Object.freeze({ bodies: false, maxBody: 65_536, allPages: false });

const _KEYS = ["bodies", "max_body", "all_pages"];

/**
 * The settings of a project's `[browser.record]` table.
 * @param {import("./settings.mjs").Project} project
 * @returns {RecordSettings}
 * @throws {BrowserError} for a key that is not a setting, or a value of the wrong kind
 */
export function readRecordSettings(project) {
  const given = browserTable(project)["record"];
  if (given === undefined) {
    return { ...DEFAULT_RECORD_SETTINGS };
  }
  if (typeof given !== "object" || given === null || Array.isArray(given)) {
    throw new BrowserError("[browser.record] must be a table: bodies, max_body, all_pages");
  }
  const table = /** @type {Record<string, unknown>} */ (given);
  for (const key of Object.keys(table)) {
    if (!_KEYS.includes(key)) {
      throw new BrowserError(
        `[browser.record] ${key} is not a setting (${_KEYS.join(", ")}); the keys a capture redacts are [browser] redact, which can only add to the default ones`,
      );
    }
  }
  return {
    bodies: _flag(table, "bodies", DEFAULT_RECORD_SETTINGS.bodies),
    maxBody: _size(table, DEFAULT_RECORD_SETTINGS.maxBody),
    allPages: _flag(table, "all_pages", DEFAULT_RECORD_SETTINGS.allPages),
  };
}

/**
 * @param {Record<string, unknown>} table
 * @param {string} key
 * @param {boolean} fallback
 * @returns {boolean}
 * @throws {BrowserError} when the value is not true or false
 */
function _flag(table, key, fallback) {
  const value = table[key];
  if (value === undefined) {
    return fallback;
  }
  if (typeof value !== "boolean") {
    throw new BrowserError(`[browser.record] ${key} must be true or false, not ${JSON.stringify(value)}`);
  }
  return value;
}

/**
 * @param {Record<string, unknown>} table
 * @param {number} fallback
 * @returns {number}
 * @throws {BrowserError} when the value is not a positive whole number
 */
function _size(table, fallback) {
  const value = table["max_body"];
  if (value === undefined) {
    return fallback;
  }
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    throw new BrowserError(
      `[browser.record] max_body must be a positive whole number of bytes, not ${JSON.stringify(value)}`,
    );
  }
  return value;
}
