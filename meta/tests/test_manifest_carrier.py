"""The npm carrier's manifest shape, gated (ADR 0020 D05, C103).

``test_carriers_match.py`` proves both carriers ship the same *files*; this proves the npm side
is still a carrier and not a project — no runtime dependency, no lifecycle hook, dev pins exact,
its version derived rather than hand-written. None of that was checked before this file: an added
``dependencies`` block, a ``postinstall`` script or a ``^`` range passed every gate in the
repository and reached whoever ran ``npm install -g akmon``. The zero-runtime-dependency promise
is the same one ADR 0009 §1 states for the wheel, spoken to a different installer.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from common.versions import semver_spelling

_AKMON = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "hooks").is_dir() and (parent / "bin").is_dir()
)
_MANIFEST = json.loads((_AKMON / "package.json").read_text(encoding="utf-8"))
_LOCK = json.loads((_AKMON / "package-lock.json").read_text(encoding="utf-8"))

# An exact pin is a version and nothing else: a caret, tilde, comparator, hyphen range, dist-tag
# or workspace protocol fails this. `npm ci` installs the lock, but the lock is only reviewable
# while the manifest that produced it names one version per dependency.
_EXACT_PIN_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def test_the_carrier_declares_no_runtime_dependency_and_no_scripts():
    # A lifecycle script is arbitrary code run at install time on the consumer's machine; a runtime
    # dependency pulls the tree a consumer installs out of the zero-dependency contract.
    for key in ("dependencies", "optionalDependencies", "peerDependencies", "scripts"):
        assert key not in _MANIFEST, f"{key} would make the npm carrier install something else"


def test_every_dev_dependency_is_an_exact_pin():
    floating = [
        f"{name} {spec}" for name, spec in _MANIFEST["devDependencies"].items() if not _EXACT_PIN_RE.fullmatch(spec)
    ]
    assert floating == []
    assert _EXACT_PIN_RE.fullmatch("^10.11.0") is None  # the seed this pin exists to catch


def test_engines_name_the_node_floor():
    # A floor is a claim about the code under ``js/``, so it is pinned as a claim: raising or
    # widening it is a deliberate act that has to pass through this assertion.
    assert _MANIFEST["engines"]["node"] == ">=22"


def test_the_bin_target_is_a_file_in_the_tree():
    # npm packs whatever ``bin`` names and symlinks it on install, so a dangling target installs a
    # command that cannot run.
    for name, relative in _MANIFEST["bin"].items():
        assert (_AKMON / relative).is_file(), f"bin.{name} points at {relative}, which is not in the tree"


def test_the_carrier_version_is_the_derived_spelling_of_the_python_one():
    # Checked against the derivation rule, never against a constant: the npm version is what
    # ``common/versions.py`` derives from the PEP 440 literal, so a hand-typed spelling fails here
    # even when it happens to look right today.
    with (_AKMON / "pyproject.toml").open("rb") as handle:
        declared = tomllib.load(handle)["project"]["version"]
    assert _MANIFEST["version"] == semver_spelling(declared)


def test_the_dev_lock_agrees_with_the_manifest_pins():
    # ``npm ci --ignore-scripts`` installs exactly this lock, so a lock that drifted from the
    # manifest would mean the tree reviewed and the tree installed are different trees.
    assert _LOCK["lockfileVersion"] == 3  # the ``packages`` form npm 7+ writes and ``npm ci`` reads
    root = _LOCK["packages"][""]
    assert root["devDependencies"] == _MANIFEST["devDependencies"]
    assert root["version"] == _MANIFEST["version"]
    for name, spec in _MANIFEST["devDependencies"].items():
        resolved = _LOCK["packages"].get(f"node_modules/{name}")
        assert resolved is not None and resolved["version"] == spec, f"{name} is not resolved at its pin"
    # Every entry dev, transitively: that is what proves the dev tooling installs no runtime
    # dependency graph alongside the carrier.
    assert [name for name, entry in _LOCK["packages"].items() if name and not entry.get("dev")] == []
