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
AKMON_ROOT = Path(__file__).resolve().parents[2]
BIN = AKMON_ROOT / "bin"  # the two launchers; the shared library lives in ``common``.
# akmon's own development layer (self-CI runner + tests) lives under meta/.
META = AKMON_ROOT / "meta"

# The shared finding envelope, the root walk and the version-spelling rule all ship in the
# standard's own ``common`` package (stdlib-only, no install), so this tool speaks the same
# five fields every other check does and compares versions by the one rule that also governs the
# CLI's skew notice.
sys.path.insert(0, str(AKMON_ROOT))

from common import jsondata  # noqa: E402
from common.findings import Finding, exit_code, line_safe, print_findings  # noqa: E402
from common.project_root import aitna_root, aitna_root_name, resolve_project_root  # noqa: E402
from common.record import read_akmon_toml  # noqa: E402
from common.versions import is_final, split_version  # noqa: E402

_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
_UNRELEASED_RE = re.compile(r"^##\s+Unreleased\b", re.MULTILINE | re.IGNORECASE)


def _release_data() -> dict:
    """The release tool's texts and subject facts (``release.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "release.json")


def subjects() -> tuple[str, ...]:
    """The release subjects: the akmon standard's own tag, or the consuming project's package."""
    return tuple(_release_data()["subjects"])


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
    texts = _release_data()["run_state"]
    if not shutil.which("git"):
        return texts["git_not_found"]
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--short"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - defensive
        return jsondata.fill(texts["git_status_failed"], {"exc": exc})
    out = proc.stdout.strip()
    return out if out else texts["git_clean"]


def _changelog_summary(akmon: Path) -> list[str]:
    texts = _release_data()["run_state"]
    changelog = changelog_name()
    text = _read(akmon / changelog)
    if not text:
        return [jsondata.fill(texts["file_missing"], {"name": changelog})]
    lines = [texts["changelog_sections"]]
    lines.extend(
        jsondata.fill(texts["changelog_section_item"], {"heading": match.group(1).strip()})
        for match in re.finditer(r"^##\s+(.+)$", text, re.MULTILINE)
    )
    if not _UNRELEASED_RE.search(text):
        lines.append(texts["changelog_no_unreleased"])
    return lines


def _tasks_summary(tasks_dir: Path) -> list[str]:
    out: list[str] = []
    texts = _release_data()["run_state"]
    for name in ("TASKS.md", "TASKS_ARCHIVE.md"):
        text = _read(tasks_dir / name)
        if not text:
            out.append(jsondata.fill(texts["file_missing"], {"name": name}))
            continue
        entries = [ln.strip() for ln in text.splitlines() if ln.lstrip().startswith("- ") and " · " in ln]
        out.append(jsondata.fill(texts["file_entry_count"], {"name": name, "count": len(entries)}))
        if name == "TASKS.md":
            done = [ln for ln in entries if re.search(r"\bdone\b", ln)]
            if done:
                out.append(jsondata.fill(texts["done_move_note"], {"count": len(done)}))
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

    texts = _release_data()["run_state"]
    print(jsondata.fill(texts["state_header"], {"subject": subject}))
    print(jsondata.fill(texts["project_root_line"], {"root": root}))
    print()
    for line in _tasks_summary(tasks_dir):
        print(line)
    print()
    for line in _changelog_summary(changelog_dir):
        print(line)
    print()
    if subject == "package":
        charter = root / _release_charter()
        note = texts["charter_found"] if charter.is_file() else texts["charter_missing"]
        print(jsondata.fill(texts["charter_line"], {"charter": _release_charter(), "note": note}))
        print()
    print(jsondata.fill(texts["git_status_header"], {"name": git_dir.name}))
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

def changelog_name() -> str:
    """The changelog file whose topmost released window the version is checked against."""
    return _release_data()["changelog_name"]


def pyproject_name() -> str:
    """The file holding the ``[project].version`` literal hatchling stamps into the wheel."""
    return _release_data()["pyproject_name"]


def static_version_file() -> str:
    """The file holding the ``_STATIC_VERSION`` fallback literal for an uninstalled package."""
    return _release_data()["static_version_file"]

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
# admissible release tag (ADR-0018/D01); the bare form is matched here so that a
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
    changelog, pyproject, static_file = changelog_name(), pyproject_name(), static_version_file()
    findings_data = _release_data()["findings"]
    changelog_path = root / changelog
    # Read once: two rules ask about the same headings, and a file re-read between them could
    # answer them from two different files.
    headings = _changelog_headings(changelog_path)

    declared = _pyproject_version(root / pyproject)
    fallback = _static_version(root / static_file)
    if declared is not None and fallback is not None:
        if declared == fallback:
            findings.append(
                _finding(
                    "ok",
                    "release.version-literals",
                    jsondata.fill(
                        findings_data["version-literals-match"]["message"],
                        {"pyproject": pyproject, "static_version_file": static_file, "declared": declared},
                    ),
                    pyproject,
                    findings_data["version-literals-match"]["fix"],
                )
            )
        else:
            findings.append(
                _finding(
                    "error",
                    "release.version-literals",
                    jsondata.fill(
                        findings_data["version-literals-mismatch"]["message"],
                        {
                            "pyproject": pyproject,
                            "static_version_file": static_file,
                            "declared": declared,
                            "fallback": fallback,
                        },
                    ),
                    pyproject,
                    findings_data["version-literals-mismatch"]["fix"],
                )
            )
    # `pyproject` wins when both exist: it is the literal that names the built wheel, and the
    # disagreement itself has already been reported above.
    version = declared if declared is not None else fallback

    if version is None:
        findings.append(
            _skip(
                jsondata.fill(
                    findings_data["no-version-source"]["message"],
                    {"pyproject": pyproject, "static_version_file": static_file},
                ),
                "",
                findings_data["no-version-source"]["fix"],
            )
        )
    elif not changelog_path.is_file():
        findings.append(
            _skip(
                jsondata.fill(
                    findings_data["changelog-absent"]["message"], {"changelog": changelog, "version": version}
                ),
                changelog,
                jsondata.fill(findings_data["changelog-absent"]["fix"], {"changelog": changelog}),
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
    changelog = changelog_name()
    texts = _release_data()["findings"]
    base, _ = split_version(version)
    if not is_final(version):
        if headings and _UNRELEASED_HEADING_RE.match(headings[0]):
            return [
                _finding(
                    "ok",
                    "release.changelog-window",
                    jsondata.fill(texts["window-nonfinal-ok"]["message"], {"version": version}),
                    changelog,
                    texts["window-nonfinal-ok"]["fix"],
                )
            ]
        observed = (
            jsondata.fill(texts["window-nonfinal-heading"], {"heading": headings[0]})
            if headings
            else texts["window-nonfinal-none"]
        )
        return [
            _finding(
                "error",
                "release.changelog-window",
                jsondata.fill(texts["window-nonfinal-error"]["message"], {"version": version, "observed": observed}),
                changelog,
                texts["window-nonfinal-error"]["fix"],
            )
        ]
    released = _released_headings(headings)
    if not released:
        return [
            _finding(
                "error",
                "release.changelog-window",
                jsondata.fill(
                    texts["window-final-no-released"]["message"], {"version": version, "changelog": changelog}
                ),
                changelog,
                jsondata.fill(texts["window-final-no-released"]["fix"], {"base": base}),
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
                jsondata.fill(
                    texts["window-final-topmost-mismatch"]["message"], {"version": version, "topmost": topmost}
                ),
                changelog,
                jsondata.fill(texts["window-final-topmost-mismatch"]["fix"], {"base": base, "topmost": topmost}),
            )
        ]
    return [
        _finding(
            "ok",
            "release.changelog-window",
            jsondata.fill(texts["window-final-ok"]["message"], {"version": version, "topmost": topmost}),
            changelog,
            texts["window-final-ok"]["fix"],
        )
    ]


def _check_tags(root: Path, version: str | None, *, has_changelog: bool, headings: list[str]) -> list[Finding]:
    """The two git-dependent rules: the re-release warn and the tag-coverage warn."""
    findings: list[Finding] = []
    changelog = changelog_name()
    texts = _release_data()["findings"]
    tags = _git_tags(root)
    final = version is not None and is_final(version)
    if tags is None:
        if final:
            findings.append(
                _skip(
                    jsondata.fill(texts["git-unavailable-final"]["message"], {"version": version}),
                    "",
                    texts["git-unavailable-final"]["fix"],
                )
            )
        findings.append(
            _skip(
                jsondata.fill(texts["git-unavailable-tags"]["message"], {"changelog": changelog}),
                changelog,
                texts["git-unavailable-tags"]["fix"],
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
            jsondata.fill(texts["tag-spelling"]["message"], {"tag": tag}),
            tag,
            jsondata.fill(texts["tag-spelling"]["fix"], {"tag": tag}),
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
                    jsondata.fill(texts["retag"]["message"], {"version": version, "tag": matching[0]}),
                    matching[0],
                    texts["retag"]["fix"],
                )
            )
    if not has_changelog:
        # Unrunnable, not inapplicable: there are tags, and nothing to check them against.
        findings.append(
            _skip(
                jsondata.fill(texts["changelog-absent-tags"]["message"], {"changelog": changelog}),
                changelog,
                jsondata.fill(texts["changelog-absent-tags"]["fix"], {"changelog": changelog}),
            )
        )
        return findings
    documented = {released for _heading, released in _released_headings(headings)}
    findings.extend(
        _finding(
            "warn",
            "release.undocumented-tag",
            jsondata.fill(texts["undocumented-tag"]["message"], {"tag": tag, "changelog": changelog}),
            tag,
            jsondata.fill(texts["undocumented-tag"]["fix"], {"tag": tag}),
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
    texts = _release_data()["run_check"]
    version_findings = check_release_versions(AKMON_ROOT if subject == "akmon" else root)
    print(texts["cross_check_header"])
    print_findings(version_findings)
    print()

    if subject == "akmon":
        commands = [
            [sys.executable, str(META / "self_ci.py")],
            _pytest_command(AKMON_ROOT, str(META / "tests")),
        ]
        failed = _run_commands(AKMON_ROOT, commands)
    else:  # package — the project's own suite. Keep verify (the akmon contract still
        # applies), then defer to the project's documented commands rather than guessing.
        commands = [
            [sys.executable, str(BIN / "verify.py"), "--project-root", str(root), "--strict", "--quiet"],
        ]
        failed = _run_commands(root, commands)
        charter = root / _release_charter()
        if charter.is_file():
            print("\n" + jsondata.fill(texts["charter_runs_note"], {"charter": _release_charter()}))
            print(texts["charter_runs_note_suffix"])
        else:
            print("\n" + jsondata.fill(texts["charter_missing_note"], {"charter": _release_charter()}))
            failed.append(_release_charter())

    if exit_code(version_findings):
        failed.append(texts["version_check_failed_item"])

    print()
    if failed:
        print(texts["failed_header"])
        for item in failed:
            print(jsondata.fill(texts["failed_item"], {"item": item}))
        return 1
    print(texts["all_green"])
    return 0


def _display(command: list[str]) -> str:
    """How a suite command is shown: the akmon command it stands for, never the host interpreter path.

    The printed line is shared spec with the JavaScript implementation (ADR 0020 D03), so the
    interpreter this process happens to run under stays out of it.
    """
    if len(command) > 1 and command[0] == sys.executable:
        script = Path(command[1])
        if script == BIN / "verify.py":
            return " ".join(["akmon", "verify", *command[2:]])
        if script.is_relative_to(AKMON_ROOT):
            return " ".join(["python3", script.relative_to(AKMON_ROOT).as_posix(), *command[2:]])
    return " ".join(command)


def _run_commands(root: Path, commands: list[list[str]]) -> list[str]:
    failed: list[str] = []
    for command in commands:
        printable = _display(command)
        print(f"== {printable}", flush=True)
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
    plan = _release_data()["run_plan"]
    if not _VERSION_RE.match(version):
        print(jsondata.fill(plan["error_version"], {"version": repr(version)}), file=sys.stderr)
        return 2
    literal, _ = split_version(version)
    facts = plan["subjects"][subject]
    lines = [*plan["header"], ""]
    if subject == "akmon":
        lines.append(jsondata.fill(facts["cd_line"], {"aitna_root": aitna_root_name()}))
    lines.append("")
    lines += [jsondata.fill(line, {"literal": literal}) for line in plan["bump_note"]]
    if subject == "akmon":
        lines += [jsondata.fill(line, {"literal": literal}) for line in facts["literal_lines"]]
    else:  # package — run from the project root.
        lines.append(jsondata.fill(facts["literal_line"], {"charter": _release_charter()}))
    lines.append(jsondata.fill(plan["changelog_note"], {"version": version}))
    lines.append(plan["recheck_note"])
    lines.append("")
    lines.append(jsondata.fill(facts["staged_line"], {"staged": facts["staged_files"]}))
    lines.append(plan["git_status_line"])
    lines.append("")
    lines.append(jsondata.fill(plan["commit_line"], {"subject": facts["commit_subject"], "version": version}))
    lines.append(jsondata.fill(plan["tag_line"], {"version": version}))
    lines.append(plan["push_line"])
    if subject == "package":
        lines.append("\n" + jsondata.fill(facts["publish_note"], {"charter": _release_charter()}))
    lines.append("")
    lines += [jsondata.fill(line, {"literal": literal}) for line in plan["cycle_note"]]
    lines.append("")
    lines.append(plan["closing"])
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: dispatch to ``--state``/``--check``/``--plan`` for the chosen subject."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-root", type=Path, help="Project root. Defaults to cwd or a parent with AGENTS.md.")
    parser.add_argument(
        "--subject",
        choices=subjects(),
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
