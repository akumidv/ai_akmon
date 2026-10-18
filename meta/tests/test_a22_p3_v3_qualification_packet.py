"""The V3 scorer packet exposes only the exchange and evaluator rubric."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))
scorer_route_check = __import__("scorer_route_check")
SPEC = importlib.util.spec_from_file_location("v3_qualification_packet_test", ROOT / "v3_qualification_packet.py")
assert SPEC is not None and SPEC.loader is not None
packet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packet)


def _sample() -> tuple[dict, dict]:
    row = next(item for item in packet.schedule.read(packet.schedule.SCHEDULE)["cells"] if item["case"] == "P3-01")
    case = packet.schedule.read(ROOT / "cases" / "P3-01.json")
    exchange = {
        "run_id": row["run_id"],
        "turns": [
            {"user": case["subject"]["turn1"], "assistant": "Please answer about consumer use.\nCHECK: owner-use"},
            {"user": case["subject"]["menu"][0]["output"], "assistant": "Use the consumer-owned boundary."},
        ],
    }
    return row, exchange


def test_both_scorers_receive_same_blinded_bytes() -> None:
    row, exchange = _sample()
    visible, request = packet.render(row, exchange)
    assert visible.startswith(f"# Run {row['packet_id']}\n".encode())
    assert row["run_id"].encode() not in visible
    assert row["subject_attempt_id"].encode() not in visible
    assert b"strongest" not in visible
    assert b"## Elements" in visible
    assert b"E1:" in visible
    assert request == packet.sealed_bytes("scoring/scorer-prompt.txt") + scorer_route_check.PACKET_MARKER + visible
    assert request.endswith(visible)
    assert packet.render(row, exchange) == (visible, request)


@pytest.mark.parametrize("mutation", ["run_id", "turn1", "turn2", "missing_turn"])
def test_wrong_exchange_fails_closed(mutation: str) -> None:
    row, exchange = _sample()
    if mutation == "run_id":
        exchange["run_id"] = "wrong"
    elif mutation == "turn1":
        exchange["turns"][0]["user"] = "different prompt"
    elif mutation == "turn2":
        exchange["turns"][1]["user"] = "fabricated answer"
    else:
        exchange["turns"].pop()
    with pytest.raises(packet.PacketError):
        packet.render(row, exchange)
