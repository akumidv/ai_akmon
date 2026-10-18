"""Offline gates for a matching Codex scorer-format route."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("v3_codex_format_route", ROOT / "v3_codex_format_route.py")
assert SPEC and SPEC.loader
route = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route)


def test_format_only_prompt_and_blind_packet() -> None:
    manifest, packet, base, ids = route.old_route.validate_packet()
    assert route.format_prompt() == base + route.FORMAT_SUFFIX
    assert ids == ["E1", "E2", "E3", "E4"]
    assert manifest["scored_p3"] is False
    assert manifest["qualification_data"] is False
    assert b"gpt-6-astra" not in packet


def test_balance_and_qwen_route_are_bound() -> None:
    seal = route.verify_seal()
    assert seal["opening_codex_tokens"] == 273_286
    assert seal["qwen_format_outcome_sha256"] == route.sha(route.QWEN_FORMAT_OUTCOME)
    assert seal["terminal_qualification_ledger_sha256"] == route.sha(route.QUAL_LEDGER)
    assert seal["prompt_sha256"] == route.sha(route.PROMPT)


def test_default_deny_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        route.verify_approval(dispatch=True)
