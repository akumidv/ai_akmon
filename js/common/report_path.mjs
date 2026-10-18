/**
 * The one owner of "what is the next report file called" (C114) — twin of `common/report_path.py`.
 *
 * Every tool that writes a markdown report into a shared directory (gate_pack, second_opinion,
 * coverage_map, stats) names it `<prefix>-<n>.md`: `prefix` is `<task>-<base>` when the run names
 * a task and `<base>` otherwise, and `n` is one past the largest ordinal already in the directory
 * for exactly that prefix. The file is created exclusively, so two concurrent runs never
 * overwrite each other: the loser of a race takes the next ordinal.
 */

import fs from "node:fs";

import { encodeUtf8, isDir, pyPath, strRepr } from "./pyvalue.mjs";

/**
 * `name` with every character other than a letter, a digit, `-` or `_` turned into `-`, outer
 * `-` stripped. May return `""`; the caller decides the fallback (a gate falls back to `gate`).
 * @param {string} name
 * @returns {string}
 */
export function safeName(name) {
  const kept = Array.from(name, (ch) => (/^[\p{L}\p{N}]$/u.test(ch) || ch === "-" || ch === "_" ? ch : "-"));
  return kept.join("").replace(/^-+|-+$/g, "");
}

/**
 * The usage-error sentence for a `--task` that sanitizes to nothing, else `null`. `null` or
 * `undefined` (no `--task`) is fine; `""`, `"///"` or `"..."` is not: a task the user named must
 * show in the report's name, never silently vanish (C114). The tools call this before reading or
 * writing anything, so the user sees a usage error.
 * @param {string | null | undefined} task
 * @returns {string | null}
 */
export function taskError(task) {
  if (task === null || task === undefined || safeName(task)) {
    return null;
  }
  return `--task ${strRepr(task)} has no usable characters (letters, digits, '_' or '-')`;
}

/**
 * `<task>-<base>` with a task, else `<base>`; the task is sanitized like a gate name, case kept.
 * Throws (with `taskError`'s sentence) on a task that sanitizes to nothing.
 * @param {string} base
 * @param {string | null | undefined} task
 * @returns {string}
 */
export function reportPrefix(base, task) {
  if (task === null || task === undefined) {
    return base;
  }
  const error = taskError(task);
  if (error !== null) {
    throw new Error(error);
  }
  return `${safeName(task)}-${base}`;
}

/**
 * @param {string} directory
 * @param {string} prefix
 * @returns {number}
 */
function largestOrdinal(directory, prefix) {
  if (!isDir(directory)) {
    return 0;
  }
  const pattern = new RegExp(`^${prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}-([0-9]+)\\.md$`);
  let largest = 0;
  for (const name of fs.readdirSync(directory)) {
    const match = pattern.exec(name);
    if (match) {
      largest = Math.max(largest, Number(match[1]));
    }
  }
  return largest;
}

/**
 * `<directory>/<prefix>-<n>.md` with `n` one past the largest existing ordinal of `prefix` (1
 * when none). Only names matching `<prefix>-<digits>.md` exactly count, so `design-align` does
 * not see `design-align-full-3.md`. Nothing is created.
 * @param {string} directory
 * @param {string} prefix
 * @returns {string}
 */
export function nextReportPath(directory, prefix) {
  return pyPath(directory, `${prefix}-${largestOrdinal(directory, prefix) + 1}.md`);
}

/**
 * Create the next `<prefix>-<n>.md` in `directory` exclusively with `text`; return its path. On
 * a name that already exists (a concurrent run took it) the next ordinal is tried, so no report
 * is ever overwritten.
 * @param {string} directory
 * @param {string} prefix
 * @param {string} text
 * @param {number} [start] the first ordinal tried (default: the next one)
 * @returns {string}
 */
export function createReport(directory, prefix, text, start) {
  fs.mkdirSync(directory, { recursive: true });
  const data = encodeUtf8(text);
  let ordinal = start ?? largestOrdinal(directory, prefix) + 1;
  for (;;) {
    const path = pyPath(directory, `${prefix}-${ordinal}.md`);
    try {
      fs.writeFileSync(path, data, { flag: "wx" });
      return path;
    } catch (error) {
      if (/** @type {{code?: string}} */ (error).code !== "EEXIST") {
        throw error;
      }
      ordinal += 1;
    }
  }
}
