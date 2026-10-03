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

Five questions are answered here and nowhere else:

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
:func:`order_key`
    Where one version sits among releases, as a comparable tuple. Below the release it keeps
    the PEP 440 chain in PEP 440 order — ``.devN < aN < bN < rcN < release`` — and gives a
    development version of a step a place of its own, before that step.
:func:`compare_versions`
    Which of two versions comes first — what ``akmon update`` asks before it moves a pin, so
    that it never moves one backwards unasked (A23). A development version comes before its
    release, every pre-release step comes before the release, a ``git describe`` distance after
    it. Callers compare **through this function**: an order key is data, and comparing two keys
    with ``<`` is correct for Python tuples and wrong for JavaScript arrays (which compare as
    strings), so the ordering has one owner here instead of one per language.
:func:`semver_spelling`
    The SemVer carrier spelling of a PEP 440 version — the npm side of the same version line
    (ADR 0020 D05: the ``package.json`` version is derived from the PEP 440 one by this logic,
    never hand-written). Only a final release and its own development version are carriable.
    What SemVer cannot express without lying about order — a ``.postN`` (which sorts *after* the
    release), a ``+local`` build, a distance past a tag, and every pre-release step (``aN``,
    ``bN``, ``rcN``, alone or with a ``.devN`` of its own) — raises rather than guesses: the
    spelling SemVer would form for those sorts ``alpha < beta < dev < rc`` where PEP 440 sorts
    ``dev < a < b < rc``.
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


#: The release a version names or is on the way to: its leading ``X.Y.Z``.
_RELEASE_PREFIX_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

#: A development version of the release itself: the ``.dev0`` of ``0.4.0.dev0``, with nothing
#: between the release and it. Its number is not read — the place is the same for every ``.devN``.
_DEV_OF_RELEASE_RE = re.compile(r"\.dev\d+")

#: A pre-release step of the release, and the development version of that step: ``0.5.0a1``,
#: ``0.5.0a1.dev0``. PEP 440's spelled-out aliases (``alpha``, ``beta``, ``pre``, ``preview``,
#: ``c``) are deliberately absent — the tail this rule cannot name is not quietly read as a
#: step of the chain.
_PRE_RELEASE_RE = re.compile(r"\.?(a|b|rc)\d+(?:\.dev(\d+))?")

#: ``order_key``'s fourth element for a version at the release itself, and for anything past it
#: (a ``git describe`` distance, a ``-dirty`` tree, a ``.postN`` or a ``+local`` build).
_AT_RELEASE_POSITION = 0
_PAST_RELEASE_POSITION = 1

#: ``order_key``'s fourth element for each pre-release step, in PEP 440 order. The steps take
#: the odd places below the release so that each has the even place beneath it free for its own
#: development version — ``1.0.0rc1.dev0`` at -2 sorts before ``1.0.0rc1`` at -1, the way
#: PEP 440 sorts them.
_PRE_RELEASE_POSITION = {"rc": -1, "b": -3, "a": -5}

#: A development version of the release precedes every pre-release step of it, so it sits one
#: place below the first step (``a``).
_DEV_OF_RELEASE_POSITION = -7

#: A tail that is neither the release, nor past it, nor one of the steps this rule can name:
#: one place before the release, the coarse answer the rule gave every such spelling before the
#: steps were separated.
_BEFORE_RELEASE_POSITION = -1


def _position_before_release(rest: str) -> int:
    """Where a release's tail sits below the release, in PEP 440 order.

    ``rest`` is what follows the ``X.Y.Z`` of a version that is neither the release itself nor
    past it. The chain is ``.devN < aN < bN < rcN < release``, and PEP 440 puts a development
    version of a step *before* that step (``1.0.0a1.dev0 < 1.0.0a1``), which is why the steps
    are spaced two apart.
    """
    if _DEV_OF_RELEASE_RE.fullmatch(rest) is not None:
        return _DEV_OF_RELEASE_POSITION
    match = _PRE_RELEASE_RE.fullmatch(rest)
    if match is None:
        return _BEFORE_RELEASE_POSITION
    step = _PRE_RELEASE_POSITION[match[1]]
    return step - 1 if match[2] is not None else step


