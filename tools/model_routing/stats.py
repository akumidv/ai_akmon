"""Session-statistics digest (design: docs/design/model-routing.md §4.4, task C13).

Parses the delegation log, the session transcript(s), and (optionally) the Claude API
usage endpoint to produce an on-demand digest of a session's routing activity: how much
was delegated, where the tokens went, how much budget remains, and (task A49) what share of the
project's sessions needed code at all. Stdlib-only.

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
import re
import sys
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The tree root, so the shared ``common`` package resolves: the data loader and the
# delegation-log path it owns are reached the same way in mounted and package mode alike.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routing

from common import jsondata
from common.report_path import create_report, report_prefix, task_error
from common.transcripts import newest_jsonl, transcripts_dir


def _stats_data() -> dict:
    """The session-stats digest and report texts (``stats.json``), read on the call that needs it."""
    return jsondata.read(Path(__file__).parent / "stats.json")


def usage_url() -> str:
    """The Claude API usage endpoint the budget summary fetches (opt out with ``--no-budget``)."""
    return _stats_data()["usage_url"]


def credentials_rel() -> str:
    """The OAuth credentials file (home-relative) the budget summary reads the access token from."""
    return _stats_data()["credentials_rel"]


def report_dir_rel() -> str:
    """The full-report output directory (project-root-relative)."""
    return _stats_data()["report_dir_rel"]


# --------------------------------------------------------------------------------------
# Token usage — shared shape across the orchestrator and every subagent
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenUsage:
    """Token usage for one turn or one aggregate — the shape shared across every role."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def add(self, other: TokenUsage) -> TokenUsage:
        """Elementwise sum with ``other``."""
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
    """Aggregated delegation-log counts: total, and per (subagent, model) pair."""

    total: int = 0
    per_pair: Counter[tuple[str, str]] = field(default_factory=Counter)

    @property
    def per_subagent(self) -> Counter[str]:
        """Delegation counts collapsed to subagent, ignoring model."""
        counts: Counter[str] = Counter()
        for (subagent, _model), count in self.per_pair.items():
            counts[subagent] += count
        return counts

    @property
    def per_model(self) -> Counter[str]:
        """Delegation counts collapsed to model, ignoring subagent."""
        counts: Counter[str] = Counter()
        for (_subagent, model), count in self.per_pair.items():
            counts[model] += count
        return counts


def aggregate_delegation_lines(lines: Iterable[str]) -> DelegationStats:
    """Aggregate delegation-log lines, counting exactly the rows ``routing.parse_delegation_entries`` yields.

    The current 6-field schema and the legacy 4-field one; a shorter line is skipped. One
    parser for both default readers, not a second reading here: this digest accepted a
    3-field row that the coverage map skips, so the two could disagree on which delegations
    exist (C76). An absent model counts as ``-``, as the log writes it.
    """
    stats = DelegationStats()
    for entry in routing.parse_delegation_entries(lines):
        stats.total += 1
        stats.per_pair[(entry.subagent, entry.model or "-")] += 1
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
    """Aggregated main-session transcript stats: per-model token usage + a user-message count.

    ``code_touch`` is the scan of the directory the transcript sits in (task A49), set by ``main``
    once the transcript is read; it is ``None`` until then and for a transcript that is not found.
    """

    per_model: dict[str, TokenUsage] = field(default_factory=dict)
    user_message_count: int = 0
    code_touch: CodeTouchStats | None = None


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
    """Read and aggregate the main-session transcript; None when ``path`` is absent."""
    if path is None or not path.is_file():
        return None
    return aggregate_transcript_lines(path.read_text(encoding="utf-8").splitlines())


# --------------------------------------------------------------------------------------
# Subagent transcripts — ``<session-stem>/subagents/agent-<id>.jsonl`` + ``.meta.json``
# --------------------------------------------------------------------------------------


@dataclass
class SubagentRecord:
    """One subagent transcript's identity, label/tier, and total token usage."""

    agent_id: str
    label: str
    tier: str
    usage: TokenUsage


