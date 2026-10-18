#!/usr/bin/env python3
"""Run akmon's self-checks against a synthetic consuming-project fixture.

Each leg — the fixture ``sync`` write, the ``sync --check`` re-run, the USE-layer
``verify --strict``, the installed-wheel smoke, and the npm smoke with no Python on ``PATH``
(C106) — reports through the shared finding envelope (``common/findings.py``), imported
directly rather than by parsing what the child processes print. The child's own output is
echoed to stderr when its leg fails, so the finding names the leg and the detail is still
there to read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

_AKMON_ROOT = Path(__file__).resolve().parents[1]
# The tree root for the shared ``common`` package, and ``bin/`` for the two launchers,
# which are imported by their bare script name (``import sync``) the way they are at runtime.
sys.path.insert(0, str(_AKMON_ROOT / "bin"))
sys.path.insert(0, str(_AKMON_ROOT))
sys.path.insert(0, str(_AKMON_ROOT / "meta"))

import verify as verify_tool  # noqa: E402
from checks import always_loaded as always_loaded_caps  # noqa: E402
from checks import canary, capabilities, decision_records  # noqa: E402
from checks import runtime as runtime_checks  # noqa: E402

from common.findings import Finding, exit_code, print_findings  # noqa: E402
from common.runtime import codex_hooks_list_command  # noqa: E402

AGENTS_MD = """# AGENTS.md

## Dev layer — akmon

Model: `_aitna/akmon/README.md`. Archetype: `ARCHETYPES.md`. Roles:
`_aitna/akmon/roles/`. Read `_aitna/memory` at session start.

The owner verifies consequential decisions recorded in ADRs. D5 is always-on. Secrets come from `.env`.
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
        "common/report_path.py",
        "common/runtime.json",
        "common/runtime.py",
        "common/versions.py",
        "profiles/ruff.toml",
        "bin/check.py",
        "bin/sync.py",
        "bin/verify.py",
        "bin/verify.json",
        "bin/sync.json",
        "src/akmon/init.json",
        "src/akmon/update.json",
        "src/akmon/cli.json",
        *(f"hooks/{name}" for name in verify_tool.wired_hook_scripts()),
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
        "tools/release/release.json",
        "tools/tasks/archive.json",
    ):
        source = akmon_root / relative
        text = source.read_text(encoding="utf-8") if source.is_file() else "fixture placeholder\n"
        _write(root / "_aitna" / "akmon" / relative, text)
    # The js tree is carried whole, the way the corpus snapshot carries it (corpus.py::snapshot_js):
    # a derived list over the directory, not a hardcoded one, so a new module joins the fixture
    # without touching this file.
    js_root = akmon_root / "js"
    for path in sorted(js_root.rglob("*")):
        if path.is_file():
            _write(root / "_aitna" / "akmon" / "js" / path.relative_to(js_root), path.read_text(encoding="utf-8"))


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
    """How to run one self-CI leg's subprocess — its argv, (optionally) its environment and cwd."""

    command: list[str]
    env: dict | None = None
    cwd: Path | None = None


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
    result = subprocess.run(
        invocation.command, capture_output=True, text=True, env=invocation.env, cwd=invocation.cwd, check=False
    )
    if result.returncode == 0:
        findings.append(Finding("ok", code, f"{label} passes", "", fixes.ok_fix))
        return True
    detail = (result.stdout or result.stderr).strip().splitlines()
    tail = detail[-1] if detail else f"exit {result.returncode}"
    sys.stderr.write((result.stdout or "") + (result.stderr or ""))
    findings.append(Finding("error", code, f"{label} failed: {tail}", "", fixes.error_fix))
    return False


