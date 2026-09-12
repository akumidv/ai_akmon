"""Vendor-neutral akmon hook decisions.

This module contains the guardrail logic only. Vendor entrypoints adapt their incoming
payload and serialize ``HookResult`` into the shape their runtime expects.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

# Where the dev layer is, what it is called, and how the project root is found are not this
# module's facts — they belong to ``common.project_root``, which is stdlib-only and sits
# beside ``hooks/`` at the same tree-relative path in every carrier the hooks run from: the
# mounted ``<AITNA_ROOT>/akmon/`` tree and the wheel's embedded ``akmon/_tree/``. The copy that
# used to live here answered the same questions in the same words and was the last remaining
# second definition (C73).
# This file's own tree root. Every carrier keeps a hook and the data it reads in one tree —
# the mounted ``<AITNA_ROOT>/akmon/``, and the wheel's embedded ``akmon/_tree/`` — so this is
# both the import anchor for ``common`` and the answer to "which tree is running" below.
_TREE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TREE_ROOT))

from common.materialization import stale_guardrails  # noqa: E402
from common.project_root import (  # noqa: E402
    aitna_root,
    aitna_root_name,
    akmon_mount,
    find_project_root,
)
from common.record import read_akmon_toml  # noqa: E402


def akmon_runtime_root(project_root: Path) -> Path:
    """Runtime files used by hooks: **the tree this hook is executing from**.

    Each carrier ships a hook and its data together, so the hook's own location answers the
    question without asking anything: the mounted tree when the wiring named a file there, and
    the wheel's embedded ``akmon/_tree`` when the wiring called ``akmon hook`` (C77). No
    record read, no directory probe, and no way for the two to disagree.

    This replaces the record-vetoes-the-directory rule (C69/D2-26), which was correct only while
    mode ``package`` copied the hooks — and the whole runtime surface they read — into
    ``<AITNA_ROOT>/.akmon/``. With the materialization narrowed to the guardrails the
    consumer's ``AGENTS.md`` imports, that directory holds no registry at all, and pointing
    here would have made the routing hook's "no registry, older pin — stay silent" guard fire on
    every session: status line and delegation log gone, exit code 0, stderr empty.

    What the old rule defended against is gone rather than given up: a stale
    ``<AITNA_ROOT>/akmon`` from a prior mode cannot shadow anything, because a tree that is not
    executing is not a candidate.

    ``project_root`` stays in the signature: the project overlay it locates
    (``<AITNA_ROOT>/model-routing.json``) is still layered onto whatever registry this tree
    carries, and callers pass the pair together.
    """
    del project_root  # the carrier answers; the project only supplies the overlay on top of it
    return _TREE_ROOT


def runtime_root_display(project_root: Path) -> str:
    """How to *spell* the runtime tree in something an agent will run.

    Project-relative when the executing tree **is the project's mount** — the spelling the
    session already reads everywhere else. ``$(akmon path)`` otherwise.

    The test is "is it the mount", deliberately, not "is it somewhere under the project root".
    The two are not the same and the difference was measured on a real package-mode consumer:
    the wheel's tree sits at ``<project>/.venv/lib/python3.14/site-packages/akmon/_tree``, which
    *is* under the root, so a containment test spelled the recovery command with the venv's
    Python version in it — a command that breaks on the next interpreter bump and on every
    other machine, printed to the one person trying to recover. ``akmon path`` is the CLI's own
    answer to the same question and stays true wherever the venv is.
    """
    mount = akmon_mount(project_root)
    try:
        if akmon_runtime_root(project_root).resolve() == mount.resolve():
            return f"{aitna_root_name()}/akmon"
    except OSError:  # pragma: no cover - resolve() only raises on pathological filesystems
        pass
    return "$(akmon path)"


@dataclass(frozen=True)
class HookResult:
    event_name: str
    additional_context: str | None = None
    permission_decision: str | None = None
    permission_reason: str | None = None
    system_message: str | None = None


_CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".hpp",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".php",
        ".sh",
        ".bash",
        ".zsh",
        ".sql",
        ".r",
        ".jl",
        ".lua",
        ".dart",
        ".m",
        ".mm",
    }
)
# Path-classification segments are derived from the configured dev-layer root (default
# ``_aitna``) so relocating it via AITNA_ROOT keeps the code/planning-doc detection correct.
# These match lowercased path *substrings*, so the segment uses the lowercased root name.
def _non_code_segments() -> tuple[str, ...]:
    aitna = aitna_root_name().lower()
    return (
        "/docs/",
        f"/{aitna}/design/",
        f"/{aitna}/memory/",
        f"/{aitna}/akmon/",
        f"/{aitna}/.akmon/",
        "/.claude/",
    )


# Neutral tool-kind: each vendor adapter normalizes its own file-editing tool name(s) to this
# token before calling. The core stays vendor-clean — it never names a vendor's tools.
EDIT_TOOL = "edit"
_EDIT_TOOL_KINDS = frozenset({EDIT_TOOL})
# Further neutral kinds for the delegation nudge: a shell/command tool, a read/sweep tool
# (Read/Grep/Glob), and the vendor's subagent-delegation tool.
SHELL_TOOL = "shell"
READ_TOOL = "read"
SUBAGENT_TOOL = "subagent"


def claim_diagnostic_marker(kind: str, identity: str | None) -> bool:
    """Atomically claim one stderr diagnostic for ``identity``; True means "emit now".

    Two throttle domains, deliberately different and stated here because the difference reads
    as an inconsistency otherwise (D2-19 c, D2-21 a):

    - **route-level** diagnostics describe what a *route* can do, so they throttle by session
      id — one statement per session, even though a later call on the same route is silent;
    - **event-level** diagnostics report a defect in one call, so they throttle by a
      session/tool-use pair — a second malformed call stays visible.

    An absent or unreliable identity repeats instead of claiming a shared ``nosession``
    marker, which would let one early session hide every later gap. The name is hashed so a
    session id containing ``/`` cannot escape the tempdir — not for secrecy: the three
    advisory markers in this module still carry a literal session id, which is the convention
    gap C36(a) owns (D2-21 b). Marker lifecycle — stale files outliving their session, and
    migrating those three onto this helper — is the rest of C36(a).
    """
    if not identity or identity == "nosession":
        return True  # no identity to throttle by: repeat rather than hide the diagnostic
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    marker = Path(tempfile.gettempdir()) / f"akmon-{kind}-{digest}"
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    except OSError:
        return True  # marker failure must make the diagnostic noisier, never invisible
    try:
        os.close(descriptor)
    except OSError:
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return True
    return True


UNCLASSIFIED_SHELL_ROUTE_NOTICE = (
    "akmon hook: a shell call may mutate the filesystem, but the path-keyed advisories cannot "
    "classify this route; hook-process stderr diagnostic only — role-on-code, analysis-guard "
    "and the D2 reminder receive no inferred target"
)


def report_unclassified_shell_route(session_id: str | None) -> None:
    """Say once per session that a shell call has effects the advisories cannot classify.

    The advisories key off a path; a shell call carries a command, and reading a path out of a
    command string is a guess — so this route is *reported*, never classified. It states the
    route's capability, not a guessed effect (C49).

    Vendor-neutral by owner decision at D2-19(e): the blind spot is not Codex's. On Claude the
    same effect reaches the filesystem through ``Bash`` while the advisories sit on the edit
    tools, so the route was not merely unclassified there — it was unreported. Both vendors now
    emit one message from one implementation, because two copies of a diagnostic are two things
    that can drift into disagreeing about what akmon can see.

    Never blocks and never becomes model context: every caller keeps its exit code. Whether a
    harness surfaces hook stderr to the owner is unverified on both vendors and is not claimed.
    """
    if claim_diagnostic_marker("shell-route", session_id):
        print(UNCLASSIFIED_SHELL_ROUTE_NOTICE, file=sys.stderr)


# Planning / design docs — editing one may be an analysis-only turn that needs confirmation
# first (see guardrails/_common.md § Analysis before mutation).
def _planning_doc_segments() -> tuple[str, ...]:
    aitna = aitna_root_name().lower()
    return (
        f"/{aitna}/design/",
        "/docs/dev/",
        f"/{aitna}/akmon/",
        f"/{aitna}/.akmon/",
    )


def _planning_doc_files() -> tuple[str, ...]:
    aitna = aitna_root_name().lower()
    return (f"/{aitna}/tasks.md", f"/{aitna}/tasks_archive.md")


def current_git_branch() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""



# ask->deny escalation for unattended sessions (C31/D2-10, owner decision). A live test
# showed a hook-forced `ask` is a silent no-op — no prompt, no block — in a Claude Code
# background/child session running in `acceptEdits` mode; the PreToolUse payload carries a
# `permission_mode` field (same enum on Codex) that tells a hook whether an interactive
# owner is actually there to answer. Only the strict `default` mode is known to gate on
# `ask`; everywhere else (or the field missing outright) the owner asked to be stricter
# rather than silently pass through, so the decision is escalated to a hard `deny` — the one
# decision every vendor is confirmed to enforce unconditionally.
_INTERACTIVE_DEFAULT_PERMISSION_MODE = "default"


def _escalate_unattended_ask(result: HookResult, permission_mode: str | None) -> HookResult:
    if result.permission_decision != "ask" or permission_mode == _INTERACTIVE_DEFAULT_PERMISSION_MODE:
        return result
    return HookResult(
        event_name=result.event_name,
        additional_context=result.additional_context,
        permission_decision="deny",
        permission_reason=(
            f"{result.permission_reason} [escalated ask→deny: permission_mode="
            f"{permission_mode!r} is not the interactive default, so 'ask' cannot be trusted "
            "to reach the owner (D2-10/C31) — re-run from an attended default-mode session if "
            "this was genuinely intended.]"
        ),
        system_message=result.system_message,
    )


_SUDO_RE = re.compile(r"\bsudo\b")


def privilege_escalation_guard_result(command: str) -> HookResult | None:
    """Deny any Bash command that invokes ``sudo``, unconditionally.

    The agent runs as an unprivileged user by design; a command reaching for ``sudo`` is
    either probing for elevated access or trying to route around a permission boundary that
    exists on purpose (e.g. a root-owned file). Neither is something the agent decides for
    itself — if elevated access is genuinely needed, the owner runs it themselves. No ask:
    the answer does not depend on session attentiveness, so there is nothing to escalate.
    """
    if not _SUDO_RE.search(command):
        return None
    return HookResult(
        event_name="PreToolUse",
        permission_decision="deny",
        permission_reason="Privilege-escalation guardrail: 'sudo' is never run by the agent. "
        "If elevated access is genuinely required, ask the owner to run the command themselves.",
    )


def git_commit_guard_result(
    command: str, branch: str | None = None, *, permission_mode: str | None = None
) -> HookResult | None:
    if "git" not in command:
        return None

    if re.search(r"co-authored-by", command, re.IGNORECASE):
        return HookResult(
            event_name="PreToolUse",
            permission_decision="deny",
            permission_reason="Commit guardrail: no AI 'Co-Authored-By' trailer — the committer is "
            "the human. Remove it and retry.",
        )

    def is_git(subcommand: str) -> bool:
        return re.search(r"\bgit\b[^|&;]*\b" + subcommand + r"\b", command) is not None

    if is_git("push") or is_git("tag") or is_git("merge"):
        return _escalate_unattended_ask(
            HookResult(
                event_name="PreToolUse",
                permission_decision="ask",
                permission_reason="Commit guardrail: the owner owns commits. push/tag/merge land "
                "history — confirm this is explicitly requested.",
            ),
            permission_mode,
        )

    if is_git("commit"):
        resolved_branch = current_git_branch() if branch is None else branch
        if resolved_branch in ("main", "master") or not resolved_branch:
            return _escalate_unattended_ask(
                HookResult(
                    event_name="PreToolUse",
                    permission_decision="ask",
                    permission_reason=f"Commit guardrail: the owner owns commits. A commit on "
                    f"'{resolved_branch or 'detached HEAD'}' is a landing commit — confirm "
                    "explicitly, or branch to backup/* first.",
                ),
                permission_mode,
            )

    return None


def agent_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(
        item.name
        for item in directory.iterdir()
        if item.is_dir() and not item.name.startswith(".") and (item / "README.md").is_file()
    )


def stale_guardrail_notice(root: Path) -> str | None:
    """One owner-addressed line when the materialized guardrails are behind the running tree.

    The interactive half of the freshness guarantee (C77). ``sync --check`` and ``verify``
    already catch this copy in CI, but they run on a commit; the window this closes opens
    earlier and closes silently. A pin bump installs the new hooks the instant the dependency
    resolves — they run from the package — while ``<AITNA_ROOT>/.akmon/guardrails/`` still
    holds the previous release's text until someone runs ``akmon sync``. Nothing in a session
    would otherwise say that the always-on rules loaded from the repository are not the rules
    the running standard ships.

    Package execution is the precondition: mounted modes import their guardrails directly from
    the same mounted tree as the hook, so a leftover package-mode materialization is inactive
    and must not produce a warning. In package mode the copy is compared against
    :func:`akmon_runtime_root`, the tree this hook is executing from, so the answer is about the
    code actually in play rather than a recorded version string: a release that leaves the
    guardrails untouched stays quiet, and a hand-edited copy does not.

    The restart is part of the instruction, not politeness: the ``@``-import is expanded by the
    harness when the session starts, so running ``sync`` mid-session fixes the file on disk and
    changes nothing about the text already in context.
    """
    runtime_root = akmon_runtime_root(root)
    try:
        if runtime_root.resolve() == akmon_mount(root).resolve():
            return None
    except OSError:
        # SessionStart is advisory and fail-open. A pathological filesystem must not make a
        # hook that cannot prove package execution block or warn about an inactive copy.
        return None
    names = stale_guardrails(root, runtime_root)
    if not names:
        return None
    return (
        f"\u26a0 akmon: the guardrails in {aitna_root_name()}/.akmon/guardrails/ are not the ones "
        f"this session's akmon ships ({', '.join(names)}). Run `akmon sync`, then start a new "
        "session — the guardrail text is @-imported once at session start, so this session keeps "
        "the stale copy."
    )


def session_start_result(root: Path) -> HookResult | None:
    stale = stale_guardrail_notice(root)
    dev = agent_names(aitna_root(root) / "agents")
    desk = agent_names(root / "agents")
    if not dev and not desk:
        # A project with no agent charters still has to hear this one: it is about the rules
        # the harness just loaded, not about the roles it did not declare.
        if stale is None:
            return None
        return HookResult(event_name="SessionStart", additional_context=stale, system_message=stale)

    lines = [
        "[akmon] Active-agent declaration",
        "Before doing project work, state which agent you are operating as, and restate it "
        "whenever you switch. Format: `\U0001f9ed agent: <name> — <focus>`.",
    ]
    if dev:
        lines.append(f"- DEVELOP (build the project): {', '.join(dev)}")
    if desk:
        lines.append(f"- OPERATE (run/use from outside): {', '.join(desk)}")
    lines.append("No agent is active yet.")
    if dev:
        # The DEVELOP routing discriminator (ADR 0003 §4): give the picking rule up front, not
        # only after a code/planning edit already happened. Keyed by cognitive operation.
        lines.append(
            "Pick by operation: decompose an existing thing → review · construct a new "
            "structure/decision → architect · realize a decided structure in code → engineer. "
            "If unclear, ask."
        )
    else:
        lines.append("Pick the one the task calls for; if unclear, ask.")
    lines.append(
        "Delegation is the default for non-atomic work: before the first repository sweep, edit, "
        "or test run, decompose the task and delegate every independent sub-step to available "
        "subagents. Keep only decomposition, routing, synthesis, and owner dialogue in the "
        "orchestrator. Skip delegation only when the task is atomic or the harness exposes no "
        "subagents; state the reason."
    )
    lines.append(f"Also: read `{aitna_root_name()}/memory/` at session start (project memory).")
    if stale is not None:
        lines.append(stale)
    # Dual channel for the stale-guardrail line only (requirement 11): it asks the *owner* for a
    # command and a restart, which the model cannot do for them. The reminder itself stays
    # context-only.
    return HookResult(
        event_name="SessionStart",
        additional_context="\n".join(lines),
        system_message=stale,
    )


def _relative_within(candidate: Path, root: Path) -> str | None:
    """``candidate`` as a ``root``-relative POSIX path, or ``None`` when it is not under it."""
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return None


def _project_relative_posix(file_path: str, root: Path) -> str | None:
    """Return a canonical project-relative POSIX path, or ``None`` outside ``root``.

    Relative hook paths are project-relative (Codex patch bodies), not relative to the hook
    process, so both forms are anchored to the supplied project root — ``.``, ``..`` and
    duplicate separators then classify identically. A path that leaves the project is not a
    project target and must not accidentally match a local planning or D2 pattern.

    The collapse is **lexical** (``os.path.normpath``), not ``Path.resolve()``: resolving
    follows symlinks, so any symlinked subtree pointing outside the repo — an ``_aitna``
    kept elsewhere, a monorepo's shared source, an ``_aitna/akmon`` linked at a developer's
    akmon checkout — landed outside the root and silenced every predicate underneath it.
    That is the same "did not match is indistinguishable from matched and stayed quiet"
    failure C47 exists to remove, re-entered through the traversal guard. The resolved
    comparison survives only as a fallback, for the opposite case: root and payload naming
    one directory through different symlinked aliases (``/tmp`` vs ``/private/tmp``, a
    checkout reached through a linked home). A traversal escapes both, so the guard holds.

    That guard is **advisory-grade, not containment** (D2-17 d): it stops ``..``, but a link
    inside the tree pointing out of the repository stays lexically inside the root and still
    classifies as a project target. Catching it would require resolving, which is the
    silencing failure above. Harmless for reminders — one extra reminder at worst — and not
    to be inherited as a security property by any deny-class consumer.
    """
    path = Path(file_path)
    anchored = path if path.is_absolute() else root / path
    lexical = _relative_within(Path(os.path.normpath(anchored)), Path(os.path.normpath(root)))
    if lexical is not None:
        return lexical
    try:
        resolved_root = root.resolve(strict=False)
        candidate = path if path.is_absolute() else resolved_root / path
        return _relative_within(candidate.resolve(strict=False), resolved_root)
    except OSError:
        return None


def classify_target(file_path: str, root: Path | None = None) -> str:
    """``file_path`` in the one form every classifier matches on: project-relative POSIX,
    lowercased, with a leading ``/``.

    The classification segments (``/docs/``, ``/<aitna>/design/``) are written with
    surrounding slashes, so matching them against the *raw* string answered "no" for every
    relative path — and a silent "no" is indistinguishable from "matched and stayed quiet"
    (C47). The two forms are not hypothetical: Claude Code always sends an absolute
    ``file_path``, while Codex passes through what the patch body carried
    (``*** Add File: note.txt``), which is repo-relative. Normalizing first makes the answer
    a property of the file rather than of the vendor's spelling. Stripping the project root
    also drops a second failure mode — a repo living under a directory called ``docs`` no
    longer makes every file in it a non-code path.
    """
    text = file_path.replace("\\", "/")
    path = Path(text)
    # Preserve the core helper's standalone absolute-path API when no project root was
    # supplied. Real hook wrappers always pass the payload-derived root; callers without
    # one cannot safely decide whether an arbitrary absolute fixture lies outside a project.
    # The pre-C47 unstripped behaviour therefore survives behind this default, and a payload
    # with no `cwd` still reaches `find_project_root(None)` → `Path.cwd()`. Both are accepted
    # (D2-17 a): no wired path takes either branch, and a mandatory `root` would change three
    # signatures without changing a single answer.
    if root is None and path.is_absolute():
        normalized = path.as_posix()
    else:
        normalized = _project_relative_posix(text, root if root is not None else find_project_root())
    if normalized is None:
        return "/__outside_project__"
    lowered = normalized.lower()
    return lowered if lowered.startswith("/") else f"/{lowered}"


def is_code_path(file_path: str, root: Path | None = None) -> bool:
    target = classify_target(file_path, root)
    if any(segment in target for segment in _non_code_segments()):
        return False
    return Path(target).suffix in _CODE_EXTENSIONS


def role_on_code_message() -> str:
    tasks = f"{aitna_root_name()}/TASKS.md"
    return (
        "[akmon] Role check — you are editing project code.\n"
        "Editing code is **realization** → the `engineer` role. Discriminator: decompose an "
        "existing thing → `review` · construct a new structure/decision → `architect` · "
        "realize a decided structure in code → `engineer`. If you were assessing (`review`) or "
        "designing (`architect`) — or no role is declared — this is a switch: declare "
        "`\U0001f9ed agent: engineer — <focus>` and follow its pipeline (code-flow + pre-commit: "
        "tests + lint mandatory before \"done\") before continuing. "
        "Restate the role on every switch (roles/README.md).\n"
        "Design→code hand-off: before writing code, confirm the task is **landed in "
        f"`{tasks}`** with a link to its design (design-flow step 8 Hand-off), and **re-read "
        "the backlog** to sequence it against other work (code-flow step 1 Take) — a cold engineer "
        f"session must be able to pick this task from `{tasks}` alone."
    )


def role_on_code_result(
    tool_name: str, file_path: str | None, session_id: str | None, project_root: Path | None = None
) -> HookResult | None:
    if tool_name not in _EDIT_TOOL_KINDS:
        return None
    if not isinstance(file_path, str) or not is_code_path(file_path, project_root):
        return None

    marker = Path(tempfile.gettempdir()) / f"akmon-role-on-code-{session_id or 'nosession'}.marker"
    if marker.exists():
        return None
    try:
        marker.write_text("seen", encoding="utf-8")
    except OSError:
        pass

    return HookResult(event_name="PreToolUse", additional_context=role_on_code_message())


def is_planning_doc(file_path: str, root: Path | None = None) -> bool:
    target = classify_target(file_path, root)
    if target.endswith(_planning_doc_files()):
        return True
    if not target.endswith(".md"):
        return False
    return any(segment in target for segment in _planning_doc_segments())


def analysis_before_mutation_message() -> str:
    return (
        "[akmon] Analysis-before-mutation check — you are editing a planning/design doc "
        "(backlog / design / ADR / requirements / akmon process).\n"
        "Role: **assessing what is** (problems, state, conformance) is `review`; **constructing "
        "the design** (options, contracts, the chosen structure) is `architect`. Declare the role "
        "(`\U0001f9ed agent: <name> — <focus>`) and restate it on a switch (roles/README.md).\n"
        "If this turn is analysis-only — the owner asked you to analyze, explain, review, "
        "compare options, or identify what remains — STOP: report findings + a recommendation in "
        "chat and get explicit confirmation (\"write it\" / \"record it\" / \"make the change\") "
        "before editing. If the request was already an edit command, proceed. Rule: "
        "guardrails/_common.md § Analysis before mutation."
    )


def analysis_write_result(
    tool_name: str, file_path: str | None, session_id: str | None, project_root: Path | None = None
) -> HookResult | None:
    if tool_name not in _EDIT_TOOL_KINDS:
        return None
    if not isinstance(file_path, str) or not is_planning_doc(file_path, project_root):
        return None

    marker = Path(tempfile.gettempdir()) / f"akmon-analysis-guard-{session_id or 'nosession'}.marker"
    if marker.exists():
        return None
    try:
        marker.write_text("seen", encoding="utf-8")
    except OSError:
        pass

    return HookResult(event_name="PreToolUse", additional_context=analysis_before_mutation_message())


# D2 ledger reminder — an edit to a project-declared D2-sensitive path (math / data shape /
# architecture; the owner-verify guardrail) should be logged in the ledger so the point survives
# to commit time, where Verify is caught (design meta/design/d2-ledger.md §2.2, phase 2 of C11).
# PreToolUse reminds once per session on the first such edit. The sensitive-path globs are the
# project's, read from ``<aitna>/.akmon.toml`` ``[d2_ledger] sensitive_paths`` (§5.A). When
# unconfigured the hook stays silent — a per-edit reminder can't guess what's sensitive without
# fatiguing every edit; the coarse `check` gate and the session counter are the nets there.
# Advisory only — task classification is the agent's call, so it never blocks.


def d2_sensitive_paths(root: Path) -> list[str]:
    """The project's ``[d2_ledger] sensitive_paths`` globs from ``<aitna>/.akmon.toml`` (``[]`` if unset).

    Reads through the shared ``common.record`` reader (C75) rather than a second parser of its
    own: the same lenient parse every other caller gets, degrading to ``{}`` on an absent or
    unreadable record and to a partial dict on a malformed one, so an abnormal host can never
    turn this advisory into a hook crash."""
    data = read_akmon_toml(aitna_root(root) / ".akmon.toml")
    section = data.get("d2_ledger")
    globs = section.get("sensitive_paths") if isinstance(section, dict) else None
    return [g for g in globs if isinstance(g, str)] if isinstance(globs, list) else []


def _segments_match(pattern_segments: list[str], path_segments: list[str]) -> bool:
    """Recursive ``/``-aware glob match: ``**`` spans zero or more whole segments, ``*``/``?`` stay
    within one segment (via ``fnmatchcase``). Mirrors ``PurePath.full_match`` but runs on any
    the supported Python 3.11+ host, so ``full_match`` (3.13+) is not available here."""
    if not pattern_segments:
        return not path_segments
    head, *rest = pattern_segments
    if head == "**":
        return any(_segments_match(rest, path_segments[i:]) for i in range(len(path_segments) + 1))
    if not path_segments:
        return False
    if fnmatchcase(path_segments[0], head):
        return _segments_match(rest, path_segments[1:])
    return False


def is_d2_sensitive_path(file_path: str, root: Path, globs: list[str]) -> bool:
    """Whether ``file_path`` matches one of the project's D2-sensitive ``globs`` (``**``-aware)."""
    relative = _project_relative_posix(file_path.replace("\\", "/"), root)
    if relative is None:
        return False
    path_segments = [s for s in relative.split("/") if s]
    return any(_segments_match([s for s in glob.split("/") if s], path_segments) for glob in globs)