def agent_tier_map() -> dict[str, str]:
    """Map ``k_*`` agent name → tier, from the routing registry's generated-agent specs."""
    return {spec.name: spec.tier for spec in routing.agent_specs()}


def _read_json_dict(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def label_and_tier(meta: dict, fallback_label: str, tier_map: dict[str, str]) -> tuple[str, str]:
    """Display label and tier for a subagent transcript, from its ``.meta.json`` and the tier map."""
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
# Code touch — which sessions needed code at all (task A49)
# --------------------------------------------------------------------------------------

#: The three classes a session falls into, from the strongest touch of code to none.
CODE_EDIT = "code-edit"
CODE_READ = "code-read"
NO_CODE = "no-code"


@dataclass(frozen=True)
class TouchRules:
    """What counts as touching code: the tools, the code-file extensions, the test-command pattern."""

    code_extensions: frozenset[str]
    edit_tools: frozenset[str]
    read_tools: frozenset[str]
    shell_tools: frozenset[str]
    path_fields: tuple[str, ...]
    command_pattern: re.Pattern[str]
    system_reminder_prefix: str


def touch_rules(data: dict) -> TouchRules:
    """The rules from the ``code_touch`` block of ``stats.json`` (``data`` is the whole file)."""
    block = data["code_touch"]
    alternatives = "|".join(block["test_command_patterns"])
    return TouchRules(
        code_extensions=frozenset(block["code_extensions"]),
        edit_tools=frozenset(block["edit_tools"]),
        read_tools=frozenset(block["read_tools"]),
        shell_tools=frozenset(block["shell_tools"]),
        path_fields=tuple(block["path_fields"]),
        command_pattern=re.compile(rf"\b(?:{alternatives})\b", re.ASCII),
        system_reminder_prefix=block["system_reminder_prefix"],
    )


@dataclass(frozen=True)
class SessionTouch:
    """One transcript classified: its class, the user turn of its first code touch, its label.

    ``label`` is the subagent type for a subagent transcript and ``-`` for a main session.
    """

    kind: str
    first_touch_turn: int | None
    label: str = "-"


@dataclass(frozen=True)
class CodeTouchStats:
    """Every classified main session and subagent transcript found beside the located transcript."""

    scanned: Path
    main: list[SessionTouch]
    subagents: list[SessionTouch]


def _is_user_turn(record: dict, rules: TouchRules) -> bool:
    """A prompt typed by the user: not a tool result, not a meta or system-reminder record."""
    if record.get("type") != "user" or record.get("isMeta"):
        return False
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return not content.startswith(rules.system_reminder_prefix)
    if isinstance(content, list):
        kinds = {item.get("type") for item in content if isinstance(item, dict)}
        return "tool_result" not in kinds and "text" in kinds
    return False


def _touches_code(tool_use: dict, rules: TouchRules) -> str | None:
    """``CODE_EDIT`` or ``CODE_READ`` when one tool call touches code, else ``None``."""
    name = tool_use.get("name")
    tool_input = tool_use.get("input")
    if not isinstance(name, str) or not isinstance(tool_input, dict):
        return None
    if name in rules.shell_tools:
        command = tool_input.get("command")
        if isinstance(command, str) and rules.command_pattern.search(command):
            return CODE_READ
        return None
    if name not in rules.edit_tools and name not in rules.read_tools:
        return None
    target = next((tool_input[field] for field in rules.path_fields if tool_input.get(field)), "")
    if not isinstance(target, str) or Path(target).suffix.lower() not in rules.code_extensions:
        return None
    return CODE_EDIT if name in rules.edit_tools else CODE_READ


def _json_records(lines: Iterable[str]) -> Iterator[dict]:
    """The lines that are JSON objects; blank, unparseable and non-object lines are passed over."""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def _tool_uses(record: dict) -> Iterator[dict]:
    """The ``tool_use`` items of an assistant record."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if record.get("type") != "assistant" or not isinstance(content, list):
        return
    yield from (item for item in content if isinstance(item, dict) and item.get("type") == "tool_use")


def classify_session_lines(lines: Iterable[str], rules: TouchRules) -> SessionTouch | None:
    """Classify one transcript; ``None`` when it holds no user turn (nothing asked, nothing to measure).

    A code *edit* is an edit tool on a code file; a code *read* is a read tool on a code file or a
    shell command running the project's tests, linters or tools. A shell write (heredoc, ``sed -i``)
    and ``Grep``/``Glob`` are not counted, so ``NO_CODE`` is an upper bound on the sessions that
    never touched code. ``first_touch_turn`` is how many user turns had been seen at the first edit
    or read, whichever came first. The label is the transcript's ``attributionAgent``, else ``-``.
    """
    turns = 0
    edited = False
    first_touch_turn: int | None = None
    label = "-"
    for record in _json_records(lines):
        attribution = record.get("attributionAgent")
        if label == "-" and isinstance(attribution, str) and attribution:
            label = attribution
        if _is_user_turn(record, rules):
            turns += 1
            continue
        for tool_use in _tool_uses(record):
            kind = _touches_code(tool_use, rules)
            if kind is None:
                continue
            edited = edited or kind == CODE_EDIT
            if first_touch_turn is None:
                first_touch_turn = turns
    if turns == 0:
        return None
    if edited:
        return SessionTouch(CODE_EDIT, first_touch_turn, label)
    return SessionTouch(NO_CODE if first_touch_turn is None else CODE_READ, first_touch_turn, label)


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def collect_code_touch(transcripts_directory: Path, rules: TouchRules) -> CodeTouchStats | None:
    """Classify every session of a transcript directory and every subagent transcript under it.

    Main sessions are the ``*.jsonl`` files of the directory; subagents are
    ``<directory>/<session>/subagents/agent-*.jsonl``, labelled by their ``.meta.json`` ``agentType``
    (else their ``attributionAgent``). ``None`` when the directory is missing.
    """
    if not transcripts_directory.is_dir():
        return None
    main: list[SessionTouch] = []
    for path in sorted(transcripts_directory.glob("*.jsonl")):
        touch = classify_session_lines(_read_lines(path), rules)
        if touch is not None:
            main.append(touch)
    subagents: list[SessionTouch] = []
    for path in sorted(transcripts_directory.glob("*/subagents/agent-*.jsonl")):
        touch = classify_session_lines(_read_lines(path), rules)
        if touch is not None:
            label, _tier = label_and_tier(_read_json_dict(path.parent / f"{path.stem}.meta.json"), touch.label, {})
            subagents.append(replace(touch, label=label))
    return CodeTouchStats(transcripts_directory, main, subagents)


# --------------------------------------------------------------------------------------
# Budget — Claude API usage endpoint (opt out with --no-budget)
# --------------------------------------------------------------------------------------


@dataclass
class LimitSummary:
    """One usage-endpoint limit: its label, remaining percent, and reset time."""

    label: str
    remaining_pct: float | None
    resets_at: str | None


@dataclass
class BudgetSummary:
    """Parsed ``/api/oauth/usage`` response: session/week/scoped limits, or an unavailable reason."""

    session: LimitSummary | None = None
    week: LimitSummary | None = None
    scoped: list[LimitSummary] = field(default_factory=list)
    unavailable: str | None = None


def _remaining_pct(percent: object) -> float | None:
    # A tuple keeps the runtime check explicit and accepts both numeric scalar types.
    if not isinstance(percent, (int, float)):
        return None
    return round(100.0 - float(percent), 1)


def parse_usage_response(data: dict) -> BudgetSummary:
    """Pure parse of the ``/api/oauth/usage`` response shape into remaining-budget summaries."""
    try:
        labels = _stats_data()["budget_labels"]
        five_hour = data.get("five_hour") or {}
        seven_day = data.get("seven_day") or {}
        session = LimitSummary(
            label=labels["session"],
            remaining_pct=_remaining_pct(five_hour.get("utilization")),
            resets_at=five_hour.get("resets_at"),
        )
        week = LimitSummary(
            label=labels["week_all_models"],
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
                    label=jsondata.fill(labels["week_scoped"], {"model": model_name}),
                    remaining_pct=_remaining_pct(limit.get("percent")),
                    resets_at=limit.get("resets_at"),
                )
            )
        return BudgetSummary(session=session, week=week, scoped=scoped)
    except Exception as exc:  # noqa: BLE001 — any unexpected shape degrades, never crashes the digest
        return BudgetSummary(unavailable=f"{type(exc).__name__}: {exc}")


def read_access_token(credentials_path: Path) -> str | None:
    """The OAuth access token from a ``.credentials.json`` file, or None when absent/malformed."""
    data = _read_json_dict(credentials_path)
    token = data.get("claudeAiOauth", {}).get("accessToken") if isinstance(data.get("claudeAiOauth"), dict) else None
    return token if isinstance(token, str) and token else None


def fetch_usage(url: str, token: str) -> dict:
    """The one network call in this module — kept tiny so tests inject a canned dict instead."""
    request = urllib.request.Request(  # noqa: S310 (fixed https API host)
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
    creds_path = credentials_path or (Path.home() / credentials_rel())
    try:
        token = read_access_token(creds_path)
        if not token:
            return BudgetSummary(unavailable="no credentials found")
        data = fetch(usage_url(), token)
        return parse_usage_response(data)
    except Exception as exc:  # noqa: BLE001 — never raises: every failure is `unavailable`
        return BudgetSummary(unavailable=f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------------------
# Rendering — full report (file) + compact digest (stdout)
# --------------------------------------------------------------------------------------


def _fmt_pct(value: float | None) -> str:
    return f"{value}%" if value is not None else "-"


def _fmt_resets(value: str | None) -> str:
    return value or "-"


def _percent(count: int, total: int) -> int:
    """``count`` of ``total`` as a whole percent, halves rounded up — integer arithmetic, so both twins agree."""
    return (200 * count + total) // (2 * total)


def _share(count: int, total: int) -> str:
    return f"{_percent(count, total)}%" if total else "-"


def _median_text(values: Iterable[int]) -> str:
    """The median of whole numbers, ``-`` for none; an even count between two odd values ends in ``.5``."""
    ordered = sorted(values)
    if not ordered:
        return "-"
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return str(ordered[middle])
    pair = ordered[middle - 1] + ordered[middle]
    return str(pair // 2) if pair % 2 == 0 else f"{pair // 2}.5"


@dataclass(frozen=True)
class _Group:
    """The class counts of one group of transcripts, as the texts the digest and the report print."""

    n: int
    edit: str
    read: str
    none: str
    median: str


def _group(touches: Sequence[SessionTouch]) -> _Group:
    total = len(touches)
    counts = Counter(touch.kind for touch in touches)
    turns = [touch.first_touch_turn for touch in touches if touch.first_touch_turn is not None]
    return _Group(
        n=total,
        edit=f"{counts[CODE_EDIT]} ({_share(counts[CODE_EDIT], total)})",
        read=f"{counts[CODE_READ]} ({_share(counts[CODE_READ], total)})",
        none=f"{counts[NO_CODE]} ({_share(counts[NO_CODE], total)})",
        median=_median_text(turns),
    )


def _no_code_by_type(subagents: Sequence[SessionTouch]) -> list[tuple[str, int, int]]:
    """``(type, transcripts, no-code transcripts)`` per subagent type, the largest no-code share first."""
    totals: Counter[str] = Counter(touch.label for touch in subagents)
    empty: Counter[str] = Counter(touch.label for touch in subagents if touch.kind == NO_CODE)
    rows = [(label, totals[label], empty[label]) for label in totals]
    return sorted(rows, key=lambda row: (-_percent(row[2], row[1]), row[0]))


def _render_code_touch_digest(code_touch: CodeTouchStats | None) -> list[str]:
    """The digest's code-touch lines: both groups, the no-code share per subagent type, the limit."""
    data = _stats_data()
    texts = data["digest"]
    groups = data["code_touch"]
    if code_touch is None or not (code_touch.main or code_touch.subagents):
        return [texts["code_touch_none"]]
    lines: list[str] = []
    for name, touches in ((groups["group_main"], code_touch.main), (groups["group_subagents"], code_touch.subagents)):
        if not touches:
            lines.append(jsondata.fill(texts["code_touch_group_empty"], {"group": name}))
            continue
        group = _group(touches)
        lines.append(
            jsondata.fill(
                texts["code_touch_group"],
                {
                    "group": name,
                    "n": str(group.n),
                    "edit": group.edit,
                    "read": group.read,
                    "none": group.none,
                    "median": group.median,
                },
            )
        )
    if code_touch.subagents:
        types = ", ".join(
            f"{label} {_share(empty, total)} (n={total})"
            for label, total, empty in _no_code_by_type(code_touch.subagents)
        )
        lines.append(jsondata.fill(texts["code_touch_no_code_by_type"], {"types": types}))
    lines.append(texts["code_touch_limit"])
    return lines


def _render_code_touch_section(code_touch: CodeTouchStats | None) -> list[str]:
    """The '## Code touch' body: a table per group, a table per subagent type, the definitions."""
    data = _stats_data()
    texts = data["report"]
    groups = data["code_touch"]
    if code_touch is None or not (code_touch.main or code_touch.subagents):
        return [texts["code_touch_none"]]
    lines = [jsondata.fill(texts["code_touch_scanned"], {"dir": str(code_touch.scanned)}), ""]
    lines.extend(texts["code_touch_group_header"])
    for name, touches in ((groups["group_main"], code_touch.main), (groups["group_subagents"], code_touch.subagents)):
        group = _group(touches)
        lines.append(
            jsondata.fill(
                texts["code_touch_group_row"],
                {
                    "group": name,
                    "n": str(group.n),
                    "edit": group.edit,
                    "read": group.read,
                    "none": group.none,
                    "median": group.median,
                },
            )
        )
    if code_touch.subagents:
        lines.extend(["", *texts["code_touch_type_header"]])
        lines.extend(
            jsondata.fill(
                texts["code_touch_type_row"],
                {"type": label, "n": str(total), "none": str(empty), "share": _share(empty, total)},
            )
            for label, total, empty in _no_code_by_type(code_touch.subagents)
        )
    lines.extend(["", texts["code_touch_note"]])
    return lines


@dataclass(frozen=True)
class SessionRef:
    """Which session a report is about — its stem and the transcript path it was parsed from.

    The two travel together everywhere a report is rendered: ``stem`` is only ever derived
    from ``transcript_path`` (or stands in for a missing one), never chosen independently.
    """

    stem: str
    transcript_path: Path | None


def _render_delegations_section(delegation: DelegationStats | None) -> list[str]:
    """The '## Delegations' body: total plus the per-subagent/model breakdown table."""
    data = _stats_data()["report"]
    if delegation is None:
        return [data["delegations_none"]]
    if delegation.total == 0:
        return [data["delegations_zero"]]
    lines = [
        jsondata.fill(data["delegations_total"], {"total": delegation.total}),
        "",
        *data["delegations_table_header"],
    ]
    lines.extend(
        jsondata.fill(data["delegations_table_row"], {"subagent": subagent, "model": model, "count": count})
        for (subagent, model), count in sorted(delegation.per_pair.items())
    )
    return lines


def _render_tokens_section(transcript_stats: TranscriptStats | None, subagents: list[SubagentRecord]) -> list[str]:
    """The '## Tokens' body: per-role/tier token table plus the totals row."""
    data = _stats_data()["report"]
    lines = list(data["tokens_table_header"])
    total = TokenUsage()
    if transcript_stats is None:
        lines.append(data["tokens_orchestrator_missing_row"])
    else:
        for model, usage in sorted(transcript_stats.per_model.items()):
            lines.append(
                jsondata.fill(
                    data["tokens_orchestrator_row"],
                    {
                        "model": model,
                        "input": usage.input_tokens,
                        "output": usage.output_tokens,
                        "cache_read": usage.cache_read_tokens,
                        "cache_created": usage.cache_creation_tokens,
                    },
                )
            )
            total = total.add(usage)
    for record in subagents:
        lines.append(
            jsondata.fill(
                data["tokens_subagent_row"],
                {
                    "label": record.label,
                    "tier": record.tier,
                    "input": record.usage.input_tokens,
                    "output": record.usage.output_tokens,
                    "cache_read": record.usage.cache_read_tokens,
                    "cache_created": record.usage.cache_creation_tokens,
                },
            )
        )
        total = total.add(record.usage)
    lines.append(
        jsondata.fill(
            data["tokens_total_row"],
            {
                "input": total.input_tokens,
                "output": total.output_tokens,
                "cache_read": total.cache_read_tokens,
                "cache_created": total.cache_creation_tokens,
            },
        )
    )
    if not subagents:
        lines.append("")
        lines.append(data["tokens_no_subagents"])
    return lines


def _render_budget_section(budget: BudgetSummary) -> list[str]:
    """The '## Budget' body: unavailable notice, or the session/week/scoped remaining lines."""
    data = _stats_data()["report"]
    if budget.unavailable:
        return [jsondata.fill(data["budget_unavailable"], {"reason": budget.unavailable})]
    lines = []
    if budget.session:
        lines.append(
            jsondata.fill(
                data["budget_session_line"],
                {"remaining": _fmt_pct(budget.session.remaining_pct), "resets": _fmt_resets(budget.session.resets_at)},
            )
        )
    if budget.week:
        lines.append(
            jsondata.fill(
                data["budget_week_line"],
                {"remaining": _fmt_pct(budget.week.remaining_pct), "resets": _fmt_resets(budget.week.resets_at)},
            )
        )
    lines.extend(
        jsondata.fill(
            data["budget_scoped_line"],
            {
                "label": scoped.label,
                "remaining": _fmt_pct(scoped.remaining_pct),
                "resets": _fmt_resets(scoped.resets_at),
            },
        )
        for scoped in budget.scoped
    )
    return lines


def render_report(
    session: SessionRef,
    delegation: DelegationStats | None,
    transcript_stats: TranscriptStats | None,
    subagents: list[SubagentRecord],
    budget: BudgetSummary,
) -> str:
    """Full markdown report (file) — delegations, per-role tokens, code touch, budget."""
    data = _stats_data()["report"]
    transcript_path = session.transcript_path
    lines = [jsondata.fill(data["title"], {"stem": session.stem}), ""]
    lines.append(
        jsondata.fill(data["transcript_found"], {"path": transcript_path})
        if transcript_path
        else data["transcript_not_found"]
    )
    lines.append("")

    lines.append(data["delegations_heading"])
    lines.append("")
    lines.extend(_render_delegations_section(delegation))
    lines.append("")

    lines.append(data["tokens_heading"])
    lines.append("")
    lines.extend(_render_tokens_section(transcript_stats, subagents))
    lines.append("")

    lines.append(data["code_touch_heading"])
    lines.append("")
    lines.extend(_render_code_touch_section(transcript_stats.code_touch if transcript_stats else None))
    lines.append("")

    lines.append(data["budget_heading"])
    lines.append("")
    lines.extend(_render_budget_section(budget))
    lines.append("")

    lines.append(data["separator"])
    sources = data["sources_found"] if transcript_path else data["sources_not_found"]
    lines.append(jsondata.fill(sources, {"path": transcript_path, "delegation_log": routing.delegation_log_rel()}))
    return "\n".join(lines) + "\n"


def render_digest(
    delegation: DelegationStats | None,
    transcript_stats: TranscriptStats | None,
    subagents: list[SubagentRecord],
    budget: BudgetSummary,
    report_path: Path,
) -> str:
    """Compact stdout digest (~12-16 lines) — relayed to chat verbatim by the calling skill."""
    data = _stats_data()["digest"]
    lines: list[str] = []

    if delegation is None:
        lines.append(data["no_delegations_logged"])
    elif delegation.total == 0:
        lines.append(data["no_delegations_recorded"])
    else:
        per_subagent = ", ".join(f"{name}={count}" for name, count in sorted(delegation.per_subagent.items()))
        lines.append(
            jsondata.fill(data["delegations_total"], {"total": delegation.total, "per_subagent": per_subagent})
        )

    if transcript_stats is None:
        lines.append(data["orchestrator_transcript_unavailable"])
    else:
        orch_total = _sum_usage(transcript_stats.per_model.values())
        lines.append(
            jsondata.fill(
                data["orchestrator_tokens"],
                {
                    "input": orch_total.input_tokens,
                    "output": orch_total.output_tokens,
                    "cache_read": orch_total.cache_read_tokens,
                },
            )
        )

    if subagents:
        sub_total = _sum_usage(record.usage for record in subagents)
        lines.append(
            jsondata.fill(
                data["subagent_tokens"],
                {
                    "n": len(subagents),
                    "input": sub_total.input_tokens,
                    "output": sub_total.output_tokens,
                    "cache_read": sub_total.cache_read_tokens,
                },
            )
        )
    else:
        lines.append(data["no_subagent_transcripts"])

    lines.extend(_render_code_touch_digest(transcript_stats.code_touch if transcript_stats else None))

    if budget.unavailable:
        lines.append(jsondata.fill(data["budget_unavailable"], {"reason": budget.unavailable}))
    else:
        session = budget.session
        week = budget.week
        lines.append(
            jsondata.fill(
                data["budget_session_week"],
                {
                    "session_remaining": _fmt_pct(session.remaining_pct) if session else "-",
                    "session_resets": _fmt_resets(session.resets_at) if session else "-",
                    "week_remaining": _fmt_pct(week.remaining_pct) if week else "-",
                    "week_resets": _fmt_resets(week.resets_at) if week else "-",
                },
            )
        )
        lines.extend(
            jsondata.fill(
                data["budget_scoped"],
                {
                    "label": scoped.label,
                    "remaining": _fmt_pct(scoped.remaining_pct),
                    "resets": _fmt_resets(scoped.resets_at),
                },
            )
            for scoped in budget.scoped
        )

    lines.append(jsondata.fill(data["report"], {"path": report_path}))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: assemble the digest, write the full report, print the compact digest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd(), help="Project root (default: cwd).")
    parser.add_argument("--transcript", type=Path, help="Override the main session transcript path.")
    parser.add_argument("--no-budget", action="store_true", help="Skip the Claude API budget call.")
    parser.add_argument("--report-dir", type=Path, help="Override the report output directory.")
    parser.add_argument(
        "--task",
        help="Task id the report belongs to; the report is <report-dir>/[<task>-]stats-<n>.md, n the next ordinal.",
    )
    args = parser.parse_args(argv)
    if (task_problem := task_error(args.task)) is not None:
        parser.error(task_problem)

    root = args.project_root.resolve()

    delegation = parse_delegation_log(root / routing.delegation_log_rel())

    transcript_path = args.transcript or newest_jsonl(transcripts_dir(root))
    transcript_stats = parse_main_transcript(transcript_path)

    session_stem = transcript_path.stem if transcript_path else "-"
    subagent_records: list[SubagentRecord] = []
    if transcript_path is not None:
        subagents_dir = transcript_path.parent / session_stem / "subagents"
        subagent_records = collect_subagent_stats(subagents_dir)

    if transcript_stats is not None and transcript_path is not None:
        transcript_stats.code_touch = collect_code_touch(transcript_path.parent, touch_rules(_stats_data()))

    budget = BudgetSummary(unavailable="skipped (--no-budget)") if args.no_budget else budget_summary()

    report_dir = args.report_dir or (root / report_dir_rel())
    report_file = create_report(
        report_dir,
        report_prefix("stats", args.task),
        render_report(
            SessionRef(session_stem, transcript_path),
            delegation,
            transcript_stats,
            subagent_records,
            budget,
        ),
    )

    print(render_digest(delegation, transcript_stats, subagent_records, budget, report_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
