#!/usr/bin/env python3
"""Corpus loading and fixture building (C101).

A *scenario* is one process-boundary test case: it names a fixture (a consumer project the
implementation under test runs in), an invocation (hook payload, CLI argv, tool argv, or a
unit table), and the exact normalized expectations. Scenario files are TOML, one per file,
under ``scenarios/<area>/``; their ``id`` is the file path without extension and directory.

A *snapshot* is the controlled view of the standard tree a consumer sees: the corpus copies a
curated file list out of the repository under test, so the generated outputs a scenario
asserts on depend on corpus-controlled content, not on whatever else happens to sit in the
checkout (scratch files, a worktree's in-progress docs). The list is normative — changing it
is a corpus change. A mounted consumer links the snapshot as its mount; a package-mode
consumer runs the snapshot's own CLI, which resolves the snapshot as its embedded tree.

An *attach* says how the consumer is connected to the implementation under test
(ADR 0020 D02): ``native`` is the implementation's own package mode (Python: a
``pyproject.toml`` dev pin and the ``.venv/bin/akmon`` launcher; Node: ``package.json`` and
``node_modules/akmon``), ``mount`` is a mounted mode — Python only, so a ``shared`` scenario
may not use it — and ``none`` connects nothing. The files of a ``native`` attach live in
``fixtures/attach/<layer>/`` and are laid over the base fixture before the scenario's own files.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = CORPUS_ROOT.parents[1]

KINDS = ("hook", "cli", "tool", "unit")
ECOSYSTEMS = ("shared", "python", "node")
ATTACHES = ("native", "mount", "none")
WARMUPS = ("after", "before", "none")
#: The fixture layers a ``native`` attach lays over the base, per implementation: what every
#: package mode shares (the package-mode AGENTS.md block), then the ecosystem's own carrier.
NATIVE_LAYERS = {"python": ("package", "python"), "node": ("package", "node")}
#: The Python carrier's dev pin (``{{version}}`` materializes to the live version).
PYTHON_PIN = '[project]\nname = "consumer"\nversion = "0.1.0"\n\n[dependency-groups]\ndev = ["akmon=={{version}}"]\n'
COVER_RE = r"^(command|hook|tool|code|unit):[a-z0-9][a-z0-9_./-]*$"


class CorpusError(ValueError):
    """A scenario file the corpus refuses to run."""


@dataclass(frozen=True)
class FixtureSpec:
    """How one scenario's consumer project is built: base fixture, files, and run flags."""

    name: str = "base"
    files: dict[str, str] = field(default_factory=dict)  # path -> content (tokens materialized)
    remove: tuple[str, ...] = ()  # base paths deleted before the run
    branch: str = "main"
    attach: str = "native"  # native | mount | none (module docstring)
    # The implementation's own sync (write) into the fixture: "after" the scenario's files (a
    # synced project), "before" them (a synced project the files then break), or "none".
    warmup: str = "none"
    repo: bool = False  # build a local standard-tree git repo tagged v<version> for --repo runs
    git: bool = True  # False: no git repo at all (the check.scope scenarios' non-work-tree)
    tmp_files: dict[str, str] = field(default_factory=dict)  # seeded into the run tempdir before the process starts
    tree_files: dict[str, str] = field(default_factory=dict)  # tree-side overrides: scenario-local snapshot copy
    tree_remove: tuple[str, ...] = ()  # snapshot paths deleted from that private copy
    tags: tuple[str, ...] = ()  # git tags on the fixture's baseline commit


@dataclass(frozen=True)
class RunSpec:
    """How one scenario's process boundary is invoked: hook, CLI, tool, or unit probe."""

    script: str = ""  # hook: hooks/<script>.py (python) | js/hooks/<script>.mjs (node)
    args: tuple[str, ...] = ()
    payload: dict | None = None  # hook: the stdin JSON document
    argv: tuple[str, ...] = ()  # cli: console argv; tool: argv after the tool path
    tool: str = ""  # tool: tools/<tool>.py
    probe: str = ""  # unit: probe subcommand
    table: str = ""  # unit: units/<table>


@dataclass(frozen=True)
class ExpectedSpec:
    """One scenario's exact normalized expectations, seeded by ``--record`` and reviewed by a human."""

    exit: int = 0
    stdout: str | None = None  # exact, normalized
    stdout_json: dict | None = None  # parsed-JSON equality, normalized string leaves
    stderr: str | None = None  # exact, normalized
    stderr_contains: tuple[str, ...] = ()  # normalized substrings; only for text an argument parser owns
    findings: tuple[str, ...] | None = None  # every finding line but ecosystem-owned codes', in output order
    files: dict[str, str] = field(default_factory=dict)  # rel path -> exact content, or ref:tree:<path>
    file_absent: tuple[str, ...] = ()
    seeded: bool = True  # False = a skeleton awaiting its first --record seeding


