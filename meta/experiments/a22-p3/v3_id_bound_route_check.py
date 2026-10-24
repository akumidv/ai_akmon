#!/usr/bin/env python3
"""Run one sealed, terminal scorer-format route call at a time."""

# ruff: noqa: BLE001 C901 D103 PLR0912 PLR0915 PLR2004 S108
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
import v3_qualification_id_bound as qualification
import v3_qwen_5000_format_route as qwen_route
import v3_scorer_id_binding as identity

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2].resolve()
PROPOSAL = HERE / "V3_ID_BOUND_ROUTE_PROPOSAL.md"
PLAN = HERE / "runs/v3-id-bound-route-plan-v1.json"
SEAL = HERE / "runs/v3-id-bound-route-seal-v1.json"
PREFLIGHT = HERE / "runs/v3-id-bound-route-preflight-v1.json"
APPROVAL = HERE / "runs/v3-id-bound-route-approval-v1.json"
OUTCOMES = qualification.NEW_ROUTE_OUTCOMES
RUNTIME = Path("/tmp/a22-p3-v3-id-bound-route-runtime")
LEDGER = RUNTIME / "route-events.jsonl"
PACKET_ROOT = Path("/tmp/a22-p3-v3-qualification-successor-runtime/evidence/g225a6ea21aeb6b0df81a151977b43f20")
PACKET = PACKET_ROOT / "packet.md"
PREDECESSOR_LEDGER = qualification.PRIOR_LEDGER
PACKET_ID = "gf04a4422bf50dd1f"
ELEMENTS = ["E1", "E2", "E3", "E4"]
OPENING = 559_835
LIMIT = 5_000_000
ROUTES = ("qwen", "codex")


class RouteError(ValueError):
    """The sealed route or its evidence failed."""


def sha(path: Path) -> str:
    return qualification.sha(path)


def read(path: Path) -> Any:
    return qualification.read(path)


def write_json(path: Path, value: Any) -> None:
    qualification.write_json(path, value)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prompt_and_packet() -> tuple[bytes, bytes]:
    prompt = qualification.packet.PROMPT.read_bytes()
    expected = (
        qualification.packet.sealed_bytes("scoring/scorer-prompt.txt").split(
            b"Output tab-separated rows with exactly:\n", 1
        )[0]
        + qualification.packet.FORMAT_INSTRUCTIONS
    )
    if qualification.packet.PROMPT.is_symlink() or prompt != expected:
        raise RouteError("new prompt differs from frozen rubric")
    predecessor = read(PACKET_ROOT / "prepared.json")
    old_schedule = read(HERE / "runs/v3-qualification-successor-schedule-v1.json")
    old_row = next(
        (row for row in old_schedule["cells"] if row["run_id"] == predecessor.get("call", {}).get("run_id")),
        None,
    )
    packet = PACKET.read_bytes()
    if (
        PACKET.is_symlink()
        or old_row is None
        or old_row["packet_id"] != PACKET_ID
        or old_row["element_ids"] != ELEMENTS
        or predecessor.get("packet_sha256") != sha_bytes(packet)
        or predecessor.get("call", {}).get("call_id") != PACKET_ROOT.name
        or f"{PACKET_ID}".encode() not in packet
    ):
        raise RouteError("terminal predecessor packet differs")
    return prompt, packet


