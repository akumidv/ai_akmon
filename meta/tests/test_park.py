"""Tests for the park helper (tools/park/park.py): the note, the lease, the athlos, the ergons, the commands.

The local index is retired (ADR 0028 D12): nothing here expects a row, and a test pins that none is written.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from common import jsondata, project_root

_AKMON = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("park_helper", _AKMON / "tools" / "park" / "park.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass resolves its module by name
    spec.loader.exec_module(module)
    return module


park = _load()
TEXTS = jsondata.read(_AKMON / "tools" / "park" / "park.json")

STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
LAPTOP = "laptop"
ERGON_ID = "C186"
ERGON_NAME = "C186-holders-units"
HOURS = 3600
# The staleness threshold is park.json's, never restated here: a test that spells out 24 would pass
# while the shipped value said something else.
STALE_HOURS = TEXTS["stale_after_hours"]


def _stamp(epoch: float) -> str:
    """An epoch as the stamp the helper writes, built here so no date is spelled out."""
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git inside the test's own folder: no outer repository, no inherited git environment."""
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root, and the cwd: ``AGENTS.md`` beside the dev layer's integration record."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (root / "_aitna").mkdir()
    (root / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository on branch ``main`` with two commits, outside the project."""
    folder = tmp_path / "repo"
    folder.mkdir()
    _git(folder, "init", "-b", "main")
    for name in ("one", "two"):
        (folder / f"{name}.txt").write_text(name, encoding="utf-8")
        _git(folder, "add", f"{name}.txt")
        _git(folder, "commit", "-m", name)
    return folder.resolve()


@pytest.fixture
def linked(tmp_path: Path) -> tuple[Path, Path]:
    """A main checkout and a linked worktree ``.worktrees/C186-holders-units.1`` of it."""
    main = tmp_path / "main"
    main.mkdir()
    (main / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (main / "_aitna").mkdir()
    (main / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    _git(main, "init", "-b", "main")
    _git(main, "add", "AGENTS.md")
    _git(main, "commit", "-m", "init")
    worktree = main / ".worktrees" / f"{ERGON_NAME}.1"
    _git(main, "worktree", "add", "-b", "athlos-1", str(worktree))
    return main.resolve(), worktree.resolve()


def _ergon(project: Path, name: str = "C183-park-helper") -> Path:
    return project / "_aitna" / ".ergon" / name


def _closed(project: Path, name: str) -> Path:
    return project / "_aitna" / ".ergon" / ".closed" / name


def _write(project: Path, *extra: str, ergon_id: str = "C183", name: str = "park-helper") -> int:
    argv = ["write", ergon_id, "--name", name, "--goal", "Build the helper", "--next", "Twin it"]
    return park.main([*argv, *extra, "--root", str(project)])


def _run(project: Path, *argv: str) -> int:
    return park.main([*argv, "--root", str(project)])


def _session(session: str = "s1", machine: str = LAPTOP) -> list[str]:
    """The flags that name the holder of a lease."""
    return ["--harness", "claude", "--session-id", session, "--machine", machine]


def _holder(session: str = "s1", machine: str = LAPTOP) -> park.Holder:
    return park.Holder("claude", session, machine, "/work/tree")


def _context(now: float = 1_000_000.0, stale_hours: int = STALE_HOURS, machine: str = LAPTOP) -> park.LeaseContext:
    return park.LeaseContext(now=now, stale_hours=stale_hours, machine=machine)


def _live_context() -> park.LeaseContext:
    return _context(now=time.time())


PLAN = """---
id: C186
name: holders-units
title: Holders and athlos
tasks: C186, C187
---

# Holders and athlos

The target in prose. A line that starts with a dash outside the athlos is not an athlos:

- C186.9 · not read · result: it sits outside the Athlos section

## Athlos

- C186.1 · Lease module · tasks C186 · paths tools/park, meta/tests · harness claude · result: a held athlos is refused
- C186.2 · Athlos file · tasks C186 · after C186.1 · paths tools/park/park.py · result: the athlos file is written
- C186.3 · Docs · tasks C187 · paths docs · zone: park · result: the docs say so
- a line that is not an athlos line
- C186.4

## Notes

- C186.8 · not read · result: it sits after the Athlos section
"""


def _plan_ergon(project: Path, plan_text: str = PLAN, name: str = ERGON_NAME) -> Path:
    ergon = _ergon(project, name)
    ergon.mkdir(parents=True)
    (ergon / "PLAN.md").write_text(plan_text, encoding="utf-8")
    return ergon


def _athlos(project: Path, number: int, *extra: str, session: str = "s1") -> int:
    return _run(project, "athlos", ERGON_ID, "--number", str(number), *extra, *_session(session))


def _make_athlos(ergon: Path, number: int, label: str, *, done: bool = False, steps: tuple[str, ...] = ()) -> Path:
    """An athlos folder written straight from the types, with no lease."""
    header = park.ParkFields(
        id=ERGON_ID,
        name="holders-units",
        next_action="the result",
        plan=ERGON_ID,
        athlos=f"{ERGON_ID}.{number}",
        tasks=(ERGON_ID,),
    )
    folder = ergon / str(number)
    park.write_athlos_doc(folder, park.AthlosDoc(header, tuple((step, False) for step in steps), done), TEXTS)
    return folder


def _listed(project: Path, capsys: pytest.CaptureFixture[str], *flags: str) -> list[str]:
    """The lines of ``park list`` with the flags, run as the laptop."""
    capsys.readouterr()
    _run(project, "list", *flags, "--machine", LAPTOP)
    return capsys.readouterr().out.splitlines()


def _ergon_ids(lines: list[str]) -> list[str]:
    """The ergon lines of a listing (the athlos lines are indented), by id."""
    return [line.split(" | ")[0] for line in lines if not line.startswith(" ")]


FULL_FIELDS = park.ParkFields(
    id="C183",
    name="park-helper",
    next_action="Twin it: JS | Python",
    plan="A59",
    athlos="C183.1",
    row="C183",
    branch="_aitna/C183-park-helper",
    revisions=("abc123", "def456"),
    owned_paths=("tools/park/park.py", "meta/tests/test_park.py"),
    tasks=("C183", "C184"),
    sessions=(park.SessionRef("claude", "s-1", "laptop"), park.SessionRef("codex", "s-2", "")),
    origin="claude on laptop",
    readiness="ready for a successor",
    written=_stamp(0),
)
FULL_BODY = park.ParkBody(
    goal="Build the park helper\nand its tests",
    decisions=("D-C183-TWIN", "D-C183-NAME"),
    answers=("owner: go",),
    checks=("pytest: green",),
    unverified=("the JS twin",),
    agents=("none running",),
    purpose=(("question", "is the note enough?"), ("reader_sees", "facts only")),
)

# A note as it was written before ADR 0028 D09: ``state`` first, ``peers`` after ``sessions``.
LEGACY_NOTE = """---
state: resumed
id: C183
name: park-helper
plan: A59
row:
branch: old-branch
revisions:
  - abc123
owned_paths:
next: Twin it
sessions:
  - claude|s-1|laptop
peers:
origin:
readiness:
---

# C183-park-helper

## Goal

Build the helper

## Next action

Twin it
"""


# --------------------------------------------------------------------------------------
# the header and the note
# --------------------------------------------------------------------------------------


def test_header_round_trips_every_field():
    text = park.render_header(FULL_FIELDS)
    assert park.parse_header(text, "PARK.md", TEXTS) == FULL_FIELDS


def test_header_round_trips_with_empty_fields():
    fields = park.ParkFields(id="_T3", name="local-task", next_action="Continue")
    text = park.render_header(fields)
    assert "plan:\n" in text and "revisions:\n" in text and "written:\n" in text
    assert park.parse_header(text, "PARK.md", TEXTS) == fields


def test_header_text_is_flat_and_ordered_and_carries_no_state_or_peers():
    lines = park.render_header(FULL_FIELDS).split("\n")
    assert lines[0] == lines[-2] == "---"
    keys = [line.split(":")[0] for line in lines[1:-2] if not line.startswith("  - ")]
    assert keys == [
        "id",
        "name",
        "plan",
        "athlos",
        "row",
        "branch",
        "revisions",
        "owned_paths",
        "tasks",
        "next",
        "sessions",
        "origin",
        "readiness",
        "written",
    ]
    assert "state" not in keys and "peers" not in keys
    assert "  - claude|s-1|laptop" in lines
    assert "  - codex|s-2|" in lines
    assert f"written: {_stamp(0)}" in lines


def test_the_fields_type_has_no_state_and_no_peers():
    names = {field.name for field in dataclasses.fields(park.ParkFields)}
    assert not names & {"state", "peers"}
    assert {"athlos", "tasks", "written"} <= names


def test_note_round_trips_header_and_body():
    text = park.render_note(FULL_FIELDS, FULL_BODY, TEXTS)
    fields, body = park.parse_note(text, "PARK.md", TEXTS)
    assert fields == FULL_FIELDS
    assert body == FULL_BODY


def test_note_without_purpose_has_no_purpose_section():
    text = park.render_note(FULL_FIELDS, park.ParkBody(goal="g"), TEXTS)
    assert "## Purpose" not in text
    assert "## Next action\n\nTwin it: JS | Python" in text


def test_the_retired_state_rewrite_is_gone():
    assert not hasattr(park, "with_state")
    assert not hasattr(park, "WriteOptions")


def test_a_note_written_before_the_state_dropped_still_parses_and_the_legacy_keys_are_ignored():
    fields, body = park.parse_note(LEGACY_NOTE, "PARK.md", TEXTS)
    assert fields == park.ParkFields(
        id="C183",
        name="park-helper",
        next_action="Twin it",
        plan="A59",
        branch="old-branch",
        revisions=("abc123",),
        sessions=(park.SessionRef("claude", "s-1", "laptop"),),
    )
    assert body.goal == "Build the helper"
    rewritten = park.render_header(fields)
    assert "state:" not in rewritten and "peers:" not in rewritten


def test_a_legacy_peers_list_with_items_is_ignored_too():
    text = LEGACY_NOTE.replace("peers:\n", "peers:\n  - sibling session on B8\n")
    fields, _body = park.parse_note(text, "PARK.md", TEXTS)
    assert fields.sessions == (park.SessionRef("claude", "s-1", "laptop"),)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "c1"}, "id c1 is not a task id"),
        ({"id": "C"}, "id C is not a task id"),
        ({"plan": "plan"}, "plan plan is not a task id"),
        ({"athlos": "C183"}, "athlos C183 is not an athlos id"),
        ({"athlos": "C183.x"}, "athlos C183.x is not an athlos id"),
        ({"name": "Park Helper"}, "name Park Helper is not kebab-case"),
        ({"name": "park--helper"}, "is not kebab-case"),
        ({"next_action": "two\nlines"}, "next must be a single line"),
        ({"branch": "a\rb"}, "branch must be a single line"),
        ({"origin": " padded "}, "origin must be a single line"),
        ({"written": "a\nb"}, "written must be a single line"),
        ({"next_action": ""}, "next must not be empty"),
        ({"revisions": ("a\nb",)}, "revision must be a single line"),
        ({"tasks": ("",)}, "task must not be empty"),
        ({"sessions": (park.SessionRef("a|b", "s", "m"),)}, "is not harness|session_id|machine"),
    ],
)
def test_fields_are_refused_at_the_boundary(change, message):
    fields = dataclasses.replace(FULL_FIELDS, **change)
    with pytest.raises(park.ParkError, match=re.escape(message)):
        park.check_fields(fields, TEXTS)
    with pytest.raises(park.ParkError):
        park.render_note(fields, FULL_BODY, TEXTS)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"goal": ""}, "goal must not be empty"),
        ({"goal": "a\n## Goal\nb"}, "goal has a line that starts with '## '"),
        ({"goal": "padded "}, "goal must not have surrounding whitespace"),
        ({"decisions": ("a\nb",)}, "decision must be a single line"),
        ({"purpose": (("Bad Key", "v"),)}, "purpose key Bad Key must be"),
        ({"purpose": (("key", ""),)}, "purpose key must not be empty"),
    ],
)
def test_body_is_refused_at_the_boundary(change, message):
    body = dataclasses.replace(FULL_BODY, **change)
    with pytest.raises(park.ParkError, match=re.escape(message)):
        park.check_body(body, TEXTS)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no header\n", "no header between two '---' lines"),
        ("---\nid: C1\n", "no header between two '---' lines"),
        ("---\nid: C1\nid: C1\n---\n", "header key id is unknown or repeated"),
        ("---\nbogus: 1\n---\n", "header key bogus is unknown or repeated"),
        ("---\n  - orphan\n---\n", "is a list item with no list key above it"),
        ("---\nid: C1\n  - x\n---\n", "is a list item with no list key above it"),
        ("---\nrevisions: a\n---\n", "header key revisions takes a single value"),
        ("---\nID C1\n---\n", "is neither 'key: value' nor an indented '- item'"),
        ("---\nid: C1\nname: n\n---\n", "no value for next"),
        ("---\nid: c1\nname: n\nnext: x\n---\n", "id c1 is not a task id"),
    ],
)
def test_malformed_headers_are_refused(text, message):
    with pytest.raises(park.ParkError, match=re.escape(message)):
        park.parse_header(text, "PARK.md", TEXTS)


# --------------------------------------------------------------------------------------
# write: the ergon, the note header read from git, the resume prompt
# --------------------------------------------------------------------------------------


def test_write_creates_the_ergon_with_both_files_and_no_lease(project, capsys):
    assert _write(project, "--plan", "A59", "--decision", "D-X") == 0
    assert capsys.readouterr().out == "_aitna/.ergon/C183-park-helper\n"
    ergon = _ergon(project)
    fields, body = park.parse_note((ergon / "PARK.md").read_text(encoding="utf-8"), "PARK.md", TEXTS)
    assert (fields.id, fields.name, fields.plan) == ("C183", "park-helper", "A59")
    assert body.goal == "Build the helper"
    assert body.decisions == ("D-X",)
    assert (ergon / "RESUME.md").is_file()
    assert sorted(path.name for path in ergon.iterdir()) == ["PARK.md", "RESUME.md"]


def test_the_written_note_has_no_state_and_no_peers_key(project):
    _write(project)
    lines = (_ergon(project) / "PARK.md").read_text(encoding="utf-8").split("\n")
    header = lines[1 : lines.index("---", 1)]
    keys = [line.split(":")[0] for line in header if not line.startswith("  - ")]
    assert "state" not in keys and "peers" not in keys
    assert keys[:2] == ["id", "name"] and keys[-1] == "written"


def test_the_note_records_when_it_was_written(project, monkeypatch):
    monkeypatch.setattr(park, "now_stamp", lambda: "stamp-one")
    _write(project)
    assert park.read_note(_ergon(project), TEXTS)[0].written == "stamp-one"
    monkeypatch.setattr(park, "now_stamp", lambda: "stamp-two")
    assert _write(project) == 0
    assert park.read_note(_ergon(project), TEXTS)[0].written == "stamp-two"


def test_the_written_stamp_is_utc_to_the_second():
    assert STAMP_RE.match(park.now_stamp())
    _write_now = time.time()
    parsed = park._parse_stamp(park.now_stamp(), "HOLDER", TEXTS)
    assert abs(parsed - _write_now) < 5


def test_write_flags_fill_the_header_fields_and_git_fills_the_rest(project):
    code = _write(
        project,
        "--plan",
        "A59",
        "--row",
        "C183",
        "--owned-path",
        "tools/park/park.py",
        "--origin",
        "claude",
        "--readiness",
        "ready",
        "--harness",
        "claude",
        "--session-id",
        "s1",
        "--machine",
        LAPTOP,
        "--check",
        "pytest",
        "--unverified",
        "twin",
        "--answer",
        "go",
        "--agent",
        "none",
    )
    assert code == 0
    fields, body = park.read_note(_ergon(project), TEXTS)
    assert STAMP_RE.match(fields.written)
    assert dataclasses.replace(fields, written="") == park.ParkFields(
        id="C183",
        name="park-helper",
        next_action="Twin it",
        plan="A59",
        row="C183",
        owned_paths=("tools/park/park.py",),
        sessions=(park.SessionRef("claude", "s1", LAPTOP),),
        origin="claude",
        readiness="ready",
    )
    assert (body.checks, body.unverified, body.answers, body.agents) == (("pytest",), ("twin",), ("go",), ("none",))


def test_the_branch_and_the_revisions_are_read_from_git_when_the_note_is_written(project, repo, monkeypatch):
    monkeypatch.chdir(repo)
    assert _write(project) == 0
    fields, _body = park.read_note(_ergon(project), TEXTS)
    assert fields.branch == "main"
    assert fields.revisions == tuple(_git(repo, "log", "-5", "--format=%h").split("\n"))
    assert len(fields.revisions) == 2


def test_outside_a_repository_the_note_has_no_branch_and_no_revisions(project):
    assert _write(project) == 0
    fields, _body = park.read_note(_ergon(project), TEXTS)
    assert (fields.branch, fields.revisions) == ("", ())


def test_a_branch_or_revisions_the_caller_supplies_never_reach_the_note(project, repo):
    fields = park.ParkFields(id="C9", name="long", next_action="Next", branch="stale", revisions=("zzz",))
    ergon = park.write_ergon(fields, park.ParkBody(goal="g"), project, TEXTS, repo)
    written, _body = park.read_note(ergon, TEXTS)
    assert (written.branch, "zzz" in written.revisions) == ("main", False)


def test_git_helpers_answer_empty_outside_a_repository(tmp_path):
    assert park.git_branch(tmp_path) == ""
    assert park.git_revisions(tmp_path) == ()


def test_git_helpers_read_the_branch_and_the_newest_revisions_first(repo):
    assert park.git_branch(repo) == "main"
    revisions = park.git_revisions(repo)
    assert revisions == tuple(_git(repo, "log", "--format=%h").split("\n"))
    assert park.git_revisions(repo, 1) == revisions[:1]


def test_git_helpers_answer_empty_when_git_is_absent(project, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))
    assert park.git_branch(project) == ""
    assert park.git_revisions(project) == ()


@pytest.mark.parametrize("flag", ["--branch", "--revision", "--peer", "--role", "--title", "--state"])
def test_the_retired_write_flags_are_refused(project, flag):
    with pytest.raises(SystemExit) as exc:
        _write(project, flag, "x")
    assert exc.value.code == 2
    assert not _ergon(project).exists()


def test_a_second_write_rewrites_the_note(project):
    _write(project)
    assert _write(project, "--decision", "D-NEW") == 0
    assert park.read_note(_ergon(project), TEXTS)[1].decisions == ("D-NEW",)


def test_session_flags_without_a_harness_are_refused(project, capsys):
    assert _write(project, "--session-id", "s1") == 1
    assert capsys.readouterr().err == "error: --session-id and --machine need --harness\n"
    assert not _ergon(project).exists()


def test_resume_prompt_is_harness_neutral_and_dateless(project):
    _write(project, "--decision", "D-X", "--plan", "A59")
    ergon = _ergon(project)
    resume = (ergon / "RESUME.md").read_text(encoding="utf-8")
    assert "`_aitna/.ergon/C183-park-helper/PARK.md`" in resume
    assert "`akmon tool park/park unpark C183`" in resume
    assert "Twin it" in resume and "- D-X" in resume
    assert "stop is observed" in resume and "otherwise report a blocker" in resume
    assert "(N15)" in resume
    assert str(project) not in resume
    assert not any(line.startswith("/") for line in resume.splitlines())
    assert not DATE_RE.search(resume)
    note_lines = (ergon / "PARK.md").read_text(encoding="utf-8").splitlines()
    assert not any(DATE_RE.search(line) for line in note_lines if not line.startswith("written:"))


def test_a_dev_root_pointer_moves_the_ergon(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (tmp_path / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert _write(tmp_path) == 0
    assert (tmp_path / "tools/ai/.ergon/C183-park-helper/PARK.md").is_file()
    assert "`tools/ai/.ergon/C183-park-helper/PARK.md`" in (
        tmp_path / "tools/ai/.ergon/C183-park-helper/RESUME.md"
    ).read_text(encoding="utf-8")
    assert not (tmp_path / "tools/ai/.local").exists()


def test_a_failure_while_landing_the_files_leaves_nothing_behind(project, monkeypatch):
    def refuse(self, target):
        raise OSError("disk says no")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk says no"):
        _write(project)
    assert not _ergon(project).exists()
    assert [path for path in project.rglob("*") if path.name.endswith(".tmp")] == []


def test_a_failure_keeps_an_existing_ergon_and_removes_only_the_temp_files(project, monkeypatch):
    _write(project)
    ergon = _ergon(project)
    before = {path.name: path.read_bytes() for path in ergon.iterdir()}

    def refuse(self, target):
        raise OSError("disk says no")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk says no"):
        _write(project, "--decision", "D-NEW")
    assert {path.name: path.read_bytes() for path in ergon.iterdir()} == before


def test_a_ergon_with_the_id_and_another_name_is_refused(project, capsys):
    _write(project)
    assert _write(project, name="renamed") == 1
    assert capsys.readouterr().err == (
        "error: ergon C183-park-helper already carries id C183; keep its name or retire it before writing renamed\n"
    )
    assert not _ergon(project, "C183-renamed").exists()


def test_a_closed_ergon_with_the_id_and_another_name_is_refused_too(project, capsys):
    _closed(project, "C183-old").mkdir(parents=True)
    assert _write(project) == 1
    assert capsys.readouterr().err == (
        "error: ergon C183-old already carries id C183; keep its name or retire it before writing park-helper\n"
    )
    assert not _ergon(project).exists()


def test_write_refuses_a_bad_id_and_a_bad_name_before_any_file(project, capsys):
    assert _write(project, ergon_id="c183") == 1
    assert _write(project, name="Bad_Name") == 1
    errors = capsys.readouterr().err.splitlines()
    assert errors[0].startswith("error: id c183 is not a task id")
    assert errors[1].startswith("error: name Bad_Name is not kebab-case")
    assert not (project / "_aitna" / ".ergon").exists()


def test_write_refuses_a_newline_in_a_scalar(project, capsys):
    argv = ["write", "C1", "--name", "n", "--goal", "g", "--next", "a\nb"]
    assert _run(project, *argv) == 1
    assert capsys.readouterr().err == "error: next must be a single line with no surrounding whitespace\n"


def test_local_ids_are_accepted(project):
    assert _write(project, ergon_id="_T7", name="scratch") == 0
    assert _ergon(project, "_T7-scratch").is_dir()


# --------------------------------------------------------------------------------------
# the retired local index (ADR 0028 D12)
# --------------------------------------------------------------------------------------


def _no_index_anywhere(project: Path) -> None:
    assert not (project / "_aitna" / ".local").exists()
    assert list(project.rglob("TASKS.md")) == []


def test_no_command_writes_a_local_index(project, tmp_path):
    _plan_ergon(project)
    bundle = tmp_path / "bundle.md"
    commands = [
        ["write", "C183", "--name", "park-helper", "--goal", "g", "--next", "n"],
        ["unpark", "C183", *_session()],
        ["hold", ERGON_ID, *_session()],
        ["athlos", ERGON_ID, "--number", "1", "--step", "first", *_session()],
        ["release", ERGON_ID, "--number", "1"],
        ["release", ERGON_ID],
        ["list"],
        ["list", "--closed"],
        ["digest", "C183"],
        ["active"],
        ["export", "C183", "--out", str(bundle)],
        ["close", "C183"],
        ["close", ERGON_ID],
    ]
    for argv in commands:
        assert _run(project, *argv) == 0, argv
    _no_index_anywhere(project)


def test_an_existing_local_index_is_left_exactly_as_it_was(project):
    index = project / "_aitna" / ".local" / "TASKS.md"
    index.parent.mkdir(parents=True)
    index.write_text("# TASKS — local index\n\n- C183 · t · active · engineer · g\n", encoding="utf-8")
    before = index.read_bytes()
    _write(project)
    _run(project, "unpark", "C183", *_session())
    _run(project, "list")
    _run(project, "close", "C183")
    assert index.read_bytes() == before
    assert sorted(path.name for path in index.parent.iterdir()) == ["TASKS.md"]


def test_the_project_index_is_never_touched(project):
    project_index = project / "_aitna" / "TASKS.md"
    project_index.write_text("- C183 · t · active · engineer · g\n", encoding="utf-8")
    before = project_index.read_bytes()
    _write(project)
    _run(project, "unpark", "C183")
    assert project_index.read_bytes() == before
    assert sorted(path.name for path in (project / "_aitna").iterdir() if path.is_file()) == [".akmon.toml", "TASKS.md"]


# --------------------------------------------------------------------------------------
# the lease: HOLDER per unit
# --------------------------------------------------------------------------------------


def test_the_lease_is_created_exclusively(tmp_path):
    unit = tmp_path / "unit"
    lease = park.acquire_lease(unit, _holder(), TEXTS, _context())
    assert (unit / "HOLDER").is_file()
    assert park.read_lease(unit, TEXTS) == lease
    with pytest.raises(FileExistsError):
        park._write_exclusive(unit / "HOLDER", "not allowed to replace")
    assert park.read_lease(unit, TEXTS) == lease


def test_the_lease_file_records_harness_session_machine_worktree_and_the_time_written(tmp_path):
    park.acquire_lease(tmp_path, _holder(), TEXTS, _context(now=1_000_000.0))
    lines = (tmp_path / "HOLDER").read_text(encoding="utf-8").split("\n")
    assert lines == [
        "---",
        "harness: claude",
        "session: s1",
        "machine: laptop",
        "worktree: /work/tree",
        f"written: {_stamp(1_000_000.0)}",
        "---",
        "",
    ]


def test_a_lease_round_trips_and_a_time_that_is_not_one_is_refused():
    lease = park.Lease(_holder(), 1_000_000.0)
    assert park.parse_lease(park.render_lease(lease), "HOLDER", TEXTS) == lease
    odd = "---\nharness: claude\nsession: s1\nmachine: laptop\nworktree:\nwritten: yesterday\n---\n"
    # a corrupt stamp is refused, never read as the epoch: 0.0 would call a live holder's unit free
    with pytest.raises(park.ParkError, match="written yesterday is not a UTC stamp"):
        park.parse_lease(odd, "HOLDER", TEXTS)
    with pytest.raises(park.ParkError, match="no header between two '---' lines"):
        park.parse_lease("garbage\n", "HOLDER", TEXTS)


def test_a_unit_with_no_lease_reads_free(tmp_path):
    assert park.read_lease(tmp_path, TEXTS) is None


def test_a_second_session_is_refused_with_the_holder_named(tmp_path):
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    before = (tmp_path / "HOLDER").read_bytes()
    with pytest.raises(park.ParkError) as exc:
        park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context())
    message = str(exc.value)
    assert f"{tmp_path.name} is held by claude s1 laptop /work/tree" in message
    assert "--takeover" in message
    assert (tmp_path / "HOLDER").read_bytes() == before


def test_a_lease_is_stale_by_age_past_the_threshold_and_judged_on_read():
    lease = park.Lease(_holder(), 1_000_000.0)
    assert not park.lease_is_stale(lease, _context(now=1_000_000.0 + (STALE_HOURS - 1) * HOURS))
    # exactly the threshold is not past it: the lease still holds
    assert not park.lease_is_stale(lease, _context(now=1_000_000.0 + STALE_HOURS * HOURS))
    assert park.lease_is_stale(lease, _context(now=1_000_000.0 + STALE_HOURS * HOURS + 1))
    assert park.lease_is_stale(lease, _context(now=1_000_000.0 + 2 * HOURS, stale_hours=1))
    assert park.lease_is_stale(lease, _context(now=1_000_000.0 + 1, stale_hours=0))
    assert park.Lease(_holder(), 100.0).age_seconds(50.0) == 0.0  # a clock behind the file is never negative


def test_another_machines_lease_is_stale_at_once():
    lease = park.Lease(_holder(machine="desktop"), 1_000_000.0)
    assert park.lease_is_stale(lease, _context(now=1_000_000.0, machine=LAPTOP))
    assert not park.lease_is_stale(lease, _context(now=1_000_000.0, machine="desktop"))
    assert not park.lease_is_stale(lease, _context(now=1_000_000.0, machine=""))  # no machine to compare against


def test_a_stale_lease_is_refused_too_and_taken_over_only_on_the_owners_word(tmp_path):
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context(now=1_000_000.0))
    later = _context(now=1_000_000.0 + 48 * HOURS)
    with pytest.raises(park.ParkError, match="whose lease is stale; take it over only on the owner's word"):
        park.acquire_lease(tmp_path, _holder("s2"), TEXTS, later)
    assert park.read_lease(tmp_path, TEXTS).holder.session_id == "s1"
    taken = park.acquire_lease(tmp_path, _holder("s2"), TEXTS, later, takeover=True)
    assert park.read_lease(tmp_path, TEXTS) == taken
    assert taken.holder.session_id == "s2"


def test_a_live_lease_is_taken_over_only_with_the_flag(tmp_path):
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    with pytest.raises(park.ParkError, match="is held by claude s1"):
        park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context())
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    assert park.read_lease(tmp_path, TEXTS).holder.session_id == "s2"


def test_a_takeover_keeps_the_replaced_holder_among_the_notes_sessions(tmp_path):
    fields = park.ParkFields(id="C9", name="long", next_action="Next")
    note = park.render_note(fields, park.ParkBody(goal="g"), TEXTS) + "\nhand-written line\n"
    (tmp_path / "PARK.md").write_text(note, encoding="utf-8")
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    updated, body = park.read_note(tmp_path, TEXTS)
    assert updated.sessions == (park.SessionRef("claude", "s1", LAPTOP),)
    assert body.goal == "g"
    assert (tmp_path / "PARK.md").read_text(encoding="utf-8").endswith("hand-written line\n")
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context(), takeover=True)
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    assert park.read_note(tmp_path, TEXTS)[0].sessions.count(park.SessionRef("claude", "s1", LAPTOP)) == 1


def test_a_takeover_leaves_the_notes_body_byte_for_byte_as_it_was(tmp_path):
    fields = park.ParkFields(id="C9", name="long", next_action="Next")
    note = park.render_note(fields, park.ParkBody(goal="g"), TEXTS)
    (tmp_path / "PARK.md").write_text(note, encoding="utf-8")

    def body_of(text: str) -> str:
        return text.split("\n---\n", 1)[1]

    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    for session in ("s2", "s3", "s4"):
        park.acquire_lease(tmp_path, _holder(session), TEXTS, _context(), takeover=True)
    assert body_of((tmp_path / "PARK.md").read_text(encoding="utf-8")) == body_of(note)
    assert len(park.read_note(tmp_path, TEXTS)[0].sessions) == 3


@pytest.mark.parametrize("holder", [park.Holder("", "s1", LAPTOP, "/w"), park.Holder("claude", "", LAPTOP, "/w")])
def test_a_holder_with_no_harness_or_no_session_is_not_recorded_among_the_sessions(tmp_path, holder):
    fields = park.ParkFields(id="C9", name="long", next_action="Next")
    note = park.render_note(fields, park.ParkBody(goal="g"), TEXTS)
    (tmp_path / "PARK.md").write_text(note, encoding="utf-8")
    park.acquire_lease(tmp_path, holder, TEXTS, _context())
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    assert (tmp_path / "PARK.md").read_text(encoding="utf-8") == note
    assert park.read_note(tmp_path, TEXTS)[0].sessions == ()


def test_a_takeover_of_a_unit_with_no_note_keeps_the_replaced_holder_in_a_pending_record(tmp_path):
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["HOLDER", "SESSIONS"]
    assert park.read_pending_sessions(tmp_path, TEXTS) == (park.SessionRef("claude", "s1", LAPTOP),)
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context(), takeover=True)
    assert park.read_pending_sessions(tmp_path, TEXTS) == (
        park.SessionRef("claude", "s1", LAPTOP),
        park.SessionRef("claude", "s2", LAPTOP),
    )


def test_a_takeover_of_a_athlos_keeps_the_replaced_holder_in_the_athlos_file(tmp_path):
    header = park.ParkFields(id="C9", name="long", next_action="Next", athlos="C9.1")
    doc = park.AthlosDoc(header, (("first", False),))
    (tmp_path / "ATHLOS.md").write_text(park.render_athlos_doc(doc, TEXTS), encoding="utf-8")
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    kept = park.read_athlos_doc(tmp_path / "ATHLOS.md", TEXTS)
    assert kept.header.sessions == (park.SessionRef("claude", "s1", LAPTOP),)
    assert kept.steps == (("first", False),)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["ATHLOS.md", "HOLDER"]


def test_a_takeover_stops_before_the_lease_changes_when_the_note_does_not_parse(tmp_path):
    (tmp_path / "PARK.md").write_text("not a note\n", encoding="utf-8")
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    before = (tmp_path / "HOLDER").read_bytes()
    with pytest.raises(park.ParkError, match="no header between two '---' lines"):
        park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    assert (tmp_path / "HOLDER").read_bytes() == before
    assert (tmp_path / "PARK.md").read_text(encoding="utf-8") == "not a note\n"


def test_a_takeover_leaves_no_temporary_file_behind(tmp_path):
    fields = park.ParkFields(id="C9", name="long", next_action="Next")
    (tmp_path / "PARK.md").write_text(park.render_note(fields, park.ParkBody(goal="g"), TEXTS), encoding="utf-8")
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(now=1_000_001.0))  # a renewal
    assert sorted(path.name for path in tmp_path.iterdir()) == ["HOLDER", "PARK.md"]


def test_the_temporary_name_of_an_atomic_write_is_unique_per_call(tmp_path, monkeypatch):
    names: list[str] = []
    real_replace = Path.replace

    def spy(self, target):
        names.append(self.name)
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy)
    park._write_atomically(tmp_path / "HOLDER", "one")
    park._write_atomically(tmp_path / "HOLDER", "two")
    assert len(names) == len(set(names)) == 2
    assert (tmp_path / "HOLDER").read_text(encoding="utf-8") == "two"


def test_two_anonymous_holders_are_not_the_same_session(tmp_path):
    anonymous = park.Holder("", "", LAPTOP, "/w")
    assert not anonymous.same_as(anonymous)
    assert not anonymous.same_as(park.Holder("", "", LAPTOP, "/w"))
    assert not park.Holder("claude", "", LAPTOP, "/w").same_as(park.Holder("claude", "", LAPTOP, "/w"))
    assert _holder("s1").same_as(_holder("s1"))
    park.acquire_lease(tmp_path, anonymous, TEXTS, _context())
    with pytest.raises(park.ParkError, match="is held by \\? \\? laptop /w"):
        park.acquire_lease(tmp_path, anonymous, TEXTS, _context())


def test_a_second_anonymous_hold_through_the_command_line_is_refused(project, capsys):
    _write(project)
    assert _run(project, "hold", "C183", "--machine", LAPTOP) == 0
    capsys.readouterr()
    assert _run(project, "hold", "C183", "--machine", LAPTOP) == 1
    assert "C183-park-helper is held by ? ? laptop" in capsys.readouterr().err


def _stale_lease_of(unit: Path, session: str = "s1", worktree: str = "/work/tree") -> None:
    holder = park.Holder("claude", session, LAPTOP, worktree)
    (unit / "HOLDER").write_text(park.render_lease(park.Lease(holder, time.time() - 30 * HOURS)), encoding="utf-8")


def test_a_takeover_names_the_replaced_holders_uncommitted_paths_before_anything_else(project, repo, capsys):
    _write(project)
    (repo / "scratch.txt").write_text("x", encoding="utf-8")
    (repo / "one.txt").write_text("changed", encoding="utf-8")
    _stale_lease_of(_ergon(project), worktree=str(repo))
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"claude s1 laptop {repo} left uncommitted paths: one.txt, scratch.txt"
    assert lines[1].startswith("C183-park-helper: claude s2 laptop ")
    assert len(lines) == 2


def test_a_takeover_of_a_clean_worktree_names_no_path(project, repo, capsys):
    _write(project)
    _stale_lease_of(_ergon(project), worktree=str(repo))
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_a_takeover_says_when_the_replaced_worktree_cannot_be_read(project, tmp_path, capsys):
    _write(project)
    _stale_lease_of(_ergon(project), worktree=str(tmp_path / "gone"))
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"the uncommitted paths of claude s1 laptop {tmp_path / 'gone'} could not be read"
    assert len(lines) == 2


def test_a_takeover_of_a_free_unit_or_ones_own_lease_names_nothing(project, capsys):
    _write(project)
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert len(capsys.readouterr().out.splitlines()) == 1
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_git_uncommitted_paths_reads_tracked_and_untracked_and_none_when_unreadable(repo, tmp_path):
    assert park.git_uncommitted_paths(str(repo)) == ()
    (repo / "one.txt").write_text("changed", encoding="utf-8")
    (repo / "new.txt").write_text("new", encoding="utf-8")
    assert park.git_uncommitted_paths(str(repo)) == ("one.txt", "new.txt")  # tracked changes first, untracked after
    assert park.git_uncommitted_paths("") is None
    assert park.git_uncommitted_paths(str(tmp_path / "gone")) is None
    plain = tmp_path / "plain"
    plain.mkdir()
    assert park.git_uncommitted_paths(str(plain)) is None


def test_the_same_holder_renews_its_lease(tmp_path):
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context(now=1_000_000.0))
    renewed = park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context(now=1_000_000.0 + 3 * HOURS))
    assert park.read_lease(tmp_path, TEXTS) == renewed
    assert renewed.written == 1_000_000.0 + 3 * HOURS
    # a stale lease of the same holder is the holder's own to renew, with no flag
    again = park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context(now=1_000_000.0 + 90 * HOURS))
    assert again.written == 1_000_000.0 + 90 * HOURS


def test_the_same_session_on_another_worktree_is_still_the_same_holder():
    one = park.Holder("claude", "s1", LAPTOP, "/a")
    assert one.same_as(park.Holder("claude", "s1", LAPTOP, "/b"))
    assert not one.same_as(park.Holder("claude", "s1", "desktop", "/a"))
    assert not one.same_as(park.Holder("codex", "s1", LAPTOP, "/a"))
    assert park.Holder("", "", "", "").label() == "? ? ?"
    assert one.label() == "claude s1 laptop /a"


def test_release_removes_the_lease_and_keeps_the_note(tmp_path):
    (tmp_path / "PARK.md").write_text("note", encoding="utf-8")
    park.acquire_lease(tmp_path, _holder(), TEXTS, _context())
    park.release_lease(tmp_path)
    assert park.read_lease(tmp_path, TEXTS) is None
    assert (tmp_path / "PARK.md").read_text(encoding="utf-8") == "note"
    park.release_lease(tmp_path)  # releasing a free unit is no failure


def test_release_leases_frees_the_plan_and_every_athlos_of_a_ergon(project):
    ergon = _plan_ergon(project)
    athlos = [_make_athlos(ergon, 1, "Lease module"), _make_athlos(ergon, 2, "Athlos file")]
    for unit in (ergon, *athlos):
        park.acquire_lease(unit, _holder(), TEXTS, _context())
    park.release_leases(ergon)
    assert [unit for unit in (ergon, *athlos) if (unit / "HOLDER").exists()] == []


def test_the_state_of_a_unit_is_derived_from_its_lease_and_its_note(tmp_path):
    context = _live_context()
    states = TEXTS["states"]
    assert park.unit_state(tmp_path, TEXTS, context) == states["not_started"] == "not started"
    (tmp_path / "PARK.md").write_text("note", encoding="utf-8")
    assert park.unit_state(tmp_path, TEXTS, context) == states["parked"] == "parked"
    park.acquire_lease(tmp_path, _holder(), TEXTS, context)
    assert park.unit_state(tmp_path, TEXTS, context) == states["active"] == "active"
    stale = _context(now=context.now + 48 * HOURS)
    assert park.unit_state(tmp_path, TEXTS, stale) == "parked"  # a stale lease holds nothing
    foreign = _context(now=context.now, machine="desktop")
    assert park.unit_state(tmp_path, TEXTS, foreign) == "parked"  # another machine's lease holds nothing
    assert park.unit_state(tmp_path, TEXTS, context, athlos_done=True) == states["done"] == "done"


def test_the_lease_of_a_note_less_unit_makes_it_active_and_a_stale_one_not_started(tmp_path):
    context = _live_context()
    park.acquire_lease(tmp_path, _holder(), TEXTS, context)
    assert park.unit_state(tmp_path, TEXTS, context) == "active"
    assert park.unit_state(tmp_path, TEXTS, _context(now=context.now + 48 * HOURS)) == "not started"


def test_exporting_a_ergon_leaves_the_leases_out(project, tmp_path, capsys):
    ergon = _plan_ergon(project)
    _write(project, ergon_id=ERGON_ID, name="holders-units")
    folder = _make_athlos(ergon, 1, "Lease module", steps=("first",))
    park.acquire_lease(ergon, _holder(), TEXTS, _live_context())
    park.acquire_lease(folder, _holder("s2"), TEXTS, _live_context())
    bundle = tmp_path / "out" / "bundle.md"
    capsys.readouterr()
    assert _run(project, "export", ERGON_ID, "--out", str(bundle)) == 0
    assert capsys.readouterr().out == f"{bundle.as_posix()}\n"
    text = bundle.read_text(encoding="utf-8")
    assert text.startswith(f"# akmon ergon bundle: {ERGON_NAME}\n")
    for name in ("PARK.md", "PLAN.md", "RESUME.md", "1/ATHLOS.md"):
        assert f"--- file: {name}\n" in text
    assert "HOLDER" not in text and "session: s1" not in text and "session: s2" not in text
    assert text.count("--- end") == 4
    assert (ergon / "HOLDER").is_file() and (folder / "HOLDER").is_file()  # the export leaves the source alone


def test_export_needs_an_out_flag():
    with pytest.raises(SystemExit) as exc:
        park.main(["export", "C1"])
    assert exc.value.code == 2


# --------------------------------------------------------------------------------------
# the lease through the command line
# --------------------------------------------------------------------------------------


def test_hold_takes_the_lease_of_a_ergon_and_prints_the_holder(project, capsys):
    _write(project)
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    assert capsys.readouterr().out == f"C183-park-helper: claude s1 laptop {Path.cwd()}\n"
    assert (_ergon(project) / "HOLDER").is_file()


def test_a_second_session_on_a_held_ergon_is_refused_with_the_holder_named(project, capsys):
    _write(project)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert "--takeover" in err
    assert park.read_lease(_ergon(project), TEXTS).holder.session_id == "s1"


def test_the_same_session_holds_again_and_a_takeover_needs_the_flag(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1"))
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert park.read_lease(_ergon(project), TEXTS).holder.session_id == "s2"
    assert park.read_note(_ergon(project), TEXTS)[0].sessions == (park.SessionRef("claude", "s1", LAPTOP),)


def test_a_lease_from_another_machine_is_stale_at_once_and_still_needs_the_flag(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1", machine="desktop"))
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2", machine=LAPTOP)) == 1
    assert "whose lease is stale" in capsys.readouterr().err
    assert _run(project, "hold", "C183", *_session("s2", machine=LAPTOP), "--takeover") == 0
    assert park.read_lease(_ergon(project), TEXTS).holder == park.Holder("claude", "s2", LAPTOP, str(Path.cwd()))


def test_a_lease_older_than_the_threshold_is_stale_through_the_command_line(project, capsys):
    _write(project)
    old = park.Lease(_holder("s1"), time.time() - (STALE_HOURS + 1) * HOURS)
    (_ergon(project) / "HOLDER").write_text(park.render_lease(old), encoding="utf-8")
    assert _listed(project, capsys)[0].split(" | ")[2] == "parked"
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    assert "whose lease is stale" in capsys.readouterr().err
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0


def test_a_lease_just_inside_the_threshold_still_holds(project, capsys):
    _write(project)
    fresh = park.Lease(_holder("s1"), time.time() - (STALE_HOURS - 1) * HOURS)
    (_ergon(project) / "HOLDER").write_text(park.render_lease(fresh), encoding="utf-8")
    assert _listed(project, capsys)[0].split(" | ")[2] == "active"
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    assert "whose lease is stale" not in capsys.readouterr().err


def test_release_frees_the_unit_and_a_free_unit_has_no_holder_to_release(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1"))
    capsys.readouterr()
    assert _run(project, "release", "C183") == 0
    assert capsys.readouterr().out == "C183-park-helper\n"
    assert not (_ergon(project) / "HOLDER").exists()
    assert _run(project, "release", "C183") == 1
    assert capsys.readouterr().err == "error: C183-park-helper has no holder file\n"
    assert _run(project, "hold", "C183", *_session("s2")) == 0


def test_hold_and_release_act_on_a_athlos_by_number(project, capsys):
    _plan_ergon(project)
    assert _run(project, "hold", ERGON_ID, "--number", "1") == 1
    assert capsys.readouterr().err == f"error: ergon {ERGON_NAME} has no athlos C186.1\n"
    _athlos(project, 1, "--step", "first", session="s1")
    _run(project, "release", ERGON_ID, "--number", "1")
    folder = _ergon(project, ERGON_NAME) / "1"
    assert not (folder / "HOLDER").exists()
    capsys.readouterr()
    assert _run(project, "hold", ERGON_ID, "--number", "1", *_session("s2")) == 0
    assert capsys.readouterr().out.startswith("1: claude s2 laptop ")
    assert not (_ergon(project, ERGON_NAME) / "HOLDER").exists()  # the athlos's lease is not the plan's


def test_write_into_a_unit_another_session_holds_is_refused_and_the_note_is_untouched(project, capsys):
    _write(project)
    before = (_ergon(project) / "PARK.md").read_bytes()
    _run(project, "hold", "C183", *_session("s1"))
    capsys.readouterr()
    assert _write(project, *_session("s2"), "--decision", "D-NEW") == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert "read the note, hold another unit, or ask the owner" in err
    assert (_ergon(project) / "PARK.md").read_bytes() == before


def test_write_by_the_holder_parks_the_unit_and_releases_the_lease(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1"))
    assert _listed(project, capsys)[0].split(" | ")[2] == "active"
    assert _write(project, *_session("s1")) == 0
    assert not (_ergon(project) / "HOLDER").exists()
    assert _listed(project, capsys)[0].split(" | ")[2] == "parked"


def test_write_over_a_stale_lease_is_refused_and_changes_nothing(project, capsys):
    _write(project)
    _stale_lease_of(_ergon(project))
    lease_before = (_ergon(project) / "HOLDER").read_bytes()
    note_before = (_ergon(project) / "PARK.md").read_bytes()
    capsys.readouterr()
    assert _write(project, *_session("s2"), "--decision", "D-NEW") == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop /work/tree, whose lease is stale;")
    assert "hold --takeover" in err
    assert "the owner's word" in err
    assert err.count("\n") == 1
    assert (_ergon(project) / "HOLDER").read_bytes() == lease_before
    assert (_ergon(project) / "PARK.md").read_bytes() == note_before


def test_write_after_a_takeover_goes_through_and_keeps_the_replaced_holder(project):
    _write(project)
    _stale_lease_of(_ergon(project))
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert _write(project, *_session("s2")) == 0
    assert not (_ergon(project) / "HOLDER").exists()
    sessions = park.read_note(_ergon(project), TEXTS)[0].sessions
    assert sessions == (park.SessionRef("claude", "s1", LAPTOP), park.SessionRef("claude", "s2", LAPTOP))


def test_write_keeps_the_sessions_of_the_note_and_adds_the_new_ones_once(project):
    assert _write(project, *_session("s1")) == 0
    assert _write(project, *_session("s2")) == 0
    assert _write(project, *_session("s1")) == 0
    sessions = park.read_note(_ergon(project), TEXTS)[0].sessions
    assert sessions == (park.SessionRef("claude", "s1", LAPTOP), park.SessionRef("claude", "s2", LAPTOP))
    assert _write(project) == 0  # a write that names no session keeps the ones the note has
    assert park.read_note(_ergon(project), TEXTS)[0].sessions == sessions


def test_write_merges_the_holder_a_takeover_kept_before_the_ergon_had_a_note(project):
    ergon = _ergon(project)
    ergon.mkdir(parents=True)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    _stale_lease_of(ergon)
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert (ergon / "SESSIONS").is_file()
    assert _write(project, *_session("s2")) == 0
    assert park.read_note(ergon, TEXTS)[0].sessions == (
        park.SessionRef("claude", "s1", LAPTOP),
        park.SessionRef("claude", "s2", LAPTOP),
    )
    assert sorted(path.name for path in ergon.iterdir()) == ["PARK.md", "RESUME.md"]


def test_a_takeover_of_a_athlos_is_kept_in_the_athlos_file_through_the_command_line(project):
    ergon = _plan_ergon(project)
    assert _athlos(project, 1, "--step", "first") == 0
    folder = ergon / "1"
    _stale_lease_of(folder)
    assert _run(project, "hold", ERGON_ID, "--number", "1", *_session("s2"), "--takeover") == 0
    assert park.read_athlos_doc(folder / "ATHLOS.md", TEXTS).header.sessions == (
        park.SessionRef("claude", "s1", LAPTOP),
    )
    assert _athlos(project, 1, "--step", "second", session="s2") == 0
    assert park.read_athlos_doc(folder / "ATHLOS.md", TEXTS).header.sessions == (
        park.SessionRef("claude", "s1", LAPTOP),
    )


def test_a_write_that_fails_leaves_no_lease_and_no_folder_behind(project, capsys):
    _write(project)
    capsys.readouterr()
    assert _write(project, ergon_id="C183", name="other-name") == 1  # the id is taken under another name
    assert not (_ergon(project, "C183-other-name")).exists()
    assert _write(project, "--origin", "two\nlines", ergon_id="C184", name="new-ergon") == 1
    assert not (_ergon(project, "C184-new-ergon")).exists()


def test_write_refuses_to_reuse_the_id_and_name_of_a_closed_ergon(project, capsys):
    _write(project)
    assert _run(project, "close", "C183") == 0
    capsys.readouterr()
    assert _write(project) == 1
    err = capsys.readouterr().err
    assert err == "error: ergon C183-park-helper is closed and keeps its id and name; write under another id or name\n"
    assert not _ergon(project).exists()


def test_close_refuses_a_ergon_a_live_session_holds_and_changes_nothing(project, capsys):
    _write(project)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    capsys.readouterr()
    assert _run(project, "close", "C183", *_session("s2")) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert err.count("\n") == 1
    assert (_ergon(project) / "HOLDER").is_file()
    assert not _closed(project, "C183-park-helper").exists()


def test_close_refuses_a_ergon_whose_athlos_a_live_session_holds(project, capsys):
    ergon = _plan_ergon(project)
    _write(project, ergon_id=ERGON_ID, name="holders-units")
    assert _athlos(project, 1, "--step", "first", session="s1") == 0
    capsys.readouterr()
    assert _run(project, "close", ERGON_ID, *_session("s2")) == 1
    assert capsys.readouterr().err.startswith("error: 1 is held by claude s1 laptop ")
    assert (ergon / "1" / "HOLDER").is_file()


def test_close_by_the_holder_releases_its_leases_and_a_stale_lease_does_not_block(project, capsys):
    _write(project)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    assert _run(project, "close", "C183", *_session("s1")) == 0
    assert list(_closed(project, "C183-park-helper").rglob("HOLDER")) == []
    _write(project, ergon_id="C184", name="second")
    _stale_lease_of(_ergon(project, "C184-second"))
    capsys.readouterr()
    assert _run(project, "close", "C184", *_session("s2")) == 0
    assert list(_closed(project, "C184-second").rglob("HOLDER")) == []


def test_close_over_an_existing_closed_ergon_is_one_line_and_changes_nothing(project, capsys):
    _write(project)
    target = _closed(project, "C183-park-helper")
    target.mkdir(parents=True)
    (target / "mark").write_text("old", encoding="utf-8")
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    capsys.readouterr()
    assert _run(project, "close", "C183", *_session("s1")) == 1
    err = capsys.readouterr().err
    assert err == (
        "error: ergon C183-park-helper was not closed: _aitna/.ergon/.closed/C183-park-helper already exists\n"
    )
    assert (_ergon(project) / "HOLDER").is_file()
    assert (_ergon(project) / "PARK.md").is_file()
    assert [path.name for path in target.iterdir()] == ["mark"]


def test_write_by_an_anonymous_session_over_an_anonymous_lease_is_refused(project, capsys):
    _write(project)
    (_ergon(project) / "HOLDER").write_text(
        park.render_lease(park.Lease(park.Holder("", "", "", ""), time.time())), encoding="utf-8"
    )
    capsys.readouterr()
    assert _write(project) == 1
    assert "C183-park-helper is held by ? ? ?" in capsys.readouterr().err


# --------------------------------------------------------------------------------------
# the plan and its athlos lines
# --------------------------------------------------------------------------------------


def test_the_plan_header_and_the_athlos_section_are_parsed():
    plan = park.parse_plan(PLAN, TEXTS)
    assert plan.header == park.PlanHeader(
        id="C186", name="holders-units", title="Holders and athlos", tasks=("C186", "C187")
    )
    assert [line.id for line in plan.athlos] == ["C186.1", "C186.2", "C186.3"]
    assert plan.athlos[0] == park.AthlosLine(
        id="C186.1",
        number=1,
        label="Lease module",
        tasks=("C186",),
        paths=("tools/park", "meta/tests"),
        harness="claude",
        result="a held athlos is refused",
    )
    assert plan.athlos[1].after == ("C186.1",)
    assert plan.athlos[2].tasks == ("C187",)


def test_the_zone_of_an_athlos_line_sits_beside_its_tasks_and_is_empty_when_absent():
    line = park.parse_athlos_line("- C1.1 · A · tasks C1 · zone: docs · result: r", TEXTS)
    assert line is not None and (line.tasks, line.zone, line.result) == (("C1",), "docs", "r")
    plain = park.parse_athlos_line("- C1.1 · A · tasks C1 · result: r", TEXTS)
    assert plain is not None and plain.zone == ""


def test_a_plan_line_with_a_field_the_format_does_not_carry_is_refused():
    text = "---\nid: C1\nname: k\n---\n\n## Athlos\n\n- C1.1 · A · colour red · result: r\n"
    with pytest.raises(park.ParkError) as exc:
        park.parse_plan(text, TEXTS)
    assert str(exc.value) == (
        "C1.1: a plan line carries no field colour (the fields are tasks, after, paths, harness, result, zone)"
    )


def test_a_plan_written_before_the_rename_is_read_and_translated():
    plan = park.parse_plan(PLAN.replace("## Athlos", "## Jobs", 1), TEXTS)
    assert [line.id for line in plan.athlos] == ["C186.1", "C186.2", "C186.3"]


def test_a_plan_with_no_header_and_no_athlos_is_empty():
    assert park.parse_plan("just prose\n", TEXTS) == park.Plan()
    assert park.parse_plan("---\nid: A1\nname: x\n---\n", TEXTS).athlos == ()


def test_an_athlos_line_is_only_a_dash_line_with_an_athlos_id_and_a_label():
    assert park.parse_athlos_line("not a list item", TEXTS) is None
    assert park.parse_athlos_line("- C186.1", TEXTS) is None
    assert park.parse_athlos_line("- C186 · no number", TEXTS) is None
    assert park.parse_athlos_line("- x1.1 · bad id", TEXTS) is None
    line = park.parse_athlos_line("- _T3.2 · A local athlos · tasks _T3 · result: ok", TEXTS)
    assert (line.id, line.number, line.tasks, line.result) == ("_T3.2", 2, ("_T3",), "ok")


def test_an_ergon_with_no_plan_has_none_and_one_with_a_plan_reads_it(project):
    ergon = _ergon(project, "C5-a")
    ergon.mkdir(parents=True)
    assert park.read_plan(ergon, TEXTS) is None
    (ergon / "PLAN.md").write_text(PLAN, encoding="utf-8")
    assert park.read_plan(ergon, TEXTS).header.id == "C186"


def test_an_athlos_folder_is_named_by_its_number_alone(project):
    ergon = _plan_ergon(project)
    assert park.athlos_folder(ergon, 1) is None
    doc = park.AthlosDoc(park.ParkFields(id=ERGON_ID, name="holders-units", next_action="r", athlos="C186.1"))
    park.write_athlos_doc(ergon / "1", doc, TEXTS)
    assert park.athlos_folder(ergon, 1) == ergon / "1"
    assert park.find_athlos_folder(ergon, "C186.1", TEXTS) == ergon / "1"
    assert park._athlos_folders(ergon) == [ergon / "1"]


def test_a_record_in_the_old_jobs_layout_is_read_and_moved_by_the_next_write(project, capsys):
    ergon = _plan_ergon(project)
    legacy = ergon / "jobs" / "1-lease-module"
    legacy.mkdir(parents=True)
    doc = park.AthlosDoc(park.ParkFields(id=ERGON_ID, name="holders-units", next_action="r", athlos="C186.1"))
    # the old file name and the old header key, as ADR 0029 D12 leaves them on disk
    (legacy / "JOB.md").write_text(park.render_athlos_doc(doc, TEXTS).replace("\nathlos:", "\njob:"), encoding="utf-8")
    assert park.athlos_folder(ergon, 1) == legacy
    assert park.read_athlos_doc(park.athlos_file_of(legacy), TEXTS).header.athlos == "C186.1"
    assert park._athlos_folders(ergon) == [legacy]
    assert _athlos(project, 1, "--step", "one") == 0
    capsys.readouterr()
    assert not (ergon / "jobs").exists()
    assert park.read_athlos_doc(ergon / "1" / "ATHLOS.md", TEXTS).steps == (("one", False),)


# --------------------------------------------------------------------------------------
# the athlos file and the athlos command
# --------------------------------------------------------------------------------------


def test_the_first_athlos_write_creates_the_folder_the_file_and_takes_the_lease(project, capsys):
    ergon = _plan_ergon(project)
    assert _athlos(project, 1, "--step", "write the lease", "--step", "test it") == 0
    assert capsys.readouterr().out == f"_aitna/.ergon/{ERGON_NAME}/1\n"
    folder = ergon / "1"
    assert sorted(path.name for path in folder.iterdir()) == ["ATHLOS.md", "HOLDER"]
    doc = park.read_athlos_doc(folder / "ATHLOS.md", TEXTS)
    assert doc.steps == (("write the lease", False), ("test it", False))
    assert not doc.done
    assert dataclasses.replace(doc.header, branch="") == park.ParkFields(
        id=ERGON_ID,
        name="holders-units",
        next_action="a held athlos is refused",
        plan=ERGON_ID,
        athlos="C186.1",
        tasks=("C186",),
    )
    assert park.read_lease(folder, TEXTS).holder.session_id == "s1"


def test_a_label_in_another_script_names_no_folder_so_the_athlos_is_written(project, capsys):
    line = "- C186.1 · Écrire le bail 租约 · tasks C186 · result: le bail existe"
    plan = f"---\nid: C186\nname: holders-units\n---\n\n## Athlos\n\n{line}\n"
    ergon = _plan_ergon(project, plan)
    assert _athlos(project, 1, "--step", "écrire") == 0
    assert capsys.readouterr().out == f"_aitna/.ergon/{ERGON_NAME}/1\n"
    assert (ergon / "1" / "ATHLOS.md").is_file()  # the folder is the number; the label stays on the plan line


def test_a_later_athlos_write_appends_steps_and_keeps_the_old_ones(project):
    folder = _plan_ergon(project) / "1"
    _athlos(project, 1, "--step", "one")
    _athlos(project, 1, "--step", "two")
    doc = park.read_athlos_doc(folder / "ATHLOS.md", TEXTS)
    assert [text for text, _done in doc.steps] == ["one", "two"]
    assert doc.next_step() == "one"


def test_the_athlos_file_marks_steps_and_the_done_marker_and_round_trips(project):
    header = park.ParkFields(id=ERGON_ID, name="holders-units", next_action="the result", athlos="C186.1")
    doc = park.AthlosDoc(header, (("first", True), ("second", False)), done=False)
    text = park.render_athlos_doc(doc, TEXTS)
    assert "## Steps\n\n- [x] first\n- [ ] second\n" in text
    assert park.parse_athlos_doc(text, "ATHLOS.md", TEXTS) == doc
    assert park.parse_athlos_doc(text, "ATHLOS.md", TEXTS).next_step() == "second"
    finished = dataclasses.replace(doc, done=True)
    finished_text = park.render_athlos_doc(finished, TEXTS)
    assert finished_text.rstrip("\n").endswith("\ndone")
    assert park.parse_athlos_doc(finished_text, "ATHLOS.md", TEXTS) == finished
    assert park.AthlosDoc(header, (("a", True),)).next_step() == ""


def test_a_athlos_with_no_steps_reads_back_with_none_and_a_step_named_done_is_no_marker():
    header = park.ParkFields(id=ERGON_ID, name="holders-units", next_action="the result", athlos="C186.1")
    empty = park.render_athlos_doc(park.AthlosDoc(header), TEXTS)
    assert "_none_" in empty
    assert park.parse_athlos_doc(empty, "ATHLOS.md", TEXTS) == park.AthlosDoc(header)
    named = park.AthlosDoc(header, (("done", False),))
    assert park.parse_athlos_doc(park.render_athlos_doc(named, TEXTS), "ATHLOS.md", TEXTS) == named


def test_athlos_done_writes_the_marker_once_and_keeps_it(project, capsys):
    folder = _plan_ergon(project) / "1"
    _athlos(project, 1, "--step", "only", "--done")
    assert park.read_athlos_doc(folder / "ATHLOS.md", TEXTS).done
    _athlos(project, 1, "--step", "late")
    doc = park.read_athlos_doc(folder / "ATHLOS.md", TEXTS)
    assert doc.done and len(doc.steps) == 2
    assert (folder / "ATHLOS.md").read_text(encoding="utf-8").count("\ndone\n") == 1


def test_a_athlos_the_plan_does_not_name_is_refused(project, capsys):
    _plan_ergon(project)
    assert _athlos(project, 9) == 1
    assert capsys.readouterr().err == f"error: ergon {ERGON_NAME} has no athlos C186.9\n"
    assert not (_ergon(project, ERGON_NAME) / "9").exists()


def test_a_ergon_with_no_plan_has_no_athlos_to_write(project, capsys):
    _ergon(project, ERGON_NAME).mkdir(parents=True)
    assert _athlos(project, 1) == 1
    assert capsys.readouterr().err == f"error: ergon {ERGON_NAME} has no PLAN.md, so it has no athlos\n"
    assert not (_ergon(project, ERGON_NAME) / "1").exists()


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("- C186.1 ·  · result: r", "error: athlos C186.1 has no label on its plan line\n"),
        ("- C186.1 · Lease module · tasks C186", f"error: ergon {ERGON_NAME}: athlos C186.1 has no result\n"),
        ("- C186.1 · Lease module · result:", f"error: ergon {ERGON_NAME}: athlos C186.1 has no result\n"),
    ],
)
def test_an_athlos_line_the_helper_cannot_write_from_is_refused_before_writing(project, capsys, line, message):
    ergon = _plan_ergon(project, f"---\nid: C186\nname: holders-units\n---\n\n## Athlos\n\n{line}\n")
    assert _athlos(project, 1, "--step", "x") == 1
    assert capsys.readouterr().err == message
    assert not (ergon / "1").exists()
    assert list(ergon.rglob("HOLDER")) == []


def test_the_athlos_command_prints_the_plans_shared_path_warnings_on_stderr(project, capsys):
    _plan_ergon(
        project,
        "---\nid: C186\nname: holders-units\n---\n\n## Athlos\n\n"
        "- C186.1 · Lease module · paths tools/park · result: r\n"
        "- C186.2 · Athlos file · paths tools/park/park.py · result: r\n",
    )
    assert _athlos(project, 1, "--step", "x") == 0
    captured = capsys.readouterr()
    assert captured.out == f"_aitna/.ergon/{ERGON_NAME}/1\n"
    assert captured.err == "warning: athlos C186.1 C186.2 may run at once and share path tools/park\n"


def test_the_athlos_command_prints_no_warning_for_a_plan_with_no_shared_path(project, capsys):
    _plan_ergon(project)
    capsys.readouterr()
    assert _athlos(project, 1, "--step", "x") == 0
    assert capsys.readouterr().err == ""


def test_a_second_session_writing_a_held_athlos_is_refused_with_the_holder_named(project, capsys):
    folder = _plan_ergon(project) / "1"
    assert _athlos(project, 1, "--step", "mine", session="s1") == 0
    before = (folder / "ATHLOS.md").read_bytes()
    capsys.readouterr()
    assert _athlos(project, 1, "--step", "intruder", session="s2") == 1
    err = capsys.readouterr().err
    assert err.startswith("error: 1 is held by claude s1 laptop ")
    assert (folder / "ATHLOS.md").read_bytes() == before
    assert _athlos(project, 2, "--step", "other athlos", session="s2") == 0  # another athlos is its own unit


def test_two_athlos_that_may_run_at_once_and_share_a_path_are_warned_about():
    plan = park.parse_plan(
        "---\nid: C1\nname: k\n---\n\n## Athlos\n\n"
        "- C1.1 · A · paths tools/park, meta/tests · result: r\n"
        "- C1.2 · B · paths tools/park/park.py, docs · result: r\n"
        "- C1.3 · C · paths docs/ · result: r\n"
        "- C1.4 · D · paths js · result: r\n"
        "- C1.5 · E · result: r\n",
        TEXTS,
    )
    assert park.shared_path_warnings(plan, TEXTS) == [
        "warning: athlos C1.1 C1.2 may run at once and share path tools/park",
        "warning: athlos C1.2 C1.3 may run at once and share path docs",
    ]


def test_a_path_is_shared_by_prefix_by_equality_and_never_by_a_common_stem():
    assert park._paths_overlap("tools/park", "tools/park/park.py")
    assert park._paths_overlap("tools/park/", "tools/park")
    assert park._paths_overlap("docs", "docs")
    assert not park._paths_overlap("tools/park", "tools/parking")
    assert not park._paths_overlap("a", "b")


def test_a_plan_with_no_shared_path_has_no_warning():
    plan = park.parse_plan(PLAN, TEXTS)
    assert [w for w in park.shared_path_warnings(plan, TEXTS) if "docs" in w] == []
    assert park.shared_path_warnings(park.Plan(), TEXTS) == []


@pytest.mark.parametrize(
    "lines",
    [
        ["- C1.1 · A · paths x · result: r", "- C1.2 · B · after C1.1 · paths x · result: r"],
        [
            "- C1.1 · A · paths x · result: r",
            "- C1.2 · B · after C1.1 · paths x · result: r",
            "- C1.3 · C · after C1.2 · paths x · result: r",
        ],
    ],
)
def test_athlos_that_wait_for_each_other_share_no_warning(lines):
    plan = park.parse_plan("---\nid: C1\nname: k\n---\n\n## Athlos\n\n" + "\n".join(lines) + "\n", TEXTS)
    assert park.shared_path_warnings(plan, TEXTS) == []


# --------------------------------------------------------------------------------------
# unpark and digest
# --------------------------------------------------------------------------------------


def test_unpark_takes_the_lease_and_prints_resume_then_the_digest(project, capsys):
    _write(project, "--decision", "D-X", "--answer", "owner: go", "--plan", "A59")
    capsys.readouterr()
    assert _run(project, "unpark", "C183", *_session("s1")) == 0
    out = capsys.readouterr().out
    resume = (_ergon(project) / "RESUME.md").read_text(encoding="utf-8")
    assert out.startswith(resume.rstrip("\n") + "\n\npark C183-park-helper · active\n")
    assert out.endswith("Owner answers:\n- owner: go\n")
    assert park.read_lease(_ergon(project), TEXTS).holder.session_id == "s1"
    _no_index_anywhere(project)


def test_unpark_by_a_second_session_is_refused_with_the_holder_named(project, capsys):
    _write(project)
    _run(project, "unpark", "C183", *_session("s1"))
    capsys.readouterr()
    assert _run(project, "unpark", "C183", *_session("s2")) == 1
    assert capsys.readouterr().err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert _run(project, "unpark", "C183", *_session("s1")) == 0


def test_unpark_names_the_candidates_when_no_ergon_matches(project, capsys):
    _write(project)
    assert _run(project, "unpark", "C999") == 1
    assert capsys.readouterr().err == "error: no ergon with id C999 under _aitna/.ergon; ergons: C183-park-helper\n"


def test_unpark_with_no_ergons_at_all_says_none(project, capsys):
    assert _run(project, "unpark", "C1") == 1
    assert capsys.readouterr().err == "error: no ergon with id C1 under _aitna/.ergon; ergons: none\n"


def test_unpark_names_the_ergons_when_several_carry_the_id(project, capsys):
    for name in ("C5-a", "C5-b", "C50-c"):
        _ergon(project, name).mkdir(parents=True)
    assert _run(project, "unpark", "C5") == 1
    assert capsys.readouterr().err == "error: several ergons carry id C5 under _aitna/.ergon: C5-a, C5-b\n"


def test_digest_of_a_ergon_that_was_never_parked_is_refused(project, capsys):
    _ergon(project, "C5-a").mkdir(parents=True)
    assert _run(project, "digest", "C5") == 1
    assert capsys.readouterr().err == "error: ergon C5-a was never parked: it has no PARK.md\n"


def test_unpark_of_a_ergon_with_no_resume_prompt_is_refused(project, capsys):
    _ergon(project, "C5-a").mkdir(parents=True)
    assert _run(project, "unpark", "C5") == 1
    assert capsys.readouterr().err == "error: ergon C5-a has no RESUME.md; write it again to regenerate it\n"


def test_a_refused_unpark_leaves_no_lease_behind(project):
    _ergon(project, "C5-a").mkdir(parents=True)
    assert _run(project, "unpark", "C5", *_session("s1")) == 1
    assert not (_ergon(project, "C5-a") / "HOLDER").exists()


def test_an_unpark_of_a_ergon_with_a_resume_prompt_and_no_note_leaves_no_lease_behind(project, capsys):
    ergon = _ergon(project, "C5-a")
    ergon.mkdir(parents=True)
    (ergon / "RESUME.md").write_text("# Resume C5-a\n", encoding="utf-8")
    assert _run(project, "unpark", "C5", *_session("s1")) == 1
    assert capsys.readouterr().err == "error: ergon C5-a was never parked: it has no PARK.md\n"
    assert not (ergon / "HOLDER").exists()


def _ergon_with_answers(project: Path, count: int) -> Path:
    body = park.ParkBody(goal="Goal line", answers=tuple(f"answer {number:02d}" for number in range(count)))
    fields = park.ParkFields(id="C9", name="long", next_action="Next")
    return park.write_ergon(fields, body, project, TEXTS, project)


def test_digest_within_the_cap_is_whole_and_has_no_overflow_line(project):
    ergon = _ergon_with_answers(project, 2)
    text = park.digest(ergon, 3000, project, TEXTS)
    assert text == (
        "park C9-long · parked\nGoal: Goal line\nNext action: Next\nOpen decisions: none\n"
        "Owner answers:\n- answer 00\n- answer 01"
    )


def test_digest_names_the_derived_state_of_the_ergon(project):
    ergon = _ergon_with_answers(project, 1)
    park.acquire_lease(ergon, _holder(), TEXTS, _live_context())
    assert park.digest(ergon, 3000, project, TEXTS).startswith("park C9-long · active\n")
    park.release_lease(ergon)
    assert park.digest(ergon, 3000, project, TEXTS).startswith("park C9-long · parked\n")


def test_digest_judges_a_copied_lease_on_the_machine_it_is_given(project):
    ergon = _ergon_with_answers(project, 1)
    park.acquire_lease(ergon, _holder(), TEXTS, _live_context())
    here = park.digest(ergon, 3000, project, TEXTS, machine=LAPTOP)
    elsewhere = park.digest(ergon, 3000, project, TEXTS, machine=f"{LAPTOP}-copy")
    assert here.startswith("park C9-long · active\n")
    assert elsewhere.startswith("park C9-long · parked\n")  # the same state as `list` gives on that machine


def test_digest_is_cut_at_a_whole_line_and_names_the_overflow(project):
    ergon = _ergon_with_answers(project, 10)
    full = park.digest(ergon, 3000, project, TEXTS).split("\n")
    # keep the title, goal, next, decisions-none and the answers heading, plus 2 answers
    kept = full[:7]
    cap = sum(len(line) + 1 for line in kept)
    text = park.digest(ergon, cap, project, TEXTS)
    assert text.split("\n")[:-1] == kept
    assert text.split("\n")[-1] == "… 8 more lines in _aitna/.ergon/C9-long/PARK.md"
    # one character short of the next line: it is dropped whole, never cut; with room for it, it is kept
    assert park.digest(ergon, cap + len("- answer 02"), project, TEXTS).split("\n")[-1].startswith("… 8 more")
    assert park.digest(ergon, cap + len("- answer 02") + 1, project, TEXTS).split("\n")[-1].startswith("… 7 more")


def test_digest_with_a_tiny_cap_is_only_the_overflow_line(project):
    ergon = _ergon_with_answers(project, 1)
    assert park.digest(ergon, 0, project, TEXTS) == "… 6 more lines in _aitna/.ergon/C9-long/PARK.md"


def test_digest_without_a_root_names_the_note_by_ergon(project):
    ergon = _ergon_with_answers(project, 1)
    assert park.digest(ergon, 0, None, TEXTS).endswith("lines in C9-long/PARK.md")


def test_digest_reads_its_own_texts_when_called_alone(project):
    ergon = _ergon_with_answers(project, 1)
    assert park.digest(ergon, 3000).startswith("park C9-long · parked")


def test_digest_indents_the_continuation_of_a_multiline_goal(project):
    fields = park.ParkFields(id="C9", name="long", next_action="Next", plan="A59", readiness="ready")
    ergon = park.write_ergon(fields, park.ParkBody(goal="one\ntwo"), project, TEXTS, project)
    assert park.digest(ergon, 3000, project, TEXTS).split("\n")[:6] == [
        "park C9-long · parked",
        "plan: A59",
        "readiness: ready",
        "Goal: one",
        "  two",
        "Next action: Next",
    ]


def test_digest_carries_the_branch_the_note_read_from_git(project, repo, monkeypatch):
    monkeypatch.chdir(repo)
    _write(project)
    lines = park.digest(_ergon(project), 3000, project, TEXTS).split("\n")
    assert "branch: main" in lines


def test_digest_command_prints_the_digest_and_refuses_a_negative_cap(project, capsys):
    _write(project)
    capsys.readouterr()
    assert _run(project, "digest", "C183", "--cap", "40") == 0
    assert (
        capsys.readouterr().out
        == "park C183-park-helper · parked\n… 4 more lines in _aitna/.ergon/C183-park-helper/PARK.md\n"
    )
    assert _run(project, "digest", "C183", "--cap", "-1") == 1
    assert capsys.readouterr().err == "error: --cap must be a whole number of at least 0, got -1\n"


def test_digest_command_default_cap_is_3000(project, capsys):
    ergon = _ergon_with_answers(project, 400)
    capsys.readouterr()
    _run(project, "digest", "C9")
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1].startswith("… ") and "more lines in _aitna/.ergon/C9-long/PARK.md" in lines[-1]
    assert sum(len(line) + 1 for line in lines[:-1]) <= 3000
    assert ergon.is_dir()


# --------------------------------------------------------------------------------------
# list: the derived state per ergon and per athlos
# --------------------------------------------------------------------------------------


def test_list_of_an_empty_ergon_says_so(project, capsys):
    assert _run(project, "list") == 0
    assert capsys.readouterr().out == "no ergons in _aitna/.ergon\n"
    (project / "_aitna" / ".ergon").mkdir(parents=True)
    _run(project, "list")
    assert capsys.readouterr().out == "no ergons in _aitna/.ergon\n"


def _populate(project: Path) -> None:
    _write(project, "--plan", "A59", "--decision", "D-X", "--decision", "D-Y")
    _write(project, "--plan", "A60", ergon_id="A5", name="second")
    _ergon(project, "C7-never").mkdir()
    _write(project, ergon_id="C20", name="third")
    _run(project, "unpark", "C20", *_session("s1"))


def test_list_prints_one_line_per_ergon_sorted_by_id_with_its_derived_state(project, capsys):
    _populate(project)
    assert _listed(project, capsys) == [
        "A5 | second | parked | A60 | Twin it | 0 | - | 0d",
        "C183 | park-helper | parked | A59 | Twin it | 2 | - | 0d",
        "C20 | third | active | - | Twin it | 0 | - | 0d",
        "C7 | never | not started | - | - | 0 | - | -",
    ]


def test_list_shows_the_branch_the_note_read_from_git(project, repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    _write(project)
    assert _listed(project, capsys) == ["C183 | park-helper | parked | - | Twin it | 0 | main | 0d"]


def test_list_filters_by_plan_and_by_derived_state(project, capsys):
    _populate(project)
    assert _ergon_ids(_listed(project, capsys, "--plan", "A59")) == ["C183"]
    assert _ergon_ids(_listed(project, capsys, "--state", "parked")) == ["A5", "C183"]
    assert _ergon_ids(_listed(project, capsys, "--state", "not started")) == ["C7"]
    assert _ergon_ids(_listed(project, capsys, "--state", "active")) == ["C20"]
    assert _listed(project, capsys, "--plan", "A59", "--state", "active") == ["no ergon matches the filters"]


def test_the_state_filter_is_the_derived_state_and_the_old_status_flag_is_gone(project, capsys):
    _populate(project)
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        _run(project, "list", "--status", "parked")
    assert exc.value.code == 2


def test_list_reads_a_lease_from_another_machine_as_stale(project, capsys):
    _populate(project)
    assert _ergon_ids(_listed(project, capsys, "--state", "active")) == ["C20"]
    capsys.readouterr()
    _run(project, "list", "--machine", "desktop")
    states = {line.split(" | ")[0]: line.split(" | ")[2] for line in capsys.readouterr().out.splitlines()}
    assert states["C20"] == "parked"


def test_a_ergon_with_a_note_in_the_old_format_lists_as_parked_whatever_its_old_state_said(project, capsys):
    ergon = _ergon(project)
    ergon.mkdir(parents=True)
    (ergon / "PARK.md").write_text(LEGACY_NOTE, encoding="utf-8")
    assert _listed(project, capsys)[0].split(" | ")[:3] == ["C183", "park-helper", "parked"]


def test_list_shows_the_athlos_of_a_ergon_under_it_with_their_own_states(project, capsys):
    ergon = _plan_ergon(project)
    _athlos(project, 1, "--step", "write the lease", session="s1")  # held: active
    _make_athlos(ergon, 2, "Athlos file", steps=("later",))  # no lease, no note: not started
    _athlos(project, 3, "--done", session="s1")
    park.release_lease(ergon / "3")  # done stays done whoever held it
    lines = _listed(project, capsys)
    assert lines == [
        f"{ERGON_ID} | holders-units | active | - | - | 0 | - | -",  # a held athlos makes its ergon active
        "  C186.1 | 1 | active | C186 | write the lease | - | 0d",
        "  C186.2 | 2 | not started | C186 | later | - | 0d",
        "  C186.3 | 3 | done | C187 | - | - | 0d",
    ]


def test_a_athlos_with_a_note_and_no_lease_lists_as_parked(project, capsys):
    ergon = _plan_ergon(project)
    folder = _make_athlos(ergon, 1, "Lease module")
    note = park.render_note(
        park.ParkFields(id=ERGON_ID, name="holders-units", next_action="n"), park.ParkBody("g"), TEXTS
    )
    (folder / "PARK.md").write_text(note, encoding="utf-8")
    assert _listed(project, capsys)[1].split(" | ")[2] == "parked"
    park.acquire_lease(folder, park.Holder("claude", "s1", LAPTOP, "/w"), TEXTS, _live_context())
    assert _listed(project, capsys)[1].split(" | ")[2] == "active"


def test_a_ergon_whose_athlos_are_all_done_is_done_and_one_with_a_athlos_left_is_not(project):
    ergon = _plan_ergon(project)
    _make_athlos(ergon, 1, "Lease module", done=True)
    _make_athlos(ergon, 2, "Athlos file", done=True)
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "not started"  # the plan's third athlos has no folder
    _make_athlos(ergon, 3, "Docs", done=True)
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "done"
    _make_athlos(ergon, 3, "Docs")
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "not started"
    (ergon / "PARK.md").write_text("note", encoding="utf-8")
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "parked"
    park.acquire_lease(ergon, _holder(), TEXTS, _live_context())
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "active"


PLAN_WITH_BAD_ID = PLAN.replace("id: C186\n", "id: c3\n", 1)


def test_a_plan_whose_id_is_no_task_id_is_refused_before_the_athlos_file_or_the_lease_exists(project, capsys):
    ergon = _plan_ergon(project, PLAN_WITH_BAD_ID)
    assert _athlos(project, 1, "--step", "x") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"error: ergon {ERGON_NAME}: plan c3 is not a task id "
        "(a capital letter or _T followed by digits, e.g. C183 or _T3)\n"
    )
    assert not (ergon / "1").exists()


def test_a_athlos_file_is_replaced_atomically_and_leaves_no_temporary_file(project, monkeypatch):
    ergon = _plan_ergon(project)
    folder = _make_athlos(ergon, 1, "Lease module", steps=("first",))
    before = (folder / "ATHLOS.md").read_bytes()
    doc = park.read_athlos_doc(folder / "ATHLOS.md", TEXTS)

    def refuse(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        park.write_athlos_doc(folder, dataclasses.replace(doc, steps=(("second", False),)), TEXTS)
    monkeypatch.undo()
    assert (folder / "ATHLOS.md").read_bytes() == before
    assert sorted(path.name for path in folder.iterdir()) == ["ATHLOS.md"]
    park.write_athlos_doc(folder, dataclasses.replace(doc, steps=(("second", False),)), TEXTS)
    assert park.read_athlos_doc(folder / "ATHLOS.md", TEXTS).steps == (("second", False),)
    assert sorted(path.name for path in folder.iterdir()) == ["ATHLOS.md"]


def test_a_ergon_is_active_when_any_of_its_athlos_is_held(project):
    ergon = _plan_ergon(project)
    assert _athlos(project, 1, "--step", "write the lease") == 0
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "active"  # the ergon itself is free
    park.release_lease(ergon / "1")
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "not started"


def test_a_ergon_is_parked_when_any_of_its_athlos_is_parked_and_active_beats_parked(project):
    ergon = _plan_ergon(project)
    folder = _make_athlos(ergon, 1, "Lease module")
    note = park.render_note(
        park.ParkFields(id=ERGON_ID, name="holders-units", next_action="n"), park.ParkBody("g"), TEXTS
    )
    (folder / "PARK.md").write_text(note, encoding="utf-8")
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "parked"
    other = _make_athlos(ergon, 2, "Athlos file")
    park.acquire_lease(other, _holder(), TEXTS, _live_context())
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "active"


def test_a_ergon_with_every_athlos_done_is_done_unless_the_ergon_itself_is_held(project):
    ergon = _plan_ergon(project)
    for number, label in ((1, "Lease module"), (2, "Athlos file"), (3, "Docs")):
        _make_athlos(ergon, number, label, done=True)
    (ergon / "PARK.md").write_text("note", encoding="utf-8")  # a stale note of the plan does not undo done
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "done"
    park.acquire_lease(ergon, _holder(), TEXTS, _live_context())
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "active"


def test_a_planned_athlos_with_a_folder_but_no_athlos_file_blocks_done(project):
    ergon = _plan_ergon(project)
    _make_athlos(ergon, 1, "Lease module", done=True)
    (ergon / "2").mkdir()
    _make_athlos(ergon, 3, "Docs", done=True)
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "not started"


def test_a_ergon_with_no_plan_or_a_plan_with_no_athlos_is_done_by_the_athlos_folders_that_exist(project):
    bare = _ergon(project, "C5-bare")
    bare.mkdir(parents=True)
    assert park.ergon_state(bare, TEXTS, _live_context()) == "not started"  # no folder, nothing done
    empty = _plan_ergon(project, "---\nid: C6\nname: empty\n---\n\n## Athlos\n\n", "C6-empty")
    for ergon in (bare, empty):
        _make_athlos(ergon, 1, "Only", done=True)
        assert park.ergon_state(ergon, TEXTS, _live_context()) == "done"


def test_a_athlos_folder_with_no_athlos_file_is_not_a_athlos_and_blocks_done(project):
    ergon = _plan_ergon(project)
    _make_athlos(ergon, 1, "Lease module", done=True)
    (ergon / "2").mkdir()
    assert park.summarize_athlos(ergon / "2", TEXTS, _live_context()) is None
    assert park.ergon_state(ergon, TEXTS, _live_context()) == "not started"
    summaries, athlos = park.list_ergons(project, park.ListQuery(), TEXTS, _live_context())
    assert [athlos.id for athlos in athlos] == ["C186.1"] and len(summaries) == 1


def test_list_filters_by_task_through_the_plan_header_the_athlos_lines_and_the_athlos_files(project, capsys):
    _plan_ergon(project)  # the plan header names C186 and C187
    _write(project, "--plan", "A59")  # no plan, no athlos: carries no task
    other = _ergon(project, "C300-other")
    other.mkdir()
    (other / "PLAN.md").write_text(
        "---\nid: C300\nname: other\ntasks: C300\n---\n\n## Athlos\n\n- C300.1 · J · tasks C301 · result: r\n",
        encoding="utf-8",
    )
    folder = other / "2"
    park.write_athlos_doc(
        folder,
        park.AthlosDoc(park.ParkFields(id="C300", name="other", next_action="n", athlos="C300.2", tasks=("C302",))),
        TEXTS,
    )
    assert _ergon_ids(_listed(project, capsys, "--task", "C187")) == [ERGON_ID]
    assert _ergon_ids(_listed(project, capsys, "--task", "C300")) == ["C300"]  # the plan header
    assert _ergon_ids(_listed(project, capsys, "--task", "C301")) == ["C300"]  # an athlos line
    assert _ergon_ids(_listed(project, capsys, "--task", "C302")) == ["C300"]  # an athlos's file
    assert _listed(project, capsys, "--task", "C999") == ["no ergon matches the filters"]
    only = _listed(project, capsys, "--task", "C186")
    assert _ergon_ids(only) == [ERGON_ID]


def test_list_with_closed_adds_the_closed_ergons_and_without_it_hides_them(project, capsys):
    _plan_ergon(project)
    _write(project)
    assert _run(project, "close", ERGON_ID) == 0
    assert _ergon_ids(_listed(project, capsys)) == ["C183"]
    assert _ergon_ids(_listed(project, capsys, "--closed")) == ["C183", ERGON_ID]
    assert _ergon_ids(_listed(project, capsys, "--closed", "--task", "C187")) == [ERGON_ID]


def test_list_with_only_closed_ergons_says_there_are_no_ergons_and_with_closed_shows_them(project, capsys):
    _write(project)
    _run(project, "close", "C183")
    assert _listed(project, capsys) == ["no ergons in _aitna/.ergon"]
    assert _ergon_ids(_listed(project, capsys, "--closed")) == ["C183"]


def test_the_closed_folder_is_no_ergon_of_its_own(project, capsys):
    _write(project)
    _run(project, "close", "C183")
    assert park._ergon_names(project) == []
    assert park._ergon_names(project, closed=True) == ["C183-park-helper"]


def test_list_truncates_the_next_action_at_sixty_characters(project, capsys):
    long_next = "x" * 100
    _run(project, "write", "C1", "--name", "n", "--goal", "g", "--next", long_next)
    capsys.readouterr()
    _run(project, "list")
    next_cell = capsys.readouterr().out.split(" | ")[4]
    assert next_cell == "x" * 59 + "…"
    exact = "y" * 60
    _run(project, "write", "C2", "--name", "n", "--goal", "g", "--next", exact)
    capsys.readouterr()
    _run(project, "list")
    assert capsys.readouterr().out.splitlines()[1].split(" | ")[4] == exact


def test_list_age_is_whole_days_from_the_note_mtime(project):
    _write(project)
    note = _ergon(project) / "PARK.md"
    context = _live_context()
    now = context.now
    os.utime(note, (now - 3 * 86400 - 100, now - 3 * 86400 - 100))
    [item], _athlos = park.list_ergons(project, park.ListQuery(), TEXTS, context)
    assert item.age_days == 3
    assert park.format_summary(item, TEXTS).endswith("| 3d")
    os.utime(note, (now + 500, now + 500))  # a clock behind the file never gives a negative age
    assert park.list_ergons(project, park.ListQuery(), TEXTS, context)[0][0].age_days == 0


def test_list_reads_and_writes_nothing(project):
    _populate(project)
    _plan_ergon(project)
    _athlos(project, 1, "--step", "x")
    snapshot = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    before = {p: p.stat().st_mtime_ns for p in snapshot}
    _run(project, "list")
    _run(project, "list", "--state", "parked")
    _run(project, "list", "--closed", "--task", "C186")
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == snapshot
    assert {p: p.stat().st_mtime_ns for p in snapshot} == before
    _no_index_anywhere(project)


def test_list_ignores_folders_that_are_not_ergons(project, capsys):
    _write(project)
    (_ergon(project).parent / "notes").mkdir()
    (_ergon(project).parent / "stray.txt").write_text("x", encoding="utf-8")
    capsys.readouterr()
    _run(project, "list")
    assert capsys.readouterr().out.count("\n") == 1


def test_list_reports_a_ergon_whose_note_does_not_parse_on_its_own_line_and_lists_the_others(project, capsys):
    _write(project)
    _write(project, ergon_id="C184", name="other")
    (_ergon(project) / "PARK.md").write_text("broken\n", encoding="utf-8")
    capsys.readouterr()
    assert _run(project, "list") == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert lines[0] == (
        "C183 | park-helper | unreadable | "
        "C183-park-helper/PARK.md: no header between two '---' lines at the top of the note"
    )
    assert lines[1].startswith("C184 | other | parked | ")


def test_list_names_the_ergon_and_the_athlos_file_of_a_athlos_file_that_does_not_parse(project, capsys):
    ergon = _plan_ergon(project)
    _make_athlos(ergon, 1, "Lease module")
    (ergon / "1" / "ATHLOS.md").write_text("no header\n", encoding="utf-8")
    _write(project)
    lines = _listed(project, capsys)
    assert lines[0].startswith("C183 | park-helper | parked | ")
    assert lines[1] == (
        f"{ERGON_ID} | holders-units | unreadable | "
        f"{ERGON_NAME}/1/ATHLOS.md: no header between two '---' lines at the top of the note"
    )


def test_an_unreadable_ergon_is_listed_whatever_the_filters_say(project, capsys):
    _write(project)
    (_ergon(project) / "PARK.md").write_text("broken\n", encoding="utf-8")
    lines = _listed(project, capsys, "--state", "active")
    assert len(lines) == 1 and lines[0].startswith("C183 | park-helper | unreadable | ")


# --------------------------------------------------------------------------------------
# the local ids and closing an ergon
# --------------------------------------------------------------------------------------


def test_the_next_local_id_counts_over_the_live_and_the_closed_ergons(project):
    assert park.next_local_id(project) == "_T1"
    _ergon(project, "_T1-a").mkdir(parents=True)
    _ergon(project, "_T4-b").mkdir()
    _ergon(project, "C9-not-local").mkdir()
    _closed(project, "_T7-gone").mkdir(parents=True)
    _closed(project, "C8-closed").mkdir()
    assert park.next_local_id(project) == "_T8"
    assert sorted(path.name for path in (project / "_aitna").iterdir()) == [".akmon.toml", ".ergon"]
    _no_index_anywhere(project)


def test_the_next_local_id_skips_every_number_the_legacy_index_holds_and_the_index_is_left_alone(project):
    local = project / "_aitna" / ".local"
    local.mkdir(parents=True)
    legacy = local / "TASKS.md"
    rows = ["# TASKS", "", "- _T6 \u00b7 plan: a \u00b7 active", "- C9 \u00b7 not local", "- _T12 \u00b7 b"]
    text = "\n".join([*rows, "  - _T40 \u00b7 nested", "_T30 \u00b7 no bullet", ""])
    legacy.write_text(text, encoding="utf-8")
    before = legacy.read_bytes()
    _ergon(project, "_T2-a").mkdir(parents=True)
    assert park.next_local_id(project) == "_T13"
    _closed(project, "_T20-gone").mkdir(parents=True)
    assert park.next_local_id(project) == "_T21"
    assert legacy.read_bytes() == before


def test_the_local_id_command_prints_the_next_free_id_and_writes_nothing(project, capsys):
    assert _run(project, "local-id") == 0
    assert capsys.readouterr().out == "_T1\n"
    assert not (project / "_aitna" / ".ergon").exists()
    _ergon(project, "_T2-a").mkdir(parents=True)
    _closed(project, "_T5-gone").mkdir(parents=True)
    assert _run(project, "local-id") == 0
    assert capsys.readouterr().out == "_T6\n"


def test_the_local_id_command_takes_no_holder_flags(project):
    with pytest.raises(SystemExit) as exc:
        _run(project, "local-id", "--harness", "claude")
    assert exc.value.code == 2


def test_closing_the_highest_local_ergon_never_frees_its_number(project):
    assert _write(project, ergon_id="_T1", name="one") == 0
    assert _write(project, ergon_id="_T2", name="two") == 0
    assert park.next_local_id(project) == "_T3"
    assert _run(project, "close", "_T2") == 0
    assert park.next_local_id(project) == "_T3"
    assert _run(project, "close", "_T1") == 0
    assert park.next_local_id(project) == "_T3"


def test_close_moves_the_ergon_to_the_closed_folder_and_releases_its_leases(project, capsys):
    ergon = _plan_ergon(project)
    _write(project, ergon_id=ERGON_ID, name="holders-units")
    _athlos(project, 1, "--step", "first")
    _run(project, "hold", ERGON_ID, *_session("s1"))
    capsys.readouterr()
    assert _run(project, "close", ERGON_ID) == 0
    assert capsys.readouterr().out == f"_aitna/.ergon/.closed/{ERGON_NAME}\n"
    assert not ergon.exists()
    closed = _closed(project, ERGON_NAME)
    assert sorted(path.name for path in closed.iterdir()) == ["1", "PARK.md", "PLAN.md", "RESUME.md"]
    assert list(closed.rglob("HOLDER")) == []
    assert (closed / "1" / "ATHLOS.md").is_file()
    assert _run(project, "unpark", ERGON_ID) == 1
    assert capsys.readouterr().err.startswith(f"error: no ergon with id {ERGON_ID} under _aitna/.ergon; ergons: none")


def test_close_of_an_unknown_ergon_names_the_candidates(project, capsys):
    _write(project)
    assert _run(project, "close", "C999") == 1
    assert capsys.readouterr().err == "error: no ergon with id C999 under _aitna/.ergon; ergons: C183-park-helper\n"
    assert _ergon(project).is_dir()


def test_find_closed_ergon_finds_a_closed_ergon_or_none(project):
    _write(project)
    _run(project, "close", "C183")
    assert park.find_closed_ergon(project, "C183", TEXTS) == _closed(project, "C183-park-helper")
    assert park.find_closed_ergon(project, "C999", TEXTS) is None
    with pytest.raises(park.ParkError, match="no ergon with id C183"):
        park.find_ergon(project, "C183", TEXTS)


# --------------------------------------------------------------------------------------
# the active unit, read from the worktree's folder (ADR 0028 D10)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("folder", "unit"),
    [
        ("C186-holders-units.1", ("C186", 1)),
        ("_T3-scratch.12", ("_T3", 12)),
        ("A59-park-and-resume.5", ("A59", 5)),
        ("C186-holders-units.\u0663", ("C186", 3)),  # a decimal digit of another script still reads
        ("C186-holders-units.\u00b2", None),  # a superscript digit passes isdigit and fails in int()
        ("C186-holders-units", None),
        ("C186-Holders.1", None),
        ("holders-units.1", None),
        ("C186-holders-units.x", None),
        ("C186-holders-units.", None),
        (".1", None),
    ],
)
def test_the_worktree_folder_names_the_ergon_and_the_athlos_number(folder, unit):
    assert park.worktree_unit(Path("/x/.worktrees") / folder) == unit


@pytest.fixture
def worktree_project(tmp_path: Path) -> Path:
    """A project root that sits in ``.worktrees/C186-holders-units.1``, with the ergon and an athlos in it."""
    root = tmp_path / ".worktrees" / f"{ERGON_NAME}.1"
    (root / "_aitna").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (root / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    ergon = _plan_ergon(root)
    park.write_athlos_doc(
        ergon / "1",
        park.AthlosDoc(park.ParkFields(id=ERGON_ID, name="holders-units", next_action="r", athlos="C186.1")),
        TEXTS,
    )
    return root.resolve()


def test_the_active_unit_is_the_athlos_the_worktree_folder_names(worktree_project):
    ergon, ergon_id, number = park.active_unit(worktree_project, TEXTS)
    assert (ergon, ergon_id, number) == (_ergon(worktree_project, ERGON_NAME), ERGON_ID, 1)


def test_a_session_in_the_main_checkout_has_no_active_unit(project, capsys):
    _plan_ergon(project)
    assert park.active_unit(project, TEXTS) is None
    assert _run(project, "active") == 0
    assert capsys.readouterr().out == f"{TEXTS['active']['none']}\n"


def test_a_worktree_of_no_ergon_has_no_active_unit(tmp_path, capsys):
    root = tmp_path / ".worktrees" / "C999-nothing.1"
    (root / "_aitna").mkdir(parents=True)
    (root / "AGENTS.md").write_text("", encoding="utf-8")
    (root / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    assert park.active_unit(root.resolve(), TEXTS) is None
    assert _run(root, "active") == 0
    assert capsys.readouterr().out == f"{TEXTS['active']['none']}\n"


def test_active_prints_the_athlos_with_its_derived_state_and_its_holder(worktree_project, capsys):
    folder = _ergon(worktree_project, ERGON_NAME) / "1"
    path = f"_aitna/.ergon/{ERGON_NAME}/1"
    capsys.readouterr()
    assert _run(worktree_project, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out == f"athlos: C186.1 | 1 | not started | - | {path}\n"
    park.acquire_lease(folder, park.Holder("claude", "s1", LAPTOP, "/w"), TEXTS, _live_context())
    assert _run(worktree_project, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out == f"athlos: C186.1 | 1 | active | claude s1 laptop /w | {path}\n"


def test_active_names_the_ergon_when_the_folders_athlos_has_no_folder_yet(worktree_project, capsys):
    import shutil

    shutil.rmtree(_ergon(worktree_project, ERGON_NAME) / "1")
    capsys.readouterr()
    assert _run(worktree_project, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out == f"ergon: C186 | {ERGON_NAME} | not started | - | _aitna/.ergon/{ERGON_NAME}\n"


# --------------------------------------------------------------------------------------
# ergon_root through the repository's common directory, and a linked worktree
# --------------------------------------------------------------------------------------


def test_the_ergons_of_a_linked_worktree_are_the_main_checkouts(linked):
    main, worktree = linked
    assert project_root.git_common_root(worktree) == main
    assert project_root.git_common_root(main) == main
    assert project_root.ergon_root(worktree) == main / "_aitna" / ".ergon"
    assert project_root.ergon_root(main) == main / "_aitna" / ".ergon"


def test_the_dev_root_of_a_worktree_is_the_main_checkouts_declaration(linked):
    main, worktree = linked
    (main / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    assert project_root.ergon_root(worktree) == main / "tools" / "ai" / ".ergon"
    assert not (worktree / ".aitna-root").exists()


def test_outside_a_repository_the_common_root_is_the_project_root_and_no_root_is_none(project):
    assert project_root.git_common_root(project) == project
    assert project_root.git_common_root(None) is None
    assert project_root.ergon_root(project) == project / "_aitna" / ".ergon"


def test_a_repository_whose_top_is_no_project_keeps_the_project_root(tmp_path):
    top = tmp_path / "wider"
    nested = top / "proj"
    nested.mkdir(parents=True)
    _git(top, "init", "-b", "main")
    (nested / "AGENTS.md").write_text("", encoding="utf-8")
    assert project_root.git_common_root(nested.resolve()) == nested.resolve()


def test_a_project_in_a_repository_subfolder_keeps_its_own_dev_root(tmp_path):
    top = tmp_path / "mono"
    proj = top / "proj"
    proj.mkdir(parents=True)
    (top / "AGENTS.md").write_text("", encoding="utf-8")
    (proj / "AGENTS.md").write_text("", encoding="utf-8")
    (proj / ".aitna-root").write_text("_aitna\n", encoding="utf-8")
    _git(top, "init", "-b", "main")
    assert project_root.git_common_root(proj.resolve()) == proj.resolve()
    assert project_root.ergon_root(proj.resolve()) == proj.resolve() / "_aitna" / ".ergon"
    assert project_root.ergon_root(top.resolve()) == top.resolve() / "_aitna" / ".ergon"


def test_a_linked_worktree_of_a_subfolder_project_uses_the_main_checkouts_subfolder(tmp_path):
    main = tmp_path / "mono"
    proj = main / "proj"
    proj.mkdir(parents=True)
    (proj / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    _git(main, "init", "-b", "main")
    _git(main, "add", "proj/AGENTS.md")
    _git(main, "commit", "-m", "init")
    worktree = tmp_path / "linked"
    _git(main, "worktree", "add", "-b", "athlos-1", str(worktree))
    linked_proj = (worktree / "proj").resolve()
    assert project_root.git_common_root(linked_proj) == proj.resolve()
    assert project_root.ergon_root(linked_proj) == proj.resolve() / "_aitna" / ".ergon"


def test_without_git_the_common_root_is_the_project_root(tmp_path, monkeypatch):
    root = tmp_path / "nogit"
    root.mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))
    assert project_root.git_common_root(root) == root


def test_the_common_root_is_probed_on_every_call_and_remembered_by_nobody(tmp_path, monkeypatch):
    root = tmp_path / "uncached"
    root.mkdir()
    calls = []
    real = project_root._resolve_git_common_root
    monkeypatch.setattr(project_root, "_resolve_git_common_root", lambda path: calls.append(path) or real(path))
    project_root.git_common_root(root)
    project_root.git_common_root(root)
    # no module-level cache: a worktree that appears mid-process must not read the old answer
    assert calls == [root, root]


def test_a_session_in_a_linked_worktree_lists_the_main_checkouts_ergons(linked, capsys):
    main, worktree = linked
    assert _run(main, "write", "C183", "--name", "park-helper", "--goal", "g", "--next", "Twin it") == 0
    capsys.readouterr()
    assert _run(worktree, "list", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out.startswith("C183 | park-helper | parked | - | Twin it | 0 | ")
    assert park._ergon_names(worktree) == ["C183-park-helper"]
    assert not (worktree / "_aitna" / ".ergon").exists()


def test_a_session_in_a_linked_worktree_writes_into_the_main_checkouts_ergons(linked, capsys):
    main, worktree = linked
    assert _run(worktree, "write", "C183", "--name", "park-helper", "--goal", "g", "--next", "Twin it") == 0
    assert (main / "_aitna" / ".ergon" / "C183-park-helper" / "PARK.md").is_file()
    assert not (worktree / "_aitna" / ".ergon").exists()


def test_a_session_in_a_linked_worktree_knows_its_athlos_from_its_folder(linked, capsys):
    main, worktree = linked
    _plan_ergon(main)
    assert _athlos(main, 1, "--step", "first") == 0
    capsys.readouterr()
    assert _run(worktree, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out.startswith("athlos: C186.1 | 1 | active | claude s1 laptop ")


def test_a_path_is_printed_from_the_root_when_inside_it_and_as_it_is_when_outside(tmp_path):
    root = tmp_path / "root"
    assert park._display_path(root / "a" / "b.md", root) == "a/b.md"
    assert park._display_path(root, root) == "."
    outside = tmp_path / "main" / "_aitna" / ".ergon"
    assert park._display_path(outside, root) == str(outside)


def test_every_command_of_a_linked_worktree_prints_the_main_checkouts_ergon_paths_as_they_are(linked, capsys):
    main, worktree = linked
    layer = main / "_aitna" / ".ergon"
    assert _run(worktree, "list") == 0
    assert capsys.readouterr().out == f"no ergons in {layer}\n"
    assert _run(worktree, "unpark", "C9") == 1
    assert capsys.readouterr().err == f"error: no ergon with id C9 under {layer}; ergons: none\n"
    assert _run(worktree, "write", "C183", "--name", "park-helper", "--goal", "g", "--next", "n") == 0
    ergon = layer / "C183-park-helper"
    assert capsys.readouterr().out == f"{ergon}\n"
    assert f"1. Read `{ergon / 'PARK.md'}`." in (ergon / "RESUME.md").read_text(encoding="utf-8")
    assert _run(worktree, "unpark", "C9") == 1
    assert capsys.readouterr().err == f"error: no ergon with id C9 under {layer}; ergons: C183-park-helper\n"
    assert _run(worktree, "digest", "C183", "--cap", "40") == 0
    assert capsys.readouterr().out.endswith(f"… 5 more lines in {ergon / 'PARK.md'}\n")
    assert _run(worktree, "close", "C183") == 0
    assert capsys.readouterr().out == f"{layer / '.closed' / 'C183-park-helper'}\n"


def test_the_athlos_command_of_a_linked_worktree_prints_the_folder_as_it_is(linked, capsys):
    main, worktree = linked
    _plan_ergon(main)
    assert _athlos(worktree, 1, "--step", "first") == 0
    assert capsys.readouterr().out == f"{_ergon(main, ERGON_NAME) / '1'}\n"


# --------------------------------------------------------------------------------------
# project root
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["list"],
        ["write", "C1", "--name", "n", "--goal", "g", "--next", "x"],
        ["unpark", "C1"],
        ["hold", "C1"],
        ["close", "C1"],
        ["active"],
    ],
)
def test_no_project_root_is_refused_and_nothing_is_written(tmp_path, monkeypatch, capsys, argv):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    assert park.main(argv) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: [akmon] no project root at or above ")
    assert err.count("\n") == 1
    assert list(work.iterdir()) == []


def test_an_explicit_root_that_is_not_a_directory_is_refused(tmp_path, capsys):
    missing = tmp_path / "missing"
    assert park.main(["list", "--root", str(missing)]) == 1
    assert capsys.readouterr().err == f"error: --root {missing} is not a directory\n"


def test_the_project_root_is_found_by_walking_up(project, monkeypatch, capsys):
    nested = project / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert park.main(["write", "C1", "--name", "n", "--goal", "g", "--next", "x"]) == 0
    assert capsys.readouterr().out == "_aitna/.ergon/C1-n\n"
    assert (project / "_aitna" / ".ergon" / "C1-n" / "PARK.md").is_file()
    assert not (nested / "_aitna").exists()


def test_project_root_flag_is_an_alias_of_root(project, capsys):
    assert park.main(["list", "--project-root", str(project)]) == 0
    assert capsys.readouterr().out == "no ergons in _aitna/.ergon\n"


# --------------------------------------------------------------------------------------
# worktrees: every worktree git knows and every backup branch, by state (C190, D-C190-WORKTREES)
# --------------------------------------------------------------------------------------

STATES = TEXTS["worktrees"]["states"]
PENDING_SUBJECT = 'pending: add the "pending" file'


def _athlos_branch(number: int) -> str:
    return f"_aitna/{ERGON_NAME}.{number}"


def _athlos_folder(main: Path, number: int) -> Path:
    return main / ".worktrees" / f"{ERGON_NAME}.{number}"


def _commit_files(folder: Path, files: dict[str, str], message: str) -> None:
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
        _git(folder, "add", name)
    _git(folder, "commit", "-m", message)


def _add_athlos_worktree(main: Path, number: int, files: dict[str, str], message: str) -> Path:
    folder = _athlos_folder(main, number)
    _git(main, "worktree", "add", "-b", _athlos_branch(number), str(folder))
    _commit_files(folder, files, message)
    return folder


def _carry_by_squash(main: Path, number: int) -> None:
    """The owner's carry: one squash commit on main; the branch stays unmerged in git's eyes."""
    _git(main, "merge", "--squash", _athlos_branch(number))
    _git(main, "commit", "-m", f"carry {number}")


@pytest.fixture
def world(tmp_path: Path) -> Path:
    """A main checkout with one worktree or branch of every kind a ``worktrees`` row can be.

    1 carried by a squash, 2 ready (four paths, a quote in its subject), 3 dirty, 4 carried but held by a
    live lease, 5 a backup carried by a squash, 6 a backup not carried (its note names the branch), 7 carried
    by a merge commit, and a harness worktree.
    """
    main = tmp_path / "world"
    main.mkdir()
    (main / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (main / "_aitna").mkdir()
    (main / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    (main / ".gitignore").write_text(".worktrees/\n_aitna/\n.claude/\n", encoding="utf-8")
    _git(main, "init", "-b", "main")
    _git(main, "add", "AGENTS.md", ".gitignore")
    _git(main, "commit", "-m", "base")
    _add_athlos_worktree(main, 1, {"squashed.txt": "one"}, "one")
    _add_athlos_worktree(
        main,
        2,
        {"pending.txt": "two", "p1.txt": "1", "p2.txt": "2", "p3.txt": "3"},
        PENDING_SUBJECT,
    )
    dirty = _add_athlos_worktree(main, 3, {"dirty.txt": "three"}, "three")
    (dirty / "scratch.txt").write_text("untracked", encoding="utf-8")
    held = _add_athlos_worktree(main, 4, {"held.txt": "four"}, "four")
    gone = _add_athlos_worktree(main, 5, {"gone.txt": "five"}, "five")
    _git(main, "worktree", "remove", str(gone))
    behind = _add_athlos_worktree(main, 6, {"behind.txt": "six"}, "six")
    _git(main, "worktree", "remove", str(behind))
    _add_athlos_worktree(main, 7, {"merged.txt": "seven"}, "seven")
    harness = main / ".claude" / "worktrees" / "agent-x"
    _git(main, "worktree", "add", "-b", "worktree-agent-x", str(harness))
    _commit_files(harness, {"harness.txt": "h"}, "harness work")
    for number in (1, 4, 5):
        _carry_by_squash(main, number)
    _git(main, "merge", "--no-ff", "-m", "merge seven", _athlos_branch(7))
    ergon = _ergon(main, ERGON_NAME)
    ergon.mkdir(parents=True)
    folder = _make_athlos(ergon, 4, "held")
    park.acquire_lease(folder, park.Holder("claude", "s1", LAPTOP, str(held)), TEXTS, _live_context())
    park.write_athlos_doc(
        _make_athlos(ergon, 6, "behind"),
        park.AthlosDoc(
            park.ParkFields(
                id=ERGON_ID, name="holders-units", next_action="x", athlos=f"{ERGON_ID}.6", branch=_athlos_branch(6)
            ),
            (),
            done=False,
        ),
        TEXTS,
    )
    return main


def _world_rows(main: Path) -> dict[str, park.WorktreeRow]:
    return {row.branch: row for row in park.list_worktrees(main, TEXTS, _live_context())}


def _worktrees_out(main: Path, capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    capsys.readouterr()
    code = _run(main, "worktrees", *argv, "--machine", LAPTOP)
    return code, capsys.readouterr().out


def test_the_owners_checkout_comes_first_and_backup_branches_last(world):
    rows = park.list_worktrees(world, TEXTS, _live_context())
    assert rows[0].kind == "main"
    assert rows[0].path == str(world.resolve())
    assert rows[0].state == STATES["main"]
    assert [row.branch for row in rows[-2:]] == [_athlos_branch(5), _athlos_branch(6)]
    assert [row.kind for row in rows[-2:]] == ["branch-only", "branch-only"]


def test_a_branch_carried_by_a_squash_is_carried_though_git_calls_it_unmerged(world):
    row = _world_rows(world)[_athlos_branch(1)]
    assert _git(world, "branch", "--merged", "main", "--list", _athlos_branch(1)) == ""
    assert (row.kind, row.state, row.carried, row.removable) == ("athlos", STATES["carried"], True, True)
    assert (row.clean, row.ahead, row.differing) == (True, 1, ())
    assert row.shown == f"{ERGON_NAME}.1"


def test_a_branch_merged_by_a_merge_commit_is_carried_with_nothing_ahead(world):
    row = _world_rows(world)[_athlos_branch(7)]
    assert (row.state, row.carried, row.ahead, row.removable) == (STATES["carried"], True, 0, True)


def test_a_clean_branch_beyond_the_owners_and_not_carried_is_ready_with_its_subject(world):
    row = _world_rows(world)[_athlos_branch(2)]
    assert (row.state, row.carried, row.ahead, row.removable) == (STATES["ready"], False, 1, False)
    assert row.differing == ("p1.txt", "p2.txt", "p3.txt", "pending.txt")
    assert row.subject == PENDING_SUBJECT


def test_a_dirty_worktree_is_working_and_untracked_files_count(world):
    row = _world_rows(world)[_athlos_branch(3)]
    assert (row.state, row.clean, row.carried, row.removable) == (STATES["working"], False, False, False)
    assert row.subject == ""


def test_a_live_lease_on_the_worktree_holds_it_whatever_its_content(world):
    row = _world_rows(world)[_athlos_branch(4)]
    assert row.carried
    assert (row.state, row.ergon, row.athlos, row.removable) == (STATES["working"], ERGON_ID, f"{ERGON_ID}.4", False)


def test_a_stale_lease_holds_nothing(world):
    folder = _ergon(world, ERGON_NAME) / "4"
    (folder / "HOLDER").write_text(
        f"---\nharness: claude\nsession: s1\nmachine: {LAPTOP}\nworktree: {_athlos_folder(world, 4)}\n"
        "written: 2000-01-01T00:00:00Z\n---\n",
        encoding="utf-8",
    )
    row = _world_rows(world)[_athlos_branch(4)]
    assert (row.state, row.removable) == (STATES["carried"], True)


def test_a_harness_worktree_is_never_removable(world):
    row = _world_rows(world)["worktree-agent-x"]
    assert (row.kind, row.state, row.removable) == ("harness", STATES["harness"], False)
    assert row.shown == str(world.resolve() / ".claude" / "worktrees" / "agent-x")


def test_a_branch_with_no_worktree_is_a_backup_and_its_note_names_its_athlos(world):
    rows = _world_rows(world)
    carried, behind = rows[_athlos_branch(5)], rows[_athlos_branch(6)]
    assert (carried.kind, carried.path, carried.clean, carried.state) == ("branch-only", "", None, STATES["backup"])
    assert carried.removable
    assert (behind.state, behind.removable, behind.carried) == (STATES["not_carried_backup"], False, False)
    assert (behind.ergon, behind.athlos) == (ERGON_ID, f"{ERGON_ID}.6")


def test_a_backup_held_by_a_live_lease_is_working(world):
    folder = _ergon(world, ERGON_NAME) / "6"
    park.acquire_lease(folder, park.Holder("claude", "s9", LAPTOP, "/elsewhere"), TEXTS, _live_context())
    assert _world_rows(world)[_athlos_branch(6)].state == STATES["working"]


def test_the_table_and_the_commands_for_the_ready_and_the_removable(world, capsys):
    code, out = _worktrees_out(world, capsys)
    assert code == 0
    table, carry, removal = out.rstrip("\n").split("\n\n")
    lines = table.split("\n")
    assert [cell.strip() for cell in lines[0].split(" | ")] == TEXTS["worktrees"]["columns"]
    assert len(lines) == 1 + 9
    assert len({line.index(" | ") for line in lines}) == 1  # the columns are aligned
    assert carry.split("\n") == [
        f"cd {world.resolve()}",
        f"git merge --squash {_athlos_branch(2)}",
        'git commit -m "pending: add the \\"pending\\" file"',
    ]
    assert removal.split("\n") == [
        f"git worktree remove {_athlos_folder(world.resolve(), 1)}",
        f"git worktree remove {_athlos_folder(world.resolve(), 7)}",
        f"git branch -D {_athlos_branch(5)}",
    ]


def test_worktrees_reads_and_changes_nothing(world, capsys):
    before = (_git(world, "for-each-ref"), _git(world, "worktree", "list"), _git(world, "status", "--porcelain"))
    _worktrees_out(world, capsys)
    _worktrees_out(world, capsys, _athlos_branch(2))
    after = (_git(world, "for-each-ref"), _git(world, "worktree", "list"), _git(world, "status", "--porcelain"))
    assert after == before


def test_a_branch_target_prints_its_row_and_a_carried_verdict_with_exit_zero(world, capsys):
    for target in (_athlos_branch(1), f"{ERGON_NAME}.1"):
        code, out = _worktrees_out(world, capsys, target)
        lines = out.rstrip("\n").split("\n")
        assert code == 0
        assert len(lines) == 3  # the header, the row and the verdict
        assert lines[1].startswith(f"{ERGON_NAME}.1 ")
        assert lines[2] == f"{_athlos_branch(1)}: carried"


def test_an_athlos_key_names_the_row_of_its_unit(world, capsys):
    code, out = _worktrees_out(world, capsys, f"{ERGON_ID}.4")
    assert code == 0
    assert out.rstrip("\n").split("\n")[-1] == f"{_athlos_branch(4)}: carried"


def test_a_branch_not_carried_names_the_first_three_paths_that_differ_and_exits_one(world, capsys):
    code, out = _worktrees_out(world, capsys, _athlos_branch(2))
    assert code == 1
    assert out.rstrip("\n").split("\n")[-1] == f"{_athlos_branch(2)}: not carried — p1.txt, p2.txt, p3.txt, …"
    code, out = _worktrees_out(world, capsys, _athlos_branch(3))
    assert code == 1
    assert out.rstrip("\n").split("\n")[-1] == f"{_athlos_branch(3)}: not carried — dirty.txt"


def test_a_missing_branch_is_said_and_exits_one(world, capsys):
    code, out = _worktrees_out(world, capsys, "nope")
    assert (code, out) == (1, "nope: no such branch\n")


def test_the_verdict_follows_the_content_after_the_owner_changes_a_carried_path_again(world, capsys):
    (world / "squashed.txt").write_text("changed again", encoding="utf-8")
    _git(world, "commit", "-am", "owner edits it")
    code, out = _worktrees_out(world, capsys, _athlos_branch(1))
    assert code == 1
    assert out.rstrip("\n").endswith(f"{_athlos_branch(1)}: not carried — squashed.txt")


def test_worktrees_outside_a_repository_is_refused_in_one_line(project, capsys):
    assert _run(project, "worktrees") == 1
    assert (
        capsys.readouterr().err == f"error: {project} is not in a git repository, so there are no worktrees to list\n"
    )


def test_a_main_checkout_alone_lists_one_row_and_no_commands(project, capsys):
    _git(project, "init", "-b", "main")
    _git(project, "add", "AGENTS.md")
    _git(project, "commit", "-m", "base")
    capsys.readouterr()
    assert _run(project, "worktrees", "--machine", LAPTOP) == 0
    lines = capsys.readouterr().out.rstrip("\n").split("\n")
    assert len(lines) == 2
    assert lines[1].split(" | ")[0].strip() == str(project.resolve())
    assert lines[1].endswith(f" | {STATES['main']}")


def test_the_porcelain_listing_is_parsed_in_git_order_and_a_bare_entry_is_marked():
    text = (
        "worktree /srv/main\nHEAD aaa\nbranch refs/heads/main\n\n"
        "worktree /srv/main/.worktrees/x.1\nHEAD bbb\nbranch refs/heads/_aitna/C1-x.1\nlocked\n\n"
        "worktree /srv/detached\nHEAD ccc\ndetached\n\n"
        "worktree /srv/bare.git\nbare\n"
    )
    assert park.parse_worktree_list(text) == [
        park.GitWorktree("/srv/main", "aaa", "main", bare=False),
        park.GitWorktree("/srv/main/.worktrees/x.1", "bbb", "_aitna/C1-x.1", bare=False),
        park.GitWorktree("/srv/detached", "ccc", "", bare=False),
        park.GitWorktree("/srv/bare.git", "", "", bare=True),
    ]


@pytest.mark.parametrize(
    ("branch", "unit"),
    [
        ("_aitna/C186-holders-units.1", ("C186", 1)),
        ("_aitna/_T3-local-thing.12", ("_T3", 12)),
        ("_aitna/C186-holders-units", None),
        ("_aitna/C186-holders-units.x", None),
        ("feature/C186-holders-units.1", None),
        ("main", None),
    ],
)
def test_an_athlos_branch_is_in_the_namespace_and_names_its_ergon_and_number(branch, unit):
    assert park.branch_unit(branch) == unit


def _row(**changes: object) -> park.WorktreeRow:
    base = park.WorktreeRow(
        path="/srv/a b",
        shown="a b",
        branch="_aitna/C1-x.1",
        kind="athlos",
        ergon="",
        athlos="",
        clean=True,
        ahead=2,
        age_seconds=0,
        carried=True,
        differing=(),
        state=STATES["carried"],
        removable=True,
        subject="",
    )
    return dataclasses.replace(base, **changes)


def test_the_table_shows_short_relative_ages_and_the_empty_cell_for_what_is_unknown():
    rows = [
        _row(age_seconds=59 * 60 + 59),
        _row(age_seconds=60 * 60),
        _row(age_seconds=24 * 3600 - 1),
        _row(age_seconds=24 * 3600),
        _row(age_seconds=None, ahead=None, clean=None, shown="", path="", kind="branch-only"),
    ]
    lines = park.format_worktrees(rows, TEXTS)
    assert [line.split(" | ")[7].strip() for line in lines[1:]] == ["59m", "1h", "23h", "1d", "-"]
    last = [cell.strip() for cell in lines[-1].split(" | ")]
    assert (last[0], last[5], last[6]) == ("-", "-", "-")


def test_the_commands_are_quoted_for_the_shell_and_the_message_for_double_quotes():
    ready = _row(state=STATES["ready"], removable=False, carried=False, subject='fix `a` and "b" $HOME \\ done')
    [block] = park.carry_commands([ready], "/srv/the main", TEXTS)
    assert block == [
        "cd '/srv/the main'",
        "git merge --squash _aitna/C1-x.1",
        'git commit -m "fix \\`a\\` and \\"b\\" \\$HOME \\\\ done"',
    ]
    assert park.removal_commands([_row(), _row(path="", branch="_aitna/it's")], TEXTS) == [
        "git worktree remove '/srv/a b'",
        "git branch -D '_aitna/it'\"'\"'s'",
    ]


# ---------------------------------------------------------------------------------------------
# the block commit: the controlling style prints it in the main checkout, never runs it (ADR 0031 D04, D05)
# ---------------------------------------------------------------------------------------------

BLOCK = TEXTS["block_commit"]
ERGON_PATH = "_aitna/.ergon/C183-park-helper"


def _commit_all(folder: Path) -> None:
    _git(folder, "add", "-A")
    _git(folder, "commit", "-m", "base")


def _set_style(checkout: Path, style: str) -> None:
    local = checkout / "_aitna" / ".local"
    local.mkdir(parents=True, exist_ok=True)
    (local / "work.json").write_text(f'{{"style": "{style}"}}\n', encoding="utf-8")


def _styled_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, style: str) -> Path:
    """A main checkout with one commit, one edited file and a developer work style; it is the cwd."""
    main = tmp_path / "styled"
    (main / "_aitna").mkdir(parents=True)
    (main / "src").mkdir()
    (main / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (main / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    (main / "src" / "code.py").write_text("one\n", encoding="utf-8")
    _set_style(main, style)
    _git(main, "init", "-b", "main")
    _commit_all(main)
    (main / "src" / "code.py").write_text("two\n", encoding="utf-8")
    monkeypatch.chdir(main)
    return main.resolve()


def _resume_reminder() -> str:
    return jsondata.fill(BLOCK["reminder"], {"resume": f"{ERGON_PATH}/RESUME.md"})


def test_controlling_in_the_main_checkout_prints_the_block_commit_of_the_owned_paths(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    owned = ["--owned-path", "src/code.py", "--owned-path", "docs/a file.md", "--owned-path", "src/code.py"]
    assert _write(main, *owned, "--commit-message", 'Fix "the" $thing') == 0
    assert capsys.readouterr().out == (
        f"{ERGON_PATH}\n\n"
        f"{BLOCK['heading']}\n"
        f"cd {shlex.quote(str(main))}\n"
        "git add -- src/code.py 'docs/a file.md'\n"
        'git commit -m "Fix \\"the\\" \\$thing"\n\n'
        f"{_resume_reminder()}\n"
    )


def test_controlling_without_owned_paths_stages_the_changed_paths_once_each(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    assert _write(main) == 0
    assert capsys.readouterr().out == (
        f"{ERGON_PATH}\n\n"
        f"{BLOCK['heading']}\n"
        f"cd {shlex.quote(str(main))}\n"
        f"git add -- src/code.py {ERGON_PATH}/PARK.md {ERGON_PATH}/RESUME.md\n"
        f'git commit -m "{BLOCK["placeholder"]}"\n\n'
        f"{BLOCK['propose']}\n{_resume_reminder()}\n"
    )


def test_the_block_commit_enters_the_repository_root_from_a_subdirectory(tmp_path, monkeypatch, capsys):
    # git status reports paths relative to the repository root, so the block works from any directory
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    monkeypatch.chdir(main / "src")
    assert _write(main, "--owned-path", "src/code.py", "--commit-message", "Park it") == 0
    lines = capsys.readouterr().out.splitlines()
    heading = lines.index(BLOCK["heading"])
    assert lines[heading + 1] == f"cd {shlex.quote(str(main))}"
    assert lines[heading + 2] == "git add -- src/code.py"


def test_the_changed_paths_block_enters_the_root_from_a_subdirectory(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    monkeypatch.chdir(main / "src")
    assert _write(main) == 0
    lines = capsys.readouterr().out.splitlines()
    heading = lines.index(BLOCK["heading"])
    assert lines[heading + 1] == f"cd {shlex.quote(str(main))}"
    assert lines[heading + 2].startswith("git add -- src/code.py ")


def test_controlling_with_no_owned_and_no_changed_path_prints_no_block(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    (main / "src" / "code.py").write_text("one\n", encoding="utf-8")
    (main / ".git" / "info" / "exclude").write_text("_aitna/.ergon/\n", encoding="utf-8")
    assert _write(main) == 0
    assert capsys.readouterr().out == f"{ERGON_PATH}\n"


def test_the_changed_paths_name_the_new_side_of_a_rename_only(tmp_path, monkeypatch, capsys):
    # the origin of a staged rename is gone from the tree: `git add -- <origin>` would fail
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    _git(main, "mv", "src/code.py", "src/moved.py")
    assert park._status_paths(main) == ("src/moved.py",)
    assert _write(main) == 0
    add = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("git add -- "))
    assert add.startswith("git add -- src/moved.py ")
    assert "src/code.py" not in add


def test_a_staged_copy_is_listed_by_its_new_path_only(tmp_path, monkeypatch):
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    (main / "src" / "code.py").write_text("a\nb\nc\nd\ne\nf\n", encoding="utf-8")
    _commit_all(main)
    (main / "src" / "code.py").write_text("a\nb\nc\nd\ne\nf\ng\n", encoding="utf-8")
    (main / "src" / "copy.py").write_text("a\nb\nc\nd\ne\nf\ng\n", encoding="utf-8")
    _git(main, "add", "src")
    _git(main, "config", "status.renames", "copies")
    assert "C  src/code.py -> src/copy.py" in _git(main, "status", "--porcelain")
    assert park._status_paths(main)[:2] == ("src/code.py", "src/copy.py")
    assert park._status_paths(main).count("src/code.py") == 1


def test_owned_paths_are_rebased_onto_the_repository_root_when_the_project_is_a_subdirectory(
    tmp_path, monkeypatch, capsys
):
    repo = tmp_path / "repo"
    proj = repo / "proj"
    (proj / "_aitna").mkdir(parents=True)
    (proj / "src").mkdir()
    (proj / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (proj / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    (proj / "src" / "code.py").write_text("one\n", encoding="utf-8")
    _set_style(proj, "controlling")
    _git(repo, "init", "-b", "main")
    _commit_all(repo)
    monkeypatch.chdir(proj)
    owned = ["--owned-path", "src/code.py", "--owned-path", "../top level.md", "--owned-path", "/abs/x.md"]
    assert _write(proj, *owned, "--commit-message", "Park it") == 0
    lines = capsys.readouterr().out.splitlines()
    heading = lines.index(BLOCK["heading"])
    assert lines[heading + 1] == f"cd {shlex.quote(str(repo.resolve()))}"
    assert lines[heading + 2] == "git add -- proj/src/code.py 'top level.md' /abs/x.md"


def test_the_changed_paths_stay_relative_to_the_repository_root_when_the_project_is_a_subdirectory(
    tmp_path, monkeypatch, capsys
):
    repo = tmp_path / "repo2"
    proj = repo / "proj"
    (proj / "_aitna").mkdir(parents=True)
    (proj / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (proj / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    (proj / "code.py").write_text("one\n", encoding="utf-8")
    _set_style(proj, "controlling")
    _git(repo, "init", "-b", "main")
    _commit_all(repo)
    (proj / "code.py").write_text("two\n", encoding="utf-8")
    monkeypatch.chdir(proj)
    assert _write(proj) == 0
    out = capsys.readouterr().out
    assert "git add -- proj/code.py " in out


def test_the_delegating_style_prints_the_path_only(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "delegating")
    assert _write(main, "--owned-path", "src/code.py", "--commit-message", "m") == 0
    assert capsys.readouterr().out == f"{ERGON_PATH}\n"


def test_no_recorded_style_is_the_default_delegating_one(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "delegating")
    (main / "_aitna" / ".local" / "work.json").unlink()
    assert _write(main, "--owned-path", "src/code.py") == 0
    assert capsys.readouterr().out == f"{ERGON_PATH}\n"


def test_the_session_style_decides_over_the_developer_one(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "delegating")
    sessions = main / "_aitna" / ".local" / "work-sessions.json"
    sessions.write_text('{"sessions": {"s-9": "controlling"}}\n', encoding="utf-8")
    assert _write(main, "--owned-path", "src/code.py", "--session-id", "s-9", "--harness", "claude") == 0
    assert capsys.readouterr().out.startswith(f"{ERGON_PATH}\n\n{BLOCK['heading']}\n")


def test_controlling_inside_a_linked_worktree_prints_the_path_only(tmp_path, monkeypatch, capsys):
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    worktree = main / ".worktrees" / "C183-park-helper.1"
    _git(main, "worktree", "add", "-b", "athlos-1", str(worktree))
    _set_style(worktree, "controlling")
    monkeypatch.chdir(worktree)
    assert _write(worktree, "--owned-path", "src/code.py") == 0
    assert capsys.readouterr().out == f"{main / ERGON_PATH}\n"


def test_controlling_outside_git_prints_the_path_only(project, capsys):
    _set_style(project, "controlling")
    assert _write(project, "--owned-path", "src/code.py") == 0
    assert capsys.readouterr().out == f"{ERGON_PATH}\n"


def test_the_block_commit_is_in_no_record_and_the_tool_runs_no_git_add(tmp_path, monkeypatch):
    main = _styled_main(tmp_path, monkeypatch, "controlling")
    assert _write(main, "--owned-path", "src/code.py", "--commit-message", "Park it") == 0
    for name in ("PARK.md", "RESUME.md"):
        text = (main / ERGON_PATH / name).read_text(encoding="utf-8")
        assert BLOCK["heading"] not in text and "git commit" not in text and "Park it" not in text
    assert _git(main, "diff", "--cached", "--name-only") == ""
    assert _git(main, "rev-list", "--count", "HEAD") == "1"
