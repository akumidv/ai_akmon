"""Offline guards for the A22 cell-25 pair restart."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path[:0] = [str(ROOT / "successors"), str(ROOT)]

import v3_qualification_pair_restart_v1 as trial  # noqa: E402


def test_only_cell25_attempt_and_two_call_ids_change() -> None:
    old = trial.read(trial.previous.SCHEDULE)
    new = trial.read(trial.SCHEDULE)
    plan = trial.read(trial.PLAN)
    trial.verify_schedule(new)
    assert new["cells"][:24] == old["cells"][:24]
    assert new["cells"][25:] == old["cells"][25:]
    assert new["cells"][24]["run_id"] == old["cells"][24]["run_id"]
    assert new["cells"][24]["packet_id"] == old["cells"][24]["packet_id"]
    assert new["cells"][24]["subject_attempt_id"] == plan["new_subject_attempt_id"]
    assert new["cells"][24]["subject_call_ids"] == plan["new_call_ids"]
    assert trial.full_plan()[:96] == trial.previous.full_plan()[:96]
    assert trial.full_plan()[98:] == trial.previous.full_plan()[98:]


def test_predecessor_superseded_turn_and_failed_turn_are_charged() -> None:
    result = trial.validate_predecessor()
    assert result["accepted_prefix"] == 96
    assert result["superseded_accepted_calls"] == 1
    assert trial.read(trial.PLAN)["opening_codex_tokens"] == 1_608_025
    assert trial.read(trial.PLAN)["predecessor_transport_failures"] == 4


def test_pair_id_collision_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = trial.read(trial.PLAN)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({**plan, "new_call_ids": [plan["old_call_ids"][0], plan["new_call_ids"][1]]}))
    monkeypatch.setattr(trial, "PLAN", path)
    with pytest.raises(trial.SubstitutionError, match="collides"):
        trial.verify_schedule(trial.read(trial.SCHEDULE))


def test_second_prompt_comes_from_new_first_reply() -> None:
    row = trial.read(trial.SCHEDULE)["cells"][24]
    case = trial.read(trial.HERE / "cases" / f"{row['case']}.json")
    no_check = trial.prior.source._second_prompt(case, "No request for a check.")[2]
    item = case["subject"]["menu"][0]
    with_check = trial.prior.source._second_prompt(case, f"CHECK: {item['id']}")[2]
    assert no_check == case["subject"]["no_item_reply"]
    assert with_check == item["output"]
    assert no_check != with_check
    assert row["subject_call_ids"] == trial.read(trial.PLAN)["new_call_ids"]


def test_approval_defaults_to_no_dispatch() -> None:
    template = trial.approval_template()
    assert template["dispatch_allowed"] is False
    assert template["authorized_phases"] == []
