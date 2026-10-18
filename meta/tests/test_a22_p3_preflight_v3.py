from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parents[1] / "experiments" / "a22-p3"
LEDGER_SPEC = importlib.util.spec_from_file_location("usage_ledger_v3", HERE / "usage_ledger_v3.py")
assert LEDGER_SPEC and LEDGER_SPEC.loader
ledger = importlib.util.module_from_spec(LEDGER_SPEC)
LEDGER_SPEC.loader.exec_module(ledger)
sys.modules["usage_ledger_v3"] = ledger
SOURCE_SPEC = importlib.util.spec_from_file_location("source_v3", HERE / "source_v3.py")
assert SOURCE_SPEC and SOURCE_SPEC.loader
source = importlib.util.module_from_spec(SOURCE_SPEC)
SOURCE_SPEC.loader.exec_module(source)
sys.modules["source_v3"] = source
PREFLIGHT_SPEC = importlib.util.spec_from_file_location("preflight_v3", HERE / "preflight_v3.py")
assert PREFLIGHT_SPEC and PREFLIGHT_SPEC.loader
preflight = importlib.util.module_from_spec(PREFLIGHT_SPEC)
PREFLIGHT_SPEC.loader.exec_module(preflight)


def _inputs(tmp_path: Path):
    plan = tmp_path / "plan.md"
    plan.write_text("q1461 remains terminal\n", encoding="utf-8")
    packet = tmp_path / "packet.json"
    packet.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema": 1,
                "record_type": "p3_v3_owner_approval",
                "owner_accepted": False,
                "dispatch_allowed": False,
                "authorized_phases": [],
                "preflight_status": "NOT_RUN",
            }
        ),
        encoding="utf-8",
    )
    seal = tmp_path / "seal.json"
    sources = {
        "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md": ledger.sha256(plan),
        "usage_ledger_v3.py": ledger.sha256(HERE / "usage_ledger_v3.py"),
        "dispatch_v3.py": ledger.sha256(HERE / "dispatch_v3.py"),
        "v3_runner.py": ledger.sha256(HERE / "v3_runner.py"),
        "quota_adapter_v3.py": ledger.sha256(HERE / "quota_adapter_v3.py"),
        "preflight_v3.py": ledger.sha256(HERE / "preflight_v3.py"),
        "source_v3.py": ledger.sha256(HERE / "source_v3.py"),
    }
    seal.write_text(
        json.dumps(
            {
                "schema": 1,
                "record_type": "p3_v3_plan_seal",
                "proposal_sha256": ledger.sha256(plan),
                "packet_seal_sha256": ledger.sha256(packet),
                "source_sha256": sources,
                "settings": {
                    "codex_cli": "0.156.1",
                    "codex_model": "gpt-6-astra",
                    "qwen_cli": "0.24.7",
                    "qwen_model": "qwen3.8-27b",
                    "qwen_thinking": "default",
                    "codex_epoch_limit_tokens": 5_000_000,
                    "five_hour_stop_percent": 80,
                    "weekly_stop_percent": 90,
                    "retry_evidence_policy": "OBSERVED_NO_RETRY",
                },
            }
        ),
        encoding="utf-8",
    )
    return plan, packet, approval, seal


def test_preflight_checks_seal_policy_ids_and_stays_fail_closed(tmp_path):
    plan, packet, approval, seal = _inputs(tmp_path)
    result = preflight.run_preflight(
        runtime_root=tmp_path / "runtime", plan=plan, packet_seal=packet, approval=approval, seal_path=seal
    )
    assert result["network_or_provider_calls"] == 0
    assert result["dispatch_allowed"] is False
    assert result["synthetic_policy_checks"] == {
        "missing_usage_locks_dispatch": "PASSED",
        "token_ceiling_stops_dispatch": "PASSED",
        "quota_stop_control_locks_dispatch": "PASSED",
    }
    assert result["historical_id_collision_checks"]["sample_size"] == 64
    assert result["q1461_source_rejection"] == "PASSED"
    assert result["status"] == "BLOCKED_STATIC_EVIDENCE"
    assert result["additional_required_evidence"]


def test_preflight_rejects_stale_v3_seal_before_static_checks(tmp_path):
    plan, packet, approval, seal = _inputs(tmp_path)
    plan.write_text("changed after seal\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="V3 seal"):
        preflight.run_preflight(
            runtime_root=tmp_path / "runtime", plan=plan, packet_seal=packet, approval=approval, seal_path=seal
        )


def test_preflight_rejects_runtime_inside_sealed_tree(tmp_path):
    with pytest.raises(ledger.LedgerError, match="outside the repository"):
        preflight.run_preflight(runtime_root=HERE / "scratch")


def test_additional_evidence_checks_report_verified_and_missing_artifacts(tmp_path):
    result = preflight._required_evidence(ledger.PLAN, ledger.APPROVAL, tmp_path)

    assert result["route checks explicitly unscored"]["status"] == "BLOCKED"
    assert "96-reading-per-route schedule and 240-pass ceiling reconciled" in result
    assert result["96-reading-per-route schedule and 240-pass ceiling reconciled"]["status"] == "PASSED"
    assert (
        "owner acceptance: False" in result["96-reading-per-route schedule and 240-pass ceiling reconciled"]["detail"]
    )
    assert result["V2 artifacts matched an authoritative immutable hash manifest"]["status"] == "BLOCKED"
    assert result["technical source excluded from scored qualification map"]["status"] == "BLOCKED"
    assert result["source provenance evaluator-only and scorer payload blinded"]["status"] == "BLOCKED"
    assert result["four subject mechanics controls and their pins/limits verified"]["status"] == "BLOCKED"
    key = "writable runtime manifest proves all writable targets and sealed inputs read-only"
    assert result[key]["status"] == "BLOCKED"
