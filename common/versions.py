#!/usr/bin/env python3
"""How akmon spells a version, in one place.

The same standard reaches a comparison under several spellings by construction: mounted mode
records ``git describe --tags`` (``v0.3.0``, optionally ``-N-g<sha>``, optionally ``-dirty``),
package mode records installed metadata (``0.4.0.dev0`` — PEP 440, no ``v``), ``pyproject.toml``
carries the literal hatchling stamps into the wheel, and ``CHANGELOG.md`` headings carry the
``v``-prefixed form. Two callers need the same rule — the CLI's skew notice (C61) and the
release-time version join (C54, F9/6) — so the rule has one owner rather than two copies.

Stdlib-only and dependency-free by contract: it ships in ``bin/`` beside ``findings.py`` and
must import on the declared Python floor with no venv.

Two questions are answered here and nowhere else:

:func:`split_version`
    What part of a recorded string names the version, and how far past it the tree is. A
    leading ``v`` is a *spelling*; a ``git describe`` distance is a separate fact about the
    tree. A PEP 440 pre/post/dev segment is neither — it names a different version and keeps
    comparing unequal.
:func:`is_final`
    Whether a version names a release or something on the way to one. The classification is
    **binary by construction**: final is exactly ``X.Y.Z`` with no distance past a tag, and
    everything else — every PEP 440 non-final segment (``.devN``, ``aN``/``bN``/``rcN``,
    ``.postN``, ``+local``), any unrecognized spelling, and any version a ``describe`` distance
    says the tree has already moved past — is non-final. No spelling falls between the two, so
    no caller needs a third branch and no version escapes both rules.
"""

from __future__ import annotations

import re

#: ``git describe --tags`` distance from the tag: ``-<N>-g<sha>``, optionally ``-dirty``.
DESCRIBE_SUFFIX_RE = re.compile(r"-(\d+)-g[0-9a-f]+(?:-dirty)?$")

#: A final release version, after :func:`split_version` has removed the spelling.
FINAL_RE = re.compile(r"\d+\.\d+\.\d+")


def split_version(recorded: str) -> tuple[str, str | None]:
    """Split a recorded version into the part to compare and its ``git describe`` distance.

    Returns ``(base, commits_ahead)``; ``commits_ahead`` is ``None`` when the recorded string
    names a version exactly rather than a position past a tag.
    """
    base = recorded.strip()
    ahead = None
    match = DESCRIBE_SUFFIX_RE.search(base)
    if match:
        ahead = match.group(1)
        base = base[: match.start()]
    if base[:1] == "v":
        base = base[1:]
    return base, ahead


def is_final(recorded: str) -> bool:
    """True when ``recorded`` names a release: exactly ``X.Y.Z``, and not past a tag."""
    base, ahead = split_version(recorded)
    return ahead is None and FINAL_RE.fullmatch(base) is not None
