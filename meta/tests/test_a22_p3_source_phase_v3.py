"""Source-only V3 approval and offline preflight remain separate and default-deny."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

EXPERIMENT = Path(__file__).resolve().parents[1] / "experiments" / "a22-p3"
sys.path.insert(0, str(EXPERIMENT))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ledger = _load("usage_ledger_v3", EXPERIMENT / "usage_ledger_v3.py")
source = _load("source_v3", EXPERIMENT / "source_v3.py")
source_phase = _load("source_phase_v3", EXPERIMENT / "source_phase_v3.py")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    plan = tmp_path / "plan.md"
    plan.write_text("q1461 remains terminal; the source phase is technical only.\n", encoding="utf-8")
    packet = EXPERIMENT / "seal.json"
    base_seal = tmp_path / "operative-v3-seal.json"
    base_sources = {
        "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md": source_phase.sha256(plan),
        **{name: source_phase.sha256(EXPERIMENT / name) for name in source_phase.BASE_SOURCE_NAMES
           if name != "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md"},
    }
    _write_json(base_seal, {
        "schema": 1, "record_type": "p3_v3_plan_seal", "proposal_sha256": source_phase.sha256(plan),
        "packet_seal_sha256": source_phase.sha256(packet), "source_sha256": base_sources,
        "settings": {
            "codex_cli": "0.156.1", "codex_model": "gpt-6-astra", "qwen_cli": "0.24.7",
            "qwen_model": "qwen3.8-27b", "qwen_thinking": "default",
            "codex_epoch_limit_tokens": ledger.CODEX_LIMIT,
            "five_hour_stop_percent": ledger.FIVE_HOUR_STOP_PERCENT,
            "weekly_stop_percent": ledger.WEEKLY_STOP_PERCENT,
            "retry_evidence_policy": "OBSERVED_NO_RETRY",
        },
    })
    monkeypatch.setattr(source_phase, "OPERATIVE_V3_SEAL_SHA256", source_phase.sha256(base_seal))
    amendment_proposal = tmp_path / "amendment.md"
    exact_quote = source_phase._owner_acceptance_quote(source_phase.AMENDMENT_PROPOSAL)
    amendment_proposal.write_text(f"> {exact_quote}\n", encoding="utf-8")
    amendment_seal = tmp_path / "amendment-seal.json"
    approval = tmp_path / "source-approval.json"
    campaign_approval = tmp_path / "campaign-approval.json"
    _write_json(campaign_approval, {
        "owner_accepted": False, "dispatch_allowed": False, "authorized_phases": [],
    })
    _write_json(amendment_seal, source_phase.expected_amendment_seal(
        plan=plan, packet_seal=packet, base_seal=base_seal,
        amendment_proposal=amendment_proposal))
    record = source_phase.approval_template(
        plan=plan, base_seal=base_seal, amendment_seal=amendment_seal,
        amendment_proposal=amendment_proposal)
    for key in (
            "owner_accepted", "new_epoch_budget_accepted", "v2_usage_exclusion_accepted",
            "subscription_thresholds_accepted", "observed_no_retry_accepted", "source_conditions_accepted"):
        record[key] = True
    record["named_stop_operator"] = "Operator A"
    record["authorized_phases"] = [source_phase.PHASE]
    transcript = tmp_path / "owner-acceptance-transcript.json"
    exact_quote = source_phase._owner_acceptance_quote(amendment_proposal)
    transcript_bytes = (json.dumps({
        "record_type": "p3_v3_owner_acceptance_transcript", "session_id": "synthetic-session",
        "message_id": "synthetic-message", "owner": "Owner A", "text": exact_quote,
    }, sort_keys=True, indent=2) + "\n").encode()
    transcript.write_bytes(transcript_bytes)
    record["acceptance_evidence"] = {
        "exact_quote": exact_quote,
        "transcript_path": str(transcript),
        "transcript_sha256": source_phase.hashlib.sha256(transcript_bytes).hexdigest(),
        "amendment_proposal_sha256": record["amendment_proposal_sha256"],
        "proposal_sha256": record["proposal_sha256"],
        "operative_v3_seal_sha256": record["operative_v3_seal_sha256"],
        "amendment_seal_sha256": record["amendment_seal_sha256"],
    }
    _write_json(approval, record)
    monkeypatch.setattr(source_phase, "_validate_v2_history", lambda: True)
    return {
        "plan": plan, "packet": packet, "base_seal": base_seal,
        "amendment_proposal": amendment_proposal, "amendment_seal": amendment_seal,
        "approval": approval, "campaign_approval": campaign_approval,
    }


def _quota(**changes: Any) -> dict[str, Any]:
    return {
        "captured_utc": "2030-01-01T00:00:00Z", "source": "synthetic-source",
        "source_version": "fixture-v1", "freshness_seconds": 0,
        "five_hour_used_percent": 1, "five_hour_reset_utc": "2030-01-01T05:00:00Z",
        "weekly_used_percent": 1, "weekly_reset_utc": "2030-01-08T00:00:00Z",
        "raw_redacted_sha256": "a" * 64, **changes,
    }


def test_accepted_v2_snapshot_is_bound_by_path_and_exact_hashes() -> None:
    binding = source_phase._v2_history_binding()
    assert binding["path"] == str(source_phase.V2_HISTORY_ROOT.resolve())
    assert binding["files"] == source_phase.V2_HISTORY_SHA256
    assert binding["storage_assurance"] == "hash-matching preserved snapshot; storage is not immutable"
    assert source_phase._validate_v2_history()


def _preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], dict[str, Path]]:
    paths = _bundle(tmp_path, monkeypatch)
    report = source_phase.run_source_preflight(
        runtime_root=tmp_path / "runtime", approval_path=paths["approval"],
        seal_path=paths["amendment_seal"], plan=paths["plan"], packet_seal=paths["packet"],
        base_seal=paths["base_seal"], amendment_proposal=paths["amendment_proposal"],
        campaign_approval=paths["campaign_approval"])
    return report, paths


def test_source_approval_accepts_only_technical_source_and_binds_both_seals(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _bundle(tmp_path, monkeypatch)
    approval = source_phase.validate_source_approval(
        approval_path=paths["approval"], seal_path=paths["amendment_seal"],
        plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
        amendment_proposal=paths["amendment_proposal"])
    assert approval["authorized_phases"] == ["technical_source"]
    assert approval["operative_v3_seal_sha256"] == source_phase.sha256(paths["base_seal"])

    approval["authorized_phases"] = ["technical_source", "route_checks"]
    _write_json(paths["approval"], approval)
    with pytest.raises(source_phase.SourcePhaseError, match="only technical_source"):
        source_phase.validate_source_approval(
            approval_path=paths["approval"], seal_path=paths["amendment_seal"],
            plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
            amendment_proposal=paths["amendment_proposal"])


def test_default_deny_source_approval_cannot_pass_validation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _bundle(tmp_path, monkeypatch)
    approval = source_phase.approval_template(
        plan=paths["plan"], base_seal=paths["base_seal"],
        amendment_seal=paths["amendment_seal"], amendment_proposal=paths["amendment_proposal"])
    _write_json(paths["approval"], approval)
    with pytest.raises(source_phase.SourcePhaseError, match="default-deny"):
        source_phase.validate_source_approval(
            approval_path=paths["approval"], seal_path=paths["amendment_seal"],
            plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
            amendment_proposal=paths["amendment_proposal"])


def test_fabricated_acceptance_quote_or_transcript_hash_is_rejected(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _bundle(tmp_path, monkeypatch)
    record = json.loads(paths["approval"].read_text(encoding="utf-8"))
    record["acceptance_evidence"]["exact_quote"] = "I authorize only technical source."
    _write_json(paths["approval"], record)
    with pytest.raises(source_phase.SourcePhaseError, match="exact amended decision"):
        source_phase.validate_source_approval(
            approval_path=paths["approval"], seal_path=paths["amendment_seal"],
            plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
            amendment_proposal=paths["amendment_proposal"])

    second = tmp_path / "second"
    second.mkdir()
    paths = _bundle(second, monkeypatch)
    record = json.loads(paths["approval"].read_text(encoding="utf-8"))
    record["acceptance_evidence"]["transcript_sha256"] = "f" * 64
    _write_json(paths["approval"], record)
    with pytest.raises(source_phase.SourcePhaseError, match="malformed or bound"):
        source_phase.validate_source_approval(
            approval_path=paths["approval"], seal_path=paths["amendment_seal"],
            plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
            amendment_proposal=paths["amendment_proposal"])


def test_preflight_is_offline_passes_source_checks_and_never_authorizes_launch(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report, _ = _preflight(tmp_path, monkeypatch)
    assert report["status"] == "PASSED_SOURCE_PHASE_PREFLIGHT"
    assert report["network_or_provider_calls"] == 0
    assert report["q1461_source_rejection"] == "PASSED"
    assert report["dispatch_allowed"] is False
    assert report["launch_ready"] is False
    assert report["runner_integration"] == "PASSED"
    assert report["synthetic_quota_checks"] == {
        "five_hour_threshold": "PASSED", "weekly_threshold": "PASSED", "stale_snapshot": "PASSED",
        "missing_quota": "PASSED", "unknown_usage_lock": "PASSED", "token_ceiling": "PASSED",
        "persisted_stop_control": "PASSED",
    }


def test_source_gate_authorizes_only_after_integration_and_requires_fresh_quota(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report, paths = _preflight(tmp_path, monkeypatch)
    result = source_phase.verify_source_dispatch_gate(
        report=report, quota_snapshot=_quota(), approval_path=paths["approval"],
        seal_path=paths["amendment_seal"], plan=paths["plan"], packet_seal=paths["packet"],
        base_seal=paths["base_seal"], amendment_proposal=paths["amendment_proposal"])
    assert result["status"] == "SOURCE_PHASE_AUTHORIZED"
    assert result["provider_processes_started"] == 0
    assert result["launch_ready"] is True
    assert result["runner_integration"] == "PASSED"

    with pytest.raises(source_phase.SourcePhaseError, match="fresh interpretable quota"):
        source_phase.verify_source_dispatch_gate(
            report=report, quota_snapshot=_quota(freshness_seconds=ledger.MAX_QUOTA_FRESHNESS_SECONDS + 1),
            approval_path=paths["approval"], seal_path=paths["amendment_seal"],
            plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
            amendment_proposal=paths["amendment_proposal"])


def test_stale_amendment_seal_or_preflight_report_is_rejected(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report, paths = _preflight(tmp_path, monkeypatch)
    with paths["amendment_proposal"].open("a", encoding="utf-8") as stream:
        stream.write("changed\n")
    with pytest.raises(source_phase.SourcePhaseError, match="seal is stale"):
        source_phase.verify_source_dispatch_gate(
            report=report, quota_snapshot=_quota(), approval_path=paths["approval"],
            seal_path=paths["amendment_seal"], plan=paths["plan"], packet_seal=paths["packet"],
            base_seal=paths["base_seal"], amendment_proposal=paths["amendment_proposal"])


def test_preflight_rejects_runtime_inside_repository(tmp_path: Path) -> None:
    with pytest.raises(source_phase.SourcePhaseError, match="outside the repository"):
        source_phase.run_source_preflight(runtime_root=EXPERIMENT / "scratch")


def test_source_preflight_rejects_report_inside_repository_before_any_write(tmp_path: Path) -> None:
    with pytest.raises(source_phase.SourcePhaseError, match=r"preflight report.*outside"):
        source_phase.run_source_preflight(
            runtime_root=tmp_path / "runtime", report_path=EXPERIMENT / "runs" / "blocked-report.json")


def test_source_ledger_rejects_repository_path_before_parent_creation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _bundle(tmp_path, monkeypatch)
    ledger_path = EXPERIMENT / "runs" / "blocked-source-ledger.jsonl"
    with pytest.raises(source_phase.SourcePhaseError, match=r"source-phase ledger.*outside"):
        source_phase.initialize_source_ledger(
            ledger_path=ledger_path, approval_path=paths["approval"], seal_path=paths["amendment_seal"],
            plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
            amendment_proposal=paths["amendment_proposal"])
    assert not ledger_path.exists()


def test_source_dispatch_gate_consumes_only_empty_source_ledger_and_rejects_replay(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report, paths = _preflight(tmp_path, monkeypatch)
    dispatch = _load("dispatch_v3", EXPERIMENT / "dispatch_v3.py")
    ledger_path = tmp_path / "source-ledger.jsonl"
    source_phase.initialize_source_ledger(
        ledger_path=ledger_path, approval_path=paths["approval"], seal_path=paths["amendment_seal"],
        plan=paths["plan"], packet_seal=paths["packet"], base_seal=paths["base_seal"],
        amendment_proposal=paths["amendment_proposal"])
    report_path = tmp_path / "preflight-report.json"
    _write_json(report_path, report)
    gate_args = {
        "phase": "technical_source", "approval": paths["approval"],
        "seal_path": paths["base_seal"], "plan": paths["plan"], "packet_seal": paths["packet"],
        "ledger_path": ledger_path, "source_preflight_report": report_path,
        "source_amendment_seal": paths["amendment_seal"], "quota_snapshot": _quota(),
        "source_amendment_proposal": paths["amendment_proposal"],
    }
    admitted = dispatch.require_dispatch(**gate_args)
    assert admitted["status"] == "AUTHORIZED_SOURCE_PHASE"
    assert admitted["provider_processes_started"] == 0

    ledger.reserve("codex", "technical", quota_snapshot=_quota(), path=ledger_path)
    with pytest.raises(dispatch.ledger.LedgerError, match="one-shot"):
        dispatch.require_dispatch(**gate_args)


def test_technical_runner_completes_two_synthetic_turns_through_module_boundaries(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report, paths = _preflight(tmp_path, monkeypatch)
    runner = _load("a22_p3_v3_runner", EXPERIMENT / "v3_runner.py")
    ledger_path = tmp_path / "source-ledger.jsonl"
    report_path = tmp_path / "source-preflight.json"
    _write_json(report_path, report)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    auth_path = codex_home / "auth.json"
    auth_path.write_text('{"account_id":"synthetic-account"}', encoding="utf-8")
    auth_path.chmod(0o600)
    executable = tmp_path / "bin" / "codex"
    executable.parent.mkdir()
    executable.write_text("synthetic executable placeholder", encoding="utf-8")
    monkeypatch.setattr(runner.shutil, "which", lambda _codex: str(executable))
    versions: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        versions.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, runner.CLI_VERSION, "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    receipt = {
        "codex_executable_sha256": "1" * 64, "codex_home_sha256": "2" * 64,
        "account_id_sha256": "3" * 64, "five_hour_stop_percent": 80,
        "weekly_stop_percent": 90,
    }
    receipt["limit_receipt_sha256"] = source_phase.hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    quota_bindings: list[tuple[str, Path, dict[str, str]]] = []
    monkeypatch.setattr(runner.quota_adapter_v3, "account_limit_receipt",
                        lambda cli, home: (quota_bindings.append((cli, home, {})) or receipt))

    def fake_quota(*, codex_executable: str, codex_home: Path,
                   environment: dict[str, str]) -> dict[str, Any]:
        quota_bindings.append((codex_executable, codex_home, environment))
        assert environment["CODEX_HOME"] == str(codex_home)
        return _quota(source=runner.quota_adapter_v3.SOURCE, account_limit_receipt=receipt)

    monkeypatch.setattr(runner.quota_adapter_v3, "read_quota_snapshot", fake_quota)
    session = "synthetic-source-session"
    usages = ({"input_tokens": 120, "output_tokens": 12}, {"input_tokens": 160, "output_tokens": 15})
    call_count = 0

    def stream(reply: str, usage: dict[str, int]) -> str:
        return "\n".join(json.dumps(event) for event in (
            {"type": "thread.started", "thread_id": session},
            {"type": "item.completed", "item": {"type": "agent_message", "text": reply}},
            {"type": "turn.completed", "usage": usage},
        ))

    rollout_events = [
        {"type": "session_meta", "payload": {"id": session, "cli_version": runner.CLI_VERSION,
         "cwd": str(scratch.resolve()), "base_instructions": {"text": runner.ARM.read_text()}}},
        {"type": "turn_context", "payload": {"model": runner.MODEL, "effort": runner.EFFORT}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": usages[0]}}},
        {"type": "turn_context", "payload": {"model": runner.MODEL, "effort": runner.EFFORT}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": usages[1]}}},
    ]

    class FakeProcess:
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            self.command = command
            self.env = kwargs["env"]
            self.stdout = stream("CHECK: owner-use" if call_count == 1 else "Synthetic second-turn answer.",
                                 usages[call_count - 1])

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            if call_count == 2:
                sessions = Path(self.env["CODEX_HOME"]) / "sessions"
                sessions.mkdir(parents=True, exist_ok=True)
                (sessions / "synthetic-rollout.jsonl").write_text(
                    "\n".join(json.dumps(event) for event in rollout_events) + "\n", encoding="utf-8")
            return self.stdout, ""

        def terminate(self) -> None:
            raise AssertionError("synthetic source call should not be terminated")

        def kill(self) -> None:
            raise AssertionError("synthetic source call should not be killed")

    monkeypatch.setattr(runner.subprocess, "Popen", FakeProcess)
    result = runner.run_technical_source(
        output_dir=tmp_path / "output", scratch=scratch, rollout_root=codex_home / "sessions",
        codex="codex", ledger_path=ledger_path, codex_home=codex_home,
        approval=paths["approval"], seal_path=paths["base_seal"], plan=paths["plan"],
        packet_seal=paths["packet"], source_preflight_report=report_path,
        source_amendment_seal=paths["amendment_seal"],
        source_amendment_proposal=paths["amendment_proposal"])
    assert call_count == 2 and result["verified"] is True
    assert result["provenance_scope"] == "evaluator_only"
    assert result["account_limit_receipt"] == receipt
    assert len(versions) == 1 and versions[0][0] == [str(executable), "--version"]
    assert versions[0][1]["CODEX_HOME"] == str(codex_home)
    assert all(binding[0] == str(executable) and binding[1] == codex_home for binding in quota_bindings)
    assert quota_bindings[-1][2]["CODEX_HOME"] == versions[0][1]["CODEX_HOME"]
    assert all("CODEX_API_KEY" not in env and "OPENAI_API_KEY" not in env for _, env in versions)
    header, events = ledger._read(ledger_path)
    assert header["source_phase_only"] is True
    completed = [event for event in events if event["event"] == "completed"]
    assert len(completed) == 2 and all(event["usage_status"] == "known" for event in completed)


def test_source_runner_rejects_in_repo_ledger_before_initialization(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report, paths = _preflight(tmp_path, monkeypatch)
    runner = _load("a22_p3_v3_runner", EXPERIMENT / "v3_runner.py")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    output = tmp_path / "output"
    ledger_path = EXPERIMENT / "runs" / "blocked-runner-source-ledger.jsonl"
    report_path = tmp_path / "preflight.json"
    _write_json(report_path, report)
    with pytest.raises(runner.RunnerError, match=r"source ledger.*outside"):
        runner.run_technical_source(
            output_dir=output, scratch=scratch,
            rollout_root=output / "runtime" / "codex-home" / "sessions",
            ledger_path=ledger_path, codex_home=tmp_path / "codex-home", approval=paths["approval"],
            seal_path=paths["base_seal"], plan=paths["plan"], packet_seal=paths["packet"],
            source_preflight_report=report_path, source_amendment_seal=paths["amendment_seal"],
            source_amendment_proposal=paths["amendment_proposal"])
    assert not ledger_path.exists()
    assert not output.exists()


def test_source_runner_rejects_symlinked_or_preconfigured_codex_home(tmp_path: Path) -> None:
    runner = _load("a22_p3_v3_runner", EXPERIMENT / "v3_runner.py")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    real_home = tmp_path / "real-codex-home"
    real_home.mkdir()
    auth_path = real_home / "auth.json"
    auth_path.write_text('{"account_id":"synthetic"}', encoding="utf-8")
    auth_path.chmod(0o600)
    linked_home = tmp_path / "linked-codex-home"
    linked_home.symlink_to(real_home, target_is_directory=True)
    with pytest.raises(runner.RunnerError, match="CODEX_HOME cannot be a symlink"):
        runner._validate_source_runtime_paths(
            scratch=scratch, output_dir=tmp_path / "output", rollout_root=linked_home / "sessions",
            ledger_path=tmp_path / "ledger.jsonl", codex_home=linked_home)

    (real_home / "config.toml").write_text("[mcp_servers.synthetic]\n", encoding="utf-8")
    with pytest.raises(runner.RunnerError, match="dedicated external directory"):
        runner._validate_source_runtime_paths(
            scratch=scratch, output_dir=tmp_path / "output", rollout_root=real_home / "sessions",
            ledger_path=tmp_path / "ledger.jsonl", codex_home=real_home)
