#!/usr/bin/env python3
"""The park helper: hold, write, resume, digest and list the kits of parked work.

A *kit* is the folder ``<dev root>/.ergon/<id>-<name>/`` of one piece of work. Its plan is
``PLAN.md``; its units are the plan itself (the kit root) and its jobs (``jobs/<n>-<name>/``).
Parking a unit writes two files into it, atomically: ``PARK.md``, the park note — a small
machine-readable header between two ``---`` lines and a Markdown body of facts — and
``RESUME.md``, the harness-neutral prompt a successor starts from. There is no local index
anymore: a kit is its own record, and ``park list`` is the index (ADR 0028 D12).

    akmon tool park/park write C186 --name holders-jobs --goal "…" --next "…"
    akmon tool park/park hold C186 --number 1 --harness claude --session-id abc
    akmon tool park/park job C186 --number 1 --step "…"
    akmon tool park/park unpark C186        # takes the lease, prints RESUME.md and the digest
    akmon tool park/park digest C186 [--cap N]
    akmon tool park/park list [--plan ID] [--task ID] [--state S] [--closed]
    akmon tool park/park active             # the unit this session is in, read from the disk
    akmon tool park/park close C186         # moves the kit to the closed folder
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
note without a lease makes it *parked*, neither makes it *not started*, and a job whose
``JOB.md`` says ``done`` is *done*. The branch and the revisions of a note are read from git
when the note is written, and the note records when it was written.

The helper writes no date into a tracked document, never reads a transcript and never pushes.
Stdlib-only, and nothing happens at import time: tools run before a virtual environment exists.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import errno
import os
import re
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

from common import jsondata
from common.project_root import ergon_root, git_common_root, local_root, resolve_project_root

_SECONDS_PER_DAY = 86400
_SECONDS_PER_HOUR = 3600
_PARK_FILE = "PARK.md"
_RESUME_FILE = "RESUME.md"
_PLAN_FILE = "PLAN.md"
_HOLDER_FILE = "HOLDER"
_JOB_FILE = "JOB.md"
_SESSIONS_FILE = "SESSIONS"
_HEADER_FENCE = "---"
_ID_RE = re.compile(r"^(?:[A-Z]\d+|_T\d+)$")  # ADR 0002 typed id, and a local id's _T<n> (ADR 0028 D12)
_JOB_ID_RE = re.compile(r"^((?:[A-Z]\d+|_T\d+))\.(\d+)$")
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_KIT_RE = re.compile(r"^((?:[A-Z]\d+|_T\d+))-([a-z0-9]+(?:-[a-z0-9]+)*)$")
_KEY_RE = re.compile(r"^([a-z_]+):(?: (.*))?$")
_PURPOSE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SLUG_MAX = 40
_LOCAL_ID_RE = re.compile(r"^_T(\d+)$")
_LEGACY_INDEX_FILE = "TASKS.md"  # the retired local index, in ``<dev root>/.local/``
_LEGACY_ROW_RE = re.compile(r"^- _T([0-9]+)(?:[ \t]|$)")  # one of its rows: ``- _T6 · ...``
_GIT_TIMEOUT_SECONDS = 10
_GIT_REVISIONS = 5
_STEPS_HEADING = "## Steps"
_DONE_MARKER = "done"
_STEP_UNDONE = "- [ ] "
_STEP_DONE = "- [x] "
_JOBS_DIR = "jobs"
_CLOSED_DIR = ".closed"
_WORKTREES_DIR = ".worktrees"
_TASK_SEPARATOR = "·"
_FIELD_SEPARATOR = ","
_PATH_SEPARATOR = "/"
_JOBS_HEADING = "Jobs"
_JOB_SOURCE_PARTS = 4  # kit folder, ``jobs``, job folder, ``JOB.md``
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
    job: str = ""
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
class JobLine:
    """One job line of ``PLAN.md``: the structure of a job, never its state (ADR 0028 D08)."""

    id: str
    number: int
    label: str
    tasks: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    harness: str = ""
    result: str = ""


@dataclass(frozen=True)
class PlanHeader:
    """The header of ``PLAN.md``: the kit's id, name, title and the tasks it carries."""

    id: str = ""
    name: str = ""
    title: str = ""
    tasks: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    """A plan: its header and its job lines."""

    header: PlanHeader = PlanHeader()
    jobs: tuple[JobLine, ...] = ()


@dataclass(frozen=True)
class JobDoc:
    """A job's own file ``JOB.md``: its steps with their done marks, and whether it is done."""

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
class KitSummary:
    """One line of ``list``: what a kit says of itself, read from its folder."""

    id: str
    name: str
    state: str
    plan: str
    next_action: str
    decisions: int
    branch: str
    age_days: int | None
    unreadable: str = ""  # why the kit's files could not be read; the other fields are then empty


@dataclass(frozen=True)
class JobSummary:
    """One job line of ``list``: what a job says of itself, read from its folder."""

    id: str
    name: str
    state: str
    tasks: tuple[str, ...]
    next_action: str
    branch: str
    age_days: int | None


@dataclass(frozen=True)
class ListQuery:
    """The filters of ``list``; an empty one matches every kit."""

    plan: str = ""
    task: str = ""
    state: str = ""
    closed: bool = False


