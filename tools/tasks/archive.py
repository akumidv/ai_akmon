#!/usr/bin/env python3
"""Archive done backlog entries: move ``· done ·`` lines from TASKS.md to TASKS_ARCHIVE.md.

The one repeatable mechanic of the tasks pipeline ([pipelines/tasks.md](../../pipelines/tasks.md)):
a task that lands ``done`` moves to ``TASKS_ARCHIVE.md`` **in the same session** — done work
never lingers in the live file (``verify.py`` warns when it does). This tool performs that move
deterministically instead of hand-editing two files on every task close.

An *entry* is a top-level list item ``- <id> · … · done · …`` plus any indented continuation
lines beneath it. The status is the third ``·``-separated field (tasks.md § entry format). Done
entries are removed from wherever they sit in ``TASKS.md`` and inserted at the top of the
archive's ``## Done`` section (so the newest sit first), **verbatim** — rewording an archived
line into its terse form stays the owner's call; this tool only relocates.

    python3 .../tools/tasks/archive.py --tasks <path>                 # dry-run: list what would move
    python3 .../tools/tasks/archive.py --tasks <path> --apply         # perform the move
    python3 .../tools/tasks/archive.py --tasks <path> --done C11 --apply  # close C11, then move it

``--done <id>…`` flips the named entries' status to ``done`` before the sweep, so closing a task
is one command instead of a hand-edit-then-run. The owner still names the ids (deciding it is done
stays the owner's call — the tool only mechanizes the flip+move); an id that is not a top-level
entry is a typo, so it **fails closed**: exit ``2``, nothing written. Terse rewording of the moved
line stays the owner's call — this tool never rewrites an entry's prose, only its status field.

As an advisory, any top-level bullet whose leading field looks like a task id (``A``/``C``/``L``/
``N``/``V``/``T`` + digits) but that lacks a status field (fewer than three ``·`` fields — a
dropped separator) is warned about on stderr; it does not change the exit code.

Stdlib-only and idempotent (a second ``--apply`` moves nothing; ``--done`` on an already-done entry
is a no-op). The archive is the sibling ``TASKS_ARCHIVE.md``. It never runs git — the owner commits
(D5). Dry-run exits ``1`` when done entries are present (so CI can flag a backlog that still holds
landed work); ``--apply`` exits ``0`` on success.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DONE_STATUS = "done"
DONE_HEADER = "## Done"
_TASK_ID_RE = re.compile(r"^[ACLNTV]\d+$")  # typed id scheme (ADR 0002) + grandfathered T#


def _is_bullet(line: str) -> bool:
    return line.startswith("- ")


def _entry_id(bullet: str) -> str:
    """The leading id field of a top-level entry (``- C21 · …`` → ``C21``)."""
    return bullet[2:].split("·", 1)[0].strip()


def _status_of(bullet: str) -> str | None:
    """The status field (third ``·``-separated field), or ``None`` when the line has too few."""
    fields = [field.strip() for field in bullet[2:].split("·")]
    return fields[2] if len(fields) >= 3 else None


def _set_status(bullet: str, status: str) -> str:
    """Rewrite the status field (third ``·``-separated field) to ``status``, keeping its spacing.

    Only the status cell changes — the id, title, and detail are left verbatim. A malformed
    bullet (fewer than three fields) is returned unchanged."""
    parts = bullet.split("·")
    if len(parts) < 3:
        return bullet
    field = parts[2]
    lead = field[: len(field) - len(field.lstrip())]
    trail = field[len(field.rstrip()) :]
    parts[2] = f"{lead}{status}{trail}"
    return "·".join(parts)


def mark_done(tasks_text: str, ids: list[str]) -> tuple[str, list[str]]:
    """Set the status of each named entry to ``done``; returns ``(new_text, missing_ids)``.

    ``missing_ids`` are requested ids that are not a top-level entry (a likely typo). An entry
    already ``done`` is left as-is (idempotent). Deciding a task is done stays the owner's call —
    this only mechanizes the status flip so a close is one command."""
    lines = tasks_text.splitlines()
    wanted = list(dict.fromkeys(ids))  # de-dupe, preserve order
    found: set[str] = set()
    for start, _end in parse_entries(lines):
        entry_id = _entry_id(lines[start])
        if entry_id in wanted:
            found.add(entry_id)
            lines[start] = _set_status(lines[start], DONE_STATUS)
    missing = [i for i in wanted if i not in found]
    return "\n".join(lines).rstrip("\n") + "\n", missing


def malformed_entries(lines: list[str]) -> list[str]:
    """Top-level bullets whose leading field looks like a task id but that lack a status field.

    A likely typo — a dropped ``·`` separator — rather than a prose bullet (whose leading field
    would not match the id scheme). Advisory only: reported, never swept."""
    return [
        lines[start]
        for start, _end in parse_entries(lines)
        if _TASK_ID_RE.match(_entry_id(lines[start])) and _status_of(lines[start]) is None
    ]


def parse_entries(lines: list[str]) -> list[tuple[int, int]]:
    """``[start, end)`` line ranges for each top-level entry (bullet + indented continuation)."""
    entries: list[tuple[int, int]] = []
    i, n = 0, len(lines)
    while i < n:
        if _is_bullet(lines[i]):
            j = i + 1
            while j < n and lines[j][:1] in (" ", "\t"):  # indented continuation belongs to it
                j += 1
            entries.append((i, j))
            i = j
        else:
            i += 1
    return entries


def _collapse_blanks(lines: list[str]) -> list[str]:
    """Drop runs of consecutive blank lines left behind by a removal down to a single blank."""
    out: list[str] = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    return out


def split_done(tasks_text: str) -> tuple[str, list[list[str]], list[str]]:
    """Split ``TASKS.md`` text into (remaining text, done entry blocks, moved ids)."""
    lines = tasks_text.splitlines()
    done_indices: set[int] = set()
    blocks: list[list[str]] = []
    ids: list[str] = []
    for start, end in parse_entries(lines):
        if _status_of(lines[start]) == DONE_STATUS:
            blocks.append(lines[start:end])
            ids.append(_entry_id(lines[start]))
            done_indices.update(range(start, end))
    kept = _collapse_blanks([line for idx, line in enumerate(lines) if idx not in done_indices])
    remaining = "\n".join(kept).rstrip("\n") + "\n"
    return remaining, blocks, ids


def insert_into_archive(archive_text: str, blocks: list[list[str]]) -> str:
    """Insert entry ``blocks`` at the top of the archive's ``## Done`` section (newest-first)."""
    lines = archive_text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == DONE_HEADER:
            at = idx + 1
            while at < len(lines) and not lines[at].strip():  # step past the header's blank line
                at += 1
            flat = [line for block in blocks for line in block]
            merged = lines[:at] + flat + lines[at:]
            return "\n".join(merged).rstrip("\n") + "\n"
    raise ValueError(f"archive has no '{DONE_HEADER}' section")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Move done backlog entries into TASKS_ARCHIVE.md.")
    parser.add_argument("--tasks", required=True, help="Path to the TASKS.md to sweep.")
    parser.add_argument(
        "--done",
        nargs="+",
        metavar="ID",
        help="Mark these entry ids `done` before sweeping (owner names them; all must exist).",
    )
    parser.add_argument("--apply", action="store_true", help="Perform the move (default: dry-run).")
    args = parser.parse_args(argv)

    tasks_path = Path(args.tasks)
    if not tasks_path.is_file():
        print(f"error: no such file: {tasks_path}", file=sys.stderr)
        return 2
    archive_path = tasks_path.with_name("TASKS_ARCHIVE.md")

    text = tasks_path.read_text(encoding="utf-8")
    for bullet in malformed_entries(text.splitlines()):
        print(f"warning: task entry missing a status field: {bullet.strip()}", file=sys.stderr)

    if args.done:
        text, missing = mark_done(text, args.done)
        if missing:
            print(f"error: no such entry: {', '.join(missing)}", file=sys.stderr)
            return 2

    remaining, blocks, ids = split_done(text)
    if not blocks:
        print("no done entries to archive")
        return 0

    if not args.apply:
        print(f"would archive {len(ids)} done entr{'y' if len(ids) == 1 else 'ies'}: {', '.join(ids)}")
        print("re-run with --apply to move them")
        return 1

    if not archive_path.is_file():
        print(f"error: no archive file: {archive_path}", file=sys.stderr)
        return 2
    try:
        new_archive = insert_into_archive(archive_path.read_text(encoding="utf-8"), blocks)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    tasks_path.write_text(remaining, encoding="utf-8")
    archive_path.write_text(new_archive, encoding="utf-8")
    print(f"archived {len(ids)}: {', '.join(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
