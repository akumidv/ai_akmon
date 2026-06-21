"""Tests for the vendor adapters' tool normalization and the shared project-root lookup.

The neutral core (`hook_core`) never names a vendor's tools; each adapter maps its own
edit-tool name(s) to `hook_core.EDIT_TOOL`. `find_project_root` lives in the core and is reused.
"""

from __future__ import annotations

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
