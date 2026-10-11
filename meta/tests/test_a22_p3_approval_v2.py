from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "approval_v2.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_approval_v2", MODULE_PATH)
assert SPEC and SPEC.loader
approval_v2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(approval_v2)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, option: str = "usd25") -> tuple[Path, Path, Path, dict]:
    plan = tmp_path / "plan.md"
    plan.write_text("proposal snapshot\n", encoding="utf-8")
    seal = tmp_path / "seal.json"
    seal.write_text(json.dumps({
        "schema": 1,
        "record_type": "p3_v2_plan_seal",
        "proposal_sha256": _sha(plan),
        "packet_seal_sha256": _sha(approval_v2.PACKET_SEAL),
    }, separators=(",", ":")), encoding="utf-8")
    record = {
        "schema": 2,
        "record_type": "p3_v2_owner_approval",
        "proposal_sha256": _sha(plan),
        "accepted_v2_seal_sha256": _sha(seal),
        "owner_accepted": True,
        "owner_acceptance_provenance": "TRANSCRIPT_EVIDENCE_NONCRYPTOGRAPHIC",
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "acceptance_evidence": {
            "record_type": "p3_owner_acceptance_transcript_evidence",
            "accepted_utc": "2026-10-11T00:00:00Z", "transcript_ref": "test-only fixture",
            "transcript_sha256": "a" * 64,
            "exact_quote": "I accept OBSERVED_NO_RETRY for the test-only fixture.",
            "decision_ref": "test-only fixture decision", "proposal_sha256": _sha(plan),
            "accepted_v2_seal_sha256": _sha(seal),
        },
        "authorized_phases": ["route_check", "qualification"],
        "selected_resource_option": option,
        "options": {
            "usd25": {
                "route_rates_usd_per_million": {
                    "codex": {"input": 1.0, "output": 2.0},
                    "qwen": {"input": 0.5, "output": 1.0},
                },
                "estimated_total_usd": 20.0,
                "named_operator": "Ada Owner",
                "exploratory_calls_counted": True,
            },
            "token_only": {
                "codex_aggregate_limit_tokens": 5_000_000,
                "known_prior_codex_usage_tokens": 153_614,
                "remaining_codex_tokens_at_approval": 4_846_386,
                "qwen_aggregate_limit_tokens": None,
                "accepted_scorer_readings_per_route": 120,
                "named_operator": "Ada Owner",
                "exploratory_calls_counted": True,
            },
        },
        "preflight_status": "PASSED",
        "dispatch_allowed": True,
        "test_only_fixture": True,
    }
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps(record), encoding="utf-8")
    return approval, plan, seal, record


def test_live_v2_record_is_unselected_and_denied_without_dispatch():
    record = json.loads(approval_v2.APPROVAL.read_text(encoding="utf-8"))
    assert record == approval_v2.draft_record()
    assert record["selected_resource_option"] is None
    assert record["accepted_v2_seal_sha256"] is None
    assert record["dispatch_allowed"] is False
    assert record["retry_evidence_policy"] == "UNSELECTED"
    with pytest.raises(ValueError, match="unselected"):
        approval_v2.validate()


def test_usd25_option_is_unsupported_even_with_zero_rates_or_low_asserted_cost(tmp_path):
    approval, plan, seal, _ = _fixture(tmp_path, "usd25")
    record = json.loads(approval.read_text(encoding="utf-8"))
    for route in record["options"]["usd25"]["route_rates_usd_per_million"].values():
        route["input"] = 0
        route["output"] = 0
    record["options"]["usd25"]["estimated_total_usd"] = 0
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="USD 25 option is unsupported"):
        approval_v2.validate(approval, plan, seal)


def test_valid_token_only_policy_passes_pure_validation(tmp_path):
    approval, plan, seal, _ = _fixture(tmp_path, "token_only")
    assert approval_v2.validate(approval, plan, seal)["selected_resource_option"] == "token_only"


@pytest.mark.parametrize("value,match", [
    ("UNSELECTED", "retry evidence policy is unselected"),
    ("PROVIDER_ZERO_RETRIES", "retry evidence policy is unknown"),
    ([], "retry evidence policy is unknown"),
])
def test_retry_evidence_policy_must_be_owner_selected_supported_value(tmp_path, value, match):
    approval, plan, seal, record = _fixture(tmp_path, "token_only")
    record["retry_evidence_policy"] = value
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        approval_v2.validate(approval, plan, seal)


def test_retry_policy_must_appear_in_recorded_owner_quote(tmp_path):
    approval, plan, seal, record = _fixture(tmp_path, "token_only")
    record["acceptance_evidence"]["exact_quote"] = "I accept the protocol."
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="quote does not select"):
        approval_v2.validate(approval, plan, seal)


