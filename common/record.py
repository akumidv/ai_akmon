#!/usr/bin/env python3
"""The one reader of ``<AITNA_ROOT>/.akmon.toml`` — the project's integration record.

The record answers "which carrier is this project on" (ADR 0009 §3), and answering it wrongly
is never loud: a package-mode project beside a stale ``<AITNA_ROOT>/akmon`` had its hooks bind
the stale tree's registry and print stale tool paths, silently (C69/D2-26). Before this module
existed, ``bin/sync.py`` held the original reader and four other modules had grown narrow
readers of their own, each justified in place. C75 folded three of those four —
``release_check``, ``model_routing/init.py`` and the CLI (through the embedded tree's copy) —
plus two callers that count missed: ``src/akmon/_init.py::_recorded_mount``, which borrowed the
CLI's private reader, and ``hooks/hook_core.py::d2_sensitive_paths``, which had kept its own bare
``tomllib`` call. One reader stays local on purpose — ``d2_ledger.py`` needs the strict parse
this module deliberately is not, and its docstring says why (D2-39). A static carrier,
``meta/tests/test_record_owner.py`` (C83), keeps a new reader from growing.

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

    Uses Python 3.11+ ``tomllib`` when available; a minimal stdlib line parser is the fallback,
    used both when ``tomllib`` is absent and when it raises ``TOMLDecodeError`` on a malformed
    file — lenient parsing, not a pre-3.11 support promise. Quotes are stripped; values are
    treated as strings. Returns ``{}`` only when the file is absent or unreadable (``OSError``);
    a malformed file is read leniently by the fallback parser instead and can come back
    non-empty, so a caller that needs to *report* a broken record must check the file itself
    rather than infer it from the result."""
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


class RecordError(ValueError):
    """The integration record exists but cannot be read as TOML."""


def read_akmon_toml_strict(path: Path) -> dict:
    """Read ``_aitna/.akmon.toml`` strictly: ``{}`` when the file is absent, the parsed table
    otherwise, and :class:`RecordError` when it cannot be read or does not parse.

    :func:`read_akmon_toml` is lenient on purpose, and that is right for a caller that only
    *consults* the record. It is wrong for one that *applies* it: the Python rule configuration
    (ADR 0014 §4) is read to switch rules on and off, and the lenient fallback flattens a nested
    table into strings — a broken record would silently leave a rule on, or off, instead of
    saying so. Such a caller takes this entry point and reports the error.
    """
    if not path.is_file():
        return {}
    import tomllib

    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RecordError(f"{path.name} cannot be read as TOML: {exc}") from exc


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

    Fail-safe by construction, not fail-empty: an absent or unreadable record reads as ``{}`` and
    answers ``False``. A malformed record is parsed leniently instead — the fallback line parser
    can still resolve a ``mount = "package"`` line out of an otherwise-broken file, so this can
    answer ``True`` off a record that would fail a strict parse. Either way no caller aborts a
    session over a file it only consults; a caller that must *reject* a broken record has to check
    the file itself, as ``d2_ledger.py`` does (C75).
    """
    return recorded_mount(project_root) == _PACKAGE_MODE
