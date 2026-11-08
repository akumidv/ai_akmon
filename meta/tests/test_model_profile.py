"""Tests for the model-profile probe (``tools/model_profile/``).

Nothing here needs the network, a credential or a container daemon: the sandbox is replaced by
a stub that answers with a canned verdict, the endpoint by a channel that returns canned
completions or a fake opener that yields canned streams, and the docker flags are pinned by
asserting on the argv that would be run. The in-container runner is exercised for real with the
host interpreter in a temporary directory. The one test that needs a running daemon carries the
``docker`` marker and is skipped when ``docker version`` fails.
"""

from __future__ import annotations

import http.client
import importlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_PROFILE = _AKMON / "tools" / "model_profile"
_TOOL_MODULES = ("settings", "cases", "sandbox", "scoring", "oracle", "transport", "runner", "cli")


def _import_tool() -> dict[str, ModuleType]:
    """Import the tool's modules by the bare names they use among themselves, then forget the names.

    The modules import each other by bare name (the way a script run by path does). Other
    suites own a bare ``runner``, so the names are registered only while the tool is imported
    and then handed back, leaving ``sys.modules`` as it was.
    """
    saved = {name: sys.modules.pop(name) for name in _TOOL_MODULES if name in sys.modules}
    sys.path.insert(0, str(_PROFILE))
    try:
        return {name: importlib.import_module(name) for name in _TOOL_MODULES}
    finally:
        sys.path.remove(str(_PROFILE))
        for name in _TOOL_MODULES:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


_MODULES = _import_tool()
settings = _MODULES["settings"]
cases = _MODULES["cases"]
sandbox = _MODULES["sandbox"]
scoring = _MODULES["scoring"]
oracle = _MODULES["oracle"]
transport = _MODULES["transport"]
runner = _MODULES["runner"]
cli = _MODULES["cli"]

_STAMP = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

#: The defective file of the fixture case, in its buggy and in its fixed form.
_BUGGY_SOURCE = "def compute(x):\n    return x + 1\n"
_FIXED_SOURCE = "def compute(x):\n    return x\n"
_FIX_ANSWER = f"```python\n{_FIXED_SOURCE}```\n"


def _case(case_id: str = "fixture-case", family: str = "hunt") -> cases.Case:
    """A one-item case: a buggy program, a decoy, its fixed twin, an oracle and one ask."""
    return cases.Case(
        id=case_id,
        families=(family,),
        bug=cases.Bug(file="pkg/mod.py", function="compute", kind="off-by-one"),
        files={"pkg/mod.py": _BUGGY_SOURCE, "pkg/decoy.py": "def other():\n    return 0\n"},
        fixed_files={"pkg/mod.py": _FIXED_SOURCE},
        hidden_test=cases.HiddenTest(
            path="tests/test_mod.py",
            content="def test_compute():\n    assert compute(1) == 1\n",
        ),
        asks={family: cases.Ask(system="Name the defect.", user="Where is the defect?")},
    )


def _item_set(*case_list: cases.Case) -> cases.ItemSet:
    """An item set over the given cases - the hashes are what the ledger row carries."""
    return cases.ItemSet(
        version="fixture-1",
        cases=tuple(case_list),
        cases_sha="cases-sha",
        envelope_sha="envelope-sha",
        families=tuple(sorted({family for case in case_list for family in case.families})),
    )


def _never_run(files, test_path, test_source) -> sandbox.SandboxResult:
    """A sandbox stub that refuses to run - the container is never reached from a unit test."""
    raise AssertionError("the container sandbox must not be reached from a unit test")


def _always_fails(files, test_path, test_source) -> sandbox.SandboxResult:
    """A sandbox stub whose hidden test fails, whatever program it is given."""
    return sandbox.SandboxResult(passed=False, tests={"test_compute": "failed"})


def _separating_runner(files, test_path, test_source) -> sandbox.SandboxResult:
    """A sandbox stub that separates the two programs, as a real hidden test does."""
    buggy = _BUGGY_SOURCE in files["pkg/mod.py"]
    return sandbox.SandboxResult(passed=not buggy, tests={"test_compute": "failed" if buggy else "passed"})


def _variant(model: str = "probe-model") -> transport.RequestVariant:
    return transport.RequestVariant(
        model=model, temperature=0.0, max_output_tokens=4096, timeout_s=180, scaffold="direct"
    )


def _answer(text: str, *, prompt_tokens: int = 10, completion_tokens: int = 5) -> transport.Answer:
    return transport.Answer(
        text=text,
        usage=transport.Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        latency_s=1.0,
        variant=_variant(),
    )


def _deferral(reason: str = "the endpoint could not be reached", **usage: int) -> transport.Deferral:
    return transport.Deferral(reason=reason, latency_s=0.5, variant=_variant(), usage=transport.Usage(**usage))


class _StubChannel:
    """A channel that returns what a script says - no socket, no token."""

    endpoint = "https://endpoint.example/v1/chat/completions"

    def __init__(self, script) -> None:
        self._script = script
        self.calls: list[str] = []

    def variant(self, model: str) -> transport.RequestVariant:
        return _variant(model)

    def complete(self, model: str, system: str, user: str) -> transport.Completion:
        self.calls.append(model)
        return self._script(model, len(self.calls))


def _options(tmp_path: Path, **overrides) -> runner.RunOptions:
    return runner.RunOptions(out_dir=tmp_path / "out", run_test=_separating_runner, now=_STAMP, **overrides)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------------------
# The shared data: profile.json and the in-container runner's source
# --------------------------------------------------------------------------------------


def test_the_settings_are_read_once_from_the_data_file_next_to_the_code() -> None:
    loaded = settings.load()

    assert settings.load() is loaded
    assert loaded.hash_length == 12
    assert loaded.families.known == ("hunt", "fix-traceback", "fix-symptom")
    assert loaded.sandbox.image == "python:3.13-slim"
    assert loaded.sandbox.docker_failure_codes == (125, 126, 127)


def test_every_key_of_the_data_file_is_read_by_a_settings_field() -> None:
    """Nothing in ``profile.json`` is dead, and nothing the code reads is missing from it."""
    document = json.loads((_PROFILE / "profile.json").read_text(encoding="utf-8"))
    loaded = settings.load()

    assert set(document) == set(vars(loaded))
    for section, value in document.items():
        if isinstance(value, dict):
            assert set(value) == set(vars(getattr(loaded, section))), section


def test_the_in_container_runner_is_the_shared_file_and_a_python_program() -> None:
    source = settings.runner_source()

    assert source == (_PROFILE / settings.load().sandbox.runner_source_file).read_text(encoding="utf-8")
    compile(source, settings.load().sandbox.runner_file, "exec")
    assert settings.runner_source() is source


def test_a_missing_or_broken_data_file_raises_one_named_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings.load.cache_clear()
    monkeypatch.setattr(settings, "_HERE", tmp_path)
    try:
        with pytest.raises(settings.SettingsError, match="cannot be read"):
            settings.load()
        (tmp_path / settings.PROFILE_FILE).write_text("{nope", encoding="utf-8")
        with pytest.raises(settings.SettingsError, match="not valid JSON"):
            settings.load()
        (tmp_path / settings.PROFILE_FILE).write_text("{}", encoding="utf-8")
        with pytest.raises(settings.SettingsError, match="no 'families' object"):
            settings.load()
    finally:
        settings.load.cache_clear()


