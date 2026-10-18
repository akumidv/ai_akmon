from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import re
import secrets
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "usage_ledger_v2.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_usage_ledger_v2", MODULE_PATH)
assert SPEC and SPEC.loader
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, *, qualified: bool = True) -> ledger.LedgerPaths:
    plan = tmp_path / "plan.md"
    plan.write_text("proposal\n", encoding="utf-8")
    packet_seal = tmp_path / "packet-seal.json"
    packet_seal.write_text('{"packet":"sealed"}\n', encoding="utf-8")
    plan_seal = tmp_path / ledger.ACCEPTED_SEAL_NAME
    seal_value = {
        "schema": 1,
        "record_type": "p3_v2_plan_seal",
        "proposal_sha256": _sha(plan),
        "packet_seal_sha256": _sha(packet_seal),
    }
    plan_seal.write_text(json.dumps(seal_value), encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema": 2,
                "record_type": "p3_v2_owner_approval",
                "proposal_sha256": _sha(plan),
                "accepted_v2_seal_sha256": _sha(plan_seal),
                "owner_accepted": True,
                "owner_acceptance_provenance": "TRANSCRIPT_EVIDENCE_NONCRYPTOGRAPHIC",
                "retry_evidence_policy": "OBSERVED_NO_RETRY",
                "acceptance_evidence": {
                    "record_type": "p3_owner_acceptance_transcript_evidence",
                    "accepted_utc": "2026-10-11T00:00:00Z",
                    "transcript_ref": "test-only fixture",
                    "transcript_sha256": "a" * 64,
                    "exact_quote": "I accept OBSERVED_NO_RETRY for the test-only fixture.",
                    "decision_ref": "test-only fixture decision",
                    "proposal_sha256": _sha(plan),
                    "accepted_v2_seal_sha256": _sha(plan_seal),
                },
                "authorized_phases": ["route_check", "qualification"],
                "selected_resource_option": "token_only",
                "options": {
                    "usd25": {
                        "route_rates_usd_per_million": None,
                        "estimated_total_usd": None,
                        "named_operator": None,
                        "exploratory_calls_counted": None,
                    },
                    "token_only": {
                        "codex_aggregate_limit_tokens": 5_000_000,
                        "known_prior_codex_usage_tokens": 153_614,
                        "remaining_codex_tokens_at_approval": 4_846_386,
                        "qwen_aggregate_limit_tokens": None,
                        "accepted_scorer_readings_per_route": 120,
                        "named_operator": "Test Fixture Operator",
                        "exploratory_calls_counted": True,
                    },
                },
                "preflight_status": "PASSED",
                "dispatch_allowed": True,
                "test_only_fixture": True,
            }
        ),
        encoding="utf-8",
    )
    path = tmp_path / "attempt-ledger.jsonl"
    paths = (path, plan, packet_seal, approval)
    ledger.initialize(paths)
    if qualified:
        _complete_route_checks(paths)
    return paths


