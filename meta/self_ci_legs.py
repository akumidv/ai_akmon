#!/usr/bin/env python3
"""Which self-CI legs a set of changed paths can affect (A49, D-A49-SELFCI-CHECK).

``meta/self_ci.py`` runs about seventeen legs and takes minutes, so a pre-commit run runs only the legs
whose inputs a changed path touches. What each leg reads is data, ``self_ci_legs.json``, in the glob
dialect that file states; this module reads it and answers the one question. The change set itself comes
from git (``git_changed_paths``) — ``akmon check --changed`` never lists the dev layer, ``meta/`` here —
or from paths the caller names.

The rule that keeps a skip honest: a leg is skipped only when **no** changed path matches its
inputs. A path no leg reads and the file does not list under ``no_leg`` is an unknown path, and an
unknown path runs every leg — the table is allowed to be incomplete, never to hide a leg. The one
deliberate exception is a ``full_only`` leg (D-A49-SELFCI-GAIN): the slowest ones run only in a full run
and in CI, and a selection that defers them says so by name.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from common import jsondata

LEGS_FILE = Path(__file__).resolve().parent / "self_ci_legs.json"

#: The ``{files}`` spelling of "the whole project", which ``akmon check`` passes on a full run.
WHOLE_PROJECT = "."

#: The git argv that lists staged, unstaged and untracked (not ignored) paths against HEAD, NUL-separated.
_GIT_STATUS = ("status", "--porcelain=v1", "-z", "--untracked-files=all")

#: A status entry is two status letters and a space, then the path.
_STATUS_PREFIX = 3

_SET_PREFIX = "@"
#: How many triggering paths a "run" line names before it says "...".
_SHOWN = 3


def glob_regex(pattern: str) -> str:
    """The regular expression for one pattern of the table's glob dialect (see the data file)."""
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        elif pattern[index] == "[" and (close := pattern.find("]", index + 1)) != -1:
            out.append(pattern[index : close + 1])
            index = close + 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    return "".join(out)


def path_matches(path: str, patterns: Sequence[str]) -> bool:
    """Whether ``path`` matches any of ``patterns``."""
    return any(re.fullmatch(glob_regex(pattern), path) for pattern in patterns)


@dataclass(frozen=True)
class LegSelection:
    """The outcome of a selection: the legs to run with why, and the legs skipped."""

    reasons: Mapping[str, str]
    skipped: tuple[str, ...]
    full: bool = False
    deferred: tuple[str, ...] = ()

    @property
    def legs(self) -> frozenset[str]:
        """The names of the legs to run."""
        return frozenset(self.reasons)


@dataclass(frozen=True)
class LegTable:
    """What each leg reads, with the paths that trigger every leg and the paths that trigger none."""

    legs: Mapping[str, tuple[str, ...]]
    always: tuple[str, ...]
    no_leg: tuple[str, ...]
    full_only: tuple[str, ...] = ()

    def select(self, changed: Sequence[str] | None, *, defer_full_only: bool = False) -> LegSelection:
        """The legs ``changed`` can affect; ``None``, no paths or ``.`` selects every leg.

        With ``defer_full_only`` a leg the table marks ``full_only`` is moved from the legs to run to
        ``deferred`` when a changed path selects it; a full run never defers.
        """
        paths = [path.removeprefix("./") for path in changed or ()]
        if not paths or WHOLE_PROJECT in paths:
            reason = "full run: no changed files given"
            return LegSelection(dict.fromkeys(self.legs, reason), (), full=True)
        triggers: dict[str, list[str]] = {leg: [] for leg in self.legs}
        for path in paths:
            if path_matches(path, self.always):
                for leg in self.legs:
                    triggers[leg].append(f"{path} (changes the selection itself)")
                continue
            hit = [leg for leg, patterns in self.legs.items() if path_matches(path, patterns)]
            if hit:
                for leg in hit:
                    triggers[leg].append(path)
            elif not path_matches(path, self.no_leg):
                for leg in self.legs:
                    triggers[leg].append(f"{path} (no leg declares it: every leg runs)")
        reasons = {
            leg: ", ".join(found[:_SHOWN]) + (", ..." if len(found) > _SHOWN else "")
            for leg, found in triggers.items()
            if found
        }
        deferred: tuple[str, ...] = ()
        if defer_full_only:
            deferred = tuple(leg for leg in self.legs if leg in reasons and leg in self.full_only)
            reasons = {leg: reason for leg, reason in reasons.items() if leg not in deferred}
        skipped = tuple(leg for leg in self.legs if leg not in reasons and leg not in deferred)
        return LegSelection(reasons, skipped, deferred=deferred)


