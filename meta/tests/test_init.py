"""Unit + end-to-end tests for ``akmon init`` (``src/akmon/_init.py``, C37).

The end-to-end tests are the point of the file: attach a throwaway consumer under
``tmp_path`` in each mount mode and drive the whole chain the design specifies —
``init`` → ``sync`` → model-routing init → ``verify --strict`` — asserting the last one comes
back green. Nothing touches the real repo except read-only: the "embedded tree" a dev bench
resolves to *is* this checkout (``akmon._tree``'s editable fallback), which is what the
vendored/package fixtures copy or read from.

The submodule test clones this repository over ``file://`` (no network), which git refuses
for submodules since CVE-2022-39253 unless ``protocol.file.allow=always`` — set through
``GIT_CONFIG_*`` in the test's own environment, never in the shipped code.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SRC = _AKMON / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from akmon import __version__, _init, _tree, cli  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


@pytest.fixture(autouse=True)
def isolated_aitna_root(monkeypatch):
    """`init` sets ``AITNA_ROOT`` in the process environment on purpose (every step and every
    subprocess it spawns must agree on one dev-layer root). In-process tests therefore have to
    be isolated from each other: without this, one test's ``--aitna-root`` would silently
    relocate the dev layer of every test that ran after it."""
    monkeypatch.setenv("AITNA_ROOT", "_aitna")


@pytest.fixture
def local_git_repo(monkeypatch):
    """Allow ``file://`` submodule clones for this test process only."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")


# --------------------------------------------------------------------------------------
# The tree_members data must stay equal to the wheel's member lists
# --------------------------------------------------------------------------------------


def _wheel_tree_members() -> tuple[str, ...]:
    """The wheel's standard-tree members, in declared order: the ``force-include`` keys, then the
    ``only-include`` members ``sources`` maps under ``akmon/_tree/`` (``src/akmon`` is the CLI
    package, not the tree). The split is hatchling's — force-include ignores ``exclude``, so a
    member carrying files to drop (``js/``'s tests) is an ``only-include`` one (C118)."""
    wheel = tomllib.loads((_AKMON / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]
    wheel = wheel["targets"]["wheel"]
    forced = list(wheel["force-include"])
    assert all(wheel["force-include"][member] == f"akmon/_tree/{member}" for member in forced)
    mapped = [member for member in wheel["only-include"] if member != "src/akmon"]
    assert all(wheel["sources"][member] == f"akmon/_tree/{member}" for member in mapped)
    return (*forced, *mapped)


def test_tree_members_match_the_wheel_members():
    """Mode ``vendored`` must mount exactly what mode ``package`` ships (ADR 0009 D01).

    Both lists are hand-maintained in different files, so the equality is asserted rather
    than trusted; a member added to the wheel and forgotten here would silently produce a
    poorer vendored mount. The list lives in the shared data file (``src/akmon/init.json``)
    since C102.
    """
    assert _wheel_tree_members() == tuple(_INIT_DATA["tree_members"])


def test_no_carrier_member_is_the_development_record():
    """``meta/`` is akmon's development record, not the standard: neither the wheel, the npm
    package nor the vendored copy carries it (ADR 0009, C118 amendment)."""
    manifest = json.loads((_AKMON / "package.json").read_text(encoding="utf-8"))
    assert "meta" not in _INIT_DATA["tree_members"]
    assert "meta" not in _wheel_tree_members()
    assert not [entry for entry in manifest["files"] if entry.split("/", 1)[0] == "meta"]


# --------------------------------------------------------------------------------------
# src/akmon/init.json — the shared init text and tables (C102)
# --------------------------------------------------------------------------------------

_INIT_DATA = json.loads((_AKMON / "src" / "akmon" / "init.json").read_text(encoding="utf-8"))


def test_init_data_pins_its_structure():
    """The data file is the single owner of the init text: pin the key set and a few
    characteristic exact values so a transcription drift is caught here, not in the corpus."""
    assert set(_INIT_DATA) == {
        # the Python init's refusal of a record the JavaScript implementation wrote (C105), and the
        # package-mode spelling of the CLI it names (`node_mounted_cli` the mounted one, C129)
        "python_refuses_ecosystem",
        "node_package_cli",
        # the Python init's hand-over of a Node attach to the JavaScript implementation (C129)
        "python_hands_over_node",
        "python_hands_over_why",
        "python_switch_hands_over",
        # the JavaScript init's own keys (C105, C129); this file never reads them
        "node_refuses_record",
        "node_refuses_python_ecosystem",
        "node_refuses_python_why",
        "node_refuses_reverse",
        # the JavaScript init's move of a Python-mounted record to Node (C129 step 8)
        "node_refuses_record_switch",
        "node_switch_mounted_only",
        "node_switch_log",
        "node_switch_checks_redecided",
        "node_switch_codex_step",
        "node_switch_ruff_step",
        # the refusal of a mount that predates the switch, and the data that says so (C129)
        "node_switch_requires",
        "node_switch_mount_predates",
        "node_switch_mount_update",
        "node_mounted_cli",
        "node_oxlint_rules",
        "node_oxlint_rules_mounted",
        "node_oxlintrc_text",
        "node_oxlintrc_wrote",
        "node_oxlintrc_env_step",
        "node_oxlintrc_own_step",
        "node_oxlint_step",
        "node_scripts_step",
        "node_mode_reason",
        "agents_shared_layer_node",
        "gitignore_lines_node",
        "node_managers",
        "ci_workflow_steps_node",
        "ci_workflow_steps_node_mounted",
        "record_fresh_node",
        "pin_step_node",
        "report_missing_node",
        "akmon_repo",
        "tree_members",
        "tree_members_node",
        "tree_markers",
        "copy_ignore",
        "mount_gitignore",
        "mount_text",
        "agents_header",
        "agents_block",
        "agents_roles_hint_package",
        "agents_roles_hint_mounted",
        "agents_shared_layer_package",
        "agents_shared_layer_mounted",
        "tasks_skeleton",
        "memory_index",
        "charters",
        "charter",
        "charter_locate_package",
        "charter_locate_mounted",
        "gitignore_lines",
        "ci_workflow",
        "ci_workflow_steps_package",
        "ci_workflow_steps_mounted",
        "record_fresh",
        "record_version_line",
        "old_mount_removal",
        "mode_switch_step",
        "mode_switch_link_resolution_package",
        "mode_switch_link_resolution_mounted",
        "mode_switch_remove_mount",
        "pin_step",
        "ruff_step",
        # an explicit --checks deciding an empty [check] table again (C129 audit F4)
        "checks_redecided_empty",
        "run_prefix",
        "write_ci_commands",
        "report",
        "closing_steps",
    }
    assert _INIT_DATA["akmon_repo"] == "https://github.com/akumidv/ai_akmon"
    assert list(_INIT_DATA["charters"]) == ["review", "architect", "engineer"]  # write order is load-bearing
    assert _INIT_DATA["charters"]["engineer"] == "realize a decided structure in code, with tests"
    assert _INIT_DATA["tree_markers"] == ["bin/sync.py", "bin/verify.py", "roles/README.md", "guardrails/_common.md"]
    assert _INIT_DATA["mount_gitignore"] == "__pycache__/\n*.py[cod]\n"
    assert _INIT_DATA["ruff_step"]["uv"] == (
        "add ruff as a development dependency so `akmon check` can run it: `uv add --dev ruff`"
    )
    assert _INIT_DATA["run_prefix"] == {"uv.lock": "uv run ", "poetry.lock": "poetry run "}
    assert _INIT_DATA["write_ci_commands"]["package"] == ["akmon sync --check", "akmon verify --strict"]
    assert _INIT_DATA["report"]["complete"] == "attached, with steps left to a human/agent decision:"
    assert _INIT_DATA["report"]["incomplete"] == "attached, but INCOMPLETE:"
    assert _INIT_DATA["old_mount_removal"]["submodule"] == (
        "    git submodule deinit -f -- {{relative}}\n    git rm -f -- {{relative}}\n"
        "    rm -rf .git/modules/{{relative}}"
    )
    assert _INIT_DATA["memory_index"].startswith("# Project memory")
    assert "{{aitna}}/.akmon.toml" in _INIT_DATA["tasks_skeleton"]
    assert "{{version}}" in _INIT_DATA["record_version_line"]
    assert set(_INIT_DATA["pin_step"]) == {"none", "runtime", "unreadable"}
    assert set(_INIT_DATA["old_mount_removal"]) == {"submodule", "subtree", "vendored"}


def test_init_loader_asks_for_exactly_the_init_json(monkeypatch):
    """The loader reads ``init.json`` beside ``_init.py`` — the path the wheel and the corpus
    snapshot both place the file at."""
    from common import jsondata

    seen: list[Path] = []
    real_read = jsondata.read

    def spy(path):
        seen.append(path)
        return real_read(path)

    monkeypatch.setattr(jsondata, "read", spy)
    assert _init.akmon_repo() == "https://github.com/akumidv/ai_akmon"
    assert _init.tree_members()
    assert seen, "the loader never asked for the data file"
    for path in seen:
        assert path == Path(_init.__file__).parent / "init.json"


def test_init_data_file_error_propagates_uncaught(monkeypatch):
    """A missing or broken ``init.json`` is a loud failure, not a swallowed one."""
    from common import jsondata

    def broken_read(path):
        raise jsondata.DataFileError(f"akmon data file missing: {path}")

    monkeypatch.setattr(jsondata, "read", broken_read)
    with pytest.raises(jsondata.DataFileError):
        _init._agents_block("_aitna", "v0.1.0", _init._Classification("backend", "python"), package_mode=True)
    with pytest.raises(jsondata.DataFileError):
        _init._tasks_skeleton("_aitna")


# --------------------------------------------------------------------------------------
# pure helpers
# --------------------------------------------------------------------------------------


def test_version_key_orders_releases_numerically():
    assert _init._version_key("v0.10.0") > _init._version_key("v0.9.0")
    assert max(["v0.2.1", "v0.10.0", "v0.3.0"], key=_init._version_key) == "v0.10.0"


def test_tag_for_version_points_at_main_for_a_development_version():
    assert _init._tag_for_version("0.4.0") == "v0.4.0"
    assert _init._tag_for_version("v0.4.0") == "v0.4.0"
    assert _init._tag_for_version("0.4.0.dev0") == "main"


@pytest.mark.parametrize(
    "version",
    ["0.4.0.dev0", "0.4.0a1", "0.4.0b2", "0.4.0rc1", "0.4.0.post1", "0.4.0+local.1", "v0.4.0-3-gdeadbee", "0.4", ""],
)
def test_no_non_final_version_is_pointed_at_a_tag(version):
    # One owner answers "is this a release": the substring heuristic this replaced returned
    # `v0.4.0.post1` — a tag no repository carries.
    assert _init._tag_for_version(version) == "main"


def test_package_default_ref_uses_the_latest_tag_from_the_requested_remote(tmp_path, monkeypatch):
    seen = []

    def remote_tags(cmd, *, cwd, capture, timeout):
        seen.append((cmd, cwd, capture, timeout))
        return subprocess.CompletedProcess(
            cmd,
            0,
            "aaa refs/tags/v0.2.1\nccc refs/tags/v0.3.0\nbbb refs/tags/v0.10.0\n",
            "",
        )

    monkeypatch.setattr(_init, "_run", remote_tags)
    assert _init._package_default_ref("https://example.invalid/akmon", tmp_path) == "v0.10.0"
    assert seen == [
        (
            [
                "git",
                "ls-remote",
                "--tags",
                "--refs",
                "https://example.invalid/akmon",
                "refs/tags/v*",
            ],
            tmp_path,
            True,
            20,
        )
    ]


def test_package_default_ref_without_local_git_fails_when_remote_is_unavailable(tmp_path, monkeypatch):
    assert not (tmp_path / ".git").exists()  # installed/wheel-like consumer
    monkeypatch.setattr(
        _init,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, "", "unreachable"),
    )
    with pytest.raises(_init._InitError, match=r"pass --ref explicitly"):
        _init._package_default_ref("https://example.invalid/akmon", tmp_path)