def _assert_wheel_python_floor(wheel: Path) -> None:
    """Fail unless the built wheel carries exactly one Python >=3.12 metadata field (the C122 floor)."""
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise RuntimeError(f"wheel has {len(metadata_names)} METADATA files; expected exactly one")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
    fields = [line for line in metadata.splitlines() if line.startswith("Requires-Python:")]
    if fields != ["Requires-Python: >=3.12"]:
        rendered = ", ".join(fields) if fields else "missing"
        raise RuntimeError(f"wheel Requires-Python must be exactly >=3.12; got {rendered}")


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
    # The fixture has no linter of its own, so `init` set up ruff with akmon's Python rules, and its
    # pyproject.toml made the fresh block import the Python profile (C127); `sync` materialized both
    # beside the imported guardrail — and nothing else.
    if materialized != [
        "_aitna/.akmon/guardrails/_common.md",
        "_aitna/.akmon/profiles/python.md",
        "_aitna/.akmon/profiles/ruff.toml",
    ]:
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


def _run_generated_hook_commands(fixture: Path, nested: Path, env: dict[str, str] | None = None) -> None:
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
    environment = {**(os.environ if env is None else env), "CLAUDE_PROJECT_DIR": str(fixture)}
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


#: What the npm smoke hides from ``PATH``: every Python a hook or command could fall back to.
_PYTHON_BINARIES = ("python3", "python")


def _python_free_env(env: dict[str, str], scratch: Path) -> dict[str, str]:
    """``env`` with every Python interpreter hidden from its ``PATH`` (one shadow set per binary)."""
    path = env.get("PATH", os.defpath)
    for binary in _PYTHON_BINARIES:
        path = path_without(binary, path, scratch / binary)
    for binary in _PYTHON_BINARIES:
        if shutil.which(binary, path=path) is not None:
            raise RuntimeError(f"could not hide {binary} from PATH ({shutil.which(binary, path=path)})")
    return {**env, "PATH": path}


#: The npm smoke's toolchain: ``node`` runs every command and hook, ``npm`` packs and installs,
#: ``git`` makes the fixture a repository. Nothing else — the leg is offline by design.
_NPM_SMOKE_BINARIES = ("node", "npm", "git")

#: The oldest Node major the npm smoke runs on (``engines.node`` in package.json).
_NODE_FLOOR = 22

#: What every npm smoke prerequisite message names, whichever of them is missing.
_NPM_SMOKE_PREREQUISITES = f"node >= {_NODE_FLOOR}, npm and git on PATH"


def _node_major(version: str) -> int:
    """The major of a ``node --version`` line (``v24.1.0`` → 24)."""
    major = version.strip().removeprefix("v").split(".", 1)[0]
    if not major.isdigit():
        raise RuntimeError(f"node --version printed an unreadable version: {version.strip()!r}")
    return int(major)


def _check_npm_smoke_prerequisites(env: dict[str, str]) -> None:
    """Raise, naming the prerequisite, when ``env``'s ``PATH`` lacks a toolchain binary or holds a node below the floor.

    Checked up front so a missing or old toolchain reads as what it is rather than as the first
    command that happens to trip over it.
    """
    path = env.get("PATH", os.defpath)
    for binary in _NPM_SMOKE_BINARIES:
        if shutil.which(binary, path=path) is None:
            raise RuntimeError(f"the `{binary}` binary is not on PATH")
    node = shutil.which("node", path=path)
    version = subprocess.run([node, "--version"], env=env, capture_output=True, text=True, check=True).stdout
    if _node_major(version) < _NODE_FLOOR:
        raise RuntimeError(f"node {version.strip()} is older than {_NODE_FLOOR}")