# Header keys in their written order, and which of them hold a list: the one table the renderer and
# the parser share. ``next_action`` is written as ``next``.
_SCALAR_KEYS = ("id", "name", "plan", "job", "row", "branch", "next", "origin", "readiness", "written")
_LIST_KEYS = ("revisions", "owned_paths", "tasks", "sessions")
_HEADER_ORDER = (
    "id",
    "name",
    "plan",
    "job",
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
# The keys of the lease file ``HOLDER``, in their written order.
_LEASE_KEYS = ("harness", "session", "machine", "worktree", "written")


@dataclass(frozen=True)
class HeaderSpec:
    """The keys of one flat header: their order, which hold a list, and which are read and ignored."""

    order: tuple[str, ...]
    list_keys: tuple[str, ...] = ()
    legacy: tuple[str, ...] = ()


# The header of a park note and the header of a lease: the two flat formats the helper reads.
NOTE_HEADER = HeaderSpec(order=_HEADER_ORDER, list_keys=_LIST_KEYS, legacy=_LEGACY_KEYS)
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

    The kits of a linked worktree live in the main checkout (ADR 0028 D12), outside the session's
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


def _check_job_id(value: str, label: str, texts: Mapping) -> None:
    if not _JOB_ID_RE.match(value):
        raise _error(texts, "bad_job_id", label=label, value=value)


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
    if fields.job:
        _check_job_id(fields.job, "job", texts)
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
        "job": fields.job,
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
        if key not in spec.order or key in values:
            raise _error(texts, "header_key", path=source, key=key)
        if key in spec.list_keys:
            if value:
                raise _error(texts, "header_scalar_list", path=source, key=key)
            values[key] = []
            current = key
        else:
            values[key] = value
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
        job=scalar("job"),
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
    lines = [jsondata.fill(texts["note"]["title"], {"kit": f"{fields.id}-{fields.name}"}), ""]
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
        "kit": f"{fields.id}-{fields.name}",
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
    lines = [jsondata.fill(spec["title"], {"kit": f"{fields.id}-{fields.name}", "state": state})]
    for key, value in (
        ("plan", fields.plan),
        ("job", fields.job),
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


def read_note(kit: Path, texts: Mapping) -> tuple[ParkFields, ParkBody]:
    """The fields and the body of a kit's ``PARK.md``; a kit without one was never parked.

    Raises:
        ParkError: the kit has no ``PARK.md``, or its note does not parse.
    """
    note = kit / _PARK_FILE
    if not note.is_file():
        raise _error(texts, "never_parked", kit=kit.name)
    return parse_note(note.read_text(encoding="utf-8"), f"{kit.name}/{_PARK_FILE}", texts)


def digest(kit: Path, cap: int, root: Path | None = None, data: Mapping | None = None) -> str:
    """The capped digest of a kit's note: whole lines up to ``cap`` characters, then the overflow line.

    ``cap`` counts the characters of the lines kept, newline included; the overflow line
    (``… N more lines in <path>``) is appended after them and is not counted. With ``root`` the
    path is the note's path from the project root, otherwise ``<kit name>/PARK.md``.

    Raises:
        ParkError: the kit was never parked or its note does not parse.
    """
    texts = data if data is not None else _texts()
    fields, body = read_note(kit, texts)
    context = LeaseContext(now=time.time(), stale_hours=texts["stale_after_hours"], machine="")
    lines = digest_lines(fields, body, kit_state(kit, texts, context), texts)
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > cap:
            break
        kept.append(line)
        used += len(line) + 1
    if len(kept) < len(lines):
        where = _display_path(kit / _PARK_FILE, root) if root is not None else f"{kit.name}/{_PARK_FILE}"
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


def _parse_stamp(value: str) -> float:
    """The epoch seconds of an ISO stamp, or ``0.0`` when it is not one."""
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return 0.0


def parse_lease(text: str, source: str, texts: Mapping) -> Lease:
    """The lease a ``HOLDER`` file declares.

    Raises:
        ParkError: the file has no header, or a line is malformed.
    """
    lines, _body = _split_note(text, source, texts)
    values = _header_values(lines, source, texts, LEASE_HEADER)
    holder = Holder(
        harness=str(values.get("harness", "")),
        session_id=str(values.get("session", "")),
        machine=str(values.get("machine", "")),
        worktree=str(values.get("worktree", "")),
    )
    return Lease(holder=holder, written=_parse_stamp(str(values.get("written", ""))))


def read_lease(unit: Path, texts: Mapping) -> Lease | None:
    """The lease of a unit, or ``None`` when the unit is free."""
    path = _lease_path(unit)
    if not path.is_file():
        return None
    return parse_lease(path.read_text(encoding="utf-8"), f"{unit.name}/{_HOLDER_FILE}", texts)


def lease_is_stale(lease: Lease, context: LeaseContext) -> bool:
    """Whether a lease is stale: written on another machine, or older than the threshold.

    A lease that came with a copied kit names another machine, and is stale at once.
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


def release_leases(kit: Path) -> None:
    """Release every lease of a kit: the plan's and its jobs'."""
    release_lease(kit)
    for folder in _job_folders(kit):
        release_lease(folder)


def _unit_note(unit: Path) -> Path | None:
    """The file that carries a unit's sessions: ``PARK.md`` for a kit, ``JOB.md`` for a job, or ``None``."""
    for name in (_PARK_FILE, _JOB_FILE):
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

    The header of a unit's note carries the sessions the work was done in (``PARK.md`` for a kit,
    ``JOB.md`` for a job); a holder that is taken over stays among them, so the note says who held
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
        doc = parse_job_doc(text, source, texts)
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
        _write_atomically(note, render_job_doc(dataclasses.replace(doc, header=header), texts))


# --------------------------------------------------------------------------------------
# the plan: its header and its job lines, read from ``PLAN.md``
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


def _job_field(cell: str) -> tuple[str, str]:
    """One job line cell as ``key, value``: ``tasks C186`` and ``result: text`` both parse."""
    if ": " in cell:
        key, _, value = cell.partition(": ")
        return key.strip(), value.strip()
    key, _, value = cell.partition(" ")
    return key.strip(), value.strip()


def parse_job_line(line: str) -> JobLine | None:
    """One job line of a plan as a ``JobLine``; a line that is not a job line is skipped."""
    if not line.startswith("- "):
        return None
    cells = tuple(cell.strip() for cell in line[2:].split(_TASK_SEPARATOR))
    if len(cells) < 2:  # noqa: PLR2004 — an id and a label are the minimum
        return None
    match = _JOB_ID_RE.match(cells[0])
    if match is None:
        return None
    fields: dict[str, object] = {"tasks": (), "after": (), "paths": (), "harness": "", "result": ""}
    for cell in cells[2:]:
        key, value = _job_field(cell)
        if key == "tasks":
            fields["tasks"] = _split_values(value)
        elif key == "after":
            fields["after"] = _split_values(value)
        elif key == "paths":
            fields["paths"] = _split_values(value)
        elif key == "harness":
            fields["harness"] = value
        elif key == "result":
            fields["result"] = value
    return JobLine(
        id=cells[0],
        number=int(match.group(2)),
        label=cells[1],
        tasks=tuple(fields["tasks"]),  # type: ignore[arg-type]
        after=tuple(fields["after"]),  # type: ignore[arg-type]
        paths=tuple(fields["paths"]),  # type: ignore[arg-type]
        harness=str(fields["harness"]),
        result=str(fields["result"]),
    )


def parse_plan(text: str) -> Plan:
    """A plan file as its header and its job lines."""
    values = _plan_values(text)
    header = PlanHeader(
        id=values.get("id", ""),
        name=values.get("name", ""),
        title=values.get("title", ""),
        tasks=_split_values(values.get("tasks", "")),
    )
    sections = _sections(text)
    job_lines = [line for line in sections.get(_JOBS_HEADING, []) if line.strip()]
    jobs = [job for job in (parse_job_line(line) for line in job_lines) if job is not None]
    return Plan(header=header, jobs=tuple(jobs))


def read_plan(kit: Path) -> Plan | None:
    """The plan of a kit, or ``None`` when it has none."""
    path = kit / _PLAN_FILE
    if not path.is_file():
        return None
    return parse_plan(path.read_text(encoding="utf-8"))


def job_slug(label: str) -> str:
    """A kebab-case name for a job, taken from its label."""
    slug = _SLUG_RE.sub("-", label.lower()).strip("-")
    return slug[:_SLUG_MAX].strip("-")


def _paths_overlap(one: str, other: str) -> bool:
    """Whether two forecast paths of two jobs may touch the same file."""
    left = one.rstrip(_PATH_SEPARATOR)
    right = other.rstrip(_PATH_SEPARATOR)
    return left == right or left.startswith(right + _PATH_SEPARATOR) or right.startswith(left + _PATH_SEPARATOR)


def _job_orders(one: JobLine, other: JobLine, plan: Plan) -> bool:
    """Whether one of the two jobs waits for the other, directly or through a chain of them.

    The chain matters: a job that waits for a job that waits for another cannot run at once
    with it, so the pair shares no warning. Only job ids of this plan order jobs; an
    ``after`` that names a task id orders nothing here.
    """
    jobs = {job.id: job for job in plan.jobs}
    waiting = _jobs_waiting_for(jobs, one.id)
    return other.id in waiting or one.id in _jobs_waiting_for(jobs, other.id)


def _jobs_waiting_for(jobs: Mapping[str, JobLine], job_id: str) -> set[str]:
    """The job ids that wait, directly or through a chain, for ``job_id``."""
    reached: set[str] = set()
    pending = [job_id]
    while pending:
        current = pending.pop()
        for other in jobs.values():
            if current in other.after and other.id not in reached:
                reached.add(other.id)
                pending.append(other.id)
    return reached


def shared_path_warnings(plan: Plan, texts: Mapping) -> list[str]:
    """The warnings of a plan: two jobs that may run at once and forecast the same path.

    The forecast is advice, not a fact; the owned uncommitted paths of each note are the fact.
    """
    warnings: list[str] = []
    for index, one in enumerate(plan.jobs):
        for other in plan.jobs[index + 1 :]:
            if _job_orders(one, other, plan):
                continue
            shared = sorted(
                {path for path in one.paths for other_path in other.paths if _paths_overlap(path, other_path)}
            )
            warnings.extend(
                jsondata.fill(
                    texts["list"]["warning_shared_paths"],
                    {"jobs": f"{one.id} {other.id}", "path": path},
                )
                for path in shared
            )
    return warnings


# --------------------------------------------------------------------------------------
# a job's own file: its steps with their done marks, and whether it is done
# --------------------------------------------------------------------------------------


def render_job_doc(doc: JobDoc, texts: Mapping) -> str:
    """The whole ``JOB.md``: its header, its steps and, once the result is met, the done mark."""
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


def parse_job_doc(text: str, source: str, texts: Mapping) -> JobDoc:
    """The ``JobDoc`` a ``JOB.md`` declares: its header, its steps and its done mark.

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
    return JobDoc(header=header, steps=tuple(steps), done=done)


def read_job_doc(path: Path, texts: Mapping) -> JobDoc | None:
    """The job file of a job folder, or ``None`` when it has none."""
    if not path.is_file():
        return None
    source = "/".join(path.parts[-_JOB_SOURCE_PARTS:])  # <kit>/jobs/<job>/JOB.md: the kit is named
    return parse_job_doc(path.read_text(encoding="utf-8"), source, texts)


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
# the kits of a project
# --------------------------------------------------------------------------------------


def _kit_names(root: Path, *, closed: bool = False) -> list[str]:
    """The names of the kit folders under ``.ergon/`` (``<id>-<name>`` only), sorted."""
    ergon = ergon_root(root)
    if closed:
        ergon = ergon / _CLOSED_DIR
    if not ergon.is_dir():
        return []
    return sorted(entry.name for entry in ergon.iterdir() if entry.is_dir() and _KIT_RE.match(entry.name))


def _kit_id(kit_name: str) -> str:
    match = _KIT_RE.match(kit_name)
    assert match is not None  # noqa: S101 — callers pass names _kit_names accepted
    return match.group(1)


def _find_kit_in(root: Path, kit_id: str, texts: Mapping, *, closed: bool) -> Path:
    names = _kit_names(root, closed=closed)
    found = [name for name in names if _kit_id(name) == kit_id]
    ergon = _display_path(ergon_root(root), root)
    if not found:
        raise _error(texts, "no_kit", id=kit_id, ergon=ergon, kits=", ".join(names) or "none")
    if len(found) > 1:
        raise _error(texts, "several_kits", id=kit_id, ergon=ergon, kits=", ".join(found))
    base = ergon_root(root) / _CLOSED_DIR if closed else ergon_root(root)
    return base / found[0]


def find_kit(root: Path, kit_id: str, texts: Mapping) -> Path:
    """The kit folder whose name leads with ``kit_id``.

    Raises:
        ParkError: no kit or several kits carry the id; the message names the candidates.
    """
    return _find_kit_in(root, kit_id, texts, closed=False)


def find_closed_kit(root: Path, kit_id: str, texts: Mapping) -> Path | None:
    """The closed kit folder whose name leads with ``kit_id``, or ``None``."""
    try:
        return _find_kit_in(root, kit_id, texts, closed=True)
    except ParkError:
        return None


def _jobs_dir(kit: Path) -> Path:
    return kit / _JOBS_DIR


def _job_folders(kit: Path) -> list[Path]:
    """The job folders of a kit, sorted by name."""
    folder = _jobs_dir(kit)
    if not folder.is_dir():
        return []
    return sorted(entry for entry in folder.iterdir() if entry.is_dir())


def find_job_folder(kit: Path, job_id: str, texts: Mapping) -> Path | None:
    """The folder of the job whose ``JOB.md`` names ``job_id``, or ``None``."""
    for folder in _job_folders(kit):
        doc = read_job_doc(folder / "JOB.md", texts)
        if doc is not None and doc.header.job == job_id:
            return folder
    return None


def job_id_of(kit_id: str, number: int) -> str:
    """The id of a job of a kit: the kit's id and the job's number."""
    return f"{kit_id}.{number}"


def unit_state(unit: Path, texts: Mapping, context: LeaseContext, *, job_done: bool = False) -> str:
    """The derived state of a unit (ADR 0028 D09): active, parked, not started or done.

    A stale lease holds nothing: the unit is free, and the lease is offered to the owner.
    """
    states = _states(texts)
    if job_done:
        return states["done"]
    lease = read_lease(unit, texts)
    if lease is not None and not lease_is_stale(lease, context):
        return states["active"]
    if (unit / _PARK_FILE).is_file():
        return states["parked"]
    return states["not_started"]


def kit_state(kit: Path, texts: Mapping, context: LeaseContext) -> str:
    """The state of a kit, joined from its jobs and its own lease and note (ADR 0028 D08, D09).

    A kit is **active** when it or any of its jobs is held, else **done** when every job is done,
    else **parked** when it or any of its jobs is parked, else **not started**. With a plan that
    lists jobs, "every job" is every listed job: it has a folder whose ``JOB.md`` is done, and a
    job with no folder has not started. With no plan, or a plan that lists no jobs, the job
    folders that exist decide. A kit whose jobs are all done is done even when its own note is
    still there; only a live lease on the kit itself outranks that.
    """
    states = _states(texts)
    folders = _job_folders(kit)
    docs = [read_job_doc(folder / "JOB.md", texts) for folder in folders]
    job_states = [
        unit_state(folder, texts, context, job_done=doc.done)
        for folder, doc in zip(folders, docs, strict=True)
        if doc is not None
    ]
    own = unit_state(kit, texts, context)
    if states["active"] in (own, *job_states):
        return states["active"]
    plan = read_plan(kit)
    if plan is not None and plan.jobs:
        done_ids = {doc.header.job for doc in docs if doc is not None and doc.done}
        if all(job.id in done_ids for job in plan.jobs):
            return states["done"]
    elif docs and all(doc is not None and doc.done for doc in docs):
        return states["done"]
    if states["parked"] in (own, *job_states):
        return states["parked"]
    return states["not_started"]


def _age_days(path: Path, now: float) -> int | None:
    """The age of a file in whole days, or ``None`` when there is no file."""
    if not path.is_file():
        return None
    return max(0, int((now - path.stat().st_mtime) // _SECONDS_PER_DAY))


# --------------------------------------------------------------------------------------
# writing a kit and a job
# --------------------------------------------------------------------------------------


def write_kit(fields: ParkFields, body: ParkBody, root: Path, texts: Mapping, cwd: Path) -> Path:
    """Park the work: write ``RESUME.md`` and ``PARK.md`` into the kit folder.

    The kit folder is created when missing. Everything that can be refused is checked before
    any file is touched; the files then land together (``write_files``), ``PARK.md`` last among
    the kit's, and a failure removes the folder it created when that folder is still empty.

    The sessions of the note are kept, not rebuilt: the sessions an earlier write recorded, the holder
    a takeover kept (``SESSIONS`` when the kit had no note yet), and then the ones on this command line.

    The branch and the revisions come from git, and the note records the time it was written.

    Returns:
        The kit folder.

    Raises:
        ParkError: a field fails its check, a kit with this id has another name, a closed kit has this
            id and name, or the note already there does not parse.
    """
    check_fields(fields, texts)
    check_body(body, texts)
    refuse_kit_conflict(fields, root, texts)
    kit = ergon_root(root) / f"{fields.id}-{fields.name}"
    park_path = _display_path(kit / _PARK_FILE, root)
    sessions = merge_sessions(_note_sessions(kit, texts), read_pending_sessions(kit, texts), fields.sessions)
    stamped = dataclasses.replace(
        fields, sessions=sessions, branch=git_branch(cwd), revisions=git_revisions(cwd), written=now_stamp()
    )
    files = [
        (kit / _RESUME_FILE, render_resume(stamped, body, park_path, texts)),
        (kit / _PARK_FILE, render_note(stamped, body, texts)),
    ]
    created = not kit.is_dir()
    try:
        kit.mkdir(parents=True, exist_ok=True)
        write_files(files)
    except BaseException:
        if created:
            _remove_if_empty(kit)
        raise
    (kit / _SESSIONS_FILE).unlink(missing_ok=True)  # merged into the note just written
    return kit


def _note_sessions(kit: Path, texts: Mapping) -> tuple[SessionRef, ...]:
    """The sessions the kit's note already carries; none when the kit has no note yet."""
    if not (kit / _PARK_FILE).is_file():
        return ()
    return read_note(kit, texts)[0].sessions


def refuse_kit_conflict(fields: ParkFields, root: Path, texts: Mapping) -> None:
    """Refuse a kit whose id is taken by another name, or whose id and name belong to a closed kit.

    A closed kit keeps its id and name for good, so a write never reuses them; ``local-id`` counts
    the closed kits for the same reason.

    Raises:
        ParkError: a live or closed kit carries the id under another name, or a closed kit has both.
    """
    kit_name = f"{fields.id}-{fields.name}"
    other = [name for name in _kit_names(root) if _kit_id(name) == fields.id and name != kit_name]
    other += [name for name in _kit_names(root, closed=True) if _kit_id(name) == fields.id and name != kit_name]
    if other:
        raise _error(texts, "kit_other_name", existing=other[0], id=fields.id, name=fields.name)
    if kit_name in _kit_names(root, closed=True):
        raise _error(texts, "kit_closed", kit=kit_name)


def write_job_doc(folder: Path, doc: JobDoc, texts: Mapping) -> None:
    """Write a job's own file, creating its folder when missing; a reader sees the old file or the new one."""
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomically(folder / "JOB.md", render_job_doc(doc, texts))


def _check_job_doc(doc: JobDoc, kit_name: str, texts: Mapping) -> None:
    """Refuse a job file whose header would not read back, naming the kit and the offending value.

    The header is built from the plan's header and job line, so the plan is what is at fault: a
    plan ``id`` that is no task id, say, would make a ``JOB.md`` that ``park list`` cannot parse.

    Raises:
        ParkError: the plan's header or job line breaks the header's contract.
    """
    try:
        check_fields(doc.header, texts)
    except ParkError as exc:
        raise _error(texts, "bad_plan", kit=kit_name, reason=exc) from exc


def job_doc_for(job: JobLine, kit_id: str, kit_name: str, plan: Plan | None) -> JobDoc:
    """The job file a job starts with: its header from the plan's job line, no steps yet."""
    header = ParkFields(
        id=kit_id,
        name=kit_name,
        next_action=job.result,
        plan=plan.header.id if plan is not None else "",
        job=job.id,
        tasks=job.tasks,
        branch=git_branch(Path.cwd()),
    )
    return JobDoc(header=header)


# --------------------------------------------------------------------------------------
# the listing: the kits, their jobs, and the states derived from the folders
# --------------------------------------------------------------------------------------


def summarize_kit(kit: Path, texts: Mapping, context: LeaseContext) -> KitSummary:
    """What ``list`` says of one kit; a kit with no ``PARK.md`` has no age and no next action."""
    kit_id = _kit_id(kit.name)
    name = kit.name[len(kit_id) + 1 :]
    note = kit / _PARK_FILE
    if not note.is_file():
        return KitSummary(kit_id, name, kit_state(kit, texts, context), "", "", 0, "", None)
    fields, body = read_note(kit, texts)
    return KitSummary(
        kit_id,
        name,
        kit_state(kit, texts, context),
        fields.plan,
        fields.next_action,
        len(body.decisions),
        fields.branch,
        _age_days(note, context.now),
    )


def summarize_job(folder: Path, texts: Mapping, context: LeaseContext) -> JobSummary | None:
    """What ``list`` says of one job, or ``None`` when the folder carries no job file."""
    doc = read_job_doc(folder / "JOB.md", texts)
    if doc is None:
        return None
    state = unit_state(folder, texts, context, job_done=doc.done)
    return JobSummary(
        id=doc.header.job or folder.name,
        name=folder.name,
        state=state,
        tasks=doc.header.tasks,
        next_action=doc.next_step(),
        branch=doc.header.branch,
        age_days=_age_days(folder / "JOB.md", context.now),
    )


def _kit_tasks(kit: Path, jobs: Sequence[JobSummary]) -> tuple[str, ...]:
    """The task ids a kit carries: from its plan header, its job lines and its jobs' files."""
    tasks: list[str] = []
    plan = read_plan(kit)
    if plan is not None:
        tasks.extend(plan.header.tasks)
        for job in plan.jobs:
            tasks.extend(job.tasks)
    for job in jobs:
        tasks.extend(job.tasks)
    return tuple(tasks)


def _matches(summary: KitSummary, jobs: Sequence[JobSummary], kit: Path, query: ListQuery) -> bool:
    """Whether a kit passes the filters of ``list``."""
    if query.plan and summary.plan != query.plan:
        return False
    if query.state and summary.state != query.state:
        return False
    return not query.task or query.task in _kit_tasks(kit, jobs)


def list_kits(
    root: Path, query: ListQuery, texts: Mapping, context: LeaseContext
) -> tuple[list[KitSummary], list[JobSummary]]:
    """The kits under ``.ergon/`` that match ``query``, and the jobs of those kits.

    Reads only: the local index is retired, so the folders are the whole record. A kit whose files
    do not parse is listed with its ``unreadable`` reason, whatever the filters, and the other
    kits are listed as usual.
    """
    summaries: list[KitSummary] = []
    jobs: list[JobSummary] = []
    entries: list[Path] = [ergon_root(root) / name for name in _kit_names(root)]
    if query.closed:
        entries += [ergon_root(root) / _CLOSED_DIR / name for name in _kit_names(root, closed=True)]
    for kit in entries:
        try:
            summary = summarize_kit(kit, texts, context)
            kit_jobs = [summarize_job(folder, texts, context) for folder in _job_folders(kit)]
        except ParkError as exc:  # one bad kit is reported on its own line, never stops the others
            kit_id = _kit_id(kit.name)
            reason = _LINE_BREAKS_RE.sub(" ", str(exc))
            summaries.append(KitSummary(kit_id, kit.name[len(kit_id) + 1 :], "", "", "", 0, "", None, reason))
            continue
        kit_jobs = [job for job in kit_jobs if job is not None]
        if not _matches(summary, kit_jobs, kit, query):
            continue
        summaries.append(summary)
        jobs.extend(kit_jobs)
    return sorted(summaries, key=lambda item: item.id), jobs


def _truncate(text: str, width: int, texts: Mapping) -> str:
    """``text`` cut to ``width`` characters, the last one the ellipsis when it was cut."""
    return text if len(text) <= width else text[: width - 1] + texts["ellipsis"]


def format_summary(item: KitSummary, texts: Mapping) -> str:
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


def format_job(item: JobSummary, texts: Mapping) -> str:
    """One job line of ``list``."""
    empty = texts["empty_cell"]
    return jsondata.fill(
        texts["list"]["job_line"],
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
    """The kit id and the job number a worktree's folder names, or ``None``.

    The folder is ``<id>-<name>.<n>``: the kit's own folder name and the job's number.
    """
    name = folder.name
    base, _, tail = name.rpartition(".")
    if not base or not tail.isdigit() or not _KIT_RE.match(base):
        return None
    match = _KIT_RE.match(base)
    assert match is not None  # noqa: S101 — the guard above checked it
    return match.group(1), int(tail)


def active_unit(root: Path, texts: Mapping) -> tuple[Path, str, int] | None:
    """The kit and the job this session is in, read from the folder it works in.

    A session in the main checkout has no active unit until it picks one; a session in a job's
    worktree is in that job, named by the worktree's own folder.
    """
    if root.parent.name != _WORKTREES_DIR:
        return None
    unit = worktree_unit(root)
    if unit is None:
        return None
    kit_id, number = unit
    try:
        kit = find_kit(root, kit_id, texts)
    except ParkError:
        return None
    return kit, kit_id, number


# --------------------------------------------------------------------------------------
# the export: the kit's files, its leases left out (ADR 0028 D07, branch B10)
# --------------------------------------------------------------------------------------


def export_kit(kit: Path, out: Path, texts: Mapping) -> Path:
    """Write the kit's files to one bundle file, its leases left out.

    The bundle is plain text: the file's path, then its content, so any language reads it.
    """
    lines = [jsondata.fill(texts["export"]["title"], {"kit": kit.name}), ""]
    for path in sorted(item for item in kit.rglob("*") if item.is_file()):
        if path.name == _HOLDER_FILE:
            continue
        lines.append(jsondata.fill(texts["export"]["file_header"], {"path": path.relative_to(kit).as_posix()}))
        lines.append(path.read_text(encoding="utf-8").rstrip("\n"))
        lines.append(texts["export"]["end"])
        lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------------------
# the local ids: ``_T<n>`` counted over the kits, live and closed, never reused
# --------------------------------------------------------------------------------------


def _legacy_local_ids(root: Path) -> list[int]:
    """The ``_T<n>`` numbers the retired local index ``<DEV>/.local/TASKS.md`` still holds.

    Read as legacy input and never written (ADR 0028 D12). The index sits with the kits in the
    main checkout, so a linked worktree reads that one. No such file holds no number.
    """
    index = local_root(git_common_root(root)) / _LEGACY_INDEX_FILE
    if not index.is_file():
        return []
    rows = (_LEGACY_ROW_RE.match(line) for line in index.read_text(encoding="utf-8").split("\n"))
    return [int(match.group(1)) for match in rows if match is not None]


def next_local_id(root: Path) -> str:
    """The next free local id: ``_T<n>`` counted over every kit, live and closed, and the legacy index."""
    numbers = [0, *_legacy_local_ids(root)]
    for name in _kit_names(root) + _kit_names(root, closed=True):
        match = _LOCAL_ID_RE.match(_kit_id(name))
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
    """The commands that write or read a kit's own note: write, unpark, digest, list."""
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
    _add_holder_flags(write)

    unpark = commands.add_parser("unpark", parents=[common], help="Resume a parked kit.", allow_abbrev=False)
    unpark.add_argument("id")
    _add_holder_flags(unpark)

    digest_cmd = commands.add_parser("digest", parents=[common], help="Print the capped digest.", allow_abbrev=False)
    digest_cmd.add_argument("id")
    digest_cmd.add_argument("--cap", type=int, default=None)

    listing = commands.add_parser("list", parents=[common], help="List the kits.", allow_abbrev=False)
    listing.add_argument("--plan", default="")
    listing.add_argument("--task", default="")
    listing.add_argument("--state", default="")
    listing.add_argument("--closed", action="store_true")


def _add_unit_commands(commands: Any, common: argparse.ArgumentParser) -> None:
    """The commands that act on one unit: hold, release, job, active, close, export, local-id."""
    hold = commands.add_parser("hold", parents=[common], help="Take the lease of a unit.", allow_abbrev=False)
    hold.add_argument("id")
    hold.add_argument("--number", type=int, default=None)
    hold.add_argument("--takeover", action="store_true")
    _add_holder_flags(hold)

    release = commands.add_parser("release", parents=[common], help="Release the lease of a unit.", allow_abbrev=False)
    release.add_argument("id")
    release.add_argument("--number", type=int, default=None)

    job = commands.add_parser("job", parents=[common], help="Write a job's own file.", allow_abbrev=False)
    job.add_argument("id")
    job.add_argument("--number", type=int, required=True)
    job.add_argument("--step", action="append", default=[])
    job.add_argument("--done", action="store_true")
    _add_holder_flags(job)

    commands.add_parser("active", parents=[common], help="Print the unit this session is in.", allow_abbrev=False)

    close = commands.add_parser(
        "close", parents=[common], help="Close a kit and move it to the closed folder.", allow_abbrev=False
    )
    close.add_argument("id")
    _add_holder_flags(close)

    export = commands.add_parser(
        "export", parents=[common], help="Write the kit to one bundle file.", allow_abbrev=False
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
    parser = argparse.ArgumentParser(description="Park work into a kit and resume it.", allow_abbrev=False)
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


def _holder_of(args: argparse.Namespace, machine: str) -> Holder:
    """The holder a command acts as: the flags, or the machine it runs on."""
    return Holder(
        harness=args.harness.strip(),
        session_id=args.session_id.strip(),
        machine=args.machine.strip() or machine,
        worktree=str(Path.cwd()),
    )


def _unit_of(kit: Path, number: int | None, texts: Mapping) -> Path:
    """The folder of the unit a command acts on: the kit root, or one of its jobs."""
    if number is None:
        return kit
    job_id = job_id_of(_kit_id(kit.name), number)
    folder = find_job_folder(kit, job_id, texts)
    if folder is None:
        raise _error(texts, "no_job", kit=kit.name, job=job_id)
    return folder


def _machine_label() -> str:
    """The label of the machine this session runs on."""
    with contextlib.suppress(OSError):
        return socket.gethostname()
    return ""


def _read_resume(kit: Path, texts: Mapping) -> str:
    """The resume prompt of a kit, and the proof that its note reads: nothing is held yet.

    Raises:
        ParkError: the kit has no ``RESUME.md``, was never parked, or its note does not parse.
    """
    resume = kit / _RESUME_FILE
    if not resume.is_file():
        raise _error(texts, "no_resume", kit=kit.name)
    read_note(kit, texts)
    return resume.read_text(encoding="utf-8").rstrip("\n")


def _resume_text(prompt: str, kit: Path, root: Path, texts: Mapping) -> str:
    """The resume prompt of a kit, followed by a blank line and its capped digest."""
    return prompt + "\n\n" + digest(kit, texts["default_cap"], root, texts)


def _planned_job(kit: Path, plan: Plan, job_id: str, texts: Mapping) -> JobLine:
    """The usable job line of a plan for ``job_id``: it names a folder and a result for ``JOB.md``.

    Raises:
        ParkError: the plan has no such job, or the line has no label or no result.
    """
    line = next((job for job in plan.jobs if job.id == job_id), None)
    if line is None:
        raise _error(texts, "no_job", kit=kit.name, job=job_id)
    if not line.label:
        raise _error(texts, "job_label", id=job_id)
    if not line.result:
        raise _error(texts, "bad_plan", kit=kit.name, reason=f"job {job_id} has no result")
    return line


def _write_job(root: Path, args: argparse.Namespace, texts: Mapping, context: LeaseContext) -> None:
    """Write a job's own file: create it from the plan's job line, then add its steps.

    Everything that can be refused is checked before the lease is taken or a file is touched. The
    first write into a job's folder takes its lease, so two sessions never write one file. The
    plan's shared-path warnings go to stderr.

    Raises:
        ParkError: the kit has no plan, the plan has no usable line for the job, or the job is held.
    """
    kit = find_kit(root, args.id.strip(), texts)
    kit_id = _kit_id(kit.name)
    job_id = job_id_of(kit_id, args.number)
    plan = read_plan(kit)
    if plan is None:
        raise _error(texts, "no_plan", kit=kit.name)
    folder = find_job_folder(kit, job_id, texts)
    doc = read_job_doc(folder / "JOB.md", texts) if folder is not None else None
    if doc is None:
        line = _planned_job(kit, plan, job_id, texts)
        doc = job_doc_for(line, kit_id, kit.name[len(kit_id) + 1 :], plan)
        _check_job_doc(doc, kit.name, texts)
        if folder is None:
            folder = _jobs_dir(kit) / f"{args.number}-{job_slug(line.label)}"
    acquire_lease(folder, _holder_of(args, context.machine), texts, context)
    steps = doc.steps + tuple((text, False) for text in _stripped(args.step))
    write_job_doc(folder, JobDoc(header=doc.header, steps=steps, done=doc.done or args.done), texts)
    print(_display_path(folder, root))
    for warning in shared_path_warnings(plan, texts):
        print(warning, file=sys.stderr)


def _print_active(root: Path, texts: Mapping, context: LeaseContext) -> None:
    """Print the unit this session is in: the job of the worktree it works in."""
    found = active_unit(root, texts)
    if found is None:
        print(texts["active"]["none"])
        return
    kit, kit_id, number = found
    job_id = job_id_of(kit_id, number)
    folder = find_job_folder(kit, job_id, texts)
    unit = folder if folder is not None else kit
    lease = read_lease(unit, texts)
    state = unit_state(unit, texts, context)
    path = _display_path(unit, root)
    print(
        jsondata.fill(
            texts["active"]["line"],
            {
                "kind": "job" if folder is not None else "kit",
                "id": job_id if folder is not None else kit_id,
                "name": unit.name,
                "state": state,
                "holder": lease.holder.label() if lease is not None else texts["empty_cell"],
                "path": path,
            },
        )
    )


@dataclass(frozen=True)
class _Run:
    """What every command of one invocation shares: the root, the texts, the lease clock, the machine."""

    root: Path
    texts: Mapping
    lease: LeaseContext
    machine: str


def _cmd_write(args: argparse.Namespace, run: _Run) -> int:
    fields = _fields_from(args, run.texts)
    body = _body_from(args)
    kit = _kit_folder(run.root, fields)
    holder = _holder_of(args, run.machine)
    check_fields(fields, run.texts)
    check_body(body, run.texts)
    refuse_kit_conflict(fields, run.root, run.texts)
    _refuse_foreign_lease(kit, holder, run)
    free = read_lease(kit, run.texts) is None
    # The write holds the kit while it writes: a lease taken since the check is refused, not overwritten.
    lease = acquire_lease(kit, holder, run.texts, run.lease)
    try:
        write_kit(fields, body, run.root, run.texts, Path.cwd())
    except BaseException:
        if free:
            _release_own_lease(kit, lease, run.texts)
            _remove_if_empty(kit)
        raise
    _release_own_lease(kit, lease, run.texts)
    print(_display_path(kit, run.root))
    return 0


def _release_own_lease(unit: Path, lease: Lease, run_texts: Mapping) -> None:
    """Release the lease of a unit when it is still the one this session took; another's is never removed."""
    current = read_lease(unit, run_texts)
    if current is not None and current.holder == lease.holder:
        release_lease(unit)


def _kit_folder(root: Path, fields: ParkFields) -> Path:
    """The folder a kit has, or the one it would have; the name conflict is the writer's to refuse."""
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
    kit = find_kit(run.root, args.id.strip(), run.texts)
    prompt = _read_resume(kit, run.texts)  # everything that can be refused, before a lease is taken
    acquire_lease(kit, _holder_of(args, run.machine), run.texts, run.lease)
    print(_resume_text(prompt, kit, run.root, run.texts))
    return 0


def _cmd_digest(args: argparse.Namespace, run: _Run) -> int:
    cap = run.texts["default_cap"] if args.cap is None else args.cap
    if cap < 0:
        raise _error(run.texts, "bad_cap", value=cap)
    print(digest(find_kit(run.root, args.id.strip(), run.texts), cap, run.root, run.texts))
    return 0


def _cmd_list(args: argparse.Namespace, run: _Run) -> int:
    query = ListQuery(args.plan.strip(), args.task.strip(), args.state.strip(), args.closed)
    kits, jobs = list_kits(run.root, query, run.texts, run.lease)
    if kits:
        lines: list[str] = []
        for summary in kits:
            lines.append(format_summary(summary, run.texts))
            lines.extend(format_job(job, run.texts) for job in jobs if job.id.startswith(f"{summary.id}."))
        print("\n".join(lines))
    elif not _kit_names(run.root):
        folder = _display_path(ergon_root(run.root), run.root)
        print(jsondata.fill(run.texts["list"]["empty"], {"path": folder}))
    else:
        print(run.texts["list"]["no_match"])
    return 0


def _cmd_hold(args: argparse.Namespace, run: _Run) -> int:
    kit = find_kit(run.root, args.id.strip(), run.texts)
    unit = _unit_of(kit, args.number, run.texts)
    holder = _holder_of(args, run.machine)
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
    kit = find_kit(run.root, args.id.strip(), run.texts)
    unit = _unit_of(kit, args.number, run.texts)
    if read_lease(unit, run.texts) is None:
        raise _error(run.texts, "no_holder", unit=unit.name)
    release_lease(unit)
    print(unit.name)
    return 0


def _cmd_job(args: argparse.Namespace, run: _Run) -> int:
    _write_job(run.root, args, run.texts, run.lease)
    return 0


def _cmd_active(_args: argparse.Namespace, run: _Run) -> int:
    _print_active(run.root, run.texts, run.lease)
    return 0


def _cmd_close(args: argparse.Namespace, run: _Run) -> int:
    kit = find_kit(run.root, args.id.strip(), run.texts)
    _refuse_live_foreign_lease(kit, _holder_of(args, run.machine), run)
    closed = ergon_root(run.root) / _CLOSED_DIR
    target = closed / kit.name
    if target.exists():
        raise _error(run.texts, "close_exists", kit=kit.name, target=_display_path(target, run.root))
    closed.mkdir(parents=True, exist_ok=True)
    try:
        kit.rename(target)
    except OSError as exc:
        raise _error(
            run.texts, "close_failed", kit=kit.name, reason=errno.errorcode.get(exc.errno or 0, "OSError")
        ) from exc
    release_leases(target)  # after the move, so a close that is refused or fails changes nothing
    print(_display_path(target, run.root))
    return 0


def _refuse_live_foreign_lease(kit: Path, holder: Holder, run: _Run) -> None:
    """Refuse to close a kit while a live lease of another session is in it, the plan's or a job's.

    A stale lease holds nothing, and the closing session's own leases are its to release.

    Raises:
        ParkError: another session holds a unit of the kit; the message names the unit and the holder.
    """
    for unit in (kit, *_job_folders(kit)):
        lease = read_lease(unit, run.texts)
        if lease is None or lease_is_stale(lease, run.lease) or lease.holder.same_as(holder):
            continue
        raise _error(run.texts, "close_held", unit=unit.name, holder=lease.holder.label())


def _cmd_export(args: argparse.Namespace, run: _Run) -> int:
    kit = find_kit(run.root, args.id.strip(), run.texts)
    export_kit(kit, Path(args.out), run.texts)
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
        "job": _cmd_job,
        "active": _cmd_active,
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
