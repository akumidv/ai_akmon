#!/usr/bin/env node
/**
 * Validate an akmon-consuming project's USE contract — `akmon verify`. The JavaScript twin of
 * `bin/verify.py` (C105, ADR 0020 D01): the Python module is the spec, the same findings with the
 * same codes and texts, the same exit code, the same stdout and stderr.
 *
 * This is the USE-layer verifier: it checks the structural contract a *consuming* project must
 * satisfy — AGENTS.md, generated vendor pointers, hooks, skills, memory, the local `_aitna` layout,
 * and the USE-surface isolation rule. It does not modify files; run `akmon sync` for generated
 * pointer fixes.
 *
 *     akmon verify             every check, all findings
 *     akmon verify --strict    warnings fail too
 *     akmon verify --quiet     only warnings and errors
 *
 * This implementation serves Node package mode only (ADR 0020 D02), exactly as `sync` does: the
 * record says `mount = "package"` and `ecosystem = "node"`. Any other record (none, mounted, a
 * Python package attach) is refused with exit 2 and the `unsupported_record` text of
 * `bin/verify.json` — a report on a carrier this file does not read would be wrong, not partial.
 *
 * What is Node's own (ADR 0020 D05), each a finding with a `node` entry in `bin/verify.json`:
 * - `hooks.launcher`: the wiring runs `node "<anchor>/node_modules/akmon/js/hooks/<name>.mjs"`, so
 *   the check is that `<root>/node_modules/akmon/js/hooks` is a directory — with the two ways it
 *   fails named apart (Yarn Plug'n'Play installs no `node_modules`; a hoisted install sits in an
 *   ancestor directory that the committed wiring cannot reach);
 * - `package.dev-pin` reads `package.json` through `packagePinStatus`; the same
 *   finding is a warning when the `devDependencies` pin is not an exact version (no Python twin);
 * - `layout.standard-path` checks the `js/hooks/*.mjs` files the Node wiring runs
 *   (`node_wired_hook_scripts`).
 *
 * The Python's mounted-only checks are unreachable here and have no port: `gitignore.akmon-pycache`
 * (`check_akmon_gitignore`), `layout.vendored-leftover` (`check_vendored_leftovers`, a vendored
 * mount's members the carrier no longer ships, C117), `changelog.unreleased` (the mounted half of `check_changelog`; package
 * mode answers `changelog.package-mode`) and the mount-relative paths of `check_standard_path`
 * (the standard tree of a Node project is `<root>/node_modules/akmon`, `standardTreeRoot`).
 *
 * Data (the C102 convention): `main` builds a `Verifier`, which reads `bin/verify.json`, the sync
 * bundle and `common/findings.json` once and passes each down as the first parameter, `data`, of
 * every function that needs it; the always-loaded, Codex-hooks, runtime and check-runner tables are
 * read on first use, once per run.
 *
 * Twin notes (ADR 0020 D08, `meta/conformance/DIVERGENCES.md`):
 * - the arguments are parsed by `node:util` `parseArgs`: a usage error is the one line
 *   `akmon verify: error: …` on stderr and exit 2, `-h`/`--help` prints a short usage and exits 0;
 * - the Python's text patterns carry `re.ASCII` (the C103 twin rule), so these spell `\\d \\w \\s \\b`
 *   as ASCII classes: `[0-9]`, look-arounds over `[A-Za-z0-9_]`, `[ \\t\\n\\r\\f\\v]` (JS `\\s` is
 *   Unicode even without `u`), and `i` without `u` folds ASCII letters only, as `re.IGNORECASE | re.ASCII`;
 * - `Path.glob` over the isolation patterns (`skills/**\/*.md`): a literal segment must be a
 *   directory, `**` is the directory and every real subdirectory below it (a linked one is listed,
 *   not entered), the last segment matches any entry, hidden ones included; `sorted()` orders paths
 *   by their components, by code point;
 * - `shutil.which("codex")` is `_which`: each `PATH` entry in order (an empty one is the current
 *   directory), the first existing, executable non-directory;
 * - a TOML record value is `truthy` the way Python's is: a date or time is always true.
 */

import fs from "node:fs";
import { posix } from "node:path";
import { fileURLToPath } from "node:url";
import { TextDecoder, parseArgs } from "node:util";

import {
  apply,
  codexHooksText,
  packagePinStatus,
  plannedFiles,
  readJson,
  readSyncData,
  skillSources,
  standardTreeRoot,
  unsupportedFound,
} from "./sync.mjs";
import * as alwaysLoaded from "../common/always_loaded.mjs";
import {
  checkTableOk,
  configTarget,
  correctEntryFix,
  readChecks,
  repairRecordVerifyFix,
} from "../common/check_runner.mjs";
import * as codexHooks from "../common/codex_hooks.mjs";
import { fnmatchCase } from "../common/glob.mjs";
import { Finding, exitCode, lineSafe, printFindings, readFindingsData } from "../common/findings.mjs";
import { fill, read } from "../common/jsondata.mjs";
import { generatedMarker } from "../common/materialization.mjs";
import { aitnaRoot, aitnaRootName, resolveProjectRoot } from "../common/project_root.mjs";
import {
  isDir,
  isFile,
  isOSError,
  isDict,
  dictGet,
  pyContains,
  pyEq,
  pyError,
  pyLen,
  pyLower,
  pyPath,
  pyRepr,
  pySplit,
  pySplitlines,
  pyStat,
  pyStrip,
  readText,
  strRepr,
  truthy,
} from "../common/pyvalue.mjs";
import { RecordError, readAkmonToml, readAkmonTomlStrict } from "../common/record.mjs";
import { codexHooksListCommand } from "../common/runtime.mjs";
import { codePointCompare, codePointSort } from "../common/sort.mjs";
import { splitVersion } from "../common/versions.mjs";

/** @typedef {import("../common/check_runner.mjs").CheckRunnerData} CheckRunnerData */
/** @typedef {import("../common/findings.mjs").FindingsData} FindingsData */
/** @typedef {import("./sync.mjs").SyncData} SyncData */
/** @typedef {any} Json */
/** @typedef {import("../common/codex_hooks.mjs").HooksListRunner} Runner The Codex query's injectable seam. */

/**
 * The shape of `bin/verify.json`: the data file is the owner of these keys.
 * @typedef {object} VerifyData
 * @property {string[]} wired_hook_scripts
 * @property {string[]} node_wired_hook_scripts
 * @property {string[]} basic_layout_consumer_paths
 * @property {string[]} basic_layout_standard_paths
 * @property {Record<string, Record<string, string>>} agents_anchors
 * @property {Record<string, [string, string | null]>} vendor_pointers
 * @property {string[]} use_operative_globs
 * @property {string[]} use_operative_files
 * @property {string[]} dev_path_tokens
 * @property {string[]} skill_required_frontmatter
 * @property {number} skill_name_max
 * @property {number} skill_description_max
 * @property {string[]} routing_shipped_paths
 * @property {string[]} routing_vendors
 * @property {string[]} routing_semantic_fallback_keys
 * @property {string[]} routing_second_opinion_keys
 * @property {string[]} routing_retired_second_opinion_keys
 * @property {string[]} reasoner_policy_values
 * @property {{env_secret: string, env_example_keep: string, pycache: string}} gitignore_patterns
 * @property {Record<string, string[]>} ci_required_commands
 * @property {string[]} record_required_keys
 * @property {string[]} task_statuses
 * @property {number} tasks_max_lines
 * @property {string} changelog_package_mode
 * @property {string} changelog_package_mode_fix
 * @property {string} unsupported_record
 * @property {Record<string, any>} node the Node-only texts
 */

/** The tree this module executes from, links dereferenced: `<tree>/js/bin/verify.mjs` → `<tree>`. */
const TREE_ROOT = fs.realpathSync(posix.resolve(posix.dirname(fileURLToPath(import.meta.url)), "..", ".."));

