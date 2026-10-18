"""Offline regressions for the distinct P3 source version-check successor."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(EXPERIMENT))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EXPERIMENT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ledger = _load("usage_ledger_version_successor_v3", "usage_ledger_version_successor_v3.py")
protocol = _load("lean_source_version_successor_v3", "lean_source_version_successor_v3.py")
runner = _load("v3_runner_version_successor", "v3_runner_version_successor.py")


def test_executable_banner_requires_the_exact_frozen_pin():
    assert runner._executable_version_matches("codex-cli 0.156.1\n", "")
    for stdout, stderr in (
        ("prefix codex-cli 0.156.1", ""),
        ("codex-cli 0.156.1 extra", ""),
        ("codex-cli 0.156.2", ""),
        ("codex-cli 0.156.1", "warning"),
    ):
        assert not runner._executable_version_matches(stdout, stderr)


@pytest.mark.parametrize("spelling", ["0.156.1", "codex-cli 0.156.1"])
def test_rollout_accepts_only_the_two_pinned_version_spellings(tmp_path: Path, spelling: str):
    root = tmp_path / "sessions"
    root.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    events = [
        {
            "type": "session_meta",
            "payload": {
                "id": "pinned-session",
                "cli_version": spelling,
                "cwd": str(scratch),
                "base_instructions": {"text": "frozen arm"},
            },
        },
        {"type": "turn_context", "payload": {"model": runner.MODEL, "effort": runner.EFFORT}},
        {"type": "turn_context", "payload": {"model": runner.MODEL, "effort": runner.EFFORT}},
    ]
    (root / "rollout.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    path, digest = runner._usage_from_rollout(
        root, "pinned-session", expected_turns=2, arm_text="frozen arm", scratch=scratch
    )
    assert path == root / "rollout.jsonl"
    assert digest == runner._sha(path.read_bytes())


@pytest.mark.parametrize("spelling", ["0.156.0", "0.156.2", "codex-cli 0.156.1 extra", "", None])
def test_rollout_rejects_every_other_version(tmp_path: Path, spelling: str | None):
    root = tmp_path / "sessions"
    root.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    events = [
        {
            "type": "session_meta",
            "payload": {
                "id": "pinned-session",
                "cli_version": spelling,
                "cwd": str(scratch),
                "base_instructions": {"text": "frozen arm"},
            },
        },
        {"type": "turn_context", "payload": {"model": runner.MODEL, "effort": runner.EFFORT}},
        {"type": "turn_context", "payload": {"model": runner.MODEL, "effort": runner.EFFORT}},
    ]
    (root / "rollout.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    with pytest.raises(runner.RunnerError, match="CLI version or scratch cwd"):
        runner._usage_from_rollout(root, "pinned-session", expected_turns=2, arm_text="frozen arm", scratch=scratch)


def test_prior_terminal_usage_is_bound_and_charged_in_new_ledger(tmp_path: Path):
    assert protocol.validated_prior_ledger() == protocol.PRIOR_LEDGER_SHA256
    path = tmp_path / "successor-ledger.jsonl"
    header = {
        "record_type": "p3_v3_ledger_header",
        "epoch_id": "synthetic",
        "proposal_sha256": "p",
        "approval_sha256": "a",
        "v3_prior_observed_tokens": protocol.PRIOR_OBSERVED_TOKENS,
        "v3_prior_ledger_sha256": protocol.PRIOR_LEDGER_SHA256,
    }
    path.write_text(json.dumps(header) + "\n", encoding="utf-8")
    assert ledger.summary(path)["v3_codex_tokens_used"] == 26_988
    quota = {
        "captured_utc": "stable",
        "source": "fixture",
        "source_version": "v1",
        "freshness_seconds": 0,
        "five_hour_used_percent": 1,
        "five_hour_reset_utc": "stable",
        "weekly_used_percent": 1,
        "weekly_reset_utc": "stable",
        "raw_redacted_sha256": "a" * 64,
    }
    with pytest.raises(ledger.LedgerError, match="token ceiling"):
        ledger.reserve(
            "codex", "technical", quota_snapshot=quota, path=path, token_reservation=ledger.CODEX_LIMIT - 26_988 + 1
        )
    assert len(path.read_text().splitlines()) == 1


def test_successor_approval_remains_default_deny():
    approval = json.loads(protocol.OPERATIONAL_APPROVAL.read_text(encoding="utf-8"))
    assert approval == protocol.operational_approval_template()
    assert approval["implementation_acceptance"]["owner_accepted"] is False
    assert approval["dispatch_allowed"] is False
    assert not protocol.OPERATIONAL_ACCEPTANCE_EVIDENCE.exists()
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_operational_approval()
