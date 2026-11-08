#!/usr/bin/env python3
"""The one owner of "where is the project root" and "what is the dev-layer called".

Both questions were answered independently by seven modules (C73): three walked up for
``AGENTS.md`` beside either a mounted tree or a package integration record, one ignored
package mode, and three additionally hard-coded ``_aitna`` past an environment variable. Every one of
them ended the walk with ``return start`` — the current directory — so a command that had
found nothing was indistinguishable from one that had found the root, and it went on to write
its artifacts under the cwd. Since the answer decides which registry binds and where a gate
pack lands, it is one fact and gets one owner.

The dev-layer root is declared by a file, not by the environment (ADR 0022 D09): ``<root>/.aitna-root``
holds one project-root-relative POSIX path, an absent file means ``_aitna``, and ``dev_root`` is the
accessor that answers it together with how it was found.

Stdlib-only and free of project imports on purpose — see ``common/__init__.py`` for why
that, and the package's reachability from every carrier, is what lets a single owner exist at
all. There is no second definition left: ``hooks/hook_core.py`` imports from here too.
"""

from __future__ import annotations

import errno
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# The dev-layer (LOCAL) root is configurable: ``_aitna`` is the default, but a project may
# relocate it by committing ``.aitna-root`` (one line: a path relative to the project root, e.g.
# ``tools/ai``). akmon is always mounted at ``<aitna-root>/akmon``. Public because the
# *default* itself is a fact callers ask for: ``akmon init`` writes the declaration only when
# the chosen root is not this one.
AITNA_ROOT_DEFAULT = "_aitna"

# The file at the project root that declares a dev-layer root other than the default.
DEV_ROOT_FILE = ".aitna-root"

# The two dotted folders under the dev root (ADR 0028 D01): ``.local`` holds what only this
# machine needs (learning state, model overlays), ``.ergon`` holds one ergon per piece of work.
# Both are gitignored. The local index retired with ADR 0028 D12, so no row is written anywhere.
LOCAL_DIR_NAME = ".local"
ERGON_DIR_NAME = ".ergon"

# The folder the local layer had before ADR 0028; named only so the legacy check can find it.
_LEGACY_LOCAL_DIR_NAME = "local"

# How a dev root was found (``DevRoot.origin``).
ORIGIN_POINTER = "pointer"
ORIGIN_DEFAULT = "default"
ORIGIN_NO_PROJECT_ROOT = "no-project-root"

# The longest start path the walk accepts, in UTF-8 bytes: Linux's PATH_MAX. No longer path
# names anything the kernel can look up, and resolving one costs time quadratic in its depth.
_START_PATH_MAX_BYTES = 4096

# How much of a refused start path its error message quotes.
_REFUSED_PREFIX_CHARS = 40

# How long the git probe that resolves a worktree's main checkout may take.
_GIT_TIMEOUT_SECONDS = 10


def resolve_path(path: Path) -> Path:
    """``path.resolve()`` that refuses a symlink loop on every interpreter, as the 3.12 floor does.

    CPython 3.12 raises ``RuntimeError("Symlink loop from '<path>'")`` for a loop even in
    non-strict mode; 3.13 stopped raising there and answers the path unresolved (M154). The
    floor's answer is the spec — the JavaScript twin ``resolvePath`` and the corpus tables
    follow it — so the loop is asked of the strict walk first, which reports it on every
    interpreter, and any other failure of that walk (a missing component, a file used as a
    directory) is the non-strict answer's to give.

    Raises:
        RuntimeError: a symlink on the path loops.
    """
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise RuntimeError(f"Symlink loop from {exc.filename!r}") from exc
    return path.resolve()


@dataclass(frozen=True)
class DevRoot:
    """The dev-layer root of a project and how it was found.

    ``path`` is ``<project root>/<name>`` — absolute when the project root is — except for
    ``ORIGIN_NO_PROJECT_ROOT``, where there is no root to anchor it and it is the bare default
    name, usable for reading only: a writer of the local layer stops there.
    """

    path: Path
    origin: str