def test_token_policy_fixes_codex_only_limit_and_qwen_has_no_aggregate_cap(tmp_path):
    approval, plan, seal, record = _fixture(tmp_path, "token_only")
    option = record["options"]["token_only"]
    assert option["codex_aggregate_limit_tokens"] == 5_000_000
    assert option["known_prior_codex_usage_tokens"] == 153_614
    assert option["remaining_codex_tokens_at_approval"] == 4_846_386
    assert option["qwen_aggregate_limit_tokens"] is None
    assert option["accepted_scorer_readings_per_route"] == 120
    assert approval_v2.validate(approval, plan, seal)["selected_resource_option"] == "token_only"


@pytest.mark.parametrize("field,value", [
    ("codex_aggregate_limit_tokens", 5_040_000),
    ("known_prior_codex_usage_tokens", None),
    ("remaining_codex_tokens_at_approval", 5_000_000),
    ("qwen_aggregate_limit_tokens", 5_000_000),
    ("accepted_scorer_readings_per_route", 240),
    ("exploratory_calls_counted", False),
])
def test_invalid_or_missing_accepted_limits_fail_closed(tmp_path, field, value):
    approval, plan, seal, record = _fixture(tmp_path, "token_only")
    record["options"]["token_only"][field] = value
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match=r"Codex-only 5,000,000 limit|exploratory calls must count"):
        approval_v2.validate(approval, plan, seal)


def test_policy_validator_requires_explicit_phases_and_a_completed_preflight(tmp_path):
    approval, plan, seal, record = _fixture(tmp_path)
    record["authorized_phases"] = ["route_check"]
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="phase authorization"):
        approval_v2.validate(approval, plan, seal)


def test_stale_proposal_and_stale_seal_fail_closed(tmp_path):
    approval, plan, seal, _ = _fixture(tmp_path)
    plan.write_text("changed proposal\n", encoding="utf-8")
    with pytest.raises(ValueError, match="proposal changed"):
        approval_v2.validate(approval, plan, seal)


def test_stale_seal_fails_closed(tmp_path):
    approval, plan, seal, _ = _fixture(tmp_path)
    seal.write_text(seal.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="seal is missing or has changed"):
        approval_v2.validate(approval, plan, seal)


def test_rehashed_compound_seal_with_wrong_packet_seal_fails(tmp_path):
    approval, plan, seal, record = _fixture(tmp_path, "token_only")
    compound = json.loads(seal.read_text(encoding="utf-8"))
    compound["packet_seal_sha256"] = "0" * 64
    seal.write_text(json.dumps(compound), encoding="utf-8")
    record["accepted_v2_seal_sha256"] = _sha(seal)
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="current proposal and packet seal"):
        approval_v2.validate(approval, plan, seal)


def test_compound_seal_fails_when_current_packet_seal_changes(tmp_path):
    approval, plan, seal, _ = _fixture(tmp_path, "token_only")
    packet_seal = tmp_path / "packet-seal.json"
    packet_seal.write_bytes(approval_v2.PACKET_SEAL.read_bytes() + b" ")
    with pytest.raises(ValueError, match="current proposal and packet seal"):
        approval_v2.validate(approval, plan, seal, packet_seal)


def test_owner_boolean_is_not_owner_provenance(tmp_path):
    approval, plan, seal, record = _fixture(tmp_path, "token_only")
    record["owner_acceptance_provenance"] = "VERIFIED"
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="transcript provenance"):
        approval_v2.validate(approval, plan, seal)


def test_missing_option_operator_or_rates_fail_closed(tmp_path):
    approval, plan, seal, record = _fixture(tmp_path)
    record["selected_resource_option"] = None
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="resource option"):
        approval_v2.validate(approval, plan, seal)

    approval, plan, seal, record = _fixture(tmp_path)
    record["options"].pop("token_only")
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="both V2 resource options"):
        approval_v2.validate(approval, plan, seal)


def test_missing_operator_and_rates_remain_fail_closed_under_unsupported_usd_path(tmp_path):
    child = tmp_path / "operator"
    child.mkdir()
    approval, plan, seal, record = _fixture(child)
    record["options"]["usd25"]["named_operator"] = None
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="USD 25 option is unsupported"):
        approval_v2.validate(approval, plan, seal)

    child = tmp_path / "rates"
    child.mkdir()
    approval, plan, seal, record = _fixture(child)
    record["options"]["usd25"]["route_rates_usd_per_million"] = None
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="USD 25 option is unsupported"):
        approval_v2.validate(approval, plan, seal)


def test_v1_approval_record_is_not_accepted_as_v2(tmp_path):
    approval, plan, seal, _ = _fixture(tmp_path)
    v1 = Path(__file__).parents[1] / "experiments" / "a22-p3" / "runs" / "owner-approval.json"
    approval.write_text(v1.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="schema is malformed"):
        approval_v2.validate(approval, plan, seal)
