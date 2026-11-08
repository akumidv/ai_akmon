"""The probe runner: ask a model through a channel, grade the answer, and write the ledger.

One run covers a list of models over a case/family selection, and it is written down as a
ledger so a score can be compared with another score later. The order of the stages is the
discipline:

1. **The gold-sanity gate runs first, over the whole selection.** The runner proves that each
   case's hidden test fails on the buggy program and passes on the fixed one before any model
   is asked about it. A case the gate refuses is **never scored**: the run is refused and the
   refusal is reported.
2. **Every model is asked the same items**, under one pinned envelope, and each answer is
   graded by a mechanical rule: a location hit for the hunt family, the hidden test for the
   two fix families. The scaffold is the one the channel carries - it is part of the score's
   key, not a detail of the run.
3. **A deferral is not a failure.** A transport failure, an empty answer, a cut-off answer and
   an attempt skipped for the token budget are counted on their own line and stay out of the
   pass rate, so a rate is always a rate over answers that were really produced.
4. **A malformed hunt answer is not a wrong location.** An answer that is not one
   ``file.py:function`` line is counted as ``malformed`` on its own line and is excluded from
   the localization rates: the model has not been shown unable to localize, only unable to
   follow the format.

Three different gates live in the tool, and they judge three different things:

* the **oracle gate** (``oracle.py``) judges an *item's hidden test*: it must fail on the buggy
  program and pass on the fixed one;
* the **model gates** (``gates`` in ``profile.json``) judge a *model's cell* - one model on one
  family - against a bar. These bars are declared data, in this one place. They are
  provisional: no published absolute threshold exists for a location hit or a repair rate, so
  every bar is a stated starting point, not a measured one;
* the **item-selection band** (``item_band`` in ``profile.json``) judges an *item across the
  pool of models*: an item that nearly every model passes, or nearly every model fails, does
  not separate the models, and is flagged for removal from the ranking. The band is 30-70 %
  over the candidate pool. It is a property of the item, not a bar a model must meet, and it
  needs several models to mean anything - with fewer scored attempts than ``min_scored`` it
  reports ``pool_too_small`` instead of a verdict.

**Nothing is lost to a crash.** Each attempt is appended to its detail file the moment it
finishes. A cell's ledger row is appended when the cell is complete; an interrupted run
(an exception, Ctrl-C, a sandbox failure) appends the rows of the cells it had begun with
``complete: false`` before the exception propagates. A re-run into the same output directory
appends to what is there.

**The token budget is per model.** With ``token_budget`` set, a model that has spent that many
prompt-plus-completion tokens (a deferral's spend counts) is not called again: its remaining
attempts are recorded as deferrals with the reason ``budget``. The check is made before each
call, so the last call may overshoot the budget by one answer.
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import cases
import oracle
import sandbox
import scoring
import settings
import transport

# The family names, the verdicts, the budget reason, the estimate's constants, the model gates
# and the item band are data (``profile.json``, read through ``settings.load()``). The model
# gates are provisional: no published absolute threshold exists for a location hit or a repair
# rate, so every bar is a stated starting point, not a measured one. Only ``pass`` and ``fail``
# are scored verdicts. The ``items_scored`` bar is 30 because a binary family at p ~ 0.5 has a
# standard error of about 9 points at 30 items, so below 30 items the rate is noise.


class RunnerError(RuntimeError):
    """The run cannot be made - a broken selection, not a model's failure."""


@dataclass(frozen=True)
class Selection:
    """What a run asks: which models, over which families and cases (``None`` is all)."""

    models: tuple[str, ...]
    families: tuple[str, ...] | None = None
    case_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class RunOptions:
    """How a run is made: where it writes, how long the sandbox may take, the budget per model."""

    out_dir: Path
    sandbox_timeout_s: int = field(default_factory=lambda: settings.load().sandbox.default_timeout_s)
    token_budget: int | None = None
    #: Grades a hidden test; ``None`` is the container sandbox, anything else is a stand-in.
    run_test: sandbox.TestRunner | None = None
    #: The run's timestamp; ``None`` is the current time.
    now: datetime | None = None