# --------------------------------------------------------------------------------------
# The oracle gate
# --------------------------------------------------------------------------------------


def test_the_gate_refuses_a_case_whose_fixed_program_fails_its_hidden_test() -> None:
    """A gold answer that does not pass its own hidden test is refused and named, never scored."""
    report = oracle.run_gate(_item_set(_case("broken-gold")), _always_fails)

    assert not report.ok
    assert report.usable_case_ids == ()
    assert [outcome.case_id for outcome in report.refused] == ["broken-gold"]
    assert "does not pass on the fixed program" in report.refused[0].reason
    with pytest.raises(oracle.GateRefusalError, match="broken-gold"):
        oracle.require_usable(report)


def test_the_gate_accepts_a_case_whose_hidden_test_separates_the_two_programs() -> None:
    report = oracle.run_gate(_item_set(_case("good-gold")), _separating_runner)

    assert report.ok
    assert report.usable_case_ids == ("good-gold",)
    oracle.require_usable(report)


def test_the_gate_refuses_a_test_that_passes_on_the_bug() -> None:
    def passes_everywhere(files, test_path, test_source):
        return sandbox.SandboxResult(passed=True, tests={"test_compute": "passed"})

    report = oracle.run_gate(_item_set(_case("weak-oracle")), passes_everywhere)

    assert [outcome.case_id for outcome in report.refused] == ["weak-oracle"]
    assert "passes on the buggy program" in report.refused[0].reason


def test_a_refused_case_stops_the_run_before_any_model_is_asked(tmp_path: Path) -> None:
    channel = _StubChannel(lambda model, call: _answer("pkg/mod.py:compute"))
    options = runner.RunOptions(out_dir=tmp_path / "out", run_test=_always_fails, now=_STAMP)

    with pytest.raises(oracle.GateRefusalError):
        runner.run_probe(_item_set(_case()), channel, runner.Selection(models=("m",)), options)

    assert channel.calls == []
    assert not (tmp_path / "out").exists()


# --------------------------------------------------------------------------------------
# Scoring: the hunt scorer, malformed answers, the fix grader
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [  # expected: (hit, file_hit, function_hit, malformed)
        ("pkg/mod.py:compute", (True, True, True, False)),
        ("pkg/mod.py:other", (False, True, False, False)),
        ("other/mod.py:compute", (False, False, True, False)),
        ("pkg/mod.py", (False, False, False, True)),
        ("pkg/mod.py:compute\nexplains itself", (False, False, False, True)),
        ("I think it is pkg/mod.py:compute", (False, False, False, True)),
        ("", (False, False, False, True)),
    ],
)
def test_the_hunt_scorer_decides_a_hit_against_the_expected_location(
    answer: str, expected: tuple[bool, bool, bool, bool]
) -> None:
    """The right file with the wrong function is a localization gap, kept apart from a wrong file."""
    graded = scoring.score_hunt(answer, expected_file="pkg/mod.py", expected_function="compute")

    assert (graded.hit, graded.file_hit, graded.function_hit, graded.malformed) == expected


def test_parse_location_reads_one_line_of_the_agreed_form() -> None:
    assert scoring.parse_location("pkg/mod.py:compute") == ("pkg/mod.py", "compute")
    assert scoring.parse_location("  pkg/mod.py:compute\n") == ("pkg/mod.py", "compute")
    assert scoring.parse_location("pkg/mod.py") is None
    assert scoring.parse_location("pkg/mod.py:compute and more") is None
    assert scoring.parse_location("") is None


def test_a_malformed_hunt_answer_is_counted_apart_and_left_out_of_the_localization_rates(tmp_path: Path) -> None:
    """Not one ``file.py:function`` line is ``malformed``: its own count, not a wrong location, not in the rates."""
    cases_ = [_case(f"case-{index}") for index in range(3)]
    answers = {
        "case-0": "pkg/mod.py:compute",  # a hit
        "case-1": "pkg/mod.py:other",  # a wrong location
        "case-2": "The defect is in pkg/mod.py, function compute.",  # malformed
    }
    calls: list[str] = []

    def script(model: str, call: int) -> transport.Completion:
        calls.append(model)
        return _answer(answers[f"case-{call - 1}"])

    report = runner.run_probe(
        _item_set(*cases_), _StubChannel(script), runner.Selection(models=("m",)), _options(tmp_path)
    )

    verdicts = {attempt.case_id: attempt.outcome.verdict for attempt in report.attempts}
    assert verdicts == {"case-0": "pass", "case-1": "fail", "case-2": "malformed"}
    malformed = next(attempt for attempt in report.attempts if attempt.case_id == "case-2")
    assert malformed.outcome.location_hit is None
    metrics = report.rows[0]["metrics"]
    assert metrics["malformed"] == 1
    assert metrics["scored"] == 2
    assert metrics["location_hit_rate"] == 0.5  # 1 of the 2 well-formed answers; the malformed one is not in it
    assert metrics["file_localization_rate"] == 1.0


def test_the_fix_grader_runs_the_hidden_test_on_the_one_replaced_file_and_leaves_the_others_alone() -> None:
    """The sandbox is handed the case's files with only the defective one replaced - byte for byte."""
    case = _case(family="fix-traceback")
    seen: list[dict[str, str]] = []

    def recording(files, test_path, test_source):
        seen.append(dict(files))
        return sandbox.SandboxResult(passed=True, tests={"test_compute": "passed"})

    verdict = scoring.score_fix(_FIX_ANSWER, case, recording)

    assert verdict.passed
    assert len(seen) == 1
    assert seen[0]["pkg/mod.py"] == _FIXED_SOURCE
    assert {path: source for path, source in seen[0].items() if path != "pkg/mod.py"} == {
        path: source for path, source in case.files.items() if path != "pkg/mod.py"
    }
    assert not hasattr(verdict, "unchanged_others")  # "others unchanged" is by construction, not scored


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("no code at all", "no single fenced"),
        (f"{_FIX_ANSWER}{_FIX_ANSWER}", "no single fenced"),
        ("```python\ndef broken(:\n```\n", "does not compile"),
    ],
)
def test_a_fix_answer_without_a_usable_block_is_a_wrong_answer_not_a_deferral(answer: str, reason: str) -> None:
    verdict = scoring.score_fix(answer, _case(family="fix-traceback"), _never_run)

    assert not verdict.passed
    assert reason in verdict.reason


# --------------------------------------------------------------------------------------
# The runner: deferrals, the ledger, the detail rows
# --------------------------------------------------------------------------------------


