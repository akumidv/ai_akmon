"""``akmon learn`` — the learning agent's run record and its session list (C177, ADR 0026/D07).

The record, the thresholds, the texts and the session-file discovery are ``common/learning.py``'s
and ``common/transcripts.py``'s; this module is the command line over them. Imported lazily by
``akmon.cli``, as ``trust`` is. It reads only the sessions of the project the cwd belongs to —
never another project's (ADR 0026/D07).

The JavaScript twin is ``js/akmon/_learn.mjs``; the texts and exit codes are the same.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO

from akmon import _tree, cli

_SUBCOMMANDS = ("status", "sessions", "mark")
_AT_ARGUMENTS = 2  # ``--at`` and its time


@dataclass(frozen=True)
class LearnIO:
    """What the command touches of the process: environment, cwd, streams and the clock."""

    environ: Mapping[str, str]
    cwd: Path
    out: TextIO
    err: TextIO
    now: Callable[[], datetime]


def process_io() -> LearnIO:
    """The real process: its environment, cwd and streams, and the wall clock."""
    return LearnIO(os.environ, Path.cwd(), sys.stdout, sys.stderr, lambda: datetime.now(UTC))


def _home(environ: Mapping[str, str], variable: str, default: str) -> Path:
    """A harness home: the directory ``variable`` names, else ``~/<default>``."""
    named = environ.get(variable)
    return Path(named) if named else Path.home() / default


@dataclass(frozen=True)
class _Options:
    """The flags of ``sessions`` (``--all``) and ``mark`` (``--at``)."""

    list_all: bool = False
    at: str | None = None
    project_root: Path | None = None


_PROJECT_ROOT_FLAG = "--project-root"


def _take_project_root(rest: Sequence[str]) -> tuple[Path | None, list[str]]:
    """``--project-root PATH`` taken out of ``rest``, and what is left.

    Raises:
        ValueError: the flag is repeated or has no path.
    """
    remaining = list(rest)
    if _PROJECT_ROOT_FLAG not in remaining:
        return None, remaining
    index = remaining.index(_PROJECT_ROOT_FLAG)
    if index + 1 >= len(remaining) or remaining[index + 1].startswith("--"):
        raise ValueError(f"{_PROJECT_ROOT_FLAG} takes a path")
    given = Path(remaining[index + 1])
    del remaining[index : index + 2]
    if _PROJECT_ROOT_FLAG in remaining:
        raise ValueError(f"{_PROJECT_ROOT_FLAG} given twice")
    return given, remaining


def _options(command: str, rest: Sequence[str]) -> _Options:
    """The flags ``command`` takes out of ``rest``; ``--project-root PATH`` is taken by every command.

    Raises:
        ValueError: a flag the command does not take, a repeated one, or ``--at`` without a time.
    """
    project_root, rest = _take_project_root(rest)
    if command == "sessions" and rest == ["--all"]:
        return _Options(list_all=True, project_root=project_root)
    if command == "mark" and rest and rest[0] == "--at":
        if len(rest) != _AT_ARGUMENTS:
            raise ValueError("mark --at takes one time, e.g. 2026-10-28T09:30:00Z")
        return _Options(at=rest[1], project_root=project_root)
    if rest:
        takes = {"sessions": "only --all", "mark": "only --at TIME"}.get(command, "no arguments")
        raise ValueError(f"{command} takes {takes}; got {rest[0]!r}")
    return _Options(project_root=project_root)


class _Learn:
    """One run of ``akmon learn`` in the project the cwd belongs to."""

    def __init__(self, io: LearnIO, explicit_root: Path | None = None) -> None:
        tree = _tree.embedded_tree_root()
        self.io = io
        self.lib: ModuleType = cli._embedded_common_module(tree, "learning")
        self.transcripts: ModuleType = cli._embedded_common_module(tree, "transcripts")
        self.jsondata: ModuleType = cli._embedded_common_module(tree, "jsondata")
        resolver = cli._embedded_common_module(tree, "project_root")
        self.root, notice = resolver.resolve_project_root(
            None if explicit_root is None else io.cwd / explicit_root, io.cwd
        )
        self.rooted = notice is None
        if notice:
            io.err.write(notice + "\n")
        self.data: dict[str, Any] = self.lib.read_data()
        self.path = self.lib.state_path(self.root, self.data)
        self.texts: dict[str, str] = self.data["cli"]

    def _say(self, key: str, **values: object) -> None:
        text = self.jsondata.fill(self.texts[key], {name: str(value) for name, value in values.items()})
        self.io.out.write(text + "\n")

    def status(self) -> int:
        state = self.lib.read_state(self.path)
        thresholds = self.lib.read_thresholds(self.root, self.data)
        days = self.lib.days_since(state, self.io.now())
        if state.last_run is None:
            self._say("status_never_run")
        else:
            self._say("status_last_run", last_run=state.last_run)
        if state.since is None:
            self._say("status_not_counting")
        else:
            self._say("status_since", since=state.since)
        self._say("status_sessions", count=len(state.sessions))
        if days is None:
            self._say("status_days_none")
        else:
            self._say("status_days", days=days)
        self._say("status_thresholds", sessions=thresholds.reminder_sessions, days=thresholds.reminder_days)
        self._say("status_state", path=self.path.relative_to(self.root).as_posix())
        return 0

    def sessions(self, options: _Options) -> int:
        """List this project's sessions modified since the last run, or since counting began before a first run.

        The first line is the listing time: ``mark --at`` stamps it, so activity after the listing is
        not swallowed by the run. ``options.list_all`` ignores the record and lists every session.
        """
        listed_at = self.lib.format_utc(self.io.now())
        state = self.lib.read_state(self.path)
        bound = None if options.list_all else state.last_run or state.since
        since = self.lib.parse_utc(bound) if bound else None
        self._say("sessions_listed_at", listed_at=listed_at)
        found = [
            *self.transcripts.claude_sessions(self.root, _home(self.io.environ, "CLAUDE_CONFIG_DIR", ".claude"), since),
            *self.transcripts.codex_sessions(self.root, _home(self.io.environ, "CODEX_HOME", ".codex"), since),
        ]
        found.sort(key=lambda item: (item.modified, item.path.name))
        if not found:
            self._say("sessions_none" if bound else "sessions_none_ever", since=bound)
            return 0
        self._say("sessions_header")
        for item in found:
            modified = self.lib.format_utc(item.modified)
            self.io.out.write(f"{item.kind}\t{item.session_id}\t{modified}\t{item.size}\t{item.path}\n")
        return 0

    def mark(self, at: str | None) -> int:
        """Record the end of a run at ``at`` (a UTC ISO-seconds time, normally the listing time) or now.

        With no project root there is no local layer to record in: the notice was already printed, and
        nothing is written (ADR 0022 D09).

        Raises:
            ValueError: ``at`` is not a UTC ISO-seconds time, or lies after the current time.
        """
        if not self.rooted:
            return 2
        now = self.io.now()
        moment = now if at is None else self.lib.parse_utc(at)
        if moment > now:
            raise ValueError(self.jsondata.fill(self.texts["mark_future"], {"at": at, "now": self.lib.format_utc(now)}))
        state = self.lib.mark_run(self.path, moment, self.data)
        self._say("marked", last_run=state.last_run)
        return 0


def _usage_error(io: LearnIO, usage: str, message: str) -> int:
    io.err.write(f"akmon learn: {message}\n{usage}")
    return 2


def _run(session: _Learn, command: str, options: _Options) -> int:
    """Run ``command`` of the validated ``_SUBCOMMANDS`` on ``session``."""
    if command == "status":
        return session.status()
    return session.sessions(options) if command == "sessions" else session.mark(options.at)


def main(argv: Sequence[str], io: LearnIO | None = None) -> int:
    """Run ``akmon learn <subcommand>``; ``io`` is the process unless a test hands in a fake."""
    io = io if io is not None else process_io()
    usage = cli._embedded_common_module(_tree.embedded_tree_root(), "learning").read_data()["cli"]["usage"]
    if not argv:
        io.err.write(usage)
        return 2
    if argv[0] in ("-h", "--help"):
        io.out.write(usage)
        return 0
    command, rest = argv[0], list(argv[1:])
    if command not in _SUBCOMMANDS:
        return _usage_error(io, usage, f"unknown command {command!r}")
    try:
        options = _options(command, rest)
    except ValueError as exc:
        return _usage_error(io, usage, str(exc))
    try:
        return _run(_Learn(io, options.project_root), command, options)
    except (OSError, RuntimeError, ValueError) as exc:
        io.err.write(f"akmon learn: {exc}\n")
        return 2
