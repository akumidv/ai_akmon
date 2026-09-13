"""Unit tests for mount mode ``package`` (ADR 0009 §4, C37 slice B; narrowed by C77):
mount-decoupled tree resolution, the guardrail-and-profile ``.akmon/`` materialization, launcher
resolution and hook-entry recognition across every spelling, and the ``.akmon.toml`` version
stamp — all in ``bin/sync.py``.

These build throwaway project trees under ``tmp_path``; nothing touches the real repo. A
package-mode fixture has no mounted tree at all, so ``sync``'s own "embedded tree" fallback
(``_TREE_ROOT``, this checkout's own akmon root) supplies real hook/guardrail content to
materialize from — the same dev-bench property the CLI's tests rely on.

Run from the akmon root::

    python3 -m pytest tests
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest
import sync

from common import materialization


def test_python_floor_declarations_stay_joined():
    root = sync._TREE_ROOT
    with (root / "pyproject.toml").open("rb") as handle:
        manifest = tomllib.load(handle)

    assert manifest["project"]["requires-python"] == ">=3.11"
    assert manifest["tool"]["ruff"]["target-version"] == "py311"
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python-version: ["3.11", "3.13"]' in workflow
    lock = (root / "uv.lock").read_text(encoding="utf-8")
    assert lock.startswith('version = 1\nrevision = 3\nrequires-python = ">=3.11"\n')


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _make_mounted_root(tmp_path: Path) -> Path:
    """A minimal mounted-mode project (no .akmon.toml): AGENTS.md + an empty mount dir."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "_aitna" / "akmon").mkdir(parents=True)
    return tmp_path


# The AGENTS.md akmon block both *makes* the guardrail import and *documents* it, quoting the
# language-profile form as an example. Read literally the two are indistinguishable, so the
# fixture carries both — the scan must take the first and leave the second.
_AGENTS_MD = """# AGENTS

## Dev layer — akmon

- **Guardrails and profiles (always-on):** import this project's language profile on its own
  line (e.g. `@_aitna/.akmon/profiles/python.md`) per the ARCHETYPES map.

@_aitna/.akmon/guardrails/_common.md
@_aitna/.akmon/profiles/python.md
"""


