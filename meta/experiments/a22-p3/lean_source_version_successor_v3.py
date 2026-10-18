#!/usr/bin/env python3
"""Exact hash gate for the separate source version-check successor."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import usage_ledger_v3 as prior_ledger
import usage_ledger_version_successor_v3 as ledger

HERE = Path(__file__).resolve().parent
PROPOSAL = HERE / "V3_SOURCE_VERSION_SUCCESSOR_PROPOSAL.md"
SEAL = HERE / "runs" / "lean-source-protocol-seal-v1.json"
APPROVAL = HERE / "runs" / "lean-source-approval-template-v1.json"
CHAT_APPROVAL_EVIDENCE = HERE / "runs" / "lean-source-chat-approval-evidence-v1.json"
OPERATIONAL_SEAL = HERE / "runs" / "source-version-successor-seal-v1.json"
OPERATIONAL_APPROVAL = HERE / "runs" / "source-version-successor-approval-v1.json"
OPERATIONAL_ACCEPTANCE_EVIDENCE = HERE / "runs" / "source-version-successor-acceptance-evidence-v1.json"
PREFLIGHT_REPORT = HERE / "runs" / "source-version-successor-preflight-v1.json"
PREVIOUS_OPERATIONAL_SEAL = HERE / "runs" / "lean-source-operational-seal-v1.json"
PRIOR_LEDGER = Path("/tmp/a22-p3-v3-lean-f450a4a726b3/provider-usage-v3.jsonl")  # noqa: S108
PRIOR_LEDGER_SHA256 = "a918352f2108acb9fdbde653ebf22c1626098c65d1da04a46aee49398770d4cb"
PRIOR_OBSERVED_TOKENS = 26_988
PRIOR_COMPLETED_CALLS = 2
PREVIOUS_CHAT_SEAL = HERE / "runs" / "source-phase-chat-evidence-seal-v3-4.json"
PARSER_SEAL = HERE / "runs" / "usage-parser-amendment-seal-v1.json"
SOURCE_NAMES = (
    "dispatch_v3.py",
    "source_phase_v3.py",
    "usage_ledger_v3.py",
    "usage_ledger_version_successor_v3.py",
    "v3_runner_version_successor.py",
    "quota_adapter_v3.py",
    "lean_source_protocol_v3.py",
    "lean_source_version_successor_v3.py",
)


class ProtocolError(ValueError):
    """The proposal, seal, or approval is missing, stale, or malformed."""


def sha256(path: Path) -> str:
    """Return the exact file digest used by the prospective chain."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validated_prior_ledger() -> str:
    """Bind the exact terminal attempt and its two known Codex debits."""
    if sha256(PRIOR_LEDGER) != PRIOR_LEDGER_SHA256:
        raise ProtocolError("prior terminal V3 ledger differs from the frozen evidence")
    _, events = prior_ledger._read(PRIOR_LEDGER)
    completions = [event for event in events if event.get("event") == "completed"]
    if (
        len(completions) != PRIOR_COMPLETED_CALLS
        or any(event.get("route") != "codex" or event.get("usage_status") != "known" for event in completions)
        or sum(event["input_tokens"] + event["output_tokens"] for event in completions) != PRIOR_OBSERVED_TOKENS
    ):
        raise ProtocolError("prior terminal V3 ledger lacks the two known usage debits")
    return PRIOR_LEDGER_SHA256


def expected_seal() -> dict[str, Any]:
    """Return the prospective successor seal body without writing it."""
    return {
        "schema": 1,
        "record_type": "p3_v3_lean_source_protocol_seal",
        "status": "proposal_only_not_accepted",
        "proposal_sha256": sha256(PROPOSAL),
        "previous_usage_parser_seal_sha256": sha256(PARSER_SEAL),
        "previous_chat_evidence_seal_sha256": sha256(PREVIOUS_CHAT_SEAL),
        "source_sha256": {name: sha256(HERE / name) for name in SOURCE_NAMES},
        "regression_sha256": {
            name: sha256(HERE.parents[1] / "tests" / name)
            for name in ("test_a22_p3_lean_source_protocol_v3.py", "test_a22_p3_source_phase_v3.py")
        },
        "scope": ["technical_source"],
        "owner_accepted": False,
        "dispatch_allowed": False,
    }


