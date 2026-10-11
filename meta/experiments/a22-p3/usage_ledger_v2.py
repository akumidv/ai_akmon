#!/usr/bin/env python3
"""Offline append-only unified provider-usage and subject-attempt ledger for A22 P3 V2."""
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
LEDGER = HERE / "runs" / "provider-usage-v2.jsonl"
CODEX_AGGREGATE_LIMIT_TOKENS = 5_000_000
KNOWN_PRIOR_CODEX_USAGE_TOKENS = 153_614
CODEX_REMAINING_AT_START_TOKENS = CODEX_AGGREGATE_LIMIT_TOKENS - KNOWN_PRIOR_CODEX_USAGE_TOKENS
SCORER_READINGS_PER_ROUTE = 120
ATTEMPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ROUTES = {"codex", "qwen"}
ATTEMPT_CLASSES = {"scored_reading", "route_check", "subject_call"}
SUBJECT_CLASSES = {"scored", "technical", "defect"}
MAX_SCORED_SUBJECT_ATTEMPTS = 96
MAX_TECHNICAL_DEFECT_ATTEMPTS = 24
MAX_SUBJECT_ATTEMPTS = 120
HISTORICAL_SUBJECT_MARKERS = (
    "preflight-A-strongest-01", "preflight-A-strongest-03", "preflight-A-mid-01",
    "preflight-C-strongest-01", "preflight-C-mid-01",
)
MAX_INPUT_TOKENS_PER_CALL = 20_000
MAX_OUTPUT_TOKENS_PER_ROUTE = {"codex": 1_000, "qwen": 2_000}
RESOURCE_OPTIONS = {"usd25", "token_only"}
USAGE_PROVENANCE = "UNVERIFIED_NO_RUNNER_VALIDATION"
ACCOUNTING_SCOPE = "UNIFIED_SUBJECT_SCORER_ROUTE_CHECK_PROVIDER_CALLS"
DISPATCH_READINESS = "DENIED_UNTIL_FRESH_APPROVAL_SEAL_AND_ROUTE_VALIDATION"


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
    if choice != "token_only":
        raise LedgerError("USD 25 option is unsupported")
    option = record.get("options", {}).get("token_only")
    expected = {
        "codex_aggregate_limit_tokens": CODEX_AGGREGATE_LIMIT_TOKENS,
        "known_prior_codex_usage_tokens": KNOWN_PRIOR_CODEX_USAGE_TOKENS,
        "remaining_codex_tokens_at_approval": CODEX_REMAINING_AT_START_TOKENS,
        "qwen_aggregate_limit_tokens": None,
        "accepted_scorer_readings_per_route": SCORER_READINGS_PER_ROUTE,
    }
    if not isinstance(option, dict) or any(option.get(key) != value for key, value in expected.items()):
        raise LedgerError("selected approval does not bind the Codex-only limit and Qwen no-cap policy")
    if option.get("exploratory_calls_counted") is not True:
        raise LedgerError("approval must count exploratory calls in the prior Codex debit")
    return hashlib.sha256(raw).hexdigest(), choice


