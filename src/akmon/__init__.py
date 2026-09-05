"""akmon — the akmon AI-agent development standard, as an installable package (C37).

Zero runtime dependencies (locked, ADR 0009 §1): everything under ``src/akmon/`` is
stdlib only. See ``meta/design/packaging/README.md`` for the operative packaging spec.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# The built version is the static literal in `pyproject.toml`, which hatchling stamps into the
# wheel; the owner bumps it as a release step and the git tag records the reviewed state rather
# than producing the number (package version == standard version, ADR 0009 §1). This fallback
# must stay literally equal to that literal — `tools/release/release_check.py` checks it — and
# is used only when the package is not installed (e.g. run from a source checkout without
# `pip install` / `uv pip install -e`).
_STATIC_VERSION = "0.4.0.dev0"

try:
    __version__ = version("akmon")
except PackageNotFoundError:
    __version__ = _STATIC_VERSION

__all__ = ["__version__"]
