"""``akmon init`` — attach the standard to a project (C37, design ``meta/design/packaging/``).

This is the mechanized half of ``BOOTSTRAP.md`` §A: mount the standard in one of the four
modes (ADR 0009 §3-4), create the ``<AITNA_ROOT>/`` local layout, write the integration
record, run ``sync`` and the model-routing initializer, and print the steps it deliberately
did **not** do. The judgment steps stay with the agent/owner — archetype classification and
the guardrail/profile map (``ARCHETYPES.md``), and the ``[test].runner`` pin — so ``init``
scaffolds their slots and names them as next steps rather than guessing.

Two properties the rest of the tooling already promises and this command must not break:

- **Idempotent.** A re-run realigns: it never rewrites project text it did not author. An
  existing ``AGENTS.md`` akmon block, ``TASKS.md``, memory index, or agent charter is left
  exactly as it is; ``.gitignore`` gains only the lines it lacks; ``.akmon.toml`` keys are
  upserted one by one (``sync.py::_upsert_toml_key``), preserving comments and every
  hand-written field. Changing the *mount mode* is not a realign but a migration — it moves
  every path the hand-owned block names — so it is refused unless ``--switch-mode`` says so,
  and then the edits `init` must not make are printed rather than skipped silently.
- **Never commits, and stages only what git staged for it.** ``init`` creates no commit. The
  single index write is git's own: ``git submodule add`` writes ``.gitmodules`` and the gitlink
  because that is how git implements a submodule, and `init` corrects *that* entry to the ref it
  actually checked out instead of leaving git's initial value behind. It happens only on the run
  that creates the submodule; moving an **existing** pin with ``--ref`` is a pin bump, which is
  the owner's to stage and commit (D5), so that case is left unstaged and printed as a step.
  Mode ``subtree`` is refused outright while the subtree is absent, because ``git subtree add``
  *commits*; `init` prints the command for the owner to run. Changing mount mode is refused
  while the previous mount is still on disk — removing it is a deletion `init` must not make.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from akmon import __version__, _tree, cli

MODES = ("submodule", "vendored", "subtree", "package")


def _jsondata() -> ModuleType:
    """The embedded tree's ``common.jsondata`` — the one reader of the shared init data."""
    return cli._embedded_common_module(_tree.embedded_tree_root(), "jsondata")


def _data() -> Any:
    """The shared init text and tables (``init.json``, beside this module), read on the call.

    Never at import time, with no module-level cache and no swallowed ``DataFileError``: a
    data file the standard ships is a dependency, not an optional input (C102).
    """
    return _jsondata().read(Path(__file__).parent / "init.json")


def akmon_repo() -> str:
    """The standard's canonical repository URL (``init.json``)."""
    return _data()["akmon_repo"]


# ``git ls-remote`` prints one "<sha> <ref>" pair per line — a stray line with any other
# field count is not a ref listing and is skipped rather than misparsed.
_LS_REMOTE_FIELD_COUNT = 2

# The top-level members that *are* the standard tree (``init.json``, ``tree_members``)
# mirror ``[tool.hatch.build.targets.wheel.force-include]`` in ``pyproject.toml``: mode
# ``vendored`` copies exactly what mode ``package`` would ship, so a vendored mount is not a
# poorer flavor of the standard (ADR 0009 §1, "yes for parity"). The embedded tree resolves
# to the akmon repo root in a source checkout, which carries development-only members
# (``src/``, ``.git/``, ``tests/``, ``AGENTS.md``, …) that the wheel does not ship — an
# allowlist keeps both carriers producing the same mount. ``meta/tests/test_init.py``
# asserts the data file and the pyproject force-include list stay equal.


def tree_members() -> list[str]:
    """The standard tree's top-level members (``init.json``); mode ``vendored`` copies exactly these."""
    return _data()["tree_members"]


# What never enters the mount. The caches are noise; ``*.test.mjs`` is the one entry here that is
# not about noise: a mounted file sits *inside the consumer's own project root*, and both JS
# tools scan that root by default — measured, a consumer running ``node --test`` over a vendored
# mount discovered 49 tests and failed 4 of them (akmon's own suites, resolving paths against a
# tree they do not live in), and ``eslint`` reported 58 problems for files the project did not
# write. The same content under ``node_modules/akmon/js`` — mode ``package`` — reports 1 test and
# 0 problems, because both tools skip that directory (M116). Tests are dev-only material, which is
# the rule the member allowlist already applies to ``src/`` and ``tests/``; the JS tree simply
# carried its tests past it.
_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.py[cod]", ".pytest_cache", ".ruff_cache", ".git", ".DS_Store", "*.test.mjs"
)


def _mount_gitignore() -> str:
    """The mounted tree's own ``.gitignore`` text (``init.json``)."""
    return _data()["mount_gitignore"]


def _tree_markers() -> tuple[str, ...]:
    """The markers a directory must carry before `init` will treat it as *this* standard's tree.

    `bin/sync.py` alone is not an identity: a vendored realign deletes and re-copies whole
    top-level members, so mistaking someone's directory for akmon destroys their work. Four
    markers spread across three top-level members is a threshold no unrelated tree crosses
    by accident, while every akmon version that has ever shipped a mount clears it.
    """
    return tuple(_data()["tree_markers"])


def _is_akmon_tree(path: Path) -> bool:
    return all((path / marker).is_file() for marker in _tree_markers())


# --------------------------------------------------------------------------------------
# small process / git helpers
# --------------------------------------------------------------------------------------


