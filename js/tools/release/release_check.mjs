#!/usr/bin/env node
/**
 * Release readiness tool for the akmon `release` role (propose / prepare only) — the JavaScript
 * twin of `tools/release/release_check.py` (C108, ADR 0020 D01). The Python module is the spec:
 * the same stdout lines, the same `error:` line, the same exit codes; its docstring carries the
 * full account of the modes and of the version <-> changelog cross-check.
 *
 * It drives the mechanical parts of a release — collect state, run the verify suite, print an
 * owner-run command plan — and **never** runs `git commit` / `git tag` / `git push` / publish.
 *
 *     --state             summarize TASKS / TASKS_ARCHIVE / CHANGELOG / git status
 *     --check             run the subject's release suite (the default)
 *     --plan vX.Y.Z       print the exact owner-run commit/tag/push command set
 *
 * The subject (`--subject akmon|package`) is the akmon standard's own tag, or the consuming
 * project's package version.
 *
 * Data (the C102 convention): `main` reads `tools/release/release.json` once and passes it down.
 *
 * Twin notes (`meta/conformance/DIVERGENCES.md`):
 * - `--subject package --check` runs the verify of this very tree (`node js/akmon/cli.mjs verify
 *   --project-root R --strict --quiet`) where Python spawns `bin/verify.py`; both print the line
 *   `akmon verify --project-root R --strict --quiet`;
 * - `--subject akmon --check` (and the default, which is that) is refused with exit 2: it runs
 *   akmon's own Python release suite (self-CI and pytest), which only the Python implementation
 *   has; `--state` and `--plan` for the akmon subject are ported;
 * - the arguments are parsed by `node:util` `parseArgs` (ADR 0020 D08): a usage error is the one
 *   line `release_check.mjs: error: …` on stderr and exit 2 (`argparse` prints its usage block with
 *   every error, names the program `release_check.py`, and abbreviates long options),
 *   `-h`/`--help` prints a short usage and exits 0;
 * - a `git` that cannot be started is reported by its error code, where Python names the `OSError`.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { basename, join, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { TextDecoder, parseArgs } from "node:util";

import { embeddedTreeRoot } from "../../akmon/_tree.mjs";
import { Finding, exitCode, lineSafe, printFindings } from "../../common/findings.mjs";
import { fill, read } from "../../common/jsondata.mjs";
import { JSONDecodeError, jsonLoads } from "../../common/pyjson.mjs";
import {
  aitnaRoot,
  aitnaRootName,
  akmonMount,
  findProjectRoot,
  isProjectRoot,
  resolvePath,
  resolveProjectRoot,
} from "../../common/project_root.mjs";
import {
  isDict,
  isDir,
  isFile,
  pyLstrip,
  pyPath,
  pyRepr,
  pySplitlines,
  pyStrip,
  readText,
} from "../../common/pyvalue.mjs";
import { isFinal, semverSpelling, splitVersion } from "../../common/versions.mjs";
import { TomlError, parse as parseToml } from "../../vendor/smol-toml/dist/index.js";

/**
 * The keys of `tools/release/release.json`; the text groups are read by key, so they are loose.
 * @typedef {object} ReleaseData
 * @property {string} changelog_name
 * @property {string} pyproject_name
 * @property {string} static_version_file
 * @property {string[]} subjects
 * @property {Record<string, any>} run_state
 * @property {Record<string, any>} run_check
 * @property {Record<string, any>} findings
 * @property {Record<string, any>} run_plan
 */

const PROG = "release_check.mjs";

const USAGE = `usage: ${PROG} [-h] [--project-root PROJECT_ROOT] [--subject {akmon,package}]
                        [--state | --check | --plan vX.Y.Z]

Release readiness tool for the akmon release role (propose / prepare only).

options:
  -h, --help            show this help message and exit
  --project-root PROJECT_ROOT
                        Project root. Defaults to cwd or a parent with AGENTS.md.
  --subject {akmon,package}
                        Release subject: akmon (the standard's tag, default) or package (the project's own version).
  --state               Summarize TASKS / CHANGELOG / git status.
  --check               Run the subject's release suite (default).
  --plan vX.Y.Z         Print the owner-run commit/tag/push command set.
`;

