"""Contract tests for the conformance coverage gate (C101, design §5 gate 2).

Two layers. The seeded rejections run against a synthetic tree and synthetic scenarios, so each
one breaks exactly one relation — an uncovered error side, a python-tagged scenario standing in
for a shared item, an unlisted dynamic emitter, a stale entry — and the assertion names the code
and the item. The shipped-contract test runs the derivation over akmon's own tree and pins items a
hand-kept list once lost (the release_check codes, the error side of a consumer-path check).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SPEC = importlib.util.spec_from_file_location(
    "conformance_coverage", _AKMON / "meta" / "conformance" / "coverage.py"
)
coverage = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = coverage
_SPEC.loader.exec_module(coverage)

from corpus import ExpectedSpec, FixtureSpec, RunSpec, Scenario  # noqa: E402

_CLI = '''"""Fixture CLI."""

_COMMANDS = ("sync", "verify")
'''

_HOOK = '''"""Fixture hook entry."""


def main():
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

_CORE = '''"""Fixture hook core: shared code, no entry point."""


def helper():
    return 1
'''

_TOOL = '''"""Fixture tool."""

if __name__ == "__main__":
    print("tool")
'''

_VERIFY = '''"""Fixture verifier: literal emissions plus one reviewed dynamic wrapper."""

from common.findings import Finding


class Verifier:
    def __init__(self):
        self.findings = []

    def ok(self, code, message, *, fix):
        self.findings.append(Finding("ok", code, message, "", fix))

    def error(self, code, message, *, fix):
        self.findings.append(Finding("error", code, message, "", fix))

    def check_layout(self, parser):
        if parser:
            self.ok("layout.consumer-path", "present", fix="Keep it.")
        else:
            self.error("layout.consumer-path", "missing", fix="Create it.")
        parser.error("argparse text, never a finding")
'''

_SYNC = '''"""Fixture sync: a literal Finding constructor."""

from common.findings import Finding

STALE = Finding("warn", "sync.stale-generated", "stale", "", "Run sync.")
'''

_DYNAMIC = '''"""Fixture wrapper nobody reviewed."""


def emit(severity, code):
    return make_finding(severity, code, "m", "", "Fix it.")
'''


def _tree(tmp_path: Path, *, dynamic_emitter: bool = False) -> Path:
    for relative, content in {
        "src/akmon/cli.py": _CLI,
        "hooks/role-on-code.py": _HOOK,
        "hooks/hook_core.py": _CORE,
        "tools/release/release_check.py": _TOOL,
        "bin/verify.py": _VERIFY,
        "bin/sync.py": _SYNC,
        "common/__init__.py": "",
        "units/glob.toml": "",
    }.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if dynamic_emitter:
        (tmp_path / "common" / "emit.py").write_text(_DYNAMIC, encoding="utf-8")
    return tmp_path


def _population(tmp_path: Path, **kwargs) -> coverage.Population:
    root = _tree(tmp_path, **kwargs)
    return coverage.derive_population(root, units_dir=root / "units")


_REVIEWED = {"bin/verify.py::Verifier.ok": "wrapper", "bin/verify.py::Verifier.error": "wrapper"}


def _exceptions(**kwargs) -> coverage.Exceptions:
    kwargs.setdefault("dynamic", dict(_REVIEWED))
    return coverage.Exceptions(**kwargs)


def _scenario(
    sid: str,
    kind: str,
    *,
    ecosystem: str = "shared",
    covers: tuple[str, ...] = (),
    **fields: object,
) -> Scenario:
    """A synthetic scenario; ``stdout``/``findings`` go to its expectation, the rest to its run."""
    expected = {key: fields.pop(key) for key in ("stdout", "findings") if key in fields}
    return Scenario(
        id=sid,
        ecosystem=ecosystem,
        kind=kind,
        covers=covers,
        fixture=FixtureSpec(),
        env={},
        run=RunSpec(**fields),
        expected=ExpectedSpec(**expected),
    )


def _full_corpus() -> list[Scenario]:
    """Scenarios that cover the synthetic population completely, all shared."""
    return [
        _scenario(
            "cli/verify-ok",
            "cli",
            argv=("verify",),
            stdout="OK layout.consumer-path: present → Keep it.\nsummary line\n",
        ),
        _scenario(
            "cli/verify-missing",
            "cli",
            argv=("verify",),
            findings=("ERROR layout.consumer-path: missing → Create it.",),
        ),
        _scenario("cli/sync-stale", "cli", argv=("sync",), findings=("WARN sync.stale-generated: stale → Run sync.",)),
        _scenario("hooks/role", "hook", script="role-on-code"),
        _scenario("tools/release", "tool", tool="release/release_check", stdout="done\n"),
        _scenario("units/glob", "unit", probe="glob", table="glob.toml"),
    ]


def _by_code(findings: list) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for finding in findings:
        grouped.setdefault(finding.code, []).append(finding.target)
    return grouped


def test_population_is_derived_from_source(tmp_path: Path) -> None:
    population = _population(tmp_path)
    assert population.items == {
        "command:sync",
        "command:verify",
        "hook:role-on-code",
        "tool:release/release_check",
        "unit:glob",
        "code:layout.consumer-path:ok",
        "code:layout.consumer-path:error",
        "code:sync.stale-generated:warn",
    }
    assert population.dynamic == {"bin/verify.py::Verifier.ok", "bin/verify.py::Verifier.error"}


def test_complete_corpus_passes(tmp_path: Path) -> None:
    findings = coverage.gate(_population(tmp_path), _exceptions(), _full_corpus())
    assert [(f.severity, f.code) for f in findings] == [("ok", "conformance.coverage")]
    assert "8 derived population items" in findings[0].message
    assert "6 scenarios" in findings[0].message


def test_uncovered_error_side_is_missing(tmp_path: Path) -> None:
    scenarios = [s for s in _full_corpus() if s.id != "cli/verify-missing"]
    findings = coverage.gate(_population(tmp_path), _exceptions(), scenarios)
    assert _by_code(findings) == {"conformance.coverage-missing": ["code:layout.consumer-path:error"]}
    assert findings[0].message == "code:layout.consumer-path:error has no shared scenario"


def test_covers_claim_alone_is_not_evidence(tmp_path: Path) -> None:
    scenarios = [s for s in _full_corpus() if s.id != "cli/verify-missing"]
    scenarios.append(
        _scenario("cli/claims-only", "cli", argv=("verify",), covers=("code:layout.consumer-path",), stdout="x\n")
    )
    findings = coverage.gate(_population(tmp_path), _exceptions(), scenarios)
    assert _by_code(findings) == {"conformance.coverage-missing": ["code:layout.consumer-path:error"]}


def test_python_scenario_does_not_cover_shared_item(tmp_path: Path) -> None:
    scenarios = [s for s in _full_corpus() if s.id != "cli/sync-stale"]
    scenarios.append(
        _scenario(
            "cli/sync-stale-py",
            "cli",
            ecosystem="python",
            argv=("sync",),
            findings=("WARN sync.stale-generated: stale → Run sync.",),
        )
    )
    findings = coverage.gate(_population(tmp_path), _exceptions(), scenarios)
    assert _by_code(findings) == {"conformance.coverage-missing": ["command:sync", "code:sync.stale-generated:warn"]}


def test_ecosystem_item_is_covered_by_its_ecosystem(tmp_path: Path) -> None:
    scenarios = [s for s in _full_corpus() if s.id != "cli/sync-stale"]
    scenarios.append(
        _scenario(
            "cli/sync-stale-py",
            "cli",
            ecosystem="python",
            argv=("sync",),
            findings=("WARN sync.stale-generated: stale → Run sync.",),
        )
    )
    tagged = {"command:sync": "python", "code:sync.stale-generated:warn": "python"}
    findings = coverage.gate(_population(tmp_path), _exceptions(ecosystem=tagged), scenarios)
    assert [f.code for f in findings] == ["conformance.coverage"]
    # A node scenario does not stand in for a python-owned item.
    node = [s for s in scenarios if s.id != "cli/sync-stale-py"]
    node.append(_scenario("cli/sync-node", "cli", ecosystem="node", argv=("sync",), stdout="x\n"))
    node.append(_scenario("cli/sync-any", "cli", argv=("sync",), stdout="x\n"))
    findings = coverage.gate(_population(tmp_path), _exceptions(ecosystem=tagged), node)
    assert [f.message for f in findings] == ["code:sync.stale-generated:warn has no shared or python scenario"]


def test_exempt_item_needs_no_scenario(tmp_path: Path) -> None:
    scenarios = [s for s in _full_corpus() if s.id != "cli/verify-missing"]
    exempt = {"code:layout.consumer-path:error": "reason"}
    findings = coverage.gate(_population(tmp_path), _exceptions(exempt=exempt), scenarios)
    assert [f.code for f in findings] == ["conformance.coverage"]


def test_unlisted_dynamic_site_is_refused(tmp_path: Path) -> None:
    findings = coverage.gate(_population(tmp_path, dynamic_emitter=True), _exceptions(), _full_corpus())
    assert _by_code(findings) == {"conformance.population-dynamic": ["common/emit.py::emit"]}


def test_stale_dynamic_entry_is_refused(tmp_path: Path) -> None:
    dynamic = {**_REVIEWED, "bin/verify.py::Verifier.warn": "wrapper"}
    findings = coverage.gate(_population(tmp_path), _exceptions(dynamic=dynamic), _full_corpus())
    assert _by_code(findings) == {"conformance.coverage-stale": ["bin/verify.py::Verifier.warn"]}


def test_stale_exemption_and_ecosystem_entry_are_refused(tmp_path: Path) -> None:
    exceptions = _exceptions(
        exempt={"code:codex.host-trust:warn": "gone"},
        ecosystem={"code:layout.consumer-path:warn": "python"},
    )
    findings = coverage.gate(_population(tmp_path), exceptions, _full_corpus())
    assert _by_code(findings) == {
        "conformance.coverage-stale": ["code:layout.consumer-path:warn", "code:codex.host-trust:warn"]
    }


def test_stale_claim_is_refused(tmp_path: Path) -> None:
    scenarios = _full_corpus()
    scenarios.append(
        _scenario("cli/stale", "cli", argv=("verify",), covers=("code:layout.retired", "hook:gone"), stdout="x\n")
    )
    findings = coverage.gate(_population(tmp_path), _exceptions(), scenarios)
    assert _by_code(findings) == {"conformance.coverage-stale": ["cli/stale", "cli/stale"]}


def test_code_claim_names_any_severity(tmp_path: Path) -> None:
    scenarios = _full_corpus()
    scenarios.append(
        _scenario(
            "cli/claim", "cli", argv=("sync",), covers=("code:sync.stale-generated", "command:sync"), stdout="x\n"
        )
    )
    findings = coverage.gate(_population(tmp_path), _exceptions(), scenarios)
    assert [f.code for f in findings] == ["conformance.coverage"]


def test_codex_dispatcher_claim_counts(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "hooks" / "codex-hook.py").write_text(_HOOK, encoding="utf-8")
    population = coverage.derive_population(root, units_dir=root / "units")
    scenarios = [s for s in _full_corpus() if s.id != "hooks/role"]
    scenarios.append(_scenario("hooks/codex-role", "hook", script="codex-hook", covers=("hook:role-on-code",)))
    assert coverage.scenario_evidence(scenarios[-1]) == {"hook:codex-hook", "hook:role-on-code"}
    findings = coverage.gate(population, _exceptions(), scenarios)
    assert [f.code for f in findings] == ["conformance.coverage"]
    # The same claim from any other hook's scenario is not evidence.
    other = _scenario("hooks/other", "hook", script="gate-audit", covers=("hook:role-on-code",))
    assert coverage.scenario_evidence(other) == {"hook:gate-audit"}


def test_real_tree_derivation() -> None:
    population = coverage.derive_population(_AKMON)
    assert "code:layout.consumer-path:error" in population.items
    release = {item for item in population.items if item.startswith("code:release.")}
    assert {item.split(":")[1] for item in release} == {
        "release.changelog-window",
        "release.check-skipped",
        "release.retag",
        "release.tag-spelling",
        "release.undocumented-tag",
        "release.version-literals",
    }
    commands = {item for item in population.items if item.startswith("command:")}
    assert commands == {
        f"command:{name}" for name in ("init", "update", "sync", "verify", "check", "path", "hook", "version")
    }
    # Every dynamic site in the shipped tree is reviewed, and every review names a live site.
    exceptions = coverage.load_exceptions()
    assert set(exceptions.dynamic) == set(population.dynamic)