@dataclass(frozen=True)
class Outcome:
    """What one question earned, before it is tied to the model and the case."""

    verdict: str
    reason: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    answer: str = ""
    location_hit: bool | None = None
    file_hit: bool | None = None


@dataclass(frozen=True)
class Attempt:
    """One question asked of one model, and what it earned."""

    model: str
    case_id: str
    family: str
    scaffold: str
    envelope_sha: str
    cases_sha: str
    seed: str
    ts: str
    outcome: Outcome

    def as_dict(self) -> dict[str, object]:
        """The attempt as one JSON object - a line of the detail file."""
        outcome = self.outcome
        return {
            "ts": self.ts,
            "model": self.model,
            "case_id": self.case_id,
            "family": self.family,
            "scaffold": self.scaffold,
            "envelope_sha": self.envelope_sha,
            "cases_sha": self.cases_sha,
            "seed": self.seed,
            "verdict": outcome.verdict,
            "reason": outcome.reason,
            "answer": outcome.answer,
            "prompt_tokens": outcome.prompt_tokens,
            "completion_tokens": outcome.completion_tokens,
            "latency_s": round(outcome.latency_s, 3),
            "location_hit": outcome.location_hit,
            "file_hit": outcome.file_hit,
        }


@dataclass(frozen=True)
class Plan:
    """What a run would ask, and what it would cost."""

    pairs: tuple[tuple[str, str], ...]
    models: tuple[str, ...]
    calls: int
    estimated_minutes: float
    estimated_input_tokens: int
    estimated_output_tokens: int


@dataclass(frozen=True)
class ItemBandResult:
    """Where one (case, family) item sits against the item band across the pool."""

    case_id: str
    family: str
    scored: int
    pass_rate: float | None
    status: Literal["in_band", "outside_band", "pool_too_small"]


@dataclass(frozen=True)
class RunReport:
    """What a run produced: the attempts, the ledger rows, the gate's verdict and the item bands."""

    attempts: tuple[Attempt, ...]
    rows: tuple[dict[str, object], ...]
    gate: oracle.GateReport
    item_bands: tuple[ItemBandResult, ...]
    ledger: Path
    detail_files: tuple[Path, ...]


def _selected_pairs(item_set: cases.ItemSet, selection: Selection) -> tuple[tuple[cases.Case, str], ...]:
    """The (case, family) pairs a run asks, in the item set's own order."""
    wanted = set(selection.families) if selection.families is not None else None
    return tuple(
        (case, family)
        for case in item_set.select(selection.case_ids, selection.families)
        for family in case.families
        if wanted is None or family in wanted
    )


def _prompt_tokens(case: cases.Case, family: str) -> int:
    """The prompt's size in tokens, estimated from its characters."""
    ask = case.ask(family)
    return math.ceil((len(ask.system) + len(ask.user)) / settings.load().estimate.chars_per_token)


def build_plan(item_set: cases.ItemSet, selection: Selection) -> Plan:
    """The (case id, family) pairs a run would ask, with a rough time and token estimate.

    The estimate stands on four constants, stated so the number can be argued with:
    ``call_seconds`` per call, ``sandbox_seconds`` per sandboxed run (the two fix families
    only), ``chars_per_token`` for the prompt's size, and ``output_tokens`` for one answer -
    all in ``profile.json``.
    """
    estimate = settings.load().estimate
    pairs = _selected_pairs(item_set, selection)
    models = len(selection.models)
    calls = len(pairs) * models
    input_tokens = sum(_prompt_tokens(case, family) for case, family in pairs) * models
    sandbox_runs = sum(1 for _case, family in pairs if family in settings.load().families.fix) * models
    seconds = calls * estimate.call_seconds + sandbox_runs * estimate.sandbox_seconds
    return Plan(
        pairs=tuple((case.id, family) for case, family in pairs),
        models=selection.models,
        calls=calls,
        estimated_minutes=round(seconds / 60.0, 1),
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=calls * estimate.output_tokens,
    )


def _deferred(reason: str, usage: transport.Usage, latency_s: float, answer: str = "") -> Outcome:
    return Outcome(
        verdict="deferred",
        reason=reason,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        latency_s=latency_s,
        answer=answer,
    )


