"""Offline guard tests for the V2 one-shot scored-reading runner."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNNER_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "scored_reading.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_scored_reading", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
scored = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scored)


class FakeLedger:
    DEFAULT_PATHS = (Path("ledger"), Path("plan"), Path("seal"), Path("approval"))

    def __init__(self, *, denied: bool = False, retry_policy: str = "OBSERVED_NO_RETRY") -> None:
        self.denied = denied
        self.retry_policy = retry_policy
        self.calls: list[tuple[str, object]] = []
        self.runs_path: Path | None = None

    def require_dispatch_authorization(self, *, paths: object, phase: str) -> None:
        self.calls.append(("gate", phase))
        if self.denied:
            raise ValueError("not authorized")

    def approved_retry_evidence_policy(self, *, paths: object, phase: str) -> str:
        self.calls.append(("retry_policy", phase))
        return self.retry_policy

    def reserve_attempt(self, route: str, attempt_class: str, *, paths: object,  # noqa: PLR0913
                        attempt_id: str, opaque_packet_id: str, packet_sha256: str) -> str:
        self.calls.append(("reserve", attempt_class))
        return attempt_id

    def complete_attempt(self, attempt_id: str, **kwargs: object) -> dict[str, str]:
        if kwargs.get("outcome") == "accepted" and self.runs_path is not None:
            assert (self.runs_path / "scored-readings" / attempt_id / "outcome.json").is_file()
        self.calls.append(("complete", kwargs.get("outcome")))
        return {"outcome": str(kwargs["outcome"])}


def _fake_core(*, bad_correlation: bool = False, secret: str = "", receipt_error: bool = False,  # noqa: C901
               retry_marker: bool = False, qwen_control_mismatch: bool = False) -> SimpleNamespace:
    packet = b"opaque packet content"
    prompt = b"frozen scorer prompt"
    opaque_id = "g0123456789abcdef"
    answer = f"run_id\telement\tverdict\treason\n{opaque_id}\tE1\tPASS\tEvidence.\n"
    settings_by_route = {
        "codex": {"executable": "codex", "version": "0.156.1", "model": "gpt-6-astra"},
        "qwen": {"executable": "qwen", "version": "0.24.7", "model": "qwen3.8-27b"},
    }
    scratch_seen: list[Path] = []
    session_seen: list[str] = []

    def invoke(_command: list[str], _request: bytes, scratch: Path,
               _env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
        scratch_seen.append(scratch)
        if "--session-id" in _command:
            session_seen.append(_command[_command.index("--session-id") + 1])
        else:
            session_seen.append("session-1")
        return subprocess.CompletedProcess(
            ["codex"], 0, b"event", (secret + "\n" if secret else "stderr").encode())

    def private_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)

    def write_json(path: Path, value: object) -> None:
        if receipt_error and path.name == "outcome.json":
            raise OSError("simulated receipt write failure")
        private_write(path, (json.dumps(value) + "\n").encode())

    def parse_jsonl(data: bytes) -> list[dict]:
        events = [{"type": "turn.completed", "thread_id": "session-1",
                   "session_id": session_seen[-1],
                   "usage": {"input_tokens": 50, "output_tokens": 20}, "text": answer}]
        if retry_marker:
            events.append({"type": "api_retry"})
        return events

    def final_text(events: list[dict]) -> str:
        return events[0]["text"]

    def usage_artifact(path: Path, **kwargs: object) -> dict[str, str]:
        private_write(path, json.dumps(kwargs, default=str).encode())
        return {"artifact_path": path.name, "artifact_sha256": "a" * 64,
                "request_id": str(kwargs["request_id"]), "session_id": str(kwargs["session_id"]),
                "model_id": str(kwargs["model_id"]), "call_id": str(kwargs["call_id"])}

    def terminalize(ledger: FakeLedger, attempt_id: str, **kwargs: object) -> dict[str, str]:
        return ledger.complete_attempt(attempt_id, **kwargs)

    def route_settings(route: str) -> dict[str, str]:
        return settings_by_route[route]

    def qwen_settings(_home: Path, _env: dict[str, str]) -> tuple[str, dict, dict]:
        return "https://gateway.example", {}, {
            "maxRetries": 1 if qwen_control_mismatch else 0,
            "model_fallbacks": [], "max_tokens": 2_000,
        }

    return SimpleNamespace(
        validate_bundle=lambda _packet, _evaluator: ({"opaque_packet_id": opaque_id}, packet, prompt, ["E1"]),
        make_request=lambda prompt_bytes, packet_bytes: prompt_bytes + b"\n" + packet_bytes,
        _model_settings=route_settings, sha=lambda value: __import__("hashlib").sha256(value).hexdigest(),
        OUTPUT_CAP={"codex": 1_000, "qwen": 2_000}, INPUT_CAP=20_000, ProviderStartError=OSError,
        _child_environment=lambda _route, _parent, **_kwargs: {"PATH": "/bin", "OPENAI_API_KEY": "qwen-token"},
        _version_matches=lambda _version, _expected: True, _redacted_argv=lambda *_args: ["codex", "exec"],
        _codex_command=lambda _executable, _scratch: ["codex", "exec"],
        _qwen_preflight=qwen_settings,
        _qwen_command=lambda _executable, _gateway, session_id: ["qwen", "--session-id", session_id],
        invoke_one_provider_process=invoke,
        secure_capture=lambda data, _secret="": data.replace(secret.encode(), b"[REDACTED]") if secret else data,
        private_write=private_write, parse_jsonl=parse_jsonl, write_json=write_json,
        usage_from_events=lambda _events: {"input_tokens": 50, "output_tokens": 20},
        codex_rollout=lambda _home, _session: (b"rollout", {
            "model_id": "other-model" if bad_correlation else "gpt-6-astra",
            "cwd": str(scratch_seen[-1]) if scratch_seen else "",
        }),
        event_session_ids=lambda events: {events[0]["session_id"]},
        qwen_usage_record=lambda _path, _project, qwen_session, _before: {
            "input_tokens": 50, "output_tokens": 20, "model_id": "qwen3.8-27b",
            "requests": 1, "tool_calls": 0, "session_id": qwen_session,
        },
        tool_markers=lambda _events: [], final_text=final_text,
        validate_retry_evidence=scored._route_core().validate_retry_evidence,
        validate_tsv=lambda reply, packet_id, ids: None if reply.startswith(
            f"run_id\telement\tverdict\treason\n{packet_id}\tE1\tPASS" ) and ids == ["E1"]
            else (_ for _ in ()).throw(ValueError("invalid TSV")),
        _usage_artifact=usage_artifact, terminalize_attempt=terminalize,
    )


def _install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, denied: bool = False,  # noqa: PLR0913
             integrity_error: bool = False, bad_correlation: bool = False,
             secret: str = "", receipt_error: bool = False, route: str = "codex",
             retry_policy: str = "OBSERVED_NO_RETRY", retry_marker: bool = False,
             qwen_control_mismatch: bool = False) -> FakeLedger:
    ledger = FakeLedger(denied=denied, retry_policy=retry_policy)
    ledger.runs_path = tmp_path / "runs"
    core = _fake_core(bad_correlation=bad_correlation, secret=secret, receipt_error=receipt_error,
                      retry_marker=retry_marker, qwen_control_mismatch=qwen_control_mismatch)
    if integrity_error:
        core.validate_bundle = lambda *_args: (_ for _ in ()).throw(ValueError("tampered"))
    monkeypatch.setattr(scored, "_route_core", lambda: core)
    monkeypatch.setattr(scored, "_load_ledger", lambda: ledger)
    monkeypatch.setattr(scored, "RUNS", tmp_path / "runs")
    version = "0.24.7" if route == "qwen" else "0.156.1"
    monkeypatch.setattr(scored.shutil, "which", lambda _name: f"/usr/bin/{route}")
    monkeypatch.setattr(scored.subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess(
        [route, "--version"], 0, f"{route}-cli {version}".encode(), b""))
    return ledger


def test_approval_denial_stops_before_packet_read_or_cli(monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = _install(monkeypatch, tmp_path, denied=True)
    result = scored.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator")
    assert result == 2
    assert ledger.calls == [("gate", "qualification")]
    assert "DISPATCH_BLOCKED" in capsys.readouterr().out


def test_packet_integrity_failure_never_reserves_or_calls_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    ledger = _install(monkeypatch, tmp_path, integrity_error=True)
    result = scored.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator")
    assert result == 2
    assert ledger.calls == [("gate", "qualification"), ("retry_policy", "qualification")]


def test_scored_reading_reserves_correct_class_and_redacts_provider_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    ledger = _install(monkeypatch, tmp_path, secret="provider-secret")
    result = scored.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator")
    assert result == 0
    assert ledger.calls == [("gate", "qualification"), ("retry_policy", "qualification"),
                            ("reserve", "scored_reading"), ("complete", "accepted")]
    assert "provider-secret" not in capsys.readouterr().out
    evidence_dirs = list((tmp_path / "runs" / "scored-readings").iterdir())
    assert len(evidence_dirs) == 1
    assert b"provider-secret" not in (evidence_dirs[0] / "stderr.raw").read_bytes()
    outcome = json.loads((evidence_dirs[0] / "outcome.json").read_text())
    assert outcome["opaque_packet_id"] == "g0123456789abcdef"
    assert outcome["scored_p3"] is True
    assert outcome["ledger_outcome"] == "pending"
    assert outcome["intended_ledger_outcome"] == "accepted"


def test_usage_session_model_mismatch_terminalizes_as_failed_unknown_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    ledger = _install(monkeypatch, tmp_path, bad_correlation=True)
    result = scored.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator")
    assert result == 1
    assert ledger.calls[-1] == ("complete", "failed")
    evidence_dir = next((tmp_path / "runs" / "scored-readings").iterdir())
    outcome = json.loads((evidence_dir / "outcome.json").read_text())
    assert outcome["usage"] is None
    assert outcome["failure_code"] == "missing_usage"


def test_outcome_receipt_is_written_before_ledger_acceptance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    ledger = _install(monkeypatch, tmp_path, receipt_error=True)
    result = scored.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator")
    assert result == 2
    assert ledger.calls[-1] == ("complete", "failed")
    evidence_dir = next((tmp_path / "runs" / "scored-readings").iterdir())
    assert (evidence_dir / "final.tsv").is_file()
    assert not (evidence_dir / "outcome.json").exists()


@pytest.mark.parametrize("route", ["codex", "qwen"])
def test_selected_retry_policy_is_validated_and_persisted_for_both_routes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, route: str,
) -> None:
    ledger = _install(monkeypatch, tmp_path, route=route)
    result = scored.dispatch(route, tmp_path / "packet", tmp_path / "evaluator")
    assert result == 0
    assert ledger.calls[-1] == ("complete", "accepted")
    evidence_dir = next((tmp_path / "runs" / "scored-readings").iterdir())
    outcome = json.loads((evidence_dir / "outcome.json").read_text())
    assert outcome["retry_evidence_policy"] == "OBSERVED_NO_RETRY"
    assert outcome["retry_observed_markers"] == []
    assert "transport retries are not observable" in outcome["retry_evidence"]
    usage = json.loads((tmp_path / "runs" / "usage-artifacts" / f"{evidence_dir.name}.json").read_text())
    assert usage["evidence"]["retry_evidence_policy"] == "OBSERVED_NO_RETRY"


def test_unselected_retry_policy_blocks_before_reservation_or_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    ledger = _install(monkeypatch, tmp_path, retry_policy="UNSELECTED")
    result = scored.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator")
    assert result == 2
    assert ledger.calls == [("gate", "qualification"), ("retry_policy", "qualification")]
    assert "DISPATCH_BLOCKED" in capsys.readouterr().out


def test_retry_marker_or_qwen_control_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    ledger = _install(monkeypatch, tmp_path, retry_marker=True)
    assert scored.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator") == 1
    evidence_dir = next((tmp_path / "runs" / "scored-readings").iterdir())
    outcome = json.loads((evidence_dir / "outcome.json").read_text())
    assert outcome["retry_observed_markers"] == ["event:type"]
    assert ledger.calls[-1] == ("complete", "failed")

    monkeypatch.undo()
    qwen_tmp = tmp_path / "qwen"
    qwen_tmp.mkdir()
    qwen_ledger = _install(monkeypatch, qwen_tmp, route="qwen", qwen_control_mismatch=True)
    assert scored.dispatch("qwen", qwen_tmp / "packet", qwen_tmp / "evaluator") == 1
    qwen_evidence = next((qwen_tmp / "runs" / "scored-readings").iterdir())
    qwen_outcome = json.loads((qwen_evidence / "outcome.json").read_text())
    assert qwen_outcome["retry_evidence_policy"] == "OBSERVED_NO_RETRY"
    assert qwen_ledger.calls[-1] == ("complete", "failed")
