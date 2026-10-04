#!/usr/bin/env python3
"""Offline, fail-closed validation for a future A22 P3 V2 approval.

This module checks proposal/seal integrity and resource policy fields only. It has
no dispatch, provider, or subprocess path. Owner-acceptance provenance is not
implemented; the boolean in the record is not authenticated. The accepted V2 seal is
deliberately absent until an owner decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE / "RUN_PLAN_V2_PROPOSAL.md"
PACKET_SEAL = HERE / "seal.json"
APPROVAL = HERE / "runs" / "owner-approval-v2.json"
MAX_TOKEN_ENVELOPE = 5_040_000
SCHEMA = 2
SHA256_LENGTH = 64


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
        "selected_resource_option": None,
        "options": {
            "usd25": {
                "route_rates_usd_per_million": None,
                "estimated_total_usd": None,
                "named_operator": None,
                "exploratory_calls_counted": None,
            },
            "token_only": {
                "accepted_pass_envelope_tokens": None,
                "named_operator": None,
                "exploratory_calls_counted": None,
            },
        },
        "preflight_status": "NOT_RUN",
        "dispatch_allowed": False,
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
    required = {"accepted_pass_envelope_tokens", "named_operator", "exploratory_calls_counted"}
    if not isinstance(option, dict) or set(option) != required:
        raise ValueError("token-only option is incomplete")
    envelope = option["accepted_pass_envelope_tokens"]
    if not isinstance(envelope, int) or isinstance(envelope, bool) or not 0 < envelope <= MAX_TOKEN_ENVELOPE:
        raise ValueError("token envelope must be explicit and no larger than 5,040,000")
    if not _operator(option["named_operator"]):
        raise ValueError("named token-stop operator is required")
    if not isinstance(option["exploratory_calls_counted"], bool):
        raise ValueError("whether exploratory calls count must be explicit")


def validate(approval_path: Path = APPROVAL, plan_path: Path = PLAN,
             seal_path: Path | None = None, packet_seal_path: Path = PACKET_SEAL) -> dict:
    """Check record integrity and resource fields; owner provenance is not authenticated."""
    data = json.loads(approval_path.read_text(encoding="utf-8"))
    required = {
        "schema", "record_type", "proposal_sha256", "accepted_v2_seal_sha256",
        "owner_accepted", "owner_acceptance_provenance", "selected_resource_option", "options", "preflight_status",
        "dispatch_allowed",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError("V2 approval schema is malformed (V1 approvals are not accepted)")
    if data["schema"] != SCHEMA or data["record_type"] != "p3_v2_owner_approval":
        raise ValueError("not a V2 approval record")
    if data["proposal_sha256"] != sha_file(plan_path):
        raise ValueError("V2 proposal changed since approval")
    if data["owner_acceptance_provenance"] != "UNIMPLEMENTED":
        raise ValueError("owner acceptance provenance is not implemented")
    if data["owner_accepted"] is not True:
        raise ValueError("V2 approval is unselected")
    if data["dispatch_allowed"] is not False or data["preflight_status"] != "NOT_RUN":
        raise ValueError("this offline policy validator cannot authorize dispatch or assert preflight")
    _validate_seal(seal_path, data["accepted_v2_seal_sha256"], plan_path, packet_seal_path)

    options = data["options"]
    if not isinstance(options, dict) or set(options) != {"usd25", "token_only"}:
        raise ValueError("both V2 resource options must be represented")
    choice = data["selected_resource_option"]
    if choice == "usd25":
        _validate_usd25(options[choice])
    elif choice == "token_only":
        _validate_token_only(options[choice])
    else:
        raise ValueError("a V2 resource option must be selected")
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
    print("V2 record integrity and resource fields validate. Owner provenance and preflight "
          "are unimplemented; this command does not authorize or dispatch.")


if __name__ == "__main__":
    main()
