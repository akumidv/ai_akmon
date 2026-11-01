"""The learning agent's run record and its reminder — the one owner (C177, ADR 0026/D07).

The learning agent reads the sessions of the project it serves, recorded since its last run. This
module keeps that record — ``<dev root>/.local/learning.json`` in the project's local layer
(ADR 0022), gitignored — and decides when a session-start hook should remind the owner to run it.

State is three fields: ``last_run`` (UTC ISO seconds, ``null`` before the first run), ``since``
(when counting began: the first session recorded while no run exists) and ``sessions`` (the
distinct session ids seen since the last run). A missing or unreadable file is empty state, not an
error — the next write replaces it. Writes are atomic (temp file in the same directory, then
rename), so a hook killed mid-write leaves the old file or the new one, never half of one. A write
that follows a read (``record_session``, ``mark_run``) holds an exclusive lock file beside the state
(``learning.json.lock``, created with ``O_EXCL``): a short bounded retry, a stale lock past its
timeout is taken over, and a lock that cannot be taken raises :class:`StateLockedError` — the hook
gives up silently on it, ``akmon learn mark`` reports it.

Everything that reads the world — the clock, the file, the thresholds in
``<dev root>/.akmon.toml`` — is read at the entry point and passed down; the decision functions
take values. The JavaScript twin is ``js/common/learning.mjs``; the texts and thresholds'
defaults are ``common/learning.json``'s, shared by both.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common import jsondata
from common.project_root import aitna_root
from common.record import recorded_table

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_TIME_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_SECONDS_PER_DAY = 24 * 60 * 60


@dataclass(frozen=True)
class LearningState:
    """What the local layer records of the learning run: the last run, the counting start, the sessions since."""

    last_run: str | None = None
    since: str | None = None
    sessions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Thresholds:
    """When the reminder fires: this many sessions, or this many days, since the last run."""

    reminder_sessions: int
    reminder_days: int


@dataclass(frozen=True)
class SessionEvent:
    """A session start as the hook payload names it: its id and how it began (``startup``, ``compact`` …).

    ``attended`` is whether a person is at the session; an unattended run (``claude -p``) is recorded
    but never reminded, since nobody is there to act on the reminder.
    """

    session_id: str | None
    source: str | None
    attended: bool = True


@dataclass(frozen=True)
class Due:
    """A reminder that is due: how many sessions and whole days have passed."""

    sessions: int
    days: int
    since_run: bool


class StateLockedError(RuntimeError):
    """The state file's lock could not be taken within the retry window."""


def read_data() -> dict[str, Any]:
    """The learning data file beside this module: state path, threshold defaults, reminder and CLI texts."""
    return jsondata.read(Path(__file__).parent / "learning.json")


def format_utc(moment: datetime) -> str:
    """``moment`` as the UTC ISO-seconds text the state file records (``2026-10-28T09:30:00Z``)."""
    return moment.astimezone(UTC).strftime(_TIME_FORMAT)


def parse_utc(text: str) -> datetime:
    """The moment a recorded UTC ISO-seconds ``text`` names.

    Raises:
        ValueError: ``text`` is not in the ``format_utc`` shape, or names no real moment.
    """
    if not _TIME_SHAPE.fullmatch(text):
        raise ValueError(f"not a UTC ISO-seconds time: {text!r}")
    return datetime.strptime(text, _TIME_FORMAT).replace(tzinfo=UTC)


def is_second_opinion(environ: Mapping[str, str], data: Mapping[str, Any]) -> bool:
    """Whether this is a second-opinion run (``tools/model_routing/second_opinion.py``), not an owner session."""
    return bool(environ.get(data["second_opinion_variable"]))


def is_attended(environ: Mapping[str, str], data: Mapping[str, Any]) -> bool:
    """Whether a person is at the session: false only when the harness says ``0`` (M199, M200); absent is attended."""
    return environ.get(data["attended_variable"]) != "0"


