"""Unit tests for ``meta/self_ci.py``'s failure reporting.

The installed-wheel leg has two kinds of red: something akmon ships is broken, and a
prerequisite of the leg is missing (no network reach, or a git that cannot authenticate
outside this checkout — the leg resolves the pin from the akmon repository's release tags).
They read identically as a bare exit status and cost very different work, so the leg has to
tell them apart.
"""

from __future__ import annotations

import self_ci

from common.findings import Finding

_PREREQUISITE = (
    "/tmp/x/venv/bin/akmon init --mode package --project-root /tmp/x/c --yes: "
    "akmon init: cannot discover the latest release tag from "
    "'https://github.com/akumidv/ai_akmon'; pass --ref explicitly"
)


def _finding(detail: str) -> Finding:
    message, fix = self_ci._wheel_smoke_report(detail)
    # Constructed, not just returned: the envelope caps ``fix`` at one sentence, and a
    # remediation that cannot be filed is the same as no remediation.
    return Finding("error", "selfci.wheel-smoke", message, "", fix)


def test_a_missing_prerequisite_is_named_as_one():
    finding = _finding(_PREREQUISITE)
    assert "prerequisite of this leg, not a packaging defect" in finding.message
    assert "cannot discover the latest release tag" in finding.message
    assert "gh auth setup-git" in finding.fix


def test_a_git_credential_failure_is_the_same_prerequisite():
    finding = _finding("fatal: could not read Username for 'https://github.com'")
    assert "prerequisite of this leg" in finding.message
    assert "gh auth setup-git" in finding.fix


def test_any_other_failure_keeps_the_packaging_remediation():
    finding = _finding("verify --strict: exit 1")
    assert finding.message == "installed-wheel smoke failed: verify --strict: exit 1"
    assert "fix the packaged-install failure" in finding.fix
    assert "gh auth" not in finding.fix
