"""Trust in a project's own grant files by an owner-accepted digest — the one owner (C172).

ADR 0025 D04 and D05 fix the contract. Grants a project declares in its own tracked files take
effect only once the owner accepted their content; the record of acceptance sits in a user-level
store outside every checkout, where an autonomous run cannot write.

- **Digest** — the SHA-256 of the file's bytes, hex. It is content-keyed: not bound to a project
  or a path, so the same text in another clone or at another path is already accepted.
- **Store** — ``$AKMON_TRUST_DIR``, else ``$XDG_STATE_HOME/akmon/trust``, else
  ``~/.local/state/akmon/trust`` (:func:`resolve_store`), and never inside the project's checkout: a
  store the project's own files could reach would let the project ship pre-accepted copies, so a
  resolved path (symbolic links followed) inside the resolved project root is refused.
  ``accepted/<digest>`` is a byte copy of
  every accepted file and its existence *is* the acceptance; ``trust.log`` is the append-only TSV
  record of what happened: ``timestamp · event · digest · path · project · previous`` with
  ``-`` for an absent field. The store directory is created by the first write, never by a read.
- **State of a file** — ``trusted`` (its digest is accepted), ``changed`` (it is not, and an
  earlier version at the same path *of the same project* is), ``new`` (it is not, and no version at
  that path of that project is). The digest is content-keyed; the history is keyed by (project
  name, relative path), so a new file in one project is never presented as a change of another's.
  Another project's accepted version of the same relative path is still found
  (:func:`last_accepted_elsewhere`) so the owner can read a diff against it, under its project's name.

Stdlib-only, no project imports beyond ``common``, and nothing at import time. Configuration is
read at the entry point: :func:`resolve_store` takes the environment and the project root as arguments, and no other
function here reads it. Failure is raised as :class:`GrantTrustError`; a missing file or an
unwritable store surfaces as the ``OSError`` it is.

The JavaScript twin is ``js/common/grant_trust.mjs``; both write the same log lines, and the log is
split on the newline character only, so no stdlib-versus-Node difference in what counts as a line break reaches
it. The line diff here is written out rather than taken from ``difflib`` so that both twins print
the same text for the same two files.
"""

from __future__ import annotations

import hashlib
import os
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from common import jsondata, project_root

#: The three kinds of log line.
EVENT_ACCEPT = "accept"
EVENT_REVOKE = "revoke"
EVENT_UNTRUSTED = "untrusted"

#: What stands in a log field with no value.
NO_PREVIOUS = "-"

#: Hex characters of a digest a listing shows, and the shortest prefix a command resolves.
SHORT_DIGEST_LENGTH = 12

_DIGEST_LENGTH = 64
_FIELD_COUNT = 6
_HEX = frozenset("0123456789abcdef")
_STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_EVENTS = (EVENT_ACCEPT, EVENT_REVOKE, EVENT_UNTRUSTED)
_CONTEXT_LINES = 3
# Two files whose differing middle holds more line pairs than this are shown as a full
# replacement instead of a minimal diff: the table is quadratic and grant files are small.
_MAX_DIFF_CELLS = 4_000_000


class GrantTrustError(RuntimeError):
    """A trust operation cannot proceed; the message names the file, digest or line."""


class TrustState(StrEnum):
    """Where a grant file stands: accepted as it is, an accepted path with new content, or unseen."""

    TRUSTED = "trusted"
    NEW = "new"
    CHANGED = "changed"


@dataclass(frozen=True)
class TrustStore:
    """The resolved store: where accepted copies and the log live (nothing is created by resolving)."""

    root: Path
    accepted_dir: Path
    log_path: Path


@dataclass(frozen=True)
class GrantFile:
    """One grant file as read once: what is shown, digested and accepted is these very bytes."""

    relative: str
    project: str
    content: bytes
    digest: str


@dataclass(frozen=True)
class FileTrust:
    """A grant file's state; ``previous`` is the last accepted digest at its path in its project (``None`` when new)."""

    grant: GrantFile
    state: TrustState
    previous: str | None


