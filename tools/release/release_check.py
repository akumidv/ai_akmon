#!/usr/bin/env python3
"""Release readiness tool for the akmon ``release`` role (propose / prepare only).

Drives the mechanical parts of a akmon release: collect state, run the verify suite, and
print an owner-run command plan. It **never** runs ``git commit`` / ``git tag`` / ``git
push`` / publish / pin-bump commands — the owner executes those (D5). It is stdlib-only and
safe to run repeatedly.

Modes (mutually exclusive; ``--check`` is the default):

    --state             summarize TASKS / TASKS_ARCHIVE / CHANGELOG / git status
    --check             run the subject's release suite (runner-resilient)
    --plan vX.Y.Z       print the exact owner-run commit/tag/push command set

The release **subject** is parameterized, selected with ``--subject``:

    akmon  (default)  release the akmon standard itself (its tag)
    package              release the consuming project's own package version

The third subject — an akmon **pin bump** recorded in a consuming project — is deferred
(backlog T18). For ``package``, project-specific check/build commands live in the project's
``<AITNA_ROOT>/agents/release/README.md`` (the release-agent incarnation); this tool reads that
charter and points the owner at it rather than inventing commands.

The skill that drives this tool: ``<AITNA_ROOT>/akmon/skills/release/SKILL.md``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# tools/release/release_check.py → akmon root is two levels up.
KEYSTONE_ROOT = Path(__file__).resolve().parents[2]
BIN = KEYSTONE_ROOT / "bin"  # the two launchers; the shared library lives in ``common``.
# akmon's own development layer (self-CI runner + tests) lives under meta/.
META = KEYSTONE_ROOT / "meta"

# The shared finding envelope, the root walk and the version-spelling rule all ship in the
# standard's own ``common`` package (stdlib-only, no install), so this tool speaks the same
# five fields every other check does and compares versions by the one rule that also governs the
# CLI's skew notice.
sys.path.insert(0, str(KEYSTONE_ROOT))

from common.findings import Finding, exit_code, line_safe, print_findings  # noqa: E402
from common.project_root import aitna_root, aitna_root_name, resolve_project_root  # noqa: E402
from common.record import read_akmon_toml  # noqa: E402
from common.versions import is_final, split_version  # noqa: E402

_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_UNRELEASED_RE = re.compile(r"^##\s+Unreleased\b", re.MULTILINE | re.IGNORECASE)

SUBJECTS = ("akmon", "package")


def _release_charter() -> str:
    """The release charter, project-root-relative, under the *configured* dev layer.

    A function rather than a constant because ``AITNA_ROOT`` is read at call time: the
    literal this replaced pointed a project with a relocated dev layer at a file it does not
    have, both when reading it and when printing it into the owner-run plan.
    """
    return f"{aitna_root_name()}/agents/release/README.md"


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


def _changelog_summary(akmon: Path) -> list[str]:
    text = _read(akmon / "CHANGELOG.md")
    if not text:
        return ["CHANGELOG.md: (missing)"]
    lines = ["CHANGELOG.md sections:"]
    lines.extend(f"  - {match.group(1).strip()}" for match in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE))
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
    """``--state``: print the TASKS / CHANGELOG / release-charter / git-status summary."""
    akmon = aitna_root(root) / "akmon"
    # The subject decides which working tree a tag is cut from: akmon is the submodule's
    # own tree; package is the project root. For akmon the backlog lives in its dev layer
    # (meta/) while the changelog stays at the akmon root; for package both come from the
    # project root.
    if subject == "akmon":
        tasks_dir = akmon / "meta"
        changelog_dir = akmon
        git_dir = akmon if (akmon / ".git").exists() else root
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
        charter = root / _release_charter()
        note = "found" if charter.is_file() else "MISSING — add it for project-specific release commands"
        print(f"release charter: {_release_charter()} ({note})")
        print()
    print(f"git status (short) [{git_dir.name}]:")
    for line in _git_status(git_dir).splitlines():
        print(f"  {line}")
    return 0


# --------------------------------------------------------------------------------------
# version <-> changelog cross-check (C54, design §4 — owner choice F9)
# --------------------------------------------------------------------------------------
#
# The tree carries four independent version carriers — ``pyproject.toml``'s ``version`` (the
# literal hatchling stamps into the wheel), ``src/akmon/__init__.py::_STATIC_VERSION`` (the
# fallback when the package is not installed), the topmost ``CHANGELOG.md`` heading, and the git
# tag — and until C54 nothing related any two of them. The defect that motivated the join had
# already shipped: the tree at tag ``v0.3.0`` carried ``0.3.0.dev0``, so a wheel built from the
# reviewed state was misnamed and the string ``0.3.0`` never existed in the tree at all.
#
# Severities follow the forks the owner closed in F9, and each one is a claim about what a
# consumer can act on rather than a preference:
#
# * the two literals disagreeing is an **error** — one release bump is two edits, and this is the
#   check that says so (F9/2);
# * a version that does not match the changelog window is an **error** — that is the join;
# * a final version that already has its tag is a **warn**, not an error: a retag is legitimate
#   owner work and the check must not fight it;
# * a tag with no heading is a **warn**: tags are immutable, so a historical gap can never be
#   repaired into green and a hard error would be waived within one release (F9/5);
# * a rule whose input is absent emits an explicit **skip finding** rather than passing quietly
#   (F9/4) — silence is the failure this stage exists to remove. A rule that does not *apply*
#   (the re-release question under a non-final version) is not skipped, because nothing about it
#   went unchecked.
#
# Every comparison normalizes through ``bin/versions.py`` first (F9/6): a leading ``v`` is a
# spelling, a ``git describe`` distance means the tree is *past* that tag rather than at it, and
# a PEP 440 pre/post/dev segment is neither — it names a different version.

_CHANGELOG = "CHANGELOG.md"
_PYPROJECT = "pyproject.toml"
_STATIC_VERSION_FILE = "src/akmon/__init__.py"

_STATIC_VERSION_RE = re.compile(r"^_STATIC_VERSION\s*=\s*[\"\']([^\"\']+)[\"\']", re.MULTILINE)
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
# A released heading names its version *first* and may say more after it. `## v0.3.0` is this
# repo's own form; `## [1.2.3] - 2024-01-01` is Keep a Changelog's, and the `package` subject
# reads a consuming project's file. Requiring the whole heading to be a version would report
# "no released heading" over a changelog full of them — a confident wrong answer.
# The boundary after the version is any character that cannot *start* a PEP 440 suffix, so
# `## v1.2.3: title` and `## v1.2.3 (2024-01-01)` are released while `## v1.2.3rc1`,
# `## v1.2.3.post1` and `## v1.2.3-4` are not. Anchored at the heading's start on purpose: a
# version mentioned mid-heading (`## Fixed in 1.2.3`) describes a release, it does not name one.
_HEADING_VERSION_RE = re.compile(r"^\[?v?(\d+\.\d+\.\d+)\]?(?:[^\w.+-]|$)")
_UNRELEASED_HEADING_RE = re.compile(r"^\[?unreleased\]?$", re.IGNORECASE)
_PYPROJECT_VERSION_RE = re.compile(r"^version\s*=\s*[\"\']([^\"\']+)[\"\']")
_SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$")
# What *could* be a release tag: a version-shaped name in either spelling. Only `vX.Y.Z` is an
# admissible release tag (owner ruling on D2-31 (8)); the bare form is matched here so that a
# tag cut as `1.2.3` is reported as misspelled rather than dropped in silence — a filter that
# quietly excludes it would hide the tag from both git-dependent rules and say nothing.
_TAG_SHAPE_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


def _pyproject_version(path: Path) -> str | None:
    """``[project].version`` from ``pyproject.toml``, or ``None`` when there is none.

    Python 3.11+ ``tomllib``, with a section-scoped line scan retained as a defensive
    stdlib-only fallback. It is section-scoped so a ``version`` belonging to some other table
    is never mistaken for the project's.
    """
    if not path.is_file():
        return None
    try:
        import tomllib  # noqa: PLC0415 — the one-reader carrier (test_record_owner) keys on the importing function

        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except ImportError:
        pass
    except (OSError, ValueError):
        return None
    else:
        project = data.get("project")
        version = project.get("version") if isinstance(project, dict) else None
        return version if isinstance(version, str) and version.strip() else None
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        heading = _SECTION_RE.match(stripped)
        if heading:
            section = heading.group(1).strip()
            continue
        if section != "project":
            continue
        match = _PYPROJECT_VERSION_RE.match(stripped)
        if match:
            return match.group(1)
    return None


def _static_version(path: Path) -> str | None:
    """The ``_STATIC_VERSION`` literal, read as a literal rather than by importing the package."""
    if not path.is_file():
        return None
    match = _STATIC_VERSION_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _changelog_headings(path: Path) -> list[str]:
    """Every ``## `` heading, in file order — the changelog window as a reader meets it."""
    if not path.is_file():
        return []
    return [match.group(1).strip() for match in _HEADING_RE.finditer(path.read_text(encoding="utf-8"))]


