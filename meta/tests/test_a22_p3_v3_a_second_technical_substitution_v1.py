"""Offline guards for the second infrastructure-invalid A scorer substitution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path[:0] = [str(ROOT / "successors"), str(ROOT)]

import v3_qualification_second_technical_substitution_v1 as trial  # noqa: E402


def test_only_second_failed_scorer_id_changes() -> None:
    schedule = trial.read(trial.SCHEDULE)
    trial.verify_schedule(schedule)
    old = trial.previous.full_plan()
    new = trial.full_plan()
    assert len(old) == len(new) == 128
    assert new[:95] == old[:95]
    assert new[95]["call_id"] == trial.read(trial.PLAN)["new_call_id"]
    assert new[96:] == old[96:]
    assert new[95]["run_id"] == old[95]["run_id"]


def test_two_predecessors_and_second_503_are_bound() -> None:
    result = trial.validate_predecessor()
    assert result["accepted_prefix"] == 95
    assert result["predecessor_accepted_calls"] == 8
    assert result["predecessor_ledger_sha256"] == trial.sha(trial.previous.LEDGER)


def test_replacement_uses_second_predecessor_exchange_and_request() -> None:
    row = trial.full_plan()[95]
    exchange = trial.previous.RUNTIME / "exchanges" / f"{row['run_id']}.json"
    assert exchange.is_file()
    trial._configure_base()
    try:
        visible, request = trial._guarded_render(trial.read(trial.SCHEDULE)["cells"][23], trial.read(exchange))
    finally:
        trial._reset_base()
    assert visible and trial.prior.sha_bytes(request) == trial.read(trial.PLAN)["request_sha256"]


def test_default_deny_and_fresh_runtime() -> None:
    assert trial.read(trial.APPROVAL) == trial.approval_template()
    with pytest.raises(trial.SubstitutionError, match="approval"):
        trial.verify_approval(dispatch=True)
    assert not trial.RUNTIME.exists()


def test_old_call_id_cannot_be_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = trial.read(trial.PLAN)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({**plan, "new_call_id": plan["old_call_id"]}))
    monkeypatch.setattr(trial, "PLAN", path)
    with pytest.raises(trial.SubstitutionError, match="collides"):
        trial.verify_schedule(trial.read(trial.SCHEDULE))
