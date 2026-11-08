/**
 * Vendor-neutral akmon hook decisions — the JavaScript twin of `hooks/hook_core.py` (ADR 0020
 * D01). This module contains the guardrail logic only: the vendor entry points adapt their
 * incoming payload and serialize `HookResult` into the shape their runtime expects. The Python
 * module is the spec: the same answers, the same texts, byte for byte, the same exceptions by
 * class name (the crash handler prints `type(exc).__name__`).
 *
 * Data (the C102/C104 convention): this module never reads a shared file itself. Every function
 * whose Python twin reads a data file or a marker — directly or through a callee — takes the
 * bundle of `hook_data.mjs` as its first parameter, `data`; the other functions have none. Each
 * file of the bundle is read on first access, so a broken one fails only the hooks that reach it.
 *
 * Signatures: a Python positional parameter stays positional (camelCase), a keyword-only one
 * moves into a trailing options object (`{permissionMode}`, `{isSubagent}`); a dataclass becomes
 * a frozen class whose constructor takes ONE options object; a `Path` is a string spelled as
 * `str(Path)` spells it (`pyPath`).
 *
 * Twin notes — every place the stdlib answers differently from Node's:
 * - the command guards' patterns are `re.ASCII` on the Python side (`\b` is ASCII here); the
 *   `co-authored-by` pattern stays `IGNORECASE` only, which is ASCII-only for its letters (none
 *   has a non-ASCII case partner), and JavaScript's non-Unicode `i` flag never folds across the
 *   ASCII boundary either;
 * - `Path` normalization, `os.path.normpath`, `relative_to` and `suffix` have no Node twin: the
 *   small ports below are pinned in `hook_core.test.mjs` on `""`, `.`, `..`, `//x`, `///x`, a
 *   trailing and a duplicate `/`, and `a/./b`;
 * - a payload value reaches `re.search`/`Path`/`.get` untyped in Python and raises by class
 *   (`TypeError`, `AttributeError`); the same raises are spelled with `pyError` here;
 * - `Path.resolve()` of a path holding NUL raises `ValueError` (it is not an `OSError`, so no
 *   handler swallows it), where Node reports an argument error — `_resolve` re-raises as Python;
 * - the drift counter file holds `"{seen} {score}"` with the score spelled as a Python float
 *   (`1.0`, `0.5`, `2.5`, `1e+16`), read back with `int()`/`float()` (`pyIntBig`/`pyFloat`:
 *   whitespace, `+`, `_`, other scripts' digits), and the score in a message is `f"{score:g}"`
 *   (`formatG`: six significant digits, half to even on the exact binary value);
 * - `tempfile.gettempdir()` is `gettempdir` of `markers.mjs`, asked once per call as Python's
 *   cache makes it; the counter and marker files are written by `write_text` (UTF-8, no fsync)
 *   with `OSError` — and only that — suppressed;
 * - `subprocess.run(["git", …])` is a `spawnSync` loaded where it is used, so a hook that never
 *   asks for the branch never pays for `node:child_process`.
 */

import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import pathModule from "node:path";

import { DataFileError, fill } from "../common/jsondata.mjs";
import { FloatValue, hookForm } from "../common/json_writer.mjs";
import {
  claimDiagnosticMarker,
  delegationStateName,
  gettempdir,
  markerKind,
  unidentifiedIdentity,
} from "../common/markers.mjs";
import { staleMaterialized } from "../common/materialization.mjs";
import {
  AITNA_ROOT_DEFAULT,
  aitnaRootName,
  findProjectRoot,
  locateProjectRoot,
  resolvePath,
} from "../common/project_root.mjs";
import {
  pyError,
  pyTypeName,
  dictItem,
  pyContains,
  pyFloat,
  pyIntBig,
  pyRepr,
  pyStrip,
  pyPath,
  isOSError,
  pyStat,
  isDir,
  isFile,
  readText,
  writeText,
  unlinkMissingOk,
  decodeUtf8,
  exceptionClassName,
} from "../common/pyvalue.mjs";
import { codePointSort } from "../common/sort.mjs";
import {
  ACTORS,
  AI_TRAILER_CLASS,
  outcome as accessOutcome,
  isOwnBranch,
  isProtectedBranch,
  OUTCOMES,
  protectedBranches,
} from "../common/access_matrix.mjs";
import { fileFormat, writeReason as settingsWriteReason } from "../common/harness_settings.mjs";
import { resolve as resolveWorkStyle } from "../common/work_style.mjs";
import { TREE_ROOT } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */
/** @typedef {import("../common/access_matrix.mjs").Actor} Actor */

export { aitnaRootName, findProjectRoot, locateProjectRoot };

/**
 * The fields of a {@link HookResult}; only `eventName` is required.
 * @typedef {object} HookResultInit
 * @property {string} eventName
 * @property {string | null} [additionalContext]
 * @property {string | null} [permissionDecision]
 * @property {string | null} [permissionReason]
 * @property {string | null} [systemMessage]
 * @property {string | null} [decision]
 * @property {string | null} [reason]
 */

// --------------------------------------------------------------------------------------
// The tree this hook runs from
// --------------------------------------------------------------------------------------

/**
 * `Path.resolve()` as the hook-side callers need it: a path with an embedded NUL raises
 * `ValueError` in Python — not an `OSError`, so no handler below swallows it — and one with a
 * lone surrogate `UnicodeEncodeError`. (A surrogate in U+DC80–U+DCFF is a raw byte to Python and
 * U+FFFD to Node: not reproduced.)
 * @param {string} path
 * @returns {string}
 */
function _resolve(path) {
  assertEncodablePath(path);
  return resolvePath(path);
}

/**
 * Runtime files used by hooks: **the tree this hook is executing from**.
 *
 * Each carrier ships a hook and its data together, so the hook's own location answers the
 * question without asking anything: the mounted tree when the wiring named a file there, and
 * the wheel's embedded `akmon/_tree` (or the npm package's tree) when the wiring called
 * `akmon hook` (C77). No record read, no directory probe, and no way for the two to disagree.
 *
 * `projectRoot` stays in the signature: the project overlay it locates
 * (`<dev root>/model-routing.json`) is still layered onto whatever registry this tree
 * carries, and callers pass the pair together.
 * @param {string} projectRoot
 * @returns {string}
 */
export function akmonRuntimeRoot(projectRoot) {
  void projectRoot; // the carrier answers; the project only supplies the overlay on top of it
  return TREE_ROOT;
}

/**
 * How to *spell* the runtime tree in something an agent will run: project-relative when the
 * executing tree **is the project's mount**, `$(akmon path)` otherwise. The test is "is it the
 * mount", deliberately, not "is it somewhere under the project root" — the wheel's tree sits
 * under the root in `.venv/lib/python3.x/site-packages`, and a containment test would spell the
 * recovery command with the venv's interpreter version in it.
 * @param {string} projectRoot
 * @returns {string}
 */
export function runtimeRootDisplay(projectRoot) {
  const mount = pyPath(projectRoot, aitnaRootName(projectRoot), "akmon");
  try {
    if (_resolve(akmonRuntimeRoot(projectRoot)) === _resolve(mount)) {
      return `${aitnaRootName(projectRoot)}/akmon`;
    }
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
  }
  return "$(akmon path)";
}

/** A hook's decision, vendor-neutral, ready for an adapter to serialize. */
export class HookResult {
  /**
   * @param {HookResultInit} fields
   */
  constructor({
    eventName,
    additionalContext = null,
    permissionDecision = null,
    permissionReason = null,
    systemMessage = null,
    decision = null,
    reason = null,
  }) {
    this.eventName = eventName;
    this.additionalContext = additionalContext;
    this.permissionDecision = permissionDecision;
    this.permissionReason = permissionReason;
    this.systemMessage = systemMessage;
    /** A turn-level decision (`Stop`): `block` holds the turn, with `reason` as the one thing the
     * model is asked to do before it may end the turn again. */
    this.decision = decision;
    this.reason = reason;
    Object.freeze(this);
  }
}

// --------------------------------------------------------------------------------------
// The crash report
// --------------------------------------------------------------------------------------

/**
 * The one stderr line a crashed entry point writes (ADR 0013 F3): the hook and the class.
 *
 * Never the exception's message — it routinely carries a path, a key or a payload fragment.
 * The text stays in code, not in `hook_core.json` (C102 review F1): the crash path must not
 * depend on a data file, since a missing or broken one is exactly what it reports.
 *
 * Runtime classification: operational
 * Rationale: crash posture (ADR 0013 F3), not a guardrail policy — it reports that a hook failed
 * and authors no rule of its own. An adapter renders it into the hook process's stderr, so it
 * reaches the owner from outside the `*Result` join, where ADR-0012/D07 requires the
 * classification to be stated rather than left silent.
 * @param {string} hookName
 * @param {unknown} exc
 * @returns {string}
 */
export function hookFailureDiagnostic(hookName, exc) {
  return `akmon ${hookName} hook: ${exceptionClassName(exc)}`;
}

/**
 * What the owner is told when an entry point crashed (C87, ADR-0013/D01): the fact, then the command.
 *
 * The same two facts as {@link hookFailureDiagnostic} and nothing from the exception's text.
 * It is written inside a crash handler, so nothing it reads can raise out of it — the dev-layer
 * name is looked up from `start` (default: the cwd) and falls back to the default name when
 * that lookup itself fails, and the text is code, not data.
 *
 * Runtime classification: operational
 * Rationale: the owner-facing half of the same crash report (ADR-0013/D01) — it states that a
 * hook was skipped and names the recovery command, and authors no guardrail rule. An adapter
 * renders it into the vendor's owner channel, so ADR-0012/D07 requires this classification on it
 * even though it sits outside the `*Result` join.
 * @param {string} hookName
 * @param {unknown} exc
 * @param {string | null} [start]
 * @returns {string}
 */
export function hookFailureNotice(hookName, exc, start = null) {
  let devName = AITNA_ROOT_DEFAULT;
  try {
    devName = aitnaRootName(locateProjectRoot(start));
  } catch {
    // the lookup itself failed: the default name stands, the crash report must not crash
  }
  return (
    `⚠ akmon: the ${hookName} hook failed (${exceptionClassName(exc)}) and was skipped — this action ` +
    `went ahead without it. Check the setup: \`akmon verify\` (a mounted tree: ` +
    `\`python3 ${devName}/akmon/bin/verify.py\`).`
  );
}

// --------------------------------------------------------------------------------------
// Vocabulary and data lookups
// --------------------------------------------------------------------------------------

/**
 * One key of `hooks/hook_core.json`; a miss raises `KeyError`.
 * @param {HookData} data
 * @param {string} key
 * @returns {any}
 */
function _core(data, key) {
  return dictItem(data.core, key);
}

/**
 * One neutral tool-kind token by stem (the table is owned by hooks/vocabulary.json, C102).
 * @param {HookData} data
 * @param {string} stem
 * @returns {string}
 */
export function neutralKind(data, stem) {
  return dictItem(dictItem(data.vocabulary, "neutral_kinds"), stem);
}

/**
 * The neutral edit-tool kind every vendor adapter normalizes to.
 *
 * Runtime classification: operational
 * Rationale: a data lookup (hooks/vocabulary.json, C102) — it resolves the token the adapters
 * compare against and renders no text of its own; what is said is owned by the caller.
 * @param {HookData} data
 * @returns {string}
 */
export function editTool(data) {
  return neutralKind(data, "edit");
}

/**
 * The neutral shell/command-tool kind.
 *
 * Runtime classification: operational
 * Rationale: a data lookup (hooks/vocabulary.json, C102) — see {@link editTool}.
 * @param {HookData} data
 * @returns {string}
 */
export function shellTool(data) {
  return neutralKind(data, "shell");
}

/**
 * The neutral read/sweep-tool kind.
 *
 * Runtime classification: operational
 * Rationale: a data lookup (hooks/vocabulary.json, C102) — see {@link editTool}.
 * @param {HookData} data
 * @returns {string}
 */
export function readTool(data) {
  return neutralKind(data, "read");
}

/**
 * The neutral subagent-delegation kind.
 *
 * Runtime classification: operational
 * Rationale: a data lookup (hooks/vocabulary.json, C102) — it resolves the token the core
 * compares against and renders no text of its own; what is said is owned by the caller.
 * @param {HookData} data
 * @returns {string}
 */
export function subagentTool(data) {
  return neutralKind(data, "subagent");
}

/**
 * The path-classification segments with the configured dev-layer root filled in. They match
 * lowercased path *substrings*, so the segment uses the lowercased root name.
 * @param {HookData} data
 * @param {string} key the `hook_core.json` list to fill
 * @param {string | null} root the project, or `null` for the one found from the cwd
 * @returns {string[]}
 */
function _segments(data, key, root) {
  const aitna = aitnaRootName(root === null ? locateProjectRoot() : root).toLowerCase();
  return /** @type {string[]} */ (_core(data, key)).map((segment) => fill(segment, { aitna }));
}

/**
 * The once-per-session stderr line for a shell call no advisory can classify (C102).
 * @param {HookData} data
 * @returns {string}
 */
export function unclassifiedShellRouteNotice(data) {
  return _core(data, "unclassified_shell_route_notice");
}

/**
 * Say once per session that a shell call has effects the advisories cannot classify.
 *
 * The advisories key off a path; a shell call carries a command, and reading a path out of a
 * command string is a guess — so this route is *reported*, never classified. It states the
 * route's capability, not a guessed effect (C49).
 *
 * Vendor-neutral by ADR-0012/D02: the blind spot is not Codex's. On Claude the same effect
 * reaches the filesystem through `Bash` while the advisories sit on the edit tools. Both
 * vendors emit one message from one implementation, because two copies of a diagnostic are two
 * things that can drift into disagreeing about what akmon can see.
 *
 * Never blocks and never becomes model context: every caller keeps its exit code.
 *
 * Runtime classification: operational
 * Rationale: it reports a *gap* in what the advisories can see, which is the opposite of
 * enforcing a rule — no guardrail subset is claimed. It writes to stderr itself, so
 * ADR-0012/D07 puts it among the owner-visible callables outside the join that must say what
 * they are.
 * @param {HookData} data
 * @param {string | null} sessionId
 * @returns {void}
 */
export function reportUnclassifiedShellRoute(data, sessionId) {
  if (claimDiagnosticMarker(data.markers, markerKind(data.markers, "shell_route"), sessionId)) {
    process.stderr.write(`${unclassifiedShellRouteNotice(data)}\n`);
  }
}

// --------------------------------------------------------------------------------------
// The commit and privilege guards
// --------------------------------------------------------------------------------------

/**
 * Current branch name, or `""` when it cannot be determined.
 * @returns {string}
 */
