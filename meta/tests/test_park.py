"""Tests for the park helper (tools/park/park.py): the note, the kit, the local index, the commands."""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import time
from pathlib import Path

import pytest

from common import jsondata

_AKMON = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("park_helper", _AKMON / "tools" / "park" / "park.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass resolves its module by name
    spec.loader.exec_module(module)
    return module


park = _load()
TEXTS = jsondata.read(_AKMON / "tools" / "park" / "park.json")

LOCAL_HEADER = "# TASKS — local index"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project root: ``AGENTS.md`` beside the dev layer's integration record."""
    (tmp_path / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (tmp_path / "_aitna").mkdir()
    (tmp_path / "_aitna" / ".akmon.toml").write_text("", encoding="utf-8")
    return tmp_path


def _kit(project: Path, name: str = "C183-park-helper") -> Path:
    return project / "_aitna" / ".ergon" / name


def _index(project: Path) -> Path:
    return project / "_aitna" / ".local" / "TASKS.md"


def _write(project: Path, *extra: str, kit_id: str = "C183", name: str = "park-helper") -> int:
    argv = ["write", kit_id, "--name", name, "--goal", "Build the helper", "--next", "Twin it"]
    return park.main([*argv, *extra, "--root", str(project)])


FULL_FIELDS = park.ParkFields(
    id="C183",
    name="park-helper",
    next_action="Twin it: JS | Python",
    state="parked",
    plan="A59",
    row="C183",
    branch="_aitna/C183-park-helper",
    revisions=("abc123", "def456"),
    owned_paths=("tools/park/park.py", "meta/tests/test_park.py"),
    sessions=(park.SessionRef("claude", "s-1", "laptop"), park.SessionRef("codex", "s-2", "")),
    peers=("sibling session on B8",),
    origin="claude on laptop",
    readiness="ready for a successor",
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


# --------------------------------------------------------------------------------------
# the header and the note
# --------------------------------------------------------------------------------------


def test_header_round_trips_every_field():
    text = park.render_header(FULL_FIELDS)
    assert park.parse_header(text, "PARK.md", TEXTS) == FULL_FIELDS


def test_header_round_trips_with_empty_fields():
    fields = park.ParkFields(id="_T3", name="local-task", next_action="Continue")
    text = park.render_header(fields)
    assert "plan:\n" in text and "revisions:\n" in text
    assert park.parse_header(text, "PARK.md", TEXTS) == fields


def test_header_text_is_flat_and_ordered():
    lines = park.render_header(FULL_FIELDS).split("\n")
    assert lines[0] == lines[-2] == "---"
    keys = [line.split(":")[0] for line in lines[1:-2] if not line.startswith("  - ")]
    assert keys == [
        "state",
        "id",
        "name",
        "plan",
        "row",
        "branch",
        "revisions",
        "owned_paths",
        "next",
        "sessions",
        "peers",
        "origin",
        "readiness",
    ]
    assert "  - claude|s-1|laptop" in lines
    assert "  - codex|s-2|" in lines


def test_note_round_trips_header_and_body():
    text = park.render_note(FULL_FIELDS, FULL_BODY, TEXTS)
    fields, body = park.parse_note(text, "PARK.md", TEXTS)
    assert fields == FULL_FIELDS
    assert body == FULL_BODY


def test_note_without_purpose_has_no_purpose_section():
    text = park.render_note(FULL_FIELDS, park.ParkBody(goal="g"), TEXTS)
    assert "## Purpose" not in text
    assert "## Next action\n\nTwin it: JS | Python" in text


def test_with_state_changes_only_the_state_and_keeps_the_body():
    text = park.render_note(FULL_FIELDS, FULL_BODY, TEXTS) + "\nhand-written line\n"
    resumed = park.with_state(text, "resumed", "PARK.md", TEXTS)
    fields, body = park.parse_note(resumed, "PARK.md", TEXTS)
    assert fields.state == "resumed"
    assert fields == park.dataclasses.replace(FULL_FIELDS, state="resumed")
    assert body == FULL_BODY
    assert resumed.endswith("hand-written line\n")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "c1"}, "id c1 is not a task id"),
        ({"id": "C"}, "id C is not a task id"),
        ({"plan": "plan"}, "plan plan is not a task id"),
        ({"name": "Park Helper"}, "name Park Helper is not kebab-case"),
        ({"name": "park--helper"}, "is not kebab-case"),
        ({"next_action": "two\nlines"}, "next must be a single line"),
        ({"branch": "a\rb"}, "branch must be a single line"),
        ({"origin": " padded "}, "origin must be a single line"),
        ({"next_action": ""}, "next must not be empty"),
        ({"state": "done"}, "state done is not parked or resumed"),
        ({"revisions": ("a\nb",)}, "revision must be a single line"),
        ({"peers": ("",)}, "peer must not be empty"),
        ({"sessions": (park.SessionRef("a|b", "s", "m"),)}, "is not harness|session_id|machine"),
    ],
)
def test_fields_are_refused_at_the_boundary(change, message):
    fields = park.dataclasses.replace(FULL_FIELDS, **change)
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
    body = park.dataclasses.replace(FULL_BODY, **change)
    with pytest.raises(park.ParkError, match=re.escape(message)):
        park.check_body(body, TEXTS)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("no header\n", "no header between two '---' lines"),
        ("---\nstate: parked\n", "no header between two '---' lines"),
        ("---\nstate: parked\nstate: parked\n---\n", "header key state is unknown or repeated"),
        ("---\nbogus: 1\n---\n", "header key bogus is unknown or repeated"),
        ("---\n  - orphan\n---\n", "is a list item with no list key above it"),
        ("---\nid: C1\n  - x\n---\n", "is a list item with no list key above it"),
        ("---\nrevisions: a\n---\n", "header key revisions takes a single value"),
        ("---\nSTATE parked\n---\n", "is neither 'key: value' nor an indented '- item'"),
        ("---\nstate: parked\nid: C1\nname: n\n---\n", "no value for next"),
        ("---\nstate: parked\nid: c1\nname: n\nnext: x\n---\n", "id c1 is not a task id"),
    ],
)
def test_malformed_headers_are_refused(text, message):
    with pytest.raises(park.ParkError, match=re.escape(message)):
        park.parse_header(text, "PARK.md", TEXTS)