@dataclass(frozen=True)
class TrustEvent:
    """One log line. ``previous`` is :data:`NO_PREVIOUS` when the path had no accepted version in the project."""

    timestamp: str
    event: str
    digest: str
    path: str
    project: str
    previous: str


@dataclass(frozen=True)
class TrustReport:
    """What the log says: ``median_seconds`` is ``None`` when no sighted digest was later accepted."""

    accepts: int
    reaccepts: int
    revokes: int
    untrusted_digests: int
    accepted_after_sighting: int
    median_seconds: float | None


def _data() -> dict[str, Any]:
    """The layout names beside this module (``grant_trust.json``)."""
    return jsondata.read(Path(__file__).parent / "grant_trust.json")


def resolve_store(environment: Mapping[str, str], root: Path) -> TrustStore:
    """The store ``environment`` names: ``AKMON_TRUST_DIR``, else the XDG state home, else ``~/.local/state``.

    An empty variable is unset, as the XDG specification says of a relative or empty path. The
    directory is not created: only a write does that. The store is the resolved path, symbolic
    links followed, so what was checked is what is written to.

    Raises:
        GrantTrustError: the store lies inside the project at ``root`` (resolved the same way).
    """
    data = _data()
    explicit = environment.get(data["store_env"])
    state_home = environment.get(data["state_home_env"])
    if explicit:
        store_root = Path(explicit)
    elif state_home:
        store_root = Path(state_home) / data["store_subdir"]
    else:
        home = environment.get("HOME") or str(Path.home())
        store_root = Path(home) / data["state_home_subdir"] / data["store_subdir"]
    store_root, project = store_root.resolve(), root.resolve()
    if store_root.is_relative_to(project):
        raise GrantTrustError(
            f"the trust store {store_root} is inside the project {project}; "
            f"set {data['store_env']} to a directory outside the checkout (ADR 0025/D05)"
        )
    return TrustStore(store_root, store_root / data["accepted_dir"], store_root / data["log_file"])


def grants_directory(root: Path) -> Path:
    """The default grant location of the project at ``root``: ``<dev root>/grants`` (ADR 0025 D05, provisional)."""
    return project_root.aitna_root(root) / _data()["grants_dir"]


