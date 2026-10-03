# ruff: noqa: ANN001, ANN201, B905, D103, PLR2004, PLR0913, S101, S311
"""Import sealed qualification evidence and write B/C cells fail-closed."""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ELEMENT_RE = re.compile(r"^(E\d+):")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def read_tsv(path: Path, qual_map: dict[str, dict], cases_dir: Path) -> dict[str, dict[str, str]]:
    """Read one complete scorer TSV and reject malformed, duplicate, or extra rows."""
    verdicts: dict[str, dict[str, str]] = {}
    expected_runs = set(qual_map)
    with path.open(encoding="utf-8", newline="") as stream:
        for line_number, row in enumerate(csv.reader(stream, delimiter="\t"), 1):
            if len(row) != 4:
                fail(f"{path}:{line_number}: expected four TSV columns")
            run_id, element, verdict, reason = row
            if run_id not in expected_runs:
                fail(f"{path}:{line_number}: unexpected run id {run_id!r}")
            if verdict not in {"PASS", "FAIL"} or not reason.strip():
                fail(f"{path}:{line_number}: invalid verdict or empty reason")
            if element in verdicts.get(run_id, {}):
                fail(f"{path}:{line_number}: duplicate element {run_id}/{element}")
            verdicts.setdefault(run_id, {})[element] = verdict
    if set(verdicts) != expected_runs:
        fail(f"{path}: scorer run ids do not match all qualification cells")
    for run_id in expected_runs:
        card = json.loads((cases_dir / f"{qual_map[run_id]['case']}.json").read_text())
        matches = [ELEMENT_RE.match(item) for item in card["scoring"]]
        if not all(matches):
            fail(f"case scoring element lacks E id for {run_id}")
        expected = {match.group(1) for match in matches if match}
        if not expected or set(verdicts[run_id]) != expected:
            fail(f"{path}: element set mismatch for {run_id}")
    return verdicts


def verify_run(run_id: str, cell: dict, runs_dir: Path, cases_dir: Path,
               arms_dir: Path) -> dict:
    record_path = runs_dir / f"{run_id}.record.json"
    exchange_path = runs_dir / f"{run_id}.exchange.json"
    if not record_path.is_file() or not exchange_path.is_file():
        fail(f"missing verified record or exchange for {run_id}")
    record = json.loads(record_path.read_text())
    exchange = json.loads(exchange_path.read_text())
    case_path = cases_dir / f"{cell['case']}.json"
    arm_path = arms_dir / f"{cell['arm']}.architect.system.txt"
    expected = {"run_id": run_id, "case": cell["case"], "arm": "A",
                "tier": cell["tier"], "repeat": cell["repeat"]}
    if any(record.get(key) != value for key, value in expected.items()):
        fail(f"record cell does not match sealed map for {run_id}")
    if record.get("verified") is not True or record.get("case_sha256") != sha(case_path):
        fail(f"unverified record or case hash mismatch for {run_id}")
    if record.get("arm_sha256") != sha(arm_path):
        fail(f"arm hash mismatch for {run_id}")
    if record.get("exchange_sha256") != sha(exchange_path):
        fail(f"exchange hash mismatch for {run_id}")
    turns = exchange.get("turns")
    if exchange.get("run_id") != run_id or not isinstance(turns, list) or len(turns) != 2:
        fail(f"exchange identity/schema mismatch for {run_id}")
    event_hashes = record.get("events_sha256")
    if not isinstance(event_hashes, list) or len(event_hashes) != 2 or any(
            turns[index].get("events_sha256") != event_hashes[index] for index in range(2)):
        fail(f"exchange turn hashes mismatch for {run_id}")
    if not isinstance(record.get("rollout"), dict) or record["rollout"].get("verified") is not True:
        fail(f"rollout provenance is not verified for {run_id}")
    return {"record_sha256": sha(record_path), "exchange_sha256": sha(exchange_path)}


