"""Vendor-neutral akmon hook decisions.

This module contains the guardrail logic only. Vendor entrypoints adapt their incoming
payload and serialize ``HookResult`` into the shape their runtime expects.
"""

from __future__ import annotations

import contextlib
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, TypedDict, Unpack

# Where the dev layer is, what it is called, and how the project root is found are not this
# module's facts — they belong to ``common.project_root``, which is stdlib-only and sits
# beside ``hooks/`` at the same tree-relative path in every carrier the hooks run from: the
# mounted ``<dev root>/akmon/`` tree and the wheel's embedded ``akmon/_tree/``. The copy that
# used to live here answered the same questions in the same words and was the last remaining
# second definition (C73).
# This file's own tree root. Every carrier keeps a hook and the data it reads in one tree —
# the mounted ``<dev root>/akmon/``, and the wheel's embedded ``akmon/_tree/`` — so this is
# both the import anchor for ``common`` and the answer to "which tree is running" below.
_TREE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TREE_ROOT))

from common import access_matrix, harness_settings, jsondata, work_style  # noqa: E402
from common.markers import (  # noqa: E402
    claim_diagnostic_marker,
    delegation_state_name,
    marker_kind,
    unidentified_identity,
)
from common.materialization import stale_materialized  # noqa: E402
from common.project_root import (  # noqa: E402
    AITNA_ROOT_DEFAULT,
    aitna_root,
    aitna_root_name,
    akmon_mount,
    find_project_root,
    local_root,
    locate_project_root,
)


