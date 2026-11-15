"""Unit tests for the session-statistics digest tool (``tools/model_routing/stats.py``).

Everything builds throwaway fixtures under ``tmp_path``; no real home directory and no
network access — the budget tests inject a canned usage-response dict / fetch function.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _AKMON / "tools" / "model_routing"
if str(_ROUTING_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTING_DIR))

import routing  # noqa: E402
import stats  # noqa: E402

from common import jsondata  # noqa: E402
from common.transcripts import munged_project_dir  # noqa: E402

# --------------------------------------------------------------------------------------
# delegation log
# --------------------------------------------------------------------------------------


def test_parse_delegation_log_missing_file_returns_none(tmp_path):
    assert stats.parse_delegation_log(tmp_path / "model-routing.log") is None


def test_aggregate_delegation_lines_counts_and_skips_malformed():
    lines = [
        "T0\tk_explorer\tsmall\tfind X",
        "T1\tk_explorer\tsmall\tfind Y",
        "T2\tk_implementer\tmedium\timplement Z",
        "not-a-valid-line",
        "",
    ]
    result = stats.aggregate_delegation_lines(lines)
    assert result.total == 3
    assert result.per_subagent == {"k_explorer": 2, "k_implementer": 1}
    assert result.per_model == {"small": 2, "medium": 1}
    assert result.per_pair[("k_explorer", "small")] == 2


def test_digest_counts_exactly_the_rows_the_coverage_map_reads():
    """A 3-field row was counted here and skipped by the coverage map (C76): one parser now."""
    lines = [
        "T0\tk_explorer\tsmall",  # too short for either schema
        "T1\tk_explorer\tsmall\tfind X",  # legacy 4-field
        "T2\tsess-1\tk_reasoner\t-\tauth\tthink",  # current 6-field, no model
    ]
    result = stats.aggregate_delegation_lines(lines)
    assert result.total == len(routing.parse_delegation_entries(lines)) == 2
    assert result.per_pair == {("k_explorer", "small"): 1, ("k_reasoner", "-"): 1}


def test_parse_delegation_log_reads_real_file(tmp_path):
    log_path = tmp_path / "model-routing.log"
    log_path.write_text("T0\tk_explorer\tsmall\tfind X\n", encoding="utf-8")
    result = stats.parse_delegation_log(log_path)
    assert result.total == 1
    assert result.per_subagent["k_explorer"] == 1


# --------------------------------------------------------------------------------------
# main transcript aggregation
# --------------------------------------------------------------------------------------


def _assistant_record(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_created: int = 0):
    return {
        "type": "assistant",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_created,
            },
        },
    }


def test_aggregate_transcript_lines_groups_by_model_and_counts_user_messages():
    lines = [
        json.dumps(_assistant_record("claude-fable-5", 100, 20, cache_read=5, cache_created=1)),
        json.dumps(_assistant_record("claude-fable-5", 50, 10)),
        json.dumps(_assistant_record("claude-haiku-5", 10, 2)),
        json.dumps({"type": "user", "message": {"role": "user"}}),
        json.dumps({"type": "user", "message": {"role": "user"}}),
        json.dumps({"type": "system", "content": "..."}),
        json.dumps({"type": "file-history-snapshot"}),
        "not json at all {{{",
        "",
    ]
    result = stats.aggregate_transcript_lines(lines)
    assert set(result.per_model) == {"claude-fable-5", "claude-haiku-5"}
    fable = result.per_model["claude-fable-5"]
    assert fable.input_tokens == 150
    assert fable.output_tokens == 30
    assert fable.cache_read_tokens == 5
    assert fable.cache_creation_tokens == 1
    assert result.per_model["claude-haiku-5"].input_tokens == 10
    assert result.user_message_count == 2


def test_parse_main_transcript_missing_path_returns_none(tmp_path):
    assert stats.parse_main_transcript(None) is None
    assert stats.parse_main_transcript(tmp_path / "nope.jsonl") is None


def test_parse_main_transcript_reads_real_file(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps(_assistant_record("claude-fable-5", 5, 5)) + "\n", encoding="utf-8")
    result = stats.parse_main_transcript(path)
    assert result.per_model["claude-fable-5"].input_tokens == 5


# --------------------------------------------------------------------------------------
# subagent transcripts
# --------------------------------------------------------------------------------------


def test_agent_tier_map_covers_generated_specs():
    tier_map = stats.agent_tier_map()
    assert tier_map["k_explorer"] == "worker"
    assert tier_map["k_implementer"] == "mid"
    assert tier_map["k_reasoner"] == "reasoner"


def test_collect_subagent_stats_missing_dir_returns_empty(tmp_path):
    assert stats.collect_subagent_stats(tmp_path / "nope") == []


def test_collect_subagent_stats_reads_meta_and_falls_back_to_attribution(tmp_path):
    subagents = tmp_path / "subagents"
    subagents.mkdir()

    (subagents / "agent-aaa.jsonl").write_text(
        json.dumps(_assistant_record("claude-fable-5", 10, 5)) + "\n",
        encoding="utf-8",
    )
    (subagents / "agent-aaa.meta.json").write_text(
        json.dumps({"agentType": "k_explorer", "description": "recon"}), encoding="utf-8"
    )

    # No meta.json for this one — falls back to the record's attributionAgent field.
    record = _assistant_record("claude-haiku-5", 3, 1)
    record["attributionAgent"] = "k_mechanic"
    (subagents / "agent-bbb.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    records = stats.collect_subagent_stats(subagents)
    by_id = {record.agent_id: record for record in records}

    assert by_id["agent-aaa"].label == "k_explorer"
    assert by_id["agent-aaa"].tier == "worker"
    assert by_id["agent-aaa"].usage.input_tokens == 10

    assert by_id["agent-bbb"].label == "k_mechanic"
    assert by_id["agent-bbb"].tier == "worker"
    assert by_id["agent-bbb"].usage.input_tokens == 3


def test_label_and_tier_unknown_label_is_dash():
    label, tier = stats.label_and_tier({}, "-", stats.agent_tier_map())
    assert label == "-"
    assert tier == "-"


# --------------------------------------------------------------------------------------
# budget
# --------------------------------------------------------------------------------------


_USAGE_RESPONSE = {
    "five_hour": {"utilization": 12.5, "resets_at": "2026-07-03T18:00:00Z"},
    "seven_day": {"utilization": 40.0, "resets_at": "2026-07-07T00:00:00Z"},
    "limits": [
        {
            "kind": "weekly_scoped",
            "percent": 20.0,
            "resets_at": "2026-07-07T00:00:00Z",
            "scope": {"model": {"display_name": "Claude Opus 4"}},
        },
        {"kind": "session", "percent": 12.5, "resets_at": "2026-07-03T18:00:00Z"},
    ],
}


def test_parse_usage_response_reports_remaining_percentages():
    summary = stats.parse_usage_response(_USAGE_RESPONSE)
    assert summary.unavailable is None
    assert summary.session.remaining_pct == 87.5
    assert summary.session.resets_at == "2026-07-03T18:00:00Z"
    assert summary.week.remaining_pct == 60.0
    assert len(summary.scoped) == 1
    assert summary.scoped[0].label == "week (Claude Opus 4)"
    assert summary.scoped[0].remaining_pct == 80.0


def test_parse_usage_response_bad_shape_is_unavailable():
    summary = stats.parse_usage_response({"five_hour": "not-a-dict"})
    assert summary.unavailable is not None


def test_read_access_token_missing_file_returns_none(tmp_path):
    assert stats.read_access_token(tmp_path / "nope.json") is None


def test_read_access_token_reads_oauth_field(tmp_path):
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "secret-token"}}), encoding="utf-8")
    assert stats.read_access_token(creds) == "secret-token"


def test_budget_summary_no_credentials_is_unavailable(tmp_path):
    summary = stats.budget_summary(credentials_path=tmp_path / "nope.json")
    assert summary.unavailable == "no credentials found"


def test_budget_summary_uses_injected_fetch(tmp_path):
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "secret-token"}}), encoding="utf-8")

    captured: dict = {}

    def fake_fetch(url: str, token: str) -> dict:
        captured["url"] = url
        captured["token"] = token
        return _USAGE_RESPONSE

    summary = stats.budget_summary(credentials_path=creds, fetch=fake_fetch)
    assert summary.unavailable is None
    assert summary.session.remaining_pct == 87.5
    assert captured["token"] == "secret-token"
    assert captured["url"] == stats.usage_url()


def test_budget_summary_fetch_failure_is_unavailable(tmp_path):
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "secret-token"}}), encoding="utf-8")

    def failing_fetch(url: str, token: str) -> dict:
        raise TimeoutError("timed out")

    summary = stats.budget_summary(credentials_path=creds, fetch=failing_fetch)
    assert summary.unavailable is not None
    assert "timed out" in summary.unavailable


# --------------------------------------------------------------------------------------
# report + digest rendering
# --------------------------------------------------------------------------------------


def _sample_pieces():
    delegation = stats.aggregate_delegation_lines(
        [
            "T0\tk_explorer\tsmall\tfind X",
            "T1\tk_implementer\tmedium\timplement Z",
        ]
    )
    transcript_stats = stats.aggregate_transcript_lines(
        [json.dumps(_assistant_record("claude-fable-5", 100, 20, cache_read=5))]
    )
    subagents = [
        stats.SubagentRecord(
            agent_id="agent-aaa",
            label="k_explorer",
            tier="worker",
            usage=stats.TokenUsage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_creation_tokens=0),
        )
    ]
    budget = stats.parse_usage_response(_USAGE_RESPONSE)
    return delegation, transcript_stats, subagents, budget


def test_render_report_contains_key_numbers(tmp_path):
    delegation, transcript_stats, subagents, budget = _sample_pieces()
    report = stats.render_report(
        stats.SessionRef("session-stem", tmp_path / "session-stem.jsonl"),
        delegation,
        transcript_stats,
        subagents,
        budget,
    )
    assert "session-stem" in report
    assert "k_explorer" in report and "small" in report
    assert "k_implementer" in report and "medium" in report
    assert "100" in report and "20" in report  # orchestrator token totals
    assert "87.5%" in report  # session remaining
    assert "60.0%" in report  # week remaining
    assert "Claude Opus 4" in report


def test_render_report_degrades_when_everything_missing():
    budget = stats.BudgetSummary(unavailable="no credentials found")
    report = stats.render_report(stats.SessionRef("-", None), None, None, [], budget)
    assert "no delegations logged" in report
    assert "no subagent transcripts" in report
    assert "unavailable: no credentials found" in report


def test_render_digest_is_compact_and_contains_key_numbers(tmp_path):
    delegation, transcript_stats, subagents, budget = _sample_pieces()
    report_path = tmp_path / "stats-20260703-000000.md"
    digest = stats.render_digest(delegation, transcript_stats, subagents, budget, report_path)
    lines = digest.splitlines()

    assert 4 <= len(lines) <= 12
    assert any("delegations: 2 total" in line for line in lines)
    assert any("k_explorer=1" in line for line in lines)
    assert any("orchestrator tokens" in line and "in=100" in line for line in lines)
    assert any("subagent tokens" in line for line in lines)
    assert any("87.5%" in line for line in lines)
    assert lines[-1] == f"report: {report_path}"


def test_render_digest_degrades_when_everything_missing(tmp_path):
    report_path = tmp_path / "stats-20260703-000000.md"
    budget = stats.BudgetSummary(unavailable="no credentials found")
    digest = stats.render_digest(None, None, [], budget, report_path)
    assert "no delegations logged" in digest
    assert "transcript unavailable" in digest
    assert "no subagent transcripts" in digest
    assert "unavailable (no credentials found)" in digest
    assert digest.splitlines()[-1] == f"report: {report_path}"


# --------------------------------------------------------------------------------------
# CLI end-to-end (no network — --no-budget)
# --------------------------------------------------------------------------------------


def test_main_end_to_end_writes_report_and_prints_digest(tmp_path, capsys, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    log_path = root / routing.delegation_log_rel()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("T0\tk_explorer\tsmall\tfind X\n", encoding="utf-8")

    fake_home = tmp_path / "home"
    claude_dir = fake_home / ".claude"
    munged = munged_project_dir(root)
    session_dir = claude_dir / "projects" / munged
    session_dir.mkdir(parents=True)
    session_path = session_dir / "abc123.jsonl"
    session_path.write_text(json.dumps(_assistant_record("claude-fable-5", 42, 7)) + "\n", encoding="utf-8")

    # transcripts_dir() reads Path.home() / ".claude"; point Path.home() at fake_home so
    # that Path.home() / ".claude" == claude_dir.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    report_dir = tmp_path / "reports"
    exit_code = stats.main(
        [
            "--project-root",
            str(root),
            "--no-budget",
            "--report-dir",
            str(report_dir),
        ]
    )
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "delegations: 1 total" in out
    assert "report:" in out

    report_files = list(report_dir.glob("stats-*.md"))
    assert [p.name for p in report_files] == ["stats-1.md"]
    content = report_files[0].read_text(encoding="utf-8")
    assert "k_explorer" in content
    assert "42" in content


def test_main_with_a_task_takes_the_next_ordinal_of_that_prefix(tmp_path, capsys):
    """C114: ``<report-dir>/[<task>-]stats-<n>.md``; files of another prefix are not counted."""
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "C7-stats-1.md").write_text("earlier\n", encoding="utf-8")
    (report_dir / "stats-3.md").write_text("no task\n", encoding="utf-8")
    argv = ["--project-root", str(tmp_path), "--transcript", str(tmp_path / "absent.jsonl"), "--no-budget"]
    argv += ["--report-dir", str(report_dir), "--task", "C7"]

    assert stats.main(argv) == 0
    assert capsys.readouterr().out.rstrip().endswith("C7-stats-2.md")
    assert (report_dir / "C7-stats-1.md").read_text(encoding="utf-8") == "earlier\n"


# --------------------------------------------------------------------------------------
# A49: code touch — which sessions needed code at all
# --------------------------------------------------------------------------------------


def _rules() -> stats.TouchRules:
    return stats.touch_rules(stats._stats_data())


def _scanned(code_touch: stats.CodeTouchStats | None) -> stats.TranscriptStats:
    return stats.TranscriptStats(code_touch=code_touch)


def _prompt(text: str = "do it") -> str:
    return json.dumps({"type": "user", "message": {"content": text}})


def _tool_use(name: str, **tool_input: object) -> str:
    item = {"type": "tool_use", "name": name, "input": tool_input}
    return json.dumps({"type": "assistant", "message": {"content": [item]}})


def _tool_result() -> str:
    item = {"type": "tool_result", "content": "ok"}
    return json.dumps({"type": "user", "message": {"content": [item]}})


def test_a_session_with_no_user_turn_is_not_classified():
    lines = [_tool_use("Edit", file_path="/p/a.py"), _tool_result()]
    assert stats.classify_session_lines(lines, _rules()) is None


def test_system_reminder_meta_and_tool_result_records_are_not_user_turns():
    lines = [
        _prompt("<system-reminder>context</system-reminder>"),
        json.dumps({"type": "user", "isMeta": True, "message": {"content": "meta"}}),
        _tool_result(),
        json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "typed"}]}}),
    ]
    touch = stats.classify_session_lines(lines, _rules())
    assert touch == stats.SessionTouch(stats.NO_CODE, None)


def test_an_edit_of_a_code_file_is_code_edit_and_records_the_turn_of_the_first_touch():
    lines = [
        _prompt(),
        _tool_use("Read", file_path="/p/docs/a.md"),
        _prompt("again"),
        _tool_use("Read", file_path="/p/a.py"),
        _prompt("and again"),
        _tool_use("Write", file_path="/p/b.mjs"),
    ]
    touch = stats.classify_session_lines(lines, _rules())
    assert touch == stats.SessionTouch(stats.CODE_EDIT, 2)


def test_a_notebook_edit_reads_its_notebook_path_and_a_config_edit_is_no_touch():
    rules = _rules()
    assert stats.classify_session_lines([_prompt(), _tool_use("Edit", file_path="/p/c.toml")], rules).kind == (
        stats.NO_CODE
    )
    # A .ipynb is not a code extension, so a NotebookEdit on one counts for nothing.
    assert stats.classify_session_lines(
        [_prompt(), _tool_use("NotebookEdit", notebook_path="/p/n.ipynb")], rules
    ).kind == (stats.NO_CODE)
    assert stats.classify_session_lines(
        [_prompt(), _tool_use("NotebookEdit", notebook_path="/p/n.py")], rules
    ).kind == (stats.CODE_EDIT)


def test_a_read_of_a_code_file_or_a_test_command_is_code_read():
    rules = _rules()
    read = stats.classify_session_lines([_prompt(), _tool_use("Read", file_path="/p/A.PY")], rules)
    assert read == stats.SessionTouch(stats.CODE_READ, 1)
    ran = stats.classify_session_lines([_prompt(), _prompt(), _tool_use("Bash", command="uv run pytest -q")], rules)
    assert ran == stats.SessionTouch(stats.CODE_READ, 2)


def test_a_command_that_only_contains_a_test_word_inside_another_word_is_no_touch():
    rules = _rules()
    lines = [_prompt(), _tool_use("Bash", command="git log --oneline"), _tool_use("Bash", command="echo subtsc")]
    assert stats.classify_session_lines(lines, rules).kind == stats.NO_CODE


def test_a_bash_write_and_a_search_are_not_counted_the_stated_limit():
    lines = [
        _prompt(),
        _tool_use("Bash", command="cat > tools/a.py <<'EOF'\nx = 1\nEOF"),
        _tool_use("Grep", pattern="x", path="tools"),
        _tool_use("Glob", pattern="**/*.py"),
    ]
    assert stats.classify_session_lines(lines, _rules()).kind == stats.NO_CODE


def test_a_malformed_record_is_passed_over():
    lines = ["", "not json", "[1]", json.dumps({"type": "assistant", "message": {"content": "text"}}), _prompt()]
    assert stats.classify_session_lines(lines, _rules()) == stats.SessionTouch(stats.NO_CODE, None)


def test_the_label_is_the_attribution_agent():
    lines = [json.dumps({"type": "user", "attributionAgent": "k_explorer", "message": {"content": "go"}})]
    assert stats.classify_session_lines(lines, _rules()).label == "k_explorer"


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _code_touch_fixture(root: Path) -> None:
    _write_lines(root / "a.jsonl", [_prompt(), _tool_use("Edit", file_path="/p/a.py")])
    _write_lines(root / "b.jsonl", [_prompt(), _tool_use("Read", file_path="/p/b.js")])
    _write_lines(root / "c.jsonl", [_prompt()])
    _write_lines(root / "d.jsonl", [_tool_use("Edit", file_path="/p/a.py")])  # no user turn: left out
    _write_lines(root / "a" / "subagents" / "agent-1.jsonl", [_prompt(), _tool_use("Write", file_path="/p/n.ts")])
    (root / "a" / "subagents" / "agent-1.meta.json").write_text('{"agentType": "k_implementer"}', encoding="utf-8")
    _write_lines(root / "a" / "subagents" / "agent-2.jsonl", [_prompt()])
    (root / "a" / "subagents" / "agent-2.meta.json").write_text('{"agentType": "k_explorer"}', encoding="utf-8")
    _write_lines(
        root / "b" / "subagents" / "agent-3.jsonl",
        [json.dumps({"type": "user", "attributionAgent": "k_explorer", "message": {"content": "go"}})],
    )


def test_collect_code_touch_missing_directory_is_none(tmp_path):
    assert stats.collect_code_touch(tmp_path / "absent", _rules()) is None


def test_collect_code_touch_classifies_main_sessions_and_labelled_subagents(tmp_path):
    _code_touch_fixture(tmp_path)
    result = stats.collect_code_touch(tmp_path, _rules())
    assert result.scanned == tmp_path
    assert [touch.kind for touch in result.main] == [stats.CODE_EDIT, stats.CODE_READ, stats.NO_CODE]
    assert [(touch.label, touch.kind) for touch in result.subagents] == [
        ("k_implementer", stats.CODE_EDIT),
        ("k_explorer", stats.NO_CODE),
        ("k_explorer", stats.NO_CODE),
    ]


def test_median_text_is_whole_for_an_odd_count_and_half_steps_for_an_even_one():
    assert stats._median_text([]) == "-"
    assert stats._median_text([3, 1, 2]) == "2"
    assert stats._median_text([1, 3]) == "2"
    assert stats._median_text([1, 2]) == "1.5"


def test_percent_rounds_halves_up_in_integer_arithmetic():
    assert [stats._percent(count, 8) for count in range(9)] == [0, 13, 25, 38, 50, 63, 75, 88, 100]
    assert stats._share(0, 0) == "-"


def test_the_digest_reports_both_groups_the_type_shares_and_the_limit(tmp_path):
    _code_touch_fixture(tmp_path)
    code_touch = stats.collect_code_touch(tmp_path, _rules())
    lines = stats.render_digest(None, _scanned(code_touch), [], stats.BudgetSummary(), Path("r.md")).splitlines()
    assert (
        "code touch, main sessions (n=3): code-edit 1 (33%), code-read 1 (33%), no-code 1 (33%);"
        " median first touch at user turn 1"
    ) in lines
    assert (
        "code touch, subagents (n=3): code-edit 1 (33%), code-read 0 (0%), no-code 2 (67%);"
        " median first touch at user turn 1"
    ) in lines
    assert "code touch, no-code share by subagent type: k_explorer 100% (n=2), k_implementer 0% (n=1)" in lines
    assert any(line.startswith("code touch: a Bash write") for line in lines)


def test_the_digest_with_no_session_says_so_once(tmp_path):
    empty = stats.collect_code_touch(tmp_path, _rules())
    for code_touch in (None, empty):
        lines = stats.render_digest(None, _scanned(code_touch), [], stats.BudgetSummary(), Path("r.md")).splitlines()
        assert "code touch: no session transcript with a user turn" in lines
        assert not any(line.startswith("code touch,") for line in lines)


def test_the_digest_names_a_group_with_no_transcript(tmp_path):
    _write_lines(tmp_path / "a.jsonl", [_prompt()])
    code_touch = stats.collect_code_touch(tmp_path, _rules())
    lines = stats.render_digest(None, _scanned(code_touch), [], stats.BudgetSummary(), Path("r.md")).splitlines()
    assert "code touch, subagents: no transcript with a user turn" in lines
    assert not any("by subagent type" in line for line in lines)


def test_the_report_has_a_code_touch_section_with_group_and_type_tables(tmp_path):
    _code_touch_fixture(tmp_path)
    code_touch = stats.collect_code_touch(tmp_path, _rules())
    session = stats.SessionRef("main", tmp_path / "a.jsonl")
    report = stats.render_report(session, None, _scanned(code_touch), [], stats.BudgetSummary())
    assert "## Code touch" in report
    assert "| main sessions | 3 | 1 (33%) | 1 (33%) | 1 (33%) | 1 |" in report
    assert "| subagents | 3 | 1 (33%) | 0 (0%) | 2 (67%) | 1 |" in report
    assert "| k_explorer | 2 | 2 | 100% |" in report
    assert "upper bound" in report
    assert report.index("## Tokens") < report.index("## Code touch") < report.index("## Budget")


def test_main_scans_the_directory_of_the_located_transcript(tmp_path, capsys):
    sessions = tmp_path / "sessions"
    _code_touch_fixture(sessions)
    argv = ["--project-root", str(tmp_path), "--transcript", str(sessions / "a.jsonl"), "--no-budget"]
    argv += ["--report-dir", str(tmp_path / "reports")]
    assert stats.main(argv) == 0
    assert "code touch, main sessions (n=3)" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# C102: stats.json — the digest and report texts
# --------------------------------------------------------------------------------------


def test_stats_data_pins_the_structure_and_characteristic_texts():
    data = json.loads((_ROUTING_DIR / "stats.json").read_text(encoding="utf-8"))
    assert set(data) == {
        "usage_url",
        "credentials_rel",
        "report_dir_rel",
        "budget_labels",
        "code_touch",
        "digest",
        "report",
    }
    assert data["code_touch"]["edit_tools"] == ["Edit", "Write", "MultiEdit", "NotebookEdit"]
    assert ".py" in data["code_touch"]["code_extensions"]
    assert data["usage_url"] == "https://api.anthropic.com/api/oauth/usage"
    assert data["credentials_rel"] == ".claude/.credentials.json"
    assert data["report_dir_rel"] == ".claude/stats"
    assert data["budget_labels"]["week_all_models"] == "week (all models)"
    assert data["budget_labels"]["week_scoped"] == "week ({{model}})"
    assert data["digest"]["budget_unavailable"] == "budget: unavailable ({{reason}})"
    assert data["report"]["title"] == "# Session statistics — {{stem}}"
    assert data["report"]["tokens_orchestrator_missing_row"] == "| orchestrator | orchestrator | - | - | - | - |"
    assert data["report"]["tokens_table_header"][0] == (
        "| role/agent | tier | input | output | cache-read | cache-created |"
    )


def test_stats_loader_reads_exactly_stats_json(monkeypatch):
    seen: list[Path] = []

    def spy(path: Path):
        seen.append(path)
        return json.loads(path.read_text(encoding="utf-8"))

    monkeypatch.setattr(jsondata, "read", spy)
    stats.usage_url()
    stats.render_digest(None, None, [], stats.BudgetSummary(), Path("r.md"))
    assert len(seen) >= 2
    assert all(path == _ROUTING_DIR / "stats.json" for path in seen)


def test_a_missing_stats_json_raises_from_rendering(monkeypatch):
    def broken(path: Path):
        raise jsondata.DataFileError(f"akmon data file missing: {path}")

    monkeypatch.setattr(jsondata, "read", broken)
    with pytest.raises(jsondata.DataFileError):
        stats.render_digest(None, None, [], stats.BudgetSummary(), Path("r.md"))
    with pytest.raises(jsondata.DataFileError):
        stats.render_report(stats.SessionRef("s", None), None, None, [], stats.BudgetSummary())
    with pytest.raises(jsondata.DataFileError):
        stats.usage_url()
