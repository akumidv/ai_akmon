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

import routing


def _find_project_root(start: Path) -> Path:
    forge = routing.forge_root_name()
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / forge / "keystone").exists():
            return candidate
    return start


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _prompt(gate: str, prompt_text: str) -> str:
    return f"""You are an independent second-opinion reviewer for a keystone verify gate.

Gate: {gate}

Rules:
- Review only; do not edit files, run commands, commit, push, or approve on behalf of the owner.
- Return: verdict, key disagreements or risks, missing verification, and concrete file/line references when available.
- Treat the result as advisory input to owner verification, not a sign-off.

Material to review:
{prompt_text}
"""


def _report_path(root: Path, report_dir: str, gate: str) -> Path:
    safe_gate = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in gate).strip("-") or "gate"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / report_dir / f"{safe_gate}-{stamp}.md"


def _digest(text: str, limit: int = 1200) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "\n...[truncated; see full report]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--provider", help="External review provider. Defaults to configured opposite vendor.")
    parser.add_argument("--orchestrator-vendor", default="openai", help="Vendor running the main session.")
    parser.add_argument("--gate", required=True, help="Verify gate name, e.g. design-align or code-verify.")
    parser.add_argument("--prompt-file", type=Path, required=True, help="File containing the review material.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command and target report path without running it.",
    )
    args = parser.parse_args(argv)

    root = (args.project_root or _find_project_root(Path.cwd())).resolve()
    keystone_dir = root / routing.forge_root_name() / "keystone"
    registry = routing.load_registry(keystone_dir, root)
    config = _read_json(root / routing.LOCAL_CONFIG_REL)
    provider = args.provider or routing.second_opinion_provider(registry, config, args.orchestrator_vendor)
    spec = routing.second_opinion_spec(registry, provider)
    prompt_text = args.prompt_file.read_text(encoding="utf-8")
    command = routing.second_opinion_command(spec, _prompt(args.gate, prompt_text))
    report = _report_path(root, str(spec["report_dir"]), args.gate)

    if args.dry_run:
        print(" ".join(command))
        print(f"report: {report.relative_to(root)}")
        return 0

    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    output = completed.stdout.strip()
    if completed.stderr.strip():
        output = f"{output}\n\n[stderr]\n{completed.stderr.strip()}".strip()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(output + "\n", encoding="utf-8")
    print(f"second-opinion provider={provider} gate={args.gate} exit={completed.returncode}")
    print(f"report: {report.relative_to(root)}")
    if output:
        print("")
        print(_digest(output))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
