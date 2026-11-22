"""A49 — the SessionStart hook text the always-loaded ratchet counts (ADR 0012 F18, D-A49-HOOKCOUNT)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import hook_core
import routing
import session_start_text

from common import always_loaded as al
from common import learning


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def _project(tmp_path: Path) -> Path:
    charter = tmp_path / "_aitna" / "agents" / "development"
    charter.mkdir(parents=True)
    (charter / "README.md").write_text("# development\n", encoding="utf-8")
    materialized = tmp_path / "_aitna" / ".akmon" / "guardrails"
    materialized.mkdir(parents=True)
    (materialized / "_common.md").write_text("old text\n", encoding="utf-8")
    return tmp_path


def _text(members: tuple[al.Member, ...], name: str) -> str:
    return next(member.text for member in members if member.name == f"hook: {name}")


def test_the_three_session_start_hooks_are_members(tmp_path):
    members = session_start_text.session_start_members(_project(tmp_path))
    assert [member.name for member in members] == [
        "hook: session-start-agent",
        "hook: model-routing",
        "hook: learning-reminder",
    ]


def test_counting_the_hooks_writes_nothing(tmp_path):
    root = _project(tmp_path)
    before = _snapshot(root)
    session_start_text.session_start_members(root)
    assert _snapshot(root) == before  # no learning record, no marker, no routing config


def test_the_text_a_hook_injects_is_the_text_counted(tmp_path):
    root = _project(tmp_path)
    members = session_start_text.session_start_members(root)
    # session-start-agent: one function builds the context; only the stale line differs (worst case counted).
    ceiling = hook_core.stale_guardrail_ceiling(root)
    assert ceiling is not None
    layer = hook_core.session_layer(root, attended=True)
    assert _text(members, "session-start-agent") == hook_core.session_start_context(root, None, ceiling, layer)
    live = hook_core.session_start_result(root, None, layer)
    assert live is not None
    assert live.additional_context == hook_core.session_start_context(
        root, None, hook_core.stale_guardrail_notice(root), layer
    )
    # learning-reminder: the counted text is one of the two texts reminder_texts gives for the thresholds.
    data = learning.read_data()
    thresholds = learning.read_thresholds(root, data)
    wordings = {
        learning.reminder_texts(learning.Due(thresholds.reminder_sessions, thresholds.reminder_days, since_run), data)[
            0
        ]
        for since_run in (True, False)
    }
    assert _text(members, "learning-reminder") in wordings
    # model-routing: the status block is the hook's status_lines with the second-opinion pair resolved.
    registry = routing.load_registry(hook_core.akmon_runtime_root(root))
    config = routing.local_config(
        routing.compute_binding(registry, "opus", None, "anthropic", None),
        registry,
        second_opinion=False,
        available=None,
    )
    second = routing._second_opinion_status(registry, config, "anthropic", None)
    assert routing.status_lines(config, registry, "cmd", None) == routing.status_block(config, registry, "cmd", second)


def test_the_stale_ceiling_names_every_materialized_file(tmp_path):
    root = _project(tmp_path)
    notice = hook_core.stale_guardrail_ceiling(root)
    assert notice is not None
    assert "guardrails/_common.md" in notice


def test_the_learning_ceiling_is_the_longer_wording_and_reads_no_record(tmp_path):
    data = learning.read_data()
    thresholds = learning.Thresholds(10, 7)
    text = learning.reminder_ceiling(thresholds, data)
    assert text == max(
        (learning.reminder_texts(learning.Due(10, 7, since_run), data)[0] for since_run in (True, False)), key=len
    )
    assert not (tmp_path / data["state_rel"]).exists()
    assert learning.reminder_due(learning.LearningState(), thresholds, datetime.now(UTC)) is None


def test_the_routing_ceiling_is_deterministic_and_the_longest_form():
    registry = routing.load_registry(hook_core.akmon_runtime_root(Path()))
    text = routing.session_start_ceiling(registry, "akmon tool model_routing/init")
    assert text == routing.session_start_ceiling(registry, "akmon tool model_routing/init")
    assert "model routing:" in text
    init = "\n".join(routing.init_instruction(routing.staleness({}, registry, None), "akmon tool model_routing/init"))
    assert len(text.encode()) >= len(init.encode())


def test_hooks_join_both_scopes_and_are_reported_apart(tmp_path):
    agents = "# A\n\n## Dev layer — akmon\n\nintro\n"
    (tmp_path / "AGENTS.md").write_text(agents, encoding="utf-8")
    hook = al.Member("hook: x", "one\ntwo\n")
    found = al.populations(agents, tmp_path, hooks=(hook,))
    assert found is not None
    for scope in (al.shipped(), al.consumer()):
        population = found[scope]
        assert population.hooks == (hook,)
        assert population.hook_size == 8
        assert population.size == sum(m.size for m in population.members) + 8
        assert population.lines == sum(m.lines for m in population.members) + 2
        assert al.report(population, al.Cap(lines=100, bytes=1000)).endswith(" hooks=8")


def test_a_registry_that_does_not_parse_costs_the_routing_member_not_the_count(monkeypatch, tmp_path):
    def unreadable(_akmon, _root=None):
        raise ValueError("invalid JSON")

    monkeypatch.setattr(routing, "load_registry", unreadable)
    members = session_start_text.session_start_members(_project(tmp_path))
    assert [member.name for member in members] == ["hook: session-start-agent", "hook: learning-reminder"]


def test_the_tool_command_ceiling_is_the_longest_launcher_spelling():
    mount = routing.tool_command("_aitna/akmon", "model_routing/init")
    assert routing.tool_command_ceiling("_aitna/akmon", "model_routing/init") == mount
    assert len(mount) >= len(routing.tool_command("$(akmon path)", "model_routing/init"))
    assert routing.tool_command_ceiling("a", "t") == "python3 a/tools/t.py"


def test_each_audience_counts_its_own_layer_and_a_delegate_only_the_subagent_start_text(tmp_path):
    root = _project(tmp_path)
    attended = session_start_text.session_start_members(root)
    unattended = session_start_text.session_start_members(root, attended=False)
    delegate = session_start_text.subagent_start_members(root)
    head_layer = hook_core.session_layer(root, attended=True)
    other_layer = hook_core.session_layer(root, attended=False)
    assert _text(attended, "session-start-agent").endswith(head_layer)
    assert _text(unattended, "session-start-agent").endswith(other_layer)
    assert head_layer not in _text(unattended, "session-start-agent")
    assert [member.name for member in delegate] == ["hook: subagent-start"]
    assert delegate[0].text == other_layer  # the delegate and the unattended head read the same layer
    assert hook_core.subagent_start_result(root).additional_context == other_layer