// The Python module's patterns under `re.ASCII` (see the header).
const _WORD = "A-Za-z0-9_";
const _SPACE = " \\t\\n\\r\\f\\v";
const _DATE_RE = new RegExp(`(?<![${_WORD}])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![${_WORD}])`);
// A backlog entry's `·`-separated fields (pipelines/tasks.md): id, title, status, goal, detail.
// Reading the status field needs at least the first three.
const _MIN_STATUS_FIELDS = 3;
const _DELEGATION_DEFAULT_RE = new RegExp(
  `(?<![${_WORD}])delegation[${_SPACE}]+is[${_SPACE}]+the[${_SPACE}]+default(?![${_WORD}])`,
  "i",
);
const _SKILL_NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const _NUMBERED_DR_RE = new RegExp(`(?<![${_WORD}])ADR[${_SPACE}-]?[0-9]{2,4}(?![${_WORD}])`, "g");
const _ROADMAP_CITE_RE = new RegExp(`(?<![${_WORD}])ROADMAP(?:\\.md|[${_SPACE}]+O[0-9]+)`, "g");
const _DEV_NAME_RE = new RegExp(`(?<![${_WORD}])self_ci(?![${_WORD}])|(?<![${_WORD}])CONCEPT\\.md(?![${_WORD}])`, "g");
const _LINK_RE = /\]\(([^)]+)\)/gu;
const _INLINE_CODE_RE = /`([^`]+)`/gu;
const _LEGACY_OWNER_ANCHOR_RE = new RegExp(`\\*\\*D2\\*\\*[${_SPACE}]+—[${_SPACE}]+the owner[${_SPACE}]+verifies`);
/** The text patterns, exported for the twin test that pins their ASCII meaning against the Python's. */
export const TEXT_PATTERNS = {
  date: _DATE_RE,
  delegationDefault: _DELEGATION_DEFAULT_RE,
  numberedDr: _NUMBERED_DR_RE,
  roadmapCite: _ROADMAP_CITE_RE,
  devName: _DEV_NAME_RE,
  legacyOwnerAnchor: _LEGACY_OWNER_ANCHOR_RE,
};
/** An exact semver release: `MAJOR.MINOR.PATCH`, an optional pre-release and build part. */
const _SEMVER = String.raw`[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?`;
const _EXACT_VERSION_RE = new RegExp(`^=?${_SEMVER}$`);
/**
 * A git dependency at an exact release tag, as npm, pnpm and yarn write one: a hosted shorthand
 * (`github:`, `gitlab:`, `bitbucket:`, or bare `<owner>/<repo>`) or a `git`, `git+http(s)` or
 * `git+ssh` URL, whose `#` fragment is `v`? and an exact version. A branch, a `#semver:` range, a
 * commit, no fragment, or a plain http(s) tarball URL stays a non-exact pin.
 */
const _GIT_TAG_PIN_RE = new RegExp(
  String.raw`^(?:(?:github|gitlab|bitbucket):[^\s#]+|[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+` +
    String.raw`|git(?:\+(?:https?|ssh))?://[^\s#]+)#v?${_SEMVER}$`,
);

/** The standard files the Node project's wiring runs, relative to the standard tree. */
const _NODE_HOOKS_DIR = "js/hooks";
/** Where the wiring finds akmon, relative to the project root. */
const _NODE_LAUNCHER_DIR = "node_modules/akmon/js/hooks";

/**
 * The shared verify text and tables (`verify.json`, beside the Python launcher).
 *
 * Read once by the {@link Verifier} and passed down: never at import time, with no module-level
 * cache and no swallowed `DataFileError` (C102).
 * @returns {VerifyData}
 */
export function readVerifyData() {
  return /** @type {VerifyData} */ (read(posix.join(TREE_ROOT, "bin", "verify.json")));
}

/**
 * Name the offenders, not just their count — a finding a reader cannot locate is half a finding.
 * @param {string[]} ids
 * @param {number} [limit]
 * @returns {string}
 */
function _sample(ids, limit = 4) {
  const shown = ids.slice(0, limit).join(", ");
  return ids.length <= limit ? shown : `${shown}, +${ids.length - limit} more`;
}

/**
 * `text.strip(chars)`: the characters of `chars` cut from both ends.
 * @param {string} text
 * @param {string} chars
 * @returns {string}
 */
function _stripChars(text, chars) {
  let start = 0;
  let end = text.length;
  while (start < end && chars.includes(text[start])) {
    start += 1;
  }
  while (end > start && chars.includes(text[end - 1])) {
    end -= 1;
  }
  return text.slice(start, end);
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
 * `sorted()` over paths: component by component, by code point — not the joined string. A path
 * that is a prefix of another comes first.
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

/**
 * The entries of `directory`, `[]` for one that cannot be listed (`Path.glob` skips what it may not read).
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
 * `directory` and every real directory below it (`**` of `Path.glob`: a link to a directory is not entered).
 * @param {string} directory
 * @returns {string[]}
 */
function _recursiveDirs(directory) {
  /** @type {string[]} */
  const found = [directory];
  for (const name of _names(directory)) {
    const child = pyPath(directory, name);
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
      found.push(..._recursiveDirs(child));
    }
  }
  return found;
}

/**
 * `base.glob(pattern)` for the patterns of `use_operative_globs`: literal and wildcard segments and
 * `**`. A segment before the last must be a directory; the last matches any entry.
 * @param {string} base
 * @param {string} pattern
 * @returns {string[]}
 */
function _glob(base, pattern) {
  const parts = pattern.split("/");
  let current = [base];
  parts.forEach((part, index) => {
    const last = index === parts.length - 1;
    if (part === "**") {
      current = current.flatMap(_recursiveDirs);
    } else if (!/[*?[]/.test(part)) {
      current = current
        .map((directory) => pyPath(directory, part))
        .filter((path) => (last ? pyStat(path) !== null : isDir(path)));
    } else {
      current = current.flatMap((directory) =>
        _names(directory)
          .filter((name) => fnmatchCase(name, part))
          .map((name) => pyPath(directory, name))
          .filter((path) => last || isDir(path)),
      );
    }
  });
  return [...new Set(current)];
}

/**
 * `shutil.which(command)`: the first `PATH` entry holding an executable non-directory of that name.
 * @param {string} command
 * @returns {string | null}
 */
function _which(command) {
  const path = process.env.PATH;
  if (path === undefined || path === "") {
    return null;
  }
  const usable = (/** @type {string} */ candidate) => {
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
    } catch {
      return false;
    }
    return !isDir(candidate);
  };
  if (command.includes("/")) {
    return usable(command) ? command : null;
  }
  for (const directory of path.split(":")) {
    const candidate = directory === "" ? command : `${directory.endsWith("/") ? directory : `${directory}/`}${command}`;
    if (usable(candidate)) {
      return candidate;
    }
  }
  return null;
}

/**
 * A parsed JSON document with its objects as plain objects (the model `pyvalue` reads), from the
 * ordered `Map`s `readJson` builds.
 * @param {Json} value
 * @returns {Json}
 */
function _plain(value) {
  if (value instanceof Map) {
    /** @type {Record<string, Json>} */
    const table = {};
    for (const [key, item] of value) {
      Object.defineProperty(table, key, { value: _plain(item), writable: true, enumerable: true, configurable: true });
    }
    return table;
  }
  return Array.isArray(value) ? value.map(_plain) : value;
}

/**
 * Python truthiness of a value read from the TOML record: a date or time object is always true,
 * which `pyvalue.truthy` (JSON values) does not say.
 * @param {unknown} value
 * @returns {boolean}
 */
function _recordTruthy(value) {
  if (value instanceof Date) {
    return true;
  }
  if (typeof value === "bigint") {
    return value !== 0n;
  }
  return truthy(value);
}

/**
 * The `devDependencies.akmon` value of `package.json`, or `undefined` when none can be read.
 * @param {string} root
 * @returns {unknown}
 */
function _devPinValue(root) {
  try {
    const document = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(fs.readFileSync(pyPath(root, "package.json"))),
    );
    const dev = document?.devDependencies;
    return dev !== null && typeof dev === "object" && Object.hasOwn(dev, "akmon") ? dev.akmon : undefined;
  } catch {
    return undefined;
  }
}

/**
 * The pin as a finding names it: a string as Python's `repr`, anything else (or nothing) as its JSON form.
 * @param {unknown} value
 * @returns {string}
 */
function _pinSpelling(value) {
  return typeof value === "string" ? strRepr(value) : JSON.stringify(value);
}

/**
 * A skill's frontmatter as `key → value` (a nested key is `parent.child`), in file order.
 * @typedef {Map<string, string>} Frontmatter
 */

