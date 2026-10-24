"""Validate a one-packet scorer reply and bind its ID from sealed call metadata."""

from __future__ import annotations

import re

RAW_HEADER = "element\tverdict\treason"
CANONICAL_HEADER = "run_id\telement\tverdict\treason"
PACKET_ID = re.compile(r"g[0-9a-f]{16}\Z")
RAW_COLUMN_COUNT = 3


def canonicalize(reply: str, packet_id: str, element_ids: list[str]) -> str:
    """Return strict four-column TSV without trusting a model-authored packet ID."""
    if not PACKET_ID.fullmatch(packet_id):
        raise ValueError("sealed packet ID is malformed")
    if not element_ids or len(set(element_ids)) != len(element_ids):
        raise ValueError("sealed element IDs are malformed")
    if "\r" in reply:
        raise ValueError("scorer reply contains carriage returns")
    lines = [line for line in reply.split("\n") if line.strip()]
    if not lines or lines[0] != RAW_HEADER:
        raise ValueError("raw scorer TSV header mismatch")
    seen: set[str] = set()
    canonical = [CANONICAL_HEADER]
    for line in lines[1:]:
        columns = line.split("\t")
        if len(columns) != RAW_COLUMN_COUNT or columns[1] not in {"PASS", "FAIL"} or not columns[2].strip():
            raise ValueError("raw scorer TSV row is malformed")
        element = columns[0]
        if element not in element_ids or element in seen:
            raise ValueError("raw scorer TSV has an unknown or duplicate element")
        seen.add(element)
        canonical.append("\t".join((packet_id, *columns)))
    if seen != set(element_ids):
        raise ValueError("raw scorer TSV element set differs from packet")
    return "\n".join(canonical) + "\n"
