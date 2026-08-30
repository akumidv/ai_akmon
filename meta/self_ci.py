#!/usr/bin/env python3
"""Run akmon's self-checks against a synthetic consuming-project fixture.

Each leg — the fixture ``sync`` write, the ``sync --check`` re-run, the USE-layer
``verify --strict``, and the installed-wheel smoke — reports through the shared finding
envelope (``bin/findings.py``), imported directly rather than by parsing what the child
processes print. The child's own output is echoed to stderr when its leg fails, so the
finding names the leg and the detail is still there to read.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_KEYSTONE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_KEYSTONE_ROOT / "bin"))
sys.path.insert(0, str(_KEYSTONE_ROOT / "meta"))

from checks import capabilities  # noqa: E402
from checks import runtime as runtime_checks  # noqa: E402
from findings import Finding, exit_code, print_findings  # noqa: E402

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
description: Demonstrates the akmon skill contract.
when_to_use: Use for akmon self-CI fixture coverage.
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
        "bin/findings.py",
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


def _checked(command: list[str], *, cwd: Path | None = None) -> None:
    """Run a sub-leg quietly; on failure echo its output to stderr and raise with the tail.

    Captured rather than inherited so a nested launcher's own finding stream does not print
    into this one — two envelopes on one channel read as one, and the reader cannot tell
    whose findings they are.
    """
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode == 0:
        return
    sys.stderr.write((result.stdout or "") + (result.stderr or ""))
    detail = (result.stdout or result.stderr).strip().splitlines()
    tail = detail[-1] if detail else f"exit {result.returncode}"
    raise RuntimeError(f"{' '.join(command)}: {tail}")


def _leg(
    findings: list[Finding],
    label: str,
    command: list[str],
    *,
    code: str,
    ok_fix: str,
    error_fix: str,
) -> bool:
    """Run one leg as a subprocess and record it as a finding; ``True`` when it passed."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0:
        findings.append(Finding("ok", code, f"{label} passes", "", ok_fix))
        return True
    detail = (result.stdout or result.stderr).strip().splitlines()
    tail = detail[-1] if detail else f"exit {result.returncode}"
    sys.stderr.write((result.stdout or "") + (result.stderr or ""))
    findings.append(Finding("error", code, f"{label} failed: {tail}", "", error_fix))
    return False


def _installed_wheel_smoke(akmon_root: Path, tmp_root: Path) -> None:
    """The package leg: build the wheel, install it, and attach a fresh consumer with the
    installed console script — `akmon init` → `sync` → routing init → `verify --strict`.

    This is the only leg where the standard tree comes from ``site-packages`` (the wheel's
    force-included ``akmon/_tree``) rather than from this checkout, so it is what proves the
    embedded-tree resolution, the ``<AITNA_ROOT>/.akmon/`` materialization, and the
    hook-runtime contract hold for a real installation rather than for a dev bench.
    """
    dist = tmp_root / "dist"
    venv = tmp_root / "venv"
    fixture = tmp_root / "package-consumer"
    _checked(["uv", "build", "--wheel", "--out-dir", str(dist)], cwd=akmon_root)
    wheel = next(dist.glob("akmon-*.whl"))
    _checked(["uv", "venv", str(venv)])
    python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    akmon = venv / ("Scripts/akmon.exe" if sys.platform == "win32" else "bin/akmon")
    _checked(["uv", "pip", "install", "--python", str(python), str(wheel)])

    fixture.mkdir(parents=True)
    # The manifest a package-mode consumer must carry: mode `package` mounts no tree, so this
    # dev-group declaration *is* the pin (ADR 0009 §4) — `init` ends non-zero without it, and
    # `verify --strict` keeps reporting it, so the fixture has to look like a real consumer.
    _write(
        fixture / "pyproject.toml",
        '[project]\nname = "package-consumer"\nversion = "0.1.0"\n\n'
        '[dependency-groups]\ndev = ["akmon"]\n',
    )
    subprocess.run(
        [str(akmon), "init", "--mode", "package", "--project-root", str(fixture), "--yes"],
        check=True,
        capture_output=True,
        text=True,
    )
    for command in (["sync", "--check"], ["verify", "--strict", "--quiet"]):
        _checked([str(akmon), *command], cwd=fixture)

    nested = fixture / "src" / "package"
    nested.mkdir(parents=True)
    completed = subprocess.run(
        [str(python), str(fixture / "_aitna" / ".akmon" / "hooks" / "codex-hook.py"), "session-start"],
        input=json.dumps({"cwd": str(nested)}),
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(completed.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "DEVELOP (build the project): architect, engineer, review" in context
    assert "Delegation is the default for non-atomic work" in context


def _run(akmon_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    with tempfile.TemporaryDirectory(prefix="akmon-self-ci-") as tmp:
        fixture = Path(tmp)
        _make_fixture(fixture, akmon_root)
        mounted_bin = fixture / "_aitna" / "akmon" / "bin"
        sync_py = str(mounted_bin / "sync.py")
        verify_py = str(mounted_bin / "verify.py")
        # Ordered and short-circuiting: a fixture that will not sync tells us nothing about
        # what `verify` would have said, so the first red leg is the whole answer.
        healthy = _leg(
            findings,
            "fixture sync",
            [sys.executable, sync_py, "--project-root", str(fixture)],
            code="selfci.fixture-sync",
            ok_fix="Keep fixture sync able to materialize every generated artifact.",
            error_fix="Run python3 meta/self_ci.py and fix the sync failure it reports.",
        ) and _leg(
            findings,
            "fixture sync --check",
            [sys.executable, sync_py, "--project-root", str(fixture), "--check"],
            code="selfci.fixture-sync-check",
            ok_fix="Keep sync idempotent so a second run reports no drift.",
            error_fix="Make sync idempotent so a second run reports no drift.",
        ) and _leg(
            findings,
            "fixture verify --strict",
            [sys.executable, verify_py, "--project-root", str(fixture), "--strict", "--quiet"],
            code="selfci.fixture-verify",
            ok_fix="Keep the synthetic consumer compliant with the USE contract.",
            error_fix="Fix the USE-contract finding the fixture verify reports.",
        )
        if not healthy:
            return findings
        try:
            _installed_wheel_smoke(akmon_root, fixture / "wheel-smoke")
        except Exception as exc:  # the leg owns build, install, attach and hook execution
            detail = " ".join(str(exc).split()) or type(exc).__name__
            findings.append(
                Finding(
                    "error",
                    "selfci.wheel-smoke",
                    f"installed-wheel smoke failed: {detail}",
                    "",
                    "Run python3 meta/self_ci.py and fix the packaged-install failure it reports.",
                )
            )
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors.")
    args = parser.parse_args(argv)

    findings = _run(_KEYSTONE_ROOT)
    print_findings(findings, quiet=args.quiet)
    return exit_code(findings, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