def test_default_mode_is_vendored_outside_a_git_repository(tmp_path):
    mode, reason = _init._default_mode(tmp_path, _init.akmon_repo())
    assert mode == "vendored"
    assert "not a git repository" in reason


def test_default_mode_is_submodule_for_a_reachable_repo(tmp_path, monkeypatch, local_git_repo):
    _git(["init", "-q", "."], cwd=tmp_path)
    monkeypatch.setattr(_init, "_remote_reachable", lambda repo, root: True)
    mode, reason = _init._default_mode(tmp_path, _init.akmon_repo())
    assert mode == "submodule"
    assert "git repository" in reason


def test_merge_gitignore_appends_only_missing_lines():
    existing = "node_modules/\n*.env\n"
    merged = _init._merge_gitignore(existing, _init._gitignore_lines("_aitna"))
    assert merged.startswith(existing)
    assert merged.count("*.env\n") == 1  # already there, not duplicated
    assert "!*.env.example" in merged
    assert ".claude/agents/k_*.md" in merged


def test_merge_gitignore_is_idempotent():
    once = _init._merge_gitignore("", _init._gitignore_lines("_aitna"))
    twice = _init._merge_gitignore(once, _init._gitignore_lines("_aitna"))
    assert twice == once


def test_merge_gitignore_leaves_a_complete_file_untouched():
    complete = "\n".join(_init._gitignore_lines("_aitna")) + "\n"
    assert _init._merge_gitignore(complete, _init._gitignore_lines("_aitna")) == complete


# --------------------------------------------------------------------------------------
# AGENTS.md — hand-owned source text
# --------------------------------------------------------------------------------------


def _init_vendored(root: Path, *extra: str) -> int:
    return _init.main(["--mode", "vendored", "--project-root", str(root), "--yes", *extra])


def test_init_writes_agents_md_when_absent(tmp_path):
    assert _init_vendored(tmp_path) == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert _init.block_heading() in text
    assert "@_aitna/akmon/guardrails/_common.md" in text
    assert "delegation is the default" in text.lower()


# The fresh block's language-profile imports (C127): one per detected language, right after the
# common guardrail, under the attach's prefix; none for an unknown language, which keeps `classify`.


def test_init_imports_the_profile_the_language_flag_names(tmp_path, capsys):
    assert _init_vendored(tmp_path, "--archetype", "package", "--language", "python") == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/profiles/python.md\n" in text
    assert "classify the project" not in capsys.readouterr().out


def test_init_imports_the_profile_the_manifest_names_and_keeps_classify(tmp_path, capsys):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\n')
    assert _init_vendored(tmp_path, "--checks", "none") == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/profiles/python.md\n" in text
    out = capsys.readouterr().out
    assert "classify the project's archetype against ARCHETYPES.md" in out  # the archetype is still unclassified
    assert "import the language profile" not in out  # init already imported it (C127)


