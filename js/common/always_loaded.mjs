/**
 * The always-loaded ratchet's one counter — population, measurement, finding and report — the
 * JavaScript twin of `common/always_loaded.py` (C56, ADR 0012 F18; ADR 0020 D01);
 * `units/always_loaded.toml` is the spec both must pass.
 *
 * *Always-loaded* is everything reaching the model before it asks for anything, measured over two
 * scopes that differ on purpose: **akmon-shipped** (the marked akmon block of `AGENTS.md`, the
 * guardrail chain it `@`-imports, resolved transitively, and the selected language guardrail) and
 * **consumer total** (the whole `AGENTS.md` plus that same chain and language guardrail). Members
 * are counted as a union and summed with no synthetic separator: lines are
 * `len(text.splitlines())`, bytes the UTF-8 length. `over` and `report` read the same
 * {@link Population}, so the numbers a reader sees are the numbers the cap was checked against.
 *
 * Data (the C102/C103 convention): this module never reads a file itself apart from the counted
 * texts. `data` is the parsed `common/always_loaded.json` (block heading, scopes, caps,
 * severities), read once by the caller through {@link readAlwaysLoadedData} and passed down as the
 * first parameter.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - the import, fence, inline-code and comment patterns are `re.ASCII` on the Python side (a
 *   no-break space after an `@`-token is part of the token in both), and `^`/`$`/`.` under
 *   `MULTILINE`/`DOTALL` become `(?<![^\n])`, `(?![^\n])` and `[^]` here — `\r` and U+2028 are
 *   not line starts in either language's pattern, whatever `str.splitlines` thinks;
 * - `str.splitlines` (with `keepends`) breaks on `\n \r \r\n \v \f \x1c \x1d \x1e \x85 U+2028
 *   U+2029` — `_splitlinesKeepEnds`; the counted line number is `pySplitlines`;
 * - `Path.read_text` decodes strictly and translates `\r\n` and `\r` to `\n` (`readText`), so a
 *   CRLF file counts the bytes of its translated text, as in the twin;
 * - `Path.expanduser` expands a leading `~`/`~user` component (`$HOME`, then the password
 *   database; `~user` is read from `/etc/passwd`, not through NSS) and raises `RuntimeError`
 *   when it cannot; `Path.resolve` is `resolvePath`; `Path.relative_to` raises `ValueError`
 *   (the Python 3.12 wording; 3.11 appends " OR one path is relative and the other is absolute.").
 */

import fs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";

import { read } from "./jsondata.mjs";
import { isRelativeTo, resolvePath } from "./project_root.mjs";
import { isFile, pyError, pySplitlines, readText } from "./pyvalue.mjs";

/** The finding code the always-loaded ratchet reports under. */
export const CODE = "caps.always-loaded";

/**
 * The shape of `common/always_loaded.json` — the data file is the owner of these keys.
 * @typedef {object} AlwaysLoadedData
 * @property {string} block_heading
 * @property {string[]} scopes
 * @property {Record<string, {lines: number, bytes: number}>} caps
 * @property {Record<string, string>} severity
 */

/**
 * The block heading, scopes, caps and severities, as the data file carries them.
 * @returns {AlwaysLoadedData}
 */
export function readAlwaysLoadedData() {
  return /** @type {AlwaysLoadedData} */ (
    read(fileURLToPath(new URL("../../common/always_loaded.json", import.meta.url)))
  );
}

/**
 * The heading that marks the akmon block of a project's `AGENTS.md`.
 * @param {AlwaysLoadedData} data
 * @returns {string}
 */
export function blockHeading(data) {
  return data.block_heading;
}

/**
 * The akmon-shipped scope name.
 * @param {AlwaysLoadedData} data
 * @returns {string}
 */
export function shipped(data) {
  return data.scopes[0];
}

/**
 * The consumer-total scope name.
 * @param {AlwaysLoadedData} data
 * @returns {string}
 */
export function consumer(data) {
  return data.scopes[1];
}

