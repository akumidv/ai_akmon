#!/usr/bin/env python3
"""Fail-closed, one-shot runner for the three remaining V3 mechanics controls."""

# Evidence validation and process handling intentionally reuse the verified source runner.
# ruff: noqa: C901 PLR0912 PLR0913 PLR0915
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import quota_adapter_v3 as quota
import reconcile_v3_usage as accounting
import usage_ledger_v3 as ledger
import v3_runner_version_successor as source

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2].resolve()
RUNTIME = Path("/tmp/a22-p3-v3-controls-successor-runtime")  # noqa: S108 - isolated experiment root
PREDECESSOR_RUNTIME = Path("/tmp/a22-p3-v3-controls-runtime")  # noqa: S108 - preserved failed startup
EXECUTABLE = Path("/home/ai/.codex/packages/standalone/releases/0.162.1-x86_64-unknown-linux-musl/bin/codex")
SEAL = HERE / "runs" / "v3-controls-successor-seal-v1.json"
APPROVAL = HERE / "runs" / "v3-controls-successor-approval-v1.json"
ACCEPTANCE = HERE / "runs" / "v3-controls-successor-acceptance-evidence-v1.json"
PROPOSAL = HERE / "V3_CONTROLS_SUCCESSOR_PROPOSAL.md"
CASE = HERE / "cases" / "P3-01.json"
PACKET_SEAL = HERE / "seal.json"
ARM_MANIFEST = HERE / "arms" / "manifest.json"
AUTH_SOURCE = Path("/tmp/a22-p3-v3-successor-9xViiq/codex-home-run/auth.json")  # noqa: S108
VERIFIED_SOURCE_ROOT = Path("/tmp/a22-p3-v3-successor-9xViiq")  # noqa: S108
VERIFIED_RUN_ID = "4c22e100b2101c0d67067d33fd98cd92"
ROUTE_ROOT = Path("/tmp/a22-p3-v3-successor-route-runtime")  # noqa: S108
LEDGER = RUNTIME / "control-events.jsonl"
CELLS = (("A", "mid", "gpt-5.6-luna"), ("C", "strongest", "gpt-6-astra"), ("C", "mid", "gpt-5.6-luna"))
CLI_VERSION = "codex-cli 0.162.1"
ACCOUNT_ID_SHA = "dc17f02443f35278c2d94b94ee471ee5dc9f10e499726ea3d92d591eecdab320"
SOURCE_FILES = (
    "v3_controls_successor.py",
    "reconcile_v3_usage.py",
    "usage_ledger_v3.py",
    "quota_adapter_v3.py",
    "v3_runner_version_successor.py",
)
CONTROL_TURNS = 2
RETRY_MARKER = re.compile(r"retry|error|failed|failure", re.IGNORECASE)


class ControlError(ValueError):
    """A control phase gate or evidence check failed."""


