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

import errno
import fnmatch
import shlex
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from common import jsondata
from common.findings import Finding, read_findings_data
from common.project_root import aitna_root_name

_SPEC_KEYS = {"command", "files"}


def _check_data() -> dict:
    """The ``[check]`` texts, the git argv and the problem templates, as the data file carries them."""
    return jsondata.read(Path(__file__).parent / "check_runner.json")


def config_target() -> str:
    """The target a ``check.config`` finding names."""
    return _check_data()["config_target"]


def files_placeholder() -> str:
    """The placeholder a command replaces with the files a run covers."""
    return _check_data()["files_placeholder"]


def default_files() -> tuple[str, ...]:
    """The file patterns a check covers when it names none."""
    return tuple(_check_data()["default_files"])


def repair_record_fix() -> str:
    """The ``check.config`` fix ``akmon check`` gives for an unparseable record."""
    return _check_data()["check_config"]["repair_record"]


def repair_record_verify_fix() -> str:
    """The ``check.config`` fix ``verify`` gives for an unparseable record."""
    return _check_data()["check_config"]["repair_record_verify"]


def correct_entry_fix() -> str:
    """The ``check.config`` fix both ``akmon check`` and ``verify`` give for a malformed entry."""
    return _check_data()["check_config"]["correct_entry"]


def no_checks() -> tuple[str, str]:
    """The ``(message, fix)`` ``akmon check`` gives when the record names no checks at all."""
    data = _check_data()["check_config"]
    return data["no_checks"], data["no_checks_fix"]


def scope_fix() -> str:
    """The ``check.scope`` fix ``akmon check`` gives when the changed files cannot be listed."""
    return _check_data()["check_config"]["scope_fix"]


def check_table_ok() -> tuple[str, str]:
    """The ``(message, fix)`` ``verify``'s ``[check]`` table check gives when every entry is sound.

    The message carries the ``{{count}}`` placeholder ``verify`` fills with the table's size.
    """
    data = _check_data()["check_config"]
    return data["check_table_ok"], data["check_table_ok_fix"]


@dataclass(frozen=True)
class Check:
    """One declared check: a name, the command's argv (placeholder kept) and its file patterns."""

    name: str
    argv: tuple[str, ...]
    files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.files:
            object.__setattr__(self, "files", default_files())


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
    problems_data = _check_data()["problems"]
    if not isinstance(table, Mapping):
        return [], [problems_data["not_table"]]
    checks, problems = [], []
    for name, value in table.items():
        spec = {"command": value} if isinstance(value, str) else value
        if not isinstance(spec, Mapping):
            problems.append(jsondata.fill(problems_data["bad_entry"], {"name": str(name)}))
            continue
        unknown = sorted(set(spec) - _SPEC_KEYS)
        if unknown:
            problems.append(jsondata.fill(problems_data["unknown_key"], {"name": str(name), "key": repr(unknown[0])}))
            continue
        command, files = spec.get("command"), spec.get("files", list(default_files()))
        if not isinstance(command, str) or not command.strip():
            problems.append(jsondata.fill(problems_data["needs_command"], {"name": str(name)}))
            continue
        if not _string_list(files):
            problems.append(jsondata.fill(problems_data["bad_files"], {"name": str(name)}))
            continue
        try:
            argv = tuple(shlex.split(command))
        except ValueError as exc:
            problems.append(jsondata.fill(problems_data["unsplit_command"], {"name": str(name), "error": str(exc)}))
            continue
        checks.append(Check(str(name), argv, tuple(files)))
    return checks, problems


def changed_files(root: Path) -> list[str]:
    """Files that differ from ``HEAD`` or are new and not ignored — never the dev layer."""
    data = _check_data()
    names = []
    for args in data["git_commands"]:
        # The message names the git command and its outcome, never the interpreter's exception
        # text: it is spec shared with the JavaScript implementation (ADR 0020 D03). The argv
        # carries -z (NUL separators); the display line strips it.
        command = "git " + " ".join(arg for arg in args if arg != "-z")
        try:
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
        except OSError as exc:
            reason = errno.errorcode.get(exc.errno or 0, "not runnable")
            raise ScopeError(jsondata.fill(data["scope_error"]["git_unrunnable"], {"reason": reason})) from exc
        if result.returncode != 0:
            raise ScopeError(
                jsondata.fill(
                    data["scope_error"]["git_failed"],
                    {"command": command, "returncode": str(result.returncode)},
                )
            )
        names += [name for name in result.stdout.decode("utf-8", "replace").split("\0") if name]
    dev_layer = f"{aitna_root_name()}/"
    return sorted({name for name in names if not name.startswith(dev_layer) and (root / name).is_file()})


def argv_for(check: Check, changed: list[str] | None) -> list[str] | None:
    """The argv one run executes, or ``None`` when ``--changed`` left it nothing to check."""
    placeholder = files_placeholder()
    if placeholder not in check.argv:
        return list(check.argv)
    if changed is None:
        files = ["."]
    else:
        files = [name for name in changed if any(fnmatch.fnmatchcase(name, pattern) for pattern in check.files)]
        if not files:
            return None
    argv: list[str] = []
    for part in check.argv:
        argv.extend(files if part == placeholder else [part])
    return argv


Runner = Callable[..., subprocess.CompletedProcess]


def run_checks(
    root: Path, checks: list[Check], changed: list[str] | None, runner: Runner = subprocess.run
) -> list[Finding]:
    """Run every check in declaration order; the command's own output goes straight through."""
    findings = []
    runs = _check_data()["check_run"]
    record = read_findings_data()  # one read of the envelope's vocabulary per run, not per finding
    for check in checks:
        target = f"[check].{check.name}"
        argv = argv_for(check, changed)
        if argv is None:
            nothing = runs["nothing_to_do"]
            findings.append(Finding("ok", "check.run", nothing["message"], target, nothing["fix"], data=record))
            continue
        try:
            result = runner(argv, cwd=root, check=False)
        except FileNotFoundError:
            not_installed = runs["not_installed"]
            findings.append(
                Finding(
                    "error",
                    "check.run",
                    jsondata.fill(not_installed["message"], {"command": argv[0]}),
                    target,
                    jsondata.fill(not_installed["fix"], {"command": argv[0], "target": target}),
                    data=record,
                )
            )
            continue
        if result.returncode == 0:
            passed = runs["passed"]
            findings.append(
                Finding(
                    "ok",
                    "check.run",
                    jsondata.fill(passed["message"], {"command": shlex.join(argv)}),
                    target,
                    passed["fix"],
                    data=record,
                )
            )
        else:
            failed = runs["failed"]
            findings.append(
                Finding(
                    "error",
                    "check.run",
                    jsondata.fill(
                        failed["message"], {"command": shlex.join(argv), "returncode": str(result.returncode)}
                    ),
                    target,
                    failed["fix"],
                    data=record,
                )
            )
    return findings
