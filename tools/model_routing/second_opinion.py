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
from common.report_path import create_report, next_report_path, report_prefix, safe_name, task_error


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


def _report_prefix(gate: str, task: str | None) -> str:
    """``[<task>-]<gate>``: the review's name before its ``-<n>.md`` ordinal (C114)."""
    return report_prefix(safe_name(gate) or "gate", task)


def _report_dir_error(root: Path, report_dir: Path, configured: str) -> str | None:
    """The error line for a ``report_dir`` that resolves outside ``root``, else ``None``.

    Reports stay inside the project (C9): the check resolves symlinks and ``..`` first, so an
    absolute path, a ``../outside`` and a link inside the project pointing out are all refused,
    and it runs before the provider is started or any file is written.
    """
    if report_dir.resolve().is_relative_to(root.resolve()):
        return None
    return jsondata.fill(_so_data()["report_dir_outside"], {"report_dir": configured})


def _decoded(data: bytes) -> str:
    r"""A provider pipe as text: UTF-8 with an undecodable byte as U+FFFD, universal newlines.

    A provider's bytes are its own; a byte that is not UTF-8 must not cost the review its report
    (C120). ``\r\n`` and a lone ``\r`` arrive as ``\n``, as a text-mode pipe reads them (C115).
    """
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


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
        "--task",
        help="Task id the review belongs to; the report is <report_dir>/[<task>-]<gate>-<n>.md, n the next ordinal.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command and target report path without running it.",
    )
    args = parser.parse_args(argv)
    if (task_problem := task_error(args.task)) is not None:
        parser.error(task_problem)

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
    report_dir = root / str(spec["report_dir"])
    if (outside := _report_dir_error(root, report_dir, str(spec["report_dir"]))) is not None:
        print(outside, file=sys.stderr)
        return 2
    # The resolved form, so the report line is always a path under the (resolved) root.
    report_dir = report_dir.resolve()
    material = args.gate_pack.read_text(encoding="utf-8")
    try:
        command = routing.second_opinion_command(spec, _prompt(args.gate, material), model=model)
    except routing.UnpinnableModelError as exc:
        print(f"second-opinion: {exc}", file=sys.stderr)
        return 2
    prefix = _report_prefix(args.gate, args.task)

    summary = _so_data()["summary"]
    if args.dry_run:
        print(" ".join(command))
        print(jsondata.fill(summary["report_line"], {"path": next_report_path(report_dir, prefix).relative_to(root)}))
        print(jsondata.fill(summary["provider_line"], {"provider": provider, "model": model or "(default)"}))
        return 0

    completed = subprocess.run(command, cwd=root, capture_output=True, check=False)
    output = _decoded(completed.stdout).strip()
    if stderr := _decoded(completed.stderr).strip():
        output = f"{output}\n\n[stderr]\n{stderr}".strip()
    report = create_report(report_dir, prefix, output + "\n")
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
