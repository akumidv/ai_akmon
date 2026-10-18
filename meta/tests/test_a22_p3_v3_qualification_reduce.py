"""The V3 floor uses two complete run-level readings on the same repeat."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("v3_qualification_reduce_test", ROOT / "v3_qualification_reduce.py")
assert SPEC is not None and SPEC.loader is not None
reducer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reducer)


def _reply(row: dict, failed_element: str | None = None) -> str:
    lines = ["run_id\telement\tverdict\treason"]
    for element in row["element_ids"]:
        verdict = "FAIL" if element == failed_element else "PASS"
        lines.append(f"{row['packet_id']}\t{element}\t{verdict}\tsynthetic reason")
    return "\n".join(lines) + "\n"


def _readings() -> dict[str, dict[str, str]]:
    candidate = reducer.schedule.read(reducer.schedule.SCHEDULE)
    return {row["run_id"]: {route: _reply(row) for route in reducer.schedule.ROUTES} for row in candidate["cells"]}


def test_same_repeat_run_level_failure_and_pair_floor() -> None:
    candidate = reducer.schedule.read(reducer.schedule.SCHEDULE)
    readings = _readings()
    pairs = set()
    for row in candidate["cells"]:
        pair = reducer.schedule.read(ROOT / "cases" / f"{row['case']}.json")["pair"]
        if pair in pairs:
            continue
        pairs.add(pair)
        elements = row["element_ids"]
        readings[row["run_id"]] = {
            "codex": _reply(row, elements[0]),
            "qwen": _reply(row, elements[-1]),
        }
    result = reducer.reduce(readings)
    assert result["status"] == "FLOOR_PASSED"
    assert len(result["qualified_strata"]) == 4
    assert len(result["qualified_runs"]) == 4
    assert result["comparison_authorized"] is False
    assert any(row["element_disagreements"] for row in result["details"])


def test_different_repeats_do_not_qualify_same_stratum() -> None:
    candidate = reducer.schedule.read(reducer.schedule.SCHEDULE)
    readings = _readings()
    rows = [row for row in candidate["cells"] if row["case"] == "P3-01" and row["tier"] == "mid"]
    assert len(rows) == 2
    readings[rows[0]["run_id"]]["codex"] = _reply(rows[0], rows[0]["element_ids"][0])
    readings[rows[1]["run_id"]]["qwen"] = _reply(rows[1], rows[1]["element_ids"][0])
    result = reducer.reduce(readings)
    assert result["status"] == "FLOOR_FAILED"
    assert result["qualified_strata"] == []


def test_missing_or_duplicate_readings_fail_closed() -> None:
    readings = _readings()
    readings.pop(next(iter(readings)))
    with pytest.raises(reducer.ReductionError, match="complete"):
        reducer.reduce(readings)
    readings = _readings()
    first = next(iter(readings))
    readings[first]["qwen"] = readings[first]["qwen"].replace("\tE1\t", "\tE2\t")
    with pytest.raises(reducer.ReductionError, match="duplicate"):
        reducer.reduce(readings)
