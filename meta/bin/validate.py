#!/usr/bin/env python3
"""Validate keystone's own repository — the dev-layer (META) validator.

Counterpart to ``bin/verify.py``. That tool checks the USE contract a *consuming*
project must satisfy and is shipped into every consumer; it is deliberately ignorant of
keystone's own development artifacts. This tool is the other half: it runs only inside
keystone's own repository and asserts what *keystone itself* must hold —

  1. the dev-layer tree exists (vision, decisions, roadmap, design, reviews, tests, the
     self-CI fixture runner) under ``meta/``;
  2. the operative USE surface still passes its own contract, exercised through the
     synthetic-fixture self-CI (``meta/self_ci.py`` runs ``sync.py`` + ``bin/verify.py``);
  3. keystone's unit tests pass (``pytest meta/tests``), unless skipped.

It never modifies files. A consuming project does not run this; it runs ``bin/verify.py``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# meta/bin/validate.py → keystone root is two parents up.
_KEYSTONE_ROOT = Path(__file__).resolve().parents[2]

# keystone's own dev-layer artifacts (META). These ship with the submodule but are inert
# for a consumer; here we assert they exist so keystone's own tree stays whole.
_DEV_LAYER_FILES = (
    "meta/CONCEPT.md",
    "meta/ROADMAP.md",
    "meta/TASKS.md",
    "meta/decisions/README.md",
    "meta/self_ci.py",
    "meta/tests/conftest.py",
    "meta/tests/test_verify.py",
    "meta/tests/test_sync.py",
)

# the operative USE-surface source files keystone authors and ships (the contract itself).
_USE_SOURCE_FILES = (
    "MODEL.md",
    "BOOTSTRAP.md",
    "ARCHETYPES.md",
    "CHANGELOG.md",
    "README.md",
    "roles/README.md",
    "bin/sync.py",
    "bin/verify.py",
)


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


class Validator:
    def __init__(self, root: Path, *, skip_tests: bool = False) -> None:
        self.root = root
        self.skip_tests = skip_tests
        self.findings: list[Finding] = []

    def ok(self, message: str) -> None:
        self.findings.append(Finding("ok", message))

    def warn(self, message: str) -> None:
        self.findings.append(Finding("warn", message))

    def error(self, message: str) -> None:
        self.findings.append(Finding("error", message))

    def check_present(self, relatives: tuple[str, ...], label: str) -> None:
        missing = [rel for rel in relatives if not (self.root / rel).is_file()]
        if missing:
            self.error(f"{label}: missing {', '.join(missing)}")
        else:
            self.ok(f"{label}: all present")

    def check_dev_layout(self) -> None:
        self.check_present(_DEV_LAYER_FILES, "dev layer (meta/)")
        self.check_present(_USE_SOURCE_FILES, "USE-surface sources")

    def run_self_ci(self) -> None:
        """Run the synthetic-fixture self-CI: sync.py + USE-layer verify.py on a fixture."""
        self_ci = self.root / "meta" / "self_ci.py"
        if not self_ci.is_file():
            self.error("meta/self_ci.py is missing; cannot exercise the USE contract")
            return
        result = subprocess.run(
            [sys.executable, str(self_ci)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self.ok("self-CI fixture passes (sync + USE verify)")
        else:
            detail = (result.stderr or result.stdout).strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            self.error(f"self-CI fixture failed: {tail}")

    def run_tests(self) -> None:
        if self.skip_tests:
            self.warn("unit tests skipped (--skip-tests)")
            return
        tests_dir = self.root / "meta" / "tests"
        if not tests_dir.is_dir():
            self.error("meta/tests is missing; cannot run keystone unit tests")
            return
        runner = self._pytest_command()
        if runner is None:
            self.warn("no pytest runner found (uv / python -m pytest); skipping unit tests")
            return
        result = subprocess.run(
            [*runner, str(tests_dir), "-q"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self.ok(f"unit tests pass ({' '.join(runner)})")
        else:
            detail = (result.stdout or result.stderr).strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            self.error(f"unit tests failed: {tail}")

    def _pytest_command(self) -> list[str] | None:
        """Pick a pytest runner that actually resolves here, else None.

        keystone is stdlib-only and ships no pyproject, so a bare ``uv run pytest`` cannot
        provision pytest — it only works where pytest is already importable (CI, or a
        consuming project's env). Probe before claiming a runner so "pytest absent" surfaces
        as a skip-warning, not a spurious test failure.

        On a non-Python host, run this validator with the dev-layer venv interpreter so the
        ``import pytest`` probe succeeds — e.g. ``_forge/.venv/bin/python`` (provisioned by
        BOOTSTRAP §A; see that step to create it).
        """
        try:
            import pytest  # noqa: F401

            return [sys.executable, "-m", "pytest"]
        except ImportError:
            pass
        if shutil.which("uv") and shutil.which("pytest"):
            return ["uv", "run", "pytest"]
        return None

    def run(self) -> None:
        self.check_dev_layout()
        self.run_self_ci()
        self.run_tests()


def print_findings(findings: list[Finding], *, quiet: bool) -> None:
    for finding in findings:
        if quiet and finding.level == "ok":
            continue
        print(f"[{finding.level}] {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the pytest run.")
    args = parser.parse_args(argv)

    validator = Validator(_KEYSTONE_ROOT, skip_tests=args.skip_tests)
    validator.run()
    print_findings(validator.findings, quiet=args.quiet)

    has_errors = any(finding.level == "error" for finding in validator.findings)
    has_warnings = any(finding.level == "warn" for finding in validator.findings)
    if has_errors or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