export function currentGitBranch() {
  const { spawnSync } = /** @type {typeof import("node:child_process")} */ (
    createRequire(import.meta.url)("node:child_process")
  );
  const result = spawnSync("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
    stdio: ["inherit", "pipe", "pipe"],
    timeout: 5000,
  });
  if (result.error !== undefined) {
    return ""; // no git, a timeout, a missing cwd: the SubprocessError/OSError of the twin
  }
  return pyStrip(decodeUtf8(result.stdout));
}

// ask->deny escalation for an unattended run (C31, ADR-0006/D02, narrowed by ADR-0025/D06). A live
// test showed a hook-forced `ask` is a silent no-op -- no prompt, no block -- in a Claude Code
// background/child session, so an ask that nobody can answer becomes a hard `deny`, the one
// decision every vendor is confirmed to enforce unconditionally. Who attends is read from what the
// host states: Claude Code sets `CLAUDE_CODE_SESSION_ATTENDED` (the adapter reads it at the entry
// point and hands it down as `attended`; M199, M200). Where the host states nothing, only the
// interactive `default` permission mode attends. A mode that skips every question never does.

/**
 * Whether a hook's `ask` reaches an owner who can answer it (ADR-0025/D06).
 *
 * `attended` is the host's own statement (`CLAUDE_CODE_SESSION_ATTENDED`: `true` for `1`, `false`
 * for `0`), or `null` where it states nothing; the permission mode then decides, as it did
 * before. A mode that skips every question is never attended, whatever `attended` says.
 * @param {HookData} data
 * @param {string | null} permissionMode
 * @param {{attended?: boolean | null}} [options]
 * @returns {boolean}
 */
export function askIsAttended(data, permissionMode, { attended = null } = {}) {
  if (
    /** @type {string[]} */ (_core(data, "unattended_permission_modes")).includes(
      /** @type {string} */ (permissionMode),
    )
  ) {
    return false;
  }
  if (attended !== null) {
    return attended;
  }
  return permissionMode === _core(data, "interactive_default_permission_mode");
}

/** The attendance value as the host spells it, or `unset` where it stated nothing. */
const _ATTENDED_LABELS = new Map([
  [true, "1"],
  [false, "0"],
  [null, "unset"],
]);

/**
 * @param {HookData} data
 * @param {HookResult} result
 * @param {string | null} permissionMode
 * @param {boolean | null} attended
 * @returns {HookResult}
 */
function _escalateUnattendedAsk(data, result, permissionMode, attended) {
  if (result.permissionDecision !== "ask" || askIsAttended(data, permissionMode, { attended })) {
    return result;
  }
  const suffix = fill(_core(data, "escalated_ask_suffix"), {
    permission_mode: pyRepr(permissionMode),
    attended: /** @type {string} */ (_ATTENDED_LABELS.get(attended)),
  });
  return new HookResult({
    eventName: result.eventName,
    additionalContext: result.additionalContext,
    permissionDecision: "deny",
    permissionReason: `${result.permissionReason} ${suffix}`,
    systemMessage: result.systemMessage,
  });
}

/**
 * The argument check `re.search` makes of its subject.
 * @param {unknown} text
 * @returns {string}
 */
function _subject(text) {
  if (typeof text !== "string") {
    throw pyError("TypeError", `expected string or bytes-like object, got '${pyTypeName(text)}'`);
  }
  return text;
}

// ``re.ASCII`` on the Python side: ``\b`` here is ASCII-only.
const _SUDO_RE = /\bsudo\b/;

/**
 * Deny any Bash command that invokes `sudo`, and one that writes a harness settings file, unconditionally.
 *
 * The agent runs as an unprivileged user by design; a command reaching for `sudo` is either
 * probing for elevated access or trying to route around a permission boundary that exists on
 * purpose (e.g. a root-owned file). Neither is something the agent decides for itself — if
 * elevated access is genuinely needed, the owner runs it themselves. No ask: the answer does not
 * depend on session attentiveness, so there is nothing to escalate.
 *
 * The same rule covers the actor's carrier (ADR 0031/D07, D-C203-ACTOR-WRITE): a harness settings
 * file's `env` reaches the hook process (M239), so a command whose words write one of those files —
 * an output redirection, `tee`, `sed -i`/`perl -i`, a `cp`/`mv`/`install` destination, `dd of=` —
 * is denied, for every actor; reading one passes. Only command words are read, never a quoted
 * argument or a heredoc body. `directory` is where the command starts (default: the process's).
 * The edit tools' half of the rule is the `settings-env-guard` hook (`common/harness_settings.mjs`).
 *
 * Policy ID: privilege.no-escalation
 * @param {HookData} data
 * @param {unknown} command
 * @param {string | null} [directory]
 * @returns {HookResult | null}
 */
export function privilegeEscalationGuardResult(data, command, directory = null) {
  if (_SUDO_RE.test(_subject(command))) {
    return new HookResult({
      eventName: "PreToolUse",
      permissionDecision: "deny",
      permissionReason: _core(data, "privilege_escalation_reason"),
    });
  }
  const reason = _settingsWriteReason(
    data,
    /** @type {string} */ (command),
    directory === null ? _workingDirectory() : directory,
  );
  if (reason === null) {
    return null;
  }
  return new HookResult({ eventName: "PreToolUse", permissionDecision: "deny", permissionReason: reason });
}

// --------------------------------------------------------------------------------------
// The commit guard: which repository a command acts on (C190, ADR-0029/D09)
// --------------------------------------------------------------------------------------

/**
 * One `git`, `gh` or `glab` command found in a shell command: its subcommand, its arguments, and where it
 * runs. `arguments` are the words after the subcommand, quotes removed. `directory` is `null` when
 * the place cannot be told from the text (a `$` expansion, a `GIT_DIR` assignment, `--git-dir`,
 * `cd -`). `program` is `git`, `gh` or `glab`; a forge subcommand is its group and action as one string
 * (`pr create`); `gh api` and `glab api` keep every word after `api`. `configOverride` is `true` for a
 * `git` carrying `-c` or `--config-env`: the command runs under configuration the text does not show.
 */
export class GitInvocation {
  /**
   * @param {{subcommand: string, directory: string | null, arguments?: string[], program?: string, configOverride?: boolean}} fields
   */
  constructor({ subcommand, directory, arguments: words = [], program = "git", configOverride = false }) {
    this.subcommand = subcommand;
    this.directory = directory;
    this.arguments = Object.freeze([...words]);
    this.program = program;
    this.configOverride = configOverride;
    Object.freeze(this);
  }
}

/**
 * What the guard needs of the repository at a directory: a linked worktree or not, and its
 * branch (`""` on a detached `HEAD`).
 */
export class RepositoryFacts {
  /**
   * @param {{linked: boolean, branch: string}} fields
   */
  constructor({ linked, branch }) {
    this.linked = linked;
    this.branch = branch;
    Object.freeze(this);
  }
}

/**
 * A shell word after quote removal; `operand` is `false` for the target of a redirection, and
 * `write` is `true` for the target of an output redirection (`>`, `>>`, `>|`, `&>`), which opens
 * its file for writing.
 * @typedef {object} ShellWord
 * @property {string} value
 * @property {boolean} expands
 * @property {ShellUnit[][]} substitutions
 * @property {boolean} operand
 * @property {boolean} write
 */

/**
 * A simple command, or a parenthesized subshell (a directory change inside it does not leave it).
 * @typedef {{kind: "command", words: ShellWord[]} | {kind: "group", script: ShellUnit[]}} ShellUnit
 */

/**
 * The word being read: its text so far, whether it was started, whether a `$` was met.
 */
class _WordBuilder {
  constructor() {
    /** @type {string[]} */
    this.parts = [];
    this.started = false;
    this.expands = false;
    /** @type {ShellUnit[][]} */
    this.substitutions = [];
  }

  /** @param {string} text */
  add(text) {
    this.parts.push(text);
    this.started = true;
  }
}

/** One script being read: the finished units, the command's words, the word under way. */
class _Frame {
  constructor() {
    /** @type {ShellUnit[]} */
    this.units = [];
    /** @type {ShellWord[]} */
    this.words = [];
    this.builder = new _WordBuilder();
  }
}

const _DIGITS_RE = /^[0-9]+$/;
const _ASSIGNMENT_RE = /^[A-Za-z_][A-Za-z0-9_]*=/;
// Words a command word may hide behind: a wrapper that runs the next command, and the shell
// keywords that open a command (`then git commit`).
const _WRAPPERS = new Set([
  "env",
  "command",
  "time",
  "nohup",
  "exec",
  "!",
  "{",
  "}",
  "if",
  "then",
  "else",
  "elif",
  "do",
  "while",
  "until",
]);
const _SHELLS = new Set(["bash", "sh", "zsh", "dash"]);
const _ENVIRONMENT_REPOSITORY = new Set(["GIT_DIR", "GIT_WORK_TREE"]);

/**
 * Reads shell text into scripts of simple commands, with no filesystem and no execution.
 *
 * It splits on unquoted `; & | newline` and parentheses, honours quotes and backslashes, skips
 * heredoc bodies, and reads `$(...)` and backticks as scripts of their own. It is the reading of a
 * command's *words* — what only a command word may be — not a shell.
 */
class _Parser {
  /** @param {string} text */
  constructor(text) {
    this._text = text;
    this._pos = 0;
    /** @type {Array<[string, boolean]>} */
    this._heredocs = [];
    this._redirectTargetNext = false;
    this._redirectWriteNext = false;
  }

  /**
   * Read to the end of the text, or, when `nested`, to the `)` that closes it.
   * @param {boolean} nested
   * @returns {ShellUnit[]}
   */
  script(nested) {
    const frame = new _Frame();
    const text = this._text;
    while (this._pos < text.length) {
      const char = text[this._pos];
      if (char === " " || char === "\t") {
        this._pos += 1;
        this._endWord(frame);
      } else if (char === "\n") {
        this._pos += 1;
        this._endCommand(frame);
        this._skipHeredocs();
      } else if (char === ";" || char === "&" || char === "|") {
        this._pos += 1;
        this._endCommand(frame);
      } else if (char === "(") {
        this._pos += 1;
        this._endCommand(frame);
        frame.units.push({ kind: "group", script: this.script(true) });
      } else if (char === ")") {
        this._pos += 1;
        this._endCommand(frame);
        if (nested) {
          return frame.units;
        }
      } else if (char === "#" && !frame.builder.started) {
        const end = text.indexOf("\n", this._pos);
        this._pos = end < 0 ? text.length : end;
      } else if (char === "<" || char === ">") {
        this._redirect(frame);
      } else {
        this._wordCharacter(frame);
      }
    }
    this._endCommand(frame);
    return frame.units;
  }

  /** @param {_Frame} frame */
  _endWord(frame) {
    const builder = frame.builder;
    if (builder.started) {
      frame.words.push({
        value: builder.parts.join(""),
        expands: builder.expands,
        substitutions: builder.substitutions,
        operand: !this._redirectTargetNext,
        write: this._redirectTargetNext && this._redirectWriteNext,
      });
      this._redirectTargetNext = false;
      this._redirectWriteNext = false;
    }
    frame.builder = new _WordBuilder();
  }

  /** @param {_Frame} frame */
  _endCommand(frame) {
    this._endWord(frame);
    this._redirectTargetNext = false;
    this._redirectWriteNext = false;
    if (frame.words.length > 0) {
      frame.units.push({ kind: "command", words: frame.words });
      frame.words = [];
    }
  }

  /** @param {_Frame} frame */
  _wordCharacter(frame) {
    const text = this._text;
    const builder = frame.builder;
    const char = text[this._pos];
    if (char === "\\") {
      const following = text.slice(this._pos + 1, this._pos + 2);
      if (following !== "" && following !== "\n") {
        builder.add(following);
      }
      this._pos += following === "" ? 1 : 2;
    } else if (char === "'") {
      let end = text.indexOf("'", this._pos + 1);
      end = end < 0 ? text.length : end;
      builder.add(text.slice(this._pos + 1, end));
      this._pos = end + 1;
    } else if (char === '"') {
      this._doubleQuoted(builder);
    } else if (char === "$") {
      this._dollar(builder);
    } else if (char === "`") {
      this._backtick(builder);
    } else {
      builder.add(char);
      this._pos += 1;
    }
  }

  /** @param {_WordBuilder} builder */
  _doubleQuoted(builder) {
    const text = this._text;
    builder.add("");
    this._pos += 1;
    while (this._pos < text.length) {
      const char = text[this._pos];
      if (char === '"') {
        this._pos += 1;
        return;
      }
      if (char === "\\") {
        const following = text.slice(this._pos + 1, this._pos + 2);
        if (following !== "" && '"\\$`'.includes(following)) {
          builder.add(following);
          this._pos += 2;
        } else if (following === "\n") {
          this._pos += 2;
        } else {
          builder.add(char);
          this._pos += 1;
        }
      } else if (char === "$") {
        this._dollar(builder);
      } else if (char === "`") {
        this._backtick(builder);
      } else {
        builder.add(char);
        this._pos += 1;
      }
    }
  }

  /** @param {_WordBuilder} builder */
  _dollar(builder) {
    builder.expands = true;
    if (this._text.startsWith("$(", this._pos)) {
      this._pos += 2;
      builder.started = true;
      builder.substitutions.push(this.script(true));
    } else {
      builder.add("$");
      this._pos += 1;
    }
  }

  /** @param {_WordBuilder} builder */
  _backtick(builder) {
    const text = this._text;
    /** @type {string[]} */
    const inner = [];
    let position = this._pos + 1;
    while (position < text.length && text[position] !== "`") {
      const following = text.slice(position + 1, position + 2);
      if (text[position] === "\\" && following !== "" && "`\\$".includes(following)) {
        inner.push(following);
        position += 2;
      } else {
        inner.push(text[position]);
        position += 1;
      }
    }
    this._pos = position + 1;
    builder.expands = true;
    builder.started = true;
    builder.substitutions.push(new _Parser(inner.join("")).script(false));
  }

  /** @param {_Frame} frame */
  _redirect(frame) {
    const text = this._text;
    if (text.startsWith("(", this._pos + 1)) {
      // process substitution: the group follows
      this._endWord(frame);
      this._pos += 1;
      return;
    }
    if (frame.builder.started && _DIGITS_RE.test(frame.builder.parts.join(""))) {
      frame.builder = new _WordBuilder(); // a file descriptor number, not an operand
    }
    this._endWord(frame);
    if (text.startsWith("<<<", this._pos)) {
      this._pos += 3;
      this._redirectTargetNext = true;
    } else if (text.startsWith("<<", this._pos)) {
      this._heredoc(this._pos + 2);
    } else {
      const start = this._pos;
      this._pos += 1;
      while (this._pos < text.length && "&>|<".includes(text[this._pos])) {
        this._pos += 1;
      }
      this._redirectTargetNext = true;
      this._redirectWriteNext = text.slice(start, this._pos).includes(">");
    }
  }

