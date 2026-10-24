#!/usr/bin/env python3
"""Reduce two complete blind A readings without adjudication or model calls."""

from __future__ import annotations

from typing import Any

import scorer_route_check as scorer
import v3_qualification_header_optional_schedule as schedule

MIN_QUALIFIED_STRATA = 4


class ReductionError(ValueError):
    """The fixed two-scorer qualification dataset is incomplete or malformed."""


def _verdicts(reply: str, packet_id: str, elements: list[str]) -> dict[str, str]:
    try:
        scorer.validate_tsv(reply, packet_id, elements)
    except ValueError as exc:
        raise ReductionError(str(exc)) from exc
    rows = [line.split("\t") for line in reply.splitlines() if line.strip()][1:]
    return {element: verdict for _packet, element, verdict, _reason in rows}


def reduce(readings: dict[str, dict[str, str]], *, candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    """Qualify only a same-repeat run failed under both fixed scorers."""
    candidate = candidate or schedule.read(schedule.SCHEDULE)
    schedule.verify_schedule(candidate)
    cells = candidate["cells"]
    if not isinstance(readings, dict) or set(readings) != {row["run_id"] for row in cells}:
        raise ReductionError("qualification readings do not cover the complete 32-cell grid")
    details = []
    qualifying_runs = []
    strata = set()
    pairs = set()
    for row in cells:
        run_id = row["run_id"]
        replies = readings[run_id]
        if not isinstance(replies, dict) or set(replies) != set(schedule.ROUTES):
            raise ReductionError("each A output needs one complete reading from each route")
        verdicts = {route: _verdicts(replies[route], row["packet_id"], row["element_ids"]) for route in schedule.ROUTES}
        failed = {route: any(value == "FAIL" for value in values.values()) for route, values in verdicts.items()}
        if failed["codex"] and failed["qwen"]:
            qualifying_runs.append(run_id)
            strata.add((row["case"], row["tier"]))
            pairs.add(schedule.read(schedule.HERE / "cases" / f"{row['case']}.json")["pair"])
        details.append(
            {
                "run_id": run_id,
                "case": row["case"],
                "tier": row["tier"],
                "repeat": row["repeat"],
                "codex_failed": failed["codex"],
                "qwen_failed": failed["qwen"],
                "element_disagreements": [
                    element for element in row["element_ids"] if verdicts["codex"][element] != verdicts["qwen"][element]
                ],
            }
        )
    expected_pairs = {schedule.read(schedule.HERE / "cases" / f"{case}.json")["pair"] for case in schedule.CASES}
    floor_passed = len(strata) >= MIN_QUALIFIED_STRATA and pairs == expected_pairs
    return {
        "schema": 1,
        "record_type": "p3_v3_qualification_reduction_candidate",
        "status": "FLOOR_PASSED" if floor_passed else "FLOOR_FAILED",
        "qualified_runs": qualifying_runs,
        "qualified_strata": [{"case": case, "tier": tier} for case, tier in sorted(strata)],
        "represented_pairs": sorted(pairs),
        "details": details,
        "comparison_authorized": False,
    }