def _git_tags(root: Path) -> list[str] | None:
    """Every version-shaped tag, or ``None`` when git cannot answer — absent binary or no repo.

    ``None`` and ``[]`` are different answers and the caller treats them so: a repository with no
    tags has been asked and answered, while an unanswerable question becomes a skip finding.
    """
    if not shutil.which("git"):
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "tag", "--list"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if _TAG_SHAPE_RE.match(line.strip())]


def _finding(severity: str, code: str, message: str, target: str, fix: str) -> Finding:
    """A finding whose message and target may quote a file: every separator is escaped first.

    Headings, tags and version literals are read out of files and out of ``git`` output, so they
    are untrusted for rendering purposes — a stray separator would split one finding into two
    apparent ones, and the envelope refuses to construct at all. The ``fix`` is always this
    module's own prose and needs no escaping.
    """
    return Finding(severity, code, line_safe(message), line_safe(target), fix)


def _skip(message: str, target: str, fix: str) -> Finding:
    """A rule that could not run, said out loud. Never an error: see F9/4 and F9/5."""
    return _finding("warn", "release.check-skipped", message, target, fix)


def check_release_versions(root: Path) -> list[Finding]:
    """The F9 join over ``root``'s four version carriers, as shared-envelope findings."""
    findings: list[Finding] = []
    changelog_path = root / _CHANGELOG
    # Read once: two rules ask about the same headings, and a file re-read between them could
    # answer them from two different files.
    headings = _changelog_headings(changelog_path)

    declared = _pyproject_version(root / _PYPROJECT)
    fallback = _static_version(root / _STATIC_VERSION_FILE)
    if declared is not None and fallback is not None:
        if declared == fallback:
            findings.append(
                _finding(
                    "ok",
                    "release.version-literals",
                    f"{_PYPROJECT} and {_STATIC_VERSION_FILE} both declare {declared}",
                    _PYPROJECT,
                    "Bump both literals together — one release bump is two edits.",
                )
            )
        else:
            findings.append(
                _finding(
                    "error",
                    "release.version-literals",
                    f"{_PYPROJECT} declares {declared} while {_STATIC_VERSION_FILE} declares {fallback}",
                    _PYPROJECT,
                    "Set both literals to the same string — one release bump is two edits.",
                )
            )
    # `pyproject` wins when both exist: it is the literal that names the built wheel, and the
    # disagreement itself has already been reported above.
    version = declared if declared is not None else fallback

    if version is None:
        findings.append(
            _skip(
                f"no version source: neither {_PYPROJECT} [project].version nor "
                f"{_STATIC_VERSION_FILE} _STATIC_VERSION is present",
                "",
                "Ignore this on a project that carries no Python version literal, and add one otherwise.",
            )
        )
    elif not changelog_path.is_file():
        findings.append(
            _skip(
                f"{_CHANGELOG} is absent, so version {version} was compared against nothing",
                _CHANGELOG,
                f"Add {_CHANGELOG} so a consumer can read the window before accepting a pin.",
            )
        )
    else:
        findings.extend(_check_window(version, headings))

    findings.extend(_check_tags(root, version, has_changelog=changelog_path.is_file(), headings=headings))
    return findings


