"""akmon develops on its own layer: its repository is wired the way it wires a consumer.

The standard's own `.claude/settings.json` is not hand-kept. It is the wiring `akmon sync`
writes for a mounted consumer, with the materialized hook directory replaced by the in-tree
one — so a hook added, renamed or re-evented for consumers cannot quietly skip the repository
that ships it. `AGENTS.md` carries the same idea for prose: the guardrail and the profiles are
imported, never restated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import sync

_ROOT = Path(__file__).resolve().parents[2]
_SETTINGS = _ROOT / ".claude" / "settings.json"
_AGENTS = _ROOT / "AGENTS.md"
_IN_TREE_HOOKS = "$CLAUDE_PROJECT_DIR/hooks/"


def _shipped_wiring() -> dict:
    """What `akmon sync` would write for a mounted consumer, re-pointed at this tree."""
    mounted = f"$CLAUDE_PROJECT_DIR/{sync.aitna_root_name()}/akmon/hooks/"
    blob = json.dumps(sync._claude_hooks(_ROOT))
    assert mounted in blob, "the shipped wiring no longer names the mounted hook directory"
    return json.loads(blob.replace(mounted, _IN_TREE_HOOKS))


def test_akmon_wires_its_own_repository_exactly_as_it_wires_a_consumer():
    assert json.loads(_SETTINGS.read_text(encoding="utf-8")) == _shipped_wiring()


def test_every_wired_hook_script_exists_in_this_tree():
    blob = _SETTINGS.read_text(encoding="utf-8")
    scripts = set(re.findall(r"\$CLAUDE_PROJECT_DIR/hooks/([\w-]+\.py)", blob))
    assert scripts, "no hook is wired for akmon's own development"
    missing = sorted(name for name in scripts if not (_ROOT / "hooks" / name).is_file())
    assert missing == []


def test_the_dev_layer_imports_its_rules_instead_of_restating_them():
    text = _AGENTS.read_text(encoding="utf-8")
    imports = set(re.findall(r"^@(\S+)$", text, re.MULTILINE))
    assert "guardrails/_common.md" in imports
    assert {"profiles/python.md", "profiles/python-stdlib.md"} <= imports
    for target in imports:
        assert (_ROOT / target).is_file(), f"AGENTS.md imports a missing file: {target}"


def test_the_dev_layer_does_not_restate_an_imported_rule():
    """A rule the guardrail owns must not be paraphrased here — link or import it instead.

    The probe is the guardrail's own section names: if `AGENTS.md` grows a section of the same
    name, the single-owner rule has been broken. Delegation is the deliberate exception the
    file states, because Codex does not expand nested imports.
    """
    guardrail = (_ROOT / "guardrails" / "_common.md").read_text(encoding="utf-8")
    owned = {
        line[3:].split("—")[0].strip().lower()
        for line in guardrail.splitlines()
        if line.startswith("## ")
    }
    mine = {
        line[3:].split("—")[0].strip().lower()
        for line in _AGENTS.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    }
    assert owned & mine == set(), f"AGENTS.md restates a guardrail section: {sorted(owned & mine)}"


def test_akmon_ignores_what_it_tells_a_consumer_to_ignore():
    """`akmon init` appends these to a consumer's `.gitignore`; this repository never ran it.

    The hooks now run here (C99), so the same per-user, per-session routing artifacts appear in
    this tree. Only the mount-relative line is out of scope: akmon has no `_aitna/` of its own.
    """
    from akmon import _init

    aitna = "_aitna"
    wanted = [
        line.strip()
        for line in _init._gitignore_lines(aitna)
        if line.strip() and not line.startswith("#") and aitna not in line
    ]
    present = {
        line.strip()
        for line in (_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert [line for line in wanted if line not in present] == []
