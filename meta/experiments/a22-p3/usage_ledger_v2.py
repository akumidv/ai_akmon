#!/usr/bin/env python3
"""Offline append-only attempt and actual-usage ledger for A22 P3 V2.

This module has no provider or dispatch path. Reservations count toward the 240
attempt allowance. The token envelope is planning metadata only; post-hoc usage
cannot provide a provider-enforced hard cap.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PLAN = HERE / "RUN_PLAN_V2_PROPOSAL.md"
PACKET_SEAL = HERE / "seal.json"
APPROVAL = HERE / "runs" / "owner-approval-v2.json"
LEDGER = HERE / "runs" / "scorer-usage-v2.jsonl"
MAX_ATTEMPTS = 240
PLANNED_ENVELOPE_TOKENS = 5_040_000
ATTEMPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ROUTES = {"codex", "qwen"}
RESOURCE_OPTIONS = {"usd25", "token_only"}
USAGE_PROVENANCE = "UNVERIFIED_NO_RUNNER_VALIDATION"


class LedgerError(ValueError):
    """A ledger integrity, state, or admission check failed."""


LedgerPaths = tuple[Path, Path, Path, Path]
DEFAULT_PATHS: LedgerPaths = (LEDGER, PLAN, PACKET_SEAL, APPROVAL)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approval_snapshot(approval_path: Path, plan_path: Path) -> tuple[str, str]:
    raw = approval_path.read_bytes()
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LedgerError("V2 approval record is malformed") from exc
    choice = record.get("selected_resource_option") if isinstance(record, dict) else None
    if choice not in RESOURCE_OPTIONS:
        raise LedgerError("V2 approval has no selected resource option; ledger cannot initialize")
    if record.get("proposal_sha256") != _sha(plan_path):
        raise LedgerError("V2 approval is stale and does not bind the current proposal")
    if record.get("owner_accepted") is not True or record.get("dispatch_allowed") is not False:
        raise LedgerError("ledger requires a selected approval with dispatch still denied")
    if record.get("owner_acceptance_provenance") != "UNIMPLEMENTED":
        raise LedgerError("owner provenance remains unimplemented; ledger readiness is denied")
    return hashlib.sha256(raw).hexdigest(), choice


def _header(plan_path: Path = PLAN, packet_seal_path: Path = PACKET_SEAL,
            approval_path: Path = APPROVAL) -> dict[str, Any]:
    approval_sha256, selected_option = _approval_snapshot(approval_path, plan_path)
    return {
        "schema": 1,
        "record_type": "p3_v2_attempt_usage_ledger",
        "proposal_sha256": _sha(plan_path),
        "packet_seal_sha256": _sha(packet_seal_path),
        "approval_sha256": approval_sha256,
        "selected_resource_option": selected_option,
        "max_attempts": MAX_ATTEMPTS,
        "planned_accounting_envelope_tokens": PLANNED_ENVELOPE_TOKENS,
        "hard_token_cap_enforced": False,
        "usage_provenance_status": USAGE_PROVENANCE,
        "dispatch_readiness": "DENIED_UNVERIFIED_OWNER_AND_USAGE_PROVENANCE",
    }


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(fd, payload[offset:])


def _lock(path: Path) -> int:
    lock_path = path.with_name(path.name + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _unlock(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def initialize(paths: LedgerPaths = DEFAULT_PATHS) -> dict[str, Any]:
    """Create a new header-only ledger exclusively; never overwrite an existing file."""
    path, plan_path, packet_seal_path, approval_path = paths
    header = _header(plan_path, packet_seal_path, approval_path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(fd, (json.dumps(header, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return header


def _usage_valid(usage: object) -> bool:
    return (
        isinstance(usage, dict)
        and set(usage) == {"input_tokens", "output_tokens"}
        and all(isinstance(usage[k], int) and not isinstance(usage[k], bool) and usage[k] >= 0
                for k in ("input_tokens", "output_tokens"))
    )


def _usage_artifact_valid(artifact: object) -> bool:
    fields = {"artifact_path", "artifact_sha256", "request_id", "session_id", "model_id"}
    if not isinstance(artifact, dict) or set(artifact) != fields:
        return False
    if any(not isinstance(artifact[field], str) or not artifact[field].strip()
           for field in fields - {"artifact_sha256"}):
        return False
    return re.fullmatch(r"[0-9a-f]{64}", artifact["artifact_sha256"]) is not None


def _records(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise LedgerError("ledger ends with an incomplete record")
    try:
        records = [json.loads(line) for line in raw.splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LedgerError("ledger contains malformed JSON") from exc
    return records


def _apply_reservation(seq: int, event: dict[str, Any], states: dict[str, dict[str, Any]]) -> None:
    if set(event) != {
            "seq", "event", "attempt_id", "route", "created_utc", "approval_sha256", "selected_resource_option"}:
        raise LedgerError("reservation record has an unexpected shape")
    attempt_id = event["attempt_id"]
    if attempt_id in states or event["route"] not in ROUTES or not isinstance(event["created_utc"], str):
        raise LedgerError("reservation is duplicate or malformed")
    states[attempt_id] = {"state": "unresolved", "route": event["route"], "seq": seq}


def _validate_accepted_completion(usage: object, artifact: object, failure_code: object) -> None:
    if not _usage_valid(usage) or not _usage_artifact_valid(artifact):
        raise LedgerError("accepted attempt lacks structured usage artifact and correlation metadata")
    if failure_code is not None:
        raise LedgerError("accepted completion has a failure code")


def _validate_failed_completion(usage: object, artifact: object, failure_code: object) -> None:
    if failure_code not in {"attempt_failed", "missing_usage", "invalid_usage"}:
        raise LedgerError("failed completion has an unknown failure code")
    if usage is None and artifact is not None:
        raise LedgerError("usage artifact exists without actual usage")
    if usage is not None and (not _usage_valid(usage) or
                              (artifact is not None and not _usage_artifact_valid(artifact))):
        raise LedgerError("failed attempt usage evidence is malformed")


def _validate_completion_values(outcome: str, usage: object, artifact: object,
                               provenance: object, failure_code: object) -> None:
    if provenance != USAGE_PROVENANCE:
        raise LedgerError("usage provenance must remain explicitly unverified until runner validation")
    if outcome == "accepted":
        _validate_accepted_completion(usage, artifact, failure_code)
    elif outcome == "failed":
        _validate_failed_completion(usage, artifact, failure_code)
    else:
        raise LedgerError("completion outcome is invalid")


def _apply_completion(event: dict[str, Any], states: dict[str, dict[str, Any]]) -> None:
    if set(event) != {
            "seq", "event", "attempt_id", "approval_sha256", "selected_resource_option",
            "outcome", "actual_usage", "usage_artifact", "usage_provenance_status", "failure_code"}:
        raise LedgerError("completion record has an unexpected shape")
    current = states.get(event["attempt_id"])
    if current is None or current["state"] != "unresolved":
        raise LedgerError("completion has no unique unresolved reservation")
    _validate_completion_values(
        event["outcome"], event["actual_usage"], event["usage_artifact"],
        event["usage_provenance_status"], event["failure_code"]
    )
    current.update({"state": event["outcome"], "actual_usage": event["actual_usage"],
                    "usage_provenance_status": event["usage_provenance_status"]})


def _read(path: Path, plan_path: Path, packet_seal_path: Path, approval_path: Path) -> tuple[
        dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    records = _records(path)
    if not records or records[0] != _header(plan_path, packet_seal_path, approval_path):
        raise LedgerError("ledger header is stale or does not bind current proposal, packet seal, and approval")
    states: dict[str, dict[str, Any]] = {}
    events = records[1:]
    for seq, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("seq") != seq:
            raise LedgerError("ledger sequence is malformed or non-monotonic")
        attempt_id = event.get("attempt_id")
        if not isinstance(attempt_id, str) or ATTEMPT_ID_RE.fullmatch(attempt_id) is None:
            raise LedgerError("attempt id is malformed")
        if event.get("event") == "reserved":
            if event.get("approval_sha256") != records[0]["approval_sha256"] or event.get(
                    "selected_resource_option") != records[0]["selected_resource_option"]:
                raise LedgerError("reservation does not bind the ledger approval and selected option")
            _apply_reservation(seq, event, states)
        elif event.get("event") == "completed":
            if event.get("approval_sha256") != records[0]["approval_sha256"] or event.get(
                    "selected_resource_option") != records[0]["selected_resource_option"]:
                raise LedgerError("completion does not bind the ledger approval and selected option")
            _apply_completion(event, states)
        else:
            raise LedgerError("ledger event type is invalid")
    return records[0], events, states


def _append(path: Path, event: dict[str, Any]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        _write_all(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def _observed_tokens(states: dict[str, dict[str, Any]]) -> int:
    return sum(
        state["actual_usage"]["input_tokens"] + state["actual_usage"]["output_tokens"]
        for state in states.values() if state.get("actual_usage") is not None
    )


def reserve_attempt(route: str, paths: LedgerPaths = DEFAULT_PATHS,
                    attempt_id: str | None = None) -> str:
    """Atomically reserve one counted attempt if no prior reservation is unresolved or failed."""
    if route not in ROUTES:
        raise LedgerError("route must be codex or qwen")
    path, plan_path, packet_seal_path, approval_path = paths
    candidate = attempt_id or secrets.token_hex(16)
    if ATTEMPT_ID_RE.fullmatch(candidate) is None:
        raise LedgerError("attempt id must be 128-bit lowercase opaque hex")
    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
        count = len(states)
        if count >= MAX_ATTEMPTS:
            raise LedgerError("240-attempt allowance is exhausted")
        if _observed_tokens(states) > PLANNED_ENVELOPE_TOKENS:
            raise LedgerError("observed aggregate exceeds the planned token envelope")
        if any(state["state"] != "accepted" for state in states.values()):
            raise LedgerError("unresolved or failed attempt blocks new reservations")
        if candidate in states:
            raise LedgerError("attempt id was already used")
        event = {
            "seq": len(events) + 1,
            "event": "reserved",
            "attempt_id": candidate,
            "route": route,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "approval_sha256": header["approval_sha256"],
            "selected_resource_option": header["selected_resource_option"],
        }
        _append(path, event)
        return candidate
    finally:
        _unlock(lock_fd)


def _normalize_completion(outcome: str, actual_usage: object, usage_artifact: object,
                          failure_code: str | None) -> tuple[str, object, object, str | None, str | None]:
    normalized_outcome = outcome
    normalized_usage = actual_usage
    normalized_artifact = usage_artifact
    normalized_failure = failure_code
    invalid_acceptance: str | None = None
    if outcome == "accepted" and (not _usage_valid(actual_usage) or not _usage_artifact_valid(usage_artifact)):
        normalized_outcome = "failed"
        normalized_artifact = None
        normalized_failure = "missing_usage" if actual_usage is None else "invalid_usage"
        if not _usage_valid(actual_usage):
            normalized_usage = None
        invalid_acceptance = "accepted attempt without structured usage metadata was recorded as failed"
    elif outcome == "failed":
        normalized_failure = failure_code or "attempt_failed"
        if normalized_failure not in {"attempt_failed", "missing_usage", "invalid_usage"}:
            raise LedgerError("failure_code is invalid")
        if actual_usage is not None and not _usage_valid(actual_usage):
            normalized_usage = None
            normalized_failure = "invalid_usage"
        if normalized_artifact is not None and not _usage_artifact_valid(normalized_artifact):
            normalized_artifact = None
            normalized_failure = "invalid_usage"
    return normalized_outcome, normalized_usage, normalized_artifact, normalized_failure, invalid_acceptance


def complete_attempt(attempt_id: str, *, outcome: str, actual_usage: object = None,  # noqa: PLR0913
                     usage_artifact: object = None, failure_code: str | None = None,
                     paths: LedgerPaths = DEFAULT_PATHS) -> dict[str, Any]:
    """Append one terminal outcome; missing/invalid usage is durably recorded as failed."""
    path, plan_path, packet_seal_path, approval_path = paths
    if outcome not in {"accepted", "failed"}:
        raise LedgerError("outcome must be accepted or failed")
    if ATTEMPT_ID_RE.fullmatch(attempt_id) is None:
        raise LedgerError("attempt id is malformed")
    (normalized_outcome, normalized_usage, normalized_artifact, normalized_failure,
     invalid_acceptance) = _normalize_completion(outcome, actual_usage, usage_artifact, failure_code)

    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
        state = states.get(attempt_id)
        if state is None or state["state"] != "unresolved":
            raise LedgerError("attempt has no unresolved reservation")
        event = {
            "seq": len(events) + 1,
            "event": "completed",
            "attempt_id": attempt_id,
            "approval_sha256": header["approval_sha256"],
            "selected_resource_option": header["selected_resource_option"],
            "outcome": normalized_outcome,
            "actual_usage": normalized_usage,
            "usage_artifact": normalized_artifact,
            "usage_provenance_status": USAGE_PROVENANCE,
            "failure_code": normalized_failure,
        }
        _append(path, event)
    finally:
        _unlock(lock_fd)
    if invalid_acceptance:
        raise LedgerError(invalid_acceptance)
    return event


def summary(paths: LedgerPaths = DEFAULT_PATHS) -> dict[str, Any]:
    """Return computed counts and observed usage; totals are accounting data, not hard caps."""
    path, plan_path, packet_seal_path, approval_path = paths
    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
    finally:
        _unlock(lock_fd)
    measured_input = measured_output = 0
    measured_attempts = 0
    for state in states.values():
        usage = state.get("actual_usage")
        if usage is not None:
            measured_attempts += 1
            measured_input += usage["input_tokens"]
            measured_output += usage["output_tokens"]
    return {
        "proposal_sha256": header["proposal_sha256"],
        "packet_seal_sha256": header["packet_seal_sha256"],
        "approval_sha256": header["approval_sha256"],
        "selected_resource_option": header["selected_resource_option"],
        "reserved_attempts": len(states),
        "accepted_attempts": sum(state["state"] == "accepted" for state in states.values()),
        "failed_attempts": sum(state["state"] == "failed" for state in states.values()),
        "unresolved_attempts": sum(state["state"] == "unresolved" for state in states.values()),
        "attempt_events": len(events),
        "measured_attempts": measured_attempts,
        "observed_input_tokens": measured_input,
        "observed_output_tokens": measured_output,
        "observed_total_tokens": measured_input + measured_output,
        "planned_accounting_envelope_tokens": PLANNED_ENVELOPE_TOKENS,
        "hard_token_cap_enforced": False,
        "usage_provenance_status": USAGE_PROVENANCE,
        "dispatch_readiness": "DENIED_UNVERIFIED_OWNER_AND_USAGE_PROVENANCE",
    }
