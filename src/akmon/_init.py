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
import shutil
import subprocess
import sys
from pathlib import Path

from akmon import __version__, _tree

AKMON_REPO = "https://github.com/akumidv/ai_akmon"
MODES = ("submodule", "vendored", "subtree", "package")

# The top-level members that *are* the standard tree, mirroring
# ``[tool.hatch.build.targets.wheel.force-include]`` in ``pyproject.toml``: mode ``vendored``
# copies exactly what mode ``package`` would ship, so a vendored mount is not a poorer
# flavor of the standard (ADR 0009 §1, "yes for parity"). The embedded tree resolves to the
# akmon repo root in a source checkout, which carries development-only members
# (``src/``, ``.git/``, ``tests/``, ``AGENTS.md``, …) that the wheel does not ship — an
# allowlist keeps both carriers producing the same mount. ``meta/tests/test_init.py``
# asserts this tuple and the pyproject force-include list stay equal.
TREE_MEMBERS = (
    "ARCHETYPES.md",
    "BOOTSTRAP.md",
    "CAPABILITIES.md",
    "CHANGELOG.md",
    "LICENSE",
    "MODEL.md",
    "README.md",
    "common",
    "bin",
    "examples",
    "guardrails",
    "hooks",
    "meta",
    "pipelines",
    "profiles",
    "roles",
    "skills",
    "tools",
)

_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.py[cod]", ".pytest_cache", ".ruff_cache", ".git", ".DS_Store"
)

_MOUNT_GITIGNORE = "__pycache__/\n*.py[cod]\n"

# The markers a directory must carry before `init` will treat it as *this* standard's tree.
# `bin/sync.py` alone is not an identity: a vendored realign deletes and re-copies whole
# top-level members, so mistaking someone's directory for akmon destroys their work. Four
# markers spread across three top-level members is a threshold no unrelated tree crosses by
# accident, while every akmon version that has ever shipped a mount clears it.
_TREE_MARKERS = ("bin/sync.py", "bin/verify.py", "roles/README.md", "guardrails/_common.md")


def _is_akmon_tree(path: Path) -> bool:
    return all((path / marker).is_file() for marker in _TREE_MARKERS)


# --------------------------------------------------------------------------------------
# small process / git helpers
# --------------------------------------------------------------------------------------