  /**
   * Read `<<WORD` or `<<-WORD` and remember its delimiter; the body is skipped at the newline.
   * @param {number} start
   */
  _heredoc(start) {
    const text = this._text;
    let position = start;
    const stripTabs = text.startsWith("-", position);
    position += stripTabs ? 1 : 0;
    while (position < text.length && (text[position] === " " || text[position] === "\t")) {
      position += 1;
    }
    /** @type {string[]} */
    const parts = [];
    while (position < text.length && !" \t\n;&|()<>".includes(text[position])) {
      const char = text[position];
      if (char === "\\" && position + 1 < text.length) {
        parts.push(text[position + 1]);
        position += 2;
      } else if (char === "'" || char === '"') {
        let end = text.indexOf(char, position + 1);
        end = end < 0 ? text.length : end;
        parts.push(text.slice(position + 1, end));
        position = end + 1;
      } else {
        parts.push(char);
        position += 1;
      }
    }
    this._pos = position;
    this._heredocs.push([parts.join(""), stripTabs]);
  }

  _skipHeredocs() {
    const text = this._text;
    for (const [delimiter, stripTabs] of this._heredocs) {
      while (this._pos < text.length) {
        const end = text.indexOf("\n", this._pos);
        const line = end < 0 ? text.slice(this._pos) : text.slice(this._pos, end);
        this._pos = end < 0 ? text.length : end + 1;
        if ((stripTabs ? line.replace(/^\t+/, "") : line) === delimiter) {
          break;
        }
      }
    }
    this._heredocs = [];
  }
}

/**
 * `path` read from `directory`: lexical, so `..` is left for the program that opens it.
 * @param {string | null} directory
 * @param {string} path
 * @returns {string | null}
 */
function _joined(directory, path) {
  if (path.startsWith("/")) {
    return path;
  }
  if (directory === null) {
    return null;
  }
  if (path === "") {
    return directory;
  }
  return directory.endsWith("/") ? directory + path : `${directory}/${path}`;
}

/**
 * Where a `cd` or `-C` operand leads from `directory`; `null` when the text does not say.
 * @param {ShellWord} word
 * @param {string | null} directory
 * @param {string | null} home
 * @returns {string | null}
 */
function _targetDirectory(word, directory, home) {
  if (word.expands) {
    return null;
  }
  const value = word.value;
  if (value === "~" || value.startsWith("~/")) {
    return home === null ? null : _joined(directory, home + value.slice(1));
  }
  if (value.startsWith("~")) {
    return null;
  }
  return _joined(directory, value);
}

/**
 * @param {ShellWord} word
 * @returns {boolean}
 */
function _isOption(word) {
  return word.value.startsWith("-") && word.value.length > 1;
}

/**
 * The directory after `cd`/`pushd`; `null` for no literal path, `-`, or an expansion.
 * @param {ShellWord[]} operands
 * @param {string | null} directory
 * @param {string | null} home
 * @returns {string | null}
 */
function _changedDirectory(operands, directory, home) {
  const paths = [...operands];
  while (paths.length > 0 && _isOption(paths[0])) {
    paths.shift();
  }
  if (paths.length === 0 || paths[0].value === "-") {
    return null;
  }
  return _targetDirectory(paths[0], directory, home);
}

// the forge command lines the guard reads like git's
const _FORGE_PROGRAMS = ["gh", "glab"];
// `gh <group> <action>`: `pr create`; `glab mr create`
const _FORGE_NAME_WORDS = 2;
// `-B`: a dash and a letter
const _SHORT_OPTION = 2;
// `gh api <endpoint> -X POST`: the options after it are its arguments
const _FORGE_API = "api";

/**
 * The group and action of a `gh`/`glab` command (`pr create`), its arguments, and where it runs. Options
 * are skipped (`-R`/`--repo` take the next word); a group with no action (`gh pr`) is the
 * subcommand alone. `api` takes no action word: its arguments are every word after it, options
 * included. `null` when no word names a group.
 * @param {ShellWord[]} operands
 * @param {string | null} directory
 * @param {string} program
 * @returns {GitInvocation | null}
 */
function _forgeInvocation(operands, directory, program) {
  const words = operands.map((word) => word.value);
  /** @type {string[]} */
  const names = [];
  /** @type {string[]} */
  let rest = [];
  let index = 0;
  while (index < words.length) {
    const word = words[index];
    if (names.length === _FORGE_NAME_WORDS) {
      rest = words.slice(index);
      break;
    }
    if (word.startsWith("-")) {
      index += 1 + (word === "-R" || word === "--repo" ? 1 : 0);
      continue;
    }
    names.push(word);
    index += 1;
    if (names.length === 1 && names[0] === _FORGE_API) {
      rest = words.slice(index);
      break;
    }
  }
  if (names.length === 0) {
    return null;
  }
  return new GitInvocation({ subcommand: names.join(" "), directory, arguments: rest, program });
}

/**
 * The subcommand after git's global options, its arguments, and the directory they and `directory` give.
 * @param {ShellWord[]} operands
 * @param {string | null} directory
 * @param {boolean} repositoryUnknown
 * @param {string | null} home
 * @returns {GitInvocation | null}
 */
function _gitInvocation(operands, directory, repositoryUnknown, home) {
  let unknown = repositoryUnknown;
  let overridden = false;
  let place = directory;
  let index = 0;
  while (index < operands.length) {
    const value = operands[index].value;
    if (value === "-C") {
      index += 1;
      if (index < operands.length) {
        place = _targetDirectory(operands[index], place, home);
      }
    } else if (value === "-c" || value === "--config-env") {
      index += 1;
      overridden = true;
    } else if (value.startsWith("--config-env=")) {
      overridden = true;
    } else if (value === "--namespace") {
      index += 1;
    } else if (value === "--git-dir" || value === "--work-tree") {
      index += 1;
      unknown = true;
    } else if (value.startsWith("--git-dir=") || value.startsWith("--work-tree=")) {
      unknown = true;
    } else if (!value.startsWith("-")) {
      return new GitInvocation({
        subcommand: value,
        directory: unknown ? null : place,
        arguments: operands.slice(index + 1).map((word) => word.value),
        configOverride: overridden,
      });
    }
    index += 1;
  }
  return null;
}

/**
 * The string argument of `-c` in the arguments of `bash`/`sh`/`zsh`/`dash`, if any.
 * @param {ShellWord[]} operands
 * @returns {string | null}
 */
function _shellScript(operands) {
  for (const [index, word] of operands.entries()) {
    const value = word.value;
    if (!value.startsWith("-")) {
      return null;
    }
    if (!value.startsWith("--") && value.slice(1).includes("c")) {
      return index + 1 < operands.length ? operands[index + 1].value : null;
    }
  }
  return null;
}

/**
 * The shell text a command runs by itself: the `-c` string of a shell, or what `eval` joins.
 * @param {string} name
 * @param {ShellWord[]} operands
 * @returns {string | null}
 */
function _nestedScript(name, operands) {
  if (_SHELLS.has(name.slice(name.lastIndexOf("/") + 1))) {
    return _shellScript(operands);
  }
  if (name === "eval") {
    return operands.map((word) => word.value).join(" ");
  }
  return null;
}

/**
 * Where a command's own word is among `words`, and whether a leading assignment moved git's
 * repository. Leading `VAR=value` words and wrappers are skipped; the index is `words.length` when
 * nothing runs.
 * @param {ShellWord[]} words
 * @returns {[number, boolean]}
 */
function _commandStart(words) {
  let repositoryUnknown = false;
  let index = 0;
  while (index < words.length) {
    const value = words[index].value;
    if (_ASSIGNMENT_RE.test(value)) {
      repositoryUnknown = repositoryUnknown || _ENVIRONMENT_REPOSITORY.has(value.slice(0, value.indexOf("=")));
    } else if (_WRAPPERS.has(value)) {
      while (index + 1 < words.length && _isOption(words[index + 1])) {
        index += 1;
      }
    } else {
      break;
    }
    index += 1;
  }
  return [index, repositoryUnknown];
}

/**
 * @param {{kind: "command", words: ShellWord[]}} command
 * @param {string | null} directory
 * @param {string | null} home
 * @param {GitInvocation[]} found
 * @returns {string | null}
 */
function _walkCommand(command, directory, home, found) {
  for (const word of command.words) {
    for (const substitution of word.substitutions) {
      _walkScript(substitution, directory, home, found);
    }
  }
  const words = command.words.filter((word) => word.operand);
  const [index, repositoryUnknown] = _commandStart(words);
  if (index >= words.length) {
    return directory;
  }
  const name = words[index].value;
  const operands = words.slice(index + 1);
  if (name === "cd" || name === "pushd") {
    return _changedDirectory(operands, directory, home);
  }
  if (name === "popd") {
    return null;
  }
  const program = name.slice(name.lastIndexOf("/") + 1);
  /** @type {GitInvocation | null} */
  let invocation = null;
  if (program === "git") {
    invocation = _gitInvocation(operands, directory, repositoryUnknown, home);
  } else if (_FORGE_PROGRAMS.includes(program)) {
    invocation = _forgeInvocation(operands, directory, program);
  } else {
    const script = _nestedScript(name, operands);
    if (script !== null) {
      _walkScript(new _Parser(script).script(false), directory, home, found);
    }
  }
  if (invocation !== null) {
    found.push(invocation);
  }
  return directory;
}

/**
 * @param {ShellUnit[]} script
 * @param {string | null} start
 * @param {string | null} home
 * @param {GitInvocation[]} found
 * @returns {void}
 */
function _walkScript(script, start, home, found) {
  let directory = start;
  for (const unit of script) {
    if (unit.kind === "group") {
      _walkScript(unit.script, directory, home, found);
    } else {
      directory = _walkCommand(unit, directory, home, found);
    }
  }
}

/**
 * Every `git`, `gh` and `glab` command a shell command runs, in order, with the directory each runs in.
 *
 * Only *command words* count: a heredoc body, a quoted argument (`echo "git push"`,
 * `grep 'git merge' f`) and a comment are text. The scan follows `;`, `&&`, `||`, pipes, newlines,
 * parentheses, `$(...)`, backticks, `bash -c '...'` and `eval`; it skips leading `VAR=value` and the
 * wrappers `env command time nohup exec`; and it tracks `cd`/`pushd` and git's `-C`. It reads no
 * file: `startDirectory` is where the command starts, and a directory the text does not determine
 * (a `$` expansion, `GIT_DIR`, `--git-dir`, `cd -`) is `null`. `~` is `homeDirectory`, or an
 * unknown place when that is `null`.
 * @param {string} command
 * @param {string | null} startDirectory
 * @param {{homeDirectory?: string | null}} [options]
 * @returns {GitInvocation[]}
 */
export function gitInvocations(command, startDirectory, { homeDirectory = null } = {}) {
  /** @type {GitInvocation[]} */
  const found = [];
  _walkScript(new _Parser(command).script(false), startDirectory, homeDirectory, found);
  return found;
}

/**
 * Standard output of `git -C directory <arguments>`; `null` on any failure.
 * @param {string} directory
 * @param {string[]} gitArguments
 * @returns {string | null}
 */
function _gitOutput(directory, gitArguments) {
  const { spawnSync } = /** @type {typeof import("node:child_process")} */ (
    createRequire(import.meta.url)("node:child_process")
  );
  try {
    const result = spawnSync("git", ["-C", directory, ...gitArguments], {
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 5000,
    });
    return result.error === undefined && result.status === 0 ? decodeUtf8(result.stdout) : null;
  } catch {
    return null; // an argument node refuses (a NUL): the ValueError of the twin
  }
}

/**
 * `path` resolved against `directory` through links where it exists.
 * @param {string} directory
 * @param {string} path
 * @returns {string}
 */
function _realPath(directory, path) {
  const absolute = pathModule.resolve(directory, path);
  try {
    return fs.realpathSync(absolute);
  } catch {
    return absolute;
  }
}

/**
 * The path `cp`/`mv`/`install` writes: the last operand, or the sources' names inside a `-t` directory.
 * @param {readonly string[]} values
 * @param {import("../common/harness_settings.mjs").HarnessSettingsData["shell"]} shell
 * @returns {string[]}
 */
function _destination(values, shell) {
  /** @type {string | null} */
  let targetDirectory = null;
  /** @type {string[]} */
  const operands = [];
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    const equals = value.indexOf("=");
    const longName = equals < 0 ? value : value.slice(0, equals);
    const attached = equals < 0 ? "" : value.slice(equals + 1);
    if (shell.target_directory_options.includes(value)) {
      targetDirectory = index + 1 < values.length ? values[index + 1] : null;
      index += 1;
    } else if (shell.target_directory_options.includes(longName) && attached !== "") {
      targetDirectory = attached;
    } else if (value.startsWith("-t") && !value.startsWith("--") && value.length > _SHORT_OPTION) {
      targetDirectory = value.slice(_SHORT_OPTION);
    } else if (!(value.startsWith("-") && value.length > 1)) {
      operands.push(value);
    }
  }
  if (targetDirectory !== null) {
    const base = targetDirectory.replace(/\/+$/, "");
    return operands.map((operand) => {
      const trimmed = operand.replace(/\/+$/, "");
      return `${base}/${trimmed.slice(trimmed.lastIndexOf("/") + 1)}`;
    });
  }
  return operands.slice(-1);
}

/**
 * The paths a program writes among its `operands`: the words, by what `harness_settings.json` says
 * it does. `tee` and `sponge` write every operand; `sed -i` and `perl -i` (any option cluster
 * holding the letter, or `--in-place`) write the files they name; `cp`, `mv` and `install` write
 * their last operand, or, with `-t DIRECTORY`, a file of that name in it; `dd` writes its `of=`
 * operand.
 * @param {string} program
 * @param {readonly ShellWord[]} operands
 * @param {import("../common/harness_settings.mjs").HarnessSettingsData["shell"]} shell
 * @returns {string[]}
 */
function _writeCandidates(program, operands, shell) {
  const values = operands.map((word) => word.value);
  const options = values.filter((value) => value.startsWith("-") && value.length > 1);
  const paths = () => values.filter((value) => !options.includes(value));
  if (shell.write_all_operands.includes(program)) {
    return paths();
  }
  const letter = Object.hasOwn(shell.in_place, program) ? shell.in_place[program] : null;
  if (letter !== null) {
    const longOption = shell.in_place_long_option;
    const inPlace = options.some((option) =>
      option.startsWith("--")
        ? option === longOption || option.startsWith(`${longOption}=`)
        : option.slice(1).includes(letter),
    );
    return inPlace ? paths() : [];
  }
  if (shell.write_last_operand.includes(program)) {
    return _destination(values, shell);
  }
  const prefix = Object.hasOwn(shell.operand_assignments, program) ? shell.operand_assignments[program] : null;
  if (prefix !== null) {
    return values.filter((value) => value.startsWith(prefix)).map((value) => value.slice(prefix.length));
  }
  return [];
}

