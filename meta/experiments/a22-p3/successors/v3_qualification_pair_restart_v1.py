#!/usr/bin/env python3
"""Carry forward 96 accepted A calls and restart a failed subject pair."""

# ruff: noqa: D103 PERF401 PLR2004 S108
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scorer_route_check as scorer
import v3_qualification_bounded_transport_v1 as previous
import v3_qualification_headroom as prior
import v3_qualification_technical_substitution_v2 as first

HERE = Path(__file__).resolve().parent.parent
RUNS = HERE / "runs"
PROPOSAL = HERE / "V3_A_SUBJECT_PAIR_RESTART_PROPOSAL.md"
PLAN = RUNS / "v3-a-pair-restart-plan-v1.json"
SCHEDULE = RUNS / "v3-a-pair-restart-schedule-v1.json"
SEAL = RUNS / "v3-a-pair-restart-seal-v1.json"
PREFLIGHT = RUNS / "v3-a-pair-restart-preflight-v1.json"
APPROVAL = RUNS / "v3-a-pair-restart-approval-v1.json"
RUNTIME = Path("/tmp/a22-p3-v3-a-pair-restart-v1-runtime")
LEDGER = RUNTIME / "qualification-events.jsonl"
ATTEMPT_OUTCOME = RUNTIME / "subject-attempt-outcome.json"
ACCEPTED_PREFIX = 96
NEW_CALLS = 32
OPENING = 1_608_025
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
    "header": prior._header,
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
    """Allow only the cell-25 attempt and its two call IDs to change."""
    old = _old_schedule()
    plan = read(PLAN)
    target = old["cells"][24]
    if plan.get("replaced_positions") != [96, 97] or plan.get("old_call_ids") != target["subject_call_ids"]:
        raise SubstitutionError("pair target differs")
    new_ids = [plan.get("new_subject_attempt_id"), *plan.get("new_call_ids", [])]
    if (
        len(new_ids) != 3
        or len(set(new_ids)) != 3
        or any(
            not isinstance(x, str)
            or len(x) != 33
            or not x.startswith("g")
            or any(c not in "0123456789abcdef" for c in x[1:])
            for x in new_ids
        )
    ):
        raise SubstitutionError("new pair IDs are malformed or reused")
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
    if set(new_ids) & (all_old | historical | {read(prior.headroom.PLAN)["packet_id"]}):
        raise SubstitutionError("pair ID collides with old A")
    expected = json.loads(json.dumps(old))
    target = expected["cells"][24]
    target["subject_attempt_id"] = plan["new_subject_attempt_id"]
    target["subject_call_ids"] = plan["new_call_ids"]
    expected["record_type"] = "p3_v3_a_pair_restart_schedule"
    expected["status"] = "offline_candidate_pending_owner_acceptance"
    if candidate != expected:
        raise SubstitutionError("schedule differs beyond cell-25 subject pair")


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
    if len(result) != 128 or [result[i]["call_id"] for i in (96, 97)] != read(PLAN)["new_call_ids"]:
        raise SubstitutionError("frozen call order differs")
    return result


def attempt_registry() -> dict[str, Any]:
    """Keep historical technical attempts distinct from the pending primary pair."""
    plan = read(PLAN)
    row = read(previous.SCHEDULE)["cells"][24]
    first_failed, first_superseded = plan["historical_first_call_ids"]
    return {
        "cell_run_id": row["run_id"],
        "packet_id": row["packet_id"],
        "historical": [
            {
                "origin_first_call_id": first_failed,
                "scheduled_attempt_id_alias": row["subject_attempt_id"],
                "classification": "technical",
                "terminal_status": "failed_turn_1_http_503",
            },
            {
                "origin_first_call_id": first_superseded,
                "scheduled_attempt_id_alias": row["subject_attempt_id"],
                "classification": "technical",
                "terminal_status": "superseded_after_failed_turn_2_http_503",
                "second_call_id": plan["old_call_ids"][1],
            },
        ],
        "current": {
            "subject_attempt_id": plan["new_subject_attempt_id"],
            "first_call_id": plan["new_call_ids"][0],
            "second_call_id": plan["new_call_ids"][1],
            "status": "planned",
            "replaces": plan["historical_first_call_ids"],
        },
    }


