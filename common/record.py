#!/usr/bin/env python3
"""The one reader of ``<AITNA_ROOT>/.akmon.toml`` — the project's integration record.

The record answers "which carrier is this project on" (ADR 0009 §3), and answering it wrongly
is never loud: a package-mode project beside a stale ``<AITNA_ROOT>/akmon`` had its hooks bind
the stale tree's registry and print stale tool paths, silently (C69/D2-26). Five modules had
grown their own narrow reader before this one existed, each justified in place; the hooks would
have been the sixth, which is what settled it.

Lifted out of ``bin/sync.py`` unchanged — the tomllib-when-present / stdlib-fallback pair and
the quote-aware comment strip are the same code, moved rather than rewritten, so nothing about
how a record parses changed with the move. ``sync`` re-exports both names.
"""

from __future__ import annotations

from pathlib import Path

from common.project_root import aitna_root

_PACKAGE_MODE = "package"


def _strip_inline_comment(value: str) -> str:
    """A TOML value with any trailing ``# comment`` removed, honouring quotes.

    ``tomllib`` does this for free; the narrow fallback in ``read_akmon_toml`` must agree, so
    the very shape BOOTSTRAP §C documents — ``runner = "poetry run pytest"  # optional`` —
    strict and lenient parsing cannot produce different values. A ``#`` inside a quoted value
    is data, not a comment, so a quoted
    value ends at its closing quote and only a bare value is cut at the first ``#``.
    """
    value = value.strip()
    quote = value[:1]
    if quote not in ('"', "'"):
        return value.split("#", 1)[0].strip()
    # Scan to the *closing* quote rather than to the next one: in a basic string a `\"` is an
    # escaped quote, so `find` would end the value in the middle of it and hand back a broken
    # fragment. Literal strings (`'...'`) have no escapes at all, by TOML's definition.
    index = 1
    while index < len(value):
        if quote == '"' and value[index] == "\\":
            index += 2
            continue
        if value[index] == quote:
            return value[: index + 1]
        index += 1
    return value


def read_akmon_toml(path: Path) -> dict:
    """Read ``_aitna/.akmon.toml`` (the integration record) into a nested dict.

    Uses Python 3.11+ ``tomllib``; a minimal stdlib parser remains as a lenient fallback for
    malformed records in this record's subset. It is not a pre-3.11 support promise. Quotes are
    stripped; values are treated as strings. Returns ``{}`` if the
    file is absent, unreadable, or malformed — a caller that needs to *report* a broken record must
    check the file itself rather than infer it from an empty dict."""
    if not path.is_file():
        return {}
    try:
        import tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment]
    if tomllib is not None:
        try:
            with path.open("rb") as handle:
                return tomllib.load(handle)
        except tomllib.TOMLDecodeError:
            # A malformed record falls through to the lenient parser below rather than raising.
            # Two reasons, both measured. It is what this function documents ("absent or
            # unreadable"), and a hook consulting the record must not abort a session over a file
            # it only reads (C69/D2-26). It also keeps strict and lenient parsing aligned on
            # inline comments instead of making malformed-input behavior parser-dependent.
            pass
        except OSError:
            return {}
    data: dict = {}
    section = data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = data.setdefault(stripped[1:-1].strip(), {})
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        section[key.strip()] = _strip_inline_comment(value).strip('"').strip("'")
    return data


def recorded_mount(project_root: Path) -> str | None:
    """The ``mount`` value this project records, or ``None`` when it records nothing.

    ``None`` rather than a default on purpose: the callers that want the backward-compatible
    ``submodule`` default ask ``sync.read_mount_mode`` for it, while a caller deciding whether
    the record *vetoes* something must be able to tell "records submodule" from "records
    nothing at all" — a project that predates the field records nothing, and treating that as a
    declaration would send it somewhere it never asked to go.
    """
    value = read_akmon_toml(aitna_root(project_root) / ".akmon.toml").get("mount")
    return value if isinstance(value, str) and value else None


def records_package_mode(project_root: Path) -> bool:
    """Whether the record declares mount mode ``package`` (ADR 0009 §4).

    Fail-safe by construction: an absent, unreadable or malformed record reads as ``{}`` and
    answers ``False``, so a caller falls back to whatever it would have done without a record.
    That matters most for the hooks, which must never abort a session over a file they only
    consult.
    """
    return recorded_mount(project_root) == _PACKAGE_MODE
