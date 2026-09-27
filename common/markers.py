"""Once-per-identity diagnostic markers in the system tempdir — the one owner (C36).

A hook runs as a fresh process per event, so "say this once per session" needs state outside
the process. Every such marker is claimed here, which fixes the properties the population used
to disagree on:

- **atomic claim** — ``O_CREAT | O_EXCL``: of several hook processes racing on one identity,
  exactly one emits;
- **hashed name, mode 0600** — a session id containing ``/`` cannot escape the tempdir, and the
  file is the owner's alone;
- **repeat when unidentified** — an absent identity (or the literal ``nosession`` some payload
  readers substitute) never claims a shared marker, which would let one anonymous session
  silence every later one; the diagnostic repeats instead (fail-visible);
- **age-out** — a marker older than ``MARKER_MAX_AGE_SECONDS`` is stale (a crashed session, a
  session id reused days later) and is replaced, so the diagnostic speaks again rather than
  staying suppressed. A long session may therefore hear it once more per day; that is the
  accepted direction.

Two processes that find the same stale marker may both replace it and both emit — the loud
direction again, never a silent one.

A marker failure (unwritable tempdir) makes the diagnostic noisier, never invisible.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from common import jsondata

#: A day: longer than a working session, short enough that a crashed or reused session id does
#: not suppress a diagnostic for long.
MARKER_MAX_AGE_SECONDS = 24 * 60 * 60


def _data() -> dict[str, Any]:
    """The marker data file beside this module (C102): name shape, kinds, unidentified, state-file templates."""
    return jsondata.read(Path(__file__).parent / "markers.json")


def _unidentified() -> tuple[str, ...]:
    return ("", _data()["unidentified"])


def _marker_path(kind: str, identity: str, directory: Path | None) -> Path:
    data = _data()
    digest = hashlib.sha256(identity.encode()).hexdigest()[: data["name_sha256_tail"]]
    return (directory or Path(tempfile.gettempdir())) / f"{data['name_prefix']}{kind}-{digest}"


def marker_kind(stem: str) -> str:
    """The tempdir kind spelling for one vocabulary stem (the table is owned by markers.json, C102)."""
    return _data()["kinds"][stem]


def unidentified_identity() -> str:
    """The literal identity payload readers substitute when a session is unknown (C102)."""
    return _data()["unidentified"]


def delegation_state_name(which: str, identity: str) -> str:
    """One of the delegation drift state-file names for ``identity``: counter, marker, ask_marker (C102)."""
    return jsondata.fill(_data()["delegation_state_files"][which], {"identity": identity})


def _is_stale(marker: Path, now: float) -> bool:
    try:
        return now - marker.stat().st_mtime > MARKER_MAX_AGE_SECONDS
    except OSError:
        return False


def claim_diagnostic_marker(kind: str, identity: str | None, *, directory: Path | None = None) -> bool:
    """Atomically claim one diagnostic for ``identity``; True means "emit now".

    Two throttle domains, deliberately different and stated here because the difference reads
    as an inconsistency otherwise (ADR-0012/D02):

    - **route-level** diagnostics describe what a *route* can do, so they throttle by session
      id — one statement per session, even though a later call on the same route is silent;
    - **event-level** diagnostics report a defect in one call, so they throttle by a
      session/tool-use pair — a second malformed call stays visible.
    """
    if not identity or identity in _unidentified():
        return True  # no identity to throttle by: repeat rather than hide the diagnostic
    marker = _marker_path(kind, identity, directory)
    for _attempt in range(2):
        try:
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if not _is_stale(marker, time.time()):
                return False
            with contextlib.suppress(OSError):
                marker.unlink()
            continue
        except OSError:
            return True  # marker failure must make the diagnostic noisier, never invisible
        try:
            os.close(descriptor)
        except OSError:
            with contextlib.suppress(OSError):
                marker.unlink(missing_ok=True)
        return True
    return True  # lost the replace race twice: emit rather than stay silent


def release_diagnostic_markers(
    kind_prefix: str, identity: str | None, *, keep_kind: str | None = None, directory: Path | None = None
) -> None:
    """Remove this identity's markers whose kind starts with ``kind_prefix`` — the condition cleared.

    A content-keyed diagnostic folds its condition into the kind (``<prefix>-<condition>``), so
    clearing it, or moving to a new condition, re-arms the notice for a later recurrence.
    ``keep_kind`` spares the marker just claimed.
    """
    if not identity or identity in _unidentified():
        return
    keep = _marker_path(keep_kind, identity, directory).name if keep_kind else None
    suffix = _marker_path(kind_prefix, identity, directory).name.rsplit("-", 1)[1]
    folder = directory or Path(tempfile.gettempdir())
    for marker in folder.glob(f"{_data()['name_prefix']}{kind_prefix}*-{suffix}"):
        if marker.name != keep:
            with contextlib.suppress(OSError):
                marker.unlink()
