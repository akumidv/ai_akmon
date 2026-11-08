"""The work style in force — the one owner of where it is set and how it is read (ADR 0031/D03).

A work style says how a ``developer`` run splits the work with the developer: ``delegating`` (the
default) or ``controlling`` (ADR 0031/D02). It never widens a permission (D01). The first of these
that holds a valid value decides:

1. **session** — the owner typed ``/style delegating`` or ``/style controlling``; the
   ``UserPromptSubmit`` hook :func:`record_and_reply` records it for that ``session_id`` in
   ``<dev root>/.local/work-sessions.json`` (the most recent ``sessions_keep`` entries stay);
2. **developer** — ``<dev root>/.local/work.json``, key ``style``, untracked;
3. **project** — ``[work] style`` in ``<dev root>/.akmon.toml``, through the lenient record reader;
4. **default** — ``delegating``.

A value that is not a style is skipped at its level and the next level decides. Every reader here
is lenient (a missing or unreadable file is no value) so a hook consulting the style never aborts
a session over it; the one write, the session store, is atomic (a temp file in the same
directory, then a rename).

Everything that reads the world — the payload, the clock, the data file — is read at the entry
point and passed down. The JavaScript twin is ``js/common/work_style.mjs``; the texts and
constants are ``common/work_style.json``'s, shared by both.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from common import jsondata
from common.project_root import aitna_root
from common.record import recorded_table

StyleSource = Literal["session", "developer", "project", "default"]


@dataclass(frozen=True)
class WorkStyle:
    """The style in force and the level that decided it."""

    style: str
    source: StyleSource


def read_data() -> dict[str, Any]:
    """The work-style data file beside this module: the styles, the file locations, the hook texts."""
    return jsondata.read(Path(__file__).parent / "work_style.json")


def developer_path(project_root: Path, data: Mapping[str, Any]) -> Path:
    """Where the developer's own setting lives: under the local layer of ``<dev root>`` (ADR 0022)."""
    return aitna_root(project_root) / data["developer_rel"]


def sessions_path(project_root: Path, data: Mapping[str, Any]) -> Path:
    """Where the per-session styles live: beside the developer's setting, in the local layer."""
    return aitna_root(project_root) / data["sessions_rel"]


def _load_object(path: Path) -> dict[str, Any]:
    """The JSON object in ``path``, or ``{}`` when it is missing, unreadable or not an object."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _valid(value: object, data: Mapping[str, Any]) -> str | None:
    """``value`` when it is one of the styles, else ``None`` (the level is skipped)."""
    return value if isinstance(value, str) and value in data["styles"] else None


def read_sessions(path: Path, data: Mapping[str, Any]) -> dict[str, str]:
    """The recorded per-session styles in recorded order, oldest first; an entry that is not a style is dropped."""
    table = _load_object(path).get("sessions")
    if not isinstance(table, dict):
        return {}
    return {key: value for key, value in table.items() if key and _valid(value, data)}


def read_developer(path: Path, data: Mapping[str, Any]) -> str | None:
    """The developer's ``style``, or ``None`` when the file, the key or the value is missing or invalid."""
    return _valid(_load_object(path).get("style"), data)


def read_project(project_root: Path, data: Mapping[str, Any]) -> str | None:
    """The project's ``[work] style``, or ``None`` when the record, table, key or value is missing or invalid."""
    return _valid(recorded_table(project_root, data["record_section"]).get(data["record_key"]), data)


def resolve(project_root: Path, session_id: str | None, data: Mapping[str, Any]) -> WorkStyle:
    """The style in force for ``session_id`` and where it came from, first valid level wins (ADR 0031/D03)."""
    if session_id:
        recorded = read_sessions(sessions_path(project_root, data), data).get(session_id)
        if recorded is not None:
            return WorkStyle(recorded, "session")
    developer = read_developer(developer_path(project_root, data), data)
    if developer is not None:
        return WorkStyle(developer, "developer")
    project = read_project(project_root, data)
    if project is not None:
        return WorkStyle(project, "project")
    return WorkStyle(data["default"], "default")


def typed_style(prompt: str, data: Mapping[str, Any]) -> str | None:
    """The text after ``/style`` when the whole ``prompt`` is that command, else ``None``.

    The prompt is trimmed; the command is the first word, so ``/styles x`` is not it. The text is
    returned as typed (``""`` for a bare ``/style``) — whether it names a style is :func:`known_style`'s.
    """
    command = data["command"]
    text = prompt.strip()
    if not text.startswith(command):
        return None
    rest = text[len(command) :]
    if rest and rest == rest.lstrip():
        return None
    return rest.strip()


def known_style(typed: str, data: Mapping[str, Any]) -> str | None:
    """The style ``typed`` names, case-insensitive, or ``None``."""
    return _valid(typed.lower(), data)


def write_sessions(sessions: Mapping[str, str], path: Path) -> None:
    """Persist ``sessions`` at ``path`` atomically: a temp file in the same directory, then a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"sessions": dict(sessions)}, indent=2) + "\n")
        Path(temp_name).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(temp_name).unlink()
        raise


def record_session_style(path: Path, session_id: str, style: str, data: Mapping[str, Any]) -> None:
    """Record ``style`` for ``session_id`` as the most recent entry and keep the newest ``sessions_keep``.

    A later write for the same session moves it to the newest place. No lock is taken: two sessions
    typing ``/style`` in the same instant can lose one entry, which reads as the next level's style.
    """
    sessions = read_sessions(path, data)
    sessions.pop(session_id, None)
    sessions[session_id] = style
    write_sessions(dict(list(sessions.items())[-data["sessions_keep"] :]), path)


def record_and_reply(project_root: Path, session_id: str | None, prompt: str, data: Mapping[str, Any]) -> str | None:
    """Handle a typed prompt: record a valid ``/style`` for the session and return the reply, else ``None``.

    ``None`` means the prompt is not a ``/style`` command, and nothing is written. A value that
    names no style, or a payload with no session id, writes nothing and returns the text saying so.
    """
    typed = typed_style(prompt, data)
    if typed is None:
        return None
    style = known_style(typed, data)
    if style is None:
        return jsondata.fill(data["invalid"], {"value": typed, "allowed": ", ".join(data["styles"])})
    if not session_id:
        return jsondata.fill(data["no_session"], {"style": style, "developer_file": data["developer_rel"]})
    record_session_style(sessions_path(project_root, data), session_id, style, data)
    return jsondata.fill(data["recorded"], {"style": style})