def akmon_runtime_root(project_root: Path) -> Path:
    """Runtime files used by hooks: **the tree this hook is executing from**.

    Each carrier ships a hook and its data together, so the hook's own location answers the
    question without asking anything: the mounted tree when the wiring named a file there, and
    the wheel's embedded ``akmon/_tree`` when the wiring called ``akmon hook`` (C77). No
    record read, no directory probe, and no way for the two to disagree.

    This replaces the record-vetoes-the-directory rule (C69, ADR-0009/D02), which was correct only while
    mode ``package`` copied the hooks — and the whole runtime surface they read — into
    ``<dev root>/.akmon/``. With the materialization narrowed to the guardrails the
    consumer's ``AGENTS.md`` imports, that directory holds no registry at all, and pointing
    here would have made the routing hook's "no registry, older pin — stay silent" guard fire on
    every session: status line and delegation log gone, exit code 0, stderr empty.

    What the old rule defended against is gone rather than given up: a stale
    ``<dev root>/akmon`` from a prior mode cannot shadow anything, because a tree that is not
    executing is not a candidate.

    ``project_root`` stays in the signature: the project overlay it locates
    (``<dev root>/model-routing.json``) is still layered onto whatever registry this tree
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
            return f"{aitna_root_name(project_root)}/akmon"
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


def hook_failure_notice(hook_name: str, exc: BaseException, start: Path | None = None) -> str:
    """What the owner is told when an entry point crashed (C87, ADR-0013/D01): the fact, then the command.

    The same two facts as :func:`hook_failure_diagnostic` and nothing from the exception's text.
    It is written inside a crash handler, so nothing it reads can raise out of it — the dev-layer
    name is looked up from ``start`` (default: the cwd) and falls back to the default name when
    that lookup itself fails, and the text is code, not data (see :func:`hook_failure_diagnostic`).

    Runtime classification: operational
    Rationale: the owner-facing half of the same crash report (ADR-0013/D01) — it states that a
    hook was skipped and names the recovery command, and authors no guardrail rule. An adapter
    renders it into the vendor's owner channel, so ADR-0012/D07 requires this classification on it
    even though it sits outside the ``*_result`` join.
    """
    try:
        dev_name = aitna_root_name(locate_project_root(start))
    except (OSError, ValueError, RuntimeError):
        dev_name = AITNA_ROOT_DEFAULT
    return (
        f"⚠ akmon: the {hook_name} hook failed ({type(exc).__name__}) and was skipped — this action "
        f"went ahead without it. Check the setup: `akmon verify` (a mounted tree: "
        f"`python3 {dev_name}/akmon/bin/verify.py`)."
    )


def _hook_core_data() -> dict[str, Any]:
    """The hook_core data file beside this module (C102).

    The path-classification tables, the delegation policy, and the owner-facing reminder texts.
    """
    return jsondata.read(Path(__file__).parent / "hook_core.json")


def _code_extensions() -> frozenset[str]:
    """The recognized source-file extensions (hooks/hook_core.json, C102)."""
    return frozenset(_hook_core_data()["code_extensions"])


def _dev_name(root: Path | None) -> str:
    """The lowercased dev-layer name the path classifiers match on; ``root`` defaults to the project at the cwd."""
    return aitna_root_name(root if root is not None else locate_project_root()).lower()


# Path-classification segments are derived from the project's dev-layer root (default ``_aitna``)
# so relocating it via ``.aitna-root`` keeps the code/planning-doc detection correct.
# These match lowercased path *substrings*, so the segment uses the lowercased root name.
def _non_code_segments(root: Path | None) -> tuple[str, ...]:
    aitna = _dev_name(root)
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
def _planning_doc_segments(root: Path | None) -> tuple[str, ...]:
    aitna = _dev_name(root)
    return tuple(jsondata.fill(segment, {"aitna": aitna}) for segment in _hook_core_data()["planning_doc_segments"])


def _planning_doc_files(root: Path | None) -> tuple[str, ...]:
    aitna = _dev_name(root)
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


# ask->deny escalation for an unattended run (C31, ADR-0006/D02, narrowed by ADR-0025/D06). A live
# test showed a hook-forced `ask` is a silent no-op -- no prompt, no block -- in a Claude Code
# background/child session, so an ask that nobody can answer becomes a hard `deny`, the one
# decision every vendor is confirmed to enforce unconditionally. Who attends is read from what the
# host states: Claude Code sets `CLAUDE_CODE_SESSION_ATTENDED` (the adapter reads it at the entry
# point and hands it down as `attended`; M199, M200). Where the host states nothing, only the
# interactive `default` permission mode attends. A mode that skips every question never does.
def _interactive_default_permission_mode() -> str:
    """The one permission mode known to gate on a hook-forced ``ask`` when the host states no attendance (C102)."""
    return _hook_core_data()["interactive_default_permission_mode"]


def _unattended_permission_modes() -> frozenset[str]:
    """The permission modes that skip every question, so an ``ask`` is never shown in them (M193)."""
    return frozenset(_hook_core_data()["unattended_permission_modes"])


def ask_is_attended(permission_mode: str | None, *, attended: bool | None = None) -> bool:
    """Whether a hook's ``ask`` reaches an owner who can answer it (ADR-0025/D06).

    ``attended`` is the host's own statement (``CLAUDE_CODE_SESSION_ATTENDED``: ``True`` for ``1``,
    ``False`` for ``0``), or ``None`` where it states nothing; the permission mode then decides,
    as it did before. A mode that skips every question is never attended, whatever ``attended`` says.
    """
    if permission_mode in _unattended_permission_modes():
        return False
    if attended is not None:
        return attended
    return permission_mode == _interactive_default_permission_mode()


# The attendance value as the host spells it, or ``unset`` where it stated nothing.
_ATTENDED_LABELS = {True: "1", False: "0", None: "unset"}


def _escalate_unattended_ask(
    result: HookResult, permission_mode: str | None, *, attended: bool | None = None
) -> HookResult:
    if result.permission_decision != "ask" or ask_is_attended(permission_mode, attended=attended):
        return result
    suffix = jsondata.fill(
        _hook_core_data()["escalated_ask_suffix"],
        {"permission_mode": repr(permission_mode), "attended": _ATTENDED_LABELS[attended]},
    )
    return HookResult(
        event_name=result.event_name,
        additional_context=result.additional_context,
        permission_decision="deny",
        permission_reason=f"{result.permission_reason} {suffix}",
        system_message=result.system_message,
    )


# Every pattern of the command guards that uses ``\b`` is ``re.ASCII``: the JavaScript twin's ``\b`` is
# ASCII-only, while Python's, left alone, also counts other scripts' letters as word characters, so
# ``ésudo`` would be placed differently by the two. A shell command word is ASCII.
# The ``co-authored-by`` pattern below stays ``IGNORECASE`` only: none of its letters has a
# non-ASCII case partner (only ``i``, ``s`` and ``k`` do, via U+0131, U+017F and U+212A).
_SUDO_RE = re.compile(r"\bsudo\b", re.ASCII)


def privilege_escalation_guard_result(command: str, directory: str | None = None) -> HookResult | None:
    """Deny any Bash command that invokes ``sudo``, and one that writes a harness settings file, unconditionally.

    The agent runs as an unprivileged user by design; a command reaching for ``sudo`` is
    either probing for elevated access or trying to route around a permission boundary that
    exists on purpose (e.g. a root-owned file). Neither is something the agent decides for
    itself — if elevated access is genuinely needed, the owner runs it themselves. No ask:
    the answer does not depend on session attentiveness, so there is nothing to escalate.

    The same rule covers the actor's carrier (ADR 0031/D07, D-C203-ACTOR-WRITE): a harness settings
    file's ``env`` reaches the hook process (M239), so a command whose words write one of those files — an
    output redirection, ``tee``, ``sed -i``/``perl -i``, a ``cp``/``mv``/``install`` destination, ``dd of=``
    — is denied, for every actor; reading one passes. Only command words are read, never a quoted
    argument or a heredoc body. ``directory`` is where the command starts (default: the process's).
    The edit tools' half of the rule is the ``settings-env-guard`` hook (``common/harness_settings.py``).

    Policy ID: privilege.no-escalation
    """
    if _SUDO_RE.search(command):
        return HookResult(
            event_name="PreToolUse",
            permission_decision="deny",
            permission_reason=_hook_core_data()["privilege_escalation_reason"],
        )
    reason = _settings_write_reason(command, _working_directory() if directory is None else directory)
    if reason is None:
        return None
    return HookResult(event_name="PreToolUse", permission_decision="deny", permission_reason=reason)


# --------------------------------------------------------------------------------------
# The commit guard: which repository a command acts on (C190, ADR-0029/D09)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GitInvocation:
    """One ``git``, ``gh`` or ``glab`` command found in a shell command: its subcommand, arguments and place.

    ``arguments`` are the words after the subcommand, quotes removed. ``directory`` is ``None`` when
    the place cannot be told from the text (a ``$`` expansion, a ``GIT_DIR`` assignment,
    ``--git-dir``, ``cd -``). ``program`` is ``git``, ``gh`` or ``glab``; a forge
    subcommand is its group and action as one string (``pr create``, ``mr create``); ``gh api`` and
    ``glab api`` keep every word after ``api``. ``config_override`` is ``True`` for a ``git`` carrying
    ``-c`` or ``--config-env``: the command runs under configuration the text does not show.
    """

    subcommand: str
    directory: str | None
    arguments: tuple[str, ...] = ()
    program: str = "git"
    config_override: bool = False


@dataclass(frozen=True)
class RepositoryFacts:
    """What the guard needs of the repository at a directory: a linked worktree or not, and its branch.

    ``branch`` is ``""`` on a detached ``HEAD``.
    """

    linked: bool
    branch: str


@dataclass(frozen=True)
class _Word:
    """A shell word after quote removal.

    ``operand`` is ``False`` for the target of a redirection, and ``write`` is ``True`` for the target of
    an output redirection (``>``, ``>>``, ``>|``, ``&>``), which opens its file for writing.
    """

    value: str
    expands: bool
    substitutions: tuple[list[Any], ...]
    operand: bool
    write: bool = False


@dataclass(frozen=True)
class _Command:
    words: tuple[_Word, ...]


@dataclass(frozen=True)
class _Group:
    """A parenthesized subshell: a directory change inside it does not leave it."""

    script: list[Any]


class _WordBuilder:
    """The word being read: its text so far, whether it was started, whether a ``$`` was met."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.started = False
        self.expands = False
        self.substitutions: list[list[Any]] = []

    def add(self, text: str) -> None:
        self.parts.append(text)
        self.started = True


class _Frame:
    """One script being read: the finished units, the command's words, the word under way."""

    def __init__(self) -> None:
        self.units: list[Any] = []
        self.words: list[_Word] = []
        self.builder = _WordBuilder()


_DIGITS_RE = re.compile(r"[0-9]+")
_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# Words a command word may hide behind: a wrapper that runs the next command, and the shell
# keywords that open a command (`then git commit`).
_WRAPPERS = frozenset(
    {"env", "command", "time", "nohup", "exec", "!", "{", "}", "if", "then", "else", "elif", "do", "while", "until"}
)
_SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
_ENVIRONMENT_REPOSITORY = frozenset({"GIT_DIR", "GIT_WORK_TREE"})
_SHORT_OPTION = 2  # `-B`: a dash and a letter
_WRITE_OPERANDS = 2  # `symbolic-ref <name> <ref>` writes; one operand reads
_LAYOUT_PATHS = 2  # `rev-parse --git-dir --git-common-dir` prints one path per line
_FORGE_PROGRAMS = ("gh", "glab")  # the forge command lines the guard reads like git's
_FORGE_NAME_WORDS = 2  # `gh <group> <action>`: `pr create`; `glab mr create`
_FORGE_API = "api"  # `gh api <endpoint> -X POST`: the options after it are its arguments
_FORGE_VALUED_OPTIONS = frozenset({"-R", "--repo"})  # `gh -R owner/name pr create`


class _Parser:
    """Reads shell text into scripts of simple commands, with no filesystem and no execution.

    It splits on unquoted ``; & | newline`` and parentheses, honours quotes and backslashes,
    skips heredoc bodies, and reads ``$(...)`` and backticks as scripts of their own. It is the
    reading of a command's *words* — what only a command word may be — not a shell.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0
        self._heredocs: list[tuple[str, bool]] = []
        self._redirect_target_next = False
        self._redirect_write_next = False

    def script(self, *, nested: bool) -> list[Any]:
        """Read to the end of the text, or, when ``nested``, to the ``)`` that closes it."""
        frame = _Frame()
        text = self._text
        while self._pos < len(text):
            char = text[self._pos]
            if char in " \t":
                self._pos += 1
                self._end_word(frame)
            elif char == "\n":
                self._pos += 1
                self._end_command(frame)
                self._skip_heredocs()
            elif char in ";&|":
                self._pos += 1
                self._end_command(frame)
            elif char == "(":
                self._pos += 1
                self._end_command(frame)
                frame.units.append(_Group(self.script(nested=True)))
            elif char == ")":
                self._pos += 1
                self._end_command(frame)
                if nested:
                    return frame.units
            elif char == "#" and not frame.builder.started:
                end = text.find("\n", self._pos)
                self._pos = len(text) if end < 0 else end
            elif char in "<>":
                self._redirect(frame)
            else:
                self._word_character(frame)
        self._end_command(frame)
        return frame.units

    def _end_word(self, frame: _Frame) -> None:
        builder = frame.builder
        if builder.started:
            frame.words.append(
                _Word(
                    "".join(builder.parts),
                    builder.expands,
                    tuple(builder.substitutions),
                    not self._redirect_target_next,
                    self._redirect_target_next and self._redirect_write_next,
                )
            )
            self._redirect_target_next = False
            self._redirect_write_next = False
        frame.builder = _WordBuilder()

    def _end_command(self, frame: _Frame) -> None:
        self._end_word(frame)
        self._redirect_target_next = False
        self._redirect_write_next = False
        if frame.words:
            frame.units.append(_Command(tuple(frame.words)))
            frame.words = []

    def _word_character(self, frame: _Frame) -> None:
        text = self._text
        builder = frame.builder
        char = text[self._pos]
        if char == "\\":
            following = text[self._pos + 1 : self._pos + 2]
            if following not in ("", "\n"):
                builder.add(following)
            self._pos += 2 if following else 1
        elif char == "'":
            end = text.find("'", self._pos + 1)
            end = len(text) if end < 0 else end
            builder.add(text[self._pos + 1 : end])
            self._pos = end + 1
        elif char == '"':
            self._double_quoted(builder)
        elif char == "$":
            self._dollar(builder)
        elif char == "`":
            self._backtick(builder)
        else:
            builder.add(char)
            self._pos += 1

    def _double_quoted(self, builder: _WordBuilder) -> None:
        text = self._text
        builder.add("")
        self._pos += 1
        while self._pos < len(text):
            char = text[self._pos]
            if char == '"':
                self._pos += 1
                return
            if char == "\\":
                following = text[self._pos + 1 : self._pos + 2]
                if following and following in '"\\$`':
                    builder.add(following)
                    self._pos += 2
                elif following == "\n":
                    self._pos += 2
                else:
                    builder.add(char)
                    self._pos += 1
            elif char == "$":
                self._dollar(builder)
            elif char == "`":
                self._backtick(builder)
            else:
                builder.add(char)
                self._pos += 1

    def _dollar(self, builder: _WordBuilder) -> None:
        builder.expands = True
        if self._text.startswith("$(", self._pos):
            self._pos += 2
            builder.started = True
            builder.substitutions.append(self.script(nested=True))
        else:
            builder.add("$")
            self._pos += 1

    def _backtick(self, builder: _WordBuilder) -> None:
        text = self._text
        inner: list[str] = []
        position = self._pos + 1
        while position < len(text) and text[position] != "`":
            if text[position] == "\\" and text[position + 1 : position + 2] and text[position + 1] in "`\\$":
                inner.append(text[position + 1])
                position += 2
            else:
                inner.append(text[position])
                position += 1
        self._pos = position + 1
        builder.expands = True
        builder.started = True
        builder.substitutions.append(_Parser("".join(inner)).script(nested=False))

    def _redirect(self, frame: _Frame) -> None:
        text = self._text
        if text.startswith("(", self._pos + 1):  # process substitution: the group follows
            self._end_word(frame)
            self._pos += 1
            return
        if frame.builder.started and _DIGITS_RE.fullmatch("".join(frame.builder.parts)):
            frame.builder = _WordBuilder()  # a file descriptor number, not an operand
        self._end_word(frame)
        if text.startswith("<<<", self._pos):
            self._pos += 3
            self._redirect_target_next = True
        elif text.startswith("<<", self._pos):
            self._heredoc(self._pos + 2)
        else:
            start = self._pos
            self._pos += 1
            while self._pos < len(text) and text[self._pos] in "&>|<":
                self._pos += 1
            self._redirect_target_next = True
            self._redirect_write_next = ">" in text[start : self._pos]

    def _heredoc(self, position: int) -> None:
        """Read ``<<WORD`` or ``<<-WORD`` and remember its delimiter; the body is skipped at the newline."""
        text = self._text
        strip_tabs = text.startswith("-", position)
        position += 1 if strip_tabs else 0
        while position < len(text) and text[position] in " \t":
            position += 1
        parts: list[str] = []
        while position < len(text) and text[position] not in " \t\n;&|()<>":
            char = text[position]
            if char == "\\" and position + 1 < len(text):
                parts.append(text[position + 1])
                position += 2
            elif char in "'\"":
                end = text.find(char, position + 1)
                end = len(text) if end < 0 else end
                parts.append(text[position + 1 : end])
                position = end + 1
            else:
                parts.append(char)
                position += 1
        self._pos = position
        self._heredocs.append(("".join(parts), strip_tabs))

    def _skip_heredocs(self) -> None:
        text = self._text
        for delimiter, strip_tabs in self._heredocs:
            while self._pos < len(text):
                end = text.find("\n", self._pos)
                line = text[self._pos :] if end < 0 else text[self._pos : end]
                self._pos = len(text) if end < 0 else end + 1
                if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                    break
        self._heredocs = []


def _joined(directory: str | None, path: str) -> str | None:
    """``path`` read from ``directory``: lexical, so ``..`` is left for the program that opens it."""
    if path.startswith("/"):
        return path
    if directory is None:
        return None
    if path == "":
        return directory
    return directory + path if directory.endswith("/") else directory + "/" + path


def _target_directory(word: _Word, directory: str | None, home: str | None) -> str | None:
    """Where a ``cd`` or ``-C`` operand leads from ``directory``; ``None`` when the text does not say."""
    if word.expands:
        return None
    value = word.value
    if value == "~" or value.startswith("~/"):
        return None if home is None else _joined(directory, home + value[1:])
    if value.startswith("~"):
        return None
    return _joined(directory, value)


def _is_option(word: _Word) -> bool:
    return word.value.startswith("-") and len(word.value) > 1


def _changed_directory(operands: Sequence[_Word], directory: str | None, home: str | None) -> str | None:
    """The directory after ``cd``/``pushd``; ``None`` for no literal path, ``-``, or an expansion."""
    paths = list(operands)
    while paths and _is_option(paths[0]):
        paths.pop(0)
    if not paths or paths[0].value == "-":
        return None
    return _target_directory(paths[0], directory, home)


def _git_invocation(
    operands: Sequence[_Word], directory: str | None, *, repository_unknown: bool, home: str | None
) -> GitInvocation | None:
    """The subcommand after git's global options, its arguments, and the directory they and ``directory`` give."""
    unknown = repository_unknown
    overridden = False
    index = 0
    while index < len(operands):
        value = operands[index].value
        if value == "-C":
            index += 1
            if index < len(operands):
                directory = _target_directory(operands[index], directory, home)
        elif value in ("-c", "--config-env"):
            index += 1
            overridden = True
        elif value.startswith("--config-env="):
            overridden = True
        elif value == "--namespace":
            index += 1
        elif value in ("--git-dir", "--work-tree"):
            index += 1
            unknown = True
        elif value.startswith(("--git-dir=", "--work-tree=")):
            unknown = True
        elif not value.startswith("-"):
            arguments = tuple(word.value for word in operands[index + 1 :])
            return GitInvocation(value, None if unknown else directory, arguments, config_override=overridden)
        index += 1
    return None


