from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "usage_ledger_v3.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_usage_ledger_v3", MODULE_PATH)
assert SPEC and SPEC.loader
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)
sys.modules["usage_ledger_v3"] = ledger
SOURCE_PATH = MODULE_PATH.with_name("source_v3.py")
SOURCE_SPEC = importlib.util.spec_from_file_location("a22_p3_source_v3", SOURCE_PATH)
assert SOURCE_SPEC and SOURCE_SPEC.loader
source = importlib.util.module_from_spec(SOURCE_SPEC)
SOURCE_SPEC.loader.exec_module(source)


def _fixture(tmp_path: Path):
    plan = tmp_path / "proposal.md"
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
    path = tmp_path / "ledger.jsonl"
    return path, plan, packet, approval


def _quota(**overrides):
    return {
        "captured_utc": "2026-10-15T00:00:00Z",
        "source": "fixture",
        "source_version": "v1",
        "freshness_seconds": 0,
        "five_hour_used_percent": 1,
        "five_hour_reset_utc": "2026-10-15T05:00:00Z",
        "weekly_used_percent": 1,
        "weekly_reset_utc": "2026-10-20T00:00:00Z",
        "raw_redacted_sha256": "a" * 64,
        **overrides,
    }


def test_initialization_is_epoch_scoped_and_default_deny(tmp_path):
    path, plan, packet, approval = _fixture(tmp_path)
    header = ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    assert header["codex_epoch_limit_tokens"] == 5_000_000
    assert header["v3_codex_tokens_used"] == 0
    assert header["v2_known_usage_tokens_historical_only"] == 153_614
    assert header["q1461_disposition_historical_only"] == "UNKNOWN_USAGE"
    assert header["dispatch_ready"] is False
    with pytest.raises(FileExistsError):
        ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)


def test_quota_thresholds_missing_fields_and_staleness_stop(tmp_path):
    ledger.validate_quota(_quota(), "codex")
    for bad in (
        _quota(five_hour_used_percent=80),
        _quota(weekly_used_percent=90),
        _quota(freshness_seconds=601),
        {"source": "missing"},
    ):
        with pytest.raises(ledger.LedgerError):
            ledger.validate_quota(bad, "codex")


def test_unknown_codex_usage_locks_next_reservation_and_keeps_v2_separate(tmp_path):
    path, plan, packet, approval = _fixture(tmp_path)
    ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    call_id = ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=path)
    ledger.complete(
        call_id, outcome="failed", usage=None, quota_snapshot=_quota(), path=path, failure_code="usage_missing"
    )
    assert ledger.summary(path)["unknown_codex_usage"] is True
    assert ledger.summary(path)["v3_codex_tokens_used"] == 0
    assert ledger.summary(path)["v2_known_usage_tokens_historical_only"] == 153_614
    with pytest.raises(ledger.LedgerError, match="unknown V3 Codex usage"):
        ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=path)


def test_checkpoint_precedes_reservation_and_post_call_checkpoint_follows(tmp_path):
    path, plan, packet, approval = _fixture(tmp_path)
    ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    call_id = ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=path)
    ledger.complete(
        call_id, outcome="accepted", usage={"input_tokens": 12, "output_tokens": 3}, quota_snapshot=_quota(), path=path
    )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    events = rows[1:]
    reserve_index = next(i for i, e in enumerate(events) if e["event"] == "reserved")
    complete_index = next(i for i, e in enumerate(events) if e["event"] == "completed")
    assert events[reserve_index - 1]["event"] == "quota_checkpoint"
    assert events[complete_index + 1]["event"] == "quota_checkpoint"
    assert ledger.summary(path)["v3_codex_tokens_used"] == 15


def test_post_call_threshold_persists_known_usage_and_locks_dispatch(tmp_path):
    path, plan, packet, approval = _fixture(tmp_path)
    ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    call_id = ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=path)
    stopped = _quota(five_hour_used_percent=80)
    with pytest.raises(ledger.LedgerError, match="post-call subscription stop threshold"):
        ledger.complete(
            call_id,
            outcome="accepted",
            usage={"input_tokens": 40, "output_tokens": 7},
            quota_snapshot=stopped,
            path=path,
        )
    _, events = ledger._read(path)
    completion = next(event for event in events if event["event"] == "completed")
    checkpoint = next(event for event in reversed(events) if event["event"] == "quota_checkpoint")
    assert completion["outcome"] == "failed"
    assert completion["provider_outcome"] == "accepted"
    assert completion["failure_code"] == "subscription_quota_stop_after_call"
    assert completion["usage_status"] == "known"
    assert completion["input_tokens"] + completion["output_tokens"] == 47
    assert checkpoint["snapshot"] == stopped
    assert checkpoint["dispatch_stopped"] is True
    assert checkpoint["stop_reason"] == "codex_five_hour_threshold"
    assert ledger.summary(path)["v3_codex_tokens_used"] == 47
    with pytest.raises(ledger.LedgerError, match="prior V3 quota checkpoint permanently stopped"):
        ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=path)


