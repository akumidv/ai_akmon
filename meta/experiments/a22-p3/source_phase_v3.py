#!/usr/bin/env python3
"""Offline source-only approval and preflight gate for the A22 P3 V3 proposal."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import source_chat_evidence_v3
import source_v3
import usage_ledger_v3 as ledger

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2].resolve()
PLAN = HERE / "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md"
PACKET_SEAL = HERE / "seal.json"
BASE_SEAL = HERE / "seal-v3.json"
OPERATIVE_V3_SEAL_SHA256 = "58eea0362178111b0497e6fcd248dffb25b07dda295fa91de2d03205819cedde"
AMENDMENT_PROPOSAL = HERE / "V3_PHASED_SOURCE_AMENDMENT_PROPOSAL.md"
AMENDMENT_SEAL = HERE / "runs" / "source-phase-seal-v3.json"
SOURCE_APPROVAL = HERE / "runs" / "owner-approval-v3-source.json"
PREFLIGHT_REPORT = HERE / "runs" / "source-phase-preflight-v3.json"
SOURCE_FILE = HERE / "source_phase_v3.py"
CHAT_EVIDENCE_PROPOSAL = HERE / "V3_CHAT_EVIDENCE_AMENDMENT_PROPOSAL.md"
V2_HISTORY_PROPOSAL = HERE / "V3_V2_HISTORY_BINDING_AMENDMENT_PROPOSAL.md"
CHAT_EVIDENCE_ARTIFACT = Path("/tmp/a22-p3-v3-chat-evidence-2.json")  # noqa: S108
PREVIOUS_CHAT_EVIDENCE_SEAL = HERE / "runs" / "source-phase-chat-evidence-seal-v3-3.json"
CHAT_EVIDENCE_SEAL = HERE / "runs" / "source-phase-chat-evidence-seal-v3-4.json"
DEFAULT_AMENDMENT_SEAL = CHAT_EVIDENCE_SEAL
V2_HISTORY_ROOT = Path("/tmp/akmon-a22-p3-v2-20261011/meta/experiments/a22-p3")  # noqa: S108
V2_HISTORY_SHA256 = {
    "RUN_PLAN_V2_PROPOSAL.md": "89de386b05fbd38e70ed90da75a56c6f3aa584598314afdbb54de859c0f9b8f5",
    "seal.json": "a4e7036b5aae7ea4b603add4e7e98a7bde3331164a5fae5da5e85fbb75b66bcb",
    "runs/accepted-v2-seal.json": "dfa34f9da5ae18a6038b506170ea83226bbf026902db2951ad457b589499d0c9",
    "runs/owner-approval-v2.json": "986dc2d304c505f748624c2f261b92f027bf9d165593f9cad8d08a63420ed0e9",
}
DISPATCH_FILE = HERE / "dispatch_v3.py"
RUNNER_FILE = HERE / "v3_runner.py"
BASE_SOURCE_NAMES = {
    "RUN_PLAN_V3_CLEAN_RESTART_PROPOSAL.md", "usage_ledger_v3.py", "dispatch_v3.py",
    "v3_runner.py", "quota_adapter_v3.py", "preflight_v3.py", "source_v3.py",
}
APPROVAL_TYPE = "p3_v3_source_phase_owner_approval"
SEAL_TYPE = "p3_v3_source_phase_amendment_seal"
PHASE = "technical_source"
TWO_TURN_COUNT = 2
ID_SAMPLE_SIZE = 64
SHA256_HEX_LENGTH = 64


class SourcePhaseError(ValueError):
    """Source-only approval or preflight failed closed."""


def _outside_repo(path: Path, label: str) -> Path:
    """Resolve a runtime artifact path and reject the repository or sealed tree."""
    resolved = path.expanduser().resolve()
    if resolved in (REPO, HERE) or REPO in resolved.parents or HERE in resolved.parents:
        raise SourcePhaseError(f"{label} must resolve outside the repository and sealed source tree")
    return resolved


def sha256(path: Path) -> str:
    """Return a file's SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourcePhaseError(f"required JSON artifact is unavailable or malformed: {path.name}") from exc
    if not isinstance(value, dict):
        raise SourcePhaseError(f"required JSON artifact is not an object: {path.name}")
    return value


