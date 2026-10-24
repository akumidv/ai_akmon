#!/usr/bin/env python3
"""Run one sealed V8 header-optional scorer route call at a time."""

# ruff: noqa: BLE001 C901 D103 PLR0912 PLR0915 PLR2004 S108
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import quota_adapter_v3 as quota  # noqa: E402
import scorer_route_check as scorer  # noqa: E402
import v3_qualification_id_bound as qualification  # noqa: E402
import v3_qwen_5000_format_route as qwen_route  # noqa: E402
import v3_scorer_header_optional as identity  # noqa: E402

REPO = HERE.parents[2].resolve()
SELF = Path(__file__).resolve()
PROPOSAL = HERE / "V3_HEADER_OPTIONAL_SCORER_PROPOSAL.md"
PLAN = HERE / "runs/v3-header-optional-route-plan-v8.json"
SEAL = HERE / "runs/v3-header-optional-route-seal-v8.json"
PREFLIGHT = HERE / "runs/v3-header-optional-route-preflight-v8.json"
LIVE_PREFLIGHT = HERE / "runs/v3-header-optional-route-live-preflight-v8.json"
APPROVAL = HERE / "runs/v3-header-optional-route-approval-v8.json"
RUNTIME = Path("/tmp/a22-p3-v3-header-optional-route-v8-runtime")
V5_RUNTIME = Path("/tmp/a22-p3-v3-header-optional-route-runtime")
V5_RUNTIME_BOUND = Path("/tmp/a22-p3-v3-header-optional-route-runtime")
V5_RUNS = HERE / "runs"
V5_CALL_ID = "gd9c97537bfa14809a06fbe6e44c1f528"
V5_SETTINGS = V5_RUNTIME / V5_CALL_ID / "qwen-settings.json"
LEDGER = RUNTIME / "route-events.jsonl"
FAILED_SEAL = HERE / "runs/v3-id-bound-route-seal-v1.json"
FAILED_APPROVAL = HERE / "runs/v3-id-bound-route-approval-v1.json"
FAILED_PLAN = HERE / "runs/v3-id-bound-route-plan-v1.json"
FAILED_OUTCOME = HERE / "runs/v3-id-bound-qwen-route-outcome-v1.json"
FAILED_LEDGER = Path("/tmp/a22-p3-v3-id-bound-route-runtime/route-events.jsonl")
OLD_ROUTE_RUNTIME = Path("/tmp/a22-p3-v3-id-bound-route-successor-runtime")
PACKETS = {
    "prior_route": {
        "root": Path("/tmp/a22-p3-v3-qualification-successor-runtime/evidence/g225a6ea21aeb6b0df81a151977b43f20"),
        "id": "gf04a4422bf50dd1f",
        "call_id": "g225a6ea21aeb6b0df81a151977b43f20",
        "schedule": HERE / "runs/v3-qualification-successor-schedule-v1.json",
        "seal": HERE / "runs/v3-qualification-successor-seal-v1.json",
    },
    "identity_bound": {
        "root": Path("/tmp/a22-p3-v3-qualification-id-bound-runtime/evidence/gf341bc1d86005586f1c807ad716c5b94"),
        "id": "g9dce84eeb2db2e39",
        "call_id": "gf341bc1d86005586f1c807ad716c5b94",
        "schedule": HERE / "runs/v3-qualification-id-bound-schedule-v1.json",
        "seal": HERE / "runs/v3-qualification-id-bound-seal-v1.json",
    },
}
PREDECESSOR_LEDGER = qualification.PRIOR_LEDGER
ELEMENTS = ["E1", "E2", "E3", "E4"]
OPENING = 636_645
LIMIT = 5_000_000
CODEX_INPUT_CAP = 20_000
CODEX_OUTPUT_CAP = 1_000
QWEN_OUTPUT_CAP = 5_000
PACKET_KEYS = ("prior_route", "identity_bound")
ROUTES = ("qwen", "codex")


class RouteError(ValueError):
    """The sealed route or its evidence failed."""


def sha(path: Path) -> str:
    return qualification.sha(path)


def read(path: Path) -> Any:
    return qualification.read(path)


def write_json(path: Path, value: Any) -> None:
    qualification.write_json(path, value)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_failed_predecessor() -> dict[str, str]:
    """Bind the terminal DNS attempt without reclassifying its usage."""
    plan = read(FAILED_PLAN)
    outcome = read(FAILED_OUTCOME)
    approval = read(FAILED_APPROVAL)
    rows = [json.loads(line) for line in FAILED_LEDGER.read_text().splitlines()]
    if (
        len(rows) != 3
        or rows[0].get("seal_sha256") != sha(FAILED_SEAL)
        or rows[0].get("approval_sha256") != sha(FAILED_APPROVAL)
        or rows[1].get("event") != "reserved"
        or rows[2].get("event") != "completed"
        or rows[1].get("call") != plan["calls"][0]
        or rows[2].get("call") != plan["calls"][0]
        or rows[2].get("status") != "failed"
        or rows[2].get("usage") is not None
        or rows[2].get("outcome_sha256") != sha(FAILED_OUTCOME)
        or outcome.get("status") != "failed"
        or outcome.get("route") != "qwen"
        or outcome.get("usage") is not None
        or outcome.get("retry_authorized") is not False
        or outcome.get("call_id") != plan["calls"][0]["call_id"]
        or approval.get("authorized_phases") != ["id_bound_route_checks"]
        or plan["calls"][1]["route"] != "codex"
    ):
        raise RouteError("terminal DNS predecessor differs")
    return {
        "seal_sha256": sha(FAILED_SEAL),
        "approval_sha256": sha(FAILED_APPROVAL),
        "plan_sha256": sha(FAILED_PLAN),
        "outcome_sha256": sha(FAILED_OUTCOME),
        "ledger_sha256": sha(FAILED_LEDGER),
    }


def check_gateway_tls() -> None:
    """Check DNS and TLS transport only; do not send an API request."""
    gateway, _, _, _ = qwen_effective_settings()
    parsed = urlsplit(gateway)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RouteError("Qwen gateway differs")
    try:
        with (
            socket.create_connection((parsed.hostname, parsed.port or 443), timeout=8) as connection,
            ssl.create_default_context().wrap_socket(connection, server_hostname=parsed.hostname),
        ):
            pass
    except (OSError, ssl.SSLError) as exc:
        raise RouteError("Qwen gateway DNS/TLS probe failed") from exc