/**
 * The first of `candidates` that names a harness settings file, spelled as given or read from `directory`.
 * @param {readonly string[]} candidates
 * @param {string | null} directory
 * @param {HookData} data
 * @returns {string | null}
 */
function _settingsFileAmong(candidates, directory, data) {
  for (const candidate of candidates) {
    for (const path of [candidate, _joined(directory, candidate)]) {
      if (path !== null && fileFormat(path, data.harnessSettings) !== null) {
        return candidate;
      }
    }
  }
  return null;
}

/**
 * The harness settings file `command` writes, if any, and the directory after it (`cd` moves it).
 * @param {HookData} data
 * @param {{kind: "command", words: ShellWord[]}} command
 * @param {string | null} directory
 * @param {string | null} home
 * @returns {[string | null, string | null]}
 */
function _writtenSettingsFile(data, command, directory, home) {
  for (const word of command.words) {
    for (const substitution of word.substitutions) {
      const path = _writtenSettingsIn(data, substitution, directory, home);
      if (path !== null) {
        return [path, directory];
      }
    }
  }
  const candidates = command.words.filter((word) => word.write).map((word) => word.value);
  const words = command.words.filter((word) => word.operand);
  const [index] = _commandStart(words);
  if (index < words.length) {
    const name = words[index].value;
    const operands = words.slice(index + 1);
    if (name === "cd" || name === "pushd") {
      return [null, _changedDirectory(operands, directory, home)];
    }
    if (name === "popd") {
      return [null, null];
    }
    candidates.push(..._writeCandidates(name.slice(name.lastIndexOf("/") + 1), operands, data.harnessSettings.shell));
    const script = _nestedScript(name, operands);
    if (script !== null) {
      const path = _writtenSettingsIn(data, new _Parser(script).script(false), directory, home);
      if (path !== null) {
        return [path, directory];
      }
    }
  }
  return [_settingsFileAmong(candidates, directory, data), directory];
}

/**
 * The first harness settings file a script's commands write, as the command spells it.
 * @param {HookData} data
 * @param {ShellUnit[]} script
 * @param {string | null} start
 * @param {string | null} home
 * @returns {string | null}
 */
function _writtenSettingsIn(data, script, start, home) {
  let directory = start;
  for (const unit of script) {
    /** @type {string | null} */
    let path;
    if (unit.kind === "group") {
      path = _writtenSettingsIn(data, unit.script, directory, home);
    } else {
      [path, directory] = _writtenSettingsFile(data, unit, directory, home);
    }
    if (path !== null) {
      return path;
    }
  }
  return null;
}

/**
 * The reason to deny `command` for writing a harness settings file, `null` when no command word does.
 * The data file names the directories (`.claude`, `.codex`) that a command, or the directory it starts
 * in, must mention for the command to be parsed at all.
 * @param {HookData} data
 * @param {string} command
 * @param {string | null} directory
 * @returns {string | null}
 */
function _settingsWriteReason(data, command, directory) {
  const settings = data.harnessSettings;
  if (
    !settings.files.some((entry) => pyContains(command, entry.directory) || (directory ?? "").includes(entry.directory))
  ) {
    return null;
  }
  const path = _writtenSettingsIn(data, new _Parser(command).script(false), directory, _homeDirectory());
  return path === null ? null : settingsWriteReason(path, settings);
}

/**
 * Ask git what repository `directory` is in; `null` when it is in none or git cannot say.
 *
 * A worktree is *linked* when its git directory differs from the common one the main checkout
 * keeps. A detached `HEAD` has the branch `""`.
 * @param {string} directory
 * @returns {RepositoryFacts | null}
 */
export function repositoryFacts(directory) {
  const layout = _gitOutput(directory, ["rev-parse", "--git-dir", "--git-common-dir"]);
  const paths = layout === null ? [] : layout.replace(/\n+$/, "").split("\n");
  if (paths.length !== 2) {
    return null;
  }
  const branch = _gitOutput(directory, ["symbolic-ref", "--short", "-q", "HEAD"]);
  return new RepositoryFacts({
    linked: _realPath(directory, paths[0]) !== _realPath(directory, paths[1]),
    branch: pyStrip(branch ?? ""),
  });
}

/**
 * What one actor may do: the matrix row, and the texts that say so (ADR 0031/D07). Built once per
 * guard call from `common/access_matrix.json` and `hook_core.json`.
 */
/**
 * The deny for an AI trailer: unconditional, read from no matrix (commits.owner-owned).
 *
 * `checkTrailerFloor` already refuses a matrix whose `ai_trailer` cells are not `deny`; the floor does
 * not depend on them. The reason is the actor's text for the class, as the matrix path gives.
 * @param {HookData} data
 * @param {Actor} actor
 * @returns {HookResult}
 */
function _aiTrailerFloor(data, actor) {
  const key = dictItem(dictItem(dictItem(data.core, "access_reasons"), actor), AI_TRAILER_CLASS);
  return new HookResult({
    eventName: "PreToolUse",
    permissionDecision: "deny",
    permissionReason: fill(dictItem(data.core, key), {}),
  });
}

/**
 * The reason a crashed commit guard gives an autonomous run when `hook_core.json` cannot be read
 * either: the crash path depends on no data file, since a missing or broken one may be the very
 * failure it answers.
 */
export const GUARD_CRASH_FALLBACK_REASON =
  "Commit guardrail (autonomous run): the access matrix could not be read, so an autonomous run is denied.";

/**
 * The one-line JSON `PreToolUse` deny a crashed commit guard answers an `autonomous` run with.
 *
 * ADR-0031/D07 (D-C203-GUARD-CRASH): when the guard cannot read the access matrix, or raises while
 * evaluating a command, an autonomous run is denied where a developer run is let through (the
 * crash-open posture of ADR 0013). The actor is read from the environment before the matrix is, so
 * this answer depends on neither the matrix nor, if the texts cannot be read, on any data file: it
 * names its keys literally and falls back to a reason in code. Both vendor adapters write this
 * document.
 *
 * Runtime classification: operational
 * Rationale: it is the crash posture of the commit guard (`commits.owner-owned`), not a rule of its
 * own: it answers a failure with the deny the guard's autonomous row would otherwise give, and an
 * adapter writes it into the vendor's channel from outside the `*_result` join, so ADR-0012/D07
 * requires the classification to be stated rather than left silent.
 * @param {HookData} data
 * @returns {string}
 */
export function guardCrashDenyDocument(data) {
  /** @type {string} */
  let reason;
  try {
    reason = dictItem(data.core, "git_commit_guard_crash_reason");
  } catch {
    reason = GUARD_CRASH_FALLBACK_REASON;
  }
  const output = new Map([
    ["hookEventName", "PreToolUse"],
    ["permissionDecision", "deny"],
    ["permissionDecisionReason", reason],
  ]);
  return hookForm(new Map([["hookSpecificOutput", output]]));
}

class _Access {
  /**
   * @param {HookData} data
   * @param {Actor} actor
   * @param {string | null} [runBranch] the branch an autonomous run owns (`AKMON_RUN_BRANCH`), if one is named
   */
  constructor(data, actor, runBranch = null) {
    this.actor = actor;
    this.runBranch = runBranch;
    this.texts = data.core;
    this.matrix = data.accessMatrix;
    // The branches this actor is kept off as it is off the default branch: the default branches and its protected ones.
    /** @type {readonly string[]} */
    this.defaultBranchNames = _core(data, "git_default_branches");
    /** @type {readonly string[]} */
    this.protectedNames = protectedBranches(this.matrix, actor);
  }

  /**
   * Whether `branch` is a default branch or one the actor is kept off like it (`develop`, `release/*`).
   * @param {string} branch
   * @returns {boolean}
   */
  isDefaultBranch(branch) {
    return this.defaultBranchNames.includes(branch) || isProtectedBranch(this.protectedNames, branch);
  }

  /**
   * Whether `branch` is one the actor may write: for an autonomous run, its own run branch.
   * @param {string} branch
   * @returns {boolean}
   */
  isOwnBranch(branch) {
    return isOwnBranch(this.matrix, this.actor, branch, this.runBranch);
  }

  /**
   * What the matrix gives the actor for `actionClass`: `null` to pass, else an ask or a deny. The
   * reason is the actor's text for the class (`access_reasons` in `hook_core.json`) filled with
   * `values`.
   * @param {string} actionClass
   * @param {Record<string, string>} values
   * @returns {HookResult | null}
   */
  result(actionClass, values) {
    const decision = accessOutcome(this.matrix, this.actor, actionClass);
    if (decision === "allow") {
      return null;
    }
    const key = dictItem(dictItem(dictItem(this.texts, "access_reasons"), this.actor), actionClass);
    return new HookResult({
      eventName: "PreToolUse",
      permissionDecision: decision,
      permissionReason: fill(dictItem(this.texts, key), values),
    });
  }

  /**
   * Whether the actor gets one outcome for all of `actionClasses`: telling them apart changes nothing.
   * @param {readonly string[]} actionClasses
   * @returns {boolean}
   */
  uniform(actionClasses) {
    return new Set(actionClasses.map((name) => accessOutcome(this.matrix, this.actor, name))).size === 1;
  }

  /**
   * The result for `subcommand` writing history at a `place` (a `history_*` class), `facts` naming it.
   * @param {string} subcommand
   * @param {string} place
   * @param {Record<string, string>} facts
   * @returns {HookResult | null}
   */
  historyResult(subcommand, place, facts) {
    if (accessOutcome(this.matrix, this.actor, place) === "allow") {
      return null;
    }
    const key = dictItem(dictItem(dictItem(this.texts, "access_where"), this.actor), place);
    return this.result(place, { subcommand, where: fill(dictItem(this.texts, key), facts) });
  }
}

/** The rank of each outcome, from the most permissive to the most restrictive. */
const _OUTCOME_ORDER = new Map(OUTCOMES.map((name, rank) => [name, rank]));

/**
 * The result with the strictest decision among `results` (an `ask` before a pass, a `deny` before an ask).
 * @param {(HookResult | null)[]} results
 * @returns {HookResult | null}
 */
function _mostRestrictive(results) {
  /** @type {HookResult | null} */
  let strictest = null;
  for (const result of results) {
    if (result === null) {
      continue;
    }
    const rank = /** @type {number} */ (_OUTCOME_ORDER.get(result.permissionDecision ?? "allow"));
    if (
      strictest === null ||
      rank > /** @type {number} */ (_OUTCOME_ORDER.get(strictest.permissionDecision ?? "allow"))
    ) {
      strictest = result;
    }
  }
  return strictest;
}

/**
 * Where `directory` puts a history write: its action class in the matrix, and the values naming it.
 * `history_unresolved` and `history_not_repository` have no facts; the rest are
 * `history_{checkout|worktree}_{default|detached|branch}` — a linked worktree or not, on a default
 * branch, on a detached `HEAD` or on a named branch — and `history_not_run_branch`: a named branch of
 * a checkout (not a linked worktree) that is not the actor's own run branch. A linked worktree's
 * branch is its own by the job-branch carve-out, so the run branch does not narrow it (ADR 0031/D07).
 * @param {string | null} directory
 * @param {(directory: string) => {linked: boolean, branch: string} | null} repositoryAt
 * @param {_Access} access
 * @returns {[string, Record<string, string>]}
 */
function _historyPlace(directory, repositoryAt, access) {
  if (directory === null) {
    return ["history_unresolved", {}];
  }
  const facts = repositoryAt(directory);
  if (facts === null) {
    return ["history_not_repository", { directory }];
  }
  const where = facts.linked ? "worktree" : "checkout";
  let branch = "branch";
  if (!facts.branch) {
    branch = "detached";
  } else if (access.isDefaultBranch(facts.branch)) {
    branch = "default";
  } else if (!facts.linked && !access.isOwnBranch(facts.branch)) {
    return ["history_not_run_branch", { directory, branch: facts.branch }];
  }
  return [`history_${where}_${branch}`, { directory, branch: facts.branch }];
}

/** @typedef {(directory: string) => {linked: boolean, branch: string} | null} RepositoryLookup */

/**
 * Whether `name` is a job branch, short (`_aitna/x`) or full (`refs/heads/_aitna/x`).
 * @param {HookData} data
 * @param {string} name
 * @returns {boolean}
 */
function _isJobBranch(data, name) {
  const prefix = /** @type {string} */ (_core(data, "git_job_branch_prefix"));
  return name.startsWith(prefix) || name.startsWith(`${_core(data, "git_heads_prefix")}${prefix}`);
}

/**
 * Git arguments as `[options, operands]`: `--` ends the options, a `valued` option takes the next word.
 * @param {readonly string[]} args
 * @param {readonly string[]} [valued]
 * @returns {[string[], string[]]}
 */
function _splitArguments(args, valued = []) {
  /** @type {string[]} */
  const options = [];
  /** @type {string[]} */
  const operands = [];
  let optionsEnded = false;
  for (let index = 0; index < args.length; index += 1) {
    const word = args[index];
    if (optionsEnded || !word.startsWith("-") || word === "-") {
      operands.push(word);
    } else if (word === "--") {
      optionsEnded = true;
    } else {
      options.push(word);
      index += valued.includes(word) ? 1 : 0;
    }
  }
  return [options, operands];
}

/**
 * The flags among `options` as letters: `longNames` spell the long ones, a `u` ends a cluster.
 * @param {readonly string[]} options
 * @param {Record<string, string>} longNames
 * @returns {Set<string>}
 */
function _optionLetters(options, longNames) {
  /** @type {Set<string>} */
  const flags = new Set();
  for (const word of options) {
    if (word.startsWith("--")) {
      const name = word.split("=", 1)[0];
      for (const letter of Object.hasOwn(longNames, name) ? longNames[name] : "") {
        flags.add(letter);
      }
      continue;
    }
    for (const letter of word.slice(1)) {
      flags.add(letter);
      if (letter === "u") {
        break; // the rest of the cluster is the upstream's name
      }
    }
  }
  return flags;
}

const _BRANCH_LONG_FLAGS = {
  "--force": "f",
  "--delete": "d",
  "--move": "m",
  "--copy": "c",
  "--set-upstream-to": "u",
  "--unset-upstream": "u",
};
// subcommand: [letter that forces, letters that take a branch name, long form that forces]
/** @type {Record<string, [string, string, string]>} */
const _FORCE_CREATE = { checkout: ["B", "bB", ""], switch: ["C", "cC", "--force-create"] };

