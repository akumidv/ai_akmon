"""Tests for the park helper (tools/park/park.py): the note, the lease, the jobs, the kits, the commands.

The local index is retired (ADR 0028 D12): nothing here expects a row, and a test pins that none is written.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import re
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
KIT_ID = "C186"
KIT_NAME = "C186-holders-jobs"
HOURS = 3600


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
    """A main checkout and a linked worktree ``.worktrees/C186-holders-jobs.1`` of it."""
    main = tmp_path / "main"
    main.mkdir()
    (main / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (main / "_aitna").mkdir()
    (main / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    _git(main, "init", "-b", "main")
    _git(main, "add", "AGENTS.md")
    _git(main, "commit", "-m", "init")
    worktree = main / ".worktrees" / f"{KIT_NAME}.1"
    _git(main, "worktree", "add", "-b", "job-1", str(worktree))
    return main.resolve(), worktree.resolve()


def _kit(project: Path, name: str = "C183-park-helper") -> Path:
    return project / "_aitna" / ".ergon" / name


def _closed(project: Path, name: str) -> Path:
    return project / "_aitna" / ".ergon" / ".closed" / name


def _write(project: Path, *extra: str, kit_id: str = "C183", name: str = "park-helper") -> int:
    argv = ["write", kit_id, "--name", name, "--goal", "Build the helper", "--next", "Twin it"]
    return park.main([*argv, *extra, "--root", str(project)])


def _run(project: Path, *argv: str) -> int:
    return park.main([*argv, "--root", str(project)])


def _session(session: str = "s1", machine: str = LAPTOP) -> list[str]:
    """The flags that name the holder of a lease."""
    return ["--harness", "claude", "--session-id", session, "--machine", machine]


def _holder(session: str = "s1", machine: str = LAPTOP) -> park.Holder:
    return park.Holder("claude", session, machine, "/work/tree")


def _context(now: float = 1_000_000.0, stale_hours: int = 24, machine: str = LAPTOP) -> park.LeaseContext:
    return park.LeaseContext(now=now, stale_hours=stale_hours, machine=machine)


def _live_context() -> park.LeaseContext:
    return _context(now=time.time())


PLAN = """---
id: C186
name: holders-jobs
title: Holders and jobs
tasks: C186, C187
---

# Holders and jobs

The target in prose. A line that starts with a dash outside the jobs is not a job:

- C186.9 · not read · result: it sits outside the Jobs section

## Jobs

- C186.1 · Lease module · tasks C186 · paths tools/park, meta/tests · harness claude · result: a held job is refused
- C186.2 · Job file · tasks C186 · after C186.1 · paths tools/park/park.py · result: the job file is written
- C186.3 · Docs · tasks C187 · paths docs · result: the docs say so
- a line that is not a job line
- C186.4

## Notes

- C186.8 · not read · result: it sits after the Jobs section
"""


def _plan_kit(project: Path, plan_text: str = PLAN, name: str = KIT_NAME) -> Path:
    kit = _kit(project, name)
    kit.mkdir(parents=True)
    (kit / "PLAN.md").write_text(plan_text, encoding="utf-8")
    return kit


def _job(project: Path, number: int, *extra: str, session: str = "s1") -> int:
    return _run(project, "job", KIT_ID, "--number", str(number), *extra, *_session(session))


def _make_job(kit: Path, number: int, label: str, *, done: bool = False, steps: tuple[str, ...] = ()) -> Path:
    """A job folder written straight from the types, with no lease."""
    header = park.ParkFields(
        id=KIT_ID, name="holders-jobs", next_action="the result", plan=KIT_ID, job=f"{KIT_ID}.{number}", tasks=(KIT_ID,)
    )
    folder = kit / "jobs" / f"{number}-{park.job_slug(label)}"
    park.write_job_doc(folder, park.JobDoc(header, tuple((step, False) for step in steps), done), TEXTS)
    return folder


def _listed(project: Path, capsys: pytest.CaptureFixture[str], *flags: str) -> list[str]:
    """The lines of ``park list`` with the flags, run as the laptop."""
    capsys.readouterr()
    _run(project, "list", *flags, "--machine", LAPTOP)
    return capsys.readouterr().out.splitlines()


def _kit_ids(lines: list[str]) -> list[str]:
    """The kit lines of a listing (the job lines are indented), by id."""
    return [line.split(" | ")[0] for line in lines if not line.startswith(" ")]


FULL_FIELDS = park.ParkFields(
    id="C183",
    name="park-helper",
    next_action="Twin it: JS | Python",
    plan="A59",
    job="C183.1",
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
        "job",
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
    assert {"job", "tasks", "written"} <= names


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
        ({"job": "C183"}, "job C183 is not a job id"),
        ({"job": "C183.x"}, "job C183.x is not a job id"),
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
# write: the kit, the note header read from git, the resume prompt
# --------------------------------------------------------------------------------------


def test_write_creates_the_kit_with_both_files_and_no_lease(project, capsys):
    assert _write(project, "--plan", "A59", "--decision", "D-X") == 0
    assert capsys.readouterr().out == "_aitna/.ergon/C183-park-helper\n"
    kit = _kit(project)
    fields, body = park.parse_note((kit / "PARK.md").read_text(encoding="utf-8"), "PARK.md", TEXTS)
    assert (fields.id, fields.name, fields.plan) == ("C183", "park-helper", "A59")
    assert body.goal == "Build the helper"
    assert body.decisions == ("D-X",)
    assert (kit / "RESUME.md").is_file()
    assert sorted(path.name for path in kit.iterdir()) == ["PARK.md", "RESUME.md"]


def test_the_written_note_has_no_state_and_no_peers_key(project):
    _write(project)
    lines = (_kit(project) / "PARK.md").read_text(encoding="utf-8").split("\n")
    header = lines[1 : lines.index("---", 1)]
    keys = [line.split(":")[0] for line in header if not line.startswith("  - ")]
    assert "state" not in keys and "peers" not in keys
    assert keys[:2] == ["id", "name"] and keys[-1] == "written"


def test_the_note_records_when_it_was_written(project, monkeypatch):
    monkeypatch.setattr(park, "now_stamp", lambda: "stamp-one")
    _write(project)
    assert park.read_note(_kit(project), TEXTS)[0].written == "stamp-one"
    monkeypatch.setattr(park, "now_stamp", lambda: "stamp-two")
    assert _write(project) == 0
    assert park.read_note(_kit(project), TEXTS)[0].written == "stamp-two"


def test_the_written_stamp_is_utc_to_the_second():
    assert STAMP_RE.match(park.now_stamp())
    _write_now = time.time()
    parsed = park._parse_stamp(park.now_stamp())
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
    fields, body = park.read_note(_kit(project), TEXTS)
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
    fields, _body = park.read_note(_kit(project), TEXTS)
    assert fields.branch == "main"
    assert fields.revisions == tuple(_git(repo, "log", "-5", "--format=%h").split("\n"))
    assert len(fields.revisions) == 2


def test_outside_a_repository_the_note_has_no_branch_and_no_revisions(project):
    assert _write(project) == 0
    fields, _body = park.read_note(_kit(project), TEXTS)
    assert (fields.branch, fields.revisions) == ("", ())


def test_a_branch_or_revisions_the_caller_supplies_never_reach_the_note(project, repo):
    fields = park.ParkFields(id="C9", name="long", next_action="Next", branch="stale", revisions=("zzz",))
    kit = park.write_kit(fields, park.ParkBody(goal="g"), project, TEXTS, repo)
    written, _body = park.read_note(kit, TEXTS)
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
    assert not _kit(project).exists()


def test_a_second_write_rewrites_the_note(project):
    _write(project)
    assert _write(project, "--decision", "D-NEW") == 0
    assert park.read_note(_kit(project), TEXTS)[1].decisions == ("D-NEW",)


def test_session_flags_without_a_harness_are_refused(project, capsys):
    assert _write(project, "--session-id", "s1") == 1
    assert capsys.readouterr().err == "error: --session-id and --machine need --harness\n"
    assert not _kit(project).exists()


def test_resume_prompt_is_harness_neutral_and_dateless(project):
    _write(project, "--decision", "D-X", "--plan", "A59")
    kit = _kit(project)
    resume = (kit / "RESUME.md").read_text(encoding="utf-8")
    assert "`_aitna/.ergon/C183-park-helper/PARK.md`" in resume
    assert "`akmon tool park/park unpark C183`" in resume
    assert "Twin it" in resume and "- D-X" in resume
    assert "stop is observed" in resume and "otherwise report a blocker" in resume
    assert "(N15)" in resume
    assert str(project) not in resume
    assert not any(line.startswith("/") for line in resume.splitlines())
    assert not DATE_RE.search(resume)
    note_lines = (kit / "PARK.md").read_text(encoding="utf-8").splitlines()
    assert not any(DATE_RE.search(line) for line in note_lines if not line.startswith("written:"))


def test_a_dev_root_pointer_moves_the_kit(tmp_path, monkeypatch):
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
    assert not _kit(project).exists()
    assert [path for path in project.rglob("*") if path.name.endswith(".tmp")] == []


def test_a_failure_keeps_an_existing_kit_and_removes_only_the_temp_files(project, monkeypatch):
    _write(project)
    kit = _kit(project)
    before = {path.name: path.read_bytes() for path in kit.iterdir()}

    def refuse(self, target):
        raise OSError("disk says no")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk says no"):
        _write(project, "--decision", "D-NEW")
    assert {path.name: path.read_bytes() for path in kit.iterdir()} == before


def test_a_kit_with_the_id_and_another_name_is_refused(project, capsys):
    _write(project)
    assert _write(project, name="renamed") == 1
    assert capsys.readouterr().err == (
        "error: kit C183-park-helper already carries id C183; keep its name or retire it before writing renamed\n"
    )
    assert not _kit(project, "C183-renamed").exists()


def test_a_closed_kit_with_the_id_and_another_name_is_refused_too(project, capsys):
    _closed(project, "C183-old").mkdir(parents=True)
    assert _write(project) == 1
    assert capsys.readouterr().err == (
        "error: kit C183-old already carries id C183; keep its name or retire it before writing park-helper\n"
    )
    assert not _kit(project).exists()


def test_write_refuses_a_bad_id_and_a_bad_name_before_any_file(project, capsys):
    assert _write(project, kit_id="c183") == 1
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
    assert _write(project, kit_id="_T7", name="scratch") == 0
    assert _kit(project, "_T7-scratch").is_dir()


# --------------------------------------------------------------------------------------
# the retired local index (ADR 0028 D12)
# --------------------------------------------------------------------------------------


def _no_index_anywhere(project: Path) -> None:
    assert not (project / "_aitna" / ".local").exists()
    assert list(project.rglob("TASKS.md")) == []


def test_no_command_writes_a_local_index(project, tmp_path):
    _plan_kit(project)
    bundle = tmp_path / "bundle.md"
    commands = [
        ["write", "C183", "--name", "park-helper", "--goal", "g", "--next", "n"],
        ["unpark", "C183", *_session()],
        ["hold", KIT_ID, *_session()],
        ["job", KIT_ID, "--number", "1", "--step", "first", *_session()],
        ["release", KIT_ID, "--number", "1"],
        ["release", KIT_ID],
        ["list"],
        ["list", "--closed"],
        ["digest", "C183"],
        ["active"],
        ["export", "C183", "--out", str(bundle)],
        ["close", "C183"],
        ["close", KIT_ID],
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


def test_a_lease_round_trips_and_an_unreadable_time_reads_as_the_epoch():
    lease = park.Lease(_holder(), 1_000_000.0)
    assert park.parse_lease(park.render_lease(lease), "HOLDER", TEXTS) == lease
    odd = "---\nharness: claude\nsession: s1\nmachine: laptop\nworktree:\nwritten: yesterday\n---\n"
    assert park.parse_lease(odd, "HOLDER", TEXTS).written == 0.0
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
    assert not park.lease_is_stale(lease, _context(now=1_000_000.0 + 23 * HOURS))
    assert not park.lease_is_stale(lease, _context(now=1_000_000.0 + 24 * HOURS))
    assert park.lease_is_stale(lease, _context(now=1_000_000.0 + 24 * HOURS + 1))
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


def test_a_takeover_of_a_job_keeps_the_replaced_holder_in_the_job_file(tmp_path):
    header = park.ParkFields(id="C9", name="long", next_action="Next", job="C9.1")
    doc = park.JobDoc(header, (("first", False),))
    (tmp_path / "JOB.md").write_text(park.render_job_doc(doc, TEXTS), encoding="utf-8")
    park.acquire_lease(tmp_path, _holder("s1"), TEXTS, _context())
    park.acquire_lease(tmp_path, _holder("s2"), TEXTS, _context(), takeover=True)
    kept = park.read_job_doc(tmp_path / "JOB.md", TEXTS)
    assert kept.header.sessions == (park.SessionRef("claude", "s1", LAPTOP),)
    assert kept.steps == (("first", False),)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["HOLDER", "JOB.md"]


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
    _stale_lease_of(_kit(project), worktree=str(repo))
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"claude s1 laptop {repo} left uncommitted paths: one.txt, scratch.txt"
    assert lines[1].startswith("C183-park-helper: claude s2 laptop ")
    assert len(lines) == 2


def test_a_takeover_of_a_clean_worktree_names_no_path(project, repo, capsys):
    _write(project)
    _stale_lease_of(_kit(project), worktree=str(repo))
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_a_takeover_says_when_the_replaced_worktree_cannot_be_read(project, tmp_path, capsys):
    _write(project)
    _stale_lease_of(_kit(project), worktree=str(tmp_path / "gone"))
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


def test_release_leases_frees_the_plan_and_every_job_of_a_kit(project):
    kit = _plan_kit(project)
    jobs = [_make_job(kit, 1, "Lease module"), _make_job(kit, 2, "Job file")]
    for unit in (kit, *jobs):
        park.acquire_lease(unit, _holder(), TEXTS, _context())
    park.release_leases(kit)
    assert [unit for unit in (kit, *jobs) if (unit / "HOLDER").exists()] == []


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
    assert park.unit_state(tmp_path, TEXTS, context, job_done=True) == states["done"] == "done"


def test_the_lease_of_a_note_less_unit_makes_it_active_and_a_stale_one_not_started(tmp_path):
    context = _live_context()
    park.acquire_lease(tmp_path, _holder(), TEXTS, context)
    assert park.unit_state(tmp_path, TEXTS, context) == "active"
    assert park.unit_state(tmp_path, TEXTS, _context(now=context.now + 48 * HOURS)) == "not started"


def test_exporting_a_kit_leaves_the_leases_out(project, tmp_path, capsys):
    kit = _plan_kit(project)
    _write(project, kit_id=KIT_ID, name="holders-jobs")
    folder = _make_job(kit, 1, "Lease module", steps=("first",))
    park.acquire_lease(kit, _holder(), TEXTS, _live_context())
    park.acquire_lease(folder, _holder("s2"), TEXTS, _live_context())
    bundle = tmp_path / "out" / "bundle.md"
    capsys.readouterr()
    assert _run(project, "export", KIT_ID, "--out", str(bundle)) == 0
    assert capsys.readouterr().out == f"{bundle.as_posix()}\n"
    text = bundle.read_text(encoding="utf-8")
    assert text.startswith(f"# akmon kit bundle: {KIT_NAME}\n")
    for name in ("PARK.md", "PLAN.md", "RESUME.md", "jobs/1-lease-module/JOB.md"):
        assert f"--- file: {name}\n" in text
    assert "HOLDER" not in text and "session: s1" not in text and "session: s2" not in text
    assert text.count("--- end") == 4
    assert (kit / "HOLDER").is_file() and (folder / "HOLDER").is_file()  # the export leaves the source alone


def test_export_needs_an_out_flag():
    with pytest.raises(SystemExit) as exc:
        park.main(["export", "C1"])
    assert exc.value.code == 2


# --------------------------------------------------------------------------------------
# the lease through the command line
# --------------------------------------------------------------------------------------


def test_hold_takes_the_lease_of_a_kit_and_prints_the_holder(project, capsys):
    _write(project)
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    assert capsys.readouterr().out == f"C183-park-helper: claude s1 laptop {Path.cwd()}\n"
    assert (_kit(project) / "HOLDER").is_file()


def test_a_second_session_on_a_held_kit_is_refused_with_the_holder_named(project, capsys):
    _write(project)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert "--takeover" in err
    assert park.read_lease(_kit(project), TEXTS).holder.session_id == "s1"


def test_the_same_session_holds_again_and_a_takeover_needs_the_flag(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1"))
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert park.read_lease(_kit(project), TEXTS).holder.session_id == "s2"
    assert park.read_note(_kit(project), TEXTS)[0].sessions == (park.SessionRef("claude", "s1", LAPTOP),)


def test_a_lease_from_another_machine_is_stale_at_once_and_still_needs_the_flag(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1", machine="desktop"))
    capsys.readouterr()
    assert _run(project, "hold", "C183", *_session("s2", machine=LAPTOP)) == 1
    assert "whose lease is stale" in capsys.readouterr().err
    assert _run(project, "hold", "C183", *_session("s2", machine=LAPTOP), "--takeover") == 0
    assert park.read_lease(_kit(project), TEXTS).holder == park.Holder("claude", "s2", LAPTOP, str(Path.cwd()))


def test_a_lease_older_than_the_threshold_is_stale_through_the_command_line(project, capsys):
    _write(project)
    old = park.Lease(_holder("s1"), time.time() - 25 * HOURS)
    (_kit(project) / "HOLDER").write_text(park.render_lease(old), encoding="utf-8")
    assert _listed(project, capsys)[0].split(" | ")[2] == "parked"
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    assert "whose lease is stale" in capsys.readouterr().err
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0


def test_a_lease_just_inside_the_threshold_still_holds(project, capsys):
    _write(project)
    fresh = park.Lease(_holder("s1"), time.time() - 23 * HOURS)
    (_kit(project) / "HOLDER").write_text(park.render_lease(fresh), encoding="utf-8")
    assert _listed(project, capsys)[0].split(" | ")[2] == "active"
    assert _run(project, "hold", "C183", *_session("s2")) == 1
    assert "whose lease is stale" not in capsys.readouterr().err


def test_release_frees_the_unit_and_a_free_unit_has_no_holder_to_release(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1"))
    capsys.readouterr()
    assert _run(project, "release", "C183") == 0
    assert capsys.readouterr().out == "C183-park-helper\n"
    assert not (_kit(project) / "HOLDER").exists()
    assert _run(project, "release", "C183") == 1
    assert capsys.readouterr().err == "error: C183-park-helper has no holder file\n"
    assert _run(project, "hold", "C183", *_session("s2")) == 0


def test_hold_and_release_act_on_a_job_by_number(project, capsys):
    _plan_kit(project)
    assert _run(project, "hold", KIT_ID, "--number", "1") == 1
    assert capsys.readouterr().err == f"error: kit {KIT_NAME} has no job C186.1\n"
    _job(project, 1, "--step", "first", session="s1")
    _run(project, "release", KIT_ID, "--number", "1")
    folder = _kit(project, KIT_NAME) / "jobs" / "1-lease-module"
    assert not (folder / "HOLDER").exists()
    capsys.readouterr()
    assert _run(project, "hold", KIT_ID, "--number", "1", *_session("s2")) == 0
    assert capsys.readouterr().out.startswith("1-lease-module: claude s2 laptop ")
    assert not (_kit(project, KIT_NAME) / "HOLDER").exists()  # the job's lease is not the plan's


def test_write_into_a_unit_another_session_holds_is_refused_and_the_note_is_untouched(project, capsys):
    _write(project)
    before = (_kit(project) / "PARK.md").read_bytes()
    _run(project, "hold", "C183", *_session("s1"))
    capsys.readouterr()
    assert _write(project, *_session("s2"), "--decision", "D-NEW") == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert "read the note, hold another unit, or ask the owner" in err
    assert (_kit(project) / "PARK.md").read_bytes() == before


def test_write_by_the_holder_parks_the_unit_and_releases_the_lease(project, capsys):
    _write(project)
    _run(project, "hold", "C183", *_session("s1"))
    assert _listed(project, capsys)[0].split(" | ")[2] == "active"
    assert _write(project, *_session("s1")) == 0
    assert not (_kit(project) / "HOLDER").exists()
    assert _listed(project, capsys)[0].split(" | ")[2] == "parked"


def test_write_over_a_stale_lease_is_refused_and_changes_nothing(project, capsys):
    _write(project)
    _stale_lease_of(_kit(project))
    lease_before = (_kit(project) / "HOLDER").read_bytes()
    note_before = (_kit(project) / "PARK.md").read_bytes()
    capsys.readouterr()
    assert _write(project, *_session("s2"), "--decision", "D-NEW") == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop /work/tree, whose lease is stale;")
    assert "hold --takeover" in err
    assert "the owner's word" in err
    assert err.count("\n") == 1
    assert (_kit(project) / "HOLDER").read_bytes() == lease_before
    assert (_kit(project) / "PARK.md").read_bytes() == note_before


def test_write_after_a_takeover_goes_through_and_keeps_the_replaced_holder(project):
    _write(project)
    _stale_lease_of(_kit(project))
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert _write(project, *_session("s2")) == 0
    assert not (_kit(project) / "HOLDER").exists()
    sessions = park.read_note(_kit(project), TEXTS)[0].sessions
    assert sessions == (park.SessionRef("claude", "s1", LAPTOP), park.SessionRef("claude", "s2", LAPTOP))


def test_write_keeps_the_sessions_of_the_note_and_adds_the_new_ones_once(project):
    assert _write(project, *_session("s1")) == 0
    assert _write(project, *_session("s2")) == 0
    assert _write(project, *_session("s1")) == 0
    sessions = park.read_note(_kit(project), TEXTS)[0].sessions
    assert sessions == (park.SessionRef("claude", "s1", LAPTOP), park.SessionRef("claude", "s2", LAPTOP))
    assert _write(project) == 0  # a write that names no session keeps the ones the note has
    assert park.read_note(_kit(project), TEXTS)[0].sessions == sessions


def test_write_merges_the_holder_a_takeover_kept_before_the_kit_had_a_note(project):
    kit = _kit(project)
    kit.mkdir(parents=True)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    _stale_lease_of(kit)
    assert _run(project, "hold", "C183", *_session("s2"), "--takeover") == 0
    assert (kit / "SESSIONS").is_file()
    assert _write(project, *_session("s2")) == 0
    assert park.read_note(kit, TEXTS)[0].sessions == (
        park.SessionRef("claude", "s1", LAPTOP),
        park.SessionRef("claude", "s2", LAPTOP),
    )
    assert sorted(path.name for path in kit.iterdir()) == ["PARK.md", "RESUME.md"]


def test_a_takeover_of_a_job_is_kept_in_the_job_file_through_the_command_line(project):
    kit = _plan_kit(project)
    assert _job(project, 1, "--step", "first") == 0
    folder = kit / "jobs" / "1-lease-module"
    _stale_lease_of(folder)
    assert _run(project, "hold", KIT_ID, "--number", "1", *_session("s2"), "--takeover") == 0
    assert park.read_job_doc(folder / "JOB.md", TEXTS).header.sessions == (park.SessionRef("claude", "s1", LAPTOP),)
    assert _job(project, 1, "--step", "second", session="s2") == 0
    assert park.read_job_doc(folder / "JOB.md", TEXTS).header.sessions == (park.SessionRef("claude", "s1", LAPTOP),)


def test_a_write_that_fails_leaves_no_lease_and_no_folder_behind(project, capsys):
    _write(project)
    capsys.readouterr()
    assert _write(project, kit_id="C183", name="other-name") == 1  # the id is taken under another name
    assert not (_kit(project, "C183-other-name")).exists()
    assert _write(project, "--origin", "two\nlines", kit_id="C184", name="new-kit") == 1
    assert not (_kit(project, "C184-new-kit")).exists()


def test_write_refuses_to_reuse_the_id_and_name_of_a_closed_kit(project, capsys):
    _write(project)
    assert _run(project, "close", "C183") == 0
    capsys.readouterr()
    assert _write(project) == 1
    err = capsys.readouterr().err
    assert err == "error: kit C183-park-helper is closed and keeps its id and name; write under another id or name\n"
    assert not _kit(project).exists()


def test_close_refuses_a_kit_a_live_session_holds_and_changes_nothing(project, capsys):
    _write(project)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    capsys.readouterr()
    assert _run(project, "close", "C183", *_session("s2")) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert err.count("\n") == 1
    assert (_kit(project) / "HOLDER").is_file()
    assert not _closed(project, "C183-park-helper").exists()


def test_close_refuses_a_kit_whose_job_a_live_session_holds(project, capsys):
    kit = _plan_kit(project)
    _write(project, kit_id=KIT_ID, name="holders-jobs")
    assert _job(project, 1, "--step", "first", session="s1") == 0
    capsys.readouterr()
    assert _run(project, "close", KIT_ID, *_session("s2")) == 1
    assert capsys.readouterr().err.startswith("error: 1-lease-module is held by claude s1 laptop ")
    assert (kit / "jobs" / "1-lease-module" / "HOLDER").is_file()


def test_close_by_the_holder_releases_its_leases_and_a_stale_lease_does_not_block(project, capsys):
    _write(project)
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    assert _run(project, "close", "C183", *_session("s1")) == 0
    assert list(_closed(project, "C183-park-helper").rglob("HOLDER")) == []
    _write(project, kit_id="C184", name="second")
    _stale_lease_of(_kit(project, "C184-second"))
    capsys.readouterr()
    assert _run(project, "close", "C184", *_session("s2")) == 0
    assert list(_closed(project, "C184-second").rglob("HOLDER")) == []


def test_close_over_an_existing_closed_kit_is_one_line_and_changes_nothing(project, capsys):
    _write(project)
    target = _closed(project, "C183-park-helper")
    target.mkdir(parents=True)
    (target / "mark").write_text("old", encoding="utf-8")
    assert _run(project, "hold", "C183", *_session("s1")) == 0
    capsys.readouterr()
    assert _run(project, "close", "C183", *_session("s1")) == 1
    err = capsys.readouterr().err
    assert err == "error: kit C183-park-helper was not closed: _aitna/.ergon/.closed/C183-park-helper already exists\n"
    assert (_kit(project) / "HOLDER").is_file()
    assert (_kit(project) / "PARK.md").is_file()
    assert [path.name for path in target.iterdir()] == ["mark"]


def test_write_by_an_anonymous_session_over_an_anonymous_lease_is_refused(project, capsys):
    _write(project)
    (_kit(project) / "HOLDER").write_text(
        park.render_lease(park.Lease(park.Holder("", "", "", ""), time.time())), encoding="utf-8"
    )
    capsys.readouterr()
    assert _write(project) == 1
    assert "C183-park-helper is held by ? ? ?" in capsys.readouterr().err


# --------------------------------------------------------------------------------------
# the plan and its job lines
# --------------------------------------------------------------------------------------


def test_the_plan_header_and_the_jobs_section_are_parsed():
    plan = park.parse_plan(PLAN)
    assert plan.header == park.PlanHeader(
        id="C186", name="holders-jobs", title="Holders and jobs", tasks=("C186", "C187")
    )
    assert [job.id for job in plan.jobs] == ["C186.1", "C186.2", "C186.3"]
    assert plan.jobs[0] == park.JobLine(
        id="C186.1",
        number=1,
        label="Lease module",
        tasks=("C186",),
        paths=("tools/park", "meta/tests"),
        harness="claude",
        result="a held job is refused",
    )
    assert plan.jobs[1].after == ("C186.1",)
    assert plan.jobs[2].tasks == ("C187",)


def test_a_plan_with_no_header_and_no_jobs_is_empty():
    assert park.parse_plan("just prose\n") == park.Plan()
    assert park.parse_plan("---\nid: A1\nname: x\n---\n").jobs == ()


def test_a_job_line_is_only_a_dash_line_with_a_job_id_and_a_label():
    assert park.parse_job_line("not a list item") is None
    assert park.parse_job_line("- C186.1") is None
    assert park.parse_job_line("- C186 · no number") is None
    assert park.parse_job_line("- x1.1 · bad id") is None
    line = park.parse_job_line("- _T3.2 · A local job · tasks _T3 · result: ok")
    assert (line.id, line.number, line.tasks, line.result) == ("_T3.2", 2, ("_T3",), "ok")


def test_a_kit_with_no_plan_has_none_and_one_with_a_plan_reads_it(project):
    kit = _kit(project, "C5-a")
    kit.mkdir(parents=True)
    assert park.read_plan(kit) is None
    (kit / "PLAN.md").write_text(PLAN, encoding="utf-8")
    assert park.read_plan(kit).header.id == "C186"


@pytest.mark.parametrize(
    ("label", "slug"),
    [
        ("Lease module", "lease-module"),
        ("  Holders & jobs!  ", "holders-jobs"),
        ("a" * 60, "a" * 40),
        ("x" * 39 + " y", "x" * 39),
    ],
)
def test_a_job_folder_is_named_from_its_label(label, slug):
    assert park.job_slug(label) == slug


# --------------------------------------------------------------------------------------
# the job file and the job command
# --------------------------------------------------------------------------------------


def test_the_first_job_write_creates_the_folder_the_file_and_takes_the_lease(project, capsys):
    kit = _plan_kit(project)
    assert _job(project, 1, "--step", "write the lease", "--step", "test it") == 0
    assert capsys.readouterr().out == f"_aitna/.ergon/{KIT_NAME}/jobs/1-lease-module\n"
    folder = kit / "jobs" / "1-lease-module"
    assert sorted(path.name for path in folder.iterdir()) == ["HOLDER", "JOB.md"]
    doc = park.read_job_doc(folder / "JOB.md", TEXTS)
    assert doc.steps == (("write the lease", False), ("test it", False))
    assert not doc.done
    assert dataclasses.replace(doc.header, branch="") == park.ParkFields(
        id=KIT_ID,
        name="holders-jobs",
        next_action="a held job is refused",
        plan=KIT_ID,
        job="C186.1",
        tasks=("C186",),
    )
    assert park.read_lease(folder, TEXTS).holder.session_id == "s1"


def test_a_later_job_write_appends_steps_and_keeps_the_old_ones(project):
    folder = _plan_kit(project) / "jobs" / "1-lease-module"
    _job(project, 1, "--step", "one")
    _job(project, 1, "--step", "two")
    doc = park.read_job_doc(folder / "JOB.md", TEXTS)
    assert [text for text, _done in doc.steps] == ["one", "two"]
    assert doc.next_step() == "one"


def test_the_job_file_marks_steps_and_the_done_marker_and_round_trips(project):
    header = park.ParkFields(id=KIT_ID, name="holders-jobs", next_action="the result", job="C186.1")
    doc = park.JobDoc(header, (("first", True), ("second", False)), done=False)
    text = park.render_job_doc(doc, TEXTS)
    assert "## Steps\n\n- [x] first\n- [ ] second\n" in text
    assert park.parse_job_doc(text, "JOB.md", TEXTS) == doc
    assert park.parse_job_doc(text, "JOB.md", TEXTS).next_step() == "second"
    finished = dataclasses.replace(doc, done=True)
    finished_text = park.render_job_doc(finished, TEXTS)
    assert finished_text.rstrip("\n").endswith("\ndone")
    assert park.parse_job_doc(finished_text, "JOB.md", TEXTS) == finished
    assert park.JobDoc(header, (("a", True),)).next_step() == ""


def test_a_job_with_no_steps_reads_back_with_none_and_a_step_named_done_is_no_marker():
    header = park.ParkFields(id=KIT_ID, name="holders-jobs", next_action="the result", job="C186.1")
    empty = park.render_job_doc(park.JobDoc(header), TEXTS)
    assert "_none_" in empty
    assert park.parse_job_doc(empty, "JOB.md", TEXTS) == park.JobDoc(header)
    named = park.JobDoc(header, (("done", False),))
    assert park.parse_job_doc(park.render_job_doc(named, TEXTS), "JOB.md", TEXTS) == named


def test_job_done_writes_the_marker_once_and_keeps_it(project, capsys):
    folder = _plan_kit(project) / "jobs" / "1-lease-module"
    _job(project, 1, "--step", "only", "--done")
    assert park.read_job_doc(folder / "JOB.md", TEXTS).done
    _job(project, 1, "--step", "late")
    doc = park.read_job_doc(folder / "JOB.md", TEXTS)
    assert doc.done and len(doc.steps) == 2
    assert (folder / "JOB.md").read_text(encoding="utf-8").count("\ndone\n") == 1


def test_a_job_the_plan_does_not_name_is_refused(project, capsys):
    _plan_kit(project)
    assert _job(project, 9) == 1
    assert capsys.readouterr().err == f"error: kit {KIT_NAME} has no job C186.9\n"
    assert not (_kit(project, KIT_NAME) / "jobs").exists()


def test_a_kit_with_no_plan_has_no_jobs_to_write(project, capsys):
    _kit(project, KIT_NAME).mkdir(parents=True)
    assert _job(project, 1) == 1
    assert capsys.readouterr().err == f"error: kit {KIT_NAME} has no PLAN.md, so it has no jobs\n"
    assert not (_kit(project, KIT_NAME) / "jobs").exists()


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("- C186.1 ·  · result: r", "error: job C186.1 has no label, so its folder has no name\n"),
        ("- C186.1 · Lease module · tasks C186", f"error: kit {KIT_NAME}: job C186.1 has no result\n"),
        ("- C186.1 · Lease module · result:", f"error: kit {KIT_NAME}: job C186.1 has no result\n"),
    ],
)
def test_a_job_line_the_helper_cannot_write_from_is_refused_before_anything_is_written(project, capsys, line, message):
    kit = _plan_kit(project, f"---\nid: C186\nname: holders-jobs\n---\n\n## Jobs\n\n{line}\n")
    assert _job(project, 1, "--step", "x") == 1
    assert capsys.readouterr().err == message
    assert not (kit / "jobs").exists()
    assert list(kit.rglob("HOLDER")) == []


def test_the_job_command_prints_the_plans_shared_path_warnings_on_stderr(project, capsys):
    _plan_kit(
        project,
        "---\nid: C186\nname: holders-jobs\n---\n\n## Jobs\n\n"
        "- C186.1 · Lease module · paths tools/park · result: r\n"
        "- C186.2 · Job file · paths tools/park/park.py · result: r\n",
    )
    assert _job(project, 1, "--step", "x") == 0
    captured = capsys.readouterr()
    assert captured.out == f"_aitna/.ergon/{KIT_NAME}/jobs/1-lease-module\n"
    assert captured.err == "warning: jobs C186.1 C186.2 may run at once and share path tools/park\n"


def test_the_job_command_prints_no_warning_for_a_plan_with_no_shared_path(project, capsys):
    _plan_kit(project)
    capsys.readouterr()
    assert _job(project, 1, "--step", "x") == 0
    assert capsys.readouterr().err == ""


def test_a_second_session_writing_a_held_job_is_refused_with_the_holder_named(project, capsys):
    folder = _plan_kit(project) / "jobs" / "1-lease-module"
    assert _job(project, 1, "--step", "mine", session="s1") == 0
    before = (folder / "JOB.md").read_bytes()
    capsys.readouterr()
    assert _job(project, 1, "--step", "intruder", session="s2") == 1
    err = capsys.readouterr().err
    assert err.startswith("error: 1-lease-module is held by claude s1 laptop ")
    assert (folder / "JOB.md").read_bytes() == before
    assert _job(project, 2, "--step", "other job", session="s2") == 0  # another job is its own unit


def test_two_jobs_that_may_run_at_once_and_share_a_path_are_warned_about():
    plan = park.parse_plan(
        "---\nid: C1\nname: k\n---\n\n## Jobs\n\n"
        "- C1.1 · A · paths tools/park, meta/tests · result: r\n"
        "- C1.2 · B · paths tools/park/park.py, docs · result: r\n"
        "- C1.3 · C · paths docs/ · result: r\n"
        "- C1.4 · D · paths js · result: r\n"
        "- C1.5 · E · result: r\n"
    )
    assert park.shared_path_warnings(plan, TEXTS) == [
        "warning: jobs C1.1 C1.2 may run at once and share path tools/park",
        "warning: jobs C1.2 C1.3 may run at once and share path docs",
    ]


def test_a_path_is_shared_by_prefix_by_equality_and_never_by_a_common_stem():
    assert park._paths_overlap("tools/park", "tools/park/park.py")
    assert park._paths_overlap("tools/park/", "tools/park")
    assert park._paths_overlap("docs", "docs")
    assert not park._paths_overlap("tools/park", "tools/parking")
    assert not park._paths_overlap("a", "b")


def test_a_plan_with_no_shared_path_has_no_warning():
    plan = park.parse_plan(PLAN)
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
def test_jobs_that_wait_for_each_other_share_no_warning(lines):
    plan = park.parse_plan("---\nid: C1\nname: k\n---\n\n## Jobs\n\n" + "\n".join(lines) + "\n")
    assert park.shared_path_warnings(plan, TEXTS) == []


# --------------------------------------------------------------------------------------
# unpark and digest
# --------------------------------------------------------------------------------------


def test_unpark_takes_the_lease_and_prints_resume_then_the_digest(project, capsys):
    _write(project, "--decision", "D-X", "--answer", "owner: go", "--plan", "A59")
    capsys.readouterr()
    assert _run(project, "unpark", "C183", *_session("s1")) == 0
    out = capsys.readouterr().out
    resume = (_kit(project) / "RESUME.md").read_text(encoding="utf-8")
    assert out.startswith(resume.rstrip("\n") + "\n\npark C183-park-helper · active\n")
    assert out.endswith("Owner answers:\n- owner: go\n")
    assert park.read_lease(_kit(project), TEXTS).holder.session_id == "s1"
    _no_index_anywhere(project)


def test_unpark_by_a_second_session_is_refused_with_the_holder_named(project, capsys):
    _write(project)
    _run(project, "unpark", "C183", *_session("s1"))
    capsys.readouterr()
    assert _run(project, "unpark", "C183", *_session("s2")) == 1
    assert capsys.readouterr().err.startswith("error: C183-park-helper is held by claude s1 laptop ")
    assert _run(project, "unpark", "C183", *_session("s1")) == 0


def test_unpark_names_the_candidates_when_no_kit_matches(project, capsys):
    _write(project)
    assert _run(project, "unpark", "C999") == 1
    assert capsys.readouterr().err == "error: no kit with id C999 under _aitna/.ergon; kits: C183-park-helper\n"


def test_unpark_with_no_kits_at_all_says_none(project, capsys):
    assert _run(project, "unpark", "C1") == 1
    assert capsys.readouterr().err == "error: no kit with id C1 under _aitna/.ergon; kits: none\n"


def test_unpark_names_the_kits_when_several_carry_the_id(project, capsys):
    for name in ("C5-a", "C5-b", "C50-c"):
        _kit(project, name).mkdir(parents=True)
    assert _run(project, "unpark", "C5") == 1
    assert capsys.readouterr().err == "error: several kits carry id C5 under _aitna/.ergon: C5-a, C5-b\n"


def test_digest_of_a_kit_that_was_never_parked_is_refused(project, capsys):
    _kit(project, "C5-a").mkdir(parents=True)
    assert _run(project, "digest", "C5") == 1
    assert capsys.readouterr().err == "error: kit C5-a was never parked: it has no PARK.md\n"


def test_unpark_of_a_kit_with_no_resume_prompt_is_refused(project, capsys):
    _kit(project, "C5-a").mkdir(parents=True)
    assert _run(project, "unpark", "C5") == 1
    assert capsys.readouterr().err == "error: kit C5-a has no RESUME.md; write it again to regenerate it\n"


def test_a_refused_unpark_leaves_no_lease_behind(project):
    _kit(project, "C5-a").mkdir(parents=True)
    assert _run(project, "unpark", "C5", *_session("s1")) == 1
    assert not (_kit(project, "C5-a") / "HOLDER").exists()


def test_an_unpark_of_a_kit_with_a_resume_prompt_and_no_note_leaves_no_lease_behind(project, capsys):
    kit = _kit(project, "C5-a")
    kit.mkdir(parents=True)
    (kit / "RESUME.md").write_text("# Resume C5-a\n", encoding="utf-8")
    assert _run(project, "unpark", "C5", *_session("s1")) == 1
    assert capsys.readouterr().err == "error: kit C5-a was never parked: it has no PARK.md\n"
    assert not (kit / "HOLDER").exists()


def _kit_with_answers(project: Path, count: int) -> Path:
    body = park.ParkBody(goal="Goal line", answers=tuple(f"answer {number:02d}" for number in range(count)))
    fields = park.ParkFields(id="C9", name="long", next_action="Next")
    return park.write_kit(fields, body, project, TEXTS, project)


def test_digest_within_the_cap_is_whole_and_has_no_overflow_line(project):
    kit = _kit_with_answers(project, 2)
    text = park.digest(kit, 3000, project, TEXTS)
    assert text == (
        "park C9-long · parked\nGoal: Goal line\nNext action: Next\nOpen decisions: none\n"
        "Owner answers:\n- answer 00\n- answer 01"
    )


def test_digest_names_the_derived_state_of_the_kit(project):
    kit = _kit_with_answers(project, 1)
    park.acquire_lease(kit, _holder(), TEXTS, _live_context())
    assert park.digest(kit, 3000, project, TEXTS).startswith("park C9-long · active\n")
    park.release_lease(kit)
    assert park.digest(kit, 3000, project, TEXTS).startswith("park C9-long · parked\n")


def test_digest_is_cut_at_a_whole_line_and_names_the_overflow(project):
    kit = _kit_with_answers(project, 10)
    full = park.digest(kit, 3000, project, TEXTS).split("\n")
    # keep the title, goal, next, decisions-none and the answers heading, plus 2 answers
    kept = full[:7]
    cap = sum(len(line) + 1 for line in kept)
    text = park.digest(kit, cap, project, TEXTS)
    assert text.split("\n")[:-1] == kept
    assert text.split("\n")[-1] == "… 8 more lines in _aitna/.ergon/C9-long/PARK.md"
    # one character short of the next line: it is dropped whole, never cut; with room for it, it is kept
    assert park.digest(kit, cap + len("- answer 02"), project, TEXTS).split("\n")[-1].startswith("… 8 more")
    assert park.digest(kit, cap + len("- answer 02") + 1, project, TEXTS).split("\n")[-1].startswith("… 7 more")


def test_digest_with_a_tiny_cap_is_only_the_overflow_line(project):
    kit = _kit_with_answers(project, 1)
    assert park.digest(kit, 0, project, TEXTS) == "… 6 more lines in _aitna/.ergon/C9-long/PARK.md"


def test_digest_without_a_root_names_the_note_by_kit(project):
    kit = _kit_with_answers(project, 1)
    assert park.digest(kit, 0, None, TEXTS).endswith("lines in C9-long/PARK.md")


def test_digest_reads_its_own_texts_when_called_alone(project):
    kit = _kit_with_answers(project, 1)
    assert park.digest(kit, 3000).startswith("park C9-long · parked")


def test_digest_indents_the_continuation_of_a_multiline_goal(project):
    fields = park.ParkFields(id="C9", name="long", next_action="Next", plan="A59", readiness="ready")
    kit = park.write_kit(fields, park.ParkBody(goal="one\ntwo"), project, TEXTS, project)
    assert park.digest(kit, 3000, project, TEXTS).split("\n")[:6] == [
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
    lines = park.digest(_kit(project), 3000, project, TEXTS).split("\n")
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
    kit = _kit_with_answers(project, 400)
    capsys.readouterr()
    _run(project, "digest", "C9")
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1].startswith("… ") and "more lines in _aitna/.ergon/C9-long/PARK.md" in lines[-1]
    assert sum(len(line) + 1 for line in lines[:-1]) <= 3000
    assert kit.is_dir()


# --------------------------------------------------------------------------------------
# list: the derived state per kit and per job
# --------------------------------------------------------------------------------------


def test_list_of_an_empty_ergon_says_so(project, capsys):
    assert _run(project, "list") == 0
    assert capsys.readouterr().out == "no kits in _aitna/.ergon\n"
    (project / "_aitna" / ".ergon").mkdir(parents=True)
    _run(project, "list")
    assert capsys.readouterr().out == "no kits in _aitna/.ergon\n"


def _populate(project: Path) -> None:
    _write(project, "--plan", "A59", "--decision", "D-X", "--decision", "D-Y")
    _write(project, "--plan", "A60", kit_id="A5", name="second")
    _kit(project, "C7-never").mkdir()
    _write(project, kit_id="C20", name="third")
    _run(project, "unpark", "C20", *_session("s1"))


def test_list_prints_one_line_per_kit_sorted_by_id_with_its_derived_state(project, capsys):
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
    assert _kit_ids(_listed(project, capsys, "--plan", "A59")) == ["C183"]
    assert _kit_ids(_listed(project, capsys, "--state", "parked")) == ["A5", "C183"]
    assert _kit_ids(_listed(project, capsys, "--state", "not started")) == ["C7"]
    assert _kit_ids(_listed(project, capsys, "--state", "active")) == ["C20"]
    assert _listed(project, capsys, "--plan", "A59", "--state", "active") == ["no kit matches the filters"]


def test_the_state_filter_is_the_derived_state_and_the_old_status_flag_is_gone(project, capsys):
    _populate(project)
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        _run(project, "list", "--status", "parked")
    assert exc.value.code == 2


def test_list_reads_a_lease_from_another_machine_as_stale(project, capsys):
    _populate(project)
    assert _kit_ids(_listed(project, capsys, "--state", "active")) == ["C20"]
    capsys.readouterr()
    _run(project, "list", "--machine", "desktop")
    states = {line.split(" | ")[0]: line.split(" | ")[2] for line in capsys.readouterr().out.splitlines()}
    assert states["C20"] == "parked"


def test_a_kit_with_a_note_in_the_old_format_lists_as_parked_whatever_its_old_state_said(project, capsys):
    kit = _kit(project)
    kit.mkdir(parents=True)
    (kit / "PARK.md").write_text(LEGACY_NOTE, encoding="utf-8")
    assert _listed(project, capsys)[0].split(" | ")[:3] == ["C183", "park-helper", "parked"]


def test_list_shows_the_jobs_of_a_kit_under_it_with_their_own_states(project, capsys):
    kit = _plan_kit(project)
    _job(project, 1, "--step", "write the lease", session="s1")  # held: active
    _make_job(kit, 2, "Job file", steps=("later",))  # no lease, no note: not started
    _job(project, 3, "--done", session="s1")
    park.release_lease(kit / "jobs" / "3-docs")  # done stays done whoever held it
    lines = _listed(project, capsys)
    assert lines == [
        f"{KIT_ID} | holders-jobs | active | - | - | 0 | - | -",  # a held job makes its kit active
        "  C186.1 | 1-lease-module | active | C186 | write the lease | - | 0d",
        "  C186.2 | 2-job-file | not started | C186 | later | - | 0d",
        "  C186.3 | 3-docs | done | C187 | - | - | 0d",
    ]


def test_a_job_with_a_note_and_no_lease_lists_as_parked(project, capsys):
    kit = _plan_kit(project)
    folder = _make_job(kit, 1, "Lease module")
    note = park.render_note(park.ParkFields(id=KIT_ID, name="holders-jobs", next_action="n"), park.ParkBody("g"), TEXTS)
    (folder / "PARK.md").write_text(note, encoding="utf-8")
    assert _listed(project, capsys)[1].split(" | ")[2] == "parked"
    park.acquire_lease(folder, park.Holder("claude", "s1", LAPTOP, "/w"), TEXTS, _live_context())
    assert _listed(project, capsys)[1].split(" | ")[2] == "active"


def test_a_kit_whose_jobs_are_all_done_is_done_and_one_with_a_job_left_is_not(project):
    kit = _plan_kit(project)
    _make_job(kit, 1, "Lease module", done=True)
    _make_job(kit, 2, "Job file", done=True)
    assert park.kit_state(kit, TEXTS, _live_context()) == "not started"  # the plan's third job has no folder
    _make_job(kit, 3, "Docs", done=True)
    assert park.kit_state(kit, TEXTS, _live_context()) == "done"
    _make_job(kit, 3, "Docs")
    assert park.kit_state(kit, TEXTS, _live_context()) == "not started"
    (kit / "PARK.md").write_text("note", encoding="utf-8")
    assert park.kit_state(kit, TEXTS, _live_context()) == "parked"
    park.acquire_lease(kit, _holder(), TEXTS, _live_context())
    assert park.kit_state(kit, TEXTS, _live_context()) == "active"


PLAN_WITH_BAD_ID = PLAN.replace("id: C186\n", "id: c3\n", 1)


def test_a_plan_whose_id_is_no_task_id_is_refused_before_the_job_file_or_the_lease_exists(project, capsys):
    kit = _plan_kit(project, PLAN_WITH_BAD_ID)
    assert _job(project, 1, "--step", "x") == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"error: kit {KIT_NAME}: plan c3 is not a task id "
        "(a capital letter or _T followed by digits, e.g. C183 or _T3)\n"
    )
    assert not (kit / "jobs").exists()


def test_a_job_file_is_replaced_atomically_and_leaves_no_temporary_file(project, monkeypatch):
    kit = _plan_kit(project)
    folder = _make_job(kit, 1, "Lease module", steps=("first",))
    before = (folder / "JOB.md").read_bytes()
    doc = park.read_job_doc(folder / "JOB.md", TEXTS)

    def refuse(self, target):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        park.write_job_doc(folder, dataclasses.replace(doc, steps=(("second", False),)), TEXTS)
    monkeypatch.undo()
    assert (folder / "JOB.md").read_bytes() == before
    assert sorted(path.name for path in folder.iterdir()) == ["JOB.md"]
    park.write_job_doc(folder, dataclasses.replace(doc, steps=(("second", False),)), TEXTS)
    assert park.read_job_doc(folder / "JOB.md", TEXTS).steps == (("second", False),)
    assert sorted(path.name for path in folder.iterdir()) == ["JOB.md"]


def test_a_kit_is_active_when_any_of_its_jobs_is_held(project):
    kit = _plan_kit(project)
    assert _job(project, 1, "--step", "write the lease") == 0
    assert park.kit_state(kit, TEXTS, _live_context()) == "active"  # the kit itself is free
    park.release_lease(kit / "jobs" / "1-lease-module")
    assert park.kit_state(kit, TEXTS, _live_context()) == "not started"


def test_a_kit_is_parked_when_any_of_its_jobs_is_parked_and_active_beats_parked(project):
    kit = _plan_kit(project)
    folder = _make_job(kit, 1, "Lease module")
    note = park.render_note(park.ParkFields(id=KIT_ID, name="holders-jobs", next_action="n"), park.ParkBody("g"), TEXTS)
    (folder / "PARK.md").write_text(note, encoding="utf-8")
    assert park.kit_state(kit, TEXTS, _live_context()) == "parked"
    other = _make_job(kit, 2, "Job file")
    park.acquire_lease(other, _holder(), TEXTS, _live_context())
    assert park.kit_state(kit, TEXTS, _live_context()) == "active"


def test_a_kit_with_every_job_done_is_done_unless_the_kit_itself_is_held(project):
    kit = _plan_kit(project)
    for number, label in ((1, "Lease module"), (2, "Job file"), (3, "Docs")):
        _make_job(kit, number, label, done=True)
    (kit / "PARK.md").write_text("note", encoding="utf-8")  # a stale note of the plan does not undo done
    assert park.kit_state(kit, TEXTS, _live_context()) == "done"
    park.acquire_lease(kit, _holder(), TEXTS, _live_context())
    assert park.kit_state(kit, TEXTS, _live_context()) == "active"


def test_a_planned_job_with_a_folder_but_no_job_file_blocks_done(project):
    kit = _plan_kit(project)
    _make_job(kit, 1, "Lease module", done=True)
    (kit / "jobs" / "2-job-file").mkdir()
    _make_job(kit, 3, "Docs", done=True)
    assert park.kit_state(kit, TEXTS, _live_context()) == "not started"


def test_a_kit_with_no_plan_or_a_plan_with_no_jobs_is_done_by_the_job_folders_that_exist(project):
    bare = _kit(project, "C5-bare")
    bare.mkdir(parents=True)
    assert park.kit_state(bare, TEXTS, _live_context()) == "not started"  # no folder, nothing done
    empty = _plan_kit(project, "---\nid: C6\nname: empty\n---\n\n## Jobs\n\n", "C6-empty")
    for kit in (bare, empty):
        _make_job(kit, 1, "Only", done=True)
        assert park.kit_state(kit, TEXTS, _live_context()) == "done"


def test_a_job_folder_with_no_job_file_is_not_a_job_and_blocks_done(project):
    kit = _plan_kit(project)
    _make_job(kit, 1, "Lease module", done=True)
    (kit / "jobs" / "2-stray").mkdir()
    assert park.summarize_job(kit / "jobs" / "2-stray", TEXTS, _live_context()) is None
    assert park.kit_state(kit, TEXTS, _live_context()) == "not started"
    summaries, jobs = park.list_kits(project, park.ListQuery(), TEXTS, _live_context())
    assert [job.id for job in jobs] == ["C186.1"] and len(summaries) == 1


def test_list_filters_by_task_through_the_plan_header_the_job_lines_and_the_job_files(project, capsys):
    _plan_kit(project)  # the plan header names C186 and C187
    _write(project, "--plan", "A59")  # no plan, no jobs: carries no task
    other = _kit(project, "C300-other")
    other.mkdir()
    (other / "PLAN.md").write_text(
        "---\nid: C300\nname: other\ntitle: t\ntasks: C300\n---\n\n## Jobs\n\n- C300.1 · J · tasks C301 · result: r\n",
        encoding="utf-8",
    )
    folder = other / "jobs" / "2-filed"
    park.write_job_doc(
        folder,
        park.JobDoc(park.ParkFields(id="C300", name="other", next_action="n", job="C300.2", tasks=("C302",))),
        TEXTS,
    )
    assert _kit_ids(_listed(project, capsys, "--task", "C187")) == [KIT_ID]
    assert _kit_ids(_listed(project, capsys, "--task", "C300")) == ["C300"]  # the plan header
    assert _kit_ids(_listed(project, capsys, "--task", "C301")) == ["C300"]  # a job line
    assert _kit_ids(_listed(project, capsys, "--task", "C302")) == ["C300"]  # a job's file
    assert _listed(project, capsys, "--task", "C999") == ["no kit matches the filters"]
    only = _listed(project, capsys, "--task", "C186")
    assert _kit_ids(only) == [KIT_ID]


def test_list_with_closed_adds_the_closed_kits_and_without_it_hides_them(project, capsys):
    _plan_kit(project)
    _write(project)
    assert _run(project, "close", KIT_ID) == 0
    assert _kit_ids(_listed(project, capsys)) == ["C183"]
    assert _kit_ids(_listed(project, capsys, "--closed")) == ["C183", KIT_ID]
    assert _kit_ids(_listed(project, capsys, "--closed", "--task", "C187")) == [KIT_ID]


def test_list_with_only_closed_kits_says_there_are_no_kits_and_with_closed_shows_them(project, capsys):
    _write(project)
    _run(project, "close", "C183")
    assert _listed(project, capsys) == ["no kits in _aitna/.ergon"]
    assert _kit_ids(_listed(project, capsys, "--closed")) == ["C183"]


def test_the_closed_folder_is_no_kit_of_its_own(project, capsys):
    _write(project)
    _run(project, "close", "C183")
    assert park._kit_names(project) == []
    assert park._kit_names(project, closed=True) == ["C183-park-helper"]


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
    note = _kit(project) / "PARK.md"
    context = _live_context()
    now = context.now
    os.utime(note, (now - 3 * 86400 - 100, now - 3 * 86400 - 100))
    [item], _jobs = park.list_kits(project, park.ListQuery(), TEXTS, context)
    assert item.age_days == 3
    assert park.format_summary(item, TEXTS).endswith("| 3d")
    os.utime(note, (now + 500, now + 500))  # a clock behind the file never gives a negative age
    assert park.list_kits(project, park.ListQuery(), TEXTS, context)[0][0].age_days == 0


def test_list_reads_and_writes_nothing(project):
    _populate(project)
    _plan_kit(project)
    _job(project, 1, "--step", "x")
    snapshot = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    before = {p: p.stat().st_mtime_ns for p in snapshot}
    _run(project, "list")
    _run(project, "list", "--state", "parked")
    _run(project, "list", "--closed", "--task", "C186")
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == snapshot
    assert {p: p.stat().st_mtime_ns for p in snapshot} == before
    _no_index_anywhere(project)


def test_list_ignores_folders_that_are_not_kits(project, capsys):
    _write(project)
    (_kit(project).parent / "notes").mkdir()
    (_kit(project).parent / "stray.txt").write_text("x", encoding="utf-8")
    capsys.readouterr()
    _run(project, "list")
    assert capsys.readouterr().out.count("\n") == 1


def test_list_reports_a_kit_whose_note_does_not_parse_on_its_own_line_and_lists_the_others(project, capsys):
    _write(project)
    _write(project, kit_id="C184", name="other")
    (_kit(project) / "PARK.md").write_text("broken\n", encoding="utf-8")
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


def test_list_names_the_kit_and_the_job_file_of_a_job_file_that_does_not_parse(project, capsys):
    kit = _plan_kit(project)
    _make_job(kit, 1, "Lease module")
    (kit / "jobs" / "1-lease-module" / "JOB.md").write_text("no header\n", encoding="utf-8")
    _write(project)
    lines = _listed(project, capsys)
    assert lines[0].startswith("C183 | park-helper | parked | ")
    assert lines[1] == (
        f"{KIT_ID} | holders-jobs | unreadable | "
        f"{KIT_NAME}/jobs/1-lease-module/JOB.md: no header between two '---' lines at the top of the note"
    )


def test_an_unreadable_kit_is_listed_whatever_the_filters_say(project, capsys):
    _write(project)
    (_kit(project) / "PARK.md").write_text("broken\n", encoding="utf-8")
    lines = _listed(project, capsys, "--state", "active")
    assert len(lines) == 1 and lines[0].startswith("C183 | park-helper | unreadable | ")


# --------------------------------------------------------------------------------------
# the local ids and closing a kit
# --------------------------------------------------------------------------------------


def test_the_next_local_id_counts_over_the_live_and_the_closed_kits(project):
    assert park.next_local_id(project) == "_T1"
    _kit(project, "_T1-a").mkdir(parents=True)
    _kit(project, "_T4-b").mkdir()
    _kit(project, "C9-not-local").mkdir()
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
    _kit(project, "_T2-a").mkdir(parents=True)
    assert park.next_local_id(project) == "_T13"
    _closed(project, "_T20-gone").mkdir(parents=True)
    assert park.next_local_id(project) == "_T21"
    assert legacy.read_bytes() == before


def test_the_local_id_command_prints_the_next_free_id_and_writes_nothing(project, capsys):
    assert _run(project, "local-id") == 0
    assert capsys.readouterr().out == "_T1\n"
    assert not (project / "_aitna" / ".ergon").exists()
    _kit(project, "_T2-a").mkdir(parents=True)
    _closed(project, "_T5-gone").mkdir(parents=True)
    assert _run(project, "local-id") == 0
    assert capsys.readouterr().out == "_T6\n"


def test_the_local_id_command_takes_no_holder_flags(project):
    with pytest.raises(SystemExit) as exc:
        _run(project, "local-id", "--harness", "claude")
    assert exc.value.code == 2


def test_closing_the_highest_local_kit_never_frees_its_number(project):
    assert _write(project, kit_id="_T1", name="one") == 0
    assert _write(project, kit_id="_T2", name="two") == 0
    assert park.next_local_id(project) == "_T3"
    assert _run(project, "close", "_T2") == 0
    assert park.next_local_id(project) == "_T3"
    assert _run(project, "close", "_T1") == 0
    assert park.next_local_id(project) == "_T3"


def test_close_moves_the_kit_to_the_closed_folder_and_releases_its_leases(project, capsys):
    kit = _plan_kit(project)
    _write(project, kit_id=KIT_ID, name="holders-jobs")
    _job(project, 1, "--step", "first")
    _run(project, "hold", KIT_ID, *_session("s1"))
    capsys.readouterr()
    assert _run(project, "close", KIT_ID) == 0
    assert capsys.readouterr().out == f"_aitna/.ergon/.closed/{KIT_NAME}\n"
    assert not kit.exists()
    closed = _closed(project, KIT_NAME)
    assert sorted(path.name for path in closed.iterdir()) == ["PARK.md", "PLAN.md", "RESUME.md", "jobs"]
    assert list(closed.rglob("HOLDER")) == []
    assert (closed / "jobs" / "1-lease-module" / "JOB.md").is_file()
    assert _run(project, "unpark", KIT_ID) == 1
    assert capsys.readouterr().err.startswith(f"error: no kit with id {KIT_ID} under _aitna/.ergon; kits: none")


def test_close_of_an_unknown_kit_names_the_candidates(project, capsys):
    _write(project)
    assert _run(project, "close", "C999") == 1
    assert capsys.readouterr().err == "error: no kit with id C999 under _aitna/.ergon; kits: C183-park-helper\n"
    assert _kit(project).is_dir()


def test_find_closed_kit_finds_a_closed_kit_or_none(project):
    _write(project)
    _run(project, "close", "C183")
    assert park.find_closed_kit(project, "C183", TEXTS) == _closed(project, "C183-park-helper")
    assert park.find_closed_kit(project, "C999", TEXTS) is None
    with pytest.raises(park.ParkError, match="no kit with id C183"):
        park.find_kit(project, "C183", TEXTS)


# --------------------------------------------------------------------------------------
# the active unit, read from the worktree's folder (ADR 0028 D10)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("folder", "unit"),
    [
        ("C186-holders-jobs.1", ("C186", 1)),
        ("_T3-scratch.12", ("_T3", 12)),
        ("A59-park-and-resume.5", ("A59", 5)),
        ("C186-holders-jobs", None),
        ("C186-Holders.1", None),
        ("holders-jobs.1", None),
        ("C186-holders-jobs.x", None),
        ("C186-holders-jobs.", None),
        (".1", None),
    ],
)
def test_the_worktree_folder_names_the_kit_and_the_job_number(folder, unit):
    assert park.worktree_unit(Path("/x/.worktrees") / folder) == unit


@pytest.fixture
def worktree_project(tmp_path: Path) -> Path:
    """A project root that sits in ``.worktrees/C186-holders-jobs.1``, with the kit and a job in it."""
    root = tmp_path / ".worktrees" / f"{KIT_NAME}.1"
    (root / "_aitna").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (root / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    kit = _plan_kit(root)
    park.write_job_doc(
        kit / "jobs" / "1-lease-module",
        park.JobDoc(park.ParkFields(id=KIT_ID, name="holders-jobs", next_action="r", job="C186.1")),
        TEXTS,
    )
    return root.resolve()


def test_the_active_unit_is_the_job_the_worktree_folder_names(worktree_project):
    kit, kit_id, number = park.active_unit(worktree_project, TEXTS)
    assert (kit, kit_id, number) == (_kit(worktree_project, KIT_NAME), KIT_ID, 1)


def test_a_session_in_the_main_checkout_has_no_active_unit(project, capsys):
    _plan_kit(project)
    assert park.active_unit(project, TEXTS) is None
    assert _run(project, "active") == 0
    assert capsys.readouterr().out == f"{TEXTS['active']['none']}\n"


def test_a_worktree_of_no_kit_has_no_active_unit(tmp_path, capsys):
    root = tmp_path / ".worktrees" / "C999-nothing.1"
    (root / "_aitna").mkdir(parents=True)
    (root / "AGENTS.md").write_text("", encoding="utf-8")
    (root / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    assert park.active_unit(root.resolve(), TEXTS) is None
    assert _run(root, "active") == 0
    assert capsys.readouterr().out == f"{TEXTS['active']['none']}\n"


def test_active_prints_the_job_with_its_derived_state_and_its_holder(worktree_project, capsys):
    folder = _kit(worktree_project, KIT_NAME) / "jobs" / "1-lease-module"
    path = f"_aitna/.ergon/{KIT_NAME}/jobs/1-lease-module"
    capsys.readouterr()
    assert _run(worktree_project, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out == f"job: C186.1 | 1-lease-module | not started | - | {path}\n"
    park.acquire_lease(folder, park.Holder("claude", "s1", LAPTOP, "/w"), TEXTS, _live_context())
    assert _run(worktree_project, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out == f"job: C186.1 | 1-lease-module | active | claude s1 laptop /w | {path}\n"


def test_active_names_the_kit_when_the_folders_job_has_no_folder_yet(worktree_project, capsys):
    import shutil

    shutil.rmtree(_kit(worktree_project, KIT_NAME) / "jobs")
    capsys.readouterr()
    assert _run(worktree_project, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out == f"kit: C186 | {KIT_NAME} | not started | - | _aitna/.ergon/{KIT_NAME}\n"


# --------------------------------------------------------------------------------------
# ergon_root through the repository's common directory, and a linked worktree
# --------------------------------------------------------------------------------------


def test_the_kits_of_a_linked_worktree_are_the_main_checkouts(linked):
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
    _git(main, "worktree", "add", "-b", "job-1", str(worktree))
    linked_proj = (worktree / "proj").resolve()
    assert project_root.git_common_root(linked_proj) == proj.resolve()
    assert project_root.ergon_root(linked_proj) == proj.resolve() / "_aitna" / ".ergon"


def test_without_git_the_common_root_is_the_project_root(tmp_path, monkeypatch):
    root = tmp_path / "nogit"
    root.mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))
    assert project_root.git_common_root(root) == root


def test_the_common_root_is_resolved_once_per_root(tmp_path, monkeypatch):
    root = tmp_path / "cached"
    root.mkdir()
    calls = []
    real = project_root._resolve_git_common_root
    monkeypatch.setattr(project_root, "_resolve_git_common_root", lambda path: calls.append(path) or real(path))
    project_root.git_common_root(root)
    project_root.git_common_root(root)
    assert calls == [root]


def test_a_session_in_a_linked_worktree_lists_the_main_checkouts_kits(linked, capsys):
    main, worktree = linked
    assert _run(main, "write", "C183", "--name", "park-helper", "--goal", "g", "--next", "Twin it") == 0
    capsys.readouterr()
    assert _run(worktree, "list", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out.startswith("C183 | park-helper | parked | - | Twin it | 0 | ")
    assert park._kit_names(worktree) == ["C183-park-helper"]
    assert not (worktree / "_aitna" / ".ergon").exists()


def test_a_session_in_a_linked_worktree_writes_into_the_main_checkouts_kits(linked, capsys):
    main, worktree = linked
    assert _run(worktree, "write", "C183", "--name", "park-helper", "--goal", "g", "--next", "Twin it") == 0
    assert (main / "_aitna" / ".ergon" / "C183-park-helper" / "PARK.md").is_file()
    assert not (worktree / "_aitna" / ".ergon").exists()


def test_a_session_in_a_linked_worktree_knows_its_job_from_its_folder(linked, capsys):
    main, worktree = linked
    _plan_kit(main)
    assert _job(main, 1, "--step", "first") == 0
    capsys.readouterr()
    assert _run(worktree, "active", "--machine", LAPTOP) == 0
    assert capsys.readouterr().out.startswith("job: C186.1 | 1-lease-module | active | claude s1 laptop ")


def test_a_path_is_printed_from_the_root_when_inside_it_and_as_it_is_when_outside(tmp_path):
    root = tmp_path / "root"
    assert park._display_path(root / "a" / "b.md", root) == "a/b.md"
    assert park._display_path(root, root) == "."
    outside = tmp_path / "main" / "_aitna" / ".ergon"
    assert park._display_path(outside, root) == str(outside)


def test_every_command_of_a_linked_worktree_prints_the_main_checkouts_kit_paths_as_they_are(linked, capsys):
    main, worktree = linked
    ergon = main / "_aitna" / ".ergon"
    assert _run(worktree, "list") == 0
    assert capsys.readouterr().out == f"no kits in {ergon}\n"
    assert _run(worktree, "unpark", "C9") == 1
    assert capsys.readouterr().err == f"error: no kit with id C9 under {ergon}; kits: none\n"
    assert _run(worktree, "write", "C183", "--name", "park-helper", "--goal", "g", "--next", "n") == 0
    kit = ergon / "C183-park-helper"
    assert capsys.readouterr().out == f"{kit}\n"
    assert f"1. Read `{kit / 'PARK.md'}`." in (kit / "RESUME.md").read_text(encoding="utf-8")
    assert _run(worktree, "unpark", "C9") == 1
    assert capsys.readouterr().err == f"error: no kit with id C9 under {ergon}; kits: C183-park-helper\n"
    assert _run(worktree, "digest", "C183", "--cap", "40") == 0
    assert capsys.readouterr().out.endswith(f"… 5 more lines in {kit / 'PARK.md'}\n")
    assert _run(worktree, "close", "C183") == 0
    assert capsys.readouterr().out == f"{ergon / '.closed' / 'C183-park-helper'}\n"


def test_the_job_command_of_a_linked_worktree_prints_the_folder_as_it_is(linked, capsys):
    main, worktree = linked
    _plan_kit(main)
    assert _job(worktree, 1, "--step", "first") == 0
    assert capsys.readouterr().out == f"{_kit(main, KIT_NAME) / 'jobs' / '1-lease-module'}\n"


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
    assert capsys.readouterr().out == "no kits in _aitna/.ergon\n"