/** Runs every USE-contract check against one consuming project and collects findings. */
export class Verifier {
  /**
   * @param {string} root the project root
   * @param {{codexHooksRunner?: Runner}} [options] `codexHooksRunner`
   *   is the injectable seam of the host-trust query (a carrier passes a fake instead of spawning a
   *   real `codex app-server`)
   */
  constructor(root, { codexHooksRunner } = {}) {
    this.root = root;
    /** @type {Finding[]} */
    this.findings = [];
    // The dev-layer root is configurable (AITNA_ROOT, default _aitna); akmon sits in the project's
    // `node_modules`. Every path below derives from these so a relocated layer still verifies.
    this.aitna = aitnaRootName();
    this.akmon = `${this.aitna}/akmon`;
    // The standard tree this project operates against: `<root>/node_modules/akmon`, spelled
    // unresolved — may live outside the root entirely when this tree is not the installed one.
    this.standardRoot = standardTreeRoot(root);
    this._codexHooksRunner = codexHooksRunner;
    /** @type {VerifyData} */
    this.data = readVerifyData();
    /** @type {SyncData} */
    this.syncData = readSyncData();
    /** @type {FindingsData} */
    this.findingsData = readFindingsData();
    /** @type {Record<string, any>} */
    this._lazy = {};
  }

  /**
   * A shared data table other than the three above, read on first use and kept.
   * @param {string} name
   * @param {() => any} reader
   * @returns {any}
   */
  _table(name, reader) {
    this._lazy[name] ??= reader();
    return this._lazy[name];
  }

  /** `common/always_loaded.json`, via its twin. */
  get alwaysLoadedData() {
    return this._table("always", alwaysLoaded.readAlwaysLoadedData);
  }

  /** `common/codex_hooks.json`, via its twin. */
  get codexHooksData() {
    return this._table("codex", codexHooks.readCodexHooksData);
  }

  /** `common/runtime.json`. */
  get runtimeData() {
    return this._table("runtime", () => read(posix.join(TREE_ROOT, "common", "runtime.json")));
  }

  /** `common/check_runner.json`. */
  get checkData() {
    return this._table(
      "check",
      () => /** @type {CheckRunnerData} */ (read(posix.join(TREE_ROOT, "common", "check_runner.json"))),
    );
  }

  /**
   * @param {string} severity
   * @param {string} code
   * @param {string} message
   * @param {string} target
   * @param {string} fix
   */
  _record(severity, code, message, target, fix) {
    this.findings.push(
      new Finding({
        severity,
        code,
        message: lineSafe(message),
        target: lineSafe(target),
        fix: lineSafe(fix),
        data: this.findingsData,
      }),
    );
  }

  /**
   * Record a passing finding.
   * @param {string} code
   * @param {string} message
   * @param {{target?: string, fix: string}} fields
   */
  ok(code, message, { target = "", fix }) {
    this._record("ok", code, message, target, fix);
  }

  /**
   * Record a warning finding.
   * @param {string} code
   * @param {string} message
   * @param {{target?: string, fix: string}} fields
   */
  warn(code, message, { target = "", fix }) {
    this._record("warn", code, message, target, fix);
  }

  /**
   * Record a failing finding.
   * @param {string} code
   * @param {string} message
   * @param {{target?: string, fix: string}} fields
   */
  error(code, message, { target = "", fix }) {
    this._record("error", code, message, target, fix);
  }

  /**
   * Check that a path in the consumer's own tree exists; record and return the result.
   * @param {string} relative
   * @param {"file" | "dir"} [kind]
   * @returns {boolean}
   */
  checkPath(relative, kind = "file") {
    const path = pyPath(this.root, relative);
    const exists = kind === "dir" ? isDir(path) : isFile(path);
    if (exists) {
      this.ok("layout.consumer-path", `${relative} exists`, { target: relative, fix: `Keep ${relative} in place.` });
      return true;
    }
    this.error("layout.consumer-path", `${relative} is missing`, { target: relative, fix: `Create ${relative}.` });
    return false;
  }

  /**
   * `path` rendered as the Python renders it for an embedded tree: a path inside the standard
   * tree reads `standard tree:`-prefixed and relative to it (the shared findings then agree
   * across implementations — `node_modules/akmon` is where the Node tree lives, not what a
   * finding names), any other path relative to the consumer root.
   * @param {string} path
   * @returns {string}
   */
  displayPath(path) {
    try {
      return `standard tree:${_relativeTo(path, this.standardRoot)}`;
    } catch (error) {
      if (!(error instanceof Error) || error.name !== "ValueError") {
        throw error;
      }
      return _relativeTo(path, this.root);
    }
  }

  /**
   * Like {@link checkPath}, resolved against the standard tree instead of the root: content that
   * ships with the standard itself rather than being generated into the consumer repo.
   * @param {string} relative
   * @param {"file" | "dir"} [kind]
   * @returns {boolean}
   */
  checkStandardPath(relative, kind = "file") {
    const path = pyPath(this.standardRoot, relative);
    const exists = kind === "dir" ? isDir(path) : isFile(path);
    const display = this.displayPath(path);
    if (exists) {
      this.ok("layout.standard-path", `${display} exists`, {
        target: display,
        fix: `Keep ${display} in the standard tree.`,
      });
      return true;
    }
    this.error("layout.standard-path", `${display} is missing`, {
      target: display,
      fix: `Restore ${display} by re-attaching or updating the akmon standard tree.`,
    });
    return false;
  }

  /** Check that the consumer's and the standard's required files and directories exist. */
  checkBasicLayout() {
    const data = this.data;
    for (const item of data.basic_layout_consumer_paths) {
      this.checkPath(fill(item, { aitna: this.aitna }));
    }
    for (const relative of data.basic_layout_standard_paths) {
      this.checkStandardPath(relative);
    }
    for (const relative of [`${this.aitna}/agents`, `${this.aitna}/memory`]) {
      this.checkPath(relative, "dir");
    }
  }

  /**
   * The operative USE surface must not name akmon's own development artifacts: a numbered
   * decision-record citation, and any link/inline-code path into the dev tree or its artifacts.
   * Generic process vocabulary ("file an ADR") stays allowed.
   */
  checkUseSurfaceIsolation() {
    const akmon = this.standardRoot;
    if (!isDir(akmon)) {
      return;
    }
    /** @type {string[]} */
    const sources = [];
    for (const pattern of this.data.use_operative_globs) {
      sources.push(..._glob(akmon, pattern).sort(_comparePaths));
    }
    for (const name of this.data.use_operative_files) {
      const candidate = pyPath(akmon, name);
      if (isFile(candidate)) {
        sources.push(candidate);
      }
    }
    /** @type {string[]} */
    const violations = [];
    for (const source of [...new Set(sources)].sort(_comparePaths)) {
      violations.push(...this._isolationViolations(source));
    }
    if (violations.length > 0) {
      this.error(
        "isolation.use-surface",
        "USE surface names akmon development artifacts (keep it self-contained so a " +
          `consumer never reads the dev tree): ${violations.join("; ")}`,
        { fix: "Remove the listed development-tree citations and paths from the USE surface." },
      );
    } else {
      this.ok("isolation.use-surface", "USE surface names no akmon development artifacts", {
        fix: "Keep decision-record citations and dev-tree paths out of the USE surface.",
      });
    }
  }

  /**
   * @param {string} source
   * @returns {string[]}
   */
  _isolationViolations(source) {
    const text = readText(source);
    const relative = this.displayPath(source);
    /** @type {string[]} */
    const found = [];
    for (const citation of [_NUMBERED_DR_RE, _ROADMAP_CITE_RE]) {
      for (const match of text.matchAll(citation)) {
        found.push(`${relative} → cites ${match[0]}`);
      }
    }
    for (const match of text.matchAll(_DEV_NAME_RE)) {
      found.push(`${relative} → names ${match[0]}`);
    }
    const spans = [...text.matchAll(_LINK_RE), ...text.matchAll(_INLINE_CODE_RE)].map((match) => match[1]);
    for (const span of spans) {
      const path = pyStrip(span) !== "" ? pySplit(span)[0].split("#")[0] : "";
      if (this.data.dev_path_tokens.some((token) => path.includes(token))) {
        found.push(`${relative} → path ${span}`);
      }
    }
    return found;
  }

