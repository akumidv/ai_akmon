#!/usr/bin/env python3
"""Validate akmon's own repository — the dev-layer (META) validator.

Counterpart to ``bin/verify.py``. That tool checks the USE contract a *consuming*
project must satisfy and is shipped into every consumer; it is deliberately ignorant of
akmon's own development artifacts. This tool is the other half: it runs only inside
akmon's own repository and asserts what *akmon itself* must hold —

  1. the dev-layer tree exists (vision, decisions, roadmap, design, reviews, tests, the
     self-CI fixture runner) under ``meta/``;
  2. the operative USE surface still passes its own contract, exercised through the
     synthetic-fixture self-CI (``meta/self_ci.py`` runs ``sync.py`` + ``bin/verify.py``);
  3. akmon's unit tests pass (``pytest meta/tests``), unless skipped.

It never modifies files. A consuming project does not run this; it runs ``bin/verify.py``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# meta/bin/validate.py → akmon root is two parents up.
_KEYSTONE_ROOT = Path(__file__).resolve().parents[2]

# The shared finding envelope ships in the standard's own ``bin/`` (stdlib-only, no install).
# The tree root for the shared ``common`` package, and ``bin/`` for the two launchers,
# which are imported by their bare script name (``import sync``) the way they are at runtime.
sys.path.insert(0, str(_KEYSTONE_ROOT / "bin"))
sys.path.insert(0, str(_KEYSTONE_ROOT))

from common.findings import Finding, exit_code, line_safe, print_findings  # noqa: E402

# akmon's own dev-layer artifacts (META). These ship with the submodule but are inert
# for a consumer; here we assert they exist so akmon's own tree stays whole.
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

# the operative USE-surface source files akmon authors and ships (the contract itself).
_USE_SOURCE_FILES = (
    "MODEL.md",
    "CAPABILITIES.md",
    "BOOTSTRAP.md",
    "ARCHETYPES.md",
    "CHANGELOG.md",
    "README.md",
    "roles/README.md",
    "bin/sync.py",
    "bin/verify.py",
)


def _uv_default_groups(data: dict, groups: dict) -> list[str]:
    """The dependency-groups ``uv run`` installs without being asked: ``dev`` unless configured."""
    configured = data.get("tool", {}).get("uv", {}).get("default-groups")
    if configured == "all":
        return list(groups)
    if isinstance(configured, list):
        return [name for name in configured if isinstance(name, str)]
    return ["dev"]


def _requirement_name(requirement: str) -> str:
    """The distribution name heading a PEP 508 requirement string (``pytest>=8`` → ``pytest``)."""
    head = requirement.strip().split(";", 1)[0]
    for index, char in enumerate(head):
        if not (char.isalnum() or char in "-_."):
            return head[:index].lower()
    return head.lower()


class Validator:
    def __init__(self, root: Path, *, skip_tests: bool = False) -> None:
        self.root = root
        self.skip_tests = skip_tests
        self.findings: list[Finding] = []

    def ok(self, code: str, message: str, *, target: str = "", fix: str) -> None:
        self.findings.append(Finding("ok", code, line_safe(message), line_safe(target), line_safe(fix)))

    def warn(self, code: str, message: str, *, target: str = "", fix: str) -> None:
        self.findings.append(Finding("warn", code, line_safe(message), line_safe(target), line_safe(fix)))

    def error(self, code: str, message: str, *, target: str = "", fix: str) -> None:
        self.findings.append(Finding("error", code, line_safe(message), line_safe(target), line_safe(fix)))

    def check_present(self, relatives: tuple[str, ...], label: str, *, code: str, target: str) -> None:
        """One presence rule over a population; the caller owns the code naming that rule."""
        missing = [rel for rel in relatives if not (self.root / rel).is_file()]
        if missing:
            self.error(
                code,
                f"{label}: missing {', '.join(missing)}",
                target=target,
                fix="Restore the listed files from git history.",
            )
        else:
            self.ok(
                code,
                f"{label}: all present",
                target=target,
                fix="Keep every file in this population present.",
            )

    def check_dev_layout(self) -> None:
        self.check_present(_DEV_LAYER_FILES, "dev layer (meta/)", code="devlayer.files", target="meta/")
        self.check_present(_USE_SOURCE_FILES, "USE-surface sources", code="devlayer.use-surface", target=".")

    def run_self_ci(self) -> None:
        """Run the synthetic-fixture self-CI: sync.py + USE-layer verify.py on a fixture."""
        self_ci = self.root / "meta" / "self_ci.py"
        if not self_ci.is_file():
            self.error(
                "devlayer.self-ci-runner",
                "meta/self_ci.py is missing; cannot exercise the USE contract",
                target="meta/self_ci.py",
                fix="Restore meta/self_ci.py from git history.",
            )
            return
        result = subprocess.run(
            [sys.executable, str(self_ci)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self.ok(
                "devlayer.self-ci",
                "self-CI fixture passes (sync + USE verify)",
                target="meta/self_ci.py",
                fix="Keep the synthetic fixture green before every release.",
            )
        else:
            # Name the failure, not the last thing printed. `self_ci` streams every finding to
            # stdout and exits non-zero only for the `error` ones, so the last line is routinely
            # an unrelated `warn` — a reader is then pointed at a rule that did not fail. Prefer
            # the first rendered error; fall back to the tail only when there is none.
            stderr, stdout = result.stderr.strip(), result.stdout.strip()
            errors = [line for line in stdout.splitlines() if line.startswith("ERROR ")]
            lines = (stderr or stdout).splitlines()
            tail = errors[0] if errors else (lines[-1] if lines else f"exit {result.returncode}")
            self.error(
                "devlayer.self-ci",
                f"self-CI fixture failed: {tail}",
                target="meta/self_ci.py",
                fix="Run python3 meta/self_ci.py and fix the reported failure.",
            )

    def run_tests(self) -> None:
        if self.skip_tests:
            self.warn(
                "devlayer.unit-tests-skipped",
                "unit tests skipped (--skip-tests)",
                target="meta/tests",
                fix="Drop --skip-tests to run the unit tests.",
            )
            return
        tests_dir = self.root / "meta" / "tests"
        if not tests_dir.is_dir():
            self.error(
                "devlayer.tests-dir",
                "meta/tests is missing; cannot run akmon unit tests",
                target="meta/tests",
                fix="Restore meta/tests from git history.",
            )
            return
        runner, reason = self._pytest_command()
        if runner is None:
            self.warn(
                "devlayer.unit-tests-skipped",
                f"unit tests skipped: {reason}",
                target="meta/tests",
                fix="Install pytest, or run this validator with an interpreter that has it.",
            )
            return
        result = subprocess.run(
            [*runner, str(tests_dir), "-q"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self.ok(
                "devlayer.unit-tests",
                f"unit tests pass ({' '.join(runner)})",
                target="meta/tests",
                fix="Keep the unit tests green before every commit.",
            )
        else:
            detail = (result.stdout or result.stderr).strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            self.error(
                "devlayer.unit-tests",
                f"unit tests failed: {tail}",
                target="meta/tests",
                fix="Run the unit tests locally and fix the reported failure.",
            )

    def _pytest_command(self) -> tuple[list[str] | None, str]:
        """Pick a pytest runner that actually resolves here, else ``None`` and the reason why.

        Probe before claiming a runner, so "pytest absent" stays a skip-warning and never becomes
        a spurious test failure. Two ways it resolves:

        1. **pytest is importable** under this interpreter — the certain case, and the one a
           non-Python host hits when the validator is run with the dev-layer venv interpreter,
           e.g. ``_aitna/.venv/bin/python`` (provisioned by BOOTSTRAP §A; see that step to
           create it).
        2. **``uv`` plus a manifest that declares pytest** in a group ``uv run`` installs by
           default. That is the real distinction, and it is about *this root*, not about the
           host: ``uv run`` provisions from the project it resolves, so it works exactly where
           such a manifest exists. akmon's own root has had one since C37 (``[dependency-groups]
           dev``); a consumer's dev layer may not.

        The guard used to be ``which("uv") and which("pytest")``, from an era when akmon shipped
        no ``pyproject.toml`` and a bare ``uv run pytest`` therefore had nothing to provision
        from. That stopped being true at C37, and the test built on it was the wrong one twice
        over: it refused the runner in exactly the case ``uv`` now handles (no pytest installed,
        manifest resolvable) and accepted it only where pytest was already installed — where the
        import probe above has usually answered already.
        """
        try:
            import pytest  # noqa: F401

            return [sys.executable, "-m", "pytest"], ""
        except ImportError:
            pass
        if not shutil.which("uv"):
            return None, "pytest is not importable and uv is not on PATH"
        resolvable, why = self._manifest_declares_pytest()
        if resolvable:
            return ["uv", "run", "pytest"], ""
        return None, f"pytest is not importable and {why}"

    def _manifest_declares_pytest(self) -> tuple[bool, str]:
        """Whether this root's ``pyproject.toml`` names pytest where ``uv run`` will install it.

        ``uv run`` syncs the project's dependencies plus its default dependency-groups, so the
        question is whether pytest is *declared* in one of those — not whether it is installed
        right now. Anything unreadable answers no: a skip-warning is the safe direction, and a
        runner claimed on a guess is the failure mode this method exists to avoid.
        """
        manifest = self.root / "pyproject.toml"
        if not manifest.is_file():
            return False, "this root has no pyproject.toml for uv run to provision from"
        try:
            import tomllib
        except ImportError:
            return False, "its pyproject.toml cannot be read here (tomllib needs Python 3.11+)"
        try:
            with manifest.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, ValueError):
            return False, "its pyproject.toml does not parse"
        groups = data.get("dependency-groups") or {}
        requirements = list(data.get("project", {}).get("dependencies") or [])
        for name in _uv_default_groups(data, groups):
            requirements.extend(groups.get(name) or [])
        if any(_requirement_name(item) == "pytest" for item in requirements if isinstance(item, str)):
            return True, ""
        return False, "its pyproject.toml declares no pytest in a group uv installs by default"

    def run(self) -> None:
        self.check_dev_layout()
        self.run_self_ci()
        self.run_tests()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the pytest run.")
    args = parser.parse_args(argv)

    validator = Validator(_KEYSTONE_ROOT, skip_tests=args.skip_tests)
    validator.run()
    print_findings(validator.findings, quiet=args.quiet)
    return exit_code(validator.findings, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
