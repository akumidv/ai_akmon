"""akmon — the akmon AI-agent development standard, as an installable package (C37).

Zero runtime dependencies (locked, ADR 0009 §1): everything under ``src/akmon/`` is
stdlib only. See ``meta/design/packaging-uvx-init.md`` for the operative packaging spec.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# The release pipeline cuts the real version from the git tag (package version == standard
# version, ADR 0009 §1); this placeholder is only used when the package is not installed
# (e.g. run from a source checkout without `pip install` / `uv pip install -e`).
_STATIC_VERSION = "0.3.0.dev0"

try:
    __version__ = version("akmon")
except PackageNotFoundError:
    __version__ = _STATIC_VERSION

__all__ = ["__version__"]
