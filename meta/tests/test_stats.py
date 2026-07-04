"""Unit tests for the session-statistics digest tool (``tools/model_routing/stats.py``).

Everything builds throwaway fixtures under ``tmp_path``; no real home directory and no
network access — the budget tests inject a canned usage-response dict / fetch function.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_ROUTING_DIR = _KEYSTONE / "tools" / "model_routing"
if str(_ROUTING_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTING_DIR))

import routing  # noqa: E402
import stats  # noqa: E402

# --------------------------------------------------------------------------------------
# munged project dir + newest-jsonl selection
# --------------------------------------------------------------------------------------


def test_munged_project_dir_replaces_every_slash():
    root = Path("/home/ai/workspace/alphavar")
    assert stats.munged_project_dir(root) == "-home-ai-workspace-alphavar"


def test_transcripts_dir_under_claude_home(tmp_path):
    claude_home = tmp_path / "claude-home"
    root = tmp_path / "project"
    directory = stats.transcripts_dir(root, claude_home=claude_home)
    assert directory == claude_home / "projects" / stats.munged_project_dir(root)


def test_newest_jsonl_picks_most_recently_modified(tmp_path):
    directory = tmp_path / "sessions"
    directory.mkdir()
    older = directory / "aaa.jsonl"
    newer = directory / "zzz.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    time.sleep(0.01)
    newer.write_text("{}\n", encoding="utf-8")
    # Touch the older file's mtime backwards to remove any doubt about write order.
    import os

    now = time.time()
    os.utime(older, (now - 100, now - 100))
    os.utime(newer, (now, now))

    assert stats.newest_jsonl(directory) == newer


def test_newest_jsonl_missing_directory_returns_none(tmp_path):
    assert stats.newest_jsonl(tmp_path / "nope") is None


def test_newest_jsonl_ignores_non_jsonl_files(tmp_path):
    directory = tmp_path / "sessions"
    directory.mkdir()
    (directory / "notes.txt").write_text("hi", encoding="utf-8")
    assert stats.newest_jsonl(directory) is None


# --------------------------------------------------------------------------------------
# delegation log
# --------------------------------------------------------------------------------------


def test_parse_delegation_log_missing_file_returns_none(tmp_path):
    assert stats.parse_delegation_log(tmp_path / "model-routing.log") is None


def test_aggregate_delegation_lines_counts_and_skips_malformed():
    lines = [
        "T0\tk-explorer\tsmall\tfind X",
        "T1\tk-explorer\tsmall\tfind Y",
        "T2\tk-implementer\tmedium\timplement Z",
        "not-a-valid-line",
        "",
    ]
    result = stats.aggregate_delegation_lines(lines)
    assert result.total == 3
    assert result.per_subagent == {"k-explorer": 2, "k-implementer": 1}
    assert result.per_model == {"small": 2, "medium": 1}
    assert result.per_pair[("k-explorer", "small")] == 2


def test_parse_delegation_log_reads_real_file(tmp_path):
    log_path = tmp_path / "model-routing.log"
    log_path.write_text("T0\tk-explorer\tsmall\tfind X\n", encoding="utf-8")
    result = stats.parse_delegation_log(log_path)
    assert result.total == 1
    assert result.per_subagent["k-explorer"] == 1


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
    assert tier_map["k-explorer"] == "worker"
    assert tier_map["k-implementer"] == "mid"
    assert tier_map["k-reasoner"] == "reasoner"


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
        json.dumps({"agentType": "k-explorer", "description": "recon"}), encoding="utf-8"
    )

    # No meta.json for this one — falls back to the record's attributionAgent field.
    record = _assistant_record("claude-haiku-5", 3, 1)
    record["attributionAgent"] = "k-mechanic"
    (subagents / "agent-bbb.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")

    records = stats.collect_subagent_stats(subagents)
    by_id = {record.agent_id: record for record in records}

    assert by_id["agent-aaa"].label == "k-explorer"
    assert by_id["agent-aaa"].tier == "worker"
    assert by_id["agent-aaa"].usage.input_tokens == 10

    assert by_id["agent-bbb"].label == "k-mechanic"
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
    assert captured["url"] == stats.USAGE_URL


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
            "T0\tk-explorer\tsmall\tfind X",
            "T1\tk-implementer\tmedium\timplement Z",
        ]
    )
    transcript_stats = stats.aggregate_transcript_lines(
        [json.dumps(_assistant_record("claude-fable-5", 100, 20, cache_read=5))]
    )
    subagents = [
        stats.SubagentRecord(
            agent_id="agent-aaa",
            label="k-explorer",
            tier="worker",
            usage=stats.TokenUsage(input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_creation_tokens=0),
        )
    ]
    budget = stats.parse_usage_response(_USAGE_RESPONSE)
    return delegation, transcript_stats, subagents, budget


def test_render_report_contains_key_numbers(tmp_path):
    delegation, transcript_stats, subagents, budget = _sample_pieces()
    report = stats.render_report(
        "session-stem", tmp_path / "session-stem.jsonl", delegation, transcript_stats, subagents, budget
    )
    assert "session-stem" in report
    assert "k-explorer" in report and "small" in report
    assert "k-implementer" in report and "medium" in report
    assert "100" in report and "20" in report  # orchestrator token totals
    assert "87.5%" in report  # session remaining
    assert "60.0%" in report  # week remaining
    assert "Claude Opus 4" in report


def test_render_report_degrades_when_everything_missing():
    budget = stats.BudgetSummary(unavailable="no credentials found")
    report = stats.render_report("-", None, None, None, [], budget)
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
    assert any("k-explorer=1" in line for line in lines)
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
    log_path = root / routing.DELEGATION_LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("T0\tk-explorer\tsmall\tfind X\n", encoding="utf-8")

    fake_home = tmp_path / "home"
    claude_dir = fake_home / ".claude"
    munged = stats.munged_project_dir(root)
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
    assert len(report_files) == 1
    content = report_files[0].read_text(encoding="utf-8")
    assert "k-explorer" in content
    assert "42" in content