def plan() -> dict[str, Any]:
    value = read(PLAN)
    historical = qualification.schedule.prior_ids() | set(read(qualification.schedule.OLD_MAP))
    for path in qualification.schedule.PRIOR_SCHEDULES:
        previous = read(path)
        for row in previous["cells"]:
            historical.update((row["run_id"], row["subject_attempt_id"], row["packet_id"]))
            historical.update(row["subject_call_ids"])
            historical.update(item["call_id"] for item in row["scorers"])
    historical.update(
        item
        for row in read(qualification.schedule.SCHEDULE)["cells"]
        for item in (row["run_id"], row["subject_attempt_id"], row["packet_id"], *row["subject_call_ids"])
    )
    historical.update(
        item["call_id"] for row in read(qualification.schedule.SCHEDULE)["cells"] for item in row["scorers"]
    )
    calls = value.get("calls")
    if (
        value.get("record_type") != "p3_v3_id_bound_route_plan"
        or value.get("packet_sha256") != sha(PACKET)
        or value.get("prompt_sha256") != sha(qualification.packet.PROMPT)
        or not isinstance(calls, list)
        or len(calls) != 2
        or [row.get("route") for row in calls] != list(ROUTES)
        or len({row.get("call_id") for row in calls}) != 2
        or any(
            not isinstance(row.get("call_id"), str)
            or len(row["call_id"]) != 33
            or not row["call_id"].startswith("g")
            or any(character not in "0123456789abcdef" for character in row["call_id"][1:])
            or row["call_id"] in historical
            for row in calls
        )
    ):
        raise RouteError("frozen route plan differs")
    return value


def seal_body() -> dict[str, Any]:
    prompt_and_packet()
    plan()
    predecessor_rows = [json.loads(line) for line in PREDECESSOR_LEDGER.read_text().splitlines() if line.strip()]
    if (
        len(predecessor_rows) != 63
        or predecessor_rows[-1].get("event") != "completed"
        or predecessor_rows[-1].get("status") != "failed"
        or predecessor_rows[-1].get("call", {}).get("call_id") != PACKET_ROOT.name
        or predecessor_rows[-1].get("usage") != {"input_tokens": 12_779, "output_tokens": 558}
    ):
        raise RouteError("terminal qualification predecessor differs")
    gateway, overlay, meta = qwen_route.qwen_settings()
    if (
        meta.get("thinking_override") != "omitted; provider default retained"
        or overlay["modelProviders"]["openai"][0]["generationConfig"]["maxRetries"] != 0
        or overlay["modelProviders"]["openai"][0]["generationConfig"]["samplingParams"]["max_tokens"] != 5000
    ):
        raise RouteError("Qwen settings differ")
    return {
        "schema": 1,
        "record_type": "p3_v3_id_bound_route_seal",
        "status": "offline_candidate_pending_owner_acceptance",
        "scope": ["id_bound_route_checks"],
        "provider_calls_started": 0,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "opening_codex_tokens": OPENING,
        "codex_limit_tokens": LIMIT,
        "codex_five_hour_stop_percent": 80,
        "codex_weekly_stop_percent": 90,
        "codex_cli_version": "codex-cli 0.162.1",
        "codex_model": "gpt-6-astra",
        "codex_effort": "medium",
        "codex_executable_sha256": sha(qualification.CODEX),
        "account_id_sha256": qualification.ACCOUNT_ID_SHA,
        "qwen_cli_version": "0.24.7",
        "qwen_model": "qwen3.8-27b",
        "qwen_thinking": "provider default retained",
        "qwen_output_setting": 5000,
        "qwen_executable_sha256": sha(Path(shutil.which("qwen") or "/missing/qwen").resolve(strict=True)),
        "qwen_gateway_sha256": sha_bytes(gateway.encode()),
        "packet_id": PACKET_ID,
        "element_ids": ELEMENTS,
        "packet_sha256": sha(PACKET),
        "prompt_sha256": sha(qualification.packet.PROMPT),
        "proposal_sha256": sha(PROPOSAL),
        "plan_sha256": sha(PLAN),
        "predecessor_seal_sha256": sha(HERE / "runs/v3-qualification-successor-seal-v1.json"),
        "predecessor_schedule_sha256": sha(HERE / "runs/v3-qualification-successor-schedule-v1.json"),
        "predecessor_ledger_sha256": sha(PREDECESSOR_LEDGER),
        "predecessor_failure_sha256": sha(PACKET_ROOT / "failure.json"),
        "source_sha256": {
            name: sha(HERE / name)
            for name in (
                "v3_id_bound_route_check.py",
                "v3_scorer_id_binding.py",
                "v3_qualification_id_bound.py",
                "v3_qualification_id_bound_packet.py",
                "scorer_route_check.py",
                "quota_adapter_v3.py",
            )
        },
        "regression_sha256": sha(HERE.parents[1] / "tests/test_a22_p3_v3_id_bound_route.py"),
        "runtime_root": str(RUNTIME),
    }