/** Python's `^` and `$` under `re.MULTILINE`: a line starts after a newline only and ends before one only. */
const LINE_START = "(?<![^\\n])";
const LINE_END = "(?![^\\n])";

const VERSION_RE = /^v\d+\.\d+\.\d+$/;
const UNRELEASED_RE = new RegExp(`${LINE_START}##\\s+Unreleased(?![\\p{L}\\p{N}_])`, "iu");
const STATIC_VERSION_RE = new RegExp(`${LINE_START}_STATIC_VERSION\\s*=\\s*["']([^"']+)["']`);
const HEADING_RE = new RegExp(`${LINE_START}##\\s+([^\\n]+?)\\s*${LINE_END}`, "g");
const SECTION_HEADING_RE = new RegExp(`${LINE_START}##\\s+([^\\n]+)${LINE_END}`, "g");
// A released heading names its version *first* and may say more after it (see the Python for why).
const HEADING_VERSION_RE = /^\[?v?(\d+\.\d+\.\d+)\]?(?:[^\p{L}\p{N}_.+-]|$)/u;
const UNRELEASED_HEADING_RE = /^\[?unreleased\]?$/i;
const TAG_SHAPE_RE = /^v?\d+\.\d+\.\d+$/;

/**
 * The release subjects: the akmon standard's own tag, or the consuming project's package.
 * @param {ReleaseData} data
 * @returns {string[]}
 */
export function subjects(data) {
  return [...data.subjects];
}

/**
 * The release charter, project-root-relative, under the *configured* dev layer.
 * @returns {string}
 */
function _releaseCharter() {
  return `${aitnaRootName()}/agents/release/README.md`;
}

/**
 * @param {string} path
 * @returns {string}
 */
function _read(path) {
  return isFile(path) ? readText(path) : "";
}

/**
 * @param {string} [text]
 */
function _out(text = "") {
  process.stdout.write(`${text}\n`);
}

// --------------------------------------------------------------------------------------
// --state
// --------------------------------------------------------------------------------------

/**
 * `git -C <root> <args>`; `error` names why git could not be started.
 * @param {string} root
 * @param {string[]} args
 * @returns {{status: number | null, stdout: string, error?: Error} }
 */
function _git(root, args) {
  const proc = spawnSync("git", ["-C", root, ...args], { encoding: "utf8", maxBuffer: Infinity });
  return { status: proc.status, stdout: proc.stdout ?? "", error: proc.error };
}

/**
 * @param {ReleaseData} data
 * @param {string} root
 * @returns {string}
 */
function _gitStatus(data, root) {
  const texts = data.run_state;
  const proc = _git(root, ["status", "--short"]);
  if (proc.error) {
    const code = /** @type {{code?: string}} */ (proc.error).code;
    return code === "ENOENT" ? texts.git_not_found : fill(texts.git_status_failed, { exc: proc.error.message });
  }
  const out = pyStrip(proc.stdout);
  return out || texts.git_clean;
}

/**
 * @param {ReleaseData} data
 * @param {string} akmon
 * @returns {string[]}
 */
function _changelogSummary(data, akmon) {
  const texts = data.run_state;
  const changelog = changelogName(data);
  const text = _read(pyPath(akmon, changelog));
  if (!text) {
    return [fill(texts.file_missing, { name: changelog })];
  }
  const lines = [texts.changelog_sections];
  for (const match of text.matchAll(SECTION_HEADING_RE)) {
    lines.push(fill(texts.changelog_section_item, { heading: pyStrip(match[1]) }));
  }
  if (!UNRELEASED_RE.test(text)) {
    lines.push(texts.changelog_no_unreleased);
  }
  return lines;
}

/**
 * @param {ReleaseData} data
 * @param {string} tasksDir
 * @returns {string[]}
 */
