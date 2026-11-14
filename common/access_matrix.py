"""The access matrix: what an actor may do, by action class (ADR 0031/D07).

Whether an action passes, asks or is denied is read from the actor (ADR 0025/D01) and the action
class; ``common/access_matrix.json`` holds the answers, keyed by actor and then by action class, each
``allow``, ``ask`` or ``deny``. Two other top-level keys are not actor rows: ``protected_branches`` lists per
actor the branches the guard treats like the default branch for that actor (a trailing ``*`` is a prefix
match: ``release/*``), and ``run_branch_patterns`` lists per actor the regular expressions a branch name
matches to be that actor's own run branch (ADR 0031/D07, D-C203-RUN-BRANCH). The commit guard
(``hooks/hook_core.py``) reads it, and so does C173's repertoire. The *parsing* — which command is which action
class, which repository and branch it acts on — stays in the guard's code; a style is not a key (D07).

The actor is carried by ``AKMON_ACTOR``, and an autonomous run's own branch by ``AKMON_RUN_BRANCH``, both set
by whatever launches the run. A hook's entry point reads them (like attendance, ADR 0025/D06) and passes the
:class:`Actor` and the run branch down: a pure function never reads the environment. A run with no actor
value, or one this module does not know, is a ``developer`` run.

The JavaScript twin is ``js/common/access_matrix.mjs``; the data is ``common/access_matrix.json``'s,
shared by both.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from common import jsondata

# The environment value that carries the actor, set by the launcher.
ACTOR_ENV = "AKMON_ACTOR"

# The environment value that names an autonomous run's own branch, set by the launcher (D-C203-RUN-BRANCH).
RUN_BRANCH_ENV = "AKMON_RUN_BRANCH"

# What an action class may be mapped to, from the most permissive to the most restrictive.
OUTCOMES = ("allow", "ask", "deny")

# The top-level key of the data file that is not an actor row: ``{actor: [branch, ...]}``.
PROTECTED_BRANCHES_KEY = "protected_branches"

# The other top-level key that is not an actor row: ``{actor: [regular expression, ...]}``.
RUN_BRANCH_PATTERNS_KEY = "run_branch_patterns"

_NON_ACTOR_KEYS = (PROTECTED_BRANCHES_KEY, RUN_BRANCH_PATTERNS_KEY)

# The action classes of driving the shared browser (ADR 0032/D07): from the developer's own session, and from a
# delegated agent (a subagent's tool event carries ``agent_id``, M189); the actor picks the row.
BROWSER_SESSION_CLASS = "browser_session"
BROWSER_DELEGATED_CLASS = "browser_delegated"

# The action class of an AI trailer (``Co-Authored-By``): a floor of the commit guard, denied for every actor.
AI_TRAILER_CLASS = "ai_trailer"


class Actor(enum.StrEnum):
    """Who drives a run, fixed for the run (ADR 0025/D01). The ``guided`` actor is A76's, not yet here."""

    DEVELOPER = "developer"
    AUTONOMOUS = "autonomous"


def actor_from_environment(environ: Mapping[str, str]) -> Actor:
    """The actor ``environ`` carries; ``developer`` where the value is absent or unknown.

    A hook entry point passes ``os.environ``; nothing below it reads the environment.
    """
    try:
        return Actor(environ.get(ACTOR_ENV, ""))
    except ValueError:
        return Actor.DEVELOPER


def run_branch_from_environment(environ: Mapping[str, str]) -> str | None:
    """The run branch ``environ`` names, or ``None`` where the value is absent or empty.

    A hook entry point passes ``os.environ``; nothing below it reads the environment.
    """
    return environ.get(RUN_BRANCH_ENV) or None


def read_data() -> dict[str, Any]:
    """The access matrix beside this module: ``{actor: {action class: outcome}}`` and the two branch keys.

    A matrix whose ``ai_trailer`` cell is not ``deny`` for some actor raises :class:`jsondata.DataFileError`:
    the trailer deny is a floor of the commit guard, so a matrix that softens it is broken, not a choice.
    So does a ``protected_branches`` that is not ``{actor: [branch, ...]}`` for every actor, and a
    ``run_branch_patterns`` that is not ``{actor: [regular expression, ...]}`` for every actor.
    """
    data = jsondata.read(Path(__file__).parent / "access_matrix.json")
    check_trailer_floor(data)
    check_protected_branches(data)
    check_run_branch_patterns(data)
    return data


def actor_rows(data: Mapping[str, Any]) -> dict[str, Any]:
    """The actor rows of ``data``: everything but the ``protected_branches`` and ``run_branch_patterns`` keys."""
    return {name: row for name, row in data.items() if name not in _NON_ACTOR_KEYS}


