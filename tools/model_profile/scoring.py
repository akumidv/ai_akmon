"""Grade one answer per family - pure rules, so a score can be re-derived from the answer.

The grading is mechanical on purpose: no judge sits in the score, and the same answer always
earns the same verdict. Each family has its own rule:

* **hunt** - the answer must be exactly one line, ``file.py:function_name``. A hit needs both
  the file and the function; the file's own correctness is recorded beside it, so a
  *localization* gap (the right file, the wrong function) is distinguishable from a *repair*
  gap. An answer that is not one such line is **malformed**: it is counted apart from a wrong
  location and is excluded from localization accuracy (see ``runner``), because a model that
  cannot follow the answer format has not been shown to be unable to localize. A location
  metric needs a scorer validated on human-labelled items before a localization gap is
  reported as a capability gap, which is why the scorer here is a pure function with labelled
  unit tests.
* **fix-traceback / fix-symptom** - the answer must carry exactly one fenced ```python block,
  and that block must compile; it is the corrected content of the file that holds the defect.
  The fix passes when the hidden test passes on the program with that one file replaced. An
  answer with no block, or a block that does not compile, is a **wrong answer** - never a
  deferral: the model answered, it answered badly. The answer replaces exactly one file, so
  "no other file changed" holds by construction and is not scored; a pass-to-pass check (other
  tests still passing) has no data in the item set and is not claimed.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

import cases
import sandbox

#: The one line a hunt answer must be: a Python file, a colon, a function name.
_LOCATION = re.compile(r"^(?P<file>[^\s:]+\.py):(?P<function>[A-Za-z_][A-Za-z0-9_]*)$")


@dataclass(frozen=True)
class LocationHit:
    """What a hunt answer named, and how much of it was right."""

    hit: bool
    file_hit: bool
    function_hit: bool
    malformed: bool
    file: str | None = None
    function: str | None = None


@dataclass(frozen=True)
class FixVerdict:
    """What a fix answer earned."""

    passed: bool
    reason: str
    compiled: bool = False
    failed_tests: tuple[str, ...] = ()


def parse_location(answer: str) -> tuple[str, str] | None:
    """The ``(file, function)`` a hunt answer names - ``None`` when it is not one clean line."""
    text = answer.strip()
    if not text or "\n" in text:
        return None
    match = _LOCATION.match(text)
    if match is None:
        return None
    return match.group("file"), match.group("function")


def score_hunt(answer: str, *, expected_file: str, expected_function: str) -> LocationHit:
    """Grade a hunt answer against the case's defect - the file's correctness is kept apart."""
    parsed = parse_location(answer)
    if parsed is None:
        return LocationHit(hit=False, file_hit=False, function_hit=False, malformed=True)
    file, function = parsed
    file_hit = file == expected_file
    function_hit = function == expected_function
    return LocationHit(
        hit=file_hit and function_hit,
        file_hit=file_hit,
        function_hit=function_hit,
        malformed=False,
        file=file,
        function=function,
    )


def hunt_reason(hit: LocationHit, *, expected_file: str, expected_function: str) -> str:
    """Why a hunt answer missed - a localization gap and a wrong file read differently."""
    if hit.malformed:
        return "the answer is not one line of the form file.py:function_name"
    if hit.file_hit and not hit.function_hit:
        return (
            f"the right file, the wrong function ({hit.function} instead of "
            f"{expected_function}) - a localization gap, not a repair one"
        )
    return f"named {hit.file}:{hit.function}, the defect is in {expected_file}:{expected_function}"


def score_fix(answer: str, case: cases.Case, run_test: sandbox.TestRunner) -> FixVerdict:
    """Grade a fix answer: the one fenced block replaces the defective file, the hidden test must pass."""
    block = sandbox.extract_python_block(answer)
    if block is None:
        return FixVerdict(passed=False, reason="the answer carries no single fenced ```python block")
    try:
        ast.parse(block)
    except (SyntaxError, ValueError) as exc:
        return FixVerdict(passed=False, reason=f"the fenced block does not compile: {exc}")
    patched = case.program()
    patched[case.bug.file] = block
    result = run_test(patched, case.hidden_test.path, case.hidden_test.content)
    if not result.passed:
        failed = ", ".join(result.failed_tests) or "the test file broke"
        return FixVerdict(
            passed=False,
            reason=f"the hidden test still fails ({failed})",
            compiled=True,
            failed_tests=result.failed_tests,
        )
    return FixVerdict(passed=True, reason="the hidden test passes", compiled=True)
