#!/usr/bin/env python3
"""Check a project's Python against akmon's rule catalog — ``akmon check`` (ADR 0014 §4).

The rules are the catalog's (``profiles/python.rules.toml``), their severities and parameters
the project's (``[python]`` in ``<AITNA_ROOT>/.akmon.toml``); the engine is
``common/python_rules.py``. No linter is required of the project: this is akmon's own check.

    akmon check              every tracked Python file
    akmon check --changed    the files that differ from HEAD (the pre-commit use)
    akmon check PATH ...     the named files or directories
    akmon check --print-ruff a ruff fragment matching the rules this project runs

Exit 1 when an ``error`` finding exists (any finding under ``--strict``), else 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ``bin/`` is the launcher directory; the shared utilities live in the tree's ``common``
# package, so the tree root joins the path, as in the other launchers.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.findings import Finding, exit_code, print_findings  # noqa: E402
from common.project_root import aitna_root, resolve_project_root  # noqa: E402
from common.python_rules import (  # noqa: E402
    CONFIG_TARGET,
    ScopeError,
    Settings,
    check_files,
    load_catalog,
    project_files,
    read_settings,
    ruff_fragment,
)
from common.record import RecordError, read_akmon_toml_strict  # noqa: E402

# The tree this launcher belongs to: its catalog is the one that runs, in every mount mode.
_TREE_ROOT = Path(__file__).resolve().parent.parent


def load_settings(root: Path, catalog: dict) -> tuple[Settings, list[Finding]]:
    """The project's validated settings, and a ``python.config`` error for every problem in them."""
    try:
        record = read_akmon_toml_strict(aitna_root(root) / ".akmon.toml")
    except RecordError as exc:
        settings, _ = read_settings(catalog, None)
        return settings, [
            Finding("error", "python.config", str(exc), CONFIG_TARGET, "Repair the record so it parses as TOML")
        ]
    settings, problems = read_settings(catalog, record.get("python"))
    return settings, [
        Finding("error", "python.config", problem, CONFIG_TARGET, "Correct or remove the key the message names")
        for problem in problems
    ]


def _named_files(root: Path, paths: list[Path]) -> tuple[list[str], list[Finding]]:
    files, findings = set(), []
    base = root.resolve()
    for given in paths:
        path = given.resolve()
        candidates = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for candidate in candidates:
            try:
                files.add(candidate.relative_to(base).as_posix())
            except ValueError:
                outside = Finding("error", "python.scope", "is outside the project", str(given), "Name project files")
                findings.append(outside)
    return sorted(files), findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path, help="Files or directories to check.")
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument("--changed", action="store_true", help="Check only the files that differ from HEAD.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--print-ruff", action="store_true", help="Print a matching ruff fragment and exit.")
    args = parser.parse_args(argv)

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    catalog = load_catalog(_TREE_ROOT)
    settings, findings = load_settings(root, catalog)
    if args.print_ruff:
        print_findings(findings)
        print(ruff_fragment(catalog, settings), end="")
        return exit_code(findings)

    if args.paths:
        files, scope_findings = _named_files(root, args.paths)
        findings.extend(scope_findings)
    else:
        try:
            files = project_files(root, settings, changed=args.changed)
        except ScopeError as exc:
            files = []
            findings.append(
                Finding("error", "python.scope", str(exc), "", "Run it inside a git work tree, or name the files")
            )
    findings.extend(check_files(root, files, catalog, settings))
    print_findings(findings)
    errors = sum(finding.severity == "error" for finding in findings)
    warnings = sum(finding.severity == "warn" for finding in findings)
    print(f"akmon check: {len(files)} file(s), {errors} error(s), {warnings} warning(s)", file=sys.stderr)
    return exit_code(findings, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
