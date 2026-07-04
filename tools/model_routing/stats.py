"""Session-statistics digest (design: meta/design/model-routing.md §4.4, task C13).

Parses the delegation log, the session transcript(s), and (optionally) the Claude API
usage endpoint to produce an on-demand digest of a session's routing activity: how much
was delegated, where the tokens went, and how much budget remains. Stdlib-only.

Pure aggregation lives in plain functions that take already-read data (lines, dicts);
I/O — filesystem walks, reading files, the HTTP call — sits in thin wrappers around them,
so the aggregation logic is testable without a real home directory or network access.

Run as ``python3 stats.py [--project-root PATH] [--transcript PATH] [--no-budget]
[--report-dir PATH]``. Never raises for a missing/unavailable data source: each section of
the digest degrades to an explanatory line instead, and the tool always exits 0.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import routing

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_CREDENTIALS_REL = Path(".claude") / ".credentials.json"
_REPORT_DIR_REL = Path(".claude") / "stats"


# --------------------------------------------------------------------------------------
# Token usage — shared shape across the orchestrator and every subagent
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def add(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
        )


def usage_from_message(message: dict) -> TokenUsage | None:
    """Extract a ``TokenUsage`` from an assistant record's ``message``; None when absent."""
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    def _int(key: str) -> int:
        value = usage.get(key, 0)
        return value if isinstance(value, int) else 0

    return TokenUsage(
        input_tokens=_int("input_tokens"),
        output_tokens=_int("output_tokens"),
        cache_read_tokens=_int("cache_read_input_tokens"),
        cache_creation_tokens=_int("cache_creation_input_tokens"),
    )


def _sum_usage(usages: Iterable[TokenUsage]) -> TokenUsage:
    total = TokenUsage()
    for usage in usages:
        total = total.add(usage)
    return total


# --------------------------------------------------------------------------------------
# Delegation log — ``.claude/model-routing.log``
# TSV: timestamp · session_id · subagent · model · zone · description (legacy: timestamp,
# subagent, model, description). Column ownership: routing.delegation_log_line.
# --------------------------------------------------------------------------------------


