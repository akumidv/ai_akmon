#!/usr/bin/env node
/**
 * Archive done backlog entries: move `· done ·` lines from TASKS.md to TASKS_ARCHIVE.md — the
 * JavaScript twin of `tools/tasks/archive.py` (C108, ADR 0020 D01). The Python module is the
 * spec: the same files in the same bytes, the same stdout lines, the same `error:`/`warning:`
 * lines, the same exit codes; its docstring carries the full account of the mechanic.
 *
 * An *entry* is a top-level list item `- <id> · … · done · …` plus any indented continuation
 * lines beneath it; the status is the third `·`-separated field. Done entries are removed from
 * `TASKS.md` and inserted verbatim at the top of the archive's `## Done` section. `--done <id>…`
 * flips the named entries to `done` first; an id that is not a top-level entry fails closed
 * (exit 2, nothing written). Dry-run exits 1 when done entries are present; `--apply` exits 0.
 *
 * Data (the C102 convention): `main` reads `tools/tasks/archive.json` once and passes it down.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `archive.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with every
 *   error, names the program `archive.py`, and abbreviates long options — `--app`), `-h`/`--help`
 *   prints a short usage and exits 0;
 * - `--done ID…` takes the ids that follow it up to the next option (as `nargs="+"` does) and may
 *   also be repeated (`--done A --done B`); `argparse` keeps only the last occurrence of a repeated
 *   flag.
 */

import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import fs from "node:fs";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import {
  isFile,
  pyLstrip,
  pyPath,
  pySplitlines,
  pyStrip,
  readText,
  rstripChars,
  writeText,
} from "../../common/pyvalue.mjs";

/**
 * The keys of `tools/tasks/archive.json`.
 * @typedef {object} ArchiveData
 * @property {string} done_status
 * @property {string} done_header
 * @property {string} archive_no_section
 * @property {string} error_no_archive_file
 * @property {string} error_generic
 * @property {string} archived
 * @property {string} warning_missing_status
 * @property {string} error_no_such_entry
 * @property {string} no_done_entries
 * @property {string} would_archive_entry
 * @property {string} would_archive_entries
 * @property {string} reapply_hint
 */

const PROG = "archive.mjs";

const USAGE = `usage: ${PROG} [-h] --tasks TASKS [--done ID [ID ...]] [--apply]

Move done backlog entries into TASKS_ARCHIVE.md.

options:
  -h, --help            show this help message and exit
  --tasks TASKS         Path to the TASKS.md to sweep.
  --done ID [ID ...]    Mark these entry ids \`done\` before sweeping (owner names them; all must exist).
  --apply               Perform the move (default: dry-run).
`;

/** The typed id scheme (ADR 0002) plus the grandfathered `T#`; `\\p{Nd}` is Python's `\\d`. */
const TASK_ID_RE = /^[ACLNTV]\p{Nd}+$/u;
/** Minimum `·`-separated fields (id, title, status) for an entry to carry a status field. */
const STATUS_FIELD_COUNT = 3;

/**
 * @param {string} line
 * @returns {boolean}
 */
function _isBullet(line) {
  return line.startsWith("- ");
}

/**
 * The leading id field of a top-level entry (`- C21 · …` → `C21`).
 * @param {string} bullet
 * @returns {string}
 */
function _entryId(bullet) {
  return pyStrip(bullet.slice(2).split("·")[0]);
}

/**
 * The status field (third `·`-separated field), or `null` when the line has too few.
 * @param {string} bullet
 * @returns {string | null}
 */
function _statusOf(bullet) {
  const fields = bullet
    .slice(2)
    .split("·")
    .map((field) => pyStrip(field));
  return fields.length >= STATUS_FIELD_COUNT ? fields[2] : null;
}

/**
 * Rewrite the status field (third `·`-separated field) to `status`, keeping its spacing.
 *
 * Only the status cell changes — the id, title, and detail are left verbatim. A malformed
 * bullet (fewer than three fields) is returned unchanged.
 * @param {string} bullet
 * @param {string} status
 * @returns {string}
 */
function _setStatus(bullet, status) {
  const parts = bullet.split("·");
  if (parts.length < STATUS_FIELD_COUNT) {
    return bullet;
  }
  const field = parts[2];
  const stripped = pyStrip(field);
  const lead = field.slice(0, field.length - pyLstrip(field).length);
  // `field.rstrip()` keeps nothing of an all-blank field, so its whole text is the trailing run.
  const trail = stripped === "" ? field : field.slice(lead.length + stripped.length);
  parts[2] = `${lead}${status}${trail}`;
  return parts.join("·");
}

/**
 * `[start, end)` line ranges for each top-level entry (bullet + indented continuation).
 * @param {string[]} lines
 * @returns {[number, number][]}
 */