def validate_predecessor() -> dict[str, Any]:
    """Bind the fourth failed call and superseded first turn without accepting either."""
    previous.verify_seal()
    previous.verify_approval(dispatch=True)
    previous.validate_predecessor()
    plan = read(PLAN)
    expected_plan = {
        "schema": 1,
        "record_type": "p3_v3_a_pair_restart_plan",
        "replaced_positions": [96, 97],
        "old_call_ids": ["gaf1c096b38359b39b26ccc238a839761", "g6d0853c9c1c83c02c47535b5d6dd6ae2"],
        "historical_first_call_ids": ["g2b3d24f77858c85f834a333661d78f05", "gaf1c096b38359b39b26ccc238a839761"],
        "old_subject_attempt_id": read(previous.SCHEDULE)["cells"][24]["subject_attempt_id"],
        "new_subject_attempt_id": plan["new_subject_attempt_id"],
        "new_call_ids": plan["new_call_ids"],
        "carried_accepted_calls": 96,
        "new_provider_calls": 32,
        "opening_codex_tokens": OPENING,
        "superseded_first_turn_charged": 5_934,
        "failed_second_turn_charged": 14_575,
        "first_request_sha256": "1f5de0656ab20059655aa12b4710195fbcb77e1b0e29e9266f8f43ee760e497e",
        "failed_second_request_sha256": "2ecb197a8db6cea76740890837978a9ed46d92fa492d661249c60fa98c68cbd9",
        "transport_failure_limit": 8,
        "predecessor_transport_failures": 4,
    }
    if plan != expected_plan:
        raise SubstitutionError("pair restart plan differs")
    previous._configure_base()
    try:
        rows = prior._rows()
        if len(rows) != 5:
            raise SubstitutionError("fourth predecessor ledger cardinality differs")
        first_reserved, first_done = rows[1:3]
        old_steps = previous.full_plan()[96:98]
        first_result = previous.RUNTIME / "evidence" / old_steps[0]["call_id"] / "result.json"
        if (
            first_reserved.get("event") != "reserved"
            or first_done.get("event") != "completed"
            or first_done.get("status") != "accepted"
            or first_reserved.get("call") != old_steps[0]
            or first_done.get("call") != old_steps[0]
            or first_done.get("usage") != {"input_tokens": 5_758, "output_tokens": 176}
            or first_done.get("evidence_sha256") != sha(first_result)
            or first_reserved.get("request_sha256") != plan["first_request_sha256"]
        ):
            raise SubstitutionError("superseded first turn differs")
        final_reserved, final = rows[-2:]
        target = old_steps[1]
        if (
            final_reserved.get("event") != "reserved"
            or final.get("event") != "completed"
            or final.get("status") != "failed"
            or final_reserved.get("call") != target
            or final.get("call") != target
            or final.get("usage") != {"input_tokens": 14_376, "output_tokens": 199}
        ):
            raise SubstitutionError("fourth failed subject identity or usage differs")
        root = previous.RUNTIME / "evidence" / target["call_id"]
        failure = read(root / "failure.json")
        events = read(root / "source.events.json")
        stderr = (root / "source.stderr.txt").read_bytes()
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
            or final_reserved.get("request_sha256") != plan["failed_second_request_sha256"]
            or prior.source.extract_usage(events) != final["usage"]
            or prior.source.has_tool_use(events)
            or not prior.controls._retry_markers(events, stderr)
            or stderr.count(b"503 Service Unavailable") != 1
        ):
            raise SubstitutionError("fourth failed-call 503 evidence differs")
        original_rows = prior._rows
        try:
            prior._rows = lambda: rows[:3]
            count, charged_before_failure = prior._state()
        finally:
            prior._rows = original_rows
        if count != 1 or charged_before_failure + sum(final["usage"].values()) != OPENING:
            raise SubstitutionError("fourth carryover usage or evidence differs")
        return {
            "accepted_prefix": ACCEPTED_PREFIX,
            "superseded_accepted_calls": count,
            "predecessor_ledger_sha256": sha(previous.LEDGER),
            "superseded_first_result_sha256": sha(first_result),
            "failed_evidence_sha256": sha(root / "failure.json"),
        }
    finally:
        _reset_base()


