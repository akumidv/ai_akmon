#!/usr/bin/env node
/**
 * Synchronize generated agent pointers for an akmon-consuming project — `akmon sync`. The
 * JavaScript twin of `bin/sync.py` (C105, ADR 0020 D01): the Python module is the spec, the same
 * files in the same bytes, the same texts, the same exit codes.
 *
 * The source of truth stays in AGENTS.md, akmon docs, and SKILL.md files. This tool writes thin
 * vendor pointers and hook wiring so assistants do not need duplicated instruction copies. It is
 * safe to run repeatedly.
 *
 *     akmon sync               write the generated files
 *     akmon sync --dry-run     print what would change
 *     akmon sync --check       write nothing; findings, exit 1 when a generated file is stale
 *
 * This implementation serves Node projects (ADR 0020 D02, its C129 amendment): the record says
 * `ecosystem = "node"`, in package mode (`mount = "package"`) or a mounted one (`submodule`,
 * `vendored`, `subtree`). Any other record is refused with exit 2 and the `unsupported_record` text
 * of `bin/sync.json` — a wrong-spelling write is worse than a refusal.
 *
 * What is Node's own (ADR 0020 D05):
 * - the hook command is `node "<anchor>/<hooks dir>/<script>.mjs"`, the hooks directory being
 *   `node_modules/akmon/js/hooks` in package mode and `<AITNA_ROOT>/akmon/js/hooks` in a mounted one
 *   (`nodeHooksDir`); the spelling is data (`node_hook_command`, `node_codex_hook_command`, one
 *   `{{hooks_dir}}` placeholder each);
 * - the standard tree of a Node package project is `<root>/node_modules/akmon`, spelled **unresolved**
 *   (pnpm makes it a link into `.pnpm/akmon@<version>/…`, a path that carries the version and must
 *   never reach a committed file). `standardTreeRoot` answers that spelling when its realpath is the
 *   running tree, the running tree's realpath otherwise; a mounted record reads the mount, as the
 *   Python does. Inside the project root, a standard skill's stub points at it with a relative link,
 *   never through `$(akmon path)`;
 * - `packagePinStatus` reads `package.json`, and the tree's own version (`installedAkmonVersion`) is
 *   the `version` of its `package.json`. The launcher (`launcher_relative`, `is_executable_file`,
 *   `_cli_name`) is the Python carrier's and has no twin.
 *
 * Data (the C102 convention): `main` reads `bin/sync.json`, `common/materialization.json` and
 * `common/findings.json` through one lazy bundle (`readSyncData`) and passes it down as the first
 * parameter, `data`, of every function that needs it — the Python takes it last and optional.
 *
 * Twin notes, each a place where the stdlib answers differently from Node's:
 * - `str.splitlines()` and `strip()` break and trim on the Unicode sets (`pySplitlines`, `pyStrip`),
 *   and `Path.read_text` decodes strictly and translates newlines (`readText`); a file that is not
 *   UTF-8 raises `UnicodeDecodeError` with the codec's own sentence (`_readText`);
 * - `re` with `MULTILINE`/`DOTALL`: `^` and `$` see only `\n` and `.` crosses it, so the fenced-block
 *   pattern spells `(?<![^\n])`, `(?![^\n])` and `[^]` and uses no `m`/`s` flag. Nothing here uses
 *   `\d \w \s \b`, so no `re.ASCII` is owed;
 * - `json.loads`/`json.dumps` of `.claude/settings.json`: the document is read into ordered `Map`s
 *   with `FloatValue` for a float (`_decodeJson` is the C scanner's grammar, with its error
 *   sentences and `char N` counted in code points) and written by `wiringForm`. An integer beyond
 *   2**53 cannot be written back byte for byte, so it is refused as a plan error (a divergence);
 * - `Path.glob("*\/SKILL.md")` and `Path.rglob` list hidden names, follow a link only to test it, and
 *   do not descend into a linked directory; `sorted()` orders paths by their components, not by the
 *   joined string (`a-b` before `a/c`), by code point;
 * - `tomllib.load` refuses a BOM that the vendored parser folds in: `ruffExtends` refuses it too;
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `akmon sync: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0.
 *   `argparse` prints its usage block with every error and abbreviates long options (`--dry`).
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { TextDecoder, parseArgs } from "node:util";

import { TomlError, parse as parseToml } from "../vendor/smol-toml/dist/index.js";
import { Finding, lineSafe, printFindings, readFindingsData } from "../common/findings.mjs";
import { fill, read } from "../common/jsondata.mjs";
import { FloatValue, wiringForm } from "../common/json_writer.mjs";
import { fnmatchCase } from "../common/glob.mjs";
import { generatedBanner, generatedMarker, importedDirs, materializedText } from "../common/materialization.mjs";
import { aitnaRoot, aitnaRootName, resolveProjectRoot } from "../common/project_root.mjs";
import { recordedEcosystem, recordedMount } from "../common/record.mjs";
import {
  isDir,
  isFile,
  isOSError,
  pyError,
  pyLen,
  pyPath,
  pyRepr,
  pySplitlines,
  pyStat,
  pyStrip,
  readText,
  writeText,
} from "../common/pyvalue.mjs";
import { codePointCompare, codePointSort } from "../common/sort.mjs";

/** @typedef {import("../common/findings.mjs").FindingsData} FindingsData */
/** @typedef {import("../common/materialization.mjs").MaterializationData} MaterializationData */
/** @typedef {any} Json */

/**
 * The shape of `bin/sync.json` — the data file is the owner of these keys; the functions that read a
 * key type it.
 * @typedef {object} SyncDocument
 * @property {string} cli_name
 * @property {string[]} akmon_hook_markers
 * @property {string} node_hook_command
 * @property {string} node_codex_hook_command
 * @property {string} unsupported_record
 * @property {{no_record: string, ecosystem: string}} unsupported_found
 * @property {Record<string, Array<{matcher: string | null, commands: string[]}>>} claude_hooks
 * @property {Record<string, Array<{matcher: string, commands: Array<[string, string]>}>>} codex_hooks
 * @property {{claude_md: string, copilot_md: string, gemini_md: string, codex_readme: string}} vendor_pointers
 * @property {Array<[string, string]>} planned_files
 * @property {{no_frontmatter: string, with_frontmatter: string}} skill_stubs
 * @property {string[]} skill_stub_dirs
 * @property {string} always_materialized
 * @property {Record<string, string>} moved_imports
 * @property {Array<{profile: string, languages: string[], manifests: string[]}>} language_profiles
 * @property {Array<[string, string[]]>} ruff_configs
 * @property {string} ruff_toml_template
 * @property {{files: string[], sources: string, walk_limit: number}} python_markers
 * @property {Record<string, {message: string, fix: string}>} check_findings
 * @property {{changed: {dry_run: string, write: string}, deleted: {dry_run: string, write: string}, ok: string, error: string, no_changes: string}} summary_verbs
 */

/**
 * What the sync reads from the shared data files: one bundle, each file read on first access and
 * once per process. A test or a probe passes a plain object holding the same properties.
 * @typedef {object} SyncData
 * @property {SyncDocument} sync `bin/sync.json`
 * @property {MaterializationData} materialization `common/materialization.json`
 * @property {FindingsData} findings `common/findings.json`
 */

/** The tree this module executes from, links dereferenced: `<tree>/js/bin/sync.mjs` → `<tree>`. */
const TREE_ROOT = fs.realpathSync(posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", ".."));

const _PACKAGE_MODE = "package";
const _NODE_ECOSYSTEM = "node";

// --------------------------------------------------------------------------------------
// The record, the pin and the tree
// --------------------------------------------------------------------------------------

/**
 * The recorded `mount` value from `<AITNA_ROOT>/.akmon.toml` (ADR 0009 §3): `"submodule"`,
 * `"vendored"`, `"subtree"` or `"package"`. An absent record or key defaults to `"submodule"` — the
 * traditional mounted-tree default, kept for backward compatibility with every project that
 * predates this field.
 * @param {string} projectRoot
 * @returns {string}
 */
export function readMountMode(projectRoot) {
  return recordedMount(projectRoot) ?? "submodule";
}

/**
 * Whether `projectRoot` is governed by mount mode `package` (ADR 0009 §4). Driven solely by the
 * recorded `mount` field, never by whether `<AITNA_ROOT>/akmon` happens to exist on disk.
 * @param {string} projectRoot
 * @returns {boolean}
 */
export function isPackageMode(projectRoot) {
  return readMountMode(projectRoot) === _PACKAGE_MODE;
}

/**
 * Whether a dependency table of `package.json` has `akmon` as a key. A manifest that parses can
 * still hold a string where a table belongs.
 * @param {unknown} table
 * @returns {boolean}
 */
function _namesAkmon(table) {
  return _isPlainTable(table) && Object.hasOwn(/** @type {object} */ (table), "akmon");
}

/**
 * How the consumer's `package.json` pins akmon: `"dev"`, `"runtime"`, `"none"` or `"unreadable"`.
 *
 * Mode `package` mounts no tree: the pin *is* the consumer's dependency declaration, and ADR 0020
 * D05 locks which class it may be — `devDependencies`, never `dependencies`, `optionalDependencies`
 * or `peerDependencies`, because akmon is dev tooling and must not reach the consumer's own users.
 * Every declaration is read and the **worst** answer wins (`runtime` > `dev` > `none`): stopping at
 * the first match would let a correct dev pin hide a runtime one. A manifest that is not a JSON
 * object is `"unreadable"`, not "no pin": npm cannot read it either. No `package.json` is `"none"`.
 * Never reads `pyproject.toml` — the Python pin reader is the Python carrier's.
 * @param {string} projectRoot
 * @returns {"dev" | "runtime" | "none" | "unreadable"}
 */
export function packagePinStatus(projectRoot) {
  const manifest = pyPath(projectRoot, "package.json");
  if (!isFile(manifest)) {
    return "none";
  }
  /** @type {unknown} */
  let document;
  try {
    // npm strips a byte-order mark; the decoder's default does too, and a malformed byte is refused.
    document = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(fs.readFileSync(manifest)));
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof TypeError || isOSError(error)) {
      return "unreadable";
    }
    throw error;
  }
  if (!_isPlainTable(document)) {
    return "unreadable";
  }
  const declared = /** @type {Record<string, unknown>} */ (document);
  if (["dependencies", "optionalDependencies", "peerDependencies"].some((key) => _namesAkmon(declared[key]))) {
    return "runtime";
  }
  return _namesAkmon(declared["devDependencies"]) ? "dev" : "none";
}

