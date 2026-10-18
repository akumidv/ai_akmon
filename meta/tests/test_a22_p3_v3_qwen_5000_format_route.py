"""Offline checks for the new Qwen final-answer format route."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "experiments/a22-p3"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("v3_qwen_5000_format_route", HERE / "v3_qwen_5000_format_route.py")
assert SPEC and SPEC.loader
route = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route)


def test_prompt_only_adds_final_reply_format_and_preserves_thinking() -> None:
    manifest, packet, prompt, ids = route.packet_inputs()
    assert prompt == route.BASE_PROMPT.read_bytes() + route.FORMAT_SUFFIX
    assert manifest["scored_p3"] is False
    assert packet and ids == ["E1", "E2", "E3", "E4"]
    assert b"Keep private thinking separate from the final reply" in prompt
    _, overlay, meta = route.qwen_settings()
    assert overlay["modelProviders"]["openai"][0]["generationConfig"] == {
        "maxRetries": 0,
        "samplingParams": {"max_tokens": 5_000},
    }
    assert meta["thinking_override"] == "omitted; provider default retained"


def test_new_seal_binds_terminal_predecessor_and_format_prompt() -> None:
    route.prior_format_stop()
    body = route.seal_body()
    assert body["scope"] == ["qwen_5000_format_route_check"]
    assert body["prior_format_outcome_sha256"] == route.sha(route.PRIOR_FORMAT_RUNTIME / "outcome.json")
    assert body["prior_format_reply_sha256"] == route.sha(route.PRIOR_FORMAT_RUNTIME / "reply.tsv")
    assert body["prompt_sha256"] == route.sha(route.PROMPT)


def test_approval_defaults_to_denial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_existing_runtime_prevents_another_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route, "RUNTIME", tmp_path)
    monkeypatch.setattr(route, "verify_seal", dict)
    with pytest.raises(route.RouteError, match="already used"):
        route.preflight()
