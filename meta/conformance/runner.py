#!/usr/bin/env python3
"""Run the conformance corpus against one implementation (C101).

The corpus is the normative behavioral spec both permanent implementations must pass
(ADR 0020 D01/D03). This runner executes the scenarios at the process boundary — the same
surface a harness invokes — against the Python implementation for now; the Node
implementation joins here as ``--impl node`` once it exists (C104+).

Usage:
    python3 meta/conformance/runner.py [--tree REPO] [--impl python] [--area hooks]
                                       [--scenario cli/version] [--record]

``--record`` reseeds the ``[expected]`` section of the named scenario(s) from the live
behavior of the implementation under test. Seeding is a mechanical half of a two-step act:
the corpus records what the implementation does, a human reviews that the recorded behavior
is what the standard means, and only then does the record become the spec.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CORPUS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(CORPUS_ROOT))
sys.path.insert(0, str(CORPUS_ROOT.parents[1]))

from corpus import (  # noqa: E402
    CORPUS_ROOT as CORPUS,
)
from corpus import (  # noqa: E402
    REPO_ROOT,
    CorpusError,
    ExpectedSpec,
    RunEnv,
    Scenario,
    build_snapshot,
    load_scenarios,
    materialize_fixture,
)
from coverage import check_coverage, load_exceptions  # noqa: E402
from normalize import NORM_VERSION, Ctx, normalize  # noqa: E402

IMPL_SCOPE = {"python": ("shared", "python"), "node": ("shared", "node")}
#: One finding line as ``common.findings.render`` prints it: ``SEVERITY code[ target]: …``.
FINDING_LINE = re.compile(r"^(OK|WARN|ERROR) ([a-z][a-z_]*\.[a-z0-9-]+)[ :]")


@dataclass
class Outcome:
    """One scenario's report line: its id, its status, and the detail on failure."""

    scenario: str
    status: str  # pass | fail | skip
    detail: str = ""


def _hide_binary_from_path(binary: str, scratch: Path) -> str:
    """PATH with every directory holding ``binary`` shadowed by a copy that lacks it.

    The corpus tests the corpus's own contract, not the host's live harness: verify's
    ``codex.host-trust`` would otherwise run a live app-server RPC against the host's Codex
    (slow, and host-state-dependent). Live harness probes are N10's job.
    """
    entries = []
    for index, entry in enumerate(os.environ.get("PATH", "").split(os.pathsep)):
        directory = Path(entry).absolute() if entry else None
        if directory and (directory / binary).exists():
            shadow = scratch / f"path-{index}"
            shadow.mkdir(parents=True, exist_ok=True)
            for child in directory.iterdir():
                if child.name != binary and not os.path.lexists(shadow / child.name):
                    (shadow / child.name).symlink_to(child)
            entries.append(str(shadow))
        else:
            entries.append(entry)
    return os.pathsep.join(entries)


def _today() -> str:
    """The host's local calendar day, the one the process under test stamps its dates in."""
    return datetime.datetime.now().astimezone().date().isoformat()


def _impl_version(repo: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(repo / "src" / "akmon" / "cli.py"), "version"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repo / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
    )
    return result.stdout.strip()


def _materialize_tokens(text: str, ctx: Ctx) -> str:
    """Scenario-side token substitution (fixture files, payloads, argv).

    The mirror of normalize in the reverse direction: a token in scenario text becomes the
    host fact.
    """
    for token, raw in (
        ("{{root}}", ctx.root),
        ("{{mount}}", ctx.mount),
        ("{{tree}}", ctx.tree),
        ("{{repo}}", ctx.repo),
        ("{{tmp}}", ctx.tmp),
    ):
        if raw:
            text = text.replace(token, raw)
    return text.replace("{{version}}", ctx.version)


def _normalize_leaves(value: object, ctx: Ctx) -> object:
    if isinstance(value, str):
        return normalize(value, ctx)
    if isinstance(value, list):
        return [_normalize_leaves(item, ctx) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_leaves(item, ctx) for key, item in value.items()}
    return value


def _toml_string(value: str) -> str:
    """A TOML basic string literal: JSON escaping is a subset of TOML's, and valid as such."""
    return json.dumps(value, ensure_ascii=False)