def test_a_deferral_is_never_scored_as_a_miss(tmp_path: Path) -> None:
    """A deferral is counted on its own line, so the pass rate stays a rate over real answers."""
    cases_ = [_case(f"case-{index}") for index in range(3)]
    plan = {1: _answer("pkg/mod.py:compute"), 2: _deferral(), 3: _deferral()}
    channel = _StubChannel(lambda model, call: plan[call])

    report = runner.run_probe(_item_set(*cases_), channel, runner.Selection(models=("m",)), _options(tmp_path))

    assert [attempt.outcome.verdict for attempt in report.attempts] == ["pass", "deferred", "deferred"]
    metrics = report.rows[0]["metrics"]
    assert (metrics["pass_rate"], metrics["scored"], metrics["deferred"], metrics["n"]) == (1.0, 1, 2, 3)
    failed = runner.evaluate_gates(metrics, "hunt")
    assert [gate for gate in failed if gate.startswith("items_scored")]
    assert not [gate for gate in failed if gate.startswith("hunt.location_hit")]


def test_a_deferral_keeps_the_usage_the_stream_reported(tmp_path: Path) -> None:
    """A deferral still cost tokens - the attempt records them instead of zeroing them."""
    deferral = _deferral("the answer was cut off by the 4096-token cap", prompt_tokens=1091, completion_tokens=4096)
    channel = _StubChannel(lambda model, call: deferral)

    report = runner.run_probe(_item_set(_case()), channel, runner.Selection(models=("m",)), _options(tmp_path))

    outcome = report.attempts[0].outcome
    assert outcome.verdict == "deferred"
    assert (outcome.prompt_tokens, outcome.completion_tokens) == (1091, 4096)


def test_the_detail_row_carries_the_answer_the_model_produced(tmp_path: Path) -> None:
    """The answer is kept, so the verdict can be re-derived by someone other than the runner."""
    plan = {1: _answer("pkg/mod.py:compute"), 2: _deferral()}
    channel = _StubChannel(lambda model, call: plan[call])

    report = runner.run_probe(
        _item_set(_case("a"), _case("b")), channel, runner.Selection(models=("m",)), _options(tmp_path)
    )

    rows = _read_jsonl(report.detail_files[0])
    assert [(row["verdict"], row["answer"]) for row in rows] == [("pass", "pkg/mod.py:compute"), ("deferred", "")]


def test_the_ledger_row_carries_the_agreed_keys(tmp_path: Path) -> None:
    channel = _StubChannel(lambda model, call: _answer("pkg/mod.py:compute"))

    report = runner.run_probe(
        _item_set(_case()), channel, runner.Selection(models=("probe/model",)), _options(tmp_path)
    )

    row = _read_jsonl(report.ledger)[0]
    assert set(row) == {
        "date", "ts", "target", "model", "endpoint", "request", "stage", "cases_sha", "system_sha",
        "sufficient", "complete", "failed", "metrics", "detail",
    }  # fmt: skip
    assert row["date"] == "2026-03-01"
    assert row["ts"] == _STAMP.isoformat()
    assert row["target"] == "direct"
    assert row["endpoint"] == "https://endpoint.example/v1/chat/completions"
    assert row["request"]["model"] == "probe/model"
    assert row["stage"] == "hunt"
    assert (row["cases_sha"], row["system_sha"]) == ("cases-sha", "envelope-sha")
    assert row["complete"] is True
    assert row["detail"] == "detail/probe_model__hunt.jsonl"
    assert (tmp_path / "out" / row["detail"]).is_file()
    assert "items_scored" in row["failed"][0]  # one scored item is far under the 30 the gate wants
    assert row["sufficient"] is False


# --------------------------------------------------------------------------------------
# (a) a crash keeps what was written
# --------------------------------------------------------------------------------------


def test_a_crash_midway_keeps_every_finished_attempt_and_the_partial_ledger_row(tmp_path: Path) -> None:
    """Ctrl-C on the third call: the two finished attempts are on disk and the cell's row says incomplete."""

    def script(model: str, call: int) -> transport.Completion:
        if call == 3:
            raise KeyboardInterrupt
        return _answer("pkg/mod.py:compute")

    items = _item_set(_case("a"), _case("b"), _case("c"))
    with pytest.raises(KeyboardInterrupt):
        runner.run_probe(items, _StubChannel(script), runner.Selection(models=("m",)), _options(tmp_path))

    detail = _read_jsonl(tmp_path / "out" / "detail" / "m__hunt.jsonl")
    assert [row["case_id"] for row in detail] == ["a", "b"]
    ledger = _read_jsonl(tmp_path / "out" / "ledger.jsonl")
    assert [(row["model"], row["complete"], row["sufficient"]) for row in ledger] == [("m", False, False)]
    assert ledger[0]["metrics"]["scored"] == 2


def test_a_sandbox_failure_keeps_the_answer_it_could_not_grade_and_stops_the_run(tmp_path: Path) -> None:
    """The model answered and was paid for; the sandbox broke: the answer is kept as a deferral, the run stops."""
    calls = {"count": 0}

    def flaky(files, test_path, test_source):
        calls["count"] += 1
        if calls["count"] == 8:  # the gate takes two runs for each of the three cases; 7 grades "a", 8 grades "b"
            raise sandbox.SandboxError("docker failed")
        return _separating_runner(files, test_path, test_source)

    channel = _StubChannel(lambda model, call: _answer(_FIX_ANSWER))
    items = _item_set(_case("a", "fix-symptom"), _case("b", "fix-symptom"), _case("c", "fix-symptom"))
    options = runner.RunOptions(out_dir=tmp_path / "out", run_test=flaky, now=_STAMP)

    with pytest.raises(sandbox.SandboxError):
        runner.run_probe(items, channel, runner.Selection(models=("m",)), options)

    detail = _read_jsonl(tmp_path / "out" / "detail" / "m__fix-symptom.jsonl")
    assert [(row["case_id"], row["verdict"]) for row in detail] == [("a", "pass"), ("b", "deferred")]
    assert detail[1]["answer"] == _FIX_ANSWER
    assert "sandbox error" in detail[1]["reason"]
    assert channel.calls == ["m", "m"]
    assert _read_jsonl(tmp_path / "out" / "ledger.jsonl")[0]["complete"] is False


def test_a_second_run_into_the_same_directory_appends(tmp_path: Path) -> None:
    channel = _StubChannel(lambda model, call: _answer("pkg/mod.py:compute"))
    selection = runner.Selection(models=("m",))

    runner.run_probe(_item_set(_case()), channel, selection, _options(tmp_path))
    runner.run_probe(_item_set(_case()), channel, selection, _options(tmp_path))

    assert len(_read_jsonl(tmp_path / "out" / "ledger.jsonl")) == 2
    assert len(_read_jsonl(tmp_path / "out" / "detail" / "m__hunt.jsonl")) == 2


# --------------------------------------------------------------------------------------
# (e) the per-model token budget
# --------------------------------------------------------------------------------------


