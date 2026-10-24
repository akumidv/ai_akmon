#!/usr/bin/env python3
"""Carry forward 95 accepted A calls and replace a second invalid scorer."""

# ruff: noqa: D103 PERF401 PLR2004 S108
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scorer_route_check as scorer
import v3_qualification_headroom as prior
import v3_qualification_technical_substitution_v2 as previous

HERE = Path(__file__).resolve().parent.parent
RUNS = HERE / "runs"
PROPOSAL = HERE / "V3_A_SECOND_TECHNICAL_SUBSTITUTION_PROPOSAL.md"
PLAN = RUNS / "v3-a-second-technical-substitution-plan-v1.json"
SCHEDULE = RUNS / "v3-a-second-technical-substitution-schedule-v1.json"
SEAL = RUNS / "v3-a-second-technical-substitution-seal-v1.json"
PREFLIGHT = RUNS / "v3-a-second-technical-substitution-preflight-v1.json"
APPROVAL = RUNS / "v3-a-second-technical-substitution-approval-v1.json"
RUNTIME = Path("/tmp/a22-p3-v3-a-second-technical-substitution-v1-runtime")
LEDGER = RUNTIME / "qualification-events.jsonl"
ACCEPTED_PREFIX = 95
NEW_CALLS = 33
OPENING = 1_569_103
ORIGINAL_BASE = {
    "runtime": prior.RUNTIME,
    "ledger": prior.LEDGER,
    "seal": prior.SEAL,
    "approval": prior.APPROVAL,
    "preflight": prior.PREFLIGHT,
    "opening": prior.OPENING,
    "total_calls": prior.TOTAL_CALLS,
    "schedule": prior.schedule.SCHEDULE,
    "verify_schedule": prior.schedule.verify_schedule,
    "call_plan": prior.call_plan,
    "packet_render": prior.packet.render,
}


class SubstitutionError(ValueError):
    """A carried result, replacement, or new terminal call differs."""


def sha(path: Path) -> str:
    return prior.sha(path)


def read(path: Path) -> Any:
    return prior.read(path)


def _old_schedule() -> dict[str, Any]:
    old = read(previous.SCHEDULE)
    previous.verify_schedule(old)
    return old


def verify_schedule(candidate: dict[str, Any]) -> None:
    """Allow only one new call ID; all cells, packets and other IDs stay frozen."""
    old = _old_schedule()
    plan = read(PLAN)
    if plan.get("replaced_position") != 95 or plan.get("old_call_id") != "g3b83b6b857d3f34ef081f2a39f0215a6":
        raise SubstitutionError("replacement target differs")
    if not isinstance(plan.get("new_call_id"), str) or len(plan["new_call_id"]) != 33:
        raise SubstitutionError("replacement call ID shape differs")
    if not plan["new_call_id"].startswith("g") or any(x not in "0123456789abcdef" for x in plan["new_call_id"][1:]):
        raise SubstitutionError("replacement call ID is malformed")
    all_old = {
        x
        for row in old["cells"]
        for x in (
            row["run_id"],
            row["subject_attempt_id"],
            row["packet_id"],
            *row["subject_call_ids"],
            *(item["call_id"] for item in row["scorers"]),
        )
    }
    historical = prior.schedule.prior_ids() | set(read(prior.schedule.OLD_MAP))
    if plan["new_call_id"] in all_old | historical | {read(prior.headroom.PLAN)["packet_id"]}:
        raise SubstitutionError("replacement call ID collides with old A")
    expected = json.loads(json.dumps(old))
    target = expected["cells"][23]
    scorer_row = next(item for item in target["scorers"] if item["route"] == "codex")
    if scorer_row["call_id"] != plan["old_call_id"]:
        raise SubstitutionError("failed scorer does not match cell 22")
    scorer_row["call_id"] = plan["new_call_id"]
    expected["record_type"] = "p3_v3_a_second_technical_substitution_schedule"
    expected["status"] = "offline_candidate_pending_owner_acceptance"
    if candidate != expected:
        raise SubstitutionError("schedule differs beyond one technical scorer ID")


def full_plan() -> list[dict[str, Any]]:
    candidate = read(SCHEDULE)
    verify_schedule(candidate)
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
    if len(result) != 128 or result[95]["call_id"] != read(PLAN)["new_call_id"]:
        raise SubstitutionError("frozen call order differs")
    return result