def _released_headings(headings: list[str]) -> list[tuple[str, str]]:
    """``(heading, version)`` for every heading that names a release, in file order.

    ``## Unreleased`` is not one of them, and neither is a heading whose version is not a plain
    ``X.Y.Z`` — a ``## v1.2.3rc1`` section names a pre-release, which no ``vX.Y.Z`` tag matches.
    """
    pairs = []
    for heading in headings:
        match = _HEADING_VERSION_RE.match(heading)
        if match:
            pairs.append((heading, match.group(1)))
    return pairs


def _check_window(version: str, headings: list[str]) -> list[Finding]:
    """The changelog window rule, in its two branches.

    Non-final wants ``## Unreleased``; final wants its own released heading above every
    other released one.
    """
    base, _ = split_version(version)
    if not is_final(version):
        if headings and _UNRELEASED_HEADING_RE.match(headings[0]):
            return [
                _finding(
                    "ok",
                    "release.changelog-window",
                    f"non-final version {version} sits above a topmost `## Unreleased` heading",
                    _CHANGELOG,
                    "Keep `## Unreleased` topmost while the version is non-final.",
                )
            ]
        observed = f"the topmost heading is `## {headings[0]}`" if headings else "it carries no heading"
        return [
            _finding(
                "error",
                "release.changelog-window",
                f"non-final version {version} but {observed}",
                _CHANGELOG,
                "Add a topmost `## Unreleased` heading, or make the version final.",
            )
        ]
    released = _released_headings(headings)
    if not released:
        return [
            _finding(
                "error",
                "release.changelog-window",
                f"final version {version} but {_CHANGELOG} carries no released heading",
                _CHANGELOG,
                f"Cut the `## Unreleased` heading to `## v{base}` before tagging.",
            )
        ]
    # The *topmost* released heading, not any of them: a matching heading further down names an
    # older release, and accepting it would pass a version the newest section does not describe.
    topmost, topmost_base = released[0]
    if topmost_base != base:
        return [
            _finding(
                "error",
                "release.changelog-window",
                f"final version {version} but the topmost released heading is `## {topmost}`",
                _CHANGELOG,
                f"Cut a `## v{base}` heading above `## {topmost}` before tagging.",
            )
        ]
    return [
        _finding(
            "ok",
            "release.changelog-window",
            f"final version {version} matches the topmost released heading `## {topmost}`",
            _CHANGELOG,
            "Keep the topmost released heading equal to the version being built.",
        )
    ]


