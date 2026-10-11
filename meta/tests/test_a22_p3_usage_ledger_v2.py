from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "usage_ledger_v2.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_usage_ledger_v2", MODULE_PATH)
assert SPEC and SPEC.loader
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> ledger.LedgerPaths:
    plan = tmp_path / "plan.md"
    plan.write_text("proposal\n", encoding="utf-8")
    packet_seal = tmp_path / "packet-seal.json"
    packet_seal.write_text('{"packet":"sealed"}\n', encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({
        "schema": 2,
        "record_type": "p3_v2_owner_approval",
        "proposal_sha256": _sha(plan),
        "accepted_v2_seal_sha256": None,
        "owner_accepted": True,
        "owner_acceptance_provenance": "UNIMPLEMENTED",
        "selected_resource_option": "token_only",
        "options": {"token_only": {
            "codex_aggregate_limit_tokens": 5_000_000,
            "known_prior_codex_usage_tokens": 153_614,
            "remaining_codex_tokens_at_approval": 4_846_386,
            "qwen_aggregate_limit_tokens": None,
            "accepted_scorer_readings_per_route": 120,
            "exploratory_calls_counted": True,
        }},
        "dispatch_allowed": False,
    }), encoding="utf-8")
    path = tmp_path / "attempt-ledger.jsonl"
    paths = (path, plan, packet_seal, approval)
    ledger.initialize(paths)
    return paths


def _artifact(paths: ledger.LedgerPaths, attempt_id: str, usage: dict[str, int]) -> dict[str, str]:
    artifact_path = paths[0].parent / f"{attempt_id}.usage.json"
    artifact_path.write_text(json.dumps({
        "request_id": f"request-{attempt_id}",
        "session_id": f"session-{attempt_id}",
        "model_id": "pinned-model-test-fixture",
        "usage": usage,
    }, sort_keys=True), encoding="utf-8")
    return {
        "artifact_path": artifact_path.name,
        "artifact_sha256": _sha(artifact_path),
        "request_id": f"request-{attempt_id}",
        "session_id": f"session-{attempt_id}",
        "model_id": "pinned-model-test-fixture",
    }


def _accept(paths: ledger.LedgerPaths, attempt_id: str,
            input_tokens: int = 10, output_tokens: int = 5) -> None:
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    ledger.complete_attempt(
        attempt_id,
        outcome="accepted",
        actual_usage=usage,
        usage_artifact=_artifact(paths, attempt_id, usage),
        paths=paths,
    )


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
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        ledger.initialize(paths)
    assert path.read_bytes() == original


def test_reservations_bind_approval_and_append_monotonic_usage(tmp_path):
    paths = _fixture(tmp_path)
    path, _, _, approval = paths
    attempt_id = ledger.reserve_attempt("codex", "scored_reading", paths)
    assert re.fullmatch(r"[0-9a-f]{32}", attempt_id)
    with pytest.raises(ledger.LedgerError, match="unresolved attempt"):
        ledger.reserve_attempt("qwen", "scored_reading", paths)
    _accept(paths, attempt_id)
    next_id = ledger.reserve_attempt("qwen", "scored_reading", paths)
    assert next_id != attempt_id
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()][1:]
    assert [event["seq"] for event in events] == [1, 2, 3]
    assert [event["event"] for event in events] == ["reserved", "completed", "reserved"]
    assert all("event_sha256" in event and "previous_event_sha256" in event for event in events)
    assert events[0]["attempt_class"] == "scored_reading"
    assert all(event["approval_sha256"] == _sha(approval) for event in events)
    assert all(event["selected_resource_option"] == "token_only" for event in events)
    summary = ledger.summary(paths)
    assert (summary["reserved_attempts"], summary["accepted_attempts"], summary["unresolved_attempts"]) == (2, 1, 1)
    assert summary["codex_observed_aggregate_tokens"] == 153_629
    assert summary["qwen_observed_tokens"] == 0
    assert summary["codex_remaining_tokens"] == 4_846_371
    assert summary["hard_token_cap_enforced"] is False
    assert summary["dispatch_readiness"] == ledger.DISPATCH_READINESS
    assert summary["accounting_scope"] == ledger.ACCOUNTING_SCOPE


