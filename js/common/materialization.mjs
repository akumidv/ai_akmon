/**
 * The one owner of the package-mode materialization: its format, and whether it is current —
 * the JavaScript twin of `common/materialization.py` (ADR 0020 D01); `units/materialization.toml`
 * is the spec both must pass.
 *
 * Mode `package` puts no executable surface in the consumer repository; exactly one thing is
 * written there: the guardrail and profile files the consumer's `AGENTS.md` `@`-imports. That
 * copy is the consumer's rules, so it must not go quietly stale. `sync` writes it, `verify`
 * compares what `sync` would write with what is on disk, and the SessionStart hook says so when
 * the installed standard has moved past it — the banner rule and the comparison live here and
 * the callers hold no copy of either.
 *
 * Data (the C102/C103 convention): this module never reads a file itself. `data` is the parsed
 * `common/materialization.json` (the banner fragments and the imported directories), read once
 * by the caller at its entry point and passed down.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - `str.splitlines()` breaks on `\n \r \r\n \v \f \x1c \x1d \x1e \x85 U+2028 U+2029`, and
 *   `str.lstrip()` strips the Unicode whitespace `str.isspace` names — neither is the JS
 *   `\s`/`trim` set (which has U+FEFF and lacks `\x1c`–`\x1f` and `\x85`), so both are spelled
 *   out below;
 * - `Path.read_text(encoding="utf-8")` decodes strictly, keeps a BOM, and translates `\r\n`
 *   and `\r` to `\n` — `_readText`; a file that is not UTF-8 raises there, as it does in the
 *   twin, and is not "stale";
 * - `Path.is_dir()` raises on some errors in Python 3.11/3.12 and answers false in 3.13; the
 *   hook that calls this must never raise, so it answers false here;
 * - `sorted()` on paths orders their names by code point — `codePointSort`.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { TextDecoder } from "node:util";

import { aitnaRoot, aitnaRootName } from "./project_root.mjs";
import { codePointSort } from "./sort.mjs";

/**
 * The shape of `common/materialization.json` — the data file is the owner of these keys.
 * @typedef {object} MaterializationData
 * @property {{prefix: string, suffix: string}} generated_banner
 * @property {string[]} imported_dirs
 */