@dataclass
class DelegationStats:
    total: int = 0
    per_pair: Counter[tuple[str, str]] = field(default_factory=Counter)

    @property
    def per_subagent(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for (subagent, _model), count in self.per_pair.items():
            counts[subagent] += count
        return counts

    @property
    def per_model(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for (_subagent, model), count in self.per_pair.items():
            counts[model] += count
        return counts


def aggregate_delegation_lines(lines: Iterable[str]) -> DelegationStats:
    """Aggregate TSV delegation-log lines; a malformed line (fewer than 3 fields) is skipped.

    Current schema has subagent/model at fields 2/3 (>= 6 fields); a legacy 4-field line
    (timestamp · subagent · model · description) keeps them at 1/2 and is still counted.
    """
    stats = DelegationStats()
    for raw in lines:
        line = raw.rstrip("\n")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 6:
            subagent, model = parts[2], parts[3]
        elif len(parts) >= 3:
            subagent, model = parts[1], parts[2]
        else:
            continue
        stats.total += 1
        stats.per_pair[(subagent, model)] += 1
    return stats


def parse_delegation_log(path: Path) -> DelegationStats | None:
    """None when the log file is missing (renders as "no delegations logged")."""
    if not path.is_file():
        return None
    return aggregate_delegation_lines(path.read_text(encoding="utf-8").splitlines())


# --------------------------------------------------------------------------------------
# Main session transcript — ``~/.claude/projects/<munged-root>/*.jsonl``
# --------------------------------------------------------------------------------------


@dataclass
class TranscriptStats:
    per_model: dict[str, TokenUsage] = field(default_factory=dict)
    user_message_count: int = 0


def munged_project_dir(project_root: Path) -> str:
    """The ``~/.claude/projects/`` directory name for a project root: every ``/`` → ``-``."""
    return str(project_root.resolve()).replace("/", "-")


def transcripts_dir(project_root: Path, claude_home: Path | None = None) -> Path:
    home = claude_home or (Path.home() / ".claude")
    return home / "projects" / munged_project_dir(project_root)


def newest_jsonl(directory: Path) -> Path | None:
    """The most recently modified ``*.jsonl`` file in ``directory`` — the current session."""
    if not directory.is_dir():
        return None
    candidates = [path for path in directory.iterdir() if path.is_file() and path.suffix == ".jsonl"]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def aggregate_transcript_lines(lines: Iterable[str]) -> TranscriptStats:
    """Aggregate a main-session transcript: per-model token usage + a user-message count.

    Tolerates unparseable lines and ignores record types other than ``assistant`` (with
    ``message.usage``) and ``user`` (counted only).
    """
    stats = TranscriptStats()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        record_type = record.get("type")
        if record_type == "user":
            stats.user_message_count += 1
            continue
        if record_type != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = usage_from_message(message)
        if usage is None:
            continue
        model = str(message.get("model") or "-")
        stats.per_model[model] = stats.per_model.get(model, TokenUsage()).add(usage)
    return stats


def parse_main_transcript(path: Path | None) -> TranscriptStats | None:
    if path is None or not path.is_file():
        return None
    return aggregate_transcript_lines(path.read_text(encoding="utf-8").splitlines())


# --------------------------------------------------------------------------------------
# Subagent transcripts — ``<session-stem>/subagents/agent-<id>.jsonl`` + ``.meta.json``
# --------------------------------------------------------------------------------------


@dataclass
class SubagentRecord:
    agent_id: str
    label: str
    tier: str
    usage: TokenUsage


def agent_tier_map() -> dict[str, str]:
    """Map ``k-*`` agent name → tier, from the routing registry's generated-agent specs."""
    return {spec.name: spec.tier for spec in routing.AGENT_SPECS}


def _read_json_dict(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def label_and_tier(meta: dict, fallback_label: str, tier_map: dict[str, str]) -> tuple[str, str]:
    label = str(meta.get("agentType") or fallback_label or "-")
    return label, tier_map.get(label, "-")


def aggregate_subagent_lines(lines: Iterable[str]) -> tuple[TokenUsage, str | None]:
    """One subagent transcript's total usage, plus its ``attributionAgent`` as a label fallback."""
    total = TokenUsage()
    fallback_label: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if fallback_label is None:
            attribution = record.get("attributionAgent")
            if isinstance(attribution, str) and attribution:
                fallback_label = attribution
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = usage_from_message(message)
        if usage is not None:
            total = total.add(usage)
    return total, fallback_label


def collect_subagent_stats(subagents_dir: Path, tier_map: dict[str, str] | None = None) -> list[SubagentRecord]:
    """[] when the subagents directory is missing (renders as "no subagent transcripts")."""
    if not subagents_dir.is_dir():
        return []
    tiers = tier_map if tier_map is not None else agent_tier_map()
    records: list[SubagentRecord] = []
    for jsonl_path in sorted(subagents_dir.glob("agent-*.jsonl")):
        agent_id = jsonl_path.stem
        meta = _read_json_dict(subagents_dir / f"{agent_id}.meta.json")
        usage, fallback_label = aggregate_subagent_lines(jsonl_path.read_text(encoding="utf-8").splitlines())
        label, tier = label_and_tier(meta, fallback_label or "-", tiers)
        records.append(SubagentRecord(agent_id=agent_id, label=label, tier=tier, usage=usage))
    return records


# --------------------------------------------------------------------------------------
# Budget — Claude API usage endpoint (opt out with --no-budget)
# --------------------------------------------------------------------------------------


@dataclass
class LimitSummary:
    label: str
    remaining_pct: float | None
    resets_at: str | None


@dataclass
class BudgetSummary:
    session: LimitSummary | None = None
    week: LimitSummary | None = None
    scoped: list[LimitSummary] = field(default_factory=list)
    unavailable: str | None = None


def _remaining_pct(percent: object) -> float | None:
    if not isinstance(percent, int | float):
        return None
    return round(100.0 - float(percent), 1)


def parse_usage_response(data: dict) -> BudgetSummary:
    """Pure parse of the ``/api/oauth/usage`` response shape into remaining-budget summaries."""
    try:
        five_hour = data.get("five_hour") or {}
        seven_day = data.get("seven_day") or {}
        session = LimitSummary(
            label="session",
            remaining_pct=_remaining_pct(five_hour.get("utilization")),
            resets_at=five_hour.get("resets_at"),
        )
        week = LimitSummary(
            label="week (all models)",
            remaining_pct=_remaining_pct(seven_day.get("utilization")),
            resets_at=seven_day.get("resets_at"),
        )
        scoped: list[LimitSummary] = []
        for limit in data.get("limits") or []:
            if not isinstance(limit, dict) or limit.get("kind") != "weekly_scoped":
                continue
            model_name = ((limit.get("scope") or {}).get("model") or {}).get("display_name", "?")
            scoped.append(
                LimitSummary(
                    label=f"week ({model_name})",
                    remaining_pct=_remaining_pct(limit.get("percent")),
                    resets_at=limit.get("resets_at"),
                )
            )
        return BudgetSummary(session=session, week=week, scoped=scoped)
    except Exception as exc:  # defensive: any unexpected shape degrades, never crashes the digest
        return BudgetSummary(unavailable=f"{type(exc).__name__}: {exc}")


def read_access_token(credentials_path: Path) -> str | None:
    data = _read_json_dict(credentials_path)
    token = data.get("claudeAiOauth", {}).get("accessToken") if isinstance(data.get("claudeAiOauth"), dict) else None
    return token if isinstance(token, str) and token else None


def fetch_usage(url: str, token: str) -> dict:
    """The one network call in this module — kept tiny so tests inject a canned dict instead."""
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 (fixed https API host)
        return json.loads(response.read().decode("utf-8"))


def budget_summary(
    *,
    credentials_path: Path | None = None,
    fetch: Callable[[str, str], dict] = fetch_usage,
) -> BudgetSummary:
    """Never raises: any failure (no creds, HTTP error, timeout, bad shape) → ``unavailable``."""
    creds_path = credentials_path or (Path.home() / _CREDENTIALS_REL)
    try:
        token = read_access_token(creds_path)
        if not token:
            return BudgetSummary(unavailable="no credentials found")
        data = fetch(USAGE_URL, token)
        return parse_usage_response(data)
    except Exception as exc:
        return BudgetSummary(unavailable=f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------------------
# Rendering — full report (file) + compact digest (stdout)
# --------------------------------------------------------------------------------------


def _fmt_pct(value: float | None) -> str:
    return f"{value}%" if value is not None else "-"


def _fmt_resets(value: str | None) -> str:
    return value or "-"


def render_report(
    session_stem: str,
    transcript_path: Path | None,
    delegation: DelegationStats | None,
    transcript_stats: TranscriptStats | None,
    subagents: list[SubagentRecord],
    budget: BudgetSummary,
) -> str:
    lines = [f"# Session statistics — {session_stem}", ""]
    lines.append(f"Transcript: `{transcript_path}`" if transcript_path else "Transcript: not found")
    lines.append("")

    lines.append("## Delegations")
    lines.append("")
    if delegation is None:
        lines.append("no delegations logged")
    elif delegation.total == 0:
        lines.append("no delegations recorded")
    else:
        lines.append(f"Total: {delegation.total}")
        lines.append("")
        lines.append("| subagent | requested model | count |")
        lines.append("|---|---|---|")
        for (subagent, model), count in sorted(delegation.per_pair.items()):
            lines.append(f"| {subagent} | {model} | {count} |")
    lines.append("")

    lines.append("## Tokens")
    lines.append("")
    lines.append("| role/agent | tier | input | output | cache-read | cache-created |")
    lines.append("|---|---|---|---|---|---|")
    total = TokenUsage()
    if transcript_stats is None:
        lines.append("| orchestrator | orchestrator | - | - | - | - |")
    else:
        for model, usage in sorted(transcript_stats.per_model.items()):
            lines.append(
                f"| orchestrator ({model}) | orchestrator | {usage.input_tokens} | {usage.output_tokens} | "
                f"{usage.cache_read_tokens} | {usage.cache_creation_tokens} |"
            )
            total = total.add(usage)
    for record in subagents:
        lines.append(
            f"| {record.label} | {record.tier} | {record.usage.input_tokens} | {record.usage.output_tokens} | "
            f"{record.usage.cache_read_tokens} | {record.usage.cache_creation_tokens} |"
        )
        total = total.add(record.usage)
    lines.append(
        f"| **total** | | {total.input_tokens} | {total.output_tokens} | "
        f"{total.cache_read_tokens} | {total.cache_creation_tokens} |"
    )
    if not subagents:
        lines.append("")
        lines.append("no subagent transcripts")
    lines.append("")

    lines.append("## Budget")
    lines.append("")
    if budget.unavailable:
        lines.append(f"unavailable: {budget.unavailable}")
    else:
        if budget.session:
            lines.append(
                f"- session remaining: {_fmt_pct(budget.session.remaining_pct)} "
                f"(resets {_fmt_resets(budget.session.resets_at)})"
            )
        if budget.week:
            lines.append(
                f"- week (all models) remaining: {_fmt_pct(budget.week.remaining_pct)} "
                f"(resets {_fmt_resets(budget.week.resets_at)})"
            )
        for scoped in budget.scoped:
            lines.append(
                f"- {scoped.label} remaining: {_fmt_pct(scoped.remaining_pct)} (resets {_fmt_resets(scoped.resets_at)})"
            )
    lines.append("")

    lines.append("---")
    lines.append(
        "Sources: delegation log `.claude/model-routing.log`; "
        f"session transcript `{transcript_path}`." if transcript_path else "Sources: delegation log "
        "`.claude/model-routing.log`; session transcript not found."
    )
    return "\n".join(lines) + "\n"


def render_digest(
    delegation: DelegationStats | None,
    transcript_stats: TranscriptStats | None,
    subagents: list[SubagentRecord],
    budget: BudgetSummary,
    report_path: Path,
) -> str:
    """Compact stdout digest (~8-12 lines) — relayed to chat verbatim by the calling skill."""
    lines: list[str] = []

    if delegation is None:
        lines.append("delegations: no delegations logged")
    elif delegation.total == 0:
        lines.append("delegations: none recorded")
    else:
        per_subagent = ", ".join(f"{name}={count}" for name, count in sorted(delegation.per_subagent.items()))
        lines.append(f"delegations: {delegation.total} total ({per_subagent})")

    if transcript_stats is None:
        lines.append("orchestrator tokens: transcript unavailable")
    else:
        orch_total = _sum_usage(transcript_stats.per_model.values())
        lines.append(
            f"orchestrator tokens: in={orch_total.input_tokens} out={orch_total.output_tokens} "
            f"cache-read={orch_total.cache_read_tokens}"
        )

    if subagents:
        sub_total = _sum_usage(record.usage for record in subagents)
        lines.append(
            f"subagent tokens (n={len(subagents)}): in={sub_total.input_tokens} out={sub_total.output_tokens} "
            f"cache-read={sub_total.cache_read_tokens}"
        )
    else:
        lines.append("subagent tokens: no subagent transcripts")

    if budget.unavailable:
        lines.append(f"budget: unavailable ({budget.unavailable})")
    else:
        session = budget.session
        week = budget.week
        lines.append(
            f"budget: session {_fmt_pct(session.remaining_pct) if session else '-'} remaining "
            f"(resets {_fmt_resets(session.resets_at) if session else '-'}), "
            f"week {_fmt_pct(week.remaining_pct) if week else '-'} remaining "
            f"(resets {_fmt_resets(week.resets_at) if week else '-'})"
        )
        for scoped in budget.scoped:
            lines.append(
                f"budget: {scoped.label} {_fmt_pct(scoped.remaining_pct)} remaining "
                f"(resets {_fmt_resets(scoped.resets_at)})"
            )

    lines.append(f"report: {report_path}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root (default: cwd).")
    parser.add_argument("--transcript", type=Path, help="Override the main session transcript path.")
    parser.add_argument("--no-budget", action="store_true", help="Skip the Claude API budget call.")
    parser.add_argument("--report-dir", type=Path, help="Override the report output directory.")
    args = parser.parse_args(argv)

    root = args.project_root.resolve()

    delegation = parse_delegation_log(root / routing.DELEGATION_LOG_REL)

    transcript_path = args.transcript or newest_jsonl(transcripts_dir(root))
    transcript_stats = parse_main_transcript(transcript_path)

    session_stem = transcript_path.stem if transcript_path else "-"
    subagent_records: list[SubagentRecord] = []
    if transcript_path is not None:
        subagents_dir = transcript_path.parent / session_stem / "subagents"
        subagent_records = collect_subagent_stats(subagents_dir)

    budget = BudgetSummary(unavailable="skipped (--no-budget)") if args.no_budget else budget_summary()

    report_dir = args.report_dir or (root / _REPORT_DIR_REL)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"stats-{time.strftime('%Y%m%d-%H%M%S')}.md"
    report_file.write_text(
        render_report(session_stem, transcript_path, delegation, transcript_stats, subagent_records, budget),
        encoding="utf-8",
    )

    print(render_digest(delegation, transcript_stats, subagent_records, budget, report_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