def _grade_hunt(case: cases.Case, answer: transport.Answer) -> Outcome:
    """Grade a hunt answer: the file and the function, kept apart; a format miss is ``malformed``."""
    hit = scoring.score_hunt(answer.text, expected_file=case.bug.file, expected_function=case.bug.function)
    reason = scoring.hunt_reason(hit, expected_file=case.bug.file, expected_function=case.bug.function)
    if hit.malformed:
        verdict = "malformed"
    elif hit.hit:
        verdict, reason = "pass", "the answer names the file and the function that hold the defect"
    else:
        verdict = "fail"
    return Outcome(
        verdict=verdict,
        reason=reason,
        prompt_tokens=answer.usage.prompt_tokens,
        completion_tokens=answer.usage.completion_tokens,
        latency_s=answer.latency_s,
        answer=answer.text,
        location_hit=None if hit.malformed else hit.hit,
        file_hit=None if hit.malformed else hit.file_hit,
    )


def _grade_fix(case: cases.Case, answer: transport.Answer, run_test: sandbox.TestRunner) -> Outcome:
    """Grade a fix answer: the one block replaces the defective file and the hidden test must pass."""
    verdict = scoring.score_fix(answer.text, case, run_test)
    return Outcome(
        verdict="pass" if verdict.passed else "fail",
        reason=verdict.reason,
        prompt_tokens=answer.usage.prompt_tokens,
        completion_tokens=answer.usage.completion_tokens,
        latency_s=answer.latency_s,
        answer=answer.text,
    )


def _rate(passed: int, scored: int) -> float | None:
    """A rate over the scored attempts - ``None`` when nothing was scored."""
    if not scored:
        return None
    return passed / scored


def _median(values: Sequence[float]) -> float | None:
    """The median of a set of values - ``None`` when the set is empty."""
    if not values:
        return None
    return statistics.median(values)


def _count(attempts: Sequence[Attempt], verdict: str) -> int:
    return sum(1 for attempt in attempts if attempt.outcome.verdict == verdict)


def _metrics(cell: Sequence[Attempt]) -> dict[str, object]:
    """The metrics of one (model, family) cell.

    The pass rate is computed over the **scored** attempts only (``pass`` and ``fail``): a
    deferral and a malformed answer are each counted on their own line and never as a miss, so
    the rate stays a rate over answers that were really produced and well-formed. The latency
    median covers every attempt that called the model, because a timeout is a wall-clock fact
    about the model as much as a deferral.
    """
    scored = [attempt for attempt in cell if attempt.outcome.verdict in ("pass", "fail")]
    passed = _count(scored, "pass")
    called = [attempt for attempt in cell if attempt.outcome.reason != settings.load().run.budget_reason]
    metrics: dict[str, object] = {
        "n": len(cell),
        "scored": len(scored),
        "passed": passed,
        "failed": len(scored) - passed,
        "deferred": _count(cell, "deferred"),
        "malformed": _count(cell, "malformed"),
        "pass_rate": _rate(passed, len(scored)),
        "median_output_tokens": _median([attempt.outcome.completion_tokens for attempt in scored]),
        "median_input_tokens": _median([attempt.outcome.prompt_tokens for attempt in scored]),
        "median_latency_s": _median([attempt.outcome.latency_s for attempt in called]),
    }
    hunt = [attempt for attempt in scored if attempt.family == settings.load().families.hunt]
    if hunt:
        metrics["location_hit_rate"] = _rate(sum(1 for attempt in hunt if attempt.outcome.location_hit), len(hunt))
        metrics["file_localization_rate"] = _rate(sum(1 for attempt in hunt if attempt.outcome.file_hit), len(hunt))
    return metrics


def _gate_value(gate: settings.Gate, metrics: Mapping[str, object]) -> float | None:
    """The number a gate reads - ``None`` when the metric was never computed."""
    value = metrics.get(gate.metric)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _meets(gate: settings.Gate, value: float | None) -> bool:
    """Whether a value meets a gate's bar - an undefined value meets nothing."""
    if value is None:
        return False
    if gate.operator == ">=":
        return value >= gate.threshold
    return value <= gate.threshold


