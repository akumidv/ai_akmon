#!/usr/bin/env python3
"""The park helper: hold, write, resume, digest and list the ergons of parked work.

An *ergon* is the folder ``<dev root>/.ergon/<id>-<name>/`` of one piece of work. Its plan is
``PLAN.md``; its units are the plan itself (the ergon root) and its athlos, each in the folder of
its own number, ``<dev root>/.ergon/<id>-<name>/<n>/ATHLOS.md`` (ADR 0029 D11).
Parking a unit writes two files into it, atomically: ``PARK.md``, the park note — a small
machine-readable header between two ``---`` lines and a Markdown body of facts — and
``RESUME.md``, the harness-neutral prompt a successor starts from. There is no local index
anymore: an ergon is its own record, and ``park list`` is the index (ADR 0028 D12).

A record written before the rename of ADR 0029 is read and translated: the ``job`` word, the
``jobs/<n>-<label>/JOB.md`` layout, the ``job:`` key of a note and the retired local index. An old
form is never written (ADR 0029 D12).

    akmon tool park/park write C186 --name holders-units --goal "…" --next "…" [--commit-message "…"]
    akmon tool park/park hold C186 --number 1 --harness claude --session-id abc
    akmon tool park/park athlos C186 --number 1 --step "…"
    akmon tool park/park unpark C186        # takes the lease, prints RESUME.md and the digest
    akmon tool park/park digest C186 [--cap N]
    akmon tool park/park list [--plan ID] [--task ID] [--state S] [--closed]
    akmon tool park/park active             # the unit this session is in, read from the disk
    akmon tool park/park worktrees [BRANCH|ATHLOS]  # every worktree and backup branch by state; one: is it carried
    akmon tool park/park close C186         # moves the ergon to the closed folder
    akmon tool park/park local-id           # the next free local id, _T<n>
    akmon tool park/park export C186 --out bundle.md

The header has ONE source, the frozen ``ParkFields`` the command line fills: it is rendered from
that type and parsed back into it, and no other declaration of its keys exists. Its format is a
fixed, flat one so any language reads it without a YAML library:

    ---
    key: value          a scalar; an empty value is written ``key:`` with nothing after the colon
    key:                a list key, then one ``  - item`` line (two spaces) per item
      - item
    ---

The state of a unit is derived, never typed (ADR 0028 D09): a live lease makes it *active*, a
note without a lease makes it *parked*, neither makes it *not started*, and an athlos whose
``ATHLOS.md`` says ``done`` is *done*. The branch and the revisions of a note are read from git
when the note is written, and the note records when it was written.

In the ``controlling`` work style, in the main checkout, ``write`` also prints the block commit as two
commands and a reminder (ADR 0031 D04, D05); it never runs them and writes nothing of them into a record.

The helper writes no date into a tracked document, never reads a transcript and never pushes.
Stdlib-only, and nothing happens at import time: tools run before a virtual environment exists.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import errno
import os
import posixpath
import re
import shlex
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The tree root, so the shared ``common`` package resolves from the mounted tree and from a
# materialized copy alike (the way ``tasks/archive.py`` reaches it).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common import jsondata, work_style
from common.project_root import ergon_root, git_common_root, local_root, resolve_project_root

_SECONDS_PER_DAY = 86400
_SECONDS_PER_HOUR = 3600
_PARK_FILE = "PARK.md"
_RESUME_FILE = "RESUME.md"
_PLAN_FILE = "PLAN.md"
_HOLDER_FILE = "HOLDER"
_ATHLOS_FILE = "ATHLOS.md"
_SESSIONS_FILE = "SESSIONS"
_HEADER_FENCE = "---"
_ID_RE = re.compile(r"^(?:[A-Z]\d+|_T\d+)$")  # ADR 0002 typed id, and a local id's _T<n> (ADR 0028 D12)
_ATHLOS_ID_RE = re.compile(r"^((?:[A-Z]\d+|_T\d+))\.(\d+)$")
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ERGON_RE = re.compile(r"^((?:[A-Z]\d+|_T\d+))-([a-z0-9]+(?:-[a-z0-9]+)*)$")
_KEY_RE = re.compile(r"^([a-z_]+):(?: (.*))?$")
_PURPOSE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_LOCAL_ID_RE = re.compile(r"^_T(\d+)$")
_LEGACY_INDEX_FILE = "TASKS.md"  # the retired local index, in ``<dev root>/.local/``
_LEGACY_ROW_RE = re.compile(r"^- _T([0-9]+)(?:[ \t]|$)")  # one of its rows: ``- _T6 · ...``
_LEGACY_ATHLOS_DIR = "jobs"  # the folder of an ergon's athlos before ADR 0029 D11
_LEGACY_ATHLOS_FILE = "JOB.md"  # an athlos's own file before ADR 0029 D11
_GIT_TIMEOUT_SECONDS = 10
_GIT_REVISIONS = 5
_STEPS_HEADING = "## Steps"
_DONE_MARKER = "done"
_STEP_UNDONE = "- [ ] "
_STEP_DONE = "- [x] "
_CLOSED_DIR = ".closed"
_WORKTREES_DIR = ".worktrees"
_TASK_SEPARATOR = "·"
_FIELD_SEPARATOR = ","
_PATH_SEPARATOR = "/"
_ATHLOS_HEADING = "Athlos"
_LEGACY_ATHLOS_HEADING = "Jobs"  # the plan's section heading before ADR 0029 D02
_ATHLOS_SOURCE_PARTS = 3  # ergon folder, athlos folder, ``ATHLOS.md``
_LINE_BREAKS_RE = re.compile(r"[\r\n]+")


class ParkError(Exception):
    """A failure the command line reports as one line on stderr with exit 1."""


@dataclass(frozen=True)
class SessionRef:
    """Where the work was done: a reference for provenance, never a requirement (ADR 0028 D03)."""

    harness: str
    session_id: str
    machine: str


@dataclass(frozen=True)
class Holder:
    """The holder of a lease: who holds a unit, and where (ADR 0028 D09)."""

    harness: str
    session_id: str
    machine: str
    worktree: str

    @property
    def identified(self) -> bool:
        """Whether the holder names a session: a harness and a session id, the pair a note can carry."""
        return bool(self.harness and self.session_id)

    def same_as(self, other: Holder) -> bool:
        """Whether the two holders are the same session on the same machine.

        An anonymous holder, one that names no harness or no session, is the same as nobody: two
        of them cannot be told apart, so neither is taken for the other (ADR 0028 D09).
        """
        if not (self.identified and other.identified):
            return False
        return (self.harness, self.session_id, self.machine) == (other.harness, other.session_id, other.machine)

    def label(self) -> str:
        """The holder as one line of text: harness, session, machine and worktree."""
        parts = [self.harness or "?", self.session_id or "?", self.machine or "?"]
        if self.worktree:
            parts.append(self.worktree)
        return " ".join(parts)


@dataclass(frozen=True)
class Lease:
    """The lease file ``HOLDER`` of a unit: its holder and the time of its last write."""

    holder: Holder
    written: float

    def age_seconds(self, now: float) -> float:
        """How long ago the lease was last written."""
        return max(0.0, now - self.written)


@dataclass(frozen=True)
class LeaseContext:
    """What a lease is judged against: the clock, the stale threshold and this machine."""

    now: float
    stale_hours: int
    machine: str


@dataclass(frozen=True)
class ParkFields:
    """The header of a park note: the one source of its keys, rendered and parsed from here."""

    id: str
    name: str
    next_action: str
    plan: str = ""
    athlos: str = ""
    row: str = ""
    branch: str = ""
    revisions: tuple[str, ...] = ()
    owned_paths: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    sessions: tuple[SessionRef, ...] = ()
    origin: str = ""
    readiness: str = ""
    written: str = ""


@dataclass(frozen=True)
class ParkBody:
    """The facts under the header. ``purpose`` is empty until a brief kind fills it (branch B8)."""

    goal: str
    decisions: tuple[str, ...] = ()
    answers: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()
    purpose: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AthlosLine:
    """One athlos line of ``PLAN.md``: the structure of an athlos, never its state (ADR 0028 D08).

    The line carries the zone beside the tasks (ADR 0029 D03): the pair (task id, zone) is the
    athlos's content, its id is its place in the plan.
    """

    id: str
    number: int
    label: str
    tasks: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    harness: str = ""
    result: str = ""
    zone: str = ""


@dataclass(frozen=True)
class PlanHeader:
    """The header of ``PLAN.md``: the ergon's id, name, title and the tasks it carries."""

    id: str = ""
    name: str = ""
    title: str = ""
    tasks: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    """A plan: its header and its athlos lines."""

    header: PlanHeader = PlanHeader()
    athlos: tuple[AthlosLine, ...] = ()


@dataclass(frozen=True)
class AthlosDoc:
    """An athlos's own file ``ATHLOS.md``: its steps with their done marks, and whether it is done."""

    header: ParkFields
    steps: tuple[tuple[str, bool], ...] = ()
    done: bool = False

    def next_step(self) -> str:
        """The first step that is not done, or the empty string when every step is done."""
        for text, is_done in self.steps:
            if not is_done:
                return text
        return ""


@dataclass(frozen=True)
class ErgonSummary:
    """One line of ``list``: what an ergon says of itself, read from its folder."""

    id: str
    name: str
    state: str
    plan: str
    next_action: str
    decisions: int
    branch: str
    age_days: int | None
    unreadable: str = ""  # why the ergon's files could not be read; the other fields are then empty


@dataclass(frozen=True)
class AthlosSummary:
    """One athlos line of ``list``: what an athlos says of itself, read from its folder."""

    id: str
    name: str
    state: str
    tasks: tuple[str, ...]
    next_action: str
    branch: str
    age_days: int | None


@dataclass(frozen=True)
class ListQuery:
    """The filters of ``list``; an empty one matches every ergon."""

    plan: str = ""
    task: str = ""
    state: str = ""
    closed: bool = False


# Header keys in their written order, and which of them hold a list: the one table the renderer and
# the parser share. ``next_action`` is written as ``next``.
_SCALAR_KEYS = ("id", "name", "plan", "athlos", "row", "branch", "next", "origin", "readiness", "written")
_LIST_KEYS = ("revisions", "owned_paths", "tasks", "sessions")
_HEADER_ORDER = (
    "id",
    "name",
    "plan",
    "athlos",
    "row",
    "branch",
    "revisions",
    "owned_paths",
    "tasks",
    "next",
    "sessions",
    "origin",
    "readiness",
    "written",
)
# The keys of a note written before ADR 0028 D09: read and ignored, never written again.
_LEGACY_KEYS = ("state", "peers")
# A key renamed by ADR 0029 D02, as ``(old, new)``: read and translated, never written again.
_RENAMED_KEYS = (("job", "athlos"),)
# The keys of the lease file ``HOLDER``, in their written order.
_LEASE_KEYS = ("harness", "session", "machine", "worktree", "written")


@dataclass(frozen=True)
class HeaderSpec:
    """The keys of one flat header: their order, which hold a list, which are read and ignored.

    ``renamed`` carries ``(old, new)`` pairs of a key that ADR 0029 renamed: the old spelling is read
    under the new key, so a note written before the release still parses (ADR 0029 D12).
    """

    order: tuple[str, ...]
    list_keys: tuple[str, ...] = ()
    legacy: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()

    def key_of(self, key: str) -> str:
        """The key ``key`` is read under: itself, or the new spelling of a renamed one."""
        for old, new in self.renamed:
            if old == key:
                return new
        return key


# The header of a park note and the header of a lease: the two flat formats the helper reads.
NOTE_HEADER = HeaderSpec(order=_HEADER_ORDER, list_keys=_LIST_KEYS, legacy=_LEGACY_KEYS, renamed=_RENAMED_KEYS)
LEASE_HEADER = HeaderSpec(order=_LEASE_KEYS)


def _texts() -> dict:
    """The tool's texts (``park.json``), read on the call that needs them."""
    return jsondata.read(Path(__file__).parent / "park.json")


def _error(texts: Mapping, code: str, **values: object) -> ParkError:
    """A ``ParkError`` from the stored message ``errors.<code>``, with its placeholders filled."""
    return ParkError(jsondata.fill(texts["errors"][code], {name: str(value) for name, value in values.items()}))


def _states(texts: Mapping) -> Mapping[str, str]:
    """The four derived states, by their short names."""
    return texts["states"]


def _display_path(path: Path, root: Path) -> str:
    """``path`` as the helper prints it: from ``root`` when it lies inside, as it is when it does not.

    The ergons of a linked worktree live in the main checkout (ADR 0028 D12), outside the session's
    root, so a path there is printed absolute rather than refused.
    """
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


# --------------------------------------------------------------------------------------
# validation: at the boundary, so the renderer and every reader can trust the types
# --------------------------------------------------------------------------------------


def _check_line(value: str, label: str, texts: Mapping) -> None:
    """A scalar holds one line with no surrounding whitespace, so it survives a round trip."""
    if "\n" in value or "\r" in value or value != value.strip():
        raise _error(texts, "bad_line", label=label)


def _check_id(value: str, label: str, texts: Mapping) -> None:
    if not _ID_RE.match(value):
        raise _error(texts, "bad_id", label=label, value=value)


def _check_athlos_id(value: str, label: str, texts: Mapping) -> None:
    if not _ATHLOS_ID_RE.match(value):
        raise _error(texts, "bad_athlos_id", label=label, value=value)


def _check_items(items: Sequence[str], label: str, texts: Mapping) -> None:
    for item in items:
        if not item:
            raise _error(texts, "empty", label=label)
        _check_line(item, label, texts)


