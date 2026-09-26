"""C56 — the always-loaded counter: population, inclusive boundaries, report (ADR 0012 F18, F13 carriers)."""

from __future__ import annotations

from pathlib import Path

import pytest
from checks import always_loaded as shipped

from common import always_loaded as al

_KEYSTONE = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)

BLOCK = "## Dev layer — akmon\n\nintro line\n\n@_aitna/.akmon/guardrails/_common.md\n\n"
TAIL = "## Project\n\nhand-owned prose\n"


def _project(tmp_path: Path, *, block: str = BLOCK, tail: str = TAIL, files: dict[str, str] | None = None) -> str:
    files = {"_aitna/.akmon/guardrails/_common.md": "rule one\nrule two\n", **(files or {})}
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    agents = "# AGENTS.md\n\n" + block + tail
    (tmp_path / "AGENTS.md").write_text(agents, encoding="utf-8")
    return agents


def _names(population: al.Population) -> list[str]:
    return [member.name for member in population.members]


def test_the_block_runs_from_its_heading_to_the_next_peer_heading():
    agents = "# A\n\n## Dev layer — akmon (developing)\n\nx\n### sub\ny\n## Next\nz\n"
    assert al.marked_block(agents) == "## Dev layer — akmon (developing)\n\nx\n### sub\ny\n"
    assert al.marked_block("# A\n\n## Other\n") is None


def test_shipped_counts_block_chain_and_selected_once_and_consumer_counts_the_whole_file(tmp_path):
    agents = _project(tmp_path, files={"_aitna/.akmon/profiles/python.md": "py rule\n"})
    selected = [tmp_path / "_aitna/.akmon/profiles/python.md", tmp_path / "_aitna/.akmon/guardrails/_common.md"]
    found = al.populations(agents, tmp_path, selected)
    shipped, consumer = found[al.SHIPPED], found[al.CONSUMER]
    assert _names(shipped) == [
        "AGENTS.md (akmon block)",
        "_aitna/.akmon/guardrails/_common.md",
        "_aitna/.akmon/profiles/python.md",
    ]
    assert shipped.lines == len(BLOCK.splitlines()) + 2 + 1
    assert consumer.lines == len(agents.splitlines()) + 2 + 1
    assert consumer.size - shipped.size == len(agents.encode()) - len(BLOCK.encode())


@pytest.mark.parametrize(
    ("member", "text"),
    [("_aitna/.akmon/guardrails/_common.md", "rule one\nrule two\nrule three\n"), ("AGENTS.md (akmon block)", None)],
)
def test_changing_one_member_moves_the_shipped_count_by_exactly_that_member(tmp_path, member, text):
    before = al.populations(_project(tmp_path), tmp_path)[al.SHIPPED]
    if text is None:
        after = al.populations(_project(tmp_path, block=BLOCK + "one more line\n"), tmp_path)[al.SHIPPED]
        assert (after.lines - before.lines, after.size - before.size) == (1, len(b"one more line\n"))
    else:
        after = al.populations(_project(tmp_path, files={member: text}), tmp_path)[al.SHIPPED]
        assert (after.lines - before.lines, after.size - before.size) == (1, len(b"rule three\n"))


def test_transitive_imports_are_followed_once_relative_to_the_importing_file(tmp_path):
    files = {
        "_aitna/.akmon/guardrails/_common.md": "common\n@nested.md\n@nested.md\n",
        "_aitna/.akmon/guardrails/nested.md": "nested\n@_common.md\n",
    }
    found = al.populations(_project(tmp_path, files=files), tmp_path)[al.SHIPPED]
    assert _names(found) == [
        "AGENTS.md (akmon block)",
        "_aitna/.akmon/guardrails/_common.md",
        "_aitna/.akmon/guardrails/nested.md",
    ]


@pytest.mark.parametrize(
    "block",
    [
        BLOCK + "- [roles](_aitna/.akmon/roles/README.md) — a link is on-demand\n",
        BLOCK + "<!-- @_aitna/.akmon/profiles/python.md -->\n",
        BLOCK + "`@_aitna/.akmon/profiles/python.md`\n",
        BLOCK + "```\n@_aitna/.akmon/profiles/python.md\n```\n",
    ],
    ids=["link", "html-comment", "code-span", "fenced"],
)
def test_links_and_example_imports_stay_outside_the_population(tmp_path, block):
    files = {"_aitna/.akmon/profiles/python.md": "py\n", "_aitna/.akmon/roles/README.md": "roles\n"}
    found = al.populations(_project(tmp_path, block=block, files=files), tmp_path)[al.SHIPPED]
    assert _names(found) == ["AGENTS.md (akmon block)", "_aitna/.akmon/guardrails/_common.md"]


def test_imports_outside_the_marked_block_count_only_as_consumer_prose(tmp_path):
    files = {"_aitna/.akmon/profiles/python.md": "py\n"}
    agents = _project(tmp_path, tail=TAIL + "@_aitna/.akmon/profiles/python.md\n", files=files)
    found = al.populations(agents, tmp_path)
    assert "_aitna/.akmon/profiles/python.md" not in _names(found[al.SHIPPED])
    assert "_aitna/.akmon/profiles/python.md" not in _names(found[al.CONSUMER])