function _tasksSummary(data, tasksDir) {
  /** @type {string[]} */
  const out = [];
  const texts = data.run_state;
  for (const name of ["TASKS.md", "TASKS_ARCHIVE.md"]) {
    const text = _read(pyPath(tasksDir, name));
    if (!text) {
      out.push(fill(texts.file_missing, { name }));
      continue;
    }
    const entries = pySplitlines(text)
      // `str.lstrip()`, not `trimStart()`: a BOM is whitespace to JavaScript and not to Python (C115).
      .filter((ln) => pyLstrip(ln).startsWith("- ") && ln.includes(" · "))
      .map((ln) => pyStrip(ln));
    out.push(fill(texts.file_entry_count, { name, count: String(entries.length) }));
    if (name === "TASKS.md") {
      const done = entries.filter((ln) => /(?<![\p{L}\p{N}_])done(?![\p{L}\p{N}_])/u.test(ln));
      if (done.length > 0) {
        out.push(fill(texts.done_move_note, { count: String(done.length) }));
      }
    }
  }
  return out;
}

/**
 * `--state`: print the TASKS / CHANGELOG / release-charter / git-status summary.
 *
 * The akmon subject reads `<AITNA_ROOT>/akmon` when the project mounts it, else the running tree
 * itself; it is refused when that tree has no `meta/` at all (see the Python).
 * @param {ReleaseData} data
 * @param {string} root
 * @param {string} subject
 * @returns {number} 0, or 2 for the refused akmon subject without `meta/`
 */
export function runState(data, root, subject) {
  const mounted = pyPath(aitnaRoot(root), "akmon");
  const akmon = isDir(mounted) ? mounted : embeddedTreeRoot();
  // The subject decides which working tree a tag is cut from (see the Python).
  /** @type {string} */ let tasksDir;
  /** @type {string} */ let changelogDir;
  /** @type {string} */ let gitDir;
  if (subject === "akmon") {
    tasksDir = pyPath(akmon, "meta");
    changelogDir = akmon;
    gitDir = fs.existsSync(pyPath(akmon, ".git")) ? akmon : root;
  } else {
    tasksDir = root;
    changelogDir = root;
    gitDir = root;
  }

  const texts = data.run_state;
  if (subject === "akmon" && !isDir(tasksDir)) {
    process.stderr.write(`${texts.akmon_meta_absent}\n`);
    return 2;
  }
  _out(fill(texts.state_header, { subject }));
  _out(fill(texts.project_root_line, { root }));
  _out();
  for (const line of _tasksSummary(data, tasksDir)) {
    _out(line);
  }
  _out();
  for (const line of _changelogSummary(data, changelogDir)) {
    _out(line);
  }
  _out();
  if (subject === "package") {
    const charter = pyPath(root, _releaseCharter());
    const note = isFile(charter) ? texts.charter_found : texts.charter_missing;
    _out(fill(texts.charter_line, { charter: _releaseCharter(), note }));
    _out();
  }
  _out(fill(texts.git_status_header, { name: basename(gitDir) }));
  for (const line of pySplitlines(_gitStatus(data, gitDir))) {
    _out(`  ${line}`);
  }
  return 0;
}

// --------------------------------------------------------------------------------------
// version <-> changelog cross-check (C54, design §4 — owner choice F9)
// --------------------------------------------------------------------------------------

/**
 * The changelog file whose topmost released window the version is checked against.
 * @param {ReleaseData} data
 * @returns {string}
 */
export function changelogName(data) {
  return data.changelog_name;
}

/**
 * The file holding the `[project].version` literal hatchling stamps into the wheel.
 * @param {ReleaseData} data
 * @returns {string}
 */
export function pyprojectName(data) {
  return data.pyproject_name;
}

/**
 * The file holding the `_STATIC_VERSION` fallback literal for an uninstalled package.
 * @param {ReleaseData} data
 * @returns {string}
 */
export function staticVersionFile(data) {
  return data.static_version_file;
}

/**
 * A non-blank string, or `null`.
 * @param {unknown} value
 * @returns {string | null}
 */
function _nonBlank(value) {
  return typeof value === "string" && pyStrip(value) !== "" ? value : null;
}