def check_fields(fields: ParkFields, texts: Mapping) -> None:
    """Refuse a header that would not render or parse back: a bad id or name, a multi-line scalar.

    Raises:
        ParkError: a field breaks the header's contract; the message names the field.
    """
    _check_id(fields.id, "id", texts)
    if not _NAME_RE.match(fields.name):
        raise _error(texts, "bad_name", value=fields.name)
    for label, value in (("plan", fields.plan), ("row", fields.row)):
        if value:
            _check_id(value, label, texts)
    if fields.athlos:
        _check_athlos_id(fields.athlos, "athlos", texts)
    for label, value in (
        ("branch", fields.branch),
        ("next", fields.next_action),
        ("origin", fields.origin),
        ("readiness", fields.readiness),
        ("written", fields.written),
    ):
        _check_line(value, label, texts)
    if not fields.next_action:
        raise _error(texts, "empty", label="next")
    _check_items(fields.revisions, "revision", texts)
    _check_items(fields.owned_paths, "owned path", texts)
    _check_items(fields.tasks, "task", texts)
    for session in fields.sessions:
        parts = (session.harness, session.session_id, session.machine)
        if any("|" in part for part in parts) or not session.harness:
            raise _error(texts, "bad_session", value="|".join(parts))
        for part in parts:
            _check_line(part, "session", texts)


def check_body(body: ParkBody, texts: Mapping) -> None:
    """Refuse a body whose text would open a section or break an item line.

    Raises:
        ParkError: the goal is empty or unstable under a round trip, or an item spans lines.
    """
    if not body.goal:
        raise _error(texts, "empty", label="goal")
    if body.goal != body.goal.strip():
        raise _error(texts, "bad_text", label="goal")
    if any(line.startswith("## ") for line in body.goal.split("\n")):
        raise _error(texts, "bad_heading", label="goal")
    for label, items in (
        ("decision", body.decisions),
        ("answer", body.answers),
        ("check", body.checks),
        ("unverified", body.unverified),
        ("agent", body.agents),
    ):
        _check_items(items, label, texts)
    for key, value in body.purpose:
        if not _PURPOSE_KEY_RE.match(key):
            raise _error(texts, "bad_key", value=key)
        if not value:
            raise _error(texts, "empty", label=f"purpose {key}")
        _check_line(value, f"purpose {key}", texts)


# --------------------------------------------------------------------------------------
# the park note: header and body, rendered from the types and parsed back into them
# --------------------------------------------------------------------------------------


def _session_text(session: SessionRef) -> str:
    return f"{session.harness}|{session.session_id}|{session.machine}"


def _scalar_line(key: str, value: str) -> str:
    return f"{key}: {value}" if value else f"{key}:"


def render_header(fields: ParkFields) -> str:
    """The header of ``fields``: the fenced ``key: value`` block that opens ``PARK.md``.

    The fields are trusted here; ``check_fields`` is the gate that precedes every caller.
    """
    scalars = {
        "id": fields.id,
        "name": fields.name,
        "plan": fields.plan,
        "athlos": fields.athlos,
        "row": fields.row,
        "branch": fields.branch,
        "next": fields.next_action,
        "origin": fields.origin,
        "readiness": fields.readiness,
        "written": fields.written,
    }
    lists = {
        "revisions": fields.revisions,
        "owned_paths": fields.owned_paths,
        "tasks": fields.tasks,
        "sessions": tuple(_session_text(session) for session in fields.sessions),
    }
    lines = [_HEADER_FENCE]
    for key in _HEADER_ORDER:
        if key in scalars:
            lines.append(_scalar_line(key, scalars[key]))
        else:
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in lists[key])
    lines.append(_HEADER_FENCE)
    return "\n".join(lines) + "\n"


def _split_note(text: str, source: str, texts: Mapping) -> tuple[list[str], str]:
    """The header lines of a note and the text after its closing fence (the body, untouched)."""
    lines = text.split("\n")
    if not lines or lines[0] != _HEADER_FENCE:
        raise _error(texts, "header_missing", path=source)
    for index in range(1, len(lines)):
        if lines[index] == _HEADER_FENCE:
            return lines[1:index], "\n".join(lines[index + 1 :])
    raise _error(texts, "header_missing", path=source)


def _parse_session(text: str, texts: Mapping) -> SessionRef:
    parts = text.split("|")
    if len(parts) != 3:  # noqa: PLR2004 — harness|session_id|machine
        raise _error(texts, "bad_session", value=text)
    return SessionRef(parts[0], parts[1], parts[2])


def _header_values(
    lines: Sequence[str],
    source: str,
    texts: Mapping,
    spec: HeaderSpec = NOTE_HEADER,
) -> dict[str, str | list[str]]:
    """The header lines as ``key -> scalar | list``, each key known and once, each line well-formed."""
    values: dict[str, str | list[str]] = {}
    current: str | None = None
    legacy_list = False
    for number, line in enumerate(lines, start=1):
        if line.startswith("  - "):
            if legacy_list:
                continue
            if current is None or current not in spec.list_keys:
                raise _error(texts, "header_item", path=source, line=number)
            item = values[current]
            assert isinstance(item, list)  # noqa: S101 — a list key was opened by its own line
            item.append(line[4:])
            continue
        match = _KEY_RE.match(line)
        if match is None:
            raise _error(texts, "header_line", path=source, line=number)
        key, value = match.group(1), match.group(2) or ""
        if key in spec.legacy:
            # A retired key is read and ignored; a retired list takes its items with it.
            current = None
            legacy_list = not value
            continue
        legacy_list = False
        # A key the release renamed is read under its new spelling, never written in the old one.
        named = spec.key_of(key)
        if named not in spec.order or named in values:
            raise _error(texts, "header_key", path=source, key=key)
        if named in spec.list_keys:
            if value:
                raise _error(texts, "header_scalar_list", path=source, key=key)
            values[named] = []
            current = named
        else:
            values[named] = value
            current = None
    return values


def parse_header(text: str, source: str, texts: Mapping) -> ParkFields:
    """The ``ParkFields`` a note's header declares; ``source`` names the note in the error.

    Raises:
        ParkError: no header, a malformed or unknown line, or a field that fails ``check_fields``.
    """
    lines, _body = _split_note(text, source, texts)
    values = _header_values(lines, source, texts)
    for key in ("id", "name", "next"):
        if not values.get(key):
            raise _error(texts, "header_required", path=source, key=key)

    def scalar(key: str) -> str:
        value = values.get(key, "")
        assert isinstance(value, str)  # noqa: S101 — scalar keys are stored as str by _header_values
        return value

    def listed(key: str) -> tuple[str, ...]:
        value = values.get(key, [])
        assert isinstance(value, list)  # noqa: S101 — list keys are stored as list by _header_values
        return tuple(value)

    fields = ParkFields(
        id=scalar("id"),
        name=scalar("name"),
        next_action=scalar("next"),
        plan=scalar("plan"),
        athlos=scalar("athlos"),
        row=scalar("row"),
        branch=scalar("branch"),
        revisions=listed("revisions"),
        owned_paths=listed("owned_paths"),
        tasks=listed("tasks"),
        sessions=tuple(_parse_session(item, texts) for item in listed("sessions")),
        origin=scalar("origin"),
        readiness=scalar("readiness"),
        written=scalar("written"),
    )
    try:
        check_fields(fields, texts)
    except ParkError as exc:
        raise _error(texts, "header_invalid", path=source, reason=exc) from exc
    return fields


def _section(heading: str, content: Sequence[str]) -> list[str]:
    return [f"## {heading}", "", *content, ""]


def _bullets(items: Sequence[str], texts: Mapping) -> list[str]:
    return [f"- {item}" for item in items] if items else [texts["none_marker"]]


def render_body(fields: ParkFields, body: ParkBody, texts: Mapping) -> str:
    """The Markdown body of a note: the sections of ADR 0021 D01 and 0028 D03, then the purpose block."""
    headings = texts["headings"]
    lines = [jsondata.fill(texts["note"]["title"], {"ergon": f"{fields.id}-{fields.name}"}), ""]
    lines += _section(headings["goal"], body.goal.split("\n"))
    lines += _section(headings["decisions"], _bullets(body.decisions, texts))
    lines += _section(headings["answers"], _bullets(body.answers, texts))
    lines += _section(headings["checks"], _bullets(body.checks, texts))
    lines += _section(headings["unverified"], _bullets(body.unverified, texts))
    lines += _section(headings["agents"], _bullets(body.agents, texts))
    lines += _section(headings["next"], [fields.next_action])
    if body.purpose:
        lines += _section(headings["purpose"], [f"- {key}: {value}" for key, value in body.purpose])
    return "\n".join(lines).rstrip("\n") + "\n"


def render_note(fields: ParkFields, body: ParkBody, texts: Mapping) -> str:
    """The whole ``PARK.md``: header, a blank line, body.

    Raises:
        ParkError: the fields or the body fail their checks.
    """
    check_fields(fields, texts)
    check_body(body, texts)
    return render_header(fields) + "\n" + render_body(fields, body, texts)


def _sections(text: str) -> dict[str, list[str]]:
    """The ``## `` sections of a body by heading (the first of a repeated heading wins)."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.split("\n"):
        if line.startswith("## "):
            heading = line[3:].strip()
            current = sections.setdefault(heading, []) if heading not in sections else None
        elif current is not None:
            current.append(line)
    return sections


def _items(lines: Sequence[str]) -> tuple[str, ...]:
    return tuple(line[2:] for line in lines if line.startswith("- "))


def parse_body(text: str, texts: Mapping) -> ParkBody:
    """The ``ParkBody`` of a note's text after its header; a section that is missing reads as empty."""
    headings = texts["headings"]
    sections = _sections(text)
    goal_lines = sections.get(headings["goal"], [])
    purpose = []
    for item in _items(sections.get(headings["purpose"], [])):
        key, _, value = item.partition(": ")
        purpose.append((key, value))
    return ParkBody(
        goal="\n".join(goal_lines).strip("\n"),
        decisions=_items(sections.get(headings["decisions"], [])),
        answers=_items(sections.get(headings["answers"], [])),
        checks=_items(sections.get(headings["checks"], [])),
        unverified=_items(sections.get(headings["unverified"], [])),
        agents=_items(sections.get(headings["agents"], [])),
        purpose=tuple(purpose),
    )


def parse_note(text: str, source: str, texts: Mapping) -> tuple[ParkFields, ParkBody]:
    """The fields and the body of a whole ``PARK.md``."""
    fields = parse_header(text, source, texts)
    _lines, rest = _split_note(text, source, texts)
    return fields, parse_body(rest, texts)


def render_resume(fields: ParkFields, body: ParkBody, park_path: str, texts: Mapping) -> str:
    """``RESUME.md``: the harness-neutral prompt, generated from the note and nothing else.

    It names paths from the project root and the helper's own command, never an absolute path or a
    slash command, and carries the retirement text of ADR 0021 D05.
    """
    resume = texts["resume"]
    values = {
        "ergon": f"{fields.id}-{fields.name}",
        "id": fields.id,
        "park_path": park_path,
        "command": texts["invocation"],
    }
    blocks: list[list[str]] = [
        [jsondata.fill(resume["title"], values)],
        [resume["intro"]],
        [jsondata.fill(step, values) for step in resume["steps"]],
        [resume["next_heading"], "", fields.next_action],
        [
            resume["decisions_heading"],
            "",
            *([f"- {item}" for item in body.decisions] if body.decisions else [resume["decisions_none"]]),
        ],
        [resume["retirement_heading"], "", resume["retirement"][0]],
        *([line] for line in resume["retirement"][1:]),
    ]
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"


# --------------------------------------------------------------------------------------
# the digest: what SessionStart returns after a compaction (capped, cut at a whole line)
# --------------------------------------------------------------------------------------


def digest_lines(fields: ParkFields, body: ParkBody, state: str, texts: Mapping) -> list[str]:
    """The digest before the cap: the summary, the goal, the next action, the decisions and the answers."""
    spec = texts["digest"]
    lines = [jsondata.fill(spec["title"], {"ergon": f"{fields.id}-{fields.name}", "state": state})]
    for key, value in (
        ("plan", fields.plan),
        ("athlos", fields.athlos),
        ("row", fields.row),
        ("branch", fields.branch),
        ("readiness", fields.readiness),
    ):
        if value:
            lines.append(jsondata.fill(spec["field"], {"key": key, "value": value}))
    goal = body.goal.split("\n")
    lines.append(jsondata.fill(spec["goal"], {"text": goal[0]}))
    lines.extend(f"  {line}" for line in goal[1:])
    lines.append(jsondata.fill(spec["next"], {"text": fields.next_action}))
    for items, head, none in (
        (body.decisions, spec["decisions"], spec["decisions_none"]),
        (body.answers, spec["answers"], spec["answers_none"]),
    ):
        if items:
            lines.append(head)
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append(none)
    return lines


def read_note(ergon: Path, texts: Mapping) -> tuple[ParkFields, ParkBody]:
    """The fields and the body of an ergon's ``PARK.md``; an ergon without one was never parked.

    Raises:
        ParkError: the ergon has no ``PARK.md``, or its note does not parse.
    """
    note = ergon / _PARK_FILE
    if not note.is_file():
        raise _error(texts, "never_parked", ergon=ergon.name)
    return parse_note(note.read_text(encoding="utf-8"), f"{ergon.name}/{_PARK_FILE}", texts)


def digest(
    ergon: Path,
    cap: int,
    root: Path | None = None,
    data: Mapping | None = None,
    machine: str = "",
) -> str:
    """The capped digest of an ergon's note: whole lines up to ``cap`` characters, then the overflow line.

    ``cap`` counts the characters of the lines kept, newline included; the overflow line
    (``… N more lines in <path>``) is appended after them and is not counted. With ``root`` the
    path is the note's path from the project root, otherwise ``<ergon name>/PARK.md``. ``machine``
    is the one the caller judges a lease against, so the digest reads a copied lease stale exactly
    as ``list`` does.

    Raises:
        ParkError: the ergon was never parked or its note does not parse.
    """
    texts = data if data is not None else _texts()
    fields, body = read_note(ergon, texts)
    context = LeaseContext(now=time.time(), stale_hours=texts["stale_after_hours"], machine=machine)
    lines = digest_lines(fields, body, ergon_state(ergon, texts, context), texts)
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > cap:
            break
        kept.append(line)
        used += len(line) + 1
    if len(kept) < len(lines):
        where = _display_path(ergon / _PARK_FILE, root) if root is not None else f"{ergon.name}/{_PARK_FILE}"
        kept.append(jsondata.fill(texts["digest"]["overflow"], {"count": len(lines) - len(kept), "path": where}))
    return "\n".join(kept)


