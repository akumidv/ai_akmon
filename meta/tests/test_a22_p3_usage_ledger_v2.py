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
    assert header["max_attempts"] == 240
    assert header["planned_accounting_envelope_tokens"] == 5_040_000
    assert header["hard_token_cap_enforced"] is False
    assert header["dispatch_readiness"] == "DENIED_UNVERIFIED_OWNER_AND_USAGE_PROVENANCE"
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        ledger.initialize(paths)
    assert path.read_bytes() == original


def test_reservations_bind_approval_and_append_monotonic_usage(tmp_path):
    paths = _fixture(tmp_path)
    path, _, _, approval = paths
    attempt_id = ledger.reserve_attempt("codex", paths)
    assert re.fullmatch(r"[0-9a-f]{32}", attempt_id)
    with pytest.raises(ledger.LedgerError, match="unresolved or failed"):
        ledger.reserve_attempt("qwen", paths)
    _accept(paths, attempt_id)
    next_id = ledger.reserve_attempt("qwen", paths)
    assert next_id != attempt_id
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()][1:]
    assert [event["seq"] for event in events] == [1, 2, 3]
    assert [event["event"] for event in events] == ["reserved", "completed", "reserved"]
    assert all(event["approval_sha256"] == _sha(approval) for event in events)
    assert all(event["selected_resource_option"] == "token_only" for event in events)
    summary = ledger.summary(paths)
    assert (summary["reserved_attempts"], summary["accepted_attempts"], summary["unresolved_attempts"]) == (2, 1, 1)
    assert summary["observed_total_tokens"] == 15
    assert summary["hard_token_cap_enforced"] is False
    assert summary["dispatch_readiness"] == "DENIED_UNVERIFIED_OWNER_AND_USAGE_PROVENANCE"


def test_approval_hash_change_invalidates_ledger_and_readiness(tmp_path):
    paths = _fixture(tmp_path)
    approval = paths[3]
    record = json.loads(approval.read_text(encoding="utf-8"))
    record["non_authorizing_note"] = "changed after ledger creation"
    approval.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="stale"):
        ledger.summary(paths)


def test_missing_usage_is_recorded_as_failed_and_stops_reservations(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("codex", paths)
    with pytest.raises(ledger.LedgerError, match="recorded as failed"):
        ledger.complete_attempt(attempt_id, outcome="accepted", paths=paths)
    summary = ledger.summary(paths)
    assert summary["reserved_attempts"] == 1
    assert summary["failed_attempts"] == 1
    assert summary["measured_attempts"] == 0
    assert summary["dispatch_readiness"] == "DENIED_UNVERIFIED_OWNER_AND_USAGE_PROVENANCE"
    with pytest.raises(ledger.LedgerError, match="unresolved or failed"):
        ledger.reserve_attempt("qwen", paths)


def test_missing_or_malformed_usage_correlation_fails_and_preserves_unverified_status(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("qwen", paths)
    usage = {"input_tokens": 1_000, "output_tokens": 900}
    with pytest.raises(ledger.LedgerError, match="structured usage metadata"):
        ledger.complete_attempt(attempt_id, outcome="accepted", actual_usage=usage, paths=paths)
    summary = ledger.summary(paths)
    assert summary["failed_attempts"] == 1
    assert summary["observed_total_tokens"] == 1_900
    assert summary["usage_provenance_status"] == ledger.USAGE_PROVENANCE
    assert summary["dispatch_readiness"] == "DENIED_UNVERIFIED_OWNER_AND_USAGE_PROVENANCE"


def test_reservations_are_exclusive_under_concurrent_calls(tmp_path):
    paths = _fixture(tmp_path)

    def reserve():
        try:
            return ledger.reserve_attempt("codex", paths)
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
        ledger.reserve_attempt("codex", paths)


def test_stale_packet_seal_invalidates_ledger(tmp_path):
    child = tmp_path / "packet"
    child.mkdir()
    paths = _fixture(child)
    paths[2].write_text('{"packet":"changed"}\n', encoding="utf-8")
    with pytest.raises(ledger.LedgerError, match="stale"):
        ledger.reserve_attempt("codex", paths)


def test_duplicate_opaque_id_cannot_be_reused(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = "a" * 32
    assert ledger.reserve_attempt("codex", paths, attempt_id) == attempt_id
    _accept(paths, attempt_id)
    with pytest.raises(ledger.LedgerError, match="already used"):
        ledger.reserve_attempt("qwen", paths, attempt_id)


def test_240_attempt_limit_counts_all_accepted_reservations(tmp_path):
    paths = _fixture(tmp_path)
    for _ in range(ledger.MAX_ATTEMPTS):
        attempt_id = ledger.reserve_attempt("codex", paths)
        _accept(paths, attempt_id)
    assert ledger.summary(paths)["reserved_attempts"] == 240
    with pytest.raises(ledger.LedgerError, match="allowance is exhausted"):
        ledger.reserve_attempt("codex", paths)


def test_actual_usage_above_planned_envelope_is_reported_and_blocks_next(tmp_path):
    paths = _fixture(tmp_path)
    attempt_id = ledger.reserve_attempt("codex", paths)
    _accept(paths, attempt_id, input_tokens=ledger.PLANNED_ENVELOPE_TOKENS + 1)
    summary = ledger.summary(paths)
    assert summary["observed_total_tokens"] > summary["planned_accounting_envelope_tokens"]
    assert summary["hard_token_cap_enforced"] is False
    with pytest.raises(ledger.LedgerError, match="observed aggregate exceeds"):
        ledger.reserve_attempt("qwen", paths)
