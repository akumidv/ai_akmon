"""Validate a scorer TSV with an optional exact header and bind its packet ID."""

from __future__ import annotations

import re

RAW_HEADER = "element\tverdict\treason"
CANONICAL_HEADER = "run_id\telement\tverdict\treason"
PACKET_ID = re.compile(r"g[0-9a-f]{16}\Z")
RAW_COLUMN_COUNT = 3


def _canonical_row(line: str, packet_id: str, element_ids: set[str], seen: set[str]) -> str:
    columns = line.split("\t")
    if len(columns) != RAW_COLUMN_COUNT or columns[1] not in {"PASS", "FAIL"} or not columns[2].strip():
        raise ValueError("raw scorer TSV row is malformed")
    element = columns[0]
    if element not in element_ids or element in seen:
        raise ValueError("raw scorer TSV has an unknown or duplicate element")
    seen.add(element)
    return "\t".join((packet_id, *columns))


def canonicalize(reply: str, packet_id: str, element_ids: list[str]) -> tuple[str, str]:
    """Return canonical four-column TSV and whether its exact header was present.

    Blank lines are ignored. The first nonblank line may be the exact raw header;
    otherwise it must be a data row. No preface, malformed header, or trailing
    commentary is accepted.
    """
    if not isinstance(packet_id, str) or not PACKET_ID.fullmatch(packet_id):
        raise ValueError("sealed packet ID is malformed")
    if (
        not element_ids
        or any(not isinstance(element, str) or not element for element in element_ids)
        or len(set(element_ids)) != len(element_ids)
    ):
        raise ValueError("sealed element IDs are malformed")
    if not isinstance(reply, str):
        raise ValueError("scorer reply must be text")
    if "\r" in reply:
        raise ValueError("scorer reply contains carriage returns")

    lines = [line for line in reply.split("\n") if line.strip()]
    if not lines:
        raise ValueError("raw scorer TSV has no rows")
    if lines[0] == RAW_HEADER:
        rows = lines[1:]
        normalization_kind = "exact_header"
    else:
        rows = lines
        normalization_kind = "inserted_header"

    seen: set[str] = set()
    canonical = [CANONICAL_HEADER]
    allowed = set(element_ids)
    canonical.extend(_canonical_row(line, packet_id, allowed, seen) for line in rows)

    if seen != allowed:
        raise ValueError("raw scorer TSV element set differs from packet")
    return "\n".join(canonical) + "\n", normalization_kind