def _forge_invocation(operands: Sequence[_Word], directory: str | None, program: str) -> GitInvocation | None:
    """The group and action of a ``gh``/``glab`` command (``pr create``), its arguments, and where it runs.

    Options are skipped (``-R``/``--repo`` take the next word); a group with no action (``gh pr``) is
    the subcommand alone. ``api`` takes no action word: its arguments are every word after it, options
    included. ``None`` when no word names a group.
    """
    words = [word.value for word in operands]
    names: list[str] = []
    rest: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if len(names) == _FORGE_NAME_WORDS:
            rest = words[index:]
            break
        if word.startswith("-"):
            index += 1 + (word in _FORGE_VALUED_OPTIONS)
            continue
        names.append(word)
        index += 1
        if names == [_FORGE_API]:
            rest = words[index:]
            break
    if not names:
        return None
    return GitInvocation(" ".join(names), directory, tuple(rest), program=program)


def _shell_script(operands: Sequence[_Word]) -> str | None:
    """The string argument of ``-c`` in the arguments of ``bash``/``sh``/``zsh``/``dash``, if any."""
    for index, word in enumerate(operands):
        value = word.value
        if not value.startswith("-"):
            return None
        if not value.startswith("--") and "c" in value[1:]:
            return operands[index + 1].value if index + 1 < len(operands) else None
    return None


def _nested_script(name: str, operands: Sequence[_Word]) -> str | None:
    """The shell text a command runs by itself: the ``-c`` string of a shell, or what ``eval`` joins."""
    if name.rsplit("/", 1)[-1] in _SHELLS:
        return _shell_script(operands)
    if name == "eval":
        return " ".join(word.value for word in operands)
    return None


def _command_start(words: Sequence[_Word]) -> tuple[int, bool]:
    """Where a command's own word is among ``words``, and whether a leading assignment moved git's repository.

    Leading ``VAR=value`` words and wrappers are skipped; the index is ``len(words)`` when nothing runs.
    """
    repository_unknown = False
    index = 0
    while index < len(words):
        value = words[index].value
        if _ASSIGNMENT_RE.match(value):
            repository_unknown = repository_unknown or value.split("=", 1)[0] in _ENVIRONMENT_REPOSITORY
        elif value in _WRAPPERS:
            while index + 1 < len(words) and _is_option(words[index + 1]):
                index += 1
        else:
            break
        index += 1
    return index, repository_unknown


def _walk_command(command: _Command, directory: str | None, home: str | None, found: list[GitInvocation]) -> str | None:
    for word in command.words:
        for substitution in word.substitutions:
            _walk_script(substitution, directory, home, found)
    words = [word for word in command.words if word.operand]
    index, repository_unknown = _command_start(words)
    if index >= len(words):
        return directory
    name = words[index].value
    operands = words[index + 1 :]
    program = name.rsplit("/", 1)[-1]
    if name in ("cd", "pushd"):
        return _changed_directory(operands, directory, home)
    if name == "popd":
        return None
    if program == "git":
        invocation = _git_invocation(operands, directory, repository_unknown=repository_unknown, home=home)
    elif program in _FORGE_PROGRAMS:
        invocation = _forge_invocation(operands, directory, program)
    else:
        invocation = None
        script = _nested_script(name, operands)
        if script is not None:
            _walk_script(_Parser(script).script(nested=False), directory, home, found)
    if invocation is not None:
        found.append(invocation)
    return directory


def _walk_script(script: Sequence[Any], directory: str | None, home: str | None, found: list[GitInvocation]) -> None:
    for unit in script:
        if isinstance(unit, _Group):
            _walk_script(unit.script, directory, home, found)
        else:
            directory = _walk_command(unit, directory, home, found)


def git_invocations(
    command: str, start_directory: str | None, *, home_directory: str | None = None
) -> list[GitInvocation]:
    """Every ``git``, ``gh`` and ``glab`` command a shell command runs, in order, with the directory each runs in.

    Only *command words* count: a heredoc body, a quoted argument (``echo "git push"``,
    ``grep 'git merge' f``) and a comment are text. The scan follows ``;``, ``&&``, ``||``, pipes,
    newlines, parentheses, ``$(...)``, backticks, ``bash -c '...'`` and ``eval``; it skips leading
    ``VAR=value`` and the wrappers ``env command time nohup exec``; and it tracks ``cd``/``pushd`` and
    git's ``-C``. It reads no file: ``start_directory`` is where the command starts, and a directory the
    text does not determine (a ``$`` expansion, ``GIT_DIR``, ``--git-dir``, ``cd -``) is ``None``.
    ``~`` is ``home_directory``, or an unknown place when that is ``None``.
    """
    found: list[GitInvocation] = []
    _walk_script(_Parser(command).script(nested=False), start_directory, home_directory, found)
    return found


def _destination(values: Sequence[str], shell: Mapping[str, Any]) -> list[str]:
    """The path ``cp``/``mv``/``install`` writes: the last operand, or the sources' names inside a ``-t`` directory."""
    target_directory: str | None = None
    operands: list[str] = []
    index = 0
    while index < len(values):
        value = values[index]
        long_name, _, attached = value.partition("=")
        if value in shell["target_directory_options"]:
            target_directory = values[index + 1] if index + 1 < len(values) else None
            index += 1
        elif long_name in shell["target_directory_options"] and attached:
            target_directory = attached
        elif value.startswith("-t") and not value.startswith("--") and len(value) > _SHORT_OPTION:
            target_directory = value[_SHORT_OPTION:]
        elif not (value.startswith("-") and len(value) > 1):
            operands.append(value)
        index += 1
    if target_directory is not None:
        return [target_directory.rstrip("/") + "/" + operand.rstrip("/").rsplit("/", 1)[-1] for operand in operands]
    return operands[-1:]


def _write_candidates(program: str, operands: Sequence[_Word], shell: Mapping[str, Any]) -> list[str]:
    """The paths a program writes among its ``operands``: the words, by what ``harness_settings.json`` says it does.

    ``tee`` and ``sponge`` write every operand; ``sed -i`` and ``perl -i`` (any option cluster holding the
    letter, or ``--in-place``) write the files they name; ``cp``, ``mv`` and ``install`` write their last
    operand, or, with ``-t DIRECTORY``, a file of that name in it; ``dd`` writes its ``of=`` operand.
    """
    values = [word.value for word in operands]
    options = [value for value in values if value.startswith("-") and len(value) > 1]
    if program in shell["write_all_operands"]:
        return [value for value in values if value not in options]
    letter = shell["in_place"].get(program)
    if letter is not None:
        long_option = shell["in_place_long_option"]
        in_place = any(
            option == long_option or option.startswith(long_option + "=")
            if option.startswith("--")
            else letter in option[1:]
            for option in options
        )
        return [value for value in values if value not in options] if in_place else []
    if program in shell["write_last_operand"]:
        return _destination(values, shell)
    prefix = shell["operand_assignments"].get(program)
    if prefix is not None:
        return [value[len(prefix) :] for value in values if value.startswith(prefix)]
    return []


def _settings_file_among(candidates: Sequence[str], directory: str | None, data: Mapping[str, Any]) -> str | None:
    """The first of ``candidates`` that names a harness settings file, spelled as given or read from ``directory``."""
    for candidate in candidates:
        for path in (candidate, _joined(directory, candidate)):
            if path is not None and harness_settings.file_format(path, data) is not None:
                return candidate
    return None


def _written_settings_file(
    command: _Command, directory: str | None, home: str | None, data: Mapping[str, Any]
) -> tuple[str | None, str | None]:
    """The harness settings file ``command`` writes, if any, and the directory after it (``cd`` moves it)."""
    for word in command.words:
        for substitution in word.substitutions:
            path = _written_settings_in(substitution, directory, home, data)
            if path is not None:
                return path, directory
    candidates = [word.value for word in command.words if word.write]
    words = [word for word in command.words if word.operand]
    index, _ = _command_start(words)
    if index < len(words):
        name = words[index].value
        operands = words[index + 1 :]
        if name in ("cd", "pushd"):
            return None, _changed_directory(operands, directory, home)
        if name == "popd":
            return None, None
        candidates += _write_candidates(name.rsplit("/", 1)[-1], operands, data["shell"])
        script = _nested_script(name, operands)
        if script is not None:
            path = _written_settings_in(_Parser(script).script(nested=False), directory, home, data)
            if path is not None:
                return path, directory
    return _settings_file_among(candidates, directory, data), directory