def _installed_npm_smoke(akmon_root: Path, tmp_root: Path, verify_env: dict[str, str]) -> None:
    """The npm leg (C106): pack, install into a fresh Node project, and attach it with no Python on the host.

    `npm pack` → `npm install` of the tarball → `akmon init` → `sync --check` → `verify --strict` → every
    generated hook command, run verbatim — with `python3` and `python` hidden from ``PATH`` for all of it,
    so a command or hook that still reaches for Python fails here instead of on a consumer's machine.

    The tarball is installed offline and the pin is then written as the exact version, which is what
    `npm install -D -E akmon` leaves after a publish: the `file:` spelling a tarball install records is a
    range to `verify` (`package.dev-pin`), and the registry is not what this leg tests.
    """
    _check_npm_smoke_prerequisites(verify_env)
    dist = tmp_root / "dist"
    dist.mkdir(parents=True)
    fixture = tmp_root / "node-consumer"
    fixture.mkdir(parents=True)
    # A repository, because the Codex wiring anchors on `git rev-parse --show-toplevel`.
    _checked(["git", "init", "-q", str(fixture)])
    _checked(["npm", "pack", "--silent", "--pack-destination", str(dist)], cwd=akmon_root)
    tarball = next(dist.glob("akmon-*.tgz"), None)
    if tarball is None:
        raise RuntimeError(f"npm pack produced no akmon-*.tgz tarball in {dist}")
    version = json.loads((akmon_root / "package.json").read_text(encoding="utf-8"))["version"]
    _write(fixture / "package.json", json.dumps({"name": "node-consumer", "version": "0.1.0", "private": True}) + "\n")
    _checked(
        ["npm", "install", "--save-dev", "--save-exact", "--offline", "--no-audit", "--no-fund", str(tarball)],
        cwd=fixture,
    )
    manifest = json.loads((fixture / "package.json").read_text(encoding="utf-8"))
    manifest["devDependencies"]["akmon"] = version
    _write(fixture / "package.json", json.dumps(manifest, indent=2) + "\n")

    env = _python_free_env(verify_env, tmp_root / "path")
    akmon = str(fixture / "node_modules" / ".bin" / "akmon")
    _checked([akmon, "init", "--yes", "--project-root", str(fixture)], cwd=fixture, env=env)
    for command in (["sync", "--check"], ["verify", "--strict", "--quiet"]):
        _checked([akmon, *command], cwd=fixture, env=env)

    record = (fixture / "_aitna" / ".akmon.toml").read_text(encoding="utf-8")
    if 'ecosystem = "node"' not in record:
        raise RuntimeError('the Node attach did not record ecosystem = "node"')
    materialized = sorted(
        path.relative_to(fixture).as_posix() for path in (fixture / "_aitna" / ".akmon").rglob("*") if path.is_file()
    )
    # The lint rules are extended in place from node_modules/akmon/profiles/oxlint.json (C109), so only
    # the imported guardrail and the js profile the fresh block imports for a package.json (C127) are
    # materialized.
    if materialized != ["_aitna/.akmon/guardrails/_common.md", "_aitna/.akmon/profiles/js.md"]:
        raise RuntimeError(f"the Node attach materialized more than the imported rules: {materialized}")
    wiring = [command for _, _, command in _generated_hook_commands(fixture)]
    if not wiring or any("/node_modules/akmon/js/hooks/" not in command for command in wiring):
        raise RuntimeError(f"the Node wiring does not run every hook from node_modules/akmon/js/hooks: {wiring}")

    nested = fixture / "src" / "package"
    nested.mkdir(parents=True)
    _run_generated_hook_commands(fixture, nested, env)


#: How a missing toolchain surfaces once a command runs: Python's own ``FileNotFoundError`` for a
#: binary it spawns, and coreutils ``env`` for node missing behind a ``#!/usr/bin/env node`` shebang
#: (npm, the akmon bin) — ``/usr/bin/env: 'node': No such file or directory``, exit 127. The quotes
#: and the reason text follow the locale (curly quotes under a UTF-8 one), so neither is matched.
_MISSING_TOOLCHAIN_RE = re.compile(
    r"No such file or directory: '(?:node|npm|git)'"
    r"|\benv: \W?node\W?: "
    r"|the `(?:node|npm|git)` binary is not on PATH"
    rf"|\bnode \S+ is older than {_NODE_FLOOR}\b"
)


def _npm_smoke_report(detail: str) -> tuple[str, str]:
    """Message and one-sentence fix for a failed npm smoke — a missing or old toolchain is a prerequisite, said so.

    The leg is offline by design (no registry, an ``--offline`` install, a Node ``init`` that looks
    nothing up), so a missing node, npm or git — or a node below the floor — is its only kind of
    prerequisite failure; anything else is a defect in what akmon ships.
    """
    if _MISSING_TOOLCHAIN_RE.search(detail):
        return (
            f"npm smoke could not run: {detail} :: prerequisite of this leg, not a packaging defect — it needs "
            f"{_NPM_SMOKE_PREREQUISITES}",
            f"Install node >= {_NODE_FLOOR} (npm ships with it) and git, and re-run python3 meta/self_ci.py.",
        )
    return (
        f"npm smoke failed: {detail}",
        "Run python3 meta/self_ci.py and fix the Python-free Node install failure it reports.",
    )


