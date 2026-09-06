"""akmon — the akmon AI-agent development standard, as an installable package (C37).

Zero runtime dependencies (locked, ADR 0009 §1): everything under ``src/akmon/`` is
stdlib only. See ``meta/design/packaging/README.md`` for the operative packaging spec.
"""

from __future__ import annotations

# The built version is the static literal in `pyproject.toml`, which hatchling stamps into the
# wheel; the owner bumps it as a release step and the git tag records the reviewed state rather
# than producing the number (package version == standard version, ADR 0009 §1). This fallback
# must stay literally equal to that literal — `tools/release/release_check.py` checks it — and
# is used only when the package is not installed (e.g. run from a source checkout without
# `pip install` / `uv pip install -e`).
_STATIC_VERSION = "0.4.0.dev0"

__all__ = ["__version__"]


def __getattr__(name: str) -> str:
    """Resolve ``__version__`` on first access (PEP 562), not on import.

    ``importlib.metadata.version()`` walks every installed distribution's metadata. That cost
    was invisible while the package was a command a human typed; since the generated hook
    wiring calls ``akmon hook <name>`` on the hottest tools of a session (C77), every hook
    invocation paid it — including the hooks that never ask for a version. Caching into
    ``globals()`` means the lookup happens at most once per process, and only if something
    asks.

    Callers must reach it through the module (``import akmon`` … ``akmon.__version__``):
    ``from akmon import __version__`` resolves this attribute at *import* time and puts the
    whole cost straight back.
    """
    if name != "__version__":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib.metadata import PackageNotFoundError, version

    try:
        resolved = version("akmon")
    except PackageNotFoundError:
        resolved = _STATIC_VERSION
    globals()["__version__"] = resolved
    return resolved
