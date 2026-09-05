"""``akmon`` console entry point — a thin CLI dispatching to the standard tree.

``init`` / ``sync`` / ``verify`` / ``path`` / ``version`` per the CLI contract in
``meta/design/packaging/README.md``. ``init`` (all four mount modes) lives in
``akmon._init``; this module keeps only the dispatch rules.

Version-skew rule (design doc, "sync / verify"): when a mounted tree exists at
``<AITNA_ROOT>/akmon`` the launcher runs *that* tree's ``bin/sync.py`` / ``bin/verify.py``
(subprocess, so the pinned standard governs, not whatever CLI version is installed) and
prints a one-line notice if the CLI's own version differs from the pin recorded in
``<AITNA_ROOT>/.akmon.toml``; otherwise it runs the embedded tree's copies (importing their
``main`` when possible, else subprocess). Mode ``package`` has no mount at all — the package
*is* the pin — so it always resolves to the embedded tree. ``init`` runs before any mount
exists and therefore starts embedded; once it has mounted the standard, the sync it runs
goes through this same dispatch, so the freshly pinned tree governs from that point on.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from akmon import __version__, _tree

_DISPATCHED_COMMANDS = {"sync", "verify"}


def _load_module_from_path(path: Path, name: str) -> ModuleType:
    """Load ``path`` as module ``name``, registered in ``sys.modules`` under that name.

    Registration happens *before* ``exec_module`` (the standard ``importlib`` recipe), not
    after: a module using ``from __future__ import annotations`` with dataclasses needs
    ``sys.modules[__name__]`` to already resolve to itself while its class bodies execute
    (dataclass's string-annotation resolution looks itself up there) — sync.py is exactly
    such a module.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _load_embedded_common(tree_root: Path) -> ModuleType:
    """Load ``tree_root/common/`` as the package ``common``, for *this* tree.

    The tree the CLI runs is the tree that answers, so a swapped ``tree_root`` must never
    resolve to a previously loaded copy (akmon's own tests swap the embedded tree inside one
    process). The package is registered with its ``__path__`` pointed at this tree, and every
    ``common`` entry from a different tree is discarded first; submodules then resolve
    through that ``__path__``, so no ``sys.path`` mutation is needed and nothing leaks either
    way. Re-registration is skipped when the loaded package already belongs to this tree.

    Registering it is required, not merely convenient: the embedded ``bin/sync.py`` and
    ``bin/verify.py`` import ``common.*`` by name, and the import statement consults
    ``sys.modules`` before it consults ``sys.path``.
    """
    package_dir = (tree_root / "common").resolve()
    loaded = sys.modules.get("common")
    if loaded is not None and Path(next(iter(loaded.__path__), "")).resolve() == package_dir:
        return loaded
    for name in [n for n in sys.modules if n == "common" or n.startswith("common.")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        "common", package_dir / "__init__.py", submodule_search_locations=[str(package_dir)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load 'common' from {package_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["common"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("common", None)
        raise
    return module


def _embedded_common_module(tree_root: Path, name: str) -> ModuleType:
    """One module out of ``tree_root``'s ``common`` — e.g. ``versions``, ``project_root``."""
    _load_embedded_common(tree_root)
    return importlib.import_module(f"common.{name}")


def _load_embedded_sync(tree_root: Path) -> ModuleType:
    """Load ``tree_root/bin/sync.py`` fresh, registered as ``sys.modules['sync']``.

    ``verify.py`` does a bare ``import sync``; registering under that name (the import
    statement checks ``sys.modules`` before touching ``sys.path``) resolves it
    deterministically to *this* ``tree_root``'s own copy — no ``sys.path`` mutation, so no
    leakage across differing ``tree_root`` values used within one process (e.g. across test
    fixtures that swap the embedded tree).
    """
    _load_embedded_common(tree_root)  # sync.py imports `common.*`; resolve them first.
    return _load_module_from_path(tree_root / "bin" / "sync.py", "sync")


def _project_root_lib() -> ModuleType:
    """The embedded tree's ``common.project_root`` — the owner of the dev-layer name.

    Asked rather than answered again here, for the same reason as :func:`_split_version` below:
    the tree that ships with this CLI is in lockstep with it, so delegating costs nothing and
    leaves one definition. Note this is *not* the dependency :func:`_mounted_akmon_root` must
    avoid — that one is on the **consumer's** mounted or materialized tree, whose content is
    exactly what that function is deciding about.
    """
    return _embedded_common_module(_tree.embedded_tree_root(), "project_root")


def _toml_scalar(raw: str) -> str:
    """A ``.akmon.toml`` scalar: a quoted string's content, else the bare value up to a ``#``.

    The same rule as ``bin/sync.py::_strip_inline_comment`` + quote stripping, kept local for
    the reason the reader itself is local (below). Without it the documented shape
    ``mount = "package"  # materialized`` read back as ``package"  # materialized`` — i.e. not
    ``package`` — and a package-mode project whose record carried a comment silently fell back
    to the mounted-tree branch, the exact skew this field exists to prevent.
    """
    value = raw.strip()
    quote = value[:1]
    if quote not in ('"', "'"):
        return value.split("#", 1)[0].strip()
    index = 1
    while index < len(value):
        if quote == '"' and value[index] == "\\":
            index += 2
            continue
        if value[index] == quote:
            return value[1:index]
        index += 1
    return value[1:]


def _read_top_level_toml_value(path: Path, key: str) -> str | None:
    """A minimal top-level ``key = "value"`` reader for ``.akmon.toml`` (stops at the first
    ``[section]`` header). A narrow, self-contained duplicate of ``sync.py``'s fuller
    ``read_akmon_toml`` — kept local (not imported) for the same reason mount detection
    reimplements its own marker check below: this decides which tree to trust, so it must
    not itself depend on either tree's content.
    """
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            break
        found_key, sep, value = stripped.partition("=")
        if sep and found_key.strip() == key:
            return _toml_scalar(value)
    return None


def _mounted_akmon_root(start: Path) -> Path | None:
    """The mounted tree root (``<AITNA_ROOT>/akmon``) for ``start``'s project, if any.

    A deliberate, narrow duplication of ``bin/sync.py``'s own marker check
    (``_find_project_root`` + ``akmon_root``: an ``AGENTS.md`` file plus an existing
    ``<AITNA_ROOT>/akmon`` directory, walking up from ``start``) rather than a reuse: this
    function's job is to decide *which* tree's code the CLI should trust for everything
    else, so it must not itself depend on either tree's content.

    Also honours ``<AITNA_ROOT>/.akmon.toml``'s ``mount`` field when present:
    ``mount = "package"`` means "run the embedded tree unconditionally, no skew by
    construction" (ADR 0009 §4-5) — a stale ``<AITNA_ROOT>/akmon`` left over from a prior
    mode must not shadow it, so this returns ``None`` (no mount) even if that directory
    still exists on disk.
    """
    aitna_name = _project_root_lib().aitna_root_name()
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file():
            aitna_dir = candidate / aitna_name
            if _read_top_level_toml_value(aitna_dir / ".akmon.toml", "mount") == "package":
                return None
            akmon_root = aitna_dir / "akmon"
            if akmon_root.exists():
                return akmon_root
    return None


def _split_version(recorded: str) -> tuple[str, str | None]:
    """Split a recorded version into the part to compare and its ``git describe`` distance.

    Delegates to the embedded tree's ``common/versions.py``, the sole owner of the rule
    (C54 lifted it there): release-time checking asks the same question, and the second copy
    that would answer it is the pattern C46 exists to remove. Returns ``(base, commits_ahead)``;
    ``commits_ahead`` is ``None`` when the recorded string names a version exactly.
    """
    return _embedded_common_module(_tree.embedded_tree_root(), "versions").split_version(recorded)


def _skew_notice(mounted_root: Path) -> str | None:
    """One-line notice when the CLI's own version differs from the mounted tree's pin.

    Reads ``<AITNA_ROOT>/.akmon.toml``'s ``akmon_version`` (the consumer's recorded pin).
    Absent for a project that has not realigned yet — nothing to compare, no notice.

    Comparison normalizes first (F9/6): the pin and ``__version__`` reach this function in
    different spellings by construction, so a raw equality fires on every command in a mounted
    consumer. A ``git describe`` distance is a **separate** notice — the mounted tree is past the
    tag this CLI matches, which is not the same fact as a version mismatch — and both notices
    render each version as it was recorded rather than re-prefixing it.
    """
    sync_mod = _load_embedded_sync(_tree.embedded_tree_root())
    aitna = mounted_root.parent
    fields = sync_mod.read_akmon_toml(aitna / ".akmon.toml")
    pinned = fields.get("akmon_version")
    if not pinned:
        return None
    pinned_base, ahead = _split_version(pinned)
    cli_base, _ = _split_version(__version__)
    if pinned_base != cli_base:
        return (
            f"akmon: CLI is {__version__}, mounted/pinned standard is {pinned} "
            "— the mounted tree governs."
        )
    if ahead is not None:
        commits = "commit" if ahead == "1" else "commits"
        return (
            f"akmon: mounted/pinned standard is {pinned}, {ahead} {commits} past the tag this CLI "
            "matches — the mounted tree governs."
        )
    return None


def _run_mounted(script: str, mounted_root: Path, argv: list[str]) -> int:
    """``exec`` the mounted tree's launcher as a subprocess (skew rule)."""
    script_path = mounted_root / "bin" / f"{script}.py"
    result = subprocess.run([sys.executable, str(script_path), *argv])
    return result.returncode


def _run_embedded(script: str, argv: list[str]) -> int:
    """Run the embedded tree's launcher: import its ``main`` when possible, else subprocess."""
    tree_root = _tree.embedded_tree_root()
    script_path = tree_root / "bin" / f"{script}.py"
    try:
        if script == "verify":
            _load_embedded_sync(tree_root)  # verify.py does `import sync`; resolve it first.
        else:
            _load_embedded_common(tree_root)  # every launcher imports the shared utilities.
        module = _load_module_from_path(script_path, f"_akmon_embedded_{script}")
        main = module.main
    except Exception:
        # Not (cleanly) importable — fall back to running the embedded file directly.
        result = subprocess.run([sys.executable, str(script_path), *argv])
        return result.returncode
    return main(argv)


def _dispatch(script: str, argv: list[str], *, cwd: Path | None = None) -> int:
    cwd = cwd if cwd is not None else Path.cwd()
    mounted_root = _mounted_akmon_root(cwd)
    if mounted_root is not None:
        notice = _skew_notice(mounted_root)
        if notice:
            print(notice, file=sys.stderr)
        return _run_mounted(script, mounted_root, argv)
    return _run_embedded(script, argv)


def _cmd_path(*, cwd: Path | None = None) -> int:
    cwd = cwd if cwd is not None else Path.cwd()
    mounted_root = _mounted_akmon_root(cwd)
    root = mounted_root if mounted_root is not None else _tree.embedded_tree_root()
    print(root)
    return 0


def _cmd_version() -> int:
    print(__version__)
    return 0


def _cmd_init(argv: list[str]) -> int:
    """Attach the standard to a project. Imported lazily: ``_init`` imports this module back
    (for the dev-layer root resolver and the post-mount sync dispatch), and only ``init``
    pays for loading it."""
    from akmon import _init

    return _init.main(argv)


_COMMANDS = ("init", "sync", "verify", "path", "version")

# `argparse.add_subparsers` + a REMAINDER positional mis-parses a remainder that starts
# with "-" (e.g. `akmon sync --check`) — a known argparse limitation. A single top-level
# `command` choice + one REMAINDER positional sidesteps it; per-command help text is
# supplied via the epilog instead of per-subparser help.
_EPILOG = """commands:
  init      attach the standard to a project (mount + layout + sync + routing)
  sync      sync generated agent pointers (bin/sync.py)
  verify    verify a consuming project's USE contract (bin/verify.py)
  path      print the resolved standard-tree root
  version   print the akmon package version

sync/verify/init accept their own flags, passed through verbatim, e.g.:
  akmon init --mode package
  akmon sync --check
  akmon verify --strict
  akmon init --help
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akmon",
        description="akmon — the akmon AI-agent development standard, as an installable package.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=_COMMANDS, help=argparse.SUPPRESS)
    parser.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command in _DISPATCHED_COMMANDS:
        return _dispatch(args.command, args.args)
    if args.command == "path":
        return _cmd_path()
    if args.command == "version":
        return _cmd_version()
    if args.command == "init":
        return _cmd_init(args.args)
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover - choices already restrict this
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
