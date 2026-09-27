"""Vendor-neutral akmon hook decisions.

This module contains the guardrail logic only. Vendor entrypoints adapt their incoming
payload and serialize ``HookResult`` into the shape their runtime expects.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

from common import jsondata  # noqa: E402
from common.markers import (  # noqa: E402
    claim_diagnostic_marker,
    delegation_state_name,
    marker_kind,
    unidentified_identity,
)
from common.materialization import stale_materialized  # noqa: E402
from common.project_root import (  # noqa: E402
    aitna_root,
    aitna_root_name,
    akmon_mount,
    find_project_root,
)


def akmon_runtime_root(project_root: Path) -> Path:
    """Runtime files used by hooks: **the tree this hook is executing from**.

    Each carrier ships a hook and its data together, so the hook's own location answers the
    question without asking anything: the mounted tree when the wiring named a file there, and
    the wheel's embedded ``akmon/_tree`` when the wiring called ``akmon hook`` (C77). No
    record read, no directory probe, and no way for the two to disagree.

    This replaces the record-vetoes-the-directory rule (C69, ADR-0009/D02), which was correct only while
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
    """A hook's decision, vendor-neutral, ready for an adapter to serialize."""

    event_name: str
    additional_context: str | None = None
    permission_decision: str | None = None
    permission_reason: str | None = None
    system_message: str | None = None
    #: A turn-level decision (``Stop``): ``block`` holds the turn, with ``reason`` as the one
    #: thing the model is asked to do before it may end the turn again.
    decision: str | None = None
    reason: str | None = None


def hook_failure_diagnostic(hook_name: str, exc: BaseException) -> str:
    """The one stderr line a crashed entry point writes (ADR 0013 F3): the hook and the class.

    Never the exception's message — it routinely carries a path, a key or a payload fragment.
    The text stays in code, not in ``hook_core.json`` (C102 review F1): the crash path must not
    depend on a data file, since a missing or broken one is exactly what it reports.

    Runtime classification: operational
    Rationale: crash posture (ADR 0013 F3), not a guardrail policy — it reports that a hook failed
    and authors no rule of its own. An adapter renders it into the hook process's stderr, so it
    reaches the owner from outside the ``*_result`` join, where ADR-0012/D07 requires the
    classification to be stated rather than left silent.
    """
    return f"akmon {hook_name} hook: {type(exc).__name__}"


def hook_failure_notice(hook_name: str, exc: BaseException) -> str:
    """What the owner is told when an entry point crashed (C87, ADR-0013/D01): the fact, then the command.

    The same two facts as :func:`hook_failure_diagnostic` and nothing from the exception's text.
    It is written inside a crash handler, so it reads nothing that can raise — the dev-layer
    name is an environment lookup with a default, not a filesystem question, and the text is
    code, not data (see :func:`hook_failure_diagnostic`).

    Runtime classification: operational
    Rationale: the owner-facing half of the same crash report (ADR-0013/D01) — it states that a
    hook was skipped and names the recovery command, and authors no guardrail rule. An adapter
    renders it into the vendor's owner channel, so ADR-0012/D07 requires this classification on it
    even though it sits outside the ``*_result`` join.
    """
    return (
        f"⚠ akmon: the {hook_name} hook failed ({type(exc).__name__}) and was skipped — this action "
        f"went ahead without it. Check the setup: `akmon verify` (a mounted tree: "
        f"`python3 {aitna_root_name()}/akmon/bin/verify.py`)."
    )


def _hook_core_data() -> dict[str, Any]:
    """The hook_core data file beside this module (C102).

    The path-classification tables, the delegation policy, and the owner-facing reminder texts.
    """
    return jsondata.read(Path(__file__).parent / "hook_core.json")


def _code_extensions() -> frozenset[str]:
    """The recognized source-file extensions (hooks/hook_core.json, C102)."""
    return frozenset(_hook_core_data()["code_extensions"])


# Path-classification segments are derived from the configured dev-layer root (default
# ``_aitna``) so relocating it via AITNA_ROOT keeps the code/planning-doc detection correct.
# These match lowercased path *substrings*, so the segment uses the lowercased root name.
def _non_code_segments() -> tuple[str, ...]:
    aitna = aitna_root_name().lower()
    return tuple(jsondata.fill(segment, {"aitna": aitna}) for segment in _hook_core_data()["non_code_segments"])