def _registry_unreachable(output: str) -> bool:
    """Whether a failed npm invocation names registry reach — a prerequisite, not a shipped defect."""
    if any(marker in output for marker in ("ENOTFOUND", "EAI_AGAIN", "ETIMEDOUT", "ECONNREFUSED")):
        return True
    return "registry.npmjs.org" in output and ("404" in output or "403" in output)


#: The wall-clock bound on one node-toolchain leg, in seconds. The longest leg is the release-depth
#: fuzz (2000 cases): about 0.4 s a case on a 4-core host, so roughly 13 minutes; an hour is several
#: times that and still ends a hung leg rather than the release check hanging for ever.
JS_LEG_TIMEOUT = 3600


def _js_leg(
    findings: list[Finding],
    label: str,
    invocation: LegInvocation,
    *,
    code: str,
    fixes: LegFixes,
) -> None:
    """One node-toolchain leg (C103): run one command and record it, naming a failed prerequisite first.

    The ``_wheel_smoke_report`` stance, applied to the JS legs: a failure that is a missing binary
    or the npm registry's reach is a prerequisite of the leg, not a defect of what akmon ships, so
    the finding says so rather than reporting a bare exit status. Each leg is independent — a red
    one records its finding and the rest still run. A leg whose command is not a node binary
    (the corpus-node leg runs the corpus's own runner) relies on the runner naming the missing
    node prerequisite itself.
    """
    command = invocation.command
    binary = command[0] if command[0] != sys.executable else "node"
    if shutil.which(binary) is None:
        findings.append(
            Finding(
                "error",
                code,
                f"{label} could not run: the `{binary}` binary is not on PATH :: prerequisite of this leg, not a "
                "defect — the node toolchain legs need node >= 22 and npm",
                "",
                "Install node (npm ships with it) and re-run python3 meta/self_ci.py.",
            )
        )
        return
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, cwd=invocation.cwd, check=False, timeout=JS_LEG_TIMEOUT
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        sys.stderr.write(partial if isinstance(partial, str) else partial.decode("utf-8", "replace"))
        findings.append(
            Finding(
                "error",
                code,
                f"{label} timed out: still running after {JS_LEG_TIMEOUT} s and was stopped, so it has no verdict",
                "",
                fixes.error_fix,
            )
        )
        return
    if result.returncode == 0:
        findings.append(Finding("ok", code, f"{label} passes", "", fixes.ok_fix))
        return
    output = (result.stdout or "") + (result.stderr or "")
    sys.stderr.write(output)
    detail = output.strip().splitlines()
    tail = detail[-1] if detail else f"exit {result.returncode}"
    if command[0] == "npm" and _registry_unreachable(output):
        findings.append(
            Finding(
                "error",
                code,
                f"{label} could not run: prerequisite of this leg, not a defect — npm needs registry reach ({tail})",
                "",
                "Check network access to the npm registry and re-run python3 meta/self_ci.py.",
            )
        )
        return
    findings.append(Finding("error", code, f"{label} failed: {tail}", "", fixes.error_fix))


#: The differential fuzz leg's budget per depth: (cases, seed). The bounded leg is self-CI's
#: (about 45 s on a 4-core host); the release depth draws a fresh seed (``None``) so successive
#: releases explore different cases, and prints it so a failure reproduces.
FUZZ_BUDGETS: dict[str, tuple[int, int | None]] = {"bounded": (120, 0), "release": (2000, None)}