@dataclass(frozen=True)
class Scenario:
    """One conformance scenario: its id, the fixture, the invocation, and the expectations."""

    id: str
    ecosystem: str
    kind: str
    covers: tuple[str, ...]
    fixture: FixtureSpec
    env: dict[str, str]
    run: RunSpec
    expected: ExpectedSpec


def _parse_fixture(path: Path, ecosystem: str, data: dict) -> FixtureSpec:
    """The [fixture] table, with its defaults; a mounted attach is refused on a non-Python scenario."""
    attach = data.get("attach", "native")
    if attach not in ATTACHES:
        raise CorpusError(f"{path}: fixture.attach must be one of {ATTACHES}")
    if attach == "mount" and ecosystem != "python":
        raise CorpusError(f"{path}: a mounted attach is Python-only (ADR 0020 D02); tag the scenario python")
    # A native consumer is a synced one unless the scenario says otherwise.
    warmup = data.get("warmup", "after" if attach == "native" else "none")
    warmup = {True: "after", False: "none"}.get(warmup, warmup)
    if warmup not in WARMUPS:
        raise CorpusError(f"{path}: fixture.warmup must be one of {WARMUPS} (or true/false)")
    return FixtureSpec(
        name=data.get("name", "base"),
        files=dict(data.get("files", {})),
        remove=tuple(data.get("remove", ())),
        branch=data.get("branch", "main"),
        attach=attach,
        warmup=warmup,
        repo=data.get("repo", False),
        git=data.get("git", True),
        tmp_files=dict(data.get("tmp_files", {})),
        tree_files=dict(data.get("tree_files", {})),
        tree_remove=tuple(data.get("tree_remove", ())),
        tags=tuple(data.get("tags", ())),
    )


def _parse_run(path: Path, kind: str, data: dict) -> RunSpec:
    """The [run] table, checked for the invocation fields the scenario's kind requires."""
    run = RunSpec(
        script=data.get("script", ""),
        args=tuple(data.get("args", ())),
        payload=data.get("payload"),
        argv=tuple(data.get("argv", ())),
        tool=data.get("tool", ""),
        probe=data.get("probe", ""),
        table=data.get("table", ""),
    )
    if kind == "hook" and not run.script:
        raise CorpusError(f"{path}: a hook scenario needs run.script")
    if kind == "cli" and not run.argv:
        raise CorpusError(f"{path}: a cli scenario needs run.argv")
    if kind == "tool" and not run.tool:
        raise CorpusError(f"{path}: a tool scenario needs run.tool")
    if kind == "unit" and not (run.probe and run.table):
        raise CorpusError(f"{path}: a unit scenario needs run.probe and run.table")
    return run


def _asserts_only_exit_code(expected: ExpectedSpec, kind: str) -> bool:
    """True when a seeded non-unit scenario pins no observable beyond the exit code."""
    return (
        kind != "unit"
        and expected.seeded
        and expected.stdout is None
        and expected.stdout_json is None
        and expected.stderr is None
        and not expected.stderr_contains
        and expected.findings is None
        and not expected.files
    )


def _parse_expected(path: Path, kind: str, *, strict_seeded: bool, data: dict) -> ExpectedSpec:
    """The [expected] table; its presence is what makes a scenario seeded."""
    expected_data = data.get("expected", {})
    expected = ExpectedSpec(
        exit=int(expected_data.get("exit", 0)),
        stdout=expected_data.get("stdout"),
        stdout_json=expected_data.get("stdout_json"),
        stderr=expected_data.get("stderr"),
        stderr_contains=tuple(expected_data.get("stderr_contains", ())),
        findings=tuple(expected_data["findings"]) if "findings" in expected_data else None,
        files=dict(expected_data.get("files", {})),
        file_absent=tuple(expected_data.get("file_absent", ())),
        seeded="expected" in data,
    )
    if sum(value is not None for value in (expected.stdout, expected.stdout_json, expected.findings)) > 1:
        raise CorpusError(f"{path}: expected.stdout, expected.stdout_json and expected.findings are mutually exclusive")
    if expected.stderr is not None and expected.stderr_contains:
        raise CorpusError(f"{path}: expected.stderr and expected.stderr_contains are mutually exclusive")
    if strict_seeded and kind != "unit" and not expected.seeded:
        raise CorpusError(f"{path}: not seeded (no [expected] table); run the runner with --record and review")
    if _asserts_only_exit_code(expected, kind):
        raise CorpusError(f"{path}: a scenario asserts nothing beyond its exit code")
    return expected


