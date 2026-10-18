"""Contract tests for the fuzz seed recorder (C121, ``meta/conformance/fuzz_record.py``).

``tee`` must never change the hook it wraps — the same stdout, stderr and exit code, recording or
not — and ``scrub`` must leave no private path, id or text in a seed while keeping the payload's
shape, one seed per shape. Everything runs on temporary directories; no real capture is read.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SCRIPT = _AKMON / "meta" / "conformance" / "fuzz_record.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


record = _load("conformance_fuzz_record", _SCRIPT)

# A hook stand-in: echoes its stdin to stdout, writes one line to stderr, exits 3.
_HOOK = [
    sys.executable,
    "-c",
    "import sys; data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data); "
    "sys.stderr.write('hook says\\n'); raise SystemExit(3)",
]


def _tee(out: Path, stdin: bytes, *extra: str) -> subprocess.CompletedProcess:
    command = [sys.executable, str(_SCRIPT), "tee", "--out", str(out), *extra, "--", *_HOOK]
    return subprocess.run(command, input=stdin, capture_output=True, check=False)


# --- tee ---------------------------------------------------------------------------------


def test_tee_records_the_stdin_bytes_and_passes_the_hook_through(tmp_path):
    raw = tmp_path / "raw"
    stdin = b'{"hook_event_name": "PreToolUse", "x": "\xc3\xa9"}'
    first = _tee(raw, stdin, "--script", "delegation-nudge")
    assert (first.returncode, first.stdout, first.stderr) == (3, stdin, b"hook says\n")
    assert (raw / "delegation-nudge--1.json").read_bytes() == stdin
    second = _tee(raw, b"not json", "--script", "delegation-nudge")
    assert (second.returncode, second.stdout) == (3, b"not json")
    assert (raw / "delegation-nudge--2.json").read_bytes() == b"not json"


def test_a_recording_failure_leaves_the_hook_unchanged(tmp_path):
    blocked = tmp_path / "a-file"
    blocked.write_text("in the way", encoding="utf-8")
    result = _tee(blocked / "raw", b"{}", "--script", "delegation-log")
    assert (result.returncode, result.stdout, result.stderr) == (3, b"{}", b"hook says\n")
    assert blocked.read_text(encoding="utf-8") == "in the way"


def test_a_capture_directory_inside_the_repository_records_nothing(tmp_path):
    repo = tmp_path / "repo"
    assert record.record(b"{}", repo / "captures", "gate-audit", [repo]) is None
    assert not (repo / "captures").exists()
    assert (
        record.record(b"{}", tmp_path / "outside", "gate-audit", [repo]) == tmp_path / "outside" / "gate-audit--1.json"
    )


@pytest.mark.parametrize(
    ("command", "name"),
    [
        (["python3", "/x/hooks/delegation-nudge.py"], "delegation-nudge"),
        (["node", "node_modules/akmon/js/hooks/gate-audit.mjs"], "gate-audit"),
        ([".venv/bin/akmon", "hook", "role-on-code"], "role-on-code"),
        (["true"], "true"),
    ],
)
def test_the_script_name_comes_from_the_hook_command(command, name):
    assert record.script_name(command) == name


# --- scrub -------------------------------------------------------------------------------


def _places(tmp_path: Path):
    return record.Places(
        root=str(tmp_path / "home" / "dev" / "proj"), tmps=("/tmp",), home=str(tmp_path / "home" / "dev")
    )


def _capture(raw: Path, name: str, payload: object) -> Path:
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_scrub_neutralizes_paths_ids_and_text_and_keeps_the_shape(tmp_path):
    places = _places(tmp_path)
    root, home = places.root, places.home
    payload = {
        "session_id": "0f3c-real-session",
        "transcript_path": f"{home}/.claude/projects/x/0f3c.jsonl",
        "cwd": root,
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_use_id": "toolu_real",
        "tool_input": {
            "file_path": f"{root}/src/a.py",
            "old_string": "secret text",
            "new_string": "other text",
            "edits": [{"old_string": "a", "new_string": "b", "replace_all": False}],
        },
        "tool_response": {"filePath": f"{root}/src/a.py", "structuredPatch": [{"lines": ["+x"], "oldLines": 3}]},
        "prompt": "what the owner typed",
        "permission_mode": "default",
        "scratch": "/tmp/akmon-x/marker",
    }
    script, scrubbed = record.scrub_capture(_capture(tmp_path / "raw", "delegation-nudge--7.json", payload), places)
    assert script == "delegation-nudge"
    assert scrubbed == {
        "session_id": "session-recorded",
        "transcript_path": record.NEUTRAL_HOME_PATH,
        "cwd": "{{root}}",
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_use_id": "tool-use-recorded",
        "tool_input": {
            "file_path": "{{root}}/src/a.py",
            "old_string": "scrubbed",
            "new_string": "scrubbed",
            "edits": [{"old_string": "scrubbed", "new_string": "scrubbed", "replace_all": False}],
        },
        "tool_response": {"filePath": "scrubbed", "structuredPatch": [{"lines": ["scrubbed"], "oldLines": 3}]},
        "prompt": "scrubbed",
        "permission_mode": "default",
        "scratch": "{{tmp}}/akmon-x/marker",
    }
    assert record.shape(scrubbed) == record.shape(payload)


def test_scrub_keeps_a_bash_command_with_its_paths_rewritten_and_routing_fields(tmp_path):
    places = _places(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Task",
        "tool_input": {"subagent_type": "k_mechanic", "model": "haiku", "command": f"ls {places.root}/docs /usr/bin"},
    }
    _script, scrubbed = record.scrub_capture(_capture(tmp_path / "raw", "delegation-log--1.json", payload), places)
    assert scrubbed["tool_input"] == {
        "subagent_type": "k_mechanic",
        "model": "haiku",
        "command": "ls {{root}}/docs /usr/bin",
    }


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"[1, 2]", "not one JSON object"),
        (b"{broken", "not a JSON document"),
        (b"\xff{}", "not a JSON document"),
    ],
)
def test_scrub_skips_a_capture_that_is_not_one_object(tmp_path, body, reason):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "gate-audit--1.json").write_bytes(body)
    with pytest.raises(record.UnscrubbableError, match=reason):
        record.scrub_capture(raw / "gate-audit--1.json", _places(tmp_path))


def test_scrub_skips_a_home_path_outside_the_project_inside_a_string(tmp_path):
    places = _places(tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": f"cat {places.home}/other-project/notes.md"}}
    plan = record.plan_scrub(
        _capture(tmp_path / "raw", "git-commit-guard--1.json", payload).parent, places, tmp_path / "s"
    )
    assert plan.seeds == {}
    (line,) = plan.lines
    assert line.startswith("skip git-commit-guard--1.json: a home path outside the project inside a string: 'cat ")


def test_a_sibling_directory_sharing_the_root_prefix_is_not_the_project(tmp_path):
    places = _places(tmp_path)
    assert record.scrub_string(f"{places.root}-old/a", places) == record.NEUTRAL_HOME_PATH
    assert record.scrub_string(places.root, places) == "{{root}}"


def test_one_seed_per_shape_a_dry_run_writes_nothing_and_apply_writes_loadable_seeds(tmp_path):
    places = _places(tmp_path)
    raw = tmp_path / "raw"
    read = {"hook_event_name": "PreToolUse", "tool_name": "Read", "session_id": "a", "tool_input": {"file_path": "x"}}
    _capture(raw, "delegation-nudge--1.json", read)
    _capture(raw, "delegation-nudge--2.json", {**read, "session_id": "b", "tool_input": {"file_path": "y"}})
    _capture(raw, "delegation-nudge--3.json", {**read, "tool_input": {"file_path": "y", "limit": 5}})
    _capture(raw, "role-on-code--1.json", read)
    seeds_dir = tmp_path / "seeds"
    plan = record.plan_scrub(raw, places, seeds_dir)
    assert len(plan.seeds) == 3  # the second capture has the first one's shape; another script is another seed
    assert [line.split(" ")[0] for line in plan.lines] == ["seed", "same", "seed", "seed"]
    assert not seeds_dir.exists()
    assert all(name.startswith(("delegation-nudge--pretooluse-read-", "role-on-code--")) for name in plan.seeds)
    written = record.write_seeds(plan, seeds_dir)
    assert sorted(p.name for p in written) == sorted(plan.seeds)
    again = record.plan_scrub(raw, places, seeds_dir)
    assert again.seeds == {}  # every shape is already a seed

    fuzz = sys.modules.get("conformance_fuzz") or _load_fuzz()
    seeds = [s for s in fuzz.load_seeds(seeds_dir=seeds_dir) if s.name.startswith("seeds/")]
    assert {s.script for s in seeds} == {"delegation-nudge", "role-on-code"}
    assert len(seeds) == 3


def _load_fuzz():
    conformance = _AKMON / "meta" / "conformance"
    foreign = sys.modules.get("coverage")
    if foreign is not None and Path(getattr(foreign, "__file__", "") or "").parent != conformance:
        del sys.modules["coverage"]
    else:
        foreign = None
    try:
        return _load("conformance_fuzz", conformance / "fuzz.py")
    finally:
        if foreign is not None:
            sys.modules["coverage"] = foreign


def test_the_scrub_cli_is_a_dry_run_unless_applied(tmp_path, capsys):
    raw = tmp_path / "raw"
    _capture(raw, "gate-audit--1.json", {"hook_event_name": "Stop", "cwd": str(tmp_path / "p")})
    seeds_dir = tmp_path / "seeds"
    argv = ["scrub", "--raw", str(raw), "--project-root", str(tmp_path / "p"), "--seeds-dir", str(seeds_dir)]
    assert record.main(argv) == 0
    assert "dry run, 1 seed(s) would be written" in capsys.readouterr().out
    assert not seeds_dir.exists()
    assert record.main([*argv, "--apply"]) == 0
    (seed,) = seeds_dir.iterdir()
    assert json.loads(seed.read_text(encoding="utf-8")) == {"hook_event_name": "Stop", "cwd": "{{root}}"}
