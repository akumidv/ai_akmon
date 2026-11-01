#!/usr/bin/env python3
"""The park helper: write, resume, digest and list the kits of parked work (ADR 0028 D02, D03, D06).

A *kit* is the folder ``<dev root>/.ergon/<id>-<name>/`` of one piece of work. Parking it writes two
files into it, atomically: ``PARK.md``, the park note — a small machine-readable header between two
``---`` lines and a Markdown body of facts — and ``RESUME.md``, the harness-neutral prompt a
successor starts from. It also keeps the kit's one row in the local index
(``<dev root>/.local/TASKS.md``) at the status ``parked``; a project index is never touched.

    akmon tool park/park write C183 --name park-helper --goal "…" --next "…"
    akmon tool park/park unpark C183     # state resumed, row active, prints RESUME.md and the digest
    akmon tool park/park digest C183 [--cap N]
    akmon tool park/park list [--plan ID] [--state S] [--status TOKEN]

The header has ONE source, the frozen ``ParkFields`` the command line fills: it is rendered from
that type and parsed back into it, and no other declaration of its keys exists. Its format is a
fixed, flat one so any language reads it without a YAML library:

    ---
    key: value          a scalar; an empty value is written ``key:`` with nothing after the colon
    key:                a list key, then one ``  - item`` line (two spaces) per item
      - item
    ---

The helper writes no date (a kit's age is read from the file's mtime), never runs git, never reads
a transcript and never pushes. Stdlib-only, and nothing happens at import time: tools run before a
virtual environment exists.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# The tree root, so the shared ``common`` package resolves from the mounted tree and from a
# materialized copy alike (the way ``tasks/archive.py`` reaches it).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common import jsondata
from common.project_root import ERGON_DIR_NAME, ergon_root, local_root, resolve_project_root

_SECONDS_PER_DAY = 86400
_PARK_FILE = "PARK.md"
_RESUME_FILE = "RESUME.md"
_INDEX_FILE = "TASKS.md"
_HEADER_FENCE = "---"
_ID_RE = re.compile(r"^(?:[A-Z]\d+|_T\d+)$")  # ADR 0002 typed id, and a local row's _T<n> (ADR 0022 D03)
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_KIT_RE = re.compile(r"^((?:[A-Z]\d+|_T\d+))-([a-z0-9]+(?:-[a-z0-9]+)*)$")
_KEY_RE = re.compile(r"^([a-z_]+):(?: (.*))?$")
_PURPOSE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ROW_ID_TAIL = re.compile(r"\[[^\]]*\]$")  # a row id may carry a tracker tag: C2[#134]
_LINK_RE = re.compile(r"\]\([^)]*\)")
_STATUS_FIELD = 2  # the third ``·``-separated field of an index row (pipelines/tasks.md)
_ROW_FIELDS_MIN = 3


class ParkError(Exception):
    """A failure the command line reports as one line on stderr with exit 1."""


@dataclass(frozen=True)
class SessionRef:
    """Where the work was done: a reference for provenance, never a requirement (ADR 0028 D03)."""

    harness: str
    session_id: str
    machine: str


@dataclass(frozen=True)
class ParkFields:
    """The header of a park note: the one source of its keys, rendered and parsed from here."""

    id: str
    name: str
    next_action: str
    state: str = "parked"
    plan: str = ""
    row: str = ""
    branch: str = ""
    revisions: tuple[str, ...] = ()
    owned_paths: tuple[str, ...] = ()
    sessions: tuple[SessionRef, ...] = ()
    peers: tuple[str, ...] = ()
    origin: str = ""
    readiness: str = ""


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
class KitSummary:
    """One line of ``list``: what a kit says of itself, read from its folder and the local index."""

    id: str
    name: str
    state: str
    plan: str
    next_action: str
    decisions: int
    branch: str
    age_days: int | None
    status: str


@dataclass(frozen=True)
class ListQuery:
    """The filters of ``list``; an empty one matches every kit."""

    plan: str = ""
    state: str = ""
    status: str = ""


@dataclass(frozen=True)
class WriteOptions:
    """What ``write`` needs beyond the note: the index row's title and role."""

    title: str = ""
    role: str = ""


# Header keys in their written order, and which of them hold a list: the one table the renderer and
# the parser share. ``next_action`` is written as ``next``.
_SCALAR_KEYS = ("state", "id", "name", "plan", "row", "branch", "next", "origin", "readiness")
_LIST_KEYS = ("revisions", "owned_paths", "sessions", "peers")
_HEADER_ORDER = (
    "state",
    "id",
    "name",
    "plan",
    "row",
    "branch",
    "revisions",
    "owned_paths",
    "next",
    "sessions",
    "peers",
    "origin",
    "readiness",
)


