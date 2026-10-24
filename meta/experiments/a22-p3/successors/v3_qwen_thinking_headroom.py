#!/usr/bin/env python3
"""One terminal, unscored Qwen mechanics call before a fresh A qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import ssl
import stat
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scorer_route_check as scorer  # noqa: E402
import v3_scorer_header_optional as parser  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
RUNS = HERE / "runs"
PLAN = RUNS / "v3-qwen-thinking-headroom-plan-v1.json"
SEAL = RUNS / "v3-qwen-thinking-headroom-seal-v1.json"
PREFLIGHT = RUNS / "v3-qwen-thinking-headroom-preflight-v1.json"
APPROVAL = RUNS / "v3-qwen-thinking-headroom-approval-v1.json"
PACKET = RUNS / "v3-qwen-thinking-headroom-packet-v1.md"
PROMPT = HERE / "scoring/scorer-prompt-id-bound.txt"
PROPOSAL = HERE / "V3_QWEN_THINKING_HEADROOM_PROPOSAL.md"
SOURCE = Path(__file__).resolve()
RUNTIME = Path("/tmp/a22-p3-v3-qwen-thinking-headroom-runtime")
PREDECESSOR = Path("/tmp/a22-p3-v3-qualification-header-optional-runtime")
OUTPUT = 16_000


def sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing or linked file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    sha(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, data) -> None:
    write_new(path, (json.dumps(data, sort_keys=True, indent=2) + "\n").encode())


def settings():
    gateway, overlay, meta = scorer._qwen_preflight(Path.home(), os.environ.copy())
    provider = overlay["modelProviders"]["openai"]
    if len(provider) != 1 or provider[0]["id"] != "qwen3.8-27b":
        raise ValueError("Qwen provider identity differs")
    generation = provider[0]["generationConfig"]
    if generation.get("maxRetries") != 0 or meta.get("thinking_override") != "omitted; provider default retained":
        raise ValueError("Qwen no-retry or thinking condition differs")
    generation["samplingParams"]["max_tokens"] = OUTPUT
    parsed = urlsplit(gateway)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Qwen gateway differs")
    return gateway, overlay, meta


def expected_seal():
    plan = read(PLAN)
    failure = read(PREDECESSOR / "evidence" / plan["prior_call_id"] / "failure.json")
    ledger = PREDECESSOR / "qualification-events.jsonl"
    if failure.get("retry_authorized") is not False or plan.get("element_ids") != ["E1", "E2", "E3", "E4"]:
        raise ValueError("terminal predecessor or four-element plan differs")
    old = PREDECESSOR / "evidence" / plan["prior_call_id"] / "packet.md"
    packet = PACKET.read_bytes()
    old_bytes = old.read_bytes()
    if (
        len(packet) != len(old_bytes)
        or plan["packet_id"] == plan["prior_packet_id"]
        or old_bytes.count(plan["prior_packet_id"].encode()) != 1
        or packet != old_bytes.replace(plan["prior_packet_id"].encode(), plan["packet_id"].encode())
        or len(plan["packet_id"]) != len(plan["prior_packet_id"])
    ):
        raise ValueError("fresh blinded packet or size differs")
    gateway, overlay, meta = settings()
    return {
        "schema": 1,
        "record_type": "p3_v3_qwen_thinking_headroom_seal",
        "scope": "one_unscored_qwen_mechanics_call",
        "plan_sha256": sha(PLAN),
        "proposal_sha256": sha(PROPOSAL),
        "packet_sha256": sha(PACKET),
        "prompt_sha256": sha(PROMPT),
        "source_sha256": {"runner": sha(SOURCE), "route": sha(HERE / "scorer_route_check.py"), "parser": sha(HERE / "v3_scorer_header_optional.py")},
        "predecessor_sha256": {"ledger": sha(ledger), "failure": sha(PREDECESSOR / "evidence" / plan["prior_call_id"] / "failure.json"), "packet": sha(old)},
        "gateway_sha256": hashlib.sha256(gateway.encode()).hexdigest(),
        "settings_sha256": hashlib.sha256(json.dumps(overlay, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "qwen_model": "qwen3.8-27b",
        "qwen_cli_version": "0.24.7",
        "qwen_output_setting": OUTPUT,
        "thinking": meta["thinking_override"],
        "max_retries": 0,
        "max_tools": 0,
        "runtime": str(RUNTIME),
        "status": "offline_candidate_pending_owner_acceptance",
    }


def preflight():
    if read(SEAL) != expected_seal() or RUNTIME.exists() or RUNTIME.is_symlink():
        raise ValueError("seal differs or runtime already used")
    if not os.environ.get("LITE_LLM_AUTH_TOKEN"):
        raise ValueError("Qwen credential absent")
    qwen = shutil.which("qwen")
    if not qwen:
        raise ValueError("Qwen executable absent")
    import subprocess
    version = subprocess.run([qwen, "--version"], capture_output=True, text=True, timeout=10, check=False)
    if version.returncode or not scorer._version_matches(version.stdout + version.stderr, "0.24.7"):
        raise ValueError("Qwen CLI version differs")
    gateway, _, _ = settings()
    parsed = urlsplit(gateway)
    with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=8) as stream:
        with ssl.create_default_context().wrap_socket(stream, server_hostname=parsed.hostname):
            pass
    return {"status": "passed", "provider_calls": 0, "dispatch_allowed": False, "seal_sha256": sha(SEAL), "gateway_probe": "verified_tls_handshake"}


def dispatch():
    if read(SEAL) != expected_seal() or read(PREFLIGHT) != {"status": "passed", "provider_calls": 0, "dispatch_allowed": False, "seal_sha256": sha(SEAL), "gateway_probe": "verified_tls_handshake"}:
        raise ValueError("exact sealed preflight absent")
    approval = read(APPROVAL)
    if approval != {"owner_accepted": True, "dispatch_allowed": True, "authorized_phases": ["qwen_thinking_headroom_route"], "seal_sha256": sha(SEAL), "preflight_sha256": sha(PREFLIGHT), "acceptance_basis": "owner requested the new call and fresh A rerun in this chat"}:
        raise ValueError("exact route approval absent")
    if RUNTIME.exists() or RUNTIME.is_symlink():
        raise ValueError("route already attempted")
    RUNTIME.mkdir(mode=0o700)
    scratch = RUNTIME / "scratch"
    scratch.mkdir(mode=0o700)
    gateway, overlay, _ = settings()
    write_json(RUNTIME / "settings-sealed.json", overlay)
    write_json(RUNTIME / "settings.json", overlay)
    packet_id = read(PLAN)["packet_id"]
    request = scorer.make_request(PROMPT.read_bytes(), PACKET.read_bytes())
    write_json(RUNTIME / "reservation.json", {"seal_sha256": sha(SEAL), "approval_sha256": sha(APPROVAL), "request_sha256": hashlib.sha256(request).hexdigest(), "packet_id": packet_id})
    session = str(uuid.uuid4())
    before = set()
    usage_file = Path.home() / ".qwen/usage_record.jsonl"
    if usage_file.exists():
        for line in usage_file.read_text().splitlines():
            try:
                before.add(json.loads(line).get("sessionId"))
            except json.JSONDecodeError:
                pass
    env = scorer._child_environment("qwen", os.environ.copy(), auth_token=os.environ["LITE_LLM_AUTH_TOKEN"])
    env.update({"QWEN_CODE_SYSTEM_SETTINGS_PATH": str(RUNTIME / "settings.json"), "QWEN_CODE_MAX_OUTPUT_TOKENS": str(OUTPUT), "QWEN_CODE_UNATTENDED_RETRY": "0"})
    command = scorer._qwen_command(shutil.which("qwen") or "", gateway, session)
    try:
        process = scorer.invoke_one_provider_process(command, request, scratch, env)
        write_new(RUNTIME / "stdout.raw", scorer.secure_capture(process.stdout, os.environ["LITE_LLM_AUTH_TOKEN"]))
        write_new(RUNTIME / "stderr.raw", scorer.secure_capture(process.stderr, os.environ["LITE_LLM_AUTH_TOKEN"]))
        write_new(RUNTIME / "settings-after.json", (RUNTIME / "settings.json").read_bytes())
        events = scorer.parse_jsonl((RUNTIME / "stdout.raw").read_bytes())
        write_json(RUNTIME / "events.json", events)
        usage = scorer.qwen_usage_record(usage_file, str(scratch), session, before)
        write_json(RUNTIME / "usage.json", usage)
        if (
            process.returncode
            or scorer.event_session_ids(events) != {session}
            or usage["requests"] != 1
            or usage["tool_calls"] != 0
            or usage["output_tokens"] > OUTPUT
            or usage["input_tokens"] > 20_000
        ):
            raise ValueError("process, identity or usage differs")
        if scorer.cli_retry_error_markers(events, (RUNTIME / "stderr.raw").read_bytes()) or scorer.tool_markers(events):
            raise ValueError("visible retry, error or tool marker")
        after = read(RUNTIME / "settings-after.json")
        if after != {**overlay, "$version": 4}:
            raise ValueError("Qwen effective settings drift")
        raw = scorer.final_text(events)
        canonical, kind = parser.canonicalize(raw, packet_id, read(PLAN)["element_ids"])
        write_new(RUNTIME / "reply.raw.tsv", raw.encode())
        write_new(RUNTIME / "reply.tsv", canonical.encode())
        result = {"status": "accepted", "unscored": True, "usage": usage, "normalization_kind": kind, "packet_id": packet_id, "seal_sha256": sha(SEAL)}
    except Exception as exc:
        result = {"status": "failed", "unscored": True, "error": type(exc).__name__, "detail": str(exc), "retry_authorized": False, "seal_sha256": sha(SEAL)}
    write_json(RUNTIME / "outcome.json", result)
    return result


def main():
    command = argparse.ArgumentParser()
    command.add_argument("phase", choices=["seal", "preflight", "dispatch"])
    args = command.parse_args()
    if args.phase == "seal":
        write_json(SEAL, expected_seal())
    elif args.phase == "preflight":
        write_json(PREFLIGHT, preflight())
    else:
        print(json.dumps(dispatch(), sort_keys=True))


if __name__ == "__main__":
    main()