def _number(value: float | None) -> str:
    """A number as it is written in a failed gate."""
    return "n/a" if value is None else f"{value:g}"


def evaluate_gates(metrics: Mapping[str, object], family: str) -> list[str]:
    """The model gates this cell fails, each naming the gate, its number and what it means."""
    failed: list[str] = []
    for gate in settings.load().gates:
        if gate.family not in (None, family):
            continue
        value = _gate_value(gate, metrics)
        if not _meets(gate, value):
            failed.append(f"{gate.name} {_number(value)} {gate.operator} {_number(gate.threshold)} - {gate.meaning}")
    return failed


def item_bands(attempts: Sequence[Attempt]) -> tuple[ItemBandResult, ...]:
    """Where each (case, family) item sits against the item band, over the scored attempts of every model."""
    band = settings.load().item_band
    pools: dict[tuple[str, str], list[Attempt]] = {}
    for attempt in attempts:
        if attempt.outcome.verdict in ("pass", "fail"):
            pools.setdefault((attempt.case_id, attempt.family), []).append(attempt)
    results = []
    for (case_id, family), pool in pools.items():
        rate = _rate(_count(pool, "pass"), len(pool))
        if len(pool) < band.min_scored or rate is None:
            status: Literal["in_band", "outside_band", "pool_too_small"] = "pool_too_small"
        elif band.low <= rate <= band.high:
            status = "in_band"
        else:
            status = "outside_band"
        results.append(ItemBandResult(case_id, family, len(pool), rate, status))
    return tuple(results)


def _safe_name(name: str) -> str:
    """A name safe for a filename - a model id may carry a slash."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _detail_ref(model: str, family: str) -> str:
    """One (model, family) cell's detail file, relative to the run's output directory."""
    return f"{settings.load().run.detail_dir}/{_safe_name(model)}__{_safe_name(family)}.jsonl"


def _append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    """Append one JSON object to a file as a line, and push it to disk before returning."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class _Run:
    """The state of one run: what was asked, what it cost, and what has been written down."""

    def __init__(
        self,
        item_set: cases.ItemSet,
        channel: transport.Channel,
        options: RunOptions,
        stamp: datetime,
        run_test: sandbox.TestRunner,
    ) -> None:
        self._item_set = item_set
        self._channel = channel
        self._options = options
        self._stamp = stamp
        self._run_test = run_test
        self.attempts: list[Attempt] = []
        self.rows: list[dict[str, object]] = []
        self.detail_files: list[Path] = []
        self._spent: dict[str, int] = {}
        self._flushed: set[tuple[str, str]] = set()

    @property
    def ledger(self) -> Path:
        """Where the ledger rows go."""
        return self._options.out_dir / settings.load().run.ledger_file

    def step(self, model: str, case: cases.Case, family: str) -> None:
        """Ask one model one question, grade it, and write the attempt down before returning."""
        budget = self._options.token_budget
        if budget is not None and self._spent.get(model, 0) >= budget:
            outcome = _deferred(settings.load().run.budget_reason, transport.Usage(), 0.0)
            self._record(model, case, family, self._channel.variant(model).scaffold, outcome)
            return
        ask = case.ask(family)
        completion = self._channel.complete(model, ask.system, ask.user)
        scaffold = completion.variant.scaffold
        if isinstance(completion, transport.Deferral):
            self._record(
                model, case, family, scaffold, _deferred(completion.reason, completion.usage, completion.latency_s)
            )
            return
        try:
            if family == settings.load().families.hunt:
                outcome = _grade_hunt(case, completion)
            else:
                outcome = _grade_fix(case, completion, self._run_test)
        except sandbox.SandboxError as exc:
            # The model answered; the sandbox could not grade. Keep the answer and its cost, stop the run.
            outcome = _deferred(f"sandbox error: {exc}", completion.usage, completion.latency_s, completion.text)
            self._record(model, case, family, scaffold, outcome)
            raise
        self._record(model, case, family, scaffold, outcome)

    def _record(self, model: str, case: cases.Case, family: str, scaffold: str, outcome: Outcome) -> None:
        attempt = Attempt(
            model=model,
            case_id=case.id,
            family=family,
            scaffold=scaffold,
            envelope_sha=self._item_set.envelope_sha,
            cases_sha=self._item_set.cases_sha,
            seed=self._item_set.version,
            ts=self._stamp.isoformat(),
            outcome=outcome,
        )
        self.attempts.append(attempt)
        self._spent[model] = self._spent.get(model, 0) + outcome.prompt_tokens + outcome.completion_tokens
        _append_jsonl(self._options.out_dir / _detail_ref(model, family), attempt.as_dict())

    def flush_cells(self, *, complete: bool, models: Sequence[str] | None = None) -> None:
        """Append the ledger row of every not-yet-written cell (of ``models``, when given)."""
        cells: dict[tuple[str, str], list[Attempt]] = {}
        for attempt in self.attempts:
            if models is None or attempt.model in models:
                cells.setdefault((attempt.model, attempt.family), []).append(attempt)
        for key, cell in cells.items():
            if key in self._flushed:
                continue
            self._flushed.add(key)
            metrics = _metrics(cell)
            row = self._ledger_row(key, metrics, evaluate_gates(metrics, key[1]), complete=complete)
            self.rows.append(row)
            self.detail_files.append(self._options.out_dir / _detail_ref(*key))
            _append_jsonl(self.ledger, row)

    def _ledger_row(
        self, key: tuple[str, str], metrics: Mapping[str, object], failed: Sequence[str], *, complete: bool
    ) -> dict[str, object]:
        """One ledger row, keyed by (model, family) the way a score is looked up later.

        ``target`` is the harness the run was made under and ``stage`` is the probe family.
        """
        model, family = key
        variant = self._channel.variant(model)
        return {
            "date": self._stamp.date().isoformat(),
            "ts": self._stamp.isoformat(),
            "target": variant.scaffold,
            "model": model,
            "endpoint": self._channel.endpoint,
            "request": variant.as_dict(),
            "stage": family,
            "cases_sha": self._item_set.cases_sha,
            "system_sha": self._item_set.envelope_sha,
            "sufficient": complete and not failed,
            "complete": complete,
            "failed": list(failed),
            "metrics": dict(metrics),
            "detail": _detail_ref(model, family),
        }