def validated_dev_root_name(value: str, project_root: Path, source: str = "--aitna-root") -> str:
    """A dev-layer root as a project-root-relative POSIX path, or a ``ValueError`` naming ``value``.

    The root is *project-root-relative* by contract and ``akmon init`` writes a whole layout under
    it — backlog, memory, charters, the integration record, and in package mode the materialized
    imported guardrails. An absolute path or one climbing out with ``..`` would scatter all of
    that outside the project the caller named, silently, because every later step simply follows
    the declaration. Checked both lexically and by resolution: a symlinked segment can leave the
    project without a single ``..`` in the string. ``source`` names the declaration in the message
    (``--aitna-root`` or ``.aitna-root``).

    Raises:
        ValueError: the value is empty, absolute, climbs with ``..`` or resolves outside the project.
    """
    raw = value.strip()
    # Absoluteness is decided on the *raw* value: stripping the slashes first would turn
    # `/tmp/escaped` into the innocent-looking relative `tmp/escaped` and let it through.
    if Path(raw).is_absolute():
        raise ValueError(f"{source} must be relative to the project root and stay inside it: {value!r}")
    cleaned = raw.strip("/")
    if not cleaned:
        raise ValueError(f"{source} cannot be empty")
    candidate = Path(cleaned)
    if ".." in candidate.parts:
        raise ValueError(f"{source} must be relative to the project root and stay inside it: {value!r}")
    resolved = resolve_path(project_root / candidate)
    if resolve_path(project_root) not in resolved.parents:
        raise ValueError(f"{source} resolves outside the project root: {resolved}")
    return cleaned


def dev_root(project_root: Path | None) -> DevRoot:
    """The dev-layer root of ``project_root``, and how it was found (ADR 0022 D09).

    ``<project_root>/.aitna-root`` holds one line, a project-root-relative POSIX path: ``pointer``
    when it names the root, ``default`` (``_aitna``) when the file is absent. ``None`` — no
    project root was found — answers ``_aitna`` as ``no-project-root``, for reading only.

    Raises:
        ValueError: the declaration is empty, spans several lines, is absolute, climbs with
            ``..`` or resolves outside the project.
    """
    if project_root is None:
        return DevRoot(Path(AITNA_ROOT_DEFAULT), ORIGIN_NO_PROJECT_ROOT)
    declaration = project_root / DEV_ROOT_FILE
    if not declaration.is_file():
        return DevRoot(project_root / AITNA_ROOT_DEFAULT, ORIGIN_DEFAULT)
    text = declaration.read_text(encoding="utf-8").strip()
    if len(text.splitlines()) > 1:
        raise ValueError(f"{DEV_ROOT_FILE} must hold one line, a project-root-relative path: {text!r}")
    return DevRoot(project_root / validated_dev_root_name(text, project_root, DEV_ROOT_FILE), ORIGIN_POINTER)


def aitna_root_name(project_root: Path | None) -> str:
    """The dev-layer root of ``project_root`` as a project-root-relative POSIX path (default ``_aitna``)."""
    found = dev_root(project_root)
    if project_root is None:
        return found.path.as_posix()
    return found.path.relative_to(project_root).as_posix()


def aitna_root(project_root: Path | None) -> Path:
    """Absolute dev-layer root for ``project_root`` (see ``dev_root``)."""
    return dev_root(project_root).path


def local_root(project_root: Path | None) -> Path:
    """The local layer ``<dev root>/.local`` of ``project_root`` (ADR 0028 D01).

    The path, computed — not a claim that it exists. With no project root it is the default-name
    relative path (``_aitna/.local``), usable for reading only, as ``aitna_root`` is.
    """
    return aitna_root(project_root) / LOCAL_DIR_NAME


def git_common_root(project_root: Path | None) -> Path | None:
    """The main checkout of the repository that holds ``project_root``, or ``project_root`` itself.

    A linked worktree keeps its own working tree but shares the repository, so
    ``git rev-parse --git-common-dir`` answers where the repository really is. The ergons live in
    the main checkout (ADR 0028 D11), so the accessor resolves them through it: a session in a
    worktree writes into the main checkout's ergons, and one ergon is one folder for the project.

    The probe runs on every call and its answer is not kept: a cached root is module state a later
    call cannot see the end of — a worktree added or removed while a process lives would keep
    answering the old one. A caller that asks repeatedly passes the resolved root down.

    Outside a repository, or when git is absent, the answer is the project root unchanged. With
    no project root at all, the answer is ``None``, as everywhere else in this module.
    """
    if project_root is None:
        return None
    return _resolve_git_common_root(project_root)


