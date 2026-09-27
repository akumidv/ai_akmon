"""Shared JSON data files: one loader, loud failure (C102).

akmon ships data next to the code that reads it: policy tables, message texts, matcher
and path lists. Both permanent implementations read the same files (ADR 0020 D03, design
[node-consumers.md](../meta/design/node-consumers.md)): Python with stdlib ``json``, Node
with ``JSON.parse`` — so a text or table is written once and the corpus proves both
spell it identically.

Conventions the JS port mirrors:

- a file holds exact text; ``{{name}}`` marks a value the code fills at runtime. The code
  computes every value — formatted numbers, quoted names — before calling :func:`fill`;
  no format specifier ever reaches the data file.
- a data file is read once at the entry point and passed down: never at import time,
  with no module-level cache. Helpers take the parsed data as a parameter; a public
  function a caller may also use on its own takes it as an optional trailing ``data``
  argument and reads the file only when called without one — that call is then its own
  entry point. What the rule forbids is a read per line or per item of a report (C102
  review F2: ``verify`` once parsed ``verify.json`` 1,140 times); a hook, which makes one
  decision, may still read through a few single-shot accessors.
- a crash handler reads no data file: its text stays in code, because a missing or broken
  data file is one of the failures it reports (C102 review F1).
- a missing or broken file raises :class:`DataFileError` naming the file — a data file
  the standard ships is a dependency, not an optional input.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")


class DataFileError(RuntimeError):
    """A shared data file is missing or unreadable; the message names the file."""


def read(path: Path) -> Any:
    """Parse one data file, failing loudly (and naming the file) on absence or breakage."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataFileError(f"akmon data file missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataFileError(
            f"akmon data file {path} is not valid JSON (line {exc.lineno}, column {exc.colno})"
        ) from exc


def fill(template: str, values: Mapping[str, str]) -> str:
    """Replace every ``{{name}}`` placeholder in stored text; an unfilled one raises."""

    def _one(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise DataFileError(f"placeholder {{{{{key}}}}} in a data template has no value")
        return str(values[key])

    return _PLACEHOLDER.sub(_one, template)
