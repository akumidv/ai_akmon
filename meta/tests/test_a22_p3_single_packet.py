from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "experiments" / "a22-p3" / "build_single_packet.py"
SPEC = importlib.util.spec_from_file_location("a22_p3_single_packet", MODULE_PATH)
assert SPEC and SPEC.loader
packet_builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packet_builder)

REDUCER_PATH = MODULE_PATH.with_name("reduce_scorer_tsvs.py")
REDUCER_SPEC = importlib.util.spec_from_file_location("a22_p3_reduce_scorer_tsvs", REDUCER_PATH)
assert REDUCER_SPEC and REDUCER_SPEC.loader
scorer_reducer = importlib.util.module_from_spec(REDUCER_SPEC)
REDUCER_SPEC.loader.exec_module(scorer_reducer)


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _fixture(root: Path) -> tuple[str, Path]:
    run_id = "q1234"
    files = {
        "runs/qual-sealed-map.json": json.dumps({run_id: {
            "case": "P3-01", "arm": "A", "tier": "tier-secret-max",
            "repeat": 1, "qualification_label": "qualification-secret",
            "subject_model": "model-secret-name",
        }}, sort_keys=True).encode(),
        "cases/P3-01.json": json.dumps({"scoring": [
            "E1: first criterion", "E2: second criterion", "E3: third criterion", "E4: fourth criterion",
        ]}, sort_keys=True).encode(),
        "scoring/scorer-prompt.txt": b"Frozen scorer instructions.\n",
        "score_packets.py": b"# sealed production renderer\n",
        "arms/A.architect.system.txt": b"frozen arm A\n",
        "grid.py": (packet_builder.HERE / "grid.py").read_bytes(),
    }
    for name, content in files.items():
        _write(root / name, content)
    event_hashes = ["event-hash-1", "event-hash-2"]
    exchange = {
        "turns": [
            {"user": "First packet question.", "assistant": "First subject response.",
             "events_sha256": event_hashes[0]},
            {"user": "Follow-up packet question.", "assistant": "Final subject response.",
             "events_sha256": event_hashes[1]},
        ],
        "run_id": run_id,
        "arm": "arm-secret-A", "tier": "tier-secret-max", "qualification_label": "qualification-secret",
        "subject_model": "model-secret-name",
    }
    exchange_bytes = json.dumps(exchange, sort_keys=True).encode()
    _write(root / "runs" / f"{run_id}.exchange.json", exchange_bytes)
    record = {
        "run_id": run_id, "case": "P3-01", "arm": "A", "tier": "tier-secret-max", "repeat": 1,
        "verified": True,
        "case_sha256": hashlib.sha256(files["cases/P3-01.json"]).hexdigest(),
        "arm_sha256": hashlib.sha256(files["arms/A.architect.system.txt"]).hexdigest(),
        "exchange_sha256": hashlib.sha256(exchange_bytes).hexdigest(),
        "events_sha256": event_hashes,
        "rollout": {"verified": True, "sha256": "verified-rollout-hash"},
    }
    _write(root / "runs" / f"{run_id}.record.json", json.dumps(record, sort_keys=True).encode())
    seal = {"schema": 1, "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    _write(root / "seal.json", json.dumps(seal, sort_keys=True).encode())
    out_dir = root.parent / "packet-output"
    return run_id, out_dir


def _fixed_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(packet_builder, "_new_opaque_id", lambda: "g0123456789abcdef")


def test_builds_one_blind_packet_and_separate_evaluator_mapping(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)

    result = packet_builder.build_single_packet(run_id, out_dir, project_root=root)

    packet = (out_dir / "packet.md").read_text(encoding="utf-8")
    evaluator_dir = out_dir.with_name(out_dir.name + ".evaluator")
    evaluator = json.loads((evaluator_dir / "evaluator-map.json").read_text(encoding="utf-8"))
    packet_builder.verify_bundle(out_dir, evaluator_dir)
    manifest = json.loads((evaluator_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["opaque_packet_id"] == "g0123456789abcdef"
    assert packet.startswith("# Run g0123456789abcdef\n")
    assert "First subject response." in packet and "Final subject response." in packet
    assert "arm-secret-A" not in packet
    assert "tier-secret-max" not in packet
    assert "qualification-secret" not in packet
    assert "model-secret-name" not in packet
    assert run_id not in packet and "P3-01" not in packet
    assert len(list(out_dir.glob("*.md"))) == 1
    assert {path.name for path in out_dir.iterdir()} == {"packet.md"}
    assert {path.name for path in evaluator_dir.iterdir()} == {"evaluator-map.json", "manifest.json"}
    assert evaluator["opaque_packet_id"] == manifest["opaque_packet_id"]
    assert evaluator["source_run_id"] == run_id
    assert evaluator["sealed_cell"]["arm"] == "A"
    assert manifest["model_visible_files"] == ["packet.md"]
    assert manifest["model_visible_packet_count"] == 1
    assert manifest["packet_sha256"] == hashlib.sha256((out_dir / "packet.md").read_bytes()).hexdigest()
    assert stat.S_IMODE(out_dir.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in out_dir.iterdir())
    assert stat.S_IMODE(evaluator_dir.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in evaluator_dir.iterdir())


def test_existing_bundle_is_never_overwritten(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)
    packet_builder.build_single_packet(run_id, out_dir, project_root=root)
    before = {path.name: path.read_bytes() for path in out_dir.iterdir()}
    evaluator_dir = out_dir.with_name(out_dir.name + ".evaluator")
    evaluator_before = {path.name: path.read_bytes() for path in evaluator_dir.iterdir()}

    with pytest.raises(FileExistsError, match="already exists"):
        packet_builder.build_single_packet(run_id, out_dir, project_root=root)

    assert {path.name: path.read_bytes() for path in out_dir.iterdir()} == before
    assert {path.name: path.read_bytes() for path in evaluator_dir.iterdir()} == evaluator_before


def test_sealed_input_hash_mismatch_fails_before_output(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)
    map_path = root / "runs" / "qual-sealed-map.json"
    map_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="sealed input hash mismatch"):
        packet_builder.build_single_packet(run_id, out_dir, project_root=root)

    assert not out_dir.exists()


def test_unsealed_grid_verifier_tampering_fails_before_import_or_output(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)
    (root / "grid.py").write_text("raise AssertionError('untrusted verifier executed')\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"sealed input hash mismatch: grid.py"):
        packet_builder.build_single_packet(run_id, out_dir, project_root=root)

    assert not out_dir.exists()


def test_nonsealed_selector_and_missing_exchange_fail_closed(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)

    with pytest.raises(ValueError, match="not in the selected verified source map"):
        packet_builder.build_single_packet("other1", out_dir, project_root=root)
    (root / "runs" / f"{run_id}.exchange.json").unlink()
    with pytest.raises(ValueError, match="missing verified record or exchange"):
        packet_builder.build_single_packet(run_id, out_dir, project_root=root)

    assert not out_dir.exists()


def test_bundle_verification_detects_packet_tampering(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)
    packet_builder.build_single_packet(run_id, out_dir, project_root=root)
    with (out_dir / "packet.md").open("ab") as stream:
        stream.write(b"changed\n")

    with pytest.raises(ValueError, match="content hash mismatch"):
        packet_builder.verify_bundle(out_dir, out_dir.with_name(out_dir.name + ".evaluator"))


@pytest.mark.parametrize("mutation", ["record_missing", "record_run_id", "record_exchange_hash",
                                       "record_event_hash", "exchange_run_id", "exchange_event_hash",
                                       "rollout_unverified"])
def test_unverified_source_provenance_fails_closed(tmp_path, monkeypatch, mutation):  # noqa: C901
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)
    record_path = root / "runs" / f"{run_id}.record.json"
    exchange_path = root / "runs" / f"{run_id}.exchange.json"
    record = json.loads(record_path.read_text())
    exchange = json.loads(exchange_path.read_text())
    if mutation == "record_missing":
        record_path.unlink()
    elif mutation == "record_run_id":
        record["run_id"] = "wrong-id"
    elif mutation == "record_exchange_hash":
        record["exchange_sha256"] = "wrong-hash"
    elif mutation == "record_event_hash":
        record["events_sha256"][0] = "wrong-event-hash"
    elif mutation == "exchange_run_id":
        exchange["run_id"] = "wrong-id"
    elif mutation == "exchange_event_hash":
        exchange["turns"][1]["events_sha256"] = "wrong-event-hash"
    elif mutation == "rollout_unverified":
        record["rollout"]["verified"] = False
    if mutation != "record_missing":
        if mutation in {"exchange_run_id", "exchange_event_hash"}:
            record["exchange_sha256"] = hashlib.sha256(
                json.dumps(exchange, sort_keys=True).encode()
            ).hexdigest()
        record_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    if mutation in {"exchange_run_id", "exchange_event_hash"}:
        exchange_path.write_text(json.dumps(exchange, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError):
        packet_builder.build_single_packet(run_id, out_dir, project_root=root)
    assert not out_dir.exists()
    assert not out_dir.with_name(out_dir.name + ".evaluator").exists()


def test_current_sealed_map_has_no_matching_exchange_and_emits_nothing(tmp_path, monkeypatch):
    map_path = packet_builder.HERE / "runs" / "qual-sealed-map.json"
    sealed = json.loads(map_path.read_text(encoding="utf-8"))
    source_run_id = next(iter(sealed))
    out_dir = tmp_path / "must-not-exist"
    _fixed_id(monkeypatch)

    with pytest.raises(ValueError, match="missing verified record or exchange"):
        packet_builder.build_single_packet(source_run_id, out_dir)

    assert not out_dir.exists()


def test_reducer_rejects_unreceipted_blind_pair(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, packet_dir = _fixture(root)
    _fixed_id(monkeypatch)
    packet_builder.build_single_packet(run_id, packet_dir, project_root=root)
    scorer_dir = tmp_path / "scorers"
    scorer_dir.mkdir()
    header = "run_id\telement\tverdict\treason\n"
    rows = "".join(f"g0123456789abcdef\tE{i}\tFAIL\treason {i}\n" for i in range(1, 5))
    scorer1, scorer2 = scorer_dir / "s1.tsv", scorer_dir / "s2.tsv"
    scorer1.write_text(header + rows, encoding="utf-8")
    scorer2.write_text(header + rows.replace("FAIL", "PASS"), encoding="utf-8")

    out_dir = tmp_path / "reduced"
    with pytest.raises(ValueError, match="directory of accepted reading receipts"):
        scorer_reducer.reduce_scores(scorer1, scorer2, tmp_path, out_dir)
    assert not out_dir.exists()


@pytest.mark.parametrize("bad_rows", [
    "g0123456789abcdef\tE1\tFAIL\tone\ng0123456789abcdef\tE1\tFAIL\tduplicate\n",
    "g0123456789abcdef\tE1\tFAIL\tone\n",
    "gffffffffffffffff\tE1\tFAIL\tunknown ID\n",
])
def test_reducer_rejects_duplicate_partial_or_mismatched_pair_before_output(tmp_path, monkeypatch, bad_rows):
    root = tmp_path / "project"
    run_id, packet_dir = _fixture(root)
    _fixed_id(monkeypatch)
    packet_builder.build_single_packet(run_id, packet_dir, project_root=root)
    scorer_dir = tmp_path / "scorers"
    scorer_dir.mkdir()
    scorer1, scorer2 = scorer_dir / "s1.tsv", scorer_dir / "s2.tsv"
    header = "run_id\telement\tverdict\treason\n"
    good = "".join(f"g0123456789abcdef\tE{i}\tFAIL\treason {i}\n" for i in range(1, 5))
    scorer1.write_text(header + bad_rows, encoding="utf-8")
    scorer2.write_text(header + good, encoding="utf-8")
    out_dir = tmp_path / "reduced"

    with pytest.raises(ValueError):
        scorer_reducer.reduce_scores(scorer1, scorer2, tmp_path, out_dir)

    assert not out_dir.exists()


def test_grid_packet_requires_rederivation_inputs(tmp_path, monkeypatch):
    root = tmp_path / "project"
    run_id, out_dir = _fixture(root)
    _fixed_id(monkeypatch)
    with pytest.raises(ValueError, match="both original qualification TSVs"):
        packet_builder.build_single_packet(run_id, out_dir, project_root=root,
                                           map_kind="grid", map_path=root / "runs" / "grid-sealed-map.json")
    assert not out_dir.exists()