/**
 * `[project].version` from `pyproject.toml`, or `null` when there is none.
 * @param {string} path
 * @returns {string | null}
 */
function _pyprojectVersion(path) {
  if (!isFile(path)) {
    return null;
  }
  /** @type {Record<string, unknown>} */ let table;
  try {
    const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(fs.readFileSync(path));
    table = parseToml(text);
  } catch (exc) {
    if (
      exc instanceof TomlError ||
      exc instanceof TypeError ||
      /** @type {{code?: string}} */ (exc).code !== undefined
    ) {
      return null;
    }
    throw exc;
  }
  const project = table.project;
  return isDict(project) ? _nonBlank(/** @type {Record<string, unknown>} */ (project).version) : null;
}

/**
 * The `_STATIC_VERSION` literal, read as a literal rather than by importing the package.
 * @param {string} path
 * @returns {string | null}
 */
function _staticVersion(path) {
  if (!isFile(path)) {
    return null;
  }
  const match = STATIC_VERSION_RE.exec(readText(path));
  return match ? match[1] : null;
}

/**
 * The `version` literal of the npm carrier (`package.json`), or `null` when absent or broken.
 * @param {string} path
 * @returns {string | null}
 */
function _packageJsonVersion(path) {
  if (!isFile(path)) {
    return null;
  }
  /** @type {unknown} */ let value;
  try {
    value = jsonLoads(readText(path));
  } catch (exc) {
    const name = /** @type {Error} */ (exc).name;
    if (
      exc instanceof JSONDecodeError ||
      /** @type {{code?: string}} */ (exc).code !== undefined ||
      name === "UnicodeDecodeError"
    ) {
      return null;
    }
    throw exc;
  }
  return isDict(value) ? _nonBlank(/** @type {Record<string, unknown>} */ (value).version) : null;
}

/**
 * Every `## ` heading, in file order — the changelog window as a reader meets it.
 * @param {string} path
 * @returns {string[]}
 */
function _changelogHeadings(path) {
  if (!isFile(path)) {
    return [];
  }
  return [...readText(path).matchAll(HEADING_RE)].map((match) => pyStrip(match[1]));
}

/**
 * Every version-shaped tag, or `null` when git cannot answer — absent binary or no repo.
 * @param {string} root
 * @returns {string[] | null}
 */
function _gitTags(root) {
  const proc = _git(root, ["tag", "--list"]);
  if (proc.error || proc.status !== 0) {
    return null;
  }
  return pySplitlines(proc.stdout)
    .map((line) => pyStrip(line))
    .filter((line) => TAG_SHAPE_RE.test(line));
}

/**
 * A finding whose message and target may quote a file: every separator is escaped first.
 * @param {string} severity
 * @param {string} code
 * @param {string} message
 * @param {string} target
 * @param {string} fix
 * @returns {Finding}
 */
function _finding(severity, code, message, target, fix) {
  return new Finding({ severity, code, message: lineSafe(message), target: lineSafe(target), fix });
}

/**
 * A rule that could not run, said out loud. Never an error: see F9/4 and F9/5.
 * @param {string} message
 * @param {string} target
 * @param {string} fix
 * @returns {Finding}
 */
function _skip(message, target, fix) {
  return _finding("warn", "release.check-skipped", message, target, fix);
}

/**
 * The F9 join over `root`'s version carriers, as shared-envelope findings.
 *
 * The `package.json` carrier is checked for the `akmon` subject only (see the Python).
 * @param {ReleaseData} data
 * @param {string} root
 * @param {string} [subject]
 * @returns {Finding[]}
 */