/**
 * Whether `path` and `other` are one directory once links are followed; a path that cannot be
 * resolved is not.
 * @param {string} path
 * @param {string} other
 * @returns {boolean}
 */
function _sameDirectory(path, other) {
  try {
    return fs.realpathSync(path) === fs.realpathSync(other);
  } catch {
    return false;
  }
}

/**
 * The standard-tree content this script operates against for `projectRoot`. A mounted record reads
 * the mount at `<AITNA_ROOT>/akmon` when it exists (`bin/sync.py::standard_tree_root`, ADR 0020 D02 as
 * amended by C129). Package mode reads `<root>/node_modules/akmon` — spelled unresolved — when that
 * path is the running tree, the running tree's realpath otherwise: the installed package *is* the
 * pin, so a lingering mount directory from a prior mode does not shadow it.
 * @param {string} projectRoot
 * @returns {string}
 */
export function standardTreeRoot(projectRoot) {
  const mounted = pyPath(aitnaRoot(projectRoot), "akmon");
  if (!isPackageMode(projectRoot) && _exists(mounted)) {
    return mounted;
  }
  const standard = pyPath(projectRoot, "node_modules", "akmon");
  return _sameDirectory(standard, TREE_ROOT) ? standard : TREE_ROOT;
}

/**
 * The directory the Node hook wiring runs its scripts from, relative to the project root:
 * `node_modules/akmon/js/hooks` in package mode (ADR 0020 D05), `<AITNA_ROOT>/akmon/js/hooks` in a
 * mounted one (the C129 amendment of D02). The `{{hooks_dir}}` of both hook-command templates.
 * @param {string} projectRoot
 * @returns {string}
 */
export function nodeHooksDir(projectRoot) {
  return isPackageMode(projectRoot) ? "node_modules/akmon/js/hooks" : `${aitnaRootName()}/akmon/js/hooks`;
}

/**
 * The bytes of the `ruff.toml` the Python `init` writes (`ruff_toml_template`), one for each mode's
 * rules path — `<aitna>/.akmon` in package mode, `<aitna>/akmon` mounted: what `verify`'s
 * `check.ruff-without-python` and `init`'s move of a Python record to Node (C129) recognize, byte for
 * byte, as akmon's own file rather than one the owner edited or wrote.
 * @param {SyncData} data
 * @param {string} aitna
 * @returns {Buffer[]}
 */
export function ruffTomlTemplates(data, aitna) {
  return [".akmon", "akmon"].map((mount) =>
    Buffer.from(fill(data.sync.ruff_toml_template, { rules_path: `${aitna}/${mount}/profiles/ruff.toml` }), "utf8"),
  );
}

/**
 * Whether `root` holds Python (`python_markers`) — the one answer, the Python `has_python` (C129): a
 * marker file at the root (a manifest, a requirements file, a lockfile, by glob), else a Python
 * source outside the dev layer `aitna` and `node_modules` — the files git tracks in a work tree,
 * otherwise a walk that also skips dot-directories and stops after `walk_limit` entries.
 * @param {SyncData} data
 * @param {string} root
 * @param {string} aitna
 * @returns {boolean}
 */
export function hasPython(data, root, aitna) {
  const markers = data.sync.python_markers;
  /** @type {string[]} */
  let names;
  try {
    names = fs
      .readdirSync(root, { withFileTypes: true })
      .filter((entry) => isFile(posix.join(root, entry.name)))
      .map((entry) => entry.name);
  } catch {
    return false;
  }
  if (names.some((name) => markers.files.some((pattern) => fnmatchCase(name, pattern)))) {
    return true;
  }
  const sources =
    _trackedFiles(root, markers.sources) ?? _walkedFiles(root, markers.sources, aitna, markers.walk_limit);
  return sources.some((path) => !_outsideProjectCode(path, aitna));
}

/**
 * Whether a root-relative path sits in the dev layer or a `node_modules` directory.
 * @param {string} relative
 * @param {string} aitna
 * @returns {boolean}
 */
function _outsideProjectCode(relative, aitna) {
  return relative === aitna || relative.startsWith(`${aitna}/`) || relative.split("/").includes("node_modules");
}

/**
 * The files git tracks under `root` matching `pattern`; `null` outside a work tree (or without git).
 * @param {string} root
 * @param {string} pattern
 * @returns {string[] | null}
 */
function _trackedFiles(root, pattern) {
  const listed = spawnSync("git", ["ls-files", "-z", "--", pattern], { cwd: root, encoding: "utf8" });
  if (listed.error !== undefined || listed.status !== 0) {
    return null;
  }
  return listed.stdout.split("\0").filter((name) => name !== "");
}

/**
 * Root-relative files matching `pattern`, skipping the dev layer, `node_modules` and dot-directories:
 * breadth first, in directory order, as the Python twin walks; it stops after `limit` directory
 * entries — a project too large to walk counts only what was seen by then.
 * @param {string} root
 * @param {string} pattern
 * @param {string} aitna
 * @param {number} limit
 * @returns {string[]}
 */
function _walkedFiles(root, pattern, aitna, limit) {
  /** @type {string[]} */
  const found = [];
  let seen = 0;
  /** @type {string[]} */
  const pending = [""];
  while (pending.length > 0) {
    const relative = /** @type {string} */ (pending.shift());
    let entries;
    try {
      entries = fs.readdirSync(relative === "" ? root : posix.join(root, relative), { withFileTypes: true });
    } catch {
      continue;
    }
    seen += entries.length;
    if (seen > limit) {
      return found;
    }
    for (const entry of entries) {
      const path = relative === "" ? entry.name : `${relative}/${entry.name}`;
      if (entry.isDirectory()) {
        if (!entry.name.startsWith(".") && entry.name !== "node_modules" && path !== aitna) {
          pending.push(path);
        }
      } else if (fnmatchCase(entry.name, pattern)) {
        found.push(path);
      }
    }
  }
  return found;
}

/**
 * The shared sync text and tables, as one lazily-read bundle: `bin/sync.json` (beside the Python
 * launcher's `sync.json`), `common/materialization.json` and `common/findings.json`, each read on
 * first access and once per process, never at import time — a broken file fails only the work that
 * reaches it, as in the twin, with `DataFileError` naming the file.
 * @returns {SyncData}
 */
export function readSyncData() {
  /** @type {Record<string, () => unknown>} */
  const readers = {
    sync: () => read(posix.join(TREE_ROOT, "bin", "sync.json")),
    materialization: () => read(posix.join(TREE_ROOT, "common", "materialization.json")),
    findings: readFindingsData,
  };
  /** @type {Record<string, unknown>} */
  const bundle = {};
  for (const [name, reader] of Object.entries(readers)) {
    /** @type {{value: unknown} | null} */
    let loaded = null;
    Object.defineProperty(bundle, name, {
      enumerable: true,
      get() {
        loaded ??= { value: reader() };
        return loaded.value;
      },
    });
  }
  return /** @type {SyncData} */ (bundle);
}

// --------------------------------------------------------------------------------------
// Python's value semantics the module leans on
// --------------------------------------------------------------------------------------

/** Whether `value` is a plain JSON/TOML table — a parsed object, not an array, a date or a class instance. */
function _isPlainTable(/** @type {unknown} */ value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === null || prototype === Object.prototype;
}

/** Whether `value` is a JSON object in either model: an ordered `Map` (a settings document) or a plain object. */
function _isTable(/** @type {unknown} */ value) {
  return value instanceof Map || _isPlainTable(value);
}

/** `table.get(key)` for either model; `undefined` for a missing key. */
function _tableGet(/** @type {Json} */ table, /** @type {string} */ key) {
  if (table instanceof Map) {
    return table.get(key);
  }
  return Object.hasOwn(table, key) ? table[key] : undefined;
}

/** Whether `path` exists, following links (`Path.exists()`). */
function _exists(/** @type {string} */ path) {
  return pyStat(path) !== null;
}

/**
 * `path.relative_to(base)`, lexically: the path below `base`, `.` for `base` itself.
 * @param {string} path
 * @param {string} base
 * @returns {string}
 * @throws {Error} `ValueError` when `path` is not under `base`
 */
function _relativeTo(path, base) {
  if (path === base) {
    return ".";
  }
  const prefix = base.endsWith("/") ? base : `${base}/`;
  if (!path.startsWith(prefix)) {
    throw pyError("ValueError", `${pyRepr(path)} is not in the subpath of ${pyRepr(base)}`);
  }
  return path.slice(prefix.length);
}