def order_key(recorded: str) -> tuple[int, int, int, int] | None:
    """Where ``recorded`` sits among releases, for ordering versions; ``None`` when unrecognized.

    ``(X, Y, Z, position)``. ``position`` is 0 for the release itself and 1 for anything past it
    — a ``git describe`` distance, a ``-dirty`` tree, a ``.postN`` or a ``+local`` build. Below
    the release it names the PEP 440 steps apart rather than lumping them: -7 a development
    version of the release (``.devN``), -6 and -5 an alpha and its own development version, -4
    and -3 the same pair of betas, -2 and -1 the same pair of release candidates. Spacing the
    steps two apart is what leaves room for ``1.0.0a1.dev0`` to sort before ``1.0.0a1``, as
    PEP 440 does; a tail the rule cannot name keeps -1, one place before the release. Two
    versions past the same release compare equal, because their order is not a fact a version
    string carries.
    """
    base, ahead = split_version(recorded)
    match = _RELEASE_PREFIX_RE.match(base)
    if match is None:
        return None
    rest = base[match.end() :]
    if ahead is not None or rest.startswith(("-", ".post", "+")):
        position = _PAST_RELEASE_POSITION
    elif not rest:
        position = _AT_RELEASE_POSITION
    else:
        position = _position_before_release(rest)
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch, position


def compare_versions(a: str, b: str) -> int:
    """Which of two recorded versions comes first: ``-1``, ``0`` or ``1``.

    ``order_key`` answers where one version sits; this is the ordering its callers actually
    want, so that the comparison has one owner instead of one per language — a JavaScript
    ``<`` on two order keys compares their *string* forms (``"0,10,0," < "0,9,0,"``), which
    is not the same answer. Unrecognized input raises: a version the rule cannot place cannot
    be ordered, and guessing would move a pin on a coin flip (A23).
    """
    key_a = order_key(a)
    key_b = order_key(b)
    if key_a is None or key_b is None:
        unplaceable = a if key_a is None else b
        raise ValueError(f"{unplaceable!r} is not a version order_key can place, so the two cannot be compared")
    if key_a < key_b:
        return -1
    return 0 if key_a == key_b else 1


def semver_spelling(recorded: str) -> str:
    """The SemVer carrier spelling of a PEP 440 version (the npm side of the version line).

    A final release spells itself (``0.4.1``) and a development version of it carries its
    segment across as a SemVer pre-release (``0.4.0.dev0`` → ``0.4.0-dev.0``). A leading ``v``
    is a spelling and is dropped. Nothing else is carriable. SemVer §11 compares pre-release
    identifiers left to right and sorts an alphanumeric one by ASCII, so the chain a derived
    spelling would form reads ``alpha < beta < dev < rc`` while PEP 440 reads
    ``dev < a < b < rc``: ``aN``/``bN``/``rcN`` (each alone or with its own ``.devN``) are refused
    because spelling them would put the npm side in an order its PEP 440 side denies. The same
    reason refuses a ``.postN`` (which sorts *after* the release), a ``+local`` build and a
    ``git describe`` distance. Each raises :class:`ValueError` naming the input, because a
    carrier that cannot be spelled is reported (the release check skips it), never guessed.
    """
    base, ahead = split_version(recorded)
    if ahead is not None:
        raise ValueError(
            f"{recorded!r} is a distance past its tag — a position, not a version the npm carrier can spell"
        )
    if FINAL_RE.fullmatch(base) is not None:
        return base
    match = re.fullmatch(r"(\d+\.\d+\.\d+)\.dev(\d+)", base)
    if match is not None:
        return f"{match[1]}-dev.{match[2]}"
    raise ValueError(
        f"{recorded!r} is not an npm-carriable PEP 440 version: .postN, +local and a pre-release step "
        "(aN, bN, rcN, each with or without its own .devN) have no SemVer spelling"
    )