def test_the_token_budget_defers_a_models_remaining_attempts_with_the_reason_budget(tmp_path: Path) -> None:
    """Each answer costs 100 tokens; with a 150 budget a model gets two calls and the rest are deferred."""
    channel = _StubChannel(lambda model, call: _answer("pkg/mod.py:compute", prompt_tokens=60, completion_tokens=40))
    items = _item_set(*(_case(f"case-{index}") for index in range(4)))

    report = runner.run_probe(
        items, channel, runner.Selection(models=("m1", "m2")), _options(tmp_path, token_budget=150)
    )

    assert channel.calls == ["m1", "m1", "m2", "m2"]  # the budget is per model
    by_model = {
        model: [
            (attempt.outcome.verdict, attempt.outcome.reason) for attempt in report.attempts if attempt.model == model
        ]
        for model in ("m1", "m2")
    }
    skipped = ("deferred", settings.load().run.budget_reason)
    assert settings.load().run.budget_reason == "budget"
    for model in ("m1", "m2"):
        assert [verdict for verdict, _reason in by_model[model]] == ["pass", "pass", "deferred", "deferred"]
        assert by_model[model][2:] == [skipped, skipped]
    row = next(row for row in report.rows if row["model"] == "m1")
    assert row["metrics"]["deferred"] == 2
    assert row["metrics"]["scored"] == 2


def test_a_deferrals_spend_counts_against_the_budget(tmp_path: Path) -> None:
    channel = _StubChannel(lambda model, call: _deferral("cut off", prompt_tokens=100, completion_tokens=4096))
    items = _item_set(_case("a"), _case("b"))

    report = runner.run_probe(items, channel, runner.Selection(models=("m",)), _options(tmp_path, token_budget=1000))

    assert channel.calls == ["m"]
    assert [attempt.outcome.reason for attempt in report.attempts] == ["cut off", settings.load().run.budget_reason]


def test_without_a_budget_nothing_is_skipped(tmp_path: Path) -> None:
    channel = _StubChannel(lambda model, call: _answer("pkg/mod.py:compute", prompt_tokens=10**6))
    items = _item_set(_case("a"), _case("b"))

    report = runner.run_probe(items, channel, runner.Selection(models=("m",)), _options(tmp_path))

    assert channel.calls == ["m", "m"]
    assert {attempt.outcome.verdict for attempt in report.attempts} == {"pass"}


# --------------------------------------------------------------------------------------
# (f) the model gates and the item-selection band
# --------------------------------------------------------------------------------------


def test_the_model_gates_are_declared_data_in_one_place() -> None:
    bars = {gate.name: (gate.family, gate.metric, gate.operator, gate.threshold) for gate in settings.load().gates}
    assert bars == {
        "items_scored": (None, "scored", ">=", 30.0),
        "hunt.location_hit": ("hunt", "location_hit_rate", ">=", 0.5),
        "hunt.file_localization": ("hunt", "file_localization_rate", ">=", 0.5),
        "fix-traceback.pass_rate": ("fix-traceback", "pass_rate", ">=", 0.5),
        "fix-symptom.pass_rate": ("fix-symptom", "pass_rate", ">=", 0.5),
    }


def test_a_failed_model_gate_names_itself_its_number_and_what_it_means() -> None:
    failed = runner.evaluate_gates({"scored": 40, "location_hit_rate": 0.4, "file_localization_rate": 0.9}, "hunt")

    assert failed == [
        "hunt.location_hit 0.4 >= 0.5 - the model cannot name the file and the function that hold the defect"
    ]
    assert runner.evaluate_gates({"scored": 40, "pass_rate": 0.5}, "fix-symptom") == []
    assert runner.evaluate_gates({"scored": 40}, "fix-symptom")[0].startswith("fix-symptom.pass_rate n/a")


def _scored(case_id: str, model: str, verdict: str, family: str = "hunt") -> runner.Attempt:
    return runner.Attempt(
        model=model,
        case_id=case_id,
        family=family,
        scaffold="direct",
        envelope_sha="e",
        cases_sha="c",
        seed="s",
        ts=_STAMP.isoformat(),
        outcome=runner.Outcome(verdict=verdict, reason="r"),
    )


def test_the_item_band_is_a_separate_gate_from_the_model_bars() -> None:
    band = settings.load().item_band
    assert (band.name, band.low, band.high) == ("item_pass_band", 0.30, 0.70)
    assert band.name not in {gate.name for gate in settings.load().gates}


def test_item_bands_flag_an_item_every_model_passes_or_fails_and_keep_the_discriminating_one() -> None:
    models = ("m1", "m2", "m3", "m4")
    attempts = [
        *(_scored("easy", model, "pass") for model in models),
        *(_scored("hard", model, "fail") for model in models),
        *(_scored("mid", model, "pass" if index < 2 else "fail") for index, model in enumerate(models)),
        *(_scored("edge", model, "pass" if index < 3 else "fail") for index, model in enumerate(models)),  # 0.75
        _scored("thin", "m1", "pass"),
        _scored("thin", "m2", "pass"),
        _scored("thin", "m3", "deferred"),  # a deferral is not scored
    ]

    bands = {band.case_id: (band.status, band.pass_rate) for band in runner.item_bands(attempts)}

    assert bands == {
        "easy": ("outside_band", 1.0),
        "hard": ("outside_band", 0.0),
        "mid": ("in_band", 0.5),
        "edge": ("outside_band", 0.75),
        "thin": ("pool_too_small", 1.0),
    }


def test_the_band_edges_are_inclusive() -> None:
    ten = [_scored("low", f"m{index}", "pass" if index < 3 else "fail") for index in range(10)]
    ten += [_scored("high", f"m{index}", "pass" if index < 7 else "fail") for index in range(10)]

    assert {band.case_id: band.status for band in runner.item_bands(ten)} == {"low": "in_band", "high": "in_band"}


def test_a_run_reports_the_item_bands(tmp_path: Path) -> None:
    channel = _StubChannel(lambda model, call: _answer("pkg/mod.py:compute"))

    report = runner.run_probe(_item_set(_case()), channel, runner.Selection(models=("m",)), _options(tmp_path))

    assert [(band.case_id, band.status) for band in report.item_bands] == [("fixture-case", "pool_too_small")]


# --------------------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------------------


def test_the_plan_counts_calls_and_prices_the_sandbox_for_fix_families_only() -> None:
    items = _item_set(_case("a", "hunt"), _case("b", "fix-symptom"))

    plan = runner.build_plan(items, runner.Selection(models=("m1", "m2")))

    assert plan.pairs == (("a", "hunt"), ("b", "fix-symptom"))
    assert plan.calls == 4
    expected_seconds = 4 * settings.load().estimate.call_seconds + 2 * settings.load().estimate.sandbox_seconds
    assert plan.estimated_minutes == round(expected_seconds / 60, 1)
    assert plan.estimated_output_tokens == 4 * settings.load().estimate.output_tokens
    narrowed = runner.build_plan(items, runner.Selection(models=("m",), families=("hunt",)))
    assert narrowed.pairs == (("a", "hunt"),)