def _git_answer(project_root: Path) -> tuple[Path, str] | None:
    """The repository's resolved common directory and ``project_root``'s prefix in its working tree.

    The prefix is ``mono/proj/``, or empty at the top. ``None`` when git cannot say: no git, a
    timeout, a missing directory, or no repository.
    """
    try:
        done = subprocess.run(  # a fixed argument list, no shell
            ["git", "rev-parse", "--git-common-dir", "--show-prefix"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    common, _, prefix = done.stdout.partition("\n")
    common = common.strip()
    if not common:
        return None
    path = Path(common)
    if not path.is_absolute():
        path = project_root / path
    try:
        return path.resolve(), prefix.strip()
    except OSError:
        return None


def _resolve_git_common_root(project_root: Path) -> Path:
    """The main checkout's copy of ``project_root``, read from git; the project root when there is none.

    One git call answers two things: the repository's common directory (its parent is the main
    checkout) and the project root's own prefix inside its working tree. A project in a repository
    subfolder (``mono/proj``) keeps that subfolder in the main checkout, so its ergons stay its own
    and do not land in the repository top's dev root (ADR 0028 D11).
    """
    answer = _git_answer(project_root)
    if answer is None:
        return project_root
    common, prefix = answer
    # The common directory is the repository's ``.git``; its parent is the main checkout.
    top = common.parent if common.name == ".git" else common
    root = top / prefix
    return root if (root / DEV_ROOT_FILE).is_file() or (root / "AGENTS.md").is_file() else project_root


def ergon_root(project_root: Path | None) -> Path:
    """The ergon layer ``<dev root>/.ergon`` of ``project_root`` (ADR 0028 D01, D11; ADR 0029 D02).

    The path, computed — not a claim that it exists. With no project root it is the default-name
    relative path (``_aitna/.ergon``), usable for reading only, as ``aitna_root`` is. In a linked
    worktree it is the main checkout's folder: the ergons are shared, the working tree is not.
    """
    return dev_root(git_common_root(project_root)).path / ERGON_DIR_NAME


def legacy_local_root(project_root: Path | None) -> Path:
    """The pre-0028 local layer ``<dev root>/.local`` of ``project_root``.

    Used only to detect the old folder and warn that it moves by hand to ``.local`` and
    ``.ergon`` (ADR 0028 D01); akmon never reads state from it and never moves it. The path,
    computed — not a claim that it exists.
    """
    return aitna_root(project_root) / _LEGACY_LOCAL_DIR_NAME


def akmon_mount(project_root: Path | None) -> Path:
    """Absolute akmon mount for ``project_root`` (``<aitna-root>/akmon``).

    The *mounted* tree's path, computed — not a claim that it exists, and not a claim that it is
    the tree that runs: a package-mode project has no mount at all (ADR 0009 §4-5). Which tree
    runs is ``hooks/hook_core.py::akmon_runtime_root``'s question, and since C77 it answers with
    the tree it is executing from — so a stale mount left over from a prior mode cannot shadow
    anything, because it is not a candidate.
    """
    return aitna_root(project_root) / "akmon"


def is_project_root(candidate: Path) -> bool:
    """A project ``AGENTS.md`` beside a mounted tree, an integration record or ``.aitna-root``.

    The record (``<dev root>/.akmon.toml``) is the only marker a package-mode project
    carries, since it has no mounted tree at all (ADR 0009 §4); requiring the tree alone is
    the defect that made ``second_opinion.py`` and its two neighbours miss such a project
    entirely and fall back to the cwd. The declaration file is a marker of its own (ADR 0022 D09):
    a project that names its dev root has said it is one. Without the file the dev root is the
    default, so the question never has to read the declaration.
    """
    if not (candidate / "AGENTS.md").is_file():
        return False
    if (candidate / DEV_ROOT_FILE).is_file():
        return True
    aitna = candidate / AITNA_ROOT_DEFAULT
    return (aitna / "akmon").exists() or (aitna / ".akmon.toml").is_file()


def _bounded_start(start: Path | None = None) -> Path:
    """``start`` (default: the cwd), refused when its string is longer than the walk accepts.

    The bound is checked on the string before any filesystem call — ``resolve()`` included —
    because the cost it guards is in those calls: a start of 32,769 ``a/`` components kept a hook
    resolving it for minutes (C121). The length is counted in UTF-8, with a lone surrogate (an
    undecodable byte in a ``cwd``) as three bytes, the way the JavaScript twin counts it.

    Raises:
        UnicodeEncodeError: the start path holds a surrogate the filesystem encoding refuses.
        ValueError: the start path's string is longer than ``_START_PATH_MAX_BYTES``.
    """
    origin = start if start is not None else Path.cwd()
    text = str(origin)
    # A path no filesystem call can take (a lone surrogate) is refused first, as ``resolve()``
    # refuses it: the JavaScript hooks check that before the bound, so the two twins name the
    # same failure for an over-long path that is also unencodable.
    os.fsencode(text)
    size = len(text.encode("utf-8", "surrogatepass"))
    if size > _START_PATH_MAX_BYTES:
        raise ValueError(
            f"project-root start path is {size} bytes, over the {_START_PATH_MAX_BYTES}-byte bound: "
            f"{text[:_REFUSED_PREFIX_CHARS]}..."
        )
    return origin


def locate_project_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default: the cwd) to the nearest project root, or ``None``.

    The answer a writer of the local layer needs: ``None`` is "no project root", so it writes
    nothing, where ``find_project_root`` hands back a guess. The walk is linear: each step is the
    candidate's parent, until the parent stops changing.

    Raises:
        ValueError: the start path is longer than ``_START_PATH_MAX_BYTES``.
    """
    candidate = resolve_path(_bounded_start(start))
    while not is_project_root(candidate):
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent
    return candidate


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: the cwd) to the nearest project root, else ``start``.

    The fallback is deliberate and stays: a hook must not abort a session because it was
    invoked outside a project. Callers that *write* under the result must not use it bare —
    ``resolve_project_root`` hands them the same path plus the sentence to print, because
    there the fallback is a guess with a file written on top of it. A start path longer than
    ``_START_PATH_MAX_BYTES`` is not a fallback: it is refused with a ``ValueError`` before it is
    resolved (``_bounded_start``), and a hook takes that as its ordinary failure exit (C121).

    ``hooks/hook_core.py`` imports this rather than repeating it. That was previously deferred
    on the belief that it waited on the C69/ADR-0009/D02 fork; it does not. That fork is about which
    *tree* the hooks read (``akmon_runtime_root``), not about where the project root is, and the
    only real dependency — that this package sit beside ``hooks/`` — holds in every carrier by
    construction, since C77 leaves the hooks running inside the tree that ships them.

    Raises:
        ValueError: the start path is longer than ``_START_PATH_MAX_BYTES``.
    """
    found = locate_project_root(start)
    return found if found is not None else resolve_path(_bounded_start(start))


def resolve_project_root(explicit: Path | None, start: Path | None = None) -> tuple[Path, str | None]:
    """The root a command-line entry point works in, plus the notice it must print if it guessed.

    Returns ``(root, None)`` when the root was named on the command line or found by the walk,
    and ``(cwd, notice)`` when it was not. The notice exists because the fallback root is where
    the tool then reads its registry and writes its reports: unstated, a gate pack under a wrong
    root looks exactly like one under the right root, which is the failure C73 was filed for. A
    command that writes the local layer prints the notice and stops (ADR 0022 D09).
    """
    if explicit is not None:
        return resolve_path(explicit), None
    origin = resolve_path(_bounded_start(start))
    found = locate_project_root(origin)
    if found is not None:
        return found, None
    notice = (
        f"[akmon] no project root at or above {origin}: expected AGENTS.md beside {DEV_ROOT_FILE}, "
        f"{AITNA_ROOT_DEFAULT}/akmon or {AITNA_ROOT_DEFAULT}/.akmon.toml. Falling back to that directory, "
        f"so anything this command reads or writes is relative to it; pass --project-root to name the root instead."
    )
    return origin, notice
