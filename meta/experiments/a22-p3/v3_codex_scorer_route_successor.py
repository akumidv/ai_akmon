#!/usr/bin/env python3
"""Default-deny, one-shot Codex scorer mechanics check on the current CLI."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import quota_adapter_v3 as quota
import v3_controls_successor as controls
import v3_successor_route_check as old_route

HERE = Path(__file__).resolve().parent
PROPOSAL = HERE / "V3_CODEX_SCORER_ROUTE_SUCCESSOR_PROPOSAL.md"
SEAL = HERE / "runs" / "v3-codex-scorer-route-successor-seal-v1.json"
APPROVAL = HERE / "runs" / "v3-codex-scorer-route-successor-approval-v1.json"
ACCEPTANCE = HERE / "runs" / "v3-codex-scorer-route-successor-acceptance-v1.json"
PREFLIGHT = HERE / "runs" / "v3-codex-scorer-route-successor-preflight-v1.json"
RUNTIME = Path("/tmp/a22-p3-v3-codex-scorer-route-successor-runtime")  # noqa: S108
EXECUTABLE = Path("/home/ai/.codex/packages/standalone/releases/0.162.1-x86_64-unknown-linux-musl/bin/codex")
AUTH_SOURCE = Path("/tmp/a22-p3-v3-successor-9xViiq/codex-home-run/auth.json")  # noqa: S108
CONTROL_LEDGER = Path("/tmp/a22-p3-v3-controls-successor-runtime/control-events.jsonl")  # noqa: S108
CONTROL_MANIFEST = HERE / "runs" / "v3-controls-successor-evidence" / "manifest.json"
OPENING = 202_220
LIMIT = 5_000_000
CLI_VERSION = "0.162.1"
MODEL = "gpt-6-astra"
EFFORT = "medium"
ACCOUNT_ID_SHA = "dc17f02443f35278c2d94b94ee471ee5dc9f10e499726ea3d92d591eecdab320"
CONTROL_CALLS = 6
INPUT_LIMIT = 20_000
OUTPUT_LIMIT = 1_000


class RouteError(ValueError):
    """The exact successor route gate or its evidence failed."""


def sha(path: Path) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    """Read a JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value: bytes) -> None:
    """Create private evidence without replacing an existing artifact."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, value: Any) -> None:
    """Write canonical, private JSON once."""
    write_new(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def seal_body() -> dict[str, Any]:
    """Recompute all stable inputs without dispatching a provider."""
    packet = old_route.PACKET_ROOT / "visible" / "packet.md"
    manifest = old_route.PACKET_ROOT / "evaluator" / "manifest.json"
    sources = (
        "v3_codex_scorer_route_successor.py",
        "v3_successor_route_check.py",
        "scorer_route_check.py",
        "v3_successor_route_packet.py",
        "v3_controls_successor.py",
        "quota_adapter_v3.py",
    )
    return {
        "schema": 1,
        "record_type": "p3_v3_codex_scorer_route_successor_seal",
        "scope": ["codex_scorer_route_check"],
        "status": "offline_candidate_pending_owner_acceptance",
        "provider_calls_started": 0,
        "opening_codex_tokens": OPENING,
        "codex_limit_tokens": LIMIT,
        "cli_version": CLI_VERSION,
        "model": MODEL,
        "effort": EFFORT,
        "pinned_executable": str(EXECUTABLE),
        "pinned_executable_sha256": sha(EXECUTABLE),
        "proposal_sha256": sha(PROPOSAL),
        "packet_sha256": sha(packet),
        "packet_manifest_sha256": sha(manifest),
        "prompt_sha256": sha(HERE / "scoring" / "scorer-prompt.txt"),
        "prior_route_seal_sha256": sha(HERE / "runs" / "successor-route-check-seal-v6.json"),
        "prior_route_approval_sha256": sha(HERE / "runs" / "successor-route-check-approval-v6.json"),
        "controls_seal_sha256": sha(HERE / "runs" / "v3-controls-successor-seal-v1.json"),
        "controls_approval_sha256": sha(HERE / "runs" / "v3-controls-successor-approval-v1.json"),
        "controls_ledger_sha256": sha(CONTROL_LEDGER),
        "controls_manifest_sha256": sha(CONTROL_MANIFEST),
        "historical_receipt_sha256": sha(HERE / "runs" / "v3-historical-usage-reconciliation-v1.json"),
        "source_sha256": {name: sha(HERE / name) for name in sources},
        "regression_sha256": sha(HERE.parents[1] / "tests" / "test_a22_p3_v3_codex_scorer_route_successor.py"),
    }


def verify_seal() -> dict[str, Any]:
    """Reject any changed sealed input or wrong predecessor balance."""
    actual = read(SEAL)
    if actual != seal_body():
        raise RouteError("successor route seal is stale or malformed")
    controls = read(CONTROL_MANIFEST)
    if not isinstance(controls.get("files"), list) or not controls["files"]:
        raise RouteError("control evidence manifest is malformed")
    rows = controls_module_rows()
    if len(rows) != 1 + 2 * CONTROL_CALLS or sum(row.get("event") == "completed" for row in rows) != CONTROL_CALLS:
        raise RouteError("control ledger does not contain six completed calls")
    debits = [row for row in rows if row.get("event") == "completed"]
    if not all(
        row.get("outcome") == "accepted"
        and row.get("usage_status") == "known"
        and isinstance(row.get("input_tokens"), int)
        and isinstance(row.get("output_tokens"), int)
        for row in debits
    ):
        raise RouteError("control usage is incomplete")
    total = 74_257 + sum(u["input_tokens"] + u["output_tokens"] for u in debits)
    if total != OPENING:
        raise RouteError("successor route opening balance differs")
    return actual


def controls_module_rows() -> list[dict[str, Any]]:
    """Use the completed controls' hash-chain validator."""
    if controls.LEDGER != CONTROL_LEDGER:
        raise RouteError("control ledger path differs")
    return controls._rows()


