#!/usr/bin/env python3
r"""D2 ledger: mechanical tracking of owner-verification points (`_aitna/D2_LEDGER.md`).

D2 (guardrails/_common.md "Owner-verify any change to math, data shape, or architecture")
is born mid-dialogue and easily drowns before commit time. This tool gives the point a
durable, tool-parsed home: a markdown file with `## Pending`, `## Approved`, and
`## Verified` tables.
Full design: `_aitna/akmon/meta/design/d2-ledger.md` (phase 1 of C11 — this tool; the
reminder hook, session counter, and pre-commit wiring are later phases).

    python3 .../tools/d2_ledger/d2_ledger.py add --ledger <path> \
        --kind math --what "reprice formula" --anchor "src/x.py:42"
    python3 .../tools/d2_ledger/d2_ledger.py list --ledger <path>
    python3 .../tools/d2_ledger/d2_ledger.py approve D2-3 --ledger <path>
    python3 .../tools/d2_ledger/d2_ledger.py verify D2-3 --ledger <path> --commit abc1234
    python3 .../tools/d2_ledger/d2_ledger.py check --ledger <path> [--strict] [--changed PATH ...]

Every entry gets a monotonic `D2-<n>` id so chat and commit messages can cite one verify
point ("verified in D2-3"). `add` creates the ledger (from the skeleton below) if it does
not exist yet; `approve` records the owner's decision and `verify` records the landing
commit — status never flips by a bare file edit. `check` is a warn-first
pre-commit gate: exit 0 by default (it only warns to stderr), `--strict` promotes a would-warn
to exit 1 (design §4 decision 4 — the later red-promotion switch).

Stdlib-only (argparse, pathlib, re, fnmatch for `**`-aware path globbing, tomllib for the
optional `.akmon.toml` `[d2_ledger] sensitive_paths` config). Never runs git —
the commit sha is always supplied by the caller (D5: the owner owns commits).
"""

from __future__ import annotations

import argparse
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

PENDING_HEADER = "## Pending"
APPROVED_HEADER = "## Approved"
VERIFIED_HEADER = "## Verified"
KINDS = ("math", "data-shape", "architecture")

SKELETON = """\
# D2 ledger — owner-verification points

> One entry per owner-verify point (guardrails/_common.md "Owner-verify any change to
> math, data shape, or architecture"). Pending on top; approved next; verified below. No dates — the
> landing commit is the timeline (D5: the tool never runs git; the owner supplies the sha).

## Pending

| id | kind | what | anchor | draft | second_opinion |
|----|------|------|--------|-------|----------------|

## Approved

| id | kind | what | anchor | draft | second_opinion |
|----|------|------|--------|-------|----------------|

## Verified

| id | kind | what | anchor | commit |
|----|------|------|--------|--------|
"""

