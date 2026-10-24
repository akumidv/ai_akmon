"""Offline tests for prospective one-packet scorer identity binding."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))

import scorer_route_check as existing  # noqa: E402
import v3_scorer_id_binding as binding  # noqa: E402

PACKET_ID = "gf04a4422bf50dd1f"
ELEMENTS = ["E1", "E2", "E3", "E4"]
RAW = (
    "element\tverdict\treason\n"
    "E1\tPASS\tConcrete observation one.\n"
    "E2\tFAIL\tConcrete observation two.\n"
    "E3\tPASS\tConcrete observation three.\n"
    "E4\tPASS\tConcrete observation four.\n"
)


def test_canonical_reply_preserves_all_verdicts_and_reasons() -> None:
    canonical = binding.canonicalize(RAW, PACKET_ID, ELEMENTS)
    existing.validate_tsv(canonical, PACKET_ID, ELEMENTS)
    assert canonical.splitlines()[1:] == [f"{PACKET_ID}\t{line}" for line in RAW.splitlines()[1:]]


@pytest.mark.parametrize(
    "reply",
    [
        RAW.replace("element\tverdict\treason", "run_id\telement\tverdict\treason"),
        RAW.replace("E1\tPASS", "E1\tUNKNOWN"),
        RAW.replace("E1\tPASS\tConcrete observation one.", "E1\tPASS\t "),
        RAW.replace("E1\tPASS", "E1\tPASS\textra\t"),
        RAW.replace("E4\tPASS\tConcrete observation four.\n", ""),
        RAW.replace("E4\tPASS", "E1\tPASS"),
        "preface\n" + RAW,
        RAW + "commentary\n",
        RAW.replace("E1\tPASS", "E5\tPASS"),
        RAW.replace("\n", "\r\n"),
    ],
)
def test_malformed_or_incomplete_reply_fails_closed(reply: str) -> None:
    with pytest.raises(ValueError):
        binding.canonicalize(reply, PACKET_ID, ELEMENTS)


def test_sealed_packet_identity_must_have_exact_shape() -> None:
    with pytest.raises(ValueError, match="packet ID"):
        binding.canonicalize(RAW, PACKET_ID[:-1], ELEMENTS)


def test_terminal_old_reply_cannot_be_reclassified() -> None:
    old_reply = (
        Path("/tmp/a22-p3-v3-qualification-successor-runtime") / "evidence/g225a6ea21aeb6b0df81a151977b43f20/reply.tsv"
    )
    if not old_reply.exists():
        pytest.skip("private predecessor runtime unavailable")
    with pytest.raises(ValueError, match="header"):
        binding.canonicalize(old_reply.read_text(encoding="utf-8"), PACKET_ID, ELEMENTS)