def d2_ledger_reminder_message(root: Path) -> str:
    tool = f"{runtime_root_display(root)}/tools/d2_ledger/d2_ledger.py"
    ledger = f"{aitna_root_name()}/D2_LEDGER.md"
    return (
        "[akmon] D2 ledger check — you are editing a D2-sensitive path (math / data shape / "
        "architecture).\n"
        "D2 (guardrails/_common.md § Verify against reality) means the owner verifies this class "
        "of change — passing tests are necessary, not sufficient. If you have not already logged "
        "it, add a ledger entry so the point survives to commit time:\n"
        f"  python3 {tool} add --ledger {ledger} \\\n"
        '      --kind {math|data-shape|architecture} --what "<what changed>" --anchor "<file:line>"\n'
        "The owner (or you on their word) records the decision with `approve <id>`; after landing, "
        "`verify <id> --commit <sha>` closes it. Fires once per session; `list` shows both open states."
    )


def d2_ledger_reminder_result(
    tool_name: str, file_path: str | None, session_id: str | None, project_root: Path | None = None
) -> HookResult | None:
    if tool_name not in _EDIT_TOOL_KINDS:
        return None
    if not isinstance(file_path, str):
        return None
    root = project_root or find_project_root()
    globs = d2_sensitive_paths(root)
    if not globs or not is_d2_sensitive_path(file_path, root, globs):
        return None

    marker = Path(tempfile.gettempdir()) / f"akmon-d2-ledger-{session_id or 'nosession'}.marker"
    if marker.exists():
        return None
    try:
        marker.write_text("seen", encoding="utf-8")
    except OSError:
        pass

    return HookResult(event_name="PreToolUse", additional_context=d2_ledger_reminder_message(root))


