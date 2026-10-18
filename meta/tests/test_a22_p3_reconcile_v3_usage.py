"""Synthetic regression checks for the one historical V3 usage exception."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("reconcile_v3_usage_test", ROOT / "reconcile_v3_usage.py")
assert SPEC is not None and SPEC.loader is not None
reconcile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reconcile)


def _envelope():
    usage = {"input_tokens": 7737, "output_tokens": 29, "total_tokens": 7766}
    return {
        "attempt": {
            "run_id": reconcile.RUN_ID,
            "subject_attempt_id": reconcile.ATTEMPT_ID,
            "attempt_class": "technical",
            "case": "P3-01",
            "arm": "A",
            "tier": "strongest",
            "repeat": 1,
        },
        "dispatch": {
            "returncode": 0,
            "status": "accepted",
            "cwd": str(reconcile.RUNTIME / "scratch"),
            "command": ["codex", "exec", "--json"],
        },
        "events": [
            {"type": "thread.started", "thread_id": reconcile.SESSION_ID},
            {"type": "turn.completed", "usage": usage},
        ],
        "rollout": [
            {
                "type": "session_meta",
                "payload": {
                    "session_id": reconcile.SESSION_ID,
                    "cwd": str(reconcile.RUNTIME / "scratch"),
                },
            },
            {"type": "turn_context", "payload": {"turn_id": reconcile.TURN_ID}},
            {
                "type": "token_usage_record",
                "payload": {
                    "session_id": reconcile.SESSION_ID,
                    "turn_id": reconcile.TURN_ID,
                    "usage": usage,
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": usage},
                },
            },
        ],
        "ledger_events": [
            {
                "event": "reserved",
                "provider_call_id": reconcile.CALL_ID,
                "subject_attempt_id": reconcile.ATTEMPT_ID,
                "turn_id": "turn-1",
            },
            {
                "event": "completed",
                "provider_call_id": reconcile.CALL_ID,
                "usage_status": "UNKNOWN_USAGE",
                "input_tokens": None,
                "output_tokens": None,
                "outcome": "failed",
            },
        ],
        "rollout_count": 1,
    }


def test_exact_single_envelope_is_admissible_only_as_historical_debit() -> None:
    reconcile.validate_envelope(**_envelope())
    assert reconcile.DEBIT == 7766


@pytest.mark.parametrize("mutation", ["second_call", "second_usage", "second_rollout", "wrong_turn", "known_ledger"])
def test_ambiguous_or_reclassified_envelope_is_rejected(mutation: str) -> None:
    envelope = _envelope()
    if mutation == "second_call":
        envelope["ledger_events"].append({"event": "reserved", "provider_call_id": "other"})
    elif mutation == "second_usage":
        envelope["events"].append(envelope["events"][-1].copy())
    elif mutation == "second_rollout":
        envelope["rollout_count"] = 2
    elif mutation == "wrong_turn":
        envelope["rollout"][1]["payload"]["turn_id"] = "other"
    else:
        envelope["ledger_events"][1]["usage_status"] = "known"
    with pytest.raises(reconcile.ReconciliationError):
        reconcile.validate_envelope(**envelope)
