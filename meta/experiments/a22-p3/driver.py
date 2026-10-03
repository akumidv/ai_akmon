#!/usr/bin/env python3
"""Run one sealed P3 Codex cell with two transcript-verified turns.

The executable path is deliberately opt-in (``--execute``).  ``--self-test``
uses only synthetic JSONL event streams and must remain free of model calls.
"""
# These small executable helpers are internal to the packet, and the synthetic
# self-test deliberately uses assertions as its no-framework checks.
# ruff: noqa: D103, S101
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
TEST_NONZERO_EXIT = 9
CHECK_RE = re.compile(r"^CHECK: ([A-Za-z0-9][A-Za-z0-9_-]*)$")
TOOL_EVENT_MARKERS = {
    "function_call", "custom_tool_call", "local_shell_call", "web_search_call",
    "tool_search_call", "image_generation_call", "mcp_tool_call", "command_execution",
    "file_change", "computer_call", "tool_call",
}


def sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Atomically write an artifact, never silently replacing a completed record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def event_stream(text: str) -> list[dict[str, Any]]:
    """Parse Codex ``--json`` output fail-closed, preserving every event object."""
    events = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"event line {number} is not JSON") from exc
        if not isinstance(event, dict):
            raise ValueError(f"event line {number} is not an object")
        events.append(event)
    if not events:
        raise ValueError("empty Codex event stream")
    return events