# D2 ledger session counter — at SessionStart the model-routing status block gains a
# ``D2 ledger: N pending, M approved`` line so both owner-decision and landing state are visible
# up front, next to the routing status. Owner-addressed (dual-channel
# systemMessage, ADR 0006) when either count is non-zero — no open state keeps the host UI quiet.
# The authoritative ledger parse lives in the ledger tool; here we only count rows tolerantly.


def _count_d2_rows(ledger_text: str) -> tuple[int, int]:
    """``(pending, approved)`` data-row counts from either a two- or three-section ledger."""
    section = None
    counts = {"## Pending": 0, "## Approved": 0}
    for line in ledger_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped if stripped in counts else None
            continue
        if section is not None and stripped.startswith("| D2-"):
            counts[section] += 1
    return counts["## Pending"], counts["## Approved"]


def _count_pending_rows(ledger_text: str) -> int:
    """Backward-compatible pending-only view used by existing hook consumers."""
    return _count_d2_rows(ledger_text)[0]


def d2_pending_count(root: Path) -> int:
    """Number of pending entries in the project's D2 ledger (``0`` if absent/unreadable)."""
    ledger = aitna_root(root) / "D2_LEDGER.md"
    if not ledger.is_file():
        return 0
    try:
        return _count_pending_rows(ledger.read_text(encoding="utf-8"))
    except OSError:
        return 0


def d2_status_counts(root: Path) -> tuple[int, int]:
    """Pending and approved entry counts (``(0, 0)`` if the ledger is absent/unreadable)."""
    ledger = aitna_root(root) / "D2_LEDGER.md"
    if not ledger.is_file():
        return 0, 0
    try:
        return _count_d2_rows(ledger.read_text(encoding="utf-8"))
    except OSError:
        return 0, 0


def d2_tracking_active(root: Path) -> bool:
    """Whether D2 tracking is in use here (sensitive paths configured, or a ledger file exists) —
    so a project that hasn't adopted the ledger never sees the counter line."""
    return bool(d2_sensitive_paths(root)) or (aitna_root(root) / "D2_LEDGER.md").is_file()


def d2_status_line(pending: int, approved: int = 0) -> str:
    return f"D2 ledger: {pending} pending, {approved} approved"


# Delegation nudge — the routing rule (guardrails/_common.md § Route by task kind + the
# SessionStart status line) is prose the orchestrator can silently skip mid-task. This counts
# consecutive orchestrator edit/shell/read calls since session start or the last subagent
# delegation and, past the advisory threshold, reminds once per drift episode — a subagent
# delegation re-arms it. Task-kind classification is fuzzy, so the advisory never blocks; but
# on *sustained* drift past a second, higher threshold it graduates to a hard `ask` (its own
# once-per-episode marker, also cleared by a delegation) — the read/sweep class (Read/Grep/
# Glob) is exactly the class the advisory used to miss.
#
# C28d: Claude Code gives a subagent's tool calls the *same* ``session_id`` as the main
# chain, so without an exemption a subagent's Read/Grep/Glob/Bash calls would charge the
# shared counter and could trip the advisory or the hard `ask` inside a k_* delegate — which
# has no ``Task`` tool and so cannot act on the nudge at all. Subagent-originated calls are
# detected via the payload's ``agent_id`` (present only inside a subagent) and are exempted
# entirely: no counter touch, no advisory, no ask.

