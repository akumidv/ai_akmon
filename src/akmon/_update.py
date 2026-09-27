"""``akmon update`` — move a project to another akmon release, then realign it (A23, C92).

The mechanized form of BOOTSTRAP's "Pull the latest shared layer into a project": resolve the
target release, move the pin the way the project's mount mode keeps it, run ``init`` from the
version the project now pins, then ``sync --check`` and ``verify --strict``. What it settles
(A23, owner decisions):

- **Target.** ``--ref`` when given, else the newest final release tag (``vX.Y.Z``) the akmon
  repository advertises, read with ``git ls-remote``; PyPI joins once akmon is published there
  (V4). A pre-release is never the newest.
- **Direction.** Without ``--ref`` the pin never moves back: a project at or past the newest
  release is realigned where it is. With ``--ref`` an older release is a rollback, allowed and
  announced.
- **Per mount mode.** ``submodule``: fetch the release tags into the mount, then ``init --ref``
  checks the target out and leaves it unstaged. ``package``: uv only — ``uv add`` rewrites the
  pin in its PEP 735 group and syncs the environment, then the project's own, now updated, CLI
  runs ``init``; any other manager gets the command printed. ``vendored``: the mount is a copy of
  the tree of the CLI that runs ``init``, so ``init`` runs from exactly the pinned release — in
  process when this CLI is it, through ``uvx`` otherwise. ``subtree``: ``git subtree pull``
  commits, so it is printed, never run.
- **Never commits** (D5). A moved pin is a change for the owner to review and stage; the run
  ends with what to read, what to stage and what Codex needs re-approved.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from akmon import __version__, _init, _tree, cli

# `git fetch` of the release tags is the one step that waits on the network without a bound of
# its own; `uv add` and `uvx` carry their own.
_FETCH_TIMEOUT_SECONDS = 300


def _jsondata() -> ModuleType:
    """The embedded tree's ``common.jsondata`` — the one reader of the shared update data."""
    return cli._embedded_common_module(_tree.embedded_tree_root(), "jsondata")


def _data() -> Any:
    """The shared update text and tables (``update.json``, beside this module), read on the call.

    Never at import time, with no module-level cache and no swallowed ``DataFileError`` (C102).
    """
    return _jsondata().read(Path(__file__).parent / "update.json")


class _UpdateError(Exception):
    """A refusal, or a step that failed before ``init`` ran; printed, exit 2."""


@dataclass(frozen=True)
class _Plan:
    """Where the pin goes: the target, the version the record holds, and whether the pin moves."""

    target: str
    current: str | None
    move: bool
    note: str


def _versions() -> ModuleType:
    return cli._embedded_common_module(_tree.embedded_tree_root(), "versions")


def _plan(current: str | None, target: str, *, explicit: bool) -> _Plan:
    """Compare the recorded version with the target; the pin moves back only when ``--ref`` says so.

    The six note texts live in ``update.json`` (``plan_notes``), keyed by the branch taken.
    """
    versions = _versions()
    jsondata = _jsondata()
    notes = _data()["plan_notes"]
    then = versions.order_key(target)
    now = versions.order_key(current) if current else None
    if then is None:
        move, note = True, jsondata.fill(notes["not_a_release"], {"target": target})
    elif now is None:
        move, note = True, jsondata.fill(
            notes["record_no_version"], {"target": target, "current": current or "none"}
        )
    elif then > now:
        move, note = True, jsondata.fill(notes["forward"], {"current": current, "target": target})
    elif then == now:
        move, note = False, jsondata.fill(notes["already"], {"target": target})
    elif explicit:
        move, note = True, jsondata.fill(notes["rollback"], {"current": current, "target": target})
    else:
        move, note = False, jsondata.fill(notes["past_newest"], {"current": current, "target": target})
    return _Plan(target=target, current=current, move=move, note=note)


def _log(message: str) -> None:
    print(f"akmon update: {message}", flush=True)


def _run(command: list[str], cwd: Path, *, timeout: int | None = None) -> int:
    """Run ``command`` with its output on this terminal; its exit code."""
    try:
        return _init._run(command, cwd=cwd, timeout=timeout).returncode
    except (OSError, subprocess.SubprocessError) as exc:
        raise _UpdateError(f"cannot run `{command[0]}`: {exc}") from exc


def _recorded_versions(root: Path, aitna: str) -> tuple[str | None, str | None]:
    """``akmon_version`` and ``last_realign`` from the integration record."""
    fields = _init._record_fields(root, aitna)
    version, realigned = fields.get("akmon_version"), fields.get("last_realign")
    return (
        version if isinstance(version, str) and version else None,
        realigned if isinstance(realigned, str) and realigned else None,
    )


