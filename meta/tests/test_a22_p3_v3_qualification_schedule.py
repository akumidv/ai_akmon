"""Offline checks for a fresh, complete, evaluator-only V3 A schedule."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
SPEC = importlib.util.spec_from_file_location("v3_qualification_schedule_test", ROOT / "v3_qualification_schedule.py")
assert SPEC is not None and SPEC.loader is not None
schedule = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(schedule)


def test_candidate_is_complete_fresh_and_packet_bound() -> None:
    stored = schedule.read(schedule.SCHEDULE)
    schedule.verify_schedule(stored)
    assert len({row["run_id"] for row in stored["cells"]}) == schedule.SUBJECT_COUNT
    assert len({row["packet_id"] for row in stored["cells"]}) == schedule.SUBJECT_COUNT
    assert all(set(scorer) == {"route", "call_id"} for row in stored["cells"] for scorer in row["scorers"])
    assert not {row["run_id"] for row in stored["cells"]} & set(schedule.read(schedule.OLD_MAP))
    assert stored["provider_calls_started"] == 0


@pytest.mark.parametrize("mutation", ["missing_cell", "duplicate_id", "old_id", "swapped_route", "case_hash"])
def test_candidate_rejects_schedule_drift(mutation: str) -> None:
    candidate = copy.deepcopy(schedule.read(schedule.SCHEDULE))
    rows = candidate["cells"]
    if mutation == "missing_cell":
        rows.pop()
    elif mutation == "duplicate_id":
        rows[1]["subject_call_ids"][0] = rows[0]["run_id"]
    elif mutation == "old_id":
        rows[0]["run_id"] = next(iter(schedule.read(schedule.OLD_MAP)))
    elif mutation == "swapped_route":
        rows[0]["scorers"].reverse()
    else:
        candidate["packet_input_sha256"]["cases/P3-01.json"] = "0" * 64
    with pytest.raises(schedule.ScheduleError):
        schedule.verify_schedule(candidate)


def test_prepare_rejects_duplicate_generator_id() -> None:
    with pytest.raises(schedule.ScheduleError, match="aliases"):
        schedule.build_schedule(new_id=lambda: "g" + "a" * 32, shuffle=lambda _rows: None)
