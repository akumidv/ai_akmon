#!/usr/bin/env python3
"""Claude wrapper for akmon model routing — orchestrator detection + status line.

Runs on **SessionStart** and **UserPromptSubmit**. Both read the session transcript
(``transcript_path`` in the payload) to detect the model the main chain is actually
running on, map it to an alias, and — when it differs from the recorded orchestrator (a
session launched on another model, or a mid-session ``/model`` switch) — recompute the
binding and regenerate the ``k_*`` subagent definitions so delegates follow the live
model. The orchestrator itself is never overridden: it is the owner's explicit choice,
only *detected* here.

- **SessionStart:** fresh config → status line (binding + self-check, plus the corridor
  warning when the orchestrator sits below the floor or on the reserved top rung).
  Missing/stale config → the init instruction (the one-time setup that records
  ``available`` + the second-opinion opt-in).
- **UserPromptSubmit:** silent unless the orchestrator changed — then a one-line notice
  naming the recomputed binding (plus the corridor warning when the switch left the
  healthy range) — or the context fill reached a new pressure level (design §12).

Owner-addressed output — the init instruction, the corridor warning, the rebind notice —
goes out on **two channels** (requirement 11): ``additionalContext`` (the model acts on it)
and ``systemMessage`` (the owner sees it in the host UI). The context-pressure reminder is
the owner's alone — ``systemMessage`` only: the model has nothing to do with it. The
steady-state status line stays context-only.

Logic lives in ``tools/model_routing/routing.py``; this entrypoint only adapts the payload.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from claude_adapter import load_payload, print_result
from hook_core import (
    HookResult,
    aitna_root_name,
    akmon_runtime_root,
    d2_status_counts,
    d2_status_line,
    d2_tracking_active,
    find_project_root,
    runtime_root_display,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "model_routing"))

import routing


def _settings_model(project_root: Path) -> str | None:
    for name in ("settings.local.json", "settings.json"):
        path = project_root / ".claude" / name
        if not path.is_file():
            continue
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        model = settings.get("model") if isinstance(settings, dict) else None
        if isinstance(model, str) and model:
            return model
    return None


def _load_config(root: Path) -> dict:
    config_path = root / routing.LOCAL_CONFIG_REL
    if not config_path.is_file():
        return {}
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def model_routing_result(root: Path, payload: dict) -> HookResult | None:
    akmon = akmon_runtime_root(root)
    if not routing.registry_path(akmon).is_file():
        # Silence is the right answer for a pin that predates model routing: such a tree has no
        # routing tools at all, and there is nothing to report. It is the wrong answer for a
        # registry that has gone *missing* from a tree that does carry them — a broken carrier
        # takes the status line and the delegation log out of every session, at exit 0 with an
        # empty stderr. So the two states are separated rather than swallowed together (C77).
        if (akmon / "tools" / "model_routing").is_dir():
            print(
                f"akmon model-routing hook: {akmon}/tools/model_routing exists but registry.json "
                "is missing — model routing is silent for this session",
                file=sys.stderr,
            )
        return None

    registry = routing.load_registry(akmon, root)
    config = _load_config(root)
    event = payload.get("hook_event_name") or "SessionStart"

    aitna = aitna_root_name()
    # Recovery instructions must name the tree this project actually has, in a spelling that
    # keeps working: the project-relative mount when one exists, `$(akmon path)` in mode
    # `package`, where the tree is inside the installed wheel and its literal path carries the
    # venv's Python version (C77). Naming the mount unconditionally used to hand a package-mode
    # session a path that is not there.
    runtime_rel = runtime_root_display(root)
    # An overlay `briefs` key matching no agent makes every regeneration lossy, so the
    # rebind is refused rather than run — and the reason is stated instead of swallowed (C50).
    brief_warn = routing.brief_warning(registry, aitna)

    # Detect the model the main chain actually runs on (authoritative over settings) and
    # rebind the subagents when it moved. Needs an existing config for the `available`
    # ladder + opt-ins; first-time setup stays explicit (the init instruction below).
    detected = routing.detect_orchestrator(payload.get("transcript_path"), config.get("available"))
    switched = bool(detected and config and detected != config.get("orchestrator"))
    rebound = switched and brief_warn is None
    if rebound:
        routing.rebind_to(root, registry, config, detected)
        config = _load_config(root)  # reload the freshly-written binding

    pressure = routing.context_pressure_notice(
        registry, payload.get("transcript_path"), payload.get("session_id")
    )
    suppressed = routing.suppressed_rebind_warning(
        brief_warn if switched else None,
        detected,
        payload.get("session_id"),
    )

    if event != "SessionStart":
        # Per-turn: silent unless a switch or a new context-pressure level just landed — zero
        # token cost otherwise. A rebind is owner-addressed → dual-channel (requirement 11);
        # the pressure reminder goes to the owner only. A suppressed rebind speaks up here too:
        # the delegates stay pinned to the old model until the overlay is fixed, which the owner
        # has to know at the moment it happens.
        dual = (routing.rebind_notice(config, registry) if rebound else []) + suppressed
        if not dual and not pressure:
            return None
        return HookResult(
            event_name=event,
            additional_context="\n".join(dual) or None,
            system_message="\n".join(dual + pressure),
        )

    # SessionStart: the transcript (when it named a model) is ground truth, so suppress the
    # weaker settings-model staleness signal once we have detected + bound to it.
    settings_model = None if detected else _settings_model(root)
    reason = routing.staleness(config, registry, settings_model)
    overlay = [brief_warn] if brief_warn else []
    if reason is not None:
        lines = routing.init_instruction(reason, runtime_rel) + overlay
        return HookResult(
            event_name="SessionStart",
            additional_context="\n".join(lines),
            system_message="\n".join([lines[0], *overlay, *pressure]),
        )
    lines = routing.status_lines(config, registry, runtime_rel) + overlay
    # Owner-addressed subset: the corridor warning, the fact of a rebind and — for the owner
    # alone — the context-pressure reminder at either level (its info line carries ℹ, not ⚠);
    # the steady-state status line itself stays context-only so the UI is quiet when healthy.
    owner = [line for line in lines if line.startswith("⚠")] + pressure
    if rebound:
        owner.insert(0, routing.rebind_notice(config, registry)[0])
    # D2 ledger counter (phase 3 of C11): appended to the status block when tracking is in use;
    # owner-addressed while either pending decisions or approved landings remain open.
    if d2_tracking_active(root):
        d2_pending, d2_approved = d2_status_counts(root)
        d2_line = d2_status_line(d2_pending, d2_approved)
        lines.append(d2_line)
        if d2_pending > 0 or d2_approved > 0:
            owner.append(d2_line)
    return HookResult(
        event_name="SessionStart",
        additional_context="\n".join(lines),
        system_message="\n".join(owner) if owner else None,
    )


def _project_root(payload: dict) -> Path:
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return find_project_root(Path(cwd))


def main() -> int:
    # Never block a turn: on any failure, log to stderr and exit cleanly.
    try:
        payload = load_payload()
        print_result(model_routing_result(_project_root(payload), payload))
    except Exception as exc:
        print(f"akmon model-routing hook: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