def _run(
    cmd: list[str], *, cwd: Path | None = None, capture: bool = False, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd``; never inherit a credential prompt (an attach must not hang on one)."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=capture,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _git_output(args: list[str], *, cwd: Path) -> str | None:
    """``git <args>`` stdout, stripped — ``None`` when git fails or is absent."""
    try:
        completed = _run(["git", *args], cwd=cwd, capture=True)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _is_submodule(root: Path, relative: str) -> bool:
    """Whether **git** records ``relative`` as a submodule of ``root``.

    The question "is this mount a submodule?" has exactly one authority, and it is not the file
    system: a vendored copy and a subtree carry the same ``bin/sync.py`` a submodule does, so
    "the tree is there" answered it wrong in both directions — a vendored → submodule switch
    finished without ever creating a ``.gitmodules`` or a gitlink, and a submodule → vendored
    switch overwrote files *inside* the submodule. Both spellings count: the staged/committed
    gitlink (mode ``160000``) and a ``.gitmodules`` entry, since a fresh `git submodule add`
    writes both and a half-removed one may leave either.
    """
    entry = _git_output(["ls-files", "--stage", "--", relative], cwd=root)
    if entry and entry.split(maxsplit=1)[0] == "160000":
        return True
    listing = _git_output(["config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"], cwd=root)
    return any(line.split(maxsplit=1)[-1].strip() == relative for line in (listing or "").splitlines() if line.strip())


def _is_git_repo(root: Path) -> bool:
    return _git_output(["rev-parse", "--is-inside-work-tree"], cwd=root) == "true"


def _remote_reachable(repo: str, root: Path) -> bool:
    """Whether ``repo`` answers a ref listing — the capability a submodule/subtree needs."""
    try:
        completed = _run(["git", "ls-remote", "--exit-code", "--heads", repo], cwd=root, capture=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _version_key(tag: str) -> tuple:
    """Sort key for a ``vX.Y.Z`` tag; non-numeric parts sort last but stay ordered."""
    parts = tag.lstrip("v").split(".")
    key = [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in parts]
    return tuple(key)


def _newest_release(tags: Iterable[str]) -> str | None:
    """The newest final release tag (``vX.Y.Z``) among ``tags``; ``None`` when there is none.

    One rule for "latest" wherever ``init`` or ``update`` picks a pin: a pre-release or any other
    non-final tag never counts, because it is not the reviewed state a release tag stands for.
    """
    versions = cli._embedded_common_module(_tree.embedded_tree_root(), "versions")
    releases = [tag for tag in tags if tag.startswith("v") and versions.is_final(tag)]
    return max(releases, key=_version_key) if releases else None


def _latest_tag(repo_dir: Path) -> str | None:
    """Newest local release tag, or ``None`` when ``repo_dir`` carries none."""
    listing = _git_output(["tag", "--list", "v*"], cwd=repo_dir)
    return _newest_release(line.strip() for line in (listing or "").splitlines())


def _package_default_ref(repo: str, root: Path) -> str:
    """Newest release tag advertised by ``repo``, never one synthesized from a version.

    Read with ``git ls-remote``, so it needs git and network access to ``repo``; the failure says
    so and names ``--ref`` as the way around it.
    """
    unreachable = (
        f"cannot discover the latest release tag from {repo!r} (`git ls-remote` needs git and network access "
        "to it); pass --ref explicitly"
    )
    try:
        completed = _run(
            ["git", "ls-remote", "--tags", "--refs", repo, "refs/tags/v*"],
            cwd=root,
            capture=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _InitError(unreachable) from exc
    if completed.returncode != 0:
        raise _InitError(unreachable)
    tags = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == _LS_REMOTE_FIELD_COUNT and fields[1].startswith("refs/tags/v"):
            tags.append(fields[1].removeprefix("refs/tags/"))
    newest = _newest_release(tags)
    if newest is None:
        raise _InitError(f"repository {repo!r} advertises no release tags; pass --ref explicitly")
    return newest


def _describe(repo_dir: Path) -> str | None:
    """``git describe --tags`` — the recorded pin spelling for a mounted mode (BOOTSTRAP §C)."""
    return _git_output(["describe", "--tags"], cwd=repo_dir)


# --------------------------------------------------------------------------------------
# paths / mode resolution
# --------------------------------------------------------------------------------------


def _effective_aitna_root(flag: str | None, root: Path) -> str:
    """The dev-layer root this run will use — from ``--aitna-root`` or from ``AITNA_ROOT``.

    Validated whichever way it arrived.

    The two sources are one contract, so validating only the flag validated nothing: the flag's
    entire effect is to *set* the environment variable, and a caller who exports the variable
    instead reaches every code path the flag reaches. ``AITNA_ROOT=../escaped akmon init`` wrote
    the record, the backlog, the charters and the mount into a sibling directory and exited 0.
    """
    source = "--aitna-root" if flag is not None else "AITNA_ROOT"
    raw = flag if flag is not None else os.environ.get("AITNA_ROOT")
    if raw is None or not raw.strip():
        return cli._project_root_lib().AITNA_ROOT_DEFAULT
    return _validated_aitna_root(raw, root, source)


def _validated_aitna_root(value: str, root: Path, source: str = "--aitna-root") -> str:
    """A dev-layer root as a project-root-relative path, or a hard error.

    `AITNA_ROOT` is *project-root-relative* by contract (BOOTSTRAP §A) and `init` writes a whole
    layout under it — backlog, memory, charters, the integration record, and in package mode the
    materialized imported guardrails. An absolute path or one climbing out with `..` would
    scatter all of that outside the project the caller named, silently, because every later step
    simply follows the variable. Checked both lexically and by resolution: a symlinked segment
    can leave the project without a single `..` in the string.
    """
    raw = value.strip()
    # Absoluteness is decided on the *raw* value: stripping the slashes first would turn
    # `/tmp/escaped` into the innocent-looking relative `tmp/escaped` and let it through.
    if Path(raw).is_absolute():
        raise _InitError(f"{source} must be relative to the project root and stay inside it: {value!r}")
    cleaned = raw.strip("/")
    if not cleaned:
        raise _InitError(f"{source} cannot be empty")
    candidate = Path(cleaned)
    if ".." in candidate.parts:
        raise _InitError(f"{source} must be relative to the project root and stay inside it: {value!r}")
    if root.resolve() not in (root / candidate).resolve().parents:
        raise _InitError(f"{source} resolves outside the project root: {(root / candidate).resolve()}")
    return cleaned


def _recorded_mount(root: Path, aitna: str) -> str | None:
    """The mount mode a previous attach recorded, or ``None`` for a first attach.

    Read by the embedded tree's ``common/record.py``, the one reader (C75). The path is built
    here rather than asked for because ``aitna`` is the dev-layer name this attach resolved.
    """
    value = _record_fields(root, aitna).get("mount")
    return value if isinstance(value, str) and value else None


def _record_fields(root: Path, aitna: str) -> dict:
    """The integration record under ``aitna`` as a dict; ``{}`` when there is none.

    Read by the embedded tree's ``common/record.py``, the one reader (C75); ``update`` asks here
    rather than naming the record's path a second time.
    """
    record = cli._embedded_common_module(_tree.embedded_tree_root(), "record")
    return record.read_akmon_toml(root / aitna / ".akmon.toml")


def _old_mount_removal(previous: str, relative: str) -> str:
    """The commands that retire a ``previous``-mode mount — printed, never run.

    Every one of them deletes tracked files (and the submodule form rewrites git's own
    bookkeeping), so they are the owner's to run and to commit (D5).
    """
    removals = _data()["old_mount_removal"]
    return _jsondata().fill(removals.get(previous, removals["vendored"]), {"relative": relative})


def _mode_switch_steps(previous: str, mode: str, aitna: str) -> list[str]:
    """What a human must do after a mount-mode migration — the parts `init` will not do.

    Switching modes moves every path the standard is reached by, and those paths live in the
    one file `init` must not rewrite: the hand-owned `AGENTS.md` akmon block. Listing the exact
    edits is the honest half of the deal; the other half is refusing to perform the switch
    silently (see `main`).
    """
    jsondata = _jsondata()
    data = _data()
    base = f"{aitna}/.akmon" if mode == "package" else f"{aitna}/akmon"
    resolution = (
        data["mode_switch_link_resolution_package"]
        if mode == "package"
        else jsondata.fill(data["mode_switch_link_resolution_mounted"], {"aitna": aitna})
    )
    steps = [
        jsondata.fill(
            data["mode_switch_step"],
            {"previous": previous, "mode": mode, "base": base, "link_resolution": resolution},
        )
    ]
    if mode == "package":
        steps.append(jsondata.fill(data["mode_switch_remove_mount"], {"aitna": aitna}))
    return steps


def _default_mode(root: Path, repo: str) -> tuple[str, str]:
    """The mode to use when the caller named none, plus the reason — printed, never silent.

    (ADR 0009 §3): ``submodule`` for a git repository that can reach the akmon repo, else
    ``vendored``, which needs neither git nor a network.
    """
    if not _is_git_repo(root):
        return "vendored", "the project is not a git repository"
    if not _remote_reachable(repo, root):
        return "vendored", f"{repo} is not reachable from here"
    return "submodule", "a git repository that can reach the akmon repository"


def _tag_for_version(version: str) -> str:
    """The GitHub ref a consumer's human-facing links should point at: the release tag for a released version.

    ``main`` for a development one (no tag exists for it yet).

    "Released" is asked of ``common/versions.py``, the sole owner of that rule (C54), rather than
    answered again here: the substring heuristic this replaced missed ``.postN`` entirely and
    would have pointed a consumer at a tag that does not exist.
    """
    versions = cli._embedded_common_module(_tree.embedded_tree_root(), "versions")
    if not versions.is_final(version):
        return "main"
    return f"v{versions.split_version(version)[0]}"


# --------------------------------------------------------------------------------------
# mount modes
# --------------------------------------------------------------------------------------


@dataclass
class _Attach:
    """One ``init`` run: the project, its dev layer, the mount mode, and the steps left to a person.

    ``previous`` is the mount mode the integration record held before this run; ``next_steps``
    collects what the run reports at its end instead of doing itself.
    """

    root: Path
    aitna: str
    mode: str
    previous: str | None
    next_steps: list[str] = field(default_factory=list)

    @property
    def package_mode(self) -> bool:
        """Mode ``package`` mounts no tree: the installed package is the standard."""
        return self.mode == "package"

    @property
    def switching(self) -> bool:
        """The run changes a recorded mount mode — a migration, not a realign."""
        return bool(self.previous) and self.previous != self.mode

    @property
    def mount(self) -> Path:
        """Where a mounted mode puts the standard tree."""
        return self.root / self.aitna / "akmon"

    @property
    def rules_path(self) -> str:
        """The project-root-relative path an ``extend`` of akmon's ruff rules names."""
        return (
            f"{self.aitna}/.akmon/profiles/ruff.toml" if self.package_mode else f"{self.aitna}/akmon/profiles/ruff.toml"
        )


def _mount_submodule(attach: _Attach, repo: str, ref: str | None, log: Callable[[str], None]) -> str | None:
    """``git submodule add`` + checkout of the pinned ref. Returns the recorded version.

    "Already mounted" is decided by **git** (``_is_submodule``), not by the tree being on disk:
    a vendored copy or a subtree carries the same files, and reading either as an existing
    submodule is how a mode switch used to finish green with no ``.gitmodules`` and no gitlink.
    """
    root, mount = attach.root, attach.mount
    relative = mount.relative_to(root).as_posix()
    if not _is_git_repo(root):
        raise _InitError(
            f"{root} is not a git repository — mode 'submodule' needs one. "
            "Run `git init` first, or attach with `--mode vendored`."
        )
    fresh = not _is_submodule(root, relative)
    if fresh:
        if mount.exists() and any(mount.iterdir()):
            what = (
                "an akmon tree mounted some other way (vendored or subtree)"
                if _is_akmon_tree(mount)
                else "not an akmon tree"
            )
            raise _InitError(
                f"{relative} exists but git does not record it as a submodule — it is {what}. `init` will not "
                f"delete a tree it did not create, and the removal is a commit of yours (D5). Remove it, then "
                f"re-run:\n{_old_mount_removal('vendored', relative)}"
            )
        log(f"git submodule add {repo} {relative}")
        completed = _run(["git", "submodule", "add", "--name", relative, repo, relative], cwd=root)
        if completed.returncode != 0:
            raise _InitError(f"git submodule add failed ({completed.returncode}); see the git output above")
        _run(["git", "submodule", "update", "--init", "--recursive", relative], cwd=root)
    else:
        log(f"{relative} is already mounted — realigning")

    # A re-run realigns; it does not bump. Moving an existing mount to whatever tag is newest
    # would be a pin bump nobody asked for (that is `akmon update`, A23), so the
    # checkout happens only on a fresh mount or when the caller named a ref explicitly.
    pin = ref if ref else (_latest_tag(mount) if fresh else None)
    if pin:
        completed = _run(["git", "checkout", "--quiet", pin], cwd=mount)
        if completed.returncode != 0:
            raise _InitError(f"cannot check out {pin!r} in {relative}")
        if fresh:
            # `git submodule add` just staged the gitlink at the commit it happened to clone (the
            # remote's default branch). After checking out the pin, that staged entry names a
            # *different* commit than the mount actually holds — a wrong pin sitting in the index,
            # one `git commit` away from landing, and `git status` showing the mount as `AM`.
            # Restaging corrects the entry git itself created on this very run; no path enters the
            # index that git did not put there, and the commit stays the owner's (D5).
            _run(["git", "add", "--", relative], cwd=root)
            log(f"pinned {relative} at {pin}")
        else:
            # Moving an existing pin is a **bump**: a change to the consumer's committed state
            # that a human reviews. `init` checks it out so the tree matches what it records, and
            # leaves the index alone — staging it here would hand the owner a pre-made commit.
            log(f"moved {relative} to {pin} — left unstaged")
            attach.next_steps.append(
                f"review the pin bump and stage it yourself — `git add -- {relative}` (D5: the pin bump and "
                "its commit are the owner's; read the CHANGELOG window between the two versions first)"
            )
    elif fresh:
        log(f"{relative} carries no release tag; left at the default branch")
    else:
        log(f"{relative} left at its current pin (pass --ref to move it)")
    return _describe(mount) or pin


def _mount_subtree(attach: _Attach, repo: str, ref: str | None, log: Callable[[str], None]) -> str | None:
    """Mode ``subtree``: attach onto a subtree the **owner** added, never one ``init`` adds.

    ``git subtree add`` is the one mount command that *commits* — it writes a squash commit
    plus a merge commit into the consumer's history. Commits are the owner's (D5,
    BOOTSTRAP §A10 "does NOT commit"), so `init` refuses to run it and prints the exact
    command instead; a re-run then finds the subtree in place and does everything else.
    ``--ref`` is required in this mode because a subtree leaves no git metadata of its own:
    once merged, nothing on disk can tell `init` which ref the owner took, and the
    integration record must not invent one.
    """
    root, mount = attach.root, attach.mount
    relative = mount.relative_to(root).as_posix()
    if not _is_git_repo(root):
        raise _InitError(f"{root} is not a git repository — mode 'subtree' needs one (or use `--mode vendored`).")
    if _is_submodule(root, relative):
        raise _InitError(
            f"git records {relative} as a submodule, not a subtree. Retire it first, then add the subtree:\n"
            f"{_old_mount_removal('submodule', relative)}"
        )
    if _is_akmon_tree(mount):
        if not ref:
            raise _InitError(
                f"mode 'subtree': pass `--ref <tag>` naming the ref merged into {relative}. A subtree keeps no "
                "git metadata of its own, so the recorded pin can only come from you."
            )
        log(f"{relative} is already mounted as a subtree — realigning at {ref} (bump it with `git subtree pull`)")
        return ref
    pin = ref
    if pin is None:
        listing = _git_output(["ls-remote", "--tags", "--refs", repo], cwd=root)
        tags = [line.split("refs/tags/")[-1] for line in (listing or "").splitlines() if "refs/tags/v" in line]
        pin = _newest_release(tags) or "main"
    raise _InitError(
        "mode 'subtree' needs one command `init` must not run for you — `git subtree add` creates commits, and "
        "commits are the owner's (D5). Run it, then re-run init:\n"
        f"    git subtree add --prefix {relative} {repo} {pin} --squash\n"
        f"    akmon init --mode subtree --ref {pin}"
    )


def _mount_vendored(attach: _Attach, ref: str | None, log: Callable[[str], None]) -> str:
    """Copy the embedded tree into the mount, replacing it member by member.

    The pin is the installed package's version by construction — the embedded tree *is* that
    version — so ``--ref`` is refused rather than silently ignored: honouring it would mean
    fetching a different tree over the network, which is the whole point mode ``vendored``
    exists to avoid.

    Each directory member is **replaced**, not merged: a plain ``copytree(dirs_exist_ok=True)``
    leaves behind every file a later akmon version deleted, so a realigned mount would keep
    accumulating dead hooks and tools forever. Only the members this function owns are
    touched; anything else under the mount (the ``.gitignore`` below) is left alone.
    """
    if ref:
        raise _InitError(
            "mode 'vendored' copies the embedded tree of the installed akmon package, so its pin is that "
            f"package's version ({__version__}) and `--ref {ref}` cannot change it. Pin a ref with "
            "`--mode submodule`/`--mode subtree`, or install the akmon version you want to vendor."
        )
    root, mount = attach.root, attach.mount
    source = _tree.embedded_tree_root()
    relative = mount.relative_to(root).as_posix()
    if _is_git_repo(root) and _is_submodule(root, relative):
        # Copying into a submodule's working tree writes files into *another repository* that
        # the consumer's index still points at by gitlink — the mount would be neither mode.
        raise _InitError(
            f"git records {relative} as a submodule; vendoring into it would leave the consumer with a gitlink "
            f"over hand-copied files. Retire the submodule first, then re-run:\n"
            f"{_old_mount_removal('submodule', relative)}"
        )
    if mount.exists() and any(mount.iterdir()) and not _is_akmon_tree(mount):
        raise _InitError(
            f"{relative} exists and is not an akmon tree — refusing to copy over it; remove it or pick another "
            "--aitna-root"
        )
    mount.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in tree_members():
        origin = source / name
        target = mount / name
        if not origin.exists():
            continue
        if origin.is_dir():
            if target.is_dir():
                shutil.rmtree(target)
            shutil.copytree(origin, target, ignore=_COPY_IGNORE)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
        copied += 1
    # The wheel ships no .gitignore (it is not part of the standard's content), but a mounted
    # tree whose bin/ and tools/ run in-tree needs one or every consumer commit sweeps in
    # __pycache__ — the same finding verify.py::check_akmon_gitignore reports.
    gitignore = mount / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text(_mount_gitignore(), encoding="utf-8")
    log(f"vendored {copied} standard-tree members into {relative} (pin: {__version__})")
    return __version__


def _package_pin_status(root: Path) -> str:
    """Where the consumer's manifest pins akmon: ``"dev"``, ``"runtime"``, ``"none"``, or ``"unreadable"``.

    When ``pyproject.toml`` is not valid TOML.

    Delegates to ``bin/sync.py::package_pin_status``, which is also what ``verify.py`` gates on:
    `init` reporting one definition of "pinned" while the contract check enforced another is the
    second-owner defect, and here the two would sit one command apart in the same session. `init`
    still never edits the manifest (it cannot know every dialect) — it reports, and mode
    ``package`` exits non-zero while the answer is not ``dev`` (ADR 0009 §4).
    """
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    return sync_mod.package_pin_status(root)


# --------------------------------------------------------------------------------------
# local layout + hand-owned documents
# --------------------------------------------------------------------------------------


def _tasks_skeleton(aitna: str) -> str:
    """The consumer's backlog skeleton — in the standard's own entry grammar.

    One task is **one line**, `- <id> · <title> · <status> · <goal> · [detail](link)`, with a
    **typed** id whose letter derives the owning role (`A` architect, `C` engineer, …) — see
    the standard's `pipelines/tasks.md`. The two seed entries are the judgement steps `init`
    could not take, written in exactly that grammar: this file is the first backlog every
    consumer copies from, so a malformed seed would teach the wrong format to every project.
    Legacy `T#` ids are grandfathered history and must not be minted here.
    """
    return _jsondata().fill(_data()["tasks_skeleton"], {"aitna": aitna})


def _memory_index() -> str:
    """The dev layer's memory index seed (``init.json``)."""
    return _data()["memory_index"]


def _charters() -> dict[str, str]:
    """The default agent charters by role, in write order (``init.json``)."""
    return _data()["charters"]


def _charter(role: str, focus: str, aitna: str, *, package_mode: bool) -> str:
    """One agent charter (``init.json``), with the locate line picked by mount mode."""
    jsondata = _jsondata()
    data = _data()
    locate_key = "charter_locate_package" if package_mode else "charter_locate_mounted"
    locate = jsondata.fill(data[locate_key], {"aitna": aitna, "role": role})
    return jsondata.fill(data["charter"], {"role": role, "focus": focus, "locate": locate})


def _gitignore_lines(aitna: str) -> list[str]:
    """The ``.gitignore`` entries a consumer gains (``init.json``), in append order."""
    jsondata = _jsondata()
    return [jsondata.fill(line, {"aitna": aitna}) for line in _data()["gitignore_lines"]]


def _merge_gitignore(existing: str, wanted: list[str]) -> str:
    """``existing`` plus every wanted line it does not already carry, appended verbatim.

    Never reorders or rewrites what is there: a ``.gitignore`` is project text.
    """
    present = {line.strip() for line in existing.splitlines() if line.strip()}
    missing = [line for line in wanted if not line.strip() or line.strip() not in present]
    # Drop leading/trailing blanks and collapse a run of them left by already-present lines.
    trimmed: list[str] = []
    for line in missing:
        if not line.strip() and (not trimmed or not trimmed[-1].strip()):
            continue
        trimmed.append(line)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    if not [line for line in trimmed if line.strip()]:
        return existing
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    separator = "\n" if prefix and not prefix.endswith("\n\n") else ""
    return prefix + separator + "\n".join(trimmed) + "\n"


def _ci_workflow(aitna: str, *, package_mode: bool) -> str:
    """The contract-check workflow (``init.json``), its steps picked by mount mode."""
    jsondata = _jsondata()
    data = _data()
    steps_key = "ci_workflow_steps_package" if package_mode else "ci_workflow_steps_mounted"
    steps = jsondata.fill(data[steps_key], {"aitna": aitna})
    return jsondata.fill(data["ci_workflow"], {"steps": steps})


# --------------------------------------------------------------------------------------
# the AGENTS.md akmon block (hand-owned source text, written only when absent)
# --------------------------------------------------------------------------------------


def block_heading() -> str:
    """The block heading of a project's ``AGENTS.md`` akmon section.

    The standard tree's ``common/always_loaded.json`` is the single owner of that text (C102):
    resolved through the embedded tree so both carriers — the installed wheel's ``_tree`` and
    a source checkout — read the same data file.
    """
    tree_root = _tree.embedded_tree_root()
    return _jsondata().read(tree_root / "common" / "always_loaded.json")["block_heading"]


def _doc_link(name: str, aitna: str, ref: str, *, package_mode: bool) -> str:
    """A link to a standard document: relative to the mount when one exists.

    A GitHub link at the pinned ref in package mode (there is no tree in the repo to point at —
    ADR 0009 §4).
    """
    if package_mode:
        return f"{akmon_repo()}/blob/{ref}/{name}"
    return f"{aitna}/akmon/{name}"


def _agents_block(aitna: str, ref: str, archetype: str, language: str, *, package_mode: bool) -> str:
    """The AGENTS.md akmon block (``init.json``); links and fragments computed here.

    The mode-conditional fragments (``roles_hint``, ``shared_layer``) and every link value are
    computed in code; the stored template carries only their placeholders.
    """
    jsondata = _jsondata()
    data = _data()

    def link(name: str) -> str:
        return _doc_link(name, aitna, ref, package_mode=package_mode)

    guardrails_dir = f"{aitna}/.akmon/guardrails" if package_mode else f"{aitna}/akmon/guardrails"
    profiles_dir = f"{aitna}/.akmon/profiles" if package_mode else f"{aitna}/akmon/profiles"
    fragment = "package" if package_mode else "mounted"
    roles_hint = jsondata.fill(
        data[f"agents_roles_hint_{fragment}"], {"roles_link": link("roles/README.md"), "aitna": aitna}
    )
    shared_layer = jsondata.fill(data[f"agents_shared_layer_{fragment}"], {"aitna": aitna})
    return jsondata.fill(
        data["agents_block"],
        {
            "heading": block_heading(),
            "model": link("MODEL.md"),
            "bootstrap": link("BOOTSTRAP.md"),
            "readme": link("README.md"),
            "archetypes": link("ARCHETYPES.md"),
            "archetype": archetype,
            "language": language,
            "aitna": aitna,
            "shared_layer": shared_layer,
            "roles_hint": roles_hint,
            "guardrails_dir": guardrails_dir,
            "profiles_dir": profiles_dir,
            "pre_commit": link("pipelines/pre-commit.md"),
            "review_flow": link("pipelines/review-flow.md"),
            "design_flow": link("pipelines/design-flow.md"),
            "code_flow": link("pipelines/code-flow.md"),
            "tasks_link": link("pipelines/tasks.md"),
            "memory_distill": link("pipelines/memory-distill.md"),
            "learning": link("pipelines/learning.md"),
        },
    )


def _agents_header() -> str:
    """The ``# AGENTS.md`` header a fresh AGENTS.md gains the block under (``init.json``)."""
    return _data()["agents_header"]


# --------------------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------------------


class _InitError(Exception):
    """A precondition the caller has to fix; reported as one line, no traceback."""


def _confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        return True  # non-interactive by design: agents and CI are first-class callers
    answer = input(f"{question} [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


def _write_if_absent(path: Path, text: str, log: Callable[[str], None], label: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    log(f"wrote {label}")
    return True


def _write_akmon_toml(root: Path, aitna: str, *, mode: str, version: str | None, archetype: str) -> Path:
    """Create or prepare ``<AITNA_ROOT>/.akmon.toml`` for an attach/realign.

    A fresh record is written whole. An existing one is *upserted key by key*
    (``sync.py::_upsert_toml_key``) rather than regenerated, so a hand-written
    ``[test].runner``, comments, and every field this command does not own survive the
    realign — and an ``attached_archetype`` a human already resolved is never overwritten
    with the placeholder. This step records the attempted pin and mount but deliberately
    leaves ``last_realign`` unchanged; :func:`_mark_realign_complete` advances that completion
    marker only after sync, routing initialization, and the package-pin gate all succeed.
    """
    path = root / aitna / ".akmon.toml"
    if not path.is_file():
        jsondata = _jsondata()
        data = _data()
        recorded = jsondata.fill(data["record_version_line"], {"version": version}) if version else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            jsondata.fill(data["record_fresh"], {"mode": mode, "recorded": recorded, "archetype": archetype}),
            encoding="utf-8",
        )
        return path
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    text = path.read_text(encoding="utf-8")
    fields = sync_mod.read_akmon_toml(path)
    text = sync_mod._upsert_toml_key(text, "mount", mode)
    if version:
        text = sync_mod._upsert_toml_key(text, "akmon_version", version)
    if not fields.get("attached_archetype"):
        text = sync_mod._upsert_toml_key(text, "attached_archetype", archetype)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- what `akmon check` runs (ADR 0014 §4) ---------------------------------------------
# The linters and type checkers a project can already be configured for, how each announces its
# configuration, and the command `akmon check` runs for it. `{files}` becomes the files a run
# covers. Detection only reads the project's files.
_TOOLS = (
    # name, config files, pyproject [tool.<key>], setup.cfg/tox.ini section, command
    ("ruff", ("ruff.toml", ".ruff.toml"), "ruff", None, "ruff check {files}"),
    ("flake8", (".flake8",), None, "flake8", "flake8 {files}"),
    ("pylint", (".pylintrc", "pylintrc"), "pylint", None, "pylint {files}"),
    ("mypy", ("mypy.ini", ".mypy.ini"), "mypy", "mypy", "mypy {files}"),
)
CHECK_CHOICES = ("own", "akmon", "none")


def _cfg_sections(root: Path) -> set[str]:
    sections: set[str] = set()
    for name in ("setup.cfg", "tox.ini"):
        path = root / name
        try:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
        except (OSError, UnicodeDecodeError):
            continue
        sections.update(re.findall(r"^\[([\w.:-]+)\]", text, re.MULTILINE))
    return sections


def _detect_tools(root: Path, sync_mod: ModuleType) -> list[tuple[str, str]]:
    """``(name, command)`` for every linter or type checker the project is configured for."""
    manifest = sync_mod._read_manifest(root) or {}
    tool_tables = manifest.get("tool") if isinstance(manifest.get("tool"), dict) else {}
    sections = _cfg_sections(root)
    return [
        (name, command)
        for name, files, table, section, command in _TOOLS
        if any((root / file).is_file() for file in files)
        or (table is not None and table in tool_tables)
        or (section is not None and section in sections)
    ]


def _run_prefix(root: Path) -> str:
    """How the project runs its tools: through its environment manager when it has one (``init.json``)."""
    for lockfile, prefix in _data()["run_prefix"].items():
        if (root / lockfile).is_file():
            return prefix
    return ""


def _extend_with_akmon_rules(
    root: Path, rules_path: str, sync_mod: ModuleType, log: Callable[[str], None]
) -> str | None:
    """Point the project's ruff configuration at akmon's rules — the standard ``extend``.

    And return a next step when that cannot be done without overriding the owner's own choice.
    """
    extends = sync_mod.ruff_extends(root)
    if any(value == rules_path for _, value in extends):
        return None
    if extends:
        config, value = extends[0]
        return (
            f"{config} already extends `{value}` and ruff takes one `extend`: to run akmon's Python rules, "
            f"point it at `{rules_path}`"
        )
    line = f'extend = "{rules_path}"'
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        header = re.search(r"^\[tool\.ruff\][ \t]*$", text, re.MULTILINE)
        if header:
            text = f"{text[: header.end()]}\n{line}{text[header.end() :]}"
        else:
            text = f"{text.rstrip()}\n\n[tool.ruff]\n{line}\n"
        pyproject.write_text(text, encoding="utf-8")
        log(f"pyproject.toml: [tool.ruff] extends akmon's Python rules ({rules_path})")
        return None
    for name in ("ruff.toml", ".ruff.toml"):
        path = root / name
        if path.is_file():
            path.write_text(f"{line}\n{path.read_text(encoding='utf-8')}", encoding="utf-8")
            log(f"{name}: extends akmon's Python rules ({rules_path})")
            return None
    (root / "ruff.toml").write_text(
        "# ruff with akmon's Python rules; adjust them here with extend-select, extend-ignore and\n"
        f"# per-file-ignores.\n{line}\n",
        encoding="utf-8",
    )
    log(f"wrote ruff.toml extending akmon's Python rules ({rules_path})")
    return None


def _ruff_step(root: Path) -> str | None:
    """The next step that makes ruff runnable, when the project does not declare it yet (``init.json``)."""
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else ""
    if re.search(r"[\"']ruff\b", text):
        return None
    ruff_step = _data()["ruff_step"]
    if (root / "uv.lock").is_file():
        return ruff_step["uv"]
    if (root / "poetry.lock").is_file():
        return ruff_step["poetry"]
    return ruff_step["none"]


def _setup_checks(attach: _Attach, record: Path, choice: str | None, *, ask: bool, log: Callable[[str], None]) -> None:
    """Decide once what ``akmon check`` runs and record it as ``[check]``.

    The project's own linters when it has any; ruff with akmon's Python rules when it has none;
    or nothing — the owner's answer at the prompt, ``--checks``, or those defaults when nobody
    is asked. A record that already has a ``[check]`` table is left alone: a realign never
    changes that choice.
    """
    root, next_steps = attach.root, attach.next_steps
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    if re.search(r"^\[check\]", record.read_text(encoding="utf-8"), re.MULTILINE):
        log("[check] already names this project's checks — left untouched")
        return
    tools = _detect_tools(root, sync_mod)
    names = ", ".join(name for name, _ in tools)
    if choice is None and tools:
        choice = "own"
        if ask and not _confirm(f"akmon init: `akmon check` runs the project's own {names}?"):
            choice = "akmon" if _confirm("akmon init: set up ruff with akmon's Python rules instead?") else "none"
    elif choice is None:
        choice = "akmon"
        if ask and not _confirm("akmon init: no linter configured — set up ruff with akmon's Python rules?"):
            choice = "none"
    prefix = _run_prefix(root)
    if choice == "none":
        log("akmon check: no checks recorded")
        next_steps.append(f"name the project's checks under `[check]` in {record.name} when it has any")
        return
    if choice == "own" and not tools:
        next_steps.append(
            f"no linter configuration was found: name the project's checks under `[check]` in {record.name}"
        )
        return
    if choice == "own":
        commands = {name: prefix + command for name, command in tools}
    else:
        step = _extend_with_akmon_rules(root, attach.rules_path, sync_mod, log)
        commands = {"ruff": f"{prefix}ruff check {{files}}"}
        next_steps.extend(item for item in (step, _ruff_step(root)) if item)
    lines = [
        "",
        "[check]",
        "# What `akmon check` runs: the project's own commands, `{files}` becoming the files a run covers.",
        *(f'{name} = "{command}"' for name, command in commands.items()),
    ]
    text = record.read_text(encoding="utf-8")
    record.write_text(f"{text.rstrip()}\n" + "\n".join(lines) + "\n", encoding="utf-8")
    log(f"akmon check will run: {', '.join(commands)} (recorded as [check])")


def _mark_realign_complete(path: Path, version: str | None) -> None:
    """Advance the completion marker after every generated stage has succeeded.

    The other record fields describe the attach being attempted and are useful even when a
    fresh attach stops part-way through.  ``last_realign`` is different: it asserts that both
    sync and model-routing init completed for that version, so an existing value must survive
    either failure and a fresh failed attach must not gain one.
    """
    if not version:
        return
    sync_mod = cli._load_embedded_sync(_tree.embedded_tree_root())
    text = path.read_text(encoding="utf-8")
    path.write_text(sync_mod._upsert_toml_key(text, "last_realign", version), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akmon init",
        description="Attach the akmon standard to a project (the mechanical half of BOOTSTRAP §A).",
    )
    parser.add_argument("--mode", choices=MODES, help="Mount mode. Default: submodule when possible, else vendored.")
    parser.add_argument("--aitna-root", help="Dev-layer root, project-root-relative (default: _aitna).")
    parser.add_argument("--project-root", type=Path, help="Project to attach to. Defaults to the current directory.")
    repo = akmon_repo()
    parser.add_argument("--repo", default=repo, help=f"akmon repository URL (default: {repo}).")
    parser.add_argument("--ref", help="Ref to pin (default: the latest release tag).")
    parser.add_argument("--archetype", help="Archetype id per ARCHETYPES.md (default: left unclassified).")
    parser.add_argument("--language", help="Primary language per ARCHETYPES.md (default: left unclassified).")
    parser.add_argument("--no-ci", action="store_true", help="Do not write a CI workflow running sync/verify.")
    parser.add_argument(
        "--checks",
        choices=CHECK_CHOICES,
        help="What `akmon check` runs: the project's own linters (default when it has any), ruff with "
        "akmon's Python rules (default when it has none), or nothing.",
    )
    parser.add_argument(
        "--switch-mode",
        action="store_true",
        help="Allow changing the recorded mount mode (a migration: it needs manual AGENTS.md edits).",
    )
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = (args.project_root or Path.cwd()).resolve()
    if not root.is_dir():
        print(f"akmon init: {root} is not a directory", file=sys.stderr)
        return 2

    try:
        attach, reason = _plan(args, root)
        _log(f"attaching to {root}")
        _log(f"mount mode: {attach.mode} ({reason}) · dev layer: {attach.aitna}/")
        if attach.switching:
            _log(f"migrating the mount mode: {attach.previous} → {attach.mode}")
        if not args.yes and not _confirm(f"akmon init: attach akmon to {root}?"):
            print("akmon init: aborted", file=sys.stderr)
            return 1
        version, pin_status = _mount(attach, repo=args.repo, ref=args.ref)
        ref = _pin_ref(attach, version, ref=args.ref, repo=args.repo)
    except _InitError as exc:
        print(f"akmon init: {exc}", file=sys.stderr)
        return 2

    archetype = "/".join(part for part in (args.archetype, args.language) if part) or "unclassified"
    # --- local layout (LOCAL layer) --------------------------------------------------
    _write_local_layout(attach)

    # --- hand-owned documents: written when absent, never rewritten ------------------
    block = _agents_block(
        attach.aitna,
        ref,
        args.archetype or "<archetype>",
        args.language or "<language>",
        package_mode=attach.package_mode,
    )
    _write_agents_block(attach, block)
    if attach.switching:
        attach.next_steps.extend(_mode_switch_steps(attach.previous, attach.mode, attach.aitna))
    _write_gitignore(attach)
    _write_ci(attach, no_ci=args.no_ci)

    record = _write_akmon_toml(root, attach.aitna, mode=attach.mode, version=version, archetype=archetype)
    _log(f"recorded {record.relative_to(root)} (mount={attach.mode}, akmon_version={version or 'unknown'})")
    _setup_checks(attach, record, args.checks, ask=not args.yes, log=_log)

    # --- generated surface: sync, then model routing ---------------------------------
    code = _generate(root)
    if code != 0:
        return code

    # --- the judgment steps init deliberately did not do -----------------------------
    _add_closing_steps(attach, archetype=archetype, pin_status=pin_status, ref=ref)
    return _report(attach, pin_status, record, version)


def _log(message: str) -> None:
    # flush: the sync and model-routing steps run as subprocesses writing straight to the
    # terminal, so a block-buffered parent would narrate the run in the wrong order.
    print(f"akmon init: {message}", flush=True)


def _plan(args: argparse.Namespace, root: Path) -> tuple[_Attach, str]:
    """The run's dev layer and mount mode, and why that mode; refuses a migration not asked for."""
    # Every path in the tooling derives from this env var (sync/verify/hooks read it at call
    # time), so resolving it once here — from the flag or from the environment, validated
    # either way — makes the whole run, including the sync and routing subprocesses that
    # inherit the environment, agree on one dev-layer root that is inside the project.
    aitna = _effective_aitna_root(args.aitna_root, root)
    os.environ["AITNA_ROOT"] = aitna

    previous = _recorded_mount(root, aitna)
    if args.mode:
        mode, reason = args.mode, "requested"
    elif previous in MODES:
        mode, reason = previous, "recorded"
    else:
        mode, reason = _default_mode(root, args.repo)
    attach = _Attach(root, aitna, mode, previous)
    _refuse_unready_switch(attach, switch_mode=args.switch_mode)
    return attach, reason


def _refuse_unready_switch(attach: _Attach, *, switch_mode: bool) -> None:
    """Refuse a mount-mode change without ``--switch-mode``, or with the old mount still on disk."""
    if not attach.switching:
        return
    previous, mode, mount = attach.previous, attach.mode, attach.mount
    if switch_mode and not attach.package_mode and mount.exists() and any(mount.iterdir()):
        # Between two *mounted* modes the mount itself has to change shape — a submodule's
        # gitlink and `.git`, a subtree's tracked files, a vendored copy's plain files are
        # mutually exclusive states of one path. Retiring the old one deletes tracked files
        # and rewrites git bookkeeping, which is the owner's commit (D5), so `init` refuses
        # rather than half-migrating: the previous shape used to survive underneath the new
        # record, leaving a project that claimed one mode and carried another.
        relative = mount.relative_to(attach.root).as_posix()
        raise _InitError(
            f"switching mount mode {previous!r} → {mode!r} needs the old mount gone first — `init` does not "
            f"delete a tree it did not create, and the removal is your commit (D5). Retire {relative}, then "
            f"re-run:\n{_old_mount_removal(previous, relative)}\n"
            f"    akmon init --mode {mode} --switch-mode"
        )
    if not switch_mode:
        raise _InitError(
            f"this project is attached in mount mode {previous!r}; {mode!r} is a **migration**, not a realign — "
            "the AGENTS.md akmon block still points at the old layout and the old mount is still on disk, so "
            "finishing silently would leave `akmon verify --strict` red. Re-run with `--switch-mode` and init "
            "will attach in the new mode and print the edits it must not make for you."
        )


def _mount(attach: _Attach, *, repo: str, ref: str | None) -> tuple[str | None, str]:
    """Mount the standard in ``attach.mode``: the version to record, and the manifest pin's status.

    Only mode ``package`` pins akmon in the consumer's own manifest; a mounted tree reports ``dev``.
    """
    if attach.mode == "submodule":
        return _mount_submodule(attach, repo, ref, _log), "dev"
    if attach.mode == "subtree":
        return _mount_subtree(attach, repo, ref, _log), "dev"
    if attach.mode == "vendored":
        return _mount_vendored(attach, ref, _log), "dev"
    return __version__, _package_pin_status(attach.root)


def _pin_ref(attach: _Attach, version: str | None, *, ref: str | None, repo: str) -> str:
    """The release the package-mode links and the pin instruction name.

    Package-mode links and pin instructions name a remote release. Mounted modes derive their
    recorded ref from the mounted tree instead. Only a *first* package attach asks the remote for
    its latest release tag: on a realign the ref feeds nothing but the AGENTS.md block `init`
    preserves and the pin instruction, and the installed version already names it — while a
    network round-trip there would make the first step of every bump fail offline, with exit 2,
    for a value the run does not use.
    """
    first_attach = not (attach.root / attach.aitna / ".akmon.toml").is_file()
    return ref or (
        _package_default_ref(repo, attach.root)
        if attach.package_mode and first_attach
        else _tag_for_version(version or __version__)
    )


def _write_local_layout(attach: _Attach) -> None:
    """The dev layer's directories, task list, memory index and agent charters, each when absent."""
    root, aitna = attach.root, attach.aitna
    for name in ("agents", "skills", "tools", "memory"):
        (root / aitna / name).mkdir(parents=True, exist_ok=True)
    _write_if_absent(root / aitna / "TASKS.md", _tasks_skeleton(aitna), _log, f"{aitna}/TASKS.md")
    _write_if_absent(root / aitna / "memory" / "README.md", _memory_index(), _log, f"{aitna}/memory/README.md")
    for role, focus in _charters().items():
        _write_if_absent(
            root / aitna / "agents" / role / "README.md",
            _charter(role, focus, aitna, package_mode=attach.package_mode),
            _log,
            f"{aitna}/agents/{role}/README.md",
        )


def _write_agents_block(attach: _Attach, block: str) -> None:
    """Write AGENTS.md with the akmon block, or append the block; one already there stays untouched."""
    agents_md = attach.root / "AGENTS.md"
    if not agents_md.is_file():
        agents_md.write_text(_agents_header() + block, encoding="utf-8")
        _log("wrote AGENTS.md with the akmon block")
    elif block_heading() in agents_md.read_text(encoding="utf-8"):
        _log("AGENTS.md already carries an akmon block — left untouched")
        if not attach.switching:
            attach.next_steps.append("`akmon verify --strict` checks the existing AGENTS.md block against the contract")
    else:
        text = agents_md.read_text(encoding="utf-8")
        separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        agents_md.write_text(text + separator + block, encoding="utf-8")
        _log("appended the akmon block to AGENTS.md (existing content preserved)")


def _write_gitignore(attach: _Attach) -> None:
    """Add the akmon entries the project's ``.gitignore`` lacks."""
    gitignore = attach.root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    merged = _merge_gitignore(existing, _gitignore_lines(attach.aitna))
    if merged != existing:
        gitignore.write_text(merged, encoding="utf-8")
        _log(".gitignore: added the akmon entries (secrets, dev-layer venv, routing artifacts)")


def _write_ci(attach: _Attach, *, no_ci: bool) -> None:
    """Write the contract-check workflow, or name the step when the project's CI is its own."""
    aitna = attach.aitna
    workflows = attach.root / ".github" / "workflows"
    existing_workflows = sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml"))
    data = _data()
    variant = "package" if attach.package_mode else "mounted"
    check_cmds = tuple(
        _jsondata().fill(command, {"aitna": aitna}) for command in data["write_ci_commands"][variant]
    )
    if no_ci:
        attach.next_steps.append(f"add the contract checks to CI: `{check_cmds[0]}` and `{check_cmds[1]}`")
    elif existing_workflows:
        verb = "update the akmon commands in" if attach.switching else "add the contract checks to"
        attach.next_steps.append(f"{verb} your existing workflow(s): `{check_cmds[0]}` and `{check_cmds[1]}`")
    else:
        _write_if_absent(
            workflows / "akmon.yml",
            _ci_workflow(aitna, package_mode=attach.package_mode),
            _log,
            ".github/workflows/akmon.yml",
        )


def _generate(root: Path) -> int:
    """Run sync, then the model-routing initializer; the first failing exit code, else 0."""
    _log("running sync (generated pointers, hook wiring, imported guardrails)")
    code = cli._dispatch("sync", ["--project-root", str(root)], cwd=root)
    if code != 0:
        print(f"akmon init: sync failed ({code}); the attach is incomplete", file=sys.stderr)
        return code

    standard_root = cli._mounted_akmon_root(root) or _tree.embedded_tree_root()
    routing_init = standard_root / "tools" / "model_routing" / "init.py"
    _log("running model-routing init (subagent definitions + local routing config)")
    completed = _run([sys.executable, str(routing_init), "--project-root", str(root)], cwd=root)
    if completed.returncode != 0:
        print(f"akmon init: model-routing init failed ({completed.returncode})", file=sys.stderr)
        return completed.returncode
    return 0


def _add_closing_steps(attach: _Attach, *, archetype: str, pin_status: str, ref: str) -> None:
    """The judgment steps ``init`` deliberately did not take, a missing pin first (``init.json``)."""
    aitna = attach.aitna
    jsondata = _jsondata()
    steps = _data()["closing_steps"]
    if archetype == "unclassified":
        attach.next_steps.insert(0, jsondata.fill(steps["classify"], {"aitna": aitna}))
    attach.next_steps.append(jsondata.fill(steps["pin_test"], {"aitna": aitna}))
    pin_step = _pin_step(pin_status, ref) if attach.package_mode else None
    if pin_step:
        attach.next_steps.insert(0, pin_step)
    if aitna != cli._project_root_lib().AITNA_ROOT_DEFAULT:
        attach.next_steps.append(jsondata.fill(steps["export_aitna"], {"aitna": aitna}))
    attach.next_steps.append(steps["verify"])


def _pin_step(pin_status: str, ref: str) -> str | None:
    """The step a package attach needs for its manifest pin status (``init.json``).

    ``None`` when the status (``dev``) names no step.
    """
    template = _data()["pin_step"].get(pin_status)
    if template is None:
        return None
    return _jsondata().fill(template, {"repo": akmon_repo(), "ref": ref})


def _report(attach: _Attach, pin_status: str, record: Path, version: str | None) -> int:
    """Print the steps left; exit 1 while a package attach has no pin it can run from."""
    # Mode `package` mounts no tree, so the manifest pin *is* the mount: an attach that ends
    # without one has produced a project that looks attached and cannot run a single akmon
    # command. `init` cannot write the pin (it cannot know every manifest dialect), so it says so
    # in the exit code rather than reporting success over an unusable project — the CI job this
    # very run wrote would be the next thing to discover it.
    incomplete = attach.package_mode and pin_status != "dev"
    jsondata = _jsondata()
    report = _data()["report"]
    print()
    _log(report["incomplete"] if incomplete else report["complete"])
    for index, step in enumerate(attach.next_steps, start=1):
        print(jsondata.fill(report["step"], {"index": index, "step": step}), flush=True)
    if incomplete:
        key = "unreadable" if pin_status == "unreadable" else "absent"
        print()
        _log(jsondata.fill(report["exit"], {"missing": report["missing"][key], "remedy": report["remedy"][key]}))
        return 1
    _mark_realign_complete(record, version)
    return 0