def _header(plan_path: Path = PLAN, packet_seal_path: Path = PACKET_SEAL,
            approval_path: Path = APPROVAL) -> dict[str, Any]:
    approval_sha256, selected_option = _approval_snapshot(approval_path, plan_path)
    return {
        "schema": 2,
        "record_type": "p3_v2_attempt_usage_ledger",
        "historical_subject_snapshot": {
            "marker_ids": list(HISTORICAL_SUBJECT_MARKERS),
            "count": len(HISTORICAL_SUBJECT_MARKERS),
            "class": "technical",
            "usage_tokens_in_prior_aggregate": 126_014,
            "provenance": "PROVENANCE_LIMITED_RECONSTRUCTED_NO_EVENT_LEVEL_LEDGER",
            "debit_again": False,
        },
        "proposal_sha256": _sha(plan_path),
        "packet_seal_sha256": _sha(packet_seal_path),
        "approval_sha256": approval_sha256,
        "selected_resource_option": selected_option,
        "accounting_scope": ACCOUNTING_SCOPE,
        "codex_aggregate_limit_tokens": CODEX_AGGREGATE_LIMIT_TOKENS,
        "known_prior_codex_usage_tokens": KNOWN_PRIOR_CODEX_USAGE_TOKENS,
        "codex_remaining_at_start_tokens": CODEX_REMAINING_AT_START_TOKENS,
        "qwen_aggregate_limit_tokens": None,
        "accepted_scorer_readings_per_route": SCORER_READINGS_PER_ROUTE,
        "max_input_tokens_per_call": MAX_INPUT_TOKENS_PER_CALL,
        "max_output_tokens_per_route": MAX_OUTPUT_TOKENS_PER_ROUTE,
        "hard_token_cap_enforced": False,
        "usage_provenance_status": USAGE_PROVENANCE,
        "dispatch_readiness": DISPATCH_READINESS,
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


def _canonical_sha(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _chain_seed(header: dict[str, Any]) -> str:
    return _canonical_sha(header)


def _event_body(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items()
            if key not in {"previous_event_sha256", "event_sha256"}}


def _apply_reservation(seq: int, event: dict[str, Any], states: dict[str, dict[str, Any]]) -> None:
    base_fields = {
            "seq", "event", "attempt_id", "route", "attempt_class", "created_utc",
            "approval_sha256", "selected_resource_option"}
    subject_fields = {"subject_attempt_id", "turn_id", "continuation_id"}
    if set(event) not in (base_fields, base_fields | subject_fields):
        raise LedgerError("reservation record has an unexpected shape")
    attempt_id = event["attempt_id"]
    if (attempt_id in states or event["route"] not in ROUTES or
            event["attempt_class"] not in ATTEMPT_CLASSES or not isinstance(event["created_utc"], str)):
        raise LedgerError("reservation is duplicate or malformed")
    if event["attempt_class"] == "subject_call":
        if set(event) != base_fields | subject_fields:
            raise LedgerError("subject provider call lacks parent/turn linkage")
        subject = states.get("subject:" + event["subject_attempt_id"])
        if subject is None or subject.get("kind") != "subject":
            raise LedgerError("subject provider call has no registered parent attempt")
        if not isinstance(event["turn_id"], str) or not event["turn_id"].strip():
            raise LedgerError("subject provider call has no turn ID")
        if event["continuation_id"] is not None and not isinstance(event["continuation_id"], str):
            raise LedgerError("subject continuation ID is malformed")
    states[attempt_id] = {
        "kind": "provider",
        "state": "unresolved", "route": event["route"],
        "attempt_class": event["attempt_class"], "seq": seq,
        **({"subject_attempt_id": event["subject_attempt_id"], "turn_id": event["turn_id"],
            "continuation_id": event["continuation_id"]} if event["attempt_class"] == "subject_call" else {}),
    }


def _validate_accepted_completion(usage: object, artifact: object, failure_code: object,
                                  ledger_path: Path) -> None:
    if not _usage_valid(usage) or not _usage_artifact_valid(artifact):
        raise LedgerError("accepted attempt lacks structured usage artifact and correlation metadata")
    if failure_code is not None:
        raise LedgerError("accepted completion has a failure code")
    artifact_path = Path(artifact["artifact_path"])
    if artifact_path.is_absolute() or ".." in artifact_path.parts:
        raise LedgerError("usage artifact path escapes the ledger directory")
    resolved_path = ledger_path.parent / artifact_path
    try:
        raw = resolved_path.read_bytes()
        saved = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LedgerError("usage artifact is missing or malformed") from exc
    if (hashlib.sha256(raw).hexdigest() != artifact["artifact_sha256"] or
            not isinstance(saved, dict) or saved.get("usage") != usage or
            saved.get("request_id") != artifact["request_id"] or
            saved.get("session_id") != artifact["session_id"] or
            saved.get("model_id") != artifact["model_id"]):
        raise LedgerError("usage artifact hash or request/session/model correlation does not match")


def _validate_failed_completion(usage: object, artifact: object, failure_code: object) -> None:
    if failure_code not in {"attempt_failed", "missing_usage", "invalid_usage", "per_call_limit_breach"}:
        raise LedgerError("failed completion has an unknown failure code")
    if usage is None and artifact is not None:
        raise LedgerError("usage artifact exists without actual usage")
    if usage is not None and (not _usage_valid(usage) or
                              (artifact is not None and not _usage_artifact_valid(artifact))):
        raise LedgerError("failed attempt usage evidence is malformed")


def _validate_completion_values(route: str, attempt_class: str, event: dict[str, Any],
                                ledger_path: Path) -> None:
    outcome = event["outcome"]
    usage = event["actual_usage"]
    artifact = event["usage_artifact"]
    failure_code = event["failure_code"]
    if event["usage_provenance_status"] != USAGE_PROVENANCE:
        raise LedgerError("usage provenance must remain explicitly unverified until runner validation")
    if outcome == "accepted":
        scorer_breach = attempt_class != "subject_call" and _usage_valid(usage) and (
            usage["input_tokens"] > MAX_INPUT_TOKENS_PER_CALL or
            usage["output_tokens"] > MAX_OUTPUT_TOKENS_PER_ROUTE[route]
        )
        if not _usage_valid(usage) or scorer_breach:
            raise LedgerError("accepted completion exceeds a route per-call allowance")
        _validate_accepted_completion(usage, artifact, failure_code, ledger_path)
    elif outcome == "failed":
        if attempt_class != "subject_call" and failure_code == "per_call_limit_breach" and (
                not _usage_valid(usage) or (
                    usage["input_tokens"] <= MAX_INPUT_TOKENS_PER_CALL and
                    usage["output_tokens"] <= MAX_OUTPUT_TOKENS_PER_ROUTE[route]
                )):
            raise LedgerError("per-call breach record does not exceed the route allowance")
        _validate_failed_completion(usage, artifact, failure_code)
    else:
        raise LedgerError("completion outcome is invalid")


def _apply_completion(event: dict[str, Any], states: dict[str, dict[str, Any]], ledger_path: Path) -> None:
    if set(event) != {
            "seq", "event", "attempt_id", "approval_sha256", "selected_resource_option",
            "outcome", "actual_usage", "usage_artifact", "usage_provenance_status", "failure_code"}:
        raise LedgerError("completion record has an unexpected shape")
    current = states.get(event["attempt_id"])
    if current is None or current["state"] != "unresolved":
        raise LedgerError("completion has no unique unresolved reservation")
    _validate_completion_values(current["route"], current["attempt_class"], event, ledger_path)
    if event["outcome"] == "accepted" and current["attempt_class"] == "scored_reading":
        accepted = sum(state.get("kind") == "provider" and state["route"] == current["route"] and
                       state["attempt_class"] == "scored_reading" and
                       state["state"] == "accepted" for state in states.values())
        if accepted >= SCORER_READINGS_PER_ROUTE:
            raise LedgerError("ledger contains more than 120 accepted scored readings for a route")
    current.update({"state": event["outcome"], "actual_usage": event["actual_usage"],
                    "usage_provenance_status": event["usage_provenance_status"],
                    "failure_code": event["failure_code"]})


def _validate_event_chain(event: object, seq: int, previous_hash: str) -> tuple[dict[str, Any], str]:
    if not isinstance(event, dict) or event.get("seq") != seq:
        raise LedgerError("ledger sequence is malformed or non-monotonic")
    body = _event_body(event)
    hash_payload = {key: value for key, value in event.items() if key != "event_sha256"}
    chain_matches = (
        event.get("previous_event_sha256") == previous_hash and
        event.get("event_sha256") == _canonical_sha(hash_payload)
    )
    if not chain_matches:
        raise LedgerError("ledger event hash chain is invalid")
    return body, event["event_sha256"]


def _apply_replay_event(seq: int, body: dict[str, Any], header: dict[str, Any],
                        states: dict[str, dict[str, Any]], ledger_path: Path) -> None:
    if body.get("approval_sha256") != header["approval_sha256"] or body.get(
            "selected_resource_option") != header["selected_resource_option"]:
        raise LedgerError("ledger event does not bind the ledger approval and selected option")
    if body.get("event") == "subject_registered":
        required = {"seq", "event", "subject_attempt_id", "attempt_class", "origin_attempt_id",
                    "created_utc", "approval_sha256", "selected_resource_option"}
        subject_id = body.get("subject_attempt_id")
        if set(body) != required or ATTEMPT_ID_RE.fullmatch(subject_id or "") is None:
            raise LedgerError("subject registration record is malformed")
        if body.get("attempt_class") not in SUBJECT_CLASSES or "subject:" + subject_id in states:
            raise LedgerError("subject registration is duplicate or has an invalid class")
        origin = body.get("origin_attempt_id")
        if body["attempt_class"] == "defect":
            source = states.get("subject:" + str(origin))
            if not isinstance(origin, str) or source is None or source.get("kind") != "subject":
                raise LedgerError("defect attempt origin is not an earlier registered subject attempt")
        elif origin is not None:
            raise LedgerError("only defect attempts may name an origin")
        subject_attempts = [state for state in states.values() if state.get("kind") == "subject"]
        scored = sum(state["attempt_class"] == "scored" for state in subject_attempts)
        technical_defect = sum(state["attempt_class"] in {"technical", "defect"}
                               for state in subject_attempts) + len(HISTORICAL_SUBJECT_MARKERS)
        if len(subject_attempts) + len(HISTORICAL_SUBJECT_MARKERS) >= MAX_SUBJECT_ATTEMPTS:
            raise LedgerError("subject attempt allowance of 120 is exhausted")
        if body["attempt_class"] == "scored" and scored >= MAX_SCORED_SUBJECT_ATTEMPTS:
            raise LedgerError("scored subject attempt allowance of 96 is exhausted")
        if body["attempt_class"] in {"technical", "defect"} and technical_defect >= MAX_TECHNICAL_DEFECT_ATTEMPTS:
            raise LedgerError("technical plus defect subject attempt allowance of 24 is exhausted")
        states["subject:" + subject_id] = {
            "kind": "subject", "subject_attempt_id": subject_id, "attempt_class": body["attempt_class"],
            "origin_attempt_id": origin, "state": "registered", "seq": seq,
        }
        return
    attempt_id = body.get("attempt_id")
    if not isinstance(attempt_id, str) or ATTEMPT_ID_RE.fullmatch(attempt_id) is None:
        raise LedgerError("attempt id is malformed")
    if body.get("event") == "reserved":
        if any(state.get("kind") == "provider" and state["state"] == "unresolved" for state in states.values()):
            raise LedgerError("ledger reserves an attempt while another attempt is unresolved")
        if any(state.get("kind") == "provider" and state["route"] == body.get("route") and state["state"] == "failed"
               for state in states.values()):
            raise LedgerError("ledger reserves an attempt after the route was stopped")
        if (body.get("route") == "codex" and
                KNOWN_PRIOR_CODEX_USAGE_TOKENS + _observed_tokens(states, "codex")
                >= CODEX_AGGREGATE_LIMIT_TOKENS):
            raise LedgerError("ledger reserves Codex after its observed aggregate limit")
        _apply_reservation(seq, body, states)
    elif body.get("event") == "completed":
        _apply_completion(body, states, ledger_path)
    else:
        raise LedgerError("ledger event type is invalid")


def _read(path: Path, plan_path: Path, packet_seal_path: Path, approval_path: Path) -> tuple[
        dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    records = _records(path)
    if not records or records[0] != _header(plan_path, packet_seal_path, approval_path):
        raise LedgerError("ledger header is stale or does not bind current proposal, packet seal, and approval")
    states: dict[str, dict[str, Any]] = {}
    events = records[1:]
    previous_hash = _chain_seed(records[0])
    for seq, event in enumerate(events, start=1):
        body, previous_hash = _validate_event_chain(event, seq, previous_hash)
        _apply_replay_event(seq, body, records[0], states, path)
    return records[0], events, states


def _append(path: Path, event: dict[str, Any], previous_hash: str) -> dict[str, Any]:
    event = dict(event)
    event["previous_event_sha256"] = previous_hash
    event["event_sha256"] = _canonical_sha(event)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        _write_all(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return event


def _tail_hash(header: dict[str, Any], events: list[dict[str, Any]]) -> str:
    return events[-1]["event_sha256"] if events else _chain_seed(header)


def _observed_tokens(states: dict[str, dict[str, Any]], route: str) -> int:
    return sum(
        state["actual_usage"]["input_tokens"] + state["actual_usage"]["output_tokens"]
        for state in states.values() if state.get("route") == route and state.get("actual_usage") is not None
    )


def reserve_attempt(route: str, attempt_class: str, paths: LedgerPaths = DEFAULT_PATHS,
                    attempt_id: str | None = None) -> str:
    """Atomically reserve an explicitly classified attempt after route and budget checks."""
    if not isinstance(route, str) or route not in ROUTES:
        raise LedgerError("route must be codex or qwen")
    if not isinstance(attempt_class, str) or attempt_class not in {"scored_reading", "route_check"}:
        raise LedgerError("scorer attempt_class must be scored_reading or route_check")
    path, plan_path, packet_seal_path, approval_path = paths
    candidate = attempt_id or secrets.token_hex(16)
    if ATTEMPT_ID_RE.fullmatch(candidate) is None:
        raise LedgerError("attempt id must be 128-bit lowercase opaque hex")
    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
        accepted_readings = sum(
            state.get("kind") == "provider" and state["route"] == route and state["attempt_class"] == "scored_reading" and
            state["state"] == "accepted" for state in states.values()
        )
        if attempt_class == "scored_reading" and accepted_readings >= SCORER_READINGS_PER_ROUTE:
            raise LedgerError(f"{route} accepted scorer-reading allowance is exhausted")
        if route == "codex" and (
                KNOWN_PRIOR_CODEX_USAGE_TOKENS + _observed_tokens(states, "codex")
                >= CODEX_AGGREGATE_LIMIT_TOKENS):
            raise LedgerError("observed Codex aggregate reached the 5,000,000-token limit")
        if any(state.get("kind") == "provider" and state["state"] == "unresolved" for state in states.values()):
            raise LedgerError("unresolved attempt blocks new reservations")
        if any(state.get("kind") == "provider" and state["route"] == route and state["state"] == "failed" for state in states.values()):
            raise LedgerError(f"{route} route is stopped by a prior failed attempt")
        if candidate in states:
            raise LedgerError("attempt id was already used")
        event = {
            "seq": len(events) + 1,
            "event": "reserved",
            "attempt_id": candidate,
            "route": route,
            "attempt_class": attempt_class,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "approval_sha256": header["approval_sha256"],
            "selected_resource_option": header["selected_resource_option"],
        }
        _append(path, event, _tail_hash(header, events))
        return candidate
    finally:
        _unlock(lock_fd)


def register_subject_attempt(attempt_id: str | None, attempt_class: str, *,
                             origin_attempt_id: str | None = None,
                             paths: LedgerPaths = DEFAULT_PATHS) -> str:
    """Register one subject slot before any model call; IDs are immutable 128-bit hex."""
    if not isinstance(attempt_class, str) or attempt_class not in SUBJECT_CLASSES:
        raise LedgerError("subject attempt_class must be scored, technical, or defect")
    candidate = attempt_id or secrets.token_hex(16)
    if not isinstance(candidate, str) or ATTEMPT_ID_RE.fullmatch(candidate) is None:
        raise LedgerError("subject attempt id must be 128-bit lowercase opaque hex")
    if attempt_class == "defect":
        if not isinstance(origin_attempt_id, str) or ATTEMPT_ID_RE.fullmatch(origin_attempt_id) is None:
            raise LedgerError("defect attempt requires an immutable origin attempt ID")
    elif origin_attempt_id is not None:
        raise LedgerError("only a defect attempt may have an origin attempt ID")
    path, plan_path, packet_seal_path, approval_path = paths
    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
        key = "subject:" + candidate
        if key in states:
            raise LedgerError("subject attempt id was already registered")
        subject_states = [state for state in states.values() if state.get("kind") == "subject"]
        if attempt_class == "defect" and "subject:" + str(origin_attempt_id) not in states:
            raise LedgerError("defect attempt origin must be an earlier registered subject attempt")
        if len(subject_states) + len(HISTORICAL_SUBJECT_MARKERS) >= MAX_SUBJECT_ATTEMPTS:
            raise LedgerError("subject attempt allowance of 120 is exhausted")
        if attempt_class == "scored" and sum(state["attempt_class"] == "scored" for state in subject_states) >= MAX_SCORED_SUBJECT_ATTEMPTS:
            raise LedgerError("scored subject attempt allowance of 96 is exhausted")
        if attempt_class in {"technical", "defect"} and sum(
                state["attempt_class"] in {"technical", "defect"} for state in subject_states
        ) + len(HISTORICAL_SUBJECT_MARKERS) >= MAX_TECHNICAL_DEFECT_ATTEMPTS:
            raise LedgerError("technical plus defect subject attempt allowance of 24 is exhausted")
        event = {
            "seq": len(events) + 1,
            "event": "subject_registered",
            "subject_attempt_id": candidate,
            "attempt_class": attempt_class,
            "origin_attempt_id": origin_attempt_id,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "approval_sha256": header["approval_sha256"],
            "selected_resource_option": header["selected_resource_option"],
        }
        _append(path, event, _tail_hash(header, events))
        return candidate
    finally:
        _unlock(lock_fd)


def reserve_subject_call(subject_attempt_id: str, turn_id: str, *,
                         continuation_id: str | None = None, route: str = "codex",
                         paths: LedgerPaths = DEFAULT_PATHS, call_id: str | None = None) -> str:
    """Reserve one provider dispatch, correlated to its parent subject attempt and turn."""
    if route not in ROUTES:
        raise LedgerError("route must be codex or qwen")
    if not isinstance(turn_id, str) or not turn_id.strip():
        raise LedgerError("turn_id must be a nonempty string")
    if continuation_id is not None and (not isinstance(continuation_id, str) or not continuation_id.strip()):
        raise LedgerError("continuation_id must be null or a nonempty string")
    candidate = call_id or secrets.token_hex(16)
    if not isinstance(candidate, str) or ATTEMPT_ID_RE.fullmatch(candidate) is None:
        raise LedgerError("provider call id must be 128-bit lowercase opaque hex")
    path, plan_path, packet_seal_path, approval_path = paths
    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
        if "subject:" + subject_attempt_id not in states:
            raise LedgerError("subject provider call has no registered parent attempt")
        if candidate in states:
            raise LedgerError("provider call id was already used")
        if any(state.get("kind") == "provider" and state["state"] == "unresolved" for state in states.values()):
            raise LedgerError("unresolved provider call blocks new reservations")
        if any(state.get("kind") == "provider" and state["route"] == route and state["state"] == "failed"
               for state in states.values()):
            raise LedgerError(f"{route} route is stopped by a prior failed provider call")
        if route == "codex" and KNOWN_PRIOR_CODEX_USAGE_TOKENS + _observed_tokens(states, "codex") >= CODEX_AGGREGATE_LIMIT_TOKENS:
            raise LedgerError("observed Codex aggregate reached the 5,000,000-token limit")
        event = {
            "seq": len(events) + 1, "event": "reserved", "attempt_id": candidate,
            "route": route, "attempt_class": "subject_call",
            "subject_attempt_id": subject_attempt_id, "turn_id": turn_id,
            "continuation_id": continuation_id,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "approval_sha256": header["approval_sha256"],
            "selected_resource_option": header["selected_resource_option"],
        }
        _append(path, event, _tail_hash(header, events))
        return candidate
    finally:
        _unlock(lock_fd)


def complete_subject_call(call_id: str, *, outcome: str, actual_usage: object = None,
                          usage_artifact: object = None, failure_code: str | None = None,
                          paths: LedgerPaths = DEFAULT_PATHS) -> dict[str, Any]:
    """Complete a subject provider call using the shared usage/correlation rules."""
    path, plan_path, packet_seal_path, approval_path = paths
    _header(plan_path, packet_seal_path, approval_path)
    lock_fd = _lock(path)
    try:
        _, _, states = _read(path, plan_path, packet_seal_path, approval_path)
        state = states.get(call_id)
        if state is None or state.get("kind") != "provider" or state.get("attempt_class") != "subject_call":
            raise LedgerError("call ID is not a registered subject provider call")
    finally:
        _unlock(lock_fd)
    return complete_attempt(call_id, outcome=outcome, actual_usage=actual_usage,
                            usage_artifact=usage_artifact, failure_code=failure_code, paths=paths)


def _normalize_completion(route: str, attempt_class: str, outcome: str, actual_usage: object, usage_artifact: object,
                          failure_code: str | None) -> tuple[str, object, object, str | None, str | None]:
    if outcome == "accepted" and failure_code is not None:
        raise LedgerError("accepted completion has a failure code")
    normalized_outcome = outcome
    normalized_usage = actual_usage
    normalized_artifact = usage_artifact
    normalized_failure = failure_code
    invalid_acceptance: str | None = None
    over_limit = attempt_class != "subject_call" and _usage_valid(actual_usage) and (
        actual_usage["input_tokens"] > MAX_INPUT_TOKENS_PER_CALL or
        actual_usage["output_tokens"] > MAX_OUTPUT_TOKENS_PER_ROUTE[route]
    )
    if over_limit:
        normalized_outcome = "failed"
        normalized_failure = "per_call_limit_breach"
        if not _usage_artifact_valid(normalized_artifact):
            normalized_artifact = None
        invalid_acceptance = "per-call token allowance breached; usage was retained and route stopped"
    elif outcome == "accepted" and (not _usage_valid(actual_usage) or not _usage_artifact_valid(usage_artifact)):
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
    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
        state = states.get(attempt_id)
        if state is None or state.get("kind") != "provider" or state["state"] != "unresolved":
            raise LedgerError("attempt has no unresolved reservation")
        route = state["route"]
        (normalized_outcome, normalized_usage, normalized_artifact, normalized_failure,
         invalid_acceptance) = _normalize_completion(
            route, state["attempt_class"], outcome, actual_usage, usage_artifact, failure_code
        )
        if normalized_outcome == "accepted":
            _validate_accepted_completion(normalized_usage, normalized_artifact, normalized_failure, path)
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
        event = _append(path, event, _tail_hash(header, events))
    finally:
        _unlock(lock_fd)
    if invalid_acceptance:
        raise LedgerError(invalid_acceptance)
    return event


def summary(paths: LedgerPaths = DEFAULT_PATHS) -> dict[str, Any]:
    """Return scorer-only counts and route-specific observed usage; readiness stays denied."""
    path, plan_path, packet_seal_path, approval_path = paths
    lock_fd = _lock(path)
    try:
        header, events, states = _read(path, plan_path, packet_seal_path, approval_path)
    finally:
        _unlock(lock_fd)
    codex_input = codex_output = qwen_input = qwen_output = 0
    measured_attempts = 0
    codex_usage_complete = True
    codex_scored_tokens = codex_route_check_tokens = codex_subject_tokens = 0
    qwen_scored_tokens = qwen_route_check_tokens = qwen_subject_tokens = 0
    provider_states = [state for state in states.values() if state.get("kind") == "provider"]
    subject_states = [state for state in states.values() if state.get("kind") == "subject"]
    for state in provider_states:
        usage = state.get("actual_usage")
        if state["route"] == "codex" and usage is None:
            codex_usage_complete = False
        if usage is not None:
            measured_attempts += 1
            used = usage["input_tokens"] + usage["output_tokens"]
            if state["route"] == "codex":
                codex_input += usage["input_tokens"]
                codex_output += usage["output_tokens"]
                if state["attempt_class"] == "scored_reading":
                    codex_scored_tokens += used
                elif state["attempt_class"] == "route_check":
                    codex_route_check_tokens += used
                else:
                    codex_subject_tokens += used
            else:
                qwen_input += usage["input_tokens"]
                qwen_output += usage["output_tokens"]
                if state["attempt_class"] == "scored_reading":
                    qwen_scored_tokens += used
                elif state["attempt_class"] == "route_check":
                    qwen_route_check_tokens += used
                else:
                    qwen_subject_tokens += used
    return {
        "proposal_sha256": header["proposal_sha256"],
        "packet_seal_sha256": header["packet_seal_sha256"],
        "approval_sha256": header["approval_sha256"],
        "selected_resource_option": header["selected_resource_option"],
        "reserved_attempts": len(provider_states),
        "registered_subject_attempts": len(subject_states) + len(HISTORICAL_SUBJECT_MARKERS),
        "historical_subject_marker_ids": list(HISTORICAL_SUBJECT_MARKERS),
        "scored_subject_attempts": sum(state["attempt_class"] == "scored" for state in subject_states),
        "technical_subject_attempts": sum(state["attempt_class"] == "technical" for state in subject_states) + len(HISTORICAL_SUBJECT_MARKERS),
        "defect_subject_attempts": sum(state["attempt_class"] == "defect" for state in subject_states),
        "subject_attempts_by_class": {kind: sum(state["attempt_class"] == kind for state in subject_states) + (len(HISTORICAL_SUBJECT_MARKERS) if kind == "technical" else 0) for kind in sorted(SUBJECT_CLASSES)},
        "scored_reading_attempts": sum(
            state.get("kind") == "provider" and state["attempt_class"] == "scored_reading" for state in provider_states
        ),
        "route_check_attempts": sum(
            state.get("kind") == "provider" and state["attempt_class"] == "route_check" for state in provider_states
        ),
        "accepted_scored_readings_by_route": {
            route: sum(state.get("kind") == "provider" and state["route"] == route and state["attempt_class"] == "scored_reading" and
                       state["state"] == "accepted" for state in provider_states)
            for route in sorted(ROUTES)
        },
        "accepted_route_checks_by_route": {
            route: sum(state.get("kind") == "provider" and state["route"] == route and state["attempt_class"] == "route_check" and
                       state["state"] == "accepted" for state in provider_states)
            for route in sorted(ROUTES)
        },
        "stopped_routes": sorted({
            state["route"] for state in provider_states if state["state"] == "failed"
        }),
        "codex_reserved_attempts": sum(state["route"] == "codex" for state in provider_states),
        "qwen_reserved_attempts": sum(state["route"] == "qwen" for state in provider_states),
        "accepted_attempts": sum(state["state"] == "accepted" for state in provider_states),
        "codex_accepted_attempts": sum(
            state["route"] == "codex" and state["state"] == "accepted" for state in provider_states
        ),
        "qwen_accepted_attempts": sum(
            state["route"] == "qwen" and state["state"] == "accepted" for state in provider_states
        ),
        "failed_attempts": sum(state["state"] == "failed" for state in provider_states),
        "unresolved_attempts": sum(state["state"] == "unresolved" for state in provider_states),
        "attempt_events": len(events),
        "measured_attempts": measured_attempts,
        "accounting_scope": ACCOUNTING_SCOPE,
        "codex_observed_input_tokens": codex_input,
        "codex_observed_output_tokens": codex_output,
        "codex_observed_scorer_tokens": codex_scored_tokens,
        "codex_observed_route_check_tokens": codex_route_check_tokens,
        "codex_observed_subject_tokens": codex_subject_tokens,
        "codex_known_prior_tokens": KNOWN_PRIOR_CODEX_USAGE_TOKENS,
        "codex_usage_complete": codex_usage_complete,
        "codex_observed_aggregate_tokens": (
            KNOWN_PRIOR_CODEX_USAGE_TOKENS + codex_input + codex_output if codex_usage_complete else None
        ),
        "codex_remaining_tokens": (
            max(0, CODEX_AGGREGATE_LIMIT_TOKENS - KNOWN_PRIOR_CODEX_USAGE_TOKENS - codex_input - codex_output)
            if codex_usage_complete else None
        ),
        "codex_aggregate_limit_tokens": CODEX_AGGREGATE_LIMIT_TOKENS,
        "qwen_observed_input_tokens": qwen_input,
        "qwen_observed_output_tokens": qwen_output,
        "qwen_observed_tokens": qwen_input + qwen_output,
        "qwen_observed_scorer_tokens": qwen_scored_tokens,
        "qwen_observed_route_check_tokens": qwen_route_check_tokens,
        "qwen_observed_subject_tokens": qwen_subject_tokens,
        "qwen_aggregate_limit_tokens": None,
        "accepted_scorer_readings_per_route": SCORER_READINGS_PER_ROUTE,
        "hard_token_cap_enforced": False,
        "usage_provenance_status": USAGE_PROVENANCE,
        "dispatch_readiness": DISPATCH_READINESS,
    }
