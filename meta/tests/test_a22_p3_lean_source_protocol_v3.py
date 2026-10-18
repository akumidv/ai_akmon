"""Prospective lean source protocol remains exact and default deny."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(EXPERIMENT))
spec = importlib.util.spec_from_file_location(
    "lean_source_protocol_v3", EXPERIMENT / "lean_source_protocol_v3.py")
assert spec and spec.loader
protocol = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = protocol
spec.loader.exec_module(protocol)
ledger_spec = importlib.util.spec_from_file_location(
    "lean_usage_ledger_v3", EXPERIMENT / "usage_ledger_v3.py")
assert ledger_spec and ledger_spec.loader
ledger = importlib.util.module_from_spec(ledger_spec)
sys.modules[ledger_spec.name] = ledger
ledger_spec.loader.exec_module(ledger)
runner_spec = importlib.util.spec_from_file_location("lean_source_runner_v3", EXPERIMENT / "v3_runner.py")
assert runner_spec and runner_spec.loader
runner = importlib.util.module_from_spec(runner_spec)
sys.modules[runner_spec.name] = runner
runner_spec.loader.exec_module(runner)


def test_prior_proposal_seal_remains_unchanged_but_no_longer_seals_adopted_code():
    assert protocol.sha256(protocol.SEAL) == "e47596e5d3b7f0cbd9e9b15554665cc0d3a3e1428d9c13ab11eab9bfb78f0b8a"
    with pytest.raises(protocol.ProtocolError, match="stale"):
        protocol.validate_seal()
    with pytest.raises(protocol.ProtocolError, match="stale"):
        protocol.validate_approval()


def test_lean_reservation_denies_when_input_cap_exceeds_remaining_ceiling(tmp_path: Path):
    proposal, packet, approval = (tmp_path / "proposal.md", tmp_path / "packet.json",
                                  tmp_path / "approval.json")
    proposal.write_text("q1461 remains terminal\n", encoding="utf-8")
    packet.write_text("{}\n", encoding="utf-8")
    approval.write_text(json.dumps({
        "schema": 1, "record_type": "p3_v3_owner_approval", "owner_accepted": False,
        "dispatch_allowed": False, "authorized_phases": [], "preflight_status": "NOT_RUN",
    }), encoding="utf-8")
    path = tmp_path / "ledger.jsonl"
    ledger.initialize(path, plan=proposal, packet_seal=packet, approval=approval)
    with pytest.raises(ledger.LedgerError, match="token ceiling"):
        ledger.reserve("codex", "technical", quota_snapshot={
            "captured_utc": "stable", "source": "fixture", "source_version": "v1",
            "freshness_seconds": 0, "five_hour_used_percent": 1,
            "five_hour_reset_utc": "stable", "weekly_used_percent": 1,
            "weekly_reset_utc": "stable", "raw_redacted_sha256": "a" * 64,
        }, path=path, token_reservation=ledger.CODEX_LIMIT + 1)


def test_operational_adoption_keeps_proposal_approval_separate_from_code_hash(tmp_path: Path):
    seal_path = tmp_path / "operational-seal.json"
    seal_path.write_text(json.dumps(protocol.expected_operational_seal()), encoding="utf-8")
    approval_path = tmp_path / "operational-approval.json"
    approval = protocol.operational_approval_template(seal_path=seal_path)
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(protocol.ProtocolError):
        protocol.validate_operational_approval(approval_path, seal_path=seal_path)

    assert approval["proposal_acceptance"]["message_id"] == "msg_01a1402b-806a-7a31-9fe9-a662b3f251ae"
    assert approval["proposal_acceptance"]["requested_seal_sha256"] == protocol.sha256(protocol.SEAL)
    assert approval["implementation_acceptance"]["owner_accepted"] is False
    assert approval["dispatch_allowed"] is False


def test_operational_preflight_report_is_exact_and_offline(tmp_path: Path):
    seal_path = tmp_path / "operational-seal.json"
    seal_path.write_text(json.dumps(protocol.expected_operational_seal()), encoding="utf-8")
    report_path = tmp_path / "preflight.json"
    report_path.write_text(json.dumps(protocol.expected_preflight_report(seal_path=seal_path)), encoding="utf-8")
    checked = protocol.validate_preflight_report(report_path, seal_path=seal_path)
    assert checked["network_calls"] == checked["provider_calls"] == 0
    assert checked["dispatch_allowed"] is False
    changed = json.loads(report_path.read_text())
    changed["network_calls"] = 1
    report_path.write_text(json.dumps(changed))
    with pytest.raises(protocol.ProtocolError, match="stale or incomplete"):
        protocol.validate_preflight_report(report_path, seal_path=seal_path)


def test_checked_operational_seal_and_report_bind_the_current_candidate():
    seal = json.loads(protocol.OPERATIONAL_SEAL.read_text())
    assert seal == protocol.expected_operational_seal()
    report = protocol.validate_preflight_report()
    assert report["operational_seal_sha256"] == protocol.sha256(protocol.OPERATIONAL_SEAL)
    assert report["provider_calls"] == report["network_calls"] == 0
    assert all(report["checks"].values())
    approval = json.loads(protocol.OPERATIONAL_APPROVAL.read_text())
    assert approval == protocol.operational_approval_template()
    assert approval["proposal_acceptance"]["owner_accepted"] is True
    assert approval["implementation_acceptance"]["owner_accepted"] is False


def test_runner_rejects_prospective_default_deny_before_provider_lookup(tmp_path: Path):
    with pytest.raises(runner.RunnerError, match="successor seal is stale"):
        runner.run_technical_source(
            output_dir=tmp_path / "output", scratch=tmp_path / "scratch",
            rollout_root=tmp_path / "rollouts", approval=protocol.APPROVAL)
    assert not (tmp_path / "output").exists()