def _texts() -> dict:
    """The tool's texts (``park.json``), read on the call that needs them."""
    return jsondata.read(Path(__file__).parent / "park.json")


def _error(texts: Mapping, code: str, **values: object) -> ParkError:
    """A ``ParkError`` from the stored message ``errors.<code>``, with its placeholders filled."""
    return ParkError(jsondata.fill(texts["errors"][code], {name: str(value) for name, value in values.items()}))


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
    if fields.state not in (texts["state_parked"], texts["state_resumed"]):
        raise _error(texts, "bad_state", value=fields.state)
    for label, value in (("plan", fields.plan), ("row", fields.row)):
        if value:
            _check_id(value, label, texts)
    for label, value in (
        ("branch", fields.branch),
        ("next", fields.next_action),
        ("origin", fields.origin),
        ("readiness", fields.readiness),
    ):
        _check_line(value, label, texts)
    if not fields.next_action:
        raise _error(texts, "empty", label="next")
    _check_items(fields.revisions, "revision", texts)
    _check_items(fields.owned_paths, "owned path", texts)
    _check_items(fields.peers, "peer", texts)
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
        "state": fields.state,
        "id": fields.id,
        "name": fields.name,
        "plan": fields.plan,
        "row": fields.row,
        "branch": fields.branch,
        "next": fields.next_action,
        "origin": fields.origin,
        "readiness": fields.readiness,
    }
    lists = {
        "revisions": fields.revisions,
        "owned_paths": fields.owned_paths,
        "sessions": tuple(_session_text(session) for session in fields.sessions),
        "peers": fields.peers,
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


def _header_values(lines: Sequence[str], source: str, texts: Mapping) -> dict[str, str | list[str]]:
    """The header lines as ``key -> scalar | list``, each key known and once, each line well-formed."""
    values: dict[str, str | list[str]] = {}
    current: str | None = None
    for number, line in enumerate(lines, start=1):
        if line.startswith("  - "):
            if current is None or current not in _LIST_KEYS:
                raise _error(texts, "header_item", path=source, line=number)
            item = values[current]
            assert isinstance(item, list)  # noqa: S101 — a list key was opened by its own line
            item.append(line[4:])
            continue
        match = _KEY_RE.match(line)
        if match is None:
            raise _error(texts, "header_line", path=source, line=number)
        key, value = match.group(1), match.group(2) or ""
        if key not in _HEADER_ORDER or key in values:
            raise _error(texts, "header_key", path=source, key=key)
        if key in _LIST_KEYS:
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
    for key in ("id", "name", "next", "state"):
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
        state=scalar("state"),
        plan=scalar("plan"),
        row=scalar("row"),
        branch=scalar("branch"),
        revisions=listed("revisions"),
        owned_paths=listed("owned_paths"),
        sessions=tuple(_parse_session(item, texts) for item in listed("sessions")),
        peers=listed("peers"),
        origin=scalar("origin"),
        readiness=scalar("readiness"),
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


def with_state(text: str, state: str, source: str, texts: Mapping) -> str:
    """``text`` with its header's state replaced and everything after the header kept byte for byte."""
    fields = parse_header(text, source, texts)
    _lines, rest = _split_note(text, source, texts)
    return render_header(dataclasses.replace(fields, state=state)) + rest


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


def digest_lines(fields: ParkFields, body: ParkBody, texts: Mapping) -> list[str]:
    """The digest before the cap: the summary, the goal, the next action, the decisions and the answers."""
    spec = texts["digest"]
    lines = [jsondata.fill(spec["title"], {"kit": f"{fields.id}-{fields.name}", "state": fields.state})]
    for key, value in (
        ("plan", fields.plan),
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
    """The fields and the body of the kit's ``PARK.md``; a kit without one was never parked.

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
    lines = digest_lines(fields, body, texts)
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > cap:
            break
        kept.append(line)
        used += len(line) + 1
    if len(kept) < len(lines):
        where = (kit / _PARK_FILE).relative_to(root).as_posix() if root is not None else f"{kit.name}/{_PARK_FILE}"
        kept.append(jsondata.fill(texts["digest"]["overflow"], {"count": len(lines) - len(kept), "path": where}))
    return "\n".join(kept)


# --------------------------------------------------------------------------------------
# the local index: one row per kit, status parked only here
# --------------------------------------------------------------------------------------


def _row_id(row: str) -> str:
    return _ROW_ID_TAIL.sub("", row[2:].split("·", 1)[0].strip())


def _row_status(row: str) -> str | None:
    cells = row[2:].split("·")
    return cells[_STATUS_FIELD].strip() if len(cells) >= _ROW_FIELDS_MIN else None


def _with_status(row: str, status: str) -> str:
    """``row`` with only its status cell replaced, keeping the spacing around it."""
    cells = row.split("·")
    cell = cells[_STATUS_FIELD]
    lead = cell[: len(cell) - len(cell.lstrip())]
    trail = cell[len(cell.rstrip()) :]
    cells[_STATUS_FIELD] = f"{lead}{status}{trail}"
    return "·".join(cells)


def _find_row(lines: Sequence[str], row_id: str) -> int | None:
    for index, line in enumerate(lines):
        if line.startswith("- ") and _row_id(line) == row_id:
            return index
    return None


def index_statuses(text: str) -> dict[str, str]:
    """The status of every row of an index text by id (the first row of a repeated id wins)."""
    statuses: dict[str, str] = {}
    for line in text.split("\n"):
        status = _row_status(line) if line.startswith("- ") else None
        if status is not None:
            statuses.setdefault(_row_id(line), status)
    return statuses


def _first_line(text: str) -> str:
    return text.split("\n", 1)[0]


def _check_cell(value: str, label: str, texts: Mapping) -> None:
    if "·" in value:
        raise _error(texts, "bad_cell", label=label)


def park_index(text: str | None, fields: ParkFields, body: ParkBody, options: WriteOptions, texts: Mapping) -> str:
    """The local index text with the kit's row parked: its status set, or the row appended.

    ``text`` is ``None`` when the index does not exist, which starts it with the one-line header.
    An existing row keeps its prose and gains a ``[park]`` detail link only when it has no link.

    Raises:
        ParkError: the existing row has too few fields, or a new row's cell holds the separator.
    """
    link = jsondata.fill(texts["row"]["link"], {"link": f"../{ERGON_DIR_NAME}/{fields.id}-{fields.name}/{_PARK_FILE}"})
    parked = texts["status_parked"]
    if text is None:
        text = texts["index_header"] + "\n\n"
    lines = text.split("\n")
    at = _find_row(lines, fields.id)
    if at is not None:
        if _row_status(lines[at]) is None:
            raise _error(texts, "bad_row", id=fields.id, row=lines[at])
        row = _with_status(lines[at], parked).rstrip()
        lines[at] = row if _LINK_RE.search(row) else f"{row} · {link}"
        return "\n".join(lines)
    goal = _first_line(body.goal)
    title = options.title or goal
    role = options.role or texts["default_role"]
    for label, value in (("title", title), ("role", role), ("goal", goal)):
        _check_cell(value, label, texts)
    row = f"- {fields.id} · {title} · {parked} · {role} · {goal} · {link}"
    return text + row + "\n" if text.endswith("\n") else f"{text}\n{row}\n"


def resume_index(text: str, kit_id: str, texts: Mapping) -> str | None:
    """The index text with the kit's row set back to ``active``, or ``None`` when it is not ``parked``."""
    lines = text.split("\n")
    at = _find_row(lines, kit_id)
    if at is None or _row_status(lines[at]) != texts["status_parked"]:
        return None
    lines[at] = _with_status(lines[at], texts["status_active"])
    return "\n".join(lines)


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


# --------------------------------------------------------------------------------------
# the kits of a project
# --------------------------------------------------------------------------------------


def _kit_names(root: Path) -> list[str]:
    """The names of the kit folders under ``.ergon/`` (``<id>-<name>`` only), sorted."""
    ergon = ergon_root(root)
    if not ergon.is_dir():
        return []
    return sorted(entry.name for entry in ergon.iterdir() if entry.is_dir() and _KIT_RE.match(entry.name))


def _kit_id(kit_name: str) -> str:
    match = _KIT_RE.match(kit_name)
    assert match is not None  # noqa: S101 — callers pass names _kit_names accepted
    return match.group(1)


def find_kit(root: Path, kit_id: str, texts: Mapping) -> Path:
    """The kit folder whose name leads with ``kit_id``.

    Raises:
        ParkError: no kit or several kits carry the id; the message names the candidates.
    """
    names = _kit_names(root)
    found = [name for name in names if _kit_id(name) == kit_id]
    ergon = ergon_root(root).relative_to(root).as_posix()
    if not found:
        raise _error(texts, "no_kit", id=kit_id, ergon=ergon, kits=", ".join(names) or "none")
    if len(found) > 1:
        raise _error(texts, "several_kits", id=kit_id, ergon=ergon, kits=", ".join(found))
    return ergon_root(root) / found[0]


def _index_path(root: Path) -> Path:
    return local_root(root) / _INDEX_FILE


def _read_index(root: Path) -> str | None:
    path = _index_path(root)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def write_kit(fields: ParkFields, body: ParkBody, root: Path, options: WriteOptions, texts: Mapping) -> Path:
    """Park the work: write ``RESUME.md`` and ``PARK.md`` into the kit and park its row in the local index.

    The kit folder is created when missing. Everything that can be refused is checked before
    any file is touched; the files then land together (``write_files``), ``PARK.md`` last among
    the kit's, and a failure removes the folder it created when that folder is still empty.

    Returns:
        The kit folder.

    Raises:
        ParkError: a field fails its check, or a kit with this id has another name.
    """
    check_fields(fields, texts)
    check_body(body, texts)
    kit_name = f"{fields.id}-{fields.name}"
    other = [name for name in _kit_names(root) if _kit_id(name) == fields.id and name != kit_name]
    if other:
        raise _error(texts, "kit_other_name", existing=other[0], id=fields.id, name=fields.name)
    kit = ergon_root(root) / kit_name
    park_path = (kit / _PARK_FILE).relative_to(root).as_posix()
    index = _index_path(root)
    files = [
        (kit / _RESUME_FILE, render_resume(fields, body, park_path, texts)),
        (kit / _PARK_FILE, render_note(fields, body, texts)),
        (index, park_index(_read_index(root), fields, body, options, texts)),
    ]
    created = not kit.is_dir()
    try:
        kit.mkdir(parents=True, exist_ok=True)
        index.parent.mkdir(parents=True, exist_ok=True)
        write_files(files)
    except BaseException:
        if created:
            _remove_if_empty(kit)
        raise
    return kit


def _remove_if_empty(folder: Path) -> None:
    with contextlib.suppress(OSError):  # not empty, or already gone: nothing of ours to remove
        folder.rmdir()


def unpark_kit(kit: Path, root: Path, texts: Mapping) -> str:
    """Resume the work: the note's state becomes ``resumed``, its row ``active``; returns what to print.

    The text is ``RESUME.md`` followed by a blank line and the capped digest.

    Raises:
        ParkError: the kit was never parked or has no ``RESUME.md``.
    """
    note = kit / _PARK_FILE
    if not note.is_file():
        raise _error(texts, "never_parked", kit=kit.name)
    resume = kit / _RESUME_FILE
    if not resume.is_file():
        raise _error(texts, "no_resume", kit=kit.name)
    source = f"{kit.name}/{_PARK_FILE}"
    updated = with_state(note.read_text(encoding="utf-8"), texts["state_resumed"], source, texts)
    files = [(note, updated)]
    index_text = _read_index(root)
    if index_text is not None:
        resumed = resume_index(index_text, _kit_id(kit.name), texts)
        if resumed is not None:
            files.append((_index_path(root), resumed))
    write_files(files)
    return resume.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + digest(kit, texts["default_cap"], root, texts)


def summarize_kit(kit: Path, status: str, now: float, texts: Mapping) -> KitSummary:
    """What ``list`` says of one kit; a kit with no ``PARK.md`` is ``never-parked`` and has no age."""
    kit_id = _kit_id(kit.name)
    name = kit.name[len(kit_id) + 1 :]
    note = kit / _PARK_FILE
    if not note.is_file():
        return KitSummary(kit_id, name, texts["state_never_parked"], "", "", 0, "", None, status)
    fields, body = read_note(kit, texts)
    age = max(0, int((now - note.stat().st_mtime) // _SECONDS_PER_DAY))
    return KitSummary(
        kit_id, name, fields.state, fields.plan, fields.next_action, len(body.decisions), fields.branch, age, status
    )


def list_kits(root: Path, query: ListQuery, now: float, texts: Mapping) -> list[KitSummary]:
    """The kits under ``.ergon/`` that match ``query``, stably sorted by id. Reads only."""
    index_text = _read_index(root)
    statuses = index_statuses(index_text) if index_text is not None else {}
    empty = texts["empty_cell"]
    summaries = [
        summarize_kit(ergon_root(root) / name, statuses.get(_kit_id(name), empty), now, texts)
        for name in _kit_names(root)
    ]
    matching = [
        item
        for item in summaries
        if (not query.plan or item.plan == query.plan)
        and (not query.state or item.state == query.state)
        and (not query.status or item.status == query.status)
    ]
    return sorted(matching, key=lambda item: item.id)


def _truncate(text: str, width: int, texts: Mapping) -> str:
    """``text`` cut to ``width`` characters, the last one the ellipsis when it was cut."""
    return text if len(text) <= width else text[: width - 1] + texts["ellipsis"]


def format_summary(item: KitSummary, texts: Mapping) -> str:
    """One ``list`` line; an absent value is the empty cell and the age is whole days (``3d``)."""
    empty = texts["empty_cell"]
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


# --------------------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common.add_argument(
        "--root",
        "--project-root",
        dest="root",
        type=Path,
        help="Project root. Defaults to the nearest parent holding AGENTS.md beside the dev layer.",
    )
    parser = argparse.ArgumentParser(description="Park work into a kit and resume it.", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    write = commands.add_parser("write", parents=[common], help="Park a piece of work.", allow_abbrev=False)
    write.add_argument("id")
    write.add_argument("--name", required=True)
    write.add_argument("--goal", required=True)
    write.add_argument("--next", dest="next_action", required=True)
    write.add_argument("--title", default="")
    write.add_argument("--plan", default="")
    write.add_argument("--row", default="")
    write.add_argument("--branch", default="")
    write.add_argument("--revision", action="append", default=[])
    write.add_argument("--owned-path", action="append", default=[])
    write.add_argument("--check", action="append", default=[])
    write.add_argument("--unverified", action="append", default=[])
    write.add_argument("--decision", action="append", default=[])
    write.add_argument("--answer", action="append", default=[])
    write.add_argument("--agent", action="append", default=[])
    write.add_argument("--readiness", default="")
    write.add_argument("--harness", default="")
    write.add_argument("--session-id", default="")
    write.add_argument("--machine", default="")
    write.add_argument("--peer", action="append", default=[])
    write.add_argument("--origin", default="")
    write.add_argument("--role", default="")

    unpark = commands.add_parser("unpark", parents=[common], help="Resume a parked kit.", allow_abbrev=False)
    unpark.add_argument("id")

    digest_cmd = commands.add_parser("digest", parents=[common], help="Print the capped digest.", allow_abbrev=False)
    digest_cmd.add_argument("id")
    digest_cmd.add_argument("--cap", type=int, default=None)

    listing = commands.add_parser("list", parents=[common], help="List the kits.", allow_abbrev=False)
    listing.add_argument("--plan", default="")
    listing.add_argument("--state", default="")
    listing.add_argument("--status", default="")
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
        branch=args.branch.strip(),
        revisions=_stripped(args.revision),
        owned_paths=_stripped(args.owned_path),
        sessions=_session_refs(args, texts),
        peers=_stripped(args.peer),
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


def _run(args: argparse.Namespace, texts: Mapping) -> int:
    root = _project_root(args.root, texts)
    if args.command == "write":
        fields = _fields_from(args, texts)
        options = WriteOptions(args.title.strip(), args.role.strip())
        kit = write_kit(fields, _body_from(args), root, options, texts)
        print(kit.relative_to(root).as_posix())
    elif args.command == "unpark":
        print(unpark_kit(find_kit(root, args.id.strip(), texts), root, texts))
    elif args.command == "digest":
        cap = texts["default_cap"] if args.cap is None else args.cap
        if cap < 0:
            raise _error(texts, "bad_cap", value=cap)
        print(digest(find_kit(root, args.id.strip(), texts), cap, root, texts))
    else:
        query = ListQuery(args.plan.strip(), args.state.strip(), args.status.strip())
        items = list_kits(root, query, time.time(), texts)
        if items:
            print("\n".join(format_summary(item, texts) for item in items))
        elif not _kit_names(root):
            print(jsondata.fill(texts["list"]["empty"], {"path": ergon_root(root).relative_to(root).as_posix()}))
        else:
            print(texts["list"]["no_match"])
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: ``write``, ``unpark``, ``digest`` or ``list``; a failure is one stderr line and exit 1."""
    args = _build_parser().parse_args(argv)
    texts = _texts()
    try:
        return _run(args, texts)
    except ParkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
