"""Synthetic mechanics checks for the V3 Codex runner and linked ledger calls."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

EXP = Path(__file__).parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(EXP))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EXP / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ledger = _load("usage_ledger_v3", "usage_ledger_v3.py")
_load("dispatch_v3", "dispatch_v3.py")
_load("quota_adapter_v3", "quota_adapter_v3.py")
runner = _load("a22_p3_v3_runner", "v3_runner.py")


def _quota():
    return {
        "captured_utc": "2026-10-15T00:00:00Z",
        "source": "fixture",
        "source_version": "v1",
        "freshness_seconds": 0,
        "five_hour_used_percent": 2,
        "five_hour_reset_utc": "2026-10-15T05:00:00Z",
        "weekly_used_percent": 3,
        "weekly_reset_utc": "2026-10-20T00:00:00Z",
        "raw_redacted_sha256": "a" * 64,
    }


def _accepted_gate(tmp_path: Path):
    """Build a source-bound synthetic approval and ledger for runner integration checks."""
    plan, packet = ledger.PLAN, ledger.PACKET_SEAL
    seal_path = tmp_path / "seal-v3.json"
    sources = {
        "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md": ledger.sha256(plan),
        "usage_ledger_v3.py": ledger.sha256(ledger.HERE / "usage_ledger_v3.py"),
        "dispatch_v3.py": ledger.sha256(ledger.HERE / "dispatch_v3.py"),
        "v3_runner.py": ledger.sha256(ledger.HERE / "v3_runner.py"),
        "quota_adapter_v3.py": ledger.sha256(ledger.HERE / "quota_adapter_v3.py"),
        "preflight_v3.py": ledger.sha256(ledger.HERE / "preflight_v3.py"),
        "source_v3.py": ledger.sha256(ledger.HERE / "source_v3.py"),
    }
    seal_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "record_type": "p3_v3_plan_seal",
                "proposal_sha256": ledger.sha256(plan),
                "packet_seal_sha256": ledger.sha256(packet),
                "source_sha256": sources,
                "settings": {
                    "codex_cli": "0.156.1",
                    "codex_model": "gpt-6-astra",
                    "qwen_cli": "0.24.7",
                    "qwen_model": "qwen3.8-27b",
                    "qwen_thinking": "default",
                    "codex_epoch_limit_tokens": 5_000_000,
                    "five_hour_stop_percent": 80,
                    "weekly_stop_percent": 90,
                    "retry_evidence_policy": "OBSERVED_NO_RETRY",
                },
            }
        ),
        encoding="utf-8",
    )
    seal_hash = ledger.sha256(seal_path)
    approval = tmp_path / "accepted-approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema": 1,
                "record_type": "p3_v3_owner_approval",
                "proposal_sha256": ledger.sha256(plan),
                "v3_seal_sha256": seal_hash,
                "owner_accepted": True,
                "new_epoch_budget_accepted": True,
                "v2_usage_exclusion_accepted": True,
                "subscription_thresholds_accepted": True,
                "qwen_uncapped_policy_accepted": True,
                "observed_no_retry_accepted": True,
                "schedule_accepted": True,
                "named_stop_operator": "Synthetic Owner",
                "authorized_phases": ["technical_source"],
                "acceptance_evidence": {
                    "proposal_sha256": ledger.sha256(plan),
                    "v3_seal_sha256": seal_hash,
                    "transcript_sha256": "b" * 64,
                    "exact_quote": "Synthetic fixture only.",
                },
                "preflight_status": "PASSED",
                "dispatch_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.jsonl"
    ledger.initialize(ledger_path, plan=plan, packet_seal=packet, approval=approval, seal_path=seal_path)
    return approval, seal_path, ledger_path


def test_codex_stream_extracts_two_turn_usage_and_rejects_tools():
    events = runner.parse_events(
        "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "session-1"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "CHECK: E2"}}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 120, "output_tokens": 8}}),
            ]
        )
    )
    assert runner.thread_id(events) == "session-1"
    assert runner.assistant_reply(events) == "CHECK: E2"
    assert runner.extract_usage(events) == {"input_tokens": 120, "output_tokens": 8}
    assert runner._second_prompt(
        {"subject": {"menu": [{"id": "E2", "output": "second"}], "no_item_reply": "fixed"}}, "CHECK: E2"
    ) == ("E2", {"id": "E2", "output": "second"}, "second")
    assert runner._second_prompt({"subject": {"menu": [], "no_item_reply": "fixed"}}, "done") == (None, None, "fixed")
    assert not runner.has_tool_use(events)
    assert runner.has_tool_use([{"payload": {"type": "mcp_tool_call"}}])
    assert runner.has_tool_use([{"tool_call_id": "x"}])


def test_usage_accepts_only_one_direct_completed_turn_record():
    usage = {"input_tokens": 120, "output_tokens": 8}
    direct = {"type": "turn.completed", "usage": usage}
    assert runner.extract_usage([direct]) == usage
    assert (
        runner.extract_usage(
            [direct, {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 999, "output_tokens": 999}}}]
        )
        == usage
    )
    with pytest.raises(runner.RunnerError, match="exactly one"):
        runner.extract_usage([direct, direct])
    with pytest.raises(runner.RunnerError, match="exactly one"):
        runner.extract_usage([{"type": "token_count", "info": {"last_token_usage": usage}}])
    with pytest.raises(runner.RunnerError, match="exactly one"):
        runner.extract_usage([{"type": "turn.completed", "usage": {"input_tokens": True, "output_tokens": 0}}])


def test_both_turn_commands_keep_read_only_and_ignore_user_config(tmp_path: Path):
    first = runner._command("/tmp/codex", tmp_path, runner.MODEL, "first prompt")
    resumed = runner._command("/tmp/codex", tmp_path, runner.MODEL, "second prompt", resume="synthetic-session")
    for command in (first, resumed):
        assert "-s" in command and command[command.index("-s") + 1] == "read-only"
        assert "--ignore-user-config" in command
        assert "--ignore-rules" in command
        assert "-C" in command and command[command.index("-C") + 1] == str(tmp_path)
        assert f'model_instructions_file="{runner.ARM}"' in command
    assert "resume" in resumed and "synthetic-session" in resumed
    assert "resume" not in first


def test_linked_reservation_completion_preserves_subject_and_turn_binding(tmp_path: Path):
    plan, packet, approval = (tmp_path / "plan", tmp_path / "packet", tmp_path / "approval")
    plan.write_text("plan\n", encoding="utf-8")
    packet.write_text("{}\n", encoding="utf-8")
    approval.write_text(
        json.dumps(
            {
                "schema": 1,
                "record_type": "p3_v3_owner_approval",
                "owner_accepted": False,
                "dispatch_allowed": False,
                "authorized_phases": [],
                "preflight_status": "NOT_RUN",
            }
        ),
        encoding="utf-8",
    )
    path = tmp_path / "ledger.jsonl"
    ledger.initialize(path, plan=plan, packet_seal=packet, approval=approval)
    subject_id = "b" * 32
    call_id = ledger.reserve(
        "codex", "technical", quota_snapshot=_quota(), path=path, subject_attempt_id=subject_id, turn_id="turn-1"
    )
    ledger.complete(
        call_id, outcome="accepted", usage={"input_tokens": 20, "output_tokens": 2}, quota_snapshot=_quota(), path=path
    )
    _, events = ledger._read(path)
    completion = next(event for event in events if event["event"] == "completed")
    assert completion["subject_attempt_id"] == subject_id
    assert completion["turn_id"] == "turn-1"


def test_default_deny_blocks_runner_before_provider_lookup(tmp_path: Path):
    calls = []
    with pytest.raises(ledger.LedgerError):
        runner.run_technical_source(
            output_dir=tmp_path / "output",
            scratch=tmp_path / "scratch",
            rollout_root=tmp_path / "rollouts",
            approval=EXP / "runs" / "owner-approval-v3.json",
            seal_path=EXP / "seal-v3.json",
            plan=EXP / "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md",
            packet_seal=EXP / "seal.json",
            ledger_path=tmp_path / "missing-ledger.jsonl",
        )
    assert calls == []


def test_invoke_does_not_poll_quota_during_call(tmp_path: Path):
    class FakeProcess:
        def __init__(self):
            self.returncode = None
            self.terminated = False
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("codex", timeout)
            self.returncode = -15
            return "partial output", "terminated"

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.returncode = -9

    process = FakeProcess()
    artifacts = tmp_path / "attempt" / "turn1"
    process.calls = 1
    process.returncode = 0
    process.communicate = lambda timeout=None: (
        '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":0}}',
        "",
    )
    events, _ = runner._invoke(
        ["codex", "exec"],
        cwd=tmp_path,
        codex_home=tmp_path / "home",
        tmp=tmp_path / "tmp",
        artifact_base=artifacts,
        popen_factory=lambda *args, **kwargs: process,
    )
    assert runner.extract_usage(events) == {"input_tokens": 1, "output_tokens": 0}
    assert process.terminated is False
    assert process.calls == 1
    assert json.loads(Path(f"{artifacts}.dispatch.json").read_text())["status"] == "accepted"


def test_production_runner_rejects_injected_executor_and_quota_reader(tmp_path: Path, monkeypatch):
    approval, seal_path, ledger_path = _accepted_gate(tmp_path)
    output = tmp_path / "output"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    process_calls = []
    raw_events = "\n".join(
        (
            json.dumps({"type": "thread.started", "thread_id": "synthetic-session"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "A synthetic reply without token usage."},
                }
            ),
        )
    )

    def fake_executor(*args, **kwargs):
        process_calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, raw_events, "")

    with pytest.raises(TypeError, match="executor"):
        runner.run_technical_source(
            output_dir=output,
            scratch=scratch,
            rollout_root=output / "runtime" / "codex-home" / "sessions",
            executor=fake_executor,
            quota_reader=_quota,
            ledger_path=ledger_path,
            approval=approval,
            seal_path=seal_path,
        )

    assert process_calls == []
    assert not output.exists()
