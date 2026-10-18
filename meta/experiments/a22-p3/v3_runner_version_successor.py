#!/usr/bin/env python3
"""Default-deny Codex runner for the V3 technical source exchange.

Importing this module is offline. A provider process is possible only through
``run_technical_source`` after V3 admission, and the CLI requires ``--execute``.
All artifacts and mutable Codex state must live outside the sealed experiment.
"""

# These evidence validators deliberately keep the protocol checks in one place.
# ruff: noqa: ANN202 BLE001 C901 D103 PERF401 PLR0912 PLR0913 PLR0915 RUF005 RUF059 S110 SIM102 SIM105 TRY300
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dispatch_v3
import lean_source_version_successor_v3 as lean_source_protocol_v3
import quota_adapter_v3
import source_phase_v3
import usage_ledger_version_successor_v3 as ledger

HERE = Path(__file__).resolve().parent
PACKET = HERE / "cases" / "P3-01.json"
ARM = HERE / "arms" / "A.architect.system.txt"
ARM_MANIFEST = HERE / "arms" / "manifest.json"
CLI_VERSION = "codex-cli 0.156.1"
MODEL = "gpt-6-astra"
EFFORT = "medium"
TURN_INPUT_CAP = 40_000
PROCESS_STOP_GRACE_SECONDS = 5
CHECK_RE = re.compile(r"^CHECK: ([A-Za-z0-9][A-Za-z0-9_-]*)$")
TOOL_MARKERS = {
    "function_call",
    "custom_tool_call",
    "local_shell_call",
    "web_search_call",
    "tool_search_call",
    "image_generation_call",
    "mcp_tool_call",
    "command_execution",
    "file_change",
    "computer_call",
    "tool_call",
}


class RunnerError(ValueError):
    """V3 runner refused dispatch or rejected provider evidence."""


def _sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _create(path: Path, value: Any) -> None:
    """Create immutable evidence; an existing path is always an error."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _create_bytes(path: Path, data: bytes) -> None:
    """Create raw process evidence without replacing prior bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)


def parse_events(text: str) -> list[dict[str, Any]]:
    """Parse Codex JSONL strictly and preserve every event for tool checks."""
    events = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RunnerError(f"Codex event line {line_no} is not JSON") from exc
        if not isinstance(event, dict):
            raise RunnerError(f"Codex event line {line_no} is not an object")
        events.append(event)
    if not events:
        raise RunnerError("Codex event stream is empty")
    return events


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def has_tool_use(events: list[dict[str, Any]]) -> bool:
    """Reject explicit tool calls/fields anywhere in provider events."""
    for event in events:
        for obj in _walk(event):
            for key, value in obj.items():
                if key in {"tool_name", "tool_call_id"} and value:
                    return True
                if key in {"type", "event_type", "kind"} and isinstance(value, str):
                    marker = value.lower()
                    if (
                        marker in TOOL_MARKERS
                        or "tool_call" in marker
                        or "function_call" in marker
                        or "computer_call" in marker
                        or marker.endswith(".tool")
                    ):
                        return True
    return False


def thread_id(events: list[dict[str, Any]]) -> str:
    found = set()
    for event in events:
        for obj in _walk(event):
            for key in ("thread_id", "session_id"):
                value = obj.get(key)
                if isinstance(value, str) and value:
                    found.add(value)
            if obj.get("type") == "session_meta" and isinstance(obj.get("payload"), dict):
                value = obj["payload"].get("id")
                if isinstance(value, str) and value:
                    found.add(value)
    if len(found) != 1:
        raise RunnerError("Codex events lack one consistent thread/session ID")
    return next(iter(found))


