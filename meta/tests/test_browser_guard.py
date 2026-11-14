"""The browser class of the access matrix (ADR 0032/D07): who may drive the shared browser.

The JavaScript twin pins the same cases in ``js/hooks/browser-guard.test.mjs``; the hook corpus
(``meta/conformance/scenarios/hooks/browser-guard-*.toml``) runs both implementations end to end.
"""

from __future__ import annotations

import hook_core
import pytest

from common import access_matrix

DEVELOPER = access_matrix.Actor.DEVELOPER
AUTONOMOUS = access_matrix.Actor.AUTONOMOUS


@pytest.mark.parametrize(
    "command",
    [
        "akmon tool browser status",
        "akmon tool browser start --url https://example.org",
        ".venv/bin/akmon tool browser status",
        "npx akmon tool browser status",
        "npx --no-install akmon tool browser status",
        "pnpm exec akmon tool browser status",
        "node node_modules/akmon/js/tools/browser.mjs status",
        "node js/tools/browser.mjs status",
        "python3 tools/browser.py status",
        "python3 /opt/akmon/tools/browser.py status",
        "uv run akmon tool browser status",
        "uv run python tools/browser.py status",
        "node --no-warnings js/tools/browser.mjs status",
        "node _aitna/akmon/js/akmon/cli.mjs tool browser status",
        "cd sub && akmon tool browser status",
        "FOO=1 env akmon tool browser status",
        "true; akmon tool browser status | cat",
        "bash -c 'akmon tool browser status'",
        "echo $(akmon tool browser status)",
    ],
)
def test_command_words_that_run_the_browser_tool_drive_it(command):
    assert hook_core.browser_command_drives(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "akmon tool model-routing show",
        "akmon tool browser-notes",
        'echo "akmon tool browser status"',
        "echo 'akmon tool browser status' > note.txt",
        "echo akmon tool browser status",
        "grep -r 'tool browser' docs",
        "cat <<'EOF'\nakmon tool browser status\nEOF",
        "node scripts/browser.mjs",
        "npx --no-install oxfmt js/tools/browser.mjs",
        "npx --no-install oxlint js/tools/browser.mjs js/tools/browser.py",
        "node --test js/tools/browser/attach.test.mjs",
        "grep -n x js/tools/browser.mjs",
        "cat tools/browser.py",
        "npx --no-install tsc --checkJs js/tools/browser.mjs",
        "git diff js/tools/browser.mjs",
        "sed -n 1,5p tools/browser.py",
        "python3 other/browser.py",
        "git commit -m 'akmon tool browser'",
    ],
)
def test_text_and_other_programs_do_not_drive_it(command):
    assert hook_core.browser_command_drives(command) is False


def _result(tool_name, command="", **facts):
    return hook_core.browser_guard_result(tool_name, command, **facts)


@pytest.mark.parametrize(
    ("tool_name", "command"),
    [("Bash", "akmon tool browser status"), ("mcp__akmon-browser__take_snapshot", "")],
)
def test_a_developers_own_session_drives_the_browser(tool_name, command):
    assert _result(tool_name, command, actor=DEVELOPER) is None
    assert _result(tool_name, command) is None  # no actor named: a developer


@pytest.mark.parametrize(
    ("tool_name", "command"),
    [("Bash", "akmon tool browser status"), ("mcp__akmon-browser__take_snapshot", "")],
)
def test_a_delegated_agent_is_denied_with_the_hand_back_reason(tool_name, command):
    result = _result(tool_name, command, actor=DEVELOPER, delegated=True)
    assert result is not None
    assert result.permission_decision == "deny"
    assert "delegated agent" in result.permission_reason
    assert "hand it back to the main session" in result.permission_reason
    assert "WebFetch" in result.permission_reason


@pytest.mark.parametrize("delegated", [False, True])
@pytest.mark.parametrize(
    ("tool_name", "command"),
    [("Bash", "npx akmon tool browser status"), ("mcp__akmon-browser__click", "")],
)
def test_an_autonomous_run_is_denied(tool_name, command, delegated):
    result = _result(tool_name, command, actor=AUTONOMOUS, delegated=delegated)
    assert result is not None
    assert result.permission_decision == "deny"
    assert "autonomous run" in result.permission_reason


@pytest.mark.parametrize(
    ("tool_name", "command"),
    [
        ("Bash", "ls"),
        ("Bash", 'echo "akmon tool browser status"'),
        ("mcp__other-server__click", ""),
        ("Read", "akmon tool browser status"),
        ("WebFetch", ""),
    ],
)
def test_anything_else_is_not_this_guards(tool_name, command):
    assert _result(tool_name, command, actor=AUTONOMOUS, delegated=True) is None


