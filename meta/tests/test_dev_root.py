"""The dev-root accessor of ADR 0022 D09: ``<root>/.aitna-root`` names the root, its absence means ``_aitna``."""

from __future__ import annotations

from pathlib import Path

import pytest

from common import project_root

ROOT = Path(__file__).resolve().parents[2]


def _project(tmp_path: Path, pointer: str | None = None) -> Path:
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    if pointer is not None:
        (tmp_path / ".aitna-root").write_text(pointer, encoding="utf-8")
    return tmp_path


def test_the_pointer_names_the_dev_root(tmp_path):
    root = _project(tmp_path, "tools/ai\n")
    found = project_root.dev_root(root)
    assert found == project_root.DevRoot(root / "tools" / "ai", "pointer")
    assert project_root.aitna_root_name(root) == "tools/ai"


def test_an_absent_file_means_the_default(tmp_path):
    root = _project(tmp_path)
    assert project_root.dev_root(root) == project_root.DevRoot(root / "_aitna", "default")


def test_no_project_root_answers_the_default_for_reading():
    found = project_root.dev_root(None)
    assert (found.path, found.origin) == (Path("_aitna"), "no-project-root")
    assert project_root.aitna_root_name(None) == "_aitna"


@pytest.mark.parametrize("line", ["/abs/place", "../escaped", "a/../../escaped", "", "one\ntwo\n"])
def test_a_refused_declaration_raises_naming_the_value(tmp_path, line):
    root = _project(tmp_path, line)
    with pytest.raises(ValueError, match=r"\.aitna-root"):
        project_root.dev_root(root)


def test_a_symlink_leaving_the_project_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = _project(tmp_path / "proj", "leak") if (tmp_path / "proj").mkdir() is None else None
    (root / "leak").symlink_to(outside)
    with pytest.raises(ValueError, match="resolves outside the project root"):
        project_root.dev_root(root)


def test_the_declaration_alone_marks_a_project_root(tmp_path):
    assert project_root.is_project_root(_project(tmp_path, "meta\n"))


def test_akmons_own_repository_resolves_to_meta():
    assert project_root.aitna_root_name(ROOT) == "meta"
    assert project_root.dev_root(ROOT).origin == "pointer"
    assert project_root.find_project_root(ROOT / "common") == ROOT


def test_a_consumer_with_a_meta_directory_but_no_declaration_is_not_mistaken_for_akmon(tmp_path):
    root = _project(tmp_path)
    (root / "meta").mkdir()
    assert project_root.aitna_root_name(root) == "_aitna"