# --------------------------------------------------------------------------------------
# write: the kit, the resume prompt, the index
# --------------------------------------------------------------------------------------


def test_write_creates_the_kit_with_both_files(project, capsys):
    assert _write(project, "--plan", "A59", "--decision", "D-X") == 0
    assert capsys.readouterr().out == "_aitna/.ergon/C183-park-helper\n"
    kit = _kit(project)
    fields, body = park.parse_note((kit / "PARK.md").read_text(encoding="utf-8"), "PARK.md", TEXTS)
    assert (fields.id, fields.name, fields.state, fields.plan) == ("C183", "park-helper", "parked", "A59")
    assert body.goal == "Build the helper"
    assert body.decisions == ("D-X",)
    assert (kit / "RESUME.md").is_file()
    assert sorted(path.name for path in kit.iterdir()) == ["PARK.md", "RESUME.md"]


def test_second_write_rewrites_the_note_as_parked_again(project):
    _write(project)
    kit = _kit(project)
    note = kit / "PARK.md"
    note.write_text(park.with_state(note.read_text(encoding="utf-8"), "resumed", "PARK.md", TEXTS), encoding="utf-8")
    assert _write(project) == 0
    assert park.read_note(kit, TEXTS)[0].state == "parked"


def test_write_flags_fill_every_header_field(project):
    code = _write(
        project,
        "--plan",
        "A59",
        "--row",
        "C183",
        "--branch",
        "_aitna/C183-park-helper",
        "--revision",
        "abc",
        "--revision",
        "def",
        "--owned-path",
        "tools/park/park.py",
        "--peer",
        "other",
        "--origin",
        "claude",
        "--readiness",
        "ready",
        "--harness",
        "claude",
        "--session-id",
        "s1",
        "--machine",
        "laptop",
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
    assert fields == park.ParkFields(
        id="C183",
        name="park-helper",
        next_action="Twin it",
        plan="A59",
        row="C183",
        branch="_aitna/C183-park-helper",
        revisions=("abc", "def"),
        owned_paths=("tools/park/park.py",),
        sessions=(park.SessionRef("claude", "s1", "laptop"),),
        peers=("other",),
        origin="claude",
        readiness="ready",
    )
    assert (body.checks, body.unverified, body.answers, body.agents) == (("pytest",), ("twin",), ("go",), ("none",))


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
    for name in ("PARK.md", "RESUME.md"):
        assert not re.search(r"\d{4}-\d{2}-\d{2}", (kit / name).read_text(encoding="utf-8"))


def test_index_is_created_with_the_one_line_header_and_a_parked_row(project):
    _write(project, "--role", "engineer", "--title", "The park helper")
    assert _index(project).read_text(encoding="utf-8") == (
        f"{LOCAL_HEADER}\n\n- C183 · The park helper · parked · engineer · Build the helper · "
        "[park](../.ergon/C183-park-helper/PARK.md)\n"
    )


def test_new_row_defaults_title_to_the_goal_and_role_to_architect(project):
    _write(project)
    assert _index(project).read_text(encoding="utf-8").splitlines()[-1] == (
        "- C183 · Build the helper · parked · architect · Build the helper · [park](../.ergon/C183-park-helper/PARK.md)"
    )


def test_new_row_uses_the_first_line_of_a_multiline_goal(project):
    argv = ["write", "C1", "--name", "n", "--goal", "first\nsecond", "--next", "x", "--root", str(project)]
    assert park.main(argv) == 0
    assert "· first · parked · architect · first ·" in _index(project).read_text(encoding="utf-8")


def test_existing_index_is_kept_and_the_row_appended(project):
    _index(project).parent.mkdir(parents=True)
    existing = f"{LOCAL_HEADER}\n\nprose line\n\n- A71 · plan · active · architect · goal · [plan](x)\n"
    _index(project).write_text(existing, encoding="utf-8")
    _write(project)
    text = _index(project).read_text(encoding="utf-8")
    assert text.startswith(existing)
    assert text.count("\n- C183 ·") == 1


def test_existing_row_is_set_to_parked_and_gains_a_park_link(project):
    _index(project).parent.mkdir(parents=True)
    _index(project).write_text(
        f"{LOCAL_HEADER}\n\n- C183 · own title  ·  active  · engineer · own goal\n"
        "- C184 · other · active · engineer · g\n",
        encoding="utf-8",
    )
    _write(project)
    lines = _index(project).read_text(encoding="utf-8").splitlines()
    assert (
        lines[2] == "- C183 · own title  ·  parked  · engineer · own goal · [park](../.ergon/C183-park-helper/PARK.md)"
    )
    assert lines[3] == "- C184 · other · active · engineer · g"


def test_existing_row_with_a_detail_link_keeps_its_link(project):
    _index(project).parent.mkdir(parents=True)
    _index(project).write_text(
        f"{LOCAL_HEADER}\n\n- C183 · t · deferred · engineer · g · [detail](../x.md)\n", encoding="utf-8"
    )
    _write(project)
    assert (
        _index(project).read_text(encoding="utf-8").splitlines()[2]
        == "- C183 · t · parked · engineer · g · [detail](../x.md)"
    )


def test_row_with_a_tracker_tag_is_found_by_its_id(project):
    _index(project).parent.mkdir(parents=True)
    _index(project).write_text(f"{LOCAL_HEADER}\n\n- C183[#9] · t · active · engineer · g\n", encoding="utf-8")
    _write(project)
    text = _index(project).read_text(encoding="utf-8")
    assert text.count("- C183") == 1 and "· parked ·" in text


def test_row_with_too_few_fields_is_refused_and_nothing_is_written(project):
    _index(project).parent.mkdir(parents=True)
    _index(project).write_text("- C183 · only title\n", encoding="utf-8")
    assert _write(project) == 1
    assert not _kit(project).exists()
    assert _index(project).read_text(encoding="utf-8") == "- C183 · only title\n"


def test_a_separator_in_a_new_rows_cell_is_refused(project, capsys):
    assert _write(project, "--title", "a · b") == 1
    assert "title must not contain '·'" in capsys.readouterr().err
    assert not _kit(project).exists()


def test_the_project_index_is_never_touched(project):
    project_index = project / "_aitna" / "TASKS.md"
    project_index.write_text("- C183 · t · active · engineer · g\n", encoding="utf-8")
    before = project_index.read_bytes()
    _write(project)
    park.main(["unpark", "C183", "--root", str(project)])
    assert project_index.read_bytes() == before
    assert sorted(path.name for path in (project / "_aitna").iterdir() if path.is_file()) == [".akmon.toml", "TASKS.md"]


def test_a_dev_root_pointer_moves_the_kit_and_the_index(tmp_path):
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (tmp_path / ".aitna-root").write_text("tools/ai\n", encoding="utf-8")
    assert _write(tmp_path) == 0
    assert (tmp_path / "tools/ai/.ergon/C183-park-helper/PARK.md").is_file()
    assert (tmp_path / "tools/ai/.local/TASKS.md").is_file()
    assert "`tools/ai/.ergon/C183-park-helper/PARK.md`" in (
        tmp_path / "tools/ai/.ergon/C183-park-helper/RESUME.md"
    ).read_text(encoding="utf-8")


def test_a_failure_while_landing_the_files_leaves_nothing_behind(project, monkeypatch):
    def refuse(self, target):
        raise OSError("disk says no")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk says no"):
        _write(project)
    assert not _kit(project).exists()
    assert not _index(project).exists()
    leftovers = [path for path in project.rglob("*") if path.name.endswith(".tmp")]
    assert leftovers == []


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


def test_write_refuses_a_bad_id_and_a_bad_name_before_any_file(project, capsys):
    assert _write(project, kit_id="c183") == 1
    assert _write(project, name="Bad_Name") == 1
    errors = capsys.readouterr().err.splitlines()
    assert errors[0].startswith("error: id c183 is not a task id")
    assert errors[1].startswith("error: name Bad_Name is not kebab-case")
    assert not (project / "_aitna" / ".ergon").exists()


def test_write_refuses_a_newline_in_a_scalar(project, capsys):
    argv = ["write", "C1", "--name", "n", "--goal", "g", "--next", "a\nb", "--root", str(project)]
    assert park.main(argv) == 1
    assert capsys.readouterr().err == "error: next must be a single line with no surrounding whitespace\n"


def test_local_ids_are_accepted(project):
    assert _write(project, kit_id="_T7", name="scratch") == 0
    assert _kit(project, "_T7-scratch").is_dir()


# --------------------------------------------------------------------------------------
# unpark and digest
# --------------------------------------------------------------------------------------


def test_unpark_resumes_the_note_and_the_row_and_prints_resume_then_digest(project, capsys):
    _write(project, "--decision", "D-X", "--answer", "owner: go", "--plan", "A59")
    capsys.readouterr()
    assert park.main(["unpark", "C183", "--root", str(project)]) == 0
    out = capsys.readouterr().out
    resume = (_kit(project) / "RESUME.md").read_text(encoding="utf-8")
    assert out.startswith(resume.rstrip("\n") + "\n\npark C183-park-helper · resumed\n")
    assert out.endswith("Owner answers:\n- owner: go\n")
    assert park.read_note(_kit(project), TEXTS)[0].state == "resumed"
    assert "· active ·" in _index(project).read_text(encoding="utf-8")


def test_unpark_leaves_a_row_that_is_not_parked_alone(project):
    _write(project)
    _index(project).write_text(
        _index(project).read_text(encoding="utf-8").replace("· parked ·", "· blocked ·"), encoding="utf-8"
    )
    park.main(["unpark", "C183", "--root", str(project)])
    assert "· blocked ·" in _index(project).read_text(encoding="utf-8")


def test_unpark_without_an_index_row_or_file_still_resumes(project):
    _write(project)
    _index(project).unlink()
    assert park.main(["unpark", "C183", "--root", str(project)]) == 0
    assert not _index(project).exists()


def test_unpark_names_the_candidates_when_no_kit_matches(project, capsys):
    _write(project)
    assert park.main(["unpark", "C999", "--root", str(project)]) == 1
    assert capsys.readouterr().err == "error: no kit with id C999 under _aitna/.ergon; kits: C183-park-helper\n"


def test_unpark_with_no_kits_at_all_says_none(project, capsys):
    assert park.main(["unpark", "C1", "--root", str(project)]) == 1
    assert capsys.readouterr().err == "error: no kit with id C1 under _aitna/.ergon; kits: none\n"


def test_unpark_names_the_kits_when_several_carry_the_id(project, capsys):
    for name in ("C5-a", "C5-b", "C50-c"):
        _kit(project, name).mkdir(parents=True)
    assert park.main(["unpark", "C5", "--root", str(project)]) == 1
    assert capsys.readouterr().err == "error: several kits carry id C5 under _aitna/.ergon: C5-a, C5-b\n"


def test_unpark_of_a_kit_that_was_never_parked_is_refused(project, capsys):
    _kit(project, "C5-a").mkdir(parents=True)
    assert park.main(["unpark", "C5", "--root", str(project)]) == 1
    assert capsys.readouterr().err == "error: kit C5-a was never parked: it has no PARK.md\n"


def _kit_with_answers(project: Path, count: int) -> Path:
    body = park.ParkBody(goal="Goal line", answers=tuple(f"answer {number:02d}" for number in range(count)))
    fields = park.ParkFields(id="C9", name="long", next_action="Next")
    return park.write_kit(fields, body, project, park.WriteOptions(), TEXTS)


def test_digest_within_the_cap_is_whole_and_has_no_overflow_line(project):
    kit = _kit_with_answers(project, 2)
    text = park.digest(kit, 3000, project, TEXTS)
    assert text == (
        "park C9-long · parked\nGoal: Goal line\nNext action: Next\nOpen decisions: none\n"
        "Owner answers:\n- answer 00\n- answer 01"
    )


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
    kit = park.write_kit(fields, park.ParkBody(goal="one\ntwo"), project, park.WriteOptions(), TEXTS)
    assert park.digest(kit, 3000, project, TEXTS).split("\n")[:6] == [
        "park C9-long · parked",
        "plan: A59",
        "readiness: ready",
        "Goal: one",
        "  two",
        "Next action: Next",
    ]


def test_digest_command_prints_the_digest_and_refuses_a_negative_cap(project, capsys):
    _write(project)
    capsys.readouterr()
    assert park.main(["digest", "C183", "--cap", "40", "--root", str(project)]) == 0
    assert (
        capsys.readouterr().out
        == "park C183-park-helper · parked\n… 4 more lines in _aitna/.ergon/C183-park-helper/PARK.md\n"
    )
    assert park.main(["digest", "C183", "--cap", "-1", "--root", str(project)]) == 1
    assert capsys.readouterr().err == "error: --cap must be a whole number of at least 0, got -1\n"


def test_digest_command_default_cap_is_3000(project, capsys):
    kit = _kit_with_answers(project, 400)
    capsys.readouterr()
    park.main(["digest", "C9", "--root", str(project)])
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1].startswith("… ") and "more lines in _aitna/.ergon/C9-long/PARK.md" in lines[-1]
    assert sum(len(line) + 1 for line in lines[:-1]) <= 3000
    assert kit.is_dir()


