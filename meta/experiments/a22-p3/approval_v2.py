#!/usr/bin/env python3
"""Offline, fail-closed validation for a future A22 P3 V2 approval.

This module checks proposal/seal integrity, recorded owner transcript evidence, and
resource policy fields. It has no dispatch, provider, or subprocess path. Transcript
evidence is explicitly non-cryptographic; the ledger performs the dispatch gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE / "RUN_PLAN_V2_PROPOSAL.md"
PACKET_SEAL = HERE / "seal.json"
APPROVAL = HERE / "runs" / "owner-approval-v2.json"
CODEX_AGGREGATE_LIMIT = 5_000_000
KNOWN_PRIOR_CODEX_USAGE = 153_614
CODEX_REMAINING_AT_APPROVAL = CODEX_AGGREGATE_LIMIT - KNOWN_PRIOR_CODEX_USAGE
SCORER_READINGS_PER_ROUTE = 120
SCHEMA = 2
SHA256_LENGTH = 64
RETRY_EVIDENCE_POLICIES = {"UNSELECTED", "OBSERVED_NO_RETRY"}


def sha_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    """Hash a file's exact bytes."""
    return sha_bytes(path.read_bytes())


def draft_record() -> dict:
    """Current unselected record. Null seal and resource fields deny dispatch."""
    return {
        "schema": 2,
        "record_type": "p3_v2_owner_approval",
        "proposal_sha256": sha_file(PLAN),
        "accepted_v2_seal_sha256": None,
        "owner_accepted": False,
        "owner_acceptance_provenance": "UNIMPLEMENTED",
        "retry_evidence_policy": "UNSELECTED",
        "acceptance_evidence": None,
        "authorized_phases": [],
        "selected_resource_option": None,
        "options": {
            "usd25": {
                "route_rates_usd_per_million": None,
                "estimated_total_usd": None,
                "named_operator": None,
                "exploratory_calls_counted": None,
            },
            "token_only": {
                "codex_aggregate_limit_tokens": CODEX_AGGREGATE_LIMIT,
                "known_prior_codex_usage_tokens": KNOWN_PRIOR_CODEX_USAGE,
                "remaining_codex_tokens_at_approval": CODEX_REMAINING_AT_APPROVAL,
                "qwen_aggregate_limit_tokens": None,
                "accepted_scorer_readings_per_route": SCORER_READINGS_PER_ROUTE,
                "named_operator": None,
                "exploratory_calls_counted": True,
            },
        },
        "preflight_status": "NOT_RUN",
        "dispatch_allowed": False,
        "test_only_fixture": False,
    }


