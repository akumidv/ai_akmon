"""Resolve the embedded akmon standard-tree root.

The standard tree (the full akmon repo minus ``src/`` — README, roles/, pipelines/,
guardrails/, hooks/, bin/, tools/, meta/, …) ships as package data under ``akmon/_tree/``
(hatchling force-include, see ``pyproject.toml``). This module is the single place that
resolves its filesystem root; the CLI's ``path``/``sync``/``verify`` dispatch use it.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

# src/akmon/_tree.py -> parents[2] is the akmon repo root in an editable/source-checkout
# layout (src/akmon/_tree.py, src/akmon/, src/, <akmon-root>/).
_EDITABLE_ROOT = Path(__file__).resolve().parents[2]


def embedded_tree_root() -> Path:
    """Absolute path to the embedded standard tree.

    Installed (wheel) package: the force-included ``akmon/_tree`` package-data directory,
    resolved via ``importlib.resources``. Editable/source checkout, where the force-included
    data is not materialized under ``site-packages``: falls back to the akmon repo root this
    source file lives in, which *is* the standard tree itself.
    """
    try:
        traversable = resources.files("akmon") / "_tree"
        if traversable.is_dir():
            return Path(str(traversable))
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        pass
    if (_EDITABLE_ROOT / "bin" / "sync.py").is_file():
        return _EDITABLE_ROOT
    # Last-resort fallback: an installed-but-not-force-included layout would place the data
    # alongside this module.
    return Path(__file__).resolve().parent / "_tree"