def test_an_empty_selection_is_refused(tmp_path: Path) -> None:
    channel = _StubChannel(lambda model, call: _answer("x"))
    with pytest.raises(runner.RunnerError, match="no model"):
        runner.run_probe(_item_set(_case()), channel, runner.Selection(models=()), _options(tmp_path))
    with pytest.raises(runner.RunnerError, match=r"no \(case, family\) pair"):
        runner.run_probe(
            _item_set(_case()), channel, runner.Selection(models=("m",), families=("fix-symptom",)), _options(tmp_path)
        )


# --------------------------------------------------------------------------------------
# The transport: a failure to deliver is a deferral
# --------------------------------------------------------------------------------------


class _StubStream:
    """A response that yields the given SSE lines, then optionally fails - the socket is never opened."""

    def __init__(self, lines: list[str], then: BaseException | None = None) -> None:
        self._lines = list(lines)
        self._then = then

    def __enter__(self) -> _StubStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def __iter__(self):
        yield from (line.encode("utf-8") for line in self._lines)
        if self._then is not None:
            raise self._then


def _sse(payload: dict[str, object]) -> str:
    return "data: " + json.dumps(payload) + "\n"


def _channel(opener) -> transport.EndpointChannel:
    return transport.EndpointChannel(
        transport.EndpointConfig(base_url="https://endpoint.example", token="fixture-token"), opener
    )


_PARTIAL = [_sse({"choices": [{"delta": {"content": "partial answer"}}]})]


def test_the_cut_off_path_reports_the_usage_it_read() -> None:
    lines = [
        *_PARTIAL,
        _sse({"choices": [{"delta": {}, "finish_reason": "length"}]}),
        _sse({"choices": [], "usage": {"prompt_tokens": 1200, "completion_tokens": 4096}}),
    ]

    completion = _channel(lambda request, timeout: _StubStream(lines)).complete("probe-model", "system", "user")

    assert isinstance(completion, transport.Deferral)
    assert completion.usage == transport.Usage(prompt_tokens=1200, completion_tokens=4096)
    assert "cut off" in completion.reason


def test_a_complete_stream_is_an_answer_with_its_usage() -> None:
    lines = [
        *_PARTIAL,
        _sse({"choices": [{"delta": {"content": " done"}, "finish_reason": "stop"}]}),
        _sse({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}),
        "data: [DONE]\n",
    ]

    completion = _channel(lambda request, timeout: _StubStream(lines)).complete("m", "s", "u")

    assert isinstance(completion, transport.Answer)
    assert completion.text == "partial answer done"
    assert completion.usage == transport.Usage(prompt_tokens=7, completion_tokens=3)


def test_the_request_pins_the_envelope_and_streams() -> None:
    seen = {}

    def opener(request, timeout):
        seen["body"] = json.loads(request.data)
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _StubStream([*_PARTIAL, _sse({"choices": [{"delta": {}, "finish_reason": "stop"}]})])

    _channel(opener).complete("probe-model", "sys", "usr")

    assert seen["url"] == "https://endpoint.example/v1/chat/completions"
    assert seen["timeout"] == 180
    assert seen["body"] == {
        "model": "probe-model",
        "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
        "temperature": 0.0,
        "max_tokens": 4096,
        "stream": True,
        "stream_options": {"include_usage": True},
    }