# --------------------------------------------------------------------------------------
# per mount mode: move the pin, run init — the init exit code, and the launcher for the checks
# --------------------------------------------------------------------------------------

_Moved = tuple[int, Path | None]


def _update_submodule(root: Path, aitna: str, plan: _Plan, repo: str) -> _Moved:
    """Fetch the release tags from ``repo``, where the target was read, then ``init --ref`` moves the pin."""
    init_argv = ["--project-root", str(root), "--yes"]
    if plan.move:
        _log(f"fetching release tags into {aitna}/akmon")
        if _run(["git", "fetch", "--quiet", "--tags", repo], root / aitna / "akmon", timeout=_FETCH_TIMEOUT_SECONDS):
            raise _UpdateError(
                f"`git fetch --tags` failed in {aitna}/akmon — it needs git and network access to {repo}"
            )
        init_argv += ["--ref", plan.target]
    return _init.main(init_argv), None


def _update_package(root: Path, aitna: str, plan: _Plan, repo: str) -> _Moved:
    """``uv add`` the new pin into its group, then the project's own CLI runs ``init``."""
    del aitna  # package mode keeps nothing of akmon's under the dev layer to move
    launcher = root / ".venv" / "bin" / "akmon"
    if plan.move:
        # The pin moves in the spelling the project keeps it in (both measured, uv 0.11.21): a PEP 508
        # pin needs `--raw`, or uv moves its URL into `[tool.uv.sources]`; a pin whose URL already sits
        # there must go without it, or that stale entry still wins resolution.
        raw = [] if _pin_in_uv_sources(root) else ["--raw"]
        command = ["uv", "add", *raw, "--group", _pin_group(root), f"akmon @ git+{repo}@{plan.target}"]
        if shutil.which("uv") is None:
            raise _UpdateError(
                _jsondata().fill(
                    _data()["package_uv_missing"],
                    {"target": plan.target, "command": shlex.join(command)},
                )
            )
        _log(f"moving the pin: {shlex.join(command)}")
        code = _run(command, root)
        if code != 0:
            raise _UpdateError(f"`uv add` failed ({code}) — see its output above")
    if not launcher.is_file():
        raise _UpdateError(
            _jsondata().fill(
                _data()["package_launcher_missing"], {"launcher": str(launcher.relative_to(root))}
            )
        )
    return _run([str(launcher), "init", "--project-root", str(root), "--yes"], root), launcher


def _pin_group(root: Path) -> str:
    """The PEP 735 group that pins akmon — the one declaration ``uv add`` can move in place."""
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    status = sync_mod.package_pin_status(root)
    if status != "dev":
        raise _UpdateError(
            f"mode 'package' needs akmon pinned in a dev group of pyproject.toml, and it is not (found: {status}) — "
            "`akmon verify --strict` names the fix"
        )
    groups = sync_mod._table(sync_mod._read_manifest(root), "dependency-groups")
    for name, requirements in groups.items():
        if sync_mod._names_akmon(requirements):
            return name
    raise _UpdateError(
        "the akmon pin is not in a [dependency-groups] table, so `uv add` cannot move it in place — move it with "
        "the manager that declares it, then run `akmon init`"
    )


def _pin_in_uv_sources(root: Path) -> bool:
    """Whether ``[tool.uv.sources]`` names akmon — uv's own spelling of a git pin, a bare name in the group."""
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    return "akmon" in sync_mod._table(sync_mod._read_manifest(root), "tool", "uv", "sources")


def _update_vendored(root: Path, aitna: str, plan: _Plan, repo: str) -> _Moved:
    """Run ``init`` from exactly the pinned release: this CLI when it is that release, else ``uvx``."""
    del aitna  # init owns the mount; the release that runs it decides what the copy holds
    versions = _versions()
    ref = plan.target if plan.move else plan.current
    if ref and versions.is_final(ref) and versions.split_version(ref)[0] == versions.split_version(__version__)[0]:
        return _init.main(["--project-root", str(root), "--yes"]), None
    if not plan.move and not (ref and versions.is_final(ref)):
        raise _UpdateError(
            _jsondata().fill(_data()["vendored_not_fetchable"], {"recorded": ref or "version"})
        )
    tag = ref if plan.move else f"v{versions.split_version(ref)[0]}"
    command = ["uvx", "--from", f"git+{repo}@{tag}", "akmon", "init", "--project-root", str(root), "--yes"]
    if shutil.which("uvx") is None:
        raise _UpdateError(
            _jsondata().fill(
                _data()["vendored_uvx_missing"], {"tag": tag, "command": shlex.join(command)}
            )
        )
    _log(f"running init from akmon {tag}: {shlex.join(command)}")
    return _run(command, root), None