def load_scenario(path: Path, *, strict_seeded: bool = True) -> Scenario:
    """Parse and validate one scenario file.

    ``strict_seeded=False`` tolerates skeletons (no ``[expected]`` table) — the seed pass
    of a ``--record`` run; every other load refuses an unseeded scenario loudly.
    """
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    scenario_id = str(path.relative_to(CORPUS_ROOT / "scenarios").with_suffix(""))
    if data.get("id") != scenario_id:
        raise CorpusError(f"{path}: id {data.get('id')!r} does not match its file path {scenario_id!r}")
    ecosystem = data.get("ecosystem", "shared")
    if ecosystem not in ECOSYSTEMS:
        raise CorpusError(f"{path}: ecosystem must be one of {ECOSYSTEMS}")
    kind = data.get("kind")
    if kind not in KINDS:
        raise CorpusError(f"{path}: kind must be one of {KINDS}")
    covers = tuple(data.get("covers", ()))
    for item in covers:
        if not re.match(COVER_RE, item):
            raise CorpusError(f"{path}: covers entry {item!r} is not a population item (kind:name)")
    return Scenario(
        id=str(scenario_id),
        ecosystem=ecosystem,
        kind=kind,
        covers=covers,
        fixture=_parse_fixture(path, ecosystem, data.get("fixture", {})),
        env=dict(data.get("env", {})),
        run=_parse_run(path, kind, data.get("run", {})),
        expected=_parse_expected(path, kind, strict_seeded=strict_seeded, data=data),
    )


def load_scenarios(area: str | None = None, *, strict_seeded: bool = True) -> list[Scenario]:
    """Every scenario under ``scenarios/`` (optionally one area), in path order."""
    base = CORPUS_ROOT / "scenarios"
    areas = [area] if area else sorted(p.name for p in base.iterdir() if p.is_dir())
    found: list[Scenario] = []
    for one in areas:
        found.extend(load_scenario(path, strict_seeded=strict_seeded) for path in sorted((base / one).glob("*.toml")))
    return found


# --- the snapshot: the controlled standard tree a consumer sees ---------------------

#: Normative file list, relative to the repository under test. Everything a consumer's
#: sync/verify/hooks/tools read from the standard tree, plus the CLI a package-mode consumer
#: runs. Curated like ``self_ci._make_fixture``'s: small enough to reason about, complete
#: enough that a healthy fixture passes.
SNAPSHOT_FILES = (
    "src/akmon/__init__.py",
    "src/akmon/cli.py",
    "src/akmon/_init.py",
    "src/akmon/_tree.py",
    "src/akmon/_update.py",
    "src/akmon/init.json",
    "src/akmon/update.json",
    "src/akmon/cli.json",
    "README.md",
    "BOOTSTRAP.md",
    "ARCHETYPES.md",
    "CHANGELOG.md",
    "MODEL.md",
    "CAPABILITIES.md",
    ".gitignore",
    "roles/README.md",
    "roles/review.md",
    "roles/architect.md",
    "roles/engineer.md",
    "roles/learn.md",
    "roles/release.md",
    "guardrails/_common.md",
    "pipelines/pre-commit.md",
    "pipelines/code-flow.md",
    "pipelines/design-flow.md",
    "pipelines/release.md",
    "pipelines/tasks.md",
    "profiles/python.md",
    "profiles/ruff.toml",
    "common/__init__.py",
    "common/always_loaded.json",
    "common/always_loaded.py",
    "common/codex_hooks.json",
    "common/codex_hooks.py",
    "common/findings.json",
    "common/findings.py",
    "common/jsondata.py",
    "common/markers.json",
    "common/markers.py",
    "common/materialization.json",
    "common/materialization.py",
    "common/check_runner.json",
    "common/check_runner.py",
    "common/project_root.py",
    "common/record.py",
    "common/runtime.json",
    "common/runtime.py",
    "common/versions.py",
    "bin/check.py",
    "bin/sync.py",
    "bin/verify.py",
    "bin/verify.json",
    "bin/sync.json",
    "hooks/vocabulary.json",
    "hooks/hook_core.json",
    "hooks/delegation_log.json",
    "hooks/codex_hook.json",
    "tools/model_routing/registry.json",
    "tools/model_routing/agents.json",
    "tools/model_routing/gate.json",
    "tools/model_routing/second_opinion.json",
    "tools/model_routing/stats.json",
    "tools/model_routing/routing.py",
    "tools/model_routing/init.py",
    "tools/model_routing/second_opinion.py",
    "tools/model_routing/gate_pack.py",
    "tools/model_routing/coverage_map.py",
    "tools/model_routing/stats.py",
    "tools/release/release.json",
    "tools/release/release_check.py",
    "tools/tasks/archive.py",
    "tools/tasks/archive.json",
)


