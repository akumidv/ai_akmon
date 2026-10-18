#!/usr/bin/env python3
"""The one owner of "what is the next report file called" (C114).

Every tool that writes a markdown report into a shared directory (gate_pack, second_opinion,
coverage_map, stats) names it ``<prefix>-<n>.md``: ``prefix`` is ``<task>-<base>`` when the run
names a task and ``<base>`` otherwise, and ``n`` is one past the largest ordinal already in the
directory for exactly that prefix. A wall-clock stamp is not used: it carries a date into the
tree and tells a reader nothing about which piece of work a report belongs to.

The file is created exclusively, so two concurrent runs never overwrite each other: the loser
of a race takes the next ordinal.

Stdlib-only and free of project imports, like the rest of ``common/``.
"""

from __future__ import annotations

import re
from pathlib import Path


def safe_name(name: str) -> str:
    """``name`` with every character but a letter, a digit, ``-`` or ``_`` turned into ``-``, outer ``-`` stripped.

    May return ``""``; the caller decides the fallback (a gate falls back to ``gate``).
    """
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-")


def task_error(task: str | None) -> str | None:
    """The usage-error sentence for a ``--task`` that sanitizes to nothing, else ``None``.

    ``None`` (no ``--task``) is fine; ``""``, ``"///"`` or ``"..."`` is not: a task the user
    named must show in the report's name, never silently vanish (C114). The tools call this
    before reading or writing anything, so the user sees a usage error.
    """
    if task is None or safe_name(task):
        return None
    return f"--task {task!r} has no usable characters (letters, digits, '_' or '-')"


def report_prefix(base: str, task: str | None) -> str:
    """``<task>-<base>`` with a task, else ``<base>``; the task is sanitized like a gate name, case kept.

    Raises ``ValueError`` (with ``task_error``'s sentence) on a task that sanitizes to nothing.
    """
    if task is None:
        return base
    error = task_error(task)
    if error is not None:
        raise ValueError(error)
    return f"{safe_name(task)}-{base}"


def _largest_ordinal(directory: Path, prefix: str) -> int:
    pattern = re.compile(rf"{re.escape(prefix)}-([0-9]+)\.md")
    if not directory.is_dir():
        return 0
    ordinals = [int(match.group(1)) for entry in directory.iterdir() if (match := pattern.fullmatch(entry.name))]
    return max(ordinals, default=0)


def next_report_path(directory: Path, prefix: str) -> Path:
    """``<directory>/<prefix>-<n>.md`` with ``n`` one past the largest existing ordinal of ``prefix`` (1 when none).

    Only names matching ``<prefix>-<digits>.md`` exactly count, so ``design-align`` does not see
    ``design-align-full-3.md``. Nothing is created.
    """
    return directory / f"{prefix}-{_largest_ordinal(directory, prefix) + 1}.md"


def create_report(directory: Path, prefix: str, text: str, start: int | None = None) -> Path:
    """Create the next ``<prefix>-<n>.md`` in ``directory`` exclusively with ``text``; return its path.

    On a name that already exists (a concurrent run took it) the next ordinal is tried, so no
    report is ever overwritten. ``start`` overrides the first ordinal tried (default: the next one).
    """
    directory.mkdir(parents=True, exist_ok=True)
    ordinal = start if start is not None else _largest_ordinal(directory, prefix) + 1
    while True:
        path = directory / f"{prefix}-{ordinal}.md"
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(text)
        except FileExistsError:
            ordinal += 1
            continue
        return path