def check_trailer_floor(data: Mapping[str, Any]) -> None:
    """Raise :class:`jsondata.DataFileError` unless every actor's ``ai_trailer`` cell is ``deny``."""
    for actor, row in actor_rows(data).items():
        cell = row.get(AI_TRAILER_CLASS) if isinstance(row, Mapping) else None
        if cell != "deny":
            raise jsondata.DataFileError(
                f"access matrix entry {actor!r}/{AI_TRAILER_CLASS!r} is {cell!r}; "
                "an AI trailer is denied for every actor"
            )


def check_protected_branches(data: Mapping[str, Any]) -> None:
    """Raise :class:`jsondata.DataFileError` unless ``protected_branches`` maps every actor to a list of names."""
    protected = data.get(PROTECTED_BRANCHES_KEY)
    if not isinstance(protected, Mapping):
        raise jsondata.DataFileError(f"access matrix {PROTECTED_BRANCHES_KEY!r} is {protected!r}; expected a mapping")
    for actor in Actor:
        names = protected.get(actor.value)
        if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
            raise jsondata.DataFileError(
                f"access matrix {PROTECTED_BRANCHES_KEY!r}/{actor.value!r} is {names!r}; "
                "expected a list of branch names"
            )


def check_run_branch_patterns(data: Mapping[str, Any]) -> None:
    """Raise :class:`jsondata.DataFileError` unless ``run_branch_patterns`` maps every actor to a list of regexes."""
    patterns = data.get(RUN_BRANCH_PATTERNS_KEY)
    if not isinstance(patterns, Mapping):
        raise jsondata.DataFileError(f"access matrix {RUN_BRANCH_PATTERNS_KEY!r} is {patterns!r}; expected a mapping")
    for actor in Actor:
        expressions = patterns.get(actor.value)
        if not isinstance(expressions, list) or not all(isinstance(item, str) and item for item in expressions):
            raise jsondata.DataFileError(
                f"access matrix {RUN_BRANCH_PATTERNS_KEY!r}/{actor.value!r} is {expressions!r}; "
                "expected a list of regular expressions"
            )
        for expression in expressions:
            try:
                re.compile(expression, re.ASCII)
            except re.error as error:
                raise jsondata.DataFileError(
                    f"access matrix {RUN_BRANCH_PATTERNS_KEY!r}/{actor.value!r} holds {expression!r}, "
                    f"which is not a regular expression ({error})"
                ) from error


def protected_branches(data: Mapping[str, Any], actor: Actor) -> tuple[str, ...]:
    """The branches ``actor`` is kept off like the default branch (``develop`` for an autonomous run)."""
    protected = data.get(PROTECTED_BRANCHES_KEY)
    names = protected.get(actor.value) if isinstance(protected, Mapping) else None
    if not isinstance(names, list):
        raise jsondata.DataFileError(
            f"access matrix has no entry for actor {actor.value!r} in {PROTECTED_BRANCHES_KEY!r}"
        )
    return tuple(names)


def is_protected_branch(names: Sequence[str], branch: str) -> bool:
    """Whether ``branch`` is one of ``names``: an exact name, or a prefix for a name ending in ``*``."""
    return any(branch.startswith(name[:-1]) if name.endswith("*") else branch == name for name in names)


def is_own_branch(data: Mapping[str, Any], actor: Actor, branch: str, run_branch: str | None) -> bool:
    """Whether ``branch`` is one ``actor`` may write: a developer's every branch, an autonomous run's own.

    An autonomous run's own branch is the ``run_branch`` the launcher named (``AKMON_RUN_BRANCH``), exactly;
    with none named, a branch the actor's ``run_branch_patterns`` match (``agent/C203-...``). A developer has
    no run branch, so the question does not narrow what a developer may write.
    """
    if actor is not Actor.AUTONOMOUS:
        return True
    if run_branch is not None:
        return branch == run_branch
    patterns = data[RUN_BRANCH_PATTERNS_KEY].get(actor.value, [])
    return any(re.search(pattern, branch, re.ASCII) for pattern in patterns)


def outcome(data: Mapping[str, Any], actor: Actor, action_class: str) -> str:
    """What ``actor`` may do for ``action_class``: ``allow``, ``ask`` or ``deny``.

    A row, a class or a value the matrix lacks raises :class:`jsondata.DataFileError`: the matrix is a
    dependency of the guard, and a hole in it must not read as permission.
    """
    row = data.get(actor.value)
    if not isinstance(row, Mapping) or action_class not in row:
        raise jsondata.DataFileError(f"access matrix has no entry for actor {actor.value!r}, action {action_class!r}")
    value = row[action_class]
    if value not in OUTCOMES:
        raise jsondata.DataFileError(
            f"access matrix entry {actor.value!r}/{action_class!r} is {value!r}; the outcomes are {', '.join(OUTCOMES)}"
        )
    return value