_DELEGATION_NUDGE_THRESHOLD_DEFAULT = 10
_DELEGATION_ASK_THRESHOLD_DEFAULT = 20
_DELEGATION_NUDGE_TOOL_KINDS = frozenset({EDIT_TOOL, SHELL_TOOL, READ_TOOL})


def delegation_nudge_threshold() -> int:
    """Mutation count that triggers the advisory nudge (env `KEYSTONE_DELEGATION_NUDGE_THRESHOLD`)."""
    try:
        value = int(os.environ.get("KEYSTONE_DELEGATION_NUDGE_THRESHOLD", ""))
    except ValueError:
        return _DELEGATION_NUDGE_THRESHOLD_DEFAULT
    return value if value > 0 else _DELEGATION_NUDGE_THRESHOLD_DEFAULT


def delegation_ask_threshold() -> int:
    """Mutation count that graduates the nudge to a hard `ask` (env
    `KEYSTONE_DELEGATION_ASK_THRESHOLD`). Clamped so it never falls below the advisory
    threshold — an ask below the advisory would be reachable before the advisory itself."""
    try:
        value = int(os.environ.get("KEYSTONE_DELEGATION_ASK_THRESHOLD", ""))
    except ValueError:
        value = _DELEGATION_ASK_THRESHOLD_DEFAULT
    if value <= 0:
        value = _DELEGATION_ASK_THRESHOLD_DEFAULT
    return max(value, delegation_nudge_threshold())


