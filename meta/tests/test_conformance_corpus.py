"""Contract tests for the conformance corpus machinery (C101, design §5).

The corpus compares normalized process output against scenario files; a silent change in the
machinery that does the comparing moves every scenario at once without any one of them failing.
So each rule here is pinned on its own, against synthetic inputs, with no corpus run: the
normalization rules (NORM_VERSION 2), the scenario loader's refusals, the snapshot builder's two
refusals, the runner's line-level comparison and its ``--record`` round trip, and how
``release_check`` displays a suite command.

The corpus modules are loaded by file path under unique names (the corpus's ``coverage.py``
shares its bare name with the PyPI package). ``runner`` imports its siblings by bare name from its
own directory, so it is loaded after ``meta/conformance`` is on ``sys.path`` the way it puts it
there itself.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
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


norm = _load("conformance_normalize", _CONFORMANCE / "normalize.py")
corpus = _load("conformance_corpus", _CONFORMANCE / "corpus.py")

# ``runner`` does ``from coverage import …`` by bare name. A foreign ``coverage`` already imported
# (pytest-cov) would shadow the corpus's own; set it aside for the import and put it back after.
_foreign_coverage = sys.modules.get("coverage")
if _foreign_coverage is not None and Path(getattr(_foreign_coverage, "__file__", "") or "").parent != _CONFORMANCE:
    del sys.modules["coverage"]
else:
    _foreign_coverage = None
try:
    runner = _load("conformance_runner", _CONFORMANCE / "runner.py")
finally:
    if _foreign_coverage is not None:
        sys.modules["coverage"] = _foreign_coverage

release_check = _load("conformance_release_check", _AKMON / "tools" / "release" / "release_check.py")

DAY = "2026-09-27"
ROOT = "/w/proj-x"
CTX = norm.Ctx(
    root=ROOT,
    mount=f"{ROOT}/_aitna/akmon",
    tree="/w/tree",
    tmp="/w/tmp-x",
    version="9.8.7",
    repo="/w/repo",
    days=(DAY,),
)


def _n(text: str, ctx=CTX) -> str:
    return norm.normalize(text, ctx)


# --- 1. normalize ------------------------------------------------------------------


def test_norm_version_is_2():
    assert norm.NORM_VERSION == 2


@pytest.mark.parametrize(
    "command",
    [
        'python3 "$CLAUDE_PROJECT_DIR/_aitna/akmon/hooks/x.py"',
        'node "$CLAUDE_PROJECT_DIR/node_modules/akmon/js/hooks/x.mjs"',
        '"$CLAUDE_PROJECT_DIR/.venv/bin/akmon" hook x',
    ],
)
def test_hook_spellings_collapse_to_one_token(command):
    assert _n(command) == "{{hook $CLAUDE_PROJECT_DIR x}}"
    escaped = command.replace('"', '\\"')
    assert _n(f'"command": "{escaped}"') == '"command": "{{hook $CLAUDE_PROJECT_DIR x}}"'


def test_hook_git_toplevel_anchor_is_kept_distinct():
    out = _n('python3 "$(git rev-parse --show-toplevel)/_aitna/akmon/hooks/codex-hook.py" role-on-code')
    assert out == "{{hook $(git rev-parse --show-toplevel) codex-hook}} role-on-code"
    launcher = _n('\\"$(git rev-parse --show-toplevel)/.venv/bin/akmon\\" hook codex-hook')
    assert launcher == "{{hook $(git rev-parse --show-toplevel) codex-hook}}"


def test_absolute_hook_path_is_not_collapsed():
    """F5 guard: a command that hangs from no anchor stays visible; only the path tokens apply."""
    assert _n(f'python3 "{ROOT}/_aitna/akmon/hooks/x.py"') == 'python3 "{{mount}}/hooks/x.py"'
    bare = norm.Ctx(root="", mount="", tree="", tmp="", version="")
    assert _n('python3 "/tmp/p/_aitna/akmon/hooks/x.py"', bare) == 'python3 "/tmp/p/_aitna/akmon/hooks/x.py"'


def test_tool_package_spelling_is_a_token_and_mounted_spelling_stays():
    assert _n("python3 $(akmon path)/tools/model_routing/init.py --x") == "{{tool model_routing/init}} --x"
    mounted = "python3 _aitna/akmon/tools/model_routing/init.py --x"
    assert _n(mounted) == mounted


def test_parse_error_detail_json():
    line = "ERROR a.b x: invalid JSON: Expecting value: line 1 column 1 (char 0) → fix it"
    assert _n(line) == "ERROR a.b x: invalid JSON: {{parse-error}} → fix it"


def test_parse_error_detail_toml_with_repr_runs_to_the_arrow():
    line = "ERROR a.b x: cannot be read as TOML: Illegal character '\\n' (at line 2, column 5) → fix it"
    assert _n(line) == "ERROR a.b x: cannot be read as TOML: {{parse-error}} → fix it"
    # No arrow: the detail runs to the line end, and the next line is untouched.
    assert _n("x: invalid JSON: boom\nnext") == "x: invalid JSON: {{parse-error}}\nnext"


def test_path_tokens_mount_inside_root_is_mount():
    assert _n(f"{ROOT}/_aitna/akmon/bin/sync.py") == "{{mount}}/bin/sync.py"
    assert _n(f"{ROOT}/src/app.py") == "{{root}}/src/app.py"
    assert _n("/w/tree/x /w/tmp-x/y /w/repo/z") == "{{tree}}/x {{tmp}}/y {{repo}}/z"


def test_path_tokens_longest_first_for_any_nesting():
    ctx = norm.Ctx(root="/w/p", mount="", tree="", tmp="/w/p/tmp", version="")
    assert _n("/w/p/tmp/f", ctx) == "{{tmp}}/f"


def test_point_in_time_tokens_only_for_run_days():
    assert _n(f"on {DAY} at {DAY}T10:11:12Z and {DAY} 10:11:12.5+02:00") == "on {{date}} at {{ts}} and {{ts}}"
    assert _n("stamp 20260927-101112.log") == "stamp {{ts}}.log"
    other = "2020-01-02 2020-01-02T10:11:12Z 20200102-101112"
    assert _n(other) == other


def test_version_token():
    assert _n("akmon 9.8.7") == "akmon {{version}}"


# --- 2. corpus loader -------------------------------------------------------------


@pytest.fixture
def scen_root(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "CORPUS_ROOT", tmp_path)
    (tmp_path / "scenarios" / "cli").mkdir(parents=True)
    return tmp_path


def _write(root: Path, body: str, name: str = "demo", *, sid: str | None = None, ecosystem: str = "shared") -> Path:
    path = root / "scenarios" / "cli" / f"{name}.toml"
    header = (
        f'id = "{sid or "cli/" + name}"\necosystem = "{ecosystem}"\nkind = "cli"\n'
        'covers = ["command:version"]\n[run]\nargv = ["version"]\n'
    )
    path.write_text(header + body, encoding="utf-8")
    return path


_OK_EXPECTED = '[expected]\nexit = 0\nstdout = "x\\n"\n'


def test_loader_accepts_a_minimal_scenario(scen_root):
    scenario = corpus.load_scenario(_write(scen_root, _OK_EXPECTED))
    assert scenario.id == "cli/demo"
    assert scenario.ecosystem == "shared"
    assert scenario.fixture.attach == "native"
    assert scenario.fixture.warmup == "after"  # the native default is a synced consumer


def test_loader_refuses_shared_mount(scen_root):
    with pytest.raises(corpus.CorpusError, match="Python-only"):
        corpus.load_scenario(_write(scen_root, '[fixture]\nattach = "mount"\n' + _OK_EXPECTED))
    python = _write(scen_root, '[fixture]\nattach = "mount"\n' + _OK_EXPECTED, "py", ecosystem="python")
    scenario = corpus.load_scenario(python)
    assert (scenario.fixture.attach, scenario.fixture.warmup) == ("mount", "none")


@pytest.mark.parametrize("fixture", ['attach = "linked"', 'warmup = "later"'])
def test_loader_refuses_unknown_attach_or_warmup(scen_root, fixture):
    with pytest.raises(corpus.CorpusError, match="must be one of"):
        corpus.load_scenario(_write(scen_root, f"[fixture]\n{fixture}\n" + _OK_EXPECTED))


@pytest.mark.parametrize(("raw", "mapped"), [("true", "after"), ("false", "none"), ('"before"', "before")])
def test_loader_warmup_booleans(scen_root, raw, mapped):
    scenario = corpus.load_scenario(_write(scen_root, f"[fixture]\nwarmup = {raw}\n" + _OK_EXPECTED))
    assert scenario.fixture.warmup == mapped


@pytest.mark.parametrize(
    "fields",
    [
        'stdout = "x"\nfindings = []',
        'stdout = "x"\n[expected.stdout_json]\na = 1',
        'stdout = "x"\nfindings = []\nstderr = ""',
        "findings = []\n[expected.stdout_json]\na = 1",
    ],
)
def test_loader_refuses_two_stdout_modes(scen_root, fields):
    with pytest.raises(corpus.CorpusError, match="mutually exclusive"):
        corpus.load_scenario(_write(scen_root, f"[expected]\nexit = 0\n{fields}\n"))


def test_loader_refuses_stderr_with_stderr_contains(scen_root):
    body = '[expected]\nexit = 0\nstdout = ""\nstderr = ""\nstderr_contains = ["usage"]\n'
    with pytest.raises(corpus.CorpusError, match=r"stderr and expected\.stderr_contains"):
        corpus.load_scenario(_write(scen_root, body))


def test_loader_refuses_exit_code_only(scen_root):
    with pytest.raises(corpus.CorpusError, match="nothing beyond its exit code"):
        corpus.load_scenario(_write(scen_root, "[expected]\nexit = 2\n"))


@pytest.mark.parametrize("field", ['stderr_contains = ["usage"]', 'findings = ["OK a.b x: y"]', "findings = []"])
def test_loader_accepts_a_single_non_exit_assertion(scen_root, field):
    scenario = corpus.load_scenario(_write(scen_root, f"[expected]\nexit = 2\n{field}\n"))
    assert scenario.expected.exit == 2


def test_loader_refuses_unseeded_unless_recording(scen_root):
    path = _write(scen_root, "")
    with pytest.raises(corpus.CorpusError, match="not seeded"):
        corpus.load_scenario(path)
    assert corpus.load_scenario(path, strict_seeded=False).expected.seeded is False


def test_loader_refuses_id_not_matching_path(scen_root):
    with pytest.raises(corpus.CorpusError, match="does not match its file path"):
        corpus.load_scenario(_write(scen_root, _OK_EXPECTED, sid="cli/other"))


@pytest.mark.parametrize("item", ["version", "command:", "Command:version", "flag:x", "code:A.B"])
def test_loader_refuses_bad_covers_entry(scen_root, item):
    path = _write(scen_root, _OK_EXPECTED)
    path.write_text(path.read_text().replace('"command:version"', f'"{item}"'), encoding="utf-8")
    with pytest.raises(corpus.CorpusError, match="not a population item"):
        corpus.load_scenario(path)


# --- 3. snapshot ------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    standins = tmp_path / "standins"
    for relative, text in {"bin/verify.py": "code\n", "README.md": "real prose\n", "hooks/h.py": "hook\n"}.items():
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / relative).write_text(text, encoding="utf-8")
    standins.mkdir()
    (standins / "README.md").write_text("stand-in prose\n", encoding="utf-8")
    monkeypatch.setattr(corpus, "STANDIN_ROOT", standins)
    monkeypatch.setattr(corpus, "SNAPSHOT_FILES", ("bin/verify.py", "README.md"))
    monkeypatch.setattr(corpus, "snapshot_hooks", lambda _repo: ["hooks/h.py"])
    return repo, standins, tmp_path / "work"


def test_snapshot_copies_code_from_repo_and_prose_from_standins(fake_repo):
    repo, _standins, work = fake_repo
    tree = corpus.build_snapshot(repo, work)
    assert tree == work / "tree"
    assert (tree / "bin" / "verify.py").read_text() == "code\n"
    assert (tree / "hooks" / "h.py").read_text() == "hook\n"
    assert (tree / "README.md").read_text() == "stand-in prose\n"
    assert sorted(p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file()) == [
        "README.md",
        "bin/verify.py",
        "hooks/h.py",
    ]


def test_snapshot_refuses_orphan_standin(fake_repo):
    repo, standins, work = fake_repo
    (standins / "roles").mkdir()
    (standins / "roles" / "gone.md").write_text("x\n", encoding="utf-8")
    with pytest.raises(corpus.CorpusError, match=r"roles/gone\.md"):
        corpus.build_snapshot(repo, work)


def test_snapshot_refuses_path_missing_from_repo(fake_repo):
    repo, _standins, work = fake_repo
    (repo / "README.md").unlink()  # the stand-in exists; the repo path still must
    with pytest.raises(corpus.CorpusError, match=r"missing from the repository under test: README\.md"):
        corpus.build_snapshot(repo, work)


def test_shipped_standins_are_all_carried():
    assert set(corpus.standins()) <= set(corpus.SNAPSHOT_FILES)


def test_tree_remove_deletes_from_the_private_copy_only(tmp_path):
    snapshot = tmp_path / "tree"
    (snapshot / "bin").mkdir(parents=True)
    (snapshot / "bin" / "verify.py").write_text("x", encoding="utf-8")
    fixture = corpus.FixtureSpec(tree_remove=("bin/verify.py",))
    private = corpus._tree_with_overrides(snapshot, tmp_path, "cli/demo", "1.0", fixture)
    assert not (private / "bin" / "verify.py").exists()
    assert (snapshot / "bin" / "verify.py").is_file()  # the shared snapshot stays whole


def test_tree_remove_of_an_absent_path_is_refused(tmp_path):
    (tmp_path / "tree").mkdir()
    fixture = corpus.FixtureSpec(tree_remove=("bin/nope.py",))
    with pytest.raises(corpus.CorpusError, match="does not carry"):
        corpus._tree_with_overrides(tmp_path / "tree", tmp_path, "cli/demo", "1.0", fixture)


# --- 3b. shipped JSON registration (C102) ------------------------------------------

self_ci = _load("conformance_self_ci", _AKMON / "meta" / "self_ci.py")

#: Directories where a reader's shipped JSON sibling lives (C102). Every ``*.json`` found here
#: must reach a consumer through both the corpus snapshot and self-CI's synthetic fixture tree,
#: or a newly added data file silently drops out of one of them: nothing else fails. None of
#: these directories carries a JSON test fixture today (checked: only readers' own data files
#: turn up) — if one ever does, exclude it here by name with the reason, the way the corpus
#: snapshot excludes its prose stand-ins.
_DATA_JSON_DIRS = ("bin", "common", "hooks", "tools", "src/akmon")


def _shipped_json_files() -> list[str]:
    """Every ``*.json`` under the shipped directories, repo-relative posix paths."""
    found = []
    for base in _DATA_JSON_DIRS:
        found.extend(
            path.relative_to(_AKMON).as_posix()
            for path in sorted((_AKMON / base).rglob("*.json"))
            if "__pycache__" not in path.parts
        )
    return found


def test_every_shipped_json_file_is_in_the_corpus_snapshot():
    """An unregistered JSON file is invisible to the corpus forever: it never reaches the
    snapshot a scenario's fixture is built from, so its reader is exercised against nothing."""
    listed = set(corpus.SNAPSHOT_FILES) | {f"hooks/{name}" for name in corpus.snapshot_hooks(_AKMON)}
    missing = [path for path in _shipped_json_files() if path not in listed]
    assert not missing, f"missing from corpus.SNAPSHOT_FILES: {missing}"


