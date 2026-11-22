"""The audience a session's starting context is delivered to, and the layer each one reads (A49).

akmon's rules reach three readers. The floor — the guardrail, the code rules, the profiles — goes to
everyone through the entry file. Two layers go through hooks instead, so each reaches only its audience
(``docs/design/context-audiences.md``):

- the **head layer** (``rules/collaboration.md`` and ``rules/templates.md``): the session an owner
  attends — how it talks with the owner;
- the **unattended layer** (``rules/unattended.md``): a delegate, and a session no owner attends — how
  it finishes without stopping to ask.

The SessionStart hook delivers one of the two to a session, on every ``source`` (compaction drops text
given only at startup, M246); the SubagentStart hook delivers the unattended layer to a delegate.
:func:`is_attended` decides which one a session gets (D-A49-SELECTOR (a)); :func:`layer_text` reads it.

Nothing here reads the process environment: a hook entry point passes ``os.environ`` once.
The JavaScript twin is ``js/common/audience.mjs``; the file lists are ``common/audience.json``'s,
shared by both.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from common import access_matrix, jsondata, learning


def read_data() -> dict[str, Any]:
    """The layer file lists beside this module: ``attended_files``, ``unattended_files``, ``separator``."""
    return jsondata.read(Path(__file__).parent / "audience.json")


def is_attended(environ: Mapping[str, str]) -> bool:
    """Whether the session is one an owner attends, so it gets the head layer (D-A49-SELECTOR (a)).

    All three must hold: the actor is ``developer`` (an absent or unknown value reads as developer);
    the harness has not said the session is unattended (``CLAUDE_CODE_SESSION_ATTENDED`` is not ``0``,
    M199); and the run is not a second opinion (``AKMON_SECOND_OPINION`` unset). Any other session gets
    the unattended layer.
    """
    data = learning.read_data()
    return (
        access_matrix.actor_from_environment(environ) is access_matrix.Actor.DEVELOPER
        and learning.is_attended(environ, data)
        and not learning.is_second_opinion(environ, data)
    )


def layer_files(data: Mapping[str, Any], *, attended: bool) -> tuple[str, ...]:
    """The standard files of the layer an ``attended`` session gets, as tree-relative paths."""
    return tuple(data["attended_files"] if attended else data["unattended_files"])


def layer_text(tree_root: Path, *, attended: bool, data: Mapping[str, Any] | None = None) -> str:
    """The text of the layer an ``attended`` session gets, read from the standard tree at ``tree_root``.

    ``tree_root`` is the tree the hook executes from: the mount, the wheel's embedded tree, or akmon's own
    checkout — each ships the rule files beside its hooks, so the layer does not depend on a
    materialized copy. Raises ``OSError`` when a file of the layer is missing from the tree.
    """
    data = data if data is not None else read_data()
    files = layer_files(data, attended=attended)
    texts = [(tree_root / relative).read_text(encoding="utf-8").rstrip("\n") for relative in files]
    return data["separator"].join(texts)
