"""C83: ``common/record.py`` stays the one reader of ``<AITNA_ROOT>/.akmon.toml``.

Before a shared reader existed, four modules beside ``bin/sync.py`` grew narrow readers of their
own, each justified in place; C69 gave the record one home and C75 folded them into it (D2-39).
Nothing stopped another from appearing — these static carriers do. A function that parses TOML, or
a module whose code names the record's path, outside the ones listed here goes red: read the
record through ``common.record.read_akmon_toml``, or add the entry with the reason it needs one.
Docstrings do not count; code, messages included, does.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Every function that may import ``tomllib`` (module level would read as "<module>"), and why.
_TOML_PARSERS = {
    ("common/record.py", "read_akmon_toml"): "the shared reader, lenient by contract",
    ("common/record.py", "read_akmon_toml_strict"): (
        "the shared reader's strict entry, for a caller that applies the record (ADR 0014 §4)"
    ),
    ("common/python_rules.py", "load_catalog"): "reads the Python rule catalog, not the record",
    ("tools/d2_ledger/d2_ledger.py", "_read_akmon_toml"): (
        "strict on purpose: a broken record must fail the D2 path check, not switch it off (D2-39)"
    ),
    ("tools/release/release_check.py", "_pyproject_version"): "reads pyproject.toml, not the record",
    ("bin/sync.py", "_read_manifest"): "reads the consumer's pyproject.toml for the akmon pin, not the record (C84)",
}

# Every module whose code names the record's path, and what it does with it.
_RECORD_PATH_USERS = {
    "bin/sync.py": "stamps and upserts the record; reads it through the re-exported shared reader",
    "bin/check.py": "reads [python] through the shared reader's strict entry",
    "bin/verify.py": "validates the record, read through the shared reader",
    "common/python_rules.py": "names the record in the target of a configuration finding",
    "common/project_root.py": "an existence check — the package-mode marker — and a notice",
    "common/record.py": "the shared reader",
    "hooks/hook_core.py": "d2_sensitive_paths, through the shared reader",
    "src/akmon/_init.py": "writes the record; reads it through the shared reader",
    "src/akmon/cli.py": "reads the recorded pin through the shared reader",
    "tools/d2_ledger/d2_ledger.py": "the strict local reader (D2-39)",
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