def _artifact(
    paths: ledger.LedgerPaths,
    attempt_id: str,
    usage: dict[str, int],
    *,
    subject_attempt_id: str | None = None,
    turn_id: str | None = None,
) -> dict[str, str]:
    artifact_path = paths[0].parent / f"{attempt_id}.usage.json"
    artifact_path.write_text(
        json.dumps(
            {
                "request_id": f"request-{attempt_id}",
                "session_id": f"session-{attempt_id}",
                "model_id": "pinned-model-test-fixture",
                "call_id": attempt_id,
                "usage": usage,
                **(
                    {"subject_attempt_id": subject_attempt_id, "turn_id": turn_id}
                    if subject_attempt_id is not None
                    else {}
                ),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    artifact = {
        "artifact_path": artifact_path.name,
        "artifact_sha256": _sha(artifact_path),
        "request_id": f"request-{attempt_id}",
        "session_id": f"session-{attempt_id}",
        "model_id": "pinned-model-test-fixture",
        "call_id": attempt_id,
    }
    if subject_attempt_id is not None:
        artifact.update({"subject_attempt_id": subject_attempt_id, "turn_id": turn_id})
    return artifact


def _accept(
    paths: ledger.LedgerPaths,
    attempt_id: str,  # noqa: PLR0913
    input_tokens: int = 10,
    output_tokens: int = 5,
    subject_attempt_id: str | None = None,
    turn_id: str | None = None,
) -> None:
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    ledger.complete_attempt(
        attempt_id,
        outcome="accepted",
        actual_usage=usage,
        usage_artifact=_artifact(paths, attempt_id, usage, subject_attempt_id=subject_attempt_id, turn_id=turn_id),
        paths=paths,
    )


def _reserve_reading(
    paths: ledger.LedgerPaths,
    route: str = "codex",
    *,
    opaque_packet_id: str | None = None,
    packet_sha256: str | None = None,
    attempt_id: str | None = None,
) -> str:
    packet_id = opaque_packet_id or f"g{secrets.token_hex(8)}"
    packet_hash = packet_sha256 or hashlib.sha256(packet_id.encode()).hexdigest()
    return ledger.reserve_attempt(
        route, "scored_reading", paths, attempt_id, opaque_packet_id=packet_id, packet_sha256=packet_hash
    )


def _complete_route_checks(paths: ledger.LedgerPaths) -> None:
    for route in sorted(ledger.ROUTES):
        call_id = ledger.reserve_attempt(route, "route_check", paths)
        _accept(paths, call_id, 0, 0)


def test_live_approval_cannot_initialize_ledger_until_selected(tmp_path):
    live_approval = json.loads(ledger.APPROVAL.read_text(encoding="utf-8"))
    assert live_approval["selected_resource_option"] is None
    assert live_approval["dispatch_allowed"] is False
    path = tmp_path / "must-not-exist.jsonl"
    paths = (path, ledger.PLAN, ledger.PACKET_SEAL, ledger.APPROVAL)
    with pytest.raises(ledger.LedgerError, match="no selected resource option"):
        ledger.initialize(paths)
    assert not path.exists()


def test_initialization_binds_plan_packet_approval_and_option_exclusively(tmp_path):
    paths = _fixture(tmp_path)
    path, plan, packet_seal, approval = paths
    header = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert header["proposal_sha256"] == _sha(plan)
    assert header["packet_seal_sha256"] == _sha(packet_seal)
    assert header["approval_sha256"] == _sha(approval)
    assert header["retry_evidence_policy"] == "OBSERVED_NO_RETRY"
    assert header["selected_resource_option"] == "token_only"
    assert header["schema"] == 2
    assert header["accounting_scope"] == ledger.ACCOUNTING_SCOPE
    assert header["codex_aggregate_limit_tokens"] == 5_000_000
    assert header["known_prior_codex_usage_tokens"] == 153_614
    assert header["codex_remaining_at_start_tokens"] == 4_846_386
    assert header["qwen_aggregate_limit_tokens"] is None
    assert header["accepted_scorer_readings_per_route"] == 120
    assert header["hard_token_cap_enforced"] is False
    assert header["dispatch_readiness"] == ledger.DISPATCH_READINESS
    assert header["historical_subject_snapshot"]["count"] == 5
    assert header["historical_subject_snapshot"]["debit_again"] is False
    assert header["historical_subject_snapshot"]["usage_tokens_in_prior_aggregate"] == 126_014
    assert header["historical_subject_snapshot"]["scorer_exploratory_tokens_in_prior_aggregate"] == 27_600
    assert header["historical_subject_snapshot"]["aggregate_tokens"] == 153_614
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        ledger.initialize(paths)
    assert path.read_bytes() == original


def test_phase_gate_requires_one_route_check_per_route_before_qualification(tmp_path):
    paths = _fixture(tmp_path, qualified=False)
    with pytest.raises(ledger.LedgerError, match="both route checks"):
        ledger.register_subject_attempt("a" * 32, "scored", paths=paths)
    codex_check = ledger.reserve_attempt("codex", "route_check", paths)
    _accept(paths, codex_check, 0, 0)
    with pytest.raises(ledger.LedgerError, match="one attempt per route"):
        ledger.reserve_attempt("codex", "route_check", paths)
    with pytest.raises(ledger.LedgerError, match="both route checks"):
        _reserve_reading(paths, "codex")
    qwen_check = ledger.reserve_attempt("qwen", "route_check", paths)
    _accept(paths, qwen_check, 0, 0)
    subject_id = ledger.register_subject_attempt("a" * 32, "scored", paths=paths)
    assert subject_id == "a" * 32


def test_usage_artifact_cannot_be_reused_for_another_reserved_call(tmp_path):
    paths = _fixture(tmp_path)
    first_id = _reserve_reading(paths, "codex")
    usage = {"input_tokens": 10, "output_tokens": 5}
    first_artifact = _artifact(paths, first_id, usage)
    ledger.complete_attempt(
        first_id, outcome="accepted", actual_usage=usage, usage_artifact=first_artifact, paths=paths
    )
    second_id = _reserve_reading(paths, "codex")
    with pytest.raises(ledger.LedgerError, match=r"reused|different provider call"):
        ledger.complete_attempt(
            second_id, outcome="accepted", actual_usage=usage, usage_artifact=first_artifact, paths=paths
        )
    assert ledger.summary(paths)["unresolved_attempts"] == 1


def test_reservations_bind_approval_and_append_monotonic_usage(tmp_path):
    paths = _fixture(tmp_path)
    path, _, _, approval = paths
    attempt_id = _reserve_reading(paths, "codex")
    assert re.fullmatch(r"[0-9a-f]{32}", attempt_id)
    with pytest.raises(ledger.LedgerError, match="unresolved attempt"):
        _reserve_reading(paths, "qwen")
    _accept(paths, attempt_id)
    next_id = _reserve_reading(paths, "qwen")
    assert next_id != attempt_id
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()][1:]
    assert [event["seq"] for event in events] == list(range(1, 8))
    assert [event["event"] for event in events[4:]] == ["reserved", "completed", "reserved"]
    assert all("event_sha256" in event and "previous_event_sha256" in event for event in events)
    assert events[4]["attempt_class"] == "scored_reading"
    assert all(event["approval_sha256"] == _sha(approval) for event in events)
    assert all(event["selected_resource_option"] == "token_only" for event in events)
    summary = ledger.summary(paths)
    assert (summary["reserved_attempts"], summary["accepted_attempts"], summary["unresolved_attempts"]) == (4, 3, 1)
    assert summary["codex_observed_aggregate_tokens"] == 153_629
    assert summary["qwen_observed_tokens"] == 0
    assert summary["codex_remaining_tokens"] == 4_846_371
    assert summary["hard_token_cap_enforced"] is False
    assert summary["dispatch_readiness"] == ledger.DISPATCH_READINESS
    assert summary["accounting_scope"] == ledger.ACCOUNTING_SCOPE


def test_approval_hash_change_stops_dispatch_but_preserves_ledger_accounting(tmp_path):
    paths = _fixture(tmp_path)
    approval = paths[3]
    record = json.loads(approval.read_text(encoding="utf-8"))
    record["non_authorizing_note"] = "changed after ledger creation"
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="approval schema"):
        ledger.require_dispatch_authorization(paths, phase="qualification")
    with pytest.raises(ledger.LedgerError, match=r"stale|approval schema"):
        _reserve_reading(paths, "qwen")
    assert ledger.summary(paths)["approval_sha256"] != _sha(approval)


def test_denied_authorization_does_not_create_lock_file(tmp_path):
    paths = _fixture(tmp_path, qualified=False)
    approval = paths[3]
    record = json.loads(approval.read_text(encoding="utf-8"))
    record["owner_accepted"] = False
    approval.write_text(json.dumps(record), encoding="utf-8")
    lock_path = paths[0].with_name(paths[0].name + ".lock")

    with pytest.raises(ledger.LedgerError, match="owner approval"):
        ledger.require_dispatch_authorization(paths, phase="route_check")

    assert not lock_path.exists()


@pytest.mark.parametrize(
    "policy,match",
    [
        ("UNSELECTED", "retry evidence policy is unselected"),
        ("PROVIDER_ZERO_RETRIES", "retry evidence policy is unknown"),
        ([], "retry evidence policy is unknown"),
    ],
)
def test_dispatch_gate_requires_supported_owner_selected_retry_policy(tmp_path, policy, match):
    paths = _fixture(tmp_path, qualified=False)
    approval = paths[3]
    record = json.loads(approval.read_text(encoding="utf-8"))
    record["retry_evidence_policy"] = policy
    approval.write_text(json.dumps(record), encoding="utf-8")
    lock_path = paths[0].with_name(paths[0].name + ".lock")

    with pytest.raises(ledger.LedgerError, match=match):
        ledger.require_dispatch_authorization(paths, phase="route_check")

    assert not lock_path.exists()


def test_dispatch_gate_binds_retry_policy_to_transcript_quote(tmp_path):
    paths = _fixture(tmp_path, qualified=False)
    approval = paths[3]
    record = json.loads(approval.read_text(encoding="utf-8"))
    record["acceptance_evidence"]["exact_quote"] = "I accept the protocol."
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="quote does not select"):
        ledger.require_dispatch_authorization(paths, phase="route_check")


