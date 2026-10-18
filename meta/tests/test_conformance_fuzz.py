"""Contract tests for the differential hook fuzz (C111, design node-consumers.md §5 gate 4).

The fuzz run's value is its verdicts, so the machinery behind them is pinned on synthetic inputs,
without a run of both implementations: the cases are a pure function of (seed, index); every
mutation kind produces the stdin it names; the comparator flags each observable and only those;
the known-divergence table matches by its fields and refuses an entry no DV row backs; and a
divergent case's draft is a scenario the corpus loader reads. One tiny end-to-end case runs when
``node`` is on PATH.

``fuzz`` imports its siblings by bare name, like ``runner``; it is loaded the way
``test_conformance_corpus.py`` loads the runner, with a foreign ``coverage`` module set aside.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import random
import re
import shutil
import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_CONFORMANCE = _AKMON / "meta" / "conformance"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_foreign_coverage = sys.modules.get("coverage")
if _foreign_coverage is not None and Path(getattr(_foreign_coverage, "__file__", "") or "").parent != _CONFORMANCE:
    del sys.modules["coverage"]
else:
    _foreign_coverage = None
try:
    fuzz = _load("conformance_fuzz", _CONFORMANCE / "fuzz.py")
finally:
    if _foreign_coverage is not None:
        sys.modules["coverage"] = _foreign_coverage

self_ci = _load("conformance_fuzz_self_ci", _AKMON / "meta" / "self_ci.py")

SEEDS = fuzz.load_seeds()
VOCAB = fuzz.vocabulary(SEEDS)
SAMPLE = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Edit",
    "session_id": "sess-1",
    "cwd": "{{root}}",
    "tool_input": {"file_path": "{{root}}/a.md", "lines": [1, 2]},
}


# --- seeds and determinism ------------------------------------------------------------


def test_every_shared_hook_scenario_is_a_seed():
    names = {seed.name for seed in SEEDS}
    hooks = {s.id for s in fuzz.load_scenarios("hooks") if s.ecosystem == "shared"}
    assert hooks and hooks <= names
    assert {"PreToolUse", "SessionStart", "Stop"} <= set(VOCAB.events)
    assert {"Bash", "Edit"} <= set(VOCAB.tools)


def test_a_recorded_seed_names_its_hook_in_the_file_name(tmp_path):
    (tmp_path / "delegation-nudge--burst.json").write_text('{"hook_event_name": "PreToolUse"}', encoding="utf-8")
    seeds = fuzz.load_seeds("delegation-nudge", seeds_dir=tmp_path)
    recorded = [seed for seed in seeds if seed.name == "seeds/delegation-nudge--burst"]
    assert recorded and recorded[0].payload == {"hook_event_name": "PreToolUse"}
    assert recorded[0].scenario.fixture.warmup == "after"
    (tmp_path / "nameless.json").write_text("{}", encoding="utf-8")
    with pytest.raises(fuzz.CorpusError, match="<script>--<label>"):
        fuzz.load_seeds(seeds_dir=tmp_path)


def test_a_seed_nested_past_the_walk_depth_is_held_as_raw_json_and_still_mutates():
    seed = next(s for s in SEEDS if s.name == "hooks/delegation-nudge-deep-tool-name")
    node, depth = seed.payload["tool_name"], 1
    while isinstance(node, dict):
        node, depth = node["a"], depth + 1
    assert isinstance(node, fuzz.Raw) and depth == fuzz.SEED_WALK_DEPTH
    assert node.text.startswith('{"a": {"a": ') and node.text.endswith("1" + "}" * (5000 - depth + 1))
    for index in range(len(fuzz.KINDS)):
        case = fuzz.make_case(3, index, [seed], fuzz.vocabulary([seed]))
        assert case.stdin is not None


def test_a_case_is_a_pure_function_of_seed_and_index():
    for index in range(len(fuzz.KINDS) * 2):
        first = fuzz.make_case(7, index, SEEDS, VOCAB)
        again = fuzz.make_case(7, index, SEEDS, VOCAB)
        assert (first.seed.name, first.mutations, first.stdin) == (again.seed.name, again.mutations, again.stdin)
        assert fuzz.seed_of(7, index, SEEDS).name == first.seed.name
    other = [fuzz.make_case(8, index, SEEDS, VOCAB).stdin for index in range(len(fuzz.KINDS))]
    assert other != [fuzz.make_case(7, index, SEEDS, VOCAB).stdin for index in range(len(fuzz.KINDS))]


def test_the_primary_kind_cycles_so_a_bounded_run_covers_every_kind():
    seen = set()
    for index in range(len(fuzz.KINDS)):
        case = fuzz.make_case(0, index, SEEDS, VOCAB)
        kind = fuzz.KINDS[index]
        assert kind in case.kinds, (index, case.mutations)
        seen.add(kind)
    assert seen == set(fuzz.KINDS)


def test_buckets_give_each_seed_one_worker_and_keep_every_case():
    indices = tuple(range(200))
    parts = fuzz.buckets(3, indices, SEEDS, 4)
    assert sorted(i for part in parts for i in part) == list(indices)
    owners = {}
    for worker, part in enumerate(parts):
        for index in part:
            assert owners.setdefault(fuzz.seed_of(3, index, SEEDS).name, worker) == worker


# --- each mutation kind produces the stdin it names ---------------------------------------


def _mutated(kind: str, seed: int = 0) -> tuple[dict, str]:
    doc = json.loads(json.dumps(SAMPLE))
    label = fuzz.VALUE_MUTATIONS[kind](doc, random.Random(seed), VOCAB)  # noqa: S311
    return doc, label


@pytest.mark.parametrize("kind", sorted(set(fuzz.VALUE_MUTATIONS) - {"deep-nest", "big-number"}))
def test_a_value_mutation_keeps_a_parseable_object(kind):
    for seed in range(8):
        doc, label = _mutated(kind, seed)
        assert label.startswith(kind + ":")
        for ascii_only in (True, False):
            parsed = json.loads(fuzz.encode_document(doc, ascii_only=ascii_only))
            assert parsed == doc
        assert doc != SAMPLE or kind == "drop-key"


def test_value_mutations_do_what_their_label_says():
    doc, _ = _mutated("long-string")
    assert any(isinstance(v, str) and len(v.encode()) >= fuzz.LONG_STRING_BYTES for v in _leaves(doc))
    for seed in range(8):
        doc, label = _mutated("lone-surrogate", seed)
        assert b"\\ud800" in fuzz.encode_document(doc, ascii_only=False).lower() or b"\\udfff" in (
            fuzz.encode_document(doc, ascii_only=False).lower()
        ), label
        doc, label = _mutated("path-like", seed)
        assert label.split(":", 1)[1] in {"cwd", "tool_input.file_path"}
        doc, label = _mutated("swap-event", seed)
        assert doc["hook_event_name"] in VOCAB.events and doc["hook_event_name"] != "PreToolUse"
        doc, label = _mutated("swap-tool", seed)
        assert doc["tool_name"] in VOCAB.tools and doc["tool_name"] != "Edit"
        doc, label = _mutated("control-chars", seed)
        assert any(ch in v for v in _leaves(doc) if isinstance(v, str) for _name, ch in fuzz.CONTROLS)
        doc, label = _mutated("unicode-edge", seed)
        assert any(ch in v for v in _leaves(doc) if isinstance(v, str) for _name, ch in fuzz.UNICODE_EDGES)


def test_big_numbers_and_deep_nesting_are_spelled_as_raw_tokens():
    spellings = {}
    for seed in range(40):
        doc, label = _mutated("big-number", seed)
        spellings[label.split(":")[1]] = fuzz.encode_document(doc, ascii_only=True)
    assert b"9007199254740993" in spellings["beyond-2^53"]
    assert re.search(rb"(?<![\d.])-0(?![\d.])", spellings["neg-zero"])
    assert b"1e309" in spellings["overflow"]
    assert b"1.0" in spellings["float-one"]
    for seed in range(20):
        doc, label = _mutated("deep-nest", seed)
        depth = int(label.split(":")[1].split("-")[1])
        text = fuzz.encode_document(doc, ascii_only=True)
        assert (b"[" * depth in text) or (b'{"a": ' * depth in text), label


@pytest.mark.parametrize("kind", fuzz.STDIN_MUTATIONS)
def test_a_stdin_mutation_breaks_the_document_the_way_it_names(kind):
    for seed in range(12):
        doc = json.loads(json.dumps(SAMPLE))
        stdin, label, document = fuzz._stdin_stage(doc, kind, random.Random(seed), ascii_only=True)  # noqa: S311
        assert label.startswith(kind + ":") and document is None
        if kind == "invalid-utf8":
            with pytest.raises(UnicodeDecodeError):
                stdin.decode("utf-8")
        elif kind == "empty-stdin":
            assert not stdin.strip()
        elif kind == "truncate":
            with pytest.raises(ValueError):  # a proper prefix of an object is never a JSON document
                json.loads(stdin)
        elif kind == "duplicate-key":
            pairs = json.loads(stdin, object_pairs_hook=lambda items: items)
            keys = [key for key, _value in pairs]
            assert len(keys) != len(set(keys))
        else:  # non-json: not one JSON object
            try:
                value = json.loads(stdin)
            except ValueError:
                continue
            assert not isinstance(value, dict) or stdin.startswith(b"\xef\xbb\xbf")


def _leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


# --- the comparator -----------------------------------------------------------------------


def _observed(**overrides):
    base = {"exit": 0, "stdout": '{"a": 1, "b": [2]}\n', "stderr": "", "effects": {"x.log": "d1"}}
    return fuzz.Observed(**{**base, **overrides})


def test_equal_results_agree_and_stdout_compares_as_json():
    assert fuzz.differing_streams(_observed(), _observed()) == ()
    assert fuzz.differing_streams(_observed(), _observed(stdout='{"b":[2],"a":1}')) == ()


@pytest.mark.parametrize(
    ("override", "stream"),
    [
        ({"exit": 1}, "exit"),
        ({"exit": "timeout"}, "exit"),
        ({"stdout": '{"a": 2, "b": [2]}'}, "stdout"),
        ({"stdout": "not json"}, "stdout"),
        ({"stderr": "boom\n"}, "stderr"),
        ({"effects": {}}, "files"),
        ({"effects": {"x.log": "d2"}}, "files"),
    ],
)
def test_a_planted_difference_is_flagged_on_its_stream_only(override, stream):
    assert fuzz.differing_streams(_observed(), _observed(**override)) == (stream,)


def test_text_stdout_is_compared_exactly():
    assert fuzz.differing_streams(_observed(stdout="a\n"), _observed(stdout="a")) == ("stdout",)


# --- known divergences --------------------------------------------------------------------


def _case(mutations, script="delegation-log", stdin=b"{}"):
    seed = next(s for s in SEEDS if s.script == script)
    return fuzz.Case(index=0, seed=seed, mutations=tuple(mutations), stdin=stdin)


def test_a_known_entry_matches_by_script_streams_mutation_stdin_and_host():
    entry = fuzz.Known(
        dv="DV4",
        reason="r",
        scripts=("delegation-*",),
        streams=("stdout", "stderr"),
        mutation="invalid-utf8:*",
        stdin_regex="sess",
        python_stdin_errors="surrogateescape",
    )
    case = _case(["retype:x->null", "invalid-utf8:ff:session_id"], stdin=b'{"session_id": "sess"}')
    host = {"python_stdin_errors": "surrogateescape"}
    assert entry.matches(case, ("stdout",), host)
    assert not entry.matches(case, ("stdout",), {"python_stdin_errors": "strict"})
    assert not entry.matches(case, ("stdout", "exit"), host)  # a stream the entry does not allow
    assert not entry.matches(_case(["truncate:3/9"], stdin=b'{"session_id": "sess"}'), ("stdout",), host)
    assert not entry.matches(_case(["invalid-utf8:ff:x"], script="gate-audit", stdin=b"sess"), ("stdout",), host)
    assert not entry.matches(_case(["invalid-utf8:ff:x"], stdin=b"{}"), ("stdout",), host)


def test_judge_counts_a_matched_difference_as_known_and_any_other_as_divergent():
    known = [fuzz.Known(dv="DV2", reason="r", mutation="big-number:beyond-2^*")]
    results = {"python": _observed(), "node": _observed(stderr="x")}
    assert fuzz.judge(_case(["big-number:beyond-2^53:session_id"]), results, known, {}).verdict == "known"
    assert fuzz.judge(_case(["retype:a->null"]), results, known, {}).verdict == "divergent"
    same = {"python": _observed(), "node": _observed()}
    assert fuzz.judge(_case(["retype:a->null"]), same, known, {}).verdict == "agree"


def test_the_shipped_table_loads_and_every_entry_names_a_dv_row():
    entries = fuzz.load_known()
    assert entries
    rows = fuzz._dv_ids(fuzz.DIVERGENCES_FILE)
    assert all(entry.dv in rows for entry in entries)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('[[known]]\ndv = "DV999"\nreason = "r"\n', "no row of"),
        ('[[known]]\ndv = "DV1"\nreason = "r"\nscript = "x"\n', "unknown field"),
        ('[[known]]\ndv = "DV1"\n', "no reason"),
        ('[[known]]\ndv = "DV1"\nreason = "r"\nstreams = ["stdin"]\n', "unknown stream"),
    ],
)
def test_the_table_refuses_an_entry_no_dv_row_backs(tmp_path, body, message):
    (tmp_path / "fuzz.toml").write_text(body, encoding="utf-8")
    (tmp_path / "DIVERGENCES.md").write_text("| DV1 | a | b | c | d | e |\n", encoding="utf-8")
    with pytest.raises(fuzz.CorpusError, match=message):
        fuzz.load_known(tmp_path / "fuzz.toml", tmp_path / "DIVERGENCES.md")


# --- the draft scenario -------------------------------------------------------------------


def _load_draft(tmp_path, monkeypatch, text: str, name: str):
    corpus = sys.modules["corpus"]  # the loader module fuzz itself reads scenarios with
    hooks = tmp_path / "scenarios" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    path = hooks / f"{name}.toml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(corpus, "CORPUS_ROOT", tmp_path)
    # Unreviewed, the draft is refused; the reviewer's last act is removing its [fuzz] table.
    with pytest.raises(corpus.CorpusError, match=r"unreviewed fuzz draft \(a \[fuzz\] table\)"):
        corpus.load_scenario(path)
    path.write_text(_without_fuzz_table(text), encoding="utf-8")
    return corpus.load_scenario(path)


def _without_fuzz_table(text: str) -> str:
    """The draft with its ``[fuzz]`` table (the header line through the next blank line) removed."""
    lines = text.splitlines(keepends=True)
    start = lines.index("[fuzz]\n")
    end = lines.index("\n", start)
    return "".join(lines[:start] + lines[end + 1 :])


def test_a_draft_of_a_plain_payload_parses_as_a_corpus_scenario(tmp_path, monkeypatch):
    seed = next(s for s in SEEDS if s.name == "hooks/gate-audit-review-hold")
    document = {**seed.payload, "session_id": "", "extra": [1, "two"]}
    case = fuzz.Case(9, seed, ("empty-string:session_id",), fuzz.encode_document(document, ascii_only=True), document)
    python = _observed(stdout='{"decision": "block", "reason": "{{root}}"}\n', effects={}, exit=0)
    node = _observed(stdout="", stderr="crash\n", exit=1)
    text = fuzz.draft_scenario(case, 5, {"python": python, "node": node}, ("exit", "stdout", "stderr"))
    assert text.startswith("# DRAFT")
    assert "--seed 5 --case 9" in text
    scenario = _load_draft(tmp_path, monkeypatch, text, "fuzz-gate-audit-s5-c9")
    assert scenario.id == "hooks/fuzz-gate-audit-s5-c9"
    assert (scenario.kind, scenario.ecosystem, scenario.run.script) == ("hook", "shared", "gate-audit")
    assert scenario.run.payload == document
    assert scenario.fixture.files == seed.scenario.fixture.files
    assert scenario.expected.exit == 0
    assert scenario.expected.stdout_json == {"decision": "block", "reason": "{{root}}"}
    assert scenario.expected.stderr == ""


def test_a_draft_of_an_unspellable_stdin_carries_its_bytes_and_still_loads(tmp_path, monkeypatch):
    seed = next(s for s in SEEDS if s.script == "delegation-nudge")
    case = fuzz.Case(2, seed, ("non-json:nan",), b"NaN")
    python = _observed(stdout="", effects={"a/b.md": "d"}, contents={"a/b.md": "made\n"})
    text = fuzz.draft_scenario(case, 1, {"python": python, "node": _observed(stdout="")}, ("files",))
    assert "cannot carry this stdin" in text
    scenario = _load_draft(tmp_path, monkeypatch, text, "fuzz-delegation-nudge-s1-c2")
    assert scenario.run.payload is None
    assert scenario.expected.stdout == ""
    assert scenario.expected.files == {"a/b.md": "made\n"}
    assert 'stdin_base64 = "TmFO"' in text


def test_only_plain_documents_have_a_payload_spelling():
    for document in ({"a": None}, {"a": "\ud800"}, {"a": 2**64}, {"a": fuzz.Raw("-0")}, {}):
        assert fuzz.payload_toml(fuzz.Case(0, SEEDS[0], (), b"", document)) is None
    assert fuzz.payload_toml(fuzz.Case(0, SEEDS[0], (), b"", {"a": {"b": [1, "c"]}, "d": 1.5})) is not None


# --- wiring -------------------------------------------------------------------------------


def test_the_self_ci_leg_is_bounded_and_the_release_depth_draws_a_fresh_seed():
    assert self_ci.fuzz_budget("bounded") == (120, 0)
    cases, seed = self_ci.fuzz_budget("release")
    assert cases == 2000 and 0 <= seed < 2**31
    source = inspect.getsource(self_ci._run)
    assert 'code="selfci.fuzz"' in source
    assert '"fuzz.py"' in source


@pytest.mark.skipif(shutil.which("node") is None, reason="the differential case needs node on PATH")
def test_one_case_runs_on_both_implementations(tmp_path):
    plan = fuzz.Plan(seed=0, indices=(3,), script="delegation-log", jobs=1)
    outcomes, unrun = fuzz.run_fuzz(plan, tmp_path / "drafts")
    assert unrun == 0 and len(outcomes) == 1
    assert outcomes[0].verdict in {"agree", "known", "divergent"}
    assert outcomes[0].case.seed.script == "delegation-log"