def snapshot_hooks(repo: Path) -> list[str]:
    """The hook files the snapshot carries: exactly the wired population (bin/verify.py)."""
    sys.path.insert(0, str(repo / "bin"))
    try:
        import verify as verify_tool  # noqa: PLC0415 — the wired list has one owner

        return [f"hooks/{name}" for name in verify_tool.wired_hook_scripts()]
    finally:
        sys.path.pop(0)


def snapshot_js(repo: Path) -> list[str]:
    """The JavaScript tree the snapshot carries: every file under ``js/`` (ADR 0020 D04).

    Derived from the tree rather than listed, like ``snapshot_hooks``: the carriers ship the
    whole directory (the wheel's force-include, the npm file list), so the snapshot ships it
    whole, and a hand-kept list would go stale with every ported module (C104+).
    """
    js_root = repo / "js"
    if not js_root.is_dir():
        return []
    return sorted(f"js/{path.relative_to(js_root).as_posix()}" for path in js_root.rglob("*") if path.is_file())


#: Corpus-owned stand-ins for the standard tree's prose documents. The corpus pins behavior,
#: not prose: the always-loaded cap measures the imported guardrail's size, and the healthy
#: changelog check reads an ``## Unreleased`` heading a release removes — so with the real
#: documents every guardrail edit and every release would move the spec. Code, data and
#: configuration always come from the repository under test.
STANDIN_ROOT = CORPUS_ROOT / "fixtures" / "tree"


def standins() -> list[str]:
    """The snapshot paths the corpus replaces with its own stand-ins (relative, posix)."""
    return sorted(path.relative_to(STANDIN_ROOT).as_posix() for path in STANDIN_ROOT.rglob("*") if path.is_file())


def build_snapshot(repo: Path, work: Path) -> Path:
    """Copy the curated tree into ``work/tree``, prose documents from the stand-ins; returns the root."""
    snapshot = work / "tree"
    shutil.rmtree(snapshot, ignore_errors=True)
    snapshot.mkdir(parents=True)
    listed = (*SNAPSHOT_FILES, *snapshot_hooks(repo), *snapshot_js(repo))
    orphans = sorted(set(standins()) - set(listed))
    if orphans:
        raise CorpusError(f"stand-ins for paths the snapshot does not carry: {orphans}")
    for relative in listed:
        source = repo / relative
        if not source.is_file():
            # A corpus-controlled path is never allowed to silently vanish from the repo, stand-in or not.
            raise CorpusError(f"snapshot file missing from the repository under test: {relative}")
        standin = STANDIN_ROOT / relative
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(standin if standin.is_file() else source, target)
    return snapshot


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Corpus", "-c", "user.email=corpus@akmon.local", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@dataclass(frozen=True)
class RunEnv:
    """The run environment a fixture materializes against (one scenario's share of a corpus run)."""

    snapshot: Path  # the corpus-controlled standard-tree snapshot
    repo: Path  # the repository under test
    work: Path  # the run's scratch root
    version: str  # the implementation's live version, for {{version}} tokens
    impl: str = "python"  # the implementation under test: picks the native attach layers


def _remove_paths(proj: Path, remove: tuple[str, ...]) -> None:
    """Delete the base fixture paths a scenario names (files or directories)."""
    for relative in remove:
        target = proj / relative
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)


def _rewrite_tokens(proj: Path, version: str) -> None:
    """Materialize ``{{version}}`` in the copied base fixture to the implementation's live version."""
    for path in proj.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if "{{version}}" in text:
                path.write_text(text.replace("{{version}}", version), encoding="utf-8")


def _write_fixture_files(proj: Path, files: dict[str, str], version: str) -> None:
    """Write the scenario's fixture files (version tokens materialized) into the project."""
    for relative, content in files.items():
        target = proj / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.replace("{{version}}", version), encoding="utf-8")


