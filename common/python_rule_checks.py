#!/usr/bin/env python3
"""The implementations of the Python rule catalog's ``check = "ast"`` rules (ADR 0014 §3).

One function per catalog id, registered in :data:`RULES`; ``common/python_rules.py`` decides
which run on which file and at what severity. A function receives the parsed file and the rule's
effective parameters, and yields ``(line, column, message)`` — the message says what was seen,
never restates the rule (the catalog owns that text). A carrier keeps :data:`RULES` and the
catalog's ``ast`` rules one set.

Where ruff has the same rule, the behaviour follows ruff's on the ordinary case; where it has
none, the heuristic is stated on the function. Stdlib-only.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

Hit = tuple[int, int, str]

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SNAKE_RE = re.compile(r"^_*[a-z][a-z0-9_]*$")
_CAP_WORDS_RE = re.compile(r"^_*[A-Z][A-Za-z0-9]*$")
_MIXED_CASE_RE = re.compile(r"^[a-z][a-z0-9]*[A-Z]")
_GOOGLE_TODO_RE = re.compile(r"#\s*TODO:\s*\S+\s+-\s+\S")
_TODO_RE = re.compile(r"#.*\bTODO\b")
_BARE_NOQA_RE = re.compile(r"#\s*noqa\b(?!\s*:)")
_BARE_TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore\b(?!\[)")
_AKMON_IGNORE_RE = re.compile(r"#\s*akmon:\s*ignore\b(\[[^\]]*\])?\s*(.*)$")
# unittest and visitor-pattern names that the standard library dictates, as ruff's N802 exempts.
_DICTATED_NAMES = {
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "setUpModule",
    "tearDownModule",
    "asyncSetUp",
    "asyncTearDown",
    "setUpTestData",
}
_STDLIB_METACLASSES = {"ABCMeta", "EnumMeta", "EnumType"}
_LOG_LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
_BLOCKING_CALLS = {
    "time.sleep",
    "open",
    "os.system",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "urllib.request.urlopen",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "requests.head",
    "requests.request",
}


@dataclass(frozen=True)
class Source:
    """One parsed file, as every rule sees it."""

    root: Path
    relative: str
    tree: ast.Module
    lines: list[str]
    comments: list[tuple[int, int, str]]
    is_test: bool


def _at(node: ast.AST, message: str) -> Hit:
    return node.lineno, node.col_offset + 1, message


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


def _last_name(node: ast.AST) -> str | None:
    dotted = _dotted(node)
    return dotted.rsplit(".", 1)[-1] if dotted else None


def _own_nodes(body: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """Every node under ``body`` without descending into a nested function, class or lambda."""
    stack = list(body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def _public_functions(tree: ast.Module) -> Iterator[tuple[ast.FunctionDef | ast.AsyncFunctionDef, bool]]:
    """Module-level functions and the methods of public module-level classes, with whether each
    is a method."""
    for node in tree.body:
        if isinstance(node, _FUNCTIONS):
            yield node, False
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for item in node.body:
                if isinstance(item, _FUNCTIONS):
                    yield item, True


def _decorator_names(function: ast.AST) -> set[str]:
    return {_last_name(d.func if isinstance(d, ast.Call) else d) or "" for d in function.decorator_list}


def _parameters(function: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool) -> list[ast.arg]:
    args = [*function.args.posonlyargs, *function.args.args]
    if is_method and args and "staticmethod" not in _decorator_names(function):
        args = args[1:]
    return [*args, *function.args.kwonlyargs]


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def specific_suppression(source: Source, params: Mapping) -> Iterator[Hit]:
    for line, column, comment in source.comments:
        if _BARE_NOQA_RE.search(comment):
            yield line, column + 1, "a bare `# noqa` silences every rule on the line"
        if _BARE_TYPE_IGNORE_RE.search(comment):
            yield line, column + 1, "a bare `# type: ignore` silences every type error on the line"
        ignore = _AKMON_IGNORE_RE.search(comment)
        if ignore and not ignore.group(1):
            yield line, column + 1, "`# akmon: ignore` names no rule"
        elif ignore and not ignore.group(2).strip():
            yield line, column + 1, "`# akmon: ignore[...]` gives no reason"


def _local_bases(source: Source) -> list[Path]:
    return [source.root, source.root / "src"]


def import_modules(source: Source, params: Mapping) -> Iterator[Hit]:
    """For the project's own packages the answer is exact (is ``name`` a module file?); for any
    other package a capitalized name is taken as a class — the one reading that needs no import."""
    exempt = set(params["exempt"])
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        if node.module in exempt or any(node.module.startswith(f"{e}.") for e in exempt):
            continue
        parts = node.module.split(".")
        bases = [base.joinpath(*parts) for base in _local_bases(source)]
        local = any(base.is_dir() or base.with_suffix(".py").is_file() for base in bases)
        for alias in node.names:
            if alias.name == "*":
                continue
            is_module = any((b / f"{alias.name}.py").is_file() or (b / alias.name).is_dir() for b in bases)
            if is_module or (not local and not alias.name[:1].isupper()):
                continue
            yield _at(node, f"imports the symbol `{alias.name}` from `{node.module}`")


def no_wildcard_import(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            yield _at(node, f"imports `*` from `{node.module}`")


def absolute_imports(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            yield _at(node, f"imports relatively: `from {'.' * node.level}{node.module or ''} import ...`")


def no_bare_except(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            yield _at(node, "a bare `except:` catches everything, `SystemExit` included")


def _catches_everything(handler: ast.ExceptHandler) -> str | None:
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for item in types:
        if item is not None and _last_name(item) in {"Exception", "BaseException"}:
            return _last_name(item)
    return None


def no_broad_except(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ExceptHandler):
            caught = _catches_everything(node)
            if caught and not any(isinstance(inner, ast.Raise) for inner in _own_nodes(node.body)):
                yield _at(node, f"catches `{caught}` and does not re-raise")


def no_silent_except(source: Source, params: Mapping) -> Iterator[Hit]:
    """As ruff's S110 by default: only a handler that catches everything is held to it — a
    specific exception deliberately ignored is an ordinary, readable choice."""
    for node in ast.walk(source.tree):
        catches_everything = isinstance(node, ast.ExceptHandler) and (
            node.type is None or _catches_everything(node) is not None
        )
        if catches_everything and len(node.body) == 1:
            only = node.body[0]
            if isinstance(only, ast.Pass) or (
                isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant) and only.value.value is Ellipsis
            ):
                yield _at(node, "the `except` body does nothing")


def no_assert_validation(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Assert):
            yield _at(node, "`assert` checks a condition that `python -O` removes")


def raise_from(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ExceptHandler):
            for inner in _own_nodes(node.body):
                if isinstance(inner, ast.Raise) and isinstance(inner.exc, ast.Call) and inner.cause is None:
                    yield _at(inner, "raises a new exception inside `except` without `from`")


def exception_suffix(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ClassDef) and not node.name.endswith("Error"):
            bases = {_last_name(base) or "" for base in node.bases}
            if any(base in {"Exception", "BaseException"} or base.endswith(("Error", "Exception")) for base in bases):
                yield _at(node, f"exception class `{node.name}` does not end in `Error`")


def no_global_statement(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Global):
            yield _at(node, f"`global {', '.join(node.names)}` rebinds module state")


def simple_comprehension(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, _COMPREHENSIONS):
            clauses = len(node.generators)
            filters = max((len(generator.ifs) for generator in node.generators), default=0)
            if clauses > 1 or filters > 1:
                yield _at(node, f"a comprehension with {clauses} `for` clause(s) and up to {filters} `if` filter(s)")


def _is_keys_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "keys"
        and not node.args
        and not node.keywords
    )


def default_iterator(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        iters = []
        if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            iters.append(node.iter)
        elif isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
            iters.extend(node.comparators)
        for item in iters:
            if _is_keys_call(item):
                yield _at(item, "iterates `.keys()` instead of the mapping itself")


def lambda_use(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Lambda):
            yield _at(node, "binds a lambda to a name instead of defining a function")
        elif (
            isinstance(node, ast.Call)
            and _dotted(node.func) in {"map", "filter"}
            and node.args
            and isinstance(node.args[0], ast.Lambda)
        ):
            yield _at(node, f"`{_dotted(node.func)}` over a lambda instead of a comprehension")


def _is_mutable(node: ast.AST | None) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    return isinstance(node, ast.Call) and _dotted(node.func) in {"list", "dict", "set", "bytearray"}


def no_mutable_default(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, (*_FUNCTIONS, ast.Lambda)):
            for default in [*node.args.defaults, *node.args.kw_defaults]:
                if _is_mutable(default):
                    yield _at(default, "a mutable default value is shared by every call")


def none_and_bool_compare(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            for operand in [node.left, *node.comparators]:
                if isinstance(operand, ast.Constant) and (operand.value is None or isinstance(operand.value, bool)):
                    yield _at(node, f"compares to `{operand.value}` with `==` or `!=`")
                    break


def _truth_tests(node: ast.AST) -> Iterator[ast.AST]:
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _truth_tests(value)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        yield from _truth_tests(node.operand)
    else:
        yield node


def implicit_false(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        tests = []
        if isinstance(node, (ast.If, ast.While, ast.IfExp)):
            tests.append(node.test)
        elif isinstance(node, ast.comprehension):
            tests.extend(node.ifs)
        for test in tests:
            for item in _truth_tests(test):
                if isinstance(item, ast.Call) and _dotted(item.func) == "len":
                    yield _at(item, "tests `len(...)` for truth instead of the sequence itself")


def no_staticmethod(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, _FUNCTIONS) and "staticmethod" in _decorator_names(node):
            yield _at(node, f"`{node.name}` is a `@staticmethod`")


def no_power_features(source: Source, params: Mapping) -> Iterator[Hit]:
    forbid = set(params["forbid"])
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ClassDef) and "metaclass" in forbid:
            for keyword in node.keywords:
                if keyword.arg == "metaclass" and _last_name(keyword.value) not in _STDLIB_METACLASSES:
                    yield _at(node, f"class `{node.name}` uses a custom metaclass")
        elif isinstance(node, _FUNCTIONS) and node.name == "__del__" and "__del__" in forbid:
            yield _at(node, "defines `__del__`")
        elif isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name == "type" and len(node.args) == 3 and "type-3-arg" in forbid:
                yield _at(node, "builds a class with three-argument `type()`")
            elif name in {"__import__", "exec", "eval"} and name in forbid:
                yield _at(node, f"calls `{name}`")
            elif (
                name == "getattr"
                and "getattr-dynamic" in forbid
                and len(node.args) >= 2
                and not isinstance(node.args[1], ast.Constant)
            ):
                yield _at(node, "calls `getattr` with a computed name")


def annotate_public(source: Source, params: Mapping) -> Iterator[Hit]:
    for function, is_method in _public_functions(source.tree):
        if function.name.startswith("_") and not _is_dunder(function.name):
            continue
        missing = [arg.arg for arg in _parameters(function, is_method) if arg.annotation is None]
        if missing:
            yield _at(function, f"`{function.name}` leaves {', '.join(f'`{m}`' for m in missing)} unannotated")
        if function.returns is None and not _is_dunder(function.name):
            yield _at(function, f"`{function.name}` has no return annotation")


def _allows_none(annotation: ast.AST) -> bool:
    if isinstance(annotation, ast.Constant):
        if annotation.value is None:
            return True
        return isinstance(annotation.value, str) and any(w in annotation.value for w in ("None", "Optional", "Any"))
    if _last_name(annotation) in {"Any", "object"}:
        return True
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _allows_none(annotation.left) or _allows_none(annotation.right)
    if isinstance(annotation, ast.Subscript):
        outer = _last_name(annotation.value)
        if outer == "Optional":
            return True
        if outer in {"Union", "Annotated"}:
            inner = annotation.slice.elts if isinstance(annotation.slice, ast.Tuple) else [annotation.slice]
            return any(_allows_none(item) for item in (inner if outer == "Union" else inner[:1]))
    return False


def explicit_optional(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if not isinstance(node, _FUNCTIONS):
            continue
        positional = [*node.args.posonlyargs, *node.args.args]
        pairs = list(zip(positional[len(positional) - len(node.args.defaults) :], node.args.defaults, strict=True))
        pairs += [(arg, d) for arg, d in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True) if d]
        for arg, default in pairs:
            is_none = isinstance(default, ast.Constant) and default.value is None
            if is_none and arg.annotation is not None and not _allows_none(arg.annotation):
                yield _at(arg, f"`{arg.arg}` defaults to `None` but its annotation does not allow it")


def _documented_args(docstring: str) -> set[str] | None:
    lines = docstring.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "Args:":
            names = set()
            indent = None
            for entry in lines[index + 1 :]:
                if not entry.strip():
                    continue
                width = len(entry) - len(entry.lstrip())
                if indent is None:
                    indent = width
                if width < indent:
                    break
                match = re.match(r"\s*\*{0,2}(\w+)\s*(?:\([^)]*\))?\s*:", entry)
                if width == indent and match:
                    names.add(match.group(1))
            return names
    return None


def _is_generator(function: ast.AST) -> bool:
    return any(isinstance(node, (ast.Yield, ast.YieldFrom)) for node in _own_nodes(function.body))


def _private_module(relative: str) -> bool:
    """A module under any ``_``-prefixed directory or file is private, as pydocstyle reads it;
    nothing in it is public API."""
    parts = Path(relative).with_suffix("").parts
    return any(part.startswith("_") and not _is_dunder(part) for part in parts)


def docstrings(source: Source, params: Mapping) -> Iterator[Hit]:
    if _private_module(source.relative):
        return
    if source.tree.body and not ast.get_docstring(source.tree):
        yield 1, 1, "the module has no docstring"
    for node in source.tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_") and not ast.get_docstring(node):
            yield _at(node, f"public class `{node.name}` has no docstring")
    for function, is_method in _public_functions(source.tree):
        exempt = {"override", "setter", "deleter"} & _decorator_names(function)
        if function.name.startswith("_") or exempt:
            continue
        docstring = ast.get_docstring(function)
        if not docstring:
            yield _at(function, f"public function `{function.name}` has no docstring")
            continue
        documented = _documented_args(docstring)
        if params["args"] and documented is not None:
            names = [arg.arg for arg in _parameters(function, is_method)]
            names += [a.arg for a in (function.args.vararg, function.args.kwarg) if a is not None]
            missing = [name for name in names if name not in documented]
            if missing:
                yield _at(function, f"`Args:` of `{function.name}` omits {', '.join(f'`{m}`' for m in missing)}")
        if params["yields"] and _is_generator(function) and "Returns:" in docstring and "Yields:" not in docstring:
            yield _at(function, f"generator `{function.name}` documents `Returns:` instead of `Yields:`")


def no_string_concat_loop(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            for inner in _own_nodes(node.body):
                if (
                    isinstance(inner, ast.AugAssign)
                    and isinstance(inner.op, ast.Add)
                    and (
                        isinstance(inner.value, ast.JoinedStr)
                        or (isinstance(inner.value, ast.Constant) and isinstance(inner.value.value, str))
                    )
                ):
                    yield _at(inner, "accumulates a string with `+=` inside a loop")


def _is_logger(node: ast.AST) -> bool:
    name = _last_name(node)
    return bool(name) and "log" in name.lower()


def logging_format(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOG_LEVELS
            and _is_logger(node.func.value)
        ):
            continue
        position = 1 if node.func.attr == "log" else 0
        if len(node.args) <= position:
            continue
        message = node.args[position]
        if isinstance(message, ast.JoinedStr):
            yield _at(message, "the logging message is an f-string")
        elif isinstance(message, ast.BinOp) and isinstance(message.op, (ast.Mod, ast.Add)):
            yield _at(message, "the logging message is formatted before the call")
        elif isinstance(message, ast.Call) and _last_name(message.func) == "format":
            yield _at(message, "the logging message is built with `.format()`")


def open_with_context(source: Source, params: Mapping) -> Iterator[Hit]:
    managed = set()
    for node in ast.walk(source.tree):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            managed.update(id(item.context_expr) for item in node.items)
        elif isinstance(node, ast.Call) and _last_name(node.func) in {"enter_context", "closing"}:
            managed.update(id(arg) for arg in node.args)
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Call) and _dotted(node.func) == "open" and id(node) not in managed:
            yield _at(node, "opens a file outside a `with` statement")


def todo_format(source: Source, params: Mapping) -> Iterator[Hit]:
    for line, column, comment in source.comments:
        if _TODO_RE.search(comment) and not _GOOGLE_TODO_RE.search(comment):
            yield line, column + 1, "a TODO without a tracker link in `TODO: <link> - <what>` form"


def naming(source: Source, params: Mapping) -> Iterator[Hit]:
    path = source.root / source.relative
    stem = path.stem
    if (path.parent / "__init__.py").is_file() and not _is_dunder(stem) and not _SNAKE_RE.match(stem):
        yield 1, 1, f"module name `{stem}` is not `lower_with_under`"
    for node in source.tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        for target in targets:
            if isinstance(target, ast.Name) and _MIXED_CASE_RE.match(target.id):
                yield _at(target, f"module-level name `{target.id}` is mixedCase")
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ClassDef) and not _CAP_WORDS_RE.match(node.name):
            yield _at(node, f"class name `{node.name}` is not `CapWords`")
        elif isinstance(node, _FUNCTIONS):
            name = node.name
            dictated = name in _DICTATED_NAMES or name.startswith(("visit_", "depart_"))
            if not _is_dunder(name) and not dictated and not _SNAKE_RE.match(name):
                yield _at(node, f"function name `{name}` is not `lower_with_under`")
            arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            arguments += [a for a in (node.args.vararg, node.args.kwarg) if a is not None]
            for arg in arguments:
                if arg.arg != "_" and not _SNAKE_RE.match(arg.arg):
                    yield _at(arg, f"argument name `{arg.arg}` is not `lower_with_under`")
            own = list(_own_nodes(node.body))
            declared = {name for inner in own if isinstance(inner, (ast.Global, ast.Nonlocal)) for name in inner.names}
            for inner in own:
                if (
                    isinstance(inner, ast.Name)
                    and isinstance(inner.ctx, ast.Store)
                    and inner.id != inner.id.lower()
                    and inner.id not in declared
                ):
                    yield _at(inner, f"local name `{inner.id}` is not lowercase")


def short_names(source: Source, params: Mapping) -> Iterator[Hit]:
    allowed = set(params["allowed"])
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and len(node.id) == 1:
            if node.id not in allowed:
                yield _at(node, f"single-character name `{node.id}`")
        elif isinstance(node, ast.arg) and len(node.arg) == 1 and node.arg not in allowed:
            yield _at(node, f"single-character argument `{node.arg}`")


def function_length(source: Source, params: Mapping) -> Iterator[Hit]:
    limit = params["max_lines"]
    for node in ast.walk(source.tree):
        if isinstance(node, _FUNCTIONS):
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            if length > limit:
                yield _at(node, f"`{node.name}` is {length} lines long, over max_lines {limit}")


def no_blocking_in_async(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for inner in _own_nodes(node.body):
                if isinstance(inner, ast.Call) and _dotted(inner.func) in _BLOCKING_CALLS:
                    yield _at(inner, f"calls blocking `{_dotted(inner.func)}` inside `async def {node.name}`")


def _first_party(source: Source, top: str) -> bool:
    here = (source.root / source.relative).parent
    for base in (source.root, source.root / "src", here):
        if (base / f"{top}.py").is_file() or (base / top).is_dir():
            return True
    return False


def stdlib_only(source: Source, params: Mapping) -> Iterator[Hit]:
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            modules = [node.module]
        else:
            continue
        for module in modules:
            top = module.split(".")[0]
            if top not in sys.stdlib_module_names and not _first_party(source, top):
                yield _at(node, f"imports `{module}`, which is neither the standard library nor the project's own")


RULES: dict[str, Callable[[Source, Mapping], Iterable[Hit]]] = {
    "specific-suppression": specific_suppression,
    "import-modules": import_modules,
    "no-wildcard-import": no_wildcard_import,
    "absolute-imports": absolute_imports,
    "no-bare-except": no_bare_except,
    "no-broad-except": no_broad_except,
    "no-silent-except": no_silent_except,
    "no-assert-validation": no_assert_validation,
    "raise-from": raise_from,
    "exception-suffix": exception_suffix,
    "no-global-statement": no_global_statement,
    "simple-comprehension": simple_comprehension,
    "default-iterator": default_iterator,
    "lambda-use": lambda_use,
    "no-mutable-default": no_mutable_default,
    "none-and-bool-compare": none_and_bool_compare,
    "implicit-false": implicit_false,
    "no-staticmethod": no_staticmethod,
    "no-power-features": no_power_features,
    "annotate-public": annotate_public,
    "explicit-optional": explicit_optional,
    "docstrings": docstrings,
    "no-string-concat-loop": no_string_concat_loop,
    "logging-format": logging_format,
    "open-with-context": open_with_context,
    "todo-format": todo_format,
    "naming": naming,
    "short-names": short_names,
    "function-length": function_length,
    "no-blocking-in-async": no_blocking_in_async,
    "stdlib-only": stdlib_only,
}
