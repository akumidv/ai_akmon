#!/usr/bin/env python3
"""Fail-closed V3 dispatch admission boundary.

This module deliberately does not launch a provider. The V3 proposal remains
owner-pending. The V3-native technical-source runner calls ``require_dispatch``
before creating any provider process and uses the V3 reservation/completion API.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import source_phase_v3
import usage_ledger_v3 as ledger


def _source_phase_admission(**options: Any) -> dict[str, Any]:
    """Validate the separate source-only approval and freshly checked report."""
    phase = options["phase"]
    approval = options["approval"]
    seal_path = options["seal_path"]
    plan = options["plan"]
    packet_seal = options["packet_seal"]
    source_preflight_report = options["source_preflight_report"]
    source_amendment_seal = options["source_amendment_seal"]
    source_amendment_proposal = options["source_amendment_proposal"]
    quota_snapshot = options["quota_snapshot"]
    defer_quota_to_reservation = options["defer_quota_to_reservation"]
    if phase != "technical_source" or source_preflight_report is None or source_amendment_seal is None:
        raise ledger.LedgerError("source-phase approval requires its report and amendment seal")
    if quota_snapshot is None and not defer_quota_to_reservation:
        raise ledger.LedgerError("source-phase dispatch requires a fresh quota snapshot")
    try:
        source_report = json.loads(source_preflight_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ledger.LedgerError("source-phase preflight report is unavailable or malformed") from exc
    record = source_phase_v3.validate_source_approval(
        approval_path=approval, seal_path=source_amendment_seal, plan=plan,
        packet_seal=packet_seal, base_seal=seal_path,
        amendment_proposal=source_amendment_proposal)
    source_phase_v3.verify_source_dispatch_gate(
        report=source_report, quota_snapshot=quota_snapshot,
        approval_path=approval, seal_path=source_amendment_seal, plan=plan,
        packet_seal=packet_seal, base_seal=seal_path,
        amendment_proposal=source_amendment_proposal,
        require_quota=not defer_quota_to_reservation)
    return record


def require_dispatch(*, phase: str, approval: Path = ledger.APPROVAL,  # noqa: PLR0913
                     seal_path: Path = ledger.V3_SEAL,
                     plan: Path = ledger.PLAN,
                     packet_seal: Path = ledger.PACKET_SEAL,
                     ledger_path: Path = ledger.LEDGER,
                     source_preflight_report: Path | None = None,
                     source_amendment_seal: Path | None = None,
                     source_amendment_proposal: Path = source_phase_v3.AMENDMENT_PROPOSAL,
                     quota_snapshot: object = None,
                     defer_quota_to_reservation: bool = False) -> dict[str, Any]:
    """Validate every V3 gate and exact ledger binding before a future launch."""
    if phase not in {"technical_source", "route_checks", "qualification", "comparison"}:
        raise ledger.LedgerError("unknown V3 dispatch phase")
    try:
        approval_value = json.loads(approval.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ledger.LedgerError("V3 approval is unavailable or malformed") from exc
    source_phase_approval = (isinstance(approval_value, dict) and
                             approval_value.get("record_type") == "p3_v3_source_phase_owner_approval")
    if source_phase_approval:
        record = _source_phase_admission(
            phase=phase, approval=approval, seal_path=seal_path, plan=plan,
            packet_seal=packet_seal, source_preflight_report=source_preflight_report,
            source_amendment_seal=source_amendment_seal,
            source_amendment_proposal=source_amendment_proposal, quota_snapshot=quota_snapshot,
            defer_quota_to_reservation=defer_quota_to_reservation)
    else:
        record = ledger.validate_v3_approval(
            approval=approval, seal_path=seal_path, plan=plan,
            packet_seal=packet_seal, phase=phase)
    header, events = ledger._read(ledger_path)
    expected = {
        "epoch_id": header.get("epoch_id"),
        "proposal_sha256": ledger.sha256(plan),
        "packet_seal_sha256": ledger.sha256(packet_seal),
        "approval_sha256": ledger.sha256(approval),
    }
    if any(header.get(key) != value for key, value in expected.items()):
        raise ledger.LedgerError("V3 ledger does not bind the current proposal, packet, and approval")
    if header.get("dispatch_ready") is not False:
        raise ledger.LedgerError("V3 ledger dispatch state is malformed")
    if source_phase_approval:
        if header.get("source_phase_only") is not True or events:
            raise ledger.LedgerError("source-only authorization is one-shot; prior ledger activity blocks dispatch")
        return {"status": "AUTHORIZED_SOURCE_PHASE", "phase": phase,
                "epoch_id": header["epoch_id"], "owner_acceptance": True,
                "provider_processes_started": 0, "approval": record}
    # Admission is consumed only by the source-bound V3 runner. This gate does
    # not itself expose or invoke a process launcher.
    return {"status": "AUTHORIZED_GATE_ONLY", "phase": phase,
            "epoch_id": header["epoch_id"], "owner_acceptance": True,
            "provider_processes_started": 0, "approval": record}


def main() -> None:
    """Run the admission-only CLI; never start a provider process."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("technical_source", "route_checks", "qualification", "comparison"))
    args = parser.parse_args()
    try:
        report = require_dispatch(phase=args.phase)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    parser.error("V3 provider dispatch runner is not implemented; no provider process was started")


if __name__ == "__main__":
    main()
