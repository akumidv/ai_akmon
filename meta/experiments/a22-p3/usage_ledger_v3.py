#!/usr/bin/env python3
"""Default-deny, offline V3 epoch ledger and quota checkpoint primitives.

This module never launches a provider. V3 approval remains an explicit owner action.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PLAN = HERE / "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md"
PACKET_SEAL = HERE / "seal.json"
APPROVAL = HERE / "runs" / "owner-approval-v3.json"
LEDGER = HERE / "runs" / "provider-usage-v3.jsonl"
V3_SEAL = HERE / "seal-v3.json"
CODEX_LIMIT = 5_000_000
FIVE_HOUR_STOP_PERCENT = 80
WEEKLY_STOP_PERCENT = 90
MAX_QUOTA_FRESHNESS_SECONDS = 600
PERCENT_MAX = 100
SHA256_HEX_LENGTH = 64
OPAQUE_ID_HEX_LENGTH = 32
ROUTES = {"codex", "qwen"}
UNKNOWN_USAGE = "UNKNOWN_USAGE"
CODEX_QUOTA_SOURCE = "codex app-server account/rateLimits/read"


class LedgerError(ValueError):
    """V3 ledger integrity, admission, or quota failure."""


def sha256(path: Path) -> str:
    """Hash a bound V3 input file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fresh_id(existing: set[str] | None = None) -> str:
    """Return an opaque ID, rejecting historical q1461 and all supplied IDs."""
    occupied = existing or set()
    for _ in range(16):
        value = secrets.token_hex(16)
        if value != "q1461" and value not in occupied:
            return value
    raise LedgerError("could not generate a fresh V3 identifier")