export function parseEntries(lines) {
  /** @type {[number, number][]} */
  const entries = [];
  let i = 0;
  const n = lines.length;
  while (i < n) {
    if (_isBullet(lines[i])) {
      let j = i + 1;
      while (j < n && (lines[j].startsWith(" ") || lines[j].startsWith("\t"))) {
        j += 1; // indented continuation belongs to it
      }
      entries.push([i, j]);
      i = j;
    } else {
      i += 1;
    }
  }
  return entries;
}

/**
 * `"\n".join(lines).rstrip("\n") + "\n"`.
 * @param {string[]} lines
 * @returns {string}
 */
function _joined(lines) {
  return `${rstripChars(lines.join("\n"), "\n")}\n`;
}

/**
 * Set the status of each named entry to `done`; returns the new text and the ids not found.
 *
 * `missing` are requested ids that are not a top-level entry (a likely typo). An entry already
 * `done` is left as-is (idempotent). Deciding a task is done stays the owner's call — this only
 * mechanizes the status flip so a close is one command.
 * @param {ArchiveData} data
 * @param {string} tasksText
 * @param {string[]} ids
 * @returns {{text: string, missing: string[]}}
 */
export function markDone(data, tasksText, ids) {
  const lines = pySplitlines(tasksText);
  const wanted = [...new Set(ids)]; // de-dupe, preserve order
  /** @type {Set<string>} */
  const found = new Set();
  for (const [start] of parseEntries(lines)) {
    const entryId = _entryId(lines[start]);
    if (wanted.includes(entryId)) {
      found.add(entryId);
      lines[start] = _setStatus(lines[start], data.done_status);
    }
  }
  return { text: _joined(lines), missing: wanted.filter((id) => !found.has(id)) };
}

/**
 * Top-level bullets whose leading field looks like a task id but that lack a status field.
 *
 * A likely typo — a dropped `·` separator — rather than a prose bullet (whose leading field
 * would not match the id scheme). Advisory only: reported, never swept.
 * @param {string[]} lines
 * @returns {string[]}
 */
export function malformedEntries(lines) {
  return parseEntries(lines)
    .map(([start]) => lines[start])
    .filter((bullet) => TASK_ID_RE.test(_entryId(bullet)) && _statusOf(bullet) === null);
}

/**
 * Drop runs of consecutive blank lines left behind by a removal down to a single blank.
 * @param {string[]} lines
 * @returns {string[]}
 */
function _collapseBlanks(lines) {
  /** @type {string[]} */
  const out = [];
  for (const line of lines) {
    if (pyStrip(line) === "" && out.length > 0 && pyStrip(out[out.length - 1]) === "") {
      continue;
    }
    out.push(line);
  }
  return out;
}

/**
 * Split `TASKS.md` text into the remaining text, the done entry blocks and the moved ids.
 * @param {ArchiveData} data
 * @param {string} tasksText
 * @returns {{remaining: string, blocks: string[][], ids: string[]}}
 */
export function splitDone(data, tasksText) {
  const lines = pySplitlines(tasksText);
  /** @type {Set<number>} */
  const doneIndices = new Set();
  /** @type {string[][]} */
  const blocks = [];
  /** @type {string[]} */
  const ids = [];
  for (const [start, end] of parseEntries(lines)) {
    if (_statusOf(lines[start]) === data.done_status) {
      blocks.push(lines.slice(start, end));
      ids.push(_entryId(lines[start]));
      for (let idx = start; idx < end; idx += 1) {
        doneIndices.add(idx);
      }
    }
  }
  const kept = _collapseBlanks(lines.filter((_line, idx) => !doneIndices.has(idx)));
  return { remaining: _joined(kept), blocks, ids };
}

/**
 * Insert entry `blocks` at the top of the archive's `## Done` section (newest-first).
 * @param {ArchiveData} data
 * @param {string} archiveText
 * @param {string[][]} blocks
 * @returns {string}
 * @throws {Error} a `ValueError`-named error when the archive has no `## Done` section
 */
export function insertIntoArchive(data, archiveText, blocks) {
  const lines = pySplitlines(archiveText);
  for (let idx = 0; idx < lines.length; idx += 1) {
    if (pyStrip(lines[idx]) === data.done_header) {
      let at = idx + 1;
      while (at < lines.length && pyStrip(lines[at]) === "") {
        at += 1; // step past the header's blank line
      }
      const flat = blocks.flat();
      return _joined([...lines.slice(0, at), ...flat, ...lines.slice(at)]);
    }
  }
  const error = new Error(fill(data.archive_no_section, { header: data.done_header }));
  error.name = "ValueError";
  throw error;
}

/**
 * Write the swept `TASKS.md` and updated archive; the `--apply` half of `main`.
 * @param {ArchiveData} data
 * @param {string} tasksPath
 * @param {string} archivePath
 * @param {string} remaining
 * @param {string[][]} blocks
 * @param {string[]} ids
 * @returns {number}
 */
