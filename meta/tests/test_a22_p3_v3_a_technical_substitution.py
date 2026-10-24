"""Offline gates for one infrastructure-invalid A scorer substitution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path[:0] = [str(ROOT / "successors"), str(ROOT)]

import v3_qualification_technical_substitution as trial  # noqa: E402


def test_exact_one_call_id_change_and_unchanged_future_order() -> None:
    schedule = trial.read(trial.SCHEDULE)
    trial.verify_schedule(schedule)
    old = trial._old_schedule()
    plan = trial.full_plan()
    original = trial.prior.call_plan()
    assert len(plan) == len(original) == 128
    assert plan[:87] == original[:87]
    assert plan[87]["call_id"] == trial.read(trial.PLAN)["new_call_id"]
    assert plan[88:] == original[88:]
    assert schedule["cells"][21]["packet_id"] == old["cells"][21]["packet_id"]
    assert schedule["cells"][21]["scorers"] != old["cells"][21]["scorers"]


def test_terminal_503_and_all_accepted_evidence_are_bound() -> None:
    result = trial.validate_predecessor()
    assert result["accepted_prefix"] == 87
    assert result["predecessor_charged_with_failure"] == 1_489_919
    trial.verify_seal()


def test_default_deny_and_no_runtime_before_authorization() -> None:
    assert trial.read(trial.APPROVAL) == trial.approval_template()
    with pytest.raises(trial.SubstitutionError, match="approval"):
        trial.verify_approval(dispatch=True)
    assert not trial.RUNTIME.exists()


def test_preflight_record_binds_current_cli_and_settings() -> None:
    facts = trial._preflight_record()
    assert facts["seal_sha256"] == trial.sha(trial.SEAL)
    assert facts["codex_cli_version"] == "codex-cli 0.162.1"
    assert facts["codex_executable_sha256"] == trial.sha(trial.prior.CODEX)
    assert facts["qwen_cli_version"] == "0.24.7"
    assert (
        facts["qwen_effective_settings_sha256"]
        == trial.read(trial.prior.SEAL)["headroom_effective_qwen_settings"]["effective_sha256"]
    )


def test_replacement_plan_cannot_relabel_old_scorer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = trial.read(trial.PLAN)
    changed = {**plan, "new_call_id": plan["old_call_id"]}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(changed))
    monkeypatch.setattr(trial, "PLAN", path)
    with pytest.raises(trial.SubstitutionError, match="collides"):
        trial.verify_schedule(trial.read(trial.SCHEDULE))