@dataclass(frozen=True)
class ChangeSet:
    """The change set a run selects by: ``paths`` is ``None`` for a full run; ``source`` says where it came from."""

    source: str
    paths: tuple[str, ...] | None


def resolve_change_set(root: Path, paths: Sequence[str] = (), *, full: bool = False) -> ChangeSet:
    """The change set of one run.

    ``--full`` or ``.`` is every leg and named paths are those paths; with neither, the paths come from
    git at ``root``, and a clean tree is a full run.
    """
    if full:
        return ChangeSet("full run (--full)", None)
    if paths:
        if WHOLE_PROJECT in paths:
            return ChangeSet(f"full run ({WHOLE_PROJECT!r} given)", None)
        return ChangeSet(f"paths given ({len(paths)})", tuple(paths))
    changed = git_changed_paths(root)
    if not changed:
        return ChangeSet("git: clean tree, full run", None)
    return ChangeSet(f"git ({len(changed)} changed paths)", tuple(changed))


def _expand(entries: Sequence[str], sets: Mapping[str, tuple[str, ...]], owner: str) -> tuple[str, ...]:
    patterns: list[str] = []
    for entry in entries:
        if not entry.startswith(_SET_PREFIX):
            patterns.append(entry)
        elif entry[1:] in sets:
            patterns.extend(sets[entry[1:]])
        else:
            raise jsondata.DataFileError(
                f"{LEGS_FILE.name}: {owner} names the set {entry!r}, which is not declared before it"
            )
    return tuple(patterns)


def read_leg_table(path: Path = LEGS_FILE) -> LegTable:
    """Parse the data file at ``path`` into a table, expanding every ``@set`` reference."""
    data = jsondata.read(path)
    sets: dict[str, tuple[str, ...]] = {}
    for name, entries in data["sets"].items():
        sets[name] = _expand(entries, sets, f"set {name!r}")
    legs = {leg: _expand(entries, sets, f"leg {leg!r}") for leg, entries in data["legs"].items()}
    full_only = tuple(data.get("full_only", ()))
    for leg in full_only:
        if leg not in legs:
            raise jsondata.DataFileError(f"{path.name}: full_only names {leg!r}, which is not a declared leg")
    return LegTable(legs, tuple(data["always"]), tuple(data["no_leg"]), full_only)


class ChangeSetError(RuntimeError):
    """The changed paths could not be read from git."""


def git_changed_paths(root: Path) -> list[str]:
    """The paths that differ from ``HEAD`` under ``root``, the dev layer included, sorted.

    Staged, unstaged and untracked (not ignored) paths; a rename or copy counts both its old and its new
    path, and a deletion counts the deleted path. An empty list is a clean tree.
    """
    try:
        result = subprocess.run(["git", "-C", str(root), *_GIT_STATUS], capture_output=True, check=False)
    except OSError as exc:
        raise ChangeSetError(f"git is not runnable ({exc.strerror or exc})") from exc
    if result.returncode != 0:
        raise ChangeSetError(f"`git {' '.join(_GIT_STATUS)}` failed in {root} with exit status {result.returncode}")
    entries = result.stdout.decode("utf-8", "replace").split("\0")
    paths: set[str] = set()
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) <= _STATUS_PREFIX:
            continue
        paths.add(entry[_STATUS_PREFIX:])
        if entry[0] in "RC" or entry[1] in "RC":  # the next entry is the path it came from
            if index < len(entries) and entries[index]:
                paths.add(entries[index])
            index += 1
    return sorted(paths)


def report_lines(selection: LegSelection) -> list[str]:
    """One line per leg saying whether it ran and why, so no skip is silent."""
    if selection.full:
        return ["self-ci: full run, every leg"]
    lines = [f"self-ci: run {leg} — {reason}" for leg, reason in selection.reasons.items()]
    lines += [f"self-ci: {leg}: deferred to the full run / CI" for leg in selection.deferred]
    lines += [f"self-ci: skip {leg} — no changed path matches its inputs" for leg in selection.skipped]
    if not selection.reasons and not selection.deferred:
        lines.append("self-ci: no leg reads the changed paths, nothing to run")
    return lines