def test_approval_hash_change_invalidates_ledger_and_readiness(tmp_path):
    paths = _fixture(tmp_path)
    approval = paths[3]
    record = json.loads(approval.read_text(encoding="utf-8"))
    record["non_authorizing_note"] = "changed after ledger creation"
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="stale"):
        ledger.summary(paths)


def test_missing_usage_is_recorded_as_failed_and_stops_its_route(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("codex", "scored_reading", paths)
    with pytest.raises(ledger.LedgerError, match="recorded as failed"):
        ledger.complete_attempt(attempt_id, outcome="accepted", paths=paths)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 1
    assert summary["failed_attempts"] == 1
    assert summary["measured_attempts"] == 0
    assert summary["codex_usage_complete"] is False
    assert summary["codex_observed_aggregate_tokens"] is None
    assert summary["dispatch_readiness"] == ledger.DISPATCH_READINESS
    with pytest.raises(ledger.LedgerError, match="codex route is stopped"):
        ledger.reserve_attempt("codex", "scored_reading", paths)
    assert ledger.reserve_attempt("qwen", "scored_reading", paths)


def test_missing_or_malformed_usage_correlation_fails_and_preserves_unverified_status(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("qwen", "scored_reading", paths)
    usage = {"input_tokens": 1_000, "output_tokens": 900}
    with pytest.raises(ledger.LedgerError, match="structured usage metadata"):
        ledger.complete_attempt(attempt_id, outcome="accepted", actual_usage=usage, paths=paths)
    summary = ledger.summary(paths)
    assert summary["failed_attempts"] == 1
    assert summary["qwen_observed_tokens"] == 1_900
    assert summary["usage_provenance_status"] == ledger.USAGE_PROVENANCE
    assert summary["dispatch_readiness"] == ledger.DISPATCH_READINESS


def test_accepted_completion_with_failure_code_is_rejected_before_append(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("codex", "scored_reading", paths)
    usage = {"input_tokens": 10, "output_tokens": 5}
    artifact = _artifact(paths, attempt_id, usage)
    before = paths[0].read_bytes()

    with pytest.raises(ledger.LedgerError, match="accepted completion has a failure code"):
        ledger.complete_attempt(
            attempt_id, outcome="accepted", actual_usage=usage,
            usage_artifact=artifact, failure_code="attempt_failed", paths=paths,
        )

    assert paths[0].read_bytes() == before
    assert ledger.summary(paths)["unresolved_attempts"] == 1
    ledger.complete_attempt(
        attempt_id, outcome="accepted", actual_usage=usage,
        usage_artifact=artifact, paths=paths,
    )
    assert ledger.summary(paths)["accepted_attempts"] == 1


def test_reservations_are_exclusive_under_concurrent_calls(tmp_path):
    paths = _fixture(tmp_path)

    def reserve():
        try:
            return ledger.reserve_attempt("codex", "scored_reading", paths)
        except ledger.LedgerError:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: reserve(), range(8)))
    assert sum(result is not None for result in results) == 1
    assert ledger.summary(paths)["reserved_attempts"] == 1


def test_stale_proposal_or_packet_seal_invalidates_ledger(tmp_path):
    paths = _fixture(tmp_path)
    paths[1].write_text("changed proposal\n", encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="stale"):
        ledger.reserve_attempt("codex", "scored_reading", paths)


def test_stale_packet_seal_invalidates_ledger(tmp_path):
    child = tmp_path / "packet"
    child.mkdir()
    paths = _fixture(child)
    paths[2].write_text('{"packet":"changed"}\n', encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="stale"):
        ledger.reserve_attempt("codex", "scored_reading", paths)


def test_duplicate_opaque_id_cannot_be_reused(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = "a" * 32
    assert ledger.reserve_attempt("codex", "scored_reading", paths, attempt_id) == attempt_id
    _accept(paths, attempt_id)
    with pytest.raises(ledger.LedgerError, match="already used"):
        ledger.reserve_attempt("qwen", "scored_reading", paths, attempt_id)


def test_120_accepted_scored_readings_per_route_excludes_route_checks(tmp_path):
    paths = _fixture(tmp_path)
    for _ in range(ledger.SCORER_READINGS_PER_ROUTE):
        attempt_id = ledger.reserve_attempt("codex", "scored_reading", paths)
        _accept(paths, attempt_id)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 120
    assert summary["codex_reserved_attempts"] == 120
    assert summary["codex_accepted_attempts"] == 120
    assert summary["accepted_scored_readings_by_route"]["codex"] == 120
    assert summary["codex_observed_scorer_tokens"] == 1_800
    with pytest.raises(ledger.LedgerError, match="accepted scorer-reading allowance"):
        ledger.reserve_attempt("codex", "scored_reading", paths)
    route_check = ledger.reserve_attempt("codex", "route_check", paths)
    _accept(paths, route_check)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 121
    assert summary["accepted_route_checks_by_route"]["codex"] == 1
    assert summary["accepted_scored_readings_by_route"]["codex"] == 120
    assert summary["codex_observed_route_check_tokens"] == 15
    for _ in range(ledger.SCORER_READINGS_PER_ROUTE):
        attempt_id = ledger.reserve_attempt("qwen", "scored_reading", paths)
        _accept(paths, attempt_id)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 241
    assert summary["qwen_reserved_attempts"] == 120
    assert summary["qwen_accepted_attempts"] == 120
    with pytest.raises(ledger.LedgerError, match="accepted scorer-reading allowance"):
        ledger.reserve_attempt("qwen", "scored_reading", paths)
    qwen_check = ledger.reserve_attempt("qwen", "route_check", paths)
    _accept(paths, qwen_check)
    assert ledger.summary(paths)["accepted_route_checks_by_route"]["qwen"] == 1


def test_qwen_usage_has_no_aggregate_token_limit(tmp_path):
    paths = _fixture(tmp_path)
    for _ in range(3):
        attempt_id = ledger.reserve_attempt("qwen", "scored_reading", paths)
        _accept(paths, attempt_id, input_tokens=20_000, output_tokens=2_000)
    summary = ledger.summary(paths)
    assert summary["qwen_observed_tokens"] == 66_000
    assert summary["qwen_aggregate_limit_tokens"] is None


def test_codex_limit_includes_known_prior_usage_and_stops_at_reached_total(tmp_path):
    paths = _fixture(tmp_path)
    for _ in range(231):
        attempt_id = ledger.reserve_attempt("codex", "route_check", paths)
        _accept(paths, attempt_id, input_tokens=20_000, output_tokens=1_000)
    summary = ledger.summary(paths)
    assert summary["codex_observed_aggregate_tokens"] == 5_004_614
    assert summary["codex_remaining_tokens"] == 0
    with pytest.raises(ledger.LedgerError, match="reached the 5,000,000-token limit"):
        ledger.reserve_attempt("codex", "scored_reading", paths)
    # Qwen is not subject to Codex's aggregate limit.
    assert ledger.reserve_attempt("qwen", "scored_reading", paths)


def test_reservation_requires_explicit_attempt_class(tmp_path):
    paths = _fixture(tmp_path)
    with pytest.raises(TypeError):
        ledger.reserve_attempt("codex", paths=paths)


@pytest.mark.parametrize(("route", "usage"), [
    ("codex", {"input_tokens": 20_001, "output_tokens": 1_000}),
    ("codex", {"input_tokens": 20_000, "output_tokens": 1_001}),
    ("qwen", {"input_tokens": 20_001, "output_tokens": 2_000}),
    ("qwen", {"input_tokens": 20_000, "output_tokens": 2_001}),
])
def test_per_call_breach_is_recorded_and_stops_only_that_route(tmp_path, route, usage):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt(route, "route_check", paths)
    with pytest.raises(ledger.LedgerError, match="per-call token allowance breached"):
        ledger.complete_attempt(
            attempt_id, outcome="accepted", actual_usage=usage,
            usage_artifact=_artifact(paths, attempt_id, usage), paths=paths,
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
    attempt_id = ledger.reserve_attempt("codex", "scored_reading", paths)
    _accept(paths, attempt_id)
    records = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines()]
    records[2]["actual_usage"]["input_tokens"] += 1
    paths[0].write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="hash chain is invalid"):
        ledger.summary(paths)


def test_usage_artifact_must_match_recorded_tokens_and_correlation(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("codex", "scored_reading", paths)
    usage = {"input_tokens": 10, "output_tokens": 5}
    artifact = _artifact(paths, attempt_id, usage)
    artifact_path = paths[0].parent / artifact["artifact_path"]
    artifact_path.write_text(json.dumps({"request_id": artifact["request_id"],
                                         "session_id": artifact["session_id"],
                                         "model_id": artifact["model_id"],
                                         "usage": {"input_tokens": 999, "output_tokens": 5}}), encoding="utf-8")
    artifact["artifact_sha256"] = _sha(artifact_path)
    with pytest.raises(ledger.LedgerError, match="does not match"):
        ledger.complete_attempt(attempt_id, outcome="accepted", actual_usage=usage,
                                usage_artifact=artifact, paths=paths)
    assert ledger.summary(paths)["unresolved_attempts"] == 1


def test_codex_missing_usage_fails_closed_and_blocks_further_reservations(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("codex", "scored_reading", paths)
    with pytest.raises(ledger.LedgerError, match="recorded as failed"):
        ledger.complete_attempt(attempt_id, outcome="accepted", paths=paths)
    summary = ledger.summary(paths)
    assert summary["codex_usage_complete"] is False
    assert summary["codex_observed_aggregate_tokens"] is None
    assert summary["codex_remaining_tokens"] is None
    with pytest.raises(ledger.LedgerError, match="codex route is stopped"):
        ledger.reserve_attempt("codex", "scored_reading", paths)


def test_subject_attempts_are_classed_linked_and_share_codex_usage_budget(tmp_path):
    paths = _fixture(tmp_path)
    parent = ledger.register_subject_attempt("a" * 32, "scored", paths=paths)
    call_id = ledger.reserve_subject_call(parent, "turn-1", paths=paths)
    usage = {"input_tokens": 200, "output_tokens": 50}
    artifact = _artifact(paths, call_id, usage)
    ledger.complete_subject_call(call_id, outcome="accepted", actual_usage=usage,
                                 usage_artifact=artifact, paths=paths)
    summary = ledger.summary(paths)
    assert summary["registered_subject_attempts"] == 6  # five provenance-limited legacy markers
    assert summary["scored_subject_attempts"] == 1
    assert summary["codex_observed_subject_tokens"] == 250
    assert summary["codex_observed_aggregate_tokens"] == 153_864
    events = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines()][1:]
    reserved = next(event for event in events if event.get("attempt_class") == "subject_call")
    assert (reserved["subject_attempt_id"], reserved["turn_id"], reserved["continuation_id"]) == (parent, "turn-1", None)


def test_subject_call_uses_full_observed_usage_without_scorer_per_call_ceilings(tmp_path):
    paths = _fixture(tmp_path)
    parent = ledger.register_subject_attempt("9" * 32, "scored", paths=paths)
    call_id = ledger.reserve_subject_call(parent, "turn-1", paths=paths)
    usage = {"input_tokens": 45_000, "output_tokens": 3_500}
    ledger.complete_subject_call(call_id, outcome="accepted", actual_usage=usage,
                                 usage_artifact=_artifact(paths, call_id, usage), paths=paths)
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


def test_subject_attempt_partition_counts_historical_snapshot_and_enforces_ceiling(tmp_path):
    paths = _fixture(tmp_path)
    for index in range(19):
        ledger.register_subject_attempt(f"{index + 1:032x}", "technical", paths=paths)
    assert ledger.summary(paths)["technical_subject_attempts"] == 24
    with pytest.raises(ledger.LedgerError, match="technical plus defect.*24"):
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
    next_parent = ledger.register_subject_attempt("e" * 32, "scored", paths=paths)
    with pytest.raises(ledger.LedgerError, match="codex route is stopped"):
        ledger.reserve_subject_call(next_parent, "turn-1", paths=paths)
