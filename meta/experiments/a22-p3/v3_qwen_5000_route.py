#!/usr/bin/env python3
"""One terminal, unscored Qwen scorer mechanics check at a 5,000-token setting."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import scorer_route_check as scorer
import v3_successor_route_check as prior_route
import v3_successor_route_packet as packet_builder

HERE = Path(__file__).resolve().parent
PROPOSAL = HERE / "V3_QWEN_5000_ROUTE_PROPOSAL.md"
SEAL = HERE / "runs/v3-qwen-5000-route-seal-v1.json"
PREFLIGHT = HERE / "runs/v3-qwen-5000-route-preflight-v1.json"
APPROVAL = HERE / "runs/v3-qwen-5000-route-approval-v1.json"
RUNTIME = Path("/tmp/a22-p3-v3-qwen-5000-route-runtime")  # noqa: S108
OLD_RUNTIME = Path("/tmp/a22-p3-v3-qualification-runtime")  # noqa: S108
OLD_LEDGER = OLD_RUNTIME / "qualification-events.jsonl"
OLD_SEAL = HERE / "runs/v3-qualification-operational-seal-v1.json"
OLD_APPROVAL = HERE / "runs/v3-qualification-approval-v1.json"
PACKET = prior_route.PACKET_ROOT / "visible/packet.md"
MANIFEST = prior_route.PACKET_ROOT / "evaluator/manifest.json"
PROMPT = HERE / "scoring/scorer-prompt.txt"
MODEL = "qwen3.8-27b"
CLI_VERSION = "0.24.7"
INPUT_LIMIT = 20_000
OUTPUT_LIMIT = 5_000
OLD_OUTPUT_LIMIT = 2_000
PRIVATE_DIR_MODE = 0o700
OLD_LEDGER_ROW_COUNT = 15
OLD_CALL_COUNT = 7


class RouteError(ValueError):
    """A sealed route condition or one-shot evidence check failed."""


def sha(path: Path) -> str:
    """Hash a regular evidence file without following a link."""
    if path.is_symlink() or not path.is_file():
        raise RouteError(f"missing or linked input: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    """Read a regular JSON artifact."""
    sha(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, data: bytes) -> None:
    """Create a private artifact once."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise RouteError("artifact directory is linked")
    if path.is_relative_to(RUNTIME) and stat.S_IMODE(path.parent.stat().st_mode) != PRIVATE_DIR_MODE:
        raise RouteError("runtime artifact directory is not private")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, value: Any) -> None:
    """Create one canonical JSON artifact."""
    write_new(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def packet_inputs() -> tuple[dict[str, Any], bytes, bytes, list[str]]:
    """Re-render the prior unscored route packet from its sealed source."""
    manifest = read(MANIFEST)
    if manifest.get("scored_p3") is not False or manifest.get("qualification_data") is not False:
        raise RouteError("route packet is scored data")
    packet = packet_builder.packet_bytes(manifest["opaque_packet_id"])
    if packet != PACKET.read_bytes() or hashlib.sha256(packet).hexdigest() != manifest.get("packet_sha256"):
        raise RouteError("prior route packet differs from source rendering")
    prompt = packet_builder._sealed_bytes(PROMPT)
    if hashlib.sha256(prompt).hexdigest() != manifest.get("prompt_sha256"):
        raise RouteError("prior route prompt differs from packet manifest")
    case = read(packet_builder.CASE)
    ids = [item.split(":", 1)[0] for item in case["scoring"]]
    if ids != ["E1", "E2", "E3", "E4"]:
        raise RouteError("P3-01 scorer elements differ")
    return manifest, packet, prompt, ids


def old_attempt() -> None:
    """Require the exact terminal predecessor without accepting its failed call."""
    old_seal = read(OLD_SEAL)
    old_approval = read(OLD_APPROVAL)
    if (
        old_seal.get("scorer_output_settings") != {"codex": 1000, "qwen": 2000}
        or old_approval.get("operational_seal_sha256") != sha(OLD_SEAL)
        or old_approval.get("authorized_phases") != ["qualification"]
    ):
        raise RouteError("predecessor qualification binding differs")
    rows = [json.loads(line) for line in OLD_LEDGER.read_text().splitlines() if line.strip()]
    completions = [row for row in rows if row.get("event") == "completed"]
    if (
        len(rows) != OLD_LEDGER_ROW_COUNT
        or len(completions) != OLD_CALL_COUNT
        or [row.get("status") for row in completions]
        != ["accepted", "accepted", "accepted", "accepted", "accepted", "accepted", "failed"]
    ):
        raise RouteError("predecessor ledger is not the terminal seven-call attempt")
    last = completions[-1]
    if last.get("usage") != {"input_tokens": 12_591, "output_tokens": 2_000}:
        raise RouteError("terminal Qwen usage differs")


def seal_body() -> dict[str, Any]:
    """Bind all offline inputs and the terminal predecessor."""
    old_attempt()
    packet_inputs()
    return {
        "schema": 1,
        "record_type": "p3_v3_qwen_5000_route_seal",
        "scope": ["qwen_5000_route_check"],
        "status": "offline_candidate_pending_owner_acceptance",
        "provider_calls_started": 0,
        "model": MODEL,
        "cli_version": CLI_VERSION,
        "qwen_executable_sha256": sha(Path(shutil.which("qwen") or "/missing/qwen").resolve(strict=True)),
        "thinking": "provider default retained",
        "input_observed_limit": INPUT_LIMIT,
        "output_setting_and_observed_limit": OUTPUT_LIMIT,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "prior_codex_v3_charge": 273_286,
        "codex_v3_ceiling": 5_000_000,
        "proposal_sha256": sha(PROPOSAL),
        "runner_sha256": sha(HERE / "v3_qwen_5000_route.py"),
        "scorer_helper_sha256": sha(HERE / "scorer_route_check.py"),
        "packet_builder_sha256": sha(HERE / "v3_successor_route_packet.py"),
        "packet_sha256": sha(PACKET),
        "manifest_sha256": sha(MANIFEST),
        "prompt_sha256": sha(PROMPT),
        "old_qualification_seal_sha256": sha(OLD_SEAL),
        "old_qualification_approval_sha256": sha(OLD_APPROVAL),
        "old_qualification_ledger_sha256": sha(OLD_LEDGER),
        "prior_qwen_route_seal_sha256": sha(prior_route.SEAL),
        "runtime_root": str(RUNTIME),
    }


def verify_seal() -> dict[str, Any]:
    """Reject a stale or altered route seal."""
    actual = read(SEAL)
    if actual != seal_body():
        raise RouteError("Qwen 5,000 route seal differs from offline inputs")
    return actual


def approval_template() -> dict[str, Any]:
    """Default-deny approval bound to the exact seal and preflight."""
    return {
        "schema": 1,
        "record_type": "p3_v3_qwen_5000_route_approval",
        "operational_seal_sha256": sha(SEAL),
        "preflight_sha256": sha(PREFLIGHT),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "acceptance_basis": "owner direction after terminal qualification report: запускай",
    }


def verify_approval() -> None:
    """Require exact affirmative owner acceptance for one route call."""
    actual = read(APPROVAL)
    expected = approval_template()
    if actual != {
        **expected,
        "owner_accepted": True,
        "dispatch_allowed": True,
        "authorized_phases": ["qwen_5000_route_check"],
    }:
        raise RouteError("one-shot Qwen route call lacks exact phase approval")


def qwen_settings() -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Retain the checked default-thinking route and raise only output allowance."""
    gateway, overlay, meta = scorer._qwen_preflight(Path.home(), os.environ.copy())
    entries = overlay.get("modelProviders", {}).get("openai", [])
    if (
        len(entries) != 1
        or entries[0].get("generationConfig", {}).get("samplingParams", {}).get("max_tokens") != OLD_OUTPUT_LIMIT
    ):
        raise RouteError("prior Qwen overlay shape differs")
    if meta.get("thinking_override") != "omitted; provider default retained" or meta.get("maxRetries") != 0:
        raise RouteError("Qwen default thinking or retry setting differs")
    entries[0]["generationConfig"]["samplingParams"]["max_tokens"] = OUTPUT_LIMIT
    meta["max_tokens"] = OUTPUT_LIMIT
    parsed = urlsplit(gateway)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RouteError("Qwen gateway is malformed")
    return gateway, overlay, meta


def preflight() -> dict[str, Any]:
    """Check the sealed route without a provider call."""
    verify_seal()
    packet_inputs()
    if RUNTIME.exists():
        raise RouteError("one-shot route runtime is already used")
    executable = shutil.which("qwen")
    if not executable:
        raise RouteError("pinned Qwen CLI is unavailable")
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
    if version.returncode or not scorer._version_matches(version.stdout + version.stderr, CLI_VERSION):
        raise RouteError("Qwen CLI version differs")
    _, _, meta = qwen_settings()
    result = {
        "schema": 1,
        "status": "PASSED_OFFLINE_QWEN_5000_ROUTE_PREFLIGHT",
        "dispatch_allowed": False,
        "provider_calls": 0,
        "operational_seal_sha256": sha(SEAL),
        "qwen_version": CLI_VERSION,
        "qwen_model": MODEL,
        "qwen_settings": meta,
    }
    write_json(PREFLIGHT, result)
    return result


def dispatch() -> dict[str, Any]:  # noqa: PLR0915
    """Dispatch at most one Qwen scorer call after exact phase approval."""
    verify_seal()
    pre = read(PREFLIGHT)
    if pre.get("status") != "PASSED_OFFLINE_QWEN_5000_ROUTE_PREFLIGHT" or pre.get("operational_seal_sha256") != sha(
        SEAL
    ):
        raise RouteError("offline preflight differs")
    verify_approval()
    executable = shutil.which("qwen")
    if not executable:
        raise RouteError("Qwen CLI is unavailable")
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
    if (
        sha(Path(executable).resolve(strict=True)) != verify_seal()["qwen_executable_sha256"]
        or version.returncode
        or not scorer._version_matches(version.stdout + version.stderr, CLI_VERSION)
    ):
        raise RouteError("Qwen binary or version differs from sealed preflight")
    manifest, packet, prompt, ids = packet_inputs()
    request = scorer.make_request(prompt, packet)
    gateway, overlay, meta = qwen_settings()
    RUNTIME.mkdir(mode=0o700, exist_ok=False)
    if RUNTIME.is_symlink() or stat.S_IMODE(RUNTIME.stat().st_mode) != PRIVATE_DIR_MODE:
        raise RouteError("route runtime is not private")
    lock = os.open(RUNTIME / "route.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        scratch = RUNTIME / "scratch"
        scratch.mkdir(mode=0o700)
        write_json(RUNTIME / "qwen-settings.json", overlay)
        session_id = str(uuid.uuid4())
        call_id = "g" + uuid.uuid4().hex
        command = scorer._qwen_command(executable, gateway, session_id)
        environment = scorer._child_environment("qwen", os.environ.copy(), auth_token=os.environ["LITE_LLM_AUTH_TOKEN"])
        environment.update(
            {
                "QWEN_CODE_SYSTEM_SETTINGS_PATH": str(RUNTIME / "qwen-settings.json"),
                "QWEN_CODE_MAX_OUTPUT_TOKENS": str(OUTPUT_LIMIT),
                "QWEN_CODE_UNATTENDED_RETRY": "0",
            }
        )
        write_json(
            RUNTIME / "reserved.json",
            {
                "call_id": call_id,
                "session_id": session_id,
                "seal_sha256": sha(SEAL),
                "approval_sha256": sha(APPROVAL),
                "request_sha256": hashlib.sha256(request).hexdigest(),
                "packet_sha256": sha(PACKET),
                "settings": meta,
                "scored_p3": False,
                "qualification_data": False,
            },
        )
        usage: dict[str, int] | None = None
        outcome = "failed"
        reason = "provider_call_incomplete"
        try:
            process = scorer.invoke_one_provider_process(command, request, scratch, environment)
            secret = os.environ["LITE_LLM_AUTH_TOKEN"]
            stdout = scorer.secure_capture(process.stdout, secret)
            stderr = scorer.secure_capture(process.stderr, secret)
            write_new(RUNTIME / "stdout.raw", stdout)
            write_new(RUNTIME / "stderr.raw", stderr)
            events = scorer.parse_jsonl(stdout)
            write_json(RUNTIME / "events.json", events)
            if scorer.event_session_ids(events) != {session_id}:
                raise RouteError("Qwen event session differs")
            record = scorer.qwen_usage_record(Path.home() / ".qwen/usage_record.jsonl", str(scratch), session_id, set())
            usage = {"input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"]}
            write_json(RUNTIME / "usage.json", record)
            reply = scorer.final_text(events)
            write_new(RUNTIME / "reply.tsv", reply.encode())
            scorer.validate_tsv(reply, manifest["opaque_packet_id"], ids)
            if process.returncode or scorer.tool_markers(events) or scorer.cli_retry_error_markers(events, stderr):
                raise RouteError("Qwen process, tool or visible retry condition failed")
            if (
                record["model_id"] != MODEL
                or usage["input_tokens"] > INPUT_LIMIT
                or usage["output_tokens"] > OUTPUT_LIMIT
            ):
                raise RouteError("Qwen model or observed token limit differs")
            outcome = "passed_unscored"
            reason = "complete TSV and correlated usage"
        except Exception as exc:  # noqa: BLE001 - one provider process has a terminal outcome
            reason = type(exc).__name__
        result = {
            "call_id": call_id,
            "session_id": session_id,
            "outcome": outcome,
            "reason": reason,
            "usage": usage,
            "retry_authorized": False,
            "scored_p3": False,
            "qualification_data": False,
        }
        write_json(RUNTIME / "outcome.json", result)
        return result
    finally:
        os.close(lock)


def main() -> None:
    """Run only the explicit offline or one-shot route action."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seal", "preflight", "approval-template", "dispatch", "status"))
    args = parser.parse_args()
    if args.action == "seal":
        write_json(SEAL, seal_body())
        result = {"seal_sha256": sha(SEAL)}
    elif args.action == "preflight":
        result = preflight()
    elif args.action == "approval-template":
        result = approval_template()
        write_json(APPROVAL, result)
    elif args.action == "dispatch":
        result = dispatch()
    else:
        result = (
            read(RUNTIME / "outcome.json") if (RUNTIME / "outcome.json").is_file() else {"status": "NOT_DISPATCHED"}
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
