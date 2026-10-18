"""Offline fail-closed checks for the V3 qualification call scheduler."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("v3_qualification_successor", HERE / "v3_qualification_successor.py")
assert SPEC and SPEC.loader
dispatch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dispatch)


def test_fixed_call_plan_has_all_subject_and_scorer_calls() -> None:
    plan = dispatch.call_plan()
    assert len(plan) == 128
    assert len({call["call_id"] for call in plan}) == 128
    assert sum(call["kind"] == "subject" for call in plan) == 64
    assert sum(call["kind"] == "scorer" and call["route"] == "codex" for call in plan) == 32
    assert sum(call["kind"] == "scorer" and call["route"] == "qwen" for call in plan) == 32
    for offset in range(0, 128, 4):
        assert [call["kind"] for call in plan[offset : offset + 4]] == ["subject", "subject", "scorer", "scorer"]
        assert [call.get("turn") for call in plan[offset : offset + 2]] == [1, 2]


def test_seal_binds_live_predecessor_accounting() -> None:
    body = dispatch.seal_body()
    assert body["opening_codex_tokens"] == 285_782
    assert body["codex_limit_tokens"] == 5_000_000
    assert body["planned_calls"] == 128
    assert body["scope"] == ["qualification"]
    assert body["retry_evidence_policy"] == "OBSERVED_NO_RETRY"
    assert body["scorer_output_settings"] == {"codex": 1000, "qwen": 5000}
    assert body["format_prompt_sha256"] == dispatch.sha(dispatch.packet.PROMPT)


def test_fresh_schedule_excludes_terminal_attempt_ids() -> None:
    candidate = dispatch.schedule.read(dispatch.schedule.SCHEDULE)
    dispatch.schedule.verify_schedule(candidate)
    assert not dispatch.schedule.prior_ids().intersection(
        {
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
    )


def test_fresh_packet_uses_identical_blind_format_request_for_both_routes() -> None:
    row = dispatch.schedule.read(dispatch.schedule.SCHEDULE)["cells"][0]
    case = dispatch.read(HERE / "cases" / f"{row['case']}.json")
    first_reply = "No selection"
    second_prompt = dispatch.source._second_prompt(case, first_reply)[2]
    exchange = {
        "run_id": row["run_id"],
        "turns": [
            {"user": case["subject"]["turn1"], "assistant": first_reply},
            {"user": second_prompt, "assistant": "The owner should verify the result."},
        ],
    }
    visible, request = dispatch.packet.render(row, exchange)
    assert request == dispatch.scorer.make_request(dispatch.packet.PROMPT.read_bytes(), visible)
    assert dispatch.packet.PROMPT.read_bytes().endswith(dispatch.qwen_route.FORMAT_SUFFIX)
    assert row["run_id"].encode() not in visible
    assert row["tier"].encode() not in visible


def test_approval_is_default_deny_without_exact_phase_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seal = tmp_path / "seal.json"
    seal.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    preflight = tmp_path / "preflight.json"
    preflight.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(dispatch, "SEAL", seal)
    monkeypatch.setattr(dispatch, "APPROVAL", approval)
    monkeypatch.setattr(dispatch, "PREFLIGHT", preflight)
    approval.write_text(json.dumps(dispatch.approval_template()), encoding="utf-8")
    dispatch.verify_approval(dispatch=False)
    with pytest.raises(dispatch.QualificationError, match="approval"):
        dispatch.verify_approval(dispatch=True)


def test_unresolved_reservation_blocks_another_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seal = tmp_path / "seal.json"
    seal.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(dispatch, "SEAL", seal)
    monkeypatch.setattr(dispatch, "APPROVAL", approval)
    monkeypatch.setattr(dispatch, "RUNTIME", tmp_path)
    monkeypatch.setattr(dispatch, "LEDGER", tmp_path / "ledger.jsonl")
    dispatch.write_new(dispatch.LEDGER, (json.dumps(dispatch._header(), sort_keys=True) + "\n").encode())
    first = dispatch.call_plan()[0]
    dispatch._append({"event": "reserved", "call": first})
    with pytest.raises(dispatch.QualificationError, match="unresolved reservation"):
        dispatch._state()


def test_failed_completion_blocks_next_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seal = tmp_path / "seal.json"
    seal.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(dispatch, "SEAL", seal)
    monkeypatch.setattr(dispatch, "APPROVAL", approval)
    monkeypatch.setattr(dispatch, "RUNTIME", tmp_path)
    monkeypatch.setattr(dispatch, "LEDGER", tmp_path / "ledger.jsonl")
    dispatch.write_new(dispatch.LEDGER, (json.dumps(dispatch._header(), sort_keys=True) + "\n").encode())
    first = dispatch.call_plan()[0]
    dispatch._append({"event": "reserved", "call": first})
    dispatch._append({"event": "completed", "call": first, "status": "failed", "usage": None})
    with pytest.raises(dispatch.QualificationError, match="prior call failed"):
        dispatch._state()