function _applyArchive(data, tasksPath, archivePath, remaining, blocks, ids) {
  if (!isFile(archivePath)) {
    process.stderr.write(`${fill(data.error_no_archive_file, { path: archivePath })}\n`);
    return 2;
  }
  let newArchive;
  try {
    newArchive = insertIntoArchive(data, readText(archivePath), blocks);
  } catch (exc) {
    if (!(exc instanceof Error) || exc.name !== "ValueError") {
      throw exc;
    }
    process.stderr.write(`${fill(data.error_generic, { exc: exc.message })}\n`);
    return 2;
  }
  writeText(tasksPath, remaining);
  writeText(archivePath, newArchive);
  process.stdout.write(`${fill(data.archived, { count: String(ids.length), ids: ids.join(", ") })}\n`);
  return 0;
}

/**
 * Parse the arguments.
 * @param {string[]} argv
 * @returns {{tasks: string | null, done: string[] | null, apply: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values, tokens } = parseArgs({
      args: argv,
      options: {
        tasks: { type: "string" },
        done: { type: "string", multiple: true },
        apply: { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: true,
      strict: true,
      tokens: true,
    });
    // `--done A B C`: the positionals that follow a `--done` belong to it, up to the next option.
    /** @type {string[]} */ const done = [];
    /** @type {string[]} */ const stray = [];
    let afterDone = false;
    for (const token of tokens ?? []) {
      if (token.kind === "option") {
        afterDone = token.name === "done";
        if (afterDone) {
          done.push(/** @type {string} */ (token.value));
        }
      } else if (token.kind === "positional") {
        (afterDone ? done : stray).push(token.value);
      }
    }
    if (values.help === true) {
      return { tasks: null, done: null, apply: false, help: true };
    }
    if (stray.length > 0) {
      return `unrecognized arguments: ${stray.join(" ")}`;
    }
    if (values.tasks === undefined) {
      return "the following arguments are required: --tasks";
    }
    return { tasks: values.tasks, done: done.length > 0 ? done : null, apply: values.apply === true, help: false };
  } catch (exc) {
    const code = /** @type {{code?: string}} */ (exc).code;
    if (typeof code !== "string" || !code.startsWith("ERR_PARSE_ARGS_")) {
      throw exc;
    }
    // parseArgs words some errors over several lines (the hint for the fix); the first is the fact.
    return /** @type {Error} */ (exc).message.split("\n")[0];
  }
}

/**
 * CLI entry point: optionally flip `--done` entries, then sweep done entries into the archive.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: 0 on success or nothing to do, 1 for a dry-run that
 *   found done entries, 2 on a usage error, an unknown `--done` id or a missing file.
 */
export function main(argv = process.argv.slice(2)) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`${PROG}: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  const data = /** @type {ArchiveData} */ (read(join(embeddedTreeRoot(), "tools", "tasks", "archive.json")));
  const tasksPath = pyPath(/** @type {string} */ (options.tasks));
  if (!isFile(tasksPath)) {
    process.stderr.write(`error: no such file: ${tasksPath}\n`);
    return 2;
  }
  const archivePath = pyPath(dirname(tasksPath), "TASKS_ARCHIVE.md");

  let text = readText(tasksPath);
  for (const bullet of malformedEntries(pySplitlines(text))) {
    process.stderr.write(`${fill(data.warning_missing_status, { bullet: pyStrip(bullet) })}\n`);
  }

  if (options.done) {
    const marked = markDone(data, text, options.done);
    text = marked.text;
    if (marked.missing.length > 0) {
      process.stderr.write(`${fill(data.error_no_such_entry, { ids: marked.missing.join(", ") })}\n`);
      return 2;
    }
  }

  const { remaining, blocks, ids } = splitDone(data, text);
  if (blocks.length === 0) {
    process.stdout.write(`${data.no_done_entries}\n`);
    return 0;
  }

  if (!options.apply) {
    const which = ids.length === 1 ? data.would_archive_entry : data.would_archive_entries;
    process.stdout.write(`${fill(which, { count: String(ids.length), ids: ids.join(", ") })}\n`);
    process.stdout.write(`${data.reapply_hint}\n`);
    return 1;
  }

  return _applyArchive(data, tasksPath, archivePath, remaining, blocks, ids);
}

/**
 * Whether node was told to execute `invoked` as this very module (see `akmon/cli.mjs`).
 * @param {string} invoked `process.argv[1]`, the path node was given
 * @returns {boolean}
 */
function runAsEntryPoint(invoked) {
  const self = fileURLToPath(import.meta.url);
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(self);
  } catch {
    return invoked === self;
  }
}

if (process.argv[1] !== undefined && runAsEntryPoint(process.argv[1])) {
  process.exitCode = main();
}
