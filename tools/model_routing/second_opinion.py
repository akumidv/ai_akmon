#!/usr/bin/env python3
"""Run an advisory second-opinion review through the registry-selected CLI.

This runner is intentionally explicit: it is called at a verify/align gate, writes the
full external review to a configured report directory, and prints a short digest. It is
not wired as a blocking hook; owner verification remains the decision point.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The tree root, so the shared ``common`` package resolves: it holds the single owner of
# project-root discovery (C73) and is reachable at the same tree-relative depth from the
# mounted tree and from the materialized ``<AITNA_ROOT>/.akmon/`` copy alike.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routing

from common import jsondata
from common.project_root import resolve_project_root
from common.record import records_package_mode


def _so_data() -> dict:
    """The second-opinion runner texts (``second_opinion.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "second_opinion.json")


def _gate_data() -> dict:
    """The shared gate-pack texts (``gate.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "gate.json")


def _standard_tree_root(project_root: Path) -> Path:
    """The tree ``registry.json`` is read from: the mount for mounted modes, this script's own tree otherwise.

    The rule of ``bin/sync.py::standard_tree_root`` and ``init.py::_standard_tree_root``: in package
    mode there is no ``<AITNA_ROOT>/akmon`` to read, and the recorded ``mount`` field decides, so
    a stale mount directory from a prior mode does not shadow the installed tree.
    """
    mounted = project_root / routing.aitna_root_name() / "akmon"
    if not records_package_mode(project_root) and mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _prompt(gate: str, prompt_text: str) -> str:
    return jsondata.fill(_so_data()["prompt"], {"gate": gate, "material": prompt_text})


def _unavailable_notice(registry: dict, config: dict, orchestrator_vendor: str, gate: str) -> str:
    """The skip, stated as a fact plus the one option that is left and what it costs.

    The gate is skipped rather than downgraded to a same-model reviewer: shared weights
    reproduce the author's systematic errors and return a confident agreement, which reads
    exactly like a review and is filed like one. That refusal is the machine's; the weaker
    check is still worth running sometimes, so it is offered here — to a person, with its
    boundary attached — instead of being taken automatically and labelled as diversity.
    """
    reason = routing.second_opinion_unavailability(registry, config, orchestrator_vendor)
    lines = _so_data()["unavailable_notice"]
    return "\n".join(
        [
            jsondata.fill(lines[0], {"gate": gate}),
            jsondata.fill(lines[1], {"reason": reason}),
            lines[2],
            lines[3],
            lines[4],
        ]
    )


def _report_path(root: Path, report_dir: str, gate: str) -> Path:
    safe_gate = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in gate).strip("-") or "gate"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / report_dir / f"{safe_gate}-{stamp}.md"


def _digest(text: str, limit: int = 1200) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + _gate_data()["truncation_suffix_report"]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: run the second-opinion CLI against a gate pack and write its report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--provider", help="External review provider. Defaults to configured opposite vendor.")
    parser.add_argument("--orchestrator-vendor", default="openai", help="Vendor running the main session.")
    parser.add_argument("--gate", required=True, help="Verify gate name, e.g. design-align or code-verify.")
    parser.add_argument(
        "--gate-pack", type=Path, required=True, help="Path to a built gate-pack markdown file (see gate_pack.py)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command and target report path without running it.",
    )
    args = parser.parse_args(argv)

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    registry = routing.load_registry(_standard_tree_root(root), root)
    config = _read_json(root / routing.local_config_rel())

    if args.provider:
        provider, model = args.provider, None
    else:
        target = routing.resolve_second_opinion(registry, config, args.orchestrator_vendor)
        if target is None:
            print(_unavailable_notice(registry, config, args.orchestrator_vendor, args.gate))
            return 0
        provider, model = target.provider, target.model

    spec = routing.second_opinion_spec(registry, provider)
    material = args.gate_pack.read_text(encoding="utf-8")
    try:
        command = routing.second_opinion_command(spec, _prompt(args.gate, material), model=model)
    except routing.UnpinnableModelError as exc:
        print(f"second-opinion: {exc}", file=sys.stderr)
        return 2
    report = _report_path(root, str(spec["report_dir"]), args.gate)

    summary = _so_data()["summary"]
    if args.dry_run:
        print(" ".join(command))
        print(jsondata.fill(summary["report_line"], {"path": report.relative_to(root)}))
        print(jsondata.fill(summary["provider_line"], {"provider": provider, "model": model or "(default)"}))
        return 0

    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    output = completed.stdout.strip()
    if completed.stderr.strip():
        output = f"{output}\n\n[stderr]\n{completed.stderr.strip()}".strip()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(output + "\n", encoding="utf-8")
    print(
        jsondata.fill(
            _so_data()["summary"]["result_line"],
            {
                "provider": provider,
                "model": model or "(default)",
                "gate": args.gate,
                "exit": completed.returncode,
            },
        )
    )
    print(jsondata.fill(_so_data()["summary"]["report_line"], {"path": report.relative_to(root)}))
    if output:
        print("")
        print(_digest(output))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
