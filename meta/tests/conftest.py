"""Make the keystone hook and bin modules importable for keystone's own tests.

The hook entrypoints import ``hook_core`` / ``claude_adapter`` by bare name, and ``verify``
imports ``sync`` by bare name — both rely on the script directory being on ``sys.path`` at
runtime. Tests live under ``meta/tests/``, so resolve the keystone root by walking up to
the directory that holds ``hooks`` and ``bin`` (robust to where the tests sit).
"""

from __future__ import annotations

import sys
from pathlib import Path

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
for _subdir in ("hooks", "bin"):
    _path = str(_KEYSTONE / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)