def test_init_imports_both_profiles_python_first(tmp_path):
    _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\n')
    _write(tmp_path / "package.json", "{}\n")
    assert _init_vendored(tmp_path, "--checks", "none") == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert (
        "@_aitna/akmon/guardrails/_common.md\n@_aitna/akmon/profiles/python.md\n@_aitna/akmon/profiles/js.md\n"
    ) in text


def test_init_imports_no_profile_for_an_unknown_language(tmp_path, capsys):
    assert _init_vendored(tmp_path, "--archetype", "custom", "--language", "rust") == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    assert sync_mod.profile_imports(text) == []
    assert "@_aitna/akmon/guardrails/_common.md\n\n" in text
    out = capsys.readouterr().out
    assert "classify the project (archetype + language)" in out
    assert "import the language profile in AGENTS.md" in out


def test_package_block_imports_profiles_under_the_materialized_prefix():
    block = _init._agents_block(
        "_aitna", "v0.1.0", _init._Classification("package", "python", ("python.md",)), package_mode=True
    )
    assert "@_aitna/.akmon/guardrails/_common.md\n@_aitna/.akmon/profiles/python.md\n" in block
    # the quoted form names no profile: the example is a placeholder, not a value to copy
    assert "`@_aitna/.akmon/profiles/<name>.md`" in block


def test_init_appends_the_block_and_preserves_existing_content(tmp_path):
    _write(tmp_path / "AGENTS.md", "# AGENTS.md\n\nProject-specific rules nobody may lose.\n")
    assert _init_vendored(tmp_path) == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Project-specific rules nobody may lose." in text
    assert _init.block_heading() in text


def test_init_never_rewrites_an_existing_akmon_block(tmp_path):
    hand_written = f"# AGENTS.md\n\n{_init.block_heading()}\n\nHand-tuned block; do not touch.\n"
    _write(tmp_path / "AGENTS.md", hand_written)
    assert _init_vendored(tmp_path) == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == hand_written


# --------------------------------------------------------------------------------------
# the integration record
# --------------------------------------------------------------------------------------


def test_akmon_toml_records_the_keys_verify_requires(tmp_path):
    assert _init_vendored(tmp_path, "--archetype", "package", "--language", "python") == 0
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    fields = sync_mod.read_akmon_toml(tmp_path / "_aitna" / ".akmon.toml")
    assert fields["mount"] == "vendored"
    assert fields["akmon_version"] == __version__
    assert fields["last_realign"] == __version__
    assert fields["attached_archetype"] == "package/python"


def test_realign_preserves_hand_written_record_fields(tmp_path):
    assert _init_vendored(tmp_path, "--archetype", "service", "--language", "python") == 0
    record = tmp_path / "_aitna" / ".akmon.toml"
    record.write_text(
        record.read_text(encoding="utf-8").replace('# runner = "uv run pytest"', 'runner = "poetry run pytest"'),
        encoding="utf-8",
    )
    assert _init_vendored(tmp_path) == 0  # a re-run without the archetype flags

    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    fields = sync_mod.read_akmon_toml(record)
    assert fields["test"]["runner"] == "poetry run pytest"
    assert fields["attached_archetype"] == "service/python"  # not reset to the placeholder


def test_bare_init_reuses_the_recorded_package_mode(tmp_path, monkeypatch):
    """The documented bare ``akmon init`` is an idempotent realign, not a mode migration."""
    _dev_pin(tmp_path)
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 0
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        _init,
        "_default_mode",
        lambda *args: (_ for _ in ()).throw(AssertionError("an existing valid mode must win")),
    )
    monkeypatch.setattr(_init, "_package_default_ref", lambda repo, root: "v0.3.0")

    assert _init.main([]) == 0
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    assert sync_mod.read_akmon_toml(tmp_path / "_aitna" / ".akmon.toml")["mount"] == "package"


def test_sync_failure_preserves_the_previous_last_realign(tmp_path, monkeypatch):
    _dev_pin(tmp_path)
    record = tmp_path / "_aitna" / ".akmon.toml"
    _write(
        record,
        'mount = "package"\nakmon_version = "v0.2.1"\nlast_realign = "v0.2.1"\nattached_archetype = "package/python"\n',
    )
    monkeypatch.setattr(cli, "_dispatch", lambda *args, **kwargs: 7)

    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 7
    fields = cli._load_embedded_sync(_tree.embedded_tree_root()).read_akmon_toml(record)
    assert fields["akmon_version"] == __version__
    assert fields["last_realign"] == "v0.2.1"


def test_fresh_sync_failure_does_not_claim_a_completed_realign(tmp_path, monkeypatch):
    _dev_pin(tmp_path)
    monkeypatch.setattr(cli, "_dispatch", lambda *args, **kwargs: 7)

    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 7
    fields = cli._load_embedded_sync(_tree.embedded_tree_root()).read_akmon_toml(tmp_path / "_aitna" / ".akmon.toml")
    assert fields["akmon_version"] == __version__
    assert "last_realign" not in fields


def test_routing_init_failure_preserves_the_previous_last_realign(tmp_path, monkeypatch):
    _dev_pin(tmp_path)
    record = tmp_path / "_aitna" / ".akmon.toml"
    _write(
        record,
        'mount = "package"\nakmon_version = "v0.2.1"\nlast_realign = "v0.2.1"\nattached_archetype = "package/python"\n',
    )
    monkeypatch.setattr(cli, "_dispatch", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        _init,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 8, "", "routing failed"),
    )

    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 8
    fields = cli._load_embedded_sync(_tree.embedded_tree_root()).read_akmon_toml(record)
    assert fields["akmon_version"] == __version__
    assert fields["last_realign"] == "v0.2.1"


def test_fresh_routing_init_failure_does_not_claim_a_completed_realign(tmp_path, monkeypatch):
    _dev_pin(tmp_path)
    monkeypatch.setattr(cli, "_dispatch", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        _init,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 8, "", "routing failed"),
    )

    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 8
    fields = cli._load_embedded_sync(_tree.embedded_tree_root()).read_akmon_toml(tmp_path / "_aitna" / ".akmon.toml")
    assert fields["akmon_version"] == __version__
    assert "last_realign" not in fields


# --------------------------------------------------------------------------------------
# the local layout
# --------------------------------------------------------------------------------------


def test_init_creates_the_local_layout_and_leaves_its_files_alone_on_a_re_run(tmp_path):
    assert _init_vendored(tmp_path) == 0
    aitna = tmp_path / "_aitna"
    for name in ("agents", "skills", "tools", "memory"):
        assert (aitna / name).is_dir()
    tasks = aitna / "TASKS.md"
    assert "TASKS_ARCHIVE.md" in tasks.read_text(encoding="utf-8")
    assert (aitna / "memory" / "README.md").is_file()
    assert (aitna / "agents" / "engineer" / "README.md").is_file()

    tasks.write_text("# my own backlog\n", encoding="utf-8")
    assert _init_vendored(tmp_path) == 0
    assert tasks.read_text(encoding="utf-8") == "# my own backlog\n"


def test_vendored_mount_carries_the_standard_but_not_the_development_carrier(tmp_path):
    assert _init_vendored(tmp_path) == 0
    mount = tmp_path / "_aitna" / "akmon"
    assert (mount / "bin" / "sync.py").is_file()
    assert (mount / "hooks" / "hook_core.py").is_file()
    assert not (mount / "meta").exists()  # the development record is not the standard (ADR 0009, C118)
    assert not (mount / "src").exists()  # the CLI package is the carrier, not the standard
    assert not (mount / ".git").exists()
    assert "__pycache__" in (mount / ".gitignore").read_text(encoding="utf-8")