export function checkReleaseVersions(data, root, subject = "package") {
  /** @type {Finding[]} */
  const findings = [];
  const changelog = changelogName(data);
  const pyproject = pyprojectName(data);
  const staticFile = staticVersionFile(data);
  const texts = data.findings;
  const changelogPath = pyPath(root, changelog);
  // Read once: two rules ask about the same headings.
  const headings = _changelogHeadings(changelogPath);

  const declared = _pyprojectVersion(pyPath(root, pyproject));
  const fallback = _staticVersion(pyPath(root, staticFile));
  if (declared !== null && fallback !== null) {
    if (declared === fallback) {
      findings.push(
        _finding(
          "ok",
          "release.version-literals",
          fill(texts["version-literals-match"].message, { pyproject, static_version_file: staticFile, declared }),
          pyproject,
          texts["version-literals-match"].fix,
        ),
      );
    } else {
      findings.push(
        _finding(
          "error",
          "release.version-literals",
          fill(texts["version-literals-mismatch"].message, {
            pyproject,
            static_version_file: staticFile,
            declared,
            fallback,
          }),
          pyproject,
          texts["version-literals-mismatch"].fix,
        ),
      );
    }
  }
  // `pyproject` wins when both exist: it is the literal that names the built wheel.
  const version = declared !== null ? declared : fallback;

  if (subject === "akmon" && version !== null) {
    /** @type {string | null} */ let expected = null;
    try {
      expected = semverSpelling(version);
    } catch (exc) {
      findings.push(
        _skip(
          fill(texts["npm-carrier-unrepresentable"].message, {
            declared: version,
            detail: /** @type {Error} */ (exc).message,
          }),
          "package.json",
          texts["npm-carrier-unrepresentable"].fix,
        ),
      );
    }
    if (expected !== null) {
      const actual = _packageJsonVersion(pyPath(root, "package.json"));
      if (actual === null) {
        findings.push(
          _finding(
            "error",
            "release.version-literals",
            fill(texts["npm-carrier-missing"].message, { declared: version }),
            "package.json",
            texts["npm-carrier-missing"].fix,
          ),
        );
      } else if (actual === expected) {
        findings.push(
          _finding(
            "ok",
            "release.version-literals",
            fill(texts["npm-carrier-match"].message, { expected, pyproject, declared: version }),
            "package.json",
            texts["npm-carrier-match"].fix,
          ),
        );
      } else {
        findings.push(
          _finding(
            "error",
            "release.version-literals",
            fill(texts["npm-carrier-mismatch"].message, { actual, pyproject, declared: version, expected }),
            "package.json",
            texts["npm-carrier-mismatch"].fix,
          ),
        );
      }
    }
  }

  if (version === null) {
    findings.push(
      _skip(
        fill(texts["no-version-source"].message, { pyproject, static_version_file: staticFile }),
        "",
        texts["no-version-source"].fix,
      ),
    );
  } else if (!isFile(changelogPath)) {
    findings.push(
      _skip(
        fill(texts["changelog-absent"].message, { changelog, version }),
        changelog,
        fill(texts["changelog-absent"].fix, { changelog }),
      ),
    );
  } else {
    findings.push(..._checkWindow(data, version, headings));
  }

  findings.push(..._checkTags(data, root, version, isFile(changelogPath), headings));
  return findings;
}

/**
 * `[heading, version]` for every heading that names a release, in file order.
 * @param {string[]} headings
 * @returns {[string, string][]}
 */
function _releasedHeadings(headings) {
  /** @type {[string, string][]} */
  const pairs = [];
  for (const heading of headings) {
    const match = HEADING_VERSION_RE.exec(heading);
    if (match) {
      pairs.push([heading, match[1]]);
    }
  }
  return pairs;
}

/**
 * The changelog window rule, in its two branches.
 * @param {ReleaseData} data
 * @param {string} version
 * @param {string[]} headings
 * @returns {Finding[]}
 */
