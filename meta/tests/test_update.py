"""Tests for ``akmon update`` (``src/akmon/_update.py``, C92 under A23).

Most tests stand in for the three things ``update`` hands work to — ``init``, the processes it
starts, and the ``sync``/``verify`` dispatch — and assert exactly what it asked of them, per
mount mode. One end-to-end test moves a real submodule mount, cloned from this repository over
``file://``, and checks the owner-facing contract that matters most: the pin moves, the index
does not, and nothing is committed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SRC = _AKMON / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from akmon import _init, _tree, _update, cli  # noqa: E402

REPO = _init.akmon_repo()
PIN_LINE = "akmon @ git+https://github.com/akumidv/ai_akmon@v0.3.0"

# --------------------------------------------------------------------------------------
# src/akmon/update.json — the shared update text and tables (C102)
# --------------------------------------------------------------------------------------

_UPDATE_DATA = json.loads((_AKMON / "src" / "akmon" / "update.json").read_text(encoding="utf-8"))


def test_update_data_pins_its_structure():
    """The data file is the single owner of the update text: pin the key set and a few
    characteristic exact values so a transcription drift is caught here, not in the corpus."""
    assert set(_UPDATE_DATA) == {
        "plan_notes",
        "banner",
        "missing_record",
        "init_failed",
        "checks",
        "checks_running",
        "checks_failed",
        "subtree_refusal",
        "subtree_pull_command",
        "subtree_realign_command",
        "package_uv_missing",
        "package_launcher_missing",
        "vendored_not_fetchable",
        "vendored_uvx_missing",
        "closing_left_to_you",
        "closing_step",
        "closing_changelog",
        "closing_review",
        "closing_bump",
        "closing_codex",
    }
    assert set(_UPDATE_DATA["plan_notes"]) == {
        "not_a_release",
        "record_no_version",
        "forward",
        "already",
        "rollback",
        "past_newest",
    }
    assert _UPDATE_DATA["plan_notes"]["forward"] == "{{current}} → {{target}}"
    assert _UPDATE_DATA["banner"] == "{{root}} · mount mode {{mode}} · {{note}}"
    assert _UPDATE_DATA["checks"] == [["sync", "--check"], ["verify", "--strict"]]
    assert _UPDATE_DATA["checks_running"] == "running {{script}} {{flag}}"
    assert _UPDATE_DATA["closing_left_to_you"] == "left to you:"
    assert _UPDATE_DATA["closing_step"] == "  {{index}}. {{step}}"
    assert _UPDATE_DATA["subtree_realign_command"] == "    akmon init --ref {{target}}"
    assert _UPDATE_DATA["init_failed"] == "akmon update: init failed ({{code}}); see its output above"
    assert _UPDATE_DATA["package_launcher_missing"].startswith("{{launcher}} does not exist")
    assert "{{recorded}}" in _UPDATE_DATA["vendored_not_fetchable"]


def test_update_loader_asks_for_exactly_the_update_json(monkeypatch):
    """The loader reads ``update.json`` beside ``_update.py`` — the path the wheel and the
    corpus snapshot both place the file at."""
    from common import jsondata

    seen: list[Path] = []
    real_read = jsondata.read

    def spy(path):
        seen.append(path)
        return real_read(path)

    monkeypatch.setattr(jsondata, "read", spy)
    assert _update._plan("0.1.0", "0.2.0", explicit=False).note == "0.1.0 → 0.2.0"
    assert seen, "the loader never asked for the data file"
    for path in seen:
        assert path == Path(_update.__file__).parent / "update.json"


def test_update_data_file_error_propagates_uncaught(monkeypatch):
    """A missing or broken ``update.json`` is a loud failure, not a swallowed one."""
    from common import jsondata

    def broken_read(path):
        raise jsondata.DataFileError(f"akmon data file missing: {path}")

    monkeypatch.setattr(jsondata, "read", broken_read)
    with pytest.raises(jsondata.DataFileError):
        _update._plan("0.1.0", "0.2.0", explicit=False)
    with pytest.raises(jsondata.DataFileError):
        _update._closing(
            Path("/tmp"), "_aitna", "package", _update._Plan(target="0.2.0", current="0.1.0", move=True, note="x"), None
        )


@pytest.fixture(autouse=True)
def isolated_aitna_root(monkeypatch):
    """``update`` sets ``AITNA_ROOT`` for the run, as ``init`` does; keep tests apart."""
    monkeypatch.setenv("AITNA_ROOT", "_aitna")


def _versions():
    return cli._embedded_common_module(_tree.embedded_tree_root(), "versions")


def _attached(root: Path, mode: str, version: str | None = "v0.3.0", *, last_realign: str | None = None) -> Path:
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    record = root / "_aitna" / ".akmon.toml"
    record.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'mount = "{mode}"']
    lines += [f'akmon_version = "{version}"'] if version else []
    lines += [f'last_realign = "{last_realign}"'] if last_realign else []
    record.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


class _Calls:
    """What ``update`` asked of ``init``, of the processes it starts, and of the sync/verify dispatch."""

    def __init__(self, monkeypatch, *, init_code=0, run_code=0, dispatch_code=0):
        self.init: list[list[str]] = []
        self.run: list[list[str]] = []
        self.dispatch: list[list[str]] = []

        def fake_init(argv):
            self.init.append(list(argv))
            return init_code

        def fake_run(command, cwd, *, timeout=None):
            self.run.append(list(command))
            return run_code

        def fake_dispatch(script, argv, *, cwd=None):
            self.dispatch.append([script, *argv])
            return dispatch_code

        monkeypatch.setattr(_init, "main", fake_init)
        monkeypatch.setattr(_update, "_run", fake_run)
        monkeypatch.setattr(cli, "_dispatch", fake_dispatch)


def _checks(root: Path) -> list[list[str]]:
    return [["sync", "--check", "--project-root", str(root)], ["verify", "--strict", "--project-root", str(root)]]


def _newest(monkeypatch, tag: str) -> None:
    monkeypatch.setattr(_init, "_package_default_ref", lambda repo, root: tag)


# --------------------------------------------------------------------------------------
# which way the pin moves
# --------------------------------------------------------------------------------------


def test_order_key_places_a_development_version_before_its_release_and_a_describe_distance_after():
    key = _versions().order_key
    assert key("0.4.0.dev0") < key("v0.4.0") < key("v0.4.0-3-gabc1234") < key("v0.4.1")
    assert key("0.4.0rc1") < key("0.4.0") < key("0.4.0.post1")
    assert key("v0.10.0") > key("v0.9.9")
    assert key("main") is None


@pytest.mark.parametrize(
    ("current", "target", "explicit", "move", "note"),
    [
        ("v0.3.0", "v0.4.0", False, True, "v0.3.0 → v0.4.0"),
        ("v0.4.0", "v0.4.0", False, False, "already at v0.4.0"),
        ("v0.4.0-2-gabc1234", "v0.4.0", False, False, "past the newest release"),
        ("0.4.1.dev0", "v0.4.0", False, False, "past the newest release"),
        ("v0.4.0", "v0.3.0", True, True, "rolling back"),
        (None, "v0.4.0", False, True, "no comparable version"),
        ("v0.3.0", "main", True, True, "not a release version"),
    ],
)
def test_plan_never_moves_the_pin_back_unless_ref_asks(current, target, explicit, move, note):
    plan = _update._plan(current, target, explicit=explicit)
    assert plan.move is move
    assert note in plan.note


def test_the_newest_release_ignores_pre_releases(tmp_path, monkeypatch):
    listing = "".join(
        f"{index:040d}\trefs/tags/{tag}\n"
        for index, tag in enumerate(["v0.3.0", "v0.10.0", "v1.0.0rc1", "v0.11.0-beta", "v0.9.0"])
    )
    monkeypatch.setattr(_init, "_run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, listing, ""))
    assert _init._package_default_ref(REPO, tmp_path) == "v0.10.0"


def test_an_unreachable_repository_names_the_prerequisite_and_the_way_around(tmp_path, monkeypatch, capsys):
    _attached(tmp_path, "submodule")
    monkeypatch.setattr(_init, "_run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 128, "", ""))
    assert _update.main(["--project-root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "network access" in err
    assert "--ref" in err


def test_a_project_that_is_not_attached_is_refused(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    assert _update.main(["--project-root", str(tmp_path), "--ref", "v0.4.0"]) == 2
    assert "akmon init" in capsys.readouterr().err


# --------------------------------------------------------------------------------------
# submodule
# --------------------------------------------------------------------------------------


def test_submodule_fetches_the_tags_then_init_moves_the_pin(tmp_path, monkeypatch):
    root = _attached(tmp_path, "submodule")
    calls = _Calls(monkeypatch)
    _newest(monkeypatch, "v0.4.0")
    assert _update.main(["--project-root", str(root)]) == 0
    assert calls.run == [["git", "fetch", "--quiet", "--tags", REPO]]
    assert calls.init == [["--project-root", str(root), "--yes", "--ref", "v0.4.0"]]
    assert calls.dispatch == _checks(root)


def test_a_project_past_the_newest_release_is_realigned_where_it_is(tmp_path, monkeypatch, capsys):
    root = _attached(tmp_path, "submodule", "v0.4.0-3-gabc1234")
    calls = _Calls(monkeypatch)
    _newest(monkeypatch, "v0.4.0")
    assert _update.main(["--project-root", str(root)]) == 0
    assert calls.run == []
    assert calls.init == [["--project-root", str(root), "--yes"]]
    assert "the pin stays" in capsys.readouterr().out


def test_an_older_ref_rolls_back_and_says_so(tmp_path, monkeypatch, capsys):
    root = _attached(tmp_path, "submodule", "v0.4.0")
    calls = _Calls(monkeypatch)
    assert _update.main(["--project-root", str(root), "--ref", "v0.3.0"]) == 0
    assert calls.init == [["--project-root", str(root), "--yes", "--ref", "v0.3.0"]]
    assert "rolling back v0.4.0 → v0.3.0" in capsys.readouterr().out


def test_a_failing_init_stops_before_the_checks(tmp_path, monkeypatch):
    root = _attached(tmp_path, "submodule")
    calls = _Calls(monkeypatch, init_code=3)
    assert _update.main(["--project-root", str(root), "--ref", "v0.4.0"]) == 3
    assert calls.dispatch == []


def test_a_failing_check_fails_the_update(tmp_path, monkeypatch):
    root = _attached(tmp_path, "submodule")
    _Calls(monkeypatch, dispatch_code=1)
    assert _update.main(["--project-root", str(root), "--ref", "v0.4.0"]) == 1


def test_the_closing_steps_name_the_changelog_window_from_the_last_realign(tmp_path, monkeypatch, capsys):
    root = _attached(tmp_path, "submodule", "v0.3.0", last_realign="v0.2.1")
    _Calls(monkeypatch)
    assert _update.main(["--project-root", str(root), "--ref", "v0.4.0"]) == 0
    out = capsys.readouterr().out
    assert "read CHANGELOG.md after v0.2.1 up to v0.4.0" in out
    assert "the commit is the owner's (D5)" in out


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


def test_submodule_update_moves_the_mount_leaves_the_index_and_commits_nothing(tmp_path, monkeypatch):
    """End to end over ``file://``: attach at v0.3.0, update to this repository's HEAD."""
    for key, value in (
        ("GIT_CONFIG_COUNT", "1"),
        ("GIT_CONFIG_KEY_0", "protocol.file.allow"),
        ("GIT_CONFIG_VALUE_0", "always"),
    ):
        monkeypatch.setenv(key, value)
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], consumer)
    repo = f"file://{_AKMON}"
    attach = ["--mode", "submodule", "--project-root", str(consumer), "--repo", repo, "--ref", "v0.3.0", "--yes"]
    assert _init.main(attach) == 0
    mount = consumer / "_aitna" / "akmon"
    staged = _git(["ls-files", "--stage", "--", "_aitna/akmon"], consumer).split()[1]
    head = _git(["rev-parse", "HEAD"], _AKMON)

    assert _update.main(["--project-root", str(consumer), "--repo", repo, "--ref", head]) == 0

    assert _git(["rev-parse", "HEAD"], mount) == head
    assert _git(["ls-files", "--stage", "--", "_aitna/akmon"], consumer).split()[1] == staged  # D5: left unstaged
    no_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(consumer), capture_output=True, check=False)
    assert no_commit.returncode != 0