def approval_template() -> dict[str, Any]:
    """An absent owner decision is a hard denial."""
    return {
        "schema": 1,
        "record_type": "p3_v3_codex_scorer_route_successor_approval",
        "operational_seal_sha256": sha(SEAL),
        "owner_accepted": False,
        "dispatch_allowed": False,
        "authorized_phases": [],
        "named_stop_operator": None,
        "acceptance_evidence_sha256": None,
        "preflight_report_sha256": None,
        "retry_evidence_policy": "OBSERVED_NO_RETRY",
    }


def expected_owner_reply() -> str:
    """The exact, independently checkable phase authorization text."""
    return f"Подтверждаю codex_scorer_route_check для seal SHA-256 {sha(SEAL)}; оператор остановки — я."


def verify_approval(*, dispatch: bool) -> dict[str, Any]:
    """Require exact owner acceptance only at dispatch."""
    actual = read(APPROVAL)
    expected = approval_template()
    if not dispatch and actual == expected:
        return actual
    if not ACCEPTANCE.is_file():
        raise RouteError("owner acceptance evidence is absent")
    required = {
        **expected,
        "owner_accepted": True,
        "dispatch_allowed": True,
        "authorized_phases": ["codex_scorer_route_check"],
        "named_stop_operator": "owner (current chat session)",
        "acceptance_evidence_sha256": sha(ACCEPTANCE),
        "preflight_report_sha256": sha(PREFLIGHT),
    }
    if actual != required:
        raise RouteError("exact successor route approval is absent")
    evidence = read(ACCEPTANCE)
    if (
        evidence.get("record_type") != "p3_v3_codex_scorer_route_successor_acceptance"
        or evidence.get("accepted_seal_sha256") != sha(SEAL)
        or evidence.get("scope") != ["codex_scorer_route_check"]
        or evidence.get("stop_operator") != "owner (current chat session)"
        or sha(SEAL) not in evidence.get("request_text", "")
        or "codex_scorer_route_check" not in evidence.get("request_text", "")
        or not evidence.get("request_message_id")
        or not evidence.get("user_message_id")
        or evidence.get("raw_user_text") != expected_owner_reply()
    ):
        raise RouteError("successor route acceptance evidence is invalid")
    return actual