  /** AGENTS.md is hand-owned and its akmon block carries every required anchor. */
  checkAgentsMd() {
    const path = pyPath(this.root, "AGENTS.md");
    if (!isFile(path)) {
      return;
    }
    const text = readText(path);
    if (text.includes(generatedMarker(this.syncData.materialization))) {
      this.error(
        "agents.generated-source",
        "AGENTS.md must be a hand-reviewed source document, not generated by sync.py",
        {
          target: "AGENTS.md",
          fix: "Remove the generated banner and hand-own AGENTS.md.",
        },
      );
    }
    // Node is package mode by construction (the refusal in `main`): the package table applies. The
    // block heading is filled from its single owner (`common/always_loaded`), not from a copy here.
    const variant = "package";
    const heading = alwaysLoaded.blockHeading(this.alwaysLoadedData);
    const required = Object.entries(this.data.agents_anchors[variant]).map(
      ([name, snippet]) =>
        /** @type {[string, string]} */ ([name, fill(snippet, { aitna: this.aitna, akmon: this.akmon, heading })]),
    );
    const missing = required.filter(([, snippet]) => !text.includes(snippet)).map(([name]) => name);
    // C94 migrates the source contract, but consumer AGENTS.md blocks are hand-owned and explicitly
    // outside that cutover: the former exact anchor is accepted until consumer migration has a task.
    if (!text.includes("owner verifies") && !_LEGACY_OWNER_ANCHOR_RE.test(text)) {
      missing.push("owner verifies directive");
    }
    if (!_DELEGATION_DEFAULT_RE.test(text)) {
      missing.push("direct delegation-default rule");
    }
    if (missing.length > 0) {
      this.error("agents.block-anchors", `AGENTS.md akmon block is missing: ${missing.join(", ")}`, {
        target: "AGENTS.md",
        fix: "Add the listed anchors to the akmon block in AGENTS.md.",
      });
    } else {
      this.ok("agents.block-anchors", "AGENTS.md akmon block contains required anchors", {
        target: "AGENTS.md",
        fix: "Keep every required anchor in the AGENTS.md akmon block.",
      });
    }
  }

  /** Validate the source-to-pointer contract without generating AGENTS.md. */
  checkCrossAgentContract() {
    const agentsMd = pyPath(this.root, "AGENTS.md");
    if (!isFile(agentsMd)) {
      return;
    }
    const agentsText = readText(agentsMd);
    this._checkVendorPointers();
    if (agentsText.includes(".claude/skills") || agentsText.includes(".agents/skills")) {
      this.warn(
        "agents.skill-stub-link",
        "AGENTS.md should not point to generated .claude/skills or .agents/skills stubs; link source skill roots instead",
        { target: "AGENTS.md", fix: "Replace the generated stub path in AGENTS.md with the source skill root." },
      );
    }
    this._checkSkillRoots(agentsText);
    this._checkAlwaysLoaded(agentsText);
  }

  /**
   * ADR 0012 F18, consumer-total scope: warn over the cap, report the measurement every run. The
   * consumer owns most of this population, so the finding stays `warn`; `--strict` turns it into a
   * non-zero exit through the shared exit policy, not by changing severity.
   * @param {string} agentsText
   */
  _checkAlwaysLoaded(agentsText) {
    const data = this.alwaysLoadedData;
    const found = alwaysLoaded.populations(data, agentsText, this.root);
    if (found === null) {
      return; // no marked akmon block: checkAgentsMd already reports the missing anchor
    }
    const scope = alwaysLoaded.consumer(data);
    const population = found[scope];
    const cap = alwaysLoaded.caps(data)[scope];
    const message = alwaysLoaded.report(population, cap);
    if (alwaysLoaded.over(population, cap)) {
      this.warn("caps.always-loaded", message, {
        target: "AGENTS.md",
        fix: "Move on-demand material out of AGENTS.md and its imported guardrails, or link it instead",
      });
    } else {
      this.ok("caps.always-loaded", message, {
        target: "AGENTS.md",
        fix: "Keep AGENTS.md and the guardrails it imports within the always-loaded cap",
      });
    }
  }

  /** Every vendor pointer file must import its guardrail and link back to AGENTS.md. */
  _checkVendorPointers() {
    const vendorPointers = Object.entries(this.data.vendor_pointers);
    /** @type {string[]} */
    const missingAgentsLinks = [];
    let presentPointers = 0;
    for (const [relative, [agentsAnchor, requiredImport]] of vendorPointers) {
      const path = pyPath(this.root, relative);
      if (!isFile(path)) {
        continue; // checkGeneratedPointers reports stale/missing generated files.
      }
      presentPointers += 1;
      const text = readText(path);
      if (!text.includes(agentsAnchor)) {
        missingAgentsLinks.push(relative);
      }
      if (requiredImport && !text.includes(requiredImport)) {
        this.error(
          "pointers.vendor-import",
          `${relative} must import ${requiredImport}; a prose pointer is not enough`,
          {
            target: relative,
            fix: `Re-run akmon sync so ${relative} imports ${requiredImport}.`,
          },
        );
      }
    }
    if (missingAgentsLinks.length > 0) {
      this.error(
        "pointers.vendor-agents-link",
        `vendor pointer(s) do not point at AGENTS.md: ${missingAgentsLinks.join(", ")}`,
        {
          fix: "Re-run akmon sync so every vendor pointer points at AGENTS.md.",
        },
      );
    } else if (presentPointers === vendorPointers.length) {
      this.ok("pointers.vendor-agents-link", "vendor pointers point at AGENTS.md", {
        fix: "Keep every vendor pointer aimed at AGENTS.md.",
      });
    }
  }

  /**
   * When skills exist, AGENTS.md must name their source roots (not a generated stub).
   * @param {string} agentsText
   */
  _checkSkillRoots(agentsText) {
    const [skillSourceList] = skillSources(this.syncData, this.root);
    if (skillSourceList.length === 0) {
      return;
    }
    const skillRoots = ["skills/", `${this.aitna}/skills`, `${this.akmon}/skills`];
    if (skillRoots.some((hint) => agentsText.includes(hint))) {
      this.ok("agents.skill-roots", "AGENTS.md references source skill roots", {
        target: "AGENTS.md",
        fix: "Keep the source skill roots named in AGENTS.md.",
      });
    } else {
      this.warn("agents.skill-roots", "skills exist, but AGENTS.md does not mention source skill roots", {
        target: "AGENTS.md",
        fix: "Name the source skill roots in AGENTS.md so agents find the skills.",
      });
    }
  }

  /** Each agent directory has a README.md charter linking a akmon role. */
  checkAgentCharters() {
    const agentsDir = pyPath(this.root, this.aitna, "agents");
    if (!isDir(agentsDir)) {
      return;
    }
    const agents = codePointSort(_names(agentsDir)).filter((name) => isDir(pyPath(agentsDir, name)));
    if (agents.length === 0) {
      this.warn("charters.present", `${this.aitna}/agents has no agent charters`, {
        target: `${this.aitna}/agents`,
        fix: `Add one directory per agent under ${this.aitna}/agents, each with a README.md charter.`,
      });
      return;
    }
    for (const agent of agents) {
      const readme = pyPath(agentsDir, agent, "README.md");
      const relative = _relativeTo(readme, this.root);
      if (!isFile(readme)) {
        this.error("charters.readme", `${relative} is missing`, {
          target: relative,
          fix: `Create ${relative} linking the akmon role this agent follows.`,
        });
        continue;
      }
      const text = readText(readme);
      if (text.includes(`${this.akmon}/roles`) || text.includes("akmon/roles")) {
        this.ok("charters.role-link", `${relative} links a akmon role`, {
          target: relative,
          fix: "Keep the akmon role link in this charter.",
        });
      } else {
        this.warn("charters.role-link", `${relative} does not link a akmon role`, {
          target: relative,
          fix: `Link the akmon role this agent follows from ${relative}.`,
        });
      }
    }
  }

  /** The memory directory has an index and the index lists every memory file. */
  checkMemory() {
    const memoryDir = pyPath(this.root, this.aitna, "memory");
    if (!isDir(memoryDir)) {
      return;
    }
    const index = pyPath(memoryDir, "README.md");
    const legacyIndex = pyPath(memoryDir, "MEMORY.md");
    let indexText;
    if (isFile(index)) {
      indexText = readText(index);
      this.ok("memory.index", `${this.aitna}/memory/README.md exists`, {
        target: `${this.aitna}/memory/README.md`,
        fix: "Keep README.md as the memory index.",
      });
    } else if (isFile(legacyIndex)) {
      indexText = readText(legacyIndex);
      this.warn("memory.index", `${this.aitna}/memory/MEMORY.md exists; README.md is the preferred index`, {
        target: `${this.aitna}/memory/MEMORY.md`,
        fix: `Rename ${this.aitna}/memory/MEMORY.md to README.md.`,
      });
    } else {
      this.error("memory.index", `${this.aitna}/memory needs README.md index`, {
        target: `${this.aitna}/memory`,
        fix: `Add a README.md index under ${this.aitna}/memory.`,
      });
      return;
    }
    const missingFromIndex = [];
    for (const name of codePointSort(_names(memoryDir).filter((entry) => entry.endsWith(".md")))) {
      if (name === "README.md" || name === "MEMORY.md") {
        continue;
      }
      if (!indexText.includes(name)) {
        missingFromIndex.push(name);
      }
    }
    if (missingFromIndex.length > 0) {
      this.warn("memory.index-coverage", `memory files not mentioned in index: ${missingFromIndex.join(", ")}`, {
        target: `${this.aitna}/memory`,
        fix: "List the unmentioned memory files in the memory index.",
      });
    } else {
      this.ok("memory.index-coverage", "memory index mentions all memory markdown files", {
        target: `${this.aitna}/memory`,
        fix: "Keep every memory file listed in the index.",
      });
    }
  }

