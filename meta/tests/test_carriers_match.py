"""The two carriers of one artifact must ship one file list (ADR 0020 D05, C103).

The standard tree ships twice: embedded in the Python wheel (the ``force-include`` table and
the ``only-include`` + ``sources`` members in ``pyproject.toml``) and in the root npm package (the
``files`` allowlist in ``package.json``). Both lists are hand-kept in different files, so the
equality is asserted rather than trusted — the same move as
``test_init.py::test_tree_members_match_the_wheel_members`` proving the vendored mount against
the wheel. Neither carrier ships akmon's development record (``meta/``) or a test file (ADR 0009,
C118 amendment). The dry-run test covers what declared lists cannot: the carrier itself, proving
dev-only state (lockfile, ``node_modules``, the tooling configs, ``meta/``, the JS tests) never
reaches the npm tarball while the manifest does.
"""

from __future__ import annotations

import fnmatch
import functools
import json
import posixpath
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)

# hatchling filters force-include entries with these hardcoded constants
# (hatchling/builders/constants.py, measured in C103): the project's custom `exclude` patterns
# do NOT reach force-include, only the `only-include` members. `.ruff_cache`/`__pycache__` never ship
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
    """Whether npm cannot pack `rel` at all, even when a `files` entry covers it."""
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
    """What the wheel ships as payload: every ``force-include`` member and every ``only-include``
    member (``src/akmon`` among them), minus hatchling's filters — evaluated from the declared
    patterns and the builder's constants, not from what the wheel turns out to contain.

    Force-include entries are filtered only by hatchling's hardcoded constants
    (``_HATCHLING_EXCLUDED_*`` above); the custom ``exclude`` patterns apply to the
    ``only-include`` members alone (measured on hatchling 1.27, C118) — which is why ``js/``, the
    member whose tests must not ship, is an ``only-include`` one."""
    build = tomllib.loads((_AKMON / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]
    wheel = build["targets"]["wheel"]
    excludes = build["exclude"]
    assert excludes, "the hatch excludes no longer parse — the test would pass on nothing"

    def _hatchling_const_excluded(rel: str) -> bool:
        parts = rel.split("/")
        return any(part in _HATCHLING_EXCLUDED_DIRS for part in parts[:-1]) or parts[-1] in _HATCHLING_EXCLUDED_FILES

    forced = {rel for rel in _expand(_AKMON, list(wheel["force-include"])) if not _hatchling_const_excluded(rel)}
    selected = {
        rel
        for rel in _expand(_AKMON, wheel["only-include"])
        if not _hatchling_const_excluded(rel) and not _excluded(rel, excludes)
    }
    return forced | selected


def _npm_payload() -> set[str]:
    """What the npm package ships as payload: every positive ``files`` entry minus the
    negations, again evaluated from the declared patterns.

    npm's always-included entries stay out of this set on purpose: the manifest
    (``package.json``) is the npm carrier's chrome — its wheel counterpart
    (``pyproject.toml``) is not payload of either carrier; and ``README.md``, ``LICENSE``
    and the ``bin`` target are always included by npm *and* declared ``files`` entries,
    so the declared expansion already covers exactly what the tarball carries.

    npm also hard-ignores files named ``.gitignore`` and ``CACHEDIR.TAG``-marked cache
    directories (probed on npm 12.0.2, M103) — modeled by ``_npm_hard_ignored``. The one
    shipped file it used to drop, the corpus fixture's ``.gitignore``, left with ``meta/``
    (C118), so the two carriers admit no asymmetry at all.
    """
    manifest = json.loads((_AKMON / "package.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    positive = [entry for entry in files if not entry.startswith("!")]
    negations = [entry[1:] for entry in files if entry.startswith("!")]
    assert "package.json" not in positive, "the carrier's chrome must not be declared as payload"

    return {rel for rel in _expand(_AKMON, positive) if not _excluded(rel, negations) and not _npm_hard_ignored(rel)}


def test_npm_files_match_the_wheel():
    """One standard, two carriers, one file list: a member added to one carrier and
    forgotten in the other would silently ship a poorer copy, so the declared payloads
    are expanded against the tree and compared as sets of tree-relative paths. No divergence
    is allowed: the one npm hard-ignore that once forced one (a ``.gitignore`` fixture under
    ``meta/conformance``) no longer ships (C118)."""
    wheel = _wheel_payload()
    npm = _npm_payload()
    assert not npm - wheel, f"npm ships what the wheel lacks: {sorted(npm - wheel)}"
    assert not wheel - npm, f"the wheel ships what npm lacks: {sorted(wheel - npm)}"


def _development_only(rel: str) -> bool:
    """Akmon's development record or a test file — what no carrier ships (ADR 0009, C118)."""
    return rel.split("/", 1)[0] == "meta" or rel.endswith(".test.mjs")


def test_no_carrier_ships_meta_or_test_files():
    """The declared payloads, as hatchling and npm would expand them, carry no ``meta/`` and no
    ``*.test.mjs`` — guarding against a member list or a negation that regresses."""
    assert any(rel.endswith(".test.mjs") for rel in _expand(_AKMON, ["js"])), "the tree has no JS tests to drop?"
    for name, payload in (("wheel", _wheel_payload()), ("npm", _npm_payload())):
        leaked = sorted(rel for rel in payload if _development_only(rel))
        assert not leaked, f"the {name} carrier ships development-only files: {leaked}"


# A Markdown link target: inline `[text](target "title")` or a reference definition `[id]: target`.
_MD_LINK_RE = re.compile(r"\]\(\s*<?([^)\s>]+)|^\s*\[[^\]]+\]:\s*<?([^\s>]+)", re.MULTILINE)
_MD_FENCE_RE = re.compile(r"^(`{3,}|~{3,}).*?^\1", re.MULTILINE | re.DOTALL)
_REPO_META_URL = re.compile(r"https://github\.com/akumidv/ai_akmon/(blob|tree)/main/(meta(?:/[^#]*)?)(?:#(.*))?")


def _md_link_targets(text: str) -> list[str]:
    """Every link target in a Markdown text, fenced code blocks left out (a path there is code)."""
    prose = _MD_FENCE_RE.sub("", text)
    return [inline or reference for inline, reference in _MD_LINK_RE.findall(prose)]


def _github_slug(heading: str) -> str:
    """GitHub's heading anchor: lowercased, punctuation dropped, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_shipped_docs_link_into_meta_by_repository_url():
    """``meta/`` does not ship, so a shipped document's relative link into it would dangle in a mount
    and on a registry page: it links by absolute repository URL instead (ADR 0009, C118 amendment).
    The shipped set is the wheel payload (equal to npm's, above), not a hand list. Each such URL is
    mapped back to the checkout and must name an existing path — and heading, when it carries an
    anchor — so a renamed decision or measurement file does not leave a dead link behind."""
    shipped = sorted(rel for rel in _wheel_payload() if rel.endswith(".md"))
    assert "README.md" in shipped, "the shipped set no longer parses — the test would pass on nothing"
    relative: list[str] = []
    dead: list[str] = []
    checked = 0
    for rel in shipped:
        for target in _md_link_targets((_AKMON / rel).read_text(encoding="utf-8")):
            url = _REPO_META_URL.fullmatch(target)
            if url:
                checked += 1
                kind, path, anchor = url.groups()
                resolved = _AKMON / path
                if not (resolved.is_dir() if kind == "tree" else resolved.is_file()):
                    dead.append(f"{rel} → {target}")
                elif anchor and anchor not in {
                    _github_slug(line.lstrip("#"))
                    for line in resolved.read_text(encoding="utf-8").splitlines()
                    if line.startswith("#")
                }:
                    dead.append(f"{rel} → {target} (no such heading)")
                continue
            if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
                continue
            joined = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target.split("#", 1)[0]))
            if joined == "meta" or joined.startswith("meta/"):
                relative.append(f"{rel} → {target}")
    assert not relative, f"shipped docs link into meta/ relatively (use the repository URL): {relative}"
    assert not dead, f"shipped docs link to meta/ paths that do not exist: {dead}"
    assert checked, "no repository-URL link into meta/ found — the URL pattern no longer matches?"


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
    for dev_file in ("tsconfig.json", ".oxlintrc.json", ".oxfmtrc.json"):
        assert dev_file not in paths, f"{dev_file} is dev state; it must not ship in the carrier"
    assert not any("node_modules" in path.split("/") for path in paths)
    leaked = sorted(path for path in paths if _development_only(path))
    assert not leaked, f"the tarball ships development-only files: {leaked}"