def _update_subtree(root: Path, aitna: str, plan: _Plan, repo: str) -> _Moved:
    """Realign in place; a move is ``git subtree pull``, which commits, so it is printed instead."""
    if not plan.move:
        return _init.main(["--project-root", str(root), "--yes", "--ref", str(plan.current)]), None
    jsondata = _jsondata()
    data = _data()
    commands = [
        jsondata.fill(data["subtree_pull_command"], {"aitna": aitna, "repo": repo, "target": plan.target}),
        jsondata.fill(data["subtree_realign_command"], {"target": plan.target}),
    ]
    raise _UpdateError(data["subtree_refusal"] + "\n" + "\n".join(commands))


_UPDATERS: dict[str, Callable[[Path, str, _Plan, str], _Moved]] = {
    "submodule": _update_submodule,
    "package": _update_package,
    "vendored": _update_vendored,
    "subtree": _update_subtree,
}


# --------------------------------------------------------------------------------------
# after init: the checks, and what is left to the owner
# --------------------------------------------------------------------------------------


def _checks(root: Path, launcher: Path | None) -> int:
    """``sync --check``, then ``verify --strict``, run by the tree that now governs; the first failure."""
    jsondata = _jsondata()
    data = _data()
    for script, flag in data["checks"]:
        argv = [flag, "--project-root", str(root)]
        _log(jsondata.fill(data["checks_running"], {"script": script, "flag": flag}))
        code = _run([str(launcher), script, *argv], root) if launcher else cli._dispatch(script, argv, cwd=root)
        if code != 0:
            print(
                jsondata.fill(data["checks_failed"], {"script": script, "flag": flag, "code": code}),
                file=sys.stderr,
            )
            return code
    return 0


def _closing(root: Path, aitna: str, mode: str, plan: _Plan, last_realign: str | None) -> None:
    """What the update leaves to the owner (``update.json``, ``closing_*``), one numbered line each."""
    jsondata = _jsondata()
    data = _data()
    steps = []
    if plan.move:
        steps.append(
            jsondata.fill(
                data["closing_changelog"],
                {"last": last_realign or plan.current or "the previous version", "target": plan.target},
            )
        )
    staged = "`pyproject.toml` and `uv.lock`" if mode == "package" else f"`{aitna}/akmon`"
    steps.append(jsondata.fill(data["closing_review"], {"staged": staged}))
    if plan.move:
        steps.append(jsondata.fill(data["closing_bump"], {"aitna": aitna}))
    if (root / ".codex" / "hooks.json").is_file():
        steps.append(data["closing_codex"])
    print()
    _log(data["closing_left_to_you"])
    for index, step in enumerate(steps, start=1):
        print(jsondata.fill(data["closing_step"], {"index": index, "step": step}), flush=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akmon update",
        description=(
            "Move this project to another akmon release, then realign it: init, sync --check, verify --strict. "
            "Never commits."
        ),
    )
    parser.add_argument("--ref", help="Release to move to (default: the newest release tag; an older one rolls back).")
    parser.add_argument("--project-root", type=Path, help="Project to update. Defaults to the current directory.")
    parser.add_argument("--aitna-root", help="Dev-layer root, project-root-relative (default: AITNA_ROOT or _aitna).")
    repo = _init.akmon_repo()
    parser.add_argument("--repo", default=repo, help=f"akmon repository URL (default: {repo}).")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Update the project to ``--ref`` or the newest release; the first failing exit code, else 0."""
    args = _build_parser().parse_args(argv)
    root = (args.project_root or Path.cwd()).resolve()
    try:
        aitna = _init._effective_aitna_root(args.aitna_root, root)
        os.environ["AITNA_ROOT"] = aitna
        mode = _init._recorded_mount(root, aitna)
        if mode not in _UPDATERS:
            raise _UpdateError(
                _jsondata().fill(_data()["missing_record"], {"root": str(root), "aitna": aitna})
            )
        current, last_realign = _recorded_versions(root, aitna)
        target = args.ref or _init._package_default_ref(args.repo, root)
        plan = _plan(current, target, explicit=args.ref is not None)
        _log(
            _jsondata().fill(_data()["banner"], {"root": str(root), "mode": mode, "note": plan.note})
        )
        code, launcher = _UPDATERS[mode](root, aitna, plan, args.repo)
    except (_UpdateError, _init._InitError) as exc:
        print(f"akmon update: {exc}", file=sys.stderr)
        return 2
    if code != 0:
        print(_jsondata().fill(_data()["init_failed"], {"code": code}), file=sys.stderr)
        return code
    code = _checks(root, launcher)
    _closing(root, aitna, mode, plan, last_realign)
    return code
