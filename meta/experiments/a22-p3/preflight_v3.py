#!/usr/bin/env python3
"""Run the no-provider static preflight for the proposed A22 P3 V3 epoch."""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import source_v3
import usage_ledger_v3 as ledger

V2_ACCEPTED_READINGS_PER_ROUTE = 120
V2_SCORER_PASS_CEILING = 240


def _ids_in(value: object) -> set[str]:
    found: set[str] = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key.endswith("_id") and isinstance(child, str):
                    found.add(child)
                if isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(item, list):
            stack.extend(item)
    return found


def _historical_ids() -> set[str]:
    """Include JSON and JSONL identities in the immutable V2 history and V3 run area."""
    found = ledger._historical_ids()
    history = ledger.HERE / "runs" / "v2-history"
    for path in [*history.glob("*.jsonl"), *ledger.HERE.joinpath("runs").glob("*v3*.jsonl")]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                found.update(_ids_in(json.loads(line)))
    return found


def _synthetic_policy_checks(runtime: Path) -> dict[str, str]:
    """Exercise the ledger's fail-closed cases using only a disposable fixture ledger."""
    fixture = runtime / "policy-fixture"
    fixture.mkdir(parents=True)
    plan, packet, approval = fixture / "plan.md", fixture / "packet.json", fixture / "approval.json"
    plan.write_text("q1461 remains terminal\n", encoding="utf-8")
    packet.write_text("{}\n", encoding="utf-8")
    approval.write_text(json.dumps({
        "schema": 1, "record_type": "p3_v3_owner_approval", "owner_accepted": False,
        "dispatch_allowed": False, "authorized_phases": [], "preflight_status": "NOT_RUN",
    }), encoding="utf-8")

    def quota(**changes: object) -> dict[str, object]:
        return {"captured_utc": "2030-01-01T00:00:00Z", "source": "synthetic",
                "source_version": "preflight-v1", "freshness_seconds": 0,
                "five_hour_used_percent": 1, "five_hour_reset_utc": "2030-01-01T05:00:00Z",
                "weekly_used_percent": 1, "weekly_reset_utc": "2030-01-08T00:00:00Z",
                "raw_redacted_sha256": "a" * 64, **changes}

    ledger_path = fixture / "ledger.jsonl"
    ledger.initialize(ledger_path, plan=plan, packet_seal=packet, approval=approval)
    call_id = ledger.reserve("codex", "technical", quota_snapshot=quota(), path=ledger_path)
    ledger.complete(call_id, outcome="failed", usage=None, quota_snapshot=quota(),
                    path=ledger_path, failure_code="synthetic_missing_usage")
    if ledger.summary(ledger_path)["unknown_codex_usage"] is not True:
        raise ledger.LedgerError("synthetic missing usage was not retained as unknown")
    try:
        ledger.reserve("codex", "technical", quota_snapshot=quota(), path=ledger_path)
    except ledger.LedgerError:
        pass
    else:
        raise ledger.LedgerError("synthetic unknown usage did not lock subsequent dispatch")

    ceiling_path = fixture / "ceiling-ledger.jsonl"
    ledger.initialize(ceiling_path, plan=plan, packet_seal=packet, approval=approval)
    call_id = ledger.reserve("codex", "technical", quota_snapshot=quota(), path=ceiling_path)
    ledger.complete(call_id, outcome="accepted",
                    usage={"input_tokens": ledger.CODEX_LIMIT, "output_tokens": 0},
                    quota_snapshot=quota(), path=ceiling_path)
    try:
        ledger.reserve("codex", "technical", quota_snapshot=quota(), path=ceiling_path)
    except ledger.LedgerError:
        pass
    else:
        raise ledger.LedgerError("synthetic token-ceiling case did not stop dispatch")

    stop_path = fixture / "stop-ledger.jsonl"
    ledger.initialize(stop_path, plan=plan, packet_seal=packet, approval=approval)
    stopped = quota(five_hour_used_percent=80)
    event = ledger.checkpoint(stopped, "codex", path=stop_path)
    if event.get("dispatch_stopped") is not True:
        raise ledger.LedgerError("synthetic quota stop was not persisted")
    try:
        ledger.reserve("codex", "technical", quota_snapshot=quota(), path=stop_path)
    except ledger.LedgerError:
        pass
    else:
        raise ledger.LedgerError("synthetic stop control did not lock dispatch")
    return {"missing_usage_locks_dispatch": "PASSED",
            "token_ceiling_stops_dispatch": "PASSED",
            "quota_stop_control_locks_dispatch": "PASSED"}


def _q1461_source_rejection(runtime: Path) -> bool:
    """Exercise the resolver's earliest identity gate with a schema-complete fake record."""
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
        source_v3.resolve_technical_source(record, runtime / "missing-exchange.json",
                                           runtime / "missing-case.json", runtime / "missing-arm.txt",
                                           runtime / "missing-rollout.jsonl",
                                           ledger_path=runtime / "missing-ledger.jsonl")
    except source_v3.SourceError as exc:
        return "q1461" in str(exc)
    return False


def _required_evidence(plan: Path, approval: Path, runtime: Path) -> dict[str, dict[str, str]]:
    """Report evidence that can be checked offline; missing implementation stays blocked."""
    plan_text = plan.read_text(encoding="utf-8")
    current_approval = json.loads(approval.read_text(encoding="utf-8"))
    history = ledger.HERE / "runs" / "v2-history"
    old_approval = json.loads((history / "owner-approval-v2.json").read_text(encoding="utf-8"))
    old_seal_path = history / "accepted-v2-seal.json"
    old_seal = json.loads(old_seal_path.read_text(encoding="utf-8"))
    old_plan = history / "RUN_PLAN_V2_PROPOSAL.md"

    v2_manifest_ok = (
        ledger.sha256(old_seal_path) == old_approval.get("accepted_v2_seal_sha256") and
        old_seal.get("proposal_sha256") == old_approval.get("proposal_sha256") and
        old_plan.is_file() and ledger.sha256(old_plan) == old_approval.get("proposal_sha256") and
        old_seal.get("packet_seal_sha256") == ledger.sha256(ledger.PACKET_SEAL)
    )

    repo = ledger.HERE.parents[2].resolve()
    runtime_manifest_path = ledger.HERE / "runs" / "runtime-manifest-v3.json"
    runtime_manifest_ok = False
    runtime_manifest_detail = json.dumps({
        "preflight_runtime_root": str(runtime.resolve()),
        "manifest": f"missing {runtime_manifest_path.name}",
    }, sort_keys=True)
    if runtime_manifest_path.is_file():
        manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
        writable = manifest.get("writable_targets") if isinstance(manifest, dict) else None
        sealed = manifest.get("sealed_source_roots") if isinstance(manifest, dict) else None
        runtime_root = runtime.resolve()
        writable_paths = ([Path(value).resolve() for value in writable]
                          if isinstance(writable, list) and all(isinstance(v, str) for v in writable) else [])
        sealed_paths = ([Path(value).resolve() for value in sealed]
                        if isinstance(sealed, list) and all(isinstance(v, str) for v in sealed) else [])
        runtime_manifest_ok = (
            bool(writable_paths) and bool(sealed_paths) and
            all(path == runtime_root or runtime_root in path.parents for path in writable_paths) and
            all(path == repo for path in sealed_paths)
        )
        runtime_manifest_detail = json.dumps(manifest, sort_keys=True)

    qualification_map = ledger.HERE / "runs" / "qualification-map-v3.json"
    source_records = list(ledger.HERE.glob("runs/*technical-source*.json"))
    map_status = qualification_map.is_file() and bool(source_records)
    map_clean = False
    if qualification_map.is_file() and source_records:
        map_value = json.loads(qualification_map.read_text(encoding="utf-8"))
        source_runs = {json.loads(path.read_text(encoding="utf-8")).get("run_id")
                       for path in source_records}
        map_clean = not bool(source_runs & _ids_in(map_value))

    blind_files = [ledger.HERE / "source_v3.py", ledger.HERE / "scorer_route_check.py"]
    route_v3 = ledger.HERE / "scorer_route_check_v3.py"
    provenance_blinded = route_v3.is_file() and all(path.is_file() for path in blind_files)
    if provenance_blinded:
        route_source = route_v3.read_text(encoding="utf-8")
        provenance_blinded = "source_run_id" not in route_source and "subject_attempt_id" not in route_source

    runner_text = (ledger.HERE / "v3_runner.py").read_text(encoding="utf-8")
    mechanics_complete = all(marker in runner_text for marker in (
        'ARM_C', '"gpt-5.6-luna"', '"gpt-6-astra"', "TURN_INPUT_CAP = 40_000",
        "50_000", "technical control"))

    v2_ledger_source = (ledger.HERE / "usage_ledger_v2.py").read_text(encoding="utf-8")
    v2_scorer_source = (ledger.HERE / "scorer_preflight.py").read_text(encoding="utf-8")
    prior_schedule = old_approval.get("options", {}).get("token_only", {})
    numbers = [
        re.search(r"matrix contains (\d+) A qualification outputs", plan_text),
        re.search(r"up to (\d+) B/C comparison outputs", plan_text),
        re.search(r"at most (\d+) scored outputs", plan_text),
        re.search(r"(\d+) accepted readings per\s+scorer", plan_text),
        re.search(r"and (\d+) accepted readings total", plan_text),
    ]
    schedule_values = [int(match.group(1)) for match in numbers if match]
    schedule_ok = (
        len(schedule_values) == len(numbers) and
        prior_schedule.get("accepted_scorer_readings_per_route") == V2_ACCEPTED_READINGS_PER_ROUTE and
        f"SCORER_READINGS_PER_ROUTE = {V2_ACCEPTED_READINGS_PER_ROUTE}" in v2_ledger_source and
        f"TOTAL_PASS_CAP = {V2_SCORER_PASS_CEILING}" in v2_scorer_source and
        schedule_values[0] + schedule_values[1] == schedule_values[2] and
        schedule_values[3] == schedule_values[2] and
        schedule_values[3] * 2 == schedule_values[4] and
        schedule_values[4] <= V2_SCORER_PASS_CEILING
    )
    schedule_detail = (
        f"V3 {schedule_values[3]}/scorer ({schedule_values[4]} accepted total) leaves "
        f"{V2_SCORER_PASS_CEILING - schedule_values[4]} passes under the {V2_SCORER_PASS_CEILING}-pass cap; "
        f"V2 allowed {V2_ACCEPTED_READINGS_PER_ROUTE}/scorer. "
        f"V3 schedule owner acceptance: {current_approval.get('schedule_accepted') is True}."
        if len(schedule_values) == len(numbers) else "schedule arithmetic could not be parsed"
    )

    route_unscored = (
        "Route checks" in plan_text and "and mechanics controls are unscored" in plan_text and
        route_v3.is_file() and '"scored_p3": False' in route_v3.read_text(encoding="utf-8") and
        '"qualification_data": False' in route_v3.read_text(encoding="utf-8")
    )

    def item(condition: object, detail: str) -> dict[str, str]:
        return {"status": "PASSED" if condition else "BLOCKED", "detail": detail}

    return {
        "V2 artifacts matched an authoritative immutable hash manifest": item(
            v2_manifest_ok, "historical approval, seal, proposal, and current packet seal must match"),
        "writable runtime manifest proves all writable targets and sealed inputs read-only": item(
            runtime_manifest_ok, runtime_manifest_detail),
        "technical source excluded from scored qualification map": item(
            map_status and map_clean, "V3 source and qualification map must both exist and remain disjoint"),
        "source provenance evaluator-only and scorer payload blinded": item(
            provenance_blinded, "a V3 scorer route implementation bound to blinded packets is required"),
        "four subject mechanics controls and their pins/limits verified": item(
            mechanics_complete, "the V3 runner must implement all four A/C by model controls"),
        "96-reading-per-route schedule and 240-pass ceiling reconciled": item(
            schedule_ok, schedule_detail),
        "route checks explicitly unscored": item(
            route_unscored, "a V3 route-check runner must mark checks outside scored data"),
    }