def _run(cmd: list[str], *, cwd: Path | None = None, capture: bool = False, timeout: int | None = None):
    """Run ``cmd``; never inherit a credential prompt (an attach must not hang on one)."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=capture,
        text=True,
        timeout=timeout,
        env=env,
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
    key = []
    for part in parts:
        key.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return tuple(key)


def _latest_tag(repo_dir: Path) -> str | None:
    """Highest local ``v*`` tag, or ``None`` when ``repo_dir`` carries none."""
    listing = _git_output(["tag", "--list", "v*"], cwd=repo_dir)
    if not listing:
        return None
    tags = [line.strip() for line in listing.splitlines() if line.strip()]
    return max(tags, key=_version_key) if tags else None


def _package_default_ref(repo: str, root: Path) -> str:
    """Newest release tag advertised by ``repo``, never one synthesized from a version."""
    try:
        completed = _run(
            ["git", "ls-remote", "--tags", "--refs", repo, "refs/tags/v*"],
            cwd=root,
            capture=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _InitError(
            f"cannot discover the latest release tag from {repo!r}; pass --ref explicitly"
        ) from exc
    if completed.returncode != 0:
        raise _InitError(f"cannot discover the latest release tag from {repo!r}; pass --ref explicitly")
    tags = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].startswith("refs/tags/v"):
            tags.append(fields[1].removeprefix("refs/tags/"))
    if not tags:
        raise _InitError(f"repository {repo!r} advertises no release tags; pass --ref explicitly")
    return max(tags, key=_version_key)


def _describe(repo_dir: Path) -> str | None:
    """``git describe --tags`` — the recorded pin spelling for a mounted mode (BOOTSTRAP §C)."""
    return _git_output(["describe", "--tags"], cwd=repo_dir)


# --------------------------------------------------------------------------------------
# paths / mode resolution
# --------------------------------------------------------------------------------------


def _effective_aitna_root(flag: str | None, root: Path) -> str:
    """The dev-layer root this run will use — from ``--aitna-root`` or from ``AITNA_ROOT`` —
    validated whichever way it arrived.

    The two sources are one contract, so validating only the flag validated nothing: the flag's
    entire effect is to *set* the environment variable, and a caller who exports the variable
    instead reaches every code path the flag reaches. ``AITNA_ROOT=../escaped akmon init`` wrote
    the record, the backlog, the charters and the mount into a sibling directory and exited 0.
    """
    source = "--aitna-root" if flag is not None else "AITNA_ROOT"
    raw = flag if flag is not None else os.environ.get("AITNA_ROOT")
    if raw is None or not raw.strip():
        from akmon import cli

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
    from akmon import cli

    record = cli._embedded_common_module(_tree.embedded_tree_root(), "record")
    value = record.read_akmon_toml(root / aitna / ".akmon.toml").get("mount")
    return value if isinstance(value, str) and value else None


def _old_mount_removal(previous: str, relative: str) -> str:
    """The commands that retire a ``previous``-mode mount — printed, never run.

    Every one of them deletes tracked files (and the submodule form rewrites git's own
    bookkeeping), so they are the owner's to run and to commit (D5).
    """
    if previous == "submodule":
        return (
            f"    git submodule deinit -f -- {relative}\n"
            f"    git rm -f -- {relative}\n"
            f"    rm -rf .git/modules/{relative}"
        )
    if previous == "subtree":
        return (
            f"    git rm -r -- {relative}   # a subtree's files are ordinary tracked files\n"
            f"    rm -rf {relative}"
        )
    return (
        f"    git rm -r --cached -- {relative}   # if the vendored copy was committed\n"
        f"    rm -rf {relative}"
    )


def _mode_switch_steps(previous: str, mode: str, aitna: str) -> list[str]:
    """What a human must do after a mount-mode migration — the parts `init` will not do.

    Switching modes moves every path the standard is reached by, and those paths live in the
    one file `init` must not rewrite: the hand-owned `AGENTS.md` akmon block. Listing the exact
    edits is the honest half of the deal; the other half is refusing to perform the switch
    silently (see `main`).
    """
    guardrails = f"{aitna}/.akmon/guardrails" if mode == "package" else f"{aitna}/akmon/guardrails"
    steps = [
        f"re-point the AGENTS.md akmon block from the {previous} layout to {mode}: the guardrail imports become "
        f"`@{guardrails}/_common.md` (plus each language guardrail), and every link to the standard's docs "
        + (
            "becomes a GitHub link at the pinned tag, with `akmon path` named as the way to read them locally"
            if mode == "package"
            else f"becomes a path under `{aitna}/akmon/`"
        )
    ]
    if mode == "package":
        steps.append(
            f"remove the now-unused mount `{aitna}/akmon` (`git rm -r --cached` + `rm -rf`, or `git submodule "
            "deinit` first if it was a submodule) — nothing reads it in package mode"
        )
    return steps


def _default_mode(root: Path, repo: str) -> tuple[str, str]:
    """The mode to use when the caller named none, plus the reason — printed, never silent
    (ADR 0009 §3): ``submodule`` for a git repository that can reach the akmon repo, else
    ``vendored``, which needs neither git nor a network."""
    if not _is_git_repo(root):
        return "vendored", "the project is not a git repository"
    if not _remote_reachable(repo, root):
        return "vendored", f"{repo} is not reachable from here"
    return "submodule", "a git repository that can reach the akmon repository"


def _tag_for_version(version: str) -> str:
    """The GitHub ref a consumer's human-facing links should point at: the release tag for a
    released version, ``main`` for a development one (no tag exists for it yet).

    "Released" is asked of ``common/versions.py``, the sole owner of that rule (C54), rather than
    answered again here: the substring heuristic this replaced missed ``.postN`` entirely and
    would have pointed a consumer at a tag that does not exist.
    """
    from akmon import cli

    versions = cli._embedded_common_module(_tree.embedded_tree_root(), "versions")
    if not versions.is_final(version):
        return "main"
    return f"v{versions.split_version(version)[0]}"


# --------------------------------------------------------------------------------------
# mount modes
# --------------------------------------------------------------------------------------


def _mount_submodule(root: Path, mount: Path, repo: str, ref: str | None, log, next_steps: list[str]) -> str | None:
    """``git submodule add`` + checkout of the pinned ref. Returns the recorded version.

    "Already mounted" is decided by **git** (``_is_submodule``), not by the tree being on disk:
    a vendored copy or a subtree carries the same files, and reading either as an existing
    submodule is how a mode switch used to finish green with no ``.gitmodules`` and no gitlink.
    """
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
    # would be a pin bump nobody asked for (that is `akmon bump`, still deferred), so the
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
            next_steps.append(
                f"review the pin bump and stage it yourself — `git add -- {relative}` (D5: the pin bump and "
                "its commit are the owner's; read the CHANGELOG window between the two versions first)"
            )
    elif fresh:
        log(f"{relative} carries no release tag; left at the default branch")
    else:
        log(f"{relative} left at its current pin (pass --ref to move it)")
    return _describe(mount) or pin


def _mount_subtree(root: Path, mount: Path, repo: str, ref: str | None, log) -> str | None:
    """Mode ``subtree``: attach onto a subtree the **owner** added, never one ``init`` adds.

    ``git subtree add`` is the one mount command that *commits* — it writes a squash commit
    plus a merge commit into the consumer's history. Commits are the owner's (D5,
    BOOTSTRAP §A10 "does NOT commit"), so `init` refuses to run it and prints the exact
    command instead; a re-run then finds the subtree in place and does everything else.
    ``--ref`` is required in this mode because a subtree leaves no git metadata of its own:
    once merged, nothing on disk can tell `init` which ref the owner took, and the
    integration record must not invent one.
    """
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
        pin = max(tags, key=_version_key) if tags else "main"
    raise _InitError(
        "mode 'subtree' needs one command `init` must not run for you — `git subtree add` creates commits, and "
        "commits are the owner's (D5). Run it, then re-run init:\n"
        f"    git subtree add --prefix {relative} {repo} {pin} --squash\n"
        f"    akmon init --mode subtree --ref {pin}"
    )


def _mount_vendored(root: Path, mount: Path, ref: str | None, log) -> str:
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
    for name in TREE_MEMBERS:
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
        gitignore.write_text(_MOUNT_GITIGNORE, encoding="utf-8")
    log(f"vendored {copied} standard-tree members into {relative} (pin: {__version__})")
    return __version__


def _package_pin_status(root: Path) -> str:
    """Where the consumer's manifest pins akmon: ``"dev"``, ``"runtime"`` or ``"none"``.

    Delegates to ``bin/sync.py::package_pin_status``, which is also what ``verify.py`` gates on:
    `init` reporting one definition of "pinned" while the contract check enforced another is the
    second-owner defect, and here the two would sit one command apart in the same session. `init`
    still never edits the manifest (it cannot know every dialect) — it reports, and mode
    ``package`` exits non-zero while the answer is not ``dev`` (ADR 0009 §4).
    """
    from akmon import cli

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
    return f"""# TASKS — project backlog

