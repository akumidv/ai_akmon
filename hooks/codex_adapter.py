"""Codex adapter helpers for neutral akmon hook results.

Codex command-hook payload details may evolve, so this adapter accepts several common
field spellings and degrades to plain-text reminders. Hard decisions are wired only after
the exact route, payload, and runtime behavior are live-verified for the target version.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from hook_core import EDIT_TOOL, SHELL_TOOL, HookResult

# Codex's file-editing tool name(s) → akmon's neutral edit-tool kind.
EDIT_TOOLS = frozenset({"apply_patch"})
# The shell route. `Bash` is the `tool_name` codex 0.146.0 puts in the payload for a shell
# call — measured, not assumed: its model-facing names (`exec_command`, `shell`) appear
# neither as payload tool names nor as working matchers (C49).
SHELL_TOOLS = frozenset({"Bash"})

_PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)

# A deliberately narrow recognition rule for the one shell effect we can classify exactly:
# an apply_patch invocation in *command position*, with the patch body carried inline.
# Command position is the start of the command string, the position after a `;`/`&&`/`||`/`|`
# separator, the start of a subshell `(`/group `{ `, or the start of a `sh -c` / `bash -lc`
# wrapper's script. Anchoring on the string start alone was too literal: one token in front of
# the call (`cd sub && apply_patch …`) put the measured route back out of sight, and a bypass
# is spelled, not typed — which is why the separator set has to cover the ordinary ways a
# shell opens a command, `$(apply_patch …)` and `{ apply_patch …; }` included. Deliberately
# *not* after a bare newline — a heredoc body whose first line reads `apply_patch` is quoted
# data, not a call. The width is safe to spend here because the narrowing is carried by
# adjacency, not by this set: `_has_apply_patch_invocation` additionally requires the match to
# sit on the first line, outside shell quoting, and to open the patch heredoc directly.
# Everything else on Bash stays the generic shell kind and gets the route-level diagnostic; a
# false positive costs one advisory reminder, a false negative costs the route its only
# classification.
_APPLY_PATCH_INVOCATION_RE = re.compile(
    r"""(?:^|[;&|(]|\{(?=\s)|-\w*c\s*["'])\s*(?:command\s+)?(?:\S*/)?apply_patch(?=[\s<]|$)"""
)
_PATCH_HEREDOC_RE = re.compile(
    r"[ \t]*<<-?[ \t]*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)[ \t]*\r?\n"
)
_PATCH_ENVELOPE_RE = re.compile(r"^\*\*\* Begin Patch\s*$", re.MULTILINE)
_PATCH_END_RE = re.compile(r"^\*\*\* End Patch\s*$", re.MULTILINE)


def _outside_shell_quotes(text: str, position: int) -> bool:
    """Whether ``position`` starts outside simple shell single/double quoting."""
    quote = ""
    escaped = False
    for char in text[:position]:
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
        elif char in ("'", '"'):
            quote = char
    return not quote


def _has_apply_patch_invocation(command_text: str) -> bool:
    """Find an invocation that directly opens the inline patch heredoc."""
    first_newline = command_text.find("\n")
    line_end = len(command_text) if first_newline < 0 else first_newline
    for match in _APPLY_PATCH_INVOCATION_RE.finditer(command_text):
        if match.start() >= line_end or not _outside_shell_quotes(command_text, match.start()):
            continue
        opener = _PATCH_HEREDOC_RE.match(command_text, match.end())
        if opener is not None and _PATCH_ENVELOPE_RE.match(command_text, opener.end()) is not None:
            return True
    return False


def is_apply_patch_command(command_text: str) -> bool:
    """Whether Bash carries the one effect akmon can path-classify conservatively.

    Require a command-position ``apply_patch`` invocation and a complete inline envelope;
    patch-looking text that is merely printed, searched, stored, or truncated stays shell.
    """
    return bool(
        _has_apply_patch_invocation(command_text)
        and _PATCH_ENVELOPE_RE.search(command_text)
        and _PATCH_END_RE.search(command_text)
        and _PATCH_PATH_RE.search(command_text)
    )


def normalize_tool(name: str) -> str:
    """Map a Codex tool name to the neutral kind hook_core expects; pass others through."""
    if name in EDIT_TOOLS:
        return EDIT_TOOL
    return SHELL_TOOL if name in SHELL_TOOLS else name


def tool_kind(payload: dict[str, Any]) -> str:
    """The neutral kind this call *acts as*, which is not always the route it took.

    A shell call whose command carries a patch body is an edit. Codex's model demonstrated
    exactly this in the N2 deny probe: a denied ``apply_patch`` was re-issued through the
    shell in the same turn, unprompted, and went through. Classifying by route would let one
    effect be seen or unseen depending on its spelling, so the payload decides (C49).
    """
    name = normalize_tool(tool_name(payload) or "apply_patch")
    if name == SHELL_TOOL and is_apply_patch_command(command(payload)):
        return EDIT_TOOL
    return name


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


def tool_use_id(payload: dict[str, Any]) -> str:
    """Return the per-event identity Codex supplies, or an empty string if absent."""
    for key in ("tool_use_id", "toolUseId", "call_id", "callId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


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


_UNMEASURED_STRING_KEYS = ("file_path", "filePath", "path", "target", "filename")
_UNMEASURED_LIST_KEYS = ("file_paths", "filePaths", "paths", "files")


def _paths_by_source(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    """``(unmeasured, measured)`` — paths read from guessed keys, and from the patch body.

    Kept apart so a caller can say *how* it learned a path. No measured Codex version sends
    any of the guessed keys; they are tolerated in case a future shape uses one, but a path
    that only they produced is a claim no measurement backs (D2-18 a). Ranking them below the
    patch body is not enough on its own — a speculative key that matches something *other*
    than an edited file would classify it silently, which is worse than the empty list C48
    started from, so the wrapper reports the provenance instead of trusting it.
    """
    unmeasured: list[str] = []
    for source in (_tool_input(payload), payload):
        for key in _UNMEASURED_STRING_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value:
                unmeasured.append(value)
        for key in _UNMEASURED_LIST_KEYS:
            value = source.get(key)
            if isinstance(value, list):
                unmeasured.extend(item for item in value if isinstance(item, str) and item)
    patch = command(payload) or payload.get("raw")
    measured = [m.strip() for m in _PATCH_PATH_RE.findall(patch)] if isinstance(patch, str) else []
    return unmeasured, measured


def unmeasured_path_source(payload: dict[str, Any]) -> bool:
    """True when the payload named files, but only through keys no measured Codex sends."""
    unmeasured, measured = _paths_by_source(payload)
    return bool(unmeasured) and not measured


def file_paths(payload: dict[str, Any]) -> list[str]:
    """Every file path the payload names, including those parsed out of a patch body.

    The patch body is read through :func:`command` because on ``apply_patch`` it *is* the
    command: codex 0.146.0 sends the whole patch as ``tool_input.command`` (captured live).
    This used to enumerate its own key guesses — ``tool_input.patch``, ``payload.patch`` —
    neither of which any measured Codex version sends, so nothing was ever extracted and
    all three wired advisory hooks were silently inert (C48). Those invented keys are gone
    rather than kept "just in case": a key list that looks thorough while missing the only
    real one is what hid the defect, and an unrecognized future shape now produces the
    no-path defect signal in ``codex-hook.py`` instead of silence. ``raw`` stays — it is
    this module's own malformed-JSON fallback (see :func:`load_payload`), not a guess.
    """
    unmeasured, measured = _paths_by_source(payload)
    paths = unmeasured + measured
    # Stable de-duplication.
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            unique.append(path)
    return unique


def payload_shape(payload: dict[str, Any]) -> str:
    """The payload's key names, for a diagnostic that must not print the payload itself.

    Used when a matcher fired but no path could be read (C48): the useful evidence is
    *which keys arrived*, and the values may carry file contents from a patch body.
    """
    top = ", ".join(sorted(str(key) for key in payload)) or "<none>"
    inner = ", ".join(sorted(str(key) for key in _tool_input(payload))) or "<none>"
    return f"tool_input keys: {inner}; payload keys: {top}"


def cwd(payload: dict[str, Any]) -> str:
    for key in ("cwd", "working_directory", "workingDirectory", "workdir"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def print_result(result: HookResult | None) -> None:
    if result is None:
        return
    output: dict[str, str] = {"hookEventName": result.event_name}
    if result.additional_context is not None:
        output["additionalContext"] = result.additional_context
    if result.permission_decision is not None:
        output["permissionDecision"] = result.permission_decision
    if result.permission_reason is not None:
        output["permissionDecisionReason"] = result.permission_reason
    top_level: dict[str, Any] = {"hookSpecificOutput": output}
    if result.system_message is not None:
        # Codex hooks have no documented user-facing channel; pass silently for now.
        pass
    print(json.dumps(top_level))
