#!/usr/bin/env python3
"""Read-only reduction of the accepted A pair-restart calls across four runtimes."""

from __future__ import annotations

import json
from typing import Any

import v3_qualification_pair_restart_v1 as trial
import v3_qualification_second_technical_substitution_v1 as second

ORIGINAL_END = 87
FIRST_SUBSTITUTION_END = 95


def reduce_verified() -> dict[str, Any]:
    """Replay the sealed chain, then read each scorer from its actual generation."""
    trial.verify_seal()
    trial.verify_approval(dispatch=True)
    trial._record_attempt_outcome()
    count, charged = trial._state()
    if count != trial.NEW_CALLS or trial.read(trial.ATTEMPT_OUTCOME)["classification"] != "scored":
        raise trial.SubstitutionError("A primary grid is incomplete")
    candidate = trial.read(trial.SCHEDULE)
    steps = trial.full_plan()
    positions = {step["call_id"]: index for index, step in enumerate(steps)}
    readings: dict[str, dict[str, str]] = {}
    for row in candidate["cells"]:
        replies = {}
        for scorer in row["scorers"]:
            call_id = scorer["call_id"]
            position = positions[call_id]
            origin = (
                trial.ORIGINAL_BASE["runtime"]
                if position < ORIGINAL_END
                else trial.first.RUNTIME
                if position < FIRST_SUBSTITUTION_END
                else second.RUNTIME
                if position == FIRST_SUBSTITUTION_END
                else trial.RUNTIME
            )
            result = trial.read(origin / "evidence" / call_id / "result.json")
            if result.get("call") != steps[position]:
                raise trial.SubstitutionError("scorer origin or call differs")
            replies[scorer["route"]] = result["reply"]
        readings[row["run_id"]] = replies
    trial._configure_base()
    primary = trial.prior.reduce_module.reduce(readings, candidate=candidate)
    return {
        "schema": 1,
        "record_type": "p3_v3_a_pair_restart_offline_reduction",
        "primary": primary,
        "accepted_primary_calls": trial.ACCEPTED_PREFIX + count,
        "accepted_new_calls": count,
        "charged_codex_tokens": charged,
        "ledger_sha256": trial.sha(trial.LEDGER),
        "attempt_outcome_sha256": trial.sha(trial.ATTEMPT_OUTCOME),
        "reducer_source_sha256": trial.sha(trial.HERE / "successors/v3_a_pair_restart_offline_reduce_v1.py"),
        "provider_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(reduce_verified(), sort_keys=True))
