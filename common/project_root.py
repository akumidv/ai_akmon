#!/usr/bin/env python3
"""The one owner of "where is the project root" and "what is the dev-layer called".

Both questions were answered independently by seven modules (C73): three walked up for
``AGENTS.md`` beside either a mounted tree or a package integration record, one ignored
package mode, and three additionally hard-coded ``_aitna`` past ``AITNA_ROOT``. Every one of
them ended the walk with ``return start`` — the current directory — so a command that had
found nothing was indistinguishable from one that had found the root, and it went on to write
its artifacts under the cwd. Since the answer decides which registry binds and where a gate
pack lands, it is one fact and gets one owner.

Stdlib-only and free of project imports on purpose — see ``common/__init__.py`` for why
that, and the package's reachability from every carrier, is what lets a single owner exist at
all. There is no second definition left: ``hooks/hook_core.py`` imports from here too.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

# The dev-layer (LOCAL) root is configurable: ``_aitna`` is the default, but a project may
# relocate it by declaring ``AITNA_ROOT`` (a path relative to the project root, e.g.
# ``tools/ai``). akmon is always mounted at ``<aitna-root>/akmon``. Public because the
# *default* itself is a fact callers ask for: ``akmon init`` tells the owner to export
# ``AITNA_ROOT`` only when the chosen root is not this one.
AITNA_ROOT_DEFAULT = "_aitna"

# The longest start path the walk accepts, in UTF-8 bytes: Linux's PATH_MAX. No longer path
# names anything the kernel can look up, and resolving one costs time quadratic in its depth.
_START_PATH_MAX_BYTES = 4096

# How much of a refused start path its error message quotes.
_REFUSED_PREFIX_CHARS = 40


def resolve_path(path: Path) -> Path:
    """``path.resolve()`` that refuses a symlink loop on every interpreter, as the 3.12 floor does.

    CPython 3.12 raises ``RuntimeError("Symlink loop from '<path>'")`` for a loop even in
    non-strict mode; 3.13 stopped raising there and answers the path unresolved (M154). The
    floor's answer is the spec — the JavaScript twin ``resolvePath`` and the corpus tables
    follow it — so the loop is asked of the strict walk first, which reports it on every
    interpreter, and any other failure of that walk (a missing component, a file used as a
    directory) is the non-strict answer's to give.

    Raises:
        RuntimeError: a symlink on the path loops.
    """
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise RuntimeError(f"Symlink loop from {exc.filename!r}") from exc
    return path.resolve()


def aitna_root_name() -> str:
    """The configured dev-layer root, as a project-root-relative POSIX path (default ``_aitna``)."""
    return (os.environ.get("AITNA_ROOT") or AITNA_ROOT_DEFAULT).strip("/") or AITNA_ROOT_DEFAULT


def aitna_root(project_root: Path) -> Path:
    """Absolute dev-layer root for ``project_root`` (``<project_root>/<AITNA_ROOT>``)."""
    return project_root / aitna_root_name()


def akmon_mount(project_root: Path) -> Path:
    """Absolute akmon mount for ``project_root`` (``<aitna-root>/akmon``).

    The *mounted* tree's path, computed — not a claim that it exists, and not a claim that it is
    the tree that runs: a package-mode project has no mount at all (ADR 0009 §4-5). Which tree
    runs is ``hooks/hook_core.py::akmon_runtime_root``'s question, and since C77 it answers with
    the tree it is executing from — so a stale mount left over from a prior mode cannot shadow
    anything, because it is not a candidate.
    """
    return aitna_root(project_root) / "akmon"


def is_project_root(candidate: Path) -> bool:
    """A project ``AGENTS.md`` beside either a mounted tree or an integration record.

    The record (``<AITNA_ROOT>/.akmon.toml``) is the only marker a package-mode project
    carries, since it has no mounted tree at all (ADR 0009 §4); requiring the tree alone is
    the defect that made ``second_opinion.py`` and its two neighbours miss such a project
    entirely and fall back to the cwd.
    """
    if not (candidate / "AGENTS.md").is_file():
        return False
    aitna = aitna_root(candidate)
    return (aitna / "akmon").exists() or (aitna / ".akmon.toml").is_file()


def _bounded_start(start: Path | None = None) -> Path:
    """``start`` (default: the cwd), refused when its string is longer than the walk accepts.

    The bound is checked on the string before any filesystem call — ``resolve()`` included —
    because the cost it guards is in those calls: a start of 32,769 ``a/`` components kept a hook
    resolving it for minutes (C121). The length is counted in UTF-8, with a lone surrogate (an
    undecodable byte in a ``cwd``) as three bytes, the way the JavaScript twin counts it.

    Raises:
        UnicodeEncodeError: the start path holds a surrogate the filesystem encoding refuses.
        ValueError: the start path's string is longer than ``_START_PATH_MAX_BYTES``.
    """
    origin = start if start is not None else Path.cwd()
    text = str(origin)
    # A path no filesystem call can take (a lone surrogate) is refused first, as ``resolve()``
    # refuses it: the JavaScript hooks check that before the bound, so the two twins name the
    # same failure for an over-long path that is also unencodable.
    os.fsencode(text)
    size = len(text.encode("utf-8", "surrogatepass"))
    if size > _START_PATH_MAX_BYTES:
        raise ValueError(
            f"project-root start path is {size} bytes, over the {_START_PATH_MAX_BYTES}-byte bound: "
            f"{text[:_REFUSED_PREFIX_CHARS]}..."
        )
    return origin


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: the cwd) to the nearest project root, else ``start``.

    The fallback is deliberate and stays: a hook must not abort a session because it was
    invoked outside a project. Callers that *write* under the result must not use it bare —
    ``resolve_project_root`` hands them the same path plus the sentence to print, because
    there the fallback is a guess with a file written on top of it. A start path longer than
    ``_START_PATH_MAX_BYTES`` is not a fallback: it is refused with a ``ValueError`` before it is
    resolved (``_bounded_start``), and a hook takes that as its ordinary failure exit (C121).

    The walk is linear: each step is the candidate's parent, until the parent stops changing.

    ``hooks/hook_core.py`` imports this rather than repeating it. That was previously deferred
    on the belief that it waited on the C69/ADR-0009/D02 fork; it does not. That fork is about which
    *tree* the hooks read (``akmon_runtime_root``), not about where the project root is, and the
    only real dependency — that this package sit beside ``hooks/`` — holds in every carrier by
    construction, since C77 leaves the hooks running inside the tree that ships them.

    Raises:
        ValueError: the start path is longer than ``_START_PATH_MAX_BYTES``.
    """
    current = resolve_path(_bounded_start(start))
    candidate = current
    while not is_project_root(candidate):
        parent = candidate.parent
        if parent == candidate:
            return current
        candidate = parent
    return candidate


def resolve_project_root(explicit: Path | None, start: Path | None = None) -> tuple[Path, str | None]:
    """The root a command-line entry point works in, plus the notice it must print if it guessed.

    Returns ``(root, None)`` when the root was named on the command line or found by the walk,
    and ``(cwd, notice)`` when it was not. The notice exists because the fallback root is where
    the tool then reads its registry and writes its reports: unstated, a gate pack under a wrong
    root looks exactly like one under the right root, which is the failure C73 was filed for.
    """
    if explicit is not None:
        return resolve_path(explicit), None
    origin = resolve_path(_bounded_start(start))
    found = find_project_root(origin)
    if is_project_root(found):
        return found, None
    aitna = aitna_root_name()
    notice = (
        f"[akmon] no project root at or above {origin}: expected AGENTS.md beside {aitna}/akmon "
        f"or {aitna}/.akmon.toml. Falling back to that directory, so anything this command reads "
        f"or writes is relative to it; pass --project-root to name the root instead."
    )
    return origin, notice