def test_the_guard_reads_the_outcome_from_the_matrix_and_escalates_an_ask_nobody_attends(monkeypatch):
    flipped = {actor: {**row} for actor, row in access_matrix.read_data().items()}
    flipped["developer"]["browser_session"] = "ask"
    monkeypatch.setattr(access_matrix, "read_data", lambda: flipped)
    asked = _result("mcp__akmon-browser__click", actor=DEVELOPER, permission_mode="default", attended=True)
    assert asked is not None
    assert asked.permission_decision == "ask"
    denied = _result("mcp__akmon-browser__click", actor=DEVELOPER, permission_mode="default", attended=False)
    assert denied is not None
    assert denied.permission_decision == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "npx -y -p akmon akmon tool browser open",
        "uv run --frozen --no-sync akmon tool browser open",
        "uv run python -m akmon tool browser open",
        "npm exec akmon tool browser status",
        "npm exec -- akmon tool browser status",
        "uvx akmon tool browser status",
        "pipx run akmon tool browser status",
        "bun js/tools/browser.mjs status",
        "bun run js/tools/browser.mjs status",
        "deno run --allow-all js/tools/browser.mjs status",
        "timeout 30 akmon tool browser open",
        "timeout -s KILL 30 node js/tools/browser.mjs status",
        "xargs akmon tool browser status",
        "xargs -n 1 akmon tool browser status",
        "nice -n 5 akmon tool browser status",
        "setsid akmon tool browser status",
        "stdbuf -oL akmon tool browser status",
        "/usr/bin/env node js/tools/browser.mjs status",
        "env -i akmon tool browser status",
        "env -u FOO akmon tool browser status",
        "command akmon tool browser status",
        "exec akmon tool browser status",
        "/usr/bin/node js/tools/browser.mjs status",
        "node.exe js/tools/browser.mjs status",
        "node22 js/tools/browser.mjs status",
        "python3.12 tools/browser.py status",
        "py tools/browser.py status",
        "node --import ./setup.mjs js/tools/browser.mjs status",
        "node --require ./setup.cjs js/tools/browser.mjs status",
        "node -r ./setup.cjs js/tools/browser.mjs status",
        "node --loader ./hooks.mjs js/tools/browser.mjs status",
        "timeout 30 bash -c 'akmon tool browser status'",
    ],
)
def test_launchers_wrappers_and_interpreter_spellings_drive_it(command):
    assert hook_core.browser_command_drives(command) is True
    assert _result("Bash", command, actor=DEVELOPER, delegated=True).permission_decision == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "node -e 'run()' js/tools/browser.mjs",
        "python3 -c 'run()' tools/browser.py",
        "python3 -m other tools/browser.py",
        "node --import ./setup.mjs js/other.mjs",
        "timeout 30 grep -n x js/tools/browser.mjs",
        "xargs echo akmon tool browser",
        "nice -n 5 echo akmon tool browser status",
        "env -i echo akmon tool browser status",
        "env -u FOO cat tools/browser.py",
        "node --test js/tools/browser/*.test.mjs",
        "npx --no-install oxfmt --check js/tools/browser.mjs",
        "tsc --noEmit js/tools/browser.mjs",
        "oxlint js/tools/browser.mjs",
        "git log -- js/tools/browser.mjs",
    ],
)
def test_wrapped_text_and_inline_code_do_not_drive_it(command):
    assert hook_core.browser_command_drives(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "akmon tool 'brow'ser status",
        'akmon tool "brows"er status',
        "akmon tool brow\\ser status",
        "npm exec akmon -- tool browser status",
        "npx akmon -- tool browser status",
        "python3 -m akmon.cli tool browser status",
        "python3 -m akmon tool browser status",
        "python3 -m akmon.anything tool browser status",
        "node js/tools/./browser.mjs status",
        "node ./js/tools/browser.mjs status",
        "node ../akmon/js/tools/browser.mjs status",
        "python3 ./tools/../tools/browser.py status",
        "cd js/tools && node browser.mjs status",
        "cd tools && python3 browser.py status",
        "cd /opt/akmon/js/tools; node ./browser.mjs status",
        "bash -c 'cd js/tools && node browser.mjs status'",
    ],
)
def test_quoting_separators_and_path_spellings_still_drive_it(command):
    assert hook_core.browser_command_drives(command) is True
    denied = _result("Bash", command, delegated=True)
    assert denied is not None
    assert denied.permission_decision == "deny"