def _written_settings_in(
    script: Sequence[Any], directory: str | None, home: str | None, data: Mapping[str, Any]
) -> str | None:
    """The first harness settings file a script's commands write, as the command spells it."""
    for unit in script:
        if isinstance(unit, _Group):
            path = _written_settings_in(unit.script, directory, home, data)
        else:
            path, directory = _written_settings_file(unit, directory, home, data)
        if path is not None:
            return path
    return None


def _settings_write_reason(command: str, directory: str | None) -> str | None:
    """The reason to deny ``command`` for writing a harness settings file, ``None`` when no command word does.

    The data file names the directories (``.claude``, ``.codex``) that a command, or the directory it starts
    in, must mention for the command to be parsed at all.
    """
    data = harness_settings.read_data()
    if not any(entry["directory"] in command or entry["directory"] in (directory or "") for entry in data["files"]):
        return None
    path = _written_settings_in(_Parser(command).script(nested=False), directory, _home_directory(), data)
    return None if path is None else harness_settings.write_reason(path, data)


def _git_output(directory: str, *arguments: str) -> str | None:
    """Standard output of ``git -C directory <arguments>``; ``None`` on any failure."""
    try:
        completed = subprocess.run(
            ["git", "-C", directory, *arguments],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def repository_facts(directory: str) -> RepositoryFacts | None:
    """Ask git what repository ``directory`` is in; ``None`` when it is in none or git cannot say.

    A worktree is *linked* when its git directory differs from the common one the main checkout
    keeps. A detached ``HEAD`` has the branch ``""``.
    """
    layout = _git_output(directory, "rev-parse", "--git-dir", "--git-common-dir")
    paths = [] if layout is None else layout.rstrip("\n").split("\n")
    if len(paths) != _LAYOUT_PATHS:
        return None
    git_dir, common_dir = (Path(directory, path).resolve() for path in paths)
    branch = _git_output(directory, "symbolic-ref", "--short", "-q", "HEAD")
    return RepositoryFacts(linked=git_dir != common_dir, branch=(branch or "").strip())


class _Access:
    """What one actor may do: the matrix row, and the texts that say so (ADR 0031/D07).

    Built once per guard call from ``common/access_matrix.json`` and ``hook_core.json``.
    """

    def __init__(self, actor: access_matrix.Actor, run_branch: str | None = None) -> None:
        self.actor = access_matrix.Actor(actor)  # a plain string is read as the value it spells
        self.run_branch = run_branch
        self.texts = _hook_core_data()
        self._matrix = access_matrix.read_data()
        # The branches this actor is kept off as it is off the default branch: the default and its protected ones.
        self._protected = access_matrix.protected_branches(self._matrix, self.actor)

    def is_default_branch(self, branch: str) -> bool:
        """Whether ``branch`` is a default branch or one the actor is kept off like it (``develop``, ``release/*``)."""
        return branch in self.texts["git_default_branches"] or access_matrix.is_protected_branch(
            self._protected, branch
        )

    def is_own_branch(self, branch: str) -> bool:
        """Whether ``branch`` is one the actor may write: for an autonomous run, its own run branch."""
        return access_matrix.is_own_branch(self._matrix, self.actor, branch, self.run_branch)

    def result(self, action_class: str, values: Mapping[str, str]) -> HookResult | None:
        """What the matrix gives the actor for ``action_class``: ``None`` to pass, else an ask or a deny.

        The reason is the actor's text for the class (``access_reasons`` in ``hook_core.json``) filled
        with ``values``.
        """
        outcome = access_matrix.outcome(self._matrix, self.actor, action_class)
        if outcome == "allow":
            return None
        template = self.texts[self.texts["access_reasons"][self.actor.value][action_class]]
        return HookResult(
            event_name="PreToolUse", permission_decision=outcome, permission_reason=jsondata.fill(template, values)
        )

    def uniform(self, action_classes: Iterable[str]) -> bool:
        """Whether the actor gets one outcome for all of ``action_classes``: telling them apart changes nothing."""
        return len({access_matrix.outcome(self._matrix, self.actor, name) for name in action_classes}) == 1

    def history_result(self, subcommand: str, place: str, facts: Mapping[str, str]) -> HookResult | None:
        """The result for ``subcommand`` writing history at a ``place`` (a ``history_*`` class), ``facts`` naming it."""
        if access_matrix.outcome(self._matrix, self.actor, place) == "allow":
            return None
        where = jsondata.fill(self.texts[self.texts["access_where"][self.actor.value][place]], facts)
        return self.result(place, {"subcommand": subcommand, "where": where})


# The classes a push of a branch falls into (a tag is its own class, ``tag``).
_PUSH_CLASSES = ("push_own_branch", "push_own_branch_forced", "push_default_branch", "push_other_branch")
_OUTCOME_ORDER = {outcome: rank for rank, outcome in enumerate(access_matrix.OUTCOMES)}


def _most_restrictive(results: Sequence[HookResult | None]) -> HookResult | None:
    """The result with the strictest decision among ``results`` (an ``ask`` before a pass, a ``deny`` before an ask)."""
    decided = [result for result in results if result is not None]
    if not decided:
        return None
    return max(decided, key=lambda result: _OUTCOME_ORDER[result.permission_decision or "allow"])


def strictest_result(results: Sequence[HookResult | None]) -> HookResult | None:
    """The result with the strictest decision among ``results`` (``deny`` before ``ask`` before a pass).

    The first of equally strict results wins, so a caller lists the guard whose reason it prefers first.

    Runtime classification: operational
    Rationale: it picks among results the guards already rendered and authors no rule or text of its own;
    the entry points combine the commit guard and the browser guard with it (ADR 0032/D07).
    """
    return _most_restrictive(results)


def _history_place(
    directory: str | None, repository_at: Callable[[str], RepositoryFacts | None], access: _Access
) -> tuple[str, dict[str, str]]:
    """Where ``directory`` puts a history write: its action class in the matrix, and the values naming it.

    ``history_unresolved`` and ``history_not_repository`` have no facts; the rest are
    ``history_{checkout|worktree}_{default|detached|branch}`` -- a linked worktree or not, on a default
    branch, on a detached ``HEAD`` or on a named branch -- and ``history_not_run_branch``: a named branch of
    a checkout (not a linked worktree) that is not the actor's own run branch. A linked worktree's branch is
    its own by the job-branch carve-out, so the run branch does not narrow it (ADR 0031/D07).
    """
    if directory is None:
        return "history_unresolved", {}
    facts = repository_at(directory)
    if facts is None:
        return "history_not_repository", {"directory": directory}
    where = "worktree" if facts.linked else "checkout"
    if not facts.branch:
        branch = "detached"
    elif access.is_default_branch(facts.branch):
        branch = "default"
    elif not facts.linked and not access.is_own_branch(facts.branch):
        return "history_not_run_branch", {"directory": directory, "branch": facts.branch}
    else:
        branch = "branch"
    return f"history_{where}_{branch}", {"directory": directory, "branch": facts.branch}


def _is_job_branch(name: str, data: Mapping[str, Any]) -> bool:
    """Whether ``name`` is a job branch, short (``_aitna/x``) or full (``refs/heads/_aitna/x``)."""
    prefix = data["git_job_branch_prefix"]
    return name.startswith((prefix, data["git_heads_prefix"] + prefix))


def _split_arguments(arguments: Sequence[str], valued: Collection[str] = ()) -> tuple[list[str], list[str]]:
    """Git arguments as ``(options, operands)``: ``--`` ends the options, a ``valued`` option takes the next word."""
    options: list[str] = []
    operands: list[str] = []
    index = 0
    options_ended = False
    while index < len(arguments):
        word = arguments[index]
        if options_ended or not word.startswith("-") or word == "-":
            operands.append(word)
        elif word == "--":
            options_ended = True
        else:
            options.append(word)
            index += word in valued
        index += 1
    return options, operands


def _option_letters(options: Sequence[str], long_names: Mapping[str, str]) -> set[str]:
    """The flags among ``options`` as letters: ``long_names`` spell the long ones, a ``u`` ends a cluster."""
    flags: set[str] = set()
    for word in options:
        if word.startswith("--"):
            flags.update(long_names.get(word.split("=", 1)[0], ""))
            continue
        for letter in word[1:]:
            flags.add(letter)
            if letter == "u":  # the rest of the cluster is the upstream's name
                break
    return flags


_BRANCH_LONG_FLAGS = {
    "--force": "f",
    "--delete": "d",
    "--move": "m",
    "--copy": "c",
    "--set-upstream-to": "u",
    "--unset-upstream": "u",
}
# subcommand: (letter that forces, letters that take a branch name, long form that forces)
_FORCE_CREATE = {"checkout": ("B", "bB", ""), "switch": ("C", "cC", "--force-create")}


def _current_branch(invocation: GitInvocation, repository_at: Callable[[str], RepositoryFacts | None]) -> str | None:
    """The branch ``invocation``'s repository is on; ``None`` when the text, git or a detached ``HEAD`` do not say."""
    if invocation.directory is None:
        return None
    facts = repository_at(invocation.directory)
    return (facts.branch or None) if facts is not None else None


def _branch_offenders(
    invocation: GitInvocation, data: Mapping[str, Any], repository_at: Callable[[str], RepositoryFacts | None]
) -> list[str | None]:
    """The branches ``git branch`` writes to that are not job branches; ``None`` is a current branch not named.

    Listing, creating a new branch and the upstream options write no existing branch.
    """
    options, operands = _split_arguments(invocation.arguments)
    flags = {letter.lower() for letter in _option_letters(options, _BRANCH_LONG_FLAGS)}
    if "u" in flags or not flags & set("dmcf"):
        return []
    names: list[str | None]
    if flags & set("mc"):
        names = list(operands)
        if len(operands) == 1:  # one name: the current branch is the other end
            names.append(_current_branch(invocation, repository_at))
    else:
        names = list(operands) if "d" in flags else list(operands[:1])  # force: the first name only
    return [name for name in names if name is None or not _is_job_branch(name, data)]


def _forced_branch_offenders(invocation: GitInvocation, data: Mapping[str, Any]) -> list[str]:
    """The branch ``checkout -B`` or ``switch -C``/``--force-create`` writes over, unless it is a job branch."""
    letter, valued_letters, long_name = _FORCE_CREATE[invocation.subcommand]
    arguments = invocation.arguments
    names: list[str] = []
    for index, word in enumerate(arguments):
        if word == "--":
            break
        if long_name and word.split("=", 1)[0] == long_name:
            names.extend([word.partition("=")[2]] if "=" in word else arguments[index + 1 : index + 2])
        elif word.startswith("-") and not word.startswith("--"):
            cluster = word[1:]
            position = next((at for at, char in enumerate(cluster) if char in valued_letters), None)
            if position is not None and cluster[position] == letter:  # the rest of the word, or the next, is the name
                rest = cluster[position + 1 :]
                names.extend([rest] if rest else arguments[index + 1 : index + 2])
    return [name for name in names if not _is_job_branch(name, data)]


def _fetch_offenders(invocation: GitInvocation, data: Mapping[str, Any]) -> list[str]:
    """The refspec destinations of ``fetch``/``pull`` that are not remote-tracking refs or job branches."""
    _, operands = _split_arguments(invocation.arguments, data["git_fetch_valued_options"])
    destinations = []
    for refspec in operands[1:]:  # the first operand is the remote
        destination = refspec.removeprefix("+").partition(":")[2]
        if (
            destination
            and not destination.startswith(data["git_remotes_prefix"])
            and not _is_job_branch(destination, data)
        ):
            destinations.append(destination)
    return destinations


def _symbolic_ref_offenders(invocation: GitInvocation, data: Mapping[str, Any]) -> list[str]:
    """The refs ``symbolic-ref`` writes or deletes that are not job branches: ``HEAD`` may point at one."""
    options, operands = _split_arguments(invocation.arguments, ("-m",))
    deleting = "d" in _option_letters(options, {"--delete": "d"})
    if deleting:
        written = operands[:1]
    elif len(operands) >= _WRITE_OPERANDS:
        written = [name for name in operands[:1] if name != "HEAD"] + operands[1:2]
    else:
        return []
    return [name for name in written if not _is_job_branch(name, data)]


def _update_ref_offenders(invocation: GitInvocation, data: Mapping[str, Any]) -> list[str]:
    """The ref ``update-ref`` writes when it is not ``refs/heads/_aitna/*``; ``[""]`` for refs read from stdin."""
    options, operands = _split_arguments(invocation.arguments, ("-m",))
    if "--stdin" in options:
        return [""]
    job_heads = data["git_heads_prefix"] + data["git_job_branch_prefix"]
    return [name for name in operands[:1] if not name.startswith(job_heads)]


def _ref_subcommand(invocation: GitInvocation) -> str:
    """The command as the ref rules name it: ``worktree`` joins its action (``worktree remove``)."""
    if invocation.subcommand != "worktree":
        return invocation.subcommand
    _, operands = _split_arguments(invocation.arguments)
    return " ".join(["worktree", *operands[:1]])


def _ref_target(
    invocation: GitInvocation, data: Mapping[str, Any], repository_at: Callable[[str], RepositoryFacts | None]
) -> str | None:
    """What a ref-writing ``invocation`` moves, renames or deletes beyond job branches, in words; ``None`` if none."""
    subcommand = _ref_subcommand(invocation)
    if subcommand in data["git_ref_unconditional"]:
        return data["git_ref_unconditional"][subcommand]
    offenders: Sequence[str | None]
    if subcommand == "branch":
        offenders = _branch_offenders(invocation, data, repository_at)
    elif subcommand in _FORCE_CREATE:
        offenders = _forced_branch_offenders(invocation, data)
    elif subcommand in ("fetch", "pull"):
        offenders = _fetch_offenders(invocation, data)
    elif subcommand == "symbolic-ref":
        offenders = _symbolic_ref_offenders(invocation, data)
    elif subcommand == "update-ref":
        offenders = _update_ref_offenders(invocation, data)
    else:
        return None
    if not offenders:
        return None
    if offenders == [""]:
        return data["git_commit_ref_target_stdin"]
    return ", ".join(
        data["git_commit_ref_target_current_branch"] if name is None else f"'{name}'"
        for name in dict.fromkeys(offenders)
    )


def _push_flags(options: Sequence[str], data: Mapping[str, Any]) -> set[str]:
    """The flags of ``git push`` that decide its class.

    ``f`` force, ``d`` delete, ``a`` all branches, ``t`` tags, ``T`` the tags that follow the pushed commits.
    """
    flags: set[str] = set()
    for word in options:
        if word.startswith("--"):
            flags.update(data["git_push_long_flags"].get(word.split("=", 1)[0], ""))
        else:
            flags.update(letter for letter in word[1:] if letter in "fd")
    return flags


def _refspec_class(refspec: str, *, forced: bool, current: str | None, access: _Access) -> tuple[str, str]:
    """The matrix class of one pushed refspec and the ref it writes.

    The destination decides: a tag, a default branch, the branch the repository is on (``current``;
    ``HEAD`` stands for it) when that is the actor's own branch (an autonomous run's run branch), or another
    branch. A ``+`` prefix, a ``:destination`` with no source and
    the caller's ``forced`` (``--force``, ``--delete``) make a push of the own branch the forced one.
    """
    spec = refspec.removeprefix("+")
    source, colon, destination = spec.partition(":")
    target = destination if colon else source
    if target.startswith("refs/tags/"):
        return "tag", target
    target = target.removeprefix("refs/heads/")
    if target == "HEAD" and current is not None:
        target = current
    if access.is_default_branch(target):
        return "push_default_branch", target
    if target != current or not access.is_own_branch(target):
        return "push_other_branch", target
    forcing = forced or refspec.startswith("+") or (bool(colon) and not source)
    return ("push_own_branch_forced" if forcing else "push_own_branch"), target


def _push_decision(
    invocation: GitInvocation, access: _Access, repository_at: Callable[[str], RepositoryFacts | None]
) -> HookResult | None:
    """The strictest decision among the refs ``git push`` writes: which class each is, the matrix says what it gets.

    A push that names no refspec, or runs under ``-c`` configuration, writes where git's configuration
    says (``push.default``, ``remote.*.push``): its destination is not the text's, so it is another branch's.
    """
    data = access.texts
    options, operands = _split_arguments(invocation.arguments, data["git_push_valued_options"])
    flags = _push_flags(options, data)
    base = {"subcommand": invocation.subcommand}
    if "a" in flags:  # --all, --branches and --mirror write the default branch with the rest
        return access.result("push_default_branch", {**base, "branch": data["git_push_all_target"]})
    repo_named = any(word.split("=", 1)[0] == "--repo" for word in options)
    refspecs = operands if repo_named else operands[1:]  # the first operand is the remote
    # No lookup where the branch cannot change the outcome (a developer's push asks wherever it goes).
    current = None if access.uniform(_PUSH_CLASSES) else _current_branch(invocation, repository_at)
    forced = bool(flags & {"f", "d"})
    classes: list[tuple[str, str]] = []  # (matrix class, the ref as the reason names it)
    if flags & {"t", "T"}:
        classes.append(("tag", "'--tags'" if "t" in flags else "'--follow-tags'"))
    if invocation.config_override:
        classes.append(("push_other_branch", data["git_push_config_target"]))
    elif refspecs:
        for spec in refspecs:
            name, ref = _refspec_class(spec, forced=forced, current=current, access=access)
            classes.append((name, f"'{ref}'"))
    elif "t" not in flags:
        classes.append(("push_other_branch", data["git_push_implicit_target"]))
    return _most_restrictive([access.result(name, {**base, "branch": ref}) for name, ref in classes])


def _publishing_decision(
    invocation: GitInvocation, access: _Access, repository_at: Callable[[str], RepositoryFacts | None]
) -> HookResult | None:
    """What the actor gets for ``push`` or ``tag``: a push by the branch it writes, a tag by its own class."""
    if invocation.subcommand == "push":
        return _push_decision(invocation, access, repository_at)
    return access.result("tag", {"subcommand": invocation.subcommand})


def _glob_pattern(pattern: str) -> re.Pattern[str]:
    """The regular expression of a ``git_config_push_keys`` pattern: ``*`` is one or more characters."""
    return re.compile(".+".join(re.escape(part) for part in pattern.split("*")))


def _config_written_name(invocation: GitInvocation, data: Mapping[str, Any]) -> tuple[str, bool] | None:
    """What a ``git config`` writes: ``(name, is_section)``; ``("", False)`` for an editor; ``None`` for a read.

    The old form (``config [--unset] <key> [<value>]``) and the ``set``/``unset`` actions of git 2.46 are
    both read; a lone key, ``--get``, ``--list`` and the ``get``/``list`` actions read.
    """
    options, operands = _split_arguments(invocation.arguments, data["git_config_valued_options"])
    actions = data["git_config_actions"]
    if set(options) & set(data["git_config_read_options"]):
        return None
    if set(options) & set(data["git_config_edit_options"]):
        return "", False
    known_actions = {name for names in actions.values() for name in names}
    action = operands[0] if operands and operands[0] in known_actions else None
    if action in actions["read"]:
        return None
    if action in actions["edit"]:
        return "", False
    if action is not None:
        names = operands[1:2]
        is_section = action in actions["section_write"]
    elif set(options) & set(data["git_config_section_write_options"]):
        names, is_section = operands[:1], True
    elif set(options) & set(data["git_config_key_write_options"]) or len(operands) >= _WRITE_OPERANDS:
        names, is_section = operands[:1], False
    else:
        return None
    return (names[0], is_section) if names else None


def _is_push_config(name: str, data: Mapping[str, Any], *, is_section: bool) -> bool:
    """Whether the key (or section) ``name`` is one of ``git_config_push_keys``; ``""`` (an editor) is."""
    if not name:
        return True
    key = name.lower()
    for pattern in data["git_config_push_keys"]:
        # a section is written whole: test it with the variable its pattern names
        candidate = f"{key}.{pattern.rsplit('.', 1)[1].replace('*', 'x')}" if is_section else key
        if _glob_pattern(pattern).fullmatch(candidate):
            return True
    return False


def _config_decision(invocation: GitInvocation, access: _Access) -> HookResult | None:
    """What the actor gets for a ``git config`` that writes a push-redirecting key; reads and other keys pass."""
    data = access.texts
    written = _config_written_name(invocation, data)
    if written is None or not _is_push_config(written[0], data, is_section=written[1]):
        return None
    return access.result("config_push_write", {"key": written[0] or data["git_config_edit_target"]})


def _pull_request_base(invocation: GitInvocation, data: Mapping[str, Any]) -> str | None:
    """The base branch a ``pr create``/``mr create`` names (``--base X``, ``--base=X``, ``-B X``); ``None`` if none.

    Only the program's own base options count (``pr_base_options`` in ``hook_core.json``: ``-b`` is
    ``gh``'s body and ``glab``'s target branch). An option with no value reads as the empty name. Where
    the option is repeated the last value wins, as in ``gh`` and ``glab``.
    """
    options = data["pr_base_options"][invocation.program]
    arguments = invocation.arguments
    base = None
    for index, word in enumerate(arguments):
        name, equals, value = word.partition("=")
        if name in options:
            base = value if equals else "".join(arguments[index + 1 : index + 2])
        elif not word.startswith("--") and any(
            len(option) == _SHORT_OPTION and word.startswith(option) for option in options
        ):
            base = word[_SHORT_OPTION:].removeprefix("=")  # `-Bdevelop`: the value is attached
    return base


def _api_method(invocation: GitInvocation, data: Mapping[str, Any]) -> str:
    """The HTTP method a ``gh api``/``glab api`` sends: the last one named, else POST when it carries fields."""
    methods = data["forge_api_method_options"]
    fields = data["forge_api_field_options"]
    arguments = invocation.arguments
    method = None
    carries_fields = False
    for index, word in enumerate(arguments):
        name, equals, value = word.partition("=")
        if name in methods:
            method = value if equals else "".join(arguments[index + 1 : index + 2])
        elif not word.startswith("--") and any(word.startswith(option) for option in methods):
            method = word[_SHORT_OPTION:]  # `-XPOST`
        elif name in fields or (not word.startswith("--") and any(word.startswith(option) for option in fields)):
            carries_fields = True
    return (method or ("POST" if carries_fields else "GET")).upper()


def _forge_action(invocation: GitInvocation, data: Mapping[str, Any]) -> str:
    """The command's group and action with its aliases resolved (``pr new`` is ``pr create``)."""
    group, _, action = invocation.subcommand.partition(" ")
    group = data["forge_group_aliases"][invocation.program].get(group, group)
    name = f"{group} {action}".rstrip()
    return data["forge_action_aliases"][invocation.program].get(name, name)


def _forge_decision(invocation: GitInvocation, access: _Access) -> HookResult | None:
    """What the actor gets for a ``gh``/``glab`` command: its class, a pull request by the base it targets."""
    data = access.texts
    classes = {"gh": data["gh_action_classes"], "glab": data["glab_action_classes"]}[invocation.program]
    subcommand = _forge_action(invocation, data)
    if subcommand == _FORGE_API:
        action_class = (
            data["forge_api_class"] if _api_method(invocation, data) in data["forge_api_write_methods"] else None
        )
    else:
        action_class = classes.get(subcommand)
    if action_class is None:
        return None
    base = _pull_request_base(invocation, data) if action_class == "pr_create" else None
    if base is not None and base not in data["git_default_branches"]:
        action_class = "pr_create_other_base"
    values = {"program": invocation.program, "subcommand": invocation.subcommand, "base": f"'{base}'"}
    return access.result(action_class, values)


def _invocation_decision(
    invocation: GitInvocation, access: _Access, repository_at: Callable[[str], RepositoryFacts | None]
) -> HookResult | None:
    """What the actor gets for one ``git``, ``gh`` or ``glab`` command: ``None`` to pass, else an ask or a deny."""
    data = access.texts
    if invocation.program in _FORGE_PROGRAMS:
        return _forge_decision(invocation, access)
    if invocation.subcommand in data["git_publishing_subcommands"]:
        return _publishing_decision(invocation, access, repository_at)
    if invocation.subcommand == "config":
        return _config_decision(invocation, access)
    decision = None
    if invocation.subcommand in data["git_history_subcommands"]:
        place, facts = _history_place(invocation.directory, repository_at, access)
        decision = access.history_result(invocation.subcommand, place, facts)
    target = _ref_target(invocation, data, repository_at)
    if decision is not None or target is None:
        return decision
    subcommand = _ref_subcommand(invocation)
    return access.result("ref_write", {"subcommand": subcommand, "target": target})


def _home_directory() -> str | None:
    try:
        return str(Path.home())
    except (RuntimeError, OSError):
        return None


def _working_directory() -> str | None:
    try:
        return str(Path.cwd())
    except OSError:
        return None


@dataclass(frozen=True)
class RunFacts:
    """What a hook's entry point read of the run, for the commit guard.

    ``actor`` is who drives it (``AKMON_ACTOR``), ``run_branch`` the branch an autonomous run owns
    (``AKMON_RUN_BRANCH``; ``None``: the matrix's ``run_branch_patterns`` decide), ``permission_mode`` and
    ``attended`` say whether an ``ask`` reaches anybody (ADR-0025/D06), and ``directory`` is where the command
    starts (default: the process's).
    """

    actor: access_matrix.Actor = access_matrix.Actor.DEVELOPER
    permission_mode: str | None = None
    attended: bool | None = None
    directory: str | None = None
    run_branch: str | None = None


class GuardFacts(TypedDict, total=False):
    """The keyword facts of one run that :func:`git_commit_guard_result` takes: the fields of :class:`RunFacts`."""

    permission_mode: str | None
    attended: bool | None
    actor: access_matrix.Actor
    directory: str | None
    run_branch: str | None


class BrowserFacts(TypedDict, total=False):
    """The keyword facts of one call that :func:`browser_guard_result` takes."""

    actor: access_matrix.Actor
    delegated: bool
    permission_mode: str | None
    attended: bool | None
    directory: str | None


def git_commit_guard_result(command: str, **facts: Unpack[GuardFacts]) -> HookResult | None:
    """Guard ``git``, ``gh`` and ``glab`` commands by the access matrix: who writes history, publishes, opens a PR.

    What each command gets is ``common/access_matrix.json``'s (ADR 0031/D07), by ``actor``: the AI
    co-author trailer is denied wherever it stands in the text, a heredoc body included; only command
    words are read for the rest (:func:`git_invocations`). For a ``developer`` -- the default, and any
    run whose ``AKMON_ACTOR`` the entry point did not read -- ``push`` and ``tag`` ask everywhere; a
    history-writing subcommand (``commit``, ``merge``, ``rebase``, ``reset`` and the others in
    ``hook_core.json``) passes when the repository it acts on -- not the session's -- is a linked
    worktree on a named branch that is not ``main``/``master``, and asks otherwise; a ref write asks
    unless every target is a job branch. An ``autonomous`` run writes history on its own run branch (the
    ``run_branch`` the launcher named, else a branch ``run_branch_patterns`` matches) or in a linked worktree, pushes
    that branch by an explicit refspec (a push that names none, or runs under ``git -c``, is another branch's),
    opens pull requests (merge requests) into the default branch, and is denied the default branch, the branches
    ``protected_branches`` names for it (``develop``, ``release/*``), any other branch of a checkout, any other
    pull request base and a ``git config`` write of a push-redirecting key; ``gh``/``glab api`` writes ask.
    The first invocation that does not pass decides, and an ``ask`` nobody attends becomes a ``deny``.

    The ``facts`` are the fields of :class:`RunFacts`; ``directory`` is where the command starts (default: the
    process's). The repository is asked of git;
    :func:`commit_guard_decision` takes the lookup as a parameter.

    Policy ID: commits.owner-owned
    """
    return commit_guard_decision(command, RunFacts(**facts), repository_facts)


def commit_guard_decision(
    command: str, run: RunFacts, repository_at: Callable[[str], RepositoryFacts | None]
) -> HookResult | None:
    """:func:`git_commit_guard_result` with the repository lookup given.

    ``repository_at`` answers :class:`RepositoryFacts` for a directory (:func:`repository_facts` asks git).
    """
    if not any(program in command for program in ("git", *_FORGE_PROGRAMS)):
        return None

    # The AI trailer is a floor: denied for every actor before, and regardless of, the access matrix.
    trailer = re.search(r"co-authored-by", command, re.IGNORECASE) is not None
    if trailer and "git" in command:
        return _ai_trailer_floor(run.actor)

    start = _working_directory() if run.directory is None else run.directory
    invocations = git_invocations(command, start, home_directory=_home_directory())
    if trailer and any(invocation.program in _FORGE_PROGRAMS for invocation in invocations):
        return _ai_trailer_floor(run.actor)
    access = _Access(run.actor, run.run_branch)
    for invocation in invocations:
        decision = _invocation_decision(invocation, access, repository_at)
        if decision is not None:
            return _escalate_unattended_ask(decision, run.permission_mode, attended=run.attended)
    return None


# --------------------------------------------------------------------------------------
# The browser class of the access matrix (ADR 0032/D07)
# --------------------------------------------------------------------------------------


class _CommandLine(NamedTuple):
    """The words of one command (quotes removed, wrappers kept) and the directory it runs in, if known."""

    words: list[str]
    directory: str | None


def _command_lines(script: Sequence[Any], directory: str | None, home: str | None, found: list[_CommandLine]) -> None:
    """Every command of ``script`` as its words (the command word first, quotes removed), nested scripts included.

    Each line carries the directory it runs in: ``directory`` where the script starts, moved by a ``cd`` / ``pushd``
    before it (``None`` where the text does not determine it).
    """
    for unit in script:
        if isinstance(unit, _Group):
            _command_lines(unit.script, directory, home, found)
            continue
        for word in unit.words:
            for substitution in word.substitutions:
                _command_lines(substitution, directory, home, found)
        words = [word for word in unit.words if word.operand]
        index, _ = _command_start(words)
        if index >= len(words):
            continue
        operands = words[index + 1 :]
        # The line keeps the wrappers (``timeout 30 node ...``): their shapes are read from ``hook_core.json``.
        first = next((at for at, word in enumerate(words) if not _ASSIGNMENT_RE.match(word.value)), index)
        found.append(_CommandLine([word.value for word in words[first:]], directory))
        nested = _nested_script(words[index].value, operands)
        if nested is not None:
            _command_lines(_Parser(nested).script(nested=False), directory, home, found)
        if words[index].value in ("cd", "pushd"):
            directory = _changed_directory(operands, directory, home)
        elif words[index].value == "popd":
            directory = None


def _last_segment(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _wrapped_command(line: Sequence[str], browser: Mapping[str, Any]) -> list[str]:
    """The words of the command ``line`` runs once its wrappers (``timeout 30``, ``nice -n 5``, ``env``) are peeled.

    A wrapper's options, the values of its valued options and its leading operands (``timeout``'s duration) are
    skipped by the shape ``browser["wrappers"]`` gives it; the shell keywords and ``VAR=value`` words are skipped
    too. A wrapper is known by its last path segment (``/usr/bin/env``).
    """
    words = list(line)
    while words:
        name = _last_segment(words[0])
        if name in browser["keywords"] or _ASSIGNMENT_RE.match(words[0]):
            words = words[1:]
            continue
        shape = browser["wrappers"].get(name)
        if shape is None:
            break
        rest = words[1:]
        index = 0
        while index < len(rest) and rest[index].startswith("-") and len(rest[index]) > 1:
            if rest[index] == "--":
                index += 1
                break
            index += 2 if rest[index] in shape.get("valued_options", ()) else 1
        index += shape.get("operands", 0)
        words = rest[index:]
    return words


def _script_path(script: str, directory: str | None) -> str:
    """``script`` normalized (``a/./b``, ``a/../b``) and, when relative and ``directory`` is known, joined to it."""
    if script.startswith("/") or directory is None:
        return posixpath.normpath(script)
    return posixpath.normpath(f"{directory}/{script}")


def _runs_script(arguments: Sequence[str], directory: str | None, browser: Mapping[str, Any]) -> bool:
    """Whether an interpreter given ``arguments`` runs the tool's script: its first non-option argument is it.

    The values of the valued options (``--import x``) are skipped; ``-e``/``-c``/``-m`` mean inline code or a
    module, so no script follows. The path is normalized and, when relative, resolved against ``directory`` (where
    the command runs), so ``./js/tools/browser.mjs``, ``js/tools/./browser.mjs`` and ``browser.mjs`` run from
    ``js/tools`` all name the script.
    """
    index = 0
    while index < len(arguments):
        word = arguments[index]
        if word in browser["interpreter_inline_options"]:
            return False
        if word in browser["interpreter_valued_options"]:
            index += 2
        elif (word.startswith("-") and len(word) > 1) or word in browser["interpreter_subcommands"]:
            index += 1
        else:
            break
    if index >= len(arguments):
        return False
    script = _script_path(arguments[index], directory)
    return any(script == name or script.endswith("/" + name) for name in browser["scripts"])


def _shell_runs_browser_tool(line: _CommandLine, home: str | None, browser: Mapping[str, Any]) -> bool:
    """Whether the ``-c`` string of the shell command ``line`` runs the browser tool."""
    operands = [_Word(value=word, expands=False, substitutions=(), operand=True) for word in line.words[1:]]
    text = _shell_script(operands)
    if text is None:
        return False
    lines: list[_CommandLine] = []
    _command_lines(_Parser(text).script(nested=False), line.directory, home, lines)
    return any(_runs_browser_tool(nested, home, browser) for nested in lines)


def _verb_follows(words: Sequence[str], position: int, browser: Mapping[str, Any]) -> bool:
    """Whether ``tool browser`` is the next words from ``position``, past any ``--`` separating it from the entry."""
    while position < len(words) and words[position] == "--":
        position += 1
    verb = browser["verb"]
    return list(words[position : position + len(verb)]) == verb


def _runs_entry(words: Sequence[str], index: int, browser: Mapping[str, Any]) -> bool:
    """Whether ``words[index]`` is akmon's entry (``akmon``, ``cli.mjs`` or ``-m akmon[.x]``) followed by the verb."""
    name = _last_segment(words[index])
    if name in browser["entries"]:
        return _verb_follows(words, index + 1, browser)
    if words[index] == browser["module_option"] and index + 1 < len(words):
        module = words[index + 1]
        if any(module == entry or module.startswith(entry + ".") for entry in browser["entries"]):
            return _verb_follows(words, index + 2, browser)
    return False


def _runs_browser_tool(line: _CommandLine, home: str | None, browser: Mapping[str, Any]) -> bool:
    """Whether the command ``line`` runs the browser tool: ``akmon tool browser`` or the tool's script.

    The wrappers are peeled first (:func:`_wrapped_command`). A launcher (``npx``, ``uv``, ``akmon``, ...) or an
    interpreter (``node``, ``python3``, ``bun``, ...) runs what its arguments name, so ``tool browser`` after an
    ``akmon`` / ``cli.mjs`` / ``-m akmon`` word anywhere in them (a ``--`` may sit between), or the tool's script as
    an interpreter's first non-option argument, runs the tool. A shell's ``-c`` string behind a wrapper is read as a
    script of its own. Any other program (``echo``, ``grep``, ``oxfmt``) takes the words as text.
    """
    words = _wrapped_command(line.words, browser)
    program = _last_segment(words[0]) if words else ""
    interpreter = re.compile(browser["interpreter_pattern"])
    if program in _SHELLS:
        return _shell_runs_browser_tool(_CommandLine(words, line.directory), home, browser)
    if program not in browser["launchers"] and interpreter.fullmatch(program) is None:
        return False
    for index, word in enumerate(words):
        if _runs_entry(words, index, browser):
            return True
        if interpreter.fullmatch(_last_segment(word)) is not None and _runs_script(
            words[index + 1 :], line.directory, browser
        ):
            return True
    return False


def browser_command_drives(command: str, directory: str | None = None) -> bool:
    """Whether a shell command's command words run the browser tool (``akmon tool browser`` and its spellings).

    Only command words count -- a quoted argument (``echo "akmon tool browser"``) and a heredoc body are text; a
    word is read with its quotes removed, so ``akmon tool 'brow'ser`` is the tool. The command is read as
    :func:`git_invocations` reads it: ``;``, ``&&``, pipes, ``$(...)``, ``bash -c`` and ``eval`` are followed.
    A command is read past its wrappers (``timeout``, ``nice``, ``xargs``, ``env``, ...), and what it runs is the
    tool when ``tool browser`` follows an ``akmon`` word anywhere in a launcher's arguments (``npx -y -p akmon
    akmon tool browser``, ``npx akmon -- tool browser``, ``uv run --frozen akmon tool browser``, ``python -m
    akmon.cli tool browser``), or when the tool's ``js/tools/browser.mjs`` / ``tools/browser.py`` script is the
    first non-option argument of an interpreter -- as the path reads once normalized and, when relative, joined
    to ``directory`` (where the command starts; a ``cd`` before it moves it), so ``cd js/tools && node
    browser.mjs`` is the tool. A path named to another program -- ``oxfmt``, ``grep``, ``node --test`` of a test
    file -- runs nothing. All of it is the ``browser`` table of ``hook_core.json``. A deliberate evasion through
    another interpreter's inline code (``echo ... | bash``, ``node -e``) is not read: the skill forbids it.
    """
    browser = _hook_core_data()["browser"]
    home = _home_directory()
    lines: list[_CommandLine] = []
    # An unknown start is the current directory: a relative ``cd`` after it still names a place.
    _command_lines(_Parser(command).script(nested=False), directory or ".", home, lines)
    return any(_runs_browser_tool(line, home, browser) for line in lines)


def _attach_active(directory: str | None) -> bool:
    """Whether the project at ``directory`` has an active attach: ``<dev root>/.local/.browser/attach.json`` exists.

    A project the hook cannot resolve (no project root, an unreadable ``.aitna-root``) has none: the check is
    skipped rather than guessed.
    """
    try:
        root = locate_project_root(Path(directory) if directory else None)
        if root is None:
            return False
        return local_root(root).joinpath(*_hook_core_data()["browser"]["attach_file"]).is_file()
    except (OSError, ValueError):
        return False


def browser_guard_result(tool_name: str, command: str = "", **facts: Unpack[BrowserFacts]) -> HookResult | None:
    """Guard the browser class of the access matrix: who may drive the shared browser (ADR 0032/D07).

    A call drives the browser when it is a ``Bash`` call whose command words run the tool
    (:func:`browser_command_drives`) or an MCP call of the ``akmon-browser`` server (``tool_name`` starts with
    the ``browser.mcp_prefix`` of ``hook_core.json``). The matrix row is ``browser_delegated`` for a delegated
    agent (``delegated``: the payload carried ``agent_id``) and ``browser_session`` otherwise; the actor picks the
    column. A ``developer``'s own session passes, a delegated agent and every ``autonomous`` call are denied, and
    an ``ask`` nobody attends becomes a ``deny``. While the project has an active attach (:func:`_attach_active`
    at ``directory``) a ``close`` tool of the server is denied to every actor, a developer's own session
    included: an attached browser is the user's Chrome, and the agent never closes its window or its page. Any
    other call is not this guard's.

    Runtime classification: operational
    Rationale: the rule is the browser class of the access matrix (ADR 0032/D07) and its text lives in the
    ``akmon-browser`` skill, not in guardrail prose, so no ``Runtime check`` marker can claim a policy ID for it;
    ADR-0012/D07 requires the classification to be stated rather than left silent.
    """
    texts = _hook_core_data()
    browser = texts["browser"]
    is_mcp = tool_name.startswith(browser["mcp_prefix"])
    if not is_mcp and not (tool_name == "Bash" and browser_command_drives(command, facts.get("directory"))):
        return None
    access = _Access(facts.get("actor", access_matrix.Actor.DEVELOPER))
    action_class = (
        access_matrix.BROWSER_DELEGATED_CLASS if facts.get("delegated") else access_matrix.BROWSER_SESSION_CLASS
    )
    result = access.result(action_class, {})
    if result is not None:
        result = _escalate_unattended_ask(result, facts.get("permission_mode"), attended=facts.get("attended"))
    closes = is_mcp and browser["mcp_close_word"] in tool_name[len(browser["mcp_prefix"]) :].lower()
    if closes and _attach_active(facts.get("directory")):
        attached = HookResult(
            event_name="PreToolUse",
            permission_decision="deny",
            permission_reason=texts["browser_attached_close_reason"],
        )
        return strictest_result([result, attached])
    return result


# The reason a crashed commit guard gives an autonomous run when ``hook_core.json`` cannot be read either: the
# crash path depends on no data file, since a missing or broken one may be the very failure it answers.
_GUARD_CRASH_FALLBACK_REASON = (
    "Commit guardrail (autonomous run): the access matrix could not be read, so an autonomous run is denied."
)


def guard_crash_deny_document() -> str:
    """The one-line JSON ``PreToolUse`` deny a crashed commit guard answers an ``autonomous`` run with.

    ADR-0031/D07 (D-C203-GUARD-CRASH): when the guard cannot read the access matrix, or raises while
    evaluating a command, an autonomous run is denied where a developer run is let through (the crash-open
    posture of ADR 0013). The actor is read from the environment before the matrix is, so this answer depends
    on neither the matrix nor, if the texts cannot be read, on any data file: it names its keys literally and
    falls back to a reason in code. Both vendor adapters write this document.

    Runtime classification: operational
    Rationale: it is the crash posture of the commit guard (``commits.owner-owned``), not a rule of its own:
    it answers a failure with the deny the guard's autonomous row would otherwise give, and an adapter writes
    it into the vendor's channel from outside the ``*_result`` join, so ADR-0012/D07 requires the
    classification to be stated rather than left silent.
    """
    try:
        reason = _hook_core_data()["git_commit_guard_crash_reason"]
    except Exception:  # noqa: BLE001 — the answer to a failure must not fail: the reason in code stands in
        reason = _GUARD_CRASH_FALLBACK_REASON
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def _ai_trailer_floor(actor: access_matrix.Actor) -> HookResult:
    """The deny for an AI trailer: unconditional, read from no matrix (commits.owner-owned).

    :func:`access_matrix.read_data` already refuses a matrix whose ``ai_trailer`` cells are not ``deny``;
    the floor does not depend on them. The reason is the actor's text for the class, as the matrix path gives.
    """
    texts = _hook_core_data()
    template = texts[texts["access_reasons"][access_matrix.Actor(actor).value][access_matrix.AI_TRAILER_CLASS]]
    return HookResult(
        event_name="PreToolUse", permission_decision="deny", permission_reason=jsondata.fill(template, {})
    )


def agent_names(directory: Path, known: Mapping[str, Sequence[str]] | None = None) -> list[str]:
    """The agent charters (subdirectories with a ``README.md``) under ``directory``, in roster order.

    ``known`` is :func:`agent_definitions`, whose key order is the delivery chain's (ADR 0026/D08):
    the shipped agents with a charter come first, in that order, then the rest sorted by name. A
    charter directory named for a role of a shipped agent that has a charter of its own is the legacy
    layout of that agent (ADR 0026/D06), and is left out so that one agent is not listed twice; with
    no such charter it is listed as any other.
    """
    if not directory.is_dir():
        return []
    known = known or {}
    found = {
        item.name
        for item in directory.iterdir()
        if item.is_dir() and not item.name.startswith(".") and (item / "README.md").is_file()
    }
    shipped = [agent for agent in known if agent in found]
    legacy = {role for agent in shipped for role in known[agent]} - set(known)
    return shipped + sorted(found - set(shipped) - legacy)


# A role a charter names: a reference to the standard's ``roles/<role>.md``.
_CHARTER_ROLE_RE = re.compile(r"roles/([a-z][a-z0-9_-]*)\.md")


def agent_definitions() -> dict[str, list[str]]:
    """The roles of each agent akmon ships, by agent (``agents/agents.json`` of this tree).

    The one owner of the agent -> roles table: ``akmon init`` writes each charter's sections from the
    same file (ADR 0026/D06).
    """
    document = jsondata.read(_TREE_ROOT / "agents" / "agents.json")
    return {agent: list(spec["roles"]) for agent, spec in document.items()}


def agent_roles(directory: Path, agent: str, known: Mapping[str, Sequence[str]]) -> list[str]:
    """The roles of ``agent``: its definition's when ``known`` names it, else the charter's own.

    ``known`` is :func:`agent_definitions` (ADR 0026/D06). An agent it does not name — a project's
    own, or a pre-0027 role-named charter directory — falls back: the charter
    (``directory/<agent>/README.md``) names each role it works in by a reference to
    ``roles/<role>.md`` (ADR 0027/D04), and a charter that names none belongs to an agent whose charter
    directory is its role name (``learn``), so the agent's own name is its one role.
    """
    if agent in known:
        return list(known[agent])
    try:
        text = (directory / agent / "README.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [agent]
    return list(dict.fromkeys(_CHARTER_ROLE_RE.findall(text))) or [agent]


def agent_roster(directory: Path, agents: list[str], start: dict[str, str], known: Mapping[str, Sequence[str]]) -> str:
    """The agents of ``directory`` each with its roles, as the session-start roster line names them.

    ``known`` is :func:`agent_definitions`: the shipped agents' roles come from it, and only the
    development layer passes it — a project's runtime agents keep their charters' own roles.
    """
    entries = []
    for agent in agents:
        roles = agent_roles(directory, agent, known)
        template = start["agent_one_role"] if len(roles) == 1 else start["agent_many_roles"]
        entries.append(jsondata.fill(template, {"agent": agent, "roles": ", ".join(roles)}))
    return start["agent_separator"].join(entries)


def stale_guardrail_notice(root: Path) -> str | None:
    """One owner-addressed line when the materialized guardrails are behind the running tree.

    The interactive half of the freshness guarantee (C77). ``sync --check`` and ``verify``
    already catch this copy in CI, but they run on a commit; the window this closes opens
    earlier and closes silently. A pin bump installs the new hooks the instant the dependency
    resolves — they run from the package — while ``<dev root>/.akmon/`` still
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
        {"root_name": aitna_root_name(root), "names": ", ".join(names)},
    )


def _work_style_line(root: Path, session_id: str | None, start: Mapping[str, str]) -> str:
    """The one SessionStart line naming the work style in force and where it came from (ADR 0031/D03)."""
    data = work_style.read_data()
    found = work_style.resolve(root, session_id, data)
    source = jsondata.fill(
        start["work_style_sources"][found.source],
        {"root_name": aitna_root_name(root), "developer_file": data["developer_rel"]},
    )
    return jsondata.fill(start["work_style_line"], {"style": found.style, "source": source})


def session_start_result(root: Path, session_id: str | None = None) -> HookResult | None:
    """SessionStart guardrail: active-agent declaration reminder, plus a stale-materialization notice.

    One line states the work style in force for ``session_id`` and the level that set it (ADR 0031/D03);
    when the work-style data cannot be read or has the wrong shape, that line alone is left out.

    Runtime classification: operational
    Rationale: it authors no rule. It aggregates the agent roster and re-delivers rules owned
    elsewhere — role declaration, the memory-read rule, delegation-by-default — at session start,
    and on Codex it is the only delivery channel for the delegation rule, because ``@``-imports are
    not expanded there (C39). Delivery is not ownership, so the classification stands; without that
    second fact "operational" would read as "incidental", which it is not.
    """
    stale = stale_guardrail_notice(root)
    dev = agent_names(aitna_root(root) / "agents", agent_definitions())
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
        lines.append(
            jsondata.fill(
                start["develop_line"],
                {"agents": agent_roster(aitna_root(root) / "agents", dev, start, agent_definitions())},
            )
        )
    if desk:
        lines.append(jsondata.fill(start["operate_line"], {"agents": agent_roster(root / "agents", desk, start, {})}))
    lines.append(start["no_agent_line"])
    if dev:
        # The DEVELOP routing discriminator (ADR 0003 §4): give the picking rule up front, not
        # only after a code/planning edit already happened. Keyed by cognitive operation.
        lines.append(start["pick_by_operation"])
    else:
        lines.append(start["pick_generic"])
    lines.append(start["delegation_line"])
    # The line is advisory: a work-style file that is missing, not JSON or the wrong shape loses the line,
    # never the rest of the session's context.
    with contextlib.suppress(jsondata.DataFileError, KeyError, TypeError):
        lines.append(_work_style_line(root, session_id, start))
    lines.append(jsondata.fill(start["memory_line"], {"root_name": aitna_root_name(root)}))
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
    if any(segment in target for segment in _non_code_segments(root)):
        return False
    return Path(target).suffix in _code_extensions()


def role_on_code_message(root: Path | None = None) -> str:
    """Owner-facing text for the role-on-code reminder (hooks/hook_core.json, C102)."""
    tasks = f"{aitna_root_name(root if root is not None else locate_project_root())}/TASKS.md"
    return jsondata.fill(_hook_core_data()["role_on_code_message"], {"tasks": tasks})


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

    return HookResult(event_name="PreToolUse", additional_context=role_on_code_message(project_root))


def is_planning_doc(file_path: str, root: Path | None = None) -> bool:
    """Whether ``file_path`` is a backlog/design/ADR/requirements/process planning doc."""
    target = classify_target(file_path, root)
    if target.endswith(_planning_doc_files(root)):
        return True
    if not target.endswith(".md"):
        return False
    return any(segment in target for segment in _planning_doc_segments(root))


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
# - **A read never carries the ask.** In an unattended run the ask is a deny, and
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
    score: float, tool_name: str, ask_marker: Path, *, permission_mode: str | None, attended: bool | None
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
        attended=attended,
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
    attended: bool | None = None,
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
        return _delegation_ask_result(score, tool_name, ask_marker, permission_mode=permission_mode, attended=attended)
    if score >= delegation_nudge_threshold():
        return _delegation_soft_nudge_result(score, marker)
    return None
