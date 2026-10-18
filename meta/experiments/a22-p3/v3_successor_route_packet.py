#!/usr/bin/env python3
"""Build one blind, unscored route-check packet from the verified V3 successor."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = Path("/tmp/a22-p3-v3-successor-9xViiq")  # noqa: S108
RUN_ID = "4c22e100b2101c0d67067d33fd98cd92"
SOURCE_OUTPUT = SOURCE_ROOT / "output-run"
RECORD = SOURCE_OUTPUT / f"{RUN_ID}.record.json"
EXCHANGE = SOURCE_OUTPUT / f"{RUN_ID}.exchange.json"
LEDGER = SOURCE_ROOT / "ledger" / "provider-usage-v3.jsonl"
CASE = HERE / "cases" / "P3-01.json"
ARM = HERE / "arms" / "A.architect.system.txt"
PROMPT = HERE / "scoring" / "scorer-prompt.txt"
SEAL = HERE / "seal.json"
TURN_COUNT = 2
ELEMENT_COUNT = 4


class PacketError(ValueError):
    """The source, sealed scorer inputs, or private packet output is invalid."""


def sha(data: bytes) -> str:
    """Hash exact artifact bytes."""
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sealed_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PacketError("sealed scorer input is unavailable")
    seal = _json(SEAL)
    relative = path.relative_to(HERE).as_posix()
    expected = seal.get("files", {}).get(relative)
    data = path.read_bytes()
    if expected != sha(data):
        raise PacketError("sealed scorer input changed")
    return data


def _rollout(record: dict[str, Any]) -> Path:
    sessions = SOURCE_ROOT / "codex-home-run" / "sessions"
    candidates = [
        path
        for path in sessions.rglob("rollout-*.jsonl")
        if path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == record.get("rollout_sha256")
    ]
    if len(candidates) != 1:
        raise PacketError("source rollout is missing or ambiguous")
    return candidates[0]


def verified_source() -> tuple[dict[str, Any], list[dict[str, str]], Path]:  # noqa: C901
    """Recheck successor identity, immutable bytes, two turns, and ledger debits."""
    for path in (RECORD, EXCHANGE, LEDGER):
        if path.is_symlink() or not path.is_file():
            raise PacketError("source evidence is unavailable or linked")
    record = _json(RECORD)
    exchange = _json(EXCHANGE)
    if not isinstance(record, dict) or record.get("verified") is not True:
        raise PacketError("source record is not verified")
    rollout = _rollout(record)
    if (
        record.get("run_id") != RUN_ID
        or record.get("case") != "P3-01"
        or record.get("arm") != "A"
        or record.get("tier") != "strongest"
        or record.get("repeat") != 1
        or record.get("model") != "gpt-6-astra"
        or record.get("cli_version") != "codex-cli 0.156.1"
        or record.get("provenance_scope") != "evaluator_only"
        or record.get("case_sha256") != sha(_sealed_bytes(CASE))
        or record.get("arm_sha256") != sha(_sealed_bytes(ARM))
        or record.get("exchange_sha256") != sha(EXCHANGE.read_bytes())
        or record.get("rollout_sha256") != sha(rollout.read_bytes())
        or exchange.get("run_id") != RUN_ID
    ):
        raise PacketError("source identity or hashes differ from the verified cell")
    turns = exchange.get("turns")
    if (
        not isinstance(turns, list)
        or len(turns) != TURN_COUNT
        or any(
            not isinstance(turn, dict)
            or not isinstance(turn.get("user"), str)
            or not isinstance(turn.get("assistant"), str)
            or not turn["user"].strip()
            or not turn["assistant"].strip()
            or not re.fullmatch(r"[0-9a-f]{64}", str(turn.get("events_sha256", "")))
            for turn in turns
        )
    ):
        raise PacketError("source exchange is not two complete hashed turns")
    spec = importlib.util.spec_from_file_location("a22_v3_route_ledger", HERE / "usage_ledger_v3.py")
    if spec is None or spec.loader is None:
        raise PacketError("V3 ledger reader unavailable")
    ledger_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger_module)
    header, events = ledger_module._read(LEDGER)
    if record.get("epoch_id") != header.get("epoch_id"):
        raise PacketError("source epoch differs from ledger")
    calls = record.get("usage_calls")
    if not isinstance(calls, list) or len(calls) != TURN_COUNT:
        raise PacketError("source usage calls are incomplete")
    call_ids = [call.get("provider_call_id") for call in calls if isinstance(call, dict)]
    if len(call_ids) != TURN_COUNT or len(set(call_ids)) != TURN_COUNT:
        raise PacketError("source provider call IDs are absent or duplicated")
    for index, call in enumerate(calls, 1):
        if not isinstance(call, dict):
            raise PacketError("source call is malformed")
        turn = f"turn-{index}"
        reservations = [
            event
            for event in events
            if event.get("event") == "reserved" and event.get("provider_call_id") == call["provider_call_id"]
        ]
        matches = [
            event
            for event in events
            if event.get("event") == "completed" and event.get("provider_call_id") == call.get("provider_call_id")
        ]
        if (
            len(reservations) != 1
            or len(matches) != 1
            or any(
                event.get("turn_id") != turn
                or event.get("subject_attempt_id") != record.get("subject_attempt_id")
                or event.get("route") != "codex"
                for event in (*reservations, *matches)
            )
            or matches[0].get("outcome") != "accepted"
            or matches[0].get("usage_status") != "known"
            or matches[0].get("input_tokens") != call.get("input_tokens")
            or matches[0].get("output_tokens") != call.get("output_tokens")
        ):
            raise PacketError("source call does not match V3 ledger")
    return record, turns, rollout


def packet_bytes(opaque_id: str) -> bytes:
    """Render the frozen scoring format without source or arm identifiers."""
    if not re.fullmatch(r"g[0-9a-f]{16}", opaque_id):
        raise PacketError("packet id must be opaque")
    _record, turns, _rollout_path = verified_source()
    case = json.loads(_sealed_bytes(CASE))
    scoring = case.get("scoring")
    if not isinstance(scoring, list) or len(scoring) != ELEMENT_COUNT:
        raise PacketError("frozen P3-01 scoring elements are incomplete")
    spec = importlib.util.spec_from_file_location("a22_v3_route_renderer", HERE / "build_single_packet.py")
    if spec is None or spec.loader is None:
        raise PacketError("sealed packet renderer unavailable")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    _sealed_bytes(HERE / "build_single_packet.py")
    packet = renderer._render_packet(opaque_id, turns, scoring)
    if any(value.encode() in packet for value in (RUN_ID, "gpt-6-astra", "strongest", "qualification")):
        raise PacketError("source identity leaked into scorer packet")
    return packet


def build(out_dir: Path) -> dict[str, Any]:
    """Write one private packet and evaluator manifest, refusing overwrite."""
    root = out_dir.resolve()
    if root == HERE or HERE in root.parents or root.exists():
        raise PacketError("packet destination must be new and outside the repository")
    opaque_id = "g" + secrets.token_hex(8)
    packet = packet_bytes(opaque_id)
    prompt = _sealed_bytes(PROMPT)
    record, _turns, rollout = verified_source()
    manifest = {
        "schema": 1,
        "record_type": "p3_v3_successor_route_packet",
        "opaque_packet_id": opaque_id,
        "packet_sha256": sha(packet),
        "prompt_sha256": sha(prompt),
        "source_record_sha256": sha(RECORD.read_bytes()),
        "source_exchange_sha256": sha(EXCHANGE.read_bytes()),
        "source_rollout_sha256": sha(rollout.read_bytes()),
        "source_ledger_sha256": sha(LEDGER.read_bytes()),
        "source_epoch_id": record["epoch_id"],
        "source_run_id": RUN_ID,
        "source_provenance_scope": "evaluator_only",
        "scored_p3": False,
        "qualification_data": False,
    }
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    root.chmod(0o700)
    visible = root / "visible"
    evaluator = root / "evaluator"
    visible.mkdir(mode=0o700)
    evaluator.mkdir(mode=0o700)
    for path, data in (
        (visible / "packet.md", packet),
        (evaluator / "manifest.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()),
    ):
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return {"packet_dir": str(visible), "evaluator_dir": str(evaluator), **manifest}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.out_dir), sort_keys=True))
