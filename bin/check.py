#!/usr/bin/env python3
"""Run the checks a project declares — ``akmon check`` (ADR 0014 §4, as amended).

The checks are the project's own: its linter, its type checker, or ruff with akmon's rules
(``profiles/ruff.toml``), named in ``[check]`` of ``<AITNA_ROOT>/.akmon.toml``. akmon runs them
and reports the result; it checks no code itself. The engine is ``common/check_runner.py``.

    akmon check              every declared check over the whole project
    akmon check --changed    the same checks over the files that differ from HEAD

Exit 1 when a check fails or cannot run, or the table is malformed; 0 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ``bin/`` is the launcher directory; the shared utilities live in the tree's ``common``
# package, so the tree root joins the path, as in the other launchers.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.check_runner import CONFIG_TARGET, ScopeError, changed_files, read_checks, run_checks
from common.findings import Finding, exit_code, print_findings
from common.project_root import aitna_root, resolve_project_root
from common.record import RecordError, read_akmon_toml_strict


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the project's declared checks, and print findings."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--changed", action="store_true", help="Check only the files that differ from HEAD.")
    args = parser.parse_args(argv)

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    try:
        table = read_akmon_toml_strict(aitna_root(root) / ".akmon.toml").get("check")
    except RecordError as exc:
        print_findings([Finding("error", "check.config", str(exc), CONFIG_TARGET, "Repair the record so it parses")])
        return 1
    checks, problems = read_checks(table)
    findings = [
        Finding("error", "check.config", problem, CONFIG_TARGET, "Correct or remove the entry the message names")
        for problem in problems
    ]
    if not checks and not problems:
        findings.append(
            Finding(
                "warn",
                "check.config",
                "declares no checks, so nothing ran",
                CONFIG_TARGET,
                "Name the project's checks under [check], or run akmon init to set them up",
            )
        )
    try:
        changed = changed_files(root) if args.changed else None
    except ScopeError as exc:
        findings.append(Finding("error", "check.scope", str(exc), "", "Run it inside a git work tree"))
        print_findings(findings)
        return 1
    findings.extend(run_checks(root, checks, changed))
    print_findings(findings)
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
