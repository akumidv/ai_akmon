"""The gold-sanity gate: a hidden test must fail on the buggy program and pass on the fixed one.

A weak oracle accepts wrong patches, and it inflates the cheap models most - inverting the
ladder this suite exists to build. So no item is asked of any model before the runner has
proved, on that item itself, that its hidden test separates the buggy program from the fixed
one.

A case that fails either leg is **refused and reported**, never scored and never dropped
quietly: the refusal names the case, so a broken item set is visible instead of quietly
shortening the run. The refusal is also never the model's failure - a case the gate refuses is
not a case any model is asked about.

The third leg of the rule - the test must also pass on the *unmutated* original - has no data
in the item set (it carries the buggy program and its fixed twin, not the original), so this
gate implements the two legs the set can express and says so in the report.

This is the **oracle gate** on items. It is not one of the model ``gates`` and not the
``item_band`` of ``profile.json``; the module docstring of ``runner`` says which is which.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cases
import sandbox


class GateRefusalError(RuntimeError):
    """The item set did not survive the gold-sanity gate - the run is refused, not scored."""


@dataclass(frozen=True)
class GateOutcome:
    """What the gate found for one case."""

    case_id: str
    usable: bool
    reason: str


@dataclass(frozen=True)
class GateReport:
    """The gate's verdict over a set of cases."""

    outcomes: tuple[GateOutcome, ...]

    @property
    def usable_case_ids(self) -> tuple[str, ...]:
        """The ids of the cases the gate accepted."""
        return tuple(outcome.case_id for outcome in self.outcomes if outcome.usable)

    @property
    def refused(self) -> tuple[GateOutcome, ...]:
        """The cases the gate refused, with the reason each was refused."""
        return tuple(outcome for outcome in self.outcomes if not outcome.usable)

    @property
    def ok(self) -> bool:
        """Whether every case survived the gate."""
        return not self.refused


def check_case(case: cases.Case, run_test: sandbox.TestRunner) -> GateOutcome:
    """The gate's verdict for one case: the hidden test must fail on the bug and pass on the fix."""
    buggy = run_test(case.program(), case.hidden_test.path, case.hidden_test.content)
    if buggy.passed:
        return GateOutcome(
            case_id=case.id,
            usable=False,
            reason=(
                "the hidden test passes on the buggy program - it does not separate the "
                "defect, so it would accept a wrong patch"
            ),
        )
    fixed = run_test(case.fixed_program(), case.hidden_test.path, case.hidden_test.content)
    if not fixed.passed:
        failed = ", ".join(fixed.failed_tests) or "the test file itself broke"
        return GateOutcome(
            case_id=case.id,
            usable=False,
            reason=f"the hidden test does not pass on the fixed program ({failed})",
        )
    return GateOutcome(
        case_id=case.id,
        usable=True,
        reason="the hidden test fails on the buggy program and passes on the fixed one",
    )


def sandbox_runner(timeout_s: int | None = None) -> sandbox.TestRunner:
    """The runner that grades in the container - the hidden test travels in as a file."""

    def run(files: dict[str, str], test_path: str, test_source: str) -> sandbox.SandboxResult:
        return sandbox.run_hidden_test(files, test_path, timeout_s=timeout_s, extra_files={test_path: test_source})

    return run


def run_gate(
    item_set: cases.ItemSet,
    run_test: sandbox.TestRunner,
    *,
    case_ids: Sequence[str] | None = None,
    families: Sequence[str] | None = None,
) -> GateReport:
    """Run the gate over the item set's cases with ``run_test`` and report each one."""
    outcomes = tuple(check_case(case, run_test) for case in item_set.select(case_ids, families))
    return GateReport(outcomes=outcomes)


def require_usable(report: GateReport) -> None:
    """Raise when any case was refused - a refused case is never scored silently.

    Raises:
        GateRefusalError: at least one case did not survive the gate.
    """
    if report.ok:
        return
    lines = "\n".join(f"  {outcome.case_id}: {outcome.reason}" for outcome in report.refused)
    raise GateRefusalError(
        f"{len(report.refused)} case(s) did not survive the gold-sanity gate, so no model is asked about them:\n{lines}"
    )
