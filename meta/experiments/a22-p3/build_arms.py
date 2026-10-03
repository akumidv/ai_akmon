# ruff: noqa: ANN001, ANN002, ANN201, D103, E501, S101
"""Build P3 A/B/C arms from the current akmon baseline and frozen clause."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "arms"
PROTOCOL = """You are the architect for a bounded research comparison. You have no tools. Do not edit files, approve, deploy, or claim acceptance. You may request at most one named prepared item by ending your first response with exactly CHECK: <item-id>. Otherwise answer directly."""
CLAUSE = """Before choosing a response to a design uncertainty, identify what decision
ground is missing. Inspect facts in the supplied dossier or request the named
available check when its output has not been supplied. If the missing ground
is consequential owner-only use, priority, or acceptable trade-off, ask one
focused question that names the choice it affects. For an immaterial,
reversible detail, state a bounded assumption and
proceed. When the necessary ground is available, offer the relevant options
and their consequences; do not use an options menu to substitute for missing
problem knowledge."""
SOURCES = ["AGENTS.md", "guardrails/_common.md", "profiles/python.md",
           "profiles/python-stdlib.md", "roles/architect.md", "pipelines/design-flow.md"]


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def frame(path, text):
    return f"Contents of {path}:\n\n{text.rstrip()}"


def main():
    parts = {path: (ROOT / path).read_text() for path in SOURCES}
    baseline = "\n\n".join([PROTOCOL, *(frame(path, text) for path, text in parts.items())])
    arms = {"A": PROTOCOL, "B": baseline, "C": baseline + "\n\n" + CLAUSE}
    assert arms["C"].startswith(arms["B"] + "\n\n")
    OUT.mkdir(exist_ok=True)
    for arm, text in arms.items():
        (OUT / f"{arm}.architect.system.txt").write_text(text)
    manifest = {
        "repository_commit": git("rev-parse", "HEAD").strip(),
        "repository_dirty_sha256": sha(git("diff", "HEAD")),
        "protocol_sha256": sha(PROTOCOL), "clause_sha256": sha(CLAUSE),
        "parts": {path: {"bytes": len(text.encode()), "sha256": sha(text)} for path, text in parts.items()},
        "arms": {arm: {"bytes": len(text.encode()), "sha256": sha(text)} for arm, text in arms.items()},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for arm, row in manifest["arms"].items():
        print(f"{arm}: {row['bytes']} bytes {row['sha256']}")


if __name__ == "__main__":
    main()
