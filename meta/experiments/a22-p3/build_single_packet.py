#!/usr/bin/env python3
"""Build one opaque, blind scorer packet from a sealed P3 run and its exchange.

This tool is offline-only. It reads the sealed qualification map, seal, case,
scorer prompt, renderer, and one matching exchange. It never starts a model or
records scoring output. The evaluator mapping is kept in a separate file from
the sole model-visible packet. At this checkout, no sealed-map entry has a
matching exchange, so live packet generation fails closed until one is present.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SEAL_PATH = Path("seal.json")
SEALED_MAP_PATH = Path("runs/qual-sealed-map.json")
PROMPT_PATH = Path("scoring/scorer-prompt.txt")
RENDERER_PATH = Path("score_packets.py")
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
CASE_ID_RE = re.compile(r"P3-[0-9]{2}\Z")
OPAQUE_ID_RE = re.compile(r"g[0-9a-f]{16}\Z")
EVALUATOR_ARTIFACT_MODES = {"evaluator-map.json": 0o600, "manifest.json": 0o600}
PRIVATE_DIR_MODE = 0o700
P3_TURN_COUNT = 2


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {path.name}") from exc


def _sealed_bytes(root: Path, seal_files: dict[str, str], relative: Path) -> bytes:
    key = relative.as_posix()
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required sealed input is not a regular file: {key}")
    data = path.read_bytes()
    expected = seal_files.get(key)
    if not isinstance(expected, str) or _sha(data) != expected:
        raise ValueError(f"sealed input hash mismatch: {key}")
    return data


def _sealed_context(root: Path) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    seal_path = root / SEAL_PATH
    if seal_path.is_symlink() or not seal_path.is_file():
        raise ValueError("P3 seal is not a regular file")
    seal = _read_json(seal_path)
    seal_files = seal.get("files") if isinstance(seal, dict) else None
    if not isinstance(seal, dict) or seal.get("schema") != 1 or not isinstance(seal_files, dict):
        raise ValueError("unsupported or malformed P3 seal")
    map_bytes = _sealed_bytes(root, seal_files, SEALED_MAP_PATH)
    prompt_bytes = _sealed_bytes(root, seal_files, PROMPT_PATH)
    renderer_bytes = _sealed_bytes(root, seal_files, RENDERER_PATH)
    sealed_map = json.loads(map_bytes.decode("utf-8"))
    if not isinstance(sealed_map, dict):
        raise ValueError("sealed qualification map is malformed")
    if not prompt_bytes.strip() or not renderer_bytes.strip():
        raise ValueError("sealed prompt or packet renderer is empty")
    source_hashes = {
        "seal.json": _sha(seal_path.read_bytes()),
        SEALED_MAP_PATH.as_posix(): _sha(map_bytes),
        PROMPT_PATH.as_posix(): _sha(prompt_bytes),
        RENDERER_PATH.as_posix(): _sha(renderer_bytes),
    }
    return seal_files, sealed_map, source_hashes


def _load_case(root: Path, seal_files: dict[str, str], cell: dict[str, Any]) -> tuple[Path, bytes, list[str]]:
    case_id = cell.get("case")
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        raise ValueError("sealed source entry has an invalid case mapping")
    case_path = Path("cases") / f"{case_id}.json"
    case_bytes = _sealed_bytes(root, seal_files, case_path)
    case = json.loads(case_bytes.decode("utf-8"))
    scoring = case.get("scoring") if isinstance(case, dict) else None
    if not isinstance(scoring, list) or not scoring or not all(isinstance(row, str) and row.strip() for row in scoring):
        raise ValueError("sealed case has no valid scoring elements")
    return case_path, case_bytes, scoring


def _load_exchange(root: Path, source_run_id: str) -> tuple[bytes, list[dict[str, str]]]:
    exchange_path = root / "runs" / f"{source_run_id}.exchange.json"
    if exchange_path.is_symlink() or not exchange_path.is_file():
        raise ValueError("selected sealed entry has no matching exchange; no packet emitted")
    exchange_bytes = exchange_path.read_bytes()
    exchange = _read_json(exchange_path)
    turns = exchange.get("turns") if isinstance(exchange, dict) else None
    if not isinstance(turns, list) or len(turns) != P3_TURN_COUNT:
        raise ValueError("P3 source exchange must contain exactly two turns")
    normalized: list[dict[str, str]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            raise ValueError("P3 source exchange has a malformed turn")
        user, assistant = turn.get("user"), turn.get("assistant")
        if not isinstance(user, str) or not user.strip() or not isinstance(assistant, str) or not assistant.strip():
            raise ValueError("P3 source exchange has an empty or malformed turn")
        normalized.append({"user": user, "assistant": assistant})
    return exchange_bytes, normalized


def _verify_provenance(
    root: Path, source_run_id: str, cell: dict[str, Any], seal_files: dict[str, str]
) -> dict[str, str]:
    """Apply the qualification importer's record, exchange, event, and rollout checks."""
    grid_bytes = _sealed_bytes(root, seal_files, Path("grid.py"))
    grid_path = root / "grid.py"
    spec = importlib.util.spec_from_file_location("a22_p3_grid_for_packet", grid_path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load P3 qualification verifier")
    grid = importlib.util.module_from_spec(spec)
    source = compile(grid_bytes, str(grid_path), "exec")
    exec(source, grid.__dict__)  # noqa: S102 - executes bytes already matched to the seal hash
    return grid.verify_run(
        source_run_id,
        cell,
        root / "runs",
        root / "cases",
        root / "arms",
    )


def _destination(out_dir: Path, root: Path) -> tuple[Path, Path]:
    destination = out_dir.expanduser()
    if destination.is_symlink() or destination.exists():
        raise FileExistsError("packet output directory already exists")
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    evaluator_dir = destination.with_name(destination.name + ".evaluator")
    if evaluator_dir.is_symlink() or evaluator_dir.exists():
        raise FileExistsError("evaluator output directory already exists")
    packet_inside_project = destination.resolve(strict=False).is_relative_to(root)
    evaluator_inside_project = evaluator_dir.resolve(strict=False).is_relative_to(root)
    if packet_inside_project or evaluator_inside_project:
        raise ValueError("packet artifacts must be outside the sealed project tree")
    return destination, evaluator_dir


def _new_opaque_id() -> str:
    """Return a packet id that carries no source-run or condition label."""
    return f"g{secrets.token_hex(8)}"


def _render_packet(opaque_id: str, turns: list[dict[str, str]], scoring: list[str]) -> bytes:
    lines = [f"# Run {opaque_id}", "", "## Exchange"]
    for index, turn in enumerate(turns, 1):
        lines += [f"### Turn {index} user", "", turn["user"], "",
                  f"### Turn {index} subject", "", turn["assistant"], ""]
    lines += ["## Elements (PASS or FAIL, with one-line reason)", "", *scoring]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _write_exclusive(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def build_single_packet(source_run_id: str, out_dir: Path, *, project_root: Path = HERE) -> dict[str, Any]:
    """Write one model packet plus evaluator-only metadata; refuse any overwrite."""
    root = project_root.resolve(strict=True)
    if not RUN_ID_RE.fullmatch(source_run_id):
        raise ValueError("source run selector has an invalid form")
    seal_files, case_map, source_hashes = _sealed_context(root)
    if source_run_id not in case_map:
        raise ValueError("source run is not in the current sealed qualification map")
    cell = case_map[source_run_id]
    if not isinstance(cell, dict):
        raise ValueError("sealed source entry has no valid case mapping")
    case_path, case_bytes, scoring = _load_case(root, seal_files, cell)
    provenance = _verify_provenance(root, source_run_id, cell, seal_files)
    exchange_bytes, normalized_turns = _load_exchange(root, source_run_id)
    opaque_id = _new_opaque_id()
    if not OPAQUE_ID_RE.fullmatch(opaque_id) or opaque_id == source_run_id:
        raise ValueError("opaque packet id generator returned an invalid id")
    packet = _render_packet(opaque_id, normalized_turns, scoring)
    if source_run_id.encode("utf-8") in packet:
        raise ValueError("source run selector leaked into the model packet")

    destination, evaluator_destination = _destination(out_dir, root)

    evaluator_map = {
        "schema": 1,
        "opaque_packet_id": opaque_id,
        "source_run_id": source_run_id,
        "sealed_cell": cell,
        "provenance": provenance,
    }
    evaluator_bytes = (json.dumps(evaluator_map, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    packet_hash = _sha(packet)
    manifest = {
        "schema": 1,
        "record_type": "p3_single_scorer_packet",
        "opaque_packet_id": opaque_id,
        "model_visible_files": ["packet.md"],
        "model_visible_packet_count": 1,
        "packet_sha256": packet_hash,
        "evaluator_map_sha256": _sha(evaluator_bytes),
        "source_sha256": {
            **source_hashes,
            case_path.as_posix(): _sha(case_bytes),
            f"runs/{source_run_id}.exchange.json": _sha(exchange_bytes),
        },
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

    destination.mkdir(mode=PRIVATE_DIR_MODE, parents=False, exist_ok=False)
    destination.chmod(PRIVATE_DIR_MODE)
    evaluator_destination.mkdir(mode=PRIVATE_DIR_MODE, parents=False, exist_ok=False)
    evaluator_destination.chmod(PRIVATE_DIR_MODE)
    _write_exclusive(destination / "packet.md", packet)
    _write_exclusive(evaluator_destination / "evaluator-map.json", evaluator_bytes)
    _write_exclusive(evaluator_destination / "manifest.json", manifest_bytes)
    return {"opaque_packet_id": opaque_id, "packet_sha256": packet_hash,
            "packet_dir": str(destination), "evaluator_dir": str(evaluator_destination),
            "model_visible_packet_count": 1}


def verify_bundle(packet_dir: Path, evaluator_dir: Path) -> dict[str, Any]:  # noqa: C901
    """Verify the isolated model packet and its private evaluator metadata."""
    packet_path, evaluator_path = Path(packet_dir), Path(evaluator_dir)
    if packet_path.is_symlink() or evaluator_path.is_symlink():
        raise ValueError("packet bundle directory is not private")
    packet_root, evaluator_root = packet_path.resolve(strict=True), evaluator_path.resolve(strict=True)
    if (not packet_root.is_dir() or not evaluator_root.is_dir()
            or stat.S_IMODE(packet_root.stat().st_mode) != PRIVATE_DIR_MODE
            or stat.S_IMODE(evaluator_root.stat().st_mode) != PRIVATE_DIR_MODE):
        raise ValueError("packet bundle directory is not private")
    if {path.name for path in packet_root.iterdir()} != {"packet.md"}:
        raise ValueError("model-visible packet directory must contain only packet.md")
    if {path.name for path in evaluator_root.iterdir()} != set(EVALUATOR_ARTIFACT_MODES):
        raise ValueError("private evaluator directory has unexpected contents")
    for name, mode in {"packet.md": 0o600}.items():
        path = packet_root / name
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != mode:
            raise ValueError("packet bundle file is not private")
    for name, mode in EVALUATOR_ARTIFACT_MODES.items():
        path = evaluator_root / name
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != mode:
            raise ValueError("evaluator artifact is not private")
    manifest = _read_json(evaluator_root / "manifest.json")
    evaluator = _read_json(evaluator_root / "evaluator-map.json")
    packet = (packet_root / "packet.md").read_bytes()
    if manifest.get("record_type") != "p3_single_scorer_packet" or manifest.get("model_visible_files") != ["packet.md"]:
        raise ValueError("unsupported packet bundle manifest")
    if manifest.get("model_visible_packet_count") != 1 or manifest.get("packet_sha256") != _sha(packet):
        raise ValueError("packet count or content hash mismatch")
    if manifest.get("evaluator_map_sha256") != _sha((evaluator_root / "evaluator-map.json").read_bytes()):
        raise ValueError("evaluator mapping hash mismatch")
    if evaluator.get("opaque_packet_id") != manifest.get("opaque_packet_id"):
        raise ValueError("opaque packet id does not match evaluator mapping")
    return {"opaque_packet_id": manifest["opaque_packet_id"],
            "packet_sha256": manifest["packet_sha256"], "model_visible_packet_count": 1}


def main() -> int:
    """Build a packet bundle without invoking a scorer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run-id", required=True, help="evaluator-only key from the current sealed map")
    parser.add_argument("--out-dir", required=True, type=Path, help="new private output directory outside this project")
    parser.add_argument("--project-root", type=Path, default=HERE, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = build_single_packet(args.source_run_id, args.out_dir, project_root=args.project_root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
