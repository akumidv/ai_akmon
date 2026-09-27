#!/usr/bin/env python3
"""ADR 0012 F18 — akmon's shipped always-loaded share, measured against akmon's own tree.

The consumer-total scope is `verify.py`'s (the consumer owns most of that population and is
warned about it). This is the other half of the ratchet: the share akmon itself ships reaches
every attached project without anyone asking for it, so an overage is akmon's error, not the
consumer's warning.

The population is built the way a consumer receives it and never from a second copy of the
text: the block comes from the generator `akmon init` runs, the guardrail chain is resolved from
this tree through the shared counter, and the language profile is the **largest** one akmon
ships — akmon cannot know which profile a project selects, so it is accountable for the biggest
one it offers. Package mode is measured because its block is the longer of the two (the shared
layer and the document links are spelled out for a tree-less consumer).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from common import always_loaded
from common.findings import Finding

#: Only the link text varies with the pin, a few bytes over the whole block.
_REF = "v0.0.0"
_AITNA = "_aitna"
_FIX_OVER = (
    "Move material out of the AGENTS.md akmon block, the guardrail chain it imports, or the "
    "language profiles — or re-baseline the cap in ADR 0012 F18 with owner acceptance"
)
_FIX_OK = "Keep the shipped block, its guardrail chain and the largest language profile inside the cap"


def _generated_block(akmon_root: Path) -> str:
    """The AGENTS.md text `akmon init` writes, read from the generator itself."""
    if str(akmon_root / "src") not in sys.path:
        sys.path.insert(0, str(akmon_root / "src"))
    from akmon import _init  # noqa: PLC0415 — the generator is the source of this text

    block = _init._agents_block(_AITNA, _REF, "<archetype>", "<language>", package_mode=True)
    return _init._agents_header() + block


def _largest_profile(akmon_root: Path) -> Path:
    """The language profile that costs the most; ties resolve by name so the pick is stable."""
    profiles = sorted(akmon_root.joinpath("profiles").glob("*.md"))
    return max(profiles, key=lambda path: (len(path.read_bytes()), path.name))


def shipped_population(akmon_root: Path) -> always_loaded.Population:
    """What a package-mode consumer loads from akmon before it asks for anything."""
    agents = _generated_block(akmon_root)
    with tempfile.TemporaryDirectory(prefix="akmon-always-loaded-") as tmp:
        root = Path(tmp)
        mount = root / _AITNA / ".akmon"
        mount.mkdir(parents=True)
        for directory in ("guardrails", "profiles"):
            shutil.copytree(akmon_root / directory, mount / directory)
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
        selected = mount / "profiles" / _largest_profile(akmon_root).name
        found = always_loaded.populations(agents, root, [selected])
        if found is None:  # unreachable while the generator writes the heading it declares
            raise RuntimeError("the generated AGENTS.md carries no marked akmon block")
        return found[always_loaded.shipped()]


def check_always_loaded(akmon_root: Path) -> list[Finding]:
    """One Finding: error over the akmon-shipped cap, ok under it, the measurement either way."""
    population = shipped_population(akmon_root)
    cap = always_loaded.caps()[always_loaded.shipped()]
    over = always_loaded.over(population, cap)
    return [
        Finding(
            "error" if over else "ok",
            "caps.always-loaded",
            always_loaded.report(population, cap),
            "AGENTS.md",
            _FIX_OVER if over else _FIX_OK,
        )
    ]
