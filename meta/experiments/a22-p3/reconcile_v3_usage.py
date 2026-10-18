#!/usr/bin/env python3
"""Verify the one accepted historical V3 process-envelope usage exception.

This is offline evidence validation. It never launches a provider or changes an
existing ledger. Future admission must bind and revalidate the receipt bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import usage_ledger_v3 as ledger

HERE = Path(__file__).resolve().parent
RUNTIME = Path("/tmp/a22-p3-v3-source-340ec9af6c43")  # noqa: S108 - sealed historical capture
RUN_ID = "b62745e38d8ae5547c8c004c4ff19cc4"
ATTEMPT_ID = "95e85fab70b5464fd4b520d321088003"
CALL_ID = "b56635eca40db627519d47d4717d379f"
SESSION_ID = "01a13ff9-c46c-75c0-bea0-2db13a9cb475"
TURN_ID = "01a13ff9-c4ed-79e3-bd1d-4e159a400302"
EVENT_SHA = "6d88be4f6e70f0b19a3656e8dfaffddb227e495359af41e7c81645171324e31b"
ROLLOUT_SHA = "97d12028aedcae2eea8622022a223ac20e119d08df7a5e9cb15f854cddef6480"
INPUT_TOKENS = 7_737
OUTPUT_TOKENS = 29
DEBIT = INPUT_TOKENS + OUTPUT_TOKENS
RECEIPT = HERE / "runs" / "v3-historical-usage-reconciliation-v1.json"
LEAN_LEDGER = Path("/tmp/a22-p3-v3-lean-f450a4a726b3/provider-usage-v3.jsonl")  # noqa: S108
SOURCE_LEDGER = Path("/tmp/a22-p3-v3-successor-9xViiq/ledger/provider-usage-v3.jsonl")  # noqa: S108
ROUTE_LEDGER = Path("/tmp/a22-p3-v3-successor-route-runtime/route-events.jsonl")  # noqa: S108
OPENING = HERE / "runs" / "v3-qualification-opening-accounting-v1.json"
ROUTE_LEDGER_ROWS = 5
ROUTE_CODEX_INPUT = 12_305
ROUTE_CODEX_OUTPUT = 176
KNOWN_OBSERVED = 66_491
CHARGED_OPENING = 74_257
TECHNICAL_ATTEMPTS = 3


class ReconciliationError(ValueError):
    """The historical exception cannot be verified uniquely."""


def sha(path: Path) -> str:
    """Hash the exact bytes of an evidence artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _single(rows: list[dict[str, Any]], kind: str, label: str) -> dict[str, Any]:
    matches = [row for row in rows if row.get("type") == kind]
    if len(matches) != 1:
        raise ReconciliationError(f"expected exactly one {label}")
    return matches[0]


def validate_envelope(  # noqa: PLR0913
    *,
    attempt: dict[str, Any],
    dispatch: dict[str, Any],
    events: list[dict[str, Any]],
    rollout: list[dict[str, Any]],
    ledger_events: list[dict[str, Any]],
    rollout_count: int,
) -> None:
    """Require unique call, session, turn and matching usage in captured envelope."""
    if (
        attempt.get("run_id") != RUN_ID
        or attempt.get("subject_attempt_id") != ATTEMPT_ID
        or attempt.get("attempt_class") != "technical"
        or attempt.get("case") != "P3-01"
        or attempt.get("arm") != "A"
        or attempt.get("tier") != "strongest"
        or attempt.get("repeat") != 1
    ):
        raise ReconciliationError("subject attempt identity changed")
    if (
        dispatch.get("returncode") != 0
        or dispatch.get("status") != "accepted"
        or dispatch.get("cwd") != str(RUNTIME / "scratch")
        or sum(item == "exec" for item in dispatch.get("command", [])) != 1
    ):
        raise ReconciliationError("single captured Codex process is not established")
    reserved = [row for row in ledger_events if row.get("event") == "reserved"]
    completed = [row for row in ledger_events if row.get("event") == "completed"]
    if (
        len(reserved) != 1
        or len(completed) != 1
        or reserved[0].get("provider_call_id") != CALL_ID
        or reserved[0].get("subject_attempt_id") != ATTEMPT_ID
        or reserved[0].get("turn_id") != "turn-1"
        or completed[0].get("provider_call_id") != CALL_ID
        or completed[0].get("usage_status") != ledger.UNKNOWN_USAGE
        or completed[0].get("input_tokens") is not None
        or completed[0].get("output_tokens") is not None
        or completed[0].get("outcome") != "failed"
    ):
        raise ReconciliationError("the immutable unknown-usage ledger differs")
    if rollout_count != 1:
        raise ReconciliationError("capture contains competing rollout sessions")
    started = _single(events, "thread.started", "thread start")
    direct = _single(events, "turn.completed", "direct usage event")
    if (
        started.get("thread_id") != SESSION_ID
        or direct.get("usage", {}).get("input_tokens") != INPUT_TOKENS
        or direct.get("usage", {}).get("output_tokens") != OUTPUT_TOKENS
        or set(direct) != {"type", "usage"}
    ):
        raise ReconciliationError("direct usage observation changed")
    session = _single(rollout, "session_meta", "rollout session")
    turn = _single(rollout, "turn_context", "rollout turn")
    usage = _single(rollout, "token_usage_record", "rollout usage")
    counter = [
        row for row in rollout if row.get("type") == "event_msg" and row.get("payload", {}).get("type") == "token_count"
    ]
    if (
        len(counter) != 1
        or session.get("payload", {}).get("session_id") != SESSION_ID
        or session.get("payload", {}).get("cwd") != str(RUNTIME / "scratch")
        or turn.get("payload", {}).get("turn_id") != TURN_ID
        or usage.get("payload", {}).get("session_id") != SESSION_ID
        or usage.get("payload", {}).get("turn_id") != TURN_ID
    ):
        raise ReconciliationError("rollout session and turn are not unique")
    for observed in (
        usage.get("payload", {}).get("usage"),
        counter[0].get("payload", {}).get("info", {}).get("last_token_usage"),
    ):
        if (
            not isinstance(observed, dict)
            or observed.get("input_tokens") != INPUT_TOKENS
            or observed.get("output_tokens") != OUTPUT_TOKENS
            or observed.get("total_tokens") != DEBIT
        ):
            raise ReconciliationError("rollout usage disagrees with direct event")


