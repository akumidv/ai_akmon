"""Offline fail-closed checks for the V3 remaining mechanics controls."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("v3_controls_test", ROOT / "v3_controls.py")
assert SPEC is not None and SPEC.loader is not None
controls = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controls)


def test_schedule_and_default_deny() -> None:
    assert controls.CELLS == (
        ("A", "mid", "gpt-5.6-luna"),
        ("C", "strongest", "gpt-6-astra"),
        ("C", "mid", "gpt-5.6-luna"),
    )
    assert json.loads(controls.SEAL.read_text())["opening_codex_tokens"] == 74_257
    assert controls.verify_approval(dispatch=False)["authorized_phases"] == []
    with pytest.raises(controls.ControlError, match="acceptance"):
        controls.verify_approval(dispatch=True)


def test_stale_seal_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stale = json.loads(controls.SEAL.read_text())
    stale["opening_codex_tokens"] = 66_491
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(stale))
    monkeypatch.setattr(controls, "SEAL", path)
    monkeypatch.setattr(controls, "seal_body", lambda: {**stale, "opening_codex_tokens": 74_257})
    with pytest.raises(controls.ControlError, match="stale"):
        controls.verify_seal()


def test_unknown_or_unresolved_call_blocks_following_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps({"record_type": "p3_v3_controls_ledger"}) + "\n")
    monkeypatch.setattr(controls, "LEDGER", path)
    controls._append({"event": "reserved", "call_id": "one"})
    with pytest.raises(controls.ControlError, match="unresolved"):
        controls._usage_state()
    controls._append({"event": "completed", "call_id": "one", "usage_status": "UNKNOWN_USAGE"})
    with pytest.raises(controls.ControlError, match="unknown"):
        controls._usage_state()


def test_observed_retry_marker_is_rejected() -> None:
    assert controls._retry_markers([{"type": "turn.failed"}], b"")
    assert controls._retry_markers([{"type": "turn.completed", "payload": {"status": "retrying"}}], b"")
    assert controls._retry_markers([], b"retrying request")
    assert not controls._retry_markers([{"type": "turn.completed"}], b"")


def test_unaccepted_execute_starts_no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("provider process started before approval")

    monkeypatch.setattr(controls.subprocess, "Popen", forbidden)
    monkeypatch.setattr(controls, "offline_preflight", lambda: {"status": "passed"})
    with pytest.raises(controls.ControlError, match="acceptance"):
        controls.run()
    assert not controls.RUNTIME.exists()


def test_budget_and_quota_stop_gates() -> None:
    controls.require_budget(74_257, 50_000)
    with pytest.raises(controls.ControlError, match="ceiling"):
        controls.require_budget(4_990_000, 50_000)
    snapshot = {
        "captured_utc": "2026-10-15T00:00:00Z",
        "source": "fixture",
        "source_version": "v1",
        "freshness_seconds": 0,
        "five_hour_used_percent": 80,
        "five_hour_reset_utc": "2026-10-15T05:00:00Z",
        "weekly_used_percent": 1,
        "weekly_reset_utc": "2026-10-20T00:00:00Z",
        "raw_redacted_sha256": "a" * 64,
    }
    with pytest.raises(controls.ledger.LedgerError, match="threshold"):
        controls.ledger.validate_quota(snapshot, "codex")


def test_exact_phase_approval_requires_bound_owner_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = tmp_path / "acceptance.json"
    evidence.write_text(
        json.dumps(
            {
                "record_type": "p3_v3_controls_owner_acceptance",
                "accepted_seal_sha256": controls.sha(controls.SEAL),
                "request_message_id": "request",
                "user_message_id": "reply",
                "request_text": f"technical_controls seal {controls.sha(controls.SEAL)}",
                "user_text": f"technical_controls seal {controls.sha(controls.SEAL)}; operator is owner",
            }
        )
    )
    approval = tmp_path / "approval.json"
    candidate = controls.approval_template()
    candidate.update(
        {
            "owner_accepted": True,
            "dispatch_allowed": True,
            "authorized_phases": ["technical_controls"],
            "named_stop_operator": "owner (current chat session)",
            "accepted_accounting_exception": True,
            "acceptance_evidence_sha256": controls.sha(evidence),
        }
    )
    approval.write_text(json.dumps(candidate))
    monkeypatch.setattr(controls, "ACCEPTANCE", evidence)
    monkeypatch.setattr(controls, "APPROVAL", approval)
    assert controls.verify_approval(dispatch=True)["authorized_phases"] == ["technical_controls"]


def test_charged_call_is_bound_to_its_direct_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    ledger_path = runtime / "control-events.jsonl"
    ledger_path.write_text(json.dumps({"record_type": "p3_v3_controls_ledger"}) + "\n")
    monkeypatch.setattr(controls, "RUNTIME", runtime)
    monkeypatch.setattr(controls, "LEDGER", ledger_path)
    prefix = runtime / "control-0" / "output" / "run.turn1"
    prefix.parent.mkdir(parents=True)
    events_path = Path(f"{prefix}.events.json")
    dispatch_path = Path(f"{prefix}.dispatch.json")
    stdout_path = Path(f"{prefix}.stdout.txt")
    events_path.write_text(
        json.dumps(
            [
                {"type": "thread.started", "thread_id": "session"},
                {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 3}},
            ]
        )
    )
    dispatch_path.write_text(json.dumps({"returncode": 0, "cwd": str(runtime / "control-0" / "scratch")}))
    stdout_path.write_text("raw direct event stream")
    controls._append(
        {"event": "reserved", "call_id": "call", "attempt_id": "attempt", "cell": 0, "turn": 1, "run_id": "run"}
    )
    controls._append(
        {
            "event": "completed",
            "call_id": "call",
            "attempt_id": "attempt",
            "cell": 0,
            "turn": 1,
            "run_id": "run",
            "usage_status": "known",
            "input_tokens": 12,
            "output_tokens": 3,
            "outcome": "accepted",
            "session_id": "session",
            "events_sha256": controls.sha(events_path),
            "dispatch_sha256": controls.sha(dispatch_path),
            "stdout_sha256": controls.sha(stdout_path),
        }
    )
    assert controls._usage_state()[0] == 74_272
    original_ledger = ledger_path.read_text()
    ledger_rows = [json.loads(line) for line in original_ledger.splitlines()]
    ledger_rows[2]["attempt_id"] = "other-attempt"
    ledger_rows[2]["event_sha256"] = controls.digest(
        {key: value for key, value in ledger_rows[2].items() if key != "event_sha256"}
    )
    ledger_path.write_text("\n".join(json.dumps(row) for row in ledger_rows) + "\n")
    with pytest.raises(controls.ControlError, match="identity"):
        controls._usage_state()
    ledger_path.write_text(original_ledger)
    events_path.write_text(events_path.read_text().replace('"input_tokens": 12', '"input_tokens": 13'))
    with pytest.raises(controls.ControlError, match="evidence"):
        controls._usage_state()