def session_event(
    session_id: str | None, source: str | None, environ: Mapping[str, str], data: Mapping[str, Any]
) -> SessionEvent | None:
    """The session start a hook records and reminds on, or ``None`` when it is not one of the owner's.

    A second-opinion run (:func:`is_second_opinion`) is neither recorded nor reminded; an
    unattended session is recorded, never reminded. The hook reads ``environ`` once at its entry
    point and passes it here — nothing below reads the process environment.
    """
    if is_second_opinion(environ, data):
        return None
    return SessionEvent(session_id, source, is_attended(environ, data))


def state_path(project_root: Path, data: dict[str, Any]) -> Path:
    """Where the project's learning record lives: under the local layer of ``<dev root>`` (ADR 0022)."""
    return aitna_root(project_root) / data["state_rel"]


def _moment_or_none(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    try:
        parse_utc(value)
    except ValueError:
        return False
    return True


def read_state(path: Path) -> LearningState:
    """The recorded state, or the empty state when ``path`` is missing, unreadable or not a valid record."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return LearningState()
    if not isinstance(loaded, dict):
        return LearningState()
    last_run, since, sessions = loaded.get("last_run"), loaded.get("since"), loaded.get("sessions")
    if not (_moment_or_none(last_run) and _moment_or_none(since)):
        return LearningState()
    if not isinstance(sessions, list) or not all(isinstance(item, str) and item for item in sessions):
        return LearningState()
    return LearningState(last_run, since, tuple(dict.fromkeys(sessions)))


def write_state(state: LearningState, path: Path) -> None:
    """Persist ``state`` at ``path`` atomically: a temp file in the same directory, then a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"last_run": state.last_run, "since": state.since, "sessions": list(state.sessions)}
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(document, indent=2) + "\n")
        Path(temp_name).replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(temp_name).unlink()
        raise