def verify_seal() -> None:
    if read(SEAL) != seal_body():
        raise RouteError("route seal differs")


def approval_template() -> dict[str, Any]:
    return {
        "schema": 1,
        "record_type": "p3_v3_id_bound_route_approval",
        "operational_seal_sha256": sha(SEAL),
        "preflight_sha256": sha(PREFLIGHT),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
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
        "authorized_phases": ["id_bound_route_checks"],
        "named_stop_operator": "owner (current chat session)",
        "acceptance_basis": "owner separately accepted the exact identity-bound route package in this chat",
    }
    if actual != expected:
        raise RouteError("exact route-check approval is absent")


def preflight() -> dict[str, Any]:
    verify_seal()
    if RUNTIME.exists() or RUNTIME.is_symlink() or REPO in RUNTIME.resolve().parents:
        raise RouteError("route runtime is used or inside repository")
    if not os.environ.get("LITE_LLM_AUTH_TOKEN"):
        raise RouteError("Qwen credential unavailable")
    if not qualification.AUTH.is_file() or qualification.AUTH.is_symlink():
        raise RouteError("Codex auth source unavailable")
    if stat.S_IMODE(qualification.AUTH.stat().st_mode) & 0o077:
        raise RouteError("Codex auth source is not private")
    cv = subprocess.run(
        [str(qualification.CODEX), "--version"], capture_output=True, text=True, timeout=10, check=False
    )
    qwen = shutil.which("qwen")
    if not qwen:
        raise RouteError("Qwen executable unavailable")
    qv = subprocess.run([qwen, "--version"], capture_output=True, text=True, timeout=10, check=False)
    if (
        cv.returncode
        or cv.stdout.strip() != "codex-cli 0.162.1"
        or qv.returncode
        or not scorer._version_matches(qv.stdout, "0.24.7")
    ):
        raise RouteError("pinned CLI version differs")
    return {
        "status": "PASSED_OFFLINE_ID_BOUND_ROUTE_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "provider_calls": 0,
        "dispatch_allowed": False,
        "planned_calls": 2,
        "opening_codex_tokens": OPENING,
    }


def _header() -> dict[str, Any]:
    return {
        "record_type": "p3_v3_id_bound_route_ledger",
        "seal_sha256": sha(SEAL),
        "approval_sha256": sha(APPROVAL),
        "opening_codex_tokens": OPENING,
    }


