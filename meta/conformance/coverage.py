#!/usr/bin/env python3
"""The coverage gate (design §5, gate 2).

The population is **derived** from the source of the tree under test, never listed by hand:

- ``command:<name>`` — the ``_COMMANDS`` tuple literal of ``src/akmon/cli.py``;
- ``hook:<name>`` — every ``hooks/*.py`` with a ``__main__`` block (the shared core has none);
- ``tool:<rel>`` — every ``tools/**/*.py`` with a ``__main__`` block (``model_routing/init``);
- ``unit:<name>`` — every shared unit table ``units/*.toml`` of the corpus;
- ``code:<code>:<severity>`` — every literal emission site over ``bin/``, ``common/``,
  ``src/akmon/``, ``hooks/`` and ``tools/``: ``self.ok|warn|error("<code>", …)`` and any call
  whose first two positional arguments are a literal severity and a literal code
  (``Finding("error", "check.scope", …)``, ``_finding("warn", "release.check-skipped", …)``).
  A site that emits with a non-literal severity or code is *dynamic*: it must be listed in
  ``coverage.toml [dynamic]`` with a reason, so a new emitter cannot hide codes from the gate.

Coverage **evidence** is derived from each scenario's invocation and recorded expectation, not
from its ``covers`` claims: a cli scenario covers its command, a hook scenario its script, a
tool scenario its tool, a unit scenario its table, and every finding line of ``expected.stdout``
or ``expected.findings`` covers that code at that severity — the runner compares those exactly,
so a line there is real coverage. A ``codex-hook`` scenario's ``hook:<X>`` claim also counts
(the Codex dispatcher routes to X).

Scope: an item tagged in ``coverage.toml [ecosystem]`` is covered by ``shared`` or that
ecosystem's scenarios; every other item is shared and only ``shared`` scenarios cover it.
``[exempt]`` items need no scenario. Claims, exceptions and dynamic entries that name nothing
derived are stale. ``coverage.toml`` therefore holds only the exceptions.

Usage: python3 meta/conformance/coverage.py [--tree REPO]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(CORPUS_ROOT))
sys.path.insert(0, str(CORPUS_ROOT.parents[1]))

from corpus import ECOSYSTEMS, REPO_ROOT, CorpusError, Scenario, load_scenarios  # noqa: E402
from normalize import NORM_VERSION  # noqa: E402

from common.findings import Finding, exit_code, print_findings, severities  # noqa: E402

#: A finding line as the shared envelope renders it; the runner keeps its own copy.
FINDING_LINE = re.compile(r"^(OK|WARN|ERROR) ([a-z][a-z_]*\.[a-z0-9-]+)[ :]")
CODE_RE = re.compile(r"^[a-z][a-z_]*\.[a-z0-9-]+$")
#: The source roots whose literal emission sites make up the ``code:`` population.
CODE_ROOTS = ("bin", "common", "src/akmon", "hooks", "tools")
KIND_ORDER = ("command", "hook", "tool", "unit", "code")
#: The Codex dispatcher: a scenario through it covers the hook its ``covers`` names.
CODEX_DISPATCHER = "codex-hook"


@dataclass(frozen=True)
class Population:
    """What the tree under test ships: items, the codes they carry, and its dynamic emission sites."""

    items: frozenset[str]  # command:x, hook:x, tool:x, unit:x, code:<code>:<severity>
    dynamic: frozenset[str] = frozenset()  # <relpath>::<qualname>

    @property
    def codes(self) -> frozenset[str]:
        """Every derived finding code, whatever its severity."""
        return frozenset(item.split(":")[1] for item in self.items if item.startswith("code:"))


@dataclass(frozen=True)
class Exceptions:
    """``coverage.toml``: ecosystem ownership, exemptions, and the reviewed dynamic sites."""

    ecosystem: dict[str, str] = field(default_factory=dict)  # item, or code:<code> for every severity -> owner
    exempt: dict[str, str] = field(default_factory=dict)  # item -> reason
    dynamic: dict[str, str] = field(default_factory=dict)  # site -> reason

    def owner(self, item: str) -> str | None:
        """The ecosystem that owns ``item``: its own entry, else its code's whole-code entry."""
        if item in self.ecosystem:
            return self.ecosystem[item]
        if item.startswith("code:"):
            return self.ecosystem.get(item.rsplit(":", 1)[0])
        return None

    def owned_codes(self) -> frozenset[str]:
        """Codes an ecosystem owns whole (``code:<code>`` entries): their lines are not shared spec."""
        return frozenset(key.split(":")[1] for key in self.ecosystem if key.startswith("code:") and key.count(":") == 1)


# --- population ---------------------------------------------------------------------