def offline_preflight() -> dict[str, Any]:
    """Check readiness without provider or quota calls."""
    seal = verify_seal()
    verify_approval(dispatch=False)
    manifest, packet, prompt, ids = old_route.validate_packet()
    if ids != ["E1", "E2", "E3", "E4"] or sha(old_route.PACKET_ROOT / "visible" / "packet.md") != seal["packet_sha256"]:
        raise RouteError("blinded packet differs")
    if hashlib.sha256(prompt).hexdigest() != seal["prompt_sha256"] or not packet:
        raise RouteError("scorer prompt differs")
    if manifest.get("scored_p3") is not False or manifest.get("qualification_data") is not False:
        raise RouteError("route packet is not unscored")
    if not AUTH_SOURCE.is_file() or AUTH_SOURCE.is_symlink() or stat.S_IMODE(AUTH_SOURCE.stat().st_mode) & 0o077:
        raise RouteError("private Codex authentication source is unavailable")
    if RUNTIME.is_symlink() or RUNTIME.exists() or RUNTIME.resolve() == HERE or HERE in RUNTIME.resolve().parents:
        raise RouteError("route runtime is already used or not isolated")
    version = subprocess.run([str(EXECUTABLE), "--version"], capture_output=True, text=True, check=False, timeout=10)
    if version.returncode or version.stdout.strip() != f"codex-cli {CLI_VERSION}":
        raise RouteError("Codex CLI version differs from pin")
    return {
        "status": "PASSED_OFFLINE_ROUTE_PREFLIGHT",
        "operational_seal_sha256": sha(SEAL),
        "packet_sha256": seal["packet_sha256"],
        "prompt_sha256": seal["prompt_sha256"],
        "opening_codex_tokens": OPENING,
        "provider_calls": 0,
        "dispatch_allowed": False,
    }


def _rollout(home: Path, session_id: str, scratch: Path, usage: dict[str, int], helper: Any) -> bytes:
    """Correlate one CLI turn with one persisted current-version session."""
    paths = list((home / "sessions").rglob("rollout-*.jsonl"))
    if len(paths) != 1 or paths[0].is_symlink():
        raise RouteError("Codex rollout is absent or ambiguous")
    raw = paths[0].read_bytes()
    rows = helper.parse_jsonl(raw)
    metas = [r.get("payload", {}) for r in rows if r.get("type") == "session_meta"]
    turns = [r.get("payload", {}) for r in rows if r.get("type") == "turn_context"]
    tokens = [r.get("payload", {}) for r in rows if r.get("type") == "token_usage_record"]
    if (
        len(metas) != 1
        or metas[0].get("id") != session_id
        or metas[0].get("cli_version") not in {CLI_VERSION, f"codex-cli {CLI_VERSION}"}
        or Path(str(metas[0].get("cwd", ""))).resolve() != scratch
        or len(turns) != 1
        or turns[0].get("model") != MODEL
        or turns[0].get("effort") != EFFORT
        or len(tokens) != 1
        or tokens[0].get("session_id") != session_id
        or tokens[0].get("turn_id") != turns[0].get("turn_id")
        or any(tokens[0].get("thread_token_usage", {}).get(k) != v for k, v in usage.items())
        or helper.tool_markers(rows)
        or helper.cli_retry_error_markers(rows, b"")
    ):
        raise RouteError("Codex rollout identity, usage or no-tool condition differs")
    return raw


