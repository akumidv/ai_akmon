"""C105: ``recorded_ecosystem`` — which ecosystem the integration record names.

The answer table is ``meta/conformance/units/record.toml`` (``[[ecosystem]]``), run on both
implementations. What a units table cannot hold is here: bytes that are not UTF-8, a directory in
the record's place, and the contract that no record written before the key existed changes meaning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.record import recorded_ecosystem


@pytest.fixture(autouse=True)
def _default_aitna_root(monkeypatch):
    monkeypatch.delenv("AITNA_ROOT", raising=False)


def _record(root: Path, text: str, *, relative: str = "_aitna") -> None:
    (root / relative).mkdir(parents=True, exist_ok=True)
    (root / relative / ".akmon.toml").write_text(text, encoding="utf-8")


def test_a_node_attach_is_named_by_the_record(tmp_path):
    _record(tmp_path, 'mount = "package"\necosystem = "node"\n')
    assert recorded_ecosystem(tmp_path) == "node"


def test_a_record_that_predates_the_key_is_python(tmp_path):
    """No existing Python record changes meaning: the key is optional and absent means Python."""
    _record(tmp_path, 'mount = "package"\nakmon_version = "v0.4.0"\n')
    assert recorded_ecosystem(tmp_path) == "python"


def test_no_record_is_python(tmp_path):
    assert recorded_ecosystem(tmp_path) == "python"


@pytest.mark.parametrize("text", ['ecosystem = ""', "ecosystem = 3", "ecosystem = true", 'ecosystem = ["node"]'])
def test_an_empty_or_non_string_value_is_python(tmp_path, text):
    _record(tmp_path, text + "\n")
    assert recorded_ecosystem(tmp_path) == "python"


def test_the_value_is_returned_as_written(tmp_path):
    """Whether it names an ecosystem a caller serves is the caller's question, not the reader's."""
    _record(tmp_path, 'ecosystem = "Node"\n')
    assert recorded_ecosystem(tmp_path) == "Node"


def test_a_broken_record_still_answers_from_its_lines(tmp_path):
    """The reader is the lenient one: a consulting caller must not abort over a file it only reads."""
    _record(tmp_path, 'ecosystem = "node"\n[broke =\n')
    assert recorded_ecosystem(tmp_path) == "node"


def test_bytes_that_are_not_utf8_read_as_python(tmp_path):
    """An undecodable record is unreadable, exactly like an absent one: never a value guessed at it."""
    (tmp_path / "_aitna").mkdir()
    (tmp_path / "_aitna" / ".akmon.toml").write_bytes(b'ecosystem = "node\xff"\n')
    assert recorded_ecosystem(tmp_path) == "python"


def test_a_directory_in_the_records_place_is_python(tmp_path):
    (tmp_path / "_aitna" / ".akmon.toml").mkdir(parents=True)
    assert recorded_ecosystem(tmp_path) == "python"


def test_the_record_is_read_from_the_relocated_dev_layer(tmp_path, monkeypatch):
    _record(tmp_path, 'ecosystem = "node"\n')
    monkeypatch.setenv("AITNA_ROOT", "tools/ai")
    assert recorded_ecosystem(tmp_path) == "python"
    _record(tmp_path, 'ecosystem = "node"\n', relative="tools/ai")
    assert recorded_ecosystem(tmp_path) == "node"


def test_the_answer_is_always_a_string(tmp_path):
    for text in (None, "", 'ecosystem = "node"\n', "ecosystem = 1\n"):
        root = tmp_path / str(abs(hash(text)))
        root.mkdir()
        if text is not None:
            _record(root, text)
        assert isinstance(recorded_ecosystem(root), str)