_ID_RE = re.compile(r"^D2-(\d+)$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


# --------------------------------------------------------------------------------------
# markdown table parsing (hand-rolled: split on unescaped "|", skip header + separator rows)
# --------------------------------------------------------------------------------------


def _split_row(line: str) -> list[str] | None:
    """Cells of a markdown table row (``| a | b |`` -> ``["a", "b"]``), or ``None`` if not one."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [""]
    backslashes = 0
    for char in stripped:
        if char == "|" and backslashes % 2 == 0:
            cells.append("")
        else:
            cells[-1] += char
        backslashes = backslashes + 1 if char == "\\" else 0
    # The leading delimiter always produces an empty first segment; a closing delimiter,
    # when present, produces the empty last segment. Escaped pipes remain inside the cell,
    # including their backslash, so formatting and later mutations cannot corrupt Markdown.
    cells.pop(0)
    if cells and cells[-1] == "":
        cells.pop()
    return [cell.strip() for cell in cells]


def _escape_cell(cell: str) -> str:
    """Escape Markdown delimiters while preserving pipes that are already escaped."""
    escaped: list[str] = []
    backslashes = 0
    for char in cell:
        if char == "|" and backslashes % 2 == 0:
            escaped.append("\\")
        escaped.append(char)
        backslashes = backslashes + 1 if char == "\\" else 0
    return "".join(escaped)


def _format_row(cells: list[str]) -> str:
    return "| " + " | ".join(_escape_cell(cell) for cell in cells) + " |"


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(cell) for cell in cells)


def _section_header_index(lines: list[str], header: str) -> int:
    for idx, line in enumerate(lines):
        if line.strip() == header:
            return idx
    raise ValueError(f"malformed ledger: no '{header}' section")


def table_bounds(lines: list[str], header: str) -> tuple[int, int]:
    """``[start, end)`` line range of a section's data rows (after the header + separator rows).

    Blank lines *within* the data range (used in practice as a visual grouping break between
    rows) do not end the table — only a non-blank, non-row line (the next section header, or
    any other content) does. ``end`` is trimmed back to just past the last real row, so a blank
    run trailing the last row is never counted as part of the range (was: a duplicate-id bug —
    the old first-blank-line cutoff made ``add``/``next_id`` blind to any row past a mid-table
    blank line).
    """
    section_at = _section_header_index(lines, header)
    i = section_at + 1
    n = len(lines)
    while i < n and _split_row(lines[i]) is None:
        i += 1
    if i >= n:
        raise ValueError(f"malformed ledger: '{header}' has no table")
    i += 1  # step past the table header row (``| id | kind | ... |``)
    if i >= n or not _is_separator_row(_split_row(lines[i]) or []):
        raise ValueError(f"malformed ledger: '{header}' table has no separator row")
    data_start = i + 1
    cursor = data_start
    data_end = data_start
    while cursor < n:
        if _split_row(lines[cursor]) is not None:
            cursor += 1
            data_end = cursor
        elif lines[cursor].strip() == "":
            cursor += 1
        else:
            break
    return data_start, data_end


def parse_table(text: str, header: str) -> list[list[str]]:
    """Data rows (as cell lists) of the table under ``header`` in ``text``."""
    lines = text.splitlines()
    start, end = table_bounds(lines, header)
    return [row for line in lines[start:end] if (row := _split_row(line)) is not None]


def _parse_optional_table(text: str, header: str) -> list[list[str]]:
    """Rows under ``header``, or ``[]`` when reading a ledger from before that state existed."""
    try:
        return parse_table(text, header)
    except ValueError as exc:
        if f"no '{header}' section" not in str(exc):
            raise
        return []


def parse_ledger(text: str) -> tuple[list[list[str]], list[list[str]], list[list[str]]]:
    """``(pending_rows, approved_rows, verified_rows)``, including old two-section ledgers."""
    return (
        parse_table(text, PENDING_HEADER),
        _parse_optional_table(text, APPROVED_HEADER),
        parse_table(text, VERIFIED_HEADER),
    )


# --------------------------------------------------------------------------------------
# id allocation + mutation
# --------------------------------------------------------------------------------------


def next_id(*row_groups: list[list[str]]) -> str:
    """The next monotonic ``D2-<n>`` id, one past the highest id across all ``row_groups``."""
    max_n = 0
    for rows in row_groups:
        for cells in rows:
            if cells and (m := _ID_RE.match(cells[0])):
                max_n = max(max_n, int(m.group(1)))
    return f"D2-{max_n + 1}"


def add_entry(text: str, *, kind: str, what: str, anchor: str) -> tuple[str, str]:
    """Append a new pending row; returns ``(new_text, new_id)``."""
    lines = text.splitlines()
    pending_rows, approved_rows, verified_rows = parse_ledger(text)
    new_id = next_id(pending_rows, approved_rows, verified_rows)
    _, p_end = table_bounds(lines, PENDING_HEADER)
    lines.insert(p_end, _format_row([new_id, kind, what, anchor, "", ""]))
    return "\n".join(lines).rstrip("\n") + "\n", new_id


def _insert_approved_section(lines: list[str]) -> None:
    """Lazily add ``## Approved`` before Verified in a legacy two-section ledger."""
    verified_at = _section_header_index(lines, VERIFIED_HEADER)
    lines[verified_at:verified_at] = [
        APPROVED_HEADER,
        "",
        "| id | kind | what | anchor | draft | second_opinion |",
        "|----|------|------|--------|-------|----------------|",
        "",
    ]


def approve_entry(text: str, entry_id: str) -> str:
    """Move ``entry_id`` from ``## Pending`` to the top of ``## Approved``."""
    lines = text.splitlines()
    p_start, p_end = table_bounds(lines, PENDING_HEADER)
    match_at, row_line = None, None
    for i in range(p_start, p_end):
        cells = _split_row(lines[i])
        if cells and cells[0] == entry_id:
            match_at, row_line = i, lines[i]
            break
    if match_at is None:
        raise ValueError(f"no such pending entry: {entry_id}")
    del lines[match_at]
    if not any(line.strip() == APPROVED_HEADER for line in lines):
        _insert_approved_section(lines)
    a_start, _ = table_bounds(lines, APPROVED_HEADER)
    lines.insert(a_start, row_line)
    return "\n".join(lines).rstrip("\n") + "\n"


def verify_entry(text: str, entry_id: str, *, commit: str) -> str:
    """Move ``entry_id`` from ``## Approved`` to the top of ``## Verified``, stamping ``commit``.

    Raises ``ValueError`` if ``entry_id`` is not an approved entry.
    """
    lines = text.splitlines()
    if not any(line.strip() == APPROVED_HEADER for line in lines):
        raise ValueError(f"no such approved entry: {entry_id}")
    a_start, a_end = table_bounds(lines, APPROVED_HEADER)
    match_at, row_cells = None, None
    for i in range(a_start, a_end):
        cells = _split_row(lines[i])
        if cells and cells[0] == entry_id:
            match_at, row_cells = i, cells
            break
    if match_at is None:
        raise ValueError(f"no such approved entry: {entry_id}")
    del lines[match_at]
    v_start, _ = table_bounds(lines, VERIFIED_HEADER)
    verified_row = _format_row([row_cells[0], row_cells[1], row_cells[2], row_cells[3], commit])
    lines.insert(v_start, verified_row)
    return "\n".join(lines).rstrip("\n") + "\n"


def _read_or_skeleton(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else SKELETON


# --------------------------------------------------------------------------------------
# `.akmon.toml` [d2_ledger] sensitive_paths (config is the project's, per design §5.A)
# --------------------------------------------------------------------------------------


def _read_akmon_toml(path: Path) -> dict:
    """Read a ``.akmon.toml`` file into a dict; ``{}`` if absent or ``tomllib`` is unavailable.

    A malformed file raises. Deliberately not ``common/record.py``, which every other caller
    shares (C75). That reader is lenient by contract — a malformed record falls through to a
    line parser that yields every value as a string — because a hook must not end a session
    over a file it only consults.
    Here the same leniency would be a silent loss: ``sensitive_paths`` is an array the line parser
    cannot produce, so a record that fails to parse would quietly switch the D2 path check off.
    The lookup differs as well: it walks up from the ledger instead of resolving the dev-layer
    root. ``tomllib`` is on the Python 3.11 floor; an import failure still yields no sensitive-path
    config rather than a lenient guess.
    """
    if not path.is_file():
        return {}
    try:
        import tomllib  # noqa: PLC0415 — the one-reader carrier (test_record_owner) keys on the importing function
    except ImportError:
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _find_akmon_toml(start_dir: Path) -> Path | None:
    """Walk up from ``start_dir`` looking for a ``.akmon.toml`` file."""
    for candidate_dir in (start_dir, *start_dir.parents):
        candidate = candidate_dir / ".akmon.toml"
        if candidate.is_file():
            return candidate
    return None


def sensitive_paths_for(ledger_path: Path) -> list[str]:
    """The ``[d2_ledger] sensitive_paths`` globs configured near ``ledger_path``, if any."""
    config_path = _find_akmon_toml(ledger_path.resolve().parent)
    if config_path is None:
        return []
    section = _read_akmon_toml(config_path).get("d2_ledger")
    globs = section.get("sensitive_paths") if isinstance(section, dict) else None
    return [g for g in globs if isinstance(g, str)] if isinstance(globs, list) else []


def _segments_match(pattern_segments: list[str], path_segments: list[str]) -> bool:
    """Recursive ``/``-aware glob match: ``**`` spans zero or more whole segments, ``*``/``?`` stay within one segment.

    Portable across Python 3.x (``PurePath.full_match`` is 3.13+, but this tool is stdlib-only
    and may run under an older system ``python3`` — e.g. a pre-commit ``check``).
    """
    if not pattern_segments:
        return not path_segments
    head, *rest = pattern_segments
    if head == "**":
        return any(_segments_match(rest, path_segments[i:]) for i in range(len(path_segments) + 1))
    if not path_segments:
        return False
    if fnmatchcase(path_segments[0], head):
        return _segments_match(rest, path_segments[1:])
    return False


def _matches_any(changed_path: str, globs: list[str]) -> bool:
    """Whether ``changed_path`` matches any of ``globs`` (``**``-aware)."""
    path_segments = [s for s in changed_path.split("/") if s]
    return any(_segments_match([s for s in glob.split("/") if s], path_segments) for glob in globs)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def _cmd_add(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    text = _read_or_skeleton(ledger_path)
    new_text, new_id = add_entry(text, kind=args.kind, what=args.what, anchor=args.anchor)
    ledger_path.write_text(new_text, encoding="utf-8")
    print(new_id)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    pending_rows, approved_rows, _ = parse_ledger(_read_or_skeleton(Path(args.ledger)))
    if not pending_rows and not approved_rows:
        print("no open D2 entries")
        return 0
    for label, rows in (("Pending", pending_rows), ("Approved", approved_rows)):
        for cells in rows:
            entry_id, kind, what, anchor = cells[0], cells[1], cells[2], cells[3]
            print(f"{label}: {entry_id} [{kind}] {what} ({anchor})")
    return 0


def _cmd_approve(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    text = _read_or_skeleton(ledger_path)
    try:
        new_text = approve_entry(text, args.id)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    ledger_path.write_text(new_text, encoding="utf-8")
    print(f"approved {args.id}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    text = _read_or_skeleton(ledger_path)
    try:
        new_text = verify_entry(text, args.id, commit=args.commit)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    ledger_path.write_text(new_text, encoding="utf-8")
    print(f"verified {args.id} (commit {args.commit})")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    pending_rows = parse_table(_read_or_skeleton(ledger_path), PENDING_HEADER)
    if not pending_rows:
        print("D2 ledger clean")
        return 0

    if args.changed:
        globs = sensitive_paths_for(ledger_path)
        # Unconfigured (no sensitive_paths) -> can't tell which changes are D2-sensitive, so
        # warn (owner decision); once configured, warn only when a changed path matches a glob.
        should_warn = not globs or any(_matches_any(path, globs) for path in args.changed)
    else:
        should_warn = True

    if not should_warn:
        print("D2 ledger clean")
        return 0

    ids = ", ".join(cells[0] for cells in pending_rows)
    print(f"warning: D2 pending: {ids}", file=sys.stderr)
    return 1 if args.strict else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: dispatch to the ``add``/``list``/``approve``/``verify``/``check`` subcommand."""
    parser = argparse.ArgumentParser(
        prog="d2_ledger", description="Track owner-verification points (D2) in a markdown ledger."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name, builder in (
        ("add", _cmd_add),
        ("list", _cmd_list),
        ("approve", _cmd_approve),
        ("verify", _cmd_verify),
        ("check", _cmd_check),
    ):
        p = sub.add_parser(name)
        p.add_argument("--ledger", required=True, help="Path to the D2 ledger markdown file.")
        p.set_defaults(func=builder)
        if name == "add":
            p.add_argument("--kind", required=True, choices=KINDS)
            p.add_argument("--what", required=True)
            p.add_argument("--anchor", required=True)
        elif name in {"approve", "verify"}:
            p.add_argument("id", help=f"The entry id to {name}, e.g. D2-3.")
        if name == "verify":
            p.add_argument("--commit", required=True, help="The landing commit sha.")
        elif name == "check":
            p.add_argument("--strict", action="store_true", help="Exit 1 on a would-warn (default: warn-only).")
            p.add_argument("--changed", nargs="*", default=[], metavar="PATH", help="Paths touched by this change.")

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