/**
 * Whether `ancestor` is one of the lexical parents of `path` (`ancestor in path.parents`).
 * @param {string} ancestor
 * @param {string} path
 * @returns {boolean}
 */
function _isParentOf(ancestor, path) {
  return path !== ancestor && path.startsWith(ancestor.endsWith("/") ? ancestor : `${ancestor}/`);
}

/**
 * `sorted()` over paths: component by component, by code point — not the joined string, which would
 * put `a/c` before `a-b` (`/` is above `-`). A path that is a prefix of another comes first.
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
function _comparePaths(a, b) {
  const left = a.split("/");
  const right = b.split("/");
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    const order = codePointCompare(left[i], right[i]);
    if (order !== 0) {
      return order;
    }
  }
  return left.length - right.length;
}

/** `Path.suffix`: the last `.…` of the final component, `""` for a name that only begins with a dot. */
function _suffix(/** @type {string} */ name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot) : "";
}

/**
 * Why a byte string is not UTF-8, in CPython's words for the first bad sequence
 * (`UnicodeDecodeError.__str__`), or `null` when it decodes.
 * @param {Uint8Array} bytes
 * @returns {string | null}
 */
function _utf8Failure(bytes) {
  const continuation = (/** @type {number} */ at) => bytes[at] >= 0x80 && bytes[at] <= 0xbf;
  let at = 0;
  while (at < bytes.length) {
    const lead = bytes[at];
    if (lead < 0x80) {
      at += 1;
      continue;
    }
    const need =
      lead >= 0xc2 && lead <= 0xdf ? 2 : lead >= 0xe0 && lead <= 0xef ? 3 : lead >= 0xf0 && lead <= 0xf4 ? 4 : 0;
    /** @type {string | null} */
    let reason = null;
    let end = at + 1;
    if (need === 0) {
      reason = "invalid start byte";
    } else {
      // The bytes there are checked as far as they go, so a truncated sequence that is already
      // wrong is "invalid continuation byte", and only a prefix that could still be completed is
      // "unexpected end of data".
      const available = bytes.length - at;
      const second = bytes[at + 1];
      let bad = 0;
      if (
        available >= 2 &&
        (!continuation(at + 1) ||
          (lead === 0xe0 && second < 0xa0) ||
          (lead === 0xed && second >= 0xa0) ||
          (lead === 0xf0 && second < 0x90) ||
          (lead === 0xf4 && second >= 0x90))
      ) {
        bad = 1;
      } else if (need >= 3 && available >= 3 && !continuation(at + 2)) {
        bad = 2;
      } else if (need === 4 && available >= 4 && !continuation(at + 3)) {
        bad = 3;
      }
      if (bad > 0) {
        reason = "invalid continuation byte";
        end = at + bad;
      } else if (available < need) {
        reason = "unexpected end of data";
        end = bytes.length;
      }
    }
    if (reason !== null) {
      return end === at + 1
        ? `'utf-8' codec can't decode byte 0x${lead.toString(16).padStart(2, "0")} in position ${at}: ${reason}`
        : `'utf-8' codec can't decode bytes in position ${at}-${end - 1}: ${reason}`;
    }
    at += need;
  }
  return null;
}

/**
 * `Path.read_text(encoding="utf-8")` with the codec's own sentence when the bytes are not UTF-8: the
 * settings reader's `ValueError` handler prints it.
 * @param {string} path
 * @returns {string}
 */
function _readText(path) {
  try {
    return readText(path);
  } catch (error) {
    if (!(error instanceof Error) || error.name !== "UnicodeDecodeError") {
      throw error;
    }
    const failure = _utf8Failure(fs.readFileSync(path));
    throw pyError("UnicodeDecodeError", failure ?? error.message);
  }
}

// --------------------------------------------------------------------------------------
// The generated pointers
// --------------------------------------------------------------------------------------

/**
 * One generated file's target path and wanted content.
 */
export class PlannedFile {
  /**
   * @param {string} path
   * @param {string} content
   */
  constructor(path, content) {
    this.path = path;
    this.content = content;
    Object.freeze(this);
  }
}

/**
 * The outcome of applying a plan: what changed, what was deleted, what was already right.
 */
export class Result {
  /**
   * @param {string[]} changed
   * @param {string[]} deleted
   * @param {string[]} ok
   * @param {string[]} errors
   */
  constructor(changed, deleted, ok, errors) {
    this.changed = changed;
    this.deleted = deleted;
    this.ok = ok;
    this.errors = errors;
  }
}

/** The generated `CLAUDE.md` body (`sync.json`). */
function _claudeMd(/** @type {SyncData} */ data) {
  return fill(data.sync.vendor_pointers.claude_md, {
    banner: generatedBanner(data.materialization),
    aitna: aitnaRootName(),
  });
}

/** The generated Copilot instructions body (`sync.json`). */
function _copilotMd(/** @type {SyncData} */ data) {
  return fill(data.sync.vendor_pointers.copilot_md, { banner: generatedBanner(data.materialization) });
}

/** The generated `GEMINI.md` body (`sync.json`). */
function _geminiMd(/** @type {SyncData} */ data) {
  return fill(data.sync.vendor_pointers.gemini_md, { banner: generatedBanner(data.materialization) });
}

/** The generated Codex `README.md` body (`sync.json`). */
function _codexReadme(/** @type {SyncData} */ data) {
  return fill(data.sync.vendor_pointers.codex_readme, { banner: generatedBanner(data.materialization) });
}

/**
 * Every spelling of an akmon hook command the generator has ever emitted, independent of the
 * project's current mode: recognising an entry as akmon-managed must not depend on which mode (or
 * which version) wrote it, so switching modes replaces the other spelling's entries instead of
 * leaving them orphaned beside the new ones (ADR 0009 §4). The closing quote of the launcher marker
 * is part of it: a bare `akmon hook ` would also match a project's own hook that merely mentions it.
 * @param {SyncData} data
 * @returns {string[]}
 */
function _akmonHookMarkers(data) {
  const aitna = aitnaRootName();
  return data.sync.akmon_hook_markers.map((shape) => fill(shape, { aitna, cli: data.sync.cli_name }));
}

/** An ordered JSON object from `[key, value]` pairs — a `Map`, so the key order a file is written in is the one built. */
function _object(/** @type {Array<[string, Json]>} */ pairs) {
  return new Map(pairs);
}

/**
 * The Codex wiring: `node "$(git rev-parse --show-toplevel)/<hooks dir>/codex-hook.mjs"` with the
 * advisory name appended, the hooks directory being {@link nodeHooksDir}'s. The matcher/command table lives in `sync.json`: routes, not
 * spellings — `Edit`, `Write` and `apply_patch` are three live aliases for the same patch call,
 * while the shell (the route its model took when a denied patch was refused) matches as `Bash`
 * (C49, measured on codex 0.146.0). Not widened to `.*`: an unconditional hook on every shell call
 * costs latency and noise on the hottest tool and buys precision nowhere.
 * @param {SyncData} data
 * @param {string} root
 * @returns {Map<string, Json>}
 */
export function codexHooks(data, root) {
  const base = fill(data.sync.node_codex_hook_command, {
    anchor: "$(git rev-parse --show-toplevel)",
    hooks_dir: nodeHooksDir(root),
  });
  const hooks = new Map();
  for (const [event, entries] of Object.entries(data.sync.codex_hooks)) {
    hooks.set(
      event,
      entries.map((entry) =>
        _object([
          ["matcher", entry.matcher],
          [
            "hooks",
            entry.commands.map(([script, status]) =>
              _object([
                ["type", "command"],
                ["command", `${base} ${script}`],
                ["statusMessage", status],
              ]),
            ),
          ],
        ]),
      ),
    );
  }
  return _object([["hooks", hooks]]);
}

/**
 * The Claude wiring: `node "$CLAUDE_PROJECT_DIR/<hooks dir>/<script>.mjs"` ({@link nodeHooksDir}), from
 * the matcher/command table of `sync.json`. The Bash entry also carries the unclassified-shell-route
 * diagnostic (C49, ADR-0012/D02): the edit-tool advisories would not see a write that arrives
 * through Bash. The combined-matcher entry stays one entry because `mergeHookEntries` dedups by
 * command; it includes Read|Grep|Glob so the nudge/ask also see read/sweep drift. UserPromptSubmit
 * is per-turn (a mid-session /model switch rebinds silently); Stop holds a turn at or above the
 * gate's count floors (C25) — Claude only; not wired on Codex until a live probe confirms its
 * main-agent Stop (M151).
 * @param {SyncData} data
 * @param {string} root
 * @returns {Map<string, Json>}
 */
export function claudeHooks(data, root) {
  const hooksDir = nodeHooksDir(root);
  const hooks = new Map();
  for (const [event, entries] of Object.entries(data.sync.claude_hooks)) {
    hooks.set(
      event,
      entries.map((entry) => {
        const commands = entry.commands.map((script) =>
          _object([
            ["type", "command"],
            [
              "command",
              fill(data.sync.node_hook_command, { anchor: "$CLAUDE_PROJECT_DIR", hooks_dir: hooksDir, script }),
            ],
          ]),
        );
        return entry.matcher === null
          ? _object([["hooks", commands]])
          : _object([
              ["matcher", entry.matcher],
              ["hooks", commands],
            ]);
      }),
    );
  }
  return _object([["hooks", hooks]]);
}