  /**
   * One SKILL.md's frontmatter as `key → value`, or `null` after recording why it cannot be read.
   * @param {string} source
   * @returns {Frontmatter | null}
   */
  _skillFrontmatter(source) {
    const lines = pySplitlines(readText(source));
    const relative = this.displayPath(source);
    if (lines.length === 0 || pyStrip(lines[0]) !== "---") {
      this.error("skills.frontmatter", `${relative} is missing required frontmatter`, {
        target: relative,
        fix: `Open ${relative} with a --- frontmatter block.`,
      });
      return null;
    }
    /** @type {Frontmatter} */
    const fields = new Map();
    /** @type {string | null} */
    let parent = null;
    for (const line of lines.slice(1)) {
      if (pyStrip(line) === "---") {
        return fields;
      }
      const colon = line.indexOf(":");
      if (colon === -1) {
        this.error("skills.frontmatter-syntax", `${relative} frontmatter line is not key: value: ${strRepr(line)}`, {
          target: relative,
          fix: "Write each frontmatter line as key: value.",
        });
        continue;
      }
      const key = pyStrip(line.slice(0, colon));
      const value = pyStrip(line.slice(colon + 1));
      // One level of nesting, as `metadata:` needs: an indented line under a key with no value of
      // its own belongs to that key.
      if (parent !== null && (line.startsWith(" ") || line.startsWith("\t"))) {
        fields.set(`${parent}.${key}`, value);
        continue;
      }
      fields.set(key, value);
      parent = value === "" ? key : null;
    }
    this.error("skills.frontmatter-close", `${relative} frontmatter is not closed with ---`, {
      target: relative,
      fix: `Close the ${relative} frontmatter block with ---.`,
    });
    return null;
  }

  /**
   * One SKILL.md's frontmatter against the Agent Skills standard and akmon's own fields.
   * @param {string} source
   */
  checkSkillContract(source) {
    const relative = this.displayPath(source);
    const fields = this._skillFrontmatter(source);
    if (fields === null) {
      return;
    }
    this._checkSkillRequiredFields(relative, fields);
    this._checkSkillName(relative, source, fields);
    this._checkSkillDescriptionLength(relative, fields);
    this._checkSkillFrontmatterYaml(relative, fields);
  }

  /**
   * Every required frontmatter key must be present and non-empty.
   * @param {string} relative
   * @param {Frontmatter} fields
   */
  _checkSkillRequiredFields(relative, fields) {
    const required = this.data.skill_required_frontmatter;
    const missing = required.filter((field) => !fields.has(field));
    const empty = required.filter((field) => fields.has(field) && !fields.get(field));
    if (missing.length > 0) {
      this.error("skills.required-fields", `${relative} frontmatter is missing: ${missing.join(", ")}`, {
        target: relative,
        fix: "Add the listed frontmatter keys to this skill; owner goes under metadata:.",
      });
    }
    if (empty.length > 0) {
      this.error("skills.field-values", `${relative} frontmatter has empty value(s): ${empty.join(", ")}`, {
        target: relative,
        fix: "Give every required frontmatter key a value.",
      });
    }
  }

  /**
   * The frontmatter name must match its directory and the Agent Skills name format.
   * @param {string} relative
   * @param {string} source
   * @param {Frontmatter} fields
   */
  _checkSkillName(relative, source, fields) {
    const directory = posix.basename(posix.dirname(source));
    const name = fields.get("name") ?? "";
    if (name && name !== directory) {
      this.error(
        "skills.name-matches-dir",
        `${relative} frontmatter name must match its skill directory (${directory})`,
        {
          target: relative,
          fix: `Set the frontmatter name to ${directory}.`,
        },
      );
    }
    const limit = this.data.skill_name_max;
    if (name && (pyLen(name) > limit || !_SKILL_NAME_RE.test(name))) {
      this.error(
        "skills.name-format",
        `${relative} frontmatter name ${strRepr(name)} is not 1-${limit} lowercase letters, digits and single inner hyphens`,
        { target: relative, fix: "Rename the skill and its directory to lowercase letters, digits and hyphens." },
      );
    }
  }

  /**
   * The description must fit in the trigger budget the Agent Skills standard allows.
   * @param {string} relative
   * @param {Frontmatter} fields
   */
  _checkSkillDescriptionLength(relative, fields) {
    const description = fields.get("description") ?? "";
    const limit = this.data.skill_description_max;
    if (pyLen(description) > limit) {
      this.error(
        "skills.description-length",
        `${relative} description is ${pyLen(description)} characters; the limit is ${limit}`,
        {
          target: relative,
          fix: "Shorten the description to the result and the trigger; move detail into the body.",
        },
      );
    }
  }

  /**
   * Flag unquoted frontmatter values that YAML and a plain reading disagree about (M56, M57).
   * @param {string} relative
   * @param {Frontmatter} fields
   */
  _checkSkillFrontmatterYaml(relative, fields) {
    for (const [key, value] of fields) {
      if (value === "" || value[0] === '"' || value[0] === "'") {
        continue;
      }
      let problem;
      if (value.includes(" #") || value.startsWith("#")) {
        problem = "an unquoted ' #' starts a YAML comment, and Claude Code and Codex cut the value there";
      } else if (value.includes(": ")) {
        problem = "an unquoted ': ' is not valid YAML, and the Agent Skills validator rejects it";
      } else {
        continue;
      }
      this.error("skills.frontmatter-yaml", `${relative} frontmatter ${key}: ${problem}`, {
        target: relative,
        fix: `Wrap the ${key} value in double quotes.`,
      });
    }
  }

  /** Find the project's skill sources and validate each one's contract. */
  checkSkills() {
    const [sources, errors] = skillSources(this.syncData, this.root);
    for (const error of errors) {
      this.error("skills.duplicate-name", error, {
        fix: "Rename one of the two skill directories so each skill name is unique.",
      });
    }
    if (sources.length > 0) {
      this.ok("skills.present", `found ${sources.length} skill(s)`, {
        fix: "Keep at least one SKILL.md in a skill root.",
      });
      for (const source of sources) {
        this.checkSkillContract(source);
      }
    } else {
      this.warn("skills.present", "no SKILL.md files found in akmon/local/usage skill roots", {
        fix: "Add a SKILL.md under a skill root, or ignore this if the project ships no skills.",
      });
    }
  }

  /** Every generated pointer file matches what the sync plan would write. */
  checkGeneratedPointers() {
    const [files, errors] = plannedFiles(this.syncData, this.root);
    for (const error of errors) {
      this.error("pointers.generated-plan", error, {
        fix: "Resolve the reported planning error, then re-run akmon sync.",
      });
    }
    const result = apply(this.syncData, files, { write: false, root: this.root });
    if (result.changed.length > 0 || result.deleted.length > 0) {
      const stale = [...result.changed, ...result.deleted].map((path) => _relativeTo(path, this.root)).join(", ");
      this.error(
        "pointers.generated-freshness",
        `generated pointers are stale or missing: ${stale}; run \`akmon sync\``,
        {
          fix: "Run akmon sync to regenerate the listed files.",
        },
      );
    } else {
      this.ok("pointers.generated-freshness", "generated pointers match `akmon sync`", {
        fix: "Re-run akmon sync after every change to a generated file's source.",
      });
    }
  }

  /**
   * The id heading a backlog entry, for naming it in a finding.
   * @param {string} entry
   * @returns {string}
   */
  static entryId(entry) {
    let head = entry.split(" · ")[0];
    head = head.startsWith("- ") ? head.slice(2) : head;
    return _stripChars(pyStrip(head), "*") || "?";
  }

  /**
   * The status of one backlog entry: the head word of its third `·` field, or `null`. Read the
   * *field*, not the line; the head word is what is checked, so `blocked (after C51)` and
   * `**active**` stay valid.
   * @param {string} entry
   * @returns {string | null}
   */
  static entryStatus(entry) {
    const fields = entry.split(" · ");
    if (fields.length < _MIN_STATUS_FIELDS) {
      return null;
    }
    const status = pyStrip(_stripChars(pyStrip(fields[2]), "*"));
    if (status === "") {
      return null;
    }
    return pyLower(_stripChars(pySplit(status)[0], "*:,;")) || null;
  }

