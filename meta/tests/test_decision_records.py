"""Contract tests for thematic ADR block IDs and frozen D2 lookup aliases."""

from __future__ import annotations

from pathlib import Path

from checks import decision_records


def _tree(tmp_path: Path) -> Path:
    decisions = tmp_path / "meta" / "decisions"
    decisions.mkdir(parents=True)
    aliases = ", ".join(f"D2-{number}" for number in range(1, 52))
    (decisions / "0001-topic.md").write_text(
        "# 0001 — Topic\n\n### D01 — Choice\n\n"
        f"`Decision-ID: ADR-0001/D01`  \n`Legacy-ID: {aliases}`\n",
        encoding="utf-8",
    )
    (tmp_path / "meta" / "TASKS.md").write_text("# Tasks\n", encoding="utf-8")
    return tmp_path


def _codes(root: Path) -> list[str]:
    return [finding.code for finding in decision_records.check_decision_records(root) if finding.severity == "error"]


def test_complete_current_owner_map_is_clean(tmp_path):
    assert _codes(_tree(tmp_path)) == []


def test_duplicate_decision_id_is_rejected(tmp_path):
    root = _tree(tmp_path)
    (root / "meta" / "decisions" / "0001-other.md").write_text(
        "`Decision-ID: ADR-0001/D01`\n", encoding="utf-8"
    )
    assert _codes(root) == ["decision.duplicate-id"]


def test_decision_id_must_name_its_own_adr(tmp_path):
    root = _tree(tmp_path)
    path = root / "meta" / "decisions" / "0001-topic.md"
    path.write_text(path.read_text(encoding="utf-8").replace("ADR-0001/D01", "ADR-0002/D01"), encoding="utf-8")
    assert _codes(root) == ["decision.id-owner"]


def test_duplicate_legacy_alias_is_rejected(tmp_path):
    root = _tree(tmp_path)
    (root / "meta" / "TASKS.md").write_text("- N1 · open · `Legacy-ID: D2-7`\n", encoding="utf-8")
    assert _codes(root) == ["decision.legacy-duplicate"]


def test_alias_in_frozen_archive_does_not_resolve(tmp_path):
    root = _tree(tmp_path)
    current = root / "meta" / "decisions" / "0001-topic.md"
    current.write_text(current.read_text(encoding="utf-8").replace("D2-7, ", ""), encoding="utf-8")
    archive = root / "meta" / "archive" / "D2_LEDGER.md"
    archive.parent.mkdir()
    archive.write_text("`Legacy-ID: D2-7`\n", encoding="utf-8")
    assert _codes(root) == ["decision.legacy-missing"]


def test_new_legacy_number_is_rejected(tmp_path):
    root = _tree(tmp_path)
    tasks = root / "meta" / "TASKS.md"
    tasks.write_text("- A1 · new · `Legacy-ID: D2-52`\n", encoding="utf-8")
    assert _codes(root) == ["decision.legacy-unexpected"]