def test_every_snapshot_json_entry_exists_on_disk():
    """The reverse: a renamed or deleted data file must not linger in SNAPSHOT_FILES."""
    dangling = [path for path in corpus.SNAPSHOT_FILES if path.endswith(".json") and not (_AKMON / path).is_file()]
    assert not dangling, f"corpus.SNAPSHOT_FILES names a JSON absent from disk: {dangling}"


def test_every_shipped_json_file_is_in_the_self_ci_fixture(tmp_path):
    """Same silent-drop risk on the other consumer of a file list: self-CI's synthetic tree.

    Calls the real ``self_ci._make_fixture`` into a scratch root rather than re-deriving its
    file list by parsing source or duplicating a local copy of it — the production function
    stays the single owner of the list, and this only checks its observable effect (the files it
    materializes), the least brittle option for a list local to a function body.
    """
    self_ci._make_fixture(tmp_path, _AKMON)
    mounted = tmp_path / "_aitna" / "akmon"
    missing = [path for path in _shipped_json_files() if not (mounted / path).is_file()]
    assert not missing, f"missing from self_ci._make_fixture's file list: {missing}"


def test_every_self_ci_fixture_json_entry_exists_on_disk(tmp_path):
    """The reverse for self-CI: ``_write`` falls back to a literal placeholder body for a listed
    relative path whose source is not a real file, so a materialized JSON holding that
    placeholder marks a stale entry in ``_make_fixture``'s file list rather than a real data file.
    """
    self_ci._make_fixture(tmp_path, _AKMON)
    mounted = tmp_path / "_aitna" / "akmon"
    placeholders = [
        path.relative_to(mounted).as_posix()
        for path in sorted(mounted.rglob("*.json"))
        if path.read_text(encoding="utf-8") == "fixture placeholder\n"
    ]
    assert not placeholders, f"self_ci._make_fixture wrote a placeholder for a missing source: {placeholders}"