def seal_body() -> dict[str, Any]:
    predecessor = validate_predecessor()
    plan = read(PLAN)
    old_roots = [previous.RUNTIME / "evidence" / x for x in plan["old_call_ids"]]
    if read(old_roots[0] / "prepared.json").get("request_sha256") != plan["first_request_sha256"]:
        raise SubstitutionError("first-turn request hash differs")
    row = read(SCHEDULE)["cells"][24]
    case = read(HERE / "cases" / f"{row['case']}.json")
    if prior.sha_bytes(case["subject"]["turn1"].encode()) != plan["first_request_sha256"]:
        raise SubstitutionError("frozen first-turn prompt differs")
    old_first_reply = read(old_roots[0] / "result.json")["reply"]
    old_second_prompt = prior.source._second_prompt(case, old_first_reply)[2]
    if prior.sha_bytes(old_second_prompt.encode()) != plan["failed_second_request_sha256"]:
        raise SubstitutionError("failed second prompt is not derived from predecessor first reply")
    sources = (
        "successors/v3_qualification_pair_restart_v1.py",
        "successors/v3_qualification_bounded_transport_v1.py",
        "successors/v3_qualification_second_technical_substitution_v1.py",
        "successors/v3_qualification_technical_substitution_v2.py",
        "successors/v3_qualification_headroom.py",
        "successors/v3_qualification_headroom_packet.py",
        "successors/v3_qualification_headroom_schedule.py",
        "successors/v3_qualification_headroom_reduce.py",
        "v3_scorer_header_optional.py",
        "scorer_route_check.py",
        "quota_adapter_v3.py",
        "usage_ledger_v3.py",
        "v3_controls_successor.py",
        "v3_runner_version_successor.py",
        "successors/v3_header_optional_route_v8.py",
        "successors/v3_qwen_thinking_headroom.py",
        "v3_codex_format_route.py",
    )
    return {
        "schema": 1,
        "record_type": "p3_v3_a_pair_restart_seal",
        "scope": "fresh_cell25_subject_pair_plus_remaining_a_calls",
        "status": "offline_candidate_pending_owner_acceptance",
        "provider_calls_started": 0,
        "planned_new_calls": NEW_CALLS,
        "opening_codex_tokens": OPENING,
        "codex_limit_tokens": prior.LIMIT,
        "five_hour_stop_percent": 80,
        "weekly_stop_percent": 90,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "transport_failure_limit": 8,
        "predecessor_transport_failures": 4,
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
        "superseded_first_result_sha256": predecessor["superseded_first_result_sha256"],
        "failed_evidence_sha256": predecessor["failed_evidence_sha256"],
        "historical_artifact_sha256": {
            call_id: {
                name: sha(root / name)
                for name in (
                    "source.events.json",
                    "source.stdout.txt",
                    "source.stderr.txt",
                    "source.dispatch.json",
                    "prepared.json",
                    "quota-before.json",
                    *(("result.json",) if i == 0 else ("failure.json",)),
                )
            }
            for i, (call_id, root) in enumerate(zip(plan["old_call_ids"], old_roots, strict=True))
        },
        "first_prompt_sha256": plan["first_request_sha256"],
        "failed_second_prompt_sha256": plan["failed_second_request_sha256"],
        "attempt_registry_sha256": prior.digest(attempt_registry()),
        "headroom_route_outcome_sha256": sha(prior.headroom.RUNTIME / "outcome.json"),
        "headroom_effective_qwen_settings": read(ORIGINAL_BASE["seal"])["headroom_effective_qwen_settings"],
        "source_sha256": {name: sha(HERE / name) for name in sources},
        "regression_sha256": sha(HERE.parents[1] / "tests/test_a22_p3_v3_a_pair_restart_v1.py"),
        "runtime_root": str(RUNTIME),
    }


def verify_seal() -> None:
    _reset_base()
    if read(SEAL) != seal_body():
        raise SubstitutionError("technical-substitution seal differs")


