"""Offline checks for the prospective identity-bound A qualification package."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))

import v3_qualification_id_bound as trial  # noqa: E402


def test_fresh_schedule_excludes_both_terminal_attempts() -> None:
    candidate = trial.schedule.read(trial.schedule.SCHEDULE)
    trial.schedule.verify_schedule(candidate)
    identifiers = {
        identifier
        for row in candidate["cells"]
        for identifier in (
            row["run_id"],
            row["subject_attempt_id"],
            row["packet_id"],
            *row["subject_call_ids"],
            *(item["call_id"] for item in row["scorers"]),
        )
    }
    assert not identifiers.intersection(trial.schedule.prior_ids())
    assert len(trial.call_plan()) == 128


def test_blind_packet_has_the_new_identical_request_for_both_scorers() -> None:
    row = trial.schedule.read(trial.schedule.SCHEDULE)["cells"][0]
    case = trial.read(HERE / "cases" / f"{row['case']}.json")
    first_reply = "No selection"
    second_prompt = trial.source._second_prompt(case, first_reply)[2]
    exchange = {
        "run_id": row["run_id"],
        "turns": [
            {"user": case["subject"]["turn1"], "assistant": first_reply},
            {"user": second_prompt, "assistant": "The owner should verify the result."},
        ],
    }
    visible, request = trial.packet.render(row, exchange)
    assert request == trial.scorer.make_request(trial.packet.PROMPT.read_bytes(), visible)
    assert row["run_id"].encode() not in visible
    assert row["tier"].encode() not in visible


def test_missing_new_route_evidence_blocks_seal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        trial,
        "NEW_ROUTE_OUTCOMES",
        {"codex": tmp_path / "codex.json", "qwen": tmp_path / "qwen.json"},
    )
    monkeypatch.setattr(trial, "NEW_ROUTE_LEDGER", tmp_path / "route-events.jsonl")
    with pytest.raises(trial.QualificationError, match="route evidence is absent"):
        trial.seal_body()


def test_seal_binds_passing_successor_and_new_codex_opening() -> None:
    body = trial.seal_body()
    assert body["opening_codex_tokens"] == 572_310
    assert body["identity_bound_route_seal_sha256"] == trial.sha(trial.NEW_ROUTE_SEAL)
    assert body["identity_bound_route_ledger_sha256"] == trial.sha(trial.NEW_ROUTE_LEDGER)
    assert body["planned_calls"] == 128


def test_gateway_failure_blocks_qwen_before_reservation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import v3_id_bound_route_successor as route

    runtime = tmp_path / "runtime"
    monkeypatch.setattr(trial, "RUNTIME", runtime)
    monkeypatch.setattr(trial, "LEDGER", runtime / "qualification-events.jsonl")
    monkeypatch.setattr(trial, "verify_seal", lambda: None)
    monkeypatch.setattr(trial, "verify_approval", lambda **_kwargs: None)
    monkeypatch.setattr(trial, "sha", lambda _path: "test-seal")
    monkeypatch.setattr(
        trial,
        "read",
        lambda _path: {
            "status": "PASSED_OFFLINE_QUALIFICATION_SUCCESSOR_PREFLIGHT",
            "operational_seal_sha256": "test-seal",
            "provider_calls": 0,
            "dispatch_allowed": False,
            "planned_calls": 128,
            "opening_codex_tokens": 572_310,
            "gateway_probe": "verified_tls_handshake_without_api_request",
        },
    )
    monkeypatch.setattr(trial, "_state", lambda: (2, 572_310))
    monkeypatch.setattr(trial, "call_plan", lambda: [{}, {}, {"route": "qwen"}])
    monkeypatch.setattr(trial, "_call", lambda *_args: pytest.fail("provider call reached"))

    def failed_gateway() -> None:
        raise route.RouteError("Qwen gateway DNS/TLS probe failed")

    monkeypatch.setattr(route, "check_gateway_tls", failed_gateway)
    with pytest.raises(route.RouteError, match="DNS/TLS"):
        trial.advance()
    assert len(trial.LEDGER.read_text().splitlines()) == 1


def test_unaccepted_package_cannot_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seal = tmp_path / "seal.json"
    seal.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    preflight = tmp_path / "preflight.json"
    preflight.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(trial, "SEAL", seal)
    monkeypatch.setattr(trial, "APPROVAL", approval)
    monkeypatch.setattr(trial, "PREFLIGHT", preflight)
    approval.write_text(json.dumps(trial.approval_template()), encoding="utf-8")
    trial.verify_approval(dispatch=False)
    with pytest.raises(trial.QualificationError, match="approval"):
        trial.verify_approval(dispatch=True)