# --- 4. runner comparison ---------------------------------------------------------

_OWNED = frozenset({"hooks.launcher"})
_STDOUT = (
    "header line\n"
    "OK sync.write .claude/settings.json: written\n"
    "WARN hooks.launcher .venv/bin/akmon: absent\n"
    "ERROR check.runtime x: failed → fix\n"
    "  continuation text\n"
    "OKAY not.a finding\n"
)


@pytest.fixture
def owned(monkeypatch):
    monkeypatch.setattr(runner, "owned_codes", lambda: _OWNED)
    return _OWNED


def test_finding_lines_keeps_findings_but_excluded_codes():
    assert runner.finding_lines(_STDOUT, _OWNED) == [
        "OK sync.write .claude/settings.json: written",
        "ERROR check.runtime x: failed → fix",
    ]
    assert len(runner.finding_lines(_STDOUT, frozenset())) == 3


def test_cover_problems_is_line_level():
    assert runner._cover_problems(("code:check.runtime", "command:check"), _STDOUT) == []
    problems = runner._cover_problems(("code:check.run",), _STDOUT)
    assert problems == ["covers 'code:check.run': no finding line of the actual stdout carries it"]


def _scenario(ecosystem="shared", covers=(), **expected):
    return runner.Scenario(
        id="cli/demo",
        ecosystem=ecosystem,
        kind="cli",
        covers=tuple(covers),
        fixture=corpus.FixtureSpec(),
        env={},
        run=corpus.RunSpec(argv=("x",)),
        expected=corpus.ExpectedSpec(**expected),
    )