def validate_seal(path: Path = SEAL) -> dict[str, Any]:
    """Require exact bytes for the successor proposal and every bound source."""
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("lean source successor seal is unavailable or malformed") from exc
    expected = expected_seal()
    if actual != expected:
        raise ProtocolError("lean source successor seal is stale or does not bind exact sources")
    return actual


def approval_template(*, seal_path: Path = SEAL) -> dict[str, Any]:
    """Build a reviewable, explicitly default-deny approval record."""
    seal = validate_seal(seal_path)
    return {
        "schema": 1,
        "record_type": "p3_v3_lean_source_protocol_approval",
        "proposal_sha256": seal["proposal_sha256"],
        "seal_sha256": sha256(seal_path),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
    }


def validate_approval(path: Path = APPROVAL, *, seal_path: Path = SEAL) -> dict[str, Any]:
    """Validate exact bindings and keep every authorization field denied."""
    expected = approval_template(seal_path=seal_path)
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("lean source approval is unavailable or malformed") from exc
    if actual != expected:
        raise ProtocolError("lean source approval differs from its default-deny template")
    return actual


def expected_operational_seal() -> dict[str, Any]:
    """Bind the adopted implementation while preserving the user-approved proposal seal."""
    return {
        "schema": 1,
        "record_type": "p3_v3_lean_source_operational_seal",
        "status": "implementation_ready_pending_exact_hash_acceptance",
        "proposal_sha256": sha256(PROPOSAL),
        "proposal_approval_seal_sha256": sha256(SEAL),
        "previous_operational_seal_sha256": sha256(PREVIOUS_OPERATIONAL_SEAL),
        "prior_ledger_sha256": validated_prior_ledger(),
        "prior_v3_observed_tokens": PRIOR_OBSERVED_TOKENS,
        "source_sha256": {
            name: sha256(HERE / name)
            for name in (*SOURCE_NAMES, "dispatch_v3.py", "source_phase_v3.py", "preflight_v3.py")
        },
        "regression_sha256": {
            name: sha256(HERE.parents[1] / "tests" / name) for name in ("test_a22_p3_source_version_successor.py",)
        },
        "scope": ["technical_source"],
        "provider_calls_started": 0,
    }


def expected_preflight_report(*, seal_path: Path = OPERATIONAL_SEAL) -> dict[str, Any]:
    """Describe the offline-only check result bound to the exact operational seal."""
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if seal != expected_operational_seal():
        raise ProtocolError("lean operational seal is stale or does not bind exact sources")
    runner = (HERE / "v3_runner_version_successor.py").read_text(encoding="utf-8")
    ledger_source = (HERE / "usage_ledger_version_successor_v3.py").read_text(encoding="utf-8")
    completion = ledger_source.split("def complete_lean(", 1)[1].split("\ndef summary(", 1)[0]
    checks = {
        "one_phase_scope": seal.get("scope") == ["technical_source"],
        "exact_source_hashes": seal.get("source_sha256") == expected_operational_seal()["source_sha256"],
        "terminal_unknown_usage_policy": "unknown V3 Codex usage locks dispatch" in ledger_source,
        "direct_turn_usage_only": 'event.get("type") == "turn.completed" and "usage" in event' in runner,
        "per_call_quota_gate_only": (
            runner.count("snapshot = quota_reader()") == 1
            and "post_quota_snapshot" not in runner
            and "quota_snapshot" not in completion
        ),
        "single_cell_no_retry": '"retry_authorized": False' in runner and '"repeat": 1' in runner,
        "prior_usage_bound": seal.get("prior_ledger_sha256") == validated_prior_ledger(),
    }
    return {
        "schema": 1,
        "record_type": "p3_v3_lean_source_preflight",
        "status": "PASSED_OFFLINE_SOURCE_PREFLIGHT",
        "proposal_sha256": sha256(PROPOSAL),
        "proposal_approval_seal_sha256": sha256(SEAL),
        "operational_seal_sha256": sha256(seal_path),
        "v3_prior_observed_tokens": PRIOR_OBSERVED_TOKENS,
        "v3_prior_ledger_sha256": validated_prior_ledger(),
        "network_calls": 0,
        "provider_calls": 0,
        "dispatch_allowed": False,
        "checks": checks,
    }