def list_grant_files(directory: Path) -> tuple[Path, ...]:
    """Every regular file under ``directory``, recursively, sorted by relative path; none when it is absent.

    A symbolic link is not a regular file here, whatever it points at, and a link to a
    directory is not entered.
    """
    found: list[Path] = []
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except (FileNotFoundError, NotADirectoryError):
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                pending.append(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                found.append(Path(entry.path))
    return tuple(sorted(found, key=lambda path: path.relative_to(directory).as_posix()))


def file_digest(path: Path) -> str:
    """The SHA-256 hex digest of the bytes of ``path``."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_grant(path: Path, root: Path) -> GrantFile:
    """Read ``path`` once as a grant file of the project at ``root``.

    Raises:
        GrantTrustError: ``path`` is outside ``root``, or its relative path or the project's
            name holds a tab or a newline, which would break the log's lines.
    """
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise GrantTrustError(f"{path} is outside the project root {root}") from exc
    _require_line_safe(relative, "path")
    _require_line_safe(root.name, "project name")
    content = path.read_bytes()
    return GrantFile(relative, root.name, content, hashlib.sha256(content).hexdigest())


def _require_line_safe(value: str, what: str) -> None:
    if any(character in value for character in "\t\n\r"):
        raise GrantTrustError(f"the {what} {value!r} holds a tab or a line break and cannot be logged")


def format_event(event: TrustEvent) -> str:
    """The log line of ``event``, without its newline."""
    fields = (event.timestamp, event.event, event.digest, event.path, event.project, event.previous)
    return "\t".join(fields)


def parse_event(line: str) -> TrustEvent:
    """The event a log ``line`` records.

    Raises:
        GrantTrustError: the line does not hold six fields or names an unknown event.
    """
    fields = line.split("\t")
    if len(fields) != _FIELD_COUNT or fields[1] not in _EVENTS:
        raise GrantTrustError(f"malformed trust log line: {line!r}")
    return TrustEvent(*fields)


def read_log(store: TrustStore) -> tuple[TrustEvent, ...]:
    """Every event of the log in order; empty when the store has none. Never creates anything.

    Raises:
        GrantTrustError: a line is malformed (the line number is named).
    """
    try:
        text = store.log_path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return ()
    events = []
    lines = text.split("\n")
    for number, line in enumerate(lines[:-1] if lines[-1] == "" else lines, start=1):
        try:
            events.append(parse_event(line))
        except GrantTrustError as exc:
            raise GrantTrustError(f"{store.log_path}:{number}: {exc}") from exc
    return tuple(events)


def is_accepted(digest: str, store: TrustStore) -> bool:
    """Whether ``digest`` is accepted: its copy is in the store."""
    return _is_digest(digest) and (store.accepted_dir / digest).is_file()


def accepted_content(digest: str, store: TrustStore) -> bytes:
    """The accepted copy of ``digest``.

    Raises:
        GrantTrustError: ``digest`` is not accepted.
    """
    if not is_accepted(digest, store):
        raise GrantTrustError(f"digest {digest} is not accepted")
    return (store.accepted_dir / digest).read_bytes()


def last_accepted(relative: str, project: str, store: TrustStore) -> str | None:
    """The newest accepted digest the log records for ``relative`` in ``project`` that is still accepted.

    A revoked digest has lost its copy and is skipped, so an earlier surviving version answers.
    """
    for event in reversed(read_log(store)):
        if (
            event.event == EVENT_ACCEPT
            and event.path == relative
            and event.project == project
            and is_accepted(event.digest, store)
        ):
            return event.digest
    return None


def last_accepted_elsewhere(relative: str, project: str, store: TrustStore) -> TrustEvent | None:
    """The newest still-accepted acceptance of ``relative`` in a project other than ``project``.

    Only for showing the owner a diff: it never decides a state, and it names the project the
    version was accepted in.
    """
    for event in reversed(read_log(store)):
        if (
            event.event == EVENT_ACCEPT
            and event.path == relative
            and event.project != project
            and is_accepted(event.digest, store)
        ):
            return event
    return None


def file_trust(grant: GrantFile, store: TrustStore) -> FileTrust:
    """The state of ``grant`` against ``store``. Reads only."""
    if is_accepted(grant.digest, store):
        return FileTrust(grant, TrustState.TRUSTED, grant.digest)
    previous = last_accepted(grant.relative, grant.project, store)
    return FileTrust(grant, TrustState.NEW if previous is None else TrustState.CHANGED, previous)


def accept(grant: GrantFile, store: TrustStore, at: datetime | None = None) -> TrustEvent:
    """Accept ``grant``: keep a copy of exactly these bytes, then log it; returns the logged event.

    Raises:
        GrantTrustError: the digest is already accepted (nothing is logged).
    """
    if is_accepted(grant.digest, store):
        raise GrantTrustError(f"{grant.relative} is already accepted as {grant.digest}")
    stamp = _stamp(at)  # before anything is written, so a refused time leaves the store untouched
    previous = last_accepted(grant.relative, grant.project, store) or NO_PREVIOUS
    _store_copy(grant, store)
    event = TrustEvent(stamp, EVENT_ACCEPT, grant.digest, grant.relative, grant.project, previous)
    _append(event, store)
    return event


def revoke(digest: str, store: TrustStore, at: datetime | None = None) -> TrustEvent:
    """Revoke the full ``digest``: remove its copy, then log it with the path and project it was accepted for.

    Raises:
        GrantTrustError: ``digest`` is not accepted.
    """
    if not is_accepted(digest, store):
        raise GrantTrustError(f"digest {digest} is not accepted")
    stamp = _stamp(at)
    path, project = NO_PREVIOUS, NO_PREVIOUS
    for event in reversed(read_log(store)):
        if event.event == EVENT_ACCEPT and event.digest == digest:
            path, project = event.path, event.project
            break
    (store.accepted_dir / digest).unlink()
    revoked = TrustEvent(stamp, EVENT_REVOKE, digest, path, project, NO_PREVIOUS)
    _append(revoked, store)
    return revoked


def record_untrusted(grant: GrantFile, store: TrustStore, at: datetime | None = None) -> TrustEvent | None:
    """Log a sighting of ``grant`` as untrusted, once per digest; ``None`` when nothing was logged.

    Nothing is logged for a digest that is accepted or was sighted before: the log counts
    distinct untrusted contents, not how often a run met them.
    """
    stamp = _stamp(at)
    if is_accepted(grant.digest, store):
        return None
    log = read_log(store)
    if any(event.event == EVENT_UNTRUSTED and event.digest == grant.digest for event in log):
        return None
    previous = last_accepted(grant.relative, grant.project, store) or NO_PREVIOUS
    event = TrustEvent(stamp, EVENT_UNTRUSTED, grant.digest, grant.relative, grant.project, previous)
    _append(event, store)
    return event


def resolve_digest(reference: str, store: TrustStore) -> str:
    """The one accepted digest that ``reference`` — a full digest or a prefix of at least 12 hex — names.

    Raises:
        GrantTrustError: no accepted digest, or more than one, starts with ``reference``.
    """
    if len(reference) < SHORT_DIGEST_LENGTH or not set(reference) <= _HEX:
        raise GrantTrustError(f"{reference!r} is not a digest: give at least {SHORT_DIGEST_LENGTH} hex characters")
    try:
        names = sorted(entry.name for entry in os.scandir(store.accepted_dir))
    except FileNotFoundError:
        names = []
    matches = [name for name in names if _is_digest(name) and name.startswith(reference)]
    if len(matches) != 1:
        what = "names no accepted digest" if not matches else "is ambiguous"
        raise GrantTrustError(f"digest {reference} {what}")
    return matches[0]


def trust_report(store: TrustStore) -> TrustReport:
    """The summary of the log: acceptances, re-acceptances, revocations and the sighting-to-acceptance time."""
    events = read_log(store)
    first_sighting: dict[str, int] = {}
    for index, event in enumerate(events):
        if event.event == EVENT_UNTRUSTED:
            first_sighting.setdefault(event.digest, index)
    seconds: list[float] = []
    for digest, sighted in first_sighting.items():
        for event in events[sighted + 1 :]:
            if event.event == EVENT_ACCEPT and event.digest == digest:
                seconds.append(
                    (_parse_stamp(event.timestamp) - _parse_stamp(events[sighted].timestamp)).total_seconds()
                )
                break
    accepts = [event for event in events if event.event == EVENT_ACCEPT]
    return TrustReport(
        accepts=len(accepts),
        reaccepts=_reaccepts(accepts),
        revokes=sum(event.event == EVENT_REVOKE for event in events),
        untrusted_digests=len(first_sighting),
        accepted_after_sighting=len(seconds),
        median_seconds=float(statistics.median(seconds)) if seconds else None,
    )


def _reaccepts(accepts: Sequence[TrustEvent]) -> int:
    """How many acceptances follow an earlier acceptance of the same file: the same project and relative path."""
    seen: set[tuple[str, str]] = set()
    count = 0
    for event in accepts:
        key = (event.project, event.path)
        count += key in seen
        seen.add(key)
    return count


def unified_diff(old: bytes, new: bytes, old_label: str, new_label: str) -> str:
    """A unified diff (three lines of context) of two files' text; empty when the text is the same.

    Bytes are read as UTF-8 with replacement. The text is split on the newline character only, so
    a changed carriage return shows as a changed line; a difference in the final newline alone is
    not shown, and the caller says so when the bytes differ and this is empty.
    """
    old_lines, new_lines = _lines(old), _lines(new)
    operations = _edit_script(old_lines, new_lines)
    changed = [index for index, (tag, _) in enumerate(operations) if tag != " "]
    if not changed:
        return ""
    ranges: list[list[int]] = []
    for index in changed:
        low, high = max(0, index - _CONTEXT_LINES), min(len(operations) - 1, index + _CONTEXT_LINES)
        if ranges and low <= ranges[-1][1] + 1:
            ranges[-1][1] = high
        else:
            ranges.append([low, high])
    out = [f"--- {old_label}\n", f"+++ {new_label}\n"]
    for low, high in ranges:
        before = operations[:low]
        old_start, new_start = sum(tag != "+" for tag, _ in before), sum(tag != "-" for tag, _ in before)
        hunk = operations[low : high + 1]
        old_length, new_length = sum(tag != "+" for tag, _ in hunk), sum(tag != "-" for tag, _ in hunk)
        out.append(f"@@ -{_span(old_start, old_length)} +{_span(new_start, new_length)} @@\n")
        out.extend(f"{tag}{line}\n" for tag, line in hunk)
    return "".join(out)


def _lines(content: bytes) -> list[str]:
    parts = content.decode("utf-8", errors="replace").split("\n")
    return parts[:-1] if parts[-1] == "" else parts


def _span(before: int, length: int) -> str:
    """A hunk range as ``difflib`` spells it: the 1-based start, and the length unless it is one."""
    if length == 1:
        return str(before + 1)
    return f"{before if length == 0 else before + 1},{length}"


def _edit_script(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    """The line edit script of ``(" " | "-" | "+", line)``: a longest common subsequence, deletions first on ties."""
    start = 0
    while start < len(old) and start < len(new) and old[start] == new[start]:
        start += 1
    end_old, end_new = len(old), len(new)
    while end_old > start and end_new > start and old[end_old - 1] == new[end_new - 1]:
        end_old -= 1
        end_new -= 1
    middle_old, middle_new = old[start:end_old], new[start:end_new]
    script = [(" ", line) for line in old[:start]]
    if len(middle_old) * len(middle_new) > _MAX_DIFF_CELLS:
        script += [("-", line) for line in middle_old] + [("+", line) for line in middle_new]
    else:
        script += _lcs_script(middle_old, middle_new)
    return script + [(" ", line) for line in old[end_old:]]


def _lcs_script(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    rows, columns = len(old), len(new)
    table = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(rows - 1, -1, -1):
        for column in range(columns - 1, -1, -1):
            if old[row] == new[column]:
                table[row][column] = table[row + 1][column + 1] + 1
            else:
                table[row][column] = max(table[row + 1][column], table[row][column + 1])
    script: list[tuple[str, str]] = []
    row = column = 0
    while row < rows and column < columns:
        if old[row] == new[column]:
            script.append((" ", old[row]))
            row += 1
            column += 1
        elif table[row + 1][column] >= table[row][column + 1]:
            script.append(("-", old[row]))
            row += 1
        else:
            script.append(("+", new[column]))
            column += 1
    script += [("-", line) for line in old[row:]]
    script += [("+", line) for line in new[column:]]
    return script


def _is_digest(text: str) -> bool:
    return len(text) == _DIGEST_LENGTH and set(text) <= _HEX


def _stamp(at: datetime | None) -> str:
    if at is None:
        at = datetime.now(UTC)
    if at.tzinfo is None:
        raise ValueError(f"a trust event time must carry a timezone, got {at!r}")
    return at.astimezone(UTC).strftime(_STAMP_FORMAT)


def _parse_stamp(stamp: str) -> datetime:
    try:
        return datetime.strptime(stamp, _STAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise GrantTrustError(f"malformed trust log timestamp {stamp!r}") from exc


def _store_copy(grant: GrantFile, store: TrustStore) -> None:
    """Write the accepted copy whole or not at all: a temporary file in the store, then a rename."""
    store.accepted_dir.mkdir(parents=True, exist_ok=True)
    temporary = store.accepted_dir / f".{grant.digest}.{os.getpid()}.tmp"
    try:
        temporary.write_bytes(grant.content)
        temporary.replace(store.accepted_dir / grant.digest)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _append(event: TrustEvent, store: TrustStore) -> None:
    """Append the event's line in one ``write`` on an ``O_APPEND`` descriptor, creating the store on first use."""
    store.root.mkdir(parents=True, exist_ok=True)
    line = (format_event(event) + "\n").encode("utf-8")
    descriptor = os.open(store.log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if os.write(descriptor, line) != len(line):
            raise GrantTrustError(f"short write to {store.log_path}")
    finally:
        os.close(descriptor)
