#!/usr/bin/env python3
"""Advance the sealed V3 A qualification by exactly one terminal provider call."""

# This phase has deliberately explicit evidence checks and no automatic retry.
# ruff: noqa: BLE001 C901 D103 PERF401 PLR0912 PLR0913 PLR0915 PLR2004 S108
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import quota_adapter_v3 as quota
import scorer_route_check as scorer
import v3_codex_format_route as codex_route
import v3_controls_successor as controls
import v3_qualification_successor_packet as packet
import v3_qualification_successor_reduce as reduce_module
import v3_qualification_successor_schedule as schedule
import v3_qwen_5000_format_route as qwen_route
import v3_runner_version_successor as source

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2].resolve()
RUNTIME = Path("/tmp/a22-p3-v3-qualification-successor-runtime")
LEDGER = RUNTIME / "qualification-events.jsonl"
PRIOR_LEDGER = Path("/tmp/a22-p3-v3-qualification-runtime/qualification-events.jsonl")
SEAL = HERE / "runs/v3-qualification-successor-seal-v1.json"
APPROVAL = HERE / "runs/v3-qualification-successor-approval-v1.json"
PREFLIGHT = HERE / "runs/v3-qualification-successor-preflight-v1.json"
PROPOSAL = HERE / "V3_QUALIFICATION_SUCCESSOR_PROPOSAL.md"
CODEX = codex_route.EXECUTABLE
AUTH = codex_route.AUTH_SOURCE
OPENING = 285_782
LIMIT = 5_000_000
ACCOUNT_ID_SHA = codex_route.ACCOUNT_ID_SHA
TOTAL_CALLS = 128
SCORER_INPUT_CAP = 20_000
SUBJECT_INPUT_CAP = 40_000
QWEN_OUTPUT_SETTING = 5_000


class QualificationError(ValueError):
    """A frozen phase condition, call, or evidence binding failed."""


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"missing or linked evidence: {path}")
    return sha_bytes(path.read_bytes())


