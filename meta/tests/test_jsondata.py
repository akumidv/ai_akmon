"""common/jsondata — the shared-data loader (C102): loud failure, placeholder fill."""

from __future__ import annotations

from pathlib import Path

import pytest

from common import jsondata


def test_read_parses_a_data_file(tmp_path: Path) -> None:
    data_file = tmp_path / "x.json"
    data_file.write_text('{"a": [1, 2]}\n', encoding="utf-8")
    assert jsondata.read(data_file) == {"a": [1, 2]}


def test_read_names_the_file_when_it_is_missing(tmp_path: Path) -> None:
    with pytest.raises(jsondata.DataFileError, match="missing"):
        jsondata.read(tmp_path / "missing.json")


def test_read_names_the_file_when_it_is_broken(tmp_path: Path) -> None:
    data_file = tmp_path / "broken.json"
    data_file.write_text("{nope", encoding="utf-8")
    with pytest.raises(jsondata.DataFileError, match="not valid JSON"):
        jsondata.read(data_file)


def test_fill_replaces_placeholders_and_keeps_single_braces() -> None:
    assert jsondata.fill("ruff check {files} and {{name}}", {"name": "x"}) == (
        "ruff check {files} and x"
    )


def test_fill_rejects_an_unfilled_placeholder_naming_it() -> None:
    with pytest.raises(jsondata.DataFileError, match="name"):
        jsondata.fill("a {{name}} b", {})