def prompt_and_packet(packet_key: str) -> tuple[bytes, bytes]:
    prompt = qualification.packet.PROMPT.read_bytes()
    expected = (
        qualification.packet.sealed_bytes("scoring/scorer-prompt.txt").split(
            b"Output tab-separated rows with exactly:\n", 1
        )[0]
        + qualification.packet.FORMAT_INSTRUCTIONS
    )
    if qualification.packet.PROMPT.is_symlink() or prompt != expected:
        raise RouteError("new prompt differs from frozen rubric")
    source = PACKETS[packet_key]
    packet_root = source["root"]
    predecessor = read(packet_root / "prepared.json")
    old_schedule = read(source["schedule"])
    old_row = next(
        (row for row in old_schedule["cells"] if row["run_id"] == predecessor.get("call", {}).get("run_id")),
        None,
    )
    packet_path = packet_root / "packet.md"
    packet = packet_path.read_bytes()
    if (
        packet_path.is_symlink()
        or old_row is None
        or old_row["packet_id"] != source["id"]
        or old_row["element_ids"] != ELEMENTS
        or predecessor.get("packet_sha256") != sha_bytes(packet)
        or predecessor.get("call", {}).get("call_id") != source["call_id"]
        or source["id"].encode() not in packet
    ):
        raise RouteError("terminal predecessor packet differs")
    return prompt, packet


def plan() -> dict[str, Any]:
    value = read(PLAN)
    historical = qualification.schedule.prior_ids() | set(read(qualification.schedule.OLD_MAP))
    historical.update(call["call_id"] for call in read(FAILED_PLAN)["calls"])
    for path in qualification.schedule.PRIOR_SCHEDULES:
        previous = read(path)
        for row in previous["cells"]:
            historical.update((row["run_id"], row["subject_attempt_id"], row["packet_id"]))
            historical.update(row["subject_call_ids"])
            historical.update(item["call_id"] for item in row["scorers"])
    historical.update(
        item
        for row in read(qualification.schedule.SCHEDULE)["cells"]
        for item in (row["run_id"], row["subject_attempt_id"], row["packet_id"], *row["subject_call_ids"])
    )
    historical.update(
        item["call_id"] for row in read(qualification.schedule.SCHEDULE)["cells"] for item in row["scorers"]
    )
    calls = value.get("calls")
    if (
        value.get("record_type") != "p3_v3_header_optional_route_v8_plan"
        or value.get("packet_sha256") != {key: sha(PACKETS[key]["root"] / "packet.md") for key in PACKET_KEYS}
        or value.get("prompt_sha256") != sha(qualification.packet.PROMPT)
        or not isinstance(calls, list)
        or len(calls) != 4
        or [(row.get("packet_key"), row.get("route")) for row in calls]
        != [(key, route) for key in PACKET_KEYS for route in ROUTES]
        or len({row.get("call_id") for row in calls}) != 4
        or any(
            not isinstance(row.get("call_id"), str)
            or len(row["call_id"]) != 33
            or not row["call_id"].startswith("g")
            or any(character not in "0123456789abcdef" for character in row["call_id"][1:])
            or row["call_id"] in historical
            or row["call_id"]
            in {
                item["call_id"]
                for source in PACKETS.values()
                for item in [read(source["root"] / "prepared.json")["call"]]
            }
            for row in calls
        )
    ):
        raise RouteError("frozen route plan differs")
    return value


def _packet_for(call: dict[str, Any]) -> tuple[bytes, bytes, str, list[str]]:
    key = call.get("packet_key")
    if key not in PACKETS:
        raise RouteError("route packet key differs")
    prompt, packet = prompt_and_packet(key)
    return prompt, packet, PACKETS[key]["id"], ELEMENTS


def _normalized_from_canonical(canonical: str, packet_id: str) -> str:
    lines = canonical.splitlines()
    if not lines or lines[0] != identity.CANONICAL_HEADER:
        raise RouteError("canonical header differs")
    prefix = packet_id + "\t"
    raw = [identity.RAW_HEADER]
    for line in lines[1:]:
        if not line.startswith(prefix):
            raise RouteError("canonical packet binding differs")
        raw.append(line[len(prefix) :])
    return "\n".join(raw) + "\n"


def _normalized_bytes_match(normalized: bytes, canonical: str, packet_id: str) -> bool:
    """Require persisted normalization to equal the canonical-derived bytes."""
    return normalized == _normalized_from_canonical(canonical, packet_id).encode()


def _canonical_json_sha(value: Any) -> str:
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def _allowed_qwen_cli_mutation(base: dict[str, Any], after: dict[str, Any]) -> bool:
    """Permit only the CLI's observed `$version: 4` addition."""
    if not isinstance(base, dict) or not isinstance(after, dict):
        return False
    version = after.get("$version")
    unchanged = {key: value for key, value in after.items() if key != "$version"}
    return type(version) is int and version == 4 and unchanged == base


def _v5_source_and_plan_match(seal: dict[str, Any], plan_path: Path) -> bool:
    current_sources = {path.name: sha(path) for path in sorted(HERE.glob("*.py"))}
    regression = sha(HERE.parents[1] / "tests/test_a22_p3_v3_header_optional_route.py")
    packet_hashes = {key: sha(PACKETS[key]["root"] / "packet.md") for key in PACKET_KEYS}
    qwen_executable = Path(shutil.which("qwen") or "/missing/qwen").resolve(strict=True)
    return (
        seal.get("source_sha256") == current_sources
        and seal.get("regression_sha256") == regression
        and seal.get("plan_sha256") == sha(plan_path)
        and seal.get("proposal_sha256") == sha(PROPOSAL)
        and seal.get("packet_sha256") == packet_hashes
        and seal.get("prompt_sha256") == sha(qualification.packet.PROMPT)
        and seal.get("packet_ids") == {key: PACKETS[key]["id"] for key in PACKET_KEYS}
        and seal.get("element_ids") == ELEMENTS
        and seal.get("scope") == ["header_optional_unscored_route_checks"]
        and seal.get("provider_calls_started") == 0
        and seal.get("retry_evidence_policy") == "OBSERVED_NO_RETRY"
        and seal.get("opening_codex_tokens") == OPENING
        and seal.get("codex_limit_tokens") == LIMIT
        and seal.get("codex_five_hour_stop_percent") == 80
        and seal.get("codex_weekly_stop_percent") == 90
        and seal.get("codex_cli_version") == "codex-cli 0.162.1"
        and seal.get("codex_model") == "gpt-6-astra"
        and seal.get("codex_effort") == "medium"
        and seal.get("codex_executable_sha256") == sha(qualification.CODEX)
        and seal.get("account_id_sha256") == qualification.ACCOUNT_ID_SHA
        and seal.get("qwen_cli_version") == "0.24.7"
        and seal.get("qwen_model") == "qwen3.8-27b"
        and seal.get("qwen_thinking") == "provider default retained"
        and seal.get("qwen_output_setting") == QWEN_OUTPUT_CAP
        and seal.get("qwen_executable_sha256") == sha(qwen_executable)
        and seal.get("runtime_root") == str(V5_RUNTIME_BOUND)
    )


