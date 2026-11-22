"""The text akmon's SessionStart hooks put in the model's context, as the always-loaded counter reads it.

ADR 0012 F18 counts what reaches the model before it asks for anything; owner decision
D-A49-HOOKCOUNT (a) (task A49) adds the hooks that ``bin/sync.json`` wires on SessionStart —
``session-start-agent``, ``model-routing`` and ``learning-reminder`` — so that moving a rule from an
imported file into a hook is not a false saving. This module is the counter's side: it builds each
hook's text *in-process, from the functions the hook itself calls*, and returns it as
:class:`common.always_loaded.Member` rows — for the attended head, the unattended head (the other layer
on the same hooks) and a delegate (the SubagentStart text alone).

A **ceiling**, not the text of one session: every optional line is present (the roster, the delegation,
work-style and memory lines, the stale-guardrail notice naming every materialized file, the learning
reminder as if due, the routing status with its warnings). Nothing is read from the host, a transcript
or a developer's local config, and nothing is written — the learning reminder is built without touching
the record, so counting the hook never counts a session. The one text per hook lives with the hook's
own logic (``hook_core.session_start_context``, ``routing.session_start_ceiling``,
``learning.reminder_ceiling``); this module only chooses the inputs.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TREE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TREE_ROOT))
sys.path.insert(0, str(_TREE_ROOT / "tools" / "model_routing"))

import routing  # noqa: E402
from hook_core import (  # noqa: E402
    akmon_runtime_root,
    session_layer,
    session_start_context,
    stale_guardrail_ceiling,
    subagent_start_result,
)

from common import learning  # noqa: E402
from common.always_loaded import Member  # noqa: E402
from common.project_root import aitna_root_name  # noqa: E402


def _routing_text(root: Path) -> str | None:
    """The model-routing hook's ceiling for ``root``, or ``None`` where the hook is silent or cannot be read.

    Silent without a registry. A registry that does not parse, or lacks what the ceiling reads, is
    ``verify``'s ``routing.*`` finding to report: the counter says nothing for the hook rather than
    take the whole verification down with it.
    """
    akmon = akmon_runtime_root(root)
    if not routing.registry_path(akmon).is_file():
        return None
    try:
        try:
            registry = routing.load_registry(akmon, root)
        except routing.OverlayError:
            # The hook names a broken overlay in one line and routes nothing; the counter measures the shipped one.
            registry = routing.load_registry(akmon)
        command = routing.tool_command_ceiling(f"{aitna_root_name(root)}/akmon", "model_routing/init")
        return routing.session_start_ceiling(registry, command)
    except (ValueError, LookupError, TypeError, AttributeError):
        return None


def session_start_members(root: Path, *, attended: bool = True) -> tuple[Member, ...]:
    """The SessionStart hook texts for the project at ``root``, one member per hook that has something to say.

    ``attended`` picks the layer the session-start hook appends: the head layer (the default, the largest
    audience the cap is checked against) or the unattended one.
    """
    data = learning.read_data()
    layer = session_layer(root, attended=attended)
    texts = {
        "session-start-agent": session_start_context(root, None, stale_guardrail_ceiling(root), layer),
        "model-routing": _routing_text(root),
        "learning-reminder": learning.reminder_ceiling(learning.read_thresholds(root, data), data),
    }
    return tuple(Member(f"hook: {name}", text) for name, text in texts.items() if text is not None)


def subagent_start_members(root: Path) -> tuple[Member, ...]:
    """The SubagentStart hook text a delegate carries for the project at ``root``: its one member."""
    text = subagent_start_result(root).additional_context
    return (Member("hook: subagent-start", text),) if text is not None else ()