def _ctx(tmp_path):
    return norm.Ctx(root=str(tmp_path), mount="", tree="/w/tree", tmp="/w/tmp", version="9.8.7", days=(DAY,))


def test_compare_reports_stderr_contains_mismatch(tmp_path, owned):
    scenario = _scenario(stdout="", stderr_contains=("usage:",))
    assert runner._compare(scenario, 0, "", "usage: akmon\n", _ctx(tmp_path)) == ""
    problems = runner._compare(scenario, 0, "", "error: nope\n", _ctx(tmp_path))
    assert "stderr: expected to contain 'usage:'" in problems


def test_records_findings_only_for_shared_with_owned_line(owned):
    assert runner._records_findings(_scenario(), _STDOUT) is True
    assert runner._records_findings(_scenario(ecosystem="python"), _STDOUT) is False
    assert runner._records_findings(_scenario(), "OK sync.write x: y\n") is False
    assert runner._records_findings(_scenario(), "hooks.launcher mentioned in prose\n") is False


def _round_trip(tmp_path, scenario, exit_code, stdout, stderr):
    ctx = _ctx(tmp_path)
    block = runner._record_block(scenario, exit_code, stdout, stderr, ctx)
    data = tomllib.loads(block)
    expected = corpus._parse_expected(Path("x.toml"), "cli", strict_seeded=True, data=data)
    rerun = _scenario(ecosystem=scenario.ecosystem, covers=scenario.covers)
    rerun = runner.Scenario(**{**rerun.__dict__, "expected": expected})
    return expected, runner._compare(rerun, exit_code, stdout, stderr, ctx)