function _checkWindow(data, version, headings) {
  const changelog = changelogName(data);
  const texts = data.findings;
  const { base } = splitVersion(version);
  if (!isFinal(version)) {
    if (headings.length > 0 && UNRELEASED_HEADING_RE.test(headings[0])) {
      return [
        _finding(
          "ok",
          "release.changelog-window",
          fill(texts["window-nonfinal-ok"].message, { version }),
          changelog,
          texts["window-nonfinal-ok"].fix,
        ),
      ];
    }
    const observed =
      headings.length > 0
        ? fill(texts["window-nonfinal-heading"], { heading: headings[0] })
        : texts["window-nonfinal-none"];
    return [
      _finding(
        "error",
        "release.changelog-window",
        fill(texts["window-nonfinal-error"].message, { version, observed }),
        changelog,
        texts["window-nonfinal-error"].fix,
      ),
    ];
  }
  const released = _releasedHeadings(headings);
  if (released.length === 0) {
    return [
      _finding(
        "error",
        "release.changelog-window",
        fill(texts["window-final-no-released"].message, { version, changelog }),
        changelog,
        fill(texts["window-final-no-released"].fix, { base }),
      ),
    ];
  }
  // The *topmost* released heading, not any of them.
  const [topmost, topmostBase] = released[0];
  if (topmostBase !== base) {
    return [
      _finding(
        "error",
        "release.changelog-window",
        fill(texts["window-final-topmost-mismatch"].message, { version, topmost }),
        changelog,
        fill(texts["window-final-topmost-mismatch"].fix, { base, topmost }),
      ),
    ];
  }
  return [
    _finding(
      "ok",
      "release.changelog-window",
      fill(texts["window-final-ok"].message, { version, topmost }),
      changelog,
      texts["window-final-ok"].fix,
    ),
  ];
}

/**
 * The two git-dependent rules: the re-release warn and the tag-coverage warn.
 * @param {ReleaseData} data
 * @param {string} root
 * @param {string | null} version
 * @param {boolean} hasChangelog
 * @param {string[]} headings
 * @returns {Finding[]}
 */
function _checkTags(data, root, version, hasChangelog, headings) {
  /** @type {Finding[]} */
  const findings = [];
  const changelog = changelogName(data);
  const texts = data.findings;
  const tags = _gitTags(root);
  const final = version !== null && isFinal(version);
  if (tags === null) {
    if (final) {
      findings.push(
        _skip(
          fill(texts["git-unavailable-final"].message, { version: version ?? "" }),
          "",
          texts["git-unavailable-final"].fix,
        ),
      );
    }
    findings.push(
      _skip(fill(texts["git-unavailable-tags"].message, { changelog }), changelog, texts["git-unavailable-tags"].fix),
    );
    return findings;
  }

  // `vX.Y.Z` is the only admissible release-tag spelling; a misspelled one is reported, then excluded.
  const releaseTags = tags.filter((tag) => tag.startsWith("v"));
  for (const tag of tags) {
    if (!tag.startsWith("v")) {
      findings.push(
        _finding(
          "warn",
          "release.tag-spelling",
          fill(texts["tag-spelling"].message, { tag }),
          tag,
          fill(texts["tag-spelling"].fix, { tag }),
        ),
      );
    }
  }

  if (final) {
    const { base } = splitVersion(version ?? "");
    const matching = releaseTags.filter((tag) => splitVersion(tag).base === base);
    if (matching.length > 0) {
      findings.push(
        _finding(
          "warn",
          "release.retag",
          fill(texts.retag.message, { version: version ?? "", tag: matching[0] }),
          matching[0],
          texts.retag.fix,
        ),
      );
    }
  }
  if (!hasChangelog) {
    // Unrunnable, not inapplicable: there are tags, and nothing to check them against.
    findings.push(
      _skip(
        fill(texts["changelog-absent-tags"].message, { changelog }),
        changelog,
        fill(texts["changelog-absent-tags"].fix, { changelog }),
      ),
    );
    return findings;
  }
  const documented = new Set(_releasedHeadings(headings).map(([, released]) => released));
  for (const tag of releaseTags) {
    if (!documented.has(splitVersion(tag).base)) {
      findings.push(
        _finding(
          "warn",
          "release.undocumented-tag",
          fill(texts["undocumented-tag"].message, { tag, changelog }),
          tag,
          fill(texts["undocumented-tag"].fix, { tag }),
        ),
      );
    }
  }
  return findings;
}

// --------------------------------------------------------------------------------------
// --check
// --------------------------------------------------------------------------------------

/**
 * Run `command` in `cwd` with the terminal streams; the printable form is shown first.
 * @param {string} cwd
 * @param {{printable: string, argv: string[]}[]} commands
 * @returns {string[]} the printable forms of the commands that failed
 */
