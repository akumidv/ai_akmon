"""Offline fail-closed checks for P3 scorer route mechanics."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

RUNNER_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "scorer_route_check.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_scorer_route_check", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
route_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route_check)
LEDGER_PATH = RUNNER_PATH.with_name("usage_ledger_v2.py")
LEDGER_SPEC = importlib.util.spec_from_file_location("a22_p3_test_usage_ledger_v2", LEDGER_PATH)
assert LEDGER_SPEC is not None and LEDGER_SPEC.loader is not None
usage_ledger_v2 = importlib.util.module_from_spec(LEDGER_SPEC)
LEDGER_SPEC.loader.exec_module(usage_ledger_v2)


def _events(text: str) -> list[dict]:
    return route_check.parse_jsonl((text + "\n").encode())


def test_event_parser_rejects_non_objects_and_malformed_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        route_check.parse_jsonl(b"[]\n")
    with pytest.raises(json.JSONDecodeError):
        route_check.parse_jsonl(b"{bad}\n")
    with pytest.raises(ValueError, match="empty"):
        route_check.parse_jsonl(b"\n")


def test_observed_no_retry_policy_accepts_only_route_specific_mechanics_evidence() -> None:
    events = [{"type": "turn.completed"}]
    assert (
        route_check.validate_retry_evidence(
            "OBSERVED_NO_RETRY",
            "codex",
            events,
            b"",
            1,
            {},
            {"model_id": "gpt-6-astra"},
            ["codex"],
        )
        == []
    )
    assert (
        route_check.validate_retry_evidence(
            "OBSERVED_NO_RETRY",
            "qwen",
            events,
            b"",
            1,
            {"maxRetries": 0, "model_fallbacks": []},
            {"requests": 1, "model_id": "qwen3.8-27b"},
            ["qwen"],
        )
        == []
    )


@pytest.mark.parametrize(
    "events,stderr",
    [
        ([{"type": "api_retry"}], b""),
        ([{"type": "turn.completed"}], b"Retrying request after timeout"),
        ([{"type": "api_error", "message": "provider error"}], b""),
    ],
)
def test_observed_no_retry_policy_detects_visible_retry_or_error_markers(events, stderr) -> None:
    assert route_check.validate_retry_evidence(
        "OBSERVED_NO_RETRY",
        "codex",
        events,
        stderr,
        1,
        {},
        {},
        ["codex"],
    )


@pytest.mark.parametrize(
    "policy,route,settings,session,command",
    [
        ("UNSELECTED", "codex", {}, {}, ["codex"]),
        ("OBSERVED_NO_RETRY", "qwen", {"maxRetries": 1, "model_fallbacks": []}, {"requests": 1}, ["qwen"]),
        ("OBSERVED_NO_RETRY", "qwen", {"maxRetries": 0, "model_fallbacks": []}, {"requests": 2}, ["qwen"]),
        (
            "OBSERVED_NO_RETRY",
            "qwen",
            {"maxRetries": 0, "model_fallbacks": []},
            {"requests": 1},
            ["qwen", "--fallback-model"],
        ),
        ("OBSERVED_NO_RETRY", "qwen", {"maxRetries": 0}, {"requests": 1}, ["qwen"]),
    ],
)
def test_observed_no_retry_policy_fails_closed_on_unselected_or_incomplete_controls(
    policy,
    route,
    settings,
    session,
    command,
) -> None:
    with pytest.raises(ValueError):
        route_check.validate_retry_evidence(
            policy,
            route,
            [{"type": "turn.completed"}],
            b"",
            1,
            settings,
            session,
            command,
        )


def _real_grid_import(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    experiment = Path(__file__).parents[1] / "experiments" / "a22-p3"
    source_grid = experiment / "grid.py"
    grid_path = root / "grid.py"
    root.mkdir(parents=True, exist_ok=True)
    grid_path.write_bytes(source_grid.read_bytes())
    spec = importlib.util.spec_from_file_location("a22_p3_grid_import_fixture", grid_path)
    assert spec is not None and spec.loader is not None
    grid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grid)
    monkeypatch.setattr(grid, "HERE", root)

    runs, cases, arms, scoring, private = (
        root / name for name in ("runs", "cases", "arms", "scoring", "private-scorers")
    )
    for directory in (runs, cases, arms, scoring):
        directory.mkdir(parents=True, exist_ok=True)
    private.mkdir(mode=0o700)
    arm_path = arms / "A.architect.system.txt"
    arm_path.write_text("Frozen arm A.\n", encoding="utf-8")
    scorer_paths = (private / "scorer-1.tsv", private / "scorer-2.tsv")
    run_map: dict[str, dict[str, object]] = {}
    rows: list[list[str]] = [[], []]
    for case_number in range(1, 9):
        case_id = f"P3-{case_number:02d}"
        case_path = cases / f"{case_id}.json"
        case_path.write_text(
            json.dumps(
                {
                    "id": case_id,
                    "pair": f"pair{(case_number + 1) // 2}",
                    "scoring": [f"E{number}: criterion {number}" for number in range(1, 5)],
                }
            ),
            encoding="utf-8",
        )
        for tier in ("strongest", "mid"):
            for repeat in (1, 2):
                run_id = f"q{case_number:02d}{tier[0]}{repeat}"
                cell = {"case": case_id, "arm": "A", "tier": tier, "repeat": repeat}
                run_map[run_id] = cell
                events_sha = [f"{run_id}-event-1", f"{run_id}-event-2"]
                exchange = {
                    "run_id": run_id,
                    "turns": [
                        {"user": "Question 1", "assistant": "Answer 1", "events_sha256": events_sha[0]},
                        {"user": "Question 2", "assistant": "Answer 2", "events_sha256": events_sha[1]},
                    ],
                }
                exchange_path = runs / f"{run_id}.exchange.json"
                exchange_path.write_text(json.dumps(exchange), encoding="utf-8")
                record = {
                    "run_id": run_id,
                    "case": case_id,
                    "arm": "A",
                    "tier": tier,
                    "repeat": repeat,
                    "verified": True,
                    "case_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
                    "arm_sha256": hashlib.sha256(arm_path.read_bytes()).hexdigest(),
                    "exchange_sha256": hashlib.sha256(exchange_path.read_bytes()).hexdigest(),
                    "events_sha256": events_sha,
                    "rollout": {"verified": True},
                }
                (runs / f"{run_id}.record.json").write_text(json.dumps(record), encoding="utf-8")
                for scorer_rows in rows:
                    scorer_rows.extend(f"{run_id}\tE{number}\tFAIL\tObserved.\n" for number in range(1, 5))

    qual_map_path = runs / "qual-sealed-map.json"
    qual_map_path.write_text(json.dumps(run_map, sort_keys=True), encoding="utf-8")
    prompt_path = scoring / "scorer-prompt.txt"
    prompt_path.write_text("Frozen prompt.\n", encoding="utf-8")
    renderer_path = root / "score_packets.py"
    renderer_path.write_text("# Frozen renderer\n", encoding="utf-8")
    sealed_paths = [qual_map_path, prompt_path, renderer_path, grid_path, arm_path, *sorted(cases.glob("P3-*.json"))]
    seal = {
        "schema": 1,
        "files": {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sealed_paths
        },
    }
    (root / "seal.json").write_text(json.dumps(seal), encoding="utf-8")
    for path, text in zip(scorer_paths, rows, strict=True):
        path.write_text("".join(text), encoding="utf-8")
        path.chmod(0o600)

    grid.main(str(scorer_paths[0]), str(scorer_paths[1]))
    return scorer_paths


def test_grid_source_context_accepts_actual_grid_py_output_and_rederives_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    scorer1, scorer2 = _real_grid_import(root, monkeypatch)
    builder = route_check._packet_builder()
    monkeypatch.setattr(route_check, "HERE", root)
    monkeypatch.setattr(route_check, "RUNS", root / "runs")
    current_hashes = {"seal.json": route_check.sha((root / "seal.json").read_bytes())}
    result, hashes = route_check._grid_source_context(builder, current_hashes)
    imported = json.loads((root / "runs" / "qualification-import.json").read_text(encoding="utf-8"))
    assert set(imported) == {"scorer_1", "scorer_2", "run_evidence"}
    assert "source_scorer_sha256" not in imported
    assert result == json.loads((root / "runs" / "grid-sealed-map.json").read_text(encoding="utf-8"))
    assert hashes["qualification_scorer_1.tsv"] == route_check.sha(scorer1.read_bytes())
    assert hashes["qualification_scorer_2.tsv"] == route_check.sha(scorer2.read_bytes())

    (root / "runs" / "grid-sealed-map.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from scorer re-derivation"):
        route_check._grid_source_context(builder, {})


def test_grid_source_context_fails_closed_when_producer_tsv_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    scorer1, _scorer2 = _real_grid_import(root, monkeypatch)
    scorer1.unlink()
    builder = route_check._packet_builder()
    monkeypatch.setattr(route_check, "HERE", root)
    monkeypatch.setattr(route_check, "RUNS", root / "runs")
    with pytest.raises(ValueError, match="missing or unsafe"):
        route_check._grid_source_context(builder, {})


def test_one_provider_invoker_starts_one_process_and_never_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(route_check.subprocess, "run", fake_run)
    result = route_check.invoke_one_provider_process(["mock-scorer"], b"frozen request", tmp_path, {})
    assert result.returncode == 0
    assert len(calls) == 1
    assert calls[0][1]["input"] == b"frozen request"


def test_usage_parser_requires_one_nonnegative_integer_record() -> None:
    assert route_check.usage_from_events(
        _events('{"type":"turn.completed","usage":{"input_tokens":42,"output_tokens":7}}')
    ) == {"input_tokens": 42, "output_tokens": 7}
    with pytest.raises(ValueError, match="exactly one"):
        route_check.usage_from_events(
            _events(
                '{"usage":{"input_tokens":1,"output_tokens":1},"child":{"usage":{"input_tokens":2,"output_tokens":2}}}'
            )
        )
    with pytest.raises(ValueError, match="invalid token"):
        route_check.usage_from_events(_events('{"usage":{"input_tokens":true,"output_tokens":1}}'))


def test_tsv_validation_binds_packet_id_and_each_element() -> None:
    good = (
        "run_id\telement\tverdict\treason\n"
        "g0123456789abcdef\tE1\tPASS\tObserved.\n"
        "g0123456789abcdef\tE2\tFAIL\tMissing.\n"
    )
    route_check.validate_tsv(good, "g0123456789abcdef", ["E1", "E2"])
    with pytest.raises(ValueError, match="IDs"):
        route_check.validate_tsv(good, "g0123456789abcdef", ["E1"])
    with pytest.raises(ValueError, match="duplicate"):
        route_check.validate_tsv(good + "g0123456789abcdef\tE1\tPASS\tAgain.\n", "g0123456789abcdef", ["E1", "E2"])
    with pytest.raises(ValueError, match="row is malformed"):
        route_check.validate_tsv(
            good.replace("g0123456789abcdef\tE1", "g0000000000000000\tE1"), "g0123456789abcdef", ["E1", "E2"]
        )


def test_route_pair_requires_the_same_packet_and_prompt_for_one_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route_check, "RUNS", tmp_path)
    attempts = tmp_path / "route-checks" / "prior"
    attempts.mkdir(mode=0o700, parents=True)
    prior = {
        "route": "codex",
        "approval_sha256": "a" * 64,
        "opaque_packet_id": "g0123456789abcdef",
        "packet_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
    }
    (attempts / "attempt.json").write_text(json.dumps(prior) + "\n", encoding="utf-8")
    route_check._check_route_pair(
        "qwen", prior["opaque_packet_id"], prior["packet_sha256"], prior["prompt_sha256"], prior["approval_sha256"]
    )
    with pytest.raises(ValueError, match="same sealed packet"):
        route_check._check_route_pair(
            "qwen", "gffffffffffffffff", prior["packet_sha256"], prior["prompt_sha256"], prior["approval_sha256"]
        )


def test_qwen_usage_requires_exact_session_model_and_zero_tools(tmp_path: Path) -> None:
    record_path = tmp_path / "usage.jsonl"
    good = {
        "project": "/scratch",
        "sessionId": "s1",
        "models": {"qwen3.8-27b": {"requests": 1, "inputTokens": 99, "outputTokens": 20}},
        "tools": {"totalCalls": 0},
    }
    record_path.write_text(json.dumps(good) + "\n", encoding="utf-8")
    parsed = route_check.qwen_usage_record(record_path, "/scratch", "s1", set())
    assert parsed["input_tokens"] == 99 and parsed["output_tokens"] == 20
    with pytest.raises(ValueError, match="uniquely correlated"):
        route_check.qwen_usage_record(record_path, "/scratch", "s1", {"s1"})
    bad = dict(good, tools={"totalCalls": 1})
    record_path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tool evidence"):
        route_check.qwen_usage_record(record_path, "/scratch", "s1", set())


def test_usage_artifact_is_hash_and_request_session_model_correlated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_path = tmp_path / "provider-usage.jsonl"
    monkeypatch.setattr(route_check, "LEDGER_PATH", ledger_path)
    artifact_dir = tmp_path / "usage-artifacts"
    artifact_dir.mkdir(mode=0o700)
    usage = {"input_tokens": 8, "output_tokens": 3}
    artifact = route_check._usage_artifact(
        artifact_dir / "attempt.json",
        usage=usage,
        call_id="a" * 32,
        request_id="req-1",
        session_id="sess-1",
        model_id="gpt-6-astra",
        evidence={"tool_markers": [], "retry_count": 0, "tsv_sha256": "f" * 64},
    )
    reservation = {"attempt_class": "route_check", "route": "codex"}
    usage_ledger_v2._validate_usage_evidence(usage, artifact, ledger_path, "a" * 32, reservation)
    raw = (tmp_path / artifact["artifact_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == artifact["artifact_sha256"]
    saved = json.loads(raw)
    assert saved["request_id"] == artifact["request_id"]
    assert saved["session_id"] == artifact["session_id"]
    assert saved["model_id"] == artifact["model_id"]
    saved["session_id"] = "other-session"
    (tmp_path / artifact["artifact_path"]).write_text(json.dumps(saved) + "\n", encoding="utf-8")
    with pytest.raises(usage_ledger_v2.LedgerError, match="hash or request/session/model"):
        usage_ledger_v2._validate_usage_evidence(usage, artifact, ledger_path, "a" * 32, reservation)


def test_terminalize_failure_retries_only_ledger_completion_as_unknown_usage() -> None:
    class FakeLedger:
        calls: list[dict[str, object]]

        def __init__(self) -> None:
            self.calls = []

        def complete_attempt(self, attempt_id: str, **kwargs: object) -> dict[str, object]:
            self.calls.append({"attempt_id": attempt_id, **kwargs})
            if len(self.calls) == 1:
                raise usage_ledger_v2.LedgerError("evidence rejected")
            return {"outcome": "failed", "failure_code": "missing_usage"}

    ledger = FakeLedger()
    result = route_check.terminalize_attempt(
        ledger,
        "a" * 32,
        outcome="accepted",
        actual_usage={"input_tokens": 1, "output_tokens": 1},
        usage_artifact={"invalid": True},
        failure_code=None,
    )
    assert result["failure_code"] == "missing_usage"
    assert len(ledger.calls) == 2
    assert ledger.calls[1]["outcome"] == "failed"
    assert ledger.calls[1]["actual_usage"] is None
    assert ledger.calls[1]["usage_artifact"] is None


@pytest.mark.parametrize(
    "output,expected,matched",
    [
        ("codex-cli 0.156.1", "0.156.1", "yes"),
        ("codex-cli 0.156.10", "0.156.1", "no"),
        ("codex-cli 0.156.1-beta", "0.156.1", "no"),
        ("x0.156.1", "0.156.1", "no"),
        ("qwen 0.24.7", "0.24.7", "yes"),
        ("qwen 0.24.70", "0.24.7", "no"),
    ],
)
def test_cli_version_requires_exact_numeric_token(output: str, expected: str, matched: str) -> None:
    assert route_check._version_matches(output, expected) is (matched == "yes")


def test_child_environment_excludes_unrelated_credentials() -> None:
    parent = {
        "PATH": "/bin",
        "HOME": "/home/example",
        "OPENAI_API_KEY": "unrelated",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "LITE_LLM_AUTH_TOKEN": "qwen-token",
        "ANTHROPIC_API_KEY": "another-secret",
        "CODEX_HOME": "/home/example/.codex",
    }
    codex = route_check._child_environment("codex", parent)
    qwen = route_check._child_environment("qwen", parent, auth_token=parent["LITE_LLM_AUTH_TOKEN"])
    assert codex == {"PATH": "/bin", "HOME": str(Path.home()), "CODEX_HOME": "/home/example/.codex"}
    assert qwen == {"PATH": "/bin", "HOME": str(Path.home()), "OPENAI_API_KEY": "qwen-token"}
    assert "AWS_SECRET_ACCESS_KEY" not in codex and "ANTHROPIC_API_KEY" not in qwen


def test_dispatch_gate_and_reservation_precede_provider_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    order: list[str] = []

    class FakeLedger:
        DEFAULT_PATHS = (tmp_path / "ledger", tmp_path / "plan", tmp_path / "packet-seal", tmp_path / "approval")

        @staticmethod
        def require_dispatch_authorization(*, paths: object, phase: str) -> None:
            assert phase == "route_check"
            order.append("gate")

        @staticmethod
        def approved_retry_evidence_policy(*, paths: object, phase: str) -> str:
            assert phase == "route_check"
            order.append("retry-policy")
            return "OBSERVED_NO_RETRY"

        @staticmethod
        def reserve_attempt(*args: object, **kwargs: object) -> str:
            order.append("reserve")
            raise usage_ledger_v2.LedgerError("synthetic reserve stop")

    monkeypatch.setattr(route_check, "_load_ledger", lambda: FakeLedger)
    monkeypatch.setattr(route_check, "RUNS", tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "owner-approval-v2.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        route_check,
        "validate_bundle",
        lambda *_: (
            {"opaque_packet_id": "g0123456789abcdef"},
            b"packet",
            b"prompt",
            ["E1"],
        ),
    )
    monkeypatch.setattr(route_check, "_check_route_pair", lambda *_: None)
    monkeypatch.setattr(route_check.shutil, "which", lambda _: "/bin/codex")
    monkeypatch.setattr(
        route_check,
        "_model_settings",
        lambda _: {"executable": "codex", "version": "0.156.1", "model": "gpt-6-astra", "effort": "medium"},
    )

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert command[-1] == "--version"
        assert "AWS_SECRET_ACCESS_KEY" not in kwargs["env"]
        order.append("version")
        return subprocess.CompletedProcess(command, 0, b"codex-cli 0.156.1", b"")

    monkeypatch.setattr(route_check.subprocess, "run", fake_run)
    monkeypatch.setattr(
        route_check,
        "invoke_one_provider_process",
        lambda *_args, **_kwargs: pytest.fail("provider invocation happened before reservation"),
    )
    assert route_check.dispatch("codex", tmp_path / "packet", tmp_path / "evaluator") == 2
    assert order == ["gate", "retry-policy", "version", "reserve"]
    assert "DISPATCH_BLOCKED" in capsys.readouterr().out