def test_record_round_trip_stdout_mode(tmp_path, owned):
    stdout = f'OK sync.write {tmp_path}/a "q" \\ on {DAY}: done\n'
    expected, problems = _round_trip(tmp_path, _scenario(), 1, stdout, "warn: 9.8.7\n")
    assert problems == ""
    assert expected.stdout == 'OK sync.write {{root}}/a "q" \\ on {{date}}: done\n'
    assert (expected.exit, expected.stderr, expected.findings) == (1, "warn: {{version}}\n", None)


def test_record_round_trip_findings_mode(tmp_path, owned):
    expected, problems = _round_trip(tmp_path, _scenario(covers=("code:check.runtime",)), 1, _STDOUT, "")
    assert problems == ""
    assert expected.stdout is None
    assert expected.findings == ("OK sync.write .claude/settings.json: written", "ERROR check.runtime x: failed → fix")


def test_record_keeps_hand_written_stderr_contains(tmp_path, owned):
    expected, problems = _round_trip(tmp_path, _scenario(stderr_contains=("usage:",)), 2, "", "usage: akmon x\n")
    assert problems == ""
    assert (expected.stderr, expected.stderr_contains) == (None, ("usage:",))


_JSON = (
    '{"decision": "block", "n": 3, "ok": true, "tags": ["a", "b"], '
    '"hookSpecificOutput": {"hookEventName": "PreToolUse", "inner": {"path": "ROOT/x", "deep": {"k": 1}}}, '
    '"z": {"w": "v"}}'
)


