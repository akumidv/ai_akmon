"""Where a project's agent sessions are recorded, and which of them a learning run may read.

The owner of three facts that ``tools/model_routing/stats.py`` held alone until C177 and a second
reader (``akmon learn``) needed: how Claude Code names a project's transcript directory, which of
its files is the newest, and — new — which session files of *this* project changed since a given
moment. ``stats.py`` imports the first three from here; there is no second copy.

Claude Code writes ``~/.claude/projects/<munged-root>/<session-id>.jsonl``; Codex writes
``~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*.jsonl`` whose first line is a ``session_meta`` record
carrying the session's ``id`` and ``cwd``. A learning run reads this project's sessions only
(ADR 0026/D07): a Claude directory is the one named by the project root, or one named by a path
inside it (the munged name followed by ``-``) whose transcripts record a ``cwd`` inside the root;
a Codex file counts only when its recorded ``cwd`` is the root or inside it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from common.project_root import resolve_path

#: The kinds a session file can be: ``claude`` and ``codex`` name the harness that wrote it.
CLAUDE = "claude"
CODEX = "codex"

_ASTRAL = 0xFFFF
_CWD_SCAN_BYTES = 1 << 20


@dataclass(frozen=True)
class SessionFile:
    """One recorded session of a project: which harness wrote it, its id, when it last changed, its size."""

    kind: str
    session_id: str
    modified: datetime
    size: int
    path: Path


def munged_project_dir(project_root: Path) -> str:
    """The ``~/.claude/projects/`` directory name for a project root: every non-alphanumeric character → ``-``.

    Claude Code replaces each UTF-16 code unit outside ``[A-Za-z0-9]`` with ``-``, so ``_`` and ``.``
    in a path become dashes as ``/`` does (``/home/a/_cto`` → ``-home-a--cto``, read off the
    directories on disk; M203 says which cases were observed and which are inferred); an astral
    character is two code units, hence two dashes. The very long path Claude Code truncates and
    hashes is not reproduced.
    """
    text = str(project_root.resolve())
    return "".join(
        char if char.isascii() and char.isalnum() else "-" * (2 if ord(char) > _ASTRAL else 1) for char in text
    )


def transcripts_dir(project_root: Path, claude_home: Path | None = None) -> Path:
    """The project's transcript directory under ``<claude_home>/projects/``."""
    home = claude_home or (Path.home() / ".claude")
    return home / "projects" / munged_project_dir(project_root)


def newest_jsonl(directory: Path) -> Path | None:
    """The most recently modified ``*.jsonl`` file in ``directory`` — the current session."""
    if not directory.is_dir():
        return None
    candidates = [path for path in directory.iterdir() if path.is_file() and path.suffix == ".jsonl"]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _modified_after(path: Path, since: datetime | None) -> SessionFile | None:
    """``path`` as a session file stamped with its mtime (UTC), or ``None``.

    ``None`` when it is not newer than ``since`` and when the file is gone — a session file can
    vanish between the listing of its directory and the ``stat``.
    """
    try:
        info = path.stat()
    except OSError:
        return None
    modified = datetime.fromtimestamp(info.st_mtime, tz=UTC)
    if since is not None and modified <= since:
        return None
    return SessionFile(CLAUDE, path.stem, modified, info.st_size, path)


def _is_inside(path: Path, root: Path) -> bool:
    """Whether the resolved ``path`` is ``root`` or lies inside it."""
    return path == root or root in path.parents


def _recorded_cwd(path: Path) -> Path | None:
    """The ``cwd`` of the first line of the Claude transcript ``path`` that records one, else ``None``.

    Only the first ``_CWD_SCAN_BYTES`` are read (a final line cut by that limit is dropped), and a
    line that is not a JSON object or is not UTF-8 is passed over: the first lines of a transcript
    are bookkeeping records with no ``cwd``.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(_CWD_SCAN_BYTES)
    except OSError:
        return None
    lines = head.split(b"\n")
    if len(head) == _CWD_SCAN_BYTES:
        lines.pop()
    for line in lines:
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        recorded = record.get("cwd") if isinstance(record, dict) else None
        if isinstance(recorded, str) and recorded and "\0" not in recorded:
            return resolve_path(Path(recorded))
    return None


def claude_sessions(
    project_root: Path, claude_home: Path | None = None, since: datetime | None = None
) -> list[SessionFile]:
    """This project's Claude transcripts modified after ``since`` (all when ``None``), oldest first.

    Two kinds of directory under ``<claude_home>/projects/`` count. The one named by the project
    root (:func:`munged_project_dir`) is the project's own. One whose name is that name followed by
    ``-`` is a session started in a path *inside* the root (``<root>/sub`` → ``<munged>-sub``) — but
    ``<root>-x`` munges the same way, so each of its transcripts must record a ``cwd`` that is the
    root or inside it; a sibling's, or a transcript recording none, is left out. Only top-level
    ``*.jsonl`` files are read — the subagent transcripts under ``<session-id>/subagents/`` belong to
    the session that spawned them. A file that vanishes during the listing is skipped.
    """
    base = (claude_home or (Path.home() / ".claude")) / "projects"
    if not base.is_dir():
        return []
    name = munged_project_dir(project_root)
    root = resolve_path(project_root)
    found: list[SessionFile] = []
    for directory in base.iterdir():
        own = directory.name == name
        if not (own or directory.name.startswith(f"{name}-")) or not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.suffix != ".jsonl" or not path.is_file():
                continue
            item = _modified_after(path, since)
            if item is None:
                continue
            recorded = None if own else _recorded_cwd(path)
            if own or (recorded is not None and _is_inside(recorded, root)):
                found.append(item)
    return sorted(found, key=lambda item: (item.modified, item.path.name))


def _codex_meta(path: Path) -> dict | None:
    """The ``payload`` of a rollout's first line when it is a ``session_meta`` record, else ``None``."""
    try:
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
        record = json.loads(first)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    payload = record.get("payload") if isinstance(record, dict) and record.get("type") == "session_meta" else None
    return payload if isinstance(payload, dict) else None


def codex_sessions(
    project_root: Path, codex_home: Path | None = None, since: datetime | None = None
) -> list[SessionFile]:
    """The Codex sessions of this project modified after ``since``, oldest first; ``[]`` when Codex left none.

    A rollout counts when its recorded ``cwd`` resolves to the project root or inside it. A subagent rollout
    (``source`` is an object, M8) belongs to its parent session and is left out. An absent
    ``sessions`` directory and an unreadable or unrecognised file are skipped silently.
    """
    home = codex_home or (Path.home() / ".codex")
    base = home / "sessions"
    if not base.is_dir():
        return []
    root = resolve_path(project_root)
    found: list[SessionFile] = []
    for path in base.rglob("*.jsonl"):
        if not path.is_file():
            continue
        item = _modified_after(path, since)
        meta = _codex_meta(path) if item is not None else None
        if item is None or meta is None or isinstance(meta.get("source"), dict):
            continue
        recorded, session_id = meta.get("cwd"), meta.get("id")
        if not isinstance(recorded, str) or not recorded or not isinstance(session_id, str) or not session_id:
            continue
        if _is_inside(resolve_path(Path(recorded)), root):
            found.append(SessionFile(CODEX, session_id, item.modified, item.size, path))
    return sorted(found, key=lambda item: (item.modified, item.path.name))
