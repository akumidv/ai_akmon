#!/usr/bin/env python3
"""``akmon tool browser`` from the Python package: a wrapper around the one Node implementation.

The tool is written once, in Node, because the Chrome DevTools protocol and its MCP server live in
Node's toolchain (ADR 0020, amendment to D01; ADR 0032/D02). This file adds no behaviour: it finds
``node`` on ``PATH``, needs major version 22 or newer, and runs ``js/tools/browser.mjs`` of the tree it
sits in with the arguments, the standard streams and the exit status passed through unchanged. With no
usable ``node`` it says so in one line and exits ``2``; it never installs a runtime.

Stdlib-only; nothing happens at import time.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

NODE_FLOOR = 22
"""The oldest Node major version the implementation runs on (``engines.node`` of the npm package)."""

_EXIT_PREREQUISITE = 2
_EXIT_INTERRUPTED = 130


class NodeUnusableError(RuntimeError):
    """``node`` cannot run the tool: it is absent, did not answer, or is older than :data:`NODE_FLOOR`."""


def _node_version(node: str) -> tuple[int, ...]:
    """The version ``node`` reports as a tuple of integers.

    Raises:
        NodeUnusableError: when ``node`` does not answer ``--version`` with a version.
    """
    unanswered = NodeUnusableError(
        f"akmon tool browser: Node.js {NODE_FLOOR} or newer is required; `{node} --version` did not answer"
    )
    try:
        run = subprocess.run([node, "--version"], capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise unanswered from error
    text = run.stdout.strip().removeprefix("v")
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError as error:
        raise unanswered from error


def _require_node(node: str | None) -> str:
    """The ``node`` to run, checked.

    Raises:
        NodeUnusableError: with the one line saying why Node cannot run the tool.
    """
    if node is None:
        raise NodeUnusableError(
            f"akmon tool browser: Node.js {NODE_FLOOR} or newer is required and `node` is not on PATH"
        )
    version = _node_version(node)
    if version[0] < NODE_FLOOR:
        found = ".".join(str(part) for part in version)
        raise NodeUnusableError(
            f"akmon tool browser: Node.js {NODE_FLOOR} or newer is required, found {found} at {node}"
        )
    return node


def main(argv: Sequence[str] | None = None, *, node: str | None = None) -> int:
    """Run ``js/tools/browser.mjs`` with ``argv`` and return node's exit status.

    ``node`` names the interpreter; the default is the first ``node`` on ``PATH``. An unusable ``node``
    is one line and exit ``2``; Ctrl-C ends quietly with exit ``130``, as a shell reports it.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        interpreter = _require_node(node or shutil.which("node"))
        script = Path(__file__).resolve().parent.parent / "js" / "tools" / "browser.mjs"
        if not script.is_file():
            print(f"akmon tool browser: {script} is missing from this tree", file=sys.stderr)
            return _EXIT_PREREQUISITE
        code = subprocess.run([interpreter, str(script), *arguments], check=False).returncode
    except NodeUnusableError as error:
        print(error, file=sys.stderr)
        return _EXIT_PREREQUISITE
    except KeyboardInterrupt:
        return _EXIT_INTERRUPTED
    return 128 - code if code < 0 else code


if __name__ == "__main__":
    raise SystemExit(main())