def test_the_mount_carries_the_js_runtime_but_not_its_tests(tmp_path):
    # A mounted file sits inside the consumer's project root, which `node --test` and `eslint`
    # both scan by default: with the tests mounted, a consumer's own `node --test` ran akmon's
    # suites and reported 4 failures it could not fix (M116). Since C118 the wheel and the npm
    # package drop them too; the copy's own ignore list still keeps the mount clean when the
    # origin is a source checkout, which carries them.
    assert _init_vendored(tmp_path) == 0
    mounted = list((tmp_path / "_aitna" / "akmon" / "js").rglob("*.mjs"))
    assert mounted, "the mount carries no JavaScript at all"
    assert (tmp_path / "_aitna" / "akmon" / "js" / "common" / "record.mjs").is_file()
    assert not [path for path in mounted if path.name.endswith(".test.mjs")]

    checkout = _AKMON / "js"
    expected = {path.relative_to(checkout).as_posix() for path in checkout.rglob("*.mjs")} - {
        path.relative_to(checkout).as_posix() for path in checkout.rglob("*.test.mjs")
    }
    assert {path.relative_to(tmp_path / "_aitna" / "akmon" / "js").as_posix() for path in mounted} == expected


def test_init_writes_a_ci_workflow_only_when_the_project_has_none(tmp_path, capsys):
    _write(tmp_path / ".github" / "workflows" / "own.yml", "name: own\n")
    assert _init_vendored(tmp_path) == 0
    assert not (tmp_path / ".github" / "workflows" / "akmon.yml").exists()
    assert "existing workflow" in capsys.readouterr().out


def test_init_skips_the_ci_workflow_on_no_ci(tmp_path, capsys):
    assert _init_vendored(tmp_path, "--no-ci") == 0
    assert not (tmp_path / ".github" / "workflows" / "akmon.yml").exists()
    assert "add the contract checks to CI" in capsys.readouterr().out


# --------------------------------------------------------------------------------------
# end to end: init -> sync -> routing init -> verify --strict
# --------------------------------------------------------------------------------------


def _dev_pin(root: Path) -> None:
    """The manifest a package-mode consumer must carry: akmon in a dev group (ADR 0009 §4).

    Mode ``package`` mounts no tree, so this declaration *is* the mount — an attach without it
    now ends non-zero, which is why the package-mode fixtures write it before attaching.
    """
    _write(
        root / "pyproject.toml",
        '[project]\nname = "consumer"\nversion = "0.1.0"\n\n'
        '[dependency-groups]\ndev = ["akmon @ git+https://github.com/akumidv/ai_akmon@v0.3.0"]\n',
    )


def _project_venv(root: Path) -> None:
    """The console script an installed dev pin puts in the project venv.

    Written by hand because the fixture never actually installs anything, and since C77 the
    generated hook wiring names it — ``verify``'s ``hooks.launcher`` check reports its absence
    (correctly: a hook command with a missing executable fails silently).
    """
    launcher = root / ".venv" / "bin" / "akmon"
    _write(launcher, "#!/bin/sh\n")
    launcher.chmod(0o755)


def _verify_strict(root: Path, monkeypatch) -> int:
    """``akmon verify --strict`` the way a consumer runs it — through the CLI's own dispatch."""
    monkeypatch.chdir(root)
    return cli.main(["verify", "--strict", "--quiet", "--project-root", str(root)])


def test_vendored_attach_verifies_strict_green(tmp_path, monkeypatch):
    assert _init_vendored(tmp_path) == 0
    assert cli.main(["sync", "--check", "--project-root", str(tmp_path)]) == 0
    assert (tmp_path / "CLAUDE.md").is_file()
    assert sorted((tmp_path / ".claude" / "agents").glob("k_*.md"))  # model-routing init ran
    assert _verify_strict(tmp_path, monkeypatch) == 0


def test_package_attach_verifies_strict_green(tmp_path, monkeypatch):
    _dev_pin(tmp_path)
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 0
    assert not (tmp_path / "_aitna" / "akmon").exists()  # no tree in the repo (ADR 0009 §4)
    # The imported guardrails, and nothing else: no executable surface is copied any more —
    # the wiring calls `akmon hook`, which runs the hooks from inside the wheel (C77).
    materialized = sorted(
        path.relative_to(tmp_path).as_posix() for path in (tmp_path / "_aitna" / ".akmon").rglob("*") if path.is_file()
    )
    # No linter of its own, so init set up ruff with akmon's rules — the standard `extend` — and
    # sync materialized them beside the imported guardrail and the Python profile, which the
    # fresh block imports because the project has a pyproject.toml (C127).
    assert materialized == [
        "_aitna/.akmon/guardrails/_common.md",
        "_aitna/.akmon/profiles/python.md",
        "_aitna/.akmon/profiles/ruff.toml",
    ]
    configs = [
        p.read_text(encoding="utf-8") for p in (tmp_path / "pyproject.toml", tmp_path / "ruff.toml") if p.is_file()
    ]
    assert any('extend = "_aitna/.akmon/profiles/ruff.toml"' in text for text in configs)
    assert "ruff check {files}" in (tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8")
    assert sorted((tmp_path / ".claude" / "agents").glob("k_*.md"))
    _project_venv(tmp_path)
    assert _verify_strict(tmp_path, monkeypatch) == 0


def test_package_attach_without_a_manifest_pin_is_incomplete(tmp_path, capsys):
    """No pin, no mount, no way to run akmon — an attach that ends here has not finished, and
    the exit code has to say so (the CI job this same run wrote would fail next)."""
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    out = capsys.readouterr().out
    assert "dev** group" in out and "git+https://github.com/akumidv/ai_akmon@" in out
    assert "INCOMPLETE" in out and "exit 1" in out
    fields = cli._load_embedded_sync(_tree.embedded_tree_root()).read_akmon_toml(tmp_path / "_aitna" / ".akmon.toml")
    assert "last_realign" not in fields


def test_package_pin_gate_preserves_the_previous_last_realign(tmp_path, monkeypatch):
    record = tmp_path / "_aitna" / ".akmon.toml"
    _write(
        record,
        'mount = "package"\nakmon_version = "v0.2.1"\nlast_realign = "v0.2.1"\nattached_archetype = "package/python"\n',
    )
    monkeypatch.setattr(cli, "_dispatch", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        _init,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )

    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    fields = cli._load_embedded_sync(_tree.embedded_tree_root()).read_akmon_toml(record)
    assert fields["akmon_version"] == __version__
    assert fields["last_realign"] == "v0.2.1"


def test_package_attach_with_a_dev_pin_is_complete(tmp_path):
    _dev_pin(tmp_path)
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 0


def test_package_verify_strict_fails_while_the_manifest_has_no_pin(tmp_path, monkeypatch):
    """The same contract, enforced past the attach: `init` reports it once, `verify --strict`
    (the CI gate) keeps reporting it for as long as the pin is missing."""
    _write(tmp_path / "pyproject.toml", '[project]\nname = "consumer"\nversion = "0.1.0"\n')
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    assert _verify_strict(tmp_path, monkeypatch) == 1
    _dev_pin(tmp_path)
    _project_venv(tmp_path)
    assert _verify_strict(tmp_path, monkeypatch) == 1  # installing the pin is not a completed realign
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 0
    assert _verify_strict(tmp_path, monkeypatch) == 0


def test_submodule_attach_verifies_strict_green(tmp_path, monkeypatch, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    code = _init.main(
        [
            "--mode",
            "submodule",
            "--project-root",
            str(consumer),
            "--repo",
            f"file://{_AKMON}",
            "--ref",
            "HEAD",
            "--yes",
        ]
    )
    assert code == 0
    assert (consumer / "_aitna" / "akmon" / "bin" / "sync.py").is_file()
    assert (consumer / ".gitmodules").is_file()
    # `init` mounts and stages what git stages for a submodule, but never commits (D5).
    assert (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(consumer), capture_output=True, check=False).returncode
        != 0
    )
    assert _verify_strict(consumer, monkeypatch) == 0


def test_a_second_init_does_not_move_an_existing_pin(tmp_path, capsys, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    common = ["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_AKMON}", "--yes"]
    assert _init.main([*common, "--ref", "v0.3.0"]) == 0
    mount = consumer / "_aitna" / "akmon"
    pinned = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(mount), capture_output=True, text=True, check=False
    ).stdout.strip()

    assert _init.main(common) == 0  # a realign, not a bump
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(mount), capture_output=True, text=True, check=False
    ).stdout.strip()
    assert after == pinned
    assert "left at its current pin" in capsys.readouterr().out