def _check_tags(root: Path, version: str | None, *, has_changelog: bool, headings: list[str]) -> list[Finding]:
    """The two git-dependent rules: the re-release warn and the tag-coverage warn."""
    findings: list[Finding] = []
    tags = _git_tags(root)
    final = version is not None and is_final(version)
    if tags is None:
        if final:
            findings.append(
                _skip(
                    f"git is unavailable, so whether {version} is already tagged is unknown",
                    "",
                    "Run this where git can read the repository to detect a re-release.",
                )
            )
        findings.append(
            _skip(
                f"git is unavailable, so no tag was checked for a {_CHANGELOG} heading",
                _CHANGELOG,
                "Run this where git can read the repository to check tag coverage.",
            )
        )
        return findings

    # `vX.Y.Z` is the only admissible release-tag spelling. A version-shaped tag without the
    # prefix is a misspelled tag, not a second convention: it is reported and then excluded, so
    # neither the re-release answer nor tag coverage is computed from a name the standard does
    # not recognize.
    release_tags = [tag for tag in tags if tag.startswith("v")]
    findings.extend(
        _finding(
            "warn",
            "release.tag-spelling",
            f"tag {tag} names a version but is not spelled v{tag}",
            tag,
            f"Cut release tags as v{tag} — that spelling is the release tag's only form.",
        )
        for tag in tags
        if not tag.startswith("v")
    )

    if final:
        base, _ = split_version(version or "")
        matching = [tag for tag in release_tags if split_version(tag)[0] == base]
        if matching:
            findings.append(
                _finding(
                    "warn",
                    "release.retag",
                    f"final version {version} is already tagged as {matching[0]}",
                    matching[0],
                    "Confirm this is a deliberate re-release, or bump the version.",
                )
            )
    if not has_changelog:
        # Unrunnable, not inapplicable: there are tags, and nothing to check them against.
        findings.append(
            _skip(
                f"{_CHANGELOG} is absent, so no tag was checked for a heading",
                _CHANGELOG,
                f"Add {_CHANGELOG} so the tags already cut can be checked against it.",
            )
        )
        return findings
    documented = {released for _heading, released in _released_headings(headings)}
    findings.extend(
        _finding(
            "warn",
            "release.undocumented-tag",
            f"tag {tag} has no `## {tag}` heading in {_CHANGELOG}",
            tag,
            f"Add the `## {tag}` section it released, or accept the historical gap.",
        )
        for tag in release_tags
        if split_version(tag)[0] not in documented
    )
    return findings


