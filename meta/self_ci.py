#!/usr/bin/env python3
"""Run akmon's self-checks against a synthetic consuming-project fixture.

Each leg — the fixture ``sync`` write, the ``sync --check`` re-run, the USE-layer
``verify --strict``, and the installed-wheel smoke — reports through the shared finding
envelope (``common/findings.py``), imported directly rather than by parsing what the child
processes print. The child's own output is echoed to stderr when its leg fails, so the
finding names the leg and the detail is still there to read.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

_KEYSTONE_ROOT = Path(__file__).resolve().parents[1]
# The tree root for the shared ``common`` package, and ``bin/`` for the two launchers,
# which are imported by their bare script name (``import sync``) the way they are at runtime.
sys.path.insert(0, str(_KEYSTONE_ROOT / "bin"))
sys.path.insert(0, str(_KEYSTONE_ROOT))
sys.path.insert(0, str(_KEYSTONE_ROOT / "meta"))

from checks import capabilities  # noqa: E402
from checks import runtime as runtime_checks  # noqa: E402

from common.findings import Finding, exit_code, print_findings  # noqa: E402
from common.runtime import codex_hooks_list_command  # noqa: E402

AGENTS_MD = """# AGENTS.md

## Dev layer — akmon

Model: `_aitna/akmon/README.md`. Archetype: `ARCHETYPES.md`. Roles:
`_aitna/akmon/roles/`. Read `_aitna/memory` at session start.

Prime directives D2 and D5 are always-on. Secrets come from `.env`.
Skills live in `_aitna/skills/` and root `skills/`; generated vendor skill stubs are pointers only.

**Delegation is the default.** For every non-trivial task, delegate independent mechanical
substeps without waiting for an owner prompt; the orchestrator keeps decomposition, routing,
synthesis, and owner dialogue.
"""


CI_YML = """name: CI
on: [push]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - run: python3 _aitna/akmon/bin/sync.py --check
      - run: python3 _aitna/akmon/bin/verify.py --strict
"""


SKILL_MD = """---
name: demo
description: Demonstrates the akmon skill contract. Use for akmon self-CI fixture coverage.
metadata:
  owner: akmon
---

# demo
"""


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_fixture(root: Path, akmon_root: Path) -> None:
    _write(root / "AGENTS.md", AGENTS_MD)
    _write(root / "_aitna" / "TASKS.md", "# Tasks\n\n- T1 · demo · active · engineer · keep fixture valid\n")
    _write(root / "_aitna" / "agents" / "engineer" / "README.md", "See `_aitna/akmon/roles/engineer.md`.\n")
    _write(root / "_aitna" / "akmon" / "skills" / "demo" / "SKILL.md", SKILL_MD)
    _write(root / "_aitna" / "memory" / "note.md", "fact\n")
    _write(root / "_aitna" / "memory" / "README.md", "# Memory\n- note.md\n")
    _write(root / ".gitignore", "*.env\n!*.env.example\n")
    _write(root / "_aitna" / "akmon" / ".gitignore", "__pycache__/\n*.env\n!*.env.example\n")
    _write(root / ".github" / "workflows" / "ci.yml", CI_YML)

    for relative in (
        "README.md",
        "BOOTSTRAP.md",
        "ARCHETYPES.md",
        "CHANGELOG.md",
        "MODEL.md",
        "CAPABILITIES.md",
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
        "common/__init__.py",
        "common/codex_hooks.py",
        "common/findings.py",
        "common/materialization.py",
        "common/check_runner.py",
        "common/project_root.py",
        "common/record.py",
        "common/runtime.py",
        "common/versions.py",
        "profiles/ruff.toml",
        "bin/check.py",
        "bin/sync.py",
        "bin/verify.py",
        "hooks/hook_core.py",
        "hooks/claude_adapter.py",
        "hooks/codex_adapter.py",
        "hooks/codex-hook.py",
        "hooks/git-commit-guard.py",
        "hooks/session-start-agent.py",
        "hooks/role-on-code.py",
        "hooks/analysis-guard.py",
        "hooks/model-routing.py",
        "hooks/delegation-log.py",
        "tools/model_routing/registry.json",
        "tools/model_routing/routing.py",
        "tools/model_routing/init.py",
        "tools/model_routing/second_opinion.py",
    ):
        source = akmon_root / relative
        text = source.read_text(encoding="utf-8") if source.is_file() else "fixture placeholder\n"
        _write(root / "_aitna" / "akmon" / relative, text)


def path_without(binary: str, path: str, scratch: Path) -> str:
    """``path`` with every directory holding ``binary`` swapped for a shadow of it that does not.

    How self-CI stands in an *absent* Codex for the legs whose fixture never went through the
    owner's `/hooks` approval: ``verify``'s C70 check resolves the binary on ``PATH`` and reports
    an absent installation as its neutral skip, so hiding the binary runs the real code path
    rather than a switch in ``verify`` that any environment could flip. The shadow holds a
    symlink to every other entry of the directory it replaces, so the rest still resolves.
    """
    entries = []
    for index, entry in enumerate(path.split(os.pathsep)):
        directory = Path(entry).absolute()
        effective = entry
        if entry and os.path.lexists(directory / binary):
            shadow = scratch / f"path-{index}"
            shadow.mkdir(parents=True, exist_ok=True)
            for child in directory.iterdir():
                link = shadow / child.name
                if child.name != binary and not os.path.lexists(link):
                    link.symlink_to(child)
            effective = str(shadow)
        entries.append(effective)
    return os.pathsep.join(entries)


def _codex_free_env(scratch: Path) -> dict[str, str]:
    """This process's environment with the Codex binary hidden from ``PATH`` (see above)."""
    path = path_without(codex_hooks_list_command()[0], os.environ.get("PATH", os.defpath), scratch)
    return {**os.environ, "PATH": path}


