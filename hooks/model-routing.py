#!/usr/bin/env python3
"""Claude SessionStart wrapper for the keystone model-routing status line.

Fresh local config → inject one status line (binding + self-check, plus a
weak-orchestrator warning when the session model ranks below the registry floor).
Missing/stale config → inject the init instruction (run ``tools/model_routing/init.py``,
then confirm the binding and the second-opinion opt-in with the owner). Logic lives in
``tools/model_routing/routing.py``; this entrypoint only adapts Claude Code's payload.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from claude_adapter import load_payload, print_result
from hook_core import HookResult, find_project_root, forge_root_name, keystone_root

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


def model_routing_result(root: Path) -> HookResult | None:
    keystone = keystone_root(root)
    if not routing.registry_path(keystone).is_file():
        return None  # keystone without model routing (older pin) — stay silent

    registry = routing.load_registry(keystone, root)
    config_path = root / routing.LOCAL_CONFIG_REL
    config: dict = {}
    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            config = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            config = {}

    reason = routing.staleness(config, registry, _settings_model(root))
    forge = forge_root_name()
    if reason is None:
        lines = routing.status_lines(config, registry, forge)
    else:
        lines = routing.init_instruction(reason, forge)
    return HookResult(event_name="SessionStart", additional_context="\n".join(lines))


def _project_root(payload: dict) -> Path:
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return find_project_root(Path(cwd))


def main() -> int:
    # Never block session start: on any failure, log to stderr and exit cleanly.
    try:
        print_result(model_routing_result(_project_root(load_payload())))
    except Exception as exc:
        print(f"keystone model-routing hook: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