def import_qualifications(scorer1_path: Path, scorer2_path: Path,
                          qual_map_path: Path = HERE / "runs" / "qual-sealed-map.json",
                          runs_dir: Path = HERE / "runs", cases_dir: Path = HERE / "cases",
                          arms_dir: Path = HERE / "arms") -> tuple[list[dict], dict[str, dict]]:
    qual_map = json.loads(qual_map_path.read_text())
    if not isinstance(qual_map, dict) or len(qual_map) != 32:
        fail("sealed qualification map must contain exactly 32 cells")
    expected_cells = {(f"P3-{case:02d}", tier, repeat) for case in range(1, 9)
                      for tier in ("strongest", "mid") for repeat in (1, 2)}
    actual_cells = set()
    for run_id, cell in qual_map.items():
        if set(cell) != {"case", "arm", "tier", "repeat"} or cell["arm"] != "A":
            fail(f"invalid qualification cell {run_id}")
        if cell["tier"] not in {"mid", "strongest"} or cell["repeat"] not in {1, 2}:
            fail(f"invalid qualification tier/repeat for {run_id}")
        key = (cell["case"], cell["tier"], cell["repeat"])
        if key not in expected_cells or key in actual_cells:
            fail(f"unexpected or duplicate qualification cell {run_id}")
        actual_cells.add(key)
    if actual_cells != expected_cells:
        fail("qualification map does not cover all eight cases, tiers, and repeats")
    evidence = {run_id: verify_run(run_id, cell, runs_dir, cases_dir, arms_dir)
                for run_id, cell in qual_map.items()}
    scorer1 = read_tsv(scorer1_path, qual_map, cases_dir)
    scorer2 = read_tsv(scorer2_path, qual_map, cases_dir)
    qualified = []
    for run_id, cell in qual_map.items():
        verdict1 = "FAIL" if "FAIL" in scorer1[run_id].values() else "PASS"
        verdict2 = "FAIL" if "FAIL" in scorer2[run_id].values() else "PASS"
        if verdict1 == verdict2 == "FAIL":
            qualified.append({"run_id": run_id, "case": cell["case"], "tier": cell["tier"],
                              "scorer_1": verdict1, "scorer_2": verdict2,
                              **evidence[run_id]})
    return qualified, evidence


def validate_qualifications(qualifications, qual_map, pairs):
    if not isinstance(qualifications, list):
        fail("qualifications must be a list")
    seen = set()
    run_ids = set()
    for entry in qualifications:
        run_id = entry["run_id"]
        if run_id in run_ids:
            fail(f"duplicate qualification run: {run_id}")
        run_ids.add(run_id)
        if run_id not in qual_map:
            fail(f"qualification run is absent from sealed map: {run_id}")
        cell = qual_map[run_id]
        if entry["case"] != cell["case"] or entry["tier"] != cell["tier"]:
            fail(f"qualification cell mismatch: {run_id}")
        if entry["scorer_1"] != "FAIL" or entry["scorer_2"] != "FAIL":
            fail(f"qualification lacks two scorer failures: {run_id}")
        seen.add((cell["case"], cell["tier"]))
    if len(seen) < 4:
        fail("fewer than four distinct qualified strata")
    qualified_pairs = {pairs[case] for case, _ in seen}
    if qualified_pairs != set(pairs.values()):
        fail("not every P3 pair has a qualified stratum")
    return seen


def main(scorer1_path: str, scorer2_path: str) -> None:
    scorer1, scorer2 = Path(scorer1_path), Path(scorer2_path)
    qualified, evidence = import_qualifications(scorer1, scorer2)
    qual_map = json.loads((HERE / "runs" / "qual-sealed-map.json").read_text())
    pairs = {card["id"]: card["pair"] for card in
             (json.loads(path.read_text()) for path in sorted((HERE / "cases").glob("P3-*.json")))}
    seen = validate_qualifications(qualified, qual_map, pairs)
    cells = [(case, arm, tier, repeat) for case, tier in sorted(seen)
             for arm in ("B", "C") for repeat in (1, 2)]
    if len(cells) > 64:
        fail("B/C cell count exceeds 64")
    ids = random.Random(20261004).sample(range(10000, 100000), len(cells))
    sealed = {f"g{ident}": {"case": case, "arm": arm, "tier": tier, "repeat": repeat}
              for ident, (case, arm, tier, repeat) in zip(ids, cells)}
    outputs = {
        HERE / "runs" / "qualified-strata.json": json.dumps(qualified, indent=2) + "\n",
        HERE / "runs" / "grid-sealed-map.json": json.dumps(sealed, indent=2) + "\n",
        HERE / "runs" / "qualification-import.json": json.dumps({
            "scorer_1": {"path": str(scorer1), "sha256": sha(scorer1)},
            "scorer_2": {"path": str(scorer2), "sha256": sha(scorer2)},
            "run_evidence": evidence,
        }, indent=2) + "\n",
    }
    if any(path.exists() for path in outputs):
        fail("qualification output already exists; refusing to overwrite")
    for path, contents in outputs.items():
        path.write_text(contents, encoding="utf-8")
    print(f"{len(sealed)} B/C cells")