@pytest.mark.parametrize(
    "failure",
    [
        http.client.IncompleteRead(b"partial", 100),
        http.client.RemoteDisconnected("closed"),
        ConnectionResetError("reset by peer"),
        TimeoutError("timed out"),
        OSError("network is unreachable"),
    ],
    ids=lambda failure: type(failure).__name__,
)
def test_a_stream_that_breaks_midway_is_a_deferral_that_keeps_the_usage_read(failure: BaseException) -> None:
    """IncompleteRead is an HTTPException, not an OSError: both families are transport failures, never a miss."""
    lines = [*_PARTIAL, _sse({"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 8}})]

    completion = _channel(lambda request, timeout: _StubStream(lines, then=failure)).complete("m", "s", "u")

    assert isinstance(completion, transport.Deferral)
    assert completion.reason.startswith("the stream broke")
    assert completion.usage == transport.Usage(prompt_tokens=50, completion_tokens=8)


@pytest.mark.parametrize(
    "failure",
    [
        http.client.IncompleteRead(b"", 10),
        http.client.BadStatusLine("garbage"),
        urllib.error.URLError("name resolution failed"),
        ConnectionRefusedError("refused"),
    ],
    ids=lambda failure: type(failure).__name__,
)
def test_a_call_that_cannot_be_opened_is_a_deferral(failure: BaseException) -> None:
    def opener(request, timeout):
        raise failure

    completion = _channel(opener).complete("m", "s", "u")

    assert isinstance(completion, transport.Deferral)
    assert completion.usage == transport.Usage()


def test_an_http_error_is_a_deferral_naming_the_status_but_never_the_token() -> None:
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 524, "timeout", {}, io.BytesIO(b"upstream timed out"))

    completion = _channel(opener).complete("m", "s", "u")

    assert isinstance(completion, transport.Deferral)
    assert "HTTP 524" in completion.reason
    assert "upstream timed out" in completion.reason
    assert "fixture-token" not in completion.reason


@pytest.mark.parametrize(
    ("lines", "reason"),
    [
        ([], "no chunk"),
        ([_sse({"choices": [{"delta": {"content": "  "}, "finish_reason": "stop"}]})], "empty answer"),
        (["data: {not json\n"], "malformed chunk"),
        ([_sse({"error": {"message": "overloaded"}})], "returned an error"),
    ],
)
def test_an_empty_or_broken_stream_is_a_deferral(lines: list[str], reason: str) -> None:
    completion = _channel(lambda request, timeout: _StubStream(lines)).complete("m", "s", "u")

    assert isinstance(completion, transport.Deferral)
    assert reason in completion.reason


def test_a_stream_that_outlasts_its_limit_is_a_deferral() -> None:
    config = transport.EndpointConfig(base_url="https://endpoint.example", token="t", timeout_s=-1)
    channel = transport.EndpointChannel(config, lambda request, timeout: _StubStream(_PARTIAL))

    completion = channel.complete("m", "s", "u")

    assert isinstance(completion, transport.Deferral)
    assert "outlasted" in completion.reason


def test_the_token_stays_out_of_every_representation() -> None:
    config = transport.EndpointConfig(base_url="https://endpoint.example", token="fixture-token")

    assert "fixture-token" not in repr(config)
    assert "fixture-token" not in repr(transport.EndpointChannel(config))


def test_an_endpoint_that_is_not_http_is_refused() -> None:
    with pytest.raises(ValueError, match="http"):
        transport.EndpointConfig(base_url="file:///etc/passwd", token="t")


def test_served_models_lists_the_ids_the_endpoint_reports() -> None:
    body = json.dumps({"data": [{"id": "b-model"}, {"id": "a-model"}, {"object": "no id"}]}).encode()

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

    config = transport.EndpointConfig(base_url="https://endpoint.example", token="t")
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        return _Response(body)

    assert transport.served_models(config, opener) == ["a-model", "b-model"]
    assert seen == {"url": "https://endpoint.example/v1/models", "auth": "Bearer t"}


def test_served_models_raises_a_transport_error_when_the_endpoint_is_down() -> None:
    def opener(request, timeout):
        raise urllib.error.URLError("down")

    config = transport.EndpointConfig(base_url="https://endpoint.example", token="t")
    with pytest.raises(transport.TransportError):
        transport.served_models(config, opener)


def test_the_channel_protocol_is_all_the_runner_needs() -> None:
    """``run_probe`` takes anything with ``endpoint``, ``variant`` and ``complete`` - no endpoint class."""
    channel: transport.Channel = _StubChannel(lambda model, call: _answer("pkg/mod.py:compute"))

    assert channel.endpoint.endswith("/chat/completions")
    assert channel.variant("m").model == "m"


# --------------------------------------------------------------------------------------
# The sandbox: the docker flags, the verdict line, the in-container runner
# --------------------------------------------------------------------------------------


def _flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_the_container_command_pins_the_isolation_flags() -> None:
    """Pinned by the argv built; docker itself is never run."""
    argv = sandbox.container_command("model-profile-x", "tests/test_mod.py")

    assert argv[:3] == ["docker", "run", "--rm"]
    assert _flag_value(argv, "--network") == "none"
    assert "--read-only" in argv
    assert _flag_value(argv, "--memory") == settings.load().sandbox.memory_limit == "256m"
    assert _flag_value(argv, "--pids-limit") == settings.load().sandbox.pids_limit == "128"
    assert _flag_value(argv, "--cap-drop") == "ALL"
    assert _flag_value(argv, "--security-opt") == "no-new-privileges"
    assert _flag_value(argv, "--user") == "65534:65534"  # not root
    assert _flag_value(argv, "--name") == "model-profile-x"
    tmpfs = [argv[index + 1] for index, token in enumerate(argv) if token == "--tmpfs"]
    assert len(tmpfs) == 2
    assert any(spec.startswith("/tmp:") and "noexec" in spec for spec in tmpfs)
    assert any(spec.startswith("/work:") for spec in tmpfs)
    assert argv[argv.index(settings.load().sandbox.image) - 1] == "/work"  # the image comes after every flag
    assert "--interactive" in argv  # the files arrive over stdin


def test_the_container_command_mounts_nothing_from_the_host_and_grants_nothing() -> None:
    argv = sandbox.container_command("n", "t.py")
    flags = set(argv[: argv.index(settings.load().sandbox.image)])

    assert not flags & {"-v", "--volume", "--mount", "--privileged", "--network=host", "--pid", "--device"}
    assert _flag_value(argv, "--network") != "host"


def test_the_container_command_quotes_the_test_path_for_the_shell() -> None:
    argv = sandbox.container_command("n", "tests/a b; rm -rf x.py")

    assert "'tests/a b; rm -rf x.py'" in argv[-1]


def test_the_sandbox_adds_a_runner_and_a_nonce_and_refuses_a_case_that_carries_those_names() -> None:
    with tarfile.open(fileobj=io.BytesIO(sandbox.tar_stream({"a.py": "x = 1\n"}, "n0nce"))) as archive:
        names = sorted(archive.getnames())
        nonce = archive.extractfile("_probe_nonce").read()

    assert names == ["_probe_nonce", "_probe_runner.py", "a.py"]
    assert nonce == b"n0nce"
    for reserved in (settings.load().sandbox.runner_file, settings.load().sandbox.nonce_file):
        with pytest.raises(sandbox.SandboxError, match="reserves"):
            sandbox.tar_stream({reserved: "x"}, "n")


def _line(nonce: str, tests: dict[str, str], error: str | None = None) -> str:
    return f"{settings.load().sandbox.result_prefix} {nonce} {json.dumps({'tests': tests, 'error': error})}"


def test_the_verdict_is_the_last_line_with_this_runs_nonce() -> None:
    stdout = f"noise\n{_line('abc', {'test_a': 'passed', 'test_b': 'failed'})}\n"

    verdict = sandbox.parse_verdict(stdout, "abc")

    assert verdict.tests == {"test_a": "passed", "test_b": "failed"}
    assert verdict.error is None


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "no marker at all\n",
        _line("someone-elses-guess", {"test_a": "passed"}) + "\n",  # wrong nonce
        _line("abc", {"test_a": "passed"}) + "\ntrailing noise\n",  # the verdict is not the last line
        "glued " + _line("abc", {"test_a": "passed"}) + "\n",  # glued to a print(end="")
        f"{settings.load().sandbox.result_prefix} abc not-json\n",
        f"{settings.load().sandbox.result_prefix} abc "
        + json.dumps({"tests": {"test_a": "maybe"}, "error": None})
        + "\n",
        f"{settings.load().sandbox.result_prefix} abc " + json.dumps(["tests"]) + "\n",
    ],
    ids=["empty", "no-marker", "wrong-nonce", "not-last", "glued", "bad-json", "bad-outcome", "not-an-object"],
)
def test_a_forged_or_misplaced_verdict_line_is_not_a_verdict(stdout: str) -> None:
    with pytest.raises(sandbox.VerdictMissingError):
        sandbox.parse_verdict(stdout, "abc")


def _run_runner(tmp_path: Path, files: dict[str, str], nonce: str = "run-nonce") -> subprocess.CompletedProcess[str]:
    """Run the in-container runner with the host interpreter in a temporary work directory."""
    work = tmp_path / "work"
    work.mkdir()
    with tarfile.open(fileobj=io.BytesIO(sandbox.tar_stream(files, nonce))) as archive:
        archive.extractall(work, filter="data")
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(work / settings.load().sandbox.runner_file),
            "test_prog.py",
            str(work),
            settings.load().sandbox.result_prefix,
        ],
        capture_output=True,
        text=True,
        cwd=work,
        timeout=60,
        check=False,
    )


_FORGER = (
    "import sys\n"
    f'forged = \'{settings.load().sandbox.result_prefix} guess {{"tests": {{"test_x": "passed"}}, "error": null}}\'\n'
    "print(forged)\n"
    "print(forged, end='')\n"
    "sys.stdout.write(forged)\n"
    "sys.__stdout__.write(forged)  # straight to the real stdout, no newline after it\n"
    "def f():\n"
    "    return 1\n"
)
_TEST_OF_FORGER = "from prog import f\n\ndef test_x():\n    assert f() == 2\n"


def test_a_program_that_prints_a_fake_verdict_cannot_change_the_real_one(tmp_path: Path) -> None:
    """The runner's own line comes last, on a line of its own, with the nonce the program never saw."""
    done = _run_runner(tmp_path, {"prog.py": _FORGER, "test_prog.py": _TEST_OF_FORGER})

    assert "guess" in done.stdout  # the forgery did reach the real stdout
    verdict = sandbox.parse_verdict(done.stdout, "run-nonce")
    assert verdict.tests == {"test_x": "failed"}


def test_the_runner_reports_passes_and_failures_per_test_function(tmp_path: Path) -> None:
    files = {
        "prog.py": "def f():\n    return 2\n",
        "test_prog.py": (
            "from prog import f\n\ndef test_ok():\n    assert f() == 2\n\ndef test_bad():\n    assert f() == 3\n"
        ),
    }

    verdict = sandbox.parse_verdict(_run_runner(tmp_path, files).stdout, "run-nonce")

    assert verdict.tests == {"test_ok": "passed", "test_bad": "failed"}