def _has_main_block(path: Path) -> bool:
    """True when the module has a top-level ``if __name__ == "__main__":`` block."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        test = node.test if isinstance(node, ast.If) else None
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
        ):
            return True
    return False


def _commands(repo: Path) -> set[str]:
    """The string elements of the ``_COMMANDS`` tuple literal in ``src/akmon/cli.py``."""
    path = repo / "src" / "akmon" / "cli.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if any(isinstance(t, ast.Name) and t.id == "_COMMANDS" for t in targets) and isinstance(
            node.value, (ast.Tuple, ast.List)
        ):
            return {
                f"command:{elt.value}"
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
    raise CorpusError(f"{path}: no _COMMANDS tuple literal to derive the command population from")


def _hooks(repo: Path) -> set[str]:
    return {f"hook:{path.stem}" for path in sorted((repo / "hooks").glob("*.py")) if _has_main_block(path)}


def _tools(repo: Path) -> set[str]:
    base = repo / "tools"
    return {
        f"tool:{path.relative_to(base).with_suffix('').as_posix()}"
        for path in sorted(base.rglob("*.py"))
        if _has_main_block(path)
    }


def _units(units_dir: Path) -> set[str]:
    return {f"unit:{path.stem}" for path in sorted(units_dir.glob("*.toml"))}


def _str_constant(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _callee_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


class _EmissionVisitor(ast.NodeVisitor):
    """Collects one module's literal ``code:`` items and its dynamic emission sites."""

    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.scope: list[str] = []
        self.items: set[str] = set()
        self.dynamic: set[str] = set()

    def _nested(self, node: ast.AST) -> None:
        self.scope.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _nested  # noqa: N815

    def _site(self) -> str:
        return f"{self.relpath}::{'.'.join(self.scope) or '<module>'}"

    def visit_Call(self, node: ast.Call) -> None:
        positional = [arg for arg in node.args if not isinstance(arg, ast.Starred)]
        starred = len(positional) != len(node.args)
        first = _str_constant(node.args[0]) if node.args and not starred else None
        second = _str_constant(node.args[1]) if len(node.args) > 1 and not starred else None
        func = node.func
        name = _callee_name(func)
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
            and func.attr in severities()
        ):
            # Shape (a): a severity method on the checker itself.
            if first is None:
                self.dynamic.add(self._site())
            elif CODE_RE.match(first):
                self.items.add(f"code:{first}:{func.attr}")
        elif first in severities() and second is not None and CODE_RE.match(second):
            # Shape (b): any call opening with a literal severity and a literal code.
            self.items.add(f"code:{second}:{first}")
        elif (name == "Finding" or name.endswith("finding")) and (first is None or second is None):
            # A finding constructor or helper fed a non-literal severity or code.
            self.dynamic.add(self._site())
        self.generic_visit(node)


def _emissions(repo: Path) -> tuple[set[str], set[str]]:
    items: set[str] = set()
    dynamic: set[str] = set()
    for root in CODE_ROOTS:
        for path in sorted((repo / root).rglob("*.py")):
            visitor = _EmissionVisitor(path.relative_to(repo).as_posix())
            visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
            items |= visitor.items
            dynamic |= visitor.dynamic
    return items, dynamic


def derive_population(repo: Path, units_dir: Path | None = None) -> Population:
    """The population of the tree at ``repo``; unit tables come from the corpus (``units_dir``)."""
    codes, dynamic = _emissions(repo)
    items = _commands(repo) | _hooks(repo) | _tools(repo) | _units(units_dir or CORPUS_ROOT / "units") | codes
    return Population(items=frozenset(items), dynamic=frozenset(dynamic))


# --- exceptions ---------------------------------------------------------------------


def load_exceptions(path: Path | None = None) -> Exceptions:
    """Parse ``coverage.toml``; a malformed entry is refused like a malformed scenario."""
    path = path or CORPUS_ROOT / "coverage.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    unknown = set(data) - {"ecosystem", "exempt", "dynamic"}
    if unknown:
        raise CorpusError(f"{path}: unknown tables {sorted(unknown)}; expected ecosystem, exempt, dynamic")
    ecosystem: dict[str, str] = {}
    for item, entry in data.get("ecosystem", {}).items():
        tag = entry.get("ecosystem") if isinstance(entry, dict) else None
        if tag not in ECOSYSTEMS or tag == "shared" or not str(entry.get("reason", "")).strip():
            raise CorpusError(f"{path}: [ecosystem] {item!r} needs ecosystem = python|node and a reason")
        ecosystem[item] = tag
    for table in ("exempt", "dynamic"):
        for key, reason in data.get(table, {}).items():
            if not isinstance(reason, str) or not reason.strip():
                raise CorpusError(f"{path}: [{table}] {key!r} needs a reason string")
    return Exceptions(ecosystem=ecosystem, exempt=dict(data.get("exempt", {})), dynamic=dict(data.get("dynamic", {})))


# --- evidence -----------------------------------------------------------------------


def _finding_lines(scenario: Scenario) -> list[str]:
    expected = scenario.expected
    lines = list(expected.findings or ())
    if expected.stdout is not None:
        lines.extend(expected.stdout.splitlines())
    return lines


