#!/usr/bin/env python3
"""Render one V3 A exchange for both blind scorers without dispatching either."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import v3_qualification_schedule as schedule

HERE = Path(__file__).resolve().parent
RENDERER = HERE / "build_single_packet.py"
PROMPT = HERE / "scoring" / "scorer-prompt.txt"
PACKET_ID = re.compile(r"g[0-9a-f]{16}\Z")


class PacketError(ValueError):
    """The exchange or scorer-visible rendering differs from frozen inputs."""


def sha(data: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(data).hexdigest()


def sealed_bytes(relative: str) -> bytes:
    """Read a packet input only when it matches the original seal."""
    path = HERE / relative
    sealed = schedule.read(schedule.PACKET_SEAL).get("files", {})
    if path.is_symlink() or not path.is_file():
        raise PacketError(f"sealed input is absent or linked: {relative}")
    data = path.read_bytes()
    if sealed.get(relative) != sha(data):
        raise PacketError(f"sealed input differs: {relative}")
    return data


def render(row: dict[str, Any], exchange: dict[str, Any]) -> tuple[bytes, bytes]:
    """Return identical packet/request bytes for Codex and Qwen."""
    candidate = schedule.read(schedule.SCHEDULE)
    schedule.verify_schedule(candidate)
    if row not in candidate["cells"]:
        raise PacketError("cell is absent from the fresh V3 schedule")
    case = json.loads(sealed_bytes(f"cases/{row['case']}.json"))
    turns = exchange.get("turns") if isinstance(exchange, dict) else None
    if (
        not isinstance(exchange, dict)
        or not isinstance(row, dict)
        or exchange.get("run_id") != row["run_id"]
        or not isinstance(turns, list)
        or len(turns) != schedule.TURN_COUNT
        or any(
            not isinstance(turn, dict)
            or not isinstance(turn.get("user"), str)
            or not turn["user"].strip()
            or not isinstance(turn.get("assistant"), str)
            or not turn["assistant"].strip()
            for turn in turns
        )
        or turns[0]["user"] != case["subject"]["turn1"]
    ):
        raise PacketError("source exchange is incomplete or not this sealed case")
    import v3_runner_version_successor as source  # noqa: PLC0415 - keep frozen source loader local

    expected_second = source._second_prompt(case, turns[0]["assistant"])[2]
    if turns[1]["user"] != expected_second:
        raise PacketError("second user turn differs from frozen case response")
    packet_id = row["packet_id"]
    if not PACKET_ID.fullmatch(packet_id):
        raise PacketError("scorer packet ID is malformed")
    # Use the original renderer's frozen bytes, but pass only the observed exchange
    # and evaluator-held scoring criteria. The subject sees neither field.
    renderer = sealed_bytes("build_single_packet.py")
    namespace: dict[str, Any] = {"__name__": "v3_qualification_frozen_renderer", "__file__": str(RENDERER)}
    exec(compile(renderer, str(RENDERER), "exec"), namespace)  # noqa: S102 - exact sealed source bytes
    visible = namespace["_render_packet"](
        packet_id,
        [{"user": turn["user"], "assistant": turn["assistant"]} for turn in turns],
        case["scoring"],
    )
    if any(marker.encode() in visible for marker in (row["run_id"], row["subject_attempt_id"], row["tier"])):
        raise PacketError("evaluator identity leaked into scorer packet")
    prompt = sealed_bytes("scoring/scorer-prompt.txt")
    sealed_bytes("scorer_route_check.py")
    import scorer_route_check as scorer  # noqa: PLC0415 - frozen request constructor

    request = scorer.make_request(prompt, visible)
    return visible, request
