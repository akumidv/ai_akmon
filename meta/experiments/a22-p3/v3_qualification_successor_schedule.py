#!/usr/bin/env python3
"""Create and verify the evaluator-only V3 A qualification schedule offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ID_LENGTH = 33
PACKET_ID_LENGTH = 17
SUBJECT_COUNT = 32
SCORER_COUNT = 64
TURN_COUNT = 2
PACKET_SEAL = HERE / "seal.json"
OLD_MAP = HERE / "runs" / "qual-sealed-map.json"
SCHEDULE = HERE / "runs" / "v3-qualification-successor-schedule-v1.json"
PRIOR_SCHEDULE = HERE / "runs" / "v3-qualification-schedule-v1.json"
TIERS = ("strongest", "mid")
ROUTES = ("codex", "qwen")
CASES = tuple(f"P3-{number:02d}" for number in range(1, 9))


class ScheduleError(ValueError):
    """The candidate schedule is incomplete or differs from the frozen packet."""


def sha(data: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> Any:
    """Read a regular JSON file without following a symlink."""
    if path.is_symlink() or not path.is_file():
        raise ScheduleError(f"missing or linked input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def packet_hashes() -> dict[str, str]:
    """Recheck every input this schedule uses against the original packet seal."""
    sealed = read(PACKET_SEAL)
    files = sealed.get("files")
    if not isinstance(files, dict):
        raise ScheduleError("packet seal has no file map")
    needed = ["runs/qual-sealed-map.json", "arms/A.architect.system.txt"]
    needed += [f"cases/{case}.json" for case in CASES]
    hashes: dict[str, str] = {}
    for relative in needed:
        path = HERE / relative
        if path.is_symlink() or not path.is_file():
            raise ScheduleError(f"packet input missing or linked: {relative}")
        digest = sha(path.read_bytes())
        if files.get(relative) != digest:
            raise ScheduleError(f"packet input differs from seal: {relative}")
        hashes[relative] = digest
    return hashes


def cells() -> list[dict[str, Any]]:
    """Define the fixed 32-cell A grid before any qualification result exists."""
    return [
        {"case": case, "arm": "A", "tier": tier, "repeat": repeat}
        for case in CASES
        for tier in TIERS
        for repeat in (1, 2)
    ]


def prior_ids() -> set[str]:
    """Exclude every ID already reserved by the terminal qualification attempt."""
    previous = read(PRIOR_SCHEDULE)
    ids: set[str] = set()
    for row in previous["cells"]:
        ids.update((row["run_id"], row["subject_attempt_id"], row["packet_id"]))
        ids.update(row["subject_call_ids"])
        ids.update(item["call_id"] for item in row["scorers"])
    return ids


def build_schedule(*, new_id: Any = None, shuffle: Any = None) -> dict[str, Any]:
    """Prepare fresh IDs and both fixed scorer orders without provider work."""
    new_id = new_id or (lambda: f"g{secrets.token_hex(16)}")
    shuffle = shuffle or secrets.SystemRandom().shuffle
    hashes = packet_hashes()
    old_ids = set(read(OLD_MAP))
    work = cells()
    shuffle(work)
    seen = set(old_ids) | prior_ids()

    def fresh(*, packet: bool = False) -> str:
        value = new_id()
        if packet and isinstance(value, str) and len(value) == ID_LENGTH:
            value = value[:PACKET_ID_LENGTH]
        expected_length = PACKET_ID_LENGTH if packet else ID_LENGTH
        if not isinstance(value, str) or len(value) != expected_length or not value.startswith("g"):
            raise ScheduleError("generated ID has an invalid shape")
        if any(character not in "0123456789abcdef" for character in value[1:]) or value in seen:
            raise ScheduleError("generated ID aliases packet history or another ID")
        seen.add(value)
        return value

    result = []
    for cell in work:
        case = read(HERE / "cases" / f"{cell['case']}.json")
        if case.get("id") != cell["case"] or not isinstance(case.get("subject"), dict):
            raise ScheduleError("case ID or subject is malformed")
        if not isinstance(case["subject"].get("no_item_reply"), str):
            raise ScheduleError("case lacks frozen second-turn fallback")
        run_id = fresh()
        route_order = list(ROUTES if len(result) % 2 == 0 else reversed(ROUTES))
        result.append(
            {
                **cell,
                "run_id": run_id,
                "subject_attempt_id": fresh(),
                "subject_call_ids": [fresh(), fresh()],
                "packet_id": fresh(packet=True),
                "scorers": [{"route": route, "call_id": fresh()} for route in route_order],
                "turn2_no_item_reply_sha256": sha(case["subject"]["no_item_reply"].encode()),
                "turn2_menu_sha256": sha(json.dumps(case["subject"].get("menu"), sort_keys=True).encode()),
                "element_ids": [row.split(":", 1)[0] for row in case["scoring"]],
            }
        )
    return {
        "schema": 1,
        "record_type": "p3_v3_qualification_successor_schedule_candidate",
        "phase": "qualification",
        "scored_subject_count": SUBJECT_COUNT,
        "scorer_pass_count": SCORER_COUNT,
        "packet_seal_sha256": sha(PACKET_SEAL.read_bytes()),
        "packet_input_sha256": hashes,
        "cells": result,
        "provider_calls_started": 0,
        "status": "offline_candidate_pending_operational_seal_and_owner_acceptance",
    }


def verify_schedule(value: dict[str, Any]) -> None:  # noqa: C901 - complete fail-closed candidate gate
    """Reject missing, duplicate, stale or re-labelled cells and call IDs."""
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "record_type",
        "phase",
        "scored_subject_count",
        "scorer_pass_count",
        "packet_seal_sha256",
        "packet_input_sha256",
        "cells",
        "provider_calls_started",
        "status",
    }:
        raise ScheduleError("schedule envelope differs")
    if (
        value["schema"] != 1
        or value["record_type"] != "p3_v3_qualification_successor_schedule_candidate"
        or value["phase"] != "qualification"
        or value["scored_subject_count"] != SUBJECT_COUNT
        or value["scorer_pass_count"] != SCORER_COUNT
        or value["packet_seal_sha256"] != sha(PACKET_SEAL.read_bytes())
        or value["packet_input_sha256"] != packet_hashes()
        or value["provider_calls_started"] != 0
        or value["status"] != "offline_candidate_pending_operational_seal_and_owner_acceptance"
        or not isinstance(value["cells"], list)
        or len(value["cells"]) != SUBJECT_COUNT
    ):
        raise ScheduleError("schedule header or packet binding differs")
    expected = {(row["case"], row["tier"], row["repeat"]) for row in cells()}
    found: set[tuple[str, str, int]] = set()
    ids: set[str] = set(read(OLD_MAP)) | prior_ids()
    for index, row in enumerate(value["cells"]):
        if not isinstance(row, dict) or set(row) != {
            "case",
            "arm",
            "tier",
            "repeat",
            "run_id",
            "subject_attempt_id",
            "subject_call_ids",
            "packet_id",
            "scorers",
            "turn2_no_item_reply_sha256",
            "turn2_menu_sha256",
            "element_ids",
        }:
            raise ScheduleError("qualification row schema differs")
        cell = (row["case"], row["tier"], row["repeat"])
        if cell not in expected or cell in found or row["arm"] != "A":
            raise ScheduleError("qualification cell is missing, repeated or not A")
        found.add(cell)
        case = read(HERE / "cases" / f"{row['case']}.json")
        if (
            row["turn2_no_item_reply_sha256"] != sha(case["subject"]["no_item_reply"].encode())
            or row["turn2_menu_sha256"] != sha(json.dumps(case["subject"].get("menu"), sort_keys=True).encode())
            or row["element_ids"] != [item.split(":", 1)[0] for item in case["scoring"]]
            or len(row["subject_call_ids"]) != TURN_COUNT
            or len(row["scorers"]) != len(ROUTES)
            or [item["route"] for item in row["scorers"]] != list(ROUTES if index % 2 == 0 else reversed(ROUTES))
        ):
            raise ScheduleError("frozen turn-two, rubric IDs or scorer order differs")
        identifiers = [row["run_id"], row["subject_attempt_id"], *row["subject_call_ids"]]
        packet_id = row["packet_id"]
        if (
            not isinstance(packet_id, str)
            or len(packet_id) != PACKET_ID_LENGTH
            or not packet_id.startswith("g")
            or any(char not in "0123456789abcdef" for char in packet_id[1:])
            or packet_id in ids
        ):
            raise ScheduleError("scorer packet ID is malformed or duplicated")
        ids.add(packet_id)
        for scorer in row["scorers"]:
            if set(scorer) != {"route", "call_id"}:
                raise ScheduleError("scorer row schema differs")
            identifiers.append(scorer["call_id"])
        for identifier in identifiers:
            if (
                not isinstance(identifier, str)
                or len(identifier) != ID_LENGTH
                or not identifier.startswith("g")
                or any(char not in "0123456789abcdef" for char in identifier[1:])
                or identifier in ids
            ):
                raise ScheduleError("qualification ID is malformed or collides with history")
            ids.add(identifier)
    if found != expected:
        raise ScheduleError("qualification grid is incomplete")


def main() -> None:
    """Create once, or verify without changing the schedule."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    args = parser.parse_args()
    if args.action == "prepare":
        if SCHEDULE.exists() or SCHEDULE.is_symlink():
            raise ScheduleError("candidate schedule already exists")
        value = build_schedule()
        verify_schedule(value)
        payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
        fd = os.open(SCHEDULE, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        verify_schedule(read(SCHEDULE))
    print(json.dumps({"status": "PASSED_OFFLINE_SCHEDULE", "sha256": sha(SCHEDULE.read_bytes())}))


if __name__ == "__main__":
    main()