The single backlog for this project. **Index, not a document:** one line per task, detail by
reference; a finished entry moves to `TASKS_ARCHIVE.md`. No dates — git history is the
timeline. Format (akmon `pipelines/tasks.md`):

`- <id> · <title> · <status> · <goal, 12 words max> · [detail](link)`

The id is typed — `A` architecture · `C` code · `N` analysis · `L` learning · `V` release —
and the owning role follows from that letter, so it is not a separate field. Status is one of
`active | blocked | deferred | done`.

- A1 · classify archetype and guardrails · active · pick archetype/language per ARCHETYPES.md; attach its guardrail
- C1 · pin the test runner · active · record `[test].runner` in `{aitna}/.akmon.toml`, reusing this project's manager
"""


def _memory_index() -> str:
    return """# Project memory

Distilled, durable facts about this project — read at session start. One file per fact,
listed here; the learn loop (akmon `pipelines/memory-distill.md`) writes them.

<!-- - [example-fact](example-fact.md) — one-line hook -->
"""


_CHARTERS = {
    "review": "assess what *is* — architecture, risk, trade-offs, conformance; a findings report",
    "architect": "design what *should be* — options, contracts, docs, decision records",
    "engineer": "realize a decided structure in code, with tests",
}


def _charter(role: str, focus: str, aitna: str, package_mode: bool) -> str:
    locate = (
        f"`akmon path` prints the standard's root; a mounted consumer reads `{aitna}/akmon/roles/{role}.md`."
        if package_mode
        else f"Read it at [`{aitna}/akmon/roles/{role}.md`]({aitna}/akmon/roles/{role}.md)."
    )
    return f"""# Agent — {role}

