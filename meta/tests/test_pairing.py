"""Contract tests for the pairing gate (C103; ADR 0020 D03, design node-consumers.md §5 gate 3).

The synthetic trees each break exactly one relation the gate is responsible for keeping honest: an
unported file with no exemption is a gap; an exemption that has become unnecessary (every file it
covers is ported) is stale, while one still covering an unported file is live; a placeholder ``.mjs``
named by ``[[stub]]`` is not a port. A malformed ``pairing.toml`` is refused, not worked around. The
last test runs the gate over akmon's own tree — the live pin that the shipped list says what is
actually outstanding, and that C105's stub is still read as a stub.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_SPEC = importlib.util.spec_from_file_location("conformance_pairing", _AKMON / "meta" / "conformance" / "pairing.py")
pairing = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = pairing
_SPEC.loader.exec_module(pairing)

from corpus import CorpusError  # noqa: E402

_MODULE = '"""Fixture module."""\n'


def _tree(tmp_path: Path, *, py: tuple[str, ...] = (), mjs: tuple[str, ...] = ()) -> Path:
    """A synthetic tree: ``py`` are repo-relative sources, ``mjs`` the same paths under ``js/``."""
    for relative, base in [(rel, tmp_path) for rel in py] + [(rel, tmp_path / "js") for rel in mjs]:
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_MODULE, encoding="utf-8")
    return tmp_path


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pairing.toml"
    path.write_text(body, encoding="utf-8")
    return path


def _exempt(pattern: str) -> str:
    return f'[[exempt]]\npath = "{pattern}"\nreason = "the port is outstanding"\ntask = "C104"\n'


def _stub(path: str) -> str:
    return f'[[stub]]\npath = "{path}"\nreason = "the file only announces the missing port"\ntask = "C105"\n'


def _gate(tmp_path: Path, body: str, **tree) -> list:
    return pairing.check_pairing(_tree(tmp_path, **tree), _config(tmp_path, body))


def test_unported_unexempted_file_is_a_gap(tmp_path: Path) -> None:
    findings = _gate(tmp_path, "", py=("hooks/a.py", "common/b.py"))
    assert [(f.code, f.target) for f in findings] == [
        ("pairing.gap", "common/b.py"),
        ("pairing.gap", "hooks/a.py"),
    ]
    assert findings[0].message == "common/b.py has no .mjs counterpart under js/ and no pairing.toml exemption"


def test_ported_file_needs_no_exemption(tmp_path: Path) -> None:
    findings = _gate(tmp_path, "", py=("hooks/a.py",), mjs=("hooks/a.mjs",))
    assert [(f.severity, f.code) for f in findings] == [("ok", "pairing.ok")]
    assert "1 with their .mjs, 0 exempt" in findings[0].message


def test_exemption_covering_nothing_is_stale(tmp_path: Path) -> None:
    findings = _gate(tmp_path, _exempt("hooks/a.py") + _exempt("hooks/gone.py"), py=("hooks/a.py",))
    assert [(f.code, f.target) for f in findings] == [("pairing.stale", "hooks/gone.py")]
    assert "matches no consumer-executable .py" in findings[0].message


def test_fully_superseded_exemption_is_stale(tmp_path: Path) -> None:
    """Finding 10a: the port landed, so the pattern that covered it must say so by failing."""
    findings = _gate(
        tmp_path,
        _exempt("hooks/*"),
        py=("hooks/a.py", "hooks/b.py"),
        mjs=("hooks/a.mjs", "hooks/b.mjs"),
    )
    assert [(f.code, f.target) for f in findings] == [("pairing.stale", "hooks/*")]
    assert "fully superseded" in findings[0].message
    assert "the port it covered has landed" in findings[0].fix


def test_partially_superseded_exemption_stays_live(tmp_path: Path) -> None:
    findings = _gate(
        tmp_path,
        _exempt("hooks/*"),
        py=("hooks/a.py", "hooks/b.py"),
        mjs=("hooks/a.mjs",),
    )
    assert [(f.severity, f.code) for f in findings] == [("ok", "pairing.ok")]
    assert "1 with their .mjs, 1 exempt" in findings[0].message


def test_stub_counterpart_is_not_credited_as_a_port(tmp_path: Path) -> None:
    """Finding 10b: a placeholder ``.mjs`` keeps its ``.py`` out of the paired count."""
    findings = _gate(
        tmp_path,
        _exempt("hooks/*") + _stub("hooks/a.mjs"),
        py=("hooks/a.py", "hooks/b.py"),
        mjs=("hooks/a.mjs",),
    )
    assert [(f.severity, f.code) for f in findings] == [("ok", "pairing.ok")]
    assert "0 with their .mjs, 2 exempt, 1 of the exempt covered by a stub .mjs only" in findings[0].message


def test_stub_without_an_exemption_is_a_gap(tmp_path: Path) -> None:
    findings = _gate(tmp_path, _stub("hooks/a.mjs"), py=("hooks/a.py",), mjs=("hooks/a.mjs",))
    assert [(f.code, f.target) for f in findings] == [("pairing.gap", "hooks/a.py")]
    assert "stub .mjs placeholder" in findings[0].message


def test_stub_exemption_is_not_superseded(tmp_path: Path) -> None:
    """A stub is not a port, so the exemption still behind it stays live rather than turning stale."""
    findings = _gate(
        tmp_path,
        _exempt("hooks/a.py") + _stub("hooks/a.mjs"),
        py=("hooks/a.py",),
        mjs=("hooks/a.mjs",),
    )
    assert [(f.severity, f.code) for f in findings] == [("ok", "pairing.ok")]


def test_unknown_table_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CorpusError, match="unknown tables"):
        _gate(tmp_path, '[[other]]\npath = "hooks/a.py"\nreason = "r"\ntask = "C104"\n', py=("hooks/a.py",))


def test_entry_without_its_fields_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CorpusError, match=r"\[\[exempt\]\] entry"):
        _gate(tmp_path, '[[exempt]]\npath = "hooks/*"\n', py=("hooks/a.py",))


@pytest.mark.parametrize(
    "body",
    [
        _stub("hooks/a.py"),  # names a .py, not a .mjs
        _stub("hooks/gone.mjs"),  # names a file that is not there
        _stub("hooks/a.mjs") + _stub("hooks/a.mjs"),  # names one placeholder twice
    ],
    ids=["not-mjs", "missing-file", "duplicate"],
)
def test_bad_stub_entry_is_refused(tmp_path: Path, body: str) -> None:
    with pytest.raises(CorpusError, match=r"\[\[stub\]\]"):
        _gate(tmp_path, _exempt("hooks/*") + body, py=("hooks/a.py",), mjs=("hooks/a.mjs",))


def test_live_tree_passes_the_gate() -> None:
    findings = pairing.check_pairing(_AKMON)
    assert [(f.severity, f.code) for f in findings] == [("ok", "pairing.ok")]
    # The npm bin entry of this tree is C105's placeholder: it must not read as a landed port.
    assert "akmon/cli.mjs" in pairing.load_stubs()
    assert "1 of the exempt covered by a stub .mjs only" in findings[0].message