# --------------------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------------------


def _pinned_test_runner(root: Path) -> str | None:
    """The `[test].runner` recorded in `<root>/<AITNA_ROOT>/.akmon.toml`, if any.

    Attach (BOOTSTRAP §A5) pins the project's *existing* test environment here — `uv` may be
    absent, and a Python project usually already has its own manager (poetry/pdm/pip-venv/conda)
    and an env with pytest, so the right move is to *use what is there*, decided once at attach,
    not to re-guess (or build a second `<AITNA_ROOT>/.venv`) on every run. Absent → fall back to
    `_pytest_command`'s discovery for projects that predate this field.
    """
    test = read_akmon_toml(aitna_root(root) / ".akmon.toml").get("test")
    runner = test.get("runner") if isinstance(test, dict) else None
    return runner.strip() if isinstance(runner, str) and runner.strip() else None


def _pytest_command(root: Path, tests: str) -> list[str]:
    """Resolve a test runner: the pinned `test_runner` (attach record) first, else discovery.

    Discovery order: the dev-layer venv BOOTSTRAP §A5 provisions (`<AITNA_ROOT>/.venv`) → a system
    pytest → `uv` → `python -m pytest`. The dev venv comes first because it is the deliberately-
    provisioned env; `uv` is a fallback, and when used it must install pytest on the fly
    (`--with pytest`) — a bare `uv run pytest` runs in an ephemeral env *without* pytest and fails.

    The dev venv is invoked as `<venv>/bin/python -m pytest`, never via its `bin/pytest` console
    script: that script bakes an absolute-path shebang at creation, so a relocated/recopied venv
    leaves it pointing at a missing interpreter (FileNotFoundError) even though pytest imports fine.
    Mirror the dev-deps in §A5 if the dev venv grows more than pytest.
    """
    pinned = _pinned_test_runner(root)
    if pinned:
        return [*pinned.split(), tests]
    venv_python = aitna_root(root) / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return [str(venv_python), "-m", "pytest", tests]
    if shutil.which("pytest"):
        return ["pytest", tests]
    if shutil.which("uv"):
        return ["uv", "run", "--with", "pytest", "pytest", tests]
    return [sys.executable, "-m", "pytest", tests]