# --------------------------------------------------------------------------------------
# git: the branch and the revisions of the note are read, never passed by the caller
# --------------------------------------------------------------------------------------


def _git(args: Sequence[str], cwd: Path, *, strip: bool = True) -> str | None:
    """The output of one git command in ``cwd``, or ``None`` when git is absent or fails.

    The output is stripped unless ``strip`` is false, for a listing whose first line starts with a space.
    """
    try:
        done = subprocess.run(  # a fixed argument list, no shell
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() if strip else done.stdout


def git_branch(cwd: Path) -> str:
    """The branch checked out in ``cwd``, or the empty string outside a repository."""
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or ""


def git_revisions(cwd: Path, count: int = _GIT_REVISIONS) -> tuple[str, ...]:
    """The last ``count`` revisions of ``cwd``, newest first; empty outside a repository."""
    out = _git(["log", f"-{count}", "--format=%h"], cwd)
    if not out:
        return ()
    return tuple(line for line in out.split("\n") if line)


def git_uncommitted_paths(worktree: str) -> tuple[str, ...] | None:
    """The paths with uncommitted changes in ``worktree``, tracked or not, or ``None`` when unreadable.

    ``None`` means the worktree is unnamed, is not a folder here (a lease from another machine), or
    git cannot list it; an empty tuple means it is clean.
    """
    if not worktree or not Path(worktree).is_dir():
        return None
    out = _git(["status", "--porcelain", "--untracked-files=all"], Path(worktree), strip=False)
    if out is None:
        return None
    return tuple(line[3:] for line in out.split("\n") if line)


def now_stamp() -> str:
    """The current time as a stamp the note records: UTC, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------------------
# the lease: one holder per unit, created exclusively, judged stale on read
# --------------------------------------------------------------------------------------


def _lease_path(unit: Path) -> Path:
    return unit / _HOLDER_FILE


def render_lease(lease: Lease) -> str:
    """The lease file ``HOLDER``: its holder and the time of its last write."""
    holder = lease.holder
    values = {
        "harness": holder.harness,
        "session": holder.session_id,
        "machine": holder.machine,
        "worktree": holder.worktree,
        "written": datetime.fromtimestamp(lease.written, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    lines = [_HEADER_FENCE]
    lines.extend(_scalar_line(key, values[key]) for key in _LEASE_KEYS)
    lines.append(_HEADER_FENCE)
    return "\n".join(lines) + "\n"


def _parse_stamp(value: str, source: str, texts: Mapping) -> float:
    """The epoch seconds of an ISO stamp.

    A stamp that is not one is refused, never read as the epoch: ``0.0`` would make a corrupt lease
    older than any threshold, so a live holder's unit would read as free.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    except ValueError:
        raise _error(texts, "bad_stamp", path=source, key="written", value=value) from None


def parse_lease(text: str, source: str, texts: Mapping) -> Lease:
    """The lease a ``HOLDER`` file declares.

    Raises:
        ParkError: the file has no header, a line is malformed, or its stamp is not one.
    """
    lines, _body = _split_note(text, source, texts)
    values = _header_values(lines, source, texts, LEASE_HEADER)
    holder = Holder(
        harness=str(values.get("harness", "")),
        session_id=str(values.get("session", "")),
        machine=str(values.get("machine", "")),
        worktree=str(values.get("worktree", "")),
    )
    return Lease(holder=holder, written=_parse_stamp(str(values.get("written", "")), source, texts))


def read_lease(unit: Path, texts: Mapping) -> Lease | None:
    """The lease of a unit, or ``None`` when the unit is free."""
    path = _lease_path(unit)
    if not path.is_file():
        return None
    return parse_lease(path.read_text(encoding="utf-8"), f"{unit.name}/{_HOLDER_FILE}", texts)


def lease_is_stale(lease: Lease, context: LeaseContext) -> bool:
    """Whether a lease is stale: written on another machine, or older than the threshold.

    A lease that came with a copied ergon names another machine, and is stale at once.
    """
    if context.machine and lease.holder.machine and lease.holder.machine != context.machine:
        return True
    return lease.age_seconds(context.now) > context.stale_hours * _SECONDS_PER_HOUR


def acquire_lease(
    unit: Path,
    holder: Holder,
    texts: Mapping,
    context: LeaseContext,
    *,
    takeover: bool = False,
) -> Lease:
    """Take the lease of a unit, or refuse with the holder named.

    The file is created exclusively, so two sessions racing for it cannot both win. A lease
    held by this same session is renewed. A lease held by another session is refused; a stale
    one is refused too, and taken over only on the owner's word (``takeover``) — the holder it
    replaces is kept in the note's sessions, so the takeover leaves a trace.

    Raises:
        ParkError: the unit is held by another session, and the caller did not ask for a takeover.
    """
    existing = read_lease(unit, texts)
    lease = Lease(holder=holder, written=context.now)
    path = _lease_path(unit)
    path.parent.mkdir(parents=True, exist_ok=True)
    if existing is None:
        try:
            _write_exclusive(path, render_lease(lease))
        except FileExistsError:  # another session created it between the read and the create
            winner = read_lease(unit, texts)
            label = winner.holder.label() if winner is not None else texts["unknown_holder"]
            raise _error(texts, "held", unit=unit.name, holder=label) from None
        return lease
    if existing.holder.same_as(holder):
        renew_lease(unit, lease, context.now)
        return lease
    if not takeover:
        code = "held_stale" if lease_is_stale(existing, context) else "held"
        raise _error(texts, code, unit=unit.name, holder=existing.holder.label())
    remember_holder(unit, existing.holder, texts)  # the note is read, and keeps the trace, before the lease changes
    _write_atomically(path, render_lease(lease))
    return lease


def _write_exclusive(path: Path, text: str) -> None:
    """Create ``path`` with ``text``, exclusively: an existing file is never overwritten."""
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


def _write_atomically(path: Path, text: str) -> None:
    """Put ``text`` in ``path``, replacing what was there, so a reader sees the old file or the new one.

    The temporary file has a name of its own and sits beside ``path``, so two writers never share it
    and the replace is atomic.
    """
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def renew_lease(unit: Path, lease: Lease, now: float) -> None:
    """Renew the time of a lease the caller already holds."""
    renewed = Lease(holder=lease.holder, written=now)
    _write_atomically(_lease_path(unit), render_lease(renewed))


def release_lease(unit: Path) -> None:
    """Release the lease of a unit; the note stays."""
    _lease_path(unit).unlink(missing_ok=True)


def release_leases(ergon: Path) -> None:
    """Release every lease of an ergon: the plan's and its athlos'."""
    release_lease(ergon)
    for folder in _athlos_folders(ergon):
        release_lease(folder)


def _unit_note(unit: Path) -> Path | None:
    """The file that carries a unit's sessions: ``PARK.md`` for an ergon, an athlos's file, or ``None``."""
    for name in (_PARK_FILE, _ATHLOS_FILE, _LEGACY_ATHLOS_FILE):
        if (unit / name).is_file():
            return unit / name
    return None


def read_pending_sessions(unit: Path, texts: Mapping) -> tuple[SessionRef, ...]:
    """The sessions a takeover kept for a unit that had no note yet: one ``harness|session|machine`` per line.

    Raises:
        ParkError: a line is not a session.
    """
    path = unit / _SESSIONS_FILE
    if not path.is_file():
        return ()
    lines = path.read_text(encoding="utf-8").split("\n")
    return tuple(_parse_session(line, texts) for line in lines if line)


def merge_sessions(*groups: Sequence[SessionRef]) -> tuple[SessionRef, ...]:
    """The sessions of every group in order, each once: the earlier ones are kept, never rebuilt."""
    merged: list[SessionRef] = []
    for group in groups:
        merged.extend(session for session in group if session not in merged)
    return tuple(merged)


def remember_holder(unit: Path, holder: Holder, texts: Mapping) -> None:
    """Keep a replaced holder in the unit's record, among the sessions.

    The header of a unit's note carries the sessions the work was done in (``PARK.md`` for an ergon,
    ``ATHLOS.md`` for an athlos); a holder that is taken over stays among them, so the note says who held
    the unit before. A unit with no note yet keeps it in ``SESSIONS`` beside the lease, and the next
    ``write`` merges that file into the note and removes it. The note is read first, so a note that
    does not parse stops the takeover before anything changes, and the file is replaced atomically.
    A holder that names no harness or no session is no session a note can carry, so it is not
    recorded.

    Raises:
        ParkError: the unit's note, or its pending sessions, do not parse.
    """
    note = _unit_note(unit)
    source = f"{unit.name}/{note.name}" if note is not None else ""
    text = note.read_text(encoding="utf-8") if note is not None else ""
    pending = read_pending_sessions(unit, texts)
    if note is not None and note.name == _PARK_FILE:
        fields, _body = parse_note(text, source, texts)
        known = fields.sessions
    elif note is not None:
        doc = parse_athlos_doc(text, source, texts)
        known = doc.header.sessions
    else:
        known = pending
    if not holder.identified:
        return
    session = SessionRef(holder.harness, holder.session_id, holder.machine)
    if session in known:
        return
    if note is None:
        _write_atomically(unit / _SESSIONS_FILE, "".join(f"{_session_text(item)}\n" for item in (*pending, session)))
    elif note.name == _PARK_FILE:
        _lines, body = _split_note(text, source, texts)
        updated = dataclasses.replace(fields, sessions=(*known, session))
        _write_atomically(note, render_header(updated) + body)
    else:
        header = dataclasses.replace(doc.header, sessions=(*known, session))
        _write_atomically(note, render_athlos_doc(dataclasses.replace(doc, header=header), texts))


# --------------------------------------------------------------------------------------
# the plan: its header and its athlos lines, read from ``PLAN.md``
# --------------------------------------------------------------------------------------


def _plan_values(text: str) -> dict[str, str]:
    """The header of a plan file as ``key -> value``; a file without one is empty."""
    lines = text.split("\n")
    if not lines or lines[0] != _HEADER_FENCE:
        return {}
    for index in range(1, len(lines)):
        if lines[index] == _HEADER_FENCE:
            values: dict[str, str] = {}
            for line in lines[1:index]:
                match = _KEY_RE.match(line)
                if match is not None:
                    values[match.group(1)] = match.group(2) or ""
            return values
    return {}


def _split_values(value: str) -> tuple[str, ...]:
    """A comma-separated field as its items, trimmed."""
    return tuple(part.strip() for part in value.split(_FIELD_SEPARATOR) if part.strip())


def _athlos_field(cell: str) -> tuple[str, str]:
    """One athlos line cell as ``key, value``: ``tasks C186`` and ``result: text`` both parse.

    A cell that carries its colon and no value (`result:`) is the key with an empty value, not a key
    named `result:` — the empty value is what the caller refuses.
    """
    if ": " in cell:
        key, _, value = cell.partition(": ")
        return key.strip(), value.strip()
    key, _, value = cell.partition(" ")
    return key.strip().rstrip(":"), value.strip()


def parse_athlos_line(line: str, texts: Mapping) -> AthlosLine | None:
    """One athlos line of a plan as an ``AthlosLine``; a line that is not one is skipped.

    A cell whose key the format does not carry is refused, not dropped: a plan line is structure,
    and a field the reader cannot see is a field the plan silently loses (ADR 0029 D03).

    Raises:
        ParkError: a cell names an unknown field.
    """
    if not line.startswith("- "):
        return None
    cells = tuple(cell.strip() for cell in line[2:].split(_TASK_SEPARATOR))
    if len(cells) < 2:  # noqa: PLR2004 — an id and a label are the minimum
        return None
    match = _ATHLOS_ID_RE.match(cells[0])
    if match is None:
        return None
    listed_fields = ("tasks", "after", "paths")
    fields: dict[str, object] = {
        "tasks": (),
        "after": (),
        "paths": (),
        "harness": "",
        "result": "",
        "zone": "",
    }
    for cell in cells[2:]:
        key, value = _athlos_field(cell)
        if key not in fields:
            raise _error(texts, "unknown_field", id=cells[0], key=key)
        fields[key] = _split_values(value) if key in listed_fields else value
    return AthlosLine(
        id=cells[0],
        number=int(match.group(2)),
        label=cells[1],
        tasks=tuple(fields["tasks"]),  # type: ignore[arg-type]
        after=tuple(fields["after"]),  # type: ignore[arg-type]
        paths=tuple(fields["paths"]),  # type: ignore[arg-type]
        harness=str(fields["harness"]),
        result=str(fields["result"]),
        zone=str(fields["zone"]),
    )


def parse_plan(text: str, texts: Mapping) -> Plan:
    """A plan file as its header and its athlos lines.

    The section heading of the lines is read under its new name and the one a plan written before
    ADR 0029 D02 carries; only the new one is ever written.

    Raises:
        ParkError: an athlos line carries a field the format does not know.
    """
    values = _plan_values(text)
    header = PlanHeader(
        id=values.get("id", ""),
        name=values.get("name", ""),
        title=values.get("title", ""),
        tasks=_split_values(values.get("tasks", "")),
    )
    sections = _sections(text)
    lines = sections.get(_ATHLOS_HEADING) or sections.get(_LEGACY_ATHLOS_HEADING) or []
    athlos_lines = [line for line in lines if line.strip()]
    athlos = [line for line in (parse_athlos_line(text_line, texts) for text_line in athlos_lines) if line is not None]
    return Plan(header=header, athlos=tuple(athlos))


def read_plan(ergon: Path, texts: Mapping) -> Plan | None:
    """The plan of an ergon, or ``None`` when it has none.

    Raises:
        ParkError: an athlos line of the plan carries an unknown field.
    """
    path = ergon / _PLAN_FILE
    if not path.is_file():
        return None
    return parse_plan(path.read_text(encoding="utf-8"), texts)


def _paths_overlap(one: str, other: str) -> bool:
    """Whether two forecast paths of two athlos may touch the same file."""
    left = one.rstrip(_PATH_SEPARATOR)
    right = other.rstrip(_PATH_SEPARATOR)
    return left == right or left.startswith(right + _PATH_SEPARATOR) or right.startswith(left + _PATH_SEPARATOR)


def _athlos_orders(one: AthlosLine, other: AthlosLine, plan: Plan) -> bool:
    """Whether one of the two athlos waits for the other, directly or through a chain of them.

    The chain matters: an athlos that waits for an athlos that waits for another cannot run at once
    with it, so the pair shares no warning. Only athlos ids of this plan order athlos; an
    ``after`` that names a task id orders nothing here.
    """
    athlos = {line.id: line for line in plan.athlos}
    waiting = _athlos_waiting_for(athlos, one.id)
    return other.id in waiting or one.id in _athlos_waiting_for(athlos, other.id)


def _athlos_waiting_for(athlos: Mapping[str, AthlosLine], athlos_id: str) -> set[str]:
    """The athlos ids that wait, directly or through a chain, for ``athlos_id``."""
    reached: set[str] = set()
    pending = [athlos_id]
    while pending:
        current = pending.pop()
        for other in athlos.values():
            if current in other.after and other.id not in reached:
                reached.add(other.id)
                pending.append(other.id)
    return reached


def shared_path_warnings(plan: Plan, texts: Mapping) -> list[str]:
    """The warnings of a plan: two athlos that may run at once and forecast the same path.

    The forecast is advice, not a fact; the owned uncommitted paths of each note are the fact.
    """
    warnings: list[str] = []
    for index, one in enumerate(plan.athlos):
        for other in plan.athlos[index + 1 :]:
            if _athlos_orders(one, other, plan):
                continue
            shared = sorted(
                {path for path in one.paths for other_path in other.paths if _paths_overlap(path, other_path)}
            )
            warnings.extend(
                jsondata.fill(
                    texts["list"]["warning_shared_paths"],
                    {"athlos": f"{one.id} {other.id}", "path": path},
                )
                for path in shared
            )
    return warnings


# --------------------------------------------------------------------------------------
# an athlos's own file: its steps with their done marks, and whether it is done
# --------------------------------------------------------------------------------------


def render_athlos_doc(doc: AthlosDoc, texts: Mapping) -> str:
    """The whole ``ATHLOS.md``: its header, its steps and, once the result is met, the done mark."""
    lines = [render_header(doc.header).rstrip("\n"), "", _STEPS_HEADING, ""]
    for text, is_done in doc.steps:
        lines.append((_STEP_DONE if is_done else _STEP_UNDONE) + text)
    if not doc.steps:
        lines.append(texts["none_marker"])
    lines.append("")
    if doc.done:
        lines.append(_DONE_MARKER)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def parse_athlos_doc(text: str, source: str, texts: Mapping) -> AthlosDoc:
    """The ``AthlosDoc`` a ``ATHLOS.md`` declares: its header, its steps and its done mark.

    Raises:
        ParkError: the file has no header, or a line is malformed.
    """
    header = parse_header(text, source, texts)
    _lines, body = _split_note(text, source, texts)
    steps: list[tuple[str, bool]] = []
    done = False
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith(_STEP_DONE):
            steps.append((stripped[len(_STEP_DONE) :], True))
        elif stripped.startswith(_STEP_UNDONE):
            steps.append((stripped[len(_STEP_UNDONE) :], False))
        elif stripped == _DONE_MARKER:
            done = True
    return AthlosDoc(header=header, steps=tuple(steps), done=done)


def read_athlos_doc(path: Path, texts: Mapping) -> AthlosDoc | None:
    """The athlos file of an athlos folder, or ``None`` when it has none."""
    if not path.is_file():
        return None
    source = "/".join(path.parts[-_ATHLOS_SOURCE_PARTS:])  # <ergon>/<n>/ATHLOS.md: the ergon is named
    return parse_athlos_doc(path.read_text(encoding="utf-8"), source, texts)


# --------------------------------------------------------------------------------------
# files: written atomically, as a set
# --------------------------------------------------------------------------------------


def _temp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def write_files(files: Sequence[tuple[Path, str]]) -> None:
    """Write ``files`` so none is left half-written: every one to a temp file first, then replaced in order.

    Each temp file sits beside its target (``os.replace`` is atomic within a directory) and is
    removed if anything fails before or during the replacing. The caller orders ``files`` so the
    file that marks the work as done lands last.
    """
    temps: list[tuple[Path, Path]] = []
    try:
        for path, text in files:
            temp = _temp_path(path)
            temps.append((temp, path))
            with temp.open("xb") as handle:
                handle.write(text.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
        for temp, path in temps:
            temp.replace(path)
    finally:
        for temp, _path in temps:
            temp.unlink(missing_ok=True)


def _remove_if_empty(folder: Path) -> None:
    with contextlib.suppress(OSError):  # not empty, or already gone: nothing of ours to remove
        folder.rmdir()


# --------------------------------------------------------------------------------------
# the ergons of a project
# --------------------------------------------------------------------------------------


def _ergon_names(root: Path, *, closed: bool = False) -> list[str]:
    """The names of the ergon folders under ``.ergon/`` (``<id>-<name>`` only), sorted."""
    ergon = ergon_root(root)
    if closed:
        ergon = ergon / _CLOSED_DIR
    if not ergon.is_dir():
        return []
    return sorted(entry.name for entry in ergon.iterdir() if entry.is_dir() and _ERGON_RE.match(entry.name))


def _ergon_id(ergon_name: str) -> str:
    match = _ERGON_RE.match(ergon_name)
    assert match is not None  # noqa: S101 — callers pass names _ergon_names accepted
    return match.group(1)


def _find_ergon_in(root: Path, ergon_id: str, texts: Mapping, *, closed: bool) -> Path:
    names = _ergon_names(root, closed=closed)
    found = [name for name in names if _ergon_id(name) == ergon_id]
    ergon = _display_path(ergon_root(root), root)
    if not found:
        raise _error(texts, "no_ergon", id=ergon_id, ergon=ergon, ergons=", ".join(names) or "none")
    if len(found) > 1:
        raise _error(texts, "several_ergons", id=ergon_id, ergon=ergon, ergons=", ".join(found))
    base = ergon_root(root) / _CLOSED_DIR if closed else ergon_root(root)
    return base / found[0]


def find_ergon(root: Path, ergon_id: str, texts: Mapping) -> Path:
    """The ergon folder whose name leads with ``ergon_id``.

    Raises:
        ParkError: no ergon or several ergons carry the id; the message names the candidates.
    """
    return _find_ergon_in(root, ergon_id, texts, closed=False)


def find_closed_ergon(root: Path, ergon_id: str, texts: Mapping) -> Path | None:
    """The closed ergon folder whose name leads with ``ergon_id``, or ``None``."""
    try:
        return _find_ergon_in(root, ergon_id, texts, closed=True)
    except ParkError:
        return None


def athlos_file_of(folder: Path) -> Path:
    """The athlos file of a folder: ``ATHLOS.md``, or the ``JOB.md`` of a record written before the rename.

    The answer is a path whether or not either exists, so a writer gets the new name and a reader
    still finds the old one (ADR 0029 D11, D12).
    """
    fresh = folder / _ATHLOS_FILE
    if fresh.is_file():
        return fresh
    legacy = folder / _LEGACY_ATHLOS_FILE
    return legacy if legacy.is_file() else fresh


def _athlos_number(folder: Path) -> int | None:
    """The number an athlos folder carries: its whole name, or the lead of a legacy ``<n>-<label>``."""
    name = folder.name
    if name.isdecimal():
        return int(name)
    head, _, _tail = name.partition("-")
    return int(head) if head.isdecimal() else None


def athlos_folder(ergon: Path, number: int) -> Path | None:
    """The folder of the athlos of this number, in either layout, or ``None`` when the ergon has none.

    The new layout names the folder by the number alone (ADR 0029 D11); the ``jobs/<n>-<label>/`` of
    a record written before it is read and translated (ADR 0029 D12).
    """
    fresh = ergon / str(number)
    if fresh.is_dir():
        return fresh
    legacy = ergon / _LEGACY_ATHLOS_DIR
    if not legacy.is_dir():
        return None
    for entry in sorted(legacy.iterdir()):
        if entry.is_dir() and _athlos_number(entry) == number:
            return entry
    return None


def _athlos_folders(ergon: Path) -> list[Path]:
    """The athlos folders of an ergon, by number: the new layout, plus the ``jobs/`` of an old record.

    One number has one folder in the listing: where both layouts hold it, the new one is the record.
    """
    found: dict[int, Path] = {}
    if ergon.is_dir():
        for entry in sorted(ergon.iterdir()):
            if entry.is_dir() and entry.name.isdecimal():
                found[int(entry.name)] = entry
    legacy = ergon / _LEGACY_ATHLOS_DIR
    if legacy.is_dir():
        for entry in sorted(legacy.iterdir()):
            if not entry.is_dir():
                continue
            number = _athlos_number(entry)
            if number is not None and number not in found:
                found[number] = entry
    return [found[number] for number in sorted(found)]


def find_athlos_folder(ergon: Path, athlos_id: str, texts: Mapping) -> Path | None:
    """The folder of the athlos named by ``athlos_id`` (``<ergon-id>.<n>``), in either layout.

    The number of the id is the folder's name; a folder a hand made under another name is still
    found by the id its athlos file carries.
    """
    match = _ATHLOS_ID_RE.match(athlos_id)
    if match is not None:
        folder = athlos_folder(ergon, int(match.group(2)))
        if folder is not None:
            return folder
    for folder in _athlos_folders(ergon):
        doc = read_athlos_doc(athlos_file_of(folder), texts)
        if doc is not None and doc.header.athlos == athlos_id:
            return folder
    return None


def move_athlos_folder(ergon: Path, number: int, current: Path | None) -> Path:
    """The folder an athlos's file is written into: ``<ergon>/<n>/``, the old record moved there once.

    An old form is never written (ADR 0029 D12), so the write that meets a record in the retired
    layout carries the whole folder — its file, its lease and its notes — to the folder of the
    athlos's number, once. Where the new folder already stands the old one is left for the owner's
    one rewrite of the records this release did not touch.
    """
    fresh = ergon / str(number)
    if current is None or current == fresh:
        return fresh
    if fresh.exists():
        return fresh
    current.rename(fresh)
    legacy_file = fresh / _LEGACY_ATHLOS_FILE
    if legacy_file.is_file() and not (fresh / _ATHLOS_FILE).is_file():
        legacy_file.rename(fresh / _ATHLOS_FILE)
    _remove_if_empty(ergon / _LEGACY_ATHLOS_DIR)
    return fresh


def athlos_id_of(ergon_id: str, number: int) -> str:
    """The id of an athlos of an ergon: the ergon's id and the athlos's number."""
    return f"{ergon_id}.{number}"


def unit_state(unit: Path, texts: Mapping, context: LeaseContext, *, athlos_done: bool = False) -> str:
    """The derived state of a unit (ADR 0028 D09): active, parked, not started or done.

    A stale lease holds nothing: the unit is free, and the lease is offered to the owner.
    """
    states = _states(texts)
    if athlos_done:
        return states["done"]
    lease = read_lease(unit, texts)
    if lease is not None and not lease_is_stale(lease, context):
        return states["active"]
    if (unit / _PARK_FILE).is_file():
        return states["parked"]
    return states["not_started"]


def ergon_state(ergon: Path, texts: Mapping, context: LeaseContext) -> str:
    """The state of an ergon, joined from its athlos and its own lease and note (ADR 0028 D08, D09).

    An ergon is **active** when it or any of its athlos is held, else **done** when every athlos is done,
    else **parked** when it or any of its athlos is parked, else **not started**. With a plan that
    lists athlos, "every athlos" is every listed athlos: it has a folder whose ``ATHLOS.md`` is done, and a
    athlos with no folder has not started. With no plan, or a plan that lists no athlos, the athlos
    folders that exist decide. An ergon whose athlos are all done is done even when its own note is
    still there; only a live lease on the ergon itself outranks that.
    """
    states = _states(texts)
    folders = _athlos_folders(ergon)
    docs = [read_athlos_doc(athlos_file_of(folder), texts) for folder in folders]
    athlos_states = [
        unit_state(folder, texts, context, athlos_done=doc.done)
        for folder, doc in zip(folders, docs, strict=True)
        if doc is not None
    ]
    own = unit_state(ergon, texts, context)
    if states["active"] in (own, *athlos_states):
        return states["active"]
    plan = read_plan(ergon, texts)
    if plan is not None and plan.athlos:
        done_ids = {doc.header.athlos for doc in docs if doc is not None and doc.done}
        if all(line.id in done_ids for line in plan.athlos):
            return states["done"]
    elif docs and all(doc is not None and doc.done for doc in docs):
        return states["done"]
    if states["parked"] in (own, *athlos_states):
        return states["parked"]
    return states["not_started"]


def _age_days(path: Path, now: float) -> int | None:
    """The age of a file in whole days, or ``None`` when there is no file."""
    if not path.is_file():
        return None
    return max(0, int((now - path.stat().st_mtime) // _SECONDS_PER_DAY))


# --------------------------------------------------------------------------------------
# writing an ergon and an athlos
# --------------------------------------------------------------------------------------


def write_ergon(fields: ParkFields, body: ParkBody, root: Path, texts: Mapping, cwd: Path) -> Path:
    """Park the work: write ``RESUME.md`` and ``PARK.md`` into the ergon folder.

    The ergon folder is created when missing. Everything that can be refused is checked before
    any file is touched; the files then land together (``write_files``), ``PARK.md`` last among
    the ergon's, and a failure removes the folder it created when that folder is still empty.

    The sessions of the note are kept, not rebuilt: the sessions an earlier write recorded, the holder
    a takeover kept (``SESSIONS`` when the ergon had no note yet), and then the ones on this command line.

    The branch and the revisions come from git, and the note records the time it was written.

    Returns:
        The ergon folder.

    Raises:
        ParkError: a field fails its check, an ergon with this id has another name, a closed ergon has this
            id and name, or the note already there does not parse.
    """
    check_fields(fields, texts)
    check_body(body, texts)
    refuse_ergon_conflict(fields, root, texts)
    ergon = ergon_root(root) / f"{fields.id}-{fields.name}"
    park_path = _display_path(ergon / _PARK_FILE, root)
    sessions = merge_sessions(_note_sessions(ergon, texts), read_pending_sessions(ergon, texts), fields.sessions)
    stamped = dataclasses.replace(
        fields, sessions=sessions, branch=git_branch(cwd), revisions=git_revisions(cwd), written=now_stamp()
    )
    files = [
        (ergon / _RESUME_FILE, render_resume(stamped, body, park_path, texts)),
        (ergon / _PARK_FILE, render_note(stamped, body, texts)),
    ]
    created = not ergon.is_dir()
    try:
        ergon.mkdir(parents=True, exist_ok=True)
        write_files(files)
    except BaseException:
        if created:
            _remove_if_empty(ergon)
        raise
    (ergon / _SESSIONS_FILE).unlink(missing_ok=True)  # merged into the note just written
    return ergon


def _note_sessions(ergon: Path, texts: Mapping) -> tuple[SessionRef, ...]:
    """The sessions the ergon's note already carries; none when the ergon has no note yet."""
    if not (ergon / _PARK_FILE).is_file():
        return ()
    return read_note(ergon, texts)[0].sessions


def refuse_ergon_conflict(fields: ParkFields, root: Path, texts: Mapping) -> None:
    """Refuse an ergon whose id is taken by another name, or whose id and name belong to a closed ergon.

    A closed ergon keeps its id and name for good, so a write never reuses them; ``local-id`` counts
    the closed ergons for the same reason.

    Raises:
        ParkError: a live or closed ergon carries the id under another name, or a closed ergon has both.
    """
    ergon_name = f"{fields.id}-{fields.name}"
    other = [name for name in _ergon_names(root) if _ergon_id(name) == fields.id and name != ergon_name]
    other += [name for name in _ergon_names(root, closed=True) if _ergon_id(name) == fields.id and name != ergon_name]
    if other:
        raise _error(texts, "ergon_other_name", existing=other[0], id=fields.id, name=fields.name)
    if ergon_name in _ergon_names(root, closed=True):
        raise _error(texts, "ergon_closed", ergon=ergon_name)


def write_athlos_doc(folder: Path, doc: AthlosDoc, texts: Mapping) -> None:
    """Write an athlos's own file, creating its folder when missing; a reader sees the old file or the new one."""
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomically(folder / _ATHLOS_FILE, render_athlos_doc(doc, texts))


def _check_athlos_doc(doc: AthlosDoc, ergon_name: str, texts: Mapping) -> None:
    """Refuse an athlos file whose header would not read back, naming the ergon and the offending value.

    The header is built from the plan's header and athlos line, so the plan is what is at fault: a
    plan ``id`` that is no task id, say, would make a ``ATHLOS.md`` that ``park list`` cannot parse.

    Raises:
        ParkError: the plan's header or athlos line breaks the header's contract.
    """
    try:
        check_fields(doc.header, texts)
    except ParkError as exc:
        raise _error(texts, "bad_plan", ergon=ergon_name, reason=exc) from exc


def athlos_doc_for(athlos: AthlosLine, ergon_id: str, ergon_name: str, plan: Plan | None, cwd: Path) -> AthlosDoc:
    """The athlos file an athlos starts with: its header from the plan's athlos line, no steps yet."""
    header = ParkFields(
        id=ergon_id,
        name=ergon_name,
        next_action=athlos.result,
        plan=plan.header.id if plan is not None else "",
        athlos=athlos.id,
        tasks=athlos.tasks,
        branch=git_branch(cwd),
    )
    return AthlosDoc(header=header)


# --------------------------------------------------------------------------------------
# the listing: the ergons, their athlos, and the states derived from the folders
# --------------------------------------------------------------------------------------


def summarize_ergon(ergon: Path, texts: Mapping, context: LeaseContext) -> ErgonSummary:
    """What ``list`` says of one ergon; an ergon with no ``PARK.md`` has no age and no next action."""
    ergon_id = _ergon_id(ergon.name)
    name = ergon.name[len(ergon_id) + 1 :]
    note = ergon / _PARK_FILE
    if not note.is_file():
        return ErgonSummary(ergon_id, name, ergon_state(ergon, texts, context), "", "", 0, "", None)
    fields, body = read_note(ergon, texts)
    return ErgonSummary(
        ergon_id,
        name,
        ergon_state(ergon, texts, context),
        fields.plan,
        fields.next_action,
        len(body.decisions),
        fields.branch,
        _age_days(note, context.now),
    )


def summarize_athlos(folder: Path, texts: Mapping, context: LeaseContext) -> AthlosSummary | None:
    """What ``list`` says of one athlos, or ``None`` when the folder carries no athlos file."""
    doc = read_athlos_doc(athlos_file_of(folder), texts)
    if doc is None:
        return None
    state = unit_state(folder, texts, context, athlos_done=doc.done)
    return AthlosSummary(
        id=doc.header.athlos or folder.name,
        name=folder.name,
        state=state,
        tasks=doc.header.tasks,
        next_action=doc.next_step(),
        branch=doc.header.branch,
        age_days=_age_days(athlos_file_of(folder), context.now),
    )


def _ergon_tasks(ergon: Path, summaries: Sequence[AthlosSummary], texts: Mapping) -> tuple[str, ...]:
    """The task ids an ergon carries: from its plan header, its athlos lines and its athlos files."""
    tasks: list[str] = []
    plan = read_plan(ergon, texts)
    if plan is not None:
        tasks.extend(plan.header.tasks)
        for line in plan.athlos:
            tasks.extend(line.tasks)
    for summary in summaries:
        tasks.extend(summary.tasks)
    return tuple(tasks)


def _matches(
    summary: ErgonSummary, athlos: Sequence[AthlosSummary], ergon: Path, query: ListQuery, texts: Mapping
) -> bool:
    """Whether an ergon passes the filters of ``list``."""
    if query.plan and summary.plan != query.plan:
        return False
    if query.state and summary.state != query.state:
        return False
    return not query.task or query.task in _ergon_tasks(ergon, athlos, texts)


def list_ergons(
    root: Path, query: ListQuery, texts: Mapping, context: LeaseContext
) -> tuple[list[ErgonSummary], list[AthlosSummary]]:
    """The ergons under ``.ergon/`` that match ``query``, and the athlos of those ergons.

    Reads only: the local index is retired, so the folders are the whole record. An ergon whose files
    do not parse is listed with its ``unreadable`` reason, whatever the filters, and the other
    ergons are listed as usual.
    """
    summaries: list[ErgonSummary] = []
    units: list[AthlosSummary] = []
    entries: list[Path] = [ergon_root(root) / name for name in _ergon_names(root)]
    if query.closed:
        entries += [ergon_root(root) / _CLOSED_DIR / name for name in _ergon_names(root, closed=True)]
    for ergon in entries:
        try:
            summary = summarize_ergon(ergon, texts, context)
            ergon_athlos = [summarize_athlos(folder, texts, context) for folder in _athlos_folders(ergon)]
        except ParkError as exc:  # one bad ergon is reported on its own line, never stops the others
            ergon_id = _ergon_id(ergon.name)
            reason = _LINE_BREAKS_RE.sub(" ", str(exc))
            summaries.append(ErgonSummary(ergon_id, ergon.name[len(ergon_id) + 1 :], "", "", "", 0, "", None, reason))
            continue
        ergon_athlos = [item for item in ergon_athlos if item is not None]
        if not _matches(summary, ergon_athlos, ergon, query, texts):
            continue
        summaries.append(summary)
        units.extend(ergon_athlos)
    return sorted(summaries, key=lambda item: item.id), units


def _truncate(text: str, width: int, texts: Mapping) -> str:
    """``text`` cut to ``width`` characters, the last one the ellipsis when it was cut."""
    return text if len(text) <= width else text[: width - 1] + texts["ellipsis"]


def format_summary(item: ErgonSummary, texts: Mapping) -> str:
    """One ``list`` line; an absent value is the empty cell and the age is whole days (``3d``)."""
    empty = texts["empty_cell"]
    if item.unreadable:
        return jsondata.fill(texts["list"]["unreadable"], {"id": item.id, "name": item.name, "reason": item.unreadable})
    return jsondata.fill(
        texts["list"]["line"],
        {
            "id": item.id,
            "name": item.name,
            "state": item.state,
            "plan": item.plan or empty,
            "next": _truncate(item.next_action, texts["next_width"], texts) if item.next_action else empty,
            "decisions": item.decisions,
            "branch": item.branch or empty,
            "age": f"{item.age_days}d" if item.age_days is not None else empty,
        },
    )


def format_athlos(item: AthlosSummary, texts: Mapping) -> str:
    """One athlos line of ``list``."""
    empty = texts["empty_cell"]
    return jsondata.fill(
        texts["list"]["athlos_line"],
        {
            "id": item.id,
            "name": item.name,
            "state": item.state,
            "tasks": ", ".join(item.tasks) or empty,
            "next": _truncate(item.next_action, texts["next_width"], texts) if item.next_action else empty,
            "branch": item.branch or empty,
            "age": f"{item.age_days}d" if item.age_days is not None else empty,
        },
    )


# --------------------------------------------------------------------------------------
# the active unit: read from the worktree's folder, never kept in git (ADR 0028 D10)
# --------------------------------------------------------------------------------------


def worktree_unit(folder: Path) -> tuple[str, int] | None:
    """The ergon id and the athlos number a worktree's folder names, or ``None``.

    The folder is ``<id>-<name>.<n>``: the ergon's own folder name and the athlos's number.
    """
    name = folder.name
    base, _, tail = name.rpartition(".")
    # isdecimal, not isdigit: a superscript digit passes isdigit and then fails in int().
    if not base or not tail.isdecimal() or not _ERGON_RE.match(base):
        return None
    match = _ERGON_RE.match(base)
    assert match is not None  # noqa: S101 — the guard above checked it
    return match.group(1), int(tail)


def active_unit(root: Path, texts: Mapping) -> tuple[Path, str, int] | None:
    """The ergon and the athlos this session is in, read from the folder it works in.

    A session in the main checkout has no active unit until it picks one; a session in an athlos's
    worktree is in that athlos, named by the worktree's own folder.
    """
    if root.parent.name != _WORKTREES_DIR:
        return None
    unit = worktree_unit(root)
    if unit is None:
        return None
    ergon_id, number = unit
    try:
        ergon = find_ergon(root, ergon_id, texts)
    except ParkError:
        return None
    return ergon, ergon_id, number


# --------------------------------------------------------------------------------------
# the worktree list: every worktree git knows, what carries it, and which one may go (ADR 0029 D06, D09)
# --------------------------------------------------------------------------------------

_BRANCH_NAMESPACE = "_aitna/"  # ADR 0028 D04: an athlos's branch is ``_aitna/<id>-<name>.<n>``
_HEADS = "refs/heads/"


@dataclass(frozen=True)
class GitWorktree:
    """One entry of ``git worktree list --porcelain``: the folder, its commit and its branch."""

    path: str
    head: str
    branch: str  # the short name; empty when HEAD is detached
    bare: bool


@dataclass(frozen=True)
class UnitRecord:
    """What a unit says of the branch and the folder it works in: read from its lease and its note."""

    ergon: str
    athlos: str  # empty for the ergon's own unit
    branch: str  # the branch its note records
    worktree: str  # the folder its live lease names; empty when the lease is absent, stale or unnamed
    live: bool  # a live lease holds the unit
    written: float  # when its note was last written


@dataclass(frozen=True)
class WorktreeRow:
    """One row of ``worktrees``: a worktree, or a branch whose worktree is gone, and what state its work is in."""

    path: str  # absolute; empty for a branch-only row
    shown: str  # the path as printed: from the ``.worktrees/`` folder when inside it
    branch: str
    kind: str
    ergon: str
    athlos: str
    clean: bool | None  # ``None``: the folder cannot be read, or there is none
    ahead: int | None
    age_seconds: int | None
    carried: bool
    differing: tuple[str, ...] | None  # the paths the branch changed that the owner's branch does not hold alike
    state: str  # working, ready, carried, backup, not-carried backup, harness or main
    removable: bool  # a carried worktree or a carried backup branch
    subject: str  # the subject of the branch's last commit, read for a ready row only


@dataclass(frozen=True)
class _Listing:
    """What every row of one ``worktrees`` call is judged against."""

    root: Path  # where git runs
    main: str  # the owner's checkout
    owner_tip: str  # the commit its branch stands at
    units: Sequence[UnitRecord]
    texts: Mapping
    now: float


def parse_worktree_list(text: str) -> list[GitWorktree]:
    """The entries of ``git worktree list --porcelain``, in git's order; blocks are split by a blank line."""
    entries: list[GitWorktree] = []
    for block in text.split("\n\n"):
        path = head = branch = ""
        bare = False
        for line in block.split("\n"):
            key, _, value = line.partition(" ")
            if key == "worktree":
                path = value
            elif key == "HEAD":
                head = value
            elif key == "branch":
                branch = value.removeprefix(_HEADS)
            elif line == "bare":
                bare = True
        if path:
            entries.append(GitWorktree(path, head, branch, bare))
    return entries


def branch_unit(branch: str) -> tuple[str, int] | None:
    """The ergon id and the athlos number an athlos's branch ``_aitna/<id>-<name>.<n>`` names, or ``None``."""
    if not branch.startswith(_BRANCH_NAMESPACE):
        return None
    base, _, tail = branch[len(_BRANCH_NAMESPACE) :].rpartition(".")
    match = _ERGON_RE.match(base)
    if match is None or not tail.isdecimal():
        return None
    return match.group(1), int(tail)


def _same_path(one: str, other: str) -> bool:
    return bool(one) and bool(other) and os.path.realpath(one) == os.path.realpath(other)


def _live_lease(unit: Path, texts: Mapping, context: LeaseContext) -> Lease | None:
    """The lease of a unit when it is live; a stale one holds nothing."""
    lease = read_lease(unit, texts)
    return lease if lease is not None and not lease_is_stale(lease, context) else None


def _unit_record(unit: Path, ergon_id: str, athlos: str, branch: str, lease: Lease | None) -> UnitRecord:
    """What one unit says: its note's branch, and the folder its live lease names."""
    note = athlos_file_of(unit) if athlos else unit / _PARK_FILE
    return UnitRecord(
        ergon=ergon_id,
        athlos=athlos,
        branch=branch,
        worktree=lease.holder.worktree if lease is not None else "",
        live=lease is not None,
        written=note.stat().st_mtime if note.is_file() else 0.0,
    )


def _unit_records(root: Path, texts: Mapping, context: LeaseContext) -> list[UnitRecord]:
    """The ergon's own unit and each athlos of every ergon, the closed ones too, as the list matches against.

    An ergon whose files do not parse is left out: one bad ergon never stops the list.
    """
    records: list[UnitRecord] = []
    layer = ergon_root(root)
    folders = [layer / name for name in _ergon_names(root)]
    folders += [layer / _CLOSED_DIR / name for name in _ergon_names(root, closed=True)]
    for ergon in folders:
        ergon_id = _ergon_id(ergon.name)
        try:
            note_branch = read_note(ergon, texts)[0].branch if (ergon / _PARK_FILE).is_file() else ""
            found = [_unit_record(ergon, ergon_id, "", note_branch, _live_lease(ergon, texts, context))]
            for folder in _athlos_folders(ergon):
                doc = read_athlos_doc(athlos_file_of(folder), texts)
                if doc is not None:
                    athlos = doc.header.athlos or folder.name
                    found.append(
                        _unit_record(folder, ergon_id, athlos, doc.header.branch, _live_lease(folder, texts, context))
                    )
        except ParkError:
            continue
        records.extend(found)
    return records


def _changed_paths(cwd: Path, *revisions: str) -> frozenset[str] | None:
    """The paths that differ between two revisions, both sides of a rename apart, or ``None`` when git fails."""
    out = _git(["diff", "--name-only", "--no-renames", "-z", *revisions], cwd, strip=False)
    if out is None:
        return None
    return frozenset(path for path in out.split("\0") if path)


def uncarried_paths(root: Path, owner_tip: str, tip: str) -> tuple[str, ...] | None:
    """The paths of the branch at ``tip`` that the owner's branch does not hold alike; empty when it is carried.

    ``git branch --merged`` cannot say it: a squash leaves the branch unmerged. So it is read from
    content: every path the branch changed since its merge-base must hold the same blob at ``tip`` and
    at ``owner_tip`` (absent on both sides is equal); a branch that changed no path, or whose tip the
    owner's branch contains, has no such path. ``None`` is what git cannot answer (no merge-base, a
    failing command), and counts as not carried.
    """
    base = _git(["merge-base", owner_tip, tip], root)
    if not base:
        return None
    if base == tip:
        return ()
    changed = _changed_paths(root, base, tip)
    differing = _changed_paths(root, tip, owner_tip)
    if changed is None or differing is None:
        return None
    return tuple(sorted(changed & differing))


def _relative_age(seconds: int) -> str:
    """An age in the short relative form: minutes under an hour, hours under a day, days after."""
    if seconds < _SECONDS_PER_HOUR:
        return f"{seconds // 60}m"
    if seconds < _SECONDS_PER_DAY:
        return f"{seconds // _SECONDS_PER_HOUR}h"
    return f"{seconds // _SECONDS_PER_DAY}d"


def _unit_for(units: Sequence[UnitRecord], path: str, branch: str) -> tuple[UnitRecord | None, bool]:
    """The unit a row belongs to, and whether a live lease holds it.

    The live lease whose folder is ``path`` wins; else the unit whose latest note names ``branch``.
    A live lease on any unit that names the branch holds the row too.
    """
    by_path = [unit for unit in units if unit.live and _same_path(unit.worktree, path)]
    by_branch = [unit for unit in units if branch and unit.branch == branch]
    held = bool(by_path) or any(unit.live for unit in by_branch)
    if by_path:
        return max(by_path, key=lambda unit: (unit.athlos != "", unit.written)), held
    if by_branch:
        return max(by_branch, key=lambda unit: (unit.written, unit.athlos != "")), held
    return None, held


@dataclass(frozen=True)
class _RowFacts:
    """What decides a row's state: a live lease, the content check, the folder's cleanliness, the commits ahead."""

    held: bool
    carried: bool
    clean: bool | None
    ahead: int | None


def _row_state(kind: str, texts: Mapping, facts: _RowFacts) -> str:
    """The state of a row: what the owner may do with it, or why nothing yet.

    An athlos worktree is *working* while it is dirty (or cannot be read) or a live lease holds it,
    *ready* when it is clean, beyond the owner's branch and not carried, and *carried* when its work is
    in the owner's branch. A branch without a worktree is a *backup*, carried or not; a held one is
    still *working*.
    """
    kinds = texts["worktrees"]["kinds"]
    states = texts["worktrees"]["states"]
    if kind in (kinds["main"], kinds["harness"]):
        return states[kind]
    if facts.held:
        return states["working"]
    if kind == kinds["branch_only"]:
        return states["backup"] if facts.carried else states["not_carried_backup"]
    if facts.clean is not True:
        return states["working"]
    if facts.carried:
        return states["carried"]
    return states["ready"] if facts.ahead else states["working"]


def _worktree_row(listing: _Listing, path: str, branch: str, tip: str, kind: str) -> WorktreeRow:
    """One row: the facts git gives of ``tip``, the unit that owns it, and its state."""
    texts = listing.texts
    unit, held = _unit_for(listing.units, path, branch)
    differing = uncarried_paths(listing.root, listing.owner_tip, tip)
    carried = differing == ()
    uncommitted = git_uncommitted_paths(path) if path else None
    clean = None if uncommitted is None else not uncommitted
    behind = _git(["rev-list", "--count", f"{listing.owner_tip}..{tip}"], listing.root)
    ahead = int(behind) if behind and behind.isdecimal() else None
    stamp = _git(["log", "-1", "--format=%ct", tip], listing.root)
    age = max(0, int(listing.now - int(stamp))) if stamp and stamp.isdecimal() else None
    state = _row_state(kind, texts, _RowFacts(held, carried, clean, ahead))
    ready = state == texts["worktrees"]["states"]["ready"]
    shown = _display_path(Path(path), Path(listing.main) / _WORKTREES_DIR) if path else ""
    return WorktreeRow(
        path=path,
        shown=shown,
        branch=branch or texts["worktrees"]["detached"],
        kind=kind,
        ergon=unit.ergon if unit else "",
        athlos=unit.athlos if unit else "",
        clean=clean,
        ahead=ahead,
        age_seconds=age,
        carried=carried,
        differing=differing,
        state=state,
        removable=state in (texts["worktrees"]["states"]["carried"], texts["worktrees"]["states"]["backup"]),
        subject=(_git(["log", "-1", "--format=%s", tip], listing.root) or "") if ready else "",
    )


def _branch_only(root: Path, sheltered: frozenset[str]) -> list[tuple[str, str]]:
    """The ``_aitna/`` branches with no worktree, as (branch, tip), by branch name."""
    out = _git(["for-each-ref", "--format=%(objectname) %(refname)", _HEADS + _BRANCH_NAMESPACE], root) or ""
    found: list[tuple[str, str]] = []
    for line in out.split("\n"):
        tip, _, ref = line.partition(" ")
        branch = ref.removeprefix(_HEADS)
        if tip and branch and branch not in sheltered:
            found.append((branch, tip))
    return sorted(found)


def list_worktrees(root: Path, texts: Mapping, context: LeaseContext) -> list[WorktreeRow]:
    """Every worktree of the repository and every ``_aitna/`` branch that has none, as rows; reads only.

    The owner's checkout is git's first entry and comes first; a linked worktree is an *athlos* when its
    branch is in the ``_aitna/<id>-<name>.<n>`` namespace and a *harness* one otherwise; a branch whose
    worktree is gone is a backup. Each row carries a state; one is removable only when it is a carried
    athlos worktree or a carried backup branch (never one a live lease holds).

    Raises:
        ParkError: ``root`` is not in a git repository, or the repository has no checkout of its own.
    """
    out = _git(["worktree", "list", "--porcelain"], root, strip=False)
    entries = parse_worktree_list(out) if out else []
    if not entries:
        raise _error(texts, "no_repository", path=root)
    if entries[0].bare:
        raise _error(texts, "no_main_checkout", path=entries[0].path)
    main = entries[0]
    kinds = texts["worktrees"]["kinds"]
    listing = _Listing(root, main.path, main.head, _unit_records(root, texts, context), texts, context.now)
    linked = [entry for entry in entries[1:] if not entry.bare]
    rows = [_worktree_row(listing, main.path, main.branch, main.head, kinds["main"])]
    for entry in linked:
        kind = kinds["athlos"] if branch_unit(entry.branch) else kinds["harness"]
        rows.append(_worktree_row(listing, entry.path, entry.branch, entry.head, kind))
    rows[1:] = sorted(rows[1:], key=lambda row: row.shown)
    sheltered = frozenset(entry.branch for entry in entries if entry.branch)
    for branch, tip in _branch_only(root, sheltered):
        rows.append(_worktree_row(listing, "", branch, tip, kinds["branch_only"]))
    return rows


def _yes_no(texts: Mapping, *, value: bool | None) -> str:
    if value is None:
        return texts["empty_cell"]
    return texts["worktrees"]["yes"] if value else texts["worktrees"]["no"]


def _table_cells(row: WorktreeRow, texts: Mapping) -> list[str]:
    empty = texts["empty_cell"]
    return [
        row.shown or empty,
        row.branch,
        row.kind,
        row.ergon or empty,
        row.athlos or empty,
        _yes_no(texts, value=row.clean),
        empty if row.ahead is None else str(row.ahead),
        empty if row.age_seconds is None else _relative_age(row.age_seconds),
        row.state,
    ]


def format_worktrees(rows: Sequence[WorktreeRow], texts: Mapping) -> list[str]:
    """The table of ``worktrees`` as aligned lines, the header first; an absent value is the empty cell."""
    spec = texts["worktrees"]
    table = [list(spec["columns"])]
    table.extend(_table_cells(row, texts) for row in rows)
    widths = [max(len(line[column]) for line in table) for column in range(len(table[0]))]
    lines = []
    for line in table:
        padded = [cell.ljust(width) for cell, width in zip(line[:-1], widths[:-1], strict=True)]
        lines.append(spec["separator"].join([*padded, line[-1]]))
    return lines


def _double_quoted(text: str) -> str:
    """``text`` made literal inside double quotes: the four characters the shell still reads there are escaped."""
    return re.sub(r'([\\"$`])', r"\\\1", text)


def carry_commands(rows: Sequence[WorktreeRow], main: str, texts: Mapping) -> list[list[str]]:
    """The squash that carries each ready row into the owner's branch, one block of commands per row.

    The tool prints them and never runs them (ADR 0029 D09): the owner starts every carry. The message
    is the subject of the branch's last commit, which the agent may rewrite before the owner commits.
    """
    spec = texts["worktrees"]
    ready = spec["states"]["ready"]
    return [
        [
            jsondata.fill(spec["carry_cd"], {"path": shlex.quote(main)}),
            jsondata.fill(spec["carry_squash"], {"branch": shlex.quote(row.branch)}),
            jsondata.fill(spec["carry_commit"], {"message": _double_quoted(row.subject)}),
        ]
        for row in rows
        if row.state == ready
    ]


def removal_commands(rows: Sequence[WorktreeRow], texts: Mapping) -> list[str]:
    """The commands that remove each removable row: the tool prints them and never runs them.

    A worktree goes with ``git worktree remove``, which refuses while anything in it is uncommitted; a
    backup branch goes with ``-D``, because a squash leaves it unmerged in git's eyes.
    """
    spec = texts["worktrees"]
    commands: list[str] = []
    for row in rows:
        if not row.removable:
            continue
        if row.path:
            commands.append(jsondata.fill(spec["command_worktree"], {"path": shlex.quote(row.path)}))
        else:
            commands.append(jsondata.fill(spec["command_branch"], {"branch": shlex.quote(row.branch)}))
    return commands


def select_worktrees(rows: Sequence[WorktreeRow], target: str) -> list[WorktreeRow]:
    """The rows a target names: a branch (with or without ``_aitna/``) or an athlos key such as ``C190.1``."""
    return [row for row in rows if target in (row.branch, row.athlos) or row.branch == _BRANCH_NAMESPACE + target]


def worktree_verdict(row: WorktreeRow, texts: Mapping) -> str:
    """The one line that says whether the branch of ``row`` is carried and, if not, what differs."""
    spec = texts["worktrees"]
    if row.carried:
        return jsondata.fill(spec["verdict_carried"], {"branch": row.branch})
    if row.differing is None:
        paths = spec["verdict_unreadable"]
    else:
        shown = row.differing[: spec["verdict_paths"]]
        more = spec["verdict_more"] if len(row.differing) > len(shown) else ""
        paths = ", ".join(shown) + more
    return jsondata.fill(spec["verdict_not_carried"], {"branch": row.branch, "paths": paths})


# --------------------------------------------------------------------------------------
# the export: the ergon's files, its leases left out (ADR 0028 D07, branch B10)
# --------------------------------------------------------------------------------------


def export_ergon(ergon: Path, out: Path, texts: Mapping) -> Path:
    """Write the ergon's files to one bundle file, its leases left out.

    The bundle is plain text: the file's path, then its content, so any language reads it.
    """
    lines = [jsondata.fill(texts["export"]["title"], {"ergon": ergon.name}), ""]
    for path in sorted(item for item in ergon.rglob("*") if item.is_file()):
        if path.name == _HOLDER_FILE:
            continue
        lines.append(jsondata.fill(texts["export"]["file_header"], {"path": path.relative_to(ergon).as_posix()}))
        lines.append(path.read_text(encoding="utf-8").rstrip("\n"))
        lines.append(texts["export"]["end"])
        lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------------------
# the local ids: ``_T<n>`` counted over the ergons, live and closed, never reused
# --------------------------------------------------------------------------------------


def _legacy_local_ids(root: Path) -> list[int]:
    """The ``_T<n>`` numbers the retired local index ``<DEV>/.local/TASKS.md`` still holds.

    Read as legacy input and never written (ADR 0028 D12). The index sits with the ergons in the
    main checkout, so a linked worktree reads that one. No such file holds no number.
    """
    index = local_root(git_common_root(root)) / _LEGACY_INDEX_FILE
    if not index.is_file():
        return []
    rows = (_LEGACY_ROW_RE.match(line) for line in index.read_text(encoding="utf-8").split("\n"))
    return [int(match.group(1)) for match in rows if match is not None]


def next_local_id(root: Path) -> str:
    """The next free local id: ``_T<n>`` counted over every ergon, live and closed, and the legacy index."""
    numbers = [0, *_legacy_local_ids(root)]
    for name in _ergon_names(root) + _ergon_names(root, closed=True):
        match = _LOCAL_ID_RE.match(_ergon_id(name))
        if match is not None:
            numbers.append(int(match.group(1)))
    return f"_T{max(numbers) + 1}"


# --------------------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------------------


def _add_holder_flags(command: argparse.ArgumentParser) -> None:
    """The flags that name the holder of a lease: harness and session."""
    command.add_argument("--harness", default="")
    command.add_argument("--session-id", default="")


def _add_note_commands(commands: Any, common: argparse.ArgumentParser) -> None:
    """The commands that write or read an ergon's own note: write, unpark, digest, list."""
    write = commands.add_parser("write", parents=[common], help="Park a piece of work.", allow_abbrev=False)
    write.add_argument("id")
    write.add_argument("--name", required=True)
    write.add_argument("--goal", required=True)
    write.add_argument("--next", dest="next_action", required=True)
    write.add_argument("--plan", default="")
    write.add_argument("--row", default="")
    write.add_argument("--owned-path", action="append", default=[])
    write.add_argument("--check", action="append", default=[])
    write.add_argument("--unverified", action="append", default=[])
    write.add_argument("--decision", action="append", default=[])
    write.add_argument("--answer", action="append", default=[])
    write.add_argument("--agent", action="append", default=[])
    write.add_argument("--readiness", default="")
    write.add_argument("--origin", default="")
    write.add_argument("--commit-message", default="")
    _add_holder_flags(write)

    unpark = commands.add_parser("unpark", parents=[common], help="Resume a parked ergon.", allow_abbrev=False)
    unpark.add_argument("id")
    _add_holder_flags(unpark)

    digest_cmd = commands.add_parser("digest", parents=[common], help="Print the capped digest.", allow_abbrev=False)
    digest_cmd.add_argument("id")
    digest_cmd.add_argument("--cap", type=int, default=None)

    listing = commands.add_parser("list", parents=[common], help="List the ergons.", allow_abbrev=False)
    listing.add_argument("--plan", default="")
    listing.add_argument("--task", default="")
    listing.add_argument("--state", default="")
    listing.add_argument("--closed", action="store_true")


def _add_unit_commands(commands: Any, common: argparse.ArgumentParser) -> None:
    """The commands that act on one unit: hold, release, athlos, active, worktrees, close, export, local-id."""
    hold = commands.add_parser("hold", parents=[common], help="Take the lease of a unit.", allow_abbrev=False)
    hold.add_argument("id")
    hold.add_argument("--number", type=int, default=None)
    hold.add_argument("--takeover", action="store_true")
    _add_holder_flags(hold)

    release = commands.add_parser("release", parents=[common], help="Release the lease of a unit.", allow_abbrev=False)
    release.add_argument("id")
    release.add_argument("--number", type=int, default=None)

    athlos = commands.add_parser("athlos", parents=[common], help="Write an athlos's own file.", allow_abbrev=False)
    athlos.add_argument("id")
    athlos.add_argument("--number", type=int, required=True)
    athlos.add_argument("--step", action="append", default=[])
    athlos.add_argument("--done", action="store_true")
    _add_holder_flags(athlos)

    commands.add_parser("active", parents=[common], help="Print the unit this session is in.", allow_abbrev=False)

    worktrees = commands.add_parser(
        "worktrees",
        parents=[common],
        help="List the worktrees and backup branches by state; with a branch or athlos key, say if it is carried.",
        allow_abbrev=False,
    )
    worktrees.add_argument("target", nargs="?", default="")

    close = commands.add_parser(
        "close", parents=[common], help="Close an ergon and move it to the closed folder.", allow_abbrev=False
    )
    close.add_argument("id")
    _add_holder_flags(close)

    export = commands.add_parser(
        "export", parents=[common], help="Write the ergon to one bundle file.", allow_abbrev=False
    )
    export.add_argument("id")
    export.add_argument("--out", required=True)

    commands.add_parser("local-id", parents=[common], help="Print the next free local id, _T<n>.", allow_abbrev=False)


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common.add_argument(
        "--root",
        "--project-root",
        dest="root",
        type=Path,
        help="Project root. Defaults to the nearest parent holding AGENTS.md beside the dev layer.",
    )
    common.add_argument(
        "--machine",
        default="",
        help="The machine this session acts as. Defaults to the host's name.",
    )
    parser = argparse.ArgumentParser(description="Park work into an ergon and resume it.", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    _add_note_commands(commands, common)
    _add_unit_commands(commands, common)
    return parser


def _session_refs(args: argparse.Namespace, texts: Mapping) -> tuple[SessionRef, ...]:
    if not args.harness:
        if args.session_id or args.machine:
            raise _error(texts, "session_needs_harness")
        return ()
    return (SessionRef(args.harness.strip(), args.session_id.strip(), args.machine.strip()),)


def _stripped(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(value.strip() for value in values)


def _fields_from(args: argparse.Namespace, texts: Mapping) -> ParkFields:
    return ParkFields(
        id=args.id.strip(),
        name=args.name.strip(),
        next_action=args.next_action.strip(),
        plan=args.plan.strip(),
        row=args.row.strip(),
        owned_paths=_stripped(args.owned_path),
        sessions=_session_refs(args, texts),
        origin=args.origin.strip(),
        readiness=args.readiness.strip(),
    )


def _body_from(args: argparse.Namespace) -> ParkBody:
    return ParkBody(
        goal=args.goal.strip(),
        decisions=_stripped(args.decision),
        answers=_stripped(args.answer),
        checks=_stripped(args.check),
        unverified=_stripped(args.unverified),
        agents=_stripped(args.agent),
    )


def _project_root(explicit: Path | None, texts: Mapping) -> Path:
    """The root the command works in; a missing project root is refused, as every command reads or writes under it."""
    root, notice = resolve_project_root(explicit)
    if notice:
        raise ParkError(notice)
    if explicit is not None and not root.is_dir():
        raise _error(texts, "no_project_root_dir", path=root)
    return root


def _holder_of(args: argparse.Namespace, run: _Run) -> Holder:
    """The holder a command acts as: the flags, or the machine it runs on, and the folder it works in.

    The worktree is the folder the process started in, read once at the entry (``_run``) and carried
    on the run — a command never asks the file system where it is from inside the logic.
    """
    return Holder(
        harness=args.harness.strip(),
        session_id=args.session_id.strip(),
        machine=args.machine.strip() or run.machine,
        worktree=str(run.cwd),
    )


def _unit_of(ergon: Path, number: int | None, texts: Mapping) -> Path:
    """The folder of the unit a command acts on: the ergon root, or one of its athlos."""
    if number is None:
        return ergon
    athlos_id = athlos_id_of(_ergon_id(ergon.name), number)
    folder = athlos_folder(ergon, number)
    if folder is None:
        raise _error(texts, "no_athlos", ergon=ergon.name, athlos=athlos_id)
    return folder


def _machine_label() -> str:
    """The label of the machine this session runs on."""
    with contextlib.suppress(OSError):
        return socket.gethostname()
    return ""


def _read_resume(ergon: Path, texts: Mapping) -> str:
    """The resume prompt of an ergon, and the proof that its note reads: nothing is held yet.

    Raises:
        ParkError: the ergon has no ``RESUME.md``, was never parked, or its note does not parse.
    """
    resume = ergon / _RESUME_FILE
    if not resume.is_file():
        raise _error(texts, "no_resume", ergon=ergon.name)
    read_note(ergon, texts)
    return resume.read_text(encoding="utf-8").rstrip("\n")


def _resume_text(prompt: str, ergon: Path, root: Path, texts: Mapping, machine: str) -> str:
    """The resume prompt of an ergon, followed by a blank line and its capped digest."""
    return prompt + "\n\n" + digest(ergon, texts["default_cap"], root, texts, machine)


def _planned_athlos(ergon: Path, plan: Plan, athlos_id: str, texts: Mapping) -> AthlosLine:
    """The usable athlos line of a plan for ``athlos_id``: it names a label and a result for ``ATHLOS.md``.

    Raises:
        ParkError: the plan has no such athlos, or the line has no label or no result.
    """
    line = next((item for item in plan.athlos if item.id == athlos_id), None)
    if line is None:
        raise _error(texts, "no_athlos", ergon=ergon.name, athlos=athlos_id)
    if not line.label:
        raise _error(texts, "athlos_label", id=athlos_id)
    if not line.result:
        raise _error(texts, "bad_plan", ergon=ergon.name, reason=f"athlos {athlos_id} has no result")
    return line


def _write_athlos(run: _Run, args: argparse.Namespace) -> None:
    """Write an athlos's own file: create it from the plan's athlos line, then add its steps.

    Everything that can be refused is checked before the lease is taken or a file is touched. The
    first write into an athlos's folder takes its lease, so two sessions never write one file. The
    file lands in the folder of the athlos's number; a record written in the retired ``jobs/``
    layout is carried there by this write (ADR 0029 D11, D12). The plan's shared-path warnings go
    to stderr.

    Raises:
        ParkError: the ergon has no plan, the plan has no usable line for the athlos, or the athlos
            is held.
    """
    root, texts, context = run.root, run.texts, run.lease
    ergon = find_ergon(root, args.id.strip(), texts)
    ergon_id = _ergon_id(ergon.name)
    athlos_id = athlos_id_of(ergon_id, args.number)
    plan = read_plan(ergon, texts)
    if plan is None:
        raise _error(texts, "no_plan", ergon=ergon.name)
    folder = athlos_folder(ergon, args.number)
    doc = read_athlos_doc(athlos_file_of(folder), texts) if folder is not None else None
    if doc is None:
        line = _planned_athlos(ergon, plan, athlos_id, texts)
        doc = athlos_doc_for(line, ergon_id, ergon.name[len(ergon_id) + 1 :], plan, run.cwd)
        _check_athlos_doc(doc, ergon.name, texts)
    folder = move_athlos_folder(ergon, args.number, folder)
    acquire_lease(folder, _holder_of(args, run), texts, context)
    steps = doc.steps + tuple((text, False) for text in _stripped(args.step))
    write_athlos_doc(folder, AthlosDoc(header=doc.header, steps=steps, done=doc.done or args.done), texts)
    print(_display_path(folder, root))
    for warning in shared_path_warnings(plan, texts):
        print(warning, file=sys.stderr)


def _print_active(root: Path, texts: Mapping, context: LeaseContext) -> None:
    """Print the unit this session is in: the athlos of the worktree it works in."""
    found = active_unit(root, texts)
    if found is None:
        print(texts["active"]["none"])
        return
    ergon, ergon_id, number = found
    athlos_id = athlos_id_of(ergon_id, number)
    folder = find_athlos_folder(ergon, athlos_id, texts)
    unit = folder if folder is not None else ergon
    lease = read_lease(unit, texts)
    state = unit_state(unit, texts, context)
    path = _display_path(unit, root)
    print(
        jsondata.fill(
            texts["active"]["line"],
            {
                "kind": "athlos" if folder is not None else "ergon",
                "id": athlos_id if folder is not None else ergon_id,
                "name": unit.name,
                "state": state,
                "holder": lease.holder.label() if lease is not None else texts["empty_cell"],
                "path": path,
            },
        )
    )


@dataclass(frozen=True)
class _Run:
    """What every command of one invocation shares: the root, the texts, the lease clock, the machine, the folder."""

    root: Path
    texts: Mapping
    lease: LeaseContext
    machine: str
    cwd: Path


def _in_main_checkout(cwd: Path) -> bool:
    """Whether ``cwd`` is in the main checkout of a repository; false in a linked worktree or outside git.

    A worktree is linked when its git directory differs from the common one the main checkout keeps.
    """
    layout = _git(["rev-parse", "--git-dir", "--git-common-dir"], cwd)
    paths = layout.split("\n") if layout else []
    if len(paths) != 2:  # noqa: PLR2004 — the git directory and the common one
        return False
    git_dir, common_dir = (Path(cwd, path).resolve() for path in paths)
    return git_dir == common_dir


def _status_paths(cwd: Path) -> tuple[str, ...]:
    """The paths ``git status`` reports as changed in ``cwd``, once each; a rename or a copy by its new path only.

    The origin of a staged rename is no longer in the tree, so ``git add -- <origin>`` fails; the new path
    is what the block stages. None if git cannot say. The paths are relative to the repository root.
    """
    out = _git(["status", "--porcelain", "-z", "--untracked-files=all"], cwd, strip=False)
    if not out:
        return ()
    paths: list[str] = []
    entries = iter(out.split("\0"))
    for entry in entries:
        if not entry:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":  # a rename or a copy carries its origin as the next entry
            next(entries, "")
    return tuple(dict.fromkeys(path for path in paths if path))


def _toplevel_paths(paths: Sequence[str], root: Path, toplevel: str) -> tuple[str, ...]:
    """``paths`` given relative to the project ``root``, as paths relative to the repository ``toplevel``.

    The block enters the toplevel, so an owned path of a project whose root is a subdirectory of the
    repository gains that subdirectory as its prefix. An absolute path stays as it is.
    """
    prefix = Path(os.path.relpath(root.resolve(), Path(toplevel).resolve())).as_posix()
    if prefix == ".":
        return tuple(paths)
    return tuple(
        path if Path(path).is_absolute() else posixpath.normpath(posixpath.join(prefix, path)) for path in paths
    )


def block_commit_lines(paths: Sequence[str], message: str, toplevel: str, resume: str, texts: Mapping) -> list[str]:
    """The block commit as printed text, in paragraphs, or nothing when no path is left to stage.

    ``paths`` are the ones to stage (the caller picks the ergon's owned ones, else the changed ones). ``git
    status`` reports them relative to the repository root, so the first command enters ``toplevel``; the
    block works from any directory. The tool prints this and never runs it (ADR 0031 D04); the reminder
    names where the hand-off prompt points (D05).
    """
    spec = texts["block_commit"]
    paths = tuple(dict.fromkeys(paths))
    if not paths:
        return []
    text = message.strip()
    commands = [
        spec["heading"],
        jsondata.fill(spec["cd"], {"path": shlex.quote(toplevel)}),
        jsondata.fill(spec["add"], {"paths": " ".join(shlex.quote(path) for path in paths)}),
        jsondata.fill(spec["commit"], {"message": _double_quoted(text) if text else spec["placeholder"]}),
    ]
    closing = [] if text else [spec["propose"]]
    closing.append(jsondata.fill(spec["reminder"], {"resume": resume}))
    return ["\n".join(commands), "\n".join(closing)]


def _block_commit(args: argparse.Namespace, ergon: Path, run: _Run) -> list[str]:
    """The block commit this write prints: the controlling style, in the main checkout only (ADR 0031 D02)."""
    style = work_style.resolve(run.root, args.session_id.strip() or None, work_style.read_data())
    if style.style != run.texts["block_commit"]["style"] or not _in_main_checkout(run.cwd):
        return []
    resume = _display_path(ergon / _RESUME_FILE, run.root)
    toplevel = _git(["rev-parse", "--show-toplevel"], run.cwd) or str(run.cwd)
    owned = _stripped(args.owned_path)
    paths = _toplevel_paths(owned, run.root, toplevel) if owned else _status_paths(run.cwd)
    return block_commit_lines(paths, args.commit_message, toplevel, resume, run.texts)


def _cmd_write(args: argparse.Namespace, run: _Run) -> int:
    fields = _fields_from(args, run.texts)
    body = _body_from(args)
    ergon = _ergon_folder(run.root, fields)
    holder = _holder_of(args, run)
    check_fields(fields, run.texts)
    check_body(body, run.texts)
    refuse_ergon_conflict(fields, run.root, run.texts)
    _refuse_foreign_lease(ergon, holder, run)
    free = read_lease(ergon, run.texts) is None
    # The write holds the ergon while it writes: a lease taken since the check is refused, not overwritten.
    lease = acquire_lease(ergon, holder, run.texts, run.lease)
    try:
        write_ergon(fields, body, run.root, run.texts, run.cwd)
    except BaseException:
        if free:
            _release_own_lease(ergon, lease, run.texts)
            _remove_if_empty(ergon)
        raise
    _release_own_lease(ergon, lease, run.texts)
    print(_display_path(ergon, run.root))
    for paragraph in _block_commit(args, ergon, run):
        print()
        print(paragraph)
    return 0


def _release_own_lease(unit: Path, lease: Lease, run_texts: Mapping) -> None:
    """Release the lease of a unit when it is still the one this session took; another's is never removed."""
    current = read_lease(unit, run_texts)
    if current is not None and current.holder == lease.holder:
        release_lease(unit)


def _ergon_folder(root: Path, fields: ParkFields) -> Path:
    """The folder an ergon has, or the one it would have; the name conflict is the writer's to refuse."""
    return ergon_root(root) / f"{fields.id}-{fields.name}"


def _refuse_foreign_lease(unit: Path, holder: Holder, run: _Run) -> None:
    """Refuse to write a unit another session holds, live or stale.

    The lease is what keeps one file out of two writers' hands, so a write into a held unit is
    refused with the holder named. A stale lease is refused too: it is offered to the owner for a
    takeover (``hold --takeover``), which keeps the replaced holder in the note, and a write never
    takes it silently (ADR 0028 D09).

    Raises:
        ParkError: another session holds the unit.
    """
    lease = read_lease(unit, run.texts)
    if lease is None or lease.holder.same_as(holder):
        return
    code = "held_write_stale" if lease_is_stale(lease, run.lease) else "held_write"
    raise _error(run.texts, code, unit=unit.name, holder=lease.holder.label())


def _cmd_unpark(args: argparse.Namespace, run: _Run) -> int:
    ergon = find_ergon(run.root, args.id.strip(), run.texts)
    prompt = _read_resume(ergon, run.texts)  # everything that can be refused, before a lease is taken
    acquire_lease(ergon, _holder_of(args, run), run.texts, run.lease)
    print(_resume_text(prompt, ergon, run.root, run.texts, run.machine))
    return 0


def _cmd_digest(args: argparse.Namespace, run: _Run) -> int:
    cap = run.texts["default_cap"] if args.cap is None else args.cap
    if cap < 0:
        raise _error(run.texts, "bad_cap", value=cap)
    print(digest(find_ergon(run.root, args.id.strip(), run.texts), cap, run.root, run.texts, run.machine))
    return 0


def _cmd_list(args: argparse.Namespace, run: _Run) -> int:
    query = ListQuery(args.plan.strip(), args.task.strip(), args.state.strip(), args.closed)
    ergons, units = list_ergons(run.root, query, run.texts, run.lease)
    if ergons:
        lines: list[str] = []
        for summary in ergons:
            lines.append(format_summary(summary, run.texts))
            lines.extend(format_athlos(item, run.texts) for item in units if item.id.startswith(f"{summary.id}."))
        print("\n".join(lines))
    elif not _ergon_names(run.root):
        folder = _display_path(ergon_root(run.root), run.root)
        print(jsondata.fill(run.texts["list"]["empty"], {"path": folder}))
    else:
        print(run.texts["list"]["no_match"])
    return 0


def _cmd_hold(args: argparse.Namespace, run: _Run) -> int:
    ergon = find_ergon(run.root, args.id.strip(), run.texts)
    unit = _unit_of(ergon, args.number, run.texts)
    holder = _holder_of(args, run)
    if args.takeover:
        _print_replaced_paths(unit, holder, run)
    lease = acquire_lease(unit, holder, run.texts, run.lease, takeover=args.takeover)
    print(f"{unit.name}: {lease.holder.label()}")
    return 0


def _print_replaced_paths(unit: Path, holder: Holder, run: _Run) -> None:
    """Name the uncommitted paths of the holder a takeover would replace, before anything else is done.

    Nothing is printed when the unit is free, is this session's own, or the replaced worktree is clean;
    a worktree that cannot be read is said so, so a silent line means a clean one.
    """
    existing = read_lease(unit, run.texts)
    if existing is None or existing.holder.same_as(holder):
        return
    paths = git_uncommitted_paths(existing.holder.worktree)
    spec = run.texts["takeover"]
    label = existing.holder.label()
    if paths is None:
        print(jsondata.fill(spec["unreadable"], {"holder": label}))
    elif paths:
        print(jsondata.fill(spec["uncommitted"], {"holder": label, "paths": ", ".join(paths)}))


def _cmd_release(args: argparse.Namespace, run: _Run) -> int:
    ergon = find_ergon(run.root, args.id.strip(), run.texts)
    unit = _unit_of(ergon, args.number, run.texts)
    if read_lease(unit, run.texts) is None:
        raise _error(run.texts, "no_holder", unit=unit.name)
    release_lease(unit)
    print(unit.name)
    return 0


def _cmd_athlos(args: argparse.Namespace, run: _Run) -> int:
    _write_athlos(run, args)
    return 0


def _cmd_active(_args: argparse.Namespace, run: _Run) -> int:
    _print_active(run.root, run.texts, run.lease)
    return 0


def _cmd_worktrees(args: argparse.Namespace, run: _Run) -> int:
    rows = list_worktrees(run.root, run.texts, run.lease)
    target = args.target.strip()
    if target:
        return _print_worktree_verdict(select_worktrees(rows, target), target, run)
    sections = [format_worktrees(rows, run.texts)]
    sections += carry_commands(rows, rows[0].path, run.texts)
    removals = removal_commands(rows, run.texts)
    if removals:
        sections.append(removals)
    print("\n\n".join("\n".join(section) for section in sections))
    return 0


def _print_worktree_verdict(rows: Sequence[WorktreeRow], target: str, run: _Run) -> int:
    """Print the rows a target names and one verdict line each; the exit code is 0 only when all are carried."""
    if not rows:
        print(jsondata.fill(run.texts["worktrees"]["verdict_missing"], {"target": target}))
        return 1
    lines = format_worktrees(rows, run.texts)
    lines += [worktree_verdict(row, run.texts) for row in rows]
    print("\n".join(lines))
    return 0 if all(row.carried for row in rows) else 1


def _cmd_close(args: argparse.Namespace, run: _Run) -> int:
    ergon = find_ergon(run.root, args.id.strip(), run.texts)
    _refuse_live_foreign_lease(ergon, _holder_of(args, run), run)
    closed = ergon_root(run.root) / _CLOSED_DIR
    target = closed / ergon.name
    if target.exists():
        raise _error(run.texts, "close_exists", ergon=ergon.name, target=_display_path(target, run.root))
    closed.mkdir(parents=True, exist_ok=True)
    try:
        ergon.rename(target)
    except OSError as exc:
        raise _error(
            run.texts, "close_failed", ergon=ergon.name, reason=errno.errorcode.get(exc.errno or 0, "OSError")
        ) from exc
    release_leases(target)  # after the move, so a close that is refused or fails changes nothing
    print(_display_path(target, run.root))
    return 0


def _refuse_live_foreign_lease(ergon: Path, holder: Holder, run: _Run) -> None:
    """Refuse to close an ergon while a live lease of another session is in it, the plan's or an athlos's.

    A stale lease holds nothing, and the closing session's own leases are its to release.

    Raises:
        ParkError: another session holds a unit of the ergon; the message names the unit and the holder.
    """
    for unit in (ergon, *_athlos_folders(ergon)):
        lease = read_lease(unit, run.texts)
        if lease is None or lease_is_stale(lease, run.lease) or lease.holder.same_as(holder):
            continue
        raise _error(run.texts, "close_held", unit=unit.name, holder=lease.holder.label())


def _cmd_export(args: argparse.Namespace, run: _Run) -> int:
    ergon = find_ergon(run.root, args.id.strip(), run.texts)
    export_ergon(ergon, Path(args.out), run.texts)
    print(Path(args.out).as_posix())
    return 0


def _cmd_local_id(_args: argparse.Namespace, run: _Run) -> int:
    print(next_local_id(run.root))
    return 0


def _command_handlers() -> Mapping[str, Callable[[argparse.Namespace, _Run], int]]:
    """The command name to its handler; one place, so a new command is one line and one function."""
    return {
        "write": _cmd_write,
        "unpark": _cmd_unpark,
        "digest": _cmd_digest,
        "list": _cmd_list,
        "hold": _cmd_hold,
        "release": _cmd_release,
        "athlos": _cmd_athlos,
        "active": _cmd_active,
        "worktrees": _cmd_worktrees,
        "close": _cmd_close,
        "export": _cmd_export,
        "local-id": _cmd_local_id,
    }


def _effective_machine(args: argparse.Namespace) -> str:
    """The machine this session acts as: the flag when given, the host's label otherwise.

    One value serves both the holder it records and the staleness comparison, so a session
    that names its machine is never told its own lease came from another machine.
    """
    named = str(getattr(args, "machine", "") or "").strip()
    return named or _machine_label()


def _run(args: argparse.Namespace, texts: Mapping) -> int:
    root = _project_root(args.root, texts)
    machine = _effective_machine(args)
    run = _Run(
        root=root,
        texts=texts,
        lease=LeaseContext(now=time.time(), stale_hours=texts["stale_after_hours"], machine=machine),
        machine=machine,
        cwd=Path.cwd(),  # read once here; a command below never asks the file system where it is
    )
    return _command_handlers()[args.command](args, run)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; a failure is one stderr line and exit 1."""
    args = _build_parser().parse_args(argv)
    texts = _texts()
    try:
        return _run(args, texts)
    except ParkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
