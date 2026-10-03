/**
 * `akmon check` — run the checks a project declares (ADR 0014 §4, as amended). The JavaScript
 * twin of `common/check_runner.py` (ADR 0020 D01): the same commands, the same scope rule,
 * the same finding per command. The texts, git argv and problem templates come from
 * `common/check_runner.json`, read once at the entry point and passed down as `data` — this
 * module never reads a file itself.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { posix } from "node:path";

import { shlexJoin, shlexSplit } from "./shlex.mjs";
import { fnmatchCase } from "./glob.mjs";
import { codePointSort } from "./sort.mjs";
import { fill } from "./jsondata.mjs";
import { aitnaRootName } from "./project_root.mjs";

const SPEC_KEYS = new Set(["command", "files"]);

/** One `(message, fix)` template pair, as `check_run` carries each outcome. */
/** @typedef {{message: string, fix: string}} RunText */

/**
 * The shape of `common/check_runner.json` — the data file is the owner of these keys.
 *
 * @typedef {object} CheckRunnerData
 * @property {string} config_target
 * @property {string} files_placeholder
 * @property {string[]} default_files
 * @property {{repair_record: string, repair_record_verify: string, correct_entry: string,
 *   no_checks: string, no_checks_fix: string, scope_fix: string,
 *   check_table_ok: string, check_table_ok_fix: string}} check_config
 * @property {{nothing_to_do: RunText, not_installed: RunText, passed: RunText, failed: RunText}} check_run
 * @property {{git_unrunnable: string, git_failed: string}} scope_error
 * @property {string[][]} git_commands
 * @property {{not_table: string, bad_entry: string, unknown_key: string, needs_command: string,
 *   bad_files: string, unsplit_command: string}} problems
 */

/** The target a `check.config` finding names. */
export function configTarget(/** @type {CheckRunnerData} */ data) {
  return data.config_target;
}

/** The placeholder a command replaces with the files a run covers. */
export function filesPlaceholder(/** @type {CheckRunnerData} */ data) {
  return data.files_placeholder;
}

/** The file patterns a check covers when it names none. */
export function defaultFiles(/** @type {CheckRunnerData} */ data) {
  return [...data.default_files];
}

/** The `check.config` fix `akmon check` gives for an unparseable record. */
export function repairRecordFix(/** @type {CheckRunnerData} */ data) {
  return data.check_config.repair_record;
}

/** The `check.config` fix `verify` gives for an unparseable record. */
export function repairRecordVerifyFix(/** @type {CheckRunnerData} */ data) {
  return data.check_config.repair_record_verify;
}

/** The `check.config` fix both `akmon check` and `verify` give for a malformed entry. */
export function correctEntryFix(/** @type {CheckRunnerData} */ data) {
  return data.check_config.correct_entry;
}

/** The `(message, fix)` `akmon check` gives when the record names no checks at all. */
export function noChecks(/** @type {CheckRunnerData} */ data) {
  return [data.check_config.no_checks, data.check_config.no_checks_fix];
}

/** The `check.scope` fix `akmon check` gives when the changed files cannot be listed. */
export function scopeFix(/** @type {CheckRunnerData} */ data) {
  return data.check_config.scope_fix;
}

/** The `(message, fix)` `verify`'s `[check]` table check gives when every entry is sound. */
export function checkTableOk(/** @type {CheckRunnerData} */ data) {
  return [data.check_config.check_table_ok, data.check_config.check_table_ok_fix];
}

/** @typedef {{name: string, argv: string[], files: string[]}} Check */

/**
 * One declared check: a name, the command's argv (placeholder kept) and its file patterns.
 * An empty pattern list takes the check's `default_files` — the same post-init rule the
 * Python dataclass applies.
 */
export function makeCheck(
  /** @type {CheckRunnerData} */ data,
  /** @type {string} */ name,
  /** @type {string[]} */ argv,
  /** @type {string[]} */ files = [],
) {
  return { name, argv, files: files.length ? files : defaultFiles(data) };
}

/** The changed files could not be listed. */
export class ScopeError extends Error {}

function _stringList(/** @type {unknown} */ value) {
  return (
    Array.isArray(value) && value.length > 0 && value.every((/** @type {unknown} */ item) => typeof item === "string")
  );
}

// The reader hands a TOML table over as a plain object (a null-prototype one, so a test on
// `constructor` would reject it), and everything else a value can be — a string, a number, a
// date — is `typeof "object"` or a bare primitive. Naming the object tag is what separates a
// table from a `TomlDate`, and a date read as a table is a `[check]` entry that quietly
// contributes nothing: the empty object it enumerates as has no keys to complain about.
function _isTable(/** @type {unknown} */ value) {
  return Object.prototype.toString.call(value) === "[object Object]";
}

function _jsRepr(/** @type {string} */ value) {
  return `'${value}'`;
}