/**
 * The branch `invocation`'s repository is on; `null` when the text, git or a detached `HEAD` do not say.
 * @param {GitInvocation} invocation
 * @param {RepositoryLookup} repositoryAt
 * @returns {string | null}
 */
function _currentBranch(invocation, repositoryAt) {
  if (invocation.directory === null) {
    return null;
  }
  const facts = repositoryAt(invocation.directory);
  return facts === null || !facts.branch ? null : facts.branch;
}

/**
 * The branches `git branch` writes to that are not job branches; `null` is a current branch not
 * named. Listing, creating a new branch and the upstream options write no existing branch.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @param {RepositoryLookup} repositoryAt
 * @returns {(string | null)[]}
 */
function _branchOffenders(data, invocation, repositoryAt) {
  const [options, operands] = _splitArguments(invocation.arguments);
  const flags = new Set([..._optionLetters(options, _BRANCH_LONG_FLAGS)].map((letter) => letter.toLowerCase()));
  const has = (/** @type {string} */ letters) => [...letters].some((letter) => flags.has(letter));
  if (has("u") || !has("dmcf")) {
    return [];
  }
  /** @type {(string | null)[]} */
  let names;
  if (has("mc")) {
    names = [...operands];
    if (operands.length === 1) {
      names.push(_currentBranch(invocation, repositoryAt)); // one name: the current branch is the other end
    }
  } else {
    names = has("d") ? [...operands] : operands.slice(0, 1); // force: the first name only
  }
  return names.filter((name) => name === null || !_isJobBranch(data, name));
}

/**
 * The branch `checkout -B` or `switch -C`/`--force-create` writes over, unless it is a job branch.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {string[]}
 */
function _forcedBranchOffenders(data, invocation) {
  const [letter, valuedLetters, longName] = _FORCE_CREATE[invocation.subcommand];
  const args = invocation.arguments;
  /** @type {string[]} */
  const names = [];
  for (const [index, word] of args.entries()) {
    if (word === "--") {
      break;
    }
    if (longName && word.split("=", 1)[0] === longName) {
      names.push(...(word.includes("=") ? [word.slice(word.indexOf("=") + 1)] : args.slice(index + 1, index + 2)));
    } else if (word.startsWith("-") && !word.startsWith("--")) {
      const cluster = word.slice(1);
      const position = [...cluster].findIndex((char) => valuedLetters.includes(char));
      if (position >= 0 && cluster[position] === letter) {
        const rest = cluster.slice(position + 1); // the rest of the word, or the next, is the name
        names.push(...(rest ? [rest] : args.slice(index + 1, index + 2)));
      }
    }
  }
  return names.filter((name) => !_isJobBranch(data, name));
}

/**
 * The refspec destinations of `fetch`/`pull` that are not remote-tracking refs or job branches.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {string[]}
 */
function _fetchOffenders(data, invocation) {
  const [, operands] = _splitArguments(invocation.arguments, _core(data, "git_fetch_valued_options"));
  /** @type {string[]} */
  const destinations = [];
  for (const refspec of operands.slice(1)) {
    // the first operand is the remote
    const spec = refspec.startsWith("+") ? refspec.slice(1) : refspec;
    const destination = spec.includes(":") ? spec.slice(spec.indexOf(":") + 1) : "";
    if (destination && !destination.startsWith(_core(data, "git_remotes_prefix")) && !_isJobBranch(data, destination)) {
      destinations.push(destination);
    }
  }
  return destinations;
}

// `symbolic-ref <name> <ref>` writes; one operand reads
const _WRITE_OPERANDS = 2;

/**
 * The refs `symbolic-ref` writes or deletes that are not job branches: `HEAD` may point at one.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {string[]}
 */
function _symbolicRefOffenders(data, invocation) {
  const [options, operands] = _splitArguments(invocation.arguments, ["-m"]);
  /** @type {string[]} */
  let written;
  if (_optionLetters(options, { "--delete": "d" }).has("d")) {
    written = operands.slice(0, 1);
  } else if (operands.length >= _WRITE_OPERANDS) {
    written = [...operands.slice(0, 1).filter((name) => name !== "HEAD"), ...operands.slice(1, 2)];
  } else {
    return [];
  }
  return written.filter((name) => !_isJobBranch(data, name));
}

/**
 * The ref `update-ref` writes when it is not `refs/heads/_aitna/*`; `[""]` for refs read from stdin.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {string[]}
 */
function _updateRefOffenders(data, invocation) {
  const [options, operands] = _splitArguments(invocation.arguments, ["-m"]);
  if (options.includes("--stdin")) {
    return [""];
  }
  const jobHeads = `${_core(data, "git_heads_prefix")}${_core(data, "git_job_branch_prefix")}`;
  return operands.slice(0, 1).filter((name) => !name.startsWith(jobHeads));
}

/**
 * The command as the ref rules name it: `worktree` joins its action (`worktree remove`).
 * @param {GitInvocation} invocation
 * @returns {string}
 */
function _refSubcommand(invocation) {
  if (invocation.subcommand !== "worktree") {
    return invocation.subcommand;
  }
  const [, operands] = _splitArguments(invocation.arguments);
  return ["worktree", ...operands.slice(0, 1)].join(" ");
}

/**
 * What a ref-writing `invocation` moves, renames or deletes beyond job branches, in words; `null` if none.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @param {RepositoryLookup} repositoryAt
 * @returns {string | null}
 */
function _refTarget(data, invocation, repositoryAt) {
  const subcommand = _refSubcommand(invocation);
  const unconditional = _core(data, "git_ref_unconditional");
  if (Object.hasOwn(unconditional, subcommand)) {
    return unconditional[subcommand];
  }
  /** @type {(string | null)[]} */
  let offenders;
  if (subcommand === "branch") {
    offenders = _branchOffenders(data, invocation, repositoryAt);
  } else if (Object.hasOwn(_FORCE_CREATE, subcommand)) {
    offenders = _forcedBranchOffenders(data, invocation);
  } else if (subcommand === "fetch" || subcommand === "pull") {
    offenders = _fetchOffenders(data, invocation);
  } else if (subcommand === "symbolic-ref") {
    offenders = _symbolicRefOffenders(data, invocation);
  } else if (subcommand === "update-ref") {
    offenders = _updateRefOffenders(data, invocation);
  } else {
    return null;
  }
  if (offenders.length === 0) {
    return null;
  }
  if (offenders.length === 1 && offenders[0] === "") {
    return _core(data, "git_commit_ref_target_stdin");
  }
  return [...new Set(offenders)]
    .map((name) => (name === null ? _core(data, "git_commit_ref_target_current_branch") : `'${name}'`))
    .join(", ");
}

// The classes a push of a branch falls into (a tag is its own class, `tag`).
const _PUSH_CLASSES = ["push_own_branch", "push_own_branch_forced", "push_default_branch", "push_other_branch"];

/**
 * The flags of `git push` that decide its class: `f` force, `d` delete, `a` all branches, `t` tags, `T` the tags
 * that follow the pushed commits.
 * @param {HookData} data
 * @param {string[]} options
 * @returns {Set<string>}
 */
function _pushFlags(data, options) {
  /** @type {Set<string>} */
  const flags = new Set();
  const longFlags = _core(data, "git_push_long_flags");
  for (const word of options) {
    if (word.startsWith("--")) {
      const name = word.split("=", 1)[0];
      for (const letter of Object.hasOwn(longFlags, name) ? longFlags[name] : "") {
        flags.add(letter);
      }
    } else {
      for (const letter of word.slice(1)) {
        if (letter === "f" || letter === "d") {
          flags.add(letter);
        }
      }
    }
  }
  return flags;
}

/**
 * The matrix class of one pushed refspec and the ref it writes. The destination decides: a tag, a
 * default branch, the branch the repository is on (`current`; `HEAD` stands for it) when that is the
 * actor's own branch (an autonomous run's run branch), or another branch. A `+` prefix, a `:destination` with no source and the caller's `forced` (`--force`,
 * `--delete`) make a push of the own branch the forced one.
 * @param {string} refspec
 * @param {boolean} forced
 * @param {string | null} current
 * @param {_Access} access
 * @returns {[string, string]}
 */
function _refspecClass(refspec, forced, current, access) {
  const spec = refspec.startsWith("+") ? refspec.slice(1) : refspec;
  const colon = spec.indexOf(":");
  const source = colon < 0 ? spec : spec.slice(0, colon);
  const destination = colon < 0 ? "" : spec.slice(colon + 1);
  let target = colon < 0 ? source : destination;
  if (target.startsWith("refs/tags/")) {
    return ["tag", target];
  }
  if (target.startsWith("refs/heads/")) {
    target = target.slice("refs/heads/".length);
  }
  if (target === "HEAD" && current !== null) {
    target = current;
  }
  if (access.isDefaultBranch(target)) {
    return ["push_default_branch", target];
  }
  if (target !== current || !access.isOwnBranch(target)) {
    return ["push_other_branch", target];
  }
  const forcing = forced || refspec.startsWith("+") || (colon >= 0 && source === "");
  return [forcing ? "push_own_branch_forced" : "push_own_branch", target];
}

/**
 * The strictest decision among the refs `git push` writes: which class each is, the matrix says what it gets.
 * A push that names no refspec, or runs under `-c` configuration, writes where git's configuration says
 * (`push.default`, `remote.*.push`): its destination is not the text's, so it is another branch's.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @param {_Access} access
 * @param {RepositoryLookup} repositoryAt
 * @returns {HookResult | null}
 */
function _pushDecision(data, invocation, access, repositoryAt) {
  const [options, operands] = _splitArguments(invocation.arguments, _core(data, "git_push_valued_options"));
  const flags = _pushFlags(data, options);
  const base = { subcommand: invocation.subcommand };
  if (flags.has("a")) {
    // --all, --branches and --mirror write the default branch with the rest
    return access.result("push_default_branch", { ...base, branch: _core(data, "git_push_all_target") });
  }
  const repoNamed = options.some((word) => word.split("=", 1)[0] === "--repo");
  const refspecs = repoNamed ? operands : operands.slice(1); // the first operand is the remote
  // No lookup where the branch cannot change the outcome (a developer's push asks wherever it goes).
  const current = access.uniform(_PUSH_CLASSES) ? null : _currentBranch(invocation, repositoryAt);
  const forced = flags.has("f") || flags.has("d");
  // [matrix class, the ref as the reason names it]
  /** @type {[string, string][]} */
  const classes = [];
  if (flags.has("t") || flags.has("T")) {
    classes.push(["tag", flags.has("t") ? "'--tags'" : "'--follow-tags'"]);
  }
  if (invocation.configOverride) {
    classes.push(["push_other_branch", _core(data, "git_push_config_target")]);
  } else if (refspecs.length > 0) {
    for (const spec of refspecs) {
      const [name, ref] = _refspecClass(spec, forced, current, access);
      classes.push([name, `'${ref}'`]);
    }
  } else if (!flags.has("t")) {
    classes.push(["push_other_branch", _core(data, "git_push_implicit_target")]);
  }
  return _mostRestrictive(classes.map(([name, ref]) => access.result(name, { ...base, branch: ref })));
}

/**
 * What the actor gets for `push` or `tag`: a push by the branch it writes, a tag by its own class.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @param {_Access} access
 * @param {RepositoryLookup} repositoryAt
 * @returns {HookResult | null}
 */
function _publishingDecision(data, invocation, access, repositoryAt) {
  if (invocation.subcommand === "push") {
    return _pushDecision(data, invocation, access, repositoryAt);
  }
  return access.result("tag", { subcommand: invocation.subcommand });
}

/**
 * The regular expression of a `git_config_push_keys` pattern: `*` is one or more characters.
 * @param {string} pattern
 * @returns {RegExp}
 */
