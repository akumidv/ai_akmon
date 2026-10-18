#!/usr/bin/env python3
"""Offline gate and one-shot V3 successor scorer route checks."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import quota_adapter_v3 as quota
import usage_ledger_v3 as source_ledger
import v3_successor_route_packet as packet_builder

HERE = Path(__file__).resolve().parent
PROPOSAL = HERE / "V3_SUCCESSOR_ROUTE_CHECK_PROPOSAL.md"
SEAL = HERE / "runs" / "successor-route-check-seal-v6.json"
APPROVAL = HERE / "runs" / "successor-route-check-approval-v6.json"
PREFLIGHT = HERE / "runs" / "successor-route-check-preflight-v6.json"
ACCEPTANCE_EVIDENCE = HERE / "runs" / "successor-route-check-acceptance-evidence-v6.json"
PACKET_ROOT = Path("/tmp/a22-p3-v3-successor-route-packet")  # noqa: S108
RUNTIME_ROOT = Path("/tmp/a22-p3-v3-successor-route-runtime")  # noqa: S108
PRIOR_OBSERVED_CODEX_TOKENS = 54_010
CODEX_LIMIT = 5_000_000
CODEX_EXECUTABLE = Path("/home/ai/.codex/packages/standalone/releases/0.156.1-x86_64-unknown-linux-musl/bin/codex")
SCORER_NAMES = (
    "v3_successor_route_packet.py",
    "v3_successor_route_check.py",
    "scorer_route_check.py",
    "quota_adapter_v3.py",
    "usage_ledger_v3.py",
)
ROUTES = ("codex", "qwen")
SOURCE_CALL_COUNT = 2
INPUT_LIMIT = 20_000
OUTPUT_LIMITS = {"codex": 1_000, "qwen": 2_000}
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


class RouteError(ValueError):
    """The exact route gate, source, packet, or provider evidence failed."""


def sha(path: Path) -> str:
    """Hash exact file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _ensure_runtime() -> None:
    """Reject pre-existing linked, shared, or foreign runtime locations."""
    if RUNTIME_ROOT.is_symlink():
        raise RouteError("route runtime is linked")
    RUNTIME_ROOT.mkdir(mode=0o700, exist_ok=True)
    info = RUNTIME_ROOT.stat()
    if not RUNTIME_ROOT.is_dir() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != PRIVATE_DIR_MODE:
        raise RouteError("route runtime is not an owned private directory")