/**
 * The checks the record's `[check]` table declares, and every problem found in it.
 * Strict: a malformed entry is reported and skipped, never guessed at.
 *
 * @param {CheckRunnerData} data the parsed `common/check_runner.json`
 * @param {unknown} table the record's `[check]` table — unknown because a non-table is
 *   one of the answers this reader must report, not a caller error
 * @returns {{checks: Check[], problems: string[]}}
 */
export function readChecks(data, table) {
  if (table === null || table === undefined) {
    return { checks: [], problems: [] };
  }
  const problems_data = data.problems;
  if (!_isTable(table)) {
    return { checks: [], problems: [problems_data.not_table] };
  }
  /** @type {Check[]} */ const checks = [];
  /** @type {string[]} */ const problems = [];
  for (const [name, value] of Object.entries(/** @type {Record<string, unknown>} */ (table))) {
    const spec =
      typeof value === "string" ? { command: value } : /** @type {Record<string, unknown>} */ (value);
    if (!_isTable(spec)) {
      problems.push(fill(problems_data.bad_entry, { name: String(name) }));
      continue;
    }
    const unknown = codePointSort([...new Set(Object.keys(spec).filter((key) => !SPEC_KEYS.has(key)))]);
    if (unknown.length) {
      problems.push(fill(problems_data.unknown_key, { name: String(name), key: _jsRepr(unknown[0]) }));
      continue;
    }
    const command = spec.command;
    const files = spec.files;
    if (typeof command !== "string" || command.trim() === "") {
      problems.push(fill(problems_data.needs_command, { name: String(name) }));
      continue;
    }
    if (!_stringList(files === undefined ? defaultFiles(data) : files)) {
      problems.push(fill(problems_data.bad_files, { name: String(name) }));
      continue;
    }
    let argv;
    try {
      argv = shlexSplit(command);
    } catch (error) {
      // The message is spec: `unsplit_command` is filled with it, and the Python twin fills
      // the same template with `str(ValueError)` — the bare message, not the class name.
      problems.push(
        fill(problems_data.unsplit_command, { name: String(name), error: /** @type {Error} */ (error).message }),
      );
      continue;
    }
    checks.push(makeCheck(data, String(name), argv, /** @type {string[]} */ (files)));
  }
  return { checks, problems };
}

/**
 * The exit status of a finished child, in the spelling `subprocess.run` reports: a process the
 * kernel killed has no status, and its answer is the negative signal number. `spawnSync` splits
 * the two across `status` and `signal`, and a bare `null` in a finding reads as "exited null".
 * Only a child that actually ran reaches this — a spawn that failed has an `error`, which both
 * callers answer before asking for a status.
 * @param {{status: number | null, signal: string | null}} result
 * @returns {number}
 */
function _exitStatus(result) {
  if (result.status !== null) {
    return result.status;
  }
  const killed = os.constants.signals[/** @type {keyof typeof os.constants.signals} */ (result.signal)];
  if (killed === undefined) {
    throw new TypeError(`no exit status and an unknown signal ${String(result.signal)}`);
  }
  return -killed;
}

/**
 * Files that differ from `HEAD` or are new and not ignored — never the dev layer.
 * The message names the git command and its outcome, never the interpreter's exception
 * text: it is spec shared with the Python implementation (ADR 0020 D03).
 *
 * @param {CheckRunnerData} data the parsed `common/check_runner.json`
 * @param {string} root
 * @returns {string[]}
 */
export function changedFiles(data, root) {
  /** @type {string[]} */ const names = [];
  for (const args of data.git_commands) {
    const command = "git " + args.filter((arg) => arg !== "-z").join(" ");
    // This one capture is on purpose — the names are the answer — but `spawnSync` caps a captured
    // stream at 1 MiB and reports ENOBUFS as a failure to run, which on a repository with tens of
    // thousands of changed files would say "git is not runnable". The limit is raised, not removed:
    // `subprocess.run` in the twin has none.
    const result = spawnSync("git", ["-C", root, ...args], {
      encoding: "utf-8",
      maxBuffer: 256 * 1024 * 1024,
    });
    if (result.error !== undefined && result.error !== null) {
      throw new ScopeError(
        fill(data.scope_error.git_unrunnable, {
          reason: /** @type {{code?: string}} */ (result.error).code ?? "not runnable",
        }),
      );
    }
    const status = _exitStatus(result);
    if (status !== 0) {
      throw new ScopeError(
        fill(data.scope_error.git_failed, {
          command,
          returncode: String(status),
        }),
      );
    }
    for (const name of (/** @type {string} */ (result.stdout) || "").split("\0")) {
      if (name) {
        names.push(name);
      }
    }
  }
  const devLayer = `${aitnaRootName()}/`;
  const kept = new Set(
    names.filter((name) => !name.startsWith(devLayer) && fs.existsSync(posix.join(root, name))),
  );
  return codePointSort([...kept]);
}

/**
 * The argv one run executes, or `null` when `--changed` left it nothing to check.
 *
 * @param {CheckRunnerData} data the parsed `common/check_runner.json`
 * @param {Check} check
 * @param {string[] | null} changed
 * @returns {string[] | null}
 */
