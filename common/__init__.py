"""Shared, stdlib-only utilities every akmon carrier can import.

``bin/`` is the launcher directory — ``sync.py`` and ``verify.py``, the two scripts a project
actually runs. It had also become the library directory, which cost more than a misfiled name:
a library there is reachable only by putting ``bin/`` on ``sys.path`` and importing it under a
bare, generic top-level name (``findings``, ``runtime``, ``versions``), so eight call sites
repeated the same insert, ``src/akmon/cli.py`` had to re-register ``versions`` as
``akmon_versions`` because that name may already belong to a consumer's environment, and the
hooks — which could not reach it cleanly at all — kept their own copy of the project-root walk.

So the utilities live here instead, as one package. Callers put the *tree root* on ``sys.path``
once and import ``common.<module>``. The name states the admission rule rather than the
contents: a module belongs here because every carrier shares it — not because it was
miscellaneous, which is what a ``utils`` would have invited.

The rules that make a module belong here, all of them load-bearing:

- **Standard library only, and no project imports.** These modules run venv-free from a hook,
  from ``tools/``, and from an installed wheel's embedded tree; anything they import has to be
  present in all three.
- **Python 3.9.** The floor the package declares (``requires-python``), older than the tree's
  own dev environment, so it is checked, not assumed.
- **Reachable at the same tree-relative path from every carrier**: the mounted
  ``<AITNA_ROOT>/akmon/``, the materialized ``<AITNA_ROOT>/.akmon/`` copy that package mode
  writes, and ``akmon/_tree/`` inside the wheel. That is what lets one owner exist at all, and
  it is why this directory is in both ``pyproject.toml``'s force-include list and
  ``bin/sync.py::_materialized_files``.

Deliberately no re-exports here: a fact has one spelling, and ``from common import X``
beside ``from common.x import X`` would be two.
"""