def expected_amendment_seal(*, plan: Path = PLAN, packet_seal: Path = PACKET_SEAL,
                            base_seal: Path = BASE_SEAL,
                            amendment_proposal: Path = AMENDMENT_PROPOSAL) -> dict[str, Any]:
    """Describe the separate amendment seal; this helper never writes it."""
    return {
        "schema": 1,
        "record_type": SEAL_TYPE,
        "amendment_proposal_sha256": sha256(amendment_proposal),
        "proposal_sha256": sha256(plan),
        "packet_seal_sha256": sha256(packet_seal),
        "operative_v3_seal_sha256": sha256(base_seal),
        "base_source_sha256": _read_json(base_seal).get("source_sha256"),
        "source_sha256": {**{name: sha256(plan if name == PLAN.name else HERE / name)
                              for name in _read_json(base_seal).get("source_sha256", {})},
                          SOURCE_FILE.name: sha256(SOURCE_FILE)},
        "phase": PHASE,
        "technical_source": {
            "case": "P3-01", "arm": "A", "tier": "strongest", "repeat": 1,
            "turns": TWO_TURN_COUNT,
        },
        "settings": {
            "codex_cli": "0.156.1", "codex_model": "gpt-6-astra", "effort": "medium",
            "turn_input_cap": 40_000, "codex_epoch_limit_tokens": ledger.CODEX_LIMIT,
            "five_hour_stop_percent": ledger.FIVE_HOUR_STOP_PERCENT,
            "weekly_stop_percent": ledger.WEEKLY_STOP_PERCENT,
            "retry_evidence_policy": "OBSERVED_NO_RETRY",
        },
    }


def validate_amendment_seal(*, seal_path: Path = AMENDMENT_SEAL, plan: Path = PLAN,
                            packet_seal: Path = PACKET_SEAL, base_seal: Path = BASE_SEAL,
                            amendment_proposal: Path = AMENDMENT_PROPOSAL) -> dict[str, Any]:
    """Verify the amendment seal and its binding to the current operative V3 seal."""
    base = _read_json(base_seal)
    required_base_sources = BASE_SOURCE_NAMES
    expected_settings = {
        "codex_cli": "0.156.1", "codex_model": "gpt-6-astra", "qwen_cli": "0.24.7",
        "qwen_model": "qwen3.8-27b", "qwen_thinking": "default",
        "codex_epoch_limit_tokens": ledger.CODEX_LIMIT,
        "five_hour_stop_percent": ledger.FIVE_HOUR_STOP_PERCENT,
        "weekly_stop_percent": ledger.WEEKLY_STOP_PERCENT,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
    }
    base_sources = base.get("source_sha256")
    if (base.get("schema") != 1 or base.get("record_type") != "p3_v3_plan_seal" or
            sha256(base_seal) != OPERATIVE_V3_SEAL_SHA256 or
            base.get("proposal_sha256") != sha256(plan) or
            base.get("packet_seal_sha256") != sha256(packet_seal) or
            base.get("settings") != expected_settings or not isinstance(base_sources, dict) or
            set(base_sources) != required_base_sources):
        raise SourcePhaseError("operative V3 seal is unavailable, malformed, or binds different inputs")
    actual = _read_json(seal_path)
    expected = expected_amendment_seal(
        plan=plan, packet_seal=packet_seal, base_seal=base_seal,
        amendment_proposal=amendment_proposal)
    if actual != expected:
        raise SourcePhaseError("source-phase amendment seal is stale or does not bind exact inputs")
    if set(actual["source_sha256"]) != required_base_sources | {SOURCE_FILE.name}:
        raise SourcePhaseError("source-phase amendment seal does not bind the complete current runner set")
    for name, digest in actual["source_sha256"].items():
        source_path = plan if name == PLAN.name else HERE / name
        if sha256(source_path) != digest:
            raise SourcePhaseError(f"source-phase amendment source changed: {name}")
    return actual


def expected_chat_evidence_seal() -> dict[str, Any]:
    """Bind chat evidence and accepted V2 history without rewriting prior seals."""
    artifact = source_chat_evidence_v3.validate_artifact(
        artifact_path=CHAT_EVIDENCE_ARTIFACT,
        expected_quote=source_chat_evidence_v3.CANONICAL_QUOTE)
    source_names = ("source_phase_v3.py", "source_chat_evidence_v3.py", "dispatch_v3.py", "v3_runner.py")
    return {
        "schema": 1,
        "record_type": "p3_v3_source_evidence_amendment_seal",
        "chat_evidence_proposal_sha256": sha256(CHAT_EVIDENCE_PROPOSAL),
        "v2_history_proposal_sha256": sha256(V2_HISTORY_PROPOSAL),
        "prior_amendment_seal_sha256": sha256(AMENDMENT_SEAL),
        "superseded_chat_evidence_seal_sha256": sha256(PREVIOUS_CHAT_EVIDENCE_SEAL),
        "operative_v3_seal_sha256": sha256(BASE_SEAL),
        "source_sha256": {name: sha256(HERE / name) for name in source_names},
        "external_evidence": artifact,
        "accepted_v2_history": _v2_history_binding(),
        "phase": PHASE,
        "authorization_scope": [PHASE],
        "normalization_id": source_chat_evidence_v3.NORMALIZATION_ID,
    }


