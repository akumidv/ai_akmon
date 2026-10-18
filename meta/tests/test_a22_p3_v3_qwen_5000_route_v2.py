"""Offline gates for the separately sealed Qwen route after a DNS stop."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments/a22-p3"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("v3_qwen_5000_route_v2", HERE / "v3_qwen_5000_route_v2.py")
assert SPEC and SPEC.loader
route = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route)


def test_seal_binds_terminal_predecessor_and_unscored_packet() -> None:
    body = route.seal_body()
    assert body["old_qualification_ledger_sha256"] == route.sha(route.OLD_LEDGER)
    assert body["network_stop_outcome_sha256"] == route.sha(route.PRIOR_RUNTIME / "outcome.json")
    assert body["network_stop_stdout_sha256"] == route.sha(route.PRIOR_RUNTIME / "stdout.raw")
    assert body["prior_codex_v3_charge"] == 273_286
    assert body["output_setting_and_observed_limit"] == 5_000
    assert body["scope"] == ["qwen_5000_route_check"]
    manifest, packet, prompt, ids = route.packet_inputs()
    assert manifest["scored_p3"] is False
    assert manifest["qualification_data"] is False
    assert packet and prompt and ids == ["E1", "E2", "E3", "E4"]


def test_prior_dns_stop_is_terminal_and_has_unknown_usage() -> None:
    route.prior_network_stop()
    outcome = route.read(route.PRIOR_RUNTIME / "outcome.json")
    assert outcome["outcome"] == "failed"
    assert outcome["usage"] is None
    assert outcome["retry_authorized"] is False


def test_owner_approval_defaults_to_denial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seal = tmp_path / "seal.json"
    seal.write_text("{}\n", encoding="utf-8")
    preflight = tmp_path / "preflight.json"
    preflight.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    monkeypatch.setattr(route, "SEAL", seal)
    monkeypatch.setattr(route, "PREFLIGHT", preflight)
    monkeypatch.setattr(route, "APPROVAL", approval)
    approval.write_text(json.dumps(route.approval_template()), encoding="utf-8")
    with pytest.raises(route.RouteError, match="approval"):
        route.verify_approval()


def test_qwen_overlay_retains_default_thinking_and_changes_only_output() -> None:
    _, overlay, meta = route.qwen_settings()
    config = overlay["modelProviders"]["openai"][0]["generationConfig"]
    assert config == {"maxRetries": 0, "samplingParams": {"max_tokens": 5_000}}
    assert meta["thinking_override"] == "omitted; provider default retained"
    assert meta["maxRetries"] == 0


def test_existing_runtime_prevents_a_second_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route, "RUNTIME", tmp_path)
    monkeypatch.setattr(route, "verify_seal", dict)
    with pytest.raises(route.RouteError, match="already used"):
        route.preflight()