def _events() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    rows = [json.loads(line) for line in LEDGER.read_text().splitlines()]
    if not rows or rows[0] != _header():
        raise RouteError("route ledger header differs")
    if len(rows) > 5 or len(rows[1:]) % 2:
        raise RouteError("unresolved or excess route reservation")
    for index, call in enumerate(plan()["calls"][: (len(rows) - 1) // 2]):
        reserved, completed = rows[1 + 2 * index : 3 + 2 * index]
        if (
            reserved.get("event") != "reserved"
            or completed.get("event") != "completed"
            or reserved.get("call") != call
            or completed.get("call") != call
        ):
            raise RouteError("route ledger order differs")
        if completed.get("status") != "passed_unscored":
            raise RouteError("terminal route failure blocks next call")
        outcome = read(OUTCOMES[call["route"]])
        root = RUNTIME / call["call_id"]
        prompt, packet = prompt_and_packet()
        request = scorer.make_request(prompt, packet)
        prepared = read(root / "prepared.json")
        if (root / "reply.raw.tsv").is_symlink() or (root / "reply.tsv").is_symlink():
            raise RouteError("route reply evidence is linked")
        raw = (root / "reply.raw.tsv").read_text(encoding="utf-8")
        canonical = (root / "reply.tsv").read_text(encoding="utf-8")
        expected_evidence = {
            name: sha(root / name)
            for name in (
                "prepared.json",
                "stdout.raw",
                "stderr.raw",
                "events.json",
                "reply.raw.tsv",
                "reply.tsv",
                *(
                    ("usage.json", "qwen-settings.json")
                    if call["route"] == "qwen"
                    else ("quota-before.json", "rollout.jsonl")
                ),
            )
        }
        if (
            reserved.get("request_sha256") != sha_bytes(request)
            or sha(OUTCOMES[call["route"]]) != completed.get("outcome_sha256")
            or read(root / "outcome.json") != outcome
            or outcome.get("call_id") != call["call_id"]
            or outcome.get("route") != call["route"]
            or outcome.get("status") != "passed_unscored"
            or outcome.get("scored_p3") is not False
            or outcome.get("qualification_data") is not False
            or outcome.get("retry_authorized") is not False
            or outcome.get("failure_class") is not None
            or outcome.get("seal_sha256") != sha(SEAL)
            or outcome.get("usage") != completed.get("usage")
            or outcome.get("evidence_sha256") != expected_evidence
            or prepared.get("call") != call
            or prepared.get("seal_sha256") != sha(SEAL)
            or prepared.get("request_sha256") != sha_bytes(request)
            or prepared.get("packet_sha256") != sha_bytes(packet)
            or prepared.get("prompt_sha256") != sha_bytes(prompt)
            or outcome.get("raw_reply_sha256") != sha_bytes(raw.encode())
            or outcome.get("canonical_reply_sha256") != sha_bytes(canonical.encode())
            or identity.canonicalize(raw, PACKET_ID, ELEMENTS) != canonical
        ):
            raise RouteError("route outcome differs from ledger")
        scorer.validate_tsv(canonical, PACKET_ID, ELEMENTS)
        events = read(root / "events.json")
        if scorer.parse_jsonl((root / "stdout.raw").read_bytes()) != events:
            raise RouteError("route event capture differs")
        if call["route"] == "qwen":
            usage_record = read(root / "usage.json")
            if (
                usage_record.get("model_id") != "qwen3.8-27b"
                or usage_record.get("requests") != 1
                or usage_record.get("tool_calls") != 0
                or usage_record.get("input_tokens") != outcome["usage"]["input_tokens"]
                or usage_record.get("output_tokens") != outcome["usage"]["output_tokens"]
                or scorer.event_session_ids(events) != {outcome.get("session_id")}
            ):
                raise RouteError("Qwen usage or session evidence differs")
        elif scorer.usage_from_events(events) != outcome["usage"] or scorer.event_session_ids(events) != {
            outcome.get("session_id")
        }:
            raise RouteError("Codex usage or session evidence differs")
    return rows


def _append(event: dict[str, Any]) -> None:
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def advance() -> dict[str, Any]:
    verify_seal()
    if read(PREFLIGHT) != preflight_record():
        raise RouteError("offline route preflight differs")
    verify_approval(dispatch=True)
    if (
        RUNTIME.is_symlink()
        or REPO in RUNTIME.resolve().parents
        or (
            RUNTIME.exists()
            and (
                stat.S_IMODE(RUNTIME.stat().st_mode) != 0o700
                or RUNTIME.stat().st_uid != os.getuid()
                or not LEDGER.is_file()
                or LEDGER.is_symlink()
            )
        )
    ):
        raise RouteError("route runtime is linked or nonprivate")
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    lock = os.open(RUNTIME / "route.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        if not LEDGER.exists():
            qualification.write_new(LEDGER, (json.dumps(_header(), sort_keys=True) + "\n").encode())
        rows = _events()
        index = (len(rows) - 1) // 2
        if index >= 2:
            return {"status": "route_checks_complete"}
        call = plan()["calls"][index]
        if OUTCOMES[call["route"]].exists() or OUTCOMES[call["route"]].is_symlink():
            raise RouteError("route outcome path is already used")
        return _one_call(call)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def preflight_record() -> dict[str, Any]:
    return {
        "status": "PASSED_OFFLINE_ID_BOUND_ROUTE_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "provider_calls": 0,
        "dispatch_allowed": False,
        "planned_calls": 2,
        "opening_codex_tokens": OPENING,
    }


def _one_call(call: dict[str, str]) -> dict[str, Any]:
    route = call["route"]
    if route == "qwen" and not os.environ.get("LITE_LLM_AUTH_TOKEN"):
        raise RouteError("Qwen credential unavailable")
    prompt, packet = prompt_and_packet()
    request = scorer.make_request(prompt, packet)
    root = RUNTIME / call["call_id"]
    root.mkdir(mode=0o700, exist_ok=False)
    scratch = root / "scratch"
    scratch.mkdir(mode=0o700)
    session_id = str(uuid.uuid4()) if route == "qwen" else ""
    usage: dict[str, int] | None = None
    if route == "qwen":
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
            raise RouteError("Qwen gateway differs")
        write_json(root / "qwen-settings.json", overlay)
        environment = scorer._child_environment("qwen", os.environ.copy(), auth_token=os.environ["LITE_LLM_AUTH_TOKEN"])
        environment.update(
            {
                "QWEN_CODE_SYSTEM_SETTINGS_PATH": str(root / "qwen-settings.json"),
                "QWEN_CODE_MAX_OUTPUT_TOKENS": "5000",
                "QWEN_CODE_UNATTENDED_RETRY": "0",
            }
        )
        command = scorer._qwen_command(shutil.which("qwen") or "", gateway, session_id)
    else:
        home, environment = qualification._prepare_codex_home(root)
        snapshot = quota.read_quota_snapshot(
            codex_executable=str(qualification.CODEX), codex_home=home, environment=environment
        )
        quota.checkpoint_decision(snapshot)
        receipt = snapshot.get("account_limit_receipt", {})
        if receipt.get("account_id_sha256") != qualification.ACCOUNT_ID_SHA or receipt.get(
            "codex_executable_sha256"
        ) != sha(qualification.CODEX):
            raise RouteError("Codex account or executable differs")
        if OPENING + 20_000 + 1_000 > LIMIT:
            raise RouteError("Codex aggregate ceiling blocks route")
        write_json(root / "quota-before.json", snapshot)
        command = scorer._codex_command(str(qualification.CODEX), scratch)
    write_json(
        root / "prepared.json",
        {
            "call": call,
            "seal_sha256": sha(SEAL),
            "request_sha256": sha_bytes(request),
            "packet_sha256": sha_bytes(packet),
            "prompt_sha256": sha_bytes(prompt),
            "session_id": session_id or None,
            "qwen_settings": meta if route == "qwen" else None,
        },
    )
    _append({"event": "reserved", "call": call, "request_sha256": sha_bytes(request)})
    status = "failed"
    failure = "provider_call_incomplete"
    raw_sha = None
    canonical_sha = None
    try:
        process = scorer.invoke_one_provider_process(command, request, scratch, environment)
        secret = os.environ.get("LITE_LLM_AUTH_TOKEN", "") if route == "qwen" else ""
        stdout = scorer.secure_capture(process.stdout, secret)
        stderr = scorer.secure_capture(process.stderr, secret)
        qualification.write_new(root / "stdout.raw", stdout)
        qualification.write_new(root / "stderr.raw", stderr)
        events = scorer.parse_jsonl(stdout)
        write_json(root / "events.json", events)
        if route == "qwen":
            if scorer.event_session_ids(events) != {session_id}:
                raise RouteError("Qwen session differs")
            record = scorer.qwen_usage_record(Path.home() / ".qwen/usage_record.jsonl", str(scratch), session_id, set())
            usage = {"input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"]}
            write_json(root / "usage.json", record)
            if record.get("model_id") != "qwen3.8-27b":
                raise RouteError("Qwen model differs")
        else:
            usage = scorer.usage_from_events(events)
            sessions = scorer.event_session_ids(events)
            if len(sessions) != 1:
                raise RouteError("Codex session is ambiguous")
            session_id = next(iter(sessions))
            rollout = qualification._verify_scorer_rollout(home, session_id, scratch, usage)
            qualification.write_new(root / "rollout.jsonl", rollout)
        raw = scorer.final_text(events)
        qualification.write_new(root / "reply.raw.tsv", raw.encode())
        raw_sha = sha(root / "reply.raw.tsv")
        canonical = identity.canonicalize(raw, PACKET_ID, ELEMENTS)
        qualification.write_new(root / "reply.tsv", canonical.encode())
        canonical_sha = sha(root / "reply.tsv")
        scorer.validate_tsv(canonical, PACKET_ID, ELEMENTS)
        if process.returncode or scorer.tool_markers(events) or scorer.cli_retry_error_markers(events, stderr):
            raise RouteError("process, tool or visible retry condition failed")
        if usage["input_tokens"] > 20_000 or usage["output_tokens"] > (5_000 if route == "qwen" else 1_000):
            raise RouteError("scorer observed token setting exceeded")
        status = "passed_unscored"
        failure = ""
    except Exception as exc:
        failure = type(exc).__name__
    outcome = {
        "record_type": "p3_v3_id_bound_scorer_route_outcome",
        "route": route,
        "status": status,
        "scored_p3": False,
        "qualification_data": False,
        "call_id": call["call_id"],
        "session_id": session_id or None,
        "seal_sha256": sha(SEAL),
        "request_sha256": sha_bytes(request),
        "packet_sha256": sha_bytes(packet),
        "prompt_sha256": sha_bytes(prompt),
        "raw_reply_sha256": raw_sha,
        "canonical_reply_sha256": canonical_sha,
        "evidence_sha256": {
            name: sha(root / name)
            for name in (
                "prepared.json",
                "stdout.raw",
                "stderr.raw",
                "events.json",
                "reply.raw.tsv",
                "reply.tsv",
                "usage.json",
                "qwen-settings.json",
                "quota-before.json",
                "rollout.jsonl",
            )
            if (root / name).is_file()
        },
        "usage": usage,
        "failure_class": failure or None,
        "retry_authorized": False,
    }
    write_json(root / "outcome.json", outcome)
    write_json(OUTCOMES[route], outcome)
    _append(
        {"event": "completed", "call": call, "status": status, "usage": usage, "outcome_sha256": sha(OUTCOMES[route])}
    )
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("prepare-plan", "seal", "preflight", "approval-template", "advance", "status")
    )
    action = parser.parse_args().action
    if action == "prepare-plan":
        prompt, packet = prompt_and_packet()
        calls = [{"route": route, "call_id": "g" + uuid.uuid4().hex} for route in ROUTES]
        write_json(
            PLAN,
            {
                "record_type": "p3_v3_id_bound_route_plan",
                "packet_sha256": sha_bytes(packet),
                "prompt_sha256": sha_bytes(prompt),
                "calls": calls,
            },
        )
        result = {"status": "PLAN_PREPARED", "plan_sha256": sha(PLAN)}
    elif action == "seal":
        write_json(SEAL, seal_body())
        result = {"status": "SEALED_OFFLINE", "seal_sha256": sha(SEAL)}
    elif action == "preflight":
        result = preflight()
        write_json(PREFLIGHT, result)
    elif action == "approval-template":
        result = approval_template()
        write_json(APPROVAL, result)
    elif action == "advance":
        result = advance()
    else:
        result = read(OUTCOMES["codex"]) if OUTCOMES["codex"].exists() else {"status": "NOT_COMPLETE"}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "ROUTE_STOP", "reason_class": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2) from None