def delegation_nudge_message(count: int) -> str:
    return (
        f"[akmon] Delegation check — {count} consecutive orchestrator edit/shell/read calls "
        "without a subagent delegation.\n"
        "Delegation is the default: route by task kind (MODEL.md § Capability tiers; "
        "guardrails/_common.md § Route by task kind). Exploration/summaries → `k_explorer` · "
        "mechanical edits / doc-sync / test scaffolds → `k_mechanic` · gate loops → "
        "`k_validator` · code under a decided contract → `k_implementer` · load-bearing "
        "analysis → `k_reasoner`.\n"
        "If this genuinely is orchestrator work (decompose / route / synthesize / owner "
        "dialogue), carry on — this reminder is advisory and fires once per drift episode "
        "(a subagent delegation re-arms it)."
    )


def delegation_ask_message(count: int) -> str:
    return (
        f"[akmon] Sustained delegation drift — {count} consecutive orchestrator "
        "edit/shell/read calls with no subagent delegation. The read/sweep class "
        "(Read/Grep/Glob) is exactly the drift the tier floor targets "
        "(guardrails/_common.md § Route by task kind).\n"
        "Route the next steps to a `k_*` delegate — exploration/summaries → `k_explorer` · "
        "mechanical edits / doc-sync / test scaffolds → `k_mechanic` · gate loops → "
        "`k_validator` · code under a decided contract → `k_implementer` · load-bearing "
        "analysis → `k_reasoner` — or confirm this is genuinely one of the orchestrator's "
        "reserved four (decompose · route · synthesize · owner dialogue) to proceed.\n"
        "Fires once per drift episode (a subagent delegation re-arms it)."
    )


