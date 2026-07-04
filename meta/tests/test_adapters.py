"""Tests for the vendor adapters' tool normalization and the shared project-root lookup.

The neutral core (`hook_core`) never names a vendor's tools; each adapter maps its own
edit-tool name(s) to `hook_core.EDIT_TOOL`. `find_project_root` lives in the core and is reused.
"""

from __future__ import annotations

import json

import claude_adapter
import codex_adapter
import hook_core


def test_claude_normalize_maps_edit_tools():
    for name in ("Edit", "Write", "MultiEdit"):
        assert claude_adapter.normalize_tool(name) == hook_core.EDIT_TOOL
    # Non-edit tools pass through unchanged (so the core ignores them).
    assert claude_adapter.normalize_tool("Read") == "Read"
    assert claude_adapter.normalize_tool("Bash") == "Bash"


def test_codex_normalize_maps_apply_patch():
    assert codex_adapter.normalize_tool("apply_patch") == hook_core.EDIT_TOOL
    assert codex_adapter.normalize_tool("shell") == "shell"


def test_codex_session_start_payload_fields_are_read():
    payload = {
        "session_id": "s1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/tmp/project",
        "hook_event_name": "SessionStart",
        "model": "gpt",
        "source": "startup",
    }
    assert codex_adapter.cwd(payload) == "/tmp/project"
    assert codex_adapter.session_id(payload) == "s1"


def test_codex_print_result_serializes_hook_specific_output(capsys):
    result = hook_core.HookResult(event_name="SessionStart", additional_context="[keystone] context")
    codex_adapter.print_result(result)

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "[keystone] context",
        }
    }


def test_normalized_vendor_tools_drive_the_core(tmp_path, monkeypatch):
    # End-to-end: a vendor edit-tool name, once normalized, fires the core guard.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    claude = claude_adapter.normalize_tool("Write")
    codex = codex_adapter.normalize_tool("apply_patch")
    assert hook_core.role_on_code_result(claude, "src/x.py", "s-claude") is not None
    assert hook_core.role_on_code_result(codex, "src/y.py", "s-codex") is not None


def test_find_project_root_in_core(tmp_path):
    # A marked project root is found by walking up from a nested dir.
    proj = tmp_path / "proj"
    (proj / "_forge" / "keystone").mkdir(parents=True)
    (proj / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    nested = proj / "src" / "pkg"
    nested.mkdir(parents=True)
    assert hook_core.find_project_root(nested) == proj.resolve()


def test_find_project_root_falls_back_to_start(tmp_path):
    # No marker anywhere upward → returns the resolved start.
    bare = tmp_path / "bare"
    bare.mkdir()
    assert hook_core.find_project_root(bare) == bare.resolve()


def test_claude_print_result_with_system_message(capsys):
    result = hook_core.HookResult(
        event_name="PreToolUse",
        system_message="[keystone] → k-explorer (small): find X",
    )
    claude_adapter.print_result(result)

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "hookSpecificOutput": {"hookEventName": "PreToolUse"},
        "systemMessage": "[keystone] → k-explorer (small): find X",
    }
    # systemMessage is top-level, not inside hookSpecificOutput
    assert "systemMessage" in payload
    assert "systemMessage" not in payload["hookSpecificOutput"]


def test_claude_print_result_without_system_message(capsys):
    result = hook_core.HookResult(event_name="SessionStart")
    claude_adapter.print_result(result)

    payload = json.loads(capsys.readouterr().out)
    assert "systemMessage" not in payload
    assert payload == {"hookSpecificOutput": {"hookEventName": "SessionStart"}}


# --------------------------------------------------------------------------------------
# delegation-log hook format_system_message (C21)
# --------------------------------------------------------------------------------------


def test_delegation_log_system_message_with_model_and_description():
    # Import the helper function from delegation-log.py
    import importlib.util
    from pathlib import Path

    keystone_root = Path(hook_core.__file__).parent.parent
    spec = importlib.util.spec_from_file_location(
        "delegation_log", keystone_root / "hooks" / "delegation-log.py"
    )
    deleg_log = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deleg_log)

    # Line format: timestamp\tsubagent\tmodel\tdescription
    line = "2026-07-04T10:00:00+0000\tk-explorer\tsmall\tfind X in codebase"
    msg = deleg_log._format_system_message(line)
    assert msg == "[keystone] → k-explorer (small): find X in codebase"


def test_delegation_log_system_message_without_model():
    import importlib.util
    from pathlib import Path

    keystone_root = Path(hook_core.__file__).parent.parent
    spec = importlib.util.spec_from_file_location(
        "delegation_log", keystone_root / "hooks" / "delegation-log.py"
    )
    deleg_log = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deleg_log)

    line = "2026-07-04T10:00:00+0000\tk-mechanic\t-\treformat code"
    msg = deleg_log._format_system_message(line)
    assert msg == "[keystone] → k-mechanic: reformat code"


def test_delegation_log_system_message_without_description():
    import importlib.util
    from pathlib import Path

    keystone_root = Path(hook_core.__file__).parent.parent
    spec = importlib.util.spec_from_file_location(
        "delegation_log", keystone_root / "hooks" / "delegation-log.py"
    )
    deleg_log = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deleg_log)

    line = "2026-07-04T10:00:00+0000\tk-reasoner\treasoner\t"
    msg = deleg_log._format_system_message(line)
    assert msg == "[keystone] → k-reasoner (reasoner)"