def run_check(root: Path, subject: str) -> int:
    """``--check``: run the version/changelog cross-check plus the subject's release suite."""
    # The version join runs before the suites and against the tree the tag is cut from: for the
    # akmon subject that is the standard's own tree, for package the project root.
    version_findings = check_release_versions(KEYSTONE_ROOT if subject == "akmon" else root)
    print("== version ↔ changelog cross-check")
    print_findings(version_findings)
    print()

    if subject == "akmon":
        commands = [
            [sys.executable, str(META / "self_ci.py")],
            _pytest_command(KEYSTONE_ROOT, str(META / "tests")),
        ]
        failed = _run_commands(KEYSTONE_ROOT, commands)
    else:  # package — the project's own suite. Keep verify (the akmon contract still
        # applies), then defer to the project's documented commands rather than guessing.
        commands = [
            [sys.executable, str(BIN / "verify.py"), "--project-root", str(root), "--strict", "--quiet"],
        ]
        failed = _run_commands(root, commands)
        charter = root / _release_charter()
        if charter.is_file():
            print(f"\n# package release: run the project's own checks from {_release_charter()}")
            print("# (tests / lint / build — this tool does not guess them).")
        else:
            print(f"\n! {_release_charter()} is missing — add it with the project's release commands.")
            failed.append(_release_charter())

    if exit_code(version_findings):
        failed.append("version ↔ changelog cross-check")

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
    """The owner-run command set, with the version bump ahead of the staging step.

    The order is load-bearing, not cosmetic. Until C54 this plan staged ``CHANGELOG.md`` and
    never mentioned a version literal, which is why the tree at tag ``v0.3.0`` still carried
    ``0.3.0.dev0``: the procedure produced the exact mismatch a checker would then report, and a
    checker reporting a defect its own procedure keeps re-creating is theatre. So the bump comes
    first, both literals are named, and both are staged explicitly.
    """
    if not _VERSION_RE.match(version):
        print(f"error: version must look like vX.Y.Z, got {version!r}", file=sys.stderr)
        return 2
    literal, _ = split_version(version)
    print("# Owner-run release plan (D5 — prepared by the release role, executed by the owner).")
    print("# Stage files EXPLICITLY — never `git add -A` — so untracked noise")
    print("# (e.g. __pycache__/) is not swept into the release commit.")
    print()
    if subject == "akmon":
        print(f"cd {aitna_root_name()}/akmon            # tag is cut from the submodule's own tree")
        commit_subject = "akmon"
        staged = "CHANGELOG.md pyproject.toml src/akmon/__init__.py"
    else:  # package — run from the project root.
        commit_subject = "release"
        staged = "CHANGELOG.md"
    print()
    print(f"# 1. Bump the version to {literal} in BOTH literals — one release bump is two edits,")
    print("#    and the tag records the reviewed state rather than producing the number:")
    if subject == "akmon":
        print(f'#      pyproject.toml           version = "{literal}"')
        print(f'#      src/akmon/__init__.py    _STATIC_VERSION = "{literal}"')
    else:
        print(f"#      the project's own version literal(s), per {_release_charter()}")
    print(f"# 2. Cut CHANGELOG.md's `## Unreleased` section to `## {version}`.")
    print("# 3. Re-run --check: the version <-> changelog cross-check must be green before the tag.")
    print()
    if subject == "akmon":
        print(f"git add {staged}")
    else:
        print(f"git add {staged}            # + the project's version literal(s) and reviewed edits")
    print("git status                      # confirm: no __pycache__/ or stray files staged")
    print()
    print(f'git commit -m "{commit_subject} {version}"')
    print(f"git tag {version}              # the tag points at THIS commit, not a prior HEAD")
    print("git push origin main --tags")
    if subject == "package":
        print(f"\n# package also: build + publish per {_release_charter()} (owner-run).")
    print()
    print("# 4. After the push, reopen the cycle: set both literals to the next development")
    print("#    version (`<next>.dev0`) and add a fresh `## Unreleased` heading. Until then the")
    print(f"#    tree is a released {literal} whose tag exists, which --check reports as a re-release.")
    print()
    print("# This tool does not run any of the above. The owner executes them.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: dispatch to ``--state``/``--check``/``--plan`` for the chosen subject."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument(
        "--subject",
        choices=SUBJECTS,
        default="akmon",
        help="Release subject: akmon (the standard's tag, default) or package (the project's own version).",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--state", action="store_true", help="Summarize TASKS / CHANGELOG / git status.")
    group.add_argument("--check", action="store_true", help="Run the subject's release suite (default).")
    group.add_argument("--plan", metavar="vX.Y.Z", help="Print the owner-run commit/tag/push command set.")
    args = parser.parse_args(argv)

    if args.plan:
        return run_plan(args.plan, args.subject)

    root, root_notice = resolve_project_root(args.project_root)
    if root_notice:
        print(root_notice, file=sys.stderr)
    if args.state:
        return run_state(root, args.subject)
    return run_check(root, args.subject)


if __name__ == "__main__":
    raise SystemExit(main())