def delegation_nudge_result(
    tool_name: str,
    session_id: str | None,
    *,
    is_subagent: bool = False,
    permission_mode: str | None = None,
) -> HookResult | None:
    # C28d: subagent-originated calls (agent_id present in the payload) must never touch
    # the counter. k_* delegates can't delegate (no Task tool), so nudging/asking them is
    # noise and the hard ask blocks their legit reads. The session_id is shared with the
    # main chain, so without this guard a subagent's reads charge the orchestrator's counter.
    if is_subagent:
        return None

    sid = session_id or "nosession"
    counter = Path(tempfile.gettempdir()) / f"akmon-delegation-nudge-{sid}.count"
    marker = Path(tempfile.gettempdir()) / f"akmon-delegation-nudge-{sid}.marker"
    ask_marker = Path(tempfile.gettempdir()) / f"akmon-delegation-nudge-{sid}.ask-marker"

    if tool_name == SUBAGENT_TOOL:
        try:
            counter.write_text("0", encoding="utf-8")
        except OSError:
            pass
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            ask_marker.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    if tool_name not in _DELEGATION_NUDGE_TOOL_KINDS:
        return None

    try:
        count = int(counter.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        count = 0
    count += 1
    try:
        counter.write_text(str(count), encoding="utf-8")
    except OSError:
        pass

    if count >= delegation_ask_threshold():
        if ask_marker.exists():
            return None
        try:
            ask_marker.write_text("seen", encoding="utf-8")
        except OSError:
            pass
        return _escalate_unattended_ask(
            HookResult(
                event_name="PreToolUse",
                permission_decision="ask",
                permission_reason=delegation_ask_message(count),
            ),
            permission_mode,
        )
    if count >= delegation_nudge_threshold():
        if marker.exists():
            return None
        try:
            marker.write_text("seen", encoding="utf-8")
        except OSError:
            pass
        return HookResult(event_name="PreToolUse", additional_context=delegation_nudge_message(count))
    return None
