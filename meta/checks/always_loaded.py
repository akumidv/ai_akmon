#!/usr/bin/env python3
"""ADR 0012 F18 — akmon's shipped always-loaded share, measured against akmon's own tree.

The consumer-total scope is `verify.py`'s (the consumer owns most of that population and is
warned about it). This is the other half of the ratchet: the share akmon itself ships reaches
every attached project without anyone asking for it, so an overage is akmon's error, not the
consumer's warning.

The population is built the way a consumer receives it and never from a second copy of the
text: the block comes from the generator `akmon init` runs, the guardrail chain is resolved from
this tree through the shared counter, and the language profile is the **largest** one akmon
ships, imported the way `init` writes it — the profile follows the project's language, so
akmon is accountable for the biggest one it offers. A project with two languages imports two
profiles and is not what this scope measures (C127). Package mode is measured because its
block is the longer of the two (the shared layer and the document links are spelled out for a
tree-less consumer).
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from common import always_loaded, materialization
from common.findings import Finding

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

import session_start_text

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

    # The block a project with that profile's language gets: `init` writes its import line.
    classification = _init._Classification(profiles=(_largest_profile(akmon_root).name,))
    block = _init._agents_block(_AITNA, _REF, classification, package_mode=True)
    return _init._agents_header() + block


def _largest_profile(akmon_root: Path) -> Path:
    """The language profile that costs the most; ties resolve by name so the pick is stable."""
    profiles = sorted(akmon_root.joinpath("profiles").glob("*.md"))
    return max(profiles, key=lambda path: (len(path.read_bytes()), path.name))


def _write_charters(root: Path, akmon_root: Path) -> None:
    """The agent charters `akmon init` writes into a package-mode consumer, so the roster line is the real one."""
    if str(akmon_root / "src") not in sys.path:
        sys.path.insert(0, str(akmon_root / "src"))
    from akmon import _init  # noqa: PLC0415 — the generator is the source of this text

    for agent, spec in _init._charters().items():
        charter = root / _AITNA / "agents" / agent / "README.md"
        charter.parent.mkdir(parents=True, exist_ok=True)
        charter.write_text(_init._charter(agent, spec, _AITNA, package_mode=True), encoding="utf-8")


def shipped_population(akmon_root: Path) -> tuple[always_loaded.Population, always_loaded.OtherAudiences]:
    """What a package-mode consumer loads from akmon before it asks for anything, per audience.

    The population is the attended head's, which the cap is checked against; the other audiences' hook
    text comes beside it for the report.
    """
    agents = _generated_block(akmon_root)
    with tempfile.TemporaryDirectory(prefix="akmon-always-loaded-") as tmp:
        root = Path(tmp)
        mount = root / _AITNA / ".akmon"
        mount.mkdir(parents=True)
        for directory in materialization.imported_dirs():
            shutil.copytree(akmon_root / directory, mount / directory)
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
        selected = mount / "profiles" / _largest_profile(akmon_root).name
        _write_charters(root, akmon_root)
        found = always_loaded.populations(
            agents, root, [selected], hooks=session_start_text.session_start_members(root)
        )
        if found is None:  # unreachable while the generator writes the heading it declares
            raise RuntimeError("the generated AGENTS.md carries no marked akmon block")
        others = always_loaded.OtherAudiences(
            unattended=session_start_text.session_start_members(root, attended=False),
            delegate=session_start_text.subagent_start_members(root),
        )
        return found[always_loaded.shipped()], others


def check_always_loaded(akmon_root: Path) -> list[Finding]:
    """One Finding: error over the akmon-shipped cap, ok under it, the measurement either way."""
    population, others = shipped_population(akmon_root)
    cap = always_loaded.caps()[always_loaded.shipped()]
    over = always_loaded.over(population, cap)
    return [
        Finding(
            "error" if over else "ok",
            "caps.always-loaded",
            always_loaded.report(population, cap, others),
            "AGENTS.md",
            _FIX_OVER if over else _FIX_OK,
        )
    ]