def validate_predecessor() -> dict[str, Any]:
    """Replay both predecessor validators without accepting either failed scorer."""
    previous.verify_seal()
    previous.verify_approval(dispatch=True)
    previous.validate_predecessor()
    plan = read(PLAN)
    expected_plan = {
        "schema": 1,
        "record_type": "p3_v3_a_second_technical_substitution_plan",
        "replaced_position": 95,
        "old_call_id": "g3b83b6b857d3f34ef081f2a39f0215a6",
        "new_call_id": plan["new_call_id"],
        "carried_accepted_calls": 95,
        "new_provider_calls": 33,
        "opening_codex_tokens": OPENING,
        "failed_call_charged": 12_587,
        "request_sha256": "24d04e80c1e64794687e37fb45f12355bdbec498bf29715a3e8db7b009f4e497",
    }
    if plan != expected_plan:
        raise SubstitutionError("second substitution plan differs")
    previous._configure_base()
    try:
        rows = prior._rows()
        if len(rows) != 19 or len(rows[1:]) != 18:
            raise SubstitutionError("second predecessor ledger cardinality differs")
        if any(rows[2 * i + 2].get("status") != "accepted" for i in range(8)):
            raise SubstitutionError("second predecessor accepted prefix differs")
        final_reserved, final = rows[-2:]
        target = previous.full_plan()[ACCEPTED_PREFIX]
        if (
            final_reserved.get("event") != "reserved"
            or final.get("event") != "completed"
            or final.get("status") != "failed"
            or final_reserved.get("call") != target
            or final.get("call") != target
            or target["call_id"] != plan["old_call_id"]
            or final.get("usage") != {"input_tokens": 12_307, "output_tokens": 280}
        ):
            raise SubstitutionError("second failed scorer identity or usage differs")
        root = previous.RUNTIME / "evidence" / target["call_id"]
        failure = read(root / "failure.json")
        events = read(root / "events.json")
        stderr = (root / "stderr.raw").read_bytes()
        if (
            failure
            != {
                "status": "terminal",
                "failure_code": "QualificationError",
                "retry_authorized": False,
                "usage": final["usage"],
            }
            or final.get("evidence_sha256") != sha(root / "failure.json")
            or final_reserved.get("request_sha256") != read(root / "prepared.json").get("request_sha256")
            or final_reserved.get("request_sha256") != plan["request_sha256"]
            or scorer.cli_retry_error_markers(events, stderr) != ["stderr"]
            or stderr.count(b"503 Service Unavailable") != 1
            or scorer.tool_markers(events)
        ):
            raise SubstitutionError("second failed-call 503 evidence differs")
        original_rows = prior._rows
        try:
            prior._rows = lambda: rows[:17]
            count, charged_before_failure = prior._state()
        finally:
            prior._rows = original_rows
        if count != 8 or charged_before_failure + sum(final["usage"].values()) != OPENING:
            raise SubstitutionError("second carryover usage or evidence differs")
        return {
            "accepted_prefix": ACCEPTED_PREFIX,
            "predecessor_accepted_calls": count,
            "predecessor_ledger_sha256": sha(previous.LEDGER),
            "failed_evidence_sha256": sha(root / "failure.json"),
        }
    finally:
        _reset_base()