def scenario_evidence(scenario: Scenario) -> set[str]:
    """The population items a scenario's invocation and recorded expectation actually exercise."""
    run = scenario.run
    evidence: set[str] = set()
    if scenario.kind == "cli" and run.argv:
        evidence.add(f"command:{run.argv[0]}")
    elif scenario.kind == "hook" and run.script:
        evidence.add(f"hook:{run.script}")
        if run.script == CODEX_DISPATCHER:
            evidence.update(item for item in scenario.covers if item.startswith("hook:"))
    elif scenario.kind == "tool" and run.tool:
        evidence.add(f"tool:{run.tool.removesuffix('.py')}")
    elif scenario.kind == "unit" and run.table:
        evidence.add(f"unit:{Path(run.table).stem}")
    for line in _finding_lines(scenario):
        if match := FINDING_LINE.match(line):
            evidence.add(f"code:{match.group(2)}:{match.group(1).lower()}")
    return evidence


# --- the gate -----------------------------------------------------------------------


def _claim_is_derived(claim: str, population: Population) -> bool:
    kind, _, name = claim.partition(":")
    if kind == "code":
        return name in population.codes
    return claim in population.items


def _stale(target: str, message: str, fix: str) -> Finding:
    return Finding("error", "conformance.coverage-stale", message, target, fix)


def _stale_findings(population: Population, exceptions: Exceptions, scenarios: list[Scenario]) -> list[Finding]:
    findings = [
        _stale(scenario.id, f"covers claim {claim} names no derived population item", "Fix or drop the claim.")
        for scenario in scenarios
        for claim in scenario.covers
        if not _claim_is_derived(claim, population)
    ]
    for table, entries in (("ecosystem", exceptions.ecosystem), ("exempt", exceptions.exempt)):
        findings.extend(
            _stale(item, f"coverage.toml [{table}] entry names no derived population item", "Drop the entry.")
            for item in sorted(entries)
            if item not in population.items
            and not (table == "ecosystem" and item.count(":") == 1 and _claim_is_derived(item, population))
        )
    findings.extend(
        _stale(site, "coverage.toml [dynamic] entry matches no dynamic emission site", "Drop the entry.")
        for site in sorted(exceptions.dynamic)
        if site not in population.dynamic
    )
    return findings


def _dynamic_findings(population: Population, exceptions: Exceptions) -> list[Finding]:
    return [
        Finding(
            "error",
            "conformance.population-dynamic",
            "emission site passes a non-literal severity or code, so its codes cannot be derived",
            site,
            "Emit literal codes, or list the site in coverage.toml [dynamic] with the reason it hides none.",
        )
        for site in sorted(population.dynamic)
        if site not in exceptions.dynamic
    ]


def _sort_key(item: str) -> tuple[int, str]:
    return KIND_ORDER.index(item.split(":", 1)[0]), item


def _missing_findings(population: Population, exceptions: Exceptions, scenarios: list[Scenario]) -> list[Finding]:
    covered: dict[str, set[str]] = {ecosystem: set() for ecosystem in ECOSYSTEMS}
    for scenario in scenarios:
        covered[scenario.ecosystem] |= scenario_evidence(scenario)
    findings: list[Finding] = []
    for item in sorted(population.items - set(exceptions.exempt), key=_sort_key):
        owner = exceptions.owner(item)
        if item in covered["shared"] or (owner and item in covered[owner]):
            continue
        scope = f"shared or {owner}" if owner else "shared"
        findings.append(
            Finding(
                "error",
                "conformance.coverage-missing",
                f"{item} has no {scope} scenario",
                item,
                "Add a scenario whose run or expected finding lines exercise it, or exempt it in coverage.toml.",
            )
        )
    return findings


def gate(population: Population, exceptions: Exceptions, scenarios: list[Scenario]) -> list[Finding]:
    """The gate's findings over explicit inputs: missing, stale, dynamic — or the single ok finding."""
    findings = [
        *_missing_findings(population, exceptions, scenarios),
        *_stale_findings(population, exceptions, scenarios),
        *_dynamic_findings(population, exceptions),
    ]
    if findings:
        return findings
    counts = ", ".join(
        f"{sum(item.startswith(f'{kind}:') for item in population.items)} {kind}s" for kind in KIND_ORDER
    )
    return [
        Finding(
            "ok",
            "conformance.coverage",
            f"all {len(population.items)} derived population items covered ({counts}; "
            f"{len(exceptions.exempt)} exempt) by {len(scenarios)} scenarios (corpus v{NORM_VERSION})",
            "",
            "Keep every command, hook, tool, unit and finding code inside the corpus.",
        )
    ]


def check_coverage(repo: Path | None = None) -> list[Finding]:
    """The gate over the tree at ``repo`` (default: this repository) and the corpus's scenarios."""
    # Tolerate unseeded skeletons: a mid-seed corpus must not crash the coverage leg; an
    # unseeded scenario carries no expectation, so it contributes only its invocation.
    return gate(derive_population(repo or REPO_ROOT), load_exceptions(), load_scenarios(strict_seeded=False))


def main(argv: list[str] | None = None) -> int:
    """Parse the gate's CLI, run it against the corpus, and print the findings."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tree", default=str(REPO_ROOT))
    args = parser.parse_args(argv)
    findings = check_coverage(Path(args.tree).resolve())
    print_findings(findings)
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