def _write_json(path: Path, value: Any) -> None:
    _write_new(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def _helper() -> Any:
    spec = importlib.util.spec_from_file_location("a22_v3_route_helpers", HERE / "scorer_route_check.py")
    if spec is None or spec.loader is None:
        raise RouteError("sealed scorer mechanics are unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_seal() -> dict[str, Any]:
    """Bind the exact route inputs and V3 source ledger; do not authorize dispatch."""
    manifest = _read(PACKET_ROOT / "evaluator" / "manifest.json")
    return {
        "schema": 1,
        "record_type": "p3_v3_successor_route_check_seal",
        "scope": ["route_checks"],
        "status": "offline_candidate_pending_owner_acceptance",
        "proposal_sha256": sha(PROPOSAL),
        "previous_source_seal_sha256": sha(HERE / "runs" / "source-version-successor-seal-v1.json"),
        "previous_source_approval_sha256": sha(HERE / "runs" / "source-version-successor-approval-v1.json"),
        "source_record_sha256": sha(packet_builder.RECORD),
        "source_exchange_sha256": sha(packet_builder.EXCHANGE),
        "source_ledger_sha256": sha(packet_builder.LEDGER),
        "packet_sha256": sha(PACKET_ROOT / "visible" / "packet.md"),
        "packet_manifest_sha256": sha(PACKET_ROOT / "evaluator" / "manifest.json"),
        "prompt_sha256": sha(packet_builder.PROMPT),
        "opaque_packet_id": manifest["opaque_packet_id"],
        "source_sha256": {name: sha(HERE / name) for name in SCORER_NAMES},
        "regression_sha256": sha(HERE.parents[1] / "tests" / "test_a22_p3_v3_successor_route.py"),
        "prior_v3_observed_codex_tokens": PRIOR_OBSERVED_CODEX_TOKENS,
        "codex_limit_tokens": CODEX_LIMIT,
        "provider_calls_started": 0,
    }


def validate_seal() -> dict[str, Any]:
    """Reject changed code, source, packet, prompt, or earlier approval."""
    actual = _read(SEAL)
    if actual != expected_seal():
        raise RouteError("route seal is stale or malformed")
    return actual


def approval_template() -> dict[str, Any]:
    """Build the explicit default-deny phase record."""
    validate_seal()
    return {
        "schema": 1,
        "record_type": "p3_v3_successor_route_check_approval",
        "operational_seal_sha256": sha(SEAL),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
        "acceptance_evidence_sha256": None,
        "preflight_report_sha256": None,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
        "qwen_aggregate_token_ceiling": None,
    }


def expected_owner_reply() -> str:
    """One short, unambiguous owner decision for the exact route candidate."""
    return f"Подтверждаю route_checks для seal SHA-256 {sha(SEAL)}; оператор остановки — я."


def validate_approval(*, dispatch: bool) -> dict[str, Any]:
    """Require exact phase acceptance; never infer it from source approval."""
    actual = _read(APPROVAL)
    expected = approval_template()
    if not dispatch:
        if actual != expected:
            raise RouteError("route approval is not its default-deny template")
        return actual
    if (
        actual.get("schema") != 1
        or actual.get("record_type") != expected["record_type"]
        or actual.get("operational_seal_sha256") != expected["operational_seal_sha256"]
        or actual.get("owner_accepted") is not True
        or actual.get("dispatch_allowed") is not True
        or actual.get("authorized_phases") != ["route_checks"]
        or actual.get("named_stop_operator") != "owner (current chat session)"
        or actual.get("retry_evidence_policy") != "OBSERVED_NO_RETRY"
        or actual.get("qwen_aggregate_token_ceiling") is not None
        or not isinstance(actual.get("acceptance_evidence_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", actual["acceptance_evidence_sha256"])
        or actual.get("preflight_report_sha256") != sha(PREFLIGHT)
    ):
        raise RouteError("route-check phase is not accepted for this exact seal")
    if not ACCEPTANCE_EVIDENCE.is_file() or ACCEPTANCE_EVIDENCE.is_symlink():
        raise RouteError("route owner acceptance evidence is unavailable")
    evidence = _read(ACCEPTANCE_EVIDENCE)
    if (
        sha(ACCEPTANCE_EVIDENCE) != actual["acceptance_evidence_sha256"]
        or evidence.get("record_type") != "p3_v3_route_owner_acceptance"
        or evidence.get("accepted_seal_sha256") != sha(SEAL)
        or evidence.get("scope") != ["route_checks"]
        or evidence.get("stop_operator") != "owner (current chat session)"
        or not isinstance(evidence.get("request_message_id"), str)
        or not isinstance(evidence.get("user_message_id"), str)
        or sha(SEAL) not in evidence.get("request_text", "")
        or evidence.get("user_text") != expected_owner_reply()
    ):
        raise RouteError("route owner acceptance evidence is stale or malformed")
    return actual


def validate_packet() -> tuple[dict[str, Any], bytes, bytes, list[str]]:
    """Re-render from exact V3 source and require one unchanged blind packet."""
    seal = validate_seal()
    visible = PACKET_ROOT / "visible" / "packet.md"
    manifest = _read(PACKET_ROOT / "evaluator" / "manifest.json")
    if (
        PACKET_ROOT.is_symlink()
        or visible.is_symlink()
        or set(manifest)
        != {
            "schema",
            "record_type",
            "opaque_packet_id",
            "packet_sha256",
            "prompt_sha256",
            "source_record_sha256",
            "source_exchange_sha256",
            "source_rollout_sha256",
            "source_ledger_sha256",
            "source_epoch_id",
            "source_run_id",
            "source_provenance_scope",
            "scored_p3",
            "qualification_data",
        }
        or manifest.get("scored_p3") is not False
        or manifest.get("qualification_data") is not False
        or manifest.get("source_provenance_scope") != "evaluator_only"
        or manifest.get("source_run_id") != packet_builder.RUN_ID
        or manifest.get("packet_sha256") != seal["packet_sha256"]
    ):
        raise RouteError("route packet manifest is invalid")
    packet = packet_builder.packet_bytes(manifest["opaque_packet_id"])
    if packet != visible.read_bytes():
        raise RouteError("route packet differs from verified source rendering")
    prompt = packet_builder._sealed_bytes(packet_builder.PROMPT)
    if hashlib.sha256(prompt).hexdigest() != seal["prompt_sha256"]:
        raise RouteError("route prompt changed")
    case = _read(packet_builder.CASE)
    ids = [row.split(":", 1)[0] for row in case["scoring"]]
    if ids != ["E1", "E2", "E3", "E4"]:
        raise RouteError("route scoring elements differ from frozen P3-01")
    return manifest, packet, prompt, ids


def offline_preflight() -> dict[str, Any]:
    """Verify exact route readiness without network or provider calls."""
    seal = validate_seal()
    validate_approval(dispatch=False)
    manifest, packet, prompt, ids = validate_packet()
    header, events = source_ledger._read(packet_builder.LEDGER)
    known = [event for event in events if event.get("event") == "completed" and event.get("route") == "codex"]
    observed = 26_988 + sum(
        event["input_tokens"] + event["output_tokens"] for event in known if event.get("usage_status") == "known"
    )
    if len(known) != SOURCE_CALL_COUNT or observed != PRIOR_OBSERVED_CODEX_TOKENS:
        raise RouteError("V3 source usage does not match route opening balance")
    if header.get("epoch_id") != manifest["source_epoch_id"]:
        raise RouteError("source epoch changed")
    if RUNTIME_ROOT.resolve() == HERE or HERE in RUNTIME_ROOT.resolve().parents:
        raise RouteError("route runtime must be outside the repository")
    return {
        "status": "PASSED_OFFLINE_ROUTE_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "elements": ids,
        "prior_v3_observed_codex_tokens": observed,
        "provider_calls": 0,
        "dispatch_allowed": False,
        "scope": seal["scope"],
    }


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _ledger_header() -> dict[str, Any]:
    return {
        "record_type": "p3_v3_successor_route_ledger",
        "seal_sha256": sha(SEAL),
        "approval_sha256": sha(APPROVAL),
        "source_ledger_sha256": sha(packet_builder.LEDGER),
        "prior_codex_tokens": PRIOR_OBSERVED_CODEX_TOKENS,
    }


def _runtime_state() -> dict[str, Any]:  # noqa: C901, PLR0912
    path = RUNTIME_ROOT / "route-events.jsonl"
    state: dict[str, Any] = {"routes": {}, "codex_tokens": PRIOR_OBSERVED_CODEX_TOKENS}
    if not path.exists():
        return state
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != PRIVATE_FILE_MODE:
        raise RouteError("route ledger is linked or nonprivate")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not rows or rows[0] != _ledger_header():
        raise RouteError("route ledger header or prior V3 binding changed")
    previous = _digest(rows[0])
    for sequence, row in enumerate(rows[1:], 1):
        body = {key: value for key, value in row.items() if key != "event_sha256"}
        if (
            row.get("seq") != sequence
            or row.get("previous_sha256") != previous
            or row.get("event_sha256") != _digest(body)
        ):
            raise RouteError("route ledger hash chain is invalid")
        previous = row["event_sha256"]
        route = row.get("route")
        if route not in ROUTES:
            raise RouteError("route ledger names an unknown route")
        if row.get("event") == "reserved":
            if route in state["routes"]:
                raise RouteError("route ledger has duplicate reservation")
            state["routes"][route] = {
                "status": "reserved",
                "attempt_id": row.get("attempt_id"),
                "approval_sha256": row.get("approval_sha256"),
                "packet_sha256": row.get("packet_sha256"),
                "seal_sha256": row.get("seal_sha256"),
            }
        elif row.get("event") == "completed":
            entry = state["routes"].get(route)
            if not entry or entry["status"] != "reserved" or entry["attempt_id"] != row.get("attempt_id"):
                raise RouteError("route completion has no unique reservation")
            if row.get("status") not in {"passed", "failed"}:
                raise RouteError("route completion status is invalid")
            entry["status"] = row["status"]
            entry["usage"] = row.get("usage")
            if route == "codex":
                usage = row.get("usage")
                if usage is None:
                    state["codex_usage_unknown"] = True
                else:
                    state["codex_tokens"] += usage["input_tokens"] + usage["output_tokens"]
        else:
            raise RouteError("route ledger has an unknown event")
    return state


def _append_event(event: dict[str, Any]) -> None:
    path = RUNTIME_ROOT / "route-events.jsonl"
    if not path.exists():
        _write_new(path, (json.dumps(_ledger_header(), sort_keys=True) + "\n").encode())
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    previous = rows[-1].get("event_sha256", _digest(rows[-1]))
    body = {"seq": len(rows), "previous_sha256": previous, **event}
    row = {**body, "event_sha256": _digest(body)}
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    with os.fdopen(fd, "wb") as stream:
        stream.write((json.dumps(row, sort_keys=True) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def _lock() -> int:
    _ensure_runtime()
    fd = os.open(RUNTIME_ROOT / "route-events.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    if stat.S_IMODE(os.fstat(fd).st_mode) != PRIVATE_FILE_MODE:
        os.close(fd)
        raise RouteError("route lock is nonprivate")
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _reserve(route: str, manifest: dict[str, Any], approval: dict[str, Any]) -> str:
    lock = _lock()
    try:
        state = _runtime_state()
        if state["routes"].get(route) or any(row.get("status") != "passed" for row in state["routes"].values()):
            raise RouteError("route was already attempted or a prior route failed")
        if state["codex_tokens"] >= CODEX_LIMIT or state.get("codex_usage_unknown"):
            raise RouteError("V3 Codex usage state blocks dispatch")
        attempt_id = uuid.uuid4().hex
        _append_event(
            {
                "event": "reserved",
                "route": route,
                "attempt_id": attempt_id,
                "approval_sha256": sha(APPROVAL),
                "packet_sha256": manifest["packet_sha256"],
                "opaque_packet_id": manifest["opaque_packet_id"],
                "seal_sha256": approval["operational_seal_sha256"],
            }
        )
        return attempt_id
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def _finish(route: str, attempt_id: str, *, status: str, usage: dict[str, int] | None) -> None:
    lock = _lock()
    try:
        state = _runtime_state()
        entry = state["routes"].get(route)
        if not isinstance(entry, dict) or entry.get("attempt_id") != attempt_id or entry.get("status") != "reserved":
            raise RouteError("route completion has no live reservation")
        _append_event(
            {
                "event": "completed",
                "route": route,
                "attempt_id": attempt_id,
                "status": status,
                "usage": usage,
            }
        )
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def _prepare_codex_home() -> Path:
    home = RUNTIME_ROOT / "codex-home"
    if home.exists():
        auth = home / "auth.json"
        if (
            home.is_symlink()
            or stat.S_IMODE(home.stat().st_mode) != PRIVATE_DIR_MODE
            or auth.is_symlink()
            or not auth.is_file()
            or stat.S_IMODE(auth.stat().st_mode) != PRIVATE_FILE_MODE
        ):
            raise RouteError("isolated Codex home is invalid")
        return home
    source = packet_builder.SOURCE_ROOT / "codex-home-run" / "auth.json"
    if source.is_symlink() or not source.is_file():
        raise RouteError("source account credential is unavailable")
    home.mkdir(mode=0o700)
    _write_new(home / "auth.json", source.read_bytes())
    return home


def dispatch(route: str) -> int:  # noqa: C901, PLR0912, PLR0915
    """Make at most one one-shot provider call after exact phase and quota gates."""
    if route not in ROUTES:
        raise RouteError("unknown route")
    approval = validate_approval(dispatch=True)
    preflight = _read(PREFLIGHT)
    if (
        preflight.get("status") != "PASSED_OFFLINE_ROUTE_PREFLIGHT"
        or preflight.get("operational_seal_sha256") != sha(SEAL)
        or preflight.get("provider_calls") != 0
    ):
        raise RouteError("route offline preflight does not bind this seal")
    manifest, packet, prompt, ids = validate_packet()
    helper = _helper()
    request = helper.make_request(prompt, packet)
    _ensure_runtime()
    state = _runtime_state()
    if state.get("codex_usage_unknown"):
        raise RouteError("unknown V3 Codex usage locks route dispatch")
    executable = str(CODEX_EXECUTABLE if route == "codex" else shutil.which("qwen") or "")
    if not executable or not Path(executable).is_file():
        raise RouteError("pinned scorer executable unavailable")
    scratch = RUNTIME_ROOT / ("scratch-" + route)
    scratch.mkdir(mode=0o700, exist_ok=False)
    environment = os.environ.copy()
    session_id = str(uuid.uuid4()) if route == "qwen" else ""
    before_ids: set[str] = set()
    usage_path = Path.home() / ".qwen" / "usage_record.jsonl"
    secret = ""
    if route == "codex":
        home = _prepare_codex_home()
        environment["CODEX_HOME"] = str(home.resolve())
        child_env = helper._child_environment(route, environment)
        snapshot = quota.read_quota_snapshot(codex_executable=executable, codex_home=home, environment=child_env)
        quota.checkpoint_decision(snapshot)
        source_receipt = _read(packet_builder.RECORD).get("account_limit_receipt", {})
        current_receipt = snapshot.get("account_limit_receipt", {})
        if current_receipt.get("account_id_sha256") != source_receipt.get("account_id_sha256") or current_receipt.get(
            "codex_executable_sha256"
        ) != source_receipt.get("codex_executable_sha256"):
            raise RouteError("Codex account or executable differs from the source phase")
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False, timeout=10)
        if version.returncode or version.stdout.strip() != "codex-cli 0.156.1":
            raise RouteError("Codex CLI version differs from pin")
        command = helper._codex_command(executable, scratch)
    else:
        gateway, overlay, _meta = helper._qwen_preflight(Path.home(), environment)
        parsed_gateway = urlsplit(gateway)
        if (
            parsed_gateway.scheme != "https"
            or not parsed_gateway.hostname
            or parsed_gateway.username
            or parsed_gateway.password
            or parsed_gateway.query
            or parsed_gateway.fragment
        ):
            raise RouteError("Qwen gateway URL contains unsupported or sensitive components")
        secret = environment["LITE_LLM_AUTH_TOKEN"]
        child_env = helper._child_environment(route, environment, auth_token=secret)
        settings_file = RUNTIME_ROOT / "qwen-system-settings.json"
        _write_json(settings_file, overlay)
        child_env["QWEN_CODE_SYSTEM_SETTINGS_PATH"] = str(settings_file)
        child_env["QWEN_CODE_MAX_OUTPUT_TOKENS"] = "2000"
        child_env["QWEN_CODE_UNATTENDED_RETRY"] = "0"
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False, timeout=10)
        if version.returncode or not helper._version_matches(version.stdout, "0.24.7"):
            raise RouteError("Qwen CLI version differs from pin")
        command = helper._qwen_command(executable, gateway, session_id)
        if usage_path.exists():
            for line in usage_path.read_text(encoding="utf-8").splitlines():
                try:
                    prior = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if prior.get("project") == str(scratch):
                    before_ids.add(str(prior.get("sessionId")))
    attempt_id = _reserve(route, manifest, approval)
    evidence = RUNTIME_ROOT / attempt_id
    evidence.mkdir(mode=0o700)
    _write_json(
        evidence / "prepared.json",
        {
            "route": route,
            "attempt_id": attempt_id,
            "approval_sha256": sha(APPROVAL),
            "seal_sha256": sha(SEAL),
            "packet_sha256": manifest["packet_sha256"],
            "request_sha256": hashlib.sha256(request).hexdigest(),
            "scored_p3": False,
            "qualification_data": False,
        },
    )
    if route == "codex":
        _write_json(evidence / "quota-before.json", snapshot)
    usage: dict[str, int] | None = None
    status = "failed"
    try:
        process = helper.invoke_one_provider_process(command, request, scratch, child_env)
        stdout = helper.secure_capture(process.stdout, secret)
        stderr = helper.secure_capture(process.stderr, secret)
        _write_new(evidence / "stdout.raw", stdout)
        _write_new(evidence / "stderr.raw", stderr)
        events = helper.parse_jsonl(stdout)
        _write_json(evidence / "events.json", events)
        if route == "codex":
            usage = helper.usage_from_events(events)
            thread_ids = helper.event_session_ids(events)
            if len(thread_ids) != 1:
                raise RouteError("Codex session correlation is ambiguous")
            session_id = next(iter(thread_ids))
            rollout, session = helper.codex_rollout(home, session_id)
            _write_new(evidence / "rollout.jsonl", rollout)
            if session.get("cwd") != str(scratch):
                raise RouteError("Codex scratch cwd differs from persisted session")
        else:
            if helper.event_session_ids(events) != {session_id}:
                raise RouteError("Qwen session correlation failed")
            qwen = helper.qwen_usage_record(usage_path, str(scratch), session_id, before_ids)
            usage = {"input_tokens": qwen["input_tokens"], "output_tokens": qwen["output_tokens"]}
        reply = helper.final_text(events)
        _write_new(evidence / "reply.tsv", reply.encode())
        helper.validate_tsv(reply, manifest["opaque_packet_id"], ids)
        if (
            process.returncode != 0
            or helper.tool_markers(events)
            or helper.cli_retry_error_markers(events, stderr)
            or usage["input_tokens"] > INPUT_LIMIT
            or usage["output_tokens"] > OUTPUT_LIMITS[route]
        ):
            raise RouteError("route response failed observed mechanics conditions")
        status = "passed"
    except Exception as exc:  # noqa: BLE001 - retain terminal failed attempt
        _write_json(evidence / "failure.json", {"kind": type(exc).__name__, "status": "failed"})
    finally:
        _finish(route, attempt_id, status=status, usage=usage)
        _write_json(
            evidence / "outcome.json",
            {
                "status": status,
                "route": route,
                "usage": usage,
                "scored_p3": False,
                "qualification_data": False,
            },
        )
    return 0 if status == "passed" else 1


def main() -> int:
    """Keep offline checks and provider dispatch as explicit separate commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "dispatch"))
    parser.add_argument("--route", choices=ROUTES)
    args = parser.parse_args()
    if args.action == "preflight":
        print(json.dumps(offline_preflight(), sort_keys=True))
        return 0
    if args.route is None:
        parser.error("dispatch requires --route")
    return dispatch(args.route)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - don't leak packet or credential context
        print(json.dumps({"status": "DISPATCH_BLOCKED", "reason_class": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2) from None