Project charter for the **{role}** role: {focus}.

Role of record: `roles/{role}.md` in the akmon standard. {locate}

Add project-specific scope, standing instructions, and known pitfalls below; the akmon role
stays the single owner of the role's contract — do not restate it here.
"""


def _gitignore_lines(aitna: str) -> list[str]:
    return [
        "# secrets",
        "*.env",
        "!*.env.example",
        "",
        "# dev-layer venv (provisioned only when the project has no Python environment)",
        f"{aitna}/.venv/",
        "",
        "# akmon model routing — per-user/per-session artifacts (never committed)",
        ".claude/model-routing.local.json",
        ".claude/model-routing.log",
        ".claude/second-opinion/",
        ".claude/agents/k_*.md",
    ]


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


def _ci_workflow(aitna: str, package_mode: bool) -> str:
    if package_mode:
        steps = """      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run akmon sync --check
      - run: uv run akmon verify --strict"""
    else:
        steps = f"""      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - run: python3 {aitna}/akmon/bin/sync.py --check
      - run: python3 {aitna}/akmon/bin/verify.py --strict"""
    return f"""name: akmon

on: [push, pull_request]

jobs:
  akmon:
    runs-on: ubuntu-latest
    steps:
{steps}
"""


# --------------------------------------------------------------------------------------
# the AGENTS.md akmon block (hand-owned source text, written only when absent)
# --------------------------------------------------------------------------------------

BLOCK_HEADING = "## Dev layer — akmon"


def _doc_link(name: str, aitna: str, package_mode: bool, ref: str) -> str:
    """A link to a standard document: relative to the mount when one exists, a GitHub link at
    the pinned ref in package mode (there is no tree in the repo to point at — ADR 0009 §4)."""
    if package_mode:
        return f"{AKMON_REPO}/blob/{ref}/{name}"
    return f"{aitna}/akmon/{name}"


def _agents_block(aitna: str, package_mode: bool, ref: str, archetype: str, language: str) -> str:
    def link(name: str) -> str:
        return _doc_link(name, aitna, package_mode, ref)

    guardrails_dir = f"{aitna}/.akmon/guardrails" if package_mode else f"{aitna}/akmon/guardrails"
    roles_hint = (
        f"roles: [`akmon/roles/`]({link('roles/README.md')}) — run `akmon path` to read them locally"
        if package_mode
        else f"roles: [`{aitna}/akmon/roles/`]({aitna}/akmon/roles/)"
    )
    shared_layer = (
        "installed `akmon` package (hooks and tools run from it via `akmon hook`; only the "
        f"imported guardrails are materialized, at `{aitna}/.akmon/guardrails/`; `akmon path` "
        "locates the rest)"
        if package_mode
        else f"`{aitna}/akmon/`"
    )
    return f"""{BLOCK_HEADING} (developing the project)