def _vocabulary() -> dict[str, Any]:
    """The hook vocabulary table beside this module (C102).

    The neutral tool-kind tokens, the vendor tool-name tables, the codex payload key spellings,
    and the hook document-shape keys.
    """
    return jsondata.read(Path(__file__).parent / "vocabulary.json")


def neutral_kind(stem: str) -> str:
    """One neutral tool-kind token by stem (the table is owned by hooks/vocabulary.json, C102)."""
    return _vocabulary()["neutral_kinds"][stem]


def edit_tool() -> str:
    """The neutral edit-tool kind every vendor adapter normalizes to.

    Runtime classification: operational
    Rationale: a data lookup (hooks/vocabulary.json, C102) — it resolves the token the adapters
    compare against and renders no text of its own; what is said is owned by the caller.
    """
    return neutral_kind("edit")


def _edit_tool_kinds() -> frozenset[str]:
    return frozenset({edit_tool()})


# Further neutral kinds for the delegation nudge: a shell/command tool, a read/sweep tool,
# and the vendor's subagent-delegation tool.
def shell_tool() -> str:
    """The neutral shell/command-tool kind.

    Runtime classification: operational
    Rationale: a data lookup (hooks/vocabulary.json, C102) — it resolves the token the adapters
    compare against and renders no text of its own; what is said is owned by the caller.
    """
    return neutral_kind("shell")


def read_tool() -> str:
    """The neutral read/sweep-tool kind.

    Runtime classification: operational
    Rationale: a data lookup (hooks/vocabulary.json, C102) — it resolves the token the adapters
    compare against and renders no text of its own; what is said is owned by the caller.
    """
    return neutral_kind("read")


def subagent_tool() -> str:
    """The neutral subagent-delegation kind.

    Runtime classification: operational
    Rationale: a data lookup (hooks/vocabulary.json, C102) — it resolves the token the core
    compares against and renders no text of its own; what is said is owned by the caller.
    """
    return neutral_kind("subagent")


def unclassified_shell_route_notice() -> str:
    """The once-per-session stderr line for a shell call no advisory can classify (C102)."""
    return _hook_core_data()["unclassified_shell_route_notice"]


def report_unclassified_shell_route(session_id: str | None) -> None:
    """Say once per session that a shell call has effects the advisories cannot classify.

    The advisories key off a path; a shell call carries a command, and reading a path out of a
    command string is a guess — so this route is *reported*, never classified. It states the
    route's capability, not a guessed effect (C49).

    Vendor-neutral by ADR-0012/D02: the blind spot is not Codex's. On Claude the
    same effect reaches the filesystem through ``Bash`` while the advisories sit on the edit
    tools, so the route was not merely unclassified there — it was unreported. Both vendors now
    emit one message from one implementation, because two copies of a diagnostic are two things
    that can drift into disagreeing about what akmon can see.

    Never blocks and never becomes model context: every caller keeps its exit code. Whether a
    harness surfaces hook stderr to the owner is unverified on both vendors and is not claimed.

    Runtime classification: operational
    Rationale: it reports a *gap* in what the advisories can see, which is the opposite of
    enforcing a rule — no guardrail subset is claimed, and none could be, since the route it
    describes is the one nothing classifies. It writes to stderr itself, so ADR-0012/D07 puts it
    among the owner-visible callables outside the join that must say what they are.
    """
    if claim_diagnostic_marker(marker_kind("shell_route"), session_id):
        print(unclassified_shell_route_notice(), file=sys.stderr)


# Planning / design docs — editing one may be an analysis-only turn that needs confirmation
# first (see guardrails/_common.md § Analysis before mutation).
def _planning_doc_segments() -> tuple[str, ...]:
    aitna = aitna_root_name().lower()
    return tuple(jsondata.fill(segment, {"aitna": aitna}) for segment in _hook_core_data()["planning_doc_segments"])