def assistant_reply(events: list[dict[str, Any]]) -> str:
    """Extract the last non-empty assistant message, checking task-complete agreement."""
    candidates: list[str] = []
    complete: list[str] = []
    for event in events:
        kind = next(
            (event.get(key, "") for key in ("type", "event_type", "kind") if isinstance(event.get(key), str)), ""
        ).lower()
        if "task_complete" in kind:
            for obj in _walk(event):
                value = obj.get("last_agent_message")
                if isinstance(value, str):
                    complete.append(value)
        item = event.get("item")
        if kind == "item.completed" and isinstance(item, dict):
            if item.get("type") in {"agent_message", "assistant_message"}:
                for key in ("text", "message", "content"):
                    if isinstance(item.get(key), str) and item[key].strip():
                        candidates.append(item[key])
        if "agent_message" in kind or "assistant" in kind or "task_complete" in kind:
            for key in ("text", "message", "content", "last_agent_message"):
                if isinstance(event.get(key), str) and event[key].strip():
                    candidates.append(event[key])
    if not candidates:
        raise RunnerError("Codex stream contains no non-empty assistant reply")
    reply = candidates[-1]
    if complete and complete[-1].strip() and complete[-1] != reply:
        raise RunnerError("assistant reply disagrees with task-complete event")
    return reply


def extract_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    """Require exactly one direct completed-turn usage record."""

    def valid_usage(value: Any) -> dict[str, int] | None:
        if not isinstance(value, dict):
            return None
        input_tokens, output_tokens = value.get("input_tokens"), value.get("output_tokens")
        if (
            isinstance(input_tokens, int)
            and not isinstance(input_tokens, bool)
            and input_tokens > 0
            and isinstance(output_tokens, int)
            and not isinstance(output_tokens, bool)
            and output_tokens >= 0
        ):
            return {"input_tokens": input_tokens, "output_tokens": output_tokens}
        return None

    direct_events = [event for event in events if event.get("type") == "turn.completed" and "usage" in event]
    direct = [valid_usage(event.get("usage")) for event in direct_events]
    if len(direct) != 1 or direct[0] is None:
        raise RunnerError("Codex stream lacks exactly one valid direct completed-turn usage record")
    return direct[0]


def _second_prompt(case: dict[str, Any], first_reply: str) -> tuple[str | None, dict[str, Any] | None, str]:
    last = next((line.strip() for line in reversed(first_reply.splitlines()) if line.strip()), "")
    match = CHECK_RE.fullmatch(last)
    if not match:
        return None, None, case["subject"]["no_item_reply"]
    items = {str(item["id"]): item for item in case["subject"]["menu"]}
    item_id = match.group(1)
    if item_id not in items:
        raise RunnerError("first-turn CHECK request names an unknown menu ID")
    item = items[item_id]
    return item_id, item, item["output"]


def _rollout_version_matches(value: object) -> bool:
    """Accept only the banner and metadata spellings of the frozen CLI pin."""
    bare = CLI_VERSION.removeprefix("codex-cli ")
    return isinstance(value, str) and value in {CLI_VERSION, bare}


def _executable_version_matches(stdout: str, stderr: str) -> bool:
    """Require the exact frozen CLI banner, with no extra diagnostic text."""
    return stdout.strip() == CLI_VERSION and not stderr.strip()


def _usage_from_rollout(
    root: Path, session: str, *, expected_turns: int, arm_text: str, scratch: Path
) -> tuple[Path, str]:
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        ids = set()
        for event in events:
            for obj in _walk(event):
                for key in ("thread_id", "session_id"):
                    if isinstance(obj.get(key), str):
                        ids.add(obj[key])
                if obj.get("type") == "session_meta" and isinstance(obj.get("payload"), dict):
                    if isinstance(obj["payload"].get("id"), str):
                        ids.add(obj["payload"]["id"])
        if session not in ids:
            continue
        if has_tool_use(events):
            raise RunnerError("persisted Codex rollout contains a tool-use event")
        metas = [e.get("payload", {}) for e in events if e.get("type") == "session_meta"]
        if len(metas) != 1 or metas[0].get("id") != session:
            raise RunnerError("persisted rollout session metadata is missing or ambiguous")
        meta = metas[0]
        if not _rollout_version_matches(meta.get("cli_version")) or Path(str(meta.get("cwd", ""))).resolve() != scratch:
            raise RunnerError("persisted rollout CLI version or scratch cwd differs from the frozen run")
        base = meta.get("base_instructions", {})
        if not isinstance(base, dict) or base.get("text") not in {arm_text, arm_text.rstrip("\n")}:
            raise RunnerError("persisted rollout instructions differ from frozen arm A")
        contexts = [e.get("payload", {}) for e in events if e.get("type") == "turn_context"]
        if len(contexts) != expected_turns or any(
            c.get("model") != MODEL or c.get("effort") != EFFORT for c in contexts
        ):
            raise RunnerError("persisted rollout turn count, model, or effort differs from V3 pins")
        found.append(path)
    if len(found) != 1:
        raise RunnerError(f"expected exactly one persisted V3 rollout; found {len(found)}")
    path = found[0]
    return path, _sha(path.read_bytes())