def sha(path: Path) -> str:
    """Hash a bound file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    """Parse a JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value: dict[str, Any]) -> str:
    """Hash a canonical append-only event."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def seal_body() -> dict[str, Any]:
    """Recompute the exact offline control inputs."""
    source_record = VERIFIED_SOURCE_ROOT / "output-run" / f"{VERIFIED_RUN_ID}.record.json"
    source_exchange = VERIFIED_SOURCE_ROOT / "output-run" / f"{VERIFIED_RUN_ID}.exchange.json"
    rollouts = list((VERIFIED_SOURCE_ROOT / "codex-home-run" / "sessions").rglob("rollout-*.jsonl"))
    if len(rollouts) != 1:
        raise ControlError("verified A/strongest source rollout is missing or ambiguous")
    return {
        "record_type": "p3_v3_controls_seal",
        "schema": 1,
        "scope": ["technical_controls"],
        "cells": [list(cell) for cell in CELLS],
        "opening_codex_tokens": accounting.CHARGED_OPENING,
        "proposal_sha256": sha(PROPOSAL),
        "predecessor_seal_sha256": sha(HERE / "runs" / "v3-controls-seal-v1.json"),
        "predecessor_approval_sha256": sha(HERE / "runs" / "v3-controls-approval-v1.json"),
        "predecessor_ledger_sha256": sha(PREDECESSOR_RUNTIME / "control-events.jsonl"),
        "predecessor_runtime": str(PREDECESSOR_RUNTIME),
        "pinned_executable": str(EXECUTABLE),
        "pinned_executable_sha256": sha(EXECUTABLE),
        "packet_seal_sha256": sha(PACKET_SEAL),
        "case_sha256": sha(CASE),
        "arm_manifest_sha256": sha(ARM_MANIFEST),
        "arm_sha256": {arm: sha(HERE / "arms" / f"{arm}.architect.system.txt") for arm in ("A", "C")},
        "historical_receipt_sha256": sha(accounting.RECEIPT),
        "opening_record_sha256": sha(accounting.OPENING),
        "prior_route_seal_sha256": sha(HERE / "runs" / "successor-route-check-seal-v6.json"),
        "verified_source_sha256": {
            "record": sha(source_record),
            "exchange": sha(source_exchange),
            "rollout": sha(rollouts[0]),
        },
        "route_evidence_sha256": {
            "ledger": sha(accounting.ROUTE_LEDGER),
            "codex_outcome": sha(ROUTE_ROOT / "703d05a1913c46b6aea23c475a8a18a5" / "outcome.json"),
            "codex_reply": sha(ROUTE_ROOT / "703d05a1913c46b6aea23c475a8a18a5" / "reply.tsv"),
            "qwen_outcome": sha(ROUTE_ROOT / "fbc97acaaca249e99f5eec233bd30564" / "outcome.json"),
            "qwen_reply": sha(ROUTE_ROOT / "fbc97acaaca249e99f5eec233bd30564" / "reply.tsv"),
        },
        "source_sha256": {name: sha(HERE / name) for name in SOURCE_FILES},
        "regression_sha256": sha(HERE.parents[1] / "tests" / "test_a22_p3_v3_controls_successor.py"),
        "original_regression_sha256": sha(HERE.parents[1] / "tests" / "test_a22_p3_v3_controls.py"),
        "provider_calls_started": 0,
        "status": "offline_candidate_pending_owner_acceptance",
    }


def verify_seal() -> dict[str, Any]:
    """Reject any input drift before dispatch."""
    actual = read(SEAL)
    if actual != seal_body():
        raise ControlError("controls seal is stale or incomplete")
    predecessor_rows = [
        json.loads(line) for line in (PREDECESSOR_RUNTIME / "control-events.jsonl").read_text().splitlines()
    ]
    if (
        len(predecessor_rows) != 1
        or predecessor_rows[0].get("record_type") != "p3_v3_controls_ledger"
        or predecessor_rows[0].get("seal_sha256") != actual["predecessor_seal_sha256"]
        or list((PREDECESSOR_RUNTIME / "control-0" / "output").iterdir())
    ):
        raise ControlError("predecessor was not a zero-call startup failure")
    accounting.verify_receipt()
    accounting.verify_opening_record()
    source_record = read(VERIFIED_SOURCE_ROOT / "output-run" / f"{VERIFIED_RUN_ID}.record.json")
    if (
        source_record.get("verified") is not True
        or source_record.get("run_id") != VERIFIED_RUN_ID
        or source_record.get("case") != "P3-01"
        or source_record.get("arm") != "A"
        or source_record.get("tier") != "strongest"
        or source_record.get("repeat") != 1
        or source_record.get("model") != "gpt-6-astra"
        or source_record.get("provenance_scope") != "evaluator_only"
        or source_record.get("exchange_sha256") != actual["verified_source_sha256"]["exchange"]
        or source_record.get("rollout_sha256") != actual["verified_source_sha256"]["rollout"]
    ):
        raise ControlError("verified A/strongest source evidence differs")
    for route, attempt in (("codex", "703d05a1913c46b6aea23c475a8a18a5"), ("qwen", "fbc97acaaca249e99f5eec233bd30564")):
        outcome = read(ROUTE_ROOT / attempt / "outcome.json")
        if (
            outcome.get("status") != "passed"
            or outcome.get("route") != route
            or outcome.get("scored_p3") is not False
            or outcome.get("qualification_data") is not False
        ):
            raise ControlError(f"{route} route outcome is not passed")
    packet = read(PACKET_SEAL).get("files", {})
    arms = read(ARM_MANIFEST).get("arms", {})
    if packet.get("cases/P3-01.json") != sha(CASE):
        raise ControlError("control case differs from frozen packet")
    for arm in ("A", "C"):
        path = HERE / "arms" / f"{arm}.architect.system.txt"
        if packet.get(f"arms/{arm}.architect.system.txt") != sha(path) or arms.get(arm, {}).get("sha256") != sha(path):
            raise ControlError("control arm differs from frozen packet")
    return actual


def approval_template() -> dict[str, Any]:
    """Build the explicit default-deny owner approval record."""
    return {
        "record_type": "p3_v3_controls_owner_approval",
        "schema": 1,
        "operational_seal_sha256": sha(SEAL),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
        "accepted_accounting_exception": False,
        "acceptance_evidence_sha256": None,
    }


def verify_approval(*, dispatch: bool) -> dict[str, Any]:
    """Require exact phase acceptance; template is safe only for offline preflight."""
    actual = read(APPROVAL)
    expected = approval_template()
    if not dispatch and actual == expected:
        return actual
    if not ACCEPTANCE.is_file():
        raise ControlError("control phase has no owner acceptance evidence")
    required = {
        **expected,
        "owner_accepted": True,
        "dispatch_allowed": True,
        "authorized_phases": ["technical_controls"],
        "named_stop_operator": "owner (current chat session)",
        "accepted_accounting_exception": True,
        "acceptance_evidence_sha256": sha(ACCEPTANCE),
    }
    if actual != required:
        raise ControlError("exact control phase approval is absent")
    evidence = read(ACCEPTANCE)
    if (
        evidence.get("record_type") != "p3_v3_controls_owner_acceptance"
        or evidence.get("accepted_seal_sha256") != sha(SEAL)
        or not evidence.get("request_message_id")
        or not evidence.get("user_message_id")
        or sha(SEAL) not in evidence.get("request_text", "")
        or "technical_controls" not in evidence.get("request_text", "")
        or sha(SEAL) not in evidence.get("user_text", "")
        or "technical_controls" not in evidence.get("user_text", "")
        or not any(word in evidence.get("user_text", "").lower() for word in ("оператор", "operator"))
    ):
        raise ControlError("exact control acceptance evidence is absent")
    return actual


def offline_preflight() -> dict[str, Any]:
    """Check sealed accounting and runtime prerequisites without provider calls."""
    seal = verify_seal()
    verify_approval(dispatch=False)
    if not AUTH_SOURCE.is_file() or AUTH_SOURCE.is_symlink() or AUTH_SOURCE.stat().st_mode & 0o077:
        raise ControlError("private source authentication file is unavailable")
    if RUNTIME.resolve() == REPO or REPO in RUNTIME.resolve().parents or RUNTIME.is_symlink():
        raise ControlError("control runtime is not isolated from the repository")
    if LEDGER.exists() or any((RUNTIME / f"control-{index}").exists() for index in range(len(CELLS))):
        raise ControlError("control phase already has activity; no retry or reuse")
    if not EXECUTABLE.is_file() or not os.access(EXECUTABLE, os.X_OK):
        raise ControlError("pinned Codex executable is unavailable")
    return {
        "status": "PASSED_OFFLINE_CONTROLS_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "opening_record_sha256": sha(accounting.OPENING),
        "control_cells": seal["cells"],
        "provider_calls_started": 0,
        "dispatch_allowed": False,
    }


def _rows() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    rows = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines()]
    if not rows or rows[0].get("record_type") != "p3_v3_controls_ledger":
        raise ControlError("control ledger header is invalid")
    previous = digest(rows[0])
    for seq, row in enumerate(rows[1:], 1):
        body = {key: value for key, value in row.items() if key != "event_sha256"}
        if row.get("seq") != seq or row.get("previous_sha256") != previous or row.get("event_sha256") != digest(body):
            raise ControlError("control ledger hash chain differs")
        previous = row["event_sha256"]
    return rows


def _append(event: dict[str, Any]) -> None:
    rows = _rows()
    body = {
        "seq": len(rows),
        "previous_sha256": digest(rows[0]) if len(rows) == 1 else rows[-1]["event_sha256"],
        **event,
    }
    body["event_sha256"] = digest(body)
    fd = os.open(LEDGER, os.O_WRONLY | os.O_APPEND)
    try:
        remaining = memoryview((json.dumps(body, sort_keys=True) + "\n").encode())
        while remaining:
            remaining = remaining[os.write(fd, remaining) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def _usage_state() -> tuple[int, set[str]]:
    rows = _rows()
    reservations = {row["call_id"]: row for row in rows[1:] if row.get("event") == "reserved"}
    completions = {row["call_id"]: row for row in rows[1:] if row.get("event") == "completed"}
    if (
        len(reservations) != len([row for row in rows[1:] if row.get("event") == "reserved"])
        or len(completions) != len([row for row in rows[1:] if row.get("event") == "completed"])
        or set(reservations) != set(completions)
        or any(row.get("usage_status") != "known" for row in completions.values())
        or any(row.get("outcome") != "accepted" for row in completions.values())
    ):
        raise ControlError("unresolved or unknown control usage locks dispatch")
    for call_id, completion in completions.items():
        reservation = reservations[call_id]
        cell, turn, run_id = reservation.get("cell"), reservation.get("turn"), reservation.get("run_id")
        if (
            cell not in range(len(CELLS))
            or turn not in (1, 2)
            or not isinstance(run_id, str)
            or any(completion.get(key) != reservation.get(key) for key in ("attempt_id", "run_id", "cell", "turn"))
        ):
            raise ControlError("control reservation identity is malformed")
        prefix = RUNTIME / f"control-{cell}" / "output" / f"{run_id}.turn{turn}"
        event_path = Path(f"{prefix}.events.json")
        dispatch_path = Path(f"{prefix}.dispatch.json")
        stdout_path = Path(f"{prefix}.stdout.txt")
        if (
            completion.get("events_sha256") != sha(event_path)
            or completion.get("dispatch_sha256") != sha(dispatch_path)
            or completion.get("stdout_sha256") != sha(stdout_path)
            or read(dispatch_path).get("returncode") != 0
            or read(dispatch_path).get("cwd") != str(RUNTIME / f"control-{cell}" / "scratch")
        ):
            raise ControlError("control call evidence no longer binds its reservation")
        events = read(event_path)
        usage = source.extract_usage(events)
        if (
            usage["input_tokens"] != completion.get("input_tokens")
            or usage["output_tokens"] != completion.get("output_tokens")
            or source.thread_id(events) != completion.get("session_id")
        ):
            raise ControlError("direct usage does not match charged control call")
    used = accounting.CHARGED_OPENING + sum(row["input_tokens"] + row["output_tokens"] for row in completions.values())
    return used, set(reservations)


def _occupied_ids() -> set[str]:
    """Collect prior source/route IDs so new control IDs cannot alias history."""
    occupied = ledger._historical_ids() | set(read(accounting.OPENING)["technical_subject_attempt_ids"])
    for path in (accounting.RUNTIME / "provider-usage-v3.jsonl", accounting.LEAN_LEDGER, accounting.SOURCE_LEDGER):
        _, events = ledger._read(path)
        for row in events:
            for key in ("provider_call_id", "subject_attempt_id", "run_id"):
                if isinstance(row.get(key), str):
                    occupied.add(row[key])
    for line in accounting.ROUTE_LEDGER.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for key in ("attempt_id", "opaque_packet_id"):
            if isinstance(row.get(key), str):
                occupied.add(row[key])
    return occupied


def require_budget(used: int, reservation: int) -> None:
    """Stop admission before a call when its reserved input could hit the cap."""
    if (
        not isinstance(used, int)
        or used < accounting.CHARGED_OPENING
        or not isinstance(reservation, int)
        or reservation < 0
        or used >= ledger.CODEX_LIMIT
        or used + reservation > ledger.CODEX_LIMIT
    ):
        raise ControlError("V3 Codex ceiling blocks control dispatch")


def _verify_rollout(home: Path, session: str, model: str, arm: str, scratch: Path, usages: list[dict[str, int]]) -> str:
    paths = list((home / "sessions").rglob("rollout-*.jsonl"))
    if len(paths) != 1 or paths[0].is_symlink():
        raise ControlError("control rollout is absent or ambiguous")
    events = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines()]
    metas = [row["payload"] for row in events if row.get("type") == "session_meta"]
    contexts = [row["payload"] for row in events if row.get("type") == "turn_context"]
    usage_rows = [row["payload"] for row in events if row.get("type") == "token_usage_record"]
    if (
        len(metas) != 1
        or metas[0].get("id") != session
        or metas[0].get("cli_version") not in {"0.162.1", CLI_VERSION}
        or Path(str(metas[0].get("cwd", ""))).resolve() != scratch
        or metas[0].get("base_instructions", {}).get("text", "").rstrip("\n")
        != (HERE / "arms" / f"{arm}.architect.system.txt").read_text().rstrip("\n")
        or len(contexts) != CONTROL_TURNS
        or any(row.get("model") != model or row.get("effort") != "medium" for row in contexts)
        or len(usage_rows) != CONTROL_TURNS
        or len(usages) != CONTROL_TURNS
        or any(
            row.get("session_id") != session
            or row.get("turn_id") != contexts[index].get("turn_id")
            or row.get("thread_token_usage", {}).get("input_tokens") != usages[index]["input_tokens"]
            or row.get("thread_token_usage", {}).get("output_tokens") != usages[index]["output_tokens"]
            for index, row in enumerate(usage_rows)
        )
        or source.has_tool_use(events)
        or _retry_markers(events, b"")
    ):
        raise ControlError("control rollout identity, model, arm, or turn count differs")
    return sha(paths[0])


def _command(executable: str, scratch: Path, arm: str, model: str, prompt: str, resume: str | None) -> list[str]:
    command = [
        executable,
        "exec",
        "--disable",
        "memories",
        "--disable",
        "multi_agent",
        "-c",
        'web_search="disabled"',
        "-s",
        "read-only",
        "--ignore-user-config",
        "--ignore-rules",
        "-C",
        str(scratch),
        "-c",
        f'model_instructions_file="{HERE / "arms" / f"{arm}.architect.system.txt"}"',
    ]
    if resume:
        command += ["resume", "--json", "--skip-git-repo-check", resume]
    else:
        command += ["--json", "--skip-git-repo-check"]
    return [*command, "-m", model, "-c", 'model_reasoning_effort="medium"', prompt]


def _retry_markers(events: list[dict[str, Any]], stderr: bytes) -> bool:
    """Detect CLI-visible retries and errors without claiming transport visibility."""
    if RETRY_MARKER.search(stderr.decode("utf-8", errors="replace")):
        return True
    return any(
        RETRY_MARKER.search(str(item.get(key, "")))
        for event in events
        for item in source._walk(event)
        for key in ("type", "event", "event_type", "status", "error", "detail", "reason")
    )


def run() -> dict[str, Any]:
    """Execute the exact control phase once, stopping terminally on any failure."""
    offline_preflight()
    verify_approval(dispatch=True)
    executable = str(EXECUTABLE.resolve())
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=False)
    header = {
        "record_type": "p3_v3_controls_ledger",
        "schema": 1,
        "seal_sha256": sha(SEAL),
        "approval_sha256": sha(APPROVAL),
        "opening_record_sha256": sha(accounting.OPENING),
        "opening_codex_tokens": accounting.CHARGED_OPENING,
    }
    LEDGER.write_text(json.dumps(header, sort_keys=True) + "\n", encoding="utf-8")
    LEDGER.chmod(stat.S_IRUSR | stat.S_IWUSR)
    case = read(CASE)
    result = []
    occupied_ids = _occupied_ids()
    for index, (arm, tier, model) in enumerate(CELLS):
        accounting.verify_opening_record()
        cell_root = RUNTIME / f"control-{index}"
        scratch, home, output = (cell_root / name for name in ("scratch", "home", "output"))
        for path in (scratch, home, output, cell_root / "tmp"):
            path.mkdir(mode=0o700, parents=True, exist_ok=False)
        auth = home / "auth.json"
        shutil.copyfile(AUTH_SOURCE, auth)
        auth.chmod(stat.S_IRUSR | stat.S_IWUSR)
        env = source._codex_child_environment(home, cell_root / "tmp")
        version = subprocess.run(
            [executable, "--version"], env=env, capture_output=True, text=True, check=False, timeout=30
        )
        if version.returncode or version.stdout.strip() != CLI_VERSION or version.stderr.strip():
            raise ControlError("Codex CLI differs from frozen pin")
        account_receipt = quota.account_limit_receipt(executable, home)
        run_id = ledger.fresh_id(occupied_ids)
        occupied_ids.add(run_id)
        attempt_id = ledger.fresh_id(occupied_ids)
        occupied_ids.add(attempt_id)
        source._create(
            output / f"{run_id}.attempt.json",
            {
                "run_id": run_id,
                "subject_attempt_id": attempt_id,
                "case": "P3-01",
                "arm": arm,
                "tier": tier,
                "repeat": 1,
                "attempt_class": "technical",
                "model": model,
                "effort": "medium",
                "provenance_scope": "evaluator_only",
            },
        )
        replies = []
        usages = []
        turn_evidence = []
        session = None
        for turn_num in (1, 2):
            try:
                accounting.verify_opening_record()
                prompt = case["subject"]["turn1"] if turn_num == 1 else source._second_prompt(case, replies[0])[2]
                cap = 40_000 if arm == "A" else 50_000
                snapshot = quota.read_quota_snapshot(codex_executable=executable, codex_home=home, environment=env)
                ledger.validate_quota(snapshot, "codex")
                if (
                    snapshot["account_limit_receipt"] != account_receipt
                    or account_receipt["account_id_sha256"] != ACCOUNT_ID_SHA
                ):
                    raise ControlError("quota account differs from bound source/route account")
                used, occupied = _usage_state()
                require_budget(used, cap)
                call_id = ledger.fresh_id(occupied_ids | occupied)
                occupied_ids.add(call_id)
                _append(
                    {
                        "event": "reserved",
                        "call_id": call_id,
                        "attempt_id": attempt_id,
                        "run_id": run_id,
                        "cell": index,
                        "turn": turn_num,
                        "quota": snapshot,
                        "opening_record_sha256": sha(accounting.OPENING),
                    }
                )
            except BaseException as exc:
                source._create(
                    output / f"{run_id}.failure.json",
                    {
                        "terminal": True,
                        "retry_authorized": False,
                        "failure_code": type(exc).__name__,
                    },
                )
                raise
            prefix = output / f"{run_id}.turn{turn_num}"
            usage = None
            call_closed = False
            try:
                events, _raw = source._invoke(
                    _command(executable, scratch, arm, model, prompt, session),
                    cwd=scratch,
                    codex_home=home,
                    tmp=cell_root / "tmp",
                    artifact_base=prefix,
                    environment=env,
                )
                usage = source.extract_usage(events)
                if (
                    usage["input_tokens"] > cap
                    or source.has_tool_use(events)
                    or _retry_markers(events, Path(f"{prefix}.stderr.txt").read_bytes())
                ):
                    raise ControlError("control input cap, no-tool, or observed-no-retry condition failed")
                observed_session = source.thread_id(events)
                if session is not None and session != observed_session:
                    raise ControlError("control second turn changed session")
                session = observed_session
                reply = source.assistant_reply(events)
                evidence_hashes = {
                    "events_sha256": sha(Path(f"{prefix}.events.json")),
                    "dispatch_sha256": sha(Path(f"{prefix}.dispatch.json")),
                    "stdout_sha256": sha(Path(f"{prefix}.stdout.txt")),
                }
                _append(
                    {
                        "event": "completed",
                        "call_id": call_id,
                        "attempt_id": attempt_id,
                        "run_id": run_id,
                        "cell": index,
                        "turn": turn_num,
                        "usage_status": "known",
                        **usage,
                        "session_id": session,
                        **evidence_hashes,
                        "outcome": "accepted",
                    }
                )
                call_closed = True
                replies.append(reply)
                usages.append(usage)
                turn_evidence.append({"call_id": call_id, "turn": turn_num, **evidence_hashes})
                if _usage_state()[0] > ledger.CODEX_LIMIT:
                    raise ControlError("completed control call exceeded the V3 Codex ceiling")
            except BaseException as exc:
                if not call_closed:
                    _append(
                        {
                            "event": "completed",
                            "call_id": call_id,
                            "attempt_id": attempt_id,
                            "run_id": run_id,
                            "cell": index,
                            "turn": turn_num,
                            "usage_status": "known" if usage else ledger.UNKNOWN_USAGE,
                            "input_tokens": usage["input_tokens"] if usage else None,
                            "output_tokens": usage["output_tokens"] if usage else None,
                            "outcome": "failed",
                            "failure_code": type(exc).__name__,
                        }
                    )
                source._create(
                    output / f"{run_id}.failure.json",
                    {
                        "terminal": True,
                        "retry_authorized": False,
                        "failure_code": type(exc).__name__,
                    },
                )
                raise
        if session is None:
            raise ControlError("control session was not established")
        try:
            rollout_sha = _verify_rollout(home, session, model, arm, scratch, usages)
        except BaseException as exc:
            source._create(
                output / f"{run_id}.failure.json",
                {
                    "terminal": True,
                    "retry_authorized": False,
                    "failure_code": type(exc).__name__,
                },
            )
            raise
        exchange = {
            "run_id": run_id,
            "turns": replies,
            "usage": usages,
            "turn_evidence": turn_evidence,
            "case_sha256": sha(CASE),
            "arm_sha256": sha(HERE / "arms" / f"{arm}.architect.system.txt"),
            "rollout_sha256": rollout_sha,
        }
        source._create(output / f"{run_id}.exchange.json", exchange)
        source._create(
            output / f"{run_id}.record.json",
            {
                "run_id": run_id,
                "subject_attempt_id": attempt_id,
                "case": "P3-01",
                "arm": arm,
                "tier": tier,
                "model": model,
                "effort": "medium",
                "exchange_sha256": sha(output / f"{run_id}.exchange.json"),
                "rollout_sha256": rollout_sha,
                "verified": True,
                "provenance_scope": "evaluator_only",
                "scored_p3": False,
            },
        )
        result.append({"arm": arm, "tier": tier, "run_id": run_id})
    charged, calls = _usage_state()
    if len(calls) != len(CELLS) * CONTROL_TURNS or charged > ledger.CODEX_LIMIT:
        raise ControlError("completed controls exceed call count or V3 ceiling")
    return {"status": "PASSED_TECHNICAL_CONTROLS", "controls": result, "charged_codex_tokens": charged}


def main() -> None:
    """Show offline preflight unless explicitly invoked for approved execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        value = run() if args.execute else offline_preflight()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