def _planning_doc_files() -> tuple[str, ...]:
    aitna = aitna_root_name().lower()
    return tuple(jsondata.fill(name, {"aitna": aitna}) for name in _hook_core_data()["planning_doc_files"])


def current_git_branch() -> str:
    """Current branch name, or ``""`` when it cannot be determined."""
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


# ask->deny escalation for unattended sessions (C31, ADR-0006/D02). A live test
# showed a hook-forced `ask` is a silent no-op — no prompt, no block — in a Claude Code
# background/child session running in `acceptEdits` mode; the PreToolUse payload carries a
# `permission_mode` field (same enum on Codex) that tells a hook whether an interactive
# owner is actually there to answer. Only the strict `default` mode is known to gate on
# `ask`; everywhere else (or the field missing outright) the owner asked to be stricter
# rather than silently pass through, so the decision is escalated to a hard `deny` — the one
# decision every vendor is confirmed to enforce unconditionally.
def _interactive_default_permission_mode() -> str:
    """The one permission mode known to gate on a hook-forced ``ask`` (C102)."""
    return _hook_core_data()["interactive_default_permission_mode"]


def _escalate_unattended_ask(result: HookResult, permission_mode: str | None) -> HookResult:
    if result.permission_decision != "ask" or permission_mode == _interactive_default_permission_mode():
        return result
    suffix = jsondata.fill(
        _hook_core_data()["escalated_ask_suffix"], {"permission_mode": repr(permission_mode)}
    )
    return HookResult(
        event_name=result.event_name,
        additional_context=result.additional_context,
        permission_decision="deny",
        permission_reason=f"{result.permission_reason} {suffix}",
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

    Policy ID: privilege.no-escalation
    """
    if not _SUDO_RE.search(command):
        return None
    return HookResult(
        event_name="PreToolUse",
        permission_decision="deny",
        permission_reason=_hook_core_data()["privilege_escalation_reason"],
    )


def git_commit_guard_result(
    command: str, branch: str | None = None, *, permission_mode: str | None = None
) -> HookResult | None:
    """Guard commit-shaped ``git`` commands: no AI co-author trailer, owner confirms landing history.

    Policy ID: commits.owner-owned
    """
    if "git" not in command:
        return None

    if re.search(r"co-authored-by", command, re.IGNORECASE):
        return HookResult(
            event_name="PreToolUse",
            permission_decision="deny",
            permission_reason=_hook_core_data()["git_commit_no_ai_trailer_reason"],
        )

    def is_git(subcommand: str) -> bool:
        return re.search(r"\bgit\b[^|&;]*\b" + subcommand + r"\b", command) is not None

    if is_git("push") or is_git("tag") or is_git("merge"):
        return _escalate_unattended_ask(
            HookResult(
                event_name="PreToolUse",
                permission_decision="ask",
                permission_reason=_hook_core_data()["git_commit_push_tag_merge_reason"],
            ),
            permission_mode,
        )

    if is_git("commit"):
        resolved_branch = current_git_branch() if branch is None else branch
        if resolved_branch in ("main", "master") or not resolved_branch:
            data = _hook_core_data()
            return _escalate_unattended_ask(
                HookResult(
                    event_name="PreToolUse",
                    permission_decision="ask",
                    permission_reason=jsondata.fill(
                        data["git_commit_landing_reason"],
                        {"branch": resolved_branch or data["git_commit_detached_head"]},
                    ),
                ),
                permission_mode,
            )

    return None


def agent_names(directory: Path) -> list[str]:
    """Sorted names of the agent charters (subdirectories with a ``README.md``) under ``directory``."""
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
    resolves — they run from the package — while ``<AITNA_ROOT>/.akmon/`` still
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
    names = stale_materialized(root, runtime_root)
    if not names:
        return None
    return jsondata.fill(
        _hook_core_data()["stale_guardrail_notice"],
        {"root_name": aitna_root_name(), "names": ", ".join(names)},
    )


def session_start_result(root: Path) -> HookResult | None:
    """SessionStart guardrail: active-agent declaration reminder, plus a stale-materialization notice.

    Runtime classification: operational
    Rationale: it authors no rule. It aggregates the agent roster and re-delivers rules owned
    elsewhere — role declaration, the memory-read rule, delegation-by-default — at session start,
    and on Codex it is the only delivery channel for the delegation rule, because ``@``-imports are
    not expanded there (C39). Delivery is not ownership, so the classification stands; without that
    second fact "operational" would read as "incidental", which it is not.
    """
    stale = stale_guardrail_notice(root)
    dev = agent_names(aitna_root(root) / "agents")
    desk = agent_names(root / "agents")
    if not dev and not desk:
        # A project with no agent charters still has to hear this one: it is about the rules
        # the harness just loaded, not about the roles it did not declare.
        if stale is None:
            return None
        return HookResult(event_name="SessionStart", additional_context=stale, system_message=stale)

    # The line fragments are owned by hooks/hook_core.json (C102); the assembly — which lines
    # appear and in what order — stays here.
    start = _hook_core_data()["session_start"]
    lines = [start["title"], start["format_line"]]
    if dev:
        lines.append(jsondata.fill(start["develop_line"], {"agents": ", ".join(dev)}))
    if desk:
        lines.append(jsondata.fill(start["operate_line"], {"agents": ", ".join(desk)}))
    lines.append(start["no_agent_line"])
    if dev:
        # The DEVELOP routing discriminator (ADR 0003 §4): give the picking rule up front, not
        # only after a code/planning edit already happened. Keyed by cognitive operation.
        lines.append(start["pick_by_operation"])
    else:
        lines.append(start["pick_generic"])
    lines.append(start["delegation_line"])
    lines.append(jsondata.fill(start["memory_line"], {"root_name": aitna_root_name()}))
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

    That guard is **advisory-grade, not containment** (ADR-0012/D01): it stops ``..``, but a link
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
    """``file_path`` in the one form every classifier matches on.

    Project-relative POSIX, lowercased, with a leading ``/``. The classification segments
    (``/docs/``, ``/<aitna>/design/``) are written with surrounding slashes, so matching them
    against the *raw* string answered "no" for every relative path — and a silent "no" is
    indistinguishable from "matched and stayed quiet" (C47). The two forms are not
    hypothetical: Claude Code always sends an absolute
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
    # (ADR-0012/D01): no wired path takes either branch, and a mandatory `root` would change three
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
    """Whether ``file_path`` is a project code file (not docs/design, and a recognized extension)."""
    target = classify_target(file_path, root)
    if any(segment in target for segment in _non_code_segments()):
        return False
    return Path(target).suffix in _code_extensions()


def role_on_code_message() -> str:
    """Owner-facing text for the role-on-code reminder (hooks/hook_core.json, C102)."""
    return jsondata.fill(_hook_core_data()["role_on_code_message"], {"tasks": f"{aitna_root_name()}/TASKS.md"})


def role_on_code_result(
    tool_name: str, file_path: str | None, session_id: str | None, project_root: Path | None = None
) -> HookResult | None:
    """PreToolUse guardrail: on the first code edit per session, remind to declare the engineer role.

    Policy ID: role.declaration
    """
    if tool_name not in _edit_tool_kinds():
        return None
    if not isinstance(file_path, str) or not is_code_path(file_path, project_root):
        return None

    if not claim_diagnostic_marker(marker_kind("role_on_code"), session_id):
        return None

    return HookResult(event_name="PreToolUse", additional_context=role_on_code_message())


def is_planning_doc(file_path: str, root: Path | None = None) -> bool:
    """Whether ``file_path`` is a backlog/design/ADR/requirements/process planning doc."""
    target = classify_target(file_path, root)
    if target.endswith(_planning_doc_files()):
        return True
    if not target.endswith(".md"):
        return False
    return any(segment in target for segment in _planning_doc_segments())


def analysis_before_mutation_message() -> str:
    """Owner-facing text for the analysis-before-mutation reminder (hooks/hook_core.json, C102)."""
    return _hook_core_data()["analysis_before_mutation_message"]


def analysis_write_result(
    tool_name: str, file_path: str | None, session_id: str | None, project_root: Path | None = None
) -> HookResult | None:
    """PreToolUse guardrail: on the first planning-doc edit per session, remind analysis-before-mutation.

    Policy ID: analysis.before-mutation
    """
    if tool_name not in _edit_tool_kinds():
        return None
    if not isinstance(file_path, str) or not is_planning_doc(file_path, project_root):
        return None

    if not claim_diagnostic_marker(marker_kind("analysis_guard"), session_id):
        return None

    return HookResult(event_name="PreToolUse", additional_context=analysis_before_mutation_message())


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

#
# Calibrated, not guessed (C88, ADR-0006/D02). Replayed over akmon's own Claude sessions (M72), the rule
# this replaced — every call worth 1, advisory at 10, ask at 20 — fired the advisory in 10 of 11
# sessions and the ask in 10 of 11; 16 of those 17 asks came in a non-default permission mode,
# where an ask escalates to a deny, and 3 of the denies fell on a read. An earlier replay on
# another corpus found the same (M75). A signal that fires in every session measures session
# length. Three corrections, all keyed on the tool kind — the command text is not read (C28(c)):
#
# - **A read weighs half** (:func:`_delegation_weights`, from ``hooks/hook_core.json``): a sweep
#   is drift too, but cheaper to undo than an edit.
# - **The opening calls of a stretch are free** (:func:`delegation_grace`): orientation before
#   the first delegation is not yet a failure to delegate.
# - **A read never carries the ask.** Outside the interactive default mode the ask is a deny, and
#   a denied look costs the agent the means to find out what it was about to do. The score stays
#   over the threshold, so the ask lands on the next edit or shell call.
#
# At 30 / 120 the same replay fires the advisory in 10 of 11 sessions and the ask in 7 of 11. The
# weights barely move that: from 50 to 120 every weighting tried reaches 7 of 11 (M73), because
# those sessions did run hundreds of calls without a delegation — there the advisory is mostly
# right. What changed is that a read is never denied and the ask comes six times later.
def _delegation_policy() -> dict[str, Any]:
    """The calibrated delegation-drift policy (hooks/hook_core.json, C102)."""
    return _hook_core_data()["delegation"]


def _delegation_weights() -> dict[str, float]:
    """What one orchestrator call adds to the drift score, by neutral tool kind."""
    weights = _delegation_policy()["weights"]
    return {neutral_kind(stem): value for stem, value in weights.items()}


def _delegation_nudge_tool_kinds() -> frozenset[str]:
    return frozenset(_delegation_weights())


def delegation_grace() -> int:
    """Calls at the start of a stretch that score nothing (env `AKMON_DELEGATION_GRACE`)."""
    policy = _delegation_policy()
    try:
        value = int(os.environ.get(policy["grace_env"], ""))
    except ValueError:
        return policy["grace"]
    return value if value >= 0 else policy["grace"]


def delegation_nudge_threshold() -> int:
    """Drift score that triggers the advisory nudge (env `AKMON_DELEGATION_NUDGE_THRESHOLD`)."""
    policy = _delegation_policy()
    try:
        value = int(os.environ.get(policy["nudge_threshold_env"], ""))
    except ValueError:
        return policy["nudge_threshold"]
    return value if value > 0 else policy["nudge_threshold"]


def delegation_ask_threshold() -> int:
    """Drift score that graduates the nudge to a hard `ask` (env `AKMON_DELEGATION_ASK_THRESHOLD`).

    Clamped so it never falls below the advisory threshold — an ask below the advisory
    would be reachable before the advisory itself.
    """
    policy = _delegation_policy()
    try:
        value = int(os.environ.get(policy["ask_threshold_env"], ""))
    except ValueError:
        value = policy["ask_threshold"]
    if value <= 0:
        value = policy["ask_threshold"]
    return max(value, delegation_nudge_threshold())


def _drift_score_text(score: float) -> str:
    """The drift-score clause; the `:g` numeric spelling stays code (hooks/hook_core.json, C102)."""
    return jsondata.fill(
        _hook_core_data()["drift_score_text"], {"score": f"{score:g}", "grace": str(delegation_grace())}
    )


def delegation_nudge_message(score: float) -> str:
    """Owner-facing text for the advisory delegation-drift nudge (hooks/hook_core.json, C102)."""
    data = _hook_core_data()
    return jsondata.fill(
        data["delegation_nudge_message"],
        {"drift_score": _drift_score_text(score), "roster": data["delegation_roster"]},
    )


def delegation_ask_message(score: float) -> str:
    """Owner-facing text for the hard-ask escalation on sustained delegation drift (C102)."""
    data = _hook_core_data()
    return jsondata.fill(
        data["delegation_ask_message"],
        {"drift_score": _drift_score_text(score), "roster": data["delegation_roster"]},
    )


def _reset_delegation_counters(counter: Path, marker: Path, ask_marker: Path) -> None:
    """Zero the drift counter and clear both markers on a real delegation."""
    with contextlib.suppress(OSError):
        counter.write_text("0", encoding="utf-8")
    with contextlib.suppress(OSError):
        marker.unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        ask_marker.unlink(missing_ok=True)


def _update_delegation_counter(counter: Path, tool_name: str) -> float:
    """Read, bump and persist the stretch's call count and drift score; the score after this call."""
    # Two numbers in one file: `seen` is the stretch's calls (the grace is counted in calls),
    # `score` what they were worth. A one-number counter from the previous rule reads as calls
    # with no score yet.
    try:
        raw_seen, _, raw_score = counter.read_text(encoding="utf-8").partition(" ")
        seen, score = int(raw_seen), float(raw_score or 0)
    except (OSError, ValueError):
        seen, score = 0, 0.0
    seen += 1
    if seen > delegation_grace():
        score += _delegation_weights()[tool_name]
    with contextlib.suppress(OSError):
        counter.write_text(f"{seen} {score}", encoding="utf-8")
    return score


def _delegation_ask_result(
    score: float, tool_name: str, ask_marker: Path, permission_mode: str | None
) -> HookResult | None:
    """The hard ask: fires once per stretch, never on a read."""
    # A read never carries the ask and does not spend it; the next edit or shell call does.
    if ask_marker.exists() or tool_name == read_tool():
        return None
    with contextlib.suppress(OSError):
        ask_marker.write_text("seen", encoding="utf-8")
    return _escalate_unattended_ask(
        HookResult(
            event_name="PreToolUse",
            permission_decision="ask",
            permission_reason=delegation_ask_message(score),
        ),
        permission_mode,
    )


def _delegation_soft_nudge_result(score: float, marker: Path) -> HookResult | None:
    """The soft nudge: fires once per stretch, below the hard-ask threshold."""
    if marker.exists():
        return None
    with contextlib.suppress(OSError):
        marker.write_text("seen", encoding="utf-8")
    return HookResult(event_name="PreToolUse", additional_context=delegation_nudge_message(score))


def delegation_nudge_result(
    tool_name: str,
    session_id: str | None,
    *,
    is_subagent: bool = False,
    permission_mode: str | None = None,
) -> HookResult | None:
    """PreToolUse guardrail: nudge, then hard-ask, on sustained orchestrator delegation drift.

    Policy ID: delegation.tier-floor
    """
    # C28d: subagent-originated calls (agent_id present in the payload) must never touch
    # the counter. k_* delegates can't delegate (no Task tool), so nudging/asking them is
    # noise and the hard ask blocks their legit reads. The session_id is shared with the
    # main chain, so without this guard a subagent's reads charge the orchestrator's counter.
    if is_subagent:
        return None

    sid = session_id or unidentified_identity()
    counter = Path(tempfile.gettempdir()) / delegation_state_name("counter", sid)
    marker = Path(tempfile.gettempdir()) / delegation_state_name("marker", sid)
    ask_marker = Path(tempfile.gettempdir()) / delegation_state_name("ask_marker", sid)

    if tool_name == subagent_tool():
        _reset_delegation_counters(counter, marker, ask_marker)
        return None
    if tool_name not in _delegation_nudge_tool_kinds():
        return None

    score = _update_delegation_counter(counter, tool_name)

    if score >= delegation_ask_threshold():
        return _delegation_ask_result(score, tool_name, ask_marker, permission_mode)
    if score >= delegation_nudge_threshold():
        return _delegation_soft_nudge_result(score, marker)
    return None
