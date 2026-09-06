"""Resolve the embedded akmon standard-tree root.

The standard tree (the full akmon repo minus ``src/`` — README, roles/, pipelines/,
guardrails/, hooks/, bin/, common/, tools/, meta/, …) ships as package data under ``akmon/_tree/``
(hatchling force-include, see ``pyproject.toml``). This module is the single place that
resolves its filesystem root; the CLI's ``path``/``sync``/``verify`` dispatch use it.
"""

from __future__ import annotations

from pathlib import Path

# src/akmon/_tree.py -> parents[2] is the akmon repo root in an editable/source-checkout
# layout (src/akmon/_tree.py, src/akmon/, src/, <akmon-root>/).
_EDITABLE_ROOT = Path(__file__).resolve().parents[2]

# The ordinary wheel layout: the force-included data sits beside this module.
_ADJACENT_TREE = Path(__file__).resolve().parent / "_tree"


def embedded_tree_root() -> Path:
    """Absolute path to the embedded standard tree.

    Installed (wheel) package: the force-included ``akmon/_tree`` package-data directory —
    the plain path beside this module, which is what ``importlib.resources`` resolves to for a
    filesystem install. Editable/source checkout, where the force-included data is not
    materialized under ``site-packages``: falls back to the akmon repo root this source file
    lives in, which *is* the standard tree itself.

    The filesystem check comes first and ``importlib.resources`` is imported only if it misses.
    That import costs ~45 ms (it pulls ``inspect``, ``typing`` and ``tempfile``), and since C77
    this module is on the path of every ``akmon hook`` call — i.e. of every tool call in a
    package-mode session. The answers are the same: for any install this function can return a
    ``Path`` for at all, the data is a real directory beside the module. The resources lookup is
    kept for the loader layouts where it is not.
    """
    if _ADJACENT_TREE.is_dir():
        return _ADJACENT_TREE
    try:
        from importlib import resources

        traversable = resources.files("akmon") / "_tree"
        if traversable.is_dir():
            return Path(str(traversable))
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        pass
    if (_EDITABLE_ROOT / "bin" / "sync.py").is_file():
        return _EDITABLE_ROOT
    return _ADJACENT_TREE