def _tree_with_overrides(snapshot: Path, work: Path, scenario_id: str, version: str, fixture: FixtureSpec) -> Path:
    """A scenario-local copy of the snapshot carrying the fixture's tree-side overrides and removals.

    The shared snapshot must stay clean for every other scenario in the run, so overrides
    land in a private copy the fixture's mount (or package-mode CLI) runs from instead.
    """
    tree = work / f"tree-{scenario_id.replace('/', '-')}"
    shutil.rmtree(tree, ignore_errors=True)
    shutil.copytree(snapshot, tree, symlinks=True)
    for relative, content in fixture.tree_files.items():
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.replace("{{version}}", version), encoding="utf-8")
    for relative in fixture.tree_remove:
        target = tree / relative
        if not target.is_file():
            raise CorpusError(f"{scenario_id}: tree_remove names a path the snapshot does not carry: {relative}")
        target.unlink()
    return tree


def _python_launcher(proj: Path, tree: Path) -> None:
    """The launcher Python package-mode wiring names: a shim that execs the tree's own CLI."""
    launcher = proj / ".venv" / "bin" / "akmon"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    src = tree / "src"
    launcher.write_text(
        f'#!/bin/sh\nPYTHONPATH="{src}" exec "{sys.executable}" "{src / "akmon" / "cli.py"}" "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)


def _lay_out_project(fixture: FixtureSpec, env: RunEnv, scenario_id: str) -> Path:
    """The fixture's files on disk: the base, a native attach's layers, then ``remove`` and tokens."""
    proj = env.work / f"proj-{scenario_id}"
    if proj.exists():
        shutil.rmtree(proj)
    shutil.copytree(CORPUS_ROOT / "fixtures" / fixture.name, proj)
    if fixture.attach == "native":
        for layer in NATIVE_LAYERS[env.impl]:
            shutil.copytree(CORPUS_ROOT / "fixtures" / "attach" / layer, proj, dirs_exist_ok=True)
        if env.impl == "python":
            # The Python carrier's manifest pin. Written here rather than kept as a layer file: a
            # `pyproject.toml` in the repository is read by akmon's own tooling (ruff), and the
            # `{{version}}` token is not a valid requirement.
            (proj / "pyproject.toml").write_text(PYTHON_PIN, encoding="utf-8")
    _remove_paths(proj, fixture.remove)
    _rewrite_tokens(proj, env.version)
    return proj


def materialize_fixture(
    fixture: FixtureSpec, env: RunEnv, scenario_id: str, sync: Callable[[Path, Path], None] | None = None
) -> tuple[Path, Path]:
    """Copy the static fixture for one scenario run; returns (project root, tree seen by the consumer).

    The tree is the snapshot, or a private copy carrying the scenario's tree-side overrides:
    a mounted consumer links it as ``<aitna>/akmon``, a native one runs its CLI. A native
    attach lays the implementation's attach layers over the base before ``remove`` applies,
    so a scenario can take a carrier file away. ``{{version}}`` inside fixture files
    materializes to the implementation's live version, so a committed fixture can name a pin
    that tracks the tree under test.
    """
    proj = _lay_out_project(fixture, env, scenario_id)
    tree = env.snapshot
    if fixture.tree_files or fixture.tree_remove:
        tree = _tree_with_overrides(env.snapshot, env.work, scenario_id, env.version, fixture)
    if fixture.attach == "mount":
        (proj / "_aitna" / "akmon").symlink_to(tree)
    if fixture.attach == "native" and env.impl == "python":
        _python_launcher(proj, tree)
    if fixture.git:
        _git(["init", "-b", fixture.branch], cwd=proj)
    if fixture.warmup == "before" and sync:
        sync(proj, tree)
    _write_fixture_files(proj, fixture.files, env.version)
    if fixture.warmup == "after" and sync:
        sync(proj, tree)
    if fixture.git:  # one baseline: a synced consumer's sync output is committed, not a change
        commit_all(proj, "fixture baseline")
        for tag in fixture.tags:  # lightweight tags on the baseline: the release checks read them
            _git(["tag", tag], cwd=proj)
    return proj, tree


def commit_all(proj: Path, message: str) -> None:
    """Commit everything in the fixture project (``--allow-empty``: a no-op sync is fine)."""
    _git(["add", "-A"], cwd=proj)
    _git(["commit", "--allow-empty", "-m", message], cwd=proj)