/** The characters `str.splitlines` ends a line at (`\r\n` is one break, handled in `_firstLineEnd`). */
const _LINE_BREAKS = new Set(["\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]);

/** Whether the UTF-16 unit `code` is whitespace to Python's `str.isspace` (all of them BMP). */
function _isPythonSpace(/** @type {number} */ code) {
  return (
    (code >= 0x09 && code <= 0x0d) ||
    (code >= 0x1c && code <= 0x20) ||
    code === 0x85 ||
    code === 0xa0 ||
    code === 0x1680 ||
    (code >= 0x2000 && code <= 0x200a) ||
    code === 0x2028 ||
    code === 0x2029 ||
    code === 0x202f ||
    code === 0x205f ||
    code === 0x3000
  );
}

/** The end of the first line of `text`, its line ending included (`text.length` when it has none). */
function _firstLineEnd(/** @type {string} */ text) {
  for (let i = 0; i < text.length; i++) {
    if (_LINE_BREAKS.has(text[i])) {
      return text[i] === "\r" && text[i + 1] === "\n" ? i + 2 : i + 1;
    }
  }
  return text.length;
}

/** Whether `line` starts with `#` once Python's `lstrip()` has removed its leading whitespace. */
function _startsWithHash(/** @type {string} */ line) {
  let i = 0;
  while (i < line.length && _isPythonSpace(line.charCodeAt(i))) {
    i++;
  }
  return line[i] === "#";
}

/**
 * Whether `error` is a filesystem failure — Python's `OSError`. A decoding failure is not one
 * (Python raises `UnicodeDecodeError`, a `ValueError`), and is never swallowed.
 * @param {unknown} error
 * @returns {boolean}
 */
function _isOSError(error) {
  return error instanceof Error && typeof (/** @type {{errno?: unknown}} */ (error).errno) === "number";
}

/**
 * One file's text the way `Path.read_text(encoding="utf-8")` reads it.
 * @param {string} file
 * @returns {string}
 * @throws {TypeError} when the bytes are not valid UTF-8
 */
function _readText(file) {
  const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(fs.readFileSync(file));
  return text.replace(/\r\n?/g, "\n");
}

/** Whether `file` is a regular file, following links; any failure is "no". */
function _isFile(/** @type {string} */ file) {
  try {
    return fs.statSync(file).isFile();
  } catch {
    return false;
  }
}

/** Whether `directory` is a directory, following links; any failure is "no". */
function _isDir(/** @type {string} */ directory) {
  try {
    return fs.statSync(directory).isDirectory();
  } catch {
    return false;
  }
}

/** `base/name` with nothing normalized — `Path("")` is the cwd, so an empty base is `.`. */
function _under(/** @type {string} */ base, /** @type {string} */ name) {
  return `${base || "."}/${name}`;
}

/**
 * Stable substring used to recognise a generated file regardless of the configured root.
 * Verify/sync look for this prefix, not the full banner (which embeds the root path).
 * @param {MaterializationData} data the parsed `common/materialization.json`
 * @returns {string}
 */
export function generatedMarker(data) {
  return data.generated_banner.prefix;
}

/**
 * The do-not-edit banner; tracks the configured root so it never drifts from real paths. The
 * root is the only dynamic part: the fragments around it come from the shared data file.
 * @param {MaterializationData} data the parsed `common/materialization.json`
 * @returns {string}
 */
export function generatedBanner(data) {
  const banner = data.generated_banner;
  return `${banner.prefix}${aitnaRootName()}${banner.suffix}`;
}

/**
 * `sourceText` with the generated-pointer banner inserted as an HTML comment — right after a
 * leading top-level heading when present, else at the very top. The heading line keeps its own
 * line ending, so a heading with none has the comment on its line.
 * @param {MaterializationData} data the parsed `common/materialization.json`
 * @param {string} sourceText
 * @returns {string}
 */
export function materializedMarkdown(data, sourceText) {
  const bannerLine = `<!-- ${generatedBanner(data)} -->`;
  if (sourceText) {
    const end = _firstLineEnd(sourceText);
    const first = sourceText.slice(0, end);
    if (_startsWithHash(first)) {
      return first + bannerLine + "\n\n" + sourceText.slice(end);
    }
  }
  return bannerLine + "\n\n" + sourceText;
}

/**
 * The materialized copy of one standard file. Markdown carries the banner as an HTML comment
 * (`materializedMarkdown`); a TOML file — akmon's ruff rules — carries it as a `#` comment on
 * its first line, where a TOML parser skips it.
 * @param {MaterializationData} data the parsed `common/materialization.json`
 * @param {string} name
 * @param {string} sourceText
 * @returns {string}
 */
export function materializedText(data, name, sourceText) {
  if (name.endsWith(".md")) {
    return materializedMarkdown(data, sourceText);
  }
  return `# ${generatedBanner(data)}\n\n${sourceText}`;
}

/**
 * The standard directories whose files a consumer's `AGENTS.md` `@`-imports: the universal
 * guardrails and the language and environment profiles. Package mode writes the imported ones
 * under `<AITNA_ROOT>/.akmon/<directory>/`; mounted modes import them from the mount.
 * @param {MaterializationData} data the parsed `common/materialization.json`
 * @returns {string[]}
 */
export function importedDirs(data) {
  return [...data.imported_dirs];
}

/**
 * Where package mode writes the imported guardrails and profiles, one subdirectory each.
 * @param {string} projectRoot
 * @returns {string}
 */
export function materializedDir(projectRoot) {
  return posix.join(aitnaRoot(projectRoot), ".akmon");
}

/**
 * Materialized files whose text is no longer what `treeRoot` ships.
 *
 * Materialized files are named `guardrails/<name>`, `profiles/<name>`. `treeRoot` is the
 * standard tree the caller is actually running from, so the comparison is against the code
 * that is executing rather than against a recorded version string: a bump that leaves the
 * guardrails untouched must stay silent, and a hand-edit of the copy must not.
 *
 * Empty for a project with no materialization at all — every mounted-mode project, and a
 * package-mode project between `init` and its first `sync`. Directory scan rather than a
 * re-read of `AGENTS.md`'s imports: what is on disk is what the harness will load, and an
 * import with no file behind it is a plan error `sync` and `verify` already report.
 *
 * Unreadable files count as stale: "cannot be compared" and "does not match" lead to the same
 * instruction. A file that is not UTF-8 is not "unreadable" — it raises, as in the twin.
 * @param {MaterializationData} data the parsed `common/materialization.json`
 * @param {string} projectRoot
 * @param {string} treeRoot
 * @returns {string[]}
 * @throws {TypeError} when a materialized file or its source is not valid UTF-8
 */
export function staleMaterialized(data, projectRoot, treeRoot) {
  /** @type {string[]} */
  const stale = [];
  for (const directory of importedDirs(data)) {
    const dest = _under(materializedDir(projectRoot), directory);
    if (!_isDir(dest)) {
      continue;
    }
    /** @type {string[]} */
    let names = [];
    try {
      names = fs.readdirSync(dest).filter((name) => name.endsWith(".md") || name.endsWith(".toml"));
    } catch (error) {
      if (!_isOSError(error)) {
        throw error;
      }
    }
    for (const name of codePointSort(names)) {
      const relative = `${directory}/${name}`;
      const source = _under(treeRoot, relative);
      try {
        if (!_isFile(source) || _readText(_under(dest, name)) !== materializedText(data, name, _readText(source))) {
          stale.push(relative);
        }
      } catch (error) {
        if (!_isOSError(error)) {
          throw error;
        }
        stale.push(relative);
      }
    }
  }
  return stale;
}
