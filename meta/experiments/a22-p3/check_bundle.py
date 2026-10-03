# ruff: noqa: ANN001, ANN201, D103, E501, S101
"""Check P3's sealed inputs before any model call."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def norm(text):
    return " ".join(text.split()).lower()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sealed_files():
    return sorted(
        path for path in HERE.rglob("*")
        if path.is_file()
        and path.name not in {"SHA256SUMS", "seal.json"}
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and not ("runs" in path.relative_to(HERE).parts
                 and path.name != "qual-sealed-map.json")
        and not path.name.endswith((".attempt.json", ".exchange.json", ".record.json"))
    )


def snapshot():
    return {
        "schema": 1,
        "files": {str(path.relative_to(HERE)): sha(path) for path in sealed_files()},
        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True).stdout.strip(),
    }


def main():
    cards = [json.loads(path.read_text()) for path in sorted((HERE / "cases").glob("P3-*.json"))]
    assert [card["id"] for card in cards] == [f"P3-{n:02d}" for n in range(1, 9)]
    for card in cards:
        subject = card["subject"]
        assert card["role"] == "architect" and card["scoring"] and card["leakage"]
        assert len({item["id"] for item in subject["menu"]}) == len(subject["menu"])
        # Turn two is evidence supplied only after the subject requests it. Its facts may
        # legitimately determine the final recommendation; only turn one may not reveal
        # the evaluator's expected response or failure wording.
        visible = norm(subject["turn1"])
        hits = [phrase for phrase in card["leakage"] if norm(phrase) in visible]
        assert not hits, f"{card['id']} leakage: {hits}"
    arms = {name: (HERE / "arms" / f"{name}.architect.system.txt").read_text() for name in ("A", "B", "C")}
    assert arms["C"].startswith(arms["B"] + "\n\n")
    assert arms["C"][len(arms["B"]) + 2:]
    manifest = json.loads((HERE / "arms" / "manifest.json").read_text())
    for name, text in arms.items():
        assert manifest["arms"][name]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    seal = snapshot()
    seal_path = HERE / "seal.json"
    if "--write-seal" in sys.argv:
        seal_path.write_text(json.dumps(seal, indent=2) + "\n")
    else:
        assert seal_path.exists(), "no accepted seal; run check_bundle.py --write-seal once"
        assert json.loads(seal_path.read_text()) == seal, "sealed input changed"
    sums = "\n".join(f"{digest}  {name}" for name, digest in sorted(seal["files"].items())) + "\n"
    if "--write-seal" in sys.argv:
        (HERE / "SHA256SUMS").write_text(sums)
    else:
        assert (HERE / "SHA256SUMS").read_text() == sums, "SHA256SUMS differs from seal"
    print(f"8 cards, 3 arms, {len(seal['files'])} sealed files")


if __name__ == "__main__":
    main()