  /** TASKS.md's length, entry statuses, done-archiving, and freedom from dates. */
  checkTasks() {
    const path = pyPath(this.root, this.aitna, "TASKS.md");
    if (!isFile(path)) {
      return; // basic layout already reports a missing TASKS.md
    }
    const lines = pySplitlines(readText(path));
    const target = `${this.aitna}/TASKS.md`;
    if (lines.length > this.data.tasks_max_lines) {
      this.warn(
        "tasks.index-length",
        `${target} is ${lines.length} lines; keep it an index (pipelines/tasks.md) — detail by reference, not inlined`,
        { target, fix: "Move inlined task detail out to a referenced document." },
      );
    }
    // Entries are top-level list items. An indented bullet is a note *under* an entry.
    const statusList = this.data.task_statuses;
    const statusJoin = statusList.join(" | ");
    const entries = lines.filter((line) => line.startsWith("- ") && line.includes(" · "));
    if (entries.length > 0) {
      const statuses = entries.map(
        (line) => /** @type {[string, string | null]} */ ([Verifier.entryId(line), Verifier.entryStatus(line)]),
      );
      const bad = statuses.filter(([, status]) => status === null || !statusList.includes(status)).map(([id]) => id);
      if (bad.length > 0) {
        this.warn(
          "tasks.entry-status",
          `${bad.length} TASKS.md entry(ies) carry a status outside ${statusJoin}: ${_sample(bad)}`,
          { target, fix: `Set each listed entry's status field to one of ${statusJoin}.` },
        );
      }
      const finished = statuses.filter(([, status]) => status === "done").map(([id]) => id);
      if (finished.length > 0) {
        this.warn(
          "tasks.done-archived",
          `TASKS.md has 'done' entries; move them to TASKS_ARCHIVE.md: ${_sample(finished)}`,
          {
            target,
            fix: "Move the listed done entries to TASKS_ARCHIVE.md.",
          },
        );
      }
      if (bad.length === 0) {
        this.ok("tasks.entry-status", "TASKS.md uses well-formed index entries", {
          target,
          fix: `Keep every entry's status field within ${statusJoin}.`,
        });
      }
    }
    if (_DATE_RE.test(lines.join("\n"))) {
      this.warn("tasks.dates", `${target} contains dates; dates are noise — derive them from git history`, {
        target,
        fix: "Delete the dates from TASKS.md and read them from git history instead.",
      });
    }
  }

  /**
   * The hook scripts the Node wiring runs must exist in the standard tree this project runs.
   * Checked as `js/hooks/<file>` — the entries and the modules they import — because a wired hook
   * whose file is missing fails silently.
   */
  checkHooks() {
    for (const script of this.data.node_wired_hook_scripts) {
      this.checkStandardPath(`${_NODE_HOOKS_DIR}/${script}`);
    }
  }

  /**
   * The folder the generated hook wiring runs node on must exist in the project's own
   * `node_modules`. A hook command whose script is missing **fails silently** — the harness runs
   * it, the shell error stays outside the session, and the guardrails stop firing — so this is
   * checked here, in the consumer's CI, rather than as a `sync` plan error: the first attach runs
   * `sync` before the dependencies are installed. In this order: Yarn Plug'n'Play (no
   * `node_modules` at all); a hoisted install in an ancestor directory (the committed wiring and
   * the generated pointers cannot reach it, `sync` spelled the tree absolute); missing; present.
   * A linked `node_modules/akmon` (pnpm) is present — the link is not resolved for the message.
   */
  checkHookLauncher() {
    const texts = this.data.node;
    const relative = _NODE_LAUNCHER_DIR;
    const pnp = /** @type {string[]} */ (texts.pnp_markers).find((marker) => isFile(pyPath(this.root, marker)));
    if (pnp !== undefined) {
      this.error("hooks.launcher", fill(texts.launcher_pnp, { found: pnp }), {
        target: pnp,
        fix: texts.launcher_pnp_fix,
      });
      return;
    }
    if (isDir(pyPath(this.root, relative))) {
      this.ok("hooks.launcher", fill(texts.launcher_ok, { relative }), {
        target: relative,
        fix: texts.launcher_ok_fix,
      });
      return;
    }
    let ancestor = this.root;
    for (;;) {
      const parent = posix.dirname(ancestor);
      if (parent === ancestor) {
        break;
      }
      ancestor = parent;
      const hoisted = pyPath(ancestor, "node_modules", "akmon");
      if (isDir(hoisted)) {
        this.error(
          "hooks.launcher",
          fill(texts.launcher_hoisted, { relative, found: posix.relative(this.root, hoisted) }),
          {
            target: relative,
            fix: texts.launcher_hoisted_fix,
          },
        );
        return;
      }
    }
    this.error("hooks.launcher", fill(texts.launcher_missing, { relative }), {
      target: relative,
      fix: texts.launcher_missing_fix,
    });
  }

  /**
   * C70 — the live host-trust gap N7 measured (design §7, ADR-0012/D03). Generated wiring is
   * structural proof only: a discovered `hooks/list` entry can stay `enabled: true` while its
   * persisted trust is absent or stale, and the handler simply never fires. This asks the
   * authoritative host through a bounded `codex app-server` query.
   *
   * Gated on current wiring before anything is parsed: `.codex/hooks.json` must be byte-identical
   * to what the current generator writes (`codexHooksText`), or this check stops — no host call,
   * no parse (TASKS.md C70). Each of those states is already one `pointers.generated-freshness`
   * error. An absent Codex installation is an explicit neutral skip; a resolved installation the
   * bounded query cannot get a clean answer from is a warning and a strict failure.
   * @returns {Promise<void>}
   */
  async checkCodexHostTrust() {
    let text;
    try {
      text = readText(pyPath(this.root, ".codex", "hooks.json"));
    } catch (error) {
      if (isOSError(error) || (error instanceof Error && error.name === "UnicodeDecodeError")) {
        return;
      }
      throw error;
    }
    if (text !== codexHooksText(this.syncData)) {
      return;
    }
    const data = this.codexHooksData;
    const expected = codexHooks.expectedCodexHooks(data, JSON.parse(text));
    if (expected.length === 0) {
      return;
    }
    const command = codexHooksListCommand(this.runtimeData);
    if (_which(command[0]) === null) {
      this.ok("codex.host-trust", `${command[0]} is not installed; Codex host-trust delivery is not verified`, {
        target: ".codex/hooks.json",
        fix: "Install codex to verify hook delivery, or ignore if this project does not run it.",
      });
      return;
    }
    let entries;
    try {
      entries = await codexHooks.queryHooksList(data, command, this.root, { runner: this._codexHooksRunner });
    } catch (error) {
      if (!(error instanceof codexHooks.CodexProtocolError)) {
        throw error;
      }
      this.warn("codex.host-trust", `codex app-server hooks/list could not be inspected: ${error.message}`, {
        target: "codex app-server hooks/list",
        fix: "Run `codex app-server` manually to diagnose, then re-run verify.",
      });
      return;
    }
    const problems = codexHooks.hookTrustProblems(data, expected, entries);
    if (Object.keys(problems).length === 0) {
      this.ok("codex.host-trust", "every generated Codex hook entry is discovered, enabled, and trusted", {
        target: ".codex/hooks.json",
        fix: "Keep hook trust current via `/hooks` after every `akmon sync`.",
      });
      return;
    }
    const summary = codePointSort(Object.keys(problems))
      .map((problem) => `${problem} (${problems[problem].length})`)
      .join("; ");
    this.warn("codex.host-trust", `Codex hook delivery is incomplete: ${summary}`, {
      target: ".codex/hooks.json",
      fix: "Open `/hooks` in Codex and re-approve the affected generated entries.",
    });
  }