# --------------------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------------------


def test_list_of_an_empty_ergon_says_so(project, capsys):
    assert park.main(["list", "--root", str(project)]) == 0
    assert capsys.readouterr().out == "no kits in _aitna/.ergon\n"
    (project / "_aitna" / ".ergon").mkdir(parents=True)
    park.main(["list", "--root", str(project)])
    assert capsys.readouterr().out == "no kits in _aitna/.ergon\n"


def _populate(project: Path) -> None:
    _write(project, "--plan", "A59", "--decision", "D-X", "--decision", "D-Y", "--branch", "_aitna/C183-park-helper")
    _write(project, "--plan", "A60", kit_id="A5", name="second")
    _kit(project, "C7-never").mkdir()
    _write(project, kit_id="C20", name="third")
    park.main(["unpark", "C20", "--root", str(project)])


def test_list_prints_one_line_per_kit_sorted_by_id(project, capsys):
    _populate(project)
    capsys.readouterr()
    assert park.main(["list", "--root", str(project)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "A5 | second | parked | A60 | Twin it | 0 | - | 0d",
        "C183 | park-helper | parked | A59 | Twin it | 2 | _aitna/C183-park-helper | 0d",
        "C20 | third | resumed | - | Twin it | 0 | - | 0d",
        "C7 | never | never-parked | - | - | 0 | - | -",
    ]


def test_list_filters_by_plan_state_and_status(project, capsys):
    _populate(project)
    capsys.readouterr()

    def listed(*flags: str) -> list[str]:
        park.main(["list", *flags, "--root", str(project)])
        return [line.split(" | ")[0] for line in capsys.readouterr().out.splitlines()]

    assert listed("--plan", "A59") == ["C183"]
    assert listed("--state", "parked") == ["A5", "C183"]
    assert listed("--state", "never-parked") == ["C7"]
    assert listed("--state", "resumed") == ["C20"]
    assert listed("--status", "parked") == ["A5", "C183"]
    assert listed("--status", "active") == ["C20"]
    assert listed("--status", "-") == ["C7"]
    assert listed("--plan", "A59", "--state", "resumed") == ["no kit matches the filters"]


def test_list_truncates_the_next_action_at_sixty_characters(project, capsys):
    long_next = "x" * 100
    park.main(["write", "C1", "--name", "n", "--goal", "g", "--next", long_next, "--root", str(project)])
    capsys.readouterr()
    park.main(["list", "--root", str(project)])
    next_cell = capsys.readouterr().out.split(" | ")[4]
    assert next_cell == "x" * 59 + "…"
    exact = "y" * 60
    park.main(["write", "C2", "--name", "n", "--goal", "g", "--next", exact, "--root", str(project)])
    capsys.readouterr()
    park.main(["list", "--root", str(project)])
    assert capsys.readouterr().out.splitlines()[1].split(" | ")[4] == exact


def test_list_age_is_whole_days_from_the_note_mtime(project):
    _write(project)
    note = _kit(project) / "PARK.md"
    now = time.time()
    os.utime(note, (now - 3 * 86400 - 100, now - 3 * 86400 - 100))
    [item] = park.list_kits(project, park.ListQuery(), now, TEXTS)
    assert item.age_days == 3
    assert park.format_summary(item, TEXTS).endswith("| 3d")
    os.utime(note, (now + 500, now + 500))  # a clock behind the file never gives a negative age
    assert park.list_kits(project, park.ListQuery(), now, TEXTS)[0].age_days == 0


def test_list_reads_and_writes_nothing(project):
    _populate(project)
    snapshot = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    before = {p: p.stat().st_mtime_ns for p in snapshot}
    park.main(["list", "--root", str(project)])
    park.main(["list", "--state", "parked", "--root", str(project)])
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == snapshot
    assert {p: p.stat().st_mtime_ns for p in snapshot} == before


def test_list_ignores_folders_that_are_not_kits(project, capsys):
    _write(project)
    (_kit(project).parent / "notes").mkdir()
    (_kit(project).parent / "stray.txt").write_text("x", encoding="utf-8")
    capsys.readouterr()
    park.main(["list", "--root", str(project)])
    assert capsys.readouterr().out.count("\n") == 1


def test_list_names_a_kit_whose_note_does_not_parse(project, capsys):
    _write(project)
    (_kit(project) / "PARK.md").write_text("broken\n", encoding="utf-8")
    assert park.main(["list", "--root", str(project)]) == 1
    assert (
        capsys.readouterr().err
        == "error: C183-park-helper/PARK.md: no header between two '---' lines at the top of the note\n"
    )


# --------------------------------------------------------------------------------------
# project root
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv", [["list"], ["write", "C1", "--name", "n", "--goal", "g", "--next", "x"], ["unpark", "C1"]]
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