def self_test() -> None:
    with __import__("tempfile").TemporaryDirectory() as temp:
        root = Path(temp)
        runs, cases, arms = root / "runs", root / "cases", root / "arms"
        runs.mkdir()
        cases.mkdir()
        arms.mkdir()
        cells = {f"q{index}": {"case": f"P3-{case:02d}", "arm": "A", "tier": tier, "repeat": repeat}
                 for index, (case, tier, repeat) in enumerate(
                     ((case, tier, repeat) for case in range(1, 9)
                      for tier in ("strongest", "mid") for repeat in (1, 2)), 1)}
        pairs = {f"P3-{case:02d}": f"pair{(case + 1) // 2}" for case in range(1, 9)}
        scorer_rows = [[], []]
        for case in range(1, 9):
            case_path = cases / f"P3-{case:02d}.json"
            case_path.write_text(json.dumps({"scoring": ["E1: first", "E2: second"]}))
        for run_id, cell in cells.items():
            arm_path = arms / "A.architect.system.txt"
            arm_path.write_text("sealed A")
            exchange = {"run_id": run_id, "turns": [
                {"user": "one", "assistant": "reply one", "events_sha256": "h1"},
                {"user": "two", "assistant": "reply two", "events_sha256": "h2"}]}
            exchange_path = runs / f"{run_id}.exchange.json"
            exchange_path.write_text(json.dumps(exchange))
            record = {"run_id": run_id, **cell, "verified": True,
                      "case_sha256": sha(case_path), "arm_sha256": sha(arm_path),
                      "exchange_sha256": sha(exchange_path), "events_sha256": ["h1", "h2"],
                      "rollout": {"verified": True}}
            (runs / f"{run_id}.record.json").write_text(json.dumps(record))
            for scorer_index in range(2):
                for element in ("E1", "E2"):
                    scorer_rows[scorer_index].append(
                        f"{run_id}\t{element}\tFAIL\tfailed element\n")
        map_path = root / "qual-map.json"
        map_path.write_text(json.dumps(cells))
        scorer_paths = [root / "scorer1.tsv", root / "scorer2.tsv"]
        for path, rows in zip(scorer_paths, scorer_rows):
            path.write_text("".join(rows))
        imported, _evidence = import_qualifications(*scorer_paths, map_path, runs, cases, arms)
        assert len(validate_qualifications(imported, cells, pairs)) == 16
        # One scorer's disagreement must remove that run from qualification.
        scorer2_text = scorer_paths[1].read_text().replace("q1\tE1\tFAIL", "q1\tE1\tPASS")
        scorer2_text = scorer2_text.replace("q1\tE2\tFAIL", "q1\tE2\tPASS")
        scorer_paths[1].write_text(scorer2_text)
        imported, _evidence = import_qualifications(*scorer_paths, map_path, runs, cases, arms)
        assert "q1" not in {entry["run_id"] for entry in imported}
        # A tampered exchange must be caught by its retained record hash.
        with (runs / "q1.exchange.json").open("a") as stream:
            stream.write(" ")
        try:
            import_qualifications(*scorer_paths, map_path, runs, cases, arms)
        except ValueError as exc:
            assert "exchange hash mismatch" in str(exc)
        else:
            raise AssertionError("mismatched exchange accepted")
    print("synthetic qualification evidence checks passed")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(*sys.argv[1:3])