def _v5_approval_matches(approval: dict[str, Any], seal_path: Path, preflight_path: Path) -> bool:
    return (
        approval.get("operational_seal_sha256") == sha(seal_path)
        and approval.get("owner_accepted") is True
        and approval.get("dispatch_allowed") is True
        and approval.get("authorized_phases") == ["header_optional_unscored_route_checks"]
        and approval.get("named_stop_operator") == "owner (current chat session)"
        and approval.get("acceptance_basis")
        == "owner confirmed launch of the prospective two-packet header-optional route in this chat"
        and approval.get("preflight_sha256") == sha(preflight_path)
    )


def _v5_terminal_binding() -> dict[str, str]:
    root = V5_RUNTIME / V5_CALL_ID
    settings_path = root / "qwen-settings.json"
    paths = {
        "seal": V5_RUNS / "v3-header-optional-route-seal-v5.json",
        "approval": V5_RUNS / "v3-header-optional-route-approval-v5.json",
        "preflight": V5_RUNS / "v3-header-optional-route-live-preflight-v5.json",
        "plan": V5_RUNS / "v3-header-optional-route-plan-v5.json",
        "ledger": V5_RUNTIME / "route-events.jsonl",
        "outcome": V5_RUNTIME / V5_CALL_ID / "outcome.json",
        "settings_after_cli": settings_path,
    }
    if any(not path.is_file() or path.is_symlink() for path in paths.values()):
        raise RouteError("V5 terminal evidence is incomplete")
    seal, approval, preflight, plan = (read(paths[key]) for key in ("seal", "approval", "preflight", "plan"))
    outcome = read(paths["outcome"])
    prepared = read(root / "prepared.json")
    packet_id = PACKETS["prior_route"]["id"]
    prompt, packet = prompt_and_packet("prior_route")
    request = scorer.make_request(prompt, packet)
    settings = read(root / "qwen-settings.json")
    current_gateway, expected_settings, current_meta, current_effective = qwen_effective_settings()
    effective = seal.get("qwen_effective_settings", {})
    expected_events = [json.loads(line) for line in paths["ledger"].read_text().splitlines()]
    events = read(root / "events.json")
    raw_bytes = (root / "reply.raw.tsv").read_bytes()
    normalized_bytes = (root / "reply.normalized.tsv").read_bytes()
    canonical_bytes = (root / "reply.tsv").read_bytes()
    canonical, normalization_kind = identity.canonicalize(raw_bytes.decode("utf-8"), packet_id, ELEMENTS)
    usage_record = read(root / "usage.json")
    evidence_names = (
        "prepared.json",
        "stdout.raw",
        "stderr.raw",
        "events.json",
        "reply.raw.tsv",
        "reply.normalized.tsv",
        "reply.tsv",
        "usage.json",
        "qwen-settings.json",
    )
    expected_evidence = {name: sha(root / name) for name in evidence_names}
    sealed_base_hash = _canonical_json_sha(expected_settings)
    plan_calls = plan.get("calls", [])
    if (
        seal.get("record_type") != "p3_v3_header_optional_route_seal"
        or seal.get("status") != "offline_candidate_pending_owner_acceptance"
        or not _v5_source_and_plan_match(seal, paths["plan"])
        or seal.get("qwen_effective_settings") != current_effective
        or effective != current_effective
        or seal.get("qwen_gateway_sha256") != sha_bytes(current_gateway.encode())
        or seal.get("qwen_effective_settings", {}).get("meta_sha256") != _canonical_json_sha(current_meta)
        or effective.get("overlay_sha256") != sealed_base_hash
        or not _allowed_qwen_cli_mutation(expected_settings, settings)
        or approval.get("record_type") != "p3_v3_header_optional_route_approval"
        or not _v5_approval_matches(approval, paths["seal"], paths["preflight"])
        or preflight.get("status") != "PASSED_HEADER_OPTIONAL_ROUTE_PREFLIGHT"
        or preflight.get("operational_seal_sha256") != sha(paths["seal"])
        or preflight.get("provider_calls") != 0
        or preflight.get("dispatch_allowed") is not False
        or preflight.get("planned_calls") != 4
        or preflight.get("opening_codex_tokens") != OPENING
        or preflight.get("gateway_probe") != "verified_tls_handshake_without_api_request"
        or plan.get("record_type") != "p3_v3_header_optional_route_plan"
        or [(row.get("packet_key"), row.get("route")) for row in plan_calls]
        != [(key, model) for key in PACKET_KEYS for model in ROUTES]
        or len(plan_calls) != 4
        or len({row.get("call_id") for row in plan_calls}) != 4
        or plan_calls[0] != {"call_id": V5_CALL_ID, "packet_key": "prior_route", "route": "qwen"}
        or plan.get("packet_sha256") != seal.get("packet_sha256")
        or plan.get("prompt_sha256") != seal.get("prompt_sha256")
        or plan.get("prompt_sha256") != sha_bytes(prompt)
        or plan.get("packet_sha256") != {key: sha(PACKETS[key]["root"] / "packet.md") for key in PACKET_KEYS}
        or len(expected_events) != 3
        or expected_events[0]
        != {
            "record_type": "p3_v3_header_optional_route_ledger",
            "seal_sha256": sha(paths["seal"]),
            "approval_sha256": sha(paths["approval"]),
            "opening_codex_tokens": OPENING,
        }
        or expected_events[1].get("event") != "reserved"
        or expected_events[1].get("call") != plan["calls"][0]
        or expected_events[1].get("request_sha256") != sha_bytes(request)
        or expected_events[2].get("event") != "completed"
        or expected_events[2].get("call") != plan["calls"][0]
        or expected_events[2].get("status") != "passed_unscored"
        or expected_events[2].get("usage") != {"input_tokens": 12_779, "output_tokens": 850}
        or expected_events[2].get("outcome_sha256") != sha(paths["outcome"])
        or outcome.get("call_id") != V5_CALL_ID
        or outcome.get("route") != "qwen"
        or outcome.get("status") != "passed_unscored"
        or outcome.get("seal_sha256") != sha(paths["seal"])
        or outcome.get("request_sha256") != sha_bytes(request)
        or outcome.get("packet_sha256") != sha_bytes(packet)
        or outcome.get("prompt_sha256") != sha_bytes(prompt)
        or outcome.get("scored_p3") is not False
        or outcome.get("qualification_data") is not False
        or outcome.get("retry_authorized") is not False
        or outcome.get("usage") != expected_events[2].get("usage")
        or outcome.get("evidence_sha256") != expected_evidence
        or outcome.get("raw_reply_sha256") != sha_bytes(raw_bytes)
        or outcome.get("canonical_reply_sha256") != sha_bytes(canonical_bytes)
        or outcome.get("normalized_reply_sha256") != sha_bytes(normalized_bytes)
        or outcome.get("normalization_kind") != normalization_kind
        or canonical_bytes.decode("utf-8") != canonical
        or normalized_bytes != _normalized_from_canonical(canonical, packet_id).encode()
        or prepared.get("call") != plan["calls"][0]
        or prepared.get("seal_sha256") != sha(paths["seal"])
        or prepared.get("request_sha256") != sha_bytes(request)
        or prepared.get("packet_sha256") != sha_bytes(packet)
        or prepared.get("prompt_sha256") != sha_bytes(prompt)
        or prepared.get("qwen_effective_settings") != effective
        or _canonical_json_sha(prepared.get("qwen_settings")) != effective.get("meta_sha256")
        or prepared.get("qwen_dispatch_environment") != outcome.get("qwen_dispatch_environment")
        or outcome.get("qwen_dispatch_environment")
        != {
            **effective.get("dispatch_environment", {}),
            "QWEN_CODE_SYSTEM_SETTINGS_PATH": str(root / "qwen-settings.json"),
        }
        or outcome.get("session_id") != prepared.get("session_id")
        or usage_record.get("session_id") != outcome.get("session_id")
        or usage_record.get("project") != str(root / "scratch")
        or usage_record.get("requests") != 1
        or usage_record.get("tool_calls") != 0
        or usage_record.get("model_id") != "qwen3.8-27b"
        or usage_record.get("input_tokens") != outcome.get("usage", {}).get("input_tokens")
        or usage_record.get("output_tokens") != outcome.get("usage", {}).get("output_tokens")
        or scorer.parse_jsonl((root / "stdout.raw").read_bytes()) != events
        or scorer.event_session_ids(events) != {outcome.get("session_id")}
        or scorer.tool_markers(events)
        or scorer.cli_retry_error_markers(events, (root / "stderr.raw").read_bytes())
        or outcome.get("tool_markers") != []
        or outcome.get("visible_retry_error_markers") != []
    ):
        raise RouteError("V5 terminal evidence linkage differs")
    return {
        **{name: sha(path) for name, path in paths.items()},
        **{f"call/{name}": sha(root / name) for name in (*evidence_names, "outcome.json")},
    }


