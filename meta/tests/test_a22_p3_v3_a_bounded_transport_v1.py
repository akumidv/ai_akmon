"""Offline guards for the bounded A transport recovery successor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path[:0] = [str(ROOT / "successors"), str(ROOT)]

import v3_qualification_bounded_transport_v1 as trial  # noqa: E402


def test_only_failed_first_subject_turn_id_changes() -> None:
    old = trial.previous.full_plan()
    new = trial.full_plan()
    assert len(old) == len(new) == 128
    assert new[:96] == old[:96]
    assert new[96]["kind"] == "subject"
    assert new[96]["turn"] == 1
    assert new[96]["call_id"] == trial.read(trial.PLAN)["new_call_id"]
    assert new[96]["run_id"] == old[96]["run_id"]
    assert new[97:] == old[97:]


def test_three_terminal_failures_and_96_accepted_calls_bound() -> None:
    result = trial.validate_predecessor()
    assert result["accepted_prefix"] == 96
    assert result["predecessor_accepted_calls"] == 1
    assert result["predecessor_ledger_sha256"] == trial.sha(trial.previous.LEDGER)
    assert trial.read(trial.PLAN)["transport_failure_limit"] == 8
    assert trial.read(trial.PLAN)["predecessor_transport_failures"] == 3


def test_old_call_id_cannot_be_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = trial.read(trial.PLAN)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({**plan, "new_call_id": plan["old_call_id"]}))
    monkeypatch.setattr(trial, "PLAN", path)
    with pytest.raises(trial.SubstitutionError, match="collides"):
        trial.verify_schedule(trial.read(trial.SCHEDULE))


def test_second_subject_turn_remains_bound_to_replacement() -> None:
    schedule = trial.read(trial.SCHEDULE)
    row = schedule["cells"][24]
    assert row["subject_call_ids"][0] == trial.read(trial.PLAN)["new_call_id"]
    assert row["subject_call_ids"][1] == trial.read(trial.previous.SCHEDULE)["cells"][24]["subject_call_ids"][1]
    assert trial.full_plan()[97]["run_id"] == trial.full_plan()[96]["run_id"]


def test_approval_is_limited_to_one_successor_phase() -> None:
    template = trial.approval_template()
    assert template["dispatch_allowed"] is False
    assert template["authorized_phases"] == []
    assert template["seal_sha256"] == trial.sha(trial.SEAL)