def validate_chat_evidence_seal(*, seal_path: Path = CHAT_EVIDENCE_SEAL) -> dict[str, Any]:
    """Verify the additive evidence seal and preserve the prior seal as historical input."""
    if sha256(AMENDMENT_SEAL) != "c4977c962a4c216abdc57951c981a2691063657f8928f9201847045cd96e84a8":
        raise SourcePhaseError("prior source-phase amendment seal changed")
    actual = _read_json(seal_path)
    expected = expected_chat_evidence_seal()
    if actual != expected:
        raise SourcePhaseError("chat-evidence amendment seal is stale or does not bind exact inputs")
    return actual


def _v2_history_binding(root: Path = V2_HISTORY_ROOT) -> dict[str, Any]:
    """Return the explicit path and fixed digest manifest for the accepted V2 snapshot."""
    resolved = root.expanduser().resolve()
    return {
        "path": str(resolved),
        "storage_assurance": "hash-matching preserved snapshot; storage is not immutable",
        "files": dict(V2_HISTORY_SHA256),
    }


def validate_source_seal(*, seal_path: Path, plan: Path = PLAN, packet_seal: Path = PACKET_SEAL,
                         base_seal: Path = BASE_SEAL,
                         amendment_proposal: Path = AMENDMENT_PROPOSAL) -> dict[str, Any]:
    """Dispatch to the preserved historical seal or its additive evidence binding."""
    if seal_path.resolve() == CHAT_EVIDENCE_SEAL.resolve():
        actual = validate_chat_evidence_seal(seal_path=seal_path)
        if (sha256(base_seal) != actual["operative_v3_seal_sha256"] or
                sha256(AMENDMENT_SEAL) != actual["prior_amendment_seal_sha256"] or
                sha256(amendment_proposal) != sha256(AMENDMENT_PROPOSAL)):
            raise SourcePhaseError("chat-evidence seal is bound to different source-phase inputs")
        return actual
    return validate_amendment_seal(seal_path=seal_path, plan=plan, packet_seal=packet_seal,
                                    base_seal=base_seal, amendment_proposal=amendment_proposal)


def approval_template(*, plan: Path = PLAN, base_seal: Path = BASE_SEAL,
                      amendment_seal: Path = DEFAULT_AMENDMENT_SEAL,
                      amendment_proposal: Path = AMENDMENT_PROPOSAL) -> dict[str, Any]:
    """Return a default-deny approval shape without recording owner acceptance."""
    return {
        "schema": 1,
        "record_type": APPROVAL_TYPE,
        "amendment_proposal_sha256": sha256(amendment_proposal),
        "proposal_sha256": sha256(plan),
        "operative_v3_seal_sha256": sha256(base_seal),
        "amendment_seal_sha256": sha256(amendment_seal),
        "accepted_v2_history": _v2_history_binding(),
        "owner_accepted": False,
        "new_epoch_budget_accepted": False,
        "v2_usage_exclusion_accepted": False,
        "subscription_thresholds_accepted": False,
        "observed_no_retry_accepted": False,
        "source_conditions_accepted": False,
        "named_stop_operator": None,
        "authorized_phases": [],
        "acceptance_evidence": None,
    }


def validate_source_approval(*, approval_path: Path = SOURCE_APPROVAL,  # noqa: PLR0913
                             seal_path: Path = DEFAULT_AMENDMENT_SEAL, plan: Path = PLAN,
                             packet_seal: Path = PACKET_SEAL, base_seal: Path = BASE_SEAL,
                             amendment_proposal: Path = AMENDMENT_PROPOSAL) -> dict[str, Any]:
    """Require a source-only owner decision bound to both seal epochs."""
    validate_source_seal(seal_path=seal_path, plan=plan, packet_seal=packet_seal,
                         base_seal=base_seal, amendment_proposal=amendment_proposal)
    record = _read_json(approval_path)
    expected = approval_template(plan=plan, base_seal=base_seal, amendment_seal=seal_path,
                                 amendment_proposal=amendment_proposal)
    if set(record) != set(expected) or any(record.get(key) != value for key, value in expected.items()
                                           if key not in {
                                               "owner_accepted", "new_epoch_budget_accepted",
                                               "v2_usage_exclusion_accepted", "subscription_thresholds_accepted",
                                               "observed_no_retry_accepted", "source_conditions_accepted",
                                               "named_stop_operator", "authorized_phases", "acceptance_evidence",
                                           }):
        raise SourcePhaseError("source-phase approval schema or bound hashes are stale")
    required_true = (
        "owner_accepted", "new_epoch_budget_accepted", "v2_usage_exclusion_accepted",
        "subscription_thresholds_accepted", "observed_no_retry_accepted", "source_conditions_accepted",
    )
    if any(record.get(field) is not True for field in required_true):
        raise SourcePhaseError("source-phase approval is default-deny or omits an accepted condition")
    operator = record.get("named_stop_operator")
    if not isinstance(operator, str) or not operator.strip():
        raise SourcePhaseError("source-phase approval must name the human stop operator")
    if record.get("authorized_phases") != [PHASE]:
        raise SourcePhaseError("source-phase approval must authorize only technical_source")
    evidence = record.get("acceptance_evidence")
    transcript_hash = _validate_acceptance_transcript(evidence, amendment_proposal)
    for field, expected_hash in (
            ("transcript_sha256", transcript_hash),
            ("amendment_proposal_sha256", expected["amendment_proposal_sha256"]),
            ("proposal_sha256", expected["proposal_sha256"]),
            ("operative_v3_seal_sha256", expected["operative_v3_seal_sha256"]),
            ("amendment_seal_sha256", expected["amendment_seal_sha256"])):
        value = evidence.get(field)
        if (not isinstance(value, str) or len(value) != SHA256_HEX_LENGTH or
                any(char not in "0123456789abcdef" for char in value) or
                (expected_hash is not None and value != expected_hash)):
            raise SourcePhaseError("owner acceptance evidence is malformed or bound to different hashes")
    return record