function _runCommands(cwd, commands) {
  /** @type {string[]} */
  const failed = [];
  for (const { printable, argv } of commands) {
    _out(`== ${printable}`);
    const proc = spawnSync(argv[0], argv.slice(1), { cwd, stdio: "inherit" });
    if (proc.error) {
      throw proc.error;
    }
    if (proc.status !== 0) {
      failed.push(printable);
    }
  }
  return failed;
}

/**
 * `--check`: run the version/changelog cross-check plus the subject's release suite.
 *
 * The akmon subject is refused: its suite is akmon's own Python self-CI and pytest tests.
 * @param {ReleaseData} data
 * @param {string} root
 * @param {string} subject
 * @returns {number} 0 green, 1 failed, 2 refused
 */
export function runCheck(data, root, subject) {
  const texts = data.run_check;
  if (subject === "akmon") {
    process.stderr.write(`${texts.akmon_python_only}\n`);
    return 2;
  }
  const versionFindings = checkReleaseVersions(data, root, subject);
  _out(texts.cross_check_header);
  printFindings(versionFindings);
  _out();

  // package — the project's own suite. Keep verify (the akmon contract still applies), run by
  // the JavaScript CLI of this tree, then defer to the project's documented commands.
  const cli = join(embeddedTreeRoot(), "js", "akmon", "cli.mjs");
  const args = ["--project-root", root, "--strict", "--quiet"];
  const failed = _runCommands(root, [
    { printable: ["akmon", "verify", ...args].join(" "), argv: [process.execPath, cli, "verify", ...args] },
  ]);
  const charter = pyPath(root, _releaseCharter());
  if (isFile(charter)) {
    _out(`\n${fill(texts.charter_runs_note, { charter: _releaseCharter() })}`);
    _out(texts.charter_runs_note_suffix);
  } else {
    _out(`\n${fill(texts.charter_missing_note, { charter: _releaseCharter() })}`);
    failed.push(_releaseCharter());
  }

  if (exitCode(versionFindings)) {
    failed.push(texts.version_check_failed_item);
  }

  _out();
  if (failed.length > 0) {
    _out(texts.failed_header);
    for (const item of failed) {
      _out(fill(texts.failed_item, { item }));
    }
    return 1;
  }
  _out(texts.all_green);
  return 0;
}

// --------------------------------------------------------------------------------------
// --plan
// --------------------------------------------------------------------------------------

/**
 * `tree`'s path from the project root that mounts it, or null when no project mounts it: akmon's
 * own repository is the tree the tag is cut from already, so it takes no `cd` (C130; see the
 * Python).
 * @param {string} tree
 * @returns {string | null}
 */
function _mountPath(tree) {
  const project = findProjectRoot(tree);
  const mount = akmonMount(project);
  if (!isProjectRoot(project) || resolvePath(mount) !== resolvePath(tree)) {
    return null;
  }
  return posix.relative(project, mount);
}

/**
 * The owner-run command set, with the version bump ahead of the staging step. The akmon plan
 * opens with a `cd` into `tree`, the tree the tag is cut from, only when a project mounts it.
 * @param {ReleaseData} data
 * @param {string} version
 * @param {string} subject
 * @param {string} [tree] the akmon tree the tag is cut from (default: the running one)
 * @returns {number}
 */