def test_a_bare_script_name_is_the_tool_only_where_the_command_runs_in_the_tools_directory():
    assert hook_core.browser_command_drives("node browser.mjs status", "/repo/js/tools") is True
    assert hook_core.browser_command_drives("python3 browser.py status", "/repo/tools") is True
    assert hook_core.browser_command_drives("cd .. && node browser.mjs", "/repo/js/tools/sub") is True
    assert hook_core.browser_command_drives("node browser.mjs status", "/repo") is False
    assert hook_core.browser_command_drives("node browser.mjs status") is False
    assert hook_core.browser_command_drives("cd /repo && node browser.mjs status", "/repo/js/tools") is False
    result = _result("Bash", "node browser.mjs status", delegated=True, directory="/repo/js/tools")
    assert result is not None
    assert result.permission_decision == "deny"


@pytest.mark.parametrize(
    "command",
    [
        'echo "akmon tool browser"',
        "echo akmon tool browser",
        "echo 'brow'ser",
        "node --test js/tools/browser/*.test.mjs",
        "cd js/tools && node --test browser.test.mjs",
        "cd js/tools && grep -n x browser.mjs",
        "cd js/tools && cat browser.mjs",
        "cd js/tools && npx --no-install oxfmt browser.mjs",
        "git diff js/tools/browser.mjs",
        "cat <<'EOF'\nakmon tool browser\nEOF",
        "python3 -m pytest tools/browser.py",
        "npx --no-install oxlint -- js/tools/browser.mjs",
    ],
)
def test_the_new_spellings_leave_text_and_other_programs_silent(command):
    assert hook_core.browser_command_drives(command, "/repo/js/tools") is False


def test_the_strictest_decision_wins_and_the_first_of_equals():
    ask = hook_core.HookResult(event_name="PreToolUse", permission_decision="ask", permission_reason="a")
    deny = hook_core.HookResult(event_name="PreToolUse", permission_decision="deny", permission_reason="d")
    other = hook_core.HookResult(event_name="PreToolUse", permission_decision="deny", permission_reason="e")
    assert hook_core.strictest_result([None, None]) is None
    assert hook_core.strictest_result([ask, None]) is ask
    assert hook_core.strictest_result([ask, deny]) is deny
    assert hook_core.strictest_result([deny, ask]) is deny
    assert hook_core.strictest_result([deny, other]) is deny


def test_a_git_ask_does_not_hide_the_browser_deny(tmp_path):
    command = "git commit -m x && akmon tool browser status"
    git = hook_core.git_commit_guard_result(command, directory=str(tmp_path), attended=True)
    assert git is not None
    assert git.permission_decision == "ask"
    browser = _result("Bash", command, actor=DEVELOPER, delegated=True)
    chosen = hook_core.strictest_result([git, browser])
    assert chosen is not None
    assert chosen.permission_decision == "deny"
    assert "delegated agent" in chosen.permission_reason


def _project(tmp_path, *, attached):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "AGENTS.md").write_text("# project\n", encoding="utf-8")
    (tmp_path / ".aitna-root").write_text("_aitna\n", encoding="utf-8")
    if attached:
        marker = tmp_path / "_aitna" / ".local" / ".browser" / "attach.json"
        marker.parent.mkdir(parents=True)
        marker.write_text("{}", encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize("tool_name", ["mcp__akmon-browser__close_page", "mcp__akmon-browser__close_window"])
@pytest.mark.parametrize(
    "facts",
    [{}, {"delegated": True}, {"actor": AUTONOMOUS}],
)
def test_in_attach_mode_the_agent_never_closes_the_page(tmp_path, tool_name, facts):
    result = _result(tool_name, directory=_project(tmp_path, attached=True), **facts)
    assert result is not None
    assert result.permission_decision == "deny"


def test_the_attach_close_reason_is_the_attach_text_for_the_developers_session(tmp_path):
    result = _result("mcp__akmon-browser__close_page", directory=_project(tmp_path, attached=True))
    assert result is not None
    assert "attach mode" in result.permission_reason


def test_without_an_attach_a_developer_closes_pages_and_other_tools_are_not_held(tmp_path):
    detached = _project(tmp_path / "detached", attached=False)
    attached = _project(tmp_path / "attached", attached=True)
    assert _result("mcp__akmon-browser__close_page", directory=detached) is None
    assert _result("mcp__akmon-browser__take_snapshot", directory=attached) is None
    assert _result("mcp__other-server__close_page", directory=attached) is None


def test_an_unresolvable_project_skips_the_attach_check(tmp_path):
    assert _result("mcp__akmon-browser__close_page", directory=str(tmp_path)) is None
