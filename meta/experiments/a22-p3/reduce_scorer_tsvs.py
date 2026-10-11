#!/usr/bin/env python3
"""Reduce two blind scorer TSVs to private grid-import TSVs, offline only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HEADER = ["run_id", "element", "verdict", "reason"]
TSV_COLUMN_COUNT = 4
ELEMENT_RE = re.compile(r"^(E[1-9][0-9]*):\s*.+$")
OPAQUE_RE = re.compile(r"g[0-9a-f]{16}\Z")
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def sha(data: bytes) -> str:
    """Return the SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def _load_evaluator_bundles(bundle_root: Path) -> dict[str, dict[str, Any]]:  # noqa: C901, PLR0912
    root = bundle_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("packet bundle root is not a directory")
    builder_path = HERE / "build_single_packet.py"
    spec = importlib.util.spec_from_file_location("a22_p3_packet_verifier_for_reducer", builder_path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load P3 packet verifier")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    _seal_files, _sealed_map, sealed_hashes = builder._sealed_context(HERE)
    expected_prompt_sha256 = sealed_hashes["scoring/scorer-prompt.txt"]
    found: dict[str, dict[str, Any]] = {}
    source_ids: set[str] = set()
    map_kinds: set[str] = set()
    for evaluator_dir in sorted(root.glob("*.evaluator")):
        packet_dir = evaluator_dir.with_name(evaluator_dir.name.removesuffix(".evaluator"))
        verified = builder.verify_bundle(packet_dir, evaluator_dir)
        manifest = json.loads((evaluator_dir / "manifest.json").read_text(encoding="utf-8"))
        evaluator = json.loads((evaluator_dir / "evaluator-map.json").read_text(encoding="utf-8"))
        opaque_id = verified["opaque_packet_id"]
        source_id = evaluator.get("source_run_id")
        if (not OPAQUE_RE.fullmatch(opaque_id) or not isinstance(source_id, str)
                or not RUN_ID_RE.fullmatch(source_id)
                or manifest.get("source_map_kind") != evaluator.get("source_map_kind")
                or manifest.get("record_type") != "p3_single_scorer_packet"):
            raise ValueError("private evaluator mapping has invalid packet provenance")
        if source_id in source_ids:
            raise ValueError("duplicate source run ID in evaluator bundles")
        source_ids.add(source_id)
        map_kinds.add(evaluator["source_map_kind"])
        packet_text = (packet_dir / "packet.md").read_text(encoding="utf-8")
        try:
            scoring_text = packet_text.split("## Elements (PASS or FAIL, with one-line reason)\n\n", 1)[1]
        except IndexError as exc:
            raise ValueError("model packet has no scoring section") from exc
        element_ids = []
        for line in scoring_text.splitlines():
            if not line.strip():
                continue
            match = ELEMENT_RE.fullmatch(line)
            if not match:
                raise ValueError("model packet contains malformed scoring elements")
            element_ids.append(match.group(1))
        if element_ids != ["E1", "E2", "E3", "E4"]:
            raise ValueError("P3 scorer packet must contain exactly E1-E4")
        if opaque_id in found:
            raise ValueError("duplicate opaque packet ID in evaluator bundles")
        found[opaque_id] = {"source_run_id": source_id, "elements": set(element_ids),
                            "packet_sha256": verified["packet_sha256"],
                            "prompt_sha256": expected_prompt_sha256,
                            "evaluator_map_sha256": sha((evaluator_dir / "evaluator-map.json").read_bytes())}
    if not found:
        raise ValueError("no private evaluator bundles found")
    if len(map_kinds) != 1:
        raise ValueError("evaluator bundles mix source map kinds")
    return found


def _read_scores(path: Path, bundles: dict[str, dict[str, Any]]) -> dict[str, dict[str, tuple[str, str]]]:
    scores: dict[str, dict[str, tuple[str, str]]] = {}
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        if next(reader, None) != HEADER:
            raise ValueError(f"{path.name}: scorer TSV header mismatch")
        for line_number, row in enumerate(reader, 2):
            if len(row) != TSV_COLUMN_COUNT:
                raise ValueError(f"{path.name}:{line_number}: expected four TSV columns")
            opaque_id, element, verdict, reason = row
            if opaque_id not in bundles:
                raise ValueError(f"{path.name}:{line_number}: unknown opaque packet ID")
            if (element not in bundles[opaque_id]["elements"] or verdict not in {"PASS", "FAIL"}
                    or not reason.strip() or any(char in reason for char in "\r\n\t")):
                raise ValueError(f"{path.name}:{line_number}: invalid element, verdict, or reason")
            rows = scores.setdefault(opaque_id, {})
            if element in rows:
                raise ValueError(f"{path.name}:{line_number}: duplicate element row")
            rows[element] = (verdict, reason)
    if set(scores) != set(bundles):
        raise ValueError(f"{path.name}: opaque packet IDs do not match evaluator bundles")
    for opaque_id, rows in scores.items():
        if set(rows) != bundles[opaque_id]["elements"]:
            raise ValueError(f"{path.name}: incomplete element set for an opaque packet")
    return scores


def _load_ledger() -> Any:
    path = HERE / "usage_ledger_v2.py"
    spec = importlib.util.spec_from_file_location("a22_p3_reducer_usage_ledger", path)
    if spec is None or spec.loader is None:
        raise ValueError("shared usage ledger is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _accepted_readings(ledger: Any) -> dict[str, dict[str, Any]]:
    """Replay the authoritative ledger and index accepted scorer attempts by call ID."""
    ledger_path, plan_path, seal_path, approval_path = ledger.DEFAULT_PATHS
    _header, events, states = ledger._read(ledger_path, plan_path, seal_path, approval_path,
                                            allow_stale_approval=True)
    reservations = {event["attempt_id"]: event for event in events if event.get("event") == "reserved"}
    completions = {event["attempt_id"]: event for event in events if event.get("event") == "completed"}
    accepted: dict[str, dict[str, Any]] = {}
    seen_packets: set[tuple[str, str]] = set()
    for call_id, reservation in reservations.items():
        state = states.get(call_id)
        completion = completions.get(call_id)
        if (state is None or reservation.get("attempt_class") != "scored_reading"
                or state.get("state") != "accepted" or completion is None
                or completion.get("outcome") != "accepted"):
            continue
        artifact = completion.get("usage_artifact")
        try:
            raw = (ledger_path.parent / artifact["artifact_path"]).read_bytes()
            evidence = json.loads(raw).get("evidence")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError("accepted scored-reading ledger artifact is unreadable") from exc
        if (not isinstance(evidence, dict) or not isinstance(evidence.get("opaque_packet_id"), str)
                or not isinstance(evidence.get("packet_sha256"), str)):
            raise ValueError("accepted scored-reading ledger artifact lacks packet identity")
        packet_key = (reservation["route"], evidence["opaque_packet_id"])
        if packet_key in seen_packets:
            raise ValueError("ledger contains more than one accepted reading per route and packet")
        seen_packets.add(packet_key)
        accepted[call_id] = {"route": reservation["route"],
                             "usage": completion.get("actual_usage"),
                             "usage_artifact": artifact,
                             "opaque_packet_id": evidence["opaque_packet_id"],
                             "packet_sha256": evidence["packet_sha256"]}
    return accepted


def _receipt(path: Path, bundles: dict[str, dict[str, Any]], accepted: dict[str, dict[str, Any]],  # noqa: C901
             ledger: Any) -> dict[str, Any]:
    """Validate that an input is the exact final TSV from an accepted ledger-backed reading."""
    source = path.resolve(strict=True)
    if not source.is_file():
        raise ValueError("scorer input is not a regular file")
    receipt_dir = source.parent
    try:
        attempt = json.loads((receipt_dir / "attempt.json").read_text(encoding="utf-8"))
        outcome = json.loads((receipt_dir / "outcome.json").read_text(encoding="utf-8"))
        final_path = receipt_dir / "final.tsv"
        final = final_path.read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("scorer input lacks a complete scored-reading receipt") from exc
    if source != final_path.resolve(strict=True):
        raise ValueError("scorer input must be the canonical final.tsv in its receipt directory")
    if (attempt.get("record_type") != "p3_scored_reading" or attempt.get("status") != "invoking"
            or outcome.get("status") != "SCORED_READING_ACCEPTED"
            or outcome.get("ledger_outcome") != "accepted"
            or outcome.get("scored_p3") is not True or outcome.get("qualification_data") is not True):
        raise ValueError("scorer receipt is not an accepted scored reading")
    call_id = attempt.get("attempt_id")
    if (not isinstance(call_id, str) or outcome.get("attempt_id") != call_id
            or outcome.get("request_id") != attempt.get("request_id")
            or outcome.get("opaque_packet_id") != attempt.get("opaque_packet_id")
            or outcome.get("model_id") != attempt.get("model_requested")
            or not isinstance(outcome.get("session_id"), str) or not outcome["session_id"]):
        raise ValueError("scorer receipt identity fields do not agree")
    ledger_row = accepted.get(call_id)
    if ledger_row is None:
        raise ValueError("scorer receipt has no accepted scored-reading ledger event")
    if (ledger_row.get("opaque_packet_id") != attempt.get("opaque_packet_id")
            or ledger_row.get("packet_sha256") != attempt.get("packet_sha256")):
        raise ValueError("scorer receipt packet does not match its accepted ledger event")
    artifact = outcome.get("usage_artifact")
    ledger_artifact = ledger_row.get("usage_artifact")
    if artifact != ledger_artifact or artifact is None:
        raise ValueError("scorer receipt usage artifact does not match its ledger event")
    artifact_path = ledger.DEFAULT_PATHS[0].parent / artifact["artifact_path"]
    try:
        raw_artifact = artifact_path.read_bytes()
        saved = json.loads(raw_artifact)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("scorer receipt usage artifact is unavailable") from exc
    digest = sha(final)
    if (sha(raw_artifact) != artifact.get("artifact_sha256")
            or artifact.get("call_id") != call_id
            or artifact.get("session_id") != outcome.get("session_id")
            or artifact.get("model_id") != attempt.get("model_requested")
            or saved.get("call_id") != call_id or saved.get("session_id") != outcome.get("session_id")
            or saved.get("model_id") != attempt.get("model_requested")
            or saved.get("usage") != ledger_row.get("usage")
            or saved.get("evidence", {}).get("tsv_sha256") != digest
            or saved.get("evidence", {}).get("packet_sha256") != attempt.get("packet_sha256")
            or saved.get("evidence", {}).get("request_sha256") != attempt.get("request_sha256")
            or saved.get("evidence", {}).get("opaque_packet_id") != attempt.get("opaque_packet_id")
            or outcome.get("tsv_sha256") != digest):
        raise ValueError("scorer TSV is not bound to the accepted usage artifact")
    opaque_id = attempt.get("opaque_packet_id")
    if (opaque_id not in bundles or attempt.get("packet_sha256") != bundles[opaque_id]["packet_sha256"]
            or attempt.get("prompt_sha256") != bundles[opaque_id]["prompt_sha256"]):
        raise ValueError("scorer receipt does not match the expected opaque packet and prompt")
    route = attempt.get("route")
    expected_model = {"codex": "gpt-6-astra", "qwen": "qwen3.8-27b"}.get(route)
    if (route not in {"codex", "qwen"} or ledger_row.get("route") != route
            or artifact.get("model_id") != attempt.get("model_requested")
            or attempt.get("model_requested") != expected_model):
        raise ValueError("scorer receipt route or model does not match its ledger reservation")
    return {"call_id": call_id, "route": route, "model_id": attempt["model_requested"],
            "opaque_packet_id": opaque_id, "packet_sha256": attempt["packet_sha256"],
            "prompt_sha256": attempt["prompt_sha256"], "sha256": digest, "path": source}


def _read_receipt_set(root: Path, bundles: dict[str, dict[str, Any]],
                      accepted: dict[str, dict[str, Any]], ledger: Any,
                      expected_route: str) -> tuple[dict[str, dict[str, tuple[str, str]]], list[dict[str, Any]]]:
    if not root.is_dir():
        raise ValueError("each scorer input must be a directory of accepted reading receipts")
    paths = sorted(root.rglob("final.tsv"))
    receipts: list[dict[str, Any]] = []
    scores: dict[str, dict[str, tuple[str, str]]] = {}
    for path in paths:
        receipt = _receipt(path, bundles, accepted, ledger)
        if receipt["route"] != expected_route:
            raise ValueError("scorer receipt is filed under the wrong route input")
        opaque_id = receipt["opaque_packet_id"]
        if opaque_id in scores:
            raise ValueError("duplicate accepted scorer reading for an opaque packet")
        scores[opaque_id] = _read_scores(path, {opaque_id: bundles[opaque_id]})[opaque_id]
        receipts.append(receipt)
    if set(scores) != set(bundles):
        raise ValueError("accepted scorer receipts do not cover the full expected packet set")
    if len({item["call_id"] for item in receipts}) != len(receipts):
        raise ValueError("scorer receipt call ID is duplicated")
    return scores, receipts


def reduce_scores(scorer1_path: Path, scorer2_path: Path, bundle_root: Path,  # noqa: C901
                  out_dir: Path) -> dict[str, Any]:
    """Validate full receipt directories, then privately map opaque IDs to source IDs."""
    bundles = _load_evaluator_bundles(bundle_root)
    if scorer1_path.resolve(strict=True) == scorer2_path.resolve(strict=True):
        raise ValueError("scorer inputs must be distinct accepted readings")
    if not scorer1_path.is_dir() or not scorer2_path.is_dir():
        raise ValueError("each scorer input must be a directory of accepted reading receipts")
    ledger = _load_ledger()
    accepted = _accepted_readings(ledger)
    expected_packets = {(route, opaque_id) for route in ("codex", "qwen") for opaque_id in bundles}
    ledger_packets = {(row["route"], row["opaque_packet_id"]) for row in accepted.values()}
    if ledger_packets != expected_packets:
        raise ValueError("accepted scorer ledger readings do not cover the full route and packet matrix")
    scorer1, receipts1 = _read_receipt_set(scorer1_path, bundles, accepted, ledger, "codex")
    scorer2, receipts2 = _read_receipt_set(scorer2_path, bundles, accepted, ledger, "qwen")
    by_packet1 = {item["opaque_packet_id"]: item for item in receipts1}
    by_packet2 = {item["opaque_packet_id"]: item for item in receipts2}
    if set(by_packet1) != set(by_packet2):
        raise ValueError("scorer receipts do not cover the same packet set")
    for opaque_id in bundles:
        left, right = by_packet1[opaque_id], by_packet2[opaque_id]
        if (left["packet_sha256"] != right["packet_sha256"]
                or left["prompt_sha256"] != right["prompt_sha256"]
                or left["call_id"] == right["call_id"]
                or left["model_id"] == right["model_id"]):
            raise ValueError("scorer receipts do not prove independent readings of the same packet and prompt")
    destination = out_dir.expanduser().absolute()
    if destination.is_symlink() or destination.exists():
        raise FileExistsError("reducer output directory already exists")
    destination.parent.resolve(strict=True)
    resolved_destination = destination.resolve(strict=False)
    if resolved_destination.is_relative_to(HERE.resolve()):
        raise ValueError("reducer artifacts must be outside the sealed project tree")
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    destination.chmod(0o700)
    outputs = []
    for scorer_index, scores in ((1, scorer1), (2, scorer2)):
        path = destination / f"scorer-{scorer_index}-grid.tsv"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
            for opaque_id in sorted(bundles):
                source_id = bundles[opaque_id]["source_run_id"]
                for element in sorted(bundles[opaque_id]["elements"]):
                    verdict, reason = scores[opaque_id][element]
                    writer.writerow([source_id, element, verdict, reason])
            stream.flush()
            os.fsync(stream.fileno())
        outputs.append(path)
    manifest = {"schema": 1, "record_type": "p3_private_grid_scorer_pair",
                "packet_count": len(bundles), "source_scorer_sha256": [
                    sha("\n".join(sorted(item["sha256"] for item in receipts1)).encode()),
                    sha("\n".join(sorted(item["sha256"] for item in receipts2)).encode())],
                "grid_tsv_sha256": [sha(outputs[0].read_bytes()), sha(outputs[1].read_bytes())],
                "opaque_packet_ids": sorted(bundles)}
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    return {"packet_count": len(bundles), "output_dir": str(destination.resolve())}


def main() -> int:
    """Run the offline scorer-pair reducer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorer-1", required=True, type=Path, help="directory of Codex accepted-reading receipts")
    parser.add_argument("--scorer-2", required=True, type=Path, help="directory of Qwen accepted-reading receipts")
    parser.add_argument("--bundle-root", required=True, type=Path,
                        help="directory containing packet and .evaluator pairs")
    parser.add_argument("--out-dir", required=True, type=Path, help="new private directory, outside the project tree")
    args = parser.parse_args()
    try:
        result = reduce_scores(args.scorer_1, args.scorer_2, args.bundle_root, args.out_dir)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
