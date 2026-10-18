from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "driver.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("a22_p3_driver", MODULE_PATH)
assert SPEC and SPEC.loader
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


@pytest.mark.parametrize("attempt_class", ["scored", "technical"])
def test_non_defect_subject_attempt_has_no_origin(attempt_class):
    driver.validate_attempt_class(attempt_class, None)


def test_defect_subject_attempt_requires_opaque_origin():
    origin = "0123456789abcdef0123456789abcdef"
    driver.validate_attempt_class("defect", origin)
    for invalid in (None, "run-1", "A" * 32, "0" * 31):
        with pytest.raises(ValueError, match="immutable 128-bit origin"):
            driver.validate_attempt_class("defect", invalid)


@pytest.mark.parametrize("attempt_class", [None, "route_check", "Scored"])
def test_new_subject_attempt_requires_supported_explicit_class(attempt_class):
    with pytest.raises(ValueError, match="explicitly set"):
        driver.validate_attempt_class(attempt_class, None)


def test_only_defect_attempt_can_name_origin():
    with pytest.raises(ValueError, match="only a defect"):
        driver.validate_attempt_class("scored", "0123456789abcdef0123456789abcdef")


def test_legacy_partial_attempt_without_registered_id_is_blocked():
    with pytest.raises(ValueError, match="legacy partial preflight recovery is blocked"):
        driver.registered_subject_attempt_id({"run_id": "preflight-A-strongest-01"})
    subject_id = "0123456789abcdef0123456789abcdef"
    assert driver.registered_subject_attempt_id({"subject_attempt_id": subject_id}) == subject_id


def test_turn_usage_requires_input_and_output_and_rejects_bool():
    assert driver._turn_usage({"last_token_usage": {"input_tokens": 8, "output_tokens": 2}}) == {
        "input_tokens": 8,
        "output_tokens": 2,
    }
    assert driver._turn_usage({"last_token_usage": {"input_tokens": 8, "output_tokens": 0}}) == {
        "input_tokens": 8,
        "output_tokens": 0,
    }
    for usage in (
        {"input_tokens": 8},
        {"input_tokens": True, "output_tokens": 2},
        {"input_tokens": 8, "output_tokens": False},
        {"input_tokens": 8, "output_tokens": -1},
    ):
        assert driver._turn_usage({"last_token_usage": usage}) is None


def test_each_turn_is_reserved_before_cli_and_completed_once(monkeypatch, tmp_path):
    order = []
    completions = []
    args = SimpleNamespace(run_id="run-1", scratch=tmp_path, model="pinned-model", effort="medium")
    monkeypatch.setattr(driver, "LEDGER_PATHS", (tmp_path / "ledger",) * 4)

    def reserve(subject_id, turn_id, **kwargs):
        order.append(("reserve", turn_id))
        return f"{len(completions) + 1:032x}"

    def dispatch(command, cwd, run_id, turn, *, artifact_prefix=None):
        order.append(("dispatch", turn))
        return ([{"type": "agent_message"}], f"raw-{turn}")

    def usage(args, events, **kwargs):
        return (
            {"input_tokens": 100 + kwargs["turn_index"], "output_tokens": 20},
            {
                "artifact_path": "usage.json",
                "artifact_sha256": "a" * 64,
                "request_id": "request",
                "session_id": "session",
                "model_id": "pinned-model",
            },
        )

    def complete(call_id, **kwargs):
        order.append(("complete", call_id))
        completions.append(kwargs)

    monkeypatch.setattr(driver.usage_ledger, "reserve_subject_call", reserve)
    monkeypatch.setattr(driver.usage_ledger, "complete_subject_call", complete)
    monkeypatch.setattr(driver, "run_codex", dispatch)
    monkeypatch.setattr(driver, "_persisted_usage_evidence", usage)

    for turn in (1, 2):
        driver.run_accounted_codex(
            args,
            ["codex"],
            subject_attempt_id="b" * 32,
            turn_id=f"turn-{turn}",
            turn_index=turn - 1,
            expected_turns=turn,
            input_caps=(40_000,) * turn,
            turn=turn,
            arm_text="arm",
        )

    assert order == [
        ("reserve", "turn-1"),
        ("dispatch", 1),
        ("complete", f"{1:032x}"),
        ("reserve", "turn-2"),
        ("dispatch", 2),
        ("complete", f"{2:032x}"),
    ]
    assert [completion["actual_usage"] for completion in completions] == [
        {"input_tokens": 100, "output_tokens": 20},
        {"input_tokens": 101, "output_tokens": 20},
    ]
    assert all(completion["outcome"] == "accepted" for completion in completions)


def test_unverifiable_usage_closes_call_as_failed_and_stops_dispatch(monkeypatch, tmp_path):
    completions = []
    args = SimpleNamespace(run_id="run-1", scratch=tmp_path, model="pinned-model", effort="medium")
    monkeypatch.setattr(driver, "LEDGER_PATHS", (tmp_path / "ledger",) * 4)
    monkeypatch.setattr(driver.usage_ledger, "reserve_subject_call", lambda *a, **k: "c" * 32)
    monkeypatch.setattr(
        driver.usage_ledger, "complete_subject_call", lambda call_id, **kwargs: completions.append(kwargs)
    )
    monkeypatch.setattr(driver, "run_codex", lambda *a, **k: ([{"type": "agent_message"}], "raw"))

    def missing_usage(*_args, **_kwargs):
        raise ValueError("rollout lacks token usage")

    monkeypatch.setattr(driver, "_persisted_usage_evidence", missing_usage)
    with pytest.raises(ValueError, match="lacks token usage"):
        driver.run_accounted_codex(
            args,
            ["codex"],
            subject_attempt_id="b" * 32,
            turn_id="turn-1",
            turn_index=0,
            expected_turns=1,
            input_caps=(40_000,),
            turn=1,
            arm_text="arm",
        )

    assert completions == [{"outcome": "failed", "failure_code": "missing_usage", "paths": driver.LEDGER_PATHS}]
