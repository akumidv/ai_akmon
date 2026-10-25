"""Run the frozen C98 cold-resumption pair with descendant-inclusive gates."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


PACKET = Path(__file__).resolve().parent
MANIFEST = PACKET / "C98_MANIFEST.json"
SESSIONS = Path.home() / ".codex" / "sessions"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_snapshot(config: dict) -> None:
    worktree = Path(config["worktree"])
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=worktree, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=worktree, text=True
    )
    if head != config["head"] or status:
        raise RuntimeError("subject worktree HEAD or clean state changed")
    for relative, expected in config["source_sha256"].items():
        if digest(worktree / relative) != expected:
            raise RuntimeError(f"source hash changed: {relative}")
    for relative, expected in config["packet_sha256"].items():
        if digest(PACKET / relative) != expected:
            raise RuntimeError(f"packet hash changed: {relative}")


def rollout_paths() -> set[Path]:
    return set(SESSIONS.rglob("*.jsonl"))


def rollout_record(path: Path) -> dict | None:
    metadata = None
    model = None
    usage = None
    for line in path.open(encoding="utf-8"):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        payload = event.get("payload", {})
        if kind == "session_meta" and metadata is None:
            metadata = payload
        elif kind == "turn_context":
            model = payload.get("model", model)
        elif kind == "event_msg" and payload.get("type") == "token_count":
            usage = payload.get("info", {}).get("total_token_usage", usage)
    if metadata is None:
        return None
    return {
        "id": metadata.get("id"),
        "parent": metadata.get("parent_thread_id"),
        "cwd": metadata.get("cwd"),
        "model": model,
        "usage": usage,
        "path": str(path),
        "sha256": digest(path),
    }


def account(root_id: str, new_paths: set[Path], config: dict, archive: Path) -> dict:
    records = [rollout_record(path) for path in sorted(new_paths)]
    records = [
        record for record in records
        if record is not None and record["cwd"] == config["worktree"]
    ]
    ids = [record["id"] for record in records]
    if None in ids or len(ids) != len(set(ids)):
        raise RuntimeError("missing or duplicate session IDs in new worktree rollouts")
    by_parent: dict[str | None, list[dict]] = {}
    for record in records:
        by_parent.setdefault(record["parent"], []).append(record)
    queue = [root_id]
    tree = []
    seen = set()
    while queue:
        session_id = queue.pop(0)
        if session_id in seen:
            continue
        seen.add(session_id)
        match = next((record for record in records if record["id"] == session_id), None)
        if match is None or match["usage"] is None or match["model"] is None:
            raise RuntimeError(f"missing rollout, model or usage: {session_id}")
        expected = config["root_model"] if session_id == root_id else config["reader_model"]
        if match["model"] != expected:
            raise RuntimeError(f"wrong model for {session_id}: {match['model']}")
        target = archive / f"{session_id}.jsonl"
        if target.exists():
            raise RuntimeError(f"rollout archive collision: {session_id}")
        shutil.copyfile(match["path"], target)
        match["archive"] = str(target)
        tree.append(match)
        queue.extend(child["id"] for child in by_parent.get(session_id, []))
    if seen != set(ids):
        raise RuntimeError("new worktree rollout is unlinked from subject root")
    total = sum(item["usage"]["total_tokens"] for item in tree)
    return {"root_id": root_id, "total_tokens": total, "sessions": tree}


def run_arm(name: str, config: dict, runtime: Path) -> dict:
    check_snapshot(config)
    before = rollout_paths()
    archive = runtime / name
    archive.mkdir(exist_ok=False)
    prompt = (PACKET / config["arms"][name]).read_text(encoding="utf-8")
    command = [
        "codex", "exec", "-C", config["worktree"], "-m", config["root_model"],
        "-c", f'model_reasoning_effort="{config["reasoning_effort"]}"',
        "-s", "read-only", "--json", "-o", str(archive / "final.md"), "-",
    ]
    with (archive / "stdout.jsonl").open("w", encoding="utf-8") as stdout:
        with (archive / "stderr.txt").open("w", encoding="utf-8") as stderr:
            result = subprocess.run(
                command, input=prompt, text=True, stdout=stdout, stderr=stderr,
                cwd=config["worktree"], check=False,
            )
    if result.returncode:
        raise RuntimeError(f"{name} CLI failed: {result.returncode}; artifacts retained")
    root_ids = [
        json.loads(line)["thread_id"]
        for line in (archive / "stdout.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("type") == "thread.started"
    ]
    if len(root_ids) != 1 or not (archive / "final.md").is_file():
        raise RuntimeError(f"{name} missing unique root or final answer")
    tree = account(root_ids[0], rollout_paths() - before, config, archive)
    tree["arm"] = name
    tree["final_sha256"] = digest(archive / "final.md")
    (archive / "account.json").write_text(
        json.dumps(tree, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    check_snapshot(config)
    return tree


def main() -> int:
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    runtime = Path(config["runtime"]).resolve()
    worktree = Path(config["worktree"]).resolve()
    if not runtime.is_relative_to(Path("/tmp")) or runtime == Path("/tmp"):
        raise RuntimeError("runtime must be a dedicated /tmp directory")
    if runtime.is_relative_to(worktree) or runtime.is_relative_to(PACKET):
        raise RuntimeError("runtime overlaps subject or packet")
    version = subprocess.check_output(["codex", "--version"], text=True).strip()
    if version != config["cli_version"]:
        raise RuntimeError(f"Codex CLI version drift: {version}")
    check_snapshot(config)
    runtime.mkdir(exist_ok=False)
    (runtime / "manifest.json").write_bytes(MANIFEST.read_bytes())
    results = []
    try:
        for name in ("current", "pointer"):
            if name == "pointer" and results[0]["total_tokens"] > config["first_arm_gate"]:
                raise RuntimeError("first arm exceeded descendant-inclusive gate")
            result = run_arm(name, config, runtime)
            results.append(result)
            if sum(item["total_tokens"] for item in results) > config["pair_gate"]:
                raise RuntimeError("pair exceeded descendant-inclusive monitoring gate")
    except Exception as error:
        (runtime / "STOP.txt").write_text(str(error) + "\n", encoding="utf-8")
        print(f"STOP: {error}; retained at {runtime}", file=sys.stderr)
        return 1
    (runtime / "result.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Completed pair; evidence at {runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