def test_the_runner_reports_a_collection_error(tmp_path: Path) -> None:
    files = {"prog.py": "x = 1\n", "test_prog.py": "import prog\nraise RuntimeError('boom')\n"}

    verdict = sandbox.parse_verdict(_run_runner(tmp_path, files).stdout, "run-nonce")

    assert verdict.tests == {}
    assert "boom" in verdict.error


def test_the_runner_deletes_the_nonce_file_before_it_imports_anything_of_the_models(tmp_path: Path) -> None:
    files = {
        "prog.py": "import pathlib\nassert not pathlib.Path('_probe_nonce').exists()\n",
        "test_prog.py": "import prog\n\ndef test_ok():\n    pass\n",
    }

    verdict = sandbox.parse_verdict(_run_runner(tmp_path, files).stdout, "run-nonce")

    assert verdict.tests == {"test_ok": "passed"}
    assert not (tmp_path / "work" / settings.load().sandbox.nonce_file).exists()


def test_a_program_that_kills_the_runner_earns_no_verdict(tmp_path: Path) -> None:
    files = {"prog.py": "import os\nos._exit(0)\n", "test_prog.py": "import prog\n\ndef test_x():\n    pass\n"}

    done = _run_runner(tmp_path, files)

    with pytest.raises(sandbox.VerdictMissingError):
        sandbox.parse_verdict(done.stdout, "run-nonce")


def _completed(stdout: str, returncode: int, stderr: str = "") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], returncode, stdout.encode(), stderr.encode())


def test_a_run_the_program_ended_without_a_verdict_is_a_failed_result_not_a_sandbox_error() -> None:
    """An out-of-memory kill (exit 137) is the model's failure; it must not abort the run."""
    result = sandbox._result_of(_completed("", 137), "abc", 1.0)

    assert not result.passed
    assert result.exit_code == 137
    assert "no verdict" in result.stderr


@pytest.mark.parametrize("code", settings.load().sandbox.docker_failure_codes)
def test_a_run_docker_ended_without_a_verdict_is_a_sandbox_error(code: int) -> None:
    with pytest.raises(sandbox.SandboxError, match=str(code)):
        sandbox._result_of(_completed("", code, "docker: daemon error"), "abc", 1.0)


def test_a_verdict_with_every_test_passing_is_a_pass() -> None:
    stdout = "\n" + _line("abc", {"test_a": "passed", "test_b": "passed"}) + "\n"

    assert sandbox._result_of(_completed(stdout, 0), "abc", 1.0).passed
    assert not sandbox._result_of(_completed("\n" + _line("abc", {}) + "\n", 0), "abc", 1.0).passed
    assert not sandbox._result_of(_completed("\n" + _line("abc", {}, "boom") + "\n", 0), "abc", 1.0).passed


def test_docker_missing_is_a_refusal_not_a_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)

    with pytest.raises(sandbox.SandboxUnavailableError, match="docker is not on the PATH"):
        sandbox.ensure_available()


def test_extract_python_block_wants_exactly_one_fence() -> None:
    assert sandbox.extract_python_block("x\n```python\na = 1\n```\n") == "a = 1\n"
    assert sandbox.extract_python_block("```python\na\n```\n```python\nb\n```\n") is None
    assert sandbox.extract_python_block("none") is None


def _docker_unavailable_reason() -> str | None:
    """Why a real container cannot be run here, or ``None`` when one can.

    Three causes are told apart because each has a different fix: no client, no permission on the
    daemon's socket (the user is not in group ``docker``), and no daemon answering.
    """
    binary = shutil.which("docker")
    if binary is None:
        return "docker is not on the PATH (install the docker client)"
    done = subprocess.run([binary, "version"], capture_output=True, text=True, timeout=60, check=False)
    if done.returncode == 0:
        return None
    if "permission denied" in done.stderr.lower():
        return "this user may not reach the docker socket (add the user to group docker, then log in again)"
    return "docker version failed: no daemon is answering"


@pytest.fixture
def docker_daemon() -> None:
    """Skip, with the cause, unless a container can run - the one place a test needs a runtime.

    These tests are the local full suite's; CI deselects them with ``-m "not docker"``.
    """
    reason = _docker_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)


@pytest.mark.docker
def test_the_seed_item_set_survives_the_gold_sanity_gate_in_a_real_container(docker_daemon: None) -> None:
    item_set = cases.load_item_set(_PROFILE / "items" / "seed_cases.json")

    report = oracle.run_gate(item_set, oracle.sandbox_runner())

    assert report.ok, [outcome.reason for outcome in report.refused]


# --------------------------------------------------------------------------------------
# The item set
# --------------------------------------------------------------------------------------


def _seed_document() -> dict:
    return json.loads((_PROFILE / "items" / "seed_cases.json").read_text(encoding="utf-8"))