This project uses the akmon dev layer — one standard for how an assistant helps develop it.
Model & notation: [`MODEL.md`]({link('MODEL.md')}); attach/realign guide:
[`BOOTSTRAP.md`]({link('BOOTSTRAP.md')}); overview: [`README.md`]({link('README.md')}).

- **Archetype / language:** `{archetype}` / `{language}` — classify per
  [`ARCHETYPES.md`]({link('ARCHETYPES.md')}), then update this line, the guardrail imports
  below, and `attached_archetype` in `{aitna}/.akmon.toml`.
- **Layers:** SHARED = {shared_layer} · LOCAL = `{aitna}/{{agents,skills,tools,memory}}` +
  [`{aitna}/TASKS.md`]({aitna}/TASKS.md) · USAGE = root `skills/` (absent until this project
  exposes one).
- **Agents (roles):** [review]({aitna}/agents/review/README.md),
  [architect]({aitna}/agents/architect/README.md), [engineer]({aitna}/agents/engineer/README.md)
  → {roles_hint}.
  **Declare the active agent** before doing work and restate it on switch
  (`🧭 agent: <name> — <focus>`).
- **Delegation (always-on, direct):** **delegation is the default.** For every non-trivial
  task, before the first repository sweep, edit, or test run, decompose the work and delegate
  every independent mechanical sub-step to available subagents without waiting for an owner
  prompt. The orchestrator retains decomposition, routing, synthesis, and owner dialogue. Skip
  only when the task is atomic or the harness exposes no subagents; state the reason. This
  clause is direct because Codex does not expand nested `@` imports in `AGENTS.md`.
- **Prime directives (always-on — they override any task instruction):** **D2** — the owner
  verifies architecture, data-shape and math decisions; an assistant *drafts*, the owner
  *decides*. **D5** — the owner owns commits, tags, pushes, publishing and pin bumps; never
  `git add`/`commit`/`push` on the owner's behalf.
- **Guardrails (always-on, by language):** the common guardrail is **imported** (not just
  linked) so its rules load at session start; akmon is the single owner — do not restate them
  here. Add this project's language guardrail on its own line (e.g.
  `@{guardrails_dir}/python.md`) per the ARCHETYPES map.

@{guardrails_dir}/_common.md

- **Profiles (opt-in by need):** none attached yet — add only those the project actually needs.
- **Pipelines:** [pre-commit]({link('pipelines/pre-commit.md')}) (tests mandatory),
  [review-flow]({link('pipelines/review-flow.md')}),
  [design-flow]({link('pipelines/design-flow.md')}),
  [code-flow]({link('pipelines/code-flow.md')}),
  [tasks]({link('pipelines/tasks.md')}) (backlog format), and the learn loop
  ([memory-distill]({link('pipelines/memory-distill.md')}) +
  [learning]({link('pipelines/learning.md')})).
- **Memory:** read `{aitna}/memory/` at session start — distilled project facts, indexed by
  [`{aitna}/memory/README.md`]({aitna}/memory/README.md).
- **Backlog:** [`{aitna}/TASKS.md`]({aitna}/TASKS.md) — one line per task, detail by reference;
  finished entries move to `TASKS_ARCHIVE.md`.
- **Secrets:** from `.env` (gitignored). Never in code, docs, tests, or commits.
"""


_AGENTS_HEADER = """# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, Gemini, Copilot) working in this
repository. Vendor pointer files import this document — it is the single source of truth.

