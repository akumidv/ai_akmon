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

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SRC = _KEYSTONE / "src"
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
# TREE_MEMBERS must stay equal to the wheel's force-include list
# --------------------------------------------------------------------------------------


def test_tree_members_match_the_wheel_force_include():
    """Mode ``vendored`` must mount exactly what mode ``package`` ships (ADR 0009 §1 parity).

    Both lists are hand-maintained in different files, so the equality is asserted rather
    than trusted; a member added to the wheel and forgotten here would silently produce a
    poorer vendored mount.
    """
    text = (_KEYSTONE / "pyproject.toml").read_text(encoding="utf-8")
    section = text.split("[tool.hatch.build.targets.wheel.force-include]", 1)[1]
    section = section.split("\n[", 1)[0]
    included = tuple(re.findall(r'^"([^"]+)"\s*=', section, flags=re.MULTILINE))
    assert included == _init.TREE_MEMBERS


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
    mode, reason = _init._default_mode(tmp_path, _init.AKMON_REPO)
    assert mode == "vendored"
    assert "not a git repository" in reason


def test_default_mode_is_submodule_for_a_reachable_repo(tmp_path, monkeypatch, local_git_repo):
    _git(["init", "-q", "."], cwd=tmp_path)
    monkeypatch.setattr(_init, "_remote_reachable", lambda repo, root: True)
    mode, reason = _init._default_mode(tmp_path, _init.AKMON_REPO)
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
    assert _init.BLOCK_HEADING in text
    assert "@_aitna/akmon/guardrails/_common.md" in text
    assert "delegation is the default" in text.lower()


def test_init_appends_the_block_and_preserves_existing_content(tmp_path):
    _write(tmp_path / "AGENTS.md", "# AGENTS.md\n\nProject-specific rules nobody may lose.\n")
    assert _init_vendored(tmp_path) == 0
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Project-specific rules nobody may lose." in text
    assert _init.BLOCK_HEADING in text


def test_init_never_rewrites_an_existing_akmon_block(tmp_path):
    hand_written = f"# AGENTS.md\n\n{_init.BLOCK_HEADING}\n\nHand-tuned block; do not touch.\n"
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
    assert (mount / "meta" / "TASKS.md").is_file()  # parity with the submodule (ADR 0009 §1)
    assert not (mount / "src").exists()  # the CLI package is the carrier, not the standard
    assert not (mount / ".git").exists()
    assert "__pycache__" in (mount / ".gitignore").read_text(encoding="utf-8")


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
    assert _init.main(
        ["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]
    ) == 0
    assert not (tmp_path / "_aitna" / "akmon").exists()  # no tree in the repo (ADR 0009 §4)
    assert (tmp_path / "_aitna" / ".akmon" / "hooks" / "hook_core.py").is_file()
    assert (tmp_path / "_aitna" / ".akmon" / "guardrails" / "_common.md").is_file()
    assert sorted((tmp_path / ".claude" / "agents").glob("k_*.md"))
    assert _verify_strict(tmp_path, monkeypatch) == 0


def test_package_attach_without_a_manifest_pin_is_incomplete(tmp_path, capsys):
    """No pin, no mount, no way to run akmon — an attach that ends here has not finished, and
    the exit code has to say so (the CI job this same run wrote would fail next)."""
    assert _init.main(
        ["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]
    ) == 1
    out = capsys.readouterr().out
    assert "dev** group" in out and "git+https://github.com/akumidv/ai_akmon@" in out
    assert "INCOMPLETE" in out and "exit 1" in out


def test_package_attach_with_a_dev_pin_is_complete(tmp_path):
    _dev_pin(tmp_path)
    assert _init.main(
        ["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]
    ) == 0


def test_package_verify_strict_fails_while_the_manifest_has_no_pin(tmp_path, monkeypatch):
    """The same contract, enforced past the attach: `init` reports it once, `verify --strict`
    (the CI gate) keeps reporting it for as long as the pin is missing."""
    _write(tmp_path / "pyproject.toml", '[project]\nname = "consumer"\nversion = "0.1.0"\n')
    assert _init.main(
        ["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]
    ) == 1
    assert _verify_strict(tmp_path, monkeypatch) == 1
    _dev_pin(tmp_path)
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
            f"file://{_KEYSTONE}",
            "--ref",
            "HEAD",
            "--yes",
        ]
    )
    assert code == 0
    assert (consumer / "_aitna" / "akmon" / "bin" / "sync.py").is_file()
    assert (consumer / ".gitmodules").is_file()
    # `init` mounts and stages what git stages for a submodule, but never commits (D5).
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(consumer), capture_output=True).returncode != 0
    assert _verify_strict(consumer, monkeypatch) == 0


def test_a_second_init_does_not_move_an_existing_pin(tmp_path, capsys, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    common = ["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_KEYSTONE}", "--yes"]
    assert _init.main([*common, "--ref", "v0.3.0"]) == 0
    mount = consumer / "_aitna" / "akmon"
    pinned = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(mount), capture_output=True, text=True
    ).stdout.strip()

    assert _init.main(common) == 0  # a realign, not a bump
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(mount), capture_output=True, text=True
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
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True).stdout.strip()