/**
 * The commands of one settings entry (`{"hooks": [{"command": …}]}`); nothing for any other shape.
 * @param {Json} entry
 * @returns {Set<string>}
 */
function _hookCommands(entry) {
  /** @type {Set<string>} */
  const commands = new Set();
  if (!_isTable(entry)) {
    return commands;
  }
  const hooks = _tableGet(entry, "hooks");
  if (!Array.isArray(hooks)) {
    return commands;
  }
  for (const hook of hooks) {
    const command = _isTable(hook) ? _tableGet(hook, "command") : undefined;
    if (typeof command === "string") {
      commands.add(command);
    }
  }
  return commands;
}

/**
 * Whether every command of a settings entry is one akmon wrote (an entry with no command is not).
 * @param {SyncData} data
 * @param {Json} entry
 * @returns {boolean}
 */
export function isAkmonEntry(data, entry) {
  const commands = _hookCommands(entry);
  const markers = _akmonHookMarkers(data);
  return commands.size > 0 && [...commands].every((command) => markers.some((marker) => command.includes(marker)));
}

/**
 * The hook entries of one event after a sync: the stale akmon-managed ones dropped, the wanted ones
 * appended unless the user already wires the same command. Dropping first keeps user-authored hooks
 * untouched while letting sync rewrite its own (e.g. a renamed hook path) instead of leaving a
 * dangling duplicate.
 * @param {SyncData} data
 * @param {Json} existing
 * @param {Json[]} wanted
 * @returns {Json[]}
 */
export function mergeHookEntries(data, existing, wanted) {
  if (!Array.isArray(existing)) {
    return [...wanted];
  }
  const merged = existing.filter((entry) => !isAkmonEntry(data, entry));
  /** @type {Set<string>} */
  const existingCommands = new Set();
  for (const entry of merged) {
    for (const command of _hookCommands(entry)) {
      existingCommands.add(command);
    }
  }
  for (const entry of wanted) {
    const commands = _hookCommands(entry);
    if (commands.size === 0 || [...commands].every((command) => !existingCommands.has(command))) {
      merged.push(entry);
      for (const command of commands) {
        existingCommands.add(command);
      }
    }
  }
  return merged;
}

// --------------------------------------------------------------------------------------
// `json.loads` for .claude/settings.json
// --------------------------------------------------------------------------------------

/** The point a scan stopped at without a value (`StopIteration(idx)` in the C scanner). */
class _Stop {
  /** @param {number} at */
  constructor(at) {
    this.at = at;
  }
}

/** Whether `code` is a JSON whitespace character. */
function _isSpace(/** @type {number} */ code) {
  return code === 0x20 || code === 0x09 || code === 0x0a || code === 0x0d;
}

/** The value of the hex digit `code`, or -1. */
function _hexValue(/** @type {number} */ code) {
  if (code >= 0x30 && code <= 0x39) {
    return code - 0x30;
  }
  if (code >= 0x61 && code <= 0x66) {
    return code - 0x61 + 10;
  }
  if (code >= 0x41 && code <= 0x46) {
    return code - 0x41 + 10;
  }
  return -1;
}

/** Python's `int(str)` digit limit (3.11+). */
const _MAX_INT_DIGITS = 4300;

/**
 * Python's `json.loads` over a document, as ordered `Map`s: the C scanner's grammar (`NaN`,
 * `Infinity`, `-Infinity`; strict strings), its error sentences, and the float/int distinction kept
 * (`FloatValue`), because `json.dumps` writes the document back and must find it unchanged.
 */
class _JsonDecoder {
  /**
   * @param {string} text
   * @param {boolean} [lossy] keep an integer beyond 2**53 as the nearest number instead of refusing
   *   it: right for a reader that only tests the document (`verify`), wrong for one that writes it back
   */
  constructor(text, lossy = false) {
    this.text = text;
    this.lossy = lossy;
  }

  /**
   * `JSONDecodeError(msg, doc, pos)`: line and column count code points, as Python's do.
   * @param {string} message
   * @param {number} at UTF-16 index
   * @returns {Error}
   */
  fail(message, at) {
    const before = this.text.slice(0, at);
    const line = before.split("\n").length;
    const column = pyLen(before.slice(before.lastIndexOf("\n") + 1)) + 1;
    return pyError("JSONDecodeError", `${message}: line ${line} column ${column} (char ${pyLen(before)})`);
  }

  /** @param {number} at @returns {number} */
  skipSpace(at) {
    while (at < this.text.length && _isSpace(this.text.charCodeAt(at))) {
      at += 1;
    }
    return at;
  }

  /** @returns {Json} */
  document() {
    if (this.text.startsWith("\ufeff")) {
      throw this.fail("Unexpected UTF-8 BOM (decode using utf-8-sig)", 0);
    }
    /** @type {[Json, number]} */
    let scanned;
    const start = this.skipSpace(0);
    try {
      scanned = this.value(start);
    } catch (stop) {
      if (stop instanceof _Stop) {
        throw this.fail("Expecting value", stop.at);
      }
      throw stop;
    }
    const end = this.skipSpace(scanned[1]);
    if (end !== this.text.length) {
      throw this.fail("Extra data", end);
    }
    return scanned[0];
  }

  /**
   * `scan_once`: the value at `at` and where it ends.
   * @param {number} at
   * @returns {[Json, number]}
   * @throws {_Stop} where a value was expected and none is
   */
  value(at) {
    const { text } = this;
    if (at >= text.length) {
      throw new _Stop(at);
    }
    const char = text[at];
    if (char === '"') {
      return this.string(at + 1);
    }
    if (char === "{") {
      return this.object(at + 1);
    }
    if (char === "[") {
      return this.array(at + 1);
    }
    /** @type {Array<[string, Json]>} */
    const literals = [
      ["null", null],
      ["true", true],
      ["false", false],
      ["NaN", new FloatValue(NaN)],
      ["Infinity", new FloatValue(Infinity)],
      ["-Infinity", new FloatValue(-Infinity)],
    ];
    for (const [literal, value] of literals) {
      if (text.startsWith(literal, at)) {
        return [value, at + literal.length];
      }
    }
    return this.number(at);
  }

  /**
   * The number at `start`: `-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?`, ASCII digits only.
   * @param {number} start
   * @returns {[Json, number]}
   */
  number(start) {
    const { text } = this;
    const digit = (/** @type {number} */ i) =>
      i < text.length && text.charCodeAt(i) >= 0x30 && text.charCodeAt(i) <= 0x39;
    let at = start;
    if (text[at] === "-") {
      at += 1;
    }
    if (!digit(at)) {
      throw new _Stop(start);
    }
    if (text[at] === "0") {
      at += 1;
    } else {
      while (digit(at)) {
        at += 1;
      }
    }
    let isFloat = false;
    if (text[at] === "." && digit(at + 1)) {
      isFloat = true;
      at += 1;
      while (digit(at)) {
        at += 1;
      }
    }
    if (text[at] === "e" || text[at] === "E") {
      let exponent = at + 1;
      if (text[exponent] === "+" || text[exponent] === "-") {
        exponent += 1;
      }
      if (digit(exponent)) {
        isFloat = true;
        while (digit(exponent)) {
          exponent += 1;
        }
        at = exponent;
      }
    }
    const literal = text.slice(start, at);
    if (isFloat) {
      return [new FloatValue(Number(literal)), at];
    }
    const digits = literal.length - (literal.startsWith("-") ? 1 : 0);
    if (digits > _MAX_INT_DIGITS) {
      throw pyError(
        "ValueError",
        `Exceeds the limit (${_MAX_INT_DIGITS} digits) for integer string conversion: value has ${digits} digits`,
      );
    }
    const number = Number(literal);
    if (!Number.isSafeInteger(number) && !this.lossy) {
      throw pyError("ValueError", `integer ${literal} is beyond 2**53 and cannot be written back unchanged`);
    }
    return [number, at];
  }

  /**
   * `scanstring` (strict): the string whose opening quote sits at `begin - 1`.
   * @param {number} begin
   * @returns {[string, number]}
   */
  string(begin) {
    const { text } = this;
    const start = begin - 1;
    let out = "";
    let end = begin;
    for (;;) {
      let next = end;
      let char = "";
      for (; next < text.length; next++) {
        char = text[next];
        if (char === '"' || char === "\\") {
          break;
        }
        if (text.charCodeAt(next) <= 0x1f) {
          throw this.fail("Invalid control character at", next);
        }
      }
      if (next >= text.length) {
        throw this.fail("Unterminated string starting at", start);
      }
      out += text.slice(end, next);
      next += 1;
      if (char === '"') {
        return [out, next];
      }
      if (next === text.length) {
        throw this.fail("Unterminated string starting at", start);
      }
      const escape = text[next];
      if (escape !== "u") {
        end = next + 1;
        const simple = /** @type {Record<string, string>} */ ({
          '"': '"',
          "\\": "\\",
          "/": "/",
          b: "\b",
          f: "\f",
          n: "\n",
          r: "\r",
          t: "\t",
        });
        if (!Object.hasOwn(simple, escape)) {
          throw this.fail("Invalid \\escape", end - 2);
        }
        out += simple[escape];
        continue;
      }
      next += 1;
      end = next + 4;
      if (end >= text.length) {
        throw this.fail("Invalid \\uXXXX escape", next - 1);
      }
      const code = this.hex4(next, end - 5);
      next += 4;
      // A high surrogate is joined to a following `\uXXXX` low one; the pair is two UTF-16 units here
      // either way, but the second escape must still be well formed and in range of the text.
      if (code >= 0xd800 && code <= 0xdbff && end + 6 < text.length && text[next] === "\\" && text[next + 1] === "u") {
        end += 6;
        const low = this.hex4(next + 2, end - 5);
        if (low >= 0xdc00 && low <= 0xdfff) {
          out += String.fromCharCode(code, low);
          continue;
        }
        end -= 6;
      }
      out += String.fromCharCode(code);
    }
  }