def test_reserved_call_can_be_accounted_after_approval_changes(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = _reserve_reading(paths, "codex")
    approval = paths[3]
    record = json.loads(approval.read_text(encoding="utf-8"))
    record["non_authorizing_note"] = "changed after provider reservation"
    approval.write_text(json.dumps(record), encoding="utf-8")
    usage = {"input_tokens": 10, "output_tokens": 5}
    artifact = _artifact(paths, attempt_id, usage)

    ledger.complete_attempt(attempt_id, outcome="accepted", actual_usage=usage, usage_artifact=artifact, paths=paths)

    with pytest.raises(ledger.LedgerError, match=r"stale|approval schema"):
        _reserve_reading(paths, "qwen")
    summary = ledger.summary(paths)
    assert summary["accepted_attempts"] == 3
    assert summary["codex_observed_aggregate_tokens"] == 153_629


def test_missing_usage_is_recorded_as_failed_and_stops_its_route(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = _reserve_reading(paths, "codex")
    with pytest.raises(ledger.LedgerError, match="recorded as failed"):
        ledger.complete_attempt(attempt_id, outcome="accepted", paths=paths)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 3
    assert summary["failed_attempts"] == 1
    assert summary["measured_attempts"] == 2
    assert summary["codex_usage_complete"] is False
    assert summary["codex_observed_aggregate_tokens"] is None
    assert summary["dispatch_readiness"] == ledger.DISPATCH_READINESS
    with pytest.raises(ledger.LedgerError, match=r"unknown Codex usage|codex route is stopped"):
        _reserve_reading(paths, "codex")
    with pytest.raises(ledger.LedgerError, match="unknown Codex usage blocks all provider routes"):
        _reserve_reading(paths, "qwen")


def test_missing_or_malformed_usage_correlation_fails_and_preserves_unverified_status(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = _reserve_reading(paths, "qwen")
    usage = {"input_tokens": 1_000, "output_tokens": 900}
    with pytest.raises(ledger.LedgerError, match="structured usage metadata"):
        ledger.complete_attempt(attempt_id, outcome="accepted", actual_usage=usage, paths=paths)
    summary = ledger.summary(paths)
    assert summary["failed_attempts"] == 1
    assert summary["qwen_observed_tokens"] == 0
    assert summary["usage_provenance_status"] == ledger.USAGE_PROVENANCE
    assert summary["dispatch_readiness"] == ledger.DISPATCH_READINESS


def test_accepted_completion_with_failure_code_is_rejected_before_append(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = _reserve_reading(paths, "codex")
    usage = {"input_tokens": 10, "output_tokens": 5}
    artifact = _artifact(paths, attempt_id, usage)
    before = paths[0].read_bytes()

    with pytest.raises(ledger.LedgerError, match="accepted completion has a failure code"):
        ledger.complete_attempt(
            attempt_id,
            outcome="accepted",
            actual_usage=usage,
            usage_artifact=artifact,
            failure_code="attempt_failed",
            paths=paths,
        )

    assert paths[0].read_bytes() == before
    assert ledger.summary(paths)["unresolved_attempts"] == 1
    ledger.complete_attempt(
        attempt_id,
        outcome="accepted",
        actual_usage=usage,
        usage_artifact=artifact,
        paths=paths,
    )
    assert ledger.summary(paths)["accepted_attempts"] == 3


def test_reservations_are_exclusive_under_concurrent_calls(tmp_path):
    paths = _fixture(tmp_path)

    def reserve():
        try:
            return _reserve_reading(paths, "codex")
        except ledger.LedgerError:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))
    assert sum(result is not None for result in results) == 1
    assert ledger.summary(paths)["reserved_attempts"] == 3


def test_stale_proposal_or_packet_seal_invalidates_ledger(tmp_path):
    paths = _fixture(tmp_path)
    paths[1].write_text("changed proposal\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="stale"):
        _reserve_reading(paths, "codex")


def test_stale_packet_seal_invalidates_ledger(tmp_path):
    child = tmp_path / "packet"
    child.mkdir()
    paths = _fixture(child)
    paths[2].write_text('{"packet":"changed"}\n', encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="stale"):
        _reserve_reading(paths, "codex")


def test_duplicate_opaque_id_cannot_be_reused(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = "a" * 32
    assert _reserve_reading(paths, "codex", attempt_id=attempt_id) == attempt_id
    _accept(paths, attempt_id)
    with pytest.raises(ledger.LedgerError, match="already used"):
        _reserve_reading(paths, "qwen", attempt_id=attempt_id)


def test_accepted_packet_cannot_be_reserved_again_on_same_route(tmp_path):
    paths = _fixture(tmp_path)
    packet_id = "g0123456789abcdef"
    packet_hash = "b" * 64
    attempt_id = _reserve_reading(paths, "codex", opaque_packet_id=packet_id, packet_sha256=packet_hash)
    _accept(paths, attempt_id)
    with pytest.raises(ledger.LedgerError, match="packet was already reserved"):
        _reserve_reading(paths, "codex", opaque_packet_id=packet_id, packet_sha256=packet_hash)
    # The other scorer route may read the same blinded packet once.
    assert _reserve_reading(paths, "qwen", opaque_packet_id=packet_id, packet_sha256=packet_hash)


def test_unresolved_packet_cannot_be_reserved_again_on_same_route(tmp_path):
    paths = _fixture(tmp_path)
    packet_id = "g0123456789abcdef"
    packet_hash = "c" * 64
    _reserve_reading(paths, "codex", opaque_packet_id=packet_id, packet_sha256=packet_hash)
    with pytest.raises(ledger.LedgerError, match="packet was already reserved"):
        _reserve_reading(paths, "codex", opaque_packet_id=packet_id, packet_sha256=packet_hash)
    assert ledger.summary(paths)["unresolved_attempts"] == 1


def test_120_accepted_scored_readings_per_route_excludes_route_checks(tmp_path):
    paths = _fixture(tmp_path)
    for _ in range(ledger.SCORER_READINGS_PER_ROUTE):
        attempt_id = _reserve_reading(paths, "codex")
        _accept(paths, attempt_id)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 122
    assert summary["codex_reserved_attempts"] == 121
    assert summary["codex_accepted_attempts"] == 121
    assert summary["accepted_scored_readings_by_route"]["codex"] == 120
    assert summary["codex_observed_scorer_tokens"] == 1_800
    with pytest.raises(ledger.LedgerError, match="accepted scorer-reading allowance"):
        _reserve_reading(paths, "codex")
    assert summary["accepted_route_checks_by_route"]["codex"] == 1
    assert summary["accepted_scored_readings_by_route"]["codex"] == 120
    assert summary["codex_observed_route_check_tokens"] == 0
    with pytest.raises(ledger.LedgerError, match="one attempt per route"):
        ledger.reserve_attempt("codex", "route_check", paths)
    for _ in range(ledger.SCORER_READINGS_PER_ROUTE):
        attempt_id = _reserve_reading(paths, "qwen")
        _accept(paths, attempt_id)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 242
    assert summary["qwen_reserved_attempts"] == 121
    assert summary["qwen_accepted_attempts"] == 121
    with pytest.raises(ledger.LedgerError, match="accepted scorer-reading allowance"):
        _reserve_reading(paths, "qwen")
    assert ledger.summary(paths)["accepted_route_checks_by_route"]["qwen"] == 1


def test_qwen_usage_has_no_aggregate_token_limit(tmp_path):
    paths = _fixture(tmp_path)
    for _ in range(3):
        attempt_id = _reserve_reading(paths, "qwen")
        _accept(paths, attempt_id, input_tokens=20_000, output_tokens=2_000)
    summary = ledger.summary(paths)
    assert summary["qwen_observed_tokens"] == 66_000
    assert summary["qwen_aggregate_limit_tokens"] is None


def test_codex_limit_includes_known_prior_usage_and_stops_at_reached_total(tmp_path):
    paths = _fixture(tmp_path)
    last_subject = None
    for index in range(
        ledger.MAX_SCORED_SUBJECT_ATTEMPTS
        + ledger.MAX_TECHNICAL_DEFECT_ATTEMPTS
        - len(ledger.HISTORICAL_SUBJECT_MARKERS)
    ):
        attempt_class = "scored" if index < ledger.MAX_SCORED_SUBJECT_ATTEMPTS else "technical"
        try:
            subject_id = ledger.register_subject_attempt(f"{index + 1:032x}", attempt_class, paths=paths)
            last_subject = subject_id
            call_id = ledger.reserve_subject_call(subject_id, "turn-1", paths=paths)
        except ledger.LedgerError as exc:
            assert "reached the 5,000,000-token limit" in str(exc)
            break
        usage = {"input_tokens": 45_000, "output_tokens": 3_500}
        ledger.complete_subject_call(
            call_id,
            outcome="accepted",
            actual_usage=usage,
            usage_artifact=_artifact(paths, call_id, usage, subject_attempt_id=subject_id, turn_id="turn-1"),
            paths=paths,
        )
    summary = ledger.summary(paths)
    assert summary["codex_observed_aggregate_tokens"] > ledger.CODEX_AGGREGATE_LIMIT_TOKENS
    assert summary["codex_remaining_tokens"] == 0
    with pytest.raises(ledger.LedgerError, match="reached the 5,000,000-token limit"):
        ledger.reserve_subject_call(last_subject, "turn-2", paths=paths)
    # Qwen is not subject to Codex's aggregate limit.
    assert _reserve_reading(paths, "qwen")


def test_reservation_requires_explicit_attempt_class(tmp_path):
    paths = _fixture(tmp_path)
    with pytest.raises(TypeError):
        ledger.reserve_attempt("codex", paths=paths)


@pytest.mark.parametrize(
    ("route", "usage"),
    [
        ("codex", {"input_tokens": 20_001, "output_tokens": 1_000}),
        ("codex", {"input_tokens": 20_000, "output_tokens": 1_001}),
        ("qwen", {"input_tokens": 20_001, "output_tokens": 2_000}),
        ("qwen", {"input_tokens": 20_000, "output_tokens": 2_001}),
    ],
)
def test_per_call_breach_is_recorded_and_stops_only_that_route(tmp_path, route, usage):
    paths = _fixture(tmp_path, qualified=False)
    attempt_id = ledger.reserve_attempt(route, "route_check", paths)
    with pytest.raises(ledger.LedgerError, match="per-call token allowance breached"):
        ledger.complete_attempt(
            attempt_id,
            outcome="accepted",
            actual_usage=usage,
            usage_artifact=_artifact(paths, attempt_id, usage),
            paths=paths,
        )
    summary = ledger.summary(paths)
    assert summary["failed_attempts"] == 1
    assert summary["stopped_routes"] == [route]
    assert summary[f"{route}_observed_input_tokens"] == usage["input_tokens"]
    assert summary[f"{route}_observed_output_tokens"] == usage["output_tokens"]
    with pytest.raises(ledger.LedgerError, match=f"{route} route is stopped"):
        ledger.reserve_attempt(route, "route_check", paths)
    other_route = "qwen" if route == "codex" else "codex"
    assert ledger.reserve_attempt(other_route, "route_check", paths)


def test_event_hash_chain_detects_usage_or_history_mutation(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = _reserve_reading(paths, "codex")
    _accept(paths, attempt_id)
    records = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines()]
    records[2]["actual_usage"]["input_tokens"] += 1
    paths[0].write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="hash chain is invalid"):
        ledger.summary(paths)


def test_usage_artifact_must_match_recorded_tokens_and_correlation(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = _reserve_reading(paths, "codex")
    usage = {"input_tokens": 10, "output_tokens": 5}
    artifact = _artifact(paths, attempt_id, usage)
    artifact_path = paths[0].parent / artifact["artifact_path"]
    artifact_path.write_text(
        json.dumps(
            {
                "request_id": artifact["request_id"],
                "session_id": artifact["session_id"],
                "model_id": artifact["model_id"],
                "usage": {"input_tokens": 999, "output_tokens": 5},
            }
        ),
        encoding="utf-8",
    )
    artifact["artifact_sha256"] = _sha(artifact_path)
    with pytest.raises(ledger.LedgerError, match="does not match"):
        ledger.complete_attempt(
            attempt_id, outcome="accepted", actual_usage=usage, usage_artifact=artifact, paths=paths
        )
    assert ledger.summary(paths)["unresolved_attempts"] == 1


def test_codex_missing_usage_fails_closed_and_blocks_further_reservations(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = _reserve_reading(paths, "codex")
    with pytest.raises(ledger.LedgerError, match="recorded as failed"):
        ledger.complete_attempt(attempt_id, outcome="accepted", paths=paths)
    summary = ledger.summary(paths)
    assert summary["codex_usage_complete"] is False
    assert summary["codex_observed_aggregate_tokens"] is None
    assert summary["codex_remaining_tokens"] is None
    with pytest.raises(ledger.LedgerError, match=r"unknown Codex usage|codex route is stopped"):
        _reserve_reading(paths, "codex")


def test_subject_attempts_are_classed_linked_and_share_codex_usage_budget(tmp_path):
    paths = _fixture(tmp_path)
    parent = ledger.register_subject_attempt("a" * 32, "scored", paths=paths)
    call_id = ledger.reserve_subject_call(parent, "turn-1", paths=paths)
    usage = {"input_tokens": 200, "output_tokens": 50}
    artifact = _artifact(paths, call_id, usage, subject_attempt_id=parent, turn_id="turn-1")
    ledger.complete_subject_call(call_id, outcome="accepted", actual_usage=usage, usage_artifact=artifact, paths=paths)
    summary = ledger.summary(paths)
    assert summary["registered_subject_attempts"] == 6  # five provenance-limited legacy markers
    assert summary["scored_subject_attempts"] == 1
    assert summary["codex_observed_subject_tokens"] == 250
    assert summary["codex_observed_aggregate_tokens"] == 153_864
    events = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines()][1:]
    reserved = next(event for event in events if event.get("attempt_class") == "subject_call")
    assert (reserved["subject_attempt_id"], reserved["turn_id"], reserved["continuation_id"]) == (
        parent,
        "turn-1",
        None,
    )


def test_subject_call_uses_full_observed_usage_without_scorer_per_call_ceilings(tmp_path):
    paths = _fixture(tmp_path)
    parent = ledger.register_subject_attempt("9" * 32, "scored", paths=paths)
    call_id = ledger.reserve_subject_call(parent, "turn-1", paths=paths)
    usage = {"input_tokens": 45_000, "output_tokens": 3_500}
    ledger.complete_subject_call(
        call_id,
        outcome="accepted",
        actual_usage=usage,
        usage_artifact=_artifact(paths, call_id, usage, subject_attempt_id=parent, turn_id="turn-1"),
        paths=paths,
    )
    assert ledger.summary(paths)["codex_observed_subject_tokens"] == 48_500


def test_defect_origin_is_required_and_immutable(tmp_path):
    paths = _fixture(tmp_path)
    origin = ledger.register_subject_attempt("b" * 32, "scored", paths=paths)
    with pytest.raises(ledger.LedgerError, match="requires an immutable origin"):
        ledger.register_subject_attempt("c" * 32, "defect", paths=paths)
    defect = ledger.register_subject_attempt("c" * 32, "defect", origin_attempt_id=origin, paths=paths)
    with pytest.raises(ledger.LedgerError, match="already registered"):
        ledger.register_subject_attempt(defect, "defect", origin_attempt_id=origin, paths=paths)
    state = ledger._read(*paths)[2]["subject:" + defect]
    assert state["origin_attempt_id"] == origin
    ledger.validate_registered_subject_attempt(defect, "defect", origin, paths=paths)
    with pytest.raises(ledger.LedgerError, match="does not match immutable ledger class and origin"):
        ledger.validate_registered_subject_attempt(defect, "technical", None, paths=paths)


def test_subject_attempt_partition_counts_historical_snapshot_and_enforces_ceiling(tmp_path):
    paths = _fixture(tmp_path)
    for index in range(19):
        ledger.register_subject_attempt(f"{index + 1:032x}", "technical", paths=paths)
    assert ledger.summary(paths)["technical_subject_attempts"] == 24
    with pytest.raises(ledger.LedgerError, match=r"technical plus defect.*24"):
        ledger.register_subject_attempt("f" * 32, "technical", paths=paths)


def test_subject_call_without_usage_blocks_future_codex_dispatch(tmp_path):
    paths = _fixture(tmp_path)
    parent = ledger.register_subject_attempt("d" * 32, "technical", paths=paths)
    call_id = ledger.reserve_subject_call(parent, "turn-1", continuation_id="retry-1", paths=paths)
    with pytest.raises(ledger.LedgerError, match="recorded as failed"):
        ledger.complete_subject_call(call_id, outcome="accepted", paths=paths)
    summary = ledger.summary(paths)
    assert summary["codex_usage_complete"] is False
    assert summary["codex_observed_aggregate_tokens"] is None
    with pytest.raises(ledger.LedgerError, match="unknown Codex usage blocks all provider routes"):
        ledger.register_subject_attempt("e" * 32, "scored", paths=paths)
