"""Make the keystone hook and bin modules importable for keystone's own tests.

The hook entrypoints import ``hook_core`` / ``claude_adapter`` by bare name, and ``verify``
imports ``sync`` by bare name — both rely on the script directory being on ``sys.path`` at
runtime. Tests live one level up, so add ``hooks`` and ``bin`` explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

_KEYSTONE = Path(__file__).resolve().parent.parent
for _subdir in ("hooks", "bin"):
    _path = str(_KEYSTONE / _subdir)
    if _path not in sys.path:
        sys.path.insert(0, _path)