def _validate_acceptance_transcript(evidence: object, amendment_proposal: Path) -> str:
    """Verify the external transcript bytes and exact decision sentence."""
    required = {"exact_quote", "transcript_path", "transcript_sha256", "amendment_proposal_sha256",
                "proposal_sha256", "operative_v3_seal_sha256", "amendment_seal_sha256"}
    if (not isinstance(evidence, dict) or set(evidence) != required or
            not isinstance(evidence.get("exact_quote"), str) or not evidence["exact_quote"].strip()):
        raise SourcePhaseError("source-phase approval lacks exact owner acceptance evidence")
    transcript_path = _outside_repo(Path(str(evidence["transcript_path"])), "owner acceptance transcript")
    try:
        transcript_bytes = transcript_path.read_bytes()
        transcript = json.loads(transcript_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise SourcePhaseError("owner acceptance transcript is unavailable or malformed") from exc
    if isinstance(transcript, dict) and transcript.get("record_type") == "p3_v3_chat_acceptance_evidence":
        expected_chat_quote = source_chat_evidence_v3.CANONICAL_QUOTE
        if evidence.get("exact_quote") != expected_chat_quote:
            raise SourcePhaseError("chat acceptance quote differs from its canonical normalized text")
        try:
            return source_chat_evidence_v3.validate_artifact(
                artifact_path=transcript_path, expected_quote=expected_chat_quote,
                source_log_path=Path(str(transcript.get("source_log_path"))))["artifact_sha256"]
        except source_chat_evidence_v3.ChatEvidenceError as exc:
            raise SourcePhaseError("raw chat evidence does not match the retained session log") from exc
    expected_quote = _owner_acceptance_quote(amendment_proposal)
    if (not isinstance(transcript, dict) or set(transcript) != {
            "record_type", "session_id", "message_id", "owner", "text"} or
            transcript.get("record_type") != "p3_v3_owner_acceptance_transcript" or
            not isinstance(transcript.get("session_id"), str) or not transcript["session_id"].strip() or
            not isinstance(transcript.get("message_id"), str) or not transcript["message_id"].strip() or
            not isinstance(transcript.get("owner"), str) or not transcript["owner"].strip() or
            transcript.get("text") != expected_quote or evidence.get("exact_quote") != expected_quote):
        raise SourcePhaseError("owner acceptance transcript does not contain the exact amended decision")
    return hashlib.sha256(transcript_bytes).hexdigest()


def _owner_acceptance_quote(amendment_proposal: Path) -> str:
    """Extract the one exact decision sentence that the owner must accept."""
    lines = amendment_proposal.read_text(encoding="utf-8").splitlines()
    quotes = [line[2:].strip() for line in lines if line.startswith("> I accept the V3-only ")]
    if len(quotes) != 1:
        raise SourcePhaseError("amendment proposal must contain exactly one canonical owner decision")
    return quotes[0]


def _default_campaign_approval(path: Path = ledger.APPROVAL) -> bool:
    """Keep the separate full-campaign approval default-deny during source-only work."""
    record = _read_json(path)
    return (record.get("owner_accepted") is False and record.get("dispatch_allowed") is False and
            record.get("authorized_phases") == [])


def _validate_v2_history(root: Path = V2_HISTORY_ROOT) -> bool:
    """Verify exact accepted V2 snapshot bytes and their internal approval bindings."""
    resolved = root.expanduser().resolve()
    if resolved != Path(_v2_history_binding()["path"]):
        return False
    paths = {name: resolved / name for name in V2_HISTORY_SHA256}
    if any(not path.is_file() or sha256(path) != V2_HISTORY_SHA256[name]
           for name, path in paths.items()):
        return False
    try:
        approval = _read_json(paths["runs/owner-approval-v2.json"])
        accepted_seal = _read_json(paths["runs/accepted-v2-seal.json"])
    except SourcePhaseError:
        return False
    proposal_hash = V2_HISTORY_SHA256["RUN_PLAN_V2_PROPOSAL.md"]
    return (
        accepted_seal.get("schema") == 1 and
        accepted_seal.get("record_type") == "p3_v2_plan_seal" and
        accepted_seal.get("proposal_sha256") == proposal_hash and
        accepted_seal.get("packet_seal_sha256") == V2_HISTORY_SHA256["seal.json"] and
        approval.get("record_type") == "p3_v2_owner_approval" and
        approval.get("proposal_sha256") == proposal_hash and
        approval.get("accepted_v2_seal_sha256") == V2_HISTORY_SHA256["runs/accepted-v2-seal.json"]
    )


def _q1461_rejected(runtime: Path) -> bool:
    """Exercise the source resolver's first identity gate with a synthetic V2 ID."""
    record = runtime / "q1461-source.json"
    record.write_text(json.dumps({
        "epoch_id": "0" * 32, "run_id": "q1461", "subject_attempt_id": "1" * 32,
        "case": "P3-01", "arm": "A", "tier": "strongest", "repeat": 1,
        "case_sha256": "a" * 64, "arm_sha256": "b" * 64, "model": "gpt-6-astra",
        "cli_version": "codex-cli 0.156.1", "thread_id": "fixture", "verified": True,
        "exchange_sha256": "c" * 64, "rollout_sha256": "d" * 64, "usage_calls": [],
        "packet_source_sha256": "e" * 64, "provenance_scope": "evaluator_only",
    }), encoding="utf-8")
    try:
        source_v3.resolve_technical_source(
            record, runtime / "missing-exchange.json", runtime / "missing-case.json",
            runtime / "missing-arm.txt", runtime / "missing-rollout.jsonl",
            ledger_path=runtime / "missing-ledger.jsonl")
    except source_v3.SourceError as exc:
        return "q1461" in str(exc)
    return False


def _synthetic_checks() -> dict[str, str]:
    """Exercise quota, usage, budget, and persisted-stop failures offline."""
    good = {
        "captured_utc": "2030-01-01T00:00:00Z", "source": "synthetic",
        "source_version": "source-phase-fixture", "freshness_seconds": 0,
        "five_hour_used_percent": 1, "five_hour_reset_utc": "2030-01-01T05:00:00Z",
        "weekly_used_percent": 1, "weekly_reset_utc": "2030-01-08T00:00:00Z",
        "raw_redacted_sha256": "a" * 64,
    }
    ledger.validate_quota(good, "codex")
    cases = {
        "five_hour_threshold": {**good, "five_hour_used_percent": ledger.FIVE_HOUR_STOP_PERCENT},
        "weekly_threshold": {**good, "weekly_used_percent": ledger.WEEKLY_STOP_PERCENT},
        "stale_snapshot": {**good, "freshness_seconds": ledger.MAX_QUOTA_FRESHNESS_SECONDS + 1},
    }
    for name, snapshot in cases.items():
        try:
            ledger.validate_quota(snapshot, "codex")
        except ledger.LedgerError:
            continue
        raise SourcePhaseError(f"synthetic source-phase policy check did not stop: {name}")
    results = dict.fromkeys(cases, "PASSED")
    try:
        ledger.validate_quota(None, "codex")
    except ledger.LedgerError:
        results["missing_quota"] = "PASSED"
    else:
        raise SourcePhaseError("synthetic source-phase policy check did not stop: missing_quota")
    results.update(_synthetic_ledger_checks(good))
    return results


def _synthetic_ledger_checks(good_quota: dict[str, Any]) -> dict[str, str]:
    """Prove unknown usage, token ceiling, and persisted quota stops block dispatch."""
    outcomes: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="p3-v3-source-policy-") as temp:
        root = Path(temp)
        approval = root / "draft-approval.json"
        approval.write_text(json.dumps({
            "schema": 1, "record_type": "p3_v3_owner_approval", "owner_accepted": False,
            "dispatch_allowed": False, "authorized_phases": [], "preflight_status": "NOT_RUN",
        }), encoding="utf-8")
        for label, usage, post_quota, error in (
                ("unknown_usage_lock", None, good_quota, "unknown V3 Codex usage locks dispatch"),
                ("token_ceiling", {"input_tokens": ledger.CODEX_LIMIT, "output_tokens": 0},
                 good_quota, "V3 Codex epoch token ceiling reached"),
                ("persisted_stop_control", {"input_tokens": 1, "output_tokens": 0},
                 {**good_quota, "five_hour_used_percent": ledger.FIVE_HOUR_STOP_PERCENT},
                 "prior V3 quota checkpoint permanently stopped dispatch")):
            path = root / f"{label}.jsonl"
            ledger.initialize(path, plan=PLAN, packet_seal=PACKET_SEAL, approval=approval)
            call = ledger.reserve("codex", "technical", quota_snapshot=good_quota, path=path)
            try:
                ledger.complete(call, outcome="accepted" if usage else "failed", usage=usage,
                                quota_snapshot=post_quota, path=path,
                                failure_code=None if usage else "synthetic_missing_usage")
            except ledger.LedgerError:
                if label != "persisted_stop_control":
                    raise
            try:
                ledger.reserve("codex", "technical", quota_snapshot=good_quota, path=path)
            except ledger.LedgerError as exc:
                if error not in str(exc):
                    raise SourcePhaseError(f"synthetic source-phase policy check failed: {label}") from exc
                outcomes[label] = "PASSED"
            else:
                raise SourcePhaseError(f"synthetic source-phase policy check did not stop: {label}")
    return outcomes