def dispatch() -> int:  # noqa: PLR0915
    """Reserve one terminal attempt and invoke one provider process."""
    verify_seal()
    verify_approval(dispatch=True)
    preflight = read(PREFLIGHT)
    if (
        preflight.get("status") != "PASSED_OFFLINE_ROUTE_PREFLIGHT"
        or preflight.get("operational_seal_sha256") != sha(SEAL)
        or preflight.get("provider_calls") != 0
        or preflight.get("dispatch_allowed") is not False
        or preflight.get("opening_codex_tokens") != OPENING
    ):
        raise RouteError("offline preflight differs from exact seal")
    manifest, packet, prompt, ids = old_route.validate_packet()
    helper = old_route._helper()
    request = helper.make_request(prompt, packet)
    RUNTIME.mkdir(mode=0o700, exist_ok=False)
    home = RUNTIME / "codex-home"
    home.mkdir(mode=0o700)
    write_new(home / "auth.json", AUTH_SOURCE.read_bytes())
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(home)
    child = helper._child_environment("codex", environment)
    snapshot = quota.read_quota_snapshot(codex_executable=str(EXECUTABLE), codex_home=home, environment=child)
    quota.checkpoint_decision(snapshot)
    receipt = snapshot.get("account_limit_receipt", {})
    if receipt.get("account_id_sha256") != ACCOUNT_ID_SHA or receipt.get("codex_executable_sha256") != sha(EXECUTABLE):
        raise RouteError("Codex account or executable differs")
    if OPENING >= LIMIT or OPENING + INPUT_LIMIT + OUTPUT_LIMIT > LIMIT:
        raise RouteError("V3 Codex token ceiling blocks route")
    scratch = RUNTIME / "scratch"
    scratch.mkdir(mode=0o700)
    attempt_id = uuid.uuid4().hex
    ledger = RUNTIME / "route-events.jsonl"
    write_new(
        ledger,
        (
            json.dumps(
                {
                    "record_type": "p3_v3_codex_scorer_route_ledger",
                    "seal_sha256": sha(SEAL),
                    "approval_sha256": sha(APPROVAL),
                    "opening_codex_tokens": OPENING,
                },
                sort_keys=True,
            )
            + "\n"
        ).encode(),
    )
    lock_fd = os.open(RUNTIME / "route-events.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "event": "reserved",
                        "attempt_id": attempt_id,
                        "packet_sha256": manifest["packet_sha256"],
                        "request_sha256": hashlib.sha256(request).hexdigest(),
                    }
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    evidence = RUNTIME / attempt_id
    evidence.mkdir(mode=0o700)
    write_json(evidence / "quota-before.json", snapshot)
    write_json(
        evidence / "prepared.json",
        {
            "attempt_id": attempt_id,
            "seal_sha256": sha(SEAL),
            "request_sha256": hashlib.sha256(request).hexdigest(),
            "packet_sha256": manifest["packet_sha256"],
            "scored_p3": False,
            "qualification_data": False,
        },
    )
    usage: dict[str, int] | None = None
    status = "failed"
    try:
        command = helper._codex_command(str(EXECUTABLE), scratch)
        process = helper.invoke_one_provider_process(command, request, scratch, child)
        stdout = helper.secure_capture(process.stdout, "")
        stderr = helper.secure_capture(process.stderr, "")
        write_new(evidence / "stdout.raw", stdout)
        write_new(evidence / "stderr.raw", stderr)
        events = helper.parse_jsonl(stdout)
        write_json(evidence / "events.json", events)
        usage = helper.usage_from_events(events)
        sessions = helper.event_session_ids(events)
        if len(sessions) != 1:
            raise RouteError("CLI session correlation is ambiguous")
        session_id = next(iter(sessions))
        write_new(evidence / "rollout.jsonl", _rollout(home, session_id, scratch, usage, helper))
        reply = helper.final_text(events)
        write_new(evidence / "reply.tsv", reply.encode())
        helper.validate_tsv(reply, manifest["opaque_packet_id"], ids)
        if (
            process.returncode != 0
            or helper.tool_markers(events)
            or helper.cli_retry_error_markers(events, stderr)
            or usage["input_tokens"] > INPUT_LIMIT
            or usage["output_tokens"] > OUTPUT_LIMIT
        ):
            raise RouteError("route response failed observed mechanics conditions")
        status = "passed"
    except Exception as exc:  # noqa: BLE001 - the one attempt remains terminal
        write_json(evidence / "failure.json", {"status": "failed", "kind": type(exc).__name__})
    finally:
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {"event": "completed", "attempt_id": attempt_id, "status": status, "usage": usage}, sort_keys=True
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        write_json(
            evidence / "outcome.json",
            {"status": status, "usage": usage, "scored_p3": False, "qualification_data": False},
        )
    return 0 if status == "passed" else 1


def main() -> int:
    """Expose separate offline and provider actions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "dispatch"))
    args = parser.parse_args()
    if args.action == "preflight":
        print(json.dumps(offline_preflight(), sort_keys=True))
        return 0
    return dispatch()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - do not print private packet or auth details
        print(json.dumps({"status": "DISPATCH_BLOCKED", "reason_class": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2) from None
