"""Offline invariants for the current-CLI unscored Codex scorer route."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "v3_codex_scorer_route_consent_v2_test", ROOT / "v3_codex_scorer_route_consent_v2.py"
)
assert spec is not None and spec.loader is not None
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


def test_default_deny_and_blinded_packet() -> None:
    preflight = route.offline_preflight()
    assert preflight["dispatch_allowed"] is False
    assert preflight["provider_calls"] == 0
    assert route.approval_template()["authorized_phases"] == []
    manifest, packet, prompt, ids = route.old_route.validate_packet()
    assert ids == ["E1", "E2", "E3", "E4"]
    assert manifest["scored_p3"] is False
    assert manifest["qualification_data"] is False
    assert b"gpt-6-astra" not in packet
    assert b"qualification" not in packet
    assert prompt == (ROOT / "scoring" / "scorer-prompt.txt").read_bytes()


def test_dispatch_gate_rejects_default_deny() -> None:
    with pytest.raises(route.RouteError, match="exact successor route approval is absent"):
        route.verify_approval(dispatch=True)


def test_control_balance_is_complete() -> None:
    seal = route.verify_seal()
    assert seal["opening_codex_tokens"] == 202_220
    assert seal["cli_version"] == "0.162.1"
    assert seal["scope"] == ["codex_scorer_route_check"]


def test_nonaccepting_user_text_cannot_authorize_dispatch(tmp_path: Path, monkeypatch) -> None:
    evidence = tmp_path / "acceptance.json"
    direction = route.read(route.ACCEPTANCE)
    direction["visible_user_text"] = "I refuse this route check."
    evidence.write_text(json.dumps(direction))
    monkeypatch.setattr(route, "ACCEPTANCE", evidence)
    candidate = route.approval_template()
    candidate.update(
        {
            "owner_accepted": True,
            "dispatch_allowed": True,
            "authorized_phases": ["codex_scorer_route_check"],
            "named_stop_operator": "owner (current chat session)",
            "acceptance_evidence_sha256": route.sha(evidence),
            "preflight_report_sha256": route.sha(route.PREFLIGHT),
        }
    )
    original = route.read
    monkeypatch.setattr(route, "read", lambda path: candidate if path == route.APPROVAL else original(path))
    with pytest.raises(route.RouteError, match="owner direction provenance differs"):
        route.verify_approval(dispatch=True)


def test_owner_direction_is_correlated_to_local_chat_record() -> None:
    direction = route.verify_owner_direction()
    assert direction["accepted_predecessor_seal_sha256"] == route.sha(
        ROOT / "runs" / "v3-codex-scorer-route-successor-seal-v1.json"
    )
