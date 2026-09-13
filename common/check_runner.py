#!/usr/bin/env python3
"""``akmon check`` — run the checks a project declares (ADR 0014 §4, as amended).

akmon ships no linter of its own. A project names its checks in the ``[check]`` table of the
integration record — its own linter, its type checker, or ruff configured with akmon's rules
(``profiles/ruff.toml``) — and this module runs them: each command as the project itself would
run it, its output passed through untouched, and one finding per command for the result.

    [check]
    lint = "uv run ruff check {files}"
    types = { command = "uv run mypy {files}", files = ["*.py"] }

``{files}`` is replaced by the files a run covers: ``.`` for the whole project, or — under
``--changed`` — the changed files matching the check's ``files`` patterns (``*.py`` when it names
none). A command without the placeholder runs unchanged either way. Stdlib-only.
"""

from __future__ import annotations

import fnmatch
import shlex
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from common.findings import Finding
from common.project_root import aitna_root_name

CONFIG_TARGET = ".akmon.toml [check]"
FILES_PLACEHOLDER = "{files}"
DEFAULT_FILES = ("*.py",)
_SPEC_KEYS = {"command", "files"}


@dataclass(frozen=True)
class Check:
    """One declared check: a name, the command's argv (placeholder kept) and its file patterns."""

    name: str
    argv: tuple[str, ...]
    files: tuple[str, ...] = DEFAULT_FILES


class ScopeError(RuntimeError):
    """The changed files could not be listed."""


def _string_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) for item in value)


def read_checks(table: object) -> tuple[list[Check], list[str]]:
    """The checks the record's ``[check]`` table declares, and every problem found in it.

    Strict: a malformed entry is reported and skipped, never guessed at — a check that silently
    stopped running is the one failure a gate must not have.
    """
    if table is None:
        return [], []
    if not isinstance(table, Mapping):
        return [], ["[check] must be a table of named commands"]
    checks, problems = [], []
    for name, value in table.items():
        spec = {"command": value} if isinstance(value, str) else value
        if not isinstance(spec, Mapping):
            problems.append(f"[check].{name} must be a command string or a table with `command`")
            continue
        unknown = sorted(set(spec) - _SPEC_KEYS)
        if unknown:
            problems.append(f"[check].{name} has an unknown key {unknown[0]!r}")
            continue
        command, files = spec.get("command"), spec.get("files", list(DEFAULT_FILES))
        if not isinstance(command, str) or not command.strip():
            problems.append(f"[check].{name} needs a non-empty `command`")
            continue
        if not _string_list(files):
            problems.append(f"[check].{name}.files must be a non-empty list of glob patterns")
            continue
        try:
            argv = tuple(shlex.split(command))
        except ValueError as exc:
            problems.append(f"[check].{name} command does not split into arguments: {exc}")
            continue
        checks.append(Check(str(name), argv, tuple(files)))
    return checks, problems


def changed_files(root: Path) -> list[str]:
    """Files that differ from ``HEAD`` or are new and not ignored — never the dev layer."""
    try:
        names = []
        for args in (("diff", "--name-only", "-z", "HEAD", "--"), ("ls-files", "--others", "--exclude-standard", "-z")):
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
            names += [name for name in result.stdout.decode("utf-8", "replace").split("\0") if name]
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ScopeError(f"cannot list the files changed against HEAD: {exc}") from exc
    dev_layer = f"{aitna_root_name()}/"
    return sorted({name for name in names if not name.startswith(dev_layer) and (root / name).is_file()})


def argv_for(check: Check, changed: list[str] | None) -> list[str] | None:
    """The argv one run executes, or ``None`` when ``--changed`` left it nothing to check."""
    if FILES_PLACEHOLDER not in check.argv:
        return list(check.argv)
    if changed is None:
        files = ["."]
    else:
        files = [name for name in changed if any(fnmatch.fnmatchcase(name, pattern) for pattern in check.files)]
        if not files:
            return None
    argv: list[str] = []
    for part in check.argv:
        argv.extend(files if part == FILES_PLACEHOLDER else [part])
    return argv


Runner = Callable[..., subprocess.CompletedProcess]


def run_checks(
    root: Path, checks: list[Check], changed: list[str] | None, runner: Runner = subprocess.run
) -> list[Finding]:
    """Run every check in declaration order; the command's own output goes straight through."""
    findings = []
    for check in checks:
        target = f"[check].{check.name}"
        argv = argv_for(check, changed)
        if argv is None:
            findings.append(
                Finding(
                    "ok",
                    "check.run",
                    "no changed file it checks",
                    target,
                    "Nothing to do until a matching file changes",
                )
            )
            continue
        try:
            result = runner(argv, cwd=root, check=False)
        except FileNotFoundError:
            findings.append(
                Finding(
                    "error",
                    "check.run",
                    f"`{argv[0]}` is not installed or not on PATH, so the check did not run",
                    target,
                    f"Install `{argv[0]}` in the project's environment or change the command under {target}",
                )
            )
            continue
        if result.returncode == 0:
            findings.append(Finding("ok", "check.run", f"`{shlex.join(argv)}` passed", target, "Keep it passing"))
        else:
            findings.append(
                Finding(
                    "error",
                    "check.run",
                    f"`{shlex.join(argv)}` exited {result.returncode}",
                    target,
                    "Fix what the command reported above, or change its configuration in the project",
                )
            )
    return findings