def run_source_preflight(*, runtime_root: Path, approval_path: Path = SOURCE_APPROVAL,  # noqa: C901, PLR0912, PLR0913, PLR0915
                         seal_path: Path = DEFAULT_AMENDMENT_SEAL, plan: Path = PLAN,
                         packet_seal: Path = PACKET_SEAL, base_seal: Path = BASE_SEAL,
                         amendment_proposal: Path = AMENDMENT_PROPOSAL,
                         campaign_approval: Path = ledger.APPROVAL,
                         report_path: Path | None = None) -> dict[str, Any]:
    """Run offline source-phase checks; never authorize or launch a provider process."""
    runtime = _outside_repo(runtime_root, "source-phase runtime")
    if report_path is not None:
        _outside_repo(report_path, "source-phase preflight report")
    runtime.mkdir(parents=True, exist_ok=True)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise SourcePhaseError("source-phase static preflight attempted a process or network operation")

    with patch.object(subprocess, "Popen", forbidden), patch.object(subprocess, "run", forbidden), \
            patch.object(socket, "create_connection", forbidden), \
            patch.object(socket, "getaddrinfo", forbidden), \
            patch.object(socket.socket, "connect", forbidden):
        base = _read_json(base_seal)
        amendment = validate_source_seal(
            seal_path=seal_path, plan=plan, packet_seal=packet_seal, base_seal=base_seal,
            amendment_proposal=amendment_proposal)
        validate_source_approval(
            approval_path=approval_path, seal_path=seal_path, plan=plan, packet_seal=packet_seal,
            base_seal=base_seal, amendment_proposal=amendment_proposal)
        if not _default_campaign_approval(campaign_approval):
            raise SourcePhaseError("full-campaign approval must remain default-deny during source-only phase")
        if not amendment or not base:
            raise SourcePhaseError("source-phase seal verification returned no bindings")
        hashes_before = {
            str(path): sha256(path) for path in (plan, packet_seal, base_seal, seal_path,
                                                 amendment_proposal, SOURCE_FILE, approval_path,
                                                 CHAT_EVIDENCE_PROPOSAL, V2_HISTORY_PROPOSAL,
                                                 CHAT_EVIDENCE_ARTIFACT)
        }
        hashes_before.update({str(V2_HISTORY_ROOT / name): sha256(V2_HISTORY_ROOT / name)
                              for name in V2_HISTORY_SHA256})
        hashes_before["selected_log_records"] = source_chat_evidence_v3.capture()[
            "selected_log_records_sha256"]
        if not _validate_v2_history():
            raise SourcePhaseError("external V2 history snapshot does not match its accepted hash manifest")
        checks = _synthetic_checks()
        identifiers = {ledger.fresh_id() for _ in range(ID_SAMPLE_SIZE)}
        if len(identifiers) != ID_SAMPLE_SIZE or "q1461" in identifiers or identifiers & ledger._historical_ids():
            raise SourcePhaseError("synthetic V3 identity collision check failed")
        if not _q1461_rejected(runtime):
            raise SourcePhaseError("technical source resolver did not reject q1461")
        probe = runtime / ("source-preflight-" + secrets.token_hex(8))
        fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        try:
            os.write(fd, b"source-phase-runtime-check")
            os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            if os.read(fd, 64) != b"source-phase-runtime-check":
                raise SourcePhaseError("isolated source-phase runtime readback failed")
        finally:
            os.close(fd)
        with probe.open("rb") as stream:
            if stream.read() != b"source-phase-runtime-check":
                raise SourcePhaseError("isolated source-phase runtime readback failed")
        probe.unlink()
        if hashes_before != {
                str(path): sha256(path) for path in (plan, packet_seal, base_seal, seal_path,
                                                      amendment_proposal, SOURCE_FILE, approval_path,
                                                      CHAT_EVIDENCE_PROPOSAL, V2_HISTORY_PROPOSAL,
                                                      CHAT_EVIDENCE_ARTIFACT)} | {
            **{str(V2_HISTORY_ROOT / name): sha256(V2_HISTORY_ROOT / name)
               for name in V2_HISTORY_SHA256},
            "selected_log_records": source_chat_evidence_v3.capture()["selected_log_records_sha256"]
        }:
            raise SourcePhaseError("sealed source-phase inputs changed during static preflight")

        runner_source = RUNNER_FILE.read_text(encoding="utf-8")
        dispatch_source = DISPATCH_FILE.read_text(encoding="utf-8")
        source_resolver = (HERE / "source_v3.py").read_text(encoding="utf-8")
        if ("source_preflight_report" not in runner_source or
                "verify_source_dispatch_gate" not in dispatch_source or
                "source_phase_approval" not in dispatch_source or
                '"provenance_scope": "evaluator_only"' not in runner_source or
                'record["provenance_scope"] != "evaluator_only"' not in source_resolver):
            raise SourcePhaseError("source-only admission is not integrated into the technical runner")

    result = {
        "schema": 1,
        "record_type": "p3_v3_source_phase_preflight",
        "status": "PASSED_SOURCE_PHASE_PREFLIGHT",
        "proposal_sha256": sha256(plan),
        "packet_seal_sha256": sha256(packet_seal),
        "operative_v3_seal_sha256": sha256(base_seal),
        "amendment_proposal_sha256": sha256(amendment_proposal),
        "amendment_seal_sha256": sha256(seal_path),
        "approval_sha256": sha256(approval_path),
        "chat_evidence_proposal_sha256": sha256(CHAT_EVIDENCE_PROPOSAL),
        "v2_history_proposal_sha256": sha256(V2_HISTORY_PROPOSAL),
        "chat_evidence_artifact_sha256": sha256(CHAT_EVIDENCE_ARTIFACT),
        "chat_evidence_authentication": "unsigned local log evidence; not a cryptographic signature",
        "accepted_v2_history": _v2_history_binding(),
        "network_or_provider_calls": 0,
        "dispatch_allowed": False,
        "launch_ready": False,
        "source_phase_only": True,
        "campaign_approval_default_deny": True,
        "accepted_v2_history_status": "PASSED_HASH_VERIFIED_SNAPSHOT",
        "synthetic_quota_checks": checks,
        "q1461_source_rejection": "PASSED",
        "historical_id_collision_checks": {"status": "PASSED", "sample_size": ID_SAMPLE_SIZE},
        "runtime_write_read_delete": "PASSED",
        "runner_integration": "PASSED",
        "evaluator_only_source_scope": "PASSED",
        "blockers": [],
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode("utf-8")
        fd = os.open(report_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            ledger._write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
    return result


def verify_source_dispatch_gate(*, report: dict[str, Any], quota_snapshot: object,  # noqa: PLR0913
                                approval_path: Path = SOURCE_APPROVAL,
                                seal_path: Path = DEFAULT_AMENDMENT_SEAL, plan: Path = PLAN,
                                packet_seal: Path = PACKET_SEAL, base_seal: Path = BASE_SEAL,
                                amendment_proposal: Path = AMENDMENT_PROPOSAL,
                                campaign_approval: Path = ledger.APPROVAL,
                                require_quota: bool = True) -> dict[str, Any]:
    """Verify source-only owner scope and offline report; quota is checked per call."""
    approval = validate_source_approval(
        approval_path=approval_path, seal_path=seal_path, plan=plan, packet_seal=packet_seal,
        base_seal=base_seal, amendment_proposal=amendment_proposal)
    expected_bindings = {
        "proposal_sha256": sha256(plan), "packet_seal_sha256": sha256(packet_seal),
        "operative_v3_seal_sha256": sha256(base_seal),
        "amendment_proposal_sha256": sha256(amendment_proposal),
        "amendment_seal_sha256": sha256(seal_path), "approval_sha256": sha256(approval_path),
        "accepted_v2_history": _v2_history_binding(),
    }
    if (not isinstance(report, dict) or report.get("status") != "PASSED_SOURCE_PHASE_PREFLIGHT" or
            report.get("dispatch_allowed") is not False or report.get("network_or_provider_calls") != 0 or
            report.get("runner_integration") != "PASSED" or
            any(report.get(key) != value for key, value in expected_bindings.items())):
        raise SourcePhaseError("source-phase preflight report is absent, stale, or unsafe")
    with tempfile.TemporaryDirectory(prefix="p3-v3-source-gate-") as temp:
        current_report = run_source_preflight(
            runtime_root=Path(temp) / "runtime", approval_path=approval_path,
            seal_path=seal_path, plan=plan, packet_seal=packet_seal, base_seal=base_seal,
            amendment_proposal=amendment_proposal, campaign_approval=campaign_approval)
    if current_report != report:
        raise SourcePhaseError("source-phase preflight report differs from fresh offline checks")
    quota_hash = None
    if require_quota:
        try:
            quota = ledger.validate_quota(quota_snapshot, "codex")
        except ledger.LedgerError as exc:
            raise SourcePhaseError("fresh interpretable quota snapshot is required before source dispatch") from exc
        quota_hash = quota["raw_redacted_sha256"]
    return {
        "status": "SOURCE_PHASE_AUTHORIZED",
        "phase": PHASE,
        "owner_acceptance": True,
        "named_stop_operator": approval["named_stop_operator"],
        "quota_snapshot_sha256": quota_hash,
        "provider_processes_started": 0,
        "launch_ready": True,
        "runner_integration": "PASSED",
    }


def initialize_source_ledger(*, ledger_path: Path, approval_path: Path = SOURCE_APPROVAL,  # noqa: PLR0913
                             seal_path: Path = DEFAULT_AMENDMENT_SEAL, plan: Path = PLAN,
                             packet_seal: Path = PACKET_SEAL, base_seal: Path = BASE_SEAL,
                             amendment_proposal: Path = AMENDMENT_PROPOSAL) -> dict[str, Any]:
    """Create a source-bound V3 ledger once; refuse any ledger with prior call activity."""
    validate_source_approval(
        approval_path=approval_path, seal_path=seal_path, plan=plan, packet_seal=packet_seal,
        base_seal=base_seal, amendment_proposal=amendment_proposal)
    if not _default_campaign_approval():
        raise SourcePhaseError("full-campaign approval must remain default-deny during source-only work")
    _outside_repo(ledger_path, "source-phase ledger")
    _outside_repo(approval_path, "source-phase approval")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "schema": 1, "record_type": "p3_v3_ledger_header",
        "epoch_id": ledger.fresh_id(ledger._historical_ids()),
        "proposal_sha256": sha256(plan), "packet_seal_sha256": sha256(packet_seal),
        "approval_sha256": sha256(approval_path), "codex_epoch_limit_tokens": ledger.CODEX_LIMIT,
        "v2_known_usage_tokens_historical_only": 153_614,
        "q1461_disposition_historical_only": ledger.UNKNOWN_USAGE,
        "dispatch_ready": False, "source_phase_only": True,
        "created_utc": ledger._utc(),
    }
    if ledger_path.exists():
        stored, events = ledger._read(ledger_path)
        if (events or any(stored.get(key) != value for key, value in header.items()
                          if key not in {"epoch_id", "created_utc"} ) or
                not isinstance(stored.get("epoch_id"), str)):
            raise SourcePhaseError("source-phase ledger already contains activity or stale bindings")
        return stored
    data = (json.dumps(header, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(ledger_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        ledger._write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    return header


def main() -> None:
    """Create a default-deny template or run the offline source-phase preflight."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    template = sub.add_parser("approval-template")
    template.add_argument("--output", type=Path, required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--runtime-root", type=Path, required=True)
    preflight.add_argument("--report", type=Path, required=True)
    preflight.add_argument("--approval", type=Path, default=SOURCE_APPROVAL)
    preflight.add_argument("--amendment-seal", type=Path, default=DEFAULT_AMENDMENT_SEAL)
    preflight.add_argument("--base-seal", type=Path, default=BASE_SEAL)
    preflight.add_argument("--plan", type=Path, default=PLAN)
    preflight.add_argument("--packet-seal", type=Path, default=PACKET_SEAL)
    preflight.add_argument("--amendment-proposal", type=Path, default=AMENDMENT_PROPOSAL)
    args = parser.parse_args()
    if args.action == "approval-template":
        output = args.output.resolve()
        if output == REPO or REPO in output.parents:
            parser.error("write the source approval draft outside the repository")
        output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            ledger._write_all(fd, (json.dumps(approval_template(), indent=2, sort_keys=True) + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        print(output)
        return
    report = run_source_preflight(
        runtime_root=args.runtime_root, approval_path=args.approval, seal_path=args.amendment_seal,
        plan=args.plan, packet_seal=args.packet_seal, base_seal=args.base_seal,
        amendment_proposal=args.amendment_proposal, report_path=args.report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