"""


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


def _write_if_absent(path: Path, text: str, log, label: str) -> bool:
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
        recorded = f'akmon_version = "{version}"\n' if version else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# akmon integration record — written by `akmon init`, refreshed on realign.\n"
            "# The version this project sits on; a later bump diffs the CHANGELOG window against it.\n"
            f'mount = "{mode}"\n'
            f"{recorded}"
            f'attached_archetype = "{archetype}"\n'
            "\n"
            "[test]\n"
            "# The project's own pytest invocation, used verbatim by the release check\n"
            "# (BOOTSTRAP §A5). Uncomment and set it to whatever this project already uses:\n"
            '# runner = "uv run pytest"\n',
            encoding="utf-8",
        )
        return path
    from akmon import cli

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


def _mark_realign_complete(path: Path, version: str | None) -> None:
    """Advance the completion marker after every generated stage has succeeded.

    The other record fields describe the attach being attempted and are useful even when a
    fresh attach stops part-way through.  ``last_realign`` is different: it asserts that both
    sync and model-routing init completed for that version, so an existing value must survive
    either failure and a fresh failed attach must not gain one.
    """
    if not version:
        return
    from akmon import cli

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
    parser.add_argument("--repo", default=AKMON_REPO, help=f"akmon repository URL (default: {AKMON_REPO}).")
    parser.add_argument("--ref", help="Ref to pin (default: the latest release tag).")
    parser.add_argument("--archetype", help="Archetype id per ARCHETYPES.md (default: left unclassified).")
    parser.add_argument("--language", help="Primary language per ARCHETYPES.md (default: left unclassified).")
    parser.add_argument("--no-ci", action="store_true", help="Do not write a CI workflow running sync/verify.")
    parser.add_argument(
        "--switch-mode",
        action="store_true",
        help="Allow changing the recorded mount mode (a migration: it needs manual AGENTS.md edits).",
    )
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        # flush: the sync and model-routing steps run as subprocesses writing straight to the
        # terminal, so a block-buffered parent would narrate the run in the wrong order.
        print(f"akmon init: {message}", flush=True)

    root = (args.project_root or Path.cwd()).resolve()
    if not root.is_dir():
        print(f"akmon init: {root} is not a directory", file=sys.stderr)
        return 2

    next_steps: list[str] = []
    try:
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
        package_mode = mode == "package"
        mount = root / aitna / "akmon"

        switching = bool(previous) and previous != mode
        if switching and args.switch_mode and not package_mode and mount.exists() and any(mount.iterdir()):
            # Between two *mounted* modes the mount itself has to change shape — a submodule's
            # gitlink and `.git`, a subtree's tracked files, a vendored copy's plain files are
            # mutually exclusive states of one path. Retiring the old one deletes tracked files
            # and rewrites git bookkeeping, which is the owner's commit (D5), so `init` refuses
            # rather than half-migrating: the previous shape used to survive underneath the new
            # record, leaving a project that claimed one mode and carried another.
            relative = mount.relative_to(root).as_posix()
            raise _InitError(
                f"switching mount mode {previous!r} → {mode!r} needs the old mount gone first — `init` does not "
                f"delete a tree it did not create, and the removal is your commit (D5). Retire {relative}, then "
                f"re-run:\n{_old_mount_removal(previous, relative)}\n"
                f"    akmon init --mode {mode} --switch-mode"
            )
        if switching and not args.switch_mode:
            raise _InitError(
                f"this project is attached in mount mode {previous!r}; {mode!r} is a **migration**, not a realign — "
                "the AGENTS.md akmon block still points at the old layout and the old mount is still on disk, so "
                "finishing silently would leave `akmon verify --strict` red. Re-run with `--switch-mode` and init "
                "will attach in the new mode and print the edits it must not make for you."
            )

        log(f"attaching to {root}")
        log(f"mount mode: {mode} ({reason}) · dev layer: {aitna}/")
        if switching:
            log(f"migrating the mount mode: {previous} → {mode}")
        if not args.yes and not _confirm(f"akmon init: attach akmon to {root}?"):
            print("akmon init: aborted", file=sys.stderr)
            return 1

        pin_status = "dev"  # only mode `package` pins akmon in the consumer's own manifest
        if mode == "submodule":
            version = _mount_submodule(root, mount, args.repo, args.ref, log, next_steps)
        elif mode == "subtree":
            version = _mount_subtree(root, mount, args.repo, args.ref, log)
        elif mode == "vendored":
            version = _mount_vendored(root, mount, args.ref, log)
        else:
            version = __version__
            pin_status = _package_pin_status(root)
        # Package-mode links and pin instructions name a remote release. Mounted modes derive
        # their recorded ref from the mounted tree instead. Only a *first* package attach asks the
        # remote for its latest release tag: on a realign the ref feeds nothing but the AGENTS.md
        # block `init` preserves and the pin instruction, and the installed version already names
        # it — while a network round-trip there would make the first step of every bump fail
        # offline, with exit 2, for a value the run does not use.
        first_attach = not (root / aitna / ".akmon.toml").is_file()
        ref = args.ref or (
            _package_default_ref(args.repo, root)
            if package_mode and first_attach
            else _tag_for_version(version or __version__)
        )
    except _InitError as exc:
        print(f"akmon init: {exc}", file=sys.stderr)
        return 2

    archetype = "/".join(part for part in (args.archetype, args.language) if part) or "unclassified"
    # --- local layout (LOCAL layer) --------------------------------------------------
    for name in ("agents", "skills", "tools", "memory"):
        (root / aitna / name).mkdir(parents=True, exist_ok=True)
    _write_if_absent(root / aitna / "TASKS.md", _tasks_skeleton(aitna), log, f"{aitna}/TASKS.md")
    _write_if_absent(root / aitna / "memory" / "README.md", _memory_index(), log, f"{aitna}/memory/README.md")
    for role, focus in _CHARTERS.items():
        _write_if_absent(
            root / aitna / "agents" / role / "README.md",
            _charter(role, focus, aitna, package_mode),
            log,
            f"{aitna}/agents/{role}/README.md",
        )

    # --- hand-owned documents: written when absent, never rewritten ------------------
    agents_md = root / "AGENTS.md"
    block = _agents_block(aitna, package_mode, ref, args.archetype or "<archetype>", args.language or "<language>")
    if not agents_md.is_file():
        agents_md.write_text(_AGENTS_HEADER + block, encoding="utf-8")
        log("wrote AGENTS.md with the akmon block")
    elif BLOCK_HEADING in agents_md.read_text(encoding="utf-8"):
        log("AGENTS.md already carries an akmon block — left untouched")
        if not switching:
            next_steps.append("`akmon verify --strict` checks the existing AGENTS.md block against the contract")
    else:
        text = agents_md.read_text(encoding="utf-8")
        separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        agents_md.write_text(text + separator + block, encoding="utf-8")
        log("appended the akmon block to AGENTS.md (existing content preserved)")
    if switching:
        next_steps.extend(_mode_switch_steps(previous, mode, aitna))

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    merged = _merge_gitignore(existing, _gitignore_lines(aitna))
    if merged != existing:
        gitignore.write_text(merged, encoding="utf-8")
        log(".gitignore: added the akmon entries (secrets, dev-layer venv, routing artifacts)")

    workflows = root / ".github" / "workflows"
    existing_workflows = sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml"))
    check_cmds = (
        ("akmon sync --check", "akmon verify --strict")
        if package_mode
        else (f"python3 {aitna}/akmon/bin/sync.py --check", f"python3 {aitna}/akmon/bin/verify.py --strict")
    )
    if args.no_ci:
        next_steps.append(f"add the contract checks to CI: `{check_cmds[0]}` and `{check_cmds[1]}`")
    elif existing_workflows:
        verb = "update the akmon commands in" if switching else "add the contract checks to"
        next_steps.append(f"{verb} your existing workflow(s): `{check_cmds[0]}` and `{check_cmds[1]}`")
    else:
        _write_if_absent(workflows / "akmon.yml", _ci_workflow(aitna, package_mode), log, ".github/workflows/akmon.yml")

    record = _write_akmon_toml(root, aitna, mode=mode, version=version, archetype=archetype)
    log(f"recorded {record.relative_to(root)} (mount={mode}, akmon_version={version or 'unknown'})")

    # --- generated surface: sync, then model routing ---------------------------------
    from akmon import cli

    log("running sync (generated pointers, hook wiring, imported guardrails)")
    code = cli._dispatch("sync", ["--project-root", str(root)], cwd=root)
    if code != 0:
        print(f"akmon init: sync failed ({code}); the attach is incomplete", file=sys.stderr)
        return code

    standard_root = cli._mounted_akmon_root(root) or _tree.embedded_tree_root()
    routing_init = standard_root / "tools" / "model_routing" / "init.py"
    log("running model-routing init (subagent definitions + local routing config)")
    completed = _run([sys.executable, str(routing_init), "--project-root", str(root)], cwd=root)
    if completed.returncode != 0:
        print(f"akmon init: model-routing init failed ({completed.returncode})", file=sys.stderr)
        return completed.returncode

    # --- the judgment steps init deliberately did not do -----------------------------
    if archetype == "unclassified":
        next_steps.insert(
            0,
            "classify the project (archetype + language) against ARCHETYPES.md, attach the language "
            f"guardrail import in AGENTS.md, and set `attached_archetype` in {aitna}/.akmon.toml",
        )
    next_steps.append(
        f"pin the test environment: record the project's own pytest invocation as `[test].runner` in "
        f"{aitna}/.akmon.toml (BOOTSTRAP §A5 — do not build a venv when the project already has one)"
    )
    if package_mode and pin_status == "none":
        next_steps.insert(
            0,
            "**pin akmon in the project's dependency manifest**, in a **dev** group (never a runtime "
            f'dependency): "akmon @ git+{AKMON_REPO}@{ref}" — then install it into a virtualenv inside '
            "the project root. Until both are done, `akmon` cannot resolve here: the CI checks cannot "
            "run, and the generated hook commands fail silently because the console script they name "
            "does not exist",
        )
    elif package_mode and pin_status == "runtime":
        next_steps.insert(
            0,
            "**move the akmon pin** out of the project's runtime dependencies (or extras) into a **dev** "
            "group: akmon is dev tooling and must not reach this project's own users (ADR 0009 §4)",
        )
    from akmon import cli as _cli

    if aitna != _cli._project_root_lib().AITNA_ROOT_DEFAULT:
        next_steps.append(f"export AITNA_ROOT={aitna} in every shell and CI job that runs the akmon tooling")
    next_steps.append("run `akmon verify --strict` and review the diff — the owner commits, not the assistant (D5)")

    # Mode `package` mounts no tree, so the manifest pin *is* the mount: an attach that ends
    # without one has produced a project that looks attached and cannot run a single akmon
    # command. `init` cannot write the pin (it cannot know every manifest dialect), so it says so
    # in the exit code rather than reporting success over an unusable project — the CI job this
    # very run wrote would be the next thing to discover it.
    incomplete = package_mode and pin_status != "dev"
    print()
    log("attached, with steps left to a human/agent decision:" if not incomplete else "attached, but INCOMPLETE:")
    for index, step in enumerate(next_steps, start=1):
        print(f"  {index}. {step}", flush=True)
    if incomplete:
        print()
        log(
            "exit 1: mode 'package' has no akmon pin in a dev group yet (step 1) — nothing else attaches it, "
            "so this attach is not finished. Re-run `akmon init` after adding it (it keeps the recorded mode), or "
            "`akmon verify --strict` to re-check."
        )
        return 1
    _mark_realign_complete(record, version)
    return 0
