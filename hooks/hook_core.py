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
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

from common import jsondata  # noqa: E402
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


# --------------------------------------------------------------------------------------
# The commit guard: which repository a command acts on (C190, ADR-0029/D09)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GitInvocation:
    """One ``git`` command found in a shell command: its subcommand, its arguments, and where it runs.

    ``arguments`` are the words after the subcommand, quotes removed. ``directory`` is ``None`` when
    the place cannot be told from the text (a ``$`` expansion, a ``GIT_DIR`` assignment,
    ``--git-dir``, ``cd -``).
    """

    subcommand: str
    directory: str | None
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepositoryFacts:
    """What the guard needs of the repository at a directory: a linked worktree or not, and its branch.

    ``branch`` is ``""`` on a detached ``HEAD``.
    """

    linked: bool
    branch: str


@dataclass(frozen=True)
class _Word:
    """A shell word after quote removal. ``operand`` is ``False`` for the target of a redirection."""

    value: str
    expands: bool
    substitutions: tuple[list[Any], ...]
    operand: bool


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
_WRITE_OPERANDS = 2  # `symbolic-ref <name> <ref>` writes; one operand reads
_LAYOUT_PATHS = 2  # `rev-parse --git-dir --git-common-dir` prints one path per line


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
                )
            )
            self._redirect_target_next = False
        frame.builder = _WordBuilder()

    def _end_command(self, frame: _Frame) -> None:
        self._end_word(frame)
        self._redirect_target_next = False
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
            self._pos += 1
            while self._pos < len(text) and text[self._pos] in "&>|<":
                self._pos += 1
            self._redirect_target_next = True

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
    index = 0
    while index < len(operands):
        value = operands[index].value
        if value == "-C":
            index += 1
            if index < len(operands):
                directory = _target_directory(operands[index], directory, home)
        elif value in ("-c", "--namespace"):
            index += 1
        elif value in ("--git-dir", "--work-tree"):
            index += 1
            unknown = True
        elif value.startswith(("--git-dir=", "--work-tree=")):
            unknown = True
        elif not value.startswith("-"):
            arguments = tuple(word.value for word in operands[index + 1 :])
            return GitInvocation(value, None if unknown else directory, arguments)
        index += 1
    return None


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
        if invocation is not None:
            found.append(invocation)
    else:
        script = _nested_script(name, operands)
        if script is not None:
            _walk_script(_Parser(script).script(nested=False), directory, home, found)
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
    """Every ``git`` command a shell command runs, in order, with the directory each runs in.

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


def _ask(reason: str) -> HookResult:
    return HookResult(event_name="PreToolUse", permission_decision="ask", permission_reason=reason)


def _owners_place(directory: str | None, repository_at: Callable[[str], RepositoryFacts | None]) -> str | None:
    """Why ``directory`` is not an agent's place to write history, in words; ``None`` when it is.

    An agent writes history only in a linked worktree, on a named branch that is not a default one.
    """
    data = _hook_core_data()
    if directory is None:
        return data["git_commit_where_unresolved"]
    facts = repository_at(directory)
    if facts is None:
        return jsondata.fill(data["git_commit_where_not_repository"], {"directory": directory})
    if not facts.linked:
        return jsondata.fill(data["git_commit_where_checkout"], {"directory": directory})
    if not facts.branch:
        return jsondata.fill(data["git_commit_where_detached"], {"directory": directory})
    if facts.branch in data["git_default_branches"]:
        return jsondata.fill(data["git_commit_where_default_branch"], {"directory": directory, "branch": facts.branch})
    return None


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


def _invocation_ask(
    invocation: GitInvocation, repository_at: Callable[[str], RepositoryFacts | None]
) -> HookResult | None:
    data = _hook_core_data()
    if invocation.subcommand in data["git_publishing_subcommands"]:
        return _ask(data["git_commit_push_tag_merge_reason"])
    if invocation.subcommand in data["git_history_subcommands"]:
        place = _owners_place(invocation.directory, repository_at)
        if place is not None:
            return _ask(
                jsondata.fill(data["git_commit_history_reason"], {"subcommand": invocation.subcommand, "where": place})
            )
    target = _ref_target(invocation, data, repository_at)
    if target is None:
        return None
    subcommand = _ref_subcommand(invocation)
    return _ask(jsondata.fill(data["git_commit_ref_reason"], {"subcommand": subcommand, "target": target}))


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


def git_commit_guard_result(
    command: str,
    *,
    permission_mode: str | None = None,
    attended: bool | None = None,
    directory: str | None = None,
    repository_at: Callable[[str], RepositoryFacts | None] | None = None,
) -> HookResult | None:
    """Guard ``git`` commands: no AI co-author trailer, publishing and history are the owner's.

    The trailer is denied wherever it stands in the text, a heredoc body included. Only command
    words are read for the rest (:func:`git_invocations`): ``push`` and ``tag`` ask everywhere; a
    history-writing subcommand (``commit``, ``merge``, ``rebase``, ``reset`` and the others in
    ``hook_core.json``) passes when the repository it acts on — not the session's — is a linked
    worktree on a named branch that is not ``main``/``master``, and asks otherwise. The first
    invocation that does not pass decides.

    ``directory`` is where the command starts (default: the process's); ``repository_at`` answers
    :class:`RepositoryFacts` for a directory (default: :func:`repository_facts`, which asks git).

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

    lookup = repository_facts if repository_at is None else repository_at
    start = _working_directory() if directory is None else directory
    for invocation in git_invocations(command, start, home_directory=_home_directory()):
        ask = _invocation_ask(invocation, lookup)
        if ask is not None:
            return _escalate_unattended_ask(ask, permission_mode, attended=attended)
    return None


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
