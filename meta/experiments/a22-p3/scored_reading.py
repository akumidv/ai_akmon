#!/usr/bin/env python3
"""One-shot V2 P3 scorer reading for a verified opaque packet.

The runner reuses the frozen request, route pins, environment controls, CLI
parsers, usage extraction, and ledger evidence helpers from scorer_route_check.
It never reads or sends evaluator-map.json to a provider.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
PRIVATE_DIR_MODE = 0o700


def _route_core() -> Any:
    path = HERE / "scorer_route_check.py"
    spec = importlib.util.spec_from_file_location("a22_p3_scored_route_core", path)
    if spec is None or spec.loader is None:
        raise ValueError("shared scorer route core is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_ledger() -> Any:
    path = HERE / "usage_ledger_v2.py"
    spec = importlib.util.spec_from_file_location("a22_p3_scored_usage_ledger", path)
    if spec is None or spec.loader is None:
        raise ValueError("shared usage ledger is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _private_dir(path: Path) -> None:
    path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=False)
    path.chmod(PRIVATE_DIR_MODE)
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != PRIVATE_DIR_MODE:
        raise ValueError("private scorer evidence directory permissions are invalid")


def _write_record(core: Any, path: Path, value: dict[str, Any]) -> None:
    core.write_json(path, value)


def dispatch(route: str, packet_dir: Path, evaluator_dir: Path) -> int:  # noqa: C901, PLR0912, PLR0915
    """Reserve and perform exactly one authorized scored reading."""
    core = _route_core()
    ledger = _load_ledger()
    reserved: str | None = None
    evidence_dir: Path | None = None
    process_invocations = 0
    actual_usage: dict[str, int] | None = None
    usage_artifact: dict[str, str] | None = None
    failure_code: str | None = "attempt_failed"
    outcome = "failed"
    final_status = "FAILED_CLOSED"
    session_id = ""
    session: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    reply = ""
    process_returncode: int | None = None
    tool_calls: list[str] = []
    retry_policy = "UNSELECTED"
    retry_markers: list[str] = []
    secret = ""
    try:
        # This canonical gate checks both route-check acceptance and qualification
        # approval before inspecting or starting a provider CLI.
        ledger.require_dispatch_authorization(paths=ledger.DEFAULT_PATHS, phase="qualification")
        retry_policy = ledger.approved_retry_evidence_policy(
            paths=ledger.DEFAULT_PATHS, phase="qualification")
        if retry_policy != "OBSERVED_NO_RETRY":
            raise ValueError("retry evidence policy is not selected")
        manifest, packet, prompt, element_ids = core.validate_bundle(packet_dir, evaluator_dir)
        request = core.make_request(prompt, packet)
        settings = core._model_settings(route)
        attempt_id = uuid.uuid4().hex
        executable = shutil.which(settings["executable"])
        if executable is None:
            raise ValueError("pinned scorer CLI is unavailable")

        # Reservation occurs before any CLI process, including the version probe.
        reserved = ledger.reserve_attempt(route, "scored_reading", paths=ledger.DEFAULT_PATHS,
                                          attempt_id=attempt_id,
                                          opaque_packet_id=manifest["opaque_packet_id"],
                                          packet_sha256=core.sha(packet))
        evidence_dir = RUNS / "scored-readings" / reserved
        evidence_dir.parent.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
        if evidence_dir.parent.is_symlink() or stat.S_IMODE(evidence_dir.parent.stat().st_mode) != PRIVATE_DIR_MODE:
            raise ValueError("scored-reading evidence root permissions are invalid")
        _private_dir(evidence_dir)
        request_id = f"p3-scored-reading-{reserved}"
        record: dict[str, Any] = {
            "schema": 1, "record_type": "p3_scored_reading", "status": "reserved",
            "attempt_id": reserved, "request_id": request_id, "route": route,
            "opaque_packet_id": manifest["opaque_packet_id"],
            "packet_sha256": core.sha(packet), "request_sha256": core.sha(request),
            "prompt_sha256": core.sha(prompt), "model_requested": settings["model"],
            "output_limit": core.OUTPUT_CAP[route], "input_observed_limit": core.INPUT_CAP,
            "retry_evidence_policy": retry_policy,
            "provider_process_invocations_planned": 1, "retry_count": None,
            "scored_p3": True, "qualification_data": True,
        }
        _write_record(core, evidence_dir / "attempt.json", record)

        parent_env = os.environ.copy()
        child_env = core._child_environment(route, parent_env)
        version_result = subprocess.run([executable, "--version"], env=child_env,
                                         capture_output=True, timeout=10, check=False)
        version_text = (version_result.stdout + version_result.stderr).decode(
            "utf-8", errors="replace").strip()
        if version_result.returncode != 0 or not core._version_matches(version_text, settings["version"]):
            raise ValueError("pinned scorer CLI version mismatch")
        scratch_root = Path(tempfile.gettempdir()) / "akmon-p3-scored-reading"
        scratch_root.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
        if scratch_root.is_symlink():
            raise ValueError("scratch root cannot be a symlink")
        scratch = scratch_root / reserved
        scratch.mkdir(mode=PRIVATE_DIR_MODE, exist_ok=False)

        settings_meta: dict[str, Any] = {}
        usage_path: Path | None = None
        before_ids: set[str] = set()
        if route == "qwen":
            gateway, overlay, settings_meta = core._qwen_preflight(Path.home(), parent_env)
            secret = parent_env["LITE_LLM_AUTH_TOKEN"]
            child_env = core._child_environment(route, parent_env, auth_token=secret)
            settings_file = scratch_root / f"{reserved}.system-settings.json"
            core.private_write(settings_file, (json.dumps(overlay, sort_keys=True, indent=2) + "\n").encode())
            child_env["QWEN_CODE_SYSTEM_SETTINGS_PATH"] = str(settings_file)
            child_env["QWEN_CODE_MAX_OUTPUT_TOKENS"] = str(core.OUTPUT_CAP["qwen"])
            child_env["QWEN_CODE_UNATTENDED_RETRY"] = "0"
            usage_path = Path.home() / ".qwen/usage_record.jsonl"
            if usage_path.exists():
                for line in usage_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        previous = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(previous, dict) and previous.get("project") == str(scratch):
                        before_ids.add(str(previous.get("sessionId")))
            session_id = str(uuid.uuid4())
            command = core._qwen_command(executable, gateway, session_id)
        else:
            command = core._codex_command(executable, scratch)

        record.update({"status": "invoking", "cli_version": version_text,
                       "settings": settings_meta,
                       "retry_evidence_policy": retry_policy,
                       "argv_redacted": core._redacted_argv(route, executable, scratch, session_id)})
        _write_record(core, evidence_dir / "attempt.json", record)
        try:
            process = core.invoke_one_provider_process(command, request, scratch, child_env)
            process_invocations = 1
            process_returncode = process.returncode
            stdout = core.secure_capture(process.stdout, secret)
            stderr = core.secure_capture(process.stderr, secret)
            core.private_write(evidence_dir / "stdout.raw", stdout)
            core.private_write(evidence_dir / "stderr.raw", stderr)
            events = core.parse_jsonl(stdout)
            _write_record(core, evidence_dir / "events.json", events)
            if route == "codex":
                session_ids = {row["thread_id"] for row in events if isinstance(row.get("thread_id"), str)}
                if len(session_ids) != 1:
                    raise ValueError("Codex thread id is not uniquely correlated")
                session_id = next(iter(session_ids))
                actual_usage = core.usage_from_events(events)
                codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
                rollout, session = core.codex_rollout(codex_home, session_id)
                core.private_write(evidence_dir / "rollout.jsonl", core.secure_capture(rollout, secret))
                if session.get("cwd") != str(scratch):
                    raise ValueError("Codex persisted session cwd does not match isolated scratch")
                if len([row for row in events if row.get("type") == "turn.completed"]) != 1:
                    raise ValueError("Codex terminal turn cardinality is not one")
            else:
                if core.event_session_ids(events) != {session_id}:
                    raise ValueError("Qwen event session does not match the one-shot request")
                qwen = core.qwen_usage_record(usage_path, str(scratch), session_id, before_ids)
                actual_usage = {"input_tokens": qwen["input_tokens"], "output_tokens": qwen["output_tokens"]}
                session = {"session_id": session_id, "model_id": qwen["model_id"],
                           "requests": qwen["requests"], "tool_calls": qwen["tool_calls"]}
            reply = core.final_text(events)
            if process.returncode != 0:
                raise ValueError("scorer CLI exited unsuccessfully")
            tool_calls = core.tool_markers(events)
            if tool_calls:
                raise ValueError("tool activity was observed")
            retry_markers = core.validate_retry_evidence(
                retry_policy, route, events, stderr, process_invocations,
                settings_meta, session, command)
            if retry_markers:
                raise ValueError("CLI-visible retry or error marker was observed")
            core.validate_tsv(reply, manifest["opaque_packet_id"], element_ids)
            if actual_usage["input_tokens"] > core.INPUT_CAP or actual_usage["output_tokens"] > core.OUTPUT_CAP[route]:
                failure_code = "per_call_limit_breach"
                raise ValueError("observed provider usage exceeds route allowance")
            core.private_write(evidence_dir / "final.tsv", reply.encode("utf-8"))
            final_status = "SCORED_READING_ACCEPTED"
            outcome = "accepted"
            failure_code = None
        except subprocess.TimeoutExpired as exc:
            process_invocations = 1
            core.private_write(evidence_dir / "stdout.raw", core.secure_capture(exc.stdout or b"", secret))
            core.private_write(evidence_dir / "stderr.raw", core.secure_capture(exc.stderr or b"", secret))
            failure_code = "missing_usage"
            final_status = "FAILED_CLOSED_UNCERTAIN_PROVIDER_OUTCOME"
        except core.ProviderStartError as exc:
            del exc
            failure_code = "missing_usage"
            final_status = "FAILED_CLOSED_PROCESS_START"
        except Exception as exc:  # noqa: BLE001 - provider text must not reach operator output
            record["failure_kind"] = type(exc).__name__
            if actual_usage is None:
                failure_code = "missing_usage" if process_invocations else "attempt_failed"
            record["failure_code"] = failure_code
            final_status = "FAILED_CLOSED"
        finally:
            correlation_ok = bool(actual_usage and session_id and session.get("model_id") == settings["model"])
            ledger_usage = actual_usage if correlation_ok else None
            if actual_usage and not correlation_ok:
                failure_code, outcome = "missing_usage", "failed"
                final_status = "FAILED_CLOSED_USAGE_UNCORRELATED"
            if correlation_ok:
                usage_dir = RUNS / "usage-artifacts"
                try:
                    usage_dir.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
                    if usage_dir.is_symlink() or stat.S_IMODE(usage_dir.stat().st_mode) != PRIVATE_DIR_MODE:
                        raise ValueError("usage artifact directory permissions are invalid")
                    usage_evidence = {
                        "opaque_packet_id": manifest["opaque_packet_id"],
                        "packet_sha256": core.sha(packet), "request_sha256": core.sha(request),
                        "request_id_provenance": "runner-generated; linked to exact stdin hash and one CLI process",
                        "process_returncode": process_returncode,
                        "provider_process_invocations": process_invocations,
                        "retry_count": None, "retry_evidence_policy": retry_policy,
                        "retry_observed_markers": retry_markers,
                        "retry_evidence": (
                            "OBSERVED_NO_RETRY passed at the CLI/session layer; provider transport retries "
                            "are not observable"
                            if final_status == "SCORED_READING_ACCEPTED" else
                            "CLI/session retry evidence is incomplete or failed; provider transport retries "
                            "are not observable"
                        ),
                        "tool_markers": tool_calls,
                        "session": session,
                        "tsv_sha256": core.sha(reply.encode("utf-8")) if reply else None,
                        "tsv_valid": final_status == "SCORED_READING_ACCEPTED",
                    }
                    usage_artifact = core._usage_artifact(
                        usage_dir / f"{reserved}.json", usage=actual_usage, call_id=reserved,
                        request_id=f"p3-scored-reading-{reserved}", session_id=session_id,
                        model_id=settings["model"], evidence=usage_evidence)
                except (OSError, ValueError):
                    ledger_usage, usage_artifact = None, None
                    failure_code, outcome = "missing_usage", "failed"
                    final_status = "FAILED_CLOSED_USAGE_ARTIFACT"
            if evidence_dir is not None:
                _write_record(core, evidence_dir / "outcome.json", {
                    # This complete response receipt is durable before the ledger
                    # can mark the reading accepted. The ledger completion event
                    # remains authoritative for the final accounting outcome.
                    "status": final_status, "ledger_outcome": "pending",
                    "intended_ledger_outcome": outcome,
                    "attempt_id": reserved, "request_id": f"p3-scored-reading-{reserved}",
                    "opaque_packet_id": manifest["opaque_packet_id"],
                    "session_id": session_id or None, "model_id": settings["model"],
                    "usage": ledger_usage, "observed_usage": actual_usage,
                    "usage_artifact": usage_artifact, "failure_code": failure_code,
                    "process_returncode": process_returncode, "tool_markers": tool_calls,
                    "retry_evidence_policy": retry_policy,
                    "retry_observed_markers": retry_markers,
                    "retry_evidence": (
                        "OBSERVED_NO_RETRY passed at the CLI/session layer; provider transport retries "
                        "are not observable"
                        if final_status == "SCORED_READING_ACCEPTED" else
                        "CLI/session retry evidence is incomplete or failed; provider transport retries "
                        "are not observable"
                    ),
                    "provider_process_invocations": process_invocations,
                    "retry_count": None, "tsv_sha256": core.sha(reply.encode()) if reply else None,
                    "tsv_valid": final_status == "SCORED_READING_ACCEPTED",
                    "scored_p3": final_status == "SCORED_READING_ACCEPTED",
                    "qualification_data": final_status == "SCORED_READING_ACCEPTED",
                })
            terminal = core.terminalize_attempt(
                ledger, reserved, outcome=outcome, actual_usage=ledger_usage,
                usage_artifact=usage_artifact, failure_code=failure_code)
            print(json.dumps({"status": final_status, "route": route,
                              "ledger_outcome": terminal["outcome"],
                              "opaque_packet_id": manifest["opaque_packet_id"],
                              "scored_p3": final_status == "SCORED_READING_ACCEPTED",
                              "qualification_data": final_status == "SCORED_READING_ACCEPTED"}))
        return 0 if final_status == "SCORED_READING_ACCEPTED" else 1  # noqa: TRY300
    except Exception as exc:  # noqa: BLE001 - fail closed without printing provider or packet details
        if reserved is not None:
            # Reservation is terminalized even if evidence setup fails before invocation.
            terminal = core.terminalize_attempt(ledger, reserved, outcome="failed", actual_usage=None,
                                                usage_artifact=None, failure_code="missing_usage")
            print(json.dumps({"status": "FAILED_CLOSED", "ledger_outcome": terminal["outcome"],
                              "reason_class": type(exc).__name__, "provider_process_invocations": process_invocations}))
        else:
            print(json.dumps({"status": "DISPATCH_BLOCKED", "reason_class": type(exc).__name__,
                              "provider_process_invocations": process_invocations}))
        return 2


def main() -> int:
    """Run the dispatch CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    run = parser.add_subparsers(dest="action", required=True).add_parser(
        "dispatch", help="make one approval-gated scored reading")
    run.add_argument("--route", choices=("codex", "qwen"), required=True)
    run.add_argument("--packet-dir", type=Path, required=True)
    run.add_argument("--evaluator-dir", type=Path, required=True)
    args = parser.parse_args()
    return dispatch(args.route, args.packet_dir, args.evaluator_dir)


if __name__ == "__main__":
    raise SystemExit(main())
