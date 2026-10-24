"""Offline tests for prospective header-optional scorer normalization."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))

import v3_scorer_header_optional as binding  # noqa: E402

PACKET_ID = "gf04a4422bf50dd1f"
ELEMENTS = ["E1", "E2", "E3", "E4"]
ROWS = (
    "E1\tPASS\tConcrete observation one.\n"
    "E2\tFAIL\tConcrete observation two.\n"
    "E3\tPASS\tConcrete observation three.\n"
    "E4\tPASS\tConcrete observation four.\n"
)
RAW_WITH_HEADER = "element\tverdict\treason\n" + ROWS


def test_exact_header_is_preserved_and_rows_are_bound_without_changes() -> None:
    canonical, kind = binding.canonicalize(RAW_WITH_HEADER, PACKET_ID, ELEMENTS)

    assert kind == "exact_header"
    assert canonical.splitlines() == [
        "run_id\telement\tverdict\treason",
        *(f"{PACKET_ID}\t{row}" for row in ROWS.splitlines()),
    ]


def test_absent_header_is_inserted_and_leading_blank_lines_are_ignored() -> None:
    canonical, kind = binding.canonicalize("\n \n" + ROWS, PACKET_ID, ELEMENTS)

    assert kind == "inserted_header"
    assert canonical.splitlines() == [
        "run_id\telement\tverdict\treason",
        *(f"{PACKET_ID}\t{row}" for row in ROWS.splitlines()),
    ]


@pytest.mark.parametrize(
    "reply",
    [
        "",
        " \n\t\n",
        "preface\n" + RAW_WITH_HEADER,
        RAW_WITH_HEADER + "commentary\n",
        ROWS + "element\tverdict\treason\n",
        "element\tverdict\treasoN\n" + ROWS,
        ROWS.replace("E1\tPASS", "E1\tUNKNOWN"),
        ROWS.replace("E1\tPASS\tConcrete observation one.", "E1\tPASS\t "),
        ROWS.replace("E1\tPASS", "E1\tPASS\textra\t"),
        ROWS.replace("E4\tPASS\tConcrete observation four.\n", ""),
        ROWS.replace("E4\tPASS", "E1\tPASS"),
        ROWS.replace("E1\tPASS", "E5\tPASS"),
        ROWS.replace("\n", "\r\n"),
    ],
)
def test_malformed_or_incomplete_replies_fail_closed(reply: str) -> None:
    with pytest.raises(ValueError):
        binding.canonicalize(reply, PACKET_ID, ELEMENTS)


@pytest.mark.parametrize(
    ("packet_id", "element_ids"),
    [
        (PACKET_ID[:-1], ELEMENTS),
        (PACKET_ID, []),
        (PACKET_ID, ["E1", "E1"]),
        (PACKET_ID, ["E1", "", "E3"]),
    ],
)
def test_malformed_sealed_identity_is_rejected(packet_id: str, element_ids: list[str]) -> None:
    with pytest.raises(ValueError):
        binding.canonicalize(ROWS, packet_id, element_ids)