def read(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"missing or linked JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise QualificationError("linked evidence directory")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, value: Any) -> None:
    write_new(path, (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode())


def digest(value: dict[str, Any]) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def call_plan() -> list[dict[str, Any]]:
    candidate = read(schedule.SCHEDULE)
    schedule.verify_schedule(candidate)
    result = []
    for index, row in enumerate(candidate["cells"]):
        for turn in (1, 2):
            result.append(
                {
                    "index": index,
                    "kind": "subject",
                    "turn": turn,
                    "route": "codex",
                    "call_id": row["subject_call_ids"][turn - 1],
                    "run_id": row["run_id"],
                }
            )
        for item in row["scorers"]:
            result.append(
                {
                    "index": index,
                    "kind": "scorer",
                    "route": item["route"],
                    "call_id": item["call_id"],
                    "run_id": row["run_id"],
                }
            )
    if len(result) != TOTAL_CALLS or len({item["call_id"] for item in result}) != TOTAL_CALLS:
        raise QualificationError("call plan does not cover 128 fresh calls")
    return result


def seal_body() -> dict[str, Any]:
    """Bind the fresh schedule and both format-route mechanics outcomes."""
    codex_route.verify_seal()
    qwen_route.verify_seal()
    codex_outcome = read(HERE / "runs/v3-codex-format-route-evidence/outcome.json")
    qwen_outcome = read(qwen_route.RUNTIME / "outcome.json")
    if (
        codex_outcome.get("status") != "passed"
        or codex_outcome.get("scored_p3") is not False
        or qwen_outcome.get("outcome") != "passed_unscored"
        or qwen_outcome.get("scored_p3") is not False
    ):
        raise QualificationError("format-route mechanics evidence differs")
    prior_total = codex_route.OPENING + sum(codex_outcome["usage"].values())
    if prior_total != OPENING:
        raise QualificationError("successor Codex opening balance differs")
    previous = read(HERE / "runs/v3-qualification-operational-seal-v1.json")
    if previous.get("scorer_output_settings") != {"codex": 1000, "qwen": 2000}:
        raise QualificationError("terminal predecessor setting differs")
    prior_rows = [json.loads(line) for line in PRIOR_LEDGER.read_text().splitlines() if line.strip()]
    completions = [row for row in prior_rows if row.get("event") == "completed"]
    if (
        len(prior_rows) != 15
        or len(completions) != 7
        or [row.get("status") for row in completions] != ["accepted"] * 6 + ["failed"]
    ):
        raise QualificationError("terminal qualification lineage differs")
    prompt = packet.PROMPT.read_bytes()
    expected_prompt = packet.sealed_bytes("scoring/scorer-prompt.txt") + qwen_route.FORMAT_SUFFIX
    if packet.PROMPT.is_symlink() or prompt != expected_prompt:
        raise QualificationError("format-only scorer prompt differs")
    sources = (
        "v3_qualification_successor.py",
        "v3_qualification_successor_schedule.py",
        "v3_qualification_successor_packet.py",
        "v3_qualification_successor_reduce.py",
        "v3_runner_version_successor.py",
        "v3_controls_successor.py",
        "v3_codex_format_route.py",
        "v3_qwen_5000_format_route.py",
        "scorer_route_check.py",
        "quota_adapter_v3.py",
    )
    return {
        "schema": 1,
        "record_type": "p3_v3_qualification_successor_seal",
        "scope": ["qualification"],
        "status": "offline_candidate_pending_owner_acceptance",
        "provider_calls_started": 0,
        "opening_codex_tokens": OPENING,
        "codex_limit_tokens": LIMIT,
        "five_hour_stop_percent": 80,
        "weekly_stop_percent": 90,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "subject_input_cap": SUBJECT_INPUT_CAP,
        "scorer_input_cap": SCORER_INPUT_CAP,
        "scorer_output_settings": {"codex": 1000, "qwen": QWEN_OUTPUT_SETTING},
        "codex_subject_models": {"strongest": "gpt-6-astra", "mid": "gpt-5.6-luna"},
        "codex_scorer_model": "gpt-6-astra",
        "codex_effort": "medium",
        "qwen_model": "qwen3.8-27b",
        "qwen_thinking": "provider default retained",
        "codex_cli_version": "codex-cli 0.162.1",
        "qwen_cli_version": "0.24.7",
        "codex_executable": str(CODEX),
        "codex_executable_sha256": sha(CODEX),
        "account_id_sha256": ACCOUNT_ID_SHA,
        "proposal_sha256": sha(PROPOSAL),
        "packet_seal_sha256": sha(schedule.PACKET_SEAL),
        "schedule_sha256": sha(schedule.SCHEDULE),
        "terminal_qualification_seal_sha256": sha(HERE / "runs/v3-qualification-operational-seal-v1.json"),
        "terminal_qualification_ledger_sha256": sha(PRIOR_LEDGER),
        "terminal_qualification_review_sha256": sha(HERE.parents[1] / "reviews/a22-p3-v3-qualification-attempt.md"),
        "codex_format_seal_sha256": sha(codex_route.SEAL),
        "codex_format_approval_sha256": sha(codex_route.APPROVAL),
        "codex_format_manifest_sha256": sha(HERE / "runs/v3-codex-format-route-evidence/manifest.json"),
        "codex_format_outcome_sha256": sha(HERE / "runs/v3-codex-format-route-evidence/outcome.json"),
        "qwen_format_seal_sha256": sha(qwen_route.SEAL),
        "qwen_format_approval_sha256": sha(qwen_route.APPROVAL),
        "qwen_format_outcome_sha256": sha(qwen_route.RUNTIME / "outcome.json"),
        "format_prompt_sha256": sha(packet.PROMPT),
        "source_sha256": {name: sha(HERE / name) for name in sources},
        "regression_sha256": sha(HERE.parents[1] / "tests/test_a22_p3_v3_qualification_successor.py"),
        "runtime_root": str(RUNTIME),
        "planned_calls": TOTAL_CALLS,
    }


def verify_seal() -> dict[str, Any]:
    actual = read(SEAL)
    if actual != seal_body():
        raise QualificationError("qualification seal is stale or malformed")
    return actual


def approval_template() -> dict[str, Any]:
    return {
        "schema": 1,
        "record_type": "p3_v3_qualification_successor_owner_approval",
        "operational_seal_sha256": sha(SEAL),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
        "preflight_sha256": None,
        "acceptance_basis": None,
    }


def verify_approval(*, dispatch: bool) -> None:
    actual = read(APPROVAL)
    template = approval_template()
    if not dispatch and actual == template:
        return
    expected = {
        **template,
        "owner_accepted": True,
        "dispatch_allowed": True,
        "authorized_phases": ["qualification"],
        "named_stop_operator": "owner (current chat session)",
        "preflight_sha256": sha(PREFLIGHT),
        "acceptance_basis": "owner explicitly accepted the exact qualification successor package in this chat",
    }
    if actual != expected:
        raise QualificationError("exact qualification approval is absent")


def preflight() -> dict[str, Any]:
    verify_seal()
    verify_approval(dispatch=False)
    call_plan()
    if RUNTIME.exists() or RUNTIME.is_symlink() or RUNTIME.resolve() == REPO or REPO in RUNTIME.resolve().parents:
        raise QualificationError("qualification runtime is used or inside the repository")
    if not AUTH.is_file() or AUTH.is_symlink() or stat.S_IMODE(AUTH.stat().st_mode) & 0o077:
        raise QualificationError("private Codex auth source unavailable")
    version = subprocess.run([str(CODEX), "--version"], capture_output=True, text=True, check=False, timeout=10)
    if version.returncode or version.stdout.strip() != "codex-cli 0.162.1":
        raise QualificationError("pinned Codex CLI is unavailable")
    qwen = shutil.which("qwen")
    if not qwen:
        raise QualificationError("Qwen CLI unavailable")
    qversion = subprocess.run([qwen, "--version"], capture_output=True, text=True, check=False, timeout=10)
    if qversion.returncode or not scorer._version_matches(qversion.stdout, "0.24.7"):
        raise QualificationError("Qwen CLI version differs")
    gateway, overlay, meta = qwen_route.qwen_settings()
    parsed = urlsplit(gateway)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise QualificationError("Qwen gateway differs from controlled route")
    if (
        meta.get("thinking_override") != "omitted; provider default retained"
        or overlay["modelProviders"]["openai"][0]["generationConfig"]["maxRetries"] != 0
        or overlay["modelProviders"]["openai"][0]["generationConfig"]["samplingParams"]["max_tokens"]
        != QWEN_OUTPUT_SETTING
    ):
        raise QualificationError("Qwen default-thinking/no-retry configuration differs")
    return {
        "status": "PASSED_OFFLINE_QUALIFICATION_SUCCESSOR_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "provider_calls": 0,
        "dispatch_allowed": False,
        "planned_calls": TOTAL_CALLS,
        "opening_codex_tokens": OPENING,
    }


def _header() -> dict[str, Any]:
    return {
        "record_type": "p3_v3_qualification_ledger",
        "schema": 1,
        "seal_sha256": sha(SEAL),
        "approval_sha256": sha(APPROVAL),
        "opening_codex_tokens": OPENING,
        "planned_calls": TOTAL_CALLS,
    }


def _rows() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    if LEDGER.is_symlink() or stat.S_IMODE(LEDGER.stat().st_mode) != 0o600:
        raise QualificationError("qualification ledger is linked or nonprivate")
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines()]
    if not rows or rows[0] != _header():
        raise QualificationError("qualification ledger header differs")
    previous = digest(rows[0])
    for sequence, row in enumerate(rows[1:], 1):
        body = {key: value for key, value in row.items() if key != "event_sha256"}
        if (
            row.get("seq") != sequence
            or row.get("previous_sha256") != previous
            or row.get("event_sha256") != digest(body)
        ):
            raise QualificationError("qualification ledger hash chain differs")
        previous = row["event_sha256"]
    return rows


def _append(event: dict[str, Any]) -> None:
    rows = _rows()
    body = {
        "seq": len(rows),
        "previous_sha256": digest(rows[0]) if len(rows) == 1 else rows[-1]["event_sha256"],
        **event,
    }
    row = {**body, "event_sha256": digest(body)}
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _state() -> tuple[int, int]:
    rows = _rows()
    plan = call_plan()
    events = rows[1:]
    if len(events) % 2 or len(events) > 2 * len(plan):
        raise QualificationError("unresolved reservation or excess calls")
    charged = OPENING
    for position in range(0, len(events), 2):
        reserved, completed = events[position : position + 2]
        target = plan[position // 2]
        if (
            reserved.get("event") != "reserved"
            or completed.get("event") != "completed"
            or reserved.get("call") != target
            or completed.get("call") != target
        ):
            raise QualificationError("call order or reservation identity differs")
        evidence = RUNTIME / "evidence" / target["call_id"]
        if completed.get("status") != "accepted" or not isinstance(completed.get("evidence_sha256"), str):
            raise QualificationError("prior call failed or has no bound evidence")
        result = read(evidence / "result.json")
        if sha(evidence / "result.json") != completed["evidence_sha256"] or result.get("call") != target:
            raise QualificationError("prior call evidence differs")
        files = result.get("evidence_sha256")
        if not isinstance(files, dict) or any(sha(evidence / name) != value for name, value in files.items()):
            raise QualificationError("prior call artifacts differ")
        if target["kind"] == "subject" and not {
            "source.stdout.txt",
            "source.events.json",
            "source.dispatch.json",
        } <= set(files):
            raise QualificationError("subject call evidence is incomplete")
        if target["kind"] == "scorer" and not {"packet.md", "stdout.raw", "events.json", "reply.tsv"} <= set(files):
            raise QualificationError("scorer call evidence is incomplete")
        if target["kind"] == "scorer" and (evidence / "reply.tsv").read_text(encoding="utf-8") != result.get("reply"):
            raise QualificationError("scorer reply differs from accepted evidence")
        if (
            target["kind"] == "subject"
            and target.get("turn") == 2
            and result.get("exchange_sha256") != sha(RUNTIME / "exchanges" / f"{target['run_id']}.json")
        ):
            raise QualificationError("subject exchange differs")
        usage = completed.get("usage")
        if usage != result.get("usage") or not isinstance(usage, dict):
            raise QualificationError("prior call usage differs")
        if target["route"] == "codex":
            charged += usage["input_tokens"] + usage["output_tokens"]
    return len(events) // 2, charged


def reduce_accepted() -> dict[str, Any]:
    """Reduce only the complete accepted, scheduled scorer evidence."""
    verify_seal()
    verify_approval(dispatch=True)
    count, charged = _state()
    if count != TOTAL_CALLS:
        raise QualificationError("qualification has fewer than 128 accepted calls")
    candidate = read(schedule.SCHEDULE)
    readings = {}
    for index, row in enumerate(candidate["cells"]):
        replies = {}
        for item in row["scorers"]:
            result = read(RUNTIME / "evidence" / item["call_id"] / "result.json")
            target = {
                "index": index,
                "kind": "scorer",
                "route": item["route"],
                "call_id": item["call_id"],
                "run_id": row["run_id"],
            }
            if result.get("call") != target or result.get("status") != "accepted":
                raise QualificationError("scorer reading does not bind its scheduled call")
            replies[item["route"]] = result["reply"]
        readings[row["run_id"]] = replies
    value = reduce_module.reduce(readings, candidate=candidate)
    return {
        **value,
        "qualification_ledger_sha256": sha(LEDGER),
        "charged_v3_codex_tokens": charged,
        "accepted_provider_calls": count,
        "operational_seal_sha256": sha(SEAL),
    }


def _prepare_codex_home(root: Path) -> tuple[Path, dict[str, str]]:
    home = root / "home"
    home.mkdir(mode=0o700, parents=True)
    write_new(home / "auth.json", AUTH.read_bytes())
    tmp = root / "tmp"
    tmp.mkdir(mode=0o700)
    return home, source._codex_child_environment(home, tmp)


def _call(step: dict[str, Any], charged: int) -> dict[str, Any]:
    row = read(schedule.SCHEDULE)["cells"][step["index"]]
    case = read(HERE / "cases" / f"{row['case']}.json")
    root = RUNTIME / "evidence" / step["call_id"]
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    scratch = root / "scratch"
    scratch.mkdir(mode=0o700)
    usage: dict[str, int] | None = None
    session_id = ""
    request_sha = ""
    if step["kind"] == "subject":
        home, environment = _prepare_codex_home(root) if step["turn"] == 1 else _existing_subject_home(row)
        prior = None if step["turn"] == 1 else read(RUNTIME / "evidence" / row["subject_call_ids"][0] / "result.json")
        if prior is not None:
            first_root = RUNTIME / "evidence" / row["subject_call_ids"][0]
            scratch = first_root / "scratch"
            session_id = prior["session_id"]
        prompt = case["subject"]["turn1"] if prior is None else source._second_prompt(case, prior["reply"])[2]
        model = "gpt-6-astra" if row["tier"] == "strongest" else "gpt-5.6-luna"
        command = controls._command(str(CODEX), scratch, "A", model, prompt, session_id or None)
        request_sha = sha_bytes(prompt.encode())
        cap = SUBJECT_INPUT_CAP
    else:
        exchange = read(RUNTIME / "exchanges" / f"{row['run_id']}.json")
        visible, request = packet.render(row, exchange)
        write_new(root / "packet.md", visible)
        request_sha = sha_bytes(request)
        cap = SCORER_INPUT_CAP
        if step["route"] == "codex":
            home, environment = _prepare_codex_home(root)
            command = scorer._codex_command(str(CODEX), scratch)
        else:
            home = None
            parent = os.environ.copy()
            gateway, overlay, meta = qwen_route.qwen_settings()
            parsed = urlsplit(gateway)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise QualificationError("Qwen gateway is malformed")
            if meta["thinking_override"] != "omitted; provider default retained":
                raise QualificationError("Qwen thinking override differs")
            write_json(root / "qwen-system-settings.json", overlay)
            session_id = str(uuid.uuid4())
            environment = scorer._child_environment("qwen", parent, auth_token=parent["LITE_LLM_AUTH_TOKEN"])
            environment.update(
                {
                    "QWEN_CODE_SYSTEM_SETTINGS_PATH": str(root / "qwen-system-settings.json"),
                    "QWEN_CODE_MAX_OUTPUT_TOKENS": str(QWEN_OUTPUT_SETTING),
                    "QWEN_CODE_UNATTENDED_RETRY": "0",
                }
            )
            command = scorer._qwen_command(shutil.which("qwen") or "", gateway, session_id)
    snapshot = None
    if step["route"] == "codex":
        snapshot = quota.read_quota_snapshot(codex_executable=str(CODEX), codex_home=home, environment=environment)
        quota.checkpoint_decision(snapshot)
        receipt = snapshot.get("account_limit_receipt", {})
        if receipt.get("account_id_sha256") != ACCOUNT_ID_SHA or receipt.get("codex_executable_sha256") != sha(CODEX):
            raise QualificationError("Codex quota account or executable differs")
        if charged + cap + (1000 if step["kind"] == "scorer" else 0) > LIMIT:
            raise QualificationError("V3 Codex ceiling blocks next call")
        write_json(root / "quota-before.json", snapshot)
    write_json(
        root / "prepared.json",
        {
            "call": step,
            "request_sha256": request_sha,
            "packet_sha256": sha(root / "packet.md") if step["kind"] == "scorer" else None,
            "seal_sha256": sha(SEAL),
        },
    )
    _append(
        {
            "event": "reserved",
            "call": step,
            "request_sha256": request_sha,
            "quota_sha256": sha(root / "quota-before.json") if snapshot else None,
        }
    )
    try:
        if step["kind"] == "subject":
            prefix = root / "source"
            events, _raw = source._invoke(
                command,
                cwd=scratch,
                codex_home=home,
                tmp=home.parent / "tmp",
                artifact_base=prefix,
                environment=environment,
            )
            usage = source.extract_usage(events)
            reply = source.assistant_reply(events)
            observed = source.thread_id(events)
            if session_id and observed != session_id:
                raise QualificationError("second subject turn changed Codex session")
            session_id = observed
            stderr = Path(f"{prefix}.stderr.txt").read_bytes()
            if source.has_tool_use(events) or controls._retry_markers(events, stderr):
                raise QualificationError("subject tool/retry/error marker observed")
            if usage["input_tokens"] > SUBJECT_INPUT_CAP:
                raise QualificationError("subject input cap exceeded")
            if step["turn"] == 2:
                _finish_exchange(row, case, home, scratch, session_id, usage, reply)
        else:
            process = scorer.invoke_one_provider_process(command, request, scratch, environment)
            secret = os.environ.get("LITE_LLM_AUTH_TOKEN", "") if step["route"] == "qwen" else ""
            stdout = scorer.secure_capture(process.stdout, secret)
            stderr = scorer.secure_capture(process.stderr, secret)
            write_new(root / "stdout.raw", stdout)
            write_new(root / "stderr.raw", stderr)
            events = scorer.parse_jsonl(stdout)
            write_json(root / "events.json", events)
            if step["route"] == "codex":
                usage = scorer.usage_from_events(events)
                ids = scorer.event_session_ids(events)
                if len(ids) != 1:
                    raise QualificationError("scorer Codex session is ambiguous")
                session_id = next(iter(ids))
                raw = _verify_scorer_rollout(home, session_id, scratch, usage)
                write_new(root / "rollout.jsonl", raw)
            else:
                if scorer.event_session_ids(events) != {session_id}:
                    raise QualificationError("Qwen scorer session differs")
                qwen = scorer.qwen_usage_record(
                    Path.home() / ".qwen/usage_record.jsonl", str(scratch), session_id, set()
                )
                usage = {"input_tokens": qwen["input_tokens"], "output_tokens": qwen["output_tokens"]}
                write_json(root / "qwen-usage.json", qwen)
            reply = scorer.final_text(events)
            write_new(root / "reply.tsv", reply.encode())
            scorer.validate_tsv(reply, row["packet_id"], row["element_ids"])
            if process.returncode or scorer.tool_markers(events) or scorer.cli_retry_error_markers(events, stderr):
                raise QualificationError("scorer process, tool or retry condition failed")
            if usage["input_tokens"] > SCORER_INPUT_CAP or usage["output_tokens"] > (
                1000 if step["route"] == "codex" else QWEN_OUTPUT_SETTING
            ):
                raise QualificationError("scorer observed token cap exceeded")
        evidence_names = (
            "prepared.json",
            "quota-before.json",
            "packet.md",
            "source.stdout.txt",
            "source.stderr.txt",
            "source.events.json",
            "source.dispatch.json",
            "stdout.raw",
            "stderr.raw",
            "events.json",
            "rollout.jsonl",
            "reply.tsv",
            "qwen-usage.json",
        )
        result = {
            "call": step,
            "status": "accepted",
            "usage": usage,
            "session_id": session_id,
            "reply": reply,
            "request_sha256": request_sha,
            "exchange_sha256": sha(RUNTIME / "exchanges" / f"{row['run_id']}.json")
            if step["kind"] == "subject" and step["turn"] == 2
            else None,
            "evidence_sha256": {name: sha(root / name) for name in evidence_names if (root / name).is_file()},
        }
        write_json(root / "result.json", result)
        _append(
            {
                "event": "completed",
                "call": step,
                "status": "accepted",
                "usage": usage,
                "evidence_sha256": sha(root / "result.json"),
            }
        )
        return {
            "status": "accepted_but_ceiling_stop"
            if step["route"] == "codex" and charged + sum(usage.values()) > LIMIT
            else "accepted",
            "call": step,
            "usage": usage,
        }
    except BaseException as exc:
        write_json(
            root / "failure.json",
            {"status": "terminal", "failure_code": type(exc).__name__, "retry_authorized": False, "usage": usage},
        )
        _append(
            {
                "event": "completed",
                "call": step,
                "status": "failed",
                "usage": usage,
                "evidence_sha256": sha(root / "failure.json"),
            }
        )
        raise


def _existing_subject_home(row: dict[str, Any]) -> tuple[Path, dict[str, str]]:
    first = RUNTIME / "evidence" / row["subject_call_ids"][0]
    home = first / "home"
    if home.is_symlink() or sha(home / "auth.json") != sha(AUTH):
        raise QualificationError("subject Codex home differs between turns")
    return home, source._codex_child_environment(home, first / "tmp")


def _finish_exchange(
    row: dict[str, Any],
    case: dict[str, Any],
    home: Path,
    scratch: Path,
    session: str,
    second_usage: dict[str, int],
    second_reply: str,
) -> None:
    first = read(RUNTIME / "evidence" / row["subject_call_ids"][0] / "result.json")
    turns = [
        {"user": case["subject"]["turn1"], "assistant": first["reply"]},
        {"user": source._second_prompt(case, first["reply"])[2], "assistant": second_reply},
    ]
    controls._verify_rollout(
        home,
        session,
        "gpt-6-astra" if row["tier"] == "strongest" else "gpt-5.6-luna",
        "A",
        scratch,
        [first["usage"], second_usage],
    )
    exchange = {"run_id": row["run_id"], "turns": turns}
    packet.render(row, exchange)
    write_json(RUNTIME / "exchanges" / f"{row['run_id']}.json", exchange)


def _verify_scorer_rollout(home: Path, session: str, scratch: Path, usage: dict[str, int]) -> bytes:
    helper = codex_route.old_route._helper()
    return codex_route._rollout(home, session, scratch, usage, helper)


def advance() -> dict[str, Any]:
    verify_seal()
    verify_approval(dispatch=True)
    report = read(PREFLIGHT)
    if report != {
        "status": "PASSED_OFFLINE_QUALIFICATION_SUCCESSOR_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "provider_calls": 0,
        "dispatch_allowed": False,
        "planned_calls": TOTAL_CALLS,
        "opening_codex_tokens": OPENING,
    }:
        raise QualificationError("offline preflight does not bind this seal")
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = os.open(RUNTIME / "qualification.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        if not LEDGER.exists():
            write_new(LEDGER, (json.dumps(_header(), sort_keys=True) + "\n").encode())
        index, charged = _state()
        if index == TOTAL_CALLS:
            return {"status": "qualification_calls_complete", "charged_codex_tokens": charged}
        if charged >= LIMIT:
            raise QualificationError("completed Codex usage reached the V3 ceiling")
        result = _call(call_plan()[index], charged)
        result["completed_calls"] = index + 1
        result["charged_codex_tokens"] = charged + (
            sum(result["usage"].values()) if result["call"]["route"] == "codex" else 0
        )
        return result
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "advance", "status", "reduce"))
    args = parser.parse_args()
    if args.action == "preflight":
        print(json.dumps(preflight(), sort_keys=True))
    elif args.action == "status":
        verify_seal()
        index, charged = _state() if LEDGER.exists() else (0, OPENING)
        print(
            json.dumps(
                {"completed_calls": index, "planned_calls": TOTAL_CALLS, "charged_codex_tokens": charged},
                sort_keys=True,
            )
        )
    elif args.action == "reduce":
        print(json.dumps(reduce_accepted(), sort_keys=True))
    else:
        print(json.dumps(advance(), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "QUALIFICATION_STOP", "reason_class": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2) from None