#: Where the printed fuzz rerun command writes its draft scenarios: under the repository's
#: gitignored ``/.tmp`` scratch, so the owner finds them at a fixed path and they never stage.
#: The leg's own run keeps fuzz.py's default (a fresh temp dir) so self-CI writes nothing in the tree.
FUZZ_EMIT_DIR = ".tmp/fuzz-drafts"


def fuzz_rerun_command(cases: int, seed: int) -> str:
    """The command that reruns the fuzz leg's ``cases`` at ``seed`` and keeps its drafts in ``FUZZ_EMIT_DIR``."""
    return f"python3 meta/conformance/fuzz.py --cases {cases} --seed {seed} --emit {FUZZ_EMIT_DIR}"


def fuzz_budget(depth: str) -> tuple[int, int]:
    """The (cases, seed) of the fuzz leg at ``depth``: a release run's seed is drawn fresh."""
    cases, seed = FUZZ_BUDGETS[depth]
    return cases, secrets.randbelow(2**31) if seed is None else seed


def _run(akmon_root: Path, fuzz_depth: str = "bounded") -> list[Finding]:
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
        try:
            _installed_npm_smoke(akmon_root, fixture / "npm-smoke", verify_env)
        except Exception as exc:  # noqa: BLE001 — the leg owns pack, install, attach and hook execution
            detail = " ".join(str(exc).split()) or type(exc).__name__
            message, fix = _npm_smoke_report(detail)
            findings.append(Finding("error", "selfci.npm-smoke", message, "", fix))
        else:
            findings.append(
                Finding(
                    "ok",
                    "selfci.npm-smoke",
                    "npm smoke passes with python3 hidden (pack, install, init, sync, verify, hook)",
                    "",
                    "Keep the Python-free Node install green before every release.",
                )
            )
    # Akmon's own declarations, checked against akmon's own tree rather than the fixture: the
    # capability matrix is a property of what akmon ships, not of a synthetic consumer's use of it.
    findings.extend(always_loaded_caps.check_always_loaded(akmon_root))
    findings.extend(capabilities.check_capabilities(akmon_root))
    findings.extend(canary.check_canary(akmon_root))
    findings.extend(decision_records.check_decision_records(akmon_root))
    findings.extend(runtime_checks.check_declared_runtimes(akmon_root))
    # The conformance corpus (C101): the language-neutral spec both implementations pass,
    # run against the Python implementation plus its coverage gate. The leg is independent of
    # the fixture chain on purpose: a corpus failure must not hide the fixture findings, and
    # the fixture's health says nothing about the corpus.
    _leg(
        findings,
        "conformance corpus",
        LegInvocation(
            [sys.executable, str(akmon_root / "meta" / "conformance" / "runner.py"), "--tree", str(akmon_root)]
        ),
        code="selfci.conformance",
        fixes=LegFixes(
            ok_fix="Keep the corpus green on the Python implementation and its coverage gate.",
            error_fix=(
                "Run python3 meta/conformance/runner.py --tree <repo> and fix the failing "
                "scenario or the coverage gap it names."
            ),
        ),
    )
    # The node toolchain (C103, ADR 0020 D03): the JS implementation's own checks, appended
    # after the conformance leg and independent of each other the same way — a red leg records
    # its finding (naming the prerequisite when that is what failed) and the rest still run.
    _js_leg(
        findings,
        "js deps (npm ci)",
        LegInvocation(["npm", "ci", "--ignore-scripts"], cwd=akmon_root),
        code="selfci.js-deps",
        fixes=LegFixes(
            ok_fix="Keep the committed dev lockfile in sync with package.json's exact-pinned devDependencies.",
            error_fix="Run npm ci --ignore-scripts at the repository root and fix the install failure it reports.",
        ),
    )
    _js_leg(
        findings,
        "js typecheck (tsc --checkJs)",
        LegInvocation(["npx", "--no-install", "tsc", "--checkJs", "--noEmit", "-p", "."], cwd=akmon_root),
        code="selfci.js-typecheck",
        fixes=LegFixes(
            ok_fix="Keep the JSDoc-annotated js/ implementation type-clean.",
            error_fix=(
                "Run npx --no-install tsc --checkJs --noEmit at the repository root and fix the type errors it reports."
            ),
        ),
    )
    _js_leg(
        findings,
        "js unit tests (node --test js/**/*.test.mjs)",
        LegInvocation(["node", "--test", "js/**/*.test.mjs"], cwd=akmon_root),
        code="selfci.js-unit",
        fixes=LegFixes(
            ok_fix="Keep the js/ tests green.",
            error_fix="Run node --test 'js/**/*.test.mjs' and fix the failing test it names.",
        ),
    )
    _js_leg(
        findings,
        "js lint (oxlint)",
        LegInvocation(["npx", "--no-install", "oxlint", "."], cwd=akmon_root),
        code="selfci.js-lint",
        fixes=LegFixes(
            ok_fix="Keep the repository oxlint-clean under akmon's own ruleset (profiles/oxlint.json).",
            error_fix="Run npx --no-install oxlint at the repository root and fix the lint errors it reports.",
        ),
    )
    _js_leg(
        findings,
        "js format (oxfmt)",
        LegInvocation(["npx", "--no-install", "oxfmt", "--check", "."], cwd=akmon_root),
        code="selfci.js-format",
        fixes=LegFixes(
            ok_fix="Keep the JS sources formatted with oxfmt.",
            error_fix=(
                "Run npx --no-install oxfmt at the repository root to format the JS sources, then review the diff."
            ),
        ),
    )
    _js_leg(
        findings,
        "conformance corpus (node units, hooks, cli and tools)",
        LegInvocation(
            [
                sys.executable,
                str(akmon_root / "meta" / "conformance" / "runner.py"),
                "--tree",
                str(akmon_root),
                "--impl",
                "node",
                "--area",
                "units",
                "--area",
                "hooks",
                "--area",
                "cli",
                "--area",
                "tools",
            ],
            cwd=akmon_root,
        ),
        code="selfci.corpus-node",
        fixes=LegFixes(
            ok_fix=(
                "Keep the unit tables green on the node implementation through probe.mjs, every hook "
                "scenario green on the JS hooks run from node_modules/akmon, and every CLI scenario of a "
                "command with a JS port green on the JS CLI, and every scenario of a ported tool green on its JS twin."
            ),
            error_fix=(
                "Run python3 meta/conformance/runner.py --tree <repo> --impl node --area units --area hooks "
                "--area cli --area tools and fix the prerequisite or the failing scenario it names."
            ),
        ),
    )
    # Differential fuzzing (C111, design node-consumers.md §5 gate 4): every hook scenario's payload,
    # mutated, through both implementations. Bounded by default (a fixed seed, so a red leg is
    # reproducible as is); the release check asks for the deep run, whose fresh seed the label carries.
    cases, seed = fuzz_budget(fuzz_depth)
    _js_leg(
        findings,
        f"differential hook fuzz ({fuzz_depth}: {cases} cases, seed {seed})",
        LegInvocation(
            [
                sys.executable,
                str(akmon_root / "meta" / "conformance" / "fuzz.py"),
                "--cases",
                str(cases),
                "--seed",
                str(seed),
            ],
            cwd=akmon_root,
        ),
        code="selfci.fuzz",
        fixes=LegFixes(
            ok_fix="Keep the Python and Node hooks one behaviour on mutated payloads (or each difference a DV row).",
            error_fix=(
                f"Run {fuzz_rerun_command(cases, seed)}, review the draft scenarios it writes under "
                f"{FUZZ_EMIT_DIR}/, and fix the twin that is wrong or record a DIVERGENCES.md row plus a "
                "fuzz.toml entry."
            ),
        ),
    )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run every self-CI leg against akmon's own tree and print the findings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings and errors.")
    parser.add_argument(
        "--fuzz-depth",
        choices=sorted(FUZZ_BUDGETS),
        default="bounded",
        help="the differential fuzz leg's budget: bounded (self-CI) or release (the release check's deep run)",
    )
    args = parser.parse_args(argv)

    findings = _run(_AKMON_ROOT, args.fuzz_depth)
    print_findings(findings, quiet=args.quiet)
    return exit_code(findings, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