@contextlib.contextmanager
def _locked(path: Path, data: Mapping[str, Any]) -> Iterator[None]:
    """Hold the exclusive lock file beside ``path`` for the block.

    Created with ``O_EXCL``; a contended lock is retried every ``poll_seconds`` for ``wait_seconds``
    (``learning.json``'s ``lock``), and one older than ``stale_seconds`` is a crashed holder's, taken over.

    Raises:
        StateLockedError: the lock stayed held for the whole window.
    """
    settings = data["lock"]
    lock = path.with_name(path.name + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + settings["wait_seconds"]
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            _drop_stale(lock, settings["stale_seconds"])
            if time.monotonic() >= deadline:
                raise StateLockedError(f"{lock} is held by another process") from None
            time.sleep(settings["poll_seconds"])
            continue
        break
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(f"{os.getpid()}\n")
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


def _drop_stale(lock: Path, stale_seconds: float) -> None:
    """Remove ``lock`` when it is older than ``stale_seconds``; a lock that vanished meanwhile is fine."""
    try:
        age = time.time() - lock.stat().st_mtime
        if age > stale_seconds:
            lock.unlink()
    except OSError:
        return


def record_session(path: Path, session_id: str, now: datetime, data: Mapping[str, Any]) -> LearningState:
    """Record ``session_id`` as seen at ``now`` and return the new state; a known id changes nothing.

    The first session recorded while no run exists starts the count (``since``). A resumed or
    compacted session keeps its id, so it is not counted twice; an already-known id writes nothing.

    Raises:
        StateLockedError: another process holds the state's lock for the whole retry window.
    """
    known = read_state(path)
    if session_id in known.sessions:
        return known  # the common resume: no lock, no write
    with _locked(path, data):
        state = read_state(path)
        if session_id in state.sessions:
            return state
        since = state.since if state.since is not None or state.last_run is not None else format_utc(now)
        updated = LearningState(state.last_run, since, (*state.sessions, session_id))
        write_state(updated, path)
        return updated


def mark_run(path: Path, now: datetime, data: Mapping[str, Any]) -> LearningState:
    """Record the end of a learning run at ``now``: ``last_run`` set, the counted sessions and ``since`` cleared.

    Raises:
        StateLockedError: another process holds the state's lock for the whole retry window.
    """
    with _locked(path, data):
        updated = LearningState(format_utc(now), None, ())
        write_state(updated, path)
        return updated


def days_since(state: LearningState, now: datetime) -> int | None:
    """Whole days from the last run (or, before any run, from the counting start) to ``now``; ``None`` with neither."""
    baseline = state.last_run or state.since
    if baseline is None:
        return None
    return max(0, int((now - parse_utc(baseline)).total_seconds() // _SECONDS_PER_DAY))


def _positive_int(value: object, default: int) -> int:
    """``value`` as a positive integer, else ``default`` — the lenient record reader hands back strings."""
    if isinstance(value, bool):
        return default
    if isinstance(value, str):
        value = value.strip()
        value = int(value) if value.isascii() and value.isdecimal() else None
    if isinstance(value, int) and value > 0:
        return value
    return default


def read_thresholds(project_root: Path, data: dict[str, Any]) -> Thresholds:
    """The reminder thresholds: ``[learning]`` of ``<dev root>/.akmon.toml`` over the shipped defaults.

    A missing section, a missing key and a value that is not a positive integer each fall back to
    the default — a hook consulting the record never aborts a session over it.
    """
    table = recorded_table(project_root, data["record_section"])
    return Thresholds(
        _positive_int(table.get("reminder_sessions"), data["reminder_sessions"]),
        _positive_int(table.get("reminder_days"), data["reminder_days"]),
    )


def reminder_due(state: LearningState, thresholds: Thresholds, now: datetime) -> Due | None:
    """The reminder to give, or ``None``.

    Due when at least one session has passed since the last run **and** either the session count
    reached ``reminder_sessions`` or the days since the last run (before any run: since counting
    began) reached ``reminder_days``.
    """
    count = len(state.sessions)
    if count < 1:
        return None
    days = days_since(state, now)
    if count >= thresholds.reminder_sessions or (days is not None and days >= thresholds.reminder_days):
        return Due(count, days or 0, state.last_run is not None)
    return None


def _counted(count: int, one: str, many: str) -> str:
    """``count`` with its noun: ``1 session``, ``12 sessions``."""
    return f"{count} {one if count == 1 else many}"


def reminder_texts(due: Due, data: dict[str, Any]) -> tuple[str, str]:
    """The reminder as ``(for the model, for the owner)``."""
    texts = data["reminder"]
    values = {
        "sessions": _counted(due.sessions, texts["session_one"], texts["session_many"]),
        "days": _counted(due.days, texts["day_one"], texts["day_many"]),
    }
    suffix = "since_run" if due.since_run else "since_start"
    return jsondata.fill(texts[f"model_{suffix}"], values), jsondata.fill(texts[f"owner_{suffix}"], values)


def session_reminder(
    state: LearningState, source: str | None, thresholds: Thresholds, now: datetime, data: dict[str, Any]
) -> tuple[str, str] | None:
    """What a session start says about the learning run — ``(for the model, for the owner)`` — or ``None``.

    Silent on a ``source`` the data lists in ``skip_sources`` (a compaction: the same session, whose
    model was already told) and whenever :func:`reminder_due` finds nothing due. ``state`` is what
    was recorded *before* this session: a session counts only once it has passed.
    """
    if source in data["skip_sources"]:
        return None
    due = reminder_due(state, thresholds, now)
    return None if due is None else reminder_texts(due, data)


def record_and_remind(
    path: Path, event: SessionEvent, thresholds: Thresholds, now: datetime, data: dict[str, Any]
) -> tuple[str, str] | None:
    """The one SessionStart step both harnesses take: decide what is due, then record the session.

    Changes state *and* returns, by design — the hook has one step to run and both halves belong to
    it; the two parts are :func:`session_reminder` and :func:`record_session`. The decision is taken
    on the state *before* this session: the session just starting has not "passed" (ADR 0026/D07), so
    ten sessions are counted when the eleventh starts. No reminder for an unattended run
    (``event.attended`` false), which is still recorded. An unidentified session
    (``event.session_id`` is ``None`` or empty) cannot be deduplicated, so it is not recorded. A
    record that cannot be locked is given up on silently: no reminder, no write, no wait.
    """
    before = read_state(path)
    reminder = session_reminder(before, event.source, thresholds, now, data) if event.attended else None
    if event.session_id:
        try:
            record_session(path, event.session_id, now, data)
        except StateLockedError:
            return None
    return reminder