  /**
   * The routing registry and tools must ship with akmon and parse cleanly. Freshness of the
   * per-user local config is the SessionStart hook's job; verify only guards the committed
   * contract surface.
   */
  checkModelRouting() {
    for (const relative of this.data.routing_shipped_paths) {
      this.checkStandardPath(relative);
    }
    const registryPath = pyPath(this.standardRoot, "tools", "model_routing", "registry.json");
    if (isFile(registryPath)) {
      try {
        const registry = _plain(readJson(registryPath, { lossy: true }));
        this.ok("routing.registry-parse", "model-routing registry parses", {
          target: this.displayPath(registryPath),
          fix: "Keep the model-routing registry valid JSON.",
        });
        this._checkModelRoutingRegistry(registry);
      } catch (error) {
        if (!_isValueError(error)) {
          throw error;
        }
        this.error("routing.registry-parse", /** @type {Error} */ (error).message, {
          target: this.displayPath(registryPath),
          fix: "Repair the model-routing registry so it parses as JSON.",
        });
      }
    }
    const overlay = pyPath(this.root, this.aitna, "model-routing.json");
    if (isFile(overlay)) {
      let overlayData;
      try {
        overlayData = _plain(readJson(overlay, { lossy: true }));
        this.ok("routing.overlay-parse", "model-routing project overlay parses", {
          target: `${this.aitna}/model-routing.json`,
          fix: "Keep the project routing overlay valid JSON.",
        });
      } catch (error) {
        if (!_isValueError(error)) {
          throw error;
        }
        this.error("routing.overlay-parse", /** @type {Error} */ (error).message, {
          target: `${this.aitna}/model-routing.json`,
          fix: "Repair the project routing overlay so it parses as JSON.",
        });
        return;
      }
      // Outside the try: a defect in the check below must not be reported as a parse failure of
      // the file it is reading.
      this._checkOverlaySecondOpinion(overlayData);
    }
  }

  /**
   * The overlay must not carry keys C57 retired. It is deep-merged *over* the shipped registry, so
   * a stale `cli`/`invoke` pair rides alongside `harness`/`operation`, unread — checked at the file
   * rather than inferred from the merged result.
   * @param {Json} overlay
   */
  _checkOverlaySecondOpinion(overlay) {
    if (!isDict(overlay)) {
      return;
    }
    for (const vendor of this.data.routing_vendors) {
      const spec = dictGet(overlay, vendor);
      if (!isDict(spec)) {
        continue;
      }
      const second = dictGet(spec, "second_opinion");
      if (!isDict(second)) {
        continue;
      }
      const retired = this.data.routing_retired_second_opinion_keys.filter((key) => Object.hasOwn(second, key));
      if (retired.length > 0) {
        this.error(
          "routing.second-opinion",
          `project overlay ${vendor} second_opinion carries the retired key(s) ${retired.join(", ")}`,
          {
            target: `${this.aitna}/model-routing.json#${vendor}`,
            fix:
              "Delete only cli/invoke from this hand-owned overlay, leave the rest " +
              "of the object as it is, then re-run the routing initializer.",
          },
        );
      }
    }
  }

  /**
   * @param {Json} registry
   */
  _checkModelRoutingRegistry(registry) {
    const policyValues = this.data.reasoner_policy_values;
    for (const vendor of this.data.routing_vendors) {
      const spec = dictGet(registry, vendor);
      const target = `tools/model_routing/registry.json#${vendor}`;
      if (!isDict(spec)) {
        this.error("routing.vendor-present", `model-routing registry is missing vendor ${strRepr(vendor)}`, {
          target,
          fix: `Add the ${vendor} object to the model-routing registry.`,
        });
        continue;
      }
      const policy = dictGet(spec, "selection_policy");
      if (
        isDict(policy) &&
        pyContains(policyValues, dictGet(policy, "reasoner")) &&
        pyEq(dictGet(policy, "worker"), "lowest")
      ) {
        this.ok("routing.selection-policy", `model-routing ${vendor} semantic selection policy exists`, {
          target,
          fix: "Keep the semantic selection policy on this vendor.",
        });
      } else {
        this.error(
          "routing.selection-policy",
          `model-routing ${vendor} needs semantic selection_policy with worker=lowest and reasoner ${policyValues.join(" or ")}`,
          {
            target,
            fix: `Set this vendor's selection_policy to worker=lowest and reasoner ${policyValues.join(" or ")}.`,
          },
        );
      }
      const fallback = dictGet(spec, "semantic_fallback");
      if (isDict(fallback) && this.data.routing_semantic_fallback_keys.every((key) => truthy(dictGet(fallback, key)))) {
        this.ok("routing.semantic-fallback", `model-routing ${vendor} semantic fallback exists`, {
          target,
          fix: "Keep a model named for every tier in this vendor's semantic_fallback.",
        });
      } else {
        this.error(
          "routing.semantic-fallback",
          `model-routing ${vendor} semantic_fallback must name worker/mid/reasoner/orchestrator`,
          {
            target,
            fix: "Name a model for each of worker, mid, reasoner and orchestrator in semantic_fallback.",
          },
        );
      }
      const second = dictGet(spec, "second_opinion");
      if (!isDict(second)) {
        this.error("routing.second-opinion", `model-routing ${vendor} second_opinion is missing`, {
          target,
          fix: "Add a second_opinion object with harness, operation and report_dir to this vendor.",
        });
        continue;
      }
      const missing = this.data.routing_second_opinion_keys.filter((key) => !truthy(dictGet(second, key)));
      if (missing.length > 0) {
        this.error("routing.second-opinion", `model-routing ${vendor} second_opinion missing: ${missing.join(", ")}`, {
          target,
          fix: "Fill in the listed second_opinion keys for this vendor.",
        });
      } else {
        this.ok("routing.second-opinion", `model-routing ${vendor} second_opinion is configured`, {
          target,
          fix: "Keep harness, operation and report_dir set for this vendor's second_opinion.",
        });
      }
    }
  }

  /** `.gitignore` carries the akmon env-secret ignore pattern. */
  checkGitignore() {
    const path = pyPath(this.root, ".gitignore");
    if (!isFile(path)) {
      this.warn("gitignore.env-secrets", ".gitignore is missing", {
        target: ".gitignore",
        fix: "Add a .gitignore ignoring '*.env' while keeping '!*.env.example'.",
      });
      return;
    }
    const text = readText(path);
    const patterns = this.data.gitignore_patterns;
    if (text.includes(patterns.env_secret) && text.includes(patterns.env_example_keep)) {
      this.ok("gitignore.env-secrets", ".gitignore has the akmon env secret pattern", {
        target: ".gitignore",
        fix: "Keep the '*.env' and '!*.env.example' patterns in .gitignore.",
      });
    } else {
      this.warn("gitignore.env-secrets", ".gitignore should include '*.env' and '!*.env.example'", {
        target: ".gitignore",
        fix: "Add '*.env' and '!*.env.example' to .gitignore.",
      });
    }
  }

  /** A GitHub Actions workflow runs akmon's sync and verify commands. */
  checkCi() {
    const workflowDir = pyPath(this.root, ".github", "workflows");
    const names = _names(workflowDir);
    const workflows = [
      ...codePointSort(names.filter((name) => name.endsWith(".yml"))),
      ...codePointSort(names.filter((name) => name.endsWith(".yaml"))),
    ];
    if (workflows.length === 0) {
      this.warn("ci.akmon-checks", "no GitHub Actions workflows found", {
        target: ".github/workflows",
        fix: "Add a workflow running the akmon sync and verify checks.",
      });
      return;
    }
    const workflowText = workflows.map((name) => readText(pyPath(workflowDir, name))).join("\n");
    // Pinned package-mode contract: the CLI, not a path into a mount that doesn't exist (ADR 0009
    // §4). Substring match so `npx akmon sync --check` etc. pass.
    const required = this.data.ci_required_commands["package"].map((command) => fill(command, { akmon: this.akmon }));
    const missing = required.filter((command) => !workflowText.includes(command));
    if (missing.length > 0) {
      this.warn("ci.akmon-checks", `CI should run: ${missing.join(", ")}`, {
        target: ".github/workflows",
        fix: "Add the listed akmon commands to a CI workflow step.",
      });
    } else {
      this.ok("ci.akmon-checks", "CI checks akmon generated pointers and verify", {
        target: ".github/workflows",
        fix: "Keep the akmon sync and verify commands in CI.",
      });
    }
  }

  /**
   * Package mode: the standard's changelog discipline is owned by the akmon repository, not by
   * this consumer's integration surface (the mounted half, `changelog.unreleased`, is unreachable).
   */
  checkChangelog() {
    this.ok("changelog.package-mode", this.data.changelog_package_mode, { fix: this.data.changelog_package_mode_fix });
  }

