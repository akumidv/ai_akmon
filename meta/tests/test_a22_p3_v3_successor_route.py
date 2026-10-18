"""Offline checks for the V3 successor route packet and terminal route ledger."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packet = _load("v3_successor_route_packet_test", "v3_successor_route_packet.py")
route = _load("v3_successor_route_check_test", "v3_successor_route_check.py")


def test_successor_packet_is_blind_and_bound_to_verified_source() -> None:
    manifest, visible, prompt, ids = route.validate_packet()
    assert manifest["source_record_sha256"] == route.sha(packet.RECORD)
    assert manifest["source_ledger_sha256"] == route.sha(packet.LEDGER)
    assert manifest["scored_p3"] is False
    assert manifest["qualification_data"] is False
    assert ids == ["E1", "E2", "E3", "E4"]
    assert packet.RUN_ID.encode() not in visible
    assert b"gpt-6-astra" not in visible
    assert b"strongest" not in visible
    assert b"qualification" not in visible
    assert prompt == packet.PROMPT.read_bytes()


def test_phase_approval_template_denies_dispatch(monkeypatch) -> None:
    candidate = route.approval_template()
    assert candidate["authorized_phases"] == []
    original = route._read
    monkeypatch.setattr(route, "_read", lambda path: candidate if path == route.APPROVAL else original(path))
    with pytest.raises(route.RouteError, match="not accepted"):
        route.validate_approval(dispatch=True)


def test_acceptance_evidence_requires_sha256_digest(monkeypatch) -> None:
    candidate = route.approval_template()
    candidate.update(
        {
            "owner_accepted": True,
            "dispatch_allowed": True,
            "authorized_phases": ["route_checks"],
            "named_stop_operator": "owner (current chat session)",
            "acceptance_evidence_sha256": "not-a-digest",
            "preflight_report_sha256": route.sha(route.PREFLIGHT),
        }
    )
    original = route._read
    monkeypatch.setattr(route, "_read", lambda path: candidate if path == route.APPROVAL else original(path))
    with pytest.raises(route.RouteError, match="not accepted"):
        route.validate_approval(dispatch=True)


def test_denial_cannot_be_used_as_acceptance(tmp_path: Path, monkeypatch) -> None:
    evidence = tmp_path / "acceptance.json"
    evidence.write_text(
        json.dumps(
            {
                "record_type": "p3_v3_route_owner_acceptance",
                "accepted_seal_sha256": route.sha(route.SEAL),
                "scope": ["route_checks"],
                "stop_operator": "owner (current chat session)",
                "request_message_id": "request",
                "user_message_id": "denial",
                "request_text": route.expected_owner_reply(),
                "user_text": "I refuse route_checks.",
            }
        )
    )
    monkeypatch.setattr(route, "ACCEPTANCE_EVIDENCE", evidence)
    candidate = route.approval_template()
    candidate.update(
        {
            "owner_accepted": True,
            "dispatch_allowed": True,
            "authorized_phases": ["route_checks"],
            "named_stop_operator": "owner (current chat session)",
            "acceptance_evidence_sha256": route.sha(evidence),
            "preflight_report_sha256": route.sha(route.PREFLIGHT),
        }
    )
    original = route._read
    monkeypatch.setattr(route, "_read", lambda path: candidate if path == route.APPROVAL else original(path))
    with pytest.raises(route.RouteError, match="stale or malformed"):
        route.validate_approval(dispatch=True)


def test_route_ledger_is_append_only_and_failed_route_blocks_next(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(route, "RUNTIME_ROOT", tmp_path / "runtime")
    manifest = json.loads((route.PACKET_ROOT / "evaluator" / "manifest.json").read_text())
    approval = {"operational_seal_sha256": route.sha(route.SEAL)}
    first = route._reserve("codex", manifest, approval)
    with pytest.raises(route.RouteError, match="already attempted"):
        route._reserve("codex", manifest, approval)
    route._finish("codex", first, status="failed", usage={"input_tokens": 3, "output_tokens": 2})
    state = route._runtime_state()
    assert state["codex_tokens"] == route.PRIOR_OBSERVED_CODEX_TOKENS + 5
    with pytest.raises(route.RouteError, match="prior route failed"):
        route._reserve("qwen", manifest, approval)
    ledger = route.RUNTIME_ROOT / "route-events.jsonl"
    rows = ledger.read_text().splitlines()
    assert len(rows) == 3
    assert json.loads(rows[-1])["status"] == "failed"


def test_unknown_codex_usage_locks_second_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(route, "RUNTIME_ROOT", tmp_path / "runtime")
    manifest = json.loads((route.PACKET_ROOT / "evaluator" / "manifest.json").read_text())
    approval = {"operational_seal_sha256": route.sha(route.SEAL)}
    first = route._reserve("codex", manifest, approval)
    route._finish("codex", first, status="failed", usage=None)
    assert route._runtime_state()["codex_usage_unknown"] is True
    with pytest.raises(route.RouteError):
        route._reserve("qwen", manifest, approval)


def test_existing_shared_runtime_is_rejected(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "runtime"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    monkeypatch.setattr(route, "RUNTIME_ROOT", root)
    with pytest.raises(route.RouteError, match="private directory"):
        route._ensure_runtime()
    root.chmod(0o700)
    route._ensure_runtime()