def verify_runtime(root: Path = RUNTIME) -> dict[str, Any]:
    """Re-read original bytes and return a receipt body with exact source hashes."""
    if root.resolve() != RUNTIME:
        raise ReconciliationError("historical runtime root changed")
    output = root / "output"
    attempt_path = output / f"{RUN_ID}.attempt.json"
    dispatch_path = output / f"{RUN_ID}.turn1.dispatch.json"
    events_path = output / f"{RUN_ID}.turn1.events.json"
    failure_path = output / f"{RUN_ID}.failure.json"
    ledger_path = root / "provider-usage-v3.jsonl"
    if (
        len(list(output.glob("*.attempt.json"))) != 1
        or len(list(output.glob("*.turn*.dispatch.json"))) != 1
        or len(list(output.glob("*.turn*.events.json"))) != 1
        or len(list(output.glob("*.failure.json"))) != 1
    ):
        raise ReconciliationError("capture contains another attempt or process artifact")
    session_root = root / "home" / "sessions"
    rollouts = list(session_root.rglob("rollout-*.jsonl"))
    if len(rollouts) != 1:
        raise ReconciliationError("capture contains competing rollout sessions")
    rollout_path = rollouts[0]
    if sha(events_path) != EVENT_SHA or sha(rollout_path) != ROLLOUT_SHA:
        raise ReconciliationError("historical event or rollout bytes changed")
    header, ledger_events = ledger._read(ledger_path)
    if header.get("record_type") != "p3_v3_ledger_header":
        raise ReconciliationError("historical ledger header changed")
    rollout = [json.loads(line) for line in rollout_path.read_text(encoding="utf-8").splitlines()]
    validate_envelope(
        attempt=_json(attempt_path),
        dispatch=_json(dispatch_path),
        events=_json(events_path),
        rollout=rollout,
        ledger_events=ledger_events,
        rollout_count=len(rollouts),
    )
    failure = _json(failure_path)
    if failure.get("terminal") is not True or failure.get("retry_authorized") is not False:
        raise ReconciliationError("failed attempt is not terminal")
    return {
        "record_type": "p3_v3_historical_envelope_usage_reconciliation",
        "schema": 1,
        "classification": "historical_envelope_correlated_debit_only",
        "original_ledger_status": ledger.UNKNOWN_USAGE,
        "provider_call_id": CALL_ID,
        "subject_attempt_id": ATTEMPT_ID,
        "run_id": RUN_ID,
        "input_tokens": INPUT_TOKENS,
        "output_tokens": OUTPUT_TOKENS,
        "debit_tokens": DEBIT,
        "direct_correlation_claimed": False,
        "future_calls_eligible_for_exception": False,
        "source_sha256": {
            "attempt": sha(attempt_path),
            "dispatch": sha(dispatch_path),
            "events": sha(events_path),
            "rollout": sha(rollout_path),
            "ledger": sha(ledger_path),
            "failure": sha(failure_path),
        },
    }