def validate_preflight_report(path: Path = PREFLIGHT_REPORT, *, seal_path: Path = OPERATIONAL_SEAL) -> dict[str, Any]:
    """Require the exact static report for the current code seal."""
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
        expected = expected_preflight_report(seal_path=seal_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("lean source preflight report is unavailable or malformed") from exc
    if actual != expected or not all(actual["checks"].values()):
        raise ProtocolError("lean source preflight report is stale or incomplete")
    return actual


def operational_approval_template(
    *, seal_path: Path = OPERATIONAL_SEAL, evidence_path: Path = CHAT_APPROVAL_EVIDENCE
) -> dict[str, Any]:
    """Record the proposal approval without extending it to an unapproved code hash."""
    return {
        "schema": 1,
        "record_type": "p3_v3_lean_source_operational_approval",
        "proposal_sha256": sha256(PROPOSAL),
        "proposal_approval_seal_sha256": sha256(SEAL),
        "operational_seal_sha256": sha256(seal_path),
        "v3_prior_observed_tokens": PRIOR_OBSERVED_TOKENS,
        "v3_prior_ledger_sha256": validated_prior_ledger(),
        "proposal_acceptance": {
            "owner_accepted": True,
            "message_id": "msg_01a1402b-806a-7a31-9fe9-a662b3f251ae",
            "evidence_sha256": sha256(evidence_path),
            "requested_seal_sha256": sha256(SEAL),
            "scope": ["technical_source"],
        },
        "implementation_acceptance": {
            "owner_accepted": False,
            "message_id": None,
            "accepted_operational_seal_sha256": None,
            "evidence_sha256": None,
        },
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
    }


def validate_operational_approval(
    path: Path = OPERATIONAL_APPROVAL,
    *,
    seal_path: Path = OPERATIONAL_SEAL,
    evidence_path: Path = CHAT_APPROVAL_EVIDENCE,
    implementation_evidence_path: Path = OPERATIONAL_ACCEPTANCE_EVIDENCE,
) -> dict[str, Any]:
    """Require a separate owner acknowledgement of the exact adopted code seal."""
    try:
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        implementation_evidence = json.loads(implementation_evidence_path.read_text(encoding="utf-8"))
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("lean operational seal, approval, or chat evidence is unavailable") from exc
    if seal != expected_operational_seal():
        raise ProtocolError("lean operational seal is stale or does not bind exact sources")
    expected = operational_approval_template(seal_path=seal_path, evidence_path=evidence_path)
    acceptance = evidence.get("approval", {})
    if (
        acceptance.get("message_id") != expected["proposal_acceptance"]["message_id"]
        or evidence.get("request", {}).get("requested_seal_sha256") != sha256(SEAL)
        or evidence.get("scope") != ["technical_source"]
    ):
        raise ProtocolError("recorded proposal approval evidence differs from the exact chat approval")
    mutable = {"implementation_acceptance", "dispatch_allowed", "authorized_phases", "named_stop_operator"}
    if set(actual) != set(expected) or any(
        actual.get(key) != value for key, value in expected.items() if key not in mutable
    ):
        raise ProtocolError("lean operational approval has stale bindings or malformed schema")
    implementation = actual.get("implementation_acceptance")
    implementation_message = implementation_evidence.get("approval", {})
    if (
        not isinstance(implementation, dict)
        or implementation.get("owner_accepted") is not True
        or implementation.get("accepted_operational_seal_sha256") != sha256(seal_path)
        or not isinstance(implementation.get("message_id"), str)
        or not implementation["message_id"].strip()
        or implementation.get("evidence_sha256") != sha256(implementation_evidence_path)
        or implementation_evidence.get("record_type") != "p3_v3_lean_source_operational_acceptance_evidence"
        or implementation_message.get("message_id") != implementation.get("message_id")
        or implementation_message.get("operational_seal_sha256") != sha256(seal_path)
        or implementation_evidence.get("scope") != ["technical_source"]
        or actual.get("dispatch_allowed") is not True
        or actual.get("authorized_phases") != ["technical_source"]
        or not isinstance(actual.get("named_stop_operator"), str)
        or not actual["named_stop_operator"].strip()
    ):
        raise ProtocolError("exact operational seal lacks separate owner authorization")
    return actual


def initialize_operational_ledger(
    path: Path, *, approval_path: Path = OPERATIONAL_APPROVAL, seal_path: Path = OPERATIONAL_SEAL
) -> dict[str, Any]:
    """Create a one-shot, empty ledger bound to the adopted approval and code seal."""
    approval = validate_operational_approval(approval_path, seal_path=seal_path)
    header = {
        "schema": 1,
        "record_type": "p3_v3_ledger_header",
        "epoch_id": ledger.fresh_id(ledger._historical_ids()),
        "proposal_sha256": ledger.sha256(ledger.PLAN),
        "packet_seal_sha256": ledger.sha256(ledger.PACKET_SEAL),
        "approval_sha256": ledger.sha256(approval_path),
        "lean_proposal_sha256": sha256(PROPOSAL),
        "operational_seal_sha256": sha256(seal_path),
        "v3_prior_observed_tokens": PRIOR_OBSERVED_TOKENS,
        "v3_prior_ledger_sha256": validated_prior_ledger(),
        "codex_epoch_limit_tokens": ledger.CODEX_LIMIT,
        "v2_known_usage_tokens_historical_only": 153_614,
        "q1461_disposition_historical_only": ledger.UNKNOWN_USAGE,
        "dispatch_ready": False,
        "source_phase_only": True,
    }
    data = (json.dumps(header, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        stored, events = ledger._read(path)
        if events or any(stored.get(key) != value for key, value in header.items() if key not in {"epoch_id"}):
            raise ProtocolError("lean source ledger already has activity or stale bindings") from None
        return stored
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    if approval.get("authorized_phases") != ["technical_source"]:
        raise ProtocolError("lean approval scope is not the single technical_source phase")
    return header


def require_operational_dispatch(
    *, approval_path: Path, seal_path: Path, preflight_path: Path, ledger_path: Path
) -> dict[str, Any]:
    """Consume exact approval, offline report, and an untouched one-cell ledger."""
    approval = validate_operational_approval(approval_path, seal_path=seal_path)
    validate_preflight_report(preflight_path, seal_path=seal_path)
    header, events = ledger._read(ledger_path)
    expected = {
        "proposal_sha256": ledger.sha256(ledger.PLAN),
        "packet_seal_sha256": ledger.sha256(ledger.PACKET_SEAL),
        "approval_sha256": ledger.sha256(approval_path),
        "lean_proposal_sha256": sha256(PROPOSAL),
        "operational_seal_sha256": sha256(seal_path),
        "v3_prior_observed_tokens": PRIOR_OBSERVED_TOKENS,
        "v3_prior_ledger_sha256": validated_prior_ledger(),
        "source_phase_only": True,
        "dispatch_ready": False,
    }
    if events or any(header.get(key) != value for key, value in expected.items()):
        raise ProtocolError("lean source dispatch requires an empty, exactly bound one-cell ledger")
    return {
        "status": "AUTHORIZED_SOURCE_PHASE",
        "phase": "technical_source",
        "owner_acceptance": approval["implementation_acceptance"]["message_id"],
        "provider_processes_started": 0,
    }
