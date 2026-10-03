/**
 * Shared JSON data files: one loader, loud failure.
 *
 * The JavaScript twin of `common/jsondata.py` (C102, ADR 0020 D03): a file holds exact
 * text, `{{name}}` marks the values the code fills at runtime — the code computes every
 * value before calling {@link fill}, no format specifier ever reaches the data file — and
 * a missing or broken file raises {@link DataFileError} naming the file, because a data
 * file the standard ships is a dependency, not an optional input. Stdlib only: `node:fs`.
 */

import fs from "node:fs";

// Lowercase names only, as the Python's `{{[a-z0-9_]+}}`: a `{files}` check placeholder
// or any other single-brace text is data, not a fill.
const _PLACEHOLDER = /\{\{([a-z0-9_]+)\}\}/g;

/** A shared data file is missing or unreadable; the message names the file. */
export class DataFileError extends Error {
  /**
   * @param {string} message
   */
  constructor(message) {
    super(message);
    this.name = "DataFileError";
  }
}

/**
 * Parse one data file, failing loudly (and naming the file) on absence or breakage.
 *
 * @param {string} filePath
 * @returns {unknown} the parsed data
 */
export function read(filePath) {
  let text;
  try {
    text = fs.readFileSync(filePath, "utf8");
  } catch (exc) {
    // Only ENOENT is the expected "missing" answer; any other read failure (a directory
    // named like a file, a permission error) propagates, as the Python's does.
    if (/** @type {{code?: string}} */ (exc).code !== "ENOENT") {
      throw exc;
    }
    throw new DataFileError(`akmon data file missing: ${filePath}`);
  }
  try {
    return JSON.parse(text);
  } catch (exc) {
    const detail = exc instanceof Error ? exc.message : String(exc);
    throw new DataFileError(`akmon data file ${filePath} is not valid JSON: ${detail}`);
  }
}

/**
 * Replace every `{{name}}` placeholder in stored text; an unfilled one raises.
 *
 * @param {string} template
 * @param {Record<string, string>} values
 * @returns {string}
 */
export function fill(template, values) {
  return template.replace(_PLACEHOLDER, (_match, key) => {
    if (!Object.hasOwn(values, key)) {
      throw new DataFileError(`placeholder {{${key}}} in a data template has no value`);
    }
    return String(values[key]);
  });
}