def verify_receipt(path: Path = RECEIPT) -> dict[str, Any]:
    """Reject a stale, edited, or duplicate receipt before any future admission."""
    actual = _json(path)
    expected = verify_runtime()
    if actual != expected:
        raise ReconciliationError("historical reconciliation receipt differs from source")
    return actual


def verify_opening_accounting() -> dict[str, Any]:
    """Reconcile all V3 source and route ledgers without altering their entries."""
    receipt = verify_receipt()
    totals: list[int] = []
    attempts: set[str] = {ATTEMPT_ID}
    for path, expected_calls, expected_total in (
        (LEAN_LEDGER, 2, 26_988),
        (SOURCE_LEDGER, 2, 27_022),
    ):
        _, events = ledger._read(path)
        reserved = [row for row in events if row.get("event") == "reserved"]
        completed = [row for row in events if row.get("event") == "completed"]
        ids = {row.get("subject_attempt_id") for row in reserved}
        if (
            len(reserved) != expected_calls
            or len(completed) != expected_calls
            or len(ids) != 1
            or None in ids
            or attempts.intersection(ids)
            or {row.get("provider_call_id") for row in reserved} != {row.get("provider_call_id") for row in completed}
            or any(row.get("usage_status") != "known" for row in completed)
        ):
            raise ReconciliationError("source lineage call or attempt accounting differs")
        total = sum(row["input_tokens"] + row["output_tokens"] for row in completed)
        if total != expected_total:
            raise ReconciliationError("source lineage token total differs")
        attempts.update(ids)
        totals.append(total)
    route_rows = [json.loads(line) for line in ROUTE_LEDGER.read_text(encoding="utf-8").splitlines()]
    if len(route_rows) != ROUTE_LEDGER_ROWS or route_rows[0].get("record_type") != "p3_v3_successor_route_ledger":
        raise ReconciliationError("route ledger shape differs")
    route_events = route_rows[1:]
    previous = ledger._digest(route_rows[0])
    for seq, row in enumerate(route_events, 1):
        body = {key: value for key, value in row.items() if key != "event_sha256"}
        if (
            row.get("seq") != seq
            or row.get("previous_sha256") != previous
            or row.get("event_sha256") != ledger._digest(body)
        ):
            raise ReconciliationError("route ledger hash chain differs")
        previous = row["event_sha256"]
    if (
        [row.get("event") for row in route_events] != ["reserved", "completed", "reserved", "completed"]
        or [row.get("route") for row in route_events] != ["codex", "codex", "qwen", "qwen"]
        or any(row.get("status") != "passed" for row in (route_events[1], route_events[3]))
        or route_events[0].get("attempt_id") != route_events[1].get("attempt_id")
        or route_events[2].get("attempt_id") != route_events[3].get("attempt_id")
    ):
        raise ReconciliationError("route checks are incomplete or reordered")
    route_codex = route_events[1].get("usage", {})
    if route_codex.get("input_tokens") != ROUTE_CODEX_INPUT or route_codex.get("output_tokens") != ROUTE_CODEX_OUTPUT:
        raise ReconciliationError("Codex route usage differs")
    observed = sum(totals) + route_codex["input_tokens"] + route_codex["output_tokens"]
    charged = observed + receipt["debit_tokens"]
    if observed != KNOWN_OBSERVED or charged != CHARGED_OPENING or len(attempts) != TECHNICAL_ATTEMPTS:
        raise ReconciliationError("V3 opening balance or technical attempt count differs")
    return {
        "record_type": "p3_v3_qualification_opening_accounting",
        "schema": 1,
        "historical_receipt_sha256": sha(RECEIPT),
        "source_sha256": {
            "first_unknown_ledger": sha(RUNTIME / "provider-usage-v3.jsonl"),
            "lean_ledger": sha(LEAN_LEDGER),
            "verified_source_ledger": sha(SOURCE_LEDGER),
            "route_ledger": sha(ROUTE_LEDGER),
        },
        "known_observed_codex_tokens": observed,
        "historical_envelope_debit_tokens": receipt["debit_tokens"],
        "charged_v3_codex_tokens": charged,
        "technical_subject_attempt_ids": sorted(attempts),
        "technical_subject_attempts_used": len(attempts),
        "technical_subject_attempts_remaining": 24 - len(attempts),
        "route_checks_used": 2,
    }


def verify_opening_record(path: Path = OPENING) -> dict[str, Any]:
    """Require the saved opening record to equal fresh cross-ledger evidence."""
    actual = _json(path)
    expected = verify_opening_accounting()
    if actual != expected:
        raise ReconciliationError("qualification opening accounting differs from source")
    return actual


if __name__ == "__main__":
    print(json.dumps(verify_runtime(), sort_keys=True, indent=2))