def _make_package_root(tmp_path: Path, *, extra_toml: str = "", agents_md: str = _AGENTS_MD) -> Path:
    """A minimal package-mode project: AGENTS.md + _aitna/.akmon.toml, no mounted tree.

    The project venv is part of the minimum, not decoration: a real package-mode consumer has
    ``.venv/bin/akmon`` by construction (the dev-group pin puts the console script there when
    the environment is installed), and since C77 the generated wiring names it.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    (tmp_path / "_aitna").mkdir(parents=True)
    (tmp_path / "_aitna" / ".akmon.toml").write_text(f'mount = "package"\n{extra_toml}', encoding="utf-8")
    launcher = tmp_path / ".venv" / "bin" / "akmon"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    return tmp_path


# --------------------------------------------------------------------------------------
# read_mount_mode / is_package_mode
# --------------------------------------------------------------------------------------


def test_is_package_mode_true_with_recorded_mount(tmp_path):
    root = _make_package_root(tmp_path)
    assert sync.is_package_mode(root) is True
    assert sync.read_mount_mode(root) == "package"


def test_is_package_mode_false_by_default(tmp_path):
    root = _make_mounted_root(tmp_path)
    assert sync.is_package_mode(root) is False
    assert sync.read_mount_mode(root) == "submodule"


def test_is_package_mode_false_when_toml_absent_and_no_mount(tmp_path):
    # backward compatibility: no record at all must not be misread as package mode.
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    assert sync.is_package_mode(tmp_path) is False


# --------------------------------------------------------------------------------------
# standard_tree_root — mount-decoupled resolution
# --------------------------------------------------------------------------------------


def test_standard_tree_root_is_the_mount_when_mounted(tmp_path):
    root = _make_mounted_root(tmp_path)
    assert sync.standard_tree_root(root) == sync.akmon_root(root)


def test_standard_tree_root_is_own_tree_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    assert sync.standard_tree_root(root) == sync._TREE_ROOT


def test_standard_tree_root_ignores_stale_mount_dir_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    (root / "_aitna" / "akmon").mkdir(parents=True)  # stale leftover from a prior mode
    assert sync.standard_tree_root(root) == sync._TREE_ROOT


# --------------------------------------------------------------------------------------
# materialization
# --------------------------------------------------------------------------------------


def test_materialized_files_empty_outside_package_mode(tmp_path):
    root = _make_mounted_root(tmp_path)
    assert sync._materialized_files(root) == ([], [])


def test_materialization_ships_only_the_guardrails_agents_md_imports(tmp_path):
    """The one exception to "execute from the package", and its exact width.

    The ``@``-import sits in a committed ``AGENTS.md``, and the only path from there into the
    package carries the venv's Python version — the string C77 removed from the wiring, failing
    more quietly. Everything else the hooks need is already installed beside the consumer
    inside the wheel, so nothing executable is copied.
    """
    root = _make_package_root(tmp_path)
    files, errors = sync._materialized_files(root)
    assert errors == []
    paths = {f.path.relative_to(root).as_posix() for f in files}

    assert paths == {
        "_aitna/.akmon/guardrails/_common.md",
        "_aitna/.akmon/profiles/python.md",
    }
    guardrail = next(f for f in files if f.path.name == "_common.md")
    assert sync.GENERATED_MARKER in guardrail.content
    assert guardrail.content.startswith("#")  # heading preserved as the first line


def test_no_executable_surface_is_materialized(tmp_path):
    """The whole point, stated as an absence: hooks, ``common``, the routing library and its
    registry stay in the wheel and are reached through ``akmon hook``."""
    root = _make_package_root(tmp_path)
    files, _ = sync._planned_files(root)
    materialized = {
        f.path.relative_to(root).as_posix() for f in files if "/.akmon/" in f.path.relative_to(root).as_posix()
    }
    assert not any(path.endswith(".py") for path in materialized), materialized
    assert not any("/hooks/" in path or "/common/" in path for path in materialized), materialized
    assert not any("model_routing" in path for path in materialized), materialized


def test_a_guardrail_import_quoted_in_prose_is_not_an_import(tmp_path):
    """Only the ``_common.md`` anchor survives when every other mention is an example."""
    agents_md = """# AGENTS

Add a language guardrail, for example `@_aitna/.akmon/guardrails/python.md`.

```markdown
@_aitna/.akmon/guardrails/go.md
```