def test_threshold_checkpoint_is_retained_and_stops_reservations(tmp_path):
    path, plan, packet, approval = _fixture(tmp_path)
    ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    stopped = _quota(weekly_used_percent=90)
    event = ledger.checkpoint(stopped, "codex", path=path)
    assert event["snapshot"] == stopped
    assert event["dispatch_stopped"] is True
    assert event["stop_reason"] == "codex_weekly_threshold"
    with pytest.raises(ledger.LedgerError, match="prior V3 quota checkpoint permanently stopped"):
        ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=path)


def test_post_call_quota_failure_keeps_correlated_usage_and_stops(tmp_path):
    path, plan, packet, approval = _fixture(tmp_path)
    ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    call_id = ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=path)
    with pytest.raises(ledger.LedgerError, match="post-call subscription stop threshold"):
        ledger.complete(
            call_id,
            outcome="accepted",
            usage={"input_tokens": 9, "output_tokens": 4},
            quota_snapshot={"malformed": True},
            path=path,
        )
    _, events = ledger._read(path)
    completion = next(event for event in events if event["event"] == "completed")
    checkpoint = next(event for event in reversed(events) if event["event"] == "quota_checkpoint")
    assert completion["usage_status"] == "known"
    assert completion["input_tokens"] + completion["output_tokens"] == 13
    assert completion["failure_code"] == "quota_checkpoint_failure_after_call"
    assert checkpoint["snapshot"] is None
    assert checkpoint["failure_code"] == "missing_or_invalid_quota_snapshot"
    assert checkpoint["dispatch_stopped"] is True


def test_static_preflight_has_no_dispatch_and_preserves_inputs(tmp_path):
    _, plan, packet, approval = _fixture(tmp_path)
    result = ledger.static_preflight(
        plan=plan, packet_seal=packet, approval=approval, runtime_root=tmp_path / "runtime"
    )
    assert result["network_or_provider_calls"] == 0
    assert result["dispatch_allowed"] is False
    assert result["launch_ready"] is False
    assert not list((tmp_path / "runtime").iterdir())


def test_fresh_ids_never_reuse_historical_identifier():
    assert ledger.fresh_id({"q1461"}) != "q1461"


def test_canonical_v3_approval_is_denied_until_seal_and_owner_decisions_exist(tmp_path):
    with pytest.raises(ledger.LedgerError, match="seal is unavailable"):
        ledger.validate_v3_approval(approval=ledger.APPROVAL, seal_path=tmp_path / "no-seal.json")


def test_exact_synthetic_seal_and_approval_gate(tmp_path):
    _, plan, packet, _ = _fixture(tmp_path)
    seal_path = tmp_path / "seal.json"
    sources = {
        "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md": ledger.sha256(plan),
        "usage_ledger_v3.py": ledger.sha256(ledger.HERE / "usage_ledger_v3.py"),
        "dispatch_v3.py": ledger.sha256(ledger.HERE / "dispatch_v3.py"),
        "v3_runner.py": ledger.sha256(ledger.HERE / "v3_runner.py"),
        "quota_adapter_v3.py": ledger.sha256(ledger.HERE / "quota_adapter_v3.py"),
        "preflight_v3.py": ledger.sha256(ledger.HERE / "preflight_v3.py"),
        "source_v3.py": ledger.sha256(ledger.HERE / "source_v3.py"),
    }
    settings = {
        "codex_cli": "0.156.1",
        "codex_model": "gpt-6-astra",
        "qwen_cli": "0.24.7",
        "qwen_model": "qwen3.8-27b",
        "qwen_thinking": "default",
        "codex_epoch_limit_tokens": 5_000_000,
        "five_hour_stop_percent": 80,
        "weekly_stop_percent": 90,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
    }
    seal_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "record_type": "p3_v3_plan_seal",
                "proposal_sha256": ledger.sha256(plan),
                "packet_seal_sha256": ledger.sha256(packet),
                "source_sha256": sources,
                "settings": settings,
            }
        ),
        encoding="utf-8",
    )
    seal_hash = ledger.sha256(seal_path)
    approval = tmp_path / "accepted-approval-fixture.json"
    accepted = {
        "schema": 1,
        "record_type": "p3_v3_owner_approval",
        "proposal_sha256": ledger.sha256(plan),
        "v3_seal_sha256": seal_hash,
        "owner_accepted": True,
        "new_epoch_budget_accepted": True,
        "v2_usage_exclusion_accepted": True,
        "subscription_thresholds_accepted": True,
        "qwen_uncapped_policy_accepted": True,
        "observed_no_retry_accepted": True,
        "schedule_accepted": True,
        "named_stop_operator": "Synthetic Owner",
        "authorized_phases": ["technical_source", "route_checks"],
        "acceptance_evidence": {
            "proposal_sha256": ledger.sha256(plan),
            "v3_seal_sha256": seal_hash,
            "transcript_sha256": "b" * 64,
            "exact_quote": "Synthetic fixture only.",
        },
        "preflight_status": "PASSED",
        "dispatch_allowed": True,
    }
    approval.write_text(json.dumps(accepted), encoding="utf-8")
    assert (
        ledger.validate_v3_approval(
            approval=approval, seal_path=seal_path, plan=plan, packet_seal=packet, phase="technical_source"
        )
        == accepted
    )
    with pytest.raises(ledger.LedgerError, match="does not explicitly authorize"):
        ledger.validate_v3_approval(
            approval=approval, seal_path=seal_path, plan=plan, packet_seal=packet, phase="qualification"
        )
    # The dispatchable ledger is created only after the accepted approval, so
    # its immutable header can bind the exact authorization hash.
    ledger_path = tmp_path / "accepted-ledger.jsonl"
    header = ledger.initialize(ledger_path, plan=plan, packet_seal=packet, approval=approval, seal_path=seal_path)
    assert header["approval_sha256"] == ledger.sha256(approval)