def _command(codex: str, scratch: Path, model: str, prompt: str, *, resume: str | None = None) -> list[str]:
    common = [
        codex,
        "exec",
        "--disable",
        "memories",
        "--disable",
        "multi_agent",
        "-c",
        'web_search="disabled"',
        "-s",
        "read-only",
        "--ignore-user-config",
        "--ignore-rules",
        "-C",
        str(scratch),
        "-c",
        f'model_instructions_file="{ARM}"',
    ]
    if resume is not None:
        common += ["resume", "--json", "--skip-git-repo-check", resume]
    else:
        common += ["--json", "--skip-git-repo-check"]
    return common + ["-m", model, "-c", f'model_reasoning_effort="{EFFORT}"', prompt]


def _codex_child_environment(codex_home: Path, tmp: Path) -> dict[str, str]:
    """Pass only basic execution settings and the explicitly bound Codex home."""
    parent = os.environ
    allowed = {
        key: parent[key] for key in ("PATH", "LANG", "LC_ALL", "TERM", "NO_COLOR") if isinstance(parent.get(key), str)
    }
    allowed.update(
        {
            "HOME": str(codex_home.parent),
            "CODEX_HOME": str(codex_home),
            "TMPDIR": str(tmp),
            "TMP": str(tmp),
            "TEMP": str(tmp),
        }
    )
    return allowed


def _validate_source_runtime_paths(
    *, scratch: Path, output_dir: Path, rollout_root: Path, ledger_path: Path, codex_home: Path
) -> tuple[Path, Path, Path, Path, Path]:
    """Validate every source-phase writable root before initializing its ledger."""
    raw_home = codex_home.expanduser()
    if raw_home.is_symlink():
        raise RunnerError("source CODEX_HOME cannot be a symlink")
    try:
        scratch_path = source_phase_v3._outside_repo(scratch, "source scratch")
        output_path = source_phase_v3._outside_repo(output_dir, "source output")
        rollout_path = source_phase_v3._outside_repo(rollout_root, "source rollout root")
        ledger_file = source_phase_v3._outside_repo(ledger_path, "source ledger")
        home_path = source_phase_v3._outside_repo(codex_home, "source CODEX_HOME")
    except source_phase_v3.SourcePhaseError as exc:
        raise RunnerError(str(exc)) from exc
    repo = HERE.parents[2].resolve()
    if not scratch_path.is_dir() or scratch_path == repo or repo in scratch_path.parents:
        raise RunnerError("scratch must be an existing directory outside the repository")
    if output_path.exists() and (not output_path.is_dir() or any(output_path.iterdir())):
        raise RunnerError("V3 output directory must be new or empty")
    auth_path = home_path / "auth.json"
    if (
        not home_path.is_dir()
        or home_path.is_symlink()
        or not auth_path.is_file()
        or auth_path.is_symlink()
        or {entry.name for entry in home_path.iterdir()} != {"auth.json"}
    ):
        raise RunnerError("source CODEX_HOME must be a dedicated external directory containing only auth.json")
    if auth_path.stat().st_mode & 0o077:
        raise RunnerError("source CODEX_HOME auth.json must have private permissions")
    expected_rollout_root = home_path / "sessions"
    if rollout_path != expected_rollout_root:
        raise RunnerError("rollout root must be the sessions directory inside the isolated V3 Codex home")
    if output_path == ledger_file or output_path in ledger_file.parents:
        raise RunnerError("source ledger must not be inside the source output directory")
    return scratch_path, output_path, rollout_path, ledger_file, home_path


