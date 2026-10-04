#!/usr/bin/env python3
"""Record and validate the owner's acceptance of the frozen A22 P3 plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPROVAL = HERE / "runs" / "owner-approval.json"
PLAN = HERE / "RUN_PLAN.md"
SEAL = HERE / "seal.json"
REQUIRED_UTTERANCE = "запускай"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected() -> dict:
    return {
        "schema": 1,
        "record_type": "owner_acceptance_of_frozen_plan",
        "owner_utterance": REQUIRED_UTTERANCE,
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "accepted_plan_sha256": sha(PLAN),
        "accepted_seal_sha256": sha(SEAL),
        "preflight_status": "NOT_RUN",
        "route_facts_status": "UNVERIFIED",
        "scoring_spend_control": {
            "manual_ceiling_usd": 25,
            "route_prices": "UNKNOWN",
            "estimated_total_usd": "UNKNOWN",
            "named_halt_operator": "UNKNOWN",
            "dispatch_allowed": False,
            "stop_reason": "Unknown pricing or halt operator blocks all scorer dispatches.",
        },
    }


def validate(path: Path = APPROVAL) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    fixed = expected()
    # The accepted seal hash is historical evidence from the acceptance event.
    # A later packet-local tooling update may produce a newer seal while leaving
    # the exact accepted RUN_PLAN bytes unchanged.
    fixed["recorded_utc"] = data.get("recorded_utc")
    fixed["accepted_seal_sha256"] = data.get("accepted_seal_sha256")
    if data != fixed:
        raise ValueError("owner approval is malformed, stale, or contains unverified facts")
    if not isinstance(data["accepted_seal_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", data["accepted_seal_sha256"]):
        raise ValueError("accepted seal hash is malformed")
    if sha(PLAN) != data["accepted_plan_sha256"]:
        raise ValueError("accepted RUN_PLAN has changed since owner approval")
    return data


def record(utterance: str) -> Path:
    if utterance.strip() != REQUIRED_UTTERANCE:
        raise ValueError("record requires the owner's exact explicit utterance: запускай")
    APPROVAL.parent.mkdir(parents=True, exist_ok=True)
    if APPROVAL.exists():
        raise FileExistsError(f"refusing to overwrite {APPROVAL}")
    data = expected()
    APPROVAL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validate()
    return APPROVAL


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    write = sub.add_parser("record")
    write.add_argument("--utterance", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--path", type=Path, default=APPROVAL)
    args = parser.parse_args()
    if args.action == "record":
        print(record(args.utterance))
    else:
        validate(args.path)
        print("owner approval matches the current frozen RUN_PLAN; acceptance seal hash is retained")


if __name__ == "__main__":
    main()