def test_an_import_leaving_the_project_is_not_counted(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("elsewhere\n", encoding="utf-8")
    found = al.populations(_project(tmp_path, block=BLOCK + f"@{outside}\n"), tmp_path)[al.SHIPPED]
    assert str(outside) not in " ".join(_names(found))


@pytest.mark.parametrize(
    ("scope", "delta", "expected"),
    [
        (al.SHIPPED, -1, False),
        (al.SHIPPED, 0, False),
        (al.SHIPPED, 1, True),
        (al.CONSUMER, -1, False),
        (al.CONSUMER, 0, False),
        (al.CONSUMER, 1, True),
    ],
)
def test_inclusive_line_boundary(scope, delta, expected):
    cap = al.CAPS[scope]
    population = al.Population(scope, (al.Member("m", "x\n" * (cap.lines + delta)),))
    assert population.size < cap.bytes
    assert al.over(population, cap) is expected


@pytest.mark.parametrize(
    ("scope", "delta", "expected"),
    [
        (al.SHIPPED, -1, False),
        (al.SHIPPED, 0, False),
        (al.SHIPPED, 1, True),
        (al.CONSUMER, -1, False),
        (al.CONSUMER, 0, False),
        (al.CONSUMER, 1, True),
    ],
)
def test_inclusive_byte_boundary(scope, delta, expected):
    cap = al.CAPS[scope]
    population = al.Population(scope, (al.Member("m", "y" * (cap.bytes + delta)),))
    assert population.lines < cap.lines
    assert al.over(population, cap) is expected


def test_the_report_is_dynamic_in_every_field():
    cap = al.Cap(lines=10, bytes=100)
    base = al.Population(al.CONSUMER, (al.Member("m", "ab\ncd\n"),))
    assert al.report(base, cap) == "consumer-total: lines=2/10 bytes=6/100"
    line_only = al.Population(al.CONSUMER, (al.Member("m", "ab\n\nd\n"),))  # a byte became a newline
    assert al.report(line_only, cap) == "consumer-total: lines=3/10 bytes=6/100"
    byte_only = al.Population(al.CONSUMER, (al.Member("m", "abX\ncd\n"),))
    assert al.report(byte_only, cap) == "consumer-total: lines=2/10 bytes=7/100"
    assert al.report(base, al.Cap(lines=11, bytes=100)) == "consumer-total: lines=2/11 bytes=6/100"
    assert al.report(base, al.Cap(lines=10, bytes=101)) == "consumer-total: lines=2/10 bytes=6/101"


# --------------------------------------------------------------------------------------
# C56 — the akmon-shipped scope: self_ci's error leg, measured on akmon's own tree
# --------------------------------------------------------------------------------------


def test_the_shipped_population_is_the_generated_block_its_chain_and_the_largest_profile():
    population = shipped.shipped_population(_KEYSTONE)
    names = [member.name for member in population.members]
    assert population.scope == al.SHIPPED
    assert names[0] == "AGENTS.md (akmon block)"
    assert names[1].endswith("guardrails/_common.md")
    assert names[-1].endswith(shipped._largest_profile(_KEYSTONE).name)


def test_the_counted_profile_is_the_largest_one_akmon_ships_and_ties_break_by_name(tmp_path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "small.md").write_text("x\n", encoding="utf-8")
    (profiles / "big.md").write_text("x\n" * 20, encoding="utf-8")
    assert shipped._largest_profile(tmp_path).name == "big.md"
    (profiles / "also-big.md").write_text("x\n" * 20, encoding="utf-8")
    assert shipped._largest_profile(tmp_path).name == "big.md"  # same size, later name


def test_what_akmon_ships_today_is_inside_its_own_cap():
    [finding] = shipped.check_always_loaded(_KEYSTONE)
    assert (finding.severity, finding.code, finding.target) == ("ok", "caps.always-loaded", "AGENTS.md")
    assert finding.message.startswith("akmon-shipped: lines=")


@pytest.mark.parametrize(
    ("cap", "severity"),
    [(al.Cap(lines=1, bytes=10**9), "error"), (al.Cap(lines=10**6, bytes=1), "error"), (None, "ok")],
    ids=["over-lines", "over-bytes", "inside"],
)
def test_the_shipped_leg_is_an_error_over_either_dimension(monkeypatch, cap, severity):
    if cap is not None:
        monkeypatch.setitem(al.CAPS, al.SHIPPED, cap)
    [finding] = shipped.check_always_loaded(_KEYSTONE)
    assert finding.severity == severity
    if severity == "error":
        assert "ADR 0012 F18" in finding.fix


def test_the_caps_in_code_are_the_numbers_the_adr_carries():
    """The ratchet is a decision; code and ADR cannot drift apart silently."""
    adr = (_KEYSTONE / "meta/decisions/0012-stage1-contracts-and-vocabulary.md").read_text(encoding="utf-8")
    for scope in (al.SHIPPED, al.CONSUMER):
        cap = al.CAPS[scope]
        assert f"`\u2264{cap.lines} lines` and `\u2264{cap.bytes:,} bytes`" in adr


def test_self_ci_runs_the_shipped_leg_against_akmons_own_tree():
    """Pins the wiring: the F18 error leg is useless if nothing calls it."""
    import inspect

    import self_ci

    assert "always_loaded_caps.check_always_loaded(akmon_root)" in inspect.getsource(self_ci._run)
