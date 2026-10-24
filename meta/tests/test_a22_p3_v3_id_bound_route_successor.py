"""Offline integrity checks for the distinct identity-bound route successor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(HERE))

import v3_id_bound_route_successor as route  # noqa: E402


def test_successor_plan_excludes_failed_route_ids() -> None:
    failed = route.read(route.FAILED_PLAN)
    candidate = route.plan()
    assert [row["route"] for row in candidate["calls"]] == ["qwen", "codex"]
    assert {row["call_id"] for row in candidate["calls"]}.isdisjoint(row["call_id"] for row in failed["calls"])
    assert Path("/tmp/a22-p3-v3-id-bound-route-runtime") != route.RUNTIME
    assert all(path != route.FAILED_OUTCOME for path in route.OUTCOMES.values())


def test_seal_binds_terminal_failed_predecessor() -> None:
    failed = route.check_failed_predecessor()
    body = route.seal_body()
    assert body["failed_predecessor_sha256"] == failed
    assert body["gateway_preflight"] == "DNS and verified TLS handshake only; no API request"
    assert body["source_sha256"]["v3_id_bound_route_successor.py"] == route.sha(HERE / "v3_id_bound_route_successor.py")


def test_tampered_predecessor_blocks_successor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "route-events.jsonl"
    ledger.write_text(route.FAILED_LEDGER.read_text().replace('"status": "failed"', '"status": "passed_unscored"'))
    monkeypatch.setattr(route, "FAILED_LEDGER", ledger)
    with pytest.raises(route.RouteError, match="terminal DNS predecessor"):
        route.check_failed_predecessor()


def test_failed_tls_gate_blocks_qwen_before_reservation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route, "RUNTIME", tmp_path)
    monkeypatch.setattr(route, "LEDGER", tmp_path / "route-events.jsonl")
    monkeypatch.setenv("LITE_LLM_AUTH_TOKEN", "test-placeholder")

    def failed_gate() -> None:
        raise route.RouteError("Qwen gateway DNS/TLS probe failed")

    monkeypatch.setattr(route, "check_gateway_tls", failed_gate)
    with pytest.raises(route.RouteError, match="DNS/TLS"):
        route._one_call(route.plan()["calls"][0])
    assert not route.LEDGER.exists()
    assert not any(tmp_path.iterdir())