def _historical_ids() -> set[str]:
    """Collect identity fields from immutable V2 JSON artifacts for collision checks."""
    found = {"q1461"}
    runs = HERE / "runs"
    for artifact in runs.rglob("*.json"):
        try:
            value = json.loads(artifact.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stack = [value]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, item in node.items():
                    if key.endswith("_id") and isinstance(item, str):
                        found.add(item)
                    if isinstance(item, (dict, list)):
                        stack.append(item)
            elif isinstance(node, list):
                stack.extend(node)
    return found


def _utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        view = view[count:]


def _locked(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _unlock(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def _digest(obj: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:  # noqa: C901
    if not path.exists():
        raise LedgerError("V3 ledger is not initialized")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not rows or rows[0].get("record_type") != "p3_v3_ledger_header":
        raise LedgerError("V3 ledger header is missing")
    header, events = rows[0], rows[1:]
    previous = _digest(header)
    states: dict[str, dict[str, Any]] = {}
    for seq, event in enumerate(events, 1):
        body = {k: v for k, v in event.items() if k != "event_sha256"}
        if (event.get("seq") != seq or event.get("previous_sha256") != previous or
                event.get("event_sha256") != _digest(body)):
            raise LedgerError("V3 event chain is corrupt")
        previous = event["event_sha256"]
        kind = event.get("event")
        if kind == "reserved":
            call_id = event.get("provider_call_id")
            if not isinstance(call_id, str) or call_id in states or call_id == "q1461":
                raise LedgerError("duplicate or forbidden provider call ID")
            states[call_id] = {**event, "state": "reserved"}
        elif kind == "completed":
            state = states.get(event.get("provider_call_id"))
            if not state or state["state"] != "reserved":
                raise LedgerError("completion has no open reservation")
            if any(event.get(k) != state.get(k) for k in (
                    "epoch_id", "proposal_sha256", "approval_sha256", "route",
                    "subject_attempt_id", "turn_id")):
                raise LedgerError("completion binding differs from reservation")
            state.update(event)
            state["state"] = "completed"
        elif kind == "quota_checkpoint":
            pass
        else:
            raise LedgerError("unknown V3 ledger event")
    return header, events


def _append(path: Path, event: dict[str, Any], header: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    previous = events[-1]["event_sha256"] if events else _digest(header)
    event = {"seq": len(events) + 1, **event}
    event["previous_sha256"] = previous
    event["event_sha256"] = _digest(event)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    try:
        _write_all(fd, (json.dumps(event, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    return event


def initialize(path: Path = LEDGER, *, plan: Path = PLAN, packet_seal: Path = PACKET_SEAL,
               approval: Path = APPROVAL, seal_path: Path = V3_SEAL) -> dict[str, Any]:
    """Initialize an isolated ledger after preflight and bind its exact approval.

    A default-deny draft may be initialized for offline accounting tests, but it
    cannot later authorize dispatch because the ledger binds its approval hash.
    The dispatchable ledger is created only after the accepted approval exists.
    """
    approval_record = json.loads(approval.read_text(encoding="utf-8"))
    draft = (approval_record.get("schema") == 1 and
             approval_record.get("record_type") == "p3_v3_owner_approval" and
             approval_record.get("owner_accepted") is False and
             approval_record.get("dispatch_allowed") is False and
             approval_record.get("authorized_phases") == [] and
             approval_record.get("preflight_status") == "NOT_RUN")
    accepted = approval_record.get("owner_accepted") is True
    if not draft and not accepted:
        raise LedgerError("V3 ledger requires either a default-deny draft or a fully accepted approval")
    if accepted:
        validate_v3_approval(approval=approval, seal_path=seal_path,
                              plan=plan, packet_seal=packet_seal)
    header = {
        "schema": 1, "record_type": "p3_v3_ledger_header", "epoch_id": fresh_id(_historical_ids()),
        "proposal_sha256": sha256(plan), "packet_seal_sha256": sha256(packet_seal),
        "approval_sha256": sha256(approval), "codex_epoch_limit_tokens": CODEX_LIMIT,
        "v3_codex_tokens_used": 0, "v2_known_usage_tokens_historical_only": 153_614,
        "q1461_disposition_historical_only": UNKNOWN_USAGE,
        "v2_usage_excluded_by_proposed_epoch_boundary": True,
        "qwen_aggregate_limit_tokens": None, "dispatch_ready": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = _locked(path)
    try:
        if path.exists():
            raise FileExistsError(path)
        out = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            _write_all(out, (json.dumps(header, sort_keys=True) + "\n").encode())
            os.fsync(out)
        finally:
            os.close(out)
    finally:
        _unlock(fd)
    return header


def validate_quota_snapshot(snapshot: object, route: str) -> dict[str, Any]:  # noqa: C901
    """Validate quota telemetry shape, freshness, and provider-specific fields."""
    if route not in ROUTES or not isinstance(snapshot, dict):
        raise LedgerError("quota snapshot or route is malformed")
    required = {"captured_utc", "source", "source_version", "freshness_seconds", "five_hour_used_percent",
                "five_hour_reset_utc", "weekly_used_percent", "weekly_reset_utc", "raw_redacted_sha256"}
    live_receipt = snapshot.get("source") == CODEX_QUOTA_SOURCE
    if live_receipt:
        required.add("account_limit_receipt")
    if set(snapshot) != required:
        raise LedgerError("quota snapshot fields are incomplete")
    if live_receipt:
        receipt = snapshot.get("account_limit_receipt")
        fields = {"codex_executable_sha256", "codex_home_sha256", "account_id_sha256",
                  "five_hour_stop_percent", "weekly_stop_percent", "limit_receipt_sha256"}
        if (not isinstance(receipt, dict) or set(receipt) != fields or
                receipt.get("five_hour_stop_percent") != FIVE_HOUR_STOP_PERCENT or
                receipt.get("weekly_stop_percent") != WEEKLY_STOP_PERCENT):
            raise LedgerError("Codex quota account/limit receipt is missing or malformed")
        for field in ("codex_executable_sha256", "codex_home_sha256", "account_id_sha256",
                      "limit_receipt_sha256"):
            value = receipt.get(field)
            if (not isinstance(value, str) or len(value) != SHA256_HEX_LENGTH or
                    any(char not in "0123456789abcdef" for char in value)):
                raise LedgerError("Codex quota account/limit receipt hash is malformed")
        body = {key: receipt[key] for key in fields - {"limit_receipt_sha256"}}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if receipt["limit_receipt_sha256"] != digest:
            raise LedgerError("Codex quota account/limit receipt hash does not match its fields")
    if (not isinstance(snapshot["freshness_seconds"], (int, float)) or
            snapshot["freshness_seconds"] < 0 or
            snapshot["freshness_seconds"] > MAX_QUOTA_FRESHNESS_SECONDS):
        raise LedgerError("quota telemetry is missing or stale")
    for field in ("five_hour_used_percent", "weekly_used_percent"):
        value = snapshot[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= PERCENT_MAX:
            raise LedgerError("quota telemetry is uninterpretable")
    if (not isinstance(snapshot["raw_redacted_sha256"], str) or
            len(snapshot["raw_redacted_sha256"]) != SHA256_HEX_LENGTH):
        raise LedgerError("quota response hash is malformed")
    return dict(snapshot)


def quota_stop_reason(snapshot: dict[str, Any], route: str) -> str | None:
    """Return the applicable stop cause for a structurally valid snapshot."""
    if route not in ROUTES:
        raise LedgerError("quota snapshot or route is malformed")
    if snapshot["five_hour_used_percent"] >= FIVE_HOUR_STOP_PERCENT:
        return f"{route}_five_hour_threshold"
    if snapshot["weekly_used_percent"] >= WEEKLY_STOP_PERCENT:
        return f"{route}_weekly_threshold"
    return None


def validate_quota(snapshot: object, route: str) -> dict[str, Any]:
    """Validate quota state and reject it for a new provider dispatch at stop thresholds."""
    checked = validate_quota_snapshot(snapshot, route)
    stop = quota_stop_reason(checked, route)
    if stop:
        raise LedgerError(f"subscription stop threshold reached: {stop}")
    return checked


def checkpoint(snapshot: object, route: str, *, path: Path = LEDGER,
               before_call_id: str | None = None,
               during_call_id: str | None = None) -> dict[str, Any]:
    """Append a quota snapshot; preserve malformed/missing capture as a stop event."""
    if route not in ROUTES:
        raise LedgerError("quota snapshot or route is malformed")
    checked: dict[str, Any] | None = None
    try:
        checked = validate_quota_snapshot(snapshot, route)
        stop = quota_stop_reason(checked, route)
        error = None
    except LedgerError:
        stop = "quota_checkpoint_failure"
        error = "missing_or_invalid_quota_snapshot"
    fd = _locked(path)
    try:
        header, events = _read(path)
        event = {"event": "quota_checkpoint", "epoch_id": header["epoch_id"], "route": route,
                 "captured_utc": _utc(), "snapshot": checked, "before_call_id": before_call_id,
                 "during_call_id": during_call_id,
                 "dispatch_stopped": stop is not None, "stop_reason": stop,
                 "failure_code": error}
        return _append(path, event, header, events)
    finally:
        _unlock(fd)


def reserve(route: str, attempt_class: str, *, quota_snapshot: object, path: Path = LEDGER,  # noqa: C901, PLR0912, PLR0913
            proposal_sha256: str | None = None,
            approval_sha256: str | None = None,
            subject_attempt_id: str | None = None,
            turn_id: str | None = None,
            token_reservation: int = 0) -> str:
    """Record pre-call quota checkpoint then reserve; this does not launch a provider."""
    if route not in ROUTES or attempt_class not in {"technical", "route_check", "scored_reading", "subject_call"}:
        raise LedgerError("unsupported V3 route or call class")
    checked = validate_quota(quota_snapshot, route)
    fd = _locked(path)
    try:
        header, events = _read(path)
        if any(e.get("dispatch_stopped") is True for e in events if e["event"] == "quota_checkpoint"):
            raise LedgerError("a prior V3 quota checkpoint permanently stopped dispatch")
        if (proposal_sha256 not in (None, header["proposal_sha256"]) or
                approval_sha256 not in (None, header["approval_sha256"])):
            raise LedgerError("call does not bind the V3 proposal and approval")
        if ((subject_attempt_id is None) != (turn_id is None) or
                (subject_attempt_id is not None and
                 (len(subject_attempt_id) != OPAQUE_ID_HEX_LENGTH or
                  any(c not in "0123456789abcdef" for c in subject_attempt_id) or
                  turn_id not in {"turn-1", "turn-2"}))):
            raise LedgerError("subject call linkage is malformed")
        states: dict[str, dict[str, Any]] = {}
        for e in events:
            if e["event"] == "reserved":
                states[e["provider_call_id"]] = {**e, "state": "reserved"}
            elif e["event"] == "completed":
                states[e["provider_call_id"]].update(e)
                states[e["provider_call_id"]]["state"] = "completed"
        if any(s["state"] == "reserved" for s in states.values()):
            raise LedgerError("unresolved V3 provider call locks dispatch")
        if route == "codex":
            used = sum((s.get("input_tokens", 0) + s.get("output_tokens", 0)) for s in states.values()
                       if s.get("route") == "codex" and s.get("usage_status") == "known")
            if any(s.get("route") == "codex" and s.get("usage_status") == UNKNOWN_USAGE for s in states.values()):
                raise LedgerError("unknown V3 Codex usage locks dispatch")
            if (not isinstance(token_reservation, int) or isinstance(token_reservation, bool) or
                    token_reservation < 0 or used >= CODEX_LIMIT or
                    used + token_reservation > CODEX_LIMIT):
                raise LedgerError("V3 Codex epoch token ceiling reached")
        call_id = fresh_id(set(states) | _historical_ids())
        cp = {"event": "quota_checkpoint", "epoch_id": header["epoch_id"], "route": route,
              "captured_utc": _utc(), "snapshot": checked, "before_call_id": call_id}
        events.append(_append(path, cp, header, events))
        reservation = {"event": "reserved", "epoch_id": header["epoch_id"],
                       "proposal_sha256": header["proposal_sha256"], "approval_sha256": header["approval_sha256"],
                       "provider_call_id": call_id, "route": route, "attempt_class": attempt_class,
                       "token_reservation": token_reservation if route == "codex" else 0,
                       "created_utc": _utc(), "state": "reserved"}
        if subject_attempt_id is not None:
            reservation.update({"subject_attempt_id": subject_attempt_id, "turn_id": turn_id})
        _append(path, reservation, header, events)
        return call_id
    finally:
        _unlock(fd)


def complete(call_id: str, *, outcome: str, usage: dict[str, int] | None,  # noqa: PLR0913
             quota_snapshot: object, path: Path = LEDGER,
             failure_code: str | None = None) -> None:
    """Close a reservation with correlated usage or UNKNOWN_USAGE and post-call quota."""
    fd = _locked(path)
    try:
        header, events = _read(path)
        reservation = next((e for e in reversed(events) if e["event"] == "reserved" and
                            e["provider_call_id"] == call_id), None)
        closed = any(e["event"] == "completed" and e["provider_call_id"] == call_id for e in events)
        if reservation is None or closed:
            raise LedgerError("provider call reservation is missing or already closed")
        route = reservation["route"]
        checked: dict[str, Any] | None = None
        try:
            checked = validate_quota_snapshot(quota_snapshot, route)
            stop_reason = quota_stop_reason(checked, route)
            checkpoint_failure = False
        except LedgerError:
            stop_reason = "quota_checkpoint_failure"
            checkpoint_failure = True
        if outcome not in {"accepted", "failed"} or (outcome == "failed" and not failure_code):
            raise LedgerError("completion outcome or failure code is invalid")
        if usage is not None and (set(usage) != {"input_tokens", "output_tokens"} or
                                  any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in usage.values())):
            raise LedgerError("correlated usage record is malformed")
        if outcome == "accepted" and usage is None:
            raise LedgerError("accepted call requires correlated usage")
        final_outcome = "failed" if stop_reason else outcome
        final_failure = failure_code or (
            "quota_checkpoint_failure_after_call" if checkpoint_failure else
            "subscription_quota_stop_after_call" if stop_reason else None)
        completion = {"event": "completed", "epoch_id": header["epoch_id"],
                      "proposal_sha256": header["proposal_sha256"], "approval_sha256": header["approval_sha256"],
                      "provider_call_id": call_id, "route": route, "outcome": final_outcome,
                      "provider_outcome": outcome, "stop_reason": stop_reason,
                      "usage_status": "known" if usage is not None else UNKNOWN_USAGE,
                      "input_tokens": usage["input_tokens"] if usage else None,
                      "output_tokens": usage["output_tokens"] if usage else None,
                      "failure_code": final_failure, "completed_utc": _utc()}
        if "subject_attempt_id" in reservation:
            completion.update({"subject_attempt_id": reservation["subject_attempt_id"],
                               "turn_id": reservation["turn_id"]})
        events.append(_append(path, completion, header, events))
        cp = {"event": "quota_checkpoint", "epoch_id": header["epoch_id"], "route": route,
              "captured_utc": _utc(), "snapshot": checked, "before_call_id": None,
              "dispatch_stopped": stop_reason is not None, "stop_reason": stop_reason,
              "failure_code": "missing_or_invalid_quota_snapshot" if checkpoint_failure else None}
        _append(path, cp, header, events)
        if stop_reason:
            raise LedgerError(f"post-call subscription stop threshold reached: {stop_reason}")
    finally:
        _unlock(fd)


def complete_lean(call_id: str, *, outcome: str, usage: dict[str, int] | None,
                  path: Path = LEDGER, failure_code: str | None = None) -> None:
    """Close one lean-protocol call using its direct usage, without a quota fetch."""
    fd = _locked(path)
    try:
        header, events = _read(path)
        reservation = next((e for e in reversed(events) if e["event"] == "reserved" and
                            e["provider_call_id"] == call_id), None)
        if reservation is None or any(e["event"] == "completed" and
                                      e["provider_call_id"] == call_id for e in events):
            raise LedgerError("provider call reservation is missing or already closed")
        if outcome not in {"accepted", "failed"} or (outcome == "failed" and not failure_code):
            raise LedgerError("completion outcome or failure code is invalid")
        if usage is not None and (set(usage) != {"input_tokens", "output_tokens"} or
                                  any(not isinstance(v, int) or isinstance(v, bool) or v < 0
                                      for v in usage.values())):
            raise LedgerError("correlated usage record is malformed")
        if outcome == "accepted" and usage is None:
            raise LedgerError("accepted call requires correlated usage")
        event = {"event": "completed", "epoch_id": header["epoch_id"],
                 "proposal_sha256": header["proposal_sha256"],
                 "approval_sha256": header["approval_sha256"], "provider_call_id": call_id,
                 "route": reservation["route"], "outcome": outcome,
                 "usage_status": "known" if usage is not None else UNKNOWN_USAGE,
                 "input_tokens": usage["input_tokens"] if usage else None,
                 "output_tokens": usage["output_tokens"] if usage else None,
                 "failure_code": failure_code, "completed_utc": _utc()}
        for key in ("subject_attempt_id", "turn_id"):
            if key in reservation:
                event[key] = reservation[key]
        _append(path, event, header, events)
    finally:
        _unlock(fd)


def summary(path: Path = LEDGER) -> dict[str, Any]:
    """Summarize V3 usage while retaining historical V2 exposure separately."""
    header, events = _read(path)
    codex_tokens = sum(e["input_tokens"] + e["output_tokens"] for e in events
                       if e["event"] == "completed" and e["route"] == "codex" and e["usage_status"] == "known")
    unknown = any(e["event"] == "completed" and e["route"] == "codex" and e["usage_status"] == UNKNOWN_USAGE
                  for e in events)
    return {"epoch_id": header["epoch_id"], "v3_codex_tokens_used": codex_tokens,
            "unknown_codex_usage": unknown, "v2_known_usage_tokens_historical_only": 153_614,
            "q1461_disposition_historical_only": UNKNOWN_USAGE, "dispatch_ready": False,
            "completed_calls": sum(e["event"] == "completed" for e in events)}


def static_preflight(*, plan: Path = PLAN, packet_seal: Path = PACKET_SEAL,
                     approval: Path = APPROVAL, runtime_root: Path,
                     require_v2_artifacts: bool = True) -> dict[str, Any]:
    """No-network preflight: bind inputs, exercise writable runtime, keep dispatch denied."""
    record = json.loads(approval.read_text(encoding="utf-8"))
    if record.get("owner_accepted") is not False or record.get("dispatch_allowed") is not False:
        raise LedgerError("static preflight cannot convert approval into dispatch authorization")
    if "q1461" not in plan.read_text(encoding="utf-8"):
        raise LedgerError("proposal must explicitly preserve the terminal q1461 history")
    bound_inputs = [plan, packet_seal, approval]
    v2_history = HERE / "runs" / "v2-history"
    v2_expected = [v2_history / "RUN_PLAN_V2_PROPOSAL.md", v2_history / "accepted-v2-seal.json",
                   v2_history / "owner-approval-v2.json", v2_history / "provider-usage-v2.jsonl",
                   v2_history / "q1461.attempt.json"]
    v2_missing = [str(p) for p in v2_expected if not p.is_file()]
    bound_inputs.extend(p for p in v2_expected if p.is_file())
    before = {str(p): sha256(p) for p in bound_inputs}
    runtime_root.mkdir(parents=True, exist_ok=True)
    probe = runtime_root / ("v3-preflight-" + fresh_id())
    fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        payload = secrets.token_bytes(64)
        _write_all(fd, payload)
        os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        if os.read(fd, len(payload)) != payload:
            raise LedgerError("isolated runtime write/read check failed")
    finally:
        os.close(fd)
        probe.unlink(missing_ok=True)
    if before != {str(p): sha256(p) for p in bound_inputs}:
        raise LedgerError("V3 or historical V2 inputs changed during preflight")
    # Synthetic policy checks only. No command, network, or provider is invoked.
    good = {"captured_utc": _utc(), "source": "synthetic", "source_version": "fixture-v1",
            "freshness_seconds": 0, "five_hour_used_percent": 0, "five_hour_reset_utc": "2030-01-01T00:00:00Z",
            "weekly_used_percent": 0, "weekly_reset_utc": "2030-01-01T00:00:00Z",
            "raw_redacted_sha256": "a" * 64}
    validate_quota(good, "codex")
    for field, value in (("five_hour_used_percent", 80), ("weekly_used_percent", 90),
                         ("freshness_seconds", 601)):
        bad = {**good, field: value}
        try:
            validate_quota(bad, "codex")
        except LedgerError:
            continue
        raise LedgerError(f"synthetic preflight failed to stop on {field}")
    if fresh_id({"q1461"}) == "q1461":
        raise LedgerError("historical attempt ID was reused")
    missing_history_blocks = bool(v2_missing and require_v2_artifacts)
    return {"status": "BLOCKED_MISSING_V2_HISTORY" if missing_history_blocks else "PASSED_SYNTHETIC_ONLY",
            "launch_ready": False, "blockers": v2_missing if require_v2_artifacts else [],
            "network_or_provider_calls": 0, "dispatch_allowed": False, "input_hashes": before,
            "runtime_write_fsync_read_delete": "PASSED",
            "synthetic_quota_threshold_and_stale_checks": "PASSED",
            "historical_q1461_reuse_check": "PASSED"}


def validate_v3_seal(seal_path: Path = V3_SEAL, *, plan: Path = PLAN,
                      packet_seal: Path = PACKET_SEAL) -> dict[str, Any]:
    """Validate a separately created V3 seal without modifying or creating it."""
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    sources = {
        "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md": plan,
        "usage_ledger_v3.py": HERE / "usage_ledger_v3.py",
        "dispatch_v3.py": HERE / "dispatch_v3.py",
        "v3_runner.py": HERE / "v3_runner.py",
        "quota_adapter_v3.py": HERE / "quota_adapter_v3.py",
        "preflight_v3.py": HERE / "preflight_v3.py",
        "source_v3.py": HERE / "source_v3.py",
    }
    expected = {name: sha256(file) for name, file in sources.items()}
    if (not isinstance(seal, dict) or set(seal) != {
            "schema", "record_type", "proposal_sha256", "packet_seal_sha256", "source_sha256",
            "settings"} or seal.get("schema") != 1 or seal.get("record_type") != "p3_v3_plan_seal" or
            seal.get("proposal_sha256") != sha256(plan) or
            seal.get("packet_seal_sha256") != sha256(packet_seal) or
            seal.get("source_sha256") != expected):
        raise LedgerError("V3 seal is missing, stale, or does not bind the exact V3 sources")
    settings = seal.get("settings")
    if settings != {
            "codex_cli": "0.156.1", "codex_model": "gpt-6-astra",
            "qwen_cli": "0.24.7", "qwen_model": "qwen3.8-27b",
            "qwen_thinking": "default", "codex_epoch_limit_tokens": CODEX_LIMIT,
            "five_hour_stop_percent": FIVE_HOUR_STOP_PERCENT,
            "weekly_stop_percent": WEEKLY_STOP_PERCENT,
            "retry_evidence_policy": "OBSERVED_NO_RETRY"}:
        raise LedgerError("V3 seal settings do not match the frozen proposal pins")
    return seal


def validate_v3_approval(*, approval: Path = APPROVAL, seal_path: Path = V3_SEAL,
                         plan: Path = PLAN, packet_seal: Path = PACKET_SEAL,
                         phase: str | None = None) -> dict[str, Any]:
    """Require exact owner decisions and source-bound seal before any future dispatch."""
    try:
        validate_v3_seal(seal_path, plan=plan, packet_seal=packet_seal)
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError("V3 seal is unavailable or malformed") from exc
    record = json.loads(approval.read_text(encoding="utf-8"))
    required = {
        "schema", "record_type", "proposal_sha256", "v3_seal_sha256", "owner_accepted",
        "new_epoch_budget_accepted", "v2_usage_exclusion_accepted", "subscription_thresholds_accepted",
        "qwen_uncapped_policy_accepted", "observed_no_retry_accepted", "schedule_accepted",
        "named_stop_operator", "authorized_phases", "acceptance_evidence", "preflight_status",
        "dispatch_allowed",
    }
    if not isinstance(record, dict) or set(record) != required or record.get("schema") != 1 or \
            record.get("record_type") != "p3_v3_owner_approval":
        raise LedgerError("V3 approval schema is malformed")
    if (record.get("proposal_sha256") != sha256(plan) or
            record.get("v3_seal_sha256") != sha256(seal_path) or
            record.get("owner_accepted") is not True or record.get("dispatch_allowed") is not True or
            record.get("preflight_status") != "PASSED"):
        raise LedgerError("V3 approval is absent, stale, or does not authorize dispatch")
    required_decisions = (
        "new_epoch_budget_accepted", "v2_usage_exclusion_accepted", "subscription_thresholds_accepted",
        "qwen_uncapped_policy_accepted", "observed_no_retry_accepted", "schedule_accepted",
    )
    if any(record.get(field) is not True for field in required_decisions):
        raise LedgerError("V3 owner acceptance omits a material budget, quota, or schedule decision")
    if not isinstance(record.get("named_stop_operator"), str) or not record["named_stop_operator"].strip():
        raise LedgerError("V3 approval must name the human stop operator")
    allowed = {"technical_source", "route_checks", "qualification", "comparison"}
    phases = record.get("authorized_phases")
    if (not isinstance(phases, list) or not phases or not all(isinstance(item, str) for item in phases) or
            len(set(phases)) != len(phases) or not set(phases) <= allowed or
            (phase is not None and phase not in phases)):
        raise LedgerError("V3 approval does not explicitly authorize this phase")
    evidence = record.get("acceptance_evidence")
    if (not isinstance(evidence, dict) or evidence.get("proposal_sha256") != sha256(plan) or
            evidence.get("v3_seal_sha256") != sha256(seal_path) or
            not isinstance(evidence.get("transcript_sha256"), str) or
            len(evidence["transcript_sha256"]) != SHA256_HEX_LENGTH or
            any(c not in "0123456789abcdef" for c in evidence.get("transcript_sha256", "")) or
            not isinstance(evidence.get("exact_quote"), str) or not evidence["exact_quote"].strip()):
        raise LedgerError("V3 approval lacks transcript evidence bound to the proposal and seal")
    return record
