"""Offline checks for the two unscored identity-bound scorer routes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))

import v3_id_bound_route_check as route  # noqa: E402


def test_plan_binds_same_prompt_and_packet_for_both_routes() -> None:
    prompt, packet = route.prompt_and_packet()
    candidate = route.plan()
    assert candidate["prompt_sha256"] == route.sha_bytes(prompt)
    assert candidate["packet_sha256"] == route.sha_bytes(packet)
    assert [row["route"] for row in candidate["calls"]] == ["qwen", "codex"]
    assert all(row["call_id"] not in route.qualification.schedule.prior_ids() for row in candidate["calls"])


def test_seal_binds_terminal_failure_and_parser() -> None:
    body = route.seal_body()
    assert body["opening_codex_tokens"] == 559_835
    assert body["scope"] == ["id_bound_route_checks"]
    assert body["retry_evidence_policy"] == "OBSERVED_NO_RETRY"
    assert body["predecessor_failure_sha256"] == route.sha(route.PACKET_ROOT / "failure.json")
    assert body["source_sha256"]["v3_scorer_id_binding.py"] == route.sha(HERE / "v3_scorer_id_binding.py")


def test_default_deny_approval_rejects_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seal = tmp_path / "seal.json"
    seal.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    preflight = tmp_path / "preflight.json"
    preflight.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(route, "SEAL", seal)
    monkeypatch.setattr(route, "APPROVAL", approval)
    monkeypatch.setattr(route, "PREFLIGHT", preflight)
    approval.write_text(json.dumps(route.approval_template()), encoding="utf-8")
    route.verify_approval(dispatch=False)
    with pytest.raises(route.RouteError, match="approval"):
        route.verify_approval(dispatch=True)


def test_preflight_requires_qwen_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route, "verify_seal", lambda: None)
    monkeypatch.setattr(route, "RUNTIME", tmp_path / "unused-runtime")
    monkeypatch.delenv("LITE_LLM_AUTH_TOKEN", raising=False)
    with pytest.raises(route.RouteError, match="Qwen credential"):
        route.preflight()


def test_dispatch_rejects_precreated_runtime_without_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(route, "RUNTIME", runtime)
    monkeypatch.setattr(route, "LEDGER", runtime / "route-events.jsonl")
    monkeypatch.setattr(route, "verify_seal", lambda: None)
    monkeypatch.setattr(route, "verify_approval", lambda **_kwargs: None)
    monkeypatch.setattr(route, "read", lambda _path: route.preflight_record())
    with pytest.raises(route.RouteError, match="runtime"):
        route.advance()
