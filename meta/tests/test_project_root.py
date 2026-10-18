"""The contract of the single owner of project-root discovery (C73).

These carriers moved here from ``test_sync.py``, ``test_package_mode.py`` and
``test_model_routing.py`` when the seven copies of the walk collapsed into
``common/project_root.py``: the behaviour has one home, so its tests do too. The last
carrier is the guard against the copies growing back.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import pytest

from common import project_root

# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _mounted_root(tmp_path: Path, aitna: str = "_aitna") -> Path:
    """A project carrying a mounted standard tree at ``<aitna>/akmon``."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / aitna / "akmon").mkdir(parents=True)
    return tmp_path


def _package_root(tmp_path: Path, aitna: str = "_aitna") -> Path:
    """A package-mode project: the integration record is its only marker (ADR 0009 §4)."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / aitna).mkdir(parents=True)
    (tmp_path / aitna / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------------------
# find_project_root
# --------------------------------------------------------------------------------------


def test_find_project_root_walks_up_from_nested_cwd(tmp_path):
    root = _mounted_root(tmp_path)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert project_root.find_project_root(nested) == root


def test_find_project_root_falls_back_to_start_when_no_marker(tmp_path):
    assert project_root.find_project_root(tmp_path) == tmp_path


def test_find_project_root_detects_via_custom_aitna_root(monkeypatch, tmp_path):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    root = _mounted_root(tmp_path, "tools/ai")
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert project_root.find_project_root(nested) == root


def test_find_project_root_accepts_the_record_without_a_mount(tmp_path):
    root = _package_root(tmp_path)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert project_root.find_project_root(nested) == root


def test_find_project_root_still_requires_agents_md(tmp_path):
    (tmp_path / "_aitna").mkdir()
    (tmp_path / "_aitna" / ".akmon.toml").write_text('mount = "package"\n', encoding="utf-8")
    assert project_root.find_project_root(tmp_path) == tmp_path


def test_a_package_project_is_found_under_a_custom_aitna_root(monkeypatch, tmp_path):
    """The combination the three hard-coded copies could not reach: no mount *and* no ``_aitna``."""
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    root = _package_root(tmp_path, "tools/ai")
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert project_root.find_project_root(nested) == root


def _resolve_must_not_run(*_args: object, **_kwargs: object) -> Path:
    raise AssertionError("the bound is checked before any filesystem call")


def test_an_over_long_start_is_refused_before_it_is_resolved(monkeypatch):
    """C121: 32,769 ``a/`` components kept the walk busy for minutes; now it is one ValueError."""
    start = Path("/" + "a/" * 32_769)
    monkeypatch.setattr(Path, "resolve", _resolve_must_not_run)
    began = time.monotonic()
    with pytest.raises(
        ValueError, match=r"^project-root start path is 65538 bytes, over the 4096-byte bound: /a/a/"
    ) as refused:
        project_root.find_project_root(start)
    assert time.monotonic() - began < 1
    assert "\n" not in str(refused.value)
    assert str(refused.value).endswith("...")
    with pytest.raises(ValueError, match="over the 4096-byte bound"):
        project_root.resolve_project_root(None, start)


def test_the_bound_counts_utf8_bytes_and_is_inclusive(tmp_path):
    """4096 bytes is accepted (the walk then runs into the kernel's own limit); 4097 is refused."""
    base = str(tmp_path.resolve())
    filler = 4096 - len(base.encode()) - 1
    at_bound = Path(base + "/" + "é" * (filler // 2) + "x" * (filler % 2))
    assert len(str(at_bound).encode()) == 4096
    with pytest.raises(OSError) as kernel:  # ENAMETOOLONG from is_file(), not the refusal
        project_root.find_project_root(at_bound)
    assert not isinstance(kernel.value, ValueError)
    with pytest.raises(ValueError, match="4097 bytes"):
        project_root.find_project_root(Path(str(at_bound) + "x"))


def test_a_lone_surrogate_is_refused_as_resolve_refuses_it_even_when_over_long():
    """The JS hooks check encodability before the bound; the refusal class must agree."""
    with pytest.raises(UnicodeEncodeError):
        project_root.find_project_root(Path("/a\ud800" + "/b" * 3000))


def test_a_deep_start_under_the_bound_walks_in_linear_time(tmp_path):
    deep = tmp_path.resolve()
    for _ in range(600):  # one level at a time: mkdir(parents=True), like rmtree, recurses per level
        deep /= "a"
        deep.mkdir()
    began = time.monotonic()
    assert project_root.find_project_root(deep) == deep
    assert time.monotonic() - began < 5


# --------------------------------------------------------------------------------------
# resolve_project_root — the entry-point form, where a guess must say so
# --------------------------------------------------------------------------------------


def test_an_explicit_root_is_taken_as_given_and_says_nothing(tmp_path):
    root, notice = project_root.resolve_project_root(tmp_path)
    assert (root, notice) == (tmp_path.resolve(), None)


def test_an_explicit_root_through_a_dangling_link_resolves_to_its_target(tmp_path):
    """``Path.resolve()`` follows a link whose target is missing (the C115 reference)."""
    tree = (tmp_path / "tree").resolve()
    tree.mkdir()
    (tree / "dangling").symlink_to("nonexistent")
    (tree / "chain").symlink_to("dangling")
    assert project_root.resolve_project_root(tree / "dangling")[0] == tree / "nonexistent"
    assert project_root.resolve_project_root(tree / "chain" / "x")[0] == tree / "nonexistent" / "x"
    assert project_root.resolve_project_root(tree / "dangling" / "..")[0] == tree


def test_a_found_root_says_nothing_either(tmp_path):
    root = _mounted_root(tmp_path)
    nested = root / "src" / "pkg"
    nested.mkdir(parents=True)
    assert project_root.resolve_project_root(None, nested) == (root, None)


def test_a_root_that_was_not_found_is_stated_rather_than_returned_bare(tmp_path):
    """The C73 defect: a command that found nothing wrote under the cwd indistinguishably."""
    root, notice = project_root.resolve_project_root(None, tmp_path)
    assert root == tmp_path.resolve()
    assert notice is not None
    assert str(tmp_path.resolve()) in notice
    assert "_aitna/akmon" in notice and "_aitna/.akmon.toml" in notice
    assert "--project-root" in notice


def test_the_notice_names_the_configured_dev_layer_not_the_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    _, notice = project_root.resolve_project_root(None, tmp_path)
    assert notice is not None
    assert "tools/ai/akmon" in notice and "_aitna" not in notice


def test_the_notice_is_one_line_so_a_console_cannot_split_it(tmp_path):
    _, notice = project_root.resolve_project_root(None, tmp_path)
    assert notice is not None
    assert notice.splitlines() == [notice]


# --------------------------------------------------------------------------------------
# the guard: one owner, and the one stated exception
# --------------------------------------------------------------------------------------


def _tree_root() -> Path:
    return next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
    )


def _redefinitions(pattern: str) -> list[str]:
    """Every shipped module that defines ``pattern`` itself, other than the owner."""
    tree = _tree_root()
    owner = tree / "common" / "project_root.py"
    definition = re.compile(pattern, re.MULTILINE)
    return sorted(
        str(path.relative_to(tree))
        for directory in ("common", "bin", "tools", "hooks", "src")
        for path in (tree / directory).rglob("*.py")
        if path != owner and definition.search(path.read_text(encoding="utf-8"))
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root searches any directory")
@pytest.mark.skipif(sys.version_info >= (3, 14), reason="3.14's is_file() swallows every OSError")
def test_a_candidate_that_cannot_be_searched_raises(tmp_path):
    """``Path.is_file()`` lets a permission error through (the C115 reference): the walk does not
    read an unsearchable directory as "no project here"."""
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        with pytest.raises(PermissionError):
            project_root.is_project_root(locked)
    finally:
        locked.chmod(0o755)


def test_no_module_grows_its_own_copy_of_the_walk():
    """Seven copies with three behaviours is what C73 repaired; this is what keeps it repaired.

    No exception is carved out any more. ``hooks/hook_core.py`` was the last one, allowed while
    the fold-in was thought to wait on the C69/D2-26 fork; it does not — that fork is about which
    *tree* the hooks read, not where the root is — so the hooks import the owner like everyone
    else and this guard has no allow-list to erode.
    """
    assert _redefinitions(r"^def _?find_project_root\b") == []


def test_no_module_grows_its_own_copy_of_the_dev_layer_name():
    """The sibling fact, and the one that drifted furthest.

    Three modules defined it and four more spelled ``_aitna`` inline past ``AITNA_ROOT``, so a
    project with a relocated dev layer had its coverage map and its gate packs written into a
    directory it does not read, and its pinned test runner silently ignored.
    """
    assert _redefinitions(r"^def _?aitna_root_name\b") == []


def test_no_shipped_module_spells_the_default_dev_layer_inline():
    """``_aitna`` is a default, not a path: only its owner may name it.

    A literal elsewhere is invisible until someone sets ``AITNA_ROOT``, and then it degrades
    silently rather than failing — which is the whole reason this owner exists.
    """
    tree = _tree_root()
    owner = tree / "common" / "project_root.py"
    literal = re.compile(r'"_aitna"')
    offenders = sorted(
        str(path.relative_to(tree))
        for directory in ("common", "bin", "tools", "hooks", "src")
        for path in (tree / directory).rglob("*.py")
        if path != owner and literal.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == []
