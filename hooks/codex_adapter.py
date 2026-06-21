"""Codex adapter helpers for neutral keystone hook results.

Codex command-hook payload details may evolve, so this adapter accepts several common
field spellings and degrades to plain-text reminders. Hard allow/deny decisions should
only be wired after the exact Codex output contract is verified for the target version.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from hook_core import EDIT_TOOL, HookResult

# Codex's file-editing tool name(s) → keystone's neutral edit-tool kind.
EDIT_TOOLS = frozenset({"apply_patch"})

_PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)


def normalize_tool(name: str) -> str:
    """Map a Codex tool name to the neutral kind hook_core expects; pass others through."""
    return EDIT_TOOL if name in EDIT_TOOLS else name


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return value if isinstance(value, dict) else {"payload": value}


def tool_name(payload: dict[str, Any]) -> str:
    for key in ("tool_name", "toolName", "tool", "name"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            return value["name"]
    return ""


def session_id(payload: dict[str, Any]) -> str:
    keys = ("session_id", "sessionId", "conversation_id", "conversationId", "thread_id", "threadId")
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "nosession"


def _tool_input(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("tool_input", "toolInput", "input", "args", "arguments", "params"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def command(payload: dict[str, Any]) -> str:
    tool_input = _tool_input(payload)
    for key in ("command", "cmd", "script"):
        value = tool_input.get(key) or payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def file_paths(payload: dict[str, Any]) -> list[str]:
    tool_input = _tool_input(payload)
    paths: list[str] = []
    for source in (tool_input, payload):
        for key in ("file_path", "filePath", "path", "target", "filename"):
            value = source.get(key)
            if isinstance(value, str) and value:
                paths.append(value)
        for key in ("file_paths", "filePaths", "paths", "files"):
            value = source.get(key)
            if isinstance(value, list):
                paths.extend(item for item in value if isinstance(item, str) and item)
    patch = tool_input.get("patch") or payload.get("patch") or payload.get("raw")
    if isinstance(patch, str):
        paths.extend(match.strip() for match in _PATCH_PATH_RE.findall(patch))
    # Stable de-duplication.
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            unique.append(path)
    return unique


def print_result(result: HookResult | None) -> None:
    if result is None:
        return
    parts = [part for part in (result.additional_context, result.permission_reason) if part]
    if parts:
        print("\n".join(parts))