def test_record_round_trip_stdout_json_nested(tmp_path, owned):
    stdout = _JSON.replace("ROOT", str(tmp_path))
    expected, problems = _round_trip(tmp_path, _scenario(stdout_json={}), 0, stdout, "")
    assert problems == ""
    assert expected.stdout_json["hookSpecificOutput"]["inner"] == {"path": "{{root}}/x", "deep": {"k": 1}}


def test_record_round_trip_stdout_json_list_of_objects(tmp_path, owned):
    expected, problems = _round_trip(tmp_path, _scenario(stdout_json={}), 0, '{"items": [{"a": 1}, {}]}', "")
    assert problems == ""
    assert expected.stdout_json == {"items": [{"a": 1}, {}]}


def test_record_round_trip_stdout_json_dotted_member_name(tmp_path, owned):
    document = '{"a.b": {"c": 1}, "x": {"y.z": {"k": "v"}}}'
    expected, problems = _round_trip(tmp_path, _scenario(stdout_json={}), 0, document, "")
    assert problems == ""
    assert expected.stdout_json == {"a.b": {"c": 1}, "x": {"y.z": {"k": "v"}}}


def test_record_refuses_a_json_null_loudly(tmp_path, owned):
    # TOML has no null: the record says so instead of writing a scenario file tomllib cannot load.
    with pytest.raises(runner.CorpusError, match="JSON null has no TOML spelling"):
        _round_trip(tmp_path, _scenario(stdout_json={}), 0, '{"reason": null}', "")


# --- 5. release_check display -----------------------------------------------------


def test_display_verify_is_the_akmon_command():
    command = [sys.executable, str(release_check.BIN / "verify.py"), "--strict"]
    assert release_check._display(command) == "akmon verify --strict"


def test_display_akmon_script_is_relative():
    script = release_check.AKMON_ROOT / "tools" / "tasks" / "archive.py"
    assert release_check._display([sys.executable, str(script), "--check"]) == "python3 tools/tasks/archive.py --check"


@pytest.mark.parametrize(
    "command",
    [["uv", "run", "pytest", "-q"], ["/usr/bin/python3", "/elsewhere/x.py"], [sys.executable, "/elsewhere/x.py", "-v"]],
)
def test_display_other_commands_are_joined_as_is(command):
    assert release_check._display(command) == " ".join(command)