def _invoke(
    command: list[str],
    *,
    cwd: Path,
    codex_home: Path,
    tmp: Path,
    artifact_base: Path,
    environment: dict[str, str] | None = None,
    popen_factory: Callable[..., Any] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    env = environment or _codex_child_environment(codex_home, tmp)
    proc = (popen_factory or subprocess.Popen)(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        stdout, stderr = proc.communicate(timeout=1800)
    except subprocess.TimeoutExpired as exc:
        proc.terminate()
        try:
            proc.communicate(timeout=PROCESS_STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
        raise RunnerError("Codex provider call timed out; attempt is terminal") from exc
    result = subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
    _create_bytes(Path(f"{artifact_base}.stdout.txt"), result.stdout.encode("utf-8"))
    _create_bytes(Path(f"{artifact_base}.stderr.txt"), result.stderr.encode("utf-8"))
    _create(
        Path(f"{artifact_base}.dispatch.json"),
        {
            "command": command,
            "cwd": str(cwd),
            "returncode": result.returncode,
            "status": "accepted" if result.returncode == 0 else "failed",
            "stop_reason": None,
        },
    )
    if result.returncode != 0:
        raise RunnerError(f"Codex exited {result.returncode}; attempt is terminal")
    events = parse_events(result.stdout)
    _create(Path(f"{artifact_base}.events.json"), events)
    return events, result.stdout


def run_technical_source(
    *,
    output_dir: Path,
    scratch: Path,
    rollout_root: Path,
    codex: str = "codex",
    model: str = MODEL,
    ledger_path: Path | None = None,
    codex_home: Path | None = None,
    approval: Path = ledger.APPROVAL,
    seal_path: Path = ledger.V3_SEAL,
    plan: Path = ledger.PLAN,
    packet_seal: Path = ledger.PACKET_SEAL,
    source_preflight_report: Path | None = None,
    source_amendment_seal: Path = source_phase_v3.DEFAULT_AMENDMENT_SEAL,
    source_amendment_proposal: Path = source_phase_v3.AMENDMENT_PROPOSAL,
    operational_seal: Path = lean_source_protocol_v3.OPERATIONAL_SEAL,
) -> dict[str, Any]:
    """Execute one fresh two-turn A/strongest technical exchange after exact V3 admission.

    This function is the sole process-launching API. It has no process or quota
    injection parameters; offline tests patch subprocess and the quota adapter.
    """
    try:
        approval_record = _json(approval)
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError("owner approval is unavailable or malformed") from exc
    if approval_record.get("record_type") == "p3_v3_lean_source_protocol_approval":
        try:
            lean_source_protocol_v3.validate_approval(approval, seal_path=lean_source_protocol_v3.SEAL)
        except lean_source_protocol_v3.ProtocolError as exc:
            raise RunnerError("lean source protocol approval or successor seal is stale") from exc
        raise RunnerError("lean source protocol approval is default deny; provider dispatch is unauthorized")
    lean_approval = approval_record.get("record_type") == "p3_v3_lean_source_operational_approval"
    if lean_approval or approval_record.get("record_type") == source_phase_v3.APPROVAL_TYPE:
        if source_preflight_report is None:
            raise RunnerError("source-only approval requires its saved preflight report")
        if ledger_path is None:
            raise RunnerError("source-only dispatch requires an explicit out-of-repository --ledger path")
        if codex_home is None:
            raise RunnerError("source-only dispatch requires an explicit authenticated --codex-home")
        scratch, output_dir, rollout_root, ledger_path, codex_home = _validate_source_runtime_paths(
            scratch=scratch,
            output_dir=output_dir,
            rollout_root=rollout_root,
            ledger_path=ledger_path,
            codex_home=codex_home,
        )
        if lean_approval:
            try:
                lean_source_protocol_v3.validate_operational_approval(approval, seal_path=operational_seal)
            except lean_source_protocol_v3.ProtocolError as exc:
                raise RunnerError("lean operational approval or exact code seal is invalid") from exc
    else:
        ledger_path = ledger_path or ledger.LEDGER
        dispatch_v3.require_dispatch(
            phase="technical_source",
            approval=approval,
            seal_path=seal_path,
            plan=plan,
            packet_seal=packet_seal,
            ledger_path=ledger_path,
        )
        codex_home = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    if model != MODEL:
        raise RunnerError("technical source model differs from the frozen V3 pin")
    repo = HERE.parents[2].resolve()
    scratch, output_dir, rollout_root = scratch.resolve(), output_dir.resolve(), rollout_root.resolve()
    if not scratch.is_dir() or scratch == repo or repo in scratch.parents:
        raise RunnerError("scratch must be an existing directory outside the repository")
    for label, root in (("output", output_dir), ("rollout", rollout_root)):
        if root in (repo, HERE) or repo in root.parents or HERE in root.parents:
            raise RunnerError(f"{label} directory must resolve outside the sealed source tree")
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise RunnerError("V3 output directory must be new or empty")
    expected_rollout_root = codex_home.resolve() / "sessions"
    if rollout_root != expected_rollout_root:
        raise RunnerError("rollout root must be the sessions directory inside the bound CODEX_HOME")
    executable = shutil.which(codex)
    if executable is None:
        raise RunnerError("Codex executable is unavailable")
    executable = str(Path(executable).resolve())
    runtime = output_dir / "runtime"
    tmp = runtime / "tmp"
    child_env = _codex_child_environment(codex_home, tmp)
    account_receipt = quota_adapter_v3.account_limit_receipt(executable, codex_home)
    version = subprocess.run(
        [executable, "--version"], env=child_env, capture_output=True, text=True, check=False, timeout=30
    )
    if version.returncode or not _executable_version_matches(version.stdout, version.stderr):
        raise RunnerError("Codex CLI does not match frozen 0.156.1 pin")

    def quota_reader() -> dict[str, Any]:
        snapshot = quota_adapter_v3.read_quota_snapshot(
            codex_executable=executable, codex_home=codex_home, environment=child_env
        )
        if snapshot.get("account_limit_receipt") != account_receipt:
            raise RunnerError("quota account/limit receipt differs from the bound Codex runner")
        return snapshot

    if lean_approval:
        try:
            lean_source_protocol_v3.initialize_operational_ledger(
                ledger_path, approval_path=approval, seal_path=operational_seal
            )
            lean_source_protocol_v3.require_operational_dispatch(
                approval_path=approval,
                seal_path=operational_seal,
                preflight_path=source_preflight_report,
                ledger_path=ledger_path,
            )
        except lean_source_protocol_v3.ProtocolError as exc:
            raise RunnerError("lean source dispatch gate failed") from exc
    elif approval_record.get("record_type") == source_phase_v3.APPROVAL_TYPE:
        source_phase_v3.initialize_source_ledger(
            ledger_path=ledger_path,
            approval_path=approval,
            seal_path=source_amendment_seal,
            plan=plan,
            packet_seal=packet_seal,
            base_seal=seal_path,
            amendment_proposal=source_amendment_proposal,
        )
        dispatch_v3.require_dispatch(
            phase="technical_source",
            approval=approval,
            seal_path=seal_path,
            plan=plan,
            packet_seal=packet_seal,
            ledger_path=ledger_path,
            source_preflight_report=source_preflight_report,
            source_amendment_seal=source_amendment_seal,
            source_amendment_proposal=source_amendment_proposal,
            quota_snapshot=None,
            defer_quota_to_reservation=True,
        )
    packet = _json(PACKET)
    arm_text = ARM.read_text(encoding="utf-8")
    manifest = _json(ARM_MANIFEST)
    packet_seal_record = _json(packet_seal)
    sealed_files = packet_seal_record.get("files", {})
    if (
        sealed_files.get("cases/P3-01.json") != _sha(PACKET.read_bytes())
        or sealed_files.get("arms/A.architect.system.txt") != _sha(arm_text)
        or manifest.get("arms", {}).get("A", {}).get("sha256") != _sha(arm_text)
    ):
        raise RunnerError("arm A hash differs from its manifest")
    _, prior_events = ledger._read(ledger_path)
    occupied = ledger._historical_ids()
    for event in prior_events:
        for field in ("provider_call_id", "subject_attempt_id", "run_id"):
            if isinstance(event.get(field), str):
                occupied.add(event[field])
    run_id = ledger.fresh_id(occupied)
    attempt_id = ledger.fresh_id(occupied | {run_id})
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    rollout_root.mkdir(parents=True)
    _create(
        output_dir / f"{run_id}.attempt.json",
        {
            "epoch_id": ledger._read(ledger_path)[0]["epoch_id"],
            "run_id": run_id,
            "subject_attempt_id": attempt_id,
            "case": "P3-01",
            "arm": "A",
            "tier": "strongest",
            "repeat": 1,
            "attempt_class": "technical",
            "model": MODEL,
            "effort": EFFORT,
            "account_limit_receipt": account_receipt,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )

    def call(
        turn_num: int, prompt: str, *, resume: str | None = None
    ) -> tuple[list[dict[str, Any]], str, str, dict[str, int], str]:
        turn_id = f"turn-{turn_num}"
        prefix = output_dir / f"{run_id}.turn{turn_num}"
        command = _command(executable, scratch, model, prompt, resume=resume)
        try:
            snapshot = quota_reader()
        except BaseException as exc:
            raise RunnerError("fresh quota snapshot is required immediately before provider call") from exc
        call_id = ledger.reserve(
            "codex",
            "technical",
            quota_snapshot=snapshot,
            path=ledger_path,
            proposal_sha256=ledger.sha256(plan),
            approval_sha256=ledger.sha256(approval),
            subject_attempt_id=attempt_id,
            turn_id=turn_id,
            token_reservation=TURN_INPUT_CAP,
        )

        usage: dict[str, int] | None = None
        call_closed = False
        try:
            events, raw = _invoke(
                command, cwd=scratch, codex_home=codex_home, tmp=tmp, artifact_base=prefix, environment=child_env
            )
            session = thread_id(events)
            usage = extract_usage(events)
            if usage["input_tokens"] > TURN_INPUT_CAP:
                ledger.complete_lean(
                    call_id, outcome="failed", usage=usage, path=ledger_path, failure_code="turn_input_cap_exceeded"
                )
                call_closed = True
                raise RunnerError("direct usage exceeds the 40,000-token per-turn input cap")
            if has_tool_use(events):
                ledger.complete_lean(
                    call_id, outcome="failed", usage=usage, path=ledger_path, failure_code="tool_use_detected"
                )
                call_closed = True
                raise RunnerError("Codex event stream contains tool use; V3 requires no tools")
            # Account the observed call even if later transcript checks fail.
            ledger.complete_lean(call_id, outcome="accepted", usage=usage, path=ledger_path)
            call_closed = True
            return events, raw, session, usage, call_id
        except BaseException as exc:
            if not call_closed:
                try:
                    ledger.complete_lean(
                        call_id, outcome="failed", usage=None, path=ledger_path, failure_code=type(exc).__name__
                    )
                except BaseException:
                    # An unresolved reservation preserves unknown exposure and blocks dispatch.
                    pass
            raise

    try:
        e1, raw1, session1, usage1, call1 = call(1, packet["subject"]["turn1"])
        reply1 = assistant_reply(e1)
        menu_id, menu_item, prompt2 = _second_prompt(packet, reply1)
        e2, raw2, session2, usage2, call2 = call(2, prompt2, resume=session1)
        if session2 != session1:
            raise RunnerError("Codex resume created a different thread/session ID")
        reply2 = assistant_reply(e2)
        rollout_path, rollout_hash = _usage_from_rollout(
            rollout_root, session1, expected_turns=2, arm_text=arm_text, scratch=scratch
        )
        exchange = {
            "run_id": run_id,
            "turns": [
                {"user": packet["subject"]["turn1"], "assistant": reply1, "events_sha256": _sha(raw1)},
                {"user": prompt2, "assistant": reply2, "events_sha256": _sha(raw2)},
            ],
        }
        exchange_path = output_dir / f"{run_id}.exchange.json"
        _create(exchange_path, exchange)
        source_hashes = {
            "case_sha256": _sha(PACKET.read_bytes()),
            "arm_sha256": _sha(arm_text),
            "exchange_sha256": _sha(exchange_path.read_bytes()),
            "rollout_sha256": rollout_hash,
        }
        packet_source_hash = _sha(json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode())
        record = {
            "epoch_id": ledger._read(ledger_path)[0]["epoch_id"],
            "run_id": run_id,
            "subject_attempt_id": attempt_id,
            "case": "P3-01",
            "arm": "A",
            "tier": "strongest",
            "repeat": 1,
            "case_sha256": source_hashes["case_sha256"],
            "arm_sha256": source_hashes["arm_sha256"],
            "model": MODEL,
            "cli_version": CLI_VERSION,
            "thread_id": session1,
            "verified": True,
            "exchange_sha256": source_hashes["exchange_sha256"],
            "rollout_sha256": source_hashes["rollout_sha256"],
            "usage_calls": [
                {"provider_call_id": call1, **usage1},
                {"provider_call_id": call2, **usage2},
            ],
            "packet_source_sha256": packet_source_hash,
            "account_limit_receipt": account_receipt,
            "provenance_scope": "evaluator_only",
        }
        _create(output_dir / f"{run_id}.record.json", record)
        return record
    except BaseException as exc:
        _create(
            output_dir / f"{run_id}.failure.json",
            {
                "run_id": run_id,
                "subject_attempt_id": attempt_id,
                "failure": type(exc).__name__,
                "message": str(exc),
                "terminal": True,
                "retry_authorized": False,
            },
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="required to enable the two provider calls")
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--rollout-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--codex-home", type=Path, help="required source-phase external authenticated CODEX_HOME")
    parser.add_argument("--approval", type=Path, default=ledger.APPROVAL)
    parser.add_argument("--seal", type=Path, default=ledger.V3_SEAL)
    parser.add_argument("--ledger", type=Path, help="required source-phase ledger path outside the repository")
    parser.add_argument(
        "--source-preflight-report",
        type=Path,
        help="saved source-only preflight report (required for source-only approvals)",
    )
    parser.add_argument("--source-amendment-seal", type=Path, default=source_phase_v3.DEFAULT_AMENDMENT_SEAL)
    parser.add_argument("--source-amendment-proposal", type=Path, default=source_phase_v3.AMENDMENT_PROPOSAL)
    parser.add_argument("--operational-seal", type=Path, default=lean_source_protocol_v3.OPERATIONAL_SEAL)
    args = parser.parse_args()
    if not args.execute:
        parser.error("default-deny: pass --execute only after exact V3 owner approval")
    missing = [key for key in ("scratch", "rollout_root", "output_dir") if getattr(args, key) is None]
    if missing:
        parser.error("required with --execute: " + ", ".join(missing))
    if args.codex_home is None:
        parser.error("required with --execute: --codex-home")
    print(
        json.dumps(
            run_technical_source(
                scratch=args.scratch,
                rollout_root=args.rollout_root,
                output_dir=args.output_dir,
                codex=args.codex,
                codex_home=args.codex_home,
                approval=args.approval,
                seal_path=args.seal,
                ledger_path=args.ledger,
                source_preflight_report=args.source_preflight_report,
                source_amendment_seal=args.source_amendment_seal,
                source_amendment_proposal=args.source_amendment_proposal,
                operational_seal=args.operational_seal,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
