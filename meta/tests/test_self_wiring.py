"""akmon develops on its own layer: its repository is wired the way it wires a consumer.

Neither `.claude/settings.json` nor `.codex/hooks.json` is hand-kept. Each is the wiring
`akmon sync` writes for a mounted consumer, with the materialized hook directory (or, for
Codex, the mounted hook script) replaced by the in-tree one — so a hook added, renamed or
re-evented for consumers cannot quietly skip the repository that ships it. `AGENTS.md` carries
the same idea for prose: the guardrail and the profiles are imported, never restated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import sync

_ROOT = Path(__file__).resolve().parents[2]
_SETTINGS = _ROOT / ".claude" / "settings.json"
_CODEX = _ROOT / ".codex" / "hooks.json"
_AGENTS = _ROOT / "AGENTS.md"
_IN_TREE_HOOKS = "$CLAUDE_PROJECT_DIR/hooks/"
_IN_TREE_CODEX_HOOK = "$(git rev-parse --show-toplevel)/hooks/codex-hook.py"


def _consumer_root(tmp_path: Path) -> Path:
    """A throwaway mounted consumer: the one place the mounted spelling is built for comparison."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "_aitna" / "akmon").mkdir(parents=True)
    return tmp_path


def _consumer_wiring(tmp_path: Path) -> dict:
    """What `akmon sync` writes for a mounted consumer's Claude wiring, re-pointed at this tree."""
    consumer = _consumer_root(tmp_path)
    mounted = "$CLAUDE_PROJECT_DIR/_aitna/akmon/hooks/"
    blob = json.dumps(sync._claude_hooks(consumer))
    assert mounted in blob, "the shipped wiring no longer names the mounted hook directory"
    return json.loads(blob.replace(mounted, _IN_TREE_HOOKS))


def _consumer_codex_wiring(tmp_path: Path) -> dict:
    """What `akmon sync` writes for a mounted consumer's Codex wiring, re-pointed at this tree."""
    consumer = _consumer_root(tmp_path)
    mounted = "$(git rev-parse --show-toplevel)/_aitna/akmon/hooks/codex-hook.py"
    blob = json.dumps(sync._codex_hooks(consumer))
    assert mounted in blob, "the shipped Codex wiring no longer names the mounted hook script"
    return json.loads(blob.replace(mounted, _IN_TREE_CODEX_HOOK))


def test_akmon_wires_its_own_repository_exactly_as_it_wires_a_consumer(tmp_path):
    assert json.loads(_SETTINGS.read_text(encoding="utf-8")) == _consumer_wiring(tmp_path)


def test_akmon_wires_its_own_codex_hooks_exactly_as_it_wires_a_consumer(tmp_path):
    assert json.loads(_CODEX.read_text(encoding="utf-8")) == _consumer_codex_wiring(tmp_path)


def test_sync_on_akmon_itself_writes_the_committed_wiring():
    """C207: self-hosted, sync spells the in-tree path itself, so no mount prefix is mapped here."""
    assert sync.is_self_hosted(_ROOT)
    assert json.loads(_SETTINGS.read_text(encoding="utf-8")) == sync._claude_hooks(_ROOT)
    assert json.loads(_CODEX.read_text(encoding="utf-8")) == sync._codex_hooks(_ROOT)


def test_sync_check_passes_on_the_committed_tree():
    assert sync.main(["--project-root", str(_ROOT), "--check"]) == 0


def test_every_wired_hook_script_exists_in_this_tree():
    blob = _SETTINGS.read_text(encoding="utf-8") + _CODEX.read_text(encoding="utf-8")
    scripts = set(re.findall(r"/hooks/([\w-]+\.py)", blob))
    assert scripts, "no hook is wired for akmon's own development"
    missing = sorted(name for name in scripts if not (_ROOT / "hooks" / name).is_file())
    assert missing == []


def _archetype_rows(heading: str) -> dict[str, set[str]]:
    """One `ARCHETYPES.md` map table, keyed by its first column: the files each row links to.

    `heading` is the table's first header cell (`Language`, `Environment`). The map is the
    source of truth for which shared rules a project imports, so the dev layer's expected
    import set is read from it, never restated here.
    """
    rows: dict[str, set[str]] = {}
    inside = False
    for line in (_ROOT / "ARCHETYPES.md").read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.startswith("|"):
            inside = False
        elif cells[0] == heading:
            inside = True
        elif inside and not set(cells[0]) <= {"-"}:
            rows[cells[0]] = set(re.findall(r"\]\(((?:guardrails|profiles)/[\w.-]+\.md)\)", line))
    assert rows, f"ARCHETYPES.md has no `{heading}` table"
    return rows


def _expected_dev_imports() -> set[str]:
    """What the map prescribes for akmon itself: a mixed Python + JS tree with bare-interpreter hooks."""
    languages = _archetype_rows("Language")
    present = {"Python": (_ROOT / "pyproject.toml").is_file(), "JavaScript/TS": (_ROOT / "package.json").is_file()}
    assert set(present) <= set(languages), "ARCHETYPES.md renamed a language row this test reads"
    expected = set().union(*(languages[name] for name, here in present.items() if here))
    # The environment profile covers Python that runs on a bare interpreter; akmon's hooks do.
    if any((_ROOT / "hooks").glob("*.py")):
        expected |= set().union(*_archetype_rows("Environment").values())
    return expected


def test_the_dev_layer_imports_exactly_what_the_archetype_map_prescribes():
    """C10: akmon ships JS too, so the `js` profile is owed an import like `python` is."""
    imports = set(re.findall(r"^@(\S+)$", _AGENTS.read_text(encoding="utf-8"), re.MULTILINE))
    expected = _expected_dev_imports() | set(sync.always_imported())
    assert {"guardrails/_common.md", "profiles/python.md", "profiles/js.md"} <= expected
    # A domain profile is opt-in: akmon may import only those its declared archetype suggests.
    declared = re.search(r"\*\*Archetype:\*\* `([\w-]+)`", _AGENTS.read_text(encoding="utf-8"))
    assert declared, "AGENTS.md declares no archetype"
    suggested = _archetype_rows("Archetype").get(f"`{declared.group(1)}`", set())
    assert expected <= imports
    assert imports - expected <= suggested, f"opt-in imports the archetype does not suggest: {imports - expected - suggested}"


def test_the_dev_layer_imports_its_rules_instead_of_restating_them():
    text = _AGENTS.read_text(encoding="utf-8")
    imports = set(re.findall(r"^@(\S+)$", text, re.MULTILINE))
    assert imports, "AGENTS.md imports nothing"
    for target in imports:
        assert (_ROOT / target).is_file(), f"AGENTS.md imports a missing file: {target}"


def test_the_dev_layer_does_not_restate_an_imported_rule():
    """A rule the guardrail owns must not be paraphrased here — link or import it instead.

    The probe is the guardrail's own section names: if `AGENTS.md` grows a section of the same
    name, the single-owner rule has been broken. Delegation is the deliberate exception the
    file states, because Codex does not expand nested imports.
    """
    guardrail = (_ROOT / "guardrails" / "_common.md").read_text(encoding="utf-8")
    owned = {line[3:].split("—")[0].strip().lower() for line in guardrail.splitlines() if line.startswith("## ")}
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
    present = {line.strip() for line in (_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines() if line.strip()}
    assert [line for line in wanted if line not in present] == []
