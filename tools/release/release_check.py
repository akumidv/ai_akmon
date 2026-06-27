#!/usr/bin/env python3
"""Release readiness tool for the keystone ``release`` role (propose / prepare only).

Drives the mechanical parts of a keystone release: collect state, run the verify suite, and
print an owner-run command plan. It **never** runs ``git commit`` / ``git tag`` / ``git
push`` / publish / pin-bump commands — the owner executes those (D5). It is stdlib-only and
safe to run repeatedly.

Modes (mutually exclusive; ``--check`` is the default):

    --state             summarize TASKS / TASKS_ARCHIVE / CHANGELOG / git status
    --check             run the subject's release suite (runner-resilient)
    --plan vX.Y.Z       print the exact owner-run commit/tag/push command set

The release **subject** is parameterized, selected with ``--subject``:

    keystone  (default)  release the keystone standard itself (its tag)
    package              release the consuming project's own package version

The third subject — a keystone **pin bump** recorded in a consuming project — is deferred
(backlog T18). For ``package``, project-specific check/build commands live in the project's
``_forge/agents/release/README.md`` (the release-agent incarnation); this tool reads that
charter and points the owner at it rather than inventing commands.

The skill that drives this tool: ``_forge/keystone/skills/release/SKILL.md``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# tools/release/release_check.py → keystone root is two levels up.
KEYSTONE_ROOT = Path(__file__).resolve().parents[2]
BIN = KEYSTONE_ROOT / "bin"
# keystone's own development layer (self-CI runner + tests) lives under meta/.
META = KEYSTONE_ROOT / "meta"

_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_UNRELEASED_RE = re.compile(r"^##\s+Unreleased\b", re.MULTILINE | re.IGNORECASE)

SUBJECTS = ("keystone", "package")
_RELEASE_CHARTER = "_forge/agents/release/README.md"


def _find_project_root(start: Path) -> Path:
    """The consuming project root: a parent holding AGENTS.md and _forge/keystone."""
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "_forge" / "keystone").exists():
            return candidate
    return start


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


# --------------------------------------------------------------------------------------
# --state
# --------------------------------------------------------------------------------------


def _git_status(root: Path) -> str:
    if not shutil.which("git"):
        return "(git not found)"
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--short"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - defensive
        return f"(git status failed: {exc})"
    out = proc.stdout.strip()
    return out if out else "(clean)"


def _changelog_summary(keystone: Path) -> list[str]:
    text = _read(keystone / "CHANGELOG.md")
    if not text:
        return ["CHANGELOG.md: (missing)"]
    lines = ["CHANGELOG.md sections:"]
    for match in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE):
        lines.append(f"  - {match.group(1).strip()}")
    if not _UNRELEASED_RE.search(text):
        lines.append("  ! no `## Unreleased` section — add one for pending changes")
    return lines


def _tasks_summary(tasks_dir: Path) -> list[str]:
    out: list[str] = []
    for name in ("TASKS.md", "TASKS_ARCHIVE.md"):
        text = _read(tasks_dir / name)
        if not text:
            out.append(f"{name}: (missing)")
            continue
        entries = [ln.strip() for ln in text.splitlines() if ln.lstrip().startswith("- ") and " · " in ln]
        out.append(f"{name}: {len(entries)} entry(ies)")
        if name == "TASKS.md":
            done = [ln for ln in entries if re.search(r"\bdone\b", ln)]
            if done:
                out.append(f"  ! {len(done)} 'done' entry(ies) in live TASKS.md — move to TASKS_ARCHIVE.md")
    return out


def run_state(root: Path, subject: str) -> int:
    keystone = root / "_forge" / "keystone"
    # The subject decides which working tree a tag is cut from: keystone is the submodule's
    # own tree; package is the project root. For keystone the backlog lives in its dev layer
    # (meta/) while the changelog stays at the keystone root; for package both come from the
    # project root.
    if subject == "keystone":
        tasks_dir = keystone / "meta"
        changelog_dir = keystone
        git_dir = keystone if (keystone / ".git").exists() else root
    else:  # package
        tasks_dir = root
        changelog_dir = root
        git_dir = root

    print(f"== release state (subject: {subject}) ==")
    print(f"project root: {root}")
    print()
    for line in _tasks_summary(tasks_dir):
        print(line)
    print()
    for line in _changelog_summary(changelog_dir):
        print(line)
    print()
    if subject == "package":
        charter = root / _RELEASE_CHARTER
        note = "found" if charter.is_file() else "MISSING — add it for project-specific release commands"
        print(f"release charter: {_RELEASE_CHARTER} ({note})")
        print()
    print(f"git status (short) [{git_dir.name}]:")
    for line in _git_status(git_dir).splitlines():
        print(f"  {line}")
    return 0


# --------------------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------------------


def _pytest_command(root: Path, tests: str) -> list[str]:
    """Resolve a test runner resiliently: uv → project .venv → system pytest."""
    if shutil.which("uv"):
        return ["uv", "run", "pytest", tests]
    venv_pytest = root / ".venv" / "bin" / "pytest"
    if venv_pytest.is_file():
        return [str(venv_pytest), tests]
    if shutil.which("pytest"):
        return ["pytest", tests]
    return [sys.executable, "-m", "pytest", tests]


def run_check(root: Path, subject: str) -> int:
    if subject == "keystone":
        commands = [
            [sys.executable, str(BIN / "sync.py"), "--project-root", str(root), "--check"],
            [sys.executable, str(BIN / "verify.py"), "--project-root", str(root), "--strict", "--quiet"],
            [sys.executable, str(META / "self_ci.py")],
            _pytest_command(root, str(META / "tests")),
        ]
        failed = _run_commands(root, commands)
    else:  # package — the project's own suite. Keep verify (the keystone contract still
        # applies), then defer to the project's documented commands rather than guessing.
        commands = [
            [sys.executable, str(BIN / "verify.py"), "--project-root", str(root), "--strict", "--quiet"],
        ]
        failed = _run_commands(root, commands)
        charter = root / _RELEASE_CHARTER
        if charter.is_file():
            print(f"\n# package release: run the project's own checks from {_RELEASE_CHARTER}")
            print("# (tests / lint / build — this tool does not guess them).")
        else:
            print(f"\n! {_RELEASE_CHARTER} is missing — add it with the project's release commands.")
            failed.append(_RELEASE_CHARTER)

    print()
    if failed:
        print("RELEASE CHECK FAILED:")
        for item in failed:
            print(f"  - {item}")
        return 1
    print("release check: all green")
    return 0


def _run_commands(root: Path, commands: list[list[str]]) -> list[str]:
    failed: list[str] = []
    for command in commands:
        printable = " ".join(command)
        print(f"== {printable}")
        proc = subprocess.run(command, cwd=str(root), check=False)
        if proc.returncode != 0:
            failed.append(printable)
    return failed


# --------------------------------------------------------------------------------------
# --plan
# --------------------------------------------------------------------------------------


def run_plan(version: str, subject: str) -> int:
    if not _VERSION_RE.match(version):
        print(f"error: version must look like vX.Y.Z, got {version!r}", file=sys.stderr)
        return 2
    print("# Owner-run release plan (D5 — prepared by the release role, executed by the owner).")
    print("# Stage files EXPLICITLY — never `git add -A` — so untracked noise")
    print("# (e.g. __pycache__/) is not swept into the release commit.")
    print()
    if subject == "keystone":
        print("cd _forge/keystone            # tag is cut from the submodule's own tree")
        commit_subject = "keystone"
    else:  # package — run from the project root.
        commit_subject = "release"
    print()
    print("git add CHANGELOG.md            # + any other reviewed release-artifact edits")
    print("git status                      # confirm: no __pycache__/ or stray files staged")
    print()
    print(f'git commit -m "{commit_subject} {version}"')
    print(f"git tag {version}              # the tag points at THIS commit, not a prior HEAD")
    print("git push origin main --tags")
    if subject == "package":
        print("\n# package also: build + publish per _forge/agents/release/README.md (owner-run).")
    print()
    print("# This tool does not run any of the above. The owner executes them.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument(
        "--subject",
        choices=SUBJECTS,
        default="keystone",
        help="Release subject: keystone (the standard's tag, default) or package (the project's own version).",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--state", action="store_true", help="Summarize TASKS / CHANGELOG / git status.")
    group.add_argument("--check", action="store_true", help="Run the subject's release suite (default).")
    group.add_argument("--plan", metavar="vX.Y.Z", help="Print the owner-run commit/tag/push command set.")
    args = parser.parse_args(argv)

    if args.plan:
        return run_plan(args.plan, args.subject)

    root = (args.project_root or _find_project_root(Path.cwd())).resolve()
    if args.state:
        return run_state(root, args.subject)
    return run_check(root, args.subject)


if __name__ == "__main__":
    raise SystemExit(main())