def test_init_rejects_submodule_mode_outside_a_git_repository(tmp_path, capsys):
    assert _init.main(["--mode", "submodule", "--project-root", str(tmp_path), "--yes"]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_init_honours_a_relocated_dev_layer_root(tmp_path, monkeypatch):
    assert _init.main(["--mode", "vendored", "--project-root", str(tmp_path), "--aitna-root", "tools/ai", "--yes"]) == 0
    assert (tmp_path / "tools" / "ai" / "akmon" / "bin" / "sync.py").is_file()
    assert (tmp_path / "tools" / "ai" / ".akmon.toml").is_file()
    assert "@tools/ai/akmon/guardrails/_common.md" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert _verify_strict(tmp_path, monkeypatch) == 0


# --------------------------------------------------------------------------------------
# --aitna-root must stay inside the project (review finding 2)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["../escaped", "/tmp/escaped", "a/../../escaped"])
def test_aitna_root_outside_the_project_is_refused(tmp_path, capsys, value):
    project = tmp_path / "project"
    project.mkdir()
    code = _init.main(["--mode", "vendored", "--project-root", str(project), "--aitna-root", value, "--yes"])
    assert code == 2
    assert "--aitna-root" in capsys.readouterr().err
    assert not (tmp_path / "escaped").exists()
    assert list(project.iterdir()) == []  # nothing written anywhere on the refused path


@pytest.mark.parametrize("value", ["../escaped", "/tmp/escaped", "a/../../escaped"])
def test_aitna_root_from_the_environment_is_refused_the_same_way(tmp_path, monkeypatch, capsys, value):
    """The flag and the variable are one contract: the flag's whole effect is to *set* the
    variable, so validating only the flag validated nothing — exporting it reached every path."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AITNA_ROOT", value)
    assert _init.main(["--mode", "vendored", "--project-root", str(project), "--yes"]) == 2
    assert "AITNA_ROOT" in capsys.readouterr().err
    assert not (tmp_path / "escaped").exists()
    assert list(project.iterdir()) == []


def test_aitna_root_env_is_not_left_set_by_a_refused_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AITNA_ROOT", "_aitna")
    assert _init.main(["--mode", "vendored", "--project-root", str(tmp_path), "--aitna-root", "..", "--yes"]) == 2
    assert os.environ["AITNA_ROOT"] == "_aitna"


# --------------------------------------------------------------------------------------
# the staged submodule pin must be the pin (review finding 3)
# --------------------------------------------------------------------------------------


def _sha(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False).stdout.strip()


def test_submodule_index_names_the_ref_that_was_checked_out(tmp_path, local_git_repo):
    """`git submodule add` stages the commit it cloned; the pin is checked out afterwards."""
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    code = _init.main(
        [
            "--mode",
            "submodule",
            "--project-root",
            str(consumer),
            "--repo",
            f"file://{_AKMON}",
            "--ref",
            "v0.3.0",
            "--yes",
        ]
    )
    assert code == 0

    mount = consumer / "_aitna" / "akmon"
    staged = subprocess.run(
        ["git", "ls-files", "-s", "_aitna/akmon"], cwd=str(consumer), capture_output=True, text=True, check=False
    ).stdout.split()
    assert staged[1] == _sha(["rev-parse", "HEAD"], cwd=mount) == _sha(["rev-parse", "v0.3.0"], cwd=mount)
    status = subprocess.run(
        ["git", "status", "--porcelain", "_aitna/akmon"], cwd=str(consumer), capture_output=True, text=True, check=False
    ).stdout
    assert "AM" not in status  # the index and the worktree agree
    assert (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(consumer), capture_output=True, check=False).returncode
        != 0
    )


# --------------------------------------------------------------------------------------
# mode subtree — `git subtree add` commits, so the owner runs it (review finding 1)
# --------------------------------------------------------------------------------------


def test_subtree_refuses_to_add_the_subtree_itself_and_creates_no_commit(tmp_path, capsys, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "root"], cwd=consumer)
    before = _sha(["rev-parse", "HEAD"], cwd=consumer)

    code = _init.main(["--mode", "subtree", "--project-root", str(consumer), "--repo", f"file://{_AKMON}", "--yes"])
    assert code == 2
    err = capsys.readouterr().err
    assert "git subtree add --prefix _aitna/akmon" in err
    assert "akmon init --mode subtree --ref" in err
    assert _sha(["rev-parse", "HEAD"], cwd=consumer) == before  # D5: no commit was created


def test_subtree_attaches_onto_a_subtree_the_owner_added(tmp_path, monkeypatch, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "root"], cwd=consumer)
    _git(
        [
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "subtree",
            "add",
            "--prefix",
            "_aitna/akmon",
            f"file://{_AKMON}",
            "HEAD",
            "--squash",
        ],
        cwd=consumer,
    )
    assert _init.main(["--mode", "subtree", "--project-root", str(consumer), "--ref", "HEAD", "--yes"]) == 0
    assert (consumer / "_aitna" / "akmon" / "bin" / "sync.py").is_file()
    assert _verify_strict(consumer, monkeypatch) == 0


def test_subtree_realign_requires_the_ref_it_cannot_read_from_disk(tmp_path, capsys, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "root"], cwd=consumer)
    _git(
        [
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "subtree",
            "add",
            "--prefix",
            "_aitna/akmon",
            f"file://{_AKMON}",
            "HEAD",
            "--squash",
        ],
        cwd=consumer,
    )
    assert _init.main(["--mode", "subtree", "--project-root", str(consumer), "--yes"]) == 2
    assert "--ref" in capsys.readouterr().err


# --------------------------------------------------------------------------------------
# switching the mount mode is a migration, not a realign (review finding 4)
# --------------------------------------------------------------------------------------


def test_mode_switch_is_refused_without_the_flag(tmp_path, capsys):
    assert _init_vendored(tmp_path) == 0
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--yes"]) == 2
    err = capsys.readouterr().err
    assert "migration" in err and "--switch-mode" in err
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    assert sync_mod.read_akmon_toml(tmp_path / "_aitna" / ".akmon.toml")["mount"] == "vendored"  # unchanged


def test_a_foreign_ecosystem_record_is_refused_before_the_mode_switch(tmp_path, capsys):
    """A record the JavaScript implementation wrote, plus a mount-mode change: the ecosystem
    refusal answers, not the unready-switch one — the ``--switch-mode`` re-run that one advises
    would be refused here anyway (C119)."""
    record = 'mount = "package"\necosystem = "node"\n'
    _write(tmp_path / "_aitna" / ".akmon.toml", record)
    expected = (
        _INIT_DATA["python_refuses_ecosystem"]
        .replace("{{value}}", "node")
        .replace("{{aitna}}", "_aitna")
        .replace("{{cli}}", "npx akmon")
    )
    for flags in ([], ["--switch-mode"]):
        assert _init.main(["--mode", "vendored", *flags, "--project-root", str(tmp_path), "--yes"]) == 2
        assert capsys.readouterr().err == f"akmon init: {expected}\n"
    assert (tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8") == record
    assert not (tmp_path / "AGENTS.md").exists()


def test_mode_switch_names_the_edits_it_will_not_make(tmp_path, capsys):
    assert _init_vendored(tmp_path) == 0
    _dev_pin(tmp_path)
    capsys.readouterr()
    assert (
        _init.main(
            [
                "--mode",
                "package",
                "--switch-mode",
                "--project-root",
                str(tmp_path),
                "--ref",
                "v0.3.0",
                "--yes",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "re-point the AGENTS.md akmon block" in out
    assert "@_aitna/.akmon/guardrails/_common.md" in out
    assert "remove the now-unused mount `_aitna/akmon`" in out
    assert "update the akmon commands in your existing workflow(s)" in out


# --------------------------------------------------------------------------------------
# the package-mode manifest pin (review finding 5)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        ("# akmon will be added later\n", "none"),
        ('[project]\ndescription = "built with akmon"\ndependencies = ["pandas"]\n', "none"),
        ('[dependency-groups]\ndev = ["akmon-plugin"]\n', "none"),
        ('[project]\ndependencies = ["akmon @ git+https://x"]\n', "runtime"),
        ('[project]\ndependencies = [\n  "pandas",\n  "akmon @ git+https://x",\n]\n', "runtime"),
        ('[dependency-groups]\ndev = [\n  "pytest",\n  "akmon==0.4.0",\n]\n', "dev"),
        ('[dependency-groups]\ndev = [\n  "akmon==0.4.0",\n', "unreadable"),
        ('[project.optional-dependencies]\nagent = ["akmon"]\n', "runtime"),
        ('[tool.poetry.dependencies]\nakmon = "^0.4"\n', "runtime"),
        ('[dependency-groups]\ndev = ["pytest", "akmon @ git+https://x"]\n', "dev"),
        ('[tool.poetry.group.dev.dependencies]\nakmon = { git = "https://x" }\n', "dev"),
        ('[tool.pdm.dev-dependencies]\nagent = ["akmon>=0.4"]\n', "dev"),
        # A correct dev pin must not hide a runtime one declared later in the same file:
        # the classifier reports the worst answer, not the first one it meets.
        (
            '[dependency-groups]\ndev = ["akmon"]\n\n[project]\ndependencies = ["akmon @ git+https://x"]\n',
            "runtime",
        ),
        # A source override says *where a package comes from*, never *that it is required*.
        ('[tool.uv.sources]\nakmon = { git = "https://x", tag = "v0.3.0" }\n', "none"),
        (
            '[project]\ndependencies = ["pandas"]\n\n[tool.uv.sources]\nakmon = { git = "https://x" }\n',
            "none",
        ),
    ],
)
def test_package_pin_status_reads_the_manifest_not_the_word(tmp_path, manifest, expected):
    (tmp_path / "pyproject.toml").write_text(manifest, encoding="utf-8")
    assert _init._package_pin_status(tmp_path) == expected


def test_package_attach_flags_a_pin_in_the_wrong_dependency_class(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["akmon"]\n', encoding="utf-8")
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    out = capsys.readouterr().out
    assert "move the akmon pin" in out and "runtime dependencies" in out


def test_package_attach_names_an_unreadable_manifest_as_the_cause(tmp_path, capsys):
    """A manifest uv cannot parse is not a missing pin: the step and the exit line say which."""
    (tmp_path / "pyproject.toml").write_text('[dependency-groups]\ndev = [\n  "akmon==0.4.0",\n', encoding="utf-8")
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    out = capsys.readouterr().out
    assert "not valid TOML" in out and "INCOMPLETE" in out
    assert "no akmon pin in a dev group" not in out


def test_package_pin_line_uses_the_requested_ref(tmp_path, capsys, monkeypatch):
    def unexpected_default_ref(repo, root):
        raise AssertionError("an explicit --ref must bypass package-mode default discovery")

    monkeypatch.setattr(_init, "_package_default_ref", unexpected_default_ref)
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    assert "git+https://github.com/akumidv/ai_akmon@v0.3.0" in capsys.readouterr().out


def _no_remote(repo, root):
    raise AssertionError("a realign of a recorded project must not query the remote")


def test_package_realign_with_a_record_makes_no_network_request(tmp_path, monkeypatch):
    """The first step of every bump is `akmon init`; it has to work offline."""
    _dev_pin(tmp_path)
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 0
    monkeypatch.setattr(_init, "_package_default_ref", _no_remote)
    assert _init.main(["--project-root", str(tmp_path), "--yes"]) == 0


def test_package_realign_names_the_installed_version_in_the_pin_line(tmp_path, capsys, monkeypatch):
    """With no remote lookup, the pin instruction points at what is installed — no invented tag."""
    assert (
        _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    )  # no dev pin yet; the record is written all the same
    capsys.readouterr()
    monkeypatch.setattr(_init, "_package_default_ref", _no_remote)
    assert _init.main(["--project-root", str(tmp_path), "--yes"]) == 1
    out = capsys.readouterr().out
    assert f"git+https://github.com/akumidv/ai_akmon@{_init._tag_for_version(__version__)}" in out
    assert "Re-run `akmon init` after adding it" in out


def test_package_first_attach_still_asks_the_remote(tmp_path, monkeypatch):
    calls = []

    def default_ref(repo, root):
        calls.append(repo)
        return "v0.3.0"

    monkeypatch.setattr(_init, "_package_default_ref", default_ref)
    _init.main(["--mode", "package", "--project-root", str(tmp_path), "--yes"])
    assert len(calls) == 1


def test_package_pin_line_defaults_to_the_latest_existing_release_tag(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(_init, "_package_default_ref", lambda repo, root: "v0.3.0")
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--yes"]) == 1
    out = capsys.readouterr().out
    assert "git+https://github.com/akumidv/ai_akmon@v0.3.0" in out
    assert "@v0.4.0" not in out


# --------------------------------------------------------------------------------------
# vendored is a replace, not an overlay (review findings 7 and 10)
# --------------------------------------------------------------------------------------


def test_vendored_realign_prunes_what_the_new_version_no_longer_ships(tmp_path):
    assert _init_vendored(tmp_path) == 0
    stale = tmp_path / "_aitna" / "akmon" / "hooks" / "dropped-upstream.py"
    stale.write_text("# a hook a later akmon deleted\n", encoding="utf-8")
    assert _init_vendored(tmp_path) == 0
    assert not stale.exists()
    assert (tmp_path / "_aitna" / "akmon" / "hooks" / "hook_core.py").is_file()


def test_vendored_refuses_to_copy_over_a_directory_that_is_not_akmon(tmp_path, capsys):
    foreign = tmp_path / "_aitna" / "akmon" / "private"
    foreign.mkdir(parents=True)
    (foreign / "data.txt").write_text("not the standard\n", encoding="utf-8")
    assert _init_vendored(tmp_path) == 2
    assert "is not an akmon tree" in capsys.readouterr().err
    assert (foreign / "data.txt").read_text(encoding="utf-8") == "not the standard\n"


def test_vendored_refuses_a_ref_it_cannot_honour(tmp_path, capsys):
    assert _init_vendored(tmp_path, "--ref", "v0.3.0") == 2
    err = capsys.readouterr().err
    assert "`--ref v0.3.0` cannot change it" in err


def test_vendored_mount_is_populated_recursively(tmp_path):
    assert _init_vendored(tmp_path) == 0
    mount = tmp_path / "_aitna" / "akmon"
    for relative in (
        "hooks/hook_core.py",
        "hooks/codex-hook.py",
        "tools/model_routing/registry.json",
        "tools/model_routing/routing.py",
        "roles/engineer.md",
        "pipelines/tasks.md",
    ):
        assert (mount / relative).is_file(), relative
    # Bytecode caches are *not* asserted absent: running the mounted `bin/sync.py` creates them
    # in the mount at attach time, which is exactly why the mount gets a `.gitignore`.
    assert "__pycache__" in (mount / ".gitignore").read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# the generated backlog must teach the standard's own grammar (review finding 6)
# --------------------------------------------------------------------------------------


def test_tasks_skeleton_uses_the_typed_one_line_entry_grammar(tmp_path):
    assert _init_vendored(tmp_path) == 0
    text = (tmp_path / "_aitna" / "TASKS.md").read_text(encoding="utf-8")
    entries = [line for line in text.splitlines() if line.startswith("- ") and " · " in line]
    assert entries
    for entry in entries:
        fields = entry.split(" · ")
        assert len(fields) >= 4, entry
        assert re.fullmatch(r"[ACLNV]\d+", fields[0][2:]), f"typed id required, T# is legacy: {entry}"
        assert fields[2] in ("active", "blocked", "deferred", "done"), entry
        assert len(fields[3].split()) <= 12, entry
    # every entry is one line: no continuation lines under them
    assert not any(line.startswith("  ") and " · " in line for line in text.splitlines())


# --------------------------------------------------------------------------------------
# a mount mode is decided by git, not by the files lying at the path (second review, finding 2)
# --------------------------------------------------------------------------------------


def test_switching_between_mounted_modes_is_refused_while_the_old_mount_is_there(tmp_path, capsys, local_git_repo):
    """vendored → submodule used to exit 0 having created neither `.gitmodules` nor a gitlink:
    the vendored copy carried `bin/sync.py`, so it read as an existing submodule."""
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    assert _init.main(["--mode", "vendored", "--project-root", str(consumer), "--yes"]) == 0
    capsys.readouterr()
    code = _init.main(
        [
            "--mode",
            "submodule",
            "--switch-mode",
            "--project-root",
            str(consumer),
            "--repo",
            f"file://{_AKMON}",
            "--yes",
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "needs the old mount gone first" in err
    assert "rm -rf _aitna/akmon" in err
    assert not (consumer / ".gitmodules").exists()
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    assert sync_mod.read_akmon_toml(consumer / "_aitna" / ".akmon.toml")["mount"] == "vendored"  # unchanged


def test_vendoring_over_a_submodule_is_refused(tmp_path, capsys, local_git_repo):
    """The mirror case: copying into a submodule's working tree writes files into another
    repository the consumer's index still names by gitlink — neither mode, and hard to undo."""
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    assert (
        _init.main(
            [
                "--mode",
                "submodule",
                "--project-root",
                str(consumer),
                "--repo",
                f"file://{_AKMON}",
                "--ref",
                "v0.3.0",
                "--yes",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert _init.main(["--mode", "vendored", "--switch-mode", "--project-root", str(consumer), "--yes"]) == 2
    err = capsys.readouterr().err
    assert "git submodule deinit" in err
    assert _sha(["ls-files", "--stage", "--", "_aitna/akmon"], cwd=consumer).split()[0] == "160000"


def test_submodule_mode_refuses_a_tree_git_does_not_record(tmp_path, capsys, local_git_repo):
    """Even without a recorded mode switch: a directory that is not a submodule must not be
    adopted as one, or the attach records a pin git knows nothing about."""
    consumer = tmp_path / "consumer"
    (consumer / "_aitna" / "akmon" / "bin").mkdir(parents=True)
    _write(consumer / "_aitna" / "akmon" / "bin" / "sync.py", "# a copy, not a submodule\n")
    _git(["init", "-q", "."], cwd=consumer)
    code = _init.main(["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_AKMON}", "--yes"])
    assert code == 2
    assert "does not record it as a submodule" in capsys.readouterr().err
    assert not (consumer / ".gitmodules").exists()


def test_a_foreign_tree_is_not_adopted_on_one_marker(tmp_path, capsys):
    """`bin/sync.py` alone is not an identity: a vendored realign deletes and re-copies whole
    top-level members, so adopting someone's directory on one file destroys their work."""
    mount = tmp_path / "_aitna" / "akmon"
    (mount / "bin").mkdir(parents=True)
    _write(mount / "bin" / "sync.py", "# someone else's sync\n")
    _write(mount / "roles" / "README.md", "# someone else's roles\n")
    assert _init_vendored(tmp_path) == 2
    assert "is not an akmon tree" in capsys.readouterr().err
    assert (mount / "bin" / "sync.py").read_text(encoding="utf-8") == "# someone else's sync\n"


# --------------------------------------------------------------------------------------
# a pin bump is the owner's to stage (second review, finding 5)
# --------------------------------------------------------------------------------------


def test_moving_an_existing_pin_leaves_the_bump_unstaged(tmp_path, capsys, local_git_repo):
    """`init` restages only the entry `git submodule add` created on that same run. Moving an
    existing pin is a bump — a change to the consumer's committed state — so the index is left
    alone and the step is printed instead (D5)."""
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    common = ["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_AKMON}", "--yes"]
    assert _init.main([*common, "--ref", "v0.3.0"]) == 0
    staged = _sha(["ls-files", "--stage", "--", "_aitna/akmon"], cwd=consumer).split()[1]
    capsys.readouterr()

    assert _init.main([*common, "--ref", "main"]) == 0
    out = capsys.readouterr().out
    assert "left unstaged" in out
    assert "git add -- _aitna/akmon" in out
    # the worktree moved, the index did not: the bump is a diff the owner reviews and stages
    assert _sha(["ls-files", "--stage", "--", "_aitna/akmon"], cwd=consumer).split()[1] == staged
    moved = _sha(["rev-parse", "HEAD"], cwd=consumer / "_aitna" / "akmon")
    assert moved != staged
    assert moved == _sha(["rev-parse", "main^{commit}"], cwd=_AKMON)


# --------------------------------------------------------------------------------------
# a Node repository is the JavaScript implementation's (C129, ADR 0020 D02 as amended)
# --------------------------------------------------------------------------------------


def _hand_over(why: str, command: str) -> str:
    text = _INIT_DATA["python_hands_over_node"]
    return "akmon init: " + text.replace("{{why}}", why).replace("{{command}}", command) + "\n"


def test_a_mounted_first_attach_of_a_node_repository_is_handed_over(tmp_path, capsys):
    """package.json and no Python files: the Python init sets up no Python-run mount and runs no
    JavaScript either — it prints the exact command, exit 2, and the project is untouched."""
    _write(tmp_path / "package.json", "{}\n")
    assert _init_vendored(tmp_path) == 2
    captured = capsys.readouterr()
    tag = _init._tag_for_version(__version__)
    assert captured.err == _hand_over(
        "package.json and no Python files", f"npx github:akumidv/ai_akmon#{tag} init --mode vendored"
    )
    assert captured.out == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == ["package.json"]


@pytest.mark.parametrize("python", ["requirements.txt", "app/x.py"])
def test_a_node_repository_with_python_files_is_attached_here(tmp_path, capsys, python):
    """C129 (owner accepted (a)): a requirements file or a git-tracked Python source makes the
    repository a Python one beside package.json — no hand-over, and ruff is set up."""
    _write(tmp_path / "package.json", "{}\n")
    _write(tmp_path / python, "")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", python], cwd=tmp_path, check=True)
    assert _init_vendored(tmp_path) == 0
    assert "JavaScript implementation" not in capsys.readouterr().err
    assert (tmp_path / "ruff.toml").is_file()
    assert 'ruff = "' in (tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8")


def test_the_hand_over_carries_the_flags_and_names_the_mount_cli_when_one_is_there(tmp_path, capsys):
    _write(tmp_path / "package.json", "{}\n")
    _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\n')
    _write(tmp_path / "_aitna" / "akmon" / "js" / "akmon" / "cli.mjs", "")
    argv = ["--ecosystem", "node", "--ref", "v1.2.3", "--repo", "/srv/akmon", "--aitna-root", "_aitna"]
    assert _init.main(["--mode", "submodule", "--project-root", str(tmp_path), "--yes", *argv]) == 2
    assert capsys.readouterr().err == _hand_over(
        "--ecosystem node",
        "node _aitna/akmon/js/akmon/cli.mjs init --mode submodule --ecosystem node --ref v1.2.3 "
        "--aitna-root _aitna --repo /srv/akmon",
    )


def test_the_hand_over_of_a_vendored_mount_names_npx_whatever_is_on_disk(tmp_path, capsys):
    """A Python-vendored copy carries `tree_members` only, not the data the JavaScript CLI reads, so
    its `cli.mjs` is never the command: `npx` re-vendors the mount whole (C129 step 8)."""
    _write(tmp_path / "package.json", "{}\n")
    _write(tmp_path / "_aitna" / "akmon" / "js" / "akmon" / "cli.mjs", "")
    assert _init_vendored(tmp_path, "--ecosystem", "node") == 2
    tag = _init._tag_for_version(__version__)
    assert capsys.readouterr().err == _hand_over(
        "--ecosystem node", f"npx github:akumidv/ai_akmon#{tag} init --mode vendored --ecosystem node"
    )


@pytest.mark.parametrize(
    ("recorded", "tag"),
    [
        pytest.param("9.0.0", "v9.0.0", id="the record is newer"),
        pytest.param("0.1.0", None, id="this implementation is newer"),
    ],
)
def test_the_vendored_switch_hand_over_names_the_newer_release(tmp_path, capsys, recorded, tag):
    """A printed vendored switch names the release that has it: the newer of the record's and this
    implementation's (``common/versions.py::switch_tag``, the one rule; C129)."""
    _write(tmp_path / "package.json", "{}\n")
    _write(tmp_path / "_aitna" / ".akmon.toml", f'mount = "vendored"\nakmon_version = "{recorded}"\n')
    assert _init_vendored(tmp_path, "--ecosystem", "node") == 2
    ref = tag or _init._tag_for_version(__version__)
    command = f"npx github:akumidv/ai_akmon#{ref} init --mode vendored --ecosystem node"
    expected = _INIT_DATA["python_switch_hands_over"].replace("{{aitna}}", "_aitna").replace("{{command}}", command)
    assert capsys.readouterr().err == f"akmon init: {expected}\n"


def test_a_package_mode_node_attach_hands_over_to_the_npm_package(tmp_path, capsys):
    assert _init.main(["--mode", "package", "--ecosystem", "node", "--project-root", str(tmp_path), "--yes"]) == 2
    assert capsys.readouterr().err == _hand_over("--ecosystem node", "npx akmon init --mode package --ecosystem node")


def test_a_mixed_repository_stays_python_unless_the_flag_says_node(tmp_path):
    _write(tmp_path / "package.json", "{}\n")
    _write(tmp_path / "pyproject.toml", '[project]\nname = "demo"\n')
    assert _init_vendored(tmp_path, "--checks", "none") == 0
    assert "ecosystem" not in tomllib.loads((tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8"))


def test_ecosystem_python_attaches_a_node_repository_with_the_python_implementation(tmp_path):
    _write(tmp_path / "package.json", "{}\n")
    assert _init_vendored(tmp_path, "--ecosystem", "python") == 0
    assert (tmp_path / "_aitna" / "akmon" / "bin" / "sync.py").is_file()


def test_package_mode_keeps_the_carrier_ecosystem_in_a_node_repository(tmp_path):
    """Mode package is the wheel's own: no inference, no hand-over (the pin gate answers instead)."""
    _write(tmp_path / "package.json", "{}\n")
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--yes", "--ref", "v0.3.0"]) == 1


def test_a_recorded_python_attach_hands_the_node_switch_over(tmp_path, capsys):
    """The record decides once it exists; `--ecosystem node` on a Python record is the JavaScript
    implementation's switch (C129 step 8), so this init names it and changes nothing."""
    assert _init_vendored(tmp_path) == 0
    record = (tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8")
    capsys.readouterr()
    assert _init_vendored(tmp_path, "--ecosystem", "node") == 2
    tag = _init._tag_for_version(__version__)
    expected = (
        _INIT_DATA["python_switch_hands_over"]
        .replace("{{aitna}}", "_aitna")
        .replace("{{command}}", f"npx github:akumidv/ai_akmon#{tag} init --mode vendored --ecosystem node")
    )
    assert capsys.readouterr().err == f"akmon init: {expected}\n"
    assert (tmp_path / "_aitna" / ".akmon.toml").read_text(encoding="utf-8") == record


@pytest.mark.parametrize(
    ("mode", "ref", "command"),
    [
        ("submodule", "v1.0.0", "node _aitna/akmon/js/akmon/cli.mjs init --ecosystem node"),
        ("subtree", "v1.0.0", "node _aitna/akmon/js/akmon/cli.mjs init --ecosystem node"),
        ("vendored", "v1.0.0", "npx github:akumidv/ai_akmon#v1.0.0 init --ecosystem node"),
    ],
)
def test_the_node_switch_command_is_the_mount_cli_except_for_a_vendored_copy(mode, ref, command):
    assert _init.node_switch_command("_aitna", mode, ref) == command


@pytest.mark.parametrize(("mode", "cli"), [("package", "npx akmon"), ("vendored", "node _x/akmon/js/akmon/cli.mjs")])
def test_a_node_record_is_refused_naming_the_cli_of_its_mode(tmp_path, capsys, mode, cli):
    _write(tmp_path / "_x" / ".akmon.toml", f'mount = "{mode}"\necosystem = "node"\n')
    assert _init.main(["--aitna-root", "_x", "--project-root", str(tmp_path), "--yes"]) == 2
    assert capsys.readouterr().err.endswith(f"run the JavaScript implementation for it: {cli} init\n")


@pytest.mark.parametrize(
    ("repo", "spec"),
    [
        ("https://github.com/akumidv/ai_akmon", "github:akumidv/ai_akmon#v1.0.0"),
        ("https://github.com/akumidv/ai_akmon.git", "github:akumidv/ai_akmon#v1.0.0"),
        ("/srv/akmon", "git+file:///srv/akmon#v1.0.0"),
        ("ssh://git@example.org/akmon.git", "git+ssh://git@example.org/akmon.git#v1.0.0"),
    ],
)
def test_npx_spec_names_a_github_repository_by_its_shorthand(repo, spec):
    assert _init.npx_spec(repo, "v1.0.0") == spec