function _globPattern(pattern) {
  const escaped = pattern.split("*").map((part) => part.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`));
  return new RegExp(`^(?:${escaped.join(".+")})$`, "s");
}

/**
 * What a `git config` writes: `[name, isSection]`; `["", false]` for an editor; `null` for a read. The old
 * form (`config [--unset] <key> [<value>]`) and the `set`/`unset` actions of git 2.46 are both read; a
 * lone key, `--get`, `--list` and the `get`/`list` actions read.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {[string, boolean] | null}
 */
function _configWrittenName(data, invocation) {
  const [options, operands] = _splitArguments(invocation.arguments, _core(data, "git_config_valued_options"));
  /** @type {Record<string, string[]>} */
  const actions = _core(data, "git_config_actions");
  const named = (/** @type {string} */ key) => options.some((word) => _core(data, key).includes(word));
  if (named("git_config_read_options")) {
    return null;
  }
  if (named("git_config_edit_options")) {
    return ["", false];
  }
  const known = Object.values(actions).flat();
  const action = operands.length > 0 && known.includes(operands[0]) ? operands[0] : null;
  if (action !== null && actions.read.includes(action)) {
    return null;
  }
  if (action !== null && actions.edit.includes(action)) {
    return ["", false];
  }
  /** @type {string[]} */
  let names;
  let isSection = false;
  if (action !== null) {
    names = operands.slice(1, 2);
    isSection = actions.section_write.includes(action);
  } else if (named("git_config_section_write_options")) {
    names = operands.slice(0, 1);
    isSection = true;
  } else if (named("git_config_key_write_options") || operands.length >= _WRITE_OPERANDS) {
    names = operands.slice(0, 1);
  } else {
    return null;
  }
  return names.length > 0 ? [names[0], isSection] : null;
}

/**
 * Whether the key (or section) `name` is one of `git_config_push_keys`; `""` (an editor) is.
 * @param {HookData} data
 * @param {string} name
 * @param {boolean} isSection
 * @returns {boolean}
 */
function _isPushConfig(data, name, isSection) {
  if (!name) {
    return true;
  }
  const key = name.toLowerCase();
  for (const pattern of /** @type {string[]} */ (_core(data, "git_config_push_keys"))) {
    // a section is written whole: test it with the variable its pattern names
    const candidate = isSection ? `${key}.${pattern.slice(pattern.lastIndexOf(".") + 1).replaceAll("*", "x")}` : key;
    if (_globPattern(pattern).test(candidate)) {
      return true;
    }
  }
  return false;
}

/**
 * What the actor gets for a `git config` that writes a push-redirecting key; reads and other keys pass.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @param {_Access} access
 * @returns {HookResult | null}
 */
function _configDecision(data, invocation, access) {
  const written = _configWrittenName(data, invocation);
  if (written === null || !_isPushConfig(data, written[0], written[1])) {
    return null;
  }
  return access.result("config_push_write", { key: written[0] || _core(data, "git_config_edit_target") });
}

/**
 * The base branch a `pr create`/`mr create` names (`--base X`, `--base=X`, `-B X`); `null` if none.
 *
 * Only the program's own base options count (`pr_base_options` in `hook_core.json`: `-b` is `gh`'s
 * body and `glab`'s target branch). An option with no value reads as the empty name. Where the option is
 * repeated the last value wins, as in `gh` and `glab`.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {string | null}
 */
function _pullRequestBase(data, invocation) {
  /** @type {string[]} */
  const options = dictItem(_core(data, "pr_base_options"), invocation.program);
  const words = invocation.arguments;
  /** @type {string | null} */
  let base = null;
  for (const [index, word] of words.entries()) {
    const equals = word.indexOf("=");
    const name = equals < 0 ? word : word.slice(0, equals);
    if (options.includes(name)) {
      base = equals < 0 ? (words[index + 1] ?? "") : word.slice(equals + 1);
    } else if (
      !word.startsWith("--") &&
      options.some((option) => option.length === _SHORT_OPTION && word.startsWith(option))
    ) {
      const attached = word.slice(_SHORT_OPTION); // `-Bdevelop`: the value is attached
      base = attached.startsWith("=") ? attached.slice(1) : attached;
    }
  }
  return base;
}

/**
 * The HTTP method a `gh api`/`glab api` sends: the last one named, else POST when it carries fields.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {string}
 */
function _apiMethod(data, invocation) {
  /** @type {string[]} */
  const methods = _core(data, "forge_api_method_options");
  /** @type {string[]} */
  const fields = _core(data, "forge_api_field_options");
  const words = invocation.arguments;
  /** @type {string | null} */
  let method = null;
  let carriesFields = false;
  for (const [index, word] of words.entries()) {
    const equals = word.indexOf("=");
    const name = equals < 0 ? word : word.slice(0, equals);
    if (methods.includes(name)) {
      method = equals < 0 ? (words[index + 1] ?? "") : word.slice(equals + 1);
    } else if (!word.startsWith("--") && methods.some((option) => word.startsWith(option))) {
      method = word.slice(_SHORT_OPTION); // `-XPOST`
    } else if (fields.includes(name) || (!word.startsWith("--") && fields.some((option) => word.startsWith(option)))) {
      carriesFields = true;
    }
  }
  return (method || (carriesFields ? "POST" : "GET")).toUpperCase();
}

/**
 * The command's group and action with its aliases resolved (`pr new` is `pr create`).
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @returns {string}
 */
function _forgeAction(data, invocation) {
  const space = invocation.subcommand.indexOf(" ");
  const group = space < 0 ? invocation.subcommand : invocation.subcommand.slice(0, space);
  const action = space < 0 ? "" : invocation.subcommand.slice(space + 1);
  /** @type {Record<string, string>} */
  const groupAliases = dictItem(_core(data, "forge_group_aliases"), invocation.program);
  /** @type {Record<string, string>} */
  const actionAliases = dictItem(_core(data, "forge_action_aliases"), invocation.program);
  const resolved = Object.hasOwn(groupAliases, group) ? groupAliases[group] : group;
  const name = `${resolved} ${action}`.trimEnd();
  return Object.hasOwn(actionAliases, name) ? actionAliases[name] : name;
}

/**
 * What the actor gets for a `gh`/`glab` command: its class, a pull request by the base it targets.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @param {_Access} access
 * @returns {HookResult | null}
 */
function _forgeDecision(data, invocation, access) {
  const classes = dictItem(
    { gh: _core(data, "gh_action_classes"), glab: _core(data, "glab_action_classes") },
    invocation.program,
  );
  const subcommand = _forgeAction(data, invocation);
  /** @type {string | null} */
  let actionClass = null;
  if (subcommand === _FORGE_API) {
    const writes = _core(data, "forge_api_write_methods").includes(_apiMethod(data, invocation));
    actionClass = writes ? _core(data, "forge_api_class") : null;
  } else if (Object.hasOwn(classes, subcommand)) {
    actionClass = classes[subcommand];
  }
  if (actionClass === null) {
    return null;
  }
  const base = actionClass === "pr_create" ? _pullRequestBase(data, invocation) : null;
  if (base !== null && !_core(data, "git_default_branches").includes(base)) {
    actionClass = "pr_create_other_base";
  }
  return access.result(actionClass, {
    program: invocation.program,
    subcommand: invocation.subcommand,
    base: `'${base}'`,
  });
}

/**
 * What the actor gets for one `git`, `gh` or `glab` command: `null` to pass, else an ask or a deny.
 * @param {HookData} data
 * @param {GitInvocation} invocation
 * @param {_Access} access
 * @param {RepositoryLookup} repositoryAt
 * @returns {HookResult | null}
 */
function _invocationDecision(data, invocation, access, repositoryAt) {
  if (_FORGE_PROGRAMS.includes(invocation.program)) {
    return _forgeDecision(data, invocation, access);
  }
  if (_core(data, "git_publishing_subcommands").includes(invocation.subcommand)) {
    return _publishingDecision(data, invocation, access, repositoryAt);
  }
  if (invocation.subcommand === "config") {
    return _configDecision(data, invocation, access);
  }
  /** @type {HookResult | null} */
  let decision = null;
  if (_core(data, "git_history_subcommands").includes(invocation.subcommand)) {
    const [place, facts] = _historyPlace(invocation.directory, repositoryAt, access);
    decision = access.historyResult(invocation.subcommand, place, facts);
  }
  const target = _refTarget(data, invocation, repositoryAt);
  if (decision !== null || target === null) {
    return decision;
  }
  return access.result("ref_write", { subcommand: _refSubcommand(invocation), target });
}

/** @returns {string | null} */
function _homeDirectory() {
  try {
    return os.homedir() || null;
  } catch {
    return null;
  }
}

/** @returns {string | null} */
function _workingDirectory() {
  try {
    return process.cwd();
  } catch {
    return null;
  }
}

/**
 * Guard `git`, `gh` and `glab` commands by the access matrix: who may write history, publish or open a pull request.
 *
 * What each command gets is `common/access_matrix.json`'s (ADR 0031/D07), by `actor`: the AI
 * co-author trailer is denied wherever it stands in the text, a heredoc body included; only command
 * words are read for the rest ({@link gitInvocations}). For a `developer` — the default, and any
 * run whose `AKMON_ACTOR` the entry point did not read — `push` and `tag` ask everywhere; a
 * history-writing subcommand (`commit`, `merge`, `rebase`, `reset` and the others in
 * `hook_core.json`) passes when the repository it acts on — not the session's — is a linked
 * worktree on a named branch that is not `main`/`master`, and asks otherwise; a ref write asks
 * unless every target is a job branch. An `autonomous` run writes history on its own run branch (the
 * `runBranch` the launcher named, else a branch `run_branch_patterns` matches) or in a linked
 * worktree, pushes that branch by an explicit refspec (a push that names none, or runs under
 * `git -c`, is another branch's), opens pull requests (merge requests) into the default branch, and
 * is denied the default branch, the branches `protected_branches` names for it (`develop`,
 * `release/*`), any other branch of a checkout, any other pull request base and a `git config`
 * write of a push-redirecting key; `gh`/`glab api` writes ask. The first invocation that does not
 * pass decides, and an `ask` nobody attends becomes a `deny`.
 *
 * `directory` is where the command starts (default: the process's); `repositoryAt` answers
 * {@link RepositoryFacts} for a directory (default: {@link repositoryFacts}, which asks git).
 *
 * Policy ID: commits.owner-owned
 * @param {HookData} data
 * @param {unknown} command
 * @param {{permissionMode?: string | null, attended?: boolean | null, actor?: Actor, runBranch?: string | null, directory?: string | null, repositoryAt?: ((directory: string) => {linked: boolean, branch: string} | null) | null}} [options]
 * @returns {HookResult | null}
 */
export function gitCommitGuardResult(
  data,
  command,
  {
    permissionMode = null,
    attended = null,
    actor = ACTORS.DEVELOPER,
    runBranch = null,
    directory = null,
    repositoryAt = null,
  } = {},
) {
  if (!["git", ..._FORGE_PROGRAMS].some((program) => pyContains(command, program))) {
    return null;
  }

  // The AI trailer is a floor: denied for every actor before, and regardless of, the access matrix.
  const trailer = /co-authored-by/i.test(_subject(command));
  if (trailer && pyContains(command, "git")) {
    return _aiTrailerFloor(data, actor);
  }

  const lookup = repositoryAt === null ? repositoryFacts : repositoryAt;
  const start = directory === null ? _workingDirectory() : directory;
  const invocations = gitInvocations(/** @type {string} */ (command), start, { homeDirectory: _homeDirectory() });
  if (trailer && invocations.some((invocation) => _FORGE_PROGRAMS.includes(invocation.program))) {
    return _aiTrailerFloor(data, actor);
  }
  const access = new _Access(data, actor, runBranch);
  for (const invocation of invocations) {
    const decision = _invocationDecision(data, invocation, access, lookup);
    if (decision !== null) {
      return _escalateUnattendedAsk(data, decision, permissionMode, attended);
    }
  }
  return null;
}

// --------------------------------------------------------------------------------------
// SessionStart
// --------------------------------------------------------------------------------------

/**
 * The agent charters (subdirectories with a `README.md`) under `directory`, in roster order.
 *
 * `known` is {@link agentDefinitions}, whose key order is the delivery chain's (ADR 0026/D08): the
 * shipped agents with a charter come first, in that order, then the rest sorted by name. A charter
 * directory named for a role of a shipped agent that has a charter of its own is the legacy layout of
 * that agent (ADR 0026/D06), and is left out so that one agent is not listed twice; with no such
 * charter it is listed as any other.
 * @param {string} directory
 * @param {Record<string, string[]>} [known]
 * @returns {string[]}
 */
export function agentNames(directory, known = {}) {
  const base = pyPath(directory);
  if (!isDir(base)) {
    return [];
  }
  const found = new Set(
    fs
      .readdirSync(base)
      .filter((name) => isDir(pyPath(base, name)) && !name.startsWith(".") && isFile(pyPath(base, name, "README.md"))),
  );
  const shipped = Object.keys(known).filter((agent) => found.has(agent));
  const legacy = new Set(
    shipped.flatMap((agent) => dictItem(known, agent)).filter((role) => !Object.hasOwn(known, role)),
  );
  return [...shipped, ...codePointSort([...found].filter((name) => !shipped.includes(name) && !legacy.has(name)))];
}

// A role a charter names: a reference to the standard's `roles/<role>.md`.
const _CHARTER_ROLE_RE = /roles\/([a-z][a-z0-9_-]*)\.md/gu;

/**
 * The roles of each agent akmon ships, by agent (`agents/agents.json` of this tree).
 *
 * The one owner of the agent -> roles table: `akmon init` writes each charter's sections from the
 * same file (ADR 0026/D06).
 * @param {HookData} data
 * @returns {Record<string, string[]>}
 */
export function agentDefinitions(data) {
  return Object.fromEntries(Object.entries(data.definitions).map(([agent, spec]) => [agent, [...spec.roles]]));
}

/**
 * The roles of `agent`: its definition's when `known` names it, else the charter's own.
 *
 * `known` is {@link agentDefinitions} (ADR 0026/D06). An agent it does not name — a project's own,
 * or a pre-0027 role-named charter directory — falls back: the charter (`directory/<agent>/README.md`)
 * names each role it works in by a reference to `roles/<role>.md` (ADR 0027/D04), and a charter that
 * names none belongs to an agent whose charter directory is its role name (`learn`), so the agent's
 * own name is its one role.
 * @param {string} directory
 * @param {string} agent
 * @param {Record<string, string[]>} known
 * @returns {string[]}
 */
export function agentRoles(directory, agent, known) {
  if (Object.hasOwn(known, agent)) {
    return [...dictItem(known, agent)];
  }
  let text;
  try {
    text = fs.readFileSync(pyPath(directory, agent, "README.md"), "utf8");
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
    return [agent];
  }
  const roles = [...new Set([...text.matchAll(_CHARTER_ROLE_RE)].map((match) => match[1]))];
  return roles.length > 0 ? roles : [agent];
}

/**
 * The agents of `directory` each with its roles, as the session-start roster line names them.
 *
 * `known` is {@link agentDefinitions}: the shipped agents' roles come from it, and only the
 * development layer passes it — a project's runtime agents keep their charters' own roles.
 * @param {string} directory
 * @param {string[]} agents
 * @param {Record<string, string>} start the `session_start` data
 * @param {Record<string, string[]>} known
 * @returns {string}
 */
export function agentRoster(directory, agents, start, known) {
  return agents
    .map((agent) => {
      const roles = agentRoles(directory, agent, known);
      const template = dictItem(start, roles.length === 1 ? "agent_one_role" : "agent_many_roles");
      return fill(template, { agent, roles: roles.join(", ") });
    })
    .join(dictItem(start, "agent_separator"));
}

/**
 * One owner-addressed line when the materialized guardrails are behind the running tree.
 *
 * The interactive half of the freshness guarantee (C77). `sync --check` and `verify` already
 * catch this copy in CI, but they run on a commit; the window this closes opens earlier and
 * closes silently. A pin bump installs the new hooks the instant the dependency resolves — they
 * run from the package — while `<dev root>/.akmon/` still holds the previous release's text
 * until someone runs `akmon sync`.
 *
 * Package execution is the precondition: mounted modes import their guardrails directly from
 * the same mounted tree as the hook, so a leftover package-mode materialization is inactive and
 * must not produce a warning. In package mode the copy is compared against
 * {@link akmonRuntimeRoot}, the tree this hook is executing from, so the answer is about the
 * code actually in play rather than a recorded version string.
 *
 * The restart is part of the instruction, not politeness: the `@`-import is expanded by the
 * harness when the session starts, so running `sync` mid-session fixes the file on disk and
 * changes nothing about the text already in context.
 * @param {HookData} data
 * @param {string} root
 * @returns {string | null}
 */
export function staleGuardrailNotice(data, root) {
  const runtimeRoot = akmonRuntimeRoot(root);
  try {
    if (_resolve(runtimeRoot) === _resolve(pyPath(root, aitnaRootName(root), "akmon"))) {
      return null;
    }
  } catch (error) {
    // SessionStart is advisory and fail-open. A pathological filesystem must not make a
    // hook that cannot prove package execution block or warn about an inactive copy.
    if (!isOSError(error)) {
      throw error;
    }
    return null;
  }
  const names = staleMaterialized(data.materialization, root, runtimeRoot);
  if (names.length === 0) {
    return null;
  }
  return fill(_core(data, "stale_guardrail_notice"), {
    root_name: aitnaRootName(root),
    names: names.join(", "),
  });
}

/**
 * The one SessionStart line naming the work style in force and where it came from (ADR 0031/D03).
 * @param {HookData} data
 * @param {string} root
 * @param {string | null} sessionId
 * @param {any} start the `session_start` table of `hook_core.json`
 * @returns {string}
 */
function _workStyleLine(data, root, sessionId, start) {
  const found = resolveWorkStyle(root, sessionId, data.workStyle);
  const source = fill(dictItem(dictItem(start, "work_style_sources"), found.source), {
    root_name: aitnaRootName(root),
    developer_file: data.workStyle.developer_rel,
  });
  return fill(dictItem(start, "work_style_line"), { style: found.style, source });
}

/**
 * SessionStart guardrail: active-agent declaration reminder, plus a stale-materialization notice.
 *
 * Runtime classification: operational
 * Rationale: it authors no rule. It aggregates the agent roster and re-delivers rules owned
 * elsewhere — role declaration, the memory-read rule, delegation-by-default — at session start,
 * and on Codex it is the only delivery channel for the delegation rule, because `@`-imports are
 * not expanded there (C39). Delivery is not ownership, so the classification stands; without that
 * second fact "operational" would read as "incidental", which it is not.
 * One line states the work style in force for `sessionId` and the level that set it (ADR 0031/D03);
 * when the work-style data cannot be read or has the wrong shape, that line alone is left out.
 * @param {HookData} data
 * @param {string} root
 * @param {string | null} [sessionId]
 * @returns {HookResult | null}
 */
export function sessionStartResult(data, root, sessionId = null) {
  const stale = staleGuardrailNotice(data, root);
  const dev = agentNames(pyPath(root, aitnaRootName(root), "agents"), agentDefinitions(data));
  const desk = agentNames(pyPath(root, "agents"));
  if (dev.length === 0 && desk.length === 0) {
    // A project with no agent charters still has to hear this one: it is about the rules
    // the harness just loaded, not about the roles it did not declare.
    if (stale === null) {
      return null;
    }
    return new HookResult({ eventName: "SessionStart", additionalContext: stale, systemMessage: stale });
  }

  // The line fragments are owned by hooks/hook_core.json (C102); the assembly — which lines
  // appear and in what order — stays here.
  const start = _core(data, "session_start");
  const lines = [dictItem(start, "title"), dictItem(start, "format_line")];
  if (dev.length > 0) {
    lines.push(
      fill(dictItem(start, "develop_line"), {
        agents: agentRoster(pyPath(root, aitnaRootName(root), "agents"), dev, start, agentDefinitions(data)),
      }),
    );
  }
  if (desk.length > 0) {
    lines.push(fill(dictItem(start, "operate_line"), { agents: agentRoster(pyPath(root, "agents"), desk, start, {}) }));
  }
  lines.push(dictItem(start, "no_agent_line"));
  if (dev.length > 0) {
    // The DEVELOP routing discriminator (ADR 0003 §4): give the picking rule up front, not
    // only after a code/planning edit already happened. Keyed by cognitive operation.
    lines.push(dictItem(start, "pick_by_operation"));
  } else {
    lines.push(dictItem(start, "pick_generic"));
  }
  lines.push(dictItem(start, "delegation_line"));
  // The line is advisory: a work-style file that is missing, not JSON or the wrong shape loses the line,
  // never the rest of the session's context.
  try {
    lines.push(_workStyleLine(data, root, sessionId, start));
  } catch (error) {
    if (!(error instanceof DataFileError || ["KeyError", "TypeError"].includes(exceptionClassName(error)))) {
      throw error;
    }
  }
  lines.push(fill(dictItem(start, "memory_line"), { root_name: aitnaRootName(root) }));
  if (stale !== null) {
    lines.push(stale);
  }
  // Dual channel for the stale-guardrail line only (requirement 11): it asks the *owner* for a
  // command and a restart, which the model cannot do for them. The reminder itself stays
  // context-only.
  return new HookResult({
    eventName: "SessionStart",
    additionalContext: lines.join("\n"),
    systemMessage: stale,
  });
}

// --------------------------------------------------------------------------------------
// Path classification
// --------------------------------------------------------------------------------------

/**
 * `os.path.normpath` on a POSIX string: redundant separators and up-level references collapse
 * lexically (never through the filesystem), `""` is `.`, and a leading `//` — exactly two —
 * survives where one or three or more is a single `/`.
 * @param {string} path
 * @returns {string}
 */
export function normpath(path) {
  if (path === "") {
    return ".";
  }
  const initial = path.startsWith("//") && !path.startsWith("///") ? "//" : path.startsWith("/") ? "/" : "";
  /** @type {string[]} */
  const kept = [];
  for (const component of path.split("/")) {
    if (component === "" || component === ".") {
      continue;
    }
    if (component !== ".." || (initial === "" && kept.length === 0) || kept[kept.length - 1] === "..") {
      kept.push(component);
    } else if (kept.length > 0) {
      kept.pop();
    }
  }
  return initial + kept.join("/") || ".";
}

/**
 * The anchor and the components of an already normalized path (`pyPath`'s spelling).
 * @param {string} path
 * @returns {{anchor: string, names: string[]}}
 */
function _split(path) {
  const anchor = path.startsWith("//") ? "//" : path.startsWith("/") ? "/" : "";
  const rest = path.slice(anchor.length);
  return { anchor, names: rest === "" || rest === "." ? [] : rest.split("/") };
}

/**
 * `candidate` as a `root`-relative POSIX path, or `null` when it is not under it — the
 * `PurePath.relative_to(...).as_posix()` of the twin, both arguments in `pyPath`'s spelling.
 * @param {string} candidate
 * @param {string} root
 * @returns {string | null}
 */
function _relativeWithin(candidate, root) {
  const under = _split(candidate);
  const base = _split(root);
  if (under.anchor !== base.anchor || base.names.some((name, i) => under.names[i] !== name)) {
    return null;
  }
  return under.names.slice(base.names.length).join("/") || ".";
}

/**
 * Return a canonical project-relative POSIX path, or `null` outside `root`.
 *
 * Relative hook paths are project-relative (Codex patch bodies), not relative to the hook
 * process, so both forms are anchored to the supplied project root — `.`, `..` and duplicate
 * separators then classify identically. A path that leaves the project is not a project target
 * and must not accidentally match a local planning or D2 pattern.
 *
 * The collapse is **lexical** (`normpath`), not `resolvePath`: resolving follows symlinks, so
 * any symlinked subtree pointing outside the repo — an `_aitna` kept elsewhere, a monorepo's
 * shared source, an `_aitna/akmon` linked at a developer's akmon checkout — landed outside the
 * root and silenced every predicate underneath it. That is the same "did not match is
 * indistinguishable from matched and stayed quiet" failure C47 exists to remove, re-entered
 * through the traversal guard. The resolved comparison survives only as a fallback, for the
 * opposite case: root and payload naming one directory through different symlinked aliases
 * (`/tmp` vs `/private/tmp`, a checkout reached through a linked home). A traversal escapes
 * both, so the guard holds.
 *
 * That guard is **advisory-grade, not containment** (ADR-0012/D01): it stops `..`, but a link
 * inside the tree pointing out of the repository stays lexically inside the root and still
 * classifies as a project target. Catching it would require resolving, which is the silencing
 * failure above. Harmless for reminders — one extra reminder at worst — and not to be inherited
 * as a security property by any deny-class consumer.
 * @param {string} filePath
 * @param {string} root
 * @returns {string | null}
 */
function _projectRelativePosix(filePath, root) {
  const path = pyPath(filePath);
  const absolute = path.startsWith("/");
  const anchored = absolute ? path : pyPath(root, path);
  const lexical = _relativeWithin(pyPath(normpath(anchored)), pyPath(normpath(root)));
  if (lexical !== null) {
    return lexical;
  }
  try {
    const resolvedRoot = _resolve(root);
    const candidate = absolute ? path : pyPath(resolvedRoot, path);
    return _relativeWithin(_resolve(candidate), resolvedRoot);
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
    return null;
  }
}

/**
 * `filePath` in the one form every classifier matches on.
 *
 * Project-relative POSIX, lowercased, with a leading `/`. The classification segments
 * (`/docs/`, `/<aitna>/design/`) are written with surrounding slashes, so matching them against
 * the *raw* string answered "no" for every relative path — and a silent "no" is
 * indistinguishable from "matched and stayed quiet" (C47). The two forms are not hypothetical:
 * Claude Code always sends an absolute `file_path`, while Codex passes through what the patch
 * body carried (`*** Add File: note.txt`), which is repo-relative. Normalizing first makes the
 * answer a property of the file rather than of the vendor's spelling. Stripping the project root
 * also drops a second failure mode — a repo living under a directory called `docs` no longer
 * makes every file in it a non-code path.
 * @param {string} filePath
 * @param {string | null} [root]
 * @returns {string}
 */
export function classifyTarget(filePath, root = null) {
  if (typeof filePath !== "string") {
    throw pyError("AttributeError", `'${pyTypeName(filePath)}' object has no attribute 'replace'`);
  }
  const text = filePath.replaceAll("\\", "/");
  const path = pyPath(text);
  // Preserve the core helper's standalone absolute-path API when no project root was
  // supplied. Real hook wrappers always pass the payload-derived root; callers without
  // one cannot safely decide whether an arbitrary absolute fixture lies outside a project.
  // The pre-C47 unstripped behaviour therefore survives behind this default, and a payload
  // with no `cwd` still reaches `findProjectRoot(null)` → the cwd. Both are accepted
  // (ADR-0012/D01): no wired path takes either branch, and a mandatory `root` would change three
  // signatures without changing a single answer.
  const normalized =
    root === null && path.startsWith("/")
      ? path
      : _projectRelativePosix(text, root === null ? findProjectRoot() : pyPath(root));
  if (normalized === null) {
    return "/__outside_project__";
  }
  const lowered = normalized.toLowerCase();
  return lowered.startsWith("/") ? lowered : `/${lowered}`;
}

/**
 * `Path(target).suffix`: the last dot of the final component, unless it leads or ends it.
 * @param {string} target
 * @returns {string}
 */
function _suffix(target) {
  const name = _split(pyPath(target)).names.at(-1) ?? "";
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot) : "";
}

/**
 * Whether `filePath` is a project code file (not docs/design, and a recognized extension).
 * @param {HookData} data
 * @param {string} filePath
 * @param {string | null} [root]
 * @returns {boolean}
 */
export function isCodePath(data, filePath, root = null) {
  const target = classifyTarget(filePath, root);
  if (_segments(data, "non_code_segments", root).some((segment) => target.includes(segment))) {
    return false;
  }
  return /** @type {string[]} */ (_core(data, "code_extensions")).includes(_suffix(target));
}

/**
 * Owner-facing text for the role-on-code reminder (hooks/hook_core.json, C102).
 * @param {HookData} data
 * @param {string | null} [root]
 * @returns {string}
 */
export function roleOnCodeMessage(data, root = null) {
  const dev = aitnaRootName(root === null ? locateProjectRoot() : root);
  return fill(_core(data, "role_on_code_message"), { tasks: `${dev}/TASKS.md` });
}

/**
 * PreToolUse guardrail: on the first code edit per session, remind to declare the engineer role.
 *
 * Policy ID: role.declaration
 * @param {HookData} data
 * @param {string} toolName
 * @param {unknown} filePath
 * @param {string | null} sessionId
 * @param {string | null} [projectRoot]
 * @returns {HookResult | null}
 */
export function roleOnCodeResult(data, toolName, filePath, sessionId, projectRoot = null) {
  if (toolName !== editTool(data)) {
    return null;
  }
  if (typeof filePath !== "string" || !isCodePath(data, filePath, projectRoot)) {
    return null;
  }

  if (!claimDiagnosticMarker(data.markers, markerKind(data.markers, "role_on_code"), sessionId)) {
    return null;
  }

  return new HookResult({ eventName: "PreToolUse", additionalContext: roleOnCodeMessage(data, projectRoot) });
}

/**
 * Whether `filePath` is a backlog/design/ADR/requirements/process planning doc.
 * @param {HookData} data
 * @param {string} filePath
 * @param {string | null} [root]
 * @returns {boolean}
 */
export function isPlanningDoc(data, filePath, root = null) {
  const target = classifyTarget(filePath, root);
  if (_segments(data, "planning_doc_files", root).some((name) => target.endsWith(name))) {
    return true;
  }
  if (!target.endsWith(".md")) {
    return false;
  }
  return _segments(data, "planning_doc_segments", root).some((segment) => target.includes(segment));
}

/**
 * Owner-facing text for the analysis-before-mutation reminder (hooks/hook_core.json, C102).
 * @param {HookData} data
 * @returns {string}
 */
export function analysisBeforeMutationMessage(data) {
  return _core(data, "analysis_before_mutation_message");
}

/**
 * PreToolUse guardrail: on the first planning-doc edit per session, remind analysis-before-mutation.
 *
 * Policy ID: analysis.before-mutation
 * @param {HookData} data
 * @param {string} toolName
 * @param {unknown} filePath
 * @param {string | null} sessionId
 * @param {string | null} [projectRoot]
 * @returns {HookResult | null}
 */
export function analysisWriteResult(data, toolName, filePath, sessionId, projectRoot = null) {
  if (toolName !== editTool(data)) {
    return null;
  }
  if (typeof filePath !== "string" || !isPlanningDoc(data, filePath, projectRoot)) {
    return null;
  }

  if (!claimDiagnosticMarker(data.markers, markerKind(data.markers, "analysis_guard"), sessionId)) {
    return null;
  }

  return new HookResult({ eventName: "PreToolUse", additionalContext: analysisBeforeMutationMessage(data) });
}

// --------------------------------------------------------------------------------------
// Delegation nudge
// --------------------------------------------------------------------------------------

// The routing rule (guardrails/_common.md § Route by task kind + the SessionStart status line)
// is prose the orchestrator can silently skip mid-task. This counts consecutive orchestrator
// edit/shell/read calls since session start or the last subagent delegation and, past the
// advisory threshold, reminds once per drift episode — a subagent delegation re-arms it.
// Task-kind classification is fuzzy, so the advisory never blocks; but on *sustained* drift past
// a second, higher threshold it graduates to a hard `ask` (its own once-per-episode marker, also
// cleared by a delegation) — the read/sweep class (Read/Grep/Glob) is exactly the class the
// advisory used to miss.
//
// C28d: Claude Code gives a subagent's tool calls the *same* `session_id` as the main chain, so
// without an exemption a subagent's Read/Grep/Glob/Bash calls would charge the shared counter and
// could trip the advisory or the hard `ask` inside a k_* delegate — which has no `Task` tool and
// so cannot act on the nudge at all. Subagent-originated calls are detected via the payload's
// `agent_id` (present only inside a subagent) and are exempted entirely: no counter touch, no
// advisory, no ask.
//
// Calibrated, not guessed (C88, ADR-0006/D02). Replayed over akmon's own Claude sessions (M72),
// the rule this replaced — every call worth 1, advisory at 10, ask at 20 — fired the advisory in
// 10 of 11 sessions and the ask in 10 of 11; 16 of those 17 asks came in a non-default permission
// mode, where an ask escalates to a deny, and 3 of the denies fell on a read. An earlier replay on
// another corpus found the same (M75). A signal that fires in every session measures session
// length. Three corrections, all keyed on the tool kind — the command text is not read (C28(c)):
//
// - **A read weighs half** (`_delegationWeights`, from `hooks/hook_core.json`): a sweep is drift
//   too, but cheaper to undo than an edit.
// - **The opening calls of a stretch are free** (`delegationGrace`): orientation before the
//   first delegation is not yet a failure to delegate.
// - **A read never carries the ask.** In an unattended run the ask is a deny, and
//   a denied look costs the agent the means to find out what it was about to do. The score stays
//   over the threshold, so the ask lands on the next edit or shell call.
//
// At 30 / 120 the same replay fires the advisory in 10 of 11 sessions and the ask in 7 of 11. The
// weights barely move that: from 50 to 120 every weighting tried reaches 7 of 11 (M73), because
// those sessions did run hundreds of calls without a delegation — there the advisory is mostly
// right. What changed is that a read is never denied and the ask comes six times later.

/**
 * The calibrated delegation-drift policy (hooks/hook_core.json, C102).
 * @param {HookData} data
 * @returns {any}
 */
function _delegationPolicy(data) {
  return _core(data, "delegation");
}

/**
 * What one orchestrator call adds to the drift score, by neutral tool kind.
 * @param {HookData} data
 * @returns {Map<string, number>}
 */
function _delegationWeights(data) {
  const weights = dictItem(_delegationPolicy(data), "weights");
  return new Map(Object.entries(weights).map(([stem, value]) => [neutralKind(data, stem), value]));
}

/**
 * `int(os.environ.get(name, ""))`, or `null` where it raises `ValueError`.
 * @param {string} name
 * @returns {bigint | null}
 */
function _envInt(name) {
  try {
    return pyIntBig(process.env[name] ?? "");
  } catch (error) {
    if (/** @type {Error} */ (error).name === "ValueError") {
      return null;
    }
    throw error;
  }
}

/**
 * Calls at the start of a stretch that score nothing.
 * @param {HookData} data
 * @returns {number | bigint} an int of any size, as Python's
 */
function _graceExact(data) {
  const policy = _delegationPolicy(data);
  const value = _envInt(dictItem(policy, "grace_env"));
  if (value === null || value < 0n) {
    return dictItem(policy, "grace");
  }
  return value;
}

/**
 * Calls at the start of a stretch that score nothing (env `AKMON_DELEGATION_GRACE`).
 * @param {HookData} data
 * @returns {number}
 */
export function delegationGrace(data) {
  return Number(_graceExact(data));
}

/**
 * Drift score that triggers the advisory nudge (env `AKMON_DELEGATION_NUDGE_THRESHOLD`).
 * @param {HookData} data
 * @returns {number}
 */
export function delegationNudgeThreshold(data) {
  const policy = _delegationPolicy(data);
  const value = _envInt(dictItem(policy, "nudge_threshold_env"));
  return value !== null && value > 0n ? Number(value) : dictItem(policy, "nudge_threshold");
}

/**
 * Drift score that graduates the nudge to a hard `ask` (env `AKMON_DELEGATION_ASK_THRESHOLD`).
 *
 * Clamped so it never falls below the advisory threshold — an ask below the advisory would be
 * reachable before the advisory itself.
 * @param {HookData} data
 * @returns {number}
 */
export function delegationAskThreshold(data) {
  const policy = _delegationPolicy(data);
  const env = _envInt(dictItem(policy, "ask_threshold_env"));
  const value = env !== null && env > 0n ? Number(env) : dictItem(policy, "ask_threshold");
  return Math.max(value, delegationNudgeThreshold(data));
}

/**
 * `f"{value:g}"` of a float: six significant digits, fixed notation for a decimal exponent in
 * [-4, 6) and exponential outside it, trailing zeros dropped. A tie at the sixth digit rounds
 * half to even on the exact binary value (`toExponential` rounds it up).
 * @param {number} value
 * @returns {string}
 */
export function formatG(value) {
  if (Number.isNaN(value)) {
    return "nan";
  }
  if (!Number.isFinite(value)) {
    return value > 0 ? "inf" : "-inf";
  }
  const sign = value < 0 || Object.is(value, -0) ? "-" : "";
  const magnitude = Math.abs(value);
  // 25 digits show whether the digits after the sixth are exactly "5000…": a double has no
  // nonzero digit that far beyond a seven-digit decimal.
  const wide = magnitude.toExponential(24);
  const [wideMantissa, wideExponent] = wide.split("e");
  const wideDigits = wideMantissa.replace(".", "");
  const isTie = /^50*$/.test(wideDigits.slice(6));
  const rounded =
    isTie && Number(wideDigits[5]) % 2 === 0
      ? `${wideDigits[0]}.${wideDigits.slice(1, 6)}e${wideExponent}`
      : magnitude.toExponential(5);
  const [mantissa, exponentText] = rounded.split("e");
  const exponent = Number(exponentText);
  const digits = mantissa.replace(".", "");
  let body;
  if (exponent >= -4 && exponent < 6) {
    if (exponent >= 0) {
      body = `${digits.slice(0, exponent + 1)}.${digits.slice(exponent + 1)}`;
    } else {
      body = `0.${"0".repeat(-exponent - 1)}${digits}`;
    }
    body = body.includes(".") ? body.replace(/0+$/, "").replace(/\.$/, "") : body;
  } else {
    const significant = mantissa.replace(/0+$/, "").replace(/\.$/, "");
    body = `${significant}e${exponent < 0 ? "-" : "+"}${String(Math.abs(exponent)).padStart(2, "0")}`;
  }
  return sign + body;
}

/**
 * `repr(score)` of a float, as the counter file spells it.
 * @param {number} score
 * @returns {string}
 */
function _floatText(score) {
  if (Object.is(score, -0)) {
    return "-0.0";
  }
  if (Number.isNaN(score)) {
    return "nan";
  }
  if (!Number.isFinite(score)) {
    return score > 0 ? "inf" : "-inf";
  }
  return hookForm(new FloatValue(score));
}

/**
 * The drift-score clause; the `:g` numeric spelling stays code (hooks/hook_core.json, C102).
 * @param {HookData} data
 * @param {number} score
 * @returns {string}
 */
function _driftScoreText(data, score) {
  return fill(_core(data, "drift_score_text"), {
    score: formatG(score),
    grace: String(_graceExact(data)),
  });
}

/**
 * Owner-facing text for the advisory delegation-drift nudge (hooks/hook_core.json, C102).
 * @param {HookData} data
 * @param {number} score
 * @returns {string}
 */
export function delegationNudgeMessage(data, score) {
  return fill(_core(data, "delegation_nudge_message"), {
    drift_score: _driftScoreText(data, score),
    roster: _core(data, "delegation_roster"),
  });
}

/**
 * Owner-facing text for the hard-ask escalation on sustained delegation drift (C102).
 * @param {HookData} data
 * @param {number} score
 * @returns {string}
 */
export function delegationAskMessage(data, score) {
  return fill(_core(data, "delegation_ask_message"), {
    drift_score: _driftScoreText(data, score),
    roster: _core(data, "delegation_roster"),
  });
}

/**
 * A path as `open`/`unlink` take it (`os.fsencode`). An embedded NUL is a `ValueError` in Python —
 * not an `OSError`, so no `suppress(OSError)` below takes it — and an argument error in Node. A
 * session id from a JSON payload can hold a lone surrogate: UTF-8 with `surrogateescape` turns
 * U+DC80–U+DCFF into the raw byte (a name no string spells in Node, so its bytes are returned)
 * and refuses any other with `UnicodeEncodeError`.
 * @param {string} path
 * @returns {string | Buffer}
 */
export function fsPath(path) {
  if (path.includes("\0")) {
    throw pyError("ValueError", "embedded null byte");
  }
  if (!/\p{Surrogate}/u.test(path)) {
    return path;
  }
  /** @type {number[]} */
  const bytes = [];
  for (const character of path) {
    const code = character.codePointAt(0) ?? 0;
    if (code >= 0xdc80 && code <= 0xdcff) {
      bytes.push(code - 0xdc00);
    } else if (code >= 0xd800 && code <= 0xdfff) {
      throw pyError("UnicodeEncodeError", "'utf-8' codec can't encode a surrogate: surrogates not allowed");
    } else {
      bytes.push(...Buffer.from(character, "utf8"));
    }
  }
  return Buffer.from(bytes);
}

/**
 * Refuse a path no filesystem call can take, as Python does.
 * @param {string} path
 * @returns {void}
 */
export function assertEncodablePath(path) {
  fsPath(path);
}

/**
 * `Path.exists()`: a path no filesystem call can take (`ValueError`, which `exists` swallows) is
 * absent.
 * @param {string} path
 * @returns {boolean}
 */
function _exists(path) {
  try {
    return pyStat(fsPath(path)) !== null;
  } catch (error) {
    const name = /** @type {Error} */ (error).name;
    if (name === "ValueError" || name === "UnicodeEncodeError") {
      return false;
    }
    throw error;
  }
}

/**
 * `with contextlib.suppress(OSError): action()` — a filesystem failure is swallowed, any other not.
 * @param {() => void} action
 */
function _suppressOSError(action) {
  try {
    action();
  } catch (error) {
    if (!isOSError(error)) {
      throw error;
    }
  }
}

/**
 * Zero the drift counter and clear both markers on a real delegation.
 * @param {string} counter
 * @param {string} marker
 * @param {string} askMarker
 */
function _resetDelegationCounters(counter, marker, askMarker) {
  _suppressOSError(() => writeText(fsPath(counter), "0"));
  _suppressOSError(() => unlinkMissingOk(fsPath(marker)));
  _suppressOSError(() => unlinkMissingOk(fsPath(askMarker)));
}

/**
 * Read, bump and persist the stretch's call count and drift score; the score after this call.
 * @param {HookData} data
 * @param {string} counter
 * @param {string} toolName
 * @returns {number}
 */
function _updateDelegationCounter(data, counter, toolName) {
  // Two numbers in one file: `seen` is the stretch's calls (the grace is counted in calls),
  // `score` what they were worth. A one-number counter from the previous rule reads as calls
  // with no score yet.
  let seen = 0n;
  let score = 0;
  try {
    const text = readText(fsPath(counter));
    const space = text.indexOf(" ");
    const rawSeen = space < 0 ? text : text.slice(0, space);
    const rawScore = space < 0 ? "" : text.slice(space + 1);
    seen = pyIntBig(rawSeen);
    score = rawScore === "" ? 0 : pyFloat(rawScore);
  } catch (error) {
    // `OSError` and `ValueError` (a malformed number, a file that is not UTF-8) alike.
    const name = /** @type {Error} */ (error).name;
    if (!isOSError(error) && name !== "ValueError" && name !== "UnicodeDecodeError") {
      throw error;
    }
    seen = 0n;
    score = 0;
  }
  seen += 1n;
  if (seen > _graceExact(data)) {
    score += /** @type {number} */ (_delegationWeights(data).get(toolName));
  }
  _suppressOSError(() => writeText(fsPath(counter), `${seen} ${_floatText(score)}`));
  return score;
}

/**
 * The hard ask: fires once per stretch, never on a read.
 * @param {HookData} data
 * @param {number} score
 * @param {string} toolName
 * @param {string} askMarker
 * @param {{permissionMode: string | null, attended: boolean | null}} options
 * @returns {HookResult | null}
 */
function _delegationAskResult(data, score, toolName, askMarker, { permissionMode, attended }) {
  // A read never carries the ask and does not spend it; the next edit or shell call does.
  if (_exists(askMarker) || toolName === readTool(data)) {
    return null;
  }
  _suppressOSError(() => writeText(fsPath(askMarker), "seen"));
  return _escalateUnattendedAsk(
    data,
    new HookResult({
      eventName: "PreToolUse",
      permissionDecision: "ask",
      permissionReason: delegationAskMessage(data, score),
    }),
    permissionMode,
    attended,
  );
}

/**
 * The soft nudge: fires once per stretch, below the hard-ask threshold.
 * @param {HookData} data
 * @param {number} score
 * @param {string} marker
 * @returns {HookResult | null}
 */
function _delegationSoftNudgeResult(data, score, marker) {
  if (_exists(marker)) {
    return null;
  }
  _suppressOSError(() => writeText(fsPath(marker), "seen"));
  return new HookResult({ eventName: "PreToolUse", additionalContext: delegationNudgeMessage(data, score) });
}

/**
 * PreToolUse guardrail: nudge, then hard-ask, on sustained orchestrator delegation drift.
 *
 * Policy ID: delegation.tier-floor
 * @param {HookData} data
 * @param {string} toolName
 * @param {string | null} sessionId
 * @param {{isSubagent?: boolean, permissionMode?: string | null, attended?: boolean | null}} [options]
 * @returns {HookResult | null}
 */
export function delegationNudgeResult(
  data,
  toolName,
  sessionId,
  { isSubagent = false, permissionMode = null, attended = null } = {},
) {
  // C28d: subagent-originated calls (agent_id present in the payload) must never touch
  // the counter. k_* delegates can't delegate (no Task tool), so nudging/asking them is
  // noise and the hard ask blocks their legit reads. The session_id is shared with the
  // main chain, so without this guard a subagent's reads charge the orchestrator's counter.
  if (isSubagent) {
    return null;
  }

  const sid = sessionId || unidentifiedIdentity(data.markers);
  const tempdir = gettempdir();
  const counter = pyPath(tempdir, delegationStateName(data.markers, "counter", sid));
  const marker = pyPath(tempdir, delegationStateName(data.markers, "marker", sid));
  const askMarker = pyPath(tempdir, delegationStateName(data.markers, "ask_marker", sid));

  if (toolName === subagentTool(data)) {
    _resetDelegationCounters(counter, marker, askMarker);
    return null;
  }
  if (!_delegationWeights(data).has(toolName)) {
    return null;
  }

  const score = _updateDelegationCounter(data, counter, toolName);

  if (score >= delegationAskThreshold(data)) {
    return _delegationAskResult(data, score, toolName, askMarker, { permissionMode, attended });
  }
  if (score >= delegationNudgeThreshold(data)) {
    return _delegationSoftNudgeResult(data, score, marker);
  }
  return null;
}