def _write(tmp_path: Path, document: dict, name: str = "items.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_the_shipped_seed_set_loads() -> None:
    item_set = cases.load_item_set(_PROFILE / "items" / "seed_cases.json")

    assert [case.id for case in item_set.cases] == ["invoice-coupon", "inventory-available"]
    assert item_set.families == ("fix-symptom", "fix-traceback", "hunt")
    assert len(item_set.cases_sha) == len(item_set.envelope_sha) == settings.load().hash_length
    assert item_set.select(families=["hunt"])[0].id == "inventory-available"
    fixed = item_set.cases[0].fixed_program()
    assert fixed["report.py"] == item_set.cases[0].files["report.py"]  # fixed_files patches over files
    assert fixed["invoice.py"] != item_set.cases[0].files["invoice.py"]


def test_the_cases_hash_follows_the_content_not_the_filename(tmp_path: Path) -> None:
    document = _seed_document()
    first = cases.load_item_set(_write(tmp_path, document, "one.json"))
    moved = cases.load_item_set(_write(tmp_path, document, "two.json"))
    document["cases"][0]["files"]["helpers.py"] += "# edited\n"
    edited = cases.load_item_set(_write(tmp_path, document, "three.json"))

    assert first.cases_sha == moved.cases_sha
    assert edited.cases_sha != first.cases_sha


def test_the_envelope_hash_follows_the_knobs() -> None:
    path = _PROFILE / "items" / "seed_cases.json"

    assert (
        cases.load_item_set(path).envelope_sha
        != cases.load_item_set(path, cases.Envelope(max_output_tokens=2048)).envelope_sha
    )


def test_the_envelope_hash_does_not_depend_on_an_integer_or_a_float_temperature() -> None:
    """``1`` and ``1.0`` are one envelope, and the JavaScript twin cannot tell them apart."""
    path = _PROFILE / "items" / "seed_cases.json"

    as_int = cases.load_item_set(path, cases.Envelope(temperature=1)).envelope_sha  # type: ignore[arg-type]
    as_float = cases.load_item_set(path, cases.Envelope(temperature=1.0)).envelope_sha

    assert as_int == as_float


@pytest.mark.parametrize("content", [None, 7, ["a"], {"text": "a"}])
def test_a_stream_chunk_with_a_non_text_content_is_ignored_not_a_crash(content: object) -> None:
    """An odd endpoint must end in a deferral (empty answer), never a TypeError out of the run."""
    reader = transport._StreamReader()
    reader.feed({"choices": [{"delta": {"content": content}}]})
    reader.feed({"choices": [{"delta": {"content": "kept"}, "finish_reason": "stop"}]})

    assert reader.text(4096) == "kept"


def test_a_stream_of_only_non_text_content_is_an_empty_answer() -> None:
    reader = transport._StreamReader()
    reader.feed({"choices": [{"delta": {"content": 7}, "finish_reason": "stop"}]})

    with pytest.raises(transport.TransportError, match="empty answer"):
        reader.text(4096)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["cases"][0].pop("hidden_test"), "missing hidden_test"),
        (lambda d: d["cases"][0]["hidden_test"].pop("content"), "missing content"),
        (lambda d: d["cases"][0]["hidden_test"].update(path="invoice.py"), "collides"),
        (lambda d: d["cases"][0]["hidden_test"].update(path="../escape.py"), "stay inside"),
        (lambda d: d["cases"][0]["fixed_files"].update({"nope.py": "x = 1\n"}), "does not carry"),
        (lambda d: d["cases"][0]["bug"].update(file="nope.py"), "not one of the case's files"),
        (lambda d: d["cases"][0]["asks"].pop("fix-symptom"), "no ask for fix-symptom"),
        (lambda d: d["cases"][0].update(families=["telepathy"]), "unknown family"),
        (lambda d: d["cases"][0].update(families=["hunt", "hunt"]), "twice"),
        (lambda d: d["cases"].append(d["cases"][0]), "case id twice"),
        (lambda d: d.update(cases=[]), "no cases"),
        (lambda d: d.pop("version"), "version"),
    ],
)
def test_a_malformed_item_set_raises_and_never_half_loads(tmp_path: Path, mutate, message: str) -> None:
    document = _seed_document()
    mutate(document)

    with pytest.raises(cases.ItemSetError, match=message):
        cases.load_item_set(_write(tmp_path, document))


def test_an_unreadable_or_non_json_item_set_raises(tmp_path: Path) -> None:
    with pytest.raises(cases.ItemSetError, match="cannot read"):
        cases.load_item_set(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    with pytest.raises(cases.ItemSetError, match="not valid JSON"):
        cases.load_item_set(broken)


# --------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------


def test_probe_without_yes_prints_the_plan_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(transport, "served_models", lambda config, opener=None: ["m1", "m2"])
    monkeypatch.setattr(runner, "run_probe", lambda *args, **kwargs: pytest.fail("a probe ran without --yes"))
    argv = ["probe", "--endpoint", "https://endpoint.example/v1", "--models", "m1", "--token-env", "MY_TOKEN"]

    code = cli.main(argv, {"MY_TOKEN": "s3cret-value"})

    shown = capsys.readouterr()
    assert code == 2
    assert "nothing was sent" in shown.out
    assert "1 models = 3 calls" in shown.out
    assert "s3cret-value" not in shown.out + shown.err


def test_probe_with_yes_runs_and_never_prints_the_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(transport, "served_models", lambda config, opener=None: ["m1"])
    monkeypatch.setattr(sandbox, "ensure_available", lambda: None)
    seen = {}

    def fake_run(item_set, channel, selection, options):
        seen.update(
            models=selection.models, budget=options.token_budget, out=options.out_dir, endpoint=channel.endpoint
        )
        return runner.RunReport(
            attempts=(),
            rows=(),
            gate=oracle.GateReport(outcomes=()),
            item_bands=(),
            ledger=options.out_dir / "ledger.jsonl",
            detail_files=(),
        )

    monkeypatch.setattr(runner, "run_probe", fake_run)
    argv = ["probe", "--endpoint", "https://endpoint.example/v1/", "--models", "m1", "--yes", "--token-budget", "5000"]
    argv += ["--out", str(tmp_path / "run")]

    code = cli.main(argv, {settings.load().cli.default_token_env: "s3cret-value"})

    shown = capsys.readouterr()
    assert code == 0
    assert seen == {
        "models": ("m1",),
        "budget": 5000,
        "out": tmp_path / "run",
        "endpoint": "https://endpoint.example/v1/chat/completions",
    }
    assert "s3cret-value" not in shown.out + shown.err


def test_probe_without_a_token_names_the_variable_and_not_a_value(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["probe", "--endpoint", "https://endpoint.example", "--token-env", "MY_TOKEN"], {})

    assert code == 1
    assert "MY_TOKEN" in capsys.readouterr().err


def test_probe_refuses_a_model_the_endpoint_does_not_serve(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(transport, "served_models", lambda config, opener=None: ["m1"])

    token_env = settings.load().cli.default_token_env
    code = cli.main(["probe", "--endpoint", "https://endpoint.example", "--models", "ghost"], {token_env: "t"})

    assert code == 1
    assert "does not serve ghost" in capsys.readouterr().err


def test_probe_needs_an_endpoint(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["probe"], {settings.load().cli.default_token_env: "t"}) == 1
    assert "--endpoint" in capsys.readouterr().err


def test_plan_with_named_models_needs_no_endpoint(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["plan", "--models", "a", "b", "--families", "hunt"], {})

    assert code == 0
    assert "1 (case, family) pairs x 2 models = 2 calls" in capsys.readouterr().out


def test_a_token_budget_must_be_positive() -> None:
    with pytest.raises(SystemExit):
        cli.main(["probe", "--token-budget", "0"], {})


def test_gate_needs_the_sandbox_and_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)

    code = cli.main(["gate"], {})

    assert code == 1
    assert "docker" in capsys.readouterr().err


def test_gate_reports_each_case(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sandbox, "ensure_available", lambda: None)
    monkeypatch.setattr(oracle, "sandbox_runner", lambda *args, **kwargs: _always_fails)

    code = cli.main(["gate"], {})

    shown = capsys.readouterr().out
    assert code == 1
    assert "REFUSED invoice-coupon" in shown
    assert "0 of 2 case(s) usable" in shown


def test_the_default_output_directory_is_the_local_layer_of_the_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "AGENTS.md").write_text("project\n", encoding="utf-8")
    (tmp_path / ".aitna-root").write_text("meta\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    args = cli.build_parser().parse_args(["probe"])

    out = cli._out_dir(args, _STAMP)

    assert out == tmp_path.resolve() / "meta" / ".local" / "model_profile" / "20260301T120000Z"


def test_without_a_project_root_the_default_output_directory_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    args = cli.build_parser().parse_args(["probe"])

    with pytest.raises(cli.CliError, match="--out"):
        cli._out_dir(args, _STAMP)
    explicit = cli.build_parser().parse_args(["probe", "--out", str(tmp_path / "here")])
    assert cli._out_dir(explicit, _STAMP) == tmp_path / "here"