  /**
   * The consumer's `package.json` must pin akmon in `devDependencies`, and the pin must be exact.
   * Package mode mounts no tree, so that declaration *is* the pin: without it `npx akmon` cannot
   * resolve and the CI commands cannot run. The class is locked too — a runtime dependency pushes
   * dev tooling onto the consumer's own users, so it is an error rather than a warning. Exact,
   * because the record and the generated wiring are written per akmon version: a range lets two
   * installs resolve different ones. A git dependency at a release tag is exact too: the tag names
   * one release. Only checked when a `package.json` exists.
   */
  checkPackagePin() {
    if (!isFile(pyPath(this.root, "package.json"))) {
      return;
    }
    const texts = this.data.node;
    const status = packagePinStatus(this.root);
    const target = "package.json";
    if (status === "runtime") {
      this.error("package.dev-pin", texts.pin_runtime, { target, fix: texts.pin_runtime_fix });
    } else if (status === "unreadable") {
      this.warn("package.dev-pin", texts.pin_unreadable, { target, fix: texts.pin_unreadable_fix });
    } else if (status === "none") {
      this.warn("package.dev-pin", texts.pin_none, { target, fix: texts.pin_none_fix });
    } else {
      const value = _devPinValue(this.root);
      if (typeof value === "string" && (_EXACT_VERSION_RE.test(value) || _GIT_TAG_PIN_RE.test(value))) {
        this.ok("package.dev-pin", texts.pin_ok, { target, fix: texts.pin_ok_fix });
      } else {
        this.warn("package.dev-pin", fill(texts.exact_pin_warn, { value: _pinSpelling(value) }), {
          target,
          fix: texts.exact_pin_warn_fix,
        });
      }
    }
  }

  /**
   * Validate the `_aitna/.akmon.toml` integration record *of a consuming project*: the "where the
   * project is" anchor that BOOTSTRAP §E diffs against akmon's CHANGELOG. A missing record is a
   * non-gating note, so it never fails `--strict`; only a *present but malformed* record is an
   * error — and a record that is well-formed but behind is one too, for its own reason
   * ({@link checkRealignFreshness}).
   */
  checkAttachRecord() {
    const name = `${this.aitna}/.akmon.toml`;
    const path = pyPath(this.root, this.aitna, ".akmon.toml");
    if (!isDir(pyPath(this.root, this.akmon)) && !isFile(path)) {
      return; // akmon repo itself, or not an akmon consumer — no integration record expected
    }
    if (!isFile(path)) {
      this.ok(
        "attach.record",
        `${name} not present (optional; a realign writes it so future bumps can diff the CHANGELOG — BOOTSTRAP §E)`,
        { target: name, fix: `Run a realign when you next bump akmon so ${name} is written.` },
      );
      return;
    }
    const fields = readAkmonToml(path);
    const missing = this.data.record_required_keys.filter((key) => !_recordTruthy(fields[key]));
    if (missing.length > 0) {
      this.error("attach.record", `${name} is missing required key(s): ${missing.join(", ")}`, {
        target: name,
        fix: `Add the listed keys to ${name} by re-running a realign.`,
      });
      return;
    }
    const invalidVersions = ["akmon_version", "last_realign"].filter(
      (key) => typeof fields[key] !== "string" || pyStrip(/** @type {string} */ (fields[key])) === "",
    );
    if (invalidVersions.length > 0) {
      this.error(
        "attach.record",
        `${name} has invalid version key(s): ${invalidVersions.join(", ")}; expected non-empty strings`,
        {
          target: name,
          fix: `Repair the listed keys in ${name} by re-running a realign.`,
        },
      );
      return;
    }
    this.ok("attach.record", `${name} records akmon version ${fields["akmon_version"]}`, {
      target: name,
      fix: `Refresh ${name} on every akmon bump.`,
    });
    this.checkRealignFreshness(name, fields);
  }

  /**
   * The recorded realign must name the version the record says the project sits on. `sync` is not
   * a realign: it stamps `akmon_version` with the installed version on every run, so that key
   * records the *pin*. A pin ahead of the last realign is a project running new hooks against an
   * old alignment. Both spellings are normalized first (`splitVersion`).
   * @param {string} name
   * @param {Record<string, unknown>} fields
   */
  checkRealignFreshness(name, fields) {
    const recorded = /** @type {string} */ (fields["akmon_version"]);
    const realigned = /** @type {string} */ (fields["last_realign"]);
    if (splitVersion(recorded).base === splitVersion(realigned).base) {
      this.ok("attach.realign", `${name} was realigned at ${realigned}, the version it records`, {
        target: name,
        fix: "Run `akmon init` after every bump so the realign follows the pin.",
      });
      return;
    }
    this.error(
      "attach.realign",
      `${name} records akmon ${recorded} but was last realigned at ${realigned} — the pin moved and the project was never realigned to it`,
      { target: name, fix: "Run `akmon init` to realign, then `akmon sync` and `akmon verify --strict`." },
    );
  }

  /**
   * The `[check]` table of the integration record — validated here, run by `akmon check`
   * (ADR 0014 §4). Only the table, never the checks themselves: a malformed entry silently stops a
   * check from running, and that is integration health.
   */
  checkCheckConfig() {
    const data = this.checkData;
    let table;
    try {
      table = readAkmonTomlStrict(pyPath(aitnaRoot(this.root), ".akmon.toml"))["check"];
    } catch (error) {
      if (!(error instanceof RecordError)) {
        throw error;
      }
      this.error("check.config", error.message, { target: configTarget(data), fix: repairRecordVerifyFix(data) });
      return;
    }
    if (table === undefined || table === null) {
      return;
    }
    const { checks, problems } = readChecks(data, table);
    for (const problem of problems) {
      this.error("check.config", problem, { target: configTarget(data), fix: correctEntryFix(data) });
    }
    // An empty table is what `init --checks none` records (C123): no finding, as for no table.
    if (checks.length > 0 && problems.length === 0) {
      const [message, fix] = checkTableOk(data);
      this.ok("check.config", fill(message, { count: String(checks.length) }), { target: configTarget(data), fix });
    }
  }

  /**
   * Run every check in order, accumulating findings.
   * @returns {Promise<void>}
   */
  async run() {
    this.checkBasicLayout();
    this.checkUseSurfaceIsolation();
    this.checkAgentsMd();
    this.checkCrossAgentContract();
    this.checkAgentCharters();
    this.checkMemory();
    this.checkTasks();
    this.checkSkills();
    this.checkGeneratedPointers();
    this.checkHooks();
    this.checkHookLauncher();
    await this.checkCodexHostTrust();
    this.checkModelRouting();
    this.checkGitignore();
    this.checkCi();
    this.checkChangelog();
    this.checkPackagePin();
    this.checkAttachRecord();
    this.checkCheckConfig();
  }
}

/**
 * Whether `error` is Python's `ValueError` family as the readers here raise it (`UnicodeDecodeError`
 * is a subclass).
 * @param {unknown} error
 * @returns {boolean}
 */
function _isValueError(error) {
  return error instanceof Error && (error.name === "ValueError" || error.name === "UnicodeDecodeError");
}

/** What `-h` / `--help` prints (the Python has `argparse`'s own block; see the header). */
const USAGE = `usage: akmon verify [-h] [--project-root PROJECT_ROOT] [--strict] [--quiet]

Validate an akmon-consuming project's USE contract.

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --strict              Treat warnings as failures.
  --quiet               Only print warnings and errors.
`;

/**
 * Parse the arguments after `verify`.
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, strict: boolean, quiet: boolean, help: boolean} | string} the options, or the one-line usage error
 */
function _parse(argv) {
  try {
    const { values } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        strict: { type: "boolean" },
        quiet: { type: "boolean" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: false,
      strict: true,
    });
    return {
      projectRoot: /** @type {string | undefined} */ (values["project-root"]) ?? null,
      strict: values.strict === true,
      quiet: values.quiet === true,
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
 * Parse arguments, run every check against the project, and print findings.
 * @param {string[]} [argv] the arguments after `verify` (default: the process's)
 * @param {{codexHooksRunner?: Runner}} [options] the host-trust
 *   query's injectable runner (tests; the command line never passes one)
 * @returns {Promise<number>} The process exit code: 0, 1 when a finding fails (a warning too under
 *   `--strict`), 2 for a usage error or a record this implementation does not serve.
 */
export async function main(argv = process.argv.slice(2), { codexHooksRunner } = {}) {
  const options = _parse(argv);
  if (typeof options === "string") {
    process.stderr.write(`akmon verify: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }
  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  // The refusal comes first (C105): these checks read the Node carrier (the launcher folder, the
  // `package.json` pin), so a report on any other record would be wrong rather than partial.
  const verify = new Verifier(root, { codexHooksRunner });
  const found = unsupportedFound(verify.syncData, root);
  if (found !== null) {
    process.stderr.write(`${fill(verify.data.unsupported_record, { found })}\n`);
    return 2;
  }
  await verify.run();
  printFindings(verify.findings, { quiet: options.quiet });
  return exitCode(verify.findings, { strict: options.strict });
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
  process.exitCode = await main();
}