// An `@`-import as the harness reads it: a token starting a line or following whitespace. Code
// spans, fenced blocks and HTML comments are stripped first — the harness does not import from
// them. ASCII whitespace only, the Python `re.ASCII`: `[ \t\n\r\f\v]` is its `\s`.
const _SPACE = " \\t\\n\\r\\f\\v";
const _IMPORT_RE = new RegExp(`(?:(?<![^\\n])|(?<=[${_SPACE}]))@([^${_SPACE}\`]+)`, "g");
const _FENCED_RE = /(?<![^\n])(```|~~~)[^]*?(?<![^\n])\1[^\n]*(?![^\n])/g;
const _INLINE_CODE_RE = /`[^`\n]*`/g;
const _COMMENT_RE = /<!--[^]*?-->/g;

/** The characters `str.splitlines` ends a line at, `\r\n` first so it is one break. */
// eslint-disable-next-line no-control-regex
const _LINE_END = new RegExp("\\r\\n|[\\n\\r\\v\\f\\x1c\\x1d\\x1e\\x85\\u2028\\u2029]", "g");

/**
 * One scope's inclusive caps.
 */
export class Cap {
  /**
   * @param {number} lines
   * @param {number} bytes
   */
  constructor(lines, bytes) {
    this.lines = lines;
    this.bytes = bytes;
    Object.freeze(this);
  }
}

/**
 * One scope's inclusive caps, for every scope.
 * @param {AlwaysLoadedData} data
 * @returns {Record<string, Cap>}
 */
export function caps(data) {
  /** @type {Record<string, Cap>} */
  const found = {};
  for (const scope of data.scopes) {
    found[scope] = new Cap(data.caps[scope].lines, data.caps[scope].bytes);
  }
  return found;
}

/**
 * The severity an over-cap finding carries, per scope.
 * @param {AlwaysLoadedData} data
 * @returns {Record<string, string>}
 */
export function severity(data) {
  return { ...data.severity };
}

/**
 * One counted text: a file, or the marked block, by the name the report uses.
 */
export class Member {
  /**
   * @param {string} name
   * @param {string} text
   */
  constructor(name, text) {
    this.name = name;
    this.text = text;
    Object.freeze(this);
  }

  /** `len(text.splitlines())`. */
  get lines() {
    return pySplitlines(this.text).length;
  }

  /** Decimal bytes, UTF-8. */
  get size() {
    return Buffer.byteLength(this.text, "utf8");
  }
}

/**
 * The members of one scope and their summed measurements.
 */
export class Population {
  /**
   * @param {string} scope
   * @param {Iterable<Member>} members
   */
  constructor(scope, members) {
    this.scope = scope;
    this.members = Object.freeze([...members]);
    Object.freeze(this);
  }

  /** Summed member lines, no synthetic separator. */
  get lines() {
    return this.members.reduce((sum, member) => sum + member.lines, 0);
  }

  /** Summed member bytes, no synthetic separator. */
  get size() {
    return this.members.reduce((sum, member) => sum + member.size, 0);
  }
}

/**
 * `text.splitlines(keepends=True)`.
 * @param {string} text
 * @returns {string[]}
 */
function _splitlinesKeepEnds(text) {
  /** @type {string[]} */
  const lines = [];
  let from = 0;
  for (const match of text.matchAll(_LINE_END)) {
    const end = match.index + match[0].length;
    lines.push(text.slice(from, end));
    from = end;
  }
  if (from < text.length) {
    lines.push(text.slice(from));
  }
  return lines;
}

/**
 * The akmon block of `AGENTS.md`: its heading line up to the next peer `##` or EOF.
 * @param {AlwaysLoadedData} data
 * @param {string} agentsText
 * @returns {string | null}
 */
export function markedBlock(data, agentsText) {
  const heading = blockHeading(data);
  const lines = _splitlinesKeepEnds(agentsText);
  const start = lines.findIndex((line) => line.startsWith(heading));
  if (start === -1) {
    return null;
  }
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (lines[i].startsWith("## ")) {
      end = i;
      break;
    }
  }
  return lines.slice(start, end).join("");
}

/**
 * The `@`-import targets the harness would read in `text`, in order.
 * @param {string} text
 * @returns {string[]}
 */
function _imports(text) {
  const visible = text
    .replace(_FENCED_RE, () => "\n")
    .replace(_INLINE_CODE_RE, () => " ")
    .replace(_COMMENT_RE, () => " ");
  return [...visible.matchAll(_IMPORT_RE)].map((match) => match[1]);
}

/**
 * `Path(target).expanduser()` as a string: a leading `~` or `~user` component is replaced by the
 * home directory; an absolute path, or one not starting with `~`, is unchanged.
 * @param {string} target
 * @returns {string}
 */
function _expandUser(target) {
  if (target.startsWith("/")) {
    return target;
  }
  // `Path` drops empty and `.` components before the first one is looked at (`./~x` is `~x`).
  const parts = target.split("/").filter((part) => part !== "" && part !== ".");
  if (parts.length === 0 || !parts[0].startsWith("~")) {
    return target;
  }
  const user = parts[0].slice(1);
  const home = user === "" ? (process.env.HOME ?? _currentHome()) : _passwdHome(user);
  if (home === null) {
    throw pyError("RuntimeError", "Could not determine home directory.");
  }
  // `posixpath.expanduser`: trailing slashes of the home dropped, an empty home is the root.
  const base = home.replace(/\/+$/, "") || "/";
  return [base, ...parts.slice(1)].join("/").replace(/^\/\//, "/");
}

/** The current user's home from the password database, or null. */
function _currentHome() {
  try {
    return os.userInfo().homedir;
  } catch {
    return null;
  }
}

/** The home of `user` per `/etc/passwd`, or null. */
function _passwdHome(/** @type {string} */ user) {
  let text;
  try {
    text = fs.readFileSync("/etc/passwd", "utf8");
  } catch {
    return null;
  }
  for (const line of text.split("\n")) {
    const fields = line.split(":");
    if (fields[0] === user && fields.length >= 6) {
      return fields[5];
    }
  }
  return null;
}

/**
 * Files `text` `@`-imports, transitively and in first-seen order; missing targets skipped.
 *
 * A relative import resolves against the importing file's directory (`base` for the first level).
 * Resolution never leaves `root`: the population is the project's context, and an import pointing
 * outside it is not ours to count.
 * @param {string} text
 * @param {string} base
 * @param {{root: string}} options
 * @returns {string[]}
 */
export function importChain(text, base, { root }) {
  /** @type {string[]} */
  const seen = [];
  /** @type {Array<[string, string]>} */
  const pending = _imports(text).map((target) => [target, base]);
  while (pending.length > 0) {
    const [target, directory] = /** @type {[string, string]} */ (pending.shift());
    const expanded = _expandUser(target);
    const path = resolvePath(expanded.startsWith("/") ? expanded : `${directory}/${expanded}`);
    if (seen.includes(path) || !isFile(path) || !isRelativeTo(path, resolvePath(root))) {
      continue;
    }
    seen.push(path);
    for (const nested of _imports(readText(path))) {
      pending.push([nested, path.slice(0, path.lastIndexOf("/")) || "/"]);
    }
  }
  return seen;
}

/**
 * The head, then every chain/selected file once (by resolved path), as members.
 * @param {string} root
 * @param {Member} head
 * @param {string[]} chain
 * @param {string[]} selected
 * @returns {Member[]}
 */
function _union(root, head, chain, selected) {
  const members = [head];
  const seen = new Set();
  for (const path of [...chain, ...selected]) {
    const resolved = resolvePath(path);
    if (seen.has(resolved) || !isFile(resolved)) {
      continue;
    }
    seen.add(resolved);
    const rootResolved = resolvePath(root);
    if (!isRelativeTo(resolved, rootResolved)) {
      throw pyError("ValueError", `'${resolved}' is not in the subpath of '${rootResolved}'`);
    }
    const relative =
      resolved === rootResolved ? "." : resolved.slice(rootResolved === "/" ? 1 : rootResolved.length + 1);
    members.push(new Member(relative, readText(resolved)));
  }
  return members;
}

/**
 * Both scopes for one project; null when `AGENTS.md` carries no marked akmon block.
 * @param {AlwaysLoadedData} data
 * @param {string} agentsText
 * @param {string} root
 * @param {string[]} [selected]
 * @returns {Record<string, Population> | null}
 */
export function populations(data, agentsText, root, selected = []) {
  const block = markedBlock(data, agentsText);
  if (block === null) {
    return null;
  }
  const chain = importChain(block, root, { root });
  const shippedScope = shipped(data);
  const consumerScope = consumer(data);
  return {
    [shippedScope]: new Population(
      shippedScope,
      _union(root, new Member("AGENTS.md (akmon block)", block), chain, [...selected]),
    ),
    [consumerScope]: new Population(
      consumerScope,
      _union(root, new Member("AGENTS.md", agentsText), chain, [...selected]),
    ),
  };
}

/**
 * The dynamic report — scope, then actual over cap for both dimensions.
 *
 * The finding that carries it names the code, so the message does not repeat it.
 * @param {Population} population
 * @param {Cap} cap
 * @returns {string}
 */
export function report(population, cap) {
  return `${population.scope}: lines=${population.lines}/${cap.lines} bytes=${population.size}/${cap.bytes}`;
}

/**
 * Whether either inclusive dimension is exceeded.
 * @param {Population} population
 * @param {Cap} cap
 * @returns {boolean}
 */
export function over(population, cap) {
  return population.lines > cap.lines || population.size > cap.bytes;
}