@_aitna/.akmon/guardrails/_common.md
"""
    root = _make_package_root(tmp_path, agents_md=agents_md)
    names, errors = sync.imported_standard_files(root)
    assert names == ["guardrails/_common.md"]
    assert errors == []


def test_the_common_guardrail_is_materialized_even_when_agents_md_imports_nothing(tmp_path):
    """Its import is the anchor ``verify`` requires of a package-mode AGENTS.md, so a missing
    one is a finding about AGENTS.md — not a licence to ship a broken import target."""
    root = _make_package_root(tmp_path, agents_md="# AGENTS\n")
    names, errors = sync.imported_standard_files(root)
    assert names == ["guardrails/_common.md"]
    assert errors == []


def test_an_import_of_a_moved_file_is_a_plan_error_naming_the_new_line(tmp_path):
    """The language rules left ``guardrails/`` for ``profiles/``. An import of the old path
    resolves to nothing, silently, so the plan error is the only place a consumer learns the new
    line — and it names the line, not just the problem."""
    agents_md = "# AGENTS\n\n@_aitna/.akmon/guardrails/_common.md\n@_aitna/.akmon/guardrails/python.md\n"
    root = _make_package_root(tmp_path, agents_md=agents_md)
    _, errors = sync.imported_standard_files(root)
    assert errors == [
        "AGENTS.md imports guardrails/python.md, which the standard moved to profiles/python.md: "
        "replace the line with @_aitna/.akmon/profiles/python.md"
    ]
    files, plan_errors = sync._planned_files(root)
    assert plan_errors == errors
    assert not any(f.path.name == "python.md" for f in files)


def test_a_mounted_consumer_importing_what_the_mount_lacks_is_a_plan_error(tmp_path):
    """Mounted modes import the mount directly and materialize nothing — which is why the same
    import used to go unchecked there, and a bump that moved a file would have left a mounted
    consumer without its language rules and without a word about it."""
    root = _make_mounted_root(tmp_path)
    mount = root / "_aitna" / "akmon"
    (mount / "guardrails").mkdir()
    (mount / "guardrails" / "_common.md").write_text("# Common\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "# AGENTS\n\n@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/guardrails/python.md\n", encoding="utf-8"
    )
    files, errors = sync._materialized_files(root)
    assert files == []
    assert errors == [
        "AGENTS.md imports guardrails/python.md, which the standard moved to profiles/python.md: "
        "replace the line with @_aitna/akmon/profiles/python.md"
    ]


def test_a_mounted_consumer_whose_imports_resolve_plans_nothing_and_no_error(tmp_path):
    root = _make_mounted_root(tmp_path)
    mount = root / "_aitna" / "akmon"
    for relative in ("guardrails/_common.md", "profiles/python.md"):
        (mount / relative).parent.mkdir(parents=True, exist_ok=True)
        (mount / relative).write_text("# Rules\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "# AGENTS\n\n@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/profiles/python.md\n", encoding="utf-8"
    )
    assert sync._materialized_files(root) == ([], [])


def test_every_moved_import_points_from_a_retired_path_to_a_shipped_one():
    """The move table is only as good as its two ends: a new path the standard does not ship
    sends the consumer to a second broken import, and an old path that still exists makes the
    entry dead."""
    assert sync.MOVED_IMPORTS
    for old, new in sync.MOVED_IMPORTS.items():
        assert not (sync._TREE_ROOT / old).exists(), old
        assert (sync._TREE_ROOT / new).is_file(), new


def test_a_moved_guardrail_copy_is_removed_by_the_sync_that_writes_its_profile(tmp_path):
    """The migration the changelog promises: once ``AGENTS.md`` imports the profile, one ``sync``
    writes the new copy and sweeps the old one — nothing stale is left for the harness to load."""
    root = _make_package_root(tmp_path)
    old = root / "_aitna" / ".akmon" / "guardrails" / "python.md"
    old.parent.mkdir(parents=True)
    old.write_text(materialization.materialized_markdown("# Guardrails: Python\n\nold rule\n"), encoding="utf-8")

    files, errors = sync._planned_files(root)
    assert errors == []
    result = sync._apply(files, write=True, root=root)

    assert old in result.deleted and not old.exists()
    assert (root / "_aitna" / ".akmon" / "profiles" / "python.md").is_file()


def test_stale_materialized_names_a_profile_the_package_has_moved_past(tmp_path):
    """The profile copy is held to the same freshness rule as the guardrail beside it."""
    tree = _tree_with_guardrail(tmp_path, "# Common\n\nrule\n")
    (tree / "profiles").mkdir()
    (tree / "profiles" / "python.md").write_text("# Python\n\nnew rule\n", encoding="utf-8")
    root = tmp_path / "project"
    _materialize(root, "_common.md", "# Common\n\nrule\n")
    profiles = materialization.materialized_dir(root) / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "python.md").write_text(
        materialization.materialized_markdown("# Python\n\nold rule\n"), encoding="utf-8"
    )

    assert materialization.stale_materialized(root, tree) == ["profiles/python.md"]


def test_importing_a_guardrail_the_standard_does_not_ship_is_a_plan_error(tmp_path):
    """Stated, not silently skipped: an import with no target is a broken always-on rule, and
    a materialization that quietly ships nothing for it looks identical to a healthy one."""
    root = _make_package_root(tmp_path, agents_md="# AGENTS\n\n@_aitna/.akmon/guardrails/klingon.md\n")
    _, errors = sync.imported_standard_files(root)
    assert errors == ["AGENTS.md imports a file the standard does not ship: guardrails/klingon.md"]
    _, plan_errors = sync._planned_files(root)
    assert any("klingon.md" in error for error in plan_errors)


def test_sync_check_detects_drift_in_a_materialized_guardrail(tmp_path):
    root = _make_package_root(tmp_path)
    files, errors = sync._planned_files(root)
    assert errors == []
    result = sync._apply(files, write=True, root=root)
    assert not result.errors

    guardrail = root / "_aitna" / ".akmon" / "guardrails" / "_common.md"
    assert guardrail.is_file()
    hand_edited = guardrail.read_text(encoding="utf-8") + "\n<!-- hand edit -->\n"
    guardrail.write_text(hand_edited, encoding="utf-8")

    files2, errors2 = sync._planned_files(root)
    assert errors2 == []
    check_result = sync._apply(files2, write=False, root=root)
    changed_rel = {p.relative_to(root).as_posix() for p in check_result.changed}
    assert "_aitna/.akmon/guardrails/_common.md" in changed_rel
    assert guardrail.read_text(encoding="utf-8") == hand_edited  # --check must not rewrite

    # a real (write=True) sync run then clears the drift.
    result2 = sync._apply(files2, write=True, root=root)
    assert guardrail in result2.changed
    assert "hand edit" not in guardrail.read_text(encoding="utf-8")


def test_a_previous_versions_materialization_is_removed_in_one_run(tmp_path):
    """Migration must finish in one ``sync``, or it leaves a tree nobody reads and nobody
    complains about.

    Three things are pinned together because they fail apart: the banner-less routing registry
    (a banner-only sweep would keep it forever — it has to stay parseable JSON), the emptied
    parent directories, and ``__pycache__`` — swept, but never reported, since a project that
    merely *ran* a hook since the last sync is not drifted.
    """
    root = _make_package_root(tmp_path)
    stale = root / "_aitna" / ".akmon"
    for relative, text in (
        ("hooks/hook_core.py", "# Generated by ...\nprint(1)\n"),
        ("common/project_root.py", "# Generated by ...\n"),
        ("tools/model_routing/routing.py", "# Generated by ...\n"),
        ("tools/model_routing/registry.json", "{}\n"),  # never carried a banner
    ):
        path = stale / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    bytecode = stale / "hooks" / "__pycache__" / "hook_core.cpython-311.pyc"
    bytecode.parent.mkdir(parents=True)
    bytecode.write_bytes(b"\x00")

    files, errors = sync._planned_files(root)
    assert errors == []
    result = sync._apply(files, write=True, root=root)

    deleted = {p.relative_to(root).as_posix() for p in result.deleted}
    assert deleted == {
        "_aitna/.akmon/hooks/hook_core.py",
        "_aitna/.akmon/common/project_root.py",
        "_aitna/.akmon/tools/model_routing/routing.py",
        "_aitna/.akmon/tools/model_routing/registry.json",
    }
    assert not any("__pycache__" in path for path in deleted)
    assert not bytecode.exists() and not bytecode.parent.exists()
    for emptied in ("hooks", "common", "tools/model_routing", "tools"):
        assert not (stale / emptied).exists(), emptied
    assert sorted(p.name for p in stale.iterdir()) == ["guardrails", "profiles"]


def test_sync_check_does_not_report_bytecode_left_by_a_hook_run(tmp_path):
    """``--check`` runs in CI; failing it because someone executed a hook would make the gate
    a coin flip. The cache is neither reported nor (in the non-writing mode) touched."""
    root = _make_package_root(tmp_path)
    files, _ = sync._planned_files(root)
    sync._apply(files, write=True, root=root)
    bytecode = root / "_aitna" / ".akmon" / "guardrails" / "__pycache__" / "x.cpython-311.pyc"
    bytecode.parent.mkdir(parents=True)
    bytecode.write_bytes(b"\x00")

    files2, _ = sync._planned_files(root)
    check_result = sync._apply(files2, write=False, root=root)
    assert check_result.changed == []
    assert check_result.deleted == []
    assert bytecode.exists()


# --------------------------------------------------------------------------------------
# launcher resolution — a property of the project, not of whoever ran sync
# --------------------------------------------------------------------------------------


def test_launcher_prefers_the_project_venv(tmp_path):
    root = _make_package_root(tmp_path)
    assert sync.launcher_relative(root) == ".venv/bin/akmon"


def test_launcher_accepts_the_unhidden_venv_spelling(tmp_path):
    root = _make_package_root(tmp_path)
    shutil.rmtree(root / ".venv")
    legacy = root / "venv" / "bin" / "akmon"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("#!/bin/sh\n", encoding="utf-8")
    legacy.chmod(0o755)
    assert sync.launcher_relative(root) == "venv/bin/akmon"


def test_launcher_ignores_an_interpreter_outside_the_project(tmp_path, monkeypatch):
    """A pipx install, and akmon's own dev checkout running ``sync`` over a fixture, are both
    normal and both outside the consumer — neither says anything about its layout, and an
    absolute path in a committed file is a silent break for every other developer."""
    root = _make_package_root(tmp_path / "project")
    shutil.rmtree(root / ".venv")
    elsewhere = tmp_path / "elsewhere" / "bin"
    elsewhere.mkdir(parents=True)
    (elsewhere / "akmon").write_text("#!/bin/sh\n", encoding="utf-8")
    (elsewhere / "akmon").chmod(0o755)
    (elsewhere / "python3").write_text("", encoding="utf-8")
    monkeypatch.setattr(sync.sys, "executable", str(elsewhere / "python3"))
    monkeypatch.setattr(sync.shutil, "which", lambda _name: str(elsewhere / "akmon"))
    assert sync.launcher_relative(root) == ".venv/bin/akmon"


def test_launcher_accepts_an_interpreter_inside_the_project(tmp_path, monkeypatch):
    root = _make_package_root(tmp_path)
    shutil.rmtree(root / ".venv")
    inside = root / "env" / "bin"
    inside.mkdir(parents=True)
    (inside / "akmon").write_text("#!/bin/sh\n", encoding="utf-8")
    (inside / "akmon").chmod(0o755)
    (inside / "python3").write_text("", encoding="utf-8")
    monkeypatch.setattr(sync.sys, "executable", str(inside / "python3"))
    monkeypatch.setattr(sync.shutil, "which", lambda _name: None)
    assert sync.launcher_relative(root) == "env/bin/akmon"


def test_launcher_ignores_a_non_executable_script(tmp_path, monkeypatch):
    root = _make_package_root(tmp_path)
    launcher = root / ".venv" / "bin" / "akmon"
    launcher.chmod(0o644)
    fallback = root / "venv" / "bin" / "akmon"
    fallback.parent.mkdir(parents=True)
    fallback.write_text("#!/bin/sh\n", encoding="utf-8")
    fallback.chmod(0o755)
    monkeypatch.setattr(sync.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sync.sys, "executable", str(tmp_path / "nowhere" / "python3"))

    assert not sync.is_executable_file(launcher)
    assert sync.launcher_relative(root) == "venv/bin/akmon"


def test_launcher_never_fails_and_predicts_the_convention(tmp_path, monkeypatch):
    """The first attach runs ``sync`` *before* the dev group is installed, by construction. A
    hard error here would break the one flow that has to work out of the box; the prediction
    becomes true the moment the pin is installed, and ``verify`` reports it until then."""
    root = _make_package_root(tmp_path)
    shutil.rmtree(root / ".venv")
    monkeypatch.setattr(sync.shutil, "which", lambda _name: None)
    monkeypatch.setattr(sync.sys, "executable", str(tmp_path / "nowhere" / "python3"))
    assert sync.launcher_relative(root) == ".venv/bin/akmon"


# --------------------------------------------------------------------------------------
# hook wiring — the console script in package mode, files in mounted modes
# --------------------------------------------------------------------------------------


def test_claude_wiring_names_the_console_script_and_no_repo_path_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    entries = sync._claude_hooks(root)["hooks"]
    commands = [hook["command"] for event in entries.values() for entry in event for hook in entry["hooks"]]
    assert commands, "no hook commands generated"
    for command in commands:
        assert command.startswith('"$CLAUDE_PROJECT_DIR/.venv/bin/akmon" hook '), command
        assert "_aitna/" not in command, command
        assert ".py" not in command, command
    assert '"$CLAUDE_PROJECT_DIR/.venv/bin/akmon" hook delegation-log' in commands


def test_codex_wiring_keeps_its_advisory_argument_in_package_mode(tmp_path):
    root = _make_package_root(tmp_path)
    entries = sync._codex_hooks(root)["hooks"]
    commands = [hook["command"] for event in entries.values() for entry in event for hook in entry["hooks"]]
    assert '"$(git rev-parse --show-toplevel)/.venv/bin/akmon" hook codex-hook role-on-code' in commands
    for command in commands:
        assert "_aitna/" not in command, command


def test_mounted_wiring_still_names_files(tmp_path):
    """Unchanged by construction: in a mounted mode the path is both spellable and pinned."""
    root = _make_mounted_root(tmp_path)
    claude = sync._claude_settings(root).content
    codex = json.dumps(sync._codex_hooks(root))
    assert "_aitna/akmon/hooks/git-commit-guard.py" in claude
    assert "akmon\\" not in claude and " hook " not in claude
    assert "_aitna/akmon/hooks/codex-hook.py" in codex


def _akmon_entry(path: str) -> dict:
    return {"matcher": "Bash", "hooks": [{"type": "command", "command": f'python3 "{path}"'}]}


def _launcher_entry() -> dict:
    return {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": '"$CLAUDE_PROJECT_DIR/.venv/bin/akmon" hook git-commit-guard'}],
    }


def test_is_akmon_entry_recognises_every_spelling_the_generator_ever_emitted(monkeypatch):
    """Including the retired ones. Recognition is what lets a mode switch *replace* an entry
    instead of leaving the old one running beside the new."""
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    assert sync._is_akmon_entry(_akmon_entry("_aitna/akmon/hooks/git-commit-guard.py"))
    assert sync._is_akmon_entry(_akmon_entry("_aitna/.akmon/hooks/git-commit-guard.py"))
    assert sync._is_akmon_entry(_launcher_entry())


def test_a_projects_own_hook_mentioning_akmon_is_not_recognised_as_ours(monkeypatch):
    """The marker carries the closing quote (``akmon" hook ``) for this reason: a bare
    ``akmon hook`` would also match a project hook that merely names the package."""
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 tools/akmon hook check.py"}]}
    assert not sync._is_akmon_entry(mine)


@pytest.mark.parametrize(
    ("name", "stale", "wanted"),
    [
        ("mounted -> package", _akmon_entry("_aitna/akmon/hooks/git-commit-guard.py"), _launcher_entry()),
        ("package -> mounted", _launcher_entry(), _akmon_entry("_aitna/akmon/hooks/git-commit-guard.py")),
        (
            "materialized package -> package",
            _akmon_entry("_aitna/.akmon/hooks/git-commit-guard.py"),
            _launcher_entry(),
        ),
    ],
)
def test_merge_replaces_the_other_spellings_entry(monkeypatch, name, stale, wanted):
    monkeypatch.delenv("AITNA_ROOT", raising=False)
    merged = sync._merge_hook_entries([stale], [wanted])
    assert stale not in merged, name
    assert merged == [wanted], name


# --------------------------------------------------------------------------------------
# _upsert_toml_key
# --------------------------------------------------------------------------------------


def test_upsert_toml_key_updates_existing_top_level_key():
    text = 'a = "1"\nb = "2"\n'
    assert sync._upsert_toml_key(text, "a", "9") == 'a = "9"\nb = "2"\n'


def test_upsert_toml_key_inserts_before_first_section():
    text = 'a = "1"\n\n[test]\nrunner = "pytest"\n'
    result = sync._upsert_toml_key(text, "b", "2")
    lines = result.splitlines()
    assert lines.index('b = "2"') < lines.index("[test]")
    assert 'a = "1"' in result
    assert 'runner = "pytest"' in result


def test_upsert_toml_key_appends_when_no_section_present():
    text = 'a = "1"\n'
    assert sync._upsert_toml_key(text, "b", "2") == 'a = "1"\nb = "2"\n'


def test_upsert_toml_key_ignores_commented_lines():
    text = '# a = "old"\na = "1"\n'
    assert sync._upsert_toml_key(text, "a", "9") == '# a = "old"\na = "9"\n'


# --------------------------------------------------------------------------------------
# .akmon.toml version stamping
# --------------------------------------------------------------------------------------


def test_package_mode_akmon_toml_none_outside_package_mode(tmp_path, monkeypatch):
    root = _make_mounted_root(tmp_path)
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: "0.4.0")
    assert sync._package_mode_akmon_toml(root) is None


def test_package_mode_akmon_toml_none_when_version_unknown(tmp_path, monkeypatch):
    root = _make_package_root(tmp_path)
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: None)
    assert sync._package_mode_akmon_toml(root) is None


def test_package_mode_akmon_toml_stamps_version_and_preserves_other_fields(tmp_path, monkeypatch):
    root = _make_package_root(
        tmp_path,
        extra_toml='attached_archetype = "package"\nlast_realign = "2026-01-01"\n\n[test]\nrunner = "pytest"\n',
    )
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: "0.4.0")
    planned = sync._package_mode_akmon_toml(root)
    assert planned is not None
    assert planned.path == root / "_aitna" / ".akmon.toml"
    assert 'akmon_version = "0.4.0"' in planned.content
    assert 'mount = "package"' in planned.content
    assert 'attached_archetype = "package"' in planned.content
    assert 'last_realign = "2026-01-01"' in planned.content
    assert 'runner = "pytest"' in planned.content


def test_planned_files_include_akmon_toml_stamp_in_package_mode(tmp_path, monkeypatch):
    root = _make_package_root(tmp_path)
    monkeypatch.setattr(sync, "_installed_akmon_version", lambda: "0.4.0")
    files, errors = sync._planned_files(root)
    assert errors == []
    toml_plan = next((f for f in files if f.path.name == ".akmon.toml"), None)
    assert toml_plan is not None
    assert 'akmon_version = "0.4.0"' in toml_plan.content


def test_a_malformed_record_falls_through_to_the_lenient_parser_rather_than_raising():
    """The reader documents "absent or unreadable"; on 3.11+ it used to raise instead.

    Found while landing the C69/D2-26 veto: `tomllib.load` propagated `TOMLDecodeError`, so a
    project with a broken `.akmon.toml` crashed `sync`, `verify` and — once the hooks consulted
    the record — a session, on 3.11+ only, while 3.9 parsed the same file to a partial dict.

    The result is not `{}`: the fallback line parser still resolves the well-formed lines it can
    read, so `mount = "package"` survives a broken file and `records_package_mode` can answer
    `True` off it — this is what makes the shared reader "lenient by contract" (C75), not merely
    non-raising.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".akmon.toml"
        path.write_text('mount = "package"\n[unclosed\nkey = ', encoding="utf-8")
        result = sync.read_akmon_toml(path)  # no exception
        assert result == {"mount": "package", "key": ""}


def test_both_parsers_agree_on_a_record_with_an_inline_comment():
    """The documented shape, on either host Python: `tomllib` and the fallback must not differ."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".akmon.toml"
        path.write_text('mount = "package"  # materialized\n', encoding="utf-8")
        assert sync.read_akmon_toml(path)["mount"] == "package"


# --------------------------------------------------------------------------------------
# common.materialization.stale_materialized — the freshness half of the one remaining copy
# --------------------------------------------------------------------------------------


def _tree_with_guardrail(tmp_path: Path, text: str) -> Path:
    """A minimal standard tree carrying one guardrail, standing in for the installed package."""
    tree = tmp_path / "tree"
    (tree / "guardrails").mkdir(parents=True)
    (tree / "guardrails" / "_common.md").write_text(text, encoding="utf-8")
    return tree


def _materialize(root: Path, name: str, text: str) -> Path:
    dest = materialization.materialized_dir(root) / "guardrails"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / name
    path.write_text(materialization.materialized_markdown(text), encoding="utf-8")
    return path


def test_stale_guardrails_is_empty_without_a_materialization(tmp_path):
    """Every mounted-mode project, and a package-mode one between ``init`` and its first
    ``sync``: there is no copy to be stale, and the check must not invent one."""
    tree = _tree_with_guardrail(tmp_path, "# Common\n\nrule\n")
    assert materialization.stale_materialized(tmp_path / "project", tree) == []


def test_stale_guardrails_is_empty_when_the_copy_matches(tmp_path):
    text = "# Common\n\nrule\n"
    tree = _tree_with_guardrail(tmp_path, text)
    root = tmp_path / "project"
    _materialize(root, "_common.md", text)

    assert materialization.stale_materialized(root, tree) == []


def test_stale_guardrails_names_a_guardrail_the_package_has_moved_past(tmp_path):
    """The bump this exists for: the pin resolves, the hooks run from the new package, and the
    repository still holds the previous release's rules until someone runs ``sync``."""
    root = tmp_path / "project"
    _materialize(root, "_common.md", "# Common\n\nold rule\n")
    tree = _tree_with_guardrail(tmp_path, "# Common\n\nnew rule\n")

    assert materialization.stale_materialized(root, tree) == ["guardrails/_common.md"]


def test_stale_guardrails_names_a_hand_edited_copy(tmp_path):
    """Same instruction, different cause — and the reason the comparison is against content
    rather than a recorded version: a version stamp cannot see this at all."""
    text = "# Common\n\nrule\n"
    tree = _tree_with_guardrail(tmp_path, text)
    root = tmp_path / "project"
    path = _materialize(root, "_common.md", text)
    path.write_text(path.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")

    assert materialization.stale_materialized(root, tree) == ["guardrails/_common.md"]


def test_stale_guardrails_names_a_guardrail_the_package_no_longer_ships(tmp_path):
    tree = _tree_with_guardrail(tmp_path, "# Common\n\nrule\n")
    root = tmp_path / "project"
    _materialize(root, "retired.md", "# Retired\n\nrule\n")

    assert materialization.stale_materialized(root, tree) == ["guardrails/retired.md"]


def test_stale_guardrails_ignores_non_markdown_leftovers(tmp_path):
    """Sweeping stray files under ``.akmon/`` is ``sync``'s job and it reports them; the hook
    speaks only about what the harness actually ``@``-imports."""
    tree = _tree_with_guardrail(tmp_path, "# Common\n\nrule\n")
    root = tmp_path / "project"
    dest = materialization.materialized_dir(root) / "guardrails"
    dest.mkdir(parents=True)
    (dest / "notes.txt").write_text("stray\n", encoding="utf-8")

    assert materialization.stale_materialized(root, tree) == []


def test_sync_writes_guardrails_the_freshness_check_calls_current(tmp_path):
    """The two halves joined: what ``sync`` writes is exactly what the hook calls fresh. They
    share one format owner precisely so this cannot drift apart."""
    root = _make_package_root(tmp_path)
    files, errors = sync._materialized_files(root)
    assert errors == []
    for planned in files:
        planned.path.parent.mkdir(parents=True, exist_ok=True)
        planned.path.write_text(planned.content, encoding="utf-8")

    assert materialization.stale_materialized(root, sync.standard_tree_root(root)) == []