def _checked(command: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    """Run a sub-leg quietly; on failure echo its output to stderr and raise with the tail.

    Captured rather than inherited so a nested launcher's own finding stream does not print
    into this one — two envelopes on one channel read as one, and the reader cannot tell
    whose findings they are.
    """
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return
    sys.stderr.write((result.stdout or "") + (result.stderr or ""))
    # stderr first: a failing command states its reason there while stdout carries progress,
    # so preferring stdout reported the last *successful* step and dropped the diagnosis.
    detail = (result.stderr or result.stdout).strip().splitlines()
    tail = detail[-1] if detail else f"exit {result.returncode}"
    raise RuntimeError(f"{' '.join(command)}: {tail}")


@dataclass(frozen=True)
class LegInvocation:
    """How to run one self-CI leg's subprocess — its argv and (optionally) its environment."""

    command: list[str]
    env: dict | None = None


@dataclass(frozen=True)
class LegFixes:
    """The two fix hints for one leg's finding, one for each outcome (pass, fail)."""

    ok_fix: str
    error_fix: str


def _leg(
    findings: list[Finding],
    label: str,
    invocation: LegInvocation,
    *,
    code: str,
    fixes: LegFixes,
) -> bool:
    """Run one leg as a subprocess and record it as a finding; ``True`` when it passed."""
    result = subprocess.run(invocation.command, capture_output=True, text=True, env=invocation.env, check=False)
    if result.returncode == 0:
        findings.append(Finding("ok", code, f"{label} passes", "", fixes.ok_fix))
        return True
    detail = (result.stdout or result.stderr).strip().splitlines()
    tail = detail[-1] if detail else f"exit {result.returncode}"
    sys.stderr.write((result.stdout or "") + (result.stderr or ""))
    findings.append(Finding("error", code, f"{label} failed: {tail}", "", fixes.error_fix))
    return False


def _assert_wheel_python_floor(wheel: Path) -> None:
    """Fail unless the built wheel carries exactly one Python >=3.11 metadata field."""
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise RuntimeError(f"wheel has {len(metadata_names)} METADATA files; expected exactly one")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
    fields = [line for line in metadata.splitlines() if line.startswith("Requires-Python:")]
    if fields != ["Requires-Python: >=3.11"]:
        rendered = ", ".join(fields) if fields else "missing"
        raise RuntimeError(f"wheel Requires-Python must be exactly >=3.11; got {rendered}")


def _installed_wheel_smoke(akmon_root: Path, tmp_root: Path, verify_env: dict[str, str]) -> None:
    """The package leg: build the wheel, install it, and attach a fresh consumer with the installed console script.

    `akmon init` → `sync` → routing init → `verify --strict`.

    This is the only leg where the standard tree comes from ``site-packages`` (the wheel's
    force-included ``akmon/_tree``) rather than from this checkout, so it is what proves the
    embedded-tree resolution, the ``<AITNA_ROOT>/.akmon/`` materialization, and the
    hook-runtime contract hold for a real installation rather than for a dev bench.
    """
    dist = tmp_root / "dist"
    fixture = tmp_root / "package-consumer"
    fixture.mkdir(parents=True)
    # The venv lives **inside the fixture**, because mode `package` requires exactly that
    # (ADR 0009 §4): the generated hook wiring names the console script by a project-relative
    # path, and that wiring is a committed file every developer runs. A venv elsewhere would
    # only be spellable absolutely, which is a silent break for everyone but its owner.
    venv = fixture / ".venv"
    # A git repository, because the Codex wiring anchors on `git rev-parse --show-toplevel`.
    _checked(["git", "init", "-q", str(fixture)])
    _checked(["uv", "build", "--wheel", "--out-dir", str(dist)], cwd=akmon_root)
    wheel = next(dist.glob("akmon-*.whl"))
    _assert_wheel_python_floor(wheel)
    _checked(["uv", "venv", str(venv)])
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    akmon = venv / ("Scripts/akmon.exe" if sys.platform == "win32" else "bin/akmon")
    _checked(["uv", "pip", "install", "--python", str(python), str(wheel)])

    # The manifest a package-mode consumer must carry: mode `package` mounts no tree, so this
    # dev-group declaration *is* the pin (ADR 0009 §4) — `init` ends non-zero without it, and
    # `verify --strict` keeps reporting it, so the fixture has to look like a real consumer.
    _write(
        fixture / "pyproject.toml",
        '[project]\nname = "package-consumer"\nversion = "0.1.0"\n\n[dependency-groups]\ndev = ["akmon"]\n',
    )
    # Through ``_checked`` rather than a bare ``check=True``: CalledProcessError names only the
    # command and the exit status, and this leg's most common failure — the pin lookup below —
    # is a whole sentence the reader needs.
    _checked([str(akmon), "init", "--mode", "package", "--project-root", str(fixture), "--yes"])
    # `verify_env` hides Codex from PATH. C70's host-trust check would otherwise ask a live
    # `codex app-server` whether this throwaway fixture went through the owner's `/hooks`
    # approval — it never has — and fail --strict on any machine with Codex installed, over a
    # fact this packaging smoke is not testing. Hidden, it takes the check's own absent-install
    # skip; there is no switch in `verify` to flip instead.
    for command in (["sync", "--check"], ["verify", "--strict", "--quiet"]):
        _checked([str(akmon), *command], cwd=fixture, env=verify_env)

    # Nothing executable is materialized any more: the wiring calls `akmon hook`, which runs
    # the hooks out of the wheel. Assert the absence, or the next regression re-adds the copies
    # and every check below still passes.
    materialized = sorted(
        path.relative_to(fixture).as_posix() for path in (fixture / "_aitna" / ".akmon").rglob("*") if path.is_file()
    )
    # The fixture has no linter of its own, so `init` set up ruff with akmon's Python rules and
    # `sync` materialized them beside the imported guardrail — and nothing else.
    if materialized != ["_aitna/.akmon/guardrails/_common.md", "_aitna/.akmon/profiles/ruff.toml"]:
        raise RuntimeError(f"package mode materialized more than the imported rules: {materialized}")

    nested = fixture / "src" / "package"
    nested.mkdir(parents=True)
    _run_generated_hook_commands(fixture, nested)


def _generated_hook_commands(fixture: Path) -> list[tuple[str, str, str]]:
    """Every ``(vendor, event, command)`` triple the two generated wirings name.

    Read from the generated files themselves — not rebuilt from the templates that wrote them.
    """
    triples: list[tuple[str, str, str]] = []
    for vendor, relative in (("claude", ".claude/settings.json"), ("codex", ".codex/hooks.json")):
        document = json.loads((fixture / relative).read_text(encoding="utf-8"))
        for event, entries in document.get("hooks", {}).items():
            for entry in entries:
                triples.extend((vendor, event, hook["command"]) for hook in entry.get("hooks", []))
    return triples


# A patch body in the shape codex 0.146.0 actually sends (``tool_input.command``), so the
# advisories receive a real target instead of raising their own no-path diagnostic.
_CODEX_PATCH = "*** Begin Patch\n*** Update File: src/package/probe.py\n+print(1)\n*** End Patch\n"

# codex session-start + claude session-start-agent + claude model-routing.
_ALWAYS_SPEAKING_HOOK_COUNT = 3


def _hook_payload(vendor: str, event: str, cwd: Path) -> dict:
    """A payload of the shape each vendor really sends for ``event``.

    Realistic rather than minimal on purpose: a tool event with no readable target makes the
    advisories report *their own* defect signal on stderr, which would mask the thing this
    leg is watching for.
    """
    payload: dict = {"cwd": str(cwd), "session_id": "self-ci", "hook_event_name": event}
    if event != "PreToolUse":
        return payload
    payload["tool_use_id"] = "self-ci-1"
    if vendor == "codex":
        payload["tool_name"] = "apply_patch"
        payload["tool_input"] = {"command": _CODEX_PATCH}
    else:
        payload["tool_name"] = "Edit"
        payload["tool_input"] = {"file_path": str(cwd / "src" / "package" / "probe.py")}
    return payload


def _run_generated_hook_commands(fixture: Path, nested: Path) -> None:
    """Run every generated hook command **verbatim**, the way the harness runs it.

    Verbatim and through a shell because the command *is* the artifact under test: the vendor
    anchors (``$CLAUDE_PROJECT_DIR``, ``$(git rev-parse --show-toplevel)``) and the console
    script path are the parts that break, and a reconstructed invocation would test something
    the harness never runs.

    The size of stdout is checked, not only the exit code, because that is the only signal that
    separates "the hook decided to stay quiet" from "the hook silently found no tree to read":
    a hook command whose runtime root is wrong exits 0 with an empty stderr. So the two hooks
    that must always speak — the Codex session brief and the Claude routing status — are
    required to produce output, while the advisories are only required not to fail.
    """
    environment = {**os.environ, "CLAUDE_PROJECT_DIR": str(fixture)}
    speaking = 0
    for vendor, event, command in _generated_hook_commands(fixture):
        # Codex is handed the *nested* cwd, which is what pins root discovery from a
        # subdirectory; Claude's session-start wrapper takes the payload cwd as the root
        # directly, so it gets the project root.
        cwd = nested if vendor == "codex" else fixture
        payload = json.dumps(_hook_payload(vendor, event, cwd))
        completed = subprocess.run(  # noqa: S602 — the generated hook command runs as the harness runs it
            command,
            shell=True,
            cwd=fixture,
            env=environment,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
        label = f"{vendor} {event}: {command}"
        if completed.returncode != 0:
            raise RuntimeError(f"generated hook command failed ({label}): {completed.stderr.strip()}")
        if completed.stderr.strip():
            raise RuntimeError(f"generated hook command wrote to stderr ({label}): {completed.stderr.strip()}")
        if event == "SessionStart":
            # Every SessionStart hook has something to say in a freshly attached project. The
            # per-turn hooks are silent by design, so only these are required to speak.
            if not completed.stdout.strip():
                raise RuntimeError(f"generated hook command produced no output ({label})")
            speaking += 1
            if vendor == "codex":
                context = json.loads(completed.stdout)["hookSpecificOutput"]["additionalContext"]
                if "DEVELOP (build the project): architect, engineer, review" not in context:
                    raise RuntimeError(f"session-start hook lost its role brief ({label})")
                if "Delegation is the default for non-atomic work" not in context:
                    raise RuntimeError(f"session-start hook lost its delegation rule ({label})")
    if speaking < _ALWAYS_SPEAKING_HOOK_COUNT:
        raise RuntimeError(f"expected the always-speaking hooks to be wired; saw {speaking}")


def _wheel_smoke_report(detail: str) -> tuple[str, str]:
    """Message and one-sentence fix for a failed smoke — a *prerequisite* failure says so.

    The leg's ``init --mode package`` resolves the pin by reading the akmon repository's release
    tags over the network, so it also fails when the network is unreachable or git cannot
    authenticate — neither of which is a defect in what akmon ships. Reported as "returned
    non-zero exit status 2" that reads like a packaging regression and costs a bisect; reported
    as the prerequisite it is, it costs one command. The envelope keeps ``fix`` to a single
    imperative sentence, so the diagnosis rides in the message.
    """
    if "cannot discover the latest release tag" in detail or "could not read Username" in detail:
        return (
            f"installed-wheel smoke could not run: {detail} :: prerequisite of this leg, not a "
            "packaging defect — `init --mode package` resolves the pin from the akmon "
            "repository's release tags, so it needs network reach plus a git credential helper "
            "that works outside this checkout (check with `git ls-remote --tags <repo>` from a "
            "directory that is not a git repository)",
            "Wire git credentials outside this checkout with `gh auth login` then "
            "`gh auth setup-git`, and re-run python3 meta/self_ci.py.",
        )
    return (
        f"installed-wheel smoke failed: {detail}",
        "Run python3 meta/self_ci.py and fix the packaged-install failure it reports.",
    )


def _run(akmon_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    with (
        tempfile.TemporaryDirectory(prefix="akmon-self-ci-") as tmp,
        tempfile.TemporaryDirectory(prefix="akmon-self-ci-path-") as path_scratch,
    ):
        fixture = Path(tmp)
        # Outside the fixture: the shadow PATH directories are not part of the consumer tree.
        verify_env = _codex_free_env(Path(path_scratch))
        _make_fixture(fixture, akmon_root)
        mounted_bin = fixture / "_aitna" / "akmon" / "bin"
        sync_py = str(mounted_bin / "sync.py")
        verify_py = str(mounted_bin / "verify.py")
        # Ordered and short-circuiting: a fixture that will not sync tells us nothing about
        # what `verify` would have said, so the first red leg is the whole answer.
        healthy = (
            _leg(
                findings,
                "fixture sync",
                LegInvocation([sys.executable, sync_py, "--project-root", str(fixture)]),
                code="selfci.fixture-sync",
                fixes=LegFixes(
                    ok_fix="Keep fixture sync able to materialize every generated artifact.",
                    error_fix="Run python3 meta/self_ci.py and fix the sync failure it reports.",
                ),
            )
            and _leg(
                findings,
                "fixture sync --check",
                LegInvocation([sys.executable, sync_py, "--project-root", str(fixture), "--check"]),
                code="selfci.fixture-sync-check",
                fixes=LegFixes(
                    ok_fix="Keep sync idempotent so a second run reports no drift.",
                    error_fix="Make sync idempotent so a second run reports no drift.",
                ),
            )
            and _leg(
                findings,
                "fixture verify --strict",
                LegInvocation(
                    [sys.executable, verify_py, "--project-root", str(fixture), "--strict", "--quiet"],
                    # This synthetic fixture never runs the live Codex `/hooks` owner-approval flow C70
                    # checks for; Codex is hidden from PATH so the check takes its absent-install skip
                    # (see the matching note on the wheel smoke).
                    env=verify_env,
                ),
                code="selfci.fixture-verify",
                fixes=LegFixes(
                    ok_fix="Keep the synthetic consumer compliant with the USE contract.",
                    error_fix="Fix the USE-contract finding the fixture verify reports.",
                ),
            )
        )
        if not healthy:
            return findings
        try:
            _installed_wheel_smoke(akmon_root, fixture / "wheel-smoke", verify_env)
        except Exception as exc:  # noqa: BLE001 — the leg owns build, install, attach and hook execution
            detail = " ".join(str(exc).split()) or type(exc).__name__
            message, fix = _wheel_smoke_report(detail)
            findings.append(Finding("error", "selfci.wheel-smoke", message, "", fix))
        else:
            findings.append(
                Finding(
                    "ok",
                    "selfci.wheel-smoke",
                    "installed-wheel smoke passes (build, install, init, sync, verify, hook)",
                    "",
                    "Keep the packaged install green before every release.",
                )
            )
    # Akmon's own declarations, checked against akmon's own tree rather than the fixture: the
    # capability matrix is a property of what akmon ships, not of a synthetic consumer's use of it.
    findings.extend(capabilities.check_capabilities(akmon_root))
    findings.extend(runtime_checks.check_declared_runtimes(akmon_root))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run every self-CI leg against akmon's own tree and print the findings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors.")
    args = parser.parse_args(argv)

    findings = _run(_KEYSTONE_ROOT)
    print_findings(findings, quiet=args.quiet)
    return exit_code(findings, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