def seal_body() -> dict[str, Any]:
    predecessor = validate_predecessor()
    plan = read(PLAN)
    old_root = previous.RUNTIME / "evidence" / plan["old_call_id"]
    if read(old_root / "prepared.json").get("request_sha256") != plan["request_sha256"]:
        raise SubstitutionError("second replacement request hash differs")
    exchange = previous.RUNTIME / "exchanges" / f"{full_plan()[95]['run_id']}.json"
    sources = (
        "successors/v3_qualification_second_technical_substitution_v1.py",
        "successors/v3_qualification_technical_substitution_v2.py",
        "successors/v3_qualification_headroom.py",
        "successors/v3_qualification_headroom_packet.py",
        "successors/v3_qualification_headroom_schedule.py",
        "successors/v3_qualification_headroom_reduce.py",
        "v3_scorer_header_optional.py",
        "scorer_route_check.py",
        "quota_adapter_v3.py",
    )
    reconciliation = previous.RUNTIME / "pre-dispatch-stops" / "ga23f3328c7cdb4c4898ea250b40f6e78-reconciliation.json"
    record = read(reconciliation)
    archived = previous.RUNTIME / "pre-dispatch-stops" / record["call_id"]
    if (
        record.get("provider_calls") != 0
        or record.get("ledger_sha256_before_after")
        != "7fc4c5639080d2c8672a3d509c824a15bc5af922c50cb7f2282ee41102b05be2"
        or {
            str(path.relative_to(archived)): sha(path)
            for path in archived.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        != record.get("files_sha256")
        or {str(path.relative_to(archived)): str(path.readlink()) for path in archived.rglob("*") if path.is_symlink()}
        != record.get("symlinks")
    ):
        raise SubstitutionError("pre-dispatch reconciliation differs")
    return {
        "schema": 1,
        "record_type": "p3_v3_a_second_technical_substitution_seal",
        "scope": "one_second_invalid_scorer_substitution_plus_remaining_a_calls",
        "status": "offline_candidate_pending_owner_acceptance",
        "provider_calls_started": 0,
        "planned_new_calls": NEW_CALLS,
        "opening_codex_tokens": OPENING,
        "codex_limit_tokens": prior.LIMIT,
        "five_hour_stop_percent": 80,
        "weekly_stop_percent": 90,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "qwen_output_setting": 16_000,
        "model_ids": {
            "subject_strongest": "gpt-6-astra",
            "subject_mid": "gpt-5.6-luna",
            "codex_scorer": "gpt-6-astra",
            "qwen_scorer": "qwen3.8-27b",
        },
        "proposal_sha256": sha(PROPOSAL),
        "plan_sha256": sha(PLAN),
        "schedule_sha256": sha(SCHEDULE),
        "original_seal_sha256": sha(ORIGINAL_BASE["seal"]),
        "original_ledger_sha256": sha(ORIGINAL_BASE["ledger"]),
        "predecessor_seal_sha256": sha(previous.SEAL),
        "predecessor_approval_sha256": sha(previous.APPROVAL),
        "predecessor_preflight_sha256": sha(previous.PREFLIGHT),
        "predecessor_ledger_sha256": predecessor["predecessor_ledger_sha256"],
        "failed_evidence_sha256": predecessor["failed_evidence_sha256"],
        "failed_artifact_sha256": {
            name: sha(old_root / name)
            for name in (
                "events.json",
                "stdout.raw",
                "stderr.raw",
                "reply.raw.tsv",
                "reply.tsv",
                "prepared.json",
                "failure.json",
                "rollout.jsonl",
                "quota-before.json",
                "packet.md",
            )
        },
        "pre_dispatch_reconciliation_sha256": sha(reconciliation),
        "replacement_exchange_sha256": sha(exchange),
        "headroom_route_outcome_sha256": sha(prior.headroom.RUNTIME / "outcome.json"),
        "headroom_effective_qwen_settings": read(ORIGINAL_BASE["seal"])["headroom_effective_qwen_settings"],
        "source_sha256": {name: sha(HERE / name) for name in sources},
        "regression_sha256": sha(HERE.parents[1] / "tests/test_a22_p3_v3_a_second_technical_substitution_v1.py"),
        "runtime_root": str(RUNTIME),
    }


def verify_seal() -> None:
    _reset_base()
    if read(SEAL) != seal_body():
        raise SubstitutionError("technical-substitution seal differs")


def approval_template() -> dict[str, Any]:
    return {
        "schema": 1,
        "record_type": "p3_v3_a_second_technical_substitution_approval",
        "seal_sha256": sha(SEAL),
        "preflight_sha256": None,
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "acceptance_basis": None,
    }


def verify_approval(*, dispatch: bool) -> None:
    actual = read(APPROVAL)
    template = approval_template()
    if not dispatch and actual == template:
        return
    expected = {
        **template,
        "preflight_sha256": sha(PREFLIGHT),
        "owner_accepted": True,
        "dispatch_allowed": True,
        "authorized_phases": ["a_second_technical_substitution_and_remainder"],
        "acceptance_basis": "owner accepted a second infrastructure-invalid Codex scorer substitution in this chat",
    }
    if actual != expected:
        raise SubstitutionError("exact technical-substitution approval absent")


def _local_preflight_facts() -> dict[str, Any]:
    codex_version = subprocess.run(
        [str(prior.CODEX), "--version"], capture_output=True, text=True, check=False, timeout=10
    )
    qwen = shutil.which("qwen")
    if codex_version.returncode or codex_version.stdout.strip() != "codex-cli 0.162.1" or not qwen:
        raise SubstitutionError("pinned CLI executables unavailable")
    qwen_path = Path(qwen).resolve(strict=True)
    qwen_version = subprocess.run([qwen, "--version"], capture_output=True, text=True, check=False, timeout=10)
    if qwen_version.returncode or not scorer._version_matches(qwen_version.stdout + qwen_version.stderr, "0.24.7"):
        raise SubstitutionError("Qwen CLI version differs")
    prior.verify_qwen_effective_settings(read(ORIGINAL_BASE["seal"])["headroom_effective_qwen_settings"])
    return {
        "codex_cli_version": codex_version.stdout.strip(),
        "codex_executable_sha256": sha(prior.CODEX),
        "qwen_cli_version": "0.24.7",
        "qwen_executable": str(qwen_path),
        "qwen_executable_sha256": sha(qwen_path),
        "qwen_effective_settings_sha256": read(ORIGINAL_BASE["seal"])["headroom_effective_qwen_settings"][
            "effective_sha256"
        ],
    }


def _preflight_record() -> dict[str, Any]:
    return {
        "status": "passed",
        "provider_calls": 0,
        "dispatch_allowed": False,
        "seal_sha256": sha(SEAL),
        "planned_new_calls": NEW_CALLS,
        "opening_codex_tokens": OPENING,
        "gateway_probe": "verified_tls_handshake_without_api_request",
        **_local_preflight_facts(),
    }


def preflight() -> dict[str, Any]:
    verify_seal()
    verify_approval(dispatch=False)
    if RUNTIME.exists() or RUNTIME.is_symlink():
        raise SubstitutionError("successor runtime already used")
    if not prior.AUTH.is_file() or prior.AUTH.is_symlink():
        raise SubstitutionError("Codex auth source absent")
    facts = _preflight_record()
    prior.route.check_gateway_tls()
    return facts


def _configure_base() -> None:
    """Use the frozen call implementation with a new isolated ledger and schedule."""
    prior.RUNTIME = RUNTIME
    prior.LEDGER = LEDGER
    prior.SEAL = SEAL
    prior.APPROVAL = APPROVAL
    prior.PREFLIGHT = PREFLIGHT
    prior.OPENING = OPENING
    prior.TOTAL_CALLS = NEW_CALLS
    prior.schedule.SCHEDULE = SCHEDULE
    prior.schedule.verify_schedule = verify_schedule
    prior.call_plan = lambda: full_plan()[ACCEPTED_PREFIX:]
    prior.packet.render = _guarded_render


def _guarded_render(row: dict[str, Any], exchange: dict[str, Any]) -> tuple[bytes, bytes]:
    visible, request = ORIGINAL_BASE["packet_render"](row, exchange)
    if (
        row["run_id"] == full_plan()[ACCEPTED_PREFIX]["run_id"]
        and hashlib.sha256(request).hexdigest() != read(PLAN)["request_sha256"]
    ):
        raise SubstitutionError("replacement request differs from failed call")
    return visible, request


def _reset_base() -> None:
    prior.RUNTIME = ORIGINAL_BASE["runtime"]
    prior.LEDGER = ORIGINAL_BASE["ledger"]
    prior.SEAL = ORIGINAL_BASE["seal"]
    prior.APPROVAL = ORIGINAL_BASE["approval"]
    prior.PREFLIGHT = ORIGINAL_BASE["preflight"]
    prior.OPENING = ORIGINAL_BASE["opening"]
    prior.TOTAL_CALLS = ORIGINAL_BASE["total_calls"]
    prior.schedule.SCHEDULE = ORIGINAL_BASE["schedule"]
    prior.schedule.verify_schedule = ORIGINAL_BASE["verify_schedule"]
    prior.call_plan = ORIGINAL_BASE["call_plan"]
    prior.packet.render = ORIGINAL_BASE["packet_render"]


def _state() -> tuple[int, int]:
    _configure_base()
    return prior._state() if LEDGER.exists() else (0, OPENING)


def advance() -> dict[str, Any]:
    verify_seal()
    verify_approval(dispatch=True)
    if read(PREFLIGHT) != _preflight_record():
        raise SubstitutionError("offline preflight differs")
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = os.open(RUNTIME / "qualification.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        if not LEDGER.exists():
            (RUNTIME / "exchanges").mkdir(mode=0o700)
            source = previous.RUNTIME / "exchanges" / f"{full_plan()[ACCEPTED_PREFIX]['run_id']}.json"
            prior.write_new(RUNTIME / "exchanges" / source.name, source.read_bytes())
            _configure_base()
            prior.write_new(LEDGER, (json.dumps(prior._header(), sort_keys=True) + "\n").encode())
        count, charged = _state()
        if count == NEW_CALLS:
            return {
                "status": "qualification_calls_complete",
                "completed_new_calls": count,
                "charged_codex_tokens": charged,
            }
        step = full_plan()[ACCEPTED_PREFIX + count]
        if step["route"] == "qwen":
            prior.route.check_gateway_tls()
        result = prior._call(step, charged)
        result["completed_new_calls"] = count + 1
        result["charged_codex_tokens"] = charged + (sum(result["usage"].values()) if step["route"] == "codex" else 0)
        return result
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def reduce_accepted() -> dict[str, Any]:
    verify_seal()
    verify_approval(dispatch=True)
    count, charged = _state()
    if count != NEW_CALLS:
        raise SubstitutionError("successor has fewer than 41 accepted calls")
    candidate = read(SCHEDULE)
    readings: dict[str, dict[str, str]] = {}
    for row in candidate["cells"]:
        replies = {}
        for item in row["scorers"]:
            position = next(index for index, step in enumerate(full_plan()) if step["call_id"] == item["call_id"])
            origin = ORIGINAL_BASE["runtime"] if position < 87 else previous.RUNTIME if position < 95 else RUNTIME
            root = origin / "evidence" / item["call_id"]
            replies[item["route"]] = read(root / "result.json")["reply"]
        readings[row["run_id"]] = replies
    _configure_base()
    primary = prior.reduce_module.reduce(readings, candidate=candidate)
    failed = previous.RUNTIME / "evidence" / read(PLAN)["old_call_id"] / "reply.tsv"
    sensitivity = None
    if failed.is_file():
        try:
            scorer.validate_tsv(
                failed.read_text(), candidate["cells"][23]["packet_id"], candidate["cells"][23]["element_ids"]
            )
            alternate = json.loads(json.dumps(readings))
            alternate[candidate["cells"][23]["run_id"]]["codex"] = failed.read_text()
            sensitivity = prior.reduce_module.reduce(alternate, candidate=candidate)
        except ValueError:
            sensitivity = {"status": "failed_reply_not_parseable"}
    return {
        "primary": primary,
        "sensitivity_status": None if sensitivity is None else sensitivity["status"],
        "sensitivity_qualified_strata_changed": None
        if sensitivity is None or "qualified_strata" not in sensitivity
        else sensitivity["qualified_strata"] != primary["qualified_strata"],
        "charged_codex_tokens": charged,
        "accepted_new_calls": count,
        "carried_calls": ACCEPTED_PREFIX,
        "ledger_sha256": sha(LEDGER),
    }


def main() -> None:
    parser_cli = argparse.ArgumentParser()
    parser_cli.add_argument("action", choices=("preflight", "advance", "status", "reduce"))
    action = parser_cli.parse_args().action
    if action == "preflight":
        print(json.dumps(preflight(), sort_keys=True))
    elif action == "advance":
        print(json.dumps(advance(), sort_keys=True))
    elif action == "reduce":
        print(json.dumps(reduce_accepted(), sort_keys=True))
    else:
        verify_seal()
        count, charged = _state()
        print(
            json.dumps(
                {"completed_new_calls": count, "planned_new_calls": NEW_CALLS, "charged_codex_tokens": charged},
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