def qwen_effective_settings() -> tuple[str, dict[str, Any], dict[str, Any], dict[str, str]]:
    """Return Qwen settings and stable hashes of the effective dispatch inputs."""
    gateway, overlay, meta = qwen_route.qwen_settings()
    binding = {
        "gateway_sha256": sha_bytes(gateway.encode()),
        "overlay_sha256": _canonical_json_sha(overlay),
        "meta_sha256": _canonical_json_sha(meta),
        "dispatch_environment": {
            "QWEN_CODE_SYSTEM_SETTINGS_PATH": "<call-root>/qwen-settings.json",
            "QWEN_CODE_MAX_OUTPUT_TOKENS": str(QWEN_OUTPUT_CAP),
            "QWEN_CODE_UNATTENDED_RETRY": "0",
        },
    }
    binding["effective_sha256"] = _canonical_json_sha(binding)
    return gateway, overlay, meta, binding


def verify_qwen_effective_settings(expected: dict[str, str]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Fail closed if the current provider configuration differs from the seal."""
    gateway, overlay, meta, actual = qwen_effective_settings()
    if actual != expected:
        raise RouteError("effective Qwen settings differ from seal")
    return gateway, overlay, meta


def codex_reserved_upper_bound(prior_tokens: int) -> int:
    """Include observed prior Codex use and this call's full reservation."""
    if prior_tokens < OPENING:
        raise RouteError("Codex opening usage is malformed")
    total = prior_tokens + CODEX_INPUT_CAP + CODEX_OUTPUT_CAP
    if total > LIMIT:
        raise RouteError("Codex aggregate ceiling blocks route")
    return total


def seal_body() -> dict[str, Any]:
    [prompt_and_packet(key) for key in PACKET_KEYS]
    plan()
    failed_predecessor = check_failed_predecessor()
    predecessor_rows = [json.loads(line) for line in PREDECESSOR_LEDGER.read_text().splitlines() if line.strip()]
    if (
        len(predecessor_rows) != 63
        or predecessor_rows[-1].get("event") != "completed"
        or predecessor_rows[-1].get("status") != "failed"
        or predecessor_rows[-1].get("call", {}).get("call_id") != PACKETS["prior_route"]["call_id"]
        or predecessor_rows[-1].get("usage") != {"input_tokens": 12_779, "output_tokens": 558}
    ):
        raise RouteError("terminal qualification predecessor differs")
    second = PACKETS["identity_bound"]
    second_call = read(second["root"] / "prepared.json")["call"]
    second_failure = read(second["root"] / "failure.json")
    second_schedule = read(second["schedule"])
    second_row = next(row for row in second_schedule["cells"] if row["run_id"] == second_call["run_id"])
    if (
        second_call["call_id"] != second["call_id"]
        or second_row["packet_id"] != second["id"]
        or second_failure.get("status") != "terminal"
        or second_failure.get("retry_authorized") is not False
    ):
        raise RouteError("second terminal scorer predecessor differs")
    gateway, overlay, meta, qwen_binding = qwen_effective_settings()
    if (
        meta.get("thinking_override") != "omitted; provider default retained"
        or overlay["modelProviders"]["openai"][0]["generationConfig"]["maxRetries"] != 0
        or overlay["modelProviders"]["openai"][0]["generationConfig"]["samplingParams"]["max_tokens"] != 5000
    ):
        raise RouteError("Qwen settings differ")
    v5_terminal = _v5_terminal_binding()
    return {
        "schema": 1,
        "record_type": "p3_v3_header_optional_route_v8_seal",
        "status": "offline_candidate_pending_owner_acceptance",
        "scope": ["header_optional_unscored_route_checks"],
        "provider_calls_started": 0,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "failed_predecessor_sha256": failed_predecessor,
        "terminal_v5_route_evidence_sha256": v5_terminal,
        "terminal_v5_qwen_cli_mutation": "top-level integer $version=4 appended; bound by settings_after_cli SHA-256",
        "terminal_failure_evidence_sha256": {key: sha(PACKETS[key]["root"] / "failure.json") for key in PACKET_KEYS},
        "terminal_packet_prepared_sha256": {key: sha(PACKETS[key]["root"] / "prepared.json") for key in PACKET_KEYS},
        "terminal_packet_sha256": {key: sha(PACKETS[key]["root"] / "packet.md") for key in PACKET_KEYS},
        "terminal_schedule_sha256": {key: sha(PACKETS[key]["schedule"]) for key in PACKET_KEYS},
        "terminal_seal_sha256": {key: sha(PACKETS[key]["seal"]) for key in PACKET_KEYS},
        "gateway_preflight": "DNS and verified TLS handshake only; no API request",
        "opening_codex_tokens": OPENING,
        "codex_limit_tokens": LIMIT,
        "codex_five_hour_stop_percent": 80,
        "codex_weekly_stop_percent": 90,
        "codex_cli_version": "codex-cli 0.162.1",
        "codex_model": "gpt-6-astra",
        "codex_effort": "medium",
        "codex_executable_sha256": sha(qualification.CODEX),
        "account_id_sha256": qualification.ACCOUNT_ID_SHA,
        "qwen_cli_version": "0.24.7",
        "qwen_model": "qwen3.8-27b",
        "qwen_thinking": "provider default retained",
        "qwen_output_setting": 5000,
        "qwen_executable_sha256": sha(Path(shutil.which("qwen") or "/missing/qwen").resolve(strict=True)),
        "qwen_gateway_sha256": sha_bytes(gateway.encode()),
        "qwen_effective_settings": qwen_binding,
        "packet_ids": {key: PACKETS[key]["id"] for key in PACKET_KEYS},
        "element_ids": ELEMENTS,
        "packet_sha256": {key: sha(PACKETS[key]["root"] / "packet.md") for key in PACKET_KEYS},
        "prompt_sha256": sha(qualification.packet.PROMPT),
        "proposal_sha256": sha(PROPOSAL),
        "plan_sha256": sha(PLAN),
        "predecessor_seal_sha256": sha(HERE / "runs/v3-qualification-successor-seal-v1.json"),
        "predecessor_schedule_sha256": sha(HERE / "runs/v3-qualification-successor-schedule-v1.json"),
        "predecessor_ledger_sha256": sha(PREDECESSOR_LEDGER),
        "predecessor_failure_sha256": sha(PACKETS["prior_route"]["root"] / "failure.json"),
        "terminal_failed_call_evidence_sha256": {
            "identity_bound_failure": sha(PACKETS["identity_bound"]["root"] / "failure.json"),
            "identity_bound_prepared": sha(PACKETS["identity_bound"]["root"] / "prepared.json"),
            "identity_bound_raw_reply": sha(PACKETS["identity_bound"]["root"] / "reply.raw.tsv"),
            "identity_bound_stdout": sha(PACKETS["identity_bound"]["root"] / "stdout.raw"),
            "identity_bound_stderr": sha(PACKETS["identity_bound"]["root"] / "stderr.raw"),
            "identity_bound_events": sha(PACKETS["identity_bound"]["root"] / "events.json"),
        },
        "old_m155_seal_sha256": sha(HERE / "runs/v3-qualification-id-bound-seal-v1.json"),
        "old_m155_schedule_sha256": sha(HERE / "runs/v3-qualification-id-bound-schedule-v1.json"),
        "old_m155_call_id": PACKETS["identity_bound"]["call_id"],
        "old_route_evidence_sha256": {
            "ledger": sha(OLD_ROUTE_RUNTIME / "route-events.jsonl"),
            **{
                f"{call_id}/{name}": sha(OLD_ROUTE_RUNTIME / call_id / name)
                for call_id, names in {
                    "gf6739f2c871a4c6cae910f8a6a37f0ed": (
                        "prepared.json",
                        "outcome.json",
                        "reply.raw.tsv",
                        "reply.tsv",
                        "events.json",
                        "stdout.raw",
                        "stderr.raw",
                        "usage.json",
                        "qwen-settings.json",
                    ),
                    "ga6d86d07826e49898cb8bf11aff1c892": (
                        "prepared.json",
                        "outcome.json",
                        "reply.raw.tsv",
                        "reply.tsv",
                        "events.json",
                        "stdout.raw",
                        "stderr.raw",
                        "quota-before.json",
                        "rollout.jsonl",
                    ),
                }.items()
                for name in names
            },
        },
        "source_sha256": {path.name: sha(path) for path in sorted(HERE.glob("*.py"))},
        "successor_source_sha256": sha(SELF),
        "regression_sha256": sha(HERE.parents[1] / "tests/test_a22_p3_v3_header_optional_route_v8.py"),
        "runtime_root": str(RUNTIME),
    }


def verify_seal() -> None:
    if read(SEAL) != seal_body():
        raise RouteError("route seal differs")


def approval_template() -> dict[str, Any]:
    return {
        "schema": 1,
        "record_type": "p3_v3_header_optional_route_v8_approval",
        "operational_seal_sha256": sha(SEAL),
        "preflight_sha256": sha(LIVE_PREFLIGHT if LIVE_PREFLIGHT.exists() else PREFLIGHT),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
        "acceptance_basis": None,
    }


def verify_approval(*, dispatch: bool) -> None:
    actual = read(APPROVAL)
    template = approval_template()
    if not dispatch and actual == template:
        return
    expected = {
        **template,
        "owner_accepted": True,
        "dispatch_allowed": True,
        "authorized_phases": ["header_optional_unscored_route_checks"],
        "named_stop_operator": "owner (current chat session)",
        "acceptance_basis": "owner confirmed launch of the prospective two-packet header-optional route in this chat",
    }
    if actual != expected:
        raise RouteError("exact route-check approval is absent")


def preflight() -> dict[str, Any]:
    verify_seal()
    verify_qwen_effective_settings(read(SEAL)["qwen_effective_settings"])
    if RUNTIME.exists() or RUNTIME.is_symlink() or REPO in RUNTIME.resolve().parents:
        raise RouteError("route runtime is used or inside repository")
    if not os.environ.get("LITE_LLM_AUTH_TOKEN"):
        raise RouteError("Qwen credential unavailable")
    if not qualification.AUTH.is_file() or qualification.AUTH.is_symlink():
        raise RouteError("Codex auth source unavailable")
    if stat.S_IMODE(qualification.AUTH.stat().st_mode) & 0o077:
        raise RouteError("Codex auth source is not private")
    cv = subprocess.run(
        [str(qualification.CODEX), "--version"], capture_output=True, text=True, timeout=10, check=False
    )
    qwen = shutil.which("qwen")
    if not qwen:
        raise RouteError("Qwen executable unavailable")
    qv = subprocess.run([qwen, "--version"], capture_output=True, text=True, timeout=10, check=False)
    if (
        cv.returncode
        or cv.stdout.strip() != "codex-cli 0.162.1"
        or qv.returncode
        or not scorer._version_matches(qv.stdout, "0.24.7")
    ):
        raise RouteError("pinned CLI version differs")
    check_gateway_tls()
    return {
        "status": "PASSED_HEADER_OPTIONAL_ROUTE_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "provider_calls": 0,
        "dispatch_allowed": False,
        "planned_calls": 4,
        "opening_codex_tokens": OPENING,
        "gateway_probe": "verified_tls_handshake_without_api_request",
    }


def _header() -> dict[str, Any]:
    return {
        "record_type": "p3_v3_header_optional_route_v8_ledger",
        "seal_sha256": sha(SEAL),
        "approval_sha256": sha(APPROVAL),
        "opening_codex_tokens": OPENING,
    }


def _events() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    rows = [json.loads(line) for line in LEDGER.read_text().splitlines()]
    if not rows or rows[0] != _header():
        raise RouteError("route ledger header differs")
    if len(rows) > 9 or len(rows[1:]) % 2:
        raise RouteError("unresolved or excess route reservation")
    codex_total = OPENING
    for index, call in enumerate(plan()["calls"][: (len(rows) - 1) // 2]):
        reserved, completed = rows[1 + 2 * index : 3 + 2 * index]
        if (
            reserved.get("event") != "reserved"
            or completed.get("event") != "completed"
            or reserved.get("call") != call
            or completed.get("call") != call
        ):
            raise RouteError("route ledger order differs")
        if completed.get("status") != "passed_unscored":
            raise RouteError("terminal route failure blocks next call")
        root = RUNTIME / call["call_id"]
        outcome = read(root / "outcome.json")
        prompt, packet, packet_id, elements = _packet_for(call)
        request = scorer.make_request(prompt, packet)
        prepared = read(root / "prepared.json")
        if any((root / name).is_symlink() for name in ("reply.raw.tsv", "reply.normalized.tsv", "reply.tsv")):
            raise RouteError("route reply evidence is linked")
        raw = (root / "reply.raw.tsv").read_text(encoding="utf-8")
        canonical = (root / "reply.tsv").read_text(encoding="utf-8")
        expected_evidence = {
            name: sha(root / name)
            for name in (
                "prepared.json",
                "stdout.raw",
                "stderr.raw",
                "events.json",
                "reply.raw.tsv",
                "reply.normalized.tsv",
                "reply.tsv",
                *(
                    ("usage.json", "qwen-settings.json", "qwen-settings-sealed.json", "qwen-settings-after-cli.json")
                    if call["route"] == "qwen"
                    else ("quota-before.json", "rollout.jsonl")
                ),
            )
        }
        if (
            reserved.get("request_sha256") != sha_bytes(request)
            or sha(root / "outcome.json") != completed.get("outcome_sha256")
            or outcome.get("call_id") != call["call_id"]
            or outcome.get("route") != call["route"]
            or outcome.get("status") != "passed_unscored"
            or outcome.get("scored_p3") is not False
            or outcome.get("qualification_data") is not False
            or outcome.get("retry_authorized") is not False
            or outcome.get("failure_class") is not None
            or outcome.get("seal_sha256") != sha(SEAL)
            or outcome.get("usage") != completed.get("usage")
            or outcome.get("evidence_sha256") != expected_evidence
            or prepared.get("call") != call
            or prepared.get("seal_sha256") != sha(SEAL)
            or prepared.get("request_sha256") != sha_bytes(request)
            or prepared.get("packet_sha256") != sha_bytes(packet)
            or prepared.get("prompt_sha256") != sha_bytes(prompt)
            or outcome.get("raw_reply_sha256") != sha_bytes(raw.encode())
            or outcome.get("normalized_reply_sha256") != sha_bytes((root / "reply.normalized.tsv").read_bytes())
            or outcome.get("canonical_reply_sha256") != sha_bytes(canonical.encode())
            or outcome.get("normalization_kind") not in {"exact_header", "inserted_header"}
            or identity.canonicalize(raw, packet_id, elements) != (canonical, outcome.get("normalization_kind"))
            or identity.canonicalize((root / "reply.normalized.tsv").read_text(), packet_id, elements)[0] != canonical
            or not _normalized_bytes_match((root / "reply.normalized.tsv").read_bytes(), canonical, packet_id)
        ):
            raise RouteError("route outcome differs from ledger")
        scorer.validate_tsv(canonical, packet_id, elements)
        events = read(root / "events.json")
        if scorer.parse_jsonl((root / "stdout.raw").read_bytes()) != events:
            raise RouteError("route event capture differs")
        stderr = (root / "stderr.raw").read_bytes()
        if scorer.tool_markers(events) or scorer.cli_retry_error_markers(events, stderr):
            raise RouteError("route tool or visible retry evidence differs")
        if outcome.get("tool_markers") != [] or outcome.get("visible_retry_error_markers") != []:
            raise RouteError("route marker outcome differs")
        if call["route"] == "qwen":
            sealed_qwen = read(SEAL)["qwen_effective_settings"]
            expected_dispatch_environment = {
                **sealed_qwen["dispatch_environment"],
                "QWEN_CODE_SYSTEM_SETTINGS_PATH": str(root / "qwen-settings.json"),
            }
            if (
                prepared.get("qwen_effective_settings") != sealed_qwen
                or outcome.get("qwen_effective_settings") != sealed_qwen
                or prepared.get("qwen_dispatch_environment") != expected_dispatch_environment
                or outcome.get("qwen_dispatch_environment") != expected_dispatch_environment
                or _canonical_json_sha(read(root / "qwen-settings-sealed.json")) != sealed_qwen["overlay_sha256"]
                or not _allowed_qwen_cli_mutation(
                    read(root / "qwen-settings-sealed.json"), read(root / "qwen-settings-after-cli.json")
                )
                or read(root / "qwen-settings.json") != read(root / "qwen-settings-after-cli.json")
                or _canonical_json_sha(prepared.get("qwen_settings")) != sealed_qwen["meta_sha256"]
            ):
                raise RouteError("Qwen effective settings evidence differs")
            usage_record = read(root / "usage.json")
            if (
                usage_record.get("model_id") != "qwen3.8-27b"
                or usage_record.get("requests") != 1
                or usage_record.get("tool_calls") != 0
                or usage_record.get("input_tokens") != outcome["usage"]["input_tokens"]
                or usage_record.get("output_tokens") != outcome["usage"]["output_tokens"]
                or scorer.event_session_ids(events) != {outcome.get("session_id")}
            ):
                raise RouteError("Qwen usage or session evidence differs")
        else:
            if scorer.usage_from_events(events) != outcome["usage"] or scorer.event_session_ids(events) != {
                outcome.get("session_id")
            }:
                raise RouteError("Codex usage or session evidence differs")
            current_usage = sum(outcome["usage"].values())
            prior_total = codex_total
            codex_total += current_usage
            if (
                codex_total > LIMIT
                or outcome.get("codex_aggregate_tokens") != codex_total
                or outcome.get("codex_aggregate_prior_tokens") != prior_total
            ):
                raise RouteError("Codex aggregate token evidence exceeds seal")
    return rows


def _append(event: dict[str, Any]) -> None:
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def advance() -> dict[str, Any]:
    verify_seal()
    if not LIVE_PREFLIGHT.exists() or read(LIVE_PREFLIGHT) != preflight_record():
        raise RouteError("offline route preflight differs")
    verify_approval(dispatch=True)
    if (
        RUNTIME.is_symlink()
        or REPO in RUNTIME.resolve().parents
        or (
            RUNTIME.exists()
            and (
                stat.S_IMODE(RUNTIME.stat().st_mode) != 0o700
                or RUNTIME.stat().st_uid != os.getuid()
                or not LEDGER.is_file()
                or LEDGER.is_symlink()
            )
        )
    ):
        raise RouteError("route runtime is linked or nonprivate")
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    lock = os.open(RUNTIME / "route.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        if not LEDGER.exists():
            qualification.write_new(LEDGER, (json.dumps(_header(), sort_keys=True) + "\n").encode())
        rows = _events()
        index = (len(rows) - 1) // 2
        if index >= 4:
            return {"status": "route_checks_complete"}
        call = plan()["calls"][index]
        if (RUNTIME / call["call_id"]).exists() or (RUNTIME / call["call_id"]).is_symlink():
            raise RouteError("route call path is already used")
        return _one_call(call)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def preflight_record() -> dict[str, Any]:
    return {
        "status": "PASSED_HEADER_OPTIONAL_ROUTE_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "provider_calls": 0,
        "dispatch_allowed": False,
        "planned_calls": 4,
        "opening_codex_tokens": OPENING,
        "gateway_probe": "verified_tls_handshake_without_api_request",
    }


def offline_preflight_template() -> dict[str, Any]:
    """Record the offline state while keeping every dispatch gate closed."""
    return {
        "status": "PENDING_LIVE_TRANSPORT_AND_PINNED_CLI_CHECKS",
        "operational_seal_sha256": sha(SEAL),
        "provider_calls": 0,
        "dispatch_allowed": False,
        "planned_calls": 4,
        "opening_codex_tokens": OPENING,
        "gateway_probe": "not_run_offline",
    }


def _one_call(call: dict[str, str]) -> dict[str, Any]:
    route = call["route"]
    if route == "qwen" and not os.environ.get("LITE_LLM_AUTH_TOKEN"):
        raise RouteError("Qwen credential unavailable")
    if route == "qwen":
        check_gateway_tls()
    codex_prior = OPENING
    if route == "codex" and LEDGER.exists():
        for line in LEDGER.read_text().splitlines()[1:]:
            event = json.loads(line)
            if event.get("event") == "completed" and event.get("call", {}).get("route") == "codex":
                previous_usage = event.get("usage")
                if not isinstance(previous_usage, dict) or set(previous_usage) != {"input_tokens", "output_tokens"}:
                    raise RouteError("prior Codex usage is malformed")
                codex_prior += previous_usage["input_tokens"] + previous_usage["output_tokens"]
    prompt, packet, packet_id, elements = _packet_for(call)
    request = scorer.make_request(prompt, packet)
    root = RUNTIME / call["call_id"]
    root.mkdir(mode=0o700, exist_ok=False)
    scratch = root / "scratch"
    scratch.mkdir(mode=0o700)
    session_id = str(uuid.uuid4()) if route == "qwen" else ""
    usage: dict[str, int] | None = None
    qwen_binding = None
    if route == "qwen":
        gateway, overlay, meta, qwen_binding = qwen_effective_settings()
        if qwen_binding != read(SEAL)["qwen_effective_settings"]:
            raise RouteError("effective Qwen settings differ from seal")
        parsed = urlsplit(gateway)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise RouteError("Qwen gateway differs")
        write_json(root / "qwen-settings-sealed.json", overlay)
        write_json(root / "qwen-settings.json", overlay)
        qwen_dispatch_environment = {
            **qwen_binding["dispatch_environment"],
            "QWEN_CODE_SYSTEM_SETTINGS_PATH": str(root / "qwen-settings.json"),
        }
        environment = scorer._child_environment("qwen", os.environ.copy(), auth_token=os.environ["LITE_LLM_AUTH_TOKEN"])
        environment.update(qwen_dispatch_environment)
        command = scorer._qwen_command(shutil.which("qwen") or "", gateway, session_id)
    else:
        home, environment = qualification._prepare_codex_home(root)
        snapshot = quota.read_quota_snapshot(
            codex_executable=str(qualification.CODEX), codex_home=home, environment=environment
        )
        quota.checkpoint_decision(snapshot)
        receipt = snapshot.get("account_limit_receipt", {})
        if receipt.get("account_id_sha256") != qualification.ACCOUNT_ID_SHA or receipt.get(
            "codex_executable_sha256"
        ) != sha(qualification.CODEX):
            raise RouteError("Codex account or executable differs")
        codex_reserved_upper_bound(codex_prior)
        write_json(root / "quota-before.json", snapshot)
        command = scorer._codex_command(str(qualification.CODEX), scratch)
    write_json(
        root / "prepared.json",
        {
            "call": call,
            "seal_sha256": sha(SEAL),
            "request_sha256": sha_bytes(request),
            "packet_sha256": sha_bytes(packet),
            "prompt_sha256": sha_bytes(prompt),
            "session_id": session_id or None,
            "qwen_settings": meta if route == "qwen" else None,
            "qwen_effective_settings": qwen_binding,
            "qwen_dispatch_environment": qwen_dispatch_environment if route == "qwen" else None,
        },
    )
    _append({"event": "reserved", "call": call, "request_sha256": sha_bytes(request)})
    status = "failed"
    failure = "provider_call_incomplete"
    raw_sha = None
    canonical_sha = None
    normalization_kind = None
    try:
        process = scorer.invoke_one_provider_process(command, request, scratch, environment)
        if route == "qwen":
            qualification.write_new(root / "qwen-settings-after-cli.json", (root / "qwen-settings.json").read_bytes())
            if not _allowed_qwen_cli_mutation(overlay, read(root / "qwen-settings-after-cli.json")):
                raise RouteError("Qwen CLI settings mutation exceeded observed behavior")
        secret = os.environ.get("LITE_LLM_AUTH_TOKEN", "") if route == "qwen" else ""
        stdout = scorer.secure_capture(process.stdout, secret)
        stderr = scorer.secure_capture(process.stderr, secret)
        qualification.write_new(root / "stdout.raw", stdout)
        qualification.write_new(root / "stderr.raw", stderr)
        events = scorer.parse_jsonl(stdout)
        write_json(root / "events.json", events)
        if route == "qwen":
            if scorer.event_session_ids(events) != {session_id}:
                raise RouteError("Qwen session differs")
            record = scorer.qwen_usage_record(Path.home() / ".qwen/usage_record.jsonl", str(scratch), session_id, set())
            usage = {"input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"]}
            write_json(root / "usage.json", record)
            if record.get("model_id") != "qwen3.8-27b":
                raise RouteError("Qwen model differs")
        else:
            usage = scorer.usage_from_events(events)
            sessions = scorer.event_session_ids(events)
            if len(sessions) != 1:
                raise RouteError("Codex session is ambiguous")
            session_id = next(iter(sessions))
            rollout = qualification._verify_scorer_rollout(home, session_id, scratch, usage)
            qualification.write_new(root / "rollout.jsonl", rollout)
        raw = scorer.final_text(events)
        qualification.write_new(root / "reply.raw.tsv", raw.encode())
        canonical, normalization_kind = identity.canonicalize(raw, packet_id, elements)
        qualification.write_new(
            root / "reply.normalized.tsv", _normalized_from_canonical(canonical, packet_id).encode()
        )
        qualification.write_new(root / "reply.tsv", canonical.encode())
        raw_sha = sha(root / "reply.raw.tsv")
        canonical_sha = sha(root / "reply.tsv")
        scorer.validate_tsv(canonical, packet_id, elements)
        if process.returncode or scorer.tool_markers(events) or scorer.cli_retry_error_markers(events, stderr):
            raise RouteError("process, tool or visible retry condition failed")
        if usage["input_tokens"] > CODEX_INPUT_CAP or usage["output_tokens"] > (
            QWEN_OUTPUT_CAP if route == "qwen" else CODEX_OUTPUT_CAP
        ):
            raise RouteError("scorer observed token setting exceeded")
        status = "passed_unscored"
        failure = ""
    except Exception as exc:
        failure = type(exc).__name__
    outcome = {
        "record_type": "p3_v3_header_optional_v8_scorer_route_outcome",
        "route": route,
        "status": status,
        "scored_p3": False,
        "qualification_data": False,
        "call_id": call["call_id"],
        "session_id": session_id or None,
        "seal_sha256": sha(SEAL),
        "request_sha256": sha_bytes(request),
        "packet_sha256": sha_bytes(packet),
        "prompt_sha256": sha_bytes(prompt),
        "raw_reply_sha256": raw_sha,
        "canonical_reply_sha256": canonical_sha,
        "normalized_reply_sha256": sha(root / "reply.normalized.tsv")
        if (root / "reply.normalized.tsv").is_file()
        else None,
        "normalization_kind": normalization_kind,
        "qwen_effective_settings": qwen_binding,
        "qwen_dispatch_environment": qwen_dispatch_environment if route == "qwen" else None,
        "tool_markers": scorer.tool_markers(read(root / "events.json")) if (root / "events.json").is_file() else [],
        "visible_retry_error_markers": (
            scorer.cli_retry_error_markers(read(root / "events.json"), (root / "stderr.raw").read_bytes())
            if (root / "events.json").is_file() and (root / "stderr.raw").is_file()
            else []
        ),
        "codex_aggregate_prior_tokens": codex_prior if route == "codex" else None,
        "codex_aggregate_tokens": (
            codex_prior + sum(usage.values()) if route == "codex" and usage is not None else None
        ),
        "evidence_sha256": {
            name: sha(root / name)
            for name in (
                "prepared.json",
                "stdout.raw",
                "stderr.raw",
                "events.json",
                "reply.raw.tsv",
                "reply.normalized.tsv",
                "reply.tsv",
                "usage.json",
                "qwen-settings.json",
                "qwen-settings-sealed.json",
                "qwen-settings-after-cli.json",
                "quota-before.json",
                "rollout.jsonl",
            )
            if (root / name).is_file()
        },
        "usage": usage,
        "failure_class": failure or None,
        "retry_authorized": False,
    }
    write_json(root / "outcome.json", outcome)
    _append(
        {
            "event": "completed",
            "call": call,
            "status": status,
            "usage": usage,
            "outcome_sha256": sha(root / "outcome.json"),
        }
    )
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("prepare-plan", "seal", "offline-preflight", "preflight", "approval-template", "advance", "status"),
    )
    action = parser.parse_args().action
    if action == "prepare-plan":
        prompt = qualification.packet.PROMPT.read_bytes()
        packet_hashes = {key: sha(PACKETS[key]["root"] / "packet.md") for key in PACKET_KEYS}
        calls = [
            {"packet_key": key, "route": route, "call_id": "g" + uuid.uuid4().hex}
            for key in PACKET_KEYS
            for route in ROUTES
        ]
        write_json(
            PLAN,
            {
                "record_type": "p3_v3_header_optional_route_v8_plan",
                "packet_sha256": packet_hashes,
                "prompt_sha256": sha_bytes(prompt),
                "calls": calls,
            },
        )
        result = {"status": "PLAN_PREPARED", "plan_sha256": sha(PLAN)}
    elif action == "seal":
        write_json(SEAL, seal_body())
        result = {"status": "SEALED_OFFLINE", "seal_sha256": sha(SEAL)}
    elif action == "offline-preflight":
        result = offline_preflight_template()
        write_json(PREFLIGHT, result)
    elif action == "preflight":
        result = preflight()
        write_json(LIVE_PREFLIGHT, result)
    elif action == "approval-template":
        result = approval_template()
        write_json(APPROVAL, result)
    elif action == "advance":
        result = advance()
    else:
        result = {"status": "NOT_COMPLETE"}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "ROUTE_STOP", "reason_class": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2) from None
