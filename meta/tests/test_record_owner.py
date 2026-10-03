"""C83: ``common/record.py`` stays the one reader of ``<AITNA_ROOT>/.akmon.toml``.

Before a shared reader existed, four modules beside ``bin/sync.py`` grew narrow readers of their
own, each justified in place; C69 gave the record one home and C75 folded them into it (D2-39).
Nothing stopped another from appearing — these static carriers do. A function that parses TOML, or
a module whose code names the record's path, outside the ones listed here goes red: read the
record through ``common.record.read_akmon_toml``, or add the entry with the reason it needs one.
Docstrings do not count; code, messages included, does. The file also carries the readers' own
contract on bytes no decoder can read — the one input the corpus cannot pin, since a units table
is itself a text file.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from common.record import RecordError, read_akmon_toml, read_akmon_toml_strict

ROOT = Path(__file__).resolve().parents[2]

# Every function that may import ``tomllib`` (module level would read as "<module>"), and why.
_TOML_PARSERS = {
    ("common/record.py", "read_akmon_toml"): "the shared reader, lenient by contract",
    ("common/record.py", "read_akmon_toml_strict"): (
        "the shared reader's strict entry, for a caller that applies the record (ADR 0014 §4)"
    ),
    ("tools/release/release_check.py", "_pyproject_version"): "reads pyproject.toml, not the record",
    (
        "bin/sync.py",
        "ruff_extends",
    ): "reads the project's ruff configuration for an extend of akmon's rules, not the record",
    ("bin/sync.py", "_read_manifest"): "reads the consumer's pyproject.toml for the akmon pin, not the record (C84)",
}

# Every module whose code names the record's path, and what it does with it.
_RECORD_PATH_USERS = {
    "bin/sync.py": "stamps and upserts the record; reads it through the re-exported shared reader",
    "bin/check.py": "reads [check] through the shared reader's strict entry",
    "bin/verify.py": "validates the record, read through the shared reader",
    "common/project_root.py": "an existence check — the package-mode marker — and a notice",
    "common/record.py": "the shared reader",
    "src/akmon/_init.py": "writes the record; reads it through the shared reader",
    "src/akmon/cli.py": "reads the recorded pin through the shared reader",
    "tools/release/release_check.py": "reads [test].runner through the shared reader",
}


def _shipped_modules() -> Iterator[tuple[str, ast.Module]]:
    for top in ("bin", "common", "hooks", "src", "tools"):
        for path in sorted((ROOT / top).rglob("*.py")):
            yield path.relative_to(ROOT).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return "<module>"


def _imports_tomllib(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] == "tomllib" for alias in node.names)
    return isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "tomllib"


def _docstrings(tree: ast.AST) -> set[ast.AST]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(first.value)
    return found


def test_toml_is_parsed_only_by_the_listed_functions():
    parsers = set()
    for name, tree in _shipped_modules():
        parents = _parents(tree)
        parsers |= {(name, _enclosing_function(n, parents)) for n in ast.walk(tree) if _imports_tomllib(n)}
    assert parsers == set(_TOML_PARSERS)


def test_the_record_path_is_named_only_by_the_listed_modules():
    users = set()
    for name, tree in _shipped_modules():
        docstrings = _docstrings(tree)
        if any(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and ".akmon.toml" in node.value
            and node not in docstrings
            for node in ast.walk(tree)
        ):
            users.add(name)
    assert users == set(_RECORD_PATH_USERS)


# --------------------------------------------------------------------------------------
# the one reader's answer to bytes no decoder can read (the JS twin carries the same two cases)
# --------------------------------------------------------------------------------------


def _undecodable_record(tmp_path):
    """A record whose bytes are not valid UTF-8: ``[akmon]`` then a name with a 0xff 0xfe pair.

    Written with ``write_bytes`` because the input *is* those two bytes — a source-encoded
    ``\\ufffd`` is valid UTF-8, so writing that would test the substitution, not the refusal.
    """
    record = tmp_path / ".akmon.toml"
    record.write_bytes(b'[akmon]\nname = "\xff\xfe bad"\n')
    return record


def test_an_undecodable_record_degrades_to_nothing_leniently(tmp_path):
    """``tomllib.load`` decodes before it parses, so the invalid byte used to escape as a
    ``UnicodeDecodeError`` — aborting a session over a file a hook only consults (C69,
    ADR-0009/D02). It is an unreadable record, so it takes the documented ``{}`` answer; the JS
    twin used to answer the same file with the U+FFFD-substituted value no disk holds.
    """
    assert read_akmon_toml(_undecodable_record(tmp_path)) == {}


def test_an_undecodable_record_is_refused_by_name_strictly(tmp_path):
    """The strict entry, for the caller that *applies* the record, raises the named error and
    says which file. The detail after the colon is the codec's own sentence on this side and the
    decoder's on the JS one; the twins share the refusal, not the prose.
    """
    with pytest.raises(RecordError, match=r"^\.akmon\.toml cannot be read as TOML: "):
        read_akmon_toml_strict(_undecodable_record(tmp_path))
