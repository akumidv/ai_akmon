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

import { fill } from "../common/jsondata.mjs";
import { FloatValue, hookForm } from "../common/json_writer.mjs";
import {
  claimDiagnosticMarker,
  delegationStateName,
  gettempdir,
  markerKind,
  unidentifiedIdentity,
} from "../common/markers.mjs";
import { staleMaterialized } from "../common/materialization.mjs";
import { aitnaRootName, findProjectRoot, resolvePath } from "../common/project_root.mjs";
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
import { TREE_ROOT } from "./hook_data.mjs";

/** @typedef {import("./hook_data.mjs").HookData} HookData */

export { aitnaRootName, findProjectRoot };

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
 * (`<AITNA_ROOT>/model-routing.json`) is still layered onto whatever registry this tree
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
  const mount = pyPath(projectRoot, aitnaRootName(), "akmon");
  try {
    if (_resolve(akmonRuntimeRoot(projectRoot)) === _resolve(mount)) {
      return `${aitnaRootName()}/akmon`;
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
 * It is written inside a crash handler, so it reads nothing that can raise — the dev-layer
 * name is an environment lookup with a default, not a filesystem question, and the text is
 * code, not data.
 *
 * Runtime classification: operational
 * Rationale: the owner-facing half of the same crash report (ADR-0013/D01) — it states that a
 * hook was skipped and names the recovery command, and authors no guardrail rule. An adapter
 * renders it into the vendor's owner channel, so ADR-0012/D07 requires this classification on it
 * even though it sits outside the `*Result` join.
 * @param {string} hookName
 * @param {unknown} exc
 * @returns {string}
 */
export function hookFailureNotice(hookName, exc) {
  return (
    `⚠ akmon: the ${hookName} hook failed (${exceptionClassName(exc)}) and was skipped — this action ` +
    `went ahead without it. Check the setup: \`akmon verify\` (a mounted tree: ` +
    `\`python3 ${aitnaRootName()}/akmon/bin/verify.py\`).`
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
 * @returns {string[]}
 */
function _segments(data, key) {
  const aitna = aitnaRootName().toLowerCase();
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

// ask->deny escalation for unattended sessions (C31, ADR-0006/D02). A live test
// showed a hook-forced `ask` is a silent no-op — no prompt, no block — in a Claude Code
// background/child session running in `acceptEdits` mode; the PreToolUse payload carries a
// `permission_mode` field (same enum on Codex) that tells a hook whether an interactive
// owner is actually there to answer. Only the strict `default` mode is known to gate on
// `ask`; everywhere else (or the field missing outright) the owner asked to be stricter
// rather than silently pass through, so the decision is escalated to a hard `deny` — the one
// decision every vendor is confirmed to enforce unconditionally.

/**
 * @param {HookData} data
 * @param {HookResult} result
 * @param {string | null} permissionMode
 * @returns {HookResult}
 */
function _escalateUnattendedAsk(data, result, permissionMode) {
  if (result.permissionDecision !== "ask" || permissionMode === _core(data, "interactive_default_permission_mode")) {
    return result;
  }
  const suffix = fill(_core(data, "escalated_ask_suffix"), { permission_mode: pyRepr(permissionMode) });
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
 * Deny any Bash command that invokes `sudo`, unconditionally.
 *
 * The agent runs as an unprivileged user by design; a command reaching for `sudo` is either
 * probing for elevated access or trying to route around a permission boundary that exists on
 * purpose (e.g. a root-owned file). Neither is something the agent decides for itself — if
 * elevated access is genuinely needed, the owner runs it themselves. No ask: the answer does not
 * depend on session attentiveness, so there is nothing to escalate.
 *
 * Policy ID: privilege.no-escalation
 * @param {HookData} data
 * @param {unknown} command
 * @returns {HookResult | null}
 */
export function privilegeEscalationGuardResult(data, command) {
  if (!_SUDO_RE.test(_subject(command))) {
    return null;
  }
  return new HookResult({
    eventName: "PreToolUse",
    permissionDecision: "deny",
    permissionReason: _core(data, "privilege_escalation_reason"),
  });
}

/**
 * Guard commit-shaped `git` commands: no AI co-author trailer, owner confirms landing history.
 *
 * Policy ID: commits.owner-owned
 * @param {HookData} data
 * @param {unknown} command
 * @param {string | null} [branch] the current branch (default: asked of git)
 * @param {{permissionMode?: string | null}} [options]
 * @returns {HookResult | null}
 */
export function gitCommitGuardResult(data, command, branch = null, { permissionMode = null } = {}) {
  if (!pyContains(command, "git")) {
    return null;
  }

  if (/co-authored-by/i.test(_subject(command))) {
    return new HookResult({
      eventName: "PreToolUse",
      permissionDecision: "deny",
      permissionReason: _core(data, "git_commit_no_ai_trailer_reason"),
    });
  }

  const isGit = (/** @type {string} */ subcommand) =>
    new RegExp(`\\bgit\\b[^|&;]*\\b${subcommand}\\b`).test(_subject(command));

  if (isGit("push") || isGit("tag") || isGit("merge")) {
    return _escalateUnattendedAsk(
      data,
      new HookResult({
        eventName: "PreToolUse",
        permissionDecision: "ask",
        permissionReason: _core(data, "git_commit_push_tag_merge_reason"),
      }),
      permissionMode,
    );
  }

  if (isGit("commit")) {
    const resolvedBranch = branch === null ? currentGitBranch() : branch;
    if (resolvedBranch === "main" || resolvedBranch === "master" || !resolvedBranch) {
      return _escalateUnattendedAsk(
        data,
        new HookResult({
          eventName: "PreToolUse",
          permissionDecision: "ask",
          permissionReason: fill(_core(data, "git_commit_landing_reason"), {
            branch: resolvedBranch || _core(data, "git_commit_detached_head"),
          }),
        }),
        permissionMode,
      );
    }
  }

  return null;
}

// --------------------------------------------------------------------------------------
// SessionStart
// --------------------------------------------------------------------------------------

/**
 * Sorted names of the agent charters (subdirectories with a `README.md`) under `directory`.
 * @param {string} directory
 * @returns {string[]}
 */
export function agentNames(directory) {
  const base = pyPath(directory);
  if (!isDir(base)) {
    return [];
  }
  return codePointSort(
    fs
      .readdirSync(base)
      .filter(
        (name) =>
          isDir(pyPath(base, name)) && !name.startsWith(".") && isFile(pyPath(base, name, "README.md")),
      ),
  );
}

/**
 * One owner-addressed line when the materialized guardrails are behind the running tree.
 *
 * The interactive half of the freshness guarantee (C77). `sync --check` and `verify` already
 * catch this copy in CI, but they run on a commit; the window this closes opens earlier and
 * closes silently. A pin bump installs the new hooks the instant the dependency resolves — they
 * run from the package — while `<AITNA_ROOT>/.akmon/` still holds the previous release's text
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
    if (_resolve(runtimeRoot) === _resolve(pyPath(root, aitnaRootName(), "akmon"))) {
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
    root_name: aitnaRootName(),
    names: names.join(", "),
  });
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
 * @param {HookData} data
 * @param {string} root
 * @returns {HookResult | null}
 */
export function sessionStartResult(data, root) {
  const stale = staleGuardrailNotice(data, root);
  const dev = agentNames(pyPath(root, aitnaRootName(), "agents"));
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
    lines.push(fill(dictItem(start, "develop_line"), { agents: dev.join(", ") }));
  }
  if (desk.length > 0) {
    lines.push(fill(dictItem(start, "operate_line"), { agents: desk.join(", ") }));
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
  lines.push(fill(dictItem(start, "memory_line"), { root_name: aitnaRootName() }));
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
  if (_segments(data, "non_code_segments").some((segment) => target.includes(segment))) {
    return false;
  }
  return /** @type {string[]} */ (_core(data, "code_extensions")).includes(_suffix(target));
}

/**
 * Owner-facing text for the role-on-code reminder (hooks/hook_core.json, C102).
 * @param {HookData} data
 * @returns {string}
 */
export function roleOnCodeMessage(data) {
  return fill(_core(data, "role_on_code_message"), { tasks: `${aitnaRootName()}/TASKS.md` });
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

  return new HookResult({ eventName: "PreToolUse", additionalContext: roleOnCodeMessage(data) });
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
  if (_segments(data, "planning_doc_files").some((name) => target.endsWith(name))) {
    return true;
  }
  if (!target.endsWith(".md")) {
    return false;
  }
  return _segments(data, "planning_doc_segments").some((segment) => target.includes(segment));
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
// - **A read never carries the ask.** Outside the interactive default mode the ask is a deny, and
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
 * @param {string | null} permissionMode
 * @returns {HookResult | null}
 */
function _delegationAskResult(data, score, toolName, askMarker, permissionMode) {
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
 * @param {{isSubagent?: boolean, permissionMode?: string | null}} [options]
 * @returns {HookResult | null}
 */
export function delegationNudgeResult(data, toolName, sessionId, { isSubagent = false, permissionMode = null } = {}) {
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
    return _delegationAskResult(data, score, toolName, askMarker, permissionMode);
  }
  if (score >= delegationNudgeThreshold(data)) {
    return _delegationSoftNudgeResult(data, score, marker);
  }
  return null;
}