def run_probe(
    item_set: cases.ItemSet,
    channel: transport.Channel,
    selection: Selection,
    options: RunOptions,
) -> RunReport:
    """Ask every model every selected item, grade the answers and write the ledger.

    The gold-sanity gate runs first over the whole selection: a case it refuses is never
    scored, and the run is refused with the refusal reported (``oracle.GateRefusalError``).
    The ledger rows go to ``<out_dir>/ledger.jsonl`` and each cell's attempts to
    ``<out_dir>/detail/<model>__<family>.jsonl``; both are appended as the run goes (see the
    module docstring), so an interrupted run keeps what it wrote and a second run adds to the
    record instead of replacing it.

    Raises:
        RunnerError: the selection holds nothing to ask.
        oracle.GateRefusalError: an item did not survive the gold-sanity gate.
        sandbox.SandboxError: the sandbox failed while grading; the rows so far are kept.
    """
    pairs = _selected_pairs(item_set, selection)
    if not pairs:
        raise RunnerError("nothing to ask: the selection holds no (case, family) pair")
    if not selection.models:
        raise RunnerError("nothing to ask: no model was named")
    grader = options.run_test or oracle.sandbox_runner(options.sandbox_timeout_s)
    selected = list(dict.fromkeys(case.id for case, _family in pairs))
    gate = oracle.run_gate(item_set, grader, case_ids=selected, families=selection.families)
    oracle.require_usable(gate)
    run = _Run(item_set, channel, options, (options.now or datetime.now(UTC)).astimezone(UTC), grader)
    try:
        for model in selection.models:
            for case, family in pairs:
                run.step(model, case, family)
            run.flush_cells(complete=True, models=[model])
    finally:
        run.flush_cells(complete=False)
    return RunReport(
        attempts=tuple(run.attempts),
        rows=tuple(run.rows),
        gate=gate,
        item_bands=item_bands(run.attempts),
        ledger=run.ledger,
        detail_files=tuple(run.detail_files),
    )