  /**
   * Four hex digits at `at`.
   * @param {number} at
   * @param {number} errorAt where `Invalid \uXXXX escape` is reported
   * @returns {number}
   */
  hex4(at, errorAt) {
    let value = 0;
    for (let i = at; i < at + 4; i++) {
      const digit = _hexValue(this.text.charCodeAt(i));
      if (digit < 0) {
        throw this.fail("Invalid \\uXXXX escape", errorAt);
      }
      value = value * 16 + digit;
    }
    return value;
  }

  /**
   * An object whose `{` sits at `begin - 1`.
   * @param {number} begin
   * @returns {[Map<string, Json>, number]}
   */
  object(begin) {
    const { text } = this;
    const table = new Map();
    let at = this.skipSpace(begin);
    if (at >= text.length || text[at] !== "}") {
      for (;;) {
        if (at >= text.length || text[at] !== '"') {
          throw this.fail("Expecting property name enclosed in double quotes", at);
        }
        const [key, afterKey] = this.string(at + 1);
        at = this.skipSpace(afterKey);
        if (at >= text.length || text[at] !== ":") {
          throw this.fail("Expecting ':' delimiter", at);
        }
        at = this.skipSpace(at + 1);
        const [value, afterValue] = this.value(at);
        table.set(key, value);
        at = this.skipSpace(afterValue);
        if (at < text.length && text[at] === "}") {
          break;
        }
        if (at >= text.length || text[at] !== ",") {
          throw this.fail("Expecting ',' delimiter", at);
        }
        at = this.skipSpace(at + 1);
      }
    }
    return [table, at + 1];
  }

  /**
   * An array whose `[` sits at `begin - 1`.
   * @param {number} begin
   * @returns {[Json[], number]}
   */
  array(begin) {
    const { text } = this;
    /** @type {Json[]} */
    const items = [];
    let at = this.skipSpace(begin);
    if (at >= text.length || text[at] !== "]") {
      for (;;) {
        const [value, afterValue] = this.value(at);
        items.push(value);
        at = this.skipSpace(afterValue);
        if (at < text.length && text[at] === "]") {
          break;
        }
        if (at >= text.length || text[at] !== ",") {
          throw this.fail("Expecting ',' delimiter", at);
        }
        at = this.skipSpace(at + 1);
      }
    }
    return [items, at + 1];
  }
}

/**
 * The JSON object at `path`, as an ordered `Map`: `{}` when there is no file.
 * @param {string} path
 * @param {{lossy?: boolean}} [options] `lossy`: a reader that never writes the document back takes an
 *   integer beyond 2**53 as the nearest number (the Python reads it exactly)
 * @returns {Map<string, Json>}
 * @throws {Error} `ValueError` naming the file when it is not JSON or not an object
 */
export function readJson(path, { lossy = false } = {}) {
  if (!_exists(path)) {
    return new Map();
  }
  /** @type {Json} */
  let value;
  try {
    value = new _JsonDecoder(_readText(path), lossy).document();
  } catch (error) {
    if (error instanceof Error && error.name === "JSONDecodeError") {
      throw pyError("ValueError", `${path}: invalid JSON: ${error.message}`);
    }
    throw error;
  }
  if (!(value instanceof Map)) {
    throw pyError("ValueError", `${path}: expected a JSON object`);
  }
  return value;
}

/**
 * `.claude/settings.json` with the hook wiring merged in: everything else of the file verbatim,
 * user-authored hooks untouched.
 * @param {SyncData} data
 * @param {string} root
 * @returns {PlannedFile}
 * @throws {Error} `ValueError` when the file is not a JSON object with an object for `hooks`
 */
export function claudeSettings(data, root) {
  const path = pyPath(root, ".claude", "settings.json");
  const settings = readJson(path);
  if (!settings.has("hooks")) {
    settings.set("hooks", new Map());
  }
  const hooks = settings.get("hooks");
  if (!(hooks instanceof Map)) {
    throw pyError("ValueError", `${path}: expected hooks to be a JSON object`);
  }
  for (const [eventName, wantedEntries] of claudeHooks(data, root).get("hooks")) {
    hooks.set(eventName, mergeHookEntries(data, hooks.get(eventName), wantedEntries));
  }
  return new PlannedFile(path, wiringForm(settings));
}

// --------------------------------------------------------------------------------------
// Skills
// --------------------------------------------------------------------------------------

/**
 * `sorted(directory.glob("*\/SKILL.md"))`: the skill directories directly under `directory` — hidden
 * ones included, links to directories followed — that hold a `SKILL.md`.
 * @param {string} directory
 * @returns {string[]}
 */
function _globSkills(directory) {
  if (!isDir(directory)) {
    return [];
  }
  /** @type {string[]} */
  let names = [];
  try {
    names = fs.readdirSync(directory);
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
  }
  return codePointSort(names)
    .filter((name) => isDir(pyPath(directory, name)) && _exists(pyPath(directory, name, "SKILL.md")))
    .map((name) => pyPath(directory, name, "SKILL.md"));
}

/**
 * Every skill source the project sees — the standard's, the dev layer's, the project's own — and the
 * duplicate names found among them (the first one wins).
 * @param {SyncData} data
 * @param {string} root
 * @returns {[string[], string[]]}
 */
export function skillSources(data, root) {
  const searchRoots = [
    pyPath(standardTreeRoot(root), "skills"),
    pyPath(aitnaRoot(root), "skills"),
    pyPath(root, "skills"),
  ];
  /** @type {string[]} */
  const sources = [];
  /** @type {string[]} */
  const errors = [];
  /** @type {Map<string, string>} */
  const names = new Map();
  for (const searchRoot of searchRoots) {
    if (!isDir(searchRoot)) {
      continue;
    }
    for (const source of _globSkills(searchRoot)) {
      const name = posix.basename(posix.dirname(source));
      if (names.has(name)) {
        errors.push(`duplicate skill name ${pyRepr(name)}: ${names.get(name)} and ${source}`);
        continue;
      }
      names.set(name, source);
      sources.push(source);
    }
  }
  return [sources, errors];
}

/**
 * The lines between a SKILL.md's opening and closing `---`, or `null` without both.
 * @param {string} text
 * @returns {string | null}
 */
export function skillFrontmatterBlock(text) {
  const lines = pySplitlines(text);
  if (lines.length === 0 || pyStrip(lines[0]) !== "---") {
    return null;
  }
  for (let index = 1; index < lines.length; index++) {
    if (pyStrip(lines[index]) === "---") {
      return lines.slice(1, index).join("\n");
    }
  }
  return null;
}

/**
 * One skill's stub in each harness's skills directory: its frontmatter, then a pointer.
 *
 * The frontmatter is the source's, copied verbatim, because it is what a harness selects a skill by —
 * and only from the file in its own directory: Claude Code lists a stub without frontmatter under its
 * first line, the bare name, and Codex refuses to load it at all (M54, M55). The body stays a
 * pointer, so the instructions keep one source. The banner goes inside the frontmatter as a YAML
 * comment, since the frontmatter has to open the file and both harnesses read the comment as a
 * comment. A source without frontmatter keeps the bare pointer; `verify` reports that source.
 *
 * A relative link whenever the source is in the repository — the project's own skills and, in a Node
 * project, the standard's too, which sits at `node_modules/akmon` inside the root. When it is not
 * (the running tree is somewhere else), the relative link would spell a path of this machine, and
 * the pointer reaches the standard through `akmon path` instead.
 * @param {SyncData} data
 * @param {string} root
 * @param {string} source
 * @returns {PlannedFile[]}
 */
export function skillStubs(data, root, source) {
  const name = posix.basename(posix.dirname(source));
  const frontmatter = skillFrontmatterBlock(_readText(source));
  let inRepo;
  try {
    _relativeTo(source, root);
    inRepo = true;
  } catch (error) {
    if (!(error instanceof Error) || error.name !== "ValueError") {
      throw error;
    }
    inRepo = false;
  }
  const shapes = data.sync.skill_stubs;
  /** @type {PlannedFile[]} */
  const stubs = [];
  for (const skillsDir of data.sync.skill_stub_dirs) {
    const path = pyPath(root, skillsDir, name, "SKILL.md");
    let pointer;
    if (inRepo) {
      const relativeSource = posix.relative(posix.dirname(path), source);
      pointer = `Source skill: [${relativeSource}](${relativeSource})`;
    } else {
      pointer = `Source skill: \`$(${data.sync.cli_name} path)/skills/${name}/SKILL.md\``;
    }
    const body = `${pointer}\n\nRead and follow the source SKILL.md. Do not duplicate its contents here.\n`;
    const banner = generatedBanner(data.materialization);
    const content =
      frontmatter === null
        ? fill(shapes.no_frontmatter, { name, banner, body })
        : fill(shapes.with_frontmatter, { name, banner, body, frontmatter });
    stubs.push(new PlannedFile(path, content));
  }
  return stubs;
}

// --------------------------------------------------------------------------------------
// The files the standard is imported from
// --------------------------------------------------------------------------------------