def _toml_value(value: object) -> str:
    """One TOML inline value: a scalar, an array, or an inline table (arrays of objects included)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        members = ", ".join(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in value.items())
        return f"{{ {members} }}" if value else "{}"
    if value is None:
        raise CorpusError("a JSON null has no TOML spelling: pin this output with `stdout` instead of `stdout_json`")
    raise CorpusError(f"not a JSON value: {value!r}")


def _toml_key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else _toml_string(key)


def _toml_tables(value: dict, table: str) -> str:
    """A JSON object as TOML under ``[<table>]``: its non-object members, then one sub-table per object member.

    A TOML table must not be re-opened, and a key after a ``[<table>.<key>]`` header belongs to
    that header — so every non-object member is written before the first sub-table. Header
    segments are quoted like keys, so a member name holding a dot stays one segment.
    """
    lines = [f"[{table}]"]
    lines.extend(f"{_toml_key(k)} = {_toml_value(v)}" for k, v in value.items() if not isinstance(v, dict))
    for key, item in value.items():
        if isinstance(item, dict):
            lines.append(_toml_tables(item, f"{table}.{_toml_key(key)}"))
    return "\n".join(lines)


def _build_local_repo(snapshot: Path, work: Path, version: str) -> Path:
    """The local standard-tree git repo an init/update scenario's --repo names.

    A copy of the corpus snapshot (the controlled tree), committed and tagged
    ``v<version>`` — so a scenario can attach from a repository without network or
    credentials, and the tagged content is corpus-controlled.
    """
    local = work / "repo"
    shutil.rmtree(local, ignore_errors=True)
    local.mkdir(parents=True)
    for child in snapshot.iterdir():
        target = local / child.name
        if child.is_dir():
            shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target)
    subprocess.run(["git", "init", "-b", "main"], cwd=local, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Corpus"], cwd=local, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "corpus@akmon.local"], cwd=local, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=local, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "standard tree snapshot"], cwd=local, check=True, capture_output=True)
    subprocess.run(["git", "tag", f"v{version}"], cwd=local, check=True, capture_output=True)
    return local


def _run(scenario: Scenario, repo: Path, snapshot: Path, version: str, work: Path) -> tuple[int, str, str, Ctx]:
    """Execute one scenario; returns (exit, stdout, stderr, the run's normalization ctx)."""
    tag = scenario.id.replace("/", "-")
    run_tmp = work / f"tmp-{tag}"
    run_tmp.mkdir(parents=True)
    fixture = scenario.fixture
    first_day = _today()
    env = {
        **os.environ,
        "TMPDIR": str(run_tmp),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": _hide_binary_from_path("codex", work / "path-shadow"),
        **scenario.env,
    }

    def warmup(proj: Path, tree: Path) -> None:
        """The implementation's own sync (write): the mounted script, or the package CLI."""
        if fixture.attach == "mount":
            warm = [sys.executable, str(proj / "_aitna" / "akmon" / "bin" / "sync.py"), "--project-root", str(proj)]
        else:
            warm = [sys.executable, str(tree / "src" / "akmon" / "cli.py"), "sync", "--project-root", str(proj)]
        result = subprocess.run(
            warm, cwd=proj, env={**env, "PYTHONPATH": str(tree / "src")}, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            raise CorpusError(
                f"{scenario.id}: warmup sync failed (exit {result.returncode}):\n" + result.stdout + result.stderr
            )

    # The tree is the corpus-controlled snapshot (or a private override copy): a mounted
    # consumer links it, a native one runs the CLI inside it as its embedded tree.
    proj_dir, tree = materialize_fixture(
        fixture, RunEnv(snapshot=snapshot, repo=repo, work=work, version=version, impl="python"), tag, warmup
    )
    local_repo = _build_local_repo(snapshot, work, version) if fixture.repo else None
    mount = proj_dir / "_aitna" / "akmon"
    ctx = Ctx(
        root=str(proj_dir),
        mount=str(mount) if fixture.attach == "mount" else "",
        tree=str(tree),
        tmp=str(run_tmp),
        version=version,
        repo=str(local_repo) if local_repo else "",
        days=(first_day,),
    )
    cli = [sys.executable, str(tree / "src" / "akmon" / "cli.py")]
    cli_env = {"PYTHONPATH": str(tree / "src")}
    for relative, content in fixture.tmp_files.items():
        target = run_tmp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_materialize_tokens(content, ctx), encoding="utf-8")
    run_spec = scenario.run
    argv = tuple(_materialize_tokens(a, ctx) for a in run_spec.argv)
    args = tuple(_materialize_tokens(a, ctx) for a in run_spec.args)
    payload = ""
    if scenario.kind == "hook":
        # The harness's own entry: package wiring calls the launcher, mounted wiring the script.
        if fixture.attach == "native":
            command = [str(proj_dir / ".venv" / "bin" / "akmon"), "hook", run_spec.script, *args]
        else:
            command = [sys.executable, str(tree / "hooks" / f"{run_spec.script}.py"), *args]
        payload = _materialize_tokens(json.dumps(run_spec.payload), ctx) if run_spec.payload else ""
    elif scenario.kind == "cli":
        command = [*cli, *argv]
        env.update(cli_env)
    elif scenario.kind == "tool":
        command = [sys.executable, str(tree / "tools" / f"{run_spec.tool}.py"), *argv]
    else:  # unit
        command = [
            sys.executable,
            str(CORPUS / "probe.py"),
            "--tree",
            str(tree),
            run_spec.probe,
            str(CORPUS / "units" / run_spec.table),
        ]
    result = subprocess.run(command, cwd=proj_dir, env=env, input=payload, capture_output=True, text=True, check=False)
    last_day = _today()
    if last_day != first_day:  # a run across midnight: both days are the run's own
        ctx = dataclasses.replace(ctx, days=(first_day, last_day))
    return result.returncode, result.stdout, result.stderr, ctx


def _stream_diff(want: str, actual: str) -> str:
    """A unified diff between two normalized streams (the expectation first)."""
    return "".join(
        difflib.unified_diff(
            want.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile="expected",
            tofile="actual",
        )
    )


def _stdout_json_problem(stdout: str, expected_json: dict, ctx: Ctx) -> str | None:
    """The stdout_json mismatch text, or None when the parsed JSON equals the expectation."""
    try:
        actual_json = _normalize_leaves(json.loads(stdout), ctx)
    except (ValueError, TypeError) as exc:
        return f"stdout_json: actual stdout is not one JSON document ({exc!r})"
    want = _normalize_leaves(expected_json, ctx)
    if actual_json != want:
        rendered_want = json.dumps(want, indent=2, sort_keys=True, ensure_ascii=False)
        rendered_actual = json.dumps(actual_json, indent=2, sort_keys=True, ensure_ascii=False)
        return "stdout_json:\n" + _stream_diff(rendered_want, rendered_actual)
    return None


def _file_problems(expected: ExpectedSpec, proj: Path, tree: Path, ctx: Ctx) -> list[str]:
    """Every mismatch of the expected files (and absent files) against the run's project."""
    problems: list[str] = []
    for relative, recorded in expected.files.items():
        want = recorded
        if want.startswith("ref:tree:"):
            want = normalize((tree / want.removeprefix("ref:tree:")).read_text(encoding="utf-8"), ctx)
        target = proj / relative
        if not target.is_file():
            problems.append(f"file {relative}: expected to exist, missing")
            continue
        actual = normalize(target.read_text(encoding="utf-8"), ctx)
        if actual != want:
            problems.append(f"file {relative}:\n" + _stream_diff(want, actual))
    problems.extend(
        f"file {relative}: expected absent, present" for relative in expected.file_absent if (proj / relative).exists()
    )
    return problems


def claimed_codes(covers: tuple[str, ...]) -> set[str]:
    """The finding codes a scenario claims (its ``code:<id>`` covers entries)."""
    return {item.removeprefix("code:") for item in covers if item.startswith("code:")}


def owned_codes() -> frozenset[str]:
    """Codes one ecosystem owns whole (coverage.toml ``[ecosystem]`` ``code:<code>`` entries)."""
    return load_exceptions().owned_codes()


def finding_lines(stdout: str, excluded: frozenset[str]) -> list[str]:
    """Every finding line of a normalized stdout but those of ``excluded`` codes, in output order.

    ``findings`` mode: a shared scenario pins every shared finding line; a code an ecosystem
    owns whole (the standard-tree layout, the carrier's pin, the launcher) prints lines only
    that ecosystem's scenarios pin (ADR 0020 D02).
    """
    lines = []
    for line in stdout.splitlines():
        match = FINDING_LINE.match(line)
        if match and match.group(2) not in excluded:
            lines.append(line)
    return lines


def _cover_problems(covers: tuple[str, ...], stdout: str) -> list[str]:
    """The claimed codes no finding line of the actual stdout carries (a line match, not a substring)."""
    printed = {match.group(2) for line in stdout.splitlines() if (match := FINDING_LINE.match(line))}
    missing = sorted(claimed_codes(covers) - printed)
    return [f"covers 'code:{code}': no finding line of the actual stdout carries it" for code in missing]


def _compare(scenario: Scenario, exit_code: int, stdout: str, stderr: str, ctx: Ctx) -> str:
    """Empty string on match; a diff of every mismatch on failure."""
    expected = scenario.expected
    actual_stdout = normalize(stdout, ctx)
    actual_stderr = normalize(stderr, ctx)
    problems: list[str] = []
    if exit_code != expected.exit:
        problems.append(f"exit: expected {expected.exit}, got {exit_code}")
    if expected.stdout is not None and actual_stdout != expected.stdout:
        problems.append("stdout:\n" + _stream_diff(expected.stdout, actual_stdout))
    if expected.findings is not None:
        actual_findings = finding_lines(actual_stdout, owned_codes())
        if actual_findings != list(expected.findings):
            problems.append(
                "findings:\n" + _stream_diff("\n".join(expected.findings) + "\n", "\n".join(actual_findings) + "\n")
            )
    if expected.stdout_json is not None:
        json_problem = _stdout_json_problem(stdout, expected.stdout_json, ctx)
        if json_problem:
            problems.append(json_problem)
    if expected.stderr is not None and actual_stderr != expected.stderr:
        problems.append("stderr:\n" + _stream_diff(expected.stderr, actual_stderr))
    problems.extend(
        f"stderr: expected to contain {needle!r}" for needle in expected.stderr_contains if needle not in actual_stderr
    )
    problems.extend(_file_problems(expected, Path(ctx.root), Path(ctx.tree), ctx))
    problems.extend(_cover_problems(scenario.covers, stdout))
    return "\n".join(problems)


def _records_findings(scenario: Scenario, stdout: str) -> bool:
    """Whether ``--record`` writes ``findings`` rather than the exact stdout.

    Exact stdout wherever it can be shared spec. A shared scenario whose output carries a line
    of an ecosystem-owned code cannot pin that output whole, so it pins its shared finding lines.
    """
    if scenario.ecosystem != "shared":
        return False
    owned = owned_codes()
    return any((match := FINDING_LINE.match(line)) and match.group(2) in owned for line in stdout.splitlines())


def _record_block(scenario: Scenario, exit_code: int, stdout: str, stderr: str, ctx: Ctx) -> str:
    """The [expected] section a --record run writes back into the scenario file."""
    proj = Path(ctx.root)
    expected = scenario.expected
    lines = ["[expected]", f"exit = {exit_code}"]
    if expected.stderr_contains:  # hand-written, never recorded: keep it as the author left it
        lines.append(f"stderr_contains = [{', '.join(_toml_string(item) for item in expected.stderr_contains)}]")
    else:
        lines.append(f"stderr = {_toml_string(normalize(stderr, ctx))}")
    if expected.stdout_json is not None:
        lines.append(_toml_tables(_normalize_leaves(json.loads(stdout), ctx), "expected.stdout_json"))
    elif _records_findings(scenario, normalize(stdout, ctx)):
        recorded = finding_lines(normalize(stdout, ctx), owned_codes())
        lines.append("findings = [" + "".join(f"\n  {_toml_string(line)}," for line in recorded) + "\n]")
    else:
        lines.append(f"stdout = {_toml_string(normalize(stdout, ctx))}")
    if scenario.expected.files:
        lines.append("[expected.files]")
        for relative in scenario.expected.files:
            target = proj / relative
            actual = normalize(target.read_text(encoding="utf-8"), ctx) if target.is_file() else "<missing>"
            lines.append(f"{_toml_string(relative)} = {_toml_string(actual)}")
    if scenario.expected.file_absent:
        lines.append(f"file_absent = [{', '.join(_toml_string(item) for item in scenario.expected.file_absent)}]")
    return "\n".join(lines)


def _apply_record(path: Path, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    index = next((i for i, line in enumerate(lines) if line.strip() == "[expected]"), None)
    if index is None:
        lines.append("")
    else:
        lines = lines[:index]
    path.write_text("\n".join(lines).rstrip() + "\n\n" + block + "\n", encoding="utf-8")


def _wanted_scenarios(scenarios: list[Scenario], scenario_ids: list[str]) -> list[Scenario]:
    """The subset an explicit --scenario list selects: a full id, or its stem when unambiguous."""
    stems = {sid.split("/")[-1]: sid for sid in scenario_ids if "/" not in sid}
    full = {sid for sid in scenario_ids if "/" in sid}
    return [s for s in scenarios if s.id in full or (s.id.split("/")[-1] in stems and s.id in stems.values())]


def _skip(scenario: Scenario, impl: str) -> Outcome:
    """A skip for a scenario outside the implementation's ecosystem scope."""
    return Outcome(scenario.id, "skip", f"ecosystem {scenario.ecosystem} not in scope of impl {impl}")


def _record_outcome(scenario: Scenario, repo: Path, snapshot: Path, version: str, work: Path) -> Outcome:
    """Run a scenario and write its observed behavior back into the scenario file."""
    exit_code, stdout, stderr, ctx = _run(scenario, repo, snapshot, version, work)
    path = CORPUS / "scenarios" / f"{scenario.id}.toml"
    _apply_record(path, _record_block(scenario, exit_code, stdout, stderr, ctx))
    return Outcome(scenario.id, "recorded", f"exit={exit_code}")


def _judge_outcome(scenario: Scenario, repo: Path, snapshot: Path, version: str, work: Path) -> Outcome:
    """Run a scenario and compare it with its recorded expectations."""
    exit_code, stdout, stderr, ctx = _run(scenario, repo, snapshot, version, work)
    problems = _compare(scenario, exit_code, stdout, stderr, ctx)
    if problems:
        return Outcome(scenario.id, "fail", problems)
    return Outcome(scenario.id, "pass")


def _print_report(impl: str, version: str, outcomes: list[Outcome], repo: Path) -> int:
    """The runner's final report: every outcome, the coverage gate, and the process exit code."""
    print(f"conformance corpus v{NORM_VERSION} · impl {impl} · version {version}")
    for outcome in outcomes:
        print(f"  {outcome.status:<8} {outcome.scenario}")
        if outcome.detail:
            for line in outcome.detail.splitlines():
                print(f"           {line}")
    failed = [o for o in outcomes if o.status == "fail"]
    gaps = 0
    for finding in check_coverage(repo):
        severity = finding.severity.upper()
        print(f"  {severity:<8} {finding.code} {finding.message}")
        gaps += finding.severity != "ok"
    if failed or gaps:
        print(f"{len(failed)} of {len(outcomes)} scenarios failed; coverage gate: {gaps} finding(s)")
        return 1
    print(
        f"{len(outcomes)} scenarios: "
        f"{sum(o.status == 'pass' for o in outcomes)} pass, "
        f"{sum(o.status == 'skip' for o in outcomes)} skip; coverage gate ok"
    )
    return 0


def run_scenarios(repo: Path, impl: str, area: str | None, scenario_ids: list[str], *, record: bool) -> int:
    """Run the corpus against one implementation, print the report, and return the exit code."""
    version = _impl_version(repo)
    if impl == "node":
        raise CorpusError("the node implementation is not ported yet (C104+); the corpus runs it once it exists")
    with tempfile.TemporaryDirectory(prefix="akmon-conformance-") as raw:
        work = Path(raw)
        snapshot = build_snapshot(repo, work)
        scenarios = load_scenarios(area, strict_seeded=not record)
        if scenario_ids:
            scenarios = _wanted_scenarios(scenarios, scenario_ids)
        scope = IMPL_SCOPE[impl]
        outcomes: list[Outcome] = []
        for scenario in scenarios:
            if scenario.ecosystem not in scope:
                outcomes.append(_skip(scenario, impl))
                continue
            try:
                if record and scenario.kind == "unit":  # a unit table is its own expectation
                    outcomes.append(_judge_outcome(scenario, repo, snapshot, version, work))
                elif record:
                    outcomes.append(_record_outcome(scenario, repo, snapshot, version, work))
                else:
                    outcomes.append(_judge_outcome(scenario, repo, snapshot, version, work))
            except CorpusError as exc:
                outcomes.append(Outcome(scenario.id, "fail", str(exc)))
    return _print_report(impl, version, outcomes, repo)


def main(argv: list[str] | None = None) -> int:
    """Parse the runner's CLI and run the corpus once; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tree",
        default=str(REPO_ROOT),
        help="the repository under test (default: the corpus's own repo)",
    )
    parser.add_argument("--impl", choices=sorted(IMPL_SCOPE), default="python")
    parser.add_argument("--area", choices=["hooks", "cli", "tools", "units"], help="run one area only")
    parser.add_argument("--scenario", action="append", default=[], help="run one scenario id (repeatable)")
    parser.add_argument("--record", action="store_true", help="reseed [expected] from live behavior")
    args = parser.parse_args(argv)
    return run_scenarios(Path(args.tree).resolve(), args.impl, args.area, args.scenario, record=args.record)


if __name__ == "__main__":
    raise SystemExit(main())