def values(value: Any, key: str) -> list[Any]:
    """Collect values named ``key`` from a JSON event without assuming one schema."""
    found: list[Any] = []
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key:
                found.append(child)
            found.extend(values(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(values(child, key))
    return found


def event_type(event: dict[str, Any]) -> str:
    for key in ("type", "event_type", "kind"):
        value = event.get(key)
        if isinstance(value, str):
            return value.lower()
    return ""


def has_tool_use(events: list[dict[str, Any]]) -> bool:
    """Detect explicit tool-call markers at any nesting level in the JSON event."""
    kinds = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"type", "event_type", "kind"} and isinstance(child, str):
                    kinds.append(child.lower())
                if key in {"tool_name", "tool_call_id"} and child:
                    kinds.append("explicit_tool_field")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for event in events:
        visit(event)
    return any(
        kind in TOOL_EVENT_MARKERS or "tool_call" in kind or kind.endswith(".tool")
        or "function_call" in kind or "computer_call" in kind or kind == "explicit_tool_field"
        for kind in kinds
    )


def text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for key in ("text", "message", "content", "last_agent_message", "assistant"):
            child = value.get(key)
            if isinstance(child, str):
                result.append(child)
        return result
    return []


def replies(events: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for event in events:
        kind = event_type(event)
        if "agent_message" in kind or "assistant" in kind or "task_complete" in kind:
            result.extend(text for text in text_values(event) if text.strip())
    return result


def completed_reply(events: list[dict[str, Any]]) -> str:
    """Apply M94's nonempty reply rule and verify task-complete agrees when present."""
    candidates = replies(events)
    if not candidates:
        raise ValueError("no nonempty assistant reply in Codex event stream")
    reply = candidates[-1]
    complete = []
    for event in events:
        if "task_complete" in event_type(event):
            complete.extend(str(value) for value in values(event, "last_agent_message") if isinstance(value, str))
    if complete and complete[-1].strip() and complete[-1] != reply:
        raise ValueError("last nonempty reply disagrees with task_complete.last_agent_message")
    return reply


def thread_id(events: list[dict[str, Any]]) -> str:
    ids = [str(value) for event in events for value in values(event, "thread_id") if isinstance(value, str)]
    ids += [str(value) for event in events for value in values(event, "session_id") if isinstance(value, str)]
    if not ids:
        raise ValueError("Codex event stream contains no thread/session id")
    if len(set(ids)) != 1:
        raise ValueError(f"Codex event stream has conflicting thread/session ids: {sorted(set(ids))}")
    return ids[0]


def requested_item(reply: str, menu: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None]:
    """Accept an item request only as an exact final nonempty ``CHECK: id`` line."""
    last = next((line.strip() for line in reversed(reply.splitlines()) if line.strip()), "")
    match = CHECK_RE.fullmatch(last)
    if not match:
        return None, None
    item_id = match.group(1)
    by_id = {str(item["id"]): item for item in menu}
    if item_id not in by_id:
        raise ValueError(f"unknown CHECK item id: {item_id}")
    return item_id, by_id[item_id]


def second_turn(case: dict[str, Any], reply: str) -> tuple[str | None, dict[str, Any] | None, str]:
    """Resolve one exact menu request, or return the fixed no-item turn."""
    item_id, item = requested_item(reply, case["subject"]["menu"])
    return item_id, item, item["output"] if item else case["subject"]["no_item_reply"]


def load_cell(map_path: Path, run_id: str) -> dict[str, Any]:
    mapping = read_json(map_path)
    if not isinstance(mapping, dict) or run_id not in mapping or not isinstance(mapping[run_id], dict):
        raise ValueError(f"run id {run_id!r} is absent from {map_path}")
    cell = mapping[run_id]
    if set(cell) != {"case", "arm", "tier", "repeat"}:
        raise ValueError(f"run id {run_id!r} has unexpected cell shape")
    if cell["arm"] not in {"A", "B", "C"}:
        raise ValueError(f"unsupported arm: {cell['arm']!r}")
    return cell


def subject_run_count(runs: Path = RUNS) -> int:
    attempts = {path.name.removesuffix(".attempt.json") for path in runs.glob("*.attempt.json")}
    records = {path.name.removesuffix(".record.json") for path in runs.glob("*.record.json")}
    return len(attempts | records)


def scratch_outside_repository(scratch: Path, repository: Path) -> bool:
    resolved_scratch, resolved_repository = scratch.resolve(), repository.resolve()
    return resolved_scratch != resolved_repository and resolved_repository not in resolved_scratch.parents


def input_cap(name: str, declared: int, cap: int) -> None:
    if declared < 1:
        raise ValueError(f"{name} must be a positive pre-dispatch token count")
    if declared > cap:
        raise ValueError(f"{name} {declared} exceeds per-turn cap {cap}")


def verify_rollout(root: Path, identifier: str) -> tuple[Path, str]:
    """Find one JSONL rollout with an exact session id reference and hash it."""
    matches = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            events = [json.loads(line) for line in lines if line.strip()]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        ids = [str(value) for event in events for key in ("thread_id", "session_id")
               for value in values(event, key) if isinstance(value, str)]
        ids.extend(str(event.get("payload", {}).get("id")) for event in events
                   if event.get("type") == "session_meta"
                   and isinstance(event.get("payload"), dict)
                   and isinstance(event["payload"].get("id"), str))
        if identifier in ids:
            if any(has_tool_use([event]) for event in events):
                raise ValueError(f"tool-use event found in persisted rollout for {identifier}")
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(f"expected one persisted rollout for {identifier}, found {len(matches)} under {root}")
    return matches[0], sha(matches[0].read_bytes())


def run_codex(command: list[str], cwd: Path, run_id: str, turn: int,  # noqa: C901, PLR0912, PLR0915
              artifact_dir: Path = RUNS) -> tuple[list[dict[str, Any]], str]:
    """Persist raw and parsed dispatch evidence before accepting or rejecting a turn."""
    prefix = artifact_dir / f"{run_id}.turn{turn}"
    stdout_path = Path(str(prefix) + ".stdout.txt")
    stderr_path = Path(str(prefix) + ".stderr.txt")
    events_path = Path(str(prefix) + ".events.json")
    metadata_path = Path(str(prefix) + ".dispatch.json")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "run_id": run_id, "turn": turn, "command": command, "cwd": str(cwd),
        "status": "failed", "returncode": None, "failure_reason": None,
    }
    interrupted: KeyboardInterrupt | None = None
    launch_error: OSError | None = None
    try:
        with stdout_path.open("xb") as stdout_file, stderr_path.open("xb") as stderr_file:
            process = subprocess.Popen(command, cwd=cwd, stdout=stdout_file, stderr=stderr_file)
            try:
                metadata["returncode"] = process.wait()
            except KeyboardInterrupt as exc:
                interrupted = exc
                metadata["failure_reason"] = f"dispatch interrupted: {type(exc).__name__}"
                process.terminate()
                try:
                    metadata["returncode"] = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    metadata["returncode"] = process.wait()
    except OSError as exc:
        launch_error = exc
        if not stdout_path.exists():
            stdout_path.write_bytes(b"")
        if not stderr_path.exists():
            stderr_path.write_text(str(exc), encoding="utf-8")

    stdout = stdout_path.read_bytes()
    stderr = stderr_path.read_bytes()
    if launch_error is not None:
        metadata["failure_reason"] = f"dispatch launch failed: {launch_error}"
    else:
        events: list[dict[str, Any]] | None = None
        event_error = None
        try:
            events = event_stream(stdout.decode("utf-8"))
            write_json(events_path, events)
            metadata["tool_use_detected"] = has_tool_use(events)
        except (UnicodeDecodeError, ValueError) as exc:
            event_error = str(exc)
            events_path.write_text("[]\n", encoding="utf-8")
            metadata["tool_use_detected"] = False
        if metadata["returncode"]:
            metadata["failure_reason"] = f"Codex exited {metadata['returncode']}"
        elif event_error:
            metadata["failure_reason"] = f"invalid event stream: {event_error}"
        elif metadata["tool_use_detected"]:
            metadata["failure_reason"] = "tool use recorded; P3 is a no-tools protocol"
        elif interrupted is None:
            metadata["status"] = "ok"
        metadata["event_parse_error"] = event_error
    if launch_error is not None:
        events = None
        events_path.write_text("[]\n", encoding="utf-8")
        metadata["tool_use_detected"] = False
    write_json(metadata_path, metadata)
    if interrupted is not None:
        raise interrupted
    if metadata["failure_reason"]:
        detail = stderr.decode("utf-8", errors="replace").strip()[:500]
        raise RuntimeError(metadata["failure_reason"] + (f": {detail}" if detail else ""))
    if events is None:
        raise RuntimeError("event stream was not parsed")
    return events, stdout.decode("utf-8")


def command_for_initial(args: argparse.Namespace, arm_path: Path, prompt: str) -> list[str]:
    return [
        args.codex, "exec", "--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
        "-C", str(args.scratch), "-s", "read-only", "-m", args.model,
        "-c", f'model_reasoning_effort="{args.effort}"',
        "-c", f'model_instructions_file="{arm_path}"', prompt,
    ]


def command_for_resume(args: argparse.Namespace, current_thread: str, prompt: str) -> list[str]:
    return [
        args.codex, "exec", "resume", "--json", current_thread, "-m", args.model,
        "-c", f'model_reasoning_effort="{args.effort}"', prompt,
    ]


def execute(args: argparse.Namespace) -> Path:
    if not args.execute:
        raise ValueError("refusing model call without --execute")
    scratch = args.scratch.resolve()
    repository = HERE.parents[2].resolve()
    if not scratch.is_dir() or not scratch_outside_repository(scratch, repository):
        raise ValueError("scratch must be an existing directory outside the repository")
    if not args.rollout_root.is_dir():
        raise ValueError("rollout root must exist before dispatch")
    if shutil.which(args.codex) is None:
        raise ValueError(f"Codex executable is unavailable: {args.codex}")
    if args.subject_run_cap < 1 or subject_run_count() >= args.subject_run_cap:
        raise ValueError("subject-run cap reached before dispatch")
    input_cap("turn 1 declared input tokens", args.turn1_input_tokens, args.turn_cap)
    input_cap("turn 2 declared input tokens", args.turn2_input_tokens, args.turn_cap)

    cell = load_cell(args.map, args.run_id)
    case_path = HERE / "cases" / f"{cell['case']}.json"
    arm_path = HERE / "arms" / f"{cell['arm']}.architect.system.txt"
    case, manifest = read_json(case_path), read_json(HERE / "arms" / "manifest.json")
    arm_text = arm_path.read_text(encoding="utf-8")
    if sha(arm_text) != manifest["arms"][cell["arm"]]["sha256"]:
        raise ValueError("arm hash differs from sealed manifest")
    record_path = RUNS / f"{args.run_id}.record.json"
    attempt_path = RUNS / f"{args.run_id}.attempt.json"
    if record_path.exists() or attempt_path.exists():
        raise FileExistsError(f"run attempt or completed artifact exists for {args.run_id}")

    # Persist before dispatch, so failed/interrupted runs consume the subject-run budget.
    RUNS.mkdir(parents=True, exist_ok=True)
    with attempt_path.open("x", encoding="utf-8") as stream:
        json.dump({"run_id": args.run_id, **cell, "model": args.model, "effort": args.effort,
                   "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, stream, indent=2)
        stream.write("\n")

    events1, raw1 = run_codex(command_for_initial(args, arm_path, case["subject"]["turn1"]), scratch,
                              args.run_id, 1)
    answer1, id1 = completed_reply(events1), thread_id(events1)
    item_id, item, second_prompt = second_turn(case, answer1)
    turns = [{"user": case["subject"]["turn1"], "assistant": answer1, "events_sha256": sha(raw1)}]
    raw = [raw1]
    events2, raw2 = run_codex(command_for_resume(args, id1, second_prompt), scratch, args.run_id, 2)
    answer2, id2 = completed_reply(events2), thread_id(events2)
    if id2 != id1:
        raise ValueError("resume did not retain the initial thread/session id")
    turns.append({"user": second_prompt, "assistant": answer2, "events_sha256": sha(raw2)})
    raw.append(raw2)
    rollout_path, rollout_sha = verify_rollout(args.rollout_root, id1)
    exchange_path = RUNS / f"{args.run_id}.exchange.json"
    write_json(exchange_path, {"run_id": args.run_id, "turns": turns})
    record = {
        "run_id": args.run_id, **cell, "case_sha256": sha(case_path.read_bytes()),
        "arm_sha256": sha(arm_text), "thread_id": id1, "model": args.model, "effort": args.effort,
        "declared_input_tokens": {"turn1": args.turn1_input_tokens, "turn2": args.turn2_input_tokens,
                                  "source": args.token_estimate_source, "cap": args.turn_cap},
        "menu_id": item_id, "menu_right": item.get("right") if item else None,
        "tool_use_detected": False, "events_sha256": [sha(data) for data in raw],
        "rollout": {"path": str(rollout_path), "sha256": rollout_sha, "verified": True},
        "exchange_sha256": sha(exchange_path.read_bytes()), "verified": True,
        "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(record_path, record)
    return record_path


def self_test() -> None:  # noqa: PLR0915
    initial = event_stream('''{"type":"thread.started","thread_id":"s-1"}
{"type":"agent_message","message":"Need evidence.\\nCHECK: gate-log"}
{"type":"task_complete","task_complete":{"last_agent_message":"Need evidence.\\nCHECK: gate-log"}}''')
    assert not has_tool_use(initial)
    assert completed_reply(initial).endswith("CHECK: gate-log")
    assert thread_id(initial) == "s-1"
    # Failed dispatches preserve raw streams, parsed events, and the failure reason.
    original_popen = subprocess.Popen
    try:
        with tempfile.TemporaryDirectory() as temp:
            artifact_dir = Path(temp) / "runs"
            raw = b'{"type":"function_call","tool_name":"shell"}\n'
            class FakeProcess:
                returncode = TEST_NONZERO_EXIT

                def wait(self) -> int:
                    return self.returncode

            def fake_popen(_command: list[str], **kwargs: Any) -> FakeProcess:
                kwargs["stdout"].write(raw)
                kwargs["stderr"].write(b"synthetic failure")
                return FakeProcess()

            subprocess.Popen = fake_popen
            try:
                run_codex(["codex"], Path(temp), "failed", 1, artifact_dir)
            except RuntimeError as exc:
                assert f"exited {TEST_NONZERO_EXIT}" in str(exc)
            else:
                raise AssertionError("nonzero dispatch accepted")
            prefix = artifact_dir / "failed.turn1"
            assert Path(str(prefix) + ".stdout.txt").read_bytes() == raw
            assert Path(str(prefix) + ".stderr.txt").read_bytes() == b"synthetic failure"
            assert json.loads(Path(str(prefix) + ".events.json").read_text())[0]["type"] == "function_call"
            metadata = json.loads(Path(str(prefix) + ".dispatch.json").read_text())
            assert metadata["returncode"] == TEST_NONZERO_EXIT and metadata["tool_use_detected"] is True
            assert metadata["failure_reason"] == f"Codex exited {TEST_NONZERO_EXIT}"
    finally:
        subprocess.Popen = original_popen
    item_id, item = requested_item(completed_reply(initial), [{"id": "gate-log", "right": True}])
    assert item_id == "gate-log" and item and item["right"]
    tool = event_stream('{"type":"function_call","tool_name":"shell"}')
    assert has_tool_use(tool)
    nested_tool = event_stream('{"type":"item.completed","item":{"type":"function_call","name":"shell"}}')
    assert has_tool_use(nested_tool)
    try:
        requested_item("CHECK: unknown", [{"id": "known"}])
    except ValueError:
        pass
    else:
        raise AssertionError("unknown exact check id accepted")
    try:
        completed_reply(event_stream('{"type":"agent_message","message":"answer"}\n{"type":"task_complete","task_complete":{"last_agent_message":"other"}}'))
    except ValueError:
        pass
    else:
        raise AssertionError("reply/rollout disagreement accepted")
    no_item_case = {"subject": {"menu": [], "no_item_reply": "That item is not available in this setting."}}
    assert second_turn(no_item_case, "Give a bounded answer.") == (
        None, None, "That item is not available in this setting.")
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        repo = root / "repo"
        outside = root / "scratch"
        inside = repo / "scratch"
        outside.mkdir()
        inside.mkdir(parents=True)
        assert scratch_outside_repository(outside, repo)
        assert not scratch_outside_repository(inside, repo)
        (root / "rollout.jsonl").write_text(
            '{"type":"session_meta","payload":{"id":"s-1"}}\n'
            '{"type":"response_item","payload":{"type":"message"}}\n', encoding="utf-8")
        rollout, _digest = verify_rollout(root, "s-1")
        assert rollout.name == "rollout.jsonl"
        (root / "runs").mkdir()
        (root / "runs" / "failed.attempt.json").write_text("{}", encoding="utf-8")
        assert subject_run_count(root / "runs") == 1
    print("synthetic driver parser checks passed")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("--execute", action="store_true", help="allow a real model dispatch")
    result.add_argument("--map", type=Path)
    result.add_argument("--run-id")
    result.add_argument("--scratch", type=Path)
    result.add_argument("--rollout-root", type=Path)
    result.add_argument("--codex", default="codex")
    result.add_argument("--model")
    result.add_argument("--effort")
    result.add_argument("--turn-cap", type=int, default=40_000)
    result.add_argument("--turn1-input-tokens", type=int)
    result.add_argument("--turn2-input-tokens", type=int)
    result.add_argument("--token-estimate-source")
    result.add_argument("--subject-run-cap", type=int, default=120)
    return result


def main() -> None:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return
    required = ("map", "run_id", "scratch", "rollout_root", "model", "effort",
                "turn1_input_tokens", "turn2_input_tokens", "token_estimate_source")
    missing = [name.replace("_", "-") for name in required if getattr(args, name) is None]
    if missing:
        raise SystemExit("required for execution: " + ", ".join(missing))
    print(execute(args))


if __name__ == "__main__":
    main()