def test_source_resolver_accepts_only_hashed_two_turn_v3_exchange(tmp_path):
    path, plan, packet, approval = _fixture(tmp_path)
    ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    subject_id = "1" * 32
    calls = []
    for turn_id in ("turn-1", "turn-2"):
        call_id = ledger.reserve(
            "codex", "technical", quota_snapshot=_quota(), path=path, subject_attempt_id=subject_id, turn_id=turn_id
        )
        usage = {"input_tokens": 20, "output_tokens": 10}
        ledger.complete(call_id, outcome="accepted", usage=usage, quota_snapshot=_quota(), path=path)
        calls.append({"provider_call_id": call_id, **usage})
    run_id = "2" * 32
    case = tmp_path / "case.json"
    arm = tmp_path / "arm.txt"
    rollout = tmp_path / "rollout.jsonl"
    exchange_path = tmp_path / "exchange.json"
    case.write_text("{}\n", encoding="utf-8")
    arm.write_text("frozen arm\n", encoding="utf-8")
    rollout.write_text("synthetic rollout\n", encoding="utf-8")
    exchange = {
        "run_id": run_id,
        "turns": [
            {"user": "first", "assistant": "reply one", "events_sha256": "a" * 64},
            {"user": "second", "assistant": "reply two", "events_sha256": "b" * 64},
        ],
    }
    exchange_path.write_text(json.dumps(exchange), encoding="utf-8")
    source_hashes = {
        "case_sha256": ledger.sha256(case),
        "arm_sha256": ledger.sha256(arm),
        "exchange_sha256": ledger.sha256(exchange_path),
        "rollout_sha256": ledger.sha256(rollout),
    }
    packet_source = hashlib.sha256(
        json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    record = {
        "epoch_id": ledger.summary(path)["epoch_id"],
        "run_id": run_id,
        "subject_attempt_id": subject_id,
        "case": "P3-01",
        "arm": "A",
        "tier": "strongest",
        "repeat": 1,
        "case_sha256": source_hashes["case_sha256"],
        "arm_sha256": source_hashes["arm_sha256"],
        "model": "gpt-6-astra",
        "cli_version": "codex-cli 0.156.1",
        "thread_id": "synthetic-thread",
        "verified": True,
        "exchange_sha256": source_hashes["exchange_sha256"],
        "rollout_sha256": source_hashes["rollout_sha256"],
        "usage_calls": calls,
        "packet_source_sha256": packet_source,
        "provenance_scope": "evaluator_only",
    }
    record_path = tmp_path / "source-record.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    resolved = source.resolve_technical_source(record_path, exchange_path, case, arm, rollout, ledger_path=path)
    assert resolved["packet_source_sha256"] == packet_source
    assert resolved["provenance_scope"] == "evaluator_only"
    record["provenance_scope"] = "scored_qualification"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(source.SourceError, match="evaluator-only"):
        source.resolve_technical_source(record_path, exchange_path, case, arm, rollout, ledger_path=path)
    record["provenance_scope"] = "evaluator_only"
    record["run_id"] = "q1461"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(source.SourceError, match="q1461"):
        source.resolve_technical_source(record_path, exchange_path, case, arm, rollout, ledger_path=path)