# --------------------------------------------------------------------------------------
# package
# --------------------------------------------------------------------------------------


def _package_project(root: Path, manifest: str) -> Path:
    _attached(root, "package", "0.3.0")
    (root / "pyproject.toml").write_text(manifest, encoding="utf-8")
    launcher = root / ".venv" / "bin" / "akmon"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    return launcher


def test_package_moves_the_pin_in_its_group_with_uv_then_the_new_cli_runs_init(tmp_path, monkeypatch):
    launcher = _package_project(tmp_path, f'[dependency-groups]\ntools = ["{PIN_LINE}"]\n')
    calls = _Calls(monkeypatch)
    monkeypatch.setattr(_update.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert _update.main(["--project-root", str(tmp_path), "--ref", "v0.4.0"]) == 0
    root = str(tmp_path)
    assert calls.run == [
        ["uv", "add", "--raw", "--group", "tools", "akmon @ git+https://github.com/akumidv/ai_akmon@v0.4.0"],
        [str(launcher), "init", "--project-root", root, "--yes"],
        [str(launcher), "sync", "--check", "--project-root", root],
        [str(launcher), "verify", "--strict", "--project-root", root],
    ]
    assert calls.init == []  # never this process's init: it may be the version uv just replaced
    assert calls.dispatch == []


def test_package_moves_a_pin_kept_in_uv_sources_there(tmp_path, monkeypatch):
    # uv's own spelling: a bare `akmon` in the group, the URL in [tool.uv.sources]. With `--raw` that
    # stale entry still won resolution in the live update of the attached consumer (uv 0.11.21).
    _package_project(
        tmp_path,
        '[dependency-groups]\ndev = ["akmon"]\n\n[tool.uv.sources]\n'
        'akmon = { git = "https://github.com/akumidv/ai_akmon", rev = "v0.3.0" }\n',
    )
    calls = _Calls(monkeypatch)
    monkeypatch.setattr(_update.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert _update.main(["--project-root", str(tmp_path), "--ref", "v0.4.0"]) == 0
    assert calls.run[0] == ["uv", "add", "--group", "dev", "akmon @ git+https://github.com/akumidv/ai_akmon@v0.4.0"]


def test_package_without_uv_prints_the_command_and_moves_nothing(tmp_path, monkeypatch, capsys):
    _package_project(tmp_path, f'[dependency-groups]\ndev = ["{PIN_LINE}"]\n')
    calls = _Calls(monkeypatch)
    monkeypatch.setattr(_update.shutil, "which", lambda name: None)
    assert _update.main(["--project-root", str(tmp_path), "--ref", "v0.4.0"]) == 2
    assert "uv add --raw --group dev" in capsys.readouterr().err
    assert calls.run == []


def test_package_refuses_a_pin_uv_add_cannot_move_in_place(tmp_path, monkeypatch, capsys):
    _package_project(tmp_path, f'[tool.uv]\ndev-dependencies = ["{PIN_LINE}"]\n')
    calls = _Calls(monkeypatch)
    monkeypatch.setattr(_update.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert _update.main(["--project-root", str(tmp_path), "--ref", "v0.4.0"]) == 2
    assert "[dependency-groups]" in capsys.readouterr().err
    assert calls.run == []


# --------------------------------------------------------------------------------------
# vendored and subtree
# --------------------------------------------------------------------------------------


def test_vendored_runs_init_from_the_target_release_through_uvx(tmp_path, monkeypatch):
    root = _attached(tmp_path, "vendored")
    calls = _Calls(monkeypatch)
    monkeypatch.setattr(_update.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert _update.main(["--project-root", str(root), "--ref", "v0.4.0"]) == 0
    assert calls.run == [["uvx", "--from", f"git+{REPO}@v0.4.0", "akmon", "init", "--project-root", str(root), "--yes"]]
    assert calls.init == []
    assert calls.dispatch == _checks(root)


@pytest.mark.parametrize(("cli_version", "in_process"), [("0.4.0", True), ("0.5.0.dev0", False)])
def test_vendored_realigns_with_this_cli_only_when_it_is_the_pinned_release(
    tmp_path, monkeypatch, cli_version, in_process
):
    """Realigning with any other CLI would re-copy *its* tree over the pin without a word."""
    root = _attached(tmp_path, "vendored", "v0.4.0")
    calls = _Calls(monkeypatch)
    _newest(monkeypatch, "v0.4.0")
    monkeypatch.setattr(_update, "__version__", cli_version)
    monkeypatch.setattr(_update.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert _update.main(["--project-root", str(root)]) == 0
    if in_process:
        assert calls.init == [["--project-root", str(root), "--yes"]]
        assert calls.run == []
    else:
        assert calls.init == []
        assert calls.run == [
            ["uvx", "--from", f"git+{REPO}@v0.4.0", "akmon", "init", "--project-root", str(root), "--yes"]
        ]


def test_vendored_without_uvx_prints_the_command(tmp_path, monkeypatch, capsys):
    root = _attached(tmp_path, "vendored")
    calls = _Calls(monkeypatch)
    monkeypatch.setattr(_update.shutil, "which", lambda name: None)
    assert _update.main(["--project-root", str(root), "--ref", "v0.4.0"]) == 2
    assert f"uvx --from git+{REPO}@v0.4.0 akmon init" in capsys.readouterr().err
    assert calls.run == []


def test_subtree_prints_the_pull_it_must_not_run(tmp_path, monkeypatch, capsys):
    root = _attached(tmp_path, "subtree")
    calls = _Calls(monkeypatch)
    assert _update.main(["--project-root", str(root), "--ref", "v0.4.0"]) == 2
    err = capsys.readouterr().err
    assert f"git subtree pull --prefix _aitna/akmon {REPO} v0.4.0 --squash" in err
    assert "akmon init --ref v0.4.0" in err
    assert calls.run == []
    assert calls.init == []


def test_subtree_already_at_the_target_realigns_at_the_recorded_ref(tmp_path, monkeypatch):
    root = _attached(tmp_path, "subtree", "v0.4.0")
    calls = _Calls(monkeypatch)
    assert _update.main(["--project-root", str(root), "--ref", "v0.4.0"]) == 0
    assert calls.init == [["--project-root", str(root), "--yes", "--ref", "v0.4.0"]]


# --------------------------------------------------------------------------------------
# the CLI verb
# --------------------------------------------------------------------------------------


def test_the_cli_dispatches_update_with_its_flags(monkeypatch):
    seen = []
    monkeypatch.setattr(_update, "main", lambda argv: seen.append(list(argv)) or 0)
    assert cli.main(["update", "--ref", "v0.4.0"]) == 0
    assert seen == [["--ref", "v0.4.0"]]