// Fenced blocks first, then inline code spans: the akmon block in AGENTS.md *documents* the import
// as well as making it ("add any other (`@_aitna/.akmon/profiles/<name>.md`)"), and read literally the
// quoted form is indistinguishable from the real thing. Code spans are exactly where prose quotes a path it does not mean, so
// stripping them separates the two without requiring a real import to sit in any particular column.
// The Python pattern is `^(?P<fence>```|~~~).*?(?:^(?P=fence)[^\n]*$|\Z)` under MULTILINE | DOTALL.
const _FENCED_BLOCK = /(?<![^\n])(?<fence>```|~~~)[^]*?(?:(?<![^\n])\k<fence>[^\n]*(?![^\n])|(?![^]))/g;
const _INLINE_CODE = /`[^`\n]*`/g;

/** `re.escape` for the characters a prefix can hold that a pattern reads as syntax. */
function _escapeRegExp(/** @type {string} */ text) {
  return text.replace(/[.*+?^${}()|[\]\\/-]/g, "\\$&");
}

/**
 * Imports of a file the standard has moved, and where it went (`sync.json`). A closed list rather
 * than a guess by file name: an unresolved `@`-import produces no diagnostic anywhere, so the plan
 * error is the only place a consumer learns the new line, and it has to name that line exactly.
 * @param {SyncData} data
 * @returns {Record<string, string>}
 */
export function movedImports(data) {
  return { ...data.sync.moved_imports };
}

/**
 * The `@`-import prefix of the standard's files in this project's `AGENTS.md`: the materialized copy
 * in package mode, the mount otherwise.
 * @param {string} root
 * @returns {string}
 */
export function importPrefix(root) {
  return isPackageMode(root) ? `@${aitnaRootName()}/.akmon/` : `@${aitnaRootName()}/akmon/`;
}

/**
 * A language profile a project calls for, and what named its language: `source` is the manifest
 * that named it (`pyproject.toml`) or, when no manifest did, the language value that matched,
 * spelled as the caller passed it.
 * @typedef {object} LanguageProfile
 * @property {string} profile
 * @property {string} source
 */

/**
 * The language profiles `root` calls for, in the table's order (`sync.json`). A profile is called
 * for when one of `languages` names its language — a value is split on `/` and compared without
 * case, so a recorded `package/python` names `python` — or when one of its manifests is a file at
 * `root`. An unknown or unclassified language calls for none. `init` writes one import per answer;
 * `verify` warns on an answer with no import.
 * @param {SyncData} data
 * @param {string} root
 * @param {readonly string[]} languages
 * @returns {LanguageProfile[]}
 */
export function languageProfiles(data, root, languages) {
  /** @type {LanguageProfile[]} */
  const found = [];
  for (const entry of data.sync.language_profiles) {
    const manifest = entry.manifests.find((name) => isFile(pyPath(root, name)));
    const named = languages.find((value) =>
      value.split("/").some((part) => entry.languages.includes(pyStrip(part).toLowerCase())),
    );
    const source = manifest ?? named;
    if (source !== undefined) {
      found.push({ profile: entry.profile, source });
    }
  }
  return found;
}

/**
 * One `@`-import of a file under a `profiles/` directory: `prefix` is everything between `@` and
 * `profiles/` (`_aitna/.akmon/`; empty when relative), `name` the profile's file name (`python.md`),
 * and `line` the import as `AGENTS.md` spells it.
 * @typedef {object} ProfileImport
 * @property {string} prefix
 * @property {string} name
 * @property {string} line
 */

/** A profile import as the harness reads it: a token starting a line or following whitespace. */
const _PROFILE_IMPORT = /(?<![^\t\n\v\f\r ])@([^\t\n\v\f\r `]*?)profiles\/([A-Za-z0-9._-]+\.md)(?![^\t\n\v\f\r ])/g;

/**
 * Every profile `@`-import `text` makes, in order. Code spans and fenced blocks are skipped as the
 * materialization scan skips them: there the block quotes the form (`@<prefix>profiles/<name>.md`)
 * without making the import.
 * @param {string} text
 * @returns {ProfileImport[]}
 */
export function profileImports(text) {
  const visible = text.replace(_FENCED_BLOCK, "\n").replace(_INLINE_CODE, " ");
  return [...visible.matchAll(_PROFILE_IMPORT)].map((match) => ({
    prefix: match[1],
    name: match[2],
    line: `@${match[1]}profiles/${match[2]}`,
  }));
}

/**
 * `(file, value)` for every ruff configuration of the project that `extend`s a file. This is how a
 * project runs akmon's Python rules the standard way — `extend` pointing at `profiles/ruff.toml` in
 * the standard tree — so the target is owed the same guarantee an `@`-import is: it resolves, and in
 * package mode it is materialized. A file that does not parse is skipped here; ruff itself reports it.
 * @param {SyncData} data
 * @param {string} root
 * @returns {Array<[string, string]>}
 */
export function ruffExtends(data, root) {
  /** @type {Array<[string, string]>} */
  const found = [];
  for (const [name, keys] of data.sync.ruff_configs) {
    const path = pyPath(root, name);
    if (!isFile(path)) {
      continue;
    }
    /** @type {unknown} */
    let table;
    try {
      const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(fs.readFileSync(path));
      // `tomllib` refuses a byte-order mark; the vendored parser would fold it in.
      if (text.startsWith("\ufeff")) {
        continue;
      }
      table = parseToml(text);
    } catch (error) {
      if (error instanceof Error && (error instanceof TomlError || error instanceof TypeError || isOSError(error))) {
        continue;
      }
      throw error;
    }
    for (const key of keys) {
      table =
        _isPlainTable(table) && Object.hasOwn(/** @type {object} */ (table), key)
          ? /** @type {Json} */ (table)[key]
          : {};
    }
    const value = _isPlainTable(table) ? /** @type {Json} */ (table)["extend"] : undefined;
    if (typeof value === "string") {
      found.push([name, value]);
    }
  }
  return found;
}

/**
 * The standard's files the project actually uses, and any plan errors.
 *
 * The files — as `guardrails/<name>` and `profiles/<name>` — are every file `AGENTS.md`
 * `@`-imports, and the ruff rules a ruff configuration of the project `extend`s. Read from the
 * documents rather than derived from the recorded archetype: `init` writes a fresh block's
 * language-profile imports from {@link languageProfiles}, but the block is hand-owned from then on —
 * a human adds the profile of a language `init` did not detect, or an environment profile, and
 * removes one — so the document, not a derivation, is what the harness loads.
 *
 * Checked against the tree the project runs: an import whose target the standard does not ship
 * resolves to nothing, silently, and this error is the only thing that says so.
 * @param {SyncData} data
 * @param {string} root
 * @returns {[string[], string[]]}
 */
export function importedStandardFiles(data, root) {
  const prefix = importPrefix(root);
  const pathPrefix = prefix.slice(1);
  /** @type {Map<string, string>} */
  const origins = new Map();
  /** @param {string} name @param {string} origin */
  const setdefault = (name, origin) => {
    if (!origins.has(name)) {
      origins.set(name, origin);
    }
  };
  if (isPackageMode(root)) {
    origins.set(data.sync.always_materialized, "AGENTS.md imports");
  }
  const textPath = pyPath(root, "AGENTS.md");
  if (isFile(textPath)) {
    const text = _readText(textPath).replace(_FENCED_BLOCK, "\n").replace(_INLINE_CODE, " ");
    const directories = importedDirs(data.materialization).join("|");
    const pattern = new RegExp(`${_escapeRegExp(prefix)}((?:${directories})/[A-Za-z0-9._-]+)`, "g");
    for (const match of text.matchAll(pattern)) {
      setdefault(match[1], "AGENTS.md imports");
    }
  }
  for (const [config, value] of ruffExtends(data, root)) {
    const name = value.startsWith(pathPrefix) ? value.slice(pathPrefix.length) : value;
    if (value.startsWith(pathPrefix) && importedDirs(data.materialization).includes(name.split("/")[0])) {
      setdefault(name, `${config} extends`);
    }
  }
  const source = standardTreeRoot(root);
  const moved = movedImports(data);
  /** @type {string[]} */
  const errors = [];
  for (const name of codePointSort([...origins.keys()])) {
    if (isFile(pyPath(source, name))) {
      continue;
    }
    const origin = /** @type {string} */ (origins.get(name));
    const line = origin === "AGENTS.md imports" ? prefix : pathPrefix;
    const target = Object.hasOwn(moved, name) ? moved[name] : "";
    if (target) {
      errors.push(`${origin} ${name}, which the standard moved to ${target}: replace the line with ${line}${target}`);
    } else {
      errors.push(`${origin} a file the standard does not ship: ${name}`);
    }
  }
  return [codePointSort([...origins.keys()]), errors];
}

/**
 * Package-mode materialization (ADR 0009 §4, narrowed by C77, widened to profiles by ADR 0014): the
 * guardrails and profiles the consumer's `AGENTS.md` imports, the ruff rules its ruff configuration
 * extends, and nothing else. Nothing executable is copied: the hooks and the `common` code they
 * import sit in `node_modules/akmon`, and `node` runs them from there.
 *
 * The guardrails are the one exception. The import lives in `AGENTS.md`: a committed, hand-owned
 * file shared by every developer, and Codex does not expand the import at all (it reads `AGENTS.md`
 * literally — see `meta/design/codex-runtime-contract.md`), so the copy serves the one harness that
 * does not follow the import and makes the rule files a reviewed part of the repository.
 *
 * Outside package mode nothing is written, but the import errors are still returned.
 * @param {SyncData} data
 * @param {string} root
 * @returns {[PlannedFile[], string[]]}
 */
export function materializedFiles(data, root) {
  const [names, errors] = importedStandardFiles(data, root);
  if (!isPackageMode(root)) {
    return [[], errors];
  }
  const source = standardTreeRoot(root);
  const dest = pyPath(aitnaRoot(root), ".akmon");
  const files = names
    .filter((name) => isFile(pyPath(source, name)))
    .map(
      (name) =>
        new PlannedFile(
          pyPath(dest, name),
          materializedText(data.materialization, name, _readText(pyPath(source, name))),
        ),
    );
  return [files, errors];
}

/**
 * Set a top-level `key = "value"` line in TOML-ish `text`, preserving everything else verbatim —
 * comments, other keys, and `[section]`s. Updates an existing top-level (pre-first-`[section]`) line
 * for `key` in place; else inserts one just before the first `[section]` header (or appends at the
 * end if none). A minimal, comment-preserving alternative to a full parse+rewrite — `.akmon.toml`
 * mixes tool-written fields (`mount`, `akmon_version`, and `last_realign`) with hand-written ones
 * (`attached_archetype`, `[test]`…) that a full round-trip would risk losing.
 * @param {string} text
 * @param {string} key
 * @param {string} value
 * @returns {string}
 */
export function upsertTomlKey(text, key, value) {
  const lines = pySplitlines(text);
  const newLine = `${key} = "${value}"`;
  const sectionIndex = lines.findIndex((line) => pyStrip(line).startsWith("["));
  const topLines = sectionIndex >= 0 ? lines.slice(0, sectionIndex) : lines;
  let replaced = false;
  for (let i = 0; i < topLines.length; i++) {
    const stripped = pyStrip(topLines[i]);
    if (stripped.startsWith("#")) {
      continue;
    }
    const eq = stripped.indexOf("=");
    if (eq >= 0 && pyStrip(stripped.slice(0, eq)) === key) {
      lines[i] = newLine;
      replaced = true;
      break;
    }
  }
  if (!replaced) {
    lines.splice(sectionIndex >= 0 ? sectionIndex : lines.length, 0, newLine);
  }
  return lines.join("\n") + (text.endsWith("\n") || text === "" ? "\n" : "");
}

/**
 * The version of the tree this module runs from: `version` in its `package.json`, `null` when it
 * cannot be determined (no manifest, not JSON, no string version).
 * @returns {string | null}
 */
export function installedAkmonVersion() {
  try {
    const manifest = JSON.parse(fs.readFileSync(posix.join(TREE_ROOT, "package.json"), "utf-8"));
    return _isPlainTable(manifest) && typeof manifest.version === "string" ? manifest.version : null;
  } catch (error) {
    if (error instanceof SyntaxError || isOSError(error)) {
      return null;
    }
    throw error;
  }
}

/**
 * Package-mode `.akmon.toml` stamping (ADR 0009 §4). The installed package version *is* the pin, so
 * sync keeps `akmon_version` in sync with reality on every run. Only the `mount`/`akmon_version` keys
 * are touched; every other field is preserved verbatim (see {@link upsertTomlKey}). `null` outside
 * package mode, when the record does not exist yet (`init` creates it), or when the installed
 * version cannot be determined.
 *
 * **Stamping the pin is not a realign**, and this function must not be read as one. It moves the
 * recorded pin while `last_realign` and the model-routing binding stay where the last completed
 * realign left them.
 * @param {string} root
 * @returns {PlannedFile | null}
 */
export function packageModeAkmonToml(root) {
  if (!isPackageMode(root)) {
    return null;
  }
  const version = installedAkmonVersion();
  if (version === null) {
    return null;
  }
  const path = pyPath(aitnaRoot(root), ".akmon.toml");
  if (!isFile(path)) {
    return null;
  }
  const text = upsertTomlKey(upsertTomlKey(_readText(path), "mount", _PACKAGE_MODE), "akmon_version", version);
  return new PlannedFile(path, text);
}

/**
 * The exact text `.codex/hooks.json` is generated with: one spelling for both readers — the plan
 * below writes it, and `verify`'s host-trust check compares the file against it before parsing
 * anything.
 * @param {SyncData} data
 * @param {string} root
 * @returns {string}
 */
export function codexHooksText(data, root) {
  return wiringForm(codexHooks(data, root));
}

/**
 * The generated files, in plan order (`sync.json`, `planned_files`), and the errors found planning.
 * @param {SyncData} data
 * @param {string} root
 * @returns {[PlannedFile[], string[]]}
 */
export function plannedFiles(data, root) {
  /** @type {string[]} */
  const errors = [];
  /** @type {Record<string, (data: SyncData, root: string) => string>} */
  const generators = {
    claude_md: _claudeMd,
    copilot_md: _copilotMd,
    gemini_md: _geminiMd,
    codex_readme: _codexReadme,
    codex_hooks_text: codexHooksText,
  };
  /** @type {PlannedFile[]} */
  const files = data.sync.planned_files.map(
    ([relative, name]) => new PlannedFile(pyPath(root, relative), generators[name](data, root)),
  );
  try {
    files.push(claudeSettings(data, root));
  } catch (error) {
    // UnicodeDecodeError and the unsupported-integer refusal are ValueErrors too.
    if (!(error instanceof Error) || !["ValueError", "UnicodeDecodeError"].includes(error.name)) {
      throw error;
    }
    errors.push(error.message);
  }
  const [sources, skillErrors] = skillSources(data, root);
  errors.push(...skillErrors);
  for (const source of sources) {
    files.push(...skillStubs(data, root, source));
  }
  const [materialized, materializationErrors] = materializedFiles(data, root);
  files.push(...materialized);
  errors.push(...materializationErrors);
  const tomlPlan = packageModeAkmonToml(root);
  if (tomlPlan !== null) {
    files.push(tomlPlan);
  }
  return [files, errors];
}

// --------------------------------------------------------------------------------------
// Applying the plan
// --------------------------------------------------------------------------------------

const _BYTECODE_CACHE_DIR = "__pycache__";

/**
 * `<AITNA_ROOT>/.akmon` — the one directory this tool owns outright.
 * @param {string} root
 * @returns {string}
 */
export function materializationRoot(root) {
  return pyPath(aitnaRoot(root), ".akmon");
}

/**
 * The entries of `directory` the way a walk sees them: names, `[]` for a directory that cannot be
 * listed (`Path.glob` skips what it may not read).
 * @param {string} directory
 * @returns {string[]}
 */
function _names(directory) {
  try {
    return fs.readdirSync(directory);
  } catch (error) {
    if (isOSError(error)) {
      return [];
    }
    throw error;
  }
}

/**
 * Every path below `directory`, files, directories and links alike, descending only into real
 * directories (`Path.rglob("*")`: a link to a directory is listed and not entered).
 * @param {string} directory
 * @returns {{paths: string[], directories: string[]}} the entries, and the directories that were walked (`directory` first)
 */
function _walk(directory) {
  /** @type {string[]} */
  const paths = [];
  /** @type {string[]} */
  const directories = [];
  /** @param {string} current */
  const visit = (current) => {
    directories.push(current);
    for (const name of _names(current)) {
      const child = pyPath(current, name);
      paths.push(child);
      let entry;
      try {
        entry = fs.lstatSync(child);
      } catch (error) {
        if (isOSError(error)) {
          continue;
        }
        throw error;
      }
      if (entry.isDirectory()) {
        visit(child);
      }
    }
  };
  visit(directory);
  return { paths, directories };
}

/**
 * Generated files present on disk that the current plan no longer wants.
 *
 * Two kinds of directory, two recognition rules, and the difference is deliberate. Under
 * `.claude/skills/` and `.agents/skills/` the project keeps its **own** skills beside ours, so only a
 * file carrying the generated banner is ours to delete. Under `<AITNA_ROOT>/.akmon/` nobody writes
 * but us, so everything unplanned is stale **whether or not it carries a banner** — which is
 * load-bearing rather than tidy: the materialized routing registry never carried one (it has to stay
 * parseable JSON), so a banner-only sweep would leave exactly that file behind forever.
 * @param {SyncData} data
 * @param {string} root
 * @param {PlannedFile[]} files
 * @returns {string[]}
 */
export function obsoleteGeneratedFiles(data, root, files) {
  const plannedPaths = new Set(files.map((planned) => planned.path));
  /** @type {string[]} */
  const obsolete = [];
  for (const skillsDir of data.sync.skill_stub_dirs) {
    for (const path of _globSkills(pyPath(root, skillsDir))) {
      if (plannedPaths.has(path)) {
        continue;
      }
      if (_readText(path).includes(generatedMarker(data.materialization))) {
        obsolete.push(path);
      }
    }
  }
  const materialization = materializationRoot(root);
  if (isDir(materialization)) {
    for (const path of _walk(materialization).paths.sort(_comparePaths)) {
      if (isDir(path) || plannedPaths.has(path)) {
        continue;
      }
      if (path.split("/").includes(_BYTECODE_CACHE_DIR)) {
        continue; // swept separately and silently — see sweepMaterializationBytecode
      }
      obsolete.push(path);
    }
  }
  return obsolete;
}

/**
 * Delete `__pycache__` under the materialization — silently, and before the deletions.
 *
 * Any project that has ever *run* a materialized hook has bytecode beside it. Deleting the source
 * files leaves that cache untouched, so the directories survive the migration and the tree stays in
 * the repository, unread and uncomplained-about. Silent because `sync --check` must not fail a
 * project for having executed a hook since the last sync — that is not drift. Before the deletion
 * loop because only then do the parent directories actually empty and get pruned.
 * @param {string} root
 */
export function sweepMaterializationBytecode(root) {
  const materialization = materializationRoot(root);
  if (!isDir(materialization)) {
    return;
  }
  const caches = _walk(materialization)
    .directories.map((directory) => pyPath(directory, _BYTECODE_CACHE_DIR))
    .filter(_exists)
    .sort(_comparePaths)
    .reverse();
  for (const cache of caches) {
    if (!isDir(cache)) {
      continue;
    }
    for (const name of codePointSort(_names(cache))) {
      const entry = pyPath(cache, name);
      if (isFile(entry) && [".pyc", ".pyo"].includes(_suffix(name))) {
        fs.unlinkSync(entry);
      }
    }
    try {
      fs.rmdirSync(cache);
    } catch (error) {
      if (!isOSError(error)) {
        throw error;
      }
    }
  }
}

/**
 * How far up to prune emptied directories after deleting `path`: `<AITNA_ROOT>` for the
 * materialization, so `.akmon` itself disappears once its last file is gone; the skills directory the
 * stub sat in otherwise.
 * @param {SyncData} data
 * @param {string} root
 * @param {string} path
 * @returns {string}
 */
function _pruneStop(data, root, path) {
  if (_isParentOf(materializationRoot(root), path)) {
    return aitnaRoot(root);
  }
  const skillsDir = data.sync.skill_stub_dirs.find((candidate) => _isParentOf(pyPath(root, candidate), path));
  return skillsDir === undefined ? pyPath(root, ".claude", "skills") : pyPath(root, skillsDir);
}

/**
 * Remove the empty directories above `path`, up to but not including `stop`.
 * @param {string} path
 * @param {string} stop
 */
function _removeEmptyParents(path, stop) {
  let current = posix.dirname(path);
  while (current !== stop && isDir(current)) {
    try {
      fs.rmdirSync(current);
    } catch (error) {
      if (isOSError(error)) {
        return;
      }
      throw error;
    }
    current = posix.dirname(current);
  }
}

/**
 * Apply a plan: write what differs (unless this is a check or a dry run), and, with `root`, delete
 * the generated files the plan no longer wants.
 * @param {SyncData} data
 * @param {PlannedFile[]} files
 * @param {{write: boolean, root?: string | null}} options
 * @returns {Result}
 */
export function apply(data, files, { write, root = null }) {
  const result = new Result([], [], [], []);
  for (const planned of files) {
    const current = _exists(planned.path) ? _readText(planned.path) : null;
    if (current === planned.content) {
      result.ok.push(planned.path);
      continue;
    }
    result.changed.push(planned.path);
    if (write) {
      fs.mkdirSync(posix.dirname(planned.path), { recursive: true });
      writeText(planned.path, planned.content);
    }
  }
  if (root !== null) {
    if (write) {
      sweepMaterializationBytecode(root);
    }
    for (const path of obsoleteGeneratedFiles(data, root, files)) {
      result.deleted.push(path);
      if (write) {
        fs.unlinkSync(path);
        _removeEmptyParents(path, _pruneStop(data, root, path));
      }
    }
  }
  return result;
}

// --------------------------------------------------------------------------------------
// Reports
// --------------------------------------------------------------------------------------

/**
 * `--check`'s observations as the shared envelope (C51). Only the non-writing `--check` mode speaks
 * findings: `--dry-run` and a real write print an action log, because "updated this file" is a
 * record of what happened, not a diagnostic about the tree.
 * @param {SyncData} data
 * @param {Result} result
 * @param {{root: string}} options
 * @returns {Finding[]}
 */
export function checkFindings(data, result, { root }) {
  /** @type {Finding[]} */
  const findings = [];
  const texts = data.sync.check_findings;
  // One read of the envelope's vocabulary for the whole report, not one per finding.
  const record = data.findings;
  /** @param {string} key @param {string} value @returns {[string, string]} */
  const one = (key, value) => [fill(texts[key].message, { relative: value, error: value }), texts[key].fix];
  /** @type {Array<[string[], string, string, string]>} */
  const groups = [
    [result.changed, "stale", "error", "sync.stale-generated"],
    [result.deleted, "obsolete", "error", "sync.obsolete-generated"],
    [result.ok, "up_to_date", "ok", "sync.up-to-date"],
  ];
  for (const [paths, key, severity, code] of groups) {
    for (const path of paths) {
      const relative = _relativeTo(path, root);
      const [message, fix] = one(key, relative);
      findings.push(
        new Finding({ severity, code, message: lineSafe(message), target: lineSafe(relative), fix, data: record }),
      );
    }
  }
  for (const error of result.errors) {
    const [message, fix] = one("plan_error", error);
    findings.push(
      new Finding({
        severity: "error",
        code: "sync.plan-error",
        message: lineSafe(message),
        target: "",
        fix,
        data: record,
      }),
    );
  }
  return findings;
}

/**
 * The action log for the writing modes: `dry-run` and a real write. `--check` speaks findings
 * instead, see {@link checkFindings}.
 * @param {SyncData} data
 * @param {Result} result
 * @param {{root: string, mode: string}} options
 */
export function printSummary(data, result, { root, mode }) {
  const verbs = data.sync.summary_verbs;
  const variant = mode === "dry-run" ? "dry_run" : "write";
  for (const path of result.changed) {
    process.stdout.write(`${verbs.changed[variant]}: ${_relativeTo(path, root)}\n`);
  }
  for (const path of result.deleted) {
    process.stdout.write(`${verbs.deleted[variant]}: ${_relativeTo(path, root)}\n`);
  }
  for (const path of result.ok) {
    process.stdout.write(`${verbs.ok}: ${_relativeTo(path, root)}\n`);
  }
  for (const error of result.errors) {
    process.stderr.write(`${verbs.error}: ${error}\n`);
  }
  if (result.changed.length === 0 && result.deleted.length === 0 && result.errors.length === 0) {
    process.stdout.write(`${verbs.no_changes}\n`);
  }
}

// --------------------------------------------------------------------------------------
// The command
// --------------------------------------------------------------------------------------

/**
 * The refusal for a project this implementation does not serve, or `null` when the record says
 * `ecosystem = "node"`: a wrong-spelling write is worse than a refusal.
 * @param {SyncData} data
 * @param {string} root
 * @returns {string | null}
 */
export function unsupportedRecord(data, root) {
  const what = unsupportedFound(data, root);
  return what === null ? null : fill(data.sync.unsupported_record, { found: what });
}

/**
 * What the project has instead of a Node record — the `{{found}}` of every refusal text (`sync`'s,
 * `verify`'s, `init`'s and `update`'s) — or `null` when the record says `ecosystem = "node"`.
 *
 * Every command serves a Node record in every mode (the C129 amendment of ADR 0020 D02).
 * @param {SyncData} data
 * @param {string} root
 * @returns {string | null}
 */
export function unsupportedFound(data, root) {
  const found = data.sync.unsupported_found;
  if (!isFile(pyPath(aitnaRoot(root), ".akmon.toml"))) {
    return fill(found.no_record, { record: `${aitnaRootName()}/.akmon.toml` });
  }
  if (recordedEcosystem(root) !== _NODE_ECOSYSTEM) {
    return fill(found.ecosystem, { value: recordedEcosystem(root) });
  }
  return null;
}

/** What `-h` / `--help` prints (the Python has `argparse`'s own block; see the header). */
const USAGE = `usage: akmon sync [-h] [--project-root PROJECT_ROOT] [--check] [--dry-run]

Synchronize generated agent pointers for an akmon-consuming project.

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --check               Do not write; exit 1 when generated files are stale.
  --dry-run             Print changes without writing them.
`;

/**
 * Parse the arguments after `sync`.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, check: boolean, dryRun: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        check: { type: "boolean" },
        "dry-run": { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      check: values.check === true,
      dryRun: values["dry-run"] === true,
      help: values.help === true,
    };
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
 * Parse arguments, plan the generated files, and apply, check, or dry-run the plan.
 * @param {string[]} [argv] the arguments after `sync` (default: the process's)
 * @returns {number} The process exit code: 0, 1 when `--check` finds the tree stale, 2 when the
 *   files could not even be planned or the record is not a Node one.
 */
export function main(argv = process.argv.slice(2)) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`akmon sync: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }
  if (options.check && options.dryRun) {
    process.stderr.write("akmon sync: error: --check and --dry-run are mutually exclusive\n");
    return 2;
  }

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  const data = readSyncData();
  const refusal = unsupportedRecord(data, root);
  if (refusal !== null) {
    process.stderr.write(`${refusal}\n`);
    return 2;
  }
  const [files, errors] = plannedFiles(data, root);
  const write = !options.check && !options.dryRun;
  const result = apply(data, files, { write, root });
  result.errors.push(...errors);

  if (options.check) {
    printFindings(checkFindings(data, result, { root }));
  } else {
    printSummary(data, result, { root, mode: options.dryRun ? "dry-run" : "write" });
  }
  // `sync` keeps its own exit vocabulary rather than the envelope's `exitCode`, by owner decision at
  // C51: 2 separates "could not even plan the files" from 1's "the plan and the tree disagree", and no
  // `--strict` exists here because nothing in this stream warns.
  if (result.errors.length > 0) {
    return 2;
  }
  if (options.check && (result.changed.length > 0 || result.deleted.length > 0)) {
    return 1;
  }
  return 0;
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
