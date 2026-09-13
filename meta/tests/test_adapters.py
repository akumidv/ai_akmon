"""Tests for the vendor adapters' tool normalization and the shared project-root lookup.

The neutral core (`hook_core`) never names a vendor's tools; each adapter maps its own
edit-tool name(s) to `hook_core.EDIT_TOOL`. `find_project_root` lives in the core and is reused.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import claude_adapter
import codex_adapter
import hook_core
import pytest
import routing
import sync

from common.materialization import materialized_markdown


def _codex_hook():
    path = Path(hook_core.__file__).parent / "codex-hook.py"
    spec = importlib.util.spec_from_file_location("codex_hook", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _claude_hook(filename: str):
    path = Path(hook_core.__file__).parent / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py").replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claude_normalize_maps_edit_tools():
    for name in ("Edit", "Write", "MultiEdit"):
        assert claude_adapter.normalize_tool(name) == hook_core.EDIT_TOOL
    # Non-edit, non-read tools pass through unchanged (so the core ignores them).
    assert claude_adapter.normalize_tool("Bash") == "Bash"


def test_claude_normalize_maps_read_tools():
    for name in ("Read", "Grep", "Glob"):
        assert claude_adapter.normalize_tool(name) == hook_core.READ_TOOL


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
    result = hook_core.HookResult(event_name="SessionStart", additional_context="[akmon] context")
    codex_adapter.print_result(result)

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "[akmon] context",
        }
    }


# --------------------------------------------------------------------------------------
# C48: the payload codex 0.146.0 actually sends
# --------------------------------------------------------------------------------------

# Captured live from codex-cli 0.146.0 with an instrumented fixture hook (N2 stage-0 probe H),
# not an invented shape. The patch body arrives as `tool_input.command`; there is no `patch`
# key anywhere — which is what left every wired advisory hook inert since the day it was wired.
_CODEX_0_146_APPLY_PATCH = {
    "hook_event_name": "PreToolUse",
    "tool_name": "apply_patch",
    "tool_input": {"command": "*** Begin Patch\n*** Add File: note.txt\n+hello\n*** End Patch"},
    "session_id": "01996f0f-0000-7000-8000-000000000000",
    "cwd": "/home/ai/workspace/alphavar",
    "model": "gpt-5.6-terra",
    "tool_use_id": "call_0",
}


def test_captured_codex_payload_names_the_file_it_patches():
    # The whole of C48 in one assertion: this returned [] until the patch body was read
    # from `command()`, and an empty path list makes every path-keyed advisory a no-op.
    assert codex_adapter.file_paths(_CODEX_0_146_APPLY_PATCH) == ["note.txt"]


def test_patch_body_paths_cover_add_update_and_delete():
    body = (
        "*** Begin Patch\n"
        "*** Add File: docs/new.md\n+a\n"
        "*** Update File: src/x.py\n@@\n-a\n+b\n"
        "*** Delete File: old.txt\n"
        "*** End Patch"
    )
    payload = {"tool_name": "apply_patch", "tool_input": {"command": body}}
    assert codex_adapter.file_paths(payload) == ["docs/new.md", "src/x.py", "old.txt"]


def _codex_project(tmp_path: Path, *, sensitive: str | None = None) -> Path:
    root = tmp_path / "proj"
    (root / "_aitna" / "akmon").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    if sensitive is not None:
        config = root / "_aitna" / ".akmon.toml"
        config.write_text(f"[d2_ledger]\nsensitive_paths = {sensitive}\n", encoding="utf-8")
    return root


def _patch_payload(root: Path, *files: str) -> dict:
    """The captured payload shape with a chosen set of patched files."""
    body = "*** Begin Patch\n" + "".join(f"*** Add File: {name}\n+x\n" for name in files) + "*** End Patch"
    return dict(_CODEX_0_146_APPLY_PATCH, tool_input={"command": body}, cwd=str(root), session_id="sess-c48")


def _run_codex_hook(monkeypatch, hook: str, payload: dict) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert _codex_hook().main([hook]) == 0


def test_analysis_guard_fires_on_the_captured_codex_payload(monkeypatch, tmp_path, capsys):
    # argv → stdin → adapter → core → stdout, on the real payload: the path C48 broke.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    _run_codex_hook(monkeypatch, "analysis-guard", _patch_payload(root, "_aitna/design/probe.md"))

    emitted = json.loads(capsys.readouterr().out)
    context = emitted["hookSpecificOutput"]["additionalContext"]
    assert context == hook_core.analysis_before_mutation_message()


def test_role_on_code_fires_on_the_captured_codex_payload(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    _run_codex_hook(monkeypatch, "role-on-code", _patch_payload(root, "src/x.py"))

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["hookSpecificOutput"]["additionalContext"] == hook_core.role_on_code_message()


def test_d2_ledger_reminder_fires_on_the_captured_codex_payload(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path, sensitive='["src/**"]')
    _run_codex_hook(monkeypatch, "d2-ledger-reminder", _patch_payload(root, "src/x.py"))

    emitted = json.loads(capsys.readouterr().out)
    assert "D2" in emitted["hookSpecificOutput"]["additionalContext"]


# --------------------------------------------------------------------------------------
# C67: the rename form — `*** Move to:` names a path the `File:` lines never carry
# --------------------------------------------------------------------------------------

# The rename literal measured on codex-cli 0.149.1 (N1/F4 §"All four patch forms"): the source
# stays on its `*** Update File:` line and the destination arrives on `*** Move to:`. Written
# as the probe observed it, not invented — D2-18(a) is the row that refused to guess this shape.
_RENAME_BODY = "*** Begin Patch\n*** Update File: notes/plan.md\n*** Move to: src/plan.md\n@@\n-a\n+b\n*** End Patch"


def test_patch_body_paths_include_the_rename_destination():
    # The whole of C67 in one assertion: this returned ["notes/plan.md"] alone, so a rename was
    # classified under where the file came from and never under where it landed.
    payload = {"tool_name": "apply_patch", "tool_input": {"command": _RENAME_BODY}}
    assert codex_adapter.file_paths(payload) == ["notes/plan.md", "src/plan.md"]


def test_the_rename_destination_is_a_measured_path_not_a_guessed_one():
    # `*** Move to:` is observed on 0.149.1, so the destination has to land in the *measured*
    # half of the provenance split, not be appended alongside the nine tolerated key guesses:
    # D2-18(a) keys the stderr provenance line on that boundary, and a measured path reported
    # as a guess is the same kind of false statement as a guess reported as measured.
    payload = {"tool_name": "apply_patch", "tool_input": {"command": _RENAME_BODY}}
    unmeasured, measured = codex_adapter._paths_by_source(payload)
    assert unmeasured == []
    assert measured == ["notes/plan.md", "src/plan.md"]
    assert codex_adapter.unmeasured_path_source(payload) is False


def test_a_file_moved_into_a_sensitive_path_reaches_the_d2_advisory(monkeypatch, tmp_path, capsys):
    # The case the gap cost: neither endpoint is unusual on its own, but the *destination* is
    # D2-sensitive and the source is not, so reading the `File:` lines alone skipped the
    # reminder in silence — a hook with nothing to say and a hook that cannot see the path
    # print the same nothing (C48's shape, one form over).
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path, sensitive='["src/**"]')
    payload = dict(
        _CODEX_0_146_APPLY_PATCH,
        tool_input={"command": _RENAME_BODY},
        cwd=str(root),
        session_id="sess-c67-move",
    )
    _run_codex_hook(monkeypatch, "d2-ledger-reminder", payload)

    captured = capsys.readouterr()
    assert "D2" in json.loads(captured.out)["hookSpecificOutput"]["additionalContext"]
    assert captured.err == ""


def test_a_rename_carried_by_the_shell_is_still_an_edit(monkeypatch, tmp_path):
    # The C49 route exception recognizes a patch by envelope plus *some* extracted path, and a
    # rename is a patch like any other: the shell spelling must not lose the classification.
    command = f"apply_patch <<'PATCH'\n{_RENAME_BODY}\nPATCH"
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    assert codex_adapter.tool_kind(payload) == hook_core.EDIT_TOOL
    assert codex_adapter.file_paths(payload) == ["notes/plan.md", "src/plan.md"]


def test_a_patch_whose_paths_cannot_be_read_is_reported_as_a_defect(monkeypatch, tmp_path, capsys):
    # The matcher fired on an edit call and nothing could be extracted — that is akmon
    # reading the wrong key, not a quiet turn, and it must stop being indistinguishable
    # from one. Owner/dev channel only: stderr, no stdout, no block (C48).
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = dict(_CODEX_0_146_APPLY_PATCH, tool_input={"diff": "some future key"}, cwd=str(root))
    _run_codex_hook(monkeypatch, "analysis-guard", payload)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no file path could be read" in captured.err
    assert "apply_patch" in captured.err
    assert "diff" in captured.err  # names the keys that did arrive, never their values


def test_a_path_from_an_unmeasured_key_still_advises_but_says_so(monkeypatch, tmp_path, capsys):
    # Owner choice iii at D2-18(a): the guessed path keys stay — a probable target beats no
    # target — but a path only they produced is reported, because a guess that *matches*
    # classifies silently and is worse than the empty list C48 started from.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = dict(
        _CODEX_0_146_APPLY_PATCH,
        tool_input={"file_path": "_aitna/design/probe.md"},
        cwd=str(root),
    )
    _run_codex_hook(monkeypatch, "analysis-guard", payload)

    captured = capsys.readouterr()
    emitted = json.loads(captured.out)
    assert emitted["hookSpecificOutput"]["additionalContext"] == hook_core.analysis_before_mutation_message()
    assert "unmeasured payload key" in captured.err
    assert "file_path" in captured.err  # key names only, never their values
    assert "probe.md" not in captured.err


def test_the_measured_patch_body_is_not_reported_as_unmeasured(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    _run_codex_hook(monkeypatch, "analysis-guard", _patch_payload(root, "_aitna/design/probe.md"))

    captured = capsys.readouterr()
    assert json.loads(captured.out)["hookSpecificOutput"]["additionalContext"]
    assert captured.err == ""


def test_unmeasured_path_source_is_false_when_the_patch_body_also_names_files():
    payload = dict(
        _CODEX_0_146_APPLY_PATCH,
        tool_input={
            "command": "*** Begin Patch\n*** Add File: note.txt\n+hello\n*** End Patch",
            "file_path": "guessed.txt",
        },
    )
    assert codex_adapter.unmeasured_path_source(payload) is False
    assert codex_adapter.file_paths(payload) == ["guessed.txt", "note.txt"]


def test_one_bad_edit_event_emits_one_defect_signal_across_handlers(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = dict(
        _CODEX_0_146_APPLY_PATCH,
        tool_input={"diff": "some future key"},
        cwd=str(root),
        session_id="sess-c36-unreadable",
        tool_use_id="call-bad-1",
    )

    for hook in ("role-on-code", "analysis-guard", "d2-ledger-reminder"):
        _run_codex_hook(monkeypatch, hook, payload)

    assert capsys.readouterr().err.count("no file path could be read") == 1


def test_a_later_bad_edit_event_is_not_hidden_by_the_first(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    base = dict(
        _CODEX_0_146_APPLY_PATCH,
        tool_input={"diff": "some future key"},
        cwd=str(root),
        session_id="sess-c36-repeat",
    )

    for event_id in ("call-bad-1", "call-bad-2"):
        _run_codex_hook(monkeypatch, "analysis-guard", dict(base, tool_use_id=event_id))

    assert capsys.readouterr().err.count("no file path could be read") == 2


def test_bad_edit_without_event_identity_repeats_fail_visible(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {"diff": "some future key"},
        "cwd": str(root),
    }

    for hook in ("role-on-code", "analysis-guard", "d2-ledger-reminder"):
        _run_codex_hook(monkeypatch, hook, payload)

    assert capsys.readouterr().err.count("no file path could be read") == 3


def test_the_defect_signal_stays_off_the_shell_route(monkeypatch, tmp_path, capsys):
    # A shell call carries a command, not a patch, so extracting no path is normal there.
    # The C48 malformed-edit alarm stays off; C49 emits its distinct route-level diagnostic.
    root = _codex_project(tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": str(root)}
    _run_codex_hook(monkeypatch, "analysis-guard", payload)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no file path could be read" not in captured.err
    assert "may mutate the filesystem" in captured.err


# --------------------------------------------------------------------------------------
# C49: the shell route — named by the matcher, reported rather than classified
# --------------------------------------------------------------------------------------


def test_codex_normalize_maps_the_measured_shell_tool_name():
    # `Bash` is what codex 0.146.0 puts in the payload for a shell call. Its model-facing
    # names are not payload tool names and are not mapped on a guess.
    assert codex_adapter.normalize_tool("Bash") == hook_core.SHELL_TOOL
    assert codex_adapter.normalize_tool("exec_command") == "exec_command"


def test_a_patch_carried_by_the_shell_is_an_edit_not_a_shell_call():
    # The measured bypass: a denied `apply_patch` re-issued through the shell in the same
    # turn, unprompted, and it went through. One effect must not be seen or unseen by its
    # spelling, so the payload — not the route name — decides the kind.
    heredoc = "apply_patch <<'PATCH'\n*** Begin Patch\n*** Add File: src/x.py\n+x\n*** End Patch\nPATCH"
    payload = {"tool_name": "Bash", "tool_input": {"command": heredoc}}
    assert codex_adapter.is_apply_patch_command(heredoc)
    assert codex_adapter.tool_kind(payload) == hook_core.EDIT_TOOL
    assert codex_adapter.file_paths(payload) == ["src/x.py"]
    assert codex_adapter.tool_kind({"tool_name": "Bash", "tool_input": {"command": "ls"}}) == hook_core.SHELL_TOOL
    assert codex_adapter.tool_kind(_CODEX_0_146_APPLY_PATCH) == hook_core.EDIT_TOOL


_PATCH_BODY = "*** Begin Patch\n*** Add File: src/x.py\n+x\n*** End Patch"


@pytest.mark.parametrize(
    "command_template",
    (
        "{call}",
        "cd sub && {call}",
        "set -e; {call}",
        'bash -lc "{call}"',
        'sh -c "{call}"',
        "command {call}",
        "({call}\n)",
        "out=$({call}\n)",
        "{{ {call}\n}}",
    ),
)
@pytest.mark.parametrize("heredoc_spacing", (" ", ""), ids=("spaced-heredoc", "adjacent-heredoc"))
def test_an_apply_patch_invocation_is_recognized_in_any_command_position(command_template, heredoc_spacing):
    # A bypass is spelled, not typed. Recognition anchored on the *string* start let one
    # token in front of the call put the measured route back out of sight, so what counts
    # is command position: string start, after a separator, at the head of a subshell or
    # group, or inside a `-c` wrapper.
    call = f"apply_patch{heredoc_spacing}<<'PATCH'\n{_PATCH_BODY}\nPATCH"
    command_text = command_template.format(call=call)
    payload = {"tool_name": "Bash", "tool_input": {"command": command_text}}
    assert codex_adapter.is_apply_patch_command(command_text)
    assert codex_adapter.tool_kind(payload) == hook_core.EDIT_TOOL


def test_apply_patch_name_prefix_is_not_an_invocation():
    command_text = f"apply_patch_backup <<'PATCH'\n{_PATCH_BODY}\nPATCH"
    payload = {"tool_name": "Bash", "tool_input": {"command": command_text}}
    assert not codex_adapter.is_apply_patch_command(command_text)
    assert codex_adapter.tool_kind(payload) == hook_core.SHELL_TOOL


def test_a_brace_without_a_separating_space_is_a_word_not_a_group():
    # `{ cmd; }` is a group only when the brace is followed by whitespace; `{apply_patch` is
    # one word naming another command. Widening command position to `{` must not widen it to
    # every token that merely starts with the character.
    command_text = f"{{apply_patch <<'PATCH'\n{_PATCH_BODY}\nPATCH"
    payload = {"tool_name": "Bash", "tool_input": {"command": command_text}}
    assert not codex_adapter.is_apply_patch_command(command_text)
    assert codex_adapter.tool_kind(payload) == hook_core.SHELL_TOOL


def _bash_patch_payload(root: Path, path: str, session_id: str, prefix: str = "") -> dict:
    heredoc = f"{prefix}apply_patch <<'PATCH'\n*** Begin Patch\n*** Add File: {path}\n+x\n*** End Patch\nPATCH"
    return {
        "tool_name": "Bash",
        "tool_input": {"command": heredoc},
        "session_id": session_id,
        "cwd": str(root),
    }


def test_role_advisory_fires_on_a_patch_the_shell_carried(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    _run_codex_hook(monkeypatch, "role-on-code", _bash_patch_payload(root, "src/x.py", "sess-c49-role"))

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["hookSpecificOutput"]["additionalContext"] == hook_core.role_on_code_message()


def test_role_advisory_fires_on_a_prefixed_patch_the_shell_carried(monkeypatch, tmp_path, capsys):
    # End to end for the same point: the advisory must not depend on the call being the
    # first token of the command string.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = _bash_patch_payload(root, "src/x.py", "sess-c49-prefixed", prefix="cd . && ")
    _run_codex_hook(monkeypatch, "role-on-code", payload)

    captured = capsys.readouterr()
    assert json.loads(captured.out)["hookSpecificOutput"]["additionalContext"] == hook_core.role_on_code_message()
    assert "may mutate the filesystem" not in captured.err


def test_analysis_advisory_fires_on_a_patch_the_shell_carried(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = _bash_patch_payload(root, "_aitna/design/plan.md", "sess-c49-analysis")
    _run_codex_hook(monkeypatch, "analysis-guard", payload)

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["hookSpecificOutput"]["additionalContext"] == hook_core.analysis_before_mutation_message()


def test_analysis_advisory_fires_on_an_adjacent_heredoc(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = _bash_patch_payload(root, "_aitna/design/plan.md", "sess-c49-adjacent")
    payload["tool_input"]["command"] = payload["tool_input"]["command"].replace("apply_patch <<", "apply_patch<<", 1)

    _run_codex_hook(monkeypatch, "analysis-guard", payload)

    captured = capsys.readouterr()
    assert json.loads(captured.out)["hookSpecificOutput"]["additionalContext"] == (
        hook_core.analysis_before_mutation_message()
    )
    assert "may mutate the filesystem" not in captured.err


def test_d2_advisory_fires_on_a_patch_the_shell_carried(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path, sensitive='["src/**"]')
    payload = _bash_patch_payload(root, "src/x.py", "sess-c49-d2")
    _run_codex_hook(monkeypatch, "d2-ledger-reminder", payload)

    emitted = json.loads(capsys.readouterr().out)
    assert "D2" in emitted["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize(
    "command_text",
    (
        ("cat > saved.patch <<'PATCH'\n*** Begin Patch\n*** Add File: src/x.py\n+x\n*** End Patch\nPATCH"),
        "grep -n '*** Add File:' saved.patch",
        "cat saved.patch",
        "apply_patch <<'PATCH'\n*** Begin Patch\n*** Add File: src/x.py\n+x\nPATCH",
        ("cat <<'TEXT'\napply_patch\n*** Begin Patch\n*** Add File: src/x.py\n+x\n*** End Patch\nTEXT"),
        ("cat <<'TEXT'\nignored; apply_patch\n*** Begin Patch\n*** Add File: src/x.py\n+x\n*** End Patch\nTEXT"),
        (
            "printf '%s' 'ignored; apply_patch' <<'TEXT'\n*** Begin Patch\n"
            "*** Add File: src/x.py\n+x\n*** End Patch\nTEXT"
        ),
        ("apply_patch < saved.patch; cat <<'TEXT'\n*** Begin Patch\n*** Add File: src/x.py\n+x\n*** End Patch\nTEXT"),
    ),
)
def test_patch_looking_text_without_apply_patch_invocation_stays_shell(command_text):
    payload = {"tool_name": "Bash", "tool_input": {"command": command_text}}
    assert not codex_adapter.is_apply_patch_command(command_text)
    assert codex_adapter.tool_kind(payload) == hook_core.SHELL_TOOL


def test_every_nonpatch_shell_route_gets_one_generic_diagnostic_across_handlers(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "session_id": "sess-c49", "cwd": str(root)}

    for hook in ("role-on-code", "analysis-guard", "d2-ledger-reminder"):
        _run_codex_hook(monkeypatch, hook, payload)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("may mutate the filesystem") == 1
    assert "hook-process stderr diagnostic only" in captured.err


def test_shell_diagnostic_without_session_id_repeats_fail_visible(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": str(root)}

    _run_codex_hook(monkeypatch, "analysis-guard", payload)
    _run_codex_hook(monkeypatch, "analysis-guard", payload)

    captured = capsys.readouterr()
    assert captured.err.count("may mutate the filesystem") == 2


def test_shell_diagnostic_marker_is_atomic_across_handlers(monkeypatch, tmp_path):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    with ThreadPoolExecutor(max_workers=12) as pool:
        decisions = list(pool.map(lambda _: hook_core.claim_diagnostic_marker("shell-route", "sess-race"), range(24)))
    assert decisions.count(True) == 1


def test_shell_diagnostic_marker_failure_repeats_fail_visible(monkeypatch):
    def fail_open(*args, **kwargs):
        raise PermissionError("read-only tempdir")

    monkeypatch.setattr(hook_core.os, "open", fail_open)
    assert hook_core.claim_diagnostic_marker("shell-route", "sess-io-failure")
    assert hook_core.claim_diagnostic_marker("shell-route", "sess-io-failure")


def test_the_shell_route_diagnostic_is_reported_on_claude_too(monkeypatch, tmp_path, capsys):
    # D2-19(e), owner decision (ii): the blind spot is not Codex's. Claude's advisories sit on
    # the edit tools, so a Bash write is invisible to them there as well — and until now it was
    # also unreported. The already-wired commit guard carries the statement; no second process.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python3 - <<'EOF'\nopen('x.py', 'w').write('x')\nEOF"},
        "session_id": "sess-claude-c49",
    }

    for _ in range(2):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        assert _claude_hook("git-commit-guard.py").main() == 0

    captured = capsys.readouterr()
    assert captured.err.count("may mutate the filesystem") == 1
    assert captured.out == ""  # the guard itself has nothing to say about this command


def test_the_claude_shell_diagnostic_leaves_the_guard_decision_intact(monkeypatch, tmp_path, capsys):
    # The diagnostic is stderr-only and additive: a denied commit is still denied on stdout.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'wip'"},
        "session_id": "sess-claude-guard",
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert _claude_hook("git-commit-guard.py").main() == 0

    captured = capsys.readouterr()
    assert "may mutate the filesystem" in captured.err
    assert json.loads(captured.out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_non_shell_claude_call_gets_no_shell_route_diagnostic(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    payload = {"tool_name": "Write", "tool_input": {"file_path": "src/x.py"}, "session_id": "sess-claude-edit"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert _claude_hook("git-commit-guard.py").main() == 0

    assert capsys.readouterr().err == ""


def test_both_vendors_emit_one_shell_route_wording(monkeypatch, tmp_path, capsys):
    # One implementation, one message: two copies of a diagnostic are two things that can
    # drift into disagreeing about what akmon can see.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    _run_codex_hook(
        monkeypatch,
        "analysis-guard",
        {"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "sess-codex-w", "cwd": str(root)},
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "sess-claude-w"})),
    )
    assert _claude_hook("git-commit-guard.py").main() == 0

    lines = [line for line in capsys.readouterr().err.splitlines() if "may mutate the filesystem" in line]
    assert len(lines) == 2 and lines[0] == lines[1] == hook_core.UNCLASSIFIED_SHELL_ROUTE_NOTICE


def test_normalized_vendor_tools_drive_the_core(tmp_path, monkeypatch):
    # End-to-end: a vendor edit-tool name, once normalized, fires the core guard.
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    claude = claude_adapter.normalize_tool("Write")
    codex = codex_adapter.normalize_tool("apply_patch")
    assert hook_core.role_on_code_result(claude, "src/x.py", "s-claude") is not None
    assert hook_core.role_on_code_result(codex, "src/y.py", "s-codex") is not None


def test_both_adapters_take_the_project_root_from_the_payload(tmp_path):
    # C47: the path predicates normalize against a project root, so both wrappers have to
    # derive it from the payload's `cwd` rather than from the hook process's own cwd —
    # otherwise the same edit classifies differently depending on where the hook started.
    proj = tmp_path / "proj"
    (proj / "_aitna" / "akmon").mkdir(parents=True)
    (proj / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    nested = proj / "src" / "pkg"
    nested.mkdir(parents=True)

    payload = {"cwd": str(nested)}
    assert claude_adapter.project_root(payload) == proj.resolve()
    assert _codex_hook()._payload_root(payload) == proj.resolve()


def test_codex_analysis_wrapper_classifies_relative_g2_path(monkeypatch, tmp_path, capsys):
    """Exercise C47 below the adapter's still-open real-payload question (C48).

    ``patch`` deliberately marks this as a synthetic patch-shaped fixture, while the explicit
    ``file_path`` carries the relative target into the wrapper. The real Codex patch body uses
    ``tool_input.command``; this test must not be read as coverage of that C48 contract.
    """
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {
            "file_path": "_aitna/design/probe-n2-hookfire.md",
            "patch": "*** Begin Patch\n*** Add File: _aitna/design/probe-n2-hookfire.md\n+x\n*** End Patch",
        },
        "session_id": "sess-c47-wrapper",
        "cwd": str(root / "src"),
    }
    (root / "src").mkdir()

    _codex_hook()._advisory(payload, hook_core.analysis_write_result)

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["hookSpecificOutput"]["additionalContext"] == hook_core.analysis_before_mutation_message()


@pytest.mark.parametrize("relative", (True, False), ids=("relative", "absolute"))
def test_claude_analysis_entrypoint_agrees_on_path_forms(monkeypatch, tmp_path, capsys, relative):
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = _codex_project(tmp_path)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    target = "_aitna/design/probe.md" if relative else str(root / "_aitna" / "design" / "probe.md")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": target},
        "session_id": f"sess-claude-c47-{relative}",
        "cwd": str(nested),
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert _claude_hook("analysis-guard.py").main() == 0

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["hookSpecificOutput"]["additionalContext"] == hook_core.analysis_before_mutation_message()


def test_claude_role_entrypoint_strips_docs_ancestor_using_payload_root(monkeypatch, tmp_path, capsys):
    """Without wrapper root threading, the ancestor ``docs`` makes this code look like docs."""
    monkeypatch.setattr(hook_core.tempfile, "gettempdir", lambda: str(tmp_path))
    root = tmp_path / "docs" / "proj"
    (root / "_aitna" / "akmon").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(root / "src" / "x.py")},
        "session_id": "sess-claude-root-threading",
        "cwd": str(nested),
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert _claude_hook("role-on-code.py").main() == 0

    emitted = json.loads(capsys.readouterr().out)
    assert emitted["hookSpecificOutput"]["additionalContext"] == hook_core.role_on_code_message()


def test_claude_project_root_without_cwd_falls_back_to_discovery(tmp_path, monkeypatch):
    # A payload without `cwd` (or with an empty one) must not crash the hook; it degrades to
    # the same upward walk the core has always done.
    monkeypatch.chdir(tmp_path)
    assert claude_adapter.project_root({}) == tmp_path.resolve()
    assert claude_adapter.project_root({"cwd": ""}) == tmp_path.resolve()


def test_find_project_root_in_core(tmp_path):
    # A marked project root is found by walking up from a nested dir.
    proj = tmp_path / "proj"
    (proj / "_aitna" / "akmon").mkdir(parents=True)
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
        system_message="[akmon] → k_explorer (small): find X",
    )
    claude_adapter.print_result(result)

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "hookSpecificOutput": {"hookEventName": "PreToolUse"},
        "systemMessage": "[akmon] → k_explorer (small): find X",
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

    akmon_root = Path(hook_core.__file__).parent.parent
    spec = importlib.util.spec_from_file_location("delegation_log", akmon_root / "hooks" / "delegation-log.py")
    deleg_log = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deleg_log)

    # Line format: timestamp\tsession_id\tsubagent\tmodel\tzone\tdescription
    line = "2026-07-04T10:00:00+0000\tsess-1\tk_explorer\tsmall\tauth\tfind X in codebase"
    msg = deleg_log._format_system_message(line)
    assert msg == "[akmon] → k_explorer (small) [auth]: find X in codebase"


def test_delegation_log_system_message_without_model():
    import importlib.util
    from pathlib import Path

    akmon_root = Path(hook_core.__file__).parent.parent
    spec = importlib.util.spec_from_file_location("delegation_log", akmon_root / "hooks" / "delegation-log.py")
    deleg_log = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deleg_log)

    line = "2026-07-04T10:00:00+0000\tsess-1\tk_mechanic\t-\t-\treformat code"
    msg = deleg_log._format_system_message(line)
    assert msg == "[akmon] → k_mechanic: reformat code"


def test_delegation_log_system_message_without_description():
    import importlib.util
    from pathlib import Path

    akmon_root = Path(hook_core.__file__).parent.parent
    spec = importlib.util.spec_from_file_location("delegation_log", akmon_root / "hooks" / "delegation-log.py")
    deleg_log = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deleg_log)

    line = "2026-07-04T10:00:00+0000\tsess-1\tk_reasoner\treasoner\t-\t"
    msg = deleg_log._format_system_message(line)
    assert msg == "[akmon] → k_reasoner (reasoner)"


def _delegation_log_payload(tmp_path, transcript, subagent_type):
    return {
        "tool_name": "Task",
        "tool_input": {"subagent_type": subagent_type, "description": "do the work"},
        "session_id": "sess-c20",
        "cwd": str(tmp_path),
        "transcript_path": str(transcript),
    }


def _configure_delegation_log_hook(deleg_log, monkeypatch, tmp_path, payload, config=None):
    """Wire the hook onto ``tmp_path``. With ``config``, the local routing config is written
    to disk and read by the hook itself, so the config -> bound model -> console line chain
    is exercised end to end instead of being stubbed away."""
    akmon_root = Path(hook_core.__file__).parent.parent
    registry = deleg_log.routing.load_registry(akmon_root, tmp_path)
    base_registry = {**registry, "cross_cutting_kinds": []}
    monkeypatch.setattr(deleg_log, "load_payload", lambda: payload)
    monkeypatch.setattr(deleg_log, "find_project_root", lambda _path: tmp_path)
    monkeypatch.setattr(deleg_log, "akmon_runtime_root", lambda _root: akmon_root)
    if config is None:
        monkeypatch.setattr(deleg_log, "_load_config", lambda _root: {})
    else:
        path = tmp_path / deleg_log.routing.LOCAL_CONFIG_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(deleg_log.routing, "load_registry", lambda *_args: base_registry)


def test_delegation_log_role_advisory_is_system_message_only(tmp_path, monkeypatch, capsys):
    deleg_log = _claude_hook("delegation-log.py")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"content": "🧭 agent: review — audit"}}) + "\n",
        encoding="utf-8",
    )
    payload = _delegation_log_payload(tmp_path, transcript, "k_mechanic")
    _configure_delegation_log_hook(deleg_log, monkeypatch, tmp_path, payload)

    assert deleg_log.main() == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["hookSpecificOutput"] == {"hookEventName": "PreToolUse"}
    assert "permissionDecision" not in emitted["hookSpecificOutput"]
    assert "[akmon] → k_mechanic: do the work" in emitted["systemMessage"]
    assert "role/task-kind: k_mechanic" in emitted["systemMessage"]


def test_delegation_log_allowed_agent_stays_silent(tmp_path, monkeypatch, capsys):
    deleg_log = _claude_hook("delegation-log.py")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"content": "🧭 agent: review — audit"}}) + "\n",
        encoding="utf-8",
    )
    payload = _delegation_log_payload(tmp_path, transcript, "k_explorer")
    _configure_delegation_log_hook(deleg_log, monkeypatch, tmp_path, payload)

    assert deleg_log.main() == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["systemMessage"] == "[akmon] → k_explorer: do the work"
    assert "permissionDecision" not in emitted["hookSpecificOutput"]


def _bound_config(available):
    """A local routing config as ``routing.local_config`` writes it, bound or semantic."""
    akmon_root = Path(hook_core.__file__).parent.parent
    sys.path.insert(0, str(akmon_root / "tools" / "model_routing"))
    import routing

    registry = routing.load_registry(akmon_root)
    binding = routing.compute_binding(registry, "opus", available, "anthropic")
    return routing.local_config(registry=registry, binding=binding, second_opinion=False, available=available)


def test_delegation_log_names_the_bound_model(tmp_path, monkeypatch, capsys):
    """The hook reads the config itself: console line and record name the pinned model."""
    deleg_log = _claude_hook("delegation-log.py")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"content": "🧭 agent: review — audit"}}) + "\n",
        encoding="utf-8",
    )
    payload = _delegation_log_payload(tmp_path, transcript, "k_explorer")
    config = _bound_config(["haiku", "sonnet", "opus", "fable"])
    _configure_delegation_log_hook(deleg_log, monkeypatch, tmp_path, payload, config=config)

    assert deleg_log.main() == 0
    emitted = json.loads(capsys.readouterr().out)
    worker = config["binding"]["worker"]
    assert emitted["systemMessage"] == f"[akmon] → k_explorer ({worker}): do the work"
    log_line = (tmp_path / deleg_log.routing.DELEGATION_LOG_REL).read_text(encoding="utf-8").strip()
    assert log_line.split("\t")[3] == worker


def test_delegation_log_reports_no_model_without_a_bound_ladder(tmp_path, monkeypatch, capsys):
    """Semantic fallback has no pin to report: the label must not be shown as a model.

    Without a recorded ``available`` ladder the generated agent files carry no ``model:``
    line, so the host inherits the session's model. Naming the tier label (``worker``,
    ``strongest``) here would assert a pin that does not exist, in the console and in the
    record the coverage map and the stats digest read.
    """
    deleg_log = _claude_hook("delegation-log.py")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"content": "🧭 agent: review — audit"}}) + "\n",
        encoding="utf-8",
    )
    payload = _delegation_log_payload(tmp_path, transcript, "k_explorer")
    config = _bound_config(None)
    assert config["binding"]["worker"] == "worker"  # the label the old guard let through
    _configure_delegation_log_hook(deleg_log, monkeypatch, tmp_path, payload, config=config)

    assert deleg_log.main() == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["systemMessage"] == "[akmon] → k_explorer: do the work"
    log_line = (tmp_path / deleg_log.routing.DELEGATION_LOG_REL).read_text(encoding="utf-8").strip()
    assert log_line.split("\t")[3] == "-"


@pytest.mark.parametrize("available", ["haiku", 42])
def test_delegation_log_rejects_malformed_available_without_losing_record(available, tmp_path, monkeypatch, capsys):
    """Malformed local config yields no pin and cannot suppress the delegation record."""
    deleg_log = _claude_hook("delegation-log.py")
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"content": "🧭 agent: review — audit"}}) + "\n",
        encoding="utf-8",
    )
    payload = _delegation_log_payload(tmp_path, transcript, "k_explorer")
    config = {"binding": {"worker": "haiku"}, "available": available}
    _configure_delegation_log_hook(deleg_log, monkeypatch, tmp_path, payload, config=config)

    assert deleg_log.main() == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["systemMessage"] == "[akmon] → k_explorer: do the work"
    log_line = (tmp_path / deleg_log.routing.DELEGATION_LOG_REL).read_text(encoding="utf-8").strip()
    assert log_line.split("\t")[3] == "-"


def test_delegation_log_ordinary_exception_returns_zero(tmp_path, monkeypatch, capsys):
    deleg_log = _claude_hook("delegation-log.py")
    payload = _delegation_log_payload(tmp_path, tmp_path / "missing.jsonl", "k_mechanic")
    _configure_delegation_log_hook(deleg_log, monkeypatch, tmp_path, payload)

    def fail(*_args, **_kwargs):
        raise RuntimeError("seeded C20 failure")

    monkeypatch.setattr(deleg_log.routing, "delegation_log_line", fail)
    assert deleg_log.main() == 0
    captured = capsys.readouterr()
    assert captured.err.splitlines() == ["akmon delegation-log hook: RuntimeError"]
    notice = hook_core.hook_failure_notice("delegation-log", RuntimeError())
    assert json.loads(captured.out) == {"systemMessage": notice}
    assert "seeded C20 failure" not in captured.out + captured.err


# --------------------------------------------------------------------------------------
# the crash guard on every spawned entry point (C87/D2-45, ADR 0013 F3 as amended)
# --------------------------------------------------------------------------------------

_SEEDED_SECRET = "SEEDED-SECRET /home/owner/private.key"


def _seeded_crash():
    raise RuntimeError(_SEEDED_SECRET)


def _wired_entry_points(tmp_path) -> tuple[list[str], list[str]]:
    """The spawned entry points the generated wiring names: Claude files, then Codex routes.

    Read from the wiring rather than listed, so an entry added there without the guard fails
    the tests below instead of shipping a crash nobody sees.
    """
    root = tmp_path / "wiring"
    (root / "_aitna" / "akmon").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

    def commands(hooks: dict) -> list[str]:
        return [hook["command"] for groups in hooks.values() for group in groups for hook in group["hooks"]]

    claude = json.loads(sync._claude_settings(root).content)["hooks"]
    codex = sync._codex_hooks(root)["hooks"]
    files = sorted({re.search(r"hooks/([\w-]+\.py)", command).group(1) for command in commands(claude)})
    routes = sorted({command.rsplit(" ", 1)[1] for command in commands(codex)})
    return files, routes


def test_every_wired_claude_entry_reports_a_crash_to_the_owner_and_exits_zero(tmp_path, monkeypatch, capsys):
    # One stderr line with the hook and the class, the owner's notice as the one stdout document
    # (M69: shown as a notice, never passed to the model), exit 0 (M70: an exit 1 is silent).
    files, _ = _wired_entry_points(tmp_path)
    assert len(files) == 8
    for filename in files:
        hook = _claude_hook(filename)
        monkeypatch.setattr(hook, "load_payload", _seeded_crash)
        name = filename.removesuffix(".py")
        assert hook.main() == 0, filename
        captured = capsys.readouterr()
        assert captured.err.splitlines() == [f"akmon {name} hook: RuntimeError"], filename
        notice = hook_core.hook_failure_notice(name, RuntimeError())
        assert json.loads(captured.out) == {"systemMessage": notice}, filename
        assert "SEEDED-SECRET" not in captured.out + captured.err, filename


def test_every_wired_codex_route_reports_a_crash_as_failed(tmp_path, monkeypatch, capsys):
    # Exit 1 with nothing on stdout: Codex shows the hook `Failed` and the action goes ahead
    # (M68, M71); an exit 0 would read `Completed` and hide the crash.
    _, routes = _wired_entry_points(tmp_path)
    assert routes == ["analysis-guard", "d2-ledger-reminder", "role-on-code", "session-start"]
    codex_hook = _codex_hook()
    monkeypatch.setattr(codex_hook, "load_payload", _seeded_crash)
    for route in routes:
        assert codex_hook.main([route]) == 1, route
        captured = capsys.readouterr()
        assert captured.err.splitlines() == [f"akmon codex-hook {route} hook: RuntimeError"], route
        assert captured.out == "", route
        assert "SEEDED-SECRET" not in captured.err, route


def test_codex_entry_reports_a_bad_route_in_one_line(capsys):
    # argparse would print a usage block and raise SystemExit, which passes an `except Exception`
    # guard (ADR 0013): two lines, and a crash the guard never sees.
    assert _codex_hook().main(["no-such-route"]) == 1
    captured = capsys.readouterr()
    assert captured.err.splitlines() == ["akmon codex-hook hook: UsageError"]
    assert captured.out == ""


def test_claude_guard_writes_one_document_when_rendering_fails(capsys):
    # The single-write property: a result that cannot be rendered is a crash before the write,
    # so stdout carries the owner's notice alone, never a prefix followed by a second document.
    def unrenderable():
        return hook_core.HookResult(event_name="PreToolUse", additional_context=object())

    assert claude_adapter.run_guarded("probe-hook", unrenderable) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"systemMessage": hook_core.hook_failure_notice("probe-hook", TypeError())}
    assert captured.err.splitlines() == ["akmon probe-hook hook: TypeError"]


def test_hook_failure_texts_name_the_hook_and_the_class_never_the_message():
    exc = ValueError("/home/owner/.secret token=abc")
    assert hook_core.hook_failure_diagnostic("role-on-code", exc) == "akmon role-on-code hook: ValueError"
    notice = hook_core.hook_failure_notice("role-on-code", exc)
    assert "role-on-code" in notice and "ValueError" in notice
    assert "`akmon verify`" in notice and "_aitna/akmon/bin/verify.py" in notice
    assert "secret" not in notice and "token" not in notice


def test_find_project_root_in_package_mode_from_nested_directory(tmp_path):
    project = tmp_path / "project"
    (project / "_aitna").mkdir(parents=True)
    (project / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    (project / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)

    assert hook_core.find_project_root(nested) == project.resolve()


# --------------------------------------------------------------------------------------
# akmon_runtime_root — the carrier answers, and no mount state changes the answer (C77)
# --------------------------------------------------------------------------------------


def _runtime_root_case(tmp_path, *, record: str | None, mount: bool):
    """A project in one of the mount states, with its materialization always present."""
    project = tmp_path / "project"
    (project / "_aitna" / ".akmon").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    if record is not None:
        (project / "_aitna" / ".akmon.toml").write_text(record, encoding="utf-8")
    if mount:
        (project / "_aitna" / "akmon").mkdir()
    return project


@pytest.mark.parametrize(
    ("name", "record", "mount"),
    [
        # The states kept verbatim from the rule this replaced (C69/D2-26): the two the old
        # directory check got wrong, the ones its fix had to preserve, and the unparseable
        # record. The point of the table is now that **none of them changes the answer** —
        # the hook runs from a tree, and that tree is the answer.
        ("package record beside a stale mount", 'mount = "package"\n', True),
        ("package record written with a comment", 'mount = "package"  # materialized\n', True),
        ("package record, no mount", 'mount = "package"\n', False),
        ("submodule record with its mount", 'mount = "submodule"\n', True),
        ("no record, mount present", None, True),
        ("no record, no mount", None, False),
        ("unparseable record beside a mount", "mount = \x00broken\n", True),
    ],
)
def test_the_runtime_root_is_the_executing_tree_in_every_mount_state(tmp_path, name, record, mount):
    project = _runtime_root_case(tmp_path, record=record, mount=mount)
    assert hook_core.akmon_runtime_root(project) == hook_core._TREE_ROOT, name


def test_a_stale_mount_cannot_shadow_the_executing_tree(tmp_path):
    """What the record-veto rule defended against, held by construction rather than by a read.

    ``sync`` still reads the record and reports package mode; the hook answers with its own
    carrier. The leftover ``_aitna/akmon`` from a prior mode is not a candidate at all, because
    a tree that is not executing cannot be the tree that is executing.
    """
    project = _runtime_root_case(tmp_path, record='mount = "package"\n', mount=True)
    assert sync.is_package_mode(project) is True
    assert hook_core.akmon_runtime_root(project) == hook_core._TREE_ROOT
    assert hook_core.akmon_runtime_root(project) != project / "_aitna" / "akmon"


def test_the_hook_reaches_the_routing_registry_in_package_mode(tmp_path):
    """The regression this change is one mistake away from: a package-mode session with no
    model routing at all.

    ``model_routing_result`` returns ``None`` when the registry is not under the runtime root —
    silently, at exit 0 — so pointing the runtime root at the materialization (which carries no
    registry any more) would take the status line and the delegation log out of every session
    with nothing to show for it. Asserted through ``routing.registry_path`` on the hook's own
    answer, which is the exact expression the guard evaluates.
    """
    project = _runtime_root_case(tmp_path, record='mount = "package"\n', mount=False)
    runtime = hook_core.akmon_runtime_root(project)
    assert routing.registry_path(runtime).is_file()
    assert routing.load_registry(runtime, project)


def test_session_start_contains_capability_neutral_delegation_rule(tmp_path):
    project = tmp_path / "project"
    (project / "_aitna" / "agents" / "review").mkdir(parents=True)
    (project / "_aitna" / "agents" / "review" / "README.md").write_text("# review\n", encoding="utf-8")

    result = hook_core.session_start_result(project)

    assert result is not None
    assert result.additional_context is not None
    assert "Delegation is the default for non-atomic work" in result.additional_context
    assert "harness exposes no subagents" in result.additional_context


def test_stale_guardrail_notice_reaches_both_vendor_wirings(monkeypatch, tmp_path, capsys):
    """The notice lives in ``session_start_result``, the SessionStart logic both vendors already
    call, so it needed no new hook and no wiring change — which matters: a regenerated
    ``.codex/hooks.json`` invalidates the host's approval of every changed group.

    Claude carries it on both channels; Codex has no documented owner-facing channel, so it
    arrives as context and the model relays it. Asserted through the serializers rather than the
    core, because "both wirings" is the claim.
    """
    tree = tmp_path / "installed"
    (tree / "guardrails").mkdir(parents=True)
    (tree / "guardrails" / "_common.md").write_text("# Common\n\nnew rule\n", encoding="utf-8")
    monkeypatch.setattr(hook_core, "akmon_runtime_root", lambda project_root: tree)

    root = _codex_project(tmp_path)
    dest = root / "_aitna" / ".akmon" / "guardrails"
    dest.mkdir(parents=True)
    (dest / "_common.md").write_text(materialized_markdown("# Common\n\nold rule\n"), encoding="utf-8")

    result = hook_core.session_start_result(root)
    assert result is not None

    claude_adapter.print_result(result)
    claude_payload = json.loads(capsys.readouterr().out)
    assert "_common.md" in claude_payload["hookSpecificOutput"]["additionalContext"]
    assert "akmon sync" in claude_payload["systemMessage"]

    _run_codex_hook(monkeypatch, "session-start", {"cwd": str(root)})
    codex_payload = json.loads(capsys.readouterr().out)
    assert "_common.md" in codex_payload["hookSpecificOutput"]["additionalContext"]
