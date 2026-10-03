"""The two carriers of one artifact must ship one file list (ADR 0020 D05, C103).

The standard tree ships twice: embedded in the Python wheel (the ``force-include`` table in
``pyproject.toml``) and in the root npm package (the ``files`` allowlist in
``package.json``). Both lists are hand-kept in different files, so the equality is
asserted rather than trusted — the same move as
``test_init.py::test_tree_members_match_the_wheel_force_include`` proving the vendored
mount against the wheel. The second test covers what declared lists cannot: a dry run
of the carrier itself, proving dev-only state (lockfile, ``node_modules``, the tooling
configs) never reaches the npm tarball while the manifest does.
"""

from __future__ import annotations

import fnmatch
import functools
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)

# hatchling filters force-include entries with these hardcoded constants
# (hatchling/builders/constants.py, measured in C103): the project's custom `exclude` patterns
# do NOT reach force-include, only the `packages` scan. `.ruff_cache`/`__pycache__` never ship
# because of this, whatever the config says.
_HATCHLING_EXCLUDED_DIRS = frozenset(
    {
        "__pycache__",
        ".venv",
        ".git",
        ".hg",
        ".hatch",
        ".tox",
        ".nox",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".pixi",
    }
)
_HATCHLING_EXCLUDED_FILES = frozenset({".DS_Store"})

# npm's hard ignores (probed on npm 12.0.2, M103): files named `.gitignore` and everything
# under a directory carrying a CACHEDIR.TAG are dropped from the pack even when a `files`
# entry covers them, and no negation brings them back.
_NPM_HARD_IGNORED_FILENAMES = frozenset({".gitignore"})


@functools.lru_cache(maxsize=1)
def _npm_cache_dirs() -> frozenset[Path]:
    """Every directory under the tree that carries a CACHEDIR.TAG (npm drops its whole content).

    Memoized: the pack expansion asks about every file, and the question is a whole-tree scan."""
    return frozenset(path.parent for path in _AKMON.rglob("CACHEDIR.TAG") if path.is_file())


def _npm_hard_ignored(rel: str) -> bool:
    """Whether npm cannot pack `rel` at all — the one class of carrier divergence allowed."""
    if rel.rsplit("/", 1)[-1] in _NPM_HARD_IGNORED_FILENAMES:
        return True
    path = _AKMON / rel
    parent = path.parent
    while parent != _AKMON:
        if parent in _npm_cache_dirs():
            return True
        parent = parent.parent
    return False


def _excluded(rel: str, patterns: list[str]) -> bool:
    """A hatch exclude or an npm negation hits a file when the pattern matches the file
    or any of its ancestor directories — ``**/__pycache__`` names the directory, and
    everything under it is out."""
    parts = rel.split("/")
    for length in range(len(parts), 0, -1):
        prefix = "/".join(parts[:length])
        if any(fnmatch.fnmatch(prefix, pattern) for pattern in patterns):
            return True
    return False


def _expand(root: Path, members: list[str]) -> set[str]:
    """Tree-relative POSIX paths each member declares: a file member yields itself, a
    directory member yields every file under it."""
    payload: set[str] = set()
    for member in members:
        path = root / member
        if path.is_file():
            payload.add(member)
        elif path.is_dir():
            payload.update(file.relative_to(root).as_posix() for file in path.rglob("*") if file.is_file())
    return payload


def _wheel_payload() -> set[str]:
    """What the wheel ships as payload: every ``force-include`` member plus the
    ``src/akmon`` package, minus hatchling's filters — evaluated from the declared
    patterns and the builder's constants, not from what the wheel turns out to contain.

    Force-include entries are filtered only by hatchling's hardcoded constants
    (``_HATCHLING_EXCLUDED_*`` above); the custom ``exclude`` patterns apply to the
    ``packages`` scan and are modeled over the whole payload anyway — in this tree they
    match nothing the constants do not already match, so the model and the builder agree."""
    text = (_AKMON / "pyproject.toml").read_text(encoding="utf-8")
    section = text.split("[tool.hatch.build.targets.wheel.force-include]", 1)[1].split("\n[", 1)[0]
    members = [*re.findall(r'^"([^"]+)"\s*=', section, flags=re.MULTILINE), "src/akmon"]

    section = text.split("[tool.hatch.build]", 1)[1].split("\n[", 1)[0]
    excludes = re.findall(r'^\s*"([^"]+)"', section, flags=re.MULTILINE)
    assert excludes, "the hatch excludes section no longer parses — the test would pass on nothing"

    def _hatchling_const_excluded(rel: str) -> bool:
        parts = rel.split("/")
        return any(part in _HATCHLING_EXCLUDED_DIRS for part in parts[:-1]) or parts[-1] in _HATCHLING_EXCLUDED_FILES

    return {
        rel
        for rel in _expand(_AKMON, members)
        if not _hatchling_const_excluded(rel) and not _excluded(rel, excludes)
    }