export function argvFor(data, check, changed) {
  const placeholder = filesPlaceholder(data);
  if (!check.argv.includes(placeholder)) {
    return [...check.argv];
  }
  /** @type {string[]} */ let files;
  if (changed === null) {
    files = ["."];
  } else {
    files = changed.filter((name) => check.files.some((pattern) => fnmatchCase(name, pattern)));
    if (files.length === 0) {
      return null;
    }
  }
  /** @type {string[]} */ const argv = [];
  for (const part of check.argv) {
    if (part === placeholder) {
      argv.push(...files);
    } else {
      argv.push(part);
    }
  }
  return argv;
}

/** @typedef {{severity: string, code: string, message: string, target: string, fix: string}} CheckFinding */

/**
 * Whether a spawn failure is the command being absent (Python's `FileNotFoundError`, which the
 * twin catches and reports) rather than something the reporter has no business renaming.
 * @param {unknown} error
 * @returns {boolean}
 */
function isMissingCommand(error) {
  return (/** @type {{code?: string} | null} */ (error)?.code) === "ENOENT";
}

/**
 * The `check.run` finding for a command that is not on PATH.
 * @param {RunText} notInstalled the `check_run.not_installed` templates
 * @param {string} command the argv entry the runner could not execute
 * @param {string} target the finding's `[check].<name>` target
 * @returns {CheckFinding}
 */
function missingCommand(notInstalled, command, target) {
  return {
    severity: "error",
    code: "check.run",
    message: fill(notInstalled.message, { command }),
    target,
    fix: fill(notInstalled.fix, { command, target }),
  };
}

/** The directory a check command runs in. @typedef {{cwd: string}} RunOptions */
/** What a runner reports back: the exit status, or the spawn failure. @typedef {{returncode: number | null, error?: unknown}} RunResult */
/** One command execution, swappable in tests. @typedef {(argv: string[], options: RunOptions) => RunResult} Runner */

/**
 * Run every check in declaration order; the command's own output goes straight through.
 *
 * The findings are plain five-field objects: the envelope twin (`common/findings.mjs`) lands
 * with C105, and this runner core returns the fields that envelope would validate.
 *
 * @param {CheckRunnerData} data the parsed `common/check_runner.json`
 * @param {string} root
 * @param {Check[]} checks
 * @param {string[] | null} changed
 * @param {Runner} [runner]
 * @returns {CheckFinding[]}
 */
export function runChecks(data, root, checks, changed, runner) {
  // `stdio: "inherit"`, not a capture: the command's own report is what the owner reads, and it
  // is the reason this function returns findings instead of output. A captured run hides that
  // report and dies with ENOBUFS once a linter prints more than the 1 MiB pipe holds — and the
  // failure then reads as the command not being installed, which is wrong twice over: the binary
  // is there, and the output it did write is thrown away.
  /** @param {string[]} argv @returns {RunResult} */
  const run = (argv) =>
    runner !== undefined
      ? runner(argv, { cwd: root })
      : (() => {
          const result = spawnSync(argv[0], argv.slice(1), { cwd: root, stdio: "inherit" });
          if (result.error !== undefined && result.error !== null) {
            return { returncode: null, error: result.error };
          }
          return { returncode: _exitStatus(result), error: undefined };
        })();
  /** @type {CheckFinding[]} */ const findings = [];
  const runs = data.check_run;
  for (const check of checks) {
    const target = `[check].${check.name}`;
    const argv = argvFor(data, check, changed);
    if (argv === null) {
      const nothing = runs.nothing_to_do;
      findings.push({ severity: "ok", code: "check.run", message: nothing.message, target, fix: nothing.fix });
      continue;
    }
    let result;
    try {
      result = run(argv);
    } catch (error) {
      // The one failure a check reports as its own finding is the missing command (Python's
      // `FileNotFoundError`); anything else the runner cannot explain is a bug in the runner,
      // and reporting it as "not installed" would send the owner looking for a binary.
      if (!isMissingCommand(error)) {
        throw error;
      }
      findings.push(missingCommand(runs.not_installed, argv[0], target));
      continue;
    }
    if (result.error !== undefined && result.error !== null) {
      if (!isMissingCommand(result.error)) {
        throw result.error;
      }
      findings.push(missingCommand(runs.not_installed, argv[0], target));
      continue;
    }
    if (result.returncode === 0) {
      const passed = runs.passed;
      findings.push({
        severity: "ok",
        code: "check.run",
        message: fill(passed.message, { command: shlexJoin(argv) }),
        target,
        fix: passed.fix,
      });
    } else {
      const failed = runs.failed;
      findings.push({
        severity: "error",
        code: "check.run",
        message: fill(failed.message, { command: shlexJoin(argv), returncode: String(result.returncode) }),
        target,
        fix: failed.fix,
      });
    }
  }
  return findings;
}
