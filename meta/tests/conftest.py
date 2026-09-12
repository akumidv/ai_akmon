"""Make the akmon hook, launcher and library modules importable for akmon's own tests.

The hook entrypoints import ``hook_core`` / ``claude_adapter`` by bare name, and ``verify``
imports ``sync`` by bare name — both rely on the script directory being on ``sys.path`` at
runtime. The shared utilities are imported as ``common.<module>``, which needs the tree root
itself. Tests live under ``meta/tests/``, so resolve the akmon root by walking up to the
directory that holds ``hooks`` and ``bin`` (robust to where the tests sit).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_KEYSTONE = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
# ``meta`` joins them so the dev-only ``checks`` package (akmon's own declaration checkers,
# whose single production caller is ``meta/self_ci.py``) imports by the same bare name here.
for _subdir in (".", "hooks", "bin", "meta", "tools/model_routing"):
    _path = str((_KEYSTONE / _subdir).resolve())
    if _path not in sys.path:
        sys.path.insert(0, _path)

from self_ci import path_without  # noqa: E402

from common.runtime import codex_hooks_list_command  # noqa: E402


@pytest.fixture(scope="session")
def _codex_free_path(tmp_path_factory) -> str:
    return path_without(
        codex_hooks_list_command()[0],
        os.environ.get("PATH", os.defpath),
        tmp_path_factory.mktemp("codex-free-path"),
    )


@pytest.fixture(autouse=True)
def _codex_absent_in_tests(monkeypatch, _codex_free_path):
    """Every test runs on a host without Codex, the way self-CI's fixture legs do (C70).

    ``verify``'s host-trust check spawns a real ``codex app-server`` whenever a fixture's
    ``.codex/hooks.json`` is current and ``codex`` resolves on ``PATH`` — true on any host that
    has Codex installed, this one included — and no fixture here has been through `/hooks`.
    ``verify`` also runs as a genuine child process in some tests (mounted-mode ``akmon verify``
    re-execs the standard tree's script), which an in-process patch of ``shutil.which`` cannot
    reach; ``PATH`` is inherited by every child, so hiding the binary there reaches them all and
    exercises the check's own absent-installation skip rather than a switch in ``verify``. The
    tests that exercise the live-query path inject a runner or put a fake ``codex`` on ``PATH``.
    """
    monkeypatch.setenv("PATH", _codex_free_path)