def run_preflight(*, runtime_root: Path, plan: Path = ledger.PLAN,
                  packet_seal: Path = ledger.PACKET_SEAL,
                  approval: Path = ledger.APPROVAL,
                  seal_path: Path = ledger.V3_SEAL) -> dict[str, Any]:
    """Run offline checks and report missing proof as blockers, never as a pass."""
    runtime = runtime_root.resolve()
    repo = ledger.HERE.parents[2].resolve()
    if runtime == repo or repo in runtime.parents or runtime == ledger.HERE or ledger.HERE in runtime.parents:
        raise ledger.LedgerError("preflight runtime must resolve outside the repository and sealed source tree")
    runtime.mkdir(parents=True, exist_ok=True)

    # A local guard makes an accidental process or socket call fail during this
    # execution path instead of relying on a report string to claim none occurred.
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise ledger.LedgerError("static preflight attempted a process or network operation")

    with patch.object(subprocess, "Popen", forbidden), patch.object(subprocess, "run", forbidden), \
            patch.object(socket, "create_connection", forbidden):
        seal = ledger.validate_v3_seal(seal_path, plan=plan, packet_seal=packet_seal)
        base = ledger.static_preflight(plan=plan, packet_seal=packet_seal, approval=approval,
                                       runtime_root=runtime / "runtime")
        synthetic = _synthetic_policy_checks(runtime / "synthetic")
        id_pool = _historical_ids()
        generated: set[str] = set()
        for _ in range(64):
            value = ledger.fresh_id(id_pool | generated)
            if value in id_pool or value in generated:
                raise ledger.LedgerError("synthetic ID collision check failed")
            generated.add(value)
        q1461_rejected = _q1461_source_rejection(runtime)

    blockers: list[str] = []
    if base.get("status") != "PASSED_SYNTHETIC_ONLY":
        blockers.extend(base.get("blockers", []))
    if not q1461_rejected:
        blockers.append("source resolver did not reject q1461")

    required_evidence = _required_evidence(plan, approval, runtime)
    blockers.extend(name for name, result in required_evidence.items()
                    if result["status"] != "PASSED")
    return {
        "status": "PASSED" if not blockers else "BLOCKED_STATIC_EVIDENCE",
        "launch_ready": False,
        "dispatch_allowed": False,
        "network_or_provider_calls": 0,
        "seal_sha256": ledger.sha256(seal_path),
        "bound_sources": sorted(seal["source_sha256"]),
        "base_preflight": base,
        "synthetic_policy_checks": synthetic,
        "historical_id_collision_checks": {"status": "PASSED", "sample_size": len(generated),
                                            "historical_id_count": len(id_pool)},
        "q1461_source_rejection": "PASSED" if q1461_rejected else "FAILED",
        "additional_required_evidence": required_evidence,
        "runtime_manifest": {
            "preflight_runtime_root": str((runtime / "runtime").resolve()),
            "sealed_source_root": str(ledger.HERE.resolve()),
        },
        "blockers": blockers,
    }


def main() -> None:
    """Execute static checks and print their machine-readable result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path,
                        help="isolated writable runtime directory; defaults to a temporary directory")
    args = parser.parse_args()
    if args.runtime_root is not None:
        report = run_preflight(runtime_root=args.runtime_root)
    else:
        with tempfile.TemporaryDirectory(prefix="akmon-p3-v3-preflight-") as temp:
            report = run_preflight(runtime_root=Path(temp) / "runtime")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