def test_submodule_index_names_the_ref_that_was_checked_out(tmp_path, local_git_repo):
    """`git submodule add` stages the commit it cloned; the pin is checked out afterwards."""
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    code = _init.main(
        ["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_KEYSTONE}",
         "--ref", "v0.3.0", "--yes"]
    )
    assert code == 0

    mount = consumer / "_aitna" / "akmon"
    staged = subprocess.run(
        ["git", "ls-files", "-s", "_aitna/akmon"], cwd=str(consumer), capture_output=True, text=True
    ).stdout.split()
    assert staged[1] == _sha(["rev-parse", "HEAD"], cwd=mount) == _sha(["rev-parse", "v0.3.0"], cwd=mount)
    status = subprocess.run(
        ["git", "status", "--porcelain", "_aitna/akmon"], cwd=str(consumer), capture_output=True, text=True
    ).stdout
    assert "AM" not in status  # the index and the worktree agree
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(consumer), capture_output=True).returncode != 0


# --------------------------------------------------------------------------------------
# mode subtree — `git subtree add` commits, so the owner runs it (review finding 1)
# --------------------------------------------------------------------------------------


def test_subtree_refuses_to_add_the_subtree_itself_and_creates_no_commit(tmp_path, capsys, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "root"], cwd=consumer)
    before = _sha(["rev-parse", "HEAD"], cwd=consumer)

    code = _init.main(
        ["--mode", "subtree", "--project-root", str(consumer), "--repo", f"file://{_KEYSTONE}", "--yes"]
    )
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
        ["-c", "user.email=t@t", "-c", "user.name=t", "subtree", "add", "--prefix", "_aitna/akmon",
         f"file://{_KEYSTONE}", "HEAD", "--squash"],
        cwd=consumer,
    )
    assert _init.main(
        ["--mode", "subtree", "--project-root", str(consumer), "--ref", "HEAD", "--yes"]
    ) == 0
    assert (consumer / "_aitna" / "akmon" / "bin" / "sync.py").is_file()
    assert _verify_strict(consumer, monkeypatch) == 0


def test_subtree_realign_requires_the_ref_it_cannot_read_from_disk(tmp_path, capsys, local_git_repo):
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _git(["init", "-q", "."], cwd=consumer)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "root"], cwd=consumer)
    _git(
        ["-c", "user.email=t@t", "-c", "user.name=t", "subtree", "add", "--prefix", "_aitna/akmon",
         f"file://{_KEYSTONE}", "HEAD", "--squash"],
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


def test_mode_switch_names_the_edits_it_will_not_make(tmp_path, capsys):
    assert _init_vendored(tmp_path) == 0
    _dev_pin(tmp_path)
    capsys.readouterr()
    assert _init.main(
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
    ) == 0
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
    assert _init.main(
        ["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]
    ) == 1
    out = capsys.readouterr().out
    assert "move the akmon pin" in out and "runtime dependencies" in out


def test_package_pin_line_uses_the_requested_ref(tmp_path, capsys, monkeypatch):
    def unexpected_default_ref(repo, root):
        raise AssertionError("an explicit --ref must bypass package-mode default discovery")

    monkeypatch.setattr(_init, "_package_default_ref", unexpected_default_ref)
    assert _init.main(["--mode", "package", "--project-root", str(tmp_path), "--ref", "v0.3.0", "--yes"]) == 1
    assert "git+https://github.com/akumidv/ai_akmon@v0.3.0" in capsys.readouterr().out


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
        "meta/design/packaging/README.md",
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
        ["--mode", "submodule", "--switch-mode", "--project-root", str(consumer),
         "--repo", f"file://{_KEYSTONE}", "--yes"]
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
    assert _init.main(
        ["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_KEYSTONE}",
         "--ref", "v0.3.0", "--yes"]
    ) == 0
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
    code = _init.main(
        ["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_KEYSTONE}", "--yes"]
    )
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
    common = ["--mode", "submodule", "--project-root", str(consumer), "--repo", f"file://{_KEYSTONE}", "--yes"]
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
    assert moved == _sha(["rev-parse", "main^{commit}"], cwd=_KEYSTONE)
