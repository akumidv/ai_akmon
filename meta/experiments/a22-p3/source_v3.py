#!/usr/bin/env python3
"""Resolve only a fully evidenced V3 technical A source exchange."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import usage_ledger_v3 as ledger

SUBJECT_TURN_COUNT = 2
OPAQUE_ID_HEX_LENGTH = 32


class SourceError(ValueError):
    """V3 source exchange failed identity or evidence validation."""


def sha256(path: Path) -> str:
    """Hash one source artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_technical_source(record_path: Path, exchange_path: Path, case_path: Path,  # noqa: C901, PLR0912, PLR0913
                             arm_path: Path, rollout_path: Path, *,
                             ledger_path: Path = ledger.LEDGER) -> dict[str, Any]:
    """Validate a new technical A exchange and return its blinded packet source hashes."""
    record = json.loads(record_path.read_text(encoding="utf-8"))
    required = {"epoch_id", "run_id", "subject_attempt_id", "case", "arm", "tier", "repeat",
                "case_sha256", "arm_sha256", "model", "cli_version", "thread_id", "verified",
                "exchange_sha256", "rollout_sha256", "usage_calls", "packet_source_sha256",
                "provenance_scope"}
    if not isinstance(record, dict) or set(record) != required:
        raise SourceError("V3 technical source record schema is incomplete")
    if record["run_id"] == "q1461" or not re.fullmatch(r"[0-9a-f]{32}", str(record["run_id"])):
        raise SourceError("V2 q1461 or a non-opaque run ID cannot be a V3 source")
    if not re.fullmatch(rf"[0-9a-f]{{{OPAQUE_ID_HEX_LENGTH}}}", str(record["subject_attempt_id"])):
        raise SourceError("technical source subject-attempt ID is malformed")
    header, events = ledger._read(ledger_path)
    if record["epoch_id"] != header["epoch_id"]:
        raise SourceError("technical source belongs to a different V3 epoch")
    if (record["case"], record["arm"], record["tier"], record["repeat"]) != (
            "P3-01", "A", "strongest", 1):
        raise SourceError("V3 source must be the fresh P3-01 A strongest repeat-1 cell")
    if record["model"] != "gpt-6-astra" or record["cli_version"] != "codex-cli 0.156.1":
        raise SourceError("technical source does not match the frozen Codex pin")
    if record["verified"] is not True or not isinstance(record["thread_id"], str) or not record["thread_id"].strip():
        raise SourceError("technical source transcript or rollout is not verified")
    if record["provenance_scope"] != "evaluator_only":
        raise SourceError("technical source provenance is evaluator-only and cannot become scored input")
    if record["case_sha256"] != sha256(case_path) or record["arm_sha256"] != sha256(arm_path):
        raise SourceError("technical source case or arm hash differs from frozen input")
    exchange = json.loads(exchange_path.read_text(encoding="utf-8"))
    turns = exchange.get("turns") if isinstance(exchange, dict) else None
    if (exchange.get("run_id") != record["run_id"] or not isinstance(turns, list) or
            len(turns) != SUBJECT_TURN_COUNT or
            any(not isinstance(t, dict) or not isinstance(t.get("user"), str) or
                not isinstance(t.get("assistant"), str) or not t["assistant"].strip() or
                not re.fullmatch(r"[0-9a-f]{64}", str(t.get("events_sha256", ""))) for t in turns)):
        raise SourceError("source exchange must contain two complete, hashed turns")
    if record["exchange_sha256"] != sha256(exchange_path) or record["rollout_sha256"] != sha256(rollout_path):
        raise SourceError("exchange or rollout bytes differ from the source record")
    calls = record["usage_calls"]
    if not isinstance(calls, list) or len(calls) != SUBJECT_TURN_COUNT:
        raise SourceError("source requires exactly two correlated provider usage records")
    call_ids = {c.get("provider_call_id") for c in calls if isinstance(c, dict)}
    if len(call_ids) != SUBJECT_TURN_COUNT or any(not isinstance(c, dict) for c in calls):
        raise SourceError("source provider call IDs are missing or duplicated")
    completed = [e for e in events if e.get("event") == "completed" and
                 e.get("provider_call_id") in call_ids]
    reservations = [e for e in events if e.get("event") == "reserved" and
                    e.get("provider_call_id") in call_ids]
    if (len(completed) != SUBJECT_TURN_COUNT or len(reservations) != SUBJECT_TURN_COUNT or
            any(e.get("route") != "codex" or e.get("attempt_class") != "technical" or
                e.get("subject_attempt_id") != record["subject_attempt_id"] for e in reservations) or
            any(e.get("route") != "codex" or
                e.get("subject_attempt_id") != record["subject_attempt_id"] or
                e.get("outcome") != "accepted" or e.get("usage_status") != "known" for e in completed) or
            {e.get("turn_id") for e in completed} != {"turn-1", "turn-2"}):
        raise SourceError("source calls are not two accepted, usage-known V3 technical turns")
    for call in calls:
        match = next((e for e in completed if e["provider_call_id"] == call["provider_call_id"]), None)
        if (match is None or call.get("input_tokens") != match.get("input_tokens") or
                call.get("output_tokens") != match.get("output_tokens")):
            raise SourceError("source usage record does not match the V3 ledger")
    source_hashes = {"case_sha256": record["case_sha256"], "arm_sha256": record["arm_sha256"],
                     "exchange_sha256": record["exchange_sha256"], "rollout_sha256": record["rollout_sha256"]}
    packet_hash = hashlib.sha256(json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if record["packet_source_sha256"] != packet_hash:
        raise SourceError("blinded packet source hash does not match validated exchange inputs")
    return {"run_id": record["run_id"], "subject_attempt_id": record["subject_attempt_id"],
            "epoch_id": header["epoch_id"], "packet_source_sha256": packet_hash,
            "provenance_scope": "evaluator_only",
            "source_hashes": source_hashes}