def _operator(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {"unknown", "tbd", "none"}


def _validate_seal(seal_path: Path | None, seal_hash: object, plan_path: Path,
                   packet_seal_path: Path) -> None:
    if not isinstance(seal_hash, str) or len(seal_hash) != SHA256_LENGTH or any(
            c not in "0123456789abcdef" for c in seal_hash):
        raise ValueError("accepted V2 seal hash is absent or malformed")
    if seal_path is None or sha_file(seal_path) != seal_hash:
        raise ValueError("accepted V2 seal is missing or has changed")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    expected = {
        "schema": 1,
        "record_type": "p3_v2_plan_seal",
        "proposal_sha256": sha_file(plan_path),
        "packet_seal_sha256": sha_file(packet_seal_path),
    }
    if seal != expected:
        raise ValueError("V2 seal does not bind the current proposal and packet seal")


def _validate_usd25(option: object) -> None:
    del option
    raise ValueError("USD 25 option is unsupported until rate and usage accounting is defined and accepted")


def _validate_token_only(option: object) -> None:
    required = {
        "codex_aggregate_limit_tokens", "known_prior_codex_usage_tokens",
        "remaining_codex_tokens_at_approval", "qwen_aggregate_limit_tokens",
        "accepted_scorer_readings_per_route", "named_operator", "exploratory_calls_counted",
    }
    if not isinstance(option, dict) or set(option) != required:
        raise ValueError("token-only option is incomplete")
    expected = {
        "codex_aggregate_limit_tokens": CODEX_AGGREGATE_LIMIT,
        "known_prior_codex_usage_tokens": KNOWN_PRIOR_CODEX_USAGE,
        "remaining_codex_tokens_at_approval": CODEX_REMAINING_AT_APPROVAL,
        "qwen_aggregate_limit_tokens": None,
        "accepted_scorer_readings_per_route": SCORER_READINGS_PER_ROUTE,
    }
    if any(option[key] != value or (isinstance(value, int) and isinstance(option[key], bool))
           for key, value in expected.items()):
        raise ValueError(
            "Codex-only 5,000,000 limit, prior usage, Qwen no-cap policy, and 120 readings per route are fixed"
        )
    if not _operator(option["named_operator"]):
        raise ValueError("named token-stop operator is required")
    if option["exploratory_calls_counted"] is not True:
        raise ValueError("exploratory calls must count toward the Codex aggregate debit")


def _validate_record_shape(data: object, approval_path: Path, plan_path: Path) -> dict:
    """Validate the schema, canonical fixture guard, and proposal binding."""
    required = {
        "schema", "record_type", "proposal_sha256", "accepted_v2_seal_sha256",
        "owner_accepted", "owner_acceptance_provenance", "acceptance_evidence", "authorized_phases",
        "retry_evidence_policy", "selected_resource_option", "options", "preflight_status", "dispatch_allowed",
        "test_only_fixture",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError("V2 approval schema is malformed (V1 approvals are not accepted)")
    if data["schema"] != SCHEMA or data["record_type"] != "p3_v2_owner_approval":
        raise ValueError("not a V2 approval record")
    if not isinstance(data["test_only_fixture"], bool) or \
            (data["test_only_fixture"] and approval_path.resolve() == APPROVAL.resolve()):
        raise ValueError("test-only approval fixture cannot be used as the canonical approval")
    if data["proposal_sha256"] != sha_file(plan_path):
        raise ValueError("V2 proposal changed since approval")
    return data


def _validate_acceptance_evidence(evidence: object, retry_policy: str) -> dict:
    """Validate transcript evidence shape and its retry-policy quote."""
    evidence_fields = {
        "record_type", "accepted_utc", "transcript_ref", "transcript_sha256", "exact_quote",
        "decision_ref", "proposal_sha256", "accepted_v2_seal_sha256",
    }
    if not isinstance(evidence, dict) or set(evidence) != evidence_fields or \
            evidence.get("record_type") != "p3_owner_acceptance_transcript_evidence" or \
            not all(isinstance(evidence.get(key), str) and evidence[key].strip()
                    for key in ("accepted_utc", "transcript_ref", "exact_quote", "decision_ref")) or \
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                         str(evidence.get("accepted_utc"))) is None or \
            not isinstance(evidence.get("transcript_sha256"), str) or \
            len(evidence["transcript_sha256"]) != SHA256_LENGTH or \
            any(char not in "0123456789abcdef" for char in evidence["transcript_sha256"]):
        raise ValueError("owner acceptance transcript evidence is missing or malformed")
    if retry_policy not in evidence["exact_quote"]:
        raise ValueError("owner acceptance quote does not select the retry evidence policy")
    return evidence


def _validate_phases(phases: object) -> None:
    """Require explicit authorization for both dispatch phases."""
    if not isinstance(phases, list) or not all(isinstance(item, str) for item in phases) or \
            len(set(phases)) != len(phases) or set(phases) != {"route_check", "qualification"}:
        raise ValueError("explicit route_check and qualification phase authorization is required")


def _validate_option_selection(options: object, choice: object) -> None:
    """Validate both recorded resource options and the selected supported option."""
    if not isinstance(options, dict) or set(options) != {"usd25", "token_only"}:
        raise ValueError("both V2 resource options must be represented")
    if choice == "usd25":
        _validate_usd25(options[choice])
    elif choice == "token_only":
        _validate_token_only(options[choice])
    else:
        raise ValueError("a V2 resource option must be selected")


def validate(approval_path: Path = APPROVAL, plan_path: Path = PLAN,
             seal_path: Path | None = None, packet_seal_path: Path = PACKET_SEAL) -> dict:
    """Check record integrity and resource fields; owner provenance is not authenticated."""
    data = _validate_record_shape(json.loads(approval_path.read_text(encoding="utf-8")),
                                  approval_path, plan_path)
    if data["owner_accepted"] is not True:
        raise ValueError("V2 approval is unselected")
    retry_policy = data["retry_evidence_policy"]
    if not isinstance(retry_policy, str) or retry_policy not in RETRY_EVIDENCE_POLICIES:
        raise ValueError("retry evidence policy is unknown")
    if retry_policy == "UNSELECTED":
        raise ValueError("retry evidence policy is unselected")
    if data["owner_acceptance_provenance"] != "TRANSCRIPT_EVIDENCE_NONCRYPTOGRAPHIC":
        raise ValueError("owner acceptance transcript provenance is absent or unsupported")
    if data["dispatch_allowed"] is not True or data["preflight_status"] != "PASSED":
        raise ValueError("V2 dispatch authorization and completed preflight are required")
    evidence = _validate_acceptance_evidence(data["acceptance_evidence"], retry_policy)
    _validate_phases(data["authorized_phases"])
    _validate_seal(seal_path, data["accepted_v2_seal_sha256"], plan_path, packet_seal_path)
    if evidence["proposal_sha256"] != sha_file(plan_path) or \
            evidence["accepted_v2_seal_sha256"] != data["accepted_v2_seal_sha256"]:
        raise ValueError("owner acceptance evidence does not bind the current proposal and accepted seal")

    _validate_option_selection(data["options"], data["selected_resource_option"])
    return data


def main() -> None:
    """Validate recorded V2 approval without dispatching any model call."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", type=Path, default=APPROVAL)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--seal", type=Path)
    args = parser.parse_args()
    try:
        validate(args.approval, args.plan, args.seal)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print("V2 approval, transcript evidence, seal, resource policy, and phase fields validate. "
          "This command does not dispatch or authorize a provider call.")


if __name__ == "__main__":
    main()