export function runPlan(data, version, subject, tree = embeddedTreeRoot()) {
  const plan = data.run_plan;
  if (!VERSION_RE.test(version)) {
    process.stderr.write(`${fill(plan.error_version, { version: pyRepr(version) })}\n`);
    return 2;
  }
  const literal = splitVersion(version).base;
  const facts = plan.subjects[subject];
  /** @type {string[]} */
  const lines = [...plan.header, ""];
  if (subject === "akmon") {
    const mount = _mountPath(tree);
    if (mount !== null) {
      lines.push(fill(facts.cd_line, { mount }), "");
    }
    // The plan's version is validated above as vX.Y.Z, so the literal is final and its
    // SemVer spelling is derived by the shared logic, never spelled by hand.
    lines.push(fill(facts.semver_note, { semver: semverSpelling(literal) }));
  }
  lines.push("");
  lines.push(...plan.bump_note.map((/** @type {string} */ line) => fill(line, { literal })));
  if (subject === "akmon") {
    lines.push(...facts.literal_lines.map((/** @type {string} */ line) => fill(line, { literal })));
  } else {
    lines.push(fill(facts.literal_line, { charter: _releaseCharter() }));
  }
  lines.push(fill(plan.changelog_note, { version }));
  lines.push(plan.recheck_note);
  lines.push("");
  lines.push(fill(facts.staged_line, { staged: facts.staged_files }));
  lines.push(plan.git_status_line);
  lines.push("");
  lines.push(fill(plan.commit_line, { subject: facts.commit_subject, version }));
  lines.push(fill(plan.tag_line, { version }));
  lines.push(plan.push_line);
  if (subject === "package") {
    lines.push(`\n${fill(facts.publish_note, { charter: _releaseCharter() })}`);
  }
  lines.push("");
  const cycleNote = Object.hasOwn(facts, "cycle_note") ? facts.cycle_note : plan.cycle_note;
  const semver = semverSpelling(`${literal}.dev0`);
  lines.push(...cycleNote.map((/** @type {string} */ line) => fill(line, { literal, semver })));
  lines.push("");
  lines.push(plan.closing);
  _out(lines.join("\n"));
  return 0;
}

/**
 * Parse the arguments.
 * @param {ReleaseData} data
 * @param {string[]} argv
 * @returns {{projectRoot: string | null, subject: string, state: boolean, plan: string | null, help: boolean} | string}
 *   the options, or the one-line usage error
 */
function _parse(data, argv) {
  try {
    const { values, positionals } = parseArgs({
      args: argv,
      options: {
        "project-root": { type: "string" },
        subject: { type: "string" },
        state: { type: "boolean" },
        check: { type: "boolean" },
        plan: { type: "string" },
        help: { type: "boolean", short: "h" },
      },
      allowPositionals: true,
      strict: true,
    });
    if (values.help === true) {
      return { projectRoot: null, subject: "akmon", state: false, plan: null, help: true };
    }
    // argparse takes no positional here: a stray one is its `unrecognized arguments` refusal.
    if (positionals.length > 0) {
      return `unrecognized arguments: ${positionals.join(" ")}`;
    }
    const subject = values.subject ?? "akmon";
    const allowed = subjects(data);
    if (!allowed.includes(subject)) {
      return `argument --subject: invalid choice: ${pyRepr(subject)} (choose from ${allowed.map((name) => pyRepr(name)).join(", ")})`;
    }
    const modes = [
      ["--state", values.state === true],
      ["--check", values.check === true],
      ["--plan", values.plan !== undefined],
    ].filter(([, given]) => given);
    if (modes.length > 1) {
      return `argument ${modes[1][0]}: not allowed with argument ${modes[0][0]}`;
    }
    return {
      projectRoot: values["project-root"] ?? null,
      subject,
      state: values.state === true,
      plan: values.plan ?? null,
      help: false,
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
 * CLI entry point: dispatch to `--state`/`--check`/`--plan` for the chosen subject.
 * @param {string[]} [argv] the arguments (default: the process's)
 * @returns {number} The process exit code: 0 green, 1 a failed check, 2 on a usage error, a bad
 *   plan version or the refused akmon-subject check.
 */
export function main(argv = process.argv.slice(2)) {
  const data = /** @type {ReleaseData} */ (read(join(embeddedTreeRoot(), "tools", "release", "release.json")));
  const options = _parse(data, argv);
  if (typeof options === "string") {
    process.stderr.write(`${PROG}: error: ${options}\n`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(USAGE);
    return 0;
  }

  if (options.plan) {
    return runPlan(data, options.plan, options.subject);
  }

  const { root, notice } = resolveProjectRoot(options.projectRoot);
  if (notice) {
    process.stderr.write(`${notice}\n`);
  }
  if (options.state) {
    return runState(data, root, options.subject);
  }
  return runCheck(data, root, options.subject);
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