def approval_template() -> dict[str, Any]:
    return {
        "schema": 1,
        "record_type": "p3_v3_a_pair_restart_approval",
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
        "authorized_phases": ["a_subject_pair_restart"],
        "acceptance_basis": "owner accepted D-A22-PAIR-RESTART option A in this chat",
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
    prior._header = lambda: {**ORIGINAL_BASE["header"](), "subject_attempts": attempt_registry()}


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
    prior._header = ORIGINAL_BASE["header"]


def _state() -> tuple[int, int]:
    _configure_base()
    return prior._state() if LEDGER.exists() else (0, OPENING)


def _record_attempt_outcome() -> None:
    """Persist a D02 class when the first restarted cell has terminal evidence."""
    _configure_base()
    rows = prior._rows()
    first_cell = rows[2::2][:4]
    failed = next((item for item in first_cell if item.get("status") == "failed"), None)
    classification = "technical" if failed else "scored" if len(first_cell) == 4 else None
    if classification is None:
        if ATTEMPT_OUTCOME.exists():
            raise SubstitutionError("premature subject-attempt outcome")
        return
    event_count = 2 * (first_cell.index(failed) + 1) if failed else 8
    prefix = "".join(json.dumps(item, sort_keys=True) + "\n" for item in rows[: event_count + 1]).encode()
    expected = {
        "schema": 1,
        "record_type": "p3_v3_a_subject_attempt_outcome",
        "subject_attempt_id": read(PLAN)["new_subject_attempt_id"],
        "origin_first_call_id": read(PLAN)["new_call_ids"][0],
        "replaces": read(PLAN)["historical_first_call_ids"],
        "classification": classification,
        "terminal_call_id": (failed or first_cell[-1])["call"]["call_id"],
        "ledger_event_count": event_count,
        "ledger_prefix_sha256": prior.sha_bytes(prefix),
    }
    if ATTEMPT_OUTCOME.exists():
        if read(ATTEMPT_OUTCOME) != expected:
            raise SubstitutionError("subject-attempt outcome differs from ledger")
    else:
        prior.write_json(ATTEMPT_OUTCOME, expected)


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
            _configure_base()
            prior.write_new(LEDGER, (json.dumps(prior._header(), sort_keys=True) + "\n").encode())
        _record_attempt_outcome()
        count, charged = _state()
        completed_subject_attempts = len({row["run_id"] for row in read(SCHEDULE)["cells"][:24]})
        if completed_subject_attempts + len(attempt_registry()["historical"]) + 1 > 120:
            raise SubstitutionError("D02 subject-attempt ceiling exhausted")
        if read(PLAN)["predecessor_transport_failures"] >= read(PLAN)["transport_failure_limit"]:
            raise SubstitutionError("transport replacement ceiling exhausted")
        if count == NEW_CALLS:
            return {
                "status": "qualification_calls_complete",
                "completed_new_calls": count,
                "charged_codex_tokens": charged,
            }
        step = full_plan()[ACCEPTED_PREFIX + count]
        if step["route"] == "qwen":
            prior.route.check_gateway_tls()
        try:
            result = prior._call(step, charged)
        except BaseException:
            _record_attempt_outcome()
            raise
        _record_attempt_outcome()
        result["completed_new_calls"] = count + 1
        result["charged_codex_tokens"] = charged + (sum(result["usage"].values()) if step["route"] == "codex" else 0)
        return result
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def reduce_accepted() -> dict[str, Any]:
    verify_seal()
    verify_approval(dispatch=True)
    _record_attempt_outcome()
    count, charged = _state()
    if count != NEW_CALLS:
        raise SubstitutionError("successor has fewer than 32 accepted calls")
    _record_attempt_outcome()
    if read(ATTEMPT_OUTCOME)["classification"] != "scored":
        raise SubstitutionError("current subject attempt did not become scored")
    candidate = read(SCHEDULE)
    readings: dict[str, dict[str, str]] = {}
    for row in candidate["cells"]:
        replies = {}
        for item in row["scorers"]:
            position = next(index for index, step in enumerate(full_plan()) if step["call_id"] == item["call_id"])
            origin = (
                ORIGINAL_BASE["runtime"]
                if position < 87
                else first.RUNTIME
                if position < 95
                else previous.RUNTIME
                if position == 95
                else RUNTIME
            )
            root = origin / "evidence" / item["call_id"]
            replies[item["route"]] = read(root / "result.json")["reply"]
        readings[row["run_id"]] = replies
    _configure_base()
    primary = prior.reduce_module.reduce(readings, candidate=candidate)
    return {
        "primary": primary,
        "subject_attempts": {
            **attempt_registry(),
            "current": {**attempt_registry()["current"], "classification": "scored"},
        },
        "subject_attempt_outcome_sha256": sha(ATTEMPT_OUTCOME),
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
        if LEDGER.exists():
            _record_attempt_outcome()
        count, charged = _state()
        print(
            json.dumps(
                {"completed_new_calls": count, "planned_new_calls": NEW_CALLS, "charged_codex_tokens": charged},
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