def _npm_payload() -> set[str]:
    """What the npm package ships as payload: every positive ``files`` entry minus the
    negations, again evaluated from the declared patterns.

    npm's always-included entries stay out of this set on purpose: the manifest
    (``package.json``) is the npm carrier's chrome — its wheel counterpart
    (``pyproject.toml``) is not payload of either carrier; and ``README.md``, ``LICENSE``
    and the ``bin`` target are always included by npm *and* declared ``files`` entries,
    so the declared expansion already covers exactly what the tarball carries.

    npm also hard-ignores files named ``.gitignore`` and ``CACHEDIR.TAG``-marked cache
    directories (probed on npm 12.0.2, M103) — modeled by ``_npm_hard_ignored``. The
    wheel cannot express that drop (hatchling's force-include takes no custom excludes),
    so the one-file divergence — the corpus fixture's ``.gitignore``, inert in both
    carriers — is the only asymmetry the test admits.
    """
    manifest = json.loads((_AKMON / "package.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    positive = [entry for entry in files if not entry.startswith("!")]
    negations = [entry[1:] for entry in files if entry.startswith("!")]
    assert "package.json" not in positive, "the carrier's chrome must not be declared as payload"

    return {rel for rel in _expand(_AKMON, positive) if not _excluded(rel, negations) and not _npm_hard_ignored(rel)}


def test_npm_files_match_the_wheel_force_include():
    """One standard, two carriers, one file list: a member added to one carrier and
    forgotten in the other would silently ship a poorer copy, so the declared payloads
    are expanded against the tree and compared as sets of tree-relative paths.

    Every file npm packs, the wheel ships; every file the wheel ships that npm does not
    pack, npm is mechanically forced to drop (its hard ignores — the corpus fixture's
    ``.gitignore`` today, which hatchling's force-include cannot be told to lose)."""
    wheel = _wheel_payload()
    npm = _npm_payload()
    assert not npm - wheel, f"npm ships what the wheel lacks: {sorted(npm - wheel)}"
    divergence = wheel - npm
    assert all(_npm_hard_ignored(rel) for rel in divergence), (
        f"wheel ships what npm can pack but drops: {sorted(divergence)}"
    )


def test_npm_pack_carries_no_dev_state():
    """The declared list can be right while the pack is not: run the carrier's own
    ``npm pack --dry-run`` and prove the dev-only state — the lockfile, ``node_modules``,
    the tooling configs — never reaches the tarball, while the manifest itself does."""
    if shutil.which("npm") is None:
        pytest.skip("npm is not on PATH; the carrier's tarball cannot be probed")

    proc = subprocess.run(
        ["npm", "pack", "--dry-run"],
        cwd=_AKMON,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )

    # npm prints the notice lines — including the whole "Tarball Contents" listing —
    # to stderr, not stdout.
    paths: list[str] = []
    in_contents = False
    for raw in proc.stderr.splitlines():
        line = raw.removeprefix("npm notice").strip()
        if line == "Tarball Contents":
            in_contents = True
            continue
        if in_contents:
            if line.startswith("Tarball"):  # the "Tarball Details" section ends the list
                break
            if line:
                paths.append(line.split(None, 1)[1])

    assert paths, "no tarball contents parsed — the dry-run output format changed?"
    assert "package-lock.json" not in paths
    assert "package.json" in paths
    for dev_file in ("tsconfig.json", "eslint.config.mjs"):
        assert dev_file not in paths, f"{dev_file} is dev state; it must not ship in the carrier"
    assert not any("node_modules" in path.split("/") for path in paths)
